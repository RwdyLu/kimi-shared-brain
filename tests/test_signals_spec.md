# Test Specification for Signal Engine / Signal Engine 測試規格

**Module / 模組**: `signals/engine.py`  
**Version / 版本**: 1.0.0  
**Date / 日期**: 2026-04-06  
**Status / 狀態**: Specification for manual verification / 手動驗證規格

---

## Overview / 概覽

This document defines manual verification steps for the `signals/engine.py` module.
Manual verification ensures the signal generation logic and cooldown management work correctly.

本文件定義 `signals/engine.py` 模組的手動驗證步驟。
手動驗證確保訊號產生邏輯與冷卻管理正常運作。

---

## Prerequisites / 前置條件

1. Python 3.8+ installed / Python 3.8+ 已安裝
2. Module files available:
   - `signals/engine.py`
   - `data/fetcher.py`
   - `indicators/calculator.py`
3. All modules can be imported / 所有模組可匯入

---

## Test Cases / 測試案例

### TC-001: Module Import / 模組匯入

**Objective / 目的**: Verify the module can be imported without errors

**Steps / 步驟**:
```python
from signals.engine import (
    SignalEngine,
    Signal,
    CooldownManager,
    CooldownConfig,
    SignalType,
    SignalLevel
)

# Verify enums
print(f"Signal types: {[s.value for s in SignalType]}")
print(f"Signal levels: {[s.value for s in SignalLevel]}")
```

**Expected Result / 預期結果**:
- No ImportError / 無 ImportError
- SignalType: trend_long, trend_short, contrarian_watch_overheated, contrarian_watch_oversold
- SignalLevel: confirmed, watch_only

**Pass Criteria / 通過標準**: ✅ Import succeeds

---

### TC-002: CooldownManager Initialization / 冷卻管理器初始化

**Objective / 目的**: Verify cooldown manager can be created

**Steps / 步驟**:
```python
from signals.engine import CooldownManager, CooldownConfig

# Default config
cd1 = CooldownManager()
print(f"Default trend_long cooldown: {cd1.config.trend_long_seconds}s")

# Custom config
custom_config = CooldownConfig(
    trend_long_seconds=300,      # 5 minutes
    trend_short_seconds=300,
    contrarian_watch_seconds=600
)
cd2 = CooldownManager(config=custom_config)
print(f"Custom trend_long cooldown: {cd2.config.trend_long_seconds}s")
```

**Expected Result / 預期結果**:
- cd1: 900s (15 min)
- cd2: 300s (5 min)

**Pass Criteria / 通過標準**: ✅ Initialization works correctly

---

### TC-003: Cooldown Emission and Check / 冷卻發送與檢查

**Objective / 目的**: Verify cooldown emission and checking

**Steps / 步驟**:
```python
from signals.engine import CooldownManager, SignalType
import time

cd = CooldownManager()
symbol = "BTCUSDT"

# First emission should succeed
result1 = cd.can_emit(symbol, SignalType.TREND_LONG)
print(f"First can_emit: {result1}")  # Expected: True

cd.record_emission(symbol, SignalType.TREND_LONG)

# Immediate second emission should fail
result2 = cd.can_emit(symbol, SignalType.TREND_LONG)
print(f"Second can_emit: {result2}")  # Expected: False

# Check remaining cooldown
remaining = cd.get_remaining_cooldown(symbol, SignalType.TREND_LONG)
print(f"Remaining cooldown: {remaining:.0f}s")  # Expected: ~900s
```

**Expected Result / 預期結果**:
- result1: True
- result2: False
- remaining: ~900 seconds

**Pass Criteria / 通過標準**: ✅ Cooldown works correctly

---

### TC-004: SignalEngine Initialization / 訊號引擎初始化

**Objective / 目的**: Verify signal engine can be created

**Steps / 步驟**:
```python
from signals.engine import SignalEngine

# Default initialization
engine1 = SignalEngine()
print(f"Engine1 created: {type(engine1)}")

# With custom cooldown
from signals.engine import CooldownManager, CooldownConfig
custom_cd = CooldownManager(CooldownConfig(trend_long_seconds=600))
engine2 = SignalEngine(cooldown_manager=custom_cd)
print(f"Engine2 created with custom cooldown: {type(engine2)}")
```

**Expected Result / 預期結果**:
- Both engines created successfully
- Type is SignalEngine

**Pass Criteria / 通過標準**: ✅ Initialization works correctly

---

### TC-005: Trend Long Signal Generation / Trend Long 訊號產生

**Objective / 目的**: Verify trend_long signal generation when conditions met

