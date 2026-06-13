# Test Specification for Notification Module / Notification Module 測試規格

**Module / 模組**: `notifications/formatter.py`, `notifications/notifier.py`  
**Version / 版本**: 1.0.0  
**Date / 日期**: 2026-04-06  
**Status / 狀態**: Specification for manual verification / 手動驗證規格

---

## Overview / 概覽

This document defines manual verification steps for the notification module.
Manual verification ensures signal formatting and notification delivery work correctly.

本文件定義通知模組的手動驗證步驟。
手動驗證確保訊號格式化與通知傳送正常運作。

---

## Prerequisites / 前置條件

1. Python 3.8+ installed / Python 3.8+ 已安裝
2. Module files available:
   - `notifications/formatter.py`
   - `notifications/notifier.py`
   - `signals/engine.py`
3. All modules can be imported / 所有模組可匯入

---

## Test Cases / 測試案例

### TC-001: Module Import / 模組匯入

**Objective / 目的**: Verify the module can be imported without errors

**Steps / 步驟**:
```python
from notifications.formatter import (
    NotificationFormatter,
    OutputFormat
)
from notifications.notifier import (
    Notifier,
    NotifierConfig,
    OutputChannel,
    AlertOnlyNotifier,
    create_console_notifier,
    create_file_notifier,
    create_default_notifier
)

print("Imports successful / 匯入成功")
```

**Expected Result / 預期結果**:
- No ImportError / 無 ImportError

**Pass Criteria / 通過標準**: ✅ Import succeeds

---

### TC-002: NotificationFormatter Initialization / 通知格式化器初始化

**Objective / 目的**: Verify formatter can be created with different languages

**Steps / 步驟**:
```python
from notifications.formatter import NotificationFormatter

# English formatter
formatter_en = NotificationFormatter(language="en")
print(f"English formatter: {type(formatter_en)}")
print(f"Language: {formatter_en.language}")

# Chinese formatter
formatter_zh = NotificationFormatter(language="zh")
print(f"Chinese formatter: {type(formatter_zh)}")
print(f"Language: {formatter_zh.language}")
```

**Expected Result / 預期結果**:
- Both formatters created successfully
- Language attribute set correctly

**Pass Criteria / 通過標準**: ✅ Initialization works

---

### TC-003: Signal Formatting / 訊號格式化

**Objective / 目的**: Verify signal formatting works

**Steps / 步驟**:
```python
from notifications.formatter import NotificationFormatter
from signals.engine import Signal, SignalType, SignalLevel
import time

formatter = NotificationFormatter(language="en")

# Create sample signal
signal = Signal(
    signal_type=SignalType.TREND_LONG,
    level=SignalLevel.CONFIRMED,
    symbol="BTCUSDT",
    timestamp=int(time.time() * 1000),
    price_data={
        "close_5m": 69250.50,
        "ma5": 69180.25,
        "ma20": 69050.00,
        "volume_ratio": 2.4
    },
    conditions={"c1": True, "c2": True},
    reason="Test signal",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

# Format as alert
alert = formatter.format_alert(signal)
print(alert)
```

**Expected Result / 預期結果**:
- Formatted alert contains signal type, symbol, price data
- Contains warning message
- Human-readable format

**Pass Criteria / 通過標準**: ✅ Formatting works correctly

---

### TC-004: Compact Format / 緊湊格式

**Objective / 目的**: Verify compact formatting

**Steps / 步驟**:
```python
from notifications.formatter import NotificationFormatter
from signals.engine import Signal, SignalType, SignalLevel
import time

formatter = NotificationFormatter(language="en")

signal = Signal(
    signal_type=SignalType.TREND_LONG,
    level=SignalLevel.CONFIRMED,
    symbol="BTCUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"close_5m": 69250.50},
    conditions={},
    reason="Test",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

compact = formatter.format_compact(signal)
print(f"Compact: {compact}")
```

**Expected Result / 預期結果**:
- Single line format
- Contains symbol, signal type, price, level, warning

**Pass Criteria / 通過標準**: ✅ Compact format correct

---

### TC-005: Markdown Format / Markdown 格式

**Objective / 目的**: Verify Markdown formatting

