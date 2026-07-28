#!/usr/bin/env python3
"""Train-only regime context labels for v9.

This module builds fixed, causal market-regime labels from OHLCV data. It is a
validation/freeze helper, not a trading signal. The script refuses to read bars
on or after the embargo start so the labels cannot leak holdout information.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
}


@dataclass(frozen=True)
class RegimeConfig:
    version: str = "regime_v9_fixed_20260706"
    trend_return_days: int = 200
    trend_up_threshold: float = 0.05
    trend_down_threshold: float = -0.05
    vol_window_days: int = 90
    vol_percentile_lookback_days: int = 730
    high_vol_percentile: float = 0.80
    low_vol_percentile: float = 0.35
    drawdown_lookback_days: int = 365
    deep_drawdown_threshold: float = 0.20
    min_daily_bars: int = 260
    folds: int = 4
    cvar_frac: float = 0.05
    train_pnl_concentration_limit: float = 0.60
    risk_budget_per_trade: float = 0.01


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def load_config(path: Path) -> tuple[RegimeConfig, str]:
    raw = path.read_text()
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        clean = line.split("#", 1)[0].strip()
        if not clean or ":" not in clean:
            continue
        key, value = clean.split(":", 1)
        data[key.strip()] = parse_scalar(value)
    fields = {name: data[name] for name in RegimeConfig.__dataclass_fields__ if name in data}
    return RegimeConfig(**fields), hashlib.sha256(raw.encode()).hexdigest()


def month_range(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    cur = pd.Timestamp(start.year, start.month, 1, tz="UTC")
    final = pd.Timestamp(end.year, end.month, 1, tz="UTC")
    months = []
    while cur <= final:
        months.append(cur.strftime("%Y-%m"))
        cur += pd.DateOffset(months=1)
    return months


def open_time_to_dt(s: pd.Series) -> pd.Series:
    sample = float(s.dropna().iloc[0])
    if sample > 10**17:
        unit = "ns"
    elif sample > 10**14:
        unit = "us"
    elif sample > 10**11:
        unit = "ms"
    else:
        unit = "s"
    return pd.to_datetime(s, unit=unit, utc=True, errors="coerce")


def load_symbol_1h(cache_dir: Path, symbol: str, train_start: pd.Timestamp, train_end: pd.Timestamp, embargo_start: pd.Timestamp) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for month in month_range(train_start, train_end):
        path = cache_dir / f"{symbol}_1h_{month}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        keep = [c for c in ["open_time", "open", "high", "low", "close", "volume"] if c in df.columns]
        if "open_time" not in keep:
            continue
        df = df[keep].copy()
        df["dt"] = open_time_to_dt(df["open_time"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        frames.append(df)
    if not frames:
        raise SystemExit(f"no 1h cache data for {symbol} in {train_start.date()}..{train_end.date()}")
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["dt", "open", "high", "low", "close"])
    out = out.sort_values("dt").drop_duplicates("dt")
    out = out[(out["dt"] >= train_start) & (out["dt"] <= train_end)]
    if (out["dt"] >= embargo_start).any():
        bad = out.loc[out["dt"] >= embargo_start, "dt"].min()
        raise SystemExit(f"embargo guard failed for {symbol}: bar {bad} is >= {embargo_start}")
    if out.empty:
        raise SystemExit(f"empty 1h train data for {symbol}")
    return out


def resample_daily(df1h: pd.DataFrame) -> pd.DataFrame:
    agg = dict(OHLCV_AGG)
    if "volume" in df1h.columns:
        agg["volume"] = "sum"
    daily = df1h.set_index("dt").resample("1D").agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return daily


def rolling_percentile(values: pd.Series, lookback: int) -> pd.Series:
    out: list[float] = []
    raw = list(values)
    for idx, value in enumerate(raw):
        if value is None or not math.isfinite(float(value)):
            out.append(float("nan"))
            continue
        start = max(0, idx - lookback + 1)
        window = [float(v) for v in raw[start : idx + 1] if v is not None and math.isfinite(float(v))]
        if not window:
            out.append(float("nan"))
        else:
            out.append(sum(1 for v in window if v <= float(value)) / len(window))
    return pd.Series(out, index=values.index)


def label_row(row: pd.Series, cfg: RegimeConfig) -> tuple[str, str, str, str]:
    if bool(row.get("insufficient_history", False)):
        return "insufficient_history", "unknown", "unknown", "unknown"
    trend_ret = float(row["trend_return"])
    vol_pct = float(row["vol_percentile_2y"])
    drawdown = float(row["drawdown_1y"])
    if trend_ret >= cfg.trend_up_threshold:
        trend_state = "up"
    elif trend_ret <= cfg.trend_down_threshold:
        trend_state = "down"
    else:
        trend_state = "range"
    if vol_pct >= cfg.high_vol_percentile:
        vol_state = "high_vol"
    elif vol_pct <= cfg.low_vol_percentile:
        vol_state = "low_vol"
    else:
        vol_state = "normal_vol"
    drawdown_state = "deep_drawdown" if drawdown >= cfg.deep_drawdown_threshold else "normal_drawdown"

    if drawdown_state == "deep_drawdown" and trend_state != "up":
        regime = "deep_drawdown"
    elif trend_state == "up" and vol_state == "high_vol":
        regime = "up_high_vol"
    elif trend_state == "up":
        regime = "up_normal"
    elif trend_state == "down" and vol_state == "high_vol":
        regime = "down_high_vol"
    elif trend_state == "down":
        regime = "down_normal"
    elif vol_state == "high_vol":
        regime = "range_high_vol"
    else:
        regime = "range_normal"
    return regime, trend_state, vol_state, drawdown_state


def build_labels(df1h: pd.DataFrame, symbol: str, cfg: RegimeConfig) -> pd.DataFrame:
    daily = resample_daily(df1h)
    close = daily["close"]
    daily["symbol"] = symbol
    daily["trend_return"] = close / close.shift(cfg.trend_return_days) - 1.0
    daily["daily_return"] = close.pct_change()
    daily["realized_vol_90d"] = daily["daily_return"].rolling(cfg.vol_window_days).std() * math.sqrt(365)
    daily["vol_percentile_2y"] = rolling_percentile(daily["realized_vol_90d"], cfg.vol_percentile_lookback_days)
    rolling_high = close.rolling(cfg.drawdown_lookback_days, min_periods=max(30, min(cfg.drawdown_lookback_days, 60))).max()
    daily["drawdown_1y"] = (1.0 - close / rolling_high).clip(lower=0.0)
    daily["insufficient_history"] = range(len(daily))
    daily["insufficient_history"] = daily["insufficient_history"] < cfg.min_daily_bars
    labels = [label_row(row, cfg) for _, row in daily.iterrows()]
    daily["regime_id"] = [x[0] for x in labels]
    daily["trend_state"] = [x[1] for x in labels]
    daily["vol_state"] = [x[2] for x in labels]
    daily["drawdown_state"] = [x[3] for x in labels]
    keep = [
        "dt",
        "symbol",
        "regime_id",
        "trend_state",
        "vol_state",
        "drawdown_state",
        "close",
        "trend_return",
        "realized_vol_90d",
        "vol_percentile_2y",
        "drawdown_1y",
        "insufficient_history",
    ]
    return daily[keep].copy()


def occupancy(labels: pd.DataFrame) -> dict[str, float]:
    scored = labels[~labels["insufficient_history"]]
    if scored.empty:
        return {}
    counts = scored["regime_id"].value_counts(normalize=True).sort_index()
    return {str(k): float(v) for k, v in counts.items()}


def transition_matrix(labels: pd.DataFrame) -> dict[str, dict[str, int]]:
    scored = labels[~labels["insufficient_history"]]
    matrix: dict[str, dict[str, int]] = {}
    prev: str | None = None
    for regime in scored["regime_id"]:
        cur = str(regime)
        if prev is not None:
            matrix.setdefault(prev, {})
            matrix[prev][cur] = matrix[prev].get(cur, 0) + 1
        prev = cur
    return matrix


def median_duration_days(labels: pd.DataFrame) -> dict[str, float]:
    scored = labels[~labels["insufficient_history"]]
    durations: dict[str, list[int]] = {}
    prev: str | None = None
    run = 0
    for regime in scored["regime_id"]:
        cur = str(regime)
        if cur == prev:
            run += 1
        else:
            if prev is not None:
                durations.setdefault(prev, []).append(run)
            prev = cur
            run = 1
    if prev is not None:
        durations.setdefault(prev, []).append(run)
    out = {}
    for regime, values in durations.items():
        values = sorted(values)
        mid = len(values) // 2
        out[regime] = float(values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0)
    return out


def fold_occupancy(labels: pd.DataFrame, folds: int) -> list[dict[str, Any]]:
    scored = labels[~labels["insufficient_history"]].copy()
    if scored.empty:
        return []
    scored["fold"] = pd.qcut(range(len(scored)), q=min(folds, len(scored)), labels=False, duplicates="drop")
    out = []
    for fold, part in scored.groupby("fold"):
        out.append(
            {
                "fold": int(fold),
                "start": str(part["dt"].min()),
                "end": str(part["dt"].max()),
                "days": int(len(part)),
                "occupancy": occupancy(part),
            }
        )
    return out


def cross_symbol_agreement(label_map: dict[str, pd.DataFrame]) -> dict[str, Any]:
    frames = []
    for symbol, labels in label_map.items():
        part = labels[~labels["insufficient_history"]][["dt", "regime_id"]].rename(columns={"regime_id": symbol})
        frames.append(part)
    if len(frames) < 2:
        return {"pairwise_avg": None, "all_symbols_same_rate": None, "pairs": {}}
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="dt", how="inner")
    symbols = list(label_map)
    pairs: dict[str, float] = {}
    vals = []
    for i, left in enumerate(symbols):
        for right in symbols[i + 1 :]:
            if left in merged.columns and right in merged.columns and not merged.empty:
                rate = float((merged[left] == merged[right]).mean())
                pairs[f"{left}:{right}"] = rate
                vals.append(rate)
    same_rate = None
    if not merged.empty:
        same_rate = float(merged[symbols].nunique(axis=1).eq(1).mean())
    return {
        "pairwise_avg": sum(vals) / len(vals) if vals else None,
        "all_symbols_same_rate": same_rate,
        "common_days": int(len(merged)),
        "pairs": pairs,
    }


def infer_trade_columns(df: pd.DataFrame) -> tuple[str, str, str | None]:
    time_col = next((c for c in ["exit_time", "close_time", "entry_time", "ts", "dt", "time"] if c in df.columns), "")
    pnl_col = next((c for c in ["net_return", "return", "pnl_pct", "pnl", "alpha"] if c in df.columns), "")
    cost_col = next((c for c in ["cost_bps", "fee_bps"] if c in df.columns), None)
    if not time_col or not pnl_col:
        raise SystemExit("candidate trades must include a timestamp column and one pnl/return column")
    return time_col, pnl_col, cost_col


def load_candidate_trades(path: Path, embargo_start: pd.Timestamp) -> pd.DataFrame:
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix == ".json":
        df = pd.read_json(path)
    elif path.suffix == ".jsonl":
        df = pd.read_json(path, lines=True)
    else:
        df = pd.read_csv(path)
    time_col, pnl_col, cost_col = infer_trade_columns(df)
    df = df.copy()
    if pd.api.types.is_numeric_dtype(df[time_col]):
        df["trade_dt"] = open_time_to_dt(df[time_col])
    else:
        df["trade_dt"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df["trade_pnl"] = pd.to_numeric(df[pnl_col], errors="coerce")
    if cost_col:
        df["cost_bps"] = pd.to_numeric(df[cost_col], errors="coerce")
    if "symbol" not in df.columns:
        df["symbol"] = ""
    df = df.dropna(subset=["trade_dt", "trade_pnl"])
    if (df["trade_dt"] >= embargo_start).any():
        bad = df.loc[df["trade_dt"] >= embargo_start, "trade_dt"].min()
        raise SystemExit(f"candidate trade embargo guard failed: trade {bad} is >= {embargo_start}")
    return df


def cvar(values: list[float], frac: float) -> float:
    if not values:
        return 0.0
    n = max(1, int(math.ceil(len(values) * frac)))
    return sum(sorted(values)[:n]) / n


def trade_stats(values: pd.Series, cfg: RegimeConfig) -> dict[str, Any]:
    xs = [float(v) for v in values.dropna()]
    if not xs:
        return {"trades": 0, "expectancy": 0.0, "sharpe": None, "cvar5": 0.0, "total_pnl": 0.0}
    avg = sum(xs) / len(xs)
    std = pd.Series(xs).std(ddof=1)
    sharpe = None if not std or not math.isfinite(float(std)) else avg / float(std) * math.sqrt(len(xs))
    return {
        "trades": len(xs),
        "expectancy": avg,
        "sharpe": sharpe,
        "cvar5": cvar(xs, cfg.cvar_frac),
        "total_pnl": sum(xs),
    }


def candidate_trade_report(trades: pd.DataFrame, label_map: dict[str, pd.DataFrame], cfg: RegimeConfig) -> dict[str, Any]:
    joined = []
    for symbol, labels in label_map.items():
        if "symbol" in trades.columns and trades["symbol"].astype(str).str.len().gt(0).any():
            part = trades[trades["symbol"].astype(str).isin({symbol, symbol.replace("USDT", "")})].copy()
        else:
            part = trades.copy() if len(label_map) == 1 else trades[trades["symbol"].astype(str).eq(symbol)].copy()
        if part.empty:
            continue
        labs = labels[["dt", "regime_id"]].sort_values("dt")
        part = part.sort_values("trade_dt")
        matched = pd.merge_asof(part, labs, left_on="trade_dt", right_on="dt", direction="backward")
        matched["label_symbol"] = symbol
        joined.append(matched)
    if not joined:
        return {"trade_count": 0, "by_regime": {}, "gates": {"has_trades": False}}
    all_trades = pd.concat(joined, ignore_index=True).dropna(subset=["regime_id"])
    if "cost_bps" in all_trades.columns and all_trades["cost_bps"].notna().any():
        eval_trades = all_trades[all_trades["cost_bps"] >= 50.0].copy()
        cost_filter = "cost_bps>=50"
    else:
        eval_trades = all_trades
        cost_filter = "no_cost_column_all_trades"
    by_regime = {str(regime): trade_stats(part["trade_pnl"], cfg) for regime, part in eval_trades.groupby("regime_id")}
    total_positive = sum(max(0.0, stats["total_pnl"]) for stats in by_regime.values())
    if total_positive > 0:
        concentration = max(max(0.0, stats["total_pnl"]) / total_positive for stats in by_regime.values())
    else:
        denom = sum(abs(stats["total_pnl"]) for stats in by_regime.values())
        concentration = max((abs(stats["total_pnl"]) / denom for stats in by_regime.values()), default=0.0) if denom else 0.0
    traded_regimes = {k: v for k, v in by_regime.items() if v["trades"] > 0}
    worst_expectancy = min((v["expectancy"] for v in traded_regimes.values()), default=0.0)
    worst_cvar = min((v["cvar5"] for v in traded_regimes.values()), default=0.0)
    return {
        "trade_count": int(len(eval_trades)),
        "cost_filter": cost_filter,
        "by_regime": by_regime,
        "worst_regime_expectancy": worst_expectancy,
        "worst_regime_cvar5": worst_cvar,
        "pnl_concentration": concentration,
        "gates": {
            "has_trades": len(eval_trades) > 0,
            "non_negative_expectancy_in_traded_regimes": all(v["expectancy"] >= 0.0 for v in traded_regimes.values()),
            "pnl_concentration_lte_limit": concentration <= cfg.train_pnl_concentration_limit,
            "worst_regime_cvar5_within_risk_budget": worst_cvar >= -cfg.risk_budget_per_trade,
        },
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Regime Context v9",
        "",
        f"created_at: {payload['created_at']}",
        f"config_sha256: `{payload['config_sha256']}`",
        f"train_window: {payload['train_window']['start']} to {payload['train_window']['end']}",
        "",
        "## Symbols",
        "",
        "| symbol | days | top regime | top occupancy | median duration max |",
        "|---|---:|---|---:|---:|",
    ]
    for symbol, summary in payload["symbols"].items():
        occ = summary["occupancy"]
        top_regime = max(occ, key=occ.get) if occ else "none"
        max_duration = max(summary["median_duration_days"].values(), default=0.0)
        lines.append(
            f"| {symbol} | {summary['scored_days']} | {top_regime} | {occ.get(top_regime, 0.0):.3f} | {max_duration:.1f} |"
        )
    agreement = payload["cross_symbol_agreement"]
    lines.extend(
        [
            "",
            "## Cross-Symbol Agreement",
            "",
            f"- pairwise_avg: `{agreement.get('pairwise_avg')}`",
            f"- all_symbols_same_rate: `{agreement.get('all_symbols_same_rate')}`",
            f"- common_days: `{agreement.get('common_days')}`",
            "",
            "## Gates Supported",
            "",
            "- Regime robustness: candidate expectancy must be non-negative in every traded regime.",
            "- PnL concentration: train PnL from one regime should stay below the preregistered limit.",
            "- Worst-regime risk: per-trade CVaR5 must stay within the declared risk budget.",
            "",
        ]
    )
    trade_report = payload.get("candidate_trade_report")
    if trade_report:
        lines.extend(
            [
                "## Candidate Trades",
                "",
                f"- trade_count: `{trade_report.get('trade_count')}`",
                f"- cost_filter: `{trade_report.get('cost_filter')}`",
                f"- pnl_concentration: `{trade_report.get('pnl_concentration')}`",
                f"- worst_regime_expectancy: `{trade_report.get('worst_regime_expectancy')}`",
                f"- worst_regime_cvar5: `{trade_report.get('worst_regime_cvar5')}`",
                "",
                "| gate | passed |",
                "|---|---:|",
            ]
        )
        for gate, passed in trade_report.get("gates", {}).items():
            lines.append(f"| {gate} | `{passed}` |")
        lines.append("")
    path.write_text("\n".join(lines))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build train-only v9 regime context labels")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT"])
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--config", default="configs/regime_v9.yaml")
    ap.add_argument("--candidate-trades", default="")
    ap.add_argument("--out", default="artifacts/v9")
    return ap


def run(args: argparse.Namespace) -> dict[str, Any]:
    cfg, config_hash = load_config(Path(args.config))
    cache_dir = Path(args.cache_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_start = pd.Timestamp(args.train_start, tz="UTC")
    train_end = pd.Timestamp(args.train_end, tz="UTC")
    embargo_start = pd.Timestamp(args.embargo_start, tz="UTC")
    if train_end >= embargo_start:
        raise SystemExit(f"train_end {train_end} must be before embargo_start {embargo_start}")

    label_map: dict[str, pd.DataFrame] = {}
    symbol_summary: dict[str, Any] = {}
    for symbol in args.symbols:
        df1h = load_symbol_1h(cache_dir, symbol, train_start, train_end, embargo_start)
        labels = build_labels(df1h, symbol, cfg)
        if (labels["dt"] >= embargo_start).any():
            raise SystemExit(f"label embargo guard failed for {symbol}")
        label_map[symbol] = labels
        labels.to_parquet(out_dir / f"regime_labels_{symbol}.parquet", index=False)
        scored = labels[~labels["insufficient_history"]]
        symbol_summary[symbol] = {
            "input_1h_bars": int(len(df1h)),
            "label_days": int(len(labels)),
            "scored_days": int(len(scored)),
            "start": str(labels["dt"].min()),
            "end": str(labels["dt"].max()),
            "occupancy": occupancy(labels),
            "transition_matrix": transition_matrix(labels),
            "median_duration_days": median_duration_days(labels),
            "folds": fold_occupancy(labels, cfg.folds),
        }

    payload: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "train_only_fixed_causal_regime_context_v9",
        "config": str(args.config),
        "config_sha256": config_hash,
        "config_values": cfg.__dict__,
        "train_window": {"start": str(train_start), "end": str(train_end), "embargo_start": str(embargo_start)},
        "symbols": symbol_summary,
        "cross_symbol_agreement": cross_symbol_agreement(label_map),
        "outputs": {
            "labels": {symbol: str(out_dir / f"regime_labels_{symbol}.parquet") for symbol in args.symbols},
            "json": str(out_dir / "regime_report.json"),
            "md": str(out_dir / "regime_report.md"),
        },
    }
    if args.candidate_trades:
        trades = load_candidate_trades(Path(args.candidate_trades), embargo_start)
        payload["candidate_trade_report"] = candidate_trade_report(trades, label_map, cfg)

    report_json = out_dir / "regime_report.json"
    report_md = out_dir / "regime_report.md"
    report_json.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    write_markdown(payload, report_md)
    return payload


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run(args)
    print(json.dumps({
        "json": payload["outputs"]["json"],
        "md": payload["outputs"]["md"],
        "symbols": list(payload["symbols"]),
        "config_sha256": payload["config_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
