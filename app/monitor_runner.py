"""
Monitoring Runner
監測執行器

BTC/ETH Monitoring System - Application Layer
BTC/ETH 監測系統 - 應用層

This module provides a single-run entry point for the monitoring system.
Connects Data → Indicator → Signal → Notification layers.

本模組提供監測系統的單次執行入口。
串接資料 → 指標 → 訊號 → 通知層。

⚠️  IMPORTANT / 重要  ⚠️
This runner generates ALERTS ONLY. No automatic trading is performed.
本執行器僅產生提醒，不執行自動交易。

This is SINGLE-RUN ONLY (not a daemon).
這僅為單次執行（非常駐服務）。

Author: kimiclaw_bot
Version: 1.3.0
Date: 2026-04-14
"""

import sys
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.insert(0, "/tmp/kimi-shared-brain")

# Layer imports / 層級匯入
from data.fetcher import create_fetcher, BinanceFetcher, KlineData
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240, analyze_volume
from signals.engine import SignalEngine, Signal, SignalType, SignalLevel, CooldownManager
from notifications.formatter import NotificationFormatter
from notifications.notifier import Notifier, NotifierConfig, OutputChannel

# Import config loader / 匯入配置載入器
from config.loader import get_enabled_symbols, get_monitoring_params, get_indicator_params

# Import strategy executor / 匯入策略執行器
from app.strategy_executor import StrategyExecutor, StrategySignal


# Default configuration (will be overridden by config files)
# 預設配置（將被配置文件覆蓋）
def get_monitor_symbols() -> List[str]:
    """Get list of symbols to monitor from config / 從配置取得監測標的列表"""
    try:
        return get_enabled_symbols()
    except Exception:
        return ["BTCUSDT", "ETHUSDT"]


def get_timeframes() -> Dict[str, Dict[str, Any]]:
    """Get timeframe configuration from config / 從配置取得時間框架設定"""
    try:
        params = get_monitoring_params()
        data_config = params.get("data", {})
        timeframes = data_config.get("timeframes", ["1m", "5m", "15m"])

        # Build timeframe config
        result = {}
        limits = {"1m": 20, "5m": 250, "15m": 10, "1h": 100, "4h": 50, "1d": 30}
        descriptions = {
            "1m": "Volume analysis",
            "5m": "Primary trend analysis",
            "15m": "Contrarian pattern analysis",
            "1h": "Hourly trend",
            "4h": "4H trend (for research)",
            "1d": "Daily trend",
        }

        for tf in timeframes:
            result[tf] = {"limit": limits.get(tf, 100), "description": descriptions.get(tf, f"{tf} analysis")}
        return result
    except Exception:
        # Fallback defaults
        return {
            "5m": {"limit": 250, "description": "Primary trend analysis"},
            "1m": {"limit": 20, "description": "Volume analysis"},
            "15m": {"limit": 10, "description": "Contrarian pattern analysis"},
        }


# Legacy constants for backward compatibility
# 舊常數保持向後相容
MONITOR_SYMBOLS = get_monitor_symbols()
TIMEFRAMES = get_timeframes()


@dataclass
class SymbolResult:
    """
    Result for a single symbol / 單一標的結果

    Contains all data, indicators, signals and notifications for one symbol.
    包含單一標的所有資料、指標、訊號與通知。
    """

    symbol: str
    timestamp: int
    success: bool
    error: Optional[str] = None

    # Data / 資料
    data_5m: List[KlineData] = None
    data_1m: List[KlineData] = None
    data_15m: List[KlineData] = None

    # Indicators / 指標
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma240: Optional[float] = None
    volume_avg: Optional[float] = None
    volume_ratio: Optional[float] = None
    current_price: Optional[float] = None  # Current price from latest candle / 最新K線的當前價格

    # Signals / 訊號
    signals: List[Signal] = None
    confirmed_signals: List[Signal] = None
    watch_only_signals: List[Signal] = None

    def __post_init__(self):
        if self.signals is None:
            self.signals = []
        if self.confirmed_signals is None:
            self.confirmed_signals = []
        if self.watch_only_signals is None:
            self.watch_only_signals = []


