# Test Specification for Data Fetcher / Data Fetcher 測試規格

**Module / 模組**: `data/fetcher.py`  
**Version / 版本**: 1.0.0  
**Date / 日期**: 2026-04-06  
**Status / 狀態**: Specification for manual verification / 手動驗證規格

---

## Overview / 概覽

This document defines manual verification steps for the `data/fetcher.py` module.
No automated unit tests are required at this stage, but manual verification ensures
the module works correctly.

本文件定義 `data/fetcher.py` 模組的手動驗證步驟。
此階段不需要自動化單元測試，但手動驗證確保模組正常運作。

---

## Prerequisites / 前置條件

1. Python 3.8+ installed / Python 3.8+ 已安裝
2. `requests` library installed: `pip install requests`
3. Internet connection / 網路連線
4. Binance API accessible / Binance API 可存取

---

## Test Cases / 測試案例

### TC-001: Module Import / 模組匯入

**Objective / 目的**: Verify the module can be imported without errors

**Steps / 步驟**:
```python
# In Python REPL or script
from data.fetcher import (
    BinanceFetcher,
    KlineData,
    create_fetcher,
    SUPPORTED_SYMBOLS,
    SUPPORTED_INTERVALS
)
```

**Expected Result / 預期結果**:
- No ImportError / 無 ImportError
- All imports successful / 所有匯入成功

**Pass Criteria / 通過標準**: ✅ Import succeeds without errors

---

### TC-002: Fetcher Initialization / 抓取器初始化

**Objective / 目的**: Verify fetcher can be created

**Steps / 步驟**:
```python
from data.fetcher import create_fetcher, BinanceFetcher

# Test factory function
fetcher1 = create_fetcher()

# Test direct instantiation
fetcher2 = BinanceFetcher()

# Test with custom URL
fetcher3 = BinanceFetcher(base_url="https://api.binance.com")
```

**Expected Result / 預期結果**:
- All fetchers created successfully / 所有抓取器成功建立
- Type is BinanceFetcher / 類型為 BinanceFetcher

**Pass Criteria / 通過標準**: ✅ All instantiations succeed

---

### TC-003: Supported Symbols Validation / 支援標的驗證

**Objective / 目的**: Verify symbol validation works

**Steps / 步驟**:
```python
from data.fetcher import SUPPORTED_SYMBOLS, BinanceFetcher

fetcher = BinanceFetcher()

# Check supported symbols
print(f"Supported: {SUPPORTED_SYMBOLS}")
# Expected: ['BTCUSDT', 'ETHUSDT']

# Test valid symbol
fetcher._validate_symbol("BTCUSDT")  # Should pass
fetcher._validate_symbol("ETHUSDT")  # Should pass

# Test invalid symbol
try:
    fetcher._validate_symbol("INVALID")
    print("FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"PASS: Caught expected error: {e}")
```

**Expected Result / 預期結果**:
- Valid symbols pass / 有效標的通過
- Invalid symbol raises ValueError / 無效標的拋出 ValueError

**Pass Criteria / 通過標準**: ✅ Validation works correctly

---

### TC-004: Supported Intervals Validation / 支援時間框架驗證

**Objective / 目的**: Verify interval validation works

**Steps / 步驟**:
```python
from data.fetcher import SUPPORTED_INTERVALS, BinanceFetcher

fetcher = BinanceFetcher()

# Check supported intervals
print(f"Supported: {SUPPORTED_INTERVALS}")
# Expected: ['1m', '5m', '15m']

# Test valid intervals
fetcher._validate_interval("1m")   # Should pass
fetcher._validate_interval("5m")   # Should pass
fetcher._validate_interval("15m")  # Should pass

# Test invalid interval
try:
    fetcher._validate_interval("30m")
    print("FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"PASS: Caught expected error: {e}")
```

**Expected Result / 預期結果**:
- Valid intervals pass / 有效時間框架通過
- Invalid interval raises ValueError / 無效時間框架拋出 ValueError

**Pass Criteria / 通過標準**: ✅ Validation works correctly

---

### TC-005: Fetch Raw Klines / 抓取原始 K 線

**Objective / 目的**: Verify raw data fetching from Binance

