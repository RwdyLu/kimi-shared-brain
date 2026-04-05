# Trade Plan Template
# 交易計畫模板

**Version**: 1.0.0  
**版本**: 1.0.0  
**Template ID**: TPT-001  
**模板識別碼**: TPT-001  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. Purpose / 目的

Standardized template for creating executable trade plans. Translates strategy logic into actionable steps for specific trade setups.

標準化交易計畫模板。將策略邏輯轉化為特定交易設定的可執行步驟。

---

## 2. When to Use / 何時使用

Use this template when:

- A valid trade setup is identified / 識別到有效交易設定時
- Strategy signals are triggered / 策略訊號被觸發時
- Preparing for execution / 準備執行時
- Reviewing trade performance / 審查交易績效時

---

## 3. Trade Plan Required Fields / 交易計畫必填欄位

| Field / 欄位 | Description / 說明 | Format / 格式 |
|--------------|-------------------|---------------|
| `plan_id` | Unique trade plan ID / 唯一交易計畫識別碼 | `PLAN_[STRATEGY_ID]_[DATE]` |
| `related_strategy_id` | Linked strategy card / 關聯策略卡 | `[CATEGORY]_[ASSET]_[TF]_[NAME]` |
| `asset` | Trading instrument / 交易標的 | `BTCUSDT`, `ETHUSDT` |
| `timeframe` | Chart timeframe / 圖表時間框架 | `1H`, `4H`, `1D` |
| `status` | Plan status / 計畫狀態 | `Active`, `Executed`, `Cancelled`, `Completed` |

### 3.1 Plan ID Format / 計畫 ID 格式

```
PLAN_[STRATEGY_ID]_[YYYYMMDD]_[SEQUENCE]

Examples / 範例:
- PLAN_C1_BTC_4H_DualRegime_20260405_01
- PLAN_A1_ETH_4H_BB_MR_20260405_02
```

---

## 4. Setup Conditions / 設定條件

### 4.1 Market Context / 市場背景

```markdown
### Market Context / 市場背景

| Factor / 因素 | Status / 狀態 | Notes / 備註 |
|---------------|---------------|--------------|
| Trend direction / 趨勢方向 | [Bullish / Bearish / Neutral] | [Analysis] |
| Market regime / 市場機制 | [Trending / Ranging / Volatile] | [Analysis] |
| Key levels / 關鍵位 | [Support / Resistance levels] | [Price levels] |
| Correlation check / 相關性檢查 | [BTC-ETH correlation] | [Value] |
| Time of day / 時間 | [Session] | [Liquidity assessment] |
```

### 4.2 Signal Confirmation / 訊號確認

```markdown
### Signal Confirmation / 訊號確認

| Signal / 訊號 | Required / 必要 | Status / 狀態 |
|---------------|-----------------|---------------|
| Primary signal / 主要訊號 | ✅ Yes | [Confirmed / Pending] |
| Secondary confirmation / 次要確認 | ⚠️ Optional | [Confirmed / N/A] |
| Volume confirmation / 成交量確認 | ✅ Yes | [Confirmed / Pending] |
| Timeframe alignment / 時間框架一致性 | ✅ Yes | [Confirmed / Pending] |
```

---

## 5. Entry Checklist / 進場檢查清單

### 5.1 Pre-Entry Checks / 進場前檢查

```markdown
### Pre-Entry Checks / 進場前檢查

- [ ] Strategy signal is valid / 策略訊號有效
- [ ] Market conditions match strategy requirements / 市場條件符合策略要求
- [ ] No major news/events expected / 無重大新聞/事件預期
- [ ] Risk limit not exceeded / 未超過風險限制
- [ ] Position sizing calculated / 倉位規模已計算
- [ ] Stop loss level identified / 停損位已識別
- [ ] Take profit target(s) identified / 獲利目標已識別
```

### 5.2 Entry Execution / 進場執行

```markdown
### Entry Execution / 進場執行

| Parameter / 參數 | Value / 值 | Status / 狀態 |
|------------------|------------|---------------|
| Entry price / 進場價 | [Price] or [Order type] | [To be filled] |
| Order type / 訂單類型 | [Market / Limit] | [To be defined] |
| Position size / 倉位規模 | [Units / % of account] | [Calculated] |
| Risk amount / 風險金額 | [Currency / %] | [Calculated] |
| Maximum slippage / 最大滑點 | [% or absolute] | [To be defined] |
```

