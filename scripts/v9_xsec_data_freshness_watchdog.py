#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_paper_shadow import read_ledger_records, to_utc_timestamp  # noqa: E402


DEFAULT_SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def payload_hash(payload: dict[str, Any], prev_hash: str) -> str:
    raw = f"{prev_hash}\n{canonical_json(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols or DEFAULT_SYMBOLS)


def normalize_open_time_ms(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    clean = values.dropna()
    if clean.empty:
        return values.astype("Int64")
    sample = float(clean.iloc[0])
    if sample > 10**17:
        values = values // 1_000_000
    elif sample > 10**14:
        values = values // 1_000
    elif sample > 10**11:
        values = values
    else:
        values = values * 1_000
    return values.astype("Int64")


def latest_open_time_ms(path: Path) -> int | None:
    try:
        df = pd.read_parquet(path, columns=["open_time"])
    except Exception:
        return None
    if df.empty:
        return None
    values = normalize_open_time_ms(df["open_time"]).dropna()
    if values.empty:
        return None
    return int(values.astype("int64").max())


def latest_by_symbol(cache_dir: Path, symbols: tuple[str, ...], timeframe: str) -> dict[str, int | None]:
    latest: dict[str, int | None] = {}
    for symbol in symbols:
        best = None
        for path in sorted(cache_dir.glob(f"{symbol}_{timeframe}_*.parquet")):
            value = latest_open_time_ms(path)
            if value is not None:
                best = value if best is None else max(best, value)
        latest[symbol] = best
    return latest


def count_duplicate_latest_dt_records(records: list[dict[str, Any]]) -> int:
    count = 0
    previous = None
    for record in records:
        if record.get("kind") != "xsec_paper_ledger_record_v1":
            continue
        latest_dt = record.get("latest_dt")
        if latest_dt and latest_dt == previous:
            count += 1
        if latest_dt:
            previous = latest_dt
    return count


def load_previous_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def evaluate_freshness(
    *,
    latest: dict[str, int | None],
    previous_status: dict[str, Any],
    ledger_records: list[dict[str, Any]],
    now: str,
    max_cache_age_hours: float,
    min_symbol_coverage: float,
    max_unchanged_runs: int,
) -> dict[str, Any]:
    now_ts = to_utc_timestamp(now)
    available = {symbol: value for symbol, value in latest.items() if value is not None}
    max_latest_ms = max(available.values()) if available else None
    max_latest_dt = (
        pd.Timestamp(max_latest_ms, unit="ms", tz="UTC").isoformat()
        if max_latest_ms is not None
        else None
    )
    age_hours = (
        max(0.0, (now_ts - pd.Timestamp(max_latest_ms, unit="ms", tz="UTC")).total_seconds() / 3600.0)
        if max_latest_ms is not None
        else float("inf")
    )
    coverage_count = sum(1 for value in available.values() if value == max_latest_ms)
    coverage_fraction = coverage_count / max(1, len(latest))
    previous_max = previous_status.get("max_latest_ms")
    previous_unchanged = int(previous_status.get("unchanged_run_count") or 0)
    unchanged_count = previous_unchanged + 1 if previous_max == max_latest_ms else 0
    duplicate_latest_dt_records = count_duplicate_latest_dt_records(ledger_records)
    checks = {
        "cache_has_data": bool(available),
        "cache_age_le_max": math.isfinite(age_hours) and age_hours <= float(max_cache_age_hours),
        "symbol_coverage_ge_min": coverage_fraction >= float(min_symbol_coverage),
        "cache_advancing_or_below_limit": unchanged_count < int(max_unchanged_runs),
    }
    data_fresh = all(checks.values())
    return {
        "kind": "xsec_data_freshness_status_v1",
        "updated_at": now,
        "data_fresh": data_fresh,
        "checks": checks,
        "max_latest_ms": max_latest_ms,
        "max_latest_dt": max_latest_dt,
        "cache_age_hours": age_hours,
        "coverage_count": coverage_count,
        "symbol_count": len(latest),
        "coverage_fraction": coverage_fraction,
        "unchanged_run_count": unchanged_count,
        "duplicate_latest_dt_records": duplicate_latest_dt_records,
        "latest_by_symbol": {
            symbol: (
                pd.Timestamp(value, unit="ms", tz="UTC").isoformat()
                if value is not None
                else None
            )
            for symbol, value in sorted(latest.items())
        },
        "note": "Read-only freshness watchdog. It never downloads data, trades, or authorizes live.",
    }


def append_history(status: dict[str, Any], history_path: Path) -> dict[str, Any]:
    prev_hash = "GENESIS"
    if history_path.exists():
        for line in history_path.read_text().splitlines():
            if line.strip():
                try:
                    prev_hash = str(json.loads(line).get("hash") or prev_hash)
                except json.JSONDecodeError:
                    continue
    record = dict(status)
    record["prev_hash"] = prev_hash
    record["hash"] = payload_hash({key: value for key, value in record.items() if key != "hash"}, prev_hash)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def build_status(
    *,
    cache_dir: Path,
    symbols: tuple[str, ...],
    timeframe: str,
    ledger_path: Path,
    previous_status_path: Path,
    max_cache_age_hours: float,
    min_symbol_coverage: float,
    max_unchanged_runs: int,
    now: str | None = None,
) -> dict[str, Any]:
    return evaluate_freshness(
        latest=latest_by_symbol(cache_dir, symbols, timeframe),
        previous_status=load_previous_status(previous_status_path),
        ledger_records=read_ledger_records(ledger_path),
        now=now or now_utc(),
        max_cache_age_hours=max_cache_age_hours,
        min_symbol_coverage=min_symbol_coverage,
        max_unchanged_runs=max_unchanged_runs,
    )


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_text(status: dict[str, Any]) -> str:
    checks = status.get("checks") or {}
    return "\n".join(
        [
            f"data_fresh={status.get('data_fresh')}",
            f"max_latest_dt={status.get('max_latest_dt')}",
            f"cache_age_hours={status.get('cache_age_hours'):.3f}",
            f"coverage={status.get('coverage_count')}/{status.get('symbol_count')}",
            f"unchanged_run_count={status.get('unchanged_run_count')}",
            f"duplicate_latest_dt_records={status.get('duplicate_latest_dt_records')}",
            "checks=" + ",".join(f"{key}:{value}" for key, value in checks.items()),
        ]
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only data freshness watchdog for XSEC paper evidence.")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--ledger-jsonl", default="state/xsec_paper_ledger.jsonl")
    parser.add_argument("--status-json", default="artifacts/v9/watchdog/data_freshness_status.json")
    parser.add_argument("--history-jsonl", default="artifacts/v9/watchdog/data_freshness_history.jsonl")
    parser.add_argument("--max-cache-age-hours", type=float, default=6.0)
    parser.add_argument("--min-symbol-coverage", type=float, default=0.90)
    parser.add_argument("--max-unchanged-runs", type=int, default=4)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    status_path = Path(args.status_json)
    status = build_status(
        cache_dir=Path(args.cache_dir),
        symbols=parse_symbols(args.symbols),
        timeframe=args.timeframe,
        ledger_path=Path(args.ledger_jsonl),
        previous_status_path=status_path,
        max_cache_age_hours=args.max_cache_age_hours,
        min_symbol_coverage=args.min_symbol_coverage,
        max_unchanged_runs=args.max_unchanged_runs,
    )
    append_history(status, Path(args.history_jsonl))
    write_json(status, status_path)
    if args.format == "json":
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text(status))


if __name__ == "__main__":
    main()
