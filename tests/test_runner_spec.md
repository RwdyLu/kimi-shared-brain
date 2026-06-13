# Test Specification for Monitoring Runner / Monitoring Runner 測試規格

**Module / 模組**: `app/monitor_runner.py`  
**Version / 版本**: 1.0.0  
**Date / 日期**: 2026-04-06  
**Status / 狀態**: Specification for manual verification / 手動驗證規格

---

## Overview / 概覽

This document defines manual verification steps for the monitoring runner.
Manual verification ensures the runner correctly connects all four layers.

本文件定義監測執行器的手動驗證步驟。
手動驗證確保執行器正確連接所有四層。

---

## Prerequisites / 前置條件

1. Python 3.8+ installed / Python 3.8+ 已安裝
2. All lower layer modules available:
   - `data/fetcher.py`
   - `indicators/calculator.py`
   - `signals/engine.py`
   - `notifications/formatter.py`
   - `notifications/notifier.py`
3. Network access to Binance API (or test with mock data)

---

## Test Cases / 測試案例

### TC-001: Module Import / 模組匯入

**Objective / 目的**: Verify the module can be imported without errors

**Steps / 步驟**:
```python
from app.monitor_runner import (
    MonitorRunner,
    SymbolResult,
    RunSummary,
    build_run_summary,
    preview_run_output,
    MONITOR_SYMBOLS,
    TIMEFRAMES
)

print(f"MONITOR_SYMBOLS: {MONITOR_SYMBOLS}")
print(f"TIMEFRAMES: {list(TIMEFRAMES.keys())}")
print("Import successful / 匯入成功")
```

**Expected Result / 預期結果**:
- No ImportError / 無 ImportError
- MONITOR_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
- TIMEFRAMES = ["1m", "5m", "15m"]

**Pass Criteria / 通過標準**: ✅ Import succeeds

---

### TC-002: MonitorRunner Initialization / 執行器初始化

**Objective / 目的**: Verify runner can be initialized

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner

# Default initialization
runner = MonitorRunner()
print(f"Runner type: {type(runner)}")
print(f"Has fetcher: {runner.fetcher is not None}")
print(f"Has signal_engine: {runner.signal_engine is not None}")
print(f"Has notifier: {runner.notifier is not None}")
```

**Expected Result / 預期結果**:
- Runner created successfully
- All components initialized

**Pass Criteria / 通過標準**: ✅ Initialization works

---

### TC-003: Run for Single Symbol / 執行單一標的

**Objective / 目的**: Verify single symbol monitoring

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner

runner = MonitorRunner()
result = runner.run_for_symbol("BTCUSDT")

print(f"Symbol: {result.symbol}")
print(f"Success: {result.success}")
print(f"Error: {result.error}")
print(f"Data 5m count: {len(result.data_5m) if result.data_5m else 0}")
print(f"Data 1m count: {len(result.data_1m) if result.data_1m else 0}")
print(f"Data 15m count: {len(result.data_15m) if result.data_15m else 0}")
print(f"MA5: {result.ma5}")
print(f"MA20: {result.ma20}")
print(f"MA240: {result.ma240}")
print(f"Volume Ratio: {result.volume_ratio}")
print(f"Total Signals: {len(result.signals)}")
print(f"Confirmed: {len(result.confirmed_signals)}")
print(f"Watch Only: {len(result.watch_only_signals)}")
```

**Expected Result / 預期結果**:
- Data fetched for all timeframes
- Indicators calculated
- Signals list exists (may be empty if no conditions met)

**Pass Criteria / 通過標準**: ✅ Single symbol run works

---

### TC-004: Run Monitor Once (All Symbols) / 執行所有標的

**Objective / 目的**: Verify full monitoring run

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner

runner = MonitorRunner()
results, summary = runner.run_monitor_once()

print(f"\n=== SUMMARY ===")
print(f"Total Symbols: {summary.total_symbols}")
print(f"Successful: {summary.successful_symbols}")
print(f"Failed: {summary.failed_symbols}")
print(f"Total Signals: {summary.total_signals}")
print(f"Confirmed: {summary.confirmed_count}")
print(f"Watch Only: {summary.watch_only_count}")
print(f"Symbols with signals: {summary.symbols_with_signals}")

print(f"\n=== RESULTS ===")
for result in results:
    print(f"{result.symbol}: {len(result.signals)} signals")
