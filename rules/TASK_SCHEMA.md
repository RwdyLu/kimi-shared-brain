# Task Schema Specification
# Task Schema 規格

**Version**: 1.1.0  
**版本**: 1.1.0  
**Last Updated**: 2026-04-07  
**最後更新**: 2026-04-07

---

## 1. Purpose / 目的

Define the complete schema for `state/tasks.json`, including required fields, status values, transition rules, and write permissions to ensure consistent task management across the Central Brain system.

定義 `state/tasks.json` 的完整結構，包含必填欄位、狀態值、轉換規則與寫入權限，確保 Central Brain 系統中的任務管理一致性。

---

## 2. File Scope / 檔案範圍

- **`state/tasks.json`** is the **single source of truth** for all task states.
  **`state/tasks.json`** 是所有任務狀態的**唯一真相來源**。

- All task creation, updates, and status changes must be reflected in this file.
  所有任務建立、更新與狀態變更都必須反映在此檔案中。

- Both `second bot` and `kimiclaw bot` read from this file to determine task assignments and current status.
  `second bot` 與 `kimiclaw bot` 都從此檔案讀取以確定任務指派與當前狀態。

- Only `second bot` has write permissions to this file.
  只有 `second bot` 具有此檔案的寫入權限。

---

## 3. Required Task Fields / 必填欄位

| Field / 欄位 | Type / 類型 | Description / 說明 | Example / 範例 |
|--------------|-------------|-------------------|----------------|
| `task_id` | string | Unique task identifier / 唯一任務識別碼 | `"T-007"` |
| `title` | string | Brief task description / 簡短任務描述 | `"建立 Task Schema 規格文件"` |
| `assigned_to` | string | Executor assignment / 執行者指派 | `"kimiclaw_bot"` |
| `status` | string | Current task status / 當前任務狀態 | `"pending"` |
| `priority` | string | Task urgency level / 任務緊急程度 | `"high"` |
| `type` | string | Task category / 任務類別 | `"documentation"` |
| `goal` | string | Detailed objective / 詳細目標 | `"建立 TASK_SCHEMA.md 文件..."` |
| `output_file` | string | Expected deliverable path / 預期產出路徑 | `"rules/TASK_SCHEMA.md"` |
| `success_condition` | string | Completion criteria / 完成條件 | `"second bot 驗收並更新 state"` |
| `report_to` | string | Supervisor for this task / 此任務的監督者 | `"second_bot"` |
| `depends_on` | array | Task dependencies / 任務依賴 | `["T-001", "T-002"]` |
| `last_updated` | string | ISO 8601 timestamp / ISO 8601 時間戳 | `"2026-04-05T14:50:00+08:00"` |

---

## 4. Optional Task Fields / 選填欄位

| Field / 欄位 | Type / 類型 | Description / 說明 | When to Use / 使用時機 |
|--------------|-------------|-------------------|------------------------|
| `blocker` | object | Blocker report reference / 阻塞回報引用 | When status is `blocked` / 當狀態為 `blocked` 時 |
| `notes` | string | Additional context / 額外上下文 | Any supplementary information / 任何補充資訊 |
| `created_by` | string | Task creator / 任務建立者 | Usually `"Nurgle"` or `"second_bot"` |
| `created_at` | string | Creation timestamp / 建立時間戳 | ISO 8601 format |
| `completed_at` | string | Completion timestamp / 完成時間戳 | Set when status becomes `completed` |
| `reviewed_by` | string | Reviewer identifier / 審查者識別碼 | Usually `"second_bot"` |
| `repo_url` | string | GitHub repository URL / GitHub 倉庫 URL | For GitHub-only workflows |
| `instruction_archive_file` | string | Path to instruction archive / 指令封存檔路徑 | For traceability to original instruction |
| `instruction_anchor` | string | Anchor within archive file / 封存檔內錨點 | Usually same as task_id |
| `instruction_summary` | string | Brief instruction summary / 指令簡要摘要 | For quick reference without opening archive |

---

