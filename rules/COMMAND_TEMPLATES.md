# Command Templates Specification
# Command Templates 規格

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Provide ready-to-use Discord command templates for the Central Brain task system. Copy and modify these templates for quick task creation and management.

提供立即可用的 Discord 指令模板供 Central Brain 任務系統使用。複製並修改這些模板以快速建立和管理任務。

---

## 2. Usage Notes / 使用說明

- **Copy the template** that matches your need / **複製符合需求的模板**
- **Replace placeholders** marked with `<angle_brackets>` / **替換以 `<角括號>` 標記的佔位符**
- **Remove optional fields** if not needed / **如不需要可移除選填欄位**
- **Send the completed command** in Discord / **在 Discord 中發送完成的指令**

---

## 3. Template: NEW_TASK

### Purpose / 用途
Create a new task and assign it to an executor. / 建立新任務並指派給執行者。

### Required Fields / 必填欄位

| Field | Description | 說明 |
|-------|-------------|------|
| `task_id` | Unique identifier (e.g., T-009) | 唯一識別碼 |
| `title` | Brief task description | 簡短任務描述 |
| `assigned_to` | `kimiclaw_bot` or `second_bot` | 執行者 |
| `priority` | `high`, `medium`, or `low` | 優先級 |
| `type` | Task category | 任務類型 |
| `goal` | Detailed objective | 詳細目標 |
| `output_file` | Expected deliverable path | 預期產出路徑 |
| `success_condition` | How to validate completion | 如何驗證完成 |

### Template / 模板

```
NEW_TASK
task_id: <TASK_ID>
title: <TITLE>
assigned_to: kimiclaw_bot
priority: <high|medium|low>
type: <workflow_test|documentation|implementation|research>
goal: <DETAILED_OBJECTIVE>
output_file: <outbox/T-XXX_result.json>
success_condition: <VALIDATION_CRITERIA>
```

### Example / 範例

```
NEW_TASK
task_id: T-009
title: 建立 API 整合模組
assigned_to: kimiclaw_bot
priority: high
type: implementation
goal: 整合外部 API 服務並建立錯誤處理機制
output_file: outbox/T-009_result.json
success_condition: second bot 驗收並更新 state/tasks.json 為 completed
```

---

## 4. Template: EXECUTE_TASK

### Purpose / 用途
Instruct the executor to start working on an assigned task. / 指示執行者開始執行指派的任務。

### Template / 模板

```
@kimiclaw bot

執行任務 <TASK_ID>
Execute task <TASK_ID>

請嚴格遵守以下規則：
1. 讀取 `rules/OPERATING_RULES.md`
2. 讀取 `state/tasks.json` 找到 <TASK_ID>
3. 執行任務目標
4. 將結果寫入 `<OUTPUT_FILE>`
5. Commit 並 push 到 GitHub
6. 回報 push 結果（commit hash, file path）
```

### Example / 範例

```
@kimiclaw bot

執行任務 T-009
Execute task T-009

請嚴格遵守以下規則：
1. 讀取 `rules/OPERATING_RULES.md`
2. 讀取 `state/tasks.json` 找到 T-009
3. 執行任務目標
4. 將結果寫入 `outbox/T-009_result.json`
5. Commit 並 push 到 GitHub
6. 回報 push 結果（commit hash, file path）
```

---

## 5. Template: VALIDATE_TASK

### Purpose / 用途
Request supervisor validation of a completed task. / 請求監督者驗收已完成的任務。

### Template / 模板

```
@second bot

驗收任務 <TASK_ID>
Validate task <TASK_ID>

執行者已 push 結果到 GitHub：
- Commit: <COMMIT_HASH>
- File: <OUTPUT_FILE>

請執行：
1. git pull
2. 驗證輸出檔案
3. 確認 success_condition 達成
4. 更新 state/tasks.json
5. 向我回報最終狀態
```

### Example / 範例

