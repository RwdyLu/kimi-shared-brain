"""Stage 10 tests for real Evolution state and manual Promote controls."""

import json
from pathlib import Path

import pytest

from app.genetic_engine.archive import ArchiveRecord, StrategyArchive
from app.genetic_engine.chromosome_v2 import built_in_default_chromosome
from app.genetic_engine import evolution_v2
from app.genetic_engine.evolution_v2 import EvolutionEngineV2
from ui.services.evolution_service import (
    load_evolution_snapshot,
    promote_challenger,
    save_evolution_config,
)


def _generation_file(run_dir: Path) -> None:
    chromosome = built_in_default_chromosome("BTCUSDT").to_dict()
    chromosome["fitness_score"] = 0.42
    chromosome["generation"] = 3
    chromosome["fitness_details"] = {
        "per_window": {
            "BTCUSDT:all": {"fitness": 0.42, "insufficient_data": False},
        },
        "data_provenance": {
            "provider_id": "historical_csv",
            "is_mock": False,
            "is_verified": True,
        },
    }
    run_dir.mkdir(parents=True)
    (run_dir / "generation_3.json").write_text(json.dumps({
        "generation": 3,
        "epoch_id": "epoch_test",
        "timestamp": "2026-06-14T12:00:00",
        "three_layer": {
            "environment": {
                "dead_reserve_ratio": 0.2,
                "global_stop_loss": 0.3,
                "max_leverage": 1.0,
            },
            "seasons": [
                {"season": name, "aggressiveness": multiplier}
                for name, multiplier in (
                    ("winter", 0.5), ("spring", 1.0),
                    ("summer", 2.0), ("autumn", 4.0),
                )
            ],
        },
        "population": [chromosome],
    }), encoding="utf-8")


def _record(chromosome_id: str, status: str = "qualified_challenger") -> ArchiveRecord:
    chromosome = built_in_default_chromosome("BTCUSDT")
    chromosome.chromosome_id = chromosome_id
    return ArchiveRecord(
        chromosome_id=chromosome_id,
        status=status,
        epoch_id="epoch_test",
        generation=3,
        fitness_score=0.42,
        fitness_details={"eligibility": {"challenger_eligible": True}},
        chromosome_data=chromosome.to_dict(),
    )


def _add_challenger(archive_dir: Path, chromosome_id: str = "CHALLENGER_1"):
    archive = StrategyArchive(str(archive_dir))
    archive.add_qualified_challenger(_record(chromosome_id), "BTCUSDT")


def _add_pending_acceptance(archive_dir: Path, chromosome_id: str = "CHALLENGER_1"):
    archive = StrategyArchive(str(archive_dir))
    archive.add_qualified_challenger(_record(chromosome_id), "BTCUSDT")
    archive.start_validation(chromosome_id)
    archive.mark_pending_acceptance(
        chromosome_id,
        {"paper_closed_trades": 20, "paper_pnl": 1.0, "paper_validation_passed": True},
    )


def test_snapshot_uses_real_generation_and_archive_data(tmp_path):
    run_dir = tmp_path / "runs"
    archive_dir = tmp_path / "archive"
    config_file = tmp_path / "evolution.json"
    _generation_file(run_dir)
    _add_challenger(archive_dir)
    save_evolution_config({"max_generations": 10}, config_file)

    snapshot = load_evolution_snapshot(
        run_dirs=(run_dir,),
        archive_dir=archive_dir,
        config_file=config_file,
    )
    assert snapshot["epoch_id"] == "epoch_test"
    assert snapshot["generation"] == 3
    assert snapshot["progress_pct"] == 40.0
    assert [season["season"] for season in snapshot["seasons"]] == [
        "winter", "spring", "summer", "autumn",
    ]
    assert snapshot["ranking"][0]["fitness"] == 0.42
    assert snapshot["ranking"][0]["per_window"]
    assert snapshot["ranking"][0]["data_provenance"]["is_mock"] is False
    assert snapshot["archive"]["challengers"][0]["chromosome_id"] == "CHALLENGER_1"


def test_next_run_settings_are_validated_and_do_not_start_runtime(tmp_path):
    config_file = tmp_path / "evolution.json"
    config = save_evolution_config({
        "population_size": 20,
        "max_generations": 50,
        "mutation_rate": 0.4,
        "crossover_rate": 0.6,
    }, config_file)
    assert config["population_size"] == 20
    assert not (tmp_path / "evolution_v2_running.json").exists()

    with pytest.raises(ValueError):
        save_evolution_config({"mutation_rate": 2.0}, config_file)
    with pytest.raises(ValueError):
        save_evolution_config({"unknown": 1}, config_file)


def test_engine_publishes_running_state_and_clears_it(tmp_path):
    engine = EvolutionEngineV2(
        config={"population_size": 1, "max_generations": 1},
        save_dir=str(tmp_path),
    )
    chromosome = built_in_default_chromosome()
    chromosome.fitness_score = 0.1
    engine.population = [chromosome]
    engine.evaluate_generation = lambda verbose=True: None
    engine._save_generation = lambda: None
    engine._save_chromosome = lambda *args: None
    engine._run_monte_carlo_final_review = lambda _chrom: {
        "ruin_probability": None,
    }
    engine._archive_challenger = lambda _chrom: None

    engine.run(max_generations=1, verbose=False)
    state = json.loads(
        (tmp_path / "evolution_v2_running.json").read_text(encoding="utf-8")
    )
    assert state["running"] is False
    assert state["epoch_id"] == engine.epoch_id


def test_engine_loads_ui_saved_next_run_settings(tmp_path, monkeypatch):
    config_file = tmp_path / "evolution.json"
    save_evolution_config({
        "population_size": 17,
        "max_generations": 23,
    }, config_file)
    monkeypatch.setattr(evolution_v2, "EVOLUTION_CONFIG_FILE", config_file)

    engine = EvolutionEngineV2(save_dir=str(tmp_path / "run"))
    assert engine.config["population_size"] == 17
    assert engine.config["max_generations"] == 23


def test_promote_requires_exact_confirmation_and_current_challenger(tmp_path):
    archive_dir = tmp_path / "archive"
    _add_pending_acceptance(archive_dir)

    with pytest.raises(ValueError, match="exactly match"):
        promote_challenger("BTCUSDT", "CHALLENGER_1", "wrong", archive_dir)

    result = promote_challenger(
        "BTCUSDT", "CHALLENGER_1", "CHALLENGER_1", archive_dir
    )
    assert result["ok"] is True

    archive = StrategyArchive(str(archive_dir))
    assert archive.get_champion("BTCUSDT").chromosome_id == "CHALLENGER_1"
    assert archive.get_challenger("BTCUSDT") is None


def test_promote_retires_previous_champion(tmp_path):
    archive_dir = tmp_path / "archive"
    _add_pending_acceptance(archive_dir, "FIRST")
    promote_challenger("BTCUSDT", "FIRST", "FIRST", archive_dir)
    _add_pending_acceptance(archive_dir, "SECOND")
    promote_challenger("BTCUSDT", "SECOND", "SECOND", archive_dir)

    archive = StrategyArchive(str(archive_dir))
    assert archive.get_champion("BTCUSDT").chromosome_id == "SECOND"
    assert [record.chromosome_id for record in archive.retired] == ["FIRST"]
