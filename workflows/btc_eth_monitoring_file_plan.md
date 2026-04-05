# BTC/ETH Monitoring File Plan
# BTC/ETH 監測檔案計畫

**Version**: 1.0.0  
**版本**: 1.0.0  
**Document ID**: FILEPLAN-001  
**文件識別碼**: FILEPLAN-001  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. File Structure Overview / 檔案結構總覽

```
monitoring_system/
├── config/                      # Configuration / 設定
│   ├── __init__.py
│   ├── settings.py              # System settings / 系統設定
│   └── symbols.py               # Symbol definitions / 標的定義
│
├── data/                        # Data Layer / 資料層
│   ├── __init__.py
│   ├── fetcher.py               # API data fetching / API 資料抓取
│   └── cache.py                 # Data caching / 資料快取
│
├── indicators/                  # Indicator Layer / 指標層
│   ├── __init__.py
│   ├── moving_average.py        # MA calculations / MA 計算
│   ├── volume.py                # Volume metrics / 成交量指標
│   └── candle_patterns.py       # Pattern detection / 型態檢測
│
├── signals/                     # Signal Layer / 訊號層
│   ├── __init__.py
│   ├── engine.py                # Signal generation / 訊號產生
│   ├── conditions.py            # Condition checks / 條件檢查
│   └── cooldown.py              # Cooldown management / 冷卻管理
│
├── notifications/               # Notification Layer / 通知層
│   ├── __init__.py
│   ├── formatter.py             # Message formatting / 訊息格式化
│   ├── dispatcher.py            # Alert dispatching / 提醒發送
│   └── templates/               # Message templates / 訊息模板
│       ├── trend_long.txt
│       ├── trend_short.txt
│       └── contrarian_watch.txt
│
├── core/                        # Core Layer / 核心層
│   ├── __init__.py
│   ├── scheduler.py             # Polling scheduler / 輪詢排程器
│   ├── validator.py             # Input validation / 輸入驗證
│   └── logger.py                # System logging / 系統記錄
│
├── tests/                       # Tests / 測試
│   ├── __init__.py
│   ├── test_data.py
│   ├── test_indicators.py
│   ├── test_signals.py
│   └── test_notifications.py
│
├── workflows/                   # Documentation / 文件
│   ├── btc_eth_monitoring_system.md
│   ├── btc_eth_monitoring_signal_spec.md
│   └── btc_eth_monitoring_file_plan.md
│
├── main.py                      # Entry point / 進入點
├── requirements.txt             # Dependencies / 依賴
└── README.md                    # Setup guide / 設定指南
```

---

## 2. Module Responsibilities / 模組職責

### 2.1 Data Layer / 資料層

| Module / 模組 | File / 檔案 | Responsibility / 職責 |
|---------------|-------------|----------------------|
| Fetcher / 抓取器 | `data/fetcher.py` | Fetch klines from Binance API / 從 Binance API 抓取 K 線 |
| Cache / 快取 | `data/cache.py` | Cache recent data to reduce API calls / 快取近期資料以減少 API 呼叫 |

### 2.2 Indicator Layer / 指標層

| Module / 模組 | File / 檔案 | Responsibility / 職責 |
|---------------|-------------|----------------------|
| Moving Average / 移動平均 | `indicators/moving_average.py` | Calculate SMA (5, 20, 240) / 計算 SMA |
| Volume / 成交量 | `indicators/volume.py` | Calculate volume averages / 計算成交量平均 |
| Candle Patterns / K線型態 | `indicators/candle_patterns.py` | Detect consecutive candle patterns / 檢測連續 K 線型態 |

### 2.3 Signal Layer / 訊號層

| Module / 模組 | File / 檔案 | Responsibility / 職責 |
|---------------|-------------|----------------------|
| Conditions / 條件 | `signals/conditions.py` | Check signal conditions / 檢查訊號條件 |
| Cooldown / 冷卻 | `signals/cooldown.py` | Manage signal cooldown state / 管理訊號冷卻狀態 |
| Engine / 引擎 | `signals/engine.py` | Generate signals from conditions / 從條件產生訊號 |

### 2.4 Notification Layer / 通知層

| Module / 模組 | File / 檔案 | Responsibility / 職責 |
|---------------|-------------|----------------------|
| Formatter / 格式化器 | `notifications/formatter.py` | Format alert messages / 格式化提醒訊息 |
| Dispatcher / 發送器 | `notifications/dispatcher.py` | Send alerts to channels / 發送提醒到渠道 |
| Templates / 模板 | `notifications/templates/*.txt` | Message templates / 訊息模板 |

