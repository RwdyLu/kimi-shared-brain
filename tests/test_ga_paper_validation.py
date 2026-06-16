"""Phase D tests for GA Shadow/Paper validation lifecycle."""

from pathlib import Path

from app.genetic_engine.archive import (
    CHAMPION,
    QUALIFIED_CHALLENGER,
    REJECTED,
    SEED_CANDIDATE,
    ArchiveRecord,
    StrategyArchive,
)
from app.genetic_engine.chromosome_v2 import built_in_default_chromosome
from app.genetic_engine.paper_validation import (
    PaperValidationManager,
    default_paper_metrics,
)


def _record(chromosome_id: str, status: str = QUALIFIED_CHALLENGER) -> ArchiveRecord:
    chrom = built_in_default_chromosome("BTCUSDT")
    chrom.chromosome_id = chromosome_id
    return ArchiveRecord(
        chromosome_id=chromosome_id,
        status=status,
        epoch_id="epoch_test",
        generation=1,
        fitness_score=0.8,
        fitness_details={
            "ruin_probability": 0.01,
            "eligibility": {"challenger_eligible": True},
        },
        chromosome_data=chrom.to_dict(),
    )


def _archive_with_qualified(tmp_path, chromosome_id="QUAL_1"):
    archive = StrategyArchive(str(tmp_path / "archive"))
    archive.add_qualified_challenger(_record(chromosome_id), "BTCUSDT")
    return archive


def _passing_metrics(**overrides):
    metrics = default_paper_metrics("2026-06-01T00:00:00")
    metrics.update({
        "paper_days": 14,
        "paper_trades": 24,
        "paper_closed_trades": 22,
        "paper_open_trades": 2,
        "paper_pnl": 1.2,
        "paper_gross_pnl": 1.6,
        "paper_fees": 0.2,
        "paper_slippage": 0.2,
        "paper_max_drawdown": 0.08,
        "paper_win_rate": 0.45,
        "paper_profit_factor": 1.10,
        "paper_symbols_traded": ["BTCUSDT", "ETHUSDT"],
    })
    metrics.update(overrides)
    return metrics


def test_qualified_challenger_can_start_validation(tmp_path):
    archive = _archive_with_qualified(tmp_path, "QUAL_START")
    manager = PaperValidationManager(archive=archive)

    assert manager.start_paper_validation("QUAL_START")
    assert archive.get_qualified_challenger("BTCUSDT") is None
    assert archive.validating["BTCUSDT"].chromosome_id == "QUAL_START"
    assert archive.validating["BTCUSDT"].paper_metrics["paper_days"] == 0


def test_non_qualified_records_cannot_start_validation(tmp_path):
    archive = StrategyArchive(str(tmp_path / "archive"))
    archive.add_raw_candidate(_record("RAW_1", "raw_candidate"), "BTCUSDT")
    archive.add_seed_candidate(_record("SEED_1", SEED_CANDIDATE), "BTCUSDT")
    archive.add_rejected(_record("BAD_1", REJECTED), "BTCUSDT", rejected_reason="bad")
    manager = PaperValidationManager(archive=archive)

    assert manager.start_paper_validation("RAW_1") is False
    assert manager.start_paper_validation("SEED_1") is False
    assert manager.start_paper_validation("BAD_1") is False


def test_validating_can_update_paper_metrics(tmp_path):
    archive = _archive_with_qualified(tmp_path, "UPDATE_1")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("UPDATE_1")

    assert manager.update_paper_metrics("UPDATE_1", _passing_metrics(paper_days=3))
    record = archive.validating["BTCUSDT"]
    assert record.paper_metrics["paper_days"] == 3
    assert record.paper_metrics["paper_symbols_traded"] == ["BTCUSDT", "ETHUSDT"]


