from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.tsmom_factory import (  # noqa: E402
    RunConfig,
    TsmomConfig,
    config_for_preset,
    data_fingerprint,
    drop_one_lookback_summary,
    leave_one_symbol_summary,
    market_regime_series,
    run_grid,
    short_weights_from_votes,
    simulate,
    target_weights_from_votes,
    vote_fraction_matrix,
    walk_forward_summary,
)


def close_matrix(periods: int = 360) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "dt": dt,
            "AAA": [100 + idx * 0.4 for idx in range(periods)],
            "BBB": [140 - idx * 0.15 for idx in range(periods)],
            "CCC": [100 + (idx % 24) * 0.02 for idx in range(periods)],
            "DDD": [80 + idx * 0.2 for idx in range(periods)],
        }
    )


def test_vote_fraction_combines_momentum_and_sma_votes() -> None:
    data = close_matrix(120)
    votes = vote_fraction_matrix(data, (12, 24))
    assert votes["AAA"].iloc[-1] == 1.0
    assert votes["BBB"].iloc[-1] == 0.0
    assert 0.0 <= votes["CCC"].iloc[-1] <= 1.0


def test_target_weights_are_long_flat_and_normalized() -> None:
    votes = pd.Series({"AAA": 1.0, "BBB": 0.5, "CCC": 0.49})
    scales = pd.Series({"AAA": 1.0, "BBB": 0.5, "CCC": 1.0})
    weights = target_weights_from_votes(votes, scales)
    assert weights["CCC"] == 0.0
    assert weights["AAA"] > weights["BBB"] > 0.0
    assert sum(weights.values()) == 1.0


def test_short_weights_are_negative_and_normalized() -> None:
    votes = pd.Series({"AAA": 0.0, "BBB": 0.25, "CCC": 0.75})
    scales = pd.Series({"AAA": 1.0, "BBB": 0.5, "CCC": 1.0})
    weights = short_weights_from_votes(votes, scales, threshold=0.375)
    assert weights["CCC"] == 0.0
    assert weights["AAA"] < weights["BBB"] < 0.0
    assert abs(sum(abs(v) for v in weights.values()) - 1.0) < 1e-12


def test_no_trade_band_can_suppress_rebalance() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=10.0)
    result = simulate(close_matrix(180), cfg, (12, 24), cost_bps=20.0, bootstrap_iterations=0)
    assert result["rebalance_event_count"] == 0
    assert result["avg_gross_exposure"] == 0.0
    assert result["avg_long_exposure"] == 0.0
    assert result["avg_short_exposure"] == 0.0
    assert result["legs"]["long_gross_return"] == 0.0
    assert result["legs"]["short_gross_return"] == 0.0


def test_simulate_reports_long_and_short_leg_exposure() -> None:
    data = close_matrix(240)
    for col in ["AAA", "BBB", "CCC", "DDD"]:
        data[col] = [200.0 - idx * 0.5 for idx in range(len(data))]
    cfg = TsmomConfig(
        asset_vol_target_ann=0.40,
        portfolio_vol_target_ann=0.50,
        no_trade_band=0.0,
        market_filter_h=24,
        bear_mode="short_weak",
        bear_short_scale=1.0,
        short_vote_threshold=0.50,
    )
    result = simulate(data, cfg, (12, 24), cost_bps=0.0, bootstrap_iterations=0)
    assert result["avg_short_exposure"] > 0.0
    assert result["legs"]["avg_short_exposure"] == result["avg_short_exposure"]
    assert result["legs"]["short_gross_return"] > 0.0


def test_advance_checks_use_only_active_yearly_buckets() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=0.05)
    result20 = simulate(close_matrix(240), cfg, (12, 24), cost_bps=20.0, bootstrap_iterations=0)
    result40 = simulate(close_matrix(240), cfg, (12, 24), cost_bps=40.0, bootstrap_iterations=0)
    result20["sharpe"] = 1.5
    result20["max_drawdown"] = 0.10
    result20["yearly"]["2021"]["periods"] = 100
    result20["yearly"]["2021"]["net_return"] = 0.10
    result20["yearly"]["2022"]["periods"] = 100
    result20["yearly"]["2022"]["net_return"] = 0.10
    result20["yearly"]["2023"]["periods"] = 0
    result20["yearly"]["2024H1"]["periods"] = 0
    result20["yearly"]["2024H1"]["net_return"] = 0.0
    result20["active_yearly_bucket_count"] = 2
    result20["positive_active_yearly_bucket_count"] = 2
    result20["bootstrap_30d_sharpe_p5"] = 1.0
    result20["positive_symbol_count"] = result20["symbol_count"]
    result20["top_positive_symbol_share"] = 0.50
    result20["equal_weight_benchmark"]["sharpe_excess"] = 0.10
    result20["equal_weight_benchmark"]["drawdown_ratio"] = 0.50
    result20["daily_turnover"] = 0.10
    result40["sharpe"] = 1.0
    checks = __import__("v9.contract.tsmom_factory", fromlist=["advance_checks"]).advance_checks(result20, result40, bootstrap_p5_min=0.25)
    assert "positive_3_of_4_years" not in checks
    assert checks["active_yearly_buckets_ge_2"] is True
    assert checks["positive_active_yearly_buckets_ge_75pct"] is True