```
@second bot

驗收任務 T-009
Validate task T-009

執行者已 push 結果到 GitHub：
- Commit: a1b2c3d
- File: outbox/T-009_result.json

請執行：
1. git pull
2. 驗證輸出檔案
3. 確認 success_condition 達成
4. 更新 state/tasks.json
5. 向我回報最終狀態
```

---

## 6. Template: BLOCKER_REPORT

### Purpose / 用途
Report a blocker that prevents task execution. / 回報阻止任務執行的阻塞。

### Template / 模板

```
[BLOCKER_REPORT]
task_id: <TASK_ID>
status: blocked
blocker_type: <authentication|environment|dependency|ambiguous_requirement>
severity: <low|medium|high|critical>
summary: <ONE_LINE_DESCRIPTION>
context: |
  <DETAILED_CONTEXT>
attempted_actions:
  - <ACTION_1>
  - <ACTION_2>
  - <ACTION_3>
suggested_next_action: <PROPOSED_SOLUTION>
needs_user_decision: <true|false>
```

### Example / 範例

```
[BLOCKER_REPORT]
task_id: T-009
status: blocked
blocker_type: authentication
severity: high
summary: GitHub API token 過期
context: |
  嘗試呼叫 GitHub API 時收到 401 Unauthorized 錯誤。
  Token 可能已過期或被撤銷。
attempted_actions:
  - 重試 API 呼叫（3 次）
  - 檢查環境變數
  - 確認網路連線
suggested_next_action: 請提供新的 GitHub Personal Access Token
needs_user_decision: true
```

---

## 7. Template: PAUSE_TASK

### Purpose / 用途
Temporarily pause a task. / 暫時暫停任務。

### Template / 模板

```
@second bot

暫停任務 <TASK_ID>
Pause task <TASK_ID>

原因: <REASON>
Reason: <REASON>

預計恢復時間: <OPTIONAL>
Estimated resume time: <OPTIONAL>
```

### Example / 範例

```
@second bot

暫停任務 T-009
Pause task T-009

原因: 等待外部 API 供應商回覆
Reason: Waiting for external API vendor response

預計恢復時間: 2026-04-06 09:00
Estimated resume time: 2026-04-06 09:00
```

---

## 8. Template: RESUME_TASK

### Purpose / 用途
Resume a previously paused task. / 恢復先前暫停的任務。

### Template / 模板

```
@second bot

恢復任務 <TASK_ID>
Resume task <TASK_ID>

阻塞已解決: <RESOLUTION_DESCRIPTION>
Blocker resolved: <RESOLUTION_DESCRIPTION>

請更新狀態為 in_progress 並通知執行者。
Please update status to in_progress and notify executor.
```

### Example / 範例

```
@second bot

恢復任務 T-009
Resume task T-009

阻塞已解決: 已收到新的 API 金鑰
Blocker resolved: New API key received

請更新狀態為 in_progress 並通知執行者。
Please update status to in_progress and notify executor.
```

---

## 9. Template: CANCEL_TASK

### Purpose / 用途
Cancel a task permanently. / 永久取消任務。

### Template / 模板

```
@second bot

取消任務 <TASK_ID>
Cancel task <TASK_ID>

原因: <REASON>
Reason: <REASON>

確認取消後，請更新 state/tasks.json 並通知相關方。
After confirmation, please update state/tasks.json and notify parties.
```

### Example / 範例

```
@second bot

取消任務 T-009
Cancel task T-009

原因: 需求變更，此功能不再需要
Reason: Requirements changed, feature no longer needed

確認取消後，請更新 state/tasks.json 並通知相關方。
After confirmation, please update state/tasks.json and notify parties.
```

---

## 10. Template: STATUS_CHECK

### Purpose / 用途
Check the current status of a task or the entire system. / 檢查任務或整個系統的當前狀態。

### Template / 模板

```
@second bot

狀態檢查
Status check

請提供：
1. 所有進行中任務
2. 所有阻塞任務
3. 最近完成的任務
4. 系統整體狀態

Please provide:
1. All in-progress tasks
2. All blocked tasks
3. Recently completed tasks
4. Overall system status
```

### Example / 範例

