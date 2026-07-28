from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.xsec_ohlcv_factory import (  # noqa: E402
    OhlcvConfig,
    RunConfig,
    advance_checks,
    bootstrap_seed,
    bootstrap_threshold,
    build_arg_parser,
    config_for_preset,
    data_fingerprint,
    data_snapshot_path_for,
    leave_one_symbol_summary,
    gate_alignment_summary,
    load_explicit_configs,
    hedged_long_weights,
    long_only_weights,
    long_short_weights,
    market_filter,
    plateau_stability_summary,
    append_progress_row,
    progress_row_sort_key,
    progress_meta_path_for,
    progress_path_for,
    read_data_snapshot,
    run_grid,
    score_matrix,
    simulate,
    split_selection_validation,
    validation_checks,
    validation_sharpe_threshold,
    walk_forward_summary,
    write_progress_meta,
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


def crash_matrix(periods: int = 96) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    aaa = []
    bbb = []
    for idx in range(periods):
        if idx < 36:
            aaa.append(100 + idx * 1.5)
            bbb.append(100 + idx)
        elif idx < 48:
            aaa.append(154 - (idx - 35) * 5.0)
            bbb.append(135 - (idx - 35) * 4.0)
        else:
            aaa.append(94 + (idx - 48) * 0.1)
            bbb.append(87 + (idx - 48) * 0.1)
    return pd.DataFrame(
        {
            "dt": dt,
            "AAA": aaa,
            "BBB": bbb,
            "CCC": [100 - idx * 0.1 for idx in range(periods)],
            "DDD": [100] * periods,
        }
    )


def regime_rollover_matrix(periods: int = 80) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    values = []
    for idx in range(periods):
        if idx < periods - 4:
            values.append(100.0 + idx)
        else:
            values.append(values[-1] - 1.0)
    return pd.DataFrame({"dt": dt, "AAA": values, "BBB": values, "CCC": values, "DDD": values})


def market_drawdown_matrix(periods: int = 60) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    values = []
    for idx in range(periods):
        if idx < 36:
            values.append(100.0 + idx * 2.0)
        else:
            values.append(values[-1] - 3.0)
    return pd.DataFrame({"dt": dt, "AAA": values, "BBB": values, "CCC": values, "DDD": values})


def passing_gate_result(
    daily_turnover: float = 0.10,
    active_rebalance_event_count: int = 20,
    time_in_market_frac: float = 0.20,
) -> dict:
    return {
        "sharpe": 1.5,
        "max_drawdown": 0.10,
        "daily_turnover": daily_turnover,
        "active_rebalance_event_count": active_rebalance_event_count,
        "time_in_market_frac": time_in_market_frac,
        "total_return": 0.20,
        "yearly_positive_count": 4,
        "yearly": {
            "2021": {"net_return": 0.05},
            "2022": {"net_return": 0.05},
            "2023": {"net_return": 0.05},
            "2024H1": {"net_return": 0.05},
        },
        "bootstrap_30d_sharpe_p5": 0.80,
        "top_positive_symbol_share": 0.40,
        "equal_weight_benchmark": {
            "sharpe_excess": 0.20,
            "drawdown_ratio": 0.50,
        },
    }


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


def test_long_short_weights_are_market_neutral_gross_one() -> None:
    row = pd.Series({"AAA": 4.0, "BBB": 3.0, "CCC": 2.0, "DDD": 1.0})
    cfg = OhlcvConfig(
        lookback_h=4,
        skip_h=0,
        rebalance_h=2,
        k=1,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        portfolio_mode="long_short",
    )

    weights = long_short_weights(row, cfg, allow_exposure=True)

    assert weights == {"AAA": 0.5, "BBB": 0.0, "CCC": 0.0, "DDD": -0.5}
    assert sum(weights.values()) == 0.0
    assert sum(abs(v) for v in weights.values()) == 1.0


def test_long_short_weights_use_hedge_ratio_as_short_to_long_ratio() -> None:
    row = pd.Series({"AAA": 4.0, "BBB": 3.0, "CCC": 2.0, "DDD": 1.0})
    cfg = OhlcvConfig(
        lookback_h=4,
        skip_h=0,
        rebalance_h=2,
        k=1,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        portfolio_mode="long_short",
        hedge_ratio=0.5,
    )

    weights = long_short_weights(row, cfg, allow_exposure=True)

    assert weights == {"AAA": 2.0 / 3.0, "BBB": 0.0, "CCC": 0.0, "DDD": -1.0 / 3.0}
    assert sum(weights.values()) == 1.0 / 3.0
    assert sum(abs(v) for v in weights.values()) == 1.0


def test_hedged_long_weights_short_single_btc_overlay() -> None:
    row = pd.Series({"ADAUSDT": 4.0, "BTCUSDT": 3.0, "ETHUSDT": 2.0, "XRPUSDT": 1.0})
    cfg = OhlcvConfig(
        lookback_h=4,
        skip_h=0,
        rebalance_h=2,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        portfolio_mode="hedged_long",
        hedge_ratio=0.5,
    )

    weights = hedged_long_weights(row, cfg, allow_exposure=True)

    assert weights == {"ADAUSDT": 0.5, "BTCUSDT": 0.0, "ETHUSDT": 0.0, "XRPUSDT": 0.0}
    assert sum(max(v, 0.0) for v in weights.values()) == 0.5


def test_hedged_long_can_hold_downtrend_btc_short_when_market_filter_blocks() -> None:
    row = pd.Series({"ADAUSDT": 4.0, "BTCUSDT": 3.0, "ETHUSDT": 2.0, "XRPUSDT": 1.0})
    cfg = OhlcvConfig(
        lookback_h=4,
        skip_h=0,
        rebalance_h=2,
        k=2,
        score_mode="mom",
        market_filter_h=4,
        vol_target_ann=0.0,
        portfolio_mode="hedged_long",
        hedge_ratio=0.5,
        downtrend_hedge_ratio=0.25,
    )

    weights = hedged_long_weights(row, cfg, allow_exposure=False)

    assert weights == {"ADAUSDT": 0.0, "BTCUSDT": -0.25, "ETHUSDT": 0.0, "XRPUSDT": 0.0}
    assert sum(weights.values()) == -0.25


def test_load_explicit_configs_accepts_rescue_plan_configs(tmp_path) -> None:
    path = tmp_path / "configs.json"
    path.write_text(
        """
        {
          "configs": [
            {
              "lookback_h": 504,
              "skip_h": 0,
              "rebalance_h": 168,
              "k": 3,
              "score_mode": "risk_adj_mom",
              "market_filter_h": 1008,
              "vol_target_ann": 0.06,
              "n_tranches": 3,
              "drawdown_stop": 0.10,
              "cooldown_h": 168,
              "market_confirm_h": 336,
              "market_drawdown_limit": 0.25,
              "portfolio_mode": "long_short",
              "hedge_ratio": 0.5,
              "downtrend_hedge_ratio": 0.25
            }
          ]
        }
        """
    )

    configs = load_explicit_configs(path)

    assert configs == (
        OhlcvConfig(
            lookback_h=504,
            skip_h=0,
            rebalance_h=168,
            k=3,
            score_mode="risk_adj_mom",
            market_filter_h=1008,
            vol_target_ann=0.06,
            n_tranches=3,
            drawdown_stop=0.10,
            cooldown_h=168,
            market_confirm_h=336,
            market_drawdown_limit=0.25,
            portfolio_mode="long_short",
            hedge_ratio=0.5,
            downtrend_hedge_ratio=0.25,
        ),
    )


def test_cli_accepts_breakout_presets() -> None:
    parser = build_arg_parser()
    assert parser.parse_args(["--preset", "evergreen_fast"]).preset == "evergreen_fast"
    assert parser.parse_args(["--preset", "evergreen_guarded"]).preset == "evergreen_guarded"
    assert parser.parse_args(["--preset", "evergreen_regime_guarded"]).preset == "evergreen_regime_guarded"
    assert parser.parse_args(["--preset", "evergreen_lowvol_guarded"]).preset == "evergreen_lowvol_guarded"
    assert parser.parse_args(["--preset", "breakout_fast"]).preset == "breakout_fast"
    assert parser.parse_args(["--preset", "breakout_slow"]).preset == "breakout_slow"
    assert parser.parse_args(["--preset", "hq_active_recent"]).preset == "hq_active_recent"
    assert parser.parse_args(["--preset", "hq_recent_signal"]).preset == "hq_recent_signal"
    assert parser.parse_args(["--preset", "hq_decay_bridge"]).preset == "hq_decay_bridge"
    assert parser.parse_args(["--preset", "hq_wf_bridge"]).preset == "hq_wf_bridge"
    assert parser.parse_args(["--preset", "hq_wf_hostile_bridge"]).preset == "hq_wf_hostile_bridge"
    assert parser.parse_args(["--preset", "hq_wf_hostile_hedged"]).preset == "hq_wf_hostile_hedged"
    assert parser.parse_args(["--preset", "hq_wf_hostile_regime_hedged"]).preset == "hq_wf_hostile_regime_hedged"
    assert parser.parse_args(["--preset", "hq_wf_tail_defense"]).preset == "hq_wf_tail_defense"
    assert parser.parse_args(["--preset", "hq_short_reversal"]).preset == "hq_short_reversal"
    assert parser.parse_args(["--preset", "hq_wf_hostile_long_short"]).preset == "hq_wf_hostile_long_short"
    assert parser.parse_args(["--preset", "hq_market_neutral"]).preset == "hq_market_neutral"
    assert parser.parse_args(["--preset", "hq_hedged_long"]).preset == "hq_hedged_long"


def test_breakout_presets_sweep_stop_enabled_configs() -> None:
    cfg = config_for_preset(
        "breakout_fast",
        cache_dir="cache",
        train_start="2020-01-01",
        train_end="2020-12-31",
        embargo_start="2021-01-01",
        bootstrap_iterations=10,
        out_json="out.json",
        out_md="out.md",
    )

    assert cfg.drawdown_stops == (0.10, 0.15)
    assert cfg.cooldowns_h == (168,)
    assert cfg.market_confirm_hs == (168,)
    assert cfg.market_drawdown_limits == (0.25,)


def test_short_reversal_preset_is_focused_market_neutral_grid() -> None:
    cfg = config_for_preset(
        "hq_short_reversal",
        cache_dir="cache",
        train_start="2020-01-01",
        train_end="2020-12-31",
        embargo_start="2021-01-01",
        bootstrap_iterations=10,
        out_json="out.json",
        out_md="out.md",
    )

    total = (
        len(cfg.lookbacks_h)
        * len(cfg.skips_h)
        * len(cfg.rebalances_h)
        * len(cfg.ks)
        * len(cfg.score_modes)
        * len(cfg.market_filters_h)
        * len(cfg.vol_targets_ann)
        * len(cfg.n_tranches)
        * len(cfg.drawdown_stops)
        * len(cfg.cooldowns_h)
        * len(cfg.market_confirm_hs)
        * len(cfg.market_drawdown_limits)
        * len(cfg.portfolio_modes)
        * len(cfg.hedge_ratios)
        * len(cfg.downtrend_hedge_ratios)
    )

    assert total == 24
    assert cfg.score_modes == ("risk_adj_reversal",)
    assert cfg.market_filters_h == (0,)
    assert cfg.portfolio_modes == ("long_short",)
    assert cfg.hedge_ratios == (1.0,)
    assert cfg.drawdown_stops == (0.08,)
    assert cfg.selection_min_time_in_market_frac == 0.60
    assert cfg.validation_min_2024h1_periods == 1


def test_score_matrix_supports_momentum_and_risk_adjusted() -> None:
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    mom = score_matrix(close_matrix(), cfg)
    assert mom["AAA"].iloc[4] > 0
    risk_cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="risk_adj_mom", market_filter_h=0, vol_target_ann=0.0)
    risk_adj = score_matrix(close_matrix(), risk_cfg)
    assert set(risk_adj.columns) == {"AAA", "BBB", "CCC", "DDD"}
    breakout_cfg = OhlcvConfig(lookback_h=12, skip_h=0, rebalance_h=2, k=2, score_mode="breakout", market_filter_h=0, vol_target_ann=0.0)
    breakout = score_matrix(close_matrix(120), breakout_cfg)
    assert breakout["AAA"].dropna().iloc[-1] > breakout["CCC"].dropna().iloc[-1]
    vol_breakout_cfg = OhlcvConfig(lookback_h=48, skip_h=0, rebalance_h=2, k=2, score_mode="vol_breakout", market_filter_h=0, vol_target_ann=0.0)
    vol_breakout = score_matrix(close_matrix(240), vol_breakout_cfg)
    assert set(vol_breakout.columns) == {"AAA", "BBB", "CCC", "DDD"}
    assert vol_breakout.dropna(how="all").shape[0] > 0


