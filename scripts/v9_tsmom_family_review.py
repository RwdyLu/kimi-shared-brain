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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def family_candidates(state: dict[str, Any], primary_task: str) -> list[dict[str, Any]]:
    out = []
    for row in state.get("candidates_found", []):
        if row.get("task") == primary_task or row.get("duplicate_of") == primary_task:
            out.append(dict(row))
    return out


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def best_passed_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    for row in payload.get("top", []):
        if row.get("advance_passed"):
            return row
    return None


def failed_check_counts(payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in payload.get("rows", []):
        for name, passed in (row.get("advance_checks") or {}).items():
            if passed is False:
                counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def compact_artifact(record: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    path = repo_root / str(record["output_json"])
    if not path.exists():
        return {"task": record.get("task"), "output_json": record.get("output_json"), "missing": True}
    payload = read_json(path)
    row = best_passed_row(payload)
    data = payload.get("data") or {}
    summary = payload.get("summary") or {}
    selection_validation = payload.get("selection_validation") or {}
    out: dict[str, Any] = {
        "task": record.get("task"),
        "status": record.get("status"),
        "duplicate_of": record.get("duplicate_of"),
        "output_json": record.get("output_json"),
        "output_md": record.get("output_md"),
        "kind": payload.get("kind"),
        "summary": summary,
        "data": {
            "fingerprint": data.get("fingerprint"),
            "first_dt": data.get("first_dt"),
            "last_dt": data.get("last_dt"),
            "rows": data.get("rows"),
            "symbols": data.get("symbols"),
        },
        "selection_validation": {
            "effective_trials": selection_validation.get("effective_trials"),
            "prior_trials": selection_validation.get("prior_trials"),
            "n_configs_tested": selection_validation.get("n_configs_tested"),
            "selection_bootstrap_p5_min": selection_validation.get("selection_bootstrap_p5_min"),
            "validation_sharpe20_min": selection_validation.get("validation_sharpe20_min"),
            "lookbacks_h": selection_validation.get("lookbacks_h"),
            "walk_forward_required": selection_validation.get("walk_forward_required"),
            "drop_one_lookback_required": selection_validation.get("drop_one_lookback_required"),
            "leave_one_symbol_required": selection_validation.get("leave_one_symbol_required"),
        },
        "fail_counts": failed_check_counts(payload),
    }
    if row:
        c20 = row.get("cost20") or {}
        c40 = row.get("cost40") or {}
        val20 = (row.get("validation") or {}).get("cost20") or {}
        val40 = (row.get("validation") or {}).get("cost40") or {}
        wf = row.get("walk_forward") or {}
        drop_one = row.get("drop_one_lookback") or {}
        loso = row.get("leave_one_symbol") or {}
        out["best_passed_row"] = {
            "config": row.get("config"),
            "lookbacks_h": row.get("lookbacks_h"),
            "selection": {
                "sharpe20": safe_float(c20.get("sharpe")),
                "return20": safe_float(c20.get("total_return")),
                "max_drawdown20": safe_float(c20.get("max_drawdown")),
                "bootstrap_p5": safe_float(c20.get("bootstrap_30d_sharpe_p5")),
                "sharpe40": safe_float(c40.get("sharpe")),
            },
            "validation": {
                "sharpe20": safe_float(val20.get("sharpe")),
                "return20": safe_float(val20.get("total_return")),
                "max_drawdown20": safe_float(val20.get("max_drawdown")),
                "sharpe40": safe_float(val40.get("sharpe")),
            },
            "robustness": {
                "walk_forward_passed": wf.get("passed"),
                "walk_forward_q25_sharpe": safe_float(wf.get("q25_sharpe")),
                "walk_forward_sign_consistency": safe_float(wf.get("sign_consistency")),
                "drop_one_lookback_passed": drop_one.get("passed"),
                "leave_one_symbol_passed": loso.get("passed"),
            },
            "failed_checks": [name for name, passed in (row.get("advance_checks") or {}).items() if passed is False],
        }
    else:
        out["best_passed_row"] = None
    return out


def decision(records: list[dict[str, Any]]) -> tuple[str, list[str]]:
    accepted = [row for row in records if (row.get("summary") or {}).get("accepted_train_only")]
    clean = [row for row in accepted if row.get("status") == "manual_review_required"]
    fingerprints = {str((row.get("data") or {}).get("fingerprint")) for row in accepted if (row.get("data") or {}).get("fingerprint")}
    warnings = []
    if any(str(row.get("status", "")).endswith("data_drift") for row in records):
        warnings.append("family_contains_data_drift_duplicates")
    if len(fingerprints) < 2:
        warnings.append("accepted_family_seen_on_single_data_fingerprint")
    if len(accepted) >= 2 and clean:
        return "train_only_family_promising_manual_review_required", warnings
    if accepted:
        return "train_only_family_candidate_but_needs_drift_review", warnings
    return "train_only_family_not_accepted", warnings


def build_review(state_path: Path, primary_task: str, repo_root: Path) -> dict[str, Any]:
    state = read_json(state_path)
    candidates = family_candidates(state, primary_task)
    artifacts = [compact_artifact(row, repo_root) for row in candidates]
    status_counts: dict[str, int] = {}
    for row in candidates:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    family_decision, warnings = decision(artifacts)
    return {
        "kind": "v9_tsmom_family_review_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "primary_task": primary_task,
        "source_state": str(state_path),
        "decision": family_decision,
        "warnings": warnings,
        "candidate_record_count": len(candidates),
        "status_counts": dict(sorted(status_counts.items())),
        "accepted_artifact_count": sum(1 for row in artifacts if (row.get("summary") or {}).get("accepted_train_only")),
        "distinct_data_fingerprints": sorted(
            {
                str((row.get("data") or {}).get("fingerprint"))
                for row in artifacts
                if (row.get("data") or {}).get("fingerprint")
            }
        ),
        "artifacts": artifacts,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "note": "Train-only family review. It does not authorize holdout, paper trading, or live trading.",
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# V9 TSMOM Family Review",
        "",
        f"created_at: `{review['created_at']}`",
        f"primary_task: `{review['primary_task']}`",
        f"decision: `{review['decision']}`",
        "",
        "This is train-only research. It does not authorize holdout, paper trading, or live trading.",
        "",
        "## Summary",
        "",
        f"- candidate_record_count: `{review['candidate_record_count']}`",
        f"- accepted_artifact_count: `{review['accepted_artifact_count']}`",
        f"- distinct_data_fingerprints: `{len(review['distinct_data_fingerprints'])}`",
        f"- status_counts: `{json.dumps(review['status_counts'], sort_keys=True)}`",
        f"- warnings: `{','.join(review['warnings']) or 'none'}`",
        "",
        "## Artifacts",
        "",
    ]
    for artifact in review["artifacts"]:
        best = artifact.get("best_passed_row") or {}
        sel = best.get("selection") or {}
        val = best.get("validation") or {}
        rob = best.get("robustness") or {}
        summary = artifact.get("summary") or {}
        data = artifact.get("data") or {}
        lines.extend(
            [
                f"### {artifact.get('task')}",
                f"- status: `{artifact.get('status')}` duplicate_of: `{artifact.get('duplicate_of')}`",
                f"- accepted_train_only: `{summary.get('accepted_train_only')}` pass_count: `{summary.get('pass_count')}` rows: `{summary.get('rows')}`",
                f"- data: `{data.get('first_dt')}` to `{data.get('last_dt')}` fingerprint `{data.get('fingerprint')}`",
                "- best_passed: "
                f"sel_sh20 `{fmt(sel.get('sharpe20'))}` sel_dd `{fmt(sel.get('max_drawdown20'))}` "
                f"boot `{fmt(sel.get('bootstrap_p5'))}` val_sh20 `{fmt(val.get('sharpe20'))}` "
                f"val_dd `{fmt(val.get('max_drawdown20'))}` wf `{rob.get('walk_forward_passed')}` "
                f"drop `{rob.get('drop_one_lookback_passed')}` loso `{rob.get('leave_one_symbol_passed')}`",
                "",
            ]
        )
    lines.append(f"note: `{review['note']}`")
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review a train-only TSMOM candidate family")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--primary-task", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    review = build_review(Path(args.state), args.primary_task, Path(args.repo_root))
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    text = format_markdown(review)
    out_md.write_text(text)
    if args.format == "json":
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text)


if __name__ == "__main__":
    main()
