from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from v9.contract.auto_research import task_result_status, trial_metadata  # noqa: E402
from v9.contract.xsec_ohlcv_factory import RunConfig, read_data_snapshot, snapshot_metadata_path  # noqa: E402


STATE_KIND = "v9_revalidation_runner_state_v1"
DEFAULT_PROGRESS_HEARTBEAT_SEC = 15 * 60


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def group_plan_fingerprint(group: dict[str, Any]) -> str:
    config_json = Path(str(group.get("config_json") or ""))
    payload = {
        "group_id": group.get("group_id"),
        "module": group.get("module"),
        "preset": group.get("preset"),
        "train_start": group.get("train_start"),
        "train_end": group.get("train_end"),
        "embargo_start": group.get("embargo_start"),
        "data_snapshot_fingerprint": group.get("data_snapshot_fingerprint"),
        "command": group.get("command") or [],
        "config_json_sha1": file_sha1(config_json) if config_json.exists() else "",
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def completion_metadata_path(output_json: str) -> Path:
    path = Path(output_json)
    return path.with_suffix(path.suffix + ".revalidation.json")


def progress_path_for(output_json: str) -> Path:
    return Path(output_json).with_suffix(".progress.jsonl")


def lock_path_for(fingerprint: str, lock_dir: Path) -> Path:
    return lock_dir / f"{fingerprint}.lock"


def already_completed(group: dict[str, Any], fingerprint: str) -> bool:
    output_json = str(group.get("output_json") or "")
    if not output_json or not Path(output_json).exists():
        return False
    metadata = read_json(completion_metadata_path(output_json))
    return (
        metadata.get("kind") == "v9_revalidation_group_completion_v1"
        and metadata.get("group_plan_fingerprint") == fingerprint
        and metadata.get("returncode") == 0
    )


def pid_alive(pid: int | str | None) -> bool:
    try:
        pid_int = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    try:
        os.kill(pid_int, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def latest_running_row(runner_state_path: Path, fingerprint: str) -> dict[str, Any]:
    state = load_runner_state(runner_state_path)
    for row in reversed(state.get("runs") or []):
        if row.get("group_plan_fingerprint") == fingerprint and row.get("status") == "running":
            return dict(row)
    return {}


def mark_running_row_stale(runner_state_path: Path, fingerprint: str, row: dict[str, Any]) -> dict[str, Any]:
    stale_row = {
        **row,
        "status": "stale_running",
        "stale_marked_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    replace_runner_state_row(runner_state_path, fingerprint, stale_row)
    return stale_row


def fresh_progress_metadata(output_json: str, heartbeat_sec: int = DEFAULT_PROGRESS_HEARTBEAT_SEC) -> dict[str, Any]:
    progress_path = progress_path_for(output_json)
    if not progress_path.exists():
        return {"fresh": False, "progress_path": str(progress_path)}
    try:
        age_sec = max(0.0, time.time() - progress_path.stat().st_mtime)
    except OSError:
        return {"fresh": False, "progress_path": str(progress_path)}
    return {
        "fresh": age_sec <= heartbeat_sec,
        "progress_path": str(progress_path),
        "progress_age_sec": round(age_sec, 3),
        "heartbeat_sec": int(heartbeat_sec),
    }


def acquire_group_lock(lock_path: Path, fingerprint: str) -> tuple[bool, dict[str, Any]]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "v9_revalidation_group_lock_v1",
        "group_plan_fingerprint": fingerprint,
        "owner_pid": os.getpid(),
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = read_json(lock_path)
        owner_pid = existing.get("owner_pid")
        if owner_pid and not pid_alive(owner_pid):
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            return acquire_group_lock(lock_path, fingerprint)
        return (
            False,
            {
                "reason": "lock_exists",
                "lock_path": str(lock_path),
                "owner_pid": owner_pid,
            },
        )
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return True, {"lock_path": str(lock_path), "owner_pid": payload["owner_pid"]}


def release_group_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def verify_snapshot(group: dict[str, Any]) -> dict[str, Any]:
    snapshot_path = Path(str(group.get("data_snapshot_path") or ""))
    expected_fingerprint = str(group.get("data_snapshot_fingerprint") or "")
    if not snapshot_path.exists():
        return {"ok": False, "reason": "snapshot_missing", "data_snapshot_path": str(snapshot_path)}
    metadata_path = snapshot_metadata_path(snapshot_path)
    if not metadata_path.exists():
        return {"ok": False, "reason": "snapshot_metadata_missing", "data_snapshot_path": str(snapshot_path)}
    metadata = read_json(metadata_path)
    metadata_fingerprint = str(metadata.get("fingerprint") or "")
    if metadata_fingerprint != expected_fingerprint:
        return {
            "ok": False,
            "reason": "snapshot_fingerprint_mismatch",
            "data_snapshot_path": str(snapshot_path),
            "expected_fingerprint": expected_fingerprint,
            "metadata_fingerprint": metadata_fingerprint,
        }
    cfg = RunConfig(
        symbols=tuple(str(symbol) for symbol in (group.get("symbols") or [])),
        train_start=str(group.get("train_start") or ""),
        train_end=str(group.get("train_end") or ""),
        embargo_start=str(group.get("embargo_start") or ""),
    )
    try:
        _, verified_metadata = read_data_snapshot(snapshot_path, cfg)
    except Exception as exc:
        return {
            "ok": False,
            "reason": "snapshot_file_read_failed",
            "data_snapshot_path": str(snapshot_path),
            "error": str(exc),
        }
    verified_fingerprint = str(verified_metadata.get("fingerprint") or "")
    if verified_fingerprint != expected_fingerprint:
        return {
            "ok": False,
            "reason": "snapshot_file_fingerprint_mismatch",
            "data_snapshot_path": str(snapshot_path),
            "expected_fingerprint": expected_fingerprint,
            "verified_fingerprint": verified_fingerprint,
        }
    return {
        "ok": True,
        "data_snapshot_path": str(snapshot_path),
        "data_snapshot_fingerprint": expected_fingerprint,
    }


def candidate_groups(plan: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [dict(group) for group in plan.get("groups") or [] if group.get("data_snapshot_path")]
    return sorted(groups, key=lambda group: (-int(group.get("config_count") or 0), str(group.get("group_id") or "")))


def load_runner_state(path: Path) -> dict[str, Any]:
    state = read_json(path)
    if not state:
        return {"kind": STATE_KIND, "runs": []}
    state.setdefault("kind", STATE_KIND)
    state.setdefault("runs", [])
    return state


def runner_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "run_count": len(runs),
        "running_count": sum(1 for run in runs if run.get("status") == "running"),
        "dry_run_count": sum(1 for run in runs if run.get("status") == "dry_run"),
        "completed_count": sum(1 for run in runs if run.get("returncode") == 0),
        "failed_count": sum(1 for run in runs if run.get("returncode") not in (None, 0)),
        "snapshot_verification_failed_count": sum(
            1 for run in runs if run.get("status") == "snapshot_verification_failed"
        ),
        "skipped_existing_count": sum(1 for run in runs if run.get("status") == "skipped_existing"),
        "skipped_running_count": sum(1 for run in runs if run.get("status") == "skipped_running"),
        "skipped_locked_count": sum(1 for run in runs if run.get("status") == "skipped_locked"),
        "skipped_fresh_progress_count": sum(
            1 for run in runs if run.get("status") == "skipped_fresh_progress"
        ),
        "stale_running_count": sum(1 for run in runs if run.get("status") == "stale_running"),
    }


def append_runner_state(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    state = load_runner_state(path)
    state["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    state["runs"].append(row)
    runs = state["runs"]
    state["summary"] = runner_summary(runs)
    write_json(path, state)
    return state


def replace_runner_state_row(path: Path, fingerprint: str, row: dict[str, Any]) -> dict[str, Any]:
    state = load_runner_state(path)
    runs = list(state.get("runs") or [])
    for idx in range(len(runs) - 1, -1, -1):
        if runs[idx].get("group_plan_fingerprint") == fingerprint and runs[idx].get("status") == "running":
            runs[idx] = row
            break
    else:
        runs.append(row)
    state["runs"] = runs
    state["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    state["summary"] = runner_summary(runs)
    write_json(path, state)
    return state


def run_group(
    group: dict[str, Any],
    *,
    runner_state_path: Path,
    log_dir: Path,
    lock_dir: Path | None = None,
    dry_run: bool = False,
    timeout_sec: int = 6 * 60 * 60,
    progress_heartbeat_sec: int = DEFAULT_PROGRESS_HEARTBEAT_SEC,
) -> dict[str, Any]:
    fingerprint = group_plan_fingerprint(group)
    started_at = pd.Timestamp.now(tz="UTC").isoformat()
    base = {
        "group_id": group.get("group_id"),
        "module": group.get("module"),
        "preset": group.get("preset"),
        "config_count": int(group.get("config_count") or 0),
        "output_json": group.get("output_json"),
        "output_md": group.get("output_md"),
        "command": list(group.get("command") or []),
        "group_plan_fingerprint": fingerprint,
        "started_at": started_at,
    }
    if already_completed(group, fingerprint):
        row = {**base, "status": "skipped_existing", "returncode": 0, "completed_at": started_at}
        append_runner_state(runner_state_path, row)
        return row

    if not dry_run:
        running = latest_running_row(runner_state_path, fingerprint)
        if running:
            if pid_alive(running.get("child_pid")):
                row = {
                    **base,
                    "status": "skipped_running",
                    "returncode": None,
                    "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "running_child_pid": running.get("child_pid"),
                    "running_log": running.get("log"),
                }
                append_runner_state(runner_state_path, row)
                return row
            mark_running_row_stale(runner_state_path, fingerprint, running)

        progress = fresh_progress_metadata(
            str(group.get("output_json") or ""),
            heartbeat_sec=progress_heartbeat_sec,
        )
        if progress.get("fresh"):
            row = {
                **base,
                "status": "skipped_fresh_progress",
                "returncode": None,
                "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "progress_guard": progress,
            }
            append_runner_state(runner_state_path, row)
            return row

    snapshot_check = verify_snapshot(group)
    if not snapshot_check.get("ok"):
        row = {
            **base,
            "status": "snapshot_verification_failed",
            "returncode": None,
            "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "snapshot_check": snapshot_check,
        }
        append_runner_state(runner_state_path, row)
        return row

    if dry_run:
        row = {
            **base,
            "status": "dry_run",
            "returncode": None,
            "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "snapshot_check": snapshot_check,
        }
        append_runner_state(runner_state_path, row)
        return row

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"revalidate_{group.get('group_id')}_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}.log"
    resolved_lock_dir = lock_dir or runner_state_path.parent / "locks"
    lock_path = lock_path_for(fingerprint, resolved_lock_dir)
    acquired, lock_info = acquire_group_lock(lock_path, fingerprint)
    if not acquired:
        row = {
            **base,
            "status": "skipped_locked",
            "returncode": None,
            "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "lock": lock_info,
        }
        append_runner_state(runner_state_path, row)
        return row
    started = time.time()
    try:
        with log_path.open("w") as log:
            proc = subprocess.Popen(list(group.get("command") or []), stdout=log, stderr=subprocess.STDOUT, text=True)
            append_runner_state(
                runner_state_path,
                {
                    **base,
                    "status": "running",
                    "returncode": None,
                    "child_pid": proc.pid,
                    "log": str(log_path),
                    "lock": lock_info,
                    "snapshot_check": snapshot_check,
                },
            )
            try:
                returncode = proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
                returncode = 124
        elapsed_sec = round(time.time() - started, 3)
        output_payload = read_json(Path(str(group.get("output_json") or "")))
        status = task_result_status(output_payload) if returncode == 0 and output_payload else "failed"
        row = {
            **base,
            "status": status,
            "returncode": returncode,
            "elapsed_sec": elapsed_sec,
            "completed_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "log": str(log_path),
            "lock": lock_info,
            "snapshot_check": snapshot_check,
            **trial_metadata(output_payload),
        }
        if returncode == 0 and output_payload:
            write_json(
                completion_metadata_path(str(group.get("output_json"))),
                {
                    "kind": "v9_revalidation_group_completion_v1",
                    "group_id": group.get("group_id"),
                    "group_plan_fingerprint": fingerprint,
                    "returncode": returncode,
                    "status": status,
                    "completed_at": row["completed_at"],
                },
            )
        replace_runner_state_row(runner_state_path, fingerprint, row)
        return row
    finally:
        release_group_lock(lock_path)


def run_plan(
    plan_path: Path,
    *,
    runner_state_path: Path,
    log_dir: Path,
    max_groups: int,
    lock_dir: Path | None = None,
    dry_run: bool = False,
    timeout_sec: int = 6 * 60 * 60,
    progress_heartbeat_sec: int = DEFAULT_PROGRESS_HEARTBEAT_SEC,
) -> dict[str, Any]:
    plan = read_json(plan_path)
    groups = candidate_groups(plan)
    if max_groups > 0:
        groups = groups[:max_groups]
    rows = [
        run_group(
            group,
            runner_state_path=runner_state_path,
            log_dir=log_dir,
            lock_dir=lock_dir,
            dry_run=dry_run,
            timeout_sec=timeout_sec,
            progress_heartbeat_sec=progress_heartbeat_sec,
        )
        for group in groups
    ]
    return {
        "kind": "v9_revalidation_runner_report_v1",
        "plan": str(plan_path),
        "runner_state": str(runner_state_path),
        "selected_group_count": len(groups),
        "dry_run": bool(dry_run),
        "rows": rows,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"kind={report['kind']}",
        f"selected_groups={report['selected_group_count']} dry_run={report['dry_run']}",
        f"runner_state={report['runner_state']}",
    ]
    for row in report.get("rows") or []:
        lines.append(
            f"group={row.get('group_id')} status={row.get('status')} returncode={row.get('returncode')} "
            f"configs={row.get('config_count')} output={row.get('output_json')}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pinned train-only revalidation groups from a v9 plan")
    parser.add_argument("--plan", default="artifacts/v9/revalidation/v9_candidate_revalidation_plan.json")
    parser.add_argument("--runner-state", default="artifacts/v9/revalidation/runner_state.json")
    parser.add_argument("--log-dir", default="logs/v9_revalidation")
    parser.add_argument("--lock-dir", default="")
    parser.add_argument("--max-groups", type=int, default=1)
    parser.add_argument("--timeout-sec", type=int, default=6 * 60 * 60)
    parser.add_argument("--progress-heartbeat-sec", type=int, default=DEFAULT_PROGRESS_HEARTBEAT_SEC)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = run_plan(
        Path(args.plan),
        runner_state_path=Path(args.runner_state),
        log_dir=Path(args.log_dir),
        lock_dir=Path(args.lock_dir) if args.lock_dir else None,
        max_groups=int(args.max_groups),
        dry_run=bool(args.dry_run),
        timeout_sec=int(args.timeout_sec),
        progress_heartbeat_sec=int(args.progress_heartbeat_sec),
    )
    if args.out_json:
        write_json(Path(args.out_json), report)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
