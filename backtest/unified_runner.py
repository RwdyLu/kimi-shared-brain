"""
Unified Backtest Runner / 統一回測執行器

Backtesting engine that uses StrategyConditions for entry signals.
No hardcoded strategy_id → entry_method mapping needed.
Supports any strategy composed from the condition library.

統一回測引擎，使用 StrategyConditions 判斷進場訊號。
不需要為每個 strategy_id 硬編碼進場邏輯。
支援任何由條件庫組合而成的策略。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from backtest import (
    BacktestConfig, BacktestSummary, BacktestStorage,
    TradeRecord, TradeDirection, TradeResult
)
from backtest.runner import BacktestRunner
from data.fetcher import BinanceFetcher
from indicators import calculator as indicator_calc
from app.strategy_conditions import StrategyConditions, ConditionResult


class UnifiedBacktestRunner(BacktestRunner):
    """
    Unified backtest runner that evaluates strategies by their conditions.
    
    Instead of hardcoded _check_strategyX_entry() methods, this runner:
    1. Builds indicator data for each candle
    2. Feeds data to StrategyConditions
    3. Enters trade if ALL conditions pass
    
    統一回測執行器，依策略條件判斷進場。
    """

    def __init__(
        self,
        config: BacktestConfig,
        strategy_conditions: List[str],
        strategy_parameters: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(config)
        self.conditions = strategy_conditions
        self.parameters = strategy_parameters or {}
        self.condition_checker = StrategyConditions()
        self.signal_type = self.parameters.get("signal_type", "trend_long")

    def _check_entry_signals(
        self,
        symbol: str,
        timestamp: str,
        price: float,
        row: pd.Series,
        df: pd.DataFrame,
        idx: int,
    ) -> None:
        """
        Check entry using StrategyConditions / 使用策略條件檢查進場
        """
        # Build data dict for condition checker
        data = self._build_condition_data(symbol, row, df, idx)

        # Check conditions with N-of-M voting (looser than strict AND)
        results = self.condition_checker.check_all_conditions(
            self.conditions, data, self.parameters
        )

        # Use N-of-M for 3+ conditions, strict AND for 1-2
        min_passed = StrategyConditions.estimate_min_passed(len(self.conditions))
        passed = self.condition_checker.strategy_passed(results, min_passed=min_passed)

        if passed:
            passed_results = [r for r in results if r.passed]
            # Determine direction from signal_type
            direction = TradeDirection.LONG
            if "short" in self.signal_type.lower():
                direction = TradeDirection.SHORT

            # Build reason string from PASSED conditions only
            reasons = [f"{r.condition}: {r.message.split(':')[-1].strip()[:30]}" for r in passed_results]
            reason = " | ".join(reasons[:3])  # First 3 conditions

            trade = TradeRecord(
                trade_id=f"{self.backtest_id}_{symbol}_{len(self.closed_trades)}",
                symbol=symbol,
                direction=direction.value,
                entry_time=timestamp,
                entry_price=price,
                quantity=1.0,
                exit_reason=f"[unified] {reason[:100]}",
            )

            self.active_trades[symbol] = trade
            self.storage.save_trade(trade)

            print(f"   ➡️  ENTRY [{self.strategy_id}]: {direction.value.upper()} @ ${price:,.2f} ({timestamp})")
            for r in results:
                print(f"      ✅ {r.condition}: {r.message[:60]}")

    def _build_condition_data(
        self,
        symbol: str,
        row: pd.Series,
        df: pd.DataFrame,
        idx: int,
    ) -> Dict[str, Any]:
        """
        Build the data dict expected by StrategyConditions.
        Mirrors the fields used in strategy_conditions.py checkers.
        """
        data: Dict[str, Any] = {
            "price": float(row.get("close", 0)),
            "volume": float(row.get("volume", 0)),
        }

        # Moving averages
        for col in ["MA5", "MA20", "MA240"]:
            val = row.get(col)
            key = col.lower().replace("ma", "ma")
            data[key] = float(val) if val is not None else None

        # Previous MA values for cross detection
        if idx > 0:
            prev = df.iloc[idx - 1]
            for col in ["MA5", "MA20", "MA240"]:
                key = col.lower().replace("ma", "ma") + "_prev"
                val = prev.get(col)
                data[key] = float(val) if val is not None else None

        # Volume ratio
        vol_ma20 = row.get("volume_MA20")
        volume = row.get("volume")
        if volume is not None and vol_ma20 and vol_ma20 > 0:
            data["volume_ratio"] = float(volume) / float(vol_ma20)
        else:
            data["volume_ratio"] = 1.0

        # Candles for consecutive detection
        if idx >= 3:
            candles = []
            for i in range(max(0, idx - 3), idx + 1):
                r = df.iloc[i]
                candles.append({
                    "open": float(r.get("open", 0)),
                    "close": float(r.get("close", 0)),
                })
            data["candles"] = candles

        # Price history
        closes = df["close"].iloc[:idx + 1].tolist()
        highs = df["high"].iloc[:idx + 1].tolist()
        lows = df["low"].iloc[:idx + 1].tolist()
        volumes = df["volume"].iloc[:idx + 1].tolist()
        data["closes"] = [float(c) for c in closes if c is not None]
        data["highs"] = [float(h) for h in highs if h is not None]
        data["lows"] = [float(l) for l in lows if l is not None]
        data["volumes"] = [float(v) for v in volumes if v is not None]

        # RSI
        rsi = row.get("RSI")
        data["rsi"] = float(rsi) if rsi is not None else None
        if idx > 0:
            prev_rsi = df.iloc[idx - 1].get("RSI")
            data["rsi_prev"] = float(prev_rsi) if prev_rsi is not None else None

        # RSI history for divergence
        rsi_values = df["RSI"].iloc[:idx + 1].dropna().tolist()
        data["rsi_values"] = [float(r) for r in rsi_values]

        # EMA
        for col in ["EMA5", "EMA10", "EMA3", "EMA8"]:
            val = row.get(col)
            if val is not None:
                key = col.lower().replace("ema", "ema")
                data[key] = float(val)
                if idx > 0:
                    prev_val = df.iloc[idx - 1].get(col)
                    data[key + "_prev"] = float(prev_val) if prev_val is not None else None

        # EMA fast/slow aliases for composite strategies
        data["ema_fast"] = data.get("ema5") or data.get("ema3") or data.get("ma5")
        data["ema_slow"] = data.get("ema10") or data.get("ema8") or data.get("ema20") or data.get("ma20")
        if idx > 0:
            prev = df.iloc[idx - 1]
            data["ema_fast_prev"] = (
                float(prev.get("EMA5", prev.get("EMA3", prev.get("MA5", 0))))
                if any(prev.get(c) is not None for c in ["EMA5", "EMA3", "MA5"])
                else None
            )
            data["ema_slow_prev"] = (
                float(prev.get("EMA10", prev.get("EMA8", prev.get("MA20", 0))))
                if any(prev.get(c) is not None for c in ["EMA10", "EMA8", "MA20"])
                else None
            )

        # Stochastic
        stoch_k = row.get("STOCH_K")
        stoch_d = row.get("STOCH_D")
        data["stoch_fastk"] = float(stoch_k) if stoch_k is not None else None
        data["stoch_fastd"] = float(stoch_d) if stoch_d is not None else None
        if idx > 0:
            prev = df.iloc[idx - 1]
            prev_k = prev.get("STOCH_K")
            prev_d = prev.get("STOCH_D")
            data["stoch_fastk_prev"] = float(prev_k) if prev_k is not None else None
            data["stoch_fastd_prev"] = float(prev_d) if prev_d is not None else None

        # Bollinger Bands
        for col, key in [("BB_upper", "bb_upper"), ("BB_middle", "bb_middle"), ("BB_lower", "bb_lower")]:
            val = row.get(col)
            data[key] = float(val) if val is not None else None

        # TEMA
        tema = row.get("TEMA")
        data["tema"] = float(tema) if tema is not None else None
        if idx > 0:
            prev_tema = df.iloc[idx - 1].get("TEMA")
            data["tema_prev"] = float(prev_tema) if prev_tema is not None else None

        # SAR
        sar = row.get("SAR")
        data["sar"] = float(sar) if sar is not None else None

        # Hilbert Transform
        ht_sine = row.get("HT_SINE")
        ht_leadsine = row.get("HT_LEADSINE")
        data["ht_sine"] = float(ht_sine) if ht_sine is not None else None
        data["ht_leadsine"] = float(ht_leadsine) if ht_leadsine is not None else None
        if idx > 0:
            prev = df.iloc[idx - 1]
            data["ht_sine_prev"] = float(prev.get("HT_SINE")) if prev.get("HT_SINE") is not None else None
            data["ht_leadsine_prev"] = float(prev.get("HT_LEADSINE")) if prev.get("HT_LEADSINE") is not None else None

        # ADX proxy (using price range / ATR approximation)
        if idx >= 14:
            high_slice = df["high"].iloc[idx - 14:idx + 1]
            low_slice = df["low"].iloc[idx - 14:idx + 1]
            tr_values = (high_slice - low_slice).abs()
            atr = tr_values.mean()
            price_range = high_slice.max() - low_slice.min()
            if atr and atr > 0:
                data["adx14"] = float(price_range / (atr * 14) * 100)
            else:
                data["adx14"] = 25.0  # Default moderate
        else:
            data["adx14"] = 25.0

        # ATR
        if idx >= 14:
            high_slice = df["high"].iloc[idx - 14:idx + 1]
            low_slice = df["low"].iloc[idx - 14:idx + 1]
            tr_values = (high_slice - low_slice).abs()
            data["atr14"] = float(tr_values.mean())
            data["atr"] = data["atr14"]
        else:
            data["atr14"] = float(row.get("high", 0)) - float(row.get("low", 0)) if idx >= 0 else 0
            data["atr"] = data["atr14"]

        # Volume EMA
        if idx >= 19 and "volumes" in data:
            try:
                ema_list = indicator_calc.calculate_ema(data["volumes"], period=20)
                data["volume_ema20"] = float(ema_list[-1]) if ema_list else None
            except Exception:
                data["volume_ema20"] = None
        else:
            data["volume_ema20"] = None

        # CCI
        cci = row.get("CCI")
        data["cci"] = float(cci) if cci is not None else None

        # ROC
        roc = row.get("ROC")
        data["roc"] = float(roc) if roc is not None else None

        # Price channel upper
        pc_upper = row.get("PC_upper")
        data["pc_upper"] = float(pc_upper) if pc_upper is not None else None

        # Williams %R proxy (from Stochastic)
        if stoch_k is not None:
            data["williams_r"] = float(stoch_k) - 100

        return data

    def _check_strategy_specific_exit(
        self,
        symbol: str,
        trade: TradeRecord,
        row: pd.Series,
        df: pd.DataFrame,
        idx: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Unified strategy-specific exit using conditions.
        For now, fall back to default SL/TP only.
        """
        # Default: no strategy-specific exit, rely on SL/TP
        return False, None


