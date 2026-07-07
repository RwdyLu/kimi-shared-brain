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
    metadata = auto_research.progress_metadata_for_output(str(out_json))
    assert metadata["progress_exists"] is True
    assert metadata["progress_path"] == str(progress)
    assert metadata["progress_rows"] == 2
    assert metadata["progress_bytes"] == progress.stat().st_size


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
