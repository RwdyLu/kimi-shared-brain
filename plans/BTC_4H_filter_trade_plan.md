# Trade Plan: BTC 4H Filter

**Status**: Work in Progress / 進行中  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Plan Identity / 計畫識別

| Field / 欄位 | Value / 值 | Status / 狀態 |
|--------------|------------|---------------|
| Plan ID / 計畫識別碼 | PLAN_F1_BTC_4H_Filter_20260405_01 | ✅ Confirmed |
| Related Strategy / 關聯策略 | F1_BTC_4H_Filter | ✅ Confirmed |
| Asset / 資產 | BTCUSDT | ✅ Confirmed |
| Timeframe / 時間框架 | 4H | ✅ Confirmed |
| Plan Date / 計畫日期 | 2026-04-05 | ✅ Confirmed |
| Status / 狀態 | Active Research / 進行中研究 | ⚠️ Provisional |

---

## 2. Current Status / 目前狀態

| Status / 狀態 | Description / 說明 |
|---------------|-------------------|
| **Framework Development** / 框架開發 | Establishing filter criteria and selection process / 建立篩選準則與選擇流程 |

**Status Explanation / 狀態說明**:

This is a **filter framework trade plan** rather than a specific trade execution plan. The goal is to establish systematic criteria for evaluating and selecting BTC 4H strategies.

這是**篩選框架交易計畫**而非特定交易執行計畫。目標是建立系統化準則以評估和選擇 BTC 4H 策略。

---

## 3. Related Strategy Card / 對應策略卡

| Reference / 參考 | File / 檔案 | Status / 狀態 |
|------------------|-------------|---------------|
| Strategy Card / 策略卡 | `strategies/BTC_4H_filter_card.md` | ✅ Confirmed |
| Strategy ID / 策略識別碼 | F1_BTC_4H_Filter | ✅ Confirmed |
| Strategy Type / 策略類型 | Filter Framework / 篩選框架 | ✅ Confirmed |

**Note / 備註**: This trade plan is derived from the BTC 4H Filter Strategy Card and applies its framework principles to the selection process.

---

## 4. Asset and Timeframe / 資產與時間框架

| Parameter / 參數 | Value / 值 | Status / 狀態 |
|------------------|------------|---------------|
| Primary Asset / 主要資產 | BTCUSDT | ✅ Confirmed |
| Timeframe / 時間框架 | 4H | ✅ Confirmed |
| Secondary Asset / 次要資產 | ETHUSDT (correlation check) | ⚠️ Provisional |
| Analysis Window / 分析窗口 | 4H candles / 4H K 線 | ✅ Confirmed |
| Review Frequency / 檢討頻率 | Daily / 每日 | ⚠️ Provisional |

---

## 5. Setup Conditions / 設定條件

### 5.1 Market Context for Filter Application / 篩選應用的市場背景

| Factor / 因素 | Status / 狀態 | Notes / 備註 |
|---------------|---------------|--------------|
| Market regime identification / 市場機制識別 | ⚠️ To be defined | Trending, ranging, or volatile? |
| Key support/resistance / 關鍵支撐阻力 | ⚠️ To be defined | For candidate strategy evaluation |
| Volume profile / 成交量輪廓 | ⚠️ To be defined | Liquidity assessment |
| Correlation check / 相關性檢查 | ⚠️ To be defined | BTC-ETH correlation |
| Time of day / 時間 | ⚠️ To be defined | Session liquidity |

### 5.2 Candidate Strategy Signal Confirmation / 候選策略訊號確認

**Status**: NOT APPLICABLE / 不適用

This is a **filter framework**. Specific signal confirmation applies to individual strategies selected through this filter.

這是**篩選框架**。具體訊號確認適用於通過此篩選器選出的個別策略。

---

## 6. Entry Checklist / 進場檢查清單

### 6.1 Filter Application Checklist / 篩選應用檢查清單

- [ ] New strategy idea identified / 識別新策略想法
- [ ] Strategy type categorized (MR/Breakout/etc.) / 策略類型分類
- [ ] Criteria checklist reviewed / 檢閱準則檢查清單
- [ ] Risk parameters assessed / 評估風險參數
- [ ] Backtest design prepared / 準備回測設計
- [ ] Elimination criteria applied / 應用淘汰準則

### 6.2 Specific Trade Entry / 具體交易進場

**Status**: NOT APPLICABLE / 不適用

This filter framework does not define specific trade entries. Individual strategies will have their own entry criteria.

此篩選框架不定義具體交易進場。個別策略將有自己的進場準則。

---

## 7. Position Sizing Notes / 倉位規模備註

### 7.1 Filter-Level Position Sizing / 篩選層級倉位規模

**Status**: TO BE DEFINED / 待定義

