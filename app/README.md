# Application Layer / 應用層

BTC/ETH Monitoring System - Application Layer
BTC/ETH 監測系統 - 應用層

## Overview / 概覽

This directory contains the application layer that connects all monitoring system layers.
Provides the single-run entry point for BTC/ETH monitoring.

本目錄包含連接所有監測系統層級的應用層。
提供 BTC/ETH 監測的單次執行入口。

## Files / 檔案

| File / 檔案 | Description / 說明 |
|-------------|--------------------|
| `monitor_runner.py` | Main monitoring runner / 主要監測執行器 |
| `example_run_output.md` | Example output format / 範例輸出格式 |
| `README.md` | This file / 本檔案 |

## Architecture / 架構

```
┌─────────────────────────────────────────────────────────┐
│  Application Layer (app/monitor_runner.py)              │
│  應用層                                                  │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │   Data      │→│  Indicator  │→│     Signal      │ │
│  │  fetcher    │  │ calculator  │  │     engine      │ │
│  └─────────────┘  └─────────────┘  └─────────────────┘ │
│         ↓                                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │         Notification (formatter + notifier)     │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## monitor_runner.py

### Purpose / 用途

Provides a single-run monitoring execution for BTCUSDT and ETHUSDT.
連接資料 → 指標 → 訊號 → 通知四層，完成單次監測。

### Features / 功能

- **Single-run execution / 單次執行**: Not a daemon, runs once and exits
- **Multi-symbol support / 多標的支援**: BTCUSDT, ETHUSDT
- **Multi-timeframe / 多時間框架**: 1m, 5m, 15m
- **Layer integration / 層級整合**: Connects all 4 layers
- **Alert-only output / 僅提醒輸出**: No automatic trading

### Usage / 使用方法

#### Basic Usage / 基本使用

```python
from app.monitor_runner import MonitorRunner

# Create runner
runner = MonitorRunner()

# Run monitoring
results, summary = runner.run_monitor_once()

# Access results
for result in results:
    print(f"{result.symbol}: {len(result.signals)} signals")
```

#### Standalone Functions / 獨立函式

```python
from app.monitor_runner import build_run_summary, preview_run_output

# Build summary from results
summary = build_run_summary(results)

# Generate preview
preview = preview_run_output(results)
print(preview)
```

### Main Functions / 主要函式

#### `MonitorRunner.run_for_symbol(symbol)`

Run monitoring for a single symbol.
執行單一標的監測。

```python
runner = MonitorRunner()
result = runner.run_for_symbol("BTCUSDT")

print(f"Success: {result.success}")
print(f"Signals: {len(result.signals)}")
print(f"Confirmed: {len(result.confirmed_signals)}")
print(f"Watch Only: {len(result.watch_only_signals)}")
```

#### `MonitorRunner.run_monitor_once()`

Run monitoring for all configured symbols.
執行所有配置標的的監測。

```python
results, summary = runner.run_monitor_once()

print(f"Total symbols: {summary.total_symbols}")
print(f"Total signals: {summary.total_signals}")
print(f"Confirmed: {summary.confirmed_count}")
print(f"Watch Only: {summary.watch_only_count}")
```

#### `build_run_summary(results)`

Build summary from list of SymbolResult.
從 SymbolResult 列表建立摘要。

#### `preview_run_output(results)`

Generate formatted preview of run output.
產生格式化的執行輸出預覽。

### Execution Flow / 執行流程

```
run_monitor_once()
    ↓
for each symbol in [BTCUSDT, ETHUSDT]:
    ↓
    run_for_symbol(symbol)
        ↓
        [1/4] Fetch Data (1m, 5m, 15m)
        [2/4] Calculate Indicators (MA5, MA20, MA240, Volume)
        [3/4] Generate Signals (trend_long, trend_short, contrarian_watch)
        [4/4] Output Notifications
    ↓
