# Holdout Protocol v8 Batch 1

Created: 2026-07-06

## Batch

- Batch id: `v8_link_batch1_20260706`
- Frozen candidates: `results/frozen/v8_link_candidates_batch1_20260706.json`
- Freeze rule: earliest three `LINKUSDT` qualified candidates by epoch, then score.
- Later v8 candidates are excluded from this batch to avoid cherry-picking.

## Windows

- Train/search window already consumed: `2017-08` through `2024-06`
- Holdout window for this batch: `2024-07` through `2026-05`
- Fresh forward data reserved after holdout: `2026-06` onward

`2026-06` and later must not be used to tune this batch. It is reserved for fresh confirmation or paper trading.

## Evaluation

- Symbol: `LINKUSDT`
- Timeframe: `1h`
- Scenarios: `24`
- Costs: `20,30,50` bps
- Candidate source: frozen JSON only
- The holdout runner must not read later v8 `qualified` rows or search state except for the frozen candidate genomes.
- The holdout runner must run once for this batch. Any rerun must be labeled invalid unless it is a byte-for-byte deterministic rerun of the same code, inputs, candidates, and protocol.

## Gates

A candidate passes holdout only if all are true:

- `survival_rate >= 1.0`
- `min_alpha > 0.0`
- `cvar_alpha > 0.0`
- `max_drawdown <= 0.20`
- `avg_alpha >= train_avg_alpha / 3`
- Average trades are within a proportional holdout range: `10 <= avg_trades_per_scenario <= 190`
- `max_trades_per_scenario <= 720`

The family passes only if at least `2 of 3` frozen candidates pass.

If only one candidate passes, treat it as noise. If zero pass, the batch is dead.

## Consequences

- Passing this holdout does not mean production-ready.
- Passing means the family can enter paper preparation.
- Failing means this batch must not be retuned against the same holdout window.
- A failed batch can only be followed by a new strategy family, new information source, or forward data collected after `2026-06`.

## Notes

The existing LunarGenome engine is a spot-like inventory and rebalance system. It is not a contract ticket engine. Holdout success here must be interpreted as a spot-like strategy result, not as permission to run leveraged futures.
