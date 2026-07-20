#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return out or "unknown"


def pair_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("timeframe") or "").lower(),
        str(row.get("symbol") or "").upper(),
        str(row.get("side") or "").lower(),
    )


def row_passes_probe_thresholds(row: dict[str, Any], args: argparse.Namespace) -> bool:
    return (
        safe_int(row.get("recent_completed")) >= int(args.min_probe_completed)
        and safe_int(row.get("recent_analog_supported")) >= int(args.min_probe_analog_supported)
        and safe_float(row.get("recent_analog_supported_rate")) >= float(args.min_probe_analog_supported_rate)
        and safe_float(row.get("recent_sum_r")) >= float(args.min_probe_sum_r)
        and safe_float(row.get("recent_profit_factor")) >= float(args.min_probe_profit_factor)
        and safe_float(row.get("recent_max_drawdown_r")) <= float(args.max_probe_drawdown_r)
        and safe_int(row.get("recent_trailing_losses")) <= int(args.max_probe_trailing_losses)
    )


def candidate_sort_key(row: dict[str, Any]) -> tuple[float, float, int]:
    return (
        safe_float(row.get("edge_score")),
        safe_float(row.get("recent_sum_r")),
        safe_int(row.get("recent_completed")),
    )


def shell_env_command(env: dict[str, str], session: str) -> str:
    parts = [f"{key}={shlex.quote(value)}" for key, value in sorted(env.items())]
    parts.append("scripts/start_contract_edge_canary_watch.sh")
    parts.append(shlex.quote(session))
    return " ".join(parts)


