# Strategy Card Template
# 策略卡模板

**Version**: 1.0.0  
**版本**: 1.0.0  
**Template ID**: SCT-001  
**模板識別碼**: SCT-001  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. Purpose / 目的

Standardized template for documenting trading strategies. Ensures consistent format, complete information, and easy comparison across strategies.

標準化交易策略文件模板。確保格式一致、資訊完整、便於策略間比較。

---

## 2. When to Use / 何時使用

Use this template when:

- Creating new strategy documentation / 建立新策略文件
- Updating existing strategy records / 更新現有策略記錄
- Archiving eliminated strategies / 歸檔已淘汰策略
- Sharing strategy with others / 與他人分享策略

---

## 3. Strategy Card Required Fields / 策略卡必填欄位

| Field / 欄位 | Description / 說明 | Format / 格式 |
|--------------|-------------------|---------------|
| `strategy_id` | Unique identifier / 唯一識別碼 | `[CATEGORY]_[ASSET]_[TF]_[NAME]` |
| `asset` | Trading instrument / 交易標的 | `BTCUSDT`, `ETHUSDT` |
| `timeframe` | Chart timeframe / 圖表時間框架 | `1H`, `4H`, `1D` |
| `strategy_type` | Strategy category / 策略類別 | `MR`, `Breakout`, `Breakout Failure`, `Trend` |
| `status` | Current status / 當前狀態 | `Active`, `Monitoring`, `Paused`, `Eliminated` |

### 3.1 Strategy ID Format / 策略 ID 格式

```
[CATEGORY]_[ASSET]_[TIMEFRAME]_[SHORT_NAME]

Examples / 範例:
- C1_BTC_4H_DualRegime
- A1_ETH_4H_BB_MR
- B2_BTC_1H_Breakout

Category codes / 類別代碼:
- A = Mean Reversion / 均值回歸
- B = Breakout / 突破
- C = Mixed / 混合
- D = Monitoring only / 僅監控
```

---

## 4. Basic Info Section / 基本資訊區塊

```markdown
## Basic Info / 基本資訊

| Field / 欄位 | Value / 值 |
|--------------|------------|
| Strategy ID / 策略識別碼 | [strategy_id] |
| Asset / 資產 | [BTCUSDT / ETHUSDT] |
| Timeframe / 時間框架 | [4H / 1D] |
| Type / 類型 | [MR / Breakout / Breakout Failure / Trend] |
| Status / 狀態 | [Active / Monitoring / Paused / Eliminated] |
| Created / 建立日期 | [YYYY-MM-DD] |
| Last Updated / 最後更新 | [YYYY-MM-DD] |
```

---

## 5. Strategy Logic Section / 策略邏輯區塊

### 5.1 Entry Conditions / 進場條件

```markdown
### Entry Conditions / 進場條件

| Condition / 條件 | Description / 說明 | Threshold / 閾值 |
|------------------|-------------------|------------------|
| [Condition 1] | [Description] | [Value] |
| [Condition 2] | [Description] | [Value] |

**Required / 必要**: [X] out of [N] conditions
**Time of Day / 時間限制**: [Any / Specific hours]
```

### 5.2 Exit Conditions / 出場條件

```markdown
### Exit Conditions / 出場條件

| Type / 類型 | Condition / 條件 | Value / 值 |
|-------------|------------------|------------|
| Take Profit / 止盈 | [Condition] | [Value] |
| Stop Loss / 停損 | [Condition] | [Value] |
| Time Stop / 時間停損 | [Condition] | [Value] |
| Trailing Stop / 追蹤停損 | [Condition] | [Value] |
```

### 5.3 Invalidation Conditions / 失效條件

```markdown
### Invalidation Conditions / 失效條件

When to abort entry / 何時放棄進場:
- [Condition 1]
- [Condition 2]

When to exit early / 何時提早出場:
- [Condition 1]
- [Condition 2]
```

---

## 6. Risk Section / 風險區塊

### 6.1 Position Sizing / 倉位規模

```markdown
### Position Sizing / 倉位規模

| Parameter / 參數 | Value / 值 | Notes / 備註 |
|------------------|------------|--------------|
| Risk per trade / 每筆交易風險 | [X%] | % of account / 帳戶百分比 |
| Max position size / 最大倉位 | [X%] | % of account / 帳戶百分比 |
| Scaling rule / 加減倉規則 | [Rule] | Add/reduce on [condition] |
```

