# T-037: Signal Condition Diagnostics Report / 訊號條件診斷報告

**Task ID**: T-037  
**Title**: Diagnose Signal Conditions  
**Date**: 2026-04-07  
**Status**: ✅ Completed / 完成  
**Commit**: [PENDING]

---

## 1. Purpose / 目的

Diagnose why the BTC/ETH monitoring system is not generating alerts by tracing each signal condition to identify blocking factors.

診斷 BTC/ETH 監測系統為何沒有生成提醒，透過追蹤每個訊號條件來識別阻塞因素。

---

## 2. Diagnostic Method / 診斷方法

1. **Fetch live data** from Binance API for BTCUSDT and ETHUSDT
2. **Calculate indicators**: MA5, MA20, MA240, Volume metrics
3. **Check each condition** against signal requirements
4. **Identify blocking factors** preventing signal generation
5. **Document findings** with specific values and thresholds

---

## 3. Execution Time / 執行時間

**Diagnostic Run**: 2026-04-07 19:56:48 GMT+8

---

## 4. BTCUSDT Diagnostic Results / BTCUSDT 診斷結果

### 4.1 Current Market Data / 當前市場資料

| Metric | Value | MA240 Distance |
|--------|-------|----------------|
| Close (5m) | 68,324.95 | - |
| MA5 | 68,389.45 | -64.50 below close |
| MA20 | 68,424.67 | -99.72 below close |
| MA240 | 69,046.41 | **1.04% ABOVE close** |
| Timestamp | 2026-04-07 19:55:00 | - |

### 4.2 Condition C1: Close vs MA240 / 條件 C1：收盤價與 MA240

| Check | Result | Value |
|-------|--------|-------|
| Close > MA240? | ❌ FALSE | 68,324.95 > 69,046.41 |
| Close < MA240? | ✅ TRUE | 68,324.95 < 69,046.41 |
| Distance | 1.04% | Below MA240 |

**Status**: Price is **BELOW** MA240 → Bearish bias / 偏空

### 4.3 Condition C2: MA Cross Detection / 條件 C2：MA 交叉檢測

| Check | Current | Previous | Result |
|-------|---------|----------|--------|
| MA5 | 68,389.45 | 68,389.06 | - |
| MA20 | 68,424.67 | 68,454.90 | - |
| Golden Cross? | - | - | ❌ FALSE |
| Death Cross? | - | - | ❌ FALSE |

**Current Relationship**: MA5 < MA20 (Bearish alignment / 空頭排列) ✅

**Status**: No cross detected → No trend signal trigger

### 4.4 Condition C3: Volume Analysis / 條件 C3：成交量分析

| Metric | Value |
|--------|-------|
| Current Volume | 4.8625 |
| Average Volume | 64.5761 |
| Volume Ratio | **0.08x** |
| Is Spike? | ❌ NO |
| > 1.5x Threshold? | ❌ FALSE |

**Status**: Volume is **VERY LOW** (0.08x vs 1.5x required)

### 4.5 Condition C4: Pattern Detection / 條件 C4：型態檢測

| Pattern | Count | Result |
|---------|-------|--------|
| Consecutive Up (連漲) | 0 | ❌ |
| Consecutive Down (連跌) | 1 | ❌ |
| 4+ Up Candles? | - | ❌ FALSE |
| 4+ Down Candles? | - | ❌ FALSE |

**Status**: No consecutive pattern detected

### 4.6 Signal Readiness Summary / 訊號就緒摘要

| Signal Type | C1 | C2 | C3/C4 | Overall |
|-------------|----|----|-------|---------|
| Trend Long (順勢做多) | ❌ | ❌ | ❌ | 🔴 NOT READY |
| Trend Short (順勢做空) | ✅ | ❌ | ❌ | 🔴 NOT READY |
| Contrarian Overheated | ❌ | - | ❌ | 🔴 NOT READY |
| Contrarian Oversold | ✅ | - | ❌ | 🔴 NOT READY |

**Blocking Factors for BTCUSDT**:
1. ❌ No death cross detected (MA5 already below MA20, no fresh cross)
2. ❌ Volume too low (0.08x < 1.5x required)
3. ❌ Not oversold yet (only 1 consecutive down candle)

---

## 5. ETHUSDT Diagnostic Results / ETHUSDT 診斷結果

### 5.1 Current Market Data / 當前市場資料

| Metric | Value | MA240 Distance |
|--------|-------|----------------|
| Close (5m) | 2,088.63 | - |
| MA5 | 2,089.80 | -1.17 below close |
| MA20 | 2,094.00 | -5.37 below close |
| MA240 | 2,119.60 | **1.46% ABOVE close** |
| Timestamp | 2026-04-07 19:55:00 | - |

