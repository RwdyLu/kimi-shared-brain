# GA Gene Schema Audit & DNA Expansion Plan

**Phase F — Gene Schema Audit / DNA Expansion Plan**
**Phase G1/G2 — Dead Gene Activation (updated)**
**Branch:** `fix/ga-evolution-automation`
**Audited commit:** `93e3bcd` | **G1/G2 commit:** `be13225` (off-by-one fixed in verification)
**Date:** 2026-06-16

---

## 1. Gene Schema Overview

`StrategyChromosomeV2` 由五大基因塊組成：

| Block | Class | Source File |
|-------|-------|-------------|
| macro_genes | `MacroGenes` | `app/genetic_engine/chromosome_v2.py` |
| micro_genes | `MicroGenes` | `app/genetic_engine/chromosome_v2.py` |
| risk_genes | `RiskGenesV2` | `app/genetic_engine/chromosome_v2.py` |
| entry_genes / exit_genes | `List[IndicatorGene]` | `app/genetic_engine/gene_library.py` |
| environment / season | `Environment`, `SeasonConfig` | `app/genetic_engine/environment.py` |

---

## 2. 完整 Gene 清單

### 2.1 macro_genes（MacroGenes）

| gene | type | range/default | mutates | crosses_over | used_in_backtest | used_in_fitness | notes |
|------|------|---------------|---------|--------------|-----------------|----------------|-------|
| t_macro | int | [1,100] / 20 | ✅ | ✅（繼承較好父） | ✅（DCA warmup窗口） | 間接（影響交易數） | ACTIVE_EVOLUTION_FIELDS |
| t_micro | int | [1,30] / 5 | ✅ | ✅ | ✅（DCA引擎窗口） | 間接 | ACTIVE_EVOLUTION_FIELDS |
| t_deadline | int | [1,12] / 3 | ✅ | ✅ | ✅（耐心耗盡觸發） | 間接 | ACTIVE_EVOLUTION_FIELDS |
| dca_interval | int | [1,200] / 24 | ✅ | ✅ | ✅（DCA週期） | 間接 | ACTIVE_EVOLUTION_FIELDS |
| hold_period | int | [5,500] / 48 | ✅ | ✅ | ✅（強制出場K線數） | 間接 | ACTIVE_EVOLUTION_FIELDS |
| recycle_ratio | float | [0,0.5] / 0.20 | ✅ | ✅ | ✅（利潤再投入比例） | 間接 | ACTIVE_EVOLUTION_FIELDS |
| target_weight | float | [0.1,0.9] / 0.50 | ✅ | ✅ | ✅（kp/kv/ka PDE目標倉位） | 間接 | ACTIVE_EVOLUTION_FIELDS |
| max_dca_months | int | default 12 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |
| beta_threshold | float | default 0.10 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |
| moon_phase_pressure | float | default 1.0 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |
| deadline_force_pct | float | default 0.30 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |
| gc_threshold_months | int | default 6 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |
| gc_max_ratio | float | default 0.50 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |
| ema_anchor | int | default 50 | ❌ | ❌ | ❌ | ❌ | **DEAD GENE** — Legacy field |

> ACTIVE_EVOLUTION_FIELDS 明確定義為 `(t_macro, t_micro, t_deadline, dca_interval, hold_period, recycle_ratio, target_weight)`

### 2.2 micro_genes（MicroGenes）

| gene | type | range/default | mutates | crosses_over | used_in_backtest | used_in_fitness | notes |
|------|------|---------------|---------|--------------|-----------------|----------------|-------|
| kp | float | [0.05,0.90] / 0.5 | ✅ | ✅（感知段正交） | ✅（PDE公式） | ✅（影響交易數/Sharpe） | 歸一化：kp+kv+ka=1 |
| kv | float | [0.05,0.90] / 0.3 | ✅ | ✅（感知段正交） | ✅（PDE公式） | ✅ | 歸一化 |
| ka | float | [0.05,0.90] / 0.2 | ✅（由差補） | ✅（開火段正交） | ✅（PDE公式） | ✅ | 歸一化 |
| min_trade_threshold | float | [0.001,0.20] / 0.02 | ✅ | ✅（開火段正交） | ✅（skip_trade條件） | ✅（影響交易數） | 關鍵基因 |
| micro_reserve_rate | float | [0.02,0.50] / 0.15 | ✅ | ✅（平均） | ✅（float賣出比例） | 間接 | |
| sigmoid_scale | float | [0.1,10.0] / 1.0 | ✅ | ✅（平均） | ✅（進場信號縮放） | ✅（影響倉位大小） | Stage 4 |
| gamma | float | [0.1,5.0] / 0.95 | ✅ | ✅（平均） | ✅（風險厭惡指數） | ✅（影響倉位大小） | Stage 4 |
| beta | float | [0.0,1.0] / 0.5 | ✅ | ✅（平均） | ✅（出場激進程度） | 間接 | Stage 4 |

