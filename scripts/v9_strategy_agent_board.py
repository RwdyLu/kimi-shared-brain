#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return {"_error": "json_decode_error", "path": str(path)}


def file_mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def marker_state(root: Path) -> dict[str, Any]:
    state = root / "state"
    names = {
        "funding_watch_found": "FOUND_FUNDING_PAPER_WATCH.txt",
        "funding_watch_none": "NO_FUNDING_PAPER_WATCH.txt",
        "internal_candidate": "FOUND_INTERNAL_CANDIDATE.txt",
        "validated_candidate": "FOUND_VALIDATED_CANDIDATE.txt",
        "paper_ready": "FOUND_PAPER_READY.txt",
        "live_canary_ready": "FOUND_LIVE_CANARY_READY.txt",
        "production_ready": "FOUND_PRODUCTION_READY.txt",
        "no_validated": "NO_VALIDATED_CANDIDATE.txt",
    }
    out = {}
    for key, name in names.items():
        path = state / name
        text = read_text(path)
        out[key] = {
            "exists": text is not None,
            "text": text,
            "updated_at": file_mtime_iso(path),
        }
    return out


def env_probe(root: Path) -> dict[str, Any]:
    candidates = [
        root / ".env.binance_demo",
        root / ".env.binance",
        root / ".env",
    ]
    present = [str(path.relative_to(root)) for path in candidates if path.exists()]
    return {
        "binance_env_file_present": bool(present),
        "candidate_env_files_present": present,
        "note": "Only file presence is checked; secrets are never read or printed.",
    }


def build_data_auditor(root: Path, funding: dict[str, Any] | None) -> dict[str, Any]:
    checks = {
        "funding_latest_json_present": funding is not None,
        "funding_latest_json_valid": funding is not None and "_error" not in funding,
        "funding_requires_spot": bool((funding or {}).get("require_spot")),
        "funding_loaded_rows_gt_0": int((funding or {}).get("loaded_rows") or 0) > 0,
    }
    status = "ok" if all(checks.values()) else "warn"
    if funding and funding.get("_error"):
        status = "block"
    return {
        "agent": "Data Auditor",
        "status": status,
        "checks": checks,
        "funding_updated_at": (funding or {}).get("updated_at"),
        "funding_data": (funding or {}).get("data"),
        "spot_excluded_symbols": (funding or {}).get("spot_excluded_symbols") or [],
    }


def build_feasibility_agent(funding: dict[str, Any] | None) -> dict[str, Any]:
    summary = (funding or {}).get("summary") or {}
    top = (funding or {}).get("top") or []
    best = top[0] if top else {}
    current = best.get("current_signal") or {}
    config = best.get("config") or {}
    checks = best.get("advance_checks") or {}
    failed = [key for key, value in checks.items() if not bool(value)]
    found = bool(summary.get("paper_watch_candidate_found"))
    status = "watch" if found else "block"
    return {
        "agent": "Strategy Feasibility",
        "status": status,
        "paper_watch_candidate_found": found,
        "paper_watch_candidate_count": int(summary.get("paper_watch_candidate_count") or 0),
        "require_spot": bool((funding or {}).get("require_spot")),
        "spot_excluded_symbols": (funding or {}).get("spot_excluded_symbols") or [],
        "best_candidate": {
            "paper_watch_candidate": bool(best.get("paper_watch_candidate")),
            "config": config,
            "positions": [row.get("symbol") for row in current.get("positions", [])],
            "current_expected_capital_annualized_return": current.get("expected_capital_annualized_return"),
            "failed_checks": failed,
        },
    }


def build_validator_agent(markers: dict[str, Any], auto_state: dict[str, Any] | None) -> dict[str, Any]:
    checks = {
        "validated_candidate_exists": bool(markers["validated_candidate"]["exists"]),
        "paper_ready_exists": bool(markers["paper_ready"]["exists"]),
        "live_canary_ready": bool(markers["live_canary_ready"]["text"] and markers["live_canary_ready"]["text"] != "none"),
        "production_ready": bool(markers["production_ready"]["text"] and markers["production_ready"]["text"] != "none"),
        "auto_research_running": (auto_state or {}).get("status") == "running",
    }
    if checks["paper_ready_exists"]:
        status = "paper_ready"
    elif checks["validated_candidate_exists"]:
        status = "validated_needs_paper_gate"
    elif checks["auto_research_running"]:
        status = "research_running"
    else:
        status = "block"
    return {
        "agent": "Validator",
        "status": status,
        "checks": checks,
        "no_validated_marker": markers["no_validated"]["text"],
        "auto_research": {
            "updated_at": (auto_state or {}).get("updated_at"),
            "cycle_index": (auto_state or {}).get("cycle_index"),
            "tasks_done_total": (auto_state or {}).get("tasks_done_total"),
            "candidates_found_total": (auto_state or {}).get("candidates_found_total"),
            "distinct_candidates": (auto_state or {}).get("distinct_candidates"),
            "current_task": ((auto_state or {}).get("current_task") or {}).get("name")
            if isinstance((auto_state or {}).get("current_task"), dict)
            else (auto_state or {}).get("current_task"),
        },
    }


