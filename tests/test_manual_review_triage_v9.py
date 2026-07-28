from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.triage import (  # noqa: E402
    apply_review_decisions,
    build_manual_review_queue,
    write_manual_review_dossier,
    write_manual_review_queue,
)


def write_candidate_artifact(
    path: Path,
    config: dict,
    symbols: list[str] | None = None,
    cost40: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"advance_passed": True, "config": config}
    if cost40:
        row["validation"] = {"cost40": cost40}
    path.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "symbols": symbols or ["BTCUSDT", "ETHUSDT"],
                "summary": {"accepted_train_only": True},
                "selection_validation": {"effective_trials": 10},
                "rows": [row],
            },
            sort_keys=True,
        )
    )


def result_for(path: Path, adjusted_p_value: float, z_score: float, sharpe: float, snapshot: str = "") -> dict:
    return {
        "task": path.stem,
        "output_json": str(path),
        "status": "accepted_train_only_candidate_found",
        "returncode": 0,
        "fingerprint": path.stem,
        "data_snapshot_fingerprint": snapshot,
        "planned_task": {
            "train_start": "2019-01-01",
            "train_end": "2024-03-31 23:59:59",
            "embargo_start": "2024-07-01",
            "module": "v9.contract.xsec_ohlcv_factory",
            "preset": "hq_dd_plateau",
            "cli_preset": "hq_dd_plateau",
        },
        "multiplicity_decision": "multiplicity_survivor",
        "multiplicity_evidence": {
            "evaluated": True,
            "decision": "multiplicity_survivor",
            "metrics": {
                "adjusted_p_value": adjusted_p_value,
                "z_score": z_score,
                "sharpe": sharpe,
                "max_drawdown": 0.16,
            },
        },
    }


def test_manual_review_queue_ranks_replicated_strong_family_and_drops_duplicates(tmp_path) -> None:
    strong_config = {"lookback_h": 504, "rebalance_h": 168, "k": 3, "score_mode": "risk_adj_mom"}
    weak_config = {"lookback_h": 168, "rebalance_h": 24, "k": 2, "score_mode": "mom"}
    candidates = []
    task_results = []

    for idx in range(3):
        path = tmp_path / f"strong_{idx}.json"
        write_candidate_artifact(path, strong_config)
        candidates.append(
            {
                "task": f"strong_{idx}",
                "output_json": str(path),
                "output_md": str(path.with_suffix(".md")),
                "status": "manual_review_required",
                "data_snapshot_fingerprint": "snap-strong",
            }
        )
        task_results.append(result_for(path, adjusted_p_value=0.001, z_score=4.0, sharpe=2.2, snapshot="snap-strong"))

    for idx in range(5):
        path = tmp_path / f"weak_{idx}.json"
        write_candidate_artifact(path, weak_config)
        candidates.append(
            {
                "task": f"weak_{idx}",
                "output_json": str(path),
                "output_md": str(path.with_suffix(".md")),
                "status": "manual_review_required",
            }
        )
        task_results.append(result_for(path, adjusted_p_value=0.20, z_score=0.8, sharpe=1.0))

    queue = build_manual_review_queue(candidates, task_results=task_results)
    assert len(queue) == 2
    assert queue == build_manual_review_queue(candidates, task_results=task_results)
    assert queue[0]["data_snapshot_fingerprint"] == "snap-strong"
    assert queue[0]["score"] > queue[1]["score"]
    assert queue[0]["score_components"]["replication_count"] == 3
    assert queue[1]["score_components"]["duplicate_count"] == 4
    assert all("duplicate_of" not in row for row in queue)
    assert all(row["holdout_authorized"] is False for row in queue)
    assert all(row["paper_trading_authorized"] is False for row in queue)
    assert all(row["live_trading_authorized"] is False for row in queue)

    payload = write_manual_review_queue(tmp_path / "manual_review_queue.json", candidates, task_results=task_results)
    assert payload["entry_count"] == 2
    written = json.loads((tmp_path / "manual_review_queue.json").read_text())
    assert written["entries"][0]["identity"] == queue[0]["identity"]
    assert written["paper_trading_authorized"] is False


