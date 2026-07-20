#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_contract_latest_market_signal import load_symbol_cache, safe_float


DEFAULT_SOURCES = (
    ("1h", "state/contract_latest_market_signal_journal.jsonl"),
    ("15m", "state/contract_latest_market_signal_15m_journal.jsonl"),
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_sources(raw: str) -> tuple[tuple[str, str], ...]:
    if not raw.strip():
        return DEFAULT_SOURCES
    out = []
    for item in raw.split(","):
        part = item.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"source must be TIMEFRAME:PATH, got {part!r}")
        timeframe, path = part.split(":", 1)
        out.append((timeframe.strip(), path.strip()))
    return tuple(out or DEFAULT_SOURCES)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_close(cache_dir: Path, symbol: str, timeframe: str, lookback_bars: int) -> dict[str, Any]:
    frame = load_symbol_cache(cache_dir, symbol, timeframe, lookback_bars=lookback_bars)
    if frame.empty:
        return {"latest_close": None, "latest_dt": None}
    row = frame.iloc[-1]
    return {
        "latest_close": safe_float(row.get("close")),
        "latest_dt": row.get("dt").isoformat(),
    }


def current_r_multiple(record: dict[str, Any], latest: float | None) -> float | None:
    if latest is None:
        return None
    side = str(record.get("side"))
    entry = safe_float(record.get("entry_price"), float("nan"))
    stop = safe_float(record.get("stop_loss"))
    if pd.isna(entry):
        return None
    risk = entry - stop if side == "long" else stop - entry
    if risk <= 0:
        return None
    if side == "long":
        return float((latest - entry) / risk)
    if side == "short":
        return float((entry - latest) / risk)
    return None


def current_directional_pct(record: dict[str, Any], latest: float | None) -> float | None:
    if latest is None:
        return None
    side = str(record.get("side"))
    entry = safe_float(record.get("entry_price"), float("nan"))
    if pd.isna(entry) or entry <= 0:
        return None
    raw = latest / entry - 1.0
    return float(raw if side == "long" else -raw)


def optional_float(value: Any) -> float | None:
    number = safe_float(value, float("nan"))
    if pd.isna(number):
        return None
    return float(number)


def enrich_record(
    record: dict[str, Any],
    *,
    timeframe: str,
    cache_dir: Path,
    lookback_bars: int,
    latest_cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(record.get("symbol", "")).upper()
    latest_key = (timeframe, symbol)
    if latest_key not in latest_cache:
        latest_cache[latest_key] = latest_close(cache_dir, symbol, timeframe, lookback_bars)
    latest = latest_cache[latest_key]
    latest_price = latest.get("latest_close")
    outcome = record.get("outcome") or {}
    current_r = current_r_multiple(record, latest_price)
    current_pct = current_directional_pct(record, latest_price)
    filled_entry = optional_float(record.get("entry_price"))
    planned_entry = optional_float(record.get("planned_entry_price"))
    return {
        **record,
        "timeframe": timeframe,
        "latest_close": latest_price,
        "latest_dt": latest.get("latest_dt"),
        "display_entry_price": filled_entry if filled_entry is not None else planned_entry,
        "planned_entry_price": planned_entry,
        "current_r_multiple": current_r,
        "current_directional_pct": current_pct,
        "completed_r_multiple": outcome.get("r_multiple"),
        "completed_gross_r_multiple": outcome.get("gross_r_multiple"),
        "fee_cost_per_unit": outcome.get("fee_cost_per_unit"),
        "funding_cost_per_unit": outcome.get("funding_cost_per_unit"),
        "slippage_bps": outcome.get("slippage_bps") or (record.get("paper_execution") or {}).get("slippage_bps"),
        "exit_reason": outcome.get("exit_reason"),
        "exit_dt": outcome.get("exit_dt"),
        "execution_model": record.get("execution_model_version") or "legacy_v1",
    }


def outcome_label(row: dict[str, Any]) -> str:
    if row.get("status") == "pending_entry":
        return "pending_entry"
    if row.get("status") == "skipped":
        reason = row.get("exit_reason") or (row.get("outcome") or {}).get("exit_reason")
        return f"skipped:{reason}" if reason else "skipped"
    if row.get("status") != "completed":
        value = row.get("current_r_multiple")
        if value is None:
            return "open"
        if value > 0:
            return "open_profit"
        if value < 0:
            return "open_loss"
        return "open_flat"
    value = row.get("completed_r_multiple")
    if value is None:
        return "completed_unknown"
    if float(value) > 0:
        return "win"
    if float(value) < 0:
        return "loss"
    return "flat"


def completed_r(row: dict[str, Any]) -> float | None:
    value = row.get("completed_r_multiple")
    number = safe_float(value, float("nan"))
    if pd.isna(number):
        return None
    return float(number)


def record_time_key(row: dict[str, Any]) -> str:
    return str(row.get("exit_dt") or row.get("updated_at") or row.get("created_at") or "")


def max_drawdown_r(values: list[float]) -> float:
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


def profit_factor(values: list[float]) -> float | None:
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_profit = float(sum(wins))
    gross_loss = float(-sum(losses))
    if gross_loss == 0.0:
        return None if gross_profit > 0.0 else 0.0
    return float(gross_profit / gross_loss)


def compare_profit_factor(value: float | None) -> float:
    return float("inf") if value is None else float(value)


def arg_value(args: argparse.Namespace, name: str, default: Any) -> Any:
    return getattr(args, name, default)


def summarize_values(values: list[float]) -> dict[str, Any]:
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    total = float(sum(values))
    return {
        "completed": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": float(len(wins) / len(values)) if values else 0.0,
        "sum_r": total,
        "avg_r": float(total / len(values)) if values else 0.0,
        "profit_factor": profit_factor(values),
        "max_drawdown_r": max_drawdown_r(values),
        "trailing_losses": trailing_losses(values),
    }


def analog_supported_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    supported = sum(1 for row in rows if row.get("analog_supported"))
    return {
        "analog_supported": supported,
        "analog_supported_rate": float(supported / total) if total else 0.0,
    }


def group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("timeframe") or "").lower(),
        str(row.get("symbol") or "").upper(),
        str(row.get("side") or "").lower(),
    )


