from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import v9.contract.auto_research as auto_research  # noqa: E402
from v9.contract.auto_research import ResearchTask, run_auto_research  # noqa: E402
from v9.contract.report import write_json  # noqa: E402


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