### 2.3 risk_genes（RiskGenesV2）

| gene | type | range/default | mutates | crosses_over | used_in_backtest | used_in_fitness | notes |
|------|------|---------------|---------|--------------|-----------------|----------------|-------|
| stop_loss_pct | float | [-0.15,-0.02] / -0.05 | ✅（via chromosome.py） | ✅（平均） | ✅（止損觸發） | ✅（影響max_drawdown） | |
| take_profit_pct | float | [0.03,0.15] / 0.08 | ✅ | ✅ | ✅（止盈觸發） | ✅ | |
| position_pct | float | [0.05,0.25] / 0.15 | ✅ | ✅ | ✅（倉位大小） | ✅ | |
| max_hold_bars | int | [36,288] / 72 | ✅ | ✅ | ✅（強制出場） | 間接 | |
| trailing_stop | bool | False | ✅（via chromosome.py） | ✅ | ✅（若啟用） | 間接 | |
| trailing_stop_pct | float | None | ✅ | ✅ | ✅（若啟用） | 間接 | |
| profit_targets | list/None | None | ✅ | ✅ | ✅（若設置） | 間接 | |
| dead_hold_ratio | float | [0.10,0.60] / 0.30 | ✅（mutate_bridge） | ✅（平均） | ✅（庫存橋分割） | 間接 | |
| float_hold_ratio | float | 1-dead_hold_ratio / 0.70 | ✅（派生） | ✅（派生） | ✅（庫存橋分割） | 間接 | 由 dead_hold_ratio 決定 |
| unlock_ka_threshold | float | [0.0,1.0] / 0.60 | ✅（mutate_bridge） | ✅（平均） | ✅（DeadHold解封觸發） | 間接 | |

### 2.4 entry_genes / exit_genes（List[IndicatorGene]）

每個 `IndicatorGene` 的子基因：

| 子基因 | type | mutates | crosses_over | used_in_backtest | notes |
|--------|------|---------|--------------|-----------------|-------|
| name（指標名） | categorical | ✅（mutate_gene随機替換） | ✅（同名混合，不同名隨機選一） | ✅ | 15種指標可用 |
| indicator_type | enum | 跟隨name | 跟隨name | ✅ | TREND/MOMENTUM/VOLATILITY/VOLUME |
| timeframe | categorical | ✅（隨機替換） | ✅（隨機選） | ✅ | 5m/15m/1h/4h |
| params（指標參數） | dict[int/float/str] | ✅（在範圍內擾動） | ✅（隨機混合） | ✅ | 每個指標有自己的params範圍 |
| condition | categorical | ❌（未獨立突變） | ✅（隨機選） | ✅ | ABOVE/BELOW/CROSS_UP/CROSS_DOWN/BETWEEN/OUTSIDE |
| threshold | float | ✅（在threshold_range內） | ✅（平均+微擾） | ✅ | |
| threshold2 | float/None | ✅（若存在） | ✅（若存在） | ✅（BETWEEN/OUTSIDE用） | |
| weight | float | ❌（未突變） | ✅（平均） | ✅（加權邏輯時） | |

**可用指標（GENE_LIBRARY）：**
`ema_cross`, `sma_cross`, `macd`, `adx`, `supertrend`, `close_vs_ma`,
`rsi`, `stochastic`, `cci`, `momentum`,
`bbands`, `atr`, `keltner`,
`volume_sma_ratio`, `obv`, `vwap`

### 2.5 Chromosome 層級邏輯基因

