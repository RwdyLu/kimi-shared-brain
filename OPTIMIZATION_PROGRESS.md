# 優化進度追蹤 / Optimization Progress

## 2026-05-18 Session

### ✅ Completed

1. **trade_executor.py** — 全面重寫止盈止损
   - 硬止損: -3% → -5%
   - 新增階梯ROI止盈 (0min: 5% → 240min: 0.5%)
   - 新增移動止损 (profit ≥ 3% 後, 回撤 2% 出場)
   - 新增 ATR 動態止损 (1.5×ATR)
   - 策略專屬參數覆蓋

2. **indicators/calculator.py** — 新增 calculate_adx()
   - ADX 趨勢強度指標計算

3. **monitor_runner.py** — 指標層擴展
   - SymbolResult 新增: atr14, adx14, volume_ema20, lows
   - _calculate_indicators 計算並填充新指標

4. **scheduler.py** — 指標傳遞
   - 傳遞 atr14, adx14, volume_ema20 給 trade_executor

### ⏳ In Progress

5. **strategy_conditions.py** — 增加新條件
   - _check_adx_above_25 (趨勢過濾)
   - _check_atr_below_threshold (低波動過濾)
   - _check_volume_ema_spike (Strategy005風格成交量)

6. **strategies.json** — 精簡策略
   - 只保留 4-6 個策略
   - 每個至少 3 個確認條件
   - 加入 ADX 過濾
   - 新增 cluc_bounce, supertrend_trend

7. **paper_trading.py** — 倉位管理
   - position_pct: 0.1 → 0.15
   - 減少交易頻率

### 🔧 Key Insight

系統虧損的核心原因不是策略邏輯錯，而是：
- 止損太緊 (-3% 在 5m K 線上太容易觸發)
- 止盈太低 (1.5-2.5% 被手續費吃掉)
- 沒有移動止损 (利潤拿不住)
- 交易太頻繁 (297筆 MA交叉 = $65 手續費)
- 沒有趨勢過濾 (橫盤市場反覆被打臉)

修正後的框架: 1:2 盈虧比 + 減少交易次數 + 趨勢過濾
