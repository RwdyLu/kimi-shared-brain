#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


Runner = Callable[..., subprocess.CompletedProcess[str]]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def valid_session_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]+", value)) and not value.startswith("-")


def tmux_has_session(session: str, runner: Runner = subprocess.run) -> bool:
    result = runner(
        ["tmux", "has-session", "-t", f"={session}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


def launch_candidate(candidate: dict[str, Any], args: argparse.Namespace, runner: Runner = subprocess.run) -> dict[str, Any]:
    session = str(candidate.get("session") or "")
    if not valid_session_name(session):
        return {
            "source": candidate.get("source"),
            "session": session,
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "timeframe": candidate.get("timeframe"),
            "status": "invalid_session_name",
            "started": False,
        }
    if tmux_has_session(session, runner=runner):
        return {
            "source": candidate.get("source"),
            "session": session,
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "timeframe": candidate.get("timeframe"),
            "status": "already_running",
            "started": False,
        }
    if not bool(args.launch):
        return {
            "source": candidate.get("source"),
            "session": session,
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "timeframe": candidate.get("timeframe"),
            "status": "dry_run_ready",
            "started": False,
        }

    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in (candidate.get("env") or {}).items()})
    result = runner(
        ["scripts/start_contract_edge_canary_watch.sh", session],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    status = "started" if result.returncode == 0 else "start_failed"
    return {
        "source": candidate.get("source"),
        "session": session,
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "timeframe": candidate.get("timeframe"),
        "status": status,
        "started": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "")[-1000:],
        "stderr_tail": (result.stderr or "")[-1000:],
    }


def arg_value(args: argparse.Namespace, name: str, default: Any) -> Any:
    return getattr(args, name, default)


def launch_rows_from_plan(plan: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    primary = list(plan.get("candidates") or [])[: int(args.max_launches)]
    probe_rows = []
    if bool(arg_value(args, "include_paper_probes", True)):
        probe_rows = list(plan.get("paper_probe_candidates") or [])[: int(arg_value(args, "max_probe_launches", 1))]

    rows = []
    seen_sessions: set[str] = set()
    for row in primary + probe_rows:
        session = str(row.get("session") or "")
        if session in seen_sessions:
            continue
        rows.append(row)
        seen_sessions.add(session)
    return rows


def run_launcher(args: argparse.Namespace, runner: Runner = subprocess.run) -> dict[str, Any]:
    plan = json.loads(Path(args.plan_json).read_text())
    candidates = launch_rows_from_plan(plan, args)
    rows = [launch_candidate(candidate, args, runner=runner) for candidate in candidates]
    return {
        "kind": "contract_focus_canary_launcher_v1",
        "updated_at": now_utc(),
        "plan_json": args.plan_json,
        "launch_enabled": bool(args.launch),
        "summary": {
            "candidates_seen": len(plan.get("candidates") or []),
            "paper_probe_candidates_seen": len(plan.get("paper_probe_candidates") or []),
            "checked": len(rows),
            "started": sum(1 for row in rows if row.get("started")),
            "already_running": sum(1 for row in rows if row.get("status") == "already_running"),
            "failed": sum(1 for row in rows if row.get("status") == "start_failed"),
        },
        "rows": rows,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Contract Focus Canary Launcher",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- launch_enabled: `{payload['launch_enabled']}`",
        f"- candidates/checked/started/running/failed: "
        f"`{summary['candidates_seen']}/{summary['checked']}/{summary['started']}/{summary['already_running']}/{summary['failed']}`",
        f"- paper_probe_candidates_seen: `{summary.get('paper_probe_candidates_seen', 0)}`",
        "",
        "| source | session | timeframe | symbol | side | status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row.get('source')} | `{row.get('session')}` | {row.get('timeframe')} | {row.get('symbol')} | "
            f"{row.get('side')} | {row.get('status')} |"
        )
    lines.append("")
    lines.append("Paper-only launcher. No live trading is authorized.")
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"updated_at={payload['updated_at']}",
        f"launch_enabled={payload['launch_enabled']} candidates={summary['candidates_seen']} "
        f"paper_probes={summary.get('paper_probe_candidates_seen', 0)} "
        f"checked={summary['checked']} started={summary['started']} "
        f"already_running={summary['already_running']} failed={summary['failed']}",
        "safety=paper_authorized:False live:False",
    ]
    for row in payload["rows"]:
        lines.append(
            f"{row.get('status')} {row.get('source')} {row.get('timeframe')} {row.get('symbol')} {row.get('side')} "
            f"session={row.get('session')}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch paper-only focused contract canary sessions from a focus plan.")
    parser.add_argument("--plan-json", default="artifacts/v9/contract_lab/contract_focus_canary_plan_latest.json")
    parser.add_argument("--max-launches", type=int, default=3)
    parser.add_argument("--include-paper-probes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-probe-launches", type=int, default=1)
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_focus_canary_launcher_latest.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_focus_canary_launcher_latest.md")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = run_launcher(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
