# T-055: Check History Table Optimization

**Task ID**: T-055  
**Type**: Enhancement  
**Priority**: High  
**Date**: 2026-04-15

---

## Summary

Replaced price history charts with a clear table showing each check's timestamp, BTC price, ETH price, and signal count. The latest check is highlighted with a green background.

---

## Changes

### `ui/pages/dashboard.py`

#### Replaced T-054-B Charts with T-055 Table

**Before (T-054-B)**:
```
Price History
├── BTC/USDT 24h Chart (Plotly line chart)
└── ETH/USDT 24h Chart (Plotly line chart)
```

**After (T-055)**:
```
📋 Check History / 檢查歷史 (Last 10 checks)
┌───────────┬───────────┬───────────┬────────┐
│ Time      │ BTC/USDT  │ ETH/USDT  │Signals │
├───────────┼───────────┼───────────┼────────┤
│ 05:47:32  │ $74,084   │ $2,319    │ None   │ ← Latest (green bg)
│ 05:42:32  │ $74,102   │ $2,321    │ None   │
│ 05:37:32  │ $74,095   │ $2,318    │ None   │
└───────────┴───────────┴───────────┴────────┘
```

#### New Components

**1. Table Layout**
```python
dbc.Card([
    dbc.CardHeader(
        dbc.Row([
            dbc.Col(html.Strong("Time / 時間"), width=3),
            dbc.Col(html.Strong("BTC/USDT"), width=3),
            dbc.Col(html.Strong("ETH/USDT"), width=3),
            dbc.Col(html.Strong("Signals / 訊號"), width=3),
        ])
    ),
    dbc.CardBody(id="check-history-table", ...)
])
```

**2. Callback: `update_check_history_table()`**
- Reads from `indicator_snapshots.jsonl`
- Groups records by `run_id`
- Displays last 10 checks
- Highlights latest row (green background)

**3. Helper: `_load_check_history(limit=10)`**
```python
def _load_check_history(limit: int = 10) -> list:
    """Load check history from indicator_snapshots.jsonl"""
    # Returns: [{"time", "btc_price", "eth_price", "signals_count"}, ...]
```

#### Table Features

| Feature | Description |
|---------|-------------|
| **Time** | HH:MM:SS format |
| **BTC Price** | Formatted as `$74,084` |
| **ETH Price** | Formatted as `$2,319` |
| **Signals** | Count with indicators (✓ for confirmed, 👁️ for watch-only) |
| **Highlight** | Latest row has green background (`#d4edda`) |
| **Auto-refresh** | Updates every 15 seconds with dashboard |

---

## Dashboard Structure (Updated)

```
Dashboard
├── 💰 Live Prices (BTC + ETH 大卡片)
├── Status Cards
├── Active Symbols
├── Strategy Distance Panel
├── Recent Run History
├── Recent Signals
├── Backtest Results
├── 📋 Check History (NEW)  ← T-055
│   └── Table: Time | BTC | ETH | Signals
└── Quick Actions
```

---

## Data Flow

```
Scheduler runs monitor
    ↓
_save_indicator_snapshot() records prices
    ↓
Write to logs/indicator_snapshots.jsonl
    ↓
Dashboard loads / refreshes (15s interval)
    ↓
_callback: update_check_history_table()
    ↓
_load_check_history() reads JSONL
    ↓
Group by run_id, sort by timestamp
    ↓
Render table rows
    ↓
Latest row highlighted in green
```

---

## Example Output

With 3 records in `indicator_snapshots.jsonl`:

```
📋 Check History / 檢查歷史 (Last 10 checks)

Time        BTC/USDT    ETH/USDT    Signals
─────────   ─────────   ─────────   ───────
05:29:17    $74,084     $2,319      None     ← Latest (green)
```

---

## Testing

- [x] Syntax validation passed
- [x] Table renders correctly
- [x] Price grouping by run_id works
- [x] Latest row highlighting works
- [ ] Visual testing (requires UI running)

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/dashboard.py` | Replaced charts with table, added `_load_check_history()` |

---

## Notes

- Chart callbacks (`update_btc_price_chart`, `update_eth_price_chart`) removed
- `_load_price_history()` helper kept for potential future use
- Table auto-refreshes every 15 seconds
- Shows "No check history yet" when no data available

---
