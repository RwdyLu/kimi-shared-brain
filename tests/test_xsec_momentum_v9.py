from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.xsec_momentum import (  # noqa: E402
    XSecConfig,
    XSecRiskConfig,
    deterministic_ranks,
    exposure_scale_from_history,
    momentum_scores,
    one_step_neighbors,
    simulate_config,
    target_weights,
)
from v9.contract.xsec_momentum_risk import block_bootstrap_sharpe_p5  # noqa: E402


def close_matrix() -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=12, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": dt,
            "AAA": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111],
            "BBB": [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89],
            "CCC": [100] * 12,
            "DDD": [100, 100, 101, 101, 102, 102, 103, 103, 104, 104, 105, 105],
        }
    )


def test_deterministic_ranks_break_ties_by_symbol() -> None:
    row = pd.Series({"BBB": 1.0, "AAA": 1.0, "CCC": -1.0})
    assert deterministic_ranks(row) == ["AAA", "BBB", "CCC"]


def test_target_weights_are_gross_one_and_net_zero() -> None:
    row = pd.Series({"AAA": 2.0, "BBB": 1.0, "CCC": -1.0, "DDD": -2.0})
    weights = target_weights(row, XSecConfig(lookback_h=2, skip_h=0, rebalance_h=2, k=1))
    assert weights is not None
    assert weights["AAA"] == 0.5
    assert weights["DDD"] == -0.5
    assert abs(sum(weights.values())) < 1e-12
    assert sum(abs(v) for v in weights.values()) == 1.0


def test_target_weights_hysteresis_keeps_nearby_existing_positions() -> None:
    row = pd.Series({"AAA": 3.0, "BBB": 4.0, "CCC": 2.0, "DDD": 1.0})
    current = {"AAA": 0.5, "BBB": 0.0, "CCC": -0.5, "DDD": 0.0}
    weights = target_weights(
        row,
        XSecConfig(lookback_h=2, skip_h=0, rebalance_h=2, k=1),
        current_weights=current,
        risk_cfg=XSecRiskConfig(hysteresis_buffer=1),
    )
    assert weights is not None
    assert weights["AAA"] == 0.5
    assert weights["CCC"] == -0.5


def test_momentum_scores_use_skip_gap() -> None:
    cfg = XSecConfig(lookback_h=2, skip_h=1, rebalance_h=2, k=1)
    scores = momentum_scores(close_matrix(), cfg)
    expected = close_matrix()["AAA"].shift(1) / close_matrix()["AAA"].shift(3) - 1.0
    assert scores["AAA"].equals(expected)


def test_simulate_config_runs_and_reports_metrics() -> None:
    result = simulate_config(close_matrix(), XSecConfig(lookback_h=2, skip_h=0, rebalance_h=2, k=1), cost_bps=0.0)
    assert result["rebalance_count"] > 0
    assert "sharpe" in result
    assert "ic_t_stat" in result
    assert result["daily_turnover"] >= 0
    assert "symbol_pnl" in result
    assert "rolling_180d_sharpe" in result


def test_vol_target_scale_uses_past_returns_and_clips() -> None:
    risk = XSecRiskConfig(vol_target_ann=0.20, vol_lookback_h=4, vol_min_scale=0.25, vol_max_scale=1.0)
    assert exposure_scale_from_history([0.01, -0.01, 0.02], risk) == 1.0
    scale = exposure_scale_from_history([0.05, -0.05, 0.04, -0.04], risk)
    assert 0.25 <= scale <= 1.0


def test_bootstrap_sharpe_p5_is_deterministic() -> None:
    rows = [{"dt": f"2020-01-{idx + 1:02d}", "net_return": 0.001} for idx in range(80)]
    first = block_bootstrap_sharpe_p5(rows, block_days=10, iterations=20, seed=7)
    second = block_bootstrap_sharpe_p5(rows, block_days=10, iterations=20, seed=7)
    assert first == second
    assert first > 0


def test_one_step_neighbors_only_changes_one_grid_axis() -> None:
    grid = [
        XSecConfig(l, s, r, k)
        for l in [72, 168]
        for s in [0, 24]
        for r in [24, 72]
        for k in [1, 2]
    ]
    cfg = XSecConfig(72, 0, 24, 1)
    neighbors = one_step_neighbors(cfg, grid)
    assert XSecConfig(168, 0, 24, 1) in neighbors
    assert XSecConfig(72, 24, 24, 1) in neighbors
    assert XSecConfig(168, 24, 24, 1) not in neighbors
