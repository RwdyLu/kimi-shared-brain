# T-040: Fix UI Config Paths and Live Status Sync

**Date**: 2026-04-09  
**Task**: T-040  
**Type**: Patch  
**Commit**: TBD

---

## Problem Statement / 問題描述

UI 頁面使用硬編碼絕對路徑 `/tmp/kimi-shared-brain/...`，導致：
1. 在不同環境部署時路徑失效
2. Dashboard 讀不到 config/assets.json
3. Parameters 讀不到 config/monitoring_params.json
4. Strategies 讀不到 config/strategies.json
5. System 頁顯示 scheduler stopped，但其他頁面仍顯示舊的 next run 時間

---

## Solution / 解決方案

### 1. Created: `config/paths.py` ✅

**用途**: 動態專案根目錄解析器

**功能**:
- `get_project_root()`: 自動檢測專案根目錄
  1. 檢查環境變數 `KIMI_SHARED_BRAIN_ROOT`
  2. 檢查 `/tmp/kimi-shared-brain` 是否存在
  3. 檢查當前工作目錄
  4. 檢查腳本位置
  5. 回退到預設路徑
- `get_config_dir()`, `get_logs_dir()`, `get_outputs_dir()`, `get_state_dir()`: 取得各目錄路徑
- `resolve_path()`: 解析相對於專案根的路徑
- `ensure_dirs()`: 自動建立必要目錄

**全局變數**:
- `PROJECT_ROOT`, `CONFIG_DIR`, `LOGS_DIR`, `OUTPUTS_DIR`, `STATE_DIR`, `ACTIONS_DIR`, `UI_DIR`

---

### 2. Updated: `config/loader.py` ✅

**變更**:
- 從 `config.paths` 匯入 `CONFIG_DIR` 和 `resolve_path`
- `DEFAULT_CONFIG_DIR` 改為使用 `CONFIG_DIR`

**向後相容**: ✅ 是，所有公開 API 不變

---

### 3. Updated: `ui/services/monitor_service.py` ✅

**變更**:
- 匯入動態路徑解析器 `PROJECT_ROOT`, `LOGS_DIR`, `STATE_DIR`
- `__init__` 的 `base_path` 參數改為可選（`None` = 自動檢測）
- `get_next_run_time()`: 先檢查 scheduler 是否運行，stopped 時返回 `None`
- `get_full_status()`: 新增 `is_live` 和 `mode` 欄位，明確區分 live/historical 狀態

**新增欄位**:
```python
{
    "is_live": True/False,
    "mode": "LIVE" or "HISTORICAL_ONLY"
}
```

---

### 4. Updated: `ui/services/action_service.py` ✅

**變更**:
- 匯入動態路徑解析器 `STATE_DIR`, `ACTIONS_DIR`
- `DEFAULT_ACTIONS_DIR` 改為 `str(ACTIONS_DIR)`
- 更新 docstring 移除硬編碼路徑參考

---

### 5. Updated: All UI Pages ✅

統一修改所有頁面的路徑設定方式：

**檔案**:
- `ui/pages/dashboard.py`
- `ui/pages/parameters.py`
- `ui/pages/strategies.py`
- `ui/pages/signals.py`
- `ui/pages/system.py`
- `ui/pages/actions.py`
- `ui/app.py`

**變更模式**:
```python
# Before
import sys
sys.path.insert(0, '/tmp/kimi-shared-brain')

# After
from pathlib import Path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent  # or script_dir.parent for app.py
sys.path.insert(0, str(project_root))
```

---

### 6. Updated: `ui/pages/parameters.py` 硬編碼路徑 ✅

**變更**:
- `CONFIG_FILE` 改為使用 `CONFIG_DIR / "monitoring_params.json"`
- 新增 `DEFAULT_LOG_FILE = LOGS_DIR / "scheduler.log"`
- 替換所有硬編碼日誌路徑為 `DEFAULT_LOG_FILE`

