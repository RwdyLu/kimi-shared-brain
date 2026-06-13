# Scheduler Module / 排程器模組

**Module**: `app/scheduler.py`  
**Type**: Scheduler Layer / 排程層  
**Status**: ✅ Implemented

---

## Overview / 概覽

The scheduler module provides cron-ready scheduling capabilities for the BTC/ETH monitoring system while maintaining the alert-only design (no auto-trading).

排程器模組為 BTC/ETH 監測系統提供類 cron 的排程功能，同時維持僅提醒設計（無自動交易）。

---

## Features / 功能

| Feature | Status | Description |
|---------|--------|-------------|
| Single-run mode | ✅ | Execute once and exit / 執行一次後退出 |
| Interval mode | ✅ | Run at fixed intervals / 固定間隔執行 |
| Overlap prevention | ✅ | File-based lock to prevent duplicate runs / 檔案鎖防止重疊 |
| Max runs limit | ✅ | Stop after N executions / N 次執行後停止 |
| Logging | ✅ | Console + file logging / Console 與檔案日誌 |
| Statistics | ✅ | Track run history and performance / 追蹤執行歷史與效能 |
| Graceful shutdown | ✅ | Handle Ctrl+C gracefully / 優雅處理 Ctrl+C |
| Notification integration | ✅ | Works with channels.py / 與 channels.py 整合 |

---

## Classes / 類別

### SchedulerConfig

Configuration dataclass for the scheduler.

```python
from app.scheduler import SchedulerConfig, SchedulerMode

config = SchedulerConfig(
    mode=SchedulerMode.INTERVAL,      # ONCE, INTERVAL, CRON
    interval_minutes=5,                # Minutes between runs
    max_runs=100,                      # Max executions (None = infinite)
    prevent_overlap=True,              # Prevent overlapping runs
    log_file="/path/to/scheduler.log", # Log file path
    enable_file_logging=True           # Enable file logging
)
```

### SchedulerLock

File-based lock for preventing overlapping executions.

```python
from app.scheduler import SchedulerLock

lock = SchedulerLock("/path/to/lock.file")

if lock.acquire():
    try:
        # Run monitoring
        pass
    finally:
        lock.release()
else:
    print("Another instance is running")
```

### MonitoringScheduler

Main scheduler class.

```python
from app.scheduler import MonitoringScheduler, SchedulerConfig

scheduler = MonitoringScheduler(config=config)

# Run once
record = scheduler.run_once()

# Run at intervals
scheduler.run_interval(interval_minutes=5)

# Get statistics
stats = scheduler.get_statistics()
```

---

## Usage / 使用方式

### Option 1: Run Once / 執行一次

```python
from app.scheduler import run_once_with_notification

# Console output only
result = run_once_with_notification()

# With Discord notification
result = run_once_with_notification("https://discord.com/api/webhooks/...")

print(f"Success: {result.success}")
print(f"Signals: {result.signals_generated}")
```

### Option 2: Run Every 5 Minutes / 每 5 分鐘執行

```python
from app.scheduler import run_every_5_minutes

# Run indefinitely
run_every_5_minutes()

# Run max 10 times
run_every_5_minutes(max_runs=10)

# With Discord
run_every_5_minutes(
    webhook_url="https://discord.com/api/webhooks/...",
    max_runs=100
)
```

### Option 3: Custom Configuration / 自定義配置

```python
from app.scheduler import (
    MonitoringScheduler, SchedulerConfig, SchedulerMode,
    create_console_channel, create_discord_channel
)

# Create multi-channel notification
channel = create_discord_channel(
    webhook_url="https://discord.com/api/webhooks/...",
    fallback=True
)

# Configure scheduler
config = SchedulerConfig(
    mode=SchedulerMode.INTERVAL,
    interval_minutes=3,
    max_runs=50,
    prevent_overlap=True
)

# Create and run scheduler
scheduler = MonitoringScheduler(config=config, notification_channel=channel)
scheduler.run_interval()
```

### Option 4: Manual Mode / 手動模式

```python
from app.scheduler import MonitoringScheduler

scheduler = MonitoringScheduler()

# Run once manually
record = scheduler.run_once()

# Check statistics
stats = scheduler.get_statistics()
print(f"Total runs: {stats['total_runs']}")
print(f"Signals: {stats['total_signals']}")
```

---

## Safety Features / 安全功能

### 1. Overlap Prevention / 重疊防止

```python
# File-based lock ensures only one instance runs at a time
# 檔案鎖確保同一時間只有一個實例執行

config = SchedulerConfig(prevent_overlap=True)
scheduler = MonitoringScheduler(config=config)

# If another instance is running, skip this run
# 若另一實例正在執行，跳過這次執行
```

### 2. Max Runs Limit / 最大執行次數限制

```python
# Stop after N runs to prevent infinite execution
# N 次執行後停止，防止無限執行

config = SchedulerConfig(max_runs=100)
scheduler = MonitoringScheduler(config=config)
```

### 3. Graceful Shutdown / 優雅關閉

```python
scheduler = MonitoringScheduler()

# Stop after current run completes
scheduler.stop()

# Or use Ctrl+C during execution
```

---

## Cron Integration / Cron 整合

### System Cron Example / 系統 Cron 範例

Add to crontab:

