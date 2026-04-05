# Blocker Report Format Specification
# Blocker Report 格式規格

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Define the standard format for reporting blockers encountered during task execution, including severity levels, decision rules, and escalation procedures.

定義任務執行過程中遇到阻塞時的標準回報格式，包含嚴重程度分級、決策規則與升級程序。

---

## 2. When to Create a Blocker Report / 何時建立 Blocker Report

Create a blocker report when:

在以下情況建立 blocker report：

- Executor cannot proceed after exhausting all retry options / 執行者耗盡所有重試選項後仍無法繼續
- External dependency failure blocks task completion / 外部依賴故障導致任務無法完成
- Authentication or access issues prevent task execution / 認證或存取問題導致無法執行
- Environment differences prevent shared workspace access / 環境差異導致無法存取共享工作空間
- Ambiguous task requirements cannot be resolved autonomously / 模糊的任務需求無法自主解決

---

## 3. Required Fields / 必填欄位

| Field / 欄位 | Type / 類型 | Description / 說明 | Example / 範例 |
|--------------|-------------|-------------------|----------------|
| `task_id` | string | Task identifier / 任務識別碼 | `"T-003"` |
| `status` | string | Always `"blocked"` / 固定為 `"blocked"` | `"blocked"` |
| `blocker_type` | string | Category of blocker / 阻塞類別 | `"authentication"` |
| `severity` | string | `low`, `medium`, `high`, or `critical` / 嚴重程度 | `"high"` |
| `summary` | string | Brief description / 簡短描述 | `"SSH clone failed"` |
| `context` | string | Background information / 背景資訊 | `"GitHub repo requires authentication"` |
| `attempted_actions` | array | List of attempted solutions / 已嘗試的解決方案 | `["HTTPS clone", "SSH clone"]` |
| `suggested_next_action` | string | Proposed resolution / 建議下一步 | `"Provide SSH key or token"` |
| `needs_user_decision` | boolean | Whether user input is required / 是否需要使用者決策 | `true` |

---

## 4. Severity Levels / 嚴重程度分級

### `low` / 低
- **Description**: Minor inconvenience, workaround exists / 輕微不便，有替代方案
- **Examples**: Timeout on first attempt, temporary file lock / 首次嘗試超時，暫時檔案鎖定
- **Action**: Retry with delay or use fallback / 延遲重試或使用替代方案
- **Decision**: Executor can handle / 執行者可自行處理

### `medium` / 中
- **Description**: Significant obstacle, may need supervisor input / 顯著障礙，可能需要監督者介入
- **Examples**: Multiple retry failures, unclear task scope / 多次重試失敗，任務範圍不明確
- **Action**: Report to supervisor with [QUESTION] / 以 [QUESTION] 回報監督者
- **Decision**: Supervisor decides / 由監督者決定

### `high` / 高
- **Description**: Critical blocker, requires immediate attention / 關鍵阻塞，需要立即處理
- **Examples**: Authentication failure, environment mismatch / 認證失敗，環境不匹配
- **Action**: Create blocker report, stop execution / 建立 blocker report，停止執行
- **Decision**: Supervisor may escalate to user / 監督者可能升級給使用者

### `critical` / 嚴重
- **Description**: System-level failure, cannot continue / 系統級故障，無法繼續
- **Examples**: Data corruption, security breach, complete service outage / 資料損壞，安全漏洞，完全服務中斷
- **Action**: Immediate escalation to user / 立即升級給使用者
- **Decision**: User must decide / 必須由使用者決定

---

## 5. Decision Rules / 決策規則

### When second bot can decide automatically

second bot 可自動決策的情況：

| Scenario / 情境 | Decision / 決策 |
|-----------------|-----------------|
| Severity = `low` | Approve retry with delay / 批准延遲重試 |
| Severity = `medium`, has clear fallback | Approve fallback approach / 批准替代方案 |
| Minor file path discrepancy | Provide direct content provision / 直接提供內容 |
| Timeout on external API | Approve alternative API or method / 批准替代 API 或方法 |
| Retry count < 3 | Approve additional retry / 批准額外重試 |

### When user decision is required

需要使用者決策的情況：

| Scenario / 情境 | Escalation Reason / 升級原因 |
|-----------------|------------------------------|
| Severity = `critical` | System-level failure / 系統級故障 |
| Severity = `high`, no clear solution | High risk without known fix / 高風險且無已知解決方案 |
| Real trading / API keys involved / 涉及真實交易或 API 金鑰 | Security and financial impact / 安全與財務影響 |
| Mass file deletion requested / 請求大量刪除檔案 | Irreversible destructive action / 不可逆的破壞性操作 |
| Architecture change required / 需要架構變更 | Long-term system impact / 長期系統影響 |
| Specification conflict / 規格衝突 | Ambiguous requirements / 需求模糊 |

---

## 6. Retry vs Stop Rules / 重試與停止規則

### Retry Rules / 重試規則

Executor **MAY retry** when:

執行者**可以重試**的情況：

- First attempt fails due to transient error / 首次嘗試因暫時性錯誤失敗
- Alternative selector or method available / 有替代選擇器或方法可用
- Severity is `low` or `medium` / 嚴重程度為低或中
- Retry count < 3 / 重試次數小於 3

Executor **MUST STOP** when:

執行者**必須停止**的情況：

- Retry count reaches 3 without success / 重試 3 次仍未成功
- Severity is `high` or `critical` / 嚴重程度為高或嚴重
- No alternative solution available / 無替代解決方案
- User decision explicitly required / 明確需要使用者決策

### Stop and Report / 停止並回報

