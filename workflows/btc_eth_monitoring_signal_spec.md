# BTC/ETH Monitoring Signal Specification
# BTC/ETH 監測訊號規格

**Version**: 1.0.0  
**版本**: 1.0.0  
**Document ID**: SIGSPEC-001  
**文件識別碼**: SIGSPEC-001  
**Date**: 2026-04-05  
**日期**: 2026-04-05

---

## 1. Signal Overview / 訊號總覽

### 1.1 Signal Types / 訊號類型

| Signal Type / 訊號類型 | Level / 層級 | Description / 說明 |
|------------------------|--------------|--------------------|
| `trend_long` | Confirmed / 確認 | Bullish trend-following signal / 看漲順勢訊號 |
| `trend_short` | Confirmed / 確認 | Bearish trend-following signal / 看跌順勢訊號 |
| `contrarian_watch_overheated` | Watch Only / 僅觀察 | Potential reversal from overextended up move / 過度延伸上漲的潛在反轉 |
| `contrarian_watch_oversold` | Watch Only / 僅觀察 | Potential reversal from overextended down move / 過度延伸下跌的潛在反轉 |

### 1.2 Signal Classification Matrix / 訊號分類矩陣

| Signal / 訊號 | Execution / 執行 | Observation / 觀察 | Alert / 提醒 |
|---------------|------------------|--------------------|--------------|
| trend_long | ❌ No | ✅ Yes | ✅ Yes |
| trend_short | ❌ No | ✅ Yes | ✅ Yes |
| contrarian_watch_* | ❌ No | ✅ Yes | ✅ Yes |

**Important**: ALL signals are alert-only. No automatic trading.

**重要**: 所有訊號僅供提醒，不自動交易。

---

## 2. Trend Long Signal / 順勢做多訊號

### 2.1 Signal ID / 訊號識別

- **Internal Code**: `SIG_TREND_LONG`
- **Display Name**: Trend Long / 順勢做多
- **Direction**: Bullish / 看漲

### 2.2 Trigger Conditions / 觸發條件

| # | Condition / 條件 | Indicator / 指標 | Operator / 運算子 | Threshold / 閾值 | Required / 必要 |
|---|------------------|------------------|-------------------|------------------|-----------------|
| C1 | Price above long-term trend / 價格在長期趨勢之上 | 5m Close vs MA240 | `>` | MA240 value | ✅ Yes |
| C2 | Short-term momentum up / 短期動能向上 | 5m MA5 vs MA20 | `cross_above` | MA20 value | ✅ Yes |
| C3 | Volume confirmation / 成交量確認 | 1m Volume vs Avg(20) | `>` | 2.0x average | ✅ Yes |

### 2.3 Logic Expression / 邏輯運算式

```python
trend_long_signal = (
    close_5m > ma240_5m AND
    cross_above(ma5_5m, ma20_5m) AND
    volume_1m > (avg_volume_20_1m * 2.0)
)
```

### 2.4 Timeframe Requirements / 時間框架需求

| Timeframe / 時間框架 | Data Needed / 所需資料 | Update Frequency / 更新頻率 |
|----------------------|------------------------|----------------------------|
| 5m | 250 candles | Every 5 minutes |
| 1m | 25 candles | Every 1 minute |

### 2.5 Output Fields / 輸出欄位

```json
{
  "signal_type": "trend_long",
  "direction": "bullish",
  "symbol": "BTCUSDT",
  "price_data": {
    "close_5m": "69250.50",
    "ma5": "69180.25",
    "ma20": "69050.00",
    "ma240": "68500.75"
  },
  "volume_data": {
    "current_1m": "12.5",
    "avg_20_1m": "5.2",
    "ratio": 2.4
  },
  "conditions_met": {
    "c1_above_ma240": true,
    "c2_ma_cross": true,
    "c3_volume_spike": true
  }
}
```

---

## 3. Trend Short Signal / 順勢做空訊號

### 3.1 Signal ID / 訊號識別

- **Internal Code**: `SIG_TREND_SHORT`
- **Display Name**: Trend Short / 順勢做空
- **Direction**: Bearish / 看跌

