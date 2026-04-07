# T-031 Signal Quality Review / 訊號品質審查

**Task ID**: T-031  
**Title**: Review Signal Quality and Monitoring Output / 檢查訊號品質與監測輸出  
**Date**: 2026-04-07  
**Reviewer**: kimiclaw_bot  
**Status**: ✅ Review Complete

---

## 1. Purpose / 目的

This review evaluates the quality, clarity, and practical usability of the BTC/ETH monitoring system's signal design and output formatting. The goal is to identify potential issues before real-world deployment and recommend safe adjustments.

本次審查評估 BTC/ETH 監測系統的訊號設計與輸出格式的品質、清晰度與實用性。目標是在實際部署前識別潛在問題並建議安全調整。

**Scope Limitations / 範圍限制**:
- Review based on design documents and sample outputs / 基於設計文件與範例輸出的審查
- No extensive real-market testing data available / 無大量真實市場測試資料
- Focus on structural and design issues / 聚焦結構與設計問題

---

## 2. Review Scope / 審查範圍

### Documents Reviewed / 審查文件

| File / 檔案 | Purpose / 目的 | Status / 狀態 |
|-------------|----------------|---------------|
| `workflows/btc_eth_monitoring_signal_spec.md` | Signal specification / 訊號規格 | ✅ Reviewed |
| `signals/engine.py` | Signal generation logic / 訊號產生邏輯 | ✅ Reviewed |
| `notifications/formatter.py` | Output formatting / 輸出格式化 | ✅ Reviewed |
| `outputs/T-028_local_validation_report.md` | Validation results / 驗證結果 | ✅ Reviewed |
| `app/example_run_output.md` | Sample outputs / 範例輸出 | ✅ Reviewed |

### System Components Reviewed / 審查的系統元件

| Component / 元件 | Version / 版本 | Status / 狀態 |
|------------------|----------------|---------------|
| Signal Engine / 訊號引擎 | 1.0.0 | ✅ Reviewed |
| Notification Formatter / 通知格式化器 | 1.0.0 | ✅ Reviewed |
| Cooldown Manager / 冷卻管理器 | 1.0.0 | ✅ Reviewed |

---

## 3. Signal Types Reviewed / 審查的訊號類型

### 3.1 Signal Type Summary / 訊號類型摘要

| Signal Type | Level | Conditions | Cooldown |
|-------------|-------|------------|----------|
| `trend_long` | Confirmed | C1: close > MA240, C2: MA5 cross above MA20, C3: volume > 2x | 15 min |
| `trend_short` | Confirmed | C1: close < MA240, C2: MA5 cross below MA20, C3: volume > 2x | 15 min |
| `contrarian_watch_overheated` | Watch Only | 4 consecutive red candles (15m) | 30 min |
| `contrarian_watch_oversold` | Watch Only | 4 consecutive green candles (15m) | 30 min |

### 3.2 Signal Design Clarity Assessment / 訊號設計清晰度評估

| Aspect | Rating | Notes |
|--------|--------|-------|
| Naming Convention / 命名慣例 | ✅ Good | Clear, consistent naming |
| Level Distinction / 層級區分 | ✅ Good | Confirmed vs Watch Only clearly separated |
| Warning Labels / 警告標籤 | ✅ Good | All signals include appropriate warnings |
| Alert-Only Enforcement / 僅提醒強制 | ✅ Good | No execution logic present |

---

## 4. Output Readability Review / 輸出可讀性審查

### 4.1 Output Formats / 輸出格式

| Format | Status | Assessment |
|--------|--------|------------|
| Plain Text | ✅ Available | Human-readable, includes all key data |
| Markdown | ✅ Available | Structured, good for documentation |
| JSON | ✅ Available | Machine-readable, complete schema |
| Compact | ✅ Available | One-line summary for quick scanning |

### 4.2 Output Clarity Issues / 輸出清晰度問題

#### Issue 1: Missing Timestamp Context / 缺少時間戳上下文

**Current / 目前**:
```
Symbol: BTCUSDT
Time: 2026-04-06 11:30:15
```

**Problem / 問題**: Timezone not explicitly labeled / 時區未明確標示

**Recommendation / 建議**: Add timezone indicator / 添加時區指示器
```
Time: 2026-04-06 11:30:15 UTC
Market Time: 2026-04-06 19:30:15 UTC+8
```

#### Issue 2: Price Formatting Consistency / 價格格式一致性

**Current / 目前**: Prices shown with varying decimal places / 價格顯示不同小數位數