### 2.5 Core Layer / 核心層

| Module / 模組 | File / 檔案 | Responsibility / 職責 |
|---------------|-------------|----------------------|
| Scheduler / 排程器 | `core/scheduler.py` | Schedule data polling / 排程資料輪詢 |
| Validator / 驗證器 | `core/validator.py` | Validate input data / 驗證輸入資料 |
| Logger / 記錄器 | `core/logger.py` | System event logging / 系統事件記錄 |

---

## 3. Implementation Phases / 實作階段

### Phase A: Foundation (Week 1) / 基礎 (第1週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Deliverable / 交付 |
|-------------|---------------|-------------|--------------------|
| A1 | config | Create settings.py | Configuration class / 設定類別 |
| A2 | config | Create symbols.py | Symbol definitions / 標的定義 |
| A3 | data | Implement fetcher.py | Binance API client / Binance API 客戶端 |
| A4 | data | Implement cache.py | In-memory cache / 記憶體快取 |
| A5 | core | Setup logger.py | Logging infrastructure / 記錄基礎設施 |

### Phase B: Indicators (Week 1-2) / 指標 (第1-2週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Deliverable / 交付 |
|-------------|---------------|-------------|--------------------|
| B1 | indicators | Implement moving_average.py | SMA calculation / SMA 計算 |
| B2 | indicators | Implement volume.py | Volume metrics / 成交量指標 |
| B3 | indicators | Implement candle_patterns.py | Pattern detection / 型態檢測 |
| B4 | tests | Create test_indicators.py | Unit tests / 單元測試 |

### Phase C: Signal Engine (Week 2) / 訊號引擎 (第2週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Deliverable / 交付 |
|-------------|---------------|-------------|--------------------|
| C1 | signals | Implement conditions.py | Condition checks / 條件檢查 |
| C2 | signals | Implement cooldown.py | Cooldown manager / 冷卻管理器 |
| C3 | signals | Implement engine.py | Signal generation / 訊號產生 |
| C4 | tests | Create test_signals.py | Unit tests / 單元測試 |

### Phase D: Notifications (Week 2-3) / 通知 (第2-3週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Deliverable / 交付 |
|-------------|---------------|-------------|--------------------|
| D1 | notifications | Create templates/ | Message templates / 訊息模板 |
| D2 | notifications | Implement formatter.py | Message formatter / 訊息格式化器 |
| D3 | notifications | Implement dispatcher.py | Console dispatcher / 控制台發送器 |
| D4 | tests | Create test_notifications.py | Unit tests / 單元測試 |

### Phase E: Integration (Week 3) / 整合 (第3週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Deliverable / 交付 |
|-------------|---------------|-------------|--------------------|
| E1 | core | Implement scheduler.py | Polling scheduler / 輪詢排程器 |
| E2 | root | Create main.py | Entry point / 進入點 |
| E3 | tests | Integration testing | System tests / 系統測試 |
| E4 | root | Create README.md | Setup guide / 設定指南 |

### Phase F: Deployment Prep (Week 4) / 部署準備 (第4週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Deliverable / 交付 |
|-------------|---------------|-------------|--------------------|
| F1 | notifications | Add Discord webhook | Discord dispatcher / Discord 發送器 |
| F2 | core | Add error handling | Retry and recovery / 重試與恢復 |
| F3 | all | Performance optimization | Optimized code / 優化程式碼 |
| F4 | tests | Final testing | Validated system / 驗證系統 |

---

## 4. File Specifications / 檔案規格

### 4.1 Core Files / 核心檔案

#### main.py

```python
#!/usr/bin/env python3
"""
BTC/ETH Monitoring System - Entry Point
BTC/ETH 監測系統 - 進入點

Alert-only monitoring system for BTCUSDT and ETHUSDT.
僅提醒的監測系統，用於 BTCUSDT 和 ETHUSDT。
"""

from core.scheduler import Scheduler
from core.logger import setup_logger

def main():
    logger = setup_logger()
    logger.info("Starting BTC/ETH Monitoring System...")
    
    scheduler = Scheduler()
    scheduler.start()

if __name__ == "__main__":
    main()
```

#### requirements.txt

```
requests>=2.28.0
python-dateutil>=2.8.0
```

