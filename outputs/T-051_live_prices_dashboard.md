# T-051: Display Live Prices on UI Dashboard

**Task ID**: T-051  
**Type**: Enhancement  
**Priority**: Medium  
**Date**: 2026-04-14

---

## Summary

Extended T-050 to display live BTC/ETH prices on the UI Dashboard. The prices are now saved to a state file after each scheduler run and displayed in real-time on the Dashboard.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Scheduler Run  │────▶│  Save to prices  │────▶│  UI Dashboard   │
│  (monitor.py)   │     │  (state/prices)  │     │  (Display Card) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │                       │
        │                        │                       │
        ▼                        ▼                       ▼
   Get prices from          Write JSON            Read via service
   SymbolResult             (timestamp + prices)  (get_current_prices)
```

---

## Changes Made

### 1. `app/scheduler.py`

#### Version Update
- Updated version from `1.0.0` to `1.1.0`

#### New Method: `_save_prices_to_state()`
```python
def _save_prices_to_state(self, results) -> None:
    """Save current prices to state file / 儲存當前價格到狀態檔案"""
    # Saves prices to state/prices.json
    # Format: {"timestamp": "ISO", "prices": {"BTCUSDT": {"price": X, "timestamp": Y}}}
```

#### Modified `_run_monitor()`
- Added call to `_save_prices_to_state(results)` after monitoring execution

### 2. `ui/services/monitor_service.py`

#### Version Update
- Updated version from `1.1.0` to `1.2.0`

#### New Function: `get_current_prices()`
```python
def get_current_prices() -> Dict[str, Any]:
    """Get current prices from state file / 從狀態檔案取得當前價格"""
    # Reads from state/prices.json
    # Returns: {"timestamp": str, "prices": {"BTCUSDT": {"price": float, "timestamp": str}}}
```

### 3. `ui/pages/dashboard.py`

#### Import Update
- Added `get_current_prices` to imports

#### New Card: Live Prices / 即時價格
```python
# Current Prices Card (T-051)
dbc.Card(
    [
        dbc.CardHeader([
            "Live Prices / 即時價格",
            html.Small(" 💰From Last Run", className="text-muted ms-2")
        ]),
        dbc.CardBody(
            [
                html.Div(id="dashboard-prices", children=[...])
            ]
        )
    ],
    id="dashboard-prices-card",
    color="success",
    outline=True
)
```

#### New Callback: `update_prices()`
```python
@callback(
    Output("dashboard-prices", "children"),
    Output("dashboard-prices-card", "color"),
    Input("dashboard-interval", "n_intervals")
)
def update_prices(n):
    """Update current prices display / 更新當前價格顯示"""
    # Reads prices via get_current_prices()
    # Updates every 10 seconds (via dashboard-interval)
```

---

## Data Flow

### 1. Price Collection (Scheduler)
1. Scheduler runs monitoring via `run_monitor_once()`
2. `SymbolResult` now includes `current_price` field (from T-050)
3. `_save_prices_to_state()` extracts prices and saves to `state/prices.json`

### 2. Price Display (UI)
1. Dashboard loads via `get_current_prices()` service function
2. Callback `update_prices()` refreshes every 10 seconds
3. Card displays formatted prices with timestamp

---

## File Format: state/prices.json

```json
{
  "timestamp": "2026-04-14T19:07:32.203532",
  "prices": {
    "BTCUSDT": {
      "price": 71599.99,
      "timestamp": "2026-04-14T19:07:32.203550"
    },
    "ETHUSDT": {
      "price": 2214.73,
      "timestamp": "2026-04-14T19:07:32.203552"
    }
  }
}
```

---

## UI Display

### Dashboard Card
```
┌──────────────────────────────────────┐
│ Live Prices 💰From Last Run          │
├──────────────────────────────────────┤
│  BTC: $71,599.99                     │
│  ETH: $2,214.73                      │
│                                      │
│  Updated: 19:07:32                   │
└──────────────────────────────────────┘
```

### Auto-Refresh
- Dashboard interval: 10 seconds
- Price data refreshes automatically
- No page reload required

---

## Scheduler Log Output

After each run, scheduler now logs:
```
[2026-04-14 19:07:32] Run #1 completed
[2026-04-14 19:07:32]   Duration: 2.3s
[2026-04-14 19:07:32]   Symbols: 2/2
[2026-04-14 19:07:32]   Signals: 0
[2026-04-14 19:07:32]   Prices saved: ['BTCUSDT', 'ETHUSDT']  # <-- NEW
```

---

## Testing

- [x] Scheduler import test passed
- [x] Monitor service import test passed
- [x] Price save/read functionality tested
- [x] JSON data structure validated
- [x] File I/O working correctly

---

## Files Modified

| File | Changes |
|------|---------|
| `app/scheduler.py` | Added `_save_prices_to_state()` method, version bump |
| `ui/services/monitor_service.py` | Added `get_current_prices()` function, version bump |
| `ui/pages/dashboard.py` | Added Live Prices card and callback |

---

## Dependencies

- **T-050**: Required for `current_price` field in `SymbolResult`
- **State Directory**: `state/prices.json` (auto-created)
- **Dashboard**: Auto-refresh via `dcc.Interval`

---

## Notes

- Prices are saved after each scheduler run (every 5 minutes by default)
- UI refreshes prices every 10 seconds from the state file
- If no price data available, card shows "No price data available"
- Timestamp shows when prices were last updated

---
