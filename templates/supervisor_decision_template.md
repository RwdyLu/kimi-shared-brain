# Supervisor Decision Template
# 監督者決策模板

**Version**: 1.0.0  
**版本**: 1.0.0  
**Template ID**: SPD-001  
**模板識別碼**: SPD-001  
**Used by**: second_bot  
**使用者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. Purpose / 目的

Provide a standardized format for second_bot to report supervisor decisions, validation results, and task state updates. This template ensures consistent communication between Supervisor and User/Executor.

提供 second_bot 回報監督者決策、驗證結果與任務狀態更新的標準化格式。此模板確保監督者與使用者/執行者之間的溝通一致性。

---

## 2. When to Use / 何時使用

Use this template when:

在以下情況使用此模板：

- Task validation is complete / 任務驗證完成
- Decision on task execution is made / 對任務執行做出決策
- Task needs to be paused / 任務需要暫停
- Task needs to be resumed / 任務需要恢復
- Fallback approach is approved / 批准替代方案
- User escalation is required / 需要使用者升級

---

## 3. Standard Header / 標準標頭

Every supervisor decision must begin with:

每個監督者決策必須以以下內容開頭：

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: <DECISION_TYPE>
reason: <REASON>
next_action: <NEXT_STEP>
needs_user_decision: <Yes|No>
```

---

## 4. Required Fields / 必填欄位

| Field / 欄位 | Type / 類型 | Description / 說明 | Example / 範例 |
|--------------|-------------|-------------------|----------------|
| `task_id` | string | Task identifier / 任務識別碼 | `"T-012"` |
| `decision` | string | Decision type / 決策類型 | `"APPROVED"` |
| `reason` | string | Detailed justification / 詳細理由 | `"完整驗收通過..."` |
| `next_action` | string | Recommended next step / 建議下一步 | `"T-012 完成..."` |
| `needs_user_decision` | string | `Yes` or `No` / 是或否 | `"No"` |

---

## 5. Decision Types / 決策類型

### 5.1 APPROVED / 驗收通過

Use when task is validated successfully.

任務驗證成功時使用。

**Criteria**:
- Git pull successful / Git pull 成功
- Content validation passed / 內容驗證通過
- All requirements met / 所有要求達成

### 5.2 BLOCKED / 阻塞

Use when task cannot proceed due to an issue.

任務因問題無法繼續時使用。

**Criteria**:
- Validation failed / 驗證失敗
- Required content missing / 必要內容缺失
- Critical error in output / 輸出中有嚴重錯誤

### 5.3 PAUSED / 暫停

Use when task needs temporary suspension.

任務需要暫時中止時使用。

**Criteria**:
- User request to pause / 使用者要求暫停
- External dependency pending / 等待外部依賴
- Waiting for user input / 等待使用者輸入

### 5.4 RESUME / 恢復

Use when paused task can continue.

暫停任務可以繼續時使用。

**Criteria**:
- Blocker resolved / 阻塞已解決
- User confirms continuation / 使用者確認繼續
- Dependencies available / 依賴可用

### 5.5 FALLBACK / 替代方案

Use when alternative approach is approved.

批准替代方案時使用。

**Criteria**:
- Primary approach blocked / 主要方案被阻塞
- Alternative viable / 替代方案可行
- Risk acceptable / 風險可接受

---

## 6. Success Validation Template / 驗收通過模板

### 6.1 Full Template / 完整模板

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: APPROVED
reason: 完整驗收通過。(1) git pull 成功獲取 <FILE_PATH> (<LINES> 行)；(2) 文件內容驗證：<VALIDATION_DETAILS>；(3) state/tasks.json 已更新為 completed 並 push 到 GitHub。
next_action: <TASK_ID> 完成，<BRIEF_DESCRIPTION>
needs_user_decision: No

───

**<TASK_ID> 最終回報** (給 <@USER_ID>)

✅ 任務完成

```
| 項目    | 值            |
| ----- | ------------ |
| 任務 ID | <TASK_ID>   |
| 標題    | <TITLE>     |
| 狀態    | completed    |
| 執行者   | kimiclaw_bot |
| 審查者   | second_bot   |
```
───

執行事實

**kimiclaw bot 提交**:

```
repo URL:    git@github.com:RwdyLu/kimi-shared-brain.git
branch:      main
commit:      <COMMIT_HASH>
file:        <OUTPUT_FILE>
file size:   <BYTES> bytes (<LINES> 行)
remote push: ✅ 成功
```
**second bot 驗收**:

```
git pull:    ✅ 成功 (獲取 <COMMIT_HASH>)
content:     ✅ 驗證通過 (<VALIDATION_SUMMARY>)
state update:✅ 已更新為 completed
commit:      <STATE_COMMIT>
remote push: ✅ 成功
```
───

文件內容摘要

`**<FILE_NAME>**` 包含：

```
| 章節        | 狀態 |
| --------- | --- |
| <SECTION_1> | ✅  |
| <SECTION_2> | ✅  |
| <SECTION_3> | ✅  |
```
───

結論

**<BRIEF_DESCRIPTION>** 🎉

• <KEY_POINT_1>
• <KEY_POINT_2>
• <KEY_POINT_3>

<@USER_ID>
```

