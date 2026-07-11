#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_train_only_candidate_triage import build_triage  # noqa: E402
from scripts.v9_tsmom_holdout_audit import build_report as build_tsmom_holdout_report  # noqa: E402
from scripts.v9_tsmom_holdout_audit import format_text as format_tsmom_holdout_text  # noqa: E402
from scripts.v9_xsec_ohlcv_holdout_audit import build_report as build_xsec_holdout_report  # noqa: E402
from scripts.v9_xsec_ohlcv_holdout_audit import format_text as format_xsec_holdout_text  # noqa: E402
from scripts.v9_xsec_paper_readiness_gate import shadow_oos_report as build_xsec_shadow_oos_report  # noqa: E402
from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import load_close_matrix as load_xsec_close_matrix  # noqa: E402


PROTOCOL_VERSION = "v2-active-paper-probe-20260711"


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_stem(value: str) -> str:
    stem = Path(value).stem
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in stem)[:160]


def candidate_hash(candidate: dict[str, Any]) -> str:
    payload = {
        "artifact": candidate.get("artifact"),
        "config": candidate.get("config") or {},
        "lookbacks_h": candidate.get("lookbacks_h") or [],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:10]


def artifact_kind(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("kind") or "").lower()
    artifact = str(candidate.get("artifact") or "").lower()
    if "tsmom" in kind or "tsmom" in artifact:
        return "tsmom"
    if "xsec_ohlcv" in kind or "xsec_ohlcv" in artifact:
        return "xsec_ohlcv"
    return "unsupported"


def first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def candidate_train_sharpe(candidate: dict[str, Any]) -> float | None:
    metrics = candidate.get("metrics") or {}
    return first_number(metrics.get("sharpe40"), metrics.get("sharpe20"))


def audit_sharpe(report: dict[str, Any]) -> float | None:
    costs = report.get("costs") or {}
    cost40 = costs.get("40bps") or {}
    cost20 = costs.get("20bps") or {}
    return first_number(cost40.get("sharpe"), cost20.get("sharpe"))


def audit_return(report: dict[str, Any]) -> float | None:
    costs = report.get("costs") or {}
    cost40 = costs.get("40bps") or {}
    cost20 = costs.get("20bps") or {}
    return first_number(cost40.get("total_return"), cost20.get("total_return"))


def audit_drawdown(report: dict[str, Any]) -> float | None:
    costs = report.get("costs") or {}
    cost20 = costs.get("20bps") or {}
    cost40 = costs.get("40bps") or {}
    return first_number(cost20.get("max_drawdown"), cost40.get("max_drawdown"))


def decay_ratio(candidate: dict[str, Any], report: dict[str, Any]) -> float | None:
    train = candidate_train_sharpe(candidate)
    holdout = audit_sharpe(report)
    if train is None or holdout is None or train <= 0:
        return None
    return holdout / train


def resolve_time_text(value: str) -> str:
    if str(value).strip().lower() == "now":
        return now_utc()
    return value


def compact_post_holdout_probe(probe: dict[str, Any] | None) -> dict[str, Any] | None:
    if not probe:
        return None
    cost40 = ((probe.get("costs") or {}).get("40bps") or {})
    keep = (
        "sharpe",
        "daily_sharpe",
        "total_return",
        "max_drawdown",
        "rebalance_event_count",
        "active_rebalance_event_count",
        "time_in_market_frac",
        "avg_gross_exposure",
        "daily_turnover",
        "realized_daily_vol_ann",
    )
    return {
        "evaluation_start": probe.get("evaluation_start"),
        "latest_dt": probe.get("latest_dt"),
        "latest_rebalance_dt": probe.get("latest_rebalance_dt"),
        "latest_gross_exposure": probe.get("latest_gross_exposure"),
        "latest_weights": probe.get("latest_weights") or {},
        "reference_cost_bps": probe.get("reference_cost_bps"),
        "cost40": {key: cost40.get(key) for key in keep if key in cost40},
    }


def post_holdout_activity_checks(
    probe: dict[str, Any] | None,
    *,
    min_active_rebalances: int,
    min_time_in_market: float,
) -> dict[str, bool]:
    cost40 = ((probe or {}).get("costs") or {}).get("40bps") or {}
    time_in_market = float(cost40.get("time_in_market_frac") or 0.0)
    time_in_market_ok = (
        time_in_market > 0.0
        if float(min_time_in_market) <= 0.0
        else time_in_market >= float(min_time_in_market)
    )
    return {
        "post_holdout_probe_present": bool(probe),
        "post_holdout_active_rebalances_ge_min": int(cost40.get("active_rebalance_event_count") or 0)
        >= int(min_active_rebalances),
        "post_holdout_time_in_market_ge_min": time_in_market_ok,
    }


