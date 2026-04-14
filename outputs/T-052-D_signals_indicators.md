# T-052-D: Signals Page Indicators

**Task ID**: T-052-D  
**Type**: Enhancement  
**Priority**: High  
**Date**: 2026-04-14

---

## Summary

Enhanced the Signals page to show detailed indicator values when clicking on a run in the Run History. Users can now view BTC/ETH price, MA5, MA20, and distance percentages for each monitoring run.

---

## Changes Made

### `ui/pages/signals.py`

#### Import Update
```python
from ui.services.monitor_service import (
    get_recent_runs, 
    get_today_signals, 
    get_latest_indicator_snapshots  # T-052-D
)
```

#### Layout Changes

**Before**: Simple table showing run_id, timestamp, and signal count

**After**: 
- Clickable cards for each run (instead of table rows)
- Modal popup (`run-detail-modal`) showing detailed indicator data
- Store component (`selected-run-id`) to track selected run

**New Components**:
1. **Run History Cards**: Each run is now a clickable `dbc.Card`
2. **Modal**: `dbc.Modal` with `run-detail-modal-body` for details
3. **Store**: `dcc.Store` to track which run is selected

#### New Callback: `toggle_run_modal()`

**Pattern Matching Callback**:
```python
Input({"type": "run-row", "index": dash.ALL}, "n_clicks")
```

**Logic**:
1. Detect which run card was clicked
2. Fetch indicator snapshots via `get_latest_indicator_snapshots()`
3. Build modal content with BTC/ETH details
4. Show modal with formatted data

**Modal Content Structure**:
```
┌─────────────────────────────────────────────────────────────┐
│ Run Details / 執行詳情                                       │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ BTC                                                     │ │
│ │ ┌──────────────┬──────────────┬──────────────┐         │ │
│ │ │ Price        │ MA5          │ MA20         │         │ │
│ │ │ $83,500.00   │ $83,200.00   │ $82,800.00   │         │ │
│ │ │              │ Distance:    │ Distance:    │         │ │
│ │ │              │ +0.36%       │ +0.85%       │         │ │
│ │ └──────────────┴──────────────┴──────────────┘         │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ETH                                                     │ │
│ │ ┌──────────────┬──────────────┬──────────────┐         │ │
│ │ │ Price        │ MA5          │ MA20         │         │ │
│ │ │ $2,214.73    │ $2,200.00    │ $2,180.00    │         │ │
│ │ │              │ Distance:    │ Distance:    │         │ │
│ │ │              │ +0.67%       │ +1.59%       │         │ │
│ │ └──────────────┴──────────────┴──────────────┘         │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

#### Distance Formatting

- **Positive distance** (price above MA): Green (`text-success`)
- **Negative distance** (price below MA): Red (`text-danger`)
- Format: `+0.36%` or `-1.25%`

---

## User Interaction Flow

```
1. User opens Signals page
   ↓
2. Sees list of recent runs as clickable cards
   ↓
3. Clicks on a run card (e.g., "#2031")
   ↓
4. Modal opens showing BTC/ETH indicator details
   ↓
5. Views: Price, MA5, MA20, distance percentages
   ↓
6. Closes modal or clicks another run
```

---

## Technical Implementation

### Pattern Matching IDs
```python
id={"type": "run-row", "index": run_id}
```
Used to identify which run was clicked from the list of cards.

### Data Source
- Reads from `logs/indicator_snapshots.jsonl` via `get_latest_indicator_snapshots()`
- Shows the **latest** snapshot for each symbol (not historical per run)
- For per-run historical data, additional implementation would be needed

### Error Handling
- Try/except around data fetching
- Shows "Data unavailable" alert if snapshot missing
- Modal still opens even if data is missing

---

## Dependencies

- **T-052-B**: Provides `indicator_snapshots.jsonl` data
- **T-052-C**: Uses same `get_latest_indicator_snapshots()` function
- **dash**: Pattern matching callbacks (`dash.ALL`)

---

## Testing

Visual verification needed after deployment:
- [ ] Run history shows as clickable cards
- [ ] Clicking a run opens modal
- [ ] Modal shows BTC/ETH sections
- [ ] Prices displayed with $ formatting
- [ ] MA distances shown with color coding
- [ ] Modal closes properly

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/signals.py` | Added modal, clickable run cards, indicator detail callback |

---
