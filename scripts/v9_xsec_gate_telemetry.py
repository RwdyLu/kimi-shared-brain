#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_diagnostic_walkforward_report import load_rows


FAILURE_CATEGORIES = {
    "activity": {
        "active_rebalances40_ge_min",
        "time_in_market40_ge_min",
        "validation_active_rebalances40_ge_min",
        "validation_time_in_market40_ge_min",
    },
    "robustness": {
        "positive_3_of_4_years",
        "bootstrap_p5_ge_adjusted_min",
        "bootstrap_p5_confirm_ge_adjusted_min",
        "walk_forward_robust",
        "loo_all_returns_gt_0",
        "loo_min_sharpe_ge_min",
    },
    "edge_quality": {
        "sharpe20_ge_1_2",
        "sharpe40_ge_1",
        "benchmark_sharpe_excess_ge_0_10",
        "validation_sharpe20_ge_adjusted_min",
        "validation_sharpe40_gt_0",
        "validation_return20_gt_0",
    },
    "drawdown": {
        "max_dd20_le_25pct",
        "drawdown_ratio_le_0_80",
        "validation_max_dd20_le_30pct",
    },
    "concentration": {
        "top_symbol_share_le_60pct",
    },
    "cost_turnover": {
        "daily_turnover40_le_50pct",
        "validation_daily_turnover40_le_50pct",
    },
    "validation_flow": {
        "selection_passed_before_validation",
        "validation_usable",
    },
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def resolve_artifact(args: argparse.Namespace) -> Path:
    if args.artifact:
        return Path(args.artifact)
    state = read_json(Path(args.state))
    active = state.get("active_task") or {}
    progress_path = active.get("progress_path")
    if progress_path:
        return Path(str(progress_path))
    current = state.get("current_task")
    if current:
        return Path("artifacts/v9/contract_lab") / f"{current}.json"
    raise SystemExit("no artifact supplied and no active task in state")


def float_or(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def metric(row: dict[str, Any], *path: str, default: float = 0.0) -> float:
    cur: Any = row
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return float_or(cur, default)


def failed_checks(row: dict[str, Any]) -> list[str]:
    checks = row.get("advance_checks") or {}
    return [str(name) for name, passed in checks.items() if not passed]


def category_counts(fail_counts: dict[str, int]) -> dict[str, int]:
    out = {name: 0 for name in FAILURE_CATEGORIES}
    uncategorized = 0
    for check, count in fail_counts.items():
        matched = False
        for category, names in FAILURE_CATEGORIES.items():
            if check in names:
                out[category] += int(count)
                matched = True
        if not matched:
            uncategorized += int(count)
    if uncategorized:
        out["uncategorized"] = uncategorized
    return dict(sorted(out.items(), key=lambda item: item[1], reverse=True))


def compact_config(config: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "score_mode",
        "lookback_h",
        "skip_h",
        "rebalance_h",
        "k",
        "market_filter_h",
        "market_confirm_h",
        "market_drawdown_limit",
        "vol_target_ann",
        "drawdown_stop",
        "cooldown_h",
        "n_tranches",
    )
    return {key: config.get(key) for key in keys if key in config}


def row_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "config": compact_config(row.get("config") or {}),
        "advance_passed": bool(row.get("advance_passed")),
        "failed_checks": failed_checks(row),
        "selection": {
            "sharpe20": metric(row, "cost20", "sharpe"),
            "sharpe40": metric(row, "cost40", "sharpe"),
            "return20": metric(row, "cost20", "total_return"),
            "max_drawdown20": metric(row, "cost20", "max_drawdown"),
            "bootstrap_p5": metric(row, "cost20", "bootstrap_30d_sharpe_p5"),
            "benchmark_excess": metric(row, "cost20", "equal_weight_benchmark", "sharpe_excess"),
            "daily_turnover40": metric(row, "cost40", "daily_turnover"),
            "active_rebalances40": metric(row, "cost40", "active_rebalance_event_count"),
            "time_in_market40": metric(row, "cost40", "time_in_market_frac"),
            "top_symbol_share": metric(row, "cost20", "top_positive_symbol_share"),
        },
        "validation": {
            "sharpe20": metric(row, "validation", "cost20", "sharpe"),
            "return20": metric(row, "validation", "cost20", "total_return"),
            "max_drawdown20": metric(row, "validation", "cost20", "max_drawdown"),
            "active_rebalances40": metric(row, "validation", "cost40", "active_rebalance_event_count"),
            "time_in_market40": metric(row, "validation", "cost40", "time_in_market_frac"),
        },
    }


def top_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            bool(row.get("advance_passed")),
            -len(failed_checks(row)),
            metric(row, "cost20", "sharpe"),
            metric(row, "cost20", "bootstrap_30d_sharpe_p5"),
            -metric(row, "cost20", "max_drawdown"),
        ),
        reverse=True,
    )
    return [row_summary(row) for row in ordered[:limit]]