def build_xsec_post_holdout_probe(
    *,
    holdout_report: dict[str, Any],
    cache_dir: Path,
    warmup_start: str,
    evaluation_start: str,
    evaluation_end: str,
    costs_bps: tuple[float, ...],
) -> dict[str, Any]:
    end_text = resolve_time_text(evaluation_end)
    data = holdout_report.get("data") or {}
    symbols = tuple(data.get("symbols") or ())
    if not symbols:
        raise ValueError("xsec holdout report has no symbols for post-holdout probe")
    closes = load_xsec_close_matrix(
        cache_dir,
        symbols,
        utc_ts(warmup_start),
        utc_ts(end_text),
        utc_ts("2100-01-01"),
    )
    return build_xsec_shadow_oos_report(
        closes=closes,
        config=dict(holdout_report["target_config"]),
        evaluation_start=utc_ts(evaluation_start),
        costs_bps=costs_bps,
    )


def promotion_decision(
    candidate: dict[str, Any],
    report: dict[str, Any],
    *,
    min_decay_ratio: float,
    post_holdout_probe: dict[str, Any] | None = None,
    require_post_holdout_activity: bool = False,
    min_post_holdout_active_rebalances: int = 1,
    min_post_holdout_time_in_market: float = 0.0,
) -> tuple[str, dict[str, Any]]:
    ratio = decay_ratio(candidate, report)
    holdout_sharpe = audit_sharpe(report)
    holdout_return = audit_return(report)
    holdout_drawdown = audit_drawdown(report)
    checks: dict[str, bool] = {
        "holdout_decision_promising": str(report.get("decision")) == "holdout_promising_manual_review_required",
        "holdout_sharpe_decay_ge_min": ratio is not None and ratio >= min_decay_ratio,
        "holdout_sharpe_positive": holdout_sharpe is not None and holdout_sharpe > 0.0,
        "holdout_return_positive": holdout_return is not None and holdout_return > 0.0,
        "holdout_drawdown_le_25pct": holdout_drawdown is not None and holdout_drawdown <= 0.25,
    }
    holdout_checks_passed = all(checks.values())
    if require_post_holdout_activity:
        checks.update(
            post_holdout_activity_checks(
                post_holdout_probe,
                min_active_rebalances=min_post_holdout_active_rebalances,
                min_time_in_market=min_post_holdout_time_in_market,
            )
        )
    evidence = {
        "checks": checks,
        "train_sharpe": candidate_train_sharpe(candidate),
        "holdout_sharpe": holdout_sharpe,
        "holdout_sharpe_decay_ratio": ratio,
        "holdout_return": holdout_return,
        "holdout_drawdown": holdout_drawdown,
        "post_holdout_probe": compact_post_holdout_probe(post_holdout_probe),
    }
    if all(checks.values()):
        return "paper_candidate_manual_review_required", evidence
    if holdout_checks_passed and require_post_holdout_activity:
        return "holdout_promising_recently_inactive_manual_review_required", evidence
    return "holdout_failed_do_not_paper_trade", evidence


def status_allows_holdout(candidate: dict[str, Any]) -> bool:
    statuses = {str(status) for status in candidate.get("statuses") or []}
    if not statuses:
        return True
    if any("data_drift" in status or status.startswith("rejected") for status in statuses):
        return False
    return "manual_review_required" in statuses


def selection_tier(candidate: dict[str, Any]) -> int | None:
    decision = candidate.get("decision")
    if decision == "shortlist_plateau_candidate":
        return 0
    if decision == "manual_review_insufficient_neighbors":
        return 1
    return None


