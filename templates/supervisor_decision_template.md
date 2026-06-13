# Supervisor Decision Template
# 監督者決策模板

**Version**: 1.1.0  
**版本**: 1.1.0  
**Template ID**: SPD-001  
**模板識別碼**: SPD-001  
**Used by**: second_bot  
**使用者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. Purpose / 目的

Provide a standardized format for second_bot to report supervisor decisions, validation results, and task state updates.

提供 second_bot 回報監督者決策、驗證結果與任務狀態更新的標準化格式。

---

## 2. When to Use / 何時使用

- Task validation complete / 任務驗證完成
- Execution decision made / 執行決策做出
- Task needs pause/resume / 任務需要暫停/恢復
- User escalation required / 需要使用者升級

---

## 3. Standard Header / 標準標頭

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: <APPROVED|BLOCKED|PAUSED|RESUME|FALLBACK>
reason: <REASON>
next_action: <NEXT_STEP>
needs_user_decision: <Yes|No>
```

---

## 4. Required Fields / 必填欄位

| Field / 欄位 | Description / 說明 | Format / 格式 |
|--------------|-------------------|---------------|
| `task_id` | Task identifier / 任務識別碼 | `T-XXX` or `T-XXX-patch` |
| `decision` | Decision type / 決策類型 | `APPROVED`, `BLOCKED`, `PAUSED`, `RESUME`, `FALLBACK` |
| `reason` | Justification / 理由 | Concise summary / 簡潔摘要 |
| `next_action` | Next step / 下一步 | Clear instruction / 明確指示 |
| `needs_user_decision` | Requires user input / 需要使用者決定 | **Fixed format** / **固定格式**: `Yes` or `No` |

---

## 5. needs_user_decision Format / needs_user_decision 格式

### 5.1 Fixed Values / 固定值

| Value / 值 | Meaning / 含義 | When to Use / 使用時機 |
|------------|---------------|------------------------|
| `Yes` | User decision required / 需要使用者決定 | BLOCKED, critical issues / 阻塞、關鍵問題 |
| `No` | No user decision needed / 不需要使用者決定 | APPROVED, routine updates / 通過、例行更新 |

### 5.2 Placement Rule / 放置規則

- **Always** include in [SUPERVISOR_DECISION] block / **永遠**包含在 [SUPERVISOR_DECISION] 區塊
- **Never** omit this field / **絕不**省略此欄位
- Use exactly `Yes` or `No` (case-sensitive) / 精確使用 `Yes` 或 `No`（區分大小寫）

---

## 6. Decision Types / 決策類型

| Type / 類型 | Use When / 使用時機 | needs_user_decision |
|-------------|---------------------|---------------------|
| **APPROVED** | Validation passed / 驗證通過 | No |
| **BLOCKED** | Validation failed / 驗證失敗 | Yes |
| **PAUSED** | Temporary stop / 暫時停止 | No |
| **RESUME** | Continue paused task / 恢復暫停任務 | No |
| **FALLBACK** | Alternative approved / 批准替代方案 | No/Yes |

---

## 7. Discord @mention Placeholders / Discord @mention 占位符

### 7.1 Placeholder Format / 占位符格式

| Target / 目標 | Placeholder / 占位符 | Example / 範例 |
|---------------|----------------------|----------------|
| User mention / 使用者提及 | `<@USER_ID>` | `<@489277595976859649>` |
| Executor mention / 執行者提及 | `<@EXECUTOR_ID>` | `<@1487322181032476712>` |
| Role mention / 角色提及 | `<@&ROLE_ID>` | `<@&1483720457244119084>` |

### 7.2 Usage in Templates / 模板中使用

**Correct / 正確**:
```
**最終回報** (給 <@USER_ID>)
通知 <@EXECUTOR_ID> 繼續執行
```

**Incorrect / 錯誤**:
```
**最終回報** (給 <@489277595976859649>)  ← Hardcoded ID / 寫死 ID
通知 @kimiclaw bot 繼續執行              ← Text mention / 文字提及
```

### 7.3 Resolution / 解析

Actual IDs are resolved at runtime from:
- `USER_ID` → `489277595976859649` (Nurgle)
- `EXECUTOR_ID` → `1487322181032476712` (kimiclaw bot)

實際 ID 於執行時從 state/tasks.json 或環境變數解析。

---

## 8. Simplified Templates / 簡化模板

### 8.1 APPROVED (Concise) / 驗收通過（簡潔版）

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: APPROVED
reason: 完整驗收通過。(1) git pull 成功；(2) 內容驗證通過；(3) state 已更新。
next_action: <TASK_ID> 完成，<DESCRIPTION>
needs_user_decision: No

───

**<TASK_ID> 最終回報** (給 <@USER_ID>)

✅ 任務完成

| 項目    | 值             |
| ----- | ------------- |
| 任務 ID | <TASK_ID>     |
| 標題    | <TITLE>       |
| 狀態    | completed     |
| 執行者   | kimiclaw_bot  |
| 審查者   | second_bot    |

執行事實:
- commit: <COMMIT_HASH>
- file: <FILE_PATH>
- validation: ✅ 通過

<@USER_ID>
```

### 8.2 BLOCKED (Concise) / 阻塞（簡潔版）

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: BLOCKED
reason: 驗收失敗。<BRIEF_REASON>
next_action: 等待 <@USER_ID> 決定
needs_user_decision: Yes

───

**阻塞詳情**

| 項目 | 值 |
|------|-----|
| 任務 ID | <TASK_ID> |
| 狀態 | blocked |
| 原因 | <REASON> |

驗證失敗:
- ❌ <ISSUE_1>
- ❌ <ISSUE_2>

<@USER_ID> 請決定下一步。
```

---

## 9. Formatting Rules / 格式規則

### 9.1 Required Elements / 必要元素

| Element / 元素 | Required / 必要 | Example / 範例 |
|----------------|-----------------|----------------|
| [SUPERVISOR_DECISION] block / 區塊 | ✅ | See Section 3 / 見第 3 節 |
| Horizontal separator / 水平分隔 | ✅ | `───` |
| Task summary table / 任務摘要表格 | ✅ | See Section 8 / 見第 8 節 |
| User mention in final report / 最終回報中的使用者提及 | ✅ | `<@USER_ID>` |

### 9.2 Emoji Usage / 表情符號使用

| Emoji | Meaning / 含義 |
|-------|----------------|
| ✅ | Success / 成功 |
| ❌ | Failure / 失敗 |
| 🎉 | Completion / 完成 |

---

## 10. Relationship to Other Files / 與其他文件的關係

- **TASK_SCHEMA.md**: Task states / 任務狀態
- **BLOCKER_REPORT_FORMAT.md**: Blocked decisions / 阻塞決策
- **executor_report_template.md**: Responds to executor reports / 回應執行者報告

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
