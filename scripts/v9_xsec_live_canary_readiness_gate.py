#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_paper_readiness_gate import write_json, write_text  # noqa: E402
from scripts.v9_xsec_paper_shadow import (  # noqa: E402
    read_ledger_records,
    to_utc_timestamp,
    verify_ledger_chain,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def approval_subject(payload: dict[str, Any]) -> dict[str, Any]:
    subject = json.loads(canonical_json(payload))
    evidence = subject.get("evidence") or {}
    evidence.pop("data_freshness_status_age_hours", None)
    return subject


def number_or(value: Any, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return default


def ledger_wall_clock_age_days(chain: dict[str, Any]) -> float:
    first = chain.get("first_recorded_at")
    last = chain.get("last_recorded_at")
    if not first or not last:
        return 0.0
    return max(0.0, (to_utc_timestamp(str(last)) - to_utc_timestamp(str(first))).total_seconds() / 86400.0)


def normal_ledger_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("kind") == "xsec_paper_ledger_record_v1"]


def normal_ledger_wall_clock_age_days(records: list[dict[str, Any]]) -> float:
    normal = normal_ledger_records(records)
    if len(normal) < 2:
        return 0.0
    first = normal[0].get("recorded_at")
    last = normal[-1].get("recorded_at")
    if not first or not last:
        return 0.0
    return max(0.0, (to_utc_timestamp(str(last)) - to_utc_timestamp(str(first))).total_seconds() / 86400.0)


def count_duplicate_latest_dt_records(records: list[dict[str, Any]]) -> int:
    count = 0
    previous = None
    for record in normal_ledger_records(records):
        latest_dt = record.get("latest_dt")
        if latest_dt and latest_dt == previous:
            count += 1
        if latest_dt:
            previous = latest_dt
    return count


def count_weight_change_events(records: list[dict[str, Any]], min_abs_delta: float = 1e-9) -> int:
    count = 0
    previous: dict[str, float] | None = None
    previous_latest_dt = None
    for record in normal_ledger_records(records):
        latest_dt = record.get("latest_dt")
        if latest_dt and latest_dt == previous_latest_dt:
            continue
        current = {
            str(symbol): float(weight)
            for symbol, weight in (record.get("latest_weights") or {}).items()
        }
        if previous is not None:
            symbols = set(previous) | set(current)
            if any(abs(current.get(symbol, 0.0) - previous.get(symbol, 0.0)) > min_abs_delta for symbol in symbols):
                count += 1
        previous = current
        previous_latest_dt = latest_dt
    return count


def latest_normal_candidate_artifact(records: list[dict[str, Any]]) -> str | None:
    normal = normal_ledger_records(records)
    return str(normal[-1].get("candidate_artifact")) if normal and normal[-1].get("candidate_artifact") else None


def data_freshness_status_age_hours(status: dict[str, Any], now: str | None = None) -> float:
    updated_at = status.get("updated_at")
    if not updated_at:
        return float("inf")
    current = to_utc_timestamp(now or now_utc())
    return max(0.0, (current - to_utc_timestamp(str(updated_at))).total_seconds() / 3600.0)


def latest_paper_drawdown(shadow_state: dict[str, Any]) -> float:
    metrics = (((shadow_state.get("shadow") or {}).get("costs") or {}).get("40bps") or {})
    return number_or(metrics.get("max_drawdown"), 999.0)


def read_cost_values(path: Path, min_abs_weight_delta: float) -> list[float]:
    if not path.exists():
        return []
    values = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                delta = abs(float(row.get("target_weight_delta") or 0.0))
                cost = float(row.get("observed_cost_bps") or row.get("spread_bps") or 0.0)
            except ValueError:
                continue
            if delta >= min_abs_weight_delta and math.isfinite(cost):
                values.append(cost)
    return values


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(float(q) * len(ordered)) - 1))
    return float(ordered[idx])


