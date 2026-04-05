# BTC / ETH Strategy Framework
# BTC / ETH 策略框架

**Version**: 1.0.0  
**版本**: 1.0.0  
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
- Cross-asset correlation studies / 跨資產相關性研究

### 2.2 Out of Scope / 範圍外

- Traditional equity strategies (TSMC, etc.) / 傳統股票策略
- Altcoin research (beyond ETH) / 山寨幣研究
- DeFi yield farming / DeFi 流動性挖礦
- NFT trading / NFT 交易
- Fundamental analysis / 基本面分析

### 2.3 Boundary Statement / 邊界聲明

This framework focuses **exclusively** on BTC and ETH spot/perpetual strategies using technical analysis.

本框架**專注於**使用技術分析的 BTC 與 ETH 現貨/永續合約策略。

---

## 3. Core Research Objectives / 核心研究目標

### 3.1 Primary Objectives / 主要目標

| Objective / 目標 | Description / 說明 | Success Metric / 成功指標 |
|------------------|-------------------|---------------------------|
| Identify robust edges / 識別穩健優勢 | Find repeatable patterns / 找到可重複的模式 | Out-sample Sharpe > 0.5 |
| Minimize drawdowns / 最小化回撤 | Control risk in volatile markets / 在波動市場控制風險 | Max DD < 20% |
| Maintain simplicity / 保持簡單 | Avoid over-complex strategies / 避免過度複雜策略 | Parameters ≤ 5 |
| Ensure reusability / 確保可重用 | Work across market regimes / 跨市場機制有效 | 2+ years of data tested |

### 3.2 Secondary Objectives / 次要目標

- Document all research findings / 記錄所有研究發現
- Build reusable strategy components / 建立可重用策略元件
- Create monitoring infrastructure / 建立監控基礎設施
- Develop systematic evaluation process / 發展系統化評估流程

---

## 4. Strategy Categories / 策略分類

### 4.1 Breakout / 突破

**Definition**: Enter when price breaks above/below key levels.

**定義**: 當價格突破關鍵位時進場。

| Aspect / 方面 | Description / 說明 |
|---------------|-------------------|
| Entry trigger / 進場觸發 | Price closes above resistance / 收盤突破阻力位 |
| Exit trigger / 出場觸發 | Target reached or false breakout confirmed / 達到目標或確認假突破 |
| Best timeframe / 最佳時間框架 | 4H, 1D |
| Market condition / 市場條件 | Trending / 趨勢市 |

### 4.2 Breakout Failure / 突破失敗

**Definition**: Fade the breakout when it fails to follow through.

**定義**: 當突破未能持續時反向操作。

| Aspect / 方面 | Description / 說明 |
|---------------|-------------------|
| Entry trigger / 進場觸發 | Breakout reverses within N bars / N 根 K 線內突破反轉 |
| Exit trigger / 出場觸發 | Return to breakout level or stop hit / 回到突破位或觸及停損 |
| Best timeframe / 最佳時間框架 | 1H, 4H |
| Market condition / 市場條件 | Ranging / 震盪市 |

### 4.3 Mean Reversion (MR) / 均值回歸

**Definition**: Trade price extremes back toward average.

**定義**: 在價格極端時交易回歸平均值。

| Aspect / 方面 | Description / 說明 |
|---------------|-------------------|
| Entry trigger / 進場觸發 | Price reaches statistical extreme / 價格達到統計極端 |
| Exit trigger / 出場觸發 | Return to mean or stop hit / 回歸均值或觸及停損 |
| Best timeframe / 最佳時間框架 | 4H, 1D |
| Market condition / 市場條件 | Ranging, mild trend / 震盪、溫和趨勢 |

**Status**: Currently active for BTC 1D MR monitoring / 目前 BTC 1D MR 監控進行中

### 4.4 Daily / Hourly Monitoring / 每日/每小時監控

**Definition**: Systematic tracking of strategy performance and market conditions.

**定義**: 系統化追蹤策略績效與市場條件。

| Type / 類型 | Frequency / 頻率 | Content / 內容 |
|-------------|------------------|----------------|
| Daily Digest / 每日摘要 | Daily / 每日 | Performance summary, signals / 績效摘要、訊號 |
| Hourly Check / 每小時檢查 | Hourly / 每小時 | Key levels, setup forming / 關鍵位、正在形成的設定 |
| Alert System / 警示系統 | Real-time / 即時 | Trigger conditions met / 觸發條件達成 |

---

## 5. Timeframes / 時間框架

### 5.1 Primary Timeframes / 主要時間框架

| Timeframe / 時間框架 | Priority / 優先級 | Best For / 最適合 | Active Projects / 進行中專案 |
|---------------------|-------------------|-------------------|------------------------------|
| **4H** | High / 高 | Swing trading / 波段交易 | BTC 4H Strategy Filter |
| **1D** | High / 高 | Position trading / 部位交易 | BTC 1D MR Strategy Monitor |
| 1H | Medium / 中 | Short-term / 短期 | (to be defined / 待補充) |

