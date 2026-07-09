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

from v9.research.candidate_dedupe import dedupe_candidates  # noqa: E402


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve_path(path: str | Path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base / p


def accepted_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in payload.get("rows", []) if row.get("advance_passed")]


def first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return None


def metric(cost: dict[str, Any], key: str) -> float | None:
    return first_number(cost.get(key))


def compact_cost(cost: dict[str, Any]) -> dict[str, Any]:
    bench = cost.get("equal_weight_benchmark") or {}
    return {
        "sharpe": metric(cost, "sharpe"),
        "total_return": metric(cost, "total_return"),
        "max_drawdown": metric(cost, "max_drawdown"),
        "daily_turnover": metric(cost, "daily_turnover"),
        "avg_gross_exposure": metric(cost, "avg_gross_exposure"),
        "bootstrap_30d_sharpe_p5": metric(cost, "bootstrap_30d_sharpe_p5"),
        "bootstrap_30d_sharpe_p5_confirm": metric(cost, "bootstrap_30d_sharpe_p5_confirm"),
        "positive_symbol_count": cost.get("positive_symbol_count"),
        "symbol_count": cost.get("symbol_count"),
        "positive_active_yearly_bucket_count": cost.get("positive_active_yearly_bucket_count"),
        "active_yearly_bucket_count": cost.get("active_yearly_bucket_count"),
        "benchmark_sharpe_excess": metric(bench, "sharpe_excess"),
        "benchmark_drawdown_ratio": metric(bench, "drawdown_ratio"),
    }


def row_costs(row: dict[str, Any], segment: str) -> dict[str, Any]:
    block = row.get(segment) or {}
    return {
        "cost20": compact_cost(block.get("cost20") or row.get("cost20") or {}),
        "cost40": compact_cost(block.get("cost40") or row.get("cost40") or {}),
        "checks": block.get("checks") or {},
    }


def failed_checks(row: dict[str, Any]) -> list[str]:
    checks = dict(row.get("advance_checks") or {})
    for block_name in ("selection", "validation"):
        block = row.get(block_name) or {}
        checks.update(block.get("checks") or {})
    return sorted(name for name, passed in checks.items() if not passed)


def train_validation_score(row: dict[str, Any]) -> float:
    validation = row_costs(row, "validation")["cost20"]
    selection = row_costs(row, "selection")["cost20"]
    return first_number(
        validation.get("sharpe"),
        selection.get("bootstrap_30d_sharpe_p5_confirm"),
        selection.get("bootstrap_30d_sharpe_p5"),
        selection.get("sharpe"),
        0.0,
    ) or 0.0


def preregistered_holdout_command(task: str, artifact: str) -> dict[str, Any]:
    if "tsmom" in task:
        stem = Path(artifact).stem
        return {
            "status": "available_but_not_authorized",
            "do_not_run_until": "holdout_authorized=true",
            "command": (
                "python3 scripts/v9_tsmom_holdout_audit.py "
                f"{artifact} "
                f"--out-json artifacts/v9/holdout/{stem}_holdout_audit.json "
                f"--out-text artifacts/v9/holdout/{stem}_holdout_audit.txt"
            ),
            "decision_rule": (
                "holdout_20bps_sharpe_ge_0_7 and holdout_20bps_return_gt_0 and "
                "holdout_20bps_drawdown_le_25pct and holdout_40bps_sharpe_gt_0 and "
                "holdout_40bps_return_gt_0"
            ),
        }
    if "xsec_ohlcv" in task:
        stem = Path(artifact).stem
        return {
            "status": "available_but_not_authorized",
            "do_not_run_until": "holdout_authorized=true",
            "command": (
                "python3 scripts/v9_xsec_ohlcv_holdout_audit.py "
                f"{artifact} --split holdout "
                f"--out-json artifacts/v9/holdout/{stem}_holdout_audit.json "
                f"--out-text artifacts/v9/holdout/{stem}_holdout_audit.txt"
            ),
            "decision_rule": (
                "holdout_20bps_sharpe_ge_0_7 and holdout_20bps_return_gt_0 and "
                "holdout_20bps_drawdown_le_25pct and holdout_40bps_sharpe_gt_0 and "
                "holdout_40bps_return_gt_0 and holdout_top_symbol_share_le_65pct"
            ),
        }
    return {
        "status": "missing_generic_holdout_entrypoint",
        "do_not_run_until": "holdout_authorized=true",
        "command": None,
        "decision_rule": "Define and review a generic holdout audit entrypoint before authorization.",
    }