## 5. Allowed Status Values / 合法狀態值

| Status / 狀態 | Description / 說明 | Description (EN) |
|---------------|-------------------|------------------|
| `pending` | 等待執行 | Awaiting execution |
| `in_progress` | 執行中 | Currently being executed |
| `blocked` | 阻塞 | Execution blocked, needs resolution |
| `completed` | 已完成 | Task finished successfully |
| `paused` | 暫停 | Temporarily suspended |
| `cancelled` | 已取消 | Task cancelled by user or supervisor |

---

## 6. Status Transition Rules / 狀態轉換規則

### 6.1 Who Can Move Which Status / 誰可以移動哪些狀態

| Current Status | Can Be Changed By | To Status |
|----------------|-------------------|-----------|
| `pending` | second bot | `in_progress`, `cancelled` |
| `in_progress` | second bot | `blocked`, `completed`, `paused` |
| `blocked` | second bot | `in_progress`, `cancelled` |
| `paused` | second bot | `in_progress`, `cancelled` |
| `completed` | second bot | (no change allowed) |
| `cancelled` | second bot | (no change allowed) |

**Important**: `kimiclaw_bot` **MUST NOT** directly change task status in `state/tasks.json`. Status updates are handled exclusively by `second bot` after validation.

**重要**: `kimiclaw_bot` **禁止**直接變更 `state/tasks.json` 中的任務狀態。狀態更新僅由 `second bot` 在驗證後處理。

### 6.2 Valid Transitions / 合法轉換

```
pending ──▶ in_progress ──▶ completed
    │           │
    │           ├──▶ blocked ──▶ in_progress
    │           │
    │           └──▶ paused ──▶ in_progress
    │
    └──▶ cancelled
```

### 6.3 Invalid Transitions / 非法轉換

| From / 從 | To / 到 | Reason / 原因 |
|-----------|---------|---------------|
| `completed` | any | Completed tasks are final / 已完成任務為最終狀態 |
| `cancelled` | any | Cancelled tasks are final / 已取消任務為最終狀態 |
| `pending` | `completed` | Must go through `in_progress` / 必須經過 `in_progress` |
| `blocked` | `completed` | Must resolve blocker first / 必須先解決阻塞 |

---

## 7. Write Permissions / 寫入權限

### 7.1 second bot Permissions / second bot 權限

✅ **Allowed Operations / 允許操作**:
- Create new tasks / 建立新任務
- Update task status / 更新任務狀態
- Modify any task field / 修改任何任務欄位
- Delete tasks (rare) / 刪除任務（罕見）

### 7.2 kimiclaw bot Restrictions / kimiclaw bot 限制

❌ **Prohibited Operations / 禁止操作**:
- Directly modify `state/tasks.json` / 直接修改 `state/tasks.json`
- Change task status / 變更任務狀態
- Update `last_updated` timestamp / 更新 `last_updated` 時間戳

✅ **Allowed Operations / 允許操作**:
- Read `state/tasks.json` / 讀取 `state/tasks.json`
- Read assigned tasks / 讀取指派的任務

### 7.3 Enforcement / 強制執行

- `kimiclaw_bot` writes results to `outbox/` or `outputs/`, never to `state/`.
  `kimiclaw_bot` 將結果寫入 `outbox/` 或 `outputs/`，絕不寫入 `state/`。

- `second bot` pulls changes, validates, then updates `state/tasks.json`.
  `second bot` 拉取變更、驗證，然後更新 `state/tasks.json`。

---

## 8. Timestamp Rules / 時間戳規則

### 8.1 Format / 格式

All timestamps must use **ISO 8601** format with timezone:

所有時間戳必須使用含時區的 **ISO 8601** 格式：

```
YYYY-MM-DDTHH:MM:SS+HH:MM
```

Example / 範例:
```
2026-04-05T14:50:00+08:00
```

### 8.2 Required Timestamps / 必填時間戳

