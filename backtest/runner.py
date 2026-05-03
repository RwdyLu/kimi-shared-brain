"""
Backtest Runner / 回測執行器

Historical backtesting engine for BTC/ETH strategies.
BTC/ETH 策略的歷史回測引擎。

⚠️  ANALYSIS ONLY / 僅分析用途
⚠️  Past performance does not guarantee future results

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-14
"""

from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np

from backtest import (
    BacktestConfig, BacktestSummary, BacktestStorage,
    TradeRecord, TradeDirection, TradeResult
)
from data.fetcher import BinanceFetcher
from indicators import calculator as indicator_calc
from signals.engine import SignalEngine
from config.paths import PROJECT_ROOT

# Import plotly for chart generation / 匯入 plotly 生成圖表
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️  plotly not available, charts will be skipped")


class BacktestRunner:
    """
    Backtest execution engine
    回測執行引擎
    """

    # Minimum candles to hold before allowing take_profit exits
    # 最少持倉 K 線數（前 N 根只允許 stop_loss 出場）
    MIN_HOLD_CANDLES = 6

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.storage = BacktestStorage()

        # Initialize components
        self.fetcher = BinanceFetcher()
        self.signal_engine = SignalEngine()

        # Strategy identification
        self.strategy_id = config.strategy_id or config.strategy
        self.strategy_type = config.strategy_type or "trend_following"

        # State tracking
        self.active_trades: Dict[str, TradeRecord] = {}  # symbol -> TradeRecord
        self.closed_trades: List[TradeRecord] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.current_equity: float = config.initial_capital
        self.peak_equity: float = config.initial_capital
        self.max_drawdown: float = 0.0
        self.drawdown_start: Optional[str] = None

        # Daily risk control / 日內風控
        self.daily_pnl_pct = 0.0
        self.current_day = None
        self.daily_loss_limit = config.daily_loss_limit
        self.daily_profit_target = config.daily_profit_target

        # Generate backtest ID
        self.backtest_id = f"BT{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def run(self) -> BacktestSummary:
        """
        Execute the backtest
        執行回測
        """
        print(f"\n{'='*70}")
        print(f"🔄 BACKTEST START / 回測開始")
        print(f"{'='*70}")
        print(f"Backtest ID: {self.backtest_id}")
        print(f"Strategy: {self.strategy_id} ({self.strategy_type})")
        print(f"Period: {self.config.start_date} ~ {self.config.end_date}")
        print(f"Symbols: {', '.join(self.config.symbols)}")
        print(f"Initial Capital: ${self.config.initial_capital:,.2f}")
        print(f"{'='*70}\n")

        # Process each symbol
        for symbol in self.config.symbols:
            self._backtest_symbol(symbol)

        # Close any remaining open trades at end of test
        self._close_all_trades("end_of_test")
        
        # Build and save summary
        summary = self._build_summary()
        self.storage.save_backtest_result(summary)
        
        # Build and save equity chart (T-071)
        if PLOTLY_AVAILABLE:
            chart = self.build_equity_chart(summary)
            if chart:
                self.save_equity_chart(chart)
        
        # Print results
        self._print_results(summary)
        
        return summary

    def _backtest_symbol(self, symbol: str) -> None:
        """
        Run backtest for a single symbol
        對單一標的執行回測
        """
        print(f"\n📊 Processing {symbol}...")

        # Fetch historical data
        try:
            df = self._fetch_historical_data(symbol, interval="5m", limit=1000)  # T-071: 1000 bars of 5m
            if df is None or len(df) == 0:
                print(f"   ⚠️ No data available for {symbol}")
                return
            print(f"   ✓ Loaded {len(df)} candles (5m interval)")
        except Exception as e:
            print(f"   ✗ Error fetching data: {e}")
            return

        # Process each candle
        for candle_idx, (idx, row) in enumerate(df.iterrows()):
            timestamp = idx.strftime('%Y-%m-%d %H:%M')
            current_price = row['close']

            # Check for exit conditions on active trade
            if symbol in self.active_trades:
                self._check_exit_conditions(symbol, timestamp, current_price, row, candle_idx)

            # Check for entry signals (only if no active trade)
            if symbol not in self.active_trades:
                self._check_entry_signals(symbol, timestamp, current_price, row, df, candle_idx)

            # Update equity curve
            self._update_equity_curve(timestamp)

    def _fetch_historical_data(self, symbol: str, interval: str = "5m", limit: int = 500) -> Optional[pd.DataFrame]:
        """
        Fetch historical kline data
        取得歷史 K 線資料

        Args:
            symbol: Trading pair symbol (e.g., BTCUSDT)
            interval: Kline interval (default: 5m for backtesting)
            limit: Number of candles to fetch (default: 500)
        """
        # Convert dates to timestamps
        start_dt = datetime.strptime(self.config.start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(self.config.end_date, '%Y-%m-%d') + timedelta(days=1)

        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        # Fetch from Binance
        klines = self.fetcher.fetch_klines(
            symbol=symbol,
            interval=interval,  # T-071: Use 5m for backtesting
            start_time=start_ms,
            end_time=end_ms,
            limit=limit  # T-071: Fetch 500 bars
        )

        if not klines:
            return None

        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # Calculate indicators using module functions
        # Pad with None to match DataFrame length
        ma5_values = indicator_calc.calculate_ma5(df['close'].tolist())
        ma20_values = indicator_calc.calculate_ma20(df['close'].tolist())
        ma240_values = indicator_calc.calculate_ma240(df['close'].tolist())
        
        df['MA5'] = [None] * (len(df) - len(ma5_values)) + ma5_values if ma5_values else [None] * len(df)
        df['MA20'] = [None] * (len(df) - len(ma20_values)) + ma20_values if ma20_values else [None] * len(df)
        df['MA240'] = [None] * (len(df) - len(ma240_values)) + ma240_values if ma240_values else [None] * len(df)

        # Calculate additional indicators based on strategy needs
        closes = df['close'].tolist()
        highs = df['high'].tolist()
        lows = df['low'].tolist()
        volumes = df['volume'].tolist()

        # RSI (for rsi_trend, bb_mean_reversion, momentum_divergence)
        rsi_values = indicator_calc.calculate_rsi(closes, period=14)
        df['RSI'] = [None] * (len(df) - len(rsi_values)) + rsi_values if rsi_values else [None] * len(df)

        # EMA5/EMA10 (for ema_cross_fast)
        ema5_values = indicator_calc.calculate_ema(closes, period=5)
        ema10_values = indicator_calc.calculate_ema(closes, period=10)
        df['EMA5'] = [None] * (len(df) - len(ema5_values)) + ema5_values if ema5_values else [None] * len(df)
        df['EMA10'] = [None] * (len(df) - len(ema10_values)) + ema10_values if ema10_values else [None] * len(df)

        # EMA3/EMA8 (for ema_scalping)
        ema3_values = indicator_calc.calculate_ema(closes, period=3)
        ema8_values = indicator_calc.calculate_ema(closes, period=8)
        df['EMA3'] = [None] * (len(df) - len(ema3_values)) + ema3_values if ema3_values else [None] * len(df)
        df['EMA8'] = [None] * (len(df) - len(ema8_values)) + ema8_values if ema8_values else [None] * len(df)

        # CCI (for cci_reversal)
        cci_values = indicator_calc.calculate_cci(highs, lows, closes, period=14)
        df['CCI'] = [None] * (len(df) - len(cci_values)) + cci_values if cci_values else [None] * len(df)

        # ROC (for roc_momentum)
        roc_values = indicator_calc.calculate_roc(closes, period=10)
        df['ROC'] = [None] * (len(df) - len(roc_values)) + roc_values if roc_values else [None] * len(df)

        # TEMA (for hilbert_cycle, rsi_trend)
        tema_values = indicator_calc.calculate_tema(closes, period=9)
        df['TEMA'] = [None] * (len(df) - len(tema_values)) + tema_values if tema_values else [None] * len(df)

        # Bollinger Bands (for bb_mean_reversion, rsi_trend, bb_squeeze)
        bb = indicator_calc.calculate_bollinger_bands(closes, period=20, std_dev=2.0)
        bb_upper = bb.get('upper', [])
        bb_middle = bb.get('middle', [])
        bb_lower = bb.get('lower', [])
        df['BB_upper'] = [None] * (len(df) - len(bb_upper)) + bb_upper if bb_upper else [None] * len(df)
        df['BB_middle'] = [None] * (len(df) - len(bb_middle)) + bb_middle if bb_middle else [None] * len(df)
        df['BB_lower'] = [None] * (len(df) - len(bb_lower)) + bb_lower if bb_lower else [None] * len(df)
        
        # Calculate BB width for squeeze detection
        bb_width = []
        for i in range(len(closes)):
            if i < len(bb_upper) and i < len(bb_lower) and bb_upper[i] is not None and bb_lower[i] is not None and bb_middle[i] is not None and bb_middle[i] != 0:
                bb_width.append((bb_upper[i] - bb_lower[i]) / bb_middle[i])
            else:
                bb_width.append(None)
        df['BB_width'] = [None] * (len(df) - len(bb_width)) + bb_width if bb_width else [None] * len(df)

        # Stochastic (for stochastic_breakout)
        fastk, fastd = indicator_calc.calculate_stochastic(closes, highs, lows, k_period=5, d_period=3)
        df['STOCH_K'] = [None] * (len(df) - len(fastk)) + fastk if fastk else [None] * len(df)
        df['STOCH_D'] = [None] * (len(df) - len(fastd)) + fastd if fastd else [None] * len(df)

        # SAR (for stochastic_breakout)
        sar_values = indicator_calc.calculate_sar(highs, lows)
        df['SAR'] = [None] * (len(df) - len(sar_values)) + sar_values if sar_values else [None] * len(df)

        # Hilbert SineWave (for hilbert_cycle)
        ht = indicator_calc.calculate_ht_sine(closes)
        ht_sine = ht.get('sine', [])
        ht_leadsine = ht.get('leadsine', [])
        df['HT_SINE'] = [None] * (len(df) - len(ht_sine)) + ht_sine if ht_sine else [None] * len(df)
        df['HT_LEADSINE'] = [None] * (len(df) - len(ht_leadsine)) + ht_leadsine if ht_leadsine else [None] * len(df)

        # Price Channel (for price_channel_break)
        pc = indicator_calc.calculate_price_channel(highs, lows, period=20)
        pc_upper = pc.get('upper', [])
        df['PC_upper'] = [None] * (len(df) - len(pc_upper)) + pc_upper if pc_upper else [None] * len(df)

        # Volume MA20 (for volume analysis)
        volume_sma_values = []
        for i in range(len(volumes)):
            if i >= 19:
                volume_sma_values.append(sum(volumes[i-19:i+1]) / 20)
            else:
                volume_sma_values.append(None)
        df['volume_MA20'] = volume_sma_values

        return df

    def _check_entry_signals(self, symbol: str, timestamp: str, price: float, row: pd.Series, df: pd.DataFrame, idx: int) -> None:
        """
        Check for entry signals and open trades
        檢查進場訊號並開倉
        
        Fix B: Each strategy uses its own entry logic based on strategy_id
        """
        strategy_id = self.strategy_id

        # Determine entry direction and whether to open trade
        entry_triggered = False
        direction = TradeDirection.LONG
        reason = ""

        if strategy_id in ("ma_cross_trend", "ma_cross_trend_short"):
            entry_triggered, direction, reason = self._check_ma_cross_entry(symbol, row, df, idx)
        elif strategy_id == "hilbert_cycle":
            entry_triggered, direction, reason = self._check_hilbert_cycle_entry(symbol, row, df, idx)
        elif strategy_id == "stochastic_breakout":
            entry_triggered, direction, reason = self._check_stochastic_entry(symbol, row, df, idx)
        elif strategy_id == "rsi_trend":
            entry_triggered, direction, reason = self._check_rsi_trend_entry(symbol, row, df, idx)
        elif strategy_id == "rsi_mid_bounce":
            entry_triggered, direction, reason = self._check_rsi_bounce_entry(symbol, row, df, idx)
        elif strategy_id == "bb_mean_reversion":
            entry_triggered, direction, reason = self._check_bb_entry(symbol, row, df, idx)
        elif strategy_id == "ema_cross_fast":
            entry_triggered, direction, reason = self._check_ema_cross_entry(symbol, row, df, idx)
        elif strategy_id == "volume_spike":
            entry_triggered, direction, reason = self._check_volume_spike_entry(symbol, row, df, idx)
        elif strategy_id == "price_channel_break":
            entry_triggered, direction, reason = self._check_price_channel_entry(symbol, row, df, idx)
        elif strategy_id == "momentum_divergence":
            entry_triggered, direction, reason = self._check_momentum_divergence_entry(symbol, row, df, idx)
        elif strategy_id == "opening_range_breakout":
            entry_triggered, direction, reason = self._check_opening_range_entry(symbol, price, row, df, idx)
        elif strategy_id == "vwap_reversion":
            entry_triggered, direction, reason = self._check_vwap_reversion_entry(symbol, price, row, df, idx)
        elif strategy_id == "rsi_macd_confirm":
            entry_triggered, direction, reason = self._check_rsi_macd_entry(symbol, price, row, df, idx)
        elif strategy_id in ("contrarian_watch_overheated", "contrarian_watch_oversold"):
            # Contrarian watch strategies: log the signal but do NOT enter trades
            # They are WATCH-ONLY in the strategy config
            self._check_contrarian_watch(symbol, row, df, idx, strategy_id)
            return
        elif strategy_id == "bb_breakout":
            entry_triggered, direction, reason = self._check_bb_breakout_entry(symbol, row, df, idx)
        elif strategy_id == "ema_ribbon":
            entry_triggered, direction, reason = self._check_ema_ribbon_entry(symbol, row, df, idx)
        elif strategy_id == "momentum_breakout":
            entry_triggered, direction, reason = self._check_momentum_breakout_entry(symbol, row, df, idx)
        elif strategy_id == "supertrend":
            entry_triggered, direction, reason = self._check_supertrend_entry(symbol, row, df, idx)
        elif strategy_id == "ichimoku_cloud":
            entry_triggered, direction, reason = self._check_ichimoku_cloud_entry(symbol, row, df, idx)
        elif strategy_id == "williams_r":
            entry_triggered, direction, reason = self._check_williams_r_entry(symbol, row, df, idx)
        elif strategy_id == "atr_breakout":
            entry_triggered, direction, reason = self._check_atr_breakout_entry(symbol, row, df, idx)
        elif strategy_id == "dual_thrust":
            entry_triggered, direction, reason = self._check_dual_thrust_entry(symbol, row, df, idx)
        elif strategy_id == "parabolic_sar_v2":
            entry_triggered, direction, reason = self._check_parabolic_sar_v2_entry(symbol, row, df, idx)
        elif strategy_id == "keltner_breakout":
            entry_triggered, direction, reason = self._check_keltner_breakout_entry(symbol, row, df, idx)
        elif strategy_id == "ema_scalping":
            entry_triggered, direction, reason = self._check_ema_scalping_entry(symbol, row, df, idx)
        elif strategy_id == "bb_squeeze":
            entry_triggered, direction, reason = self._check_bb_squeeze_entry(symbol, row, df, idx)
        elif strategy_id == "rsi_scalping":
            entry_triggered, direction, reason = self._check_rsi_scalping_entry(symbol, row, df, idx)
        elif strategy_id == "cci_reversal":
            entry_triggered, direction, reason = self._check_cci_reversal_entry(symbol, row, df, idx)
        elif strategy_id == "roc_momentum":
            entry_triggered, direction, reason = self._check_roc_momentum_entry(symbol, row, df, idx)

        else:
            # Fallback: use unified signal engine (original behavior)
            entry_triggered, direction, reason = self._check_unified_entry(symbol, row, df, idx)

        if entry_triggered:
            trade = TradeRecord(
                trade_id=f"{self.backtest_id}_{symbol}_{len(self.closed_trades)}",
                symbol=symbol,
                direction=direction.value,
                entry_time=timestamp,
                entry_price=price,
                quantity=1.0,
                exit_reason=f"[{strategy_id}] {reason}",
            )

            self.active_trades[symbol] = trade
            self.storage.save_trade(trade)

            print(f"   ➡️  ENTRY [{strategy_id}]: {direction.value.upper()} @ ${price:,.2f} ({timestamp}) — {reason}")

    # ============================================================
    # Strategy-specific entry checks / 各策略獨立進場條件
    # ============================================================

    def _check_ma_cross_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """MA Cross Trend entry: MA5 vs MA20 cross + close vs MA240 + volume spike"""
        ma5 = row.get('MA5')
        ma20 = row.get('MA20')
        ma240 = row.get('MA240')
        close = row.get('close')
        volume = row.get('volume')

        if any(v is None for v in [ma5, ma20, ma240, close, volume]):
            return False, TradeDirection.LONG, "insufficient data"

        # Need at least 2 rows for cross detection
        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_ma5 = prev_row.get('MA5')
        prev_ma20 = prev_row.get('MA20')

        if prev_ma5 is None or prev_ma20 is None:
            return False, TradeDirection.LONG, "need previous MA"

        # Volume spike check
        volume_spike = indicator_calc.detect_volume_spike(
            df['volume'].tolist(), idx, period=20, multiplier=1.5
        )

        # MA cross trend: close > MA240, MA5 crosses above MA20, volume spike
        if close > ma240 and prev_ma5 <= prev_ma20 and ma5 > ma20 and volume_spike:
            return True, TradeDirection.LONG, f"MA5xMA20↑ close>MA240 vol_spike"

        # MA cross trend short: close < MA240, MA5 crosses below MA20, volume spike
        if close < ma240 and prev_ma5 >= prev_ma20 and ma5 < ma20 and volume_spike:
            return True, TradeDirection.SHORT, f"MA5xMA20↓ close<MA240 vol_spike"

        return False, TradeDirection.LONG, "no MA cross"

    def _check_hilbert_cycle_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Hilbert Cycle entry: HT_SINE cross above LEADSINE + TEMA rising"""
        ht_sine = row.get('HT_SINE')
        ht_leadsine = row.get('HT_LEADSINE')
        tema = row.get('TEMA')
        close = row.get('close')

        if any(v is None for v in [ht_sine, ht_leadsine, tema, close]):
            return False, TradeDirection.LONG, "insufficient data"

        # Need previous bar for cross detection
        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_sine = prev_row.get('HT_SINE')
        prev_leadsine = prev_row.get('HT_LEADSINE')
        prev_tema = prev_row.get('TEMA')

        if any(v is None for v in [prev_sine, prev_leadsine, prev_tema]):
            return False, TradeDirection.LONG, "need previous HT"

        # TEMA rising
        tema_rising = tema > prev_tema

        # HT_SINE cross above LEADSINE
        ht_cross = prev_sine <= prev_leadsine and ht_sine > ht_leadsine

        if ht_cross and tema_rising:
            return True, TradeDirection.LONG, f"HT_SINE×LEADSINE↑ TEMA↑"

        return False, TradeDirection.LONG, "no HT cycle signal"

    def _check_stochastic_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Stochastic Breakout entry: fastK cross above fastD + fastK < 20 + SAR below price"""
        fastk = row.get('STOCH_K')
        fastd = row.get('STOCH_D')
        sar = row.get('SAR')
        close = row.get('close')

        if any(v is None for v in [fastk, fastd, sar, close]):
            return False, TradeDirection.LONG, "insufficient data"

        # Need previous bar for cross detection
        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_k = prev_row.get('STOCH_K')
        prev_d = prev_row.get('STOCH_D')

        if prev_k is None or prev_d is None:
            return False, TradeDirection.LONG, "need previous STOCH"

        # fastK cross above fastD
        k_cross_d = prev_k <= prev_d and fastk > fastd
        # fastK < 20 (oversold)
        oversold = fastk < 20
        # SAR below price (uptrend)
        sar_below = sar < close

        if k_cross_d and oversold and sar_below:
            return True, TradeDirection.LONG, f"STOCH_K×D↑ K<20 SAR<close"

        return False, TradeDirection.LONG, "no stochastic signal"

    def _check_rsi_trend_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """RSI Trend entry: RSI cross above 30 + TEMA below BB middle + TEMA rising"""
        rsi = row.get('RSI')
        tema = row.get('TEMA')
        bb_middle = row.get('BB_middle')
        close = row.get('close')

        if any(v is None for v in [rsi, tema, bb_middle, close]):
            return False, TradeDirection.LONG, "insufficient data"

        # Need previous bar for cross detection
        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_rsi = prev_row.get('RSI')
        prev_tema = prev_row.get('TEMA')

        if prev_rsi is None or prev_tema is None:
            return False, TradeDirection.LONG, "need previous RSI/TEMA"

        # RSI cross above 30
        rsi_cross = prev_rsi <= 30 and rsi > 30
        # TEMA below BB middle
        tema_below_bb = tema < bb_middle
        # TEMA rising
        tema_rising = tema > prev_tema

        if rsi_cross and tema_below_bb and tema_rising:
            return True, TradeDirection.LONG, f"RSI×30↑ TEMA<BBmid TEMA↑"

        return False, TradeDirection.LONG, "no RSI trend signal"

    def _check_rsi_bounce_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """RSI Mid-Bounce entry: RSI cross above 40"""
        rsi = row.get('RSI')
        close = row.get('close')

        if any(v is None for v in [rsi, close]):
            return False, TradeDirection.LONG, "insufficient data"

        # Need previous bar for cross detection
        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_rsi = prev_row.get('RSI')

        if prev_rsi is None:
            return False, TradeDirection.LONG, "need previous RSI"

        # RSI cross above 40
        if prev_rsi <= 40 and rsi > 40:
            return True, TradeDirection.LONG, f"RSI×40↑"

        return False, TradeDirection.LONG, "no RSI bounce"

    def _check_bb_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """BB Mean Reversion entry: price below BB lower + RSI < 30 + volume spike"""
        close = row.get('close')
        bb_lower = row.get('BB_lower')
        rsi = row.get('RSI')
        volume = row.get('volume')

        if any(v is None for v in [close, bb_lower, rsi, volume]):
            return False, TradeDirection.LONG, "insufficient data"

        # Price below BB lower
        below_lower = close < bb_lower
        # RSI < 30 (oversold)
        rsi_oversold = rsi < 30
        # Volume spike
        volume_spike = indicator_calc.detect_volume_spike(
            df['volume'].tolist(), idx, period=20, multiplier=1.5
        )

        if below_lower and rsi_oversold and volume_spike:
            return True, TradeDirection.LONG, f"close<BBlower RSI<30 vol_spike"

        return False, TradeDirection.LONG, "no BB reversion signal"

    def _check_ema_cross_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """EMA Cross Fast entry: EMA5 cross above EMA10"""
        ema5 = row.get('EMA5')
        ema10 = row.get('EMA10')
        close = row.get('close')

        if any(v is None for v in [ema5, ema10, close]):
            return False, TradeDirection.LONG, "insufficient data"

        # Need previous bar for cross detection
        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_ema5 = prev_row.get('EMA5')
        prev_ema10 = prev_row.get('EMA10')

        if prev_ema5 is None or prev_ema10 is None:
            return False, TradeDirection.LONG, "need previous EMA"

        # EMA5 cross above EMA10
        if prev_ema5 <= prev_ema10 and ema5 > ema10:
            return True, TradeDirection.LONG, f"EMA5×EMA10↑"

        # EMA5 cross below EMA10 (short)
        if prev_ema5 >= prev_ema10 and ema5 < ema10:
            return True, TradeDirection.SHORT, f"EMA5×EMA10↓"

        return False, TradeDirection.LONG, "no EMA cross"

    def _check_volume_spike_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Volume Spike entry: volume > avg * 1.5"""
        volume = row.get('volume')

        if volume is None:
            return False, TradeDirection.LONG, "insufficient data"

        volume_spike = indicator_calc.detect_volume_spike(
            df['volume'].tolist(), idx, period=20, multiplier=1.5
        )

        if volume_spike:
            return True, TradeDirection.LONG, f"vol>{1.5}×avg"

        return False, TradeDirection.LONG, "no volume spike"

    def _check_price_channel_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Price Channel Break entry: price > 20-period high"""
        close = row.get('close')
        pc_upper = row.get('PC_upper')

        if any(v is None for v in [close, pc_upper]):
            return False, TradeDirection.LONG, "insufficient data"

        # Price above 20-period channel upper
        if close > pc_upper:
            return True, TradeDirection.LONG, f"close>20-period-high"

        return False, TradeDirection.LONG, "no channel break"

    def _check_momentum_divergence_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Momentum Divergence entry: price lower low + RSI higher low"""
        closes = df['close'].iloc[:idx+1].tolist()
        rsi_values = df['RSI'].iloc[:idx+1].tolist()

        # Remove None values
        valid_closes = [c for c in closes if c is not None]
        valid_rsi = [r for r in rsi_values if r is not None]

        if len(valid_closes) < 28 or len(valid_rsi) < 28:
            return False, TradeDirection.LONG, "insufficient data"

        divergence = indicator_calc.detect_momentum_divergence(valid_closes, valid_rsi, lookback=14)

        if divergence:
            return True, TradeDirection.LONG, f"bullish_divergence"

        return False, TradeDirection.LONG, "no divergence"

    def _check_contrarian_watch(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int, strategy_id: str) -> None:
        """
        Contrarian watch strategies: detect consecutive candles + close vs MA240
        These are WATCH-ONLY — no trades are opened
        """
        ma240 = row.get('MA240')
        close = row.get('close')

        if ma240 is None or close is None:
            return

        # Need at least 4 candles for consecutive detection
        if idx < 3:
            return

        # Build candles for consecutive detection
        candles = []
        for i in range(max(0, idx - 3), idx + 1):
            r = df.iloc[i]
            candles.append({
                'open': r.get('open'),
                'close': r.get('close'),
            })

        if strategy_id == "contrarian_watch_overheated":
            result = indicator_calc.detect_four_consecutive_green(candles)
            if result.pattern_detected and close > ma240:
                # Log the watch signal (but do NOT trade)
                print(f"   👁️  WATCH [overheated]: {symbol} 4 consecutive green + close>MA240 @ ${close:,.2f}")
        elif strategy_id == "contrarian_watch_oversold":
            result = indicator_calc.detect_four_consecutive_red(candles)
            if result.pattern_detected and close < ma240:
                # Log the watch signal (but do NOT trade)
                print(f"   👁️  WATCH [oversold]: {symbol} 4 consecutive red + close<MA240 @ ${close:,.2f}")

    def _check_unified_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Fallback: use unified signal engine (original behavior for unknown strategies)"""
        volume_history = df['volume'].iloc[max(0, idx-19):idx+1].tolist() if idx >= 0 else [row.get('volume')]

        indicators = {
            'MA5': row.get('MA5'),
            'MA20': row.get('MA20'),
            'MA240': row.get('MA240'),
            'volume': row.get('volume'),
            'volume_MA20': row.get('volume_MA20'),
            'volume_history': volume_history,
            'backtest_mode': True
        }

        signals = self.signal_engine.generate_signals(indicators)

        for signal in signals:
            if signal.level.value == "confirmed":
                direction = TradeDirection.LONG if "LONG" in signal.signal_type.name else TradeDirection.SHORT
                return True, direction, f"unified_{signal.signal_type.name}"

        return False, TradeDirection.LONG, "no unified signal"

    def _check_opening_range_entry(self, symbol: str, price: float, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """Opening Range Breakout entry: first candle of day defines range / 開盤區間突破 (每日限1次)"""
        # Check if already in position for this symbol
        if symbol in self.active_trades:
            return False, TradeDirection.LONG, "already in position"
        
        # Get current candle's date
        curr_ts = df.index[idx]
        curr_date = curr_ts.date()
        
        # Check if already traded today (track daily trades)
        if not hasattr(self, '_daily_trades'):
            self._daily_trades = {}  # symbol -> date
        
        if self._daily_trades.get(symbol) == curr_date:
            return False, TradeDirection.LONG, "already traded today"
        
        # Filter candles for today
        df_today = df[df.index.date == curr_date]
        if len(df_today) < 2:  # Need at least 2 candles
            return False, TradeDirection.LONG, "not enough candles"
        
        first_candle = df_today.iloc[0]
        range_high = float(first_candle['high'])
        range_low = float(first_candle['low'])
        
        # Only trade after the first candle
        if idx < 1 or curr_ts <= df_today.index[0]:
            return False, TradeDirection.LONG, "in opening candle"
        
        # Breakout above high -> long
        if price > range_high:
            self._daily_trades[symbol] = curr_date  # Mark as traded today
            return True, TradeDirection.LONG, f"ORB HIGH {range_high:.2f}"
        
        # Breakout below low -> short
        if price < range_low:
            self._daily_trades[symbol] = curr_date  # Mark as traded today
            return True, TradeDirection.SHORT, f"ORB LOW {range_low:.2f}"
        
        return False, TradeDirection.LONG, f"in range {range_low:.2f}-{range_high:.2f}"

    def _check_vwap_reversion_entry(self, symbol: str, price: float, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """VWAP Reversion entry: trade when price deviates from VWAP / VWAP 均值回歸"""
        if symbol in self.active_trades:
            return False, TradeDirection.LONG, "already in position"
        
        # Calculate VWAP up to current candle
        df_slice = df.iloc[:idx+1]
        vwap = (df_slice['close'] * df_slice['volume']).cumsum().iloc[-1] / df_slice['volume'].cumsum().iloc[-1]
        deviation = (price - vwap) / vwap
        
        # Deviation > 0.8% -> short (price too high)
        if deviation > 0.008:
            return True, TradeDirection.SHORT, f"VWAP dev +{deviation:.2%} VWAP={vwap:.2f}"
        
        # Deviation < -0.8% -> long (price too low)
        if deviation < -0.008:
            return True, TradeDirection.LONG, f"VWAP dev {deviation:.2%} VWAP={vwap:.2f}"
        
        return False, TradeDirection.LONG, f"VWAP dev {deviation:.2%} within range"

    def _check_rsi_macd_entry(self, symbol: str, price: float, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """RSI + MACD dual confirmation entry / RSI+MACD 雙重確認進場"""
        if symbol in self.active_trades:
            return False, TradeDirection.LONG, "already in position"
        
        if idx < 26:  # Need enough data for RSI(14) and EMA(26)
            return False, TradeDirection.LONG, "not enough data"
        
        df_slice = df.iloc[:idx+1]
        
        # Calculate RSI(14)
        delta = df_slice['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1])
        
        # Calculate MACD
        ema12 = df_slice['close'].ewm(span=12, adjust=False).mean()
        ema26 = df_slice['close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # Check for cross
        macd_cross_up = float(macd.iloc[-1]) > float(signal.iloc[-1]) and float(macd.iloc[-2]) <= float(signal.iloc[-2])
        macd_cross_down = float(macd.iloc[-1]) < float(signal.iloc[-1]) and float(macd.iloc[-2]) >= float(signal.iloc[-2])
        
        # RSI < 35 and MACD golden cross -> long
        if current_rsi < 35 and macd_cross_up:
            return True, TradeDirection.LONG, f"RSI={current_rsi:.1f} MACD golden cross"
        
        # RSI > 65 and MACD death cross -> short
        elif current_rsi > 65 and macd_cross_down:
            return True, TradeDirection.SHORT, f"RSI={current_rsi:.1f} MACD death cross"
        
        return False, TradeDirection.LONG, f"RSI={current_rsi:.1f} no signal"

    def _check_exit_conditions(self, symbol: str, timestamp: str, price: float, row: pd.Series, idx: int) -> None:
        """
        Check for exit conditions and close trades
        檢查出場條件並平倉
        
        B+C Fix: Minimum hold candles + only SL/TP exits (no exit_signal)
        """
        trade = self.active_trades[symbol]

        exit_triggered = False
        exit_price = price
        exit_reason = "signal"

        # Calculate how many candles we've held
        candles_held = idx - trade.entry_idx

        # Check stop loss (always allowed)
        if self.config.stop_loss_pct:
            if trade.direction == "long":
                stop_price = trade.entry_price * (1 - self.config.stop_loss_pct / 100)
                if price <= stop_price:
                    exit_triggered = True
                    exit_price = stop_price
                    exit_reason = "stop_loss"
            else:  # short
                stop_price = trade.entry_price * (1 + self.config.stop_loss_pct / 100)
                if price >= stop_price:
                    exit_triggered = True
                    exit_price = stop_price
                    exit_reason = "stop_loss"

        # During minimum hold period: ONLY stop_loss is allowed
        # 最少持倉期間內：只允許止損出場
        if not exit_triggered and candles_held < self.MIN_HOLD_CANDLES:
            return  # Skip take_profit and exit_signal

        # After minimum hold period: check take profit (no exit_signal)
        # 最少持倉期後：檢查止盈（不再檢查 exit_signal）
        if not exit_triggered and self.config.take_profit_pct:
            if trade.direction == "long":
                tp_price = trade.entry_price * (1 + self.config.take_profit_pct / 100)
                if price >= tp_price:
                    exit_triggered = True
                    exit_price = tp_price
                    exit_reason = "take_profit"
            else:  # short
                tp_price = trade.entry_price * (1 - self.config.take_profit_pct / 100)
                if price <= tp_price:
                    exit_triggered = True
                    exit_price = tp_price
                    exit_reason = "take_profit"

        if exit_triggered:
            self._close_trade(symbol, timestamp, exit_price, exit_reason)

    def _close_trade(self, symbol: str, exit_time: str, exit_price: float, reason: str) -> None:
        """
        Close an active trade
        平倉
        """
        trade = self.active_trades.pop(symbol)

        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.exit_reason = reason

        # Calculate P&L (gross, before commission)
        if trade.direction == "long":
            gross_pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
        else:  # short
            gross_pnl_pct = ((trade.entry_price - exit_price) / trade.entry_price) * 100

        # Deduct commission (entry + exit = 2 * commission_pct)
        commission_deduction = (self.config.commission_pct or 0.0) * 2
        trade.pnl_pct = gross_pnl_pct - commission_deduction

        trade.pnl_amount = (trade.pnl_pct / 100) * self.config.initial_capital * (self.config.position_size_pct / 100)

        if trade.pnl_pct >= 0:
            trade.result = TradeResult.CLOSED_PROFIT.value
            emoji = "✅"
        else:
            trade.result = TradeResult.CLOSED_LOSS.value
            emoji = "❌"

        self.closed_trades.append(trade)
        self.storage.save_trade(trade)

        # Update equity
        self.current_equity += trade.pnl_amount

        # Update daily PnL tracking / 更新日內風控 PnL
        self.daily_pnl_pct += trade.pnl_pct / 100  # convert pct to decimal

        print(f"   {emoji} EXIT: ${exit_price:,.2f} | Gross P&L: {gross_pnl_pct:+.2f}% | Net P&L: {trade.pnl_pct:+.2f}% ({reason})")

    def _close_all_trades(self, reason: str) -> None:
        """
        Close all active trades at end of backtest
        回測結束時平倉所有持倉
        """
        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            self._close_trade(symbol, "end_of_test", trade.entry_price, reason)

    def _update_equity_curve(self, timestamp: str) -> None:
        """
        Update equity curve tracking
        更新權益曲線
        """
        self.equity_curve.append({
            "timestamp": timestamp,
            "equity": self.current_equity
        })

        # Track drawdown
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
            self.drawdown_start = None
        else:
            drawdown = (self.peak_equity - self.current_equity) / self.peak_equity * 100
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
                if self.drawdown_start is None:
                    self.drawdown_start = timestamp

    def _build_summary(self) -> BacktestSummary:
        """
        Build backtest summary statistics
        建立回測摘要統計
        """
        total_trades = len(self.closed_trades)
        winning_trades = sum(1 for t in self.closed_trades if t.pnl_pct is not None and t.pnl_pct > 0)
        losing_trades = total_trades - winning_trades

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        total_return = ((self.current_equity - self.config.initial_capital) / self.config.initial_capital) * 100

        # Symbol breakdown
        symbol_stats = {}
        for symbol in self.config.symbols:
            symbol_trades = [t for t in self.closed_trades if t.symbol == symbol]
            if symbol_trades:
                symbol_stats[symbol] = {
                    "total_trades": len(symbol_trades),
                    "winning_trades": sum(1 for t in symbol_trades if t.pnl_pct is not None and t.pnl_pct > 0),
                    "total_pnl_pct": sum(t.pnl_pct for t in symbol_trades if t.pnl_pct)
                }

        return BacktestSummary(
            backtest_id=self.backtest_id,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            symbols=self.config.symbols,
            strategy=self.strategy_id or self.config.strategy,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return_pct=total_return,
            cumulative_return_pct=total_return,
            max_drawdown_pct=self.max_drawdown,
            max_drawdown_start=self.drawdown_start,
            symbol_stats=symbol_stats,
            equity_curve=self.equity_curve
        )

    def build_equity_chart(self, summary: Optional[BacktestSummary] = None) -> Optional[Any]:
        """
        Build equity curve and drawdown chart using plotly
        使用 plotly 建立權益曲線和回撤圖表

        Args:
            summary: BacktestSummary object (uses self._build_summary() if not provided)

        Returns:
            plotly Figure object with equity curve and drawdown subplots
        """
        if not PLOTLY_AVAILABLE:
            print("⚠️  plotly not available, cannot build chart")
            return None

        # Build summary if not provided
        if summary is None:
            summary = self._build_summary()

        # Prepare data
        if not self.equity_curve or len(self.equity_curve) == 0:
            print("⚠️  No equity curve data available")
            return None

        timestamps = [point["timestamp"] for point in self.equity_curve]
        equities = [point["equity"] for point in self.equity_curve]

        # Calculate drawdown series
        peak = self.config.initial_capital
        drawdowns = []
        for eq in equities:
            if eq > peak:
                peak = eq
            drawdown = ((peak - eq) / peak) * 100
            drawdowns.append(drawdown)

        # Create subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=(
                f"Equity Curve / 權益曲線 - {summary.backtest_id}",
                f"Drawdown / 回撤 - Max: {summary.max_drawdown_pct:.2f}%"
            ),
            row_heights=[0.7, 0.3]
        )

        # Add equity curve
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=equities,
                mode='lines',
                name='Equity',
                line=dict(color='#2ecc71', width=2),
                fill='tozeroy',
                fillcolor='rgba(46, 204, 113, 0.1)'
            ),
            row=1, col=1
        )

        # Add initial capital reference line
        fig.add_hline(
            y=self.config.initial_capital,
            line_dash="dash",
            line_color="gray",
            annotation_text="Initial Capital",
            row=1, col=1
        )

        # Add drawdown chart
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=drawdowns,
                mode='lines',
                name='Drawdown %',
                line=dict(color='#e74c3c', width=1.5),
                fill='tozeroy',
                fillcolor='rgba(231, 76, 60, 0.2)'
            ),
            row=2, col=1
        )

        # Update layout
        fig.update_layout(
            title_text=f"Backtest Results: {', '.join(summary.symbols)} | Return: {summary.total_return_pct:+.2f}% | Win Rate: {summary.win_rate:.1f}%",
            title_x=0.5,
            height=600,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white'
        )

        # Update y-axes labels
        fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)
        fig.update_xaxes(title_text="Time", row=2, col=1)

        return fig

    def save_equity_chart(self, fig: Any, filename: Optional[str] = None) -> str:
        """
        Save equity chart to HTML file
        儲存權益圖表為 HTML

        Args:
            fig: plotly Figure object
            filename: Output filename (default: auto-generated)

        Returns:
            Path to saved file
        """
        if fig is None:
            return ""

        if filename is None:
            filename = f"equity_chart_{self.backtest_id}.html"

        output_path = PROJECT_ROOT / "outbox" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fig.write_html(str(output_path))
        print(f"📈 Chart saved: {output_path}")

        return str(output_path)

    def _print_results(self, summary: BacktestSummary) -> None:
        """
        Print backtest results to console
        印出回測結果
        """
        print(f"\n{'='*70}")
        print(f"📊 BACKTEST RESULTS / 回測結果")
        print(f"{'='*70}")
        print(f"Backtest ID: {summary.backtest_id}")
        print(f"Period: {summary.start_date} ~ {summary.end_date}")
        print(f"{'='*70}")

        print(f"\n💰 PERFORMANCE / 績效")
        print(f"   Initial Capital: ${self.config.initial_capital:,.2f}")
        print(f"   Final Equity:    ${self.current_equity:,.2f}")
        print(f"   Total Return:    {summary.total_return_pct:+.2f}%")

        print(f"\n📈 TRADE STATISTICS / 交易統計")
        print(f"   Total Trades:    {summary.total_trades}")
        print(f"   Winning Trades:  {summary.winning_trades}")
        print(f"   Losing Trades:   {summary.losing_trades}")
        print(f"   Win Rate:        {summary.win_rate:.1f}%")

        print(f"\n⚠️  RISK METRICS / 風險指標")
        print(f"   Max Drawdown:    {summary.max_drawdown_pct:.2f}%")

        print(f"\n📊 SYMBOL BREAKDOWN / 標的明細")
        for symbol, stats in summary.symbol_stats.items():
            print(f"   {symbol}: {stats['total_trades']} trades, {stats['total_pnl_pct']:+.2f}%")

        print(f"\n{'='*70}")
        print(f"✅ BACKTEST COMPLETE / 回測完成")
        print(f"{'='*70}\n")


    def _check_ema_scalping_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """EMA Scalping: EMA3 cross EMA8 + RSI 40-60 filter"""
        ema3 = row.get('EMA3')
        ema8 = row.get('EMA8')
        rsi = row.get('RSI')
        close = row.get('close')

        if any(v is None for v in [ema3, ema8, rsi, close]):
            return False, TradeDirection.LONG, "insufficient data"

        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_ema3 = prev_row.get('EMA3')
        prev_ema8 = prev_row.get('EMA8')

        if prev_ema3 is None or prev_ema8 is None:
            return False, TradeDirection.LONG, "need previous EMA"

        # RSI filter: avoid chasing highs/lows
        if rsi < 40 or rsi > 60:
            return False, TradeDirection.LONG, f"RSI {rsi:.1f} outside 40-60"

        # EMA3 cross above EMA8 -> LONG
        if prev_ema3 <= prev_ema8 and ema3 > ema8:
            return True, TradeDirection.LONG, f"EMA3×EMA8↑ RSI={rsi:.1f}"

        # EMA3 cross below EMA8 -> SHORT
        if prev_ema3 >= prev_ema8 and ema3 < ema8:
            return True, TradeDirection.SHORT, f"EMA3×EMA8↓ RSI={rsi:.1f}"

        return False, TradeDirection.LONG, "no EMA cross"

    def _check_bb_squeeze_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """BB Squeeze: Band width < min(20) then breakout"""
        close = row.get('close')
        bb_upper = row.get('BB_upper')
        bb_lower = row.get('BB_lower')
        bb_width = row.get('BB_width')
        volume = row.get('volume')

        if any(v is None for v in [close, bb_upper, bb_lower, bb_width, volume]):
            return False, TradeDirection.LONG, "insufficient data"

        if idx < 20:
            return False, TradeDirection.LONG, "need 20 bars"

        # Check if current width is near minimum of last 20
        recent_width = df['BB_width'].iloc[idx-19:idx+1].dropna().tolist()
        if len(recent_width) < 5:
            return False, TradeDirection.LONG, "no BB width data"

        min_width = min(recent_width)
        is_squeezed = bb_width <= min_width * 1.05  # within 5% of minimum

        # Volume spike
        volume_spike = indicator_calc.detect_volume_spike(
            df['volume'].tolist(), idx, period=20, multiplier=1.2
        )

        if not is_squeezed:
            return False, TradeDirection.LONG, f"BB width {bb_width:.4f} not squeezed"

        if not volume_spike:
            return False, TradeDirection.LONG, "no volume spike"

        # Breakout above upper band -> LONG
        if close > bb_upper:
            return True, TradeDirection.LONG, f"BB squeeze breakout↑ vol>1.2×avg"

        # Breakdown below lower band -> SHORT
        if close < bb_lower:
            return True, TradeDirection.SHORT, f"BB squeeze breakout↓ vol>1.2×avg"

        return False, TradeDirection.LONG, f"in squeeze but no breakout"

    def _check_rsi_scalping_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """RSI Scalping with ADX filter: RSI cross 30/70 + ADX proxy < 2.5 (ranging market)"""
        rsi = row.get('RSI')
        close = row.get('close')

        if any(v is None for v in [rsi, close]):
            return False, TradeDirection.LONG, "insufficient data"

        if idx < 28:
            return False, TradeDirection.LONG, "need 28 bars for ADX"

        prev_row = df.iloc[idx - 1]
        prev_rsi = prev_row.get('RSI')

        if prev_rsi is None:
            return False, TradeDirection.LONG, "need previous RSI"

        # Calculate ADX proxy: price_range / (atr * 14)
        high_slice = df['high'].iloc[idx-14:idx+1]
        low_slice = df['low'].iloc[idx-14:idx+1]
        close_slice = df['close'].iloc[idx-14:idx+1]
        
        tr_values = (high_slice - low_slice).abs()
        atr = tr_values.mean()
        price_range = high_slice.max() - low_slice.min()
        
        if atr == 0 or pd.isna(atr):
            return False, TradeDirection.LONG, "ATR zero"
            
        adx_proxy = price_range / (atr * 14) * 100

        # Only trade in ranging market (ADX proxy < 30)
        if adx_proxy > 30:
            return False, TradeDirection.LONG, f"trending ADX={adx_proxy:.1f}"

        # RSI cross above 30 from below -> LONG
        if prev_rsi <= 30 and rsi > 30:
            return True, TradeDirection.LONG, f"RSI×30↑ {prev_rsi:.1f}->{rsi:.1f} ADX={adx_proxy:.1f}"

        # RSI cross below 70 from above -> SHORT
        if prev_rsi >= 70 and rsi < 70:
            return True, TradeDirection.SHORT, f"RSI×70↓ {prev_rsi:.1f}->{rsi:.1f} ADX={adx_proxy:.1f}"

        return False, TradeDirection.LONG, f"RSI={rsi:.1f} no signal"

    def _check_cci_reversal_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """CCI Reversal: CCI < -100 LONG, CCI > +100 SHORT"""
        cci = row.get('CCI')
        close = row.get('close')

        if any(v is None for v in [cci, close]):
            return False, TradeDirection.LONG, "insufficient data"

        if idx < 1:
            return False, TradeDirection.LONG, "need previous bar"

        prev_row = df.iloc[idx - 1]
        prev_cci = prev_row.get('CCI')

        if prev_cci is None:
            return False, TradeDirection.LONG, "need previous CCI"

        # CCI cross above -100 from below -> LONG
        if prev_cci <= -100 and cci > -100:
            return True, TradeDirection.LONG, f"CCI×-100↑ {prev_cci:.1f}->{cci:.1f}"

        # CCI cross below +100 from above -> SHORT
        if prev_cci >= 100 and cci < 100:
            return True, TradeDirection.SHORT, f"CCI×+100↓ {prev_cci:.1f}->{cci:.1f}"

        return False, TradeDirection.LONG, "no CCI signal"

    def _check_roc_momentum_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        """ROC Momentum: ROC > +0.5% LONG, ROC < -0.5% SHORT, need 2 consecutive bars"""
        roc = row.get('ROC')
        close = row.get('close')

        if any(v is None for v in [roc, close]):
            return False, TradeDirection.LONG, "insufficient data"

        if idx < 2:
            return False, TradeDirection.LONG, "need 2 previous bars"

        prev_row = df.iloc[idx - 1]
        prev2_row = df.iloc[idx - 2]
        prev_roc = prev_row.get('ROC')
        prev2_roc = prev2_row.get('ROC')

        if prev_roc is None or prev2_roc is None:
            return False, TradeDirection.LONG, "need previous ROC"

        # ROC > +0.5% for 2 consecutive bars -> LONG
        if roc > 0.5 and prev_roc > 0.5:
            return True, TradeDirection.LONG, f"ROC>0.5%×2 {roc:.2f}%"

        # ROC < -0.5% for 2 consecutive bars -> SHORT
        if roc < -0.5 and prev_roc < -0.5:
            return True, TradeDirection.SHORT, f"ROC<-0.5%×2 {roc:.2f}%"

        return False, TradeDirection.LONG, f"ROC {roc:.2f}% no signal"


