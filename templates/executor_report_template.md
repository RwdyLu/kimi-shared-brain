# Executor Report Template
# 執行者回報模板

**Version**: 1.0.0  
**版本**: 1.0.0  
**Template ID**: EXR-001  
**模板識別碼**: EXR-001  
**Used by**: kimiclaw_bot  
**使用者**: kimiclaw_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. Purpose / 目的

Provide a standardized format for kimiclaw_bot to report task execution status, results, and artifacts. This template ensures consistent communication between Executor and Supervisor.

提供 kimiclaw_bot 回報任務執行狀態、結果與產物的標準化格式。此模板確保執行者與監督者之間的溝通一致性。

---

## 2. When to Use / 何時使用

Use this template when:

在以下情況使用此模板：

- Task execution completes successfully / 任務執行成功完成
- Task execution is blocked / 任務執行被阻塞
- Task execution partially completes / 任務執行部分完成
- Reporting intermediate progress (for long tasks) / 回報中間進度（長任務）

---

## 3. Standard Header / 標準標頭

Every executor report must begin with:

每個執行者回報必須以以下內容開頭：

```
[TASK_EXECUTION]
task_id: <TASK_ID>
task_type: <TYPE>
status: <SUCCESS|BLOCKED|PARTIAL>
current_step: <STEP_DESCRIPTION>
result: <SUMMARY>
```

---

## 4. Required Fields / 必填欄位

| Field / 欄位 | Type / 類型 | Description / 說明 | Example / 範例 |
|--------------|-------------|-------------------|----------------|
| `task_id` | string | Task identifier / 任務識別碼 | `"T-011"` |
| `task_type` | string | Category of task / 任務類別 | `"documentation"` |
| `status` | string | `SUCCESS`, `BLOCKED`, or `PARTIAL` / 狀態 | `"SUCCESS"` |
| `current_step` | string | Current execution step / 當前執行步驟 | `"任務完成，已 push 到 GitHub"` |
| `result` | string | Summary of outcome / 結果摘要 | `"Executor Report Template 已建立"` |

---

## 5. Execution Facts Table / 執行事實表格

After the header, always include:

在標頭之後，總是包含：

```markdown
---

**執行事實**:

| 項目 | 值 |
|------|-----|
| repo URL | git@github.com:RwdyLu/kimi-shared-brain.git |
| branch | main |
| commit hash | <COMMIT_HASH> |
| file path | <OUTPUT_FILE_PATH> |
| file size | <BYTES> bytes (<LINES> lines) |
| remote push | ✅ 成功 / ❌ 失敗 |
```

---

## 6. Success Report Template / 成功回報模板

### 6.1 Full Template / 完整模板

```
[TASK_EXECUTION]
task_id: <TASK_ID>
task_type: <TYPE>
status: SUCCESS
current_step: 任務完成，已 push 到 GitHub
result: <RESULT_SUMMARY>

---

**執行事實**:

| 項目 | 值 |
|------|-----|
| repo URL | git@github.com:RwdyLu/kimi-shared-brain.git |
| branch | main |
| commit hash | <COMMIT_HASH> |
| file path | <OUTPUT_FILE_PATH> |
| file size | <BYTES> bytes (<LINES> lines) |
| remote push | ✅ 成功 |

**文件內容**:
- ✅ <SECTION_1>
- ✅ <SECTION_2>
- ✅ <SECTION_3>

等待 <@1487322181032476712> 執行 `git pull` 驗收。
```

### 6.2 Example / 範例

```
[TASK_EXECUTION]
task_id: T-011
task_type: documentation
status: SUCCESS
current_step: 任務完成，已 push 到 GitHub
result: Executor Report Template 已建立

---

**執行事實**:

| 項目 | 值 |
|------|-----|
| repo URL | git@github.com:RwdyLu/kimi-shared-brain.git |
| branch | main |
| commit hash | a1b2c3d |
| file path | templates/executor_report_template.md |
| file size | 8,500 bytes (250 lines) |
| remote push | ✅ 成功 |

**文件內容**:
- ✅ Purpose / 目的
- ✅ When to Use / 何時使用
- ✅ Standard Header / 標準標頭
- ✅ Required Fields / 必填欄位
- ✅ Execution Facts Table / 執行事實表格
- ✅ Success Report Template / 成功回報模板
- ✅ Blocked Report Template / 阻塞回報模板
- ✅ Partial Completion Template / 部分完成模板
- ✅ Bilingual Output Rules / 中英對照規則
- ✅ Formatting Rules / 格式規則
- ✅ Example Reports / 範例回報
- ✅ Relationship to Other Files / 與其他規則文件的關係

等待 <@1487322181032476712> 執行 `git pull` 驗收。
```

---

## 7. Blocked Report Template / 阻塞回報模板

### 7.1 Full Template / 完整模板