| Field / 欄位 | When to Update / 更新時機 |
|--------------|---------------------------|
| `last_updated` | Every time task is modified / 每次任務被修改時 |
| `created_at` | When task is first created / 任務首次建立時 |
| `completed_at` | When status becomes `completed` / 狀態變為 `completed` 時 |

### 8.3 Timezone / 時區

- Default: `Asia/Shanghai` (+08:00)
- 預設: `Asia/Shanghai` (+08:00)

---

## 9. Task ID Naming Convention / 任務 ID 命名規則

### 9.1 Format / 格式

```
T-{sequence_number}
```

### 9.2 Rules / 規則

- Start with `T-` prefix / 以 `T-` 前綴開頭
- Use sequential numbers / 使用連續數字
- No gaps allowed / 不允許間隔
- Case sensitive / 大小寫敏感

### 9.3 Examples / 範例

| Valid / 合法 | Invalid / 非法 | Reason / 原因 |
|--------------|----------------|---------------|
| `T-001` | `t-001` | Wrong case / 大小寫錯誤 |
| `T-007` | `T-7` | Missing leading zeros / 缺少前導零 |
| `T-010` | `Task-010` | Wrong prefix / 錯誤前綴 |
| `T-100` | `T-00100` | Extra leading zero / 多餘前導零 |

---

## 10. Standard JSON Example / 標準 JSON 範例

### 10.1 Pending Task / 等待執行任務

```json
{
  "task_id": "T-008",
  "title": "測試新功能模組",
  "assigned_to": "kimiclaw_bot",
  "status": "pending",
  "priority": "medium",
  "type": "implementation",
  "goal": "實作並測試新功能模組，確保與現有系統相容",
  "output_file": "outbox/T-008_result.json",
  "success_condition": "second bot 驗收測試結果並更新 state",
  "report_to": "second_bot",
  "depends_on": ["T-007"],
  "last_updated": "2026-04-05T15:00:00+08:00",
  "created_by": "Nurgle",
  "created_at": "2026-04-05T15:00:00+08:00"
}
```

### 10.2 Blocked Task / 阻塞任務

```json
{
  "task_id": "T-009",
  "title": "整合外部 API",
  "assigned_to": "kimiclaw_bot",
  "status": "blocked",
  "priority": "high",
  "type": "implementation",
  "goal": "整合第三方 API 服務",
  "output_file": "outbox/T-009_result.json",
  "success_condition": "API 整合完成並通過測試",
  "report_to": "second_bot",
  "depends_on": [],
  "last_updated": "2026-04-05T15:30:00+08:00",
  "blocker": {
    "type": "authentication",
    "severity": "high",
    "summary": "API key 未提供",
    "report_file": "outbox/T-009_blocker.json"
  },
  "notes": "等待使用者提供 API 金鑰"
}
```

### 10.3 Completed Task / 已完成任務

```json
{
  "task_id": "T-007",
  "title": "建立 Task Schema 規格文件",
  "assigned_to": "kimiclaw_bot",
  "status": "completed",
  "priority": "high",
  "type": "documentation",
  "goal": "建立 TASK_SCHEMA.md 文件",
  "output_file": "rules/TASK_SCHEMA.md",
  "success_condition": "second bot 驗收並更新 state",
  "report_to": "second_bot",
  "depends_on": [],
  "last_updated": "2026-04-05T14:55:00+08:00",
  "created_at": "2026-04-05T14:46:00+08:00",
  "completed_at": "2026-04-05T14:55:00+08:00",
  "reviewed_by": "second_bot"
}
```

---

## 11. Validation Notes / 驗證備註

### 11.1 Before Creating Task / 建立任務前

- Verify `task_id` is unique / 確認 `task_id` 唯一
- Check `depends_on` tasks exist / 檢查 `depends_on` 任務存在
- Validate `assigned_to` is valid agent / 驗證 `assigned_to` 為有效代理

### 11.2 Before Updating Status / 更新狀態前

- Verify status transition is valid / 確認狀態轉換合法
- Check all required fields are present / 檢查所有必填欄位存在
- Update `last_updated` timestamp / 更新 `last_updated` 時間戳

