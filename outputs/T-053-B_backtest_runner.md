# T-053-B: Backtest Execution Engine

**Task ID**: T-053-B  
**Type**: Implementation  
**Priority**: High  
**Date**: 2026-04-14

---

## Summary

Implemented the backtest execution engine that fetches historical data, simulates trades based on signals, and calculates performance metrics including win rate, returns, and drawdown.

---

## Changes Made

### `backtest/runner.py`

#### Core Class: `BacktestRunner`

**Initialization**:
```python
def __init__(self, config: BacktestConfig):
    self.config = config
    self.storage = BacktestStorage()
    self.fetcher = BinanceFetcher()
    self.signal_engine = SignalEngine()
```

**State Tracking**:
- `active_trades`: Dictionary of currently open trades by symbol
- `closed_trades`: List of completed trades
- `equity_curve`: Equity over time for charting
- `current_equity`: Running capital value
- `peak_equity`: Highest equity reached (for drawdown calc)
- `max_drawdown`: Maximum peak-to-trough decline

#### Main Method: `run()`

**Flow**:
```
1. Print backtest header
2. For each symbol:
   a. Fetch historical klines from Binance
   b. Calculate indicators (MA5, MA20, MA240)
   c. Process each candle:
      - Check exit conditions on active trade
      - Check entry signals (if no active trade)
      - Update equity curve
3. Close all remaining trades at end
4. Build and save summary
5. Print results
```

#### Trade Management

**Entry**: `_check_entry_signals()`
- Gets signals from SignalEngine
- Opens LONG trade on confirmed LONG signal
- Opens SHORT trade on confirmed SHORT signal
- Creates TradeRecord with entry details

**Exit**: `_check_exit_conditions()`
Checks multiple exit triggers:
1. **Stop Loss**: Price hits configured % below (long) or above (short) entry
2. **Take Profit**: Price hits configured % above (long) or below (short) entry
3. **Reverse Signal**: Opposite direction signal appears
4. **End of Test**: Close all at backtest end

**P&L Calculation**:
```python
# Long trade
pnl_pct = ((exit_price - entry_price) / entry_price) * 100

# Short trade
pnl_pct = ((entry_price - exit_price) / entry_price) * 100
```

#### Data Fetching: `_fetch_historical_data()`

**Parameters**:
- Symbol: BTCUSDT or ETHUSDT
- Interval: 4h (consistent with live monitoring)
- Date range: start_date to end_date

**Process**:
1. Convert dates to millisecond timestamps
2. Call Binance API via `fetcher.get_historical_klines()`
3. Convert to DataFrame
4. Calculate SMA indicators

#### Metrics Calculation: `_build_summary()`

**Trade Statistics**:
- `total_trades`: Count of closed trades
- `winning_trades`: Count with positive P&L
- `losing_trades`: Count with negative P&L
- `win_rate`: winning_trades / total_trades

**Returns**:
- `total_return_pct`: (final - initial) / initial * 100

**Risk Metrics**:
- `max_drawdown_pct`: Largest peak-to-trough decline

**Symbol Breakdown**:
Per-symbol stats with trade count and total P&L

### Convenience Function: `run_backtest()`

**Simplified API**:
```python
summary = run_backtest(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-01-31",
    initial_capital=10000.0,
    stop_loss_pct=5.0,
    take_profit_pct=10.0
)
```

---

## Output Format

