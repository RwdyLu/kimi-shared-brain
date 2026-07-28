#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import SYMBOLS, load_close_matrix, sharpe  # noqa: E402
from v9.contract.xsec_ohlcv_factory import (  # noqa: E402
    advance_checks,
    annual_bucket,
    block_bootstrap_p5,
    bootstrap_threshold,
    data_fingerprint,
    max_drawdown_from_returns,
)


def hourly_returns(closes: pd.DataFrame) -> pd.DataFrame:
    symbols = [col for col in closes.columns if col != "dt"]
    out = closes[symbols].pct_change().shift(-1).iloc[:-1].fillna(0.0)
    out.index = pd.to_datetime(closes["dt"].iloc[:-1])
    return out


def equal_weight_returns(returns: pd.DataFrame) -> pd.Series:
    return returns.mean(axis=1).fillna(0.0)


def top_positive_symbol_share(symbol_pnl: dict[str, float]) -> float:
    positives = [max(float(value), 0.0) for value in symbol_pnl.values()]
    total = sum(positives)
    return max(positives) / total if total > 0.0 else 0.0


def yearly_metrics(period_returns: pd.Series, rebalance_h: int) -> tuple[dict[str, dict[str, float | int]], int]:
    by_year: dict[str, dict[str, float | int]] = {}
    for bucket in ["2021", "2022", "2023", "2024H1"]:
        subset = period_returns[[annual_bucket(pd.Timestamp(ts)) == bucket for ts in period_returns.index]]
        by_year[bucket] = {
            "periods": int(len(subset)),
            "net_return": float((1.0 + subset).prod() - 1.0) if len(subset) else 0.0,
            "sharpe": sharpe(subset, 8760.0 / float(rebalance_h)) if len(subset) else 0.0,
        }
    return by_year, sum(1 for row in by_year.values() if float(row["net_return"]) > 0.0)


def result_from_hourly_returns(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    rebalance_h: int,
    bootstrap_iterations: int,
    bootstrap_seed: int,
    symbol_pnl: dict[str, float] | None = None,
) -> dict[str, Any]:
    aligned = pd.concat([strategy_returns.rename("strategy"), benchmark_returns.rename("benchmark")], axis=1).dropna()
    strategy = aligned["strategy"].fillna(0.0)
    benchmark = aligned["benchmark"].fillna(0.0)
    period = (1.0 + strategy).resample(f"{rebalance_h}h").prod() - 1.0
    daily = (1.0 + strategy).resample("1D").prod() - 1.0
    bench_period = (1.0 + benchmark).resample(f"{rebalance_h}h").prod() - 1.0
    bench_daily = benchmark
    strategy_sharpe = sharpe(period, 8760.0 / float(rebalance_h))
    benchmark_sharpe = sharpe(bench_period, 8760.0 / float(rebalance_h))
    strategy_dd = max_drawdown_from_returns(strategy)
    benchmark_dd = max_drawdown_from_returns(bench_daily)
    yearly, yearly_positive_count = yearly_metrics(period, rebalance_h)
    symbol_pnl = symbol_pnl or {}
    return {
        "cost_bps": 0.0,
        "total_return": float((1.0 + strategy).prod() - 1.0),
        "net_pnl": float(((1.0 + strategy).prod() - 1.0) * 10_000.0),
        "sharpe": strategy_sharpe,
        "max_drawdown": strategy_dd,
        "daily_turnover": 0.0,
        "avg_gross_exposure": 1.0,
        "avg_long_exposure": 1.0,
        "avg_short_exposure": 0.0,
        "avg_rebalance_scale": 1.0,
        "rebalance_event_count": 0,
        "yearly": yearly,
        "yearly_positive_count": int(yearly_positive_count),
        "symbol_pnl": symbol_pnl,
        "top_positive_symbol_share": top_positive_symbol_share(symbol_pnl),
        "legs": {
            "long_gross_return": float((1.0 + strategy).prod() - 1.0),
            "long_gross_sharpe": strategy_sharpe,
            "short_gross_return": 0.0,
            "short_gross_sharpe": 0.0,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
        },
        "bootstrap_30d_sharpe_p5": block_bootstrap_p5(daily, iterations=bootstrap_iterations, seed=bootstrap_seed),
        "bootstrap_seed": int(bootstrap_seed),
        "bootstrap_iterations": int(bootstrap_iterations),
        "equal_weight_benchmark": {
            "sharpe": benchmark_sharpe,
            "max_drawdown": benchmark_dd,
            "sharpe_excess": strategy_sharpe - benchmark_sharpe,
            "drawdown_ratio": strategy_dd / benchmark_dd if benchmark_dd > 0.0 else 1.0,
        },
    }


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    benchmark = result.get("equal_weight_benchmark") or {}
    return {
        "sharpe": result.get("sharpe"),
        "total_return": result.get("total_return"),
        "max_drawdown": result.get("max_drawdown"),
        "yearly_positive_count": result.get("yearly_positive_count"),
        "yearly": result.get("yearly"),
        "bootstrap_30d_sharpe_p5": result.get("bootstrap_30d_sharpe_p5"),
        "top_positive_symbol_share": result.get("top_positive_symbol_share"),
        "benchmark_sharpe_excess": benchmark.get("sharpe_excess"),
        "benchmark_drawdown_ratio": benchmark.get("drawdown_ratio"),
    }


