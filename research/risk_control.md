# Risk Control Principles
# 風險控制原則

**Version**: 1.1.0  
**版本**: 1.1.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define risk control principles and constraints for quantitative trading research. These principles ensure capital preservation, prevent catastrophic losses, and maintain disciplined approach to strategy development.

定義量化交易研究的風險控制原則與約束。這些原則確保資本保全、防止災難性損失，並維持策略開發的紀律方法。

---

## 2. Risk Dimensions / 風險維度

### 2.1 Three Distinct Risk Types / 三種風險類型

| Dimension / 維度 | Definition / 定義 | Key Metric / 關鍵指標 |
|------------------|-------------------|----------------------|
| **Capital Allocation** / 資本配置 | How much capital is committed to a strategy / 多少資本投入策略 | Strategy allocation % / 策略配置百分比 |
| **Risk at Stop** / 停損風險 | Maximum loss if stop is hit / 停損觸及時的最大損失 | % of account per trade / 每筆交易帳戶百分比 |
| **Exposure** / 曝險 | Current market exposure from open positions / 未平倉部位的當前市場曝險 | Position size × volatility / 倉位規模 × 波動率 |

### 2.2 Relationship Between Dimensions / 維度間關係

```
Capital Allocation / 資本配置
    └── How much to allocate to strategy / 分配多少給策略

Risk at Stop / 停損風險
    └── Per-trade maximum loss / 每筆交易最大損失
    └── Determined by: position size, entry, stop level
    └── 由倉位規模、進場價、停損位決定

Exposure / 曝險
    └── Current market risk / 當前市場風險
    └── Changes with price movement / 隨價格變動而變化
```

### 2.3 Draft Guidelines (To Be Confirmed) / 草稿指引（待確認）

**Status**: These numbers are draft guidelines, not finalized policy.

**狀態**: 以下數字為草稿指引，非最終政策。

| Guideline / 指引 | Draft Value / 草稿值 | Notes / 備註 |
|------------------|---------------------|--------------|
| Risk per trade / 每筆交易風險 | 1-2% of account | Conservative starting point / 保守起點 |
| Portfolio heat / 投資組合熱度 | ≤ 6% total at risk | Sum of all stop risks / 所有停損風險總和 |
| Single asset allocation / 單一資產配置 | ≤ 50% of capital | Capital allocation, not exposure / 資本配置，非曝險 |

**To confirm**: These values should be validated with user based on account size and risk tolerance.

**待確認**: 這些數值應依帳戶規模與風險承受度與使用者確認。

---

## 3. Core Risk Control Principles / 核心風控原則

### 3.1 Capital Preservation First / 資本保全優先

**Principle**: Never risk more than you can afford to lose.

**原則**: 絕不冒無法承受的風險。

**Application / 應用**:
- Define maximum acceptable loss per trade / 定義每筆交易最大可接受損失
- Limit total account heat / 限制總帳戶熱度
- Emergency stops for catastrophic scenarios / 災難情境的緊急停止

### 3.2 Asymmetric Risk-Reward / 非對稱風險報酬

**Principle**: Only take trades with favorable risk-reward ratio.

**原則**: 只進行具有有利風險報酬比的交易。

| Minimum / 最低 | Preferred / 偏好 |
|----------------|------------------|
| 1:1.5 | 1:2 or better / 1:2 或更佳 |

### 3.3 Systematic Discipline / 系統化紀律

**Principle**: Follow rules without emotional override.

**原則**: 遵循規則，不受情緒干預。

- Pre-defined entry/exit rules / 預先定義進出場規則
- No revenge trading / 不進行報復性交易
- No FOMO entries / 不因錯失恐懼而進場

---

## 4. Stop / Pause / Resume Framework / 停止、暫停、恢復框架

### 4.1 Unified Status Definitions / 統一狀態定義

Consistent with `research/criteria.md`:

與 `research/criteria.md` 一致：

| Status / 狀態 | Definition / 定義 | Risk Action / 風險行動 |
|---------------|-------------------|------------------------|
| **Active** / 進行中 | Normal operation / 正常運作 | Standard monitoring / 標準監控 |
| **Monitor** / 監控 | Warning signs present / 存在警告訊號 | Increased scrutiny / 增加審查 |
| **Pause** / 暫停 | Review required / 需要檢討 | No new entries / 不新進場 |
| **Stop** / 停止 | Hard limit hit / 觸及硬性限制 | Close positions / 平倉 |
| **Eliminate** / 淘汰 | Strategy failed / 策略失敗 | Archive / 歸檔 |

### 4.2 Triggers by Severity / 依嚴重程度觸發

#### Hard Stops (Immediate Action) / 硬性停止（立即行動）

| Trigger / 觸發 | Threshold (Draft) / 閾值（草稿）| Action / 行動 |
|----------------|--------------------------------|---------------|
| Daily loss limit / 每日虧損限制 | -3% of account | Stop for day / 當日停止 |
| Weekly loss limit / 每週虧損限制 | -6% of account | Stop for week / 當週停止 |
| Max drawdown / 最大回撤 | -15% from peak | Pause all / 暫停所有 |
| Catastrophic / 災難性 | -20% from peak | Full stop / 完全停止 |

