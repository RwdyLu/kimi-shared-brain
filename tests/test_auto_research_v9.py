from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import v9.contract.auto_research as auto_research  # noqa: E402
from v9.contract.auto_research import ResearchTask, run_auto_research, run_continuous_research  # noqa: E402
from v9.contract.report import write_json  # noqa: E402
from v9.research.task_planner import PlannedTask, append_explored_record  # noqa: E402


def safe_existing_task(name: str, out_json: Path, out_md: Path) -> ResearchTask:
    return ResearchTask(
        name=name,
        command=(
            "python3",
            "-m",
            "v9.contract.xsec_ohlcv_factory",
            "--preset",
            "core",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ),
        output_json=str(out_json),
        output_md=str(out_md),
        timeout_sec=1,
    )


def strong_train_only_row(config: dict | None = None) -> dict:
    return {
        "advance_passed": True,
        "config": config or {"lookback_h": 1},
        "cost40": {
            "sharpe": 2.4,
            "bootstrap_30d_sharpe_p5": 2.0,
            "max_drawdown": 0.10,
            "active_yearly_bucket_count": 3,
            "positive_active_yearly_bucket_count": 3,
            "rebalance_event_count": 120,
        },
        "validation": {
            "cost40": {
                "sharpe": 2.3,
                "bootstrap_30d_sharpe_p5": 1.9,
                "max_drawdown": 0.11,
                "active_yearly_bucket_count": 3,
                "positive_active_yearly_bucket_count": 3,
                "rebalance_event_count": 120,
            }
        },
    }


def test_default_tasks_are_train_only_and_use_unique_outputs() -> None:
    names = [task.name for task in auto_research.DEFAULT_TASKS]
    output_jsons = [task.output_json for task in auto_research.DEFAULT_TASKS]
    assert len(names) == len(set(names))
    assert len(output_jsons) == len(set(output_jsons))
    assert "xsec_ohlcv_defensive_neighbor_v1" in names
    assert "xsec_ohlcv_defensive_breadth_v1" in names
    assert "xsec_ohlcv_defensive_drawdown_v1" in names
    for task in auto_research.DEFAULT_TASKS:
        command = " ".join(task.command)
        assert "v9.contract.xsec_ohlcv_factory" in command
        assert "holdout" not in command
        assert "paper" not in command
        assert "live" not in command


def test_auto_research_skips_existing_candidate_and_never_authorizes_trading(tmp_path, monkeypatch) -> None:
    out_json = tmp_path / "result.json"
    write_json({"summary": {"accepted_train_only": True}}, out_json)
    task = safe_existing_task("fake", out_json, tmp_path / "result.md")
    monkeypatch.setattr(auto_research, "DEFAULT_TASKS", (task,))
    state = tmp_path / "state.json"
    latest = tmp_path / "latest.txt"
    payload = run_auto_research(state, latest, tmp_path / "logs", force=False)
    assert payload["status"] == "paused"
    assert payload["reason"] == "train_only_candidate_found:fake:manual_review_required"
    assert payload["holdout_authorized"] is False
    assert payload["paper_trading_authorized"] is False
    assert payload["live_trading_authorized"] is False
    assert payload["task_results"][0]["skipped_existing"] is True
    assert payload["candidates_found"][0]["task"] == "fake"
    assert "manual_review_required" in latest.read_text()
    marker = (tmp_path / "FOUND_INTERNAL_CANDIDATE.txt").read_text()
    assert marker.startswith("FOUND_INTERNAL_CANDIDATE ")
    assert "task=fake" in marker
    assert "paper_trading_authorized=False" in marker
    assert "live_trading_authorized=False" in marker


def test_auto_research_can_continue_collecting_after_candidate(tmp_path, monkeypatch) -> None:
    accepted = tmp_path / "accepted.json"
    rejected = tmp_path / "rejected.json"
    write_json({"summary": {"accepted_train_only": True}}, accepted)
    write_json({"summary": {"accepted_train_only": False}}, rejected)
    tasks = (
        safe_existing_task("accepted", accepted, tmp_path / "accepted.md"),
        safe_existing_task("rejected", rejected, tmp_path / "rejected.md"),
    )
    monkeypatch.setattr(auto_research, "DEFAULT_TASKS", tasks)
    payload = run_auto_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        force=False,
        continue_after_candidate=True,
    )
    assert payload["status"] == "paused"
    assert payload["reason"] == "train_only_collection_completed:candidates_found=1:manual_review_required"
    assert [r["task"] for r in payload["task_results"]] == ["accepted", "rejected"]
    assert payload["candidates_found"] == [
        {
            "task": "accepted",
            "output_json": str(accepted),
            "output_md": str(tmp_path / "accepted.md"),
            "status": "manual_review_required",
        }
    ]
    assert payload["holdout_authorized"] is False
    assert payload["paper_trading_authorized"] is False
    assert payload["live_trading_authorized"] is False


def test_auto_research_rejects_unsafe_task_before_writing_state(tmp_path, monkeypatch) -> None:
    task = ResearchTask(
        name="holdout",
        command=("python3", "-m", "scripts.holdout_eval_v8_frozen"),
        output_json=str(tmp_path / "holdout.json"),
        output_md=str(tmp_path / "holdout.md"),
        timeout_sec=1,
    )
    monkeypatch.setattr(auto_research, "DEFAULT_TASKS", (task,))
    state = tmp_path / "state.json"
    try:
        run_auto_research(state, tmp_path / "latest.txt", tmp_path / "logs")
    except ValueError as exc:
        assert "unsafe research task command" in str(exc)
    else:
        raise AssertionError("unsafe task should be rejected")
    assert not state.exists()


def test_auto_research_rejects_train_window_on_or_after_embargo(tmp_path, monkeypatch) -> None:
    out_json = tmp_path / "result.json"
    task = ResearchTask(
        name="leaky",
        command=(
            "python3",
            "-m",
            "v9.contract.xsec_ohlcv_factory",
            "--preset",
            "core",
            "--train-end",
            "2024-07-02",
            "--embargo-start",
            "2024-07-01",
            "--out-json",
            str(out_json),
            "--out-md",
            str(tmp_path / "result.md"),
        ),
        output_json=str(out_json),
        output_md=str(tmp_path / "result.md"),
        timeout_sec=1,
    )
    monkeypatch.setattr(auto_research, "DEFAULT_TASKS", (task,))
    try:
        run_auto_research(tmp_path / "state.json", tmp_path / "latest.txt", tmp_path / "logs")
    except ValueError as exc:
        assert "train_end must be before embargo_start" in str(exc)
    else:
        raise AssertionError("leaky train window should be rejected")


