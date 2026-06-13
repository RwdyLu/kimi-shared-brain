# T-052-B: Save Indicator Snapshots

**Task ID**: T-052-B  
**Type**: Implementation  
**Priority**: High (blocking other T-052 tasks)  
**Date**: 2026-04-14

---

## Summary

Added functionality to save indicator snapshots after each monitoring run. The snapshots are stored in `logs/indicator_snapshots.jsonl` for use by the UI Dashboard to display strategy distance metrics.

---

## Changes Made

### `app/monitor_runner.py`

#### Version Update
- Updated version from `1.2.0` to `1.3.0`

#### New Method: `_save_indicator_snapshot()`

```python
def _save_indicator_snapshot(self, result: SymbolResult, run_id: Optional[int] = None) -> None:
    """
    Save indicator snapshot to JSONL file / 儲存指標快照到 JSONL 檔案
    
    T-052-B: Store indicator values after each run for UI display
    """
```

**Snapshot Data Structure**:
```json
{
  "run_id": "#9999",
  "timestamp": "2026-04-14T20:11:30",
  "symbol": "BTCUSDT",
  "price": 83500.0,
  "ma5": 83200.0,
  "ma20": 82800.0,
  "ma240": 80000.0,
  "volume_ratio": 1.2,
  "price_vs_ma5_pct": 0.36,
  "price_vs_ma20_pct": 0.85,
  "price_vs_ma240_pct": 4.37,
  "signals_count": 0,
  "signal_types": []
}
```

**MA Distance Calculations**:
- `price_vs_ma5_pct` = (price - ma5) / ma5 * 100
- `price_vs_ma20_pct` = (price - ma20) / ma20 * 100
- `price_vs_ma240_pct` = (price - ma240) / ma240 * 100

**File Format**: JSONL (one JSON object per line, append-only)
- Location: `logs/indicator_snapshots.jsonl`
- Each run appends new lines
- Supports historical analysis

#### Modified `run_for_symbol()`
- Added call to `_save_indicator_snapshot(result)` after building result

---

## Data Flow

```
Monitoring Run
    ↓
Fetch Data → Calculate Indicators → Generate Signals
    ↓
Build SymbolResult (with current_price from T-050)
    ↓
_save_indicator_snapshot(result)
    ↓
Append to logs/indicator_snapshots.jsonl
    ↓
UI Dashboard reads latest snapshot per symbol
```

---

## Error Handling

- Silent fail on error (prints warning but doesn't break monitoring)
- Uses try/except to catch all exceptions
- File I/O errors don't interrupt the monitoring flow

---

## Testing

- [x] Import test passed
- [x] Method exists and callable
- [x] Snapshot file created successfully
- [x] Data structure validated
- [x] MA percentage calculations correct (0.36% for test case)

**Test Output**:
```
✓ monitor_runner.py import successful
✓ _save_indicator_snapshot method exists
✓ Snapshot saved successfully
✓ File exists with 1 line(s)
✓ Last entry: run_id=#9999, symbol=BTCUSDT
✓ price_vs_ma5_pct: 0.36%
```

---

## Files Modified

| File | Changes |
|------|---------|
| `app/monitor_runner.py` | Added `_save_indicator_snapshot()` method, version bump |

---

## Dependencies

- **T-050**: Requires `current_price` field in `SymbolResult`
- **LOGS_DIR**: From `config.paths`

---

## Next Steps

This task enables:
- T-052-A: Dashboard price display
- T-052-C: Strategy distance panel
- T-052-D: Signals page indicators

All downstream tasks read from `logs/indicator_snapshots.jsonl`.

---
