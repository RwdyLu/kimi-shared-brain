# Final backtest validation report
from backtest.runner import run_backtest
from datetime import datetime, timedelta
import json

start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
end = datetime.now().strftime('%Y-%m-%d')

strategies = [
    'rsi_mid_bounce',
    'ma_cross_trend', 
    'ema_cross_fast',
    'rsi_trend',
    'hilbert_cycle',
]

results = []

for strat in strategies:
    try:
        result = run_backtest(
            symbols=['BTCUSDT'],
            start_date=start,
            end_date=end,
            strategy_id=strat,
            initial_capital=1000,
            commission_pct=0.1,
        )
        results.append({
            'strategy': strat,
            'trades': result.total_trades,
            'win_rate': result.win_rate,
            'return_pct': result.total_return_pct,
            'max_dd': result.max_drawdown_pct,
        })
        print(f"✅ {strat}: {result.total_trades} trades, {result.win_rate:.1f}% WR, Return: {result.total_return_pct:+.2f}%")
    except Exception as e:
        print(f"❌ {strat}: ERROR - {e}")
        results.append({'strategy': strat, 'error': str(e)})

# Save results
with open('/tmp/backtest_validation_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print(f"\nResults saved to /tmp/backtest_validation_results.json")