def failed_checks(checks: dict[str, bool]) -> list[str]:
    return [name for name, passed in checks.items() if not bool(passed)]


def reference_reports(
    closes: pd.DataFrame,
    *,
    rebalance_h: int,
    bootstrap_iterations: int,
    bootstrap_p5_min: float,
) -> list[dict[str, Any]]:
    returns = hourly_returns(closes)
    benchmark = equal_weight_returns(returns)
    symbols = list(returns.columns)
    references: list[tuple[str, pd.Series, dict[str, float]]] = []
    ew_symbol_pnl = {symbol: float((returns[symbol] / len(symbols)).sum() * 10_000.0) for symbol in symbols}
    references.append(("equal_weight_8_hold", benchmark, ew_symbol_pnl))
    if "BTCUSDT" in returns.columns:
        references.append(("btc_buy_and_hold", returns["BTCUSDT"], {"BTCUSDT": float(returns["BTCUSDT"].sum() * 10_000.0)}))
    rows = []
    for idx, (name, series, symbol_pnl) in enumerate(references):
        result20 = result_from_hourly_returns(
            series,
            benchmark,
            rebalance_h=rebalance_h,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=20260710 + idx,
            symbol_pnl=symbol_pnl,
        )
        result40 = dict(result20)
        checks = advance_checks(result20, result40, bootstrap_p5_min=bootstrap_p5_min)
        rows.append(
            {
                "name": name,
                "metrics": compact_result(result20),
                "checks": checks,
                "failed_checks": failed_checks(checks),
                "advance_passed": all(checks.values()),
            }
        )
    return rows


