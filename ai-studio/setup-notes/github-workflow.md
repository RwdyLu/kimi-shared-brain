# GitHub Workflow

## Branch 規則

所有修改都走 branch，不直接改 main。

Branch 命名：

* setup/...
* feature/...
* workflow/...
* fix/...
* experiment/...

## Commit message

可用前綴：

* setup:
* docs:
* workflow:
* skill:
* agent:
* safety:
* feature:
* fix:

## 每次修改後輸出

* 修改了哪些檔案
* 為什麼修改
* 有沒有風險
* 下一步

## Secrets

不要把 secrets commit 到 GitHub。.env、API keys、tokens、credentials 必須被 .gitignore 排除。高風險修改必須開 PR 等 Rudy 確認。