**Recommendation / 建議**: Standardize to 2 decimal places for USD values / 統一為 2 位小數
```
Close: $69,250.50 (instead of 69250.5)
```

#### Issue 3: Volume Context Missing / 缺少成交量上下文

**Current / 目前**: Shows raw volume numbers / 顯示原始成交量數字

**Problem / 問題**: Hard to interpret without reference / 無參考基準難以理解

**Recommendation / 建議**: Show volume in BTC/ETH units with USD equivalent / 顯示 BTC/ETH 單位與 USD 等值
```
Volume: 12.50 BTC (~$866,250)
```

---

## 5. Trend Signal Review / 順勢訊號審查

### 5.1 Trend Long/Short Strictness Assessment / 順勢訊號嚴格度評估

#### Current Conditions / 目前條件

| Condition | Requirement | Strictness |
|-----------|-------------|------------|
| C1: Price vs MA240 | Must be above (long) or below (short) | Moderate |
| C2: MA Cross | Must be golden cross (long) or death cross (short) | Strict |
| C3: Volume | Must be > 2x average | Strict |

#### Assessment / 評估

| Aspect | Finding | Risk Level |
|--------|---------|------------|
| Signal Frequency / 訊號頻率 | Likely LOW due to strict conditions / 條件嚴格可能導致訊號稀少 | ⚠️ Medium |
| False Positive Rate / 假陽性率 | Likely LOW (strict filters) / 可能較低（嚴格過濾） | ✅ Low |
| Missed Opportunities / 錯失機會 | May miss early trend entries / 可能錯失早期趨勢進場 | ⚠️ Medium |

#### Finding: Volume Threshold May Be Too Strict / 發現：成交量閾值可能過嚴

**Current / 目前**: `volume > 2.0x average` required / 需要成交量 > 2.0 倍平均

**Problem / 問題**: 
- In normal market conditions, 2x volume spikes are relatively rare / 在正常市場條件下，2 倍成交量激增相對稀少
- May filter out valid signals during moderate volume increases / 可能過濾掉中等成交量增加時的有效訊號

**Evidence / 證據**:
- T-028 validation showed volume ratio of 0.41x-1.06x (no signals generated) / T-028 驗證顯示成交量比率 0.41x-1.06x（無訊號產生）
- This is typical for normal market conditions / 這是正常市場條件的典型情況

**Recommendation / 建議**: Consider lowering to 1.5x for testing / 考慮降低到 1.5x 進行測試
```python
# Current
VOLUME_THRESHOLD = 2.0

# Suggested for testing
VOLUME_THRESHOLD = 1.5
```

### 5.2 MA Cross Detection Timing / MA 交叉檢測時機

**Current Logic / 目前邏輯**: Detects cross on current candle / 在當前 K 線檢測交叉

**Potential Issue / 潛在問題**: 
- May generate signals on weak crosses / 可能在弱交叉時產生訊號
- No confirmation period / 無確認期間

**Recommendation / 建議**: Consider requiring 1-candle confirmation / 考慮要求 1 K 線確認
```python
# Instead of immediate detection
cross_detected = detect_ma_cross(ma5, ma20) == CrossType.CROSS_ABOVE

# Require confirmation
cross_confirmed = (
    detect_ma_cross(ma5, ma20) == CrossType.CROSS_ABOVE and
    ma5[-1] > ma20[-1]  # Confirm on next candle
)
```

---

## 6. Contrarian Watch Review / 逆勢觀察審查

### 6.1 Watch-Only Labeling / 僅觀察標示

| Aspect | Status | Notes |
|--------|--------|-------|
| Level Assignment / 層級分配 | ✅ Correct | WATCH_ONLY properly assigned |
| Warning Text / 警告文字 | ✅ Clear | "WATCH_ONLY_NOT_EXECUTION_SIGNAL" |
| Visual Distinction / 視覺區分 | ✅ Good | Different emoji (👁️ vs ✅) |

### 6.2 Contrarian Signal Conditions / 逆勢訊號條件

#### Current Conditions / 目前條件

| Signal | Condition | Timeframe |
|--------|-----------|-----------|
| Overheated / 過熱 | 4 consecutive red candles | 15m |
| Oversold / 超賣 | 4 consecutive green candles | 15m |

#### Assessment / 評估

