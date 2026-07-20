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


def test_paper_report_separates_current_policy_portfolio_risk(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = [
        {
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "status": "open",
            "symbol": "OLD1USDT",
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
            "symbol": "OLD2USDT",
            "side": "short",
            "entry_price": 100.0,
            "stop_loss": 102.0,
            "take_profit": 96.0,
            "analog_supported": True,
        },
        {
            "created_at": "2026-01-01T02:00:00+00:00",
            "updated_at": "2026-01-01T02:00:00+00:00",
            "status": "open",
            "symbol": "NEWUSDT",
            "side": "long",
            "decision_policy_version": "policy_v2",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
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
        current_decision_policy_version="policy_v2",
    )

    payload = report_mod.build_report(args)

    assert payload["portfolio_risk"]["scope"] == "global"
    assert payload["portfolio_risk"]["status"] == "overexposed"
    assert payload["portfolio_risk"]["active"] == 3
    assert payload["current_policy_portfolio_risk"]["scope"] == "current_policy"
    assert payload["current_policy_portfolio_risk"]["decision_policy_version"] == "policy_v2"
    assert payload["current_policy_portfolio_risk"]["status"] == "normal"
    assert payload["current_policy_portfolio_risk"]["active"] == 1
    assert payload["actions"]["portfolio_risk"]["status"] == "overexposed"
    assert payload["actions"]["current_policy_portfolio_risk"]["status"] == "normal"
    assert payload["actions"]["summary"]["portfolio_block_new_focus"] is True
    assert payload["actions"]["summary"]["current_policy_portfolio_block_new_focus"] is False
    assert payload["summary"]["current_policy_portfolio_risk_status"] == "normal"


def test_paper_report_projects_active_drain_eta() -> None:
    args = Namespace(portfolio_max_active=2)
    rows = [
        {
            "timeframe": "1h",
            "status": "open",
            "symbol": "AAAUSDT",
            "side": "long",
            "latest_dt": "2026-01-02T00:00:00+00:00",
            "entry_dt": "2026-01-01T00:00:00+00:00",
            "outcome_horizon_bars": 24,
            "paper_execution": {"stale_grace_bars": 4},
        },
        {
            "timeframe": "1h",
            "status": "open",
            "symbol": "BBBUSDT",
            "side": "long",
            "latest_dt": "2026-01-02T00:00:00+00:00",
            "entry_dt": "2026-01-01T12:00:00+00:00",
            "outcome_horizon_bars": 24,
            "paper_execution": {"stale_grace_bars": 4},
        },
        {
            "timeframe": "1h",
            "status": "open",
            "symbol": "CCCUSDT",
            "side": "short",
            "latest_dt": "2026-01-02T00:00:00+00:00",
            "entry_dt": "2026-01-01T20:00:00+00:00",
            "outcome_horizon_bars": 24,
            "paper_execution": {"stale_grace_bars": 4},
        },
        {
            "timeframe": "15m",
            "status": "open",
            "symbol": "DDDUSDT",
            "side": "short",
            "latest_dt": "2026-01-02T00:00:00+00:00",
            "entry_dt": "2026-01-01T19:00:00+00:00",
            "outcome_horizon_bars": 96,
            "paper_execution": {"stale_grace_bars": 4},
        },
    ]

    drain = report_mod.build_portfolio_drain(rows, args)

    assert drain["active"] == 4
    assert drain["active_excess"] == 2
    assert drain["remaining_hours_to_horizon_min"] == 0.0
    assert drain["eta_to_active_cap_hours_upper_bound"] == 12.0
    assert drain["remaining_hours_to_horizon_max"] == 20.0
    assert drain["past_stale_after"] == 0
    assert drain["by_timeframe"]["1h"]["active"] == 3
    assert drain["by_timeframe"]["15m"]["active"] == 1


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


def test_paper_report_builds_decision_policy_scoreboard(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = []
    for idx in range(5):
        rows.append(
            {
                "created_at": f"2026-01-01T0{idx}:00:00+00:00",
                "updated_at": f"2026-01-01T0{idx}:00:00+00:00",
                "status": "completed",
                "symbol": "NEWUSDT",
                "side": "long",
                "decision_policy_version": "policy_v2",
                "analog_supported": True,
                "outcome": {"r_multiple": 0.5, "exit_dt": f"2026-01-01T0{idx}:30:00+00:00"},
            }
        )
        rows.append(
            {
                "created_at": f"2026-01-02T0{idx}:00:00+00:00",
                "updated_at": f"2026-01-02T0{idx}:00:00+00:00",
                "status": "completed",
                "symbol": "OLDUSDT",
                "side": "long",
                "analog_supported": True,
                "outcome": {"r_multiple": -0.5, "exit_dt": f"2026-01-02T0{idx}:30:00+00:00"},
            }
        )
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
        scoreboard_max_rows=20,
        scoreboard_min_trades=5,
        scoreboard_recent_trades=50,
        scoreboard_fail_sum_r=-2.0,
        scoreboard_fail_profit_factor=0.8,
        scoreboard_fail_consecutive_losses=6,
        scoreboard_promote_sum_r=2.0,
        scoreboard_promote_profit_factor=1.2,
        scoreboard_promote_max_drawdown_r=1.0,
        current_decision_policy_version="policy_v2",
        actions_max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["policy_scoreboard_groups"] == 2
    assert payload["summary"]["current_decision_policy_version"] == "policy_v2"
    assert payload["summary"]["current_policy_records"] == 5
    assert payload["summary"]["current_policy_completed"] == 5
    assert payload["summary"]["current_policy_active"] == 0
    assert payload["summary"]["current_policy_scoreboard_groups"] == 1
    by_policy = {row["decision_policy_version"]: row for row in payload["policy_scoreboard"]}
    assert by_policy["policy_v2"]["recent_sum_r"] == 2.5
    assert by_policy["policy_v2"]["recent_completed"] == 5
    assert by_policy["legacy_unknown"]["recent_sum_r"] == -2.5
    assert payload["current_policy_scoreboard"][0]["symbol"] == "NEWUSDT"
    assert payload["current_policy_scoreboard"][0]["status"] == "promote_candidate"
    assert payload["actions"]["current_policy_summary"]["promote_candidates"] == 1
    assert payload["actions"]["current_policy_promote_candidates"][0]["symbol"] == "NEWUSDT"
    assert all(row.get("symbol") != "OLDUSDT" for row in payload["actions"]["current_policy_promote_candidates"])
    assert payload["records"][0]["decision_policy_version"] == "legacy_unknown"


def test_paper_report_keeps_shadow_records_out_of_portfolio_risk(tmp_path: Path) -> None:
    main_journal = tmp_path / "main.jsonl"
    shadow_journal = tmp_path / "shadow.jsonl"
    pd.DataFrame(
        {
            "open_time": [
                int(pd.Timestamp("2026-01-03T00:00:00Z").timestamp() * 1000),
                int(pd.Timestamp("2026-01-03T01:00:00Z").timestamp() * 1000),
            ],
            "open": [100.0, 100.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [10.0, 11.0],
        }
    ).to_parquet(tmp_path / "OPENUSDT_1h_2026-01.parquet", index=False)
    main_journal.write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": "open",
                "symbol": "LIVEUSDT",
                "side": "long",
                "entry_price": 100.0,
                "stop_loss": 98.0,
                "take_profit": 104.0,
                "analog_supported": True,
            }
        )
        + "\n"
    )
    shadow_rows = []
    for idx in range(5):
        shadow_rows.append(
            {
                "created_at": f"2026-01-02T0{idx}:00:00+00:00",
                "updated_at": f"2026-01-02T0{idx}:00:00+00:00",
                "status": "completed",
                "symbol": "SHADOWUSDT",
                "side": "long",
                "decision_policy_version": "policy_v2",
                "shadow_journal": True,
                "shadow_reason": "portfolio_risk_block",
                "analog_supported": True,
                "outcome": {"r_multiple": 0.5, "exit_dt": f"2026-01-02T0{idx}:30:00+00:00"},
            }
        )
    shadow_rows.append(
        {
            "created_at": "2026-01-03T00:00:00+00:00",
            "updated_at": "2026-01-03T00:00:00+00:00",
            "status": "open",
            "symbol": "OPENUSDT",
            "side": "long",
            "decision_policy_version": "policy_v2",
            "shadow_journal": True,
            "shadow_reason": "portfolio_risk_block",
            "analog_supported": False,
            "analog_expectancy_r": 0.25,
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
        }
    )
    shadow_journal.write_text("\n".join(json.dumps(row) for row in shadow_rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{main_journal}",
        shadow_sources=f"1h:{shadow_journal}",
        lookback_bars=20,
        max_rows=20,
        scoreboard_max_rows=20,
        scoreboard_min_trades=5,
        scoreboard_recent_trades=50,
        scoreboard_fail_sum_r=-2.0,
        scoreboard_fail_profit_factor=0.8,
        scoreboard_fail_consecutive_losses=6,
        scoreboard_promote_sum_r=2.0,
        scoreboard_promote_profit_factor=1.2,
        scoreboard_promote_max_drawdown_r=1.0,
        current_decision_policy_version="policy_v2",
        actions_max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["active"] == 1
    assert payload["summary"]["records"] == 1
    assert payload["summary"]["shadow_records"] == 6
    assert payload["summary"]["shadow_completed"] == 5
    assert payload["summary"]["shadow_active"] == 1
    assert payload["summary"]["shadow_active_r_known"] == 1
    assert payload["summary"]["shadow_active_profit"] == 1
    assert abs(payload["summary"]["shadow_active_sum_r"] - 0.5) < 1e-9
    assert payload["summary"]["current_policy_records"] == 0
    assert payload["summary"]["current_policy_shadow_records"] == 6
    assert payload["summary"]["current_policy_shadow_active"] == 1
    assert payload["summary"]["current_policy_shadow_active_r_known"] == 1
    assert abs(payload["summary"]["current_policy_shadow_active_sum_r"] - 0.5) < 1e-9
    assert payload["summary"]["current_policy_shadow_active_promising"] == 1
    assert payload["summary"]["current_policy_shadow_active_positive"] == 0
    assert payload["summary"]["current_policy_shadow_active_risk"] == 0
    assert payload["summary"]["current_policy_shadow_readiness_status"] == "promote_ready"
    assert payload["summary"]["current_policy_shadow_readiness_severity"] == "ready"
    assert payload["summary"]["current_policy_shadow_scoreboard_groups"] == 1
    assert payload["summary"]["current_policy_shadow_promote_candidates"] == 1
    assert payload["current_policy_shadow_scoreboard"][0]["symbol"] == "SHADOWUSDT"
    assert payload["actions"]["current_policy_summary"]["promote_candidates"] == 0
    assert payload["actions"]["current_policy_shadow_summary"]["promote_candidates"] == 1
    assert payload["actions"]["current_policy_shadow_summary"]["active_watchlist"] == 1
    assert payload["actions"]["current_policy_shadow_summary"]["active_grade_counts"]["promising_active"] == 1
    assert payload["actions"]["current_policy_shadow_readiness"]["status"] == "promote_ready"
    assert payload["actions"]["current_policy_shadow_readiness"]["next_action"] == "manual_review_before_paper_canary"
    assert payload["actions"]["current_policy_shadow_promote_candidates"][0]["symbol"] == "SHADOWUSDT"
    assert payload["actions"]["current_policy_shadow_active_watchlist"][0]["symbol"] == "OPENUSDT"
    assert payload["actions"]["current_policy_shadow_active_watchlist"][0]["current_r_multiple"] == 0.5
    assert payload["actions"]["current_policy_shadow_active_queue"][0]["symbol"] == "OPENUSDT"
    assert payload["actions"]["current_policy_shadow_active_queue"][0]["active_grade"] == "promising_active"
    assert (
        payload["actions"]["current_policy_shadow_active_queue"][0]["next_action"]
        == "await_completion_for_scoreboard"
    )
    assert payload["current_policy_shadow_active_watchlist"][0]["symbol"] == "OPENUSDT"
    assert payload["current_policy_shadow_active_queue"][0]["symbol"] == "OPENUSDT"
    assert payload["actions"]["current_policy_promote_candidates"] == []


def test_paper_report_writes_current_policy_shadow_promote_marker(tmp_path: Path) -> None:
    payload = {
        "updated_at": "2026-01-04T00:00:00+00:00",
        "summary": {
            "current_decision_policy_version": "policy_v2",
            "current_policy_shadow_completed": 20,
            "current_policy_shadow_active": 2,
            "current_policy_shadow_scoreboard_groups": 1,
        },
        "actions": {
            "current_policy_shadow_promote_candidates": [
                {
                    "timeframe": "1h",
                    "symbol": "SHADOWUSDT",
                    "side": "long",
                    "recent_completed": 20,
                    "recent_sum_r": 6.25,
                    "recent_profit_factor": 1.45,
                    "recent_max_drawdown_r": 2.0,
                    "recent_win_rate": 0.6,
                    "active": 1,
                    "active_sum_r": 0.75,
                    "latest_completed_at": "2026-01-04T00:00:00+00:00",
                }
            ]
        },
    }
    found_marker = tmp_path / "FOUND_CURRENT_POLICY_SHADOW_PROMOTE.txt"
    no_marker = tmp_path / "NO_CURRENT_POLICY_SHADOW_PROMOTE.txt"

    report_mod.write_current_policy_shadow_promote_marker(
        payload,
        found_marker,
        no_marker,
        report_json="report.json",
        actions_json="actions.json",
    )

    text = found_marker.read_text()
    assert text.startswith("FOUND_CURRENT_POLICY_SHADOW_PROMOTE ")
    assert "policy=policy_v2" in text
    assert "symbol=SHADOWUSDT" in text
    assert "recent_sum_R=6.250" in text
    assert "paper_trading_authorized=False" in text
    assert "live_trading_authorized=False" in text
    assert not no_marker.exists()

    payload["actions"]["current_policy_shadow_promote_candidates"] = []
    report_mod.write_current_policy_shadow_promote_marker(payload, found_marker, no_marker)

    assert not found_marker.exists()
    no_text = no_marker.read_text()
    assert no_text.startswith("NO_CURRENT_POLICY_SHADOW_PROMOTE ")
    assert "completed=20" in no_text
    assert "paper_trading_authorized=False" in no_text


def test_paper_report_grades_current_policy_shadow_active_queue() -> None:
    args = Namespace(
        shadow_active_promising_r=0.5,
        shadow_active_risk_r=-0.5,
        shadow_active_min_promising_expectancy_r=0.15,
    )
    rows = [
        {
            "status": "open",
            "symbol": "RISKUSDT",
            "side": "long",
            "timeframe": "15m",
            "current_r_multiple": -0.75,
            "analog_expectancy_r": 0.4,
        },
        {
            "status": "pending_entry",
            "symbol": "PENDINGUSDT",
            "side": "long",
            "timeframe": "1h",
            "analog_expectancy_r": 0.3,
        },
        {
            "status": "open",
            "symbol": "GOODUSDT",
            "side": "long",
            "timeframe": "1h",
            "current_r_multiple": 0.6,
            "analog_expectancy_r": 0.25,
        },
    ]

    queue = report_mod.active_shadow_queue(rows, args, 10)
    by_symbol = {row["symbol"]: row for row in queue}

    assert queue[0]["symbol"] == "GOODUSDT"
    assert by_symbol["GOODUSDT"]["active_grade"] == "promising_active"
    assert by_symbol["PENDINGUSDT"]["active_grade"] == "wait_entry"
    assert by_symbol["RISKUSDT"]["active_grade"] == "risk_active"
    counts = report_mod.active_shadow_grade_counts(queue)
    assert counts["promising_active"] == 1
    assert counts["wait_entry"] == 1
    assert counts["risk_active"] == 1


def test_paper_report_writes_current_policy_shadow_readiness_marker(tmp_path: Path) -> None:
    payload = {
        "updated_at": "2026-01-04T00:00:00+00:00",
        "summary": {
            "current_decision_policy_version": "policy_v2",
            "current_policy_shadow_records": 3,
            "current_policy_shadow_completed": 0,
            "current_policy_shadow_active": 3,
            "current_policy_shadow_scoreboard_groups": 0,
        },
        "actions": {
            "current_policy_shadow_promote_candidates": [],
            "current_policy_shadow_active_grade_counts": {
                "promising_active": 0,
                "positive_active": 1,
                "wait_entry": 1,
                "negative_active": 1,
                "risk_active": 0,
            },
            "current_policy_shadow_active_queue": [
                {
                    "timeframe": "1h",
                    "symbol": "GOODUSDT",
                    "side": "long",
                    "status": "open",
                    "active_grade": "positive_active",
                    "current_r_multiple": 0.25,
                    "analog_expectancy_r": 0.3,
                    "next_action": "await_completion",
                }
            ],
        },
    }
    report_mod.attach_current_policy_shadow_readiness(payload)
    marker = tmp_path / "CURRENT_POLICY_SHADOW_READINESS.txt"

    report_mod.write_current_policy_shadow_readiness_marker(payload, marker)

    text = marker.read_text()
    assert text.startswith("CURRENT_POLICY_SHADOW_READINESS ")
    assert "status=active_positive" in text
    assert "severity=watch" in text
    assert "next_action=await_completion" in text
    assert "grades=0/1/1/1/0" in text
    assert "top=1h:GOODUSDT:long:positive_active:R=0.250" in text
    assert "paper_trading_authorized=False" in text
    assert "live_trading_authorized=False" in text


def test_paper_report_summarizes_fast_shadow_as_retest_not_promotion(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    shadow = tmp_path / "shadow.jsonl"
    fast_shadow = tmp_path / "fast_shadow.jsonl"
    journal.write_text("")
    shadow.write_text("")
    rows = []
    for idx in range(20):
        rows.append(
            {
                "kind": "contract_latest_market_signal_fast_shadow_journal_v1",
                "fast_shadow_journal": True,
                "shadow_fast_probe": True,
                "promotion_eligible": False,
                "created_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "FASTUSDT",
                "side": "long",
                "timeframe": "1h",
                "decision_policy_version": report_mod.DECISION_POLICY_VERSION,
                "analog_supported": True,
                "outcome_horizon_bars": 3,
                "outcome": {
                    "r_multiple": 0.4,
                    "exit_dt": f"2026-01-01T{idx:02d}:30:00+00:00",
                },
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
        )
    fast_shadow.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        shadow_sources=f"1h:{shadow}",
        fast_shadow_sources=f"1h:{fast_shadow}",
        lookback_bars=20,
        max_rows=20,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["fast_shadow_records"] == 20
    assert payload["summary"]["fast_shadow_completed"] == 20
    assert payload["summary"]["current_policy_fast_shadow_records"] == 20
    assert payload["summary"]["current_policy_fast_shadow_completed"] == 20
    assert payload["summary"]["current_policy_fast_shadow_retest_candidates"] == 1
    assert payload["summary"]["current_policy_fast_shadow_retest_status"] == "retest_ready"
    assert payload["summary"]["current_policy_fast_shadow_retest_next_action"] == "run_full_horizon_shadow_retest"
    assert payload["summary"]["current_policy_shadow_promote_candidates"] == 0
    assert payload["actions"]["current_policy_fast_shadow_retest"]["status"] == "retest_ready"
    assert len(payload["actions"]["current_policy_fast_shadow_retest_candidates"]) == 1
    assert payload["current_policy_fast_shadow_scoreboard"][0]["status"] == "promote_candidate"
    assert payload["current_policy_fast_shadow_scoreboard"][0]["symbol"] == "FASTUSDT"
    assert "current_policy_fast_shadow_promote_candidates" not in payload["actions"]


def test_paper_report_writes_fast_shadow_retest_marker(tmp_path: Path) -> None:
    payload = {
        "updated_at": "2026-01-04T00:00:00+00:00",
        "summary": {
            "current_decision_policy_version": "policy_v2",
            "current_policy_fast_shadow_records": 20,
            "current_policy_fast_shadow_completed": 20,
            "current_policy_fast_shadow_active": 0,
            "current_policy_fast_shadow_scoreboard_groups": 1,
        },
        "actions": {},
        "current_policy_fast_shadow_scoreboard": [
            {
                "status": "promote_candidate",
                "timeframe": "1h",
                "symbol": "FASTUSDT",
                "side": "long",
                "recent_completed": 20,
                "recent_sum_r": 6.0,
                "recent_profit_factor": 2.0,
                "recent_max_drawdown_r": 2.0,
                "edge_score": 4.0,
            }
        ],
    }
    report_mod.attach_current_policy_fast_shadow_retest(payload)
    found_marker = tmp_path / "FOUND_CURRENT_POLICY_FAST_SHADOW_RETEST.txt"
    no_marker = tmp_path / "NO_CURRENT_POLICY_FAST_SHADOW_RETEST.txt"

    report_mod.write_current_policy_fast_shadow_retest_marker(
        payload,
        found_marker,
        no_marker,
        report_json="report.json",
        actions_json="actions.json",
    )

    text = found_marker.read_text()
    assert text.startswith("FOUND_CURRENT_POLICY_FAST_SHADOW_RETEST ")
    assert "status=retest_ready" in text
    assert "next_action=run_full_horizon_shadow_retest" in text
    assert "symbol=FASTUSDT" in text
    assert "note=fast_shadow_only_full_horizon_retest_required" in text
    assert "paper_trading_authorized=False" in text
    assert "live_trading_authorized=False" in text
    assert not no_marker.exists()

    payload["current_policy_fast_shadow_scoreboard"] = []
    report_mod.attach_current_policy_fast_shadow_retest(payload)
    report_mod.write_current_policy_fast_shadow_retest_marker(payload, found_marker, no_marker)

    assert not found_marker.exists()
    no_text = no_marker.read_text()
    assert no_text.startswith("NO_CURRENT_POLICY_FAST_SHADOW_RETEST ")
    assert "status=completed_no_retest" in no_text
    assert "paper_trading_authorized=False" in no_text


def test_paper_report_shadow_readiness_risk_takes_priority() -> None:
    payload = {
        "updated_at": "2026-01-04T00:00:00+00:00",
        "summary": {
            "current_decision_policy_version": "policy_v2",
            "current_policy_shadow_records": 2,
            "current_policy_shadow_completed": 0,
            "current_policy_shadow_active": 2,
            "current_policy_shadow_scoreboard_groups": 0,
        },
        "actions": {
            "current_policy_shadow_promote_candidates": [],
            "current_policy_shadow_active_grade_counts": {
                "promising_active": 1,
                "positive_active": 0,
                "wait_entry": 0,
                "negative_active": 0,
                "risk_active": 1,
            },
            "current_policy_shadow_active_queue": [],
        },
    }

    readiness = report_mod.build_current_policy_shadow_readiness(payload)

    assert readiness["status"] == "risk_watch"
    assert readiness["severity"] == "risk"
    assert readiness["next_action"] == "do_not_promote_wait_for_exit"


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
