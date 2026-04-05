# Git Conventions
# Git 規範

**Version**: 1.0.0  
**版本**: 1.0.0  
**Last Updated**: 2026-04-05  
**最後更新**: 2026-04-05

---

## 1. Purpose / 目的

Establish standardized Git workflows for the Central Brain multi-agent system. These conventions ensure consistent repository access, commit practices, and validation procedures across all agents.

為 Central Brain 多代理系統建立標準化的 Git 工作流程。這些規範確保所有代理的倉庫存取、提交實踐與驗證程序的一致性。

---

## 2. Repository Access Method / 倉庫存取方式

### 2.1 SSH Protocol Only / 僅使用 SSH 協定

All agents must use SSH for GitHub access:

所有代理必須使用 SSH 存取 GitHub：

```bash
git clone git@github.com:RwdyLu/kimi-shared-brain.git
```

**Never use HTTPS** (requires token authentication):

**絕不使用 HTTPS**（需要 token 認證）：

```bash
# ❌ Do not use / 不要使用
https://github.com/RwdyLu/kimi-shared-brain.git
```

### 2.2 SSH Key Location / SSH 金鑰位置

- Private key: `~/.ssh/id_ed25519`
- Public key: `~/.ssh/id_ed25519.pub`
- Known hosts: `~/.ssh/known_hosts`

### 2.3 Verify SSH Access / 驗證 SSH 存取

Before first use, verify SSH access:

首次使用前，驗證 SSH 存取：

```bash
ssh -T git@github.com
# Expected output: Hi RwdyLu! You've successfully authenticated...
```

---

## 3. Commit Message Format / Commit 訊息格式

### 3.1 Standard Format / 標準格式

```
T-{XXX}: {description} ({bilingual_note})
```

### 3.2 Components / 組成部分

| Component | Description | Example |
|-----------|-------------|---------|
| `T-{XXX}` | Task identifier | `T-014` |
| `description` | Brief change summary | `Add git conventions` |
| `bilingual_note` | Optional context | `bilingual, 8 sections` |

### 3.3 Examples / 範例

```bash
# Documentation task
git commit -m "T-014: Add git conventions document (bilingual, 8 sections)"

# Template creation
git commit -m "T-011: Add executor report template (bilingual, 12 sections)"

# State update
git commit -m "T-014: Mark as completed in state/tasks.json"

# README expansion
git commit -m "T-013: Expand README with comprehensive documentation"
```

### 3.4 Message Length / 訊息長度

- Subject line: ≤ 72 characters
- Body (if needed): Wrap at 72 characters
- Use present tense: "Add" not "Added"

---

## 4. Pull Before Validation / 驗收前 Pull 規則

### 4.1 Mandatory Pull / 強制 Pull

Supervisor **must** pull latest changes before validation:

監督者**必須**在驗收前拉取最新變更：

```bash
cd /tmp/kimi-shared-brain
git pull origin main
```

### 4.2 Why Pull First / 為何先 Pull

1. Get executor's latest commit / 獲取執行者的最新提交
2. Avoid merge conflicts / 避免合併衝突
3. Ensure validation is against correct version / 確保驗證針對正確版本

### 4.3 Pull Failure Handling / Pull 失敗處理

If pull fails:

如果 pull 失敗：

1. Check network connectivity / 檢查網路連線
2. Verify SSH access / 驗證 SSH 存取
3. Check for local uncommitted changes / 檢查本地未提交變更
4. Resolve conflicts if any / 如有衝突則解決

---

## 5. Push After Execution / 執行後 Push 規則

### 5.1 Mandatory Push / 強制 Push

Executor **must** push after task completion:

執行者**必須**在任務完成後推送：

```bash
git add <output_file>
git commit -m "T-XXX: Description"
git push origin main
```

### 5.2 Push Checklist / Push 檢查清單

Before pushing, verify:

推送前，驗證：

- [ ] Output file exists / 輸出檔案存在
- [ ] File content is correct / 檔案內容正確
- [ ] Commit message follows format / 提交訊息符合格式
- [ ] Git config user.name and user.email set / Git 設定已設定

### 5.3 Push Failure Handling / Push 失敗處理

If push fails:

如果 push 失敗：

| Error | Cause | Solution |
|-------|-------|----------|
| `rejected: non-fast-forward` | Remote has newer commits / 遠端有較新提交 | `git pull` first, then retry |
| `Permission denied` | SSH key issue / SSH 金鑰問題 | Verify `~/.ssh/id_ed25519` |
| `could not resolve host` | Network issue / 網路問題 | Check connectivity |

---

## 6. Branch Usage Notes / Branch 使用說明