def test_auto_research_accepts_train_only_tsmom_module(tmp_path) -> None:
    out_json = tmp_path / "tsmom.json"
    task = ResearchTask(
        name="tsmom",
        command=(
            "python3",
            "-m",
            "v9.contract.tsmom_factory",
            "--preset",
            "core",
            "--train-end",
            "2024-06-30",
            "--embargo-start",
            "2024-07-01",
            "--out-json",
            str(out_json),
            "--out-md",
            str(tmp_path / "tsmom.md"),
        ),
        output_json=str(out_json),
        output_md=str(tmp_path / "tsmom.md"),
        timeout_sec=1,
    )
    auto_research.validate_train_only_task(task)


def test_auto_research_accepts_train_only_funding_anticarry_module(tmp_path) -> None:
    out_json = tmp_path / "funding.json"
    task = ResearchTask(
        name="funding",
        command=(
            "python3",
            "-m",
            "v9.contract.funding_anticarry_factory",
            "--preset",
            "top30_anti_carry",
            "--train-end",
            "2026-06-30",
            "--embargo-start",
            "2026-07-01",
            "--out-json",
            str(out_json),
            "--out-md",
            str(tmp_path / "funding.md"),
        ),
        output_json=str(out_json),
        output_md=str(tmp_path / "funding.md"),
        timeout_sec=1,
    )
    auto_research.validate_train_only_task(task)


def test_trial_metadata_carries_data_fingerprint() -> None:
    metadata = auto_research.trial_metadata(
        {
            "summary": {"rows": 7},
            "selection_validation": {"n_configs_tested": 3, "prior_trials": 10, "effective_trials": 13},
            "data": {
                "fingerprint": "abc123",
                "snapshot": {
                    "path": "artifacts/v9/data_snapshots/xsec.parquet",
                    "fingerprint": "abc123",
                },
            },
        }
    )
    assert metadata == {
        "n_configs_tested": 3,
        "prior_trials": 10,
        "effective_trials": 13,
        "data_fingerprint": "abc123",
        "data_snapshot_path": "artifacts/v9/data_snapshots/xsec.parquet",
        "data_snapshot_fingerprint": "abc123",
    }


def test_progress_metadata_reports_progress_rows(tmp_path) -> None:
    out_json = tmp_path / "result.json"
    assert auto_research.progress_metadata_for_output(str(out_json)) == {
        "progress_exists": False,
        "progress_rows": 0,
        "progress_bytes": 0,
    }
    progress = tmp_path / "result.progress.jsonl"
    progress.write_text('{"row": 1}\n{"row": 2}\n')
    progress_meta = tmp_path / "result.progress.meta.json"
    progress_meta.write_text('{"cache_version": "v1", "total_rows": 4}\n')
    metadata = auto_research.progress_metadata_for_output(str(out_json))
    assert metadata["progress_exists"] is True
    assert metadata["progress_path"] == str(progress)
    assert metadata["progress_rows"] == 2
    assert metadata["progress_bytes"] == progress.stat().st_size
    assert metadata["progress_total_rows"] == 4
    assert metadata["progress_pct"] == 0.5
    assert metadata["progress_cache_version"] == "v1"


def test_run_task_writes_xsec_diagnostic_review_for_existing_final_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out_json = tmp_path / "artifacts/v9/contract_lab/xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc.json"
    out_md = tmp_path / "artifacts/v9/contract_lab/xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc.md"
    out_json.parent.mkdir(parents=True)
    write_json(
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "summary": {
                "accepted_train_only": False,
                "holdout_authorized": False,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            },
            "rows": [
                {
                    "advance_passed": False,
                    "advance_checks": {"positive_3_of_4_years": False},
                    "config": {
                        "lookback_h": 504,
                        "skip_h": 0,
                        "rebalance_h": 168,
                        "k": 3,
                        "score_mode": "risk_adj_mom",
                        "market_filter_h": 1008,
                        "vol_target_ann": 0.06,
                        "n_tranches": 1,
                    },
                    "cost20": {
                        "sharpe": 2.1,
                        "yearly": {
                            "2021": {"net_return": 0.1},
                            "2022": {"net_return": -0.02},
                            "2023": {"net_return": 0.1},
                            "2024H1": {"net_return": 0.1},
                        },
                    },
                    "validation": {"cost20": {"sharpe": 2.3}},
                    "walk_forward": {"enabled": True, "passed": False, "folds": []},
                    "diagnostic_walk_forward": {
                        "enabled": True,
                        "diagnostic_only": True,
                        "triggered": True,
                        "q25_sharpe": 0.5,
                        "sign_consistency": 0.833,
                        "validation_sharpe20": 2.3,
                        "validation_sharpe20_min": 1.2,
                    },
                }
            ],
        },
        out_json,
    )
    task = safe_existing_task("xsec", out_json, out_md)

    result = auto_research.run_task(task, force=False, log_dir=tmp_path / "logs")

    assert result["skipped_existing"] is True
    assert result["diagnostic_review_json"].endswith("_diagnostic_walkforward_report.json")
    assert result["diagnostic_review_text"].endswith("_diagnostic_walkforward_report.txt")
    review_json = tmp_path / result["diagnostic_review_json"]
    review_text = tmp_path / result["diagnostic_review_text"]
    assert review_json.exists()
    assert review_text.exists()
    assert "diagnostic_triggered=1" in review_text.read_text()
    assert result["rescue_plan_json"].endswith("_rescue_plan.json")
    assert result["rescue_config_json"].endswith("_rescue_configs.json")
    assert result["rescue_config_count"] > 0
    assert (tmp_path / result["rescue_plan_json"]).exists()
    assert (tmp_path / result["rescue_config_json"]).exists()


