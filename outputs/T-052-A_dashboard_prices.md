# T-052-A: Fix Dashboard Live Price Display

**Task ID**: T-052-A  
**Type**: Enhancement  
**Priority**: High  
**Date**: 2026-04-14

---

## Summary

Moved the live prices section to the top of the Dashboard page, created separate large cards for BTC and ETH, and improved the display format.

---

## Changes Made

### `ui/pages/dashboard.py`

#### Layout Changes

**Before**: Price card was in the status cards row (4th position)

**After**: 
- New "Live Prices / 即時價格" section at the top (after Header)
- Two large cards side by side:
  - **Bitcoin Card**: Large green price display with update time
  - **Ethereum Card**: Large green price display with update time

**Card Design**:
```
┌─────────────────────────┐  ┌─────────────────────────┐
│  Bitcoin                │  │  Ethereum               │
│  $83,500.00             │  │  $2,214.73              │
│  Updated 20:45:32       │  │  Updated 20:45:32       │
└─────────────────────────┘  └─────────────────────────┘
```

#### Auto-refresh Interval
- Changed from **10 seconds** to **15 seconds**
- Affects all dashboard components

#### New Callbacks

**`update_btc_price(n)`**
- Updates `btc-price-display` and `btc-price-time`
- Formats: `$XX,XXX.XX` and `Updated HH:MM:SS`

**`update_eth_price(n)`**
- Updates `eth-price-display` and `eth-price-time`
- Formats: `$X,XXX.XX` and `Updated HH:MM:SS`

#### Removed
- Old `update_prices()` callback (replaced by separate BTC/ETH callbacks)
- Old `dashboard-prices` and `dashboard-prices-card` components

---

## Page Structure

```
Dashboard
├── Header (H2: Dashboard)
├── Live Prices Section (NEW - T-052-A)
│   ├── Bitcoin Card
│   └── Ethereum Card
├── Status Cards Row
│   ├── System Status
│   ├── Last Run
│   └── Today's Signals
├── Active Symbols
├── Recent Run History
├── Recent Signals
└── Quick Actions
```

---

## Visual Hierarchy

1. **Prices are now #1 priority** - displayed at the very top
2. **Large, readable format** - H2 size prices in green
3. **Clear separation** - dedicated section with its own header
4. **Timestamp visible** - shows when prices were last updated

---

## Error Handling

Both callbacks use try/except:
- Missing data → shows `--` and "No data / 無資料"
- Exception → shows "Error" and error message

---

## Dependencies

- **T-051**: `get_current_prices()` service function
- **T-052-B**: Provides price data via `state/prices.json`

---

## Testing

Visual verification needed after deployment:
- [ ] Prices section appears at top of page
- [ ] BTC card shows price in large green text
- [ ] ETH card shows price in large green text
- [ ] Timestamps update every 15 seconds
- [ ] No JavaScript errors in browser console

---