### 6.2 Stop Logic / 停損邏輯

```markdown
### Stop Logic / 停損邏輯

| Stop Type / 停損類型 | Trigger / 觸發 | Action / 行動 |
|----------------------|----------------|---------------|
| Initial stop / 初始停損 | [Condition] | Close position / 平倉 |
| Breakeven / 損益平衡 | [Condition] | Move stop to entry / 停損移至進場價 |
| Trailing / 追蹤停損 | [Condition] | Adjust stop / 調整停損 |
```

### 6.3 Exposure Notes / 曝險備註

```markdown
### Exposure Notes / 曝險備註

- Correlation with other positions / 與其他部位的相關性: [Notes]
- Market condition dependency / 市場條件依賴: [Notes]
- Time-based risks / 時間相關風險: [Notes]
```

---

## 7. Performance Section / 績效區塊

### 7.1 Backtest Results / 回測結果

```markdown
### Backtest Results / 回測結果

**Period / 期間**: [Start] to [End]  
**Data quality / 資料品質**: [Ticks / OHLC]  
**Transaction costs / 交易成本**: [X%] included / 已包含

| Metric / 指標 | Value / 值 | Threshold / 閾值 | Status / 狀態 |
|---------------|------------|------------------|---------------|
| Return after costs / 含成本後報酬 | [X%] | > 0 | [✅/❌] |
| Median return / 中位數報酬 | [X%] | > 0 | [✅/❌] |
| Max drawdown / 最大回撤 | [X%] | < 30% | [✅/❌] |
| Sharpe ratio / 夏普比率 | [X] | > 0.5 | [✅/❌] |
| Win rate / 勝率 | [X%] | > 40% | [✅/❌] |
| Profit factor / 獲利因子 | [X] | > 1.0 | [✅/❌] |
| Number of trades / 交易次數 | [N] | > 100 | [✅/❌] |
```

### 7.2 Out-of-Sample Results / 樣本外結果

```markdown
### Out-of-Sample Results / 樣本外結果

**Period / 期間**: [Start] to [End]

| Metric / 指標 | In-Sample / 樣本內 | Out-Sample / 樣本外 | Degradation / 衰減 |
|---------------|-------------------|--------------------|--------------------|
| Return / 報酬 | [X%] | [X%] | [X%] |
| Sharpe / 夏普 | [X] | [X] | [X%] |
| Win rate / 勝率 | [X%] | [X%] | [X%] |

**Robustness check / 穩健性檢查**: [Pass / Fail / Notes]
```

### 7.3 Parameter Sensitivity / 參數敏感性

```markdown
### Parameter Sensitivity / 參數敏感性

| Parameter / 參數 | Tested Range / 測試範圍 | Robust Range / 穩健範圍 | Notes / 備註 |
|------------------|------------------------|------------------------|--------------|
| [Param 1] | [Range] | [Range] | [Notes] |
| [Param 2] | [Range] | [Range] | [Notes] |
```

---

## 8. Elimination / Monitoring Triggers / 淘汰與監控觸發條件

### 8.1 Hard Elimination (Immediate) / 硬性淘汰（立即）

```markdown
### Hard Elimination Triggers / 硬性淘汰觸發

| Trigger / 觸發條件 | Threshold / 閾值 | Status / 狀態 |
|--------------------|------------------|---------------|
| Return after costs / 含成本後報酬 | < 0 | [Not triggered / 未觸發] |
| Median return / 中位數報酬 | < 0 | [Not triggered / 未觸發] |

**Action if triggered**: Archive strategy, stop trading / 歸檔策略，停止交易
```

### 8.2 Soft Triggers (Review Required) / 軟性觸發（需檢討）

```markdown
### Soft Triggers / 軟性觸發

| Trigger / 觸發條件 | Threshold / 閾值 | Current / 當前 | Status / 狀態 |
|--------------------|------------------|----------------|---------------|
| Max drawdown / 最大回撤 | > 30% | [X%] | [✅/⚠️] |
| Sharpe decline / 夏普下降 | > 50% from peak | [X%] | [✅/⚠️] |
| Win rate drop / 勝率下降 | < 40% | [X%] | [✅/⚠️] |
| Consecutive losses / 連續虧損 | > 5 | [N] | [✅/⚠️] |

**Action if triggered**: Review strategy, consider pause / 檢討策略，考慮暫停
```