### 3.2 Trigger Conditions / 觸發條件

| # | Condition / 條件 | Indicator / 指標 | Operator / 運算子 | Threshold / 閾值 | Required / 必要 |
|---|------------------|------------------|-------------------|------------------|-----------------|
| C1 | Price below long-term trend / 價格在長期趨勢之下 | 5m Close vs MA240 | `<` | MA240 value | ✅ Yes |
| C2 | Short-term momentum down / 短期動能向下 | 5m MA5 vs MA20 | `cross_below` | MA20 value | ✅ Yes |
| C3 | Volume confirmation / 成交量確認 | 1m Volume vs Avg(20) | `>` | 2.0x average | ✅ Yes |

### 3.3 Logic Expression / 邏輯運算式

```python
trend_short_signal = (
    close_5m < ma240_5m AND
    cross_below(ma5_5m, ma20_5m) AND
    volume_1m > (avg_volume_20_1m * 2.0)
)
```

### 3.4 Timeframe Requirements / 時間框架需求

Same as Trend Long / 與順勢做多相同

### 3.5 Output Fields / 輸出欄位

```json
{
  "signal_type": "trend_short",
  "direction": "bearish",
  "symbol": "ETHUSDT",
  "price_data": {
    "close_5m": "3520.75",
    "ma5": "3535.00",
    "ma20": "3550.50",
    "ma240": "3580.25"
  },
  "volume_data": {
    "current_1m": "45.2",
    "avg_20_1m": "18.5",
    "ratio": 2.44
  },
  "conditions_met": {
    "c1_below_ma240": true,
    "c2_ma_cross": true,
    "c3_volume_spike": true
  }
}
```

---

## 4. Contrarian Watch Signals / 逆勢觀察訊號

### 4.1 Signal ID / 訊號識別

| Subtype / 子類型 | Internal Code | Display Name |
|------------------|---------------|--------------|
| Overheated / 過熱 | `SIG_CONT_WATCH_HOT` | Contrarian Watch: Overheated |
| Oversold / 超賣 | `SIG_CONT_WATCH_COLD` | Contrarian Watch: Oversold |

### 4.2 ⚠️ Important Warning / 重要警告

```
╔════════════════════════════════════════════════════════════════╗
║  CONTRARIAN_WATCH SIGNALS ARE FOR OBSERVATION ONLY             ║
║  CONTRARIAN_WATCH 訊號僅供觀察                                   ║
║                                                                ║
║  • NOT an execution signal / 不是執行訊號                        ║
║  • NOT a trade recommendation / 不是交易建議                     ║
║  • For analysis and learning only / 僅供分析與學習               ║
║                                                                ║
║  These signals indicate POTENTIAL reversal zones.              ║
║  這些訊號指示潛在反轉區域。                                       ║
║  They require additional confirmation before any action.       ║
║  需要額外確認才能採取行動。                                        ║
╚════════════════════════════════════════════════════════════════╝
```

### 4.3 Overheated Condition / 過熱條件

#### Trigger Conditions / 觸發條件

| # | Condition / 條件 | Timeframe / 時間框架 | Pattern / 型態 | Required / 必要 |
|---|------------------|----------------------|----------------|-----------------|
| C1 | Consecutive red candles / 連續紅K | 15m | 4 consecutive closes < opens | ✅ Yes |

#### Logic Expression / 邏輯運算式

```python
contrarian_overheated = (
    close_15m[-3] < open_15m[-3] AND
    close_15m[-2] < open_15m[-2] AND
    close_15m[-1] < open_15m[-1] AND
    close_15m[0] < open_15m[0]
)
```

#### Output Fields / 輸出欄位

```json
{
  "signal_type": "contrarian_watch",
  "subtype": "overheated",
  "direction": "potential_reversal_down",
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "pattern": {
    "type": "4_consecutive_red",
    "candles": [
      {"timestamp": "...", "open": "69500", "close": "69300"},
      {"timestamp": "...", "open": "69300", "close": "69100"},
      {"timestamp": "...", "open": "69100", "close": "68900"},
      {"timestamp": "...", "open": "68900", "close": "68700"}
    ]
  },
  "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
}
```

