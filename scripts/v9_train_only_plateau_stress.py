#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.xsec_ohlcv_factory import (  # noqa: E402
    OhlcvConfig,
    leave_one_symbol_summary,
    load_close_matrix,
    ohlcv_config_from_dict,
    simulate,
    utc_ts,
    walk_forward_summary,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve_path(path: str | Path, base: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else base / p


def config_key(config: dict[str, Any]) -> str:
    return json.dumps(
        {
            "k": int(config["k"]),
            "lookback_h": int(config["lookback_h"]),
            "market_filter_h": int(config["market_filter_h"]),
            "n_tranches": int(config.get("n_tranches", 1)),
            "rebalance_h": int(config["rebalance_h"]),
            "score_mode": str(config["score_mode"]),
            "skip_h": int(config.get("skip_h", 0)),
            "vol_target_ann": float(config["vol_target_ann"]),
        },
        sort_keys=True,
    )


def artifact_family_prefix(artifact: str) -> str:
    return Path(artifact).stem


def family_key(source_artifact: str, kind: str | None, config: dict[str, Any]) -> str:
    return json.dumps(
        {
            "artifact": artifact_family_prefix(source_artifact),
            "kind": kind,
            "k": int(config["k"]),
            "market_filter_h": int(config["market_filter_h"]),
            "rebalance_h": int(config["rebalance_h"]),
            "score_mode": str(config["score_mode"]),
            "n_tranches": int(config.get("n_tranches", 1)),
        },
        sort_keys=True,
    )


def selected_configs(
    artifact_path: Path,
    artifact_label: str,
    triage_path: Path | None,
    limit: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    configs: list[dict[str, Any]] = []
    if triage_path:
        triage = read_json(triage_path)
        for row in triage.get("ranked_candidates", []):
            if row.get("decision") != "shortlist_plateau_candidate":
                continue
            raw_artifact = str(row.get("artifact") or "")
            if raw_artifact != artifact_label and Path(raw_artifact).name != artifact_path.name:
                continue
            config = dict(row.get("config") or {})
            if not config:
                continue
            key = config_key(config)
            if key in seen:
                continue
            seen.add(key)
            configs.append(config)
            if len(configs) >= limit:
                return configs
        if configs:
            return configs

    payload = read_json(artifact_path)
    for row in payload.get("top", []) or payload.get("rows", []):
        if not row.get("advance_passed"):
            continue
        config = dict(row.get("config") or {})
        if not config:
            continue
        key = config_key(config)
        if key in seen:
            continue
        seen.add(key)
        configs.append(config)
        if len(configs) >= limit:
            return configs
    return configs


def first_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return default


def phase_offsets(rebalance_h: int, step_h: int) -> list[int]:
    if step_h <= 0:
        raise ValueError("phase step must be positive")
    return list(range(0, int(rebalance_h), int(step_h)))


def phase_stress(closes: Any, cfg: OhlcvConfig, *, cost_bps: float, phase_step_h: int) -> dict[str, Any]:
    variants = []
    for offset in phase_offsets(cfg.rebalance_h, phase_step_h):
        result = simulate(closes, cfg, cost_bps=cost_bps, bootstrap_iterations=0, phase_offset_h=offset)
        variants.append(
            {
                "offset_h": int(offset),
                "sharpe": float(result["sharpe"]),
                "total_return": float(result["total_return"]),
                "max_drawdown": float(result["max_drawdown"]),
                "daily_turnover": float(result["daily_turnover"]),
                "rebalance_event_count": int(result["rebalance_event_count"]),
            }
        )
    sharpes = [row["sharpe"] for row in variants]
    median = float(sorted(sharpes)[len(sharpes) // 2]) if sharpes else 0.0
    if sharpes and len(sharpes) % 2 == 0:
        mid = len(sharpes) // 2
        ordered = sorted(sharpes)
        median = float((ordered[mid - 1] + ordered[mid]) / 2.0)
    min_sharpe = min(sharpes) if sharpes else 0.0
    max_sharpe = max(sharpes) if sharpes else 0.0
    range_to_median = ((max_sharpe - min_sharpe) / median) if median > 0.0 else float("inf")
    return {
        "cost_bps": float(cost_bps),
        "phase_step_h": int(phase_step_h),
        "variants": variants,
        "min_sharpe": float(min_sharpe),
        "median_sharpe": float(median),
        "max_sharpe": float(max_sharpe),
        "range_to_median": float(range_to_median),
        "worst_offset_h": min(variants, key=lambda row: row["sharpe"])["offset_h"] if variants else None,
    }


def cost_stress(
    closes: Any,
    cfg: OhlcvConfig,
    *,
    base_cost_bps: float,
    multipliers: list[float],
) -> list[dict[str, Any]]:
    rows = []
    for multiplier in multipliers:
        cost_bps = float(base_cost_bps) * float(multiplier)
        result = simulate(closes, cfg, cost_bps=cost_bps, bootstrap_iterations=0)
        wf = walk_forward_summary(closes, cfg, cost_bps=cost_bps)
        loso = leave_one_symbol_summary(closes, cfg, cost_bps=cost_bps)
        rows.append(
            {
                "multiplier": float(multiplier),
                "cost_bps": float(cost_bps),
                "sharpe": float(result["sharpe"]),
                "total_return": float(result["total_return"]),
                "max_drawdown": float(result["max_drawdown"]),
                "walk_forward_q25": first_number(wf.get("q25_sharpe")),
                "walk_forward_passed": bool(wf.get("passed")),
                "leave_one_symbol_min_sharpe": first_number(loso.get("min_sharpe")),
                "leave_one_symbol_min_return": first_number(loso.get("min_return")),
                "leave_one_symbol_passed": bool(loso.get("passed")),
            }
        )
    return rows


def candidate_verdict(
    phase: dict[str, Any],
    cost_rows: list[dict[str, Any]],
    *,
    min_phase_sharpe: float,
    max_phase_range_to_median: float,
    cost15_min_sharpe: float,
    cost15_min_wf_q25: float,
    cost20_min_sharpe: float,
    cost20_min_loso_sharpe: float,
) -> dict[str, Any]:
    checks = {
        "phase_min_sharpe_ge_min": float(phase["min_sharpe"]) >= min_phase_sharpe,
        "phase_range_to_median_le_max": float(phase["range_to_median"]) <= max_phase_range_to_median,
    }
    for row in cost_rows:
        multiplier = float(row["multiplier"])
        if math.isclose(multiplier, 1.5):
            checks["cost_1p5_sharpe_ge_min"] = float(row["sharpe"]) >= cost15_min_sharpe
            checks["cost_1p5_wf_q25_ge_min"] = float(row["walk_forward_q25"]) >= cost15_min_wf_q25
        elif math.isclose(multiplier, 2.0):
            checks["cost_2p0_sharpe_ge_min"] = float(row["sharpe"]) >= cost20_min_sharpe
            checks["cost_2p0_loso_min_sharpe_gt_min"] = float(row["leave_one_symbol_min_sharpe"]) > cost20_min_loso_sharpe
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "passed": not failed,
        "decision": "train_only_plateau_stress_pass" if not failed else "rejected_train_stress",
        "checks": checks,
        "failed_checks": failed,
    }


def build_stress(
    artifact_path: Path,
    base: Path,
    *,
    triage_path: Path | None = None,
    limit: int = 4,
    phase_step_h: int = 24,
    base_cost_bps: float = 40.0,
    cost_multipliers: list[float] | None = None,
    min_phase_sharpe: float = 1.0,
    max_phase_range_to_median: float = 0.50,
    cost15_min_sharpe: float = 1.4,
    cost15_min_wf_q25: float = 0.8,
    cost20_min_sharpe: float = 1.0,
    cost20_min_loso_sharpe: float = 0.0,
) -> dict[str, Any]:
    artifact = read_json(artifact_path)
    artifact_kind = str(artifact.get("kind") or "")
    run_config = artifact.get("config") or {}
    symbols = tuple(run_config.get("symbols") or artifact.get("symbols") or (artifact.get("data") or {}).get("symbols") or [])
    if not symbols:
        raise ValueError("artifact has no symbols")
    train_start = str(run_config.get("train_start") or (artifact.get("train_window") or {}).get("start"))
    train_end = str(run_config.get("train_end") or (artifact.get("train_window") or {}).get("end"))
    embargo_start = str(run_config.get("embargo_start") or "2024-07-01")
    cache_dir = Path(str(run_config.get("cache_dir") or "data/binance_public_cache"))
    closes = load_close_matrix(cache_dir, symbols, utc_ts(train_start), utc_ts(train_end), utc_ts(embargo_start))
    configs = selected_configs(artifact_path, str(artifact_path), triage_path, limit)
    if not configs:
        raise ValueError("no selected configs found")
    multipliers = cost_multipliers or [1.5, 2.0]
    rows = []
    for raw in configs:
        cfg = ohlcv_config_from_dict(raw)
        phase = phase_stress(closes, cfg, cost_bps=base_cost_bps, phase_step_h=phase_step_h)
        costs = cost_stress(closes, cfg, base_cost_bps=base_cost_bps, multipliers=multipliers)
        verdict = candidate_verdict(
            phase,
            costs,
            min_phase_sharpe=min_phase_sharpe,
            max_phase_range_to_median=max_phase_range_to_median,
            cost15_min_sharpe=cost15_min_sharpe,
            cost15_min_wf_q25=cost15_min_wf_q25,
            cost20_min_sharpe=cost20_min_sharpe,
            cost20_min_loso_sharpe=cost20_min_loso_sharpe,
        )
        rows.append(
            {
                "config": raw,
                "family_key": family_key(str(artifact_path), artifact_kind, raw),
                "phase_stress": phase,
                "cost_stress": costs,
                "verdict": verdict,
            }
        )
    pass_count = sum(1 for row in rows if row["verdict"]["passed"])
    if pass_count == len(rows):
        family_decision = "family_train_only_plateau_stress_pass"
    elif pass_count == 0:
        family_decision = "family_rejected_train_stress"
    else:
        family_decision = "family_mixed_train_stress"
    return {
        "kind": "v9_train_only_plateau_stress_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": str(artifact_path),
        "source_kind": artifact_kind,
        "source_triage": str(triage_path) if triage_path else None,
        "holdout_accessed": False,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "data": {
            "train_start": train_start,
            "train_end": train_end,
            "embargo_start": embargo_start,
            "symbols": list(symbols),
            "loaded_first_dt": closes["dt"].iloc[0].isoformat(),
            "loaded_last_dt": closes["dt"].iloc[-1].isoformat(),
            "loaded_rows": int(len(closes)),
        },
        "thresholds": {
            "base_cost_bps": float(base_cost_bps),
            "phase_step_h": int(phase_step_h),
            "min_phase_sharpe": float(min_phase_sharpe),
            "max_phase_range_to_median": float(max_phase_range_to_median),
            "cost_1p5_min_sharpe": float(cost15_min_sharpe),
            "cost_1p5_min_wf_q25": float(cost15_min_wf_q25),
            "cost_2p0_min_sharpe": float(cost20_min_sharpe),
            "cost_2p0_min_loso_sharpe": float(cost20_min_loso_sharpe),
        },
        "summary": {
            "candidate_count": len(rows),
            "pass_count": pass_count,
            "reject_count": len(rows) - pass_count,
            "family_decision": family_decision,
        },
        "candidates": rows,
        "note": "Train-only phase and cost stress. This report does not authorize holdout, paper, live, or production trading.",
    }


def family_status_from_report(report: dict[str, Any]) -> dict[str, Any]:
    families: dict[str, dict[str, Any]] = {}
    family_decision = str((report.get("summary") or {}).get("family_decision") or "")
    source_artifact = str(report.get("source_artifact") or "")
    source_kind = str(report.get("source_kind") or "xsec_ohlcv_factory_v1_train_only_grid")
    for row in report.get("candidates", []):
        key = str(row.get("family_key") or "")
        if not key and source_artifact and row.get("config"):
            key = family_key(source_artifact, source_kind, row.get("config") or {})
        if not key:
            continue
        verdict = row.get("verdict") or {}
        failed = list(verdict.get("failed_checks") or [])
        current = families.setdefault(
            key,
            {
                "status": family_decision,
                "tags": [],
                "source_report": report.get("source_report"),
                "source_artifact": report.get("source_artifact"),
                "updated_at": report.get("created_at"),
                "candidate_count": 0,
                "failed_checks": {},
                "example_configs": [],
            },
        )
        current["candidate_count"] += 1
        if row.get("config") and len(current["example_configs"]) < 5:
            current["example_configs"].append(row.get("config"))
        for name in failed:
            current["failed_checks"][name] = int(current["failed_checks"].get(name, 0)) + 1
        if any(name.startswith("cost_") for name in failed):
            current["tags"].append("cost_sensitive")
        if "phase_range_to_median_le_max" in failed:
            current["tags"].append("phase_sensitive")
    for status in families.values():
        tags = set(status.get("tags") or [])
        if status.get("status") == "family_rejected_train_stress" or "cost_sensitive" in tags:
            tags.add("needs_turnover_reduction")
        status["tags"] = sorted(tags)
        status["failed_checks"] = dict(sorted((status.get("failed_checks") or {}).items()))
    return {
        "kind": "v9_train_only_family_status_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_report": report.get("source_report"),
        "families": families,
    }


def merge_family_status(path: Path, update: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        existing = read_json(path)
    else:
        existing = {
            "kind": "v9_train_only_family_status_v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "families": {},
        }
    families = dict(existing.get("families") or {})
    families.update(update.get("families") or {})
    return {
        "kind": "v9_train_only_family_status_v1",
        "created_at": existing.get("created_at") or update.get("created_at"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "families": families,
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def compact_config(config: dict[str, Any]) -> str:
    keys = ("lookback_h", "market_filter_h", "rebalance_h", "vol_target_ann", "k", "score_mode", "skip_h", "n_tranches")
    return ",".join(f"{key}={config.get(key)}" for key in keys if key in config)


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TRAIN_ONLY_PLATEAU_STRESS",
        "",
        f"created_at: `{report['created_at']}`",
        f"source_artifact: `{report['source_artifact']}`",
        f"source_triage: `{report.get('source_triage')}`",
        f"holdout_accessed: `{report['holdout_accessed']}`",
        f"holdout_authorized: `{report['holdout_authorized']}`",
        f"paper_trading_authorized: `{report['paper_trading_authorized']}`",
        f"live_trading_authorized: `{report['live_trading_authorized']}`",
        "",
        "## Summary",
        "",
        f"- candidate_count: `{report['summary']['candidate_count']}`",
        f"- pass_count: `{report['summary']['pass_count']}`",
        f"- reject_count: `{report['summary']['reject_count']}`",
        f"- family_decision: `{report['summary']['family_decision']}`",
        "",
        "## Phase Matrix",
        "",
        "| candidate | verdict | min sharpe | range/median | offset sharpes | config |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for idx, row in enumerate(report["candidates"], 1):
        phase = row["phase_stress"]
        offsets = ", ".join(f"{v['offset_h']}h:{fmt(v['sharpe'])}" for v in phase["variants"])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    row["verdict"]["decision"],
                    fmt(phase["min_sharpe"]),
                    fmt(phase["range_to_median"]),
                    offsets,
                    f"`{compact_config(row['config'])}`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Cost Stress", "", "| candidate | multiplier | cost bps | sharpe | wf q25 | loso min sharpe | return | max dd |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for idx, row in enumerate(report["candidates"], 1):
        for cost in row["cost_stress"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(idx),
                        fmt(cost["multiplier"], 1),
                        fmt(cost["cost_bps"], 1),
                        fmt(cost["sharpe"]),
                        fmt(cost["walk_forward_q25"]),
                        fmt(cost["leave_one_symbol_min_sharpe"]),
                        fmt(cost["total_return"]),
                        fmt(cost["max_drawdown"]),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Safety", "", report["note"]])
    return "\n".join(lines) + "\n"


def parse_multipliers(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train-only phase and cost stress for plateau shortlist candidates")
    parser.add_argument("artifact")
    parser.add_argument("--base", default=".")
    parser.add_argument("--triage")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--family-status-out", default="")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--phase-step-h", type=int, default=24)
    parser.add_argument("--base-cost-bps", type=float, default=40.0)
    parser.add_argument("--cost-multipliers", default="1.5,2.0")
    parser.add_argument("--min-phase-sharpe", type=float, default=1.0)
    parser.add_argument("--max-phase-range-to-median", type=float, default=0.50)
    parser.add_argument("--cost15-min-sharpe", type=float, default=1.4)
    parser.add_argument("--cost15-min-wf-q25", type=float, default=0.8)
    parser.add_argument("--cost20-min-sharpe", type=float, default=1.0)
    parser.add_argument("--cost20-min-loso-sharpe", type=float, default=0.0)
    args = parser.parse_args()

    base = Path(args.base)
    artifact = resolve_path(args.artifact, base)
    triage = resolve_path(args.triage, base) if args.triage else None
    report = build_stress(
        artifact,
        base,
        triage_path=triage,
        limit=args.limit,
        phase_step_h=args.phase_step_h,
        base_cost_bps=args.base_cost_bps,
        cost_multipliers=parse_multipliers(args.cost_multipliers),
        min_phase_sharpe=args.min_phase_sharpe,
        max_phase_range_to_median=args.max_phase_range_to_median,
        cost15_min_sharpe=args.cost15_min_sharpe,
        cost15_min_wf_q25=args.cost15_min_wf_q25,
        cost20_min_sharpe=args.cost20_min_sharpe,
        cost20_min_loso_sharpe=args.cost20_min_loso_sharpe,
    )
    out_json = resolve_path(args.out_json, base)
    out_md = resolve_path(args.out_md, base)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    report["source_report"] = str(out_json)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    out_md.write_text(format_markdown(report))
    if args.family_status_out:
        status_path = resolve_path(args.family_status_out, base)
        update = family_status_from_report(report)
        merged = merge_family_status(status_path, update)
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
