# v9 Preregistration

Status: draft. Do not start v9 search until this document is finalized and committed.

## Objective

Build a strategy-search protocol that improves the chance of finding a true out-of-sample edge while reducing false positives from correlated candidates, overlapping scenarios, and repeated holdout looks.

The immediate goal is not paper trading. The immediate goal is a validation harness strong enough that a future paper-trading decision is meaningful.

## Burned Information

The v8 LINK batch failed its holdout on 2026-07-06. The only post-2024-06 statistic that v9 may use as design input is:

`v8_link_batch1_20260706 family_passed=false`

Do not tune v9 features, thresholds, seeds, symbol choices, or candidate selection using the detailed v8 holdout diagnostics. Those diagnostics are recorded for audit only.

## Train, Embargo, Holdout, Forward

Default split:

- Train: 2017-08 through 2024-06
- Embargo: 2024-07
- Burned historical holdout: 2024-08 through 2026-05
- Fresh forward-shadow: 2026-07 onward

If v9 reuses any part of the burned historical holdout, this must be declared before the run and the family gate must be tightened. A clean paper-trading decision still requires a forward-shadow period on fresh data that was not available during v9 design.

## Universe

Start with a multi-symbol liquid crypto universe. Minimum:

- BTCUSDT
- ETHUSDT
- SOLUSDT
- LINKUSDT

Optional expansion only after the harness is stable:

- BNBUSDT
- XRPUSDT
- ADAUSDT
- AVAXUSDT

Do not build v9 as a single-symbol LINK-only rescue run.

## Candidate Freezing

A frozen family must contain candidates that are not just copies of the same trade stream.

Before freezing a family:

- Compute pairwise train-window return correlation across candidate equity/return streams.
- Require pairwise correlation below a pre-set cap. Initial cap: `rho < 0.70`.
- Prefer candidates from different symbols, regimes, and genome structures.
- Freeze by a deterministic rule before any holdout run.
- Run the common train-only freeze gate with `scripts/freeze_decorrelated_candidates_v9.py --require-common-gate`.

If fewer than the required number of decorrelated candidates exist, the family does not freeze and no holdout is spent.

The freeze tool must be run before any holdout evaluator. The expected command shape is:

```bash
python3 scripts/freeze_decorrelated_candidates_v9.py \
  --state state/<v9_search_state>.json \
  --batch-id <batch_id> \
  --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
  --family-size 3 \
  --rho-cap 0.70 \
  --require-common-gate \
  --start 2017-08 \
  --end 2024-06 \
  --out results/frozen/<batch_id>.json \
  --md results/frozen/<batch_id>.md
```

Regime-aware report-only freeze dry run must be run before enforcing regime gates:

```bash
python3 scripts/freeze_decorrelated_candidates_v9.py \
  --state state/<v9_search_state>.json \
  --batch-id <batch_id>_regime_report_only \
  --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
  --family-size 3 \
  --rho-cap 0.70 \
  --require-common-gate \
  --regime-report artifacts/v9/regime_report.json \
  --regime-gates-report-only \
  --out results/frozen/<batch_id>_regime_report_only.json \
  --md results/frozen/<batch_id>_regime_report_only.md
```

If the report-only output is sane, enforcing mode is:

```bash
python3 scripts/freeze_decorrelated_candidates_v9.py \
  --state state/<v9_search_state>.json \
  --batch-id <batch_id> \
  --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
  --family-size 3 \
  --rho-cap 0.70 \
  --require-common-gate \
  --regime-report artifacts/v9/regime_report.json \
  --enforce-regime-gates \
  --out results/frozen/<batch_id>.json \
  --md results/frozen/<batch_id>.md
```

Regime freeze metrics are scenario-window train-only exposure metrics. They must not be described as per-trade attribution, per-trade CVaR, or out-of-sample regime robustness.

Dry-run result from the failed v8 LINK family:

- Loose decorrelation-only dry run selected 1/3 candidates.
- Strict `--require-common-gate` dry run selected 0/3 candidates.
- Strict regime report-only dry run selected 0/3 candidates; all evaluated v8 LINK candidates had max regime share around 0.678, above the 0.60 limit.
- Conclusion: the old v8 LINK qualified set would not be frozen under v9 rules.

## Fitness Direction

Use maximin/CVaR style scoring. Keep training pressure on worst-case behavior:

- Reward average alpha only after worst-case alpha is acceptable.
- Penalize negative CVaR alpha.
- Penalize high drawdown.
- Penalize cost sensitivity, especially failure at 50 bps.
- Do not optimize directly against the burned holdout.

## Regime Gate

Add a coarse regime exposure gate as risk control, not as a magic alpha source.

Allowed pre-holdout inputs:

- Realized volatility
- Trend slope or moving-average spread
- Market breadth across the training universe
- Drawdown state
- Volume/liquidity filters

The regime gate must be trained and fixed using training data only. It must decide when to reduce exposure, skip trades, or lower leverage. It must not be tuned from 2024-08 through 2026-05 diagnostics.

The fixed v9 regime context is generated by:

```bash
python3 scripts/regime_context_v9.py \
  --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
  --train-start 2017-08-01 \
  --train-end "2024-06-30 23:59:59" \
  --embargo-start 2024-07-01 \
  --config configs/regime_v9.yaml \
  --out artifacts/v9
```

Frozen config:

- file: `configs/regime_v9.yaml`
- sha256: `29a68617ff3fceb494ff5fee91b1b6c996581c3309554a81be9637d2de9c0c1e`
- report: `artifacts/v9/regime_report.json`
- labels: `artifacts/v9/regime_labels_<SYMBOL>.parquet`

The regime script must raise if any OHLCV bar or candidate trade timestamp is on or after `2024-07-01`. This is a hard embargo guard.

Regime gates to add before freezing a future candidate family:

- Regime robustness: non-negative train expectancy in every regime the candidate trades in.
- PnL concentration: no more than 60% of train PnL from one regime.
- Worst-regime risk: per-trade CVaR5 cannot be worse than the declared per-trade risk budget.
- Fold visibility: regime occupancy and candidate regime stats must be reported across purged train folds, not only pooled train.

## Per-Trade Contract Engine

Add per-trade risk contracts after the validation and regime-gate rules are fixed.

Each candidate should emit:

- Entry trigger
- Invalidation/stop level
- Take-profit or trailing-exit rule
- Maximum holding period
- Position size rule
- Leverage cap

The first objective is loss containment and behavior transparency, not higher reported win rate.

## Execution Logging

Before adding contract-style entries/exits, the current LunarGenome spot/DCA evaluator must produce honest execution logs. The current log is order-event level, not a contract round-trip log.

Train-only dump command:

```bash
python3 scripts/dump_trades_v9.py \
  --frozen results/frozen/v8_link_candidates_batch1_20260706.json \
  --candidate-index 1 \
  --symbol LINKUSDT \
  --start 2017-08 \
  --end 2024-06 \
  --embargo-start 2024-07-01 \
  --regime-report artifacts/v9/regime_report.json \
  --out artifacts/v9/trade_logs/v8_link_candidate1_train_trades.jsonl \
  --summary artifacts/v9/trade_logs/v8_link_candidate1_train_trades_summary.json
```