### 4.4 Oversold Condition / 超賣條件

#### Trigger Conditions / 觸發條件

| # | Condition / 條件 | Timeframe / 時間框架 | Pattern / 型態 | Required / 必要 |
|---|------------------|----------------------|----------------|-----------------|
| C1 | Consecutive green candles / 連續綠K | 15m | 4 consecutive closes > opens | ✅ Yes |

#### Logic Expression / 邏輯運算式

```python
contrarian_oversold = (
    close_15m[-3] > open_15m[-3] AND
    close_15m[-2] > open_15m[-2] AND
    close_15m[-1] > open_15m[-1] AND
    close_15m[0] > open_15m[0]
)
```

#### Output Fields / 輸出欄位

```json
{
  "signal_type": "contrarian_watch",
  "subtype": "oversold",
  "direction": "potential_reversal_up",
  "symbol": "ETHUSDT",
  "timeframe": "15m",
  "pattern": {
    "type": "4_consecutive_green",
    "candles": [
      {"timestamp": "...", "open": "3500", "close": "3515"},
      {"timestamp": "...", "open": "3515", "close": "3530"},
      {"timestamp": "...", "open": "3530", "close": "3545"},
      {"timestamp": "...", "open": "3545", "close": "3560"}
    ]
  },
  "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
}
```

---

## 5. Signal Prerequisites / 訊號先決條件

### 5.1 Data Prerequisites / 資料先決條件

| Prerequisite / 先決條件 | Trend Signals / 趨勢訊號 | Contrarian / 逆勢 |
|-------------------------|--------------------------|--------------------|
| 5m klines available / 5m K線可用 | ✅ Required | ❌ Not needed |
| 1m klines available / 1m K線可用 | ✅ Required | ❌ Not needed |
| 15m klines available / 15m K線可用 | ❌ Not needed | ✅ Required |
| Minimum 250 5m candles / 最少250根5m | ✅ Required | ❌ Not needed |
| Minimum 25 1m candles / 最少25根1m | ✅ Required | ❌ Not needed |
| Minimum 10 15m candles / 最少10根15m | ❌ Not needed | ✅ Required |

### 5.2 Indicator Prerequisites / 指標先決條件

| Indicator / 指標 | Trend Long / 順勢做多 | Trend Short / 順勢做空 | Contrarian / 逆勢 |
|------------------|------------------------|------------------------|--------------------|
| MA5 (5m) | ✅ Required | ✅ Required | ❌ Not needed |
| MA20 (5m) | ✅ Required | ✅ Required | ❌ Not needed |
| MA240 (5m) | ✅ Required | ✅ Required | ❌ Not needed |
| Avg Volume 20 (1m) | ✅ Required | ✅ Required | ❌ Not needed |
| Candle pattern (15m) | ❌ Not needed | ❌ Not needed | ✅ Required |

---

## 6. Signal Output Schema / 訊號輸出格式

