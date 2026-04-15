# T-058: Add Relative Time to Dashboard Live Prices

**Task ID**: T-058  
**Type**: Enhancement  
**Priority**: Medium  
**Date**: 2026-04-15

---

## Summary

Modified Dashboard Live Prices section to display relative time (e.g., "32s ago") alongside the timestamp.

---

## Changes

### `ui/pages/dashboard.py`

#### Added Helper Function
```python
def format_update_time(timestamp_str: str) -> str:
    """
    Format timestamp with relative time (T-058)
    格式化時間戳並顯示相對時間
    
    Returns:
        Formatted string like "Updated 17:39:39 · 32s ago"
    """
```

#### Modified Callbacks
- `update_btc_price()` - Now uses `format_update_time()`
- `update_eth_price()` - Now uses `format_update_time()`

#### Display Format
```
Before: "Updated 17:39:39"
After:  "Updated 17:39:39 · 32s ago"
```

#### Relative Time Rules
| Time Diff | Format | Example |
|-----------|--------|---------|
| < 60s | Xs ago | 32s ago |
| < 1h | Xm ago | 5m ago |
| ≥ 1h | Xh ago | 2h ago |

---

## Testing

- [x] Syntax validation passed
- [x] Function logic tested
- [ ] Visual verification (requires UI restart)

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/dashboard.py` | Added `format_update_time()`, modified BTC/ETH price callbacks |

---

## Commit

`01fd65d` - T-058: Add Relative Time to Dashboard Live Prices

---
