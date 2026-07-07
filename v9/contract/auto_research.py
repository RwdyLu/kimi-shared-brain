from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .report import write_json
from v9.research.candidate_dedupe import dedupe_candidates, distinct_candidate_count
from v9.research.task_planner import (
    PlannedTask,
    append_explored_record,
    cumulative_trials,
    legacy_fingerprints_from_results,
    load_explored_fingerprints,
    propose_tasks,
)


TRAIN_ONLY_MODULE = "v9.contract.xsec_ohlcv_factory"
DEFAULT_TRAIN_END = "2024-06-30 23:59:59"
DEFAULT_EMBARGO_START = "2024-07-01"
FORBIDDEN_COMMAND_FRAGMENTS = (
    "holdout",
    "paper",
    "live",
    "freqtrade",
    "exchange",
    "api-key",
    "apikey",
    "secret",
    "token",
)


@dataclass(frozen=True)
class ResearchTask:
    name: str
    command: tuple[str, ...]
    output_json: str
    output_md: str
    timeout_sec: int


def xsec_ohlcv_task(
    name: str,
    preset: str,
    timeout_sec: int = 2 * 60 * 60,
    bootstrap_iterations: int = 100,
) -> ResearchTask:
    output_json = f"artifacts/v9/contract_lab/{name}.json"
    output_md = f"artifacts/v9/contract_lab/{name}.md"
    return ResearchTask(
        name=name,
        command=(
            "python3",
            "-m",
            "v9.contract.xsec_ohlcv_factory",
            "--preset",
            preset,
            "--bootstrap-iterations",
            str(bootstrap_iterations),
            "--out-json",
            output_json,
            "--out-md",
            output_md,
        ),
        output_json=output_json,
        output_md=output_md,
        timeout_sec=timeout_sec,
    )


DEFAULT_TASKS = (
    xsec_ohlcv_task("xsec_ohlcv_core_v1", "core"),
    xsec_ohlcv_task("xsec_ohlcv_defensive_v1", "defensive"),
    xsec_ohlcv_task("xsec_ohlcv_slow_v1", "slow"),
    xsec_ohlcv_task("xsec_ohlcv_fast_v1", "fast"),
    xsec_ohlcv_task("xsec_ohlcv_defensive_neighbor_v1", "defensive_neighbor", timeout_sec=3 * 60 * 60),
    xsec_ohlcv_task("xsec_ohlcv_defensive_breadth_v1", "defensive_breadth", timeout_sec=3 * 60 * 60),
    xsec_ohlcv_task("xsec_ohlcv_defensive_drawdown_v1", "defensive_drawdown", timeout_sec=3 * 60 * 60),
)


def research_task_from_planned(task: PlannedTask) -> ResearchTask:
    return ResearchTask(
        name=task.name,
        command=task.command(),
        output_json=task.output_json,
        output_md=task.output_md,
        timeout_sec=task.timeout_sec,
    )


def command_option(command: tuple[str, ...], option: str, default: str) -> str:
    if option not in command:
        return default
    idx = command.index(option)
    if idx + 1 >= len(command):
        raise ValueError(f"{option} requires a value")
    return command[idx + 1]