def sign_permuted_null_summary(
    closes: pd.DataFrame,
    *,
    rebalance_h: int,
    bootstrap_iterations: int,
    bootstrap_p5_min: float,
    trials: int,
    seed: int,
) -> dict[str, Any]:
    returns = hourly_returns(closes)
    benchmark = equal_weight_returns(returns)
    rng = random.Random(seed)
    pass_counts: Counter[str] = Counter()
    fail_counts: Counter[str] = Counter()
    all_passed = 0
    example_failures: list[dict[str, Any]] = []
    block_h = 24 * 30
    blocks = np.arange(len(benchmark)) // block_h
    for trial in range(int(trials)):
        signs_by_block = {int(block): (1.0 if rng.random() >= 0.5 else -1.0) for block in np.unique(blocks)}
        signs = pd.Series([signs_by_block[int(block)] for block in blocks], index=benchmark.index)
        permuted = benchmark * signs
        result20 = result_from_hourly_returns(
            permuted,
            benchmark,
            rebalance_h=rebalance_h,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=seed + trial + 1,
            symbol_pnl={},
        )
        result40 = dict(result20)
        checks = advance_checks(result20, result40, bootstrap_p5_min=bootstrap_p5_min)
        if all(checks.values()):
            all_passed += 1
        for name, passed in checks.items():
            if passed:
                pass_counts[name] += 1
            else:
                fail_counts[name] += 1
        if len(example_failures) < 5 and not all(checks.values()):
            example_failures.append(
                {
                    "trial": trial,
                    "metrics": compact_result(result20),
                    "failed_checks": failed_checks(checks),
                }
            )
    denominator = max(1, int(trials))
    return {
        "kind": "equal_weight_30d_block_sign_permutation",
        "trials": int(trials),
        "seed": int(seed),
        "all_pass_rate": all_passed / denominator,
        "gate_pass_rates": {name: count / denominator for name, count in sorted(pass_counts.items())},
        "gate_fail_counts": dict(sorted(fail_counts.items())),
        "example_failures": example_failures,
    }


def classify_decision(reference_rows: list[dict[str, Any]], null_summary: dict[str, Any]) -> str:
    by_name = {row["name"]: set(row["failed_checks"]) for row in reference_rows}
    ew_fail = by_name.get("equal_weight_8_hold", set())
    btc_fail = by_name.get("btc_buy_and_hold", set())
    timing_gates = {"positive_3_of_4_years", "max_dd20_le_25pct", "drawdown_ratio_le_0_80"}
    if (ew_fail & timing_gates) and (btc_fail & timing_gates):
        return "benchmarks_fail_timing_or_drawdown_gates_add_regime_overlay_before_more_selection_grids"
    if null_summary.get("all_pass_rate", 0.0) > 0.01:
        return "null_can_pass_gate_stack_review_multiple_testing_pressure"
    return "benchmarks_do_not_prove_gate_infeasibility_continue_with_targeted_research"


def build_report_from_closes(
    closes: pd.DataFrame,
    *,
    train_start: str,
    train_end: str,
    embargo_start: str,
    symbols: tuple[str, ...],
    rebalance_h: int,
    prior_trials: int,
    n_trials: int,
    bootstrap_iterations: int,
    null_trials: int,
    null_seed: int,
) -> dict[str, Any]:
    effective_trials = max(1, int(prior_trials) + int(n_trials))
    bootstrap_p5_min = bootstrap_threshold(effective_trials)
    references = reference_reports(
        closes,
        rebalance_h=rebalance_h,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_p5_min=bootstrap_p5_min,
    )
    null_summary = sign_permuted_null_summary(
        closes,
        rebalance_h=rebalance_h,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_p5_min=bootstrap_p5_min,
        trials=null_trials,
        seed=null_seed,
    )
    return {
        "kind": "v9_xsec_gate_feasibility_audit_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": classify_decision(references, null_summary),
        "train_window": {"start": train_start, "end": train_end, "embargo_start": embargo_start},
        "data": {
            "fingerprint": data_fingerprint(closes),
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
            "symbols": list(symbols),
        },
        "gate_context": {
            "rebalance_h": int(rebalance_h),
            "prior_trials": int(prior_trials),
            "n_trials": int(n_trials),
            "effective_trials": int(effective_trials),
            "bootstrap_p5_min": float(bootstrap_p5_min),
            "bootstrap_iterations": int(bootstrap_iterations),
            "null_trials": int(null_trials),
        },
        "references": references,
        "null_summary": null_summary,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "note": (
            "Train-only gate feasibility audit. It reads no holdout data and does not authorize paper or live trading. "
            "The references are diagnostics, not trade recommendations."
        ),
    }


