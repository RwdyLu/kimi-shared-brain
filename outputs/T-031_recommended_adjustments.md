# T-031 Recommended Adjustments / 建議調整

**Task ID**: T-031  
**Document**: Signal Quality Review Follow-up / 訊號品質審查後續  
**Date**: 2026-04-07

---

## Executive Summary / 執行摘要

Based on the signal quality review, this document categorizes recommended adjustments by priority. **All adjustments maintain the alert-only design** — no auto-trading logic is introduced.

基於訊號品質審查，本文件按優先級分類建議調整。**所有調整均維持僅提醒設計**——未引入自動交易邏輯。

---

## 1. High Priority Adjustments / 高優先修正

These adjustments should be implemented before or during initial production deployment.

這些調整應在初始生產部署前或期間實作。

### 1.1 Lower Volume Threshold / 降低成交量閾值

**Current / 目前**: `VOLUME_SPIKE_THRESHOLD = 2.0`

**Proposed / 建議**: `VOLUME_SPIKE_THRESHOLD = 1.5`

**Rationale / 理由**:
- 2.0x threshold is too strict for normal market conditions / 2.0x 閾值對正常市場條件過嚴
- T-028 validation showed volume ratios of 0.41x-1.06x (no signals) / T-028 驗證顯示成交量比率 0.41x-1.06x（無訊號）
- May miss valid trend signals with moderate volume / 可能錯失中等成交量的有效趨勢訊號

**Expected Impact / 預期影響**:
- More signals generated / 產生更多訊號
- Slightly higher false positive rate / 稍高的假陽性率
- Better early-trend capture / 更好捕捉早期趨勢

**Implementation / 實作**:
```python
# In indicators/calculator.py or signals/engine.py
VOLUME_SPIKE_THRESHOLD = 1.5  # Changed from 2.0
```

**Testing Recommendation / 測試建議**:
- Run 24-hour comparison test / 執行 24 小時比較測試
- Compare signal frequency at 1.5x vs 2.0x / 比較 1.5x 與 2.0x 的訊號頻率
- Target: 3-8 signals per day across both symbols / 目標：兩標的每天 3-8 個訊號

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

### 1.2 Add Explicit Timezone Labels / 添加明確時區標籤

**Current / 目前**: `Time: 2026-04-06 11:30:15`

**Proposed / 建議**: 
```
Time (UTC): 2026-04-06 11:30:15
Time (Local): 2026-04-06 19:30:15 UTC+8
```

**Rationale / 理由**:
- Prevents confusion about market timing / 防止市場時間混淆
- Important for cross-timezone teams / 對跨時區團隊重要
- Simple cosmetic improvement / 簡單的外觀改進

**Implementation / 實作**:
```python
# In notifications/formatter.py
from datetime import datetime, timezone

def format_timestamp(self, timestamp_ms: int) -> str:
    dt_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    dt_local = dt_utc.astimezone()  # Convert to local
    return f"Time (UTC): {dt_utc.strftime('%Y-%m-%d %H:%M:%S')}\nTime (Local): {dt_local.strftime('%Y-%m-%d %H:%M:%S %Z')}"
```

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

## 2. Medium Priority Adjustments / 中優先修正

These adjustments improve usability but are not blockers for initial deployment.

這些調整改善可用性，但不是初始部署的阻擋器。

### 2.1 Add Minimum Candle Size Filter for Contrarian / 為逆勢訊號添加最小 K 線大小過濾器

**Current / 目前**: 4 consecutive candles (any size) / 4 根連續 K 線（任何大小）

**Proposed / 建議**: 4 consecutive candles with minimum body size / 4 根連續 K 線且最小實體大小

**Rationale / 理由**:
- Current pattern is too simple / 目前型態過於簡單
- Can trigger on small doji-like candles / 可能在小型類十字星 K 線上觸發
- Reduces false positives in normal trends / 減少正常趨勢中的假陽性

**Implementation / 實作**:
```python
# In indicators/calculator.py
def detect_four_consecutive_red_with_size(
    candles: List[KlineData], 
    min_body_ratio: float = 0.3
) -> bool:
    """
    Detect 4 consecutive red candles with minimum body size.
    min_body_ratio: minimum body size as ratio of average candle body
    """
    if len(candles) < 4:
        return False
    
    # Calculate average body size
    bodies = [abs(c.close - c.open) for c in candles]
    avg_body = sum(bodies) / len(bodies)
    min_body = avg_body * min_body_ratio
    
    # Check last 4 candles
    for i in range(1, 5):
        candle = candles[-i]
        body = candle.open - candle.close  # Red candle: open > close
        if body < min_body:  # Too small
            return False
    
    return True
```

**Testing Recommendation / 測試建議**:
- Backtest on recent 15m data / 在最近 15m 資料上回測
- Compare signal frequency with/without size filter / 比較有/無大小過濾器的訊號頻率

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