def select_candidates(triage_report: dict[str, Any], max_candidates: int) -> list[dict[str, Any]]:
    eligible = []
    for row in triage_report.get("ranked_candidates", []):
        tier = selection_tier(row)
        if tier is None or not status_allows_holdout(row):
            continue
        enriched = dict(row)
        enriched["holdout_selection_tier"] = tier
        enriched["holdout_selection_reason"] = (
            "primary_plateau_candidate" if tier == 0 else "fallback_insufficient_neighbors_candidate"
        )
        eligible.append(enriched)
    eligible.sort(key=lambda row: (int(row.get("holdout_selection_tier", 99)), -float(row.get("score") or -999.0), str(row.get("artifact"))))
    return eligible[:max(0, max_candidates)]


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("promotion_decision") or row.get("audit_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def run_candidate_audit(
    candidate: dict[str, Any],
    *,
    base: Path,
    reviews_dir: Path,
    protocol_id: str,
    cache_dir: Path,
    holdout_start: str,
    holdout_end: str,
    costs_bps: tuple[float, ...],
    bootstrap_iterations: int,
    min_decay_ratio: float,
    post_holdout_probe_start: str,
    post_holdout_probe_end: str,
    min_post_holdout_active_rebalances: int,
    min_post_holdout_time_in_market: float,
) -> dict[str, Any]:
    kind = artifact_kind(candidate)
    artifact = Path(str(candidate.get("artifact") or ""))
    artifact_path = artifact if artifact.is_absolute() else base / artifact
    stem = safe_stem(str(artifact))
    digest = candidate_hash(candidate)
    json_path = reviews_dir / f"{protocol_id}_{stem}_{digest}_holdout.json"
    text_path = reviews_dir / f"{protocol_id}_{stem}_{digest}_holdout.txt"
    post_holdout_probe = None
    if kind == "tsmom":
        report = build_tsmom_holdout_report(
            artifact=artifact_path,
            cache_dir=cache_dir,
            holdout_start=holdout_start,
            holdout_end=holdout_end,
            costs_bps=costs_bps,
            bootstrap_iterations=bootstrap_iterations,
            holdout_authorized=True,
            target_config=candidate.get("config") or None,
            target_lookbacks_h=candidate.get("lookbacks_h") or None,
        )
        text = format_tsmom_holdout_text(report)
    elif kind == "xsec_ohlcv":
        report = build_xsec_holdout_report(
            artifact=artifact_path,
            cache_dir=cache_dir,
            split="holdout",
            holdout_start=holdout_start,
            holdout_end=holdout_end,
            costs_bps=costs_bps,
            bootstrap_iterations=bootstrap_iterations,
            holdout_authorized=True,
            target_config=candidate.get("config") or None,
        )
        text = format_xsec_holdout_text(report)
        post_holdout_probe = build_xsec_post_holdout_probe(
            holdout_report=report,
            cache_dir=cache_dir,
            warmup_start=holdout_start,
            evaluation_start=post_holdout_probe_start,
            evaluation_end=post_holdout_probe_end,
            costs_bps=costs_bps,
        )
    else:
        return {
            "audit_status": "unsupported_artifact_kind",
            "artifact": str(candidate.get("artifact")),
            "artifact_kind": kind,
            "candidate": candidate,
        }

    write_json(report, json_path)
    write_text(text, text_path)
    decision, promotion = promotion_decision(
        candidate,
        report,
        min_decay_ratio=min_decay_ratio,
        post_holdout_probe=post_holdout_probe,
        require_post_holdout_activity=kind == "xsec_ohlcv",
        min_post_holdout_active_rebalances=min_post_holdout_active_rebalances,
        min_post_holdout_time_in_market=min_post_holdout_time_in_market,
    )
    return {
        "audit_status": "completed",
        "artifact": str(candidate.get("artifact")),
        "artifact_kind": kind,
        "candidate_score": candidate.get("score"),
        "candidate_metrics": candidate.get("metrics") or {},
        "candidate_config": candidate.get("config") or {},
        "holdout_report_json": str(json_path),
        "holdout_report_text": str(text_path),
        "holdout_decision": report.get("decision"),
        "post_holdout_probe": compact_post_holdout_probe(post_holdout_probe),
        "promotion_decision": decision,
        "promotion_evidence": promotion,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def build_protocol_from_triage(
    triage_report: dict[str, Any],
    *,
    max_candidates: int,
    holdout_authorized: bool,
    min_decay_ratio: float,
    audit_candidate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    selected = select_candidates(triage_report, max_candidates)
    if not holdout_authorized:
        return {
            "kind": "v9_train_only_holdout_batch_v1",
            "protocol_version": PROTOCOL_VERSION,
            "created_at": now_utc(),
            "holdout_accessed": False,
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "pre_registered_rules": {
                "candidate_source": "train_only_candidate_triage shortlist_plateau_candidate, falling back to manual_review_insufficient_neighbors when no plateau survives",
                "max_candidates": max_candidates,
                "min_holdout_sharpe_decay_ratio": min_decay_ratio,
                "paper_candidate_rule": (
                    "holdout promising, positive return, max drawdown <= 25%, holdout Sharpe decay ratio "
                    ">= threshold, and XSEC post-holdout paper probe has active exposure"
                ),
            },
            "triage_summary": triage_report.get("summary") or {},
            "selected_candidates": selected,
            "holdout_results": [],
            "summary": {
                "selected_count": len(selected),
                "holdout_completed_count": 0,
                "paper_candidate_count": 0,
                "status_counts": {},
            },
            "recommendation": "Dry run only. Re-run with --holdout-authorized to spend holdout once under this frozen protocol.",
        }

    results = []
    for candidate in selected:
        try:
            results.append(audit_candidate(candidate))
        except Exception as exc:  # pragma: no cover - defensive batch behavior.
            results.append(
                {
                    "audit_status": "error",
                    "artifact": str(candidate.get("artifact")),
                    "candidate": candidate,
                    "error": str(exc),
                }
            )
    paper_candidates = [row for row in results if row.get("promotion_decision") == "paper_candidate_manual_review_required"]
    return {
        "kind": "v9_train_only_holdout_batch_v1",
        "protocol_version": PROTOCOL_VERSION,
        "created_at": now_utc(),
        "holdout_accessed": True,
        "holdout_authorized": True,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "pre_registered_rules": {
            "candidate_source": "train_only_candidate_triage shortlist_plateau_candidate, falling back to manual_review_insufficient_neighbors when no plateau survives",
            "max_candidates": max_candidates,
            "min_holdout_sharpe_decay_ratio": min_decay_ratio,
            "paper_candidate_rule": (
                "holdout promising, positive return, max drawdown <= 25%, holdout Sharpe decay ratio "
                ">= threshold, and XSEC post-holdout paper probe has active exposure"
            ),
        },
        "triage_summary": triage_report.get("summary") or {},
        "selected_candidates": selected,
        "holdout_results": results,
        "summary": {
            "selected_count": len(selected),
            "holdout_completed_count": sum(1 for row in results if row.get("audit_status") == "completed"),
            "paper_candidate_count": len(paper_candidates),
            "status_counts": status_counts(results),
        },
        "recommendation": (
            "Move paper_candidate_manual_review_required rows to paper trading only after manual review of costs, fills, "
            "funding, and execution constraints. Live trading remains unauthorized."
            if paper_candidates
            else "No paper candidate survived this holdout batch. Do not paper trade these candidates."
        ),
    }


def format_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    rules = report.get("pre_registered_rules") or {}
    lines = [
        "# V9 Train-Only Holdout Batch",
        "",
        f"created_at: `{report.get('created_at')}`",
        f"protocol_version: `{report.get('protocol_version')}`",
        f"holdout_accessed: `{report.get('holdout_accessed')}`",
        f"holdout_authorized: `{report.get('holdout_authorized')}`",
        f"paper_trading_authorized: `{report.get('paper_trading_authorized')}`",
        f"live_trading_authorized: `{report.get('live_trading_authorized')}`",
        "",
        "## Pre-Registered Rules",
        "",
        f"- candidate_source: `{rules.get('candidate_source')}`",
        f"- max_candidates: `{rules.get('max_candidates')}`",
        f"- min_holdout_sharpe_decay_ratio: `{rules.get('min_holdout_sharpe_decay_ratio')}`",
        f"- paper_candidate_rule: `{rules.get('paper_candidate_rule')}`",
        "",
        "## Summary",
        "",
        f"- selected_count: `{summary.get('selected_count', 0)}`",
        f"- holdout_completed_count: `{summary.get('holdout_completed_count', 0)}`",
        f"- paper_candidate_count: `{summary.get('paper_candidate_count', 0)}`",
        f"- status_counts: `{json.dumps(summary.get('status_counts', {}), sort_keys=True)}`",
        "",
        "## Results",
        "",
        "| rank | promotion | holdout | decay | train sharpe | holdout sharpe | return | dd | active reb | time in mkt | artifact | report |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    rows = report.get("holdout_results") or []
    for idx, row in enumerate(rows, 1):
        evidence = row.get("promotion_evidence") or {}
        probe40 = ((evidence.get("post_holdout_probe") or {}).get("cost40") or {})
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    str(row.get("promotion_decision") or row.get("audit_status")),
                    str(row.get("holdout_decision") or ""),
                    fmt(evidence.get("holdout_sharpe_decay_ratio")),
                    fmt(evidence.get("train_sharpe")),
                    fmt(evidence.get("holdout_sharpe")),
                    fmt(evidence.get("holdout_return")),
                    fmt(evidence.get("holdout_drawdown")),
                    fmt(probe40.get("active_rebalance_event_count"), 0),
                    fmt(probe40.get("time_in_market_frac")),
                    f"`{row.get('artifact')}`",
                    f"`{row.get('holdout_report_text') or ''}`",
                ]
            )
            + " |"
        )
    if not rows:
        for idx, row in enumerate(report.get("selected_candidates") or [], 1):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(idx),
                        "dry_run_selected",
                        "",
                        "",
                        fmt(candidate_train_sharpe(row)),
                        "",
                        "",
                        "",
                        "",
                        "",
                        f"`{row.get('artifact')}`",
                        "",
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Recommendation", "", str(report.get("recommendation") or "")])
    return "\n".join(lines)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def write_validated_marker(report: dict[str, Any], marker_dir: Path) -> None:
    paper_candidates = [
        row for row in report.get("holdout_results", []) if row.get("promotion_decision") == "paper_candidate_manual_review_required"
    ]
    if not paper_candidates:
        return
    best = paper_candidates[0]
    marker = marker_dir / "FOUND_VALIDATED_CANDIDATE.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "FOUND_VALIDATED_CANDIDATE "
        f"{now_utc()} artifact={best.get('artifact')} "
        f"holdout_report={best.get('holdout_report_json')} "
        "paper_trading_authorized=False live_trading_authorized=False\n"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frozen batch holdout protocol for train-only V9 candidates")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--base", default=".")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--family-status", default="artifacts/v9/reviews/FAMILY_STATUS.json")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--state-out", default="state/v9_holdout_protocol_state.json")
    parser.add_argument("--marker-dir", default="state")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--min-decay-ratio", type=float, default=0.50)
    parser.add_argument("--holdout-start", default="2024-07-01")
    parser.add_argument("--holdout-end", default="2026-05-31 23:59:59")
    parser.add_argument("--post-holdout-probe-start", default="2026-06-01")
    parser.add_argument("--post-holdout-probe-end", default="now")
    parser.add_argument("--min-post-holdout-active-rebalances", type=int, default=1)
    parser.add_argument("--min-post-holdout-time-in-market", type=float, default=0.0)
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--holdout-authorized", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    base = Path(args.base)
    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = base / state_path
    family_status_path = Path(args.family_status)
    if not family_status_path.is_absolute():
        family_status_path = base / family_status_path
    if not family_status_path.exists():
        family_status_path = None
    costs = tuple(float(item.strip()) for item in args.costs_bps.split(",") if item.strip())
    protocol_id = "HOLDOUT_BATCH_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reviews_dir = base / "artifacts/v9/reviews"
    triage = build_triage(
        state_path=state_path,
        base=base,
        family_status_path=family_status_path,
        max_per_family=1,
        limit=max(args.max_candidates * 20, 200),
    )

    def audit_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        return run_candidate_audit(
            candidate,
            base=base,
            reviews_dir=reviews_dir,
            protocol_id=protocol_id,
            cache_dir=Path(args.cache_dir),
            holdout_start=args.holdout_start,
            holdout_end=args.holdout_end,
            costs_bps=costs,
            bootstrap_iterations=args.bootstrap_iterations,
            min_decay_ratio=args.min_decay_ratio,
            post_holdout_probe_start=args.post_holdout_probe_start,
            post_holdout_probe_end=args.post_holdout_probe_end,
            min_post_holdout_active_rebalances=args.min_post_holdout_active_rebalances,
            min_post_holdout_time_in_market=args.min_post_holdout_time_in_market,
        )

    report = build_protocol_from_triage(
        triage,
        max_candidates=args.max_candidates,
        holdout_authorized=args.holdout_authorized,
        min_decay_ratio=args.min_decay_ratio,
        audit_candidate=audit_candidate,
    )
    state_out = Path(args.state_out)
    if not state_out.is_absolute():
        state_out = base / state_out
    write_json(report, state_out)
    out_json = Path(args.out_json) if args.out_json else reviews_dir / f"{protocol_id}.json"
    out_md = Path(args.out_md) if args.out_md else reviews_dir / f"{protocol_id}.md"
    if not out_json.is_absolute():
        out_json = base / out_json
    if not out_md.is_absolute():
        out_md = base / out_md
    write_json(report, out_json)
    markdown = format_markdown(report)
    write_text(markdown, out_md)
    if args.holdout_authorized:
        marker_dir = Path(args.marker_dir)
        if not marker_dir.is_absolute():
            marker_dir = base / marker_dir
        write_validated_marker(report, marker_dir)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(markdown)


if __name__ == "__main__":
    main()
