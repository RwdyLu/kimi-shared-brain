#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


REMEDIATION_TRANCHES = (2, 3, 4)
REMEDIATION_REBALANCES_H = (240, 360, 480)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def required_base_config(config: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "lookback_h",
        "skip_h",
        "rebalance_h",
        "k",
        "score_mode",
        "market_filter_h",
        "vol_target_ann",
        "n_tranches",
    )
    missing = [key for key in keys if key not in config]
    if missing:
        raise ValueError(f"family example config missing keys: {missing}")
    return {key: config[key] for key in keys}


def config_fingerprint(config: dict[str, Any]) -> str:
    payload = {key: config[key] for key in sorted(config) if key not in {"parent_family", "remediation"}}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def family_is_turnover_remediation_target(status: dict[str, Any]) -> bool:
    tags = set(str(tag) for tag in (status.get("tags") or []))
    return "needs_turnover_reduction" in tags


def build_variants_for_family(family_key: str, status: dict[str, Any]) -> list[dict[str, Any]]:
    examples = status.get("example_configs") or []
    if not examples:
        return []
    base = required_base_config(dict(examples[0]))
    variants = []
    for n_tranches in REMEDIATION_TRANCHES:
        for rebalance_h in REMEDIATION_REBALANCES_H:
            config = dict(base)
            config["n_tranches"] = int(n_tranches)
            config["rebalance_h"] = int(rebalance_h)
            config["parent_family"] = family_key
            config["remediation"] = "turnover_reduction_tranche_cadence"
            config["config_fingerprint"] = config_fingerprint(config)
            variants.append(config)
    unique: dict[str, dict[str, Any]] = {}
    for variant in variants:
        unique[variant["config_fingerprint"]] = variant
    return list(unique.values())


def build_plan(status_path: Path, *, max_families: int = 10) -> dict[str, Any]:
    payload = read_json(status_path)
    families = payload.get("families") or {}
    configs: list[dict[str, Any]] = []
    selected = []
    for family_key, status in families.items():
        if len(selected) >= max_families:
            break
        if not isinstance(status, dict) or not family_is_turnover_remediation_target(status):
            continue
        variants = build_variants_for_family(str(family_key), status)
        if not variants:
            continue
        selected.append(
            {
                "family_key": family_key,
                "status": status.get("status"),
                "tags": status.get("tags") or [],
                "source_artifact": status.get("source_artifact"),
                "source_report": status.get("source_report"),
                "variant_count": len(variants),
            }
        )
        configs.extend(variants)
    return {
        "kind": "v9_xsec_turnover_remediation_plan_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_family_status": str(status_path),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "remediation": {
            "reason": "Prior train-only stress marked these families as cost/phase sensitive.",
            "n_tranches": list(REMEDIATION_TRANCHES),
            "rebalances_h": list(REMEDIATION_REBALANCES_H),
            "gate": "Run through normal train-only xsec factory and the same phase+cost stress checks; no holdout authorization.",
        },
        "selected_families": selected,
        "rescue_config_count": len(configs),
        "configs": configs,
    }


def write_outputs(plan: dict[str, Any], out_plan: Path, out_configs: Path) -> dict[str, Any]:
    out_plan.parent.mkdir(parents=True, exist_ok=True)
    out_configs.parent.mkdir(parents=True, exist_ok=True)
    out_plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    out_configs.write_text(json.dumps({"configs": plan["configs"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return {
        "out_plan": str(out_plan),
        "out_configs": str(out_configs),
        "selected_family_count": len(plan["selected_families"]),
        "rescue_config_count": len(plan["configs"]),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build train-only turnover remediation configs for rejected XSEC families")
    parser.add_argument("--family-status", default="artifacts/v9/reviews/FAMILY_STATUS.json")
    parser.add_argument("--out-plan", required=True)
    parser.add_argument("--out-configs", required=True)
    parser.add_argument("--max-families", type=int, default=10)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    plan = build_plan(Path(args.family_status), max_families=args.max_families)
    metadata = write_outputs(plan, Path(args.out_plan), Path(args.out_configs))
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
