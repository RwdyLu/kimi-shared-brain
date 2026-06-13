# T-030 Test Specification / 測試規格

**Task ID**: T-030  
**Title**: Add Scheduler for Monitoring Runs / 為監測執行新增排程器  
**Type**: Manual Validation / 手動驗證

---

## Test Overview / 測試概覽

Verify that the scheduler module works correctly for:
- Single-run execution / 單次執行
- Interval-based execution / 間隔執行
- Overlap prevention / 重疊防止
- Statistics tracking / 統計追蹤

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

**Purpose**: Verify the scheduler module can be imported

**Steps**:
```python
python3 -c "
from app.scheduler import (
    MonitoringScheduler, SchedulerConfig, SchedulerMode,
    SchedulerLock, RunRecord,
    run_once_with_notification, run_every_5_minutes
)
print('✅ All imports successful')
"
```

**Expected Result**: All imports succeed without errors

**Status**: ⬜ Not tested

---

### TC-002: SchedulerLock - Acquire and Release / 排程器鎖 - 取得與釋放

**Purpose**: Verify file-based locking works

**Steps**:
```python
python3 -c "
from app.scheduler import SchedulerLock
import os

lock = SchedulerLock('/tmp/test_scheduler.lock')

# Test acquire
result1 = lock.acquire()
print(f'First acquire: {result1}')
assert result1 == True, 'First acquire should succeed'

# Test second acquire (should fail)
lock2 = SchedulerLock('/tmp/test_scheduler.lock')
result2 = lock2.acquire()
print(f'Second acquire: {result2}')
assert result2 == False, 'Second acquire should fail'

# Release first lock
lock.release()

# Now second should succeed
result3 = lock2.acquire()
print(f'After release: {result3}')
assert result3 == True, 'Should succeed after release'

lock2.release()

# Cleanup
if os.path.exists('/tmp/test_scheduler.lock'):
    os.remove('/tmp/test_scheduler.lock')

print('✅ Lock test passed')
"
```

**Expected Result**:
- First acquire: True
- Second acquire: False
- After release: True

**Status**: ⬜ Not tested

---

### TC-003: Run Once Mode / 單次執行模式

**Purpose**: Verify single execution works

**Steps**:
```python
python3 -c "
from app.scheduler import MonitoringScheduler, SchedulerConfig, SchedulerMode

config = SchedulerConfig(mode=SchedulerMode.ONCE)
scheduler = MonitoringScheduler(config=config)

record = scheduler.run_once()

print(f'Run ID: {record.run_id}')
print(f'Success: {record.success}')
print(f'Start time: {record.start_time}')
print(f'End time: {record.end_time}')
print(f'Signals: {record.signals_generated}')
print(f'Error: {record.error}')

assert record.run_id == 1, 'Run ID should be 1'
assert record.success == True, 'Should succeed'
assert record.end_time is not None, 'Should have end time'

print('✅ Run once test passed')
"
```

**Expected Result**:
- Run ID is 1
- Success is True
- Has start and end times
- No error

**Status**: ⬜ Not tested

---

### TC-004: Statistics Tracking / 統計追蹤

**Purpose**: Verify run statistics are tracked

**Steps**:
```python
python3 -c "
from app.scheduler import MonitoringScheduler

scheduler = MonitoringScheduler()

# Run twice
scheduler.run_once()
scheduler.run_once()

stats = scheduler.get_statistics()

print(f'Total runs: {stats[\"total_runs\"]}')
print(f'Successful: {stats[\"successful_runs\"]}')
print(f'Failed: {stats[\"failed_runs\"]}')

assert stats['total_runs'] == 2, 'Should have 2 runs'
assert stats['successful_runs'] == 2, 'Should have 2 successful'
assert stats['failed_runs'] == 0, 'Should have 0 failed'

print('✅ Statistics test passed')
"
```

**Expected Result**:
- Total runs: 2
- Successful: 2
- Failed: 0

**Status**: ⬜ Not tested

---

### TC-005: Overlap Prevention / 重疊防止

**Purpose**: Verify overlapping runs are prevented

**Steps**:
```python
python3 -c "
from app.scheduler import MonitoringScheduler, SchedulerConfig
import time

config = SchedulerConfig(prevent_overlap=True)
scheduler = MonitoringScheduler(config=config)

# First run
result1 = scheduler.run_once()
print(f'First run: {result1.success}')

# Simulate lock held by creating manual lock
from app.scheduler import SchedulerLock
lock = SchedulerLock()
lock.acquire()

# Second run should skip
try:
    result2 = scheduler.run_once()
    print(f'Second run (with lock): {result2.success}, error: {result2.error}')
    assert result2.success == False, 'Should fail due to lock'
    assert 'Lock held' in result2.error, 'Should indicate lock issue'
finally:
    lock.release()

print('✅ Overlap prevention test passed')
"
```

**Expected Result**:
- First run succeeds
- Second run fails with lock message

**Status**: ⬜ Not tested

---

### TC-006: Convenience Function - run_once_with_notification / 便利函數測試

**Purpose**: Verify convenience function works

**Steps**:
```python
python3 -c "
from app.scheduler import run_once_with_notification

# Run with console only
result = run_once_with_notification()

print(f'Success: {result.success}')
print(f'Run ID: {result.run_id}')
print(f'Signals: {record.signals_generated}')

assert result.success == True, 'Should succeed'

print('✅ Convenience function test passed')
"
```

**Expected Result**:
- Function executes successfully
- Returns RunRecord with success=True

