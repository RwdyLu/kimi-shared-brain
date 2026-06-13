# T-054: Price History Logging and Visualization

**Task ID**: T-054 (Series)  
**Type**: Implementation  
**Priority**: High  
**Date**: 2026-04-15

---

## Summary

Successfully implemented price history recording and visualization across the monitoring system. The scheduler now records price data after each run, and the UI displays this data in charts and run history.

---

## T-054-A: Scheduler Price Logging

### Status: ✅ COMPLETED

**Changes**:
- Verified `_save_indicator_snapshot()` is called in `monitor_runner.py`
- Created `start_scheduler.py` helper script
- Confirmed price data is written to `indicator_snapshots.jsonl`

**Verified Data Format**:
```json
{
  "run_id": "#1776202157",
  "timestamp": "2026-04-15T05:29:17.376000",
  "symbol": "BTCUSDT",
  "price": 74084.1,
  "ma5": 74148.16,
  "ma20": 74217.67,
  "ma240": 74568.74,
  "volume_ratio": 0.18,
  "price_vs_ma5_pct": -0.09,
  "price_vs_ma20_pct": -0.18,
  "price_vs_ma240_pct": -0.65,
  "signals_count": 0,
  "signal_types": []
}
```

**Current Price Data**:
- BTC/USDT: $74,084.10
- ETH/USDT: $2,319.23

---

## T-054-B: Dashboard Price History Charts

### Status: ✅ COMPLETED

**Changes to `ui/pages/dashboard.py`**:

#### Added Section
```python
# T-054-B: Price History Chart / 價格歷史圖表
html.Hr(),
html.H4("Price History / 價格歷史", className="mt-4 mb-3"),
dbc.Row([
    dbc.Col(dbc.Card([...BTC Chart...]), width=12, md=6),
    dbc.Col(dbc.Card([...ETH Chart...]), width=12, md=6),
])
```

#### Features
- **24-hour price history** for both BTC and ETH
- **Line chart with Plotly**: Clean, interactive visualization
- **MA5 overlay**: Shows price vs 5-period moving average
- **Auto-refresh**: Updates with dashboard interval (15s)
- **Responsive layout**: Side-by-side on desktop, stacked on mobile

#### Chart Details
- **Green line (#2ecc71)**: BTC price
- **Purple line (#9b59b6)**: ETH price
- **Blue dashed line (#3498db)**: MA5
- **X-axis**: Time (HH:MM format)
- **Y-axis**: Price in USDT
- **Hover**: Unified mode for easy comparison

#### Helper Function
```python
def _load_price_history(symbol: str, hours: int = 24) -> tuple:
    """Load price history from indicator_snapshots.jsonl"""
    # Returns: (timestamps, prices, ma5_values)
```

#### Callbacks
- `update_btc_price_chart()`: Renders BTC 24h chart
- `update_eth_price_chart()`: Renders ETH 24h chart

---

## T-054-C: Signals Page Price Display

### Status: ✅ COMPLETED

**Changes to `ui/pages/signals.py`**:

#### Run History Enhancement
Added price display column to run history cards:
```python
# T-054-C: Price display column / 價格顯示欄
dbc.Col(
    html.Div(price_display) if price_display else html.Small("Prices N/A", className="text-muted"),
    width=6,
    md=4
)
```

**Price Display Format**:
```
BTC: $74,084  ETH: $2,319
```

**Changes to `ui/services/monitor_service.py`**:

#### New Method
```python
def _get_prices_for_run(self, run_id: Any, timestamp_str: str) -> Dict[str, float]:
    """Get prices for a specific run from indicator_snapshots.jsonl"""
    # Matches by run_id or timestamp (±30 seconds window)
    # Returns: {"BTCUSDT": 74084.1, "ETHUSDT": 2319.23}
```

#### Enhanced get_recent_runs()
```python
run["prices"] = self._get_prices_for_run(
    run.get("run_id"), 
    run["timestamp"]
)
```

---

## Dashboard Structure (Updated)

```
Dashboard
├── Live Prices (BTC + ETH 大卡片)
├── Status Cards
├── Active Symbols
├── Strategy Distance Panel
├── Recent Run History
├── Recent Signals
├── Backtest Results
├── Price History (NEW)  ← T-054-B
│   ├── BTC/USDT 24h Chart
│   └── ETH/USDT 24h Chart
└── Quick Actions
```

---

## Signals Page Structure (Updated)

```
Signals
├── Summary Cards
├── Filters
├── Run History
│   └── Run Card (per run)
│       ├── Run ID
│       ├── Timestamp
│       ├── Prices (NEW)  ← T-054-C
│       ├── Signal Count
│       └── Click for details
├── Signal History
├── Run Detail Modal
└── Signal Type Reference
```

---

## Data Flow

### Price Recording Flow
```
Scheduler runs monitor
    ↓
MonitorRunner.run_monitor_once()
    ↓
For each symbol:
    _save_indicator_snapshot(result)
    ↓
Append to logs/indicator_snapshots.jsonl
```

### Price Visualization Flow
```
Dashboard loads
    ↓
Callback: update_btc_price_chart()
    ↓
_load_price_history("BTCUSDT", hours=24)
    ↓
Read indicator_snapshots.jsonl
    ↓
Filter last 24h for BTC
    ↓
Build Plotly figure
    ↓
Render chart
```

### Price in Run History Flow
```
Signals page loads
    ↓
get_recent_runs(10)
    ↓
For each run:
    _get_prices_for_run(run_id, timestamp)
    ↓
Match with indicator_snapshots.jsonl
    ↓
Return prices dict
    ↓
Display in run card
```

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/dashboard.py` | Added Price History section with 2 charts |
| `ui/pages/signals.py` | Added price column to run history |
| `ui/services/monitor_service.py` | Added `_get_prices_for_run()` method |
| `start_scheduler.py` | New helper script |

---

## Testing

- [x] Syntax validation passed
- [x] Module imports successful
- [x] Price data recording verified (3 entries in JSONL)
- [ ] Visual testing (requires UI to be running)

---

## Future Enhancements (Optional)

- **7-day/30-day view toggle**: Extend chart time range
- **Volume overlay**: Add volume bars to price charts
- **Signal markers**: Mark signal points on price chart
- **Price alerts**: Highlight significant price moves
- **Export chart**: Download chart as image

---

## Dependencies

- **T-052-B**: `_save_indicator_snapshot()` method
- **Plotly**: For chart rendering
- **dash**: For callback system

---

## Notes

- Charts show "No data yet" when insufficient historical data
- Prices are matched using run_id or timestamp (±30s window)
- Charts auto-refresh every 15 seconds with dashboard
- Run history shows prices for each monitored symbol

---
