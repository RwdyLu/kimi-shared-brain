#!/usr/bin/env python3
"""
Batch Backtest Open Source Strategies - Simulation Mode
Generates simulated backtest results for ranking demonstration.
In production, integrate with real backtest runner.
"""

import json
import random
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_strategies():
    """Load open source strategies."""
    with open('config/strategies_open_source.json') as f:
        data = json.load(f)
    return data['strategies']


def simulate_backtest(strategy):
    """
    Simulate backtest results for demonstration.
    In production, replace with real backtest runner.
    """
    print(f"\n🔍 Backtesting: {strategy['name']} ({strategy['id']})")
    
    # Seed random for reproducibility
    random.seed(hash(strategy['id']) % 10000)
    
    # Simulate realistic results based on strategy type
    strategy_type = strategy['type']
    
    # Different strategy types have different risk/return profiles
    type_profiles = {
        'momentum': {'return_range': (-5, 15), 'sharpe_range': (-0.5, 1.5), 'win_rate_range': (40, 60)},
        'mean_reversion': {'return_range': (-3, 12), 'sharpe_range': (-0.3, 1.2), 'win_rate_range': (45, 65)},
        'breakout': {'return_range': (-8, 20), 'sharpe_range': (-0.8, 2.0), 'win_rate_range': (35, 55)},
        'trend': {'return_range': (-5, 18), 'sharpe_range': (-0.5, 1.8), 'win_rate_range': (40, 60)},
        'volume': {'return_range': (-4, 14), 'sharpe_range': (-0.4, 1.3), 'win_rate_range': (42, 58)},
        'cycle': {'return_range': (-10, 25), 'sharpe_range': (-1.0, 2.5), 'win_rate_range': (30, 50)},
        'composite': {'return_range': (-3, 10), 'sharpe_range': (-0.3, 1.0), 'win_rate_range': (48, 62)},
    }
    
    profile = type_profiles.get(strategy_type, type_profiles['momentum'])
    
    # Generate metrics
    total_return = random.uniform(*profile['return_range'])
    sharpe_ratio = random.uniform(*profile['sharpe_range'])
    win_rate = random.uniform(*profile['win_rate_range'])
    max_drawdown = random.uniform(-15, -2)  # Negative for drawdown
    total_trades = random.randint(50, 300)
    profit_factor = random.uniform(0.8, 2.5)
    
    metrics = {
        'strategy_id': strategy['id'],
        'name': strategy['name'],
        'type': strategy['type'],
        'total_return': round(total_return, 2),
        'sharpe_ratio': round(sharpe_ratio, 2),
        'max_drawdown': round(max_drawdown, 2),
        'win_rate': round(win_rate, 1),
        'profit_factor': round(profit_factor, 2),
        'total_trades': total_trades,
        'avg_profit_per_trade': round(total_return / total_trades if total_trades > 0 else 0, 3),
        'status': 'completed'
    }
    
    print(f"   ✅ Return: {metrics['total_return']:.2f}% | Sharpe: {metrics['sharpe_ratio']:.2f} | "
          f"Win Rate: {metrics['win_rate']:.1f}% | Trades: {metrics['total_trades']}")
    
    return metrics


def rank_strategies(results):
    """Rank strategies by composite score."""
    completed = [r for r in results if r['status'] == 'completed']
    
    if not completed:
        print("\n⚠️ No successful backtests!")
        return []
    
    # Calculate composite score
    # Score = (sharpe * 0.35) + (win_rate/100 * 0.25) + (total_return * 0.02) - (abs(max_drawdown) * 0.01)
    for r in completed:
        sharpe = max(r['sharpe_ratio'], -5)
        win_rate = r['win_rate'] / 100.0
        returns = r['total_return'] / 100.0
        drawdown_penalty = abs(r['max_drawdown']) / 100.0
        
        r['composite_score'] = (
            sharpe * 0.35 +
            win_rate * 0.30 +
            returns * 0.20 -
            drawdown_penalty * 0.15
        )
    
    # Sort by composite score
    ranked = sorted(completed, key=lambda x: x['composite_score'], reverse=True)
    
    return ranked


def print_ranking(ranked):
    """Print ranking table."""
    print("\n" + "="*90)
    print("🏆 STRATEGY RANKING RESULTS")
    print("="*90)
    print(f"{'Rank':<6}{'Strategy':<28}{'Type':<14}{'Return':<10}{'Sharpe':<8}{'Win%':<8}{'DD':<8}{'Trades':<8}{'Score':<8}")
    print("-"*90)
    
    for i, r in enumerate(ranked, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        return_str = f"{r['total_return']:>+.2f}%"
        print(f"{medal} {i:<4}{r['name']:<28}{r['type']:<14}"
              f"{return_str:<10}{r['sharpe_ratio']:>6.2f}  "
              f"{r['win_rate']:>5.1f}% {r['max_drawdown']:>6.2f}% "
              f"{r['total_trades']:>6} {r['composite_score']:>6.2f}")
    
    print("="*90)
    
    # Top 3 recommendation
    print("\n📊 TOP 3 RECOMMENDED:")
    for i, r in enumerate(ranked[:3], 1):
        print(f"   {i}. {r['name']} (Score: {r['composite_score']:.2f})")
        print(f"      Return: {r['total_return']:+.2f}% | Sharpe: {r['sharpe_ratio']:.2f} | "
              f"Win Rate: {r['win_rate']:.1f}% | Max DD: {r['max_drawdown']:.2f}% | "
              f"Profit Factor: {r['profit_factor']:.2f}")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_strategies': len(ranked),
        'ranking': ranked
    }
    
    with open('state/strategy_ranking.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Results saved to state/strategy_ranking.json")


def print_strategy_details(ranked):
    """Print detailed analysis."""
    print("\n📈 STRATEGY TYPE ANALYSIS:")
    
    type_stats = {}
    for r in ranked:
        t = r['type']
        if t not in type_stats:
            type_stats[t] = []
        type_stats[t].append(r)
    
    for t, strategies in sorted(type_stats.items(), key=lambda x: sum(s['composite_score'] for s in x[1])/len(x[1]), reverse=True):
        avg_score = sum(s['composite_score'] for s in strategies) / len(strategies)
        avg_return = sum(s['total_return'] for s in strategies) / len(strategies)
        print(f"\n   {t.upper()}:")
        print(f"      Average Score: {avg_score:.2f} | Average Return: {avg_return:+.2f}%")
        for s in strategies:
            print(f"      - {s['name']}: Score {s['composite_score']:.2f}")


def main():
    """Run batch backtest."""
    print("="*90)
    print("🚀 BATCH BACKTEST: 10 Open Source Strategies")
    print("="*90)
    print(f"Started: {datetime.now()}")
    print("\n⚠️  NOTE: Using simulated results for demonstration.")
    print("   In production, integrate with real backtest runner.")
    
    # Load strategies
    strategies = load_strategies()
    print(f"\n📋 Loaded {len(strategies)} strategies")
    
    # Run backtests
    results = []
    for strategy in strategies:
        result = simulate_backtest(strategy)
        results.append(result)
    
    # Rank
    ranked = rank_strategies(results)
    
    if ranked:
        print_ranking(ranked)
        print_strategy_details(ranked)
    
    # Summary
    total = len(results)
    completed = len([r for r in results if r['status'] == 'completed'])
    
    print(f"\n📈 Summary: {completed}/{total} passed")
    print(f"Finished: {datetime.now()}")
    print("="*90)


if __name__ == '__main__':
    main()
