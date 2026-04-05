# Kimi Shared Brain
# Kimi 共享大腦

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Repository Purpose / 倉庫目的

Centralized storage for task definitions, execution rules, and output artifacts for the Central Brain multi-agent system.

Central Brain 多代理系統的任務定義、執行規則與產出物的集中儲存庫。

This repository serves as the **single source of truth** for:
- Task state management / 任務狀態管理
- Execution rules and protocols / 執行規則與協定
- Documentation templates / 文件模板
- Output artifacts / 產出物

---

## 2. Core Roles / 核心角色

| Role / 角色 | Agent / 代理 | Responsibilities / 職責 |
|-------------|--------------|------------------------|
| **User / 使用者** | Nurgle | High-level decisions, task creation / 高層決策、任務建立 |
| **Supervisor / 監督者** | second_bot | Task validation, state management, final reporting / 任務驗證、狀態管理、最終回報 |
| **Executor / 執行者** | kimiclaw_bot | Task execution, output generation / 任務執行、產出生成 |

### Communication Flow / 溝通流程

```
User (Nurgle)
    ↓ [NEW_TASK]
Supervisor (second_bot) ←→ GitHub repo
    ↓ [指派任務]
Executor (kimiclaw_bot) ←→ GitHub repo
    ↓ [TASK_EXECUTION]
Supervisor (second_bot)
    ↓ [SUPERVISOR_DECISION]
User (Nurgle)
```

---

## 3. Directory Structure / 目錄結構

```
kimi-shared-brain/
├── README.md                          # This file / 本文件
├── rules/                             # System rules / 系統規則
│   ├── OPERATING_RULES.md            # General system rules
│   ├── DISCORD_TASK_INTAKE.md        # Discord command format
│   ├── BLOCKER_REPORT_FORMAT.md      # Blocker reporting spec
│   ├── TASK_SCHEMA.md                # Task state definitions
│   └── COMMAND_TEMPLATES.md          # Command templates
├── state/                             # State storage / 狀態儲存
│   └── tasks.json                    # Task state (single source of truth)
├── templates/                         # Reusable templates / 可重用模板
│   ├── executor_report_template.md   # Executor output format
│   └── supervisor_decision_template.md # Supervisor decision format
├── outbox/                            # Execution outputs / 執行輸出
│   └── T-XXX_result.json             # Task results
├── outputs/                           # Review documents / 審查文件
│   └── T-XXX_review.md               # Review reports
└── logs/                              # Execution logs / 執行日誌
```

---

## 4. GitHub-only Workflow / GitHub-only 工作流程

### 4.1 Core Principle / 核心原則

All shared work **must** go through GitHub. No local path fallbacks.

所有共享工作**必須**透過 GitHub。不使用本地路徑備案。

### 4.2 Execution Flow / 執行流程

1. **User creates task** / 使用者建立任務
   - Supervisor updates `state/tasks.json`
   - Supervisor assigns to Executor

2. **Executor pulls latest** / 執行者拉取最新
   ```bash
   git pull origin main
   ```

3. **Executor reads task** / 執行者讀取任務
   - Read `state/tasks.json`
   - Read relevant rules from `rules/`

4. **Executor executes** / 執行者執行
   - Generate output
   - Write to appropriate directory

5. **Executor commits and pushes** / 執行者提交並推送
   ```bash
   git add <output_file>
   git commit -m "T-XXX: Description"
   git push origin main
   ```

6. **Supervisor validates** / 監督者驗證
   ```bash
   git pull origin main
   ```
   - Validate output
   - Update `state/tasks.json`
   - Commit and push

7. **Supervisor reports to User** / 監督者回報使用者

### 4.3 Key Rules / 關鍵規則

| Rule / 規則 | Description / 說明 |
|-------------|-------------------|
| SSH only / 僅 SSH | Use `git@github.com:RwdyLu/kimi-shared-brain.git` |
| No local fallback / 無本地備案 | Never use local paths as fallback |
| second_bot writes state / second_bot 寫入狀態 | Only supervisor updates `state/tasks.json` |
| kimiclaw_bot writes outputs / kimiclaw_bot 寫入輸出 | Executor writes to `outbox/`, `outputs/`, `templates/` |

---

## 5. Key Rule Files / 核心規則文件

