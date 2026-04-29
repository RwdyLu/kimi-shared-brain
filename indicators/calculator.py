"""
Indicator Calculator Module
指標計算模組

BTC/ETH Monitoring System - Indicator Layer
BTC/ETH 監測系統 - 指標層

This module provides technical indicator calculations for the monitoring system.
本模組提供監測系統的技術指標計算。

Author: kimiclaw_bot
Version: 1.1.0
Date: 2026-04-07
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

# Import config loader / 匯入配置載入器
import sys
sys.path.insert(0, '/tmp/kimi-shared-brain')
from config.loader import get_indicator_params, get_volume_threshold


class CrossType(Enum):
    """MA cross types / MA 交叉類型"""
    CROSS_ABOVE = "cross_above"  # Short crosses above long / 短期上穿長期
    CROSS_BELOW = "cross_below"  # Short crosses below long / 短期下穿長期
    NO_CROSS = "no_cross"        # No cross detected / 無交叉


class CandleColor(Enum):
    """Candle color / K 線顏色"""
    RED = "red"      # Close < Open / 收盤 < 開盤
    GREEN = "green"  # Close > Open / 收盤 > 開盤
    NEUTRAL = "neutral"  # Close == Open / 收盤 == 開盤


@dataclass
class MACrossResult:
    """MA cross detection result / MA 交叉檢測結果"""
    cross_type: CrossType
    short_ma_value: float
    long_ma_value: float
    prev_short_ma: float
    prev_long_ma: float
    timestamp: Optional[int] = None


@dataclass
class VolumeAnalysisResult:
    """Volume analysis result / 成交量分析結果"""
    current_volume: float
    avg_volume: float
    ratio: float
    is_spike: bool
    threshold: float = None  # Loaded from config / 從配置載入
    
    def __post_init__(self):
        """Set default threshold from config if not provided"""
        if self.threshold is None:
            try:
                self.threshold = get_volume_threshold()
            except:
                self.threshold = 1.5  # Fallback default


@dataclass
class CandlePatternResult:
    """Candle pattern detection result / K 線型態檢測結果"""
    pattern_detected: bool
    pattern_type: str  # "consecutive_red", "consecutive_green", "none"
    consecutive_count: int
    candles_analyzed: int


# =============================================================================
# Moving Average Calculations / 移動平均計算
# =============================================================================

def calculate_sma(values: List[float], period: int) -> List[float]:
    """
    Calculate Simple Moving Average / 計算簡單移動平均
    
    Args:
        values: List of numeric values / 數值列表
        period: MA period / MA 週期
        
    Returns:
        List of SMA values / SMA 值列表
        
    Example:
        >>> prices = [10, 11, 12, 13, 14, 15]
        >>> calculate_sma(prices, 3)
        [11.0, 12.0, 13.0, 14.0]
    """
    if len(values) < period:
        return []
    
    sma = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        sma.append(sum(window) / period)
    
    return sma


def calculate_ma5(closes: List[float]) -> List[float]:
    """
    Calculate 5-period MA for 5m timeframe / 計算 5m 時間框架的 5 週期 MA
    
    Args:
        closes: List of closing prices / 收盤價列表
        
    Returns:
        List of MA5 values / MA5 值列表
    """
    return calculate_sma(closes, 5)


def calculate_ma20(closes: List[float]) -> List[float]:
    """
    Calculate 20-period MA for 5m timeframe / 計算 5m 時間框架的 20 週期 MA
    
    Args:
        closes: List of closing prices / 收盤價列表
        
    Returns:
        List of MA20 values / MA20 值列表
    """
    return calculate_sma(closes, 20)


def calculate_ma240(closes: List[float]) -> List[float]:
    """
    Calculate 240-period MA for 5m timeframe / 計算 5m 時間框架的 240 週期 MA
    
    Args:
        closes: List of closing prices / 收盤價列表
        
    Returns:
        List of MA240 values / MA240 值列表
        
    Note:
        240 periods ≈ 20 hours of 5m data / 240 週期 ≈ 20 小時的 5m 資料
    """
    return calculate_sma(closes, 240)


# =============================================================================
# Volume Calculations / 成交量計算
# =============================================================================

def calculate_volume_sma(volumes: List[float], period: int = 20) -> float:
    """
    Calculate volume SMA / 計算成交量 SMA
    
    Args:
        volumes: List of volume values / 成交量值列表
        period: SMA period (default: 20) / SMA 週期（預設：20）
        
    Returns:
        Volume SMA value / 成交量 SMA 值
        
    Example:
        >>> volumes = [100, 110, 120, 130, 140, 150]
        >>> calculate_volume_sma(volumes, 3)
        140.0
    """
    if len(volumes) < period:
        return 0.0
    
    recent_volumes = volumes[-period:]
    return sum(recent_volumes) / period


def analyze_volume(
    current_volume: float,
    volumes: List[float],
    period: int = None,
    threshold: float = None
) -> VolumeAnalysisResult:
    """
    Analyze current volume against average / 分析當前成交量相對於平均值
    
    Args:
        current_volume: Current period volume / 當前期間成交量
        volumes: Historical volume data / 歷史成交量資料
        period: Average period (default: from config) / 平均週期（預設：從配置讀取）
        threshold: Spike threshold multiplier (default: from config) / 爆增閾值倍數（預設：從配置讀取）
        
    Returns:
        Volume analysis result / 成交量分析結果
        
    Example:
        >>> volumes = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
        >>> result = analyze_volume(25, volumes, period=10, threshold=2.0)
        >>> result.is_spike
        True  # 25 > 10 * 2.0
    """
    # Load defaults from config if not provided
    if period is None or threshold is None:
        try:
            indicator_params = get_indicator_params()
            volume_config = indicator_params.get("volume", {})
            if period is None:
                period = volume_config.get("window", 20)
            if threshold is None:
                threshold = volume_config.get("spike_threshold", 1.5)
        except:
            # Fallback defaults
            if period is None:
                period = 20
            if threshold is None:
                threshold = 1.5
    
    avg_volume = calculate_volume_sma(volumes, period)
    
    if avg_volume == 0:
        ratio = 0.0
        is_spike = False
    else:
        ratio = current_volume / avg_volume
        is_spike = ratio > threshold
    
    return VolumeAnalysisResult(
        current_volume=current_volume,
        avg_volume=avg_volume,
        ratio=ratio,
        is_spike=is_spike,
        threshold=threshold
    )


# =============================================================================
# Cross Detection / 交叉檢測
# =============================================================================

def detect_ma_cross(
    short_ma: List[float],
    long_ma: List[float],
    timestamp: Optional[int] = None
) -> MACrossResult:
    """
    Detect if short MA crossed long MA / 檢測短期 MA 是否交叉長期 MA
    
    Args:
        short_ma: Short period MA values / 短期 MA 值列表
        long_ma: Long period MA values / 長期 MA 值列表
        timestamp: Optional timestamp for the cross / 交叉的可選時間戳
        
    Returns:
        MA cross detection result / MA 交叉檢測結果
        
    Logic:
        - Cross Above: prev_short < prev_long AND curr_short >= curr_long
        - Cross Below: prev_short > prev_long AND curr_short <= curr_long
        
    Example:
        >>> short_ma = [90, 95, 100, 105]
        >>> long_ma = [100, 100, 100, 100]
        >>> result = detect_ma_cross(short_ma, long_ma)
        >>> result.cross_type == CrossType.CROSS_ABOVE
        True
    """
    if len(short_ma) < 2 or len(long_ma) < 2:
        return MACrossResult(
            cross_type=CrossType.NO_CROSS,
            short_ma_value=short_ma[-1] if short_ma else 0.0,
            long_ma_value=long_ma[-1] if long_ma else 0.0,
            prev_short_ma=0.0,
            prev_long_ma=0.0,
            timestamp=timestamp
        )
    
    prev_short = short_ma[-2]
    prev_long = long_ma[-2]
    curr_short = short_ma[-1]
    curr_long = long_ma[-1]
    
    # Detect cross above / 檢測上穿
    if prev_short < prev_long and curr_short >= curr_long:
        cross_type = CrossType.CROSS_ABOVE
    # Detect cross below / 檢測下穿
    elif prev_short > prev_long and curr_short <= curr_long:
        cross_type = CrossType.CROSS_BELOW
    else:
        cross_type = CrossType.NO_CROSS
    
    return MACrossResult(
        cross_type=cross_type,
        short_ma_value=curr_short,
        long_ma_value=curr_long,
        prev_short_ma=prev_short,
        prev_long_ma=prev_long,
        timestamp=timestamp
    )


def detect_ma5_ma20_cross(ma5: List[float], ma20: List[float]) -> MACrossResult:
    """
    Detect MA5 cross MA20 / 檢測 MA5 交叉 MA20
    
    Args:
        ma5: MA5 values / MA5 值列表
        ma20: MA20 values / MA20 值列表
        
    Returns:
        Cross detection result / 交叉檢測結果
    """
    return detect_ma_cross(ma5, ma20)


# =============================================================================
# Candle Pattern Detection / K 線型態檢測
# =============================================================================

def get_candle_color(open_price: float, close_price: float) -> CandleColor:
    """
    Determine candle color / 判斷 K 線顏色
    
    Args:
        open_price: Opening price / 開盤價
        close_price: Closing price / 收盤價
        
    Returns:
        Candle color / K 線顏色
        
    Example:
        >>> get_candle_color(100, 95)
        CandleColor.RED
        >>> get_candle_color(100, 105)
        CandleColor.GREEN
    """
    if close_price < open_price:
        return CandleColor.RED
    elif close_price > open_price:
        return CandleColor.GREEN
    else:
        return CandleColor.NEUTRAL


def is_red_candle(open_price: float, close_price: float) -> bool:
    """
    Check if candle is red / 檢查是否為紅 K
    
    Args:
        open_price: Opening price / 開盤價
        close_price: Closing price / 收盤價
        
    Returns:
        True if red candle / 若是紅 K 則為 True
    """
    return close_price < open_price


def is_green_candle(open_price: float, close_price: float) -> bool:
    """
    Check if candle is green / 檢查是否為綠 K
    
    Args:
        open_price: Opening price / 開盤價
        close_price: Closing price / 收盤價
        
    Returns:
        True if green candle / 若是綠 K 則為 True
    """
    return close_price > open_price


def detect_consecutive_candles(
    candles: List[Dict[str, Any]],
    n: int = 4,
    candle_type: str = "red"
) -> CandlePatternResult:
    """
    Detect N consecutive candles of same type / 檢測 N 根連續同色 K 線
    
    Args:
        candles: List of candle data with 'open' and 'close' keys /
                 K 線資料列表，需包含 'open' 和 'close' 鍵
        n: Number of consecutive candles to detect / 要檢測的連續 K 線數量
        candle_type: 'red' or 'green' / 'red' 或 'green'
        
    Returns:
        Pattern detection result / 型態檢測結果
        
    Example:
        >>> candles = [
        ...     {"open": 100, "close": 95},
        ...     {"open": 95, "close": 90},
        ...     {"open": 90, "close": 85},
        ...     {"open": 85, "close": 80}
        ... ]
        >>> result = detect_consecutive_candles(candles, n=4, candle_type="red")
        >>> result.pattern_detected
        True
    """
    if len(candles) < n:
        return CandlePatternResult(
            pattern_detected=False,
            pattern_type="none",
            consecutive_count=0,
            candles_analyzed=len(candles)
        )
    
    # Get last N candles / 取得最後 N 根 K 線
    recent_candles = candles[-n:]
    
    # Check each candle / 檢查每根 K 線
    for candle in recent_candles:
        try:
            open_price = float(candle["open"])
            close_price = float(candle["close"])
        except (KeyError, ValueError, TypeError):
            return CandlePatternResult(
                pattern_detected=False,
                pattern_type="none",
                consecutive_count=0,
                candles_analyzed=len(candles)
            )
        
        if candle_type == "red":
            if not is_red_candle(open_price, close_price):
                return CandlePatternResult(
                    pattern_detected=False,
                    pattern_type="none",
                    consecutive_count=0,
                    candles_analyzed=len(candles)
                )
        elif candle_type == "green":
            if not is_green_candle(open_price, close_price):
                return CandlePatternResult(
                    pattern_detected=False,
                    pattern_type="none",
                    consecutive_count=0,
                    candles_analyzed=len(candles)
                )
    
    # All N candles match the type / 所有 N 根 K 線符合類型
    pattern_type = f"consecutive_{candle_type}"
    return CandlePatternResult(
        pattern_detected=True,
        pattern_type=pattern_type,
        consecutive_count=n,
        candles_analyzed=len(candles)
    )


def detect_four_consecutive_red(candles: List[Dict[str, Any]]) -> CandlePatternResult:
    """
    Detect 4 consecutive red candles (15m overheated signal) /
    檢測 4 根連續紅 K（15m 過熱訊號）
    
    Args:
        candles: 15m candle data / 15m K 線資料
        
    Returns:
        Pattern result / 型態結果
        
    Note:
        This is a contrarian watch signal - for observation only.
        這是逆勢觀察訊號 - 僅供觀察。
    """
    return detect_consecutive_candles(candles, n=4, candle_type="red")


def detect_four_consecutive_green(candles: List[Dict[str, Any]]) -> CandlePatternResult:
    """
    Detect 4 consecutive green candles (15m oversold signal) /
    檢測 4 根連續綠 K（15m 超賣訊號）
    
    Args:
        candles: 15m candle data / 15m K 線資料
        
    Returns:
        Pattern result / 型態結果
        
    Note:
        This is a contrarian watch signal - for observation only.
        這是逆勢觀察訊號 - 僅供觀察。
    """
    return detect_consecutive_candles(candles, n=4, candle_type="green")


# =============================================================================
# High-Level Analysis Functions / 高階分析函式
# =============================================================================

def analyze_5m_trend_conditions(
    closes: List[float],
    ma240: Optional[List[float]] = None
) -> Dict[str, Any]:
    """
    Analyze 5m timeframe trend conditions / 分析 5m 時間框架趨勢條件
    
    Args:
        closes: List of 5m closing prices / 5m 收盤價列表
        ma240: Pre-calculated MA240 (optional) / 預先計算的 MA240（可選）
        
    Returns:
        Dictionary with trend analysis / 包含趨勢分析的字典
        
    Analysis includes:
        - MA5, MA20, MA240 values / MA5、MA20、MA240 值
        - Current position vs MA240 / 當前位置相對 MA240
        - Cross detection / 交叉檢測
    """
    if len(closes) < 240:
        return {
            "error": "Insufficient data (need 240 candles)",
            "candles_available": len(closes),
            "candles_required": 240
        }
    
    # Calculate MAs / 計算 MA
    ma5 = calculate_ma5(closes)
    ma20 = calculate_ma20(closes)
    
    if ma240 is None:
        ma240 = calculate_ma240(closes)
    
    if not ma5 or not ma20 or not ma240:
        return {
            "error": "Failed to calculate MAs",
            "ma5_available": len(ma5),
            "ma20_available": len(ma20),
            "ma240_available": len(ma240)
        }
    
    current_close = closes[-1]
    current_ma5 = ma5[-1]
    current_ma20 = ma20[-1]
    current_ma240 = ma240[-1]
    
    # Position relative to MA240 / 相對 MA240 的位置
    above_ma240 = current_close > current_ma240
    below_ma240 = current_close < current_ma240
    
    # Cross detection / 交叉檢測
    cross_result = detect_ma5_ma20_cross(ma5, ma20)
    
    return {
        "current_close": current_close,
        "ma5": current_ma5,
        "ma20": current_ma20,
        "ma240": current_ma240,
        "above_ma240": above_ma240,
        "below_ma240": below_ma240,
        "cross_result": cross_result,
        "ma5_history": ma5,
        "ma20_history": ma20,
        "ma240_history": ma240
    }


def analyze_volume_conditions(
    current_volume: float,
    volumes: List[float],
    period: int = 20,
    threshold: float = 2.0
) -> VolumeAnalysisResult:
    """
    Analyze volume conditions for signal confirmation /
    分析成交量條件以確認訊號
    
    Args:
        current_volume: Current 1m volume / 當前 1m 成交量
        volumes: Historical 1m volumes / 歷史 1m 成交量
        period: Average period / 平均週期
        threshold: Spike threshold / 爆增閾值
        
    Returns:
        Volume analysis result / 成交量分析結果
    """
    return analyze_volume(current_volume, volumes, period, threshold)


def analyze_15m_contrarian_conditions(
    candles_15m: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Analyze 15m timeframe for contrarian watch signals /
    分析 15m 時間框架的逆勢觀察訊號
    
    Args:
        candles_15m: 15m candle data / 15m K 線資料
        
    Returns:
        Dictionary with contrarian analysis / 包含逆勢分析的字典
        
    Note:
        These are WATCH-ONLY signals, not execution signals.
        這些是僅觀察訊號，非執行訊號。
    """
    overheated_result = detect_four_consecutive_red(candles_15m)
    oversold_result = detect_four_consecutive_green(candles_15m)
    
    return {
        "overheated": overheated_result,
        "oversold": oversold_result,
        "any_pattern_detected": (
            overheated_result.pattern_detected or 
            oversold_result.pattern_detected
        ),
        "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
    }


