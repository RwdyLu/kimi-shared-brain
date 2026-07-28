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
BINANCE_API = "https://api.binance.com/api/v3/klines"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols or DEFAULT_SYMBOLS)


def interval_ms(interval: str) -> int:
    raw = str(interval).strip().lower()
    unit = raw[-1]
    value = int(raw[:-1])
    if unit == "m":
        return value * 60_000
    if unit == "h":
        return value * 3_600_000
    if unit == "d":
        return value * 86_400_000
    raise ValueError(f"unsupported interval: {interval}")


def current_closed_open_time_ms(now_ms: int, interval: str) -> int:
    step = interval_ms(interval)
    return (int(now_ms) // step - 1) * step


def month_label(open_time_ms: int) -> str:
    return pd.Timestamp(int(open_time_ms), unit="ms", tz="UTC").strftime("%Y-%m")


def read_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    df = pd.read_parquet(path).copy()
    for col in ["open_time", "open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = pd.NA
    return normalize_frame(df)


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    keep = ["open_time", "open", "high", "low", "close", "volume"]
    out = df[[col for col in keep if col in df.columns]].copy()
    out["open_time"] = pd.to_numeric(out["open_time"], errors="coerce").astype("Int64")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["open_time", "open", "high", "low", "close"])
    out["open_time"] = out["open_time"].astype("int64")
    return out.sort_values("open_time").drop_duplicates("open_time", keep="last").reset_index(drop=True)


def frame_from_klines(rows: list[list[Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    return normalize_frame(
        pd.DataFrame(
            {
                "open_time": df[0],
                "open": df[1],
                "high": df[2],
                "low": df[3],
                "close": df[4],
                "volume": df[5],
            }
        )
    )


def latest_cached_open_time(cache_dir: Path, symbol: str, interval: str) -> int | None:
    latest = None
    for path in cache_dir.glob(f"{symbol}_{interval}_*.parquet"):
        try:
            df = pd.read_parquet(path, columns=["open_time"])
        except Exception:
            continue
        if df.empty:
            continue
        value = int(pd.to_numeric(df["open_time"], errors="coerce").dropna().max())
        latest = value if latest is None else max(latest, value)
    return latest


def fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    limit: int = 1000,
    api_url: str = BINANCE_API,
) -> list[list[Any]]:
    out: list[list[Any]] = []
    cursor = int(start_ms)
    step = interval_ms(interval)
    while cursor <= int(end_ms):
        params = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": int(end_ms),
                "limit": int(limit),
            }
        )
        with urllib.request.urlopen(f"{api_url}?{params}", timeout=20) as response:
            batch = json.loads(response.read().decode("utf-8"))
        if not batch:
            break
        out.extend(batch)
        next_cursor = int(batch[-1][0]) + step
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < limit:
            break
        time.sleep(0.15)
    return out


def write_monthly_cache(cache_dir: Path, symbol: str, interval: str, frame: pd.DataFrame) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for month, part in frame.groupby(frame["open_time"].map(month_label)):
        path = cache_dir / f"{symbol}_{interval}_{month}.parquet"
        merged = normalize_frame(pd.concat([read_existing(path), part], ignore_index=True))
        merged.to_parquet(path, index=False)
        written.append({"path": str(path), "rows": int(len(merged)), "latest_open_time": int(merged["open_time"].max())})
    return {"files": written, "written_file_count": len(written)}


def update_symbol(
    *,
    cache_dir: Path,
    symbol: str,
    interval: str,
    now_ms: int,
    lookback_bars_if_empty: int,
    api_url: str = BINANCE_API,
) -> dict[str, Any]:
    step = interval_ms(interval)
    latest_before = latest_cached_open_time(cache_dir, symbol, interval)
    last_closed = current_closed_open_time_ms(now_ms, interval)
    start_ms = (
        latest_before + step
        if latest_before is not None
        else last_closed - max(1, int(lookback_bars_if_empty) - 1) * step
    )
    if start_ms > last_closed:
        return {
            "symbol": symbol,
            "interval": interval,
            "status": "up_to_date",
            "latest_before": latest_before,
            "latest_after": latest_before,
            "downloaded_rows": 0,
        }
    rows = fetch_klines(symbol, interval, start_ms, last_closed + step - 1, api_url=api_url)
    frame = frame_from_klines(rows)
    if frame.empty:
        return {
            "symbol": symbol,
            "interval": interval,
            "status": "no_rows",
            "latest_before": latest_before,
            "latest_after": latest_before,
            "downloaded_rows": 0,
        }
    frame = frame[frame["open_time"] <= last_closed].copy()
    written = write_monthly_cache(cache_dir, symbol, interval, frame)
    latest_after = latest_cached_open_time(cache_dir, symbol, interval)
    return {
        "symbol": symbol,
        "interval": interval,
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
            interval=args.timeframe,
            now_ms=now_ms,
            lookback_bars_if_empty=args.lookback_bars_if_empty,
            api_url=args.api_url,
        )
        for symbol in parse_symbols(args.symbols)
    ]
    return {
        "kind": "xsec_binance_cache_update_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "timeframe": args.timeframe,
        "api_url": args.api_url,
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
        f"timeframe={report['timeframe']}",
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
    parser = argparse.ArgumentParser(description="Update XSEC Binance OHLCV parquet cache for closed candles only.")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--api-url", default=BINANCE_API)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--lookback-bars-if-empty", type=int, default=72)
    parser.add_argument("--state-json", default="artifacts/v9/watchdog/binance_cache_update_status.json")
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
