from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_latest_market_signal.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_latest_market_signal", SCRIPT)
assert SPEC and SPEC.loader
signal_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signal_mod)


def write_symbol_cache(cache_dir: Path, symbol: str, closes: list[float]) -> None:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    previous = closes[0]
    for idx, close in enumerate(closes):
        open_price = previous if idx else close
        rows.append(
            {
                "open_time": int((start + pd.Timedelta(hours=idx)).timestamp() * 1000),
                "open": open_price,
                "high": max(open_price, close) * 1.001,
                "low": min(open_price, close) * 0.999,
                "close": close,
                "volume": 1000.0 + idx,
            }
        )
        previous = close
    frame = pd.DataFrame(rows)
    frame.to_parquet(cache_dir / f"{symbol}_1h_2026-01.parquet", index=False)


def base_args(tmp_path: Path, *, symbols: str) -> Namespace:
    return Namespace(
        cache_dir=str(tmp_path),
        timeframe="1h",
        universe_json="",
        top_n=20,
        symbols=symbols,
        lookback_bars=240,
        fast_ema=24,
        slow_ema=96,
        slope_n=12,
        breakout_n=24,
        breakout_buffer=0.002,
        atr_n=14,
        rsi_n=14,
        min_votes=5,
        min_slope=0.001,
        min_ret_24h=0.003,
        max_long_rsi=75.0,
        min_short_rsi=25.0,
        stop_atr_mult=2.0,
        min_stop_pct=0.01,
        reward_r=2.0,
        risk_per_trade=0.005,
        leverage_cap=2.0,
        analog_top_k=20,
        analog_horizon_bars=12,
        min_analog_samples=6,
        min_analog_hit_rate=0.40,
        min_analog_profitable_rate=0.55,
        min_analog_expectancy_r=0.0,
        paper_outcome_horizon_bars=12,
        paper_fee_bps=5.0,
        paper_slippage_bps=2.0,
        paper_entry_latency_bars=1,
        paper_max_entry_drift_bps=80.0,
        paper_funding_bps_per_8h=1.0,
        paper_partial_fill_frac=1.0,
        paper_min_fill_frac=1.0,
        paper_stale_grace_bars=4,
        regime_filter_mode="block_conflict",
        regime_symbols="BTCUSDT,ETHUSDT",
        regime_min_direction_votes=2,
        regime_vol_lookback_bars=1000,
        regime_high_vol_percentile=0.85,
        regime_block_high_vol=False,
        paper_migrate_legacy_records="all",
        journal_jsonl=str(tmp_path / "journal.jsonl"),
        journal_allowed_pairs="",
        journal_max_active_per_pair=0,
        journal_max_active_total=0,
        journal_record_mode="all_signals",
        max_journal_records=1000,
        out_json=str(tmp_path / "signal.json"),
        out_md=str(tmp_path / "signal.md"),
        marker=str(tmp_path / "FOUND.txt"),
        no_marker=str(tmp_path / "NO.txt"),
        analog_marker=str(tmp_path / "FOUND_ANALOG.txt"),
        analog_no_marker=str(tmp_path / "NO_ANALOG.txt"),
        format="text",
    )


def test_latest_market_signal_builds_long_paper_plan(tmp_path: Path) -> None:
    closes = [100.0 * (1.0015**idx) for idx in range(180)]
    write_symbol_cache(tmp_path, "AAAUSDT", closes)

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="AAAUSDT"))

    best = payload["top"][0]
    plan = best["paper_plan"]
    assert payload["summary"]["paper_plan_found"] is True
    assert payload["summary"]["analog_supported_plan_found"] is True
    assert payload["journal"]["new_records"] == 1
    assert payload["summary"]["paper_trading_authorized"] is False
    assert payload["summary"]["live_trading_authorized"] is False
    assert best["signal"] == "long"
    assert best["analog_evidence"]["supported"] is True
    assert best["regime_filter"]["allowed"] is True
    assert plan["stop_loss"] < plan["entry_price"] < plan["take_profit"]
    assert plan["order_intent"]["entry"] == "paper_only_no_order"


def test_latest_market_signal_builds_short_paper_plan(tmp_path: Path) -> None:
    closes = [180.0 * (0.9985**idx) for idx in range(180)]
    write_symbol_cache(tmp_path, "BBBUSDT", closes)

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="BBBUSDT"))

    best = payload["top"][0]
    plan = best["paper_plan"]
    assert payload["summary"]["paper_plan_found"] is True
    assert payload["summary"]["analog_supported_plan_found"] is True
    assert best["signal"] == "short"
    assert best["analog_evidence"]["supported"] is True
    assert best["regime_filter"]["allowed"] is True
    assert plan["take_profit"] < plan["entry_price"] < plan["stop_loss"]


