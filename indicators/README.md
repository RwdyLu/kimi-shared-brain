# Indicator Module / 指標模組

BTC/ETH Monitoring System - Indicator Layer
BTC/ETH 監測系統 - 指標層

## Overview / 概覽

This module provides technical indicator calculations for the monitoring system.
It processes raw kline data and produces calculated indicators for signal generation.

本模組為監測系統提供技術指標計算。
處理原始 K 線資料並產生計算後的指標供訊號產生使用。

## Files / 檔案

| File / 檔案 | Description / 說明 |
|-------------|--------------------|
| `calculator.py` | Main indicator calculator / 主要指標計算器 |
| `README.md` | This file / 本檔案 |

## Supported Indicators / 支援的指標

### Moving Averages / 移動平均

| Indicator / 指標 | Timeframe / 時間框架 | Period / 週期 | Purpose / 用途 |
|------------------|----------------------|---------------|----------------|
| MA5 | 5m | 5 | Short-term momentum / 短期動能 |
| MA20 | 5m | 20 | Medium-term trend / 中期趨勢 |
| MA240 | 5m | 240 | Long-term trend / 長期趨勢 |

### Volume Analysis / 成交量分析

| Indicator / 指標 | Timeframe / 時間框架 | Period / 週期 | Purpose / 用途 |
|------------------|----------------------|---------------|----------------|
| Volume SMA | 1m | 20 | Volume average / 成交量平均 |
| Volume Spike | 1m | Current vs Avg(20) | Signal confirmation / 訊號確認 |

### Cross Detection / 交叉檢測

| Cross Type / 交叉類型 | Indicators / 指標 | Signal / 訊號 |
|------------------------|-------------------|---------------|
| Cross Above | MA5 crosses above MA20 | Bullish / 看漲 |
| Cross Below | MA5 crosses below MA20 | Bearish / 看跌 |

### Candle Patterns / K 線型態

| Pattern / 型態 | Timeframe / 時間框架 | Count / 數量 | Signal / 訊號 |
|----------------|----------------------|--------------|---------------|
| Consecutive Red | 15m | 4 | Overheated / 過熱 |
| Consecutive Green | 15m | 4 | Oversold / 超賣 |

## Usage / 使用方法

### Basic Usage / 基本使用

```python
from indicators.calculator import (
    calculate_ma5,
    calculate_ma20,
    calculate_ma240,
    detect_ma5_ma20_cross,
    analyze_volume,
    detect_four_consecutive_red
)

# Calculate MAs
ma5 = calculate_ma5(closes)
ma20 = calculate_ma20(closes)
ma240 = calculate_ma240(closes)

# Detect cross
cross_result = detect_ma5_ma20_cross(ma5, ma20)

# Analyze volume
volume_result = analyze_volume(current_volume, volumes)

# Detect pattern
pattern = detect_four_consecutive_red(candles_15m)
```

### Moving Average Calculations / 移動平均計算

```python
from indicators.calculator import calculate_sma

# Generic SMA
sma_values = calculate_sma(prices, period=20)

# Specific MAs
from indicators.calculator import calculate_ma5, calculate_ma20, calculate_ma240

ma5 = calculate_ma5(closes)
ma20 = calculate_ma20(closes)
ma240 = calculate_ma240(closes)
```

### Volume Analysis / 成交量分析

```python
from indicators.calculator import analyze_volume, VolumeAnalysisResult

# Analyze current volume
result = analyze_volume(
    current_volume=25.0,
    volumes=[10.0] * 20,
    period=20,
    threshold=2.0
)

print(f"Ratio: {result.ratio:.2f}x")
print(f"Is Spike: {result.is_spike}")
```

### Cross Detection / 交叉檢測

```python
from indicators.calculator import detect_ma_cross, CrossType

# Detect cross
result = detect_ma_cross(short_ma, long_ma)

if result.cross_type == CrossType.CROSS_ABOVE:
    print("Bullish cross detected!")
elif result.cross_type == CrossType.CROSS_BELOW:
    print("Bearish cross detected!")
```

### Candle Pattern Detection / K 線型態檢測

```python
from indicators.calculator import (
    detect_four_consecutive_red,
    detect_four_consecutive_green
)

# Check for patterns
overheated = detect_four_consecutive_red(candles_15m)
oversold = detect_four_consecutive_green(candles_15m)

if overheated.pattern_detected:
    print("⚠️ Overheated - Watch only")
if oversold.pattern_detected:
    print("⚠️ Oversold - Watch only")
```

### High-Level Analysis / 高階分析

```python
from indicators.calculator import (
    analyze_5m_trend_conditions,
    analyze_15m_contrarian_conditions
)

# Analyze 5m trend
trend_analysis = analyze_5m_trend_conditions(closes_5m)

# Analyze 15m contrarian
contrarian_analysis = analyze_15m_contrarian_conditions(candles_15m)
```

## API Reference / API 參考

### Moving Average Functions / 移動平均函式

#### `calculate_sma(values: List[float], period: int) -> List[float]`
Calculate Simple Moving Average / 計算簡單移動平均

#### `calculate_ma5(closes: List[float]) -> List[float]`
Calculate 5-period MA / 計算 5 週期 MA