def regime_group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("timeframe") or "").lower(),
        str(row.get("market_regime_id") or "unknown"),
        str(row.get("side") or "").lower(),
    )


def decide_group_status(stats: dict[str, Any], args: argparse.Namespace) -> tuple[str, list[str]]:
    min_trades = int(arg_value(args, "scoreboard_min_trades", 20))
    fail_sum_r = float(arg_value(args, "scoreboard_fail_sum_r", -5.0))
    fail_profit_factor = float(arg_value(args, "scoreboard_fail_profit_factor", 0.8))
    fail_consecutive_losses = int(arg_value(args, "scoreboard_fail_consecutive_losses", 6))
    promote_sum_r = float(arg_value(args, "scoreboard_promote_sum_r", 5.0))
    promote_profit_factor = float(arg_value(args, "scoreboard_promote_profit_factor", 1.2))
    promote_max_drawdown_r = float(arg_value(args, "scoreboard_promote_max_drawdown_r", 5.0))

    if int(stats["recent_completed"]) < min_trades:
        return "collecting", [f"recent_completed<{min_trades}"]

    reasons: list[str] = []
    recent_pf = compare_profit_factor(stats.get("recent_profit_factor"))
    if safe_float(stats.get("recent_sum_r")) <= fail_sum_r:
        reasons.append(f"recent_sum_r<={fail_sum_r:g}")
    if recent_pf < fail_profit_factor:
        reasons.append(f"recent_profit_factor<{fail_profit_factor:g}")
    if int(stats.get("recent_trailing_losses") or 0) >= fail_consecutive_losses:
        reasons.append(f"recent_trailing_losses>={fail_consecutive_losses}")
    if reasons:
        return "stop_candidate", reasons

    if (
        safe_float(stats.get("recent_sum_r")) >= promote_sum_r
        and recent_pf >= promote_profit_factor
        and safe_float(stats.get("recent_max_drawdown_r")) <= promote_max_drawdown_r
    ):
        return "promote_candidate", [
            f"recent_sum_r>={promote_sum_r:g}",
            f"recent_profit_factor>={promote_profit_factor:g}",
            f"recent_max_drawdown_r<={promote_max_drawdown_r:g}",
        ]
    return "watch", ["not_failed_not_promoted"]


