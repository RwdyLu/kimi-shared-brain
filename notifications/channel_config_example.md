# Notification Channel Configuration Examples / 通知渠道配置範例

**⚠️ EXAMPLE ONLY / 僅供範例**  
**Copy and modify for your use case / 複製並修改以供您的使用場景使用**

---

## Supported Channels / 支援的渠道

| Channel | Type | Description |
|---------|------|-------------|
| Console | `console` | Print to stdout / 輸出到標準輸出 |
| Discord Webhook | `discord_webhook` | Send to Discord channel / 發送到 Discord 頻道 |
| File | `file` | Write to log file / 寫入日誌檔案 |

---

## Configuration Examples / 配置範例

### Example 1: Console Only / 範例 1：僅 Console

```python
from notifications.channels import ChannelConfig, ChannelType, create_console_channel

# Simple console configuration / 簡單的 console 配置
config = ChannelConfig(
    channel_type=ChannelType.CONSOLE
)

channel = create_console_channel()
```

---

### Example 2: Discord Webhook / 範例 2：Discord Webhook

```python
from notifications.channels import ChannelConfig, ChannelType, create_discord_channel

# Discord webhook with fallback / 帶回退的 Discord webhook
config = ChannelConfig(
    channel_type=ChannelType.DISCORD_WEBHOOK,
    webhook_url="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN",
    fallback_to_console=True,  # Fallback to console if Discord fails / Discord 失敗時回退到 console
    timeout_seconds=10,
    retry_count=1
)

channel = create_discord_channel(
    webhook_url="https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN",
    fallback=True
)
```

**⚠️ IMPORTANT / 重要**:  
Replace `YOUR_WEBHOOK_ID` and `YOUR_WEBHOOK_TOKEN` with your actual Discord webhook URL.

---

### Example 3: Multi-Channel / 範例 3：多渠道

```python
from notifications.channels import (
    ChannelConfig, ChannelType, 
    create_multi_channel, create_console_channel, create_discord_channel
)

# Create multiple channels / 建立多個渠道
channels = [
    create_console_channel(),
    create_discord_channel(
        webhook_url="https://discord.com/api/webhooks/...",
        fallback=True
    )
]

multi = create_multi_channel([
    ChannelConfig(channel_type=ChannelType.CONSOLE),
    ChannelConfig(
        channel_type=ChannelType.DISCORD_WEBHOOK,
        webhook_url="https://discord.com/api/webhooks/...",
        fallback_to_console=True
    )
])

# Send to all channels / 發送到所有渠道
results = multi.send_to_all("Test message / 測試訊息")
```

---

## Environment Variable Configuration / 環境變數配置

### Using environment variables / 使用環境變數

```python
import os
from notifications.channels import create_discord_channel

# Read from environment / 從環境讀取
webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

if webhook_url:
    channel = create_discord_channel(webhook_url, fallback=True)
else:
    from notifications.channels import create_console_channel
    channel = create_console_channel()
    print("Warning: DISCORD_WEBHOOK_URL not set, using console / 警告：未設置 DISCORD_WEBHOOK_URL，使用 console")
```

### .env file example / .env 檔案範例

```bash
# Discord webhook URL / Discord webhook URL
# Get this from Discord channel settings → Integrations → Webhooks
# 從 Discord 頻道設定 → 整合 → Webhook 取得
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123456789/abcdef...

# Optional: Set timeout / 可選：設定超時
DISCORD_TIMEOUT_SECONDS=10

# Optional: Set retry count / 可選：設定重試次數
DISCORD_RETRY_COUNT=1
```

---

## Integration with Monitor Runner / 與監測執行器整合

### Option 1: Console Output / 選項 1：Console 輸出

```python
from app.monitor_runner import MonitorRunner
from notifications.channels import create_console_channel

runner = MonitorRunner()
console = create_console_channel()

results, summary = runner.run_monitor_once()

# Send alerts via console / 透過 console 發送提醒
for result in results:
    for signal in result.signals:
        signal_data = {
            "signal_type": signal.signal_type.value,
            "level": signal.level.value,
            "symbol": signal.symbol,
            "warning": signal.warning,
            "reason": signal.reason,
            "price_data": signal.price_data,
            "conditions": signal.conditions
        }
        console.send_alert(signal_data)
```

### Option 2: Discord Webhook / 選項 2：Discord Webhook

```python
from app.monitor_runner import MonitorRunner
from notifications.channels import create_discord_channel

runner = MonitorRunner()
discord = create_discord_channel(
    webhook_url="https://discord.com/api/webhooks/...",
    fallback=True  # Fallback to console if Discord fails
)

results, summary = runner.run_monitor_once()

# Send alerts via Discord / 透過 Discord 發送提醒
for result in results:
    for signal in result.signals:
        signal_data = {
            "signal_type": signal.signal_type.value,
            "level": signal.level.value,
            "symbol": signal.symbol,
            "warning": signal.warning,
            "reason": signal.reason,
            "price_data": signal.price_data,
            "conditions": signal.conditions
        }
        result = discord.send_alert(signal_data)
        if result.fallback_used:
            print(f"Discord failed, used fallback / Discord 失敗，使用回退")
```

### Option 3: Multi-Channel / 選項 3：多渠道

