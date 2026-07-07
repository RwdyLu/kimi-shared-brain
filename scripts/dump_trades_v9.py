#!/usr/bin/env python3
"""Dump train-only execution logs for a frozen genome.

This script is intentionally thin: it calls the existing evaluator with
``record_trades=True`` and serializes the resulting execution events. It must
not duplicate fill, fee, or PnL logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v7_robust as v7  # noqa: E402
import lunar_genome_symbol_validate_v7 as sv  # noqa: E402


DEFAULT_FROZEN = "results/frozen/v8_link_candidates_batch1_20260706.json"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Dump train-only execution logs for a frozen v8/v9 candidate")
    ap.add_argument("--frozen", default=DEFAULT_FROZEN)
    ap.add_argument("--candidate-index", type=int, default=1)
    ap.add_argument("--symbol", default="LINKUSDT")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--start", default="2017-08")
    ap.add_argument("--end", default="2024-06")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--scenarios", type=int, default=24)
    ap.add_argument("--scenario-costs", default="20,30,50")
    ap.add_argument("--months-per-symbol", type=int, default=4)
    ap.add_argument("--window-bars", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20260706)
    ap.add_argument("--data-manifest-dir", default="data/manifests/lowfreq1h_core8")
    ap.add_argument("--data-cache-dir", default="data/binance_public_cache")
    ap.add_argument("--regime-report", default="artifacts/v9/regime_report.json")
    ap.add_argument("--out", default="artifacts/v9/trade_logs/v8_link_candidate1_train_trades.jsonl")
    ap.add_argument("--summary", default="artifacts/v9/trade_logs/v8_link_candidate1_train_trades_summary.json")
    return ap.parse_args()


def sha256_payload(obj: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def build_eval_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        symbols=[args.symbol],
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        months_per_symbol=args.months_per_symbol,
        window_bars=args.window_bars,
        scenarios=args.scenarios,
        scenario_costs=args.scenario_costs,
        data_manifest_dir=args.data_manifest_dir,
        data_audit_summary_hash="",
        data_cache_dir=args.data_cache_dir,
        initial_cash=10000.0,
        cost_bps=20.0,
        lot_step=0.0001,
        lot_min=0.0001,
        min_notional=10.0,
        drawdown_penalty=1.0,
        max_drawdown=0.20,
        max_trades=720,
        min_trades=10,
        min_positive_alpha_frac=1.0,
        min_survival_rate=1.0,
        min_alpha=0.0,
        min_return=0.0,
        signal_delay_bars=0,
        record_trades=True,
    )


def load_candidate(path: Path, candidate_index: int) -> dict[str, Any]:
    obj = json.loads(path.read_text())
    candidates = obj.get("candidates") or []
    if candidate_index < 1 or candidate_index > len(candidates):
        raise SystemExit(f"candidate-index {candidate_index} outside 1..{len(candidates)}")
    return candidates[candidate_index - 1]


def assert_train_only_scenarios(scenarios: list[dict[str, Any]], symbol: str, embargo_start: str) -> None:
    embargo = pd.Timestamp(embargo_start, tz="UTC")
    for sc in scenarios:
        for month in (sc.get("selected") or {}).get(symbol, []):
            month_start = pd.Timestamp(str(month) + "-01", tz="UTC")
            if month_start >= embargo:
                raise SystemExit(f"scenario {sc.get('scenario')} selected non-train month {month}")


def load_regime_map(report_path: str, symbol: str, embargo_start: str) -> tuple[dict[str, str], str | None]:
    if not report_path:
        return {}, None
    report = json.loads(Path(report_path).read_text())
    label_path = (report.get("outputs", {}).get("labels") or {}).get(symbol)
    if not label_path:
        return {}, report.get("config_sha256")
    df = pd.read_parquet(label_path)
    df["dt"] = pd.to_datetime(df["dt"], utc=True, errors="coerce")
    embargo = pd.Timestamp(embargo_start, tz="UTC")
    if (df["dt"] >= embargo).any():
        bad = df.loc[df["dt"] >= embargo, "dt"].min()
        raise SystemExit(f"regime labels include embargo/holdout date {bad}")
    return {str(row.dt.date()): str(row.regime_id) for row in df.itertuples()}, report.get("config_sha256")


def regime_for_ts(regime_map: dict[str, str], ts: str) -> str | None:
    if not ts:
        return None
    day = str(pd.Timestamp(ts).date())
    return regime_map.get(day)


def main() -> int:
    args = parse_args()
    started = time.time()
    frozen_path = Path(args.frozen)
    candidate = load_candidate(frozen_path, args.candidate_index)
    genome = v7.dict_to_genome(candidate.get("genome") or {})
    if genome is None:
        raise SystemExit("invalid candidate genome")
    genome_hash = sha256_payload(candidate.get("genome") or {})

    eval_args = build_eval_args(args)
    rng = random.Random(args.seed)
    scenarios = sv.make_symbol_scenarios(eval_args, rng, args.symbol)
    assert_train_only_scenarios(scenarios, args.symbol, args.embargo_start)
    regime_map, regime_hash = load_regime_map(args.regime_report, args.symbol, args.embargo_start)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    per_scenario: list[dict[str, Any]] = []
    by_regime: dict[str, dict[str, Any]] = {}
    by_action: dict[str, int] = {}
    max_ts = None
    with out.open("w") as fh:
        for sc in scenarios:
            eval_args.cost_bps = sc["cost_bps"]
            score, metrics = v7.robust_evaluate(genome, [sc], eval_args)
            row = (metrics.get("rows") or [{}])[0]
            per_symbol = (row.get("per_symbol") or {}).get(args.symbol) or {}
            trades = per_symbol.get("trade_log") or []
            expected_trades = int(per_symbol.get("trades", 0))
            if expected_trades != len(trades):
                raise SystemExit(
                    f"trade count mismatch scenario={sc.get('scenario')} cost={sc.get('cost_bps')}: "
                    f"metric={expected_trades} log={len(trades)}"
                )
            fee_sum = sum(float(t.get("fee", 0.0)) for t in trades)
            cost = float(per_symbol.get("cost", 0.0))
            if abs(fee_sum - cost) > max(1e-6, abs(cost) * 1e-9):
                raise SystemExit(
                    f"fee mismatch scenario={sc.get('scenario')} cost={sc.get('cost_bps')}: metric={cost} log={fee_sum}"
                )
            cash = float(per_symbol.get("trade_log_initial_cash", eval_args.initial_cash))
            qty = 0.0
            for trade in trades:
                cash += float(trade.get("cash_delta", 0.0))
                qty += float(trade.get("qty_delta", 0.0))
            final_price = float(per_symbol.get("trade_log_final_price", 0.0))
            reconstructed_equity = cash + qty * final_price
            equity = float(per_symbol.get("equity", 0.0))
            if abs(reconstructed_equity - equity) > max(1e-5, abs(equity) * 1e-8):
                raise SystemExit(
                    f"equity reconstruction mismatch scenario={sc.get('scenario')} cost={sc.get('cost_bps')}: "
                    f"metric={equity} reconstructed={reconstructed_equity}"
                )
            for trade in trades:
                ts = trade.get("ts") or ""
                if ts:
                    tstamp = pd.Timestamp(ts)
                    if tstamp >= pd.Timestamp(args.embargo_start, tz="UTC"):
                        raise SystemExit(f"trade timestamp {ts} is on/after embargo {args.embargo_start}")
                    max_ts = max(max_ts, tstamp) if max_ts is not None else tstamp
                enriched = dict(trade)
                enriched.update(
                    {
                        "scenario": sc.get("scenario"),
                        "cost_bps": sc.get("cost_bps"),
                        "symbol": args.symbol,
                        "candidate_index": args.candidate_index,
                        "genome_hash": genome_hash,
                        "code_version": "trade_log_v9_execution_event_v1",
                        "regime_at_execution": regime_for_ts(regime_map, ts),
                        "regime_config_sha256": regime_hash,
                    }
                )
                regime = str(enriched.get("regime_at_execution") or "unknown")
                action = str(enriched.get("action") or "unknown")
                by_action[action] = by_action.get(action, 0) + 1
                bucket = by_regime.setdefault(
                    regime,
                    {
                        "events": 0,
                        "buy_events": 0,
                        "sell_events": 0,
                        "gross": 0.0,
                        "fees": 0.0,
                        "realized_pnl": 0.0,
                        "qty_abs": 0.0,
                    },
                )
                bucket["events"] += 1
                if enriched.get("side") == "buy":
                    bucket["buy_events"] += 1
                elif enriched.get("side") == "sell":
                    bucket["sell_events"] += 1
                bucket["gross"] += float(enriched.get("gross", 0.0))
                bucket["fees"] += float(enriched.get("fee", 0.0))
                bucket["realized_pnl"] += float(enriched.get("realized_pnl", 0.0))
                bucket["qty_abs"] += abs(float(enriched.get("qty_delta", 0.0)))
                fh.write(json.dumps(enriched, sort_keys=True) + "\n")
                written += 1
            per_scenario.append(
                {
                    "scenario": sc.get("scenario"),
                    "cost_bps": sc.get("cost_bps"),
                    "trades": len(trades),
                    "return": per_symbol.get("return"),
                    "alpha": per_symbol.get("alpha"),
                    "max_drawdown": per_symbol.get("max_drawdown"),
                    "equity": per_symbol.get("equity"),
                    "fee_sum": fee_sum,
                }
            )

    summary = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(time.time() - started, 3),
        "out": str(out),
        "frozen": str(frozen_path),
        "candidate_index": args.candidate_index,
        "symbol": args.symbol,
        "genome_hash": genome_hash,
        "train_window": {"start": args.start, "end": args.end, "embargo_start": args.embargo_start},
        "scenario_count": len(scenarios),
        "trade_events": written,
        "max_trade_ts": str(max_ts) if max_ts is not None else None,
        "regime_report": args.regime_report,
        "regime_config_sha256": regime_hash,
        "by_regime": by_regime,
        "by_action": by_action,
        "per_scenario": per_scenario,
        "schema_note": "Execution/order events from spot inventory evaluator; not contract round-trips or per-trade CVaR.",
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps({
        "out": str(out),
        "summary": args.summary,
        "trade_events": written,
        "scenario_count": len(scenarios),
        "max_trade_ts": summary["max_trade_ts"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
