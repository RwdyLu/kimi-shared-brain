from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from v9.research.candidate_dedupe import dedupe_candidates
from v9.research.multiplicity import multiplicity_evidence


REVIEW_DECISIONS = frozenset({"validate_train_only", "reject"})
REVIEW_STATUS_BY_DECISION = {
    "validate_train_only": "validated_train_only",
    "reject": "rejected_manual_review",
}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def canonical_sha1(value: Any) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def planned_window_key(row: dict[str, Any]) -> tuple[str, ...] | None:
    planned = row.get("planned_task") or {}
    keys = ("train_start", "train_end", "embargo_start")
    if not all(planned.get(key) for key in keys):
        return None
    scope = (
        str(planned.get("module") or ""),
        str(planned.get("preset") or ""),
        str(planned.get("cli_preset") or planned.get("preset") or ""),
    )
    return tuple(str(planned[key]) for key in keys) + scope


def family_from_task_name(task: str) -> str:
    parts = [part for part in str(task).split("_") if part]
    while parts and all(ch in "0123456789abcdef" for ch in parts[-1].lower()) and len(parts[-1]) >= 8:
        parts.pop()
    return "_".join(parts) or str(task)


def candidate_identity(record: dict[str, Any]) -> str:
    signature = record.get("signature")
    if signature:
        digest = hashlib.sha1(str(signature).encode("utf-8")).hexdigest()[:16]
        return f"signature:{digest}"
    fingerprint = record.get("fingerprint")
    if fingerprint:
        return f"fingerprint:{fingerprint}"
    return f"family:{family_from_task_name(str(record.get('task') or 'unknown'))}"


def result_maps(task_results: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[tuple[str, ...]]]:
    by_output = {
        str(row.get("output_json")): row
        for row in task_results
        if row.get("output_json")
    }
    drift_windows: set[tuple[str, ...]] = set()
    for row in task_results:
        status = str(row.get("candidate_status") or row.get("status") or row.get("multiplicity_decision") or "").lower()
        if "data_drift" not in status and "quarantined" not in status:
            continue
        key = planned_window_key(row)
        if key:
            drift_windows.add(key)
    return by_output, drift_windows


def effective_trials_for_evidence(result: dict[str, Any], payload: dict[str, Any] | None) -> int:
    selection_validation = (payload or {}).get("selection_validation") or {}
    for value in (
        result.get("effective_trials"),
        selection_validation.get("effective_trials"),
    ):
        if value is not None:
            return max(1, int(value or 0))
    prior_trials = result.get("prior_trials")
    n_configs = result.get("n_configs_tested")
    if prior_trials is not None or n_configs is not None:
        return max(1, int(prior_trials or 0) + int(n_configs or 0))
    prior_trials = selection_validation.get("prior_trials")
    n_configs = selection_validation.get("n_configs_tested") or selection_validation.get("n_configs")
    if prior_trials is not None or n_configs is not None:
        return max(1, int(prior_trials or 0) + int(n_configs or 0))
    return 1