def run_unified_backtest(
    strategy_config: Dict[str, Any],
    symbols: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 10000.0,
    stop_loss_pct: Optional[float] = 5.0,
    take_profit_pct: Optional[float] = 10.0,
    commission_pct: float = 0.0,
    daily_loss_limit: float = -0.02,
    daily_profit_target: float = 0.015,
) -> BacktestSummary:
    """
    Convenience function to run a unified backtest from a strategy config dict.

    Args:
        strategy_config: Dict with 'id', 'conditions', 'parameters', 'signal_type', etc.
        symbols: List of symbols (default: from config or ["BTCUSDT"])
        start_date, end_date: Date range
        initial_capital, stop_loss_pct, take_profit_pct: Risk parameters

    Returns:
        BacktestSummary
    """
    config_symbols = strategy_config.get("symbols", symbols or ["BTCUSDT"])
    config = BacktestConfig(
        symbols=config_symbols[:1] if len(config_symbols) > 1 else config_symbols,  # Test 1 symbol for speed
        start_date=start_date or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        end_date=end_date or datetime.now().strftime("%Y-%m-%d"),
        strategy_id=strategy_config.get("id", "unified"),
        strategy_type=strategy_config.get("type", "unified"),
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        commission_pct=commission_pct,
        daily_loss_limit=daily_loss_limit,
        daily_profit_target=daily_profit_target,
    )

    runner = UnifiedBacktestRunner(
        config=config,
        strategy_conditions=strategy_config.get("conditions", []),
        strategy_parameters=strategy_config.get("parameters", {}),
    )

    return runner.run()
