from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.schema import ContractCandidate
from v9.contract.simulator import attach_regimes, prepare_features, simulate_candidate


def bars(rows: list[tuple[float, float, float, float, str]]) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": dt,
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "regime_id": [r[4] for r in rows],
            "insufficient_history": False,
        }
    )


def candidate(**kwargs) -> ContractCandidate:
    data = {
        "symbol": "LINKUSDT",
        "allowed_regimes": ("up_normal",),
        "breakout_n": 1,
        "atr_n": 1,
        "stop_atr_k": 1.0,
        "tp_r_multiple": 2.0,
        "max_hold_bars": 10,
        "risk_per_trade": 0.01,
        "leverage_cap": 1.0,
        "cooldown_bars": 0,
        "fee_bps": 0.0,
        "slippage_bps": 0.0,
        "funding_bps_per_8h": 0.0,
    }
    data.update(kwargs)
    return ContractCandidate(**data)


def test_same_bar_stop_and_target_uses_pessimistic_stop() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 110, 98, 105, "up_normal"),
        ]
    )
    result = simulate_candidate(df, candidate(), include_trades=True)
    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == 100.0
    assert pd.Timestamp(trade["entry_time"]) > pd.Timestamp(trade["signal_time"])
    assert trade["entry_index"] > trade["signal_index"]
    assert result["residual_positions"] == 0


def test_gap_through_stop_exits_at_worse_open() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 103, 101, 102.5, "up_normal"),
            (99, 101, 95, 100, "up_normal"),
        ]
    )
    result = simulate_candidate(df, candidate(tp_r_multiple=10.0), include_trades=True)
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == 99.0


def test_breakeven_stop_uses_previous_bar_trigger_only() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 104, 101, 103.0, "up_normal"),
            (103, 104, 102, 103.5, "up_normal"),
            (101, 102, 100, 101.0, "up_normal"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(tp_r_multiple=10.0, be_trigger_r=0.5, be_lock_r=0.0),
        include_trades=True,
    )
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == 102.0


def test_breakeven_does_not_use_same_bar_high() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 106, 100.5, 103.0, "up_normal"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(tp_r_multiple=10.0, be_trigger_r=0.5, be_lock_r=0.0),
        include_trades=True,
    )
    trade = result["trades"][0]
    assert trade["exit_reason"] == "train_end"


def test_trailing_stop_uses_prior_high_and_atr() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 108, 101, 106.0, "up_normal"),
            (106, 107, 100.5, 105.0, "up_normal"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(tp_r_multiple=10.0, trail_atr_mult=1.0, trail_trigger_r=0.5),
        include_trades=True,
    )
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == 101.0


def test_max_hold_forces_next_open_exit() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 103, 101, 102.5, "up_normal"),
            (103, 104, 102, 103.5, "up_normal"),
        ]
    )
    result = simulate_candidate(df, candidate(tp_r_multiple=10.0, max_hold_bars=1), include_trades=True)
    trade = result["trades"][0]
    assert trade["exit_reason"] == "max_hold"
    assert trade["exit_price"] == 103.0


def test_train_end_forces_flat_residual_zero() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 103, 101, 102.5, "up_normal"),
        ]
    )
    result = simulate_candidate(df, candidate(tp_r_multiple=10.0, stop_atr_k=10.0), include_trades=True)
    assert result["trade_count"] == 1
    assert result["trades"][0]["exit_reason"] == "train_end"
    assert result["residual_positions"] == 0


def test_regime_filter_blocks_disallowed_entries() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "deep_drawdown"),
            (100, 102, 100, 101, "deep_drawdown"),
            (102, 110, 98, 105, "deep_drawdown"),
        ]
    )
    result = simulate_candidate(df, candidate(), include_trades=True)
    assert result["trade_count"] == 0


