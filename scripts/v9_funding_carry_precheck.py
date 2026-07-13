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
    for funding_time in pivot.index:
        scores = trailing.loc[funding_time].dropna()
        realized = pivot.loc[funding_time].dropna()
        common = scores.index.intersection(realized.index)
        if len(common) < int(min_symbols):
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
    return {
        "kind": "funding_carry_precheck_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "symbols": symbols,
        "lookback_events": int(args.lookback_events),
        "bucket_fraction": float(args.bucket_fraction),
        "min_symbols": int(args.min_symbols),
        "loaded_rows": int(len(frame)),
        "metrics": metrics,
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
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cheap point-in-time funding-carry edge precheck.")
    parser.add_argument("--cache-dir", default="data/binance_funding_cache")
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