---

## 6. Position Sizing / 倉位規模

### 6.1 Sizing Calculation / 規模計算

```markdown
### Position Sizing Calculation / 倉位規模計算

| Input / 輸入 | Value / 值 | Formula / 公式 |
|--------------|------------|----------------|
| Account balance / 帳戶餘額 | [Amount] | Current balance |
| Risk per trade / 每筆交易風險 | [%] | From risk_control.md |
| Entry price / 進場價 | [Price] | Signal price |
| Stop loss price / 停損價 | [Price] | Calculated below |
| Risk per unit / 每單位風險 | [Amount] | Entry - Stop |
| Position size / 倉位規模 | [Units] | (Balance × Risk%) / Risk per unit |
```

### 6.2 Sizing Constraints / 規模限制

```markdown
### Sizing Constraints / 規模限制

| Constraint / 限制 | Value / 值 | Check / 檢查 |
|-------------------|------------|--------------|
| Max risk per trade / 每筆最大風險 | ≤ 2% of account | [ ] Pass |
| Max position size / 最大倉位 | ≤ 10% of account | [ ] Pass |
| Total portfolio heat / 總投資組合熱度 | ≤ 6% at risk | [ ] Pass |
| Single asset limit / 單一資產限制 | ≤ 50% allocation | [ ] Pass |
```

---

## 7. Stop Logic / 停損邏輯

### 7.1 Stop Loss Definition / 停損定義

```markdown
### Stop Loss Definition / 停損定義

| Stop Type / 停損類型 | Level / 位 | Logic / 邏輯 |
|----------------------|------------|--------------|
| Technical stop / 技術停損 | [Price] | Below support / Above resistance |
| Fixed % stop / 固定百分比 | [Price] | Entry × (1 - risk%) |
| Volatility stop / 波動率停損 | [Price] | ATR × multiplier |
| Time stop / 時間停損 | [Time] | Max hold period |
```

### 7.2 Stop Management / 停損管理

```markdown
### Stop Management / 停損管理

| Stage / 階段 | Trigger / 觸發 | Action / 行動 |
|--------------|----------------|---------------|
| Initial stop / 初始停損 | At entry / 進場時 | Set at [Level] |
| Breakeven move / 移至損益平衡 | +1% profit | Move stop to entry |
| Trailing activation / 追蹤啟動 | +3% profit | Activate trailing stop |
| Trailing step / 追蹤步驟 | +1% profit increments | Trail by [method] |
```

---

## 8. Exit Plan / 出場計畫

### 8.1 Take Profit Targets / 獲利目標

```markdown
### Take Profit Targets / 獲利目標

| Target / 目標 | Level / 位 | Size to Close / 平倉規模 | R:R Ratio / 風險報酬比 |
|---------------|------------|--------------------------|------------------------|
| TP1 / 目標 1 | [Price] | 30% of position | 1:1.5 |
| TP2 / 目標 2 | [Price] | 30% of position | 1:2 |
| TP3 / 目標 3 | [Price] | 40% of position | 1:3 |
| Final target / 最終目標 | [Price] or [Trailing] | Remaining / 剩餘 | Open / 開放 |
```

### 8.2 Exit Triggers / 出場觸發

```markdown
### Exit Triggers / 出場觸發

| Trigger / 觸發 | Condition / 條件 | Action / 行動 |
|----------------|------------------|---------------|
| Target hit / 觸及目標 | Price reaches TP level | Close portion at target |
| Stop hit / 觸及停損 | Price reaches stop | Close full position |
| Signal reversal / 訊號反轉 | Opposite signal appears | Consider early exit |
| Time limit / 時間限制 | Max hold time reached | Close regardless of P&L |
| Invalidation / 失效 | Setup invalidated | Close immediately |
```

---

## 9. Invalidation / Abort Conditions / 失效與取消條件

### 9.1 Pre-Entry Invalidation / 進場前失效

```markdown
### Pre-Entry Invalidation / 進場前失效

Cancel trade if / 取消交易如果：
- [ ] Signal disappears before entry / 進場前訊號消失
- [ ] Market conditions change abruptly / 市場條件突然改變
- [ ] Major news event occurs / 發生重大新聞事件
- [ ] Correlated asset moves against setup / 相關資產反向移動
- [ ] Risk limit would be exceeded / 將超過風險限制
```

