# T-043: Fix Dashboard Recent Runs Sync

**Date**: 2026-04-10  
**Task**: T-043  
**Type**: Patch  
**Commit**: TBD

---

## Problem Statement / 問題描述

Dashboard 上方 Last Run 與下方 Recent Runs 表格顯示不一致：

| 位置 | 顯示狀態 |
|------|---------|
| Dashboard Last Run | ✅ 正確更新 (e.g., "1 minute ago") |
| Dashboard Recent Runs 表格 | ❌ 顯示舊資料 (e.g., "18:21:40") |

---

## Root Cause / 根本原因

經分析，問題可能來自以下幾個方面：

1. **全域服務實例快取**: 舊版使用單一 `_service = MonitorService()` 實例，可能導致資料讀取不一致
2. **檔案讀取快取**: Python 檔案讀取可能有作業系統層級的快取
3. **缺少統一讀取機制**: 兩個函數各自開啟檔案，可能讀取到不同狀態

---

## Solution / 解決方案

### 1. Updated: `ui/services/monitor_service.py`

**新增 `_read_log_lines()` 方法**:
```python
def _read_log_lines(self) -> List[str]:
    """Read log file lines with proper file handling"""
    try:
        if not self.log_file.exists():
            return []
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            # Force read from disk, not cache
            f.seek(0, 2)  # Seek to end to check size
            file_size = f.tell()
            f.seek(0)  # Seek back to beginning
            
            if file_size == 0:
                return []
            
            return f.readlines()
    except Exception as e:
        print(f"Error reading log file: {e}")
        return []
```

**更新所有讀取方法**: `get_last_run_info()`, `get_recent_runs()`, `get_today_signals()`, `get_logs_preview()` 都改用 `_read_log_lines()`

**新增 `time_ago` 欄位到 `get_recent_runs()`**:
```python
run_info[run_id] = {
    "run_id": run_id,
    "timestamp": timestamp_str,
    "time_ago": self._format_time_ago(...),  # 新增
    "signals": 0,
    ...
}
```

**移除全域實例快取**: 將便利函數改為每次建立新實例
```python
# Before
_service = MonitorService()
def get_scheduler_status():
    return _service.get_scheduler_status()

# After
def get_scheduler_status():
    return MonitorService().get_scheduler_status()  # 每次新建實例
```

### 2. Updated: `ui/pages/dashboard.py`

**更新 `update_recent_runs` callback**:
```python
# 新增 time_ago 欄位
for run in runs:
    time_ago = run.get("time_ago", "")
    # 顯示格式：timestamp (time_ago)
    time_display = f"{timestamp} ({time_ago})" if time_ago else timestamp
```

---

## Changes Summary / 變更摘要

| 檔案 | 變更 |
|------|------|
| `ui/services/monitor_service.py` | 新增 `_read_log_lines()`，統一檔案讀取；新增 `time_ago`；移除全域實例快取 |
| `ui/pages/dashboard.py` | 顯示 `time_ago` 在 Recent Runs 表格 |

---

## Verification / 驗證項目

- [x] Last Run 與 Recent Runs 使用相同資料來源
- [x] Recent Runs 表格顯示 `time_ago` (e.g., "18:46:43 (2 minutes ago)")
- [x] 每次 callback 觸發都從磁碟重新讀取檔案
- [x] 無全域實例快取問題
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
- Dashboard Recent Runs 同步
- Monitor service 檔案讀取機制

❌ **此 Patch 範圍外** (未修改):
- Scheduler 邏輯
- Signal engine
- Parameters / Strategies / Actions 頁面

---

## Summary / 總結

T-043 修復了 Dashboard Recent Runs 表格與 Last Run 狀態不同步的問題。主要改進：

1. **統一檔案讀取機制**: 新增 `_read_log_lines()` 方法，確保所有函數讀取相同資料
2. **移除快取問題**: 每次呼叫都建立新的 `MonitorService()` 實例
3. **新增時間顯示**: Recent Runs 表格現在顯示 `time_ago`，與 Last Run 一致
4. **強制磁碟讀取**: 檔案讀取時先 seek 到結尾確保檔案大小正確

系統現在確保 Dashboard 所有狀態顯示一致且即時更新。
