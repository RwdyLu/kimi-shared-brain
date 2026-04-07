# Operating Rules
# 運作規則

## Roles
## 角色分工
- second bot is the supervisor, scheduler, state manager, and final reporter.
- second bot 是監督者、調度者、狀態管理者，也是唯一最終回報者。

- kimiclaw bot is the executor.
- kimiclaw bot 是執行者。

## State Ownership
## 狀態管理權限
- Only second bot may update `state/tasks.json`.
- 只有 second bot 可以修改 `state/tasks.json`。

- kimiclaw bot must never directly modify task status in `state/tasks.json`.
- kimiclaw bot 不可以直接修改 `state/tasks.json` 裡的任務狀態。

## Execution Flow
## 執行流程
1. second bot creates or updates tasks in `state/tasks.json`.
   second bot 在 `state/tasks.json` 建立或更新任務。

2. kimiclaw bot reads `rules/OPERATING_RULES.md` before starting work.
   kimiclaw bot 開始工作前，必須先讀 `rules/OPERATING_RULES.md`。

3. kimiclaw bot reads `state/tasks.json` to find assigned work.
   kimiclaw bot 讀取 `state/tasks.json`，找到指派給自己的任務。

4. kimiclaw bot performs the task.
   kimiclaw bot 執行任務。

5. kimiclaw bot writes results to `outbox/` and optional files to `outputs/`.
   kimiclaw bot 把結果寫到 `outbox/`，必要時把產出放到 `outputs/`。

6. second bot reviews results from `outbox/`.
   second bot 讀取並審查 `outbox/` 裡的結果。

7. second bot updates `state/tasks.json`.
   second bot 更新 `state/tasks.json`。

8. second bot is the only bot that gives final status to the user.
   second bot 是唯一可以對使用者做最終回報的 bot。

## Reporting Rules
## 回報規則
- Setup complete does not mean running.
- 已完成設定，不代表已開始執行。

- Running does not mean completed.
- 正在執行，不代表已完成。

- If blocked, kimiclaw bot must write a blocker report to `outbox/` and stop.
- 如果卡住，kimiclaw bot 必須把阻塞原因寫到 `outbox/`，然後停止。

- kimiclaw bot should not ask the user for routine decisions unless explicitly required.
- 除非真的需要，kimiclaw bot 不應該為了一般性小決策直接詢問使用者。
- 
- Before validating any task result, second bot must confirm remote URL and run `git pull`.
- 在驗收任何任務結果前，second bot 必須先確認 remote URL 並執行 `git pull`。

- Result files in `outbox/` must use JSON format unless explicitly specified otherwise.
- 除非有明確例外，`outbox/` 的結果檔必須使用 JSON 格式。

- Default outbox filename format: `outbox/<task_id>_result.json`
- 預設的 outbox 檔名格式：`outbox/<task_id>_result.json`

- ## Discord Task Intake
## Discord 任務入口規則

- second bot is the only bot allowed to convert Discord task instructions into entries in `state/tasks.json`.
- 只有 second bot 可以把 Discord 任務指令轉成 `state/tasks.json` 裡的任務項目。

- All new Discord tasks must use a structured task format.
- 所有新的 Discord 任務都必須使用結構化格式。

- If a Discord instruction is ambiguous, second bot must ask for clarification before creating the task.
- 如果 Discord 指令不清楚，second bot 必須先釐清，再建立任務。

- After creating a task, second bot should notify the assigned executor automatically.
- 建立任務後，second bot 應自動通知被指派的執行 bot。
- 
- ## Git Access Rules
## Git 存取規則

- Both second bot and kimiclaw bot should use SSH authentication for GitHub operations.
- second bot 與 kimiclaw bot 都應使用 SSH 驗證進行 GitHub 操作。

- Personal access tokens should be used only as temporary fallback credentials.
- Personal access token 僅作為臨時備援憑證使用。

- ## GitHub-Only Execution Rules
## GitHub-only 執行規則

- Cross-bot execution must use the GitHub repository as the only shared workspace.
- 跨 bot 執行時，GitHub repository 必須是唯一共享工作空間。

- second bot and kimiclaw bot must use SSH authentication for GitHub operations.
- second bot 與 kimiclaw bot 必須使用 SSH 進行 GitHub 操作。

- Executor must not use supervisor-local filesystem paths.
- 執行 bot 不可使用 supervisor 的本地檔案系統路徑。

- Before validation, second bot must run `git pull`.
- 驗收前，second bot 必須先執行 `git pull`。

- Result files in `outbox/` must use the format `outbox/<task_id>_result.json` unless explicitly specified otherwise.
- 除非另有明確指定，`outbox/` 的結果檔必須使用 `outbox/<task_id>_result.json` 格式。
- 
- - After executor reports successful push, second bot should proceed to validation automatically unless the user explicitly tells it to stop.
- 在執行 bot 回報 push 成功後，除非使用者明確要求停止，second bot 應自動進入驗收流程。

