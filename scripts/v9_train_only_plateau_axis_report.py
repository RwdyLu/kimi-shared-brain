#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


AXES = ("lookback_h", "rebalance_h", "market_filter_h", "vol_target_ann", "k", "skip_h", "score_mode")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def numeric_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return left == right


def changed_axes(config: dict[str, Any], center: dict[str, Any]) -> list[str]:
    return [axis for axis in AXES if axis in center and not numeric_equal(config.get(axis), center.get(axis))]


def validation_sharpe20(row: dict[str, Any]) -> float | None:
    value = ((row.get("validation") or {}).get("cost20") or {}).get("sharpe")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pass_stats(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    values = [validation_sharpe20(row) for row in rows]
    valid = [value for value in values if value is not None]
    pass_count = sum(1 for value in valid if value >= threshold)
    total = len(rows)
    fail_count = total - pass_count
    return {
        "pass_count": int(pass_count),
        "fail_count": int(fail_count),
        "total": int(total),
        "pass_fraction": float(pass_count / total) if total else 0.0,
        "min_sharpe20": min(valid) if valid else None,
        "mean_sharpe20": float(sum(valid) / len(valid)) if valid else None,
        "max_sharpe20": max(valid) if valid else None,
    }


def build_axis_report(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    summary = payload.get("summary", {}) or {}
    selection_validation = payload.get("selection_validation", {}) or {}
    plateau = selection_validation.get("plateau_stability") or {}
    center = plateau.get("center_config") or {}
    if not center:
        raise ValueError("artifact has no plateau_stability.center_config")
    threshold = float(plateau.get("validation_sharpe20_min") or 1.0)
    rows = payload.get("rows", [])
    neighbors = [row for row in rows if changed_axes(row.get("config", {}) or {}, center)]
    overall = pass_stats(neighbors, threshold)
    expected_total = int(plateau.get("neighbor_total") or overall["total"])
    expected_pass = int(plateau.get("neighbor_pass_count") or overall["pass_count"])
    reconciled = expected_total == overall["total"] and expected_pass == overall["pass_count"]

    axes: list[dict[str, Any]] = []
    for axis in AXES:
        if axis not in center:
            continue
        changed = [row for row in neighbors if axis in changed_axes(row.get("config", {}) or {}, center)]
        values: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in neighbors:
            cfg = row.get("config", {}) or {}
            values[str(cfg.get(axis))].append(row)
        changed_stats = pass_stats(changed, threshold)
        if changed_stats["total"] == 0:
            continue
        axes.append(
            {
                "axis": axis,
                "center_value": center.get(axis),
                "changed": changed_stats,
                "values": [
                    {"value": value, **pass_stats(value_rows, threshold)}
                    for value, value_rows in sorted(values.items(), key=lambda item: item[0])
                ],
            }
        )
    axes.sort(key=lambda row: (row["changed"]["pass_fraction"], -row["changed"]["total"], row["axis"]))

    return {
        "artifact": str(path),
        "kind": payload.get("kind"),
        "decision": "train_only_plateau_axis_report",
        "summary": {
            "accepted_train_only": bool(summary.get("accepted_train_only")),
            "holdout_authorized": bool(summary.get("holdout_authorized")),
            "paper_trading_authorized": bool(summary.get("paper_trading_authorized")),
            "live_trading_authorized": bool(summary.get("live_trading_authorized")),
        },
        "data": payload.get("data", {}),
        "plateau": plateau,
        "threshold": threshold,
        "overall_neighbors": overall,
        "reconciled_with_plateau": bool(reconciled),
        "axes": axes,
    }


def format_text(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) or {}
    plateau = report.get("plateau", {}) or {}
    overall = report.get("overall_neighbors", {}) or {}
    lines = [
        f"decision={report['decision']}",
        "safety="
        f"holdout:{summary.get('holdout_authorized')} "
        f"paper:{summary.get('paper_trading_authorized')} "
        f"live:{summary.get('live_trading_authorized')}",
        "overall="
        f"neighbors:{overall.get('pass_count')}/{overall.get('total')} "
        f"frac:{fmt(overall.get('pass_fraction'))} "
        f"threshold:{fmt(report.get('threshold'))} "
        f"reconciled:{report.get('reconciled_with_plateau')}",
        "plateau="
        f"passed:{plateau.get('passed')} "
        f"center_sharpe20:{fmt(plateau.get('center_validation_sharpe20'))} "
        f"best_neighbor:{fmt(plateau.get('best_neighbor_validation_sharpe20'))} "
        f"center_not_spike:{plateau.get('center_not_spike')}",
    ]
    for axis in report.get("axes", []):
        changed = axis["changed"]
        lines.append(
            "axis="
            f"{axis['axis']} center:{axis.get('center_value')} "
            f"changed_pass:{changed['pass_count']}/{changed['total']} "
            f"frac:{fmt(changed['pass_fraction'])} "
            f"mean:{fmt(changed.get('mean_sharpe20'))} "
            f"min:{fmt(changed.get('min_sharpe20'))} "
            f"max:{fmt(changed.get('max_sharpe20'))}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only plateau neighbor axis report for train-only artifacts")
    parser.add_argument("artifact", help="xsec_ohlcv_factory plateau JSON artifact")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args()
    report = build_axis_report(Path(args.artifact))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(report))


if __name__ == "__main__":
    main()
