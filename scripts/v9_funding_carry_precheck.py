#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")
EVENTS_PER_YEAR = 3.0 * 365.25
HOUR_MS = 3_600_000


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols or DEFAULT_SYMBOLS)


def timestamp_ms_to_iso(value: int | float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(int(value), unit="ms", tz="UTC").isoformat()


def normalize_funding_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "symbol": df["symbol"] if "symbol" in df.columns else pd.NA,
            "funding_time": df["funding_time"] if "funding_time" in df.columns else pd.NA,
            "funding_rate": df["funding_rate"] if "funding_rate" in df.columns else pd.NA,
        }
    )
    out["symbol"] = out["symbol"].astype("string").str.upper()
    out["funding_time"] = pd.to_numeric(out["funding_time"], errors="coerce").astype("Int64")
    out["funding_rate"] = pd.to_numeric(out["funding_rate"], errors="coerce")
    out = out.dropna(subset=["symbol", "funding_time", "funding_rate"])
    out["funding_time"] = out["funding_time"].astype("int64")
    return out.sort_values(["funding_time", "symbol"]).drop_duplicates(["funding_time", "symbol"], keep="last")


def load_funding_cache(cache_dir: Path, symbols: tuple[str, ...]) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        for path in sorted(cache_dir.glob(f"{symbol.upper()}_funding_*.parquet")):
            try:
                frames.append(pd.read_parquet(path, columns=["symbol", "funding_time", "funding_rate"]))
            except Exception:
                continue
    if not frames:
        return pd.DataFrame(columns=["symbol", "funding_time", "funding_rate"])
    return normalize_funding_frame(pd.concat(frames, ignore_index=True))


def load_ohlcv_close_cache(cache_dir: Path, symbols: tuple[str, ...], timeframe: str) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        for path in sorted(cache_dir.glob(f"{symbol.upper()}_{timeframe}_*.parquet")):
            try:
                df = pd.read_parquet(path, columns=["open_time", "close"])
            except Exception:
                continue
            df = df.copy()
            df["symbol"] = symbol.upper()
            frames.append(df[["symbol", "open_time", "close"]])
    if not frames:
        return pd.DataFrame(columns=["symbol", "open_time", "close"])
    out = pd.concat(frames, ignore_index=True)
    out["symbol"] = out["symbol"].astype("string").str.upper()
    out["open_time"] = pd.to_numeric(out["open_time"], errors="coerce").astype("Int64")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["symbol", "open_time", "close"])
    out["open_time"] = out["open_time"].astype("int64")
    return out.sort_values(["open_time", "symbol"]).drop_duplicates(["open_time", "symbol"], keep="last")


def last_closed_hour_open_time_for_funding(funding_time: int) -> int:
    funding_boundary = int(funding_time) // HOUR_MS * HOUR_MS
    return funding_boundary - HOUR_MS