Output schema is execution-event JSONL:

- `ts`, `signal_ts`, `scenario`, `cost_bps`, `symbol`
- `action`, `side`, `inventory_bucket`
- `price`, `qty_delta`, `cash_delta`, `gross`, `fee`
- `realized_pnl`, `realized_return`
- `route_label`, `route_multiplier`, `policy_multiplier`
- `regime_at_execution`, `regime_config_sha256`
- `genome_hash`, `code_version`

The dump script must hard-fail if any selected scenario month or execution timestamp is on or after `2024-07-01`. It also reconciles logged event count, fees, and reconstructed final equity against evaluator metrics.

Dry-run result from v8 LINK candidate 1:

- train-only execution events: 7,866
- max execution timestamp: 2024-05-27 21:00:00 UTC
- action counts: `macro_buy_dead=210`, `micro_buy_float=4059`, `micro_sell_float=3597`
- largest execution concentration: `deep_drawdown=6647` events

Do not call this per-trade contract attribution yet. It is execution/order-event attribution for the current spot inventory strategy. Contract-style entry/exit, MAE/MFE, stop/target, and leverage gates require a later engine change.

FIFO lot-level accounting command:

```bash
python3 scripts/round_trip_contract_v9.py \
  --events artifacts/v9/trade_logs/v8_link_candidate1_train_trades.jsonl \
  --out artifacts/v9/trade_logs/v8_link_candidate1_round_trips.jsonl \
  --summary artifacts/v9/trade_logs/v8_link_candidate1_round_trips_summary.json \
  --cutoff "2024-06-30 23:59:59"
```

This converts inventory order events into FIFO lot-level round trips and explicitly reports open residual inventory. MAE/MFE fields remain null unless mark-path data is supplied. Do not infer MAE/MFE from fills alone.

Dry-run FIFO result for v8 LINK candidate 1:

- round trips: 6,778
- residual lots: 1,088
- max timestamp: 2024-05-27 21:00:00 UTC
- gates: `passed=false`
- residual inventory failed in all 72 scenario/cost streams
- entry-regime net PnL summary:
  - `deep_drawdown`: 5,905 round trips, net PnL -2339.20
  - `up_high_vol`: 273 round trips, net PnL 3438.20
  - `up_normal`: 600 round trips, net PnL 2321.37

Interpretation: the old LunarGenome spot/DCA inventory model leaves too much open residual inventory to be treated as a clean contract strategy. Future contract-style v9 work must add explicit entry, invalidation/stop, exit, max hold, and residual-flattening rules instead of assuming the current inventory strategy already has them.

## Contract Lab v9 Train-Only Scaffold

The first v9 contract-style scaffold is intentionally separate from the old LunarGenome spot/DCA evaluator.

Modules:

- `v9/contract/schema.py`: candidate schema and stable candidate hash.
- `v9/contract/simulator.py`: one-position long-only contract simulator.
- `v9/contract/metrics.py`: per-trade metrics and fail-closed gates.
- `v9/contract/search.py`: train-only random Donchian parameter search.
- `v9/contract/report.py`: JSON and Markdown reports.

Mandatory simulation rules:

- Signals are computed on bar `t` close and executed at bar `t+1` open.
- ATR/regime used for entry must come from the signal bar, not the entry bar.
- Daily regime labels are shifted forward by one day before joining to 1h bars.
- Same-bar stop-loss and take-profit ambiguity is resolved pessimistically: stop-loss wins.
- Gap through stop-loss exits at the worse open price.
- `max_hold_bars` exits at the next open.
- End of train data forces flat inventory; `residual_positions` must be zero.
- Base cost and 2x cost streams are both evaluated before any candidate can advance.

Train-only dry-run artifacts created on 2026-07-06:

- `artifacts/v9/contract_lab/contract_search_LINKUSDT_train_smoke3.{json,md}`
- `artifacts/v9/contract_lab/contract_search_LINKUSDT_train_smoke30.{json,md}`
- `artifacts/v9/contract_lab/contract_search_LINKUSDT_train_2022_2024_sample12.{json,md}`
- `artifacts/v9/contract_lab/contract_eval_LINKUSDT_best_sample12_full_train.{json,md}`

Current contract-lab status:

- No candidate is holdout-authorized.
- No candidate is paper-trading-authorized.
- `contract_search_LINKUSDT_train_smoke30` sampled 30 candidates on the full train window and found 4 train-only gate-pass candidates.
- Best train-only pass candidate:
  - candidate: `ecc1879130422082`
  - trades: 258
  - net PnL: 2537.77
  - 2x-cost net PnL: 1828.52
  - win rate: 0.519
  - avg R: 0.119
  - CVaR5 R: -1.040
  - max drawdown: 0.041
  - fold PnLs: 1068.43, 517.62, 951.72
  - entry-regime PnL: `up_normal` 2578.77, `up_high_vol` -40.99

Interpretation: the contract-style path is now executable and structurally cleaner than v8 DCA. The first full-train smoke search produced train-only pass candidates, but this is not enough for holdout, paper, or live. The next train-only step must freeze/decorrelate candidates, run a stricter regime robustness review, and avoid reusing the 2024-08..2026-05 burned holdout for tuning.

### Contract Freeze Audit

The freeze audit is a stricter train-only gate that must run before any future frozen family can request fresh shadow or holdout access.

Command shape:

```bash
python3 -m v9.contract.freeze \
  --search artifacts/v9/contract_lab/contract_search_LINKUSDT_train_smoke30.json \
  --out artifacts/v9/contract_lab/contract_freeze_audit_LINKUSDT_smoke30.json \
  --md artifacts/v9/contract_lab/contract_freeze_audit_LINKUSDT_smoke30.md \
  --bootstrap-iterations 2000
```

Freeze audit gates:

- trades at 2x cost >= 150
- 2x cost net PnL > 0
- 2x/base cost retention >= 50%
- all three folds positive
- minimum fold share >= 10% of 2x net PnL
- block-bootstrap 2x net PnL 5% lower bound > 0
- top 5 winning trades <= 40% of 2x net PnL
- non-`up_normal` regimes do not exceed the registered loss limits
- CVaR5 R >= -1.20
- longest underwater period <= 730 days
- signal time strictly precedes entry time
- no trade exits after the train cutoff
- 2x cost net PnL <= base cost net PnL

Dry-run result for `contract_search_LINKUSDT_train_smoke30`:

- candidate_count: 4
- freeze_gate_passed: 0
- selected_preview: none
- family_frozen: false
- block reason: `no_decorrelated_gate_pass_candidates`

Failure summary:

- `max_underwater_days`: 4
- `min_fold_share`: 3
- `top5_profit_share`: 3
- `bootstrap_p5_positive`: 2
- `cost_retention`: 1
- `folds_all_positive`: 1
- `min_trades`: 1
- `non_up_normal_loss`: 1
- `single_regime_loss`: 1

The best smoke30 candidate `ecc1879130422082` remained positive under 2x and 3x costs and passed bootstrap/concentration/fold gates, but failed the longest-underwater gate:

