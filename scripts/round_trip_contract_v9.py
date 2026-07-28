#!/usr/bin/env python3
"""Build FIFO lot-level round trips from execution/order event logs.

This is an accounting view over the current spot/DCA inventory strategy. It is
not a futures contract simulator and it does not infer MAE/MFE without mark
data.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Convert execution events to FIFO round-trip accounting")
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--cutoff", default="2024-06-30 23:59:59")
    ap.add_argument("--residual-limit", type=float, default=0.005)
    ap.add_argument("--recon-tolerance", type=float, default=1e-6)
    return ap.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"empty execution log: {path}")
    return rows


def to_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")


def event_sort_key(row: dict[str, Any]) -> tuple[Any, float, pd.Timestamp, int]:
    return (row.get("scenario"), float(row.get("cost_bps", 0.0)), to_ts(row.get("ts")), int(row.get("order_index", 0)))


def group_key(row: dict[str, Any]) -> str:
    return f"{row.get('scenario')}@{float(row.get('cost_bps', 0.0)):g}"


def build_round_trips_for_group(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows = sorted(rows, key=event_sort_key)
    lots: list[dict[str, Any]] = []
    trips: list[dict[str, Any]] = []
    trip_id = 0
    gross_buy = 0.0
    gross_sell = 0.0
    total_fees = 0.0
    for row in rows:
        qty_delta = float(row.get("qty_delta", 0.0))
        gross = float(row.get("gross", 0.0))
        fee = float(row.get("fee", 0.0))
        total_fees += fee
        if qty_delta > 0:
            gross_buy += gross
            lots.append(
                {
                    "qty": qty_delta,
                    "entry_price": float(row.get("price", 0.0)),
                    "entry_ts": row.get("ts"),
                    "entry_fee_remaining": fee,
                    "entry_gross_remaining": gross,
                    "entry_regime": row.get("regime_at_execution"),
                    "entry_action": row.get("action"),
                    "symbol": row.get("symbol"),
                    "scenario": row.get("scenario"),
                    "cost_bps": row.get("cost_bps"),
                    "genome_hash": row.get("genome_hash"),
                }
            )
        elif qty_delta < 0:
            sell_qty_remaining = abs(qty_delta)
            sell_price = float(row.get("price", 0.0))
            sell_fee_remaining = fee
            gross_sell += gross
            while sell_qty_remaining > 1e-12 and lots:
                lot = lots[0]
                take = min(sell_qty_remaining, float(lot["qty"]))
                entry_qty_before = float(lot["qty"])
                entry_fee = float(lot["entry_fee_remaining"]) * (take / entry_qty_before)
                entry_gross = float(lot["entry_gross_remaining"]) * (take / entry_qty_before)
                exit_fee = sell_fee_remaining * (take / sell_qty_remaining)
                entry_px = float(lot["entry_price"])
                gross_pnl = take * (sell_price - entry_px)
                net_pnl = gross_pnl - entry_fee - exit_fee
                trip_id += 1
                entry_ts = to_ts(lot["entry_ts"])
                exit_ts = to_ts(row.get("ts"))
                trips.append(
                    {
                        "trip_id": trip_id,
                        "scenario": row.get("scenario"),
                        "cost_bps": row.get("cost_bps"),
                        "symbol": row.get("symbol") or lot.get("symbol"),
                        "side": "long_inventory",
                        "entry_ts": str(entry_ts),
                        "exit_ts": str(exit_ts),
                        "hold_time_s": max(0.0, (exit_ts - entry_ts).total_seconds()),
                        "entry_px_vwap": entry_px,
                        "exit_px_vwap": sell_price,
                        "qty": take,
                        "entry_gross": entry_gross,
                        "exit_gross": take * sell_price,
                        "gross_pnl": gross_pnl,
                        "fees": entry_fee + exit_fee,
                        "net_pnl": net_pnl,
                        "net_return_on_entry_gross": net_pnl / entry_gross if entry_gross > 0 else 0.0,
                        "regime_label_entry": lot.get("entry_regime"),
                        "regime_label_exit": row.get("regime_at_execution"),
                        "entry_action": lot.get("entry_action"),
                        "exit_action": row.get("action"),
                        "genome_hash": row.get("genome_hash") or lot.get("genome_hash"),
                        "mae_px": None,
                        "mae_pct": None,
                        "mfe_px": None,
                        "mfe_pct": None,
                        "mae_source": "unavailable_no_mark_path",
                        "stop_feasible_at": [],
                    }
                )
                lot["qty"] = entry_qty_before - take
                lot["entry_fee_remaining"] = float(lot["entry_fee_remaining"]) - entry_fee
                lot["entry_gross_remaining"] = float(lot["entry_gross_remaining"]) - entry_gross
                sell_qty_remaining -= take
                sell_fee_remaining -= exit_fee
                if lot["qty"] <= 1e-12:
                    lots.pop(0)
            if sell_qty_remaining > 1e-9:
                raise SystemExit(f"sell quantity exceeds open lots in {group_key(row)} at {row.get('ts')}")
    residuals = []
    final_price = float(rows[-1].get("price", 0.0))
    for idx, lot in enumerate(lots, 1):
        qty = float(lot["qty"])
        residuals.append(
            {
                "residual_id": idx,
                "scenario": lot.get("scenario"),
                "cost_bps": lot.get("cost_bps"),
                "symbol": lot.get("symbol"),
                "entry_ts": lot.get("entry_ts"),
                "qty": qty,
                "entry_px": lot.get("entry_price"),
                "mark_px": final_price,
                "entry_gross_remaining": lot.get("entry_gross_remaining"),
                "entry_fee_remaining": lot.get("entry_fee_remaining"),
                "mark_value": qty * final_price,
                "regime_label_entry": lot.get("entry_regime"),
                "status": "open_residual",
            }
        )
    summary = {
        "events": len(rows),
        "round_trips": len(trips),
        "residual_lots": len(residuals),
        "residual_qty": sum(float(r["qty"]) for r in residuals),
        "residual_mark_value": sum(float(r["mark_value"]) for r in residuals),
        "gross_buy": gross_buy,
        "gross_sell": gross_sell,
        "total_fees": total_fees,
        "net_pnl_closed": sum(float(t["net_pnl"]) for t in trips),
    }
    traded_notional = max(gross_buy + gross_sell, 1e-12)
    summary["residual_mark_value_share_of_turnover"] = summary["residual_mark_value"] / traded_notional
    summary["residual_inventory_ok"] = summary["residual_mark_value_share_of_turnover"] <= 0.005
    summary["hold_time_sane"] = all(float(t["hold_time_s"]) > 0.0 for t in trips)
    return trips, residuals, summary


def quantile(xs: list[float], q: float) -> float | None:
    vals = sorted(v for v in xs if math.isfinite(v))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def regime_summary(trips: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trip in trips:
        groups[str(trip.get("regime_label_entry") or "unknown")].append(trip)
    out = {}
    for regime, rows in sorted(groups.items()):
        pnls = [float(r["net_pnl"]) for r in rows]
        rets = [float(r["net_return_on_entry_gross"]) for r in rows]
        holds = [float(r["hold_time_s"]) for r in rows]
        out[regime] = {
            "round_trips": len(rows),
            "net_pnl": sum(pnls),
            "avg_net_return_on_entry_gross": sum(rets) / max(1, len(rets)),
            "p05_net_return_on_entry_gross": quantile(rets, 0.05),
            "median_hold_time_s": quantile(holds, 0.50),
            "p95_hold_time_s": quantile(holds, 0.95),
        }
    return out


def main() -> int:
    args = parse_args()
    started = time.time()
    rows = read_jsonl(Path(args.events))
    cutoff = pd.Timestamp(args.cutoff, tz="UTC")
    max_ts = max(to_ts(r.get("ts")) for r in rows)
    if max_ts > cutoff:
        raise SystemExit(f"execution log exceeds cutoff: {max_ts} > {cutoff}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[group_key(row)].append(row)
    all_trips = []
    all_residuals = []
    per_group = {}
    for key, part in sorted(grouped.items()):
        trips, residuals, summary = build_round_trips_for_group(part)
        for trip in trips:
            trip["group"] = key
        for residual in residuals:
            residual["group"] = key
        all_trips.extend(trips)
        all_residuals.extend(residuals)
        per_group[key] = summary
    failures = []
    for key, summary in per_group.items():
        if not summary["residual_inventory_ok"]:
            failures.append(f"{key}: residual_inventory_not_ok")
        if not summary["hold_time_sane"]:
            failures.append(f"{key}: hold_time_not_sane")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for trip in all_trips:
            fh.write(json.dumps(trip, sort_keys=True) + "\n")
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(time.time() - started, 3),
        "input": args.events,
        "out": args.out,
        "train_only": True,
        "cutoff": str(cutoff),
        "max_ts": str(max_ts),
        "round_trips": len(all_trips),
        "residual_lots": len(all_residuals),
        "per_group": per_group,
        "regime_summary": regime_summary(all_trips),
        "residuals": all_residuals,
        "gates": {
            "passed": not failures,
            "failures": failures,
            "residual_inventory_ok": not any("residual_inventory_not_ok" in f for f in failures),
            "hold_time_sane": not any("hold_time_not_sane" in f for f in failures),
        },
        "schema_note": "FIFO lot-level accounting over spot inventory execution events; not futures contracts.",
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(json.dumps({
        "out": args.out,
        "summary": args.summary,
        "round_trips": len(all_trips),
        "residual_lots": len(all_residuals),
        "passed": payload["gates"]["passed"],
        "failures": len(failures),
    }, indent=2, sort_keys=True))
    return 0 if payload["gates"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
