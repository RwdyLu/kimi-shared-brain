# Cron Setup Examples / Cron 設定範例

**⚠️ EXAMPLE ONLY / 僅供範例**  
**These are examples for reference / 這些是參考範例**

---

## Overview / 概覽

This document provides examples for setting up the BTC/ETH monitoring system with cron. These are **examples only** — you need to customize them for your environment.

本文件提供使用 cron 設定 BTC/ETH 監測系統的範例。這些**僅供範例**——您需要根據您的環境進行自定義。

---

## Prerequisites / 前置條件

1. Python 3.x installed / 已安裝 Python 3.x
2. Project cloned to `/tmp/kimi-shared-brain` / 專案已 clone 到 `/tmp/kimi-shared-brain`
3. Dependencies installed / 已安裝相依套件
4. (Optional) Discord webhook URL /（可選）Discord webhook URL

---

## Cron Expression Format / Cron 表示式格式

```
* * * * *
│ │ │ │ │
│ │ │ │ └─── Day of week (0-7, Sunday = 0 or 7)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

---

## Example 1: Every 5 Minutes / 範例 1：每 5 分鐘

### Crontab Entry

```bash
*/5 * * * * cd /tmp/kimi-shared-brain && /usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

### With Discord Notification

```bash
*/5 * * * * export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN" && cd /tmp/kimi-shared-brain && /usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification('\$DISCORD_WEBHOOK_URL')" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

---

## Example 2: Every Minute / 範例 2：每分鐘

```bash
* * * * * cd /tmp/kimi-shared-brain && /usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

---

## Example 3: Every Hour / 範例 3：每小時

```bash
0 * * * * cd /tmp/kimi-shared-brain && /usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

---

## Example 4: Specific Times / 範例 4：特定時間

### Business Hours Only (9 AM - 6 PM) / 僅營業時間（上午 9 點 - 下午 6 點）

```bash
*/5 9-18 * * 1-5 cd /tmp/kimi-shared-brain && /usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

### Every 30 Minutes During Active Hours / 活躍時間每 30 分鐘

```bash
*/30 8-22 * * * cd /tmp/kimi-shared-brain && /usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

---

## Example 5: Using Wrapper Script / 範例 5：使用包裝腳本

### Create Script / 建立腳本

Create `/tmp/kimi-shared-brain/run_monitor.sh`:

```bash
#!/bin/bash

# BTC/ETH Monitoring Runner / BTC/ETH 監測執行器
# Alert-Only System / 僅提醒系統

set -e

# Configuration / 配置
PROJECT_DIR="/tmp/kimi-shared-brain"
PYTHON="/usr/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"

# Create log directory / 建立日誌目錄
mkdir -p "$LOG_DIR"

# Load environment variables / 載入環境變數
if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
fi

# Change to project directory / 切換到專案目錄
cd "$PROJECT_DIR"

# Run monitoring / 執行監測
if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    $PYTHON -c "from app.scheduler import run_once_with_notification; run_once_with_notification('$DISCORD_WEBHOOK_URL')" 2>> "$LOG_DIR/cron.log"
else
    $PYTHON -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" 2>> "$LOG_DIR/cron.log"
fi
```

Make executable / 設定可執行：

```bash
chmod +x /tmp/kimi-shared-brain/run_monitor.sh
```

### Crontab Entry

```bash
*/5 * * * * /tmp/kimi-shared-brain/run_monitor.sh
```

---

## Example 6: Environment File / 範例 6：環境檔案

Create `/tmp/kimi-shared-brain/.env`:

```bash
# Discord Webhook URL / Discord Webhook URL
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN

# Log level / 日誌等級
LOG_LEVEL=INFO
```

Update wrapper script to source it (as shown in Example 5).

---

## Cron Schedule Reference / Cron 排程參考

| Schedule | Expression | Description |
|----------|------------|-------------|
| Every minute | `* * * * *` | High frequency / 高頻率 |
| Every 5 minutes | `*/5 * * * *` | Recommended / 建議 |
| Every 10 minutes | `*/10 * * * *` | Balanced / 平衡 |
| Every 15 minutes | `*/15 * * * *` | Conservative / 保守 |
| Every 30 minutes | `*/30 * * * *` | Low frequency / 低頻率 |
| Every hour | `0 * * * *` | Minimal / 最低 |
| Business hours | `*/5 9-18 * * 1-5` | Mon-Fri 9-6 / 週一至週五 9-6 |
| Market hours | `*/5 0-23 * * *` | 24/7 / 全天候 |

---

## Setup Instructions / 設定步驟

### Step 1: Edit Crontab / 步驟 1：編輯 Crontab

```bash
crontab -e
```

### Step 2: Add Entry / 步驟 2：新增項目

Add one of the example lines above.

### Step 3: Save and Exit / 步驟 3：儲存並退出

Save the file (Ctrl+O, Enter, Ctrl+X for nano).

### Step 4: Verify / 步驟 4：驗證

```bash
# List cron jobs
crontab -l

