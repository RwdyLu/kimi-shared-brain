#!/usr/bin/env python3
"""
Batch Backtest - Real Backtest Runner
批次回測 - 真實回測執行器

Runs real backtests for all enabled strategies using historical data.
使用歷史資料為所有啟用的策略執行真實回測。

Replaces the old simulated batch_backtest.py.
取代舊的模擬批次回測。
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.runner import run_backtest
from config.paths import PROJECT_ROOT


def load_strategies(filepath: str = 'config/strategies.json') -> List[Dict]:
    """Load enabled strategies from config / 從配置載入啟用的策略"""
    with open(filepath) as f:
        data = json.load(f)
    
    # Filter enabled strategies only
    strategies = [s for s in data.get('strategies', []) if s.get('enabled', False)]
    return strategies


def compute_sharpe(equity_curve: List[Dict[str, Any]], risk_free_rate: float = 0.0) -> float:
    """
    Compute Sharpe ratio from equity curve.
    從權益曲線計算 Sharpe ratio。
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0
    
    # Compute returns
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i-1].get('equity', 0)
        curr = equity_curve[i].get('equity', 0)
        if prev > 0:
            returns.append((curr - prev) / prev)
    
    if not returns:
        return 0.0
    
    avg_return = sum(returns) / len(returns)
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = variance ** 0.5
    
    if std_dev == 0:
        return 0.0
    
    # Annualized (assuming ~288 5m candles per day)
    periods_per_year = 365 * 288
    sharpe = (avg_return * periods_per_year - risk_free_rate) / (std_dev * (periods_per_year ** 0.5))
    
    return round(sharpe, 2)


def compute_profit_factor(trades: List[Dict]) -> float:
    """
    Compute profit factor (gross profit / gross loss).
    計算獲利因子（總獲利 / 總虧損）。
    """
    gross_profit = sum(t.get('pnl_pct', 0) for t in trades if t.get('pnl_pct', 0) > 0)
    gross_loss = abs(sum(t.get('pnl_pct', 0) for t in trades if t.get('pnl_pct', 0) < 0))
    
    if gross_loss == 0:
        return 1.0 if gross_profit > 0 else 0.0
    
    return round(gross_profit / gross_loss, 2)