| File | Purpose | Key Content |
|------|---------|-------------|
| **OPERATING_RULES.md** | General rules | Roles, state ownership, execution flow |
| **DISCORD_TASK_INTAKE.md** | Command format | NEW_TASK format, required fields |
| **BLOCKER_REPORT_FORMAT.md** | Blocker handling | Severity levels, decision rules, JSON format |
| **TASK_SCHEMA.md** | Task structure | Fields, status values, transition rules |
| **COMMAND_TEMPLATES.md** | Command templates | NEW_TASK, EXECUTE_TASK, VALIDATE_TASK templates |

### 5.1 Quick Reference / 快速參考

**Task Status Values**:
- `pending` → `in_progress` → `completed`
- `blocked` (can return to `in_progress`)
- `paused` (can resume)
- `cancelled` (final)

**Severity Levels**:
- `low` → Executor handles
- `medium` → Supervisor decides
- `high` → May escalate to user
- `critical` → Must escalate to user

---

## 6. Common Task Lifecycle / 常見任務生命週期

### 6.1 Standard Documentation Task / 標準文件任務

```
User: NEW_TASK (T-XXX)
       ↓
Supervisor: Update state/tasks.json → status: pending
       ↓
Supervisor: @kimiclaw bot 執行 T-XXX
       ↓
Executor: git pull → read task → execute → push
       ↓
Executor: [TASK_EXECUTION] report
       ↓
Supervisor: git pull → validate → update state → push
       ↓
Supervisor: [SUPERVISOR_DECISION] → final report to User
```

### 6.2 Blocked Task Flow / 阻塞任務流程

```
Executor: [TASK_EXECUTION] status: BLOCKED
       ↓
Executor: [QUESTION] to Supervisor
       ↓
Supervisor: Assess severity
       ↓
Supervisor: Decide OR escalate to User
       ↓
User: Provide decision
       ↓
Supervisor: Update state → Resume task
```

---

## 7. Common Templates / 常用模板

### 7.1 Available Templates / 可用模板

| Template | Location | Used By |
|----------|----------|---------|
| Executor Report | `templates/executor_report_template.md` | kimiclaw_bot |
| Supervisor Decision | `templates/supervisor_decision_template.md` | second_bot |

### 7.2 Template Usage / 模板使用

Copy the template, fill in placeholders (marked with `<angle_brackets>`), and use for consistent reporting.

複製模板，填入佔位符（以 `<角括號>` 標記），用於一致的回報。

---

## 8. Notes for Future Expansion / 後續擴充說明

### 8.1 Planned Additions / 計畫新增

| Item | Target Path | Priority |
|------|-------------|----------|
| Git conventions | `docs/git_conventions.md` | Medium |
| Research criteria | `research/criteria.md` | Medium |
| Risk control principles | `research/risk_control.md` | Medium |

### 8.2 Contribution Guidelines / 貢獻指南

1. All files must be bilingual (English/Chinese) / 所有文件必須雙語
2. Follow existing Markdown formatting / 遵循現有 Markdown 格式
3. Update this README when adding major features / 新增主要功能時更新本 README
4. Use T-XXX commit message format / 使用 T-XXX 提交訊息格式

### 8.3 Active Projects / 進行中專案

Per USER.md:
- **BTC 4H Strategy Filter** (Active research)
- **BTC 1D MR Strategy Monitor** (Maintenance)
- **TSMC MR Strategy** (Maintenance)

---

## Quick Start / 快速開始

### For Users / 給使用者

```
@second bot
NEW_TASK
task_id: T-XXX
title: Task description
assigned_to: kimiclaw_bot
priority: high
type: documentation
goal: Detailed objective
output_file: outbox/T-XXX_result.md
success_condition: Validation criteria
```

### For Executors / 給執行者

```bash
cd /tmp/kimi-shared-brain
git pull origin main
cat state/tasks.json  # Find your task
# Execute task
git add <output>
git commit -m "T-XXX: Description"
git push origin main
```

### For Supervisors / 給監督者

```bash
cd /tmp/kimi-shared-brain
git pull origin main
# Validate output
# Update state/tasks.json
git add state/tasks.json
git commit -m "T-XXX: Mark as completed"
git push origin main
```

---

**Maintained by**: Nurgle, second_bot, kimiclaw_bot  
**維護者**: Nurgle, second_bot, kimiclaw_bot  
**License**: Private / 私有  
**Repository**: `git@github.com:RwdyLu/kimi-shared-brain.git`
