from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_holdout_batch.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_holdout_batch", SCRIPT)
assert SPEC and SPEC.loader
batch_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch_mod)


def candidate(artifact: str = "artifacts/v9/contract_lab/tsmom.json", sharpe40: float = 2.0) -> dict[str, Any]:
    return {
        "decision": "shortlist_plateau_candidate",
        "artifact": artifact,
        "kind": "tsmom_factory_v1_train_only_grid",
        "score": 3.0,
        "metrics": {"sharpe40": sharpe40, "max_drawdown40": 0.1},
        "config": {"market_filter_h": 720},
    }


def triage_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "summary": {"shortlist_count": len(rows)},
        "ranked_candidates": rows,
    }


def promising_audit(_candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_status": "completed",
        "artifact": "artifacts/v9/contract_lab/tsmom.json",
        "holdout_decision": "holdout_promising_manual_review_required",
        "promotion_decision": "paper_candidate_manual_review_required",
        "promotion_evidence": {
            "train_sharpe": 2.0,
            "holdout_sharpe": 1.2,
            "holdout_sharpe_decay_ratio": 0.6,
            "holdout_return": 0.08,
            "holdout_drawdown": 0.12,
        },
    }


def test_dry_run_selects_candidates_without_accessing_holdout() -> None:
    called = False

    def audit(_candidate: dict[str, Any]) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    report = batch_mod.build_protocol_from_triage(
        triage_report([candidate()]),
        max_candidates=5,
        holdout_authorized=False,
        min_decay_ratio=0.5,
        audit_candidate=audit,
    )

    assert called is False
    assert report["holdout_accessed"] is False
    assert report["holdout_authorized"] is False
    assert report["summary"]["selected_count"] == 1
    assert report["summary"]["holdout_completed_count"] == 0
    assert report["summary"]["paper_candidate_count"] == 0


def test_holdout_authorized_batch_promotes_only_manual_review_candidate() -> None:
    report = batch_mod.build_protocol_from_triage(
        triage_report([candidate()]),
        max_candidates=5,
        holdout_authorized=True,
        min_decay_ratio=0.5,
        audit_candidate=promising_audit,
    )

    assert report["holdout_accessed"] is True
    assert report["holdout_authorized"] is True
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["summary"]["holdout_completed_count"] == 1
    assert report["summary"]["paper_candidate_count"] == 1
    assert report["summary"]["status_counts"] == {"paper_candidate_manual_review_required": 1}


def test_promotion_decision_requires_decay_ratio_and_holdout_quality() -> None:
    report = {
        "decision": "holdout_promising_manual_review_required",
        "costs": {
            "40bps": {"sharpe": 0.8, "total_return": 0.03, "max_drawdown": 0.14},
            "20bps": {"sharpe": 0.9, "total_return": 0.04, "max_drawdown": 0.12},
        },
    }

    decision, evidence = batch_mod.promotion_decision(candidate(sharpe40=2.0), report, min_decay_ratio=0.5)

    assert decision == "holdout_failed_do_not_paper_trade"
    assert evidence["holdout_sharpe_decay_ratio"] == 0.4
    assert evidence["checks"]["holdout_sharpe_decay_ge_min"] is False


def test_promotion_decision_blocks_inactive_xsec_post_holdout_probe() -> None:
    report = {
        "decision": "holdout_promising_manual_review_required",
        "costs": {
            "40bps": {"sharpe": 1.2, "total_return": 0.08, "max_drawdown": 0.14},
            "20bps": {"sharpe": 1.4, "total_return": 0.10, "max_drawdown": 0.12},
        },
    }
    probe = {
        "evaluation_start": "2026-06-01T00:00:00+00:00",
        "latest_dt": "2026-07-11T00:00:00+00:00",
        "costs": {
            "40bps": {
                "rebalance_event_count": 5,
                "active_rebalance_event_count": 0,
                "time_in_market_frac": 0.0,
            }
        },
    }

    decision, evidence = batch_mod.promotion_decision(
        candidate(sharpe40=2.0),
        report,
        min_decay_ratio=0.5,
        post_holdout_probe=probe,
        require_post_holdout_activity=True,
        min_post_holdout_active_rebalances=1,
        min_post_holdout_time_in_market=0.0,
    )

    assert decision == "holdout_promising_recently_inactive_manual_review_required"
    assert evidence["checks"]["holdout_sharpe_decay_ge_min"] is True
    assert evidence["checks"]["post_holdout_probe_present"] is True
    assert evidence["checks"]["post_holdout_active_rebalances_ge_min"] is False
    assert evidence["checks"]["post_holdout_time_in_market_ge_min"] is False
    assert evidence["post_holdout_probe"]["cost40"]["active_rebalance_event_count"] == 0


