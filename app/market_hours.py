"""
Multi-Market Trading Hours Manager
Manages trading hours for multiple markets.
"""
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import pytz


@dataclass
class MarketHours:
    """Trading hours for a market."""
    market: str
    timezone: str
    open_time: time
    close_time: time
    pre_market: Optional[tuple] = None
    post_market: Optional[tuple] = None
    holidays: List[str] = None


class MarketHoursManager:
    """
    Manages trading hours for multiple global markets.
    
    Supports:
    - Crypto (24/7)
    - Taiwan Stock (TWSE)
    - US Stock (NYSE/NASDAQ)
    - Forex
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Market definitions
        self.markets: Dict[str, MarketHours] = {
            'crypto': MarketHours(
                market='Crypto',
                timezone='UTC',
                open_time=time(0, 0),
                close_time=time(23, 59),
            ),
            'twse': MarketHours(
                market='TWSE',
                timezone='Asia/Taipei',
                open_time=time(9, 0),
                close_time=time(13, 30),
            ),
            'us': MarketHours(
                market='US',
                timezone='America/New_York',
                open_time=time(9, 30),
                close_time=time(16, 0),
                pre_market=(time(4, 0), time(9, 30)),
                post_market=(time(16, 0), time(20, 0)),
            ),
            'forex': MarketHours(
                market='Forex',
                timezone='UTC',
                open_time=time(0, 0),
                close_time=time(23, 59),
            ),
        }
        
        self.logger.info("MarketHoursManager initialized")
    
    def is_market_open(self, market: str, dt: Optional[datetime] = None) -> bool:
        """
        Check if market is open.
        
        Args:
            market: Market identifier
            dt: Datetime to check (None = now)
            
        Returns:
            True if market is open
        """
        if market not in self.markets:
            return False
        
        hours = self.markets[market]
        
        # Crypto is always open
        if market == 'crypto':
            return True
        
        # Get time in market timezone
        dt = dt or datetime.now(pytz.utc)
        
        tz = pytz.timezone(hours.timezone)
        market_time = dt.astimezone(tz)
        
        # Check if holiday
        date_str = market_time.strftime('%Y-%m-%d')
        if hours.holidays and date_str in hours.holidays:
            return False
        
        # Check trading hours
        current_time = market_time.time()
        return hours.open_time <= current_time <= hours.close_time
    
    def get_market_status(self, market: str) -> Dict:
        """
        Get market status.
        
        Args:
            market: Market identifier
            
        Returns:
            Status dict
        """
        if market not in self.markets:
            return {'error': f'Unknown market: {market}'}
        
        hours = self.markets[market]
        is_open = self.is_market_open(market)
        
        return {
            'market': hours.market,
            'timezone': hours.timezone,
            'is_open': is_open,
            'trading_hours': f"{hours.open_time.strftime('%H:%M')}-{hours.close_time.strftime('%H:%M')}",
        }
    
    def get_all_markets_status(self) -> Dict[str, Dict]:
        """Get status for all markets."""
        return {m: self.get_market_status(m) for m in self.markets}
    
    def time_until_open(self, market: str) -> Optional[timedelta]:
        """
        Calculate time until market opens.
        
        Args:
            market: Market identifier
            
        Returns:
            Time delta or None if always open
        """
        if market not in self.markets:
            return None
        
        hours = self.markets[market]
        
        if market == 'crypto':
            return None
        
        now = datetime.now(pytz.timezone(hours.timezone))
        
        # If market is open, time until tomorrow's open
        # If closed, time until next open
        if self.is_market_open(market):
            # Already open
            return timedelta(0)
        
        # Calculate next open
        next_open = datetime.combine(now.date(), hours.open_time)
        next_open = pytz.timezone(hours.timezone).localize(next_open)
        
        if now.time() > hours.close_time:
            # After hours, next open is tomorrow
            next_open += timedelta(days=1)
        
        return next_open - now


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    manager = MarketHoursManager()
    
    print("Market Hours Manager Demo")
    print("=" * 50)
    
    for market in ['crypto', 'twse', 'us', 'forex']:
        status = manager.get_market_status(market)
        print(f"\n{status['market']}:")
        print(f"  Open: {'Yes' if status['is_open'] else 'No'}")
        print(f"  Hours: {status['trading_hours']}")
        print(f"  Timezone: {status['timezone']}")