def recommendation(
    *,
    rows: list[dict[str, Any]],
    fail_counts: dict[str, int],
    fail_rates: dict[str, float],
    near_miss_count: int,
) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    if not rows:
        return [
            {
                "priority": "wait",
                "action": "wait_for_progress_rows",
                "reason": "No completed rows are available yet.",
            }
        ]
    if any(row.get("advance_passed") for row in rows):
        recs.append(
            {
                "priority": "high",
                "action": "run_family_registry_and_holdout_queue_after_task_finishes",
                "reason": "At least one train-only row has passed gates; do not authorize paper/live without holdout and paper checks.",
            }
        )
    if near_miss_count:
        recs.append(
            {
                "priority": "high",
                "action": "rescue_near_miss_configs_with_neighbor_grid",
                "reason": f"{near_miss_count} rows are within three failed checks; local neighbor search may be higher value than a broad preset sweep.",
            }
        )
    if fail_rates.get("positive_3_of_4_years", 0.0) >= 0.70:
        recs.append(
            {
                "priority": "high",
                "action": "de_prioritize_current_preset_until_year_robustness_improves",
                "reason": "Most rows fail positive-year robustness; this is a regime fragility signal, not a gate to relax.",
            }
        )
    if fail_rates.get("bootstrap_p5_ge_adjusted_min", 0.0) >= 0.60:
        recs.append(
            {
                "priority": "high",
                "action": "prefer_maximin_or_bootstrap_first_fitness",
                "reason": "Bootstrap p5 failures dominate; average Sharpe is not enough for a professional strategy.",
            }
        )
    activity_rate = max(
        fail_rates.get("active_rebalances40_ge_min", 0.0),
        fail_rates.get("time_in_market40_ge_min", 0.0),
    )
    if activity_rate >= 0.35:
        recs.append(
            {
                "priority": "medium",
                "action": "test_active_but_risk_capped_neighbors",
                "reason": "Many rows are too inactive; try shorter cooldowns, wider drawdown_stop, or less restrictive market confirmation while keeping holdout gates unchanged.",
            }
        )
    if fail_rates.get("benchmark_sharpe_excess_ge_0_10", 0.0) >= 0.50:
        recs.append(
            {
                "priority": "medium",
                "action": "compare_against_hq_dd_plateau_or_breadth_presets",
                "reason": "Current rows often fail to beat equal-weight benchmark after risk controls.",
            }
        )
    if fail_rates.get("top_symbol_share_le_60pct", 0.0) >= 0.25:
        recs.append(
            {
                "priority": "medium",
                "action": "increase_breadth_or_add_symbol_concentration_penalty",
                "reason": "Profit concentration is high; professional deployment should avoid one-symbol dependence.",
            }
        )
    if not recs:
        recs.append(
            {
                "priority": "observe",
                "action": "continue_current_task_until_more_rows_complete",
                "reason": "No dominant bottleneck is visible yet.",
            }
        )
    return recs


