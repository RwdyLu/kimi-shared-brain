"""
Market Direction Filter Module
市場方向過濾模組

Per-symbol independent trend direction filter.
每個幣種獨立的趨勢方向過濾器。

Logic:
1. Fetch 15m K-line data per symbol
2. Calculate EMA20 and EMA50 from 15m closes
3. Direction rules (per symbol):
   - EMA20 > EMA50  → Trend UP   → Allow LONG signals only
   - EMA20 < EMA50  → Trend DOWN → Allow SHORT signals only
   - Gap < 0.3%     → Sideways  → BLOCK ALL signals for this symbol
4. Gate-check runs before any signal is emitted
5. Filter results are logged: Symbol | EMA20 | EMA50 | Direction | Allowed

T-066 / 2026-05-08
"""

import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.fetcher import create_fetcher, BinanceFetcher, KlineData
from indicators.calculator import calculate_ema

logger = logging.getLogger(__name__)


class MarketDirection(Enum):
    """Market direction per symbol / 每個幣種的市場方向"""
    UP = "up"           # EMA20 > EMA50
    DOWN = "down"       # EMA20 < EMA50
    SIDEWAYS = "sideways"  # |EMA20 - EMA50| / EMA50 < 0.3%
    UNKNOWN = "unknown"  # Not enough data


class SignalSide(Enum):
    """Signal side / 訊號方向"""
    LONG = "long"
    SHORT = "short"
    UNKNOWN = "unknown"


