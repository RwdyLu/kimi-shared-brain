# BTC / ETH Strategy Framework
# BTC / ETH 策略框架

**Version**: 1.1.0  
**版本**: 1.1.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define the research framework, strategy types, output formats, and workflow for BTC and ETH quantitative trading research. This document serves as the master guide for all BTC/ETH strategy development activities.

定義 BTC 與 ETH 量化交易研究的研究框架、策略類型、輸出格式與工作流程。本文件作為所有 BTC/ETH 策略開發活動的主要指南。

---

## 2. Scope / 範圍

### 2.1 In Scope / 範圍內

- **BTCUSDT** strategy research / 策略研究
- **ETHUSDT** strategy research / 策略研究
- Related technical analysis methods / 相關技術分析方法
- Risk management for crypto assets / 加密資產風險管理

### 2.2 Out of Scope / 範圍外

- Traditional equity strategies / 傳統股票策略
- Altcoin research (beyond ETH) / 山寨幣研究
- DeFi / NFT / 基本面分析

---

## 3. Framework vs Status / 框架與狀態

### 3.1 Framework Layer (This Document) / 框架層（本文件）

**Purpose**: Define **how** research is conducted / 定義**如何**進行研究

- Workflow stages / 工作流程階段
- Output formats / 輸出格式
- Strategy categories / 策略類別
- High-level principles / 高層原則

### 3.2 Status Layer (Tracked in state/tasks.json) / 狀態層（記錄於 state/tasks.json）

**Purpose**: Track **current** project status / 追蹤**當前**專案狀態

| Project / 專案 | Current Status / 當前狀態 | Last Updated / 最後更新 |
|----------------|---------------------------|------------------------|
| BTC 4H Strategy Filter | Active research | 2026-04-05 |
| BTC 1D MR Strategy Monitor | Maintenance | 2026-04-05 |
| ETH 4H Strategy Research | Planned / 計畫中 | 2026-04-05 |

**Note**: Status changes are tracked in `state/tasks.json`, not this document.

**注意**: 狀態變更記錄於 `state/tasks.json`，非本文件。

---

## 4. Core Research Objectives / 核心研究目標

### 4.1 High-Level Principles / 高層原則

| Principle / 原則 | Description / 說明 |
|------------------|-------------------|
| Identify robust edges / 識別穩健優勢 | Find repeatable patterns / 找到可重複的模式 |
| Minimize drawdowns / 最小化回撤 | Control risk in volatile markets / 在波動市場控制風險 |
| Maintain simplicity / 保持簡單 | Avoid over-complex strategies / 避免過度複雜策略 |
| Ensure reusability / 確保可重用 | Work across market regimes / 跨市場機制有效 |

### 4.2 Specific Thresholds / 具體閾值

**Reference**: See `research/criteria.md` for:

- Elimination thresholds / 淘汰閾值
- Statistical requirements / 統計要求
- Overfitting constraints / 過度最佳化限制

**Do not duplicate** specific numbers in this framework document.

**不要**在本框架文件中重複具體數字。

---

## 5. Strategy Categories / 策略分類

### 5.1 Breakout / 突破

- Entry: Price closes above resistance / 收盤突破阻力位
- Exit: Target reached or false breakout / 達到目標或假突破
- Market: Trending / 趨勢市

### 5.2 Breakout Failure / 突破失敗

- Entry: Breakout reverses within N bars / N 根 K 線內突破反轉
- Exit: Return to breakout level / 回到突破位
- Market: Ranging / 震盪市

### 5.3 Mean Reversion (MR) / 均值回歸

- Entry: Price reaches statistical extreme / 價格達到統計極端
- Exit: Return to mean / 回歸均值
- Market: Ranging, mild trend / 震盪、溫和趨勢

### 5.4 Monitoring / 監控

Systematic tracking of strategy performance / 系統化追蹤策略績效

---

## 6. Current Preferred Timeframes / 當前偏好時間框架

### 6.1 Timeframe Preferences / 時間框架偏好

| Timeframe / 時間框架 | Priority / 優先級 | Rationale / 理由 |
|---------------------|-------------------|------------------|
| **4H** | Primary / 主要 | Balance of signal quality and frequency / 訊號品質與頻率平衡 |
| **1D** | Secondary / 次要 | Lower maintenance, position trading / 較低維護，部位交易 |
| 1H | Experimental / 實驗性 | Requires more monitoring / 需要更多監控 |

### 6.2 Selection Guide / 選擇指南

| Available Time / 可用時間 | Preferred TF / 偏好時間框架 |
|--------------------------|----------------------------|
| Full-time / 全時 | 4H, 1H |
| Part-time daily / 兼職每日 | 4H |
| Weekly only / 僅每週 | 1D |

---

## 7. Research Workflow / 研究流程

### 7.1 Seven Stages / 七個階段

```
1. Idea / 想法
2. Criteria Check / 標準檢查 (→ criteria.md)
3. Test Design / 測試設計
4. Result Review / 結果審查 (→ criteria.md for thresholds)
5. Strategy Card / 策略卡
6. Trade Plan / 交易計畫 (→ risk_control.md for sizing)
7. Daily Digest / Monitoring / 每日摘要/監控
```

### 7.2 Key References / 關鍵參考

