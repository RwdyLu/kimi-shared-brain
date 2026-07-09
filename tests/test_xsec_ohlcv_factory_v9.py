from __future__ import annotations

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
    config_for_preset,
    data_fingerprint,
    leave_one_symbol_summary,
    long_only_weights,
    market_filter,
    plateau_stability_summary,
    append_progress_row,
    progress_meta_path_for,
    progress_path_for,
    run_grid,
    score_matrix,
    simulate,
    split_selection_validation,
    validation_sharpe_threshold,
    walk_forward_summary,
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
    assert "bootstrap_p5_ge_adjusted_min" in checks
    assert result20["daily_turnover"] >= 0
    assert result20["rebalance_offsets_h"] == [0]
    assert result20["avg_long_exposure"] >= 0
    assert result20["avg_short_exposure"] == 0
    assert result20["legs"]["avg_long_exposure"] == result20["avg_long_exposure"]
    assert result20["legs"]["short_gross_return"] == 0


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
    assert "leave_one_symbol" in payload["top"][0]
    assert not progress_meta_path_for(cfg.out_json).exists()


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
            "avg_rebalance_scale": 1.0,
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


def test_presets_select_distinct_search_spaces() -> None:
    core = config_for_preset("core", "cache", "start", "end", "embargo", 10, "a.json", "a.md")
    slow = config_for_preset("slow", "cache", "start", "end", "embargo", 10, "b.json", "b.md")
    neighbor = config_for_preset("defensive_neighbor", "cache", "start", "end", "embargo", 10, "c.json", "c.md")
    drawdown = config_for_preset("defensive_drawdown", "cache", "start", "end", "embargo", 10, "d.json", "d.md")
    hq_dd = config_for_preset("hq_dd_long", "cache", "start", "end", "embargo", 10, "e.json", "e.md")
    hq_plateau = config_for_preset("hq_dd_plateau", "cache", "start", "end", "embargo", 10, "p.json", "p.md")
    hq_cadence = config_for_preset("hq_cadence_tranche", "cache", "start", "end", "embargo", 10, "t.json", "t.md")
    hq_fast = config_for_preset("hq_fast_rebal", "cache", "start", "end", "embargo", 10, "f.json", "f.md")
    hq_breadth = config_for_preset("hq_breadth_wide", "cache", "start", "end", "embargo", 10, "g.json", "g.md")
    assert core.out_json == "a.json"
    assert slow.out_json == "b.json"
    assert slow.rebalances_h != core.rebalances_h
    assert 1440 in slow.lookbacks_h
    assert neighbor.score_modes == ("risk_adj_mom",)
    assert 0.10 in neighbor.vol_targets_ann
    assert min(drawdown.vol_targets_ann) == 0.08
    assert max(drawdown.market_filters_h) == 2160
    assert 1008 in hq_dd.lookbacks_h
    assert 0.06 in hq_dd.vol_targets_ann
    assert hq_plateau.validate_all_rows is True
    assert hq_plateau.plateau_center_config["lookback_h"] == 504
    assert len(hq_plateau.lookbacks_h) * len(hq_plateau.rebalances_h) * len(hq_plateau.market_filters_h) * len(hq_plateau.vol_targets_ann) == 81
    assert hq_plateau.stress_costs_bps == (30.0, 40.0)
    assert hq_cadence.n_tranches == (3,)
    assert len(hq_cadence.lookbacks_h) * len(hq_cadence.rebalances_h) * len(hq_cadence.ks) * len(hq_cadence.market_filters_h) * len(hq_cadence.vol_targets_ann) == 72
    assert 24 in hq_fast.rebalances_h
    assert 5 in hq_breadth.ks


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
