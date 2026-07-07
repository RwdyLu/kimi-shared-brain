from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.pair_mr import (  # noqa: E402
    PairMRConfig,
    leg_weights,
    net_excluding_top_winners,
    prepare_pair_features,
    rolling_beta,
    simulate_pair,
)


def pair_bars(y: list[float], x: list[float]) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=len(y), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": dt,
            "open_y": y,
            "close_y": y,
            "open_x": x,
            "close_x": x,
        }
    )


def test_leg_weights_are_gross_normalized() -> None:
    wy, wx = leg_weights(2.0)
    assert abs(wy + wx - 1.0) < 1e-12
    assert wy == 1.0 / 3.0
    assert wx == 2.0 / 3.0


def test_rolling_beta_is_shifted_to_avoid_current_bar_leakage() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 100.0])
    y = 2.0 * x
    beta = rolling_beta(y, x, 3)
    changed = x.copy()
    changed.iloc[-1] = 1000.0
    changed_beta = rolling_beta(2.0 * changed, changed, 3)
    assert beta.iloc[5] == changed_beta.iloc[5]


def test_prepare_pair_features_generates_z_scores() -> None:
    bars = pair_bars(
        [100, 101, 102, 103, 104, 105, 104, 103, 102, 101],
        [100, 100.5, 101, 101.5, 102, 102.5, 102, 101.5, 101, 100.5],
    )
    cfg = PairMRConfig("Y", "X", beta_lookback=3, z_lookback=3, z_entry=1.5, z_exit=0.5, z_stop=4.0, max_hold_bars=3)
    features = prepare_pair_features(bars, cfg)
    assert "beta" in features
    assert "z" in features
    assert features["z"].notna().any()


def test_net_excluding_top_winners_removes_best_five() -> None:
    trades = [{"net_pnl": 10.0} for _ in range(6)] + [{"net_pnl": -1.0}]
    assert net_excluding_top_winners(trades) == 9.0


def test_simulate_pair_runs_and_records_costs() -> None:
    y = [100, 101, 102, 103, 104, 110, 105, 103, 102, 101, 100, 99, 98]
    x = [100, 100.5, 101, 101.5, 102, 102, 102, 101.5, 101, 100.5, 100, 99.5, 99]
    cfg = PairMRConfig(
        "Y",
        "X",
        beta_lookback=3,
        z_lookback=3,
        z_entry=0.5,
        z_exit=0.25,
        z_stop=4.0,
        max_hold_bars=3,
        fee_bps=0.0,
        slippage_bps=0.0,
    )
    result = simulate_pair(pair_bars(y, x), cfg)
    assert result["signal_count"] > 0
    assert result["trade_count"] > 0
    assert result["trades"][0]["cost_ret"] == 0.0
