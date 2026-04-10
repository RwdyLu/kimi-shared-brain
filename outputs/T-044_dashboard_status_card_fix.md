# T-044: Fix Dashboard System Status Card Sync

**Date**: 2026-04-10  
**Task**: T-044  
**Type**: Patch  
**Commit**: TBD

---

## Problem Statement / 問題描述

Dashboard 顯示狀態不一致：

| 位置 | 顯示狀態 |
|------|---------|
| Last Run | ✅ 22 seconds ago |
| Recent Runs | ✅ 已更新到最新 |
| System Status 卡片 | ❌ Stopped / Stale PID |

---

## Root Cause / 根本原因

**PID 檔案錯位問題**:
- **PID 檔案內容**: `119391` (bash process，啟動後已結束)
- **實際 Python Scheduler**: `119392` (仍在運行並記錄 logs)

**問題流程**:
1. Scheduler 使用 bash nohup 啟動
2. PID 檔案記錄的是 bash process ID (119391)
3. bash 命令執行完畢後結束，但 Python scheduler (119392) 繼續在背景運行
4. `get_scheduler_status()` 檢查 PID 119391 發現不存在 → 顯示 "Stale PID"
5. 但 scheduler 實際仍在運行並記錄新的 runs

---

## Solution / 解決方案

### Updated: `ui/services/monitor_service.py`

**新增 `_is_recent_run_active()` 方法**:
```python
def _is_recent_run_active(self, max_minutes: int = 10) -> bool:
    """
    Check if there's a recent run in the log (within max_minutes)
    檢查日誌中是否有最近的 run（在 max_minutes 分鐘內）
    """
    # Parse last "Run #X completed" timestamp
    # Check if within max_minutes
    # Return True if recent activity found
```

**更新 `get_scheduler_status()` 方法**:

Before:
```python
def get_scheduler_status(self):
    # Only check PID file
    if pid_file.exists():
        if os.kill(pid, 0) succeeds:
            return "Running"
        else:
            return "Stale PID"
```

After:
```python
def get_scheduler_status(self):
    # Primary check: PID file
    if pid_file.exists():
        if os.kill(pid, 0) succeeds:
            return "Running"
        # PID check failed, fall through to secondary check
    
    # Secondary check: Recent log activity
    if _is_recent_run_active(max_minutes=10):
        return {
            "running": True,
            "pid": "Unknown (from log)",
            "status_text": "Running (active) / 執行中 (活躍)"
        }
    
    # No PID and no recent activity
    return "Stopped / Stale PID"
```

**檢測邏輯**:
1. **主要檢查**: PID 檔案存在且 process 可signal → Running
2. **次要檢查**: PID 檢查失敗，但日誌中有 10 分鐘內的 run → Running (active)
3. **最終判斷**: 無 PID 且無近期日誌 → Stopped / Stale PID

---

## Changes Summary / 變更摘要

| 檔案 | 變更 |
|------|------|
| `ui/services/monitor_service.py` | 新增 `_is_recent_run_active()`，更新 `get_scheduler_status()` 支援雙重檢測 |

---

## Verification / 驗證項目

- [x] PID 正常時顯示 "Running / 執行中"
- [x] PID 失效但日誌活躍時顯示 "Running (active) / 執行中 (活躍)"
- [x] 無 PID 且無日誌時顯示 "Stopped / 已停止"
- [x] 與 Last Run / Recent Runs 狀態一致
- [x] 向後相容：所有公開 API 不變

---

## Alert-Only / 僅提醒設計

✅ **維持不變**

- 無交易 API 連接
- 無自動下單邏輯
- 僅狀態顯示同步

---

## Scope / 範圍確認

✅ **此 Patch 範圍內**:
- Dashboard System Status 卡片同步
- Scheduler 狀態檢測邏輯

❌ **此 Patch 範圍外** (未修改):
- Scheduler 啟動邏輯 (PID 檔案產生方式)
- Signal engine
- Parameters / Strategies / Actions 頁面

---

## Long-term Fix / 長期修復建議

此 patch 是治標方案。治本方案應修正 scheduler 啟動腳本，確保 PID 檔案記錄正確的 Python process ID：

```bash
# 目前問題方式（記錄 bash PID）
nohup python3 ... &
echo $! > .monitor.pid  # 這是 bash 的 $!，不是 python 的

# 建議修正方式（記錄 Python PID）
nohup python3 ... &
PYTHON_PID=$!
echo $PYTHON_PID > .monitor.pid
```

或使用更穩健的方式（如 pgrep 檢查實際 process）。

---

## Summary / 總結

T-044 修復了 Dashboard System Status 卡片與實際 scheduler 狀態不一致的問題。主要改進：

1. **雙重檢測機制**: 不僅依賴 PID 檔案，同時檢查日誌活動
2. **容錯設計**: 即使 PID 檔案過期，只要日誌顯示近期有活動，仍判定為 Running
3. **向後相容**: 原有 PID 檢測邏輯優先，僅在失敗時啟用次要檢測

系統現在能正確顯示 scheduler 狀態，不再出現「Last Run 幾十秒前但 Status 卻是 Stopped」的矛盾。