def test_score_matrix_risk_adjusted_reversal_rewards_recent_losers() -> None:
    dt = pd.date_range("2020-01-01", periods=120, freq="1h", tz="UTC")
    data = pd.DataFrame(
        {
            "dt": dt,
            "DUMPED": [100.0 if idx < 96 else 100.0 - (idx - 95) * 1.0 for idx in range(120)],
            "PUMPED": [100.0 if idx < 96 else 100.0 + (idx - 95) * 1.0 for idx in range(120)],
            "FLAT": [100.0] * 120,
            "DRIFT": [100.0 + idx * 0.02 for idx in range(120)],
        }
    )
    cfg = OhlcvConfig(
        lookback_h=24,
        skip_h=0,
        rebalance_h=24,
        k=2,
        score_mode="risk_adj_reversal",
        market_filter_h=0,
        vol_target_ann=0.0,
    )

    scores = score_matrix(data, cfg).dropna(how="all").iloc[-1]

    assert scores["DUMPED"] > scores["PUMPED"]
    assert scores["DUMPED"] > scores["DRIFT"]


def test_score_matrix_risk_adjusted_momentum_ensemble_blends_ranked_horizons() -> None:
    cfg = OhlcvConfig(
        lookback_h=12,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="risk_adj_mom_ensemble",
        market_filter_h=0,
        vol_target_ann=0.0,
    )

    scores = score_matrix(close_matrix(80), cfg)
    late = scores.iloc[-1].dropna()

    assert list(scores.columns) == ["AAA", "BBB", "CCC", "DDD"]
    assert len(late) == 4
    assert late.max() <= 0.5
    assert late.min() >= -0.5
    assert late["AAA"] > late["CCC"]


def test_score_matrix_momentum_reversal_blend_rewards_pullbacks() -> None:
    dt = pd.date_range("2020-01-01", periods=160, freq="1h", tz="UTC")
    data = pd.DataFrame(
        {
            "dt": dt,
            "TREND_PULLBACK": [100 + idx * 1.0 - max(0, idx - 120) * 1.4 for idx in range(160)],
            "HOT_TREND": [100 + idx * 0.9 + max(0, idx - 120) * 1.0 for idx in range(160)],
            "WEAK": [100 - idx * 0.2 for idx in range(160)],
            "FLAT": [100.0] * 160,
        }
    )
    cfg = OhlcvConfig(
        lookback_h=96,
        skip_h=0,
        rebalance_h=24,
        k=2,
        score_mode="mom_reversal_blend",
        market_filter_h=0,
        vol_target_ann=0.0,
    )

    blended = score_matrix(data, cfg).dropna(how="all").iloc[-1]

    assert set(blended.index) == {"TREND_PULLBACK", "HOT_TREND", "WEAK", "FLAT"}
    assert blended["TREND_PULLBACK"] > blended["HOT_TREND"]
    assert blended["TREND_PULLBACK"] > blended["WEAK"]


def test_market_filter_turns_off_when_market_momentum_is_negative() -> None:
    data = close_matrix()
    data["AAA"] = list(reversed(data["AAA"].tolist()))
    data["BBB"] = list(reversed(data["BBB"].tolist()))
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=2, k=2, score_mode="mom", market_filter_h=4, vol_target_ann=0.0)
    allowed = market_filter(data, cfg)
    assert not bool(allowed.iloc[-1])


def test_market_filter_requires_shorter_confirmation_when_configured() -> None:
    data = regime_rollover_matrix()
    base = OhlcvConfig(lookback_h=8, skip_h=0, rebalance_h=4, k=2, score_mode="mom", market_filter_h=20, vol_target_ann=0.0)
    guarded = OhlcvConfig(
        lookback_h=8,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="mom",
        market_filter_h=20,
        vol_target_ann=0.0,
        market_confirm_h=4,
    )

    assert bool(market_filter(data, base).iloc[-1])
    assert not bool(market_filter(data, guarded).iloc[-1])