### 6.2 Example / 範例

```
[SUPERVISOR_DECISION]
task_id: T-012
decision: APPROVED
reason: 完整驗收通過。(1) git pull 成功獲取 templates/supervisor_decision_template.md (480 行)；
(2) 文件內容驗證：包含所有 12 個章節 (Purpose, When to Use, Standard Header, Required Fields, 
Decision Types, Success/Blocked/Pause Templates, Bilingual Rules, Formatting Rules, Examples, 
Relationship to Other Files)；(3) state/tasks.json 已更新為 completed 並 push 到 GitHub。
next_action: T-012 完成，Supervisor Decision Template 已建立，可供後續任務直接複製使用
needs_user_decision: No

───

**T-012 最終回報** (給 <@489277595976859649>)

✅ 任務完成

```
| 項目    | 值                           |
| ----- | --------------------------- |
| 任務 ID | T-012                       |
| 標題    | 建立 Supervisor Decision Template |
| 狀態    | completed                   |
| 執行者   | kimiclaw_bot                |
| 審查者   | second_bot                  |
```
───

執行事實

**kimiclaw bot 提交**:

```
repo URL:    git@github.com:RwdyLu/kimi-shared-brain.git
branch:      main
commit:      a1b2c3d
file:        templates/supervisor_decision_template.md
file size:   9,500 bytes (480 行)
remote push: ✅ 成功
```
**second bot 驗收**:

```
git pull:    ✅ 成功 (獲取 a1b2c3d)
content:     ✅ 驗證通過 (12 個章節完整)
state update:✅ 已更新為 completed
commit:      e5f6g7h
remote push: ✅ 成功
```
───

文件內容摘要

`**templates/supervisor_decision_template.md**` 包含：

```
| 章節                                           | 狀態 |
| -------------------------------------------- | --- |
| 1. Purpose / 目的                              | ✅  |
| 2. When to Use / 何時使用                        | ✅  |
| 3. Standard Header / 標準標頭                      | ✅  |
| 4. Required Fields / 必填欄位                      | ✅  |
| 5. Decision Types / 決策類型                       | ✅  |
| 6. Success Validation Template / 驗收通過模板        | ✅  |
| 7. Blocked Decision Template / 阻塞決策模板          | ✅  |
| 8. Pause/Resume Template / 暫停與恢復模板            | ✅  |
| 9. Bilingual Output Rules / 中英對照規則             | ✅  |
| 10. Formatting Rules / 格式規則                    | ✅  |
| 11. Example Decisions / 範例決策                   | ✅  |
| 12. Relationship to Other Files / 與其他規則文件的關係  | ✅  |
```
───

結論

**Supervisor Decision Template 已建立** 🎉

• 格式：中英對照，結構清晰，可直接複製使用
• 正式沉澱 second bot 標準決策輸出格式
• 包含 APPROVED、BLOCKED、PAUSED、RESUME、FALLBACK 五種決策類型
• GitHub-only 工作流程驗證成功

<@489277595976859649>
```

---

