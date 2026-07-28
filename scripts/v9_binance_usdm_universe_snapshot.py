#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXCHANGE_INFO_API = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKER_24H_API = "https://fapi.binance.com/fapi/v1/ticker/24hr"
KLINES_API = "https://fapi.binance.com/fapi/v1/klines"
STABLE_BASE_ASSETS = {"BUSD", "DAI", "FDUSD", "TUSD", "USDC", "USDE", "USDP", "USDS", "USTC"}
MS_PER_DAY = 86_400_000


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    suffix = ""
    if params:
        suffix = "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url + suffix, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_exchange_info() -> dict[str, Any]:
    return fetch_json(EXCHANGE_INFO_API)


def fetch_ticker_24h() -> list[dict[str, Any]]:
    payload = fetch_json(TICKER_24H_API)
    if isinstance(payload, dict):
        raise RuntimeError(f"24h ticker API error: {payload}")
    return payload


def fetch_daily_klines(symbol: str, *, limit: int) -> list[list[Any]]:
    payload = fetch_json(KLINES_API, {"symbol": symbol.upper(), "interval": "1d", "limit": int(limit)})
    if isinstance(payload, dict):
        raise RuntimeError(f"kline API error for {symbol}: {payload}")
    return payload


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out


def symbol_listing_age_days(info: dict[str, Any], *, now_ms: int) -> float | None:
    onboard = info.get("onboardDate")
    if onboard is None:
        return None
    return max(0.0, (int(now_ms) - int(onboard)) / MS_PER_DAY)


def is_candidate_symbol(info: dict[str, Any], *, now_ms: int, min_listing_age_days: int) -> bool:
    if info.get("status") != "TRADING":
        return False
    if info.get("contractType") != "PERPETUAL":
        return False
    if info.get("quoteAsset") != "USDT":
        return False
    if not str(info.get("symbol", "")).endswith("USDT"):
        return False
    if info.get("baseAsset") in STABLE_BASE_ASSETS:
        return False
    age = symbol_listing_age_days(info, now_ms=now_ms)
    if age is not None and age < float(min_listing_age_days):
        return False
    return True


def median_quote_volume_from_klines(rows: list[list[Any]]) -> float:
    quote_volumes = [safe_float(row[7]) for row in rows if len(row) > 7 and safe_float(row[7]) > 0]
    if not quote_volumes:
        return 0.0
    return float(statistics.median(quote_volumes))


def build_universe(args: argparse.Namespace) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    exchange_info = fetch_exchange_info()
    symbol_info = {
        row["symbol"]: row
        for row in exchange_info.get("symbols", [])
        if is_candidate_symbol(row, now_ms=now_ms, min_listing_age_days=args.min_listing_age_days)
    }
    tickers = fetch_ticker_24h()
    ticker_rows = []
    for row in tickers:
        symbol = row.get("symbol")
        if symbol not in symbol_info:
            continue
        ticker_rows.append(
            {
                "symbol": symbol,
                "quote_volume_24h": safe_float(row.get("quoteVolume")),
                "base_asset": symbol_info[symbol].get("baseAsset"),
                "listing_age_days": symbol_listing_age_days(symbol_info[symbol], now_ms=now_ms),
            }
        )
    ticker_rows.sort(key=lambda row: row["quote_volume_24h"], reverse=True)
    prefiltered = ticker_rows[: max(int(args.top_n), int(args.prefilter_limit))]
    scored = []
    for row in prefiltered:
        rows = fetch_daily_klines(row["symbol"], limit=args.volume_lookback_days)
        median_quote_volume = median_quote_volume_from_klines(rows)
        if median_quote_volume < float(args.min_median_quote_volume):
            continue
        scored.append(
            {
                **row,
                "median_quote_volume": median_quote_volume,
                "daily_kline_count": len(rows),
            }
        )
        time.sleep(max(0.0, float(args.sleep_sec)))
    scored.sort(key=lambda row: row["median_quote_volume"], reverse=True)
    selected = scored[: int(args.top_n)]
    return {
        "kind": "binance_usdm_universe_snapshot_v1",
        "updated_at": now_utc(),
        "top_n": int(args.top_n),
        "prefilter_limit": int(args.prefilter_limit),
        "volume_lookback_days": int(args.volume_lookback_days),
        "min_listing_age_days": int(args.min_listing_age_days),
        "min_median_quote_volume": float(args.min_median_quote_volume),
        "candidate_count": len(symbol_info),
        "prefiltered_count": len(prefiltered),
        "selected_count": len(selected),
        "symbols": [row["symbol"] for row in selected],
        "rows": selected,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"updated_at={report['updated_at']}",
        f"selected_count={report['selected_count']}",
        f"candidate_count={report['candidate_count']}",
        f"symbols={','.join(report['symbols'])}",
        "safety=paper:False live:False",
    ]
    for row in report["rows"][:10]:
        lines.append(
            f"{row['symbol']} median_quote_volume={row['median_quote_volume']:.2f} "
            f"listing_age_days={row.get('listing_age_days')}"
        )
    return "\n".join(lines)


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Binance USD-M Universe Snapshot",
        "",
        f"- updated_at: `{report['updated_at']}`",
        f"- selected_count: `{report['selected_count']}`",
        f"- volume_lookback_days: `{report['volume_lookback_days']}`",
        f"- min_listing_age_days: `{report['min_listing_age_days']}`",
        f"- min_median_quote_volume: `{report['min_median_quote_volume']}`",
        "",
        "| rank | symbol | median_quote_volume | listing_age_days |",
        "| ---: | --- | ---: | ---: |",
    ]
    for idx, row in enumerate(report["rows"], start=1):
        lines.append(
            f"| {idx} | {row['symbol']} | {row['median_quote_volume']:.2f} | "
            f"{row.get('listing_age_days')} |"
        )
    lines.extend(["", "This snapshot does not authorize paper or live trading."])
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a Binance USD-M perp universe by 30d median quote volume.")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--prefilter-limit", type=int, default=80)
    parser.add_argument("--volume-lookback-days", type=int, default=30)
    parser.add_argument("--min-listing-age-days", type=int, default=90)
    parser.add_argument("--min-median-quote-volume", type=float, default=50_000_000.0)
    parser.add_argument("--sleep-sec", type=float, default=0.05)
    parser.add_argument("--out-json", default="artifacts/v9/universe/binance_usdm_top30_volume_snapshot.json")
    parser.add_argument("--out-md", default="artifacts/v9/universe/binance_usdm_top30_volume_snapshot.md")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = build_universe(args)
    write_json(report, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(report))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(report), flush=True)


if __name__ == "__main__":
    main()
