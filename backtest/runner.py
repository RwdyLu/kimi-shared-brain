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
                self._check_exit_conditions(symbol, timestamp, current_price, row)

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

        # TEMA (for hilbert_cycle, rsi_trend)
        tema_values = indicator_calc.calculate_tema(closes, period=9)
        df['TEMA'] = [None] * (len(df) - len(tema_values)) + tema_values if tema_values else [None] * len(df)

        # Bollinger Bands (for bb_mean_reversion, rsi_trend)
        bb = indicator_calc.calculate_bollinger_bands(closes, period=20, std_dev=2.0)
        bb_upper = bb.get('upper', [])
        bb_middle = bb.get('middle', [])
        bb_lower = bb.get('lower', [])
        df['BB_upper'] = [None] * (len(df) - len(bb_upper)) + bb_upper if bb_upper else [None] * len(df)
        df['BB_middle'] = [None] * (len(df) - len(bb_middle)) + bb_middle if bb_middle else [None] * len(df)
        df['BB_lower'] = [None] * (len(df) - len(bb_lower)) + bb_lower if bb_lower else [None] * len(df)

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
        elif strategy_id in ("contrarian_watch_overheated", "contrarian_watch_oversold"):
            # Contrarian watch strategies: log the signal but do NOT enter trades
            # They are WATCH-ONLY in the strategy config
            self._check_contrarian_watch(symbol, row, df, idx, strategy_id)
            return
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

    def _check_exit_conditions(self, symbol: str, timestamp: str, price: float, row: pd.Series) -> None:
        """
        Check for exit conditions and close trades
        檢查出場條件並平倉
        """
        trade = self.active_trades[symbol]

        exit_triggered = False
        exit_price = price
        exit_reason = "signal"

        # Check stop loss
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

        # Check take profit
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

        # Check reverse signal / exit signal
        if not exit_triggered:
            indicators = {
                'MA5': row.get('MA5'),
                'MA20': row.get('MA20'),
                'MA240': row.get('MA240'),
                'position_side': trade.direction,
                'symbol': symbol,
                'backtest_mode': True,
            }
            exit_signals = self.signal_engine.generate_exit_signals(indicators)
            
            if exit_signals:
                exit_triggered = True
                exit_reason = "exit_signal"

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

        # Calculate P&L
        if trade.direction == "long":
            trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
        else:  # short
            trade.pnl_pct = ((trade.entry_price - exit_price) / trade.entry_price) * 100

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

        print(f"   {emoji} EXIT: ${exit_price:,.2f} | P&L: {trade.pnl_pct:+.2f}% ({reason})")

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
            strategy=self.config.strategy,
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

    def build_equity_chart(self, summary: Optional[BacktestSummary] = None) -> Optional[go.Figure]:
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

    def save_equity_chart(self, fig: go.Figure, filename: Optional[str] = None) -> str:
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


def run_backtest(
    symbols: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 10000.0,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    strategy_id: Optional[str] = None,
    strategy_type: Optional[str] = None,
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
