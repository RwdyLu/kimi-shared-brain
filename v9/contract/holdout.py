from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.v9_train_only_candidate_triage import all_rows, row_metrics
from scripts.v9_train_only_holdout_batch import run_candidate_audit
from v9.contract.triage import (
    atomic_write_json,
    build_manual_review_queue,
    candidate_ids_for_record,
    canonical_sha1,
    entry_ids,
    read_json,
)
from v9.research.family_registry import family_fingerprint


AuditCandidate = Callable[[dict[str, Any]], dict[str, Any]]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_authorizations(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    rows = payload.get("authorizations") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("holdout authorizations must be a list or an object with authorizations")
    return [dict(row) for row in rows]


def empty_ledger() -> dict[str, Any]:
    return {
        "kind": "v9_holdout_ledger_v1",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "entries": [],
    }


def load_ledger(path: Path) -> dict[str, Any]:
    ledger = read_json(path)
    if not ledger:
        return empty_ledger()
    ledger.setdefault("kind", "v9_holdout_ledger_v1")
    ledger.setdefault("entries", [])
    return ledger


def resolve_path(base: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def queue_for_validated_state(candidates: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compatible = []
    for record in candidates:
        row = dict(record)
        if row.get("status") == "validated_train_only":
            row["status"] = "manual_review_required"
        compatible.append(row)
    return build_manual_review_queue(compatible, task_results=results)


def candidate_lookup(candidates: list[dict[str, Any]]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for idx, record in enumerate(candidates):
        for candidate_id in candidate_ids_for_record(record):
            lookup.setdefault(candidate_id, idx)
    return lookup


def queue_lookup(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for candidate_id in entry_ids(entry):
            lookup.setdefault(candidate_id, entry)
    return lookup


def result_lookup(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for result in results:
        for key in ("task", "output_json"):
            value = result.get(key)
            if value:
                lookup.setdefault(str(value), result)
    return lookup


def parse_iso_date_prefix(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def train_window_disjoint(
    record: dict[str, Any],
    results_by_key: dict[str, dict[str, Any]],
    holdout_start: str,
) -> tuple[bool, str]:
    result = (
        results_by_key.get(str(record.get("task") or ""))
        or results_by_key.get(str(record.get("output_json") or ""))
        or {}
    )
    planned = result.get("planned_task") or record.get("planned_task") or {}
    train_end = parse_iso_date_prefix(planned.get("train_end"))
    embargo_start = parse_iso_date_prefix(planned.get("embargo_start"))
    holdout_start_date = parse_iso_date_prefix(holdout_start)
    if train_end is None or embargo_start is None or holdout_start_date is None:
        return False, "missing_train_window"
    if train_end >= holdout_start_date or embargo_start > holdout_start_date:
        return False, "train_holdout_overlap"
    return True, ""


def accepted_row(payload: dict[str, Any]) -> dict[str, Any]:
    for row in all_rows(payload):
        if row.get("advance_passed"):
            return row
    return {}


def artifact_kind(payload: dict[str, Any], artifact: str) -> str:
    text = f"{payload.get('kind', '')} {artifact}".lower()
    if "tsmom" in text:
        return "tsmom"
    if "xsec_ohlcv" in text:
        return "xsec_ohlcv"
    return "unsupported"


def holdout_candidate_from_record(record: dict[str, Any], artifact: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(artifact.read_text())
    row = accepted_row(payload)
    config = dict(row.get("config") or {})
    candidate = {
        "artifact": str(artifact),
        "kind": payload.get("kind"),
        "score": record.get("score"),
        "metrics": row_metrics(row) if row else {},
        "config": config,
        "lookbacks_h": row.get("lookbacks_h") or [],
        "statuses": [record.get("status")],
        "tasks": [record.get("task")],
    }
    return candidate, family_fingerprint(payload, str(artifact))


def first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def cost_metrics(report: dict[str, Any]) -> dict[str, Any]:
    costs = report.get("costs") or {}
    cost40 = costs.get("40bps") or {}
    cost20 = costs.get("20bps") or {}
    return {
        "sharpe": first_number(cost40.get("sharpe"), cost20.get("sharpe")),
        "total_return": first_number(cost40.get("total_return"), cost20.get("total_return")),
        "max_drawdown": first_number(cost20.get("max_drawdown"), cost40.get("max_drawdown")),
    }


def holdout_decision(audit: dict[str, Any], criteria: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    evidence = dict(audit.get("promotion_evidence") or {})
    metrics = cost_metrics(audit)
    train_sharpe = first_number(evidence.get("train_sharpe"))
    holdout_sharpe = first_number(evidence.get("holdout_sharpe"), metrics.get("sharpe"))
    holdout_return = first_number(evidence.get("holdout_return"), metrics.get("total_return"))
    holdout_dd = first_number(evidence.get("holdout_drawdown"), metrics.get("max_drawdown"))
    ratio = first_number(evidence.get("holdout_sharpe_decay_ratio"))
    if ratio is None and train_sharpe is not None and holdout_sharpe is not None and train_sharpe > 0:
        ratio = holdout_sharpe / train_sharpe
    min_ratio = float(criteria["min_holdout_sharpe_ratio_vs_train"])
    max_dd = float(criteria["max_dd"])
    min_return = float(criteria.get("min_holdout_return", 0.0))
    min_sharpe = float(criteria.get("min_holdout_sharpe", 0.0))
    checks = {
        "holdout_decision_promising": audit.get("holdout_decision") == "holdout_promising_manual_review_required",
        "holdout_sharpe_ratio_ge_min": ratio is not None and ratio >= min_ratio,
        "holdout_sharpe_gt_min": holdout_sharpe is not None and holdout_sharpe > min_sharpe,
        "holdout_return_gt_min": holdout_return is not None and holdout_return > min_return,
        "holdout_drawdown_le_max": holdout_dd is not None and holdout_dd <= max_dd,
    }
    decision = "validated_holdout" if all(checks.values()) else "rejected_holdout"
    return decision, {
        "criteria": criteria,
        "checks": checks,
        "train_sharpe": train_sharpe,
        "holdout_sharpe": holdout_sharpe,
        "holdout_sharpe_ratio_vs_train": ratio,
        "holdout_return": holdout_return,
        "holdout_drawdown": holdout_dd,
    }


def consumed_candidate_ids(ledger: dict[str, Any]) -> set[str]:
    ids = set()
    for entry in ledger.get("entries") or []:
        for value in entry.get("candidate_ids") or []:
            ids.add(str(value))
    return ids


def consumed_family_count(ledger: dict[str, Any], family: str) -> int:
    return sum(1 for entry in ledger.get("entries") or [] if entry.get("family_fingerprint") == family)


def validate_authorization(raw: dict[str, Any]) -> tuple[bool, str]:
    if raw.get("decision") != "authorize_holdout":
        return False, "invalid_decision"
    if not raw.get("candidate_id"):
        return False, "missing_candidate_id"
    if not raw.get("evidence_sha1"):
        return False, "missing_evidence_sha1"
    if not raw.get("authorized_by"):
        return False, "missing_authorized_by"
    criteria = raw.get("criteria")
    if not isinstance(criteria, dict):
        return False, "missing_criteria"
    if criteria.get("min_holdout_sharpe_ratio_vs_train") is None:
        return False, "missing_min_holdout_sharpe_ratio_vs_train"
    if criteria.get("max_dd") is None:
        return False, "missing_max_dd"
    return True, ""


def append_consumed_ledger_entry(
    ledger_path: Path,
    ledger: dict[str, Any],
    entry: dict[str, Any],
) -> None:
    ledger.setdefault("entries", []).append(entry)
    ledger["updated_at"] = now_utc()
    atomic_write_json(ledger_path, ledger)


def update_ledger_entry(ledger_path: Path, ledger: dict[str, Any], ledger_id: str, updates: dict[str, Any]) -> None:
    for entry in ledger.get("entries") or []:
        if entry.get("ledger_id") == ledger_id:
            entry.update(updates)
            break
    ledger["updated_at"] = now_utc()
    atomic_write_json(ledger_path, ledger)


def run_authorized_holdout(
    *,
    state_path: Path,
    authorizations_path: Path,
    ledger_path: Path,
    base: Path = Path("."),
    cache_dir: Path = Path("data/binance_public_cache"),
    reviews_dir: Path = Path("artifacts/v9/reviews"),
    holdout_start: str = "2024-07-01",
    holdout_end: str = "2026-05-31 23:59:59",
    costs_bps: tuple[float, ...] = (20.0, 40.0, 60.0, 80.0),
    bootstrap_iterations: int = 100,
    post_holdout_probe_start: str = "2026-06-01",
    post_holdout_probe_end: str = "now",
    max_holdouts_per_family: int = 2,
    min_post_holdout_active_rebalances: int = 1,
    min_post_holdout_time_in_market: float = 0.0,
    audit_candidate: AuditCandidate | None = None,
) -> dict[str, Any]:
    state = read_json(state_path) or {}
    candidates = list(state.get("candidates_found") or [])
    results = list(state.get("task_results") or [])
    authorizations = load_authorizations(authorizations_path)
    ledger = load_ledger(ledger_path)
    queue = queue_for_validated_state(candidates, results)
    by_candidate_id = candidate_lookup(candidates)
    by_queue_id = queue_lookup(queue)
    by_result_key = result_lookup(results)
    consumed_ids = consumed_candidate_ids(ledger)
    now = now_utc()
    rows = []
    applied_count = 0

    if audit_candidate is None:
        protocol_id = "AUTHORIZED_HOLDOUT_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        def audit_candidate(row: dict[str, Any]) -> dict[str, Any]:
            return run_candidate_audit(
                row,
                base=base,
                reviews_dir=reviews_dir,
                protocol_id=protocol_id,
                cache_dir=cache_dir,
                holdout_start=holdout_start,
                holdout_end=holdout_end,
                costs_bps=costs_bps,
                bootstrap_iterations=bootstrap_iterations,
                min_decay_ratio=float(row["authorization_criteria"]["min_holdout_sharpe_ratio_vs_train"]),
                post_holdout_probe_start=post_holdout_probe_start,
                post_holdout_probe_end=post_holdout_probe_end,
                min_post_holdout_active_rebalances=min_post_holdout_active_rebalances,
                min_post_holdout_time_in_market=min_post_holdout_time_in_market,
            )

    for raw in authorizations:
        candidate_id = str(raw.get("candidate_id") or "")
        row = {
            "candidate_id": candidate_id,
            "decision": raw.get("decision"),
            "applied": False,
            "reason": "",
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }
        ok, reason = validate_authorization(raw)
        if not ok:
            row["reason"] = reason
            rows.append(row)
            continue
        if candidate_id in consumed_ids:
            row["reason"] = "candidate_already_consumed"
            rows.append(row)
            continue

        queue_entry = by_queue_id.get(candidate_id)
        record_idx = by_candidate_id.get(candidate_id)
        if record_idx is None and queue_entry:
            for alternate_id in entry_ids(queue_entry):
                record_idx = by_candidate_id.get(alternate_id)
                if record_idx is not None:
                    break
        if record_idx is None:
            row["reason"] = "unknown_candidate"
            rows.append(row)
            continue
        record = candidates[record_idx]
        row["current_status"] = record.get("status")
        if record.get("status") != "validated_train_only":
            row["reason"] = "not_validated_train_only"
            rows.append(row)
            continue
        if not queue_entry:
            row["reason"] = "not_in_review_evidence_queue"
            rows.append(row)
            continue
        row["expected_evidence_sha1"] = queue_entry.get("evidence_sha1")
        if raw.get("evidence_sha1") != queue_entry.get("evidence_sha1"):
            row["reason"] = "evidence_mismatch"
            rows.append(row)
            continue
        disjoint, disjoint_reason = train_window_disjoint(record, by_result_key, holdout_start)
        if not disjoint:
            row["reason"] = disjoint_reason
            rows.append(row)
            continue

        record_ids = candidate_ids_for_record(record)
        ledger_candidate_ids = set(record_ids)
        ledger_candidate_ids.add(candidate_id)
        if consumed_ids & ledger_candidate_ids:
            row["reason"] = "candidate_already_consumed"
            rows.append(row)
            continue
        output_json = record.get("output_json")
        if not output_json:
            row["reason"] = "missing_output_json"
            rows.append(row)
            continue
        artifact = resolve_path(base, str(output_json))
        if not artifact.exists():
            row["reason"] = "artifact_missing"
            row["artifact"] = str(artifact)
            rows.append(row)
            continue
        holdout_candidate, family = holdout_candidate_from_record(record, artifact)
        if artifact_kind(json.loads(artifact.read_text()), str(artifact)) == "unsupported":
            row["reason"] = "unsupported_artifact_kind"
            rows.append(row)
            continue
        if consumed_family_count(ledger, family) >= int(max_holdouts_per_family):
            row["reason"] = "family_budget_exhausted"
            row["family_fingerprint"] = family
            rows.append(row)
            continue

        ledger_id = canonical_sha1(
            {
                "candidate_id": candidate_id,
                "evidence_sha1": raw.get("evidence_sha1"),
                "family_fingerprint": family,
                "authorized_by": raw.get("authorized_by"),
                "consumed_at": now,
            }
        )[:20]
        ledger_entry = {
            "ledger_id": ledger_id,
            "consumed_at": now,
            "status": "holdout_consumed_before_audit",
            "candidate_id": candidate_id,
            "candidate_ids": sorted(ledger_candidate_ids),
            "task": record.get("task"),
            "output_json": str(artifact),
            "evidence_sha1": raw.get("evidence_sha1"),
            "authorized_by": raw.get("authorized_by"),
            "family_fingerprint": family,
            "criteria": raw.get("criteria"),
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }
        append_consumed_ledger_entry(ledger_path, ledger, ledger_entry)
        consumed_ids.update(ledger_candidate_ids)

        holdout_candidate["authorization_criteria"] = dict(raw["criteria"])
        audit = audit_candidate(holdout_candidate)
        new_status, decision_evidence = holdout_decision(audit, dict(raw["criteria"]))
        record["status"] = new_status
        record["holdout_reviewed_at"] = now_utc()
        record["holdout_authorized_by"] = raw.get("authorized_by")
        record["holdout_evidence_sha1"] = raw.get("evidence_sha1")
        record["holdout_ledger_id"] = ledger_id
        record["holdout_accessed"] = True
        record["holdout_authorized"] = False
        record["paper_trading_authorized"] = False
        record["live_trading_authorized"] = False
        record["holdout_decision_evidence"] = decision_evidence
        record["holdout_report_json"] = audit.get("holdout_report_json")
        record["holdout_report_text"] = audit.get("holdout_report_text")
        update_ledger_entry(
            ledger_path,
            ledger,
            ledger_id,
            {
                "status": new_status,
                "completed_at": now_utc(),
                "holdout_report_json": audit.get("holdout_report_json"),
                "holdout_report_text": audit.get("holdout_report_text"),
                "holdout_decision": audit.get("holdout_decision"),
                "promotion_decision": audit.get("promotion_decision"),
                "decision_evidence": decision_evidence,
            },
        )
        row.update(
            {
                "applied": True,
                "reason": "applied",
                "new_status": new_status,
                "ledger_id": ledger_id,
                "family_fingerprint": family,
                "holdout_authorized": True,
                "holdout_report_json": audit.get("holdout_report_json"),
            }
        )
        applied_count += 1
        rows.append(row)

    if applied_count:
        state["candidates_found"] = candidates
        state["candidates_found_total"] = len(candidates)
        state["holdout_review_updated_at"] = now_utc()
        state["holdout_authorized"] = False
        state["paper_trading_authorized"] = False
        state["live_trading_authorized"] = False
        atomic_write_json(state_path, state)

    return {
        "kind": "v9_authorized_holdout_report",
        "generated_at": now_utc(),
        "source_state": str(state_path),
        "authorizations_path": str(authorizations_path),
        "ledger_path": str(ledger_path),
        "authorization_count": len(authorizations),
        "applied_count": applied_count,
        "holdout_accessed": bool(applied_count),
        "holdout_authorized": bool(applied_count),
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "decisions": rows,
    }


def parse_costs(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Human-authorized one-shot holdout executor")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="consume explicit holdout authorizations and run one-shot holdout audits")
    run.add_argument("--state", default="state/v9_auto_research_state.json")
    run.add_argument("--authorizations", default="state/holdout_authorizations.json")
    run.add_argument("--ledger", default="state/holdout_ledger.json")
    run.add_argument("--base", default=".")
    run.add_argument("--cache-dir", default="data/binance_public_cache")
    run.add_argument("--reviews-dir", default="artifacts/v9/reviews")
    run.add_argument("--out", default="state/v9_holdout_report.json")
    run.add_argument("--holdout-start", default="2024-07-01")
    run.add_argument("--holdout-end", default="2026-05-31 23:59:59")
    run.add_argument("--post-holdout-probe-start", default="2026-06-01")
    run.add_argument("--post-holdout-probe-end", default="now")
    run.add_argument("--costs-bps", default="20,40,60,80")
    run.add_argument("--bootstrap-iterations", type=int, default=100)
    run.add_argument("--max-holdouts-per-family", type=int, default=2)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.command != "run":  # pragma: no cover
        raise SystemExit(f"unknown command: {args.command}")
    report = run_authorized_holdout(
        state_path=Path(args.state),
        authorizations_path=Path(args.authorizations),
        ledger_path=Path(args.ledger),
        base=Path(args.base),
        cache_dir=Path(args.cache_dir),
        reviews_dir=Path(args.reviews_dir),
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        costs_bps=parse_costs(args.costs_bps),
        bootstrap_iterations=args.bootstrap_iterations,
        post_holdout_probe_start=args.post_holdout_probe_start,
        post_holdout_probe_end=args.post_holdout_probe_end,
        max_holdouts_per_family=args.max_holdouts_per_family,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
