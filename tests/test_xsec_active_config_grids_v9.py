from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_active_config_grids.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_active_config_grids", SCRIPT)
assert SPEC and SPEC.loader
grid_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grid_mod)


def test_active_recent_hedged_grid_matches_cloud_fingerprint() -> None:
    payload = grid_mod.grid_payload("hq_active_recent_hedged_v1")
    fingerprint = grid_mod.grid_fingerprint("hq_active_recent_hedged_v1", payload, "4cd1599")

    assert fingerprint == "9ba29be50b1a1a783089c93c2572dbef3c89b396"
    assert len(payload["configs"]) == 384
    assert payload["configs"][0] == {
        "cooldown_h": 72,
        "drawdown_stop": 0.08,
        "hedge_ratio": 0.25,
        "k": 2,
        "lookback_h": 168,
        "market_confirm_h": 0,
        "market_drawdown_limit": 0.0,
        "market_filter_h": 0,
        "n_tranches": 1,
        "portfolio_mode": "hedged_long",
        "rebalance_h": 48,
        "score_mode": "risk_adj_mom",
        "skip_h": 0,
        "vol_target_ann": 0.04,
    }


def test_fast_breakout_hedged_grid_matches_cloud_fingerprint() -> None:
    payload = grid_mod.grid_payload("hq_fast_breakout_hedged_v1")
    fingerprint = grid_mod.grid_fingerprint("hq_fast_breakout_hedged_v1", payload, "65f092f")

    assert fingerprint == "abe379cd37467fad60c3c1a5def2f33f2a8b52d9"
    assert len(payload["configs"]) == 384
    assert payload["configs"][0] == {
        "cooldown_h": 24,
        "drawdown_stop": 0.08,
        "hedge_ratio": 0.25,
        "k": 2,
        "lookback_h": 72,
        "market_confirm_h": 0,
        "market_drawdown_limit": 0.0,
        "market_filter_h": 0,
        "n_tranches": 1,
        "portfolio_mode": "hedged_long",
        "rebalance_h": 48,
        "score_mode": "vol_breakout",
        "skip_h": 0,
        "vol_target_ann": 0.03,
    }


def test_write_grid_outputs_config_json(tmp_path) -> None:
    result = grid_mod.write_grid("hq_fast_breakout_hedged_v1", tmp_path)
    path = Path(result["path"])
    payload = json.loads(path.read_text())

    assert result["short"] == "abe379cd3746"
    assert path.name == "hq_fast_breakout_hedged_v1_abe379cd3746.json"
    assert len(payload["configs"]) == result["config_count"] == 384
