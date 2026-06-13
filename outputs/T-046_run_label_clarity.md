# T-046: Clarify Session Run vs Historical Run Labels

**Date**: 2026-04-10  
**Task**: T-046  
**Type**: Patch  
**Commit**: TBD

---

## Problem Statement / 問題描述

Dashboard 顯示造成使用者混淆：

| 位置 | 顯示 |
|------|------|
| 上方 Last Run | #33 |
| 下方 Recent Runs | #890, #889, #888... |

使用者可能誤以為兩者是同一套編號系統，實際上：
- 上方顯示 current session 的最新 run
- 下方顯示來自 log 的歷史 runs

---

## Root Cause / 根本原因

**來源分析**:
- 兩者都從 `scheduler.log` 讀取相同的 run_id
- 但 UI 標示未清楚區分兩者的不同語意
- 使用者看到不同數字範圍時產生困惑

---

## Solution / 解決方案

### 更新: `ui/pages/dashboard.py`

**1. Last Run Card 標題強化**:

Before:
```python
dbc.CardHeader("Last Run / 最後執行")
```

After:
```python
dbc.CardHeader([
    "Last Run (Live) / 最後執行 (即時)",
    html.Small(" 📍Current Session", className="text-muted ms-2")
])
```

**2. Recent Runs 區塊標題強化**:

Before:
```python
html.H4("Recent Runs / 最近執行", className="mt-4 mb-3")
```

After:
```python
html.H4([
    "Recent Run History / 近期執行記錄",
    html.Small(" 📜From Log", className="text-muted ms-2")
], className="mt-4 mb-3"),
html.P("Historical runs from scheduler log / 來自排程器日誌的歷史記錄", 
       className="text-muted small mb-2")
```

---

## Changes Summary / 變更摘要

| 檔案 | 變更 |
|------|------|
| `ui/pages/dashboard.py` | 更新 Last Run 與 Recent Runs 標題與說明文字 |

---

## UI Display / 顯示效果

### Last Run Card / 最後執行卡片
```
┌─────────────────────────────────────┐
│ Last Run (Live) / 最後執行 (即時) 📍Current Session │
├─────────────────────────────────────┤
│ #896 • 2 minutes ago                │
│ No signals / 無訊號                 │
└─────────────────────────────────────┘
```

### Recent Run History Section / 近期執行記錄區塊
```
Recent Run History / 近期執行記錄 📜From Log
Historical runs from scheduler log / 來自排程器日誌的歷史記錄

┌────────────────────────────────────────────────────────┐
│ Run  │ Time / 時間       │ Signals / 訊號 │ Symbols / 標的 │
├────────────────────────────────────────────────────────┤
│ #896 │ 19:56:51 (2m ago) │ 0              │ BTC ETH        │
│ #895 │ 19:51:50 (7m ago) │ 0              │ BTC ETH        │
│ ...  │ ...               │ ...            │ ...            │
└────────────────────────────────────────────────────────┘
```

---

## Label Meanings / 標籤語意

| 標籤 | 意義 |
|------|------|
| 📍Current Session | 當前 session 的最新執行狀態 |
| 📜From Log | 從排程器日誌讀取的歷史記錄 |

---

## Verification / 驗證項目

- [x] Last Run 卡片顯示 "(Live)" 與 "📍Current Session"
- [x] Recent Runs 區塊顯示 "History" 與 "📜From Log"
- [x] 新增說明文字解釋資料來源
- [x] 兩者編號差異現在有明確語意說明

---

## Alert-Only / 僅提醒設計

✅ **維持不變**

- 無交易 API 連接
- 無自動下單邏輯
- 僅 UI 文案清晰度優化

---

## Scope / 範圍確認

✅ **此 Patch 範圍內**:
- Dashboard UI 標示文案

❌ **此 Patch 範圍外** (未修改):
- Scheduler 邏輯
- Run 計數規則
- Signal engine

---

## Summary / 總結

T-046 透過明確的 UI 標示解決了使用者對 run 編號的混淆：

1. **Last Run (Live)**: 標示為 "Current Session"，強調這是即時狀態
2. **Recent Run History**: 標示為 "From Log"，強調這是歷史記錄
3. **說明文字**: 新增副標題解釋資料來源

即使兩者顯示不同範圍的編號（如 #33 vs #890+），使用者現在能清楚理解這是不同語意的資料呈現。