# =============================================================================
# Convenience Functions / 便利函式
# =============================================================================

def get_latest_ma_values(
    closes: List[float]
) -> Dict[str, Optional[float]]:
    """
    Get latest MA values / 取得最新 MA 值
    
    Args:
        closes: List of closing prices / 收盤價列表
        
    Returns:
        Dictionary with latest MA values / 包含最新 MA 值的字典
    """
    ma5_list = calculate_ma5(closes)
    ma20_list = calculate_ma20(closes)
    ma240_list = calculate_ma240(closes) if len(closes) >= 240 else []
    
    return {
        "ma5": ma5_list[-1] if ma5_list else None,
        "ma20": ma20_list[-1] if ma20_list else None,
        "ma240": ma240_list[-1] if ma240_list else None,
        "close": closes[-1] if closes else None
    }


# =============================================================================
# Advanced Indicators for P2 Strategies / P2 策略進階指標
# =============================================================================

def calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
    """
    Calculate RSI / 計算 RSI
    
    Args:
        closes: List of closing prices / 收盤價列表
        period: RSI period (default: 14) / RSI 週期（預設：14）
        
    Returns:
        List of RSI values / RSI 值列表
    """
    if len(closes) < period + 1:
        return []
    
    rsi_values = []
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    
    # First average gain/loss
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # First RSI
    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100.0 - (100.0 / (1 + rs)))
    
    # Smoothed RSI
    for i in range(period, len(gains)):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100.0 - (100.0 / (1 + rs)))
    
    return rsi_values


