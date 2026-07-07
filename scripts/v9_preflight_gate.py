#!/usr/bin/env python3
"""Aggregate v9 train-only gates into one fail-closed manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v9_preflight_1"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build v9 train-only preflight GO/NO_GO manifest")
    ap.add_argument("--prereg", required=True)
    ap.add_argument("--regime-report", required=True)
    ap.add_argument("--freeze-report", required=True)
    ap.add_argument("--exec-summary", required=True)
    ap.add_argument("--exec-analysis", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", default="")
    ap.add_argument("--train-cutoff", default="2024-06-30")
    ap.add_argument("--human-ack", action="store_true")
    return ap.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def extract_regime_hash_from_prereg(text: str) -> str | None:
    match = re.search(r"sha256:\s*`?([a-fA-F0-9]{64})`?", text)
    return match.group(1).lower() if match else None


def extract_failure_counts(exec_analysis: dict[str, Any]) -> dict[str, int]:
    raw = (exec_analysis.get("gates") or {}).get("failure_summary") or {}
    return {str(k): int(v) for k, v in raw.items()}


def bool_gate(value: Any) -> bool:
    return bool(value) is True


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "prereg": Path(args.prereg),
        "regime_report": Path(args.regime_report),
        "freeze_report": Path(args.freeze_report),
        "exec_summary": Path(args.exec_summary),
        "exec_analysis": Path(args.exec_analysis),
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "inputs": {name: str(path) for name, path in paths.items()},
            "gates": {"all_inputs_present": False, "missing_inputs": missing},
            "verdict": "NO_GO",
            "blocking_gates": ["all_inputs_present"],
            "holdout_authorized": False,
        }

    prereg_text = paths["prereg"].read_text()
    prereg_hash = sha256_file(paths["prereg"])
    regime = load_json(paths["regime_report"])
    freeze = load_json(paths["freeze_report"])
    exec_summary = load_json(paths["exec_summary"])
    exec_analysis = load_json(paths["exec_analysis"])

    prereg_regime_hash = extract_regime_hash_from_prereg(prereg_text)
    regime_hash = regime.get("config_sha256")
    exec_regime_hash = exec_summary.get("regime_config_sha256")
    freeze_regime_hash = ((freeze.get("regime_gate") or {}).get("config_sha256"))
    exec_integrity = exec_analysis.get("integrity") or {}
    exec_gates = exec_analysis.get("gates") or {}
    exec_meta = exec_analysis.get("meta") or {}

    gates = {
        "all_inputs_present": True,
        "prereg_hash_present": bool(prereg_hash),
        "regime_config_sha_in_prereg": bool(prereg_regime_hash),
        "regime_config_sha_matches_prereg": bool(prereg_regime_hash and regime_hash and prereg_regime_hash == str(regime_hash).lower()),
        "freeze_regime_sha_matches_regime": bool(freeze_regime_hash and regime_hash and str(freeze_regime_hash).lower() == str(regime_hash).lower()),
        "exec_regime_sha_matches_regime": bool(exec_regime_hash and regime_hash and str(exec_regime_hash).lower() == str(regime_hash).lower()),
        "train_only_flag": bool(exec_meta.get("train_only") is True),
        "train_only_max_ts_ok": bool(exec_integrity.get("cutoff_ok") is True),
        "embargo_guard_present": "2024-07-01" in prereg_text,
        "freeze_family_frozen": bool(freeze.get("family_frozen") is True and int(freeze.get("selected_count", 0)) >= 1),
        "execution_integrity_passed": bool(
            exec_integrity.get("cutoff_ok") is True
            and float(exec_integrity.get("cash_recon_max_err", 999.0)) <= 1e-6
            and float(exec_integrity.get("equity_recon_max_err", 999.0)) <= 1e-6
            and float(exec_integrity.get("fee_model_max_err", 999.0)) <= 1e-8
            and exec_integrity.get("monotonic_ts") is True
        ),
        "execution_analysis_passed": bool(exec_gates.get("passed") is True),
        "failure_counts": extract_failure_counts(exec_analysis),
    }
    blocking = [key for key, value in gates.items() if isinstance(value, bool) and not value]
    verdict = "GO" if not blocking else "NO_GO"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {
            "prereg": str(paths["prereg"]),
            "prereg_sha256": prereg_hash,
            "prereg_regime_config_sha256": prereg_regime_hash,
            "regime_report": str(paths["regime_report"]),
            "regime_report_sha256": sha256_file(paths["regime_report"]),
            "regime_config_sha256": regime_hash,
            "freeze_report": str(paths["freeze_report"]),
            "freeze_report_sha256": sha256_file(paths["freeze_report"]),
            "exec_summary": str(paths["exec_summary"]),
            "exec_summary_sha256": sha256_file(paths["exec_summary"]),
            "exec_analysis": str(paths["exec_analysis"]),
            "exec_analysis_sha256": sha256_file(paths["exec_analysis"]),
        },
        "gates": gates,
        "verdict": verdict,
        "blocking_gates": blocking,
        "holdout_authorized": bool(verdict == "GO" and args.human_ack),
        "human_ack": bool(args.human_ack),
        "note": "Train-only procedural preflight. GO does not imply profitability.",
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# v9 Preflight Gate",
        "",
        f"generated_at: {payload['generated_at']}",
        f"verdict: `{payload['verdict']}`",
        f"holdout_authorized: `{payload['holdout_authorized']}`",
        "",
        "This is a train-only procedural gate. It does not imply profitability.",
        "",
        "## Blocking Gates",
        "",
    ]
    if payload["blocking_gates"]:
        for gate in payload["blocking_gates"]:
            lines.append(f"- {gate}")
    else:
        lines.append("- none")
    lines.extend(["", "## Gates", "", "| gate | value |", "|---|---:|"])
    for key, value in payload["gates"].items():
        if isinstance(value, dict):
            lines.append(f"| {key} | `{json.dumps(value, sort_keys=True)}` |")
        else:
            lines.append(f"| {key} | `{value}` |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    payload = build_manifest(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    md = Path(args.md) if args.md else out.with_suffix(".md")
    write_markdown(payload, md)
    print(json.dumps({
        "out": str(out),
        "md": str(md),
        "verdict": payload["verdict"],
        "holdout_authorized": payload["holdout_authorized"],
        "blocking_gates": payload["blocking_gates"],
    }, indent=2, sort_keys=True))
    return 0 if payload["verdict"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