def test_market_filter_blocks_large_market_drawdown() -> None:
    data = market_drawdown_matrix()
    base = OhlcvConfig(lookback_h=20, skip_h=0, rebalance_h=4, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    guarded = OhlcvConfig(
        lookback_h=20,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        market_drawdown_limit=0.20,
    )

    assert bool(market_filter(data, base).iloc[-1])
    assert not bool(market_filter(data, guarded).iloc[-1])


def test_simulate_reports_gate_inputs() -> None:
    cfg = OhlcvConfig(lookback_h=4, skip_h=0, rebalance_h=4, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    result20 = simulate(close_matrix(120), cfg, cost_bps=20.0, bootstrap_iterations=10)
    result40 = simulate(close_matrix(120), cfg, cost_bps=40.0, bootstrap_iterations=10)
    checks = advance_checks(result20, result40)
    assert "equal_weight_benchmark" in result20
    assert "bootstrap_p5_ge_adjusted_min" in checks
    assert result20["daily_turnover"] >= 0
    assert result20["time_in_market_frac"] >= 0
    assert result20["max_flat_streak_h"] >= 0
    assert result20["active_rebalance_event_count"] >= 0
    assert result20["rebalance_offsets_h"] == [0]
    assert result20["avg_long_exposure"] >= 0
    assert result20["avg_short_exposure"] == 0
    assert result20["legs"]["avg_long_exposure"] == result20["avg_long_exposure"]
    assert result20["legs"]["short_gross_return"] == 0


def test_selection_and_validation_gates_reject_high_turnover() -> None:
    low_turnover = passing_gate_result(daily_turnover=0.10)
    high_turnover = passing_gate_result(daily_turnover=0.75)

    assert advance_checks(low_turnover, low_turnover, bootstrap_p5_min=0.25)["daily_turnover40_le_50pct"] is True
    assert advance_checks(low_turnover, high_turnover, bootstrap_p5_min=0.25)["daily_turnover40_le_50pct"] is False
    assert validation_checks(low_turnover, low_turnover, sharpe20_min=0.70)["validation_daily_turnover40_le_50pct"] is True
    assert validation_checks(low_turnover, high_turnover, sharpe20_min=0.70)["validation_daily_turnover40_le_50pct"] is False


def test_selection_and_validation_gates_reject_insufficient_activity() -> None:
    active = passing_gate_result(active_rebalance_event_count=20, time_in_market_frac=0.20)
    inactive = passing_gate_result(active_rebalance_event_count=1, time_in_market_frac=0.01)

    selection = advance_checks(active, inactive, bootstrap_p5_min=0.25)
    validation = validation_checks(active, inactive, sharpe20_min=0.70)

    assert selection["active_rebalances40_ge_min"] is False
    assert selection["time_in_market40_ge_min"] is False
    assert validation["validation_active_rebalances40_ge_min"] is False
    assert validation["validation_time_in_market40_ge_min"] is False


def test_selection_gate_can_require_2022_return_floor() -> None:
    weak_2022 = passing_gate_result()
    weak_2022["yearly"]["2022"]["net_return"] = -0.05
    strong_2022 = passing_gate_result()
    strong_2022["yearly"]["2022"]["net_return"] = 0.01

    assert "return_2022_ge_min" not in advance_checks(weak_2022, weak_2022, bootstrap_p5_min=0.25)
    assert advance_checks(
        weak_2022,
        weak_2022,
        bootstrap_p5_min=0.25,
        min_2022_return=-0.02,
    )["return_2022_ge_min"] is False
    assert advance_checks(
        strong_2022,
        strong_2022,
        bootstrap_p5_min=0.25,
        min_2022_return=-0.02,
    )["return_2022_ge_min"] is True


def test_validation_gate_can_require_2024h1_trading_activity() -> None:
    inactive_recent = passing_gate_result()
    inactive_recent["yearly"]["2024H1"]["periods"] = 0
    active_recent = passing_gate_result()
    active_recent["yearly"]["2024H1"]["periods"] = 3

    assert "validation_periods_2024h1_ge_min" not in validation_checks(
        inactive_recent,
        inactive_recent,
        sharpe20_min=0.70,
    )
    assert validation_checks(
        inactive_recent,
        inactive_recent,
        sharpe20_min=0.70,
        min_2024h1_periods=1,
    )["validation_periods_2024h1_ge_min"] is False
    assert validation_checks(
        active_recent,
        active_recent,
        sharpe20_min=0.70,
        min_2024h1_periods=1,
    )["validation_periods_2024h1_ge_min"] is True


def test_activity_gates_can_reject_long_flat_streaks() -> None:
    active = passing_gate_result(active_rebalance_event_count=20, time_in_market_frac=0.70)
    active["max_flat_streak_h"] = 24
    inactive = {**active, "max_flat_streak_h": 60}

    selection = advance_checks(active, inactive, bootstrap_p5_min=0.25, max_flat_streak_h=48)
    validation = validation_checks(active, inactive, sharpe20_min=0.70, max_flat_streak_h=48)

    assert selection["max_flat_streak40_le_limit"] is False
    assert validation["validation_max_flat_streak40_le_limit"] is False


def test_simulate_reports_market_regime_diagnostics() -> None:
    cfg = OhlcvConfig(
        lookback_h=8,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="mom",
        market_filter_h=20,
        vol_target_ann=0.0,
        market_confirm_h=4,
        market_drawdown_limit=0.25,
    )
    result = simulate(regime_rollover_matrix(120), cfg, cost_bps=20.0, bootstrap_iterations=0)

    regime = result["market_regime"]
    assert regime["primary_filter_h"] == 20
    assert regime["confirm_h"] == 4
    assert regime["drawdown_limit"] == 0.25
    assert 0.0 <= regime["allowed_frac"] <= 1.0
    assert regime["allowed_frac"] <= regime["primary_allowed_frac"]
    attribution = result["regime_attribution"]
    assert attribution["trend_filter_h"] == 20
    assert -5.0 <= attribution["beta_to_equal_weight"] <= 5.0
    assert 0.99 <= attribution["above_trend_hour_frac"] + attribution["below_trend_hour_frac"] <= 1.01
    assert attribution["above_trend_avg_gross_exposure"] >= 0.0
    assert attribution["below_trend_avg_gross_exposure"] >= 0.0


def test_simulate_long_short_portfolio_reports_short_leg() -> None:
    cfg = OhlcvConfig(
        lookback_h=4,
        skip_h=0,
        rebalance_h=4,
        k=1,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        portfolio_mode="long_short",
    )

    result = simulate(close_matrix(120), cfg, cost_bps=20.0, bootstrap_iterations=0)

    assert result["avg_long_exposure"] > 0.0
    assert result["avg_short_exposure"] > 0.0
    assert abs(result["avg_long_exposure"] - result["avg_short_exposure"]) < 1e-9
    assert result["legs"]["avg_short_exposure"] > 0.0


def test_simulate_drawdown_stop_forces_flat_and_charges_exit_cost() -> None:
    cfg = OhlcvConfig(
        lookback_h=8,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        drawdown_stop=0.05,
        cooldown_h=12,
    )

    result = simulate(crash_matrix(), cfg, cost_bps=20.0, bootstrap_iterations=0)

    assert result["risk_off_event_count"] >= 1
    assert result["risk_off_hours"] >= 12
    assert result["risk_off_max_gross_exposure"] == 0.0
    assert result["risk_stop_exit_turnover"] > 0.0
    assert result["risk_stop_exit_cost"] > 0.0


def test_simulate_drawdown_stop_rearms_after_cooldown_without_self_locking() -> None:
    cfg = OhlcvConfig(
        lookback_h=8,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        drawdown_stop=0.05,
        cooldown_h=12,
    )

    result = simulate(crash_matrix(144), cfg, cost_bps=20.0, bootstrap_iterations=0)

    assert result["risk_off_event_count"] == 1
    assert result["risk_off_hours"] == 12
    assert result["time_in_market_frac"] > 0.80
    assert result["max_flat_streak_h"] <= 16


def test_simulate_drawdown_stop_zero_disables_risk_off() -> None:
    cfg = OhlcvConfig(
        lookback_h=8,
        skip_h=0,
        rebalance_h=4,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        drawdown_stop=0.0,
        cooldown_h=12,
    )

    result = simulate(crash_matrix(), cfg, cost_bps=20.0, bootstrap_iterations=0)

    assert result["risk_off_event_count"] == 0
    assert result["risk_off_hours"] == 0
    assert result["risk_stop_exit_cost"] == 0.0


def test_tranche_one_matches_default_single_phase() -> None:
    data = close_matrix(240)
    base = OhlcvConfig(lookback_h=12, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    explicit = OhlcvConfig(
        lookback_h=12,
        skip_h=0,
        rebalance_h=12,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        n_tranches=1,
    )

    assert simulate(data, base, cost_bps=20.0, bootstrap_iterations=10) == simulate(data, explicit, cost_bps=20.0, bootstrap_iterations=10)


def test_phase_offset_shifts_single_tranche_rebalance_start() -> None:
    data = close_matrix(240)
    cfg = OhlcvConfig(lookback_h=12, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)

    default_result = simulate(data, cfg, cost_bps=20.0, bootstrap_iterations=10)
    offset_result = simulate(data, cfg, cost_bps=20.0, bootstrap_iterations=10, phase_offset_h=4)

    assert default_result["rebalance_offsets_h"] == [0]
    assert default_result["phase_offset_h"] == 0
    assert offset_result["rebalance_offsets_h"] == [4]
    assert offset_result["phase_offset_h"] == 4


def test_tranched_rebalancing_uses_staggered_offsets() -> None:
    data = close_matrix(240)
    single = OhlcvConfig(lookback_h=12, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    tranched = OhlcvConfig(
        lookback_h=12,
        skip_h=0,
        rebalance_h=12,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        n_tranches=3,
    )

    single_result = simulate(data, single, cost_bps=20.0, bootstrap_iterations=10)
    tranched_result = simulate(data, tranched, cost_bps=20.0, bootstrap_iterations=10)

    assert tranched_result["rebalance_offsets_h"] == [0, 4, 8]
    assert tranched_result["rebalance_event_count"] > single_result["rebalance_event_count"]
    assert tranched_result["avg_gross_exposure"] <= single_result["avg_gross_exposure"]


def test_split_selection_validation_keeps_validation_after_purge() -> None:
    cfg = OhlcvConfig(lookback_h=24, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=48, vol_target_ann=0.0)
    selection, validation, meta = split_selection_validation(close_matrix(1400), cfg)
    assert len(selection) > 0
    assert len(validation) > 0
    assert pd.Timestamp(validation["dt"].iloc[0]) > pd.Timestamp(selection["dt"].iloc[-1])
    assert meta["purge_hours"] == 48
    assert meta["validation_usable"] is True


def test_walk_forward_summary_reports_cross_sectional_fold_metrics() -> None:
    cfg = OhlcvConfig(lookback_h=24, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    summary = walk_forward_summary(
        close_matrix(900),
        cfg,
        cost_bps=0.0,
        folds=3,
        min_q25_sharpe=-99.0,
        min_sign_consistency=0.0,
    )
    assert summary["enabled"] is True
    assert summary["fold_count"] == 3
    assert summary["passed"] is True
    assert {row["fold"] for row in summary["folds"]} == {0, 1, 2}
    assert "median_long_gross_sharpe" in summary
    assert "median_short_gross_sharpe" in summary
    assert "regime_attribution" in summary["folds"][0]
    assert "beta_to_equal_weight" in summary["folds"][0]["regime_attribution"]


def test_walk_forward_summary_allows_bounded_loss_consistency(monkeypatch) -> None:
    cfg = OhlcvConfig(lookback_h=24, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    fold_results = iter(
        [
            {"sharpe": 4.0, "total_return": 0.40, "max_drawdown": 0.06},
            {"sharpe": 2.0, "total_return": 0.20, "max_drawdown": 0.08},
            {"sharpe": 1.9, "total_return": 0.15, "max_drawdown": 0.09},
            {"sharpe": 1.5, "total_return": 0.10, "max_drawdown": 0.10},
            {"sharpe": -0.2, "total_return": -0.02, "max_drawdown": 0.11},
            {"sharpe": -0.1, "total_return": -0.03, "max_drawdown": 0.12},
        ]
    )

    def fake_simulate(frame, cfg, cost_bps, bootstrap_iterations=0):
        row = dict(next(fold_results))
        row["daily_turnover"] = 0.02
        row["legs"] = {
            "long_gross_sharpe": 1.0,
            "short_gross_sharpe": 0.0,
            "long_gross_return": 0.1,
            "short_gross_return": 0.0,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
        }
        return row

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    summary = walk_forward_summary(close_matrix(1440), cfg, folds=6)
    assert summary["strict_consistency_passed"] is False
    assert summary["bounded_loss_consistency_passed"] is True
    assert summary["checks"]["wf_consistency_ge_min_or_bounded_loss"] is True
    assert summary["passed"] is True


def test_walk_forward_summary_rejects_unbounded_fold_loss(monkeypatch) -> None:
    cfg = OhlcvConfig(lookback_h=24, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    fold_results = iter(
        [
            {"sharpe": 4.0, "total_return": 0.40, "max_drawdown": 0.06},
            {"sharpe": 2.0, "total_return": 0.20, "max_drawdown": 0.08},
            {"sharpe": 1.9, "total_return": 0.15, "max_drawdown": 0.09},
            {"sharpe": 1.5, "total_return": 0.10, "max_drawdown": 0.10},
            {"sharpe": -0.2, "total_return": -0.02, "max_drawdown": 0.11},
            {"sharpe": -0.1, "total_return": -0.08, "max_drawdown": 0.12},
        ]
    )

    def fake_simulate(frame, cfg, cost_bps, bootstrap_iterations=0):
        row = dict(next(fold_results))
        row["daily_turnover"] = 0.02
        row["legs"] = {
            "long_gross_sharpe": 1.0,
            "short_gross_sharpe": 0.0,
            "long_gross_return": 0.1,
            "short_gross_return": 0.0,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
        }
        return row

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    summary = walk_forward_summary(close_matrix(1440), cfg, folds=6)
    assert summary["bounded_loss_consistency_passed"] is False
    assert summary["checks"]["wf_consistency_ge_min_or_bounded_loss"] is False
    assert summary["passed"] is False


def test_walk_forward_summary_uses_overlay_gate_for_hedged_long(monkeypatch) -> None:
    cfg = OhlcvConfig(
        lookback_h=24,
        skip_h=0,
        rebalance_h=12,
        k=2,
        score_mode="mom",
        market_filter_h=0,
        vol_target_ann=0.0,
        portfolio_mode="hedged_long",
        hedge_ratio=0.5,
    )
    hedged_results = [
        {"sharpe": 3.0, "total_return": 0.20, "max_drawdown": 0.07},
        {"sharpe": 2.0, "total_return": 0.20, "max_drawdown": 0.08},
        {"sharpe": 0.5, "total_return": 0.03, "max_drawdown": 0.10},
        {"sharpe": -0.1, "total_return": -0.004, "max_drawdown": 0.06},
        {"sharpe": 0.5, "total_return": 0.02, "max_drawdown": 0.05},
        {"sharpe": 1.0, "total_return": 0.10, "max_drawdown": 0.08},
    ]
    unhedged_results = [
        {"sharpe": 4.0, "total_return": 0.40, "max_drawdown": 0.06},
        {"sharpe": 0.2, "total_return": 0.02, "max_drawdown": 0.10},
        {"sharpe": 0.2, "total_return": 0.01, "max_drawdown": 0.11},
        {"sharpe": -0.1, "total_return": -0.008, "max_drawdown": 0.09},
        {"sharpe": 0.5, "total_return": 0.03, "max_drawdown": 0.07},
        {"sharpe": 1.4, "total_return": 0.26, "max_drawdown": 0.10},
    ]
    fold_results = iter(value for pair in zip(hedged_results, unhedged_results) for value in pair)

    def fake_simulate(frame, cfg, cost_bps, bootstrap_iterations=0):
        row = dict(next(fold_results))
        row["daily_turnover"] = 0.02
        if cfg.portfolio_mode == "hedged_long":
            row["legs"] = {
                "long_gross_sharpe": 1.0,
                "short_gross_sharpe": -0.2,
                "long_gross_return": 0.1,
                "short_gross_return": -0.01,
                "avg_long_exposure": 1.0,
                "avg_short_exposure": 0.5,
            }
        else:
            row["legs"] = {
                "long_gross_sharpe": row["sharpe"],
                "short_gross_sharpe": 0.0,
                "long_gross_return": row["total_return"],
                "short_gross_return": 0.0,
                "avg_long_exposure": 1.0,
                "avg_short_exposure": 0.0,
            }
        return row

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    summary = walk_forward_summary(close_matrix(1440), cfg, folds=6)
    assert summary["median_short_gross_sharpe"] < 0.0
    assert "wf_median_short_leg_sharpe_ge_0" not in summary["checks"]
    assert summary["checks"]["wf_hedged_dd_improves_half_folds"] is True
    assert summary["checks"]["wf_net_median_sharpe_retains_80pct_long_only"] is True
    assert summary["passed"] is True


def test_leave_one_symbol_summary_reports_each_symbol_drop() -> None:
    cfg = OhlcvConfig(lookback_h=24, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=0, vol_target_ann=0.0)
    summary = leave_one_symbol_summary(close_matrix(600), cfg, cost_bps=0.0, min_sharpe=-99.0)
    assert summary["enabled"] is True
    assert len(summary["rows"]) == 4
    assert {row["dropped_symbol"] for row in summary["rows"]} == {"AAA", "BBB", "CCC", "DDD"}
    assert summary["worst_drop"]["dropped_symbol"] in {"AAA", "BBB", "CCC", "DDD"}


def test_trial_adjusted_thresholds_tighten_with_prior_trials() -> None:
    assert bootstrap_threshold(16 + 500) > bootstrap_threshold(16)
    assert validation_sharpe_threshold(10) == 0.70
    assert validation_sharpe_threshold(1000) > validation_sharpe_threshold(10)


def test_progress_meta_records_prior_and_effective_trials(tmp_path) -> None:
    cfg = RunConfig(prior_trials=123)
    path = tmp_path / "case.progress.meta.json"

    write_progress_meta(
        path,
        total_rows=10,
        completed_rows=4,
        closes_fingerprint="fp",
        cfg=cfg,
        bootstrap_p5_min=0.30,
        validation_sharpe20_min=1.10,
        confirm_iterations=500,
        progress_rows=[
            {
                "config": {"lookback_h": 24},
                "advance_passed": False,
                "cost20": {"sharpe": 0.5, "total_return": 0.01, "max_drawdown": 0.2},
                "selection": {"checks": {"bootstrap_p5_ge_adjusted_min": False}},
                "validation": {"cost20": {}},
                "walk_forward": {"q25_sharpe": -0.1},
                "advance_checks": {"bootstrap_p5_ge_adjusted_min": False, "validation_usable": True},
            },
            {
                "config": {"lookback_h": 48},
                "advance_passed": True,
                "cost20": {"sharpe": 1.8, "total_return": 0.20, "max_drawdown": 0.08},
                "selection": {"checks": {"bootstrap_p5_ge_adjusted_min": True}},
                "validation": {"cost20": {"sharpe": 1.2, "total_return": 0.06, "max_drawdown": 0.05}},
                "walk_forward": {"q25_sharpe": 0.7},
                "advance_checks": {"bootstrap_p5_ge_adjusted_min": True, "validation_usable": True},
            },
        ],
    )

    payload = json.loads(path.read_text())
    assert payload["prior_trials"] == 123
    assert payload["effective_trials"] == 133
    assert payload["total_rows"] == 10
    assert payload["completed_rows"] == 4
    assert payload["diagnostics"]["pass_count_so_far"] == 1
    assert payload["diagnostics"]["selection_pass_count_so_far"] == 1
    assert payload["diagnostics"]["validated_row_count_so_far"] == 1
    assert payload["diagnostics"]["failed_check_counts"] == {"bootstrap_p5_ge_adjusted_min": 1}
    assert payload["diagnostics"]["best_so_far"]["config"] == {"lookback_h": 48}
    assert payload["diagnostics"]["best_passed_so_far"]["config"] == {"lookback_h": 48}


def test_gate_alignment_prefers_near_gate_rows_over_raw_sharpe() -> None:
    near20 = passing_gate_result()
    near20["max_flat_streak_h"] = 12
    near40 = json.loads(json.dumps(near20))
    near40["sharpe"] = 1.1
    near_checks = advance_checks(near20, near40, bootstrap_p5_min=0.25, max_flat_streak_h=48)
    near_checks["walk_forward_robust"] = False
    near_row = {
        "advance_passed": False,
        "cost20": near20,
        "cost40": near40,
        "validation": {"cost20": near20, "cost40": near40},
        "walk_forward": {"q25_sharpe": -0.10},
        "advance_checks": near_checks,
    }

    weak20 = passing_gate_result()
    weak20.update(
        {
            "sharpe": 4.0,
            "max_drawdown": 0.48,
            "yearly_positive_count": 1,
            "bootstrap_30d_sharpe_p5": 0.05,
            "top_positive_symbol_share": 0.92,
            "max_flat_streak_h": 300,
        }
    )
    weak20["yearly"]["2024H1"]["net_return"] = -0.08
    weak20["equal_weight_benchmark"] = {"sharpe_excess": -0.20, "drawdown_ratio": 1.40}
    weak40 = json.loads(json.dumps(weak20))
    weak40.update(
        {
            "sharpe": 0.20,
            "active_rebalance_event_count": 1,
            "time_in_market_frac": 0.01,
            "max_flat_streak_h": 300,
        }
    )
    weak_checks = advance_checks(weak20, weak40, bootstrap_p5_min=0.25, max_flat_streak_h=48)
    weak_checks["walk_forward_robust"] = False
    weak_row = {
        "advance_passed": False,
        "cost20": weak20,
        "cost40": weak40,
        "validation": {"cost20": weak20, "cost40": weak40},
        "walk_forward": {"q25_sharpe": 0.90},
        "advance_checks": weak_checks,
    }

    assert weak20["sharpe"] > near20["sharpe"]
    assert gate_alignment_summary(near_row)["score"] > gate_alignment_summary(weak_row)["score"]
    assert progress_row_sort_key(near_row) > progress_row_sort_key(weak_row)


def test_bootstrap_seed_is_stable_and_segment_specific() -> None:
    cfg = OhlcvConfig(lookback_h=24, skip_h=0, rebalance_h=12, k=2, score_mode="mom", market_filter_h=48, vol_target_ann=0.0)
    first = bootstrap_seed(cfg, 20.0, "selection", "2020-01-01", "2021-01-01")
    assert first == bootstrap_seed(cfg, 20.0, "selection", "2020-01-01", "2021-01-01")
    assert first != bootstrap_seed(cfg, 20.0, "selection_confirm", "2020-01-01", "2021-01-01")
    assert first != bootstrap_seed(cfg, 40.0, "selection", "2020-01-01", "2021-01-01")


def test_data_fingerprint_is_stable_and_sensitive() -> None:
    closes = close_matrix(600)
    assert data_fingerprint(closes) == data_fingerprint(closes.copy())
    perturbed = closes.copy()
    perturbed["AAA"] = perturbed["AAA"].astype(float)
    perturbed.iloc[100, 1] += 1e-9
    assert data_fingerprint(perturbed) != data_fingerprint(closes)


def test_run_grid_payload_pins_data_fingerprint(monkeypatch, tmp_path) -> None:
    closes = close_matrix(600)

    def fake_load_close_matrix(cache_dir, symbols, start, end, embargo):
        return closes

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", fake_load_close_matrix)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )
    payload = run_grid(cfg)
    assert payload["data"]["fingerprint"] == data_fingerprint(closes)
    assert payload["data"]["rows"] == len(closes)
    assert payload["selection_validation"]["walk_forward_required"] is True
    assert payload["selection_validation"]["leave_one_symbol_required"] is True
    assert "walk_forward" in payload["top"][0]
    assert "diagnostic_walk_forward" in payload["top"][0]
    assert "leave_one_symbol" in payload["top"][0]
    assert not progress_meta_path_for(cfg.out_json).exists()


def test_run_grid_can_reuse_pinned_data_snapshot(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    closes = close_matrix(600)

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: closes)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )
    payload = run_grid(cfg)
    snapshot_path = Path(payload["data"]["snapshot"]["path"])
    assert snapshot_path.exists()
    assert payload["data"]["snapshot"]["fingerprint"] == data_fingerprint(closes)

    def fail_live_cache(*args):
        raise AssertionError("pinned snapshot run should not read live cache")

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", fail_live_cache)
    snap_cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        data_snapshot=str(snapshot_path),
        out_json=str(tmp_path / "snap.json"),
        out_md="",
    )
    snap_payload = run_grid(snap_cfg)
    assert snap_payload["data"]["fingerprint"] == payload["data"]["fingerprint"]
    assert snap_payload["data"]["snapshot"]["source"] == "pinned_data_snapshot"


def test_data_snapshot_detects_metadata_fingerprint_mismatch(tmp_path) -> None:
    closes = close_matrix(600)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        data_snapshot="",
    )
    fingerprint = data_fingerprint(closes)
    snapshot_path = data_snapshot_path_for(cfg, fingerprint)
    snapshot_path = tmp_path / snapshot_path.name
    closes.to_parquet(snapshot_path, index=False)
    snapshot_path.with_suffix(snapshot_path.suffix + ".json").write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_data_snapshot_v1",
                "fingerprint": "wrong",
                "train_start": cfg.train_start,
                "train_end": cfg.train_end,
                "embargo_start": cfg.embargo_start,
                "symbols": list(cfg.symbols),
            }
        )
    )

    try:
        read_data_snapshot(snapshot_path, cfg)
    except ValueError as exc:
        assert "fingerprint mismatch" in str(exc)
    else:
        raise AssertionError("expected snapshot fingerprint mismatch")


def test_validate_all_rows_can_run_diagnostic_walk_forward_without_passing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: close_matrix(1200))

    def fake_simulate(
        closes,
        cfg,
        cost_bps,
        bootstrap_iterations=500,
        bootstrap_seed_value=20260707,
        bootstrap_confirm_iterations=0,
        bootstrap_confirm_seed_value=None,
    ):
        return {
            "config": {
                "lookback_h": cfg.lookback_h,
                "skip_h": cfg.skip_h,
                "rebalance_h": cfg.rebalance_h,
                "k": cfg.k,
                "score_mode": cfg.score_mode,
                "market_filter_h": cfg.market_filter_h,
                "vol_target_ann": cfg.vol_target_ann,
                "n_tranches": cfg.n_tranches,
            },
            "cost_bps": float(cost_bps),
            "total_return": 0.20,
            "net_pnl": 2000.0,
            "sharpe": 1.6,
            "max_drawdown": 0.10,
            "daily_turnover": 0.01,
            "avg_gross_exposure": 1.0,
            "time_in_market_frac": 1.0,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
            "avg_rebalance_scale": 1.0,
            "rebalance_event_count": 20,
            "active_rebalance_event_count": 20,
            "yearly": {
                "2021": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2022": {"periods": 10, "net_return": -0.01, "sharpe": -0.2},
                "2023": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2024H1": {"periods": 10, "net_return": -0.01, "sharpe": -0.2},
            },
            "yearly_positive_count": 2,
            "symbol_pnl": {"AAA": 1000.0, "BBB": 900.0, "CCC": 200.0, "DDD": 100.0},
            "top_positive_symbol_share": 0.45,
            "bootstrap_30d_sharpe_p5": 0.80,
            "bootstrap_seed": int(bootstrap_seed_value),
            "bootstrap_iterations": int(bootstrap_iterations),
            "legs": {
                "long_gross_return": 0.20,
                "long_gross_sharpe": 1.6,
                "short_gross_return": 0.0,
                "short_gross_sharpe": 0.0,
                "avg_long_exposure": 1.0,
                "avg_short_exposure": 0.0,
            },
            "equal_weight_benchmark": {
                "sharpe": 0.8,
                "max_drawdown": 0.20,
                "sharpe_excess": 0.80,
                "drawdown_ratio": 0.50,
            },
        }

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        validate_all_rows=True,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )
    payload = run_grid(cfg)
    row = payload["rows"][0]
    assert row["selection"]["checks"]["positive_3_of_4_years"] is False
    assert row["validation"]["checks"]["validation_sharpe20_ge_adjusted_min"] is True
    assert row["diagnostic_walk_forward"]["diagnostic_only"] is True
    assert row["diagnostic_walk_forward"]["triggered"] is True
    assert row["diagnostic_walk_forward"]["q25_sharpe"] == 1.6
    assert row["advance_passed"] is False
    assert payload["summary"]["pass_count"] == 0


