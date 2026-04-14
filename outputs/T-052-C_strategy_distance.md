# T-052-C: Strategy Distance Panel

**Task ID**: T-052-C  
**Type**: Enhancement  
**Priority**: High  
**Date**: 2026-04-14

---

## Summary

Added a "Strategy Distance / 策略距離" panel to the Dashboard showing how close each symbol is to strategy trigger conditions. The panel displays current price, MA distances, trigger conditions, and recent signals.

---

## Changes Made

### 1. `ui/services/monitor_service.py`

#### New Function: `get_latest_indicator_snapshots()`
```python
def get_latest_indicator_snapshots() -> Dict[str, Any]:
    """Get latest indicator snapshots for each symbol"""
    # Reads from logs/indicator_snapshots.jsonl
    # Returns latest snapshot per symbol
```

**Returns**:
```python
{
    "BTCUSDT": {
        "price": 83500.0,
        "ma5": 83200.0,
        "price_vs_ma5_pct": 0.36,
        "signals_count": 0,
        "signal_types": []
    },
    "ETHUSDT": {...}
}
```

### 2. `ui/pages/dashboard.py`

#### New Section: Strategy Distance Panel

Added between "Active Symbols" and "Recent Run History":

```
┌─────────────────────────────────────────────────────────────┐
│ Strategy Distance / 策略距離                                 │
├──────────────────────────────┬──────────────────────────────┤
│ BTC Strategy Distance        │ ETH Strategy Distance        │
├──────────────────────────────┼──────────────────────────────┤
│ Current Price / 現價         │ Current Price / 現價         │
│ $83,500.00                   │ $2,214.73                    │
├──────────────────────────────┼──────────────────────────────┤
│ MA Distance / MA 距離        │ MA Distance / MA 距離        │
│ MA5: +0.36% (green)          │ MA5: +0.85% (green)          │
│ MA20: +0.85% (green)         │ MA20: +1.20% (green)         │
│ MA240: +4.37% (green)        │ MA240: +3.50% (green)        │
├──────────────────────────────┼──────────────────────────────┤
│ Trigger Conditions           │ Trigger Conditions           │
│ • Trend Long: MA5 cross      │ • Trend Long: MA5 cross      │
│   above MA20 + volume        │   above MA20 + volume        │
│ • Trend Short: MA5 cross     │ • Trend Short: MA5 cross     │
│   below MA20                 │   below MA20                 │
│ • Contrarian Oversold:       │ • Contrarian Oversold:       │
│   4 red + low volume         │   4 red + low volume         │
│ • Contrarian Overbought:     │ • Contrarian Overbought:     │
│   4 green + high volume      │   4 green + high volume      │
├──────────────────────────────┼──────────────────────────────┤
│ Recent Signal / 最近訊號     │ Recent Signal / 最近訊號     │
│ No signals / 無訊號          │ 1 signal(s)                  │
│                              │ • TREND_LONG                 │
└──────────────────────────────┴──────────────────────────────┘
```

#### New Callbacks

**`_format_ma_distance(value)`**
- Helper function to format MA distance with color
- Returns tuple: (formatted_text, color_class)
- Color: green (+) = above MA, red (-) = below MA

**`update_btc_strategy_distance(n)`**
- Updates BTC strategy distance card
- 5 outputs: price, ma5, ma20, ma240, recent_signal

**`update_eth_strategy_distance(n)`**
- Updates ETH strategy distance card
- 5 outputs: price, ma20, ma240, recent_signal

---

## Page Structure (Updated)

```
Dashboard
├── Live Prices (BTC + ETH cards)           ← T-052-A
├── Status Cards (System, Last Run, Signals)
├── Active Symbols
├── Strategy Distance Panel (NEW)           ← T-052-C
│   ├── BTC Strategy Distance Card
│   └── ETH Strategy Distance Card
├── Recent Run History
├── Recent Signals
└── Quick Actions
```

---

## Visual Design

### MA Distance Colors
- **Green** (`text-success`): Price above MA (positive distance)
- **Red** (`text-danger`): Price below MA (negative distance)
- **Gray** (`text-secondary`): Data unavailable

### Format
- Positive: `+0.36%`
- Negative: `-1.25%`

---

## Data Flow

```
Scheduler Run
    ↓
monitor_runner._save_indicator_snapshot()
    ↓
logs/indicator_snapshots.jsonl (append)
    ↓
Dashboard Callback (15s interval)
    ↓
get_latest_indicator_snapshots()
    ↓
update_btc/eth_strategy_distance()
    ↓
UI Display
```

---

## Error Handling

- **File not found**: Returns empty dict, displays "Data unavailable"
- **Parse error**: Skips malformed lines in JSONL
- **Missing symbol**: Shows "--" for that symbol
- **Exception**: Shows error message in UI

---

## Dependencies

- **T-052-B**: Provides `indicator_snapshots.jsonl` data
- **T-052-A**: Dashboard structure and 15s refresh interval

---

## Testing

- [x] Service function import successful
- [x] JSONL reading working
- [x] Latest snapshot per symbol retrieved
- [x] MA distance formatting correct

**Test Output**:
```
✓ get_latest_indicator_snapshots function available
✓ Read 1 symbol(s) from indicator_snapshots.jsonl
  - BTCUSDT: price=83500.0, ma5_pct=0.36%
```

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/services/monitor_service.py` | Added `get_latest_indicator_snapshots()` |
| `ui/pages/dashboard.py` | Added Strategy Distance section and callbacks |

---
