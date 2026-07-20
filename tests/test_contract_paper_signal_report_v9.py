from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_paper_signal_report.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_paper_signal_report", SCRIPT)
assert SPEC and SPEC.loader
report_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_mod)


def test_paper_report_calculates_open_short_r_multiple(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "open_time": [
                int(pd.Timestamp("2026-01-01T00:00:00Z").timestamp() * 1000),
                int(pd.Timestamp("2026-01-01T01:00:00Z").timestamp() * 1000),
            ],
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 98.0],
            "close": [100.0, 98.0],
            "volume": [10.0, 11.0],
        }
    ).to_parquet(tmp_path / "AAAUSDT_1h_2026-01.parquet", index=False)
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": "open",
                "symbol": "AAAUSDT",
                "side": "short",
                "entry_price": 100.0,
                "stop_loss": 102.0,
                "take_profit": 96.0,
                "analog_supported": True,
            }
        )
        + "\n"
    )
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
    )

    payload = report_mod.build_report(args)

    row = payload["open"][0]
    assert row["symbol"] == "AAAUSDT"
    assert row["current_r_multiple"] == 1.0
    assert row["current_directional_pct"] == 0.020000000000000018
    assert report_mod.outcome_label(row) == "open_profit"


def test_paper_report_surfaces_portfolio_overexposure_in_actions(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = [
        {
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "status": "open",
            "symbol": "AAAUSDT",
            "side": "long",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "analog_supported": True,
        },
        {
            "created_at": "2026-01-01T01:00:00+00:00",
            "updated_at": "2026-01-01T01:00:00+00:00",
            "status": "open",
            "symbol": "BBBUSDT",
            "side": "short",
            "entry_price": 100.0,
            "stop_loss": 102.0,
            "take_profit": 96.0,
            "analog_supported": True,
        },
    ]
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
        portfolio_max_active=1,
    )

    payload = report_mod.build_report(args)

    assert payload["portfolio_risk"]["status"] == "overexposed"
    assert payload["portfolio_risk"]["block_new_focus"] is True
    assert payload["portfolio_risk"]["active"] == 2
    assert payload["portfolio_risk"]["active_excess"] == 1
    assert "portfolio_active>1" in payload["portfolio_risk"]["reason_codes"]
    assert payload["actions"]["portfolio_risk"]["status"] == "overexposed"
    assert payload["actions"]["summary"]["portfolio_block_new_focus"] is True


def test_paper_report_surfaces_portfolio_side_risk_without_global_block(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = []
    for idx in range(20):
        rows.append(
            {
                "created_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "SHORTUSDT",
                "side": "short",
                "analog_supported": True,
                "outcome": {"r_multiple": -1.0, "exit_dt": f"2026-01-01T{idx:02d}:30:00+00:00"},
            }
        )
        rows.append(
            {
                "created_at": f"2026-01-02T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-02T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "LONGUSDT",
                "side": "long",
                "analog_supported": True,
                "outcome": {"r_multiple": 0.5, "exit_dt": f"2026-01-02T{idx:02d}:30:00+00:00"},
            }
        )
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["portfolio_risk"]["status"] == "normal"
    assert payload["portfolio_risk"]["block_new_focus"] is False
    assert payload["portfolio_risk"]["blocked_sides"] == ["short"]
    assert payload["portfolio_segment_risk"]["blocked_sides"] == ["short"]
    short = payload["portfolio_segment_risk"]["segments"]["short"]
    long = payload["portfolio_segment_risk"]["segments"]["long"]
    assert short["status"] == "blocked"
    assert long["status"] == "normal"
    assert "portfolio_side_recent_sum_R<=-20.00" in short["reason_codes"]
    assert "portfolio_side_loss_rate>=0.70" in short["reason_codes"]
    assert payload["actions"]["portfolio_risk"]["blocked_sides"] == ["short"]
    assert payload["actions"]["summary"]["portfolio_blocked_sides"] == ["short"]


def test_paper_report_builds_strategy_scoreboard(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "open_time": [
                int(pd.Timestamp("2026-01-03T00:00:00Z").timestamp() * 1000),
                int(pd.Timestamp("2026-01-03T01:00:00Z").timestamp() * 1000),
            ],
            "open": [100.0, 104.0],
            "high": [105.0, 106.0],
            "low": [99.0, 103.0],
            "close": [104.0, 105.0],
            "volume": [10.0, 11.0],
        }
    ).to_parquet(tmp_path / "AAAUSDT_1h_2026-01.parquet", index=False)
    journal = tmp_path / "journal.jsonl"
    rows = []
    for idx in range(20):
        rows.append(
            {
                "created_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "AAAUSDT",
                "side": "long",
                "analog_supported": idx < 10,
                "outcome": {"r_multiple": 0.3, "exit_dt": f"2026-01-01T{idx:02d}:30:00+00:00"},
            }
        )
        rows.append(
            {
                "created_at": f"2026-01-02T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-02T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "BBBUSDT",
                "side": "short",
                "analog_supported": idx < 4,
                "outcome": {"r_multiple": -0.3, "exit_dt": f"2026-01-02T{idx:02d}:30:00+00:00"},
            }
        )
    rows.append(
        {
            "created_at": "2026-01-03T00:00:00+00:00",
            "updated_at": "2026-01-03T01:00:00+00:00",
            "status": "open",
            "symbol": "AAAUSDT",
            "side": "long",
            "entry_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
            "analog_supported": True,
        }
    )
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
        scoreboard_max_rows=20,
        scoreboard_min_trades=20,
        scoreboard_recent_trades=20,
        scoreboard_fail_sum_r=-5.0,
        scoreboard_fail_profit_factor=0.8,
        scoreboard_fail_consecutive_losses=6,
        scoreboard_promote_sum_r=5.0,
        scoreboard_promote_profit_factor=1.2,
        scoreboard_promote_max_drawdown_r=5.0,
        actions_max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["scoreboard_groups"] == 2
    assert payload["summary"]["promote_candidates"] == 1
    assert payload["summary"]["stop_candidates"] == 1
    assert payload["scoreboard"][0]["symbol"] == "AAAUSDT"
    assert payload["scoreboard"][0]["status"] == "promote_candidate"
    assert abs(payload["scoreboard"][0]["recent_sum_r"] - 6.0) < 1e-9
    assert payload["scoreboard"][0]["recent_analog_supported"] == 10
    assert payload["scoreboard"][0]["recent_analog_supported_rate"] == 0.5
    assert payload["scoreboard"][0]["active"] == 1
    assert payload["scoreboard"][0]["active_r_known"] == 1
    assert payload["scoreboard"][0]["active_profit"] == 1
    assert payload["scoreboard"][0]["active_loss"] == 0
    assert abs(payload["scoreboard"][0]["active_sum_r"] - 0.5) < 1e-9
    assert payload["actions"]["promote_candidates"][0]["active_sum_r"] == payload["scoreboard"][0]["active_sum_r"]
    stop = next(row for row in payload["scoreboard"] if row["symbol"] == "BBBUSDT")
    assert stop["status"] == "stop_candidate"
    assert stop["recent_analog_supported"] == 4
    assert stop["recent_analog_supported_rate"] == 0.2
    assert "recent_sum_r<=-5" in stop["reason_codes"]
    assert payload["actions"]["summary"]["blocked_pairs"] == 1
    assert payload["actions"]["blocked_pairs"][0]["timeframe"] == "1h"
    assert payload["actions"]["blocked_pairs"][0]["symbol"] == "BBBUSDT"
    assert payload["actions"]["blocked_pairs"][0]["side"] == "short"
    assert payload["actions"]["summary"]["fresh_analog_veto_pairs"] == 1
    assert payload["actions"]["fresh_analog_veto_pairs"][0]["symbol"] == "BBBUSDT"
    assert "fresh_veto_recent_sum_r<=-2" in payload["actions"]["fresh_analog_veto_pairs"][0]["fresh_veto_reason_codes"]