### 6.1 Single Branch Policy / 單一 Branch 政策

Use only `main` branch for all work:

所有工作僅使用 `main` branch：

```bash
git branch  # Should show: * main
```

### 6.2 No Feature Branches / 無 Feature Branch

Do not create feature branches:

不建立 feature branch：

```bash
# ❌ Do not use / 不要使用
git checkout -b feature/T-014
git checkout -b dev
git checkout -b temp
```

### 6.3 Rationale / 理由

- Simplifies workflow / 簡化工作流程
- Reduces merge conflicts / 減少合併衝突
- All changes immediately visible / 所有變更立即可見

---

## 7. File Update Discipline / 檔案更新紀律

### 7.1 Add Specific Files / 添加特定檔案

Add only the files you created/modified:

僅添加你建立/修改的檔案：

```bash
# ✅ Good / 良好
git add templates/executor_report_template.md
git add README.md

# ❌ Avoid / 避免
git add .  # May include unwanted files
```

### 7.2 Check Status Before Commit / 提交前檢查狀態

```bash
git status
# Review the output / 檢查輸出
```

Expected output for executor:

執行者的預期輸出：

```
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        new file:   templates/executor_report_template.md
```

### 7.3 Never Commit State File (Executor) / 絕不提交狀態檔案（執行者）

Executor must **never** commit `state/tasks.json`:

執行者**絕對禁止**提交 `state/tasks.json`：

```bash
# ❌ Forbidden for executor / 執行者禁止
git add state/tasks.json
```

Only supervisor updates state:

僅監督者更新狀態：

```bash
# ✅ Only supervisor / 僅監督者
git add state/tasks.json
git commit -m "T-XXX: Mark as completed"
```

---

## 8. Example Commands / 範例指令

### 8.1 Executor Workflow / 執行者工作流程

```bash
# 1. Navigate to repo / 導航到倉庫
cd /tmp/kimi-shared-brain

# 2. Pull latest / 拉取最新
git pull origin main

# 3. Execute task / 執行任務
# ... create output file ...

# 4. Check status / 檢查狀態
git status

# 5. Add specific file / 添加特定檔案
git add templates/executor_report_template.md

# 6. Commit with proper message / 以適當訊息提交
git commit -m "T-011: Add executor report template (bilingual, 12 sections)"

# 7. Push to GitHub / 推送到 GitHub
git push origin main
```

### 8.2 Supervisor Workflow / 監督者工作流程

```bash
# 1. Navigate to repo / 導航到倉庫
cd /tmp/kimi-shared-brain

# 2. Pull executor's changes / 拉取執行者的變更
git pull origin main

# 3. Validate output / 驗證輸出
# ... review files ...

# 4. Update state / 更新狀態
# ... edit state/tasks.json ...

# 5. Check status / 檢查狀態
git status

# 6. Add state file / 添加狀態檔案
git add state/tasks.json

# 7. Commit / 提交
git commit -m "T-011: Mark as completed in state/tasks.json"

# 8. Push to GitHub / 推送到 GitHub
git push origin main
```

### 8.3 Troubleshooting / 疑難排解

```bash
# Check SSH connection / 檢查 SSH 連線
ssh -T git@github.com

# View commit history / 查看提交歷史
git log --oneline -10

# View remote URL / 查看遠端 URL
git remote -v

# Discard local changes / 捨棄本地變更
git restore <file>

# Reset to remote version / 重置到遠端版本
git reset --hard origin/main
```

---

## Summary / 摘要

| Rule / 規則 | Executor | Supervisor |
|-------------|----------|------------|
| **Access** / 存取 | SSH only | SSH only |
| **Commit format** / 提交格式 | `T-XXX: Description` | `T-XXX: Description` |
| **Pull before work** / 工作前 pull | ✅ Yes | ✅ Yes (before validation) |
| **Push after work** / 工作後 push | ✅ Yes | ✅ Yes |
| **Branch** / Branch | `main` only | `main` only |
| **Update state** / 更新狀態 | ❌ Never | ✅ Only supervisor |
| **File updates** / 檔案更新 | Output files only | State file only |

---

## Related Files / 相關檔案

- `README.md` - Repository overview / 倉庫概覽
- `rules/OPERATING_RULES.md` - General system rules / 一般系統規則
- `templates/executor_report_template.md` - Executor output format / 執行者輸出格式
- `templates/supervisor_decision_template.md` - Supervisor output format / 監督者輸出格式

---

**Established by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Reviewed by**: second_bot  
**審查者**: second_bot  
**Date**: 2026-04-05  
**日期**: 2026-04-05