def calculate_tema(closes: List[float], period: int = 9) -> List[float]:
    """
    Calculate TEMA (Triple Exponential Moving Average) / 計算 TEMA
    
    TEMA = 3*EMA1 - 3*EMA2 + EMA3
    where EMA1 = EMA of closes, EMA2 = EMA of EMA1, EMA3 = EMA of EMA2
    
    Args:
        closes: List of closing prices / 收盤價列表
        period: TEMA period (default: 9) / TEMA 週期（預設：9）
        
    Returns:
        List of TEMA values / TEMA 值列表
    """
    def _ema(values: List[float], period: int) -> List[float]:
        if len(values) < period:
            return []
        multiplier = 2.0 / (period + 1)
        ema = [sum(values[:period]) / period]
        for price in values[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema
    
    if len(closes) < period * 3:
        return []
    
    ema1 = _ema(closes, period)
    if len(ema1) < period:
        return []
    
    ema2 = _ema(ema1, period)
    if len(ema2) < period:
        return []
    
    ema3 = _ema(ema2, period)
    if len(ema3) < 1:
        return []
    
    # Align lengths - use last len(ema3) values from each
    len_ema3 = len(ema3)
    tema = []
    for i in range(len_ema3):
        e1 = ema1[-(len_ema3 - i)]
        e2 = ema2[-(len_ema3 - i)]
        e3 = ema3[i]
        tema.append(3 * e1 - 3 * e2 + e3)
    
    return tema


def calculate_stochastic(closes: List[float], highs: List[float], lows: List[float], 
                         k_period: int = 5, d_period: int = 3) -> Tuple[List[float], List[float]]:
    """
    Calculate Stochastic Oscillator (Fast K & D) / 計算隨機指標
    
    Args:
        closes: List of closing prices / 收盤價列表
        highs: List of high prices / 最高價列表
        lows: List of low prices / 最低價列表
        k_period: K period (default: 5) / K 週期
        d_period: D period (default: 3) / D 週期
        
    Returns:
        Tuple of (fastk_values, fastd_values) / (K值列表, D值列表)
    """
    if len(closes) < k_period or len(highs) < k_period or len(lows) < k_period:
        return [], []
    
    fastk_values = []
    for i in range(k_period - 1, len(closes)):
        recent_highs = highs[i - k_period + 1:i + 1]
        recent_lows = lows[i - k_period + 1:i + 1]
        highest_high = max(recent_highs)
        lowest_low = min(recent_lows)
        
        if highest_high == lowest_low:
            fastk = 50.0
        else:
            fastk = ((closes[i] - lowest_low) / (highest_high - lowest_low)) * 100
        fastk_values.append(fastk)
    
    # Fast D = SMA of Fast K
    fastd_values = []
    for i in range(d_period - 1, len(fastk_values)):
        fastd = sum(fastk_values[i - d_period + 1:i + 1]) / d_period
        fastd_values.append(fastd)
    
    return fastk_values, fastd_values


def calculate_bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, List[float]]:
    """
    Calculate Bollinger Bands / 計算布林帶
    
    Args:
        closes: List of closing prices / 收盤價列表
        period: BB period (default: 20) / BB 週期
        std_dev: Standard deviation multiplier (default: 2.0) / 標準差倍數
        
    Returns:
        Dictionary with upper, middle, lower bands / 上中下轨字典
    """
    if len(closes) < period:
        return {"upper": [], "middle": [], "lower": []}
    
    upper = []
    middle = []
    lower = []
    
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        sma = sum(window) / period
        variance = sum((x - sma) ** 2 for x in window) / period
        std = variance ** 0.5
        
        middle.append(sma)
        upper.append(sma + std_dev * std)
        lower.append(sma - std_dev * std)
    
    return {"upper": upper, "middle": middle, "lower": lower}


