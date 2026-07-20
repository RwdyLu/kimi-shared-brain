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


def optional_float(value: Any) -> float | None:
    number = safe_float(value, float("nan"))
    if math.isnan(number):
        return None
    return float(number)


def compare_profit_factor(value: Any) -> float:
    return float("inf") if value is None else safe_float(value)


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
    return not probe_rejection_reasons(row, args)


def probe_rejection_reasons(row: dict[str, Any], args: argparse.Namespace) -> list[str]:
    reasons: list[str] = []
    if safe_int(row.get("recent_completed")) < int(args.min_probe_completed):
        reasons.append(f"recent_completed<{int(args.min_probe_completed)}")
    if safe_int(row.get("recent_analog_supported")) < int(args.min_probe_analog_supported):
        reasons.append(f"recent_analog_supported<{int(args.min_probe_analog_supported)}")
    if safe_float(row.get("recent_analog_supported_rate")) < float(args.min_probe_analog_supported_rate):
        reasons.append(f"recent_analog_supported_rate<{float(args.min_probe_analog_supported_rate):.2f}")
    if safe_float(row.get("recent_sum_r")) < float(args.min_probe_sum_r):
        reasons.append(f"recent_sum_r<{float(args.min_probe_sum_r):.2f}")
    if compare_profit_factor(row.get("recent_profit_factor")) < float(args.min_probe_profit_factor):
        reasons.append(f"recent_profit_factor<{float(args.min_probe_profit_factor):.2f}")
    if safe_float(row.get("recent_max_drawdown_r")) > float(args.max_probe_drawdown_r):
        reasons.append(f"recent_max_drawdown_r>{float(args.max_probe_drawdown_r):.2f}")
    if safe_int(row.get("recent_trailing_losses")) > int(args.max_probe_trailing_losses):
        reasons.append(f"recent_trailing_losses>{int(args.max_probe_trailing_losses)}")
    return reasons


def candidate_sort_key(row: dict[str, Any]) -> tuple[float, float, int]:
    return (
        safe_float(row.get("edge_score")),
        safe_float(row.get("recent_sum_r")),
        safe_int(row.get("recent_completed")),
    )


def fresh_signal_sort_key(row: dict[str, Any]) -> tuple[float, float, float, int]:
    return (
        safe_float(row.get("analog_expectancy_r")),
        safe_float(row.get("analog_hit_rate")),
        safe_float(row.get("analog_profitable_rate")),
        safe_int(row.get("analog_used_count")),
    )


def parse_signal_jsons(raw: str) -> list[Path]:
    return [Path(part.strip()) for part in raw.split(",") if part.strip()]


