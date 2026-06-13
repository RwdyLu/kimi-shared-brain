# Test Specification for Indicator Calculator / Indicator Calculator 測試規格

**Module / 模組**: `indicators/calculator.py`  
**Version / 版本**: 1.0.0  
**Date / 日期**: 2026-04-06  
**Status / 狀態**: Specification for manual verification / 手動驗證規格

---

## Overview / 概覽

This document defines manual verification steps for the `indicators/calculator.py` module.
Manual verification ensures the indicator calculations work correctly.

本文件定義 `indicators/calculator.py` 模組的手動驗證步驟。
手動驗證確保指標計算正確運作。

---

## Prerequisites / 前置條件

1. Python 3.8+ installed / Python 3.8+ 已安裝
2. Module files available: `indicators/calculator.py` / 模組檔案可用
3. Data module available (optional, for integration) / 資料模組可用（可選，用於整合）

---

## Test Cases / 測試案例

### TC-001: Module Import / 模組匯入

**Objective / 目的**: Verify the module can be imported without errors

**Steps / 步驟**:
```python
from indicators.calculator import (
    # Functions / 函式
    calculate_sma,
    calculate_ma5,
    calculate_ma20,
    calculate_ma240,
    calculate_volume_sma,
    analyze_volume,
    detect_ma_cross,
    detect_ma5_ma20_cross,
    get_candle_color,
    is_red_candle,
    is_green_candle,
    detect_consecutive_candles,
    detect_four_consecutive_red,
    detect_four_consecutive_green,
    analyze_5m_trend_conditions,
    analyze_15m_contrarian_conditions,
    get_latest_ma_values,
    
    # Classes / 類別
    MACrossResult,
    VolumeAnalysisResult,
    CandlePatternResult,
    
    # Enums / 列舉
    CrossType,
    CandleColor
)
```

**Expected Result / 預期結果**:
- No ImportError / 無 ImportError
- All imports successful / 所有匯入成功

**Pass Criteria / 通過標準**: ✅ Import succeeds without errors

---

### TC-002: SMA Calculation / SMA 計算

**Objective / 目的**: Verify Simple Moving Average calculation

**Steps / 步驟**:
```python
from indicators.calculator import calculate_sma

# Test basic SMA
values = [10, 11, 12, 13, 14, 15]
result = calculate_sma(values, period=3)

print(f"Input: {values}")
print(f"SMA(3): {result}")
print(f"Expected: [11.0, 12.0, 13.0, 14.0]")

# Test insufficient data
short_values = [1, 2]
result_short = calculate_sma(short_values, period=5)
print(f"Insufficient data result: {result_short}")
print(f"Expected: []")
```

**Expected Result / 預期結果**:
- `result` = `[11.0, 12.0, 13.0, 14.0]`
- `result_short` = `[]` (empty list)

**Pass Criteria / 通過標準**: ✅ SMA calculation is correct

---

### TC-003: MA5, MA20, MA240 Calculations / MA5、MA20、MA240 計算

**Objective / 目的**: Verify specific MA calculations

**Steps / 步驟**:
```python
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

# Generate test data (enough for MA240)
import random
random.seed(42)
prices = [100 + random.gauss(0, 2) for _ in range(250)]

ma5 = calculate_ma5(prices)
ma20 = calculate_ma20(prices)
ma240 = calculate_ma240(prices)

print(f"Input length: {len(prices)}")
print(f"MA5 length: {len(ma5)}")
print(f"MA20 length: {len(ma20)}")
print(f"MA240 length: {len(ma240)}")

print(f"\nLatest values:")
print(f"  MA5: {ma5[-1]:.2f}")
print(f"  MA20: {ma20[-1]:.2f}")
print(f"  MA240: {ma240[-1]:.2f}")

# Verify lengths
assert len(ma5) == len(prices) - 5 + 1
assert len(ma20) == len(prices) - 20 + 1
assert len(ma240) == len(prices) - 240 + 1
print("\nLength verification: PASSED")
```

**Expected Result / 預期結果**:
- MA5 length = 246
- MA20 length = 231
- MA240 length = 11
- All MA values are floats / 所有 MA 值為浮點數