def calculate_sar(highs: List[float], lows: List[float], 
                  acceleration: float = 0.02, maximum: float = 0.2) -> List[float]:
    """
    Calculate Parabolic SAR / 計算拋物線 SAR
    
    Simplified implementation - works for trend confirmation.
    簡化實作 - 適用於趨勢確認。
    
    Args:
        highs: List of high prices / 最高價列表
        lows: List of low prices / 最低價列表
        acceleration: SAR acceleration factor / 加速因子
        maximum: Maximum acceleration / 最大加速因子
        
    Returns:
        List of SAR values / SAR 值列表
    """
    if len(highs) < 2 or len(lows) < 2:
        return []
    
    sar_values = []
    
    # Initialize
    af = acceleration
    ep = highs[0]
    sar = lows[0]
    long = True
    
    for i in range(1, min(len(highs), len(lows))):
        if long:
            sar = sar + af * (ep - sar)
            if lows[i] < sar:
                long = False
                sar = ep
                ep = lows[i]
                af = acceleration
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + acceleration, maximum)
        else:
            sar = sar + af * (ep - sar)
            if highs[i] > sar:
                long = True
                sar = ep
                ep = highs[i]
                af = acceleration
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + acceleration, maximum)
        
        sar_values.append(sar)
    
    return sar_values


