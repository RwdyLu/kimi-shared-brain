# Strategy Card: BTC 4H Filter

**Status**: Work in Progress / 進行中  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Strategy Identity / 策略識別

| Field / 欄位 | Value / 值 | Status / 狀態 |
|--------------|------------|---------------|
| Strategy ID / 策略識別碼 | F1_BTC_4H_Filter | ✅ Confirmed / 已確認 |
| Full Name / 全名 | BTC 4H Strategy Filter / BTC 4H 策略篩選 | ✅ Confirmed |
| Category / 類別 | Filter / Research Framework / 篩選器 / 研究框架 | ✅ Confirmed |
| Version / 版本 | 0.1.0 (Draft) | ⚠️ Provisional / 暫定 |

---

## 2. Current Status / 目前狀態

| Status / 狀態 | Description / 說明 |
|---------------|-------------------|
| **Active Research** / 進行中研究 | Strategy filtering and selection in progress / 策略篩選與選擇進行中 |

**Status Explanation / 狀態說明**:

This is a **filtering framework** rather than a single trading strategy. It defines the criteria and process for evaluating and selecting BTC 4H strategies.

這是一個**篩選框架**而非單一交易策略。它定義評估和選擇 BTC 4H 策略的準則和流程。

---

## 3. Asset and Timeframe / 資產與時間框架

| Parameter / 參數 | Value / 值 | Status / 狀態 |
|------------------|------------|---------------|
| Primary Asset / 主要資產 | BTCUSDT | ✅ Confirmed |
| Timeframe / 時間框架 | 4H | ✅ Confirmed |
| Secondary Asset / 次要資產 | ETHUSDT (for correlation) | ⚠️ Provisional |
| Market Type / 市場類型 | Spot / Perpetual | ⚠️ To be defined |

---

## 4. Strategy Type / 策略類型

| Attribute / 屬性 | Value / 值 | Status / 狀態 |
|------------------|------------|---------------|
| Primary Type / 主要類型 | Filter Framework / 篩選框架 | ✅ Confirmed |
| Target Strategies / 目標策略 | MR, Breakout, Breakout Failure | ⚠️ Provisional |
| Research Phase / 研究階段 | Phase 1: Criteria Definition | ✅ Confirmed |

---

## 5. Strategy Hypothesis / 策略假設

### 5.1 Core Hypothesis / 核心假設

**English**: Systematic filtering of BTC 4H strategies based on robust criteria can identify edges with positive risk-adjusted returns.

**中文**: 基於穩健準則對 BTC 4H 策略進行系統化篩選，可以識別具有正風險調整報酬的優勢。

### 5.2 Key Assumptions / 關鍵假設

| Assumption / 假設 | Rationale / 理由 | Status / 狀態 |
|-------------------|------------------|---------------|
| 4H timeframe captures meaningful price movements / 4H 時間框架捕捉有意義的價格變動 | Balances signal quality and frequency | ⚠️ To be validated |
| Elimination criteria prevent overfitting / 淘汰準則防止過度最佳化 | Negative returns after costs indicate failure | ✅ Per criteria.md |
| Mean reversion exists in crypto / 加密貨幣存在均值回歸 | Historical observation | ⚠️ To be tested |

---

## 6. Current Known Logic / 目前已知邏輯

### 6.1 Filter Process / 篩選流程

```
Strategy Idea / 策略想法
    ↓
Criteria Check / 準則檢查 (criteria.md)
    ↓
Backtest Design / 回測設計
    ↓
Result Evaluation / 結果評估
    ↓
Decision: Proceed / Pause / Eliminate
    ↓
Strategy Card / Trade Plan
```

### 6.2 Evaluation Dimensions / 評估維度

| Dimension / 維度 | Reference / 參考 | Status / 狀態 |
|------------------|------------------|---------------|
| Return after costs / 含成本後報酬 | criteria.md Sec 4.1 | ✅ Defined |
| Median return / 中位數報酬 | criteria.md Sec 4.1 | ✅ Defined |
| Max drawdown / 最大回撤 | criteria.md Sec 4.2 | ✅ Defined |
| Sharpe ratio / 夏普比率 | criteria.md Sec 4.2 | ✅ Defined |
| Overfitting check / 過度最佳化檢查 | criteria.md Sec 7 | ✅ Defined |