```
[TASK_EXECUTION]
task_id: <TASK_ID>
task_type: <TYPE>
status: BLOCKED
current_step: <STEP_WHERE_BLOCKED>
result: <BLOCKER_SUMMARY>

---

**阻塞詳情**:

| 項目 | 值 |
|------|-----|
| blocker_type | <authentication|environment|dependency|ambiguous_requirement> |
| severity | <low|medium|high|critical> |
| summary | <ONE_LINE_DESCRIPTION> |

**已嘗試的解決方案**:
1. <ACTION_1>
2. <ACTION_2>
3. <ACTION_3>

**建議下一步**: <SUGGESTED_SOLUTION>

[QUESTION]
是否需要使用者決策？
當前狀態無法繼續執行，等待 Supervisor 指示。
```

### 7.2 Example / 範例

```
[TASK_EXECUTION]
task_id: T-011
task_type: documentation
status: BLOCKED
current_step: 嘗試 push 到 GitHub
result: GitHub 認證失敗

---

**阻塞詳情**:

| 項目 | 值 |
|------|-----|
| blocker_type | authentication |
| severity | high |
| summary | SSH 金鑰無法驗證 |

**已嘗試的解決方案**:
1. 檢查 ~/.ssh/ 目錄存在
2. 嘗試 SSH clone (失敗)
3. 嘗試 HTTPS clone (需要 token)

**建議下一步**: 請提供 GitHub Personal Access Token 或 SSH 私鑰

[QUESTION]
是否需要使用者決策？
當前狀態無法繼續執行，等待 Supervisor 指示。
```

---

## 8. Partial Completion Template / 部分完成模板

### 8.1 Full Template / 完整模板

```
[TASK_EXECUTION]
task_id: <TASK_ID>
task_type: <TYPE>
status: PARTIAL
current_step: <CURRENT_STEP>
result: <PARTIAL_RESULT_SUMMARY>

---

**已完成項目**:
- ✅ <COMPLETED_ITEM_1>
- ✅ <COMPLETED_ITEM_2>

**待完成項目**:
- ⏳ <PENDING_ITEM_1>
- ⏳ <PENDING_ITEM_2>

**執行進度**: <PERCENTAGE>%

**預估剩餘時間**: <ESTIMATE>

是否需要繼續執行？
```

### 8.2 Example / 範例

```
[TASK_EXECUTION]
task_id: T-011
task_type: documentation
status: PARTIAL
current_step: 已完成前 6 個章節，剩餘 6 個章節
result: Executor Report Template 部分完成

---

**已完成項目**:
- ✅ Purpose / 目的
- ✅ When to Use / 何時使用
- ✅ Standard Header / 標準標頭
- ✅ Required Fields / 必填欄位
- ✅ Execution Facts Table / 執行事實表格
- ✅ Success Report Template / 成功回報模板

**待完成項目**:
- ⏳ Blocked Report Template / 阻塞回報模板
- ⏳ Partial Completion Template / 部分完成模板
- ⏳ Bilingual Output Rules / 中英對照規則
- ⏳ Formatting Rules / 格式規則
- ⏳ Example Reports / 範例回報
- ⏳ Relationship to Other Files / 與其他規則文件的關係

**執行進度**: 50%

**預估剩餘時間**: 10 分鐘

是否需要繼續執行？
```

---

## 9. Bilingual Output Rules / 中英對照規則

### 9.1 Section Headers / 章節標題

Format all section headers in bilingual:

所有章節標題使用中英對照格式：

```markdown
## Section Name / 章節名稱
```

### 9.2 Table Headers / 表格標題

For tables, provide bilingual column headers:

表格提供雙語欄位標題：

```markdown
| Field / 欄位 | Type / 類型 | Description / 說明 |
```

### 9.3 Code Comments / 程式碼註解

Use English for technical terms in code blocks:

程式碼區塊中使用英文技術術語：

```markdown
[TASK_EXECUTION]
task_id: <TASK_ID>  # Task identifier / 任務識別碼
```

### 9.4 Final Line / 結尾行

Always end with the waiting message in Chinese (as per Discord context):

總是以中文等待訊息結尾（依 Discord 上下文）：

```
等待 <@1487322181032476712> 執行 `git pull` 驗收。
```

---

## 10. Formatting Rules / 格式規則

### 10.1 Markdown Standards / Markdown 標準

- Use ATX-style headers (`##`) / 使用 ATX 風格標題
- Use pipe tables for structured data / 使用管道表格呈現結構化資料
- Use code blocks with language tags / 使用帶語言標籤的程式碼區塊
- Use horizontal rules (`---`) to separate sections / 使用水平線分隔章節

### 10.2 Emoji Usage / 表情符號使用

