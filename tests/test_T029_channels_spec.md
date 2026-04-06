# T-029 Test Specification / 測試規格

**Task ID**: T-029  
**Title**: Notification Channel Integration / 通知渠道整合  
**Type**: Manual Validation / 手動驗證

---

## Test Overview / 測試概覽

Verify that the notification channels module works correctly for:
- Console output / Console 輸出
- Discord webhook (with fallback) / Discord webhook（含回退）
- Multi-channel sending / 多渠道發送

---

## Prerequisites / 前置條件

```bash
# Ensure you're in the project directory
cd /tmp/kimi-shared-brain

# Verify Python is available
python3 --version

# Pull latest changes
git pull origin main
```

---

## Test Cases / 測試案例

### TC-001: Module Import Test / 模組匯入測試

**Purpose**: Verify the channels module can be imported

**Steps**:
```python
python3 -c "
from notifications.channels import (
    ChannelType, ChannelConfig, SendResult,
    BaseChannel, ConsoleChannel, DiscordWebhookChannel, MultiChannel,
    create_console_channel, create_discord_channel, create_multi_channel
)
print('✅ All imports successful')
"
```

**Expected Result**: All imports succeed without errors

**Status**: ⬜ Not tested

---

### TC-002: Console Channel - Send Message / Console 渠道 - 發送訊息

**Purpose**: Verify console channel prints messages correctly

**Steps**:
```python
python3 -c "
from notifications.channels import create_console_channel

channel = create_console_channel()
result = channel.send('Test message from T-029')

print(f'Success: {result.success}')
print(f'Channel: {result.channel}')
print(f'Message: {result.message}')
"
```

**Expected Result**:
- Message printed to console with formatting
- `result.success` is `True`
- `result.channel` is `"console"`

**Status**: ⬜ Not tested

---

### TC-003: Console Channel - Send Alert / Console 渠道 - 發送提醒

**Purpose**: Verify console channel formats and prints alerts correctly

**Steps**:
```python
python3 -c "
from notifications.channels import create_console_channel

channel = create_console_channel()

signal_data = {
    'signal_type': 'trend_long',
    'level': 'confirmed',
    'symbol': 'BTCUSDT',
    'warning': 'ALERT_ONLY_NO_AUTO_TRADE',
    'reason': 'BTCUSDT: close > MA240, MA5 crossed above MA20',
    'price_data': {
        'close_5m': 70250.00,
        'ma5': 70180.00,
        'ma20': 70050.00,
        'ma240': 69500.00,
        'volume_ratio': 2.51
    },
    'conditions': {
        'c1_above_ma240': True,
        'c2_ma_cross_above': True,
        'c3_volume_spike': True
    }
}

result = channel.send_alert(signal_data)
print(f'Success: {result.success}')
"
```

**Expected Result**:
- Formatted alert printed with:
  - Signal type and emoji
  - Symbol and level
  - Warning message
  - Price data (if available)
- `result.success` is `True`

**Status**: ⬜ Not tested

---

### TC-004: Discord Channel - Initialization (No URL) / Discord 渠道 - 初始化（無 URL）

**Purpose**: Verify Discord channel falls back when no webhook URL provided

**Steps**:
```python
python3 -c "
from notifications.channels import ChannelConfig, ChannelType, DiscordWebhookChannel

# Try to create without URL (should fail)
try:
    config = ChannelConfig(
        channel_type=ChannelType.DISCORD_WEBHOOK,
        webhook_url=None
    )
    channel = DiscordWebhookChannel(config)
    print('❌ Should have raised ValueError')
except ValueError as e:
    print(f'✅ Correctly raised ValueError: {e}')
"
```

**Expected Result**:
- `ValueError` is raised with message about missing webhook_url

**Status**: ⬜ Not tested

---

### TC-005: Discord Channel - Fallback to Console / Discord 渠道 - 回退到 Console

**Purpose**: Verify Discord channel falls back to console on invalid URL

**Steps**:
```python
python3 -c "
from notifications.channels import create_discord_channel

# Create with invalid URL but fallback enabled
channel = create_discord_channel(
    webhook_url='https://invalid-url.test/webhook',
    fallback=True
)

result = channel.send('Test message')

print(f'Success: {result.success}')
print(f'Fallback used: {result.fallback_used}')
print(f'Error: {result.error}')
"
```

