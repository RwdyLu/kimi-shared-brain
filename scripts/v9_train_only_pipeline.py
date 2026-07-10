#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_train_only_candidate_triage import first_number  # noqa: E402
from v9.research.family_registry import (  # noqa: E402
    family_fingerprint,
    load_registry,
    normalized_family_payload,
    queue_allowed,
    read_json,
    upsert_family,
    write_json,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(path: str | Path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base / p


def write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def accepted_train_metric(payload: dict[str, Any]) -> float | None:
    rows = payload.get("top") or payload.get("rows") or []
    for row in rows:
        if not isinstance(row, dict) or not row.get("advance_passed"):
            continue
        selection = row.get("selection") or {}
        cost40 = selection.get("cost40") or row.get("cost40") or {}
        cost20 = selection.get("cost20") or row.get("cost20") or {}
        return first_number(cost40.get("sharpe"), cost20.get("sharpe"))
    return None


def existing_queue_families(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("family_fingerprint"):
            out.add(str(row["family_fingerprint"]))
    return out


def append_queue(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def scan_candidates(
    *,
    state: dict[str, Any],
    base: Path,
    registry: dict[str, Any],
    queue_path: Path,
    require_novel: bool,
) -> dict[str, Any]:
    queued_families = existing_queue_families(queue_path)
    existing_queue_family_count = len(queued_families)
    processed = []
    latest_by_family: dict[str, dict[str, Any]] = {}
    queue_rows = []
    new_family_count = 0
    duplicate_family_count = 0
    missing_artifact_count = 0
    for candidate in state.get("candidates_found", []):
        output_json = candidate.get("output_json")
        if not output_json:
            continue
        artifact_path = resolve_path(str(output_json), base)
        if not artifact_path.exists():
            missing_artifact_count += 1
            continue
        payload = read_json(artifact_path)
        if not payload:
            missing_artifact_count += 1
            continue
        artifact = str(output_json)
        family = normalized_family_payload(payload, artifact)
        fp = family_fingerprint(payload, artifact)
        entry, created = upsert_family(
            registry,
            fingerprint=fp,
            family=family,
            candidate=candidate,
            artifact=artifact,
            train_metric=accepted_train_metric(payload),
        )
        if created:
            new_family_count += 1
        else:
            duplicate_family_count += 1
        latest_by_family[fp] = {
            "fingerprint": fp,
            "family": family,
            "candidate": dict(candidate),
            "artifact": artifact,
        }
        processed.append(
            {
                "task": candidate.get("task"),
                "artifact": artifact,
                "candidate_status": candidate.get("status"),
                "family_fingerprint": fp,
                "family": family,
                "assignment_reason": "new_family" if created else "matched_existing_family_key",
                "registry_status": entry.get("status"),
                "seen_count": entry.get("seen_count"),
                "created_family": created,
                "queued": False,
            }
        )
    for fp, row in latest_by_family.items():
        entry = (registry.get("families") or {}).get(fp) or {}
        candidate = row["candidate"]
        if fp in queued_families or not queue_allowed(entry, candidate, require_novel=require_novel):
            continue
        queue_row = {
            "kind": "v9_holdout_queue_entry_v1",
            "created_at": now_utc(),
            "family_fingerprint": fp,
            "family": row["family"],
            "task": candidate.get("task"),
            "candidate_status": candidate.get("status"),
            "artifact": row["artifact"],
            "registry_status": entry.get("status"),
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }
        queue_rows.append(queue_row)
        queued_families.add(fp)
        for processed_row in reversed(processed):
            if processed_row.get("family_fingerprint") == fp:
                processed_row["queued"] = True
                break
    append_queue(queue_path, queue_rows)
    total = max(1, len(processed))
    return {
        "processed": processed,
        "queued": queue_rows,
        "summary": {
            "candidate_records_processed": len(processed),
            "missing_artifact_count": missing_artifact_count,
            "new_family_count": new_family_count,
            "duplicate_family_count": duplicate_family_count,
            "queued_count": len(queue_rows),
            "existing_queue_family_count": existing_queue_family_count,
            "total_queue_family_count": len(queued_families),
            "novelty_rate": new_family_count / total,
        },
    }


def run_holdout_batch(args: argparse.Namespace, base: Path) -> dict[str, Any]:
    if not args.holdout_authorized or args.max_holdouts <= 0:
        return {
            "holdout_authorized": False,
            "ran": False,
            "reason": "holdout_not_authorized",
            "suggested_command": (
                "python3 scripts/v9_train_only_holdout_batch.py "
                f"--max-candidates {max(1, int(args.max_holdouts or 1))} --holdout-authorized"
            ),
        }
    cmd = [
        sys.executable,
        "scripts/v9_train_only_holdout_batch.py",
        "--max-candidates",
        str(int(args.max_holdouts)),
        "--holdout-authorized",
        "--format",
        "markdown",
    ]
    proc = subprocess.run(cmd, cwd=base, text=True, capture_output=True, timeout=int(args.holdout_timeout_sec))
    return {
        "holdout_authorized": True,
        "ran": True,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    base = Path(args.base)
    state_path = resolve_path(args.state, base)
    registry_path = resolve_path(args.registry, base)
    queue_path = resolve_path(args.queue, base)
    assignments_path = resolve_path(args.assignments_jsonl, base)
    state = read_json(state_path)
    registry = load_registry(registry_path)
    scan = scan_candidates(
        state=state,
        base=base,
        registry=registry,
        queue_path=queue_path,
        require_novel=not args.queue_known_families,
    )
    write_json(registry, registry_path)
    write_jsonl(scan["processed"], assignments_path)
    holdout = run_holdout_batch(args, base)
    return {
        "kind": "v9_train_only_pipeline_v1",
        "created_at": now_utc(),
        "source_state": str(state_path),
        "registry": str(registry_path),
        "holdout_queue": str(queue_path),
        "family_assignments": str(assignments_path),
        "holdout_accessed": bool(holdout.get("ran")),
        "holdout_authorized": bool(args.holdout_authorized),
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "summary": {
            **scan["summary"],
            "registry_family_count": len(registry.get("families") or {}),
        },
        "queued": scan["queued"],
        "processed_tail": scan["processed"][-50:],
        "holdout": holdout,
        "note": "Train-only pipeline. It queues novel families and never authorizes paper or live trading.",
    }


def format_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# V9 Train-Only Pipeline",
        "",
        f"created_at: `{report.get('created_at')}`",
        f"registry: `{report.get('registry')}`",
        f"holdout_queue: `{report.get('holdout_queue')}`",
        f"family_assignments: `{report.get('family_assignments')}`",
        f"holdout_authorized: `{report.get('holdout_authorized')}`",
        f"paper_trading_authorized: `{report.get('paper_trading_authorized')}`",
        f"live_trading_authorized: `{report.get('live_trading_authorized')}`",
        "",
        "## Summary",
        "",
        f"- candidate_records_processed: `{summary.get('candidate_records_processed')}`",
        f"- registry_family_count: `{summary.get('registry_family_count')}`",
        f"- new_family_count: `{summary.get('new_family_count')}`",
        f"- duplicate_family_count: `{summary.get('duplicate_family_count')}`",
        f"- queued_count: `{summary.get('queued_count')}`",
        f"- existing_queue_family_count: `{summary.get('existing_queue_family_count')}`",
        f"- total_queue_family_count: `{summary.get('total_queue_family_count')}`",
        f"- novelty_rate: `{summary.get('novelty_rate')}`",
        "",
        "## Queued",
        "",
        "| family | status | task | artifact |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("queued") or []:
        lines.append(
            f"| `{row.get('family_fingerprint')}` | `{row.get('candidate_status')}` | "
            f"`{row.get('task')}` | `{row.get('artifact')}` |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This pipeline does not authorize paper or live trading. Holdout runs only with `--holdout-authorized`.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train-only family registry and holdout queue pipeline.")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--base", default=".")
    parser.add_argument("--registry", default="artifacts/v9/registry/family_registry.json")
    parser.add_argument("--queue", default="artifacts/v9/registry/holdout_queue.jsonl")
    parser.add_argument("--assignments-jsonl", default="artifacts/v9/registry/family_assignments_latest.jsonl")
    parser.add_argument("--out-json", default="artifacts/v9/registry/train_only_pipeline_latest.json")
    parser.add_argument("--out-md", default="artifacts/v9/registry/train_only_pipeline_latest.md")
    parser.add_argument("--lock", default="state/v9_train_only_pipeline.lock")
    parser.add_argument("--queue-known-families", action="store_true")
    parser.add_argument("--holdout-authorized", action="store_true")
    parser.add_argument("--max-holdouts", type=int, default=0)
    parser.add_argument("--holdout-timeout-sec", type=int, default=7200)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    base = Path(args.base)
    lock_path = resolve_path(args.lock, base)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("v9_train_only_pipeline already running")
            return
        report = build_report(args)
    out_json = resolve_path(args.out_json, base)
    out_md = resolve_path(args.out_md, base)
    write_json(report, out_json)
    write_text(format_markdown(report), out_md)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_markdown(report))


if __name__ == "__main__":
    main()