**Status**: ⬜ Not tested

---

### TC-007: Interval Mode (Short Test) / 間隔模式（短測試）

**Purpose**: Verify interval execution works

**⚠️ Warning**: This test runs for ~10 seconds

**Steps**:
```python
python3 -c "
from app.scheduler import MonitoringScheduler, SchedulerConfig

config = SchedulerConfig(
    interval_minutes=0.1,  # 6 seconds for testing
    max_runs=2
)
scheduler = MonitoringScheduler(config=config)

import threading
import time

# Stop after 15 seconds
stop_timer = threading.Timer(15, scheduler.stop)
stop_timer.start()

print('Starting interval scheduler for 2 runs...')
scheduler.run_interval()

stats = scheduler.get_statistics()
print(f'Total runs: {stats[\"total_runs\"]}')

assert stats['total_runs'] == 2, 'Should have 2 runs'
print('✅ Interval test passed')
" 2>&1 | head -50
```

**Expected Result**:
- Runs 2 times
- Stops cleanly

**Status**: ⬜ Not tested

---

### TC-008: Logging Output / 日誌輸出

**Purpose**: Verify logging works

**Steps**:
```python
python3 -c "
from app.scheduler import MonitoringScheduler, SchedulerConfig
import os

log_file = '/tmp/test_scheduler.log'
config = SchedulerConfig(
    log_file=log_file,
    enable_file_logging=True
)
scheduler = MonitoringScheduler(config=config)

scheduler.run_once()

# Check log file exists
assert os.path.exists(log_file), f'Log file not found: {log_file}'

# Check log content
with open(log_file, 'r') as f:
    content = f.read()
    assert 'Run #' in content, 'Should have run log'
    print(f'Log content preview: {content[:200]}...')

# Cleanup
os.remove(log_file)

print('✅ Logging test passed')
"
```

**Expected Result**:
- Log file created
- Contains run information

**Status**: ⬜ Not tested

---

### TC-009: Integration with Channels / 與渠道整合

**Purpose**: Verify scheduler works with notification channels

**Steps**:
```python
python3 -c "
from app.scheduler import MonitoringScheduler
from notifications.channels import create_console_channel

channel = create_console_channel()
scheduler = MonitoringScheduler(notification_channel=channel)

result = scheduler.run_once()

assert result.success == True, 'Should succeed'
print('✅ Channel integration test passed')
"
```

**Expected Result**:
- Runs successfully with channel

**Status**: ⬜ Not tested

---

## Quick Test Script / 快速測試腳本

Save as `test_scheduler_quick.py`:

```python
#!/usr/bin/env python3
"""Quick test for scheduler module / 排程器模組快速測試"""

import sys
import os
sys.path.insert(0, '/tmp/kimi-shared-brain')

from app.scheduler import (
    MonitoringScheduler, SchedulerConfig, SchedulerMode,
    SchedulerLock, run_once_with_notification
)

print("="*60)
print("T-030: Scheduler Quick Test")
print("="*60)

# Test 1: Lock
print("\n[1/5] Testing lock...")
lock = SchedulerLock('/tmp/test_lock.tmp')
assert lock.acquire() == True
lock.release()
print("✅ Lock works")

# Test 2: Basic scheduler
print("\n[2/5] Testing basic scheduler...")
scheduler = MonitoringScheduler()
result = scheduler.run_once()
assert result.success == True
print(f"✅ Run completed (signals: {result.signals_generated})")

# Test 3: Statistics
print("\n[3/5] Testing statistics...")
stats = scheduler.get_statistics()
assert stats['total_runs'] >= 1
print(f"✅ Stats: {stats['total_runs']} runs")

# Test 4: Convenience function
print("\n[4/5] Testing convenience function...")
result = run_once_with_notification()
assert result.success == True
print("✅ Convenience function works")

# Test 5: Config options
print("\n[5/5] Testing config options...")
config = SchedulerConfig(
    mode=SchedulerMode.ONCE,
    prevent_overlap=True
)
scheduler2 = MonitoringScheduler(config=config)
result = scheduler2.run_once()
assert result.success == True
print("✅ Config options work")

# Cleanup
if os.path.exists('/tmp/test_lock.tmp'):
    os.remove('/tmp/test_lock.tmp')

print("\n" + "="*60)
print("All tests passed! / 所有測試通過！")
print("="*60)
```

Run with: `python3 test_scheduler_quick.py`

---

## Validation Checklist / 驗證清單

| Test Case | Description | Status |
|-----------|-------------|--------|
| TC-001 | Module import | ⬜ |
| TC-002 | Lock acquire/release | ⬜ |
| TC-003 | Run once mode | ⬜ |
| TC-004 | Statistics tracking | ⬜ |
| TC-005 | Overlap prevention | ⬜ |
| TC-006 | Convenience function | ⬜ |
| TC-007 | Interval mode | ⬜ |
| TC-008 | Logging output | ⬜ |
| TC-009 | Channel integration | ⬜ |

**Overall Status**: ⬜ Pending

---

## Notes / 備註

1. **Interval Test / 間隔測試**:
   - May take 10-15 seconds
   - Use Ctrl+C to interrupt if needed

2. **Network Dependency / 網路依賴**:
   - Tests require Binance API access
   - May fail if network is unavailable

3. **Lock File / 鎖檔案**:
   - Created at `/tmp/kimi-shared-brain/.scheduler.lock`
   - Should be cleaned up automatically
   - Manual removal may be needed if test crashes

---

**Version**: 1.0.0  
**Date**: 2026-04-06
