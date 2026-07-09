#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


AXIS_KEYS = ("k", "lookback_h", "market_filter_h", "rebalance_h", "vol_target_ann", "skip_h", "n_tranches")
EXACT_KEYS = ("score_mode",)
BLOCKING_FAMILY_STATUSES = {
    "family_rejected_train_stress",
    "cost_sensitive",
    "needs_turnover_reduction",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve_path(path: str | Path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base / p


def first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if math.isfinite(float(value)):
                return float(value)
    return None


def cost_block(row: dict[str, Any], cost_name: str) -> dict[str, Any]:
    selection = row.get("selection") or {}
    validation = row.get("validation") or {}
    return selection.get(cost_name) or validation.get(cost_name) or row.get(cost_name) or {}


def cost_metric(row: dict[str, Any], key: str, preferred_cost: str = "cost40") -> float | None:
    preferred = cost_block(row, preferred_cost)
    fallback = cost_block(row, "cost20" if preferred_cost == "cost40" else "cost40")
    return first_number(preferred.get(key), fallback.get(key))


def walk_forward(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("walk_forward") or row.get("diagnostic_walk_forward") or {}


def leave_one_symbol(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("leave_one_symbol") or {}


def all_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # For xsec/tsmom train-only artifacts, `top` rows carry enriched robustness
    # blocks such as walk_forward and leave_one_symbol. Raw `rows` can be a
    # larger grid without those blocks, which is not enough for triage.
    top = payload.get("top")
    if isinstance(top, list) and top:
        return [row for row in top if isinstance(row, dict)]
    rows = payload.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def accepted_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in all_rows(payload) if row.get("advance_passed")]


def canonical_config(config: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(config or {})
    out.setdefault("n_tranches", 1)
    return out


def config_signature(kind: str | None, symbols: list[Any] | None, config: dict[str, Any]) -> str:
    return json.dumps(
        {
            "kind": kind,
            "symbols": symbols or [],
            "config": canonical_config(config),
        },
        sort_keys=True,
    )


def artifact_family_prefix(artifact: str) -> str:
    return Path(artifact).stem


def family_key(artifact: str, kind: str | None, config: dict[str, Any]) -> str:
    cfg = canonical_config(config)
    return json.dumps(
        {
            "artifact": artifact_family_prefix(artifact),
            "kind": kind,
            "k": cfg.get("k"),
            "market_filter_h": cfg.get("market_filter_h"),
            "rebalance_h": cfg.get("rebalance_h"),
            "score_mode": cfg.get("score_mode"),
            "n_tranches": cfg.get("n_tranches", 1),
        },
        sort_keys=True,
    )


def family_key_from_stress_candidate(source_artifact: str, kind: str | None, row: dict[str, Any]) -> str:
    return family_key(source_artifact, kind, row.get("config") or {})


def load_family_status(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = read_json(path)
    raw_families = payload.get("families") if isinstance(payload, dict) else None
    if isinstance(raw_families, dict):
        return {str(key): dict(value) for key, value in raw_families.items() if isinstance(value, dict)}
    return {}


def status_blocks_family(status: dict[str, Any] | None) -> bool:
    if not status:
        return False
    values = {str(status.get("status") or ""), str(status.get("decision") or "")}
    tags = status.get("tags") or []
    if isinstance(tags, list):
        values.update(str(tag) for tag in tags)
    return bool(values & BLOCKING_FAMILY_STATUSES)


def axis_values(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    values: dict[str, set[Any]] = {key: set() for key in AXIS_KEYS}
    for row in rows:
        config = canonical_config(row.get("config"))
        for key in AXIS_KEYS:
            if key in config:
                values[key].add(config[key])
    return {key: sorted(vals) for key, vals in values.items() if vals}


def same_family(left: dict[str, Any], right: dict[str, Any]) -> bool:
    lc = canonical_config(left.get("config"))
    rc = canonical_config(right.get("config"))
    for key in EXACT_KEYS:
        if lc.get(key) != rc.get(key):
            return False
    return True


def index_distance(key: str, left: Any, right: Any, values: dict[str, list[Any]]) -> int | None:
    ordered = values.get(key)
    if not ordered or left not in ordered or right not in ordered:
        return None
    return abs(ordered.index(left) - ordered.index(right))


def is_neighbor(
    center: dict[str, Any],
    row: dict[str, Any],
    values: dict[str, list[Any]],
    *,
    max_axis_distance: int,
    max_changed_axes: int,
) -> bool:
    center_config = canonical_config(center.get("config"))
    row_config = canonical_config(row.get("config"))
    if center_config == row_config:
        return False
    if not same_family(center, row):
        return False

    changed_axes = 0
    for key in AXIS_KEYS:
        if key not in center_config and key not in row_config:
            continue
        left = center_config.get(key)
        right = row_config.get(key)
        if left == right:
            continue
        distance = index_distance(key, left, right, values)
        if distance is None or distance > max_axis_distance:
            return False
        changed_axes += 1
        if changed_axes > max_changed_axes:
            return False

    non_axis_keys = (set(center_config) | set(row_config)) - set(AXIS_KEYS) - set(EXACT_KEYS)
    for key in non_axis_keys:
        if center_config.get(key) != row_config.get(key):
            return False
    return changed_axes > 0


def row_passes_neighbor_gate(
    row: dict[str, Any],
    *,
    min_bootstrap_p5: float,
    min_walk_forward_q25: float,
    min_loso_sharpe: float,
    max_drawdown: float,
) -> bool:
    if not row.get("advance_passed"):
        return False
    boot = cost_metric(row, "bootstrap_30d_sharpe_p5", "cost40")
    wf = walk_forward(row)
    loso = leave_one_symbol(row)
    q25 = first_number(wf.get("q25_sharpe"))
    loso_sharpe = first_number(loso.get("min_sharpe"))
    max_dd = cost_metric(row, "max_drawdown", "cost40")
    total_return = cost_metric(row, "total_return", "cost40")
    return (
        (boot is not None and boot >= min_bootstrap_p5)
        and (q25 is not None and q25 >= min_walk_forward_q25)
        and (loso_sharpe is not None and loso_sharpe >= min_loso_sharpe)
        and (max_dd is not None and max_dd <= max_drawdown)
        and (total_return is not None and total_return > 0.0)
    )


def row_metrics(row: dict[str, Any]) -> dict[str, Any]:
    wf = walk_forward(row)
    loso = leave_one_symbol(row)
    return {
        "sharpe40": cost_metric(row, "sharpe", "cost40"),
        "return40": cost_metric(row, "total_return", "cost40"),
        "max_drawdown40": cost_metric(row, "max_drawdown", "cost40"),
        "bootstrap_p5_40": cost_metric(row, "bootstrap_30d_sharpe_p5", "cost40"),
        "daily_turnover": cost_metric(row, "daily_turnover", "cost40"),
        "walk_forward_q25": first_number(wf.get("q25_sharpe")),
        "walk_forward_positive_return_fraction": first_number(wf.get("positive_return_fraction")),
        "leave_one_symbol_min_sharpe": first_number(loso.get("min_sharpe")),
        "leave_one_symbol_min_return": first_number(loso.get("min_return")),
    }


def quality_score(metrics: dict[str, Any], neighbor_pass_fraction: float, neighbor_count: int) -> float:
    sharpe = float(metrics.get("sharpe40") or 0.0)
    boot = float(metrics.get("bootstrap_p5_40") or 0.0)
    q25 = float(metrics.get("walk_forward_q25") or 0.0)
    loso = float(metrics.get("leave_one_symbol_min_sharpe") or 0.0)
    drawdown = float(metrics.get("max_drawdown40") or 1.0)
    neighbor_bonus = neighbor_pass_fraction * min(neighbor_count, 12) / 12.0
    return round((1.5 * sharpe) + boot + q25 + (0.5 * loso) + neighbor_bonus - drawdown, 6)


def artifact_status_rows(state: dict[str, Any], base: Path, include_data_drift: bool) -> tuple[list[dict[str, Any]], int]:
    by_artifact: dict[str, dict[str, Any]] = {}
    excluded_data_drift = 0
    for candidate in state.get("candidates_found", []):
        raw = candidate.get("output_json")
        if not raw:
            continue
        status = str(candidate.get("status") or "")
        if "data_drift" in status and not include_data_drift:
            excluded_data_drift += 1
            continue
        key = str(raw)
        current = by_artifact.setdefault(
            key,
            {
                "artifact": key,
                "path": resolve_path(key, base),
                "tasks": [],
                "statuses": set(),
            },
        )
        current["tasks"].append(candidate.get("task"))
        current["statuses"].add(status)
    rows = []
    for row in by_artifact.values():
        rows.append({**row, "statuses": sorted(row["statuses"])})
    return rows, excluded_data_drift


def triage_artifact(
    artifact: dict[str, Any],
    *,
    min_neighbor_pass_fraction: float,
    min_neighbor_count: int,
    max_axis_distance: int,
    max_changed_axes: int,
    min_bootstrap_p5: float,
    min_walk_forward_q25: float,
    min_loso_sharpe: float,
    max_drawdown: float,
) -> list[dict[str, Any]]:
    path = artifact["path"]
    if not path.exists():
        return [
            {
                "decision": "missing_artifact",
                "artifact": artifact["artifact"],
                "tasks": artifact["tasks"],
                "statuses": artifact["statuses"],
                "reason": "output_json does not exist",
            }
        ]
    payload = read_json(path)
    rows = all_rows(payload)
    centers = accepted_rows(payload)
    values = axis_values(rows)
    out = []
    for center in centers:
        neighbors = [
            row
            for row in rows
            if is_neighbor(
                center,
                row,
                values,
                max_axis_distance=max_axis_distance,
                max_changed_axes=max_changed_axes,
            )
        ]
        passing_neighbors = [
            row
            for row in neighbors
            if row_passes_neighbor_gate(
                row,
                min_bootstrap_p5=min_bootstrap_p5,
                min_walk_forward_q25=min_walk_forward_q25,
                min_loso_sharpe=min_loso_sharpe,
                max_drawdown=max_drawdown,
            )
        ]
        neighbor_pass_fraction = (len(passing_neighbors) / len(neighbors)) if neighbors else 0.0
        metrics = row_metrics(center)
        center_passes = row_passes_neighbor_gate(
            center,
            min_bootstrap_p5=min_bootstrap_p5,
            min_walk_forward_q25=min_walk_forward_q25,
            min_loso_sharpe=min_loso_sharpe,
            max_drawdown=max_drawdown,
        )
        if not center_passes:
            decision = "reject_center_metrics"
        elif len(neighbors) < min_neighbor_count:
            decision = "manual_review_insufficient_neighbors"
        elif neighbor_pass_fraction >= min_neighbor_pass_fraction:
            decision = "shortlist_plateau_candidate"
        else:
            decision = "reject_isolated_or_fragile"
        out.append(
            {
                "decision": decision,
                "score": quality_score(metrics, neighbor_pass_fraction, len(neighbors)),
                "artifact": artifact["artifact"],
                "tasks": artifact["tasks"],
                "statuses": artifact["statuses"],
                "kind": payload.get("kind"),
                "symbols": payload.get("symbols") or (payload.get("data") or {}).get("symbols") or [],
                "data": {
                    "fingerprint": (payload.get("data") or {}).get("fingerprint"),
                    "first_dt": (payload.get("data") or {}).get("first_dt"),
                    "last_dt": (payload.get("data") or {}).get("last_dt"),
                    "rows": (payload.get("data") or {}).get("rows"),
                },
                "train_window": payload.get("train_window") or {},
                "summary": payload.get("summary") or {},
                "config": canonical_config(center.get("config")),
                "config_signature": config_signature(payload.get("kind"), payload.get("symbols"), center.get("config") or {}),
                "family_key": family_key(artifact["artifact"], payload.get("kind"), center.get("config") or {}),
                "metrics": metrics,
                "neighbor_stability": {
                    "neighbor_count": len(neighbors),
                    "passing_neighbor_count": len(passing_neighbors),
                    "neighbor_pass_fraction": neighbor_pass_fraction,
                    "min_neighbor_pass_fraction": min_neighbor_pass_fraction,
                    "min_neighbor_count": min_neighbor_count,
                    "max_axis_distance": max_axis_distance,
                    "max_changed_axes": max_changed_axes,
                },
                "safety": {
                    "holdout_authorized": bool((payload.get("summary") or {}).get("holdout_authorized")),
                    "paper_trading_authorized": bool((payload.get("summary") or {}).get("paper_trading_authorized")),
                    "live_trading_authorized": bool((payload.get("summary") or {}).get("live_trading_authorized")),
                },
            }
        )
    return out


def apply_family_status(rows: list[dict[str, Any]], statuses: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        enriched = dict(row)
        status = statuses.get(str(row.get("family_key")))
        if status:
            enriched["family_status"] = status
            if status_blocks_family(status) and row.get("decision") == "shortlist_plateau_candidate":
                enriched["decision"] = "reject_family_status"
                enriched["rejected_by_family_status"] = True
        out.append(enriched)
    return out


def apply_family_cap(rows: list[dict[str, Any]], max_per_family: int) -> list[dict[str, Any]]:
    if max_per_family <= 0:
        return rows
    counts: dict[str, int] = {}
    out = []
    for row in rows:
        enriched = dict(row)
        key = str(row.get("family_key") or "")
        if row.get("decision") == "shortlist_plateau_candidate" and key:
            counts[key] = counts.get(key, 0) + 1
            enriched["family_rank"] = counts[key]
            if counts[key] > max_per_family:
                enriched["decision"] = "reject_family_cap"
                enriched["rejected_by_family_cap"] = True
        out.append(enriched)
    return out


def sort_ranked(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            0 if row.get("decision") == "shortlist_plateau_candidate" else 1,
            -float(row.get("score") or -999.0),
            str(row.get("artifact")),
        ),
    )


def dedupe_ranked(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_signature: dict[str, dict[str, Any]] = {}
    passthrough = []
    for row in rows:
        signature = row.get("config_signature")
        if not signature:
            passthrough.append(row)
            continue
        current = by_signature.get(str(signature))
        if current is None or float(row.get("score") or -999.0) > float(current.get("score") or -999.0):
            by_signature[str(signature)] = row
    return sort_ranked([*by_signature.values(), *passthrough])


def build_triage(
    state_path: Path,
    base: Path,
    *,
    include_data_drift: bool = False,
    min_neighbor_pass_fraction: float = 0.60,
    min_neighbor_count: int = 3,
    max_axis_distance: int = 1,
    max_changed_axes: int = 2,
    min_bootstrap_p5: float = 0.50,
    min_walk_forward_q25: float = 0.0,
    min_loso_sharpe: float = 0.0,
    max_drawdown: float = 0.30,
    family_status_path: Path | None = None,
    max_per_family: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    state = read_json(state_path)
    family_status = load_family_status(family_status_path)
    artifacts, excluded_data_drift = artifact_status_rows(state, base, include_data_drift)
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        rows.extend(
            triage_artifact(
                artifact,
                min_neighbor_pass_fraction=min_neighbor_pass_fraction,
                min_neighbor_count=min_neighbor_count,
                max_axis_distance=max_axis_distance,
                max_changed_axes=max_changed_axes,
                min_bootstrap_p5=min_bootstrap_p5,
                min_walk_forward_q25=min_walk_forward_q25,
                min_loso_sharpe=min_loso_sharpe,
                max_drawdown=max_drawdown,
            )
        )
    ranked = dedupe_ranked(rows)
    ranked = apply_family_status(ranked, family_status)
    ranked = apply_family_cap(ranked, max_per_family)
    ranked = sort_ranked(ranked)
    shortlist = [row for row in ranked if row.get("decision") == "shortlist_plateau_candidate"]
    return {
        "kind": "v9_train_only_candidate_triage_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_state": str(state_path),
        "holdout_accessed": False,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "thresholds": {
            "include_data_drift": include_data_drift,
            "min_neighbor_pass_fraction": min_neighbor_pass_fraction,
            "min_neighbor_count": min_neighbor_count,
            "max_axis_distance": max_axis_distance,
            "max_changed_axes": max_changed_axes,
            "min_bootstrap_p5": min_bootstrap_p5,
            "min_walk_forward_q25": min_walk_forward_q25,
            "min_loso_sharpe": min_loso_sharpe,
            "max_drawdown": max_drawdown,
            "family_status_path": str(family_status_path) if family_status_path else None,
            "max_per_family": max_per_family,
        },
        "summary": {
            "state_candidates": len(state.get("candidates_found", [])),
            "candidate_artifacts_considered": len(artifacts),
            "excluded_data_drift_candidates": excluded_data_drift,
            "ranked_centers": len(ranked),
            "shortlist_count": len(shortlist),
            "decision_counts": decision_counts(ranked),
            "family_status_entries": len(family_status),
            "family_status_rejections": sum(1 for row in ranked if row.get("rejected_by_family_status")),
            "family_cap_rejections": sum(1 for row in ranked if row.get("rejected_by_family_cap")),
            "shortlist_family_count": len({row.get("family_key") for row in shortlist}),
        },
        "recommendation": {
            "next_step": "Human-review shortlist_plateau_candidate rows before any holdout authorization.",
            "do_not_run_until": "holdout_authorized=true",
            "paper_live_production": "not authorized by this train-only triage",
        },
        "ranked_candidates": ranked[:limit],
    }


def decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("decision"))
        counts[decision] = counts.get(decision, 0) + 1
    return dict(sorted(counts.items()))


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def compact_config(config: dict[str, Any]) -> str:
    keys = ("k", "lookback_h", "market_filter_h", "rebalance_h", "vol_target_ann", "score_mode", "skip_h")
    return ",".join(f"{key}={config.get(key)}" for key in keys if key in config)


def format_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    thresholds = report["thresholds"]
    lines = [
        "# TRAIN_ONLY_CANDIDATE_TRIAGE",
        "",
        f"created_at: `{report['created_at']}`",
        f"source_state: `{report['source_state']}`",
        f"holdout_accessed: `{report['holdout_accessed']}`",
        f"holdout_authorized: `{report['holdout_authorized']}`",
        f"paper_trading_authorized: `{report['paper_trading_authorized']}`",
        f"live_trading_authorized: `{report['live_trading_authorized']}`",
        "",
        "## Summary",
        "",
        f"- state_candidates: `{summary['state_candidates']}`",
        f"- candidate_artifacts_considered: `{summary['candidate_artifacts_considered']}`",
        f"- excluded_data_drift_candidates: `{summary['excluded_data_drift_candidates']}`",
        f"- ranked_centers: `{summary['ranked_centers']}`",
        f"- shortlist_count: `{summary['shortlist_count']}`",
        f"- shortlist_family_count: `{summary.get('shortlist_family_count', 0)}`",
        f"- family_status_entries: `{summary.get('family_status_entries', 0)}`",
        f"- family_status_rejections: `{summary.get('family_status_rejections', 0)}`",
        f"- family_cap_rejections: `{summary.get('family_cap_rejections', 0)}`",
        f"- decision_counts: `{json.dumps(summary['decision_counts'], sort_keys=True)}`",
        "",
        "## Thresholds",
        "",
        f"- neighbor_pass_fraction >= `{fmt(thresholds['min_neighbor_pass_fraction'])}`",
        f"- neighbor_count >= `{thresholds['min_neighbor_count']}`",
        f"- bootstrap_30d_sharpe_p5 >= `{fmt(thresholds['min_bootstrap_p5'])}`",
        f"- walk_forward_q25 >= `{fmt(thresholds['min_walk_forward_q25'])}`",
        f"- leave_one_symbol_min_sharpe >= `{fmt(thresholds['min_loso_sharpe'])}`",
        f"- max_drawdown <= `{fmt(thresholds['max_drawdown'])}`",
        f"- max_per_family: `{thresholds.get('max_per_family', 0)}`",
        f"- family_status_path: `{thresholds.get('family_status_path')}`",
        "",
        "## Ranked Candidates",
        "",
        "| rank | decision | score | family rank | neighbor pass | sharpe40 | boot40 | wf q25 | loso sharpe | config | artifact |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for idx, row in enumerate(report.get("ranked_candidates", []), 1):
        metrics = row.get("metrics") or {}
        stability = row.get("neighbor_stability") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    str(row.get("decision")),
                    fmt(row.get("score")),
                    fmt(row.get("family_rank"), 0),
                    f"{stability.get('passing_neighbor_count', 0)}/{stability.get('neighbor_count', 0)} ({fmt(stability.get('neighbor_pass_fraction'))})",
                    fmt(metrics.get("sharpe40")),
                    fmt(metrics.get("bootstrap_p5_40")),
                    fmt(metrics.get("walk_forward_q25")),
                    fmt(metrics.get("leave_one_symbol_min_sharpe")),
                    f"`{compact_config(row.get('config') or {})}`",
                    f"`{row.get('artifact')}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This is train-only triage. It does not read holdout data and does not authorize paper, live, or production trading.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank train-only candidates by existing artifact neighborhood robustness")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--base", default=".")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--include-data-drift", action="store_true")
    parser.add_argument("--min-neighbor-pass-fraction", type=float, default=0.60)
    parser.add_argument("--min-neighbor-count", type=int, default=3)
    parser.add_argument("--max-axis-distance", type=int, default=1)
    parser.add_argument("--max-changed-axes", type=int, default=2)
    parser.add_argument("--min-bootstrap-p5", type=float, default=0.50)
    parser.add_argument("--min-walk-forward-q25", type=float, default=0.0)
    parser.add_argument("--min-loso-sharpe", type=float, default=0.0)
    parser.add_argument("--max-drawdown", type=float, default=0.30)
    parser.add_argument("--family-status", default="")
    parser.add_argument("--max-per-family", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    base = Path(args.base)
    report = build_triage(
        resolve_path(args.state, base),
        base,
        include_data_drift=args.include_data_drift,
        min_neighbor_pass_fraction=args.min_neighbor_pass_fraction,
        min_neighbor_count=args.min_neighbor_count,
        max_axis_distance=args.max_axis_distance,
        max_changed_axes=args.max_changed_axes,
        min_bootstrap_p5=args.min_bootstrap_p5,
        min_walk_forward_q25=args.min_walk_forward_q25,
        min_loso_sharpe=args.min_loso_sharpe,
        max_drawdown=args.max_drawdown,
        family_status_path=resolve_path(args.family_status, base) if args.family_status else None,
        max_per_family=args.max_per_family,
        limit=args.limit,
    )
    out_json = resolve_path(args.out_json, base)
    out_md = resolve_path(args.out_md, base)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    out_md.write_text(format_markdown(report))


if __name__ == "__main__":
    main()
