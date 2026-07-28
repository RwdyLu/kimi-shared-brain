# v8 LINK Batch 1 Holdout Postmortem

Date: 2026-07-06

## Decision

No-go. The v8 LINK batch is not paper-trading ready.

The batch failed the pre-registered holdout protocol:

- Frozen batch: `results/frozen/v8_link_candidates_batch1_20260706.json`
- Holdout report: `results/holdout/v8_link_batch1_holdout_20260706.md`
- Holdout JSON: `results/holdout/v8_link_batch1_holdout_20260706.json`
- Protocol: `docs/holdout_protocol_v8_batch1.md`
- Effective scored holdout: 2024-08 through 2026-05
- Passed candidates: 0/3
- Family pass requirement: at least 2/3 candidates pass

Owner-facing summary:

> v8's LINK candidates passed training but failed the pre-registered out-of-sample test. They lost money in half of the tested market windows, with worst-case alpha around -4% to -6% versus benchmark, concentrated in 2025-08 through 2026-03. Per our own protocol, this failed holdout is final: this batch is discarded, not tweaked. Nothing goes to paper trading.

## Holdout Metrics

| Candidate | Train epoch | Survival | Min alpha | CVaR alpha | Avg alpha | Max DD | Avg trades | Decision |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 263 | 0.500 | -0.063753 | -0.042332 | 0.010846 | 0.1700 | 90.65 | Fail |
| 2 | 263 | 0.500 | -0.062204 | -0.041074 | 0.010172 | 0.1676 | 97.78 | Fail |
| 3 | 263 | 0.500 | -0.064852 | -0.044234 | 0.011398 | 0.1703 | 81.44 | Fail |

The drawdown and trade-count gates passed. The failed gates were survival, worst-case alpha, CVaR alpha, and holdout average alpha relative to training.

## What This Means

The risk limits were not the primary failure. The edge did not survive out-of-sample.

The train-qualified candidates were too similar to count as independent family members. All three frozen candidates came from epoch 263 and behaved almost identically in holdout. Future family gates must require candidate diversity before freezing.

The 2024-08 through 2026-05 LINK holdout is now burned. It may be used as a logged failure record, but not as a tuning target.

## No-Retuning Rule

The 2024-08 through 2026-05 LINKUSDT holdout is burned. No parameter, feature, gate threshold, seed, or candidate-selection choice in any future version may be informed by any statistic computed on post-2024-06 data, except the single recorded binary outcome `family_passed=false`.

Each frozen batch gets exactly one holdout evaluation. A failed batch is discarded unmodified. Evaluating the remaining seven train-qualified LINK candidates on the same holdout is prohibited because it would be retuning by selection.

## Follow-Up

Required before any v9 search:

- Create and maintain a holdout ledger.
- Add a candidate decorrelation gate before freezing any family.
- Pre-register v9 before running it.
- Treat image/chart recognition as lower priority until the validation harness can separate real edge from overfit.
- Add a coarse regime exposure gate only if it is trained strictly on pre-holdout data and specified in the v9 preregistration.
