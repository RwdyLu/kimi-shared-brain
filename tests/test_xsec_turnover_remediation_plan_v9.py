from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_turnover_remediation_plan.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_turnover_remediation_plan", SCRIPT)
assert SPEC and SPEC.loader
plan_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan_mod)


BASE_CONFIG = {
    "lookback_h": 672,
    "skip_h": 0,
    "rebalance_h": 240,
    "k": 3,
    "score_mode": "risk_adj_mom",
    "market_filter_h": 1008,
    "vol_target_ann": 0.06,
    "n_tranches": 1,
}


def write_family_status(path: Path) -> str:
    family_key = json.dumps(
        {
            "artifact": "xsec_ohlcv_cont_full_202402_hq_dd_plateau_8106b2112912",
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "k": 3,
            "market_filter_h": 1008,
            "rebalance_h": 240,
            "score_mode": "risk_adj_mom",
            "n_tranches": 1,
        },
        sort_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "v9_train_only_family_status_v1",
                "families": {
                    family_key: {
                        "status": "family_rejected_train_stress",
                        "tags": ["cost_sensitive", "needs_turnover_reduction"],
                        "source_artifact": "artifact.json",
                        "source_report": "stress.json",
                        "example_configs": [BASE_CONFIG],
                    },
                    "ignored": {
                        "status": "family_rejected_train_stress",
                        "tags": ["phase_sensitive"],
                        "example_configs": [BASE_CONFIG],
                    },
                },
            }
        )
    )
    return family_key


def test_build_turnover_remediation_plan_generates_tranche_cadence_grid(tmp_path) -> None:
    status_path = tmp_path / "artifacts/v9/reviews/FAMILY_STATUS.json"
    family_key = write_family_status(status_path)

    plan = plan_mod.build_plan(status_path)

    assert plan["holdout_authorized"] is False
    assert plan["paper_trading_authorized"] is False
    assert plan["live_trading_authorized"] is False
    assert plan["rescue_config_count"] == 9
    assert len(plan["selected_families"]) == 1
    assert plan["selected_families"][0]["family_key"] == family_key
    assert {row["n_tranches"] for row in plan["configs"]} == {2, 3, 4}
    assert {row["rebalance_h"] for row in plan["configs"]} == {240, 360, 480}
    assert all(row["parent_family"] == family_key for row in plan["configs"])
    assert all(row["remediation"] == "turnover_reduction_tranche_cadence" for row in plan["configs"])


def test_turnover_remediation_plan_script_writes_factory_config_list(tmp_path) -> None:
    status_path = tmp_path / "status.json"
    write_family_status(status_path)
    out_plan = tmp_path / "plan.json"
    out_configs = tmp_path / "configs.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--family-status",
            str(status_path),
            "--out-plan",
            str(out_plan),
            "--out-configs",
            str(out_configs),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    metadata = json.loads(completed.stdout)
    assert metadata["rescue_config_count"] == 9
    assert metadata["holdout_authorized"] is False
    assert out_plan.exists()
    config_payload = json.loads(out_configs.read_text())
    assert len(config_payload["configs"]) == 9