- 2x net PnL: 1828.52
- 3x net PnL: 1105.21
- bootstrap 2x net PnL p5: 368.16
- top5 profit share: 0.345
- min fold share: 0.183
- longest underwater days: 1018

Interpretation: smoke30 found useful signal families but not a freeze-ready strategy. The next train-only search must optimize not only net PnL, but also underwater duration, fold share, top-trade concentration, and bootstrap lower bound. No holdout, paper, or live step is authorized from this audit.

### Freeze-Aware Search Ranking

The contract searcher supports an optional freeze-aware ranking mode:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 40 \
  --seed 20260707 \
  --ranking-mode freeze_proxy \
  --proxy-bootstrap-iterations 200 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_freezeproxy2_sample40.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_freezeproxy2_sample40.md
```

Default `ranking_mode=train_gate` is unchanged. `freeze_proxy` keeps per-trade data during search and ranks candidates by a soft proxy for freeze readiness:

- 200-iteration block bootstrap proxy for 2x-cost PnL lower bound
- soft trade-count penalty up to 150 trades
- soft underwater penalty: full score at <=730 days, zero at >=1460 days
- soft fold penalty: full score at min fold share >=10%
- soft top5 profit concentration penalty: full score at <=40%, zero at >=80%

The strict freeze audit remains unchanged and is the only authoritative freeze gate.

Dry-run result for `contract_search_LINKUSDT_freezeproxy2_sample40`:

- sampled: 40
- train gate passed: 7
- strict freeze audit passed: 0
- family_frozen: false
- best candidate: `6ca0655252826514`
  - 2x net PnL: 1957.19
  - 3x net PnL: 1234.02
  - strict bootstrap p5: 533.78
  - max underwater days: 656
  - min fold share: 0.086
  - top5 profit share: 0.626
  - freeze failures: `min_trades`, `min_fold_share`, `top5_profit_share`, `cvar5_r`

Interpretation: freeze-aware ranking improved the underwater failure mode versus smoke30 (`1018` days to `656` days for the best candidate), but did not yet produce a freeze-ready family. The next train-only improvement should bias gene sampling toward higher trade counts and lower concentration: shorter breakouts, shorter/medium max-hold, lower per-trade risk, and stronger rejection of sparse-signal candidates before full simulation.

### Freeze-Dense And Freeze-Balanced Sampling

Two additional sampling profiles were added for train-only exploration:

- `freeze_dense`: raises signal/trade count and rejects sparse-signal candidates.
- `freeze_balanced`: keeps trade count high but avoids the discovered attractor `breakout=12 + ATR=48 + cooldown=0 + max_hold=48`.

`freeze_dense` command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 40 \
  --seed 20260708 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_dense \
  --proxy-bootstrap-iterations 200 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_freezedense_sample40.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_freezedense_sample40.md
```

`freeze_dense` result:

- sampled: 40
- attempts: 56
- accepted_rate: 0.714
- train gate passed: 2
- strict freeze audit passed: 0
- best candidate had 514 trades but failed freeze on `min_fold_share`, `bootstrap_p5_positive`, `top5_profit_share`, and `max_underwater_days`

Interpretation: `freeze_dense` solved the trade-count problem but amplified concentration risk.

`freeze_balanced` command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 64 \
  --seed 20260709 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_balanced \
  --proxy-bootstrap-iterations 200 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_freezebalanced_sample64.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_freezebalanced_sample64.md
```

`freeze_balanced` result:

- sampled: 64
- attempts: 114
- accepted_rate: 0.561
- train gate passed: 5
- strict freeze audit passed: 0
- best candidate: `bf7919c368e63524`
  - 2x net PnL: 2595.92
  - 3x net PnL: 1995.49
  - strict bootstrap p5: 710.02
  - min fold share: 0.237
  - top5 profit share: 0.546
  - max underwater days: 913
  - freeze failures: `top5_profit_share`, `max_underwater_days`

Interpretation: `freeze_balanced` is the best current path. It preserved positive 2x/3x PnL, positive bootstrap p5, and stable fold share, while reducing failures to top-trade concentration and underwater duration. The next train-only search should keep the balanced profile but further penalize/avoid top5 concentration and long underwater, likely by down-weighting `tp_r_multiple >= 2.5`, down-weighting `max_hold >= 36`, and adding a cheap realized-equity underwater proxy to candidate selection. No holdout, paper, or live step is authorized.

### Protective Stop Experiment

Protective-stop genes were added with defaults disabled, so legacy candidates keep the same behavior and stable IDs:

- `be_trigger_r`
- `be_lock_r`
- `trail_atr_mult`
- `trail_trigger_r`

Simulation rule: protective stops update only before a bar opens, using information available through the previous bar. Same-bar high cannot activate a stop that is then used against the same bar low. This preserves the existing no-lookahead rule.

Broad protective sampling is kept in an explicit `freeze_protective` profile. It is not part of the `freeze_balanced` baseline because the first broad run worsened the target metrics.

Protective dry-run command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 64 \
  --seed 20260710 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_protective \
  --proxy-bootstrap-iterations 200 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_protective_sample64.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_protective_sample64.md
```

Protective result:

- sampled: 64
- train gate passed: 4
- strict freeze audit passed: 0
- best candidate: `0107e0701971abc9`
  - 2x net PnL: 1275.17
  - 3x net PnL: 286.56
  - bootstrap p5: -615.37
  - min fold share: 0.262
  - top5 profit share: 1.144
  - max underwater days: 990
  - freeze failures: `bootstrap_p5_positive`, `top5_profit_share`, `max_underwater_days`

Interpretation: broad trailing/BE sampling did not solve the concentration problem and reduced robustness. Keep the implementation for controlled experiments, but do not use broad `freeze_protective` as the primary search path. The current best baseline remains `freeze_balanced` without protective genes; future protective experiments should isolate BE-only variants before reintroducing trailing stops.

### Regime/Hold Sweep Around Best Balanced Candidate

Fable5 recommended testing whether the best balanced candidate could be rescued by changing only regime strictness and max holding time, while keeping entry, stop, target, risk, leverage, and cooldown fixed. Because `bf7919c368e63524` already uses only `up_normal`, the stricter regime tier was implemented as an optional no-lookahead daily regime filter:

- `max_regime_drawdown_1y <= 0.25`

The filter uses the previous daily regime label after the existing D+1 shift. Defaults are disabled, so legacy candidate IDs remain stable. Inactive BE/trailing parameters are also ignored in canonical hashes when their trigger is disabled.

Sweep command:

```bash
python3 -m v9.contract.sweep \
  --source-search artifacts/v9/contract_lab/contract_search_LINKUSDT_freezebalanced_sample64.json \
  --candidate-id bf7919c368e63524 \
  --out-json artifacts/v9/contract_lab/contract_sweep_LINKUSDT_bf7919c368e63524_regime_hold.json \
  --out-md artifacts/v9/contract_lab/contract_sweep_LINKUSDT_bf7919c368e63524_regime_hold.md \
  --ranking-mode freeze_proxy \
  --proxy-bootstrap-iterations 200
```

Strict freeze audit command:

