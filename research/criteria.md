# Research Criteria
# 研究標準

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define standardized criteria for selecting, evaluating, and eliminating trading strategies in quantitative research. These criteria ensure research quality, prevent overfitting, and maintain focus on robust, reusable findings.

定義量化研究中選擇、評估和淘汰交易策略的標準化準則。這些標準確保研究品質、防止過度最佳化，並保持對穩健、可重用發現的關注。

---

## 2. Research Selection Criteria / 研究選題標準

### 2.1 Primary Instruments / 主要標的

| Instrument / 標的 | Timeframe / 時間框架 | Priority / 優先級 |
|-------------------|---------------------|-------------------|
| BTCUSDT | 4H (primary) / 4小時（主要） | High / 高 |
| BTCUSDT | 1D / 1天 | Medium / 中 |
| ETHUSDT | 4H (primary) / 4小時（主要） | High / 高 |
| ETHUSDT | 1D / 1天 | Medium / 中 |

### 2.2 Strategy Types / 策略類型

Focus areas for research:

研究的重點領域：

| Type / 類型 | Description / 說明 | Priority / 優先級 |
|-------------|-------------------|-------------------|
| Mean Reversion (MR) / 均值回歸 | Price returns to average / 價格回歸平均值 | High / 高 |
| Breakout / 突破 | Price breaks key levels / 價格突破關鍵位 | Medium / 中 |
| Trend Following / 趨勢跟隨 | Following established trends / 跟隨已建立趨勢 | Medium / 中 |

### 2.3 Minimum Viable Criteria / 最低可行標準

Before starting research, ensure:

開始研究前，確保：

- [ ] Clear hypothesis / 清晰的假設
- [ ] Defined entry/exit rules / 定義進出場規則
- [ ] Risk management parameters / 風險管理參數
- [ ] Backtesting capability / 回測能力
- [ ] Out-of-sample validation plan / 樣本外驗證計畫

---

## 3. Elimination Criteria / 淘汰標準

### 3.1 Primary Elimination Triggers / 主要淘汰觸發條件

A strategy **must be eliminated** if:

策略**必須被淘汰**如果：

| Criterion / 標準 | Threshold / 閾值 | Action / 行動 |
|------------------|------------------|---------------|
| Return after costs / 含成本後報酬 | < 0 (negative) / 負數 | ❌ Eliminate / 淘汰 |
| Median return / 中位數報酬 | < 0 (negative) / 負數 | ❌ Eliminate / 淘汰 |

### 3.2 Secondary Warning Signs / 次要警告訊號

Consider elimination if multiple occur:

如果多個同時發生，考慮淘汰：

| Warning / 警告 | Threshold / 閾值 | Severity / 嚴重性 |
|----------------|------------------|-------------------|
| Maximum drawdown / 最大回撤 | > 30% | High / 高 |
| Sharpe ratio / 夏普比率 | < 0.5 | Medium / 中 |
| Win rate / 勝率 | < 40% | Medium / 中 |
| Profit factor / 獲利因子 | < 1.0 | High / 高 |
| Consecutive losses / 連續虧損 | > 5 trades / 5 筆 | Medium / 中 |

### 3.3 Elimination Process / 淘汰流程

```
Identify trigger / 識別觸發條件
    ↓
Document evidence / 記錄證據
    ↓
Review against criteria / 對照標準審查
    ↓
Decision: Eliminate or Revise / 決定：淘汰或修正
    ↓
Update strategy status / 更新策略狀態
```

---

## 4. Evidence Quality Requirements / 證據品質要求

### 4.1 Data Requirements / 資料要求

| Aspect / 方面 | Requirement / 要求 | Rationale / 理由 |
|---------------|-------------------|------------------|
| Historical data length / 歷史資料長度 | ≥ 2 years / 2 年 | Capture different market regimes |
| Data granularity / 資料粒度 | Matches timeframe / 符合時間框架 | 4H strategies use 4H data |
| Data quality / 資料品質 | No gaps, verified / 無缺口，已驗證 | Ensure reliable backtests |
| Out-of-sample period / 樣本外期間 | ≥ 6 months / 6 個月 | Validate robustness |

### 4.2 Backtesting Standards / 回測標準

Minimum requirements for valid backtest:

有效回測的最低要求：