**Expected Result**:
- `result.success` is `True` (because fallback worked)
- `result.fallback_used` is `True`
- `result.error` contains error details
- Message printed to console

**Status**: ⬜ Not tested

---

### TC-006: Discord Channel - Embed Building / Discord 渠道 - Embed 建立

**Purpose**: Verify Discord embed is built correctly from signal data

**Steps**:
```python
python3 -c "
from notifications.channels import ChannelConfig, ChannelType, DiscordWebhookChannel

# Create a test channel (won't actually send)
config = ChannelConfig(
    channel_type=ChannelType.DISCORD_WEBHOOK,
    webhook_url='https://test.example/webhook'
)
channel = DiscordWebhookChannel(config)

signal_data = {
    'signal_type': 'trend_long',
    'level': 'confirmed',
    'symbol': 'BTCUSDT',
    'warning': 'ALERT_ONLY_NO_AUTO_TRADE',
    'reason': 'Test reason',
    'price_data': {
        'close_5m': 70250.00,
        'ma5': 70180.00,
        'volume_ratio': 2.5
    },
    'conditions': {'test': True}
}

embed = channel._build_embed(signal_data)

print('Embed structure:')
print(f'  Title: {embed.get(\"title\")}')
print(f'  Color: {embed.get(\"color\")}')
print(f'  Fields count: {len(embed.get(\"fields\", []))}')
print(f'  Has footer: {\"footer\" in embed}')
print('✅ Embed built successfully')
"
```

**Expected Result**:
- Embed has title with emoji
- Embed has color (green for trend_long)
- Embed has fields with price data
- Embed has footer with timestamp

**Status**: ⬜ Not tested

---

### TC-007: Multi-Channel - Send to All / 多渠道 - 發送到所有

**Purpose**: Verify multi-channel sender sends to all configured channels

**Steps**:
```python
python3 -c "
from notifications.channels import (
    create_multi_channel, create_console_channel,
    ChannelConfig, ChannelType
)

# Create multi-channel with console and discord (with fallback)
multi = create_multi_channel([
    ChannelConfig(channel_type=ChannelType.CONSOLE),
    ChannelConfig(
        channel_type=ChannelType.DISCORD_WEBHOOK,
        webhook_url='https://invalid-url.test/webhook',
        fallback_to_console=True
    )
])

results = multi.send_to_all('Test message for multi-channel')

print(f'Results count: {len(results)}')
for r in results:
    print(f'  Channel: {r.channel}, Success: {r.success}, Fallback: {r.fallback_used}')
"
```

**Expected Result**:
- 2 results returned
- First result: console channel, success=True
- Second result: discord_webhook channel, success=True (fallback), fallback_used=True

**Status**: ⬜ Not tested

---

### TC-008: Integration with Signal Data / 與訊號資料整合

**Purpose**: Verify channels work with actual signal data format

**Steps**:
```python
python3 -c "
from notifications.channels import create_console_channel
from signals.engine import Signal, SignalType, SignalLevel
import time

# Create a signal
signal = Signal(
    signal_type=SignalType.TREND_LONG,
    level=SignalLevel.CONFIRMED,
    symbol='BTCUSDT',
    timestamp=int(time.time() * 1000),
    price_data={
        'close_5m': 70250.00,
        'ma5': 70180.00,
        'ma20': 70050.00,
        'ma240': 69500.00,
        'volume_ratio': 2.51
    },
    conditions={
        'c1_above_ma240': True,
        'c2_ma_cross_above': True,
        'c3_volume_spike': True
    },
    reason='BTCUSDT: close > MA240, MA5 crossed above MA20',
    warning='ALERT_ONLY_NO_AUTO_TRADE'
)

# Convert to dict
signal_data = {
    'signal_type': signal.signal_type.value,
    'level': signal.level.value,
    'symbol': signal.symbol,
    'warning': signal.warning,
    'reason': signal.reason,
    'price_data': signal.price_data,
    'conditions': signal.conditions
}

# Send via console
channel = create_console_channel()
result = channel.send_alert(signal_data)

print(f'✅ Signal sent: {result.success}')
"
```

**Expected Result**:
- Signal data is correctly formatted
- Alert is printed with all signal details
- `result.success` is `True`

**Status**: ⬜ Not tested

---

### TC-009: Watch-Only Signal Formatting / 僅觀察訊號格式化