### 9.2 Post-Entry Invalidation / 進場後失效

```markdown
### Post-Entry Invalidation / 進場後失效

Exit immediately if / 立即出場如果：
- [ ] Strategy logic fundamentally changes / 策略邏輯根本改變
- [ ] Stop loss level invalidated by price action / 價格行為使停損位失效
- [ ] Technical setup breaks down / 技術設定崩解
- [ ] Time-based invalidation triggered / 時間型失效觸發
```

---

## 10. Monitoring Rules / 監控規則

### 10.1 Active Monitoring / 主動監控

```markdown
### Active Monitoring / 主動監控

| Check / 檢查 | Frequency / 頻率 | Action if Triggered / 觸發時行動 |
|--------------|------------------|----------------------------------|
| Price vs stop / 價格對停損 | Real-time / 即時 | Close if breached / 突破則平倉 |
| Price vs target / 價格對目標 | Real-time / 即時 | Take profit as planned / 按計畫獲利了結 |
| Volume confirmation / 成交量確認 | Each candle / 每根 K 線 | Review if abnormal / 異常則檢討 |
| Market regime / 市場機制 | Hourly / 每小時 | Adjust if changed / 改變則調整 |
```

### 10.2 Review Schedule / 檢討時程

```markdown
### Review Schedule / 檢討時程

| Review / 檢討 | Timing / 時機 | Content / 內容 |
|---------------|---------------|----------------|
| Initial review / 初始檢討 | 1 hour after entry | Confirm setup valid / 確認設定有效 |
| Progress review / 進度檢討 | Every 4 hours | Assess progress toward target |
| Pre-close review / 收盤前檢討 | 30 min before close | Decide overnight hold |
| Post-trade review / 交易後檢討 | Immediately after exit | Document results |
```

---

## 11. Relationship to Strategy Card / 與策略卡的關係

### 11.1 From Strategy to Plan / 從策略到計畫

```
Strategy Card / 策略卡
    ├── Strategy logic / 策略邏輯
    ├── Entry rules / 進場規則
    ├── Exit rules / 出場規則
    └── Risk parameters / 風險參數
            ↓
Trade Plan / 交易計畫
    ├── Specific setup / 特定設定
    ├── Calculated position size / 計算倉位規模
    ├── Exact entry/exit levels / 精確進出場位
    └── Real-time monitoring / 即時監控
```

### 11.2 Information Flow / 資訊流

| Source / 來源 | Information / 資訊 | Use in Plan / 計畫中使用 |
|---------------|-------------------|--------------------------|
| Strategy Card | Entry conditions | Setup identification |
| Strategy Card | Risk parameters | Position sizing calculation |
| Strategy Card | Exit conditions | Stop/target placement |
| Market Data | Current prices | Exact entry/exit levels |
| Account State | Available capital | Position size limits |

---

## 12. Relationship to Criteria and Risk Control / 與 criteria 和 risk control 的關係

### 12.1 Criteria Alignment / 準則一致性

| Criteria / 準則 | Application in Trade Plan / 交易計畫中的應用 |
|-----------------|----------------------------------------------|
| Clear hypothesis / 清晰假設 | Setup conditions define trade rationale |
| Defined entry/exit / 定義進出場 | Entry checklist and exit plan |
| Risk management / 風險管理 | Position sizing and stop logic |
| Backtest capability / 回測能力 | Plan can be backtested as part of strategy |

### 12.2 Risk Control Compliance / 風險控制符合性

| Risk Control / 風險控制 | Trade Plan Implementation / 交易計畫實施 |
|-------------------------|------------------------------------------|
| Capital allocation / 資本配置 | Position sizing respects limits |
| Risk at stop / 停損風險 | Calculated and limited per trade |
| Exposure / 曝險 | Monitored in real-time |
| Stop/Pause conditions / 停止/暫停條件 | Invalidation rules defined |

---

## 13. Bilingual Formatting Rules / 中英對照格式規則

### 13.1 Headers / 標題

```markdown
## Section Name / 章節名稱
```

### 13.2 Tables / 表格

```markdown
| Field / 欄位 | Value / 值 | Status / 狀態 |
```

### 13.3 Checklists / 檢查清單

