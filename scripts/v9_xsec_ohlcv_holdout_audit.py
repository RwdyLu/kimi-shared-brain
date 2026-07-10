#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import load_close_matrix  # noqa: E402
from v9.contract.xsec_ohlcv_factory import (  # noqa: E402
    OhlcvConfig,
    data_fingerprint,
    ohlcv_config_from_dict,
    simulate,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def top_accepted_row(payload: dict[str, Any]) -> dict[str, Any]:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    raise ValueError("artifact has no accepted train-only row")


def canonical_config(value: Any) -> dict[str, Any]:
    out = dict(value or {})
    out.setdefault("n_tranches", 1)
    return out


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_config(value), sort_keys=True)


def selected_accepted_row(payload: dict[str, Any], target_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if target_config is None:
        return top_accepted_row(payload)
    target_config_sig = canonical_json(target_config)
    for row in payload.get("rows", []):
        if row.get("advance_passed") and canonical_json(row.get("config")) == target_config_sig:
            return row
    raise ValueError("artifact has no accepted train-only row matching target config")


def split_window(payload: dict[str, Any], split: str, holdout_start: str, holdout_end: str) -> tuple[str, str]:
    cfg = payload.get("config") or {}
    if split == "train":
        return str(cfg.get("train_start", "2017-08-01")), str(cfg.get("train_end", "2024-06-30 23:59:59"))
    return holdout_start, holdout_end


def require_holdout_authorized(split: str, holdout_authorized: bool) -> None:
    if split == "holdout" and not holdout_authorized:
        raise SystemExit("refusing to read holdout data: pass --holdout-authorized only after explicit approval")


def compact_metrics(result: dict[str, Any]) -> dict[str, Any]:
    benchmark = result.get("equal_weight_benchmark") or {}
    legs = result.get("legs") or {}
    return {
        "sharpe": result.get("sharpe"),
        "total_return": result.get("total_return"),
        "max_drawdown": result.get("max_drawdown"),
        "daily_turnover": result.get("daily_turnover"),
        "avg_gross_exposure": result.get("avg_gross_exposure"),
        "positive_symbol_count": result.get("positive_symbol_count"),
        "symbol_count": result.get("symbol_count"),
        "top_positive_symbol_share": result.get("top_positive_symbol_share"),
        "bootstrap_30d_sharpe_p5": result.get("bootstrap_30d_sharpe_p5"),
        "symbol_pnl": result.get("symbol_pnl"),
        "yearly_positive_count": result.get("yearly_positive_count"),
        "yearly": result.get("yearly"),
        "benchmark_sharpe_excess": benchmark.get("sharpe_excess"),
        "benchmark_drawdown_ratio": benchmark.get("drawdown_ratio"),
        "long_gross_return": legs.get("long_gross_return"),
        "short_gross_return": legs.get("short_gross_return"),
    }


def decision_from_costs(split: str, costs: dict[str, dict[str, Any]]) -> tuple[str, dict[str, bool]]:
    cost20 = costs.get("20bps", {})
    cost40 = costs.get("40bps", {})
    prefix = "holdout" if split == "holdout" else "train_audit"
    checks = {
        f"{prefix}_20bps_sharpe_ge_0_7": float(cost20.get("sharpe", 0.0) or 0.0) >= 0.70,
        f"{prefix}_20bps_return_gt_0": float(cost20.get("total_return", 0.0) or 0.0) > 0.0,
        f"{prefix}_20bps_drawdown_le_25pct": float(cost20.get("max_drawdown", 1.0) or 1.0) <= 0.25,
        f"{prefix}_40bps_sharpe_gt_0": float(cost40.get("sharpe", 0.0) or 0.0) > 0.0,
        f"{prefix}_40bps_return_gt_0": float(cost40.get("total_return", 0.0) or 0.0) > 0.0,
        f"{prefix}_top_symbol_share_le_65pct": float(cost20.get("top_positive_symbol_share", 1.0) or 1.0) <= 0.65,
    }
    if split == "holdout" and all(checks.values()):
        return "holdout_promising_manual_review_required", checks
    if split == "holdout":
        return "holdout_failed_do_not_paper_trade", checks
    if all(checks.values()):
        return "train_split_audit_passed_holdout_still_unauthorized", checks
    return "train_split_audit_failed_do_not_request_holdout", checks


def build_report(
    artifact: Path,
    cache_dir: Path,
    split: str,
    holdout_start: str,
    holdout_end: str,
    costs_bps: tuple[float, ...],
    bootstrap_iterations: int,
    holdout_authorized: bool = False,
    target_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_holdout_authorized(split, holdout_authorized)
    payload = read_json(artifact)
    row = selected_accepted_row(payload, target_config=target_config)
    cfg = ohlcv_config_from_dict(dict(row["config"]))
    start_text, end_text = split_window(payload, split, holdout_start, holdout_end)
    embargo = utc_ts("2100-01-01") if split == "holdout" else utc_ts(str((payload.get("config") or {}).get("embargo_start", "2024-07-01")))
    closes = load_close_matrix(
        cache_dir,
        tuple(payload["symbols"]),
        utc_ts(start_text),
        utc_ts(end_text),
        embargo,
    )
    costs: dict[str, dict[str, Any]] = {}
    for cost in costs_bps:
        result = simulate(
            closes,
            cfg,
            float(cost),
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed_value=20260709 + int(cost * 10),
        )
        costs[f"{int(cost)}bps"] = compact_metrics(result)
    decision, checks = decision_from_costs(split, costs)
    return {
        "kind": "xsec_ohlcv_holdout_audit_v1",
        "decision": decision,
        "split": split,
        "source_artifact": str(artifact),
        "target_config": row["config"],
        "requested_window": {"start": start_text, "end": end_text},
        "data": {
            "fingerprint": data_fingerprint(closes),
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
            "symbols": list(payload["symbols"]),
        },
        "costs": costs,
        "checks": checks,
        "holdout_authorized": bool(holdout_authorized),
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "note": (
            "XSEC train/holdout audit. Train split is safe for pre-authorization testing; "
            "holdout split requires explicit --holdout-authorized and still does not authorize paper or live trading."
        ),
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_text(report: dict[str, Any]) -> str:
    data = report["data"]
    lines = [
        f"decision={report['decision']}",
        f"split={report['split']}",
        "safety="
        f"holdout:{report['holdout_authorized']} "
        f"paper:{report['paper_trading_authorized']} "
        f"live:{report['live_trading_authorized']}",
        f"source_artifact={report['source_artifact']}",
        f"target_config={json.dumps(report['target_config'], sort_keys=True)}",
        f"data=rows:{data['rows']} first:{data['first_dt']} last:{data['last_dt']} symbols:{len(data['symbols'])}",
    ]
    for label, row in report["costs"].items():
        lines.append(
            f"{label}="
            f"sharpe:{fmt(row.get('sharpe'))} "
            f"return:{fmt(row.get('total_return'))} "
            f"dd:{fmt(row.get('max_drawdown'))} "
            f"turnover:{fmt(row.get('daily_turnover'))} "
            f"top_symbol_share:{fmt(row.get('top_positive_symbol_share'))} "
            f"boot:{fmt(row.get('bootstrap_30d_sharpe_p5'))}"
        )
    lines.append("checks=" + ",".join(f"{key}:{value}" for key, value in report["checks"].items()))
    lines.append(f"note={report['note']}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XSEC OHLCV train/holdout audit with explicit holdout gate")
    parser.add_argument("artifact", help="XSEC train-only artifact with accepted row")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--split", choices=("train", "holdout"), default="train")
    parser.add_argument("--holdout-start", default="2024-07-01")
    parser.add_argument("--holdout-end", default="2026-05-31 23:59:59")
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--holdout-authorized", action="store_true")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--out-json")
    parser.add_argument("--out-text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    costs = tuple(float(item.strip()) for item in args.costs_bps.split(",") if item.strip())
    report = build_report(
        artifact=Path(args.artifact),
        cache_dir=Path(args.cache_dir),
        split=args.split,
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        costs_bps=costs,
        bootstrap_iterations=args.bootstrap_iterations,
        holdout_authorized=args.holdout_authorized,
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
