# v9 Train-Only Research Runbook

This runbook rebuilds the v9 train-only research runner on a new machine. It does not authorize holdout, paper trading, or live trading.

## Scope

- Repository: `git@github.com:RwdyLu/kimi-shared-brain.git`
- Train window default: `2017-08-01` to `2024-06-30 23:59:59`
- Embargo start: `2024-07-01`
- Runner: `python3 -m v9.contract.auto_research --mode continuous --continue-after-candidate`
- Outputs: `artifacts/v9/contract_lab/`, `logs/v9_auto_research/`, `state/v9_auto_research_state.json`
- XSEC paper evidence: `state/xsec_paper_ledger.jsonl`, `artifacts/v9/paper/xsec_cost_evidence.csv`
- Live-canary review gate: `state/xsec_live_canary_readiness_gate_state.json`

## New Machine Setup

```bash
git clone git@github.com:RwdyLu/kimi-shared-brain.git
cd kimi-shared-brain
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-v9.txt
pytest -q tests/test_auto_research_v9.py tests/test_xsec_ohlcv_factory_v9.py
```

The market data cache is intentionally not stored in Git. Rebuild it with the project data scripts, or copy the cache from the cloud host:

```bash
mkdir -p data/binance_public_cache
rsync -av kimi-claw-cf:/root/.openclaw/workspace/kimi-shared-brain/data/binance_public_cache/ data/binance_public_cache/
```

## Start Safe Auto Research

```bash
./scripts/start_train_only.sh v9_auto_research
```

By default this starts continuous train-only research:

```bash
python3 -m v9.contract.auto_research \
  --mode continuous \
  --continue-after-candidate \
  --target-distinct-candidates 0 \
  --planner-batch-size 3 \
  --planner-preset-mode xsec_first \
  --max-cycles 0
```

`--max-cycles 0` means no explicit cycle limit. `--target-distinct-candidates 0` means the runner records candidate milestones but does not stop because a candidate count was reached. If the deterministic planner has no new task, the runner enters `idle` and waits with backoff for new code, data, or planner space.

`--planner-preset-mode xsec_first` spends new cycles on XSEC first because the current validated paper candidate came from XSEC. Set `PLANNER_PRESET_MODE=balanced` before `start_train_only.sh` to restore the older mixed schedule.

The runner still stops for a manual stop file, low disk, repeated task failure, or an explicit operator budget such as `--max-cycles` or `--max-hours`.

To stop gracefully after the current task:

```bash
mkdir -p control
touch control/STOP
```

To keep the train-only runner alive after accidental tmux exits, add a cron monitor:

```bash
* * * * cd /root/.openclaw/workspace/kimi-shared-brain && ./scripts/ensure_train_only_running.sh v9_auto_research_continuous >> logs/v9_auto_research/ensure.log 2>&1
```

The ensure script does not start anything while `control/STOP` exists. It also refuses to auto-restart after `disk_guard`, `failure_fuse`, or explicit budget stops unless `FORCE_RESTART=1` is set by an operator.

Check status without reading full logs:

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("state/v9_auto_research_state.json")
j = json.loads(p.read_text())
print({k: j.get(k) for k in [
    "status", "reason", "current_task", "active_task",
    "holdout_authorized", "paper_trading_authorized", "live_trading_authorized",
]})
print("candidates_found=", j.get("candidates_found", []))
PY
```

## Start XSEC Paper Evidence Stack

Only run this after `state/xsec_paper_readiness_gate_state.json` exists and says `paper_trading_authorized=true`.

```bash
./scripts/start_xsec_paper_stack.sh
```

This starts two tmux sessions:

- `xsec_paper_shadow`: recalculates the paper target weights, writes the signal CSV, appends a hash-chained paper ledger, and records public bid/ask spread evidence.
- `xsec_live_canary_gate`: periodically evaluates whether paper evidence is ready for a live-canary human review.

Important outputs:

```text
state/xsec_paper_shadow_state.json
state/xsec_paper_ledger.jsonl
artifacts/v9/paper/xsec_cost_evidence.csv
state/xsec_live_canary_readiness_gate_state.json
artifacts/v9/paper/xsec_live_canary_review.txt
```

The live-canary gate requires wall-clock paper evidence, not just backtest timestamps:

- valid hash-chained ledger
- at least 12 weeks of ledger wall-clock age
- no ledger gap above 48 hours
- at least 9 target-weight rebalance events
- paper drawdown under the configured max
- observed spread cost percentile under the assumed 40 bps cost
- matching manual approval file at `state/LIVE_CANARY_APPROVAL.json`

Even when all checks pass, the gate keeps `live_trading_authorized=false`. It only writes a review artifact; execution remains a separate explicit operator step.

## Safety Invariants

- Auto research tasks may only call approved train-only factory modules:
  `v9.contract.xsec_ohlcv_factory` or `v9.contract.tsmom_factory`.
- The runner rejects task commands containing `holdout`, `paper`, `live`, `freqtrade`, `exchange`, `api-key`, `apikey`, `secret`, or `token`.
- The runner rejects any task where `--train-end` is on or after `--embargo-start`.
- `load_symbol_1h()` also refuses data on or after `embargo_start`.
- Candidate discovery stops at `manual_review_required`; it does not launch holdout, paper trading, or live trading.
- Continuous mode writes `state/v9_auto_research_explored.jsonl` so restarts avoid repeating completed task fingerprints.
- Paper shadow and live-canary gate never submit orders and never set `live_trading_authorized=true`.

## Promotion Rule

Train-only candidates are research leads, not tradable strategies. A separate human decision is required before any future holdout, paper trading, or live trading workflow.