| Aspect | Finding | Risk |
|--------|---------|------|
| Pattern Simplicity / 型態簡單性 | ✅ Very simple | Easy to understand |
| False Positive Risk / 假陽性風險 | ⚠️ Moderate | 4 candles can occur in normal trends |
| Timeframe Appropriateness / 時間框架適當性 | ✅ Good | 15m balances noise and lag |

#### Finding: Pattern May Be Too Simple / 發現：型態可能過於簡單

**Current / 目前**: Only checks consecutive closes vs opens / 僅檢查連續收盤 vs 開盤

**Problem / 問題**:
- Doesn't consider candle size / 不考慮 K 線大小
- Doesn't consider volume during pattern / 不考慮型態期間成交量
- Can trigger in normal trending markets / 可能在正常趨勢市場中觸發

**Example Scenario / 範例情境**:
- Strong uptrend with small pullbacks / 強勁上升趨勢伴隨小幅回調
- 4 small red candles appear / 出現 4 根小紅 K
- Signal generated but trend continues / 產生訊號但趨勢繼續

**Recommendation / 建議**: Consider adding minimum candle size filter / 考慮添加最小 K 線大小過濾器
```python
# Add minimum body size requirement
min_body_size = avg_candle_body * 0.3  # At least 30% of average
valid_red = close < open and (open - close) > min_body_size
```

### 6.3 Contrarian Signal Value / 逆勢訊號價值

| Aspect | Assessment |
|--------|------------|
| Educational Value / 教育價值 | ✅ Good for learning pattern recognition |
| Trading Value / 交易價值 | ⚠️ Low without additional confirmation |
| Alert Fatigue Risk / 提醒疲勞風險 | ⚠️ Moderate if too frequent |

**Recommendation / 建議**: 
- Keep contrarian signals but ensure clear labeling / 保留逆勢訊號但確保清晰標示
- Consider adding RSI or other confirmation for future versions / 考慮為未來版本添加 RSI 或其他確認

---

## 7. Cooldown and Duplicate Review / 冷卻與重複提醒審查

### 7.1 Current Cooldown Settings / 目前冷卻設定

| Signal Type | Cooldown | Assessment |
|-------------|----------|------------|
| trend_long | 15 minutes | ✅ Appropriate for 5m timeframe |
| trend_short | 15 minutes | ✅ Appropriate for 5m timeframe |
| contrarian_watch_* | 30 minutes | ✅ Good for reducing noise |

### 7.2 Cooldown Effectiveness / 冷卻有效性

| Aspect | Status | Notes |
|--------|--------|-------|
| Duplicate Prevention / 重複防止 | ✅ Working | Prevents spam within cooldown period |
| Per-Symbol Scope / 每標的範圍 | ✅ Correct | BTC and ETH tracked separately |
| Memory Usage / 記憶體使用 | ✅ Efficient | Simple dict-based storage |

### 7.3 Potential Issue: Cooldown Reset / 潛在問題：冷卻重置

**Current Behavior / 目前行為**: Cooldown resets after period expires / 冷卻在期限過期後重置

**Potential Problem / 潛在問題**: 
- If condition persists, signal may fire repeatedly / 若條件持續，訊號可能重複觸發
- Example: MA stays crossed for extended period / 範例：MA 持續交叉延長期間

**Mitigation / 緩解**:
- Current design already handles this with cooldown / 目前設計已用冷卻處理此問題
- 15-minute cooldown means max 4 signals/hour per type / 15 分鐘冷卻意味每類型每小時最多 4 個訊號

**Assessment / 評估**: ✅ Current settings are reasonable / 目前設定合理

---

## 8. Alert Context Review / 提醒上下文審查

### 8.1 Current Alert Content / 目前提醒內容

| Data Point | Included | Importance |
|------------|----------|------------|
| Signal Type | ✅ Yes | Critical |
| Symbol | ✅ Yes | Critical |
| Timestamp | ✅ Yes | Critical |
| Price Data | ✅ Yes | High |
| MA Values | ✅ Yes | High |
| Volume Data | ✅ Yes | Medium |
| Conditions Met | ✅ Yes | High |
| Warning Text | ✅ Yes | Critical |

### 8.2 Missing Context (Nice to Have) / 缺少上下文（有則更佳）

| Data Point | Current | Recommendation |
|------------|---------|----------------|
| Trend Direction | Partial | Show "Bullish/Bearish" label explicitly |
| Time Since Last Signal | ❌ No | Add for continuity tracking |
| Signal History Count | ❌ No | Show "3rd signal today" etc. |
| Market Session | ❌ No | Add "Asia/Europe/US session" |
| Price Change % | ❌ No | Show 24h change for context |