def approval_matches(path: Path, unsigned_report_sha256: str, candidate_artifact: str | None) -> dict[str, Any]:
    approval = read_json(path)
    approved_hash = approval.get("approved_unsigned_report_sha256") or approval.get("approved_report_sha256")
    artifact_ok = not approval.get("candidate_artifact") or approval.get("candidate_artifact") == candidate_artifact
    return {
        "path": str(path),
        "present": bool(approval),
        "approved_unsigned_report_sha256": approved_hash,
        "candidate_artifact": approval.get("candidate_artifact"),
        "hash_matches": approved_hash == unsigned_report_sha256,
        "candidate_artifact_matches": bool(artifact_ok),
    }


def build_unsigned_report(
    *,
    paper_gate_state: dict[str, Any],
    shadow_state: dict[str, Any],
    ledger_path: Path,
    cost_evidence_csv: Path,
    data_freshness_status: dict[str, Any],
    min_wall_clock_weeks: int,
    min_rebalance_events: int,
    max_ledger_gap_hours: float,
    max_paper_drawdown: float,
    assumed_cost_bps: float,
    cost_percentile: float,
    min_abs_weight_delta: float,
    max_data_freshness_status_age_hours: float,
    max_duplicate_latest_dt_records: int,
) -> dict[str, Any]:
    chain = verify_ledger_chain(ledger_path)
    records = read_ledger_records(ledger_path) if chain.get("valid") else []
    wall_clock_days = normal_ledger_wall_clock_age_days(records)
    rebalances = count_weight_change_events(records, min_abs_delta=min_abs_weight_delta)
    duplicate_latest_dt_records = count_duplicate_latest_dt_records(records)
    cost_values = read_cost_values(cost_evidence_csv, min_abs_weight_delta=min_abs_weight_delta)
    observed_cost_pctl = percentile(cost_values, cost_percentile)
    paper_dd = latest_paper_drawdown(shadow_state)
    candidate_artifact = ((paper_gate_state.get("candidate") or {}).get("artifact"))
    latest_ledger_artifact = latest_normal_candidate_artifact(records)
    data_freshness_age_hours = data_freshness_status_age_hours(data_freshness_status)
    checks = {
        "paper_gate_authorized": bool(paper_gate_state.get("paper_trading_authorized")),
        "paper_shadow_complete_review_required": shadow_state.get("status")
        == "paper_complete_live_manual_review_required",
        "ledger_chain_valid": bool(chain.get("valid")),
        "ledger_wall_clock_age_ge_min_weeks": wall_clock_days >= float(min_wall_clock_weeks * 7),
        "ledger_max_gap_le_limit": float(chain.get("max_gap_sec") or 0.0) <= float(max_ledger_gap_hours * 3600.0),
        "ledger_duplicate_latest_dt_le_limit": duplicate_latest_dt_records <= int(max_duplicate_latest_dt_records),
        "ledger_rebalance_events_ge_min": rebalances >= int(min_rebalance_events),
        "paper_drawdown_le_max": paper_dd <= float(max_paper_drawdown),
        "observed_cost_samples_present": len(cost_values) > 0,
        "observed_cost_pctl_le_assumed": observed_cost_pctl is not None
        and observed_cost_pctl <= float(assumed_cost_bps),
        "candidate_artifact_matches": bool(candidate_artifact) and candidate_artifact == latest_ledger_artifact,
        "data_freshness_status_present": bool(data_freshness_status),
        "data_freshness_status_fresh": data_freshness_age_hours <= float(max_data_freshness_status_age_hours),
        "data_fresh": bool(data_freshness_status.get("data_fresh")),
        "live_still_not_authorized": not bool(shadow_state.get("live_trading_authorized")),
    }
    return {
        "kind": "xsec_live_canary_readiness_unsigned_v1",
        "sources": {
            "paper_gate_state": paper_gate_state.get("source_holdout_batch"),
            "shadow_state": shadow_state.get("source_gate"),
            "ledger_jsonl": str(ledger_path),
            "cost_evidence_csv": str(cost_evidence_csv),
            "data_freshness_status": data_freshness_status.get("updated_at"),
        },
        "candidate_artifact": candidate_artifact,
        "thresholds": {
            "min_wall_clock_weeks": min_wall_clock_weeks,
            "min_rebalance_events": min_rebalance_events,
            "max_ledger_gap_hours": max_ledger_gap_hours,
            "max_paper_drawdown": max_paper_drawdown,
            "assumed_cost_bps": assumed_cost_bps,
            "cost_percentile": cost_percentile,
            "min_abs_weight_delta": min_abs_weight_delta,
            "max_data_freshness_status_age_hours": max_data_freshness_status_age_hours,
            "max_duplicate_latest_dt_records": max_duplicate_latest_dt_records,
        },
        "evidence": {
            "ledger": chain,
            "ledger_wall_clock_days": wall_clock_days,
            "ledger_rebalance_events": rebalances,
            "ledger_duplicate_latest_dt_records": duplicate_latest_dt_records,
            "paper_drawdown_40bps": paper_dd,
            "observed_cost_sample_count": len(cost_values),
            "observed_cost_percentile_bps": observed_cost_pctl,
            "data_freshness_status_age_hours": data_freshness_age_hours,
            "data_freshness": data_freshness_status,
        },
        "checks_without_manual_approval": checks,
    }