**Pass Criteria / 通過標準**: ✅ All MA calculations correct

---

### TC-004: Volume SMA Calculation / 成交量 SMA 計算

**Objective / 目的**: Verify volume SMA calculation

**Steps / 步驟**:
```python
from indicators.calculator import calculate_volume_sma

volumes = [100, 110, 120, 130, 140, 150, 160, 170, 180, 190]

# Calculate SMA with period 5
sma5 = calculate_volume_sma(volumes, period=5)
print(f"Volumes: {volumes}")
print(f"Volume SMA(5): {sma5}")
print(f"Expected: 170.0 (average of last 5)")

# Calculate SMA with period 20 (insufficient data)
sma20 = calculate_volume_sma(volumes, period=20)
print(f"Volume SMA(20): {sma20}")
print(f"Expected: 0.0")
```

**Expected Result / 預期結果**:
- `sma5` = `170.0`
- `sma20` = `0.0` (insufficient data)

**Pass Criteria / 通過標準**: ✅ Volume SMA calculation correct

---

### TC-005: Volume Analysis / 成交量分析

**Objective / 目的**: Verify volume spike detection

**Steps / 步驟**:
```python
from indicators.calculator import analyze_volume

# Normal volume
volumes = [10.0] * 20  # 20 periods of volume 10
current = 15.0
result = analyze_volume(current, volumes, period=20, threshold=2.0)

print(f"Current volume: {current}")
print(f"Average volume: {result.avg_volume}")
print(f"Ratio: {result.ratio:.2f}x")
print(f"Is spike: {result.is_spike}")
print(f"Expected: is_spike = False")

# Spike volume
current_spike = 25.0
result_spike = analyze_volume(current_spike, volumes, period=20, threshold=2.0)

print(f"\nCurrent volume: {current_spike}")
print(f"Average volume: {result_spike.avg_volume}")
print(f"Ratio: {result_spike.ratio:.2f}x")
print(f"Is spike: {result_spike.is_spike}")
print(f"Expected: is_spike = True")
```

**Expected Result / 預期結果**:
- Normal: ratio = 1.5x, is_spike = False
- Spike: ratio = 2.5x, is_spike = True

**Pass Criteria / 通過標準**: ✅ Volume analysis correct

---

### TC-006: Cross Detection - Cross Above / 交叉檢測 - 上穿

**Objective / 目的**: Verify cross above detection

**Steps / 步驟**:
```python
from indicators.calculator import detect_ma_cross, CrossType

# Create scenario: short crosses above long
short_ma = [90, 95, 100, 105]  # Rising
long_ma = [100, 100, 100, 100]  # Flat

result = detect_ma_cross(short_ma, long_ma)

print(f"Short MA: {short_ma}")
print(f"Long MA: {long_ma}")
print(f"Cross type: {result.cross_type}")
print(f"Expected: CrossType.CROSS_ABOVE")
print(f"Current short: {result.short_ma_value}")
print(f"Current long: {result.long_ma_value}")
```

**Expected Result / 預期結果**:
- `cross_type` = `CrossType.CROSS_ABOVE`
- `short_ma_value` = `105`
- `long_ma_value` = `100`

**Pass Criteria / 通過標準**: ✅ Cross above detected correctly

---

### TC-007: Cross Detection - Cross Below / 交叉檢測 - 下穿

**Objective / 目的**: Verify cross below detection

**Steps / 步驟**:
```python
from indicators.calculator import detect_ma_cross, CrossType

# Create scenario: short crosses below long
short_ma = [110, 105, 100, 95]  # Falling
long_ma = [100, 100, 100, 100]  # Flat

result = detect_ma_cross(short_ma, long_ma)

print(f"Short MA: {short_ma}")
print(f"Long MA: {long_ma}")
print(f"Cross type: {result.cross_type}")
print(f"Expected: CrossType.CROSS_BELOW")
```

**Expected Result / 預期結果**:
- `cross_type` = `CrossType.CROSS_BELOW`

**Pass Criteria / 通過標準**: ✅ Cross below detected correctly