def test_market_regime_blocks_long_against_btc_downtrend(tmp_path: Path) -> None:
    write_symbol_cache(tmp_path, "AAAUSDT", [100.0 * (1.0015**idx) for idx in range(180)])
    write_symbol_cache(tmp_path, "BTCUSDT", [180.0 * (0.9985**idx) for idx in range(180)])

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="AAAUSDT"))

    row = payload["rows"][0]
    assert payload["market_regime"]["trend_state"] == "downtrend"
    assert payload["summary"]["paper_plan_found"] is False
    assert payload["summary"]["regime_filtered_count"] == 1
    assert row["raw_signal"] == "long"
    assert row["signal"] == "none"
    assert row["status"] == "regime_blocked"
    assert row["regime_filter"]["reason"] == "long_blocked_by_market_downtrend"
    assert payload["journal"]["new_records"] == 0


def test_journal_record_persists_market_regime_context(tmp_path: Path) -> None:
    write_symbol_cache(tmp_path, "AAAUSDT", [100.0 * (1.0015**idx) for idx in range(180)])
    write_symbol_cache(tmp_path, "BTCUSDT", [100.0 * (1.0012**idx) for idx in range(180)])

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="AAAUSDT"))
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert payload["market_regime"]["trend_state"] == "uptrend"
    assert rows[0]["market_regime_id"].startswith("uptrend_")
    assert rows[0]["market_trend_state"] == "uptrend"
    assert rows[0]["regime_filter_reason"] == "regime_aligned"


def test_latest_market_signal_rejects_flat_market(tmp_path: Path) -> None:
    closes = [100.0 for _ in range(180)]
    write_symbol_cache(tmp_path, "CCCUSDT", closes)

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="CCCUSDT"))

    assert payload["summary"]["paper_plan_found"] is False
    assert payload["summary"]["analog_supported_plan_found"] is False
    assert payload["top"][0]["signal"] == "none"


def test_latest_market_signal_journal_deduplicates_same_candle(tmp_path: Path) -> None:
    closes = [100.0 * (1.0015**idx) for idx in range(180)]
    write_symbol_cache(tmp_path, "AAAUSDT", closes)
    args = base_args(tmp_path, symbols="AAAUSDT")

    first = signal_mod.run_screen(args)
    second = signal_mod.run_screen(args)

    assert first["journal"]["new_records"] == 1
    assert second["journal"]["new_records"] == 0
    records = (tmp_path / "journal.jsonl").read_text().splitlines()
    assert len(records) == 1


