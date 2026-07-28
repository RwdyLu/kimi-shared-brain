#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.multiplicity import multiplicity_evidence  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve_path(path: str | Path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base / p


def candidate_rows(state: dict[str, Any], include_data_drift: bool) -> list[dict[str, Any]]:
    rows = []
    for candidate in state.get("candidates_found", []):
        status = str(candidate.get("status") or "")
        if "data_drift" in status or "quarantined" in status:
            if not include_data_drift:
                continue
        if "rejected" in status:
            continue
        rows.append(dict(candidate))
    return rows


def triage_candidate(candidate: dict[str, Any], base: Path, total_trials: int) -> dict[str, Any]:
    artifact = resolve_path(str(candidate.get("output_json") or ""), base)
    if not artifact.exists():
        evidence = {"evaluated": False, "decision": "missing_artifact"}
    else:
        evidence = multiplicity_evidence(read_json(artifact), total_trials=total_trials)
    return {
        "task": candidate.get("task"),
        "status": candidate.get("status"),
        "duplicate_of": candidate.get("duplicate_of"),
        "output_json": candidate.get("output_json"),
        "data_fingerprint": candidate.get("data_fingerprint"),
        "multiplicity": evidence,
        "decision": evidence.get("decision"),
    }


def decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("decision"))
        counts[decision] = counts.get(decision, 0) + 1
    return dict(sorted(counts.items()))


def build_report(state_path: Path, base: Path, *, include_data_drift: bool = False, limit: int = 100) -> dict[str, Any]:
    state = read_json(state_path)
    total_trials = max(1, int(state.get("candidates_found_total") or len(state.get("candidates_found", [])) or 1))
    candidates = candidate_rows(state, include_data_drift)
    rows = [triage_candidate(candidate, base, total_trials) for candidate in candidates]
    rows.sort(
        key=lambda row: (
            0 if row.get("decision") == "multiplicity_survivor" else 1,
            float(((row.get("multiplicity") or {}).get("metrics") or {}).get("adjusted_p_value") or 1.0),
            str(row.get("task") or ""),
        )
    )
    return {
        "kind": "v9_train_only_multiplicity_triage_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_state": str(state_path),
        "holdout_accessed": False,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "threshold_basis": "existing train-only artifact metrics only; no holdout, paper, or live data",
        "summary": {
            "state_candidates": len(state.get("candidates_found", [])),
            "total_trials_for_adjustment": total_trials,
            "candidate_rows_considered": len(candidates),
            "decision_counts": decision_counts(rows),
            "survivor_count": sum(1 for row in rows if row.get("decision") == "multiplicity_survivor"),
            "rejected_multiplicity_count": sum(1 for row in rows if row.get("decision") == "rejected_multiplicity"),
            "rejected_train_hard_gate_count": sum(
                1 for row in rows if row.get("decision") == "rejected_train_hard_gate"
            ),
        },
        "recommendation": {
            "next_step": "Only multiplicity_survivor rows should remain in manual train-only review.",
            "do_not_run_until": "holdout_authorized=true",
            "paper_live_production": "not authorized by this train-only triage",
        },
        "rows": rows[:limit],
    }


def fmt(value: Any, digits: int = 4) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRAIN_ONLY_MULTIPLICITY_TRIAGE",
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
        f"- total_trials_for_adjustment: `{summary['total_trials_for_adjustment']}`",
        f"- candidate_rows_considered: `{summary['candidate_rows_considered']}`",
        f"- survivor_count: `{summary['survivor_count']}`",
        f"- rejected_multiplicity_count: `{summary['rejected_multiplicity_count']}`",
        f"- rejected_train_hard_gate_count: `{summary['rejected_train_hard_gate_count']}`",
        f"- decision_counts: `{json.dumps(summary['decision_counts'], sort_keys=True)}`",
        "",
        "## Rows",
        "",
        "| rank | decision | adjusted p | sharpe | boot p5 | dd | active+ | activity | task |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(report.get("rows", []), 1):
        evidence = row.get("multiplicity") or {}
        metrics = evidence.get("metrics") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    str(row.get("decision")),
                    fmt(metrics.get("adjusted_p_value")),
                    fmt(metrics.get("sharpe")),
                    fmt(metrics.get("bootstrap_30d_sharpe_p5")),
                    fmt(metrics.get("max_drawdown")),
                    fmt(metrics.get("positive_bucket_fraction")),
                    fmt(metrics.get("activity_count")),
                    f"`{row.get('task')}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This is train-only multiplicity triage. It does not authorize holdout, paper, live, or production trading.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage train-only candidates with multiplicity-adjusted evidence")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--base", default=".")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--include-data-drift", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    base = Path(args.base)
    report = build_report(resolve_path(args.state, base), base, include_data_drift=args.include_data_drift, limit=args.limit)
    out_json = resolve_path(args.out_json, base)
    out_md = resolve_path(args.out_md, base)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    out_md.write_text(format_markdown(report))


if __name__ == "__main__":
    main()
