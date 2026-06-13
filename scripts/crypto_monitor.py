#!/usr/bin/env python3
"""
Crypto Opportunity Monitor - Auto Screening
Monitors promising crypto coins for trading opportunities.
Runs automatically via cron job.
"""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.fetcher import BinanceFetcher
from app.crypto_screener import CryptoScreener, CoinData


def fetch_top_coins():
    """Fetch top coins from Binance with 24h change data."""
    fetcher = BinanceFetcher()
    
    # Top USDT pairs to monitor - expanded list
    symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "TRXUSDT", "AVAXUSDT", "LINKUSDT",
        "SUIUSDT", "DOTUSDT", "TONUSDT", "NEARUSDT", "APTUSDT",
        "LTCUSDT", "BCHUSDT", "ETCUSDT", "XLMUSDT", "UNIUSDT"
    ]
    
    coins = []
    for symbol in symbols:
        try:
            price_data = fetcher.get_latest_price(symbol)
            
            # Calculate volatility proxy from high/low
            price = price_data.get("price", 0)
            high_24h = price_data.get("high_24h", price)
            low_24h = price_data.get("low_24h", price)
            volatility = ((high_24h - low_24h) / price * 100) if price > 0 else 0
            
            coin = CoinData(
                symbol=symbol.replace("USDT", ""),
                name=symbol.replace("USDT", ""),
                price=price,
                volume_24h=price_data.get("volume", 0) * price,
                market_cap=0,
                price_change_24h=price_data.get("price_change_24h", 0),
                price_change_7d=0,
                volatility=volatility,
                liquidity_score=price_data.get("volume", 0) / 1000
            )
            coins.append(coin)
        except Exception as e:
            print(f"   ⚠️  {symbol}: {e}")
    
    return coins


def detect_breakouts(coins, history_file="state/screening_history.json"):
    """Detect breakouts by comparing with historical data."""
    breakouts = []
    
    # Load history
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file) as f:
                history = json.load(f)
        except:
            pass
    
    if not history:
        return breakouts
    
    # Get previous data
    prev_data = history[-1].get("top_picks", [])
    prev_prices = {c["symbol"]: c["price"] for c in prev_data}
    prev_volumes = {c["symbol"]: c["volume_24h"] for c in prev_data}
    
    for coin in coins:
        symbol = coin.symbol
        alerts = []
        
        # Price breakout (>5% from last check)
        if symbol in prev_prices:
            price_change = (coin.price - prev_prices[symbol]) / prev_prices[symbol] * 100
            if price_change > 5:
                alerts.append(f"🚀 Price +{price_change:.1f}%")
            elif price_change < -5:
                alerts.append(f"🔻 Price {price_change:.1f}%")
        
        # Volume surge (>2x from last check)
        if symbol in prev_volumes and prev_volumes[symbol] > 0:
            vol_change = (coin.volume_24h - prev_volumes[symbol]) / prev_volumes[symbol] * 100
            if vol_change > 100:
                alerts.append(f"📈 Volume +{vol_change:.0f}%")
        
        # High volatility alert
        if coin.volatility > 15:
            alerts.append(f"⚡ Volatility {coin.volatility:.1f}%")
        
        # Strong momentum (>10% 24h)
        if coin.price_change_24h > 10:
            alerts.append(f"💪 Momentum +{coin.price_change_24h:.1f}% (24h)")
        
        if alerts:
            breakouts.append({
                "symbol": symbol,
                "price": coin.price,
                "alerts": alerts,
                "score": coin.screen_score
            })
    
    return breakouts


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
    
    # Detect breakouts
    breakouts = detect_breakouts(coins)
    
    print("\n" + "="*80)
    print("🏆 TOP OPPORTUNITIES")
    print("="*80)
    print(f"{'Rank':<6}{'Coin':<10}{'Price':<15}{'24h Change':<12}{'Volume':<15}{'Score':<8}")
    print("-"*80)
    
    for i, coin in enumerate(top_picks, 1):
        change_str = f"{coin.price_change_24h:+.2f}%" if coin.price_change_24h != 0 else "N/A"
        print(f"{i:<6}{coin.symbol:<10}${coin.price:<14.2f}{change_str:<12}{coin.volume_24h:>13.0f} {coin.screen_score:>6.2f}")
    
    print("="*80)
    
    # Breakout alerts
    if breakouts:
        print("\n🚨 BREAKOUT ALERTS:")
        for b in breakouts[:5]:
            print(f"   {b['symbol']} @ ${b['price']:.2f}")
            for alert in b['alerts']:
                print(f"      {alert}")
    
    # Trending up
    trending = [c for c in coins if c.price_change_24h > 5]
    trending = sorted(trending, key=lambda x: x.price_change_24h, reverse=True)
    if trending:
        print("\n📈 TRENDING UP (>5% 24h):")
        for coin in trending[:5]:
            print(f"   {coin.symbol}: +{coin.price_change_24h:.2f}% | Vol: ${coin.volume_24h/1e6:.1f}M")
    
    # Save results
    state = {
        "timestamp": datetime.now().isoformat(),
        "total_coins": len(coins),
        "top_picks": [c.to_dict() for c in top_picks],
        "all_results": [c.to_dict() for c in results],
        "breakouts": breakouts,
        "trending": [{"symbol": c.symbol, "change": c.price_change_24h} for c in trending[:5]]
    }
    
    # Save current screening
    with open("state/screening_results.json", "w") as f:
        json.dump(state, f, indent=2)
    
    # Append to history
    history_file = "state/screening_history.json"
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file) as f:
                history = json.load(f)
        except:
            pass
    
    history.append(state)
    # Keep last 168 entries (7 days at hourly screening)
    history = history[-168:]
    
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)
    
    print(f"\n💾 Results saved to state/screening_results.json")
    print(f"📊 History saved ({len(history)} entries)")
    print("\n" + "="*80)
    
    return top_picks, breakouts


if __name__ == '__main__':
    run_screening()