def test_paper_days_below_threshold_does_not_pending(tmp_path):
    archive = _archive_with_qualified(tmp_path, "DAYS_LOW")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("DAYS_LOW")
    manager.update_paper_metrics("DAYS_LOW", _passing_metrics(paper_days=13))

    assert manager.mark_pending_acceptance_if_passed("DAYS_LOW") is False
    assert "BTCUSDT" not in archive.pending_acceptance
    assert "paper_days" in {rule["metric"] for rule in archive.validating["BTCUSDT"].paper_metrics["paper_validation_failed_rules"]}


def test_closed_trades_below_threshold_does_not_pending(tmp_path):
    archive = _archive_with_qualified(tmp_path, "TRADES_LOW")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("TRADES_LOW")
    manager.update_paper_metrics("TRADES_LOW", _passing_metrics(paper_closed_trades=19))

    assert manager.mark_pending_acceptance_if_passed("TRADES_LOW") is False


def test_non_positive_pnl_does_not_pending(tmp_path):
    archive = _archive_with_qualified(tmp_path, "PNL_LOW")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("PNL_LOW")
    manager.update_paper_metrics("PNL_LOW", _passing_metrics(paper_pnl=0.0))

    assert manager.mark_pending_acceptance_if_passed("PNL_LOW") is False


def test_drawdown_above_threshold_does_not_pending(tmp_path):
    archive = _archive_with_qualified(tmp_path, "DD_HIGH")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("DD_HIGH")
    manager.update_paper_metrics("DD_HIGH", _passing_metrics(paper_max_drawdown=0.11))

    assert manager.mark_pending_acceptance_if_passed("DD_HIGH") is False


def test_ruin_probability_above_threshold_does_not_pending(tmp_path):
    archive = StrategyArchive(str(tmp_path / "archive"))
    record = _record("RUIN_HIGH")
    record.fitness_details["ruin_probability"] = 0.03
    archive.add_qualified_challenger(record, "BTCUSDT")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("RUIN_HIGH")
    manager.update_paper_metrics("RUIN_HIGH", _passing_metrics())

    assert manager.mark_pending_acceptance_if_passed("RUIN_HIGH") is False


def test_passing_validation_moves_to_pending_acceptance(tmp_path):
    archive = _archive_with_qualified(tmp_path, "PASS_1")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("PASS_1")
    manager.update_paper_metrics("PASS_1", _passing_metrics())

    assert manager.mark_pending_acceptance_if_passed("PASS_1")
    pending = archive.pending_acceptance["BTCUSDT"]
    assert pending.chromosome_id == "PASS_1"
    assert pending.paper_metrics["paper_validation_passed"] is True


def test_pending_acceptance_only_can_promote_to_champion(tmp_path):
    archive = _archive_with_qualified(tmp_path, "PROMOTE_1")
    manager = PaperValidationManager(archive=archive)

    assert archive.promote_to_champion("PROMOTE_1", "BTCUSDT") is False
    manager.start_paper_validation("PROMOTE_1")
    manager.update_paper_metrics("PROMOTE_1", _passing_metrics())
    manager.mark_pending_acceptance_if_passed("PROMOTE_1")

    assert archive.promote_to_champion("PROMOTE_1", "BTCUSDT")
    assert archive.get_champion("BTCUSDT").status == CHAMPION


def test_phase_d_does_not_touch_existing_paper_trading_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    paper_state = state_dir / "paper_trading_state.json"
    paper_state.write_text('{"do_not_touch": true}', encoding="utf-8")
    before = paper_state.read_text(encoding="utf-8")

    archive = _archive_with_qualified(tmp_path, "NO_STATE_TOUCH")
    manager = PaperValidationManager(archive=archive)
    manager.start_paper_validation("NO_STATE_TOUCH")
    manager.update_paper_metrics("NO_STATE_TOUCH", _passing_metrics())
    manager.mark_pending_acceptance_if_passed("NO_STATE_TOUCH")

    assert paper_state.read_text(encoding="utf-8") == before
