# Notification Module / 通知模組

BTC/ETH Monitoring System - Notification Layer
BTC/ETH 監測系統 - 通知層

## Overview / 概覽

This module handles notification delivery for the monitoring system.
Formats signals into human-readable alerts and outputs to console or files.

本模組處理監測系統的通知傳送。將訊號格式化為人類可讀的提醒並輸出至主控台或檔案。

⚠️  **ALERT ONLY / 僅提醒**
This module generates ALERTS ONLY. No automatic trading is performed.
本模組僅產生提醒，不執行自動交易。

## Files / 檔案

| File / 檔案 | Description / 說明 |
|-------------|--------------------|
| `formatter.py` | Signal formatting / 訊號格式化 |
| `notifier.py` | Notification delivery / 通知傳送 |
| `README.md` | This file / 本檔案 |

## Architecture / 架構

```
Signal (from signals/engine.py)
    ↓
NotificationFormatter (formatter.py)
    ↓
Notifier (notifier.py)
    ↓
Console / File / Both
```

## Components / 元件

### NotificationFormatter

Formats Signal objects into readable messages.
將 Signal 物件格式化為可讀訊息。

**Output Formats / 輸出格式**:
| Format / 格式 | Description / 說明 |
|---------------|--------------------|
| PLAIN_TEXT | Human-readable full format / 人類可讀完整格式 |
| COMPACT | One-line summary / 單行摘要 |
| MARKDOWN | Markdown formatted / Markdown 格式 |

### Notifier

Handles notification delivery.
處理通知傳送。

**Output Channels / 輸出通道**:
| Channel / 通道 | Description / 說明 |
|----------------|--------------------|
| CONSOLE | Print to stdout / 輸出至標準輸出 |
| FILE | Save to files / 儲存至檔案 |
| BOTH | Console + File / 主控台 + 檔案 |

### AlertOnlyNotifier

Extended notifier with extra safety warnings.
帶額外安全警告的擴充通知器。

## Usage / 使用方法

### Basic Notification / 基本通知

```python
from notifications.notifier import Notifier, NotifierConfig, OutputChannel
from signals.engine import SignalEngine

# Create notifier
config = NotifierConfig(
    output_channel=OutputChannel.BOTH,
    output_dir="/tmp/kimi-shared-brain/alerts",
    language="en"
)
notifier = Notifier(config)

# Generate signals
engine = SignalEngine()
signals = engine.process_symbol("BTCUSDT", data_5m, data_1m, data_15m)

# Notify each signal
for signal in signals:
    notifier.notify(signal)
```

### Batch Notification / 批次通知

```python
from notifications.notifier import create_default_notifier

notifier = create_default_notifier()

# Notify all signals at once
success_count = notifier.notify_batch(signals)
print(f"Notified {success_count}/{len(signals)} signals")
```

### Compact Format / 緊湊格式

```python
from notifications.formatter import NotificationFormatter, OutputFormat

formatter = NotificationFormatter(language="en")

# Compact one-line format
compact = formatter.format_compact(signal)
print(compact)
# Output: [BTCUSDT] 📈 TREND LONG @ 69250.50 | ✅ CONFIRMED | ALERT_ONLY_NO_AUTO_TRADE
```

### Custom Formatter / 自訂格式化器

```python
from notifications.formatter import NotificationFormatter

# English format
formatter_en = NotificationFormatter(language="en")
alert_en = formatter_en.format_alert(signal)

# Chinese format
formatter_zh = NotificationFormatter(language="zh")
alert_zh = formatter_zh.format_alert(signal)
```

## Output Files / 輸出檔案

When using FILE or BOTH channel:
使用 FILE 或 BOTH 通道時：

| File / 檔案 | Description / 說明 |
|-------------|--------------------|
| `alerts.log` | Human-readable text logs / 人類可讀文字記錄 |
| `alerts.json` | Structured JSON history / 結構化 JSON 歷史 |

### alerts.log Example

```
[2026-04-06 11:30:15]
==================================================
ALERT: 📈 TREND LONG ✅ CONFIRMED
==================================================
Symbol: BTCUSDT
Time: 2026-04-06 11:30:15

Price Data / 價格資料:
  Close (5m): 69,250.50
  MA5: 69,180.25
  MA20: 69,050.00
  MA240: 68,500.75
  Volume (1m): 12.50
  Volume Ratio: 2.40x

Conditions Met / 條件滿足:
  ✅ c1_above_ma240
  ✅ c2_ma_cross_above
  ✅ c3_volume_spike

Reason / 原因: BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.4x average

⚠️  ALERT_ONLY_NO_AUTO_TRADE

==================================================

```