**Steps / 步驟**:
```python
from data.fetcher import BinanceFetcher

fetcher = BinanceFetcher()

# Fetch BTC 5m data
raw_data = fetcher.fetch_klines("BTCUSDT", "5m", limit=10)

print(f"Fetched {len(raw_data)} candles")
print(f"First candle fields: {len(raw_data[0])}")
print(f"First candle sample: {raw_data[0][:6]}")
```

**Expected Result / 預期結果**:
- Returns list of 10 candles / 回傳 10 根 K 線列表
- Each candle has 12 fields (Binance format) / 每根 K 線有 12 個欄位
- Fields include: timestamp, open, high, low, close, volume / 欄位包含：時間戳、開高低收、成交量

**Sample Output / 範例輸出**:
```
Fetched 10 candles
First candle fields: 12
First candle sample: [1775385000000, '69250.50', '69300.00', '69100.00', '69250.50', '12.5']
```

**Pass Criteria / 通過標準**: ✅ Data fetched successfully with correct format

---

### TC-006: Normalize Kline Data / 標準化 K 線資料

**Objective / 目的**: Verify raw data normalization

**Steps / 步驟**:
```python
from data.fetcher import BinanceFetcher, KlineData

fetcher = BinanceFetcher()

# Fetch and normalize
raw_data = fetcher.fetch_klines("BTCUSDT", "5m", limit=5)
normalized = fetcher.normalize_kline_data(raw_data)

print(f"Normalized {len(normalized)} candles")
print(f"Type: {type(normalized[0])}")

# Check first candle
first = normalized[0]
print(f"\nFirst candle:")
print(f"  timestamp: {first.timestamp}")
print(f"  open: {first.open}")
print(f"  high: {first.high}")
print(f"  low: {first.low}")
print(f"  close: {first.close}")
print(f"  volume: {first.volume}")

# Convert to dict
dict_format = first.to_dict()
print(f"\nDict format: {dict_format}")
```

**Expected Result / 預期結果**:
- Returns list of KlineData objects / 回傳 KlineData 物件列表
- All fields are correct types / 所有欄位類型正確
- Dict conversion works / 字典轉換正常

**Pass Criteria / 通過標準**: ✅ Normalization produces correct KlineData objects

---

### TC-007: Get Klines (Convenience Method) / 取得 K 線（便利方法）

**Objective / 目的**: Verify combined fetch and normalize

**Steps / 步驟**:
```python
from data.fetcher import BinanceFetcher

fetcher = BinanceFetcher()

# Get ETH 1m data
data = fetcher.get_klines("ETHUSDT", "1m", limit=20)

print(f"Fetched {len(data)} candles")
print(f"Type: {type(data[0])}")
print(f"Timestamp range: {data[0].timestamp} - {data[-1].timestamp}")
print(f"Close price range: {data[0].close} - {data[-1].close}")
```

**Expected Result / 預期結果**:
- Returns 20 KlineData objects / 回傳 20 個 KlineData 物件
- Timestamps are sequential / 時間戳連續
- Price data is reasonable / 價格資料合理

**Pass Criteria / 通過標準**: ✅ Convenience method works correctly

---

### TC-008: Multi-Timeframe Data / 多時間框架資料

**Objective / 目的**: Verify fetching multiple timeframes

**Steps / 步驟**:
```python
from data.fetcher import BinanceFetcher

fetcher = BinanceFetcher()

# Fetch all timeframes for BTC
multi_data = fetcher.get_multi_timeframe_data("BTCUSDT")

print("Multi-timeframe results:")
for interval, data in multi_data.items():
    print(f"  {interval}: {len(data)} candles")
    if data:
        print(f"    First close: {data[0].close}")
        print(f"    Last close: {data[-1].close}")

# Fetch specific timeframes only
partial_data = fetcher.get_multi_timeframe_data(
    "ETHUSDT",
    timeframes=["1m", "5m"]
)
print(f"\nPartial fetch: {list(partial_data.keys())}")
```

**Expected Result / 預期結果**:
- Returns dict with all intervals / 回傳包含所有時間框架的字典
- Each interval has correct number of candles / 每個時間框架有正確數量的 K 線
- Default limits: 1m=25, 5m=250, 15m=10 / 預設數量：1m=25, 5m=250, 15m=10

**Pass Criteria / 通過標準**: ✅ Multi-timeframe fetch works correctly

---

### TC-009: Error Handling - Invalid Symbol / 錯誤處理 - 無效標的

