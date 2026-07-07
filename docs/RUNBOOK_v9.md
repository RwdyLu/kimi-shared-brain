# v9 Train-Only Research Runbook

This runbook rebuilds the v9 train-only research runner on a new machine. It does not authorize holdout, paper trading, or live trading.

## Scope

- Repository: `git@github.com:RwdyLu/kimi-shared-brain.git`
- Train window default: `2017-08-01` to `2024-06-30 23:59:59`
- Embargo start: `2024-07-01`
- Runner: `python3 -m v9.contract.auto_research --continue-after-candidate`
- Outputs: `artifacts/v9/contract_lab/`, `logs/v9_auto_research/`, `state/v9_auto_research_state.json`

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

## Safety Invariants

- Auto research tasks may only call `python3 -m v9.contract.xsec_ohlcv_factory`.
- The runner rejects task commands containing `holdout`, `paper`, `live`, `freqtrade`, `exchange`, `api-key`, `apikey`, `secret`, or `token`.
- The runner rejects any task where `--train-end` is on or after `--embargo-start`.
- `load_symbol_1h()` also refuses data on or after `embargo_start`.
- Candidate discovery stops at `manual_review_required`; it does not launch holdout, paper trading, or live trading.

## Promotion Rule

Train-only candidates are research leads, not tradable strategies. A separate human decision is required before any future holdout, paper trading, or live trading workflow.