---

## 7. Entry Conditions / 進場條件

**Status**: NOT APPLICABLE / 不適用

This is a **filter framework**, not a trading strategy with specific entry rules.

這是**篩選框架**，非具有特定進場規則的交易策略。

Individual strategies selected through this filter will define their own entry conditions.

通過此篩選器選出的個別策略將定義自己的進場條件。

---

## 8. Exit Conditions / 出場條件

**Status**: NOT APPLICABLE / 不適用

This is a **filter framework**, not a trading strategy with specific exit rules.

這是**篩選框架**，非具有特定出場規則的交易策略。

Individual strategies selected through this filter will define their own exit conditions.

通過此篩選器選出的個別策略將定義自己的出場條件。

---

## 9. Invalidation Conditions / 失效條件

### 9.1 Filter Elimination Triggers / 篩選器淘汰觸發

| Trigger / 觸發條件 | Description / 說明 | Reference / 參考 |
|--------------------|-------------------|------------------|
| Framework ineffective / 框架無效 | No strategies pass filter after 20+ attempts | ⚠️ To be defined |
| Criteria too strict / 準則過嚴 | Zero strategies qualify | ⚠️ To be defined |
| Market regime change / 市場機制改變 | BTC behavior fundamentally changes | ⚠️ To be defined |

---

## 10. Risk Notes / 風險備註

### 10.1 Research Phase Risks / 研究階段風險

| Risk / 風險 | Mitigation / 緩解 | Status / 狀態 |
|-------------|-------------------|---------------|
| Overfitting in candidate strategies / 候選策略過度最佳化 | Strict elimination criteria | ✅ Per criteria.md |
| Insufficient sample size / 樣本不足 | Minimum 100 trades requirement | ✅ Per criteria.md |
| Curve fitting / 曲線配適 | OOS validation required | ✅ Per criteria.md |

### 10.2 Risk Control Alignment / 風險控制一致性

| Risk Dimension / 風險維度 | Status / 狀態 |
|---------------------------|---------------|
| Capital allocation / 資本配置 | ⚠️ To be defined per selected strategy |
| Risk at stop / 停損風險 | ⚠️ To be defined per selected strategy |
| Exposure / 曝險 | ⚠️ To be defined per selected strategy |

---

## 11. Performance Status / 績效狀態

### 11.1 Current Status / 目前狀態

**Status**: NO PERFORMANCE DATA / 無績效數據

This is a **filter framework**, not a trading strategy. Performance metrics apply to individual strategies selected through this filter.

這是**篩選框架**，非交易策略。績效指標適用於通過此篩選器選出的個別策略。

### 11.2 Framework Effectiveness Metrics / 框架有效性指標

| Metric / 指標 | Target / 目標 | Current / 當前 | Status / 狀態 |
|---------------|---------------|----------------|---------------|
| Strategies tested / 測試策略數 | N/A | To be tracked | 📝 To be defined |
| Strategies passed / 通過策略數 | N/A | To be tracked | 📝 To be defined |
| Strategies eliminated / 淘汰策略數 | N/A | To be tracked | 📝 To be defined |
| Pass rate / 通過率 | N/A | To be calculated | 📝 To be defined |

---

## 12. Monitoring / Review Notes / 監控與審查備註

### 12.1 Monitoring Schedule / 監控時程

| Activity / 活動 | Frequency / 頻率 | Next Review / 下次審查 | Status / 狀態 |
|-----------------|------------------|------------------------|---------------|
| Filter criteria review / 篩選準則審查 | Monthly / 每月 | 2026-05-05 | 📝 Scheduled |
| Selected strategy review / 選出策略審查 | Per strategy | As needed | 📝 To be scheduled |
| Framework effectiveness review / 框架有效性審查 | Quarterly / 每季 | 2026-07-05 | 📝 Scheduled |

### 12.2 Current Active Filters / 當前啟用篩選器

| Filter / 篩選器 | Criteria / 準則 | Status / 狀態 |
|-----------------|-----------------|---------------|
| Hard elimination / 硬性淘汰 | Return after costs < 0 | ✅ Active |
| Hard elimination / 硬性淘汰 | Median return < 0 | ✅ Active |
| Warning / 警告 | Max drawdown > 30% | ✅ Active |
| Warning / 警告 | Sharpe < 0.5 | ✅ Active |
| Overfitting prevention / 過度最佳化預防 | Parameters ≤ 5 | ✅ Active |