def max_drawdown_from_returns(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = returns.fillna(0.0).cumsum()
    drawdown = equity.cummax() - equity
    return float(drawdown.max())


def evaluate_funding_carry(
    frame: pd.DataFrame,
    *,
    lookback_events: int,
    bucket_fraction: float,
    min_symbols: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    clean = normalize_funding_frame(frame)
    if clean.empty:
        return pd.DataFrame(), {"status": "insufficient_data", "reason": "empty_funding_cache"}
    pivot = clean.pivot_table(index="funding_time", columns="symbol", values="funding_rate", aggfunc="last").sort_index()
    lookback = max(1, int(lookback_events))
    trailing = pivot.rolling(lookback, min_periods=lookback).mean().shift(1)
    rows: list[dict[str, Any]] = []
    previous_funding_time = None
    for funding_time in pivot.index:
        scores = trailing.loc[funding_time].dropna()
        realized = pivot.loc[funding_time].dropna()
        common = scores.index.intersection(realized.index)
        if len(common) < int(min_symbols):
            previous_funding_time = int(funding_time)
            continue
        ranked = scores.loc[common].sort_values()
        leg_count = max(1, int(math.floor(len(ranked) * float(bucket_fraction))))
        leg_count = min(leg_count, max(1, len(ranked) // 2))
        longs = list(ranked.index[:leg_count])
        shorts = list(ranked.index[-leg_count:])
        weights = pd.Series(0.0, index=common)
        weights.loc[longs] = 0.5 / leg_count
        weights.loc[shorts] = -0.5 / leg_count
        funding_return = float(-(weights * realized.loc[common]).sum())
        rows.append(
            {
                "funding_time": int(funding_time),
                "funding_time_iso": timestamp_ms_to_iso(int(funding_time)),
                "previous_funding_time": previous_funding_time,
                "previous_funding_time_iso": timestamp_ms_to_iso(previous_funding_time),
                "symbol_count": int(len(common)),
                "leg_count": int(leg_count),
                "long_symbols": longs,
                "short_symbols": shorts,
                "gross_funding_return": funding_return,
                "mean_long_funding": float(realized.loc[longs].mean()),
                "mean_short_funding": float(realized.loc[shorts].mean()),
                "trailing_long_funding": float(scores.loc[longs].mean()),
                "trailing_short_funding": float(scores.loc[shorts].mean()),
            }
        )
        previous_funding_time = int(funding_time)
    detail = pd.DataFrame(rows)
    if detail.empty:
        return detail, {"status": "insufficient_data", "reason": "no_point_in_time_events_after_lookback"}
    returns = detail["gross_funding_return"].astype(float)
    mean_return = float(returns.mean())
    std_return = float(returns.std(ddof=1))
    annualized_return = mean_return * EVENTS_PER_YEAR
    annualized_vol = std_return * math.sqrt(EVENTS_PER_YEAR)
    sharpe = annualized_return / annualized_vol if annualized_vol > 0 else None
    metrics = {
        "status": "ok",
        "evaluated_events": int(len(detail)),
        "first_evaluated_funding_time": int(detail["funding_time"].min()),
        "first_evaluated_funding_time_iso": timestamp_ms_to_iso(int(detail["funding_time"].min())),
        "last_evaluated_funding_time": int(detail["funding_time"].max()),
        "last_evaluated_funding_time_iso": timestamp_ms_to_iso(int(detail["funding_time"].max())),
        "mean_return_per_event": mean_return,
        "annualized_gross_return": annualized_return,
        "annualized_gross_vol": annualized_vol,
        "gross_sharpe": sharpe,
        "positive_event_fraction": float((returns > 0).mean()),
        "max_cashflow_drawdown": max_drawdown_from_returns(returns),
        "passes_gross_precheck": bool((sharpe is not None and sharpe >= 1.0) and annualized_return > 0.0),
        "costs_and_price_risk_included": False,
    }
    return detail, metrics


def weights_from_detail_row(row: pd.Series) -> pd.Series:
    longs = list(row["long_symbols"])
    shorts = list(row["short_symbols"])
    leg_count = int(row["leg_count"])
    weights = pd.Series(0.0, index=sorted(set(longs) | set(shorts)))
    weights.loc[longs] = 0.5 / leg_count
    weights.loc[shorts] = -0.5 / leg_count
    return weights


def summarize_returns(returns: pd.Series, *, prefix: str = "") -> dict[str, Any]:
    if returns.empty:
        return {
            f"{prefix}evaluated_events": 0,
            f"{prefix}annualized_return": None,
            f"{prefix}annualized_vol": None,
            f"{prefix}sharpe": None,
            f"{prefix}positive_event_fraction": None,
            f"{prefix}max_drawdown": None,
        }
    mean_return = float(returns.mean())
    std_return = float(returns.std(ddof=1))
    annualized_return = mean_return * EVENTS_PER_YEAR
    annualized_vol = std_return * math.sqrt(EVENTS_PER_YEAR)
    sharpe = annualized_return / annualized_vol if annualized_vol > 0 else None
    return {
        f"{prefix}evaluated_events": int(len(returns)),
        f"{prefix}mean_return_per_event": mean_return,
        f"{prefix}annualized_return": annualized_return,
        f"{prefix}annualized_vol": annualized_vol,
        f"{prefix}sharpe": sharpe,
        f"{prefix}positive_event_fraction": float((returns > 0).mean()),
        f"{prefix}max_drawdown": max_drawdown_from_returns(returns),
    }


def evaluate_price_aware_carry(
    detail: pd.DataFrame,
    close_frame: pd.DataFrame,
    *,
    turnover_cost_bps: float,
) -> dict[str, Any]:
    if detail.empty:
        return {"status": "insufficient_data", "reason": "empty_gross_detail"}
    if close_frame.empty:
        return {"status": "insufficient_data", "reason": "empty_ohlcv_cache"}
    close_pivot = close_frame.pivot_table(index="open_time", columns="symbol", values="close", aggfunc="last").sort_index()
    rows: list[dict[str, Any]] = []
    previous_weights = pd.Series(dtype=float)
    for _, row in detail.sort_values("funding_time").iterrows():
        previous_funding_time = row.get("previous_funding_time")
        funding_time = int(row["funding_time"])
        if previous_funding_time is None or pd.isna(previous_funding_time):
            continue
        start_open_time = last_closed_hour_open_time_for_funding(int(previous_funding_time))
        end_open_time = last_closed_hour_open_time_for_funding(funding_time)
        if start_open_time not in close_pivot.index or end_open_time not in close_pivot.index:
            continue
        weights = weights_from_detail_row(row)
        start_prices = close_pivot.loc[start_open_time].dropna()
        end_prices = close_pivot.loc[end_open_time].dropna()
        common = weights.index.intersection(start_prices.index).intersection(end_prices.index)
        if len(common) < len(weights):
            continue
        aligned_weights = weights.loc[common].astype(float)
        price_returns = end_prices.loc[common] / start_prices.loc[common] - 1.0
        price_return = float((aligned_weights * price_returns).sum())
        all_symbols = previous_weights.index.union(aligned_weights.index)
        turnover = float((aligned_weights.reindex(all_symbols, fill_value=0.0) - previous_weights.reindex(all_symbols, fill_value=0.0)).abs().sum())
        cost = turnover * float(turnover_cost_bps) / 10_000.0
        funding_return = float(row["gross_funding_return"])
        net_return = funding_return + price_return - cost
        rows.append(
            {
                "funding_time": funding_time,
                "funding_time_iso": row["funding_time_iso"],
                "price_return": price_return,
                "funding_return": funding_return,
                "turnover": turnover,
                "cost": cost,
                "net_return": net_return,
            }
        )
        previous_weights = aligned_weights
    price_detail = pd.DataFrame(rows)
    if price_detail.empty:
        return {"status": "insufficient_data", "reason": "no_events_with_price_coverage"}
    net_returns = price_detail["net_return"].astype(float)
    price_returns = price_detail["price_return"].astype(float)
    funding_returns = price_detail["funding_return"].astype(float)
    metrics = {
        "status": "ok",
        "turnover_cost_bps": float(turnover_cost_bps),
        "first_evaluated_funding_time": int(price_detail["funding_time"].min()),
        "first_evaluated_funding_time_iso": timestamp_ms_to_iso(int(price_detail["funding_time"].min())),
        "last_evaluated_funding_time": int(price_detail["funding_time"].max()),
        "last_evaluated_funding_time_iso": timestamp_ms_to_iso(int(price_detail["funding_time"].max())),
        "average_turnover": float(price_detail["turnover"].mean()),
        "annualized_cost_drag": float(price_detail["cost"].mean()) * EVENTS_PER_YEAR,
        **summarize_returns(funding_returns, prefix="funding_"),
        **summarize_returns(price_returns, prefix="price_"),
        **summarize_returns(net_returns, prefix="net_"),
    }
    metrics["passes_price_aware_precheck"] = bool(
        metrics.get("net_sharpe") is not None
        and metrics["net_sharpe"] >= 1.0
        and metrics.get("net_annualized_return") is not None
        and metrics["net_annualized_return"] > 0.0
    )
    return metrics


def run_precheck(args: argparse.Namespace) -> dict[str, Any]:
    symbols = parse_symbols(args.symbols)
    frame = load_funding_cache(Path(args.cache_dir), symbols)
    detail, metrics = evaluate_funding_carry(
        frame,
        lookback_events=args.lookback_events,
        bucket_fraction=args.bucket_fraction,
        min_symbols=args.min_symbols,
    )
    top_events = []
    if not detail.empty:
        top_events = detail.sort_values("gross_funding_return", ascending=False).head(10).to_dict(orient="records")
    price_aware_metrics = None
    loaded_ohlcv_rows = 0
    if args.ohlcv_cache_dir:
        close_frame = load_ohlcv_close_cache(Path(args.ohlcv_cache_dir), symbols, args.price_timeframe)
        loaded_ohlcv_rows = int(len(close_frame))
        price_aware_metrics = evaluate_price_aware_carry(
            detail,
            close_frame,
            turnover_cost_bps=args.turnover_cost_bps,
        )
    return {
        "kind": "funding_carry_precheck_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "symbols": symbols,
        "lookback_events": int(args.lookback_events),
        "bucket_fraction": float(args.bucket_fraction),
        "min_symbols": int(args.min_symbols),
        "loaded_rows": int(len(frame)),
        "ohlcv_cache_dir": args.ohlcv_cache_dir,
        "loaded_ohlcv_rows": loaded_ohlcv_rows,
        "metrics": metrics,
        "price_aware_metrics": price_aware_metrics,
        "top_events": top_events,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_text(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"updated_at={report['updated_at']}",
        f"status={metrics.get('status')}",
        f"loaded_rows={report['loaded_rows']}",
        f"evaluated_events={metrics.get('evaluated_events', 0)}",
        f"annualized_gross_return={metrics.get('annualized_gross_return')}",
        f"gross_sharpe={metrics.get('gross_sharpe')}",
        f"passes_gross_precheck={metrics.get('passes_gross_precheck', False)}",
        "costs_and_price_risk_included=False",
        "safety=paper:False live:False",
    ]
    price_metrics = report.get("price_aware_metrics")
    if price_metrics:
        lines.extend(
            [
                f"price_aware_status={price_metrics.get('status')}",
                f"net_annualized_return={price_metrics.get('net_annualized_return')}",
                f"net_sharpe={price_metrics.get('net_sharpe')}",
                f"passes_price_aware_precheck={price_metrics.get('passes_price_aware_precheck', False)}",
                f"annualized_cost_drag={price_metrics.get('annualized_cost_drag')}",
            ]
        )
    reason = metrics.get("reason")
    if reason:
        lines.append(f"reason={reason}")
    return "\n".join(lines)


def format_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Funding Carry Precheck",
        "",
        f"- status: `{metrics.get('status')}`",
        f"- loaded_rows: `{report['loaded_rows']}`",
        f"- evaluated_events: `{metrics.get('evaluated_events', 0)}`",
        f"- annualized_gross_return: `{metrics.get('annualized_gross_return')}`",
        f"- gross_sharpe: `{metrics.get('gross_sharpe')}`",
        f"- passes_gross_precheck: `{metrics.get('passes_gross_precheck', False)}`",
        f"- first_event: `{metrics.get('first_evaluated_funding_time_iso')}`",
        f"- last_event: `{metrics.get('last_evaluated_funding_time_iso')}`",
        "",
        "This is a gross funding-cashflow screen only. It does not authorize paper or live trading.",
    ]
    price_metrics = report.get("price_aware_metrics")
    if price_metrics:
        lines.extend(
            [
                "",
                "## Price-Aware Screen",
                "",
                f"- status: `{price_metrics.get('status')}`",
                f"- net_annualized_return: `{price_metrics.get('net_annualized_return')}`",
                f"- net_sharpe: `{price_metrics.get('net_sharpe')}`",
                f"- passes_price_aware_precheck: `{price_metrics.get('passes_price_aware_precheck', False)}`",
                f"- annualized_cost_drag: `{price_metrics.get('annualized_cost_drag')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cheap point-in-time funding-carry edge precheck.")
    parser.add_argument("--cache-dir", default="data/binance_funding_cache")
    parser.add_argument("--ohlcv-cache-dir", default="")
    parser.add_argument("--price-timeframe", default="1h")
    parser.add_argument("--turnover-cost-bps", type=float, default=10.0)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--lookback-events", type=int, default=9)
    parser.add_argument("--bucket-fraction", type=float, default=0.2)
    parser.add_argument("--min-symbols", type=int, default=6)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/funding_carry_precheck_v1.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/funding_carry_precheck_v1.md")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = run_precheck(args)
    write_json(report, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(report))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(report), flush=True)


if __name__ == "__main__":
    main()
