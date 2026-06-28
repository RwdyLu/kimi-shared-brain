"""Stage 5 tests: fixed epoch environment and ordered four-season coverage."""

import copy
from unittest.mock import MagicMock, patch

import pandas as pd

from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2
from app.genetic_engine.chromosome_v2 import MacroGenes, MicroGenes
from app.genetic_engine.environment import (
    Environment,
    Season,
    SeasonApplier,
    SeasonSampler,
    ThreeLayerConfig,
)
from app.genetic_engine.evolution_v2 import EvolutionEngineV2


def test_epoch_seasons_are_ordered_winter_spring_summer_autumn():
    seasons = SeasonSampler.sample_seasons_for_epoch(4)
    assert [s.season for s in seasons] == [
        Season.WINTER,
        Season.SPRING,
        Season.SUMMER,
        Season.AUTUMN,
    ]


def test_season_schedule_covers_history_in_four_ordered_segments():
    seasons = SeasonSampler.get_all_season_configs()
    observed = [
        SeasonApplier.season_for_index(i, 8, seasons).season
        for i in range(8)
    ]
    assert observed == [
        Season.WINTER,
        Season.WINTER,
        Season.SPRING,
        Season.SPRING,
        Season.SUMMER,
        Season.SUMMER,
        Season.AUTUMN,
        Season.AUTUMN,
    ]


def test_max_leverage_is_always_one():
    assert Environment(max_leverage=8.0).max_leverage == 1.0
    assert Environment.from_dict({"max_leverage": 3.0}).max_leverage == 1.0
    assert Environment().resample_for_new_epoch().max_leverage == 1.0


def test_environment_is_fixed_within_epoch_and_resampled_between_epochs():
    engine = EvolutionEngineV2(
        config={"population_size": 1, "symbols": ["BTCUSDT"]},
        save_dir="/tmp/stage5-test",
    )
    original_epoch = engine.epoch_id
    original_env = engine.three_layer.environment
    assert engine.three_layer.environment is original_env

    with patch.object(
        Environment,
        "resample_for_new_epoch",
        return_value=Environment(dead_reserve_ratio=0.33, global_stop_loss=0.22),
    ):
        engine.start_new_epoch()

    assert engine.epoch_id != original_epoch
    assert engine.three_layer.environment.dead_reserve_ratio == 0.33
    assert engine.three_layer.environment.global_stop_loss == 0.22
    assert engine.three_layer.environment.max_leverage == 1.0


def test_multi_symbol_evaluation_passes_all_seasons_not_random_one():
    from app.genetic_engine.backtest_engine_v2 import evaluate_chromosome_multi_symbol_v2
    from app.genetic_engine.fitness_v2 import BacktestMetricsV2
    from app.genetic_engine.backtest_engine_v2 import V2BacktestResult

    seasons = SeasonSampler.get_all_season_configs()
    mock_engine = MagicMock(spec=GeneBacktestEngineV2)
    mock_engine.initial_capital = 1000.0
    metrics = BacktestMetricsV2(
        total_trades=5,
        winning_trades=3,
        losing_trades=2,
        win_rate=0.6,
        profit_factor=1.5,
        alpha_vs_dca=0.05,
    )
    mock_engine.evaluate_v2.return_value = V2BacktestResult(
        strategy_metrics=metrics,
        strategy_trades=[MagicMock()] * 5,
        dca_metrics=BacktestMetricsV2(),
        dca_trades=[],
        alpha_vs_dca=0.05,
        friction_penalty=0.0,
    )

    evaluate_chromosome_multi_symbol_v2(
        MagicMock(),
        ["BTCUSDT"],
        engine=mock_engine,
        seasons=seasons,
        environment=Environment(),
    )

    assert mock_engine.evaluate_v2.call_args.kwargs["seasons"] is seasons
    assert "season" not in mock_engine.evaluate_v2.call_args.kwargs


def test_runtime_season_schedule_does_not_modify_genes():
    chrom = MagicMock()
    chrom.macro_genes = MacroGenes()
    before = copy.deepcopy(chrom.macro_genes.to_dict())
    seasons = SeasonSampler.get_all_season_configs()

    for index in range(40):
        SeasonApplier.season_for_index(index, 40, seasons)

    assert chrom.macro_genes.to_dict() == before


def test_strategy_runtime_records_all_four_seasons():
    from tests.test_stage4_gene_sensitivity import _make_chrom, _make_df

    chrom = _make_chrom(
        macro=MacroGenes(hold_period=999),
        micro=MicroGenes(kp=1.0, kv=0.0, ka=0.0, min_trade_threshold=0.0),
    )
    engine = GeneBacktestEngineV2(
        initial_capital=1000.0, lot_step=0.0001, lot_min=0.0001
    )
    _, _, raw = engine._run_strategy_v2(
        _make_df(400),
        chrom,
        "TEST",
        None,
        Environment(),
        False,
        season_schedule=SeasonSampler.get_all_season_configs(),
    )

    assert raw["seasons_applied"] == ["winter", "spring", "summer", "autumn"]


def test_dormant_macro_fields_do_not_mutate():
    macro = MacroGenes(
        max_dca_months=19,
        beta_threshold=0.21,
        moon_phase_pressure=1.8,
        deadline_force_pct=0.44,
        gc_threshold_months=11,
        gc_max_ratio=0.77,
        t_macro=43,
        t_micro=13,
        t_deadline=5,
        ema_anchor=180,
    )
    dormant = {
        key: value
        for key, value in macro.to_dict().items()
        if key not in MacroGenes.ACTIVE_EVOLUTION_FIELDS
    }

    with patch("app.genetic_engine.chromosome_v2.random.random", return_value=0.0), patch(
        "app.genetic_engine.chromosome_v2.random.uniform", return_value=0.5
    ):
        mutated = macro.mutate(intensity=1.0)

    for key, value in dormant.items():
        assert getattr(mutated, key) == value


def test_connected_micro_fields_participate_in_mutation():
    micro = MicroGenes(sigmoid_scale=1.0, gamma=1.0, beta=0.5)
    with patch("app.genetic_engine.chromosome_v2.random.random", return_value=0.0), patch(
        "app.genetic_engine.chromosome_v2.random.uniform", return_value=0.75
    ):
        mutated = micro.mutate(intensity=0.5)

    assert mutated.sigmoid_scale != micro.sigmoid_scale
    assert mutated.gamma != micro.gamma
    assert mutated.beta != micro.beta
