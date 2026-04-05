# Risk Control Principles
# 風險控制原則

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define risk control principles and constraints for quantitative trading research and execution. These principles ensure capital preservation, prevent catastrophic losses, and maintain disciplined approach to strategy development.

定義量化交易研究與執行的風險控制原則與約束。這些原則確保資本保全、防止災難性損失，並維持策略開發的紀律方法。

---

## 2. Core Risk Control Principles / 核心風控原則

### 2.1 Capital Preservation First / 資本保全優先

**Principle**: Protect capital before seeking returns.

**原則**: 尋求報酬前先保護資本。

| Aspect / 方面 | Rule / 規則 |
|---------------|-------------|
| Maximum total risk / 最大總風險 | ≤ 2% per trade / 每筆交易 ≤ 2% |
| Portfolio heat / 投資組合熱度 | ≤ 6% total exposure / 總曝險 ≤ 6% |
| Single asset limit / 單一資產限制 | ≤ 50% of total capital / 總資本 ≤ 50% |

### 2.2 Asymmetric Risk-Reward / 非對稱風險報酬

**Principle**: Only take trades with favorable risk-reward ratio.

**原則**: 只進行具有有利風險報酬比的交易。

| Minimum Ratio / 最低比率 | Preferred Ratio / 偏好比率 |
|-------------------------|---------------------------|
| 1:1.5 (risk:reward) | 1:2 or better / 1:2 或更佳 |

### 2.3 Systematic Discipline / 系統化紀律

**Principle**: Follow rules without emotional override.

**原則**: 遵循規則，不受情緒干預。

- Pre-defined entry/exit rules / 預先定義進出場規則
- Automated execution where possible / 盡可能自動化執行
- No revenge trading / 不進行報復性交易
- No FOMO entries / 不因錯失恐懼而進場

### 2.4 Continuous Monitoring / 持續監控

**Principle**: Monitor all positions and strategy health in real-time.

**原則**: 即時監控所有部位與策略健康度。

| Monitoring Item / 監控項目 | Frequency / 頻率 |
|---------------------------|------------------|
| Position P&L / 部位損益 | Real-time / 即時 |
| Strategy performance / 策略績效 | Daily / 每日 |
| Drawdown status / 回撤狀態 | Real-time / 即時 |
| Risk metrics / 風險指標 | Weekly / 每週 |

---

## 3. Position and Exposure Discipline / 倉位與曝險紀律

### 3.1 Position Sizing Rules / 倉位規模規則

**Fixed Fractional Method / 固定比例法**:

```
Position Size = (Account Balance × Risk %) / (Entry Price - Stop Loss)
倉位規模 = (帳戶餘額 × 風險%) / (進場價 - 停損價)
```

| Parameter / 參數 | Value / 數值 | Notes / 備註 |
|------------------|--------------|--------------|
| Risk per trade / 每筆交易風險 | 1-2% | Never exceed 2% / 絕不超過 2% |
| Max positions / 最大部位數 | 3-5 | Concurrent trades / 同時進行交易 |
| Position scaling / 倉位縮放 | Gradual / 漸進 | Add on winners only / 僅在贏家加倉 |

### 3.2 Exposure Limits / 曝險限制

| Type / 類型 | Limit / 限制 | Action at Limit / 達到限制時行動 |
|-------------|--------------|----------------------------------|
| Single trade / 單筆交易 | 2% of capital | Reduce size or skip / 縮小規模或跳過 |
| Single asset / 單一資產 | 50% of capital | No new positions / 不新建倉 |
| Correlated assets / 相關資產 | 30% combined | Reduce exposure / 降低曝險 |
| Total portfolio / 總投資組合 | 6% at risk | Pause new entries / 暫停新進場 |

### 3.3 Correlation Awareness / 相關性意識

**High Correlation Assets / 高相關性資產**:
- BTCUSDT ↔ ETHUSDT (typically 0.7-0.9)

