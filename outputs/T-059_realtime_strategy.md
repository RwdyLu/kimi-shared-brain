# T-059: Real-time Prices + Strategy Status Panel

**Task ID**: T-059-A, T-059-B  
**Type**: Enhancement  
**Priority**: High  
**Date**: 2026-04-15

---

## Summary

Implemented real-time price updates and redesigned the Dashboard Strategy Status panel with color-coded strategy indicators.

---

## T-059-A: Real-time Price Updates

### Changes

#### `ui/pages/dashboard.py`
- Changed `dcc.Interval` from 15s to 10s (10000ms)
```python
interval=10*1000,  # 10 seconds / 10 秒 (T-059-A)
```

#### `ui/services/monitor_service.py`
- `get_current_prices()` now fetches from Binance public API
- Endpoints:
  - `https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT`
  - `https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT`
- Added `_get_prices_from_snapshot()` as fallback

### Verification
```python
✓ Syntax validation passed
✓ Binance API integration implemented
✓ 10s interval configured
```

---

## T-059-B: Strategy Status Panel

### Design

```
┌─────────────────────────────────┐
│ BTC $74,102                     │
├─────────────────────────────────┤
│ 策略狀態                         │
│ 🟡 MA Cross Long   差 0.15%    │
│    MA5 $73,985 需上穿 MA20      │
│                                 │
│ 🟡 MA Cross Short  差 0.15%    │
│    MA5 需下穿 MA20              │
│                                 │
│ 🔴 Contrarian Oversold  未觸發  │
│    需連續 4 根紅 K               │
│                                 │
│ 🔴 Contrarian Overbought 未觸發 │
│    需連續 4 根綠 K               │
└─────────────────────────────────┘
```

### Color Coding
| Status | Color | Condition |
|--------|-------|-----------|
| 🟢 Green | Triggered | Strategy just triggered |
| 🟡 Yellow | Close | Distance < 0.5% |
| 🔴 Red | Far | Distance >= 0.5% |

### Implementation

#### `ui/pages/dashboard.py`

**New Layout (BTC & ETH cards):**
- Header with price and 24h change
- 4 strategy status rows:
  1. MA Cross Long
  2. MA Cross Short
  3. Contrarian Oversold
  4. Contrarian Overbought

**New Callbacks:**
- `update_btc_strategy_status()` - 13 outputs
- `update_eth_strategy_status()` - 13 outputs

**Data Sources:**
- Price: Binance API (real-time)
- MA values: `indicator_snapshots.jsonl`
- Candle counts: monitor last run results

---

## Files Modified

| File | Changes |
|------|---------|
| `ui/pages/dashboard.py` | Interval 10s, new strategy status layout & callbacks |
| `ui/services/monitor_service.py` | Binance API fetch, fallback to snapshot |

---

## Commit

`473c9b5` - T-059-A/B: Real-time Prices + Strategy Status Panel

---
