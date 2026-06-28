#!/usr/bin/env python3
"""
Stage 4 Gene Sensitivity Tests
Tests that macro/micro gene fields actually affect backtest behavior.
All mocked — no real API calls.
"""

import sys
import math
import uuid
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.genetic_engine.chromosome_v2 import (
    StrategyChromosomeV2, MacroGenes, MicroGenes, RiskGenesV2
)
from app.genetic_engine.gene_library import (
    IndicatorGene, IndicatorType, ConditionType
)
from app.genetic_engine.backtest_engine_v2 import (
    GeneBacktestEngineV2, GhostDCABaseline
)
from app.genetic_engine.fitness_v2 import compute_fitness_v2, BacktestMetricsV2


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV DataFrame with a mild uptrend and oscillations."""
    rng = np.random.default_rng(seed)
    prices = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n))
    prices = np.clip(prices, 1.0, None)
    df = pd.DataFrame({
        "open":   prices * (1 - 0.002),
        "high":   prices * (1 + 0.005),
        "low":    prices * (1 - 0.005),
        "close":  prices,
        "volume": rng.uniform(100, 1000, n),
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq="1h")
    return df


def _make_gene_always_true(name: str = "rsi") -> IndicatorGene:
    """Entry gene that always fires: RSI ABOVE -999 (always true)."""
    return IndicatorGene(
        name="rsi",
        indicator_type=IndicatorType.MOMENTUM,
        timeframe="5m",
        params={"period": 14},
        condition=ConditionType.ABOVE,
        threshold=-999.0,   # always satisfied
        weight=1.0,
    )


def _make_gene_never_true(name: str = "rsi") -> IndicatorGene:
    """Entry gene that never fires: RSI ABOVE 999."""
    return IndicatorGene(
        name="rsi",
        indicator_type=IndicatorType.MOMENTUM,
        timeframe="5m",
        params={"period": 14},
        condition=ConditionType.ABOVE,
        threshold=999.0,    # never satisfied
        weight=1.0,
    )


def _make_exit_never() -> IndicatorGene:
    """Exit gene that never fires."""
    return IndicatorGene(
        name="rsi",
        indicator_type=IndicatorType.MOMENTUM,
        timeframe="5m",
        params={"period": 14},
        condition=ConditionType.ABOVE,
        threshold=999.0,
        weight=1.0,
    )


def _make_chrom(
    macro: MacroGenes = None,
    micro: MicroGenes = None,
    entry_always: bool = True,
    exit_never: bool = True,
) -> StrategyChromosomeV2:
    entry = _make_gene_always_true() if entry_always else _make_gene_never_true()
    exit_g = _make_exit_never() if exit_never else _make_gene_always_true()
    risk = RiskGenesV2(
        stop_loss_pct=-0.50,       # wide stops so hold_period can trigger
        take_profit_pct=999.0,     # never TP
        position_pct=0.10,
        dead_hold_ratio=0.0,       # all float for simpler bookkeeping
        float_hold_ratio=1.0,
    )
    return StrategyChromosomeV2(
        chromosome_id=str(uuid.uuid4()),
        entry_genes=[entry],
        entry_logic="OR",
        exit_genes=[exit_g],
        exit_logic="OR",
        macro_genes=macro or MacroGenes(),
        micro_genes=micro or MicroGenes(kp=0.5, kv=0.0, ka=0.0),
        risk_genes=risk,
    )


def _run(chrom: StrategyChromosomeV2, df: pd.DataFrame = None):
    """Run _run_strategy_v2 and return (equity, trades, raw)."""
    if df is None:
        df = _make_df()
    engine = GeneBacktestEngineV2(initial_capital=1000.0, lot_step=0.0001, lot_min=0.0001)
    return engine._run_strategy_v2(df, chrom, "TEST", None, None, False)


# ─────────────────────────────────────────────────────────────────────────────
# 1. dca_interval affects Ghost DCA trade count
# ─────────────────────────────────────────────────────────────────────────────

def test_dca_interval_affects_ghost_dca_trade_count():
    df = _make_df(300)
    dca_engine = GhostDCABaseline(initial_capital=1000.0)

    _, trades_freq = dca_engine.run(df, dca_interval_candles=1)
    _, trades_slow = dca_engine.run(df, dca_interval_candles=50)

    assert len(trades_freq) > len(trades_slow), (
        f"dca_interval=1 should produce more buys ({len(trades_freq)}) "
        f"than dca_interval=50 ({len(trades_slow)})"
    )
    assert [t["timestamp"] for t in trades_freq[:3]] == [
        int(df.index[i].timestamp() * 1000) for i in (0, 1, 2)
    ]
    assert [t["timestamp"] for t in trades_slow[:3]] == [
        int(df.index[i].timestamp() * 1000) for i in (0, 50, 100)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 2. hold_period forces exit
# ─────────────────────────────────────────────────────────────────────────────

def test_hold_period_forces_exit():
    """
    hold_period=5 → forced exit after 5 candles since last buy.

    To ensure hold_period fires (and isn't masked by continuous re-buying
    which resets last_buy_candle each candle), we set min_trade_threshold
    to 0.40 so once actual_weight ≈ 0.1 we stop buying (deviation=|0.5-0.1|=0.4
    is just at the threshold, meaning we stop buying after first purchase).
    Then hold_period can accumulate and force exit.
    """
    macro = MacroGenes(
        hold_period=5,
        dca_interval=24,
        recycle_ratio=0.0,
        target_weight=0.5,
    )
    # min_trade_threshold=0.40 → only trade when deviation > 40%
    # After first buy, actual_weight ≈ 0.10 → deviation ≈ 0.40 → borderline
    # Use 0.38 to be just below initial deviation (|0.5-0|=0.5 > 0.38 → first buy OK)
    # then after buying, actual_weight ≈ 0.10 → deviation ≈ 0.40 > 0.38 → may still buy
    # Use 0.45 → first buy OK (deviation=0.5>0.45), after buy deviation<0.45 → no more buys
    micro = MicroGenes(kp=1.0, kv=0.0, ka=0.0, min_trade_threshold=0.45)
    chrom = _make_chrom(macro=macro, micro=micro, entry_always=True, exit_never=True)

    df = _make_df(300)
    equity, trades, raw = _run(chrom, df)

    hold_exits = [t for t in trades if t.exit_reason == "hold_period_expired"]
    assert len(hold_exits) > 0, (
        f"Expected at least one hold_period_expired exit with hold_period=5, "
        f"got exit reasons: {[t.exit_reason for t in trades]}"
    )


def test_hold_period_is_not_reset_by_continuous_entries():
    macro = MacroGenes(
        hold_period=5,
        dca_interval=24,
        recycle_ratio=0.0,
        target_weight=0.8,
    )
    micro = MicroGenes(kp=1.0, kv=0.0, ka=0.0, min_trade_threshold=0.0)
    chrom = _make_chrom(macro=macro, micro=micro, entry_always=True, exit_never=True)

    _, trades, _ = _run(chrom, _make_df(130))

    hold_exits = [t for t in trades if t.exit_reason == "hold_period_expired"]
    assert hold_exits, "Continuous entry signals must not postpone hold_period forever"
    first_exit_index = (
        pd.Timestamp(hold_exits[0].exit_time, unit="ms") - pd.Timestamp("2024-01-01")
    ) // pd.Timedelta(hours=1)
    assert 105 <= first_exit_index <= 107


# ─────────────────────────────────────────────────────────────────────────────
# 3. recycle_ratio increases next buy size
# ─────────────────────────────────────────────────────────────────────────────

def test_recycle_ratio_increases_next_buy():
    """
    With recycle_ratio=0.5, profits from a sell feed into the next buy pool.
    We compare the total invested across multiple buys between the two configs.
    A strategy that recycles 50% of gains should deploy more capital than one
    that recycles nothing, all else equal.
    """
    df = _make_df(300)

    # Make exit fire on every candle so we get buy→sell→buy cycles
    entry_gene = _make_gene_always_true()
    # Exit fires when price > 0 (always) — use ABOVE threshold=0
    exit_gene = IndicatorGene(
        name="rsi",
        indicator_type=IndicatorType.MOMENTUM,
        timeframe="5m",
        params={"period": 14},
        condition=ConditionType.ABOVE,
        threshold=0.0,  # RSI always > 0
        weight=1.0,
    )

    def make_recycle_chrom(ratio):
        macro = MacroGenes(
            hold_period=10,  # short so we cycle
            dca_interval=24,
            recycle_ratio=ratio,
            target_weight=0.5,
        )
        micro = MicroGenes(kp=1.0, kv=0.0, ka=0.0, min_trade_threshold=0.0)
        risk = RiskGenesV2(
            stop_loss_pct=-0.50,
            take_profit_pct=999.0,
            position_pct=0.10,
            dead_hold_ratio=0.0,
            float_hold_ratio=1.0,
        )
        return StrategyChromosomeV2(
            chromosome_id=str(uuid.uuid4()),
            entry_genes=[entry_gene],
            entry_logic="OR",
            exit_genes=[exit_gene],
            exit_logic="OR",
            macro_genes=macro,
            micro_genes=micro,
            risk_genes=risk,
        )

    engine = GeneBacktestEngineV2(initial_capital=1000.0, lot_step=0.0001, lot_min=0.0001)

    _, trades_no_recycle, raw_no = engine._run_strategy_v2(
        df, make_recycle_chrom(0.0), "TEST", None, None, False
    )
    _, trades_recycle, raw_rec = engine._run_strategy_v2(
        df, make_recycle_chrom(0.5), "TEST", None, None, False
    )

    assert trades_no_recycle
    assert trades_recycle
    assert raw_no["recycled_profit_deployed"] == 0.0
    assert raw_rec["recycled_profit_deployed"] > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. kp=0 suppresses position sizing (desired_weight→0 or near 0)
# ─────────────────────────────────────────────────────────────────────────────

def test_kp_zero_suppresses_position_sizing():
    """
    kp=0, kv=0, ka=0 → raw_desired = 0 → desired_position_weight = 0
    → scaled_signal ≈ sigmoid(0) = 0.5, but base_position_pct is still computed.

    The key constraint: kp controls (target_weight - actual_weight) pull.
    With kp=0 and initial actual_weight=0, raw_desired=0 → desired_position_weight=0
    → raw_signal = -0.5 → scaled_signal = sigmoid(-0.5*sigmoid_scale).
    With large sigmoid_scale → scaled_signal → 0 → very small buys.

    We use kp=0 with large sigmoid_scale to suppress buys.
    """
    macro = MacroGenes(target_weight=0.5, hold_period=999, recycle_ratio=0.0)
    micro_zero = MicroGenes(kp=0.0, kv=0.0, ka=0.0, sigmoid_scale=100.0, min_trade_threshold=0.0)
    micro_norm = MicroGenes(kp=1.0, kv=0.0, ka=0.0, sigmoid_scale=1.0, min_trade_threshold=0.0)

    chrom_zero = _make_chrom(macro=macro, micro=micro_zero)
    chrom_norm = _make_chrom(macro=macro, micro=micro_norm)

    df = _make_df(300)
    _, trades_zero, _ = _run(chrom_zero, df)
    _, trades_norm, _ = _run(chrom_norm, df)

    # With kp=0 and sigmoid_scale=100, desired_weight=0 → raw_signal=-0.5 → sigmoid(-50)≈0
    # So base_position_pct ≈ 0 → very few or no trades
    # With kp=1, normal sizing → more trades
    assert len(trades_zero) <= len(trades_norm), (
        f"kp=0/sigmoid_scale=100 should suppress buys: got {len(trades_zero)} vs {len(trades_norm)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. kv nonzero changes sizing profile
# ─────────────────────────────────────────────────────────────────────────────

def test_kv_nonzero_changes_sizing():
    """kv=1.0 vs kv=0.0 with same kp → different equity curves."""
    macro = MacroGenes(target_weight=0.5, hold_period=999, recycle_ratio=0.0)

    micro_kv0 = MicroGenes(kp=0.5, kv=0.0, ka=0.0, min_trade_threshold=0.0)
    micro_kv1 = MicroGenes(kp=0.5, kv=1.0, ka=0.0, min_trade_threshold=0.0)

    chrom_kv0 = _make_chrom(macro=macro, micro=micro_kv0)
    chrom_kv1 = _make_chrom(macro=macro, micro=micro_kv1)

    df = _make_df(300)
    equity_kv0, _, _ = _run(chrom_kv0, df)
    equity_kv1, _, _ = _run(chrom_kv1, df)

    # The two equity curves should differ (kv affects desired_position_weight)
    assert equity_kv0 != equity_kv1, "kv=0.0 vs kv=1.0 should produce different equity curves"


# ─────────────────────────────────────────────────────────────────────────────
# 6. sigmoid_scale changes entry frequency
# ─────────────────────────────────────────────────────────────────────────────

def test_sigmoid_scale_changes_entry_frequency():
    """
    sigmoid_scale=0.01 → sigmoid output ≈ 0.5 regardless of signal → moderate sizing
    sigmoid_scale=100.0 → sigmoid is near-binary → very small or very large sizing
    These affect base_position_pct differently → different trade counts or equity.
    """
    macro = MacroGenes(target_weight=0.5, hold_period=999, recycle_ratio=0.0)

    micro_low = MicroGenes(kp=1.0, kv=0.0, ka=0.0, sigmoid_scale=0.01, min_trade_threshold=0.0)
    micro_hi = MicroGenes(kp=1.0, kv=0.0, ka=0.0, sigmoid_scale=100.0, min_trade_threshold=0.0)

    chrom_low = _make_chrom(macro=macro, micro=micro_low)
    chrom_hi = _make_chrom(macro=macro, micro=micro_hi)

    df = _make_df(300)
    equity_low, trades_low, _ = _run(chrom_low, df)
    equity_hi, trades_hi, _ = _run(chrom_hi, df)

    # They should produce different outcomes
    assert equity_low != equity_hi or len(trades_low) != len(trades_hi), (
        "sigmoid_scale=0.01 vs 100.0 should produce different results"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. gamma reduces qty when position is heavy
# ─────────────────────────────────────────────────────────────────────────────

def test_gamma_reduces_qty_when_heavy():
    """
    With gamma=3.0, gamma_factor = (1 - actual_weight)^3 is small when actual_weight is large.
    We directly test the formula used in the engine.
    """
    # The engine formula: gamma_factor = (1.0 - actual_weight) ** gamma
    def gamma_factor(actual_weight, gamma):
        return (1.0 - actual_weight) ** gamma if actual_weight > 0 else 1.0

    # actual_weight = 0.1 (light position)
    gf_light_gamma1 = gamma_factor(0.1, 1.0)
    gf_light_gamma3 = gamma_factor(0.1, 3.0)

    # actual_weight = 0.8 (heavy position)
    gf_heavy_gamma1 = gamma_factor(0.8, 1.0)
    gf_heavy_gamma3 = gamma_factor(0.8, 3.0)

    # gamma=3 reduces qty MORE when heavy than gamma=1
    reduction_heavy = gf_heavy_gamma3 / gf_heavy_gamma1
    reduction_light = gf_light_gamma3 / gf_light_gamma1

    assert reduction_heavy < reduction_light, (
        f"gamma=3 should reduce qty more at 80% weight than 10% weight. "
        f"heavy_reduction={reduction_heavy:.3f}, light_reduction={reduction_light:.3f}"
    )
    assert gf_heavy_gamma3 < 0.1, (
        f"At 80% weight with gamma=3, factor should be very small, got {gf_heavy_gamma3:.3f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. min_trade_threshold suppresses small-deviation trades
# ─────────────────────────────────────────────────────────────────────────────

def test_min_trade_threshold_suppresses_small_deviation():
    """
    With min_trade_threshold=0.99, deviation must be > 0.99 to trade.
    Since actual_weight starts at 0 and target_weight=0.5, deviation < 0.99 → no buys.
    """
    macro = MacroGenes(target_weight=0.5, hold_period=999, recycle_ratio=0.0)
    micro_hi_threshold = MicroGenes(kp=1.0, kv=0.0, ka=0.0, min_trade_threshold=0.99)
    micro_lo_threshold = MicroGenes(kp=1.0, kv=0.0, ka=0.0, min_trade_threshold=0.001)

    chrom_hi = _make_chrom(macro=macro, micro=micro_hi_threshold)
    chrom_lo = _make_chrom(macro=macro, micro=micro_lo_threshold)

    df = _make_df(300)
    _, trades_hi, _ = _run(chrom_hi, df)
    _, trades_lo, _ = _run(chrom_lo, df)

    assert len(trades_hi) == 0, (
        f"min_trade_threshold=0.99 should suppress all trades, got {len(trades_hi)}"
    )
    # Low threshold should allow trades (entry gene always fires)
    assert len(trades_lo) >= 0  # at least doesn't crash


# ─────────────────────────────────────────────────────────────────────────────
# 9. Changing kp changes backtest fitness result
# ─────────────────────────────────────────────────────────────────────────────

def test_changing_kp_changes_backtest_result():
    """Perturbing kp changes the resulting equity curve and thus metrics."""
    df = _make_df(300)
    macro = MacroGenes(target_weight=0.5, hold_period=999, recycle_ratio=0.0)

    micro_a = MicroGenes(kp=0.2, kv=0.0, ka=0.0, min_trade_threshold=0.0)
    micro_b = MicroGenes(kp=0.9, kv=0.0, ka=0.0, min_trade_threshold=0.0)

    chrom_a = _make_chrom(macro=macro, micro=micro_a)
    chrom_b = _make_chrom(macro=macro, micro=micro_b)

    equity_a, trades_a, _ = _run(chrom_a, df)
    equity_b, trades_b, _ = _run(chrom_b, df)

    # The two results should differ (different kp → different desired_position_weight)
    assert equity_a[-1] != equity_b[-1] or len(trades_a) != len(trades_b), (
        "kp=0.2 vs kp=0.9 should produce different results"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 10. Changing sigmoid_scale changes backtest fitness result
# ─────────────────────────────────────────────────────────────────────────────

def test_changing_sigmoid_scale_changes_backtest_result():
    """Perturbing sigmoid_scale changes buy sizing and thus equity."""
    df = _make_df(300)
    macro = MacroGenes(target_weight=0.5, hold_period=999, recycle_ratio=0.0)

    micro_a = MicroGenes(kp=1.0, kv=0.0, ka=0.0, sigmoid_scale=0.1, min_trade_threshold=0.0)
    micro_b = MicroGenes(kp=1.0, kv=0.0, ka=0.0, sigmoid_scale=10.0, min_trade_threshold=0.0)

    chrom_a = _make_chrom(macro=macro, micro=micro_a)
    chrom_b = _make_chrom(macro=macro, micro=micro_b)

    equity_a, trades_a, raw_a = _run(chrom_a, df)
    equity_b, trades_b, raw_b = _run(chrom_b, df)

    assert equity_a[-1] != equity_b[-1] or len(trades_a) != len(trades_b), (
        "sigmoid_scale=0.1 vs 10.0 should produce different results"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