_build_run_summary(results)
_output_summary(summary)
```

### Configuration / 設定

```python
MONITOR_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = {
    "5m": {"limit": 250, "description": "Primary trend analysis"},
    "1m": {"limit": 20, "description": "Volume analysis"},
    "15m": {"limit": 10, "description": "Contrarian pattern analysis"}
}
```

## Data Classes / 資料類別

### SymbolResult

Result for a single symbol monitoring run.
單一標的監測執行結果。

```python
@dataclass
class SymbolResult:
    symbol: str                    # Trading pair / 交易對
    timestamp: int                 # Run timestamp / 執行時間戳
    success: bool                  # Success flag / 成功標誌
    error: Optional[str]           # Error message / 錯誤訊息
    
    # Data / 資料
    data_5m: List[KlineData]
    data_1m: List[KlineData]
    data_15m: List[KlineData]
    
    # Indicators / 指標
    ma5: Optional[float]
    ma20: Optional[float]
    ma240: Optional[float]
    volume_avg: Optional[float]
    volume_ratio: Optional[float]
    
    # Signals / 訊號
    signals: List[Signal]
    confirmed_signals: List[Signal]
    watch_only_signals: List[Signal]
```

### RunSummary

Summary of a complete monitoring run.
完整監測執行的摘要。

```python
@dataclass
class RunSummary:
    timestamp: int                 # Run timestamp / 執行時間戳
    total_symbols: int             # Total symbols / 總標的數
    successful_symbols: int        # Successful / 成功數
    failed_symbols: int            # Failed / 失敗數
    total_signals: int             # Total signals / 總訊號數
    confirmed_count: int           # Confirmed signals / 確認訊號數
    watch_only_count: int          # Watch only signals / 僅觀察訊號數
    symbols_with_signals: List[str]  # Symbols with signals / 有訊號的標的
    errors: List[str]              # Error messages / 錯誤訊息
```

## Important Warnings / 重要警告

### ⚠️ SINGLE-RUN ONLY / 僅單次執行

```
╔══════════════════════════════════════════════════════════════════╗
║  THIS IS A SINGLE-RUN EXECUTION                                  ║
║  這是單次執行                                                     ║
║                                                                  ║
║  • Not a daemon / 不是常駐服務                                    ║
║  • Runs once and exits / 執行一次後退出                           ║
║  • No automatic scheduling / 無自動排程                           ║
║  • No infinite loops / 無無限循環                                 ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ ALERT ONLY / 僅提醒

```
╔══════════════════════════════════════════════════════════════════╗
║  ALERT ONLY - NO AUTO TRADING                                    ║
║  僅提醒 - 無自動交易                                               ║
║                                                                  ║
║  • Generates alerts only / 僅產生提醒                              ║
║  • No order execution / 不執行訂單                                 ║
║  • No position management / 不管理部位                             ║
║  • Human decision required / 需要人工決策                          ║
╚══════════════════════════════════════════════════════════════════╝
```

## Dependencies / 依賴

| Module / 模組 | Layer / 層級 | Purpose / 用途 |
|---------------|--------------|----------------|
| `data.fetcher` | Data Layer | Kline data fetching / K 線資料抓取 |
| `indicators.calculator` | Indicator Layer | Technical indicators / 技術指標 |
| `signals.engine` | Signal Layer | Signal generation / 訊號產生 |
| `notifications.notifier` | Notification Layer | Alert output / 提醒輸出 |

## What's NOT Included / 不包含的功能

This module is intentionally limited:
本模組刻意限制：

- ❌ No automatic trading / 無自動交易
- ❌ No order execution / 無訂單執行
- ❌ No daemon mode / 無常駐模式
- ❌ No scheduler / 無排程器
- ❌ No cron integration / 無 cron 整合
- ❌ No external API trading / 無外部 API 交易

## Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-06 | Initial implementation / 初始實作 |

## References / 參考

- `workflows/btc_eth_monitoring_system.md` - System design
- `workflows/btc_eth_monitoring_file_plan.md` - Implementation plan
- `data/fetcher.py` - Data Layer / 資料層
- `indicators/calculator.py` - Indicator Layer / 指標層
- `signals/engine.py` - Signal Layer / 訊號層
- `notifications/notifier.py` - Notification Layer / 通知層
