#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.tsmom_rescue import build_tsmom_rescue_plan, write_tsmom_rescue_artifacts  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build train-only TSMOM near-miss rescue configs")
    parser.add_argument("artifact", help="TSMOM train-only artifact")
    parser.add_argument("--out-plan", required=True)
    parser.add_argument("--out-configs", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--budget-per-seed", type=int, default=25)
    parser.add_argument("--max-failures", type=int, default=2)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = json.loads(Path(args.artifact).read_text())
    meta = dict(payload.get("selection_validation") or {})
    meta["summary"] = dict(payload.get("summary") or {})
    plan = build_tsmom_rescue_plan(
        list(payload.get("rows") or []),
        meta=meta,
        source_artifact=args.artifact,
        top_k=args.top_k,
        budget_per_seed=args.budget_per_seed,
        max_failures=args.max_failures,
    )
    metadata = write_tsmom_rescue_artifacts(plan, Path(args.out_plan), Path(args.out_configs))
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