def build_report(
    *,
    paper_gate_state_path: Path,
    shadow_state_path: Path,
    ledger_path: Path,
    cost_evidence_csv: Path,
    data_freshness_status_path: Path,
    approval_path: Path,
    min_wall_clock_weeks: int,
    min_rebalance_events: int,
    max_ledger_gap_hours: float,
    max_paper_drawdown: float,
    assumed_cost_bps: float,
    cost_percentile: float,
    min_abs_weight_delta: float,
    max_data_freshness_status_age_hours: float,
    max_duplicate_latest_dt_records: int,
) -> dict[str, Any]:
    paper_gate_state = read_json(paper_gate_state_path)
    shadow_state = read_json(shadow_state_path)
    data_freshness_status = read_json(data_freshness_status_path)
    unsigned = build_unsigned_report(
        paper_gate_state=paper_gate_state,
        shadow_state=shadow_state,
        ledger_path=ledger_path,
        cost_evidence_csv=cost_evidence_csv,
        data_freshness_status=data_freshness_status,
        min_wall_clock_weeks=min_wall_clock_weeks,
        min_rebalance_events=min_rebalance_events,
        max_ledger_gap_hours=max_ledger_gap_hours,
        max_paper_drawdown=max_paper_drawdown,
        assumed_cost_bps=assumed_cost_bps,
        cost_percentile=cost_percentile,
        min_abs_weight_delta=min_abs_weight_delta,
        max_data_freshness_status_age_hours=max_data_freshness_status_age_hours,
        max_duplicate_latest_dt_records=max_duplicate_latest_dt_records,
    )
    unsigned_hash = payload_sha256(approval_subject(unsigned))
    approval = approval_matches(approval_path, unsigned_hash, unsigned.get("candidate_artifact"))
    checks = dict(unsigned["checks_without_manual_approval"])
    checks["manual_approval_present"] = (
        approval["present"] and approval["hash_matches"] and approval["candidate_artifact_matches"]
    )
    all_without_manual = all(
        value for key, value in checks.items() if key != "manual_approval_present"
    )
    if all(checks.values()):
        decision = "live_canary_ready_manual_execution_required"
    elif all_without_manual:
        decision = "live_canary_manual_approval_required"
    else:
        decision = "live_canary_blocked"
    return {
        "kind": "xsec_live_canary_readiness_gate_v1",
        "created_at": now_utc(),
        "decision": decision,
        "live_canary_ready": decision == "live_canary_ready_manual_execution_required",
        "live_trading_authorized": False,
        "unsigned_report_sha256": unsigned_hash,
        "manual_approval": approval,
        "checks": checks,
        "unsigned_report": unsigned,
        "note": (
            "Readiness review only. This gate never enables live trading; a separate "
            "operator execution step must remain explicit."
        ),
    }