#### `calculate_ma20(closes: List[float]) -> List[float]`
Calculate 20-period MA / 計算 20 週期 MA

#### `calculate_ma240(closes: List[float]) -> List[float]`
Calculate 240-period MA (~20 hours) / 計算 240 週期 MA（約 20 小時）

### Volume Functions / 成交量函式

#### `calculate_volume_sma(volumes: List[float], period: int = 20) -> float`
Calculate volume SMA / 計算成交量 SMA

#### `analyze_volume(current_volume, volumes, period=20, threshold=2.0) -> VolumeAnalysisResult`
Analyze volume against average / 分析成交量相對於平均值

### Cross Detection Functions / 交叉檢測函式

#### `detect_ma_cross(short_ma, long_ma, timestamp=None) -> MACrossResult`
Detect MA cross / 檢測 MA 交叉

#### `detect_ma5_ma20_cross(ma5, ma20) -> MACrossResult`
Detect MA5 cross MA20 / 檢測 MA5 交叉 MA20

### Candle Pattern Functions / K 線型態函式

#### `get_candle_color(open_price, close_price) -> CandleColor`
Determine candle color / 判斷 K 線顏色

#### `is_red_candle(open_price, close_price) -> bool`
Check if red candle / 檢查是否為紅 K

#### `is_green_candle(open_price, close_price) -> bool`
Check if green candle / 檢查是否為綠 K

#### `detect_consecutive_candles(candles, n=4, candle_type="red") -> CandlePatternResult`
Detect N consecutive candles / 檢測 N 根連續 K 線

#### `detect_four_consecutive_red(candles) -> CandlePatternResult`
Detect 4 consecutive red candles / 檢測 4 根連續紅 K

#### `detect_four_consecutive_green(candles) -> CandlePatternResult`
Detect 4 consecutive green candles / 檢測 4 根連續綠 K

### Analysis Functions / 分析函式

#### `analyze_5m_trend_conditions(closes, ma240=None) -> Dict`
Analyze 5m trend conditions / 分析 5m 趨勢條件

#### `analyze_15m_contrarian_conditions(candles_15m) -> Dict`
Analyze 15m contrarian conditions / 分析 15m 逆勢條件

#### `analyze_volume_conditions(current_volume, volumes, period=20, threshold=2.0) -> VolumeAnalysisResult`
Analyze volume conditions / 分析成交量條件

## Data Classes / 資料類別

### MACrossResult
```python
@dataclass
class MACrossResult:
    cross_type: CrossType        # CROSS_ABOVE, CROSS_BELOW, NO_CROSS
    short_ma_value: float        # Current short MA value
    long_ma_value: float         # Current long MA value
    prev_short_ma: float         # Previous short MA value
    prev_long_ma: float          # Previous long MA value
    timestamp: Optional[int]     # Cross timestamp
```

### VolumeAnalysisResult
```python
@dataclass
class VolumeAnalysisResult:
    current_volume: float        # Current period volume
    avg_volume: float            # Average volume
    ratio: float                 # Current / Average ratio
    is_spike: bool               # True if ratio > threshold
    threshold: float             # Threshold multiplier
```

### CandlePatternResult
```python
@dataclass
class CandlePatternResult:
    pattern_detected: bool       # True if pattern found
    pattern_type: str            # "consecutive_red", "consecutive_green", "none"
    consecutive_count: int       # Number of consecutive candles
    candles_analyzed: int        # Total candles analyzed
```

## Enums / 列舉

### CrossType
- `CROSS_ABOVE` - Short crosses above long
- `CROSS_BELOW` - Short crosses below long
- `NO_CROSS` - No cross detected

### CandleColor
- `RED` - Close < Open
- `GREEN` - Close > Open
- `NEUTRAL` - Close == Open

## Important Notes / 重要注意事項

### ⚠️ Contrarian Signals are WATCH-ONLY / 逆勢訊號僅供觀察

```
╔════════════════════════════════════════════════════════════════╗
║  Candle pattern signals (4 consecutive red/green)              ║
║  are for OBSERVATION ONLY.                                     ║
║  K 線型態訊號（4 連紅/4 連綠）僅供觀察。                        ║
║                                                                ║
║  • NOT execution signals / 不是執行訊號                        ║
║  • For analysis only / 僅供分析                                ║
║  • Require confirmation / 需要確認                             ║
╚════════════════════════════════════════════════════════════════╝
```

## Dependencies / 依賴

- `typing` - Type hints
- `dataclasses` - Data class support
- `enum` - Enum support

## What's NOT Included / 不包含的功能

This module is intentionally limited (Indicator Layer only):
本模組刻意限制（僅指標層）：

- ❌ No signal generation logic / 無訊號產生邏輯
- ❌ No cooldown management / 無冷卻管理
- ❌ No notification sending / 無通知發送
- ❌ No automatic trading / 無自動交易

These are handled by other layers:
這些由其他層級處理：
- Signal Layer / 訊號層 (`signals/`)
- Notification Layer / 通知層 (`notifications/`)

## Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-06 | Initial implementation / 初始實作 |

## References / 參考

- `workflows/btc_eth_monitoring_system.md` - Phase 2 Indicator Definition
- `workflows/btc_eth_monitoring_signal_spec.md` - Signal specifications
- `data/fetcher.py` - Data layer / 資料層
