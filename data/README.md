# Data Module / 資料模組

BTC/ETH Monitoring System - Data Layer
BTC/ETH 監測系統 - 資料層

## Overview / 概覽

This module provides data fetching capabilities for the BTC/ETH monitoring system.
It handles all interactions with the Binance API and provides normalized data structures.

本模組為 BTC/ETH 監測系統提供資料抓取功能。
處理所有與 Binance API 的互動，並提供標準化的資料結構。

## Files / 檔案

| File / 檔案 | Description / 說明 |
|-------------|--------------------|
| `fetcher.py` | Main data fetcher module / 主要資料抓取模組 |
| `README.md` | This file / 本檔案 |

## Supported Symbols / 支援的標的

| Symbol / 標的 | Asset / 資產 | Description / 說明 |
|---------------|--------------|--------------------|
| BTCUSDT | Bitcoin | Bitcoin / USDT trading pair |
| ETHUSDT | Ethereum | Ethereum / USDT trading pair |

## Supported Intervals / 支援的時間框架

| Interval / 時間框架 | Seconds / 秒數 | Use Case / 用途 |
|---------------------|----------------|-----------------|
| 1m | 60 | Volume confirmation / 成交量確認 |
| 5m | 300 | Primary signal generation / 主訊號產生 |
| 15m | 900 | Contrarian observation / 逆勢觀察 |

## Return Data Format / 回傳資料格式

### KlineData Structure / KlineData 結構

```python
@dataclass
class KlineData:
    timestamp: int    # Kline open timestamp in milliseconds / K線開盤時間戳 (毫秒)
    open: float       # Opening price / 開盤價
    high: float       # Highest price / 最高價
    low: float        # Lowest price / 最低價
    close: float      # Closing price / 收盤價
    volume: float     # Trading volume / 成交量
```

### Dictionary Format / 字典格式

```json
{
  "timestamp": 1775385000000,
  "open": 69250.50,
  "high": 69300.00,
  "low": 69100.00,
  "close": 69250.50,
  "volume": 12.5
}
```

## Usage / 使用方法

### Basic Usage / 基本使用

```python
from data.fetcher import create_fetcher, BinanceFetcher

# Create fetcher instance
fetcher = create_fetcher()

# Fetch single timeframe data
data = fetcher.get_klines("BTCUSDT", "5m", limit=100)

# Access data
for kline in data:
    print(f"Time: {kline.timestamp}, Close: {kline.close}")
```

### Multi-Timeframe Data / 多時間框架資料

```python
# Fetch all supported timeframes
multi_data = fetcher.get_multi_timeframe_data("BTCUSDT")

# Access specific timeframe
m5_data = multi_data["5m"]
m1_data = multi_data["1m"]
m15_data = multi_data["15m"]
```

### Custom Limits / 自定義數量

```python
limits = {
    "1m": 25,   # 25 candles for 1m
    "5m": 250,  # 250 candles for 5m
    "15m": 10   # 10 candles for 15m
}

data = fetcher.get_multi_timeframe_data("ETHUSDT", limits=limits)
```

## API Reference / API 參考

### BinanceFetcher Class / BinanceFetcher 類別

#### `__init__(base_url: str = "https://api.binance.com")`
Initialize the fetcher with optional custom base URL.
使用可選的自訂基礎 URL 初始化抓取器。

#### `fetch_klines(symbol, interval, limit=500, start_time=None, end_time=None) -> List[List]`
Fetch raw kline data from Binance API.
從 Binance API 抓取原始 K 線資料。

**Parameters / 參數:**
- `symbol`: Trading pair (e.g., "BTCUSDT") / 交易對
- `interval`: Kline interval (e.g., "5m") / K 線時間框架
- `limit`: Number of candles (max 1000) / K 線數量
- `start_time`: Start timestamp in ms / 開始時間戳
- `end_time`: End timestamp in ms / 結束時間戳

**Returns / 回傳:**
- Raw kline data from API / 來自 API 的原始 K 線資料