**Rule**: Treat correlated positions as single exposure.

**規則**: 將相關部位視為單一曝險。

```
Example / 範例:
- Long BTC (2% risk) + Long ETH (2% risk)
- Treated as: 4% correlated exposure
- Decision: Reduce one position or accept higher risk
```

---

## 4. Stop / Pause Conditions / 停止與暫停條件

### 4.1 Hard Stops / 硬性停止

**Execute immediately when triggered / 觸發時立即執行**:

| Condition / 條件 | Threshold / 閾值 | Action / 行動 |
|------------------|------------------|---------------|
| Daily loss limit / 每日虧損限制 | -3% of capital | Stop trading for day / 當日停止交易 |
| Weekly loss limit / 每週虧損限制 | -6% of capital | Stop trading for week / 當週停止交易 |
| Max drawdown / 最大回撤 | -15% from peak | Pause all strategies / 暫停所有策略 |
| Catastrophic stop / 災難停止 | -20% from peak | Full liquidation, review / 全數平倉，檢討 |

### 4.2 Soft Stops / 軟性停止

**Review and consider action / 檢討並考慮行動**:

| Condition / 條件 | Threshold / 閾值 | Action / 行動 |
|------------------|------------------|---------------|
| Consecutive losses / 連續虧損 | 3 in a row | Reduce size by 50% / 縮小規模 50% |
| Win rate drop / 勝率下降 | Below 40% | Review strategy / 檢討策略 |
| Sharpe decline / 夏普下降 | Below 0.5 for 1 month | Re-evaluate / 重新評估 |
| Volatility spike / 波動率飆升 | VIX > 30 | Reduce exposure / 降低曝險 |

### 4.3 Pause and Resume Protocol / 暫停與恢復協定

**Pause Triggers / 暫停觸發**:
1. Hit daily/weekly loss limit / 觸及每日/每週虧損限制
2. Max drawdown threshold reached / 達到最大回撤閾值
3. Manual user decision / 使用者手動決定
4. Market conditions unsuitable / 市場條件不適合

**Resume Conditions / 恢復條件**:
1. Cooling off period completed (24h for daily stop) / 冷卻期完成
2. Strategy review completed / 策略檢討完成
3. Market conditions normalized / 市場條件正常化
4. User explicit approval / 使用者明確批准

---

## 5. No Over-Optimization Rule / 不過度最佳化原則

### 5.1 Principle Statement / 原則聲明

**Strictly forbid curve-fitting and over-optimization.**

**嚴格禁止曲線配適與過度最佳化。**

### 5.2 Over-Optimization Checklist / 過度最佳化檢查清單

Before accepting a strategy, verify:

接受策略前，驗證：

- [ ] Parameters ≤ 5 optimized values / 參數 ≤ 5 個最佳化數值
- [ ] In-sample Sharpe not "too perfect" / 樣本內夏普不會「太完美」
- [ ] Out-sample performance ≥ 50% of in-sample / 樣本外表現 ≥ 樣本內 50%
- [ ] Parameter stability: top 3 parameter sets are similar / 參數穩定性：前 3 組參數設定相似
- [ ] Logic is explainable without data mining / 邏輯可解釋，非資料挖掘

### 5.3 Prevention Measures / 預防措施

| Measure / 措施 | Implementation / 實施 |
|----------------|----------------------|
| Parameter constraints / 參數限制 | Maximum 5 optimized parameters / 最多 5 個最佳化參數 |
| Wide ranges / 寬範圍 | Test parameters over wide ranges / 在寬範圍內測試參數 |
| Robustness test / 穩健性測試 | ±20% parameter variation test / ±20% 參數變化測試 |
| Simplification rule / 簡化規則 | Fewer rules beat complex rules / 少規則勝過複雜規則 |

### 5.4 Warning Signs / 警告訊號