### 5.2 Timeframe Selection Guide / 時間框架選擇指南

```
Available Time / 可用時間 → Timeframe / 時間框架
─────────────────────────────────────────────────
Full-time monitoring / 全時監控 → 1H, 4H
Part-time (daily check) / 兼職（每日檢查）→ 4H
Weekly check only / 僅每週檢查 → 1D
```

### 5.3 Multi-Timeframe Analysis / 多時間框架分析

| Higher TF / 較高時間框架 | Lower TF / 較低時間框架 | Use Case / 使用情境 |
|-------------------------|------------------------|---------------------|
| 1D (trend) | 4H (entry) | Confirm trend, time entry / 確認趨勢，掌握進場時機 |
| 4H (trend) | 1H (entry) | Fine-tune entry / 微調進場 |

---

## 6. Research Workflow / 研究流程

### 6.1 Workflow Stages / 工作流程階段

```
Idea / 想法
    ↓
Criteria Check / 標準檢查
    ↓
Test Design / 測試設計
    ↓
Result Review / 結果審查
    ↓
Strategy Card / 策略卡
    ↓
Trade Plan / 交易計畫
    ↓
Daily Digest / Monitoring / 每日摘要/監控
```

### 6.2 Stage Details / 階段詳情

#### Stage 1: Idea / 想法

- Document hypothesis / 記錄假設
- Identify market pattern / 識別市場模式
- Check existing research / 檢查現有研究

**Output**: Idea note / 想法筆記

#### Stage 2: Criteria Check / 標準檢查

Validate against `research/criteria.md`:

- [ ] Clear hypothesis / 清晰的假設
- [ ] Testable rules / 可測試的規則
- [ ] Sufficient data / 足夠的資料
- [ ] Risk parameters defined / 風險參數已定義

**Output**: Go / No-Go decision / 繼續/停止決定

#### Stage 3: Test Design / 測試設計

- Define entry/exit rules / 定義進出場規則
- Set position sizing / 設定倉位規模
- Plan backtest parameters / 規劃回測參數

**Output**: Test plan document / 測試計畫文件

#### Stage 4: Result Review / 結果審查

Evaluate backtest results:

| Metric / 指標 | Threshold / 閾值 | Decision / 決定 |
|---------------|------------------|-----------------|
| Return after costs / 含成本後報酬 | > 0 | Continue / 繼續 |
| Median return / 中位數報酬 | > 0 | Continue / 繼續 |
| Max drawdown / 最大回撤 | < 20% | Continue / 繼續 |
| Sharpe ratio / 夏普比率 | > 0.5 | Continue / 繼續 |

**Output**: Review report / 審查報告

#### Stage 5: Strategy Card / 策略卡

Create formal strategy documentation:

```markdown
# Strategy Card: [Name]

## Basic Info / 基本資訊
- Asset: BTCUSDT / ETHUSDT
- Timeframe: 4H / 1D
- Type: Breakout / MR / Breakout Failure
- Status: Active / Monitoring / Eliminated

## Logic / 邏輯
- Entry: [conditions]
- Exit: [conditions]
- Risk: [parameters]

## Performance / 績效
- Return: X%
- Max DD: X%
- Sharpe: X

## Elimination Triggers / 淘汰觸發條件
- [List criteria]
```

**Output**: `strategies/[strategy_id]_card.md`

#### Stage 6: Trade Plan / 交易計畫

Create executable plan:

- Entry checklist / 進場檢查清單
- Position size calculation / 倉位規模計算
- Exit scenarios / 出場情境
- Risk limits / 風險限制

**Output**: `plans/[strategy_id]_trade_plan.md`

#### Stage 7: Daily Digest / Monitoring / 每日摘要/監控

Ongoing performance tracking:

- Daily P&L / 每日損益
- Signal generation / 訊號產生
- Health metrics / 健康指標

**Output**: `digests/[date]_daily_digest.md`

---

## 7. Output Types / 輸出類型

### 7.1 Strategy Card / 策略卡

**Purpose**: Single-page strategy summary / 單頁策略摘要  
**Location**: `strategies/[strategy_id]_card.md`  
**Updated**: When strategy changes / 策略變更時更新

**Required Fields / 必填欄位**:
- Strategy ID / 策略識別碼
- Asset & Timeframe / 資產與時間框架
- Entry/Exit Rules / 進出場規則
- Risk Parameters / 風險參數
- Performance Metrics / 績效指標
- Elimination Triggers / 淘汰觸發條件

### 7.2 Trade Plan / 交易計畫

