# T-050: Add Current Price Display to Signal Checks

**Task ID**: T-050  
**Type**: Enhancement  
**Priority**: Medium  
**Date**: 2026-04-14

---

## Summary

Modified the monitoring system to display current prices for BTC and ETH during each signal check run.

---

## Changes Made

### 1. `app/monitor_runner.py`

#### Version Update
- Updated version from `1.1.0` to `1.2.0`

#### SymbolResult Dataclass
- Added `current_price: Optional[float] = None` field to store the latest price

#### run_for_symbol() Method
- Added current price extraction from the latest 5m candle
- Added display line: `💰 Current Price: $XX,XXX.XX`
- Price is now stored in the SymbolResult for later use

#### run_monitor_once() Method
- Added new "CURRENT PRICES / 當前價格" section in summary
- Displays all symbol prices in a clean format after individual runs

---

## Output Example

```
======================================================================
BTC/ETH Monitoring System - Single Run
BTC/ETH 監測系統 - 單次執行
======================================================================
⚠️  ALERT ONLY - NO AUTO TRADING / 僅提醒 - 無自動交易
⏱️  Timestamp: 2026-04-14 18:45:32
📊 Symbols: BTCUSDT, ETHUSDT
======================================================================

============================================================
Monitoring BTCUSDT...
============================================================
[1/4] Fetching data...
    ✓ 5m: 250 candles
    ✓ 1m: 20 candles
    ✓ 15m: 10 candles
[2/4] Calculating indicators...
    💰 Current Price: $71,599.99
    ✓ MA5: 71234.56
    ✓ MA20: 70890.12
    ✓ MA240: 70123.45
    ✓ Volume Ratio: 1.25x
...

----------------------------------------------------------------------
CURRENT PRICES / 當前價格
----------------------------------------------------------------------
  BTCUSDT: $71,599.99
  ETHUSDT: $2,214.73
```

---

## Technical Details

### Price Source
- Current price is extracted from the latest 5m candle's close price
- This ensures consistency with other indicators that use 5m data

### Display Location
1. **Per-symbol output**: Shows immediately after indicator calculation
2. **Summary section**: Shows all symbol prices together at the end

### Data Flow
```
Data Fetch (5m candles)
    ↓
Extract current_price = data_5m[-1].close
    ↓
Display in indicator section
    ↓
Store in SymbolResult.current_price
    ↓
Display in summary section
```

---

## Alert-Only Design

✅ **Maintained**
- No trading logic added
- Price display is for informational purposes only
- No API keys or trading functionality introduced

---

## Testing

- [x] Import test passed
- [x] SymbolResult dataclass accepts current_price field
- [x] Code structure validated

---

## Files Modified

| File | Changes |
|------|---------|
| `app/monitor_runner.py` | Added current_price field, display logic, version bump |

---

## Commit

```
T-050: Add Current Price Display to Signal Checks

- Add current_price field to SymbolResult dataclass
- Display current price in indicator calculation step
- Add CURRENT PRICES section to run summary
- Version bump: 1.1.0 → 1.2.0

Alert-only design maintained. Prices for informational purposes only.
```