### 6.1 Complete Output Schema / 完整輸出格式

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "MonitoringSignal",
  "type": "object",
  "required": [
    "metadata",
    "signal",
    "market_data",
    "conditions",
    "warnings"
  ],
  "properties": {
    "metadata": {
      "type": "object",
      "properties": {
        "version": {"type": "string"},
        "system_id": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"}
      }
    },
    "signal": {
      "type": "object",
      "properties": {
        "id": {"type": "string", "format": "uuid"},
        "type": {
          "type": "string",
          "enum": ["trend_long", "trend_short", "contrarian_watch"]
        },
        "subtype": {
          "type": ["string", "null"],
          "enum": ["overheated", "oversold", null]
        },
        "level": {
          "type": "string",
          "enum": ["confirmed", "watch_only"]
        },
        "symbol": {
          "type": "string",
          "enum": ["BTCUSDT", "ETHUSDT"]
        },
        "timestamp": {"type": "integer"},
        "timezone": {"type": "string"}
      }
    },
    "market_data": {
      "type": "object",
      "properties": {
        "timeframes": {
          "type": "object",
          "properties": {
            "5m": {
              "type": "object",
              "properties": {
                "close": {"type": "string"},
                "ma5": {"type": "string"},
                "ma20": {"type": "string"},
                "ma240": {"type": "string"}
              }
            },
            "1m": {
              "type": "object",
              "properties": {
                "volume": {"type": "string"},
                "volume_avg_20": {"type": "string"},
                "volume_ratio": {"type": "number"}
              }
            },
            "15m": {
              "type": "object",
              "properties": {
                "pattern": {"type": "string"}
              }
            }
          }
        }
      }
    },
    "conditions": {
      "type": "object",
      "properties": {
        "c1": {"type": "boolean"},
        "c2": {"type": "boolean"},
        "c3": {"type": "boolean"},
        "all_met": {"type": "boolean"}
      }
    },
    "warnings": {
      "type": "object",
      "properties": {
        "alert_only": {"type": "boolean"},
        "no_auto_trade": {"type": "boolean"},
        "contrarian_is_watch_only": {"type": "boolean"}
      }
    }
  }
}
```

### 6.2 Field Descriptions / 欄位說明

| Field Path / 欄位路徑 | Type / 類型 | Description / 說明 |
|-----------------------|-------------|--------------------|
| `metadata.version` | string | Signal spec version / 訊號規格版本 |
| `metadata.system_id` | string | System identifier / 系統識別碼 |
| `metadata.timestamp` | string | ISO 8601 timestamp / ISO 8601 時間戳 |
| `signal.id` | UUID | Unique signal ID / 唯一訊號識別碼 |
| `signal.type` | enum | Signal classification / 訊號分類 |
| `signal.subtype` | enum | Contrarian subtype / 逆勢子類型 |
| `signal.level` | enum | Confirmation level / 確認層級 |
| `signal.symbol` | enum | Trading pair / 交易對 |
| `signal.timestamp` | integer | Unix timestamp (ms) / Unix 時間戳 |
| `market_data.timeframes.5m.close` | string | 5m closing price / 5m收盤價 |
| `market_data.timeframes.5m.ma5` | string | 5-period MA / 5週期均線 |
| `market_data.timeframes.5m.ma20` | string | 20-period MA / 20週期均線 |
| `market_data.timeframes.5m.ma240` | string | 240-period MA / 240週期均線 |
| `market_data.timeframes.1m.volume` | string | Current 1m volume / 當前1m成交量 |
| `market_data.timeframes.1m.volume_avg_20` | string | 20-period volume avg / 20週期成交量平均 |
| `market_data.timeframes.1m.volume_ratio` | number | Volume multiplier / 成交量倍數 |
| `conditions.c1` | boolean | Condition 1 met / 條件1符合 |
| `conditions.c2` | boolean | Condition 2 met / 條件2符合 |
| `conditions.c3` | boolean | Condition 3 met / 條件3符合 |
| `conditions.all_met` | boolean | All conditions met / 所有條件符合 |
| `warnings.alert_only` | boolean | Is alert-only signal / 是否僅提醒訊號 |
| `warnings.no_auto_trade` | boolean | No auto-execution / 不自動執行 |
| `warnings.contrarian_is_watch_only` | boolean | Contrarian is observation / 逆勢為觀察 |

---

## 7. Signal Processing Rules / 訊號處理規則

### 7.1 Cooldown Rules / 冷卻規則

| Signal Type / 訊號類型 | Cooldown Period / 冷卻期 | Scope / 範圍 |
|------------------------|--------------------------|--------------|
| trend_long | 15 minutes | Per symbol / 每標的 |
| trend_short | 15 minutes | Per symbol / 每標的 |
| contrarian_watch_overheated | 30 minutes | Per symbol+direction / 每標的+方向 |
| contrarian_watch_oversold | 30 minutes | Per symbol+direction / 每標的+方向 |

```python
# Cooldown logic / 冷卻邏輯:
def can_emit_signal(symbol, signal_type):
    key = f"{symbol}:{signal_type}"
    last_time = cooldown_store.get(key, 0)
    cooldown_period = get_cooldown_period(signal_type)
    
    if current_time - last_time > cooldown_period:
        cooldown_store[key] = current_time
        return True
    return False