### 2.2 Add Brief Action Guidance / 添加簡短行動指引

**Current / 目前**: Only shows signal type and warning / 僅顯示訊號類型與警告

**Proposed / 建議**: Add one-line guidance / 添加一行指引

**Rationale / 理由**:
- Helps users understand what to do with signal / 幫助使用者理解如何處理訊號
- Reduces confusion between confirmed and watch signals / 減少確認與觀察訊號之間的混淆

**Implementation / 實作**:
```python
# In notifications/formatter.py
def _get_guidance(self, signal: Signal) -> str:
    """Get brief action guidance based on signal type and level"""
    if signal.level == SignalLevel.CONFIRMED:
        if signal.signal_type in [SignalType.TREND_LONG, SignalType.TREND_SHORT]:
            return "💡 Review chart for potential trend entry opportunity"
    elif signal.level == SignalLevel.WATCH_ONLY:
        return "💡 Observe for additional confirmation before any action"
    return ""
```

**Output Example / 輸出範例**:
```
📈 TREND LONG ✅ CONFIRMED
Symbol: BTCUSDT
...
💡 Review chart for potential trend entry opportunity
⚠️  ALERT_ONLY_NO_AUTO_TRADE
```

**Safety Check / 安全檢查**: ✅ No impact on alert-only design (still informational only)

---

### 2.3 Standardize Price Formatting / 標準化價格格式

**Current / 目前**: Inconsistent decimal places / 不一致的小數位數

**Proposed / 建議**: Standardize to 2 decimals with currency symbol / 標準化為 2 位小數並帶貨幣符號

**Rationale / 理由**:
- Improves readability / 改善可讀性
- Professional appearance / 專業外觀

**Implementation / 實作**:
```python
# In notifications/formatter.py
def _format_price(self, price: float) -> str:
    """Format price with 2 decimal places and $ symbol"""
    return f"${price:,.2f}"

# Usage
lines.append(f"  Close (5m): {self._format_price(price_data['close_5m'])}")
```

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

## 3. Low Priority Adjustments / 低優先修正

These are nice-to-have improvements that can be deferred.

這些是有則更佳的改進，可以延後。

### 3.1 Add Signal History Counter / 添加訊號歷史計數器

**Proposed / 建議**: Show "Signal #3 today" in output / 在輸出中顯示「今日第 3 個訊號」

**Rationale / 理由**:
- Helps track signal frequency / 幫助追蹤訊號頻率
- Provides context for repeated signals / 為重複訊號提供上下文

**Implementation Complexity / 實作複雜度**: Medium (requires persistent storage)

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

### 3.2 Add Market Session Indicator / 添加市場時段指示器

**Proposed / 建議**: Show "Asia Session", "Europe Session", "US Session" / 顯示「亞洲時段」、「歐洲時段」、「美國時段」

**Rationale / 理由**:
- Provides market context / 提供市場上下文
- Different sessions have different characteristics / 不同時段有不同特徵

**Implementation Complexity / 實作複雜度**: Low

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

### 3.3 Add 24h Price Change Context / 添加 24 小時價格變化上下文

**Proposed / 建議**: Show "24h: +5.2%" alongside signal / 在訊號旁顯示「24h: +5.2%」

**Rationale / 理由**:
- Provides broader market context / 提供更廣泛的市場上下文
- Helps assess if signal aligns with larger trend / 幫助評估訊號是否與較大趨勢一致

**Implementation Complexity / 實作複雜度**: Medium (requires additional data fetch)

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

## 4. Safe Tweaks Only / 僅限安全微調

These adjustments are safe to make without system redesign.

這些調整可以安全進行，無需系統重設計。

### 4.1 Configuration File Extraction / 配置檔案提取

**Current / 目前**: Thresholds hardcoded in source files / 閾值硬編碼在原始檔案中

**Proposed / 建議**: Extract to `config.py` or `settings.yaml` / 提取到 `config.py` 或 `settings.yaml`

**Benefits / 益處**:
- Easier adjustment without code changes / 無需修改程式碼即可調整
- Environment-specific settings / 環境特定設定
- User customization / 使用者自定義

**Example Config / 範例配置**:
```python
# config.py
VOLUME_SPIKE_THRESHOLD = 1.5  # Was 2.0
COOLDOWN_TREND_MINUTES = 15
COOLDOWN_CONTRARIAN_MINUTES = 30
ENABLE_CONTRARIAN_SIGNALS = True
```

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

### 4.2 Add Optional Debug Output / 添加可選除錯輸出

**Proposed / 建議**: Add `--debug` flag for verbose output / 添加 `--debug` 旗標用於詳細輸出

**Benefits / 益處**:
- Easier troubleshooting / 更容易故障排除
- Better visibility into signal logic / 更好檢視訊號邏輯

**Safety Check / 安全檢查**: ✅ No impact on alert-only design

