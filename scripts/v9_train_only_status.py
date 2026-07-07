#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.open())


def progress_summary(root: Path, current_task: str, active_task: dict[str, Any]) -> dict[str, Any]:
    base = root / "artifacts" / "v9" / "contract_lab" / current_task
    progress_path = Path(str(base) + ".progress.jsonl")
    progress_meta_path = Path(str(base) + ".progress.meta.json")
    progress_meta = read_json(progress_meta_path) or {}
    rows = int(active_task.get("progress_rows") or count_lines(progress_path))
    total = int(active_task.get("progress_total_rows") or progress_meta.get("total_rows") or 0)
    pct = float(active_task.get("progress_pct") or (rows / total if total > 0 else 0.0))
    return {
        "progress_exists": progress_path.exists(),
        "progress_path": str(progress_path.relative_to(root)) if progress_path.exists() else None,
        "progress_rows": rows,
        "progress_total_rows": total,
        "progress_pct": round(min(1.0, pct), 6) if total > 0 else 0.0,
        "progress_bytes": int(progress_path.stat().st_size) if progress_path.exists() else 0,
        "progress_cache_version": active_task.get("progress_cache_version") or progress_meta.get("cache_version"),
    }


def artifact_summary(root: Path, current_task: str) -> dict[str, Any]:
    base = root / "artifacts" / "v9" / "contract_lab" / current_task
    out: dict[str, Any] = {}
    for label, suffix in (("json", ".json"), ("md", ".md")):
        path = Path(str(base) + suffix)
        out[f"{label}_exists"] = path.exists()
        out[f"{label}_bytes"] = int(path.stat().st_size) if path.exists() else 0
        out[f"{label}_path"] = str(path.relative_to(root)) if path.exists() else None
    return out


def build_status(root: Path) -> dict[str, Any]:
    state_path = root / "state" / "v9_auto_research_state.json"
    state = read_json(state_path) or {}
    current_task = str(state.get("current_task") or "")
    active_task = state.get("active_task") or {}
    latest_summary_path = root / "state" / "latest_strategy_summary.txt"
    status = {
        "state_exists": state_path.exists(),
        "updated_at": state.get("updated_at"),
        "mode": state.get("mode"),
        "status": state.get("status"),
        "reason": state.get("reason"),
        "stop_reason": state.get("stop_reason"),
        "cycle_index": state.get("cycle_index"),
        "current_task": current_task,
        "active_task_status": active_task.get("status"),
        "active_task_elapsed_sec": active_task.get("elapsed_sec"),
        "tasks_done_total": state.get("tasks_done_total", 0),
        "candidates_found_total": state.get("candidates_found_total", 0),
        "distinct_candidates": state.get("distinct_candidates", 0),
        "holdout_authorized": bool(state.get("holdout_authorized")),
        "paper_trading_authorized": bool(state.get("paper_trading_authorized")),
        "live_trading_authorized": bool(state.get("live_trading_authorized")),
        "latest_summary": latest_summary_path.read_text().strip() if latest_summary_path.exists() else None,
    }
    if current_task:
        status.update(progress_summary(root, current_task, active_task))
        status.update(artifact_summary(root, current_task))
    return status


def format_text(status: dict[str, Any]) -> str:
    progress = ""
    if status.get("progress_total_rows"):
        progress = f" progress={status['progress_rows']}/{status['progress_total_rows']} ({status['progress_pct']:.1%})"
    return (
        f"status={status.get('status')} reason={status.get('reason')}{progress}\n"
        f"task={status.get('current_task')}\n"
        f"candidates={status.get('candidates_found_total')} distinct={status.get('distinct_candidates')}\n"
        "safety="
        f"holdout:{status.get('holdout_authorized')} "
        f"paper:{status.get('paper_trading_authorized')} "
        f"live:{status.get('live_trading_authorized')}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only v9 train-only runner status")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    status = build_status(Path(args.root).resolve())
    if args.format == "json":
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(status))


if __name__ == "__main__":
    main()
