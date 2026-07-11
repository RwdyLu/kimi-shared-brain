from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from v9.research.candidate_dedupe import dedupe_candidates
from v9.research.multiplicity import multiplicity_evidence


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