```

**Expected Result / 預期結果**:
- Runs for BTCUSDT and ETHUSDT
- Summary shows total counts
- Results list has 2 entries

**Pass Criteria / 通過標準**: ✅ Full run works

---

### TC-005: Build Run Summary / 建立執行摘要

**Objective / 目的**: Verify summary generation

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner, build_run_summary
from signals.engine import Signal, SignalType, SignalLevel
import time

runner = MonitorRunner()

# Create mock results
result1 = runner.run_for_symbol("BTCUSDT")

# Build summary
summary = build_run_summary([result1])

print(f"Total symbols: {summary.total_symbols}")
print(f"Successful: {summary.successful_symbols}")
print(f"Total signals: {summary.total_signals}")
```

**Expected Result / 預期結果**:
- Summary created correctly
- Counts match input results

**Pass Criteria / 通過標準**: ✅ Summary generation works

---

### TC-006: Preview Run Output / 預覽執行輸出

**Objective / 目的**: Verify preview generation

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner, preview_run_output

runner = MonitorRunner()
results, summary = runner.run_monitor_once()

# Generate preview
preview = preview_run_output(results)
print(preview)
```

**Expected Result / 預期結果**:
- Preview string generated
- Contains symbol info
- Contains signal details
- Shows warning messages

**Pass Criteria / 通過標準**: ✅ Preview generation works

---

### TC-007: Data Fetch Integration / 資料抓取整合

**Objective / 目的**: Verify data layer integration

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner

runner = MonitorRunner()
result = runner.run_for_symbol("BTCUSDT")

# Check data was fetched
assert result.data_5m is not None
assert result.data_1m is not None
assert result.data_15m is not None

print(f"5m data type: {type(result.data_5m)}")
print(f"5m first candle: {result.data_5m[0] if result.data_5m else None}")
print(f"1m data count: {len(result.data_1m)}")
print(f"15m data count: {len(result.data_15m)}")
```

**Expected Result / 預期結果**:
- Data fetched for all timeframes
- Data is list of KlineData objects
- Correct counts for each timeframe

**Pass Criteria / 通過標準**: ✅ Data layer integrated

---

### TC-008: Indicator Calculation Integration / 指標計算整合

**Objective / 目的**: Verify indicator layer integration

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner

runner = MonitorRunner()
result = runner.run_for_symbol("ETHUSDT")

print(f"MA5: {result.ma5}")
print(f"MA20: {result.ma20}")
print(f"MA240: {result.ma240}")
print(f"Volume Avg: {result.volume_avg}")
print(f"Volume Ratio: {result.volume_ratio}")

# Verify calculations
if result.data_5m and len(result.data_5m) >= 5:
    assert result.ma5 is not None
if result.data_5m and len(result.data_5m) >= 240:
    assert result.ma240 is not None
```

**Expected Result / 預期結果**:
- MAs calculated when enough data
- Volume metrics calculated
- Values are floats

**Pass Criteria / 通過標準**: ✅ Indicator layer integrated

---

### TC-009: Signal Generation Integration / 訊號產生整合

**Objective / 目的**: Verify signal layer integration

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner
from signals.engine import SignalLevel

runner = MonitorRunner()
result = runner.run_for_symbol("BTCUSDT")

print(f"Total signals: {len(result.signals)}")
print(f"Confirmed: {len(result.confirmed_signals)}")
print(f"Watch Only: {len(result.watch_only_signals)}")

# Check signal properties
for signal in result.signals:
    print(f"  - {signal.signal_type.value}: {signal.level.value}")
    print(f"    Reason: {signal.reason}")
    print(f"    Warning: {signal.warning}")
    
    # Verify WATCH_ONLY signals
    if signal.level == SignalLevel.WATCH_ONLY:
        assert "WATCH_ONLY" in signal.warning or "僅觀察" in signal.warning
```

**Expected Result / 預期結果**:
- Signals generated if conditions met
- Confirmed and watch_only separated
- All signals have warning field
- WATCH_ONLY signals properly marked

**Pass Criteria / 通過標準**: ✅ Signal layer integrated

---

### TC-010: Notification Output Integration / 通知輸出整合

**Objective / 目的**: Verify notification layer integration

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner
from notifications.notifier import create_file_notifier

