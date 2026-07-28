from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import round_trip_contract_v9 as rt


def ev(idx: int, ts: str, qty_delta: float, price: float, fee: float = 0.0) -> dict:
    gross = abs(qty_delta) * price
    return {
        "scenario": 1,
        "cost_bps": 20.0,
        "order_index": idx,
        "ts": ts,
        "symbol": "LINKUSDT",
        "side": "buy" if qty_delta > 0 else "sell",
        "action": "micro_buy_float" if qty_delta > 0 else "micro_sell_float",
        "qty_delta": qty_delta,
        "price": price,
        "gross": gross,
        "fee": fee,
        "regime_at_execution": "up_normal",
        "genome_hash": "abc",
    }


def test_fifo_round_trips_and_residuals() -> None:
    rows = [
        ev(1, "2020-01-01T00:00:00+00:00", 2.0, 10.0, 0.02),
        ev(2, "2020-01-02T00:00:00+00:00", 1.0, 12.0, 0.012),
        ev(3, "2020-01-03T00:00:00+00:00", -2.5, 15.0, 0.0375),
    ]
    trips, residuals, summary = rt.build_round_trips_for_group(rows)
    assert len(trips) == 2
    assert len(residuals) == 1
    assert abs(sum(t["qty"] for t in trips) - 2.5) < 1e-12
    assert abs(residuals[0]["qty"] - 0.5) < 1e-12
    assert summary["round_trips"] == 2
    assert summary["hold_time_sane"] is True


def test_cutoff_guard(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text(json.dumps(ev(1, "2024-07-01T00:00:00+00:00", 1.0, 10.0)) + "\n")
    rows = rt.read_jsonl(p)
    assert max(rt.to_ts(r["ts"]) for r in rows) > rt.pd.Timestamp("2024-06-30 23:59:59", tz="UTC")