def test_xsec_rescue_task_from_result_is_train_only_and_non_recursive(tmp_path) -> None:
    config_json = tmp_path / "rescue_configs.json"
    config_json.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "parent.json"),
        output_md=str(tmp_path / "parent.md"),
        prior_trials=20000,
        timeout_sec=99,
    )
    result = {
        "output_json": planned.output_json,
        "rescue_config_json": str(config_json),
        "rescue_config_count": 12,
        "prior_effective_trials": 20081,
        "effective_trials_after_rescue": 20093,
        "data_snapshot_path": "artifacts/v9/data_snapshots/xsec_parent.parquet",
        "data_snapshot_fingerprint": "snap-fp",
    }

    bundle = auto_research.xsec_rescue_task_from_result(planned, result)

    assert bundle is not None
    assert bundle.config_count == 12
    assert bundle.planned_record["is_rescue"] is True
    assert bundle.planned_record["parent_fingerprint"] == "abc123"
    assert bundle.planned_record["root_parent_fingerprint"] == "abc123"
    assert bundle.planned_record["rescue_generation"] == 1
    assert bundle.planned_record["rescue_task_name"] == bundle.task.name
    assert bundle.task.output_json.startswith("artifacts/v9/contract_lab/xsec_ohlcv_rescue_full_202406")
    assert "--config-list-json" in bundle.task.command
    assert "--data-snapshot" in bundle.task.command
    assert "artifacts/v9/data_snapshots/xsec_parent.parquet" in bundle.task.command
    assert "--prior-trials" in bundle.task.command
    assert "20081" in bundle.task.command
    assert "20093" not in bundle.task.command
    assert bundle.planned_record["prior_effective_trials"] == 20081
    assert bundle.planned_record["effective_trials_after_rescue"] == 20093
    assert bundle.planned_record["data_snapshot_path"] == "artifacts/v9/data_snapshots/xsec_parent.parquet"
    assert bundle.planned_record["data_snapshot_fingerprint"] == "snap-fp"
    auto_research.validate_train_only_task(bundle.task)
    command = " ".join(bundle.task.command)
    assert "paper" not in command
    assert "live" not in command

    recursive = dict(result)
    recursive["output_json"] = "artifacts/v9/contract_lab/xsec_ohlcv_rescue_full_202406_hq_dd_plateau.json"
    assert auto_research.xsec_rescue_task_from_result(planned, recursive) is None


def test_xsec_rescue_task_from_result_allows_second_generation_and_caps_depth(tmp_path) -> None:
    first_configs = tmp_path / "rescue_configs_g1.json"
    first_configs.write_text("[]")
    second_configs = tmp_path / "rescue_configs_g2.json"
    second_configs.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "parent.json"),
        output_md=str(tmp_path / "parent.md"),
        prior_trials=20000,
        timeout_sec=99,
    )
    first = auto_research.xsec_rescue_task_from_result(
        planned,
        {
            "output_json": planned.output_json,
            "rescue_config_json": str(first_configs),
            "rescue_config_count": 12,
            "prior_effective_trials": 20081,
        },
    )
    assert first is not None

    second = auto_research.xsec_rescue_task_from_result(
        first.planned_record,
        {
            "output_json": first.task.output_json,
            "rescue_config_json": str(second_configs),
            "rescue_config_count": 5,
            "effective_trials": 20093,
        },
    )

    assert second is not None
    assert second.config_count == 5
    assert second.planned_record["rescue_generation"] == 2
    assert second.planned_record["parent_fingerprint"] == first.fingerprint
    assert second.planned_record["root_parent_fingerprint"] == "abc123"
    assert "_g2_" in second.task.name
    assert "--prior-trials" in second.task.command
    assert "20093" in second.task.command
    auto_research.validate_train_only_task(second.task)

    third = auto_research.xsec_rescue_task_from_result(
        second.planned_record,
        {
            "output_json": second.task.output_json,
            "rescue_config_json": str(second_configs),
            "rescue_config_count": 3,
            "effective_trials": 20098,
        },
    )
    assert third is None


def test_xsec_rescue_generation_from_output_and_artifact_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    gen2 = tmp_path / "artifacts/v9/contract_lab/xsec_ohlcv_rescue_full_202406_case_g2_deadbeef.json"
    gen2.parent.mkdir(parents=True)
    write_json(
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "summary": {"accepted_train_only": False},
            "selection_validation": {"effective_trials": 100},
            "rows": [],
        },
        gen2,
    )

    assert auto_research.rescue_generation_from_output("artifacts/v9/contract_lab/xsec_ohlcv_cont_case.json") == 0
    assert auto_research.rescue_generation_from_output("artifacts/v9/contract_lab/xsec_ohlcv_rescue_case_deadbeef.json") == 1
    assert auto_research.rescue_generation_from_output(str(gen2)) == 2

    metadata = auto_research.maybe_write_xsec_rescue_artifacts(str(gen2))

    assert metadata["rescue_generation"] == 2
    assert metadata["rescue_skipped"] == "max_auto_xsec_rescue_generation"
    assert metadata["rescue_config_count"] == 0


def test_pending_xsec_rescue_bundles_from_results_recovers_unexplored_rescue(tmp_path) -> None:
    config_json = tmp_path / "rescue_configs.json"
    config_json.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "parent.json"),
        output_md=str(tmp_path / "parent.md"),
    )
    result = {
        "fingerprint": planned.fingerprint,
        "planned_task": planned.record(),
        "output_json": planned.output_json,
        "rescue_config_json": str(config_json),
        "rescue_config_count": 3,
        "effective_trials": 84,
    }

    bundles = auto_research.pending_xsec_rescue_bundles_from_results([result], explored={"abc123"})

    assert len(bundles) == 1
    assert bundles[0].planned_record["rescue_generation"] == 1
    assert bundles[0].fingerprint != "abc123"
    assert auto_research.pending_xsec_rescue_bundles_from_results([result], explored={bundles[0].fingerprint}) == []


def test_pending_rescue_bundles_prioritizes_lower_multiplicity_p_value(tmp_path) -> None:
    config_json = tmp_path / "rescue_configs.json"
    config_json.write_text("[]")

    def planned_task(name: str, fingerprint: str) -> PlannedTask:
        return PlannedTask(
            name=name,
            preset="hq_dd_plateau",
            train_start="2017-08-01",
            train_end="2024-06-30 23:59:59",
            embargo_start="2024-07-01",
            fingerprint=fingerprint,
            output_json=str(tmp_path / f"{fingerprint}.json"),
            output_md=str(tmp_path / f"{fingerprint}.md"),
        )

    weaker = planned_task("xsec_ohlcv_cont_full_202406_hq_dd_plateau_weaker", "weaker")
    stronger = planned_task("xsec_ohlcv_cont_full_202406_hq_dd_plateau_stronger", "stronger")

    def result_for(planned: PlannedTask, adjusted_p_value: float) -> dict:
        return {
            "fingerprint": planned.fingerprint,
            "planned_task": planned.record(),
            "output_json": planned.output_json,
            "status": "accepted_train_only_candidate_found",
            "rescue_config_json": str(config_json),
            "rescue_config_count": 3,
            "effective_trials": 84,
            "multiplicity_decision": "rejected_multiplicity",
            "multiplicity_evidence": {
                "decision": "rejected_multiplicity",
                "metrics": {"adjusted_p_value": adjusted_p_value},
            },
        }

    bundles = auto_research.pending_rescue_bundles_from_results(
        [result_for(weaker, 0.60), result_for(stronger, 0.02)],
        explored={"weaker", "stronger"},
    )

    assert [bundle.planned_record["parent_fingerprint"] for bundle in bundles] == ["stronger", "weaker"]
    assert bundles[0].planned_record["rescue_priority"]["policy"] == "multiplicity_adjusted_p_v1"
    assert bundles[0].planned_record["rescue_priority"]["multiplicity_adjusted_p_value"] == 0.02


