# BTC/ETH Monitoring System Design
# BTC/ETH 監測系統設計

**Version**: 0.1.0  
**版本**: 0.1.0  
**System ID**: MONITOR-001  
**系統識別碼**: MONITOR-001  
**Date**: 2026-04-05  
**日期**: 2026-04-05

**Status**: Design Phase / 設計階段  
**Type**: Alert-only (NO auto-trading) / 僅提醒（無自動交易）

---

## Executive Summary / 執行摘要

This document defines a monitoring system for BTCUSDT and ETHUSDT that generates alerts based on technical indicators. **This system is for observation and alerts only - it does NOT execute trades automatically.**

本文件定義 BTCUSDT 與 ETHUSDT 的監測系統，基於技術指標產生提醒。**本系統僅供觀察與提醒，不自動執行交易。**

---

## Phase 1: Data Fetch Design / Phase 1: 資料抓取設計

**Status**: ✅ Completed / 完成

### 1.1 Data Sources / 資料來源

| Parameter / 參數 | Value / 值 | Status / 狀態 |
|------------------|------------|---------------|
| Primary Source / 主要來源 | Binance Spot API | ⚠️ To be configured |
| Endpoint / 端點 | `GET /api/v3/klines` | ⚠️ To be configured |
| Rate Limit / 速率限制 | 1200 req/min | ⚠️ To be monitored |
| Backup Source / 備援來源 | To be defined | 📝 Placeholder |

### 1.2 Required Kline Data / 所需 K 線資料

| Timeframe / 時間框架 | Primary Use / 主要用途 | Candles Needed / 所需 K 線 | Status / 狀態 |
|----------------------|------------------------|---------------------------|---------------|
| 1m (1 minute) | Volume confirmation / 量能確認 | 25 (20 for avg + 5 buffer) | ⚠️ Required |
| 5m (5 minutes) | Main signal generation / 主訊號產生 | 250 (240 MA + 10 buffer) | ⚠️ Required |
| 15m (15 minutes) | Contrarian observation / 逆勢觀察 | 10 (4+6 buffer) | ⚠️ Required |

### 1.3 Data Schema / 資料欄位

```json
{
  "kline_schema": {
    "timestamp": "integer (ms)",
    "open": "string (decimal)",
    "high": "string (decimal)",
    "low": "string (decimal)",
    "close": "string (decimal)",
    "volume": "string (decimal)",
    "close_time": "integer (ms)",
    "quote_volume": "string (decimal)",
    "trades": "integer",
    "taker_buy_base": "string",
    "taker_buy_quote": "string"
  }
}
```

| Field / 欄位 | Type / 類型 | Required / 必要 | Description / 說明 |
|--------------|-------------|-----------------|--------------------|
| timestamp | integer | ✅ Yes | Kline open time (ms) / K線開盤時間 |
| open | string | ✅ Yes | Opening price / 開盤價 |
| high | string | ✅ Yes | Highest price / 最高價 |
| low | string | ✅ Yes | Lowest price / 最低價 |
| close | string | ✅ Yes | Closing price / 收盤價 |
| volume | string | ✅ Yes | Base asset volume / 基礎資產成交量 |
| close_time | integer | ⚠️ Optional | Kline close time / K線收盤時間 |

### 1.4 Symbol List / 標的清單

| Symbol / 標的 | Asset / 資產 | Status / 狀態 |
|---------------|--------------|---------------|
| BTCUSDT | Bitcoin / 比特幣 | ✅ Active |
| ETHUSDT | Ethereum / 以太幣 | ✅ Active |

### 1.5 Timeframe Mapping / 時間框架對應

| Internal Name / 內部名稱 | Binance Interval / Binance 間隔 | Seconds / 秒數 | Use Case / 用途 |
|--------------------------|----------------------------------|----------------|-----------------|
| `1m` | `1m` | 60 | Volume confirmation |
| `5m` | `5m` | 300 | Primary signals |
| `15m` | `15m` | 900 | Contrarian observation |

### 1.6 Polling / Refresh Logic / 輪詢/更新邏輯

```
Polling Strategy / 輪詢策略:
├── 5m candles: Fetch every 5 minutes at :00, :05, :10... / 每5分鐘
├── 1m candles: Fetch every minute for volume check / 每分鐘
└── 15m candles: Fetch every 15 minutes / 每15分鐘

Rate Limit Consideration / 速率限制考量:
- Max 1200 req/min
- Current: ~15 req/min (3 symbols × 5 timeframes with overlap)
- Buffer: Safe margin maintained
```

| Data Type / 資料類型 | Fetch Frequency / 抓取頻率 | Timing / 時機 | Status / 狀態 |
|----------------------|---------------------------|---------------|---------------|
| 5m primary / 5m 主要 | Every 5 min / 每5分鐘 | At minute :00, :05... | ⚠️ To be implemented |
| 1m volume / 1m 成交量 | Every 1 min / 每分鐘 | At minute :00, :01... | ⚠️ To be implemented |
| 15m contrarian / 15m 逆勢 | Every 15 min / 每15分鐘 | At :00, :15, :30, :45 | ⚠️ To be implemented |

### 1.7 Phase 1 Artifacts / Phase 1 產出

