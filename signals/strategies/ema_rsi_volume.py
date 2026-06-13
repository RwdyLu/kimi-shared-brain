"""
Composite EMA + RSI + Volume Strategy
EMA交叉 + RSI過濾 + 成交量確認 複合策略

A proven Freqtrade-style composite trend strategy ported to
the project's signal engine format.

References:
- Freqtrade EMA crossover strategies (github.com/freqtrade/freqtrade)
- "Trading Systems and Methods" by Perry Kaufman (EMA trend + RSI filter)
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

from signals.strategies import register
from signals.engine import Signal, SignalType, SignalLevel


class Direction(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class IndicatorSet:
    """Normalized indicator set required by the composite strategy."""
    closes: List[float]
    volumes: Optional[List[float]] = None
    highs: Optional[List[float]] = None
    lows: Optional[List[float]] = None
    ema_fast: Optional[List[float]] = None
    ema_slow: Optional[List[float]] = None
    rsi: Optional[List[float]] = None
    ma_trend: Optional[List[float]] = None  # e.g. MA100/MA200


def _compute_ema(values: List[float], period: int) -> List[float]:
    """Compute EMA using smoothing factor alpha = 2/(period+1)."""
    if not values or len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(alpha * v + (1 - alpha) * ema[-1])
    return ema


def _compute_rsi(closes: List[float], period: int = 14) -> List[float]:
    """Compute RSI series from close prices."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    rsis: List[float] = []
    gains = [max(d, 0.0) for d in deltas[:period]]
    losses = [abs(min(d, 0.0)) for d in deltas[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        rsis.append(100.0)
    else:
        rsis.append(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)))
    for i in range(period, len(deltas)):
        gain = max(deltas[i], 0.0)
        loss = abs(min(deltas[i], 0.0))
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rsis.append(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)))
    # Pad front so len(rsis) == len(closes)
    padding = [50.0] * (len(closes) - len(rsis))
    return padding + rsis


def _check_ema_cross(
    ema_fast: List[float],
    ema_slow: List[float],
    direction: Direction
) -> bool:
    """Detect EMA crossover. Returns True on the bar of the cross."""
    if len(ema_fast) < 2 or len(ema_slow) < 2:
        return False
    prev_fast = ema_fast[-2]
    prev_slow = ema_slow[-2]
    curr_fast = ema_fast[-1]
    curr_slow = ema_slow[-1]
    if direction == Direction.LONG:
        return curr_fast > curr_slow and prev_fast <= prev_slow
    return curr_fast < curr_slow and prev_fast >= prev_slow


def _check_volume_confirmed(
    volumes: List[float],
    multiplier: float = 1.2,
    lookback: int = 20
) -> bool:
    """Check if current volume is above the recent average."""
    if len(volumes) < 2:
        return False
    recent = volumes[-lookback:] if len(volumes) >= lookback else volumes[:-1]
    if not recent:
        return False
    avg_vol = sum(recent) / len(recent)
    if avg_vol == 0:
        return False
    return volumes[-1] >= avg_vol * multiplier


def _build_composite_signal(
    symbol: str,
    direction: Direction,
    price: float,
    ema_fast_period: int,
    ema_slow_period: int,
    rsi_period: int,
    rsi_threshold: float,
    volume_multiplier: float,
    conditions: Dict[str, Any],
) -> Signal:
    """Build a Signal object for the composite strategy."""
    if direction == Direction.LONG:
        signal_type = SignalType.MA_CROSS_TREND
        reason = f"Composite LONG: EMA{ema_fast_period} cross above EMA{ema_slow_period} + RSI ok + volume confirmed"
    else:
        signal_type = SignalType.MA_CROSS_TREND_SHORT
        reason = f"Composite SHORT: EMA{ema_fast_period} cross below EMA{ema_slow_period} + RSI ok + volume confirmed"

    return Signal(
        signal_type=signal_type,
        level=SignalLevel.CONFIRMED,
        symbol=symbol,
        timestamp=int(__import__("time").time() * 1000),
        price_data={"close": price},
        conditions=conditions,
        reason=reason,
        warning="ALERT_ONLY_NO_AUTO_TRADE",
        metadata={
            "strategy_name": f"composite_ema_rsi_vol_{direction.value}",
            "ema_fast_period": ema_fast_period,
            "ema_slow_period": ema_slow_period,
            "rsi_period": rsi_period,
            "rsi_threshold": rsi_threshold,
            "volume_multiplier": volume_multiplier,
            "conditions_passed": sum(1 for v in conditions.values() if v),
            "conditions_total": len(conditions),
        },
    )


