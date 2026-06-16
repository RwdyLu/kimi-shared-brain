# Rudy Claude Code Studio

這是 Rudy Claude Code Studio 工作區，用來讓 Claude Code 以「AI 自動化公司工作台」的方式協助 Rudy 做研究、企劃、草稿、報告、MVP 設計與安全審查。

這不是直接自動發文或自動交易的系統。第一階段只保留工作台文件、流程規範與輸出模板，不連 API、不建立真實排程、不部署、不自動發布。

## 主要模組

* company/：公司方向、規則、商業模式與安全政策。
* trend-lab/：熱門來源、週報模板、熱點轉內容規則與 backlog。
* departments/：內容、動畫、LINE 貼圖、crypto、數位商品、自動化部門。
* skills/：Claude Code 可讀取的任務技能說明。
* agents/：各角色 subagent 的責任邊界。
* workflows/：從點子、熱點到產出的標準流程。
* scheduled-tasks/：未來排程任務的說明文件，目前只手動執行。
* reports/：研究報告與審查結果。
* outputs/：完成的 AI 產出。

## 使用方式

1. 先讀 CLAUDE.md。
2. 再選一個 workflow。
3. 再選需要的 skill。
4. 研究或草稿輸出到 reports/ 或 outputs/。
5. 任何高風險操作前等待 Rudy 明確確認。

## 第一個建議測試

請 Claude Code 讀取 workflows/scan-trends.md 與 skills/trend-scout/SKILL.md，使用模擬資料產出 reports/test-trend-report.md。不要上網、不要接 API、不要自動發布。
