# Task Instruction Archive System
# 任務指令封存系統

**Version**: 1.0.0  
**Created**: 2026-04-07  
**Maintained by**: Central Brain System

---

## 1. Purpose / 目的

The Task Instruction Archive System preserves the original task instructions as issued by the user (Nurgle). This ensures:

任務指令封存系統保存使用者（Nurgle）發出的原始任務指令。這確保：

- **Historical Reference**: Complete record of what was requested / 歷史參考：完整記錄要求內容
- **Audit Trail**: Traceability from output back to original instruction / 稽核軌跡：從輸出追溯原始指令
- **System Learning**: Pattern analysis for workflow improvement / 系統學習：工作流程改進的模式分析
- **Accountability**: Clear record of task scope and constraints / 問責性：明確的任務範圍與限制記錄

---

## 2. Archive File Naming / 檔名規則

### Format / 格式

```
tasks_{start}_{end}.md
```

### Rules / 規則

| Component | Format | Example |
|-----------|--------|---------|
| Prefix | `tasks_` | Fixed / 固定 |
| Start ID | 3 digits with leading zeros | `001`, `101`, `201` |
| Separator | `_` (underscore) | Fixed / 固定 |
| End ID | 3 digits with leading zeros | `100`, `200`, `300` |
| Extension | `.md` | Markdown format |

### Examples / 範例

| Filename | Range | Status |
|----------|-------|--------|
| `tasks_001_100.md` | T-001 ~ T-100 | ✅ Current archive / 當前封存 |
| `tasks_101_200.md` | T-101 ~ T-200 | ⏳ Future / 未來 |
| `tasks_201_300.md` | T-201 ~ T-300 | ⏳ Future / 未來 |

---

## 3. Range Rule / 每 100 個 Task 一份規則

### Principle / 原則

Each archive file contains exactly **100 task slots** (e.g., T-001~T-100, T-101~T-200).

每份封存檔案恰好包含 **100 個任務槽位**（例如 T-001~T-100、T-101~T-200）。

### When to Create New Archive / 何時建立新封存檔

```
When T-001 created  →  Create tasks_001_100.md
When T-100 reached  →  Archive full, continue using same file
When T-101 created  →  Create tasks_101_200.md
When T-200 reached  →  Archive full
When T-201 created  →  Create tasks_201_300.md
```

### Sparsely Populated Archives / 稀疏填充的封存檔

Archives may be incomplete during normal operation:

封存檔在正常運作期間可能不完整：

```
tasks_001_100.md:
  - T-001: ✅ Present
  - T-002: ✅ Present
  ...
  - T-034: ✅ Present (current)
  - T-035 ~ T-100: ⏳ Reserved (empty for now)
```

---

## 4. Entry Format / 條目格式

### Standard Entry Structure / 標準條目結構

```markdown
### {task_id}

| Field | Value |
|-------|-------|
| **task_id** | {task_id} |
| **title** | {task_title} |
| **created_by** | {creator} |
| **type** | {task_type} |
| **date** | {creation_date} |
| **goal** | {task_goal} |
| **output_file** | {expected_output} |
| **success_condition** | {completion_criteria} |
| **repo_url** | {repository_url} |

**Original Instruction**:
{full_instruction_text}

**Note**: {reconstruction_status_if_applicable}
```

### Reconstruction Status Tags / 還原狀態標籤

| Tag | Meaning | When to Use |
|-----|---------|-------------|
| ✅ Complete | Original instruction fully preserved | Task created after archive system established |
| 🟡 Partial | Partially reconstructed from state | Early tasks before full context logging |
| ⚠️ Summary Only | Only summary available from state | Very early tasks with minimal records |
| ❌ Unavailable | Original instruction lost | Exceptional cases only |

---

## 5. Append-Only Rule / 只追加不重排規則

### Core Principle / 核心原則

> **Once written, never modified.** / **一旦寫入，永不修改。**

### Allowed Operations / 允許操作

