#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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


def completed_r(record: dict[str, Any]) -> float | None:
    outcome = record.get("outcome") or {}
    value = outcome.get("r_multiple", record.get("completed_r_multiple"))
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def record_time_key(record: dict[str, Any]) -> str:
    outcome = record.get("outcome") or {}
    return str(outcome.get("exit_dt") or record.get("exit_dt") or record.get("created_at") or "")


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return float(worst)


def trailing_losses(values: list[float]) -> int:
    count = 0
    for value in reversed(values):
        if value < 0.0:
            count += 1
        else:
            break
    return count


def active_pair_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.get("status") not in {"pending_entry", "open"}:
            continue
        symbol = str(record.get("symbol", "")).upper()
        side = str(record.get("side", "")).lower()
        if not symbol or side not in {"long", "short"}:
            continue
        key = f"{symbol}:{side}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def active_unrealized_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    active = [record for record in records if record.get("status") in {"pending_entry", "open"}]
    values = [value for record in active if (value := optional_float(record.get("current_r_multiple"))) is not None]
    total = float(sum(values))
    known = len(values)
    wins = sum(1 for value in values if value > 0.0)
    losses = sum(1 for value in values if value < 0.0)
    return {
        "active": len(active),
        "active_r_known": known,
        "active_profit": wins,
        "active_loss": losses,
        "active_loss_rate": float(losses / known) if known else 0.0,
        "active_sum_r": total,
        "active_avg_r": float(total / known) if known else 0.0,
        "active_min_r": min(values) if values else None,
        "active_max_r": max(values) if values else None,
    }


def build_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = sorted(
        [record for record in records if record.get("status") == "completed"],
        key=record_time_key,
    )
    values = [value for record in completed if (value := completed_r(record)) is not None]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = float("inf") if gross_loss == 0.0 and gross_profit > 0.0 else gross_profit / gross_loss if gross_loss else 0.0
    return {
        "completed": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(values)) if values else 0.0,
        "sum_r": float(sum(values)),
        "avg_r": (float(sum(values)) / len(values)) if values else 0.0,
        "profit_factor": float(profit_factor),
        "max_drawdown_r": max_drawdown(values),
        "trailing_losses": trailing_losses(values),
        "best_r": max(values) if values else None,
        "worst_r": min(values) if values else None,
        **active_unrealized_stats(records),
    }


def active_risk_reasons(stats: dict[str, Any], args: argparse.Namespace) -> list[str]:
    if int(stats.get("active_r_known") or 0) < int(args.active_risk_min_known):
        return []

    reasons: list[str] = []
    active_sum_r = safe_float(stats.get("active_sum_r"))
    active_avg_r = safe_float(stats.get("active_avg_r"))
    active_loss_rate = safe_float(stats.get("active_loss_rate"))
    max_sum_r = float(args.active_risk_max_sum_r)
    max_loss_rate = float(args.active_risk_max_loss_rate)
    max_avg_r = float(args.active_risk_max_avg_r)
    if active_sum_r <= max_sum_r:
        reasons.append(f"active_unrealized_sum_r<={max_sum_r:.2f}")
    if active_loss_rate >= max_loss_rate and active_avg_r <= max_avg_r:
        reasons.append(f"active_unrealized_loss_rate>={max_loss_rate:.2f}_avg_r<={max_avg_r:.2f}")
    return reasons


