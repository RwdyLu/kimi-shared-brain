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