✅ **APPEND**: Add new task entries to the current archive
✅ **CREATE**: Create new archive file when current is full
✅ **READ**: Reference archives for historical lookup

### Prohibited Operations / 禁止操作

❌ **EDIT**: Modify existing task entries
❌ **REORDER**: Change the order of entries
❌ **DELETE**: Remove task entries
❌ **MOVE**: Move entries between archives

### Why Append-Only? / 為何只追加？

1. **Immutable History**: Prevents accidental or intentional modification of records / 不可變歷史：防止意外或故意修改記錄
2. **Audit Integrity**: Ensures traceability remains valid / 稽核完整性：確保可追溯性保持有效
3. **System Trust**: All parties can rely on archive accuracy / 系統信任：所有方都可以依賴封存準確性

---

## 6. How to Locate a Task Instruction / 如何查找 Task 原始指令

### Method 1: Direct File Access / 方法 1：直接檔案存取

1. Determine archive range from task ID / 從任務 ID 確定封存範圍
   - T-034 → `tasks_001_100.md`
   - T-156 → `tasks_101_200.md`

2. Open the corresponding archive file / 開啟對應封存檔

3. Search for task header (e.g., `### T-034`) / 搜尋任務標頭

### Method 2: Via Task State / 方法 2：透過任務狀態

1. Read `state/tasks.json` / 讀取 `state/tasks.json`

2. Find the task entry / 找到任務條目
   ```json
   {
     "task_id": "T-034",
     "instruction_archive_file": "tasks/archive/tasks_001_100.md",
     "instruction_anchor": "T-034"
   }
   ```

3. Navigate to specified archive file / 導航至指定封存檔

### Method 3: Schema Reference / 方法 3：結構引用

Task schema includes instruction tracking fields:

任務結構包含指令追蹤欄位：

```json
{
  "task_id": "T-034",
  "title": "建立 Task Instruction Archive System",
  "instruction_archive_file": "tasks/archive/tasks_001_100.md",
  "instruction_anchor": "T-034",
  "instruction_summary": "建立每 100 個 task 一份的指令封存系統"
}
```

---

## 7. Integration with Task Schema / 與 Task Schema 整合

### New Schema Fields / 新增結構欄位

| Field | Type | Description |
|-------|------|-------------|
| `instruction_archive_file` | string | Path to archive file containing original instruction |
| `instruction_anchor` | string | Anchor/ID within archive file (usually same as task_id) |
| `instruction_summary` | string | Brief summary of original instruction for quick reference |

### Example Task Entry with Archive Reference / 含封存引用的任務條目範例

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

---

## 8. Maintenance Guidelines / 維護指南

### For Executors (kimiclaw_bot) / 執行者

- When creating a new task, check if archive file exists / 建立新任務時，檢查封存檔是否存在
- Append task instruction to appropriate archive / 將任務指令追加至適當封存檔
- Update `instruction_*` fields in task state / 更新任務狀態中的 `instruction_*` 欄位

### For Supervisors (second_bot) / 監督者

- Verify archive updates during task creation / 任務建立時驗證封存更新
- Ensure archive integrity during reviews / 審查時確保封存完整性
- Create new archive files when threshold reached / 達到閾值時建立新封存檔

### Archive Lifecycle / 封存生命週期

```
Create Task → Append to Archive → Reference in State → Complete Task
     ↑                                                    |
     └────────────── Next Task ───────────────────────────┘
```

---

## 9. File Structure / 檔案結構

```
tasks/
├── archive/
│   ├── README.md              # This file / 本文件
│   ├── tasks_001_100.md       # Archive for T-001~T-100
│   ├── tasks_101_200.md       # Archive for T-101~T-200 (future)
│   └── tasks_201_300.md       # Archive for T-201~T-300 (future)
└── (other task-related files)
```

---

## 10. Version History / 版本歷史

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-07 | Initial archive system establishment / 初始封存系統建立 |

---

**Established by**: kimiclaw_bot  
**Reviewed by**: second_bot  
**Date**: 2026-04-07
