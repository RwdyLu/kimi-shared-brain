"""
SNR (Support & Resistance) Trading Strategy
Detects key support and resistance levels for trading signals.
"""

import json
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class SignalType(Enum):
    """Trading signal types from SNR analysis."""

    BUY_SUPPORT = "buy_support"  # Price near support - buy
    SELL_RESISTANCE = "sell_resistance"  # Price near resistance - sell
    BREAKOUT_UP = "breakout_up"  # Break resistance - trend up
    BREAKOUT_DOWN = "breakout_down"  # Break support - trend down
    NEUTRAL = "neutral"


@dataclass
class SNRLevel:
    """Single support or resistance level."""

    price: float
    type: str  # 'support' or 'resistance'
    strength: float  # 0-100, based on touches
    touch_count: int = 0
    first_seen: Optional[datetime] = None
    last_tested: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "price": self.price,
            "type": self.type,
            "strength": self.strength,
            "touch_count": self.touch_count,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_tested": self.last_tested.isoformat() if self.last_tested else None,
        }


@dataclass
class SNRSignal:
    """SNR trading signal."""

    symbol: str
    signal_type: SignalType
    price: float
    target_level: float
    stop_loss: float
    take_profit: float
    confidence: float  # 0-1
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "price": self.price,
            "target_level": self.target_level,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class SNRStrategy:
    """
    Support & Resistance trading strategy.

    Detects key levels from historical price data and generates
    trading signals when price approaches or breaks these levels.
    """

    def __init__(
        self,
        lookback_period: int = 100,
        touch_threshold: float = 0.5,  # % price must approach level
        min_touches: int = 2,
        level_spacing: float = 1.0,
    ):  # Minimum % between levels
        self.logger = logging.getLogger(__name__)

        # Parameters
        self.lookback_period = lookback_period
        self.touch_threshold = touch_threshold
        self.min_touches = min_touches
        self.level_spacing = level_spacing

        # State
        self.levels: Dict[str, List[SNRLevel]] = {}
        self.signals: List[SNRSignal] = []

        self.logger.info("SNR Strategy initialized")

    def detect_levels(self, symbol: str, highs: List[float], lows: List[float], closes: List[float]) -> List[SNRLevel]:
        """
        Detect support and resistance levels from price data.

        Args:
            symbol: Trading pair
            highs: High prices
            lows: Low prices
            closes: Close prices

        Returns:
            List of detected SNRLevel
        """
        if len(highs) < self.lookback_period:
            return []

        levels = []

        # Find local maxima (resistance)
        resistance_levels = self._find_extrema(highs, window=5, mode="max")

        # Find local minima (support)
        support_levels = self._find_extrema(lows, window=5, mode="min")

        # Cluster nearby levels
        clustered_resistance = self._cluster_levels(resistance_levels, closes[-1])
        clustered_support = self._cluster_levels(support_levels, closes[-1])

        # Create SNRLevel objects
        for price, touches in clustered_resistance:
            level = SNRLevel(
                price=price,
                type="resistance",
                strength=min(touches * 10, 100),
                touch_count=touches,
                first_seen=datetime.now() - timedelta(hours=touches),
                last_tested=datetime.now(),
            )
            levels.append(level)

        for price, touches in clustered_support:
            level = SNRLevel(
                price=price,
                type="support",
                strength=min(touches * 10, 100),
                touch_count=touches,
                first_seen=datetime.now() - timedelta(hours=touches),
                last_tested=datetime.now(),
            )
            levels.append(level)

        # Sort by strength (descending)
        levels.sort(key=lambda l: l.strength, reverse=True)

        self.levels[symbol] = levels

        self.logger.info(
            f"Detected {len(levels)} levels for {symbol}: "
            f"{len(clustered_resistance)} resistance, "
            f"{len(clustered_support)} support"
        )

        return levels

    def _find_extrema(self, data: List[float], window: int = 5, mode: str = "max") -> List[float]:
        """
        Find local extrema in price data.

        Args:
            data: Price data
            window: Lookback/lookahead window
            mode: 'max' or 'min'

        Returns:
            List of extreme prices
        """
        extrema = []
        half_window = window // 2

        for i in range(half_window, len(data) - half_window):
            segment = data[i - half_window : i + half_window + 1]

            if mode == "max":
                if data[i] == max(segment):
                    extrema.append(data[i])
            else:
                if data[i] == min(segment):
                    extrema.append(data[i])

        return extrema

    def _cluster_levels(self, prices: List[float], current_price: float) -> List[Tuple[float, int]]:
        """
        Cluster nearby price levels.

        Args:
            prices: Raw price levels
            current_price: Current market price

        Returns:
            List of (clustered_price, touch_count)
        """
        if not prices:
            return []

        # Sort prices
        sorted_prices = sorted(prices)

        # Cluster by percentage spacing
        clusters = []
        current_cluster = [sorted_prices[0]]

        for price in sorted_prices[1:]:
            # Check if within spacing threshold
            cluster_avg = sum(current_cluster) / len(current_cluster)
            if abs(price - cluster_avg) / current_price < self.level_spacing / 100:
                current_cluster.append(price)
            else:
                clusters.append(current_cluster)
                current_cluster = [price]

        clusters.append(current_cluster)

        # Create clustered levels (average price, touch count)
        return [(sum(cluster) / len(cluster), len(cluster)) for cluster in clusters if len(cluster) >= self.min_touches]

    def generate_signal(
        self, symbol: str, current_price: float, levels: Optional[List[SNRLevel]] = None
    ) -> Optional[SNRSignal]:
        """
        Generate trading signal based on SNR levels.

        Args:
            symbol: Trading pair
            current_price: Current market price
            levels: Pre-calculated levels (optional)

        Returns:
            SNRSignal or None
        """
        levels = levels or self.levels.get(symbol, [])

        if not levels:
            return None

        # Find nearest support and resistance
        supports = [l for l in levels if l.type == "support"]
        resistances = [l for l in levels if l.type == "resistance"]

        nearest_support = min(supports, key=lambda l: abs(l.price - current_price)) if supports else None

        nearest_resistance = min(resistances, key=lambda l: abs(l.price - current_price)) if resistances else None

        # Determine signal
        signal = None

        # Check if near support (buy signal)
        if nearest_support:
            distance_to_support = abs(current_price - nearest_support.price) / current_price * 100

            if distance_to_support < self.touch_threshold:
                # Near support - potential bounce
                signal = SNRSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY_SUPPORT,
                    price=current_price,
                    target_level=nearest_support.price,
                    stop_loss=nearest_support.price * 0.98,  # 2% below support
                    take_profit=current_price * 1.05,  # 5% target
                    confidence=nearest_support.strength / 100 * (1 - distance_to_support / self.touch_threshold),
                    metadata={
                        "support_level": nearest_support.price,
                        "support_strength": nearest_support.strength,
                        "distance_pct": distance_to_support,
                    },
                )

        # Check if near resistance (sell signal)
        if nearest_resistance and not signal:
            distance_to_resistance = abs(current_price - nearest_resistance.price) / current_price * 100

            if distance_to_resistance < self.touch_threshold:
                # Near resistance - potential reversal
                signal = SNRSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL_RESISTANCE,
                    price=current_price,
                    target_level=nearest_resistance.price,
                    stop_loss=nearest_resistance.price * 1.02,  # 2% above resistance
                    take_profit=current_price * 0.95,  # 5% target
                    confidence=nearest_resistance.strength / 100 * (1 - distance_to_resistance / self.touch_threshold),
                    metadata={
                        "resistance_level": nearest_resistance.price,
                        "resistance_strength": nearest_resistance.strength,
                        "distance_pct": distance_to_resistance,
                    },
                )

        # Check for breakouts
        if nearest_resistance and current_price > nearest_resistance.price * 1.01:
            # Break above resistance
            signal = SNRSignal(
                symbol=symbol,
                signal_type=SignalType.BREAKOUT_UP,
                price=current_price,
                target_level=current_price * 1.08,
                stop_loss=nearest_resistance.price,
                take_profit=current_price * 1.08,
                confidence=0.7,
                metadata={
                    "broken_resistance": nearest_resistance.price,
                    "breakout_pct": (current_price / nearest_resistance.price - 1) * 100,
                },
            )

        if nearest_support and current_price < nearest_support.price * 0.99:
            # Break below support
            signal = SNRSignal(
                symbol=symbol,
                signal_type=SignalType.BREAKOUT_DOWN,
                price=current_price,
                target_level=current_price * 0.92,
                stop_loss=nearest_support.price,
                take_profit=current_price * 0.92,
                confidence=0.7,
                metadata={
                    "broken_support": nearest_support.price,
                    "breakdown_pct": (1 - current_price / nearest_support.price) * 100,
                },
            )

        if signal:
            self.signals.append(signal)
            self.logger.info(
                f"SNR signal: {signal.signal_type.value} {symbol} @ {current_price:.2f} "
                f"(confidence: {signal.confidence:.2f})"
            )

        return signal

    def get_levels(self, symbol: str) -> List[SNRLevel]:
        """Get detected levels for symbol."""
        return self.levels.get(symbol, [])

    def get_recent_signals(self, symbol: Optional[str] = None, limit: int = 10) -> List[SNRSignal]:
        """Get recent signals."""
        signals = self.signals

        if symbol:
            signals = [s for s in signals if s.symbol == symbol]

        return signals[-limit:]

    def get_stats(self) -> Dict:
        """Get strategy statistics."""
        total_signals = len(self.signals)

        by_type = {}
        for signal in self.signals:
            key = signal.signal_type.value
            by_type[key] = by_type.get(key, 0) + 1

        return {
            "total_levels_detected": sum(len(l) for l in self.levels.values()),
            "total_signals_generated": total_signals,
            "signals_by_type": by_type,
            "symbols_tracked": len(self.levels),
        }

    def reset(self):
        """Reset strategy state."""
        self.levels.clear()
        self.signals.clear()
        self.logger.info("SNR Strategy reset")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    strategy = SNRStrategy(lookback_period=50, touch_threshold=1.0, min_touches=2)

    # Simulate BTC price data
    np.random.seed(42)
    base_price = 45000

    # Generate synthetic data with clear support/resistance
    highs = []
    lows = []
    closes = []

    for i in range(100):
        # Add some structure to create levels
        if i % 20 < 10:
            price = base_price + np.random.normal(0, 200)
        else:
            price = base_price + 1000 + np.random.normal(0, 200)

        highs.append(price + abs(np.random.normal(0, 100)))
        lows.append(price - abs(np.random.normal(0, 100)))
        closes.append(price)

    # Detect levels
    levels = strategy.detect_levels("BTCUSDT", highs, lows, closes)

    print("SNR Strategy Demo")
    print("=" * 50)
    print(f"Detected {len(levels)} levels")

    for level in levels[:5]:
        print(f"  {level.type.upper()}: ${level.price:.0f} (strength: {level.strength:.0f}%)")

    # Generate signal
    current_price = closes[-1]
    signal = strategy.generate_signal("BTCUSDT", current_price, levels)

    if signal:
        print(f"\nSignal: {signal.signal_type.value}")
        print(f"  Price: ${signal.price:.2f}")
        print(f"  Target: ${signal.target_level:.2f}")
        print(f"  Stop: ${signal.stop_loss:.2f}")
        print(f"  Take Profit: ${signal.take_profit:.2f}")
        print(f"  Confidence: {signal.confidence:.2f}")

    print(f"\nStats: {strategy.get_stats()}")