@dataclass
class RunSummary:
    """
    Summary of a monitoring run / 監測執行摘要

    Contains aggregated results from all symbols.
    包含所有標的的彙總結果。
    """

    timestamp: int
    total_symbols: int
    successful_symbols: int
    failed_symbols: int
    total_signals: int
    confirmed_count: int
    watch_only_count: int
    symbols_with_signals: List[str] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.symbols_with_signals is None:
            self.symbols_with_signals = []
        if self.errors is None:
            self.errors = []


class MonitorRunner:
    """
    Monitoring system runner / 監測系統執行器

    Provides single-run monitoring for BTC/ETH.
    Connects all four layers: Data → Indicator → Signal → Notification

    ⚠️  SINGLE-RUN ONLY (not a daemon)
    ⚠️  ALERT ONLY (no auto trading)
    """

    def __init__(
        self,
        fetcher: Optional[BinanceFetcher] = None,
        signal_engine: Optional[SignalEngine] = None,
        notifier: Optional[Notifier] = None,
    ):
        """
        Initialize runner / 初始化執行器

        Args:
            fetcher: Data fetcher instance / 資料抓取器實例
            signal_engine: Signal engine instance / 訊號引擎實例
            notifier: Notifier instance / 通知器實例
        """
        self.fetcher = fetcher or create_fetcher()
        self.signal_engine = signal_engine or SignalEngine()
        self.notifier = notifier or self._create_default_notifier()
        self.formatter = NotificationFormatter(language="en")
        
        # Initialize strategy executor / 初始化策略執行器
        self.strategy_executor = StrategyExecutor()

    def _create_default_notifier(self) -> Notifier:
        """Create default notifier / 建立預設通知器"""
        config = NotifierConfig(output_channel=OutputChannel.CONSOLE, language="en")
        return Notifier(config)

    def _save_indicator_snapshot(self, result: SymbolResult, run_id: Optional[int] = None) -> None:
        """
        Save indicator snapshot to JSONL file / 儲存指標快照到 JSONL 檔案

        T-052-B: Store indicator values after each run for UI display
        """
        try:
            from config.paths import LOGS_DIR
            import json
            from pathlib import Path

            # Build snapshot data / 建立快照資料
            snapshot = {
                "run_id": f"#{run_id}" if run_id else f"#{int(time.time())}",
                "timestamp": datetime.fromtimestamp(result.timestamp / 1000).isoformat(),
                "symbol": result.symbol,
                "price": result.current_price,
                "ma5": result.ma5,
                "ma20": result.ma20,
                "ma240": result.ma240,
                "volume_ratio": result.volume_ratio,
            }

            # Calculate price vs MA percentages / 計算價格與 MA 的百分比
            if result.current_price and result.ma5:
                snapshot["price_vs_ma5_pct"] = round((result.current_price - result.ma5) / result.ma5 * 100, 2)
            else:
                snapshot["price_vs_ma5_pct"] = None

            if result.current_price and result.ma20:
                snapshot["price_vs_ma20_pct"] = round((result.current_price - result.ma20) / result.ma20 * 100, 2)
            else:
                snapshot["price_vs_ma20_pct"] = None

            if result.current_price and result.ma240:
                snapshot["price_vs_ma240_pct"] = round((result.current_price - result.ma240) / result.ma240 * 100, 2)
            else:
                snapshot["price_vs_ma240_pct"] = None

            # Add signals info / 添加訊號資訊
            snapshot["signals_count"] = len(result.signals) if result.signals else 0
            snapshot["signal_types"] = [s.signal_type.name for s in result.signals] if result.signals else []

            # Append to JSONL file / 附加到 JSONL 檔案
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"

            with open(snapshot_file, "a") as f:
                f.write(json.dumps(snapshot) + "\n")

        except Exception as e:
            # Silent fail - don't break monitoring if snapshot fails / 靜默失敗
            print(f"    ⚠️  Snapshot save skipped: {e}")

    def _fetch_data(self, symbol: str) -> Tuple[List[KlineData], List[KlineData], List[KlineData], Optional[str]]:
        """
        Fetch data for all timeframes / 抓取所有時間框架的資料

        Args:
            symbol: Trading pair / 交易對

        Returns:
            Tuple of (data_5m, data_1m, data_15m, error)
            (5m 資料, 1m 資料, 15m 資料, 錯誤訊息)
        """
        error = None
        data_5m, data_1m, data_15m = [], [], []

        try:
            # Fetch 5m data (for trend analysis) / 抓取 5m 資料（趨勢分析）
            raw_5m = self.fetcher.fetch_klines(symbol=symbol, interval="5m", limit=TIMEFRAMES["5m"]["limit"])
            data_5m = self.fetcher.normalize_kline_data(raw_5m)

            # Fetch 1m data (for volume analysis) / 抓取 1m 資料（成交量分析）
            raw_1m = self.fetcher.fetch_klines(symbol=symbol, interval="1m", limit=TIMEFRAMES["1m"]["limit"])
            data_1m = self.fetcher.normalize_kline_data(raw_1m)

            # Fetch 15m data (for contrarian patterns) / 抓取 15m 資料（逆勢型態）
            raw_15m = self.fetcher.fetch_klines(symbol=symbol, interval="15m", limit=TIMEFRAMES["15m"]["limit"])
            data_15m = self.fetcher.normalize_kline_data(raw_15m)

        except Exception as e:
            error = f"Failed to fetch data for {symbol}: {str(e)}"

        return data_5m, data_1m, data_15m, error

    def _calculate_indicators(self, data_5m: List[KlineData], data_1m: List[KlineData]) -> Dict[str, Any]:
        """
        Calculate indicators / 計算指標

        Args:
            data_5m: 5m kline data / 5m K 線資料
            data_1m: 1m kline data / 1m K 線資料

        Returns:
            Dictionary of indicator values / 指標值的字典
        """
        result = {"ma5": None, "ma20": None, "ma240": None, "volume_avg": None, "volume_ratio": None}

        if not data_5m or not data_1m:
            return result

        # Calculate MAs from 5m closes / 從 5m 收盤價計算 MA
        closes_5m = [k.close for k in data_5m]
        highs_5m = [k.high for k in data_5m]
        lows_5m = [k.low for k in data_5m]

        if len(closes_5m) >= 5:
            ma5_list = calculate_ma5(closes_5m)
            if ma5_list:
                result["ma5"] = ma5_list[-1]

        if len(closes_5m) >= 20:
            ma20_list = calculate_ma20(closes_5m)
            if ma20_list:
                result["ma20"] = ma20_list[-1]

        if len(closes_5m) >= 240:
            ma240_list = calculate_ma240(closes_5m)
            if ma240_list:
                result["ma240"] = ma240_list[-1]

        # Calculate volume metrics from 1m / 從 1m 計算成交量指標
        volumes_1m = [k.volume for k in data_1m]

        if volumes_1m:
            current_volume = volumes_1m[-1]
            vol_analysis = analyze_volume(
                current_volume=current_volume, volumes=volumes_1m, period=min(20, len(volumes_1m)), threshold=2.0
            )
            result["volume_avg"] = vol_analysis.avg_volume
            result["volume_ratio"] = vol_analysis.ratio

        # Calculate P2 strategy indicators / 計算 P2 策略指標
        from indicators.calculator import (
            calculate_rsi, calculate_tema, calculate_stochastic,
            calculate_bollinger_bands, calculate_sar, calculate_ht_sine
        )

        # RSI
        if len(closes_5m) >= 15:
            rsi_list = calculate_rsi(closes_5m, period=14)
            if rsi_list:
                result["rsi"] = rsi_list[-1]
                if len(rsi_list) >= 2:
                    result["rsi_prev"] = rsi_list[-2]

        # TEMA
        if len(closes_5m) >= 27:
            tema_list = calculate_tema(closes_5m, period=9)
            if tema_list:
                result["tema"] = tema_list[-1]
                if len(tema_list) >= 2:
                    result["tema_prev"] = tema_list[-2]

        # Stochastic
        if len(closes_5m) >= 8:
            fastk_list, fastd_list = calculate_stochastic(
                closes_5m, highs_5m, lows_5m, k_period=5, d_period=3
            )
            if fastk_list and fastd_list:
                result["stoch_fastk"] = fastk_list[-1]
                result["stoch_fastd"] = fastd_list[-1]
                if len(fastk_list) >= 2 and len(fastd_list) >= 2:
                    result["stoch_fastk_prev"] = fastk_list[-2]
                    result["stoch_fastd_prev"] = fastd_list[-2]

        # Bollinger Bands
        if len(closes_5m) >= 20:
            bb = calculate_bollinger_bands(closes_5m, period=20, std_dev=2.0)
            if bb["middle"]:
                result["bb_upper"] = bb["upper"][-1]
                result["bb_middle"] = bb["middle"][-1]
                result["bb_lower"] = bb["lower"][-1]

        # SAR
        if len(highs_5m) >= 2 and len(lows_5m) >= 2:
            sar_list = calculate_sar(highs_5m, lows_5m, acceleration=0.02, maximum=0.2)
            if sar_list:
                result["sar"] = sar_list[-1]

        # Hilbert Sine
        if len(closes_5m) >= 20:
            ht = calculate_ht_sine(closes_5m)
            if ht["sine"]:
                result["ht_sine"] = ht["sine"][-1]
                result["ht_leadsine"] = ht["leadsine"][-1]
                if len(ht["sine"]) >= 2 and len(ht["leadsine"]) >= 2:
                    result["ht_sine_prev"] = ht["sine"][-2]
                    result["ht_leadsine_prev"] = ht["leadsine"][-2]

        return result

    def run_for_symbol(self, symbol: str) -> SymbolResult:
        """
        Run monitoring for a single symbol / 執行單一標的監測

        Args:
            symbol: Trading pair to monitor / 要監測的交易對

        Returns:
            SymbolResult with all data / 包含所有資料的 SymbolResult
        """
        timestamp = int(time.time() * 1000)

        print(f"\n{'=' * 60}")
        print(f"Monitoring {symbol}...")
        print(f"{'=' * 60}")

        # Step 1: Fetch Data / 步驟 1：抓取資料
        print(f"[1/4] Fetching data...")
        data_5m, data_1m, data_15m, error = self._fetch_data(symbol)

        if error:
            print(f"❌ Error: {error}")
            return SymbolResult(symbol=symbol, timestamp=timestamp, success=False, error=error)

        print(f"    ✓ 5m: {len(data_5m)} candles")
        print(f"    ✓ 1m: {len(data_1m)} candles")
        print(f"    ✓ 15m: {len(data_15m)} candles")

        # Step 2: Calculate Indicators / 步驟 2：計算指標
        print(f"[2/4] Calculating indicators...")
        indicators = self._calculate_indicators(data_5m, data_1m)

        # Get current price from latest 5m candle / 從最新 5m K 線取得當前價格
        current_price = data_5m[-1].close if data_5m else None
        if current_price:
            print(f"    💰 Current Price: ${current_price:,.2f}")

        print(f"    ✓ MA5: {indicators['ma5']:.2f}" if indicators["ma5"] else "    - MA5: N/A")
        print(f"    ✓ MA20: {indicators['ma20']:.2f}" if indicators["ma20"] else "    - MA20: N/A")
        print(f"    ✓ MA240: {indicators['ma240']:.2f}" if indicators["ma240"] else "    - MA240: N/A")
        print(
            f"    ✓ Volume Ratio: {indicators['volume_ratio']:.2f}x"
            if indicators["volume_ratio"]
            else "    - Volume: N/A"
        )

        # Step 3: Generate Signals / 步驟 3：產生訊號
        print(f"[3/4] Generating signals...")
        signals = self.signal_engine.process_symbol(symbol, data_5m, data_1m, data_15m)
        
        # Step 3b: Execute Strategies / 步驟 3b：執行策略
        print(f"[3b/4] Executing strategies...")
        
        # Prepare market data for strategy executor
        market_data = {
            "price": current_price,
            "ma5": indicators.get("ma5"),
            "ma20": indicators.get("ma20"),
            "ma240": indicators.get("ma240"),
            "volume_ratio": indicators.get("volume_ratio"),
            "candles": [{"open": k.open, "high": k.high, "low": k.low, "close": k.close, "volume": k.volume} for k in data_5m] if data_5m else [],
            "closes": [k.close for k in data_5m] if data_5m else [],
            # P2 indicators
            "rsi": indicators.get("rsi"),
            "rsi_prev": indicators.get("rsi_prev"),
            "tema": indicators.get("tema"),
            "tema_prev": indicators.get("tema_prev"),
            "stoch_fastk": indicators.get("stoch_fastk"),
            "stoch_fastd": indicators.get("stoch_fastd"),
            "stoch_fastk_prev": indicators.get("stoch_fastk_prev"),
            "stoch_fastd_prev": indicators.get("stoch_fastd_prev"),
            "bb_upper": indicators.get("bb_upper"),
            "bb_middle": indicators.get("bb_middle"),
            "bb_lower": indicators.get("bb_lower"),
            "sar": indicators.get("sar"),
            "ht_sine": indicators.get("ht_sine"),
            "ht_leadsine": indicators.get("ht_leadsine"),
            "ht_sine_prev": indicators.get("ht_sine_prev"),
            "ht_leadsine_prev": indicators.get("ht_leadsine_prev"),
        }
        
        # Add previous MA values for crossover detection
        if len(data_5m) >= 2:
            prev_closes = [k.close for k in data_5m[:-1]]
            if len(prev_closes) >= 5:
                from indicators.calculator import calculate_ma5
                ma5_prev_list = calculate_ma5(prev_closes)
                if ma5_prev_list:
                    market_data["ma5_prev"] = ma5_prev_list[-1]
            if len(prev_closes) >= 20:
                from indicators.calculator import calculate_ma20
                ma20_prev_list = calculate_ma20(prev_closes)
                if ma20_prev_list:
                    market_data["ma20_prev"] = ma20_prev_list[-1]
        
        # Execute strategies
        strategy_signals = self.strategy_executor.execute_for_symbol(symbol, market_data)
        
        # Convert StrategySignal to Signal
        for strat_sig in strategy_signals:
            signal = Signal(
                symbol=symbol,
                signal_type=strat_sig.signal_type,
                level=strat_sig.level,
                reason=strat_sig.reason,
                warning=strat_sig.warning,
                timestamp=timestamp,
                price_data={"close": current_price, "ma5": indicators.get("ma5"), "ma20": indicators.get("ma20"), "ma240": indicators.get("ma240")},
                conditions={},
                metadata={
                    "strategy_id": strat_sig.strategy_id,
                    "strategy_name": strat_sig.strategy_name,
                    "strategy_type": strat_sig.strategy_type,
                    "conditions_passed": strat_sig.conditions_passed,
                    "conditions_total": strat_sig.conditions_total,
                    "details": strat_sig.details,
                }
            )
            signals.append(signal)
        
        confirmed = [s for s in signals if s.level == SignalLevel.CONFIRMED]
        watch_only = [s for s in signals if s.level == SignalLevel.WATCH_ONLY]

        print(f"    ✓ Total signals: {len(signals)}")
        print(f"    ✓ Confirmed: {len(confirmed)}")
        print(f"    ✓ Watch Only: {len(watch_only)}")
        
        # Show strategy signals
        if strategy_signals:
            print(f"    ✓ Strategy signals: {len(strategy_signals)}")
            for sig in strategy_signals:
                level_icon = "✅" if sig.level == SignalLevel.CONFIRMED else "👁️"
                print(f"      {level_icon} {sig.strategy_name}: {sig.reason[:80]}...")
        else:
            print(f"    - No strategy signals triggered")
            
        # Show strategy evaluation details (for debugging)
        print(f"    📋 Strategy evaluation:")
        for strategy in self.strategy_executor.enabled_strategies:
            strat_id = strategy['id']
            strat_name = strategy['name']
            conditions = strategy.get('conditions', [])
            
            # Check conditions
            from app.strategy_conditions import StrategyConditions
            checker = StrategyConditions()
            results = checker.check_all_conditions(conditions, market_data, strategy.get('parameters', {}))
            
            passed = sum(1 for r in results if r.result.value == 'passed')
            failed = sum(1 for r in results if r.result.value == 'failed')
            missing = sum(1 for r in results if r.result.value == 'missing_data')
            
            status_icon = "✅" if passed == len(conditions) and len(conditions) > 0 else "❌"
            print(f"      {status_icon} {strat_name}: {passed}/{len(conditions)} passed, {failed} failed, {missing} missing")

        # Step 4: Output Notifications / 步驟 4：輸出通知
        print(f"[4/4] Outputting notifications...")
        if signals:
            for signal in signals:
                self.notifier.notify(signal)
        else:
            print(f"    - No signals to notify")

        # Build result / 建立結果
        result = SymbolResult(
            symbol=symbol,
            timestamp=timestamp,
            success=True,
            data_5m=data_5m,
            data_1m=data_1m,
            data_15m=data_15m,
            ma5=indicators.get("ma5"),
            ma20=indicators.get("ma20"),
            ma240=indicators.get("ma240"),
            volume_avg=indicators.get("volume_avg"),
            volume_ratio=indicators.get("volume_ratio"),
            current_price=current_price,  # Add current price / 添加當前價格
            signals=signals,
            confirmed_signals=confirmed,
            watch_only_signals=watch_only,
        )

        # Save indicator snapshot / 儲存指標快照 (T-052-B)
        self._save_indicator_snapshot(result, run_id=None)

        print(f"✓ {symbol} monitoring complete")

        return result

    def run_monitor_once(self) -> Tuple[List[SymbolResult], RunSummary]:
        """
        Run monitoring once for all symbols / 執行所有標的的一次監測

        Returns:
            Tuple of (list of SymbolResult, RunSummary)
            (SymbolResult 列表, RunSummary)
        """
        print("\n" + "=" * 70)
        print("BTC/ETH Monitoring System - Single Run")
        print("BTC/ETH 監測系統 - 單次執行")
        print("=" * 70)
        print(f"⚠️  ALERT ONLY - NO AUTO TRADING / 僅提醒 - 無自動交易")
        print(f"⏱️  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📊 Symbols: {', '.join(MONITOR_SYMBOLS)}")
        print("=" * 70)

        results = []
        errors = []

        # Run for each symbol / 為每個標的執行
        for symbol in MONITOR_SYMBOLS:
            result = self.run_for_symbol(symbol)
            results.append(result)

            if not result.success:
                errors.append(f"{symbol}: {result.error}")

        # Build summary / 建立摘要
        summary = self._build_run_summary(results)
        summary.errors = errors

        # Generate live strategy ranking / 產生即時策略排行
        try:
            from scripts.live_strategy_ranking import generate_live_ranking
            ranking = generate_live_ranking()
            print(f"\n📊 Live strategy ranking generated: {ranking['total_strategies']} strategies x {ranking['total_symbols']} symbols")
        except Exception as e:
            print(f"\n⚠️ Live strategy ranking failed: {e}")

        # Display current prices for all symbols / 顯示所有標的的當前價格
        print("\n" + "-" * 70)
        print("CURRENT PRICES / 當前價格")
        print("-" * 70)
        for result in results:
            if result.success and result.current_price:
                print(f"  {result.symbol}: ${result.current_price:,.2f}")
            else:
                print(f"  {result.symbol}: N/A")

        # Output summary / 輸出摘要
        self._output_summary(summary)

        return results, summary

    def _build_run_summary(self, results: List[SymbolResult]) -> RunSummary:
        """
        Build run summary from results / 從結果建立執行摘要

        Args:
            results: List of SymbolResult / SymbolResult 列表

        Returns:
            RunSummary / 執行摘要
        """
        timestamp = int(time.time() * 1000)

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        total_signals = sum(len(r.signals) for r in results)
        confirmed_count = sum(len(r.confirmed_signals) for r in results)
        watch_only_count = sum(len(r.watch_only_signals) for r in results)

        symbols_with_signals = [r.symbol for r in results if r.signals]

        return RunSummary(
            timestamp=timestamp,
            total_symbols=len(results),
            successful_symbols=len(successful),
            failed_symbols=len(failed),
            total_signals=total_signals,
            confirmed_count=confirmed_count,
            watch_only_count=watch_only_count,
            symbols_with_signals=symbols_with_signals,
        )

    def _output_summary(self, summary: RunSummary) -> None:
        """
        Output run summary / 輸出執行摘要

        Args:
            summary: RunSummary to output / 要輸出的執行摘要
        """
        print("\n" + "=" * 70)
        print("RUN SUMMARY / 執行摘要")
        print("=" * 70)
        print(f"Timestamp: {datetime.fromtimestamp(summary.timestamp / 1000)}")
        print(f"Total Symbols: {summary.total_symbols}")
        print(f"  ✓ Successful: {summary.successful_symbols}")
        print(f"  ✗ Failed: {summary.failed_symbols}")
        print(f"\nSignals Generated / 產生的訊號:")
        print(f"  Total: {summary.total_signals}")
        print(f"  ✅ Confirmed: {summary.confirmed_count}")
        print(f"  👁️  Watch Only: {summary.watch_only_count}")

        if summary.symbols_with_signals:
            print(f"\nSymbols with Signals / 有訊號的標的:")
            for symbol in summary.symbols_with_signals:
                print(f"  - {symbol}")

        if summary.errors:
            print(f"\nErrors / 錯誤:")
            for error in summary.errors:
                print(f"  ✗ {error}")

        print("=" * 70)
        print("⚠️  REMINDER / 提醒:")
        print("   All signals are ALERT ONLY.")

    def preview_run_output(self, results: List[SymbolResult]) -> str:
        """
        Generate preview of run output / 產生執行輸出預覽

        Args:
            results: List of SymbolResult / SymbolResult 列表

        Returns:
            Formatted preview string / 格式化的預覽字串
        """
        lines = []
        lines.append("=" * 70)
        lines.append("MONITOR RUN OUTPUT PREVIEW / 監測執行輸出預覽")
        lines.append("=" * 70)
        lines.append("")

        for result in results:
            lines.append(f"Symbol: {result.symbol}")
            lines.append(f"  Success: {result.success}")

            if not result.success:
                lines.append(f"  Error: {result.error}")
                lines.append("")
                continue

            # Indicators / 指標
            lines.append(f"  Indicators / 指標:")
            if result.ma5:
                lines.append(f"    MA5: {result.ma5:.2f}")
            if result.ma20:
                lines.append(f"    MA20: {result.ma20:.2f}")
            if result.ma240:
                lines.append(f"    MA240: {result.ma240:.2f}")
            if result.volume_ratio:
                lines.append(f"    Volume Ratio: {result.volume_ratio:.2f}x")

            # Signals / 訊號
            lines.append(f"  Signals / 訊號 ({len(result.signals)} total):")
            for signal in result.signals:
                level_icon = "✅" if signal.level == SignalLevel.CONFIRMED else "👁️"
                lines.append(f"    {level_icon} {signal.signal_type.value}")
                lines.append(f"       {signal.reason}")
                lines.append(f"       ⚠️  {signal.warning}")

            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)