def test_candidate_multiplicity_metadata_uses_effective_trials_before_candidate_count(
    tmp_path, monkeypatch
) -> None:
    output_json = tmp_path / "candidate.json"
    write_json({"kind": "xsec_ohlcv_factory_v1_train_only_grid", "selection_validation": {}}, output_json)
    seen = {}

    def fake_multiplicity_evidence(payload: dict, *, total_trials: int, **kwargs) -> dict:
        seen["total_trials"] = total_trials
        return {"evaluated": True, "decision": "multiplicity_survivor", "total_trials": total_trials}

    monkeypatch.setattr(auto_research, "multiplicity_evidence", fake_multiplicity_evidence)

    metadata = auto_research.candidate_multiplicity_metadata(
        {"output_json": str(output_json), "effective_trials": 12345},
        total_candidates=2,
    )

    assert seen["total_trials"] == 12345
    assert metadata["multiplicity_evidence"]["total_trials"] == 12345


def test_candidate_multiplicity_metadata_falls_back_to_prior_plus_configs(tmp_path, monkeypatch) -> None:
    output_json = tmp_path / "candidate.json"
    write_json({"kind": "xsec_ohlcv_factory_v1_train_only_grid", "selection_validation": {}}, output_json)
    seen = {}

    def fake_multiplicity_evidence(payload: dict, *, total_trials: int, **kwargs) -> dict:
        seen["total_trials"] = total_trials
        return {"evaluated": True, "decision": "multiplicity_survivor", "total_trials": total_trials}

    monkeypatch.setattr(auto_research, "multiplicity_evidence", fake_multiplicity_evidence)

    auto_research.candidate_multiplicity_metadata(
        {"output_json": str(output_json), "prior_trials": 1000, "n_configs_tested": 25},
        total_candidates=3,
    )

    assert seen["total_trials"] == 1025


def test_refresh_recent_multiplicity_metadata_recomputes_stale_candidate_count_trials(
    tmp_path, monkeypatch
) -> None:
    output_json = tmp_path / "candidate.json"
    write_json(
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "selection_validation": {"effective_trials": 4321},
        },
        output_json,
    )
    seen = {}

    def fake_multiplicity_evidence(payload: dict, *, total_trials: int, **kwargs) -> dict:
        seen["total_trials"] = total_trials
        return {"evaluated": True, "decision": "rejected_multiplicity", "total_trials": total_trials}

    monkeypatch.setattr(auto_research, "multiplicity_evidence", fake_multiplicity_evidence)
    result = {
        "output_json": str(output_json),
        "status": "accepted_train_only_candidate_found",
        "returncode": 0,
        "multiplicity_decision": "multiplicity_survivor",
        "multiplicity_evidence": {"total_trials": 2},
    }

    refreshed = auto_research.refresh_recent_multiplicity_metadata([result])

    assert refreshed == 1
    assert seen["total_trials"] == 4321
    assert result["multiplicity_decision"] == "rejected_multiplicity"
    assert result["multiplicity_evidence"]["total_trials"] == 4321
    assert result["multiplicity_metadata_refresh_policy"] == "startup_recent_effective_trials_v1"


def test_sync_candidate_statuses_from_refreshed_multiplicity_results() -> None:
    candidate = {
        "task": "candidate",
        "output_json": "candidate.json",
        "output_md": "candidate.md",
        "status": "manual_review_required",
    }
    result = {
        "task": "candidate",
        "output_json": "candidate.json",
        "status": "accepted_train_only_candidate_found",
        "multiplicity_decision": "rejected_multiplicity",
        "multiplicity_evidence": {"evaluated": True, "decision": "rejected_multiplicity"},
    }

    updated = auto_research.sync_candidate_statuses_from_results([candidate], [result])

    assert updated == 1
    assert candidate["status"] == "rejected_multiplicity"
    assert candidate["candidate_status_refresh_policy"] == "startup_multiplicity_sync_v1"


def test_sync_internal_candidate_marker_clears_stale_marker_when_no_manual_candidate(tmp_path) -> None:
    marker = tmp_path / "FOUND_INTERNAL_CANDIDATE.txt"
    marker.write_text("FOUND_INTERNAL_CANDIDATE old stale\n")

    auto_research.sync_internal_candidate_marker(
        marker,
        [
            {
                "task": "candidate",
                "output_json": "candidate.json",
                "output_md": "candidate.md",
                "status": "rejected_multiplicity",
            }
        ],
    )

    assert marker.read_text() == "none\n"