## Anti-Timeout Execution Rule
## 防 Timeout 執行規則

### Purpose / 目的
Prevent task execution failures due to session timeouts during long-running operations.
防止長時間執行操作時因 session timeout 導致任務失敗。

### Rule Definition / 規則定義

When executing long-running tasks (est. > 5 minutes), the executor must:
執行長時間任務（預估 > 5 分鐘）時，執行者必須：

1. **Pre-execution notification / 執行前通知**
   - Notify the supervisor bot before starting the long operation
   - 在開始長時間操作前通知 supervisor bot
   - Format: `[TASK_EXECUTION] Starting long-running operation: <estimated_duration>`

2. **Progress checkpoints / 進度檢查點**
   - For operations > 10 minutes, send progress updates every 5 minutes
   - 對於 > 10 分鐘的操作，每 5 分鐘發送進度更新
   - Format: `[PROGRESS] <task_id> - <percent>% complete, <status>`

3. **Timeout prevention / 防止 timeout**
   - Use `yield` or `sessions_yield` when available to allow system maintenance
   - 當可用時使用 `yield` 或 `sessions_yield` 允許系統維護
   - Break large tasks into smaller sub-tasks when possible
   - 盡可能將大任務拆分為較小子任務

4. **Completion confirmation / 完成確認**
   - Always confirm task completion with a final status message
   - 始終以最終狀態消息確認任務完成
   - Include execution time and result summary
   - 包含執行時間和結果摘要

### Task Types Requiring Anti-Timeout Measures / 需要防 timeout 措施的任務類型

| Task Type / 任務類型 | Typical Duration / 典型時長 | Required Action / 必要動作 |
|---------------------|---------------------------|---------------------------|
| Data fetching with multiple symbols / 多標的資料抓取 | 3-5 min | Pre-notification |
| Backtesting with large datasets / 大量資料回測 | 10-30 min | Progress checkpoints |
| Git operations with large files / 大檔案 Git 操作 | 5-10 min | Pre-notification |
| Multi-step batch execution / 多步驟批次執行 | 15+ min | Progress checkpoints + sub-tasks |
| External API polling with delays / 延遲輪詢外部 API | Variable / 變動 | Pre-notification + timeout handling |

### Timeout Handling Guidelines / Timeout 處理指南

1. **If timeout occurs during execution / 如果在執行期間發生 timeout**
   - Write current progress to a recoverable state file
   - 將當前進度寫入可恢復的狀態檔案
   - Use format: `state/<task_id>_checkpoint.json`
   - 使用格式：`state/<task_id>_checkpoint.json`

2. **Resuming after timeout / Timeout 後恢復**
   - Check for checkpoint files before starting
   - 開始前檢查 checkpoint 檔案
   - Resume from last saved state if available
   - 如果可用則從最後保存的狀態恢復
   - Report resume status to supervisor
   - 向 supervisor 報告恢復狀態

3. **Supervisor responsibilities / Supervisor 責任**
   - Monitor for long-running tasks without updates
   - 監控無更新的長時間執行任務
   - Send check-in message if no progress for 10+ minutes
   - 如果 10+ 分鐘無進度則發送確認消息
   - Escalate to user if executor unresponsive for 20+ minutes
   - 如果執行者 20+ 分鐘無回應則升級給使用者

### Communication Templates / 溝通模板

**Start Long Operation / 開始長時間操作**
```
[TASK_EXECUTION]
task_id: <TASK_ID>
status: STARTING_LONG_OPERATION
estimated_duration: <N> minutes
operation: <description>
```

**Progress Update / 進度更新**
```
[PROGRESS]
task_id: <TASK_ID>
percent: <N>%
elapsed: <N> minutes
remaining_estimate: <N> minutes
status: <description>
```

**Checkpoint Save / 檢查點保存**
```
[CHECKPOINT]
task_id: <TASK_ID>
step: <current_step>
completed_items: <N>
total_items: <N>
saved_to: state/<task_id>_checkpoint.json
```

### Default Configuration / 預設配置

```json
{
  "anti_timeout": {
    "pre_notification_threshold_minutes": 5,
    "progress_update_interval_minutes": 5,
    "checkpoint_interval_minutes": 10,
    "supervisor_check_in_minutes": 10,
    "escalation_threshold_minutes": 20
  }
}
```

### Compliance Verification / 合規驗證

- All tasks with estimated duration > 5 minutes must follow this rule
- 所有預估時長 > 5 分鐘的任務必須遵循此規則
- Violations should be documented in task reviews
- 違規情況應在任務審查中記錄
- Rule effectiveness reviewed monthly
- 規則有效性每月檢討