```bash
python3 -m v9.contract.freeze \
  --search artifacts/v9/contract_lab/contract_sweep_LINKUSDT_bf7919c368e63524_regime_hold.json \
  --out artifacts/v9/contract_lab/contract_freeze_audit_LINKUSDT_bf7919c368e63524_regime_hold.json \
  --md artifacts/v9/contract_lab/contract_freeze_audit_LINKUSDT_bf7919c368e63524_regime_hold.md \
  --bootstrap-iterations 2000
```

Regime/hold sweep result:

- attempted variants: 6
- simulated variants: 3
- strict drawdown-cap variants rejected by prescreen: 3, reason `signals_below_min_train`
- train gate passed among simulated variants: 3
- strict freeze audit passed: 0

Audited variants:

| candidate | max hold | drawdown cap | 2x net PnL | 3x net PnL | bootstrap p5 | min fold | top5 share | underwater days | failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `bf7919c368e63524` | 36 | none | 2595.92 | 1995.49 | 710.02 | 0.237 | 0.546 | 913 | `top5_profit_share`, `max_underwater_days` |
| `d4eb96cfc17e8266` | 27 | none | 1679.74 | 1090.57 | 65.34 | 0.188 | 0.765 | 922 | `top5_profit_share`, `max_underwater_days` |
| `5fa3cf9df94efc38` | 18 | none | 2390.05 | 1742.00 | 654.64 | 0.235 | 0.574 | 812 | `top5_profit_share`, `max_underwater_days` |

Interpretation: shorter holds reduced the longest underwater period only partially and did not fix top-trade concentration. The stricter drawdown regime tier was too restrictive under the pre-registered balanced signal-count floor. This suggests the remaining failure is likely an entry-family/concentration issue, not an exit-management issue. No holdout, paper, or live step is authorized.

### Hard-Gated Distributed Entry Diagnostics

After the regime/hold sweep, `bf7919c368e63524` was added to the rejected-family ledger:

- ledger: `artifacts/v9/contract_lab/rejected_families_v9.json`
- rejection reason: `structural: top5>=0.546 and underwater>=812 invariant across max_hold {18,27,36}`
- decision: do not resurrect this family on raw net PnL or train-gate score

Search was updated with optional upstream hard gates so distribution failures can be rejected before freeze audit:

- `--freeze-distribution-hard-gate`
- `--freeze-gate-margin`
- `--min-hard-trades`
- `--max-attempts`

Hard gate definitions used in diagnostics:

- minimum hard trades: 504, roughly 2x the `bf7919` family
- top5 profit share limit with margin 0.9: `0.36`
- top5 profit share limit with margin 1.0: `0.40`, equal to strict freeze
- max underwater limit with margin 0.9: `657` days

`freeze_dense` hard-gated diagnostic:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260712 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_dense \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 0.9 \
  --min-hard-trades 504 \
  --max-attempts 160 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_distributed_hardgate_diag160.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_distributed_hardgate_diag160.md
```

Result:

- attempts: 160
- sampled: 0
- main rejections: `hard_trades_below_min=85`, `hard_top5_profit_share=29`

Interpretation: `freeze_dense` still produced too many low-frequency candidates and did not reach the distribution gates.

`freeze_distributed` was added to bias sampling toward higher-frequency, more distributed entries:

- breakout: 8/12/16/20/24
- ATR: 7/10/14
- TP multiple: mostly 1.2 to 1.8
- cooldown: mostly 0 to 4
- regimes: broader than `freeze_balanced`, including an explicit all-regime tier that is still controlled by train gates and hard distribution gates

`freeze_distributed` margin 0.9 diagnostic:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260713 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_distributed \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 0.9 \
  --min-hard-trades 504 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_freeze_distributed_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_freeze_distributed_diag80.md
```

Result:

- attempts: 80
- sampled: 0
- main rejection: `hard_top5_profit_share=63`
- `hard_trades_below_min=0`

Interpretation: `freeze_distributed` solved the hard trade-count bottleneck but exposed top-trade concentration as the binding failure.

`freeze_distributed` margin 1.0 diagnostic:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260714 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_distributed \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 504 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_freeze_distributed_margin100_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_freeze_distributed_margin100_diag80.md
```

Result:

- attempts: 80
- sampled: 0
- main rejection: `hard_top5_profit_share=66`
- `hard_trades_below_min=1`

Interpretation: even at the formal strict-freeze top5 threshold of 0.40, this LINKUSDT single-symbol Donchian-entry search space did not retain a candidate in the diagnostic budget. The current bottleneck is not trade count; it is profit concentration. Next high-value research should either introduce a genuinely different entry family with less lottery-like payoff distribution, or move to pre-registered multi-symbol portfolio/decorrelation research. Do not loosen the strict freeze top5 gate to pass these candidates.

### Pullback Long Entry Family Diagnostic

Fable5 recommended adding a genuinely different single-symbol entry family before moving to multi-symbol portfolio research, because the existing Donchian breakout family failed structurally on top-trade concentration and there were no frozen single-symbol candidates to decorrelate.

Implemented family:

- `family="pullback_long_v1"`
- entry: `RSI(rsi_len) < rsi_entry_max` and `close > EMA(trend_ema_len)`
- allowed grids:
  - `trend_ema_len`: 50, 100, 200
  - `rsi_len`: 2, 3, 4
  - `rsi_entry_max`: 10, 15, 20, 25
  - `rsi_exit_min`: 55, 65, 75
  - `max_hold_bars`: 12, 18, 27
- exits: existing stop/TP/max-hold plus RSI signal exit, executed on the next bar open
- unchanged: cost model, train window, hard gates, strict freeze gates

Search instrumentation was updated to record distribution diagnostics for every fully simulated candidate, including rejected candidates:

- `trade_count`
- `net_pnl`
- `top5_profit_share`
- `max_underwater_days`
- `distribution_rejection`

Initial pullback diagnostic command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260715 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_pullback \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 504 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_pullback_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_pullback_diag80.md
```

This run produced `sampled=0`. It initially classified most failures as `hard_top5_profit_share` because non-positive net PnL makes top5 share infinite. The hard-gate order was corrected to reject `net_pnl <= 0` before top5 concentration.

Net-first pullback diagnostic command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260716 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_pullback \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 504 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_pullback_diag80_netfirst.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_pullback_diag80_netfirst.md
```

Net-first result:

- attempts: 80
- sampled: 0
- fully simulated candidates: 65
- positive-net candidates: 0
- main rejection: `hard_net_pnl_nonpositive=60`
- secondary rejection: `hard_trades_below_min=5`
- best 2x net PnL among simulated candidates: -83.58
- median 2x net PnL: -2292.92
- median max underwater days: 1686

Interpretation: `pullback_long_v1` achieved sufficient trade frequency but showed no positive train-only expectancy in this LINKUSDT setup. This is not a near miss on top5 concentration; it is a non-positive-expectancy long pullback family under the current execution and cost model. Do not iterate this sampler or loosen gates without a new structural hypothesis.

Fable5 then recommended rerunning the same pullback family unchanged on a positive-drift symbol before deciding whether the failure was LINK-specific drift or a dead family. Search diagnostics were extended with exposure-matched buy-and-hold metrics:

- `exposure_bar_ratio`
- `exposure_matched_buy_hold_net_pnl`
- `net_pnl_minus_exposure_benchmark`

Benchmark definition:

- same train window
- margin 1.0 buy-and-hold net PnL from first close to last close
- scaled by the strategy's exposure bar ratio

BTC pullback benchmark diagnostic command:

```bash
python3 -m v9.contract.search \
  --symbol BTCUSDT \
  --samples 16 \
  --seed 20260717 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_pullback \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 504 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_BTCUSDT_pullback_diag80_netfirst_benchmark.json \
  --out-md artifacts/v9/contract_lab/contract_search_BTCUSDT_pullback_diag80_netfirst_benchmark.md
