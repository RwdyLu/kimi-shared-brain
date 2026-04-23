"""
Historical Data Cache
Caches and manages historical market data for fast backtesting and analysis.
"""
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict


@dataclass
class CandleData:
    """OHLCV candle data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
        }


class HistoricalCache:
    """
    Historical data cache for market data.
    Stores OHLCV data with efficient lookup and memory management.
    """
    
    def __init__(self, max_candles: int = 10000):
        self.logger = logging.getLogger(__name__)
        self.max_candles = max_candles
        
        # Cache storage: symbol -> timeframe -> candles
        self.cache: Dict[str, Dict[str, List[CandleData]]] = defaultdict(
            lambda: defaultdict(list)
        )
        
        # Metadata
        self.last_update: Dict[str, datetime] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
        self.logger.info(f"HistoricalCache initialized (max={max_candles})")
    
    def add_candles(self,
                    symbol: str,
                    timeframe: str,
                    candles: List[CandleData]):
        """
        Add candles to cache.
        
        Args:
            symbol: Trading pair
            timeframe: Time interval (1m, 5m, 1h, 4h, 1d)
            candles: List of CandleData
        """
        key = f"{symbol.upper()}_{timeframe}"
        
        # Add new candles
        self.cache[symbol][timeframe].extend(candles)
        
        # Sort by timestamp
        self.cache[symbol][timeframe].sort(key=lambda c: c.timestamp)
        
        # Trim to max
        if len(self.cache[symbol][timeframe]) > self.max_candles:
            self.cache[symbol][timeframe] = self.cache[symbol][timeframe][-self.max_candles:]
        
        self.last_update[key] = datetime.now()
        
        self.logger.info(
            f"Added {len(candles)} candles: {symbol} {timeframe} "
            f"(total: {len(self.cache[symbol][timeframe])})"
        )
    
    def get_candles(self,
                   symbol: str,
                   timeframe: str,
                   start: Optional[datetime] = None,
                   end: Optional[datetime] = None,
                   limit: int = 1000) -> List[CandleData]:
        """
        Get candles from cache.
        
        Args:
            symbol: Trading pair
            timeframe: Time interval
            start: Start time
            end: End time
            limit: Max candles
            
        Returns:
            List of CandleData
        """
        symbol = symbol.upper()
        
        if symbol not in self.cache or timeframe not in self.cache[symbol]:
            self.cache_misses += 1
            return []
        
        candles = self.cache[symbol][timeframe]
        
        # Filter by time
        if start:
            candles = [c for c in candles if c.timestamp >= start]
        if end:
            candles = [c for c in candles if c.timestamp <= end]
        
        self.cache_hits += 1
        
        # Return last N
        return candles[-limit:]
    
    def get_latest(self, symbol: str, timeframe: str) -> Optional[CandleData]:
        """Get latest candle."""
        candles = self.get_candles(symbol, timeframe, limit=1)
        return candles[0] if candles else None
    
    def get_range(self,
                  symbol: str,
                  timeframe: str,
                  lookback: timedelta) -> List[CandleData]:
        """
        Get candles for lookback period.
        
        Args:
            symbol: Trading pair
            timeframe: Time interval
            lookback: How far back to look
            
        Returns:
            List of CandleData
        """
        start = datetime.now() - lookback
        return self.get_candles(symbol, timeframe, start=start)
    
    def has_data(self, symbol: str, timeframe: str) -> bool:
        """Check if cache has data for symbol/timeframe."""
        return (
            symbol.upper() in self.cache and
            timeframe in self.cache[symbol.upper()] and
            len(self.cache[symbol.upper()][timeframe]) > 0
        )
    
    def get_cache_info(self) -> Dict:
        """Get cache statistics."""
        total_symbols = len(self.cache)
        total_candles = sum(
            len(candles)
            for tfs in self.cache.values()
            for candles in tfs.values()
        )
        
        hit_rate = (
            self.cache_hits / (self.cache_hits + self.cache_misses) * 100
            if (self.cache_hits + self.cache_misses) > 0 else 0
        )
        
        return {
            'symbols': total_symbols,
            'total_candles': total_candles,
            'max_candles': self.max_candles,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': hit_rate,
            'last_updates': {
                k: v.isoformat() for k, v in self.last_update.items()
            },
        }
    
    def clear(self, symbol: Optional[str] = None):
        """Clear cache."""
        if symbol:
            symbol = symbol.upper()
            if symbol in self.cache:
                del self.cache[symbol]
                self.logger.info(f"Cleared cache: {symbol}")
        else:
            self.cache.clear()
            self.last_update.clear()
            self.logger.info("Cleared all cache")
    
    def save_to_disk(self, filepath: str):
        """Save cache to disk."""
        data = {
            'saved_at': datetime.now().isoformat(),
            'cache': {
                symbol: {
                    tf: [c.to_dict() for c in candles]
                    for tf, candles in tfs.items()
                }
                for symbol, tfs in self.cache.items()
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Cache saved to {filepath}")
    
    def load_from_disk(self, filepath: str):
        """Load cache from disk."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for symbol, tfs in data.get('cache', {}).items():
            for tf, candles in tfs.items():
                candle_data = [
                    CandleData(
                        timestamp=datetime.fromisoformat(c['timestamp']),
                        open=c['open'],
                        high=c['high'],
                        low=c['low'],
                        close=c['close'],
                        volume=c['volume'],
                    )
                    for c in candles
                ]
                self.add_candles(symbol, tf, candle_data)
        
        self.logger.info(f"Cache loaded from {filepath}")
    
    def calculate_indicators(self,
                            symbol: str,
                            timeframe: str,
                            indicator: str,
                            period: int = 14) -> List[float]:
        """
        Calculate technical indicators from cached data.
        
        Args:
            symbol: Trading pair
            timeframe: Time interval
            indicator: Indicator type (sma, ema, rsi)
            period: Lookback period
            
        Returns:
            List of indicator values
        """
        candles = self.get_candles(symbol, timeframe)
        closes = [c.close for c in candles]
        
        if len(closes) < period:
            return []
        
        if indicator == "sma":
            return self._calculate_sma(closes, period)
        elif indicator == "ema":
            return self._calculate_ema(closes, period)
        elif indicator == "rsi":
            return self._calculate_rsi(closes, period)
        
        return []
    
    def _calculate_sma(self, data: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average."""
        result = []
        for i in range(period - 1, len(data)):
            avg = sum(data[i - period + 1:i + 1]) / period
            result.append(avg)
        return result
    
    def _calculate_ema(self, data: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average."""
        if len(data) < period:
            return []
        
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        result = [ema]
        
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
            result.append(ema)
        
        return result
    
    def _calculate_rsi(self, data: List[float], period: int = 14) -> List[float]:
        """Calculate RSI."""
        if len(data) < period + 1:
            return []
        
        gains = []
        losses = []
        
        for i in range(1, len(data)):
            change = data[i] - data[i - 1]
            gains.append(max(change, 0))
            losses.append(abs(min(change, 0)))
        
        result = []
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            result.append(rsi)
        
        return result


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    cache = HistoricalCache(max_candles=1000)
    
    # Add sample data
    import random
    base_price = 45000
    candles = []
    
    for i in range(100):
        price = base_price + random.gauss(0, 500)
        candle = CandleData(
            timestamp=datetime.now() - timedelta(hours=100-i),
            open=price - random.gauss(0, 100),
            high=price + abs(random.gauss(0, 200)),
            low=price - abs(random.gauss(0, 200)),
            close=price,
            volume=random.gauss(1000, 200),
        )
        candles.append(candle)
    
    cache.add_candles("BTCUSDT", "1h", candles)
    
    # Query
    print("Historical Data Cache Demo")
    print("=" * 50)
    print(f"Cached: BTCUSDT 1h - {len(cache.cache['BTCUSDT']['1h'])} candles")
    
    # Get latest
    latest = cache.get_latest("BTCUSDT", "1h")
    if latest:
        print(f"Latest: O={latest.open:.0f} H={latest.high:.0f} L={latest.low:.0f} C={latest.close:.0f}")
    
    # Calculate indicators
    sma = cache.calculate_indicators("BTCUSDT", "1h", "sma", 20)
    rsi = cache.calculate_indicators("BTCUSDT", "1h", "rsi", 14)
    
    if sma:
        print(f"SMA(20): {sma[-1]:.0f}")
    if rsi:
        print(f"RSI(14): {rsi[-1]:.1f}")
    
    print(f"\nCache info: {cache.get_cache_info()}")