### 8.3 Monitoring Schedule / 監控時程

```markdown
### Monitoring Schedule / 監控時程

| Check / 檢查 | Frequency / 頻率 | Last Check / 最後檢查 |
|--------------|------------------|----------------------|
| Performance metrics / 績效指標 | Daily / 每日 | [Date] |
| Risk metrics / 風險指標 | Daily / 每日 | [Date] |
| Full review / 完整檢討 | Weekly / 每週 | [Date] |
```

---

## 9. Relationship to Criteria and Risk Control / 與 criteria 和 risk control 的關係

### 9.1 Criteria Compliance / 準則符合性

```markdown
### Criteria Compliance / 準則符合性

| Criteria / 準則 | Reference / 參考 | Compliance / 符合性 |
|-----------------|------------------|---------------------|
| Selection criteria / 選擇準則 | `research/criteria.md` Sec 3 | [✅/⚠️/❌] |
| Elimination criteria / 淘汰準則 | `research/criteria.md` Sec 4 | [✅/⚠️/❌] |
| Evidence quality / 證據品質 | `research/criteria.md` Sec 6 | [✅/⚠️/❌] |
| Overfitting check / 過度最佳化檢查 | `research/criteria.md` Sec 7 | [✅/⚠️/❌] |
```

### 9.2 Risk Control Alignment / 風險控制一致性

```markdown
### Risk Control Alignment / 風險控制一致性

| Risk Dimension / 風險維度 | Reference / 參考 | Status / 狀態 |
|---------------------------|------------------|---------------|
| Capital allocation / 資本配置 | `research/risk_control.md` Sec 2 | [✅/⚠️/❌] |
| Risk at stop / 停損風險 | `research/risk_control.md` Sec 2 | [✅/⚠️/❌] |
| Position sizing rule / 倉位規模規則 | `research/risk_control.md` Sec 3 | [✅/⚠️/❌] |
| Stop/pause conditions / 停止/暫停條件 | `research/risk_control.md` Sec 4 | [✅/⚠️/❌] |
```

---

## 10. Bilingual Formatting Rules / 中英對照格式規則

### 10.1 Headers / 標題

```markdown
## Section Name / 章節名稱
```

### 10.2 Tables / 表格

```markdown
| Field / 欄位 | Value / 值 | Status / 狀態 |
```

### 10.3 Status Indicators / 狀態指示器

| Symbol / 符號 | Meaning / 含義 |
|---------------|----------------|
| ✅ | Pass / Met / 通過 / 達成 |
| ⚠️ | Warning / Review / 警告 / 需檢討 |
| ❌ | Fail / Not met / 失敗 / 未達成 |
| ⏸️ | Paused / 暫停 |
| 🗑️ | Eliminated / 已淘汰 |

---

## 11. Example Strategy Card / 範例策略卡

**Status**: EXAMPLE ONLY / 僅為範例

### Example: A1_BTC_4H_DualRegime (Example Only / 僅為範例)

