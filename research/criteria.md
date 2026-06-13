# Research Criteria
# 研究標準

**Version**: 1.1.0  
**版本**: 1.1.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define standardized criteria for selecting, evaluating, and eliminating trading strategies in quantitative research. These criteria ensure research quality, prevent overfitting, and maintain focus on robust, reusable findings.

定義量化研究中選擇、評估和淘汰交易策略的標準化準則。這些標準確保研究品質、防止過度最佳化，並保持對穩健、可重用發現的關注。

---

## 2. Permanent Criteria vs Current Focus / 永久標準與當前重點

### 2.1 Permanent Criteria (Long-term Valid) / 永久標準（長期有效）

These criteria apply to **all** research regardless of market conditions or current priorities:

這些標準適用於**所有**研究，無論市場條件或當前優先級：

| Category / 類別 | Principle / 原則 |
|-----------------|-----------------|
| **Selection** / 選擇 | Clear hypothesis, testable rules / 清晰假設，可測試規則 |
| **Elimination** / 淘汰 | Negative returns after costs / 含成本後報酬為負 |
| **Evidence** / 證據 | Sufficient data, statistical significance / 足夠資料，統計顯著 |
| **Overfitting** / 過度最佳化 | ≤ 5 parameters, validated OOS / ≤ 5 參數，樣本外驗證 |
| **Stability** / 穩定性 | Robust across market regimes / 跨市場機制穩健 |

### 2.2 Current Focus (Subject to Change) / 當前重點（可能變更）

| Aspect / 方面 | Current Setting / 當前設定 | Notes / 備註 |
|---------------|---------------------------|--------------|
| Primary instruments / 主要標的 | BTCUSDT, ETHUSDT | May expand to other assets / 可能擴展至其他資產 |
| Primary timeframe / 主要時間框架 | 4H | Based on current research / 基於當前研究 |
| Strategy priority / 策略優先級 | Mean Reversion > Breakout | Subject to review / 需定期檢討 |

### 2.3 Decision: Permanent vs Focus / 決定：永久 vs 重點

**Permanent** if: / **永久**如果：
- Applies to all strategies / 適用於所有策略
- Based on risk management principles / 基於風險管理原則
- Valid across market cycles / 跨市場週期有效

**Current Focus** if: / **當前重點**如果：
- Specific to current research direction / 特定於當前研究方向
- May change with market conditions / 可能隨市場條件變更
- Defined by user preference / 由使用者偏好定義

---

## 3. Selection Criteria / 選擇標準

### 3.1 Minimum Viable Criteria / 最低可行標準

Before starting research, ensure:

開始研究前，確保：

- [ ] Clear hypothesis / 清晰的假設
- [ ] Defined entry/exit rules / 定義進出場規則
- [ ] Risk management parameters / 風險管理參數
- [ ] Backtesting capability / 回測能力
- [ ] Out-of-sample validation plan / 樣本外驗證計畫

### 3.2 Instrument and Timeframe / 標的與時間框架

| Instrument / 標的 | Timeframe / 時間框架 | Status / 狀態 |
|-------------------|---------------------|---------------|
| BTCUSDT | 4H | **Current focus** / 當前重點 |
| BTCUSDT | 1D | Active / 進行中 |
| ETHUSDT | 4H | **Current focus** / 當前重點 |
| ETHUSDT | 1D | Planned / 計畫中 |

---

## 4. Elimination Criteria / 淘汰標準

### 4.1 Hard Elimination (Immediate) / 硬性淘汰（立即）

| Criterion / 標準 | Threshold / 閾值 | Action / 行動 |
|------------------|------------------|---------------|
| Return after costs / 含成本後報酬 | < 0 | ❌ Eliminate / 淘汰 |
| Median return / 中位數報酬 | < 0 | ❌ Eliminate / 淘汰 |

### 4.2 Warning Thresholds (Review Required) / 警告閾值（需檢討）

| Warning / 警告 | Threshold / 閾值 | Severity / 嚴重性 |
|----------------|------------------|-------------------|
| Maximum drawdown / 最大回撤 | > 30% | High / 高 |
| Sharpe ratio / 夏普比率 | < 0.5 | Medium / 中 |
| Win rate / 勝率 | < 40% | Medium / 中 |
| Profit factor / 獲利因子 | < 1.0 | High / 高 |

---

## 5. Monitor / Pause / Eliminate Decision Layers / 監控、暫停、淘汰決策分層

### 5.1 Decision Framework / 決策框架

```
Strategy Status / 策略狀態
    │
    ├── Active / 進行中 ─── Normal monitoring / 正常監控
    │
    ├── Warning / 警告 ───── Increased scrutiny / 增加審查
    │   └── (Soft triggers hit / 觸及軟性觸發)
    │
    ├── Paused / 暫停 ────── Stop new entries / 停止新進場
    │   └── (Review required / 需要檢討)
    │
    └── Eliminated / 淘汰 ── Archive / 歸檔
        └── (Hard triggers hit / 觸及硬性觸發)
```

### 5.2 Status Definitions / 狀態定義

| Status / 狀態 | Definition / 定義 | Action / 行動 |
|---------------|-------------------|---------------|
| **Active** / 進行中 | All criteria met / 所有標準達成 | Normal operation / 正常運作 |
| **Monitor** / 監控 | Warning signs present / 存在警告訊號 | Increase monitoring frequency / 增加監控頻率 |
| **Pause** / 暫停 | Review required / 需要檢討 | No new entries, review strategy / 不新進場，檢討策略 |
| **Eliminate** / 淘汰 | Hard criteria failed / 硬性標準失敗 | Archive, stop trading / 歸檔，停止交易 |