```

BTC result:

- attempts: 80
- sampled: 0
- fully simulated candidates: 60
- positive-net candidates: 0
- benchmark-beating candidates: 0
- main rejection: `hard_net_pnl_nonpositive=60`
- best 2x net PnL among simulated candidates: -2854.19
- median 2x net PnL: -7109.05
- median exposure-matched buy-and-hold benchmark: 8207.43
- best net minus exposure benchmark: -7745.34
- median max underwater days: 2245

Interpretation: `pullback_long_v1` failed even with BTC's positive train-period drift behind it, and it underperformed exposure-matched buy-and-hold by a large margin. Per the pre-committed branch, this RSI(2-4) pullback-below-threshold plus EMA-filter family is retired under the current cost and execution model. The next experiment should not be another long pullback sampler; it should be a structurally different entry family or a short-capable/drift-neutral construction.

### Bear Rally Fade Short Diagnostic

Fable5 recommended adding short-side support before building a portfolio harness, because no single-symbol family had passed freeze yet. It specifically recommended a rally-fade short rather than a breakdown short to avoid repeating the breakout top5 concentration failure mode.

Implemented simulator changes:

- `side`: `long` or `short`, default `long`
- short entries sell at next open with adverse slippage
- short stop is above entry; short target is below entry
- short liquidation guard is above entry
- short PnL is `qty * (entry - exit)` minus fees, funding cost, and short extra cost
- `short_extra_cost_bps`, default 5 bps per round trip, conservative stand-in for adverse borrow/funding
- exposure-matched short-and-hold benchmark, sign-flipped from long buy-and-hold

Implemented family:

- `family="bear_rally_fade_short_v1"`
- `side="short"`
- bearish regime: `close < SMA(regime_len)` and SMA slope over `slope_len` bars is negative
- entry: bearish regime and `RSI(rsi_len) >= rsi_hi`
- exits: short stop, short target, max hold, or regime exit when `close > SMA(regime_len)`, executed next bar open

Search grids:

- `regime_len`: 100, 150, 200
- `slope_len`: 10, 20
- `rsi_len`: 2, 3, 4
- `rsi_hi`: 65, 70, 75, 80
- `stop_pct`: 0.02, 0.03, 0.05
- `target_pct`: 0.01, 0.015, 0.02, 0.03
- `max_hold_bars`: 12, 24, 48

LINKUSDT diagnostic command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260718 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_bear_fade \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 150 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_bear_fade_short_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_bear_fade_short_diag80.md
```

LINKUSDT result:

- attempts: 80
- sampled: 0
- fully simulated candidates: 49
- positive-net candidates: 0
- main rejection: `hard_net_pnl_nonpositive=49`
- best 2x net PnL: -769.45
- median 2x net PnL: -2517.37
- median max underwater days: 1642
- median trades: 702
- benchmark note: all candidates beat exposure-matched short-and-hold only because short-and-hold was strongly negative; this is not sufficient because absolute net PnL stayed negative

BTCUSDT control command:

```bash
python3 -m v9.contract.search \
  --symbol BTCUSDT \
  --samples 16 \
  --seed 20260719 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_bear_fade \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 150 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_BTCUSDT_bear_fade_short_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_BTCUSDT_bear_fade_short_diag80.md
```

BTCUSDT result:

- attempts: 80
- sampled: 0
- fully simulated candidates: 50
- positive-net candidates: 0
- main rejection: `hard_net_pnl_nonpositive=50`
- best 2x net PnL: -550.00
- median 2x net PnL: -2291.62
- median max underwater days: 1891
- median trades: 769

Interpretation: `bear_rally_fade_short_v1` did not produce positive train-only expectancy on either LINKUSDT or BTCUSDT. It should not be iterated as another entry-signal sampler. The useful residual signal is that the short entries lost far less than exposure-matched short-and-hold, which suggests any next short-side experiment should be about volatility/risk scaling or drift-neutral construction, not simply changing RSI thresholds.

### Volatility/Risk Scaling Diagnostic

Fable5 recommended sizing-only experimentation after both LINKUSDT and BTCUSDT `bear_rally_fade_short_v1` diagnostics produced `positive_net_count=0`. This experiment keeps entries, exits, costs, hard gates, and freeze gates unchanged.

Implemented candidate fields:

- `vol_scaling`: `none`, `inverse_atr`, or `vol_target`
- `vol_lookback_n`
- `vol_target_ann`
- `scale_min`
- `scale_max`

Sizing formula:

```text
atr_pct = ATR(atr_n) / close

if vol_scaling == inverse_atr:
  raw_scale = rolling_median(atr_pct, vol_lookback_n) / atr_pct
elif vol_scaling == vol_target:
  sigma_ann = stdev(log_returns, vol_lookback_n) * sqrt(365 * 24)
  raw_scale = vol_target_ann / sigma_ann
else:
  raw_scale = 1

risk_scale = clip(raw_scale, scale_min, scale_max)
risk_budget = equity * risk_per_trade * risk_scale
qty = min(risk_budget / risk_per_unit, equity * leverage_cap / entry_price)
```

Rules:

- scale is computed once on the signal bar and frozen for the trade
- leverage cap is not scaled
- invalid ATR/vol warmup skips the trade instead of defaulting to scale 1
- `vol_scaling=none` keeps legacy behavior and candidate IDs stable

Diagnostics record:

- `vol_scaling`
- `median_risk_scale`
- `scale_min_clamp_share`
- `scale_max_clamp_share`

LINKUSDT vol-scaled short diagnostic command:

```bash
python3 -m v9.contract.search \
  --symbol LINKUSDT \
  --samples 16 \
  --seed 20260720 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_bear_fade \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 150 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_LINKUSDT_bear_fade_volscale_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_LINKUSDT_bear_fade_volscale_diag80.md
```

LINKUSDT result:

- attempts: 80
- sampled: 0
- fully simulated candidates: 54
- positive-net candidates: 0
- main rejection: `hard_net_pnl_nonpositive=54`
- best 2x net PnL: -294.26
- median 2x net PnL: -2198.94
- median max underwater days: 1642
- scaling mix: `inverse_atr=23`, `vol_target=19`, `none=12`
- best candidate used `vol_target`, median risk scale 0.332, min clamp share 0.264, max clamp share 0.000

BTCUSDT vol-scaled short diagnostic command:

```bash
python3 -m v9.contract.search \
  --symbol BTCUSDT \
  --samples 16 \
  --seed 20260721 \
  --ranking-mode freeze_proxy \
  --sampling-profile freeze_bear_fade \
  --proxy-bootstrap-iterations 200 \
  --freeze-distribution-hard-gate \
  --freeze-gate-margin 1.0 \
  --min-hard-trades 150 \
  --max-attempts 80 \
  --out-json artifacts/v9/contract_lab/contract_search_BTCUSDT_bear_fade_volscale_diag80.json \
  --out-md artifacts/v9/contract_lab/contract_search_BTCUSDT_bear_fade_volscale_diag80.md
```

BTCUSDT result:

- attempts: 80
- sampled: 0
- fully simulated candidates: 48
- positive-net candidates: 0
- main rejection: `hard_net_pnl_nonpositive=48`
- best 2x net PnL: -476.15
- median 2x net PnL: -2359.29
- median max underwater days: 1895
- scaling mix: `vol_target=21`, `inverse_atr=15`, `none=12`

Interpretation: volatility/risk scaling reduced losses for some short-fade candidates but did not create positive train-only expectancy on LINKUSDT or BTCUSDT. It does not pass the acceptance rule. Do not extend the same short-fade entry with wider sizing sweeps unless a new structural edge hypothesis is added.

### Pair Mean-Reversion Diagnostic

After single-leg long, single-leg short, and volatility-scaled single-leg diagnostics failed to produce a robust positive train-only strategy, Fable5 recommended a drift-neutral pair mean-reversion diagnostic as a standalone module. This does not touch holdout and does not authorize paper/live trading.

Implemented module:

- `v9.contract.pair_mr`

Strategy:

- primary pair: `ETHUSDT/BTCUSDT`
- secondary diagnostic pairs: `SOLUSDT/ETHUSDT`, `LINKUSDT/ETHUSDT`
- spread: `log(Y) - beta * log(X)`
- beta: rolling OLS of `log(Y)` on `log(X)`, shifted so beta uses data through `t-1`
- z-score: rolling spread z-score
- entry:
  - `z <= -z_entry`: long spread
  - `z >= z_entry`: short spread
- exit:
  - `abs(z) <= z_exit`
  - `abs(z) >= z_stop`
  - `max_hold_bars`
- beta is frozen at entry
- beta outside `[0.25, 4.0]` is skipped

Cost/PnL:

- beta-weighted, gross-normalized spread exposure
- no intratrade rebalance
- 1x and 2x cost outputs
- cost is fee+slippage per leg per side, so a round trip has four leg-side charges
- no funding term in this first pair diagnostic

Grid:

- `beta_lookback`: 336, 720
- `z_lookback`: 168, 336
- `z_entry`: 1.5, 2.0, 2.5
- `z_exit`: 0.25, 0.5
- `z_stop`: 4.0
- `max_hold_bars`: 72, 168

Command:

```bash
python3 -m v9.contract.pair_mr \
  --out-json artifacts/v9/contract_lab/pair_mr_diag_grid_v1.json \
  --out-md artifacts/v9/contract_lab/pair_mr_diag_grid_v1.md
```

Result:

- rows: 144
- accepted: 0
- kill rule: true
- primary `ETHUSDT/BTCUSDT` rows: 48
- primary 1x positive rows: 0
- primary top5-excision survivors: 0
- secondary 1x positive rows:
  - `SOLUSDT/ETHUSDT`: 2
  - `LINKUSDT/ETHUSDT`: 0

Per-pair summary:

| pair | 1x positive | 2x positive | top5-excision survivors | median 1x pnl | max 1x pnl | median underwater days |
|---|---:|---:|---:|---:|---:|---:|
| `ETHUSDT/BTCUSDT` | 0 | 0 | 0 | -8043.21 | -4937.60 | 2390 |
| `LINKUSDT/ETHUSDT` | 0 | 0 | 0 | -8716.46 | -3618.84 | 1884 |
| `SOLUSDT/ETHUSDT` | 2 | 0 | 0 | -7173.70 | 1934.07 | 982 |

Interpretation: the primary ETH/BTC pair family fails immediately under the pre-committed kill rule. SOL/ETH had two 1x positive cells, but both failed 2x cost and top5-excision badly; the best 1x PnL cell had top5 share above 16 and top5-excised net PnL of -29226.90. This is not a robust pair edge. Do not widen this pair-MR grid or touch holdout based on this result.

### Cross-Sectional Momentum Diagnostic

After single-leg long, single-leg short, volatility-scaled short, and pair mean-reversion diagnostics failed to produce a robust train-only edge, Fable5 recommended testing a broader market-structure hypothesis: rank multiple coins by relative strength, go long the strongest names, and short the weakest names. This directly tests a coarse market/sector allocation idea instead of trying to recognize chart shapes on one symbol.

Implemented standalone module:

- `v9.contract.xsec_momentum`

Universe:

- `ADAUSDT`
- `AVAXUSDT`
- `BNBUSDT`
- `BTCUSDT`
- `ETHUSDT`
- `LINKUSDT`
- `SOLUSDT`
- `XRPUSDT`

Common train window:

- start: `2020-09-22T06:00:00+00:00`
- end: `2024-06-30T23:00:00+00:00`

Strategy:

- signal at close: `momentum = close[t - skip_h] / close[t - skip_h - lookback_h] - 1`
- rank all eight symbols cross-sectionally
- long top `K`, short bottom `K`
- equal weights: long legs sum to `+0.5`, short legs sum to `-0.5`, gross exposure `1.0`, net exposure `0.0`
- rebalance every `rebalance_h`
- costs charged on turnover at `10 bps` and `20 bps`

Grid:

- `lookback_h`: 72, 168, 336, 720
- `skip_h`: 0, 24
- `rebalance_h`: 24, 72
- `k`: 1, 2

Train-only gates:

- 10 bps Sharpe >= 1.0
- positive net return in at least 3 of 4 yearly buckets: 2021, 2022, 2023, 2024H1
- cross-sectional IC t-stat >= 2.0
- neighbor median Sharpe >= 0.5
- 20 bps Sharpe >= 0.5
- long/short legs not catastrophically one-sided
- acceptance requires at least 2 passing configs and adjacent passers

Command:

```bash
python3 -m v9.contract.xsec_momentum \
  --out-json artifacts/v9/contract_lab/xsec_momentum_grid_v1.json \
  --out-md artifacts/v9/contract_lab/xsec_momentum_grid_v1.md
```

Result:

- rows: 32
- accepted: true
- pass count: 5
- adjacent passers: true
- 10 bps Sharpe >= 1.0 rows: 11
- IC t-stat >= 2.0 rows: 10
- 10 bps positive-net rows: 28
- kill rule: false

Selected train-only candidate:

- selected artifact: `artifacts/v9/contract_lab/xsec_momentum_selected_train_candidate_v1.json`
- selection rule: highest neighbor median Sharpe among passing configs
- config: `lookback_h=336`, `skip_h=0`, `rebalance_h=24`, `k=2`
- 10 bps Sharpe: 1.576
- 20 bps Sharpe: 1.297
- 10 bps net PnL: 77901.38
- 20 bps net PnL: 46651.03
- 10 bps max drawdown: 0.327
- 20 bps max drawdown: 0.338
- IC t-stat: 2.212
- yearly net returns at 10 bps: 2021 2.264, 2022 0.533, 2023 0.721, 2024H1 0.021
- yearly net returns at 20 bps: 2021 1.813, 2022 0.362, 2023 0.555, 2024H1 -0.049
- BTC beta: approximately 0