---

## 13. Open Questions / 待解問題

### 13.1 Critical Questions / 關鍵問題

| Question / 問題 | Priority / 優先級 | Status / 狀態 |
|-----------------|-------------------|---------------|
| What specific strategy types to prioritize? / 優先哪些策略類型？ | High / 高 | ⚠️ Open |
| Should we include breakout strategies? / 是否包含突破策略？ | Medium / 中 | ⚠️ Open |
| How to handle ETH correlation? / 如何處理 ETH 相關性？ | Medium / 中 | ⚠️ Open |
| What is the target number of strategies to maintain? / 目標維持多少策略？ | Low / 低 | ⚠️ Open |

### 13.2 Research Gaps / 研究缺口

| Gap / 缺口 | Impact / 影響 | Priority / 優先級 |
|------------|---------------|-------------------|
| No specific candidate strategies identified / 未識別具體候選策略 | Cannot execute filter | High |
| No backtest infrastructure defined / 未定義回測基礎設施 | Cannot validate | High |
| No historical strategy database / 無歷史策略資料庫 | Cannot track effectiveness | Medium |

---

## 14. Relationship to Criteria and Risk Control / 與 criteria 和 risk control 的關係

### 14.1 Criteria Compliance / 準則符合性

| Criteria / 準則 | Reference / 參考 | Compliance / 符合性 | Notes / 備註 |
|-----------------|------------------|---------------------|--------------|
| Selection criteria / 選擇準則 | criteria.md Sec 3 | ✅ Compliant | Framework defines selection process |
| Elimination criteria / 淘汰準則 | criteria.md Sec 4 | ✅ Compliant | Hard triggers defined |
| Monitor/Pause/Eliminate layers / 監控/暫停/淘汰分層 | criteria.md Sec 5 | ✅ Compliant | Framework supports this |
| Evidence quality / 證據品質 | criteria.md Sec 6 | ✅ Compliant | Requirements defined |
| Overfitting prevention / 過度最佳化預防 | criteria.md Sec 7 | ✅ Compliant | Parameter limits defined |

### 14.2 Risk Control Alignment / 風險控制一致性

| Risk Control / 風險控制 | Reference / 參考 | Alignment / 一致性 | Notes / 備註 |
|------------------------|------------------|--------------------|--------------|
| Risk dimensions / 風險維度 | risk_control.md Sec 2 | ⚠️ Partial | Per-strategy application |
| Draft guidelines / 草稿指引 | risk_control.md Sec 2.3 | ⚠️ To be applied | 1-2% per trade, 6% heat |
| Stop/Pause/Resume framework / 框架 | risk_control.md Sec 4 | ✅ Aligned | Status layers consistent |
| Research vs Live boundary / 研究與實盤邊界 | risk_control.md Sec 6 | ✅ Aligned | Research phase only |
| No over-optimization / 不過度最佳化 | risk_control.md Sec 7 | ✅ Aligned | ≤ 5 parameters |

---

## Summary / 摘要

| Aspect / 方面 | Status / 狀態 |
|---------------|---------------|
| Framework definition / 框架定義 | ✅ Active |
| Selection criteria / 選擇準則 | ✅ Defined |
| Candidate strategies / 候選策略 | ❌ Not yet identified |
| Backtest data / 回測資料 | ❌ Not yet generated |
| Strategy cards / 策略卡 | ❌ Not yet created |

**Next Steps / 下一步**:
1. Identify specific candidate strategies / 識別具體候選策略
2. Apply filter criteria / 應用篩選準則
3. Generate strategy cards for passed strategies / 為通過策略產生策略卡

---

**Created by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Based on**: strategy_card_template.md (SCT-001)  
**References**: criteria.md, risk_control.md, BTC_ETH_strategy_framework.md  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `research/criteria.md` - Research selection and elimination / 研究選題與淘汰
- `research/risk_control.md` - Risk management principles / 風險管理原則
- `research/BTC_ETH_strategy_framework.md` - Strategy framework / 策略框架
- `research/strategy_card_template.md` - Template reference / 模板參考
