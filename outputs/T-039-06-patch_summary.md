# T-039-06-patch: Normalize Action Queue Structure

**Date**: 2026-04-09  
**Task**: T-039-06-patch  
**Type**: Patch / Structure Normalization  
**Commit**: TBD

---

## Original Structure Problem / 原本結構問題

T-039-06 實作時，為了快速交付功能，將 `ActionQueueService` 直接內嵌於 `ui/pages/actions.py` 中。這導致：

| 問題 | 說明 |
|------|------|
| 違反分層原則 | Service 邏輯與 UI 頁面混在一起 |
| 無法重複使用 | 其他頁面或模組無法直接引用 Service |
| 測試困難 | 無法單獨測試 Service 邏輯 |
| 維護性差 | 檔案過大（800+ lines），職責不清 |

---

## This Patch / 本次補正

### 1. Created: `ui/services/action_service.py` ✅

**內容**: 將 `ActionQueueService` 從 `ui/pages/actions.py` 完整抽離

**功能保留**:
- `load_pending_actions()` - 載入待處理行動
- `load_history(limit)` - 載入行動歷史
- `save_pending/actions()` - 儲存待處理行動
- `save_history()` - 儲存歷史
- `process_decision()` - 處理決策 (approve/reject/snooze)
- `add_action()` - 新增行動到佇列
- `get_today_stats()` - 取得今日統計
- `clear_history()` - 清除歷史

**新增便利函數**:
- `load_pending_actions()` - 使用預設服務實例
- `load_history()` - 使用預設服務實例
- `process_decision()` - 使用預設服務實例
- `add_action()` - 使用預設服務實例
- `get_today_stats()` - 使用預設服務實例
- `clear_history()` - 使用預設服務實例

**檔案大小**: ~10,135 bytes (~280 lines)

---

### 2. Created: `config/action_queue.json` ✅

**用途**: Action Queue 配置與初始結構模板

**內容**:
```json
{
  "version": "1.0.0",
  "description": "Action Queue Configuration",
  "action_types": {
    "TREND_LONG": { "label": "...", "color": "success", ... },
    "TREND_SHORT": { "label": "...", "color": "danger", ... },
    "CONTRARIAN_WATCH": { "label": "...", "color": "info", ... }
  },
  "decisions": {
    "approve": { "label": "...", "color": "success", ... },
    "reject": { "label": "...", "color": "danger", ... },
    "snooze": { "label": "...", "color": "info", ... }
  },
  "storage_paths": {
    "runtime_state_dir": "state/actions/",
    "queue_file": "state/actions/queue.json",
    "history_file": "state/actions/history.json"
  }
}
```

**注意**: 此檔案為靜態配置，runtime 狀態仍儲存於 `state/actions/`

---

### 3. Created: `state/actions/.gitkeep` ✅

**用途**: 標示 runtime 狀態目錄位置

**說明**: 目錄中的檔案會在執行時自動建立，此檔案僅為目錄標示

---

### 4. Updated: `ui/pages/actions.py` ✅

**變更**:
- 移除內嵌的 `ActionQueueService` class (~150 lines)
- 改為從 `ui/services/action_service` 匯入
- 頁面只負責 UI 渲染與 callback 處理
- 核心邏輯交由獨立 service 處理

**匯入變更**:
```python
# Before
# (ActionQueueService class defined inline in this file)

# After
from ui.services.action_service import (
    ActionQueueService, load_pending_actions, load_history,
    process_decision, get_today_stats, clear_history
)
```

**檔案大小變更**: ~29,369 bytes → ~23,734 bytes (-5,635 bytes)

---

## File Summary / 檔案總結

| 檔案 | 類型 | 說明 |
|------|------|------|
| `ui/services/action_service.py` | 新增 | 獨立 Action Queue Service |
| `config/action_queue.json` | 新增 | Action Queue 配置模板 |
| `state/actions/.gitkeep` | 新增 | Runtime 狀態目錄標示 |
| `ui/pages/actions.py` | 更新 | 改為引用獨立 service |

---

## Backward Compatibility / 向後相容性

✅ **完全相容**

- 所有既有功能保留
- UI 行為不變
- 資料格式不變（仍使用相同的 JSON 結構）
- Runtime 狀態路徑不變

---

## Alert-Only Enforcement / 僅提醒設計

✅ **維持不變**

```python
# action_service.py 文件字串明確標示：
"""
⚠️ ALERT-ONLY SYSTEM / 僅提醒系統
This service logs decisions but NEVER executes trades automatically.
本服務記錄決策但絕不自動執行交易。
"""
```

- 無交易 API 連接
- 無自動下單邏輯
- 僅記錄人工決策

---

## Runtime State Path Behavior / Runtime 狀態路徑行為

**維持原有機制**:

```python
# 預設路徑（不變）
DEFAULT_ACTIONS_DIR = "/tmp/kimi-shared-brain/state/actions"
DEFAULT_ACTIONS_FILE = os.path.join(DEFAULT_ACTIONS_DIR, "queue.json")
DEFAULT_HISTORY_FILE = os.path.join(DEFAULT_ACTIONS_DIR, "history.json")

# 自動建立目錄（不變）
def _ensure_dirs(self):
    os.makedirs(self.actions_dir, exist_ok=True)
```

✅ Runtime 時自動建立 `state/actions/` 目錄與檔案  
✅ 現在新增 `.gitkeep` 明確標示此為 runtime 狀態目錄

---

## Testing Recommendations / 測試建議

1. **Service 單獨測試**:
   ```python
   from ui.services.action_service import ActionQueueService
   service = ActionQueueService()
   service.add_action({"type": "TEST", "symbol": "BTCUSDT"})
   ```

2. **UI 整合測試**:
   - 確認 Approve/Reject/Snooze 按鈕仍正常運作
   - 確認統計數字正確更新
   - 確認歷史記錄正確顯示

3. **資料持久化測試**:
   - 重啟 UI 後確認資料仍存在
   - 確認 `state/actions/` 檔案正確生成

---

## Conclusion / 結論

T-039-06-patch 成功將 Action Queue 結構正規化：

✅ Service 與 UI 分離  
✅ 新增配置檔案  
✅ 明確標示 runtime 狀態路徑  
✅ 完全向後相容  
✅ 維持 Alert-Only 設計  

系統現在符合標準的三層架構：
- **UI Layer**: `ui/pages/actions.py`
- **Service Layer**: `ui/services/action_service.py`
- **Config Layer**: `config/action_queue.json`
- **State Layer**: `state/actions/`
