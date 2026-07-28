from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_multiplicity_triage.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_multiplicity_triage", SCRIPT)
assert SPEC and SPEC.loader
triage_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(triage_mod)


def artifact_payload(*, sharpe: float, bootstrap_p5: float, drawdown: float = 0.10, activity: int = 120) -> dict:
    return {
        "kind": "tsmom_factory_v1_train_only_grid",
        "summary": {
            "accepted_train_only": True,
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "rows": [
            {
                "advance_passed": True,
                "config": {"asset_vol_target_ann": 0.35},
                "validation": {
                    "cost40": {
                        "sharpe": sharpe,
                        "bootstrap_30d_sharpe_p5": bootstrap_p5,
                        "max_drawdown": drawdown,
                        "active_yearly_bucket_count": 3,
                        "positive_active_yearly_bucket_count": 3,
                        "rebalance_event_count": activity,
                    }
                },
            }
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_multiplicity_triage_keeps_only_adjusted_survivors_and_safety_false(tmp_path) -> None:
    strong = tmp_path / "artifacts/strong.json"
    weak = tmp_path / "artifacts/weak.json"
    write_json(strong, artifact_payload(sharpe=2.4, bootstrap_p5=2.0))
    write_json(weak, artifact_payload(sharpe=1.2, bootstrap_p5=-1.0))
    state = tmp_path / "state.json"
    write_json(
        state,
        {
            "candidates_found_total": 2,
            "candidates_found": [
                {"task": "strong", "status": "manual_review_required", "output_json": str(strong)},
                {"task": "weak", "status": "manual_review_required", "output_json": str(weak)},
            ],
        },
    )

    report = triage_mod.build_report(state, tmp_path)
    text = triage_mod.format_markdown(report)

    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["summary"]["survivor_count"] == 1
    assert report["summary"]["rejected_multiplicity_count"] == 1
    assert report["rows"][0]["task"] == "strong"
    assert report["rows"][0]["decision"] == "multiplicity_survivor"
    assert "not authorize holdout" in text


def test_multiplicity_triage_excludes_data_drift_by_default(tmp_path) -> None:
    drift = tmp_path / "artifacts/drift.json"
    write_json(drift, artifact_payload(sharpe=2.4, bootstrap_p5=2.0))
    state = tmp_path / "state.json"
    write_json(
        state,
        {
            "candidates_found": [
                {"task": "drift", "status": "manual_review_required_data_drift", "output_json": str(drift)}
            ]
        },
    )

    report = triage_mod.build_report(state, tmp_path)

    assert report["summary"]["candidate_rows_considered"] == 0


def test_multiplicity_triage_uses_yearly_periods_as_activity_fallback(tmp_path) -> None:
    artifact = tmp_path / "artifacts/xsec.json"
    payload = artifact_payload(sharpe=2.4, bootstrap_p5=2.0)
    cost40 = payload["rows"][0]["validation"]["cost40"]
    cost40.pop("rebalance_event_count")
    cost40["yearly"] = {
        "2021": {"net_return": 0.2, "periods": 40},
        "2022": {"net_return": 0.1, "periods": 40},
        "2023": {"net_return": 0.1, "periods": 40},
    }
    write_json(artifact, payload)
    state = tmp_path / "state.json"
    write_json(
        state,
        {"candidates_found": [{"task": "xsec", "status": "manual_review_required", "output_json": str(artifact)}]},
    )

    report = triage_mod.build_report(state, tmp_path)

    assert report["summary"]["survivor_count"] == 1
    assert report["rows"][0]["multiplicity"]["metrics"]["activity_count"] == 120.0
