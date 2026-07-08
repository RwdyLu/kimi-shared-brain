#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.simulator import utc_ts
from v9.contract.tsmom_factory import TsmomConfig, simulate
from v9.contract.xsec_momentum import load_close_matrix


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def top_accepted_row(payload: dict[str, Any]) -> dict[str, Any]:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    raise ValueError("artifact has no accepted train-only row")


def decision_from_costs(costs: dict[str, dict[str, Any]]) -> tuple[str, dict[str, bool]]:
    cost20 = costs.get("20bps", {})
    cost40 = costs.get("40bps", {})
    checks = {
        "holdout_20bps_sharpe_ge_0_7": float(cost20.get("sharpe", 0.0) or 0.0) >= 0.70,
        "holdout_20bps_return_gt_0": float(cost20.get("total_return", 0.0) or 0.0) > 0.0,
        "holdout_20bps_drawdown_le_25pct": float(cost20.get("max_drawdown", 1.0) or 1.0) <= 0.25,
        "holdout_40bps_sharpe_gt_0": float(cost40.get("sharpe", 0.0) or 0.0) > 0.0,
        "holdout_40bps_return_gt_0": float(cost40.get("total_return", 0.0) or 0.0) > 0.0,
    }
    if all(checks.values()):
        return "holdout_promising_manual_review_required", checks
    return "holdout_failed_do_not_paper_trade", checks


def compact_metrics(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "sharpe": result.get("sharpe"),
        "total_return": result.get("total_return"),
        "max_drawdown": result.get("max_drawdown"),
        "daily_turnover": result.get("daily_turnover"),
        "avg_gross_exposure": result.get("avg_gross_exposure"),
        "rebalance_event_count": result.get("rebalance_event_count"),
        "positive_symbol_count": result.get("positive_symbol_count"),
        "symbol_count": result.get("symbol_count"),
        "top_positive_symbol_share": result.get("top_positive_symbol_share"),
        "bootstrap_30d_sharpe_p5": result.get("bootstrap_30d_sharpe_p5"),
        "symbol_pnl": result.get("symbol_pnl"),
    }


def build_report(
    artifact: Path,
    cache_dir: Path,
    holdout_start: str,
    holdout_end: str,
    costs_bps: tuple[float, ...],
    bootstrap_iterations: int,
) -> dict[str, Any]:
    payload = read_json(artifact)
    row = top_accepted_row(payload)
    cfg = TsmomConfig(**row["config"])
    lookbacks_h = tuple(int(v) for v in row["lookbacks_h"])
    start = utc_ts(holdout_start)
    end = utc_ts(holdout_end)
    closes = load_close_matrix(cache_dir, tuple(payload["symbols"]), start, end, utc_ts("2100-01-01"))
    costs: dict[str, dict[str, Any]] = {}
    for cost in costs_bps:
        result = simulate(
            closes,
            cfg,
            lookbacks_h,
            float(cost),
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed_value=20260708 + int(cost),
        )
        costs[f"{int(cost)}bps"] = compact_metrics(result)
    decision, checks = decision_from_costs(costs)
    return {
        "kind": "tsmom_holdout_audit_v1",
        "decision": decision,
        "source_artifact": str(artifact),
        "target_config": row["config"],
        "target_lookbacks_h": list(lookbacks_h),
        "holdout_requested": {"start": holdout_start, "end": holdout_end},
        "holdout_data": {
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
            "symbols": list(payload["symbols"]),
        },
        "costs": costs,
        "checks": checks,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "note": "Read-only holdout audit. It does not authorize paper trading or live trading.",
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_text(report: dict[str, Any]) -> str:
    data = report["holdout_data"]
    lines = [
        f"decision={report['decision']}",
        "safety="
        f"holdout:{report['holdout_authorized']} "
        f"paper:{report['paper_trading_authorized']} "
        f"live:{report['live_trading_authorized']}",
        f"source_artifact={report['source_artifact']}",
        f"target_config={json.dumps(report['target_config'], sort_keys=True)}",
        f"target_lookbacks_h={report['target_lookbacks_h']}",
        f"holdout_data=rows:{data['rows']} first:{data['first_dt']} last:{data['last_dt']} symbols:{len(data['symbols'])}",
    ]
    for label, row in report["costs"].items():
        lines.append(
            f"{label}="
            f"sharpe:{fmt(row.get('sharpe'))} "
            f"return:{fmt(row.get('total_return'))} "
            f"dd:{fmt(row.get('max_drawdown'))} "
            f"turnover:{fmt(row.get('daily_turnover'))} "
            f"symbols:{fmt(row.get('positive_symbol_count'), 0)}/{fmt(row.get('symbol_count'), 0)} "
            f"boot:{fmt(row.get('bootstrap_30d_sharpe_p5'))}"
        )
    lines.append("checks=" + ",".join(f"{key}:{value}" for key, value in report["checks"].items()))
    lines.append(f"note={report['note']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only TSMOM holdout audit")
    parser.add_argument("artifact", help="TSMOM train-only artifact with accepted row")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--holdout-start", default="2024-07-01")
    parser.add_argument("--holdout-end", default="2026-05-31 23:59:59")
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--out-json")
    parser.add_argument("--out-text")
    args = parser.parse_args()
    costs = tuple(float(item.strip()) for item in args.costs_bps.split(",") if item.strip())
    report = build_report(
        artifact=Path(args.artifact),
        cache_dir=Path(args.cache_dir),
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        costs_bps=costs,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    text = format_text(report)
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.out_text:
        out = Path(args.out_text)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text)


if __name__ == "__main__":
    main()
