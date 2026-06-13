# Strategy Auto-Discovery System / 策略自動發現系統

## Overview / 概述

This document describes the full automated strategy discovery pipeline.
No trading knowledge required — the system discovers, backtests, and deploys
strategies automatically.

本文件描述完整的自動化策略發現 pipeline。
不需要交易知識 — 系統自動發現、回測、部署策略。

---

## Architecture / 架構

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Condition Lib  │────▶│ StrategyComposer │────▶│  strategies.json│
│  (30+ checks)   │     │  (組合條件)       │     │  (disabled)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                           │
┌─────────────────┐     ┌──────────────────┐              │
│ BacktestPipeline│◀────│ StrategyGenerator│◀─────────────┘
│   (回測評分)     │     │  (參數優化)       │
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  Score & Filter │────▶│  Enable Winners  │────▶ Paper Trading
│  (評分篩選)      │     │  (啟用勝出者)     │       (紙上交易)
└─────────────────┘     └──────────────────┘
```

---

## Condition Library / 條件庫

All conditions are in `strategy_conditions.py`. They fall into categories:

| Category | Conditions | Purpose |
|----------|-----------|---------|
| **趨勢確認** | `ema_cross_above`, `price_above_trend`, `supertrend`, `adx_above_20/25`, `close_above_ma240` | 確認趨勢方向 |
| **趨勢做空** | `ema_cross_below`, `close_below_ma240` | 確認下跌趨勢 |
| **動量/突破** | `volume_spike`, `volume_ema_spike`, `price_above_20period_high`, `consecutive_green`, `keltner_breakout`, `atr_breakout` | 價格/成交量爆發 |
| **超賣** | `rsi_below_30`, `rsi_cross_above_30`, `williams_r`, `fastk_below_20`, `price_below_bb_lower`, `price_below_bb_lower_pct` | 跌太多，可能反彈 |
| **超買過濾** | `rsi_not_overbought`, `rsi_in_range` | 避免買在最高點 |
| **波動過濾** | `atr_below_threshold`, `close_vs_ma240` | 過濾極端波動 |
| **背離** | `bullish_divergence_rsi` | 指標背離訊號 |

---

## Strategy Archetypes / 策略原型

### 1. Trend Following (順勢跟隨)
- **Logic**: 趨勢確認 + 動量確認 + 過濾
- **Example**: `ema_cross_above` + `volume_ema_spike` + `adx_above_20`
- **When it works**: 市場有明確方向時

### 2. Mean Reversion (均值回歸)
- **Logic**: 超賣訊號 + 趨勢/過濾
- **Example**: `price_below_bb_lower_pct` + `rsi_below_30` + `adx_above_20`
- **When it works**: 市場震盪、有支撐時

### 3. Momentum Breakout (動量突破)
- **Logic**: 成交量爆發 + 價格突破 + 趨勢
- **Example**: `volume_ema_spike` + `price_above_20period_high` + `rsi_not_overbought`
- **When it works**: 新聞/事件驅動的價格跳升

### 4. Reversal (反轉)
- **Logic**: 背離 + 超賣
- **Example**: `bullish_divergence_rsi` + `rsi_cross_above_30`
- **When it works**: 趨勢末期的反轉

### 5. Composite (複合投票)
- **Logic**: 多個條件同時滿足
- **Example**: `ema_cross_above` + `volume_confirmed` + `rsi_in_range` + `adx_above_20`
- **When it works**: 需要高確信度時

---

## Auto-Discovery Pipeline / 自動發現流程

### Phase 1: Compose / 合成
```python
composer = StrategyComposer()
strategies = composer.compose_all(max_per_archetype=20)
# Generates ~100 strategies from condition combinations
```

### Phase 2: Parameter Variations / 參數變體
```python
generator = StrategyGenerator()
for strategy in strategies:
    variations = generator.generate_variations(strategy, count=5)
# Each strategy gets 5 parameter sets
```

### Phase 3: Backtest / 回測
```python
pipeline = BacktestPipeline()
for variation in variations:
    result = pipeline.run_backtest(variation, historical_data)
# Run all through backtest
```

### Phase 4: Score & Filter / 評分篩選

**Scoring Criteria (評分標準)**:

| Metric | Threshold | Weight |
|--------|-----------|--------|
| Profit Factor | > 1.3 | 30% |
| Sharpe Ratio | > 0.5 | 30% |
| Win Rate | > 45% | 20% |
| Max Drawdown | < 15% | -20% |
| Total Trades | > 20 | Required |

**Composite Score**:
```
score = pf * 0.3 + sharpe * 0.3 + (win_rate/100) * 0.2 - (max_dd/100) * 0.2
```

### Phase 5: Enable Winners / 啟用勝出者
- Top 5-10 strategies by score get `enabled: true`
- Added to paper trading
- Monitored for 1-2 weeks
- If paper trading profitable → consider live

---

## Usage / 使用方法

### Quick Start
```python
from app.strategy_composer import StrategyDiscoveryEngine

engine = StrategyDiscoveryEngine()

# Full discovery pipeline
results = engine.discover(
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=["5m"],
    backtest_days=30,
    max_strategies=50,
    max_variations_per_strategy=3,
)

print(f"Found {len(results)} viable strategies")
for r in results[:10]:
    print(f"  {r.strategy_id}: score={r.score:.2f}")
```

### Manual Composition
```python
from app.strategy_composer import StrategyComposer

composer = StrategyComposer()

# See what's possible
stats = composer.get_composition_stats()
print(stats)

# Compose strategies
strategies = composer.compose_all(max_per_archetype=10)

# Export to strategies.json (all disabled, awaiting backtest)
composer.export_to_strategies_json(
    strategies,
    "config/strategies_auto.json"
)
```

### Integration with Existing System
```python
# Merge auto-composed with existing strategies
composer.export_to_strategies_json(
    strategies,
    "config/strategies.json",
    merge_with_existing="config/strategies.json"
)
```

---

## Scheduling / 排程建議

**Weekly Discovery Run**:
```bash
# Run every Sunday night
python -m app.strategy_discovery --symbols BTCUSDT,ETHUSDT \
    --timeframes 5m --backtest-days 60 --max-strategies 100
```

**Daily Evaluation**:
```bash
# Check paper trading results of enabled auto-strategies
python -m app.strategy_ranking --auto-only --min-days 7
```

---

## Risk Controls / 風控

1. **All auto-strategies start DISABLED** — require backtest validation
2. **Paper trading gate** —至少 1 周紙上交易表現良好
3. **Capital limits** — 自動策略最多使用 20% 倉位
4. **Auto-disable on drawdown** — 回撤超過 10% 自動停用
5. **Diversity requirement** — 啟用的策略必須覆蓋不同 archetypes

---

## Files / 相關檔案

| File | Purpose |
|------|---------|
| `app/strategy_conditions.py` | 條件檢查庫 (30+ 條件) |
| `app/strategy_composer.py` | 策略合成器 + 發現引擎 |
| `app/strategy_generator.py` | 參數生成/優化 |
| `app/backtest_pipeline.py` | 回測 pipeline |
| `app/strategy_executor.py` | 策略執行器 |
| `config/strategies.json` | 策略配置檔 |

---

## Notes / 注意事項

- **Overfitting risk**: 自動發現有過度擬合風險。永遠使用 out-of-sample 回測。
- **Market regime dependency**: 策略可能在某些市場環境失效。監控勝率變化。
- **Transaction costs**: 回測要包含手續費/滑價，否則高頻策略看起來很好，實盤虧錢。
- **Start small**: 自動策略先小資金測試，不要直接上大倉位。

---

*Last updated: 2026-05-19*
