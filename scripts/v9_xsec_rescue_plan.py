from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_diagnostic_walkforward_report import artifact_paths, load_rows  # noqa: E402
from v9.research.xsec_rescue import (
    DEFAULT_RESCUE_BUDGET_PER_SEED,
    DEFAULT_RESCUE_TOP_K,
    build_rescue_plan,
    rescue_artifact_paths,
    write_rescue_artifacts,
)


def load_rescue_source(artifact: Path) -> tuple[list[dict[str, Any]], dict[str, Any], str, str]:
    final_json, _progress_jsonl, _progress_meta = artifact_paths(artifact)
    if final_json.exists():
        payload = json.loads(final_json.read_text())
        meta = dict(payload.get("selection_validation", {}) or {})
        meta["summary"] = dict(payload.get("summary", {}) or {})
        return list(payload.get("rows", [])), meta, "final", str(final_json)
    rows, meta, source_kind = load_rows(artifact)
    return rows, dict(meta), source_kind, str(artifact)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a train-only XSEC diagnostic rescue plan")
    parser.add_argument("artifact", help="Completed XSEC .json artifact or active .progress.jsonl")
    parser.add_argument("--top-k", type=int, default=DEFAULT_RESCUE_TOP_K)
    parser.add_argument("--budget-per-seed", type=int, default=DEFAULT_RESCUE_BUDGET_PER_SEED)
    parser.add_argument("--out-plan", default="")
    parser.add_argument("--out-configs", default="")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    artifact = Path(args.artifact)
    rows, meta, source_kind, source_artifact = load_rescue_source(artifact)
    meta["source_kind"] = source_kind
    plan = build_rescue_plan(
        rows,
        meta=meta,
        source_artifact=source_artifact,
        top_k=args.top_k,
        budget_per_seed=args.budget_per_seed,
    )
    default_plan, default_configs = rescue_artifact_paths(source_artifact)
    plan_path = Path(args.out_plan) if args.out_plan else default_plan
    config_path = Path(args.out_configs) if args.out_configs else default_configs
    metadata = write_rescue_artifacts(plan, plan_path, config_path)
    metadata["source_kind"] = source_kind
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
