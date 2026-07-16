#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXCHANGE_INFO_API = "https://api.binance.com/api/v3/exchangeInfo"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    suffix = ""
    if params:
        suffix = "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url + suffix, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def build_universe(args: argparse.Namespace) -> dict[str, Any]:
    quote_asset = str(args.quote_asset).upper()
    exchange_info = fetch_json(args.api_url)
    rows = []
    for row in exchange_info.get("symbols", []):
        if row.get("status") != "TRADING":
            continue
        if row.get("quoteAsset") != quote_asset:
            continue
        symbol = str(row.get("symbol", "")).upper()
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "base_asset": row.get("baseAsset"),
                "quote_asset": row.get("quoteAsset"),
                "status": row.get("status"),
                "is_spot_trading_allowed": bool(row.get("isSpotTradingAllowed", True)),
            }
        )
    rows.sort(key=lambda item: item["symbol"])
    return {
        "kind": "binance_spot_usdt_universe_snapshot_v1",
        "updated_at": now_utc(),
        "api_url": args.api_url,
        "quote_asset": quote_asset,
        "selected_count": len(rows),
        "symbols": [row["symbol"] for row in rows],
        "rows": rows,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def format_text(report: dict[str, Any]) -> str:
    lines = [
        f"updated_at={report['updated_at']}",
        f"quote_asset={report['quote_asset']}",
        f"selected_count={report['selected_count']}",
        "safety=paper:False live:False",
    ]
    lines.append("symbols=" + ",".join(report["symbols"][:40]))
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Binance spot USDT trading-pair snapshot.")
    parser.add_argument("--api-url", default=EXCHANGE_INFO_API)
    parser.add_argument("--quote-asset", default="USDT")
    parser.add_argument("--out-json", default="artifacts/v9/universe/binance_spot_usdt_universe_snapshot.json")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = build_universe(args)
    write_json(report, Path(args.out_json))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(report), flush=True)


if __name__ == "__main__":
    main()