```bash
# Edit crontab
crontab -e

# Run every 5 minutes
*/5 * * * * cd /tmp/kimi-shared-brain && python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1

# Run every minute (high frequency)
* * * * * cd /tmp/kimi-shared-brain && python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification('YOUR_WEBHOOK_URL')" >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

### Script-based Cron / 腳本型 Cron

Create `run_monitor.sh`:

```bash
#!/bin/bash
cd /tmp/kimi-shared-brain
source venv/bin/activate  # if using virtualenv
python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification('$DISCORD_WEBHOOK_URL')"
```

Then in crontab:

```bash
*/5 * * * * /tmp/kimi-shared-brain/run_monitor.sh >> /tmp/kimi-shared-brain/logs/cron.log 2>&1
```

---

## Log Output / 日誌輸出

### Console Output / Console 輸出

```
[2026-04-06 22:00:00] ============================================================
[2026-04-06 22:00:00] Run #1 started at 2026-04-06 22:00:00
[2026-04-06 22:00:00] ============================================================
[2026-04-06 22:00:05] Run #1 completed
[2026-04-06 22:00:05]   Duration: 5.2s
[2026-04-06 22:00:05]   Symbols: 2/2
[2026-04-06 22:00:05]   Signals: 1 (Confirmed: 1, Watch: 0)
[2026-04-06 22:00:05] Next run at 22:05:00 (in 5 min)
```

### Log File / 日誌檔案

Default location: `/tmp/kimi-shared-brain/logs/scheduler.log`

---

## API Reference / API 參考

### SchedulerMode Enum

| Value | Description |
|-------|-------------|
| `ONCE` | Run once and exit |
| `INTERVAL` | Run at fixed intervals |
| `CRON` | Reserved for future cron-like scheduling |

### MonitoringScheduler Methods

| Method | Description |
|--------|-------------|
| `run_once()` | Execute single monitoring run |
| `run_interval(minutes)` | Run at specified interval |
| `stop()` | Request graceful shutdown |
| `get_statistics()` | Get run history statistics |

### Convenience Functions

| Function | Description |
|----------|-------------|
| `run_once_with_notification(url)` | Single run with optional Discord |
| `run_every_5_minutes(url, max)` | Run every 5 minutes |
| `run_every_minute(url, max)` | Run every minute |

---

## Important Notes / 重要注意事項

### ⚠️ Alert-Only System / 僅提醒系統

```
╔══════════════════════════════════════════════════════════════════╗
║  THIS SCHEDULER IS ALERT-ONLY                                    ║
║  此排程器僅供提醒                                                   ║
║                                                                  ║
║  • Generates alerts only / 僅產生提醒                              ║
║  • No automatic trading / 無自動交易                               ║
║  • Human review required / 需要人工審查                            ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ API Rate Limits / API 速率限制

Binance API has rate limits. The scheduler respects these:
- Built-in rate limiting in `data/fetcher.py`
- Each run makes ~6 API calls (2 symbols × 3 timeframes)
- 1-minute intervals: ~360 calls/hour (well within limits)
- 5-minute intervals: ~72 calls/hour

### ⚠️ Resource Usage / 資源使用

Each monitoring run:
- CPU: Low (simple calculations)
- Memory: ~10-20 MB
- Network: ~50 KB per run
- Duration: 3-10 seconds typically

---

## Troubleshooting / 故障排除

### Issue: "Another instance is running"

**Cause**: Previous run didn't complete or crashed  
**Solution**: Check for stale lock file

```bash
# Check lock file
ls -la /tmp/kimi-shared-brain/.scheduler.lock

# Remove if stale
rm /tmp/kimi-shared-brain/.scheduler.lock
```

### Issue: Discord notifications not working

**Cause**: Invalid webhook URL or network issue  
**Solution**: 
- Check webhook URL
- Enable fallback to console
- Check logs for errors

### Issue: High memory usage

**Cause**: Too many runs without restart  
**Solution**: 
- Set `max_runs` limit
- Restart scheduler periodically
- Check for memory leaks

---

## Examples / 範例

### Example 1: Basic Monitoring / 基礎監測

```python
#!/usr/bin/env python3
from app.scheduler import run_every_5_minutes

# Simple 5-minute monitoring
run_every_5_minutes()
```

### Example 2: With Discord Alerts / 使用 Discord 提醒

```python
#!/usr/bin/env python3
import os
from app.scheduler import run_once_with_notification

webhook = os.getenv("DISCORD_WEBHOOK_URL")
result = run_once_with_notification(webhook)

if result.signals_generated > 0:
    print(f"Alert sent for {result.signals_generated} signals")
```

### Example 3: Custom Schedule / 自定義排程

```python
#!/usr/bin/env python3
from app.scheduler import MonitoringScheduler, SchedulerConfig

config = SchedulerConfig(
    interval_minutes=10,
    max_runs=100,
    enable_file_logging=True
)

scheduler = MonitoringScheduler(config=config)

print("Starting 10-minute scheduler for 100 runs...")
scheduler.run_interval()

stats = scheduler.get_statistics()
print(f"Completed {stats['total_runs']} runs")
```

---

## Version / 版本

- **Version**: 1.0.0
- **Date**: 2026-04-06
- **Author**: kimiclaw_bot
- **Task**: T-030

---

## See Also / 參見

- `app/monitor_runner.py` - Core monitoring logic
- `notifications/channels.py` - Notification channels
- `ops/cron_example.md` - Cron setup examples
