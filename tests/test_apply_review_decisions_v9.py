from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.triage import apply_review_decisions, build_manual_review_queue  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def artifact_payload(config: dict, sharpe: float, bootstrap_p5: float) -> dict:
    return {
        "kind": "xsec_ohlcv_factory_v1_train_only_grid",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "summary": {"accepted_train_only": True},
        "selection_validation": {"effective_trials": 100},
        "rows": [
            {
                "advance_passed": True,
                "config": config,
                "validation": {
                    "cost40": {
                        "sharpe": sharpe,
                        "bootstrap_30d_sharpe_p5": bootstrap_p5,
                        "max_drawdown": 0.12,
                        "active_yearly_bucket_count": 3,
                        "positive_active_yearly_bucket_count": 3,
                        "rebalance_event_count": 120,
                    }
                },
            }
        ],
    }


def candidate(task: str, path: Path) -> dict:
    return {
        "task": task,
        "output_json": str(path),
        "output_md": str(path.with_suffix(".md")),
        "status": "manual_review_required",
    }


def result(task: str, path: Path, snapshot: str = "") -> dict:
    row = {
        "task": task,
        "output_json": str(path),
        "status": "accepted_train_only_candidate_found",
        "returncode": 0,
        "planned_task": {
            "train_start": "2019-01-01",
            "train_end": "2024-03-31 23:59:59",
            "embargo_start": "2024-07-01",
            "module": "v9.contract.xsec_ohlcv_factory",
            "preset": "hq_dd_plateau",
            "cli_preset": "hq_dd_plateau",
        },
    }
    if snapshot:
        row["data_snapshot_fingerprint"] = snapshot
    return row


def test_apply_review_decisions_transitions_matching_hash_and_skips_stale(tmp_path) -> None:
    strong = tmp_path / "artifacts/strong.json"
    stale = tmp_path / "artifacts/stale.json"
    write_json(strong, artifact_payload({"lookback_h": 504, "k": 3}, sharpe=2.4, bootstrap_p5=1.9))
    write_json(stale, artifact_payload({"lookback_h": 168, "k": 2}, sharpe=1.4, bootstrap_p5=0.2))
    state = {
        "kind": "v9_auto_research_train_only_state",
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "candidates_found": [
            candidate("strong", strong),
            candidate("stale", stale),
        ],
        "task_results": [
            result("strong", strong, snapshot="snap-strong"),
            result("stale", stale),
        ],
    }
    state_path = tmp_path / "state.json"
    write_json(state_path, state)
    queue = build_manual_review_queue(state_path=state_path)
    by_task = {row["task"]: row for row in queue}
    decisions_path = tmp_path / "review_decisions.json"
    write_json(
        decisions_path,
        {
            "decisions": [
                {
                    "candidate_id": by_task["strong"]["identity"],
                    "evidence_sha1": by_task["strong"]["evidence_sha1"],
                    "decision": "validate_train_only",
                    "reviewer": "human",
                    "rationale": "Strong multiplicity survivor for train-only review.",
                },
                {
                    "candidate_id": by_task["stale"]["identity"],
                    "evidence_sha1": "not-the-current-evidence",
                    "decision": "reject",
                    "reviewer": "human",
                    "rationale": "This should not apply because evidence changed.",
                },
            ]
        },
    )

    report = apply_review_decisions(state_path, decisions_path)
    updated = json.loads(state_path.read_text())

    assert report["applied_count"] == 1
    assert report["decisions"][0]["reason"] == "applied"
    assert report["decisions"][1]["reason"] == "stale_evidence"
    assert updated["candidates_found"][0]["status"] == "validated_train_only"
    assert updated["candidates_found"][0]["decision_policy"] == "human_review_v1"
    assert updated["candidates_found"][0]["holdout_authorized"] is False
    assert updated["candidates_found"][0]["paper_trading_authorized"] is False
    assert updated["candidates_found"][0]["live_trading_authorized"] is False
    assert updated["candidates_found"][1]["status"] == "manual_review_required"
    assert updated["paper_trading_authorized"] is False
    assert updated["live_trading_authorized"] is False

    second = apply_review_decisions(state_path, decisions_path)
    assert second["applied_count"] == 0
    assert second["decisions"][0]["reason"] == "already_applied"
    assert second["decisions"][1]["reason"] == "stale_evidence"


def test_apply_review_decisions_blocks_validate_without_snapshot(tmp_path) -> None:
    path = tmp_path / "artifacts/no_snapshot.json"
    write_json(path, artifact_payload({"lookback_h": 504, "k": 3}, sharpe=2.4, bootstrap_p5=1.9))
    state = {
        "kind": "v9_auto_research_train_only_state",
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "candidates_found": [candidate("no_snapshot", path)],
        "task_results": [result("no_snapshot", path)],
    }
    state_path = tmp_path / "state.json"
    write_json(state_path, state)
    before = state_path.read_text()
    queue = build_manual_review_queue(state_path=state_path)
    decisions_path = tmp_path / "review_decisions.json"
    write_json(
        decisions_path,
        {
            "decisions": [
                {
                    "candidate_id": queue[0]["identity"],
                    "evidence_sha1": queue[0]["evidence_sha1"],
                    "decision": "validate_train_only",
                    "reviewer": "human",
                    "rationale": "Looks strong, but should be blocked without snapshot.",
                }
            ]
        },
    )

    report = apply_review_decisions(state_path, decisions_path)
    updated = json.loads(state_path.read_text())

    assert report["applied_count"] == 0
    assert report["decisions"][0]["reason"] == "snapshot_revalidation_required"
    assert updated["candidates_found"][0]["status"] == "manual_review_required"
    assert state_path.read_text() == before