```

### 7.2 Duplicate Suppression / 重複抑制

| Scenario / 情境 | Action / 行動 |
|-----------------|---------------|
| Same signal within cooldown / 冷卻期內相同訊號 | Suppress / 抑制 |
| Trend signal + Contrarian same bar / 同K線趨勢+逆勢 | Emit both with priority flag / 發送兩者並標示優先級 |
| Multiple symbols same condition / 多標的同條件 | Emit separate alerts / 發送分開提醒 |

### 7.3 Priority Rules / 優先級規則

| Priority / 優先級 | Signal Type / 訊號類型 | Rationale / 理由 |
|-------------------|------------------------|------------------|
| 1 (High) | trend_long, trend_short | Confirmed signals / 確認訊號 |
| 2 (Low) | contrarian_watch | Observation only / 僅觀察 |

---

## 8. Error Handling / 錯誤處理

### 8.1 Signal Generation Errors / 訊號產生錯誤

| Error / 錯誤 | Handling / 處理 | Fallback / 備案 |
|--------------|-----------------|-----------------|
| Insufficient data / 資料不足 | Skip signal, log warning | Wait for next cycle |
| API timeout / API 逾時 | Retry 3x with backoff | Skip and alert admin |
| Calculation error / 計算錯誤 | Log error, skip signal | Manual review needed |

### 8.2 Invalid Signal States / 無效訊號狀態

| State / 狀態 | Condition / 條件 | Action / 行動 |
|--------------|------------------|---------------|
| Partial conditions / 部分條件 | 1-2 of 3 conditions met | Do not emit / 不發送 |
| Stale data / 過期資料 | Data older than 5 minutes | Re-fetch / 重新抓取 |
| Symbol halted / 標的暫停 | No new candles | Skip symbol / 跳過標的 |

---

## 9. Examples / 範例

### 9.1 Example 1: Complete Trend Long / 範例1: 完整順勢做多

```json
{
  "metadata": {
    "version": "1.0.0",
    "system_id": "MONITOR-001",
    "timestamp": "2026-04-05T18:30:00Z"
  },
  "signal": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "trend_long",
    "subtype": null,
    "level": "confirmed",
    "symbol": "BTCUSDT",
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
      }
    }
  },
  "conditions": {
    "c1": true,
    "c2": true,
    "c3": true,
    "all_met": true
  },
  "warnings": {
    "alert_only": true,
    "no_auto_trade": true,
    "contrarian_is_watch_only": false
  }
}
```

### 9.2 Example 2: Contrarian Watch / 範例2: 逆勢觀察

```json
{
  "metadata": {
    "version": "1.0.0",
    "system_id": "MONITOR-001",
    "timestamp": "2026-04-05T18:45:00Z"
  },
  "signal": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "type": "contrarian_watch",
    "subtype": "overheated",
    "level": "watch_only",
    "symbol": "ETHUSDT",
    "timestamp": 1775385900000,
    "timezone": "UTC"
  },
  "market_data": {
    "timeframes": {
      "15m": {
        "pattern": "4_consecutive_red"
      }
    }
  },
  "conditions": {
    "c1": true,
    "all_met": true
  },
  "warnings": {
    "alert_only": true,
    "no_auto_trade": true,
    "contrarian_is_watch_only": true
  }
}
```

---

## 10. Version History / 版本歷史

| Version / 版本 | Date / 日期 | Changes / 變更 |
|----------------|-------------|----------------|
| 1.0.0 | 2026-04-05 | Initial specification / 初始規格 |

---

**Created by**: kimiclaw_bot  
**建立者**: kimiclaw_bot  
**Part of**: T-022 BTC/ETH Monitoring System  
**Date**: 2026-04-05  
**日期**: 2026-04-05
