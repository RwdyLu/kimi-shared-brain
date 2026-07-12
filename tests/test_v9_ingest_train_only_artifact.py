from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_ingest_train_only_artifact.py"
SPEC = importlib.util.spec_from_file_location("v9_ingest_train_only_artifact", SCRIPT)
assert SPEC and SPEC.loader
ingest_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest_mod)

from v9.research.task_planner import PlannedTask  # noqa: E402


def write_accepted_xsec_artifact(path: Path, snapshot: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("snapshot")
    config = {
        "train_start": "2017-08-01",
        "train_end": "2024-06-30 23:59:59",
        "embargo_start": "2024-07-01",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "lookbacks_h": [72, 120, 168],
    }
    row_config = {
        "lookback_h": 72,
        "skip_h": 0,
        "rebalance_h": 8,
        "k": 2,
        "score_mode": "risk_adj_mom",
        "market_filter_h": 168,
        "vol_target_ann": 0.12,
    }
    payload = {
        "kind": "xsec_ohlcv_factory_v1_train_only_grid",
        "summary": {"accepted_train_only": True, "pass_count": 1, "rows": 1},
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "config": config,
        "data": {
            "fingerprint": "snap-evergreen",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "snapshot": {
                "path": str(snapshot),
                "fingerprint": "snap-evergreen",
                "source": "unit_test",
            },
        },
        "selection_validation": {"effective_trials": 1, "n_configs_tested": 1},
        "rows": [
            {
                "advance_passed": True,
                "config": row_config,
                "validation": {
                    "cost40": {
                        "sharpe": 2.0,
                        "bootstrap_30d_sharpe_p5": 1.8,
                        "max_drawdown": 0.10,
                        "rebalance_event_count": 100,
                        "yearly": {
                            "2021": {"periods": 10, "net_return": 0.05},
                            "2022": {"periods": 10, "net_return": 0.05},
                            "2023": {"periods": 10, "net_return": 0.05},
                            "2024H1": {"periods": 10, "net_return": 0.05},
                        },
                    }
                },
            }
        ],
    }
    path.write_text(json.dumps(payload))


def test_ingest_train_only_artifact_appends_supplemental_candidate_and_rebuilds_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "artifacts/v9/contract_lab/xsec_ohlcv_cont_full_202406_evergreen_fast_abc.json"
    snapshot = tmp_path / "artifacts/v9/data_snapshots/xsec.parquet"
    write_accepted_xsec_artifact(artifact, snapshot)
    state = tmp_path / "state/v9_auto_research_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"task_results": [], "candidates_found": []}))

    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_evergreen_fast_abc",
        preset="evergreen_fast",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc",
        output_json=str(artifact),
        output_md=str(artifact.with_suffix(".md")),
        prior_trials=0,
    )
    report = ingest_mod.ingest_train_only_artifact(
        planned=planned,
        state_path=state,
        explored_path=tmp_path / "state/v9_auto_research_explored.jsonl",
        supplemental_candidates_path=tmp_path / "state/v9_supplemental_train_only_candidates.jsonl",
        marker_path=tmp_path / "state/FOUND_INTERNAL_CANDIDATE.txt",
        report_json=tmp_path / "state/v9_last_ingested_train_only_artifact.json",
        revalidation_out_dir=tmp_path / "artifacts/v9/revalidation",
        revalidation_out_json=tmp_path / "artifacts/v9/revalidation/v9_candidate_revalidation_plan.json",
    )

    assert report["status"] == "accepted_train_only_candidate_found"
    assert report["candidate_status"] == "manual_review_required"
    supplemental = (tmp_path / "state/v9_supplemental_train_only_candidates.jsonl").read_text()
    assert "evergreen_fast" in supplemental
    assert "FOUND_INTERNAL_CANDIDATE" in (tmp_path / "state/FOUND_INTERNAL_CANDIDATE.txt").read_text()
    plan = json.loads((tmp_path / "artifacts/v9/revalidation/v9_candidate_revalidation_plan.json").read_text())
    assert plan["group_count"] == 1
    assert plan["groups"][0]["preset"] == "evergreen_fast"
    explored = (tmp_path / "state/v9_auto_research_explored.jsonl").read_text()
    assert '"fingerprint": "abc"' in explored
