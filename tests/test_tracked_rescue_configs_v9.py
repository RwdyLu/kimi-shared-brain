from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESCUE_CONFIG = ROOT / "configs/v9/rescue/xsec_active_recent_hedged_v1_progress_rescue_ee60d5ebbf1e.json"
LATEST_RESCUE_CONFIG = ROOT / "configs/v9/rescue/xsec_active_recent_hedged_v1_progress_rescue_d0d07fd61c59.json"


def test_active_recent_progress_rescue_config_is_tracked_and_stable() -> None:
    raw = RESCUE_CONFIG.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha1(raw).hexdigest() == "ee60d5ebbf1ef5df62820e290b65c9bb7d6574bc"
    assert len(payload) == 132
    assert payload[0] == {
        "cooldown_h": 72,
        "drawdown_stop": 0.08,
        "hedge_ratio": 0.25,
        "k": 2,
        "lookback_h": 168,
        "market_confirm_h": 0,
        "market_drawdown_limit": 0.0,
        "market_filter_h": 504,
        "n_tranches": 1,
        "portfolio_mode": "hedged_long",
        "rebalance_h": 72,
        "score_mode": "risk_adj_mom",
        "skip_h": 0,
        "vol_target_ann": 0.06,
    }


def test_latest_active_recent_progress_rescue_config_is_tracked_and_stable() -> None:
    raw = LATEST_RESCUE_CONFIG.read_bytes()
    payload = json.loads(raw)

    assert hashlib.sha1(raw).hexdigest() == "d0d07fd61c5960868c87cd4f307925683318339a"
    assert len(payload) == 236
    assert payload[0] == {
        "cooldown_h": 72,
        "drawdown_stop": 0.08,
        "hedge_ratio": 0.25,
        "k": 2,
        "lookback_h": 168,
        "market_confirm_h": 0,
        "market_drawdown_limit": 0.0,
        "market_filter_h": 504,
        "n_tranches": 1,
        "portfolio_mode": "hedged_long",
        "rebalance_h": 72,
        "score_mode": "risk_adj_mom",
        "skip_h": 0,
        "vol_target_ann": 0.06,
    }
