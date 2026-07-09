from __future__ import annotations

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


def test_trial_metadata_carries_data_fingerprint() -> None:
    metadata = auto_research.trial_metadata(
        {
            "summary": {"rows": 7},
            "selection_validation": {"n_configs_tested": 3, "prior_trials": 10, "effective_trials": 13},
            "data": {"fingerprint": "abc123"},
        }
    )
    assert metadata == {
        "n_configs_tested": 3,
        "prior_trials": 10,
        "effective_trials": 13,
        "data_fingerprint": "abc123",
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
        "effective_trials": 20081,
    }

    bundle = auto_research.xsec_rescue_task_from_result(planned, result)

    assert bundle is not None
    assert bundle.config_count == 12
    assert bundle.planned_record["is_rescue"] is True
    assert bundle.planned_record["parent_fingerprint"] == "abc123"
    assert bundle.task.output_json.startswith("artifacts/v9/contract_lab/xsec_ohlcv_rescue_full_202406")
    assert "--config-list-json" in bundle.task.command
    assert "--prior-trials" in bundle.task.command
    assert "20081" in bundle.task.command
    auto_research.validate_train_only_task(bundle.task)
    command = " ".join(bundle.task.command)
    assert "paper" not in command
    assert "live" not in command

    recursive = dict(result)
    recursive["output_json"] = "artifacts/v9/contract_lab/xsec_ohlcv_rescue_full_202406_hq_dd_plateau.json"
    assert auto_research.xsec_rescue_task_from_result(planned, recursive) is None


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
    record = auto_research.candidate_record(task, current, status="manual_review_required_data_drift")
    assert record["status"] == "manual_review_required_data_drift"
    assert record["data_fingerprint"] == "new"


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
                "rows": [{"advance_passed": True, "config": {"lookback_h": 1}}],
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