def tiny_grid_config(tmp_path) -> RunConfig:
    return RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24, 48),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )


def test_run_grid_resumes_all_rows_from_progress(monkeypatch, tmp_path) -> None:
    closes = close_matrix(600)
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: closes)
    cfg = tiny_grid_config(tmp_path)
    first = run_grid(cfg)
    progress_path = progress_path_for(cfg.out_json)
    assert not progress_path.exists()
    assert not progress_meta_path_for(cfg.out_json).exists()
    for row in first["rows"]:
        append_progress_row(progress_path, row["row_cache_key"], row)

    def fail_simulate(*args, **kwargs):
        raise AssertionError("cached rows should not call simulate")

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fail_simulate)
    second = run_grid(cfg)
    assert second["rows"] == first["rows"]
    assert not progress_path.exists()
    assert not progress_meta_path_for(cfg.out_json).exists()


def test_progress_key_mismatch_forces_recompute(monkeypatch, tmp_path) -> None:
    closes = close_matrix(600)
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: closes)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )
    bad_row = {"row_cache_key": "bad", "config": {"lookback_h": 24}, "cost20": {"sharpe": 999.0}}
    append_progress_row(progress_path_for(cfg.out_json), "wrong-key", bad_row)
    calls = {"n": 0}
    original_simulate = simulate

    def counting_simulate(*args, **kwargs):
        calls["n"] += 1
        return original_simulate(*args, **kwargs)

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", counting_simulate)
    payload = run_grid(cfg)
    assert calls["n"] > 0
    assert payload["rows"][0]["row_cache_key"] != "bad"