- [ ] Transaction costs included / 包含交易成本
- [ ] Slippage estimated / 估計滑點
- [ ] Realistic position sizing / 實際倉位規模
- [ ] Walk-forward analysis / 前向分析
- [ ] Monte Carlo simulation (optional) / 蒙地卡羅模擬（選填）

### 4.3 Statistical Significance / 統計顯著性

| Metric / 指標 | Minimum / 最低 | Preferred / 偏好 |
|---------------|----------------|------------------|
| Number of trades / 交易次數 | ≥ 100 | ≥ 300 |
| Confidence level / 信心水準 | 90% | 95% |
| P-value for edge / 優勢的 p 值 | < 0.10 | < 0.05 |

---

## 5. Overfitting Avoidance / 避免過度最佳化

### 5.1 Overfitting Warning Signs / 過度最佳化警告訊號

| Sign / 訊號 | Indicator / 指標 | Action / 行動 |
|-------------|------------------|---------------|
| Too many parameters / 太多參數 | > 5 optimized params | Simplify / 簡化 |
| Perfect in-sample fit / 完美樣本內配適 | 100% win rate | Suspect / 懷疑 |
| Poor out-sample performance / 樣本外表現差 | Sharpe drops > 50% | Reject / 拒絕 |
| Parameter sensitivity / 參數敏感性 | Small changes → big results | Robustness test / 穩健性測試 |
| Curve fitting / 曲線配適 | Rules match past exactly | Generalize / 一般化 |

### 5.2 Prevention Measures / 預防措施

1. **Parameter constraints / 參數限制**
   - Limit optimized parameters to ≤ 5
   - Use wide parameter ranges
   - Prefer robust parameter regions

2. **Cross-validation / 交叉驗證**
   - Split data: 70% train, 30% test
   - Use rolling window analysis
   - Validate across multiple time periods

3. **Simplicity preference / 簡單性偏好**
   - Fewer rules beat complex rules
   - Occam's razor applies
   - Prefer interpretable strategies

### 5.3 Robustness Testing / 穩健性測試

Before accepting a strategy:

接受策略前：

```
1. Parameter sweep test / 參數掃描測試
   - Vary each parameter ±20%
   - Strategy should remain profitable

2. Market regime test / 市場機制測試
   - Test in bull, bear, sideways markets
   - Performance should not collapse

3. Asset class test / 資產類別測試
   - Test on related assets
   - Edge should persist

4. Time horizon test / 時間跨度測試
   - Test on different timeframes
   - Logic should hold
```

---

## 6. Stability and Reusability / 穩定性與可重用性

### 6.1 Stability Metrics / 穩定性指標

| Metric / 指標 | Target / 目標 | Measurement / 測量 |
|---------------|---------------|--------------------|
| Consistency / 一致性 | Monthly returns positive > 60% | Track record / 追蹤記錄 |
| Volatility / 波動性 | Monthly return std < 15% | Standard deviation / 標準差 |
| Recovery time / 恢復時間 | Max drawdown recovery < 6 months | Historical / 歷史 |
| Parameter stability / 參數穩定性 | Top 3 parameter sets similar | Sensitivity analysis / 敏感性分析 |

### 6.2 Reusability Criteria / 可重用性標準

A strategy is **reusable** if:

策略**可重用**如果：

- [ ] Logic is clearly documented / 邏輯有清晰文件
- [ ] Parameters are not over-optimized / 參數未過度最佳化
- [ ] Works across similar assets / 在相似資產上有效
- [ ] Works across different timeframes / 在不同時間框架上有效
- [ ] Has been validated out-of-sample / 已通過樣本外驗證

### 6.3 Documentation Requirements / 文件要求

Every strategy must document:

每個策略必須記錄：

```markdown
## Strategy Name / 策略名稱

### Logic / 邏輯
- Entry conditions / 進場條件
- Exit conditions / 出場條件
- Risk management / 風險管理

### Parameters / 參數
- Optimized values / 最佳化數值
- Robust ranges / 穩健範圍
- Constraints / 限制

### Performance / 績效
- In-sample results / 樣本內結果
- Out-sample results / 樣本外結果
- Risk metrics / 風險指標

### Elimination Criteria / 淘汰標準
- When to stop using / 何時停止使用
- Warning signs / 警告訊號
```

---

## 7. Recommended Evaluation Questions / 建議評估問題

### 7.1 Before Starting Research / 開始研究前

1. **What is the core hypothesis?** / 核心假設是什麼？
   - Is it based on market structure or data mining? / 基於市場結構還是資料挖掘？

