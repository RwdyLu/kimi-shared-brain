# Strategy Approval Pipeline V7

This project treats GA output as research evidence, not as trading approval.

## Contract

The approval chain is:

```text
Binance public kline cache
  -> data audit / manifest / normalized parquet
  -> GA discovery
  -> deterministic replay
  -> independent recheck seeds
  -> cost / delay / jitter / walk-forward / Monte Carlo stress
  -> immutable strategy artifact
  -> Freqtrade dry-run bridge
  -> manual paper approval
  -> live canary approval
```

Internal pass is not enough:

```text
FOUND_INTERNAL_CANDIDATE != FOUND_VALIDATED_CANDIDATE != FOUND_PAPER_READY
```

`FOUND_STRATEGY_READY.txt` remains reserved for a future final approval state. Raw
GA candidates must not be routed into Freqtrade or live trading.

## Layers

### Data

`scripts/binance_kline_data_audit.py` audits `data/binance_public_cache` and emits:

- `data/manifests/<stage>/<SYMBOL>_<timeframe>_<start>_<end>.json`
- `data/audits/<stage>/binance_kline_audit_summary.json`
- `data/audits/<stage>/gap_report.json`
- `data/audits/<stage>/timestamp_unit_report.json`
- `data/audits/<stage>/checksum_report.json`
- optional canonical parquet under `data/normalized/klines_<timeframe>/`

The audit normalizes timestamps to milliseconds, detects Binance public-data
microsecond inputs, checks duplicate bars, missing internal bars, OHLC validity,
and records file/data hashes. Existing parquet cache cannot prove raw Binance
checksum validity, so checksum fields are explicitly marked as unavailable unless
raw zip/checksum files are added later.

Small early-history bar gaps are reported as warnings when they stay below the
configured missing-bar fraction. Full missing months between a symbol's observed
start and end, unreadable files, duplicate bars, invalid OHLC rows, or large gap
fractions mark a symbol manifest invalid for research.

The search and approval runners now consume the manifest layer through
`scripts/data_health_gate.py`. Scenario generation is allowed to use only
manifest-approved `valid_months`. A symbol can still be used after its Binance
listing date when it has a contiguous valid tradable range; missing pre-listing
history is not treated as corruption. Missing months or bad bars inside the
tradable history split the valid ranges and cannot be sampled.

Every staged run writes a run manifest:

```text
state/run_manifest_v7_<stage>_<profile>.json
```

The run manifest records requested symbols, allowed symbols, blocked symbols,
the data audit summary hash, and the active gate:

```text
strict_valid_month_manifest_required
```

### Search

GA search remains the source of internal candidates. It may optimize robust
fitness and regime specialists, but its own scenario bundle is training data.
Its output can only create `FOUND_INTERNAL_CANDIDATE.txt`.

### Approval

`scripts/strategy_approval_gate_v7.py` is the approval authority. It applies:

- deterministic replay
- independent validation seeds
- cost stress
- signal delay
- parameter jitter
- random negative controls
- walk-forward validation
- Monte Carlo bootstrap
- locked holdout metadata
- failed public scenarios into the adversarial bank

Failed public validation scenarios may be added to the adversarial bank. Locked
holdout failures must not be recycled into the same training cycle.

### Artifact

`scripts/export_strategy_artifact_v7.py` exports immutable research artifacts:

- `manifest.json`
- `genome.json`
- `metrics.json`
- `approval_summary.json` when available
- `scenario_internal.json` when available
- engine hashes and data-audit hashes

Current artifacts do not yet contain trade-level parquet or full equity curves
because the evaluator does not emit those tables yet.

Artifacts include repo commit, engine hashes, data-audit hash, per-symbol data
manifest hash, cost-bps semantics, manual approval stub, and whether Freqtrade
export is allowed. Artifact export refuses invalid data-gate symbols by default.

### Freqtrade

`scripts/freqtrade_dry_run_bridge.py` creates a dry-run scaffold only:

- spot mode
- no leverage
- no API keys
- `dry_run: true`
- `initial_state: stopped`
- external signal CSV bridge

Freqtrade is an execution/paper layer, not the strategy approval engine.

By default the bridge refuses artifacts whose approval status is not paper-ready.
For integration smoke tests only, use:

```bash
python3 scripts/freqtrade_dry_run_bridge.py --artifact <artifact> --allow-unvalidated-smoke-test
```

Smoke output is marked not paper approved and not live ready.

## Legacy Ready File

`FOUND_STRATEGY_READY.txt` is legacy only and must not be consumed by execution
scripts. Current state files are:

```text
FOUND_INTERNAL_CANDIDATE.txt
FOUND_VALIDATED_CANDIDATE.txt
FOUND_PAPER_READY.txt
FOUND_LIVE_CANARY_READY.txt
FOUND_PRODUCTION_READY.txt
```