### 4.2 Config Files / 設定檔案

#### config/settings.py

```python
"""
System settings / 系統設定
"""

# API Settings / API 設定
BINANCE_BASE_URL = "https://api.binance.com"
BINANCE_KLINES_ENDPOINT = "/api/v3/klines"
RATE_LIMIT_PER_MINUTE = 1200

# Timeframe Settings / 時間框架設定
TIMEFRAMES = {
    "5m": {"interval": "5m", "candles_needed": 250},
    "1m": {"interval": "1m", "candles_needed": 25},
    "15m": {"interval": "15m", "candles_needed": 10}
}

# Indicator Settings / 指標設定
MA_PERIODS = {
    "ma5": 5,
    "ma20": 20,
    "ma240": 240
}

VOLUME_AVG_PERIOD = 20
VOLUME_SPIKE_THRESHOLD = 2.0

# Signal Settings / 訊號設定
COOLDOWN_PERIODS = {
    "trend_long": 15 * 60,        # 15 minutes / 15分鐘
    "trend_short": 15 * 60,       # 15 minutes / 15分鐘
    "contrarian_watch": 30 * 60   # 30 minutes / 30分鐘
}

# Notification Settings / 通知設定
ALERT_LEVELS = {
    "confirmed": ["trend_long", "trend_short"],
    "watch_only": ["contrarian_watch"]
}
```

#### config/symbols.py

```python
"""
Symbol definitions / 標的定義
"""

MONITORED_SYMBOLS = [
    {
        "symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "timeframes": ["1m", "5m", "15m"],
        "active": True
    },
    {
        "symbol": "ETHUSDT",
        "base_asset": "ETH",
        "quote_asset": "USDT",
        "timeframes": ["1m", "5m", "15m"],
        "active": True
    }
]
```

### 4.3 Data Layer Files / 資料層檔案

#### data/fetcher.py

```python
"""
Binance API data fetcher / Binance API 資料抓取器
"""

import requests
import time
from typing import List, Dict, Optional

class BinanceFetcher:
    def __init__(self, base_url: str = "https://api.binance.com"):
        self.base_url = base_url
        self.rate_limit_remaining = 1200
        
    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500
    ) -> Optional[List[List]]:
        """
        Fetch kline/candlestick data / 抓取 K 線資料
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Kline interval (e.g., 5m)
            limit: Number of candles to fetch
            
        Returns:
            List of klines or None if error
        """
        endpoint = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching klines: {e}")
            return None
```

#### data/cache.py

```python
"""
Data cache / 資料快取
"""

from typing import Dict, List, Optional
from collections import deque
import time

class DataCache:
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, deque] = {}
        self.timestamps: Dict[str, float] = {}
        self.max_size = max_size
        
    def get(self, key: str) -> Optional[List]:
        """Get cached data / 取得快取資料"""
        if key in self.cache:
            return list(self.cache[key])
        return None
        
    def set(self, key: str, data: List):
        """Set cached data / 設定快取資料"""
        self.cache[key] = deque(data, maxlen=self.max_size)
        self.timestamps[key] = time.time()
        
    def is_fresh(self, key: str, max_age_seconds: int = 60) -> bool:
        """Check if cached data is fresh / 檢查快取資料是否新鮮"""
        if key not in self.timestamps:
            return False
        age = time.time() - self.timestamps[key]
        return age < max_age_seconds
```

### 4.4 Indicator Layer Files / 指標層檔案

#### indicators/moving_average.py

```python
"""
Moving average calculations / 移動平均計算
"""

from typing import List

def calculate_sma(data: List[float], period: int) -> List[float]:
    """
    Calculate Simple Moving Average / 計算簡單移動平均
    
    Args:
        data: List of closing prices / 收盤價列表
        period: MA period / MA 週期
        
    Returns:
        List of SMA values / SMA 值列表
    """
    if len(data) < period:
        return []
        
    sma = []
    for i in range(period - 1, len(data)):
        window = data[i - period + 1:i + 1]
        sma.append(sum(window) / period)
    return sma

def detect_cross_above(ma_short: List[float], ma_long: List[float]) -> bool:
    """
    Detect if short MA crossed above long MA / 檢測短期 MA 是否上穿長期 MA
    """
    if len(ma_short) < 2 or len(ma_long) < 2:
        return False
        
    prev_short = ma_short[-2]
    prev_long = ma_long[-2]
    curr_short = ma_short[-1]
    curr_long = ma_long[-1]
    
    return prev_short < prev_long and curr_short >= curr_long

def detect_cross_below(ma_short: List[float], ma_long: List[float]) -> bool:
    """
    Detect if short MA crossed below long MA / 檢測短期 MA 是否下穿長期 MA
    """
    if len(ma_short) < 2 or len(ma_long) < 2:
        return False
        
    prev_short = ma_short[-2]
    prev_long = ma_long[-2]
    curr_short = ma_short[-1]
    curr_long = ma_long[-1]
    
    return prev_short > prev_long and curr_short <= curr_long
```

