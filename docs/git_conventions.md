# Git Conventions
# Git 規範

**Version**: 1.1.0  
**版本**: 1.1.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Standardized Git workflows for Central Brain multi-agent system.

Central Brain 多代理系統的標準化 Git 工作流程。

---

## 2. Repository Access / 倉庫存取

### 2.1 SSH Protocol / SSH 協定

Use SSH for GitHub access:

```bash
git clone git@github.com:RwdyLu/kimi-shared-brain.git
```

**Do not use HTTPS** (requires token):

**不要使用 HTTPS**（需要 token）：

```bash
# ❌ Do not use
https://github.com/RwdyLu/kimi-shared-brain.git
```

### 2.2 SSH Key (Default Example) / SSH 金鑰（預設範例）

**Note**: This is the default key location. Actual setup may vary.

**注意**: 這是預設金鑰位置。實際設定可能不同。

| File / 檔案 | Default Location / 預設位置 |
|-------------|----------------------------|
| Private key / 私鑰 | `~/.ssh/id_ed25519` (example / 範例) |
| Public key / 公鑰 | `~/.ssh/id_ed25519.pub` (example / 範例) |
| Known hosts | `~/.ssh/known_hosts` (example / 範例) |

### 2.3 Verify SSH / 驗證 SSH

```bash
ssh -T git@github.com
# Expected: Hi RwdyLu! You've successfully authenticated...
```

---

## 3. Commit Message Format / Commit 訊息格式

### 3.1 Format / 格式

```
T-{XXX}: {description}
```

### 3.2 Examples / 範例

```bash
git commit -m "T-014: Add git conventions document"
git commit -m "T-011: Add executor report template"
```

---

## 4. Pull Before Validation / 驗收前 Pull

Supervisor **must** pull before validation:

```bash
git pull origin main
```

---

## 5. Push After Execution / 執行後 Push

Executor **must** push after completion:

```bash
git add <output_file>
git commit -m "T-XXX: Description"
git push origin main
```

---

## 6. Branch Policy / Branch 政策

### 6.1 Current Small-Scale Workflow / 當前小規模工作流程

**Policy**: Use `main` branch only.

**政策**: 僅使用 `main` branch。

```bash
git branch  # Should show: * main
```

**Note**: This is a **current small-scale workflow policy**. May change if project scales.

**注意**: 這是**當前小規模工作流程政策**。若專案規模擴大可能變更。

### 6.2 No Feature Branches / 無 Feature Branch

```bash
# ❌ Do not create feature branches
git checkout -b feature/T-014
git checkout -b dev
```

---

## 7. File Update Rules / 檔案更新規則

### 7.1 Add Specific Files / 添加特定檔案

```bash
# ✅ Good - Add specific files
git add templates/executor_report_template.md
git add README.md
```

### 7.2 git add . (With Caution) / git add .（謹慎使用）

**Use only when working tree fully reviewed**:

**僅在 working tree 已完整檢查後使用**：

```bash
# Check status first / 先檢查狀態
git status

# Review all changes / 檢查所有變更
# Only then / 確認後才執行
git add .
```

**Warning**: `git add .` adds all changes. Only use when you have reviewed the entire working tree.

**警告**: `git add .` 會添加所有變更。僅在已檢查完整 working tree 時使用。

### 7.3 Never Commit State (Executor) / 絕不提交狀態（執行者）

Executor must **never** commit `state/tasks.json`:

執行者**禁止**提交 `state/tasks.json`：

```bash
# ❌ Forbidden for executor
git add state/tasks.json
```

Only supervisor updates state.

僅監督者更新狀態。

---

## 8. Quick Reference / 快速參考

| Rule / 規則 | Executor | Supervisor |
|-------------|----------|------------|
| Access / 存取 | SSH | SSH |
| Branch / Branch | `main` only | `main` only |
| Pull / Pull | Before work | Before validation |
| Push / Push | After work | After validation |
| State file / 狀態檔案 | ❌ Never | ✅ Only supervisor |

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