def test_market_regime_filter_turns_off_declining_market() -> None:
    data = close_matrix(120)
    data["AAA"] = list(reversed(data["AAA"].tolist()))
    data["DDD"] = list(reversed(data["DDD"].tolist()))
    allowed = market_regime_series(data, 24)
    assert not bool(allowed.iloc[-1])


def test_drawdown_circuit_breaker_reports_risk_off_events() -> None:
    data = close_matrix(220)
    for col in ["AAA", "DDD"]:
        data.loc[120:, col] = data.loc[120:, col] * 0.40
    cfg = TsmomConfig(
        asset_vol_target_ann=0.40,
        portfolio_vol_target_ann=1.00,
        no_trade_band=0.0,
        vote_threshold=0.50,
        market_filter_h=0,
        drawdown_stop=0.05,
        cooldown_h=48,
    )
    result = simulate(data, cfg, (12, 24), cost_bps=0.0, bootstrap_iterations=0)
    assert result["risk_off_event_count"] >= 1
    assert result["risk_off_days"] > 0


def test_defensive_regime_preset_uses_small_fixed_grid() -> None:
    cfg = config_for_preset(
        preset="defensive_regime",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 16
    assert any(row.market_filter_h > 0 and row.market_off_scale == 0.50 for row in cfg.preset_configs)
    assert any(row.drawdown_stop > 0 and row.cooldown_h > 0 for row in cfg.preset_configs)


def test_bear_short_regime_preset_uses_fixed_short_grid() -> None:
    cfg = config_for_preset(
        preset="bear_short_regime",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 12
    assert all(row.bear_mode == "short_weak" for row in cfg.preset_configs)
    assert any(row.bear_short_scale == 1.0 for row in cfg.preset_configs)
    assert any(row.drawdown_stop > 0 and row.cooldown_h > 0 for row in cfg.preset_configs)


def test_bear_short_medium_preset_uses_shorter_lookbacks() -> None:
    cfg = config_for_preset(
        preset="bear_short_medium",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (336, 720, 1440, 2160)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 8
    assert all(row.bear_mode == "short_weak" for row in cfg.preset_configs)


def test_bear_short_medium_neighbor_preset_expands_winner_neighborhood() -> None:
    cfg = config_for_preset(
        preset="bear_short_medium_neighbor",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (240, 336, 720, 1440)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 16
    assert {row.market_filter_h for row in cfg.preset_configs}.issuperset({240, 336, 504, 720})
    assert any(row.short_vote_threshold == 0.25 for row in cfg.preset_configs)
    assert any(row.short_vote_threshold == 0.50 for row in cfg.preset_configs)


def test_bear_short_medium_risk_preset_searches_lower_risk_variants() -> None:
    cfg = config_for_preset(
        preset="bear_short_medium_risk",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (336, 720, 1440, 2160)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 12
    assert any(row.portfolio_vol_target_ann == 0.06 for row in cfg.preset_configs)
    assert any(row.drawdown_stop > 0.0 and row.cooldown_h > 0 for row in cfg.preset_configs)


def test_bear_short_fast_preset_searches_faster_interval_judgment() -> None:
    cfg = config_for_preset(
        preset="bear_short_fast",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (168, 336, 720, 1440)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 12
    assert all(row.bear_mode == "short_weak" for row in cfg.preset_configs)


def test_bear_short_cost_guard_preset_reduces_turnover_and_short_risk() -> None:
    cfg = config_for_preset(
        preset="bear_short_cost_guard",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (336, 720, 1440, 2160)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 16
    assert all(row.no_trade_band >= 0.20 for row in cfg.preset_configs)
    assert all(row.portfolio_vol_target_ann <= 0.08 for row in cfg.preset_configs)
    assert any(row.bear_mode == "flat" and row.bear_short_scale == 0.0 for row in cfg.preset_configs)
    assert any(row.bear_mode == "short_weak" and row.bear_short_scale == 0.15 for row in cfg.preset_configs)
    assert any(row.short_vote_threshold == 0.25 for row in cfg.preset_configs)


def test_slow_cost_guard_preset_uses_slower_lookbacks_and_lower_risk() -> None:
    cfg = config_for_preset(
        preset="slow_cost_guard",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (720, 1440, 2160, 4320)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 16
    assert all(row.no_trade_band >= 0.30 for row in cfg.preset_configs)
    assert all(row.portfolio_vol_target_ann <= 0.08 for row in cfg.preset_configs)
    assert any(row.bear_mode == "flat" for row in cfg.preset_configs)


def test_ultra_slow_cost_guard_preset_pushes_lower_turnover_neighbor() -> None:
    cfg = config_for_preset(
        preset="ultra_slow_cost_guard",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.lookbacks_h == (720, 1440, 2160, 4320)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 16
    assert all(row.no_trade_band >= 0.30 for row in cfg.preset_configs)
    assert all(row.portfolio_vol_target_ann <= 0.05 for row in cfg.preset_configs)
    assert any(row.no_trade_band == 0.70 for row in cfg.preset_configs)
    assert any(row.market_filter_h == 2160 for row in cfg.preset_configs)
    assert all(row.bear_short_scale <= 0.05 for row in cfg.preset_configs)


def test_core_cost_guard_preset_removes_holdout_drag_symbols() -> None:
    cfg = config_for_preset(
        preset="core_cost_guard",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.symbols == ("ADAUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
    assert "AVAXUSDT" not in cfg.symbols
    assert "BNBUSDT" not in cfg.symbols
    assert "LINKUSDT" not in cfg.symbols
    assert cfg.lookbacks_h == (336, 720, 1440, 2160)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 14


def test_core_slow_cost_guard_preset_combines_core_symbols_and_slow_lookbacks() -> None:
    cfg = config_for_preset(
        preset="core_slow_cost_guard",
        cache_dir="data/binance_public_cache",
        train_start="2017-08-01",
        train_end="2024-06-30 23:59:59",
        embargo_start="2024-07-01",
        bootstrap_iterations=100,
        out_json="out.json",
        out_md="out.md",
    )
    assert cfg.symbols == ("ADAUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
    assert cfg.lookbacks_h == (720, 1440, 2160, 4320)
    assert cfg.preset_configs is not None
    assert len(cfg.preset_configs) == 14


def test_bear_short_mode_can_profit_from_declining_market() -> None:
    data = close_matrix(240)
    for col in ["AAA", "BBB", "CCC", "DDD"]:
        data[col] = [200.0 - idx * 0.5 for idx in range(len(data))]
    cfg = TsmomConfig(
        asset_vol_target_ann=0.40,
        portfolio_vol_target_ann=0.50,
        no_trade_band=0.0,
        market_filter_h=24,
        bear_mode="short_weak",
        bear_short_scale=1.0,
        short_vote_threshold=0.50,
    )
    result = simulate(data, cfg, (12, 24), cost_bps=0.0, bootstrap_iterations=0)
    assert result["total_return"] > 0.0
    assert result["avg_gross_exposure"] > 0.0


def test_drop_one_lookback_summary_reports_each_drop() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=0.05)
    summary = drop_one_lookback_summary(close_matrix(240), cfg, (12, 24, 48, 72), ensemble_sharpe20=0.0)
    assert summary["enabled"] is True
    assert len(summary["rows"]) == 4
    assert {row["dropped_lookback_h"] for row in summary["rows"]} == {12, 24, 48, 72}


def test_walk_forward_summary_reports_fold_and_leg_metrics() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=0.05)
    summary = walk_forward_summary(
        close_matrix(720),
        cfg,
        (12, 24, 48),
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


def test_leave_one_symbol_summary_reports_each_symbol_drop() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=0.05)
    summary = leave_one_symbol_summary(close_matrix(360), cfg, (12, 24), cost_bps=0.0, min_sharpe=-99.0)
    assert summary["enabled"] is True
    assert len(summary["rows"]) == 4
    assert {row["dropped_symbol"] for row in summary["rows"]} == {"AAA", "BBB", "CCC", "DDD"}
    assert summary["worst_drop"]["dropped_symbol"] in {"AAA", "BBB", "CCC", "DDD"}


def test_run_grid_payload_is_train_only_and_uses_eight_configs(monkeypatch, tmp_path) -> None:
    closes = close_matrix(720)

    def fake_load_close_matrix(cache_dir, symbols, start, end, embargo):
        return closes

    monkeypatch.setattr("v9.contract.tsmom_factory.load_close_matrix", fake_load_close_matrix)
    cfg = RunConfig(
        symbols=("AAA", "BBB", "CCC", "DDD"),
        lookbacks_h=(12, 24, 48, 72),
        asset_vol_targets_ann=(0.30, 0.40),
        portfolio_vol_targets_ann=(0.10, 0.15),
        no_trade_bands=(0.05, 0.10),
        bootstrap_iterations=0,
        out_json=str(tmp_path / "out.json"),
        out_md="",
    )
    payload = run_grid(cfg)
    assert payload["kind"] == "tsmom_factory_v1_train_only_grid"
    assert payload["data"]["fingerprint"] == data_fingerprint(closes)
    assert payload["selection_validation"]["n_configs_tested"] == 8
    assert payload["selection_validation"]["walk_forward_required"] is True
    assert payload["selection_validation"]["leave_one_symbol_required"] is True
    assert payload["summary"]["rows"] == 8
    assert "walk_forward" in payload["top"][0]
    assert "leave_one_symbol" in payload["top"][0]
    assert payload["summary"]["holdout_authorized"] is False
    assert payload["summary"]["paper_trading_authorized"] is False
    assert payload["summary"]["live_trading_authorized"] is False