def test_run_grid_confirm_gate_can_reject_initial_bootstrap_pass(monkeypatch, tmp_path) -> None:
    def fake_load_close_matrix(cache_dir, symbols, start, end, embargo):
        return close_matrix(600)

    def fake_simulate(
        closes,
        cfg,
        cost_bps,
        bootstrap_iterations=500,
        bootstrap_seed_value=20260707,
        bootstrap_confirm_iterations=0,
        bootstrap_confirm_seed_value=None,
    ):
        result = {
            "config": {
                "lookback_h": cfg.lookback_h,
                "skip_h": cfg.skip_h,
                "rebalance_h": cfg.rebalance_h,
                "k": cfg.k,
                "score_mode": cfg.score_mode,
                "market_filter_h": cfg.market_filter_h,
                "vol_target_ann": cfg.vol_target_ann,
            },
            "cost_bps": float(cost_bps),
            "total_return": 0.20,
            "net_pnl": 2000.0,
            "sharpe": 1.5,
            "max_drawdown": 0.10,
            "daily_turnover": 0.01,
            "avg_gross_exposure": 1.0,
            "time_in_market_frac": 1.0,
            "avg_rebalance_scale": 1.0,
            "rebalance_event_count": 20,
            "active_rebalance_event_count": 20,
            "yearly": {
                "2021": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2022": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2023": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2024H1": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
            },
            "yearly_positive_count": 4,
            "symbol_pnl": {"AAA": 1000.0, "BBB": 900.0, "CCC": 0.0, "DDD": 0.0},
            "top_positive_symbol_share": 0.52,
            "bootstrap_30d_sharpe_p5": 0.50,
            "bootstrap_seed": int(bootstrap_seed_value),
            "bootstrap_iterations": int(bootstrap_iterations),
            "equal_weight_benchmark": {
                "sharpe": 0.8,
                "max_drawdown": 0.20,
                "sharpe_excess": 0.20,
                "drawdown_ratio": 0.50,
            },
        }
        if bootstrap_confirm_iterations:
            result["bootstrap_30d_sharpe_p5_confirm"] = 0.0
            result["bootstrap_confirm_seed"] = int(bootstrap_confirm_seed_value)
            result["bootstrap_confirm_iterations"] = int(bootstrap_confirm_iterations)
        return result

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", fake_load_close_matrix)
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )
    payload = run_grid(cfg)
    row = payload["rows"][0]
    assert row["selection"]["checks"]["bootstrap_p5_ge_adjusted_min"] is True
    assert row["selection"]["checks"]["bootstrap_p5_confirm_ge_adjusted_min"] is False
    assert row["advance_passed"] is False
    assert payload["summary"]["pass_count"] == 0


def test_run_grid_prefilter_skips_bootstrap_when_cheap_selection_gate_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: close_matrix(1600))

    calls: list[dict[str, float]] = []

    def fake_simulate(
        closes,
        cfg,
        cost_bps,
        bootstrap_iterations=500,
        bootstrap_seed_value=20260707,
        bootstrap_confirm_iterations=0,
        bootstrap_confirm_seed_value=None,
    ):
        calls.append(
            {
                "cost_bps": float(cost_bps),
                "bootstrap_iterations": int(bootstrap_iterations),
                "bootstrap_confirm_iterations": int(bootstrap_confirm_iterations),
            }
        )
        return {
            "config": {
                "lookback_h": cfg.lookback_h,
                "skip_h": cfg.skip_h,
                "rebalance_h": cfg.rebalance_h,
                "k": cfg.k,
                "score_mode": cfg.score_mode,
                "market_filter_h": cfg.market_filter_h,
                "vol_target_ann": cfg.vol_target_ann,
            },
            "cost_bps": float(cost_bps),
            "total_return": 0.20,
            "net_pnl": 2000.0,
            "sharpe": 1.8,
            "max_drawdown": 0.10,
            "daily_turnover": 0.01,
            "avg_gross_exposure": 1.0,
            "time_in_market_frac": 0.80,
            "max_flat_streak_h": 12,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
            "avg_rebalance_scale": 1.0,
            "rebalance_event_count": 20,
            "active_rebalance_event_count": 20,
            "yearly": {
                "2021": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2022": {"periods": 10, "net_return": -0.05, "sharpe": -1.0},
                "2023": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2024H1": {"periods": 10, "net_return": 0.00, "sharpe": 0.0},
            },
            "yearly_positive_count": 2,
            "symbol_pnl": {"AAA": 1000.0, "BBB": 900.0, "CCC": 200.0, "DDD": 100.0},
            "top_positive_symbol_share": 0.45,
            "bootstrap_30d_sharpe_p5": 0.0,
            "bootstrap_seed": int(bootstrap_seed_value),
            "bootstrap_iterations": int(bootstrap_iterations),
            "legs": {
                "long_gross_return": 0.20,
                "long_gross_sharpe": 1.6,
                "short_gross_return": 0.0,
                "short_gross_sharpe": 0.0,
                "avg_long_exposure": 1.0,
                "avg_short_exposure": 0.0,
            },
            "equal_weight_benchmark": {
                "sharpe": 0.8,
                "max_drawdown": 0.20,
                "sharpe_excess": 0.80,
                "drawdown_ratio": 0.50,
            },
        }

    def fail_walk_forward(*args, **kwargs):
        raise AssertionError("cheap selection failures should not run walk-forward")

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.walk_forward_summary", fail_walk_forward)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )

    payload = run_grid(cfg)
    row = payload["rows"][0]

    assert {call["bootstrap_iterations"] for call in calls} == {0}
    assert all(call["bootstrap_confirm_iterations"] == 0 for call in calls)
    assert row["selection_prefilter"]["passed"] is False
    assert row["selection_prefilter"]["skipped_bootstrap"] is True
    assert row["selection_prefilter"]["bootstrap_check_skipped"] is True
    assert row["selection"]["checks"]["positive_3_of_4_years"] is False
    assert "bootstrap_p5_ge_adjusted_min" not in row["selection"]["checks"]
    assert row["validation"]["checks"]["selection_passed_before_validation"] is False
    assert row["advance_passed"] is False
    assert payload["selection_validation"]["selection_prefilter_enabled"] is True
    assert payload["summary"]["pass_count"] == 0