def test_refresh_recent_xsec_rescue_metadata_rebuilds_stale_plan_with_current_logic(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    output_json = tmp_path / "artifacts/v9/contract_lab/xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123.json"
    output_json.parent.mkdir(parents=True)
    output_md = output_json.with_suffix(".md")
    config = {
        "lookback_h": 504,
        "skip_h": 0,
        "rebalance_h": 168,
        "k": 3,
        "score_mode": "risk_adj_mom",
        "market_filter_h": 1008,
        "market_confirm_h": 336,
        "market_drawdown_limit": 0.25,
        "vol_target_ann": 0.08,
        "n_tranches": 1,
        "drawdown_stop": 0.10,
        "cooldown_h": 168,
    }
    write_json(
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "summary": {"accepted_train_only": True, "rows": 1},
            "selection_validation": {"effective_trials": 1200},
            "rows": [
                {
                    "advance_passed": True,
                    "config": config,
                    "advance_checks": {},
                    "selection": {
                        "cost20": {
                            "sharpe": 1.7,
                            "bootstrap_30d_sharpe_p5": 0.42,
                            "equal_weight_benchmark": {"sharpe_excess": 0.2},
                            "top_positive_symbol_share": 0.45,
                            "yearly": {
                                "2021": {"net_return": 0.20},
                                "2022": {"net_return": -0.02},
                                "2023": {"net_return": 0.10},
                            },
                        },
                        "cost40": {
                            "sharpe": 1.3,
                            "active_rebalance_event_count": 80,
                            "time_in_market_frac": 0.20,
                        },
                    },
                    "validation": {"cost20": {"sharpe": 1.6}},
                    "diagnostic_walk_forward": {"triggered": False},
                }
            ],
        },
        output_json,
    )
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(output_json),
        output_md=str(output_md),
    )
    result = {
        "fingerprint": planned.fingerprint,
        "planned_task": planned.record(),
        "output_json": str(output_json),
        "output_md": str(output_md),
        "status": "accepted_train_only_candidate_found",
        "returncode": 0,
        "rescue_config_json": "stale.json",
        "rescue_config_count": 0,
    }

    refreshed = auto_research.refresh_recent_xsec_rescue_metadata([result])

    assert refreshed == 1
    assert result["rescue_metadata_refresh_policy"] == "startup_recent_xsec_v1"
    assert result["accepted_train_only_seed_count"] == 1
    assert result["rescue_config_count"] > 0
    assert Path(result["rescue_config_json"]).exists()
    bundles = auto_research.pending_rescue_bundles_from_results([result], explored={"abc123"})
    assert len(bundles) == 1
    assert bundles[0].planned_record["rescue_config_json"] == result["rescue_config_json"]


def test_parent_failure_counts_load_from_rescue_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_path = tmp_path / "artifacts/v9/rescue/xsec_ohlcv_cont_case_rescue_plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(
            {
                "seeds": [
                    {
                        "rescue_relevant_failure_count": 2,
                        "neighbors": [
                            {"config_fingerprint": "aaa"},
                            {"config_fingerprint": "bbb"},
                        ],
                    }
                ]
            }
        )
    )

    inferred = auto_research.parent_rescue_plan_path_for_output(
        "artifacts/v9/contract_lab/xsec_ohlcv_rescue_case_deadbeef.json"
    )

    assert inferred == Path("artifacts/v9/rescue/xsec_ohlcv_cont_case_rescue_plan.json")
    assert auto_research.parent_failure_count_by_config_from_plan(inferred) == {"aaa": 2, "bbb": 2}


def test_xsec_rescue_task_from_result_enforces_config_cap(tmp_path) -> None:
    config_json = tmp_path / "rescue_configs.json"
    config_json.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "parent.json"),
        output_md=str(tmp_path / "parent.md"),
    )
    result = {
        "output_json": planned.output_json,
        "rescue_config_json": str(config_json),
        "rescue_config_count": auto_research.MAX_AUTO_RESCUE_CONFIGS + 1,
    }

    assert auto_research.xsec_rescue_task_from_result(planned, result) is None


def test_tsmom_rescue_task_from_result_is_train_only_and_non_recursive(tmp_path) -> None:
    rescue_configs = tmp_path / "tsmom_rescue_configs.json"
    rescue_configs.write_text(json.dumps([{"asset_vol_target_ann": 0.35, "portfolio_vol_target_ann": 0.12, "no_trade_band": 0.1}]))
    planned = PlannedTask(
        name="tsmom_cont_full_202406_tsmom_bear_short_regime_abc123",
        preset="tsmom_bear_short_regime",
        cli_preset="bear_short_regime",
        module="v9.contract.tsmom_factory",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "planned.json"),
        output_md=str(tmp_path / "planned.md"),
        prior_trials=26000,
    )
    result = {
        "task": planned.name,
        "status": "completed_no_candidate",
        "output_json": planned.output_json,
        "rescue_config_json": str(rescue_configs),
        "rescue_config_count": 1,
        "effective_trials_after_rescue": 26001,
    }

    bundle = auto_research.tsmom_rescue_task_from_result(planned, result)

    assert bundle is not None
    assert bundle.task.output_json.startswith("artifacts/v9/contract_lab/tsmom_rescue_full_202406")
    assert "--config-list-json" in bundle.task.command
    assert "--prior-trials" in bundle.task.command
    assert "26001" in bundle.task.command
    assert bundle.planned_record["rescue_family"] == "tsmom_near_miss"
    assert bundle.planned_record["rescue_generation"] == 1
    assert bundle.planned_record["root_parent_fingerprint"] == "abc123"
    auto_research.validate_train_only_task(bundle.task)
    command = " ".join(bundle.task.command)
    assert "v9.contract.tsmom_factory" in command
    assert "holdout" not in command
    assert "paper" not in command
    assert "live" not in command

    restored = auto_research.tsmom_rescue_task_from_result(planned.record(), result)
    assert restored is not None
    assert restored.fingerprint == bundle.fingerprint
    assert restored.task.command == bundle.task.command

    recursive = dict(result)
    recursive["output_json"] = "artifacts/v9/contract_lab/tsmom_rescue_full_202406_tsmom_bear_short_regime.json"
    assert auto_research.tsmom_rescue_task_from_result(planned, recursive) is None


def test_pending_rescue_bundles_from_results_recovers_unexplored_tsmom_rescue(tmp_path) -> None:
    rescue_configs = tmp_path / "tsmom_rescue_configs.json"
    rescue_configs.write_text(json.dumps([{"asset_vol_target_ann": 0.35, "portfolio_vol_target_ann": 0.12}]))
    planned = PlannedTask(
        name="tsmom_cont_full_202406_tsmom_bear_short_regime_abc123",
        preset="tsmom_bear_short_regime",
        cli_preset="bear_short_regime",
        module="v9.contract.tsmom_factory",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "planned.json"),
        output_md=str(tmp_path / "planned.md"),
        prior_trials=26000,
    )
    result = {
        "fingerprint": planned.fingerprint,
        "planned_task": planned.record(),
        "output_json": planned.output_json,
        "output_md": planned.output_md,
        "status": "completed_no_candidate",
        "returncode": 0,
        "rescue_config_json": str(rescue_configs),
        "rescue_config_count": 1,
        "effective_trials_after_rescue": 26001,
    }

    bundles = auto_research.pending_rescue_bundles_from_results([result], explored={"abc123"})

    assert len(bundles) == 1
    assert bundles[0].task.name.startswith("tsmom_rescue_full_202406")
    assert bundles[0].planned_record["rescue_family"] == "tsmom_near_miss"
    assert bundles[0].planned_record["parent_fingerprint"] == "abc123"
    assert auto_research.pending_rescue_bundles_from_results([result], explored={bundles[0].fingerprint}) == []