def candidate_evidence(candidate: dict[str, Any], base: Path) -> dict[str, Any] | None:
    artifact_raw = str(candidate.get("output_json") or "")
    if not artifact_raw:
        return None
    artifact = resolve_path(artifact_raw, base)
    if not artifact.exists():
        return {
            "task": candidate.get("task"),
            "status": candidate.get("status"),
            "artifact": artifact_raw,
            "missing_artifact": True,
        }
    payload = read_json(artifact)
    summary = payload.get("summary") or {}
    rows = accepted_rows(payload)
    top = max(rows, key=train_validation_score) if rows else {}
    selection_validation = payload.get("selection_validation") or {}
    data = payload.get("data") or {}
    run_config = payload.get("config") or {}
    return {
        "task": candidate.get("task"),
        "status": candidate.get("status"),
        "duplicate_of": candidate.get("duplicate_of"),
        "artifact": artifact_raw,
        "kind": payload.get("kind"),
        "accepted_train_only": bool(summary.get("accepted_train_only")),
        "pass_count": int(summary.get("pass_count") or len(rows)),
        "rows": int(summary.get("rows") or len(payload.get("rows", []))),
        "safety": {
            "holdout_authorized": bool(summary.get("holdout_authorized")),
            "paper_trading_authorized": bool(summary.get("paper_trading_authorized")),
            "live_trading_authorized": bool(summary.get("live_trading_authorized")),
        },
        "train_window": {
            "train_start": run_config.get("train_start"),
            "train_end": run_config.get("train_end"),
            "embargo_start": run_config.get("embargo_start"),
        },
        "data_lineage": {
            "fingerprint": data.get("fingerprint") or candidate.get("data_fingerprint"),
            "first_dt": data.get("first_dt"),
            "last_dt": data.get("last_dt"),
            "rows": data.get("rows"),
            "symbols": data.get("symbols") or payload.get("symbols"),
        },
        "selection_validation": {
            "effective_trials": selection_validation.get("effective_trials"),
            "prior_trials": selection_validation.get("prior_trials"),
            "n_configs_tested": selection_validation.get("n_configs_tested"),
            "selection_bootstrap_p5_min": selection_validation.get("selection_bootstrap_p5_min"),
            "validation_sharpe20_min": selection_validation.get("validation_sharpe20_min"),
            "note": selection_validation.get("note"),
        },
        "top_config": top.get("config") or {},
        "top_selection": row_costs(top, "selection") if top else {},
        "top_validation": row_costs(top, "validation") if top else {},
        "failed_checks": failed_checks(top) if top else ["no_accepted_row"],
        "train_validation_score": train_validation_score(top) if top else None,
        "pre_registered_holdout": preregistered_holdout_command(str(candidate.get("task") or ""), artifact_raw),
    }


