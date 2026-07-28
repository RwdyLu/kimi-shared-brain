#!/usr/bin/env python3
"""Analyze train-only execution/order event logs.

This analyzer is intentionally scoped to execution events from the current
spot/DCA evaluator. It does not compute round-trip win rate, profit factor,
holding period, or per-trade CVaR.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    return build_arg_parser().parse_args()


def parse_args_from_list(argv: list[str]) -> argparse.Namespace:
    return build_arg_parser().parse_args(argv)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Analyze train-only execution/order event JSONL")
    ap.add_argument("--input", required=True)
    ap.add_argument("--cutoff", default="2024-06-30 23:59:59")
    ap.add_argument("--out", default="artifacts/v9/trade_logs/execution_analysis.json")
    ap.add_argument("--md", default="artifacts/v9/trade_logs/execution_analysis.md")
    ap.add_argument("--max-drawdown", type=float, default=0.20)
    ap.add_argument("--min-secondary-regime-events", type=int, default=100)
    ap.add_argument("--cash-tolerance", type=float, default=1e-6)
    ap.add_argument("--equity-tolerance", type=float, default=1e-6)
    ap.add_argument("--fee-tolerance", type=float, default=1e-8)
    return ap


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"empty execution log: {path}")
    return rows


def to_ts(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        return pd.Timestamp(value).tz_convert("UTC") if pd.Timestamp(value).tzinfo else pd.Timestamp(value, tz="UTC")
    except Exception:
        return None


def max_drawdown(values: list[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def quantile(values: list[float], q: float) -> float | None:
    xs = sorted(v for v in values if math.isfinite(v))
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def daily_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    for row in rows:
        ts = to_ts(row.get("ts"))
        equity = float(row.get("equity_after", 0.0))
        if ts is not None and equity > 0:
            points.append((ts, equity))
    if not points:
        return {"n_days": 0, "sharpe": None, "max_dd": 0.0}
    df = pd.DataFrame(points, columns=["ts", "equity"]).sort_values("ts")
    daily = df.set_index("ts")["equity"].resample("1D").last().dropna()
    rets = daily.pct_change().dropna()
    sharpe = None
    if len(rets) >= 2:
        std = float(rets.std(ddof=1))
        if std > 0 and math.isfinite(std):
            sharpe = float(rets.mean()) / std * math.sqrt(365)
    return {"n_days": int(len(daily)), "sharpe": sharpe, "max_dd": max_drawdown([float(v) for v in daily])}


def group_key(row: dict[str, Any]) -> str:
    return f"{row.get('scenario')}@{float(row.get('cost_bps', 0.0)):g}"


def analyze_group(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: (to_ts(r.get("ts")) or pd.Timestamp.min.tz_localize("UTC"), int(r.get("order_index", 0))))
    events_by_action = dict(Counter(str(r.get("action", "unknown")) for r in rows))
    events_by_regime = dict(Counter(str(r.get("regime_at_execution") or "unknown") for r in rows))
    gross = sum(float(r.get("gross", 0.0)) for r in rows)
    fees = sum(float(r.get("fee", 0.0)) for r in rows)
    realized_pnl = sum(float(r.get("realized_pnl", 0.0)) for r in rows)
    equities = [float(r.get("equity_after", 0.0)) for r in rows if float(r.get("equity_after", 0.0)) > 0]
    first_equity = equities[0] if equities else 0.0
    last_equity = equities[-1] if equities else 0.0
    route_values = [float(r.get("route_multiplier")) for r in rows if r.get("route_multiplier") is not None]
    policy_values = [float(r.get("policy_multiplier")) for r in rows if r.get("policy_multiplier") is not None]

    cash_recon_max_err = 0.0
    equity_recon_max_err = 0.0
    fee_model_max_err_bps = 0.0
    monotonic_ts = True
    prev_cash = None
    prev_ts = None
    for row in rows:
        cash_after = float(row.get("cash_after", 0.0))
        cash_delta = float(row.get("cash_delta", 0.0))
        if prev_cash is not None:
            cash_recon_max_err = max(cash_recon_max_err, abs((cash_after - prev_cash) - cash_delta))
        prev_cash = cash_after
        qty = float(row.get("dead_qty_after", 0.0)) + float(row.get("float_qty_after", 0.0))
        equity_recon = cash_after + qty * float(row.get("price", 0.0))
        equity_recon_max_err = max(equity_recon_max_err, abs(equity_recon - float(row.get("equity_after", 0.0))))
        expected_fee = float(row.get("gross", 0.0)) * float(row.get("cost_bps", 0.0)) / 10000.0
        fee_model_max_err_bps = max(fee_model_max_err_bps, abs(float(row.get("fee", 0.0)) - expected_fee))
        ts = to_ts(row.get("ts"))
        if prev_ts is not None and ts is not None and ts < prev_ts:
            monotonic_ts = False
        if ts is not None:
            prev_ts = ts

    regime_counts = sorted(events_by_regime.values(), reverse=True)
    secondary_ok = len(regime_counts) >= 2 and regime_counts[1] >= args.min_secondary_regime_events

    return {
        "n_events": len(rows),
        "events_by_action": events_by_action,
        "events_by_regime": events_by_regime,
        "gross_turnover": gross,
        "total_fees": fees,
        "fee_drag_bps_of_turnover": (fees / gross * 10000.0) if gross > 0 else 0.0,
        "realized_pnl_incremental": realized_pnl,
        "net_pnl_eventpath": last_equity - first_equity,
        "first_equity_after": first_equity,
        "last_equity_after": last_equity,
        "max_dd_eventpath": max_drawdown(equities),
        "daily": daily_stats(rows),
        "inventory": {
            "dead_qty_end": float(rows[-1].get("dead_qty_after", 0.0)),
            "float_qty_end": float(rows[-1].get("float_qty_after", 0.0)),
            "max_dead_qty": max(float(r.get("dead_qty_after", 0.0)) for r in rows),
            "max_float_qty": max(float(r.get("float_qty_after", 0.0)) for r in rows),
        },
        "multipliers": {
            "route": {"p50": quantile(route_values, 0.50), "p95": quantile(route_values, 0.95)},
            "policy": {"p50": quantile(policy_values, 0.50), "p95": quantile(policy_values, 0.95)},
        },
        "integrity": {
            "cash_recon_max_err": cash_recon_max_err,
            "equity_recon_max_err": equity_recon_max_err,
            "fee_model_max_err": fee_model_max_err_bps,
            "monotonic_ts": monotonic_ts,
        },
        "coverage": {
            "secondary_regime_events_ok": secondary_ok,
            "dominant_regime_share": (regime_counts[0] / len(rows)) if rows and regime_counts else 0.0,
            "second_regime_events": regime_counts[1] if len(regime_counts) >= 2 else 0,
        },
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Execution Log Analysis v9",
        "",
        f"created_at: {payload['created_at']}",
        f"input: `{payload['meta']['input']}`",
        f"events: {payload['meta']['n_events']}",
        f"ts_max: `{payload['meta']['ts_max']}`",
        f"train_only: `{payload['meta']['train_only']}`",
        "",
        "This is execution/order-event analysis. It is not round-trip trade analysis.",
        "",
        "## Gates",
        "",
        f"passed: `{payload['gates']['passed']}`",
        "",
    ]
    if payload["gates"]["failures"]:
        lines.append("")
        lines.append("Failure summary:")
        for reason, count in sorted(payload["gates"].get("failure_summary", {}).items()):
            lines.append(f"- {reason}: {count}")
        lines.append("")
        lines.append("Failure details:")
        detail_limit = 60
        for failure in payload["gates"]["failures"][:detail_limit]:
            lines.append(f"- {failure}")
        omitted = len(payload["gates"]["failures"]) - detail_limit
        if omitted > 0:
            lines.append(f"- ... {omitted} more")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Scenarios",
            "",
            "| scenario | events | gross | fees | fee bps | net pnl path | eventpath DD | daily DD | dominant regime share |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for key, row in payload["per_scenario"].items():
        lines.append(
            "| {key} | {events} | {gross:.2f} | {fees:.2f} | {feebps:.2f} | {pnl:.2f} | {dd:.4f} | {ddd:.4f} | {dom:.3f} |".format(
                key=key,
                events=row["n_events"],
                gross=row["gross_turnover"],
                fees=row["total_fees"],
                feebps=row["fee_drag_bps_of_turnover"],
                pnl=row["net_pnl_eventpath"],
                dd=row["max_dd_eventpath"],
                ddd=row["daily"]["max_dd"],
                dom=row["coverage"]["dominant_regime_share"],
            )
        )
    lines.extend(
        [
            "",
            "## Not Claimed",
            "",
            "- No win rate, profit factor, average trade PnL, holding period, or per-trade CVaR.",
            "- `realized_pnl` is incremental inventory realization, not a round-trip outcome.",
            "- Regime stats are train-only descriptive attribution, not forward robustness.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    started = time.time()
    rows = read_jsonl(Path(args.input))
    cutoff = pd.Timestamp(args.cutoff, tz="UTC")
    timestamps = [to_ts(r.get("ts")) for r in rows]
    timestamps = [t for t in timestamps if t is not None]
    ts_min = min(timestamps) if timestamps else None
    ts_max = max(timestamps) if timestamps else None
    cutoff_ok = bool(ts_max is None or ts_max <= cutoff)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[group_key(row)].append(row)
    per_scenario = {key: analyze_group(part, args) for key, part in sorted(grouped.items())}

    failures = []
    if not cutoff_ok:
        failures.append(f"leak_gate_failed: ts_max {ts_max} > cutoff {cutoff}")
    for key, row in per_scenario.items():
        integ = row["integrity"]
        if integ["cash_recon_max_err"] > args.cash_tolerance:
            failures.append(f"{key}: cash_recon_max_err {integ['cash_recon_max_err']}")
        if integ["equity_recon_max_err"] > args.equity_tolerance:
            failures.append(f"{key}: equity_recon_max_err {integ['equity_recon_max_err']}")
        if integ["fee_model_max_err"] > args.fee_tolerance:
            failures.append(f"{key}: fee_model_max_err {integ['fee_model_max_err']}")
        if not integ["monotonic_ts"]:
            failures.append(f"{key}: timestamps_not_monotonic")
        if not row["coverage"]["secondary_regime_events_ok"]:
            failures.append(f"{key}: secondary_regime_coverage_failed")
        if row["net_pnl_eventpath"] <= 0:
            failures.append(f"{key}: net_pnl_eventpath_not_positive")
        if row["daily"]["max_dd"] > args.max_drawdown:
            failures.append(f"{key}: daily_max_dd_exceeds_{args.max_drawdown}")
    failure_summary: dict[str, int] = {}
    for failure in failures:
        reason = failure.split(": ", 1)[1] if ": " in failure else failure
        if reason.startswith("daily_max_dd_exceeds"):
            reason = "daily_max_dd_exceeds"
        elif reason.startswith("equity_recon_max_err"):
            reason = "equity_recon_max_err"
        elif reason.startswith("cash_recon_max_err"):
            reason = "cash_recon_max_err"
        elif reason.startswith("fee_model_max_err"):
            reason = "fee_model_max_err"
        failure_summary[reason] = failure_summary.get(reason, 0) + 1

    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(time.time() - started, 3),
        "meta": {
            "input": args.input,
            "n_events": len(rows),
            "ts_min": str(ts_min) if ts_min is not None else None,
            "ts_max": str(ts_max) if ts_max is not None else None,
            "cutoff": str(cutoff),
            "cost_bps_values": sorted({float(r.get("cost_bps", 0.0)) for r in rows}),
            "train_only": True,
            "schema_note": "execution/order events, not contract round trips",
        },
        "integrity": {
            "cutoff_ok": cutoff_ok,
            "cash_recon_max_err": max((r["integrity"]["cash_recon_max_err"] for r in per_scenario.values()), default=0.0),
            "equity_recon_max_err": max((r["integrity"]["equity_recon_max_err"] for r in per_scenario.values()), default=0.0),
            "fee_model_max_err": max((r["integrity"]["fee_model_max_err"] for r in per_scenario.values()), default=0.0),
            "monotonic_ts": all(r["integrity"]["monotonic_ts"] for r in per_scenario.values()),
        },
        "per_scenario": per_scenario,
        "gates": {"passed": not failures, "failures": failures, "failure_summary": failure_summary},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    write_markdown(payload, Path(args.md))
    print(json.dumps({
        "out": args.out,
        "md": args.md,
        "passed": payload["gates"]["passed"],
        "failures": len(failures),
        "events": len(rows),
        "ts_max": payload["meta"]["ts_max"],
    }, indent=2, sort_keys=True))
    return 0 if payload["gates"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
