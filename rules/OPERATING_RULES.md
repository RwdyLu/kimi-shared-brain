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