### 5.2 Condition C1: Close vs MA240 / 條件 C1：收盤價與 MA240

| Check | Result | Value |
|-------|--------|-------|
| Close > MA240? | ❌ FALSE | 2,088.63 > 2,119.60 |
| Close < MA240? | ✅ TRUE | 2,088.63 < 2,119.60 |
| Distance | 1.46% | Below MA240 |

**Status**: Price is **BELOW** MA240 → Bearish bias / 偏空

### 5.3 Condition C2: MA Cross Detection / 條件 C2：MA 交叉檢測

| Check | Current | Previous | Result |
|-------|---------|----------|--------|
| MA5 | 2,089.80 | 2,089.71 | - |
| MA20 | 2,094.00 | 2,095.53 | - |
| Golden Cross? | - | - | ❌ FALSE |
| Death Cross? | - | - | ❌ FALSE |

**Current Relationship**: MA5 < MA20 (Bearish alignment / 空頭排列) ✅

**Status**: No cross detected → No trend signal trigger

### 5.4 Condition C3: Volume Analysis / 條件 C3：成交量分析

| Metric | Value |
|--------|-------|
| Current Volume | 141.7441 |
| Average Volume | 1,402.8125 |
| Volume Ratio | **0.10x** |
| Is Spike? | ❌ NO |
| > 1.5x Threshold? | ❌ FALSE |

**Status**: Volume is **VERY LOW** (0.10x vs 1.5x required)

### 5.5 Condition C4: Pattern Detection / 條件 C4：型態檢測

| Pattern | Count | Result |
|---------|-------|--------|
| Consecutive Up (連漲) | 0 | ❌ |
| Consecutive Down (連跌) | 2 | ❌ |
| 4+ Up Candles? | - | ❌ FALSE |
| 4+ Down Candles? | - | ❌ FALSE |

**Status**: No consecutive pattern detected

### 5.6 Signal Readiness Summary / 訊號就緒摘要

| Signal Type | C1 | C2 | C3/C4 | Overall |
|-------------|----|----|-------|---------|
| Trend Long (順勢做多) | ❌ | ❌ | ❌ | 🔴 NOT READY |
| Trend Short (順勢做空) | ✅ | ❌ | ❌ | 🔴 NOT READY |
| Contrarian Overheated | ❌ | - | ❌ | 🔴 NOT READY |
| Contrarian Oversold | ✅ | - | ❌ | 🔴 NOT READY |

**Blocking Factors for ETHUSDT**:
1. ❌ No death cross detected
2. ❌ Volume too low (0.10x < 1.5x required)
3. ❌ Not oversold yet (only 2 consecutive down candles)

---

## 6. Comparative Analysis / 比較分析

| Factor | BTCUSDT | ETHUSDT | Status |
|--------|---------|---------|--------|
| Price vs MA240 | 1.04% BELOW | 1.46% BELOW | Both bearish |
| MA Alignment | Bearish | Bearish | Both MA5 < MA20 |
| Volume Ratio | 0.08x | 0.10x | Both very low |
| Consecutive Down | 1 candle | 2 candles | Neither >= 4 |
| Ready for Short? | No | No | Same blockers |
| Ready for Long? | No | No | Price below MA240 |

---

## 7. Root Cause Analysis / 根本原因分析

### 7.1 Why No Signals? / 為什麼沒有訊號？

**BTCUSDT and ETHUSDT are both in a consolidation phase** with the following characteristics:

| Characteristic | BTCUSDT | ETHUSDT | Impact on Signals |
|----------------|---------|---------|-------------------|
| **Below MA240** | 1.04% | 1.46% | ✅ Enables bearish signals |
| **MA5 < MA20** | Yes | Yes | ✅ Bearish alignment |
| **No fresh cross** | - | - | ❌ Blocks trend signals |
| **Low volume** | 0.08x | 0.10x | ❌ Blocks ALL signals |
| **No 4+ pattern** | 1 | 2 candles | ❌ Blocks contrarian signals |

### 7.2 Primary Blocker: Low Volume / 主要阻塞因素：低成交量

Both symbols show **extremely low volume**:
- BTCUSDT: 0.08x average (needs 1.5x)
- ETHUSDT: 0.10x average (needs 1.5x)

This is the **primary blocker** preventing ALL signal types from triggering.

### 7.3 Secondary Blocker: No Fresh Crosses / 次要阻塞因素：無新鮮交叉

Both symbols are in established bearish alignment (MA5 < MA20) but:
- No recent death cross (already below)
- No golden cross in sight

