"""
Taiwan Stock Data Connector
Connects to Taiwan Stock Exchange (TWSE) for market data.
"""

import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import time


@dataclass
class TWSEQuote:
    """TWSE stock quote."""

    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    open_price: float
    high: float
    low: float
    prev_close: float
    timestamp: datetime

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": self.price,
            "change": self.change,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "open": self.open_price,
            "high": self.high,
            "low": self.low,
            "prev_close": self.prev_close,
            "timestamp": self.timestamp.isoformat(),
        }


class TWSEConnector:
    """
    Taiwan Stock Exchange (TWSE) data connector.

    Provides real-time and historical data for Taiwan stocks.
    Supports major indices: TAIEX, TWII, and individual stocks.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key

        # Cache
        self.cache: Dict[str, TWSEQuote] = {}
        self.cache_time: Optional[datetime] = None

        self.logger.info("TWSEConnector initialized")

    def fetch_quote(self, symbol: str) -> Optional[TWSEQuote]:
        """
        Fetch stock quote from TWSE.

        Args:
            symbol: Stock symbol (e.g., "2330" for TSMC)

        Returns:
            TWSEQuote or None
        """
        # Mock implementation - would integrate with TWSE API
        # TWSE API endpoints:
        # - https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{symbol}.tw

        try:
            # Simulate API call
            quote = self._mock_quote(symbol)
            self.cache[symbol] = quote
            self.cache_time = datetime.now()
            return quote

        except Exception as e:
            self.logger.error(f"Failed to fetch {symbol}: {e}")
            return None

    def _mock_quote(self, symbol: str) -> TWSEQuote:
        """Generate mock quote for demo."""
        import random

        # Common TW stocks
        names = {
            "2330": "台積電",
            "2317": "鴻海",
            "2454": "聯發科",
            "2308": "台達電",
            "2881": "富邦金",
            "2882": "國泰金",
            "2303": "聯電",
            "2886": "兆豐金",
            "1216": "統一",
            "2891": "中信金",
        }

        base_prices = {
            "2330": 850,
            "2317": 120,
            "2454": 1200,
            "2308": 380,
            "2881": 65,
            "2882": 58,
            "2303": 55,
            "2886": 32,
            "1216": 75,
            "2891": 28,
        }

        base = base_prices.get(symbol, 100)
        change_pct = random.gauss(0, 1.5)
        price = base * (1 + change_pct / 100)

        return TWSEQuote(
            symbol=symbol,
            name=names.get(symbol, f"Stock_{symbol}"),
            price=round(price, 2),
            change=round(price - base, 2),
            change_pct=round(change_pct, 2),
            volume=random.randint(1000000, 50000000),
            open_price=round(base * (1 + random.gauss(0, 0.5) / 100), 2),
            high=round(price * (1 + abs(random.gauss(0, 1)) / 100), 2),
            low=round(price * (1 - abs(random.gauss(0, 1)) / 100), 2),
            prev_close=base,
            timestamp=datetime.now(),
        )

    def fetch_multiple(self, symbols: List[str]) -> Dict[str, TWSEQuote]:
        """
        Fetch multiple stock quotes.

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary of symbol -> TWSEQuote
        """
        results = {}
        for symbol in symbols:
            quote = self.fetch_quote(symbol)
            if quote:
                results[symbol] = quote

        return results

    def get_market_status(self) -> Dict:
        """Get Taiwan stock market status."""
        now = datetime.now()

        # TWSE trading hours: 9:00-13:30
        is_trading_hours = 9 <= now.hour < 13 or (now.hour == 13 and now.minute <= 30)

        return {
            "market": "TWSE",
            "is_open": is_trading_hours,
            "trading_hours": "09:00-13:30",
            "timezone": "Asia/Taipei",
            "current_time": now.isoformat(),
        }

    def get_cache(self, symbol: str) -> Optional[TWSEQuote]:
        """Get cached quote."""
        # Check cache freshness (5 minutes)
        if self.cache_time and (datetime.now() - self.cache_time).seconds < 300:
            return self.cache.get(symbol)
        return None

    def export_quotes(self, filepath: str):
        """Export all cached quotes."""
        data = {
            "exported_at": datetime.now().isoformat(),
            "quotes": {s: q.to_dict() for s, q in self.cache.items()},
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Quotes exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    twse = TWSEConnector()

    print("TWSE Connector Demo")
    print("=" * 50)

    # Fetch TSMC
    quote = twse.fetch_quote("2330")
    if quote:
        print(f"{quote.name} ({quote.symbol}): ${quote.price}")
        print(f"  Change: {quote.change_pct:+.2f}%")
        print(f"  Volume: {quote.volume:,}")

    # Market status
    print(f"\nMarket: {twse.get_market_status()}")