```markdown
- [ ] Item description / 項目說明
```

---

## 14. Example Trade Plan / 範例交易計畫

**Status**: EXAMPLE ONLY / 僅為範例

### Example: PLAN_C1_BTC_4H_DualRegime_20260405_01 (Example Only)

```markdown
# Trade Plan: PLAN_C1_BTC_4H_DualRegime_20260405_01

**Status**: EXAMPLE ONLY - Not a real trade / 僅為範例 - 非真實交易

## Setup Information / 設定資訊

| Field / 欄位 | Value / 值 |
|--------------|------------|
| Plan ID / 計畫識別碼 | PLAN_C1_BTC_4H_DualRegime_20260405_01 |
| Related Strategy / 關聯策略 | C1_BTC_4H_DualRegime |
| Asset / 資產 | BTCUSDT |
| Timeframe / 時間框架 | 4H |
| Plan Date / 計畫日期 | 2026-04-05 |
| Status / 狀態 | Active / 進行中 |

## Market Context / 市場背景 (Example / 範例)

| Factor / 因素 | Status / 狀態 | Notes / 備註 |
|---------------|---------------|--------------|
| Trend / 趨勢 | Bullish / 多頭 | Price above 200 MA |
| Regime / 機制 | Mild trend / 溫和趨勢 | Low volatility |
| Key level / 關鍵位 | Support at 68,000 | Previous resistance |

## Entry Checklist / 進場檢查清單

- [x] Signal valid / 訊號有效
- [x] Market conditions match / 市場條件符合
- [ ] Risk limit check / 風險限制檢查
- [ ] Position sizing / 倉位規模計算

## Position Sizing / 倉位規模 (Example / 範例)

| Input / 輸入 | Value / 值 |
|--------------|------------|
| Account balance / 帳戶餘額 | $100,000 |
| Risk per trade / 每筆交易風險 | 1.5% |
| Entry price / 進場價 | $69,500 |
| Stop price / 停損價 | $67,900 |
| Risk per BTC / 每 BTC 風險 | $1,600 |
| Position size / 倉位規模 | 0.9375 BTC |
| Position value / 倉位價值 | $65,156 |
| Risk amount / 風險金額 | $1,500 (1.5%) |

## Stop Logic / 停損邏輯

| Type / 類型 | Level / 位 |
|-------------|------------|
| Initial stop / 初始停損 | $67,900 (-2.3%) |
| Breakeven / 損益平衡 | $69,500 (at entry) |
| Trailing activation / 追蹤啟動 | $71,650 (+3.1%) |

## Exit Plan / 出場計畫

| Target / 目標 | Price / 價格 | Size / 規模 | R:R |
|---------------|--------------|-------------|-----|
| TP1 | $71,500 | 30% | 1:1.2 |
| TP2 | $73,000 | 30% | 1:2.1 |
| TP3 | $75,000 | 40% | 1:3.4 |

## Monitoring / 監控

- Check every 4H candle close / 每 4H K 線收盤檢查
- Move to breakeven at +1% / +1% 時移至損益平衡
- Activate trailing at +3% / +3% 時啟動追蹤停損

**EXAMPLE ONLY** - This is a template example.

**僅為範例** - 這是模板範例。
```

---

## 15. Naming Convention / 命名規則

### 15.1 Trade Plan File Naming / 交易計畫檔案命名

```
plans/<asset>_<timeframe>_<strategy_name>_trade_plan.md

Examples / 範例:
- plans/BTC_4H_dual_regime_trade_plan.md
- plans/ETH_4H_bb_mr_trade_plan.md
- plans/BTC_1H_breakout_trade_plan.md
```

### 15.2 Plan ID Naming / 計畫 ID 命名

```
PLAN_[STRATEGY_ID]_[YYYYMMDD]_[SEQUENCE]

Examples / 範例:
- PLAN_C1_BTC_4H_DualRegime_20260405_01
- PLAN_A1_ETH_4H_BB_MR_20260405_02
- PLAN_B2_BTC_1H_Breakout_20260406_01
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

- `research/strategy_card_template.md` - Strategy documentation template / 策略文件模板
- `strategies/BTC_4H_filter_card.md` - Example strategy card / 範例策略卡
- `research/criteria.md` - Research selection criteria / 研究選題準則
- `research/risk_control.md` - Risk management principles / 風險管理原則