**Purpose**: Verify watch-only signals are properly marked

**Steps**:
```python
python3 -c "
from notifications.channels import create_console_channel

channel = create_console_channel()

# Contrarian watch signal
signal_data = {
    'signal_type': 'contrarian_watch_overheated',
    'level': 'watch_only',
    'symbol': 'ETHUSDT',
    'warning': 'WATCH_ONLY_NOT_EXECUTION_SIGNAL',
    'reason': 'ETHUSDT 15m: 4 consecutive red candles',
    'price_data': {
        'timeframe': '15m',
        'pattern': 'overheated',
        'consecutive_count': 4
    },
    'conditions': {'pattern_detected': True}
}

result = channel.send_alert(signal_data)
print(f'✅ Watch-only signal sent: {result.success}')
"
```

**Expected Result**:
- Alert shows "WATCH ONLY" indicator
- Warning message is prominently displayed
- Price data includes pattern information

**Status**: ⬜ Not tested

---

## Validation Checklist / 驗證清單

| Test Case | Description | Status |
|-----------|-------------|--------|
| TC-001 | Module import | ⬜ |
| TC-002 | Console send message | ⬜ |
| TC-003 | Console send alert | ⬜ |
| TC-004 | Discord init (no URL) | ⬜ |
| TC-005 | Discord fallback | ⬜ |
| TC-006 | Discord embed building | ⬜ |
| TC-007 | Multi-channel send | ⬜ |
| TC-008 | Integration with signals | ⬜ |
| TC-009 | Watch-only formatting | ⬜ |

**Overall Status**: ⬜ Pending

---

## Quick Test Script / 快速測試腳本

Save as `test_channels_quick.py`:

```python
#!/usr/bin/env python3
"""Quick test for notification channels / 通知渠道快速測試"""

import sys
sys.path.insert(0, '/tmp/kimi-shared-brain')

from notifications.channels import (
    create_console_channel, create_discord_channel, create_multi_channel,
    ChannelConfig, ChannelType
)

print("="*60)
print("T-029: Notification Channel Quick Test")
print("="*60)

# Test 1: Console channel
print("\n[1/4] Testing console channel...")
console = create_console_channel()
result = console.send("Test message")
assert result.success, "Console send failed"
print("✅ Console channel works")

# Test 2: Discord with fallback
print("\n[2/4] Testing Discord fallback...")
discord = create_discord_channel(
    webhook_url="https://invalid.test/webhook",
    fallback=True
)
result = discord.send("Test with fallback")
assert result.success, "Discord fallback failed"
assert result.fallback_used, "Fallback should be used"
print("✅ Discord fallback works")

# Test 3: Send alert
print("\n[3/4] Testing alert formatting...")
signal_data = {
    "signal_type": "trend_long",
    "level": "confirmed",
    "symbol": "BTCUSDT",
    "warning": "ALERT_ONLY_NO_AUTO_TRADE",
    "reason": "Test signal",
    "price_data": {"close_5m": 70000},
    "conditions": {"test": True}
}
result = console.send_alert(signal_data)
assert result.success, "Alert send failed"
print("✅ Alert formatting works")

# Test 4: Multi-channel
print("\n[4/4] Testing multi-channel...")
multi = create_multi_channel([
    ChannelConfig(channel_type=ChannelType.CONSOLE),
])
results = multi.send_to_all("Multi-channel test")
assert len(results) == 1, "Wrong number of results"
assert all(r.success for r in results), "Some sends failed"
print("✅ Multi-channel works")

print("\n" + "="*60)
print("All tests passed! / 所有測試通過！")
print("="*60)
```

Run with: `python3 test_channels_quick.py`

---

## Notes / 備註

1. **Discord Webhook Testing / Discord Webhook 測試**:
   - Real webhook testing requires a valid Discord webhook URL
   - For safety, tests use invalid URLs to trigger fallback behavior
   - To test with real webhook, set `DISCORD_WEBHOOK_URL` environment variable

2. **Network Requirements / 網路需求**:
   - TC-005 and TC-006 may require network to attempt connection
   - Fallback behavior is the primary testing target

3. **Manual Verification / 手動驗證**:
   - Visual inspection of console output is required
   - Check formatting, emojis, and warning messages

---

**Version**: 1.0.0  
**Last Updated**: 2026-04-06