### 8.3 Alert Actionability / 提醒可操作性

| Aspect | Status | Notes |
|--------|--------|-------|
| Clear Signal Type | ✅ Yes | User knows what happened |
| Clear Level | ✅ Yes | User knows urgency |
| Price Context | ✅ Yes | User knows current price |
| Suggested Action | ⚠️ Partial | "Watch only" or "Confirmed" but no specific guidance |

**Recommendation / 建議**: Add brief guidance text / 添加簡短指引文字
```
For confirmed signals: "Review for potential entry opportunity"
For watch signals: "Observe for additional confirmation before action"
```

---

## 9. Risk of False Positives / 假陽性風險

### 9.1 False Positive Assessment by Signal Type / 按訊號類型的假陽性評估

| Signal Type | False Positive Risk | Primary Cause |
|-------------|---------------------|---------------|
| trend_long | 🟡 Low-Medium | Strict conditions reduce FP, but volume spike may be coincidental |
| trend_short | 🟡 Low-Medium | Same as trend_long |
| contrarian_watch_overheated | 🟠 Medium | Simple pattern can trigger in normal trends |
| contrarian_watch_oversold | 🟠 Medium | Same as overheated |

### 9.2 Mitigation Strategies / 緩解策略

| Strategy | Implementation | Effectiveness |
|----------|----------------|---------------|
| Strict Volume Threshold | 2.0x required | High for trend signals |
| Cooldown Periods | 15-30 min | Medium |
| Multiple Conditions | 3 for trend, 1 for contrarian | High for trend, Low for contrarian |
| Watch-Only Labeling | Clear warnings | High (prevents wrong actions) |

### 9.3 Recommendation / 建議

Current false positive protection is **adequate for initial deployment** but can be improved:

1. **Trend Signals**: Lower volume threshold to 1.5x for more signals / 降低成交量閾值至 1.5x 以獲得更多訊號
2. **Contrarian Signals**: Add minimum candle size filter / 添加最小 K 線大小過濾器
3. **Both**: Consider adding RSI or MACD confirmation in future versions / 考慮在未來版本添加 RSI 或 MACD 確認

---

## 10. Risk of Missing Useful Signals / 漏訊號風險

### 10.1 Signal Generation Threshold Assessment / 訊號產生閾值評估

| Condition | Current | Risk of Missing Signals |
|-----------|---------|-------------------------|
| Volume > 2.0x | Strict | ⚠️ High - May miss valid trends with 1.5x-2.0x volume |
| MA Cross | Required | ✅ Low - Core requirement, should not relax |
| Price vs MA240 | Required | ✅ Low - Core requirement, should not relax |
| 4 Consecutive Candles | Simple | ✅ Low - Will catch most extended moves |

### 10.2 Missed Signal Scenarios / 漏訊號情境

#### Scenario 1: Moderate Volume Trend / 中等成交量趨勢

**Market Condition / 市場條件**:
- Clear uptrend established / 明確上升趨勢建立
- Volume increases to 1.7x average / 成交量增加至 1.7 倍平均
- Price above MA240, MA5 crosses MA20 / 價格在 MA240 之上，MA5 交叉 MA20

**Current Result / 目前結果**: No signal generated (volume < 2.0x) / 無訊號產生

**Risk Assessment / 風險評估**: ⚠️ **HIGH** - Valid trend signal missed / 錯失有效趨勢訊號

#### Scenario 2: Early Trend Entry / 早期趨勢進場

**Market Condition / 市場條件**:
- Price breaks above MA240 / 價格突破 MA240
- Volume only 1.3x (early stage) / 成交量僅 1.3x（早期階段）
- MA5 not yet crossed MA20 / MA5 尚未交叉 MA20

**Current Result / 目前結果**: No signal (conditions not met) / 無訊號（條件未滿足）

**Risk Assessment / 風險評估**: 🟡 Medium - Design choice for confirmation / 中等 - 確認的設計選擇

### 10.3 Recommendation / 建議

**Primary Issue / 主要問題**: Volume threshold of 2.0x is likely too strict for initial deployment.

**Suggested Adjustment / 建議調整**:
```python
# In signals/engine.py or configuration
VOLUME_SPIKE_THRESHOLD = 1.5  # Was 2.0
```

**Expected Impact / 預期影響**:
- More signals generated / 產生更多訊號
- Slightly higher false positive rate / 稍高的假陽性率
- Better capture of early trends / 更好捕捉早期趨勢

