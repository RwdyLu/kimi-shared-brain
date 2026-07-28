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
        metrics_40bps={
            "rebalance_event_count": 4,
            "active_rebalance_event_count": 4,
            "time_in_market_frac": 0.10,
            "max_drawdown": 0.02,
        },
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
        metrics_40bps={
            "rebalance_event_count": 4,
            "active_rebalance_event_count": 4,
            "time_in_market_frac": 0.10,
            "max_drawdown": 0.02,
        },
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
        metrics_40bps={
            "rebalance_event_count": 10,
            "active_rebalance_event_count": 10,
            "time_in_market_frac": 0.10,
            "max_drawdown": 0.20,
        },
        min_weeks=12,
        min_rebalances=9,
        max_drawdown=0.15,
    )

    assert status == "paper_stopped_risk_review_required"
    assert checks["paper_drawdown_le_max"] is False


def test_paper_status_blocks_scheduled_only_rebalances() -> None:
    status, checks = shadow_mod.paper_status(
        evaluation_start="2026-06-01T00:00:00+00:00",
        latest_dt="2026-09-10T00:00:00+00:00",
        metrics_40bps={
            "rebalance_event_count": 10,
            "active_rebalance_event_count": 0,
            "time_in_market_frac": 0.0,
            "max_drawdown": 0.02,
        },
        min_weeks=12,
        min_rebalances=9,
        max_drawdown=0.15,
    )

    assert status == "paper_running"
    assert checks["paper_rebalances_ge_min"] is True
    assert checks["paper_active_rebalances_ge_min"] is False
    assert checks["paper_time_in_market_positive"] is False


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


def test_append_ledger_writes_hash_chain_and_verifies(tmp_path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    state = {
        "status": "paper_running",
        "source_gate": "gate.json",
        "paper_trading_authorized": True,
        "candidate": {"artifact": "candidate.json"},
        "checks": {"paper_drawdown_le_max": True},
        "shadow": {
            "latest_dt": "2026-07-10T00:00:00+00:00",
            "latest_rebalance_dt": "2026-07-10T00:00:00+00:00",
            "latest_weights": {"BTCUSDT": 0.25},
            "latest_gross_exposure": 0.25,
            "costs": {
                "40bps": {
                    "max_drawdown": 0.01,
                    "rebalance_event_count": 1,
                    "active_rebalance_event_count": 1,
                    "time_in_market_frac": 0.25,
                    "risk_off_event_count": 1,
                    "risk_stop_exit_turnover": 0.25,
                }
            },
        },
    }

    first = shadow_mod.append_ledger(state, ledger, recorded_at="2026-07-10T00:00:00+00:00")
    state["shadow"]["latest_weights"] = {"BTCUSDT": 0.50}
    second = shadow_mod.append_ledger(state, ledger, recorded_at="2026-07-10T01:00:00+00:00")
    chain = shadow_mod.verify_ledger_chain(ledger)

    assert first["seq"] == 1
    assert second["seq"] == 2
    assert second["prev_hash"] == first["hash"]
    assert chain["valid"] is True
    assert chain["row_count"] == 2
    assert chain["max_gap_sec"] == 3600.0
    assert first["metrics_40bps"]["active_rebalance_event_count"] == 1
    assert first["metrics_40bps"]["time_in_market_frac"] == 0.25
    assert first["metrics_40bps"]["risk_off_event_count"] == 1
    assert first["metrics_40bps"]["risk_stop_exit_turnover"] == 0.25


def test_skip_ledger_marker_preserves_hash_chain_but_is_not_normal_record(tmp_path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    state = {
        "status": "paper_running",
        "paper_trading_authorized": True,
        "candidate": {"artifact": "candidate.json"},
        "shadow": {
            "latest_dt": "2026-07-10T00:00:00+00:00",
            "latest_weights": {"BTCUSDT": 0.25},
            "costs": {"40bps": {"max_drawdown": 0.01}},
        },
    }
    first = shadow_mod.append_ledger(state, ledger, recorded_at="2026-07-10T00:00:00+00:00")
    skipped = shadow_mod.append_skip_ledger_marker(
        path=ledger,
        reason="SKIPPED_STALE_DATA",
        recorded_at="2026-07-10T00:30:00+00:00",
        latest_dt="2026-07-10T00:00:00+00:00",
        candidate_artifact="candidate.json",
        data_freshness={"data_fresh": False},
    )

    chain = shadow_mod.verify_ledger_chain(ledger)

    assert skipped["kind"] == "xsec_paper_ledger_skip_v1"
    assert skipped["prev_hash"] == first["hash"]
    assert shadow_mod.latest_normal_ledger_record(ledger)["hash"] == first["hash"]
    assert chain["valid"] is True


def test_latest_dt_duplicate_detects_only_normal_records(tmp_path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    shadow_mod.append_skip_ledger_marker(
        path=ledger,
        reason="SKIPPED_STALE_DATA",
        latest_dt="2026-07-10T00:00:00+00:00",
    )
    assert shadow_mod.latest_dt_is_duplicate(ledger, "2026-07-10T00:00:00+00:00") is False

    shadow_mod.append_ledger(
        {
            "status": "paper_running",
            "paper_trading_authorized": True,
            "candidate": {"artifact": "candidate.json"},
            "shadow": {
                "latest_dt": "2026-07-10T00:00:00+00:00",
                "latest_weights": {"BTCUSDT": 0.25},
                "costs": {"40bps": {"max_drawdown": 0.01}},
            },
        },
        ledger,
    )
    assert shadow_mod.latest_dt_is_duplicate(ledger, "2026-07-10T00:00:00+00:00") is True


def test_verify_ledger_chain_rejects_tampering(tmp_path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    state = {
        "status": "paper_running",
        "paper_trading_authorized": True,
        "candidate": {"artifact": "candidate.json"},
        "shadow": {
            "latest_dt": "2026-07-10T00:00:00+00:00",
            "latest_weights": {"BTCUSDT": 0.25},
            "costs": {"40bps": {"max_drawdown": 0.01}},
        },
    }
    shadow_mod.append_ledger(state, ledger, recorded_at="2026-07-10T00:00:00+00:00")
    text = ledger.read_text().replace("0.25", "0.75")
    ledger.write_text(text)

    chain = shadow_mod.verify_ledger_chain(ledger)

    assert chain["valid"] is False
    assert chain["errors"]
