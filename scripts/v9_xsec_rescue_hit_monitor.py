#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_diagnostic_walkforward_report import load_rows


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def float_or(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def cost_block(row: dict[str, Any], key: str) -> dict[str, Any]:
    return dict((row.get(key) or (row.get("selection") or {}).get(key) or {}))


def yearly_return(row: dict[str, Any], bucket: str) -> float:
    yearly = cost_block(row, "cost20").get("yearly") or {}
    values = yearly.get(bucket) if isinstance(yearly, dict) else None
    if not isinstance(values, dict):
        return 0.0
    return float_or(values.get("net_return"))


def failed_checks(row: dict[str, Any]) -> list[str]:
    checks = row.get("advance_checks") or {}
    if not isinstance(checks, dict):
        return []
    return [str(name) for name, passed in checks.items() if not passed]


def compact_config(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("config") or cost_block(row, "cost20").get("config") or {}
    keys = (
        "score_mode",
        "lookback_h",
        "skip_h",
        "rebalance_h",
        "k",
        "market_filter_h",
        "market_confirm_h",
        "market_drawdown_limit",
        "vol_target_ann",
        "drawdown_stop",
        "cooldown_h",
        "hedge_ratio",
        "n_tranches",
        "portfolio_mode",
    )
    return {key: cfg.get(key) for key in keys if key in cfg}


def row_metrics(row: dict[str, Any], hostile_year: str) -> dict[str, Any]:
    cost20 = cost_block(row, "cost20")
    cost40 = cost_block(row, "cost40")
    return {
        "advance_passed": bool(row.get("advance_passed")),
        "failed_checks": failed_checks(row),
        "hostile_year": hostile_year,
        "hostile_year_return20": yearly_return(row, hostile_year),
        "sharpe20": float_or(cost20.get("sharpe")),
        "sharpe40": float_or(cost40.get("sharpe")),
        "return20": float_or(cost20.get("total_return")),
        "max_drawdown20": float_or(cost20.get("max_drawdown")),
        "bootstrap_p5": float_or(cost20.get("bootstrap_30d_sharpe_p5")),
        "active_rebalances40": float_or(cost40.get("active_rebalance_event_count")),
        "time_in_market40": float_or(cost40.get("time_in_market_frac")),
        "config": compact_config(row),
    }


def hit_score(hit: dict[str, Any]) -> tuple[float, ...]:
    return (
        1.0 if hit["advance_passed"] else 0.0,
        float(hit["hostile_year_return20"]),
        float(hit["sharpe20"]),
        float(hit["sharpe40"]),
        float(hit["bootstrap_p5"]),
        -float(hit["max_drawdown20"]),
    )


def build_report(
    artifact: Path,
    *,
    hostile_year: str,
    min_sharpe20: float,
    min_year_return20: float,
    min_sharpe40: float,
    max_drawdown20: float,
    top_limit: int,
) -> dict[str, Any]:
    rows, meta, source = load_rows(artifact)
    total_rows = int((meta or {}).get("total_rows") or len(rows))
    hits = []
    watchlist = []
    for idx, row in enumerate(rows):
        metrics = row_metrics(row, hostile_year)
        metrics["row_index"] = idx
        year_ok = metrics["hostile_year_return20"] >= min_year_return20
        sharpe20_ok = metrics["sharpe20"] >= min_sharpe20
        sharpe40_ok = metrics["sharpe40"] >= min_sharpe40
        dd_ok = metrics["max_drawdown20"] <= max_drawdown20
        metrics["hit_checks"] = {
            "hostile_year_return20_ge_min": year_ok,
            "sharpe20_ge_min": sharpe20_ok,
            "sharpe40_ge_min": sharpe40_ok,
            "max_drawdown20_le_max": dd_ok,
        }
        if year_ok and sharpe20_ok and sharpe40_ok and dd_ok:
            hits.append(metrics)
        elif year_ok or (sharpe20_ok and metrics["hostile_year_return20"] > -0.03):
            watchlist.append(metrics)

    hits.sort(key=hit_score, reverse=True)
    watchlist.sort(key=hit_score, reverse=True)
    return {
        "kind": "xsec_rescue_hit_monitor_v1",
        "created_at": now_utc(),
        "artifact": str(artifact),
        "source": source,
        "completed_rows": len(rows),
        "total_rows": total_rows,
        "progress": (len(rows) / total_rows) if total_rows else None,
        "criteria": {
            "hostile_year": hostile_year,
            "min_sharpe20": min_sharpe20,
            "min_year_return20": min_year_return20,
            "min_sharpe40": min_sharpe40,
            "max_drawdown20": max_drawdown20,
        },
        "hit_count": len(hits),
        "watchlist_count": len(watchlist),
        "hits": hits[:top_limit],
        "watchlist": watchlist[:top_limit],
        "safety": {
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "note": "Read-only monitor; hits still require official ingest, validation, holdout, and paper gates.",
        },
    }


def format_text(report: dict[str, Any]) -> str:
    progress = report.get("progress")
    progress_text = f"{progress:.3f}" if isinstance(progress, float) else "n/a"
    lines = [
        f"created_at={report['created_at']}",
        f"source={report['source']}",
        f"artifact={report['artifact']}",
        f"rows={report['completed_rows']}/{report.get('total_rows') or '?'} progress={progress_text}",
        f"criteria={json.dumps(report['criteria'], sort_keys=True)}",
        f"hit_count={report['hit_count']} watchlist_count={report['watchlist_count']}",
        "safety=paper:False live:False",
    ]
    if report["hits"]:
        lines.append("hits:")
        for hit in report["hits"]:
            lines.append(
                "- row={row_index} sh20={sharpe20:.3f} sh40={sharpe40:.3f} "
                "year={hostile_year_return20:.3f} dd={max_drawdown20:.3f} "
                "boot={bootstrap_p5:.3f} advance={advance_passed} fails={fails} cfg={cfg}".format(
                    row_index=hit["row_index"],
                    sharpe20=hit["sharpe20"],
                    sharpe40=hit["sharpe40"],
                    hostile_year_return20=hit["hostile_year_return20"],
                    max_drawdown20=hit["max_drawdown20"],
                    bootstrap_p5=hit["bootstrap_p5"],
                    advance_passed=hit["advance_passed"],
                    fails=",".join(hit["failed_checks"]) or "none",
                    cfg=json.dumps(hit["config"], sort_keys=True),
                )
            )
    else:
        lines.append("hits: none")
    if report["watchlist"]:
        lines.append("watchlist:")
        for hit in report["watchlist"]:
            lines.append(
                "- row={row_index} sh20={sharpe20:.3f} sh40={sharpe40:.3f} "
                "year={hostile_year_return20:.3f} dd={max_drawdown20:.3f} "
                "checks={checks} cfg={cfg}".format(
                    row_index=hit["row_index"],
                    sharpe20=hit["sharpe20"],
                    sharpe40=hit["sharpe40"],
                    hostile_year_return20=hit["hostile_year_return20"],
                    max_drawdown20=hit["max_drawdown20"],
                    checks=json.dumps(hit["hit_checks"], sort_keys=True),
                    cfg=json.dumps(hit["config"], sort_keys=True),
                )
            )
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], out_json: Path, out_text: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_text.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    out_text.write_text(format_text(report))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only XSEC hostile-year rescue hit monitor.")
    parser.add_argument("artifact", help="Final .json or active .progress.jsonl")
    parser.add_argument("--hostile-year", default="2022")
    parser.add_argument("--min-sharpe20", type=float, default=1.5)
    parser.add_argument("--min-year-return20", type=float, default=0.0)
    parser.add_argument("--min-sharpe40", type=float, default=1.0)
    parser.add_argument("--max-drawdown20", type=float, default=0.25)
    parser.add_argument("--top-limit", type=int, default=10)
    parser.add_argument("--out-json", default="state/xsec_rescue_hit_monitor.json")
    parser.add_argument("--out-text", default="state/xsec_rescue_hit_monitor.txt")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=300.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact = Path(args.artifact)
    out_json = Path(args.out_json)
    out_text = Path(args.out_text)
    while True:
        report = build_report(
            artifact,
            hostile_year=str(args.hostile_year),
            min_sharpe20=float(args.min_sharpe20),
            min_year_return20=float(args.min_year_return20),
            min_sharpe40=float(args.min_sharpe40),
            max_drawdown20=float(args.max_drawdown20),
            top_limit=max(1, int(args.top_limit)),
        )
        write_report(report, out_json, out_text)
        print(format_text(report), end="")
        if not args.loop:
            return 0
        time.sleep(max(1.0, float(args.sleep_sec)))


if __name__ == "__main__":
    raise SystemExit(main())
