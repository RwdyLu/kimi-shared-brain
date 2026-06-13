# T-053-C: Dashboard Backtest Visualization

**Task ID**: T-053-C  
**Type**: Enhancement  
**Priority**: High  
**Date**: 2026-04-14

---

## Summary

Added backtest results visualization to the Dashboard page. Now displays key metrics from the latest backtest run including win rate, total return, max drawdown, and backtest details.

---

## Changes Made

### `ui/pages/dashboard.py`

#### New Layout Section: Backtest Results

Added between Quick Actions and end of layout:

```
Dashboard
├── Live Prices
├── Status Cards
├── Active Symbols
├── Strategy Distance Panel
├── Recent Run History
├── Recent Signals
├── Quick Actions
└── Backtest Results (NEW)  ← T-053-C
    ├── Win Rate Card
    ├── Total Return Card
    ├── Max Drawdown Card
    ├── Latest Run ID Card
    └── View Full Report Button
```

**4 Summary Cards**:

| Card | Metric | Format |
|------|--------|--------|
| Win Rate / 勝率 | Win rate % + trade count | `60.0%` + `5 trades (3 wins)` |
| Total Return / 總報酬 | Return % with color | `+8.50%` (green) or `-5.20%` (red) |
| Max Drawdown / 最大回撤 | Drawdown % | `4.25%` (always red) |
| Latest Run / 最新執行 | Backtest ID + symbols | `BT20260414...` + `BTCUSDT, ETHUSDT` |

#### New Callback: `update_backtest_summary()`

**Outputs** (8):
1. `backtest-win-rate` - Win rate percentage
2. `backtest-trade-count` - Trade count with win breakdown
3. `backtest-return` - Total return percentage
4. `backtest-return` (className) - Color class (green/red)
5. `backtest-period` - Date range (start ~ end)
6. `backtest-drawdown` - Max drawdown percentage
7. `backtest-latest-id` - Backtest ID
8. `backtest-symbols` - Symbols tested

**Data Source**:
```python
from backtest import BacktestStorage
storage = BacktestStorage()
backtests = storage.get_latest_backtests(limit=1)
```

**Empty State**:
When no backtests exist:
- All cards show "--"
- Subtext: "No backtests yet / 尚無回測"
- Button still links to backtest page

#### Visual Design

**Win Rate Card**:
- Color: `text-info` (blue)
- Shows: Win rate % + trade breakdown

**Return Card**:
- Dynamic color:
  - Positive: `text-success` (green)
  - Negative: `text-danger` (red)
- Shows: Return % with +/- sign

**Drawdown Card**:
- Color: `text-danger` (red, always)
- Shows: Drawdown %

**Latest Run Card**:
- Color: `text-primary` (blue)
- Shows: Backtest ID + symbols list

---

## Dashboard Page Structure (Updated)

```
Dashboard
├── Header
├── Live Prices (BTC/ETH cards)          ← T-052-A
├── Status Cards (System/Last Run/Signals)
├── Active Symbols
├── Strategy Distance Panel               ← T-052-C
├── Recent Run History
├── Recent Signals
├── Quick Actions
├── Backtest Results Section (NEW)        ← T-053-C
│   ├── Win Rate Card
│   ├── Total Return Card
│   ├── Max Drawdown Card
│   ├── Latest Run Card
│   └── View Full Report Button → /backtest
└── Auto-refresh interval (15s)
```

---

## Data Flow

```
Dashboard loads
    ↓
Callback triggered (15s interval or page load)
    ↓
BacktestStorage.get_latest_backtests(limit=1)
    ↓
Read backtest/backtest_results.jsonl
    ↓
Parse latest backtest summary
    ↓
Extract metrics (win_rate, total_return_pct, etc.)
    ↓
Format display strings
    ↓
Update 8 card outputs
    ↓
UI displays results
```

---

## Error Handling

- **No backtests**: Shows "--" and helpful message
- **File not found**: Handled by BacktestStorage (returns empty list)
- **Parse error**: Shows truncated error message
- **Exception**: Shows "Check backtest module"

---

## Usage

### View Results
1. Open Dashboard page
2. Scroll to "Backtest Results / 回測結果" section
3. See latest backtest metrics
4. Click "View Full Report" for detailed page (T-053-D)

### Run New Backtest
```python
from backtest.runner import run_backtest

summary = run_backtest(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-01-31"
)
```
Refresh Dashboard to see new results.

---

## Dependencies

- **T-053-A**: BacktestStorage class
- **T-053-B**: Backtest results JSONL file format

---

## Testing

- [x] Layout renders without errors
- [x] Callback imports BacktestStorage successfully
- [x] Empty state displays correctly
- [ ] With backtest data (requires running backtest)

---

## Next Steps

- **T-053-D**: Full backtest report page at `/backtest`
  - Detailed trade list
  - Equity curve chart
  - Symbol breakdown
  - Export functionality

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/dashboard.py` | Added Backtest Results section + callback |

---