---

### TC-008: Cross Detection - No Cross / 交叉檢測 - 無交叉

**Objective / 目的**: Verify no cross detection

**Steps / 步驟**:
```python
from indicators.calculator import detect_ma_cross, CrossType

# No cross scenario
short_ma = [105, 106, 107]  # Always above
long_ma = [100, 100, 100]

result = detect_ma_cross(short_ma, long_ma)
print(f"Always above: {result.cross_type}")
print(f"Expected: CrossType.NO_CROSS")

# No cross scenario (always below)
short_ma2 = [95, 94, 93]  # Always below
long_ma2 = [100, 100, 100]

result2 = detect_ma_cross(short_ma2, long_ma2)
print(f"Always below: {result2.cross_type}")
print(f"Expected: CrossType.NO_CROSS")
```

**Expected Result / 預期結果**:
- Both results = `CrossType.NO_CROSS`

**Pass Criteria / 通過標準**: ✅ No cross detected correctly

---

### TC-009: Candle Color Detection / K 線顏色檢測

**Objective / 目的**: Verify candle color detection

**Steps / 步驟**:
```python
from indicators.calculator import (
    get_candle_color, is_red_candle, is_green_candle, CandleColor
)

# Red candle (close < open)
print(f"Red candle: {get_candle_color(100, 95)}")
print(f"is_red_candle(100, 95): {is_red_candle(100, 95)}")

# Green candle (close > open)
print(f"Green candle: {get_candle_color(100, 105)}")
print(f"is_green_candle(100, 105): {is_green_candle(100, 105)}")

# Neutral candle (close == open)
print(f"Neutral candle: {get_candle_color(100, 100)}")
```

**Expected Result / 預期結果**:
- Red: `CandleColor.RED`, `is_red_candle` = True
- Green: `CandleColor.GREEN`, `is_green_candle` = True
- Neutral: `CandleColor.NEUTRAL`

**Pass Criteria / 通過標準**: ✅ Candle color detection correct

---

### TC-010: Consecutive Red Detection / 連續紅 K 檢測

**Objective / 目的**: Verify 4 consecutive red candles detection

**Steps / 步驟**:
```python
from indicators.calculator import detect_four_consecutive_red

# 4 consecutive red candles
candles_red = [
    {"open": 100, "close": 95},
    {"open": 95, "close": 90},
    {"open": 90, "close": 85},
    {"open": 85, "close": 80}
]

result = detect_four_consecutive_red(candles_red)
print(f"4 red candles - Detected: {result.pattern_detected}")
print(f"Pattern type: {result.pattern_type}")
print(f"Expected: True, 'consecutive_red'")

# Not consecutive (mixed)
candles_mixed = [
    {"open": 100, "close": 95},   # Red
    {"open": 95, "close": 96},    # Green
    {"open": 96, "close": 90},    # Red
    {"open": 90, "close": 85}     # Red
]

result2 = detect_four_consecutive_red(candles_mixed)
print(f"\nMixed candles - Detected: {result2.pattern_detected}")
print(f"Expected: False")
```

**Expected Result / 預期結果**:
- 4 red: `pattern_detected` = True, `pattern_type` = "consecutive_red"
- Mixed: `pattern_detected` = False

**Pass Criteria / 通過標準**: ✅ Pattern detection correct

---

### TC-011: Consecutive Green Detection / 連續綠 K 檢測

**Objective / 目的**: Verify 4 consecutive green candles detection

**Steps / 步驟**:
```python
from indicators.calculator import detect_four_consecutive_green

# 4 consecutive green candles
candles_green = [
    {"open": 100, "close": 105},
    {"open": 105, "close": 110},
    {"open": 110, "close": 115},
    {"open": 115, "close": 120}
]

result = detect_four_consecutive_green(candles_green)
print(f"4 green candles - Detected: {result.pattern_detected}")
print(f"Pattern type: {result.pattern_type}")
print(f"Expected: True, 'consecutive_green'")
```

**Expected Result / 預期結果**:
- `pattern_detected` = True
- `pattern_type` = "consecutive_green"

