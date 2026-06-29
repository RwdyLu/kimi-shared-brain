#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


BASE = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = BASE / "data" / "binance_public_cache"
DEFAULT_MANIFESTS = BASE / "data" / "manifests"
DEFAULT_AUDITS = BASE / "data" / "audits"
DEFAULT_NORMALIZED = BASE / "data" / "normalized"

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

FILENAME_RE = re.compile(r"^(?P<symbol>[A-Z0-9]+)_(?P<timeframe>[0-9a-z]+)_(?P<month>[0-9]{4}-[0-9]{2})\.parquet$")
OHLC_COLUMNS = ["open", "high", "low", "close"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=json_default)
    return hashlib.sha256(raw.encode()).hexdigest()


def parse_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.replace(",", " ").split() if x.strip()]


def month_range(start: str, end: str) -> list[str]:
    y, m = [int(x) for x in start.split("-")]
    ey, em = [int(x) for x in end.split("-")]
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y += 1
            m = 1
    return out


def month_bounds_ms(month: str) -> tuple[int, int]:
    y, m = [int(x) for x in month.split("-")]
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def next_month(month: str) -> str:
    y, m = [int(x) for x in month.split("-")]
    m += 1
    if m == 13:
        y += 1
        m = 1
    return f"{y:04d}-{m:02d}"


def month_blocks(months: list[str]) -> list[list[str]]:
    ordered = sorted(set(months))
    if not ordered:
        return []
    blocks: list[list[str]] = []
    current = [ordered[0]]
    for month in ordered[1:]:
        if month == next_month(current[-1]):
            current.append(month)
        else:
            blocks.append(current)
            current = [month]
    blocks.append(current)
    return blocks