| gene | type | range/default | mutates | crosses_over | used_in_backtest | notes |
|------|------|---------------|---------|--------------|-----------------|-------|
| entry_logic | categorical | AND/OR | ✅（via chromosome.py） | ✅（隨機選） | ✅ | |
| entry_min_weight | float | [0,1] / 0.5 | ✅ | ✅（平均） | ✅ | |
| exit_logic | categorical | AND/OR | ✅ | ✅ | ✅ | |
| exit_min_weight | float | [0,1] / 0.3 | ✅ | ✅ | ✅ | |
| trend_filter | IndicatorGene/None | random | ✅ | ✅ | ✅ | 可能為None |
| volume_filter | IndicatorGene/None | random | ✅ | ✅ | ✅ | 可能為None |

### 2.6 environment_genes（Environment — 造物主法則）

| gene | type | range/default | mutates（跨Epoch） | used_in_backtest | notes |
|------|------|---------------|--------------------|-----------------|-------|
| dead_reserve_ratio | float | [0.05,0.50] / 0.20 | ✅（截斷正態） | ✅（usable_cash_ratio） | 不參與每代GA，跨Epoch抽樣 |
| global_stop_loss | float | [0.10,0.50] / 0.30 | ✅（截斷正態） | ✅（G1 已實作：peak_equity追蹤、drawdown觸發、block新entry） | **active（G1啟用）** |
| max_leverage | float | 固定1.0 | ❌（__post_init__強制1.0） | ❌（現貨GA固定） | **FIXED — 意圖鎖定為現貨** |

### 2.7 season_genes（SeasonConfig）

| gene | type | range/default | mutates | used_in_backtest | used_in_fitness | notes |
|------|------|---------------|---------|-----------------|----------------|-------|
| season | enum | WINTER/SPRING/SUMMER/AUTUMN | ❌（外部設定，非GA演化） | ✅（aggressiveness乘數） | 間接 | Epoch層級設定，非per-chromosome |
| aggressiveness | float | default 1.0 | ❌ | ✅（DCA金額和倉位縮放） | 間接 | |

---

## 3. Mutation / Crossover 分析

### 3.1 Mutation 支援情況

| 類型 | 支援 | 實作方式 | 說明 |
|------|------|---------|------|
| int mutation | ✅ | 加減delta後clamp | MacroGenes fields_int |
| float mutation | ✅ | 比例擾動後clamp | MacroGenes fields_float, MicroGenes, chromosome.py |
| bool mutation | ✅ | 透過chromosome.py | trailing_stop |
| categorical mutation | ✅（部分） | 隨機替換 timeframe/condition | condition 未獨立突變 |
| list/object mutation | ✅ | mutate_gene在參數層級 | IndicatorGene逐參數突變 |

### 3.2 Crossover 方式

| Block | 方式 | 說明 |
|-------|------|------|
| macro_genes | 繼承較好父 | `p1_better` 比較 fitness_score |
| micro_genes（感知段kp/kv） | 正交（Orthogonal） | 從父A取 kp/kv，從父B取 ka/threshold |
| micro_genes（開火段ka/threshold） | 正交 | 50%機率翻轉 |
| micro_genes（其他） | 算術平均 | micro_reserve_rate/sigmoid_scale/gamma/beta |
| risk_genes（基本） | 透過chromosome.py | stop_loss/take_profit/position_pct/max_hold_bars |
| risk_genes（bridge） | 算術平均 | dead_hold_ratio/float_hold_ratio/unlock_ka_threshold |
| entry_genes/exit_genes | 隨機選基因池 | 透過chromosome.py舊版crossover |
| entry_logic/exit_logic | 隨機選 | 透過chromosome.py |

> **注意：非block-level crossover**。crossover並非語義塊整體選一個父，而是各欄位分別處理。
> macro_genes是例外：整塊從較好父繼承。

### 3.3 Mutation Ramp

mutation_ramp 已實作：
- 停滯時（trigger_ramp_if_no_improvement）觸發 `apply_mutation_ramp()`
- `mutation_ramp_factor = 1.25`，最高到 `mutation_rate_max=0.55`, `mutation_intensity_max=0.6`

