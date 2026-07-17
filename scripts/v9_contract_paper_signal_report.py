#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.v9_contract_latest_market_signal import load_symbol_cache, safe_float


DEFAULT_SOURCES = (
    ("1h", "state/contract_latest_market_signal_journal.jsonl"),
    ("15m", "state/contract_latest_market_signal_15m_journal.jsonl"),
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_sources(raw: str) -> tuple[tuple[str, str], ...]:
    if not raw.strip():
        return DEFAULT_SOURCES
    out = []
    for item in raw.split(","):
        part = item.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"source must be TIMEFRAME:PATH, got {part!r}")
        timeframe, path = part.split(":", 1)
        out.append((timeframe.strip(), path.strip()))
    return tuple(out or DEFAULT_SOURCES)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_close(cache_dir: Path, symbol: str, timeframe: str, lookback_bars: int) -> dict[str, Any]:
    frame = load_symbol_cache(cache_dir, symbol, timeframe, lookback_bars=lookback_bars)
    if frame.empty:
        return {"latest_close": None, "latest_dt": None}
    row = frame.iloc[-1]
    return {
        "latest_close": safe_float(row.get("close")),
        "latest_dt": row.get("dt").isoformat(),
    }


def current_r_multiple(record: dict[str, Any], latest: float | None) -> float | None:
    if latest is None:
        return None
    side = str(record.get("side"))
    entry = safe_float(record.get("entry_price"))
    stop = safe_float(record.get("stop_loss"))
    risk = entry - stop if side == "long" else stop - entry
    if risk <= 0:
        return None
    if side == "long":
        return float((latest - entry) / risk)
    if side == "short":
        return float((entry - latest) / risk)
    return None


def current_directional_pct(record: dict[str, Any], latest: float | None) -> float | None:
    if latest is None:
        return None
    side = str(record.get("side"))
    entry = safe_float(record.get("entry_price"))
    if entry <= 0:
        return None
    raw = latest / entry - 1.0
    return float(raw if side == "long" else -raw)