| Artifact / 產出 | Status / 狀態 |
|-----------------|---------------|
| Data requirements defined / 資料需求已定義 | ✅ Complete |
| Symbol list confirmed / 標的清單已確認 | ✅ Complete |
| Timeframe mapping / 時間框架對應 | ✅ Complete |
| Polling logic draft / 輪詢邏輯草稿 | ✅ Complete |
| API endpoint identified / API 端點已識別 | ⚠️ Identified, not connected |

---

## Phase 2: Indicator Definition / Phase 2: 指標定義

**Status**: ✅ Completed / 完成

### 2.1 Moving Average Definitions / 移動平均定義

#### 5m MA5 (5-minute 5-period MA)

```python
# Formula / 公式
MA5 = SUM(close[0:5]) / 5

# Where / 其中:
# - close[0] = current 5m close / 當前5分鐘收盤價
# - close[1:5] = previous 4 closes / 前4根收盤價
```

| Parameter / 參數 | Value / 值 |
|------------------|------------|
| Timeframe / 時間框架 | 5m |
| Period / 週期 | 5 |
| Type / 類型 | Simple Moving Average (SMA) |
| Update frequency / 更新頻率 | Every 5 minutes |

#### 5m MA20 (5-minute 20-period MA)

```python
# Formula / 公式
MA20 = SUM(close[0:20]) / 20
```

| Parameter / 參數 | Value / 值 |
|------------------|------------|
| Timeframe / 時間框架 | 5m |
| Period / 週期 | 20 |
| Type / 類型 | Simple Moving Average (SMA) |

#### 5m MA240 (5-minute 240-period MA)

```python
# Formula / 公式
MA240 = SUM(close[0:240]) / 240
```

| Parameter / 參數 | Value / 值 |
|------------------|------------|
| Timeframe / 時間框架 | 5m |
| Period / 週期 | 240 |
| Type / 類型 | Simple Moving Average (SMA) |
| Notes / 備註 | ~20 hours of data / 約20小時資料 |

### 2.2 Volume Average Definition / 成交量平均定義

#### 1m Avg Volume(20)

```python
# Formula / 公式
AvgVolume20 = SUM(volume[0:20]) / 20

# Current volume check / 當前成交量檢查:
VolumeSpike = current_volume > (AvgVolume20 * 2)
```

| Parameter / 參數 | Value / 值 |
|------------------|------------|
| Timeframe / 時間框架 | 1m |
| Period / 週期 | 20 |
| Threshold / 閾值 | 2x average (200%) |
| Check frequency / 檢查頻率 | Every minute |

### 2.3 Cross Detection Rules / 交叉檢測規則

#### Cross Above (MA5 上穿 MA20)

```python
# Definition / 定義
CrossAbove = (MA5[prev] < MA20[prev]) AND (MA5[current] >= MA20[current])

# Where / 其中:
# - [prev] = previous 5m candle / 前一根5分鐘K線
# - [current] = current 5m candle / 當前5分鐘K線
```

| Condition / 條件 | Requirement / 要求 |
|------------------|-------------------|
| Previous state / 前狀態 | MA5 < MA20 |
| Current state / 當前狀態 | MA5 >= MA20 |
| Confirmation / 確認 | Must wait for 5m candle close / 需等待5分鐘K線收盤 |

#### Cross Below (MA5 下穿 MA20)

```python
# Definition / 定義
CrossBelow = (MA5[prev] > MA20[prev]) AND (MA5[current] <= MA20[current])
```

| Condition / 條件 | Requirement / 要求 |
|------------------|-------------------|
| Previous state / 前狀態 | MA5 > MA20 |
| Current state / 當前狀態 | MA5 <= MA20 |
| Confirmation / 確認 | Must wait for 5m candle close / 需等待5分鐘K線收盤 |

### 2.4 Contrarian Candle Detection / 逆勢K線檢測

#### 15m 連續紅K (Overheated Signal / 過熱訊號)

```python
# Definition / 定義
RedCandle = close < open
Consecutive4Red = RedCandle[-3] AND RedCandle[-2] AND RedCandle[-1] AND RedCandle[0]

# Where / 其中:
# - [-3], [-2], [-1] = previous 3 candles / 前3根K線
# - [0] = current candle / 當前K線
```

| Parameter / 參數 | Value / 值 |
|------------------|------------|
| Timeframe / 時間框架 | 15m |
| Condition / 條件 | 4 consecutive red candles / 連續4根紅K |
| Candle definition / K線定義 | close < open |
| Signal / 訊號 | contrarian_watch_overheated |

#### 15m 連續綠K (Oversold Signal / 超賣訊號)

```python
# Definition / 定義
GreenCandle = close > open
Consecutive4Green = GreenCandle[-3] AND GreenCandle[-2] AND GreenCandle[-1] AND GreenCandle[0]
```

| Parameter / 參數 | Value / 值 |
|------------------|------------|
| Timeframe / 時間框架 | 15m |
| Condition / 條件 | 4 consecutive green candles / 連續4根綠K |
| Candle definition / K線定義 | close > open |
| Signal / 訊號 | contrarian_watch_oversold |

### 2.5 Phase 2 Artifacts / Phase 2 產出