@dataclass
class FilterResult:
    """Filter check result / 過濾檢查結果"""
    symbol: str
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    direction: MarketDirection = MarketDirection.UNKNOWN
    gap_pct: Optional[float] = None
    allowed: bool = False
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ema20": round(self.ema20, 4) if self.ema20 else None,
            "ema50": round(self.ema50, 4) if self.ema50 else None,
            "direction": self.direction.value,
            "gap_pct": round(self.gap_pct, 4) if self.gap_pct else None,
            "allowed": self.allowed,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class MarketDirectionFilter:
    """
    Per-symbol market direction filter.
    
    Fetches 15m data per symbol, calculates EMA20/EMA50,
    and determines whether a signal should be allowed.
    """
    
    # Config
    EMA_FAST_PERIOD = 20
    EMA_SLOW_PERIOD = 50
    TIMEFRAME = "15m"
    KLINE_LIMIT = 60  # Need at least 50 for EMA50
    SIDEWAYS_THRESHOLD_PCT = 0.3  # 0.3%
    
    def __init__(self, fetcher: Optional[BinanceFetcher] = None):
        self.fetcher = fetcher or create_fetcher()
        self._cache: Dict[str, FilterResult] = {}
        self._cache_ttl_seconds = 60  # Cache results for 60s to avoid excessive API calls
        self._cache_time: Dict[str, float] = {}
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached result is still valid"""
        last_time = self._cache_time.get(symbol, 0)
        return (time.time() - last_time) < self._cache_ttl_seconds
    
    def _fetch_15m_data(self, symbol: str) -> List[KlineData]:
        """Fetch 15m kline data for a symbol"""
        try:
            raw = self.fetcher.fetch_klines(symbol=symbol, interval=self.TIMEFRAME, limit=self.KLINE_LIMIT)
            return self.fetcher.normalize_kline_data(raw)
        except Exception as e:
            logger.error(f"Failed to fetch 15m data for {symbol}: {e}")
            return []
    
    def _calculate_ema20_ema50(self, closes: List[float]) -> Tuple[Optional[float], Optional[float]]:
        """Calculate EMA20 and EMA50 from closes"""
        if len(closes) < self.EMA_SLOW_PERIOD:
            return None, None
        
        ema20_list = calculate_ema(closes, self.EMA_FAST_PERIOD)
        ema50_list = calculate_ema(closes, self.EMA_SLOW_PERIOD)
        
        if not ema20_list or not ema50_list:
            return None, None
        
        return ema20_list[-1], ema50_list[-1]
    
    def _determine_direction(self, ema20: float, ema50: float) -> Tuple[MarketDirection, float, str]:
        """
        Determine market direction and gap percentage.
        
        Returns: (direction, gap_pct, reason)
        """
        gap = ema20 - ema50
        gap_pct = abs(gap) / ema50 * 100  # Percentage relative to EMA50
        
        if gap_pct < self.SIDEWAYS_THRESHOLD_PCT:
            return MarketDirection.SIDEWAYS, gap_pct, f"Gap {gap_pct:.2f}% < {self.SIDEWAYS_THRESHOLD_PCT}% (sideways)"
        
        if ema20 > ema50:
            return MarketDirection.UP, gap_pct, f"EMA20 {ema20:.2f} > EMA50 {ema50:.2f} (up, gap={gap_pct:.2f}%)"
        else:
            return MarketDirection.DOWN, gap_pct, f"EMA20 {ema20:.2f} < EMA50 {ema50:.2f} (down, gap={gap_pct:.2f}%)"
    
    def evaluate_symbol(self, symbol: str, force_refresh: bool = False) -> FilterResult:
        """
        Evaluate market direction for a single symbol.
        
        Returns FilterResult with direction and allowance status.
        """
        # Check cache
        if not force_refresh and self._is_cache_valid(symbol) and symbol in self._cache:
            return self._cache[symbol]
        
        # Fetch data
        data_15m = self._fetch_15m_data(symbol)
        if not data_15m:
            result = FilterResult(
                symbol=symbol,
                direction=MarketDirection.UNKNOWN,
                allowed=False,
                reason="Failed to fetch 15m data"
            )
            self._cache[symbol] = result
            self._cache_time[symbol] = time.time()
            return result
        
        closes = [k.close for k in data_15m]
        ema20, ema50 = self._calculate_ema20_ema50(closes)
        
        if ema20 is None or ema50 is None:
            result = FilterResult(
                symbol=symbol,
                direction=MarketDirection.UNKNOWN,
                allowed=False,
                reason=f"Not enough data (need {self.EMA_SLOW_PERIOD} candles, got {len(closes)})"
            )
            self._cache[symbol] = result
            self._cache_time[symbol] = time.time()
            return result
        
        # Determine direction
        direction, gap_pct, reason = self._determine_direction(ema20, ema50)
        
        result = FilterResult(
            symbol=symbol,
            ema20=ema20,
            ema50=ema50,
            direction=direction,
            gap_pct=gap_pct,
            allowed=(direction != MarketDirection.SIDEWAYS),  # Sideways = block all
            reason=reason
        )
        
        # Update cache
        self._cache[symbol] = result
        self._cache_time[symbol] = time.time()
        
        return result
    
    def gate_check(self, symbol: str, signal_side: SignalSide, force_refresh: bool = False) -> FilterResult:
        """
        Gate-check: determine if a signal should be allowed for this symbol.
        
        Args:
            symbol: Trading pair
            signal_side: LONG or SHORT
            force_refresh: Force re-fetch data
            
        Returns:
            FilterResult with allowed=True/False
        """
        base_result = self.evaluate_symbol(symbol, force_refresh=force_refresh)
        
        # Create a fresh copy to avoid mutating the cached object / 建立新副本避免修改快取
        result = FilterResult(
            symbol=base_result.symbol,
            ema20=base_result.ema20,
            ema50=base_result.ema50,
            direction=base_result.direction,
            gap_pct=base_result.gap_pct,
            allowed=base_result.allowed,
            reason=base_result.reason,
            timestamp=base_result.timestamp,
        )
        
        # Sideways: block everything
        if result.direction == MarketDirection.SIDEWAYS:
            result.allowed = False
            result.reason += f" | BLOCKED: sideways market, no {signal_side.value} allowed"
            return result
        
        # Trend UP: allow LONG only
        if result.direction == MarketDirection.UP:
            if signal_side == SignalSide.LONG:
                result.allowed = True
                result.reason += f" | ALLOWED: {signal_side.value} in uptrend"
            else:
                result.allowed = False
                result.reason += f" | BLOCKED: {signal_side.value} signal rejected in uptrend"
            return result
        
        # Trend DOWN: allow SHORT only
        if result.direction == MarketDirection.DOWN:
            if signal_side == SignalSide.SHORT:
                result.allowed = True
                result.reason += f" | ALLOWED: {signal_side.value} in downtrend"
            else:
                result.allowed = False
                result.reason += f" | BLOCKED: {signal_side.value} signal rejected in downtrend"
            return result
        
        # Unknown: block
        result.allowed = False
        result.reason += f" | BLOCKED: unknown direction"
        return result
    
    def evaluate_all_symbols(self, symbols: List[str]) -> Dict[str, FilterResult]:
        """
        Evaluate all symbols and return results.
        
        Returns:
            Dict mapping symbol -> FilterResult
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.evaluate_symbol(symbol)
        return results
    
    def get_direction_for_symbol(self, symbol: str) -> MarketDirection:
        """Get cached direction for a symbol (evaluates if needed)"""
        result = self.evaluate_symbol(symbol)
        return result.direction
    
    def log_all_results(self, results: Dict[str, FilterResult]) -> str:
        """
        Format and return log output for all symbol evaluations.
        
        Returns formatted log string.
        """
        lines = []
        lines.append("=" * 70)
        lines.append("MARKET DIRECTION FILTER / 市場方向過濾器")
        lines.append("=" * 70)
        lines.append(f"{'Symbol':<12} {'EMA20':>10} {'EMA50':>10} {'Gap%':>8} {'Direction':<10} {'Allowed':<8} {'Reason'}")
        lines.append("-" * 70)
        
        for symbol, result in sorted(results.items()):
            ema20_str = f"{result.ema20:>10.2f}" if result.ema20 else "     N/A"
            ema50_str = f"{result.ema50:>10.2f}" if result.ema50 else "     N/A"
            gap_str = f"{result.gap_pct:>7.2f}%" if result.gap_pct else "    N/A"
            dir_str = result.direction.value.upper()
            allowed_str = "YES" if result.allowed else "NO"
            
            lines.append(
                f"{symbol:<12} {ema20_str} {ema50_str} {gap_str} {dir_str:<10} {allowed_str:<8} {result.reason}"
            )
        
        lines.append("=" * 70)
        log_output = "\n".join(lines)
        print(log_output)
        return log_output
    
    def clear_cache(self) -> None:
        """Clear cached results"""
        self._cache.clear()
        self._cache_time.clear()


# Convenience function for direct use
def create_market_filter(fetcher: Optional[BinanceFetcher] = None) -> MarketDirectionFilter:
    """Create a market direction filter instance"""
    return MarketDirectionFilter(fetcher=fetcher)


# Standalone test
if __name__ == "__main__":
    print("Market Direction Filter / 市場方向過濾器")
    print("=" * 50)
    
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    
    filter_obj = MarketDirectionFilter()
    results = filter_obj.evaluate_all_symbols(symbols)
    filter_obj.log_all_results(results)
    
    print("\nGate-check examples / 閘門檢查範例:")
    for symbol in symbols[:3]:
        long_result = filter_obj.gate_check(symbol, SignalSide.LONG)
        short_result = filter_obj.gate_check(symbol, SignalSide.SHORT)
        print(f"  {symbol}: LONG={'✅' if long_result.allowed else '❌'}, SHORT={'✅' if short_result.allowed else '❌'}")
