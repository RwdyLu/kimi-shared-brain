"""
Stock Fundamental Data Fetcher
Fetches fundamental data for stock analysis.
"""
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FundamentalData:
    """Stock fundamental metrics."""
    symbol: str
    market_cap: float
    pe_ratio: float
    pb_ratio: float
    dividend_yield: float
    eps: float
    revenue: float
    debt_to_equity: float
    roe: float
    gross_margin: float
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'market_cap': self.market_cap,
            'pe_ratio': self.pe_ratio,
            'pb_ratio': self.pb_ratio,
            'dividend_yield': self.dividend_yield,
            'eps': self.eps,
            'revenue': self.revenue,
            'debt_to_equity': self.debt_to_equity,
            'roe': self.roe,
            'gross_margin': self.gross_margin,
            'timestamp': self.timestamp.isoformat(),
        }


class FundamentalDataFetcher:
    """
    Fetches fundamental data for stock analysis.
    
    Supports Taiwan and US stocks with key metrics:
    - Valuation (P/E, P/B)
    - Profitability (ROE, margins)
    - Financial health (D/E ratio)
    - Income (EPS, revenue)
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache: Dict[str, FundamentalData] = {}
        self.logger.info("FundamentalDataFetcher initialized")
    
    def fetch(self, symbol: str) -> Optional[FundamentalData]:
        """
        Fetch fundamental data for symbol.
        
        Args:
            symbol: Stock symbol (e.g., "2330.TW" or "AAPL")
            
        Returns:
            FundamentalData or None
        """
        # Mock implementation - would integrate with financial data API
        # APIs: Yahoo Finance, Financial Modeling Prep, etc.
        
        try:
            data = self._mock_data(symbol)
            self.cache[symbol] = data
            return data
            
        except Exception as e:
            self.logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
            return None
    
    def _mock_data(self, symbol: str) -> FundamentalData:
        """Generate mock fundamental data."""
        import random
        
        # Mock data for demo
        data = FundamentalData(
            symbol=symbol,
            market_cap=random.uniform(1000000000, 3000000000000),
            pe_ratio=random.uniform(10, 40),
            pb_ratio=random.uniform(1, 8),
            dividend_yield=random.uniform(0, 5),
            eps=random.uniform(1, 50),
            revenue=random.uniform(1000000000, 500000000000),
            debt_to_equity=random.uniform(0.1, 2.0),
            roe=random.uniform(5, 30),
            gross_margin=random.uniform(20, 80),
            timestamp=datetime.now()
        )
        
        return data
    
    def screen_value_stocks(self,
                           max_pe: float = 20,
                           max_pb: float = 3,
                           min_dividend: float = 2.0) -> List[FundamentalData]:
        """
        Screen for value stocks.
        
        Args:
            max_pe: Maximum P/E ratio
            max_pb: Maximum P/B ratio
            min_dividend: Minimum dividend yield %
            
        Returns:
            List of value stocks
        """
        value_stocks = []
        
        for data in self.cache.values():
            if (data.pe_ratio <= max_pe and
                data.pb_ratio <= max_pb and
                data.dividend_yield >= min_dividend):
                value_stocks.append(data)
        
        # Sort by composite value score
        value_stocks.sort(key=lambda d: d.pe_ratio + d.pb_ratio)
        
        return value_stocks
    
    def get_growth_stocks(self, min_roe: float = 15) -> List[FundamentalData]:
        """
        Screen for growth stocks.
        
        Args:
            min_roe: Minimum ROE %
            
        Returns:
            List of growth stocks
        """
        growth = [d for d in self.cache.values() if d.roe >= min_roe]
        growth.sort(key=lambda d: d.roe, reverse=True)
        return growth
    
    def export_data(self, filepath: str):
        """Export all cached data."""
        data = {
            'exported_at': datetime.now().isoformat(),
            'fundamentals': {s: d.to_dict() for s, d in self.cache.items()},
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Data exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    fetcher = FundamentalDataFetcher()
    
    print("Fundamental Data Fetcher Demo")
    print("=" * 50)
    
    # Fetch data
    for symbol in ["2330.TW", "2317.TW", "AAPL", "MSFT"]:
        data = fetcher.fetch(symbol)
        if data:
            print(f"\n{symbol}:")
            print(f"  P/E: {data.pe_ratio:.1f}, P/B: {data.pb_ratio:.1f}")
            print(f"  ROE: {data.roe:.1f}%, Dividend: {data.dividend_yield:.1f}%")
            print(f"  Market Cap: ${data.market_cap/1e9:.1f}B")