def test_manual_review_queue_recomputes_missing_multiplicity_evidence(tmp_path) -> None:
    path = tmp_path / "candidate.json"
    write_candidate_artifact(
        path,
        {"lookback_h": 504, "rebalance_h": 168, "k": 3, "score_mode": "risk_adj_mom"},
        cost40={
            "sharpe": 2.4,
            "bootstrap_30d_sharpe_p5": 1.9,
            "max_drawdown": 0.12,
            "active_yearly_bucket_count": 3,
            "positive_active_yearly_bucket_count": 3,
            "rebalance_event_count": 120,
        },
    )
    candidates = [
        {
            "task": "candidate",
            "output_json": str(path),
            "output_md": str(path.with_suffix(".md")),
            "status": "manual_review_required",
        }
    ]
    task_results = [{"task": "candidate", "output_json": str(path), "status": "accepted_train_only_candidate_found"}]

    queue = build_manual_review_queue(candidates, task_results=task_results)

    assert len(queue) == 1
    assert queue[0]["score_components"]["adjusted_p_value"] is not None
    assert queue[0]["score_components"]["multiplicity_decision"] == "multiplicity_survivor"


def test_manual_review_dossier_writes_non_apply_ready_draft(tmp_path) -> None:
    path = tmp_path / "strong.json"
    write_candidate_artifact(
        path,
        {"lookback_h": 504, "rebalance_h": 168, "k": 3, "score_mode": "risk_adj_mom"},
    )
    candidates = [
        {
            "task": "strong",
            "output_json": str(path),
            "output_md": str(path.with_suffix(".md")),
            "status": "manual_review_required",
            "data_snapshot_fingerprint": "snap-strong",
        }
    ]
    task_results = [result_for(path, adjusted_p_value=0.001, z_score=4.0, sharpe=2.2, snapshot="snap-strong")]
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"candidates_found": candidates, "task_results": task_results}, sort_keys=True))
    draft_path = tmp_path / "review_decisions_draft.json"
    markdown_path = tmp_path / "manual_review_dossier.md"

    dossier = write_manual_review_dossier(
        tmp_path / "manual_review_dossier.json",
        candidates,
        state_path,
        task_results=task_results,
        draft_path=draft_path,
        markdown_path=markdown_path,
        limit=1,
    )
    draft = json.loads(draft_path.read_text())
    markdown = markdown_path.read_text()
    report = apply_review_decisions(state_path, draft_path)
    updated = json.loads(state_path.read_text())

    assert dossier["selected_count"] == 1
    assert dossier["entries"][0]["recommended_decision"] == "validate_train_only"
    assert dossier["entries"][0]["draft_is_not_apply_ready"] is True
    assert dossier["entries"][0]["train_window"]["disjoint"] is True
    assert dossier["paper_trading_authorized"] is False
    assert draft["draft_is_not_apply_ready"] is True
    assert draft["decisions"][0]["decision"] is None
    assert draft["decisions"][0]["recommended_decision"] == "validate_train_only"
    assert draft["decisions"][0]["reviewer"] == ""
    assert draft["decisions"][0]["rationale"] == ""
    assert draft["decisions"][0]["rationale_template"]
    assert dossier["entries"][0]["evidence_sha1"] in markdown
    assert "not apply-ready" in markdown
    assert report["applied_count"] == 0
    assert report["decisions"][0]["reason"] == "invalid_decision"
    assert updated["candidates_found"][0]["status"] == "manual_review_required"


def test_manual_review_dossier_requires_snapshot_revalidation_when_snapshot_missing(tmp_path) -> None:
    path = tmp_path / "missing_snapshot.json"
    write_candidate_artifact(
        path,
        {"lookback_h": 504, "rebalance_h": 168, "k": 3, "score_mode": "risk_adj_mom"},
    )
    candidates = [
        {
            "task": "missing_snapshot",
            "output_json": str(path),
            "output_md": str(path.with_suffix(".md")),
            "status": "manual_review_required",
        }
    ]
    task_results = [result_for(path, adjusted_p_value=0.001, z_score=4.0, sharpe=2.2)]

    dossier = write_manual_review_dossier(
        tmp_path / "manual_review_dossier.json",
        candidates,
        tmp_path / "state.json",
        task_results=task_results,
        limit=1,
    )

    assert dossier["entries"][0]["recommended_decision"] == "snapshot_revalidation_required"
    assert "missing_data_snapshot" in dossier["entries"][0]["soft_flags"]
    assert dossier["draft_decisions"][0]["recommended_decision"] == "snapshot_revalidation_required"
