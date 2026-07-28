#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.simulator import utc_ts
from v9.contract.tsmom_factory import (
    TsmomConfig,
    asset_vol_scale_matrix,
    market_regime_series,
    portfolio_exposure_scale,
    short_weights_from_votes,
    target_weights_from_votes,
    vote_fraction_matrix,
)
from v9.contract.xsec_momentum import load_close_matrix, sharpe


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def top_accepted_row(payload: dict[str, Any]) -> dict[str, Any]:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    raise ValueError("artifact has no accepted train-only row")


def max_drawdown_from_returns(returns: pd.Series) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1.0 + float(value)
        peak = max(peak, equity)
        if peak > 0.0:
            worst = max(worst, 1.0 - equity / peak)
    return float(worst)


def simulate_detailed(closes: pd.DataFrame, cfg: TsmomConfig, lookbacks_h: tuple[int, ...], cost_bps: float) -> pd.DataFrame:
    symbols = [c for c in closes.columns if c != "dt"]
    votes = vote_fraction_matrix(closes, lookbacks_h)
    asset_scales = asset_vol_scale_matrix(closes, cfg.asset_vol_target_ann)
    market_allowed = market_regime_series(closes, cfg.market_filter_h)
    returns = closes[symbols].pct_change().shift(-1)
    weights = {sym: 0.0 for sym in symbols}
    past_returns: list[float] = []
    rows: list[dict[str, Any]] = []
    equity = 1.0
    peak_equity = 1.0
    risk_off_until = -1

    for idx in range(len(closes) - 1):
        ts = pd.Timestamp(closes["dt"].iloc[idx])
        current_drawdown = 1.0 - equity / peak_equity if peak_equity > 0.0 else 0.0
        if cfg.drawdown_stop > 0.0 and idx >= risk_off_until and current_drawdown >= cfg.drawdown_stop:
            risk_off_until = idx + max(1, int(cfg.cooldown_h))
        forced_exit = idx < risk_off_until and sum(abs(v) for v in weights.values()) > 0.0
        rebalance = bool(idx % 24 == 0 or forced_exit)
        allow_market = bool(market_allowed.iloc[idx])
        mode = "long"
        turnover = 0.0
        cost = 0.0
        if rebalance:
            if idx < risk_off_until:
                base = {sym: 0.0 for sym in symbols}
                mode = "risk_off"
            elif not allow_market and cfg.bear_mode == "short_weak":
                base = short_weights_from_votes(votes.iloc[idx], asset_scales.iloc[idx], threshold=cfg.short_vote_threshold)
                base = {sym: weight * max(0.0, min(1.0, cfg.bear_short_scale)) for sym, weight in base.items()}
                mode = "short_weak"
            else:
                base = target_weights_from_votes(votes.iloc[idx], asset_scales.iloc[idx], threshold=cfg.vote_threshold)
                if not allow_market:
                    base = {sym: weight * max(0.0, min(1.0, cfg.market_off_scale)) for sym, weight in base.items()}
                    mode = "market_off_scaled"
            scale = portfolio_exposure_scale(past_returns, cfg.portfolio_vol_target_ann)
            target = {sym: base[sym] * scale for sym in symbols}
            turnover = sum(abs(target[sym] - weights[sym]) for sym in symbols)
            must_exit = sum(abs(v) for v in target.values()) == 0.0 and sum(abs(v) for v in weights.values()) > 0.0
            if turnover > 0.0 and (turnover >= cfg.no_trade_band or must_exit or forced_exit):
                weights = target
                cost = turnover * cost_bps / 10000.0
            else:
                turnover = 0.0
        row_rets = returns.iloc[idx].fillna(0.0)
        long_gross = 0.0
        short_gross = 0.0
        symbol_contribs: dict[str, float] = {}
        for sym in symbols:
            contribution = float(weights[sym]) * float(row_rets[sym])
            symbol_contribs[sym] = contribution
            if weights[sym] >= 0.0:
                long_gross += contribution
            else:
                short_gross += contribution
        gross = long_gross + short_gross
        net = gross - cost
        equity *= 1.0 + net
        peak_equity = max(peak_equity, equity)
        row = {
            "dt": ts,
            "net_return": net,
            "gross_return": gross,
            "long_gross_return": long_gross,
            "short_gross_return": short_gross,
            "cost": cost,
            "turnover": turnover,
            "gross_exposure": sum(abs(v) for v in weights.values()),
            "long_exposure": sum(max(v, 0.0) for v in weights.values()),
            "short_exposure": sum(abs(min(v, 0.0)) for v in weights.values()),
            "market_allowed": allow_market,
            "mode": mode,
            "risk_off": bool(idx < risk_off_until),
        }
        for sym, contribution in symbol_contribs.items():
            row[f"sym_{sym}"] = contribution
            row[f"w_{sym}"] = float(weights[sym])
        rows.append(row)
        past_returns.append(net)
    return pd.DataFrame(rows).set_index("dt")