## 7. Blocked Decision Template / 阻塞決策模板

### 7.1 Full Template / 完整模板

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: BLOCKED
reason: <VALIDATION_FAILED_REASON>
next_action: 等待 <@USER_ID> 決定下一步
needs_user_decision: Yes

───

**阻塞詳情**

| 項目 | 值 |
|------|-----|
| 任務 ID | <TASK_ID> |
| 狀態 | blocked |
| 阻塞原因 | <BLOCKER_DESCRIPTION> |

**驗證失敗項目**:
- ❌ <FAILED_ITEM_1>
- ❌ <FAILED_ITEM_2>

**已發現的問題**:
1. <ISSUE_1>
2. <ISSUE_2>

**建議解決方案**:
- <SUGGESTED_SOLUTION_1>
- <SUGGESTED_SOLUTION_2>

<@USER_ID> 請決定：
1. 要求執行者修正後重新提交？
2. 接受當前版本（降低驗收標準）？
3. 取消此任務？
```

### 7.2 Example / 範例

```
[SUPERVISOR_DECISION]
task_id: T-012
decision: BLOCKED
reason: 驗收失敗。文件缺少必要章節，無法通過驗收。
next_action: 等待 <@489277595976859649> 決定下一步
needs_user_decision: Yes

───

**阻塞詳情**

| 項目 | 值 |
|------|-----|
| 任務 ID | T-012 |
| 狀態 | blocked |
| 阻塞原因 | 缺少必要章節 |

**驗證失敗項目**:
- ❌ Section 11: Example Decisions 缺失
- ❌ 中英對照格式不一致

**已發現的問題**:
1. 文件僅包含 10 個章節，要求 12 個
2. 部分表格欄位缺少英文對照

**建議解決方案**:
- 要求執行者補充缺少的章節
- 統一表格格式為中英對照

<@489277595976859649> 請決定：
1. 要求執行者修正後重新提交？
2. 接受當前版本（降低驗收標準）？
3. 取消此任務？
```

---

## 8. Pause/Resume Template / 暫停與恢復模板

### 8.1 Pause Template / 暫停模板

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: PAUSED
reason: <PAUSE_REASON>
next_action: 等待 <CONDITION> 後恢復執行
needs_user_decision: No

───

**任務暫停**

| 項目 | 值 |
|------|-----|
| 任務 ID | <TASK_ID> |
| 暫停時間 | <TIMESTAMP> |
| 暫停原因 | <REASON> |
| 預計恢復 | <ESTIMATED_RESUME> |

**當前狀態**:
- 已執行: <COMPLETED_STEPS>
- 待執行: <PENDING_STEPS>
- 執行進度: <PERCENTAGE>%

**恢復條件**:
<RESUME_CONDITION>
```

### 8.2 Resume Template / 恢復模板

```
[SUPERVISOR_DECISION]
task_id: <TASK_ID>
decision: RESUME
reason: <RESUME_REASON>
next_action: 通知執行者繼續執行任務
needs_user_decision: No

───

**任務恢復**

| 項目 | 值 |
|------|-----|
| 任務 ID | <TASK_ID> |
| 恢復時間 | <TIMESTAMP> |
| 恢復原因 | <REASON> |

**阻塞解決**:
✅ <BLOCKER_RESOLVED>

**下一步**:
通知 <@1487322181032476712> (Executor) 繼續執行。
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

### 9.3 Decision Output / 決策輸出

[SUPERVISOR_DECISION] block uses English field names for consistency:

[SUPERVISOR_DECISION] 區塊使用英文欄位名稱以保持一致性：

```
[SUPERVISOR_DECISION]
task_id: T-012
decision: APPROVED
reason: 完整驗收通過...
```

### 9.4 User-Facing Sections / 面向使用者的章節

Final report sections should be in Chinese (as per Discord context):

最終回報章節應使用中文（依 Discord 上下文）：

```
**T-012 最終回報** (給 @Nurgle)