| Stage / 階段 | Reference Document / 參考文件 |
|--------------|------------------------------|
| Criteria Check / 標準檢查 | `research/criteria.md` |
| Result Review / 結果審查 | `research/criteria.md` (elimination criteria) |
| Trade Plan / 交易計畫 | `research/risk_control.md` (risk dimensions) |

---

## 8. Output Types and Proposed Paths / 輸出類型與建議路徑

### 8.1 Output Types / 輸出類型

| Type / 類型 | Purpose / 目的 | Proposed Path / 建議路徑 |
|-------------|---------------|-------------------------|
| Strategy Card / 策略卡 | Strategy summary / 策略摘要 | `strategies/[id]_card.md` |
| Trade Plan / 交易計畫 | Executable instructions / 可執行指令 | `plans/[id]_plan.md` |
| Daily Digest / 每日摘要 | Performance summary / 績效摘要 | `digests/[date]_digest.md` |
| Monitoring / 監控 | Health overview / 健康概覽 | `monitoring/[id]_status.md` |

**Note**: Paths are proposed conventions, not enforced structure.

**注意**: 路徑為建議慣例，非強制結構。

### 8.2 Strategy Card Template / 策略卡模板

**Reference**: See `templates/strategy_card_template.md` (T-018)

**參考**: 見 `templates/strategy_card_template.md` (T-018)

---

## 9. BTC Research Themes / BTC 研究主題

### 9.1 Active Themes / 進行中主題

- BTC 4H Strategy Filter / BTC 4H 策略篩選
- BTC 1D MR Strategy Monitor / BTC 1D MR 策略監控

### 9.2 Planned Themes / 計畫主題

- Breakout systems / 突破系統
- Breakout failure / 突破失敗

---

## 10. ETH Research Themes / ETH 研究主題

### 10.1 Status: Provisional / 狀態：暫定

**Status**: ETH framework is **provisional** and **to be expanded**.

**狀態**: ETH 框架為**暫定**且**待擴充**。

### 10.2 Current Plan / 當前計畫

- Mirror BTC 4H framework for ETH / 將 BTC 4H 框架應用於 ETH
- Adapt for ETH-specific characteristics / 調整以適應 ETH 特性
- Evaluate correlation impact / 評估相關性影響

### 10.3 Considerations / 考量

- Higher volatility than BTC / 波動率高於 BTC
- Strong correlation with BTC (0.7-0.9) / 與 BTC 高度相關

---

## 11. Relationship to Other Documents / 與其他文件的關係

### 11.1 Document Hierarchy / 文件層級

```
Framework / 框架
├── BTC_ETH_strategy_framework.md (this file)
│   └── High-level workflow and categories
├── criteria.md
│   └── Selection, elimination, evaluation thresholds
└── risk_control.md
    └── Risk dimensions, position sizing, stop rules
```

### 11.2 Content Boundaries / 內容邊界

| Topic / 主題 | Located In / 位於 | Why / 原因 |
|--------------|-------------------|------------|
| Workflow stages / 工作流程階段 | This file / 本文件 | Framework definition |
| Elimination thresholds / 淘汰閾值 | criteria.md | Detailed criteria |
| Risk per trade / 每筆交易風險 | risk_control.md | Risk control specifics |
| Parameter limits / 參數限制 | criteria.md | Overfitting prevention |

---

## 12. What Belongs Here / 什麼應該放在這裡

### 12.1 Belongs Here / 應該放在這裡

- Workflow stages / 工作流程階段
- Output format definitions / 輸出格式定義
- Strategy category definitions / 策略類別定義
- High-level principles / 高層原則
- Proposed paths (as conventions) / 建議路徑（作為慣例）

### 12.2 Does Not Belong Here / 不應該放在這裡

| Content / 內容 | Belongs In / 應該放在 |
|----------------|----------------------|
| Specific thresholds / 具體閾值 | criteria.md |
| Risk calculations / 風險計算 | risk_control.md |
| Current project status / 當前專案狀態 | state/tasks.json |
| Backtest results / 回測結果 | Output reports / 輸出報告 |

---

## 13. Recommended Next Documents / 建議下一步文件

### 13.1 High Priority / 高優先級

- `strategies/BTC_4H_filter_card.md` - Document active strategy
- `templates/strategy_card_template.md` - Reusable template

### 13.2 Medium Priority / 中優先級

- `plans/BTC_4H_filter_plan.md` - Executable plan
- `research/eth_framework.md` - ETH-specific details (provisional)

---

## Summary / 摘要

| Element / 元素 | Definition / 定義 |
|----------------|-------------------|
| **Scope** / 範圍 | BTC and ETH research / BTC 與 ETH 研究 |
| **Framework** / 框架 | How research is conducted / 如何進行研究 |
| **Status** / 狀態 | Tracked in state/tasks.json / 記錄於 state/tasks.json |
| **Timeframes** / 時間框架 | 4H primary, 1D secondary (current preference) |
| **Categories** / 類別 | Breakout, Breakout Failure, MR |
| **Outputs** / 輸出 | Strategy card, Trade plan, Daily digest |
| **ETH** / ETH | Provisional, to be expanded / 暫定，待擴充 |

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `research/criteria.md` - Selection and elimination / 選擇與淘汰
- `research/risk_control.md` - Risk management / 風險管理
- `state/tasks.json` - Project status / 專案狀態
- `README.md` - System overview / 系統概覽