### 3.4 初始化（genesis_v2）1-4-5 配比

| 類型 | 比例 | 實作 | 說明 |
|------|------|------|------|
| 10% 舊神火種（elite） | `init_elite_ratio=0.10` | ✅ | 從archive.get_elite_seeds注入 |
| 40% 伴生變異（targeted mutants） | `init_mutant_ratio=0.40` | ✅ | elite拷貝+加大突變 (intensity*1.5) |
| 50% 外來移民（explorers） | `init_explorer_ratio=0.50` | ✅ | 均勻隨機全新個體 |

> **每代 evolve_v2 與 genesis_v2 的配比不同**。
> `evolve_v2` 使用 crossover_rate/mutation_rate/random 混合，不是固定1-4-5比例。
> 1-4-5 比例只適用於 genesis（初始化）。

### 3.5 每代精英保留

- `elite_ratio=0.05`（5%），每代 `elite_count = max(1, ceil(pop_size * 0.05))`
- 精英直接進入 survivors，不受淘汰

---

## 4. Dead Gene 清單

| gene_name | reason | source_file | impact | priority_to_fix |
|-----------|--------|-------------|--------|----------------|
| max_dca_months | 不會mutation、不在ACTIVE_EVOLUTION_FIELDS、backtest未使用 | chromosome_v2.py:41 | 佔序列化空間，存在誤解風險 | medium |
| beta_threshold | 同上 | chromosome_v2.py:44 | 同上 | medium |
| moon_phase_pressure | 同上 | chromosome_v2.py:47 | 概念有趣但未實作 | low |
| deadline_force_pct | 同上 | chromosome_v2.py:50 | 同上 | low |
| gc_threshold_months | 同上 | chromosome_v2.py:53 | 同上 | low |
| gc_max_ratio | 同上 | chromosome_v2.py:56 | 同上 | low |
| ema_anchor | 同上 | chromosome_v2.py:62 | 未使用於任何backtest計算 | medium |
| global_stop_loss | ~~configured_but_unused~~ **→ G1 已修復**：peak_equity追蹤 + drawdown觸發 + block新entry + raw_ledger記錄 | environment.py:49 / backtest_engine_v2.py | **active** | resolved |
| IndicatorGene.weight | to_dict/from_dict有保存，crossover有平均，但weighted entry logic使用entry_min_weight不是per-gene weight乘積 | gene_library.py | 序列化存在，但影響路徑不確定 | medium |
| IndicatorGene condition（突變缺口） | mutate_gene未對condition獨立突變（只有整體roll替換gene） | gene_library.py | condition空間未完整探索 | low |

---

## 5. Fixed Parameters（尚未 gene 化）