### 11.3 Before Marking Completed / 標記完成前

- Verify `output_file` exists in repo / 確認 `output_file` 存在於倉庫
- Check `success_condition` is met / 檢查 `success_condition` 已達成
- Set `completed_at` timestamp / 設定 `completed_at` 時間戳
- Set `reviewed_by` field / 設定 `reviewed_by` 欄位

---

## 12. Relationship to Other Rule Files / 與其他規則文件的關係

```
rules/
├── OPERATING_RULES.md          # General system rules / 一般系統規則
├── DISCORD_TASK_INTAKE.md      # Discord command format / Discord 指令格式
├── BLOCKER_REPORT_FORMAT.md    # Blocker reporting / 阻塞回報格式
└── TASK_SCHEMA.md             # This file / 本文件 (Task state schema / 任務狀態結構)
```

### 12.1 Dependency Graph / 依賴圖

```
OPERATING_RULES.md (root / 根)
    ├── DISCORD_TASK_INTAKE.md
    │       └── creates tasks in / 建立任務至 ──▶ state/tasks.json
    ├── BLOCKER_REPORT_FORMAT.md
    │       └── references / 引用 ──▶ state/tasks.json (blocker field)
    └── TASK_SCHEMA.md (this file / 本文件)
            └── defines / 定義 ──▶ state/tasks.json structure
```

### 12.2 Consistency Requirements / 一致性要求

- All rule files must reference `state/tasks.json` using the schema defined here.
  所有規則文件必須使用此處定義的結構引用 `state/tasks.json`。

- Changes to this schema require updates to all dependent files.
  對此結構的變更需要更新所有相依文件。

---

## 13. Task Instruction Archive Integration / 任務指令封存整合

### 13.1 Purpose / 目的

Task instructions are archived separately from the task state to maintain an immutable record of original user requests. The task state references these archives for traceability.

任務指令與任務狀態分開封存，以保持原始使用者请求的不可變記錄。任務狀態引用這些封存以實現可追溯性。

### 13.2 Archive Fields / 封存欄位

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `instruction_archive_file` | string | Path to archive file containing original instruction | `"tasks/archive/tasks_001_100.md"` |
| `instruction_anchor` | string | Anchor/ID within archive file | `"T-034"` |
| `instruction_summary` | string | Brief summary for quick reference | `"建立每 100 個 task 一份的指令封存系統"` |

### 13.3 Archive File Structure / 封存檔結構

Archives are organized in batches of 100 tasks:

封存檔以每批 100 個任務組織：

```
tasks/archive/
├── README.md              # Archive system documentation
├── tasks_001_100.md       # T-001 ~ T-100
├── tasks_101_200.md       # T-101 ~ T-200
└── tasks_201_300.md       # T-201 ~ T-300
```

### 13.4 Example Task with Archive Reference / 含封存引用的任務範例

```json
{
  "task_id": "T-034",
  "title": "建立 Task Instruction Archive System",
  "assigned_to": "kimiclaw_bot",
  "status": "completed",
  "priority": "high",
  "type": "documentation_and_structure",
  "goal": "建立 task 原始指令封存系統...",
  "output_file": "tasks/archive/tasks_001_100.md",
  "success_condition": "second bot 完成 git pull 驗收...",
  "report_to": "second_bot",
  "last_updated": "2026-04-07T17:30:00+08:00",
  "instruction_archive_file": "tasks/archive/tasks_001_100.md",
  "instruction_anchor": "T-034",
  "instruction_summary": "建立每 100 個 task 一份的指令封存系統"
}
```

### 13.5 Archive Rules / 封存規則

- **Append-Only**: Once written, never modify / 只追加：一旦寫入，永不修改
- **Range-Based**: 100 tasks per file / 基於範圍：每檔 100 個任務
- **Immutable History**: Preserves original instruction exactly as issued / 不可變歷史：完全按發出時保存原始指令

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-07  
**日期**: 2026-04-07