def test_latest_market_signal_journal_filters_allowed_pairs(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT,BBBUSDT")
    args.journal_allowed_pairs = "BBBUSDT:short"
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
            {
                "symbol": "BBBUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert rows[0]["symbol"] == "BBBUSDT"
    assert rows[0]["side"] == "short"


def test_latest_market_signal_journal_blocks_pairs_from_json(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT,BBBUSDT")
    blocked = tmp_path / "blocked.json"
    blocked.write_text(
        json.dumps(
            {
                "blocked_pairs": [
                    {
                        "timeframe": "1h",
                        "symbol": "AAAUSDT",
                        "side": "long",
                        "status": "stop_candidate",
                    }
                ]
            }
        )
    )
    args.journal_blocked_pairs_json = str(blocked)
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
            {
                "symbol": "BBBUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert summary["journal_blocked_candidate_rows"] == 1
    assert summary["journal_blocked_pairs"] == ["1h:AAAUSDT:long"]
    assert rows[0]["symbol"] == "BBBUSDT"
    assert rows[0]["side"] == "short"


def test_latest_market_signal_journal_blocks_side_from_portfolio_actions(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT,BBBUSDT")
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            {
                "portfolio_risk": {
                    "status": "normal",
                    "block_new_focus": False,
                    "reason_codes": [],
                    "blocked_sides": ["short"],
                    "segment_risk": {"blocked_sides": ["short"]},
                }
            }
        )
    )
    args.journal_risk_actions_json = str(actions)
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
            {
                "symbol": "BBBUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert summary["journal_portfolio_risk_status"] == "normal"
    assert summary["journal_portfolio_blocked_sides"] == ["short"]
    assert summary["journal_portfolio_risk_blocked_candidate_rows"] == 0
    assert summary["journal_portfolio_side_blocked_candidate_rows"] == 1
    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["side"] == "long"


def test_latest_market_signal_journal_blocks_all_when_portfolio_is_overexposed(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT,BBBUSDT")
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            {
                "portfolio_risk": {
                    "status": "overexposed",
                    "block_new_focus": True,
                    "reason_codes": ["portfolio_active>12"],
                    "blocked_sides": ["long", "short"],
                }
            }
        )
    )
    args.journal_risk_actions_json = str(actions)
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
            {
                "symbol": "BBBUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = (tmp_path / "journal.jsonl").read_text().splitlines()

    assert summary["new_records"] == 0
    assert summary["journal_portfolio_risk_status"] == "overexposed"
    assert summary["journal_portfolio_block_new_records"] is True
    assert summary["journal_portfolio_blocked_sides"] == ["long", "short"]
    assert summary["journal_portfolio_risk_blocked_candidate_rows"] == 2
    assert summary["journal_portfolio_side_blocked_candidate_rows"] == 0
    assert rows == []


def test_latest_market_signal_journal_allows_portfolio_drawdown_recovery_probe(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT")
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            {
                "portfolio_risk": {
                    "status": "portfolio_drawdown",
                    "block_new_focus": True,
                    "active": 2,
                    "active_excess": 0,
                    "reason_codes": ["portfolio_recent_drawdown_R>=30.00"],
                    "blocked_sides": [],
                    "segment_risk": {"blocked_sides": [], "segments": {"long": {"active": 0}}},
                }
            }
        )
    )
    args.journal_risk_actions_json = str(actions)
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {
                    "supported": True,
                    "used_count": 72,
                    "hit_rate": 0.60,
                    "profitable_rate": 0.60,
                    "expectancy_r": 0.45,
                },
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            }
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert summary["journal_portfolio_risk_blocked_candidate_rows"] == 0
    assert summary["journal_portfolio_drawdown_recovery_candidate_rows"] == 1
    assert rows[0]["portfolio_drawdown_recovery_probe"] is True
    assert rows[0]["portfolio_drawdown_recovery_reason"] == "portfolio_drawdown_strong_analog_recovery"


def test_latest_market_signal_journal_allows_strong_side_recovery_probe(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="BBBUSDT")
    actions = tmp_path / "actions.json"
    actions.write_text(
        json.dumps(
            {
                "portfolio_risk": {
                    "status": "normal",
                    "block_new_focus": False,
                    "reason_codes": [],
                    "blocked_sides": ["short"],
                    "segment_risk": {
                        "blocked_sides": ["short"],
                        "segments": {"short": {"status": "blocked", "active": 0}},
                    },
                }
            }
        )
    )
    args.journal_risk_actions_json = str(actions)
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "BBBUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {
                    "supported": True,
                    "used_count": 64,
                    "hit_rate": 0.58,
                    "profitable_rate": 0.60,
                    "expectancy_r": 0.42,
                },
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            }
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert summary["journal_portfolio_side_blocked_candidate_rows"] == 0
    assert summary["journal_portfolio_side_recovery_candidate_rows"] == 1
    assert rows[0]["symbol"] == "BBBUSDT"
    assert rows[0]["portfolio_side_recovery_probe"] is True
    assert rows[0]["portfolio_side_recovery_reason"] == "blocked_side_strong_analog_recovery"


def test_latest_market_signal_journal_limits_active_pair_records(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT")
    args.journal_max_active_per_pair = 1
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
            {
                "symbol": "AAAUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T01:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 99.0,
                    "stop_loss": 101.0,
                    "take_profit": 95.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert rows[0]["latest_dt"] == "2026-01-01T00:00:00+00:00"


def test_latest_market_signal_journal_limits_total_active_records(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT,BBBUSDT")
    args.journal_max_active_total = 1
    payload = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
            {
                "symbol": "BBBUSDT",
                "signal": "short",
                "latest_dt": "2026-01-01T00:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 102.0,
                    "take_profit": 96.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            },
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 1
    assert summary["open_records"] == 1
    assert summary["journal_max_active_total"] == 1
    assert summary["journal_active_total_cap_blocked_candidate_rows"] == 1
    assert rows[0]["symbol"] == "AAAUSDT"


def test_latest_market_signal_journal_total_active_cap_counts_existing_open_records(tmp_path: Path) -> None:
    args = base_args(tmp_path, symbols="AAAUSDT")
    args.journal_max_active_total = 1
    existing = signal_mod.journal_record_from_row(
        {
            "symbol": "OLDUSDT",
            "signal": "long",
            "latest_dt": "2026-01-01T00:00:00+00:00",
            "reason": "existing",
            "analog_evidence": {"supported": True},
            "paper_plan": {
                "entry_price": 100.0,
                "stop_loss": 98.0,
                "take_profit": 104.0,
                "risk_per_unit": 2.0,
                "reward_r": 2.0,
                "risk_per_trade": 0.005,
                "leverage_cap": 2.0,
            },
        },
        updated_at="2026-01-01T00:00:00+00:00",
        horizon_bars=12,
        execution_config=signal_mod.execution_config_from_args(args),
    )
    signal_mod.write_journal(Path(args.journal_jsonl), [existing])
    payload = {
        "updated_at": "2026-01-01T01:00:00+00:00",
        "rows": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "latest_dt": "2026-01-01T01:00:00+00:00",
                "reason": "test",
                "analog_evidence": {"supported": True},
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 98.0,
                    "take_profit": 104.0,
                    "risk_per_unit": 2.0,
                    "reward_r": 2.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            }
        ],
    }

    summary = signal_mod.update_journal(payload, args)
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]

    assert summary["new_records"] == 0
    assert summary["open_records"] == 1
    assert summary["journal_active_total_cap_blocked_candidate_rows"] == 1
    assert len(rows) == 1
    assert rows[0]["symbol"] == "OLDUSDT"