```
@second bot

狀態檢查 T-009
Status check T-009

請提供此任務的詳細狀態與執行進度。
Please provide detailed status and execution progress for this task.
```

---

## 11. Template: USER_DECISION_REQUEST

### Purpose / 用途
Request user decision for a high-stakes or ambiguous situation. / 請求使用者對高風險或模糊情況做出決策。

### Template / 模板

```
[ESCALATION]
task_id: <TASK_ID>
問題: <PROBLEM_DESCRIPTION>
已知事實: |
  - <FACT_1>
  - <FACT_2>
  - <FACT_3>
無法裁定原因: <WHY_SUPERVISOR_CANNOT_DECIDE>
需要決策點: |
  1. <DECISION_OPTION_A>
  2. <DECISION_OPTION_B>
  3. <DECISION_OPTION_C>

@Nurgle 請做出決策。
```

### Example / 範例

```
[ESCALATION]
task_id: T-009
問題: 選擇資料庫方案
已知事實: |
  - 需要支援高併發寫入
  - 預算限制在 $500/月
  - 團隊熟悉 PostgreSQL 和 MongoDB
無法裁定原因: 此決策影響長期架構，需要產品負責人裁定
需要決策點: |
  1. 使用 PostgreSQL（熟悉，成本低）
  2. 使用 MongoDB（擴展性好，學習成本高）
  3. 使用託管服務（成本高，維護少）

@Nurgle 請做出決策。
```

---

## 12. Best Practices / 最佳實踐

### 12.1 Task ID Naming / 任務 ID 命名

- Use sequential numbering: T-001, T-002, T-003... / 使用連續編號
- Always include leading zeros: T-001 not T-1 / 總是包含前導零
- Never reuse task IDs / 絕不重複使用任務 ID

### 12.2 Writing Clear Goals / 撰寫清晰的目標

✅ **Good / 良好**:
```
goal: 建立使用者認證模組，包含登入、註冊、密碼重設功能，並通過單元測試
```

❌ **Bad / 不佳**:
```
goal: 做認證功能
```

### 12.3 Defining Success Conditions / 定義成功條件

✅ **Good / 良好**:
```
success_condition: second bot 驗收測試報告，確認所有 10 個測試案例通過，並更新 state/tasks.json 為 completed
```

❌ **Bad / 不佳**:
```
success_condition: 完成測試
```

### 12.4 Handling Blockers / 處理阻塞

1. **Always report** after 3 failed attempts / **3 次失敗後總是回報**
2. **Provide context** not just error messages / **提供上下文而非僅錯誤訊息**
3. **Suggest solutions** don't just state problems / **建議解決方案而非僅陳述問題**
4. **Set correct severity** for proper escalation / **設定正確嚴重程度以適當升級**

### 12.5 Communication Style / 溝通風格

- **Be specific** / **具體明確**
- **One task at a time** / **一次一個任務**
- **Wait for confirmation** before proceeding / **等待確認後再繼續**
- **Use the templates** for consistency / **使用模板以保持一致性**

---

## 13. Quick Reference / 快速參考

| Command / 指令 | Template Section / 模板章節 |
|----------------|----------------------------|
| Create new task / 建立新任務 | [Template: NEW_TASK](#3-template-new_task) |
| Start execution / 開始執行 | [Template: EXECUTE_TASK](#4-template-execute_task) |
| Validate completion / 驗證完成 | [Template: VALIDATE_TASK](#5-template-validate_task) |
| Report blocker / 回報阻塞 | [Template: BLOCKER_REPORT](#6-template-blocker_report) |
| Pause task / 暫停任務 | [Template: PAUSE_TASK](#7-template-pause_task) |
| Resume task / 恢復任務 | [Template: RESUME_TASK](#8-template-resume_task) |
| Cancel task / 取消任務 | [Template: CANCEL_TASK](#9-template-cancel_task) |
| Check status / 檢查狀態 | [Template: STATUS_CHECK](#10-template-status_check) |
| Request decision / 請求決策 | [Template: USER_DECISION_REQUEST](#11-template-user_decision_request) |

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