def run_backtest(
    symbols: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 10000.0,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    commission_pct: Optional[float] = None,
    strategy_id: Optional[str] = None,
    strategy_type: Optional[str] = None,
    daily_loss_limit: float = -0.02,
    daily_profit_target: float = 0.015,
) -> BacktestSummary:
    """
    Convenience function to run a backtest
    執行回測的便捷函數

    Args:
        symbols: List of symbols to test (default: ["BTCUSDT", "ETHUSDT"])
        start_date: Start date (YYYY-MM-DD, default: 30 days ago)
        end_date: End date (YYYY-MM-DD, default: today)
        initial_capital: Starting capital
        stop_loss_pct: Stop loss percentage (e.g., 5.0 for 5%)
        take_profit_pct: Take profit percentage (e.g., 10.0 for 10%)
        commission_pct: Commission percentage per side (e.g., 0.1 for 0.1%)
        strategy_id: Strategy ID (e.g., "ma_cross_trend", "rsi_trend")
        strategy_type: Strategy type (e.g., "trend_following", "momentum")

    Returns:
        BacktestSummary with results
    """
    # Set defaults
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    if start_date is None:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    # Create config
    config = BacktestConfig(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        commission_pct=commission_pct or 0.0,
        daily_loss_limit=daily_loss_limit,
        daily_profit_target=daily_profit_target,
    )

    # Run backtest
    runner = BacktestRunner(config)
    return runner.run()