@register("composite_ema_rsi_volume")
def evaluate(
    symbol: str,
    closes: List[float],
    volumes: Optional[List[float]] = None,
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    ema_fast: Optional[List[float]] = None,
    ema_slow: Optional[List[float]] = None,
    rsi: Optional[List[float]] = None,
    ma_trend: Optional[List[float]] = None,
    direction: str = "long",
    parameters: Optional[Dict[str, Any]] = None,
) -> Optional[Signal]:
    """
    Evaluate the composite EMA+RSI+Volume strategy.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT")
        closes: List of close prices
        volumes: List of volumes (optional)
        highs: List of highs (optional)
        lows: List of lows (optional)
        ema_fast: Pre-computed EMA fast series (optional)
        ema_slow: Pre-computed EMA slow series (optional)
        rsi: Pre-computed RSI series (optional)
        ma_trend: Pre-computed trend MA series (optional)
        direction: "long" or "short"
        parameters: Strategy parameters override

    Returns:
        Signal if all conditions pass, None otherwise
    """
    params = parameters or {}
    ema_fast_period = params.get("ema_fast_period", 8)
    ema_slow_period = params.get("ema_slow_period", 21)
    rsi_period = params.get("rsi_period", 14)
    volume_multiplier = params.get("volume_multiplier", 1.2)
    rsi_overbought = params.get("rsi_overbought", 70)
    rsi_oversold = params.get("rsi_oversold", 30)

    dir_enum = Direction.LONG if direction.lower() == "long" else Direction.SHORT

    min_bars = max(ema_slow_period, rsi_period) + 5
    if len(closes) < min_bars:
        return None

    # Compute or use provided EMA
    if ema_fast is None:
        ema_fast = _compute_ema(closes, ema_fast_period)
    if ema_slow is None:
        ema_slow = _compute_ema(closes, ema_slow_period)

    if len(ema_fast) < 2 or len(ema_slow) < 2:
        return None

    # 1. EMA Crossover check
    ema_cross = _check_ema_cross(ema_fast, ema_slow, dir_enum)

    # 2. RSI filter
    if rsi is None:
        rsi = _compute_rsi(closes, rsi_period)
    if not rsi:
        return None
    current_rsi = rsi[-1]
    rsi_ok = False
    if dir_enum == Direction.LONG:
        rsi_ok = current_rsi < rsi_overbought
    else:
        rsi_ok = current_rsi > rsi_oversold

    # 3. Volume confirmation
    volume_ok = True
    if volumes and len(volumes) >= 10:
        volume_ok = _check_volume_confirmed(volumes, volume_multiplier)

    # 4. Trend alignment (price above/below long-term MA)
    trend_ok = True
    if ma_trend is not None and len(ma_trend) > 0:
        if dir_enum == Direction.LONG:
            trend_ok = closes[-1] > ma_trend[-1]
        else:
            trend_ok = closes[-1] < ma_trend[-1]
    elif len(closes) >= 100:
        ma_trend_proxy = sum(closes[-100:]) / 100
        if dir_enum == Direction.LONG:
            trend_ok = closes[-1] > ma_trend_proxy
        else:
            trend_ok = closes[-1] < ma_trend_proxy

    conditions = {
        "ema_cross": ema_cross,
        "rsi_ok": rsi_ok,
        "volume_confirmed": volume_ok,
        "trend_aligned": trend_ok,
    }

    if all(conditions.values()):
        return _build_composite_signal(
            symbol=symbol,
            direction=dir_enum,
            price=closes[-1],
            ema_fast_period=ema_fast_period,
            ema_slow_period=ema_slow_period,
            rsi_period=rsi_period,
            rsi_threshold=rsi_overbought if dir_enum == Direction.LONG else rsi_oversold,
            volume_multiplier=volume_multiplier,
            conditions=conditions,
        )
    return None
