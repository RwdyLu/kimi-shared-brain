# Kimi Shared Brain
# Kimi 共享大腦

**Version**: 1.1.0  
**版本**: 1.1.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Repository Purpose / 倉庫目的

Centralized storage for Central Brain multi-agent system:
- Task state management / 任務狀態管理
- Execution rules and protocols / 執行規則與協定  
- Documentation templates / 文件模板
- Output artifacts / 產出物

---

## 2. Core Roles / 核心角色

| Role / 角色 | Agent / 代理 | Responsibilities / 職責 |
|-------------|--------------|------------------------|
| **User / 使用者** | Nurgle | High-level decisions / 高層決策 |
| **Supervisor / 監督者** | second_bot | Task validation, state management / 任務驗證、狀態管理 |
| **Executor / 執行者** | kimiclaw_bot | Task execution / 任務執行 |

---

## 3. Directory Structure / 目錄結構

```
kimi-shared-brain/
├── rules/              # System rules / 系統規則
├── state/              # Task states / 任務狀態
├── templates/          # Output templates / 輸出模板
├── outbox/             # Task results / 任務結果
├── outputs/            # Review documents / 審查文件
├── docs/               # Documentation / 說明文件
└── research/           # Research standards / 研究標準
```

---

## 4. GitHub-only Workflow / GitHub-only 工作流程

All shared work **must** go through GitHub. No local path fallbacks.

所有共享工作**必須**透過 GitHub。不使用本地路徑備案。

### 4.1 Basic Flow / 基本流程

1. Supervisor updates `state/tasks.json` / 監督者更新任務狀態
2. Executor: `git pull` → execute → `git push` / 執行者：拉取 → 執行 → 推送
3. Supervisor validates and updates state / 監督者驗證並更新狀態

### 4.2 Key Rules / 關鍵規則

| Rule / 規則 | Description / 說明 |
|-------------|-------------------|
| SSH only / 僅 SSH | `git@github.com:RwdyLu/kimi-shared-brain.git` |
| No local fallback / 無本地備案 | Never use local paths / 絕不使用本地路徑 |
| State ownership / 狀態所有權 | Only second_bot updates `state/tasks.json` |

---

## 5. Key Files / 核心文件

| File / 檔案 | Purpose / 目的 |
|-------------|----------------|
| `rules/OPERATING_RULES.md` | General system rules / 一般系統規則 |
| `rules/DISCORD_TASK_INTAKE.md` | Discord command format / Discord 指令格式 |
| `rules/TASK_SCHEMA.md` | Task structure definitions / 任務結構定義 |
| `state/tasks.json` | Current task states / 當前任務狀態 |

---

## 6. Active Projects / 進行中專案

**Current examples / 當前範例** (per USER.md):

| Project / 專案 | Status / 狀態 | Focus / 重點 |
|----------------|---------------|--------------|
| BTC 4H Strategy Filter | Active research | Strategy screening / 策略篩選 |
| BTC 1D MR Monitor | Maintenance | Performance tracking / 績效追蹤 |
| TSMC MR Strategy | Maintenance | Monitoring / 監控 |

**Note**: See `state/tasks.json` for current task status. See `USER.md` for detailed project notes.

**注意**: 當前任務狀態見 `state/tasks.json`。詳細專案說明見 `USER.md`。

---

## 7. Quick Start / 快速開始

### For Users / 給使用者

```
@second bot
NEW_TASK
task_id: T-XXX
title: Task description
assigned_to: kimiclaw_bot
priority: high
type: documentation
goal: Objective
output_file: outbox/T-XXX_result.json
```

### For Executors / 給執行者

```bash
cd /tmp/kimi-shared-brain
git pull origin main
# Execute task
git add outbox/T-XXX_result.json
git commit -m "T-XXX: Description"
git push origin main
```

**Note**: Output files go to `outbox/T-XXX_result.json` (not .md).

**注意**: 輸出檔案為 `outbox/T-XXX_result.json`（非 .md）。

---

## 8. See Also / 另見

| Document / 文件 | Content / 內容 |
|-----------------|----------------|
| `USER.md` | User preferences and active projects / 使用者偏好與進行中專案 |
| `rules/` | All system rules and templates / 所有系統規則與模板 |
| `docs/git_conventions.md` | Git workflow details / Git 工作流程詳情 |

---

**Maintained by**: Nurgle, second_bot, kimiclaw_bot  
**維護者**: Nurgle, second_bot, kimiclaw_bot  
**Repository**: `git@github.com:RwdyLu/kimi-shared-brain.git`