def test_run_grid_requires_acceptance_level_validation_activity(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: close_matrix(1600))

    def fake_simulate(
        closes,
        cfg,
        cost_bps,
        bootstrap_iterations=500,
        bootstrap_seed_value=20260707,
        bootstrap_confirm_iterations=0,
        bootstrap_confirm_seed_value=None,
    ):
        result = {
            "config": {
                "lookback_h": cfg.lookback_h,
                "skip_h": cfg.skip_h,
                "rebalance_h": cfg.rebalance_h,
                "k": cfg.k,
                "score_mode": cfg.score_mode,
                "market_filter_h": cfg.market_filter_h,
                "vol_target_ann": cfg.vol_target_ann,
                "n_tranches": cfg.n_tranches,
            },
            "cost_bps": float(cost_bps),
            "total_return": 0.20,
            "net_pnl": 2000.0,
            "sharpe": 1.6,
            "max_drawdown": 0.10,
            "daily_turnover": 0.01,
            "avg_gross_exposure": 1.0,
            "time_in_market_frac": 0.80,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
            "avg_rebalance_scale": 1.0,
            "rebalance_event_count": 20,
            "active_rebalance_event_count": 20,
            "yearly": {
                "2021": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2022": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2023": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
                "2024H1": {"periods": 10, "net_return": 0.05, "sharpe": 1.0},
            },
            "yearly_positive_count": 4,
            "symbol_pnl": {"AAA": 1000.0, "BBB": 900.0, "CCC": 200.0, "DDD": 100.0},
            "top_positive_symbol_share": 0.45,
            "bootstrap_30d_sharpe_p5": 0.80,
            "bootstrap_seed": int(bootstrap_seed_value),
            "bootstrap_iterations": int(bootstrap_iterations),
            "legs": {
                "long_gross_return": 0.20,
                "long_gross_sharpe": 1.6,
                "short_gross_return": 0.0,
                "short_gross_sharpe": 0.0,
                "avg_long_exposure": 1.0,
                "avg_short_exposure": 0.0,
            },
            "equal_weight_benchmark": {
                "sharpe": 0.8,
                "max_drawdown": 0.20,
                "sharpe_excess": 0.80,
                "drawdown_ratio": 0.50,
            },
        }
        if bootstrap_confirm_iterations:
            result["bootstrap_30d_sharpe_p5_confirm"] = 0.80
            result["bootstrap_confirm_seed"] = int(bootstrap_confirm_seed_value)
            result["bootstrap_confirm_iterations"] = int(bootstrap_confirm_iterations)
        return result

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24, 48, 72),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2,),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        accepted_min_validation_active_rebalances=50,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )

    payload = run_grid(cfg)

    assert payload["summary"]["pass_count"] >= 3
    assert payload["summary"]["accepted_max_validation_active_rebalances"] == 20
    assert payload["summary"]["accepted_activity_ok"] is False
    assert payload["summary"]["accepted_train_only"] is False
    assert payload["selection_validation"]["accepted_min_validation_active_rebalances"] == 50


def test_run_grid_sorts_top_rows_by_gate_alignment_before_raw_sharpe(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.load_close_matrix", lambda *args: close_matrix(1600))

    def fake_simulate(
        closes,
        cfg,
        cost_bps,
        bootstrap_iterations=500,
        bootstrap_seed_value=20260707,
        bootstrap_confirm_iterations=0,
        bootstrap_confirm_seed_value=None,
    ):
        if cfg.k == 2:
            result = passing_gate_result(active_rebalance_event_count=1, time_in_market_frac=0.01)
            result.update(
                {
                    "sharpe": 4.0,
                    "max_drawdown": 0.48,
                    "yearly_positive_count": 1,
                    "bootstrap_30d_sharpe_p5": 0.05,
                    "top_positive_symbol_share": 0.92,
                    "max_flat_streak_h": 300,
                }
            )
            result["yearly"]["2024H1"]["net_return"] = -0.08
            result["equal_weight_benchmark"] = {"sharpe_excess": -0.20, "drawdown_ratio": 1.40}
        else:
            result = passing_gate_result(active_rebalance_event_count=20, time_in_market_frac=0.80)
            result.update({"sharpe": 1.4, "max_flat_streak_h": 12})
        result["config"] = {
            "lookback_h": cfg.lookback_h,
            "skip_h": cfg.skip_h,
            "rebalance_h": cfg.rebalance_h,
            "k": cfg.k,
            "score_mode": cfg.score_mode,
            "market_filter_h": cfg.market_filter_h,
            "vol_target_ann": cfg.vol_target_ann,
        }
        result["cost_bps"] = float(cost_bps)
        result["bootstrap_seed"] = int(bootstrap_seed_value)
        result["bootstrap_iterations"] = int(bootstrap_iterations)
        result["legs"] = {
            "long_gross_return": 0.20,
            "long_gross_sharpe": 1.4,
            "short_gross_return": 0.0,
            "short_gross_sharpe": 0.0,
            "avg_long_exposure": 1.0,
            "avg_short_exposure": 0.0,
        }
        if bootstrap_confirm_iterations:
            result["bootstrap_30d_sharpe_p5_confirm"] = result["bootstrap_30d_sharpe_p5"]
            result["bootstrap_confirm_seed"] = int(bootstrap_confirm_seed_value)
            result["bootstrap_confirm_iterations"] = int(bootstrap_confirm_iterations)
        return result

    def fake_walk_forward(closes, cfg, cost_bps=40.0, **kwargs):
        if cfg.k == 3:
            return {"enabled": True, "passed": False, "folds": [], "q25_sharpe": -0.10}
        return {"enabled": True, "passed": False, "folds": [], "q25_sharpe": 0.90}

    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.simulate", fake_simulate)
    monkeypatch.setattr("v9.contract.xsec_ohlcv_factory.walk_forward_summary", fake_walk_forward)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(24,),
        skips_h=(0,),
        rebalances_h=(12,),
        ks=(2, 3),
        score_modes=("mom",),
        market_filters_h=(0,),
        vol_targets_ann=(0.0,),
        bootstrap_iterations=10,
        validate_all_rows=True,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )

    payload = run_grid(cfg)

    assert payload["rows"][0]["config"]["k"] == 3
    assert payload["rows"][0]["cost20"]["sharpe"] < payload["rows"][1]["cost20"]["sharpe"]
    assert payload["rows"][0]["gate_alignment"]["score"] > payload["rows"][1]["gate_alignment"]["score"]


