#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def accepted_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in payload.get("rows", []) if row.get("advance_passed")]


def metric_view(row: dict[str, Any]) -> dict[str, Any]:
    selection = row.get("selection", {}) or {}
    validation = row.get("validation", {}) or {}
    sel20 = selection.get("cost20") or row.get("cost20", {}) or {}
    sel40 = selection.get("cost40") or row.get("cost40", {}) or {}
    val20 = validation.get("cost20") or {}
    val40 = validation.get("cost40") or {}
    bench = sel20.get("equal_weight_benchmark") or {}
    drop_one = row.get("drop_one_lookback") or {}
    return {
        "config": row.get("config", {}),
        "selection": {
            "sharpe20": sel20.get("sharpe"),
            "sharpe40": sel40.get("sharpe"),
            "total_return40": sel40.get("total_return"),
            "max_drawdown40": sel40.get("max_drawdown"),
            "total_return20": sel20.get("total_return"),
            "max_drawdown20": sel20.get("max_drawdown"),
            "bootstrap_30d_sharpe_p5": sel20.get("bootstrap_30d_sharpe_p5"),
            "bootstrap_30d_sharpe_p5_confirm": sel20.get("bootstrap_30d_sharpe_p5_confirm"),
            "top_positive_symbol_share": sel20.get("top_positive_symbol_share"),
            "positive_symbol_count": sel20.get("positive_symbol_count"),
            "symbol_count": sel20.get("symbol_count"),
            "positive_active_yearly_bucket_count": sel20.get("positive_active_yearly_bucket_count"),
            "active_yearly_bucket_count": sel20.get("active_yearly_bucket_count"),
            "daily_turnover": sel20.get("daily_turnover"),
            "benchmark_sharpe_excess": bench.get("sharpe_excess"),
            "drawdown_ratio": bench.get("drawdown_ratio"),
        },
        "validation": {
            "sharpe20": val20.get("sharpe"),
            "sharpe40": val40.get("sharpe"),
            "total_return40": val40.get("total_return"),
            "max_drawdown40": val40.get("max_drawdown"),
            "total_return20": val20.get("total_return"),
            "max_drawdown20": val20.get("max_drawdown"),
            "positive_symbol_count": val20.get("positive_symbol_count"),
            "symbol_count": val20.get("symbol_count"),
            "positive_active_yearly_bucket_count": val20.get("positive_active_yearly_bucket_count"),
            "active_yearly_bucket_count": val20.get("active_yearly_bucket_count"),
        },
        "drop_one_lookback": {
            "passed": drop_one.get("passed"),
            "threshold_sharpe20": drop_one.get("threshold_sharpe20"),
            "rows": [
                {
                    "dropped_lookback_h": r.get("dropped_lookback_h"),
                    "sharpe20": r.get("sharpe20"),
                    "total_return20": r.get("total_return20"),
                    "max_drawdown20": r.get("max_drawdown20"),
                    "passed": r.get("passed"),
                }
                for r in drop_one.get("rows", [])
            ],
        }
        if drop_one
        else {},
        "checks": row.get("advance_checks", {}),
    }