def fresh_analog_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    if not bool(args.include_fresh_analog):
        return []
    rows: list[dict[str, Any]] = []
    for path in parse_signal_jsons(args.signal_jsons):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        timeframe = str(payload.get("timeframe") or "").lower()
        for row in payload.get("rows", []):
            side = str(row.get("signal") or "").lower()
            if side not in {"long", "short"} or not row.get("paper_plan"):
                continue
            analog = row.get("analog_evidence") or {}
            regime_filter = row.get("regime_filter") or {}
            if not analog.get("supported"):
                continue
            if regime_filter.get("allowed") is False:
                continue
            if safe_int(analog.get("used_count")) < int(args.min_fresh_analog_samples):
                continue
            if safe_float(analog.get("expectancy_r")) < float(args.min_fresh_analog_expectancy_r):
                continue
            if safe_float(analog.get("hit_rate")) < float(args.min_fresh_analog_hit_rate):
                continue
            if safe_float(analog.get("profitable_rate")) < float(args.min_fresh_analog_profitable_rate):
                continue
            rows.append(
                {
                    "timeframe": timeframe,
                    "symbol": row.get("symbol"),
                    "side": side,
                    "status": "fresh_analog_signal",
                    "reason_codes": [
                        str(row.get("reason") or "signal"),
                        str(analog.get("reason") or "analog_supported"),
                        str(regime_filter.get("reason") or "regime"),
                    ],
                    "recent_completed": 0,
                    "recent_sum_r": 0.0,
                    "recent_profit_factor": 0.0,
                    "recent_max_drawdown_r": 0.0,
                    "recent_trailing_losses": 0,
                    "recent_analog_supported": 0,
                    "recent_analog_supported_rate": 0.0,
                    "active": 0,
                    "edge_score": safe_float(analog.get("expectancy_r")),
                    "analog_used_count": safe_int(analog.get("used_count")),
                    "analog_hit_rate": safe_float(analog.get("hit_rate")),
                    "analog_profitable_rate": safe_float(analog.get("profitable_rate")),
                    "analog_expectancy_r": safe_float(analog.get("expectancy_r")),
                    "latest_dt": row.get("latest_dt"),
                }
            )
    return sorted(rows, key=fresh_signal_sort_key, reverse=True)


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
            "recent_profit_factor": optional_float(row.get("recent_profit_factor")),
            "recent_max_drawdown_r": safe_float(row.get("recent_max_drawdown_r")),
            "recent_trailing_losses": safe_int(row.get("recent_trailing_losses")),
            "recent_analog_supported": safe_int(row.get("recent_analog_supported")),
            "recent_analog_supported_rate": safe_float(row.get("recent_analog_supported_rate")),
            "analog_used_count": safe_int(row.get("analog_used_count")),
            "analog_hit_rate": safe_float(row.get("analog_hit_rate")),
            "analog_profitable_rate": safe_float(row.get("analog_profitable_rate")),
            "analog_expectancy_r": safe_float(row.get("analog_expectancy_r")),
            "active": safe_int(row.get("active")),
            "active_r_known": safe_int(row.get("active_r_known")),
            "active_profit": safe_int(row.get("active_profit")),
            "active_loss": safe_int(row.get("active_loss")),
            "active_sum_r": safe_float(row.get("active_sum_r")),
            "active_avg_r": safe_float(row.get("active_avg_r")),
            "active_min_r": optional_float(row.get("active_min_r")),
            "active_max_r": optional_float(row.get("active_max_r")),
            "edge_score": safe_float(row.get("edge_score")),
        },
        "reason_codes": row.get("reason_codes") or [],
        "paths": paths,
        "env": env,
        "launch_command": shell_env_command(env, session),
    }


def build_rejection_config(row: dict[str, Any], *, source: str, reasons: list[str]) -> dict[str, Any]:
    timeframe, symbol, side = pair_key(row)
    return {
        "source": source,
        "timeframe": timeframe,
        "symbol": symbol,
        "side": side,
        "rejection_reasons": reasons,
        "metrics": {
            "recent_completed": safe_int(row.get("recent_completed")),
            "recent_sum_r": safe_float(row.get("recent_sum_r")),
            "recent_profit_factor": optional_float(row.get("recent_profit_factor")),
            "recent_max_drawdown_r": safe_float(row.get("recent_max_drawdown_r")),
            "recent_trailing_losses": safe_int(row.get("recent_trailing_losses")),
            "recent_analog_supported": safe_int(row.get("recent_analog_supported")),
            "recent_analog_supported_rate": safe_float(row.get("recent_analog_supported_rate")),
            "analog_used_count": safe_int(row.get("analog_used_count")),
            "analog_hit_rate": safe_float(row.get("analog_hit_rate")),
            "analog_profitable_rate": safe_float(row.get("analog_profitable_rate")),
            "analog_expectancy_r": safe_float(row.get("analog_expectancy_r")),
            "active": safe_int(row.get("active")),
            "active_r_known": safe_int(row.get("active_r_known")),
            "active_profit": safe_int(row.get("active_profit")),
            "active_loss": safe_int(row.get("active_loss")),
            "active_sum_r": safe_float(row.get("active_sum_r")),
            "active_avg_r": safe_float(row.get("active_avg_r")),
            "active_min_r": optional_float(row.get("active_min_r")),
            "active_max_r": optional_float(row.get("active_max_r")),
            "edge_score": safe_float(row.get("edge_score")),
        },
        "reason_codes": row.get("reason_codes") or [],
    }


def reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for reason in row.get("rejection_reasons", []):
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def normalized_shortfall(actual: float, target: float) -> float:
    if target <= 0.0:
        return 0.0
    return max(0.0, target - actual) / target


def near_miss_gap_score(row: dict[str, Any], args: argparse.Namespace) -> float:
    metrics = row.get("metrics") or {}
    return float(
        normalized_shortfall(float(safe_int(metrics.get("recent_completed"))), float(args.min_probe_completed))
        + normalized_shortfall(
            float(safe_int(metrics.get("recent_analog_supported"))),
            float(args.min_probe_analog_supported),
        )
        + normalized_shortfall(
            safe_float(metrics.get("recent_analog_supported_rate")),
            float(args.min_probe_analog_supported_rate),
        )
        + normalized_shortfall(safe_float(metrics.get("recent_sum_r")), float(args.min_probe_sum_r))
        + normalized_shortfall(compare_profit_factor(metrics.get("recent_profit_factor")), float(args.min_probe_profit_factor))
    )


def near_miss_missing_metrics(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    metrics = row.get("metrics") or {}
    missing_completed = max(0, int(args.min_probe_completed) - safe_int(metrics.get("recent_completed")))
    missing_analog_supported = max(
        0,
        int(args.min_probe_analog_supported) - safe_int(metrics.get("recent_analog_supported")),
    )
    missing_analog_supported_rate = max(
        0.0,
        float(args.min_probe_analog_supported_rate) - safe_float(metrics.get("recent_analog_supported_rate")),
    )
    missing_sum_r = max(0.0, float(args.min_probe_sum_r) - safe_float(metrics.get("recent_sum_r")))
    missing_profit_factor = max(
        0.0,
        float(args.min_probe_profit_factor) - compare_profit_factor(metrics.get("recent_profit_factor")),
    )
    active = safe_int(metrics.get("active"))
    active_r_known = safe_int(metrics.get("active_r_known"))
    active_loss = safe_int(metrics.get("active_loss"))
    active_profit = safe_int(metrics.get("active_profit"))
    active_loss_rate = float(active_loss / active_r_known) if active_r_known else 0.0
    return {
        "missing_completed": missing_completed,
        "missing_analog_supported": missing_analog_supported,
        "missing_analog_supported_rate": missing_analog_supported_rate,
        "missing_sum_r": missing_sum_r,
        "missing_profit_factor": missing_profit_factor,
        "active": active,
        "active_r_known": active_r_known,
        "active_profit": active_profit,
        "active_loss": active_loss,
        "active_loss_rate": active_loss_rate,
        "active_sum_r": safe_float(metrics.get("active_sum_r")),
        "active_avg_r": safe_float(metrics.get("active_avg_r")),
        "active_min_r": optional_float(metrics.get("active_min_r")),
        "active_max_r": optional_float(metrics.get("active_max_r")),
        "active_can_cover_missing_completed": active >= missing_completed if missing_completed > 0 else active > 0,
    }


def near_miss_next_action(missing: dict[str, Any]) -> str:
    if safe_int(missing.get("active")) > 0 and (
        safe_int(missing.get("missing_completed")) > 0 or safe_float(missing.get("missing_sum_r")) > 0.0
    ):
        if (
            safe_int(missing.get("active_r_known")) > 0
            and safe_float(missing.get("active_sum_r")) < 0.0
            and safe_float(missing.get("active_loss_rate")) >= 0.5
        ):
            return "await_active_settlement_risk"
        return "await_active_settlement"
    return "probe_more"


def build_near_miss_queue(rejected: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    hard_prefixes = ("recent_max_drawdown_r>", "recent_trailing_losses>")
    rows: list[dict[str, Any]] = []
    for row in rejected:
        reasons = list(row.get("rejection_reasons") or [])
        metrics = row.get("metrics") or {}
        if row.get("source") != "positive_watchlist":
            continue
        if "blocked_pair" in reasons or "fresh_analog_veto_pair" in reasons:
            continue
        if any(reason.startswith(hard_prefixes) for reason in reasons):
            continue
        if safe_int(metrics.get("recent_completed")) < int(args.min_near_miss_completed):
            continue
        if safe_float(metrics.get("recent_sum_r")) <= 0.0:
            continue
        if compare_profit_factor(metrics.get("recent_profit_factor")) < float(args.min_near_miss_profit_factor):
            continue
        gap = near_miss_gap_score(row, args)
        if gap > float(args.max_near_miss_gap_score):
            continue
        near = dict(row)
        near["near_miss_gap_score"] = gap
        near["readiness_score"] = float(1.0 / (1.0 + gap))
        near["missing_metrics"] = near_miss_missing_metrics(row, args)
        near["next_action"] = near_miss_next_action(near["missing_metrics"])
        rows.append(near)
    rows.sort(
        key=lambda row: (
            safe_float(row.get("near_miss_gap_score")),
            -safe_float((row.get("metrics") or {}).get("recent_sum_r")),
            -safe_float((row.get("metrics") or {}).get("edge_score")),
            -safe_int((row.get("metrics") or {}).get("recent_completed")),
            str(row.get("timeframe")),
            str(row.get("symbol")),
            str(row.get("side")),
        )
    )
    return rows[: int(args.max_near_miss_candidates)]


def build_paper_probe_candidates(
    near_miss: list[dict[str, Any]],
    args: argparse.Namespace,
    used: set[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    if not bool(args.include_near_miss_paper_probes):
        return []
    rows: list[dict[str, Any]] = []
    for row in near_miss:
        if row.get("next_action") != "probe_more":
            continue
        key = pair_key(row)
        if key in used:
            continue
        rows.append(build_candidate_config(row, source="near_miss_probe"))
        used.add(key)
        if len(rows) >= int(args.max_near_miss_paper_probes):
            break
    return rows


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    actions = json.loads(Path(args.actions_json).read_text())
    blocked = {pair_key(row) for row in actions.get("blocked_pairs", [])}
    fresh_veto = {pair_key(row) for row in actions.get("fresh_analog_veto_pairs", [])}
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    used: set[tuple[str, str, str]] = set()
    max_rejections = int(args.max_rejections)

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
            reasons: list[str] = []
            if key in blocked and not args.allow_blocked:
                reasons.append("blocked_pair")
            if source == "positive_watchlist":
                reasons.extend(probe_rejection_reasons(row, args))
            if reasons:
                if len(rejected) < max_rejections:
                    rejected.append(build_rejection_config(row, source=source, reasons=reasons))
                continue
            selected.append(build_candidate_config(row, source=source))
            used.add(key)
            if len(selected) >= int(args.max_candidates):
                break
        if len(selected) >= int(args.max_candidates):
            break

    fresh_rows = fresh_analog_rows(args)
    fresh_added = 0
    for row in fresh_rows:
        if len(selected) >= int(args.max_candidates) or fresh_added >= int(args.max_fresh_analog_candidates):
            break
        key = pair_key(row)
        if key in used:
            continue
        reasons = []
        if key in blocked and not args.allow_blocked:
            reasons.append("blocked_pair")
        if key in fresh_veto and not args.allow_fresh_veto:
            reasons.append("fresh_analog_veto_pair")
        if reasons:
            if len(rejected) < max_rejections:
                rejected.append(build_rejection_config(row, source="fresh_analog_signal", reasons=reasons))
            continue
        selected.append(build_candidate_config(row, source="fresh_analog_signal"))
        used.add(key)
        fresh_added += 1

    rejection_reason_counts = reason_counts(rejected)
    near_miss = build_near_miss_queue(rejected, args)
    paper_probe_candidates = build_paper_probe_candidates(near_miss, args, used)

    return {
        "kind": "contract_focus_canary_plan_v1",
        "updated_at": now_utc(),
        "actions_json": args.actions_json,
        "config": {
            "max_candidates": int(args.max_candidates),
            "max_rejections": max_rejections,
            "max_near_miss_candidates": int(args.max_near_miss_candidates),
            "include_near_miss_paper_probes": bool(args.include_near_miss_paper_probes),
            "max_near_miss_paper_probes": int(args.max_near_miss_paper_probes),
            "min_near_miss_completed": int(args.min_near_miss_completed),
            "min_near_miss_profit_factor": float(args.min_near_miss_profit_factor),
            "max_near_miss_gap_score": float(args.max_near_miss_gap_score),
            "include_fresh_analog": bool(args.include_fresh_analog),
            "signal_jsons": args.signal_jsons,
            "max_fresh_analog_candidates": int(args.max_fresh_analog_candidates),
            "allow_fresh_veto": bool(args.allow_fresh_veto),
            "min_fresh_analog_samples": int(args.min_fresh_analog_samples),
            "min_fresh_analog_hit_rate": float(args.min_fresh_analog_hit_rate),
            "min_fresh_analog_profitable_rate": float(args.min_fresh_analog_profitable_rate),
            "min_fresh_analog_expectancy_r": float(args.min_fresh_analog_expectancy_r),
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
            "fresh_analog_veto_pairs": len(fresh_veto),
            "promote_candidates_seen": len(actions.get("promote_candidates", [])),
            "positive_watchlist_seen": len(actions.get("positive_watchlist", [])),
            "fresh_analog_seen": len(fresh_rows),
            "fresh_analog_added": fresh_added,
            "rejected_candidates": len(rejected),
            "near_miss_candidates": len(near_miss),
            "paper_probe_candidates": len(paper_probe_candidates),
            "rejection_reason_counts": rejection_reason_counts,
        },
        "candidates": selected,
        "near_miss_candidates": near_miss,
        "paper_probe_candidates": paper_probe_candidates,
        "rejected_candidates": rejected,
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
        f"- fresh analog veto pairs: `{summary.get('fresh_analog_veto_pairs', 0)}`",
        f"- fresh analog seen/added: `{summary.get('fresh_analog_seen', 0)}/{summary.get('fresh_analog_added', 0)}`",
        f"- near-miss candidates: `{summary.get('near_miss_candidates', 0)}`",
        f"- paper probe candidates: `{summary.get('paper_probe_candidates', 0)}`",
        f"- rejected candidates shown: `{summary.get('rejected_candidates', 0)}`",
        "",
        "| rank | source | timeframe | symbol | side | recent_n | analog | analog_rate | signal_exp_R | sum_R | pf | max_DD_R | active_R | trailing_loss | session |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(payload["candidates"], start=1):
        metrics = row["metrics"]
        lines.append(
            f"| {idx} | {row['source']} | {row['timeframe']} | {row['symbol']} | {row['side']} | "
            f"{metrics['recent_completed']} | {metrics['recent_analog_supported']} | "
            f"{fmt_num(metrics['recent_analog_supported_rate'])} | {fmt_num(metrics['analog_expectancy_r'])} | "
            f"{fmt_num(metrics['recent_sum_r'])} | "
            f"{fmt_num(metrics['recent_profit_factor'])} | {fmt_num(metrics['recent_max_drawdown_r'])} | "
            f"{fmt_num(metrics['active_sum_r'])} | {metrics['recent_trailing_losses']} | `{row['session']}` |"
        )
    if payload.get("near_miss_candidates"):
        lines.extend(
            [
                "",
                "## Near-Miss Queue",
                "",
                "| rank | timeframe | symbol | side | readiness | action | gap | missing | active | active_R | active_w/l | recent_n | analog | analog_rate | sum_R | pf | max_DD_R | trailing_loss |",
                "| ---: | --- | --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for idx, row in enumerate(payload["near_miss_candidates"], start=1):
            metrics = row["metrics"]
            missing = row.get("missing_metrics") or {}
            lines.append(
                f"| {idx} | {row['timeframe']} | {row['symbol']} | {row['side']} | "
                f"{fmt_num(row.get('readiness_score'))} | {row.get('next_action')} | "
                f"{fmt_num(row.get('near_miss_gap_score'))} | "
                f"{','.join(row['rejection_reasons'])} | "
                f"{missing.get('active')} | {fmt_num(missing.get('active_sum_r'))} | "
                f"{missing.get('active_profit')}/{missing.get('active_loss')} | "
                f"{metrics['recent_completed']} | {metrics['recent_analog_supported']} | "
                f"{fmt_num(metrics['recent_analog_supported_rate'])} | {fmt_num(metrics['recent_sum_r'])} | "
                f"{fmt_num(metrics['recent_profit_factor'])} | {fmt_num(metrics['recent_max_drawdown_r'])} | "
                f"{metrics['recent_trailing_losses']} |"
            )
    if payload.get("paper_probe_candidates"):
        lines.extend(
            [
                "",
                "## Paper Probe Candidates",
                "",
                "| rank | source | timeframe | symbol | side | recent_n | analog | analog_rate | sum_R | pf | active_R | session |",
                "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for idx, row in enumerate(payload["paper_probe_candidates"], start=1):
            metrics = row["metrics"]
            lines.append(
                f"| {idx} | {row['source']} | {row['timeframe']} | {row['symbol']} | {row['side']} | "
                f"{metrics['recent_completed']} | {metrics['recent_analog_supported']} | "
                f"{fmt_num(metrics['recent_analog_supported_rate'])} | {fmt_num(metrics['recent_sum_r'])} | "
                f"{fmt_num(metrics['recent_profit_factor'])} | {fmt_num(metrics['active_sum_r'])} | `{row['session']}` |"
            )
    if payload.get("rejected_candidates"):
        lines.extend(
            [
                "",
                "## Rejected Candidates",
                "",
                "| rank | source | timeframe | symbol | side | reasons | recent_n | analog | analog_rate | signal_exp_R | sum_R | pf | max_DD_R | active_R | trailing_loss |",
                "| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for idx, row in enumerate(payload["rejected_candidates"], start=1):
            metrics = row["metrics"]
            lines.append(
                f"| {idx} | {row['source']} | {row['timeframe']} | {row['symbol']} | {row['side']} | "
                f"{','.join(row['rejection_reasons'])} | "
                f"{metrics['recent_completed']} | {metrics['recent_analog_supported']} | "
                f"{fmt_num(metrics['recent_analog_supported_rate'])} | {fmt_num(metrics['analog_expectancy_r'])} | "
                f"{fmt_num(metrics['recent_sum_r'])} | {fmt_num(metrics['recent_profit_factor'])} | "
                f"{fmt_num(metrics['recent_max_drawdown_r'])} | {fmt_num(metrics['active_sum_r'])} | "
                f"{metrics['recent_trailing_losses']} |"
            )
    lines.extend(["", "## Launch Commands", ""])
    for row in payload["candidates"]:
        lines.extend(["```bash", row["launch_command"], "```", ""])
    if payload.get("paper_probe_candidates"):
        lines.extend(["", "## Paper Probe Launch Commands", ""])
        for row in payload["paper_probe_candidates"]:
            lines.extend(["```bash", row["launch_command"], "```", ""])
    lines.append("Paper-only focused canary plan. No live trading is authorized.")
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"updated_at={payload['updated_at']}",
        f"selected={summary['selected']} promote_seen={summary['promote_candidates_seen']} "
        f"positive_seen={summary['positive_watchlist_seen']} blocked_seen={summary['blocked_pairs']} "
        f"fresh_veto={summary.get('fresh_analog_veto_pairs', 0)} "
        f"fresh_seen={summary.get('fresh_analog_seen', 0)} fresh_added={summary.get('fresh_analog_added', 0)} "
        f"near_miss={summary.get('near_miss_candidates', 0)} "
        f"paper_probes={summary.get('paper_probe_candidates', 0)} rejected={summary.get('rejected_candidates', 0)}",
        f"reject_reasons={json.dumps(summary.get('rejection_reason_counts', {}), sort_keys=True)}",
        "safety=paper_authorized:False live:False",
    ]
    for row in payload.get("near_miss_candidates", []):
        metrics = row["metrics"]
        lines.append(
            f"near_miss {row['timeframe']} {row['symbol']} {row['side']} "
            f"readiness={fmt_num(row.get('readiness_score'))} action={row.get('next_action')} "
            f"gap={fmt_num(row.get('near_miss_gap_score'))} "
            f"missing={','.join(row.get('rejection_reasons') or [])} "
            f"recent_n={metrics['recent_completed']} sum_R={fmt_num(metrics['recent_sum_r'])} "
            f"pf={fmt_num(metrics['recent_profit_factor'])} "
            f"analog={metrics['recent_analog_supported']}/{fmt_num(metrics['recent_analog_supported_rate'])} "
            f"active_R={fmt_num(metrics['active_sum_r'])} active_wl={metrics['active_profit']}/{metrics['active_loss']} "
            f"trailing_losses={metrics['recent_trailing_losses']}"
        )
    for row in payload.get("paper_probe_candidates", []):
        metrics = row["metrics"]
        lines.append(
            f"paper_probe {row['timeframe']} {row['symbol']} {row['side']} "
            f"recent_n={metrics['recent_completed']} sum_R={fmt_num(metrics['recent_sum_r'])} "
            f"pf={fmt_num(metrics['recent_profit_factor'])} "
            f"analog={metrics['recent_analog_supported']}/{fmt_num(metrics['recent_analog_supported_rate'])} "
            f"active_R={fmt_num(metrics['active_sum_r'])} "
            f"session={row['session']}"
        )
    for row in payload["candidates"]:
        metrics = row["metrics"]
        lines.append(
            f"candidate {row['source']} {row['timeframe']} {row['symbol']} {row['side']} "
            f"recent_n={metrics['recent_completed']} sum_R={fmt_num(metrics['recent_sum_r'])} "
            f"pf={fmt_num(metrics['recent_profit_factor'])} max_dd_R={fmt_num(metrics['recent_max_drawdown_r'])} "
            f"analog={metrics['recent_analog_supported']}/{fmt_num(metrics['recent_analog_supported_rate'])} "
            f"active_R={fmt_num(metrics['active_sum_r'])} active_wl={metrics['active_profit']}/{metrics['active_loss']} "
            f"signal_exp_R={fmt_num(metrics['analog_expectancy_r'])} "
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
    parser.add_argument("--max-rejections", type=int, default=50)
    parser.add_argument("--max-near-miss-candidates", type=int, default=5)
    parser.add_argument("--include-near-miss-paper-probes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-near-miss-paper-probes", type=int, default=1)
    parser.add_argument("--min-near-miss-completed", type=int, default=4)
    parser.add_argument("--min-near-miss-profit-factor", type=float, default=1.0)
    parser.add_argument("--max-near-miss-gap-score", type=float, default=1.0)
    parser.add_argument("--include-fresh-analog", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--signal-jsons",
        default=(
            "artifacts/v9/contract_lab/contract_latest_market_signal_latest.json,"
            "artifacts/v9/contract_lab/contract_latest_market_signal_15m_latest.json"
        ),
    )
    parser.add_argument("--max-fresh-analog-candidates", type=int, default=2)
    parser.add_argument("--allow-fresh-veto", action="store_true")
    parser.add_argument("--min-fresh-analog-samples", type=int, default=30)
    parser.add_argument("--min-fresh-analog-hit-rate", type=float, default=0.42)
    parser.add_argument("--min-fresh-analog-profitable-rate", type=float, default=0.42)
    parser.add_argument("--min-fresh-analog-expectancy-r", type=float, default=0.25)
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