Interpretation: this is the first v9 direction that passed its pre-registered train-only diagnostic gates. It supports the broader-market/rank-first path more than the single-symbol chart-pattern path. It is still not holdout-authorized, paper-authorized, or live-authorized. The max drawdown remains too high for risk-controlled deployment, and the 20 bps 2024H1 bucket is negative. Before any future holdout access, this needs an execution-timing/no-lookahead audit, turnover and final-exit cost audit, top-period concentration audit, risk hardening, and the normal preflight gate.

#### Cross-Sectional Momentum Risk Hardening And Final R72 Decision

Fable5 recommended a train-only risk hardening pass before spending any holdout or paper-trading attention. The first risk pass added:

- rank hysteresis: enter top/bottom `K`, exit only after a one-rank buffer
- volatility targeting: 30-day realized strategy-vol target, capped at gross exposure 1.0 or 1.5 depending on profile
- 30-day block bootstrap Sharpe p5
- per-symbol contribution concentration
- long/short leg Sharpe
- stricter 20 bps risk gates

Base risk command:

```bash
python3 -m v9.contract.xsec_momentum_risk \
  --bootstrap-iterations 1000 \
  --out-json artifacts/v9/contract_lab/xsec_momentum_risk_hardening_v1.json \
  --out-md artifacts/v9/contract_lab/xsec_momentum_risk_hardening_v1.md
```

Base risk result:

- rows: 30
- accepted profiles: none
- best near miss: `lookback_h=336`, `skip_h=0`, `rebalance_h=72`, `k=2`, `hysteresis1_vol20`
- near-miss 20 bps Sharpe: about 1.30
- near-miss 20 bps max drawdown: about 0.257
- failure: max drawdown stayed just above the 0.25 gate

Low-vol near-miss command:

```bash
python3 -m v9.contract.xsec_momentum_risk \
  --profile-set lowvol \
  --bootstrap-iterations 1000 \
  --out-json artifacts/v9/contract_lab/xsec_momentum_risk_lowvol_v1.json \
  --out-md artifacts/v9/contract_lab/xsec_momentum_risk_lowvol_v1.md
```

Low-vol result:

- rows: 24
- accepted profiles: none
- individual passing rows existed only around `lookback_h=336`, `skip_h=0`, `rebalance_h=72`, `k=2`
- `vol14`, `vol16`, and `vol18` all passed the individual 20 bps gates at this one structure
- surrounding `R24`, `L168`, `L720`, `skip24`, and `K1` checks failed

Fable5 then recommended one final train-side iteration, with no further tuning after it:

- fixed: `skip_h=0`, `k=2`, hysteresis enabled
- sweep: `lookback_h` in 288, 336, 432
- sweep: `rebalance_h` in 48, 72, 96
- sweep: volatility target in 14%, 16%, 18%
- center: `lookback_h=336`, `rebalance_h=72`, `vol_target=16%`
- score center again at 30 bps and 40 bps

Final R72 command:

```bash
python3 -m v9.contract.xsec_momentum_risk \
  --profile-set r72final \
  --grid-set r72_final \
  --bootstrap-iterations 1000 \
  --out-json artifacts/v9/contract_lab/xsec_momentum_r72_final_v1.json \
  --out-md artifacts/v9/contract_lab/xsec_momentum_r72_final_v1.md
```

Final R72 result:

- rows: 27
- decision artifact: `artifacts/v9/contract_lab/xsec_momentum_r72_final_decision_v1.json`
- accepted train-only: false
- center profile: `hysteresis1_vol16_cap100`
- center config: `lookback_h=336`, `skip_h=0`, `rebalance_h=72`, `k=2`
- center 20 bps Sharpe: 1.311
- center 20 bps max drawdown: 0.233
- center 20 bps 2024H1 return: 0.028
- center 30-day bootstrap Sharpe p5: 0.499
- center 30 bps Sharpe: 1.146
- center 40 bps Sharpe: 0.962
- non-center pass count: 8/26
- neighbor pass rate: 0.308, below the required 0.60
- connected axes: lookback, rebalance, and vol-target axes each had at least one passing face neighbor

Final checks:

- center passed 20 bps individual gates: true
- center bootstrap p5 >= 0.30: true
- connected axes >= 2: true
- neighbor pass rate >= 60%: false
- center 40 bps Sharpe >= 1.0: false

Interpretation: cross-sectional momentum v1 found a real train-only signal component, but not a robust enough strategy family. The center point survived normal 20 bps gates, but the plateau was too thin and the 40 bps stress failed. Per the final train iteration rule, do not widen this grid, move the center, lower the volatility target further, or add more overlays to rescue this family. Bench xsec momentum v1 as a component candidate only. It is not holdout-authorized, paper-authorized, or live-authorized. Next research should move to a structurally different signal family such as funding-rate carry, basis/funding plus momentum, or volatility-adjusted momentum.

### Safe Auto Research Runner

The v9 safe auto runner is allowed to run train-only research tasks in tmux, but it must never authorize holdout, paper trading, or live trading. It writes state and heartbeat information to:

- `state/v9_auto_research_state.json`
- `state/latest_strategy_summary.txt`

Runner command:

```bash
python3 -m v9.contract.auto_research
```

The active tmux session is:

```bash
tmux new -d -s v9_auto_research \
  "cd /root/.openclaw/workspace/kimi-shared-brain && python3 -m v9.contract.auto_research > logs/v9_auto_research_tmux.log 2>&1"
```

Safety invariants:

- `holdout_authorized=false`
- `paper_trading_authorized=false`
- `live_trading_authorized=false`
- train-only candidate discovery pauses the runner for manual review
- every task has a timeout
- heartbeat is written while a long task is running

Initial task queue:

- `xsec_ohlcv_core_v1`
- `xsec_ohlcv_defensive_v1`
- `xsec_ohlcv_slow_v1`
- `xsec_ohlcv_fast_v1`

`xsec_ohlcv_core_v1` result:

- artifact: `artifacts/v9/contract_lab/xsec_ohlcv_core_v1.json`
- rows: 16
- pass count: 0
- accepted train-only: false
- best rows had high Sharpe but failed max drawdown, so no candidate was selected

`xsec_ohlcv_defensive_v1` result:

- artifact: `artifacts/v9/contract_lab/xsec_ohlcv_defensive_v1.json`
- selected candidate artifact: `artifacts/v9/contract_lab/xsec_ohlcv_defensive_candidate_v1.json`
- rows: 24
- pass count: 4
- accepted train-only: true
- runner status after discovery: paused for manual review

Selected defensive candidate:

- config: `lookback_h=336`, `skip_h=0`, `rebalance_h=72`, `k=2`, `score_mode=risk_adj_mom`, `market_filter_h=720`, `vol_target_ann=0.12`
- 20 bps Sharpe: 1.916
- 20 bps max drawdown: 0.224
- 20 bps net PnL: 45792.54
- 20 bps 30-day bootstrap Sharpe p5: 0.957
- 40 bps Sharpe: 1.741
- 40 bps max drawdown: 0.246
- top positive symbol share: 0.198
- average gross exposure: 0.234
- daily turnover: 0.060
- equal-weight benchmark Sharpe excess: 0.558
- drawdown ratio versus equal-weight benchmark: 0.273
- yearly 20 bps returns: 2021 2.495, 2022 -0.205, 2023 0.710, 2024H1 0.174

Interpretation: the safe auto runner successfully found a train-only candidate and stopped for manual review as designed. This is not holdout-authorized, paper-authorized, or live-authorized. The candidate is stronger than the earlier bench-only xsec momentum family because it combines a 720h market filter, risk-adjusted momentum, lower volatility target, low gross exposure, lower turnover, 40 bps survival, and low symbol concentration. The main red flag is the negative 2022 bucket. Next step must be a deeper train-only review with higher bootstrap iterations, plateau checks, and no parameter movement.

Deep train-only review of the selected defensive candidate:

- artifact: `artifacts/v9/contract_lab/xsec_ohlcv_defensive_candidate_v1_deep_review.json`
- bootstrap iterations: 2000
- parameters moved: none
- status: `deep_train_only_review_passed`
- holdout authorized: false
- paper trading authorized: false
- live trading authorized: false

Deep review checks:

- 20 bps Sharpe >= 1.2: true
- 20 bps max drawdown <= 25%: true
- 40 bps Sharpe >= 1.0: true
- 60 bps Sharpe >= 0.8: true
- 20 bps bootstrap Sharpe p5 >= 0.5: true
- 40 bps bootstrap Sharpe p5 >= 0.25: true
- 60 bps bootstrap Sharpe p5 > 0: true
- 20 bps 2024H1 return positive: true
- 20 bps top positive symbol share <= 40%: true

Deep review metrics:

- 20 bps Sharpe: 1.916
- 20 bps max drawdown: 0.224
- 20 bps bootstrap Sharpe p5: 1.115
- 40 bps Sharpe: 1.741
- 40 bps max drawdown: 0.246
- 40 bps bootstrap Sharpe p5: 0.920
- 60 bps Sharpe: 1.562
- 60 bps max drawdown: 0.267
- 60 bps bootstrap Sharpe p5: 0.725

Interpretation: the defensive candidate survived a stricter train-only review without moving parameters. It remains blocked from holdout, paper, and live until a formal preflight package exists. The negative 2022 bucket still needs explicit review; do not ignore it just because aggregate metrics are strong.

Execution-log analyzer command:

```bash
python3 scripts/analyze_execution_log_v9.py \
  --input artifacts/v9/trade_logs/v8_link_candidate1_train_trades.jsonl \
  --cutoff "2024-06-30 23:59:59" \
  --out artifacts/v9/trade_logs/v8_link_candidate1_execution_analysis.json \
  --md artifacts/v9/trade_logs/v8_link_candidate1_execution_analysis.md
```

The analyzer checks:

- no execution timestamp after the train cutoff
- cash/equity reconstruction consistency
- fee model consistency
- timestamp monotonicity within each scenario/cost stream
- secondary regime event coverage
- positive event-path net PnL
- daily-resampled event-path max drawdown

Dry-run analyzer result for v8 LINK candidate 1:

- `passed=false`
- `events=7866`
- `failures=108`
- failure summary: `secondary_regime_coverage_failed=72`, `net_pnl_eventpath_not_positive=21`, `daily_max_dd_exceeds=15`

Do not report win rate, profit factor, average trade PnL, holding period, event-level Sharpe, or per-trade CVaR from this analyzer. The current log contains spot inventory execution events, not independent round-trip contract trades.

## Image or Chart Pattern Recognition

Do not prioritize image/chart pattern recognition for v9.

The factory already overfit numeric features in v8. Adding image features before validation is stronger will expand the search space and increase false positives. Revisit this only after the validation harness, decorrelation gate, regime gate, and per-trade contracts are working.

## Pass Criteria

Historical family pass, if using any burned holdout data:

- Tightened family gate: `3/3` pass if the family size is three.
- Each candidate must pass a standalone 50 bps cost tier.
- Survival rate must be 1.0 under the pre-registered scenario design.
- Worst-case alpha must be positive.
- CVaR alpha must be positive.
- Max drawdown must stay at or below 20%.
- Trade count must stay inside pre-registered bounds.
- Candidate family must satisfy the decorrelation gate before holdout.

Every holdout result must also have a read-only risk report generated from the existing holdout JSON:

```bash
python3 scripts/holdout_risk_report.py \
  --holdout results/holdout/<batch_id>_holdout.json \
  --out results/analysis/<batch_id>_holdout_risk_report.json \
  --md results/analysis/<batch_id>_holdout_risk_report.md
```

The report must include per-cost-tier metrics and scenario-block bootstrap confidence intervals. This report is analysis of a spent holdout, not permission to retune.

## Preflight Gate

No candidate family may touch historical holdout or forward-shadow data until a train-only preflight manifest exists.

Command shape:

```bash
python3 scripts/v9_preflight_gate.py \
  --prereg docs/preregistration_v9.md \
  --regime-report artifacts/v9/regime_report.json \
  --freeze-report results/frozen/<batch_id>.json \
  --exec-summary artifacts/v9/trade_logs/<batch_id>_train_trades_summary.json \
  --exec-analysis artifacts/v9/trade_logs/<batch_id>_execution_analysis.json \
  --out artifacts/v9/preflight/<batch_id>_preflight.json \
  --md artifacts/v9/preflight/<batch_id>_preflight.md
```

The preflight gate is fail-closed. Missing input, hash mismatch, missing embargo marker, failed freeze gate, failed execution integrity, or failed execution analysis all produce `NO_GO`.

`holdout_authorized` is always false unless both are true:

- `verdict=GO`
- the command is rerun with explicit `--human-ack`

Dry-run result for the v8 LINK candidate 1 package:

- output: `artifacts/v9/preflight/v8_link_candidate1_preflight.json`
- verdict: `NO_GO`
- blocking gates: `freeze_family_frozen`, `execution_analysis_passed`
- holdout authorized: `false`

This gate only certifies train-only procedural integrity. It does not imply profitability and does not override the burned-holdout no-retuning rule.

Fresh forward-shadow gate before paper trading:

- Run on data after the v9 protocol is finalized.
- Minimum duration: 30 calendar days for 1h strategies; longer for slower timeframes.
- No parameter changes during shadow.
- Paper trading can be considered only if the forward-shadow result agrees with the historical pass.

## No-Retuning Rule

The 2024-08 through 2026-05 LINKUSDT holdout is burned. No parameter, feature, gate threshold, seed, or candidate-selection choice in any future version may be informed by any statistic computed on post-2024-06 data, except the single recorded binary outcome `family_passed=false`.

Each frozen batch gets exactly one holdout evaluation ever; a failed batch is discarded unmodified. Every evaluation touching post-train data is logged in `docs/holdout_ledger.md` before or immediately after it runs.
