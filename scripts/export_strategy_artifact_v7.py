#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import data_health_gate as dhg


BASE = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = BASE / "artifacts"
DEFAULT_DATA_AUDIT = BASE / "data" / "audits" / "binance_kline_audit_summary.json"

ENGINE_FILES = [
    "scripts/lunar_genome_crypto_lab_v6.py",
    "scripts/lunar_genome_crypto_lab_v7_robust.py",
    "scripts/lunar_genome_symbol_local_search_v7_doc_tailfirst.py",
    "scripts/lunar_genome_symbol_validate_v7.py",
    "scripts/lunar_genome_symbol_walkforward_v7.py",
    "scripts/strategy_approval_gate_v7.py",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")
    tmp.replace(path)


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def short_hash(payload: Any, n: int = 16) -> str:
    return sha256_json(payload)[:n]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=BASE, text=True).strip()
    except Exception:
        return None


def flatten_candidates(archive: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for row in (archive.get("qualified") or []) + (archive.get("top") or []):
        genome = row.get("genome")
        symbol = row.get("symbol")
        if not symbol or not genome:
            continue
        cid = candidate_id(symbol, genome)
        if cid in seen:
            continue
        seen.add(cid)
        copy = dict(row)
        copy["candidate_id"] = cid
        rows.append(copy)
    return rows


def candidate_id(symbol: str, genome: dict[str, Any]) -> str:
    return f"{symbol}:{short_hash(genome)}"


def approval_by_candidate(approval: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for section in ["paper_ready", "validated", "top"]:
        for row in approval.get(section) or []:
            cid = row.get("candidate_id")
            if cid and cid not in out:
                out[cid] = row
    return out


def infer_status(approval_row: dict[str, Any] | None) -> str:
    if not approval_row:
        return "internal_candidate_only"
    if approval_row.get("paper_ready"):
        return "paper_ready_requires_manual_launch"
    if approval_row.get("validated"):
        return "validated_candidate_not_paper_ready"
    return "internal_candidate_only"


def compact_metrics(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") or row.get("internal_metrics") or {}
    keys = [
        "qualified_rows",
        "scenario_count",
        "survival_rate",
        "min_alpha",
        "avg_alpha",
        "min_return",
        "avg_return",
        "max_drawdown",
        "avg_trades_per_scenario",
        "max_trades_per_scenario",
        "dominant_regime",
        "router_active_frac",
        "avg_route_multiplier",
    ]
    return {k: metrics.get(k) for k in keys if k in metrics}


def engine_hashes() -> dict[str, Any]:
    hashes = {}
    for rel in ENGINE_FILES:
        path = BASE / rel
        hashes[rel] = sha256_file(path)
    return hashes


def find_symbol_manifest(data_audit: dict[str, Any], symbol: str) -> Path | None:
    for raw in data_audit.get("manifest_paths") or []:
        path = Path(raw)
        if not path.is_absolute():
            path = BASE / path
        if path.name.startswith(f"{symbol}_"):
            return path
    return None


def artifact_data_gate(symbol: str, timeframe: str, approval_args: dict[str, Any], data_audit: dict[str, Any], data_audit_path: Path) -> dict[str, Any]:
    manifest_path = find_symbol_manifest(data_audit, symbol)
    if not manifest_path:
        return {"allowed": False, "reason": "missing_symbol_manifest", "manifest_path": None}
    manifest = load_json(manifest_path)
    requested_start = approval_args.get("start") or data_audit.get("start") or manifest.get("requested_start_month")
    requested_end = approval_args.get("end") or data_audit.get("end") or manifest.get("requested_end_month")
    months_per_symbol = int(approval_args.get("months_per_symbol") or 1)
    gate = dhg.DataHealthGate(manifest_path.parent, timeframe, requested_start, requested_end, months_per_symbol)
    months = dhg.month_range(requested_start, requested_end)
    reason = gate.reject_reason(symbol, months)
    return {
        "allowed": reason is None,
        "reason": reason,
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "manifest_data_hash": manifest.get("data_hash"),
        "valid_for_research": bool(manifest.get("valid_for_research")),
        "valid_month_count": len(manifest.get("valid_months") or []),
        "valid_tradable_ranges": manifest.get("valid_tradable_ranges") or [],
        "data_audit_summary": str(data_audit_path),
        "data_audit_summary_hash": data_audit.get("summary_hash"),
    }


def write_readme(path: Path, manifest: dict[str, Any]) -> None:
    text = f"""# Strategy Artifact: {manifest['strategy_id']}

This artifact is an immutable research handoff for one GA candidate.

Approval status: `{manifest['approval_status']}`

Important rules:

- `internal_candidate_only` is not paper-ready and must not be routed to live trading.
- Freqtrade dry-run may only be launched after the approval gate marks an artifact paper-ready, or after manual override by the operator.
- Live trading requires a separate live-canary approval step and API keys are never stored in this artifact.

Current engine limitations:

- Trade-level parquet and full equity-curve parquet are not emitted by the current evaluator yet.
- The artifact stores genome, metrics, approval evidence, data audit hash, scenario details when available, and engine file hashes.
"""
    path.write_text(text)


def export_artifact(candidate: dict[str, Any], approval_row: dict[str, Any] | None, archive_path: Path, approval_path: Path | None, data_audit_path: Path, out_root: Path, tag: str, allow_invalid_data_artifact: bool) -> Path:
    symbol = candidate["symbol"]
    genome = candidate["genome"]
    cid = candidate["candidate_id"]
    genome_hash = cid.split(":", 1)[1]
    metrics = candidate.get("metrics") or {}
    approval_args = load_json(approval_path).get("args", {}) if approval_path and approval_path.exists() else {}
    data_audit = load_json(data_audit_path)
    timeframe = approval_args.get("timeframe") or "unknown"
    data_gate = artifact_data_gate(symbol, timeframe, approval_args, data_audit, data_audit_path) if data_audit else {"allowed": False, "reason": "missing_data_audit_summary"}
    if not data_gate.get("allowed") and not allow_invalid_data_artifact:
        raise SystemExit(f"Refusing to export artifact for invalid data gate: {symbol} {data_gate}")
    created = utc_now()
    safe_tag = tag or created.replace(":", "").replace("-", "")
    strategy_id = f"{symbol}_{genome_hash}_{safe_tag}"
    artifact_dir = out_root / strategy_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    status = infer_status(approval_row)
    data_audit_hash = sha256_file(data_audit_path) if data_audit_path.exists() else None
    manifest = {
        "schema_version": 1,
        "created_at": created,
        "strategy_id": strategy_id,
        "candidate_id": cid,
        "symbol": symbol,
        "timeframe": timeframe,
        "approval_status": status,
        "repo_commit": git_commit(),
        "engine_version": "lunar_genome_v7",
        "approval_gate_version": "v7",
        "approval_contract": {
            "internal_candidate_only": "GA discovery result only; not valid for paper or live.",
            "validated_candidate_not_paper_ready": "Passed independent validation but failed at least one paper-readiness stress.",
            "paper_ready_requires_manual_launch": "Passed approval gate; dry-run launch still requires manual operator action.",
            "live_canary": "Not produced by this exporter.",
        },
        "genome_hash": genome_hash,
        "engine_hashes": engine_hashes(),
        "data_audit_path": str(data_audit_path) if data_audit_path.exists() else None,
        "data_audit_sha256": data_audit_hash,
        "data_audit_summary_hash": data_audit.get("summary_hash"),
        "data_gate": data_gate,
        "data_manifest_hashes": {
            symbol: data_gate.get("manifest_sha256"),
        },
        "source_archive": str(archive_path),
        "source_archive_sha256": sha256_file(archive_path),
        "source_approval": str(approval_path) if approval_path else None,
        "source_approval_sha256": sha256_file(approval_path) if approval_path else None,
        "internal_metrics": compact_metrics(candidate),
        "selection_context": {
            "archive_epoch": load_json(archive_path).get("epoch"),
            "archive_qualified_count": load_json(archive_path).get("qualified_count"),
            "archive_top_count": len(load_json(archive_path).get("top") or []),
            "num_genomes_evaluated_before_selection": None,
            "num_genomes_note": "not emitted by current search archive; add explicit evaluation counter in next engine revision",
        },
        "fee_model": {
            "cost_bps_semantics": "per_side",
            "slippage_included": False,
            "spread_included": False,
            "maker_taker_modeled": False,
            "source": "simulate_symbol applies gross * cost_rate on buys and sells",
        },
        "approval_checks": summarize_approval(approval_row),
        "available_outputs": {
            "genome_json": True,
            "metrics_json": True,
            "approval_summary_json": bool(approval_row),
            "scenario_internal_json": bool((metrics.get("details") or [])),
            "trades_internal_parquet": False,
            "trades_recheck_parquet": False,
            "equity_curves_parquet": False,
            "quantstats_report_html": False,
        },
        "safety": {
            "contains_api_keys": False,
            "live_trading_enabled": False,
            "freqtrade_dry_run_enabled": False,
            "freqtrade_export_allowed": status in {"paper_ready", "paper_ready_requires_manual_launch"},
            "allowed_next_step": "approval_gate_or_dry_run_bridge_only_if_paper_ready",
        },
        "manual_approval": {
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "approval_reason": None,
            "max_allowed_stage": "none",
        },
    }

    save_json(artifact_dir / "genome.json", genome)
    save_json(artifact_dir / "metrics.json", metrics)
    if metrics.get("details"):
        save_json(artifact_dir / "scenario_internal.json", metrics.get("details"))
    if approval_row:
        save_json(artifact_dir / "approval_summary.json", approval_row)
    manifest["artifact_manifest_sha256_without_self"] = sha256_json(manifest)
    save_json(artifact_dir / "manifest.json", manifest)
    write_readme(artifact_dir / "README.md", manifest)
    return artifact_dir


def summarize_approval(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    out = {
        "validated": bool(row.get("validated")),
        "paper_ready": bool(row.get("paper_ready")),
        "deterministic_audit_passed": bool((row.get("deterministic_audit") or {}).get("passed")),
        "random_controls_passed": bool((row.get("random_controls") or {}).get("passed")),
        "independent_validation": summarize_check_list(row.get("independent_validation")),
        "cost_stress_passed": bool((row.get("cost_stress") or {}).get("passed")),
        "signal_delay_passed": bool((row.get("signal_delay") or {}).get("passed")),
        "parameter_jitter_passed": bool((row.get("parameter_jitter") or {}).get("passed")),
        "walkforward_passed": bool((row.get("walkforward") or {}).get("passed")),
        "monte_carlo_passed": bool((row.get("monte_carlo") or {}).get("passed")),
        "holdout_passed": bool((row.get("holdout") or {}).get("passed")),
        "adversarial_rows_written": row.get("adversarial_rows_written"),
    }
    return out


def summarize_check_list(value: Any) -> dict[str, Any]:
    rows = value or []
    if not isinstance(rows, list):
        return {"passed": False, "count": 0}
    return {
        "passed": bool(rows) and all(bool(row.get("passed")) for row in rows),
        "count": len(rows),
        "passed_count": sum(1 for row in rows if row.get("passed")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an immutable strategy artifact from a GA archive and approval output.")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--approval", default="")
    parser.add_argument("--candidate-id", default="")
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--out-root", default=str(DEFAULT_ARTIFACTS))
    parser.add_argument("--data-audit", default=str(DEFAULT_DATA_AUDIT))
    parser.add_argument("--tag", default="")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--allow-invalid-data-artifact", action="store_true")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    if not archive_path.is_absolute():
        archive_path = BASE / archive_path
    approval_path = Path(args.approval) if args.approval else None
    if approval_path and not approval_path.is_absolute():
        approval_path = BASE / approval_path
    data_audit_path = Path(args.data_audit)
    if not data_audit_path.is_absolute():
        data_audit_path = BASE / data_audit_path
    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = BASE / out_root

    archive = load_json(archive_path)
    approval = load_json(approval_path) if approval_path else {}
    candidates = flatten_candidates(archive)
    approval_rows = approval_by_candidate(approval)
    if not candidates:
        raise SystemExit(f"No candidates found in {archive_path}")

    if args.candidate_id:
        selected = [row for row in candidates if row["candidate_id"] == args.candidate_id]
    else:
        selected = candidates[args.candidate_index : args.candidate_index + max(1, args.limit)]
    if not selected:
        raise SystemExit("No selected candidates matched the request")

    exported = []
    for idx, row in enumerate(selected):
        tag = args.tag or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if len(selected) > 1:
            tag = f"{tag}_{idx + 1}"
        path = export_artifact(
            candidate=row,
            approval_row=approval_rows.get(row["candidate_id"]),
            archive_path=archive_path,
            approval_path=approval_path,
            data_audit_path=data_audit_path,
            out_root=out_root,
            tag=tag,
            allow_invalid_data_artifact=args.allow_invalid_data_artifact,
        )
        exported.append(str(path))
    print(json.dumps({"exported": exported}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