def utc_ts(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC") if ts.tzinfo else pd.Timestamp(value, tz="UTC")


def validate_train_only_task(task: ResearchTask) -> None:
    if len(task.command) < 3 or task.command[:3] != ("python3", "-m", TRAIN_ONLY_MODULE):
        raise ValueError(f"unsafe research task command for {task.name}: only {TRAIN_ONLY_MODULE} is allowed")

    command_text = " ".join(task.command).lower()
    for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
        if fragment in command_text:
            raise ValueError(f"unsafe research task command for {task.name}: forbidden fragment {fragment!r}")

    train_end = utc_ts(command_option(task.command, "--train-end", DEFAULT_TRAIN_END))
    embargo_start = utc_ts(command_option(task.command, "--embargo-start", DEFAULT_EMBARGO_START))
    if train_end >= embargo_start:
        raise ValueError(f"unsafe research task window for {task.name}: train_end must be before embargo_start")


def validate_train_only_tasks(tasks: tuple[ResearchTask, ...]) -> None:
    seen_outputs: set[str] = set()
    for task in tasks:
        validate_train_only_task(task)
        if task.output_json in seen_outputs:
            raise ValueError(f"duplicate research output_json: {task.output_json}")
        seen_outputs.add(task.output_json)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def task_result_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "missing"
    summary = payload.get("summary", {})
    if summary.get("accepted_train_only"):
        return "accepted_train_only_candidate_found"
    return "completed_no_candidate"


def progress_metadata_for_output(output_json: str) -> dict[str, Any]:
    progress_path = Path(output_json).with_suffix(".progress.jsonl")
    progress_meta_path = Path(output_json).with_suffix(".progress.meta.json")
    if not progress_path.exists():
        return {"progress_exists": False, "progress_rows": 0, "progress_bytes": 0}
    try:
        progress_rows = sum(1 for _ in progress_path.open())
        progress_bytes = progress_path.stat().st_size
    except OSError:
        return {"progress_exists": False, "progress_rows": 0, "progress_bytes": 0}
    metadata: dict[str, Any] = {
        "progress_exists": True,
        "progress_path": str(progress_path),
        "progress_rows": int(progress_rows),
        "progress_bytes": int(progress_bytes),
    }
    if progress_meta_path.exists():
        try:
            progress_meta = json.loads(progress_meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            progress_meta = {}
        total_rows = int(progress_meta.get("total_rows") or 0)
        if total_rows > 0:
            metadata["progress_total_rows"] = total_rows
            metadata["progress_pct"] = round(min(1.0, progress_rows / total_rows), 6)
        if progress_meta.get("cache_version"):
            metadata["progress_cache_version"] = str(progress_meta["cache_version"])
    return metadata


def trial_metadata(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    selection_validation = payload.get("selection_validation", {}) or {}
    summary = payload.get("summary", {}) or {}
    data = payload.get("data", {}) or {}
    n_configs = int(selection_validation.get("n_configs_tested") or summary.get("rows") or 0)
    metadata: dict[str, Any] = {"n_configs_tested": n_configs}
    for key in ("prior_trials", "effective_trials"):
        if key in selection_validation:
            metadata[key] = int(selection_validation.get(key) or 0)
    if data.get("fingerprint"):
        metadata["data_fingerprint"] = str(data["fingerprint"])
    return metadata


def cumulative_trials_from_results(task_results: list[dict[str, Any]]) -> int:
    total = 0
    for result in task_results:
        if result.get("n_configs_tested") is not None:
            total += int(result.get("n_configs_tested") or 0)
            continue
        output_json = result.get("output_json")
        if not output_json:
            continue
        total += int(trial_metadata(read_json(Path(str(output_json)))).get("n_configs_tested", 0))
    return total


def planned_window_key(result: dict[str, Any]) -> tuple[str, str, str] | None:
    planned = result.get("planned_task") or {}
    if not planned:
        return None
    keys = ("train_start", "train_end", "embargo_start")
    if not all(planned.get(key) for key in keys):
        return None
    return tuple(str(planned[key]) for key in keys)


def has_data_drift(task_results: list[dict[str, Any]], result: dict[str, Any]) -> bool:
    fingerprint = result.get("data_fingerprint")
    key = planned_window_key(result)
    if not fingerprint or key is None:
        return False
    for previous in task_results:
        if planned_window_key(previous) != key:
            continue
        previous_fingerprint = previous.get("data_fingerprint")
        if previous_fingerprint and previous_fingerprint != fingerprint:
            return True
    return False


def drift_history_from_explored(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    keys = ("train_start", "train_end", "embargo_start")
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row.get("data_fingerprint") or not all(row.get(key) for key in keys):
            continue
        rows.append(
            {
                "planned_task": {key: str(row[key]) for key in keys},
                "data_fingerprint": str(row["data_fingerprint"]),
            }
        )
    return rows


def candidate_record(task: ResearchTask, result: dict[str, Any], status: str = "manual_review_required") -> dict[str, Any]:
    record = {
        "task": task.name,
        "output_json": result["output_json"],
        "output_md": result["output_md"],
        "status": status,
    }
    if result.get("fingerprint"):
        record["fingerprint"] = result["fingerprint"]
    if result.get("data_fingerprint"):
        record["data_fingerprint"] = result["data_fingerprint"]
    return record


def write_latest_summary(path: Path, status: str, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pd.Timestamp.now(tz='UTC').isoformat()} status={status} reason={reason}\n")


def state_payload(
    started_at: str,
    status: str,
    reason: str,
    task_results: list[dict[str, Any]],
    current_task: str | None = None,
    active_task: dict[str, Any] | None = None,
    candidates_found: list[dict[str, Any]] | None = None,
    tasks: tuple[ResearchTask, ...] = DEFAULT_TASKS,
    mode: str = "oneshot",
    cycle_index: int = 0,
    stop_reason: str | None = None,
    deadline_at: str | None = None,
) -> dict[str, Any]:
    enriched_candidates = dedupe_candidates(candidates_found or [])
    payload = {
        "created_at": started_at,
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "v9_auto_research_train_only_state",
        "mode": mode,
        "status": status,
        "reason": reason,
        "stop_reason": stop_reason,
        "cycle_index": cycle_index,
        "current_task": current_task,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "tasks": [asdict(task) for task in tasks],
        "task_results": task_results,
        "tasks_done_total": len(task_results),
        "candidates_found": enriched_candidates,
        "candidates_found_total": len(enriched_candidates),
        "distinct_candidates": distinct_candidate_count(enriched_candidates),
    }
    if deadline_at is not None:
        payload["deadline_at"] = deadline_at
    if active_task is not None:
        payload["active_task"] = active_task
    return payload


def write_state(
    path: Path,
    started_at: str,
    status: str,
    reason: str,
    task_results: list[dict[str, Any]],
    current_task: str | None = None,
    active_task: dict[str, Any] | None = None,
    candidates_found: list[dict[str, Any]] | None = None,
    tasks: tuple[ResearchTask, ...] = DEFAULT_TASKS,
    mode: str = "oneshot",
    cycle_index: int = 0,
    stop_reason: str | None = None,
    deadline_at: str | None = None,
) -> dict[str, Any]:
    payload = state_payload(
        started_at,
        status,
        reason,
        task_results,
        current_task,
        active_task,
        candidates_found,
        tasks,
        mode,
        cycle_index,
        stop_reason,
        deadline_at,
    )
    write_json(payload, path)
    return payload


def run_task(
    task: ResearchTask,
    force: bool,
    log_dir: Path,
    heartbeat: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    out_path = Path(task.output_json)
    existing = read_json(out_path)
    if existing and not force:
        return {
            "task": task.name,
            "status": task_result_status(existing),
            "skipped_existing": True,
            "output_json": task.output_json,
            "output_md": task.output_md,
            "returncode": 0,
            **trial_metadata(existing),
        }

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{task.name}_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}.log"
    started = time.time()
    with log_path.open("w") as log:
        proc = subprocess.Popen(task.command, stdout=log, stderr=subprocess.STDOUT, text=True)
        last_heartbeat = 0.0
        returncode = 124
        while True:
            polled = proc.poll()
            elapsed = time.time() - started
            if polled is not None:
                returncode = polled
                break
            if elapsed >= task.timeout_sec:
                proc.kill()
                proc.wait(timeout=10)
                returncode = 124
                break
            if heartbeat is not None and elapsed - last_heartbeat >= 30.0:
                heartbeat(elapsed)
                last_heartbeat = elapsed
            time.sleep(1.0)
    payload = read_json(out_path)
    return {
        "task": task.name,
        "status": task_result_status(payload) if returncode == 0 else "failed",
        "skipped_existing": False,
        "output_json": task.output_json,
        "output_md": task.output_md,
        "log": str(log_path),
        "returncode": returncode,
        "elapsed_sec": round(time.time() - started, 3),
        **trial_metadata(payload),
    }


def run_auto_research(
    state_path: Path,
    latest_summary_path: Path,
    log_dir: Path,
    force: bool = False,
    continue_after_candidate: bool = False,
) -> dict[str, Any]:
    validate_train_only_tasks(DEFAULT_TASKS)
    started_at = pd.Timestamp.now(tz="UTC").isoformat()
    write_latest_summary(latest_summary_path, "running", "v9_auto_research_train_only")
    task_results = []
    candidates_found = []
    write_state(
        state_path,
        started_at,
        "running",
        "v9_auto_research_train_only:starting",
        task_results,
        current_task=None,
        candidates_found=candidates_found,
    )
    final_status = "completed_no_candidate"
    final_reason = "all_train_only_tasks_completed_without_candidate"

    for task in DEFAULT_TASKS:
        reason = f"v9_auto_research_train_only:{task.name}"
        write_latest_summary(latest_summary_path, "running", reason)
        write_state(
            state_path,
            started_at,
            "running",
            reason,
            task_results,
            current_task=task.name,
            candidates_found=candidates_found,
        )
        def heartbeat(elapsed: float, task_name: str = task.name) -> None:
            write_state(
                state_path,
                started_at,
                "running",
                reason,
                task_results,
                current_task=task_name,
                active_task={
                    "name": task_name,
                    "status": "running",
                    "elapsed_sec": round(elapsed, 3),
                    **progress_metadata_for_output(task.output_json),
                },
                candidates_found=candidates_found,
            )

        result = run_task(task, force=force, log_dir=log_dir, heartbeat=heartbeat)
        task_results.append(result)
        if result["status"] == "accepted_train_only_candidate_found":
            candidates_found.append(candidate_record(task, result))
        write_state(
            state_path,
            started_at,
            "running",
            f"task_completed:{task.name}",
            task_results,
            current_task=None,
            candidates_found=candidates_found,
        )
        if result["status"] == "accepted_train_only_candidate_found":
            if not continue_after_candidate:
                final_status = "paused"
                final_reason = f"train_only_candidate_found:{task.name}:manual_review_required"
                break
            final_status = "running"
            final_reason = f"train_only_candidate_collected:{task.name}:continuing"
            continue
        if result["status"] == "failed":
            final_status = "paused"
            final_reason = f"task_failed:{task.name}"
            break

    if final_status == "completed_no_candidate":
        final_status = "paused"
    if continue_after_candidate and candidates_found and final_status != "paused":
        final_status = "paused"
        final_reason = f"train_only_collection_completed:candidates_found={len(candidates_found)}:manual_review_required"
    payload = write_state(
        state_path,
        started_at,
        final_status,
        final_reason,
        task_results,
        current_task=None,
        candidates_found=candidates_found,
    )
    write_latest_summary(latest_summary_path, final_status, final_reason)
    return payload


def stop_file_requested(control_dir: Path) -> bool:
    return (control_dir / "STOP").exists()


def free_disk_gb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return float(usage.free) / (1024.0**3)


def interruptible_idle_sleep(
    seconds: float,
    control_dir: Path,
    poll_sec: float,
    heartbeat: Callable[[float], None],
) -> bool:
    deadline = time.time() + max(0.0, seconds)
    poll = max(0.1, poll_sec)
    while time.time() < deadline:
        if stop_file_requested(control_dir):
            return True
        remaining = max(0.0, deadline - time.time())
        heartbeat(remaining)
        time.sleep(min(poll, remaining))
    return stop_file_requested(control_dir)


def run_continuous_research(
    state_path: Path,
    latest_summary_path: Path,
    log_dir: Path,
    explored_path: Path,
    control_dir: Path,
    force: bool = False,
    planner_batch_size: int = 3,
    target_distinct_candidates: int = 0,
    pause_on_target_distinct: bool = False,
    max_cycles: int = 0,
    max_hours: float = 0.0,
    cycle_sleep_sec: float = 60.0,
    idle_backoff_initial_sec: float = 60.0,
    idle_backoff_max_sec: float = 3600.0,
    idle_poll_sec: float = 30.0,
    max_consecutive_failures: int = 3,
    min_free_disk_gb: float = 2.0,
) -> dict[str, Any]:
    started_at = pd.Timestamp.now(tz="UTC").isoformat()
    control_dir.mkdir(parents=True, exist_ok=True)
    deadline_time = time.time() + max_hours * 3600.0 if max_hours > 0 else None
    deadline_at = pd.Timestamp.fromtimestamp(deadline_time, tz="UTC").isoformat() if deadline_time else None
    previous = read_json(state_path) or {}
    task_results = list(previous.get("task_results", []))
    candidates_found = list(previous.get("candidates_found", []))
    explored = load_explored_fingerprints(explored_path)
    explored.update(legacy_fingerprints_from_results(task_results))
    explored.update(str(row["fingerprint"]) for row in task_results if row.get("fingerprint"))
    drift_history = drift_history_from_explored(explored_path)

    write_latest_summary(latest_summary_path, "running", "v9_auto_research_train_only:continuous_starting")
    consecutive_failures = 0
    cycle_index = int(previous.get("cycle_index") or 0)
    idle_backoff_sec = max(0.0, idle_backoff_initial_sec)
    target_milestone_emitted = False

    while True:
        if stop_file_requested(control_dir):
            reason = "manual_stop_file"
            payload = write_state(
                state_path,
                started_at,
                "paused",
                reason,
                task_results,
                candidates_found=candidates_found,
                mode="continuous",
                cycle_index=cycle_index,
                stop_reason=reason,
                deadline_at=deadline_at,
            )
            write_latest_summary(latest_summary_path, "paused", reason)
            return payload
        if deadline_time is not None and time.time() >= deadline_time:
            reason = "budget_exhausted:max_hours"
            payload = write_state(
                state_path,
                started_at,
                "paused",
                reason,
                task_results,
                candidates_found=candidates_found,
                mode="continuous",
                cycle_index=cycle_index,
                stop_reason=reason,
                deadline_at=deadline_at,
            )
            write_latest_summary(latest_summary_path, "paused", reason)
            return payload
        if free_disk_gb(Path(".")) < min_free_disk_gb:
            reason = "disk_guard"
            payload = write_state(
                state_path,
                started_at,
                "paused",
                reason,
                task_results,
                candidates_found=candidates_found,
                mode="continuous",
                cycle_index=cycle_index,
                stop_reason=reason,
                deadline_at=deadline_at,
            )
            write_latest_summary(latest_summary_path, "paused", reason)
            return payload

        prior_trials = max(cumulative_trials(explored_path), cumulative_trials_from_results(task_results))
        planned = propose_tasks(
            explored,
            planner_batch_size,
            task_results=task_results,
            candidates=candidates_found,
            prior_trials=prior_trials,
        )
        tasks = tuple(research_task_from_planned(task) for task in planned)
        if not tasks:
            reason = "search_space_exhausted_waiting_for_new_plan"
            write_latest_summary(latest_summary_path, "idle", reason)

            def idle_heartbeat(remaining_sec: float) -> None:
                write_state(
                    state_path,
                    started_at,
                    "idle",
                    reason,
                    task_results,
                    active_task={
                        "status": "idle",
                        "backoff_sec": round(idle_backoff_sec, 3),
                        "remaining_sleep_sec": round(remaining_sec, 3),
                    },
                    candidates_found=candidates_found,
                    tasks=tasks,
                    mode="continuous",
                    cycle_index=cycle_index,
                    deadline_at=deadline_at,
                )

            idle_heartbeat(idle_backoff_sec)
            interruptible_idle_sleep(idle_backoff_sec, control_dir, idle_poll_sec, idle_heartbeat)
            if idle_backoff_max_sec > 0:
                idle_backoff_sec = min(idle_backoff_max_sec, max(1.0, idle_backoff_sec * 2.0))
            continue
        validate_train_only_tasks(tasks)
        idle_backoff_sec = max(0.0, idle_backoff_initial_sec)

        write_state(
            state_path,
            started_at,
            "running",
            f"continuous_cycle_start:{cycle_index}",
            task_results,
            candidates_found=candidates_found,
            tasks=tasks,
            mode="continuous",
            cycle_index=cycle_index,
            deadline_at=deadline_at,
        )

        for planned_task, task in zip(planned, tasks):
            reason = f"continuous_train_only:{planned_task.name}"
            write_latest_summary(latest_summary_path, "running", reason)
            write_state(
                state_path,
                started_at,
                "running",
                reason,
                task_results,
                current_task=task.name,
                candidates_found=candidates_found,
                tasks=tasks,
                mode="continuous",
                cycle_index=cycle_index,
                deadline_at=deadline_at,
            )

            def heartbeat(elapsed: float, task_name: str = task.name) -> None:
                write_state(
                    state_path,
                    started_at,
                    "running",
                    reason,
                    task_results,
                    current_task=task_name,
                    active_task={
                        "name": task_name,
                        "status": "running",
                        "elapsed_sec": round(elapsed, 3),
                        "fingerprint": planned_task.fingerprint,
                        **progress_metadata_for_output(task.output_json),
                    },
                    candidates_found=candidates_found,
                    tasks=tasks,
                    mode="continuous",
                    cycle_index=cycle_index,
                    deadline_at=deadline_at,
                )

            result = run_task(task, force=force, log_dir=log_dir, heartbeat=heartbeat)
            result["fingerprint"] = planned_task.fingerprint
            result["planned_task"] = planned_task.record()
            candidate_status = (
                "manual_review_required_data_drift"
                if has_data_drift(drift_history + task_results, result)
                else "manual_review_required"
            )
            task_results.append(result)
            explored.add(planned_task.fingerprint)
            append_explored_record(
                explored_path,
                {
                    "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "fingerprint": planned_task.fingerprint,
                    "task": task.name,
                    "status": result["status"],
                    "output_json": result["output_json"],
                    "output_md": result["output_md"],
                    "returncode": result["returncode"],
                    "train_start": planned_task.train_start,
                    "train_end": planned_task.train_end,
                    "embargo_start": planned_task.embargo_start,
                    "n_configs_tested": result.get("n_configs_tested", 0),
                    "prior_trials": result.get("prior_trials", 0),
                    "effective_trials": result.get("effective_trials", 0),
                    "data_fingerprint": result.get("data_fingerprint", ""),
                },
            )
            if result.get("data_fingerprint"):
                drift_history.append(
                    {
                        "planned_task": {
                            "train_start": planned_task.train_start,
                            "train_end": planned_task.train_end,
                            "embargo_start": planned_task.embargo_start,
                        },
                        "data_fingerprint": str(result["data_fingerprint"]),
                    }
                )

            if result["status"] == "accepted_train_only_candidate_found":
                known_outputs = {str(row.get("output_json")) for row in candidates_found}
                if result["output_json"] not in known_outputs:
                    candidates_found.append(candidate_record(task, result, status=candidate_status))
                    if candidate_status == "manual_review_required_data_drift":
                        write_latest_summary(latest_summary_path, "running", f"data_drift_detected:{task.name}")
            if result["status"] == "failed":
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            if consecutive_failures >= max_consecutive_failures:
                reason = "failure_fuse"
                payload = write_state(
                    state_path,
                    started_at,
                    "paused",
                    reason,
                    task_results,
                    candidates_found=candidates_found,
                    tasks=tasks,
                    mode="continuous",
                    cycle_index=cycle_index,
                    stop_reason=reason,
                    deadline_at=deadline_at,
                )
                write_latest_summary(latest_summary_path, "paused", reason)
                return payload

            distinct = distinct_candidate_count(candidates_found)
            if target_distinct_candidates > 0 and distinct >= target_distinct_candidates:
                reason = f"distinct_target_reached_manual_review:{distinct}"
                if pause_on_target_distinct:
                    payload = write_state(
                        state_path,
                        started_at,
                        "paused",
                        reason,
                        task_results,
                        candidates_found=candidates_found,
                        tasks=tasks,
                        mode="continuous",
                        cycle_index=cycle_index,
                        stop_reason=reason,
                        deadline_at=deadline_at,
                    )
                    write_latest_summary(latest_summary_path, "paused", reason)
                    return payload
                if not target_milestone_emitted:
                    target_milestone_emitted = True
                    write_state(
                        state_path,
                        started_at,
                        "running",
                        f"milestone:{reason}",
                        task_results,
                        candidates_found=candidates_found,
                        tasks=tasks,
                        mode="continuous",
                        cycle_index=cycle_index,
                        deadline_at=deadline_at,
                    )
                    write_latest_summary(latest_summary_path, "running", f"milestone:{reason}")

            if stop_file_requested(control_dir):
                reason = "manual_stop_file"
                payload = write_state(
                    state_path,
                    started_at,
                    "paused",
                    reason,
                    task_results,
                    candidates_found=candidates_found,
                    tasks=tasks,
                    mode="continuous",
                    cycle_index=cycle_index,
                    stop_reason=reason,
                    deadline_at=deadline_at,
                )
                write_latest_summary(latest_summary_path, "paused", reason)
                return payload

        cycle_index += 1
        if max_cycles > 0 and cycle_index >= max_cycles:
            reason = "budget_exhausted:max_cycles"
            payload = write_state(
                state_path,
                started_at,
                "paused",
                reason,
                task_results,
                candidates_found=candidates_found,
                mode="continuous",
                cycle_index=cycle_index,
                stop_reason=reason,
                deadline_at=deadline_at,
            )
            write_latest_summary(latest_summary_path, "paused", reason)
            return payload
        time.sleep(max(0.0, cycle_sleep_sec))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Safe train-only v9 automatic research runner")
    ap.add_argument("--state", default="state/v9_auto_research_state.json")
    ap.add_argument("--latest-summary", default="state/latest_strategy_summary.txt")
    ap.add_argument("--log-dir", default="logs/v9_auto_research")
    ap.add_argument("--explored", default="state/v9_auto_research_explored.jsonl")
    ap.add_argument("--control-dir", default="control")
    ap.add_argument("--mode", choices=("oneshot", "continuous"), default="oneshot")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--continue-after-candidate", action="store_true")
    ap.add_argument("--planner-batch-size", type=int, default=3)
    ap.add_argument("--target-distinct-candidates", type=int, default=0, help="0 means milestone tracking only; no progress-based stop")
    ap.add_argument("--pause-on-target-distinct", action="store_true")
    ap.add_argument("--max-cycles", type=int, default=0, help="0 means no explicit cycle limit")
    ap.add_argument("--max-hours", type=float, default=0.0, help="0 means no explicit time limit")
    ap.add_argument("--cycle-sleep-sec", type=float, default=60.0)
    ap.add_argument("--idle-backoff-initial-sec", type=float, default=60.0)
    ap.add_argument("--idle-backoff-max-sec", type=float, default=3600.0)
    ap.add_argument("--idle-poll-sec", type=float, default=30.0)
    ap.add_argument("--max-consecutive-failures", type=int, default=3)
    ap.add_argument("--min-free-disk-gb", type=float, default=2.0)
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.mode == "continuous":
        payload = run_continuous_research(
            state_path=Path(args.state),
            latest_summary_path=Path(args.latest_summary),
            log_dir=Path(args.log_dir),
            explored_path=Path(args.explored),
            control_dir=Path(args.control_dir),
            force=args.force,
            planner_batch_size=args.planner_batch_size,
            target_distinct_candidates=args.target_distinct_candidates,
            pause_on_target_distinct=args.pause_on_target_distinct,
            max_cycles=args.max_cycles,
            max_hours=args.max_hours,
            cycle_sleep_sec=args.cycle_sleep_sec,
            idle_backoff_initial_sec=args.idle_backoff_initial_sec,
            idle_backoff_max_sec=args.idle_backoff_max_sec,
            idle_poll_sec=args.idle_poll_sec,
            max_consecutive_failures=args.max_consecutive_failures,
            min_free_disk_gb=args.min_free_disk_gb,
        )
    else:
        payload = run_auto_research(
            state_path=Path(args.state),
            latest_summary_path=Path(args.latest_summary),
            log_dir=Path(args.log_dir),
            force=args.force,
            continue_after_candidate=args.continue_after_candidate,
        )
    print(
        "v9_auto_research done "
        f"status={payload['status']} reason={payload['reason']} "
        f"tasks={len(payload['task_results'])}"
    )
    print(args.state)


if __name__ == "__main__":
    main()
