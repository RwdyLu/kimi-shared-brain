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

from scripts.v9_contract_latest_market_signal import DECISION_POLICY_VERSION, load_symbol_cache, safe_float


DEFAULT_SOURCES = (
    ("1h", "state/contract_latest_market_signal_journal.jsonl"),
    ("15m", "state/contract_latest_market_signal_15m_journal.jsonl"),
)
DEFAULT_SHADOW_SOURCES = (
    ("1h", "state/contract_latest_market_signal_shadow_journal.jsonl"),
    ("15m", "state/contract_latest_market_signal_15m_shadow_journal.jsonl"),
)
DEFAULT_FAST_SHADOW_SOURCES = (
    ("1h", "state/contract_latest_market_signal_fast_shadow_journal.jsonl"),
    ("15m", "state/contract_latest_market_signal_15m_fast_shadow_journal.jsonl"),
)
LEGACY_DECISION_POLICY_VERSION = "legacy_unknown"


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


def parse_shadow_sources(raw: str) -> tuple[tuple[str, str], ...]:
    if not raw.strip():
        return DEFAULT_SHADOW_SOURCES
    return parse_sources(raw)


def parse_fast_shadow_sources(raw: str) -> tuple[tuple[str, str], ...]:
    if not raw.strip():
        return DEFAULT_FAST_SHADOW_SOURCES
    return parse_sources(raw)


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
        "decision_policy_version": decision_policy_version(record),
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


def decision_policy_version(row: dict[str, Any]) -> str:
    value = row.get("decision_policy_version") or (row.get("paper_execution") or {}).get("decision_policy_version")
    return str(value or LEGACY_DECISION_POLICY_VERSION)


def rows_for_decision_policy(rows: list[dict[str, Any]], policy_version: str) -> list[dict[str, Any]]:
    return [row for row in rows if decision_policy_version(row) == policy_version]


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


def active_unrealized_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for row in rows if (value := optional_float(row.get("current_r_multiple"))) is not None]
    total = float(sum(values))
    return {
        "active_r_known": len(values),
        "active_profit": sum(1 for value in values if value > 0.0),
        "active_loss": sum(1 for value in values if value < 0.0),
        "active_sum_r": total,
        "active_avg_r": float(total / len(values)) if values else 0.0,
        "active_min_r": min(values) if values else None,
        "active_max_r": max(values) if values else None,
    }


def interval_minutes(timeframe: str) -> float | None:
    raw = str(timeframe).strip().lower()
    if len(raw) < 2:
        return None
    try:
        value = float(raw[:-1])
    except ValueError:
        return None
    if value <= 0.0:
        return None
    unit = raw[-1]
    if unit == "s":
        return value / 60.0
    if unit == "m":
        return value
    if unit == "h":
        return value * 60.0
    if unit == "d":
        return value * 1440.0
    return None


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        return pd.Timestamp(value).tz_convert("UTC")
    except TypeError:
        try:
            return pd.Timestamp(value).tz_localize("UTC")
        except Exception:
            return None
    except Exception:
        return None


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * pct))))
    return float(ordered[idx])