```markdown
# Strategy Card: A1_BTC_4H_DualRegime

**Status**: EXAMPLE ONLY - Not real strategy results / 僅為範例 - 非真實策略結果

## Basic Info / 基本資訊

| Field / 欄位 | Value / 值 |
|--------------|------------|
| Strategy ID / 策略識別碼 | A1_BTC_4H_DualRegime |
| Asset / 資產 | BTCUSDT |
| Timeframe / 時間框架 | 4H |
| Type / 類型 | Mixed (Trend + MR) / 混合（趨勢 + 均值回歸）|
| Status / 狀態 | Active / 進行中 |
| Created / 建立日期 | 2026-04-01 |
| Last Updated / 最後更新 | 2026-04-05 |

## Strategy Logic / 策略邏輯

### Entry Conditions / 進場條件

| Condition / 條件 | Description / 說明 | Threshold / 閾值 |
|------------------|-------------------|------------------|
| Trend condition / 趨勢條件 | Price above 200 MA / 價格在 200 MA 之上 | Close > MA200 |
| MR condition / MR 條件 | RSI oversold / RSI 超賣 | RSI < 30 |
| Volume / 成交量 | Above average / 高於平均 | Vol > SMA20 |

**Required / 必要**: 2 out of 3 conditions

### Exit Conditions / 出場條件

| Type / 類型 | Condition / 條件 | Value / 值 |
|-------------|------------------|------------|
| Take Profit / 止盈 | RSI overbought / RSI 超買 | RSI > 70 |
| Stop Loss / 停損 | Fixed % below entry / 進場下方固定百分比 | -2% |
| Time Stop / 時間停損 | Max hold time / 最大持有時間 | 20 bars |

### Invalidation Conditions / 失效條件

- Price closes below 200 MA / 價格收盤低於 200 MA
- Volume spike without price movement / 成交量飆升但價格未動

## Risk Section / 風險區塊

### Position Sizing / 倉位規模

| Parameter / 參數 | Value / 值 | Notes / 備註 |
|------------------|------------|--------------|
| Risk per trade / 每筆交易風險 | 1.5% | Per `risk_control.md` guidelines |
| Max position size / 最大倉位 | 10% | Of account / 帳戶的 |
| Scaling rule / 加減倉規則 | No scaling | Fixed size / 固定規模 |

### Stop Logic / 停損邏輯

| Stop Type / 停損類型 | Trigger / 觸發 | Action / 行動 |
|----------------------|----------------|---------------|
| Initial stop / 初始停損 | -2% from entry | Close full position |
| Breakeven / 損益平衡 | +1% profit | Move stop to entry |

## Performance Section / 績效區塊

**Status**: EXAMPLE DATA / 範例數據

| Metric / 指標 | Value / 值 | Threshold / 閾值 | Status / 狀態 |
|---------------|------------|------------------|---------------|
| Return after costs / 含成本後報酬 | +12.86% | > 0 | ✅ |
| Median return / 中位數報酬 | +0.35% | > 0 | ✅ |
| Max drawdown / 最大回撤 | -15.2% | < 30% | ✅ |
| Sharpe ratio / 夏普比率 | 0.82 | > 0.5 | ✅ |
| Win rate / 勝率 | 51.28% | > 40% | ✅ |
| Profit factor / 獲利因子 | 1.35 | > 1.0 | ✅ |
| Number of trades / 交易次數 | 39 | > 100 | ⚠️ |

## Elimination Triggers / 淘汰觸發

**Status**: EXAMPLE / 範例

| Trigger / 觸發 | Threshold / 閾值 | Current / 當前 | Status / 狀態 |
|----------------|------------------|----------------|---------------|
| Return < 0 | < 0% | +12.86% | ✅ |
| Median return < 0 | < 0% | +0.35% | ✅ |
| Max DD > 30% | > 30% | -15.2% | ✅ |

## Notes / 備註

**EXAMPLE ONLY** - This is a template example, not real strategy results.

**僅為範例** - 這是模板範例，非真實策略結果。
```

---

## 12. Naming Convention / 命名規則

### 12.1 Strategy Card File Naming / 策略卡檔案命名

```
strategies/<asset>_<timeframe>_<strategy_name>_card.md

Examples / 範例:
- strategies/BTC_4H_dual_regime_card.md
- strategies/ETH_4H_bb_mr_card.md
- strategies/BTC_1D_breakout_card.md
```

### 12.2 Strategy ID Naming / 策略 ID 命名

```
[CATEGORY]_[ASSET]_[TIMEFRAME]_[SHORT_NAME]

Examples / 範例:
- C1_BTC_4H_DualRegime
- A1_ETH_4H_BB_MR
- B2_BTC_1H_Breakout

Category codes / 類別代碼:
- A = Mean Reversion
- B = Breakout / Breakout Failure
- C = Mixed / Multi-regime
- D = Monitoring / Tracking only
```

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `research/criteria.md` - Research selection and elimination criteria / 研究選題與淘汰標準
- `research/risk_control.md` - Risk management principles / 風險管理原則
- `research/BTC_ETH_strategy_framework.md` - Strategy framework / 策略框架
