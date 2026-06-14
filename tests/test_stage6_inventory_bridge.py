"""Stage 6 tests: asynchronous clocks, inventory bridge, and ledger conservation."""

from unittest.mock import patch

from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2
from app.genetic_engine.chromosome_v2 import (
    MacroGenes,
    MicroGenes,
    RiskGenesV2,
    mutate_chromosome_v2,
    crossover_chromosomes_v2,
)
from tests.test_stage4_gene_sensitivity import _make_chrom, _make_df


def _bridge_chrom(unlock_threshold: float):
    chrom = _make_chrom(
        macro=MacroGenes(
            t_macro=10,
            t_micro=1,
            t_deadline=3,
            hold_period=999,
            target_weight=0.8,
        ),
        micro=MicroGenes(
            kp=0.8,
            kv=0.1,
            ka=1.0,
            min_trade_threshold=0.0,
        ),
    )
    chrom.risk_genes.dead_hold_ratio = 1.0
    chrom.risk_genes.float_hold_ratio = 0.0
    chrom.risk_genes.unlock_ka_threshold = unlock_threshold
    return chrom


def _run_single_entry(chrom):
    df = _make_df(140)
    df.loc[df.index[102]:, ["open", "high", "low", "close"]] *= 2.0
    engine = GeneBacktestEngineV2(
        initial_capital=1000.0, lot_step=0.0001, lot_min=0.0001
    )
    with patch.object(
        engine,
        "_check_entry_conditions",
        side_effect=lambda i, *_: i == 100,
    ), patch.object(engine, "_check_exit_conditions", return_value=False):
        return engine._run_strategy_v2(df, chrom, "TEST", None, None, False)


def test_dead_hold_unlocks_only_when_ka_acceleration_exceeds_threshold():
    _, trades_low, ledger_low = _run_single_entry(_bridge_chrom(0.001))
    _, trades_high, ledger_high = _run_single_entry(_bridge_chrom(2.0))

    assert ledger_low["unlock_events"]
    assert any(t.exit_reason == "end_of_test" for t in trades_low)
    assert trades_low[-1].entry_price > 0.0
    assert trades_low[-1].pnl_pct != 0.0
    assert ledger_low["dead_hold_qty"] == 0.0

    assert ledger_high["unlock_events"] == []
    assert trades_high == []
    assert ledger_high["dead_hold_qty"] > 0.0
    assert ledger_high["float_hold_qty"] == 0.0


def test_inventory_and_cash_ledger_conservation():
    _, _, ledger = _run_single_entry(_bridge_chrom(2.0))

    assert abs(
        ledger["position_qty"]
        - ledger["dead_hold_qty"]
        - ledger["float_hold_qty"]
    ) < 1e-9

    expected_cash = (
        1000.0
        - ledger["total_buy_notional"]
        - ledger["total_buy_fees"]
        + ledger["total_sell_notional"]
        - ledger["total_sell_fees"]
    )
    assert abs(ledger["cash"] - expected_cash) < 1e-6
    assert abs(
        ledger["final_equity"]
        - ledger["cash"]
        - ledger["position_qty"] * ledger["final_price"]
    ) < 1e-6


def test_macro_micro_deadline_clocks_share_timeline_but_tick_independently():
    _, _, ledger = _run_single_entry(_bridge_chrom(2.0))
    processed = 140 - 100
    assert ledger["macro_ticks"] == len(range(0, processed, 10))
    assert ledger["micro_ticks"] == len(range(0, processed, 1))
    assert ledger["deadline_ticks"] == len(range(0, processed, 3))


def test_bridge_genes_survive_mutation_and_crossover():
    parent1 = _bridge_chrom(0.10)
    parent2 = _bridge_chrom(0.30)
    parent1.risk_genes.dead_hold_ratio = 0.2
    parent1.risk_genes.float_hold_ratio = 0.8
    parent2.risk_genes.dead_hold_ratio = 0.6
    parent2.risk_genes.float_hold_ratio = 0.4
    parent1.fitness_score = 0.5
    parent2.fitness_score = 0.4

    child = crossover_chromosomes_v2(parent1, parent2, generation=1)
    assert child.risk_genes.dead_hold_ratio == 0.4
    assert child.risk_genes.float_hold_ratio == 0.6
    assert child.risk_genes.unlock_ka_threshold == 0.2

    with patch("app.genetic_engine.chromosome_v2.random.random", return_value=0.0):
        mutated = mutate_chromosome_v2(
            parent1, generation=1, mutation_rate=1.0, intensity=0.5
        )
    assert abs(
        mutated.risk_genes.dead_hold_ratio
        + mutated.risk_genes.float_hold_ratio
        - 1.0
    ) < 1e-9
    assert 0.0 <= mutated.risk_genes.unlock_ka_threshold <= 1.0