def test_paper_report_fresh_veto_blocks_short_negative_evidence_before_stop_candidate(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = []
    for idx, value in enumerate([-1.1, -1.2, -1.3]):
        rows.append(
            {
                "created_at": f"2026-01-01T0{idx}:00:00+00:00",
                "updated_at": f"2026-01-01T0{idx}:00:00+00:00",
                "status": "completed",
                "symbol": "DOGEUSDT",
                "side": "long",
                "analog_supported": False,
                "outcome": {"r_multiple": value, "exit_dt": f"2026-01-01T0{idx}:30:00+00:00"},
            }
        )
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"15m:{journal}",
        lookback_bars=20,
        max_rows=20,
        scoreboard_max_rows=20,
        scoreboard_min_trades=20,
        scoreboard_recent_trades=50,
        scoreboard_fail_sum_r=-5.0,
        scoreboard_fail_profit_factor=0.8,
        scoreboard_fail_consecutive_losses=6,
        scoreboard_promote_sum_r=5.0,
        scoreboard_promote_profit_factor=1.2,
        scoreboard_promote_max_drawdown_r=5.0,
        fresh_veto_min_trades=3,
        fresh_veto_sum_r=-2.0,
        fresh_veto_profit_factor=0.5,
        fresh_veto_trailing_losses=3,
        actions_max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["stop_candidates"] == 0
    assert payload["actions"]["summary"]["fresh_analog_veto_pairs"] == 1
    row = payload["actions"]["fresh_analog_veto_pairs"][0]
    assert row["timeframe"] == "15m"
    assert row["symbol"] == "DOGEUSDT"
    assert row["side"] == "long"
    assert "fresh_veto_recent_trailing_losses>=3" in row["fresh_veto_reason_codes"]


def test_paper_report_builds_regime_scoreboard(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = []
    for idx, value in enumerate([0.8, 0.7, -0.2, 0.5]):
        rows.append(
            {
                "created_at": f"2026-01-01T0{idx}:00:00+00:00",
                "updated_at": f"2026-01-01T0{idx}:00:00+00:00",
                "status": "completed",
                "symbol": "AAAUSDT",
                "side": "long",
                "market_regime_id": "uptrend_normal_vol",
                "outcome": {"r_multiple": value, "exit_dt": f"2026-01-01T0{idx}:30:00+00:00"},
            }
        )
    for idx, value in enumerate([-1.0, -0.6]):
        rows.append(
            {
                "created_at": f"2026-01-02T0{idx}:00:00+00:00",
                "updated_at": f"2026-01-02T0{idx}:00:00+00:00",
                "status": "completed",
                "symbol": "BBBUSDT",
                "side": "long",
                "market_regime_id": "downtrend_normal_vol",
                "outcome": {"r_multiple": value, "exit_dt": f"2026-01-02T0{idx}:30:00+00:00"},
            }
        )
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
        scoreboard_max_rows=20,
        scoreboard_recent_trades=50,
        actions_max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["regime_scoreboard_groups"] == 2
    assert payload["regime_scoreboard"][0]["market_regime_id"] == "uptrend_normal_vol"
    assert abs(payload["regime_scoreboard"][0]["recent_sum_r"] - 1.8) < 1e-9
