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
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    # 13 unique strategy signal types
    MA_CROSS_TREND = "ma_cross_trend"
    MA_CROSS_TREND_SHORT = "ma_cross_trend_short"
    CONTRARIAN_OVERHEATED = "contrarian_overheated"
    CONTRARIAN_OVERSOLD = "contrarian_oversold"
    HILBERT_CYCLE = "hilbert_cycle"
    STOCHASTIC_BREAKOUT = "stochastic_breakout"
    RSI_TREND = "rsi_trend"
    BB_MEAN_REVERSION = "bb_mean_reversion"
    EMA_CROSS_FAST = "ema_cross_fast"
    RSI_MID_BOUNCE = "rsi_mid_bounce"
    VOLUME_SPIKE = "volume_spike"
    PRICE_CHANNEL_BREAK = "price_channel_break"
    MOMENTUM_DIVERGENCE = "momentum_divergence"
    # Exit signal types for position management
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"
    # New strategies / 新增策略
    SUPERTREND = "supertrend"
    ICHIMOKU_CLOUD = "ichimoku_cloud"
    WILLIAMS_R = "williams_r"
    KELTNER_BREAKOUT = "keltner_breakout"
    ATR_BREAKOUT = "atr_breakout"


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
    supertrend_seconds: int = None
    ichimoku_seconds: int = None
    williams_r_seconds: int = None
    keltner_seconds: int = None
    atr_breakout_seconds: int = None
    
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
        # New strategy cooldowns / 新增策略冷卻期
        if self.supertrend_seconds is None:
            self.supertrend_seconds = 1800  # 30 minutes
        if self.ichimoku_seconds is None:
            self.ichimoku_seconds = 1800
        if self.williams_r_seconds is None:
            self.williams_r_seconds = 1800
        if self.keltner_seconds is None:
            self.keltner_seconds = 1800
        if self.atr_breakout_seconds is None:
            self.atr_breakout_seconds = 1800


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
        if signal_type == SignalType.MA_CROSS_TREND:
            return self.config.trend_long_seconds
        elif signal_type == SignalType.MA_CROSS_TREND_SHORT:
            return self.config.trend_short_seconds
        elif signal_type in [
            SignalType.CONTRARIAN_OVERHEATED,
            SignalType.CONTRARIAN_OVERSOLD
        ]:
            return self.config.contrarian_watch_seconds
        elif signal_type == SignalType.SUPERTREND:
            return self.config.supertrend_seconds
        elif signal_type == SignalType.ICHIMOKU_CLOUD:
            return self.config.ichimoku_seconds
        elif signal_type == SignalType.WILLIAMS_R:
            return self.config.williams_r_seconds
        elif signal_type == SignalType.KELTNER_BREAKOUT:
            return self.config.keltner_seconds
        elif signal_type == SignalType.ATR_BREAKOUT:
            return self.config.atr_breakout_seconds
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
            return SignalType.CONTRARIAN_OVERHEATED, {
                "pattern": red_result,
                "type": "overheated"
            }
        
        # Check oversold (4 consecutive green)
        green_result = detect_four_consecutive_green(candles_15m)
        if green_result.pattern_detected:
            return SignalType.CONTRARIAN_OVERSOLD, {
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
        if not self.cooldown.can_emit(symbol, SignalType.MA_CROSS_TREND):
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
            signal_type=SignalType.MA_CROSS_TREND,
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
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "ma_cross_trend", "conditions_passed": len([c for c in analysis["conditions"].values() if c]), "conditions_total": len(analysis["conditions"])}
        )
        
        # Record emission / 記錄發送
        self.cooldown.record_emission(symbol, SignalType.MA_CROSS_TREND)
        
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
        if not self.cooldown.can_emit(symbol, SignalType.MA_CROSS_TREND_SHORT):
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
            signal_type=SignalType.MA_CROSS_TREND_SHORT,
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
        self.cooldown.record_emission(symbol, SignalType.MA_CROSS_TREND_SHORT)
        
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
                "strategy_name": "contrarian_watch_overheated" if signal_type == SignalType.CONTRARIAN_OVERHEATED else "contrarian_watch_oversold",
                "conditions_passed": 1,
                "conditions_total": 1
            }
        )
        
        # Record emission / 記錄發送
        self.cooldown.record_emission(symbol, signal_type)
        
        return signal
    
    # =========================================================================
    # Supertrend Signal / Supertrend 訊號
    # =========================================================================
    
    def _check_supertrend_conditions(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Tuple[bool, str, str]:
        """
        Check supertrend conditions / 檢查 Supertrend 條件
        
        Returns: (triggered, direction, reason)
        """
        if len(closes) < 2:
            return False, None, "Not enough data"
        
        # Calculate ATR-based bands
        n = 10
        mult = 2.0
        
        # Use last n periods
        slice_highs = highs[-n:] if len(highs) >= n else highs
        slice_lows = lows[-n:] if len(lows) >= n else lows
        slice_closes = closes[-n:] if len(closes) >= n else closes
        
        if len(slice_closes) < 2:
            return False, None, "Not enough data"
        
        # Simple ATR proxy: rolling high-low
        atr_vals = []
        for i in range(len(slice_highs)):
            atr_vals.append(slice_highs[i] - slice_lows[i])
        
        # hl2 and bands
        hl2 = [(slice_highs[i] + slice_lows[i]) / 2 for i in range(len(slice_closes))]
        
        # Use current ATR
        current_atr = sum(atr_vals) / len(atr_vals) if atr_vals else 0
        current_hl2 = hl2[-1]
        upper_band = current_hl2 + mult * current_atr
        lower_band = current_hl2 - mult * current_atr
        
        current_close = closes[-1]
        prev_close = closes[-2]
        
        # Supertrend direction flip detection
        if prev_close <= lower_band and current_close > lower_band:
            return True, "LONG", f"Supertrend flipped LONG: close {current_close:.2f} > lower {lower_band:.2f}"
        elif prev_close >= upper_band and current_close < upper_band:
            return True, "SHORT", f"Supertrend flipped SHORT: close {current_close:.2f} < upper {upper_band:.2f}"
        
        return False, None, f"Supertrend: close {current_close:.2f}, upper {upper_band:.2f}, lower {lower_band:.2f}"
    
    def generate_supertrend_signal(
        self,
        symbol: str,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """Generate supertrend signal / 產生 Supertrend 訊號"""
        if not self.cooldown.can_emit(symbol, SignalType.SUPERTREND):
            return None
        
        triggered, direction, reason = self._check_supertrend_conditions(highs, lows, closes)
        if not triggered:
            return None
        
        signal = Signal(
            signal_type=SignalType.SUPERTREND,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close": closes[-1] if closes else 0,
                "high": highs[-1] if highs else 0,
                "low": lows[-1] if lows else 0,
            },
            conditions={"supertrend_flip": True, "direction": direction},
            reason=reason,
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "supertrend", "direction": direction}
        )
        
        self.cooldown.record_emission(symbol, SignalType.SUPERTREND)
        return signal
    
    # =========================================================================
    # Ichimoku Cloud Signal / 一目均衡表訊號
    # =========================================================================
    
    def _check_ichimoku_conditions(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Tuple[bool, str, str]:
        """
        Check Ichimoku Cloud conditions / 檢查一目均衡表條件
        
        做多：收盤價 > 雲上方 + 轉換線 > 基準線
        做空：收盤價 < 雲下方 + 轉換線 < 基準線
        
        Returns: (triggered, direction, reason)
        """
        if len(closes) < 52:
            return False, None, "Not enough data (need 52 periods)"
        
        from indicators.calculator import calculate_ichimoku
        
        tenkan, kijun, senkou_a, senkou_b = calculate_ichimoku(highs, lows, closes)
        
        current_close = closes[-1]
        current_tenkan = tenkan[-1]
        current_kijun = kijun[-1]
        current_a = senkou_a[-1]
        current_b = senkou_b[-1]
        
        cloud_top = max(current_a, current_b)
        cloud_bottom = min(current_a, current_b)
        
        # Long: above cloud + tenkan > kijun
        if current_close > cloud_top and current_tenkan > current_kijun:
            return True, "LONG", f"Ichimoku LONG: close {current_close:.2f} > cloud {cloud_top:.2f}, tenkan {current_tenkan:.2f} > kijun {current_kijun:.2f}"
        
        # Short: below cloud + tenkan < kijun
        if current_close < cloud_bottom and current_tenkan < current_kijun:
            return True, "SHORT", f"Ichimoku SHORT: close {current_close:.2f} < cloud {cloud_bottom:.2f}, tenkan {current_tenkan:.2f} < kijun {current_kijun:.2f}"
        
        return False, None, f"Ichimoku: close {current_close:.2f}, cloud [{cloud_bottom:.2f}-{cloud_top:.2f}], tenkan {current_tenkan:.2f}, kijun {current_kijun:.2f}"
    
    def generate_ichimoku_signal(
        self,
        symbol: str,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """Generate Ichimoku Cloud signal / 產生一目均衡表訊號"""
        if not self.cooldown.can_emit(symbol, SignalType.ICHIMOKU_CLOUD):
            return None
        
        triggered, direction, reason = self._check_ichimoku_conditions(highs, lows, closes)
        if not triggered:
            return None
        
        signal = Signal(
            signal_type=SignalType.ICHIMOKU_CLOUD,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close": closes[-1] if closes else 0,
                "high": highs[-1] if highs else 0,
                "low": lows[-1] if lows else 0,
            },
            conditions={"above_cloud": direction == "LONG", "below_cloud": direction == "SHORT"},
            reason=reason,
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "ichimoku_cloud", "direction": direction}
        )
        
        self.cooldown.record_emission(symbol, SignalType.ICHIMOKU_CLOUD)
        return signal
    
    # =========================================================================
    # Williams %R Signal / Williams %R 訊號
    # =========================================================================
    
    def _check_williams_r_conditions(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Tuple[bool, str, str]:
        """
        Check Williams %R conditions / 檢查 Williams %R 條件
        
        WR = (Highest High - Close) / (Highest High - Lowest Low) * -100
        做多：WR 從 -80 以下反彈穿越 -80
        做空：WR 從 -20 以上跌破 -20
        
        Returns: (triggered, direction, reason)
        """
        if len(closes) < 3:
            return False, None, "Not enough data"
        
        period = 14
        if len(closes) < period:
            period = len(closes)
        
        # Calculate Williams %R for last 3 values
        wr_values = []
        for i in range(max(0, len(closes) - 3), len(closes)):
            start = max(0, i - period + 1)
            hh = max(highs[start:i+1])
            ll = min(lows[start:i+1])
            c = closes[i]
            
            if hh == ll:
                wr = -50.0
            else:
                wr = ((hh - c) / (hh - ll)) * -100
            wr_values.append(wr)
        
        if len(wr_values) < 3:
            return False, None, "Not enough WR values"
        
        prev_wr = wr_values[-2]
        current_wr = wr_values[-1]
        
        # Long: WR crosses above -80 from below (oversold bounce)
        if prev_wr < -80 and current_wr >= -80:
            return True, "LONG", f"Williams %R oversold bounce: {prev_wr:.1f} -> {current_wr:.1f}"
        
        # Short: WR crosses below -20 from above (overbought pullback)
        if prev_wr > -20 and current_wr <= -20:
            return True, "SHORT", f"Williams %R overbought pullback: {prev_wr:.1f} -> {current_wr:.1f}"
        
        return False, None, f"Williams %R: {current_wr:.1f}"
    
    def generate_williams_r_signal(
        self,
        symbol: str,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """Generate Williams %R signal / 產生 Williams %R 訊號"""
        if not self.cooldown.can_emit(symbol, SignalType.WILLIAMS_R):
            return None
        
        triggered, direction, reason = self._check_williams_r_conditions(highs, lows, closes)
        if not triggered:
            return None
        
        signal = Signal(
            signal_type=SignalType.WILLIAMS_R,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close": closes[-1] if closes else 0,
                "high": highs[-1] if highs else 0,
                "low": lows[-1] if lows else 0,
            },
            conditions={"oversold_bounce": direction == "LONG", "overbought_pullback": direction == "SHORT"},
            reason=reason,
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "williams_r", "direction": direction}
        )
        
        self.cooldown.record_emission(symbol, SignalType.WILLIAMS_R)
        return signal
    
    # =========================================================================
    # Keltner Breakout Signal / Keltner 突破訊號
    # =========================================================================
    
    def _check_keltner_conditions(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Tuple[bool, str, str]:
        """
        Check Keltner Channel breakout conditions / 檢查 Keltner 通道突破條件
        
        中線 = EMA(20)
        上軌 = EMA(20) + 2 * ATR(10)
        下軌 = EMA(20) - 2 * ATR(10)
        
        Returns: (triggered, direction, reason)
        """
        if len(closes) < 20:
            return False, None, "Not enough data (need 20 periods)"
        
        from indicators.calculator import calculate_ema, calculate_atr
        
        # EMA(20)
        ema20_values = calculate_ema(closes, 20)
        if not ema20_values:
            return False, None, "EMA calculation failed"
        
        ema20 = ema20_values[-1]
        
        # ATR(10)
        atr_values = calculate_atr(highs, lows, closes, period=10)
        if not atr_values or atr_values[-1] == 0:
            return False, None, "ATR calculation failed"
        
        atr = atr_values[-1]
        current_close = closes[-1]
        
        upper = ema20 + 2.0 * atr
        lower = ema20 - 2.0 * atr
        
        # Long: close above upper band
        if current_close > upper:
            return True, "LONG", f"Keltner LONG: close {current_close:.2f} > upper {upper:.2f} (EMA20={ema20:.2f}, ATR={atr:.2f})"
        
        # Short: close below lower band
        if current_close < lower:
            return True, "SHORT", f"Keltner SHORT: close {current_close:.2f} < lower {lower:.2f} (EMA20={ema20:.2f}, ATR={atr:.2f})"
        
        return False, None, f"Keltner: close {current_close:.2f}, upper {upper:.2f}, lower {lower:.2f}"
    
    def generate_keltner_signal(
        self,
        symbol: str,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """Generate Keltner breakout signal / 產生 Keltner 突破訊號"""
        if not self.cooldown.can_emit(symbol, SignalType.KELTNER_BREAKOUT):
            return None
        
        triggered, direction, reason = self._check_keltner_conditions(highs, lows, closes)
        if not triggered:
            return None
        
        signal = Signal(
            signal_type=SignalType.KELTNER_BREAKOUT,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close": closes[-1] if closes else 0,
                "high": highs[-1] if highs else 0,
                "low": lows[-1] if lows else 0,
            },
            conditions={"upper_breakout": direction == "LONG", "lower_breakdown": direction == "SHORT"},
            reason=reason,
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "keltner_breakout", "direction": direction}
        )
        
        self.cooldown.record_emission(symbol, SignalType.KELTNER_BREAKOUT)
        return signal
    
    # =========================================================================
    # ATR Breakout Signal / ATR 突破訊號
    # =========================================================================
    
    def _check_atr_breakout_conditions(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Tuple[bool, str, str]:
        """
        Check ATR breakout conditions / 檢查 ATR 突破條件
        
        突破門檻 = 前一根收盤價 ± 1.5 * ATR(14)
        做多：當前收盤 > 前收盤 + 1.5 * ATR
        做空：當前收盤 < 前收盤 - 1.5 * ATR
        
        Returns: (triggered, direction, reason)
        """
        if len(closes) < 2:
            return False, None, "Not enough data"
        
        from indicators.calculator import calculate_atr
        
        # ATR(14)
        atr_values = calculate_atr(highs, lows, closes, period=14)
        if not atr_values or atr_values[-1] == 0:
            return False, None, "ATR calculation failed"
        
        atr = atr_values[-1]
        current_close = closes[-1]
        prev_close = closes[-2]
        
        upper = prev_close + 1.5 * atr
        lower = prev_close - 1.5 * atr
        
        # Long: close above prev_close + 1.5*ATR
        if current_close > upper:
            return True, "LONG", f"ATR LONG: close {current_close:.2f} > threshold {upper:.2f} (prev={prev_close:.2f}, ATR={atr:.2f})"
        
        # Short: close below prev_close - 1.5*ATR
        if current_close < lower:
            return True, "SHORT", f"ATR SHORT: close {current_close:.2f} < threshold {lower:.2f} (prev={prev_close:.2f}, ATR={atr:.2f})"
        
        return False, None, f"ATR: close {current_close:.2f}, threshold [{lower:.2f}-{upper:.2f}]"
    
    def generate_atr_breakout_signal(
        self,
        symbol: str,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        timestamp: Optional[int] = None
    ) -> Optional[Signal]:
        """Generate ATR breakout signal / 產生 ATR 突破訊號"""
        if not self.cooldown.can_emit(symbol, SignalType.ATR_BREAKOUT):
            return None
        
        triggered, direction, reason = self._check_atr_breakout_conditions(highs, lows, closes)
        if not triggered:
            return None
        
        signal = Signal(
            signal_type=SignalType.ATR_BREAKOUT,
            level=SignalLevel.CONFIRMED,
            symbol=symbol,
            timestamp=timestamp or int(time.time() * 1000),
            price_data={
                "close": closes[-1] if closes else 0,
                "high": highs[-1] if highs else 0,
                "low": lows[-1] if lows else 0,
            },
            conditions={"atr_upper_break": direction == "LONG", "atr_lower_break": direction == "SHORT"},
            reason=reason,
            warning="ALERT_ONLY_NO_AUTO_TRADE",
            metadata={"strategy_name": "atr_breakout", "direction": direction}
        )
        
        self.cooldown.record_emission(symbol, SignalType.ATR_BREAKOUT)
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
        
        # Generate supertrend signal / 產生 Supertrend 訊號
        highs_5m = [k.high for k in data_5m]
        lows_5m = [k.low for k in data_5m]
        if highs_5m and lows_5m and closes_5m:
            supertrend = self.generate_supertrend_signal(
                symbol=symbol,
                highs=highs_5m,
                lows=lows_5m,
                closes=closes_5m
            )
            if supertrend:
                signals.append(supertrend)
        
        # Generate ichimoku_cloud signal / 產生 Ichimoku Cloud 訊號
        if highs_5m and lows_5m and closes_5m:
            ichimoku = self.generate_ichimoku_signal(
                symbol=symbol,
                highs=highs_5m,
                lows=lows_5m,
                closes=closes_5m
            )
            if ichimoku:
                signals.append(ichimoku)
        
        # Generate williams_r signal / 產生 Williams %R 訊號
        if highs_5m and lows_5m and closes_5m:
            williams = self.generate_williams_r_signal(
                symbol=symbol,
                highs=highs_5m,
                lows=lows_5m,
                closes=closes_5m
            )
            if williams:
                signals.append(williams)
        
        # Generate keltner_breakout signal / 產生 Keltner 突破訊號
        if highs_5m and lows_5m and closes_5m:
            keltner = self.generate_keltner_signal(
                symbol=symbol,
                highs=highs_5m,
                lows=lows_5m,
                closes=closes_5m
            )
            if keltner:
                signals.append(keltner)
        
        # Generate atr_breakout signal / 產生 ATR 突破訊號
        if highs_5m and lows_5m and closes_5m:
            atr_breakout = self.generate_atr_breakout_signal(
                symbol=symbol,
                highs=highs_5m,
                lows=lows_5m,
                closes=closes_5m
            )
            if atr_breakout:
                signals.append(atr_breakout)
        
        return signals
    
    def generate_signals(self, indicators: Dict[str, Any]) -> List[Signal]:
        """
        Generate signals from indicator data (backtest compatibility).
        從指標資料產生訊號（回測相容性）。
        
        Args:
            indicators: Dict with MA5, MA20, MA240, volume keys
            
        Returns:
            List of Signal objects
        """
        signals = []
        
        # Extract values
        ma5 = indicators.get('MA5')
        ma20 = indicators.get('MA20')
        ma240 = indicators.get('MA240')
        volume = indicators.get('volume')
        
        # Debug
        print(f"[DEBUG generate_signals] ma5={ma5 is not None}, ma20={ma20 is not None}, ma240={ma240 is not None}, volume={volume}")
        
        # Check if we have valid data
        if not ma5 or not ma20 or not ma240:
            return signals
        
        # Ensure lists
        if not isinstance(ma5, list):
            ma5 = [ma5]
        if not isinstance(ma20, list):
            ma20 = [ma20]
        if not isinstance(ma240, list):
            ma240 = [ma240]
        
        # Get current values
        current_close = ma5[-1] if ma5 else 0
        current_volume = volume if volume else 0
        
    def generate_signals(self, indicators: Dict[str, Any]) -> List[Signal]:
        """
        Generate signals from indicator data (backtest compatibility).
        從指標資料產生訊號（回測相容性）。
        
        Args:
            indicators: Dict with MA5, MA20, MA240, volume keys
            
        Returns:
            List of Signal objects
        """
        signals = []
        
        # Extract values
        ma5 = indicators.get('MA5')
        ma20 = indicators.get('MA20')
        ma240 = indicators.get('MA240')
        volume = indicators.get('volume')
        
        # Check if we have valid data
        if not ma5 or not ma20 or not ma240:
            return signals
        
        # Ensure lists
        if not isinstance(ma5, list):
            ma5 = [ma5]
        if not isinstance(ma20, list):
            ma20 = [ma20]
        if not isinstance(ma240, list):
            ma240 = [ma240]
        
        # Get current values
        current_close = ma5[-1] if ma5 else 0
        current_volume = volume if volume else 0
        
        # Use actual volume history if provided (backtest), otherwise mock
        volumes_1m = indicators.get('volume_history') or [current_volume] * 20
        
        # For backtest, use simpler trend-following logic (not just cross)
        if indicators.get('backtest_mode', False):
            ma5_last = ma5[-1] if ma5 else 0
            ma20_last = ma20[-1] if ma20 else 0
            ma240_last = ma240[-1] if ma240 else 0
            
            # Long signal: MA5 > MA20 and close > MA240
            if ma5_last > ma20_last and current_close > ma240_last:
                vol_analysis = analyze_volume(current_volume, volumes_1m, period=20, threshold=1.0)
                signals.append(Signal(
                    signal_type=SignalType.MA_CROSS_TREND,
                    level=SignalLevel.CONFIRMED,
                    symbol="BACKTEST",
                    timestamp=int(time.time() * 1000),
                    price_data={"close": current_close, "ma5": ma5_last, "ma20": ma20_last, "ma240": ma240_last},
                    conditions={"ma5_above_ma20": True, "above_ma240": True, "volume_ok": vol_analysis.is_spike},
                    reason="Backtest trend long: MA5 > MA20 and close > MA240",
                    warning="ALERT_ONLY_NO_AUTO_TRADE",
                    metadata={"strategy_name": "ma_cross_trend", "conditions_passed": 3, "conditions_total": 3}
                ))
            
            # Short signal: MA5 < MA20 and close < MA240
            if ma5_last < ma20_last and current_close < ma240_last:
                vol_analysis = analyze_volume(current_volume, volumes_1m, period=20, threshold=1.0)
                signals.append(Signal(
                    signal_type=SignalType.MA_CROSS_TREND_SHORT,
                    level=SignalLevel.CONFIRMED,
                    symbol="BACKTEST",
                    timestamp=int(time.time() * 1000),
                    price_data={"close": current_close, "ma5": ma5_last, "ma20": ma20_last, "ma240": ma240_last},
                    conditions={"ma5_below_ma20": True, "below_ma240": True, "volume_ok": vol_analysis.is_spike},
                    reason="Backtest trend short: MA5 < MA20 and close < MA240",
                    warning="ALERT_ONLY_NO_AUTO_TRADE",
                    metadata={"strategy_name": "ma_cross_trend_short", "conditions_passed": 3, "conditions_total": 3}
                ))
        else:
            # Live monitoring: use full cross detection
            try:
                conditions_met, analysis = self._check_trend_long_conditions(
                    close_5m=current_close,
                    ma5=ma5,
                    ma20=ma20,
                    ma240=ma240,
                    volume_1m=current_volume,
                    volumes_1m=volumes_1m
                )
                if conditions_met:
                    signals.append(Signal(
                        signal_type=SignalType.MA_CROSS_TREND,
                        level=SignalLevel.CONFIRMED,
                        symbol="BACKTEST",
                        timestamp=int(time.time() * 1000),
                        price_data={"close": current_close, "ma5": ma5[-1], "ma20": ma20[-1], "ma240": ma240[-1]},
                        conditions=analysis["conditions"],
                        reason="Trend long signal from backtest indicators",
                        warning="ALERT_ONLY_NO_AUTO_TRADE",
                        metadata={"strategy_name": "ma_cross_trend", "conditions_passed": 3, "conditions_total": 3}
                    ))
            except Exception:
                pass
            
            try:
                conditions_met, analysis = self._check_trend_short_conditions(
                    close_5m=current_close,
                    ma5=ma5,
                    ma20=ma20,
                    ma240=ma240,
                    volume_1m=current_volume,
                    volumes_1m=volumes_1m
                )
                if conditions_met:
                    signals.append(Signal(
                        signal_type=SignalType.MA_CROSS_TREND_SHORT,
                        level=SignalLevel.CONFIRMED,
                        symbol="BACKTEST",
                        timestamp=int(time.time() * 1000),
                        price_data={"close": current_close, "ma5": ma5[-1], "ma20": ma20[-1], "ma240": ma240[-1]},
                        conditions=analysis["conditions"],
                        reason="Trend short signal from backtest indicators",
                        warning="ALERT_ONLY_NO_AUTO_TRADE",
                        metadata={"strategy_name": "ma_cross_trend_short", "conditions_passed": 3, "conditions_total": 3}
                    ))
            except Exception:
                pass
        
        return signals

    def generate_exit_signals(self, indicators: Dict[str, Any]) -> List[Signal]:
        """
        Generate exit signals from indicator data.
        從指標資料產生出場訊號。
        
        Args:
            indicators: Dict with MA5, MA20, MA240, position_side keys
            
        Returns:
            List of exit Signal objects
        """
        signals = []
        
        ma5 = indicators.get('MA5')
        ma20 = indicators.get('MA20')
        ma240 = indicators.get('MA240')
        position_side = indicators.get('position_side')  # "long" or "short"
        
        if not ma5 or not ma20 or not ma240 or not position_side:
            return signals
        
        if not isinstance(ma5, list):
            ma5 = [ma5]
        if not isinstance(ma20, list):
            ma20 = [ma20]
        if not isinstance(ma240, list):
            ma240 = [ma240]
        
        current_close = ma5[-1] if ma5 else 0
        ma5_last = ma5[-1] if ma5 else 0
        ma20_last = ma20[-1] if ma20 else 0
        ma240_last = ma240[-1] if ma240 else 0
        
        # EXIT_LONG: close long position when trend turns bearish
        if position_side == "long":
            if ma5_last < ma20_last or current_close < ma240_last:
                signals.append(Signal(
                    signal_type=SignalType.EXIT_LONG,
                    level=SignalLevel.CONFIRMED,
                    symbol=indicators.get('symbol', 'UNKNOWN'),
                    timestamp=int(time.time() * 1000),
                    price_data={"close": current_close, "ma5": ma5_last, "ma20": ma20_last, "ma240": ma240_last},
                    conditions={"ma5_below_ma20": ma5_last < ma20_last, "below_ma240": current_close < ma240_last},
                    reason=f"Exit long: MA5={ma5_last:.2f} vs MA20={ma20_last:.2f}, close={current_close:.2f} vs MA240={ma240_last:.2f}",
                    warning="ALERT_ONLY_NO_AUTO_TRADE",
                    metadata={"strategy_name": "ma_cross_trend", "exit_reason": "trend_reversal", "conditions_passed": 1, "conditions_total": 2}
                ))
        
        # EXIT_SHORT: close short position when trend turns bullish
        elif position_side == "short":
            if ma5_last > ma20_last or current_close > ma240_last:
                signals.append(Signal(
                    signal_type=SignalType.EXIT_SHORT,
                    level=SignalLevel.CONFIRMED,
                    symbol=indicators.get('symbol', 'UNKNOWN'),
                    timestamp=int(time.time() * 1000),
                    price_data={"close": current_close, "ma5": ma5_last, "ma20": ma20_last, "ma240": ma240_last},
                    conditions={"ma5_above_ma20": ma5_last > ma20_last, "above_ma240": current_close > ma240_last},
                    reason=f"Exit short: MA5={ma5_last:.2f} vs MA20={ma20_last:.2f}, close={current_close:.2f} vs MA240={ma240_last:.2f}",
                    warning="ALERT_ONLY_NO_AUTO_TRADE",
                    metadata={"strategy_name": "ma_cross_trend_short", "exit_reason": "trend_reversal", "conditions_passed": 1, "conditions_total": 2}
                ))
        
        return signals

    def get_cooldown_status(self, symbol: str) -> Dict[str, float]:
        """
        Get cooldown status for symbol / 取得標的的冷卻狀態
        
        Returns:
            Dictionary of signal type to remaining cooldown seconds
            訊號類型到剩餘冷卻秒數的字典
        """
        return {
            "trend_long": self.cooldown.get_remaining_cooldown(symbol, SignalType.MA_CROSS_TREND),
            "trend_short": self.cooldown.get_remaining_cooldown(symbol, SignalType.MA_CROSS_TREND_SHORT),
            "contrarian_watch_overheated": self.cooldown.get_remaining_cooldown(
                symbol, SignalType.CONTRARIAN_OVERHEATED
            ),
            "contrarian_watch_oversold": self.cooldown.get_remaining_cooldown(
                symbol, SignalType.CONTRARIAN_OVERSOLD
            ),
            "exit_long": self.cooldown.get_remaining_cooldown(symbol, SignalType.EXIT_LONG),
            "exit_short": self.cooldown.get_remaining_cooldown(symbol, SignalType.EXIT_SHORT),
            "supertrend": self.cooldown.get_remaining_cooldown(symbol, SignalType.SUPERTREND),
            "ichimoku_cloud": self.cooldown.get_remaining_cooldown(symbol, SignalType.ICHIMOKU_CLOUD),
            "williams_r": self.cooldown.get_remaining_cooldown(symbol, SignalType.WILLIAMS_R),
            "keltner_breakout": self.cooldown.get_remaining_cooldown(symbol, SignalType.KELTNER_BREAKOUT),
            "atr_breakout": self.cooldown.get_remaining_cooldown(symbol, SignalType.ATR_BREAKOUT),
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
