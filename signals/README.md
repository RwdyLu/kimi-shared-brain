# Signal Engine Module / 訊號引擎模組

BTC/ETH Monitoring System - Signal Layer
BTC/ETH 監測系統 - 訊號層

## Overview / 概覽

This module provides signal generation and cooldown management for the monitoring system.
It combines data from the Data Layer and indicators from the Indicator Layer to generate signals.

本模組提供訊號產生與冷卻管理。結合資料層的資料與指標層的指標產生訊號。

⚠️  **ALERT ONLY / 僅提醒**
This module generates ALERTS ONLY. No automatic trading is performed.
本模組僅產生提醒，不執行自動交易。

## Files / 檔案

| File / 檔案 | Description / 說明 |
|-------------|--------------------|
| `engine.py` | Signal generation engine / 訊號產生引擎 |
| `README.md` | This file / 本檔案 |

## Signal Types / 訊號類型

| Signal / 訊號 | Level / 層級 | Description / 說明 |
|---------------|--------------|--------------------|
| `trend_long` | Confirmed / 確認 | Bullish trend-following signal / 看漲順勢訊號 |
| `trend_short` | Confirmed / 確認 | Bearish trend-following signal / 看跌順勢訊號 |
| `contrarian_watch_overheated` | Watch Only / 僅觀察 | Potential reversal from extended up / 延伸上漲的潛在反轉 |
| `contrarian_watch_oversold` | Watch Only / 僅觀察 | Potential reversal from extended down / 延伸下跌的潛在反轉 |

## Signal Conditions / 訊號條件

### trend_long (Confirmed Signal / 確認訊號)

**All conditions must be met / 必須全部符合：**

| # | Condition / 條件 | Indicator / 指標 | Threshold / 閾值 |
|---|------------------|------------------|------------------|
| C1 | Price above long-term trend / 價格在長期趨勢之上 | close_5m > MA240 | > MA240 |
| C2 | Short-term momentum up / 短期動能向上 | MA5 cross above MA20 | Cross above |
| C3 | Volume confirmation / 成交量確認 | 1m volume > 2x avg(20) | > 2.0x |

### trend_short (Confirmed Signal / 確認訊號)

**All conditions must be met / 必須全部符合：**

| # | Condition / 條件 | Indicator / 指標 | Threshold / 閾值 |
|---|------------------|------------------|------------------|
| C1 | Price below long-term trend / 價格在長期趨勢之下 | close_5m < MA240 | < MA240 |
| C2 | Short-term momentum down / 短期動能向下 | MA5 cross below MA20 | Cross below |
| C3 | Volume confirmation / 成交量確認 | 1m volume > 2x avg(20) | > 2.0x |

### contrarian_watch_overheated (Watch Only / 僅觀察)

**⚠️ NOT an execution signal / 非執行訊號**

| Condition / 條件 | Timeframe / 時間框架 | Pattern / 型態 |
|------------------|----------------------|----------------|
| 4 consecutive red candles / 4 根連續紅 K | 15m | close < open x 4 |

### contrarian_watch_oversold (Watch Only / 僅觀察)

**⚠️ NOT an execution signal / 非執行訊號**

| Condition / 條件 | Timeframe / 時間框架 | Pattern / 型態 |
|------------------|----------------------|----------------|
| 4 consecutive green candles / 4 根連續綠 K | 15m | close > open x 4 |

## Cooldown Configuration / 冷卻設定

| Signal / 訊號 | Cooldown / 冷卻期 |
|---------------|-------------------|
| trend_long | 15 minutes / 15 分鐘 |
| trend_short | 15 minutes / 15 分鐘 |
| contrarian_watch_* | 30 minutes / 30 分鐘 |

## Usage / 使用方法

### Basic Usage / 基本使用

```python
from signals.engine import SignalEngine, SignalType, SignalLevel

# Create engine
engine = SignalEngine()

# Process symbol with pre-fetched data
data_5m = [...]  # From data.fetcher
data_1m = [...]
data_15m = [...]

signals = engine.process_symbol("BTCUSDT", data_5m, data_1m, data_15m)

for signal in signals:
    print(f"{signal.signal_type.value}: {signal.reason}")
```

### Generate Individual Signals / 產生個別訊號

```python
from signals.engine import SignalEngine

engine = SignalEngine()

# Trend long
signal = engine.generate_trend_long_signal(
    symbol="BTCUSDT",
    close_5m=69250.50,
    ma5=[...],
    ma20=[...],
    ma240=[...],
    volume_1m=25.0,
    volumes_1m=[...]
)

if signal:
    print(f"Signal: {signal.signal_type.value}")
    print(f"Level: {signal.level.value}")
    print(f"Reason: {signal.reason}")
```

### Check Cooldown Status / 檢查冷卻狀態

```python
from signals.engine import SignalEngine

engine = SignalEngine()

# After generating signals
status = engine.get_cooldown_status("BTCUSDT")
print(f"Trend long cooldown: {status['trend_long']:.0f}s")
```

## API Reference / API 參考

### SignalEngine Class / SignalEngine 類別

#### `__init__(fetcher=None, cooldown_manager=None)`
Initialize signal engine with optional dependencies.
使用可選的依賴初始化訊號引擎。

