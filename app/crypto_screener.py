"""
Crypto Screener - Promising Coins Filter
Filters and ranks cryptocurrencies based on multiple criteria.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ScreenerCriteria(Enum):
    """Available screening criteria."""

    VOLUME = "volume"  # 24h volume
    MARKET_CAP = "market_cap"  # Market capitalization
    PRICE_CHANGE = "price_change"  # 24h price change
    VOLATILITY = "volatility"  # Price volatility
    LIQUIDITY = "liquidity"  # Bid-ask spread
    TREND = "trend"  # Price trend direction


@dataclass
class CoinData:
    """Cryptocurrency data snapshot."""

    symbol: str
    name: str
    price: float
    volume_24h: float
    market_cap: float
    price_change_24h: float
    price_change_7d: float
    volatility: float = 0.0
    liquidity_score: float = 0.0

    # Screen score
    screen_score: float = 0.0
    passed_filters: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": self.price,
            "volume_24h": self.volume_24h,
            "market_cap": self.market_cap,
            "price_change_24h": self.price_change_24h,
            "price_change_7d": self.price_change_7d,
            "volatility": self.volatility,
            "liquidity_score": self.liquidity_score,
            "screen_score": self.screen_score,
            "passed_filters": self.passed_filters,
        }


class CryptoScreener:
    """
    Cryptocurrency screener and filter.

    Evaluates coins against multiple criteria and generates
    a ranked list of promising trading opportunities.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Default filters
        self.filters: Dict[str, Dict] = {
            "min_volume": {"threshold": 1000000, "weight": 1.0},  # $1M daily volume
            "min_market_cap": {"threshold": 10000000, "weight": 0.8},  # $10M market cap
            "max_volatility": {"threshold": 50, "weight": 0.5},  # <50% volatility
            "min_price_change": {"threshold": -10, "weight": 0.6},  # Not crashing (> -10%)
            "trending_up": {"threshold": 0, "weight": 0.7},  # Positive 24h change
        }

        # Screening results
        self.coins: Dict[str, CoinData] = {}
        self.screened: List[CoinData] = []

        self.logger.info("CryptoScreener initialized")

    def add_coin(self, coin: CoinData):
        """Add coin to screener."""
        self.coins[coin.symbol] = coin

    def add_coins(self, coins: List[CoinData]):
        """Add multiple coins."""
        for coin in coins:
            self.add_coin(coin)

    def set_filter(self, name: str, threshold: float, weight: float = 1.0):
        """
        Configure a filter criterion.

        Args:
            name: Filter name
            threshold: Filter threshold
            weight: Scoring weight
        """
        self.filters[name] = {"threshold": threshold, "weight": weight}

    def screen(self, symbols: Optional[List[str]] = None) -> List[CoinData]:
        """
        Run screening on coins.

        Args:
            symbols: Specific symbols to screen (None = all)

        Returns:
            Ranked list of CoinData that passed filters
        """
        symbols = symbols or list(self.coins.keys())
        results = []

        for symbol in symbols:
            if symbol not in self.coins:
                continue

            coin = self.coins[symbol]
            score = 0.0
            passed = []

            # Apply filters
            if "min_volume" in self.filters:
                if coin.volume_24h >= self.filters["min_volume"]["threshold"]:
                    score += self.filters["min_volume"]["weight"]
                    passed.append("volume")

            if "min_market_cap" in self.filters:
                if coin.market_cap >= self.filters["min_market_cap"]["threshold"]:
                    score += self.filters["min_market_cap"]["weight"]
                    passed.append("market_cap")

            if "max_volatility" in self.filters:
                if coin.volatility <= self.filters["max_volatility"]["threshold"]:
                    score += self.filters["max_volatility"]["weight"]
                    passed.append("volatility")

            if "min_price_change" in self.filters:
                if coin.price_change_24h >= self.filters["min_price_change"]["threshold"]:
                    score += self.filters["min_price_change"]["weight"]
                    passed.append("price_change")

            if "trending_up" in self.filters:
                if coin.price_change_24h > self.filters["trending_up"]["threshold"]:
                    score += self.filters["trending_up"]["weight"]
                    passed.append("trending_up")

            # Calculate screen score (0-100)
            max_possible = sum(f["weight"] for f in self.filters.values())
            coin.screen_score = (score / max_possible * 100) if max_possible > 0 else 0
            coin.passed_filters = passed

            # Include if passed at least 3 filters
            if len(passed) >= 3:
                results.append(coin)

        # Sort by screen score descending
        results.sort(key=lambda c: c.screen_score, reverse=True)
        self.screened = results

        self.logger.info(f"Screened {len(symbols)} coins, {len(results)} passed")

        return results

    def get_top_picks(self, n: int = 10) -> List[CoinData]:
        """Get top N picks from screening."""
        return self.screened[:n]

    def get_breakout_candidates(self, min_volume_change: float = 50.0) -> List[CoinData]:
        """
        Find coins with unusual volume activity.

        Args:
            min_volume_change: Minimum volume increase %

        Returns:
            Coins with volume spikes
        """
        candidates = []
        for coin in self.screened:
            # Would compare to average volume in practice
            if coin.volume_24h > 0:  # Placeholder
                candidates.append(coin)

        return candidates

    def get_trending(self, min_change: float = 5.0) -> List[CoinData]:
        """
        Find trending coins.

        Args:
            min_change: Minimum 24h change %

        Returns:
            Coins with strong momentum
        """
        return [c for c in self.screened if c.price_change_24h >= min_change]

    def get_undervalued(self, max_change: float = -5.0) -> List[CoinData]:
        """
        Find potentially undervalued coins.

        Args:
            max_change: Maximum 24h change (negative)

        Returns:
            Coins that dropped but have good fundamentals
        """
        return [
            c
            for c in self.screened
            if c.price_change_24h <= max_change and c.market_cap > 100000000  # $100M+ market cap
        ]

    def generate_report(self) -> str:
        """Generate screening report."""
        if not self.screened:
            return "No coins screened yet."

        report = f"""
🔍 Crypto Screener Report
{'=' * 50}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Total Coins: {len(self.coins)}
Passed Screening: {len(self.screened)}

📊 Top Picks (by screen score):
"""

        for i, coin in enumerate(self.screened[:10], 1):
            report += f"""
{i}. {coin.symbol} - {coin.name}
   Price: ${coin.price:.4f}
   24h Change: {coin.price_change_24h:+.2f}%
   Volume: ${coin.volume_24h:,.0f}
   Market Cap: ${coin.market_cap:,.0f}
   Score: {coin.screen_score:.1f}/100
   Passed: {', '.join(coin.passed_filters)}
"""

        # Statistics
        trending = len(self.get_trending())
        undervalued = len(self.get_undervalued())

        report += f"""
📈 Summary:
• Trending Up: {trending}
• Undervalued: {undervalued}
• High Volume: {len(self.get_breakout_candidates())}

💡 Filters Applied:
"""
        for name, config in self.filters.items():
            report += f"• {name}: threshold={config['threshold']}, weight={config['weight']}\n"

        return report

    def export_results(self, filepath: str):
        """Export screening results to JSON."""
        data = {
            "screened_at": datetime.now().isoformat(),
            "total_coins": len(self.coins),
            "passed": len(self.screened),
            "filters": self.filters,
            "top_picks": [c.to_dict() for c in self.screened[:20]],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Results exported to {filepath}")

    def get_stats(self) -> Dict:
        """Get screener statistics."""
        return {
            "total_coins": len(self.coins),
            "screened": len(self.screened),
            "avg_screen_score": sum(c.screen_score for c in self.screened) / len(self.screened) if self.screened else 0,
            "filters_active": len(self.filters),
            "top_performer": self.screened[0].symbol if self.screened else None,
        }

    def reset(self):
        """Reset screener state."""
        self.coins.clear()
        self.screened.clear()
        self.logger.info("Screener reset")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    screener = CryptoScreener()

    # Add sample coins
    coins = [
        CoinData(
            symbol="BTCUSDT",
            name="Bitcoin",
            price=45000,
            volume_24h=5000000000,
            market_cap=900000000000,
            price_change_24h=2.5,
            price_change_7d=5.0,
            volatility=25,
        ),
        CoinData(
            symbol="ETHUSDT",
            name="Ethereum",
            price=3200,
            volume_24h=2000000000,
            market_cap=380000000000,
            price_change_24h=3.0,
            price_change_7d=-2.0,
            volatility=30,
        ),
        CoinData(
            symbol="SOLUSDT",
            name="Solana",
            price=120,
            volume_24h=500000000,
            market_cap=50000000000,
            price_change_24h=8.0,
            price_change_7d=15.0,
            volatility=45,
        ),
        CoinData(
            symbol="SHIBUSDT",
            name="Shiba Inu",
            price=0.00001,
            volume_24h=100000000,
            market_cap=5000000000,
            price_change_24h=-5.0,
            price_change_7d=-10.0,
            volatility=60,
        ),
    ]

    screener.add_coins(coins)

    # Run screening
    results = screener.screen()

    print("Crypto Screener Demo")
    print("=" * 50)
    print(f"Screened {len(coins)} coins, {len(results)} passed")

    print("\nTop Picks:")
    for coin in results[:3]:
        print(f"  {coin.symbol}: Score={coin.screen_score:.1f} (change: {coin.price_change_24h:+.1f}%)")

    print(f"\nTrending: {len(screener.get_trending())} coins")
    print(f"Undervalued: {len(screener.get_undervalued())} coins")

    print(f"\nStats: {screener.get_stats()}")

    # Report
    print("\n" + screener.generate_report())
