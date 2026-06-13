# Example Run Output / 執行輸出範例

**⚠️ EXAMPLE ONLY / 僅供範例**  
**This is a demonstration of output format, not actual trading results.**  
**這是輸出格式的示範，不是真實交易結果。**

---

## Run Information / 執行資訊

| Field / 欄位 | Value / 值 |
|--------------|------------|
| Timestamp / 時間戳 | 2026-04-06 11:30:15 UTC |
| Type / 類型 | Single-run monitoring / 單次監測 |
| Symbols / 標的 | BTCUSDT, ETHUSDT |

---

## BTCUSDT Results / BTCUSDT 結果

### Data Fetched / 抓取資料

| Timeframe / 時間框架 | Candles / K 線數 | Status / 狀態 |
|----------------------|------------------|---------------|
| 5m | 250 | ✅ OK |
| 1m | 20 | ✅ OK |
| 15m | 10 | ✅ OK |

### Indicators / 指標

| Indicator / 指標 | Value / 值 |
|------------------|------------|
| Close (5m) | $69,250.50 |
| MA5 | $69,180.25 |
| MA20 | $69,050.00 |
| MA240 | $68,500.75 |
| Volume (1m) | 12.50 BTC |
| Volume Avg | 5.20 BTC |
| Volume Ratio | 2.40x |

### Signals / 訊號

#### Signal 1: trend_long (CONFIRMED)

```
╔══════════════════════════════════════════════════════════════════╗
║ 📈 TREND LONG ✅ CONFIRMED                                       ║
╠══════════════════════════════════════════════════════════════════╣
║ Symbol: BTCUSDT                                                  ║
║ Time: 2026-04-06 11:30:15                                        ║
╠══════════════════════════════════════════════════════════════════╣
║ Price Data:                                                      ║
║   Close (5m): $69,250.50                                         ║
║   MA5: $69,180.25                                                ║
║   MA20: $69,050.00                                               ║
║   MA240: $68,500.75                                              ║
║   Volume Ratio: 2.40x                                            ║
╠══════════════════════════════════════════════════════════════════╣
║ Conditions Met:                                                  ║
║   ✅ close > MA240                                               ║
║   ✅ MA5 crossed above MA20                                      ║
║   ✅ volume > 2x average                                         ║
╠══════════════════════════════════════════════════════════════════╣
║ Reason: BTCUSDT: close > MA240, MA5 crossed above MA20,          ║
║         volume 2.4x average                                      ║
╠══════════════════════════════════════════════════════════════════╣
║ ⚠️  ALERT_ONLY_NO_AUTO_TRADE                                     ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## ETHUSDT Results / ETHUSDT 結果

### Data Fetched / 抓取資料

| Timeframe / 時間框架 | Candles / K 線數 | Status / 狀態 |
|----------------------|------------------|---------------|
| 5m | 250 | ✅ OK |
| 1m | 20 | ✅ OK |
| 15m | 10 | ✅ OK |

### Indicators / 指標

| Indicator / 指標 | Value / 值 |
|------------------|------------|
| Close (5m) | $3,520.75 |
| MA5 | $3,540.20 |
| MA20 | $3,580.50 |
| MA240 | $3,620.00 |
| Volume Ratio | 1.20x |

### Signals / 訊號

#### Signal 1: contrarian_watch_oversold (WATCH ONLY)

```
╔══════════════════════════════════════════════════════════════════╗
║ ❄️ CONTRARIAN WATCH 👁️ WATCH ONLY                                ║
╠══════════════════════════════════════════════════════════════════╣
║ Symbol: ETHUSDT                                                  ║
║ Time: 2026-04-06 11:30:15                                        ║
╠══════════════════════════════════════════════════════════════════╣
║ Pattern Data:                                                    ║
║   Timeframe: 15m                                                 ║
║   Pattern: oversold                                              ║
║   Consecutive Count: 4                                           ║
╠══════════════════════════════════════════════════════════════════╣
║ Reason: ETHUSDT 15m: 4 consecutive green candles -               ║
║         potential reversal zone                                  ║
╠══════════════════════════════════════════════════════════════════╣
║ ⚠️  WATCH_ONLY_NOT_EXECUTION_SIGNAL                              ║
╚══════════════════════════════════════════════════════════════════╝
```

**Note / 注意**:  
This is a **WATCH ONLY** signal, not an execution signal.  
這是 **僅觀察** 訊號，非執行訊號。

---

## Run Summary / 執行摘要

```
======================================================================
RUN SUMMARY / 執行摘要
======================================================================
Timestamp: 2026-04-06 11:30:15
Total Symbols: 2
  ✓ Successful: 2
  ✗ Failed: 0