```python
from app.monitor_runner import MonitorRunner
from notifications.channels import create_multi_channel, ChannelConfig, ChannelType

runner = MonitorRunner()
multi = create_multi_channel([
    ChannelConfig(channel_type=ChannelType.CONSOLE),
    ChannelConfig(
        channel_type=ChannelType.DISCORD_WEBHOOK,
        webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
        fallback_to_console=True
    )
])

results, summary = runner.run_monitor_once()

# Send alerts to all channels / 發送提醒到所有渠道
for result in results:
    for signal in result.signals:
        signal_data = {
            "signal_type": signal.signal_type.value,
            "level": signal.level.value,
            "symbol": signal.symbol,
            "warning": signal.warning,
            "reason": signal.reason,
            "price_data": signal.price_data,
            "conditions": signal.conditions
        }
        send_results = multi.send_alert_to_all(signal_data)
        for sr in send_results:
            print(f"Channel {sr.channel}: {sr.message}")
```

---

## Discord Embed Format / Discord Embed 格式

The Discord webhook sends rich embeds with the following format:

### Confirmed Signal / 確認訊號

```json
{
  "title": "✅ TREND LONG",
  "description": "**Reason:** BTCUSDT: close > MA240, MA5 crossed above MA20\n**Warning:** ALERT_ONLY_NO_AUTO_TRADE",
  "color": 65280,
  "fields": [
    {"name": "Close (5m)", "value": "$70,250.00", "inline": true},
    {"name": "MA5", "value": "$70,180.00", "inline": true},
    {"name": "MA20", "value": "$70,050.00", "inline": true},
    {"name": "MA240", "value": "$69,500.00", "inline": true},
    {"name": "Volume Ratio", "value": "2.51x", "inline": true}
  ],
  "footer": {
    "text": "BTCUSDT | Alert-Only System | 2026-04-06 12:00:00 UTC"
  }
}
```

### Watch-Only Signal / 僅觀察訊號

```json
{
  "title": "👁️ CONTRARIAN WATCH OVERHEATED",
  "description": "**Reason:** BTCUSDT 15m: 4 consecutive red candles - potential reversal zone\n**Warning:** WATCH_ONLY_NOT_EXECUTION_SIGNAL",
  "color": 16753920,
  "fields": [
    {"name": "Timeframe", "value": "15m", "inline": true},
    {"name": "Pattern", "value": "overheated", "inline": true},
    {"name": "Consecutive Count", "value": "4", "inline": true}
  ],
  "footer": {
    "text": "BTCUSDT | Alert-Only System | 2026-04-06 12:00:00 UTC"
  }
}
```

---

## Error Handling and Fallback / 錯誤處理與回退

### Fallback Behavior / 回退行為

| Scenario | Behavior |
|----------|----------|
| Discord timeout | Fallback to console if enabled / 如果啟用則回退到 console |
| Discord 4xx/5xx error | Fallback to console if enabled |
| Missing webhook URL | Fallback to console if enabled |
| Console always works | No fallback needed |

### Example with error handling / 帶錯誤處理的範例

```python
from notifications.channels import create_discord_channel, create_console_channel

discord = create_discord_channel(
    webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
    fallback=True  # Will fallback to console if URL is empty or invalid
)

result = discord.send_alert(signal_data)

if result.success:
    print(f"✅ Alert sent via {result.channel}")
elif result.fallback_used:
    print(f"⚠️  Discord failed, used fallback: {result.error}")
else:
    print(f"❌ Failed: {result.error}")
```

---

## Security Notes / 安全注意事項

1. **Webhook URL Security / Webhook URL 安全**
   - Keep webhook URLs private / 保持 webhook URL 私密
   - Do not commit URLs to public repos / 不要將 URL 提交到公開 repo
   - Use environment variables / 使用環境變數

2. **Rate Limiting / 速率限制**
   - Discord webhook: ~30 requests per 60 seconds / Discord webhook：約每 60 秒 30 次請求
   - Built-in rate limiting in fetcher / fetcher 內建速率限制
   - No spam protection in this module / 本模組無垃圾訊息保護

3. **Alert-Only Enforcement / 僅提醒強制**
   - All signals include warning field / 所有訊號包含警告欄位
   - Contrarian signals are always watch-only / 逆勢訊號永遠是僅觀察
   - No auto-trading logic / 無自動交易邏輯

---

## Testing / 測試

### Test console channel / 測試 console 渠道

```python
python3 notifications/channels.py
```

### Test with mock signal / 使用模擬訊號測試

```python
from notifications.channels import create_console_channel

channel = create_console_channel()

mock_signal = {
    "signal_type": "trend_long",
    "level": "confirmed",
    "symbol": "BTCUSDT",
    "warning": "ALERT_ONLY_NO_AUTO_TRADE",
    "reason": "Test signal / 測試訊號",
    "price_data": {"close_5m": 70000.00, "ma5": 69900.00},
    "conditions": {"test": True}
}

result = channel.send_alert(mock_signal)
print(f"Success: {result.success}")
```

---

## Configuration Summary / 配置摘要

| Config | Console | Discord | File |
|--------|---------|---------|------|
| `channel_type` | `ChannelType.CONSOLE` | `ChannelType.DISCORD_WEBHOOK` | `ChannelType.FILE` |
| `webhook_url` | Not needed | Required | Not needed |
| `fallback_to_console` | N/A | Recommended | N/A |
| `timeout_seconds` | N/A | Default: 10 | N/A |
| `retry_count` | N/A | Default: 1 | N/A |

---

**Version**: 1.0.0  
**Last Updated**: 2026-04-06
