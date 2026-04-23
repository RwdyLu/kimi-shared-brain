#!/usr/bin/env python3
"""
Crypto Opportunity Monitor
Monitors promising crypto coins for trading opportunities.
"""

import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.fetcher import BinanceFetcher
from app.crypto_screener import CryptoScreener, CoinData


def fetch_top_coins():
    """Fetch top coins from Binance."""
    fetcher = BinanceFetcher()
    
    # Top USDT pairs to monitor
    symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "TRXUSDT", "AVAXUSDT", "LINKUSDT",
        "SUIUSDT", "DOTUSDT", "TONUSDT", "NEARUSDT", "APTUSDT"
    ]
    
    coins = []
    for symbol in symbols:
        try:
            price_data = fetcher.get_latest_price(symbol)
            
            # Create coin data (simplified)
            coin = CoinData(
                symbol=symbol.replace("USDT", ""),
                name=symbol.replace("USDT", ""),
                price=price_data.get("price", 0),
                volume_24h=price_data.get("volume", 0) * price_data.get("price", 0),
                market_cap=0,  # Would need additional API
                price_change_24h=0,  # Would need historical data
                price_change_7d=0,
                volatility=0.0,
                liquidity_score=price_data.get("volume", 0) / 1000
            )
            coins.append(coin)
        except Exception as e:
            print(f"⚠️  Error fetching {symbol}: {e}")
    
    return coins


def run_screening():
    """Run crypto screening."""
    print("="*80)
    print("🔍 CRYPTO OPPORTUNITY SCREENER")
    print(f"Time: {datetime.now()}")
    print("="*80)
    
    # Initialize screener
    screener = CryptoScreener()
    
    # Fetch coins
    print("\n📊 Fetching market data...")
    coins = fetch_top_coins()
    print(f"✅ Fetched {len(coins)} coins")
    
    # Add coins to screener
    screener.add_coins(coins)
    
    # Run screening
    print("\n🎯 Running screening filters...")
    results = screener.screen()
    
    # Get top picks
    top_picks = screener.get_top_picks(n=5)
    
    print("\n" + "="*80)
    print("🏆 TOP OPPORTUNITIES")
    print("="*80)
    print(f"{'Rank':<6}{'Coin':<10}{'Price':<15}{'Volume':<15}{'Score':<8}")
    print("-"*80)
    
    for i, coin in enumerate(top_picks, 1):
        print(f"{i:<6}{coin.symbol:<10}${coin.price:<14.2f}{coin.volume_24h:>13.0f} {coin.screen_score:>6.2f}")
    
    print("="*80)
    
    # Breakout candidates
    breakouts = screener.get_breakout_candidates()
    if breakouts:
        print("\n🚀 BREAKOUT CANDIDATES:")
        for coin in breakouts[:3]:
            print(f"   • {coin.symbol}: Score {coin.screen_score:.2f}")
    
    # Trending
    trending = screener.get_trending()
    if trending:
        print("\n📈 TRENDING UP:")
        for coin in trending[:3]:
            print(f"   • {coin.symbol}: +{coin.price_change_24h:.2f}% (24h)")
    
    # Save results
    state = {
        "timestamp": datetime.now().isoformat(),
        "total_coins": len(coins),
        "top_picks": [c.to_dict() for c in top_picks],
        "all_results": [c.to_dict() for c in results]
    }
    
    with open("state/screening_results.json", "w") as f:
        json.dump(state, f, indent=2)
    
    print(f"\n💾 Results saved to state/screening_results.json")
    print("\n" + "="*80)
    
    return top_picks


if __name__ == '__main__':
    run_screening()