**Purpose**: Executable trading instructions / 可執行的交易指令  
**Location**: `plans/[strategy_id]_trade_plan.md`  
**Updated**: Per trade setup / 每次交易設定時更新

**Required Fields / 必填欄位**:
- Setup conditions / 設定條件
- Entry checklist / 進場檢查清單
- Position size / 倉位規模
- Stop loss level / 停損位
- Take profit targets / 獲利目標
- Risk amount / 風險金額

### 7.3 Daily Digest / 每日摘要

**Purpose**: Daily performance summary / 每日績效摘要  
**Location**: `digests/[date]_daily_digest.md`  
**Updated**: Daily / 每日更新

**Required Fields / 必填欄位**:
- Date / 日期
- Active strategies / 進行中策略
- Signals generated / 產生的訊號
- Positions status / 部位狀態
- P&L summary / 損益摘要
- Market notes / 市場備註

### 7.4 Monitoring Summary / 監控摘要

**Purpose**: Strategy health overview / 策略健康度概覽  
**Location**: `monitoring/[strategy_id]_status.md`  
**Updated**: Weekly or on trigger / 每週或觸發時更新

**Required Fields / 必填欄位**:
- Current status / 目前狀態
- Performance vs benchmark / 績效對比基準
- Risk metrics / 風險指標
- Alert status / 警示狀態
- Recommended action / 建議行動

---

## 8. BTC-related Existing Themes / BTC 既有研究主題

### 8.1 Active Research / 進行中研究

| Theme / 主題 | Status / 狀態 | Description / 說明 |
|--------------|---------------|-------------------|
| BTC 4H Strategy Filter / BTC 4H 策略篩選 | Active / 進行中 | Systematic filtering of 4H strategies / 4H 策略系統化篩選 |
| BTC 1D MR Strategy Monitor / BTC 1D MR 策略監控 | Maintenance / 維護 | Daily monitoring of MR strategy / MR 策略每日監控 |

### 8.2 Strategy Types Under Research / 研究中的策略類型

- **Breakout systems** / 突破系統: To be tested / 待測試
- **Breakout failure** / 突破失敗: To be tested / 待測試
- **Volume-based entries** / 基於量能的進場: To be defined / 待定義
- **Volatility expansion** / 波動率擴張: To be defined / 待定義

### 8.3 Timeframe Focus / 時間框架重點

- **Primary**: 4H / 主要
- **Secondary**: 1D / 次要
- **Experimental**: 1H / 實驗性

---

## 9. ETH-related Existing Themes / ETH 既有研究主題

### 8.1 Active Research / 進行中研究

| Theme / 主題 | Status / 狀態 | Description / 說明 |
|--------------|---------------|-------------------|
| ETH 4H Strategy Research / ETH 4H 策略研究 | Planned / 計畫中 | Mirror BTC 4H framework for ETH / 將 BTC 4H 框架應用於 ETH |

### 8.2 Considerations / 考量因素

- Higher volatility than BTC / 波動率高於 BTC
- Strong correlation with BTC (0.7-0.9) / 與 BTC 高度相關
- Different liquidity profile / 不同的流動性特徵
- May share signals with BTC strategies / 可能與 BTC 策略共享訊號

### 8.3 Planned Work / 計畫工作

- Adapt BTC strategies for ETH / 調整 BTC 策略用於 ETH
- Test ETH-specific patterns / 測試 ETH 特定模式
- Evaluate cross-asset hedging / 評估跨資產對沖

---

## 10. Relationship to Criteria and Risk Control / 與 criteria 和 risk control 的關係

### 10.1 Document Hierarchy / 文件層級

```
Research Framework / 研究框架
├── BTC_ETH_strategy_framework.md (this file / 本文件)
│   └── Defines workflow and outputs / 定義工作流程與輸出
├── criteria.md
│   └── Defines selection and elimination / 定義選擇與淘汰
├── risk_control.md
│   └── Defines risk limits / 定義風險限制
└── Output documents / 輸出文件
    ├── Strategy cards / 策略卡
    ├── Trade plans / 交易計畫
    └── Daily digests / 每日摘要
```

### 10.2 Integration Points / 整合點

| This Framework / 本框架 | Links To / 連結到 | Purpose / 目的 |
|------------------------|-------------------|----------------|
| Research workflow Stage 2 / 研究工作流程第 2 階段 | `criteria.md` | Validate ideas / 驗證想法 |
| Strategy card risk section / 策略卡風險章節 | `risk_control.md` | Set limits / 設定限制 |
| Elimination triggers / 淘汰觸發條件 | `criteria.md` | Auto-eliminate / 自動淘汰 |
| Position sizing / 倉位規模 | `risk_control.md` | Calculate size / 計算規模 |

### 10.3 Decision Flow / 決策流程