#### indicators/volume.py

```python
"""
Volume indicators / 成交量指標
"""

from typing import List

def calculate_volume_sma(volumes: List[float], period: int = 20) -> float:
    """
    Calculate volume SMA / 計算成交量 SMA
    
    Args:
        volumes: List of volume values / 成交量值列表
        period: SMA period / SMA 週期
        
    Returns:
        Volume SMA value / 成交量 SMA 值
    """
    if len(volumes) < period:
        return 0.0
        
    recent_volumes = volumes[-period:]
    return sum(recent_volumes) / period

def detect_volume_spike(
    current_volume: float,
    avg_volume: float,
    threshold: float = 2.0
) -> bool:
    """
    Detect if current volume is above threshold / 檢測當前成交量是否高於閾值
    
    Args:
        current_volume: Current period volume / 當前期間成交量
        avg_volume: Average volume / 平均成交量
        threshold: Multiplier threshold / 倍數閾值
        
    Returns:
        True if volume spike detected / 若檢測到成交量爆增則為 True
    """
    if avg_volume == 0:
        return False
    return current_volume > (avg_volume * threshold)
```

#### indicators/candle_patterns.py

```python
"""
Candle pattern detection / K 線型態檢測
"""

from typing import List, Dict, Tuple

def is_red_candle(open_price: float, close_price: float) -> bool:
    """Check if candle is red (close < open) / 檢查是否為紅 K"""
    return close_price < open_price

def is_green_candle(open_price: float, close_price: float) -> bool:
    """Check if candle is green (close > open) / 檢查是否為綠 K"""
    return close_price > open_price

def detect_consecutive_candles(
    candles: List[Dict],
    n: int = 4,
    candle_type: str = "red"
) -> bool:
    """
    Detect N consecutive candles of same type / 檢測 N 根連續同色 K 線
    
    Args:
        candles: List of candle data with 'open' and 'close' / K 線資料列表
        n: Number of consecutive candles / 連續 K 線數量
        candle_type: 'red' or 'green' / 'red' 或 'green'
        
    Returns:
        True if pattern detected / 若檢測到型態則為 True
    """
    if len(candles) < n:
        return False
        
    recent_candles = candles[-n:]
    
    for candle in recent_candles:
        open_p = float(candle['open'])
        close_p = float(candle['close'])
        
        if candle_type == "red":
            if not is_red_candle(open_p, close_p):
                return False
        elif candle_type == "green":
            if not is_green_candle(open_p, close_p):
                return False
                
    return True

def detect_consecutive_red(candles: List[Dict], n: int = 4) -> bool:
    """Detect N consecutive red candles / 檢測 N 根連續紅 K"""
    return detect_consecutive_candles(candles, n, "red")

def detect_consecutive_green(candles: List[Dict], n: int = 4) -> bool:
    """Detect N consecutive green candles / 檢測 N 根連續綠 K"""
    return detect_consecutive_candles(candles, n, "green")
```

---

## 5. Implementation Order / 實作順序

### Week 1: Foundation + Indicators / 第1週：基礎 + 指標

```
Day 1-2: Config + Data Layer
├── config/settings.py
├── config/symbols.py
├── data/fetcher.py
└── data/cache.py

Day 3-5: Indicator Layer
├── indicators/moving_average.py
├── indicators/volume.py
├── indicators/candle_patterns.py
└── tests/test_indicators.py
```

### Week 2: Signals + Notifications / 第2週：訊號 + 通知

```
Day 1-3: Signal Layer
├── signals/conditions.py
├── signals/cooldown.py
├── signals/engine.py
└── tests/test_signals.py

Day 4-5: Notification Layer
├── notifications/templates/
├── notifications/formatter.py
├── notifications/dispatcher.py
└── tests/test_notifications.py
```