**Raises / 拋出:**
- `ValueError`: Invalid symbol or interval / 無效的標的或時間框架
- `requests.RequestException`: API request failed / API 請求失敗

#### `normalize_kline_data(raw_data: List[List]) -> List[KlineData]`
Convert raw Binance data to normalized KlineData objects.
將原始 Binance 資料轉換為標準化的 KlineData 物件。

**Parameters / 參數:**
- `raw_data`: Raw data from fetch_klines / 來自 fetch_klines 的原始資料

**Returns / 回傳:**
- List of KlineData objects / KlineData 物件列表

#### `get_klines(symbol, interval, limit=500) -> List[KlineData]`
Convenience method: fetch and normalize in one call.
便利方法：一次呼叫完成抓取與標準化。

#### `get_multi_timeframe_data(symbol, timeframes=None, limits=None) -> Dict[str, List[KlineData]]`
Fetch data for multiple timeframes in one call.
一次呼叫抓取多個時間框架的資料。

**Parameters / 參數:**
- `symbol`: Trading pair / 交易對
- `timeframes`: List of intervals (default: all) / 時間框架列表（預設：全部）
- `limits`: Dict of interval -> limit / 時間框架到數量的字典

**Returns / 回傳:**
- Dict mapping interval to KlineData list / 時間框架到 KlineData 列表的字典

### Utility Functions / 工具函式

#### `create_fetcher() -> BinanceFetcher`
Factory function to create a new fetcher instance.
建立新抓取器實例的工廠函式。

## Error Handling / 錯誤處理

The module handles the following error cases:
本模組處理以下錯誤情況：

| Error / 錯誤 | Handling / 處理 | Exception / 例外 |
|--------------|-----------------|------------------|
| Invalid symbol / 無效標的 | Validation before request / 請求前驗證 | `ValueError` |
| Invalid interval / 無效時間框架 | Validation before request / 請求前驗證 | `ValueError` |
| API timeout / API 逾時 | Retry with timeout / 逾時重試 | `requests.RequestException` |
| HTTP error / HTTP 錯誤 | Raise with status code / 帶狀態碼拋出 | `requests.RequestException` |
| Empty response / 空回應 | Raise value error / 拋出數值錯誤 | `ValueError` |
| Invalid data format / 無效資料格式 | Raise with index info / 帶索引資訊拋出 | `ValueError` |

## Rate Limiting / 速率限制

Binance API has a rate limit of 1200 requests per minute.
This module implements automatic rate limiting to stay within this limit.

Binance API 有每分鐘 1200 次請求的速率限制。
本模組實作自動速率限制以遵守此限制。

## Dependencies / 依賴

- `requests`: HTTP client library
- `typing`: Type hints
- `dataclasses`: Data class support

## Notes / 注意事項

1. **No API Key Required / 不需要 API Key**: Binance kline endpoint is public
2. **Rate Limiting / 速率限制**: Automatic rate limiting is applied
3. **Error Recovery / 錯誤恢復**: Caller should handle exceptions and retry if needed
4. **Data Freshness / 資料新鮮度**: Data is fetched in real-time from Binance

## What's NOT Included / 不包含的功能

This module is intentionally minimal (Data Layer only):
本模組刻意保持最小（僅資料層）：

- ❌ No MA calculations / 無 MA 計算
- ❌ No signal detection / 無訊號檢測
- ❌ No notification sending / 無通知發送
- ❌ No automatic trading / 無自動交易
- ❌ No data persistence / 無資料持久化

These will be implemented in subsequent layers:
這些將在後續層級實作：
- Indicator Layer / 指標層 (`indicators/`)
- Signal Layer / 訊號層 (`signals/`)
- Notification Layer / 通知層 (`notifications/`)

## Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-06 | Initial implementation / 初始實作 |

## References / 參考

- [Binance API Documentation](https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data)
- `workflows/btc_eth_monitoring_system.md` - System design / 系統設計
- `workflows/btc_eth_monitoring_signal_spec.md` - Signal specification / 訊號規格