| Parameter / 參數 | Draft Value / 草稿值 | Status / 狀態 |
|------------------|---------------------|---------------|
| Max strategies tracked / 最大追蹤策略數 | 5-10 | ⚠️ Provisional |
| Capital per strategy / 每策略資金 | 10-20% of account | ⚠️ Provisional |
| Risk per trade (strategy level) / 每筆交易風險 | ≤ 2% | ⚠️ Draft per risk_control.md |
| Total portfolio heat / 總投資組合熱度 | ≤ 6% | ⚠️ Draft per risk_control.md |

### 7.2 Sizing Constraints / 規模限制

| Constraint / 限制 | Value / 值 | Status / 狀態 |
|-------------------|------------|---------------|
| Max risk per strategy / 每策略最大風險 | ≤ 2% | ⚠️ Draft |
| Max position per trade / 每筆最大倉位 | ≤ 10% | ⚠️ Draft |
| Single asset concentration / 單一資產集中 | ≤ 50% | ⚠️ Draft |

---

## 8. Stop Logic / 停損邏輯

### 8.1 Filter-Level Stops / 篩選層級停損

| Stop Type / 停損類型 | Trigger / 觸發 | Action / 行動 | Status / 狀態 |
|----------------------|----------------|---------------|---------------|
| Strategy elimination / 策略淘汰 | Return < 0 after costs | Remove from tracking | ✅ Per criteria.md |
| Strategy pause / 策略暫停 | Max DD > 30% | Stop trading, review | ✅ Per criteria.md |
| Framework review / 框架檢討 | 0 strategies pass in 20+ attempts | Review filter criteria | ⚠️ To be defined |

### 8.2 Specific Trade Stops / 具體交易停損

**Status**: NOT APPLICABLE / 不適用

Individual strategies will define their own stop loss logic.

個別策略將定義自己的停損邏輯。

---

## 9. Exit Plan / 出場計畫

### 9.1 Filter-Level Exits / 篩選層級出場

| Exit Type / 出場類型 | Condition / 條件 | Action / 行動 |
|----------------------|------------------|---------------|
| Strategy graduation / 策略畢業 | Passes all criteria | Move to active monitoring |
| Strategy elimination / 策略淘汰 | Fails hard criteria | Archive and stop tracking |
| Strategy pause / 策略暫停 | Triggers soft criteria | Suspend, review parameters |
| Framework pivot / 框架轉向 | Filter ineffective | Redesign criteria |

### 9.2 Specific Trade Exits / 具體交易出場

**Status**: NOT APPLICABLE / 不適用

Individual strategies will define their own exit targets and logic.

個別策略將定義自己的出場目標和邏輯。

---

## 10. Invalidation / Abort Conditions / 失效與取消條件

### 10.1 Pre-Filter Application / 篩選應用前

Cancel filter application if / 取消篩選應用如果：
- [ ] Strategy idea lacks clear hypothesis / 策略想法缺乏清晰假設
- [ ] Required data unavailable / 所需資料不可用
- [ ] Similar strategy already in tracking / 類似策略已在追蹤中
- [ ] Market conditions unsuitable for strategy type / 市場條件不適合策略類型

### 10.2 Post-Filter Selection / 篩選選擇後

Stop tracking strategy if / 停止追蹤策略如果：
- [ ] Hard elimination criteria triggered / 觸發硬性淘汰準則
- [ ] Strategy logic fundamentally changes / 策略邏輯根本改變
- [ ] Market regime shifts permanently / 市場機制永久轉變
- [ ] Better alternative identified / 識別到更好替代方案

---

## 11. Monitoring Rules / 監控規則

### 11.1 Active Monitoring / 主動監控

| Check / 檢查 | Frequency / 頻率 | Action / 行動 |
|--------------|------------------|---------------|
| New strategy candidates / 新策略候選人 | Daily / 每日 | Review and categorize |
| Tracked strategies performance / 追蹤策略績效 | Daily / 每日 | Update metrics |
| Criteria threshold breaches / 準則門檻突破 | Real-time / 即時 | Flag for review |
| Filter effectiveness / 篩選器有效性 | Weekly / 每週 | Calculate pass rates |

### 11.2 Review Schedule / 檢討時程

| Review / 檢討 | Timing / 時機 | Content / 內容 |
|---------------|---------------|----------------|
| Daily digest / 每日摘要 | End of day | New candidates, status updates |
| Weekly review / 每週檢討 | Sunday | Filter effectiveness, pass rates |
| Monthly audit / 每月審計 | Month end | Criteria relevance, framework health |
| Quarterly assessment / 每季評估 | Quarter end | Major framework revisions |

---

## 12. Execution Notes / 執行備註

### 12.1 Current Execution Focus / 當前執行重點