#### `generate_trend_long_signal(symbol, close_5m, ma5, ma20, ma240, volume_1m, volumes_1m, timestamp=None) -> Optional[Signal]`
Generate trend_long signal if conditions met.
若條件符合則產生 trend_long 訊號。

#### `generate_trend_short_signal(symbol, close_5m, ma5, ma20, ma240, volume_1m, volumes_1m, timestamp=None) -> Optional[Signal]`
Generate trend_short signal if conditions met.
若條件符合則產生 trend_short 訊號。

#### `generate_contrarian_watch_signal(symbol, candles_15m, timestamp=None) -> Optional[Signal]`
Generate contrarian_watch signal if pattern detected.
若檢測到型態則產生 contrarian_watch 訊號。

#### `process_symbol(symbol, data_5m, data_1m, data_15m) -> List[Signal]`
Process all signals for a symbol.
處理單一標的所有訊號。

#### `get_cooldown_status(symbol) -> Dict[str, float]`
Get cooldown status for symbol.
取得標的的冷卻狀態。

### CooldownManager Class / CooldownManager 類別

#### `__init__(config=None)`
Initialize cooldown manager.
初始化冷卻管理器。

#### `can_emit(symbol, signal_type) -> bool`
Check if signal can be emitted.
檢查訊號是否可以發送。

#### `record_emission(symbol, signal_type)`
Record signal emission time.
記錄訊號發送時間。

#### `get_remaining_cooldown(symbol, signal_type) -> float`
Get remaining cooldown seconds.
取得剩餘冷卻秒數。

### Signal Data Class / Signal 資料類別

```python
@dataclass
class Signal:
    signal_type: SignalType      # TREND_LONG, TREND_SHORT, etc.
    level: SignalLevel           # CONFIRMED, WATCH_ONLY
    symbol: str                  # Trading pair
    timestamp: int               # Unix timestamp (ms)
    price_data: Dict             # Price and indicator values
    conditions: Dict[str, bool]  # Which conditions were met
    reason: str                  # Human-readable reason
    warning: str                 # ALERT_ONLY or WATCH_ONLY warning
```

### Enums / 列舉

#### SignalType
- `TREND_LONG`
- `TREND_SHORT`
- `CONTRARIAN_WATCH_OVERHEATED`
- `CONTRARIAN_WATCH_OVERSOLD`

#### SignalLevel
- `CONFIRMED` - For trend signals
- `WATCH_ONLY` - For contrarian signals

## Signal Output Format / 訊號輸出格式

### Trend Signal Example / 趨勢訊號範例

```json
{
  "signal_type": "trend_long",
  "level": "confirmed",
  "symbol": "BTCUSDT",
  "timestamp": 1775385000000,
  "price_data": {
    "close_5m": 69250.50,
    "ma5": 69180.25,
    "ma20": 69050.00,
    "ma240": 68500.75,
    "volume_1m": 12.5,
    "volume_avg_1m": 5.2,
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
```

### Contrarian Signal Example / 逆勢訊號範例

```json
{
  "signal_type": "contrarian_watch_overheated",
  "level": "watch_only",
  "symbol": "ETHUSDT",
  "timestamp": 1775385900000,
  "price_data": {
    "timeframe": "15m",
    "pattern": "overheated",
    "consecutive_count": 4
  },
  "conditions": {
    "pattern_detected": true
  },
  "reason": "ETHUSDT 15m: 4 consecutive overheated candles - potential reversal zone",
  "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
}
```

## Important Warnings / 重要警告

### ⚠️ ALERT ONLY SYSTEM / 僅提醒系統

```
╔══════════════════════════════════════════════════════════════════╗
║  THIS MODULE GENERATES ALERTS ONLY                               ║
║  本模組僅產生提醒                                                 ║
║                                                                  ║
║  • NO automatic trading / 不自動交易                              ║
║  • NO order execution / 不執行訂單                                ║
║  • NO position management / 不管理部位                            ║
║                                                                  ║
║  All signals require human review and decision.                  ║
║  所有訊號都需要人工審查與決策。                                     ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ CONTRARIAN_WATCH IS NOT EXECUTION / 逆勢觀察非執行

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
| `data.fetcher` | Data Layer | Kline data fetching / K 線資料抓取 |
| `indicators.calculator` | Indicator Layer | Technical indicators / 技術指標 |

## What's NOT Included / 不包含的功能

This module is intentionally limited (Signal Layer only):
本模組刻意限制（僅訊號層）：

- ❌ No notification sending / 無通知發送
- ❌ No alert formatting / 無提醒格式化
- ❌ No automatic trading / 無自動交易

These are handled by other layers:
這些由其他層級處理：
- Notification Layer / 通知層 (`notifications/`)

## Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-06 | Initial implementation / 初始實作 |

## References / 參考

- `workflows/btc_eth_monitoring_system.md` - Phase 3 Signal Engine Design
- `workflows/btc_eth_monitoring_signal_spec.md` - Signal specifications
- `data/fetcher.py` - Data Layer / 資料層
- `indicators/calculator.py` - Indicator Layer / 指標層