#### Soft Stops (Review Required) / 軟性停止（需檢討）

| Trigger / 觸發 | Threshold / 閾值 | Action / 行動 |
|----------------|------------------|---------------|
| Consecutive losses / 連續虧損 | 3 in a row | Reduce size 50% / 縮小規模 50% |
| Win rate drop / 勝率下降 | Below 40% | Review / 檢討 |
| Sharpe decline / 夏普下降 | Below 0.5 for 1 month | Re-evaluate / 重新評估 |

### 4.3 Pause and Resume Protocol / 暫停與恢復協定

**Pause Triggers / 暫停觸發**:
1. Soft stop threshold reached / 觸及軟性停止閾值
2. User decision / 使用者決定
3. Market conditions unsuitable / 市場條件不適合

**Resume Conditions / 恢復條件**:
1. Cooling period (24h for daily, 1 week for strategy) / 冷卻期
2. Review completed / 檢討完成
3. User approval / 使用者批准

---

## 5. Failure Protocol / 失敗協定

### 5.1 Unified with Stop Framework / 與停止框架統一

| Severity / 嚴重程度 | Corresponds to / 對應 | Response / 回應 |
|---------------------|----------------------|-----------------|
| Low / 低 | Warning sign / 警告訊號 | Monitor / 監控 |
| Medium / 中 | Soft stop / 軟性停止 | Reduce size / 縮小規模 |
| High / 高 | Pause / 暫停 | Stop new entries / 停止新進場 |
| Critical / 嚴重 | Hard stop / 硬性停止 | Close all / 全部平倉 |

### 5.2 Recovery Process / 恢復流程

After high/critical failure:

高/嚴重失敗後：

1. **Immediate / 立即**: Stop, document, preserve capital / 停止、記錄、保全資本
2. **Within 24h / 24 小時內**: Analyze root cause / 分析根本原因
3. **Within 1 week / 1 週內**: Decide fix/replace/abandon / 決定修正/替換/放棄

---

## 6. Research vs Live Execution Boundary / 研究與實盤邊界

### 6.1 Hard Boundary / 硬性邊界

**Research Environment / 研究環境**:
- ✅ Historical backtesting / 歷史回測
- ✅ Paper trading simulation / 模擬交易
- ✅ Strategy development / 策略開發
- ❌ No real orders / 無真實訂單
- ❌ No real capital at risk / 無真實資本風險

**Live Environment / 實盤環境**:
- ✅ Real market orders / 真實市場訂單
- ✅ Real capital / 真實資本
- ⚠️ Requires explicit user approval / 需要明確使用者批准
- ⚠️ Requires separate validation / 需要單獨驗證

### 6.2 Transition Gates / 轉換閘門

**Research → Paper Trading / 研究 → 模擬交易**:
- [ ] Out-sample validation passed / 樣本外驗證通過
- [ ] Strategy documented / 策略已記錄
- [ ] Risk parameters defined / 風險參數已定義

**Paper Trading → Live / 模擬交易 → 實盤**:
- [ ] Profitable paper record (≥ 1 month) / 模擬交易獲利記錄
- [ ] All risk controls tested / 所有風險控制已測試
- [ ] **User explicit approval required** / **需要使用者明確批准**
- [ ] Live environment setup complete / 實盤環境設定完成

### 6.3 Current Status: RESEARCH ONLY / 當前狀態：僅研究

| Phase / 階段 | Status / 狀態 | Notes / 備註 |
|--------------|---------------|--------------|
| Backtesting / 回測 | ✅ Active | Historical data only |
| Paper trading / 模擬交易 | ⏳ Planned | Not yet started |
| Live trading / 實盤交易 | ❌ **NOT ALLOWED** | Requires explicit user decision |

**No real trading API keys in research environment.**

**研究環境中無真實交易 API 金鑰。**

---

## 7. No Over-Optimization / 不過度最佳化

### 7.1 Constraints / 限制

- Parameters ≤ 5 / 參數 ≤ 5
- Must validate out-of-sample / 必須樣本外驗證
- Prefer simple over complex / 偏好簡單而非複雜

### 7.2 Warning Signs / 警告訊號

- Win rate > 70% / 勝率 > 70%
- Perfect equity curve / 完美權益曲線
- No out-of-sample data / 無樣本外資料

---

## Summary / 摘要

| Principle / 原則 | Application / 應用 |
|------------------|-------------------|
| **Three Risk Dimensions** / 三種風險維度 | Capital allocation, Risk at stop, Exposure / 資本配置、停損風險、曝險 |
| **Draft Guidelines** / 草稿指引 | 1-2% per trade, 6% heat (to be confirmed) / 每筆 1-2%，6% 熱度（待確認）|
| **Status Framework** / 狀態框架 | Active → Monitor → Pause → Stop → Eliminate |
| **Research Only** / 僅研究 | No live trading without explicit approval / 未經明確批准不實盤 |
| **Over-Optimization** / 過度最佳化 | ≤ 5 params, OOS required / ≤ 5 參數，需樣本外 |

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
- `templates/strategy_card_template.md` - Strategy documentation / 策略文件