if __name__ == "__main__":
    # Example usage
    summary = run_backtest(
        symbols=["BTCUSDT", "ETHUSDT"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_capital=10000.0,
        stop_loss_pct=5.0,
        take_profit_pct=10.0
    )

    print(f"\nBacktest saved with ID: {summary.backtest_id}")


    def _check_bb_breakout_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        df_slice['ma20'] = df_slice['close'].rolling(20).mean()
        df_slice['std20'] = df_slice['close'].rolling(20).std()
        df_slice['upper'] = df_slice['ma20'] + 2 * df_slice['std20']
        df_slice['lower'] = df_slice['ma20'] - 2 * df_slice['std20']
        df_slice['vol_ma20'] = df_slice['volume'].rolling(20).mean()

        upper = float(df_slice['upper'].iloc[-1])
        lower = float(df_slice['lower'].iloc[-1])
        price = float(row['close'])
        vol = float(row['volume'])
        vol_ma = float(df_slice['vol_ma20'].iloc[-1])

        if vol < vol_ma * 1.2:
            return False, None, f"Volume {vol:.0f} < {vol_ma*1.2:.0f} threshold"

        if price > upper:
            return True, "LONG", f"BB upper breakout {upper:.2f}"
        elif price < lower:
            return True, "SHORT", f"BB lower breakdown {lower:.2f}"
        return False, None, f"Price {price:.2f} within BB bands"

    def _check_ema_ribbon_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        df_slice['ema8'] = df_slice['close'].ewm(span=8).mean()
        df_slice['ema21'] = df_slice['close'].ewm(span=21).mean()
        df_slice['ema55'] = df_slice['close'].ewm(span=55).mean()

        e8 = float(df_slice['ema8'].iloc[-1])
        e21 = float(df_slice['ema21'].iloc[-1])
        e55 = float(df_slice['ema55'].iloc[-1])

        if e8 > e21 > e55:
            return True, "LONG", f"EMA ribbon LONG {e8:.2f}>{e21:.2f}>{e55:.2f}"
        elif e8 < e21 < e55:
            return True, "SHORT", f"EMA ribbon SHORT {e8:.2f}<{e21:.2f}<{e55:.2f}"
        return False, None, f"EMA not aligned {e8:.2f}/{e21:.2f}/{e55:.2f}"

    def _check_momentum_breakout_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        high_10 = float(df_slice['high'].rolling(10).max().iloc[-1])
        low_10 = float(df_slice['low'].rolling(10).min().iloc[-1])

        delta = df_slice['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1])
        price = float(row['close'])

        if current_rsi < 40 or current_rsi > 60:
            return False, None, f"RSI {current_rsi:.1f} outside 40-60"

        if price > high_10:
            return True, "LONG", f"Momentum breakout {high_10:.2f}"
        elif price < low_10:
            return True, "SHORT", f"Momentum breakdown {low_10:.2f}"
        return False, None, f"Price {price:.2f} within range"

    def _check_supertrend_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        n = 10
        mult = 3.0

        df_slice['hl2'] = (df_slice['high'] + df_slice['low']) / 2
        df_slice['atr'] = df_slice['high'].rolling(n).max() - df_slice['low'].rolling(n).min()
        df_slice['upper_band'] = df_slice['hl2'] + mult * df_slice['atr']
        df_slice['lower_band'] = df_slice['hl2'] - mult * df_slice['atr']

        st = [df_slice['lower_band'].iloc[0]]
        direction = [1]

        for i in range(1, len(df_slice)):
            if df_slice['close'].iloc[i] > df_slice['upper_band'].iloc[i-1]:
                st.append(df_slice['lower_band'].iloc[i])
                direction.append(1)
            elif df_slice['close'].iloc[i] < df_slice['lower_band'].iloc[i-1]:
                st.append(df_slice['upper_band'].iloc[i])
                direction.append(-1)
            else:
                st.append(st[-1])
                direction.append(direction[-1])

        if len(direction) < 2:
            return False, None, "Not enough data"

        current_dir = direction[-1]
        prev_dir = direction[-2]

        if current_dir == 1 and prev_dir == -1:
            return True, "LONG", "Supertrend flipped LONG"
        elif current_dir == -1 and prev_dir == 1:
            return True, "SHORT", "Supertrend flipped SHORT"
        return False, None, f"Supertrend dir {current_dir}"

    def _check_ichimoku_cloud_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        high_9 = df_slice['high'].rolling(9).max()
        low_9 = df_slice['low'].rolling(9).min()
        high_26 = df_slice['high'].rolling(26).max()
        low_26 = df_slice['low'].rolling(26).min()

        df_slice['tenkan'] = (high_9 + low_9) / 2
        df_slice['kijun'] = (high_26 + low_26) / 2
        df_slice['senkou_a'] = ((df_slice['tenkan'] + df_slice['kijun']) / 2).shift(26)
        df_slice['senkou_b'] = ((df_slice['high'].rolling(52).max() + df_slice['low'].rolling(52).min()) / 2).shift(26)

        price = float(row['close'])
        senkou_a = float(df_slice['senkou_a'].iloc[-1])
        senkou_b = float(df_slice['senkou_b'].iloc[-1])
        tenkan = float(df_slice['tenkan'].iloc[-1])
        kijun = float(df_slice['kijun'].iloc[-1])

        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)

        if price > cloud_top and tenkan > kijun:
            return True, "LONG", f"Ichimoku LONG {cloud_top:.2f}"
        elif price < cloud_bottom and tenkan < kijun:
            return True, "SHORT", f"Ichimoku SHORT {cloud_bottom:.2f}"
        return False, None, f"Price {price:.2f} in cloud"

    def _check_williams_r_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        high_14 = df_slice['high'].rolling(14).max()
        low_14 = df_slice['low'].rolling(14).min()
        df_slice['williams_r'] = (df_slice['close'] - high_14) / (high_14 - low_14) * -100

        wr_values = df_slice['williams_r'].tail(3).values
        if len(wr_values) < 3:
            return False, None, "Not enough data"
        current_wr = float(wr_values[-1])

        if current_wr < -80 and all(w < -80 for w in wr_values):
            return True, "LONG", f"Williams %R oversold {current_wr:.1f}"
        elif current_wr > -20 and all(w > -20 for w in wr_values):
            return True, "SHORT", f"Williams %R overbought {current_wr:.1f}"
        return False, None, f"Williams %R {current_wr:.1f}"

    def _check_atr_breakout_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        df_slice['tr1'] = df_slice['high'] - df_slice['low']
        df_slice['tr2'] = abs(df_slice['high'] - df_slice['close'].shift(1))
        df_slice['tr3'] = abs(df_slice['low'] - df_slice['close'].shift(1))
        df_slice['tr'] = df_slice[['tr1', 'tr2', 'tr3']].max(axis=1)
        df_slice['atr'] = df_slice['tr'].rolling(14).mean()

        if len(df_slice) < 2:
            return False, None, "Not enough data"

        prev_close = float(df_slice['close'].iloc[-2])
        atr = float(df_slice['atr'].iloc[-1])
        price = float(row['close'])
        upper = prev_close + 1.5 * atr
        lower = prev_close - 1.5 * atr

        if price > upper:
            return True, "LONG", f"ATR LONG {upper:.2f}"
        elif price < lower:
            return True, "SHORT", f"ATR SHORT {lower:.2f}"
        return False, None, f"Price {price:.2f} within ATR"

    def _check_dual_thrust_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        if len(df_slice) < 5:
            return False, None, "Not enough data"

        hh = float(df_slice['high'].rolling(4).max().iloc[-1])
        ll = float(df_slice['low'].rolling(4).min().iloc[-1])
        hc = float(df_slice['close'].rolling(4).max().iloc[-1])
        lc = float(df_slice['close'].rolling(4).min().iloc[-1])

        range_val = max(hh - lc, hc - ll)
        open_price = float(row['open'])
        price = float(row['close'])
        k = 0.5

        if price > open_price + k * range_val:
            return True, "LONG", "Dual Thrust LONG"
        elif price < open_price - k * range_val:
            return True, "SHORT", "Dual Thrust SHORT"
        return False, None, "Price within range"

    def _check_parabolic_sar_v2_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        if len(df_slice) < 2:
            return False, None, "Not enough data"

        af = 0.02
        max_af = 0.2
        sar = float(df_slice['low'].iloc[0])
        ep = float(df_slice['high'].iloc[0])
        trend = 1
        directions = [trend]

        for i in range(1, len(df_slice)):
            sar = sar + af * (ep - sar)
            if trend == 1:
                if df_slice['low'].iloc[i] < sar:
                    trend = -1
                    sar = ep
                    ep = float(df_slice['low'].iloc[i])
                    af = 0.02
                else:
                    if float(df_slice['high'].iloc[i]) > ep:
                        ep = float(df_slice['high'].iloc[i])
                        af = min(af + 0.02, max_af)
            else:
                if float(df_slice['high'].iloc[i]) > sar:
                    trend = 1
                    sar = ep
                    ep = float(df_slice['high'].iloc[i])
                    af = 0.02
                else:
                    if float(df_slice['low'].iloc[i]) < ep:
                        ep = float(df_slice['low'].iloc[i])
                        af = min(af + 0.02, max_af)
            directions.append(trend)

        if len(directions) < 2:
            return False, None, "Not enough data"

        current_trend = directions[-1]
        prev_trend = directions[-2]

        if current_trend == 1 and prev_trend == -1:
            return True, "LONG", "SAR flipped LONG"
        elif current_trend == -1 and prev_trend == 1:
            return True, "SHORT", "SAR flipped SHORT"
        return False, None, f"SAR trend {current_trend}"

    def _check_keltner_breakout_entry(self, symbol: str, row: pd.Series, df: pd.DataFrame, idx: int) -> tuple:
        df_slice = df.iloc[:idx+1].copy()
        df_slice['ema20'] = df_slice['close'].ewm(span=20).mean()
        df_slice['tr1'] = df_slice['high'] - df_slice['low']
        df_slice['tr2'] = abs(df_slice['high'] - df_slice['close'].shift(1))
        df_slice['tr3'] = abs(df_slice['low'] - df_slice['close'].shift(1))
        df_slice['tr'] = df_slice[['tr1', 'tr2', 'tr3']].max(axis=1)
        df_slice['atr'] = df_slice['tr'].rolling(14).mean()

        ema20 = float(df_slice['ema20'].iloc[-1])
        atr = float(df_slice['atr'].iloc[-1])
        price = float(row['close'])
        upper = ema20 + 2.0 * atr
        lower = ema20 - 2.0 * atr

        if price > upper:
            return True, "LONG", f"Keltner LONG {upper:.2f}"
        elif price < lower:
            return True, "SHORT", f"Keltner SHORT {lower:.2f}"
        return False, None, f"Price {price:.2f} in Keltner"