When stopping:

停止時：

1. Set `status` to `"blocked"` / 將 `status` 設為 `"blocked"`
2. Document all `attempted_actions` / 記錄所有 `attempted_actions`
3. Provide clear `suggested_next_action` / 提供明確的 `suggested_next_action`
4. Set `needs_user_decision` appropriately / 適當設定 `needs_user_decision`
5. Write to `outbox/<task_id>_blocker.json` / 寫入 `outbox/<task_id>_blocker.json`
6. Notify supervisor via Discord / 透過 Discord 通知監督者

---

## 7. Standard JSON Format / 標準 JSON 格式

```json
{
  "task_id": "string",
  "status": "blocked",
  "blocker_type": "string",
  "severity": "low|medium|high|critical",
  "summary": "string",
  "context": "string",
  "attempted_actions": [
    "action_1",
    "action_2",
    "action_3"
  ],
  "suggested_next_action": "string",
  "needs_user_decision": true|false,
  "timestamp": "ISO8601",
  "agent": "kimiclaw_bot"
}
```

### Field Descriptions / 欄位說明

| Field | Required | Description |
|-------|----------|-------------|
| `task_id` | Yes | Task identifier |
| `status` | Yes | Fixed value: `"blocked"` |
| `blocker_type` | Yes | Classification of blocker |
| `severity` | Yes | Impact level |
| `summary` | Yes | One-line description |
| `context` | Yes | Detailed background |
| `attempted_actions` | Yes | Array of tried solutions |
| `suggested_next_action` | Yes | Recommended resolution |
| `needs_user_decision` | Yes | Boolean flag |
| `timestamp` | No | When blocker occurred |
| `agent` | No | Reporter identifier |

---

## 8. Example Blocker Reports / 範例 Blocker Reports

### Example 1: No user decision needed

**Scenario**: SSH timeout on first attempt, succeeded on retry

```json
{
  "task_id": "T-007",
  "status": "blocked",
  "blocker_type": "transient_error",
  "severity": "low",
  "summary": "SSH connection timeout on git clone",
  "context": "Initial attempt to clone repo failed with connection timeout after 30 seconds",
  "attempted_actions": [
    "Initial SSH clone attempt",
    "Wait 5 seconds",
    "Retry SSH clone - SUCCESS"
  ],
  "suggested_next_action": "Retry succeeded, continue with task execution",
  "needs_user_decision": false,
  "timestamp": "2026-04-05T15:00:00+08:00",
  "agent": "kimiclaw_bot"
}
```

**Outcome**: second bot approves retry, task continues.

---

### Example 2: User decision needed

**Scenario**: Repository requires authentication, no SSH key available

```json
{
  "task_id": "T-004",
  "status": "blocked",
  "blocker_type": "authentication",
  "severity": "high",
  "summary": "GitHub repository requires authentication",
  "context": "Attempting to clone private repository RwdyLu/kimi-shared-brain. HTTPS clone requires token, SSH clone requires private key. Neither authentication method is available in current environment.",
  "attempted_actions": [
    "HTTPS clone without token - failed",
    "SSH clone without key - failed",
    "Check ~/.ssh/ - no keys found"
  ],
  "suggested_next_action": "Provide SSH private key or GitHub personal access token",
  "needs_user_decision": true,
  "timestamp": "2026-04-05T14:10:00+08:00",
  "agent": "kimiclaw_bot"
}
```

**Outcome**: second bot escalates to user with [ESCALATION] format.

---

## 9. Supervisor Handling Flow / second bot 處理流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. Receive blocker report from executor                    │
│     接收來自執行者的 blocker report                          │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Read outbox/<task_id>_blocker.json                      │
│     讀取 outbox/<task_id>_blocker.json                      │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Assess severity and needs_user_decision                 │
│     評估嚴重程度與 needs_user_decision                      │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
                    ┌─────────┐
                    │ Decision │
                    └────┬────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Low    │    │ Medium  │    │ High/   │
    │ Severity│    │ Severity│    │ Critical│
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
         ▼               ▼               ▼
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Auto-    │    │ Provide  │    │ Escalate │
   │ approve  │    │ fallback │    │ to user  │
   │ retry    │    │ solution │    │          │
   └──────────┘    └──────────┘    └──────────┘
```

### Decision Output Format / 決策輸出格式

**When second bot decides**:

```
[SUPERVISOR_DECISION]
task_id: <task_id>
decision: <decision>
reason: <reason>
next_action: <action>
needs_user_decision: No
```

**When escalating to user**:

```
[ESCALATION]
task_id: <task_id>
問題: <description>
已知事實: <facts>
無法裁定原因: <reason>
需要決策點: <decision_point>
```

---

## 10. Naming Convention / 命名規則

### Default Format / 預設格式

```
outbox/<task_id>_blocker.json
```

### Examples / 範例

| Task ID | Blocker Report Filename |
|---------|------------------------|
| T-001 | `outbox/T-001_blocker.json` |
| T-005 | `outbox/T-005_blocker.json` |
| T-010 | `outbox/T-010_blocker.json` |

### Alternative Names / 替代名稱

If multiple blockers for same task:

如果同一任務有多個 blocker：

```
outbox/<task_id>_blocker_1.json
outbox/<task_id>_blocker_2.json
```

---

## 11. Related Documents / 相關文件

- `rules/OPERATING_RULES.md` - General operating rules / 一般運作規則
- `rules/DISCORD_TASK_INTAKE.md` - Discord task format / Discord 任務格式
- `state/tasks.json` - Task state storage / 任務狀態儲存

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