def test_presets_select_distinct_search_spaces() -> None:
    core = config_for_preset("core", "cache", "start", "end", "embargo", 10, "a.json", "a.md")
    slow = config_for_preset("slow", "cache", "start", "end", "embargo", 10, "b.json", "b.md")
    neighbor = config_for_preset("defensive_neighbor", "cache", "start", "end", "embargo", 10, "c.json", "c.md")
    drawdown = config_for_preset("defensive_drawdown", "cache", "start", "end", "embargo", 10, "d.json", "d.md")
    hq_dd = config_for_preset("hq_dd_long", "cache", "start", "end", "embargo", 10, "e.json", "e.md")
    hq_hedged = config_for_preset("hq_hedged_long", "cache", "start", "end", "embargo", 10, "hl.json", "hl.md")
    hq_neutral = config_for_preset("hq_market_neutral", "cache", "start", "end", "embargo", 10, "mn.json", "mn.md")
    hq_plateau = config_for_preset("hq_dd_plateau", "cache", "start", "end", "embargo", 10, "p.json", "p.md")
    hq_active = config_for_preset("hq_active_recent", "cache", "start", "end", "embargo", 10, "ar.json", "ar.md")
    hq_signal = config_for_preset("hq_recent_signal", "cache", "start", "end", "embargo", 10, "rs.json", "rs.md")
    hq_bridge = config_for_preset("hq_decay_bridge", "cache", "start", "end", "embargo", 10, "db.json", "db.md")
    hq_wf_hostile = config_for_preset("hq_wf_hostile_bridge", "cache", "start", "end", "embargo", 10, "hwb.json", "hwb.md")
    hq_wf_hostile_hedged = config_for_preset(
        "hq_wf_hostile_hedged", "cache", "start", "end", "embargo", 10, "hwh.json", "hwh.md"
    )
    hq_wf_hostile_regime_hedged = config_for_preset(
        "hq_wf_hostile_regime_hedged",
        "cache",
        "start",
        "end",
        "embargo",
        10,
        "hwrh.json",
        "hwrh.md",
    )
    hq_wf_tail_defense = config_for_preset(
        "hq_wf_tail_defense",
        "cache",
        "start",
        "end",
        "embargo",
        10,
        "hwtd.json",
        "hwtd.md",
    )
    hq_wf_hostile_long_short = config_for_preset(
        "hq_wf_hostile_long_short", "cache", "start", "end", "embargo", 10, "hwls.json", "hwls.md"
    )
    hq_cadence = config_for_preset("hq_cadence_tranche", "cache", "start", "end", "embargo", 10, "t.json", "t.md")
    hq_fast = config_for_preset("hq_fast_rebal", "cache", "start", "end", "embargo", 10, "f.json", "f.md")
    hq_breadth = config_for_preset("hq_breadth_wide", "cache", "start", "end", "embargo", 10, "g.json", "g.md")
    evergreen = config_for_preset("evergreen_fast", "cache", "start", "end", "embargo", 10, "ev.json", "ev.md")
    guarded = config_for_preset("evergreen_guarded", "cache", "start", "end", "embargo", 10, "eg.json", "eg.md")
    regime_guarded = config_for_preset(
        "evergreen_regime_guarded", "cache", "start", "end", "embargo", 10, "erg.json", "erg.md"
    )
    lowvol_guarded = config_for_preset(
        "evergreen_lowvol_guarded", "cache", "start", "end", "embargo", 10, "elg.json", "elg.md"
    )
    assert core.out_json == "a.json"
    assert core.validation_min_2024h1_periods == 0
    assert slow.out_json == "b.json"
    assert slow.rebalances_h != core.rebalances_h
    assert 1440 in slow.lookbacks_h
    assert neighbor.score_modes == ("risk_adj_mom",)
    assert 0.10 in neighbor.vol_targets_ann
    assert min(drawdown.vol_targets_ann) == 0.08
    assert max(drawdown.market_filters_h) == 2160
    assert 1008 in hq_dd.lookbacks_h
    assert 0.06 in hq_dd.vol_targets_ann
    assert hq_hedged.portfolio_modes == ("hedged_long",)
    assert hq_hedged.hedge_ratios == (0.5, 1.0)
    assert hq_hedged.market_filters_h == (0, 1176)
    assert (
        len(hq_hedged.lookbacks_h)
        * len(hq_hedged.rebalances_h)
        * len(hq_hedged.ks)
        * len(hq_hedged.score_modes)
        * len(hq_hedged.market_filters_h)
        * len(hq_hedged.vol_targets_ann)
        * len(hq_hedged.portfolio_modes)
        * len(hq_hedged.hedge_ratios)
        * len(hq_hedged.drawdown_stops)
        * len(hq_hedged.cooldowns_h)
        == 48
    )
    assert hq_neutral.portfolio_modes == ("long_short",)
    assert hq_neutral.lookbacks_h == (600, 720, 840)
    assert hq_neutral.market_filters_h == (0, 504, 1176)
    assert (
        len(hq_neutral.lookbacks_h)
        * len(hq_neutral.rebalances_h)
        * len(hq_neutral.ks)
        * len(hq_neutral.score_modes)
        * len(hq_neutral.market_filters_h)
        * len(hq_neutral.vol_targets_ann)
        * len(hq_neutral.portfolio_modes)
        * len(hq_neutral.drawdown_stops)
        * len(hq_neutral.cooldowns_h)
        == 54
    )
    assert hq_active.lookbacks_h == (504, 720, 1008)
    assert hq_active.rebalances_h == (120, 168, 240)
    assert hq_active.score_modes == ("mom", "risk_adj_mom")
    assert hq_active.market_filters_h == (336, 504, 720, 1008)
    assert hq_active.vol_targets_ann == (0.04, 0.06, 0.08)
    assert hq_active.n_tranches == (1,)
    assert hq_active.selection_min_time_in_market_frac == 0.35
    assert hq_active.validation_min_2024h1_periods == 1
    assert hq_active.selection_max_flat_streak_h == 45 * 24
    assert hq_active.validation_max_flat_streak_h == 45 * 24
    assert (
        len(hq_active.lookbacks_h)
        * len(hq_active.rebalances_h)
        * len(hq_active.ks)
        * len(hq_active.score_modes)
        * len(hq_active.market_filters_h)
        * len(hq_active.vol_targets_ann)
        * len(hq_active.n_tranches)
        == 648
    )
    assert hq_signal.lookbacks_h == (168, 240, 336, 504)
    assert hq_signal.rebalances_h == (48, 72, 120)
    assert hq_signal.score_modes == ("risk_adj_mom", "vol_breakout")
    assert hq_signal.market_filters_h == (168, 240, 336, 504)
    assert hq_signal.vol_targets_ann == (0.04, 0.06)
    assert hq_signal.drawdown_stops == (0.10,)
    assert hq_signal.cooldowns_h == (72,)
    assert hq_signal.market_confirm_hs == (72,)
    assert hq_signal.market_drawdown_limits == (0.25,)
    assert hq_signal.validation_min_2024h1_periods == 1
    assert hq_signal.selection_max_flat_streak_h == 30 * 24
    assert hq_signal.validation_max_flat_streak_h == 45 * 24
    assert (
        len(hq_signal.lookbacks_h)
        * len(hq_signal.rebalances_h)
        * len(hq_signal.ks)
        * len(hq_signal.score_modes)
        * len(hq_signal.market_filters_h)
        * len(hq_signal.vol_targets_ann)
        == 384
    )
    assert hq_bridge.lookbacks_h == (336, 504, 720, 1008)
    assert hq_bridge.rebalances_h == (120, 168, 240)
    assert hq_bridge.ks == (3,)
    assert hq_bridge.score_modes == ("risk_adj_mom",)
    assert hq_bridge.market_filters_h == (240, 336, 504, 720)
    assert hq_bridge.vol_targets_ann == (0.06, 0.08, 0.10)
    assert hq_bridge.drawdown_stops == (0.0, 0.10)
    assert hq_bridge.cooldowns_h == (72,)
    assert hq_bridge.validation_min_2024h1_periods == 1
    assert hq_bridge.selection_max_flat_streak_h == 45 * 24
    assert hq_bridge.validation_max_flat_streak_h == 45 * 24
    assert (
        len(hq_bridge.lookbacks_h)
        * len(hq_bridge.rebalances_h)
        * len(hq_bridge.ks)
        * len(hq_bridge.score_modes)
        * len(hq_bridge.market_filters_h)
        * len(hq_bridge.vol_targets_ann)
        * len(hq_bridge.drawdown_stops)
        == 288
    )
    hq_wf_bridge = config_for_preset("hq_wf_bridge", "cache", "start", "end", "embargo", 10, "wfb.json", "wfb.md")
    assert hq_wf_bridge.lookbacks_h == (336, 504)
    assert hq_wf_bridge.rebalances_h == (120, 168)
    assert hq_wf_bridge.ks == (3, 4)
    assert hq_wf_bridge.score_modes == ("mom", "risk_adj_mom")
    assert hq_wf_bridge.market_filters_h == (240, 336)
    assert hq_wf_bridge.vol_targets_ann == (0.04, 0.06)
    assert hq_wf_bridge.n_tranches == (2,)
    assert hq_wf_bridge.drawdown_stops == (0.08, 0.10)
    assert hq_wf_bridge.cooldowns_h == (72,)
    assert hq_wf_bridge.market_confirm_hs == (0, 72)
    assert hq_wf_bridge.market_drawdown_limits == (0.0, 0.25)
    assert hq_wf_bridge.selection_max_flat_streak_h == 45 * 24
    assert hq_wf_bridge.validation_max_flat_streak_h == 45 * 24
    assert (
        len(hq_wf_bridge.lookbacks_h)
        * len(hq_wf_bridge.rebalances_h)
        * len(hq_wf_bridge.ks)
        * len(hq_wf_bridge.score_modes)
        * len(hq_wf_bridge.market_filters_h)
        * len(hq_wf_bridge.vol_targets_ann)
        * len(hq_wf_bridge.n_tranches)
        * len(hq_wf_bridge.drawdown_stops)
        * len(hq_wf_bridge.market_confirm_hs)
        * len(hq_wf_bridge.market_drawdown_limits)
        == 512
    )
    assert hq_wf_hostile.lookbacks_h == (336, 504)
    assert hq_wf_hostile.rebalances_h == (120, 168)
    assert hq_wf_hostile.ks == (3, 4)
    assert hq_wf_hostile.score_modes == ("risk_adj_mom",)
    assert hq_wf_hostile.market_filters_h == (720, 1008)
    assert hq_wf_hostile.vol_targets_ann == (0.04, 0.05)
    assert hq_wf_hostile.n_tranches == (2,)
    assert hq_wf_hostile.drawdown_stops == (0.08, 0.10)
    assert hq_wf_hostile.cooldowns_h == (72,)
    assert hq_wf_hostile.market_confirm_hs == (168,)
    assert hq_wf_hostile.market_drawdown_limits == (0.0, 0.15, 0.20)
    assert hq_wf_hostile.selection_min_time_in_market_frac == 0.15
    assert hq_wf_hostile.validation_min_2024h1_periods == 1
    assert hq_wf_hostile.selection_max_flat_streak_h == 180 * 24
    assert hq_wf_hostile.validation_min_time_in_market_frac == 0.10
    assert hq_wf_hostile.validation_max_flat_streak_h == 180 * 24
    assert (
        len(hq_wf_hostile.lookbacks_h)
        * len(hq_wf_hostile.rebalances_h)
        * len(hq_wf_hostile.ks)
        * len(hq_wf_hostile.score_modes)
        * len(hq_wf_hostile.market_filters_h)
        * len(hq_wf_hostile.vol_targets_ann)
        * len(hq_wf_hostile.n_tranches)
        * len(hq_wf_hostile.drawdown_stops)
        * len(hq_wf_hostile.market_confirm_hs)
        * len(hq_wf_hostile.market_drawdown_limits)
        == 192
    )
    assert hq_wf_hostile_hedged.lookbacks_h == (336, 504)
    assert hq_wf_hostile_hedged.rebalances_h == (120, 168)
    assert hq_wf_hostile_hedged.ks == (3, 4)
    assert hq_wf_hostile_hedged.score_modes == ("risk_adj_mom",)
    assert hq_wf_hostile_hedged.market_filters_h == (720, 1008)
    assert hq_wf_hostile_hedged.vol_targets_ann == (0.04, 0.05)
    assert hq_wf_hostile_hedged.n_tranches == (2,)
    assert hq_wf_hostile_hedged.drawdown_stops == (0.08,)
    assert hq_wf_hostile_hedged.cooldowns_h == (72,)
    assert hq_wf_hostile_hedged.market_confirm_hs == (168,)
    assert hq_wf_hostile_hedged.market_drawdown_limits == (0.0, 0.15, 0.20)
    assert hq_wf_hostile_hedged.portfolio_modes == ("hedged_long",)
    assert hq_wf_hostile_hedged.hedge_ratios == (0.5, 1.0)
    assert hq_wf_hostile_hedged.downtrend_hedge_ratios == (0.0,)
    assert hq_wf_hostile_hedged.selection_min_time_in_market_frac == 0.15
    assert hq_wf_hostile_hedged.validation_min_2024h1_periods == 1
    assert hq_wf_hostile_hedged.selection_max_flat_streak_h == 180 * 24
    assert hq_wf_hostile_hedged.validation_min_time_in_market_frac == 0.10
    assert hq_wf_hostile_hedged.validation_max_flat_streak_h == 180 * 24
    assert (
        len(hq_wf_hostile_hedged.lookbacks_h)
        * len(hq_wf_hostile_hedged.rebalances_h)
        * len(hq_wf_hostile_hedged.ks)
        * len(hq_wf_hostile_hedged.score_modes)
        * len(hq_wf_hostile_hedged.market_filters_h)
        * len(hq_wf_hostile_hedged.vol_targets_ann)
        * len(hq_wf_hostile_hedged.n_tranches)
        * len(hq_wf_hostile_hedged.drawdown_stops)
        * len(hq_wf_hostile_hedged.market_confirm_hs)
        * len(hq_wf_hostile_hedged.market_drawdown_limits)
        * len(hq_wf_hostile_hedged.portfolio_modes)
        * len(hq_wf_hostile_hedged.hedge_ratios)
        * len(hq_wf_hostile_hedged.downtrend_hedge_ratios)
        == 192
    )
    assert hq_wf_hostile_regime_hedged.lookbacks_h == hq_wf_hostile_hedged.lookbacks_h
    assert hq_wf_hostile_regime_hedged.portfolio_modes == ("hedged_long",)
    assert hq_wf_hostile_regime_hedged.downtrend_hedge_ratios == (0.25, 0.50)
    assert hq_wf_hostile_regime_hedged.selection_min_2022_return == -0.02
    assert hq_wf_hostile_regime_hedged.validation_min_2024h1_periods == 1
    assert (
        len(hq_wf_hostile_regime_hedged.lookbacks_h)
        * len(hq_wf_hostile_regime_hedged.rebalances_h)
        * len(hq_wf_hostile_regime_hedged.ks)
        * len(hq_wf_hostile_regime_hedged.score_modes)
        * len(hq_wf_hostile_regime_hedged.market_filters_h)
        * len(hq_wf_hostile_regime_hedged.vol_targets_ann)
        * len(hq_wf_hostile_regime_hedged.n_tranches)
        * len(hq_wf_hostile_regime_hedged.drawdown_stops)
        * len(hq_wf_hostile_regime_hedged.market_confirm_hs)
        * len(hq_wf_hostile_regime_hedged.market_drawdown_limits)
        * len(hq_wf_hostile_regime_hedged.portfolio_modes)
        * len(hq_wf_hostile_regime_hedged.hedge_ratios)
        * len(hq_wf_hostile_regime_hedged.downtrend_hedge_ratios)
        == 384
    )
    assert hq_wf_tail_defense.lookbacks_h == (240, 336, 504)
    assert hq_wf_tail_defense.rebalances_h == (72, 120)
    assert hq_wf_tail_defense.score_modes == ("risk_adj_mom_ensemble",)
    assert hq_wf_tail_defense.market_filters_h == (720, 1008)
    assert hq_wf_tail_defense.vol_targets_ann == (0.03, 0.04)
    assert hq_wf_tail_defense.drawdown_stops == (0.06,)
    assert hq_wf_tail_defense.market_drawdown_limits == (0.10, 0.15)
    assert hq_wf_tail_defense.portfolio_modes == ("hedged_long",)
    assert hq_wf_tail_defense.hedge_ratios == (0.5,)
    assert hq_wf_tail_defense.downtrend_hedge_ratios == (0.50, 0.75)
    assert hq_wf_tail_defense.selection_min_time_in_market_frac == 0.12
    assert hq_wf_tail_defense.validation_min_time_in_market_frac == 0.08
    assert (
        len(hq_wf_tail_defense.lookbacks_h)
        * len(hq_wf_tail_defense.rebalances_h)
        * len(hq_wf_tail_defense.ks)
        * len(hq_wf_tail_defense.score_modes)
        * len(hq_wf_tail_defense.market_filters_h)
        * len(hq_wf_tail_defense.vol_targets_ann)
        * len(hq_wf_tail_defense.n_tranches)
        * len(hq_wf_tail_defense.drawdown_stops)
        * len(hq_wf_tail_defense.market_confirm_hs)
        * len(hq_wf_tail_defense.market_drawdown_limits)
        * len(hq_wf_tail_defense.portfolio_modes)
        * len(hq_wf_tail_defense.hedge_ratios)
        * len(hq_wf_tail_defense.downtrend_hedge_ratios)
        == 96
    )
    assert hq_wf_hostile_long_short.lookbacks_h == (336, 504)
    assert hq_wf_hostile_long_short.rebalances_h == (120, 168)
    assert hq_wf_hostile_long_short.ks == (3, 4)
    assert hq_wf_hostile_long_short.score_modes == ("risk_adj_mom", "mom_reversal_blend")
    assert hq_wf_hostile_long_short.market_filters_h == (0,)
    assert hq_wf_hostile_long_short.vol_targets_ann == (0.04, 0.05)
    assert hq_wf_hostile_long_short.n_tranches == (2,)
    assert hq_wf_hostile_long_short.drawdown_stops == (0.08, 0.10)
    assert hq_wf_hostile_long_short.cooldowns_h == (72,)
    assert hq_wf_hostile_long_short.market_confirm_hs == (0,)
    assert hq_wf_hostile_long_short.market_drawdown_limits == (0.0,)
    assert hq_wf_hostile_long_short.portfolio_modes == ("long_short",)
    assert hq_wf_hostile_long_short.hedge_ratios == (0.5, 1.0)
    assert hq_wf_hostile_long_short.selection_min_time_in_market_frac == 0.60
    assert hq_wf_hostile_long_short.validation_min_2024h1_periods == 1
    assert hq_wf_hostile_long_short.selection_max_flat_streak_h == 45 * 24
    assert hq_wf_hostile_long_short.validation_min_time_in_market_frac == 0.30
    assert hq_wf_hostile_long_short.validation_max_flat_streak_h == 45 * 24
    assert (
        len(hq_wf_hostile_long_short.lookbacks_h)
        * len(hq_wf_hostile_long_short.rebalances_h)
        * len(hq_wf_hostile_long_short.ks)
        * len(hq_wf_hostile_long_short.score_modes)
        * len(hq_wf_hostile_long_short.market_filters_h)
        * len(hq_wf_hostile_long_short.vol_targets_ann)
        * len(hq_wf_hostile_long_short.n_tranches)
        * len(hq_wf_hostile_long_short.drawdown_stops)
        * len(hq_wf_hostile_long_short.market_confirm_hs)
        * len(hq_wf_hostile_long_short.market_drawdown_limits)
        * len(hq_wf_hostile_long_short.portfolio_modes)
        * len(hq_wf_hostile_long_short.hedge_ratios)
        * len(hq_wf_hostile_long_short.downtrend_hedge_ratios)
        == 128
    )
    assert hq_plateau.validate_all_rows is True
    assert hq_plateau.plateau_center_config["lookback_h"] == 504
    assert len(hq_plateau.lookbacks_h) * len(hq_plateau.rebalances_h) * len(hq_plateau.market_filters_h) * len(hq_plateau.vol_targets_ann) == 81
    assert hq_plateau.stress_costs_bps == (30.0, 40.0)
    assert hq_cadence.n_tranches == (3,)
    assert len(hq_cadence.lookbacks_h) * len(hq_cadence.rebalances_h) * len(hq_cadence.ks) * len(hq_cadence.market_filters_h) * len(hq_cadence.vol_targets_ann) == 72
    assert 24 in hq_fast.rebalances_h
    assert 5 in hq_breadth.ks
    assert evergreen.rebalances_h == (8, 12, 24)
    assert evergreen.market_filters_h == (0, 168, 336)
    assert evergreen.selection_min_time_in_market_frac == 0.60
    assert evergreen.selection_max_flat_streak_h == 45 * 24
    assert evergreen.validation_min_time_in_market_frac == 0.30
    assert evergreen.validation_max_flat_streak_h == 45 * 24
    assert guarded.drawdown_stops == (0.05, 0.10)
    assert guarded.cooldowns_h == (72, 168)
    assert guarded.vol_targets_ann == (0.08, 0.10, 0.12)
    assert guarded.selection_min_time_in_market_frac == 0.45
    assert guarded.selection_max_flat_streak_h == 60 * 24
    assert guarded.validation_min_time_in_market_frac == 0.25
    assert guarded.validation_max_flat_streak_h == 60 * 24
    assert regime_guarded.market_filters_h == (168, 336)
    assert regime_guarded.market_confirm_hs == (72,)
    assert regime_guarded.market_drawdown_limits == (0.20, 0.30)
    assert regime_guarded.n_tranches == (2,)
    assert regime_guarded.cooldowns_h == (72, 168)
    assert regime_guarded.selection_min_time_in_market_frac == 0.25
    assert regime_guarded.selection_max_flat_streak_h == 120 * 24
    assert (
        len(regime_guarded.lookbacks_h)
        * len(regime_guarded.rebalances_h)
        * len(regime_guarded.score_modes)
        * len(regime_guarded.market_filters_h)
        * len(regime_guarded.vol_targets_ann)
        * len(regime_guarded.drawdown_stops)
        * len(regime_guarded.cooldowns_h)
        * len(regime_guarded.market_drawdown_limits)
        == 256
    )
    assert lowvol_guarded.market_filters_h == (336,)
    assert lowvol_guarded.vol_targets_ann == (0.04, 0.06, 0.08)
    assert lowvol_guarded.n_tranches == (2, 3)
    assert lowvol_guarded.drawdown_stops == (0.10, 0.15)
    assert lowvol_guarded.cooldowns_h == (72, 168)
    assert lowvol_guarded.selection_min_time_in_market_frac == 0.40
    assert lowvol_guarded.validation_min_time_in_market_frac == 0.20
    assert (
        len(lowvol_guarded.lookbacks_h)
        * len(lowvol_guarded.rebalances_h)
        * len(lowvol_guarded.ks)
        * len(lowvol_guarded.vol_targets_ann)
        * len(lowvol_guarded.n_tranches)
        * len(lowvol_guarded.drawdown_stops)
        * len(lowvol_guarded.cooldowns_h)
        == 192
    )