| Emoji | Meaning / 含義 | Usage / 使用 |
|-------|----------------|--------------|
| ✅ | Success / 成功 | Completed items / 已完成項目 |
| ❌ | Failure / 失敗 | Failed operations / 失敗操作 |
| ⏳ | Pending / 等待 | In-progress items / 進行中項目 |
| 📋 | Template / 模板 | Reference to templates / 引用模板 |
| 📝 | Documentation / 文件 | Documentation tasks / 文件任務 |

### 10.3 Discord @mentions / Discord @提及

- Use `<@USER_ID>` format for users / 對使用者使用 `<@USER_ID>` 格式
- Example: `<@1487322181032476712>` for second bot
- Never use `@username` text format (no notification) / 絕不使用 `@username` 文字格式（無通知）

---

## 11. Example Reports / 範例回報

### 11.1 Success Example / 成功範例

```
[TASK_EXECUTION]
task_id: T-006
task_type: documentation
status: SUCCESS
current_step: 任務完成，已 push 到 GitHub
result: Blocker Report Format 規格文件已建立

---

**執行事實**:

| 項目 | 值 |
|------|-----|
| repo URL | git@github.com:RwdyLu/kimi-shared-brain.git |
| branch | main |
| commit hash | 87006a8 |
| file path | rules/BLOCKER_REPORT_FORMAT.md |
| file size | 10,672 bytes |
| remote push | ✅ 成功 |

**文件內容**:
- ✅ Purpose / 目的
- ✅ When to Create a Blocker Report / 何時建立 blocker report
- ✅ Required Fields / 必填欄位
- ✅ Severity Levels / 嚴重程度分級
- ✅ Decision Rules / 決策規則
- ✅ Retry vs Stop Rules / 重試與停止規則
- ✅ Standard JSON Format / 標準 JSON 格式
- ✅ Example Blocker Reports / 範例 blocker reports
- ✅ Supervisor Handling Flow / second bot 處理流程
- ✅ Naming Convention / 命名規則

等待 <@1487322181032476712> 執行 `git pull` 驗收。
```

### 11.2 Blocked Example / 阻塞範例

```
[TASK_EXECUTION]
task_id: T-004
task_type: workflow_test
status: BLOCKED
current_step: 嘗試 clone GitHub repo
result: GitHub 認證失敗，無法存取 private repo

---

**阻塞詳情**:

| 項目 | 值 |
|------|-----|
| blocker_type | authentication |
| severity | high |
| summary | Private repo requires SSH key or token |

**已嘗試的解決方案**:
1. SSH clone without key - 失敗 (Permission denied)
2. HTTPS clone without token - 失敗 (404)
3. 檢查 ~/.ssh/ - 無金鑰

**建議下一步**: 請提供 SSH private key 或 GitHub Personal Access Token

[QUESTION]
是否需要使用者決策？
當前狀態無法繼續執行，等待 Supervisor 指示。
```

### 11.3 Partial Completion Example / 部分完成範例

```
[TASK_EXECUTION]
task_id: T-010
task_type: inventory_and_catalog
status: PARTIAL
current_step: 已完成 8 個章節，剩餘 4 個章節
result: Content Inventory 部分完成

---

**已完成項目**:
- ✅ Purpose / 目的
- ✅ Inventory Scope / 盤點範圍
- ✅ Source Categories / 來源分類
- ✅ Inventory List / 內容總清單
- ✅ Grouped by Category / 依類別分組
- ✅ Grouped by Value Type / 依價值類型分組
- ✅ Candidate Items for GitHub / GitHub 候選項目
- ✅ Needs Rewrite Before Move / 需重寫後再搬的項目

**待完成項目**:
- ⏳ Keep in Chat Only / 僅保留在聊天中的項目
- ⏳ Suggested Target Paths / 建議目標路徑
- ⏳ Migration Readiness / 遷移成熟度
- ⏳ Recommended Next Selection Step / 建議下一步選擇流程

**執行進度**: 67%

**預估剩餘時間**: 15 分鐘

是否需要繼續執行？
```

---

## 12. Relationship to Other Files / 與其他規則文件的關係

```
rules/
├── OPERATING_RULES.md          # General system rules
├── DISCORD_TASK_INTAKE.md      # Discord command format
├── BLOCKER_REPORT_FORMAT.md    # Blocker reporting (referenced for BLOCKED status)
├── TASK_SCHEMA.md             # Task state definitions
└── COMMAND_TEMPLATES.md        # Command templates (uses this report format)

templates/
└── executor_report_template.md # This file
```

### 12.1 Dependencies / 依賴

- **BLOCKER_REPORT_FORMAT.md**: When `status: BLOCKED`, follow the blocker report format from this file
- **TASK_SCHEMA.md**: Task IDs and status values must match schema definitions
- **COMMAND_TEMPLATES.md**: Templates may reference this report format

### 12.2 Used By / 使用者

- **kimiclaw_bot**: Uses this template for all task execution reports
- **second_bot**: Expects this format for validation and processing

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