def build_report(
    *,
    cache_dir: Path,
    symbols: tuple[str, ...],
    train_start: str,
    train_end: str,
    embargo_start: str,
    rebalance_h: int,
    prior_trials: int,
    n_trials: int,
    bootstrap_iterations: int,
    null_trials: int,
    null_seed: int,
) -> dict[str, Any]:
    closes = load_close_matrix(cache_dir, symbols, utc_ts(train_start), utc_ts(train_end), utc_ts(embargo_start))
    return build_report_from_closes(
        closes,
        train_start=train_start,
        train_end=train_end,
        embargo_start=embargo_start,
        symbols=symbols,
        rebalance_h=rebalance_h,
        prior_trials=prior_trials,
        n_trials=n_trials,
        bootstrap_iterations=bootstrap_iterations,
        null_trials=null_trials,
        null_seed=null_seed,
    )


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# V9 XSec Gate Feasibility Audit",
        "",
        f"created_at: `{report['created_at']}`",
        f"decision: `{report['decision']}`",
        "",
        "This is train-only research. It does not authorize holdout, paper trading, or live trading.",
        "",
        "## Gate Context",
        "",
    ]
    for key, value in report["gate_context"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## References", ""])
    for row in report["references"]:
        metrics = row["metrics"]
        lines.append(f"### {row['name']}")
        lines.append(f"- advance_passed: `{row['advance_passed']}`")
        lines.append(f"- failed_checks: `{','.join(row['failed_checks']) or 'none'}`")
        lines.append(
            "- metrics: "
            f"sharpe `{fmt(metrics.get('sharpe'))}`, "
            f"return `{fmt(metrics.get('total_return'))}`, "
            f"dd `{fmt(metrics.get('max_drawdown'))}`, "
            f"year_pos `{metrics.get('yearly_positive_count')}`, "
            f"boot `{fmt(metrics.get('bootstrap_30d_sharpe_p5'))}`, "
            f"bench_excess `{fmt(metrics.get('benchmark_sharpe_excess'))}`, "
            f"dd_ratio `{fmt(metrics.get('benchmark_drawdown_ratio'))}`"
        )
        yearly = metrics.get("yearly") or {}
        yearly_text = ", ".join(f"{bucket}:{fmt(values.get('net_return'))}" for bucket, values in yearly.items())
        lines.append(f"- yearly_return: `{yearly_text}`")
        lines.append("")
    null_summary = report["null_summary"]
    lines.extend(
        [
            "## Null Summary",
            "",
            f"- kind: `{null_summary['kind']}`",
            f"- trials: `{null_summary['trials']}`",
            f"- all_pass_rate: `{fmt(null_summary['all_pass_rate'])}`",
            f"- gate_fail_counts: `{json.dumps(null_summary['gate_fail_counts'], sort_keys=True)}`",
            "",
            f"note: `{report['note']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train-only feasibility audit for XSEC OHLCV advance gates")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--symbols", default=",".join(SYMBOLS))
    parser.add_argument("--train-start", default="2018-01-01")
    parser.add_argument("--train-end", default="2024-05-31 23:59:59")
    parser.add_argument("--embargo-start", default="2024-07-01")
    parser.add_argument("--rebalance-h", type=int, default=240)
    parser.add_argument("--prior-trials", type=int, default=0)
    parser.add_argument("--n-trials", type=int, default=2)
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--null-trials", type=int, default=50)
    parser.add_argument("--null-seed", type=int, default=20260710)
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    symbols = tuple(item.strip() for item in args.symbols.split(",") if item.strip())
    report = build_report(
        cache_dir=Path(args.cache_dir),
        symbols=symbols,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        rebalance_h=args.rebalance_h,
        prior_trials=args.prior_trials,
        n_trials=args.n_trials,
        bootstrap_iterations=args.bootstrap_iterations,
        null_trials=args.null_trials,
        null_seed=args.null_seed,
    )
    text = format_markdown(report)
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.out_md:
        out = Path(args.out_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(text)


if __name__ == "__main__":
    main()
