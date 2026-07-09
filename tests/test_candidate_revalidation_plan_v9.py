from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_candidate_revalidation_plan.py"
SPEC = importlib.util.spec_from_file_location("v9_candidate_revalidation_plan", SCRIPT)
assert SPEC and SPEC.loader
plan_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan_mod)


def write_artifact(path: Path, *, kind: str, config: dict, row_config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": kind,
                "summary": {"accepted_train_only": True, "pass_count": 1, "rows": 1},
                "symbols": config.get("symbols", []),
                "config": config,
                "selection_validation": {"effective_trials": 123, "n_configs_tested": 1},
                "rows": [{"advance_passed": True, "config": row_config}],
            }
        )
    )


def test_build_revalidation_plan_groups_xsec_and_tsmom_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    xsec_artifact = tmp_path / "artifacts/v9/contract_lab/xsec.json"
    tsmom_artifact = tmp_path / "artifacts/v9/contract_lab/tsmom.json"
    write_artifact(
        xsec_artifact,
        kind="xsec_ohlcv_factory_v1_train_only_grid",
        config={
            "train_start": "2017-08-01",
            "train_end": "2024-01-31 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "lookbacks_h": [336],
        },
        row_config={
            "lookback_h": 336,
            "skip_h": 0,
            "rebalance_h": 168,
            "k": 2,
            "score_mode": "risk_adj_mom",
            "market_filter_h": 1008,
            "vol_target_ann": 0.08,
        },
    )
    write_artifact(
        tsmom_artifact,
        kind="tsmom_factory_v1_train_only_grid",
        config={
            "train_start": "2017-08-01",
            "train_end": "2024-01-31 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "lookbacks_h": [720, 1440],
        },
        row_config={
            "asset_vol_target_ann": 0.25,
            "portfolio_vol_target_ann": 0.06,
            "no_trade_band": 0.3,
            "vote_threshold": 0.5,
            "market_filter_h": 720,
        },
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "candidates_found": [
                    {
                        "task": "xsec_ohlcv_cont_full_202401_hq_dd_plateau_abc123",
                        "status": "manual_review_required",
                        "output_json": str(xsec_artifact),
                    },
                    {
                        "task": "tsmom_cont_full_202401_tsmom_core_slow_cost_guard_def456",
                        "status": "manual_review_required",
                        "output_json": str(tsmom_artifact),
                    },
                    {
                        "task": "duplicate",
                        "status": "manual_review_required",
                        "output_json": str(xsec_artifact),
                        "duplicate_of": "xsec_ohlcv_cont_full_202401_hq_dd_plateau_abc123",
                    },
                ]
            }
        )
    )

    plan = plan_mod.build_revalidation_plan(state, out_dir=tmp_path / "revalidation")

    assert plan["group_count"] == 2
    assert plan["config_count"] == 2
    assert plan["holdout_authorized"] is False
    assert plan["paper_trading_authorized"] is False
    assert plan["live_trading_authorized"] is False
    commands = [" ".join(group["command"]) for group in plan["groups"]]
    assert any("v9.contract.xsec_ohlcv_factory" in command and "--config-list-json" in command for command in commands)
    assert any("v9.contract.tsmom_factory" in command and "core_slow_cost_guard" in command for command in commands)
    for group in plan["groups"]:
        assert Path(group["config_json"]).exists()