| Priority / 優先級 | Task / 任務 | Status / 狀態 |
|-------------------|-------------|---------------|
| High / 高 | Define specific candidate strategies / 定義具體候選策略 | 📝 Not started |
| High / 高 | Establish backtest infrastructure / 建立回測基礎設施 | 📝 Not started |
| Medium / 中 | Create strategy database / 建立策略資料庫 | 📝 Not started |
| Medium / 中 | Design monitoring dashboard / 設計監控儀表板 | 📝 Not started |
| Low / 低 | Automate filter application / 自動化篩選應用 | 📝 Not started |

### 12.2 Execution Constraints / 執行限制

- **Research phase only / 僅研究階段**: No live trading / 無實盤交易
- **Manual process / 手動流程**: Current filter application is manual
- **Limited candidates / 有限候選**: No specific strategies identified yet

---

## 13. Open Questions / 待解問題

### 13.1 Critical Questions / 關鍵問題

| Question / 問題 | Impact / 影響 | Priority / 優先級 | Status / 狀態 |
|-----------------|---------------|-------------------|---------------|
| What specific strategy types to prioritize? / 優先哪些策略類型？ | Filter design | High / 高 | ⚠️ Open |
| How many concurrent strategies to track? / 同時追蹤多少策略？ | Resource allocation | High / 高 | ⚠️ Open |
| Should breakout strategies be included? / 是否包含突破策略？ | Scope definition | Medium / 中 | ⚠️ Open |
| How to handle ETH correlation in filtering? / 篩選中如何處理 ETH 相關性？ | Risk management | Medium / 中 | ⚠️ Open |

### 13.2 Data Requirements / 資料需求

| Requirement / 需求 | Purpose / 用途 | Status / 狀態 |
|--------------------|----------------|---------------|
| Historical strategy database / 歷史策略資料庫 | Track effectiveness | ❌ Not available |
| Real-time performance feeds / 即時績效資料流 | Active monitoring | ❌ Not available |
| Correlation matrix / 相關性矩陣 | Risk assessment | ⚠️ To be built |
| Backtest engine / 回測引擎 | Validation | ⚠️ To be defined |

---

## 14. Relationship to Criteria and Risk Control / 與 criteria 和 risk control 的關係

### 14.1 Criteria Compliance / 準則符合性

| Criteria / 準則 | Application in Trade Plan / 交易計畫中的應用 | Status / 狀態 |
|-----------------|----------------------------------------------|---------------|
| Clear hypothesis / 清晰假設 | Framework assumes systematic filtering works | ⚠️ To be validated |
| Defined entry/exit / 定義進出場 | N/A for filter (applies to selected strategies) | ✅ N/A |
| Risk management / 風險管理 | Filter-level risk controls defined | ⚠️ Partial |
| Backtest capability / 回測能力 | Each candidate requires backtesting | 📝 To be implemented |

### 14.2 Risk Control Alignment / 風險控制一致性

| Risk Control / 風險控制 | Trade Plan Implementation / 交易計畫實施 | Status / 狀態 |
|-------------------------|------------------------------------------|---------------|
| Capital allocation / 資本配置 | Draft: 10-20% per strategy | ⚠️ Draft |
| Risk at stop / 停損風險 | Draft: ≤ 2% per trade | ⚠️ Draft |
| Exposure / 曝險 | Draft: ≤ 6% total heat | ⚠️ Draft |
| Stop/Pause framework / 停止/暫停框架 | Mapped to filter elimination criteria | ✅ Aligned |

---

## Summary / 摘要

| Aspect / 方面 | Status / 狀態 |
|---------------|---------------|
| Filter framework / 篩選框架 | ✅ Active |
| Selection criteria / 選擇準則 | ✅ Defined |
| Candidate strategies / 候選策略 | ❌ Not yet identified |
| Backtest infrastructure / 回測基礎設施 | ❌ Not yet built |
| Monitoring system / 監控系統 | ⚠️ To be defined |

**Next Steps / 下一步**:
1. Identify first specific candidate strategy / 識別第一個具體候選策略
2. Apply filter criteria / 應用篩選準則
3. Design backtest for passed strategy / 為通過策略設計回測
4. Create strategy-specific trade plan / 建立策略專屬交易計畫

---

**Created by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Based on**: trade_plan_template.md (TPT-001)  
**References**: BTC_4H_filter_card.md, criteria.md, risk_control.md  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `strategies/BTC_4H_filter_card.md` - Filter strategy card / 篩選策略卡
- `research/trade_plan_template.md` - Template reference / 模板參考
- `research/criteria.md` - Selection and elimination criteria / 選擇與淘汰準則
- `research/risk_control.md` - Risk management principles / 風險管理原則