| Indicator / 指標 | Formula / 公式 | Status / 狀態 |
|------------------|----------------|---------------|
| 5m MA5 | SMA(5) | ✅ Defined |
| 5m MA20 | SMA(20) | ✅ Defined |
| 5m MA240 | SMA(240) | ✅ Defined |
| 1m Avg Volume(20) | SMA(20) on volume | ✅ Defined |
| Cross Above detection | MA5[prev] < MA20[prev] AND MA5 >= MA20 | ✅ Defined |
| Cross Below detection | MA5[prev] > MA20[prev] AND MA5 <= MA20 | ✅ Defined |
| 4 consecutive red | 4x (close < open) on 15m | ✅ Defined |
| 4 consecutive green | 4x (close > open) on 15m | ✅ Defined |

---

## Phase 3: Signal Engine Design / Phase 3: 訊號引擎設計

**Status**: ✅ Completed / 完成

### 3.1 Signal Types / 訊號類型

| Signal Type / 訊號類型 | Description / 說明 | Action Level / 行動層級 | Status / 狀態 |
|------------------------|--------------------|-------------------------|---------------|
| `trend_long` | Trend-following long alert / 順勢做多提醒 | ⚠️ Alert only | ✅ Defined |
| `trend_short` | Trend-following short alert / 順勢做空提醒 | ⚠️ Alert only | ✅ Defined |
| `contrarian_watch` | Contrarian observation alert / 逆勢觀察提醒 | 👀 Watch only | ✅ Defined |

**Important / 重要**: All signals are for **observation and alerts only**. No automatic trading is performed.

所有訊號僅供**觀察與提醒**，不自動執行交易。

### 3.2 Trend Long Signal / 順勢做多訊號

#### Conditions (ALL must be met / 必須全部符合):

```python
# Condition 1: Above long-term MA / 條件1: 在長期均線之上
C1 = close_5m > MA240

# Condition 2: MA cross / 條件2: 均線交叉
C2 = CrossAbove(MA5, MA20)

# Condition 3: Volume spike / 條件3: 成交量爆增
C3 = volume_1m_current > (AvgVolume20_1m * 2)

# Final signal / 最終訊號:
TrendLongSignal = C1 AND C2 AND C3
```

| Condition / 條件 | Indicator / 指標 | Threshold / 閾值 | Required / 必要 |
|------------------|------------------|------------------|-----------------|
| 1 | 5m close vs MA240 | close > MA240 | ✅ Yes |
| 2 | MA5 cross MA20 | Cross above | ✅ Yes |
| 3 | 1m volume | > 2x avg(20) | ✅ Yes |

### 3.3 Trend Short Signal / 順勢做空訊號

#### Conditions (ALL must be met / 必須全部符合):

```python
# Condition 1: Below long-term MA / 條件1: 在長期均線之下
C1 = close_5m < MA240

# Condition 2: MA cross / 條件2: 均線交叉
C2 = CrossBelow(MA5, MA20)

# Condition 3: Volume spike / 條件3: 成交量爆增
C3 = volume_1m_current > (AvgVolume20_1m * 2)

# Final signal / 最終訊號:
TrendShortSignal = C1 AND C2 AND C3
```

| Condition / 條件 | Indicator / 指標 | Threshold / 閾值 | Required / 必要 |
|------------------|------------------|------------------|-----------------|
| 1 | 5m close vs MA240 | close < MA240 | ✅ Yes |
| 2 | MA5 cross MA20 | Cross below | ✅ Yes |
| 3 | 1m volume | > 2x avg(20) | ✅ Yes |

### 3.4 Contrarian Watch Signal / 逆勢觀察訊號

#### Conditions (EITHER can trigger / 任一可觸發):

```python
# Overheated condition / 過熱條件:
Overheated = 4_consecutive_red_15m

# Oversold condition / 超賣條件:
Oversold = 4_consecutive_green_15m

# Final signal / 最終訊號:
ContrarianWatchSignal = Overheated OR Oversold
```

| Condition / 條件 | Timeframe / 時間框架 | Pattern / 型態 | Signal / 訊號 |
|------------------|----------------------|----------------|---------------|
| Overheated / 過熱 | 15m | 4 consecutive red / 連續4紅 | contrarian_watch_overheated |
| Oversold / 超賣 | 15m | 4 consecutive green / 連續4綠 | contrarian_watch_oversold |

**Warning / 警告**: `contrarian_watch` signals are **watch-only** and **NOT execution signals**. They indicate potential reversal zones for observation only.

`contrarian_watch` 訊號**僅供觀察**，**不是執行訊號**。僅表示潛在反轉區域供觀察。

### 3.5 Signal Classification / 訊號分類

| Classification / 分類 | Description / 說明 | Signals / 訊號 |
|------------------------|--------------------|----------------|
| **Confirmed Signal** / 確認訊號 | All conditions met, ready for alert / 所有條件符合，可發提醒 | trend_long, trend_short |
| **Watch-Only Signal** / 僅觀察訊號 | Observation only, no action implied / 僅觀察，無行動意涵 | contrarian_watch |

### 3.6 Signal Cooldown / Duplicate Suppression / 訊號冷卻/重複抑制

