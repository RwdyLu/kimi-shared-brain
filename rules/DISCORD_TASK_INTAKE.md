# Discord Task Intake Specification
# Discord 任務入口規格

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define the standard format and workflow for converting Discord commands into executable tasks through the GitHub-only workflow.

定義將 Discord 指令轉換為可執行任務的標準格式與流程，透過 GitHub-only 工作流程完成。

---

## 2. Roles / 角色分工

| Role / 角色 | Responsibilities / 職責 |
|-------------|------------------------|
| **second bot** | Supervisor, scheduler, state manager, final reporter / 監督者、調度者、狀態管理者、最終回報者 |
| **kimiclaw bot** | Executor / 執行者 |

---

## 3. Standard Discord Task Format / 標準 Discord 任務格式

All new tasks in Discord must use the following structured format:

所有 Discord 新任務必須使用以下結構化格式：

```
NEW_TASK
task_id: <unique_id>
title: <task_title>
assigned_to: <kimiclaw_bot | second_bot>
priority: <high | medium | low>
type: <workflow_test | documentation | implementation | research>
goal: <clear_description>
output_file: <expected_output_path>
success_condition: <validation_criteria>
```

---

## 4. Required Fields / 必填欄位

| Field / 欄位 | Description / 說明 | Example / 範例 |
|--------------|-------------------|----------------|
| `task_id` | Unique identifier / 唯一識別碼 | `T-005` |
| `title` | Brief task description / 簡短任務描述 | `建立 Discord 任務入口規格文件` |
| `assigned_to` | Executor assignment / 執行者指派 | `kimiclaw_bot` |
| `priority` | Task urgency / 任務緊急程度 | `high`, `medium`, `low` |
| `type` | Task category / 任務類別 | `documentation` |
| `goal` | Detailed objective / 詳細目標 | 建立規格文件... |
| `output_file` | Expected deliverable / 預期產出 | `rules/DISCORD_TASK_INTAKE.md` |
| `success_condition` | Completion criteria / 完成條件 | second bot 驗收並更新 state |

---

## 5. Execution Flow / 執行流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. User sends NEW_TASK in Discord                          │
│     使用者在 Discord 發送 NEW_TASK 指令                      │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  2. second bot writes task to state/tasks.json              │
│     second bot 將任務寫入 state/tasks.json                   │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  3. second bot assigns executor (kimiclaw_bot)              │
│     second bot 指派執行者 (kimiclaw_bot)                     │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Executor reads rules and state from GitHub              │
│     執行者從 GitHub 讀取 rules 與 state                      │
│     (git clone / git pull via SSH)                          │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Executor performs the task                              │
│     執行者執行任務                                            │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Executor writes result to GitHub                        │
│     執行者將結果寫入 GitHub                                   │
│     (git commit & git push)                                 │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  7. second bot runs git pull                                │
│     second bot 執行 git pull                                 │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  8. second bot validates result                             │
│     second bot 驗收結果                                       │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  9. second bot updates state/tasks.json                     │
│     second bot 更新 state/tasks.json                         │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  10. second bot reports back to user                        │
│      second bot 向使用者回報                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. GitHub-only Rule / GitHub-only 規則

- **SSH Authentication**: Both bots must use SSH for GitHub operations.
  **SSH 驗證**: 兩個 bot 都必須使用 SSH 進行 GitHub 操作。

- **No Local Fallback**: Never use local workspace paths as fallback.
  **無本地備援**: 絕不使用本地工作路徑作為備援。

- **Shared Source of Truth**: GitHub repo is the single source of truth for all task data.
  **共享真相來源**: GitHub repo 是所有任務資料的唯一真相來源。

- **State Ownership**: Only second bot may update `state/tasks.json`.
  **狀態所有權**: 只有 second bot 可以更新 `state/tasks.json`。

---

## 7. Validation Rule / 驗收規則

Before validating any task result, the supervisor must:

監督者在驗收任何任務結果前，必須：

1. **Confirm Remote URL** / 確認遠端 URL
   - Verify the correct GitHub repository
   - 確認正確的 GitHub 倉庫

2. **Run git pull** / 執行 git pull
   - Fetch the latest changes from remote
   - 從遠端獲取最新變更

3. **Verify File Existence** / 驗證檔案存在
   - Check that `output_file` exists
   - 確認 `output_file` 存在

4. **Validate Content** / 驗證內容
   - Ensure content meets `success_condition`
   - 確認內容符合 `success_condition`

5. **Update State** / 更新狀態
   - Mark task as `completed` in `state/tasks.json`
   - 在 `state/tasks.json` 標記任務為 `completed`

---

## 8. Blocker Handling / 阻塞處理

If the executor encounters a blocker:

如果執行者遇到阻塞：

1. **Write Blocker Report** / 寫入阻塞報告
   - Create `outbox/<task_id>_blocker.json`
   - 建立 `outbox/<task_id>_blocker.json`

2. **Stop Execution** / 停止執行
   - Do not proceed until resolved
   - 在解決前不要繼續

3. **Notify Supervisor** / 通知監督者
   - Use `[QUESTION]` format in Discord
   - 在 Discord 使用 `[QUESTION]` 格式

4. **Supervisor Decision** / 監督者決策
   - Provide `[SUPERVISOR_DECISION]` with resolution
   - 提供 `[SUPERVISOR_DECISION]` 含解決方案

---

## 9. Example Command / 範例指令

### Discord Input / Discord 輸入

```
NEW_TASK
task_id: T-006
title: 測試新策略回測
assigned_to: kimiclaw_bot
priority: high
type: research
goal: 使用 research/ 模組對 BTC 4H 進行回測，並回報 Sharpe ratio 與最大回撤
output_file: outbox/T-006_result.json
success_condition: second bot 驗收回測結果並更新 state/tasks.json
```

### State Entry / State 項目

```json
{
  "task_id": "T-006",
  "title": "測試新策略回測",
  "assigned_to": "kimiclaw_bot",
  "status": "pending",
  "priority": "high",
  "type": "research",
  "goal": "使用 research/ 模組對 BTC 4H 進行回測...",
  "output_file": "outbox/T-006_result.json",
  "success_condition": "second bot 驗收回測結果...",
  "report_to": "second_bot",
  "last_updated": "2026-04-05T14:30:00+08:00"
}
```

---

## 10. References / 參考文件

- `rules/OPERATING_RULES.md` - General operating rules / 一般運作規則
- `state/tasks.json` - Task state storage / 任務狀態儲存
- `outbox/` - Task result output / 任務結果輸出

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