```
New Idea / 新想法
    ↓
Check criteria.md / 檢查 criteria.md
    ↓
Valid? → Design test / 有效？→ 設計測試
    ↓
Check risk_control.md / 檢查 risk_control.md
    ↓
Within limits? → Execute / 在限制內？→ 執行
    ↓
Create outputs / 建立輸出
```

---

## 11. What Belongs Here vs Not Here / 什麼應該放在這裡，什麼不應該

### 11.1 Belongs Here / 應該放在這裡

| Content / 內容 | Example / 範例 |
|----------------|----------------|
| Strategy framework / 策略框架 | Workflow stages / 工作流程階段 |
| Output formats / 輸出格式 | Strategy card template / 策略卡模板 |
| Timeframe selection / 時間框架選擇 | 4H primary, 1D secondary / 4H 主要，1D 次要 |
| Category definitions / 類別定義 | Breakout, MR, Breakout Failure |
| Active project list / 進行中專案列表 | BTC 4H Filter, BTC 1D MR Monitor |

### 11.2 Does Not Belong Here / 不應該放在這裡

| Content / 內容 | Belongs In / 應該放在 | Why / 原因 |
|----------------|----------------------|-----------|
| Specific indicator settings / 特定指標設定 | Strategy card / 策略卡 | Implementation detail / 實作細節 |
| Exact backtest results / 確切回測結果 | Review report / 審查報告 | Output of research / 研究產出 |
| Daily P&L numbers / 每日損益數字 | Daily digest / 每日摘要 | Operational data / 營運資料 |
| API credentials / API 憑證 | Secure storage / 安全儲存 | Security / 安全 |
| Complex mathematical proofs / 複雜數學證明 | Research notes / 研究筆記 | Too detailed / 過於細節 |

### 11.3 When in Doubt / 有疑問時

Ask: "Is this about the **framework** or the **specific strategy**?"

問：「這是關於**框架**還是**特定策略**？」

- Framework → This document / 框架 → 本文件
- Specific strategy → Strategy card / 特定策略 → 策略卡

---

## 12. Recommended Next Research Documents / 建議下一步研究文件

### 12.1 High Priority / 高優先級

| Document / 文件 | Purpose / 目的 | Trigger / 觸發條件 |
|-----------------|----------------|-------------------|
| `strategies/BTC_4H_filter_card.md` | Document active strategy / 記錄進行中策略 | T-017 completed / T-017 完成後 |
| `strategies/BTC_1D_MR_card.md` | Document active strategy / 記錄進行中策略 | User request / 使用者要求 |

### 12.2 Medium Priority / 中優先級

| Document / 文件 | Purpose / 目的 | Trigger / 觸發條件 |
|-----------------|----------------|-------------------|
| `plans/BTC_4H_filter_plan.md` | Executable plan / 可執行計畫 | Strategy validated / 策略驗證後 |
| `backtest/BTC_4H_results.md` | Backtest documentation / 回測文件 | Test completed / 測試完成後 |

### 12.3 Lower Priority / 較低優先級

| Document / 文件 | Purpose / 目的 | Trigger / 觸發條件 |
|-----------------|----------------|-------------------|
| `eth_framework.md` | ETH-specific framework / ETH 專屬框架 | BTC framework stable / BTC 框架穩定後 |
| `correlation_study.md` | BTC-ETH correlation analysis / BTC-ETH 相關性分析 | Need identified / 識別需求後 |

### 12.4 Document Naming Convention / 文件命名規則

```
[type]/[asset]_[timeframe]_[description].[ext]

Examples / 範例:
- strategies/BTC_4H_filter_card.md
- plans/BTC_1D_MR_trade_plan.md
- digests/2026-04-05_daily_digest.md
- monitoring/BTC_4H_filter_status.md
```

---

## Summary / 摘要

| Element / 元素 | Definition / 定義 |
|----------------|-------------------|
| **Scope** / 範圍 | BTC and ETH only / 僅 BTC 與 ETH |
| **Timeframes** / 時間框架 | 4H (primary), 1D (secondary) / 4H（主要），1D（次要） |
| **Categories** / 類別 | Breakout, Breakout Failure, MR / 突破、突破失敗、均值回歸 |
| **Workflow** / 工作流程 | 7 stages from idea to monitoring / 從想法到監控的 7 個階段 |
| **Outputs** / 輸出 | Strategy card, Trade plan, Daily digest, Monitoring / 策略卡、交易計畫、每日摘要、監控 |
| **Active** / 進行中 | BTC 4H Filter (research), BTC 1D MR (monitoring) / BTC 4H 篩選（研究）、BTC 1D MR（監控） |

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `research/criteria.md` - Research selection and elimination / 研究選題與淘汰
- `research/risk_control.md` - Risk management principles / 風險管理原則
- `README.md` - System overview / 系統概覽
- `USER.md` - Active projects and preferences / 進行中專案與偏好