| Signal / 訊號 | Cooldown Period / 冷卻期 | Logic / 邏輯 |
|---------------|--------------------------|--------------|
| trend_long | 15 minutes | Same symbol no repeat within 15m / 同標的15分鐘內不重複 |
| trend_short | 15 minutes | Same symbol no repeat within 15m / 同標的15分鐘內不重複 |
| contrarian_watch | 30 minutes | Same direction no repeat within 30m / 同方向30分鐘內不重複 |

```python
# Cooldown logic / 冷卻邏輯:
if last_signal_time + cooldown > current_time:
    suppress_signal()
```

### 3.7 Same-Bar Repeated Alerts Handling / 同K線重複提醒處理

| Scenario / 情境 | Handling / 處理 |
|-----------------|-----------------|
| Multiple conditions met in same bar / 同根K線多條件符合 | Send ONE consolidated alert / 發送單一整合提醒 |
| Contrarian + Trend both trigger / 逆勢與趨勢同時觸發 | Send separate alerts with priority / 發送分開提醒並標示優先級 |
| Duplicate within cooldown / 冷卻期內重複 | Suppress and log only / 抑制並僅記錄 |

### 3.8 Signal Engine Pseudo-Code / 訊號引擎虛擬碼

```python
# Main signal loop / 主訊號迴圈:
every 5_minutes:
    for symbol in [BTCUSDT, ETHUSDT]:
        
        # Fetch data / 抓取資料
        data_5m = fetch_klines(symbol, '5m', limit=250)
        data_1m = fetch_klines(symbol, '1m', limit=25)
        data_15m = fetch_klines(symbol, '15m', limit=10)
        
        # Calculate indicators / 計算指標
        ma5 = calculate_ma(data_5m.close, 5)
        ma20 = calculate_ma(data_5m.close, 20)
        ma240 = calculate_ma(data_5m.close, 240)
        avg_volume_1m = calculate_ma(data_1m.volume, 20)
        
        # Check trend_long / 檢查順勢做多
        if (close > ma240) and cross_above(ma5, ma20):
            current_volume = data_1m.volume[-1]
            if current_volume > (avg_volume_1m * 2):
                if not in_cooldown(symbol, 'trend_long'):
                    send_alert(symbol, 'trend_long', generate_reason())
                    set_cooldown(symbol, 'trend_long', 15_minutes)
        
        # Check trend_short / 檢查順勢做空
        if (close < ma240) and cross_below(ma5, ma20):
            current_volume = data_1m.volume[-1]
            if current_volume > (avg_volume_1m * 2):
                if not in_cooldown(symbol, 'trend_short'):
                    send_alert(symbol, 'trend_short', generate_reason())
                    set_cooldown(symbol, 'trend_short', 15_minutes)
        
        # Check contrarian (every 15m) / 檢查逆勢 (每15分鐘)
        if current_time.minute % 15 == 0:
            if is_4_consecutive_red(data_15m):
                if not in_cooldown(symbol, 'contrarian_overheated'):
                    send_alert(symbol, 'contrarian_watch_overheated', generate_reason())
                    set_cooldown(symbol, 'contrarian_overheated', 30_minutes)
            
            if is_4_consecutive_green(data_15m):
                if not in_cooldown(symbol, 'contrarian_oversold'):
                    send_alert(symbol, 'contrarian_watch_oversold', generate_reason())
                    set_cooldown(symbol, 'contrarian_oversold', 30_minutes)
```

### 3.9 Condition Tree / 條件樹

```
Start / 開始
├── Fetch Data / 抓取資料
│   ├── 5m (250 candles)
│   ├── 1m (25 candles)
│   └── 15m (10 candles)
│
├── Calculate Indicators / 計算指標
│   ├── 5m: MA5, MA20, MA240
│   └── 1m: AvgVolume20
│
├── Check Trend Long / 檢查順勢做多
│   ├── close > MA240? → No → Skip
│   ├── MA5 cross above MA20? → No → Skip
│   ├── 1m volume > 2x avg? → No → Skip
│   └── Cooldown check → Send alert
│
├── Check Trend Short / 檢查順勢做空
│   ├── close < MA240? → No → Skip
│   ├── MA5 cross below MA20? → No → Skip
│   ├── 1m volume > 2x avg? → No → Skip
│   └── Cooldown check → Send alert
│
└── Check Contrarian (15m) / 檢查逆勢
    ├── 4 consecutive red? → Send watch alert
    └── 4 consecutive green? → Send watch alert
```

### 3.10 Output Schema / 輸出格式

```json
{
  "signal_output": {
    "timestamp": "integer (ms)",
    "symbol": "string (BTCUSDT|ETHUSDT)",
    "signal_type": "string (trend_long|trend_short|contrarian_watch)",
    "signal_subtype": "string (overheated|oversold|null)",
    "timeframe_context": {
      "primary": "5m",
      "volume_confirmation": "1m",
      "contrarian": "15m"
    },
    "price_data": {
      "close_5m": "string",
      "ma5": "string",
      "ma20": "string",
      "ma240": "string",
      "volume_1m": "string",
      "volume_avg_1m": "string"
    },
    "conditions": {
      "c1_trend_aligned": "boolean",
      "c2_ma_cross": "boolean",
      "c3_volume_spike": "boolean"
    },
    "alert_level": "string (confirmed|watch_only)",
    "reason_summary": "string",
    "warning": "string (ALERT_ONLY_NO_AUTO_TRADE)"
  }
}
```

