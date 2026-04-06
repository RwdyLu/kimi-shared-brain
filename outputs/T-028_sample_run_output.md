# T-028 Sample Run Output / 範例執行輸出

**⚠️ EXAMPLE / TEST OUTPUT ONLY / 僅供範例/測試輸出**  
**This is a sanitized test output from T-028 validation / 這是來自 T-028 驗證的 sanitized 測試輸出**  
**Not actual trading results / 非真實交易結果**

---

## Run Information / 執行資訊

| Field / 欄位 | Value / 值 |
|--------------|------------|
| Task ID | T-028 |
| Run Type | Local Validation / 本地驗證 |
| Timestamp | 2026-04-06 21:45:00 UTC |
| Environment | Local test environment |

---

## BTCUSDT Results / BTCUSDT 結果

### Step 1: Data Fetch / 步驟 1：資料抓取

```
[1/4] Fetching data...
    ✓ 5m: 250 candles fetched
    ✓ 1m: 20 candles fetched
    ✓ 15m: 10 candles fetched
```

### Step 2: Indicator Calculation / 步驟 2：指標計算

```
[2/4] Calculating indicators...
    ✓ MA5: 69,385.00
    ✓ MA20: 69,428.46
    ✓ MA240: 68,805.06
    ✓ Volume Ratio: 0.41x (no spike)
```

**Indicator Values / 指標值**:

| Indicator | Value | Note |
|-----------|-------|------|
| Close (5m) | $69,299.13 | Latest price |
| MA5 | $69,385.00 | Short-term trend |
| MA20 | $69,428.46 | Medium-term trend |
| MA240 | $68,805.06 | Long-term trend |
| Volume (1m) | 54.22 BTC | Current volume |
| Volume Avg | 51.16 BTC | 20-period average |
| Volume Ratio | 1.06x | Below 2x threshold |

**Analysis / 分析**:
- Price above MA240: ✅ (bullish long-term)
- MA5 < MA20: ❌ (no golden cross)
- Volume spike: ❌ (1.06x < 2x)
- **Result**: No trend_long signal generated (MA cross condition not met)

### Step 3: Signal Generation / 步驟 3：訊號產生

```
[3/4] Generating signals...
    ✓ Total signals: 0
    ✓ Confirmed: 0
    ✓ Watch Only: 0
```

**Signal Analysis / 訊號分析**:

| Signal Type | Condition Met | Status |
|-------------|---------------|--------|
| trend_long | close > MA240: ✅, MA5 cross MA20: ❌, volume > 2x: ❌ | Not generated |
| trend_short | close < MA240: ❌ | Not generated |
| contrarian_watch | 4 consecutive candles: ❌ | Not generated |

### Step 4: Notification / 步驟 4：通知

```
[4/4] Outputting notifications...
    - No signals to notify
```

---

## ETHUSDT Results / ETHUSDT 結果

### Data Summary / 資料摘要

```
Fetching data...
    ✓ 5m: 250 candles
    ✓ 1m: 20 candles
    ✓ 15m: 10 candles

Calculating indicators...
    ✓ MA5: 3,520.75
    ✓ MA20: 3,545.20
    ✓ MA240: 3,480.50
    ✓ Volume Ratio: 0.85x

Signals: 0 (no conditions met)
```

---

## Run Summary / 執行摘要

```
======================================================================
RUN SUMMARY / 執行摘要
======================================================================
Timestamp: 2026-04-06 21:45:00
Total Symbols: 2
  ✓ Successful: 2
  ✗ Failed: 0

Signals Generated / 產生的訊號:
  Total: 0
  ✅ Confirmed: 0
  👁️  Watch Only: 0

Symbols with Signals / 有訊號的標的:
  (none)

======================================================================
⚠️  REMINDER / 提醒:
   All signals are ALERT ONLY.
   所有訊號皆為僅提醒。
   No automatic trading is performed.
   不執行自動交易。
======================================================================
```

---

## Example Signal Payload (Mock) / 範例訊號 Payload（模擬）

**This is what a signal would look like if conditions were met:**

### trend_long (CONFIRMED)

```json
{
  "signal_type": "trend_long",
  "level": "confirmed",
  "symbol": "BTCUSDT",
  "timestamp": 1775486700000,
  "price_data": {
    "close_5m": 70250.00,
    "ma5": 70180.00,
    "ma20": 70050.00,
    "ma240": 69500.00,
    "volume_1m": 125.50,
    "volume_avg_1m": 50.00,
    "volume_ratio": 2.51
  },
  "conditions": {
    "c1_above_ma240": true,
    "c2_ma_cross_above": true,
    "c3_volume_spike": true
  },
  "reason": "BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.51x average",
  "warning": "ALERT_ONLY_NO_AUTO_TRADE"
}
```

### contrarian_watch_overheated (WATCH ONLY)