---

## 11. Ready vs Not Ready / 已就緒與未就緒

### 11.1 Ready for Real Reminder Use / 已就緒用於真實提醒

| Component | Status | Notes |
|-----------|--------|-------|
| Core Signal Generation | ✅ Ready | Well-designed, alert-only enforced |
| Output Formatting | ✅ Ready | Multiple formats available |
| Notification Channels | ✅ Ready | Console, Discord, File working |
| Cooldown Management | ✅ Ready | Prevents spam |
| Documentation | ✅ Ready | Comprehensive specs and READMEs |
| Alert-Only Safety | ✅ Ready | No execution logic present |

### 11.2 Needs Adjustment Before Production / 生產前需要調整

| Component | Status | Priority |
|-----------|--------|----------|
| Volume Threshold / 成交量閾值 | ⚠️ Review Recommended | High - May be too strict |
| Contrarian Pattern Filter / 逆勢型態過濾器 | ⚠️ Review Recommended | Medium - May be too simple |
| Timestamp Timezone / 時間戳時區 | ⚠️ Minor | Low - Cosmetic improvement |

### 11.3 Not Blockers but Nice to Have / 非阻擋但有則更佳

| Feature | Status | Notes |
|---------|--------|-------|
| Signal History Tracking | ⏳ Future | Track signal frequency over time |
| Performance Metrics | ⏳ Future | Win/loss tracking for signals |
| Additional Confirmations | ⏳ Future | RSI, MACD for contrarian signals |

---

## 12. Recommended Next Actions / 建議下一步

### Immediate (Before Production) / 立即（生產前）

1. **Test with Lower Volume Threshold / 用較低成交量閾值測試**
   - Change `VOLUME_SPIKE_THRESHOLD` from 2.0 to 1.5
   - Run 24-hour monitoring period
   - Compare signal frequency and quality

2. **Add Timezone Context / 添加時區上下文**
   - Update formatter to show both UTC and local time
   - Minor code change, improves usability

3. **Document Known Limitations / 記錄已知限制**
   - Contrarian signals are pattern-only (no volume/price confirmation)
   - System is designed for observation, not automated trading

### Short Term (First Week) / 短期（第一週）

4. **Monitor Signal Frequency / 監控訊號頻率**
   - Track how many signals per day actually generate
   - If < 2 signals/day, consider lowering thresholds
   - If > 20 signals/day, consider raising thresholds

5. **Validate Contrarian Signals / 驗證逆勢訊號**
   - Manually review first 10 contrarian signals
   - Assess if they correspond to actual reversal zones
   - Adjust pattern complexity if needed

### Medium Term (First Month) / 中期（第一個月）

6. **Add Performance Tracking / 添加效能追蹤**
   - Log signal outcomes (manual tracking)
   - Calculate rough accuracy rate
   - Identify which signal types are most reliable

7. **Consider Additional Filters / 考慮額外過濾器**
   - RSI for overbought/oversold confirmation
   - ATR for volatility context
   - Market session detection

### Not Recommended / 不建議

- ❌ Adding auto-trading logic / 添加自動交易邏輯
- ❌ Removing alert-only warnings / 移除僅提醒警告
- ❌ Lowering cooldown periods / 降低冷卻期間
- ❌ Major signal engine rewrite / 重大訊號引擎重寫

---

## Summary / 總結

| Aspect | Assessment |
|--------|------------|
| Overall System Quality | ✅ Good - Well-designed, safe, documented |
| Signal Design | ✅ Good - Clear types, appropriate levels |
| Output Quality | ✅ Good - Multiple formats, readable |
| False Positive Risk | 🟡 Low-Medium - Acceptable for initial use |
| Missed Signal Risk | ⚠️ Medium - Volume threshold may be too strict |
| Ready for Production | ✅ Yes - With minor adjustments noted above |

**Bottom Line / 結論**: The monitoring system is well-designed and ready for initial deployment as an alert-only system. The primary recommendation is to test with a lower volume threshold (1.5x instead of 2.0x) to ensure sufficient signal frequency for practical use.

監測系統設計良好，已就緒作為僅提醒系統的初始部署。主要建議是測試較低的成交量閾值（1.5x 而非 2.0x），以確保有足夠的訊號頻率供實際使用。

---

**Review Completed**: 2026-04-07  
**Reviewer**: kimiclaw_bot  
**Next Review Recommended**: After 1 week of live monitoring
