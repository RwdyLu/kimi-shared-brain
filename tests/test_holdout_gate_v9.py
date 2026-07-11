from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_paper_readiness_gate import paper_candidate_from_batch  # noqa: E402
from v9.contract.holdout import run_authorized_holdout  # noqa: E402
from v9.contract.triage import build_manual_review_queue  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def artifact_payload(config: dict, sharpe: float = 2.0) -> dict:
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
                        "bootstrap_30d_sharpe_p5": 1.4,
                        "max_drawdown": 0.12,
                        "total_return": 0.3,
                    }
                },
            }
        ],
    }


def candidate(task: str, path: Path, status: str = "manual_review_required") -> dict:
    return {
        "task": task,
        "output_json": str(path),
        "output_md": str(path.with_suffix(".md")),
        "status": status,
    }


def result(task: str, path: Path, train_end: str = "2024-03-31 23:59:59") -> dict:
    return {
        "task": task,
        "output_json": str(path),
        "status": "accepted_train_only_candidate_found",
        "returncode": 0,
        "planned_task": {
            "train_start": "2019-01-01",
            "train_end": train_end,
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
                "adjusted_p_value": 0.001,
                "z_score": 4.0,
                "sharpe": 2.0,
                "max_drawdown": 0.12,
            },
        },
    }


def validated_state(tmp_path: Path) -> tuple[Path, str, str]:
    artifact = tmp_path / "artifacts" / "candidate.json"
    write_json(artifact, artifact_payload({"lookback_h": 504, "k": 3, "score_mode": "risk_adj_mom"}))
    state = {
        "kind": "v9_auto_research_train_only_state",
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "candidates_found": [candidate("candidate", artifact)],
        "task_results": [result("candidate", artifact)],
    }
    state_path = tmp_path / "state.json"
    write_json(state_path, state)
    queue = build_manual_review_queue(state_path=state_path)
    evidence_sha1 = queue[0]["evidence_sha1"]
    state["candidates_found"][0]["status"] = "validated_train_only"
    state["candidates_found"][0]["review_evidence_sha1"] = evidence_sha1
    write_json(state_path, state)
    return state_path, queue[0]["identity"], evidence_sha1


def authorization(candidate_id: str, evidence_sha1: str) -> dict:
    return {
        "authorizations": [
            {
                "candidate_id": candidate_id,
                "evidence_sha1": evidence_sha1,
                "decision": "authorize_holdout",
                "authorized_by": "human",
                "criteria": {
                    "min_holdout_sharpe_ratio_vs_train": 0.5,
                    "max_dd": 0.25,
                },
            }
        ]
    }


def test_stale_evidence_refuses_before_ledger_or_audit(tmp_path) -> None:
    state_path, candidate_id, _evidence_sha1 = validated_state(tmp_path)
    authorizations_path = tmp_path / "holdout_authorizations.json"
    ledger_path = tmp_path / "holdout_ledger.json"
    write_json(authorizations_path, authorization(candidate_id, "stale-evidence"))

    def fail_if_called(_candidate: dict) -> dict:
        raise AssertionError("holdout audit must not run with stale evidence")

    report = run_authorized_holdout(
        state_path=state_path,
        authorizations_path=authorizations_path,
        ledger_path=ledger_path,
        base=tmp_path,
        audit_candidate=fail_if_called,
    )

    assert report["applied_count"] == 0
    assert report["decisions"][0]["reason"] == "evidence_mismatch"
    assert not ledger_path.exists()
    updated = json.loads(state_path.read_text())
    assert updated["candidates_found"][0]["status"] == "validated_train_only"
    assert updated["paper_trading_authorized"] is False
    assert updated["live_trading_authorized"] is False