2. **What is the edge?** / 優勢是什麼？
   - Why should this work? / 為什麼這應該有效？
   - Who is on the other side? / 誰在對立面？

3. **What is the risk?** / 風險是什麼？
   - Maximum loss scenario? / 最大損失情境？
   - When does it fail? / 何時會失效？

### 7.2 During Development / 開發期間

4. **Is it too complex?** / 是否太複雜？
   - Can I explain it simply? / 我能簡單解釋嗎？
   - Are there unnecessary rules? / 有不必要的規則嗎？

5. **Is it overfitted?** / 是否過度最佳化？
   - Too many parameters? / 太多參數？
   - Perfect in-sample results? / 完美的樣本內結果？

6. **Is it robust?** / 是否穩健？
   - Works with parameter variations? / 參數變化時仍有效？
   - Works across different periods? / 不同時期都有效？

### 7.3 Before Deployment / 部署前

7. **Has it been validated?** / 是否已驗證？
   - Out-of-sample test passed? / 樣本外測試通過？
   - Walk-forward analysis completed? / 前向分析完成？

8. **Is risk acceptable?** / 風險可接受嗎？
   - Max drawdown within limits? / 最大回撤在限制內？
   - Position sizing appropriate? / 倉位規模適當？

9. **Is it maintainable?** / 可維護嗎？
   - Clear documentation? / 清晰的文件？
   - Monitoring in place? / 監控到位？

---

## 8. Relationship to BTC/ETH Strategy Work / 與 BTC/ETH 策略工作的關係

### 8.1 Current Active Projects / 目前進行中專案

| Project / 專案 | Status / 狀態 | Criteria Applied / 應用的標準 |
|----------------|---------------|------------------------------|
| BTC 4H Strategy Filter / BTC 4H 策略篩選 | Active research / 進行中研究 | Elimination criteria / 淘汰標準 |
| BTC 1D MR Strategy Monitor / BTC 1D MR 策略監控 | Maintenance / 維護 | Stability metrics / 穩定性指標 |
| TSMC MR Strategy / TSMC MR 策略 | Maintenance / 維護 | Stability metrics / 穩定性指標 |

### 8.2 Application Guidelines / 應用指南

**For New Strategies** / 對於新策略：
1. Apply selection criteria / 應用選擇標準
2. Define elimination triggers upfront / 預先定義淘汰觸發條件
3. Document all parameters / 記錄所有參數
4. Validate out-of-sample / 樣本外驗證

**For Existing Strategies** / 對於現有策略：
1. Monitor against elimination criteria / 依淘汰標準監控
2. Review stability metrics regularly / 定期審查穩定性指標
3. Update documentation / 更新文件
4. Archive if eliminated / 如被淘汰則歸檔

### 8.3 Strategy Card Template / 策略卡模板

Each strategy should have a "Strategy Card" following this format:

每個策略應該有一個「策略卡」，遵循以下格式：

```markdown
# Strategy Card: [Name]

## Basic Info / 基本資訊
- Asset: BTCUSDT / ETHUSDT
- Timeframe: 4H / 1D
- Type: MR / Breakout / Trend
- Status: Active / Monitoring / Eliminated

## Performance / 績效
- Return after costs: X%
- Median return: X%
- Max drawdown: X%
- Sharpe ratio: X

## Risk Control / 風險控制
- Position size: X%
- Stop loss: X%
- Max positions: X

## Elimination Triggers / 淘汰觸發條件
- Return after costs < 0
- Median return < 0
- [Other criteria]

## Notes / 備註
- [Research notes]
```

---

## Summary / 摘要

| Category / 類別 | Key Principle / 核心原則 |
|-----------------|-------------------------|
| **Selection** / 選擇 | Clear hypothesis, robust logic / 清晰的假設，穩健的邏輯 |
| **Elimination** / 淘汰 | Strict cost-aware criteria / 嚴格的成本意識標準 |
| **Evidence** / 證據 | High quality, statistically significant / 高品質，統計顯著 |
| **Overfitting** / 過度最佳化 | Prevention through simplicity / 透過簡單性預防 |
| **Stability** / 穩定性 | Consistent performance across conditions / 跨情境的一致表現 |

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `README.md` - System overview / 系統概覽
- `USER.md` - User preferences and active projects / 使用者偏好與進行中專案
- `research/risk_control.md` - Risk management principles / 風險管理原則
