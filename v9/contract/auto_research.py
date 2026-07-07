from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .report import write_json


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
) -> dict[str, Any]:
    payload = {
        "created_at": started_at,
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "v9_auto_research_train_only_state",
        "status": status,
        "reason": reason,
        "current_task": current_task,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "tasks": [asdict(task) for task in DEFAULT_TASKS],
        "task_results": task_results,
        "candidates_found": candidates_found or [],
    }
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
) -> dict[str, Any]:
    payload = state_payload(started_at, status, reason, task_results, current_task, active_task, candidates_found)
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
                active_task={"name": task_name, "status": "running", "elapsed_sec": round(elapsed, 3)},
                candidates_found=candidates_found,
            )

        result = run_task(task, force=force, log_dir=log_dir, heartbeat=heartbeat)
        task_results.append(result)
        if result["status"] == "accepted_train_only_candidate_found":
            candidates_found.append(
                {
                    "task": task.name,
                    "output_json": result["output_json"],
                    "output_md": result["output_md"],
                    "status": "manual_review_required",
                }
            )
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


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Safe train-only v9 automatic research runner")
    ap.add_argument("--state", default="state/v9_auto_research_state.json")
    ap.add_argument("--latest-summary", default="state/latest_strategy_summary.txt")
    ap.add_argument("--log-dir", default="logs/v9_auto_research")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--continue-after-candidate", action="store_true")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
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