def test_authorized_holdout_writes_ledger_before_audit_and_is_one_shot(tmp_path) -> None:
    state_path, candidate_id, evidence_sha1 = validated_state(tmp_path)
    authorizations_path = tmp_path / "holdout_authorizations.json"
    ledger_path = tmp_path / "holdout_ledger.json"
    write_json(authorizations_path, authorization(candidate_id, evidence_sha1))

    def audit(candidate_row: dict) -> dict:
        ledger = json.loads(ledger_path.read_text())
        assert ledger["entries"][0]["status"] == "holdout_consumed_before_audit"
        assert candidate_row["authorization_criteria"]["max_dd"] == 0.25
        return {
            "audit_status": "completed",
            "holdout_decision": "holdout_promising_manual_review_required",
            "promotion_decision": "paper_candidate_manual_review_required",
            "promotion_evidence": {
                "train_sharpe": 2.0,
                "holdout_sharpe": 1.2,
                "holdout_sharpe_decay_ratio": 0.6,
                "holdout_return": 0.1,
                "holdout_drawdown": 0.12,
            },
            "holdout_report_json": "artifacts/v9/reviews/report.json",
        }

    first = run_authorized_holdout(
        state_path=state_path,
        authorizations_path=authorizations_path,
        ledger_path=ledger_path,
        base=tmp_path,
        audit_candidate=audit,
    )
    second = run_authorized_holdout(
        state_path=state_path,
        authorizations_path=authorizations_path,
        ledger_path=ledger_path,
        base=tmp_path,
        audit_candidate=lambda _candidate: (_ for _ in ()).throw(AssertionError("must not rerun holdout")),
    )
    updated = json.loads(state_path.read_text())
    ledger = json.loads(ledger_path.read_text())

    assert first["applied_count"] == 1
    assert first["decisions"][0]["new_status"] == "validated_holdout"
    assert first["summary"]["paper_candidate_count"] == 1
    assert first["summary"]["status_counts"] == {"paper_candidate_manual_review_required": 1}
    selected = paper_candidate_from_batch(first)
    assert selected["promotion_decision"] == "paper_candidate_manual_review_required"
    assert selected["ledger_id"] == first["decisions"][0]["ledger_id"]
    assert selected["paper_trading_authorized"] is False
    assert selected["live_trading_authorized"] is False
    assert second["applied_count"] == 0
    assert second["decisions"][0]["reason"] == "candidate_already_consumed"
    assert second["summary"]["paper_candidate_count"] == 0
    try:
        paper_candidate_from_batch(second)
    except ValueError as exc:
        assert "no paper_candidate_manual_review_required row" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("second no-op report must not expose a paper candidate")
    assert updated["candidates_found"][0]["status"] == "validated_holdout"
    assert updated["candidates_found"][0]["paper_trading_authorized"] is False
    assert updated["candidates_found"][0]["live_trading_authorized"] is False
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["status"] == "validated_holdout"


def test_overlapping_train_window_rejected_without_ledger_consumption(tmp_path) -> None:
    artifact = tmp_path / "artifacts" / "candidate.json"
    write_json(artifact, artifact_payload({"lookback_h": 504, "k": 3, "score_mode": "risk_adj_mom"}))
    state = {
        "kind": "v9_auto_research_train_only_state",
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "candidates_found": [candidate("candidate", artifact)],
        "task_results": [result("candidate", artifact, train_end="2025-01-01")],
    }
    state_path = tmp_path / "state.json"
    write_json(state_path, state)
    queue = build_manual_review_queue(state_path=state_path)
    state["candidates_found"][0]["status"] = "validated_train_only"
    write_json(state_path, state)
    authorizations_path = tmp_path / "holdout_authorizations.json"
    ledger_path = tmp_path / "holdout_ledger.json"
    write_json(authorizations_path, authorization(queue[0]["identity"], queue[0]["evidence_sha1"]))
    audit_calls = 0

    def fail_if_called(_candidate: dict) -> dict:
        nonlocal audit_calls
        audit_calls += 1
        raise AssertionError("holdout audit must not run for overlapping train window")

    report = run_authorized_holdout(
        state_path=state_path,
        authorizations_path=authorizations_path,
        ledger_path=ledger_path,
        base=tmp_path,
        audit_candidate=fail_if_called,
    )

    assert report["applied_count"] == 0
    assert report["decisions"][0]["reason"] == "train_holdout_overlap"
    assert audit_calls == 0
    assert not ledger_path.exists()
    updated = json.loads(state_path.read_text())
    assert updated["candidates_found"][0]["status"] == "validated_train_only"