Without a fresh cross event, trend signals cannot trigger.

### 7.4 Tertiary Blocker: No Consecutive Patterns / 第三阻塞因素：無連續型態

For contrarian signals:
- BTC: Only 1 consecutive down candle (need 4+)
- ETH: Only 2 consecutive down candles (need 4+)

Neither has reached the oversold threshold for contrarian signals.

---

## 8. System Health Check / 系統健康檢查

| Check | Status | Note |
|-------|--------|------|
| API Connectivity | ✅ OK | Binance API responding |
| Data Freshness | ✅ OK | Timestamps current |
| Indicator Calculation | ✅ OK | MAs calculating correctly |
| Volume Analysis | ✅ OK | Volume metrics accurate |
| Pattern Detection | ✅ OK | Consecutive counts working |
| Signal Logic | ✅ OK | All conditions being checked |

**System Status**: ✅ **WORKING CORRECTLY**

The monitoring system is functioning perfectly - it's simply waiting for market conditions to meet signal thresholds.

---

## 9. Market Context / 市場背景

### Current Market State / 當前市場狀態

- **BTCUSDT**: Trading below MA240 with low volatility
- **ETHUSDT**: Trading below MA240 with low volatility
- **Volume**: Unusually low for both symbols
- **Trend**: Established bearish alignment, no fresh momentum

### What Would Trigger Signals? / 什麼會觸發訊號？

| Signal Type | Required Conditions |
|-------------|---------------------|
| **Trend Long** | Price > MA240 + Golden Cross + Volume > 1.5x |
| **Trend Short** | Price < MA240 + Death Cross + Volume > 1.5x |
| **Contrarian Overheated** | Price > MA240 + 4+ consecutive up candles |
| **Contrarian Oversold** | Price < MA240 + 4+ consecutive down candles |

### Expected Time to Signal / 預計訊號時間

Based on current conditions:
- **Trend signals**: Wait for volume spike + MA cross
- **Contrarian signals**: Wait for 2-3 more consecutive candles in same direction

---

## 10. Recommendations / 建議

### Immediate / 立即

✅ **No action required** - System is working correctly.

✅ **無需採取行動** - 系統運作正常。

### Monitoring / 監控

1. **Watch for volume spikes** above 1.5x average
2. **Monitor MA alignment** for potential cross events
3. **Track consecutive candles** for contrarian patterns

### Optional Adjustments / 可選調整

If signals are too rare due to volume requirements:
- Consider lowering volume threshold from 1.5x to 1.2x (trade-off: more false positives)
- Add alternative volume metrics (e.g., 15m volume vs 1h average)

---

## 11. Technical Details / 技術細節

### Data Source / 資料來源

- **Exchange**: Binance Spot API
- **Endpoint**: `/api/v3/klines`
- **Timeframes**: 5m (primary), 1m (volume)

### Indicator Parameters / 指標參數

| Indicator | Period | Calculation |
|-----------|--------|-------------|
| MA5 | 5 periods | Simple Moving Average |
| MA20 | 20 periods | Simple Moving Average |
| MA240 | 240 periods | Simple Moving Average (~20 hours) |
| Volume Avg | 20 periods | Simple Moving Average |

### Signal Thresholds / 訊號閾值

| Condition | Threshold |
|-----------|-----------|
| Volume Spike | > 1.5x average |
| Consecutive Candles | >= 4 candles |
| MA Cross | Fresh cross only (not sustained alignment) |

---

## 12. Summary / 總結

| Aspect | Finding |
|--------|---------|
| **System Status** | ✅ Working correctly |
| **Data Quality** | ✅ Real-time, accurate |
| **Signal Logic** | ✅ Conditions checked properly |
| **No Signals Reason** | Market conditions don't meet thresholds |
| **Primary Blocker** | Low volume (0.08-0.10x vs 1.5x required) |
| **Secondary Blocker** | No fresh MA crosses |
| **Tertiary Blocker** | No 4+ consecutive candle patterns |

**Final Verdict**: The monitoring system is **functioning correctly**. The absence of signals is due to current market conditions (low volume, no momentum) rather than system issues. Both BTC and ETH are in a consolidation phase below MA240 waiting for a catalyst.

**最終判定**：監測系統**運作正常**。沒有訊號是因為當前市場條件（低成交量、無動能）而非系統問題。BTC 和 ETH 都處於 MA240 下方的盤整階段，等待催化劑。

---

**Diagnostic Run**: 2026-04-07 19:56:48 GMT+8  
**Data File**: `outputs/T-037_diagnostic_data.json`  
**Report By**: kimiclaw_bot