def build_execution_risk_agent(root: Path, markers: dict[str, Any]) -> dict[str, Any]:
    env = env_probe(root)
    trading_authorized = bool(markers["paper_ready"]["exists"] or markers["live_canary_ready"]["text"] not in {None, "none"})
    checks = {
        "binance_env_file_present": bool(env["binance_env_file_present"]),
        "paper_ready_exists": bool(markers["paper_ready"]["exists"]),
        "live_canary_ready": bool(markers["live_canary_ready"]["text"] and markers["live_canary_ready"]["text"] != "none"),
        "production_ready": bool(markers["production_ready"]["text"] and markers["production_ready"]["text"] != "none"),
        "trading_authorized": trading_authorized,
    }
    return {
        "agent": "Execution & Risk",
        "status": "blocked_no_trade_authorization" if not trading_authorized else "manual_review_required",
        "checks": checks,
        "env_probe": env,
        "risk_policy": {
            "read_only_or_testnet_first": True,
            "live_trading_authorized": False,
            "withdrawal_permission_allowed": False,
            "note": "This board never authorizes live trading by itself.",
        },
    }


def overall_decision(agents: dict[str, Any]) -> dict[str, Any]:
    validator = agents["validator"]
    feasibility = agents["feasibility"]
    execution = agents["execution_risk"]
    if execution["checks"]["production_ready"]:
        decision = "production_marker_present_manual_review_required"
    elif execution["checks"]["live_canary_ready"]:
        decision = "live_canary_marker_present_manual_review_required"
    elif validator["checks"]["paper_ready_exists"]:
        decision = "paper_ready_marker_present_manual_review_required"
    elif feasibility["paper_watch_candidate_found"]:
        decision = "paper_watch_only_not_authorized"
    elif validator["checks"]["auto_research_running"]:
        decision = "research_running_no_trade_candidate"
    else:
        decision = "blocked_no_running_research"
    return {
        "decision": decision,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "next_action": {
            "paper_watch_only_not_authorized": "Keep monitoring; build read-only/testnet execution probe before any trading.",
            "research_running_no_trade_candidate": "Keep research running; wait for a validated or feasible paper-watch candidate.",
            "paper_ready_marker_present_manual_review_required": "Manual paper launch review required before any dry-run.",
            "live_canary_marker_present_manual_review_required": "Manual live-canary review required; do not auto-trade.",
            "production_marker_present_manual_review_required": "Manual production review required; do not auto-trade.",
            "blocked_no_running_research": "Restart research/watch loops before making decisions.",
        }.get(decision, "Manual review required."),
    }


def build_board(root: Path) -> dict[str, Any]:
    markers = marker_state(root)
    funding = read_json(root / "artifacts/v9/contract_lab/funding_delta_neutral_top20_paper_screen_latest.json")
    auto_state = read_json(root / "state/v9_auto_research_state.json")
    agents = {
        "data_auditor": build_data_auditor(root, funding),
        "feasibility": build_feasibility_agent(funding),
        "validator": build_validator_agent(markers, auto_state),
        "execution_risk": build_execution_risk_agent(root, markers),
    }
    return {
        "kind": "v9_strategy_agent_board_v1",
        "updated_at": now_utc(),
        "root": str(root),
        "agents": agents,
        "markers": markers,
        "summary": overall_decision(agents),
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    agents = payload["agents"]
    lines = [
        "# Strategy Agent Board",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- decision: `{summary['decision']}`",
        f"- paper_trading_authorized: `{summary['paper_trading_authorized']}`",
        f"- live_trading_authorized: `{summary['live_trading_authorized']}`",
        f"- next_action: {summary['next_action']}",
        "",
        "| agent | status | key result |",
        "| --- | --- | --- |",
    ]
    lines.append(
        f"| Data Auditor | `{agents['data_auditor']['status']}` | "
        f"funding_rows_gt_0={agents['data_auditor']['checks']['funding_loaded_rows_gt_0']}, "
        f"require_spot={agents['data_auditor']['checks']['funding_requires_spot']} |"
    )
    lines.append(
        f"| Strategy Feasibility | `{agents['feasibility']['status']}` | "
        f"paper_watch={agents['feasibility']['paper_watch_candidate_found']}, "
        f"excluded={','.join(agents['feasibility']['spot_excluded_symbols'])} |"
    )
    lines.append(
        f"| Validator | `{agents['validator']['status']}` | "
        f"cycle={agents['validator']['auto_research'].get('cycle_index')}, "
        f"paper_ready={agents['validator']['checks']['paper_ready_exists']} |"
    )
    lines.append(
        f"| Execution & Risk | `{agents['execution_risk']['status']}` | "
        f"env_present={agents['execution_risk']['checks']['binance_env_file_present']}, "
        f"trading_authorized={agents['execution_risk']['checks']['trading_authorized']} |"
    )
    lines.extend(["", "This board is read-only and never authorizes live trading by itself."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    agents = payload["agents"]
    return "\n".join(
        [
            f"updated_at={payload['updated_at']}",
            f"decision={summary['decision']}",
            f"paper_trading_authorized={summary['paper_trading_authorized']}",
            f"live_trading_authorized={summary['live_trading_authorized']}",
            f"data_auditor={agents['data_auditor']['status']}",
            f"feasibility={agents['feasibility']['status']} paper_watch={agents['feasibility']['paper_watch_candidate_found']}",
            f"validator={agents['validator']['status']} cycle={agents['validator']['auto_research'].get('cycle_index')}",
            f"execution_risk={agents['execution_risk']['status']} env_present={agents['execution_risk']['checks']['binance_env_file_present']}",
            f"next_action={summary['next_action']}",
        ]
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only board that combines v9 strategy agent checks.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-json", default="state/v9_strategy_agent_board.json")
    parser.add_argument("--out-md", default="state/v9_strategy_agent_board.md")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    root = Path(args.root).resolve()
    payload = build_board(root)
    write_json(payload, root / args.out_json)
    (root / args.out_md).parent.mkdir(parents=True, exist_ok=True)
    (root / args.out_md).write_text(format_markdown(payload))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