# Create runner with file output
output_dir = "/tmp/test_monitor_output"
notifier = create_file_notifier(output_dir=output_dir)
runner = MonitorRunner(notifier=notifier)

# Run monitoring
results, summary = runner.run_monitor_once()

# Check output files
import os
log_file = os.path.join(output_dir, "alerts.log")
json_file = os.path.join(output_dir, "alerts.json")

print(f"Log file exists: {os.path.exists(log_file)}")
print(f"JSON file exists: {os.path.exists(json_file)}")

if os.path.exists(log_file):
    with open(log_file, "r") as f:
        content = f.read()
    print(f"Log content length: {len(content)} bytes")
```

**Expected Result / 預期結果**:
- Notifications output to console/file
- Log file created with alerts
- JSON file created with structured data

**Pass Criteria / 通過標準**: ✅ Notification layer integrated

---

### TC-011: Error Handling / 錯誤處理

**Objective / 目的**: Verify error handling for invalid symbol

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner

runner = MonitorRunner()

# Try invalid symbol
result = runner.run_for_symbol("INVALID_SYMBOL")

print(f"Success: {result.success}")
print(f"Error: {result.error}")
print(f"Signals: {len(result.signals)}")

assert not result.success
assert result.error is not None
```

**Expected Result / 預期結果**:
- success = False
- error message present
- No exception raised

**Pass Criteria / 通過標準**: ✅ Error handling works

---

### TC-012: Contrarian Watch Only Marking / 逆勢觀察標示

**Objective / 目的**: Verify contrarian signals are marked as watch only

**Steps / 步驟**:
```python
from app.monitor_runner import MonitorRunner
from signals.engine import SignalType, SignalLevel

runner = MonitorRunner()

# Check if any contrarian signals exist
results, summary = runner.run_monitor_once()

contrarian_signals = []
for result in results:
    for signal in result.signals:
        if signal.signal_type in [
            SignalType.CONTRARIAN_WATCH_OVERHEATED,
            SignalType.CONTRARIAN_WATCH_OVERSOLD
        ]:
            contrarian_signals.append(signal)

print(f"Contrarian signals found: {len(contrarian_signals)}")

for signal in contrarian_signals:
    print(f"Type: {signal.signal_type.value}")
    print(f"Level: {signal.level.value}")
    print(f"Warning: {signal.warning}")
    
    # Verify properties
    assert signal.level == SignalLevel.WATCH_ONLY
    assert "WATCH_ONLY" in signal.warning or "僅觀察" in signal.warning
```

**Expected Result / 預期結果**:
- Contrarian signals have level=WATCH_ONLY
- Warning contains "WATCH_ONLY" or "僅觀察"
- Warning contains "NOT_EXECUTION" or "非執行"

**Pass Criteria / 通過標準**: ✅ Contrarian properly marked

---

## Summary / 總結

| Test Case / 測試案例 | Description / 說明 | Status / 狀態 |
|----------------------|--------------------|---------------|
| TC-001 | Module Import | ⬜ Pending |
| TC-002 | Runner Init | ⬜ Pending |
| TC-003 | Single Symbol Run | ⬜ Pending |
| TC-004 | Full Run | ⬜ Pending |
| TC-005 | Build Summary | ⬜ Pending |
| TC-006 | Preview Output | ⬜ Pending |
| TC-007 | Data Layer | ⬜ Pending |
| TC-008 | Indicator Layer | ⬜ Pending |
| TC-009 | Signal Layer | ⬜ Pending |
| TC-010 | Notification Layer | ⬜ Pending |
| TC-011 | Error Handling | ⬜ Pending |
| TC-012 | Contrarian Marking | ⬜ Pending |

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
   from app.monitor_runner import MonitorRunner
   runner = MonitorRunner()
   print(runner)
   ```

## Notes / 注意事項

1. **Network Required / 需要網路**: Tests require Binance API access
2. **Rate Limits / 速率限制**: Be mindful of API rate limits
3. **Data Availability / 資料可用性**: Results depend on market conditions

## What's NOT Tested / 未測試項目

- ❌ Daemon mode / 常駐模式 (not implemented / 未實作)
- ❌ Automatic trading / 自動交易 (not implemented / 未實作)
- ❌ Scheduler integration / 排程器整合 (not implemented / 未實作)