### Console Output Example
```
======================================================================
🔄 BACKTEST START / 回測開始
======================================================================
Backtest ID: BT20260414231530
Period: 2024-01-01 ~ 2024-01-31
Symbols: BTCUSDT, ETHUSDT
Initial Capital: $10,000.00
======================================================================

📊 Processing BTCUSDT...
   ✓ Loaded 186 candles
   ➡️  ENTRY: LONG @ $42,500.00 (2024-01-05 08:00)
   ✅ EXIT: $45,200.00 | P&L: +6.35% (take_profit)
   ➡️  ENTRY: SHORT @ $44,800.00 (2024-01-15 12:00)
   ❌ EXIT: $45,500.00 | P&L: -1.56% (stop_loss)

📊 Processing ETHUSDT...
   ✓ Loaded 186 candles

======================================================================
📊 BACKTEST RESULTS / 回測結果
======================================================================
Backtest ID: BT20260414231530
Period: 2024-01-01 ~ 2024-01-31
======================================================================

💰 PERFORMANCE / 績效
   Initial Capital: $10,000.00
   Final Equity:    $10,850.00
   Total Return:    +8.50%

📈 TRADE STATISTICS / 交易統計
   Total Trades:    5
   Winning Trades:  3
   Losing Trades:   2
   Win Rate:        60.0%

⚠️  RISK METRICS / 風險指標
   Max Drawdown:    4.25%

📊 SYMBOL BREAKDOWN / 標的明細
   BTCUSDT: 3 trades, +12.50%
   ETHUSDT: 2 trades, -4.00%

======================================================================
✅ BACKTEST COMPLETE / 回測完成
======================================================================
```

### Data Files

**backtest_results.jsonl**:
```json
{"type": "summary", "timestamp": "2026-04-14T23:15:30", "data": {
  "backtest_id": "BT20260414231530",
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "strategy": "ma_cross",
  "total_trades": 5,
  "winning_trades": 3,
  "losing_trades": 2,
  "win_rate": 60.0,
  "total_return_pct": 8.5,
  "max_drawdown_pct": 4.25,
  "equity_curve": [...]
}}
```

**trade_history.jsonl**:
```json
{"type": "trade", "timestamp": "2026-04-14T23:15:30", "data": {
  "trade_id": "BT20260414231530_BTCUSDT_0",
  "symbol": "BTCUSDT",
  "direction": "long",
  "entry_time": "2024-01-05 08:00",
  "entry_price": 42500.0,
  "exit_time": "2024-01-08 12:00",
  "exit_price": 45200.0,
  "pnl_pct": 6.35,
  "result": "closed_profit"
}}
```

---

## Dependencies

- **T-053-A**: Uses BacktestConfig, BacktestSummary, BacktestStorage, TradeRecord
- **data.fetcher**: BinanceFetcher for historical data
- **indicators**: Module functions for SMA calculation
- **signals.engine**: SignalEngine for signal generation

---

## Usage

### Command Line
```bash
python backtest/runner.py
```

Runs the example backtest at bottom of file.

### Programmatic
```python
from backtest.runner import run_backtest

summary = run_backtest(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-01-31",
    initial_capital=10000.0,
    stop_loss_pct=5.0,
    take_profit_pct=10.0
)

print(f"Win Rate: {summary.win_rate}%")
print(f"Return: {summary.total_return_pct}%")
```

---

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | List[str] | ["BTCUSDT", "ETHUSDT"] | Symbols to test |
| `start_date` | str | 30 days ago | Start date (YYYY-MM-DD) |
| `end_date` | str | Today | End date (YYYY-MM-DD) |
| `initial_capital` | float | 10000.0 | Starting capital |
| `position_size_pct` | float | 100.0 | % of capital per trade |
| `stop_loss_pct` | float | None | Stop loss % (e.g., 5.0) |
| `take_profit_pct` | float | None | Take profit % (e.g., 10.0) |

---

## Testing

- [x] Imports verified
- [x] Config creation works
- [x] Storage initialization works
- [ ] Full backtest run (requires API key for historical data)

---

## Next Steps

- **T-053-C**: Dashboard visualization (equity curve chart, trade list)
- **T-053-D**: Backtest report page (detailed statistics, export)

---

## Files Modified

| File | Changes |
|------|---------|
| `backtest/runner.py` | New file - backtest execution engine |
| `backtest/__init__.py` | Fixed imports (removed non-existent classes) |

---