def test_attach_regimes_carries_regime_drawdown_feature() -> None:
    hourly = pd.DataFrame(
        {
            "dt": pd.date_range("2020-01-02", periods=2, freq="1h", tz="UTC"),
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
        }
    )
    labels = pd.DataFrame(
        {
            "dt": [pd.Timestamp("2020-01-01", tz="UTC")],
            "regime_id": ["up_normal"],
            "insufficient_history": [False],
            "drawdown_1y": [0.24],
        }
    )
    out = attach_regimes(hourly, labels)
    assert out["regime_id"].tolist() == ["up_normal", "up_normal"]
    assert out["drawdown_1y"].tolist() == [0.24, 0.24]


def test_regime_drawdown_filter_blocks_high_drawdown_entries() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 103, 101, 102, "up_normal"),
        ]
    )
    df["drawdown_1y"] = [0.10, 0.30, 0.30]

    unfiltered = simulate_candidate(df, candidate(tp_r_multiple=10.0), include_trades=True)
    filtered = simulate_candidate(
        df,
        candidate(tp_r_multiple=10.0, max_regime_drawdown_1y=0.25),
        include_trades=True,
    )

    assert unfiltered["trade_count"] == 1
    assert filtered["trade_count"] == 0


def test_pullback_entry_uses_rsi_and_ema_filter() -> None:
    df = bars(
        [
            (100, 100.1, 99.9, 100, "up_normal"),
            (110, 110.1, 109.9, 110, "up_normal"),
            (109, 109.1, 108.9, 109, "up_normal"),
            (108, 108.1, 107.9, 108, "up_normal"),
            (110, 110.1, 109.9, 110, "up_normal"),
        ]
    )
    features = prepare_features(
        df,
        candidate(
            family="pullback_long_v1",
            trend_ema_len=3,
            rsi_len=2,
            rsi_entry_max=40.0,
            rsi_exit_min=60.0,
        ),
    )

    assert features["entry_signal"].iloc[3]
    assert not features["entry_signal"].iloc[2]


