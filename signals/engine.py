"""
Signal Engine Module
訊號引擎模組

BTC/ETH Monitoring System - Signal Layer
BTC/ETH 監測系統 - 訊號層

This module provides signal generation and cooldown management for the monitoring system.
Generates trend_long, trend_short, and contrarian_watch signals based on indicator analysis.

本模組提供訊號產生與冷卻管理。
根據指標分析產生 trend_long、trend_short 與 contrarian_watch 訊號。

⚠️  IMPORTANT / 重要  ⚠️
This module generates ALERTS ONLY. No automatic trading is performed.
本模組僅產生提醒，不執行自動交易。

contrarian_watch signals are for OBSERVATION ONLY, not execution.
contrarian_watch 訊號僅供觀察，非執行訊號。

Author: kimiclaw_bot
Version: 1.1.0
Date: 2026-04-07
"""

import time
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# Import from other layers / 從其他層級匯入
import sys
sys.path.insert(0, '/tmp/kimi-shared-brain')

from data.fetcher import BinanceFetcher, KlineData, create_fetcher
from indicators.calculator import (
    calculate_ma5,
    calculate_ma20,
    calculate_ma240,
    analyze_volume,
    detect_ma_cross,
    CrossType,
    detect_four_consecutive_red,
    detect_four_consecutive_green,
    MACrossResult,
    VolumeAnalysisResult,
    CandlePatternResult
)

# Import config loader / 匯入配置載入器
from config.loader import get_signal_params, get_cooldown_minutes, get_enabled_symbols


class SignalType(Enum):
    """Signal types / 訊號類型"""
    TREND_LONG = "trend_long"
    TREND_SHORT = "trend_short"
    CONTRARIAN_WATCH_OVERHEATED = "contrarian_watch_overheated"
    CONTRARIAN_WATCH_OVERSOLD = "contrarian_watch_oversold"


class SignalLevel(Enum):
    """Signal confirmation levels / 訊號確認層級"""
    CONFIRMED = "confirmed"      # trend_long, trend_short
    WATCH_ONLY = "watch_only"    # contrarian_watch