def period_summary(frame: pd.DataFrame, periods_per_year: float = 365.0) -> dict[str, Any]:
    if frame.empty:
        return {
            "periods": 0,
            "total_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "cost_return": 0.0,
            "long_gross_return": 0.0,
            "short_gross_return": 0.0,
            "avg_gross_exposure": 0.0,
        }
    daily = (1.0 + frame["net_return"]).resample("1D").prod() - 1.0
    return {
        "periods": int(len(daily)),
        "total_return": float((1.0 + frame["net_return"]).prod() - 1.0),
        "sharpe": sharpe(daily, periods_per_year),
        "max_drawdown": max_drawdown_from_returns(frame["net_return"]),
        "cost_return": float(frame["cost"].sum()),
        "long_gross_return": float(frame["long_gross_return"].sum()),
        "short_gross_return": float(frame["short_gross_return"].sum()),
        "avg_gross_exposure": float(frame["gross_exposure"].mean()),
        "avg_long_exposure": float(frame["long_exposure"].mean()),
        "avg_short_exposure": float(frame["short_exposure"].mean()),
        "turnover": float(frame["turnover"].sum()),
    }


def monthly_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for label, sub in frame.groupby(frame.index.to_period("M")):
        summary = period_summary(sub)
        summary["month"] = str(label)
        rows.append(summary)
    return rows


def symbol_rows(frame: pd.DataFrame, symbols: list[str]) -> list[dict[str, Any]]:
    rows = []
    for sym in symbols:
        contrib = frame[f"sym_{sym}"]
        weights = frame[f"w_{sym}"]
        rows.append(
            {
                "symbol": sym,
                "contribution_sum": float(contrib.sum()),
                "positive_hours": int((contrib > 0.0).sum()),
                "negative_hours": int((contrib < 0.0).sum()),
                "avg_weight": float(weights.mean()),
                "avg_abs_weight": float(weights.abs().mean()),
                "long_hours": int((weights > 0.0).sum()),
                "short_hours": int((weights < 0.0).sum()),
            }
        )
    return sorted(rows, key=lambda row: row["contribution_sum"])


def mode_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for mode, sub in frame.groupby("mode"):
        summary = period_summary(sub)
        summary["mode"] = str(mode)
        rows.append(summary)
    return sorted(rows, key=lambda row: row["total_return"])


def worst_rows(rows: list[dict[str, Any]], key: str, count: int = 5) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: float(row.get(key, 0.0) or 0.0))[:count]