def build_review(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    summary = payload.get("summary", {}) or {}
    rows = accepted_rows(payload)
    top = metric_view(rows[0]) if rows else None
    all_passes = [metric_view(row) for row in rows]
    return {
        "artifact": str(path),
        "kind": payload.get("kind"),
        "decision": "train_only_manual_review_required" if summary.get("accepted_train_only") else "train_only_no_candidate",
        "accepted_train_only": bool(summary.get("accepted_train_only")),
        "pass_count": int(summary.get("pass_count") or len(rows)),
        "rows": int(summary.get("rows") or len(payload.get("rows", []))),
        "holdout_authorized": bool(summary.get("holdout_authorized")),
        "paper_trading_authorized": bool(summary.get("paper_trading_authorized")),
        "live_trading_authorized": bool(summary.get("live_trading_authorized")),
        "data": payload.get("data", {}),
        "selection_validation": payload.get("selection_validation", {}),
        "top_pass": top,
        "all_passes": all_passes,
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_text(review: dict[str, Any]) -> str:
    top = review.get("top_pass") or {}
    all_passes = review.get("all_passes") or []
    selection = top.get("selection") or {}
    validation = top.get("validation") or {}
    drop_one = top.get("drop_one_lookback") or {}
    config = top.get("config") or {}
    data = review.get("data") or {}
    sv = review.get("selection_validation") or {}
    lines = [
        f"decision={review['decision']}",
        f"passes={review['pass_count']}/{review['rows']}",
        "safety="
        f"holdout:{review['holdout_authorized']} "
        f"paper:{review['paper_trading_authorized']} "
        f"live:{review['live_trading_authorized']}",
        f"data_fingerprint={data.get('fingerprint')}",
        f"effective_trials={sv.get('effective_trials')} prior_trials={sv.get('prior_trials')}",
    ]
    plateau = sv.get("plateau_stability") or {}
    if plateau:
        lines.append(
            "plateau="
            f"passed:{plateau.get('passed')} "
            f"neighbors:{plateau.get('neighbor_pass_count')}/{plateau.get('neighbor_total')} "
            f"frac:{fmt(plateau.get('neighbor_pass_fraction'))} "
            f"center_sharpe20:{fmt(plateau.get('center_validation_sharpe20'))} "
            f"best_neighbor:{fmt(plateau.get('best_neighbor_validation_sharpe20'))} "
            f"center_not_spike:{plateau.get('center_not_spike')}"
        )
    if top:
        lines.extend(
            [
                f"top_config={json.dumps(config, sort_keys=True)}",
                "selection="
                f"sharpe20:{fmt(selection.get('sharpe20'))} "
                f"sharpe40:{fmt(selection.get('sharpe40'))} "
                f"dd20:{fmt(selection.get('max_drawdown20'))} "
                f"dd40:{fmt(selection.get('max_drawdown40'))} "
                f"return20:{fmt(selection.get('total_return20'))} "
                f"boot:{fmt(selection.get('bootstrap_30d_sharpe_p5'))} "
                f"confirm:{fmt(selection.get('bootstrap_30d_sharpe_p5_confirm'))} "
                f"active_years:{fmt(selection.get('positive_active_yearly_bucket_count'), 0)}/{fmt(selection.get('active_yearly_bucket_count'), 0)} "
                f"symbols:{fmt(selection.get('positive_symbol_count'), 0)}/{fmt(selection.get('symbol_count'), 0)} "
                f"turnover:{fmt(selection.get('daily_turnover'))}",
                "validation="
                f"sharpe20:{fmt(validation.get('sharpe20'))} "
                f"sharpe40:{fmt(validation.get('sharpe40'))} "
                f"dd20:{fmt(validation.get('max_drawdown20'))} "
                f"dd40:{fmt(validation.get('max_drawdown40'))} "
                f"return20:{fmt(validation.get('total_return20'))} "
                f"active_years:{fmt(validation.get('positive_active_yearly_bucket_count'), 0)}/{fmt(validation.get('active_yearly_bucket_count'), 0)} "
                f"symbols:{fmt(validation.get('positive_symbol_count'), 0)}/{fmt(validation.get('symbol_count'), 0)}",
            ]
        )
        if drop_one:
            rows = drop_one.get("rows") or []
            compact = ",".join(
                f"{r.get('dropped_lookback_h')}h:{fmt(r.get('sharpe20'))}:{r.get('passed')}" for r in rows
            )
            lines.append(
                "drop_one="
                f"passed:{drop_one.get('passed')} "
                f"threshold:{fmt(drop_one.get('threshold_sharpe20'))} "
                f"rows:{compact}"
            )
        if all_passes:
            lines.append(f"all_pass_count={len(all_passes)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a train-only candidate artifact")
    parser.add_argument("artifact", help="xsec_ohlcv_factory JSON artifact")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    review = build_review(Path(args.artifact))
    if args.format == "json":
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(review))


if __name__ == "__main__":
    main()