def enrich_record(
    record: dict[str, Any],
    *,
    timeframe: str,
    cache_dir: Path,
    lookback_bars: int,
    latest_cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(record.get("symbol", "")).upper()
    latest_key = (timeframe, symbol)
    if latest_key not in latest_cache:
        latest_cache[latest_key] = latest_close(cache_dir, symbol, timeframe, lookback_bars)
    latest = latest_cache[latest_key]
    latest_price = latest.get("latest_close")
    outcome = record.get("outcome") or {}
    current_r = current_r_multiple(record, latest_price)
    current_pct = current_directional_pct(record, latest_price)
    return {
        **record,
        "timeframe": timeframe,
        "latest_close": latest_price,
        "latest_dt": latest.get("latest_dt"),
        "current_r_multiple": current_r,
        "current_directional_pct": current_pct,
        "completed_r_multiple": outcome.get("r_multiple"),
        "exit_reason": outcome.get("exit_reason"),
        "exit_dt": outcome.get("exit_dt"),
    }


def outcome_label(row: dict[str, Any]) -> str:
    if row.get("status") != "completed":
        value = row.get("current_r_multiple")
        if value is None:
            return "open"
        if value > 0:
            return "open_profit"
        if value < 0:
            return "open_loss"
        return "open_flat"
    value = row.get("completed_r_multiple")
    if value is None:
        return "completed_unknown"
    if float(value) > 0:
        return "win"
    if float(value) < 0:
        return "loss"
    return "flat"


def fmt_num(value: Any, digits: int = 6) -> str:
    if value is None:
        return ""
    number = safe_float(value, float("nan"))
    if pd.isna(number):
        return ""
    if abs(number) >= 100:
        return f"{number:.2f}"
    if abs(number) >= 1:
        return f"{number:.4f}"
    return f"{number:.{digits}f}"


def fmt_pct(value: Any) -> str:
    if value is None:
        return ""
    return f"{safe_float(value) * 100:.2f}%"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    sources = parse_sources(args.sources)
    latest_cache: dict[tuple[str, str], dict[str, Any]] = {}
    records = []
    source_summaries = []
    for timeframe, journal_path in sources:
        path = Path(journal_path)
        raw_rows = read_jsonl(path)
        source_summaries.append(
            {
                "timeframe": timeframe,
                "journal_path": str(path),
                "record_count": len(raw_rows),
            }
        )
        for record in raw_rows:
            records.append(
                enrich_record(
                    record,
                    timeframe=timeframe,
                    cache_dir=Path(args.cache_dir),
                    lookback_bars=args.lookback_bars,
                    latest_cache=latest_cache,
                )
            )
    records.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
    open_rows = [row for row in records if row.get("status") == "open"]
    completed_rows = [row for row in records if row.get("status") == "completed"]
    wins = [row for row in completed_rows if safe_float(row.get("completed_r_multiple")) > 0]
    losses = [row for row in completed_rows if safe_float(row.get("completed_r_multiple")) < 0]
    payload = {
        "kind": "contract_paper_signal_report_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "sources": source_summaries,
        "summary": {
            "records": len(records),
            "open": len(open_rows),
            "completed": len(completed_rows),
            "wins": len(wins),
            "losses": len(losses),
            "analog_supported_open": sum(1 for row in open_rows if row.get("analog_supported")),
        },
        "open": open_rows[: args.max_rows],
        "completed": completed_rows[: args.max_rows],
        "records": records,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    return payload


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Contract Paper Signal Report",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- records: `{summary['records']}`",
        f"- open: `{summary['open']}`",
        f"- completed: `{summary['completed']}`",
        f"- wins/losses: `{summary['wins']}/{summary['losses']}`",
        f"- analog_supported_open: `{summary['analog_supported_open']}`",
        "",
        "## Open Paper Signals",
        "",
        "| timeframe | created_at | symbol | side | analog | entry | latest | stop | "
        "take_profit | current_R | current_% | status |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["open"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('created_at')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('analog_supported')} | {fmt_num(row.get('entry_price'))} | "
            f"{fmt_num(row.get('latest_close'))} | "
            f"{fmt_num(row.get('stop_loss'))} | {fmt_num(row.get('take_profit'))} | "
            f"{fmt_num(row.get('current_r_multiple'), 3)} | {fmt_pct(row.get('current_directional_pct'))} | "
            f"{outcome_label(row)} |"
        )
    lines.extend(
        [
            "",
            "## Completed Paper Signals",
            "",
            "| timeframe | created_at | symbol | side | analog | entry | stop | "
            "take_profit | exit_reason | R | result |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |",
        ]
    )
    for row in payload["completed"]:
        lines.append(
            f"| {row.get('timeframe')} | {row.get('created_at')} | {row.get('symbol')} | {row.get('side')} | "
            f"{row.get('analog_supported')} | {fmt_num(row.get('entry_price'))} | {fmt_num(row.get('stop_loss'))} | "
            f"{fmt_num(row.get('take_profit'))} | {row.get('exit_reason')} | "
            f"{fmt_num(row.get('completed_r_multiple'), 3)} | {outcome_label(row)} |"
        )
    lines.extend(["", "Paper report only. No live trading is authorized."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"updated_at={payload['updated_at']}",
        f"records={summary['records']} open={summary['open']} completed={summary['completed']}",
        f"wins={summary['wins']} losses={summary['losses']} analog_supported_open={summary['analog_supported_open']}",
        "safety=paper_authorized:False live:False",
    ]
    for row in payload["open"][:10]:
        lines.append(
            f"{row.get('timeframe')} {row.get('symbol')} {row.get('side')} "
            f"entry={fmt_num(row.get('entry_price'))} latest={fmt_num(row.get('latest_close'))} "
            f"stop={fmt_num(row.get('stop_loss'))} tp={fmt_num(row.get('take_profit'))} "
            f"R={fmt_num(row.get('current_r_multiple'), 3)} result={outcome_label(row)}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a readable report for paper-only contract market signals.")
    parser.add_argument("--cache-dir", default="data/binance_usdm_ohlcv_cache")
    parser.add_argument("--sources", default="")
    parser.add_argument("--lookback-bars", type=int, default=200)
    parser.add_argument("--max-rows", type=int, default=80)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_paper_signal_report_latest.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_paper_signal_report_latest.md")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = build_report(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