def test_plateau_stability_summary_passes_plateau_and_rejects_spike() -> None:
    center = {
        "lookback_h": 504,
        "skip_h": 0,
        "rebalance_h": 168,
        "k": 3,
        "score_mode": "risk_adj_mom",
        "market_filter_h": 1008,
        "vol_target_ann": 0.06,
    }

    def row(config, sharpe):
        return {"config": config, "validation": {"cost20": {"sharpe": sharpe}}}

    rows = [row(center, 1.2)]
    for idx, sharpe in enumerate([1.1, 1.2, 1.3, 1.4, 1.0, 1.05, 1.15, 0.8, 0.7, 0.6]):
        cfg = dict(center)
        cfg["lookback_h"] = 300 + idx
        rows.append(row(cfg, sharpe))
    cfg = RunConfig(plateau_center_config=center, plateau_neighbor_pass_fraction_min=0.70)

    summary = plateau_stability_summary(rows, cfg)

    assert summary is not None
    assert summary["passed"] is True
    assert summary["neighbor_pass_count"] == 7
    assert summary["center_not_spike"] is True

    spike_rows = [row(center, 2.1), row({**center, "lookback_h": 336}, 1.0), row({**center, "lookback_h": 672}, 1.1)]
    spike_cfg = RunConfig(plateau_center_config=center, plateau_neighbor_pass_fraction_min=0.50)
    spike = plateau_stability_summary(spike_rows, spike_cfg)
    assert spike is not None
    assert spike["passed"] is False
    assert spike["center_not_spike"] is False