### 3.11 Phase 3 Artifacts / Phase 3 產出

| Artifact / 產出 | Status / 狀態 |
|-----------------|---------------|
| Signal type definitions / 訊號類型定義 | ✅ Complete |
| Trend long conditions / 順勢做多條件 | ✅ Complete |
| Trend short conditions / 順勢做空條件 | ✅ Complete |
| Contrarian watch conditions / 逆勢觀察條件 | ✅ Complete |
| Signal classification / 訊號分類 | ✅ Complete |
| Cooldown logic / 冷卻邏輯 | ✅ Complete |
| Duplicate suppression / 重複抑制 | ✅ Complete |
| Pseudo-code / 虛擬碼 | ✅ Complete |
| Condition tree / 條件樹 | ✅ Complete |
| Output schema / 輸出格式 | ✅ Complete |

---

## Phase 4: Notification Design / Phase 4: 通知設計

**Status**: ✅ Completed / 完成

### 4.1 Message Template / 訊息模板

#### Trend Long Alert / 順勢做多提醒

```
🟢 [TREND LONG ALERT] / [順勢做多提醒]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Symbol / 標的: {symbol}
Time / 時間: {timestamp}
Signal Type / 訊號類型: trend_long ✅ CONFIRMED / 確認

Price Data / 價格資料:
  Close / 收盤: {close_5m}
  MA5: {ma5}
  MA20: {ma20}
  MA240: {ma240}

Volume Data / 成交量資料:
  Current 1m / 當前1m: {volume_1m}
  Avg 1m (20) / 平均1m: {volume_avg_1m}
  Ratio / 比率: {volume_ratio}x

Conditions Met / 符合條件:
  ✅ close > MA240
  ✅ MA5 crossed above MA20
  ✅ volume > 2x average

⚠️  IMPORTANT / 重要  ⚠️
This is an ALERT ONLY for observation.
這僅供觀察的提醒。
NO automatic trading is performed.
不執行自動交易。

Reason / 原因: {reason_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Trend Short Alert / 順勢做空提醒

```
🔴 [TREND SHORT ALERT] / [順勢做空提醒]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Symbol / 標的: {symbol}
Time / 時間: {timestamp}
Signal Type / 訊號類型: trend_short ✅ CONFIRMED / 確認

Price Data / 價格資料:
  Close / 收盤: {close_5m}
  MA5: {ma5}
  MA20: {ma20}
  MA240: {ma240}

Volume Data / 成交量資料:
  Current 1m / 當前1m: {volume_1m}
  Avg 1m (20) / 平均1m: {volume_avg_1m}
  Ratio / 比率: {volume_ratio}x

Conditions Met / 符合條件:
  ✅ close < MA240
  ✅ MA5 crossed below MA20
  ✅ volume > 2x average

⚠️  IMPORTANT / 重要  ⚠️
This is an ALERT ONLY for observation.
這僅供觀察的提醒。
NO automatic trading is performed.
不執行自動交易。

