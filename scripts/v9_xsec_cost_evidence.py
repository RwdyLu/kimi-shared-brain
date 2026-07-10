#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen


BOOK_TICKER_URL = "https://api.binance.com/api/v3/ticker/bookTicker"
TICKER_24H_URL = "https://api.binance.com/api/v3/ticker/24hr"
CSV_COLUMNS = (
    "recorded_at",
    "latest_dt",
    "symbol",
    "bid",
    "ask",
    "mid",
    "spread_bps",
    "quote_volume_24h",
    "target_weight",
    "previous_weight",
    "target_weight_delta",
    "observed_cost_bps",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, timeout_sec: float = 10.0) -> Any:
    with urlopen(url, timeout=timeout_sec) as response:  # noqa: S310 - public market data only.
        return json.loads(response.read().decode("utf-8"))


def by_symbol(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("symbol")): row for row in rows if row.get("symbol")}


def read_ledger_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def public_market_snapshot(symbols: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    books = by_symbol(fetch_json(BOOK_TICKER_URL))
    volumes = by_symbol(fetch_json(TICKER_24H_URL))
    out = {}
    for symbol in symbols:
        book = books.get(symbol) or {}
        volume = volumes.get(symbol) or {}
        if not book:
            continue
        out[symbol] = {
            "bid": float(book["bidPrice"]),
            "ask": float(book["askPrice"]),
            "quote_volume_24h": float(volume.get("quoteVolume") or 0.0),
        }
    return out


def previous_weights_from_ledger(ledger_path: Path) -> dict[str, float]:
    records = read_ledger_records(ledger_path)
    if len(records) < 2:
        return {}
    return {
        str(symbol): float(weight)
        for symbol, weight in (records[-2].get("latest_weights") or {}).items()
    }


def cost_rows(
    *,
    state: dict[str, Any],
    previous_weights: dict[str, float],
    snapshot: dict[str, dict[str, Any]],
    recorded_at: str,
) -> list[dict[str, Any]]:
    shadow = state.get("shadow") or {}
    latest_weights = {
        str(symbol): float(weight)
        for symbol, weight in (shadow.get("latest_weights") or {}).items()
    }
    rows = []
    for symbol, target_weight in sorted(latest_weights.items()):
        market = snapshot.get(symbol)
        if not market:
            continue
        bid = float(market["bid"])
        ask = float(market["ask"])
        mid = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
        spread_bps = ((ask - bid) / mid * 10000.0) if mid > 0 else 0.0
        previous_weight = float(previous_weights.get(symbol, 0.0))
        rows.append(
            {
                "recorded_at": recorded_at,
                "latest_dt": shadow.get("latest_dt"),
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "spread_bps": spread_bps,
                "quote_volume_24h": float(market.get("quote_volume_24h") or 0.0),
                "target_weight": target_weight,
                "previous_weight": previous_weight,
                "target_weight_delta": target_weight - previous_weight,
                "observed_cost_bps": spread_bps,
            }
        )
    return rows


def append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in CSV_COLUMNS})


def append_cost_evidence(
    *,
    state: dict[str, Any],
    ledger_path: Path,
    out_csv: Path,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    if not state.get("paper_trading_authorized"):
        return {"rows_written": 0, "reason": "paper_not_authorized"}
    shadow = state.get("shadow") or {}
    symbols = tuple(str(symbol) for symbol in (shadow.get("latest_weights") or {}).keys())
    if not symbols:
        return {"rows_written": 0, "reason": "no_symbols"}
    recorded = recorded_at or now_utc()
    snapshot = public_market_snapshot(symbols)
    rows = cost_rows(
        state=state,
        previous_weights=previous_weights_from_ledger(ledger_path),
        snapshot=snapshot,
        recorded_at=recorded,
    )
    append_rows(out_csv, rows)
    return {"rows_written": len(rows), "path": str(out_csv), "recorded_at": recorded}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture public spread/volume evidence for XSEC paper shadow.")
    parser.add_argument("--shadow-state", default="state/xsec_paper_shadow_state.json")
    parser.add_argument("--ledger-jsonl", default="state/xsec_paper_ledger.jsonl")
    parser.add_argument("--out-csv", default="artifacts/v9/paper/xsec_cost_evidence.csv")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    state = json.loads(Path(args.shadow_state).read_text())
    result = append_cost_evidence(
        state=state,
        ledger_path=Path(args.ledger_jsonl),
        out_csv=Path(args.out_csv),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
