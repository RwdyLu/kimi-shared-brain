# Second Bot 定期任務清理規則 (T-063)

## 修改前 (舊規則)
- 每 30 分鐘檢查 T-052 系列任務
- 重複報告已完成的任務，浪費資源

## 修改後 (新規則)
- 每 30 分鐘只檢查 `status = assigned` 或 `in_progress` 的任務
- 如果沒有進行中任務，回報「系統閒置，無待處理任務」然後 NO_REPLY
- 不再重複檢查已完成的任務

## 檢查邏輯

```python
def check_tasks():
    # 只檢查進行中任務
    active_tasks = get_tasks_with_status(["assigned", "in_progress"])
    
    if not active_tasks:
        print("系統閒置，無待處理任務")
        return "NO_REPLY"
    
    # 檢查是否有卡住超過 2 小時的任務
    stuck_tasks = [t for t in active_tasks if is_stuck(t, hours=2)]
    
    if stuck_tasks:
        notify(f"⚠️ 發現 {len(stuck_tasks)} 個任務卡住超過 2 小時")
    
    return generate_report(active_tasks)
```

## 狀態流程

```
assigned → in_progress → completed/reviewed
     ↑
   檢查點 (每 30 分鐘)
```

## 回報規則

| 狀況 | 動作 |
|------|------|
| 無進行中任務 | NO_REPLY |
| 有進行中任務 | 生成報告 |
| 有卡住任務 | 通知 @Nurgle |

---
任務 T-063 完成