| fixed_parameter | current_value | source_file | used_where | should_be_gene | priority | reason | recommended_gene_block |
|----------------|---------------|-------------|------------|---------------|---------|--------|----------------------|
| fee_rate | 0.001（0.1%） | backtest_engine_v2.py:93 | DCA/Strategy回測成本 | ✅ | high | 不同交易所/VIP tier手續費不同，影響策略alpha | friction |
| lot_step | 0.001 | backtest_engine_v2.py:229 | 最小交易單位計算 | 部分 | low | 由market_rules決定，但預設值固定 | friction |
| cooldown_bars | ✅（G2 已新增至RiskGenesV2，int，default=0，range 0–50） | chromosome_v2.py / backtest_engine_v2.py | 出場後N根bar不能進場 | ✅ | resolved | G2已實作：random_bridge/mutate_bridge/crossover/to_dict/from_dict/entry gate | frequency |
| max_trades_per_day | ❌（未存在） | backtest_engine_v2.py | 每日最大交易次數限制 | ✅ | medium | 防止過度交易 | frequency |
| min_trade_value | ✅（G3 已新增至RiskGenesV2，float，default=10.0，range 5-100） | chromosome_v2.py / backtest_engine_v2.py | entry gate：名義額低於此值的買單被 block | ✅ | resolved | G3已實作：random_bridge/mutate_bridge/crossover/to_dict/from_dict + blocked_by_min_trade計數 | friction |
| slippage_rate | ✅（G3 以 slippage_sensitivity 基因接入，base=0.05%，range 0–3x） | chromosome_v2.py / backtest_engine_v2.py | 買入+1x、賣出-1x基準滑價 | ✅ | resolved | G3已實作：total_slippage / effective_slippage_rate 進 raw_ledger | friction |
| fee_sensitivity | ✅（G3 已新增至RiskGenesV2，float，default=1.0，range 0.5–3.0） | chromosome_v2.py / backtest_engine_v2.py | 有效手續費=base_fee×fee_sensitivity | ✅ | resolved | G3已實作：effective_fee_rate / total_fees / total_friction 進 raw_ledger | friction |
| min_expected_alpha | 0（隱含） | fitness_v2.py | fitness計算門檻 | ✅ | medium | per-strategy的alpha要求是固定的 | regime |
| volatility_filter_threshold | ❌（未存在） | backtest_engine_v2.py | 高波動期過濾 | ✅ | medium | 防止異常波動期爆倉 | regime |
| trend_strength_threshold | ❌（未存在） | backtest_engine_v2.py | 趨勢強度過濾 | ✅ | medium | ADX類過濾器硬編碼或未存在 | regime |
| aggressiveness（Season） | 1.0（Season外部設定） | environment.py:141 | DCA金額縮放、倉位縮放 | 部分 | later | Season已是Epoch層概念，不在per-chromosome基因 | season |
| dead_reserve_ratio（Environment） | 0.20（跨Epoch抽樣） | environment.py:44 | usable_cash限制 | ✅（已有sampling） | later | 已有截斷正態跨Epoch抽樣，可考慮gene化 | environment |
| global_stop_loss | 0.30（**G1已啟用**：peak_equity追蹤 + drawdown觸發） | environment.py:49 | **active** | resolved | G1已完成 | environment |
| init_min_trades（fitness） | 20 | fitness_v2.py:304 | fitness懲罰門檻 | ✅ | medium | 不同市場環境下合理樣本數不同 | regime |
| dca_amount_pct | 0.05（固定在DCA引擎） | backtest_engine_v2.py:92 | DCA每次投入比例 | ✅ | medium | 現在由外部固定，應由macro_genes控制 | macro |

---

## 6. 第一批 DNA 擴充建議

### High Priority（直接影響 alpha/risk）

| gene | why_gene | expected_effect | risk | required_backtest_support | required_fitness_support |
|------|----------|----------------|------|--------------------------|------------------------|
| cooldown_bars | 目前無冷卻，策略可能反覆進出同方向 | 降低過度交易，提升profit_factor | 若cooldown過長會漏行情 | 需在strategy_backtest加入進場後K線計數 | win_rate/n_trades間接 |
| fee_sensitivity | 手續費固定0.1%，無法評估對fee敏感的策略 | 讓fee敏感策略自然被淘汰 | 若fee過高會殺死所有短線策略 | 已有fee_rate參數，需納入染色體 | total_fees已在raw_metrics |
| slippage_sensitivity | 回測無滑點，過樂觀 | 更真實的回測表現 | 滑點過大會誤判短線策略 | 需在buy/sell加入slippage計算 | 影響total_return |
| min_trade_value | 小幣種/低流動性下名義值太小 | 過濾掉不具經濟意義的交易 | 可能減少交易數統計 | 需在buy入場加入min_notional check | 間接（影響n_trades） |

### Medium Priority（改善探索廣度）

| gene | why_gene | expected_effect | risk | required_backtest_support | required_fitness_support |
|------|----------|----------------|------|--------------------------|------------------------|
| volatility_regime_filter | 高波動期停止交易，降低爆倉風險 | 降低max_drawdown | 若filter太嚴會減少機會 | 需計算ATR/vol regime並在entry加check | max_drawdown有影響 |
| max_trades_per_day | 防過度交易，控制手續費侵蝕 | 提升profit_factor | 若設太低會錯過機會 | 需在每日交易計數器 | n_trades間接 |
| indicator_period（統一基因化） | 各指標period現在在IndicatorGene.params，已有mutation，但range可更寬 | 更大探索空間 | 過長/過短period噪音大 | 已支援，擴大range即可 | 間接 |
| min_expected_alpha | 固定閾值，不同市場環境應不同 | 更靈活的eligibility | 過高要求會殺死合理策略 | 需在fitness加入per-chromosome threshold | 需修fitness |

