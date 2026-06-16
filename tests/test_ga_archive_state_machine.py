"""Phase C tests for GA archive lifecycle state machine."""

import json

import pytest

from app.genetic_engine.archive import (
    CHAMPION,
    PENDING_ACCEPTANCE,
    QUALIFIED_CHALLENGER,
    REJECTED,
    RETIRED,
    SEED_CANDIDATE,
    VALIDATING,
    ArchiveRecord,
    StrategyArchive,
)
from app.genetic_engine.chromosome_v2 import built_in_default_chromosome
from app.genetic_engine.evolution_v2 import EvolutionEngineV2


def _record(chromosome_id: str, status: str = "raw_candidate", **details) -> ArchiveRecord:
    chrom = built_in_default_chromosome("BTCUSDT")
    chrom.chromosome_id = chromosome_id
    fitness_details = {
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
        "eligibility": {"challenger_eligible": True},
    }
    fitness_details.update(details)
    return ArchiveRecord(
        chromosome_id=chromosome_id,
        status=status,
        epoch_id="epoch_test",
        generation=1,
        fitness_score=0.8,
        fitness_details=fitness_details,
        chromosome_data=chrom.to_dict(),
    )


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


def test_raw_candidate_can_be_added_and_reloaded(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.add_raw_candidate(_record("RAW_1"), "BTCUSDT")

    reloaded = StrategyArchive(str(tmp_path))
    assert reloaded.raw_candidates[0].chromosome_id == "RAW_1"
    assert reloaded.raw_candidates[0].status == "raw_candidate"


def test_seed_candidate_can_be_added_and_reloaded(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.add_seed_candidate(_record("SEED_1"), "BTCUSDT")

    reloaded = StrategyArchive(str(tmp_path))
    assert reloaded.seed_candidates[0].chromosome_id == "SEED_1"
    assert reloaded.seed_candidates[0].status == SEED_CANDIDATE


def test_rejected_preserves_failed_rules_and_reason(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    failed_rules = [{"metric": "ruin_probability", "actual": 1.0, "required": "<= 0.5"}]
    archive.add_rejected(
        _record("BAD_1"),
        "BTCUSDT",
        failed_rules=failed_rules,
        rejected_reason="ruin_probability above direct reject threshold",
    )

    reloaded = StrategyArchive(str(tmp_path))
    rejected = reloaded.rejected[0]
    assert rejected.status == REJECTED
    assert rejected.fitness_details["failed_rules"] == failed_rules
    assert "ruin_probability" in rejected.fitness_details["rejected_reason"]


def test_stage1_goes_to_seed_candidate_not_qualified(tmp_path):
    engine, archive = _engine(tmp_path, "stage1_explore")
    chrom = built_in_default_chromosome("BTCUSDT")
    chrom.chromosome_id = "STAGE1"
    chrom.symbol = "BTCUSDT"
    chrom.fitness_score = 0.2
    chrom.fitness_details = _record("STAGE1").fitness_details
    chrom.fitness_details.update({
        "avg_alpha": -0.005,
        "ruin_probability": 0.15,
        "max_drawdown": 0.20,
    })

    assert engine._archive_challenger(chrom) is False
    assert archive.seed_candidates[0].chromosome_id == "STAGE1"
    assert archive.get_qualified_challenger("BTCUSDT") is None


def test_stage2_goes_to_seed_candidate_not_qualified(tmp_path):
    engine, archive = _engine(tmp_path, "stage2_converge")
    chrom = built_in_default_chromosome("BTCUSDT")
    chrom.chromosome_id = "STAGE2"
    chrom.symbol = "BTCUSDT"
    chrom.fitness_score = 0.2
    chrom.fitness_details = _record("STAGE2").fitness_details
    chrom.fitness_details.update({
        "avg_alpha": 0.002,
        "ruin_probability": 0.08,
        "max_drawdown": 0.15,
    })

    assert engine._archive_challenger(chrom) is False
    assert archive.seed_candidates[0].chromosome_id == "STAGE2"
    assert archive.get_qualified_challenger("BTCUSDT") is None


def test_stage3_goes_to_qualified_challenger(tmp_path):
    engine, archive = _engine(tmp_path, "stage3_validate")
    chrom = built_in_default_chromosome("BTCUSDT")
    chrom.chromosome_id = "STAGE3"
    chrom.symbol = "BTCUSDT"
    chrom.fitness_score = 0.2
    chrom.fitness_details = _record("STAGE3").fitness_details

    assert engine._archive_challenger(chrom) is True
    assert archive.get_qualified_challenger("BTCUSDT").chromosome_id == "STAGE3"
    assert archive.get_qualified_challenger("BTCUSDT").status == QUALIFIED_CHALLENGER


def test_qualified_challenger_can_enter_validation(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.add_qualified_challenger(_record("QUAL_1", QUALIFIED_CHALLENGER), "BTCUSDT")

    assert archive.start_validation("QUAL_1")
    assert archive.validating["BTCUSDT"].status == VALIDATING
    assert archive.get_qualified_challenger("BTCUSDT") is None


def test_validating_can_mark_pending_acceptance_with_paper_metrics(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.add_qualified_challenger(_record("PAPER_1", QUALIFIED_CHALLENGER), "BTCUSDT")
    archive.start_validation("PAPER_1")

    metrics = {"paper_closed_trades": 22, "paper_pnl": 3.4, "paper_max_drawdown": 0.05}
    assert archive.mark_pending_acceptance("PAPER_1", metrics)
    pending = archive.pending_acceptance["BTCUSDT"]
    assert pending.status == PENDING_ACCEPTANCE
    assert pending.paper_metrics == metrics
    assert pending.paper_trades == 22
    assert pending.paper_pnl == 3.4


def test_only_pending_acceptance_can_promote_to_champion(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.add_qualified_challenger(_record("NOT_PENDING", QUALIFIED_CHALLENGER), "BTCUSDT")

    assert archive.promote_to_champion("NOT_PENDING", "BTCUSDT") is False
    assert archive.get_champion("BTCUSDT") is None

    archive.start_validation("NOT_PENDING")
    archive.mark_pending_acceptance("NOT_PENDING", {"paper_closed_trades": 20, "paper_pnl": 1.0})
    assert archive.promote_to_champion("NOT_PENDING", "BTCUSDT")
    assert archive.get_champion("BTCUSDT").status == CHAMPION


def test_promote_retires_existing_champion(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    archive.champions["BTCUSDT"] = _record("OLD_CHAMP", CHAMPION)
    archive._save_all()

    archive.add_qualified_challenger(_record("NEW_CHAMP", QUALIFIED_CHALLENGER), "BTCUSDT")
    archive.start_validation("NEW_CHAMP")
    archive.mark_pending_acceptance("NEW_CHAMP", {"paper_closed_trades": 20, "paper_pnl": 1.0})

    assert archive.promote_to_champion("NEW_CHAMP", "BTCUSDT")
    assert archive.get_champion("BTCUSDT").chromosome_id == "NEW_CHAMP"
    assert archive.retired[-1].chromosome_id == "OLD_CHAMP"
    assert archive.retired[-1].status == RETIRED


def test_add_challenger_cannot_bypass_eligibility(tmp_path):
    archive = StrategyArchive(str(tmp_path))
    unsafe = _record("UNSAFE", QUALIFIED_CHALLENGER)
    unsafe.fitness_details = {}

    with pytest.raises(ValueError, match="challenger_eligible"):
        archive.add_challenger(unsafe, "BTCUSDT")


def test_legacy_challengers_champions_retired_still_load(tmp_path):
    challenger = _record("LEGACY_CHALLENGER", "challenger").to_dict()
    champion = _record("LEGACY_CHAMP", CHAMPION).to_dict()
    retired = _record("LEGACY_RETIRED", RETIRED).to_dict()

    (tmp_path / "challengers.json").write_text(
        json.dumps({"BTCUSDT": challenger}),
        encoding="utf-8",
    )
    (tmp_path / "champions.json").write_text(
        json.dumps({"BTCUSDT": champion}),
        encoding="utf-8",
    )
    (tmp_path / "retired.json").write_text(json.dumps([retired]), encoding="utf-8")

    archive = StrategyArchive(str(tmp_path))
    assert archive.get_qualified_challenger("BTCUSDT").chromosome_id == "LEGACY_CHALLENGER"
    assert archive.get_qualified_challenger("BTCUSDT").status == QUALIFIED_CHALLENGER
    assert archive.get_champion("BTCUSDT").chromosome_id == "LEGACY_CHAMP"
    assert archive.retired[0].chromosome_id == "LEGACY_RETIRED"
