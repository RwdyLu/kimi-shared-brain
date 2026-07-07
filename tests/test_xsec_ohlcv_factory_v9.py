from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.xsec_ohlcv_factory import (  # noqa: E402
    OhlcvConfig,
    advance_checks,
    config_for_preset,
    long_only_weights,
    market_filter,
    score_matrix,
    simulate,
)


def close_matrix(periods: int = 80) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": dt,
            "AAA": [100 + idx for idx in range(periods)],
            "BBB": [100 + idx * 0.5 for idx in range(periods)],
            "CCC": [100 - idx * 0.2 for idx in range(periods)],
            "DDD": [100] * periods,
        }
    )


def test_long_only_weights_are_cash_or_gross_one() -> None:
    row = pd.Series({"AAA": 3.0, "BBB": 2.0, "CCC": 1.0})
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    weights = long_only_weights(row, cfg, allow_exposure=True)
    assert weights is not None
    assert weights["AAA"] == 0.5
    assert weights["BBB"] == 0.5
    assert weights["CCC"] == 0.0
    assert sum(abs(v) for v in weights.values()) == 1.0
    assert long_only_weights(row, cfg, allow_exposure=False) == {"AAA": 0.0, "BBB": 0.0, "CCC": 0.0}


def test_score_matrix_supports_momentum_and_risk_adjusted() -> None:
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    mom = score_matrix(close_matrix(), cfg)
    assert mom["AAA"].iloc[4] > 0
    risk_cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="risk_adj_mom", market_filter_h=0, vol_target_ann=0.0)
    risk_adj = score_matrix(close_matrix(), risk_cfg)
    assert set(risk_adj.columns) == {"AAA", "BBB", "CCC", "DDD"}


def test_market_filter_turns_off_when_market_momentum_is_negative() -> None:
    data = close_matrix()
    data["AAA"] = list(reversed(data["AAA"].tolist()))
    data["BBB"] = list(reversed(data["BBB"].tolist()))
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="mom", market_filter_h=4, vol_target_ann=0.0)
    allowed = market_filter(data, cfg)
    assert not bool(allowed.iloc[-1])


def test_simulate_reports_gate_inputs() -> None:
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=4, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    result20 = simulate(close_matrix(120), cfg, cost_bps=20.0, bootstrap_iterations=10)
    result40 = simulate(close_matrix(120), cfg, cost_bps=40.0, bootstrap_iterations=10)
    checks = advance_checks(result20, result40)
    assert "equal_weight_benchmark" in result20
    assert "bootstrap_p5_ge_0_25" in checks
    assert result20["daily_turnover"] >= 0


def test_presets_select_distinct_search_spaces() -> None:
    core = config_for_preset("core", "cache", "start", "end", "embargo", 10, "a.json", "a.md")
    slow = config_for_preset("slow", "cache", "start", "end", "embargo", 10, "b.json", "b.md")
    neighbor = config_for_preset("defensive_neighbor", "cache", "start", "end", "embargo", 10, "c.json", "c.md")
    drawdown = config_for_preset("defensive_drawdown", "cache", "start", "end", "embargo", 10, "d.json", "d.md")
    assert core.out_json == "a.json"
    assert slow.out_json == "b.json"
    assert slow.rebalances_h != core.rebalances_h
    assert 1440 in slow.lookbacks_h
    assert neighbor.score_modes == ("risk_adj_mom",)
    assert 0.10 in neighbor.vol_targets_ann
    assert min(drawdown.vol_targets_ann) == 0.08
    assert max(drawdown.market_filters_h) == 2160