### Week 3: Integration / 第3週：整合

```
Day 1-3: Core + Main
├── core/scheduler.py
├── core/validator.py
├── core/logger.py
└── main.py

Day 4-5: Testing + Documentation
├── Integration tests
├── README.md
└── Bug fixes
```

### Week 4: Deployment Prep / 第4週：部署準備

```
Day 1-2: Discord Integration
├── notifications/discord_dispatcher.py
└── Webhook configuration

Day 3-4: Optimization
├── Performance improvements
├── Error handling
└── Logging enhancement

Day 5: Final Testing
├── End-to-end tests
├── Documentation review
└── Release preparation
```

---

## 6. MVP Scope / MVP 範圍

### Included in MVP / MVP 包含

| Feature / 功能 | Scope / 範圍 |
|----------------|--------------|
| Data source / 資料來源 | Binance Spot API only / 僅 Binance 現貨 API |
| Symbols / 標的 | BTCUSDT, ETHUSDT only / 僅 BTCUSDT, ETHUSDT |
| Timeframes / 時間框架 | 1m, 5m, 15m / 1分鐘, 5分鐘, 15分鐘 |
| Indicators / 指標 | MA(5,20,240), Volume SMA(20) / MA, 成交量 SMA |
| Signals / 訊號 | trend_long, trend_short, contrarian_watch |
| Notifications / 通知 | Console output only / 僅控制台輸出 |
| Cooldown / 冷卻 | Fixed periods / 固定週期 |
| Tests / 測試 | Unit tests for indicators, signals / 指標與訊號單元測試 |

### Not in MVP (Future) / 不在 MVP (未來)

| Feature / 功能 | Planned Phase / 計畫階段 |
|----------------|--------------------------|
| Discord webhook | Phase F |
| Multiple exchanges / 多交易所 | Post-MVP |
| Configurable symbols / 可設定標的 | Post-MVP |
| Backtesting / 回測 | Post-MVP |
| Database storage / 資料庫儲存 | Post-MVP |
| Web dashboard / 網頁儀表板 | Post-MVP |

---

## 7. Testing Strategy / 測試策略

### 7.1 Unit Tests / 單元測試

| Test File / 測試檔案 | Coverage / 涵蓋範圍 |
|----------------------|---------------------|
| test_indicators.py | MA calculation, volume, patterns |
| test_signals.py | Condition checks, cooldown, engine |
| test_notifications.py | Formatter, dispatcher |
| test_data.py | Fetcher, cache |

### 7.2 Integration Tests / 整合測試

| Test Scenario / 測試情境 | Description / 說明 |
|--------------------------|--------------------|
| End-to-end signal flow / 端到端訊號流程 | Data → Indicators → Signals → Notifications |
| Cooldown enforcement / 冷卻執行 | Verify no duplicate signals / 驗證無重複訊號 |
| Error recovery / 錯誤恢復 | API failure handling / API 失敗處理 |
| Rate limiting / 速率限制 | Respect Binance limits / 遵守 Binance 限制 |

---

## 8. Dependencies / 依賴

### Python Packages / Python 套件

```
requests>=2.28.0          # HTTP client / HTTP 客戶端
python-dateutil>=2.8.0   # Date/time utilities / 日期時間工具
```

### Development Dependencies / 開發依賴

```
pytest>=7.0.0            # Testing framework / 測試框架
pytest-cov>=3.0.0        # Coverage / 涵蓋率
black>=22.0.0            # Code formatting / 程式碼格式化
flake8>=4.0.0            # Linting / 靜態檢查
```

---

## 9. Configuration / 設定

### Environment Variables / 環境變數

| Variable / 變數 | Default / 預設 | Description / 說明 |
|-----------------|----------------|--------------------|
| `BINANCE_API_KEY` | None | API key (if needed) / API 金鑰 |
| `LOG_LEVEL` | INFO | Logging level / 記錄層級 |
| `COOLDOWN_TREND` | 900 | Trend signal cooldown (sec) / 趨勢訊號冷卻 |
| `COOLDOWN_CONTRARIAN` | 1800 | Contrarian cooldown (sec) / 逆勢冷卻 |

---

## 10. Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-05 | Initial file plan / 初始檔案計畫 |

---

**Created by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Part of**: T-022 BTC/ETH Monitoring System  
**Date**: 2026-04-05  
**日期**: 2026-04-05
