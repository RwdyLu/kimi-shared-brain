#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_paper_readiness_gate import shadow_oos_report, write_json, write_text  # noqa: E402
from v9.contract.simulator import utc_ts  # noqa: E402
from v9.contract.xsec_momentum import load_close_matrix  # noqa: E402


DEFAULT_SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_evaluation_end(value: str) -> str:
    if str(value).strip().lower() == "now":
        return now_utc()
    return value


def to_utc_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def paper_status(
    *,
    evaluation_start: str,
    latest_dt: str,
    metrics_40bps: dict[str, Any],
    min_weeks: int,
    min_rebalances: int,
    max_drawdown: float,
) -> tuple[str, dict[str, bool]]:
    start = to_utc_timestamp(evaluation_start)
    latest = to_utc_timestamp(latest_dt)
    age_days = max(0.0, (latest - start).total_seconds() / 86400.0)
    checks = {
        "paper_age_ge_min_weeks": age_days >= float(min_weeks * 7),
        "paper_rebalances_ge_min": int(metrics_40bps.get("rebalance_event_count") or 0) >= int(min_rebalances),
        "paper_drawdown_le_max": float(metrics_40bps.get("max_drawdown") or 0.0) <= float(max_drawdown),
        "paper_live_not_authorized": True,
    }
    if not checks["paper_drawdown_le_max"]:
        return "paper_stopped_risk_review_required", checks
    if all(checks.values()):
        return "paper_complete_live_manual_review_required", checks
    return "paper_running", checks


def signal_rows(shadow: dict[str, Any]) -> list[dict[str, Any]]:
    latest_dt = shadow.get("latest_dt")
    rows = []
    for symbol, weight in (shadow.get("latest_weights") or {}).items():
        pair = symbol[:-4] + "/USDT" if symbol.endswith("USDT") else symbol
        rows.append(
            {
                "date": latest_dt,
                "pair": pair,
                "symbol": symbol,
                "target_weight": float(weight),
                "enter_long": 1 if float(weight) > 0.0 else 0,
                "exit_long": 1 if float(weight) == 0.0 else 0,
            }
        )
    return rows


def format_signals_csv(rows: list[dict[str, Any]]) -> str:
    lines = ["date,pair,symbol,target_weight,enter_long,exit_long"]
    for row in rows:
        lines.append(
            f"{row['date']},{row['pair']},{row['symbol']},{row['target_weight']:.10f},{row['enter_long']},{row['exit_long']}"
        )
    return "\n".join(lines) + "\n"


def build_shadow_state(
    *,
    gate_state_path: Path,
    cache_dir: Path,
    evaluation_end: str,
    costs_bps: tuple[float, ...],
) -> dict[str, Any]:
    gate = read_json(gate_state_path)
    if not gate.get("paper_trading_authorized"):
        return {
            "kind": "xsec_paper_shadow_state_v1",
            "updated_at": now_utc(),
            "status": "blocked",
            "reason": "paper_readiness_gate_not_authorized",
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "source_gate": str(gate_state_path),
        }
    candidate = gate["candidate"]
    config = dict(candidate["config"])
    data = gate.get("data") or {}
    warmup_start = str(data.get("warmup_start") or "2024-07-01")
    evaluation_start = str(data.get("evaluation_start") or "2026-06-01")
    symbols = tuple(((gate.get("holdout_40bps") or {}).get("symbols") or DEFAULT_SYMBOLS))
    closes = load_close_matrix(cache_dir, symbols, utc_ts(warmup_start), utc_ts(evaluation_end), utc_ts("2100-01-01"))
    shadow = shadow_oos_report(
        closes=closes,
        config=config,
        evaluation_start=utc_ts(evaluation_start),
        costs_bps=costs_bps,
    )
    metrics_40 = (shadow.get("costs") or {}).get("40bps") or {}
    paper_gate = gate.get("paper_gate") or {}
    status, checks = paper_status(
        evaluation_start=evaluation_start,
        latest_dt=str(shadow.get("latest_dt")),
        metrics_40bps=metrics_40,
        min_weeks=int(paper_gate.get("minimum_duration_weeks") or 12),
        min_rebalances=int(paper_gate.get("minimum_rebalance_events") or 9),
        max_drawdown=float(paper_gate.get("max_paper_drawdown") or 0.15),
    )
    rows = signal_rows(shadow)
    return {
        "kind": "xsec_paper_shadow_state_v1",
        "updated_at": now_utc(),
        "status": status,
        "checks": checks,
        "paper_trading_authorized": True,
        "live_trading_authorized": False,
        "source_gate": str(gate_state_path),
        "candidate": candidate,
        "data": {
            "warmup_start": warmup_start,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
        },
        "shadow": shadow,
        "signals": rows,
        "note": "Paper shadow only. It writes target weights/signals and never authorizes live trading.",
    }