Reason / 原因: {reason_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### Contrarian Watch Alert / 逆勢觀察提醒

```
👁️ [CONTRARIAN WATCH] / [逆勢觀察]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Symbol / 標的: {symbol}
Time / 時間: {timestamp}
Signal Type / 訊號類型: contrarian_watch
Subtype / 子類型: {overheated|oversold}

⚠️  WATCH ONLY / 僅觀察  ⚠️
This is NOT an execution signal.
這不是執行訊號。
For observation and analysis only.
僅供觀察與分析。

Pattern Detected / 檢測到的型態:
  Timeframe / 時間框架: 15m
  Pattern / 型態: {4 consecutive red candles|4 consecutive green candles}
  
Context / 背景:
  15m candles show extended move.
  15m K線顯示延伸走勢。
  Potential reversal zone - observe only.
  潛在反轉區域 - 僅觀察。

🔴 DO NOT TRADE BASED ON THIS SIGNAL ALONE / 請勿僅根據此訊號交易

Reason / 原因: {reason_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 4.2 Alert Payload Schema / 提醒載荷格式

```json
{
  "alert_payload": {
    "metadata": {
      "version": "1.0.0",
      "system_id": "MONITOR-001",
      "timestamp": "2026-04-05T18:30:00Z"
    },
    "alert": {
      "id": "uuid",
      "symbol": "BTCUSDT",
      "signal_type": "trend_long",
      "signal_subtype": null,
      "alert_level": "confirmed",
      "timestamp": 1775385000000,
      "timezone": "UTC"
    },
    "market_data": {
      "timeframes": {
        "5m": {
          "close": "69250.50",
          "ma5": "69180.25",
          "ma20": "69050.00",
          "ma240": "68500.75"
        },
        "1m": {
          "volume": "12.5",
          "volume_avg_20": "5.2",
          "volume_ratio": 2.4
        },
        "15m": {
          "context": "trending_up"
        }
      }
    },
    "conditions": {
      "c1_trend_aligned": true,
      "c2_ma_cross": true,
      "c3_volume_spike": true,
      "all_met": true
    },
    "warnings": {
      "alert_only": true,
      "no_auto_trade": true,
      "contrarian_is_watch_only": false
    },
    "reason": {
      "summary": "BTCUSDT 5m: close > MA240, MA5 crossed above MA20, 1m volume 2.4x average",
      "detail": "Trend-following long conditions met with volume confirmation"
    }
  }
}
```

### 4.3 Notification Fields / 通知欄位

| Field / 欄位 | Type / 類型 | Required / 必要 | Description / 說明 |
|--------------|-------------|-----------------|--------------------|
| symbol | string | ✅ Yes | Trading pair / 交易對 |
| signal_type | enum | ✅ Yes | trend_long, trend_short, contrarian_watch |
| timestamp | integer | ✅ Yes | Alert timestamp (ms) / 提醒時間戳 |
| alert_level | enum | ✅ Yes | confirmed, watch_only |
| close_5m | string | ✅ Yes | 5m closing price / 5m收盤價 |
| ma5 | string | ⚠️ Conditional | If trend signal / 若為趨勢訊號 |
| ma20 | string | ⚠️ Conditional | If trend signal / 若為趨勢訊號 |
| ma240 | string | ⚠️ Conditional | If trend signal / 若為趨勢訊號 |
| volume_1m | string | ⚠️ Conditional | If trend signal / 若為趨勢訊號 |
| volume_avg_1m | string | ⚠️ Conditional | If trend signal / 若為趨勢訊號 |
| reason_summary | string | ✅ Yes | Human-readable reason / 可讀原因 |
| warning | string | ✅ Yes | ALERT_ONLY_NO_AUTO_TRADE |

### 4.4 Contrarian Watch Warning / 逆勢觀察警告

**Required Warning Text / 必要警告文字**:

```
👁️ CONTRARIAN_WATCH - WATCH ONLY / 僅觀察

This signal is for OBSERVATION ONLY.
此訊號僅供觀察。

It is NOT an execution signal.
這不是執行訊號。
Do NOT trade based on this signal alone.
請勿僅根據此訊號交易。

Purpose / 目的:
- Identify potential reversal zones / 識別潛在反轉區域
- Mark extended moves for analysis / 標記延伸走勢供分析
- Support decision-making, not replace it / 輔助決策，非取代決策
```

### 4.5 Notification Examples / 通知範例

#### Example 1: Trend Long / 範例1: 順勢做多

```json
{
  "symbol": "BTCUSDT",
  "signal_type": "trend_long",
  "alert_level": "confirmed",
  "close_5m": "69250.50",
  "ma5": "69180.25",
  "ma20": "69050.00",
  "ma240": "68500.75",
  "volume_1m": "12.5",
  "volume_avg_1m": "5.2",
  "reason_summary": "BTC above MA240, MA5 crossed above MA20 with 2.4x volume confirmation",
  "warning": "ALERT_ONLY_NO_AUTO_TRADE"
}
```

#### Example 2: Contrarian Watch Overheated / 範例2: 逆勢觀察過熱

```json
{
  "symbol": "ETHUSDT",
  "signal_type": "contrarian_watch",
  "signal_subtype": "overheated",
  "alert_level": "watch_only",
  "close_5m": "3520.75",
  "timeframe_15m_context": "4_consecutive_red",
  "reason_summary": "ETH 15m shows 4 consecutive red candles - potential reversal zone",
  "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
}
```

### 4.6 Phase 4 Artifacts / Phase 4 產出

| Artifact / 產出 | Status / 狀態 |
|-----------------|---------------|
| Message templates (3 types) / 訊息模板 | ✅ Complete |
| Alert payload schema / 提醒載荷格式 | ✅ Complete |
| Required fields definition / 必要欄位定義 | ✅ Complete |
| Contrarian warning text / 逆勢警告文字 | ✅ Complete |
| Notification examples / 通知範例 | ✅ Complete |

---

## Phase 5: File Structure and Implementation Plan / Phase 5: 檔案結構與實作規劃

**Status**: ✅ Completed / 完成

### 5.1 Proposed File Tree / 建議檔案結構

```
monitoring_system/
├── config/
│   ├── __init__.py
│   ├── settings.py              # System settings / 系統設定
│   └── symbols.py               # Symbol definitions / 標的定義
│
├── data/
│   ├── __init__.py
│   ├── fetcher.py               # Data fetching / 資料抓取
│   └── cache.py                 # Data caching / 資料快取
│
├── indicators/
│   ├── __init__.py
│   ├── moving_average.py        # MA calculations / MA計算
│   ├── volume.py                # Volume metrics / 成交量指標
│   └── candle_patterns.py       # Pattern detection / 型態檢測
│
├── signals/
│   ├── __init__.py
│   ├── engine.py                # Signal generation / 訊號產生
│   ├── conditions.py            # Condition checks / 條件檢查
│   └── cooldown.py              # Cooldown management / 冷卻管理
│
├── notifications/
│   ├── __init__.py
│   ├── formatter.py             # Message formatting / 訊息格式化
│   ├── dispatcher.py            # Alert dispatching / 提醒發送
│   └── templates/               # Message templates / 訊息模板
│       ├── trend_long.txt
│       ├── trend_short.txt
│       └── contrarian_watch.txt
│
├── core/
│   ├── __init__.py
│   ├── scheduler.py             # Polling scheduler / 輪詢排程器
│   ├── validator.py             # Input validation / 輸入驗證
│   └── logger.py                # System logging / 系統記錄
│
├── tests/
│   ├── __init__.py
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

### 5.2 Module Responsibilities / 模組職責

| Module / 模組 | Layer / 層級 | Responsibility / 職責 |
|---------------|--------------|----------------------|
| `data.fetcher` | Data Layer | Fetch klines from Binance / 從 Binance 抓取 K 線 |
| `data.cache` | Data Layer | Cache recent data / 快取近期資料 |
| `indicators.moving_average` | Indicator Layer | Calculate MA5, MA20, MA240 / 計算 MA |
| `indicators.volume` | Indicator Layer | Calculate volume averages / 計算成交量平均 |
| `indicators.candle_patterns` | Indicator Layer | Detect consecutive candles / 檢測連續 K 線 |
| `signals.conditions` | Signal Layer | Check signal conditions / 檢查訊號條件 |
| `signals.cooldown` | Signal Layer | Manage cooldown state / 管理冷卻狀態 |
| `signals.engine` | Signal Layer | Generate signals / 產生訊號 |
| `notifications.formatter` | Notification Layer | Format alert messages / 格式化提醒訊息 |
| `notifications.dispatcher` | Notification Layer | Send alerts / 發送提醒 |
| `core.scheduler` | Core | Schedule polling / 排程輪詢 |
| `core.logger` | Core | Log system events / 記錄系統事件 |

### 5.3 Step-by-Step Implementation Order / 分步實作順序

#### Phase A: Foundation (Week 1) / 基礎 (第1週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Status / 狀態 |
|-------------|---------------|-------------|---------------|
| A1 | config | Create settings and symbol configs / 建立設定與標的設定 | 📝 Planned |
| A2 | data | Implement Binance API fetcher / 實作 Binance API 抓取器 | 📝 Planned |
| A3 | data | Add data caching layer / 添加資料快取層 | 📝 Planned |
| A4 | core | Setup logging infrastructure / 設定記錄基礎設施 | 📝 Planned |

#### Phase B: Indicators (Week 1-2) / 指標 (第1-2週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Status / 狀態 |
|-------------|---------------|-------------|---------------|
| B1 | indicators | Implement SMA calculation / 實作 SMA 計算 | 📝 Planned |
| B2 | indicators | Implement volume average / 實作成交量平均 | 📝 Planned |
| B3 | indicators | Implement cross detection / 實作交叉檢測 | 📝 Planned |
| B4 | indicators | Implement consecutive candle detection / 實作連續 K 線檢測 | 📝 Planned |
| B5 | tests | Add indicator unit tests / 添加指標單元測試 | 📝 Planned |

#### Phase C: Signal Engine (Week 2) / 訊號引擎 (第2週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Status / 狀態 |
|-------------|---------------|-------------|---------------|
| C1 | signals | Implement condition checks / 實作條件檢查 | 📝 Planned |
| C2 | signals | Implement cooldown manager / 實作冷卻管理器 | 📝 Planned |
| C3 | signals | Implement signal engine / 實作訊號引擎 | 📝 Planned |
| C4 | tests | Add signal engine tests / 添加訊號引擎測試 | 📝 Planned |

#### Phase D: Notifications (Week 2-3) / 通知 (第2-3週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Status / 狀態 |
|-------------|---------------|-------------|---------------|
| D1 | notifications | Create message templates / 建立訊息模板 | 📝 Planned |
| D2 | notifications | Implement formatter / 實作格式化器 | 📝 Planned |
| D3 | notifications | Implement dispatcher (console first) / 實作發送器 (先控制台) | 📝 Planned |
| D4 | tests | Add notification tests / 添加通知測試 | 📝 Planned |

#### Phase E: Integration (Week 3) / 整合 (第3週)

| Step / 步驟 | Module / 模組 | Task / 任務 | Status / 狀態 |
|-------------|---------------|-------------|---------------|
| E1 | core | Implement scheduler / 實作排程器 | 📝 Planned |
| E2 | main | Create main entry point / 建立主要進入點 | 📝 Planned |
| E3 | - | Integration testing / 整合測試 | 📝 Planned |
| E4 | - | Documentation review / 文件審查 | 📝 Planned |

#### Phase F: Deployment Prep (Week 4) / 部署準備 (第4週)

| Step / 步驟 | Task / 任務 | Status / 狀態 |
|-------------|-------------|---------------|
| F1 | Add Discord webhook support / 添加 Discord webhook 支援 | 📝 Planned |
| F2 | Add error handling and recovery / 添加錯誤處理與恢復 | 📝 Planned |
| F3 | Performance optimization / 效能優化 | 📝 Planned |
| F4 | Final testing and validation / 最終測試與驗證 | 📝 Planned |

### 5.4 MVP Scope / MVP 範圍

| Feature / 功能 | MVP / 最小可行 | Full / 完整 |
|----------------|----------------|-------------|
| Data source / 資料來源 | Binance only / 僅 Binance | Multiple sources / 多來源 |
| Notification / 通知 | Console only / 僅控制台 | Discord, Email / Discord, 郵件 |
| Symbols / 標的 | BTC, ETH only / 僅 BTC, ETH | Configurable / 可設定 |
| Cooldown / 冷卻 | Fixed 15min / 固定15分鐘 | Configurable per symbol / 每標的可設定 |
| Backtesting / 回測 | Not included / 不包含 | Historical signal analysis / 歷史訊號分析 |

### 5.5 Phase 5 Artifacts / Phase 5 產出

| Artifact / 產出 | Status / 狀態 |
|-----------------|---------------|
| File structure diagram / 檔案結構圖 | ✅ Complete |
| Module responsibilities / 模組職責 | ✅ Complete |
| Implementation phases / 實作階段 | ✅ Complete |
| Step-by-step order / 分步順序 | ✅ Complete |
| MVP scope definition / MVP 範圍定義 | ✅ Complete |

---

## System Status Summary / 系統狀態總結

### Completed Phases / 完成階段

| Phase / 階段 | Status / 狀態 | Artifacts / 產出 |
|--------------|---------------|------------------|
| Phase 1: Data Fetch Design / 資料抓取設計 | ✅ Complete | Data requirements, symbol list, polling logic |
| Phase 2: Indicator Definition / 指標定義 | ✅ Complete | MA formulas, volume calc, cross detection |
| Phase 3: Signal Engine Design / 訊號引擎設計 | ✅ Complete | Signal logic, cooldown, pseudo-code |
| Phase 4: Notification Design / 通知設計 | ✅ Complete | Message templates, payload schema |
| Phase 5: Implementation Plan / 實作規劃 | ✅ Complete | File structure, module plan, MVP scope |

### Signal Types Implemented / 實作的訊號類型

| Signal / 訊號 | Status / 狀態 | Notes / 備註 |
|---------------|---------------|--------------|
| trend_long / 順勢做多 | ✅ Specified | 3 conditions, volume confirmation |
| trend_short / 順勢做空 | ✅ Specified | 3 conditions, volume confirmation |
| contrarian_watch / 逆勢觀察 | ✅ Specified | 15m 4-candle pattern, watch-only |

### What is Ready Now / 目前已就緒

| Component / 組件 | Status / 狀態 |
|------------------|---------------|
| System design document / 系統設計文件 | ✅ Complete |
| Signal specification / 訊號規格 | ✅ Complete |
| Indicator definitions / 指標定義 | ✅ Complete |
| Notification templates / 通知模板 | ✅ Complete |
| File structure plan / 檔案結構計畫 | ✅ Complete |
| Implementation roadmap / 實作路線圖 | ✅ Complete |

### What is Still Placeholder / 仍為佔位

| Component / 組件 | Status / 狀態 | Next Step / 下一步 |
|------------------|---------------|--------------------|
| Binance API connection / Binance API 連線 | 📝 Placeholder | Implement fetcher module |
| Data caching / 資料快取 | 📝 Placeholder | Implement cache module |
| Real-time polling / 即時輪詢 | 📝 Placeholder | Implement scheduler |
| Discord webhook / Discord webhook | 📝 Placeholder | Phase F implementation |
| Unit tests / 單元測試 | 📝 Placeholder | Phase B-D implementation |

### Recommended Next Implementation Task / 建議的下一實作任務

**T-023: Implement Data Fetcher Module / 實作資料抓取模組**

- Create `monitoring_system/data/fetcher.py`
- Implement Binance API klines fetching
- Add rate limit handling
- Add error retry logic
- Add basic tests

This is the foundation for all subsequent implementation.

這是所有後續實作的基礎。

---

## Important Reminders / 重要提醒

### ⚠️ ALERT-ONLY SYSTEM / 僅提醒系統

```
╔══════════════════════════════════════════════════════════════════╗
║  THIS SYSTEM GENERATES ALERTS ONLY                               ║
║  本系統僅產生提醒                                                 ║
║                                                                  ║
║  • NO automatic trading / 不自動交易                              ║
║  • NO order execution / 不執行訂單                                ║
║  • NO position management / 不管理部位                            ║
║                                                                  ║
║  All signals require human review and decision.                  ║
║  所有訊號都需要人工審查與決策。                                     ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ CONTRARIAN_WATCH IS NOT AN EXECUTION SIGNAL / 逆勢觀察不是執行訊號

```
╔══════════════════════════════════════════════════════════════════╗
║  contrarian_watch signals are for OBSERVATION ONLY               ║
║  contrarian_watch 訊號僅供觀察                                     ║
║                                                                  ║
║  • DO NOT trade based on this signal alone                       ║
║    請勿僅根據此訊號交易                                            ║
║  • Use for identifying potential reversal zones                  ║
║    用於識別潛在反轉區域                                            ║
║  • Always confirm with additional analysis                       ║
║    務必以額外分析確認                                              ║
╚══════════════════════════════════════════════════════════════════╝
```

---

**Created by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Based on**: User requirements for BTC/ETH monitoring  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## Related Files / 相關檔案

- `workflows/btc_eth_monitoring_signal_spec.md` - Detailed signal specifications / 詳細訊號規格
- `workflows/btc_eth_monitoring_file_plan.md` - File structure and implementation plan / 檔案結構與實作計畫