### Later / GA 2.0

| gene | notes |
|------|-------|
| DeadReserveRatio | 已有跨Epoch抽樣，可先維持Environment層 |
| GlobalStopLoss | 先修觸發邏輯bug再考慮gene化 |
| MaxLeverage | 固定1.0（現貨基線），GA不開槓桿 |
| AggressivenessMultiplier | 已在Season層，per-Epoch固定，可先維持 |
| Season type gene | 需要season regime detector才能gene化 |
| DeadHold/FloatHold（動態） | 已有dead_hold_ratio，考慮增加unlock條件多樣性 |
| Inventory Bridge（進階） | 目前ka/unlock_ka_threshold已覆蓋基本概念 |
| dca_amount_pct | 目前外部固定，可納入MacroGenes |

---

## 7. Gene Registry 設計提案

**設計位置：** `config/ga_gene_registry.json`（本階段只做設計，不讓GA使用）

### 7.1 格式規範

```json
{
  "version": "gene_registry_v1",
  "description": "Gene Registry — 批准後才可進入GA演化。只有 enabled:true 且 owner:human_approved 的 gene 才參與 mutation/crossover。",
  "genes": [
    {
      "name": "stop_loss_pct",
      "block": "risk",
      "type": "float",
      "min": -0.15,
      "max": -0.02,
      "default": -0.05,
      "step": 0.001,
      "precision": 3,
      "unit": "pct",
      "enabled": true,
      "risk_level": "high",
      "mutation": {
        "method": "proportional",
        "sigma_factor": 0.5,
        "clamp": true
      },
      "crossover": {
        "enabled": true,
        "group": "risk_block"
      },
      "constraints": {
        "min_less_than_zero": true,
        "requires": [],
        "conflicts_with": []
      },
      "used_in_backtest": true,
      "used_in_fitness": true,
      "description_zh": "硬止損百分比，負值代表跌幅",
      "version": 1,
      "owner": "human_approved",
      "deprecated": false,
      "feature_flag": null
    }
  ]
}
```

### 7.2 建議新增欄位

| 欄位 | 說明 | 必要性 |
|------|------|--------|
| `allowed_values` | categorical基因的合法值列表 | 必要（IndicatorType/ConditionType） |
| `feature_flag` | 實驗性基因的開關旗標 | 重要（防止未成熟基因進入GA） |
| `deprecated` | 是否已廢棄 | 必要（Dead Gene標記） |
| `deprecated_after` | 廢棄後移除的計劃版本 | 建議 |
| `depends_on` | 依賴其他基因存在 | 建議（如threshold2依賴condition=BETWEEN） |
| `risk_cap` | 基因值的最大允許風險影響 | 建議（防止極端值） |
| `validation_rule` | 自定義驗證規則（如kp+kv+ka=1） | 必要（MicroGenes約束） |
| `migration_note` | 舊archive染色體升級說明 | 建議 |

---

## 8. Gene Proposal System 設計

### 8.1 狀態機

```
proposed → tested → approved → active → deprecated
                 ↘ rejected
```

| 狀態 | 說明 | 誰可轉換 |
|------|------|---------|
| proposed | AI提出，尚未測試 | AI自動 |
| tested | 煙霧測試通過 | 自動（通過tests_required） |
| approved | 人工審核通過 | **人工** |
| active | 正式進入GA演化 | **人工**（approved後啟用） |
| deprecated | 廢棄，不再使用 | 人工 |
| rejected | 測試失敗或人工否決 | 自動/人工 |

**核心規則：AI只能到tested，approved和active必須人工操作。**

### 8.2 資料位置

| 位置 | 用途 | Commit？ |
|------|------|---------|
| `data/genetic_archive/gene_proposals.json` | runtime proposal資料 | ❌ 不commit |
| `config/ga_gene_registry.json` | 批准後的正式Gene設定 | ✅ commit |

### 8.3 Proposal 格式

