# Quick backtest runner for validation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.runner import run_backtest
from datetime import datetime, timedelta

# Run backtest for the last 7 days on BTC
start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
end = datetime.now().strftime('%Y-%m-%d')

print(f"Running backtest: {start} ~ {end}")

try:
    result = run_backtest(
        symbols=["BTCUSDT"],
        start_date=start,
        end_date=end,
        strategy_id="rsi_mid_bounce",
        initial_capital=1000,
        commission_pct=0.1,
    )
    print(f"Backtest completed: {result.total_trades} trades, {result.win_rate:.1f}% win rate")
except Exception as e:
    print(f"Backtest error: {e}")
    import traceback
    traceback.print_exc()
