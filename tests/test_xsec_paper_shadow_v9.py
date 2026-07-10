from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_paper_shadow.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_paper_shadow", SCRIPT)
assert SPEC and SPEC.loader
shadow_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow_mod)


def test_paper_status_running_before_min_duration() -> None:
    status, checks = shadow_mod.paper_status(
        evaluation_start="2026-06-01T00:00:00+00:00",
        latest_dt="2026-07-10T00:00:00+00:00",
        metrics_40bps={"rebalance_event_count": 4, "max_drawdown": 0.02},
        min_weeks=12,
        min_rebalances=9,
        max_drawdown=0.15,
    )

    assert status == "paper_running"
    assert checks["paper_live_not_authorized"] is True


def test_paper_status_handles_naive_latest_timestamp() -> None:
    status, checks = shadow_mod.paper_status(
        evaluation_start="2026-06-01T00:00:00+00:00",
        latest_dt="2026-07-10T00:00:00",
        metrics_40bps={"rebalance_event_count": 4, "max_drawdown": 0.02},
        min_weeks=12,
        min_rebalances=9,
        max_drawdown=0.15,
    )

    assert status == "paper_running"
    assert checks["paper_age_ge_min_weeks"] is False


def test_resolve_evaluation_end_now_returns_timestamp() -> None:
    resolved = shadow_mod.resolve_evaluation_end("now")

    assert "T" in resolved
    assert resolved.endswith("+00:00")


def test_paper_status_stops_on_drawdown() -> None:
    status, checks = shadow_mod.paper_status(
        evaluation_start="2026-06-01T00:00:00+00:00",
        latest_dt="2026-09-10T00:00:00+00:00",
        metrics_40bps={"rebalance_event_count": 10, "max_drawdown": 0.20},
        min_weeks=12,
        min_rebalances=9,
        max_drawdown=0.15,
    )

    assert status == "paper_stopped_risk_review_required"
    assert checks["paper_drawdown_le_max"] is False


def test_signal_rows_maps_weights_to_enter_exit() -> None:
    rows = shadow_mod.signal_rows(
        {
            "latest_dt": "2026-07-10T00:00:00+00:00",
            "latest_weights": {"BTCUSDT": 0.3, "ETHUSDT": 0.0},
        }
    )

    by_symbol = {row["symbol"]: row for row in rows}
    assert by_symbol["BTCUSDT"]["enter_long"] == 1
    assert by_symbol["BTCUSDT"]["exit_long"] == 0
    assert by_symbol["ETHUSDT"]["enter_long"] == 0
    assert by_symbol["ETHUSDT"]["exit_long"] == 1


def test_blocked_gate_state_never_authorizes_paper(tmp_path, monkeypatch) -> None:
    gate = tmp_path / "gate.json"
    gate.write_text('{"paper_trading_authorized": false}')

    state = shadow_mod.build_shadow_state(
        gate_state_path=gate,
        cache_dir=tmp_path,
        evaluation_end="2026-07-10 00:00:00",
        costs_bps=(40.0,),
    )

    assert state["status"] == "blocked"
    assert state["paper_trading_authorized"] is False
    assert state["live_trading_authorized"] is False
