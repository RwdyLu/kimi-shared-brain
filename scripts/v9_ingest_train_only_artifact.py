from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_candidate_revalidation_plan import build_revalidation_plan  # noqa: E402
from v9.contract.auto_research import (  # noqa: E402
    DEFAULT_EMBARGO_START,
    DEFAULT_TRAIN_END,
    ResearchTask,
    candidate_multiplicity_metadata,
    candidate_record,
    drift_history_from_explored,
    has_data_drift,
    maybe_write_tsmom_rescue_artifacts,
    maybe_write_xsec_diagnostic_review,
    maybe_write_xsec_rescue_artifacts,
    read_json,
    status_after_multiplicity,
    task_result_status,
    trial_metadata,
    write_internal_candidate_marker,
)
from v9.research.candidate_dedupe import dedupe_candidates  # noqa: E402
from v9.research.task_planner import (  # noqa: E402
    CLI_PRESET_BY_PRESET,
    DEFAULT_TRAIN_MODULE,
    MODULE_BY_PRESET,
    PlannedTask,
    append_explored_record,
    evaluation_version_for_preset,
    task_fingerprint,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_jsonl_once(path: Path, record: dict[str, Any], unique_keys: tuple[str, ...]) -> bool:
    existing = read_jsonl(path)
    for row in existing:
        if any(record.get(key) and row.get(key) == record.get(key) for key in unique_keys):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return True


def planned_task_from_args(args: argparse.Namespace) -> PlannedTask:
    module = args.module or MODULE_BY_PRESET.get(args.preset, DEFAULT_TRAIN_MODULE)
    cli_preset = args.cli_preset if args.cli_preset else CLI_PRESET_BY_PRESET.get(args.preset)
    fingerprint = args.fingerprint or task_fingerprint(
        args.preset,
        args.train_start,
        args.train_end,
        args.embargo_start,
        args.bootstrap_iterations,
        evaluation_version=evaluation_version_for_preset(args.preset),
    )
    return PlannedTask(
        name=args.task_name,
        preset=args.preset,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        fingerprint=fingerprint,
        output_json=args.output_json,
        output_md=args.output_md or str(Path(args.output_json).with_suffix(".md")),
        bootstrap_iterations=args.bootstrap_iterations,
        prior_trials=args.prior_trials,
        module=module,
        cli_preset=cli_preset,
    )


def build_result(task: ResearchTask, planned: PlannedTask, payload: dict[str, Any]) -> dict[str, Any]:
    review_metadata = maybe_write_xsec_diagnostic_review(task.output_json)
    rescue_metadata = maybe_write_xsec_rescue_artifacts(task.output_json)
    tsmom_rescue_metadata = maybe_write_tsmom_rescue_artifacts(task.output_json)
    result = {
        "task": task.name,
        "status": task_result_status(payload),
        "skipped_existing": True,
        "output_json": task.output_json,
        "output_md": task.output_md,
        "returncode": 0,
        "fingerprint": planned.fingerprint,
        "planned_task": planned.record(),
        **trial_metadata(payload),
        **review_metadata,
        **rescue_metadata,
        **tsmom_rescue_metadata,
    }
    return result


def explored_record(planned: PlannedTask, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "fingerprint": planned.fingerprint,
        "task": planned.name,
        "module": planned.module,
        "preset": planned.preset,
        "cli_preset": planned.cli_preset,
        "status": result["status"],
        "output_json": result["output_json"],
        "output_md": result["output_md"],
        "returncode": result["returncode"],
        "train_start": planned.train_start,
        "train_end": planned.train_end,
        "embargo_start": planned.embargo_start,
        "n_configs_tested": result.get("n_configs_tested", 0),
        "prior_trials": result.get("prior_trials", 0),
        "effective_trials": result.get("effective_trials", 0),
        "data_fingerprint": result.get("data_fingerprint", ""),
        "data_symbols": result.get("data_symbols", []),
        "data_snapshot_path": result.get("data_snapshot_path", ""),
        "data_snapshot_fingerprint": result.get("data_snapshot_fingerprint", ""),
        "source": "supplemental_ingest_v1",
    }


def rebuild_plan(
    state_path: Path,
    supplemental_candidates_path: Path,
    revalidation_out_dir: Path,
    revalidation_out_json: Path,
) -> dict[str, Any]:
    plan = build_revalidation_plan(
        state_path,
        out_dir=revalidation_out_dir,
        supplemental_candidates_path=supplemental_candidates_path,
    )
    revalidation_out_json.parent.mkdir(parents=True, exist_ok=True)
    revalidation_out_json.write_text(json.dumps(plan, indent=2, sort_keys=True))
    return plan


def _same_artifact_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    left_path = Path(left)
    right_path = Path(right)
    if left_path.as_posix().rstrip("/") == right_path.as_posix().rstrip("/"):
        return True
    try:
        return left_path.resolve() == right_path.resolve()
    except OSError:
        return False


def plateau_audit_override_metadata(
    plateau_audit_json: Path | None,
    *,
    expected_artifact: str,
    min_neighbors: int = 2,
) -> dict[str, Any]:
    if plateau_audit_json is None:
        return {}
    if not plateau_audit_json.exists():
        raise FileNotFoundError(f"plateau audit missing: {plateau_audit_json}")

    audit = json.loads(plateau_audit_json.read_text())
    centers = [row for row in audit.get("centers", []) if isinstance(row, dict)]
    passed_centers = [row for row in centers if row.get("plateau_passed")]
    max_neighbors = max(
        (int(row.get("neighbor_validation_pass_count") or 0) for row in passed_centers),
        default=0,
    )
    audit_artifact = str(audit.get("artifact") or "")
    artifact_match = not audit_artifact or _same_artifact_path(audit_artifact, expected_artifact)
    plateau_passed = bool(audit.get("plateau_passed") or passed_centers)
    advance_pass_count = int(audit.get("advance_pass_count") or 0)
    decision = (
        "manual_review_required"
        if plateau_passed and artifact_match and advance_pass_count > 0 and max_neighbors >= min_neighbors
        else "ignored"
    )
    return {
        "policy": "plateau_audit_multiplicity_override_v1",
        "audit_json": str(plateau_audit_json),
        "audit_artifact": audit_artifact,
        "artifact_match": artifact_match,
        "plateau_passed": plateau_passed,
        "advance_pass_count": advance_pass_count,
        "passed_center_count": len(passed_centers),
        "max_neighbor_validation_pass_count": max_neighbors,
        "required_min_neighbors": int(min_neighbors),
        "decision": decision,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def ingest_train_only_artifact(
    *,
    planned: PlannedTask,
    state_path: Path,
    explored_path: Path,
    supplemental_candidates_path: Path,
    marker_path: Path,
    report_json: Path,
    revalidation_out_dir: Path,
    revalidation_out_json: Path,
    plateau_audit_json: Path | None = None,
    plateau_min_neighbors: int = 2,
    rebuild_revalidation_plan: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    output_path = Path(planned.output_json)
    if not output_path.exists():
        raise FileNotFoundError(f"train-only artifact missing: {output_path}")

    payload = read_json(output_path)
    task = ResearchTask(
        name=planned.name,
        command=planned.command(),
        output_json=planned.output_json,
        output_md=planned.output_md,
        timeout_sec=planned.timeout_sec,
    )
    result = build_result(task, planned, payload)

    explored_added = append_jsonl_once(explored_path, explored_record(planned, result), ("fingerprint",))
    if force and not explored_added:
        append_explored_record(explored_path, explored_record(planned, result))
        explored_added = True

    state = read_json(state_path) if state_path.exists() else {"task_results": [], "candidates_found": []}
    task_results = list(state.get("task_results", []))
    candidates_found = list(state.get("candidates_found", []))
    supplemental_candidates = read_jsonl(supplemental_candidates_path)
    candidate_added = False
    candidate_status = None
    record = None
    plateau_override = plateau_audit_override_metadata(
        plateau_audit_json,
        expected_artifact=planned.output_json,
        min_neighbors=plateau_min_neighbors,
    )

    if result["status"] == "accepted_train_only_candidate_found":
        candidate_status_before_multiplicity = (
            "quarantined_data_drift"
            if has_data_drift(drift_history_from_explored(explored_path) + task_results, result)
            else "manual_review_required"
        )
        candidate_status = candidate_status_before_multiplicity
        multiplicity_metadata = candidate_multiplicity_metadata(
            result,
            len(dedupe_candidates([*candidates_found, *supplemental_candidates])) + 1,
        )
        result.update(multiplicity_metadata)
        candidate_status = status_after_multiplicity(candidate_status, multiplicity_metadata)
        if plateau_override:
            result["plateau_multiplicity_override"] = plateau_override
        if (
            candidate_status_before_multiplicity == "manual_review_required"
            and candidate_status == "rejected_multiplicity"
            and plateau_override.get("decision") == "manual_review_required"
        ):
            candidate_status = "manual_review_required"
            result["candidate_status_before_plateau_override"] = "rejected_multiplicity"
            result["candidate_status_override_policy"] = plateau_override["policy"]
        record = candidate_record(task, result, status=candidate_status)
        record["source"] = "supplemental_ingest_v1"
        record["created_at"] = pd.Timestamp.now(tz="UTC").isoformat()
        if plateau_override:
            record["plateau_multiplicity_override"] = plateau_override
        candidate_added = append_jsonl_once(
            supplemental_candidates_path,
            record,
            ("fingerprint", "output_json"),
        )
        if force and not candidate_added:
            supplemental_candidates_path.parent.mkdir(parents=True, exist_ok=True)
            with supplemental_candidates_path.open("a") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            candidate_added = True
        if candidate_status == "manual_review_required":
            write_internal_candidate_marker(marker_path, record)

    plan = {}
    if rebuild_revalidation_plan:
        plan = rebuild_plan(
            state_path,
            supplemental_candidates_path,
            revalidation_out_dir,
            revalidation_out_json,
        )

    report = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "v9_train_only_artifact_ingest_v1",
        "task": planned.name,
        "fingerprint": planned.fingerprint,
        "status": result["status"],
        "candidate_status": candidate_status,
        "explored_added": explored_added,
        "candidate_added": candidate_added,
        "output_json": planned.output_json,
        "supplemental_candidates": str(supplemental_candidates_path),
        "plateau_multiplicity_override": plateau_override,
        "revalidation_plan": str(revalidation_out_json) if rebuild_revalidation_plan else "",
        "revalidation_group_count": plan.get("group_count"),
        "revalidation_config_count": plan.get("config_count"),
        "record": record,
        "result": result,
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest an out-of-band train-only artifact into candidate ledgers")
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--module", default="")
    parser.add_argument("--cli-preset", default="")
    parser.add_argument("--fingerprint", default="")
    parser.add_argument("--train-start", default="2017-08-01")
    parser.add_argument("--train-end", default=DEFAULT_TRAIN_END)
    parser.add_argument("--embargo-start", default=DEFAULT_EMBARGO_START)
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--prior-trials", type=int, default=0)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", default="")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--explored", default="state/v9_auto_research_explored.jsonl")
    parser.add_argument("--supplemental-candidates", default="state/v9_supplemental_train_only_candidates.jsonl")
    parser.add_argument("--marker", default="state/FOUND_INTERNAL_CANDIDATE.txt")
    parser.add_argument("--report-json", default="state/v9_last_ingested_train_only_artifact.json")
    parser.add_argument("--revalidation-out-dir", default="artifacts/v9/revalidation")
    parser.add_argument("--revalidation-out-json", default="artifacts/v9/revalidation/v9_candidate_revalidation_plan.json")
    parser.add_argument(
        "--plateau-audit-json",
        default="",
        help="Optional basin plateau audit; passing audits can move a rejected_multiplicity candidate back to manual review only.",
    )
    parser.add_argument("--plateau-min-neighbors", type=int, default=2)
    parser.add_argument("--no-rebuild-revalidation-plan", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    planned = planned_task_from_args(args)
    report = ingest_train_only_artifact(
        planned=planned,
        state_path=Path(args.state),
        explored_path=Path(args.explored),
        supplemental_candidates_path=Path(args.supplemental_candidates),
        marker_path=Path(args.marker),
        report_json=Path(args.report_json),
        revalidation_out_dir=Path(args.revalidation_out_dir),
        revalidation_out_json=Path(args.revalidation_out_json),
        plateau_audit_json=Path(args.plateau_audit_json) if args.plateau_audit_json else None,
        plateau_min_neighbors=args.plateau_min_neighbors,
        rebuild_revalidation_plan=not args.no_rebuild_revalidation_plan,
        force=args.force,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