def test_backfill_internal_candidate_marker_prefers_non_duplicate(tmp_path) -> None:
    marker = tmp_path / "FOUND_INTERNAL_CANDIDATE.txt"
    marker.write_text("none old\n")
    candidates = [
        {
            "task": "duplicate",
            "output_json": "duplicate.json",
            "output_md": "duplicate.md",
            "status": "manual_review_required",
            "duplicate_of": "parent",
        },
        {
            "task": "primary",
            "output_json": "primary.json",
            "output_md": "primary.md",
            "status": "manual_review_required",
        },
    ]

    auto_research.backfill_internal_candidate_marker(marker, candidates)

    text = marker.read_text()
    assert text.startswith("FOUND_INTERNAL_CANDIDATE ")
    assert "task=primary" in text
    assert "paper_trading_authorized=False" in text
    assert "live_trading_authorized=False" in text


def test_data_drift_marks_candidate_for_manual_review() -> None:
    planned = {
        "train_start": "2017-08-01",
        "train_end": "2024-06-30 23:59:59",
        "embargo_start": "2024-07-01",
    }
    previous = {"planned_task": planned, "data_fingerprint": "old"}
    current = {
        "planned_task": planned,
        "data_fingerprint": "new",
        "fingerprint": "fp",
        "output_json": "out.json",
        "output_md": "out.md",
    }
    task = ResearchTask(
        name="candidate",
        command=("python3", "-m", "v9.contract.xsec_ohlcv_factory", "--out-json", "out.json", "--out-md", "out.md"),
        output_json="out.json",
        output_md="out.md",
        timeout_sec=1,
    )
    assert auto_research.has_data_drift([previous], current) is True
    record = auto_research.candidate_record(task, current, status="quarantined_data_drift")
    assert record["status"] == "quarantined_data_drift"
    assert record["data_fingerprint"] == "new"


def test_data_drift_ignores_different_data_scope_for_same_window() -> None:
    window = {
        "train_start": "2017-08-01",
        "train_end": "2024-06-30 23:59:59",
        "embargo_start": "2024-07-01",
    }
    previous = {
        "planned_task": {
            **window,
            "module": "v9.contract.xsec_ohlcv_factory",
            "preset": "hq_dd_plateau",
            "cli_preset": "hq_dd_plateau",
        },
        "data_fingerprint": "xsec",
    }
    current = {
        "planned_task": {
            **window,
            "module": "v9.contract.tsmom_factory",
            "preset": "tsmom_core_slow_cost_guard",
            "cli_preset": "core_slow_cost_guard",
        },
        "data_fingerprint": "tsmom",
    }

    assert auto_research.has_data_drift([previous], current) is False


def test_data_drift_still_detects_same_data_scope_for_same_window() -> None:
    planned = {
        "train_start": "2017-08-01",
        "train_end": "2024-06-30 23:59:59",
        "embargo_start": "2024-07-01",
        "module": "v9.contract.xsec_ohlcv_factory",
        "preset": "hq_dd_plateau",
        "cli_preset": "hq_dd_plateau",
    }
    previous = {"planned_task": planned, "data_fingerprint": "old"}
    current = {"planned_task": planned, "data_fingerprint": "new"}

    assert auto_research.has_data_drift([previous], current) is True


def test_data_drift_survives_restart_via_explored_log(tmp_path) -> None:
    explored = tmp_path / "explored.jsonl"
    window = {
        "train_start": "2017-08-01",
        "train_end": "2024-06-30 23:59:59",
        "embargo_start": "2024-07-01",
    }
    append_explored_record(explored, {**window, "fingerprint": "t1", "data_fingerprint": "old"})
    append_explored_record(explored, {"fingerprint": "legacy_no_window", "data_fingerprint": "ignored"})

    history = auto_research.drift_history_from_explored(explored)
    assert len(history) == 1
    assert history[0]["planned_task"] == window
    assert history[0]["data_fingerprint"] == "old"

    current = {"planned_task": window, "data_fingerprint": "new"}
    same = {"planned_task": window, "data_fingerprint": "old"}
    assert auto_research.has_data_drift(history, current) is True
    assert auto_research.has_data_drift(history, same) is False


def test_drift_history_infers_scope_from_explored_task_name(tmp_path) -> None:
    explored = tmp_path / "explored.jsonl"
    window = {
        "train_start": "2017-08-01",
        "train_end": "2024-06-30 23:59:59",
        "embargo_start": "2024-07-01",
    }
    append_explored_record(
        explored,
        {
            **window,
            "fingerprint": "t1",
            "task": "tsmom_cont_full_202406_tsmom_core_slow_cost_guard_abc123",
            "data_fingerprint": "old",
        },
    )

    history = auto_research.drift_history_from_explored(explored)

    assert history[0]["planned_task"] == {
        **window,
        "module": "v9.contract.tsmom_factory",
        "preset": "tsmom_core_slow_cost_guard",
        "cli_preset": "core_slow_cost_guard",
    }


def test_continuous_research_honors_stop_file(tmp_path) -> None:
    control = tmp_path / "control"
    control.mkdir()
    (control / "STOP").write_text("stop")
    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        control,
        cycle_sleep_sec=0,
    )
    assert payload["status"] == "paused"
    assert payload["reason"] == "manual_stop_file"
    assert payload["task_results"] == []


def test_continuous_research_records_planned_task_and_continues_until_manual_stop(tmp_path, monkeypatch) -> None:
    planned = PlannedTask(
        name="planned",
        preset="core",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "planned.json"),
        output_md=str(tmp_path / "planned.md"),
        timeout_sec=1,
    )
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [planned] if "abc123" not in explored else [])
    control = tmp_path / "control"

    def fake_run_task(task: ResearchTask, force: bool, log_dir: Path, heartbeat=None) -> dict:
        write_json(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "symbols": ["AAA", "BBB"],
                "summary": {"accepted_train_only": True},
                "rows": [strong_train_only_row({"lookback_h": 1})],
            },
            Path(task.output_json),
        )
        control.mkdir(parents=True, exist_ok=True)
        (control / "STOP").write_text("stop after first accepted task")
        return {
            "task": task.name,
            "status": "accepted_train_only_candidate_found",
            "skipped_existing": False,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
        }

    monkeypatch.setattr(auto_research, "run_task", fake_run_task)
    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        control,
        planner_batch_size=1,
        target_distinct_candidates=1,
        cycle_sleep_sec=0,
    )
    assert payload["status"] == "paused"
    assert payload["reason"] == "manual_stop_file"
    assert payload["mode"] == "continuous"
    assert payload["task_results"][0]["fingerprint"] == "abc123"
    assert "abc123" in (tmp_path / "explored.jsonl").read_text()
    marker = (tmp_path / "FOUND_INTERNAL_CANDIDATE.txt").read_text()
    assert "task=planned" in marker
    assert "paper_trading_authorized=False" in marker