def calculate_ht_sine(closes: List[float]) -> Dict[str, List[float]]:
    """
    Calculate Hilbert Transform SineWave / 計算希爾伯特轉換正弦波
    
    Simplified version using dominant cycle detection.
    簡化版，使用主導週期檢測。
    
    Args:
        closes: List of closing prices / 收盤價列表
        
    Returns:
        Dictionary with 'sine' and 'leadsine' lists / 包含 sine 和 leadsine 的字典
    """
    if len(closes) < 20:
        return {"sine": [], "leadsine": []}
    
    # Use detrended price oscillator as proxy for cycle
    # 使用去趨勢價格震盪器作為週期代理
    detrended = []
    for i in range(len(closes)):
        if i < 4:
            detrended.append(0)
        else:
            # 4-bar SMA detrender
            sma4 = sum(closes[max(0, i-3):i+1]) / min(4, i+1)
            detrended.append(closes[i] - sma4)
    
    # Generate sine wave from detrended values
    sine = []
    leadsine = []
    
    for i in range(len(detrended)):
        if i < 6:
            sine.append(0)
            leadsine.append(0)
            continue
        
        # Sine wave from smoothed detrended
        window = detrended[max(0, i-5):i+1]
        smoothed = sum(window) / len(window)
        
        # Normalize to -1 to 1 range
        recent = detrended[max(0, i-10):i+1]
        if recent:
            max_val = max(abs(x) for x in recent) if any(recent) else 1
            normalized = smoothed / max_val if max_val > 0 else 0
        else:
            normalized = 0
        
        sine.append(normalized)
        
        # Lead sine = phase shifted by ~45 degrees (1 bar ahead)
        if i > 0:
            leadsine.append((normalized + sine[i-1]) / 2 if sine[i-1] != 0 else normalized)
        else:
            leadsine.append(normalized)
    
    return {"sine": sine, "leadsine": leadsine}