**Steps / 步驟**:
```python
from signals.engine import SignalEngine, SignalType, SignalLevel
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

engine = SignalEngine()

# Create scenario where all conditions are met
# Price above MA240, MA5 cross above MA20, volume spike
prices = [100 + i * 0.1 for i in range(250)]  # Rising prices
volumes = [10] * 19 + [25]  # Spike at the end

ma5 = calculate_ma5(prices)
ma20 = calculate_ma20(prices)
ma240 = calculate_ma240(prices)

signal = engine.generate_trend_long_signal(
    symbol="TESTUSDT",
    close_5m=prices[-1],
    ma5=ma5,
    ma20=ma20,
    ma240=ma240,
    volume_1m=volumes[-1],
    volumes_1m=volumes
)

if signal:
    print(f"Signal type: {signal.signal_type.value}")
    print(f"Level: {signal.level.value}")
    print(f"Reason: {signal.reason}")
    print(f"Conditions: {signal.conditions}")
    print(f"Warning: {signal.warning}")
else:
    print("No signal generated (may be in cooldown or conditions not fully met)")
```

**Expected Result / 預期結果**:
- Signal generated with type=trend_long
- Level=confirmed
- All conditions=True
- Warning=ALERT_ONLY_NO_AUTO_TRADE

**Pass Criteria / 通過標準**: ✅ Signal generated correctly

---

### TC-006: Trend Short Signal Generation / Trend Short 訊號產生

**Objective / 目的**: Verify trend_short signal generation when conditions met

**Steps / 步驟**:
```python
from signals.engine import SignalEngine, SignalType
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

engine = SignalEngine()

# Create scenario for trend short
# Price below MA240, MA5 cross below MA20, volume spike
prices = [150 - i * 0.1 for i in range(250)]  # Falling prices
volumes = [10] * 19 + [25]  # Spike at the end

ma5 = calculate_ma5(prices)
ma20 = calculate_ma20(prices)
ma240 = calculate_ma240(prices)

signal = engine.generate_trend_short_signal(
    symbol="TESTUSDT",
    close_5m=prices[-1],
    ma5=ma5,
    ma20=ma20,
    ma240=ma240,
    volume_1m=volumes[-1],
    volumes_1m=volumes
)

if signal:
    print(f"Signal type: {signal.signal_type.value}")
    print(f"Level: {signal.level.value}")
    print(f"Conditions: {signal.conditions}")
else:
    print("No signal generated")
```

**Expected Result / 預期結果**:
- Signal generated with type=trend_short
- Level=confirmed

**Pass Criteria / 通過標準**: ✅ Signal generated correctly

---

### TC-007: Contrarian Watch Signal Generation / 逆勢觀察訊號產生

**Objective / 目的**: Verify contrarian_watch signal generation

**Steps / 步驟**:
```python
from signals.engine import SignalEngine, SignalType, SignalLevel

engine = SignalEngine()

# 4 consecutive red candles (overheated)
candles_red = [
    {"open": 100, "close": 95},
    {"open": 95, "close": 90},
    {"open": 90, "close": 85},
    {"open": 85, "close": 80}
]

signal = engine.generate_contrarian_watch_signal(
    symbol="TESTUSDT",
    candles_15m=candles_red
)

if signal:
    print(f"Signal type: {signal.signal_type.value}")
    print(f"Level: {signal.level.value}")
    print(f"Warning: {signal.warning}")
    print(f"Pattern: {signal.price_data.get('pattern')}")

# 4 consecutive green candles (oversold)
candles_green = [
    {"open": 100, "close": 105},
    {"open": 105, "close": 110},
    {"open": 110, "close": 115},
    {"open": 115, "close": 120}
]

signal2 = engine.generate_contrarian_watch_signal(
    symbol="TESTUSDT",
    candles_15m=candles_green
)

if signal2:
    print(f"\nSignal type: {signal2.signal_type.value}")
    print(f"Pattern: {signal2.price_data.get('pattern')}")
```

**Expected Result / 預期結果**:
- signal: type=contrarian_watch_overheated, level=watch_only
- signal2: type=contrarian_watch_oversold, level=watch_only
- Both have warning=WATCH_ONLY_NOT_EXECUTION_SIGNAL

**Pass Criteria / 通過標準**: ✅ Contrarian signals generated correctly

---

### TC-008: No Signal When Conditions Not Met / 條件不符時無訊號

**Objective / 目的**: Verify no signal when conditions not met

**Steps / 步驟**:
```python
from signals.engine import SignalEngine
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

engine = SignalEngine()

# Prices without clear trend (no cross)
prices = [100] * 250  # Flat prices
volumes = [10] * 20  # No spike

ma5 = calculate_ma5(prices)
ma20 = calculate_ma20(prices)
ma240 = calculate_ma240(prices)

signal = engine.generate_trend_long_signal(
    symbol="TESTUSDT",
    close_5m=prices[-1],
    ma5=ma5,
    ma20=ma20,
    ma240=ma240,
    volume_1m=volumes[-1],
    volumes_1m=volumes
)

print(f"Signal generated: {signal is not None}")
print(f"Expected: False (no cross, no volume spike)")
```

