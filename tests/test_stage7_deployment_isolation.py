"""Stage 7 tests: Challenger/Champion/Retired and runtime deployment isolation."""

import json
from argparse import Namespace

import pytest

from app.genetic_engine.archive import ArchiveRecord, StrategyArchive
from app.genetic_engine.chromosome_v2 import (
    StrategyChromosomeV2,
    built_in_default_chromosome,
)
from app.genetic_engine.evolution_v2 import ContinuousEvolutionV2, EvolutionEngineV2


def _record(chromosome_id: str, status: str = "challenger") -> ArchiveRecord:
    chrom = built_in_default_chromosome("default")
    chrom.chromosome_id = chromosome_id
    return ArchiveRecord(
        chromosome_id=chromosome_id,
        status=status,
        epoch_id="epoch_test",
        generation=1,
        fitness_score=0.8,
        fitness_details={},
        chromosome_data=chrom.to_dict(),
    )


def _qualified_record(chromosome_id: str) -> ArchiveRecord:
    record = _record(chromosome_id, "qualified_challenger")
    record.fitness_details = {"eligibility": {"challenger_eligible": True}}
    return record


def test_add_challenger_requires_eligibility_and_never_replaces_champion(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    champion = _record("champion-old", "champion")
    archive.champions["default"] = champion
    archive._save_all()

    with pytest.raises(ValueError, match="challenger_eligible"):
        archive.add_challenger(_record("challenger-new"), "default")

    archive.add_qualified_challenger(_qualified_record("challenger-new"), "default")

    assert archive.get_champion("default").chromosome_id == "champion-old"
    assert archive.get_challenger("default").chromosome_id == "challenger-new"


def test_manual_promote_requires_pending_acceptance_and_retires_old_champion(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.champions["default"] = _record("champion-old", "champion")
    archive.add_qualified_challenger(_qualified_record("challenger-new"), "default")
    archive._save_all()

    assert archive.promote_challenger("challenger-new", "default") is False
    assert archive.start_validation("challenger-new")
    assert archive.mark_pending_acceptance("challenger-new", {"paper_closed_trades": 20, "paper_pnl": 1.2, "paper_validation_passed": True})
    assert archive.promote_challenger("challenger-new", "default")
    assert archive.get_champion("default").chromosome_id == "challenger-new"
    assert archive.get_challenger("default") is None
    assert archive.retired[-1].chromosome_id == "champion-old"
    assert archive.retired[-1].status == "retired"


def test_runtime_uses_default_without_champion_and_ignores_challenger(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.add_qualified_challenger(_qualified_record("high-fitness-candidate"), "default")

    runtime = archive.get_runtime_chromosome_data("default")
    assert runtime["chromosome_id"] == "builtin_default_default"
    assert built_in_default_chromosome().summary()


def test_runtime_uses_promoted_champion(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.champions["default"] = _record("approved-champion", "champion")
    archive._save_all()

    runtime = archive.get_runtime_chromosome_data("default")
    assert runtime["chromosome_id"] == "approved-champion"


def test_continuous_runtime_export_ignores_research_top_strategies(tmp_path):
    archive = StrategyArchive(str(tmp_path / "archive"))
    engine = EvolutionEngineV2(
        config={"population_size": 1, "symbols": ["BTCUSDT"]},
        archive=archive,
        save_dir=str(tmp_path / "evolution"),
    )
    continuous = ContinuousEvolutionV2.__new__(ContinuousEvolutionV2)
    continuous.engine = engine

    candidate = built_in_default_chromosome()
    candidate.chromosome_id = "unapproved-best"

    from pathlib import Path
    original_cwd = Path.cwd()
    try:
        import os
        os.chdir(tmp_path)
        continuous._deploy_to_paper([candidate])
        data = json.loads(
            (tmp_path / "data/genetic_evolution_v2/live_pool_strategies.json").read_text()
        )
    finally:
        os.chdir(original_cwd)

    assert len(data["strategies"]) == 1
    assert data["strategies"][0]["meta"]["chromosome_id"] == "builtin_default_default"


def test_legacy_direct_deploy_entry_points_are_disabled():
    import pytest
    from app.genetic_engine.hunt_runner import deploy_strategy
    from app.genetic_integration import GeneticIntegration

    with pytest.raises(RuntimeError, match="manually Promote"):
        deploy_strategy(built_in_default_chromosome(), {})

    integration = GeneticIntegration.__new__(GeneticIntegration)
    with pytest.raises(RuntimeError, match="manually Promote"):
        integration.quick_deploy()