def test_promotion_decision_promotes_active_xsec_post_holdout_probe() -> None:
    report = {
        "decision": "holdout_promising_manual_review_required",
        "costs": {
            "40bps": {"sharpe": 1.2, "total_return": 0.08, "max_drawdown": 0.14},
            "20bps": {"sharpe": 1.4, "total_return": 0.10, "max_drawdown": 0.12},
        },
    }
    probe = {
        "evaluation_start": "2026-06-01T00:00:00+00:00",
        "latest_dt": "2026-07-11T00:00:00+00:00",
        "costs": {
            "40bps": {
                "rebalance_event_count": 5,
                "active_rebalance_event_count": 2,
                "time_in_market_frac": 0.15,
            }
        },
    }

    decision, evidence = batch_mod.promotion_decision(
        candidate(sharpe40=2.0),
        report,
        min_decay_ratio=0.5,
        post_holdout_probe=probe,
        require_post_holdout_activity=True,
        min_post_holdout_active_rebalances=1,
        min_post_holdout_time_in_market=0.01,
    )

    assert decision == "paper_candidate_manual_review_required"
    assert all(evidence["checks"].values())


def test_artifact_kind_supports_tsmom_and_xsec() -> None:
    assert batch_mod.artifact_kind(candidate("artifacts/v9/contract_lab/tsmom_abc.json")) == "tsmom"
    assert (
        batch_mod.artifact_kind(
            {
                "artifact": "artifacts/v9/contract_lab/xsec_ohlcv_abc.json",
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            }
        )
        == "xsec_ohlcv"
    )
    assert batch_mod.artifact_kind({"artifact": "unknown.json", "kind": "unknown"}) == "unsupported"


def test_select_candidates_skips_rejected_or_data_drift_statuses() -> None:
    clean = candidate("clean.json")
    clean["statuses"] = ["manual_review_required"]
    rejected = candidate("rejected.json")
    rejected["statuses"] = ["rejected_multiplicity"]
    drift = candidate("drift.json")
    drift["statuses"] = ["manual_review_required_data_drift"]

    selected = batch_mod.select_candidates(triage_report([rejected, drift, clean]), max_candidates=10)

    assert [row["artifact"] for row in selected] == ["clean.json"]


def test_select_candidates_falls_back_to_insufficient_neighbors() -> None:
    fallback = candidate("fallback.json")
    fallback["decision"] = "manual_review_insufficient_neighbors"
    fallback["statuses"] = ["manual_review_required"]

    selected = batch_mod.select_candidates(triage_report([fallback]), max_candidates=10)

    assert [row["artifact"] for row in selected] == ["fallback.json"]
    assert selected[0]["holdout_selection_reason"] == "fallback_insufficient_neighbors_candidate"


def test_candidate_hash_distinguishes_same_artifact_different_config() -> None:
    left = candidate("same.json")
    right = candidate("same.json")
    right["config"] = {"market_filter_h": 504}

    assert batch_mod.candidate_hash(left) != batch_mod.candidate_hash(right)


def test_write_validated_marker_removes_stale_marker_when_no_candidate(tmp_path) -> None:
    stale = tmp_path / "FOUND_VALIDATED_CANDIDATE.txt"
    stale.write_text("old candidate\n")
    report = {
        "holdout_results": [
            {"promotion_decision": "holdout_promising_recently_inactive_manual_review_required"}
        ],
        "summary": {
            "status_counts": {
                "holdout_promising_recently_inactive_manual_review_required": 1
            }
        },
    }

    batch_mod.write_validated_marker(report, tmp_path)

    assert not stale.exists()
    none = tmp_path / "NO_VALIDATED_CANDIDATE.txt"
    assert "NO_VALIDATED_CANDIDATE" in none.read_text()