def decide(stats: dict[str, Any], args: argparse.Namespace) -> tuple[str, list[str]]:
    reasons: list[str] = []
    completed = int(stats["completed"])
    if completed < int(args.min_completed):
        return "collecting", [f"completed<{int(args.min_completed)}"]

    if safe_float(stats["sum_r"]) <= float(args.fail_sum_r):
        reasons.append(f"sum_r<={float(args.fail_sum_r):g}")
    if safe_float(stats["profit_factor"]) < float(args.fail_profit_factor):
        reasons.append(f"profit_factor<{float(args.fail_profit_factor):g}")
    if int(stats["trailing_losses"]) >= int(args.fail_consecutive_losses):
        reasons.append(f"trailing_losses>={int(args.fail_consecutive_losses)}")
    if reasons:
        return "failed", reasons

    active_reasons = active_risk_reasons(stats, args)
    if active_reasons:
        return "watch_active_risk", active_reasons

    promote_reasons = [
        completed >= int(args.promote_min_completed),
        safe_float(stats["sum_r"]) >= float(args.promote_sum_r),
        safe_float(stats["profit_factor"]) >= float(args.promote_profit_factor),
        safe_float(stats["max_drawdown_r"]) <= float(args.promote_max_drawdown_r),
    ]
    if all(promote_reasons):
        return "promote_candidate", [
            f"completed>={int(args.promote_min_completed)}",
            f"sum_r>={float(args.promote_sum_r):g}",
            f"profit_factor>={float(args.promote_profit_factor):g}",
            f"max_drawdown_r<={float(args.promote_max_drawdown_r):g}",
        ]
    return "watch", ["not_failed_not_promoted"]


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    report_path = Path(args.report_json)
    report = json.loads(report_path.read_text())
    records = list(report.get("records") or [])
    stats = build_stats(records)
    status, reasons = decide(stats, args)
    active_counts = active_pair_counts(records)
    active_overlap = {
        pair: count
        for pair, count in sorted(active_counts.items())
        if count > int(args.max_active_per_pair)
    }
    return {
        "kind": "contract_canary_guard_v1",
        "updated_at": now_utc(),
        "report_json": str(report_path),
        "report_updated_at": report.get("updated_at"),
        "status": status,
        "reason_codes": reasons,
        "stats": stats,
        "active_pair_counts": active_counts,
        "active_overlap_violations": active_overlap,
        "thresholds": {
            "min_completed": int(args.min_completed),
            "fail_sum_r": float(args.fail_sum_r),
            "fail_profit_factor": float(args.fail_profit_factor),
            "fail_consecutive_losses": int(args.fail_consecutive_losses),
            "promote_min_completed": int(args.promote_min_completed),
            "promote_sum_r": float(args.promote_sum_r),
            "promote_profit_factor": float(args.promote_profit_factor),
            "promote_max_drawdown_r": float(args.promote_max_drawdown_r),
            "max_active_per_pair": int(args.max_active_per_pair),
            "active_risk_min_known": int(args.active_risk_min_known),
            "active_risk_max_sum_r": float(args.active_risk_max_sum_r),
            "active_risk_max_loss_rate": float(args.active_risk_max_loss_rate),
            "active_risk_max_avg_r": float(args.active_risk_max_avg_r),
        },
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def fmt_num(value: Any, digits: int = 3) -> str:
    if value is None:
        return ""
    number = safe_float(value, float("nan"))
    if math.isnan(number):
        return ""
    if math.isinf(number):
        return "inf"
    return f"{number:.{digits}f}"


def format_markdown(payload: dict[str, Any]) -> str:
    stats = payload["stats"]
    thresholds = payload["thresholds"]
    lines = [
        "# Contract Canary Guard",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- report_updated_at: `{payload.get('report_updated_at')}`",
        f"- status: `{payload['status']}`",
        f"- reasons: `{', '.join(payload['reason_codes'])}`",
        "",
        "## Stats",
        "",
        "| completed | wins | losses | win_rate | sum_R | avg_R | profit_factor | max_DD_R | trailing_losses | active | active_R | active_w/l |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {stats['completed']} | {stats['wins']} | {stats['losses']} | "
            f"{fmt_num(stats['win_rate'])} | {fmt_num(stats['sum_r'])} | {fmt_num(stats['avg_r'])} | "
            f"{fmt_num(stats['profit_factor'])} | {fmt_num(stats['max_drawdown_r'])} | "
            f"{stats['trailing_losses']} | {stats['active']} | {fmt_num(stats['active_sum_r'])} | "
            f"{stats['active_profit']}/{stats['active_loss']} |"
        ),
        "",
        "## Thresholds",
        "",
        (
            f"- fail if completed >= `{thresholds['min_completed']}` and any of: "
            f"sum_R <= `{thresholds['fail_sum_r']}`, "
            f"profit_factor < `{thresholds['fail_profit_factor']}`, "
            f"trailing_losses >= `{thresholds['fail_consecutive_losses']}`"
        ),
        (
            f"- promote if completed >= `{thresholds['promote_min_completed']}`, "
            f"sum_R >= `{thresholds['promote_sum_r']}`, "
            f"profit_factor >= `{thresholds['promote_profit_factor']}`, "
            f"max_DD_R <= `{thresholds['promote_max_drawdown_r']}`"
        ),
        (
            f"- hold promotion if active known >= `{thresholds['active_risk_min_known']}` and any of: "
            f"active_R <= `{thresholds['active_risk_max_sum_r']}`, "
            f"active loss rate >= `{thresholds['active_risk_max_loss_rate']}` "
            f"with avg_R <= `{thresholds['active_risk_max_avg_r']}`"
        ),
        "",
        "## Active Overlap",
        "",
    ]
    violations = payload.get("active_overlap_violations") or {}
    if violations:
        for pair, count in violations.items():
            lines.append(f"- `{pair}` active={count}")
    else:
        lines.append("- none")
    lines.extend(["", "Paper-only guard. No live trading is authorized."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    stats = payload["stats"]
    return (
        f"updated_at={payload['updated_at']}\n"
        f"status={payload['status']} reasons={','.join(payload['reason_codes'])}\n"
        f"completed={stats['completed']} wins={stats['wins']} losses={stats['losses']} "
        f"sum_R={fmt_num(stats['sum_r'])} avg_R={fmt_num(stats['avg_r'])} "
        f"pf={fmt_num(stats['profit_factor'])} max_dd_R={fmt_num(stats['max_drawdown_r'])} "
        f"trailing_losses={stats['trailing_losses']} "
        f"active={stats['active']} active_R={fmt_num(stats['active_sum_r'])} "
        f"active_wl={stats['active_profit']}/{stats['active_loss']}\n"
        "safety=paper_authorized:False live:False"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate paper-only contract canary health and promotion gates.")
    parser.add_argument("--report-json", default="artifacts/v9/contract_lab/contract_edge_canary_report_latest.json")
    parser.add_argument("--out-json", default="state/contract_canary_guard_state.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_canary_guard_latest.md")
    parser.add_argument("--min-completed", type=int, default=20)
    parser.add_argument("--fail-sum-r", type=float, default=-5.0)
    parser.add_argument("--fail-profit-factor", type=float, default=0.8)
    parser.add_argument("--fail-consecutive-losses", type=int, default=6)
    parser.add_argument("--promote-min-completed", type=int, default=30)
    parser.add_argument("--promote-sum-r", type=float, default=5.0)
    parser.add_argument("--promote-profit-factor", type=float, default=1.2)
    parser.add_argument("--promote-max-drawdown-r", type=float, default=5.0)
    parser.add_argument("--max-active-per-pair", type=int, default=1)
    parser.add_argument("--active-risk-min-known", type=int, default=3)
    parser.add_argument("--active-risk-max-sum-r", type=float, default=-2.0)
    parser.add_argument("--active-risk-max-loss-rate", type=float, default=0.67)
    parser.add_argument("--active-risk-max-avg-r", type=float, default=-0.25)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = build_payload(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