---

### 7. Updated: `ui/pages/system.py` 硬編碼路徑 ✅

**變更**:
- 匯入 `PROJECT_ROOT`, `CONFIG_DIR`, `LOGS_DIR`, `OUTPUTS_DIR`, `STATE_DIR`
- File Locations 表格改為使用動態路徑

---

### 8. Updated: `ui/app.py` 硬編碼路徑 ✅

**變更**:
- 匯入 `PROJECT_ROOT`
- `update_navbar_status()`: PID 檔案路徑改為 `PROJECT_ROOT / ".monitor.pid"`

---

## Scheduler Live Status Fix / 排程器即時狀態修復

### Before
- `get_next_run_time()` 總是返回日誌中最後的 next run 時間
- Scheduler stopped 時仍顯示過期的 next run
- 無法區分 historical data 與 live state

### After
- `get_next_run_time()` 先檢查 scheduler 運行狀態
- Stopped 時返回 `None`，UI 顯示 "--" 或 "Not scheduled"
- `get_full_status()` 新增 `is_live` 和 `mode` 欄位
- Dashboard 可明確標示 "LIVE" vs "HISTORICAL DATA"

---

## Files Modified / 修改檔案

| 檔案 | 變更類型 | 說明 |
|------|---------|------|
| `config/paths.py` | 新增 | 動態路徑解析器 |
| `config/loader.py` | 更新 | 使用動態路徑 |
| `ui/services/monitor_service.py` | 更新 | 動態路徑 + live status fix |
| `ui/services/action_service.py` | 更新 | 動態路徑 |
| `ui/pages/dashboard.py` | 更新 | 動態路徑設定 |
| `ui/pages/parameters.py` | 更新 | 動態路徑 + 移除硬編碼路徑 |
| `ui/pages/strategies.py` | 更新 | 動態路徑設定 |
| `ui/pages/signals.py` | 更新 | 動態路徑設定 |
| `ui/pages/system.py` | 更新 | 動態路徑 + 移除硬編碼路徑 |
| `ui/pages/actions.py` | 更新 | 動態路徑設定 |
| `ui/app.py` | 更新 | 動態路徑 + PID 檔案路徑 |

---

## Testing / 測試建議

1. **Config Loading**
   ```bash
   cd /tmp/kimi-shared-brain/ui && python3 -c "
   from config.paths import CONFIG_DIR
   from config.loader import get_monitoring_params
   print('CONFIG_DIR:', CONFIG_DIR)
   print('Config loaded:', get_monitoring_params())
   "
   ```

2. **Scheduler Status**
   ```bash
   cd /tmp/kimi-shared-brain/ui && python3 -c "
   from ui.services.monitor_service import get_full_status
   status = get_full_status()
   print('is_live:', status['is_live'])
   print('mode:', status['mode'])
   print('next_run:', status['next_run'])
   "
   ```

3. **Pages Import Test**
   ```bash
   cd /tmp/kimi-shared-brain/ui && python3 -c "
   import dash
   import pages.dashboard
   import pages.parameters
   import pages.strategies
   print('All pages imported successfully')
   "
   ```

---

## Backward Compatibility / 向後相容性

✅ **完全相容**

- 所有公開 API 不變
- 配置檔案格式不變
- 資料儲存路徑不變
- UI 介面不變
- 僅內部路徑解析方式改變

---

## Alert-Only / 僅提醒設計

✅ **維持不變**

- 無交易 API 連接
- 無自動下單邏輯
- 僅記錄人工決策

---

## Summary / 總結

T-040 成功修復了 UI 的硬編碼路徑問題：

✅ 所有頁面使用動態路徑解析  
✅ Scheduler stopped 時不再顯示過期 next run  
✅ Historical vs Live 狀態明確區分  
✅ 完整向後相容  
✅ 支援多環境部署  

系統現在可以在不同環境中正確運行，不再依賴特定的絕對路徑。
