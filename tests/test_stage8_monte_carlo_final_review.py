"""Stage 8 tests: Epoch-end-only Monte Carlo final review."""

from unittest.mock import MagicMock, patch

from app.genetic_engine.chromosome_v2 import built_in_default_chromosome
from app.genetic_engine.evolution_v2 import EvolutionEngineV2
from app.genetic_engine.fitness_v2 import calculate_monte_carlo_report


def test_monte_carlo_report_records_ruin_and_return_quantiles():
    trades = [{"pnl_pct": p} for p in ([0.02, -0.01, 0.03, -0.02, 0.01] * 4)]
    report = calculate_monte_carlo_report(trades, n_simulations=200, seed=7)

    assert report["insufficient_data"] is False
    assert 0.0 <= report["ruin_probability"] <= 1.0
    assert set(report["return_quantiles"]) == {"p05", "p50", "p95"}
    assert (
        report["return_quantiles"]["p05"]
        <= report["return_quantiles"]["p50"]
        <= report["return_quantiles"]["p95"]
    )


def test_insufficient_samples_are_explicit_not_safe_zero():
    report = calculate_monte_carlo_report([{"pnl_pct": 0.01}] * 5)
    assert report["insufficient_data"] is True
    assert report["ruin_probability"] is None
    assert report["return_quantiles"] == {}


def test_final_review_uses_one_minute_complete_configured_sample(tmp_path):
    engine = EvolutionEngineV2(
        config={
            "population_size": 1,
            "symbols": ["BTCUSDT"],
            "monte_carlo_history_days": 120,
            "monte_carlo_simulations": 50,
        },
        save_dir=str(tmp_path),
    )
    challenger = built_in_default_chromosome()
    trades = [MagicMock(pnl_pct=0.01) for _ in range(12)]

    with patch(
        "app.genetic_engine.evolution_v2.evaluate_chromosome_multi_symbol_v2",
        return_value=(0.5, {}, trades),
    ) as evaluate:
        report = engine._run_monte_carlo_final_review(challenger)

    assert evaluate.call_args.kwargs["interval"] == "1m"
    assert evaluate.call_args.kwargs["days"] == 120
    assert report["interval"] == "1m"
    assert report["history_days"] == 120
    assert report["sample_trades"] == 12


def test_high_ruin_warning_does_not_change_fitness_or_block_archive(tmp_path):
    archive = MagicMock()
    engine = EvolutionEngineV2(
        config={
            "population_size": 1,
            "symbols": ["BTCUSDT"],
            "max_generations": 1,
        },
        archive=archive,
        save_dir=str(tmp_path),
    )
    challenger = built_in_default_chromosome()
    challenger.fitness_score = 0.42
    challenger.fitness_details = {}
    engine.population = [challenger]

    with patch.object(engine, "evaluate_generation"), patch.object(
        engine,
        "_run_monte_carlo_final_review",
        return_value={
            "interval": "1m",
            "ruin_probability": 1.0,
            "return_quantiles": {"p05": -0.9, "p50": -0.5, "p95": 0.1},
            "fitness_unchanged": True,
        },
    ), patch.object(engine, "_save_generation"), patch.object(
        engine, "_save_chromosome"
    ), patch.object(engine, "_archive_challenger") as archive_challenger:
        result = engine.run(max_generations=1, verbose=False)

    assert result.fitness_score == 0.42
    archive_challenger.assert_called_once()
    archived = archive_challenger.call_args.args[0]
    assert archived.fitness_score == 0.42
    assert archived.fitness_details["monte_carlo_final_review"]["ruin_probability"] == 1.0
