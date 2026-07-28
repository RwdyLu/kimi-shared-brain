from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_execution_log_v9 as analyzer


def event(ts: str, idx: int, cash_after: float, cash_delta: float, qty: float, price: float, regime: str) -> dict:
    gross = abs(cash_delta) / 1.002
    fee = gross * 20.0 / 10000.0
    return {
        "scenario": 1,
        "cost_bps": 20.0,
        "order_index": idx,
        "ts": ts,
        "action": "micro_buy_float" if cash_delta < 0 else "micro_sell_float",
        "side": "buy" if cash_delta < 0 else "sell",
        "cash_after": cash_after,
        "cash_delta": cash_delta,
        "dead_qty_after": 0.0,
        "float_qty_after": qty,
        "price": price,
        "equity_after": cash_after + qty * price,
        "gross": gross,
        "fee": fee,
        "realized_pnl": 0.0,
        "route_multiplier": 0.5,
        "policy_multiplier": 0.7,
        "regime_at_execution": regime,
    }


def test_execution_log_analyzer_integrity_passes(tmp_path: Path) -> None:
    rows = [
        event("2020-01-01T00:00:00+00:00", 1, 9900.0, -100.0, 1.0, 100.0, "up_normal"),
        event("2020-01-02T00:00:00+00:00", 2, 9800.0, -100.0, 2.0, 105.0, "down_normal"),
    ]
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    loaded = analyzer.read_jsonl(p)
    report = analyzer.analyze_group(loaded, analyzer.parse_args_from_list(["--input", str(p)]))
    assert report["integrity"]["monotonic_ts"] is True
    assert report["coverage"]["secondary_regime_events_ok"] is False


def test_execution_log_analyzer_cutoff_gate(tmp_path: Path) -> None:
    p = tmp_path / "events.jsonl"
    p.write_text(json.dumps(event("2024-07-01T00:00:00+00:00", 1, 9900.0, -100.0, 1.0, 100.0, "up_normal")) + "\n")
    rows = analyzer.read_jsonl(p)
    ts = [analyzer.to_ts(r["ts"]) for r in rows]
    assert max(ts) > analyzer.pd.Timestamp("2024-06-30 23:59:59", tz="UTC")