# Check cron service status
sudo systemctl status cron
```

### Step 5: Monitor Logs / 步驟 5：監控日誌

```bash
# Watch log file
tail -f /tmp/kimi-shared-brain/logs/cron.log

# Check for errors
grep -i error /tmp/kimi-shared-brain/logs/cron.log
```

---

## Log Rotation / 日誌輪替

Create `/tmp/kimi-shared-brain/logs/logrotate.conf`:

```
/tmp/kimi-shared-brain/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 user user
}
```

Add to system logrotate:

```bash
sudo cp /tmp/kimi-shared-brain/logs/logrotate.conf /etc/logrotate.d/kimi-monitor
```

---

## Important Notes / 重要注意事項

### ⚠️ Alert-Only System / 僅提醒系統

```
╔══════════════════════════════════════════════════════════════════╗
║  CRON SETUP IS FOR ALERTS ONLY                                   ║
║  CRON 設定僅供提醒使用                                               ║
║                                                                  ║
║  • Generates alerts on schedule / 按排程產生提醒                      ║
║  • No automatic trading / 無自動交易                                 ║
║  • Requires human review / 需要人工審查                              ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ Rate Limiting / 速率限制

- Binance API has limits / Binance API 有限制
- Each run makes ~6 API calls / 每次執行約 6 次 API 呼叫
- 1-minute intervals: ~360 calls/hour / 1 分鐘間隔：約 360 次/小時
- Recommended: 5-minute intervals or longer / 建議：5 分鐘或更長間隔

### ⚠️ Resource Usage / 資源使用

- CPU: Low / 低
- Memory: ~20 MB per run / 每次執行約 20 MB
- Disk: Log files grow over time / 日誌檔案隨時間增長

---

## Troubleshooting / 故障排除

### Cron Not Running / Cron 未執行

```bash
# Check cron service
sudo systemctl status cron

# Restart cron service
sudo systemctl restart cron

# Check cron logs
grep CRON /var/log/syslog
```

### Permission Denied / 權限被拒

```bash
# Make script executable
chmod +x /tmp/kimi-shared-brain/run_monitor.sh

# Check file ownership
ls -la /tmp/kimi-shared-brain/
```

### Python Not Found / 找不到 Python

```bash
# Find Python path
which python3

# Use full path in cron
/usr/bin/python3 instead of python3
```

### Environment Variables Not Set / 環境變數未設定

```bash
# Use wrapper script that sources .env
# Or set variables in crontab
*/5 * * * * export VAR=value; /path/to/script
```

---

## Security Considerations / 安全考量

1. **Webhook URL Security / Webhook URL 安全**
   - Don't commit to git / 不要提交到 git
   - Use environment variables / 使用環境變數
   - Restrict file permissions / 限制檔案權限

2. **File Permissions / 檔案權限**
   ```bash
   chmod 600 /tmp/kimi-shared-brain/.env
   chmod 700 /tmp/kimi-shared-brain/run_monitor.sh
   ```

3. **Log Security / 日誌安全**
   - Logs may contain sensitive data / 日誌可能包含敏感資料
   - Rotate logs regularly / 定期輪替日誌
   - Secure log directory / 保護日誌目錄

---

## Alternative: Systemd Timer / 替代方案：Systemd Timer

For systems using systemd / 對於使用 systemd 的系統：

### Create Service / 建立服務

`/etc/systemd/system/kimi-monitor.service`:

```ini
[Unit]
Description=BTC/ETH Monitoring System
After=network.target

[Service]
Type=oneshot
User=youruser
WorkingDirectory=/tmp/kimi-shared-brain
ExecStart=/usr/bin/python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()"
Environment=DISCORD_WEBHOOK_URL=your_webhook_url
```

### Create Timer / 建立計時器

`/etc/systemd/system/kimi-monitor.timer`:

```ini
[Unit]
Description=Run BTC/ETH monitoring every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
```

### Enable and Start / 啟用並啟動

```bash
sudo systemctl daemon-reload
sudo systemctl enable kimi-monitor.timer
sudo systemctl start kimi-monitor.timer
```

---

## Version / 版本

- **Version**: 1.0.0
- **Date**: 2026-04-06
- **Task**: T-030

---

**⚠️ Remember**: These are examples only. Customize for your environment.