def build_run_summary(results: List[SymbolResult]) -> RunSummary:
    """
    Build run summary from results (standalone function) / 從結果建立執行摘要（獨立函式）

    Args:
        results: List of SymbolResult / SymbolResult 列表

    Returns:
        RunSummary / 執行摘要
    """
    runner = MonitorRunner()
    return runner._build_run_summary(results)


def preview_run_output(results: List[SymbolResult]) -> str:
    """
    Generate preview of run output (standalone function) / 產生執行輸出預覽（獨立函式）

    Args:
        results: List of SymbolResult / SymbolResult 列表

    Returns:
        Formatted preview string / 格式化的預覽字串
    """
    runner = MonitorRunner()
    return runner.preview_run_output(results)


# Example usage / 使用範例
if __name__ == "__main__":
    print("Monitoring Runner")
    print("監測執行器")
    print("=" * 40)

    print("\n⚠️  SINGLE-RUN ONLY / 僅單次執行")
    print("⚠️  ALERT ONLY / 僅提醒")
    print("⚠️  NO AUTO TRADING / 無自動交易")

    print("\nUsage / 使用方法:")
    print("  from app.monitor_runner import MonitorRunner")
    print("  runner = MonitorRunner()")
    print("  results, summary = runner.run_monitor_once()")

    print("\nOr run directly / 或直接執行:")
    print("  python3 app/monitor_runner.py")

    print("\n" + "=" * 40)
    print("To run monitoring now / 立即執行監測:")
    print("  runner = MonitorRunner()")
    print("  results, summary = runner.run_monitor_once()")