def active_drain_item(row: dict[str, Any]) -> dict[str, Any]:
    timeframe = str(row.get("timeframe") or "").lower()
    minutes = interval_minutes(timeframe)
    latest_dt = parse_timestamp(row.get("latest_dt"))
    status = str(row.get("status") or "")
    reference_value = row.get("entry_dt") if status == "open" else row.get("signal_dt") or row.get("created_at")
    reference_dt = parse_timestamp(reference_value)
    horizon_bars = int(row.get("outcome_horizon_bars") or 24)
    config = row.get("paper_execution") or {}
    entry_latency_bars = int(config.get("entry_latency_bars") or 0)
    stale_grace_bars = int(config.get("stale_grace_bars") or 0)
    required_bars = entry_latency_bars if status == "pending_entry" else horizon_bars
    elapsed_bars = None
    age_hours = None
    remaining_bars = None
    remaining_hours = None
    stale_after_bars = required_bars + stale_grace_bars
    past_stale_after = False
    if latest_dt is not None and reference_dt is not None and minutes is not None:
        elapsed_minutes = max(0.0, (latest_dt - reference_dt).total_seconds() / 60.0)
        elapsed_bars = int(elapsed_minutes // minutes)
        age_hours = float(elapsed_minutes / 60.0)
        remaining_bars = max(0, required_bars - elapsed_bars)
        remaining_hours = float(remaining_bars * minutes / 60.0)
        past_stale_after = elapsed_bars >= stale_after_bars
    return {
        "timeframe": timeframe,
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "status": status,
        "latest_dt": latest_dt.isoformat() if latest_dt is not None else None,
        "reference_dt": reference_dt.isoformat() if reference_dt is not None else None,
        "age_hours": age_hours,
        "elapsed_bars": elapsed_bars,
        "required_bars": required_bars,
        "remaining_bars_to_horizon": remaining_bars,
        "remaining_hours_to_horizon": remaining_hours,
        "stale_after_bars": stale_after_bars,
        "past_stale_after": past_stale_after,
    }


def build_portfolio_drain(active_rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    max_active = int(arg_value(args, "portfolio_max_active", 12))
    items = [active_drain_item(row) for row in active_rows]
    known_remaining = [
        value for item in items if (value := optional_float(item.get("remaining_hours_to_horizon"))) is not None
    ]
    known_ages = [value for item in items if (value := optional_float(item.get("age_hours"))) is not None]
    active_excess = max(0, len(active_rows) - max_active) if max_active > 0 else 0
    eta_to_cap = None
    if active_excess > 0 and known_remaining:
        ordered_remaining = sorted(known_remaining)
        if len(ordered_remaining) >= active_excess:
            eta_to_cap = float(ordered_remaining[active_excess - 1])
    by_timeframe: dict[str, Any] = {}
    for timeframe in sorted({str(item.get("timeframe") or "") for item in items}):
        group = [item for item in items if item.get("timeframe") == timeframe]
        remaining = [
            value for item in group if (value := optional_float(item.get("remaining_hours_to_horizon"))) is not None
        ]
        ages = [value for item in group if (value := optional_float(item.get("age_hours"))) is not None]
        by_timeframe[timeframe] = {
            "active": len(group),
            "past_stale_after": sum(1 for item in group if item.get("past_stale_after")),
            "age_hours_min": min(ages) if ages else None,
            "age_hours_median": percentile(ages, 0.5),
            "age_hours_max": max(ages) if ages else None,
            "remaining_hours_to_horizon_min": min(remaining) if remaining else None,
            "remaining_hours_to_horizon_median": percentile(remaining, 0.5),
            "remaining_hours_to_horizon_max": max(remaining) if remaining else None,
        }
    return {
        "active": len(active_rows),
        "max_active": max_active,
        "active_excess": active_excess,
        "known_remaining": len(known_remaining),
        "past_stale_after": sum(1 for item in items if item.get("past_stale_after")),
        "age_hours_min": min(known_ages) if known_ages else None,
        "age_hours_median": percentile(known_ages, 0.5),
        "age_hours_max": max(known_ages) if known_ages else None,
        "remaining_hours_to_horizon_min": min(known_remaining) if known_remaining else None,
        "remaining_hours_to_horizon_median": percentile(known_remaining, 0.5),
        "remaining_hours_to_horizon_max": max(known_remaining) if known_remaining else None,
        "eta_to_active_cap_hours_upper_bound": eta_to_cap,
        "by_timeframe": by_timeframe,
    }


def build_portfolio_risk(
    completed_rows: list[dict[str, Any]],
    active_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    *,
    scope: str = "global",
    decision_policy_version: str = "",
) -> dict[str, Any]:
    recent_n = int(arg_value(args, "portfolio_recent_trades", 100))
    max_active = int(arg_value(args, "portfolio_max_active", 12))
    active_risk_min_known = int(arg_value(args, "portfolio_active_risk_min_known", 3))
    active_risk_max_sum_r = float(arg_value(args, "portfolio_active_risk_max_sum_r", -2.0))
    active_risk_max_loss_rate = float(arg_value(args, "portfolio_active_risk_max_loss_rate", 0.67))
    active_risk_max_avg_r = float(arg_value(args, "portfolio_active_risk_max_avg_r", -0.25))
    recent_fail_sum_r = float(arg_value(args, "portfolio_recent_fail_sum_r", -20.0))
    recent_max_drawdown_r = float(arg_value(args, "portfolio_recent_max_drawdown_r", 30.0))

    ordered = sorted(
        [row for row in completed_rows if completed_r(row) is not None],
        key=record_time_key,
    )
    completed_values = [value for row in ordered if (value := completed_r(row)) is not None]
    recent_values = completed_values[-recent_n:] if recent_n > 0 else completed_values
    completed_stats = summarize_values(completed_values)
    recent_stats = summarize_values(recent_values)
    active_stats = active_unrealized_stats(active_rows)
    active_r_known = int(active_stats["active_r_known"])
    active_loss_rate = float(active_stats["active_loss"] / active_r_known) if active_r_known else 0.0

    reason_codes: list[str] = []
    if max_active > 0 and len(active_rows) > max_active:
        reason_codes.append(f"portfolio_active>{max_active}")
    if active_r_known >= active_risk_min_known:
        if safe_float(active_stats.get("active_sum_r")) <= active_risk_max_sum_r:
            reason_codes.append(f"portfolio_active_R<={active_risk_max_sum_r:.2f}")
        if active_loss_rate >= active_risk_max_loss_rate and safe_float(active_stats.get("active_avg_r")) <= active_risk_max_avg_r:
            reason_codes.append(
                f"portfolio_active_loss_rate>={active_risk_max_loss_rate:.2f}_avg_R<={active_risk_max_avg_r:.2f}"
            )
    if recent_stats["completed"] > 0 and safe_float(recent_stats.get("sum_r")) <= recent_fail_sum_r:
        reason_codes.append(f"portfolio_recent_sum_R<={recent_fail_sum_r:.2f}")
    if recent_stats["completed"] > 0 and safe_float(recent_stats.get("max_drawdown_r")) >= recent_max_drawdown_r:
        reason_codes.append(f"portfolio_recent_drawdown_R>={recent_max_drawdown_r:.2f}")

    status = "normal"
    if any(reason.startswith("portfolio_active>") for reason in reason_codes):
        status = "overexposed"
    elif any(reason.startswith("portfolio_active_") for reason in reason_codes):
        status = "active_risk"
    elif reason_codes:
        status = "portfolio_drawdown"
    block_new_focus = bool(arg_value(args, "portfolio_block_new_focus_on_risk", True)) and bool(reason_codes)
    return {
        "scope": scope,
        "decision_policy_version": decision_policy_version,
        "status": status,
        "reason_codes": reason_codes,
        "block_new_focus": block_new_focus,
        "active": len(active_rows),
        "active_excess": max(0, len(active_rows) - max_active) if max_active > 0 else 0,
        **active_stats,
        "active_loss_rate": active_loss_rate,
        "completed": completed_stats,
        "recent_completed": recent_stats,
        "thresholds": {
            "portfolio_recent_trades": recent_n,
            "portfolio_max_active": max_active,
            "portfolio_active_risk_min_known": active_risk_min_known,
            "portfolio_active_risk_max_sum_r": active_risk_max_sum_r,
            "portfolio_active_risk_max_loss_rate": active_risk_max_loss_rate,
            "portfolio_active_risk_max_avg_r": active_risk_max_avg_r,
            "portfolio_recent_fail_sum_r": recent_fail_sum_r,
            "portfolio_recent_max_drawdown_r": recent_max_drawdown_r,
        },
    }


def build_portfolio_segment_risk(
    completed_rows: list[dict[str, Any]],
    active_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    recent_n = int(arg_value(args, "portfolio_segment_recent_trades", 100))
    min_completed = int(arg_value(args, "portfolio_segment_min_completed", 20))
    fail_sum_r = float(arg_value(args, "portfolio_segment_fail_sum_r", -20.0))
    max_drawdown_r_threshold = float(arg_value(args, "portfolio_segment_max_drawdown_r", 20.0))
    max_loss_rate = float(arg_value(args, "portfolio_segment_max_loss_rate", 0.70))

    sides = sorted(
        {
            str(row.get("side") or "").lower()
            for row in [*completed_rows, *active_rows]
            if str(row.get("side") or "").lower()
        }
    )
    segments: dict[str, Any] = {}
    blocked_sides: list[str] = []
    reason_codes: list[str] = []
    for side in sides:
        completed_side_rows = [
            row for row in completed_rows if str(row.get("side") or "").lower() == side and completed_r(row) is not None
        ]
        ordered = sorted(completed_side_rows, key=record_time_key)
        values = [value for row in ordered if (value := completed_r(row)) is not None]
        recent_values = values[-recent_n:] if recent_n > 0 else values
        recent_stats = summarize_values(recent_values)
        loss_rate = float(recent_stats["losses"] / recent_stats["completed"]) if recent_stats["completed"] else 0.0
        active_side_rows = [row for row in active_rows if str(row.get("side") or "").lower() == side]
        active_stats = active_unrealized_stats(active_side_rows)

        segment_reasons: list[str] = []
        if recent_stats["completed"] >= min_completed:
            if safe_float(recent_stats.get("sum_r")) <= fail_sum_r:
                segment_reasons.append(f"portfolio_side_recent_sum_R<={fail_sum_r:.2f}")
            if safe_float(recent_stats.get("max_drawdown_r")) >= max_drawdown_r_threshold:
                segment_reasons.append(f"portfolio_side_recent_drawdown_R>={max_drawdown_r_threshold:.2f}")
            if loss_rate >= max_loss_rate:
                segment_reasons.append(f"portfolio_side_loss_rate>={max_loss_rate:.2f}")

        status = "blocked" if segment_reasons else "normal"
        if segment_reasons:
            blocked_sides.append(side)
            reason_codes.extend(f"{side}:{reason}" for reason in segment_reasons)
        segments[side] = {
            "status": status,
            "reason_codes": segment_reasons,
            "recent": {**recent_stats, "loss_rate": loss_rate},
            "completed": summarize_values(values),
            "active": len(active_side_rows),
            **active_stats,
        }

    return {
        "segments": segments,
        "blocked_sides": sorted(blocked_sides),
        "reason_codes": reason_codes,
        "thresholds": {
            "portfolio_segment_recent_trades": recent_n,
            "portfolio_segment_min_completed": min_completed,
            "portfolio_segment_fail_sum_r": fail_sum_r,
            "portfolio_segment_max_drawdown_r": max_drawdown_r_threshold,
            "portfolio_segment_max_loss_rate": max_loss_rate,
        },
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


def policy_group_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        decision_policy_version(row),
        str(row.get("timeframe") or "").lower(),
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
    active_grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in completed_rows:
        value = completed_r(row)
        if value is None:
            continue
        grouped.setdefault(group_key(row), []).append(row)
    for row in active_rows:
        key = group_key(row)
        active_grouped.setdefault(key, []).append(row)

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
        active_group = active_grouped.get(key, [])
        active_stats = active_unrealized_stats(active_group)
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
            "active": len(active_group),
            "active_r_known": active_stats["active_r_known"],
            "active_profit": active_stats["active_profit"],
            "active_loss": active_stats["active_loss"],
            "active_sum_r": active_stats["active_sum_r"],
            "active_avg_r": active_stats["active_avg_r"],
            "active_min_r": active_stats["active_min_r"],
            "active_max_r": active_stats["active_max_r"],
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


def build_policy_scoreboard(completed_rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in completed_rows:
        value = completed_r(row)
        if value is None:
            continue
        grouped.setdefault(policy_group_key(row), []).append(row)

    rows = []
    recent_n = int(arg_value(args, "scoreboard_recent_trades", 50))
    for key, group in grouped.items():
        policy_version, timeframe, side = key
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
                "decision_policy_version": policy_version,
                "timeframe": timeframe,
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
            str(row.get("decision_policy_version")),
            str(row.get("timeframe")),
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
        "active_r_known": row.get("active_r_known"),
        "active_profit": row.get("active_profit"),
        "active_loss": row.get("active_loss"),
        "active_sum_r": row.get("active_sum_r"),
        "active_avg_r": row.get("active_avg_r"),
        "active_min_r": row.get("active_min_r"),
        "active_max_r": row.get("active_max_r"),
        "edge_score": row.get("edge_score"),
        "latest_completed_at": row.get("latest_completed_at"),
    }


def compact_active_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeframe": row.get("timeframe"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "signal_dt": row.get("signal_dt"),
        "latest_dt": row.get("latest_dt"),
        "entry_price": row.get("entry_price"),
        "planned_entry_price": row.get("planned_entry_price"),
        "latest_close": row.get("latest_close"),
        "stop_loss": row.get("stop_loss"),
        "take_profit": row.get("take_profit"),
        "current_r_multiple": row.get("current_r_multiple"),
        "current_directional_pct": row.get("current_directional_pct"),
        "analog_supported": row.get("analog_supported"),
        "analog_used_count": row.get("analog_used_count"),
        "analog_hit_rate": row.get("analog_hit_rate"),
        "analog_profitable_rate": row.get("analog_profitable_rate"),
        "analog_expectancy_r": row.get("analog_expectancy_r"),
        "shadow_reason": row.get("shadow_reason"),
        "decision_policy_version": decision_policy_version(row),
    }


def active_watchlist(rows: list[dict[str, Any]], max_rows: int) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            optional_float(row.get("current_r_multiple")) is None,
            -safe_float(row.get("current_r_multiple")),
            str(row.get("created_at") or ""),
            str(row.get("symbol") or ""),
        ),
    )
    return [compact_active_record(row) for row in ranked[:max_rows]]


def grade_active_shadow_record(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    compact = compact_active_record(row)
    status = str(row.get("status") or "")
    current_r = optional_float(row.get("current_r_multiple"))
    expectancy = optional_float(row.get("analog_expectancy_r"))
    promising_r = float(arg_value(args, "shadow_active_promising_r", 0.50))
    risk_r = float(arg_value(args, "shadow_active_risk_r", -0.50))
    min_promising_expectancy = float(arg_value(args, "shadow_active_min_promising_expectancy_r", 0.15))

    if status == "pending_entry":
        grade = "wait_entry"
        action = "await_entry_fill"
    elif current_r is None:
        grade = "wait_price"
        action = "await_price_refresh"
    elif current_r <= risk_r:
        grade = "risk_active"
        action = "await_exit_do_not_promote"
    elif current_r >= promising_r and (expectancy is None or expectancy >= min_promising_expectancy):
        grade = "promising_active"
        action = "await_completion_for_scoreboard"
    elif current_r > 0.0:
        grade = "positive_active"
        action = "await_completion"
    else:
        grade = "negative_active"
        action = "await_completion_risk_watch"

    return {
        **compact,
        "active_grade": grade,
        "next_action": action,
        "active_grade_reason": (
            f"R={fmt_num(current_r, 3)} "
            f"expectancy_R={fmt_num(expectancy, 3)} "
            f"promising_R>={promising_r:g} risk_R<={risk_r:g}"
        ),
    }


def active_shadow_queue(rows: list[dict[str, Any]], args: argparse.Namespace, max_rows: int) -> list[dict[str, Any]]:
    graded = [grade_active_shadow_record(row, args) for row in rows]
    priority = {
        "promising_active": 0,
        "positive_active": 1,
        "wait_entry": 2,
        "wait_price": 3,
        "negative_active": 4,
        "risk_active": 5,
    }
    graded.sort(
        key=lambda row: (
            priority.get(str(row.get("active_grade")), 9),
            -safe_float(row.get("current_r_multiple")),
            -safe_float(row.get("analog_expectancy_r")),
            str(row.get("created_at") or ""),
            str(row.get("symbol") or ""),
        )
    )
    return graded[:max_rows]


def active_shadow_grade_counts(queue: list[dict[str, Any]]) -> dict[str, int]:
    grades = [
        "promising_active",
        "positive_active",
        "wait_entry",
        "wait_price",
        "negative_active",
        "risk_active",
    ]
    counts = {grade: 0 for grade in grades}
    for row in queue:
        grade = str(row.get("active_grade") or "unknown")
        counts[grade] = counts.get(grade, 0) + 1
    return counts


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


def scoreboard_action_rows(
    scoreboard: list[dict[str, Any]],
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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
    return blocked, fresh_veto, promote, watch


def build_action_plan(
    scoreboard: list[dict[str, Any]],
    *,
    updated_at: str,
    args: argparse.Namespace,
    portfolio_risk: dict[str, Any],
    current_policy_portfolio_risk: dict[str, Any] | None = None,
    current_policy_scoreboard: list[dict[str, Any]] | None = None,
    current_policy_shadow_scoreboard: list[dict[str, Any]] | None = None,
    current_policy_shadow_active_rows: list[dict[str, Any]] | None = None,
    current_decision_policy_version: str = "",
) -> dict[str, Any]:
    max_rows = int(arg_value(args, "actions_max_rows", 80))
    blocked, fresh_veto, promote, watch = scoreboard_action_rows(scoreboard, args)
    current_policy_scoreboard = current_policy_scoreboard or []
    (
        current_policy_blocked,
        current_policy_fresh_veto,
        current_policy_promote,
        current_policy_watch,
    ) = scoreboard_action_rows(current_policy_scoreboard, args)
    current_policy_shadow_scoreboard = current_policy_shadow_scoreboard or []
    (
        current_policy_shadow_blocked,
        current_policy_shadow_fresh_veto,
        current_policy_shadow_promote,
        current_policy_shadow_watch,
    ) = scoreboard_action_rows(current_policy_shadow_scoreboard, args)
    current_policy_shadow_active_queue_all = active_shadow_queue(
        current_policy_shadow_active_rows or [],
        args,
        max(len(current_policy_shadow_active_rows or []), max_rows),
    )
    current_policy_shadow_active_grade_counts = active_shadow_grade_counts(current_policy_shadow_active_queue_all)
    current_policy_portfolio_risk = current_policy_portfolio_risk or portfolio_risk
    return {
        "kind": "contract_paper_strategy_actions_v1",
        "updated_at": updated_at,
        "blocked_pairs": blocked[:max_rows],
        "fresh_analog_veto_pairs": fresh_veto[:max_rows],
        "promote_candidates": promote[:max_rows],
        "positive_watchlist": watch[:max_rows],
        "current_decision_policy_version": current_decision_policy_version,
        "current_policy_blocked_pairs": current_policy_blocked[:max_rows],
        "current_policy_fresh_analog_veto_pairs": current_policy_fresh_veto[:max_rows],
        "current_policy_promote_candidates": current_policy_promote[:max_rows],
        "current_policy_positive_watchlist": current_policy_watch[:max_rows],
        "current_policy_shadow_blocked_pairs": current_policy_shadow_blocked[:max_rows],
        "current_policy_shadow_fresh_analog_veto_pairs": current_policy_shadow_fresh_veto[:max_rows],
        "current_policy_shadow_promote_candidates": current_policy_shadow_promote[:max_rows],
        "current_policy_shadow_positive_watchlist": current_policy_shadow_watch[:max_rows],
        "current_policy_shadow_active_watchlist": active_watchlist(current_policy_shadow_active_rows or [], max_rows),
        "current_policy_shadow_active_queue": current_policy_shadow_active_queue_all[:max_rows],
        "current_policy_shadow_active_grade_counts": current_policy_shadow_active_grade_counts,
        "portfolio_risk": portfolio_risk,
        "current_policy_portfolio_risk": current_policy_portfolio_risk,
        "summary": {
            "blocked_pairs": len(blocked),
            "fresh_analog_veto_pairs": len(fresh_veto),
            "promote_candidates": len(promote),
            "positive_watchlist": len(watch),
            "current_decision_policy_version": current_decision_policy_version,
            "current_policy_blocked_pairs": len(current_policy_blocked),
            "current_policy_fresh_analog_veto_pairs": len(current_policy_fresh_veto),
            "current_policy_promote_candidates": len(current_policy_promote),
            "current_policy_positive_watchlist": len(current_policy_watch),
            "current_policy_shadow_blocked_pairs": len(current_policy_shadow_blocked),
            "current_policy_shadow_fresh_analog_veto_pairs": len(current_policy_shadow_fresh_veto),
            "current_policy_shadow_promote_candidates": len(current_policy_shadow_promote),
            "current_policy_shadow_positive_watchlist": len(current_policy_shadow_watch),
            "current_policy_shadow_active_watchlist": len(current_policy_shadow_active_rows or []),
            "current_policy_shadow_active_promising": current_policy_shadow_active_grade_counts.get(
                "promising_active", 0
            ),
            "current_policy_shadow_active_positive": current_policy_shadow_active_grade_counts.get(
                "positive_active", 0
            ),
            "current_policy_shadow_active_wait_entry": current_policy_shadow_active_grade_counts.get("wait_entry", 0),
            "current_policy_shadow_active_negative": current_policy_shadow_active_grade_counts.get(
                "negative_active", 0
            ),
            "current_policy_shadow_active_risk": current_policy_shadow_active_grade_counts.get("risk_active", 0),
            "portfolio_risk_status": portfolio_risk.get("status"),
            "portfolio_block_new_focus": bool(portfolio_risk.get("block_new_focus")),
            "portfolio_blocked_sides": portfolio_risk.get("blocked_sides") or [],
            "current_policy_portfolio_risk_status": current_policy_portfolio_risk.get("status"),
            "current_policy_portfolio_block_new_focus": bool(
                current_policy_portfolio_risk.get("block_new_focus")
            ),
            "current_policy_portfolio_active": current_policy_portfolio_risk.get("active"),
            "current_policy_portfolio_active_excess": current_policy_portfolio_risk.get("active_excess"),
        },
        "current_policy_summary": {
            "decision_policy_version": current_decision_policy_version,
            "scoreboard_groups": len(current_policy_scoreboard),
            "blocked_pairs": len(current_policy_blocked),
            "fresh_analog_veto_pairs": len(current_policy_fresh_veto),
            "promote_candidates": len(current_policy_promote),
            "positive_watchlist": len(current_policy_watch),
        },
        "current_policy_shadow_summary": {
            "decision_policy_version": current_decision_policy_version,
            "scoreboard_groups": len(current_policy_shadow_scoreboard),
            "blocked_pairs": len(current_policy_shadow_blocked),
            "fresh_analog_veto_pairs": len(current_policy_shadow_fresh_veto),
            "promote_candidates": len(current_policy_shadow_promote),
            "positive_watchlist": len(current_policy_shadow_watch),
            "active_watchlist": len(current_policy_shadow_active_rows or []),
            "active_grade_counts": current_policy_shadow_active_grade_counts,
        },
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def blocked_pairs_for_scope(actions: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    key = "current_policy_blocked_pairs" if scope == "current_policy" else "blocked_pairs"
    rows = actions.get(key) or []
    return rows if isinstance(rows, list) else []


def blocked_pairs_payload(payload: dict[str, Any], scope: str) -> dict[str, Any]:
    actions = payload.get("actions") or {}
    return {
        "kind": "contract_paper_blocked_pairs_v1",
        "updated_at": payload["updated_at"],
        "blocked_pairs_scope": scope,
        "blocked_pairs": blocked_pairs_for_scope(actions, scope),
        "global_blocked_pairs_count": len(actions.get("blocked_pairs") or []),
        "current_policy_blocked_pairs_count": len(actions.get("current_policy_blocked_pairs") or []),
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


def build_current_policy_shadow_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    actions = payload.get("actions") or {}
    grade_counts = actions.get("current_policy_shadow_active_grade_counts") or {}
    promote = actions.get("current_policy_shadow_promote_candidates") or []
    active_queue = actions.get("current_policy_shadow_active_queue") or []

    completed = int(summary.get("current_policy_shadow_completed") or 0)
    active = int(summary.get("current_policy_shadow_active") or 0)
    groups = int(summary.get("current_policy_shadow_scoreboard_groups") or 0)
    promising = int(grade_counts.get("promising_active") or 0)
    positive = int(grade_counts.get("positive_active") or 0)
    wait_entry = int(grade_counts.get("wait_entry") or 0)
    negative = int(grade_counts.get("negative_active") or 0)
    risk = int(grade_counts.get("risk_active") or 0)

    if promote:
        status = "promote_ready"
        severity = "ready"
        next_action = "manual_review_before_paper_canary"
    elif risk > 0:
        status = "risk_watch"
        severity = "risk"
        next_action = "do_not_promote_wait_for_exit"
    elif promising > 0:
        status = "active_promising"
        severity = "watch"
        next_action = "await_completion_for_scoreboard"
    elif positive > 0:
        status = "active_positive"
        severity = "watch"
        next_action = "await_completion"
    elif wait_entry > 0:
        status = "entry_collecting"
        severity = "collecting"
        next_action = "await_entry_fill"
    elif negative > 0:
        status = "active_negative"
        severity = "risk_watch"
        next_action = "await_completion_risk_watch"
    elif active > 0:
        status = "active_collecting"
        severity = "collecting"
        next_action = "await_price_refresh"
    elif completed > 0 or groups > 0:
        status = "completed_no_candidate"
        severity = "collecting"
        next_action = "keep_collecting_or_review_stops"
    else:
        status = "no_shadow_evidence"
        severity = "collecting"
        next_action = "keep_collecting_shadow_samples"

    top_active = []
    for row in active_queue[:5]:
        top_active.append(
            {
                "timeframe": row.get("timeframe"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "status": row.get("status"),
                "active_grade": row.get("active_grade"),
                "current_r_multiple": row.get("current_r_multiple"),
                "analog_expectancy_r": row.get("analog_expectancy_r"),
                "next_action": row.get("next_action"),
            }
        )

    return {
        "status": status,
        "severity": severity,
        "next_action": next_action,
        "decision_policy_version": summary.get("current_decision_policy_version"),
        "records": summary.get("current_policy_shadow_records"),
        "completed": completed,
        "active": active,
        "scoreboard_groups": groups,
        "promote_candidates": len(promote),
        "active_grade_counts": grade_counts,
        "top_active": top_active,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def attach_current_policy_shadow_readiness(payload: dict[str, Any]) -> None:
    readiness = build_current_policy_shadow_readiness(payload)
    payload.setdefault("actions", {})["current_policy_shadow_readiness"] = readiness
    payload.setdefault("actions", {}).setdefault("summary", {})[
        "current_policy_shadow_readiness_status"
    ] = readiness["status"]
    payload["actions"]["summary"]["current_policy_shadow_readiness_severity"] = readiness["severity"]
    payload.setdefault("summary", {})["current_policy_shadow_readiness_status"] = readiness["status"]
    payload["summary"]["current_policy_shadow_readiness_severity"] = readiness["severity"]
    payload["summary"]["current_policy_shadow_readiness_next_action"] = readiness["next_action"]


def write_current_policy_shadow_readiness_marker(payload: dict[str, Any], path: Path) -> None:
    readiness = (
        (payload.get("actions") or {}).get("current_policy_shadow_readiness")
        or build_current_policy_shadow_readiness(payload)
    )
    counts = readiness.get("active_grade_counts") or {}
    top = readiness.get("top_active") or []
    top_text = "none"
    if top:
        first = top[0]
        top_text = (
            f"{first.get('timeframe')}:{first.get('symbol')}:{first.get('side')}:"
            f"{first.get('active_grade')}:R={fmt_num(first.get('current_r_multiple'), 3)}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "CURRENT_POLICY_SHADOW_READINESS "
        f"{payload.get('updated_at')} "
        f"status={readiness.get('status')} "
        f"severity={readiness.get('severity')} "
        f"next_action={readiness.get('next_action')} "
        f"policy={readiness.get('decision_policy_version')} "
        f"records={readiness.get('records')} "
        f"completed={readiness.get('completed')} "
        f"active={readiness.get('active')} "
        f"promote={readiness.get('promote_candidates')} "
        f"grades={counts.get('promising_active', 0)}/{counts.get('positive_active', 0)}/"
        f"{counts.get('wait_entry', 0)}/{counts.get('negative_active', 0)}/{counts.get('risk_active', 0)} "
        f"top={top_text} "
        "paper_trading_authorized=False live_trading_authorized=False\n"
    )


def build_current_policy_fast_shadow_retest(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    scoreboard = payload.get("current_policy_fast_shadow_scoreboard") or []
    retest_candidates = [
        compact_scoreboard_row(row)
        for row in scoreboard
        if row.get("status") == "promote_candidate"
    ]
    stop_candidates = [
        compact_scoreboard_row(row)
        for row in scoreboard
        if row.get("status") == "stop_candidate"
    ]
    completed = int(summary.get("current_policy_fast_shadow_completed") or 0)
    active = int(summary.get("current_policy_fast_shadow_active") or 0)
    groups = int(summary.get("current_policy_fast_shadow_scoreboard_groups") or 0)

    if retest_candidates:
        status = "retest_ready"
        severity = "ready"
        next_action = "run_full_horizon_shadow_retest"
    elif stop_candidates:
        status = "short_horizon_failed"
        severity = "risk"
        next_action = "do_not_retest_keep_collecting"
    elif active > 0:
        status = "fast_shadow_collecting"
        severity = "collecting"
        next_action = "await_fast_shadow_completion"
    elif completed > 0 or groups > 0:
        status = "completed_no_retest"
        severity = "collecting"
        next_action = "keep_collecting_fast_shadow"
    else:
        status = "no_fast_shadow_evidence"
        severity = "collecting"
        next_action = "keep_collecting_fast_shadow"

    return {
        "status": status,
        "severity": severity,
        "next_action": next_action,
        "decision_policy_version": summary.get("current_decision_policy_version"),
        "records": summary.get("current_policy_fast_shadow_records"),
        "completed": completed,
        "active": active,
        "scoreboard_groups": groups,
        "retest_candidates": retest_candidates,
        "stop_candidates": stop_candidates,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def attach_current_policy_fast_shadow_retest(payload: dict[str, Any]) -> None:
    retest = build_current_policy_fast_shadow_retest(payload)
    actions = payload.setdefault("actions", {})
    actions["current_policy_fast_shadow_retest"] = retest
    actions["current_policy_fast_shadow_retest_candidates"] = retest["retest_candidates"]
    actions["current_policy_fast_shadow_stop_candidates"] = retest["stop_candidates"]
    actions.setdefault("summary", {})["current_policy_fast_shadow_retest_status"] = retest["status"]
    actions["summary"]["current_policy_fast_shadow_retest_severity"] = retest["severity"]
    actions["summary"]["current_policy_fast_shadow_retest_candidates"] = len(
        retest["retest_candidates"]
    )
    summary = payload.setdefault("summary", {})
    summary["current_policy_fast_shadow_retest_status"] = retest["status"]
    summary["current_policy_fast_shadow_retest_severity"] = retest["severity"]
    summary["current_policy_fast_shadow_retest_next_action"] = retest["next_action"]


def write_current_policy_fast_shadow_retest_marker(
    payload: dict[str, Any],
    found_marker: Path,
    no_marker: Path | None = None,
    *,
    report_json: str = "",
    actions_json: str = "",
) -> None:
    retest = (
        (payload.get("actions") or {}).get("current_policy_fast_shadow_retest")
        or build_current_policy_fast_shadow_retest(payload)
    )
    candidates = retest.get("retest_candidates") or []
    found_marker.parent.mkdir(parents=True, exist_ok=True)
    if no_marker is not None:
        no_marker.parent.mkdir(parents=True, exist_ok=True)

    if not candidates:
        found_marker.unlink(missing_ok=True)
        if no_marker is not None:
            no_marker.write_text(
                "NO_CURRENT_POLICY_FAST_SHADOW_RETEST "
                f"{payload.get('updated_at')} "
                f"status={retest.get('status')} "
                f"next_action={retest.get('next_action')} "
                f"policy={retest.get('decision_policy_version')} "
                f"completed={retest.get('completed')} "
                f"active={retest.get('active')} "
                f"groups={retest.get('scoreboard_groups')} "
                "paper_trading_authorized=False live_trading_authorized=False\n"
            )
        return

    best = candidates[0]
    if no_marker is not None:
        no_marker.unlink(missing_ok=True)
    fields = [
        "FOUND_CURRENT_POLICY_FAST_SHADOW_RETEST",
        str(payload.get("updated_at")),
        f"status={retest.get('status')}",
        f"next_action={retest.get('next_action')}",
        f"policy={retest.get('decision_policy_version')}",
        f"timeframe={best.get('timeframe')}",
        f"symbol={best.get('symbol')}",
        f"side={best.get('side')}",
        f"recent_n={best.get('recent_completed')}",
        f"recent_sum_R={fmt_num(best.get('recent_sum_r'), 3)}",
        f"recent_pf={fmt_num(best.get('recent_profit_factor'), 3)}",
        f"recent_dd_R={fmt_num(best.get('recent_max_drawdown_r'), 3)}",
        f"score={fmt_num(best.get('edge_score'), 3)}",
        f"report_json={report_json}",
        f"actions_json={actions_json}",
        "note=fast_shadow_only_full_horizon_retest_required",
        "paper_trading_authorized=False",
        "live_trading_authorized=False",
    ]
    found_marker.write_text(" ".join(fields) + "\n")


def write_current_policy_shadow_promote_marker(
    payload: dict[str, Any],
    found_marker: Path,
    no_marker: Path | None = None,
    *,
    report_json: str = "",
    actions_json: str = "",
) -> None:
    actions = payload.get("actions") or {}
    summary = payload.get("summary") or {}
    candidates = actions.get("current_policy_shadow_promote_candidates") or []
    found_marker.parent.mkdir(parents=True, exist_ok=True)
    if no_marker is not None:
        no_marker.parent.mkdir(parents=True, exist_ok=True)

    if not candidates:
        found_marker.unlink(missing_ok=True)
        if no_marker is not None:
            no_marker.write_text(
                "NO_CURRENT_POLICY_SHADOW_PROMOTE "
                f"{payload.get('updated_at')} "
                f"policy={summary.get('current_decision_policy_version')} "
                f"completed={summary.get('current_policy_shadow_completed')} "
                f"active={summary.get('current_policy_shadow_active')} "
                f"groups={summary.get('current_policy_shadow_scoreboard_groups')} "
                "paper_trading_authorized=False live_trading_authorized=False\n"
            )
        return

    best = candidates[0]
    if no_marker is not None:
        no_marker.unlink(missing_ok=True)
    fields = [
        "FOUND_CURRENT_POLICY_SHADOW_PROMOTE",
        str(payload.get("updated_at")),
        f"policy={summary.get('current_decision_policy_version')}",
        f"timeframe={best.get('timeframe')}",
        f"symbol={best.get('symbol')}",
        f"side={best.get('side')}",
        f"recent_n={best.get('recent_completed')}",
        f"recent_sum_R={fmt_num(best.get('recent_sum_r'), 3)}",
        f"recent_pf={fmt_num(best.get('recent_profit_factor'), 3)}",
        f"recent_dd_R={fmt_num(best.get('recent_max_drawdown_r'), 3)}",
        f"recent_win={fmt_pct(best.get('recent_win_rate'))}",
        f"active={best.get('active')}",
        f"active_R={fmt_num(best.get('active_sum_r'), 3)}",
        f"latest_completed_at={best.get('latest_completed_at')}",
    ]
    if report_json:
        fields.append(f"report_json={report_json}")
    if actions_json:
        fields.append(f"actions_json={actions_json}")
    fields.extend(
        [
            "note=shadow_only_manual_review_required",
            "paper_trading_authorized=False",
            "live_trading_authorized=False",
        ]
    )
    found_marker.write_text(" ".join(fields) + "\n")


def load_enriched_records(
    sources: tuple[tuple[str, str], ...],
    *,
    cache_dir: Path,
    lookback_bars: int,
    latest_cache: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
                    cache_dir=cache_dir,
                    lookback_bars=lookback_bars,
                    latest_cache=latest_cache,
                )
            )
    records.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    return records, source_summaries


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    sources = parse_sources(args.sources)
    shadow_sources = parse_shadow_sources(str(arg_value(args, "shadow_sources", "") or ""))
    fast_shadow_sources = parse_fast_shadow_sources(str(arg_value(args, "fast_shadow_sources", "") or ""))
    updated_at = now_utc()
    current_policy_version = str(
        arg_value(args, "current_decision_policy_version", DECISION_POLICY_VERSION) or DECISION_POLICY_VERSION
    )
    latest_cache: dict[tuple[str, str], dict[str, Any]] = {}
    cache_dir = Path(args.cache_dir)
    records, source_summaries = load_enriched_records(
        sources,
        cache_dir=cache_dir,
        lookback_bars=args.lookback_bars,
        latest_cache=latest_cache,
    )
    shadow_records, shadow_source_summaries = load_enriched_records(
        shadow_sources,
        cache_dir=cache_dir,
        lookback_bars=args.lookback_bars,
        latest_cache=latest_cache,
    )
    fast_shadow_records, fast_shadow_source_summaries = load_enriched_records(
        fast_shadow_sources,
        cache_dir=cache_dir,
        lookback_bars=args.lookback_bars,
        latest_cache=latest_cache,
    )
    active_rows = [row for row in records if row.get("status") in {"pending_entry", "open"}]
    pending_rows = [row for row in records if row.get("status") == "pending_entry"]
    open_rows = [row for row in records if row.get("status") == "open"]
    completed_rows = [row for row in records if row.get("status") == "completed"]
    skipped_rows = [row for row in records if row.get("status") == "skipped"]
    wins = [row for row in completed_rows if safe_float(row.get("completed_r_multiple")) > 0]
    losses = [row for row in completed_rows if safe_float(row.get("completed_r_multiple")) < 0]
    scoreboard = build_scoreboard(completed_rows, active_rows, args)
    regime_scoreboard = build_regime_scoreboard(completed_rows, args)
    policy_scoreboard = build_policy_scoreboard(completed_rows, args)
    current_policy_records = rows_for_decision_policy(records, current_policy_version)
    current_policy_completed_rows = rows_for_decision_policy(completed_rows, current_policy_version)
    current_policy_active_rows = rows_for_decision_policy(active_rows, current_policy_version)
    current_policy_scoreboard = build_scoreboard(current_policy_completed_rows, current_policy_active_rows, args)
    shadow_active_rows = [row for row in shadow_records if row.get("status") in {"pending_entry", "open"}]
    shadow_completed_rows = [row for row in shadow_records if row.get("status") == "completed"]
    shadow_scoreboard = build_scoreboard(shadow_completed_rows, shadow_active_rows, args)
    fast_shadow_active_rows = [
        row for row in fast_shadow_records if row.get("status") in {"pending_entry", "open"}
    ]
    fast_shadow_completed_rows = [row for row in fast_shadow_records if row.get("status") == "completed"]
    fast_shadow_scoreboard = build_scoreboard(fast_shadow_completed_rows, fast_shadow_active_rows, args)
    current_policy_shadow_records = rows_for_decision_policy(shadow_records, current_policy_version)
    current_policy_shadow_completed_rows = rows_for_decision_policy(shadow_completed_rows, current_policy_version)
    current_policy_shadow_active_rows = rows_for_decision_policy(shadow_active_rows, current_policy_version)
    current_policy_shadow_scoreboard = build_scoreboard(
        current_policy_shadow_completed_rows,
        current_policy_shadow_active_rows,
        args,
    )
    current_policy_fast_shadow_records = rows_for_decision_policy(fast_shadow_records, current_policy_version)
    current_policy_fast_shadow_completed_rows = rows_for_decision_policy(
        fast_shadow_completed_rows,
        current_policy_version,
    )
    current_policy_fast_shadow_active_rows = rows_for_decision_policy(
        fast_shadow_active_rows,
        current_policy_version,
    )
    current_policy_fast_shadow_scoreboard = build_scoreboard(
        current_policy_fast_shadow_completed_rows,
        current_policy_fast_shadow_active_rows,
        args,
    )
    shadow_active_stats = active_unrealized_stats(shadow_active_rows)
    current_policy_shadow_active_stats = active_unrealized_stats(current_policy_shadow_active_rows)
    fast_shadow_active_stats = active_unrealized_stats(fast_shadow_active_rows)
    current_policy_fast_shadow_active_stats = active_unrealized_stats(current_policy_fast_shadow_active_rows)
    portfolio_drain = build_portfolio_drain(active_rows, args)
    portfolio_segment_risk = build_portfolio_segment_risk(completed_rows, active_rows, args)
    portfolio_risk = build_portfolio_risk(completed_rows, active_rows, args, scope="global")
    portfolio_risk["segment_risk"] = portfolio_segment_risk
    portfolio_risk["drain"] = portfolio_drain
    portfolio_risk["blocked_sides"] = portfolio_segment_risk["blocked_sides"]
    portfolio_risk["side_reason_codes"] = portfolio_segment_risk["reason_codes"]
    current_policy_portfolio_drain = build_portfolio_drain(current_policy_active_rows, args)
    current_policy_portfolio_segment_risk = build_portfolio_segment_risk(
        current_policy_completed_rows,
        current_policy_active_rows,
        args,
    )
    current_policy_portfolio_risk = build_portfolio_risk(
        current_policy_completed_rows,
        current_policy_active_rows,
        args,
        scope="current_policy",
        decision_policy_version=current_policy_version,
    )
    current_policy_portfolio_risk["segment_risk"] = current_policy_portfolio_segment_risk
    current_policy_portfolio_risk["drain"] = current_policy_portfolio_drain
    current_policy_portfolio_risk["blocked_sides"] = current_policy_portfolio_segment_risk["blocked_sides"]
    current_policy_portfolio_risk["side_reason_codes"] = current_policy_portfolio_segment_risk["reason_codes"]
    actions = build_action_plan(
        scoreboard,
        updated_at=updated_at,
        args=args,
        portfolio_risk=portfolio_risk,
        current_policy_portfolio_risk=current_policy_portfolio_risk,
        current_policy_scoreboard=current_policy_scoreboard,
        current_policy_shadow_scoreboard=current_policy_shadow_scoreboard,
        current_policy_shadow_active_rows=current_policy_shadow_active_rows,
        current_decision_policy_version=current_policy_version,
    )
    payload = {
        "kind": "contract_paper_signal_report_v1",
        "updated_at": updated_at,
        "cache_dir": args.cache_dir,
        "sources": source_summaries,
        "shadow_sources": shadow_source_summaries,
        "fast_shadow_sources": fast_shadow_source_summaries,
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
            "policy_scoreboard_groups": len(policy_scoreboard),
            "shadow_records": len(shadow_records),
            "shadow_completed": len(shadow_completed_rows),
            "shadow_active": len(shadow_active_rows),
            "shadow_active_r_known": shadow_active_stats["active_r_known"],
            "shadow_active_profit": shadow_active_stats["active_profit"],
            "shadow_active_loss": shadow_active_stats["active_loss"],
            "shadow_active_sum_r": shadow_active_stats["active_sum_r"],
            "shadow_active_avg_r": shadow_active_stats["active_avg_r"],
            "shadow_active_min_r": shadow_active_stats["active_min_r"],
            "shadow_active_max_r": shadow_active_stats["active_max_r"],
            "shadow_scoreboard_groups": len(shadow_scoreboard),
            "fast_shadow_records": len(fast_shadow_records),
            "fast_shadow_completed": len(fast_shadow_completed_rows),
            "fast_shadow_active": len(fast_shadow_active_rows),
            "fast_shadow_active_r_known": fast_shadow_active_stats["active_r_known"],
            "fast_shadow_active_profit": fast_shadow_active_stats["active_profit"],
            "fast_shadow_active_loss": fast_shadow_active_stats["active_loss"],
            "fast_shadow_active_sum_r": fast_shadow_active_stats["active_sum_r"],
            "fast_shadow_active_avg_r": fast_shadow_active_stats["active_avg_r"],
            "fast_shadow_active_min_r": fast_shadow_active_stats["active_min_r"],
            "fast_shadow_active_max_r": fast_shadow_active_stats["active_max_r"],
            "fast_shadow_scoreboard_groups": len(fast_shadow_scoreboard),
            "current_decision_policy_version": current_policy_version,
            "current_policy_records": len(current_policy_records),
            "current_policy_completed": len(current_policy_completed_rows),
            "current_policy_active": len(current_policy_active_rows),
            "current_policy_scoreboard_groups": len(current_policy_scoreboard),
            "current_policy_shadow_records": len(current_policy_shadow_records),
            "current_policy_shadow_completed": len(current_policy_shadow_completed_rows),
            "current_policy_shadow_active": len(current_policy_shadow_active_rows),
            "current_policy_shadow_active_r_known": current_policy_shadow_active_stats["active_r_known"],
            "current_policy_shadow_active_profit": current_policy_shadow_active_stats["active_profit"],
            "current_policy_shadow_active_loss": current_policy_shadow_active_stats["active_loss"],
            "current_policy_shadow_active_sum_r": current_policy_shadow_active_stats["active_sum_r"],
            "current_policy_shadow_active_avg_r": current_policy_shadow_active_stats["active_avg_r"],
            "current_policy_shadow_active_min_r": current_policy_shadow_active_stats["active_min_r"],
            "current_policy_shadow_active_max_r": current_policy_shadow_active_stats["active_max_r"],
            "current_policy_shadow_active_promising": actions["summary"][
                "current_policy_shadow_active_promising"
            ],
            "current_policy_shadow_active_positive": actions["summary"]["current_policy_shadow_active_positive"],
            "current_policy_shadow_active_wait_entry": actions["summary"][
                "current_policy_shadow_active_wait_entry"
            ],
            "current_policy_shadow_active_negative": actions["summary"]["current_policy_shadow_active_negative"],
            "current_policy_shadow_active_risk": actions["summary"]["current_policy_shadow_active_risk"],
            "current_policy_shadow_scoreboard_groups": len(current_policy_shadow_scoreboard),
            "current_policy_shadow_promote_candidates": sum(
                1 for row in current_policy_shadow_scoreboard if row.get("status") == "promote_candidate"
            ),
            "current_policy_shadow_stop_candidates": sum(
                1 for row in current_policy_shadow_scoreboard if row.get("status") == "stop_candidate"
            ),
            "current_policy_fast_shadow_records": len(current_policy_fast_shadow_records),
            "current_policy_fast_shadow_completed": len(current_policy_fast_shadow_completed_rows),
            "current_policy_fast_shadow_active": len(current_policy_fast_shadow_active_rows),
            "current_policy_fast_shadow_active_r_known": current_policy_fast_shadow_active_stats["active_r_known"],
            "current_policy_fast_shadow_active_profit": current_policy_fast_shadow_active_stats["active_profit"],
            "current_policy_fast_shadow_active_loss": current_policy_fast_shadow_active_stats["active_loss"],
            "current_policy_fast_shadow_active_sum_r": current_policy_fast_shadow_active_stats["active_sum_r"],
            "current_policy_fast_shadow_active_avg_r": current_policy_fast_shadow_active_stats["active_avg_r"],
            "current_policy_fast_shadow_active_min_r": current_policy_fast_shadow_active_stats["active_min_r"],
            "current_policy_fast_shadow_active_max_r": current_policy_fast_shadow_active_stats["active_max_r"],
            "current_policy_fast_shadow_scoreboard_groups": len(current_policy_fast_shadow_scoreboard),
            "current_policy_fast_shadow_retest_candidates": sum(
                1 for row in current_policy_fast_shadow_scoreboard if row.get("status") == "promote_candidate"
            ),
            "current_policy_fast_shadow_stop_candidates": sum(
                1 for row in current_policy_fast_shadow_scoreboard if row.get("status") == "stop_candidate"
            ),
            "current_policy_promote_candidates": sum(
                1 for row in current_policy_scoreboard if row.get("status") == "promote_candidate"
            ),
            "current_policy_stop_candidates": sum(
                1 for row in current_policy_scoreboard if row.get("status") == "stop_candidate"
            ),
            "promote_candidates": sum(1 for row in scoreboard if row.get("status") == "promote_candidate"),
            "stop_candidates": sum(1 for row in scoreboard if row.get("status") == "stop_candidate"),
            "blocked_pairs": len(actions["blocked_pairs"]),
            "fresh_analog_veto_pairs": len(actions["fresh_analog_veto_pairs"]),
            "positive_watchlist": len(actions["positive_watchlist"]),
            "portfolio_risk_status": portfolio_risk["status"],
            "portfolio_block_new_focus": bool(portfolio_risk["block_new_focus"]),
            "current_policy_portfolio_risk_status": current_policy_portfolio_risk["status"],
            "current_policy_portfolio_block_new_focus": bool(current_policy_portfolio_risk["block_new_focus"]),
            "current_policy_portfolio_active_excess": current_policy_portfolio_risk["active_excess"],
            "portfolio_blocked_sides": portfolio_segment_risk["blocked_sides"],
            "portfolio_eta_to_active_cap_hours_upper_bound": portfolio_drain[
                "eta_to_active_cap_hours_upper_bound"
            ],
            "portfolio_active_past_stale_after": portfolio_drain["past_stale_after"],
        },
        "portfolio_risk": portfolio_risk,
        "portfolio_drain": portfolio_drain,
        "portfolio_segment_risk": portfolio_segment_risk,
        "current_policy_portfolio_risk": current_policy_portfolio_risk,
        "current_policy_portfolio_drain": current_policy_portfolio_drain,
        "current_policy_portfolio_segment_risk": current_policy_portfolio_segment_risk,
        "actions": actions,
        "scoreboard": scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "regime_scoreboard": regime_scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "policy_scoreboard": policy_scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "current_policy_scoreboard": current_policy_scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "shadow_scoreboard": shadow_scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "fast_shadow_scoreboard": fast_shadow_scoreboard[: int(arg_value(args, "scoreboard_max_rows", 40))],
        "current_policy_shadow_scoreboard": current_policy_shadow_scoreboard[
            : int(arg_value(args, "scoreboard_max_rows", 40))
        ],
        "current_policy_fast_shadow_scoreboard": current_policy_fast_shadow_scoreboard[
            : int(arg_value(args, "scoreboard_max_rows", 40))
        ],
        "open": active_rows[: args.max_rows],
        "completed": completed_rows[: args.max_rows],
        "skipped": skipped_rows[: args.max_rows],
        "shadow_open": shadow_active_rows[: args.max_rows],
        "fast_shadow_open": fast_shadow_active_rows[: args.max_rows],
        "current_policy_shadow_active_watchlist": active_watchlist(
            current_policy_shadow_active_rows,
            int(arg_value(args, "scoreboard_max_rows", 40)),
        ),
        "current_policy_shadow_active_queue": actions["current_policy_shadow_active_queue"],
        "shadow_completed": shadow_completed_rows[: args.max_rows],
        "fast_shadow_completed": fast_shadow_completed_rows[: args.max_rows],
        "records": records,
        "shadow_records": shadow_records,
        "fast_shadow_records": fast_shadow_records,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    attach_current_policy_shadow_readiness(payload)
    attach_current_policy_fast_shadow_retest(payload)
    return payload


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    portfolio = payload.get("portfolio_risk") or {}
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
        f"- policy_scoreboard_groups: `{summary['policy_scoreboard_groups']}`",
        (
            f"- shadow records/completed/active/groups: "
            f"`{summary['shadow_records']}/{summary['shadow_completed']}/"
            f"{summary['shadow_active']}/{summary['shadow_scoreboard_groups']}`"
        ),
        (
            f"- shadow active_R known/sum/min/max/wl: "
            f"`{summary['shadow_active_r_known']}/{fmt_num(summary['shadow_active_sum_r'], 3)}/"
            f"{fmt_num(summary['shadow_active_min_r'], 3)}/{fmt_num(summary['shadow_active_max_r'], 3)}/"
            f"{summary['shadow_active_profit']}/{summary['shadow_active_loss']}`"
        ),
        (
            f"- fast_shadow records/completed/active/groups: "
            f"`{summary['fast_shadow_records']}/{summary['fast_shadow_completed']}/"
            f"{summary['fast_shadow_active']}/{summary['fast_shadow_scoreboard_groups']}`"
        ),
        (
            f"- current_policy `{summary['current_decision_policy_version']}` "
            f"records/completed/active/groups/promote/stop: "
            f"`{summary['current_policy_records']}/{summary['current_policy_completed']}/"
            f"{summary['current_policy_active']}/{summary['current_policy_scoreboard_groups']}/"
            f"{summary['current_policy_promote_candidates']}/{summary['current_policy_stop_candidates']}`"
        ),
        (
            f"- current_policy_shadow records/completed/active/groups/promote/stop: "
            f"`{summary['current_policy_shadow_records']}/{summary['current_policy_shadow_completed']}/"
            f"{summary['current_policy_shadow_active']}/{summary['current_policy_shadow_scoreboard_groups']}/"
            f"{summary['current_policy_shadow_promote_candidates']}/"
            f"{summary['current_policy_shadow_stop_candidates']}`"
        ),
        (
            f"- current_policy_shadow active_R known/sum/min/max/wl: "
            f"`{summary['current_policy_shadow_active_r_known']}/"
            f"{fmt_num(summary['current_policy_shadow_active_sum_r'], 3)}/"
            f"{fmt_num(summary['current_policy_shadow_active_min_r'], 3)}/"
            f"{fmt_num(summary['current_policy_shadow_active_max_r'], 3)}/"
            f"{summary['current_policy_shadow_active_profit']}/"
            f"{summary['current_policy_shadow_active_loss']}`"
        ),
        (
            f"- current_policy_shadow active grades promising/positive/wait_entry/negative/risk: "
            f"`{summary['current_policy_shadow_active_promising']}/"
            f"{summary['current_policy_shadow_active_positive']}/"
            f"{summary['current_policy_shadow_active_wait_entry']}/"
            f"{summary['current_policy_shadow_active_negative']}/"
            f"{summary['current_policy_shadow_active_risk']}`"
        ),
        (
            f"- current_policy_shadow readiness/action: "
            f"`{summary['current_policy_shadow_readiness_status']}/"
            f"{summary['current_policy_shadow_readiness_next_action']}`"
        ),
        (
            f"- current_policy_fast_shadow records/completed/active/groups/retest/stop: "
            f"`{summary['current_policy_fast_shadow_records']}/"
            f"{summary['current_policy_fast_shadow_completed']}/"
            f"{summary['current_policy_fast_shadow_active']}/"
            f"{summary['current_policy_fast_shadow_scoreboard_groups']}/"
            f"{summary['current_policy_fast_shadow_retest_candidates']}/"
            f"{summary['current_policy_fast_shadow_stop_candidates']}`"
        ),
        (
            f"- current_policy_fast_shadow retest/action: "
            f"`{summary['current_policy_fast_shadow_retest_status']}/"
            f"{summary['current_policy_fast_shadow_retest_next_action']}`"
        ),
        f"- actions blocked/fresh_veto/positive_watch: "
        f"`{summary['blocked_pairs']}/{summary['fresh_analog_veto_pairs']}/{summary['positive_watchlist']}`",
        f"- portfolio_risk: `{portfolio.get('status')}` block_new_focus=`{portfolio.get('block_new_focus')}` "
        f"active=`{portfolio.get('active')}` active_R=`{fmt_num(portfolio.get('active_sum_r'), 3)}` "
        f"active_loss_rate=`{fmt_pct(portfolio.get('active_loss_rate'))}`",
        f"- portfolio_reason_codes: `{','.join(portfolio.get('reason_codes') or [])}`",
        f"- portfolio_blocked_sides: `{','.join(portfolio.get('blocked_sides') or [])}`",
        f"- portfolio_drain_eta_to_cap_h: "
        f"`{fmt_num((portfolio.get('drain') or {}).get('eta_to_active_cap_hours_upper_bound'), 2)}` "
        f"past_stale=`{(portfolio.get('drain') or {}).get('past_stale_after')}`",
        "",
        "## Policy Scoreboard",
        "",
        "| policy | timeframe | side | recent_n | recent_win | recent_sum_R | recent_pf | recent_DD_R | trailing_loss | all_sum_R | score |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["policy_scoreboard"]:
        lines.append(
            f"| {row.get('decision_policy_version')} | {row.get('timeframe')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {fmt_num(row.get('edge_score'), 3)} |"
        )
    lines.extend(
        [
            "",
            "## Current Policy Strategy Scoreboard",
            "",
            "| status | timeframe | symbol | side | recent_n | analog_n | analog_rate | recent_win | recent_sum_R | "
            "recent_pf | recent_DD_R | recent_trailing_loss | all_sum_R | active | active_R | active_w/l | score | reasons |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["current_policy_scoreboard"]:
        lines.append(
            f"| {row.get('status')} | {row.get('timeframe')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {row.get('recent_analog_supported')} | "
            f"{fmt_pct(row.get('recent_analog_supported_rate'))} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {row.get('active')} | {fmt_num(row.get('active_sum_r'), 3)} | "
            f"{row.get('active_profit')}/{row.get('active_loss')} | {fmt_num(row.get('edge_score'), 3)} | "
            f"{', '.join(row.get('reason_codes') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Current Policy Shadow Scoreboard",
            "",
            "| status | timeframe | symbol | side | recent_n | analog_n | analog_rate | recent_win | recent_sum_R | "
            "recent_pf | recent_DD_R | recent_trailing_loss | all_sum_R | active | active_R | active_w/l | score | reasons |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["current_policy_shadow_scoreboard"]:
        lines.append(
            f"| {row.get('status')} | {row.get('timeframe')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {row.get('recent_analog_supported')} | "
            f"{fmt_pct(row.get('recent_analog_supported_rate'))} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {row.get('active')} | {fmt_num(row.get('active_sum_r'), 3)} | "
            f"{row.get('active_profit')}/{row.get('active_loss')} | {fmt_num(row.get('edge_score'), 3)} | "
            f"{', '.join(row.get('reason_codes') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Current Policy Fast Shadow Scoreboard",
            "",
            "| status | timeframe | symbol | side | recent_n | analog_n | analog_rate | recent_win | recent_sum_R | "
            "recent_pf | recent_DD_R | recent_trailing_loss | all_sum_R | active | active_R | active_w/l | score | reasons |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["current_policy_fast_shadow_scoreboard"]:
        lines.append(
            f"| {row.get('status')} | {row.get('timeframe')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {row.get('recent_analog_supported')} | "
            f"{fmt_pct(row.get('recent_analog_supported_rate'))} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {row.get('active')} | {fmt_num(row.get('active_sum_r'), 3)} | "
            f"{row.get('active_profit')}/{row.get('active_loss')} | {fmt_num(row.get('edge_score'), 3)} | "
            f"{', '.join(row.get('reason_codes') or [])} |"
        )
    lines.extend(
        [
            "",
            "## Current Policy Shadow Active",
            "",
            "| timeframe | created_at | symbol | side | status | analog | exp_R | entry | latest | stop | take_profit | current_R | reason |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["current_policy_shadow_active_watchlist"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('created_at')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('status')} | {row.get('analog_supported')} | "
            f"{fmt_num(row.get('analog_expectancy_r'), 3)} | {fmt_num(row.get('entry_price'))} | "
            f"{fmt_num(row.get('latest_close'))} | {fmt_num(row.get('stop_loss'))} | "
            f"{fmt_num(row.get('take_profit'))} | {fmt_num(row.get('current_r_multiple'), 3)} | "
            f"{row.get('shadow_reason')} |"
        )
    lines.extend(
        [
            "",
            "## Current Policy Shadow Active Grades",
            "",
            "| grade | action | timeframe | symbol | side | status | exp_R | entry | latest | stop | take_profit | current_R | reason |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["current_policy_shadow_active_queue"]:
        lines.append(
            f"| {row.get('active_grade')} | {row.get('next_action')} | {row.get('timeframe')} | "
            f"{row.get('symbol')} | {row.get('side')} | {row.get('status')} | "
            f"{fmt_num(row.get('analog_expectancy_r'), 3)} | {fmt_num(row.get('entry_price'))} | "
            f"{fmt_num(row.get('latest_close'))} | {fmt_num(row.get('stop_loss'))} | "
            f"{fmt_num(row.get('take_profit'))} | {fmt_num(row.get('current_r_multiple'), 3)} | "
            f"{row.get('active_grade_reason')} |"
        )
    lines.extend(
        [
        "",
        "## Regime Scoreboard",
        "",
        "| timeframe | regime | side | recent_n | recent_win | recent_sum_R | recent_pf | recent_DD_R | trailing_loss | all_sum_R | score |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
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
        "recent_pf | recent_DD_R | recent_trailing_loss | all_sum_R | active | active_R | active_w/l | score | reasons |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["scoreboard"]:
        lines.append(
            f"| {row.get('status')} | {row.get('timeframe')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('recent_completed')} | {row.get('recent_analog_supported')} | "
            f"{fmt_pct(row.get('recent_analog_supported_rate'))} | {fmt_pct(row.get('recent_win_rate'))} | "
            f"{fmt_num(row.get('recent_sum_r'), 3)} | {fmt_num(row.get('recent_profit_factor'), 3)} | "
            f"{fmt_num(row.get('recent_max_drawdown_r'), 3)} | {row.get('recent_trailing_losses')} | "
            f"{fmt_num(row.get('sum_r'), 3)} | {row.get('active')} | {fmt_num(row.get('active_sum_r'), 3)} | "
            f"{row.get('active_profit')}/{row.get('active_loss')} | {fmt_num(row.get('edge_score'), 3)} | "
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
    portfolio = payload.get("portfolio_risk") or {}
    current_policy_portfolio = payload.get("current_policy_portfolio_risk") or {}
    lines = [
        f"updated_at={payload['updated_at']}",
        f"records={summary['records']} active={summary['active']} open={summary['open']} "
        f"pending={summary['pending_entry']} completed={summary['completed']} skipped={summary['skipped']}",
        f"wins={summary['wins']} losses={summary['losses']} analog_supported_active={summary['analog_supported_open']}",
        f"portfolio_risk={portfolio.get('status')} block_new_focus={portfolio.get('block_new_focus')} "
        f"active={portfolio.get('active')} active_excess={portfolio.get('active_excess')} "
        f"active_R={fmt_num(portfolio.get('active_sum_r'), 3)} "
        f"active_loss_rate={fmt_pct(portfolio.get('active_loss_rate'))} "
        f"reasons={','.join(portfolio.get('reason_codes') or [])} "
        f"blocked_sides={','.join(portfolio.get('blocked_sides') or [])}",
        f"portfolio_drain active={summary['active']} excess={portfolio.get('active_excess')} "
        f"eta_to_cap_h={fmt_num((portfolio.get('drain') or {}).get('eta_to_active_cap_hours_upper_bound'), 2)} "
        f"remaining_h_min/med/max="
        f"{fmt_num((portfolio.get('drain') or {}).get('remaining_hours_to_horizon_min'), 2)}/"
        f"{fmt_num((portfolio.get('drain') or {}).get('remaining_hours_to_horizon_median'), 2)}/"
        f"{fmt_num((portfolio.get('drain') or {}).get('remaining_hours_to_horizon_max'), 2)} "
        f"past_stale={(portfolio.get('drain') or {}).get('past_stale_after')}",
        f"current_policy_portfolio_risk={current_policy_portfolio.get('status')} "
        f"block_new_focus={current_policy_portfolio.get('block_new_focus')} "
        f"active={current_policy_portfolio.get('active')} "
        f"active_excess={current_policy_portfolio.get('active_excess')} "
        f"reasons={','.join(current_policy_portfolio.get('reason_codes') or [])} "
        f"blocked_sides={','.join(current_policy_portfolio.get('blocked_sides') or [])}",
        (
            f"scoreboard_groups={summary['scoreboard_groups']} "
            f"regime_groups={summary['regime_scoreboard_groups']} "
            f"policy_groups={summary['policy_scoreboard_groups']} "
            f"promote={summary['promote_candidates']} stop={summary['stop_candidates']}"
        ),
        (
            f"shadow records={summary['shadow_records']} "
            f"completed={summary['shadow_completed']} "
            f"active={summary['shadow_active']} "
            f"groups={summary['shadow_scoreboard_groups']} "
            f"active_R_known={summary['shadow_active_r_known']} "
            f"active_R={fmt_num(summary['shadow_active_sum_r'], 3)} "
            f"active_min/max={fmt_num(summary['shadow_active_min_r'], 3)}/"
            f"{fmt_num(summary['shadow_active_max_r'], 3)} "
            f"active_wl={summary['shadow_active_profit']}/{summary['shadow_active_loss']}"
        ),
        (
            f"current_policy version={summary['current_decision_policy_version']} "
            f"records={summary['current_policy_records']} "
            f"completed={summary['current_policy_completed']} "
            f"active={summary['current_policy_active']} "
            f"groups={summary['current_policy_scoreboard_groups']} "
            f"promote={summary['current_policy_promote_candidates']} "
            f"stop={summary['current_policy_stop_candidates']}"
        ),
        (
            f"current_policy_shadow records={summary['current_policy_shadow_records']} "
            f"completed={summary['current_policy_shadow_completed']} "
            f"active={summary['current_policy_shadow_active']} "
            f"groups={summary['current_policy_shadow_scoreboard_groups']} "
            f"promote={summary['current_policy_shadow_promote_candidates']} "
            f"stop={summary['current_policy_shadow_stop_candidates']} "
            f"active_R_known={summary['current_policy_shadow_active_r_known']} "
            f"active_R={fmt_num(summary['current_policy_shadow_active_sum_r'], 3)} "
            f"active_min/max={fmt_num(summary['current_policy_shadow_active_min_r'], 3)}/"
            f"{fmt_num(summary['current_policy_shadow_active_max_r'], 3)} "
            f"active_wl={summary['current_policy_shadow_active_profit']}/"
            f"{summary['current_policy_shadow_active_loss']} "
            f"grades={summary['current_policy_shadow_active_promising']}/"
            f"{summary['current_policy_shadow_active_positive']}/"
            f"{summary['current_policy_shadow_active_wait_entry']}/"
            f"{summary['current_policy_shadow_active_negative']}/"
            f"{summary['current_policy_shadow_active_risk']} "
            f"readiness={summary['current_policy_shadow_readiness_status']} "
            f"action={summary['current_policy_shadow_readiness_next_action']}"
        ),
        (
            f"fast_shadow records={summary['fast_shadow_records']} "
            f"completed={summary['fast_shadow_completed']} "
            f"active={summary['fast_shadow_active']} "
            f"groups={summary['fast_shadow_scoreboard_groups']} "
            f"active_R_known={summary['fast_shadow_active_r_known']} "
            f"active_R={fmt_num(summary['fast_shadow_active_sum_r'], 3)} "
            f"active_wl={summary['fast_shadow_active_profit']}/{summary['fast_shadow_active_loss']}"
        ),
        (
            f"current_policy_fast_shadow records={summary['current_policy_fast_shadow_records']} "
            f"completed={summary['current_policy_fast_shadow_completed']} "
            f"active={summary['current_policy_fast_shadow_active']} "
            f"groups={summary['current_policy_fast_shadow_scoreboard_groups']} "
            f"retest={summary['current_policy_fast_shadow_retest_candidates']} "
            f"stop={summary['current_policy_fast_shadow_stop_candidates']} "
            f"active_R_known={summary['current_policy_fast_shadow_active_r_known']} "
            f"active_R={fmt_num(summary['current_policy_fast_shadow_active_sum_r'], 3)} "
            f"active_wl={summary['current_policy_fast_shadow_active_profit']}/"
            f"{summary['current_policy_fast_shadow_active_loss']} "
            f"status={summary['current_policy_fast_shadow_retest_status']} "
            f"action={summary['current_policy_fast_shadow_retest_next_action']}"
        ),
        f"actions_blocked={summary['blocked_pairs']} fresh_veto={summary['fresh_analog_veto_pairs']} "
        f"positive_watch={summary['positive_watchlist']}",
        "safety=paper_authorized:False live:False",
    ]
    for row in payload["policy_scoreboard"][:5]:
        lines.append(
            f"policy {row.get('decision_policy_version')} {row.get('timeframe')} {row.get('side')} "
            f"recent_n={row.get('recent_completed')} recent_sum_R={fmt_num(row.get('recent_sum_r'), 3)} "
            f"recent_pf={fmt_num(row.get('recent_profit_factor'), 3)} "
            f"recent_dd_R={fmt_num(row.get('recent_max_drawdown_r'), 3)} "
            f"score={fmt_num(row.get('edge_score'), 3)}"
        )
    for row in payload["current_policy_scoreboard"][:5]:
        lines.append(
            f"current_policy_scoreboard {row.get('status')} {row.get('timeframe')} {row.get('symbol')} "
            f"{row.get('side')} recent_n={row.get('recent_completed')} "
            f"recent_sum_R={fmt_num(row.get('recent_sum_r'), 3)} "
            f"recent_pf={fmt_num(row.get('recent_profit_factor'), 3)} "
            f"recent_dd_R={fmt_num(row.get('recent_max_drawdown_r'), 3)} "
            f"active={row.get('active')} active_R={fmt_num(row.get('active_sum_r'), 3)} "
            f"score={fmt_num(row.get('edge_score'), 3)}"
        )
    for row in payload["current_policy_shadow_scoreboard"][:5]:
        lines.append(
            f"current_policy_shadow_scoreboard {row.get('status')} {row.get('timeframe')} {row.get('symbol')} "
            f"{row.get('side')} recent_n={row.get('recent_completed')} "
            f"recent_sum_R={fmt_num(row.get('recent_sum_r'), 3)} "
            f"recent_pf={fmt_num(row.get('recent_profit_factor'), 3)} "
            f"recent_dd_R={fmt_num(row.get('recent_max_drawdown_r'), 3)} "
            f"active={row.get('active')} active_R={fmt_num(row.get('active_sum_r'), 3)} "
            f"score={fmt_num(row.get('edge_score'), 3)}"
        )
    for row in payload["current_policy_shadow_active_watchlist"][:5]:
        lines.append(
            f"current_policy_shadow_active {row.get('timeframe')} {row.get('symbol')} {row.get('side')} "
            f"status={row.get('status')} supported={row.get('analog_supported')} "
            f"exp_R={fmt_num(row.get('analog_expectancy_r'), 3)} "
            f"entry={fmt_num(row.get('entry_price'))} latest={fmt_num(row.get('latest_close'))} "
            f"stop={fmt_num(row.get('stop_loss'))} tp={fmt_num(row.get('take_profit'))} "
            f"R={fmt_num(row.get('current_r_multiple'), 3)} reason={row.get('shadow_reason')}"
        )
    for row in payload["current_policy_shadow_active_queue"][:5]:
        lines.append(
            f"current_policy_shadow_active_grade {row.get('active_grade')} {row.get('timeframe')} "
            f"{row.get('symbol')} {row.get('side')} status={row.get('status')} "
            f"action={row.get('next_action')} exp_R={fmt_num(row.get('analog_expectancy_r'), 3)} "
            f"entry={fmt_num(row.get('entry_price'))} latest={fmt_num(row.get('latest_close'))} "
            f"stop={fmt_num(row.get('stop_loss'))} tp={fmt_num(row.get('take_profit'))} "
            f"R={fmt_num(row.get('current_r_multiple'), 3)}"
        )
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
            f"active={row.get('active')} active_R={fmt_num(row.get('active_sum_r'), 3)} "
            f"active_wl={row.get('active_profit')}/{row.get('active_loss')} "
            f"score={fmt_num(row.get('edge_score'), 3)}"
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
    parser.add_argument("--shadow-sources", default="")
    parser.add_argument("--fast-shadow-sources", default="")
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
    parser.add_argument("--shadow-active-promising-r", type=float, default=0.50)
    parser.add_argument("--shadow-active-risk-r", type=float, default=-0.50)
    parser.add_argument("--shadow-active-min-promising-expectancy-r", type=float, default=0.15)
    parser.add_argument("--fresh-veto-min-trades", type=int, default=3)
    parser.add_argument("--fresh-veto-sum-r", type=float, default=-2.0)
    parser.add_argument("--fresh-veto-profit-factor", type=float, default=0.5)
    parser.add_argument("--fresh-veto-trailing-losses", type=int, default=3)
    parser.add_argument("--portfolio-recent-trades", type=int, default=100)
    parser.add_argument("--portfolio-max-active", type=int, default=12)
    parser.add_argument("--portfolio-active-risk-min-known", type=int, default=3)
    parser.add_argument("--portfolio-active-risk-max-sum-r", type=float, default=-2.0)
    parser.add_argument("--portfolio-active-risk-max-loss-rate", type=float, default=0.67)
    parser.add_argument("--portfolio-active-risk-max-avg-r", type=float, default=-0.25)
    parser.add_argument("--portfolio-recent-fail-sum-r", type=float, default=-20.0)
    parser.add_argument("--portfolio-recent-max-drawdown-r", type=float, default=30.0)
    parser.add_argument("--portfolio-block-new-focus-on-risk", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--portfolio-segment-recent-trades", type=int, default=100)
    parser.add_argument("--portfolio-segment-min-completed", type=int, default=20)
    parser.add_argument("--portfolio-segment-fail-sum-r", type=float, default=-20.0)
    parser.add_argument("--portfolio-segment-max-drawdown-r", type=float, default=20.0)
    parser.add_argument("--portfolio-segment-max-loss-rate", type=float, default=0.70)
    parser.add_argument("--actions-max-rows", type=int, default=80)
    parser.add_argument("--current-decision-policy-version", default=DECISION_POLICY_VERSION)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_paper_signal_report_latest.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_paper_signal_report_latest.md")
    parser.add_argument("--out-actions-json", default="")
    parser.add_argument("--out-blocked-pairs-json", default="")
    parser.add_argument(
        "--out-blocked-pairs-scope",
        choices=("current_policy", "global"),
        default="current_policy",
    )
    parser.add_argument("--out-current-policy-shadow-promote-marker", default="")
    parser.add_argument("--out-current-policy-shadow-no-promote-marker", default="")
    parser.add_argument("--out-current-policy-shadow-readiness-marker", default="")
    parser.add_argument("--out-current-policy-shadow-readiness-json", default="")
    parser.add_argument("--out-current-policy-fast-shadow-retest-marker", default="")
    parser.add_argument("--out-current-policy-fast-shadow-no-retest-marker", default="")
    parser.add_argument("--out-current-policy-fast-shadow-retest-json", default="")
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
        write_json(blocked_pairs_payload(payload, args.out_blocked_pairs_scope), Path(args.out_blocked_pairs_json))
    if args.out_current_policy_shadow_promote_marker:
        no_marker = (
            Path(args.out_current_policy_shadow_no_promote_marker)
            if args.out_current_policy_shadow_no_promote_marker
            else None
        )
        write_current_policy_shadow_promote_marker(
            payload,
            Path(args.out_current_policy_shadow_promote_marker),
            no_marker,
            report_json=args.out_json,
            actions_json=args.out_actions_json,
        )
    if args.out_current_policy_shadow_readiness_marker:
        write_current_policy_shadow_readiness_marker(
            payload,
            Path(args.out_current_policy_shadow_readiness_marker),
        )
    if args.out_current_policy_shadow_readiness_json:
        write_json(
            payload["actions"]["current_policy_shadow_readiness"],
            Path(args.out_current_policy_shadow_readiness_json),
        )
    if args.out_current_policy_fast_shadow_retest_marker:
        no_marker = (
            Path(args.out_current_policy_fast_shadow_no_retest_marker)
            if args.out_current_policy_fast_shadow_no_retest_marker
            else None
        )
        write_current_policy_fast_shadow_retest_marker(
            payload,
            Path(args.out_current_policy_fast_shadow_retest_marker),
            no_marker,
            report_json=args.out_json,
            actions_json=args.out_actions_json,
        )
    if args.out_current_policy_fast_shadow_retest_json:
        write_json(
            payload["actions"]["current_policy_fast_shadow_retest"],
            Path(args.out_current_policy_fast_shadow_retest_json),
        )
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