def format_text(report: dict[str, Any]) -> str:
    evidence = (report.get("unsigned_report") or {}).get("evidence") or {}
    lines = [
        f"decision={report.get('decision')}",
        f"live_canary_ready={report.get('live_canary_ready')}",
        f"live_trading_authorized={report.get('live_trading_authorized')}",
        f"unsigned_report_sha256={report.get('unsigned_report_sha256')}",
        "evidence="
        f"wall_clock_days:{fmt(evidence.get('ledger_wall_clock_days'))} "
        f"rebalances:{fmt(evidence.get('ledger_rebalance_events'), 0)} "
        f"paper_dd:{fmt(evidence.get('paper_drawdown_40bps'))} "
        f"cost_samples:{fmt(evidence.get('observed_cost_sample_count'), 0)} "
        f"cost_pctl_bps:{fmt(evidence.get('observed_cost_percentile_bps'))} "
        f"data_fresh:{(evidence.get('data_freshness') or {}).get('data_fresh')}",
        "checks=" + ",".join(f"{key}:{value}" for key, value in report.get("checks", {}).items()),
    ]
    return "\n".join(lines)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def write_marker(report: dict[str, Any], marker_dir: Path) -> None:
    marker_dir.mkdir(parents=True, exist_ok=True)
    if report.get("decision") == "live_canary_ready_manual_execution_required":
        name = "FOUND_LIVE_CANARY_READY.txt"
    elif report.get("decision") == "live_canary_manual_approval_required":
        name = "FOUND_LIVE_CANARY_REVIEW_REQUIRED.txt"
    else:
        return
    (marker_dir / name).write_text(
        f"{name.removesuffix('.txt')} {now_utc()} "
        f"unsigned_report_sha256={report['unsigned_report_sha256']} "
        "live_trading_authorized=False\n"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live-canary readiness gate for XSEC paper shadow.")
    parser.add_argument("--paper-gate-state", default="state/xsec_paper_readiness_gate_state.json")
    parser.add_argument("--shadow-state", default="state/xsec_paper_shadow_state.json")
    parser.add_argument("--ledger-jsonl", default="state/xsec_paper_ledger.jsonl")
    parser.add_argument("--cost-evidence-csv", default="artifacts/v9/paper/xsec_cost_evidence.csv")
    parser.add_argument("--data-freshness-status", default="artifacts/v9/watchdog/data_freshness_status.json")
    parser.add_argument("--approval", default="state/LIVE_CANARY_APPROVAL.json")
    parser.add_argument("--min-wall-clock-weeks", type=int, default=12)
    parser.add_argument("--min-rebalance-events", type=int, default=9)
    parser.add_argument("--max-ledger-gap-hours", type=float, default=48.0)
    parser.add_argument("--max-paper-drawdown", type=float, default=0.15)
    parser.add_argument("--assumed-cost-bps", type=float, default=40.0)
    parser.add_argument("--cost-percentile", type=float, default=0.90)
    parser.add_argument("--min-abs-weight-delta", type=float, default=1e-9)
    parser.add_argument("--max-data-freshness-status-age-hours", type=float, default=2.0)
    parser.add_argument("--max-duplicate-latest-dt-records", type=int, default=2)
    parser.add_argument("--out-json", default="state/xsec_live_canary_readiness_gate_state.json")
    parser.add_argument("--out-text", default="artifacts/v9/paper/xsec_live_canary_review.txt")
    parser.add_argument("--marker-dir", default="state")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = build_report(
        paper_gate_state_path=Path(args.paper_gate_state),
        shadow_state_path=Path(args.shadow_state),
        ledger_path=Path(args.ledger_jsonl),
        cost_evidence_csv=Path(args.cost_evidence_csv),
        data_freshness_status_path=Path(args.data_freshness_status),
        approval_path=Path(args.approval),
        min_wall_clock_weeks=args.min_wall_clock_weeks,
        min_rebalance_events=args.min_rebalance_events,
        max_ledger_gap_hours=args.max_ledger_gap_hours,
        max_paper_drawdown=args.max_paper_drawdown,
        assumed_cost_bps=args.assumed_cost_bps,
        cost_percentile=args.cost_percentile,
        min_abs_weight_delta=args.min_abs_weight_delta,
        max_data_freshness_status_age_hours=args.max_data_freshness_status_age_hours,
        max_duplicate_latest_dt_records=args.max_duplicate_latest_dt_records,
    )
    write_json(report, Path(args.out_json))
    write_text(format_text(report), Path(args.out_text))
    write_marker(report, Path(args.marker_dir))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