def build_report(
    artifact: Path,
    cache_dir: Path,
    holdout_start: str,
    holdout_end: str,
    cost_bps: float,
) -> dict[str, Any]:
    payload = read_json(artifact)
    row = top_accepted_row(payload)
    cfg = TsmomConfig(**row["config"])
    lookbacks_h = tuple(int(v) for v in row["lookbacks_h"])
    symbols = list(payload["symbols"])
    closes = load_close_matrix(cache_dir, tuple(symbols), utc_ts(holdout_start), utc_ts(holdout_end), utc_ts("2100-01-01"))
    frame = simulate_detailed(closes, cfg, lookbacks_h, cost_bps)
    monthly = monthly_rows(frame)
    by_symbol = symbol_rows(frame, symbols)
    by_mode = mode_rows(frame)
    overall = period_summary(frame)
    losing_months = [row for row in monthly if float(row["total_return"]) < 0.0]
    short_total = float(frame["short_gross_return"].sum())
    long_total = float(frame["long_gross_return"].sum())
    cost_total = float(frame["cost"].sum())
    diagnosis = []
    if short_total < 0.0:
        diagnosis.append("short_leg_lost_money")
    if long_total < 0.0:
        diagnosis.append("long_leg_lost_money")
    if cost_total > abs(float(overall["total_return"])) * 0.5:
        diagnosis.append("costs_material_vs_total_loss")
    if len(losing_months) >= max(1, math.ceil(len(monthly) * 0.50)):
        diagnosis.append("losses_broad_across_months")
    return {
        "kind": "tsmom_holdout_diagnostics_v1",
        "source_artifact": str(artifact),
        "target_config": row["config"],
        "target_lookbacks_h": list(lookbacks_h),
        "holdout": {
            "start": holdout_start,
            "end": holdout_end,
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
            "cost_bps": float(cost_bps),
        },
        "overall": overall,
        "diagnosis": diagnosis,
        "worst_months": worst_rows(monthly, "total_return", count=6),
        "monthly": monthly,
        "worst_symbols": worst_rows(by_symbol, "contribution_sum", count=len(by_symbol)),
        "by_mode": by_mode,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "note": "Read-only holdout diagnostics. It does not authorize paper trading or live trading.",
    }


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def format_text(report: dict[str, Any]) -> str:
    overall = report["overall"]
    lines = [
        "decision=holdout_diagnostics_only_do_not_trade",
        "safety="
        f"holdout:{report['holdout_authorized']} "
        f"paper:{report['paper_trading_authorized']} "
        f"live:{report['live_trading_authorized']}",
        f"source_artifact={report['source_artifact']}",
        f"target_config={json.dumps(report['target_config'], sort_keys=True)}",
        f"target_lookbacks_h={report['target_lookbacks_h']}",
        "overall="
        f"return:{fmt(overall.get('total_return'))} "
        f"sharpe:{fmt(overall.get('sharpe'))} "
        f"dd:{fmt(overall.get('max_drawdown'))} "
        f"long_gross:{fmt(overall.get('long_gross_return'))} "
        f"short_gross:{fmt(overall.get('short_gross_return'))} "
        f"cost:{fmt(overall.get('cost_return'))} "
        f"gross_exp:{fmt(overall.get('avg_gross_exposure'))}",
        f"diagnosis={','.join(report['diagnosis']) or 'none'}",
        "worst_months:",
    ]
    for row in report["worst_months"]:
        lines.append(
            "- "
            f"{row['month']} "
            f"return:{fmt(row.get('total_return'))} "
            f"sharpe:{fmt(row.get('sharpe'))} "
            f"dd:{fmt(row.get('max_drawdown'))} "
            f"long:{fmt(row.get('long_gross_return'))} "
            f"short:{fmt(row.get('short_gross_return'))} "
            f"cost:{fmt(row.get('cost_return'))}"
        )
    lines.append("symbols:")
    for row in report["worst_symbols"]:
        lines.append(
            "- "
            f"{row['symbol']} "
            f"contrib:{fmt(row.get('contribution_sum'))} "
            f"avg_abs_w:{fmt(row.get('avg_abs_weight'))} "
            f"long_h:{row.get('long_hours')} "
            f"short_h:{row.get('short_hours')}"
        )
    lines.append("modes:")
    for row in report["by_mode"]:
        lines.append(
            "- "
            f"{row['mode']} "
            f"return:{fmt(row.get('total_return'))} "
            f"long:{fmt(row.get('long_gross_return'))} "
            f"short:{fmt(row.get('short_gross_return'))} "
            f"cost:{fmt(row.get('cost_return'))} "
            f"gross_exp:{fmt(row.get('avg_gross_exposure'))}"
        )
    lines.append(f"note={report['note']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only TSMOM holdout failure diagnostics")
    parser.add_argument("artifact", help="TSMOM train-only artifact with accepted row")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--holdout-start", default="2024-07-01")
    parser.add_argument("--holdout-end", default="2026-05-31 23:59:59")
    parser.add_argument("--cost-bps", type=float, default=20.0)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--out-json")
    parser.add_argument("--out-text")
    args = parser.parse_args()
    report = build_report(
        artifact=Path(args.artifact),
        cache_dir=Path(args.cache_dir),
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
        cost_bps=args.cost_bps,
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