✅ 任務完成
```

---

## 10. Formatting Rules / 格式規則

### 10.1 Markdown Standards / Markdown 標準

- Use ATX-style headers (`##`) / 使用 ATX 風格標題
- Use pipe tables for structured data / 使用管道表格呈現結構化資料
- Use code blocks with language tags / 使用帶語言標籤的程式碼區塊
- Use horizontal rules (`───`) to separate sections / 使用水平線分隔章節

### 10.2 Emoji Usage / 表情符號使用

| Emoji | Meaning / 含義 | Usage / 使用 |
|-------|----------------|--------------|
| ✅ | Success / 成功 | Approved decisions / 通過的決策 |
| ❌ | Failure / 失敗 | Blocked decisions / 阻塞的決策 |
| ⏸️ | Paused / 暫停 | Paused tasks / 暫停的任務 |
| ▶️ | Resumed / 恢復 | Resumed tasks / 恢復的任務 |
| 🎉 | Celebration / 慶祝 | Task completion / 任務完成 |

### 10.3 Discord @mentions / Discord @提及

- Use `<@USER_ID>` format for users / 對使用者使用 `<@USER_ID>` 格式
- Example: `<@489277595976859649>` for Nurgle
- Example: `<@1487322181032476712>` for second bot
- Never use `@username` text format (no notification) / 絕不使用 `@username` 文字格式（無通知）

---

## 11. Example Decisions / 範例決策

### 11.1 Approved Decision / 驗收通過決策

```
[SUPERVISOR_DECISION]
task_id: T-011
decision: APPROVED
reason: 完整驗收通過。git pull 成功，內容驗證通過，state 已更新。
next_action: T-011 完成
needs_user_decision: No

───

**T-011 最終回報** (給 <@489277595976859649>)

✅ 任務完成

```
| 項目    | 值                           |
| ----- | --------------------------- |
| 任務 ID | T-011                       |
| 標題    | 建立 Executor Report Template |
| 狀態    | completed                   |
```

執行事實驗證完成，所有要求達成。
```

### 11.2 Blocked Decision / 阻塞決策

```
[SUPERVISOR_DECISION]
task_id: T-013
decision: BLOCKED
reason: 驗收失敗。輸出檔案與要求不符。
next_action: 等待使用者決定
needs_user_decision: Yes

───

**阻塞詳情**

| 項目 | 值 |
|------|-----|
| 任務 ID | T-013 |
| 狀態 | blocked |
| 阻塞原因 | 輸出格式錯誤 |

**驗證失敗項目**:
- ❌ 缺少必要章節
- ❌ 檔案路徑錯誤

請決定下一步行動。
```

### 11.3 Paused Decision / 暫停決策

```
[SUPERVISOR_DECISION]
task_id: T-014
decision: PAUSED
reason: 等待外部 API 金鑰
next_action: 收到金鑰後恢復執行
needs_user_decision: No

───

**任務暫停**

| 項目 | 值 |
|------|-----|
| 任務 ID | T-014 |
| 暫停時間 | 2026-04-05 15:00 |
| 暫停原因 | 等待外部 API 金鑰 |
| 預計恢復 | 2026-04-06 09:00 |

**當前狀態**:
- 已執行: 第 1-3 步
- 待執行: 第 4-6 步
- 執行進度: 50%
```

---

## 12. Relationship to Other Files / 與其他規則文件的關係

```
rules/
├── OPERATING_RULES.md          # General system rules
├── DISCORD_TASK_INTAKE.md      # Discord command format
├── BLOCKER_REPORT_FORMAT.md    # Blocker reporting
├── TASK_SCHEMA.md             # Task state definitions
└── COMMAND_TEMPLATES.md        # Command templates

templates/
├── executor_report_template.md # Executor output format
└── supervisor_decision_template.md # This file
```

### 12.1 Dependencies / 依賴

- **TASK_SCHEMA.md**: Task states (pending, in_progress, completed, blocked) must match schema
- **BLOCKER_REPORT_FORMAT.md**: BLOCKED decisions may reference blocker reports
- **executor_report_template.md**: Supervisor decisions respond to executor reports

### 12.2 Used By / 使用者

- **second_bot**: Uses this template for all supervisor decisions
- **kimiclaw_bot**: Receives decisions in this format
- **Nurgle**: Receives final reports in this format

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
