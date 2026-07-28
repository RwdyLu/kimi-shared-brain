#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_revalidation_runner import (  # noqa: E402
    candidate_groups,
    completion_metadata_path,
    group_plan_fingerprint,
)
from v9.contract.auto_research import task_result_status, trial_metadata  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def progress_metadata(output_json: str) -> dict[str, Any]:
    progress_path = Path(output_json).with_suffix(".progress.jsonl")
    progress_meta_path = Path(output_json).with_suffix(".progress.meta.json")
    now = time.time()
    out: dict[str, Any] = {
        "progress_exists": progress_path.exists(),
        "progress_path": str(progress_path),
        "progress_rows": 0,
        "progress_bytes": 0,
    }
    if not progress_path.exists():
        return out
    try:
        out["progress_rows"] = sum(1 for _ in progress_path.open())
        out["progress_bytes"] = progress_path.stat().st_size
        progress_mtime = progress_path.stat().st_mtime
        out["progress_updated_at"] = datetime.fromtimestamp(progress_mtime, tz=timezone.utc).isoformat()
        out["progress_age_sec"] = round(max(0.0, now - progress_mtime), 3)
    except OSError:
        return out
    meta = read_json(progress_meta_path)
    if meta:
        out["progress_meta_path"] = str(progress_meta_path)
        total = int(meta.get("total_rows") or 0)
        if total > 0:
            out["progress_total_rows"] = total
            out["progress_pct"] = round(min(1.0, int(out["progress_rows"]) / total), 6)
        if meta.get("cache_version"):
            out["progress_cache_version"] = str(meta["cache_version"])
        try:
            meta_mtime = progress_meta_path.stat().st_mtime
            out["progress_meta_updated_at"] = datetime.fromtimestamp(meta_mtime, tz=timezone.utc).isoformat()
            out["progress_meta_age_sec"] = round(max(0.0, now - meta_mtime), 3)
        except OSError:
            pass
    return out


def process_lines() -> list[str]:
    try:
        raw = subprocess.check_output(
            ["ps", "-eo", "pid,etime,pcpu,pmem,cmd"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return raw.splitlines()


def process_for_output(output_json: str, lines: list[str]) -> dict[str, Any]:
    if not output_json:
        return {"process_running": False}
    for line in lines:
        if output_json in line and "grep" not in line:
            parts = line.split(maxsplit=4)
            return {
                "process_running": True,
                "process_pid": parts[0] if parts else "",
                "process_etime": parts[1] if len(parts) > 1 else "",
                "process_pcpu": parts[2] if len(parts) > 2 else "",
                "process_pmem": parts[3] if len(parts) > 3 else "",
                "process_cmd": parts[4] if len(parts) > 4 else line,
            }
    return {"process_running": False}


def latest_runner_row(runner_state: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    for row in reversed(runner_state.get("runs") or []):
        if row.get("group_plan_fingerprint") == fingerprint:
            return dict(row)
    return {}


def group_status(
    group: dict[str, Any],
    *,
    runner_state: dict[str, Any],
    process_scan: list[str],
) -> dict[str, Any]:
    output_json = str(group.get("output_json") or "")
    fingerprint = group_plan_fingerprint(group)
    completion = read_json(completion_metadata_path(output_json))
    runner_row = latest_runner_row(runner_state, fingerprint)
    progress = progress_metadata(output_json)
    proc = process_for_output(output_json, process_scan)
    output_payload = read_json(Path(output_json))

    status = "pending"
    returncode = runner_row.get("returncode")
    if completion:
        returncode = completion.get("returncode")
        status = (
            "completed_accepted"
            if completion.get("status") == "accepted_train_only_candidate_found"
            else "completed_no_candidate"
        )
        if returncode not in (None, 0):
            status = "completed_failed"
    elif runner_row.get("status") == "running":
        status = "running"
    elif proc.get("process_running"):
        status = "running_process_detected"
    elif progress.get("progress_exists"):
        status = "progress_without_runner_state"
    elif output_payload:
        status = "output_without_completion_metadata"

    row = {
        "group_id": group.get("group_id"),
        "module": group.get("module"),
        "preset": group.get("preset"),
        "config_count": int(group.get("config_count") or 0),
        "output_json": output_json,
        "group_plan_fingerprint": fingerprint,
        "status": status,
        "runner_status": runner_row.get("status"),
        "returncode": returncode,
        "completion_status": completion.get("status"),
        "output_status": task_result_status(output_payload) if output_payload else None,
        **progress,
        **proc,
    }
    row.update(trial_metadata(output_payload))
    return row


def build_report(
    plan_path: Path,
    *,
    runner_state_path: Path,
    max_groups: int = 10,
    include_processes: bool = False,
    process_scan: list[str] | None = None,
) -> dict[str, Any]:
    plan = read_json(plan_path)
    runner_state = read_json(runner_state_path)
    groups = candidate_groups(plan)
    if max_groups > 0:
        groups = groups[:max_groups]
    scan = list(process_scan if process_scan is not None else (process_lines() if include_processes else []))
    rows = [group_status(group, runner_state=runner_state, process_scan=scan) for group in groups]
    counts = Counter(str(row.get("status")) for row in rows)
    return {
        "kind": "v9_revalidation_status_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": str(plan_path),
        "runner_state": str(runner_state_path),
        "selected_group_count": len(rows),
        "status_counts": dict(counts),
        "include_processes": bool(include_processes),
        "groups": rows,
    }


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"kind={report['kind']}",
        f"selected_groups={report['selected_group_count']} status_counts={json.dumps(report['status_counts'], sort_keys=True)}",
        f"runner_state={report['runner_state']}",
    ]
    for row in report.get("groups") or []:
        progress = ""
        if row.get("progress_exists"):
            progress = (
                f" progress={row.get('progress_rows')}/{row.get('progress_total_rows', '?')}"
                f" pct={row.get('progress_pct')} age_sec={row.get('progress_age_sec')}"
            )
        proc = f" pid={row.get('process_pid')}" if row.get("process_running") else ""
        lines.append(
            f"group={row.get('group_id')} preset={row.get('preset')} status={row.get('status')} "
            f"configs={row.get('config_count')}{progress}{proc} output={row.get('output_json')}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report pinned revalidation group status without mutating state")
    parser.add_argument("--plan", default="artifacts/v9/revalidation/v9_candidate_revalidation_plan.json")
    parser.add_argument("--runner-state", default="artifacts/v9/revalidation/runner_state.json")
    parser.add_argument("--max-groups", type=int, default=10)
    parser.add_argument("--include-processes", action="store_true")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = build_report(
        Path(args.plan),
        runner_state_path=Path(args.runner_state),
        max_groups=int(args.max_groups),
        include_processes=bool(args.include_processes),
    )
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