def test_continuous_research_writes_tsmom_family_review_after_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    planned = PlannedTask(
        name="tsmom_cont_full_202406_tsmom_bear_short_regime_abc123",
        preset="tsmom_bear_short_regime",
        cli_preset="bear_short_regime",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "artifacts/v9/contract_lab/tsmom.json"),
        output_md=str(tmp_path / "artifacts/v9/contract_lab/tsmom.md"),
        timeout_sec=1,
        module="v9.contract.tsmom_factory",
    )
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [planned])
    control = tmp_path / "control"

    def fake_run_task(task: ResearchTask, force: bool, log_dir: Path, heartbeat=None) -> dict:
        write_json(
            {
                "kind": "tsmom_factory_v1_train_only_grid",
                "summary": {
                    "accepted_train_only": True,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                    "pass_count": 1,
                    "rows": 1,
                },
                "data": {
                    "fingerprint": "train-fp",
                    "first_dt": "2020-01-01T00:00:00+00:00",
                    "last_dt": "2024-06-30T23:00:00+00:00",
                    "rows": 100,
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                },
                "selection_validation": {"n_configs_tested": 1, "effective_trials": 1},
                "rows": [
                    {
                        **strong_train_only_row(
                            {"asset_vol_target_ann": 0.35, "portfolio_vol_target_ann": 0.12}
                        ),
                        "advance_passed": True,
                        "cost20": {"sharpe": 1.4, "total_return": 0.2, "max_drawdown": 0.12},
                        "advance_checks": {"validation_sharpe20_ge_adjusted_min": True},
                    }
                ],
            },
            Path(task.output_json),
        )
        control.mkdir(parents=True, exist_ok=True)
        (control / "STOP").write_text("stop after tsmom candidate")
        return {
            "task": task.name,
            "status": "accepted_train_only_candidate_found",
            "skipped_existing": False,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
            "n_configs_tested": 1,
            "data_fingerprint": "train-fp",
            "data_symbols": ["BTCUSDT", "ETHUSDT"],
        }

    monkeypatch.setattr(auto_research, "run_task", fake_run_task)

    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        control,
        planner_batch_size=1,
        cycle_sleep_sec=0,
    )

    result = payload["task_results"][0]
    review_json = tmp_path / result["tsmom_family_review_json"]
    review_md = tmp_path / result["tsmom_family_review_md"]
    review = json.loads(review_json.read_text())
    assert review_json.exists()
    assert review_md.exists()
    assert result["tsmom_family_review_primary_task"] == planned.name
    assert result["tsmom_family_review_decision"] == "train_only_family_candidate_but_needs_drift_review"
    assert review["candidate_record_count"] == 1
    assert review["quarantined_data_drift_count"] == 0
    assert review["holdout_authorized"] is False
    assert review["paper_trading_authorized"] is False
    assert review["live_trading_authorized"] is False


def test_continuous_research_rejects_candidate_that_fails_multiplicity_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    planned = PlannedTask(
        name="weak_tsmom",
        preset="tsmom_bear_short_regime",
        cli_preset="bear_short_regime",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="weak123",
        output_json=str(tmp_path / "artifacts/v9/contract_lab/weak_tsmom.json"),
        output_md=str(tmp_path / "artifacts/v9/contract_lab/weak_tsmom.md"),
        timeout_sec=1,
        module="v9.contract.tsmom_factory",
    )
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [planned])
    control = tmp_path / "control"

    def fake_run_task(task: ResearchTask, force: bool, log_dir: Path, heartbeat=None) -> dict:
        write_json(
            {
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
                                "sharpe": 1.2,
                                "bootstrap_30d_sharpe_p5": -1.0,
                                "max_drawdown": 0.20,
                                "active_yearly_bucket_count": 3,
                                "positive_active_yearly_bucket_count": 2,
                                "rebalance_event_count": 120,
                            }
                        },
                    }
                ],
            },
            Path(task.output_json),
        )
        control.mkdir(parents=True, exist_ok=True)
        (control / "STOP").write_text("stop after rejected candidate")
        return {
            "task": task.name,
            "status": "accepted_train_only_candidate_found",
            "skipped_existing": False,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
            "data_fingerprint": "train-fp",
        }

    monkeypatch.setattr(auto_research, "run_task", fake_run_task)

    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        control,
        planner_batch_size=1,
        cycle_sleep_sec=0,
    )

    assert payload["candidates_found"][0]["status"] == "rejected_multiplicity"
    assert payload["distinct_candidates"] == 0
    assert payload["task_results"][0]["multiplicity_decision"] == "rejected_multiplicity"
    assert not (tmp_path / "FOUND_INTERNAL_CANDIDATE.txt").exists()


def test_continuous_research_runs_auto_xsec_rescue_after_primary_batch(tmp_path, monkeypatch) -> None:
    rescue_configs = tmp_path / "rescue_configs.json"
    rescue_configs.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "planned.json"),
        output_md=str(tmp_path / "planned.md"),
        timeout_sec=1,
    )
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [planned])
    calls = []

    def fake_run_task(task: ResearchTask, force: bool, log_dir: Path, heartbeat=None) -> dict:
        calls.append(task.name)
        if "rescue" in task.name:
            return {
                "task": task.name,
                "status": "completed_no_candidate",
                "skipped_existing": False,
                "output_json": task.output_json,
                "output_md": task.output_md,
                "returncode": 0,
                "n_configs_tested": 1,
                "prior_trials": 81,
                "effective_trials": 82,
            }
        return {
            "task": task.name,
            "status": "completed_no_candidate",
            "skipped_existing": False,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
            "n_configs_tested": 81,
            "prior_trials": 0,
            "effective_trials": 81,
            "rescue_config_json": str(rescue_configs),
            "rescue_config_count": 1,
        }

    monkeypatch.setattr(auto_research, "run_task", fake_run_task)

    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        tmp_path / "control",
        planner_batch_size=1,
        max_cycles=1,
        cycle_sleep_sec=0,
    )

    assert payload["status"] == "paused"
    assert payload["reason"] == "budget_exhausted:max_cycles"
    assert calls[0] == planned.name
    assert "rescue" in calls[1]
    assert payload["task_results"][1]["is_rescue"] is True
    assert payload["task_results"][1]["planned_task"]["parent_fingerprint"] == "abc123"
    explored = (tmp_path / "explored.jsonl").read_text()
    assert "abc123" in explored
    assert '"is_rescue": true' in explored


