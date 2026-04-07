"""
Indicator Calculator Module
指標計算模組

BTC/ETH Monitoring System - Indicator Layer
BTC/ETH 監測系統 - 指標層

This module provides technical indicator calculations for the monitoring system.
本模組提供監測系統的技術指標計算。

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-06
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum


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
    threshold: float = 1.5  # Changed from 2.0 to 1.5 per T-032


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
    period: int = 20,
    threshold: float = 2.0
) -> VolumeAnalysisResult:
    """
    Analyze current volume against average / 分析當前成交量相對於平均值
    
    Args:
        current_volume: Current period volume / 當前期間成交量
        volumes: Historical volume data / 歷史成交量資料
        period: Average period / 平均週期
        threshold: Spike threshold multiplier / 爆增閾值倍數
        
    Returns:
        Volume analysis result / 成交量分析結果
        
    Example:
        >>> volumes = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
        >>> result = analyze_volume(25, volumes, period=10, threshold=2.0)
        >>> result.is_spike
        True  # 25 > 10 * 2.0
    """
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
