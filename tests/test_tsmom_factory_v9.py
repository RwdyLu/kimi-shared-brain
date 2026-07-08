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
    market_regime_series,
    run_grid,
    simulate,
    target_weights_from_votes,
    vote_fraction_matrix,
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


def test_no_trade_band_can_suppress_rebalance() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=10.0)
    result = simulate(close_matrix(180), cfg, (12, 24), cost_bps=20.0, bootstrap_iterations=0)
    assert result["rebalance_event_count"] == 0
    assert result["avg_gross_exposure"] == 0.0


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


def test_drop_one_lookback_summary_reports_each_drop() -> None:
    cfg = TsmomConfig(asset_vol_target_ann=0.40, portfolio_vol_target_ann=0.15, no_trade_band=0.05)
    summary = drop_one_lookback_summary(close_matrix(240), cfg, (12, 24, 48, 72), ensemble_sharpe20=0.0)
    assert summary["enabled"] is True
    assert len(summary["rows"]) == 4
    assert {row["dropped_lookback_h"] for row in summary["rows"]} == {12, 24, 48, 72}


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
    assert payload["summary"]["rows"] == 8
    assert payload["summary"]["holdout_authorized"] is False
    assert payload["summary"]["paper_trading_authorized"] is False
    assert payload["summary"]["live_trading_authorized"] is False