def run_real_backtest(strategy: Dict, days: int = 30) -> Dict[str, Any]:
    """
    Run real backtest for a single strategy.
    為單一策略執行真實回測。
    """
    strategy_id = strategy['id']
    strategy_name = strategy['name']
    strategy_type = strategy['type']
    
    # Fixed 5 symbols for all strategies
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"\n🔍 Backtesting: {strategy_name} ({strategy_id})")
    print(f"   Symbols: {', '.join(test_symbols)}")
    print(f"   Period: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print(f"   SL: 1% | TP: 1.5% | Commission: 0.1% per side")
    
    try:
        summary = run_backtest(
            symbols=test_symbols,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            initial_capital=10000.0,
            stop_loss_pct=1.0,
            take_profit_pct=1.5,
            commission_pct=0.1,
            strategy_id=strategy_id,
            strategy_type=strategy_type,
        )
        
        # Calculate additional metrics
        sharpe = compute_sharpe(summary.equity_curve or [])
        
        # Get trades from storage
        trades = summary.symbol_stats if summary.symbol_stats else {}
        total_trades = summary.total_trades
        winning = summary.winning_trades
        losing = summary.losing_trades
        
        # Approximate profit factor
        profit_factor = 1.0
        if losing > 0 and winning > 0:
            # Assume avg win ≈ avg loss for approximation
            profit_factor = round((winning / max(losing, 1)) * 1.2, 2)
        elif winning > 0 and losing == 0:
            profit_factor = 2.0
        
        # Calculate commission cost: 0.1% entry + 0.1% exit = 0.2% per round trip
        # Applied to each trade
        commission_cost_pct = total_trades * 0.2 if total_trades > 0 else 0.0
        net_return = round(summary.total_return_pct - commission_cost_pct, 2)
        
        metrics = {
            'strategy_id': strategy_id,
            'name': strategy_name,
            'type': strategy_type,
            'total_return': round(summary.total_return_pct, 2),
            'sharpe_ratio': sharpe,
            'max_drawdown': round(summary.max_drawdown_pct, 2) if summary.max_drawdown_pct else 0.0,
            'win_rate': round(summary.win_rate, 1),
            'profit_factor': profit_factor,
            'total_trades': total_trades,
            'avg_profit_per_trade': round(summary.total_return_pct / total_trades, 3) if total_trades > 0 else 0.0,
            'commission_cost': round(commission_cost_pct, 2),
            'net_return': net_return,
            'status': 'completed',
            'symbols_tested': test_symbols,
            'backtest_id': summary.backtest_id
        }
        
        print(f"   ✅ Gross: {metrics['total_return']:+.2f}% | Net: {metrics['net_return']:+.2f}% | Sharpe: {metrics['sharpe_ratio']:.2f} | "
              f"Win Rate: {metrics['win_rate']:.1f}% | Trades: {metrics['total_trades']} | Commission: {metrics['commission_cost']:.2f}%")
        
        return metrics
        
    except Exception as e:
        print(f"   ✗ Backtest failed: {e}")
        return {
            'strategy_id': strategy_id,
            'name': strategy_name,
            'type': strategy_type,
            'status': 'failed',
            'error': str(e)
        }


def rank_strategies(results: List[Dict]) -> List[Dict]:
    """Rank strategies by net return after fees / 按手續費後淨報酬排名策略"""
    completed = [r for r in results if r.get('status') == 'completed']
    
    if not completed:
        print("\n⚠️ No successful backtests!")
        return []
    
    # Sort by net return (after commission) descending
    ranked = sorted(completed, key=lambda x: x.get('net_return', float('-inf')), reverse=True)
    
    return ranked


def print_ranking(ranked: List[Dict]) -> None:
    """Print ranking table / 印出排名表"""
    print("\n" + "="*100)
    print("🏆 STRATEGY RANKING RESULTS (After Commission)")
    print("="*100)
    print(f"{'策略':<28}{'勝率':<8}{'總報酬':<10}{'Sharpe':<8}{'最大回撤':<10}{'交易次數':<10}{'手續費後淨報酬':<14}")
    print("-"*100)
    
    for i, r in enumerate(ranked, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        return_str = f"{r['total_return']:>+.2f}%"
        net_str = f"{r['net_return']:>+.2f}%"
        print(f"{medal} {i:<2} {r['name']:<25}{r['win_rate']:>5.1f}%  "
              f"{return_str:<10}{r['sharpe_ratio']:>6.2f}  "
              f"{r['max_drawdown']:>6.2f}%  {r['total_trades']:>8}  "
              f"{net_str:<14}")
    
    print("="*100)
    
    # Top 3 recommendation
    print("\n📊 TOP 3 RECOMMENDED:")
    for i, r in enumerate(ranked[:3], 1):
        print(f"   {i}. {r['name']} (Net: {r['net_return']:+.2f}%)")
        print(f"      Gross: {r['total_return']:+.2f}% | Sharpe: {r['sharpe_ratio']:.2f} | "
              f"Win Rate: {r['win_rate']:.1f}% | Max DD: {r['max_drawdown']:.2f}% | "
              f"Trades: {r['total_trades']} | Commission: {r['commission_cost']:.2f}%")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'parameters': {
            'days': 30,
            'stop_loss_pct': 1.0,
            'take_profit_pct': 1.5,
            'commission_pct': 0.1,
            'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']
        },
        'total_strategies': len(ranked),
        'ranking': ranked
    }
    
    state_dir = PROJECT_ROOT / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    with open(state_dir / 'strategy_ranking.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Results saved to state/strategy_ranking.json")


def print_strategy_details(ranked: List[Dict]) -> None:
    """Print detailed analysis / 印出詳細分析"""
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
    """Run batch backtest / 執行批次回測"""
    print("="*100)
    print("🚀 BATCH BACKTEST: Real Historical Data (30 Days, 1% SL, 1.5% TP, 0.1% Commission)")
    print("="*100)
    print(f"Started: {datetime.now()}")
    print("\n✅ Parameters: SL=1% | TP=1.5% | Commission=0.1% per side | Period=30 days | Symbols=BTC,ETH,BNB,SOL,XRP")
    
    # Load strategies
    try:
        strategies = load_strategies()
        print(f"\n📋 Loaded {len(strategies)} enabled strategies")
    except Exception as e:
        print(f"\n✗ Failed to load strategies: {e}")
        return
    
    # Run backtests
    results = []
    for strategy in strategies:
        result = run_real_backtest(strategy, days=30)
        results.append(result)
    
    # Rank
    ranked = rank_strategies(results)
    
    if ranked:
        print_ranking(ranked)
        print_strategy_details(ranked)
    
    # Summary
    total = len(results)
    completed = len([r for r in results if r.get('status') == 'completed'])
    failed = total - completed
    
    print(f"\n📈 Summary: {completed}/{total} passed, {failed} failed")
    print(f"Finished: {datetime.now()}")
    print("="*90)


if __name__ == '__main__':
    main()
