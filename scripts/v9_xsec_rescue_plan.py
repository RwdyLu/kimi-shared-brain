from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.xsec_rescue import (
    DEFAULT_RESCUE_BUDGET_PER_SEED,
    DEFAULT_RESCUE_TOP_K,
    build_rescue_plan,
    rescue_artifact_paths,
    write_rescue_artifacts,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a train-only XSEC diagnostic rescue plan")
    parser.add_argument("artifact", help="Completed XSEC .json artifact")
    parser.add_argument("--top-k", type=int, default=DEFAULT_RESCUE_TOP_K)
    parser.add_argument("--budget-per-seed", type=int, default=DEFAULT_RESCUE_BUDGET_PER_SEED)
    parser.add_argument("--out-plan", default="")
    parser.add_argument("--out-configs", default="")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    artifact = Path(args.artifact)
    payload = json.loads(artifact.read_text())
    rows = list(payload.get("rows", []))
    meta = dict(payload.get("selection_validation", {}) or {})
    meta["summary"] = dict(payload.get("summary", {}) or {})
    plan = build_rescue_plan(
        rows,
        meta=meta,
        source_artifact=str(artifact),
        top_k=args.top_k,
        budget_per_seed=args.budget_per_seed,
    )
    default_plan, default_configs = rescue_artifact_paths(str(artifact))
    plan_path = Path(args.out_plan) if args.out_plan else default_plan
    config_path = Path(args.out_configs) if args.out_configs else default_configs
    metadata = write_rescue_artifacts(plan, plan_path, config_path)
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