**Pass Criteria / 通過標準**: ✅ Pattern detection correct

---

### TC-012: 5m Trend Analysis / 5m 趨勢分析

**Objective / 目的**: Verify 5m trend condition analysis

**Steps / 步驟**:
```python
from indicators.calculator import analyze_5m_trend_conditions
import random

random.seed(42)
# Generate 250 prices for MA240
prices = [100 + i * 0.1 + random.gauss(0, 1) for i in range(250)]

result = analyze_5m_trend_conditions(prices)

print(f"Current close: {result['current_close']:.2f}")
print(f"MA5: {result['ma5']:.2f}")
print(f"MA20: {result['ma20']:.2f}")
print(f"MA240: {result['ma240']:.2f}")
print(f"Above MA240: {result['above_ma240']}")
print(f"Cross result: {result['cross_result'].cross_type}")
```

**Expected Result / 預期結果**:
- All MA values present / 所有 MA 值存在
- `above_ma240` is boolean / `above_ma240` 為布林值
- Cross result is valid / 交叉結果有效

**Pass Criteria / 通過標準**: ✅ Trend analysis works correctly

---

### TC-013: Error Handling - Insufficient Data / 錯誤處理 - 資料不足

**Objective / 目的**: Verify handling of insufficient data

**Steps / 步驟**:
```python
from indicators.calculator import analyze_5m_trend_conditions

# Less than 240 candles
short_prices = [100] * 100

result = analyze_5m_trend_conditions(short_prices)

print(f"Result: {result}")
print(f"Expected error message present: {'error' in result}")
print(f"Expected candles required: {result.get('candles_required')}")
```

**Expected Result / 預期結果**:
- Result contains error message / 結果包含錯誤訊息
- `candles_required` = 240

**Pass Criteria / 通過標準**: ✅ Error handling correct

---

## Summary / 總結

| Test Case / 測試案例 | Description / 說明 | Status / 狀態 |
|----------------------|--------------------|---------------|
| TC-001 | Module Import | ⬜ Pending |
| TC-002 | SMA Calculation | ⬜ Pending |
| TC-003 | MA5/MA20/MA240 | ⬜ Pending |
| TC-004 | Volume SMA | ⬜ Pending |
| TC-005 | Volume Analysis | ⬜ Pending |
| TC-006 | Cross Above | ⬜ Pending |
| TC-007 | Cross Below | ⬜ Pending |
| TC-008 | No Cross | ⬜ Pending |
| TC-009 | Candle Color | ⬜ Pending |
| TC-010 | Consecutive Red | ⬜ Pending |
| TC-011 | Consecutive Green | ⬜ Pending |
| TC-012 | 5m Trend Analysis | ⬜ Pending |
| TC-013 | Error Handling | ⬜ Pending |

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
   from indicators.calculator import calculate_sma
   result = calculate_sma([1, 2, 3, 4, 5], 3)
   print(result)
   ```

4. Or create test script / 或建立測試腳本:
   ```bash
   python3 -c "
   from indicators.calculator import calculate_ma5
   result = calculate_ma5([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
   print(f'MA5: {result}')
   "
   ```

## Integration Test with Data Layer / 與資料層整合測試

```python
# If data module is available / 若資料模組可用
from data.fetcher import create_fetcher
from indicators.calculator import analyze_5m_trend_conditions

fetcher = create_fetcher()
data = fetcher.get_klines("BTCUSDT", "5m", limit=250)
closes = [k.close for k in data]

trend = analyze_5m_trend_conditions(closes)
print(f"MA5: {trend['ma5']:.2f}")
print(f"MA20: {trend['ma20']:.2f}")
print(f"MA240: {trend['ma240']:.2f}")
```

## Notes / 注意事項

1. **Pure Python / 純 Python**: No external dependencies required
2. **Deterministic / 確定性**: Same input always produces same output
3. **Edge Cases / 邊緣情況**: Module handles insufficient data gracefully

## What's NOT Tested / 未測試項目

- ❌ Real-time integration / 即時整合
- ❌ Performance under load / 高負載效能
- ❌ Concurrent access / 並行存取