def build_candidate_config(row: dict[str, Any], *, source: str) -> dict[str, Any]:
    timeframe, symbol, side = pair_key(row)
    key = slug(f"{timeframe}_{symbol}_{side}")
    allowed_pair = f"{symbol}:{side}"
    session = f"v9_contract_focus_canary_{key}_watch"
    paths = {
        "update_state_json": f"artifacts/v9/watchdog/contract_focus_canary_{key}_update_status.json",
        "signal_json": f"artifacts/v9/contract_lab/contract_focus_canary_{key}_latest.json",
        "signal_md": f"artifacts/v9/contract_lab/contract_focus_canary_{key}_latest.md",
        "journal_jsonl": f"state/contract_focus_canary_{key}_journal.jsonl",
        "report_json": f"artifacts/v9/contract_lab/contract_focus_canary_{key}_report_latest.json",
        "report_md": f"artifacts/v9/contract_lab/contract_focus_canary_{key}_report_latest.md",
        "guard_json": f"state/contract_focus_canary_{key}_guard_state.json",
        "guard_md": f"artifacts/v9/contract_lab/contract_focus_canary_{key}_guard_latest.md",
        "marker": f"state/FOUND_CONTRACT_FOCUS_CANARY_{key.upper()}_PAPER_PLAN.txt",
        "no_marker": f"state/NO_CONTRACT_FOCUS_CANARY_{key.upper()}_PAPER_PLAN.txt",
        "analog_marker": f"state/FOUND_CONTRACT_FOCUS_CANARY_{key.upper()}_ANALOG_PAPER_PLAN.txt",
        "analog_no_marker": f"state/NO_CONTRACT_FOCUS_CANARY_{key.upper()}_ANALOG_PAPER_PLAN.txt",
    }
    env = {
        "CONTRACT_EDGE_CANARY_TIMEFRAME": timeframe,
        "CONTRACT_EDGE_CANARY_SYMBOLS": symbol,
        "CONTRACT_EDGE_CANARY_ALLOWED_PAIRS": allowed_pair,
        "CONTRACT_EDGE_CANARY_UPDATE_STATE_JSON": paths["update_state_json"],
        "CONTRACT_EDGE_CANARY_SIGNAL_JSON": paths["signal_json"],
        "CONTRACT_EDGE_CANARY_SIGNAL_MD": paths["signal_md"],
        "CONTRACT_EDGE_CANARY_JOURNAL_JSONL": paths["journal_jsonl"],
        "CONTRACT_EDGE_CANARY_REPORT_JSON": paths["report_json"],
        "CONTRACT_EDGE_CANARY_REPORT_MD": paths["report_md"],
        "CONTRACT_EDGE_CANARY_GUARD_JSON": paths["guard_json"],
        "CONTRACT_EDGE_CANARY_GUARD_MD": paths["guard_md"],
        "CONTRACT_EDGE_CANARY_MARKER": paths["marker"],
        "CONTRACT_EDGE_CANARY_NO_MARKER": paths["no_marker"],
        "CONTRACT_EDGE_CANARY_ANALOG_MARKER": paths["analog_marker"],
        "CONTRACT_EDGE_CANARY_ANALOG_NO_MARKER": paths["analog_no_marker"],
        "CONTRACT_EDGE_CANARY_JOURNAL_MAX_ACTIVE_PER_PAIR": "1",
        "CONTRACT_EDGE_CANARY_JOURNAL_RECORD_MODE": "analog_supported",
    }
    return {
        "source": source,
        "timeframe": timeframe,
        "symbol": symbol,
        "side": side,
        "allowed_pair": allowed_pair,
        "session": session,
        "metrics": {
            "recent_completed": safe_int(row.get("recent_completed")),
            "recent_sum_r": safe_float(row.get("recent_sum_r")),
            "recent_profit_factor": safe_float(row.get("recent_profit_factor")),
            "recent_max_drawdown_r": safe_float(row.get("recent_max_drawdown_r")),
            "recent_trailing_losses": safe_int(row.get("recent_trailing_losses")),
            "recent_analog_supported": safe_int(row.get("recent_analog_supported")),
            "recent_analog_supported_rate": safe_float(row.get("recent_analog_supported_rate")),
            "active": safe_int(row.get("active")),
            "edge_score": safe_float(row.get("edge_score")),
        },
        "reason_codes": row.get("reason_codes") or [],
        "paths": paths,
        "env": env,
        "launch_command": shell_env_command(env, session),
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    actions = json.loads(Path(args.actions_json).read_text())
    blocked = {pair_key(row) for row in actions.get("blocked_pairs", [])}
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, str, str]] = set()

    promote_rows = sorted(
        actions.get("promote_candidates", []),
        key=candidate_sort_key,
        reverse=True,
    )
    probe_rows = sorted(
        actions.get("positive_watchlist", []),
        key=candidate_sort_key,
        reverse=True,
    )
    for source, rows in [("promote_candidate", promote_rows), ("positive_watchlist", probe_rows)]:
        for row in rows:
            key = pair_key(row)
            if key in used:
                continue
            if key in blocked and not args.allow_blocked:
                continue
            if source == "positive_watchlist" and not row_passes_probe_thresholds(row, args):
                continue
            selected.append(build_candidate_config(row, source=source))
            used.add(key)
            if len(selected) >= int(args.max_candidates):
                break
        if len(selected) >= int(args.max_candidates):
            break

    return {
        "kind": "contract_focus_canary_plan_v1",
        "updated_at": now_utc(),
        "actions_json": args.actions_json,
        "config": {
            "max_candidates": int(args.max_candidates),
            "min_probe_completed": int(args.min_probe_completed),
            "min_probe_analog_supported": int(args.min_probe_analog_supported),
            "min_probe_analog_supported_rate": float(args.min_probe_analog_supported_rate),
            "min_probe_sum_r": float(args.min_probe_sum_r),
            "min_probe_profit_factor": float(args.min_probe_profit_factor),
            "max_probe_drawdown_r": float(args.max_probe_drawdown_r),
            "max_probe_trailing_losses": int(args.max_probe_trailing_losses),
            "allow_blocked": bool(args.allow_blocked),
        },
        "summary": {
            "selected": len(selected),
            "blocked_pairs": len(blocked),
            "promote_candidates_seen": len(actions.get("promote_candidates", [])),
            "positive_watchlist_seen": len(actions.get("positive_watchlist", [])),
        },
        "candidates": selected,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def fmt_num(value: Any, digits: int = 3) -> str:
    number = safe_float(value, float("nan"))
    if math.isnan(number):
        return ""
    return f"{number:.{digits}f}"


def format_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Contract Focus Canary Plan",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- selected: `{summary['selected']}`",
        f"- seen promote/positive/blocked: "
        f"`{summary['promote_candidates_seen']}/{summary['positive_watchlist_seen']}/{summary['blocked_pairs']}`",
        "",
        "| rank | source | timeframe | symbol | side | recent_n | analog | analog_rate | sum_R | pf | max_DD_R | trailing_loss | session |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(payload["candidates"], start=1):
        metrics = row["metrics"]
        lines.append(
            f"| {idx} | {row['source']} | {row['timeframe']} | {row['symbol']} | {row['side']} | "
            f"{metrics['recent_completed']} | {metrics['recent_analog_supported']} | "
            f"{fmt_num(metrics['recent_analog_supported_rate'])} | {fmt_num(metrics['recent_sum_r'])} | "
            f"{fmt_num(metrics['recent_profit_factor'])} | {fmt_num(metrics['recent_max_drawdown_r'])} | "
            f"{metrics['recent_trailing_losses']} | `{row['session']}` |"
        )
    lines.extend(["", "## Launch Commands", ""])
    for row in payload["candidates"]:
        lines.extend(["```bash", row["launch_command"], "```", ""])
    lines.append("Paper-only focused canary plan. No live trading is authorized.")
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"updated_at={payload['updated_at']}",
        f"selected={summary['selected']} promote_seen={summary['promote_candidates_seen']} "
        f"positive_seen={summary['positive_watchlist_seen']} blocked_seen={summary['blocked_pairs']}",
        "safety=paper_authorized:False live:False",
    ]
    for row in payload["candidates"]:
        metrics = row["metrics"]
        lines.append(
            f"candidate {row['source']} {row['timeframe']} {row['symbol']} {row['side']} "
            f"recent_n={metrics['recent_completed']} sum_R={fmt_num(metrics['recent_sum_r'])} "
            f"pf={fmt_num(metrics['recent_profit_factor'])} max_dd_R={fmt_num(metrics['recent_max_drawdown_r'])} "
            f"analog={metrics['recent_analog_supported']}/{fmt_num(metrics['recent_analog_supported_rate'])} "
            f"trailing_losses={metrics['recent_trailing_losses']} session={row['session']}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build focused contract canary launch plans from paper action scores.")
    parser.add_argument(
        "--actions-json",
        default="artifacts/v9/contract_lab/contract_paper_strategy_actions_latest.json",
    )
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--min-probe-completed", type=int, default=8)
    parser.add_argument("--min-probe-analog-supported", type=int, default=4)
    parser.add_argument("--min-probe-analog-supported-rate", type=float, default=0.50)
    parser.add_argument("--min-probe-sum-r", type=float, default=2.0)
    parser.add_argument("--min-probe-profit-factor", type=float, default=1.2)
    parser.add_argument("--max-probe-drawdown-r", type=float, default=10.0)
    parser.add_argument("--max-probe-trailing-losses", type=int, default=5)
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_focus_canary_plan_latest.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_focus_canary_plan_latest.md")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = build_plan(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