def expected_rows_for_month(month: str, timeframe: str) -> int | None:
    interval = INTERVAL_MS.get(timeframe)
    if interval is None:
        return None
    y, m = [int(x) for x in month.split("-")]
    days = calendar.monthrange(y, m)[1]
    return int(days * 86_400_000 // interval)


def detect_timestamp_unit(series: pd.Series) -> str:
    ts = pd.to_numeric(series, errors="coerce").dropna()
    if ts.empty:
        return "unknown"
    median = abs(float(ts.median()))
    if median >= 1e17:
        return "ns"
    if median >= 1e14:
        return "us"
    if median >= 1e11:
        return "ms"
    if median >= 1e8:
        return "s"
    return "unknown"


def normalize_open_time_ms(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return (pd.to_datetime(series, utc=True).astype("int64") // 1_000_000).astype("int64")
    ts = pd.to_numeric(series, errors="coerce")
    unit = detect_timestamp_unit(ts)
    if unit == "ns":
        ts = ts / 1_000_000.0
    elif unit == "us":
        ts = ts / 1_000.0
    elif unit == "s":
        ts = ts * 1_000.0
    return ts.round().astype("Int64")


def ms_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def load_month_file(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "open_time" not in df.columns:
        raise ValueError("missing open_time")
    missing_ohlc = [col for col in OHLC_COLUMNS if col not in df.columns]
    if missing_ohlc:
        raise ValueError(f"missing columns: {','.join(missing_ohlc)}")
    out = df.copy()
    out["open_time"] = normalize_open_time_ms(out["open_time"])
    out = out.dropna(subset=["open_time"]).copy()
    out["open_time"] = out["open_time"].astype("int64")
    for col in OHLC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if "volume" in out.columns:
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
    return out


def gap_ranges(open_times: pd.Series, expected_ms: int) -> list[dict[str, Any]]:
    ts = open_times.dropna().astype("int64").sort_values().drop_duplicates()
    if len(ts) < 2:
        return []
    diffs = ts.diff().dropna()
    gaps = []
    for idx, diff in diffs.items():
        if int(diff) > expected_ms:
            current = int(ts.loc[idx])
            previous_pos = ts.index.get_loc(idx) - 1
            previous = int(ts.iloc[previous_pos])
            missing = int(diff // expected_ms) - 1
            gaps.append(
                {
                    "after": ms_to_iso(previous),
                    "before": ms_to_iso(current),
                    "missing_bars": max(0, missing),
                }
            )
    return gaps


def audit_frame(path: Path, symbol: str, timeframe: str, month: str) -> tuple[dict[str, Any], pd.DataFrame | None]:
    raw_hash = sha256_file(path)
    raw_unit = "unknown"
    try:
        probe = pd.read_parquet(path, columns=["open_time"])
        raw_unit = detect_timestamp_unit(probe["open_time"])
        df = load_month_file(path)
    except Exception as exc:
        return (
            {
                "path": str(path),
                "symbol": symbol,
                "timeframe": timeframe,
                "month": month,
                "raw_sha256": raw_hash,
                "readable": False,
                "error": str(exc),
            },
            None,
        )

    df = df.sort_values("open_time")
    interval = INTERVAL_MS.get(timeframe)
    duplicate_count = int(df["open_time"].duplicated().sum())
    deduped = df.drop_duplicates("open_time", keep="last").copy()
    missing_ranges = gap_ranges(deduped["open_time"], interval) if interval else []
    invalid_price = (
        deduped[OHLC_COLUMNS].isna().any(axis=1)
        | (deduped[OHLC_COLUMNS] <= 0).any(axis=1)
        | (deduped["high"] < deduped[["open", "close", "low"]].max(axis=1))
        | (deduped["low"] > deduped[["open", "close", "high"]].min(axis=1))
    )
    volume_column = "volume" in deduped.columns
    zero_volume_rows = int((deduped["volume"].fillna(0) <= 0).sum()) if volume_column else None
    month_start, month_end = month_bounds_ms(month)
    outside_month = int(((deduped["open_time"] < month_start) | (deduped["open_time"] >= month_end)).sum())
    actual_interval_ms = None
    if len(deduped) > 2:
        diffs = deduped["open_time"].diff().dropna()
        diffs = diffs[diffs > 0]
        if not diffs.empty:
            actual_interval_ms = int(diffs.median())
    normalized_hash = sha256_json(
        {
            "columns": [col for col in ["open_time", "open", "high", "low", "close", "volume"] if col in deduped.columns],
            "rows": deduped[[col for col in ["open_time", "open", "high", "low", "close", "volume"] if col in deduped.columns]].to_dict("records"),
        }
    )
    report = {
        "path": str(path),
        "symbol": symbol,
        "timeframe": timeframe,
        "month": month,
        "source": "binance-public-data-cache",
        "raw_sha256": raw_hash,
        "normalized_sha256": normalized_hash,
        "readable": True,
        "timestamp_unit_detected": raw_unit,
        "timestamp_unit_normalized": "ms",
        "rows_raw": int(len(df)),
        "rows_deduped": int(len(deduped)),
        "expected_full_month_rows": expected_rows_for_month(month, timeframe),
        "min_open_time": int(deduped["open_time"].min()) if not deduped.empty else None,
        "max_open_time": int(deduped["open_time"].max()) if not deduped.empty else None,
        "min_open_time_iso": ms_to_iso(int(deduped["open_time"].min())) if not deduped.empty else None,
        "max_open_time_iso": ms_to_iso(int(deduped["open_time"].max())) if not deduped.empty else None,
        "expected_interval_ms": interval,
        "actual_median_interval_ms": actual_interval_ms,
        "duplicate_bars": duplicate_count,
        "missing_internal_bars": int(sum(g["missing_bars"] for g in missing_ranges)),
        "gap_ranges_sample": missing_ranges[:20],
        "invalid_ohlc_rows": int(invalid_price.sum()),
        "outside_month_rows": outside_month,
        "volume_column": volume_column,
        "zero_volume_rows": zero_volume_rows,
        "checksum_verified": False,
        "checksum_reason": "raw Binance zip/checksum file not present in local parquet cache",
    }
    return report, deduped


@dataclass
class Aggregate:
    symbol: str
    timeframe: str
    files: list[dict[str, Any]] = field(default_factory=list)
    frames: list[pd.DataFrame] = field(default_factory=list)

    def add(self, report: dict[str, Any], frame: pd.DataFrame | None) -> None:
        self.files.append(report)
        if frame is not None and not frame.empty:
            self.frames.append(frame)

    def manifest(self, requested_start: str, requested_end: str, max_missing_bar_frac: float) -> dict[str, Any]:
        readable = [f for f in self.files if f.get("readable")]
        months_found = sorted({f["month"] for f in readable})
        valid_months = sorted(
            f["month"]
            for f in readable
            if not f.get("duplicate_bars", 0)
            and not f.get("invalid_ohlc_rows", 0)
            and not f.get("missing_internal_bars", 0)
            and not f.get("outside_month_rows", 0)
        )
        invalid_months = [
            {
                "month": f["month"],
                "reason": (
                    "unreadable" if not f.get("readable") else
                    "duplicate_bars" if f.get("duplicate_bars", 0) else
                    "invalid_ohlc_rows" if f.get("invalid_ohlc_rows", 0) else
                    "missing_internal_bars" if f.get("missing_internal_bars", 0) else
                    "outside_month_rows" if f.get("outside_month_rows", 0) else
                    "unknown"
                ),
            }
            for f in self.files
            if (not f.get("readable"))
            or f.get("duplicate_bars", 0)
            or f.get("invalid_ohlc_rows", 0)
            or f.get("missing_internal_bars", 0)
            or f.get("outside_month_rows", 0)
        ]
        valid_ranges = []
        for block in month_blocks(valid_months):
            start_ms, _ = month_bounds_ms(block[0])
            _, end_ms = month_bounds_ms(block[-1])
            valid_ranges.append(
                {
                    "start_month": block[0],
                    "end_month": block[-1],
                    "start": ms_to_iso(start_ms),
                    "end_exclusive": ms_to_iso(end_ms),
                    "months": len(block),
                    "missing_bars": 0,
                    "duplicate_bars": 0,
                }
            )
        all_rows = pd.concat(self.frames, ignore_index=True) if self.frames else pd.DataFrame()
        duplicate_bars = int(all_rows["open_time"].duplicated().sum()) if not all_rows.empty else 0
        all_rows = all_rows.sort_values("open_time").drop_duplicates("open_time", keep="last") if not all_rows.empty else all_rows
        months_expected = month_range(months_found[0], months_found[-1]) if months_found else []
        months_missing_between_first_last = sorted(set(months_expected) - set(months_found))
        interval = INTERVAL_MS.get(self.timeframe)
        gaps = gap_ranges(all_rows["open_time"], interval) if interval and not all_rows.empty else []
        timestamp_units: dict[str, int] = {}
        for item in readable:
            unit = item.get("timestamp_unit_detected", "unknown")
            timestamp_units[unit] = timestamp_units.get(unit, 0) + 1
        hard_invalid_files = [
            f
            for f in self.files
            if (not f.get("readable"))
            or f.get("duplicate_bars", 0)
            or f.get("invalid_ohlc_rows", 0)
            or f.get("outside_month_rows", 0)
        ]
        gap_file_count = sum(1 for f in readable if f.get("missing_internal_bars", 0))
        missing_internal_bars = int(sum(g["missing_bars"] for g in gaps))
        missing_bar_frac = missing_internal_bars / max(1, len(all_rows))
        valid_for_research = bool(readable) and not hard_invalid_files and not months_missing_between_first_last and missing_bar_frac <= max_missing_bar_frac
        warnings = []
        if missing_bar_frac > 0:
            warnings.append("missing_internal_bars")
        if months_missing_between_first_last:
            warnings.append("missing_months_between_first_last")
        if not readable:
            warnings.append("no_readable_files")
        data_hash_payload = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "file_hashes": [(f.get("month"), f.get("normalized_sha256")) for f in readable],
        }
        start_ms = int(all_rows["open_time"].min()) if not all_rows.empty else None
        end_ms = int(all_rows["open_time"].max()) if not all_rows.empty else None
        return {
            "schema_version": 1,
            "created_at": utc_now(),
            "symbol": self.symbol,
            "interval": self.timeframe,
            "source": "binance-public-data",
            "cache_source": str(DEFAULT_CACHE),
            "requested_start_month": requested_start,
            "requested_end_month": requested_end,
            "observed_start": ms_to_iso(start_ms),
            "observed_end": ms_to_iso(end_ms),
            "first_valid_bar": ms_to_iso(start_ms),
            "last_valid_bar": ms_to_iso(end_ms),
            "valid_months": valid_months,
            "invalid_months": invalid_months,
            "valid_tradable_ranges": valid_ranges,
            "timestamp_unit_normalized": "ms",
            "timestamp_unit_report": timestamp_units,
            "rows": int(len(all_rows)),
            "files_read": len(readable),
            "months_found": months_found,
            "months_missing_between_first_last": months_missing_between_first_last,
            "duplicate_bars": duplicate_bars + sum(int(f.get("duplicate_bars", 0) or 0) for f in readable),
            "missing_internal_bars": missing_internal_bars,
            "missing_bar_frac": missing_bar_frac,
            "max_missing_bar_frac": max_missing_bar_frac,
            "gap_ranges_sample": gaps[:50],
            "invalid_ohlc_rows": int(sum(f.get("invalid_ohlc_rows", 0) or 0 for f in readable)),
            "outside_month_rows": int(sum(f.get("outside_month_rows", 0) or 0 for f in readable)),
            "volume_column": bool(any(f.get("volume_column") for f in readable)),
            "zero_volume_rows": sum(int(f.get("zero_volume_rows", 0) or 0) for f in readable if f.get("zero_volume_rows") is not None),
            "checksum_verified": False,
            "checksum_reason": "raw Binance zip/checksum file not present in local parquet cache",
            "data_hash": sha256_json(data_hash_payload),
            "valid_for_research": valid_for_research,
            "audit_warnings": warnings,
            "gap_file_count": gap_file_count,
            "invalid_file_count": len(hard_invalid_files),
            "invalid_files_sample": hard_invalid_files[:30],
            "files": readable,
        }

    def normalized_frame(self) -> pd.DataFrame:
        if not self.frames:
            return pd.DataFrame()
        out = pd.concat(self.frames, ignore_index=True)
        out = out.sort_values("open_time").drop_duplicates("open_time", keep="last")
        keep = [col for col in ["open_time", "open", "high", "low", "close", "volume"] if col in out.columns]
        return out[keep].reset_index(drop=True)


def discover_files(cache_dir: Path) -> dict[tuple[str, str, str], Path]:
    out = {}
    for path in cache_dir.glob("*.parquet"):
        match = FILENAME_RE.match(path.name)
        if not match:
            continue
        out[(match.group("symbol"), match.group("timeframe"), match.group("month"))] = path
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit normalized Binance kline parquet cache and emit manifests.")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    parser.add_argument("--manifest-dir", default=str(DEFAULT_MANIFESTS))
    parser.add_argument("--audit-dir", default=str(DEFAULT_AUDITS))
    parser.add_argument("--normalized-dir", default=str(DEFAULT_NORMALIZED))
    parser.add_argument("--symbols", default="")
    parser.add_argument("--timeframes", default="4h")
    parser.add_argument("--start", default="2017-08")
    parser.add_argument("--end", default="2026-05")
    parser.add_argument("--write-normalized", action="store_true")
    parser.add_argument("--limit-months", type=int, default=0)
    parser.add_argument("--max-missing-bar-frac", type=float, default=0.0015)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any selected manifest is invalid.")
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    manifest_dir = Path(args.manifest_dir)
    audit_dir = Path(args.audit_dir)
    normalized_dir = Path(args.normalized_dir)
    files = discover_files(cache_dir)
    if not files:
        print(f"No parquet cache files found under {cache_dir}", file=sys.stderr)
        return 2

    symbols = parse_list(args.symbols)
    timeframes = parse_list(args.timeframes)
    if not symbols:
        symbols = sorted({key[0] for key in files if key[1] in set(timeframes)})
    selected_months = month_range(args.start, args.end)
    if args.limit_months > 0:
        selected_months = selected_months[: args.limit_months]

    file_reports: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []
    for symbol in symbols:
        for timeframe in timeframes:
            agg = Aggregate(symbol=symbol, timeframe=timeframe)
            for month in selected_months:
                path = files.get((symbol, timeframe, month))
                if path is None:
                    missing_files.append({"symbol": symbol, "timeframe": timeframe, "month": month})
                    continue
                report, frame = audit_frame(path, symbol, timeframe, month)
                file_reports.append(report)
                agg.add(report, frame)
            manifest = agg.manifest(args.start, args.end, args.max_missing_bar_frac)
            manifest["missing_requested_month_files"] = missing_files_for(symbol, timeframe, selected_months, files)
            manifests.append(manifest)
            save_json(manifest_dir / f"{symbol}_{timeframe}_{args.start}_{args.end}.json", manifest)
            if args.write_normalized:
                frame = agg.normalized_frame()
                if not frame.empty:
                    out_dir = normalized_dir / f"klines_{timeframe}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    frame.to_parquet(out_dir / f"{symbol}_{timeframe}.parquet", index=False)

    timestamp_report: dict[str, Any] = {}
    for report in file_reports:
        unit = report.get("timestamp_unit_detected", "unknown")
        timestamp_report[unit] = timestamp_report.get(unit, 0) + 1

    gap_report = [
        {
            "symbol": m["symbol"],
            "timeframe": m["interval"],
            "missing_internal_bars": m["missing_internal_bars"],
            "months_missing_between_first_last": m["months_missing_between_first_last"],
            "missing_requested_month_files": m["missing_requested_month_files"],
            "gap_ranges_sample": m["gap_ranges_sample"],
        }
        for m in manifests
        if m["missing_internal_bars"] or m["months_missing_between_first_last"] or m["missing_requested_month_files"]
    ]
    checksum_report = {
        "checksum_verified": False,
        "reason": "existing cache contains parquet derivatives, not Binance raw zip/checksum files",
        "files_hashed": len(file_reports),
        "raw_sha256_available": True,
    }
    summary = {
        "schema_version": 1,
        "created_at": utc_now(),
        "cache_dir": str(cache_dir),
        "manifest_dir": str(manifest_dir),
        "audit_dir": str(audit_dir),
        "symbols": symbols,
        "timeframes": timeframes,
        "start": args.start,
        "end": args.end,
        "file_count": len(file_reports),
        "manifest_count": len(manifests),
        "valid_manifest_count": sum(1 for m in manifests if m.get("valid_for_research")),
        "invalid_manifest_count": sum(1 for m in manifests if not m.get("valid_for_research")),
        "timestamp_unit_report": timestamp_report,
        "gap_report_path": str(audit_dir / "gap_report.json"),
        "checksum_report_path": str(audit_dir / "checksum_report.json"),
        "manifest_paths": [str(manifest_dir / f"{m['symbol']}_{m['interval']}_{args.start}_{args.end}.json") for m in manifests],
        "summary_hash": sha256_json([m.get("data_hash") for m in manifests]),
    }
    save_json(audit_dir / "binance_kline_audit_summary.json", summary)
    save_json(audit_dir / "file_report.json", file_reports)
    save_json(audit_dir / "gap_report.json", gap_report)
    save_json(audit_dir / "timestamp_unit_report.json", timestamp_report)
    save_json(audit_dir / "checksum_report.json", checksum_report)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict and summary["invalid_manifest_count"]:
        return 1
    return 0


def missing_files_for(symbol: str, timeframe: str, months: list[str], files: dict[tuple[str, str, str], Path]) -> list[str]:
    return [month for month in months if (symbol, timeframe, month) not in files]


if __name__ == "__main__":
    raise SystemExit(main())