| Sign / 訊號 | Interpretation / 解讀 | Action / 行動 |
|-------------|----------------------|---------------|
| Win rate > 70% | Likely overfitted / 可能過度最佳化 | Reject / 拒絕 |
| Perfect equity curve / 完美的權益曲線 | Curve fitting / 曲線配適 | Reject / 拒絕 |
| "Unique" parameter set / 「獨特」參數設定 | Not robust / 不穩健 | Widen ranges / 擴大範圍 |
| No out-sample data / 無樣本外資料 | Unvalidated / 未驗證 | Require OOS test / 要求樣本外測試 |

---

## 6. Failure Containment / 失敗控制

### 6.1 Pre-Mortem Analysis / 預先檢討

Before deploying any strategy, define failure scenarios:

部署任何策略前，定義失敗情境：

```markdown
## Strategy: [Name]

### Failure Scenarios / 失敗情境
1. **Market regime change / 市場機制改變**
   - Impact: Strategy stops working
   - Detection: Win rate drops below 40%
   - Response: Pause and review

2. **Black swan event / 黑天鵝事件**
   - Impact: Large gap moves
   - Detection: Gap > 5% against position
   - Response: Emergency exit

3. **Technical failure / 技術故障**
   - Impact: Orders not executed
   - Detection: Position mismatch
   - Response: Manual override
```

### 6.2 Failure Response Protocol / 失敗回應協定

| Severity / 嚴重程度 | Trigger / 觸發 | Response / 回應 |
|---------------------|----------------|-----------------|
| Low / 低 | Small loss (<1%) | Log and monitor / 記錄並監控 |
| Medium / 中 | Moderate loss (1-3%) | Reduce size / 縮小規模 |
| High / 高 | Large loss (3-6%) | Pause strategy / 暫停策略 |
| Critical / 嚴重 | Catastrophic (>6%) | Full stop, review / 完全停止，檢討 |

### 6.3 Recovery Plan / 恢復計畫

After any high/critical failure:

任何高/嚴重失敗後：

1. **Immediate / 立即**
   - Stop all trading / 停止所有交易
   - Document failure / 記錄失敗
   - Preserve capital / 保全資本

2. **Within 24 hours / 24 小時內**
   - Analyze root cause / 分析根本原因
   - Review strategy logic / 檢討策略邏輯
   - Assess market conditions / 評估市場條件

3. **Within 1 week / 1 週內**
   - Decide: fix, replace, or abandon / 決定：修正、替換或放棄
   - Update risk parameters / 更新風險參數
   - Resume with caution / 謹慎恢復

---

## 7. Research vs Live Execution Boundary / 研究與實盤邊界

### 7.1 Clear Separation / 明確區分

| Aspect / 方面 | Research / 研究 | Live Execution / 實盤執行 |
|---------------|-----------------|---------------------------|
| Data / 資料 | Historical / 歷史 | Real-time / 即時 |
| Risk / 風險 | Simulated / 模擬 | Real capital / 真實資本 |
| Speed / 速度 | No urgency / 不緊急 | Milliseconds matter / 毫秒重要 |
| Validation / 驗證 | Backtest / 回測 | Paper trade first / 先模擬交易 |
| Emotion / 情緒 | Detached / 抽離 | Present / 存在 |

### 7.2 Transition Criteria / 轉換標準

**From Research to Live / 從研究到實盤**:

- [ ] Out-sample validation passed / 樣本外驗證通過
- [ ] Paper trading profitable (≥ 1 month) / 模擬交易獲利（≥ 1 個月）
- [ ] Risk parameters defined / 風險參數已定義
- [ ] Stop conditions set / 停止條件已設定
- [ ] User approval obtained / 獲得使用者批准

**From Live to Research / 從實盤到研究**:

- Strategy fails live performance / 策略實盤表現失敗
- Market conditions change / 市場條件改變
- Better strategy identified / 識別到更好的策略
- User decides to stop / 使用者決定停止

