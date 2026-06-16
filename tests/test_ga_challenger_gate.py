"""Phase B tests for blocking unqualified GA Challengers."""

from app.genetic_engine.archive import StrategyArchive
from app.genetic_engine.chromosome_v2 import built_in_default_chromosome
from app.genetic_engine.evolution_v2 import EvolutionEngineV2


def _valid_details(**overrides):
    details = {
        "avg_alpha": 0.02,
        "ruin_probability": 0.02,
        "max_drawdown": 0.10,
        "profit_factor": 1.25,
        "sharpe_ratio": 0.8,
        "win_rate": 0.48,
        "total_trades": 300,
        "profitable_symbols": 6,
        "worst_symbol_alpha": -0.02,
        "single_symbol_profit_contribution": 0.40,
        "symbols_tested": 10,
        "data_invalid": False,
    }
    details.update(overrides)
    return details


def _engine(tmp_path, stage):
    archive = StrategyArchive(str(tmp_path / "archive"))
    engine = EvolutionEngineV2(
        config={
            "ga_stage": stage,
            "population_size": 1,
            "symbols": ["BTCUSDT"],
        },
        archive=archive,
        save_dir=str(tmp_path / "evolution"),
    )
    return engine, archive


def _chromosome(chromosome_id, details):
    chrom = built_in_default_chromosome("BTCUSDT")
    chrom.chromosome_id = chromosome_id
    chrom.symbol = "BTCUSDT"
    chrom.fitness_score = details.get("fitness", 0.2)
    chrom.fitness_details = details
    return chrom


def test_bad_challenger_like_current_archive_is_rejected(tmp_path):
    engine, archive = _engine(tmp_path, "stage3_validate")
    chrom = _chromosome(
        "MUT_BAD_RUIN",
        {
            "avg_alpha": -0.0496,
            "ruin_probability": 1.0,
            "total_trades": 2669,
            "symbols_tested": 10,
            "data_invalid": False,
        },
    )

    assert engine._archive_challenger(chrom) is False
    assert archive.get_challenger("BTCUSDT") is None
    assert len(archive.raw_candidates) == 1
    assert len(archive.rejected) == 1
    assert "ruin_probability" in archive.rejected[0].fitness_details["eligibility"]["rejected_reason"]


def test_stage1_passing_candidate_does_not_enter_challenger(tmp_path):
    engine, archive = _engine(tmp_path, "stage1_explore")
    chrom = _chromosome(
        "SEED_STAGE1",
        _valid_details(avg_alpha=-0.005, ruin_probability=0.15, max_drawdown=0.20),
    )

    assert engine._archive_challenger(chrom) is False
    assert archive.get_challenger("BTCUSDT") is None
    assert len(archive.raw_candidates) == 1
    assert archive.seed_candidates[0].chromosome_id == "SEED_STAGE1"
    assert archive.rejected == []
    assert chrom.fitness_details["eligibility"]["candidate_status"] == "seed_candidate"


def test_stage2_passing_candidate_does_not_enter_challenger(tmp_path):
    engine, archive = _engine(tmp_path, "stage2_converge")
    chrom = _chromosome(
        "SEED_STAGE2",
        _valid_details(avg_alpha=0.002, ruin_probability=0.08, max_drawdown=0.15),
    )

    assert engine._archive_challenger(chrom) is False
    assert archive.get_challenger("BTCUSDT") is None
    assert len(archive.raw_candidates) == 1
    assert archive.seed_candidates[0].chromosome_id == "SEED_STAGE2"
    assert archive.rejected == []
    assert chrom.fitness_details["eligibility"]["candidate_status"] == "seed_candidate"


def test_stage3_passing_candidate_enters_challenger(tmp_path):
    engine, archive = _engine(tmp_path, "stage3_validate")
    chrom = _chromosome("GOOD_STAGE3", _valid_details())

    assert engine._archive_challenger(chrom) is True
    assert archive.get_challenger("BTCUSDT").chromosome_id == "GOOD_STAGE3"
    assert archive.get_challenger("BTCUSDT").status == "qualified_challenger"
    assert len(archive.raw_candidates) == 1
    assert archive.rejected == []
    assert chrom.fitness_details["eligibility"]["challenger_eligible"] is True


def test_stage3_missing_metric_is_rejected_not_archived(tmp_path):
    engine, archive = _engine(tmp_path, "stage3_validate")
    details = _valid_details()
    del details["profit_factor"]
    chrom = _chromosome("MISSING_METRIC", details)

    assert engine._archive_challenger(chrom) is False
    assert archive.get_challenger("BTCUSDT") is None
    assert len(archive.raw_candidates) == 1
    assert len(archive.rejected) == 1
    assert "profit_factor" in archive.rejected[0].fitness_details["eligibility"]["rejected_reason"]