def evidence_for_candidate(record: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    evidence = result.get("multiplicity_evidence") or {}
    metrics = evidence.get("metrics") or {}
    if metrics.get("adjusted_p_value") is not None:
        return evidence
    output_json = record.get("output_json") or result.get("output_json")
    if not output_json:
        return evidence
    payload = read_json(Path(str(output_json)))
    if not payload:
        return evidence
    return multiplicity_evidence(payload, total_trials=effective_trials_for_evidence(result, payload))


def score_candidate(record: dict[str, Any], result: dict[str, Any] | None, drift_windows: set[tuple[str, ...]]) -> dict[str, Any]:
    result = result or {}
    evidence = evidence_for_candidate(record, result)
    metrics = evidence.get("metrics") or {}
    adjusted_p = safe_float(metrics.get("adjusted_p_value"))
    z_score = safe_float(metrics.get("z_score"), 0.0) or 0.0
    sharpe = safe_float(metrics.get("sharpe"), 0.0) or 0.0
    max_drawdown = safe_float(metrics.get("max_drawdown"))
    p_score = -math.log10(max(adjusted_p, 1e-12)) if adjusted_p is not None else 0.0
    decision = str(result.get("multiplicity_decision") or evidence.get("decision") or "")
    survivor_bonus = 2.0 if decision == "multiplicity_survivor" else 0.0
    snapshot_bonus = 0.5 if (record.get("data_snapshot_fingerprint") or result.get("data_snapshot_fingerprint")) else 0.0
    key = planned_window_key(result)
    no_drift_history = bool(key and key not in drift_windows)
    no_drift_bonus = 0.25 if no_drift_history else 0.0
    drawdown_penalty = max(0.0, (max_drawdown or 0.0) - 0.25) if max_drawdown is not None else 0.0
    base_score = (
        1.50 * p_score
        + 0.20 * max(0.0, z_score)
        + 0.25 * max(0.0, sharpe)
        + survivor_bonus
        + snapshot_bonus
        + no_drift_bonus
        - 2.0 * drawdown_penalty
    )
    return {
        "base_score": round(base_score, 6),
        "adjusted_p_value": adjusted_p,
        "p_score": round(p_score, 6),
        "z_score": z_score,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "multiplicity_decision": decision,
        "survivor_bonus": survivor_bonus,
        "snapshot_bonus": snapshot_bonus,
        "no_drift_history": no_drift_history,
        "no_drift_bonus": no_drift_bonus,
        "drawdown_penalty": round(drawdown_penalty, 6),
    }


def build_manual_review_queue(
    candidates_found: list[dict[str, Any]] | None = None,
    state_path: Path | None = None,
    task_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    state = read_json(state_path) if state_path is not None else None
    candidates = list(candidates_found if candidates_found is not None else (state or {}).get("candidates_found", []))
    results = list(task_results if task_results is not None else (state or {}).get("task_results", []))
    by_output, drift_windows = result_maps(results)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in dedupe_candidates(candidates):
        if record.get("status") != "manual_review_required":
            continue
        groups.setdefault(candidate_identity(record), []).append(record)

    queue: list[dict[str, Any]] = []
    for identity, records in groups.items():
        scored_records = []
        for record in records:
            result = by_output.get(str(record.get("output_json") or ""))
            components = score_candidate(record, result, drift_windows)
            scored_records.append((components["base_score"], record, result or {}, components))
        scored_records.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("output_json") or ""),
                str(item[1].get("task") or ""),
            ),
            reverse=True,
        )
        base_score, best_record, best_result, components = scored_records[0]
        replication_count = len({str(row.get("output_json") or row.get("task") or idx) for idx, row in enumerate(records)})
        duplicate_count = sum(1 for row in records if row.get("duplicate_of"))
        replication_bonus = 0.75 * math.log1p(max(0, replication_count - 1))
        total_score = float(base_score) + replication_bonus
        entry = {
            "identity": identity,
            "score": round(total_score, 6),
            "score_components": {
                **components,
                "replication_count": int(replication_count),
                "duplicate_count": int(duplicate_count),
                "replication_bonus": round(replication_bonus, 6),
            },
            "task": best_record.get("task"),
            "output_json": best_record.get("output_json"),
            "output_md": best_record.get("output_md"),
            "fingerprint": best_record.get("fingerprint") or best_result.get("fingerprint"),
            "data_fingerprint": best_record.get("data_fingerprint") or best_result.get("data_fingerprint"),
            "data_snapshot_fingerprint": best_record.get("data_snapshot_fingerprint")
            or best_result.get("data_snapshot_fingerprint"),
            "status": best_record.get("status"),
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }
        entry["evidence_sha1"] = canonical_sha1(
            {
                "identity": entry["identity"],
                "output_json": entry.get("output_json"),
                "fingerprint": entry.get("fingerprint"),
                "data_fingerprint": entry.get("data_fingerprint"),
                "data_snapshot_fingerprint": entry.get("data_snapshot_fingerprint"),
                "score": entry.get("score"),
                "score_components": entry.get("score_components"),
                "status": entry.get("status"),
            }
        )
        if best_record.get("signature"):
            entry["signature"] = best_record["signature"]
        queue.append(entry)
    queue.sort(
        key=lambda row: (
            float(row.get("score") or 0.0),
            str(row.get("output_json") or ""),
            str(row.get("task") or ""),
        ),
        reverse=True,
    )
    return queue


