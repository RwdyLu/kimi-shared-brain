from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_candidate_triage.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_candidate_triage", SCRIPT)
assert SPEC and SPEC.loader
triage_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(triage_mod)


def row(config: dict[str, Any], *, advance_passed: bool = True, boot: float = 0.8, q25: float = 0.4) -> dict[str, Any]:
    return {
        "advance_passed": advance_passed,
        "config": {"k": 3, "score_mode": "risk_adj_mom", "skip_h": 0, "n_tranches": 1, **config},
        "cost40": {
            "sharpe": 1.8 if advance_passed else 0.2,
            "total_return": 0.35 if advance_passed else -0.01,
            "max_drawdown": 0.12,
            "bootstrap_30d_sharpe_p5": boot,
            "daily_turnover": 0.02,
        },
        "walk_forward": {
            "passed": q25 >= 0.0,
            "q25_sharpe": q25,
            "positive_return_fraction": 0.83,
        },
        "leave_one_symbol": {
            "passed": True,
            "min_sharpe": 0.7,
            "min_return": 0.05,
        },
    }


def write_artifact(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                "summary": {
                    "accepted_train_only": True,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                    "pass_count": sum(1 for item in rows if item.get("advance_passed")),
                    "rows": len(rows),
                },
                "data": {
                    "fingerprint": "train-fp",
                    "first_dt": "2020-01-01T00:00:00+00:00",
                    "last_dt": "2024-03-31T23:00:00+00:00",
                    "rows": 100,
                    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                },
                "train_window": {
                    "start": "2020-01-01T00:00:00+00:00",
                    "end": "2024-03-31T23:00:00+00:00",
                },
                "rows": rows,
            }
        )
    )


def write_state(path: Path, candidates: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"candidates_found": candidates}))


def test_triage_shortlists_plateau_and_excludes_data_drift(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "artifacts/v9/contract_lab/plateau.json"
    drift_artifact = tmp_path / "artifacts/v9/contract_lab/drift.json"
    center = {"lookback_h": 336, "market_filter_h": 1008, "rebalance_h": 240, "vol_target_ann": 0.08}
    write_artifact(
        artifact,
        [
            row(center, boot=0.9, q25=0.8),
            row({**center, "lookback_h": 504}, boot=0.7, q25=0.3),
            row({**center, "market_filter_h": 1344}, boot=0.7, q25=0.2),
            row({**center, "rebalance_h": 120}, boot=0.6, q25=0.2),
        ],
    )
    write_artifact(drift_artifact, [row(center)])
    state = tmp_path / "state.json"
    write_state(
        state,
        [
            {
                "task": "plateau",
                "status": "manual_review_required",
                "output_json": str(artifact),
            },
            {
                "task": "drift",
                "status": "manual_review_required_data_drift",
                "output_json": str(drift_artifact),
            },
        ],
    )

    report = triage_mod.build_triage(state, tmp_path, min_neighbor_count=3)
    markdown = triage_mod.format_markdown(report)

    assert report["holdout_accessed"] is False
    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["summary"]["excluded_data_drift_candidates"] == 1
    assert report["summary"]["shortlist_count"] >= 1
    assert report["ranked_candidates"][0]["decision"] == "shortlist_plateau_candidate"
    assert report["ranked_candidates"][0]["neighbor_stability"]["passing_neighbor_count"] == 3
    assert "holdout_accessed: `False`" in markdown
    assert "not authorize paper, live, or production" in markdown


def test_triage_rejects_isolated_center_when_neighbors_fail(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "artifacts/v9/contract_lab/spike.json"
    center = {"lookback_h": 336, "market_filter_h": 1008, "rebalance_h": 240, "vol_target_ann": 0.08}
    write_artifact(
        artifact,
        [
            row(center, boot=0.9, q25=0.8),
            row({**center, "lookback_h": 504}, advance_passed=False, boot=0.1, q25=-0.3),
            row({**center, "market_filter_h": 1344}, advance_passed=False, boot=0.1, q25=-0.4),
            row({**center, "rebalance_h": 120}, advance_passed=False, boot=0.1, q25=-0.2),
        ],
    )
    state = tmp_path / "state.json"
    write_state(
        state,
        [
            {
                "task": "spike",
                "status": "manual_review_required",
                "output_json": str(artifact),
            }
        ],
    )

    report = triage_mod.build_triage(state, tmp_path, min_neighbor_count=3)

    assert report["summary"]["shortlist_count"] == 0
    assert report["ranked_candidates"][0]["decision"] == "reject_isolated_or_fragile"
    assert report["ranked_candidates"][0]["neighbor_stability"]["passing_neighbor_count"] == 0