def build_report(artifact: Path, *, top_limit: int = 10) -> dict[str, Any]:
    rows, meta, source_kind = load_rows(artifact)
    total_rows = int(meta.get("total_rows") or len(rows))
    completed_rows = int(meta.get("completed_rows") or len(rows))
    fail_counter: Counter[str] = Counter()
    for row in rows:
        fail_counter.update(failed_checks(row))
    fail_counts = dict(fail_counter.most_common())
    denom = max(1, len(rows))
    fail_rates = {key: count / denom for key, count in fail_counts.items()}
    near_misses = [row for row in rows if not row.get("advance_passed") and 0 < len(failed_checks(row)) <= 3]
    report = {
        "kind": "xsec_gate_telemetry_v1",
        "created_at": now_utc(),
        "artifact": str(artifact),
        "source_kind": source_kind,
        "completed_rows": completed_rows,
        "total_rows": total_rows,
        "progress_fraction": completed_rows / max(1, total_rows),
        "pass_count": sum(1 for row in rows if row.get("advance_passed")),
        "near_miss_count": len(near_misses),
        "failure_counts": fail_counts,
        "failure_rates": fail_rates,
        "failure_categories": category_counts(fail_counts),
        "top_rows": top_rows(rows, top_limit),
        "near_miss_rows": top_rows(near_misses, min(top_limit, 10)),
        "recommendations": recommendation(
            rows=rows,
            fail_counts=fail_counts,
            fail_rates=fail_rates,
            near_miss_count=len(near_misses),
        ),
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    return report


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"created_at={report['created_at']}",
        f"source={report['source_kind']}",
        f"artifact={report['artifact']}",
        f"rows={report['completed_rows']}/{report['total_rows']} progress={report['progress_fraction']:.3f}",
        f"pass_count={report['pass_count']} near_miss_count={report['near_miss_count']}",
        "safety=paper:False live:False",
        "failure_counts:",
    ]
    for name, count in list((report.get("failure_counts") or {}).items())[:15]:
        rate = (report.get("failure_rates") or {}).get(name, 0.0)
        lines.append(f"- {name}: {count} ({rate:.1%})")
    lines.append("failure_categories:")
    for name, count in (report.get("failure_categories") or {}).items():
        lines.append(f"- {name}: {count}")
    lines.append("recommendations:")
    for rec in report.get("recommendations") or []:
        lines.append(f"- [{rec['priority']}] {rec['action']}: {rec['reason']}")
    lines.append("top_rows:")
    for row in report.get("top_rows") or []:
        sel = row.get("selection") or {}
        lines.append(
            "- pass={pass_} fails={fails} sel_sh20={sh:.3f} boot={boot:.3f} active={active:.0f} time={time:.3f} cfg={cfg}".format(
                pass_=row.get("advance_passed"),
                fails=",".join((row.get("failed_checks") or [])[:5]),
                sh=float_or(sel.get("sharpe20")),
                boot=float_or(sel.get("bootstrap_p5")),
                active=float_or(sel.get("active_rebalances40")),
                time=float_or(sel.get("time_in_market40")),
                cfg=json.dumps(row.get("config") or {}, sort_keys=True),
            )
        )
    return "\n".join(lines)


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    artifact = resolve_artifact(args)
    report = build_report(artifact, top_limit=args.top_limit)
    write_json(report, Path(args.out_json))
    write_text(format_text(report), Path(args.out_text))
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only XSEC gate telemetry and next-action report.")
    parser.add_argument("artifact", nargs="?", default="", help="Optional final .json or .progress.jsonl path")
    parser.add_argument("--state", default="state/v9_auto_research_state.json")
    parser.add_argument("--out-json", default="state/xsec_gate_telemetry.json")
    parser.add_argument("--out-text", default="state/xsec_gate_telemetry.txt")
    parser.add_argument("--top-limit", type=int, default=10)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=600.0)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    while True:
        report = run_once(args)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        else:
            print(format_text(report), flush=True)
        if not args.loop:
            return
        time.sleep(max(60.0, float(args.sleep_sec)))


if __name__ == "__main__":
    main()