def format_text(state: dict[str, Any]) -> str:
    metrics = (((state.get("shadow") or {}).get("costs") or {}).get("40bps") or {})
    lines = [
        f"status={state.get('status')}",
        f"safety=paper:{state.get('paper_trading_authorized')} live:{state.get('live_trading_authorized')}",
        f"source_gate={state.get('source_gate')}",
        "paper_40bps="
        f"sharpe:{fmt(metrics.get('sharpe'))} "
        f"return:{fmt(metrics.get('total_return'))} "
        f"dd:{fmt(metrics.get('max_drawdown'))} "
        f"rebalances:{fmt(metrics.get('rebalance_event_count'), 0)}",
        f"latest_dt={(state.get('shadow') or {}).get('latest_dt')}",
        f"latest_weights={json.dumps((state.get('shadow') or {}).get('latest_weights') or {}, sort_keys=True)}",
        "checks=" + ",".join(f"{key}:{value}" for key, value in (state.get("checks") or {}).items()),
    ]
    return "\n".join(lines)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.{digits}f}"
    return "NA" if value is None else str(value)


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    costs = tuple(float(item.strip()) for item in args.costs_bps.split(",") if item.strip())
    state = build_shadow_state(
        gate_state_path=Path(args.gate_state),
        cache_dir=Path(args.cache_dir),
        evaluation_end=resolve_evaluation_end(args.evaluation_end),
        costs_bps=costs,
    )
    write_json(state, Path(args.out_json))
    write_text(format_text(state), Path(args.out_text))
    write_text(format_signals_csv(state.get("signals") or []), Path(args.signals_csv))
    if state.get("status") == "paper_complete_live_manual_review_required":
        marker = Path(args.marker_dir) / "FOUND_LIVE_CANARY_REVIEW_REQUIRED.txt"
        write_text(
            "FOUND_LIVE_CANARY_REVIEW_REQUIRED "
            f"{now_utc()} artifact={state['candidate']['artifact']} "
            "live_trading_authorized=False\n",
            marker,
        )
    return state


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XSEC paper shadow runner for paper-ready candidates")
    parser.add_argument("--gate-state", default="state/xsec_paper_readiness_gate_state.json")
    parser.add_argument("--cache-dir", default="data/binance_public_cache")
    parser.add_argument("--evaluation-end", default="now")
    parser.add_argument("--costs-bps", default="20,40,60,80")
    parser.add_argument("--out-json", default="state/xsec_paper_shadow_state.json")
    parser.add_argument("--out-text", default="state/xsec_paper_shadow_state.txt")
    parser.add_argument("--signals-csv", default="artifacts/v9/paper/xsec_paper_shadow_signals.csv")
    parser.add_argument("--marker-dir", default="state")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--sleep-sec", type=float, default=3600.0)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    while True:
        state = run_once(args)
        if args.format == "json":
            print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        else:
            print(format_text(state), flush=True)
        if not args.loop:
            return
        time.sleep(max(1.0, float(args.sleep_sec)))


if __name__ == "__main__":
    main()