### alerts.json Example

```json
[
  {
    "signal_type": "trend_long",
    "level": "confirmed",
    "symbol": "BTCUSDT",
    "timestamp": 1775385000000,
    "price_data": {
      "close_5m": 69250.50,
      "ma5": 69180.25,
      "ma20": 69050.00,
      "volume_ratio": 2.4
    },
    "conditions": {
      "c1_above_ma240": true,
      "c2_ma_cross_above": true,
      "c3_volume_spike": true
    },
    "reason": "BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.4x average",
    "warning": "ALERT_ONLY_NO_AUTO_TRADE"
  }
]
```

## API Reference / API 參考

### NotificationFormatter Class

#### `__init__(language="en")`
Initialize formatter / 初始化格式化器

#### `format_alert(signal) -> str`
Format signal as full text alert / 將訊號格式化為完整文字提醒

#### `format_compact(signal) -> str`
Format signal as one-line summary / 將訊號格式化為單行摘要

#### `format_markdown(signal) -> str`
Format signal as Markdown / 將訊號格式化為 Markdown

#### `format_batch(signals, format_type) -> str`
Format multiple signals / 格式化多個訊號

### Notifier Class

#### `__init__(config=None)`
Initialize notifier / 初始化通知器

#### `notify(signal, format_type) -> bool`
Send notification for a signal / 為訊號發送通知

#### `notify_batch(signals, format_type) -> int`
Send notifications for multiple signals / 為多個訊號發送通知

#### `get_alert_history(limit=None) -> List[Dict]`
Get alert history / 取得提醒歷史

#### `clear_history() -> bool`
Clear alert history / 清除提醒歷史

#### `get_stats() -> Dict`
Get notification statistics / 取得通知統計

### Convenience Functions

#### `create_console_notifier(language="en") -> Notifier`
Create console-only notifier / 建立僅主控台通知器

#### `create_file_notifier(output_dir, language="en") -> Notifier`
Create file-only notifier / 建立僅檔案通知器

#### `create_default_notifier(output_dir, language="en") -> Notifier`
Create default notifier (console + file) / 建立預設通知器

## Alert Display / 提醒顯示

### Color Coding / 顏色編碼

When console colors are enabled:
主控台顏色啟用時：

| Signal Type / 訊號類型 | Color / 顏色 |
|------------------------|--------------|
| trend_long | Green / 綠色 |
| trend_short | Red / 紅色 |
| contrarian_watch_* | Yellow / 黃色 |

### WATCH_ONLY Display / 僅觀察顯示

```
╔══════════════════════════════════════════════════════════════════╗
║  👁️  WATCH ONLY SIGNAL - NOT FOR EXECUTION                       ║
║  👁️  僅觀察訊號 - 非執行訊號                                      ║
╚══════════════════════════════════════════════════════════════════╝
```

## Important Warnings / 重要警告

### ⚠️ ALERT ONLY SYSTEM

```
╔══════════════════════════════════════════════════════════════════╗
║              ⚠️  ALERT ONLY - NO AUTO TRADING  ⚠️                 ║
║                                                                  ║
║         This is a MONITORING SYSTEM, not a trading system.       ║
║         這是監測系統，不是交易系統。                               ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ WATCH ONLY

```
╔══════════════════════════════════════════════════════════════════╗
║  contrarian_watch signals are WATCH ONLY                         ║
║  contrarian_watch 訊號僅供觀察                                     ║
║                                                                  ║
║  • NOT an execution signal / 不是執行訊號                          ║
║  • NOT a trade recommendation / 不是交易建議                       ║
║  • For observation only / 僅供觀察                                 ║
╚══════════════════════════════════════════════════════════════════╝
```

## Dependencies / 依賴

| Module / 模組 | Layer / 層級 | Purpose / 用途 |
|---------------|--------------|----------------|
| `signals.engine` | Signal Layer | Signal definitions / 訊號定義 |

## What's NOT Included / 不包含的功能

This module is intentionally limited (Notification Layer only):
本模組刻意限制（僅通知層）：

- ❌ No external integrations (Discord, Email, SMS) / 無外部整合
- ❌ No real-time push notifications / 無即時推播
- ❌ No automatic trading / 無自動交易

## Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-06 | Initial implementation / 初始實作 |

## References / 參考

- `workflows/btc_eth_monitoring_system.md` - Phase 4 Notification Design
- `workflows/btc_eth_monitoring_signal_spec.md` - Signal specifications
- `signals/engine.py` - Signal Layer / 訊號層