@dataclass
class Signal:
    """
    Signal data structure / 訊號資料結構
    
    Represents a generated signal with all relevant metadata.
    表示一個產生的訊號及其所有相關元資料。
    """
    signal_type: SignalType
    level: SignalLevel
    symbol: str
    timestamp: int
    price_data: Dict[str, Any]
    conditions: Dict[str, bool]
    reason: str
    warning: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary / 將訊號轉換為字典"""
        return {
            "signal_type": self.signal_type.value,
            "level": self.level.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "price_data": self.price_data,
            "conditions": self.conditions,
            "reason": self.reason,
            "warning": self.warning,
            "metadata": self.metadata
        }


@dataclass
class CooldownConfig:
    """
    Cooldown configuration / 冷卻設定
    
    Defines cooldown periods for different signal types.
    Loads from config/monitoring_params.json if not explicitly provided.
    定義不同訊號類型的冷卻期。若未明確提供則從配置載入。
    """
    trend_long_seconds: int = None
    trend_short_seconds: int = None
    contrarian_watch_seconds: int = None
    
    def __post_init__(self):
        """Load defaults from config if not provided"""
        try:
            if self.trend_long_seconds is None:
                self.trend_long_seconds = get_cooldown_minutes("trend_long") * 60
            if self.trend_short_seconds is None:
                self.trend_short_seconds = get_cooldown_minutes("trend_short") * 60
            if self.contrarian_watch_seconds is None:
                self.contrarian_watch_seconds = get_cooldown_minutes("contrarian_watch") * 60
        except Exception:
            # Fallback defaults
            if self.trend_long_seconds is None:
                self.trend_long_seconds = 1800  # 30 minutes
            if self.trend_short_seconds is None:
                self.trend_short_seconds = 1800  # 30 minutes
            if self.contrarian_watch_seconds is None:
                self.contrarian_watch_seconds = 900  # 15 minutes


class CooldownManager:
    """
    Signal cooldown manager / 訊號冷卻管理器
    
    Manages cooldown periods to prevent duplicate signals.
    管理冷卻期以防止重複訊號。
    """
    
    def __init__(self, config: Optional[CooldownConfig] = None):
        """
        Initialize cooldown manager / 初始化冷卻管理器
        
        Args:
            config: Cooldown configuration / 冷卻設定
        """
        self.config = config or CooldownConfig()
        self._last_signals: Dict[str, float] = {}
    
    def _get_key(self, symbol: str, signal_type: SignalType) -> str:
        """Generate cooldown key / 產生冷卻鍵"""
        return f"{symbol}:{signal_type.value}"
    
    def get_cooldown_seconds(self, signal_type: SignalType) -> int:
        """Get cooldown period for signal type / 取得訊號類型的冷卻期"""
        if signal_type == SignalType.TREND_LONG:
            return self.config.trend_long_seconds
        elif signal_type == SignalType.TREND_SHORT:
            return self.config.trend_short_seconds
        elif signal_type in [
            SignalType.CONTRARIAN_WATCH_OVERHEATED,
            SignalType.CONTRARIAN_WATCH_OVERSOLD
        ]:
            return self.config.contrarian_watch_seconds
        return 0
    
    def can_emit(self, symbol: str, signal_type: SignalType) -> bool:
        """
        Check if signal can be emitted / 檢查訊號是否可以發送
        
        Args:
            symbol: Trading pair / 交易對
            signal_type: Type of signal / 訊號類型
            
        Returns:
            True if signal can be emitted / 若可以發送則為 True
        """
        key = self._get_key(symbol, signal_type)
        last_time = self._last_signals.get(key)
        
        if last_time is None:
            return True
        
        cooldown = self.get_cooldown_seconds(signal_type)
        elapsed = time.time() - last_time
        
        return elapsed >= cooldown
    
    def record_emission(self, symbol: str, signal_type: SignalType) -> None:
        """Record signal emission time / 記錄訊號發送時間"""
        key = self._get_key(symbol, signal_type)
        self._last_signals[key] = time.time()
    
    def get_remaining_cooldown(self, symbol: str, signal_type: SignalType) -> float:
        """Get remaining cooldown seconds / 取得剩餘冷卻秒數"""
        key = self._get_key(symbol, signal_type)
        last_time = self._last_signals.get(key)
        
        if last_time is None:
            return 0.0
        
        cooldown = self.get_cooldown_seconds(signal_type)
        elapsed = time.time() - last_time
        remaining = cooldown - elapsed
        
        return max(0.0, remaining)
    
    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset cooldown state / 重置冷卻狀態"""
        if symbol is None:
            self._last_signals.clear()
        else:
            keys_to_remove = [k for k in self._last_signals if k.startswith(f"{symbol}:")]
            for key in keys_to_remove:
                del self._last_signals[key]


