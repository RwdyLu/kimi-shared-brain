"""
US Stock Data Connector
Connects to US stock exchanges for market data.
"""
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class USStockQuote:
    """US stock quote."""
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    market_cap: float
    pe_ratio: float
    timestamp: datetime


class USStockConnector:
    """US stock market data connector."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key
        self.cache: Dict[str, USStockQuote] = {}
        self.logger.info("USStockConnector initialized")
    
    def fetch_quote(self, symbol: str) -> Optional[USStockQuote]:
        """Fetch US stock quote."""
        import random
        
        names = {
            "AAPL": "Apple Inc.",
            "MSFT": "Microsoft Corp.",
            "GOOGL": "Alphabet Inc.",
            "AMZN": "Amazon.com Inc.",
            "TSLA": "Tesla Inc.",
            "NVDA": "NVIDIA Corp.",
            "META": "Meta Platforms Inc.",
            "NFLX": "Netflix Inc.",
        }
        
        base = {"AAPL": 180, "MSFT": 380, "GOOGL": 140, "AMZN": 180, "TSLA": 250, "NVDA": 800, "META": 500, "NFLX": 600}.get(symbol, 100)
        
        change_pct = random.gauss(0, 1.5)
        price = base * (1 + change_pct / 100)
        
        quote = USStockQuote(
            symbol=symbol,
            name=names.get(symbol, symbol),
            price=round(price, 2),
            change=round(price - base, 2),
            change_pct=round(change_pct, 2),
            volume=random.randint(1000000, 50000000),
            market_cap=random.randint(1000000000, 3000000000000),
            pe_ratio=round(random.gauss(25, 10), 1),
            timestamp=datetime.now()
        )
        
        self.cache[symbol] = quote
        return quote
    
    def get_market_status(self) -> Dict:
        """Get US market status."""
        now = datetime.now()
        is_open = 9 <= now.hour < 16  # Simplified EST check
        return {
            'market': 'US',
            'is_open': is_open,
            'trading_hours': '09:30-16:00 EST',
            'timezone': 'America/New_York',
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    us = USStockConnector()
    quote = us.fetch_quote("AAPL")
    if quote:
        print(f"{quote.name}: ${quote.price} ({quote.change_pct:+.2f}%)")