def test_realistic_paper_execution_waits_for_latency_and_deducts_costs() -> None:
    frame = pd.DataFrame(
        [
            {
                "dt": pd.Timestamp("2026-01-01T00:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            },
            {
                "dt": pd.Timestamp("2026-01-01T01:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
            },
            {
                "dt": pd.Timestamp("2026-01-01T02:00:00Z"),
                "open": 100.5,
                "high": 105.0,
                "low": 100.0,
                "close": 104.0,
            },
        ]
    )
    record = {
        "status": "pending_entry",
        "execution_model_version": signal_mod.REALISTIC_EXECUTION_MODEL_VERSION,
        "symbol": "AAAUSDT",
        "side": "long",
        "timeframe": "1h",
        "signal_dt": "2026-01-01T00:00:00+00:00",
        "latest_dt": "2026-01-01T00:00:00+00:00",
        "planned_entry_price": 100.0,
        "entry_price": None,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "outcome_horizon_bars": 4,
        "paper_execution": {
            "timeframe": "1h",
            "fee_bps_per_side": 5.0,
            "slippage_bps": 2.0,
            "entry_latency_bars": 1,
            "max_entry_drift_bps": 100.0,
            "funding_bps_per_8h": 1.0,
            "partial_fill_frac": 1.0,
            "min_fill_frac": 1.0,
        },
    }

    assert signal_mod.update_record_outcome(record, frame.iloc[:1], updated_at="now") is False
    assert record["status"] == "pending_entry"

    assert signal_mod.update_record_outcome(record, frame, updated_at="later") is True

    outcome = record["outcome"]
    assert record["status"] == "completed"
    assert record["entry_price"] > 100.0
    assert outcome["exit_reason"] == "take_profit"
    assert outcome["gross_r_multiple"] > outcome["r_multiple"]
    assert outcome["fee_cost_per_unit"] > 0
    assert outcome["funding_cost_per_unit"] > 0


def test_realistic_open_record_uses_entry_dt_when_tail_window_shifts() -> None:
    frame = pd.DataFrame(
        [
            {
                "dt": pd.Timestamp("2026-01-01T01:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
            },
            {
                "dt": pd.Timestamp("2026-01-01T02:00:00Z"),
                "open": 100.5,
                "high": 105.0,
                "low": 100.0,
                "close": 104.0,
            },
        ]
    )
    record = {
        "status": "open",
        "execution_model_version": signal_mod.REALISTIC_EXECUTION_MODEL_VERSION,
        "symbol": "AAAUSDT",
        "side": "long",
        "timeframe": "1h",
        "signal_dt": "2026-01-01T00:00:00+00:00",
        "latest_dt": "2026-01-01T00:00:00+00:00",
        "entry_dt": "2026-01-01T01:00:00+00:00",
        "entry_bar_index": 999,
        "entry_price": 100.02,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "outcome_horizon_bars": 4,
        "paper_execution": {
            "timeframe": "1h",
            "fee_bps_per_side": 5.0,
            "slippage_bps": 2.0,
            "entry_latency_bars": 1,
            "max_entry_drift_bps": 100.0,
            "funding_bps_per_8h": 1.0,
            "partial_fill_frac": 1.0,
            "min_fill_frac": 1.0,
        },
    }

    assert signal_mod.update_record_outcome(record, frame, updated_at="later") is True
    assert record["status"] == "completed"
    assert record["outcome"]["exit_reason"] == "take_profit"


def test_realistic_pending_entry_skips_when_stale_and_signal_missing() -> None:
    frame = pd.DataFrame(
        [
            {
                "dt": pd.Timestamp("2026-01-01T05:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            }
        ]
    )
    record = {
        "status": "pending_entry",
        "execution_model_version": signal_mod.REALISTIC_EXECUTION_MODEL_VERSION,
        "symbol": "AAAUSDT",
        "side": "long",
        "timeframe": "1h",
        "signal_dt": "2026-01-01T00:00:00+00:00",
        "latest_dt": "2026-01-01T00:00:00+00:00",
        "planned_entry_price": 100.0,
        "entry_price": None,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "outcome_horizon_bars": 4,
        "paper_execution": {
            "timeframe": "1h",
            "entry_latency_bars": 1,
            "stale_grace_bars": 2,
        },
    }

    assert signal_mod.update_record_outcome(record, frame, updated_at="later") is True

    assert record["status"] == "skipped"
    assert record["outcome"]["exit_reason"] == "stale_pending_entry_unresolved"
    assert record["outcome"]["elapsed_bars"] == 5


def test_realistic_open_record_skips_when_stale_and_entry_missing() -> None:
    frame = pd.DataFrame(
        [
            {
                "dt": pd.Timestamp("2026-01-01T05:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            }
        ]
    )
    record = {
        "status": "open",
        "execution_model_version": signal_mod.REALISTIC_EXECUTION_MODEL_VERSION,
        "symbol": "AAAUSDT",
        "side": "long",
        "timeframe": "1h",
        "signal_dt": "2026-01-01T00:00:00+00:00",
        "latest_dt": "2026-01-01T00:00:00+00:00",
        "entry_dt": "2026-01-01T01:00:00+00:00",
        "entry_price": 100.02,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "outcome_horizon_bars": 2,
        "paper_execution": {
            "timeframe": "1h",
            "entry_latency_bars": 1,
            "stale_grace_bars": 1,
        },
    }

    assert signal_mod.update_record_outcome(record, frame, updated_at="later") is True

    assert record["status"] == "skipped"
    assert record["outcome"]["exit_reason"] == "stale_open_entry_unresolved"
    assert record["outcome"]["elapsed_bars"] == 4


def test_realistic_pending_entry_waits_before_stale_grace() -> None:
    frame = pd.DataFrame(
        [
            {
                "dt": pd.Timestamp("2026-01-01T02:00:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            }
        ]
    )
    record = {
        "status": "pending_entry",
        "execution_model_version": signal_mod.REALISTIC_EXECUTION_MODEL_VERSION,
        "symbol": "AAAUSDT",
        "side": "long",
        "timeframe": "1h",
        "signal_dt": "2026-01-01T00:00:00+00:00",
        "latest_dt": "2026-01-01T00:00:00+00:00",
        "planned_entry_price": 100.0,
        "entry_price": None,
        "stop_loss": 98.0,
        "take_profit": 104.0,
        "outcome_horizon_bars": 4,
        "paper_execution": {
            "timeframe": "1h",
            "entry_latency_bars": 1,
            "stale_grace_bars": 2,
        },
    }

    assert signal_mod.update_record_outcome(record, frame, updated_at="later") is False
    assert record["status"] == "pending_entry"


def test_timeframe_aware_return_windows_use_real_hours() -> None:
    assert signal_mod.bars_for_hours("1h", 24.0) == 24
    assert signal_mod.bars_for_hours("15m", 24.0) == 96
    assert signal_mod.bars_for_hours("15m", 6.0) == 24


def test_latest_market_signal_writes_found_and_no_markers(tmp_path: Path) -> None:
    found_marker = tmp_path / "FOUND.txt"
    no_marker = tmp_path / "NO.txt"
    payload = {
        "updated_at": "2026-07-17T00:00:00+00:00",
        "summary": {"rows": 1, "paper_plan_found": True},
        "top": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 99.0,
                    "take_profit": 102.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            }
        ],
    }

    signal_mod.write_marker(payload, found_marker, no_marker)

    assert found_marker.exists()
    assert "FOUND_CONTRACT_MARKET_PAPER_PLAN" in found_marker.read_text()
    assert not no_marker.exists()

    payload["summary"]["paper_plan_found"] = False
    signal_mod.write_marker(payload, found_marker, no_marker)

    assert no_marker.exists()
    assert "NO_CONTRACT_MARKET_PAPER_PLAN" in no_marker.read_text()
    assert not found_marker.exists()