def test_continuous_research_runs_capped_second_generation_xsec_rescue(tmp_path, monkeypatch) -> None:
    rescue_configs_g1 = tmp_path / "rescue_configs_g1.json"
    rescue_configs_g1.write_text("[]")
    rescue_configs_g2 = tmp_path / "rescue_configs_g2.json"
    rescue_configs_g2.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "planned.json"),
        output_md=str(tmp_path / "planned.md"),
        timeout_sec=1,
    )
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [planned])
    calls = []

    def fake_run_task(task: ResearchTask, force: bool, log_dir: Path, heartbeat=None) -> dict:
        calls.append(task.name)
        if "_g2_" in task.name:
            return {
                "task": task.name,
                "status": "completed_no_candidate",
                "skipped_existing": False,
                "output_json": task.output_json,
                "output_md": task.output_md,
                "returncode": 0,
                "n_configs_tested": 1,
                "prior_trials": 82,
                "effective_trials": 83,
            }
        if "rescue" in task.name:
            return {
                "task": task.name,
                "status": "completed_no_candidate",
                "skipped_existing": False,
                "output_json": task.output_json,
                "output_md": task.output_md,
                "returncode": 0,
                "n_configs_tested": 1,
                "prior_trials": 81,
                "effective_trials": 82,
                "rescue_config_json": str(rescue_configs_g2),
                "rescue_config_count": 1,
            }
        return {
            "task": task.name,
            "status": "completed_no_candidate",
            "skipped_existing": False,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
            "n_configs_tested": 81,
            "prior_trials": 0,
            "effective_trials": 81,
            "rescue_config_json": str(rescue_configs_g1),
            "rescue_config_count": 1,
        }

    monkeypatch.setattr(auto_research, "run_task", fake_run_task)

    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        tmp_path / "control",
        planner_batch_size=1,
        max_cycles=1,
        cycle_sleep_sec=0,
    )

    assert payload["status"] == "paused"
    assert calls[0] == planned.name
    assert "rescue" in calls[1]
    assert "_g2_" in calls[2]
    assert payload["task_results"][1]["planned_task"]["rescue_generation"] == 1
    assert payload["task_results"][2]["planned_task"]["rescue_generation"] == 2
    assert payload["task_results"][2]["planned_task"]["parent_fingerprint"] == payload["task_results"][1]["fingerprint"]
    explored = (tmp_path / "explored.jsonl").read_text()
    assert '"rescue_generation": 1' in explored
    assert '"rescue_generation": 2' in explored


def test_continuous_research_backfills_pending_xsec_rescue_before_new_task(tmp_path, monkeypatch) -> None:
    rescue_configs = tmp_path / "rescue_configs.json"
    rescue_configs.write_text("[]")
    planned = PlannedTask(
        name="xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
        preset="hq_dd_plateau",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        fingerprint="abc123",
        output_json=str(tmp_path / "planned.json"),
        output_md=str(tmp_path / "planned.md"),
        timeout_sec=1,
    )
    state = tmp_path / "state.json"
    write_json(
        {
            "cycle_index": 0,
            "task_results": [
                {
                    "fingerprint": planned.fingerprint,
                    "planned_task": planned.record(),
                    "output_json": planned.output_json,
                    "output_md": planned.output_md,
                    "status": "completed_no_candidate",
                    "returncode": 0,
                    "rescue_config_json": str(rescue_configs),
                    "rescue_config_count": 1,
                    "effective_trials": 81,
                }
            ],
            "candidates_found": [],
        },
        state,
    )
    append_explored_record(
        tmp_path / "explored.jsonl",
        {
            "fingerprint": planned.fingerprint,
            "task": planned.name,
            "n_configs_tested": 81,
        },
    )
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [planned])
    calls = []

    def fake_run_task(task: ResearchTask, force: bool, log_dir: Path, heartbeat=None) -> dict:
        calls.append(task.name)
        return {
            "task": task.name,
            "status": "completed_no_candidate",
            "skipped_existing": False,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
            "n_configs_tested": 1,
            "prior_trials": 81,
            "effective_trials": 82,
        }

    monkeypatch.setattr(auto_research, "run_task", fake_run_task)

    payload = run_continuous_research(
        state,
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        tmp_path / "control",
        planner_batch_size=1,
        max_cycles=1,
        cycle_sleep_sec=0,
    )

    assert payload["status"] == "paused"
    assert len(calls) == 1
    assert calls[0].startswith("xsec_ohlcv_rescue_")
    assert calls[0] != planned.name
    assert payload["task_results"][-1]["is_rescue"] is True
    assert payload["task_results"][-1]["planned_task"]["rescue_generation"] == 1


def test_continuous_research_idles_when_search_space_is_exhausted_until_stop(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(auto_research, "propose_tasks", lambda explored, count, **kwargs: [])
    control = tmp_path / "control"
    states = []
    original_write_state = auto_research.write_state

    def recording_write_state(*args, **kwargs):
        payload = original_write_state(*args, **kwargs)
        states.append(payload["status"])
        return payload

    def stop_after_idle_sleep(seconds: float) -> None:
        control.mkdir(parents=True, exist_ok=True)
        (control / "STOP").write_text("stop idle")

    monkeypatch.setattr(auto_research, "write_state", recording_write_state)
    monkeypatch.setattr(auto_research.time, "sleep", stop_after_idle_sleep)
    payload = run_continuous_research(
        tmp_path / "state.json",
        tmp_path / "latest.txt",
        tmp_path / "logs",
        tmp_path / "explored.jsonl",
        control,
        idle_backoff_initial_sec=0.1,
        idle_poll_sec=0.1,
        cycle_sleep_sec=0,
    )
    assert "idle" in states
    assert payload["status"] == "paused"
    assert payload["reason"] == "manual_stop_file"