def calculate_ema(closes: List[float], period: int) -> List[float]:
    """
    Calculate EMA (Exponential Moving Average) / 計算 EMA
    
    Args:
        closes: List of closing prices / 收盤價列表
        period: EMA period / EMA 週期
        
    Returns:
        List of EMA values / EMA 值列表
    """
    if len(closes) < period:
        return []
    
    multiplier = 2.0 / (period + 1)
    ema = [sum(closes[:period]) / period]
    
    for price in closes[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    
    return ema


def detect_ema_cross(ema_fast: List[float], ema_slow: List[float]) -> CrossType:
    """
    Detect EMA cross / 檢測 EMA 交叉
    
    Args:
        ema_fast: Fast EMA values / 快線 EMA 值
        ema_slow: Slow EMA values / 慢線 EMA 值
        
    Returns:
        CrossType / 交叉類型
    """
    if len(ema_fast) < 2 or len(ema_slow) < 2:
        return CrossType.NO_CROSS
    
    # Check last two values
    fast_now = ema_fast[-1]
    slow_now = ema_slow[-1]
    fast_prev = ema_fast[-2]
    slow_prev = ema_slow[-2]
    
    # Cross above: fast was below, now above
    if fast_prev <= slow_prev and fast_now > slow_now:
        return CrossType.CROSS_ABOVE
    
    # Cross below: fast was above, now below
    if fast_prev >= slow_prev and fast_now < slow_now:
        return CrossType.CROSS_BELOW
    
    return CrossType.NO_CROSS


def calculate_price_channel(highs: List[float], lows: List[float], period: int = 20) -> Dict[str, List[float]]:
    """
    Calculate Price Channel / 計算價格通道
    
    Args:
        highs: List of high prices / 最高價列表
        lows: List of low prices / 最低價列表
        period: Channel period (default: 20) / 通道週期
        
    Returns:
        Dictionary with upper, lower channels / 上軌下軌字典
    """
    if len(highs) < period or len(lows) < period:
        return {"upper": [], "lower": []}
    
    upper = []
    lower = []
    
    for i in range(period - 1, len(highs)):
        recent_highs = highs[i - period + 1:i + 1]
        recent_lows = lows[i - period + 1:i + 1]
        upper.append(max(recent_highs))
        lower.append(min(recent_lows))
    
    return {"upper": upper, "lower": lower}


def detect_volume_spike(volumes: List[float], current_idx: int, period: int = 20, multiplier: float = 1.5) -> bool:
    """
    Detect volume spike / 檢測成交量突增
    
    Args:
        volumes: List of volume values / 成交量列表
        current_idx: Current index / 當前索引
        period: Average period (default: 20) / 平均週期
        multiplier: Spike threshold (default: 1.5) / 突增閾值
        
    Returns:
        True if volume spike detected / 是否有成交量突增
    """
    if current_idx < period:
        return False
    
    recent_volumes = volumes[current_idx - period:current_idx]
    avg_volume = sum(recent_volumes) / len(recent_volumes)
    current_volume = volumes[current_idx]
    
    if avg_volume == 0:
        return False
    
    return current_volume > avg_volume * multiplier


def detect_momentum_divergence(closes: List[float], rsi_values: List[float], lookback: int = 14) -> bool:
    """
    Detect bullish momentum divergence / 檢測底背離
    
    Bullish divergence: price makes lower low, RSI makes higher low
    底背離：價格創新低但 RSI 未創新低
    
    Args:
        closes: List of closing prices / 收盤價列表
        rsi_values: List of RSI values / RSI 值列表
        lookback: Lookback period (default: 14) / 回顧週期
        
    Returns:
        True if bullish divergence detected / 是否檢測到底背離
    """
    if len(closes) < lookback * 2 or len(rsi_values) < lookback * 2:
        return False
    
    # Find recent low and previous low in price
    recent_closes = closes[-lookback:]
    previous_closes = closes[-lookback*2:-lookback]
    
    recent_rsi = rsi_values[-lookback:]
    previous_rsi = rsi_values[-lookback*2:-lookback]
    
    price_lower_low = min(recent_closes) < min(previous_closes)
    rsi_higher_low = min(recent_rsi) > min(previous_rsi)
    
    return price_lower_low and rsi_higher_low


# Example usage / 使用範例
if __name__ == "__main__":
    print("Indicator Calculator Module")
    print("指標計算模組")
    print("=" * 40)
    
    # Example: SMA calculation / 範例：SMA 計算
    prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    
    print(f"\nPrices: {prices}")
    print(f"MA5: {calculate_ma5(prices)}")
    print(f"MA20: {calculate_ma20(prices[:20])}")
    
    # Example: Volume analysis / 範例：成交量分析
    volumes = [10, 10, 10, 10, 10] * 4  # 20 periods of volume 10
    result = analyze_volume(25, volumes, period=20, threshold=2.0)
    
    print(f"\nVolume Analysis:")
    print(f"  Current: {result.current_volume}")
    print(f"  Average: {result.avg_volume:.2f}")
    print(f"  Ratio: {result.ratio:.2f}x")
    print(f"  Is Spike: {result.is_spike}")
    
    # Example: Cross detection / 範例：交叉檢測
    short_ma = [90, 95, 100, 105]
    long_ma = [100, 100, 100, 100]
    cross = detect_ma_cross(short_ma, long_ma)
    
    print(f"\nCross Detection:")
    print(f"  Type: {cross.cross_type.value}")
    print(f"  Short MA: {cross.short_ma_value}")
    print(f"  Long MA: {cross.long_ma_value}")
    
    # Example: Candle pattern / 範例：K 線型態
    candles = [
        {"open": 100, "close": 95},
        {"open": 95, "close": 90},
        {"open": 90, "close": 85},
        {"open": 85, "close": 80}
    ]
    pattern = detect_four_consecutive_red(candles)
    
    print(f"\nCandle Pattern (4 red):")
    print(f"  Detected: {pattern.pattern_detected}")
    print(f"  Type: {pattern.pattern_type}")
