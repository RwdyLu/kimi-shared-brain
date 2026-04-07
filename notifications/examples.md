# Notification Examples / 提醒範例

**Version**: 1.1.0  
**Updated**: 2026-04-07

This document shows example notifications in different formats.

本文檔展示不同格式的提醒範例。

---

## Chinese Readable Format (New) / 中文可讀格式（新增）

### 📈 順勢做多提醒

```
📈 **順勢做多提醒** 📈

```
標的:     BTCUSDT
價格:     69,250.50 （量比 2.4x）
狀態:     ✅ 已確認訊號
```

**📋 說明**: 價格突破均線，成交量放大，可能開啟上漲趨勢

**🔍 觸發條件**:
  ✅ 價格在 MA240 之上
  ✅ MA5 上穿 MA20（黃金交叉）
  ✅ 成交量放大（超過均量）

**💡 建議**: 可考慮順勢做多，設定止損

🕐 **UTC**: 2026-04-07 10:09:00 UTC
🕐 **本地**: 2026-04-07 18:09:00 CST

> ⚠️ **僅供提醒，不會自動下單**
```

---

### 📉 順勢做空提醒

```
📉 **順勢做空提醒** 📉

```
標的:     ETHUSDT
價格:     2,124.05 （量比 1.8x）
狀態:     ✅ 已確認訊號
```

**📋 說明**: 價格跌破均線，成交量放大，可能開啟下跌趨勢

**🔍 觸發條件**:
  ✅ 價格在 MA240 之下
  ✅ MA5 下穿 MA20（死亡交叉）
  ✅ 成交量放大（超過均量）

**💡 建議**: 可考慮順勢做空，設定止損

🕐 **UTC**: 2026-04-07 10:15:00 UTC
🕐 **本地**: 2026-04-07 18:15:00 CST

> ⚠️ **僅供提醒，不會自動下單**
```

---

### 🔥 逆勢觀察：過熱

```
🔥 **逆勢觀察：過熱** 🔥

```
標的:     BTCUSDT
價格:     71,500.00
狀態:     👁️ 僅供觀察
```

**📋 說明**: 連續上漲後出現過熱訊號，可能面臨回調

**🔍 觸發條件**:
  ✅ 連續四根紅 K（上漲）
  ✅ 價格在 MA240 之上

**💡 建議**: 僅供觀察，等待確認訊號，不要追多

🕐 **UTC**: 2026-04-07 10:20:00 UTC
🕐 **本地**: 2026-04-07 18:20:00 CST

> ⚠️ **僅供提醒，不會自動下單**
>
> 👁️ **僅供觀察，不是進場訊號**
```

---

### ❄️ 逆勢觀察：超跌

```
❄️ **逆勢觀察：超跌** ❄️

```
標的:     ETHUSDT
價格:     1,980.00
狀態:     👁️ 僅供觀察
```

**📋 說明**: 連續下跌後出現超跌訊號，可能面臨反彈

**🔍 觸發條件**:
  ✅ 連續四根綠 K（下跌）
  ✅ 價格在 MA240 之下

**💡 建議**: 僅供觀察，等待確認訊號，不要追空

🕐 **UTC**: 2026-04-07 10:25:00 UTC
🕐 **本地**: 2026-04-07 18:25:00 CST

> ⚠️ **僅供提醒，不會自動下單**
>
> 👁️ **僅供觀察，不是進場訊號**
```

---

## Format Comparison / 格式比較

### Traditional Format / 傳統格式

```
==================================================
提醒: 📈 順勢做多 ✅ 已確認
==================================================
標的: BTCUSDT
時間: 2026-04-07 10:09:00 UTC / 2026-04-07 18:09:00 CST

價格資料:
  收盤價 (5m): 69,250.50
  MA5: 69,180.25
  MA20: 69,050.00
  MA240: 68,500.75
  成交量 (1m): 12.50
  量比: 2.40x

條件滿足:
  ✅ c1_above_ma240
  ✅ c2_ma_cross_above
  ✅ c3_volume_spike

原因: BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.4x average

⚠️  ALERT_ONLY_NO_AUTO_TRADE

==================================================
```

### Chinese Readable Format / 中文可讀格式

```
📈 **順勢做多提醒** 📈

```
標的:     BTCUSDT
價格:     69,250.50 （量比 2.4x）
狀態:     ✅ 已確認訊號
```

**📋 說明**: 價格突破均線，成交量放大，可能開啟上漲趨勢

**🔍 觸發條件**:
  ✅ 價格在 MA240 之上
  ✅ MA5 上穿 MA20（黃金交叉）
  ✅ 成交量放大（超過均量）

**💡 建議**: 可考慮順勢做多，設定止損

🕐 **UTC**: 2026-04-07 10:09:00 UTC
🕐 **本地**: 2026-04-07 18:09:00 CST

> ⚠️ **僅供提醒，不會自動下單**
```

---

## Usage / 使用方法

```python
from notifications.formatter import NotificationFormatter
from signals.engine import Signal, SignalType, SignalLevel

# Create formatter for Chinese readable format
formatter = NotificationFormatter(language="zh")

# Format signal
alert = formatter.format_chinese_readable(signal)

# Send to Discord (or other channels)
print(alert)
```

---

## Key Improvements / 主要改進

| Aspect | Traditional | Chinese Readable |
|--------|-------------|------------------|
| **Signal Name** | `📈 順勢做多` | `📈 **順勢做多提醒** 📈` |
| **Status** | `✅ 已確認` | Code block with clear status |
| **Conditions** | Technical codes | Translated Chinese descriptions |
| **Action** | None | Clear action recommendation |
| **Warning** | `ALERT_ONLY_NO_AUTO_TRADE` | `⚠️ **僅供提醒，不會自動下單**` |
| **Readability** | Requires context | Immediately understandable |

---

## Translation Reference / 翻譯對照

| English Code | Chinese Translation |
|--------------|---------------------|
| trend_long | 順勢做多提醒 |
| trend_short | 順勢做空提醒 |
| contrarian_watch_overheated | 逆勢觀察：過熱 |
| contrarian_watch_oversold | 逆勢觀察：超跌 |
| CONFIRMED | ✅ 已確認訊號 |
| WATCH_ONLY | 👁️ 僅供觀察 |
| ALERT_ONLY_NO_AUTO_TRADE | ⚠️ 僅供提醒，不會自動下單 |
| WATCH_ONLY_NOT_EXECUTION_SIGNAL | 👁️ 僅供觀察，不是進場訊號 |

### Condition Translations / 條件翻譯

| Code | Chinese |
|------|---------|
| c1_above_ma240 | 價格在 MA240 之上 |
| c1_below_ma240 | 價格在 MA240 之下 |
| c2_ma_cross_above | MA5 上穿 MA20（黃金交叉） |
| c2_ma_cross_below | MA5 下穿 MA20（死亡交叉） |
| c3_volume_spike | 成交量放大（超過均量） |
| c4_four_red_candles | 連續四根紅 K（上漲） |
| c4_four_green_candles | 連續四根綠 K（下跌） |

---

**Format Version**: 1.1.0  
**Compatible With**: notifications/formatter.py v1.1.0+