**Expected Result / 預期結果**:
- signal is None (no signal generated)

**Pass Criteria / 通過標準**: ✅ No false signals

---

### TC-009: Cooldown Prevents Duplicate Signals / 冷卻防止重複訊號

**Objective / 目的**: Verify cooldown prevents duplicate signals

**Steps / 步驟**:
```python
from signals.engine import SignalEngine
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

engine = SignalEngine()

# Rising prices scenario
prices = [100 + i * 0.1 for i in range(250)]
volumes = [10] * 19 + [25]

ma5 = calculate_ma5(prices)
ma20 = calculate_ma20(prices)
ma240 = calculate_ma240(prices)

# First signal
signal1 = engine.generate_trend_long_signal(
    symbol="TESTUSDT",
    close_5m=prices[-1],
    ma5=ma5,
    ma20=ma20,
    ma240=ma240,
    volume_1m=volumes[-1],
    volumes_1m=volumes
)
print(f"First signal: {signal1 is not None}")  # Expected: True

# Second immediate signal (should be blocked by cooldown)
signal2 = engine.generate_trend_long_signal(
    symbol="TESTUSDT",
    close_5m=prices[-1],
    ma5=ma5,
    ma20=ma20,
    ma240=ma240,
    volume_1m=volumes[-1],
    volumes_1m=volumes
)
print(f"Second signal: {signal2 is not None}")  # Expected: False

# Check cooldown status
status = engine.get_cooldown_status("TESTUSDT")
print(f"Trend long cooldown remaining: {status['trend_long']:.0f}s")
```

**Expected Result / 預期結果**:
- signal1: True (generated)
- signal2: False (blocked by cooldown)
- status['trend_long'] > 0

**Pass Criteria / 通過標準**: ✅ Cooldown prevents duplicates

---

### TC-010: Signal Data Structure / 訊號資料結構

**Objective / 目的**: Verify signal data structure and to_dict method

**Steps / 步驟**:
```python
from signals.engine import SignalEngine, SignalType
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

engine = SignalEngine()

prices = [100 + i * 0.1 for i in range(250)]
volumes = [10] * 19 + [25]

ma5 = calculate_ma5(prices)
ma20 = calculate_ma20(prices)
ma240 = calculate_ma240(prices)

signal = engine.generate_trend_long_signal(
    symbol="TESTUSDT",
    close_5m=prices[-1],
    ma5=ma5,
    ma20=ma20,
    ma240=ma240,
    volume_1m=volumes[-1],
    volumes_1m=volumes
)

if signal:
    # Check to_dict
    signal_dict = signal.to_dict()
    print(f"Dict keys: {list(signal_dict.keys())}")
    print(f"signal_type: {signal_dict['signal_type']}")
    print(f"level: {signal_dict['level']}")
    print(f"symbol: {signal_dict['symbol']}")
    print(f"has price_data: {'price_data' in signal_dict}")
    print(f"has conditions: {'conditions' in signal_dict}")
    print(f"has reason: {'reason' in signal_dict}")
    print(f"has warning: {'warning' in signal_dict}")
```

**Expected Result / 預期結果**:
- All required keys present
- Values are correct types

**Pass Criteria / 通過標準**: ✅ Signal structure correct

---

## Summary / 總結

| Test Case / 測試案例 | Description / 說明 | Status / 狀態 |
|----------------------|--------------------|---------------|
| TC-001 | Module Import | ⬜ Pending |
| TC-002 | CooldownManager Init | ⬜ Pending |
| TC-003 | Cooldown Emission | ⬜ Pending |
| TC-004 | SignalEngine Init | ⬜ Pending |
| TC-005 | Trend Long Signal | ⬜ Pending |
| TC-006 | Trend Short Signal | ⬜ Pending |
| TC-007 | Contrarian Signal | ⬜ Pending |
| TC-008 | No False Signals | ⬜ Pending |
| TC-009 | Cooldown Prevents Duplicates | ⬜ Pending |
| TC-010 | Signal Structure | ⬜ Pending |

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
   from signals.engine import SignalEngine
   engine = SignalEngine()
   print(engine)
   ```

## Notes / 注意事項

1. **No Network Required / 不需要網路**: Tests use mock data
2. **Deterministic / 確定性**: Same input always produces same output
3. **Independent / 獨立**: Tests don't depend on external state

## What's NOT Tested / 未測試項目

- ❌ Real-time data processing / 即時資料處理
- ❌ Performance under load / 高負載效能
- ❌ Concurrent access / 並行存取