---

## 5. Items That Should NOT Be Changed Yet / 暫時不該更動的項目

These items are working well and should not be modified at this stage.

這些項目運作良好，現階段不應修改。

### 5.1 Alert-Only Design / 僅提醒設計

**Status / 狀態**: ✅ Working correctly

**Why Not Change / 為何不更改**: Core safety requirement / 核心安全需求

### 5.2 Signal Type Definitions / 訊號類型定義

**Status / 狀態**: ✅ Clear and appropriate

**Why Not Change / 為何不更改**: Well-designed, distinct purposes / 設計良好，目的明確

### 5.3 Cooldown Periods / 冷卻期間

**Status / 狀態**: ✅ Appropriate (15min for trend, 30min for contrarian)

**Why Not Change / 為何不更改**: Prevents spam while allowing valid follow-up signals / 防止垃圾訊息同時允許有效後續訊號

### 5.4 MA Cross Detection Logic / MA 交叉檢測邏輯

**Status / 狀態**: ✅ Correct

**Why Not Change / 為何不更改**: Core signal mechanism, proven design pattern / 核心訊號機制，經驗證的設計模式

### 5.5 Price vs MA240 Condition / 價格對 MA240 條件

**Status / 狀態**: ✅ Appropriate for trend filtering

**Why Not Change / 為何不更改**: Ensures alignment with long-term trend / 確保與長期趨勢一致

### 5.6 Watch-Only Level for Contrarian / 逆勢的僅觀察層級

**Status / 狀態**: ✅ Correctly classified

**Why Not Change / 為何不更改**: Safety feature, contrarian signals should never be auto-executed / 安全功能，逆勢訊號永遠不應自動執行

---

## Implementation Priority Matrix / 實作優先級矩陣

| Adjustment | Priority | Effort | Impact | Safety |
|------------|----------|--------|--------|--------|
| Lower volume threshold | 🔴 High | Low | High | ✅ Safe |
| Add timezone labels | 🔴 High | Low | Medium | ✅ Safe |
| Extract config file | 🟡 Medium | Low | Medium | ✅ Safe |
| Add candle size filter | 🟡 Medium | Medium | Medium | ✅ Safe |
| Add action guidance | 🟡 Medium | Low | Medium | ✅ Safe |
| Standardize price format | 🟡 Medium | Low | Low | ✅ Safe |
| Add debug output | 🟢 Low | Low | Low | ✅ Safe |
| Add signal counter | 🟢 Low | Medium | Low | ✅ Safe |
| Add market session | 🟢 Low | Low | Low | ✅ Safe |
| Add 24h change | 🟢 Low | Medium | Low | ✅ Safe |

---

## Testing Plan for Adjustments / 調整測試計畫

### Phase 1: High Priority (Week 1) / 第一階段：高優先（第一週）

1. Implement volume threshold change (1.5x) / 實作成交量閾值變更（1.5x）
2. Run 24-hour parallel test (1.5x vs 2.0x) / 執行 24 小時平行測試（1.5x vs 2.0x）
3. Document signal frequency difference / 記錄訊號頻率差異
4. Add timezone labels / 添加時區標籤

### Phase 2: Medium Priority (Week 2-3) / 第二階段：中優先（第 2-3 週）

5. Implement config file extraction / 實作配置檔案提取
6. Add candle size filter for contrarian / 為逆勢添加 K 線大小過濾器
7. Add action guidance text / 添加行動指引文字
8. Standardize price formatting / 標準化價格格式

### Phase 3: Low Priority (Month 2+) / 第三階段：低優先（第 2 個月後）

9. Implement nice-to-have features / 實作有則更佳功能
10. Add performance tracking / 添加效能追蹤

---

## Summary / 總結

| Category | Count | Key Items |
|----------|-------|-----------|
| High Priority / 高優先 | 2 | Volume threshold, Timezone labels |
| Medium Priority / 中優先 | 4 | Config file, Candle filter, Guidance, Price format |
| Low Priority / 低優先 | 3 | Signal counter, Market session, 24h change |
| Safe Tweaks / 安全微調 | 2 | Config extraction, Debug output |
| Do Not Change / 不更改 | 6 | Core design elements |

**Immediate Action Items / 立即行動項目**:
1. Change `VOLUME_SPIKE_THRESHOLD` to 1.5
2. Add explicit timezone labels to output
3. Begin 24-hour signal frequency monitoring

**Bottom Line / 結論**: Focus on the 2 high-priority items first. They provide the most value with minimal risk. Reserve medium and low priority items for subsequent iterations after initial deployment feedback.

首先專注於 2 個高優先項目。它們以最小風險提供最大價值。將中低優先項目保留給初始部署反饋後的後續迭代。

---

**Document Created**: 2026-04-07  
**Author**: kimiclaw_bot  
**Review Status**: Complete
