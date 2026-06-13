# T-042: Fix Navbar Status Badge Sync

**Date**: 2026-04-10  
**Task**: T-042  
**Type**: Patch  
**Commit**: TBD

---

## Problem Statement / 問題描述

UI 頂部 navbar 的狀態 badge 與 Dashboard/System 頁面顯示不一致：

| 位置 | 顯示狀態 |
|------|---------|
| Dashboard 主狀態 | ✅ Running (PID 89413, Last Run 幾十秒前) |
| System 頁面 | ✅ Running |
| Navbar 右上角 badge | ❌ Stopped |

根本原因：navbar 與 Dashboard 使用不同的資料來源檢查 scheduler 狀態。

---

## Root Cause / 根本原因

**Navbar** (`ui/app.py`):
- 直接讀取 PID 檔案並使用 `os.kill()` 檢查
- 獨立實作，未使用統一的 service layer

**Dashboard** (`ui/pages/dashboard.py`):
- 使用 `ui.services.monitor_service.get_scheduler_status()`
- 統一的 service layer，包含完整狀態資訊

兩者雖然邏輯相似，但因為實作分離，可能因以下原因導致不一致：
1. 路徑解析差異
2. 錯誤處理差異
3. 快取或時序問題

---

## Solution / 解決方案

統一兩者使用相同的資料來源：`ui.services.monitor_service.get_scheduler_status()`

### Changes Made / 變更內容

**File: `ui/app.py`**

1. **新增 import**:
   ```python
   from ui.services.monitor_service import get_scheduler_status
   ```

2. **更新 `update_navbar_status` callback**:
   
   Before:
   ```python
   def update_navbar_status(n):
       try:
           import os
           pid_file = PROJECT_ROOT / ".monitor.pid"
           if pid_file.exists():
               with open(pid_file, 'r') as f:
                   pid = f.read().strip()
                   try:
                       os.kill(int(pid), 0)
                       return dbc.Badge("🟢 Running", color="success", className="me-2")
                   except (OSError, ValueError):
                       pass
           return dbc.Badge("🔴 Stopped", color="danger", className="me-2")
       except Exception:
           return dbc.Badge("⚪ Unknown", color="secondary", className="me-2")
   ```
   
   After:
   ```python
   def update_navbar_status(n):
       try:
           # Use the same source as Dashboard/System pages
           status = get_scheduler_status()
           
           if status.get("running"):
               return dbc.Badge("🟢 Running", color="success", className="me-2")
           else:
               return dbc.Badge("🔴 Stopped", color="danger", className="me-2")
       except Exception:
           return dbc.Badge("⚪ Unknown", color="secondary", className="me-2")
   ```

---

## Benefits / 效益

1. **一致性**: Navbar 與 Dashboard/System 使用完全相同的狀態來源
2. **可維護性**: 統一使用 service layer，未來修改只需改一處
3. **除錯便利**: 狀態邏輯集中於 `monitor_service.py`
4. **無功能擴散**: 僅修改 navbar callback，不影響其他功能

---

## Verification / 驗證

驗證項目：
- [x] Dashboard 顯示 Running 時，navbar 也顯示 Running
- [x] Dashboard 顯示 Stopped 時，navbar 也顯示 Stopped
- [x] Badge 顏色正確（Running=green, Stopped=red, Unknown=gray）
- [x] 自動刷新正常運作（30秒間隔）

---

## Files Modified / 修改檔案

| 檔案 | 變更 |
|------|------|
| `ui/app.py` | 匯入 `get_scheduler_status`，更新 `update_navbar_status` callback |

---

## Scope / 範圍確認

✅ **此 Patch 範圍內**:
- Navbar status badge 同步
- 統一使用 monitor_service

❌ **此 Patch 範圍外** (未修改):
- Scheduler 邏輯
- Signal engine
- Strategies / Parameters / Actions 頁面
- 交易邏輯

---

## Alert-Only / 僅提醒設計

✅ **維持不變**

- 無交易 API 連接
- 無自動下單邏輯
- 僅狀態顯示同步

---

## Summary / 總結

T-042 成功修復 navbar status badge 與 Dashboard/System 狀態不一致的問題。透過統一使用 `get_scheduler_status()` service，確保所有 UI 元件顯示相同的 scheduler 狀態。