**Steps / 步驟**:
```python
from notifications.formatter import NotificationFormatter
from signals.engine import Signal, SignalType, SignalLevel
import time

formatter = NotificationFormatter(language="en")

signal = Signal(
    signal_type=SignalType.TREND_SHORT,
    level=SignalLevel.CONFIRMED,
    symbol="ETHUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"close_5m": 3500.00, "ma5": 3550.00},
    conditions={"c1": True},
    reason="Test",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

markdown = formatter.format_markdown(signal)
print(markdown)
```

**Expected Result / 預期結果**:
- Markdown headers (##)
- Markdown table for price data
- Proper formatting

**Pass Criteria / 通過標準**: ✅ Markdown format correct

---

### TC-006: Chinese Language Formatting / 中文語言格式化

**Objective / 目的**: Verify Chinese language support

**Steps / 步驟**:
```python
from notifications.formatter import NotificationFormatter
from signals.engine import Signal, SignalType, SignalLevel
import time

formatter_zh = NotificationFormatter(language="zh")

signal = Signal(
    signal_type=SignalType.TREND_LONG,
    level=SignalLevel.CONFIRMED,
    symbol="BTCUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"close_5m": 69250.50},
    conditions={},
    reason="測試訊號",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

alert_zh = formatter_zh.format_alert(signal)
print(alert_zh)
```

**Expected Result / 預期結果**:
- Contains Chinese text (提醒, 標的, 時間, etc.)
- Proper formatting in Chinese

**Pass Criteria / 通過標準**: ✅ Chinese formatting works

---

### TC-007: Notifier Initialization / 通知器初始化

**Objective / 目的**: Verify notifier can be created

**Steps / 步驟**:
```python
from notifications.notifier import Notifier, NotifierConfig, OutputChannel

# Console notifier
config_console = NotifierConfig(
    output_channel=OutputChannel.CONSOLE,
    language="en"
)
notifier_console = Notifier(config_console)
print(f"Console notifier: {type(notifier_console)}")

# File notifier
config_file = NotifierConfig(
    output_channel=OutputChannel.FILE,
    output_dir="/tmp/test_alerts",
    language="en"
)
notifier_file = Notifier(config_file)
print(f"File notifier: {type(notifier_file)}")

# Both notifier
config_both = NotifierConfig(
    output_channel=OutputChannel.BOTH,
    output_dir="/tmp/test_alerts",
    language="en"
)
notifier_both = Notifier(config_both)
print(f"Both notifier: {type(notifier_both)}")
```

**Expected Result / 預期結果**:
- All notifiers created successfully
- Directory created for file notifiers

**Pass Criteria / 通過標準**: ✅ Initialization works

---

### TC-008: Console Notification / 主控台通知

**Objective / 目的**: Verify console notification output

**Steps / 步驟**:
```python
from notifications.notifier import create_console_notifier
from signals.engine import Signal, SignalType, SignalLevel
import time

notifier = create_console_notifier(language="en")

signal = Signal(
    signal_type=SignalType.TREND_LONG,
    level=SignalLevel.CONFIRMED,
    symbol="BTCUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"close_5m": 69250.50},
    conditions={},
    reason="Test notification",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

result = notifier.notify(signal)
print(f"Notification result: {result}")
```

**Expected Result / 預期結果**:
- Alert displayed in console
- Result is True

**Pass Criteria / 通過標準**: ✅ Console notification works

---

### TC-009: File Notification / 檔案通知

**Objective / 目的**: Verify file notification output

**Steps / 步驟**:
```python
from notifications.notifier import create_file_notifier
from signals.engine import Signal, SignalType, SignalLevel
import time
import os

output_dir = "/tmp/test_alerts_t009"
notifier = create_file_notifier(output_dir=output_dir, language="en")

signal = Signal(
    signal_type=SignalType.TREND_SHORT,
    level=SignalLevel.CONFIRMED,
    symbol="ETHUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"close_5m": 3500.00},
    conditions={},
    reason="Test file notification",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

result = notifier.notify(signal)
print(f"Notification result: {result}")

# Check files
log_file = os.path.join(output_dir, "alerts.log")
json_file = os.path.join(output_dir, "alerts.json")

print(f"Log file exists: {os.path.exists(log_file)}")
print(f"JSON file exists: {os.path.exists(json_file)}")

# Read log content
if os.path.exists(log_file):
    with open(log_file, "r") as f:
        content = f.read()
    print(f"Log content length: {len(content)} bytes")
```

**Expected Result / 預期結果**:
- Both files created
- Log file contains human-readable alert
- JSON file contains structured data

**Pass Criteria / 通過標準**: ✅ File notification works

---

### TC-010: AlertOnlyNotifier Safety Header / 僅提醒通知器安全標頭

**Objective / 目的**: Verify AlertOnlyNotifier shows safety header

**Steps / 步驟**:
```python
from notifications.notifier import AlertOnlyNotifier, NotifierConfig, OutputChannel
from signals.engine import Signal, SignalType, SignalLevel
import time

config = NotifierConfig(
    output_channel=OutputChannel.CONSOLE,
    language="en"
)
notifier = AlertOnlyNotifier(config)

signal = Signal(
    signal_type=SignalType.TREND_LONG,
    level=SignalLevel.CONFIRMED,
    symbol="BTCUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"close_5m": 69250.50},
    conditions={},
    reason="Test",
    warning="ALERT_ONLY_NO_AUTO_TRADE"
)

# First notification should show header
print("--- First notification (should show header) ---")
notifier.notify(signal)
```

**Expected Result / 預期結果**:
- Safety header displayed before first alert
- Contains "ALERT ONLY - NO AUTO TRADING"

**Pass Criteria / 通過標準**: ✅ Safety header shown

---

### TC-011: WATCH_ONLY Extra Warning / 僅觀察額外警告

**Objective / 目的**: Verify extra warning for WATCH_ONLY signals

**Steps / 步驟**:
```python
from notifications.notifier import AlertOnlyNotifier, NotifierConfig, OutputChannel
from signals.engine import Signal, SignalType, SignalLevel
import time

config = NotifierConfig(
    output_channel=OutputChannel.CONSOLE,
    language="en"
)
notifier = AlertOnlyNotifier(config)

# Create WATCH_ONLY signal
signal = Signal(
    signal_type=SignalType.CONTRARIAN_WATCH_OVERHEATED,
    level=SignalLevel.WATCH_ONLY,
    symbol="BTCUSDT",
    timestamp=int(time.time() * 1000),
    price_data={"pattern": "overheated", "consecutive_count": 4},
    conditions={"pattern_detected": True},
    reason="4 consecutive red candles",
    warning="WATCH_ONLY_NOT_EXECUTION_SIGNAL"
)

print("--- WATCH_ONLY signal notification ---")
notifier.notify(signal)
```

**Expected Result / 預期結果**:
- Extra warning box displayed
- Contains "WATCH ONLY SIGNAL - NOT FOR EXECUTION"

**Pass Criteria / 通過標準**: ✅ WATCH_ONLY warning shown

---

### TC-012: Batch Notification / 批次通知

**Objective / 目的**: Verify batch notification

**Steps / 步驟**:
```python
from notifications.notifier import create_console_notifier
from signals.engine import Signal, SignalType, SignalLevel
import time

notifier = create_console_notifier(language="en")

signals = [
    Signal(
        signal_type=SignalType.TREND_LONG,
        level=SignalLevel.CONFIRMED,
        symbol="BTCUSDT",
        timestamp=int(time.time() * 1000),
        price_data={"close_5m": 69250.50},
        conditions={},
        reason="Signal 1",
        warning="ALERT_ONLY_NO_AUTO_TRADE"
    ),
    Signal(
        signal_type=SignalType.TREND_SHORT,
        level=SignalLevel.CONFIRMED,
        symbol="ETHUSDT",
        timestamp=int(time.time() * 1000),
        price_data={"close_5m": 3500.00},
        conditions={},
        reason="Signal 2",
        warning="ALERT_ONLY_NO_AUTO_TRADE"
    )
]

success_count = notifier.notify_batch(signals)
print(f"Success count: {success_count}")
```

**Expected Result / 預期結果**:
- Both signals notified
- Summary displayed at end
- success_count = 2

**Pass Criteria / 通過標準**: ✅ Batch notification works

---

### TC-013: Alert History / 提醒歷史

**Objective / 目的**: Verify alert history retrieval

**Steps / 步驟**:
```python
from notifications.notifier import create_file_notifier
from signals.engine import Signal, SignalType, SignalLevel
import time
import os

output_dir = "/tmp/test_alerts_t013"
notifier = create_file_notifier(output_dir=output_dir, language="en")

# Create and notify signals
for i in range(3):
    signal = Signal(
        signal_type=SignalType.TREND_LONG,
        level=SignalLevel.CONFIRMED,
        symbol=f"TEST{i}",
        timestamp=int(time.time() * 1000),
        price_data={"close_5m": 100.0 + i},
        conditions={},
        reason=f"Test {i}",
        warning="ALERT_ONLY_NO_AUTO_TRADE"
    )
    notifier.notify(signal)

# Get history
history = notifier.get_alert_history()
print(f"History count: {len(history)}")

# Get limited history
limited = notifier.get_alert_history(limit=2)
print(f"Limited history count: {len(limited)}")
```

**Expected Result / 預期結果**:
- History contains 3 alerts
- Limited history contains 2 alerts

**Pass Criteria / 通過標準**: ✅ History retrieval works

---

### TC-014: Statistics / 統計

**Objective / 目的**: Verify statistics generation

**Steps / 步驟**:
```python
from notifications.notifier import create_file_notifier
from signals.engine import Signal, SignalType, SignalLevel
import time

output_dir = "/tmp/test_alerts_t014"
notifier = create_file_notifier(output_dir=output_dir, language="en")

# Create different types of signals
signals = [
    (SignalType.TREND_LONG, SignalLevel.CONFIRMED, "BTCUSDT"),
    (SignalType.TREND_SHORT, SignalLevel.CONFIRMED, "ETHUSDT"),
    (SignalType.CONTRARIAN_WATCH_OVERHEATED, SignalLevel.WATCH_ONLY, "BTCUSDT"),
    (SignalType.TREND_LONG, SignalLevel.CONFIRMED, "BTCUSDT"),
]

for sig_type, level, symbol in signals:
    signal = Signal(
        signal_type=sig_type,
        level=level,
        symbol=symbol,
        timestamp=int(time.time() * 1000),
        price_data={"close_5m": 100.0},
        conditions={},
        reason="Test",
        warning="ALERT_ONLY_NO_AUTO_TRADE"
    )
    notifier.notify(signal)

# Get stats
stats = notifier.get_stats()
print(f"Total alerts: {stats['total_alerts']}")
print(f"By type: {stats['by_type']}")
print(f"By level: {stats['by_level']}")
print(f"By symbol: {stats['by_symbol']}")
```

**Expected Result / 預期結果**:
- total_alerts = 4
- by_type shows counts for each signal type
- by_level shows confirmed and watch_only counts
- by_symbol shows counts per symbol

**Pass Criteria / 通過標準**: ✅ Statistics generation works

---

## Summary / 總結

| Test Case / 測試案例 | Description / 說明 | Status / 狀態 |
|----------------------|--------------------|---------------|
| TC-001 | Module Import | ⬜ Pending |
| TC-002 | Formatter Init | ⬜ Pending |
| TC-003 | Signal Formatting | ⬜ Pending |
| TC-004 | Compact Format | ⬜ Pending |
| TC-005 | Markdown Format | ⬜ Pending |
| TC-006 | Chinese Language | ⬜ Pending |
| TC-007 | Notifier Init | ⬜ Pending |
| TC-008 | Console Notification | ⬜ Pending |
| TC-009 | File Notification | ⬜ Pending |
| TC-010 | Safety Header | ⬜ Pending |
| TC-011 | WATCH_ONLY Warning | ⬜ Pending |
| TC-012 | Batch Notification | ⬜ Pending |
| TC-013 | Alert History | ⬜ Pending |
| TC-014 | Statistics | ⬜ Pending |

## How to Run Tests / 如何執行測試

1. Navigate to project root / 切換到專案根目錄:
   ```bash
   cd /path/to/kimi-shared-brain
   ```

2. Start Python REPL / 啟動 Python REPL:
   ```bash
   python3
   ```

3. Run individual test cases / 執行個別測試案例:
   ```python
   # Copy and paste test code from above
   from notifications.notifier import create_console_notifier
   print(create_console_notifier())
   ```

## Notes / 注意事項

1. **No Network Required / 不需要網路**: Tests use mock data
2. **Clean Up / 清理**: Test directories are created in `/tmp/`
3. **Independent / 獨立**: Tests don't depend on external state

## What's NOT Tested / 未測試項目

- ❌ External integrations (Discord, Email) / 外部整合
- ❌ Real-time delivery / 即時傳送
- ❌ Concurrent access / 並行存取