def write_manual_review_queue(
    path: Path,
    candidates_found: list[dict[str, Any]] | None = None,
    state_path: Path | None = None,
    task_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    entries = build_manual_review_queue(candidates_found, state_path, task_results)
    payload = {
        "kind": "v9_manual_review_queue",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "entry_count": len(entries),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "entries": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def lookup_task_results(task_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for result in task_results:
        for key in ("task", "output_json"):
            value = result.get(key)
            if value:
                lookup.setdefault(str(value), result)
    return lookup


def parse_date_prefix(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        return pd.Timestamp(str(value)[:10], tz="UTC")
    except (TypeError, ValueError):
        return None


def train_window_review(planned: dict[str, Any], holdout_start: str) -> dict[str, Any]:
    train_end = parse_date_prefix(planned.get("train_end"))
    embargo_start = parse_date_prefix(planned.get("embargo_start"))
    holdout_start_ts = parse_date_prefix(holdout_start)
    if train_end is None or embargo_start is None or holdout_start_ts is None:
        status = "missing_train_window"
        disjoint = False
    elif train_end >= holdout_start_ts or embargo_start > holdout_start_ts:
        status = "train_holdout_overlap"
        disjoint = False
    else:
        status = "disjoint"
        disjoint = True
    return {
        "train_start": planned.get("train_start"),
        "train_end": planned.get("train_end"),
        "embargo_start": planned.get("embargo_start"),
        "holdout_start": holdout_start,
        "status": status,
        "disjoint": disjoint,
    }


def dossier_risk_flags(entry: dict[str, Any], result: dict[str, Any], window: dict[str, Any]) -> tuple[list[str], list[str]]:
    components = entry.get("score_components") or {}
    hard = []
    soft = []
    if not window.get("disjoint"):
        hard.append(str(window.get("status") or "missing_train_window"))
    if components.get("adjusted_p_value") is None:
        hard.append("missing_adjusted_p_value")
    elif float(components.get("adjusted_p_value") or 1.0) > 0.05:
        hard.append("weak_adjusted_p_value")
    if components.get("multiplicity_decision") != "multiplicity_survivor":
        hard.append("not_multiplicity_survivor")
    max_drawdown = safe_float(components.get("max_drawdown"))
    if max_drawdown is None:
        soft.append("missing_drawdown")
    elif max_drawdown > 0.25:
        hard.append("drawdown_above_25pct")
    elif max_drawdown > 0.20:
        soft.append("drawdown_above_20pct")
    if int(components.get("replication_count") or 0) < 2:
        soft.append("single_replication")
    if not entry.get("data_snapshot_fingerprint"):
        soft.append("missing_data_snapshot")
    if not components.get("no_drift_history"):
        soft.append("drift_history_missing_or_unclear")
    if str(result.get("status") or "") != "accepted_train_only_candidate_found":
        soft.append("source_result_not_accepted_train_only")
    return hard, soft


def dossier_rationale(entry: dict[str, Any], hard_flags: list[str], soft_flags: list[str]) -> str:
    components = entry.get("score_components") or {}
    return (
        "Reviewed train-only candidate. "
        f"score={entry.get('score')} "
        f"adjusted_p={components.get('adjusted_p_value')} "
        f"replication_count={components.get('replication_count')} "
        f"max_drawdown={components.get('max_drawdown')} "
        f"hard_flags={hard_flags} soft_flags={soft_flags}. "
        "Decision is human review only and does not authorize holdout, paper, or live trading."
    )


def build_manual_review_dossier(
    candidates_found: list[dict[str, Any]] | None = None,
    state_path: Path | None = None,
    task_results: list[dict[str, Any]] | None = None,
    *,
    limit: int = 5,
    holdout_start: str = "2024-07-01",
) -> dict[str, Any]:
    state = read_json(state_path) if state_path is not None else None
    candidates = list(candidates_found if candidates_found is not None else (state or {}).get("candidates_found", []))
    results = list(task_results if task_results is not None else (state or {}).get("task_results", []))
    queue = build_manual_review_queue(candidates, state_path, results)
    results_by_key = lookup_task_results(results)
    entries = []
    draft_decisions = []
    for rank, entry in enumerate(queue[: max(0, limit)], 1):
        result = results_by_key.get(str(entry.get("task") or "")) or results_by_key.get(str(entry.get("output_json") or "")) or {}
        planned = result.get("planned_task") or {}
        window = train_window_review(planned, holdout_start)
        hard_flags, soft_flags = dossier_risk_flags(entry, result, window)
        if hard_flags:
            recommended_decision = "reject"
        elif "missing_data_snapshot" in soft_flags:
            recommended_decision = "snapshot_revalidation_required"
        else:
            recommended_decision = "validate_train_only"
        rationale_template = dossier_rationale(entry, hard_flags, soft_flags)
        draft = {
            "candidate_id": entry.get("identity"),
            "evidence_sha1": entry.get("evidence_sha1"),
            "decision": None,
            "recommended_decision": recommended_decision,
            "reviewer": "",
            "rationale": "",
            "rationale_template": rationale_template,
            "human_must_fill_reviewer_and_rationale": True,
        }
        draft_decisions.append(draft)
        entries.append(
            {
                "rank": rank,
                "candidate_id": entry.get("identity"),
                "evidence_sha1": entry.get("evidence_sha1"),
                "recommended_decision": recommended_decision,
                "hard_flags": hard_flags,
                "soft_flags": soft_flags,
                "human_action_required": True,
                "draft_is_not_apply_ready": True,
                "train_window": window,
                "queue_entry": entry,
                "draft_decision": draft,
            }
        )
    return {
        "kind": "v9_manual_review_dossier",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source_state": str(state_path) if state_path else None,
        "holdout_start": holdout_start,
        "queue_entry_count": len(queue),
        "selected_count": len(entries),
        "human_action_required": True,
        "draft_is_not_apply_ready": True,
        "instructions": (
            "Review entries, then create control/review_decisions.json manually with reviewer and rationale. "
            "This dossier does not authorize holdout, paper trading, or live trading."
        ),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "entries": entries,
        "draft_decisions": draft_decisions,
    }


def format_manual_review_dossier_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# V9 Manual Review Dossier",
        "",
        f"generated_at: `{payload.get('generated_at')}`",
        f"source_state: `{payload.get('source_state')}`",
        f"queue_entry_count: `{payload.get('queue_entry_count')}`",
        f"selected_count: `{payload.get('selected_count')}`",
        f"holdout_authorized: `{payload.get('holdout_authorized')}`",
        f"paper_trading_authorized: `{payload.get('paper_trading_authorized')}`",
        f"live_trading_authorized: `{payload.get('live_trading_authorized')}`",
        "",
        (
            "This dossier is not apply-ready. A human must write "
            "`control/review_decisions.json` with a decision, reviewer, and rationale."
        ),
        "",
        "| rank | recommended | score | adjusted p | dd | rep | train window | hard flags | soft flags | candidate | evidence |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("entries") or []:
        entry = row.get("queue_entry") or {}
        comp = entry.get("score_components") or {}
        window = row.get("train_window") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("rank")),
                    str(row.get("recommended_decision")),
                    str(entry.get("score")),
                    str(comp.get("adjusted_p_value")),
                    str(comp.get("max_drawdown")),
                    str(comp.get("replication_count")),
                    str(window.get("status")),
                    ",".join(row.get("hard_flags") or []) or "none",
                    ",".join(row.get("soft_flags") or []) or "none",
                    f"`{row.get('candidate_id')}`",
                    f"`{row.get('evidence_sha1')}`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Instructions", "", str(payload.get("instructions") or "")])
    return "\n".join(lines)


def write_manual_review_dossier(
    path: Path,
    candidates_found: list[dict[str, Any]] | None = None,
    state_path: Path | None = None,
    task_results: list[dict[str, Any]] | None = None,
    *,
    draft_path: Path | None = None,
    markdown_path: Path | None = None,
    limit: int = 5,
    holdout_start: str = "2024-07-01",
) -> dict[str, Any]:
    payload = build_manual_review_dossier(
        candidates_found,
        state_path,
        task_results,
        limit=limit,
        holdout_start=holdout_start,
    )
    atomic_write_json(path, payload)
    if draft_path is not None:
        atomic_write_json(
            draft_path,
            {
                "kind": "v9_review_decisions_draft",
                "generated_at": payload["generated_at"],
                "source_dossier": str(path),
                "human_action_required": True,
                "draft_is_not_apply_ready": True,
                "holdout_authorized": False,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
                "decisions": payload["draft_decisions"],
            },
        )
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(format_manual_review_dossier_markdown(payload) + "\n")
    return payload


def status_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in candidates:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def load_review_decisions(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        rows = payload.get("decisions") or []
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("review decisions must be a list or an object with decisions")
    return [dict(row) for row in rows]


def candidate_ids_for_record(record: dict[str, Any]) -> set[str]:
    ids = {candidate_identity(record)}
    for key in ("output_json", "fingerprint", "task"):
        value = record.get(key)
        if value:
            ids.add(str(value))
    return ids


def entry_ids(entry: dict[str, Any]) -> set[str]:
    ids = {str(entry.get("identity"))}
    for key in ("output_json", "fingerprint", "task"):
        value = entry.get(key)
        if value:
            ids.add(str(value))
    return {value for value in ids if value and value != "None"}


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def apply_review_decisions(state_path: Path, decisions_path: Path, task_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    state = read_json(state_path) or {}
    candidates = list(state.get("candidates_found", []))
    results = list(task_results if task_results is not None else state.get("task_results", []))
    queue = build_manual_review_queue(candidates, state_path, results)
    queue_by_id: dict[str, dict[str, Any]] = {}
    for entry in queue:
        for candidate_id in entry_ids(entry):
            queue_by_id[candidate_id] = entry

    deduped = dedupe_candidates(candidates)
    record_index_by_id: dict[str, int] = {}
    for idx, record in enumerate(deduped):
        for candidate_id in candidate_ids_for_record(record):
            record_index_by_id.setdefault(candidate_id, idx)

    decisions = load_review_decisions(decisions_path)
    now = pd.Timestamp.now(tz="UTC").isoformat()
    applied = 0
    rows = []
    before_counts = status_counts(candidates)

    for raw in decisions:
        candidate_id = str(raw.get("candidate_id") or "")
        decision = str(raw.get("decision") or "")
        evidence_sha1 = str(raw.get("evidence_sha1") or "")
        reviewer = str(raw.get("reviewer") or "")
        rationale = str(raw.get("rationale") or "").strip()
        row = {
            "candidate_id": candidate_id,
            "decision": decision,
            "applied": False,
            "reason": "",
        }
        if not candidate_id:
            row["reason"] = "missing_candidate_id"
            rows.append(row)
            continue
        if decision not in REVIEW_DECISIONS:
            row["reason"] = "invalid_decision"
            rows.append(row)
            continue
        if not reviewer:
            row["reason"] = "missing_reviewer"
            rows.append(row)
            continue
        if not rationale:
            row["reason"] = "missing_rationale"
            rows.append(row)
            continue

        record_idx = record_index_by_id.get(candidate_id)
        if record_idx is None:
            row["reason"] = "unknown_candidate"
            rows.append(row)
            continue
        record = candidates[record_idx]
        target_status = REVIEW_STATUS_BY_DECISION[decision]
        if record.get("status") == target_status and record.get("review_evidence_sha1") == evidence_sha1:
            row["reason"] = "already_applied"
            row["applied"] = False
            rows.append(row)
            continue

        entry = queue_by_id.get(candidate_id)
        if not entry:
            row["reason"] = "not_in_manual_review_queue"
            row["current_status"] = record.get("status")
            rows.append(row)
            continue
        row["queue_identity"] = entry.get("identity")
        row["expected_evidence_sha1"] = entry.get("evidence_sha1")
        if evidence_sha1 != entry.get("evidence_sha1"):
            row["reason"] = "stale_evidence"
            rows.append(row)
            continue
        if decision == "validate_train_only" and not entry.get("data_snapshot_fingerprint"):
            row["reason"] = "snapshot_revalidation_required"
            rows.append(row)
            continue
        if record.get("status") != "manual_review_required":
            row["reason"] = "not_manual_review_required"
            row["current_status"] = record.get("status")
            rows.append(row)
            continue

        record["status"] = target_status
        record["review_decision"] = decision
        record["reviewed_by"] = reviewer
        record["reviewed_at"] = now
        record["review_rationale"] = rationale
        record["review_evidence_sha1"] = evidence_sha1
        record["decision_policy"] = "human_review_v1"
        record["holdout_authorized"] = False
        record["paper_trading_authorized"] = False
        record["live_trading_authorized"] = False
        row["applied"] = True
        row["reason"] = "applied"
        row["new_status"] = target_status
        applied += 1
        rows.append(row)

    if applied:
        state["candidates_found"] = candidates
        state["candidates_found_total"] = len(candidates)
        state["manual_review_decision_updated_at"] = now
        state["holdout_authorized"] = False
        state["paper_trading_authorized"] = False
        state["live_trading_authorized"] = False
        atomic_write_json(state_path, state)

    return {
        "kind": "v9_manual_review_decision_report",
        "generated_at": now,
        "source_state": str(state_path),
        "decisions_path": str(decisions_path),
        "decision_policy": "human_review_v1",
        "applied_count": applied,
        "decision_count": len(decisions),
        "status_counts_before": before_counts,
        "status_counts_after": status_counts(candidates),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "decisions": rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual review triage and decision applicator")
    sub = parser.add_subparsers(dest="command", required=True)
    queue = sub.add_parser("queue", help="write manual review queue")
    queue.add_argument("--state", default="state/v9_auto_research_state.json")
    queue.add_argument("--out", default="state/manual_review_queue.json")
    dossier = sub.add_parser("dossier", help="write manual review dossier and non-applicable decision draft")
    dossier.add_argument("--state", default="state/v9_auto_research_state.json")
    dossier.add_argument("--out", default="state/manual_review_dossier.json")
    dossier.add_argument("--draft-out", default="state/review_decisions_draft.json")
    dossier.add_argument("--md-out", default="state/manual_review_dossier.md")
    dossier.add_argument("--limit", type=int, default=5)
    dossier.add_argument("--holdout-start", default="2024-07-01")
    apply = sub.add_parser("apply-decisions", help="apply human review decisions with evidence hash checks")
    apply.add_argument("--state", default="state/v9_auto_research_state.json")
    apply.add_argument("--decisions", default="control/review_decisions.json")
    apply.add_argument("--out", default="state/review_decision_report.json")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.command == "queue":
        payload = write_manual_review_queue(Path(args.out), state_path=Path(args.state))
    elif args.command == "dossier":
        payload = write_manual_review_dossier(
            Path(args.out),
            state_path=Path(args.state),
            draft_path=Path(args.draft_out),
            markdown_path=Path(args.md_out),
            limit=args.limit,
            holdout_start=args.holdout_start,
        )
    elif args.command == "apply-decisions":
        state_path = Path(args.state)
        payload = apply_review_decisions(state_path, Path(args.decisions))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True))
        write_manual_review_queue(state_path.parent / "manual_review_queue.json", state_path=state_path)
    else:  # pragma: no cover
        raise SystemExit(f"unknown command: {args.command}")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
