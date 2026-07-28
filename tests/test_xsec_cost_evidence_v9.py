from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_cost_evidence.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_cost_evidence", SCRIPT)
assert SPEC and SPEC.loader
cost_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cost_mod)


def test_cost_rows_compute_spread_and_weight_delta() -> None:
    rows = cost_mod.cost_rows(
        state={
            "shadow": {
                "latest_dt": "2026-07-10T00:00:00+00:00",
                "latest_weights": {"BTCUSDT": 0.25},
            }
        },
        previous_weights={"BTCUSDT": 0.10},
        snapshot={"BTCUSDT": {"bid": 99.0, "ask": 101.0, "quote_volume_24h": 12345.0}},
        recorded_at="2026-07-10T00:00:01+00:00",
    )

    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["target_weight_delta"] == 0.15
    assert rows[0]["spread_bps"] == 200.0
    assert rows[0]["observed_cost_bps"] == 200.0


def test_append_rows_writes_header_once(tmp_path) -> None:
    path = tmp_path / "cost.csv"
    row = {
        "recorded_at": "2026-07-10T00:00:01+00:00",
        "latest_dt": "2026-07-10T00:00:00+00:00",
        "symbol": "BTCUSDT",
        "bid": 99.0,
        "ask": 101.0,
        "mid": 100.0,
        "spread_bps": 200.0,
        "quote_volume_24h": 12345.0,
        "target_weight": 0.25,
        "previous_weight": 0.10,
        "target_weight_delta": 0.15,
        "observed_cost_bps": 200.0,
    }

    cost_mod.append_rows(path, [row])
    cost_mod.append_rows(path, [row])

    lines = path.read_text().splitlines()
    assert lines[0].startswith("recorded_at,latest_dt,symbol")
    assert len(lines) == 3