```json
{
  "proposal_id": "gene_prop_001",
  "name": "cooldown_bars",
  "block": "frequency",
  "type": "int",
  "min": 0,
  "max": 50,
  "default": 5,
  "reason": "Currently no cooldown exists; strategies re-enter repeatedly causing high fee drag",
  "expected_effect": "Reduce n_trades by 20-40%, increase profit_factor",
  "risk": "May miss re-entry opportunities in trending markets",
  "tests_required": [
    "schema_validation",
    "mutation_smoke_test",
    "crossover_smoke_test",
    "backtest_usage_check",
    "fitness_impact_check"
  ],
  "status": "proposed",
  "requires_human_approval": true,
  "trigger_source": "high_fee_drag_pattern",
  "proposed_by": "ai",
  "proposed_at": "2026-06-16T00:00:00"
}
```

### 8.4 從失敗規則觸發 Proposal

| 觀察到的失敗模式 | 觸發的 Gene Proposal | 說明 |
|----------------|-------------------|------|
| 交易太頻繁，fee超過alpha | `cooldown_bars` / `max_trades_per_day` / `fee_sensitivity` | 頻繁交易懲罰 |
| 高波動期連續止損 | `volatility_regime_filter` | 波動過濾器 |
| 單一標的貢獻>50% | `symbol_consistency_weight` | 多元化懲罰 |
| 最大回撤持續>15% | `dynamic_position_sizing` / `cooldown_bars` | 風控加強 |
| Sharpe<0但win_rate>50% | `profit_factor_weight_gene` | fitness函數調整 |
| 手續費超過alpha 20% | `min_trade_value` / `slippage_sensitivity` | 摩擦力基因 |

---

## 9. Evolution Engine 配比確認

### 9.1 genesis_v2（初始化）
- ✅ 10% 舊神火種（archive elite seeds）
- ✅ 40% 伴生變異（elite + 1.5x intensity mutate）
- ✅ 50% 外來移民（random_chromosome_v2）

### 9.2 evolve_v2（每代演化）
- ✅ 5% elite保留（elite_ratio=0.05）
- ✅ crossover_rate控制交叉率
- ✅ mutation_rate控制突變率
- ✅ 剩餘隨機新個體補充

**注意：evolve_v2 不複製 genesis_v2 的1-4-5比例，這是設計意圖（初始化 vs 穩態演化不同）。**

### 9.3 Mutation Ramp
- ✅ 停滯時自動放大 mutation_rate / mutation_intensity
- ✅ 有上限 mutation_rate_max / mutation_intensity_max

---

## 10. Phase G 建議

### 10.1 最優先修正（Dead Gene / Bug）
1. **修復 global_stop_loss 觸發邏輯**：`configured_but_unused`，需在 `backtest_engine_v2.py` 加入equity drawdown check
2. **標記7個Dead MacroGenes**：在 `chromosome_v2.py` 加入 `@deprecated` 注釋或移至 `legacy_fields` dict
3. **修復 IndicatorGene.condition 未突變問題**：`mutate_gene` 加入 condition mutation 分支

### 10.2 第一批 Gene 化（High Priority）
1. `cooldown_bars`（frequency block）
2. `slippage_sensitivity`（friction block）  
3. `fee_sensitivity`（friction block）
4. `min_trade_value`（friction block）

### 10.3 建立 Gene Registry
1. 建立 `config/ga_gene_registry.json`（本階段只設計，Phase G 實作）
2. 建立 `scripts/validate_gene_registry.py`（驗證格式）
3. 讓 GA 讀取 registry 決定哪些 gene 參與 mutation

### 10.4 Gene Proposal System
1. 建立 `scripts/propose_gene.py`（AI提出gene，寫入proposals.json）
2. 建立 `scripts/review_gene_proposal.py`（人工審核，搬移到registry）
3. proposals.json 加入 .gitignore

---

## 11. 總結

| 類別 | 數量 |
|------|------|
| 已確認 Active Gene（參與mutation+crossover+backtest） | 約 35個 |
| Dead Gene（存在但無作用） | 7個（MacroGenes 7個legacy fields）|
| G1/G2 已修復 | 2個（global_stop_loss觸發 G1✅ / cooldown_bars G2✅）|
| Fixed Parameter（應gene化） | 9個 |
| 建議第一批gene化（High Priority） | 4個 |
| 建議第二批gene化（Medium Priority） | 4個 |