**Objective / 目的**: Verify error handling for invalid symbol

**Steps / 步驟**:
```python
from data.fetcher import BinanceFetcher

fetcher = BinanceFetcher()

try:
    data = fetcher.get_klines("INVALID", "5m", limit=10)
    print("FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"PASS: Caught expected ValueError")
    print(f"Error message: {e}")
```

**Expected Result / 預期結果**:
- Raises ValueError / 拋出 ValueError
- Error message mentions supported symbols / 錯誤訊息提及支援的標的

**Pass Criteria / 通過標準**: ✅ Error handled correctly

---

### TC-010: Error Handling - Invalid Interval / 錯誤處理 - 無效時間框架

**Objective / 目的**: Verify error handling for invalid interval

**Steps / 步驟**:
```python
from data.fetcher import BinanceFetcher

fetcher = BinanceFetcher()

try:
    data = fetcher.get_klines("BTCUSDT", "30m", limit=10)
    print("FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"PASS: Caught expected ValueError")
    print(f"Error message: {e}")
```

**Expected Result / 預期結果**:
- Raises ValueError / 拋出 ValueError
- Error message mentions supported intervals / 錯誤訊息提及支援的時間框架

**Pass Criteria / 通過標準**: ✅ Error handled correctly

---

### TC-011: KlineData Data Class / KlineData 資料類別

**Objective / 目的**: Verify KlineData functionality

**Steps / 步驟**:
```python
from data.fetcher import KlineData

# Create from values
kline = KlineData(
    timestamp=1775385000000,
    open=69250.50,
    high=69300.00,
    low=69100.00,
    close=69250.50,
    volume=12.5
)

print(f"Created: {kline}")
print(f"to_dict(): {kline.to_dict()}")

# Create from dict
kline2 = KlineData.from_dict(kline.to_dict())
print(f"from_dict(): {kline2}")
print(f"Equal: {kline == kline2}")
```

**Expected Result / 預期結果**:
- Object created with correct values / 物件以正確數值建立
- to_dict() returns correct dict / to_dict() 回傳正確字典
- from_dict() recreates equivalent object / from_dict() 重建等價物件

**Pass Criteria / 通過標準**: ✅ KlineData works correctly

---

## Summary / 總結

| Test Case / 測試案例 | Description / 說明 | Status / 狀態 |
|----------------------|--------------------|---------------|
| TC-001 | Module Import | ⬜ Pending |
| TC-002 | Fetcher Initialization | ⬜ Pending |
| TC-003 | Symbol Validation | ⬜ Pending |
| TC-004 | Interval Validation | ⬜ Pending |
| TC-005 | Fetch Raw Klines | ⬜ Pending |
| TC-006 | Normalize Data | ⬜ Pending |
| TC-007 | Get Klines | ⬜ Pending |
| TC-008 | Multi-Timeframe | ⬜ Pending |
| TC-009 | Error - Invalid Symbol | ⬜ Pending |
| TC-010 | Error - Invalid Interval | ⬜ Pending |
| TC-011 | KlineData Class | ⬜ Pending |

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
   from data.fetcher import BinanceFetcher
   fetcher = BinanceFetcher()
   # ... etc
   ```

4. Or create test script / 或建立測試腳本:
   ```bash
   python3 -c "
   from data.fetcher import create_fetcher
   fetcher = create_fetcher()
   data = fetcher.get_klines('BTCUSDT', '5m', limit=5)
   print(f'Fetched {len(data)} candles')
   "
   ```

## Notes / 注意事項

1. **Network Required / 需要網路**: Tests require internet access to Binance
2. **Rate Limiting / 速率限制**: Tests include rate limiting, may be slow
3. **Market Hours / 市場時間**: Binance operates 24/7, but data availability may vary
4. **Data Freshness / 資料新鮮度**: Prices will vary based on current market

## What's NOT Tested / 未測試項目

These are intentionally out of scope for this module:
以下刻意不在此模組範圍內：

- ❌ Network failure recovery / 網路失敗恢復
- ❌ API key authentication / API 金鑰認證
- ❌ WebSocket streaming / WebSocket 串流
- ❌ Historical data pagination / 歷史資料分頁
- ❌ Data persistence / 資料持久化

These may be added in future iterations.
這些可能在未來迭代中添加。