Signals Generated / 產生的訊號:
  Total: 2
  ✅ Confirmed: 1
  👁️  Watch Only: 1

Symbols with Signals / 有訊號的標的:
  - BTCUSDT (1 confirmed)
  - ETHUSDT (1 watch only)

======================================================================
⚠️  REMINDER / 提醒:
   All signals are ALERT ONLY.
   所有訊號皆為僅提醒。
   No automatic trading is performed.
   不執行自動交易。
======================================================================
```

---

## JSON Output Format / JSON 輸出格式

```json
{
  "run_timestamp": 1775385015000,
  "summary": {
    "total_symbols": 2,
    "successful_symbols": 2,
    "failed_symbols": 0,
    "total_signals": 2,
    "confirmed_count": 1,
    "watch_only_count": 1,
    "symbols_with_signals": ["BTCUSDT", "ETHUSDT"]
  },
  "results": [
    {
      "symbol": "BTCUSDT",
      "timestamp": 1775385015000,
      "success": true,
      "indicators": {
        "close_5m": 69250.50,
        "ma5": 69180.25,
        "ma20": 69050.00,
        "ma240": 68500.75,
        "volume_ratio": 2.40
      },
      "signals": [
        {
          "signal_type": "trend_long",
          "level": "confirmed",
          "symbol": "BTCUSDT",
          "timestamp": 1775385015000,
          "price_data": {
            "close_5m": 69250.50,
            "ma5": 69180.25,
            "ma20": 69050.00,
            "ma240": 68500.75,
            "volume_ratio": 2.40
          },
          "conditions": {
            "c1_above_ma240": true,
            "c2_ma_cross_above": true,
            "c3_volume_spike": true
          },
          "reason": "BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.4x average",
          "warning": "ALERT_ONLY_NO_AUTO_TRADE"
        }
      ]
    },
    {
      "symbol": "ETHUSDT",
      "timestamp": 1775385015000,
      "success": true,
      "indicators": {
        "close_5m": 3520.75,
        "ma5": 3540.20,
        "ma20": 3580.50,
        "ma240": 3620.00,
        "volume_ratio": 1.20
      },
      "signals": [
        {
          "signal_type": "contrarian_watch_oversold",
          "level": "watch_only",
          "symbol": "ETHUSDT",
          "timestamp": 1775385015000,
          "price_data": {
            "timeframe": "15m",
            "pattern": "oversold",
            "consecutive_count": 4
          },
          "conditions": {
            "pattern_detected": true
          },
          "reason": "ETHUSDT 15m: 4 consecutive green candles - potential reversal zone",
          "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
        }
      ]
    }
  ]
}
```

---

## Important Notes / 重要說明

### ⚠️ EXAMPLE ONLY / 僅供範例

```
╔══════════════════════════════════════════════════════════════════╗
║  THIS IS AN EXAMPLE OUTPUT                                       ║
║  這是範例輸出                                                     ║
║                                                                  ║
║  • Not actual trading results / 不是真實交易結果                   ║
║  • Demonstrates format only / 僅示範格式                          ║
║  • Prices are illustrative / 價格僅供說明                         ║
║  • Real output depends on market conditions                       ║
║    真實輸出取決於市場狀況                                          ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ ALERT ONLY / 僅提醒

```
╔══════════════════════════════════════════════════════════════════╗
║  ALERT ONLY - NO AUTO TRADING                                    ║
║  僅提醒 - 無自動交易                                               ║
║                                                                  ║
║  • Generates alerts only / 僅產生提醒                              ║
║  • Requires human review / 需要人工審查                            ║
║  • Not investment advice / 非投資建議                              ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ WATCH ONLY SIGNALS / 僅觀察訊號

```
╔══════════════════════════════════════════════════════════════════╗
║  CONTRARIAN_WATCH SIGNALS ARE WATCH ONLY                         ║
║  CONTRARIAN_WATCH 訊號僅供觀察                                     ║
║                                                                  ║
║  • NOT execution signals / 不是執行訊號                            ║
║  • NOT trade recommendations / 不是交易建議                        ║
║  • For observation only / 僅供觀察                                 ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Version / 版本

- Example Version: 1.0.0
- Created: 2026-04-06
- For: BTC/ETH Monitoring System