```json
{
  "signal_type": "contrarian_watch_overheated",
  "level": "watch_only",
  "symbol": "ETHUSDT",
  "timestamp": 1775486700000,
  "price_data": {
    "timeframe": "15m",
    "pattern": "overheated",
    "consecutive_count": 4
  },
  "conditions": {
    "pattern_detected": true
  },
  "reason": "ETHUSDT 15m: 4 consecutive red candles - potential reversal zone",
  "warning": "WATCH_ONLY_NOT_EXECUTION_SIGNAL"
}
```

**⚠️ IMPORTANT**: This contrarian signal is **WATCH ONLY**, not an execution signal.

---

## Example Notification Output (Mock) / 範例通知輸出（模擬）

```
==================================================
ALERT: 📈 TREND LONG ✅ CONFIRMED
==================================================
Symbol: BTCUSDT
Time: 2026-04-06 21:45:00

Price Data / 價格資料:
  Close (5m): 70,250.00
  MA5: 70,180.00
  MA20: 70,050.00
  MA240: 69,500.00
  Volume (1m): 125.50
  Volume Ratio: 2.51x

Conditions Met / 條件滿足:
  ✅ c1_above_ma240
  ✅ c2_ma_cross_above
  ✅ c3_volume_spike

Reason / 原因: BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.51x average

⚠️  ALERT_ONLY_NO_AUTO_TRADE

==================================================
```

---

## Compact Format Example / 緊湊格式範例

```
[BTCUSDT] 📈 TREND LONG @ 70,250.00 | ✅ CONFIRMED | ALERT_ONLY_NO_AUTO_TRADE
[ETHUSDT] 🔥 CONTRARIAN WATCH @ 3,520.00 | 👁️ WATCH ONLY | WATCH_ONLY_NOT_EXECUTION_SIGNAL
```

---

## JSON Output Format / JSON 輸出格式

```json
{
  "run_timestamp": 1775486700000,
  "summary": {
    "total_symbols": 2,
    "successful_symbols": 2,
    "failed_symbols": 0,
    "total_signals": 1,
    "confirmed_count": 1,
    "watch_only_count": 0,
    "symbols_with_signals": ["BTCUSDT"]
  },
  "results": [
    {
      "symbol": "BTCUSDT",
      "timestamp": 1775486700000,
      "success": true,
      "indicators": {
        "close_5m": 70250.00,
        "ma5": 70180.00,
        "ma20": 70050.00,
        "ma240": 69500.00,
        "volume_ratio": 2.51
      },
      "signals": [
        {
          "signal_type": "trend_long",
          "level": "confirmed",
          "symbol": "BTCUSDT",
          "timestamp": 1775486700000,
          "price_data": {
            "close_5m": 70250.00,
            "ma5": 70180.00,
            "ma20": 70050.00,
            "ma240": 69500.00,
            "volume_ratio": 2.51
          },
          "conditions": {
            "c1_above_ma240": true,
            "c2_ma_cross_above": true,
            "c3_volume_spike": true
          },
          "reason": "BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.51x average",
          "warning": "ALERT_ONLY_NO_AUTO_TRADE"
        }
      ]
    },
    {
      "symbol": "ETHUSDT",
      "timestamp": 1775486700000,
      "success": true,
      "indicators": {
        "close_5m": 3520.00,
        "ma5": 3510.00,
        "ma20": 3545.00,
        "ma240": 3480.00,
        "volume_ratio": 0.85
      },
      "signals": []
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
║  • Generated during T-028 validation / T-028 驗證期間產生          ║
║  • Prices are from test run / 價格來自測試執行                     ║
║  • May not reflect current market / 可能不反映當前市場              ║
║  • For format demonstration only / 僅供格式示範                    ║
╚══════════════════════════════════════════════════════════════════╝
```

### ⚠️ ALERT ONLY / 僅提醒

```
╔══════════════════════════════════════════════════════════════════╗
║  ALERT ONLY - NO AUTO TRADING                                    ║
║  僅提醒 - 無自動交易                                               ║
║                                                                  ║
║  • This system generates alerts only / 本系統僅產生提醒             ║
║  • No orders are executed / 不執行訂單                             ║
║  • Human review required / 需要人工審查                            ║
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
║  • Require additional confirmation / 需要額外確認                   ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## Test Environment Details / 測試環境詳情

| Component | Version/Status |
|-----------|----------------|
| Python | 3.x |
| data.fetcher | ✅ Working |
| indicators.calculator | ✅ Working |
| signals.engine | ✅ Working |
| notifications.formatter | ✅ Working |
| notifications.notifier | ✅ Working |
| app.monitor_runner | ✅ Working (after fixes) |

---

**Generated**: 2026-04-06  
**Task**: T-028 Local Validation  
**Status**: Test output / 測試輸出
