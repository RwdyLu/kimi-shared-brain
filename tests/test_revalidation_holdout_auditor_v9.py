from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_revalidation_holdout_auditor.py"
SPEC = importlib.util.spec_from_file_location("v9_revalidation_holdout_auditor", SCRIPT)
assert SPEC and SPEC.loader
auditor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(auditor)


def row(config: dict[str, Any], *, sharpe40: float = 2.0) -> dict[str, Any]:
    return {
        "advance_passed": True,
        "config": config,
        "cost20": {"sharpe": sharpe40 + 0.1},
        "cost40": {"sharpe": sharpe40},
    }


def write_artifact(path: Path) -> None:
    payload = {
        "kind": "xsec_ohlcv_factory_v1_train_only_grid",
        "symbols": ["AAA", "BBB"],
        "data": {"fingerprint": "data-fp"},
        "top": [
            row({"lookback_h": 8, "rebalance_h": 4, "k": 2, "score_mode": "mom", "market_filter_h": 0, "vol_target_ann": 0.05}),
            row({"lookback_h": 12, "rebalance_h": 4, "k": 2, "score_mode": "mom", "market_filter_h": 0, "vol_target_ann": 0.05}),
        ],
        "rows": [
            row({"lookback_h": 8, "rebalance_h": 4, "k": 2, "score_mode": "mom", "market_filter_h": 0, "vol_target_ann": 0.05}),
            row({"lookback_h": 16, "rebalance_h": 8, "k": 2, "score_mode": "mom", "market_filter_h": 0, "vol_target_ann": 0.05}),
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_accepted_rows_are_top_first_unique_and_limited(tmp_path) -> None:
    artifact = tmp_path / "revalidate_group.json"
    write_artifact(artifact)
    rows = auditor.accepted_rows(json.loads(artifact.read_text()), max_configs=2)

    assert len(rows) == 2
    assert rows[0]["config"]["lookback_h"] == 8
    assert rows[1]["config"]["lookback_h"] == 12


def test_recent_probe_costs_prefers_40bps() -> None:
    assert auditor.recent_probe_costs((20.0, 40.0, 60.0)) == (40.0,)
    assert auditor.recent_probe_costs((30.0, 50.0)) == (30.0,)
    assert auditor.recent_probe_costs(()) == (40.0,)


def test_audit_group_requires_holdout_authorization(tmp_path) -> None:
    artifact = tmp_path / "revalidate_group.json"
    write_artifact(artifact)

    verdict = auditor.audit_group(
        {"group_id": "group-a", "output_json": str(artifact), "group_plan_fingerprint": "plan-a"},
        cache_dir=tmp_path,
        holdout_start="2024-07-01",
        holdout_end="2026-07-12 01:00:00",
        recent_start="2026-06-01",
        costs_bps=(40.0,),
        bootstrap_iterations=0,
        max_configs=2,
        min_decay_ratio=0.5,
        min_recent_active_rebalances=1,
        min_recent_time_in_market=0.0,
        holdout_authorized=False,
    )

    assert verdict["audit_status"] == "holdout_not_authorized"
    assert verdict["paper_trading_authorized"] is False
    assert verdict["live_trading_authorized"] is False
    assert not auditor.verdict_path_for(str(artifact)).exists()


def test_audit_group_writes_idempotent_verdict_without_authorizing_paper(tmp_path) -> None:
    artifact = tmp_path / "revalidate_group.json"
    write_artifact(artifact)

    def fake_probe_builder(**_kwargs: Any) -> dict[str, Any]:
        return {
            "evaluation_start": "2026-06-01T00:00:00+00:00",
            "latest_dt": "2026-07-12T01:00:00+00:00",
            "latest_gross_exposure": 0.2,
            "latest_weights": {"AAA": 0.2, "BBB": 0.0},
            "costs": {
                "40bps": {
                    "active_rebalance_event_count": 2,
                    "time_in_market_frac": 0.25,
                    "total_return": 0.02,
                }
            },
        }

    def fake_holdout_builder(**_kwargs: Any) -> dict[str, Any]:
        return {
            "decision": "holdout_promising_manual_review_required",
            "costs": {
                "20bps": {"sharpe": 1.4, "total_return": 0.12, "max_drawdown": 0.08},
                "40bps": {"sharpe": 1.2, "total_return": 0.10, "max_drawdown": 0.10},
            },
        }

    group = {"group_id": "group-a", "output_json": str(artifact), "group_plan_fingerprint": "plan-a"}
    verdict = auditor.audit_group(
        group,
        cache_dir=tmp_path,
        holdout_start="2024-07-01",
        holdout_end="2026-07-12 01:00:00",
        recent_start="2026-06-01",
        costs_bps=(40.0,),
        bootstrap_iterations=0,
        max_configs=2,
        min_decay_ratio=0.5,
        min_recent_active_rebalances=1,
        min_recent_time_in_market=0.0,
        holdout_authorized=True,
        holdout_builder=fake_holdout_builder,
        probe_builder=fake_probe_builder,
    )

    assert verdict["decision"] == "paper_candidate_manual_review_required"
    assert verdict["paper_candidate_count"] == 1
    assert verdict["paper_trading_authorized"] is False
    assert verdict["live_trading_authorized"] is False

    rerun = auditor.audit_group(
        group,
        cache_dir=tmp_path,
        holdout_start="2024-07-01",
        holdout_end="2026-07-12 01:00:00",
        recent_start="2026-06-01",
        costs_bps=(40.0,),
        bootstrap_iterations=0,
        max_configs=2,
        min_decay_ratio=0.5,
        min_recent_active_rebalances=1,
        min_recent_time_in_market=0.0,
        holdout_authorized=True,
        holdout_builder=fake_holdout_builder,
        probe_builder=fake_probe_builder,
    )

    assert rerun["audit_status"] == "skipped_existing"
    assert rerun["audit_key"] == verdict["audit_key"]


def test_audit_group_can_skip_existing_verdict_even_when_key_changes(tmp_path) -> None:
    artifact = tmp_path / "revalidate_group.json"
    write_artifact(artifact)
    existing_path = auditor.verdict_path_for(str(artifact))
    existing_path.write_text(
        json.dumps(
            {
                "kind": auditor.GROUP_VERDICT_KIND,
                "audit_key": "old-key",
                "group_id": "group-a",
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
        )
    )

    verdict = auditor.audit_group(
        {"group_id": "group-a", "output_json": str(artifact), "group_plan_fingerprint": "plan-a"},
        cache_dir=tmp_path,
        holdout_start="2024-07-01",
        holdout_end="2026-07-12 01:00:00",
        recent_start="2026-06-01",
        costs_bps=(40.0,),
        bootstrap_iterations=0,
        max_configs=2,
        min_decay_ratio=0.5,
        min_recent_active_rebalances=1,
        min_recent_time_in_market=0.0,
        holdout_authorized=True,
        skip_existing_any_key=True,
    )

    assert verdict["audit_status"] == "skipped_existing"
    assert verdict["audit_key"] == "old-key"


def test_write_validated_marker_for_revalidation_paper_candidate(tmp_path) -> None:
    report = {
        "verdicts": [
            {
                "group_id": "group-a",
                "output_json": "artifacts/v9/contract_lab/revalidate_group.json",
                "verdict_path": "artifacts/v9/contract_lab/revalidate_group.json.holdout_verdict.json",
                "paper_candidate_count": 1,
                "results": [
                    {
                        "config_sig": "abc123",
                        "promotion_decision": "paper_candidate_manual_review_required",
                    }
                ],
            }
        ]
    }

    auditor.write_validated_marker(report, tmp_path)

    text = (tmp_path / "FOUND_VALIDATED_CANDIDATE.txt").read_text()
    assert "source=revalidation_holdout_auditor" in text
    assert "group_id=group-a" in text
    assert "config_sig=abc123" in text
    assert "paper_trading_authorized=False" in text
    assert "live_trading_authorized=False" in text
    assert not (tmp_path / "FOUND_PAPER_READY.txt").exists()


def test_write_validated_marker_leaves_state_unchanged_without_candidate(tmp_path) -> None:
    auditor.write_validated_marker({"verdicts": [{"paper_candidate_count": 0}]}, tmp_path)

    assert not (tmp_path / "FOUND_VALIDATED_CANDIDATE.txt").exists()


def test_build_audit_report_filters_target_group_id(tmp_path, monkeypatch) -> None:
    def fake_status(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["max_groups"] == 0
        return {
            "status_counts": {"completed_accepted": 2, "running": 1},
            "groups": [
                {"group_id": "group-a", "status": "completed_accepted", "output_json": "artifacts/a.json"},
                {"group_id": "group-b", "status": "completed_accepted", "output_json": "artifacts/b.json"},
                {"group_id": "group-c", "status": "running", "output_json": "artifacts/c.json"},
            ],
        }

    seen: list[str] = []

    def fake_audit_group(group: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        seen.append(str(group["group_id"]))
        return {
            "group_id": group["group_id"],
            "paper_candidate_count": 0,
            "reason": "holdout_failed",
        }

    monkeypatch.setattr(auditor, "build_revalidation_status", fake_status)
    monkeypatch.setattr(auditor, "audit_group", fake_audit_group)

    report = auditor.build_audit_report(
        plan_path=tmp_path / "plan.json",
        runner_state_path=tmp_path / "runner.json",
        cache_dir=tmp_path,
        holdout_start="2024-07-01",
        holdout_end="2026-07-12 01:00:00",
        recent_start="2026-06-01",
        costs_bps=(40.0,),
        bootstrap_iterations=0,
        max_groups=1,
        max_configs=2,
        min_decay_ratio=0.5,
        min_recent_active_rebalances=1,
        min_recent_time_in_market=0.0,
        holdout_authorized=True,
        force=False,
        skip_existing_any_key=False,
        stop_path=tmp_path / "STOP",
        target_group_ids=("group-b",),
    )

    assert seen == ["group-b"]
    assert report["summary"]["targeted"] is True
    assert report["summary"]["target_matched_count"] == 1
    assert report["summary"]["verdict_count"] == 1


def test_build_audit_report_filters_target_output_json_suffix(tmp_path, monkeypatch) -> None:
    def fake_status(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "status_counts": {"completed_accepted": 2},
            "groups": [
                {
                    "group_id": "group-a",
                    "status": "completed_accepted",
                    "output_json": "/root/project/artifacts/v9/contract_lab/a.json",
                },
                {
                    "group_id": "group-b",
                    "status": "completed_accepted",
                    "output_json": "/root/project/artifacts/v9/contract_lab/b.json",
                },
            ],
        }

    seen: list[str] = []

    def fake_audit_group(group: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        seen.append(str(group["group_id"]))
        return {
            "group_id": group["group_id"],
            "paper_candidate_count": 0,
            "reason": "holdout_failed",
        }

    monkeypatch.setattr(auditor, "build_revalidation_status", fake_status)
    monkeypatch.setattr(auditor, "audit_group", fake_audit_group)

    report = auditor.build_audit_report(
        plan_path=tmp_path / "plan.json",
        runner_state_path=tmp_path / "runner.json",
        cache_dir=tmp_path,
        holdout_start="2024-07-01",
        holdout_end="2026-07-12 01:00:00",
        recent_start="2026-06-01",
        costs_bps=(40.0,),
        bootstrap_iterations=0,
        max_groups=10,
        max_configs=2,
        min_decay_ratio=0.5,
        min_recent_active_rebalances=1,
        min_recent_time_in_market=0.0,
        holdout_authorized=True,
        force=False,
        skip_existing_any_key=False,
        stop_path=tmp_path / "STOP",
        target_output_jsons=("artifacts/v9/contract_lab/b.json",),
    )

    assert seen == ["group-b"]
    assert report["summary"]["target_matched_count"] == 1