### 7.3 MOCK ONLY Policy / 僅模擬政策

**Current System**: Research phase only / 目前系統：僅研究階段

| Phase / 階段 | Status / 狀態 | Notes / 備註 |
|--------------|---------------|--------------|
| Backtesting / 回測 | ✅ Active / 進行中 | Historical data only / 僅歷史資料 |
| Paper trading / 模擬交易 | ⏳ Planned / 計畫中 | Simulated execution / 模擬執行 |
| Live trading / 實盤交易 | ❌ Not allowed / 不允許 | Requires explicit approval / 需要明確批准 |

**No real trading API keys in research environment.**

**研究環境中無真實交易 API 金鑰。**

---

## 8. Relationship to Trade Plan / 與交易計畫的關係

### 8.1 Trade Plan Components / 交易計畫組成

Risk Control Principles inform the Trade Plan:

風險控制原則指導交易計畫：

```
Trade Plan / 交易計畫
├── Strategy Rules / 策略規則
│   ├── Entry conditions / 進場條件
│   ├── Exit conditions / 出場條件
│   └── Position sizing / 倉位規模
├── Risk Control / 風險控制  ←── This document
│   ├── Stop losses / 停損
│   ├── Position limits / 倉位限制
│   └── Pause conditions / 暫停條件
└── Execution Rules / 執行規則
    ├── Order types / 訂單類型
    ├── Timing / 時機
    └── Emergency procedures / 緊急程序
```

### 8.2 From Principles to Plan / 從原則到計畫

| Principle / 原則 | Plan Element / 計畫元素 |
|------------------|------------------------|
| Capital preservation / 資本保全 | Max 2% per trade rule / 每筆交易最多 2% 規則 |
| Asymmetric risk-reward / 非對稱風險報酬 | Only 1:2+ trades / 僅 1:2+ 交易 |
| No over-optimization / 不過度最佳化 | Parameter limits in strategy doc / 策略文件中的參數限制 |
| Failure containment / 失敗控制 | Pre-defined exit scenarios / 預定義出場情境 |

### 8.3 Active Projects Risk Profile / 進行中專案風險概況

Per USER.md:

| Project / 專案 | Status / 狀態 | Risk Level / 風險等級 | Key Control / 關鍵控制 |
|----------------|---------------|----------------------|------------------------|
| BTC 4H Strategy Filter / BTC 4H 策略篩選 | Active research / 進行中研究 | Medium / 中 | Elimination criteria / 淘汰標準 |
| BTC 1D MR Strategy Monitor / BTC 1D MR 策略監控 | Maintenance / 維護 | Low / 低 | Performance tracking / 績效追蹤 |
| TSMC MR Strategy / TSMC MR 策略 | Maintenance / 維護 | Low / 低 | Performance tracking / 績效追蹤 |

---

## Summary / 摘要

| Principle / 原則 | Key Rule / 關鍵規則 |
|------------------|---------------------|
| **Capital Preservation** / 資本保全 | ≤ 2% risk per trade / 每筆交易 ≤ 2% 風險 |
| **Asymmetric Risk-Reward** / 非對稱風險報酬 | 1:2 minimum ratio / 最低 1:2 比率 |
| **No Over-Optimization** / 不過度最佳化 | ≤ 5 parameters, validated OOS / ≤ 5 參數，樣本外驗證 |
| **Systematic Discipline** / 系統化紀律 | Pre-defined rules, no emotion / 預定義規則，無情緒 |
| **Failure Containment** / 失敗控制 | Pre-mortem, response protocols / 預先檢討，回應協定 |
| **Research Only** / 僅研究 | No live trading without approval / 未經批准不實盤 |

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
- `README.md` - System overview and active projects / 系統概覽與進行中專案
- `USER.md` - User preferences and risk tolerance / 使用者偏好與風險承受度
- `rules/BLOCKER_REPORT_FORMAT.md` - Risk escalation procedures / 風險升級程序