def test_pullback_signal_exit_executes_next_open() -> None:
    df = bars(
        [
            (100, 100.1, 99.9, 100, "up_normal"),
            (110, 110.1, 109.9, 110, "up_normal"),
            (109, 109.1, 108.9, 109, "up_normal"),
            (108, 108.1, 107.9, 108, "up_normal"),
            (110, 110.1, 109.9, 110, "up_normal"),
            (111, 111.1, 110.9, 111, "up_normal"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(
            family="pullback_long_v1",
            trend_ema_len=3,
            rsi_len=2,
            rsi_entry_max=40.0,
            rsi_exit_min=60.0,
            stop_atr_k=10.0,
            tp_r_multiple=100.0,
            max_hold_bars=10,
        ),
        include_trades=True,
    )

    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_index"] == 4
    assert trade["exit_index"] == 5
    assert trade["exit_reason"] == "signal_exit"
    assert trade["exit_price"] == 111.0


def test_bear_fade_short_enters_on_rally_in_downtrend_and_hits_target() -> None:
    df = bars(
        [
            (100, 101, 99, 100, "deep_drawdown"),
            (95, 96, 94, 95, "deep_drawdown"),
            (90, 91, 89, 90, "deep_drawdown"),
            (85, 86, 84, 85, "deep_drawdown"),
            (80, 81, 79, 80, "deep_drawdown"),
            (82, 83, 81, 82, "deep_drawdown"),
            (84, 85, 83, 84, "deep_drawdown"),
            (83, 84, 80, 82, "deep_drawdown"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(
            family="bear_rally_fade_short_v1",
            side="short",
            allowed_regimes=("deep_drawdown",),
            regime_len=5,
            slope_len=1,
            rsi_len=2,
            rsi_hi=70.0,
            stop_pct=0.03,
            target_pct=0.02,
            max_hold_bars=10,
            risk_per_trade=0.01,
            leverage_cap=1.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            funding_bps_per_8h=0.0,
            short_extra_cost_bps=0.0,
        ),
        include_trades=True,
    )

    assert result["trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_index"] == 7
    assert trade["side"] == "short"
    assert trade["exit_reason"] == "take_profit"
    assert abs(trade["exit_price"] - 81.34) < 1e-9
    assert trade["net_pnl"] > 0


def test_bear_fade_short_stop_uses_worse_gap_open() -> None:
    df = bars(
        [
            (100, 101, 99, 100, "deep_drawdown"),
            (95, 96, 94, 95, "deep_drawdown"),
            (90, 91, 89, 90, "deep_drawdown"),
            (85, 86, 84, 85, "deep_drawdown"),
            (80, 81, 79, 80, "deep_drawdown"),
            (82, 83, 81, 82, "deep_drawdown"),
            (84, 85, 83, 84, "deep_drawdown"),
            (83, 84, 82, 82, "deep_drawdown"),
            (88, 89, 87, 88, "deep_drawdown"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(
            family="bear_rally_fade_short_v1",
            side="short",
            allowed_regimes=("deep_drawdown",),
            regime_len=5,
            slope_len=1,
            rsi_len=2,
            rsi_hi=70.0,
            stop_pct=0.03,
            target_pct=0.02,
            max_hold_bars=10,
            risk_per_trade=0.01,
            leverage_cap=1.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            funding_bps_per_8h=0.0,
            short_extra_cost_bps=0.0,
        ),
        include_trades=True,
    )

    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_price"] == 88.0
    assert trade["net_pnl"] < 0


def test_inverse_atr_scaling_reduces_risk_budget_on_high_atr() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 112, 92, 103, "up_normal"),
        ]
    )
    unscaled = simulate_candidate(df, candidate(), include_trades=True)
    scaled = simulate_candidate(
        df,
        candidate(vol_scaling="inverse_atr", vol_lookback_n=2, scale_min=0.25, scale_max=1.0),
        include_trades=True,
    )

    assert unscaled["trade_count"] == 1
    assert scaled["trade_count"] == 1
    assert scaled["trades"][0]["risk_scale"] < 1.0
    assert scaled["trades"][0]["risk_amount"] < unscaled["trades"][0]["risk_amount"]


def test_vol_target_scaling_skips_trade_when_warmup_missing() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 103, 101, 102, "up_normal"),
        ]
    )
    result = simulate_candidate(
        df,
        candidate(vol_scaling="vol_target", vol_lookback_n=10, vol_target_ann=0.5),
        include_trades=True,
    )

    assert result["trade_count"] == 0


def test_signal_features_do_not_use_future_bars() -> None:
    df = bars(
        [
            (100, 100, 99, 100, "up_normal"),
            (100, 102, 100, 101, "up_normal"),
            (102, 103, 101, 102.5, "up_normal"),
            (103, 104, 102, 103.5, "up_normal"),
        ]
    )
    c = candidate()
    original = prepare_features(df, c)["entry_signal"].iloc[:2].tolist()
    changed = df.copy()
    changed.loc[3, ["high", "low", "close"]] = [10_000.0, 1.0, 9_000.0]
    after = prepare_features(changed, c)["entry_signal"].iloc[:2].tolist()
    assert after == original


def test_attach_regimes_normalizes_datetime_precision_and_uses_previous_daily_label() -> None:
    hourly = pd.DataFrame(
        {
            "dt": pd.Series(pd.date_range("2020-01-02", periods=2, freq="1h", tz="UTC"), dtype="datetime64[ms, UTC]"),
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
        }
    )
    labels = pd.DataFrame(
        {
            "dt": pd.Series(pd.to_datetime(["2020-01-01"], utc=True), dtype="datetime64[us, UTC]"),
            "regime_id": ["up_normal"],
            "insufficient_history": [False],
        }
    )
    out = attach_regimes(hourly, labels)
    assert out["regime_id"].tolist() == ["up_normal", "up_normal"]