class SignalEngine:
    """
    Signal generation engine / 訊號產生引擎
    
    Generates trading signals based on technical indicator analysis.
    根據技術指標分析產生交易訊號。
    
    Signals generated:
    - trend_long: Bullish trend following signal
    - trend_short: Bearish trend following signal
    - contrarian_watch_overheated: Potential reversal from extended up move
    - contrarian_watch_oversold: Potential reversal from extended down move
    
    ⚠️  ALERT ONLY - No automatic trading
    """
    
    def __init__(
        self,
        fetcher: Optional[BinanceFetcher] = None,
        cooldown_manager: Optional[CooldownManager] = None
    ):
        """
        Initialize signal engine / 初始化訊號引擎
        
        Args:
            fetcher: Data fetcher instance / 資料抓取器實例
            cooldown_manager: Cooldown manager instance / 冷卻管理器實例
        """
        self.fetcher = fetcher or create_fetcher()
        self.cooldown = cooldown_manager or CooldownManager()
    
    # =========================================================================
    # Signal Condition Checks / 訊號條件檢查
    # =========================================================================
    
    def _check_trend_long_conditions(
        self,
        close_5m: float,
        ma5: List[float],
        ma20: List[float],
        ma240: List[float],
        volume_1m: float,
        volumes_1m: List[float]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check trend_long conditions / 檢查 trend_long 條件
        
        Conditions (ALL must be met):
        1. close_5m > MA240
        2. MA5 crossed above MA20
        3. 1m volume > 2x average(20)
        """
        conditions = {
            "c1_above_ma240": False,
            "c2_ma_cross_above": False,
            "c3_volume_spike": False
        }
        details = {}
        
        # C1: Price above long-term trend
        if ma240:
            conditions["c1_above_ma240"] = close_5m > ma240[-1]
            details["ma240"] = ma240[-1]
        
        # C2: MA cross
        if ma5 and ma20:
            cross_result = detect_ma_cross(ma5, ma20)
            conditions["c2_ma_cross_above"] = (
                cross_result.cross_type == CrossType.CROSS_ABOVE
            )
            details["cross_result"] = cross_result
        
        # C3: Volume confirmation
        if volumes_1m:
            vol_analysis = analyze_volume(volume_1m, volumes_1m, period=20, threshold=1.5)
            conditions["c3_volume_spike"] = vol_analysis.is_spike
            details["volume_analysis"] = vol_analysis
        
        all_met = all(conditions.values())
        return all_met, {"conditions": conditions, "details": details}
    
    def _check_trend_short_conditions(
        self,
        close_5m: float,
        ma5: List[float],
        ma20: List[float],
        ma240: List[float],
        volume_1m: float,
        volumes_1m: List[float]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check trend_short conditions / 檢查 trend_short 條件
        
        Conditions (ALL must be met):
        1. close_5m < MA240
        2. MA5 crossed below MA20
        3. 1m volume > 2x average(20)
        """
        conditions = {
            "c1_below_ma240": False,
            "c2_ma_cross_below": False,
            "c3_volume_spike": False
        }
        details = {}
        
        # C1: Price below long-term trend
        if ma240:
            conditions["c1_below_ma240"] = close_5m < ma240[-1]
            details["ma240"] = ma240[-1]
        
        # C2: MA cross
        if ma5 and ma20:
            cross_result = detect_ma_cross(ma5, ma20)
            conditions["c2_ma_cross_below"] = (
                cross_result.cross_type == CrossType.CROSS_BELOW
            )
            details["cross_result"] = cross_result
        
        # C3: Volume confirmation
        if volumes_1m:
            vol_analysis = analyze_volume(volume_1m, volumes_1m, period=20, threshold=1.5)
            conditions["c3_volume_spike"] = vol_analysis.is_spike
            details["volume_analysis"] = vol_analysis
        
        all_met = all(conditions.values())
        return all_met, {"conditions": conditions, "details": details}
    
    def _check_contrarian_conditions(
        self,
        candles_15m: List[Dict[str, Any]]
    ) -> Tuple[Optional[SignalType], Dict[str, Any]]:
        """
        Check contrarian watch conditions / 檢查逆勢觀察條件
        
        Returns signal type if pattern detected, None otherwise.
        若檢測到型態則回傳訊號類型，否則回傳 None。
        
        ⚠️  WATCH ONLY - Not execution signal
        """
        # Check overheated (4 consecutive red)
        red_result = detect_four_consecutive_red(candles_15m)
        if red_result.pattern_detected:
            return SignalType.CONTRARIAN_WATCH_OVERHEATED, {
                "pattern": red_result,
                "type": "overheated"
            }
        
        # Check oversold (4 consecutive green)
        green_result = detect_four_consecutive_green(candles_15m)
        if green_result.pattern_detected:
            return SignalType.CONTRARIAN_WATCH_OVERSOLD, {
                "pattern": green_result,
                "type": "oversold"
            }
        
        return None, {}
    
    # =========================================================================
    # Signal Generation / 訊號產生
    # =========================================================================
    
    def generate_trend_long_signal(
        self,
        symbol: str,
        close_5m: float,
        ma5: List[float],
        ma20: List[float],
        ma240: List[float],
        volume_1m: float,
        volumes_1m: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """
        Generate trend_long signal if conditions met / 若條件符合則產生 trend_long 訊號
        """
        # Check cooldown / 檢查冷卻
        if not self.cooldown.can_emit(symbol, SignalType.TREND_LONG):
            return None
        
        # Check conditions / 檢查條件
        conditions_met, analysis = self._check_trend_long_conditions(
            close_5m, ma5, ma20, ma240, volume_1m, volumes_1m
        )
        
        if not conditions_met:
            return None
        
        # Generate signal / 產生訊號
        details = analysis["details"]
        vol_analysis = details.get("volume_analysis")
        
        signal = Signal(
            signal_type=SignalType.TREND_LONG,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close_5m": close_5m,
                "ma5": details.get("cross_result", {}).short_ma_value if details.get("cross_result") else None,
                "ma20": details.get("cross_result", {}).long_ma_value if details.get("cross_result") else None,
                "ma240": details.get("ma240"),
                "volume_1m": volume_1m,
                "volume_avg_1m": vol_analysis.avg_volume if vol_analysis else None,
                "volume_ratio": round(vol_analysis.ratio, 2) if vol_analysis else None
            },
            conditions=analysis["conditions"],
            reason=f"{symbol}: close > MA240, MA5 crossed above MA20, volume {vol_analysis.ratio:.2f}x average",
            warning="ALERT_ONLY_NO_AUTO_TRADE"
        )
        
        # Record emission / 記錄發送
        self.cooldown.record_emission(symbol, SignalType.TREND_LONG)
        
        return signal
    
    def generate_trend_short_signal(
        self,
        symbol: str,
        close_5m: float,
        ma5: List[float],
        ma20: List[float],
        ma240: List[float],
        volume_1m: float,
        volumes_1m: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """
        Generate trend_short signal if conditions met / 若條件符合則產生 trend_short 訊號
        """
        # Check cooldown / 檢查冷卻
        if not self.cooldown.can_emit(symbol, SignalType.TREND_SHORT):
            return None
        
        # Check conditions / 檢查條件
        conditions_met, analysis = self._check_trend_short_conditions(
            close_5m, ma5, ma20, ma240, volume_1m, volumes_1m
        )
        
        if not conditions_met:
            return None
        
        # Generate signal / 產生訊號
        details = analysis["details"]
        vol_analysis = details.get("volume_analysis")
        
        signal = Signal(
            signal_type=SignalType.TREND_SHORT,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close_5m": close_5m,
                "ma5": details.get("cross_result", {}).short_ma_value if details.get("cross_result") else None,
                "ma20": details.get("cross_result", {}).long_ma_value if details.get("cross_result") else None,
                "ma240": details.get("ma240"),
                "volume_1m": volume_1m,
                "volume_avg_1m": vol_analysis.avg_volume if vol_analysis else None,
                "volume_ratio": round(vol_analysis.ratio, 2) if vol_analysis else None
            },
            conditions=analysis["conditions"],
            reason=f"{symbol}: close < MA240, MA5 crossed below MA20, volume {vol_analysis.ratio:.2f}x average",
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "ma_cross_trend_short", "conditions_passed": len([c for c in analysis["conditions"].values() if c]), "conditions_total": len(analysis["conditions"])}
        )
        
        # Record emission / 記錄發送
        self.cooldown.record_emission(symbol, SignalType.TREND_SHORT)
        
        return signal
    
    def generate_contrarian_watch_signal(
        self,
        symbol: str,
        candles_15m: List[Dict[str, Any]],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """
        Generate contrarian_watch signal if pattern detected / 若檢測到型態則產生 contrarian_watch 訊號
        
        ⚠️  WATCH ONLY - Not execution signal / 僅觀察 - 非執行訊號
        """
        # Check conditions / 檢查條件
        signal_type, details = self._check_contrarian_conditions(candles_15m)
        
        if signal_type is None:
            return None
        
        # Check cooldown / 檢查冷卻
        if not self.cooldown.can_emit(symbol, signal_type):
            return None
        
        pattern_type = details.get("type", "unknown")
        pattern_result = details.get("pattern")
        
        signal = Signal(
            signal_type=signal_type,
            level=SignalLevel.WATCH_ONLY,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "timeframe": "15m",
                "pattern": pattern_type,
                "consecutive_count": pattern_result.consecutive_count if pattern_result else 0
            },
            conditions={"pattern_detected": True},
            reason=f"{symbol} 15m: {pattern_result.consecutive_count} consecutive {pattern_type} candles - potential reversal zone",
            warning="WATCH_ONLY_NOT_EXECUTION_SIGNAL",
            metadata={
                "strategy_name": "contrarian_watch_overheated" if signal_type == SignalType.CONTRARIAN_WATCH_OVERHEATED else "contrarian_watch_oversold",
                "conditions_passed": 1,
                "conditions_total": 1
            }
        )
        
        # Record emission / 記錄發送
        self.cooldown.record_emission(symbol, signal_type)
        
        return signal
    
    # =========================================================================
    # High-Level Signal Processing / 高階訊號處理
    # =========================================================================
    
    def process_symbol(
        self,
        symbol: str,
        data_5m: List[KlineData],
        data_1m: List[KlineData],
        data_15m: List[KlineData]
    ) -> List[Signal]:
        """
        Process all signals for a symbol / 處理單一標的所有訊號
        
        Args:
            symbol: Trading pair / 交易對
            data_5m: 5m kline data / 5m K 線資料
            data_1m: 1m kline data / 1m K 線資料
            data_15m: 15m kline data / 15m K 線資料
            
        Returns:
            List of generated signals / 產生的訊號列表
        """
        signals = []
        
        # Extract data / 提取資料
        closes_5m = [k.close for k in data_5m]
        volumes_1m = [k.volume for k in data_1m]
        candles_15m = [
            {"open": k.open, "close": k.close} for k in data_15m
        ]
        
        # Calculate indicators / 計算指標
        ma5 = calculate_ma5(closes_5m)
        ma20 = calculate_ma20(closes_5m)
        ma240 = calculate_ma240(closes_5m) if len(closes_5m) >= 240 else []
        
        current_close_5m = closes_5m[-1] if closes_5m else 0
        current_volume_1m = volumes_1m[-1] if volumes_1m else 0
        
        # Generate trend_long signal / 產生 trend_long 訊號
        if ma5 and ma20 and ma240 and volumes_1m:
            trend_long = self.generate_trend_long_signal(
                symbol=symbol,
                close_5m=current_close_5m,
                ma5=ma5,
                ma20=ma20,
                ma240=ma240,
                volume_1m=current_volume_1m,
                volumes_1m=volumes_1m
            )
            if trend_long:
                signals.append(trend_long)
        
        # Generate trend_short signal / 產生 trend_short 訊號
        if ma5 and ma20 and ma240 and volumes_1m:
            trend_short = self.generate_trend_short_signal(
                symbol=symbol,
                close_5m=current_close_5m,
                ma5=ma5,
                ma20=ma20,
                ma240=ma240,
                volume_1m=current_volume_1m,
                volumes_1m=volumes_1m
            )
            if trend_short:
                signals.append(trend_short)
        
        # Generate contrarian_watch signal / 產生 contrarian_watch 訊號
        if candles_15m:
            contrarian = self.generate_contrarian_watch_signal(
                symbol=symbol,
                candles_15m=candles_15m
            )
            if contrarian:
                signals.append(contrarian)
        
        return signals
    
    def get_cooldown_status(self, symbol: str) -> Dict[str, float]:
        """
        Get cooldown status for symbol / 取得標的的冷卻狀態
        
        Returns:
            Dictionary of signal type to remaining cooldown seconds
            訊號類型到剩餘冷卻秒數的字典
        """
        return {
            "trend_long": self.cooldown.get_remaining_cooldown(symbol, SignalType.TREND_LONG),
            "trend_short": self.cooldown.get_remaining_cooldown(symbol, SignalType.TREND_SHORT),
            "contrarian_watch_overheated": self.cooldown.get_remaining_cooldown(
                symbol, SignalType.CONTRARIAN_WATCH_OVERHEATED
            ),
            "contrarian_watch_oversold": self.cooldown.get_remaining_cooldown(
                symbol, SignalType.CONTRARIAN_WATCH_OVERSOLD
            )
        }


# Example usage / 使用範例
if __name__ == "__main__":
    print("Signal Engine Module")
    print("訊號引擎模組")
    print("=" * 40)
    
    print("\n⚠️  ALERT ONLY SYSTEM / 僅提醒系統")
    print("This module generates ALERTS ONLY.")
    print("本模組僅產生提醒。")
    print("NO automatic trading is performed.")
    print("不執行自動交易。")
    
    print("\nSignal Types / 訊號類型:")
    for sig_type in SignalType:
        print(f"  - {sig_type.value}")
    
    print("\nExample / 範例:")
    print("  engine = SignalEngine()")
    print("  signals = engine.process_symbol('BTCUSDT', data_5m, data_1m, data_15m)")
    
    print("\n⚠️  IMPORTANT / 重要")
    print("contrarian_watch signals are WATCH-ONLY.")
    print("contrarian_watch 訊號僅供觀察。")
    print("NOT execution signals / 非執行訊號。")