def build_evidence(state_path: Path, base: Path, max_candidates: int = 30) -> dict[str, Any]:
    state = read_json(state_path)
    deduped = dedupe_candidates(list(state.get("candidates_found", [])))
    distinct = [row for row in deduped if not row.get("duplicate_of")]
    evidence_rows = []
    for candidate in distinct:
        evidence = candidate_evidence(candidate, base)
        if evidence:
            evidence_rows.append(evidence)
    evidence_rows.sort(
        key=lambda row: (
            bool(row.get("missing_artifact")),
            bool(row.get("failed_checks")),
            -float(row.get("train_validation_score") or 0.0),
            -int(row.get("pass_count") or 0),
            str(row.get("task")),
        )
    )
    selected = evidence_rows[:max_candidates]
    return {
        "kind": "v9_train_cv_evidence_pack_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_state": str(state_path),
        "inputs_read": [str(state_path)] + [row["artifact"] for row in selected if row.get("artifact")],
        "holdout_accessed": False,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "summary": {
            "state_candidates": len(state.get("candidates_found", [])),
            "distinct_candidates": len(distinct),
            "reported_candidates": len(selected),
            "missing_artifacts": sum(1 for row in selected if row.get("missing_artifact")),
            "clean_train_only_candidates": sum(1 for row in selected if not row.get("failed_checks") and not row.get("missing_artifact")),
            "data_drift_status_counts": status_counts(selected),
        },
        "acceptance_criteria_for_human_holdout_authorization": [
            "Review only this train-only evidence pack and source artifacts; do not read holdout data.",
            "Candidate must have accepted_train_only=true, no failed train advance checks, and no missing artifact.",
            "Selection/validation data must end before embargo_start according to artifact lineage.",
            "Pre-register the exact holdout command and pass/fail rule before any holdout run.",
            "Do not write FOUND_PAPER_READY, live, or production markers from this train-only packet.",
        ],
        "candidates": selected,
    }


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status"))
        out[status] = out.get(status, 0) + 1
    return dict(sorted(out.items()))


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# TRAIN_CV_EVIDENCE",
        "",
        f"created_at: `{report['created_at']}`",
        "safety: `holdout_authorized=False paper_trading_authorized=False live_trading_authorized=False`",
        f"holdout_accessed: `{report['holdout_accessed']}`",
        "",
        "## Summary",
        f"- state_candidates: {summary['state_candidates']}",
        f"- distinct_candidates: {summary['distinct_candidates']}",
        f"- reported_candidates: {summary['reported_candidates']}",
        f"- clean_train_only_candidates: {summary['clean_train_only_candidates']}",
        f"- missing_artifacts: {summary['missing_artifacts']}",
        f"- status_counts: `{json.dumps(summary['data_drift_status_counts'], sort_keys=True)}`",
        "",
        "## Holdout Authorization Criteria",
    ]
    lines.extend(f"- {item}" for item in report["acceptance_criteria_for_human_holdout_authorization"])
    lines.extend(["", "## Candidates"])
    for idx, row in enumerate(report["candidates"], 1):
        validation = ((row.get("top_validation") or {}).get("cost20") or {})
        selection = ((row.get("top_selection") or {}).get("cost20") or {})
        data = row.get("data_lineage") or {}
        command = row.get("pre_registered_holdout") or {}
        lines.extend(
            [
                f"### {idx}. {row.get('task')}",
                f"- status: `{row.get('status')}`",
                f"- artifact: `{row.get('artifact')}`",
                f"- accepted_train_only: `{row.get('accepted_train_only')}` passes: `{row.get('pass_count')}/{row.get('rows')}`",
                f"- selection20: sharpe `{fmt(selection.get('sharpe'))}` dd `{fmt(selection.get('max_drawdown'))}` boot `{fmt(selection.get('bootstrap_30d_sharpe_p5'))}`",
                f"- validation20: sharpe `{fmt(validation.get('sharpe'))}` return `{fmt(validation.get('total_return'))}` dd `{fmt(validation.get('max_drawdown'))}`",
                f"- data: fp `{str(data.get('fingerprint'))[:12]}` first `{data.get('first_dt')}` last `{data.get('last_dt')}` symbols `{len(data.get('symbols') or [])}`",
                f"- failed_checks: `{','.join(row.get('failed_checks') or []) or 'none'}`",
                f"- holdout_command_status: `{command.get('status')}` do_not_run_until `{command.get('do_not_run_until')}`",
            ]
        )
        if command.get("command"):
            lines.append(f"- pre_registered_command: `{command['command']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a train-only CV evidence packet for holdout authorization review")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--out-json", default="artifacts/v9/reviews/TRAIN_CV_EVIDENCE.json")
    parser.add_argument("--out-md", default="artifacts/v9/reviews/TRAIN_CV_EVIDENCE.md")
    parser.add_argument("--max-candidates", type=int, default=30)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    base = Path.cwd()
    report = build_evidence(Path(args.state), base=base, max_candidates=args.max_candidates)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True))
    out_md.write_text(format_markdown(report))
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_markdown(report))


if __name__ == "__main__":
    main()
