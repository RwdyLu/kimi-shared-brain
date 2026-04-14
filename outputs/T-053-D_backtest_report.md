# T-053-D: Backtest Report Page

**Task ID**: T-053-D  
**Type**: Implementation  
**Priority**: High  
**Date**: 2026-04-14

---

## Summary

Created a comprehensive backtest report page with detailed analysis, trade history, and export functionality. Users can now view complete backtest results, browse historical runs, and export data for further analysis.

---

## Changes Made

### `ui/pages/backtest.py` (New)

#### Page Structure

```
Backtest Report Page
├── Header / 標題
├── Backtest Selector / 回測選擇器
│   ├── Dropdown (latest 20 backtests)
│   └── Quick Select buttons (Latest, Refresh)
├── Summary Cards (4)
│   ├── Period / 期間
│   ├── Total Return / 總報酬 (color-coded)
│   ├── Win Rate / 勝率
│   └── Max Drawdown / 最大回撤
├── Trade Statistics
│   ├── Total Trades
│   ├── Winning / 盈利
│   ├── Losing / 虧損
│   └── Symbols Count
├── Symbol Breakdown / 標的明細
│   └── Per-symbol trade count and P&L
├── Trade History / 交易歷史
│   └── List of all trades with details
├── Export Button
└── Auto-refresh (30s)
```

#### Features

**1. Backtest Selector**
- Dropdown showing up to 20 latest backtests
- Format: `{ID} ({start}~{end}) [{return}%]`
- Auto-selects latest on load
- "Latest" and "Refresh" buttons

**2. Summary Cards**
| Card | Content | Format |
|------|---------|--------|
| Period | Date range + duration | `2024-01-01 ~ 2024-01-31` (30 days) |
| Return | Total return % | `+8.50%` (green) or `-5.20%` (red) |
| Win Rate | Win percentage | `60.0%` |
| Drawdown | Max drawdown % | `4.25%` (red) |

**3. Trade Statistics**
- Total trades count
- Winning trades (green)
- Losing trades (red)
- Number of symbols tested

**4. Symbol Breakdown**
- Per-symbol statistics
- Trade count per symbol
- Total P&L per symbol (color-coded)

**5. Trade History Table**
Columns:
- Symbol
- Direction (LONG/SHORT)
- Entry Price
- Exit Price
- P&L % (color-coded)
- Result (WIN/LOSS badge)

**6. Export Function**
- Exports selected backtest to JSON
- Filename: `{backtest_id}_report.json`
- Includes all backtest data

#### Callbacks

**`update_backtest_list()`**
- Loads latest 20 backtests from storage
- Builds dropdown options
- Maintains current selection on refresh

**`update_backtest_details()`**
- Main callback for page updates
- 14 outputs covering all display elements
- Loads trade history for selected backtest
- Formats all metrics for display

**`export_backtest()`**
- Triggered by Export button
- Uses `dcc.Download` for file download
- Serializes backtest data to JSON

### `ui/app.py`

#### Navigation Update

Added "Backtest" link to navbar:
```python
dbc.NavItem(dbc.NavLink("Backtest", href="/backtest")),
```

Placed between "Signals" and "Parameters" for logical flow.

---

## Page Layout Details

### Responsive Design
- Uses `dbc.Row` and `dbc.Col` with breakpoints
- Cards stack on mobile (width=6 → width=12)
- Table columns adjust for screen size

### Color Coding
- **Green (success)**: Positive returns, winning trades
- **Red (danger)**: Negative returns, losing trades, drawdown
- **Blue (info)**: Win rate, neutral data

### Empty States
- "No backtest selected" shown initially
- "Backtest not found" for invalid IDs
- "No trades recorded" when no trade data

---

## Data Flow

```
User opens /backtest
    ↓
update_backtest_list callback
    ↓
Load backtests from backtest_results.jsonl
    ↓
Populate dropdown, select latest
    ↓
update_backtest_details callback (triggered by selection)
    ↓
Load backtest summary + trades
    ↓
Update all 14 display outputs
    ↓
Render complete report
```

---

## Usage

### View Backtest Report
1. Click "Backtest" in navigation
2. Select a backtest from dropdown (or click "Latest")
3. View summary cards, statistics, and trade list

### Export Data
1. Select backtest
2. Click "Export to JSON"
3. File downloads: `{backtest_id}_report.json`

### Refresh Data
- Click "Refresh" button
- Or wait for 30s auto-refresh

---

## Navigation Structure (Updated)

```
BTC/ETH Monitor
├── Dashboard    (/, T-052/T-053-C)
├── Signals      (/signals, T-026/T-052-D)
├── Backtest     (/backtest, T-053-D)  ← NEW
├── Parameters   (/parameters, T-039-05)
├── Strategies   (/strategies, T-020)
├── Actions      (/actions, T-039-06)
└── System       (/system, T-039-04)
```

---

## Dependencies

- **T-053-A**: BacktestStorage for data loading
- **T-053-B**: Backtest data format (JSONL)
- **T-053-C**: Dashboard link to this page
- **dash-bootstrap-components**: UI components

---

## Testing

- [x] Syntax validation passed
- [x] BacktestStorage import successful
- [x] All callbacks registered
- [x] Navigation link added
- [ ] Visual testing (requires running backtest)

---

## Future Enhancements (Optional)

- **Equity Curve Chart**: Plotly line chart of equity over time
- **Performance Charts**: Win rate by symbol, monthly returns
- **Compare Mode**: Side-by-side backtest comparison
- **Advanced Filters**: Filter trades by symbol, direction, result

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/backtest.py` | New file - complete backtest report page |
| `ui/app.py` | Added Backtest link to navigation |

---

## Complete T-053 Series

| Task | Description | Status |
|------|-------------|--------|
| T-053-A | Backtest storage structure | ✅ |
| T-053-B | Backtest execution engine | ✅ |
| T-053-C | Dashboard visualization | ✅ |
| T-053-D | Backtest report page | ✅ |

---