### 5.3 Status Transitions / 狀態轉換

| From / 從 | To / 到 | Trigger / 觸發條件 |
|-----------|---------|-------------------|
| Active | Monitor | 2+ warning thresholds / 2+ 警告閾值 |
| Monitor | Pause | User decision or severe warning / 使用者決定或嚴重警告 |
| Pause | Active | Review passed, conditions restored / 檢討通過，條件恢復 |
| Pause | Eliminate | Hard criteria confirmed / 硬性標準確認 |
| Active | Eliminate | Hard elimination criteria / 硬性淘汰標準 |

---

## 6. Evidence Quality Requirements / 證據品質要求

### 6.1 Data Requirements / 資料要求

| Aspect / 方面 | Requirement / 要求 |
|---------------|-------------------|
| Historical data / 歷史資料 | ≥ 2 years / 2 年 |
| Data granularity / 資料粒度 | Matches strategy timeframe / 符合策略時間框架 |
| Data quality / 資料品質 | No gaps, verified / 無缺口，已驗證 |
| Out-of-sample / 樣本外 | ≥ 6 months / 6 個月 |

### 6.2 Backtesting Requirements / 回測要求

- [ ] Transaction costs included / 包含交易成本
- [ ] Slippage estimated / 估計滑點
- [ ] Realistic position sizing / 實際倉位規模
- [ ] Walk-forward analysis / 前向分析

### 6.3 Statistical Requirements / 統計要求

| Metric / 指標 | Minimum / 最低 |
|---------------|----------------|
| Number of trades / 交易次數 | ≥ 100 |
| Confidence level / 信心水準 | 90% |

---

## 7. Overfitting Avoidance / 避免過度最佳化

### 7.1 Constraints / 限制

| Constraint / 限制 | Rule / 規則 |
|-------------------|-------------|
| Parameters / 參數 | ≤ 5 optimized / ≤ 5 最佳化 |
| Parameter range / 參數範圍 | Wide ranges preferred / 偏好寬範圍 |
| Validation / 驗證 | Out-of-sample required / 需要樣本外 |

### 7.2 Warning Signs / 警告訊號

| Sign / 訊號 | Action / 行動 |
|-------------|---------------|
| Win rate > 70% / 勝率 > 70% | Suspect overfitting / 懷疑過度最佳化 |
| Perfect equity curve / 完美權益曲線 | Reject / 拒絕 |
| No OOS data / 無樣本外資料 | Require OOS test / 要求樣本外測試 |

### 7.3 Robustness Testing / 穩健性測試

Before accepting:

- Parameter variation ±20% / 參數變化 ±20%
- Cross-market regime test / 跨市場機制測試
- Cross-asset test / 跨資產測試

---

## 8. Stability and Reusability / 穩定性與可重用性

### 8.1 Stability Metrics / 穩定性指標

| Metric / 指標 | Target / 目標 |
|---------------|---------------|
| Monthly positive / 月正報酬 | > 60% |
| Max drawdown recovery / 最大回撤恢復 | < 6 months / 6 個月 |
| Parameter stability / 參數穩定性 | Top 3 sets similar / 前 3 組相似 |

### 8.2 Reusability Checklist / 可重用性檢查清單

- [ ] Logic documented / 邏輯已記錄
- [ ] Parameters not over-optimized / 參數未過度最佳化
- [ ] Cross-asset validated / 跨資產驗證
- [ ] Out-of-sample passed / 樣本外通過

---

## 9. Application to Active Projects / 應用於進行中專案

### 9.1 Project Status Overview / 專案狀態概覽

| Project / 專案 | Current Status / 當前狀態 | Criteria Applied / 應用標準 |
|----------------|---------------------------|----------------------------|
| BTC 4H Strategy Filter | Active research | Selection, Elimination |
| BTC 1D MR Monitor | Maintenance | Monitor/Pause layers |
| TSMC MR Strategy | Maintenance | Monitor/Pause layers |

### 9.2 For New Strategies / 對於新策略

1. Check against selection criteria / 檢查選擇標準
2. Define elimination triggers upfront / 預先定義淘汰觸發
3. Set up monitoring thresholds / 設定監控閾值
4. Plan status transitions / 規劃狀態轉換

### 9.3 For Existing Strategies / 對於現有策略

1. Regular review against criteria / 定期依標準檢討
2. Monitor for warning signs / 監控警告訊號
3. Document status changes / 記錄狀態變更
4. Archive if eliminated / 如淘汰則歸檔

---

## Summary / 摘要

| Layer / 層級 | Key Principle / 核心原則 |
|--------------|-------------------------|
| **Permanent** / 永久 | Hypothesis, risk management, simplicity / 假設、風險管理、簡單性 |
| **Current Focus** / 當前重點 | BTC/ETH 4H, MR priority / BTC/ETH 4H，MR 優先 |
| **Elimination** / 淘汰 | Hard (immediate) vs Soft (review) / 硬性（立即）vs 軟性（檢討）|
| **Status Layers** / 狀態層級 | Active → Monitor → Pause → Eliminate |
| **Evidence** / 證據 | Data quality, OOS validation / 資料品質、樣本外驗證 |
| **Overfitting** / 過度最佳化 | ≤ 5 params, robustness test / ≤ 5 參數、穩健性測試 |

---

**Note**: Strategy Card Template has been moved to `templates/strategy_card_template.md` (T-018).

**注意**: 策略卡模板已移至 `templates/strategy_card_template.md` (T-018)。

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `research/risk_control.md` - Risk management principles / 風險管理原則
- `templates/strategy_card_template.md` - Strategy documentation template / 策略文件模板
- `README.md` - System overview / 系統概覽