def build_scoreboard(
    completed_rows: list[dict[str, Any]],
    active_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    active_counts: dict[tuple[str, str, str], int] = {}
    for row in completed_rows:
        value = completed_r(row)
        if value is None:
            continue
        grouped.setdefault(group_key(row), []).append(row)
    for row in active_rows:
        key = group_key(row)
        active_counts[key] = active_counts.get(key, 0) + 1

    rows = []
    recent_n = int(arg_value(args, "scoreboard_recent_trades", 50))
    for key, group in grouped.items():
        timeframe, symbol, side = key
        ordered = sorted(group, key=record_time_key)
        values = [value for row in ordered if (value := completed_r(row)) is not None]
        if not values:
            continue
        recent_rows = ordered[-recent_n:] if recent_n > 0 else ordered
        recent_values = [value for row in recent_rows if (value := completed_r(row)) is not None]
        all_stats = summarize_values(values)
        recent_stats = summarize_values(recent_values)
        all_analog = analog_supported_stats(ordered)
        recent_analog = analog_supported_stats(recent_rows)
        stats = {
            "timeframe": timeframe,
            "symbol": symbol,
            "side": side,
            "completed": all_stats["completed"],
            "wins": all_stats["wins"],
            "losses": all_stats["losses"],
            "win_rate": all_stats["win_rate"],
            "sum_r": all_stats["sum_r"],
            "avg_r": all_stats["avg_r"],
            "profit_factor": all_stats["profit_factor"],
            "max_drawdown_r": all_stats["max_drawdown_r"],
            "trailing_losses": all_stats["trailing_losses"],
            "analog_supported": all_analog["analog_supported"],
            "analog_supported_rate": all_analog["analog_supported_rate"],
            "recent_completed": recent_stats["completed"],
            "recent_wins": recent_stats["wins"],
            "recent_losses": recent_stats["losses"],
            "recent_win_rate": recent_stats["win_rate"],
            "recent_sum_r": recent_stats["sum_r"],
            "recent_avg_r": recent_stats["avg_r"],
            "recent_profit_factor": recent_stats["profit_factor"],
            "recent_max_drawdown_r": recent_stats["max_drawdown_r"],
            "recent_trailing_losses": recent_stats["trailing_losses"],
            "recent_analog_supported": recent_analog["analog_supported"],
            "recent_analog_supported_rate": recent_analog["analog_supported_rate"],
            "active": active_counts.get(key, 0),
            "latest_completed_at": record_time_key(ordered[-1]),
        }
        status, reasons = decide_group_status(stats, args)
        edge_score = (
            safe_float(stats["recent_sum_r"])
            - safe_float(stats["recent_max_drawdown_r"])
            - 0.25 * float(stats["recent_trailing_losses"])
        )
        rows.append({**stats, "status": status, "reason_codes": reasons, "edge_score": float(edge_score)})

    priority = {"promote_candidate": 0, "watch": 1, "collecting": 2, "stop_candidate": 3}
    rows.sort(
        key=lambda row: (
            priority.get(str(row.get("status")), 9),
            -safe_float(row.get("edge_score")),
            -int(row.get("recent_completed") or 0),
            str(row.get("timeframe")),
            str(row.get("symbol")),
            str(row.get("side")),
        )
    )
    return rows


def build_regime_scoreboard(completed_rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in completed_rows:
        value = completed_r(row)
        if value is None:
            continue
        grouped.setdefault(regime_group_key(row), []).append(row)

    rows = []
    recent_n = int(arg_value(args, "scoreboard_recent_trades", 50))
    for key, group in grouped.items():
        timeframe, regime_id, side = key
        ordered = sorted(group, key=record_time_key)
        values = [value for row in ordered if (value := completed_r(row)) is not None]
        if not values:
            continue
        recent_values = values[-recent_n:] if recent_n > 0 else values
        all_stats = summarize_values(values)
        recent_stats = summarize_values(recent_values)
        edge_score = (
            safe_float(recent_stats["sum_r"])
            - safe_float(recent_stats["max_drawdown_r"])
            - 0.25 * float(recent_stats["trailing_losses"])
        )
        rows.append(
            {
                "timeframe": timeframe,
                "market_regime_id": regime_id,
                "side": side,
                "completed": all_stats["completed"],
                "wins": all_stats["wins"],
                "losses": all_stats["losses"],
                "win_rate": all_stats["win_rate"],
                "sum_r": all_stats["sum_r"],
                "profit_factor": all_stats["profit_factor"],
                "max_drawdown_r": all_stats["max_drawdown_r"],
                "trailing_losses": all_stats["trailing_losses"],
                "recent_completed": recent_stats["completed"],
                "recent_win_rate": recent_stats["win_rate"],
                "recent_sum_r": recent_stats["sum_r"],
                "recent_profit_factor": recent_stats["profit_factor"],
                "recent_max_drawdown_r": recent_stats["max_drawdown_r"],
                "recent_trailing_losses": recent_stats["trailing_losses"],
                "edge_score": float(edge_score),
                "latest_completed_at": record_time_key(ordered[-1]),
            }
        )
    rows.sort(
        key=lambda row: (
            -safe_float(row.get("edge_score")),
            -int(row.get("recent_completed") or 0),
            str(row.get("timeframe")),
            str(row.get("market_regime_id")),
            str(row.get("side")),
        )
    )
    return rows


def compact_scoreboard_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeframe": row.get("timeframe"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "status": row.get("status"),
        "reason_codes": row.get("reason_codes") or [],
        "recent_completed": row.get("recent_completed"),
        "recent_win_rate": row.get("recent_win_rate"),
        "recent_sum_r": row.get("recent_sum_r"),
        "recent_profit_factor": row.get("recent_profit_factor"),
        "recent_max_drawdown_r": row.get("recent_max_drawdown_r"),
        "recent_trailing_losses": row.get("recent_trailing_losses"),
        "recent_analog_supported": row.get("recent_analog_supported"),
        "recent_analog_supported_rate": row.get("recent_analog_supported_rate"),
        "completed": row.get("completed"),
        "sum_r": row.get("sum_r"),
        "profit_factor": row.get("profit_factor"),
        "analog_supported": row.get("analog_supported"),
        "analog_supported_rate": row.get("analog_supported_rate"),
        "active": row.get("active"),
        "edge_score": row.get("edge_score"),
        "latest_completed_at": row.get("latest_completed_at"),
    }


def fresh_analog_veto_reasons(row: dict[str, Any], args: argparse.Namespace) -> list[str]:
    min_trades = int(arg_value(args, "fresh_veto_min_trades", 3))
    if int(row.get("recent_completed") or 0) < min_trades:
        return []
    reasons = []
    veto_sum_r = float(arg_value(args, "fresh_veto_sum_r", -2.0))
    veto_profit_factor = float(arg_value(args, "fresh_veto_profit_factor", 0.5))
    veto_trailing_losses = int(arg_value(args, "fresh_veto_trailing_losses", 3))
    if safe_float(row.get("recent_sum_r")) <= veto_sum_r:
        reasons.append(f"fresh_veto_recent_sum_r<={veto_sum_r:g}")
    if compare_profit_factor(row.get("recent_profit_factor")) < veto_profit_factor:
        reasons.append(f"fresh_veto_recent_profit_factor<{veto_profit_factor:g}")
    if int(row.get("recent_trailing_losses") or 0) >= veto_trailing_losses:
        reasons.append(f"fresh_veto_recent_trailing_losses>={veto_trailing_losses}")
    return reasons


def build_action_plan(scoreboard: list[dict[str, Any]], *, updated_at: str, args: argparse.Namespace) -> dict[str, Any]:
    max_rows = int(arg_value(args, "actions_max_rows", 80))
    blocked = [compact_scoreboard_row(row) for row in scoreboard if row.get("status") == "stop_candidate"]
    promote = [compact_scoreboard_row(row) for row in scoreboard if row.get("status") == "promote_candidate"]
    watch = [
        compact_scoreboard_row(row)
        for row in scoreboard
        if row.get("status") in {"watch", "collecting"} and safe_float(row.get("recent_sum_r")) > 0.0
    ]
    fresh_veto = []
    for row in scoreboard:
        reasons = fresh_analog_veto_reasons(row, args)
        if reasons:
            compact = compact_scoreboard_row(row)
            compact["fresh_veto_reason_codes"] = reasons
            fresh_veto.append(compact)
    return {
        "kind": "contract_paper_strategy_actions_v1",
        "updated_at": updated_at,
        "blocked_pairs": blocked[:max_rows],
        "fresh_analog_veto_pairs": fresh_veto[:max_rows],
        "promote_candidates": promote[:max_rows],
        "positive_watchlist": watch[:max_rows],
        "summary": {
            "blocked_pairs": len(blocked),
            "fresh_analog_veto_pairs": len(fresh_veto),
            "promote_candidates": len(promote),
            "positive_watchlist": len(watch),
        },
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def fmt_num(value: Any, digits: int = 6) -> str:
    if value is None:
        return ""
    number = safe_float(value, float("nan"))
    if pd.isna(number):
        return ""
    if abs(number) >= 100:
        return f"{number:.2f}"
    if abs(number) >= 1:
        return f"{number:.4f}"
    return f"{number:.{digits}f}"


def fmt_pct(value: Any) -> str:
    if value is None:
        return ""
    return f"{safe_float(value) * 100:.2f}%"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    sources = parse_sources(args.sources)
    updated_at = now_utc()
    latest_cache: dict[tuple[str, str], dict[str, Any]] = {}
    records = []
    source_summaries = []
    for timeframe, journal_path in sources:
        path = Path(journal_path)
        raw_rows = read_jsonl(path)
        source_summaries.append(
            {
                "timeframe": timeframe,
                "journal_path": str(path),
                "record_count": len(raw_rows),
            }
        )
        for record in raw_rows:
            records.append(
                enrich_record(
                    record,
                    timeframe=timeframe,
                    cache_dir=Path(args.cache_dir),
                    lookback_bars=args.lookback_bars,
                    latest_cache=latest_cache,
                )
            )
    records.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    active_rows = [row for row in records if row.get("status") in {"pending_entry", "open"}]
    pending_rows = [row for row in records if row.get("status") == "pending_entry"]
    open_rows = [row for row in records if row.get("status") == "open"]
    completed_rows = [row for row in records if row.get("status") == "completed"]
    skipped_rows = [row for row in records if row.get("status") == "skipped"]
    wins = [row for row in completed_rows if safe_float(row.get("completed_r_multiple")) > 0]
    losses = [row for row in completed_rows if safe_float(row.get("completed_r_multiple")) < 0]
    scoreboard = build_scoreboard(completed_rows, active_rows, args)
    regime_scoreboard = build_regime_scoreboard(completed_rows, args)
    actions = build_action_plan(scoreboard, updated_at=updated_at, args=args)
    payload = {
        "kind": "contract_paper_signal_report_v1",
        "updated_at": updated_at,
        "cache_dir": args.cache_dir,
        "sources": source_summaries,
        "summary": {
            "records": len(records),
            "open": len(open_rows),
            "pending_entry": len(pending_rows),
            "active": len(active_rows),
            "completed": len(completed_rows),
            "skipped": len(skipped_rows),
            "wins": len(wins),
            "losses": len(losses),
            "analog_supported_open": sum(1 for row in active_rows if row.get("analog_supported")),
            "scoreboard_groups": len(scoreboard),
            "regime_scoreboard_groups": len(regime_scoreboard),
            "promote_candidates": sum(1 for row in scoreboard if row.get("status") == "promote_candidate"),
            "stop_candidates": sum(1 for row in scoreboard if row.get("status") == "stop_candidate"),
            "blocked_pairs": len(actions["blocked_pairs"]),
            "fresh_analog_veto_pairs": len(actions["fresh_analog_veto_pairs"]),
            "positive_watchlist": len(actions["positive_watchlist"]),
        },
        "actions": actions,
        "scoreboard": scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "regime_scoreboard": regime_scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "open": active_rows[: args.max_rows],
        "completed": completed_rows[: args.max_rows],
        "skipped": skipped_rows[: args.max_rows],
        "records": records,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    return payload


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Contract Paper Signal Report",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- records: `{summary['records']}`",
        f"- active/open/pending: `{summary['active']}/{summary['open']}/{summary['pending_entry']}`",
        f"- completed: `{summary['completed']}`",
        f"- skipped: `{summary['skipped']}`",
        f"- wins/losses: `{summary['wins']}/{summary['losses']}`",
        f"- analog_supported_open: `{summary['analog_supported_open']}`",
        (
            f"- scoreboard groups/promote/stop: "
            f"`{summary['scoreboard_groups']}/{summary['promote_candidates']}/{summary['stop_candidates']}`"
        ),
        f"- regime_scoreboard_groups: `{summary['regime_scoreboard_groups']}`",
        f"- actions blocked/fresh_veto/positive_watch: "
        f"`{summary['blocked_pairs']}/{summary['fresh_analog_veto_pairs']}/{summary['positive_watchlist']}`",
        "",
        "## Regime Scoreboard",
        "",
        "| timeframe | regime | side | recent_n | recent_win | recent_sum_R | recent_pf | recent_DD_R | trailing_loss | all_sum_R | score |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["regime_scoreboard"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('market_regime_id')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {fmt_num(row.get('edge_score'), 3)} |"
        )
    lines.extend(
        [
        "",
        "## Strategy Scoreboard",
        "",
        "| status | timeframe | symbol | side | recent_n | analog_n | analog_rate | recent_win | recent_sum_R | "
        "recent_pf | recent_DD_R | recent_trailing_loss | all_sum_R | active | score | reasons |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["scoreboard"]:
        lines.append(
            f"| {row.get('status')} | {row.get('timeframe')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {row.get('recent_analog_supported')} | "
            f"{fmt_pct(row.get('recent_analog_supported_rate'))} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {row.get('active')} | {fmt_num(row.get('edge_score'), 3)} | "
            f"{', '.join(row.get('reason_codes') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Active Paper Signals",
            "",
            "| timeframe | created_at | symbol | side | model | analog | planned_entry | fill_entry | latest | stop | "
            "take_profit | current_R | current_% | status |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["open"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('created_at')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('execution_model')} | {row.get('analog_supported')} | "
            f"{fmt_num(row.get('planned_entry_price'))} | {fmt_num(row.get('entry_price'))} | "
            f"{fmt_num(row.get('latest_close'))} | "
            f"{fmt_num(row.get('stop_loss'))} | {fmt_num(row.get('take_profit'))} | "
            f"{fmt_num(row.get('current_r_multiple'), 3)} | {fmt_pct(row.get('current_directional_pct'))} | "
            f"{outcome_label(row)} |"
        )
    lines.extend(
        [
            "",
            "## Completed Paper Signals",
            "",
            "| timeframe | created_at | symbol | side | model | analog | entry | stop | "
            "take_profit | exit_reason | net_R | gross_R | fees | funding | result |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["completed"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('created_at')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('execution_model')} | {row.get('analog_supported')} | "
            f"{fmt_num(row.get('entry_price'))} | {fmt_num(row.get('stop_loss'))} | "
            f"{fmt_num(row.get('take_profit'))} | {row.get('exit_reason')} | "
            f"{fmt_num(row.get('completed_r_multiple'), 3)} | "
            f"{fmt_num(row.get('completed_gross_r_multiple'), 3)} | "
            f"{fmt_num(row.get('fee_cost_per_unit'))} | {fmt_num(row.get('funding_cost_per_unit'))} | "
            f"{outcome_label(row)} |"
        )
    lines.extend(
        [
            "",
            "## Skipped Paper Signals",
            "",
            "| timeframe | created_at | symbol | side | model | planned_entry | reason |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in payload["skipped"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('created_at')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('execution_model')} | {fmt_num(row.get('planned_entry_price'))} | {outcome_label(row)} |"
        )
    lines.extend(["", "Paper report only. No live trading is authorized."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"updated_at={payload['updated_at']}",
        f"records={summary['records']} active={summary['active']} open={summary['open']} "
        f"pending={summary['pending_entry']} completed={summary['completed']} skipped={summary['skipped']}",
        f"wins={summary['wins']} losses={summary['losses']} analog_supported_active={summary['analog_supported_open']}",
        (
            f"scoreboard_groups={summary['scoreboard_groups']} "
            f"regime_groups={summary['regime_scoreboard_groups']} "
            f"promote={summary['promote_candidates']} stop={summary['stop_candidates']}"
        ),
        f"actions_blocked={summary['blocked_pairs']} fresh_veto={summary['fresh_analog_veto_pairs']} "
        f"positive_watch={summary['positive_watchlist']}",
        "safety=paper_authorized:False live:False",
    ]
    for row in payload["regime_scoreboard"][:5]:
        lines.append(
            f"regime {row.get('timeframe')} {row.get('market_regime_id')} {row.get('side')} "
            f"recent_n={row.get('recent_completed')} recent_sum_R={fmt_num(row.get('recent_sum_r'), 3)} "
            f"recent_pf={fmt_num(row.get('recent_profit_factor'), 3)} "
            f"recent_dd_R={fmt_num(row.get('recent_max_drawdown_r'), 3)} "
            f"score={fmt_num(row.get('edge_score'), 3)}"
        )
    for row in payload["scoreboard"][:10]:
        lines.append(
            f"scoreboard {row.get('status')} {row.get('timeframe')} {row.get('symbol')} {row.get('side')} "
            f"recent_n={row.get('recent_completed')} recent_sum_R={fmt_num(row.get('recent_sum_r'), 3)} "
            f"recent_pf={fmt_num(row.get('recent_profit_factor'), 3)} "
            f"recent_analog={row.get('recent_analog_supported')}/{fmt_pct(row.get('recent_analog_supported_rate'))} "
            f"recent_dd_R={fmt_num(row.get('recent_max_drawdown_r'), 3)} "
            f"active={row.get('active')} score={fmt_num(row.get('edge_score'), 3)}"
        )
    for row in payload["open"][:10]:
        lines.append(
            f"{row.get('timeframe')} {row.get('symbol')} {row.get('side')} "
            f"model={row.get('execution_model')} status={row.get('status')} "
            f"planned={fmt_num(row.get('planned_entry_price'))} entry={fmt_num(row.get('entry_price'))} "
            f"latest={fmt_num(row.get('latest_close'))} "
            f"stop={fmt_num(row.get('stop_loss'))} tp={fmt_num(row.get('take_profit'))} "
            f"R={fmt_num(row.get('current_r_multiple'), 3)} result={outcome_label(row)}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a readable report for paper-only contract market signals.")
    parser.add_argument("--cache-dir", default="data/binance_usdm_ohlcv_cache")
    parser.add_argument("--sources", default="")
    parser.add_argument("--lookback-bars", type=int, default=200)
    parser.add_argument("--max-rows", type=int, default=80)
    parser.add_argument("--scoreboard-max-rows", type=int, default=40)
    parser.add_argument("--scoreboard-min-trades", type=int, default=20)
    parser.add_argument("--scoreboard-recent-trades", type=int, default=50)
    parser.add_argument("--scoreboard-fail-sum-r", type=float, default=-5.0)
    parser.add_argument("--scoreboard-fail-profit-factor", type=float, default=0.8)
    parser.add_argument("--scoreboard-fail-consecutive-losses", type=int, default=6)
    parser.add_argument("--scoreboard-promote-sum-r", type=float, default=5.0)
    parser.add_argument("--scoreboard-promote-profit-factor", type=float, default=1.2)
    parser.add_argument("--scoreboard-promote-max-drawdown-r", type=float, default=5.0)
    parser.add_argument("--fresh-veto-min-trades", type=int, default=3)
    parser.add_argument("--fresh-veto-sum-r", type=float, default=-2.0)
    parser.add_argument("--fresh-veto-profit-factor", type=float, default=0.5)
    parser.add_argument("--fresh-veto-trailing-losses", type=int, default=3)
    parser.add_argument("--actions-max-rows", type=int, default=80)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_paper_signal_report_latest.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_paper_signal_report_latest.md")
    parser.add_argument("--out-actions-json", default="")
    parser.add_argument("--out-blocked-pairs-json", default="")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = build_report(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    if args.out_actions_json:
        write_json(payload["actions"], Path(args.out_actions_json))
    if args.out_blocked_pairs_json:
        write_json(
            {
                "kind": "contract_paper_blocked_pairs_v1",
                "updated_at": payload["updated_at"],
                "blocked_pairs": payload["actions"]["blocked_pairs"],
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            },
            Path(args.out_blocked_pairs_json),
        )
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
