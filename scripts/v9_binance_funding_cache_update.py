#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")
BINANCE_FUNDING_API = "https://fapi.binance.com/fapi/v1/fundingRate"
DEFAULT_FUNDING_INTERVAL_MS = 8 * 3_600_000


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols or DEFAULT_SYMBOLS)


def month_label(funding_time_ms: int) -> str:
    return pd.Timestamp(int(funding_time_ms), unit="ms", tz="UTC").strftime("%Y-%m")


def _column_or_default(df: pd.DataFrame, name: str, default: Any) -> Any:
    if name in df.columns:
        return df[name]
    return [default] * len(df)


def normalize_frame(df: pd.DataFrame, *, symbol: str | None = None) -> pd.DataFrame:
    target_symbol = symbol.upper() if symbol else None
    out = pd.DataFrame(
        {
            "symbol": _column_or_default(df, "symbol", target_symbol),
            "funding_time": _column_or_default(df, "funding_time", pd.NA),
            "funding_rate": _column_or_default(df, "funding_rate", pd.NA),
            "mark_price": _column_or_default(df, "mark_price", pd.NA),
        }
    )
    out["symbol"] = out["symbol"].astype("string").str.upper()
    if target_symbol:
        out["symbol"] = out["symbol"].fillna(target_symbol)
    out["funding_time"] = pd.to_numeric(out["funding_time"], errors="coerce").astype("Int64")
    out["funding_rate"] = pd.to_numeric(out["funding_rate"], errors="coerce")
    out["mark_price"] = pd.to_numeric(out["mark_price"], errors="coerce")
    out = out.dropna(subset=["symbol", "funding_time", "funding_rate"])
    if target_symbol:
        out = out[out["symbol"] == target_symbol].copy()
    out["funding_time"] = out["funding_time"].astype("int64")
    return out.sort_values("funding_time").drop_duplicates("funding_time", keep="last").reset_index(drop=True)


def read_existing(path: Path, *, symbol: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "funding_time", "funding_rate", "mark_price"])
    df = pd.read_parquet(path).copy()
    return normalize_frame(df, symbol=symbol)


def frame_from_funding_rows(rows: list[dict[str, Any]], *, symbol: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["symbol", "funding_time", "funding_rate", "mark_price"])
    df = pd.DataFrame(rows)
    return normalize_frame(
        pd.DataFrame(
            {
                "symbol": _column_or_default(df, "symbol", symbol),
                "funding_time": _column_or_default(df, "fundingTime", pd.NA),
                "funding_rate": _column_or_default(df, "fundingRate", pd.NA),
                "mark_price": _column_or_default(df, "markPrice", pd.NA),
            }
        ),
        symbol=symbol,
    )


def latest_cached_funding_time(cache_dir: Path, symbol: str) -> int | None:
    latest = None
    for path in cache_dir.glob(f"{symbol.upper()}_funding_*.parquet"):
        try:
            df = pd.read_parquet(path, columns=["funding_time"])
        except Exception:
            continue
        if df.empty:
            continue
        value = int(pd.to_numeric(df["funding_time"], errors="coerce").dropna().max())
        latest = value if latest is None else max(latest, value)
    return latest


def fetch_funding_rates(symbol: str, start_ms: int, end_ms: int, *, limit: int = 1000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = int(start_ms)
    while cursor <= int(end_ms):
        params = urllib.parse.urlencode(
            {
                "symbol": symbol.upper(),
                "startTime": cursor,
                "endTime": int(end_ms),
                "limit": int(limit),
            }
        )
        with urllib.request.urlopen(f"{BINANCE_FUNDING_API}?{params}", timeout=20) as response:
            batch = json.loads(response.read().decode("utf-8"))
        if isinstance(batch, dict):
            raise RuntimeError(f"funding API error for {symbol}: {batch}")
        if not batch:
            break
        out.extend(batch)
        funding_times = [int(row["fundingTime"]) for row in batch if "fundingTime" in row]
        if not funding_times:
            break
        next_cursor = max(funding_times) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < int(limit):
            break
        time.sleep(0.15)
    return out


def write_monthly_cache(cache_dir: Path, symbol: str, frame: pd.DataFrame) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    written = []
    normalized = normalize_frame(frame, symbol=symbol)
    for month, part in normalized.groupby(normalized["funding_time"].map(month_label)):
        path = cache_dir / f"{symbol.upper()}_funding_{month}.parquet"
        merged = normalize_frame(pd.concat([read_existing(path, symbol=symbol), part], ignore_index=True), symbol=symbol)
        merged.to_parquet(path, index=False)
        written.append(
            {
                "path": str(path),
                "rows": int(len(merged)),
                "latest_funding_time": int(merged["funding_time"].max()),
            }
        )
    return {"files": written, "written_file_count": len(written)}


def update_symbol(
    *,
    cache_dir: Path,
    symbol: str,
    now_ms: int,
    lookback_events_if_empty: int,
) -> dict[str, Any]:
    symbol = symbol.upper()
    latest_before = latest_cached_funding_time(cache_dir, symbol)
    start_ms = (
        latest_before + 1
        if latest_before is not None
        else int(now_ms) - max(1, int(lookback_events_if_empty) - 1) * DEFAULT_FUNDING_INTERVAL_MS
    )
    if start_ms > int(now_ms):
        return {
            "symbol": symbol,
            "status": "up_to_date",
            "latest_before": latest_before,
            "latest_after": latest_before,
            "downloaded_rows": 0,
        }
    rows = fetch_funding_rates(symbol, start_ms, int(now_ms))
    frame = frame_from_funding_rows(rows, symbol=symbol)
    frame = frame[frame["funding_time"] <= int(now_ms)].copy()
    if frame.empty:
        return {
            "symbol": symbol,
            "status": "no_rows",
            "latest_before": latest_before,
            "latest_after": latest_before,
            "downloaded_rows": 0,
        }
    written = write_monthly_cache(cache_dir, symbol, frame)
    latest_after = latest_cached_funding_time(cache_dir, symbol)
    return {
        "symbol": symbol,
        "status": "updated" if latest_after != latest_before else "unchanged",
        "latest_before": latest_before,
        "latest_after": latest_after,
        "downloaded_rows": int(len(frame)),
        **written,
    }


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    results = [
        update_symbol(
            cache_dir=Path(args.cache_dir),
            symbol=symbol,
            now_ms=now_ms,
            lookback_events_if_empty=args.lookback_events_if_empty,
        )
        for symbol in parse_symbols(args.symbols)
    ]
    return {
        "kind": "binance_funding_cache_update_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "symbols": parse_symbols(args.symbols),
        "updated_count": sum(1 for row in results if row.get("status") == "updated"),
        "results": results,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"updated_at={report['updated_at']}",
        f"updated_count={report['updated_count']}",
        "safety=paper:False live:False",
    ]
    for row in report["results"]:
        lines.append(
            f"{row['symbol']} status={row['status']} downloaded={row['downloaded_rows']} "
            f"before={row.get('latest_before')} after={row.get('latest_after')}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update Binance USD-M funding-rate parquet cache.")
    parser.add_argument("--cache-dir", default="data/binance_funding_cache")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--lookback-events-if-empty", type=int, default=90)
    parser.add_argument("--state-json", default="artifacts/v9/watchdog/binance_funding_cache_update_status.json")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=1800.0)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    while True:
        report = run_once(args)
        write_json(report, Path(args.state_json))
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        else:
            print(format_text(report), flush=True)
        if not args.loop:
            return
        time.sleep(max(60.0, float(args.sleep_sec)))


if __name__ == "__main__":
    main()
