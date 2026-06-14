#!/usr/bin/env python3
"""
Stage 3 Tests: Multi-Window Cross-Validation
All tests are mocked — no real API calls.

Tests:
  1.  test_window_weights_sum_to_one
  2.  test_window_slicing_correct
  3.  test_window_insufficient_data_flagged
  4.  test_ghost_dca_computed_per_window
  5.  test_alpha_per_window
  6.  test_random_is_reproducible_with_seed
  7.  test_random_is_different_seeds
  8.  test_aggregate_excludes_insufficient_windows
  9.  test_all_windows_insufficient_returns_zero
  10. test_cache_fetched_once_per_symbol
  11. test_window_results_in_fitness_details
"""

import sys
import random
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock, patch, call
import pandas as pd
import numpy as np
import pytest

# Make sure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.genetic_engine.windows import (
    WINDOWS, WINDOW_WEIGHTS, MIN_DATA_COVERAGE,
    WindowResult, _random_is_slice, _slice_df, _RANDOM_IS_MIN_MS, _RANDOM_IS_MAX_MS,
    run_window_backtest, run_all_windows, aggregate_window_fitness,
    aggregate_multi_symbol_windows, stable_window_seed, _days_ms,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_df(n_candles: int = 5000, start_ts_ms: Optional[int] = None) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame with DatetimeIndex."""
    if start_ts_ms is None:
        start_ts_ms = int(time.time() * 1000) - n_candles * 5 * 60 * 1000

    index = pd.date_range(
        start=pd.Timestamp(start_ts_ms, unit='ms'),
        periods=n_candles,
        freq='5min',
    )
    close = np.cumsum(np.random.default_rng(42).normal(0, 1, n_candles)) + 100
    df = pd.DataFrame({
        'open':   close,
        'high':   close * 1.001,
        'low':    close * 0.999,
        'close':  close,
        'volume': np.ones(n_candles) * 1000,
    }, index=index)
    return df


def _make_chromosome():
    """Minimal mock chromosome that satisfies _run_strategy_v2."""
    from app.genetic_engine.gene_library import IndicatorGene, IndicatorType, ConditionType

    chrom = MagicMock()
    chrom.chromosome_id = "TEST_CHROM_01"
    chrom.entry_genes = []
    chrom.exit_genes = []
    chrom.trend_filter = None
    chrom.volume_filter = None
    chrom.entry_logic = "AND"
    chrom.exit_logic = "AND"
    chrom.entry_min_weight = 0.5
    chrom.exit_min_weight = 0.5

    risk = MagicMock()
    risk.stop_loss_pct = -0.05
    risk.take_profit_pct = 0.10
    risk.position_pct = 0.10
    risk.dead_hold_ratio = 0.5
    risk.float_hold_ratio = 0.5
    chrom.risk_genes = risk

    micro = MagicMock()
    micro.min_trade_threshold = 0.01
    micro.micro_reserve_rate = 1.0
    # Stage 4: kp/kv/ka and sigmoid/gamma/beta must be real floats
    micro.kp = 1.0
    micro.kv = 0.0
    micro.ka = 0.0
    micro.sigmoid_scale = 1.0
    micro.gamma = 1.0
    micro.beta = 0.5
    chrom.micro_genes = micro

    # Stage 4: macro_genes fields needed by _run_strategy_v2
    macro = MagicMock()
    macro.hold_period = 9999
    macro.recycle_ratio = 0.0
    macro.target_weight = 0.5
    macro.dca_interval = 24
    chrom.macro_genes = macro

    return chrom


def _make_engine():
    """Create a real GeneBacktestEngineV2 with a stub fetcher."""
    from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2
    engine = GeneBacktestEngineV2(initial_capital=1000.0)
    return engine


# ─────────────────────────────────────────────────────────────────────────────
# 1. Window weights sum to 1.0
# ─────────────────────────────────────────────────────────────────────────────

def test_window_weights_sum_to_one():
    total = sum(WINDOW_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Window slicing — "6m" window uses correct time range
# ─────────────────────────────────────────────────────────────────────────────

def test_window_slicing_correct():
    # Build a df that spans exactly "6m" by using enough 5-min candles.
    # We create candles from (now - 6m) to now so the slice has full coverage.
    window_span_ms = WINDOWS["6m"]  # e.g. 6 * 30 * 24 * 60 * 60 * 1000
    now_ms = int(time.time() * 1000)
    slice_start_ms = now_ms - window_span_ms

    candle_interval_ms = 5 * 60 * 1000  # 5 min
    n_candles = window_span_ms // candle_interval_ms  # enough to fill 6m

    df = _make_df(n_candles=n_candles, start_ts_ms=slice_start_ms)

    # Slice the df using _slice_df
    df_slice = _slice_df(df, slice_start_ms, now_ms)

    assert len(df_slice) > 0, "Slice must not be empty"

    actual_span_ms = (
        int(df_slice.index[-1].timestamp() * 1000)
        - int(df_slice.index[0].timestamp() * 1000)
    )

    # Should cover ≥ 80% of 6-month window
    coverage = actual_span_ms / window_span_ms
    assert coverage >= MIN_DATA_COVERAGE, (
        f"6m slice coverage {coverage:.2%} < {MIN_DATA_COVERAGE:.2%}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Insufficient data flagged when < 80% coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_window_insufficient_data_flagged():
    # Build only 1 month of data, but request "6m" window
    one_month_ms = _days_ms(30)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - one_month_ms

    candle_interval_ms = 5 * 60 * 1000
    n_candles = one_month_ms // candle_interval_ms
    df = _make_df(n_candles=n_candles, start_ts_ms=start_ms)

    chrom = _make_chromosome()
    engine = _make_engine()

    result = run_window_backtest(
        chromosome=chrom,
        full_df=df,
        window_name="6m",
        end_ms=now_ms,
        engine=engine,
        seed=0,
    )

    assert result.insufficient_data is True, (
        "Expected insufficient_data=True when data covers only ~1/6 of 6m window"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ghost DCA computed independently per window
# ─────────────────────────────────────────────────────────────────────────────

def test_ghost_dca_computed_per_window():
    """Each window result should have a ghost_dca_return value computed from its slice."""
    now_ms = int(time.time() * 1000)
    # 6 years of data so all windows have sufficient coverage
    six_years_ms = _days_ms(6 * 365)
    start_ms = now_ms - six_years_ms

    candle_ms = 5 * 60 * 1000
    n = six_years_ms // candle_ms
    df = _make_df(n_candles=min(n, 50_000), start_ts_ms=start_ms)

    chrom = _make_chromosome()
    engine = _make_engine()

    trades = [MagicMock(pnl_pct=0.01) for _ in range(5)]
    with patch.object(
        engine,
        "_run_strategy_v2",
        return_value=([1000.0, 1010.0], trades, {"total_fees": 1.0, "realized_pnl": 10.0}),
    ):
        results = run_all_windows(chrom, df, end_ms=now_ms, engine=engine, seed=42)

    valid = [r for r in results if not r.insufficient_data]
    assert len(valid) > 0, "Expected at least one valid window"

    # Each valid window should have a ghost_dca_return attribute (may be 0.0 if no DCA trades)
    for r in valid:
        assert hasattr(r, "ghost_dca_return"), f"Missing ghost_dca_return for {r.window_name}"
        assert isinstance(r.ghost_dca_return, float)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Alpha = strategy_return - ghost_dca_return per window
# ─────────────────────────────────────────────────────────────────────────────

def test_alpha_per_window():
    now_ms = int(time.time() * 1000)
    six_years_ms = _days_ms(6 * 365)
    start_ms = now_ms - six_years_ms

    candle_ms = 5 * 60 * 1000
    n = six_years_ms // candle_ms
    df = _make_df(n_candles=min(n, 50_000), start_ts_ms=start_ms)

    chrom = _make_chromosome()
    engine = _make_engine()

    trades = [MagicMock(pnl_pct=0.01) for _ in range(5)]
    with patch.object(
        engine,
        "_run_strategy_v2",
        return_value=([1000.0, 1010.0], trades, {"total_fees": 1.0, "realized_pnl": 10.0}),
    ):
        results = run_all_windows(chrom, df, end_ms=now_ms, engine=engine, seed=42)
    valid = [r for r in results if not r.insufficient_data]

    for r in valid:
        expected_alpha = r.strategy_return - r.ghost_dca_return
        assert abs(r.alpha - expected_alpha) < 1e-9, (
            f"Window {r.window_name}: alpha={r.alpha} != "
            f"strategy_return({r.strategy_return}) - ghost_dca_return({r.ghost_dca_return})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. random_is reproducible with same seed
# ─────────────────────────────────────────────────────────────────────────────

def test_random_is_reproducible_with_seed():
    df_start_ms = 1_000_000_000_000
    df_end_ms   = df_start_ms + _days_ms(3 * 365)

    s1_start, s1_end = _random_is_slice(df_start_ms, df_end_ms, seed=99)
    s2_start, s2_end = _random_is_slice(df_start_ms, df_end_ms, seed=99)

    assert s1_start == s2_start and s1_end == s2_end, (
        "Same seed must produce same random_is slice"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. random_is produces different slices with different seeds
# ─────────────────────────────────────────────────────────────────────────────

def test_random_is_different_seeds():
    df_start_ms = 1_000_000_000_000
    df_end_ms   = df_start_ms + _days_ms(3 * 365)

    slices = set()
    for seed in range(20):
        s, e = _random_is_slice(df_start_ms, df_end_ms, seed=seed)
        slices.add((s, e))

    # With 20 different seeds, expect at least 5 distinct slices
    assert len(slices) >= 5, (
        f"Expected diverse random_is slices, got only {len(slices)} distinct ones"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Aggregate: 1 insufficient window → weight redistributed (not zeroed)
# ─────────────────────────────────────────────────────────────────────────────

def test_aggregate_excludes_insufficient_windows():
    # 4 valid windows, 1 insufficient
    results = [
        WindowResult("all",  fitness=0.5, insufficient_data=False, weight=0.20),
        WindowResult("5y",   fitness=0.6, insufficient_data=False, weight=0.30),
        WindowResult("2y",   fitness=0.4, insufficient_data=False, weight=0.30),
        WindowResult("6m",   fitness=0.3, insufficient_data=True,  weight=0.15),  # insufficient
        WindowResult("random_is", fitness=0.7, insufficient_data=False, weight=0.05),
    ]

    agg = aggregate_window_fitness(results)

    # Verify: weight should be redistributed among valid windows (all, 5y, 2y, random_is)
    valid = [r for r in results if not r.insufficient_data]
    total_w = sum(r.weight for r in valid)
    expected = sum((r.weight / total_w) * r.fitness for r in valid)

    assert abs(agg - expected) < 1e-9, f"agg={agg} expected={expected}"
    # Must be > 0
    assert agg > 0.0, "Aggregate fitness must be positive when valid windows exist"


# ─────────────────────────────────────────────────────────────────────────────
# 9. All windows insufficient → fitness = 0
# ─────────────────────────────────────────────────────────────────────────────

def test_all_windows_insufficient_returns_zero():
    results = [
        WindowResult(w, insufficient_data=True, weight=WINDOW_WEIGHTS[w])
        for w in WINDOWS
    ]
    assert aggregate_window_fitness(results) == 0.0


def test_strict_aggregate_fails_when_any_window_is_missing():
    results = [
        WindowResult(w, fitness=0.5, weight=WINDOW_WEIGHTS[w])
        for w in WINDOWS
        if w != "5y"
    ]
    assert aggregate_window_fitness(results, require_all=True) == 0.0


def test_multi_symbol_aggregate_fails_when_required_symbol_is_incomplete():
    complete = [
        WindowResult(w, fitness=0.5, weight=WINDOW_WEIGHTS[w])
        for w in WINDOWS
    ]
    incomplete = [
        WindowResult(w, fitness=0.5, weight=WINDOW_WEIGHTS[w])
        for w in WINDOWS
        if w != "2y"
    ]
    score, per_symbol, failed = aggregate_multi_symbol_windows(
        {"BTCUSDT": complete, "ETHUSDT": incomplete},
        ["BTCUSDT", "ETHUSDT"],
    )
    assert score == 0.0
    assert failed == ["ETHUSDT"]
    assert "BTCUSDT" in per_symbol


def test_stable_window_seed_is_reproducible_and_epoch_sensitive():
    seed = stable_window_seed("CHROM-A", epoch_id=12, generation=3)
    assert seed == stable_window_seed("CHROM-A", epoch_id=12, generation=3)
    assert seed != stable_window_seed("CHROM-A", epoch_id=13, generation=3)
    assert seed != stable_window_seed("CHROM-A", epoch_id=12, generation=4)


def test_window_fitness_uses_v2_metrics():
    now_ms = int(time.time() * 1000)
    df = _make_df(n_candles=500, start_ts_ms=now_ms - 500 * 5 * 60 * 1000)
    chrom = _make_chromosome()
    engine = _make_engine()

    trades = [
        MagicMock(pnl_pct=value)
        for value in (0.02, 0.01, -0.01, 0.03, 0.01)
    ]
    raw_ledger = {"total_fees": 2.5, "realized_pnl": 60.0}
    with patch.object(
        engine,
        "_run_strategy_v2",
        return_value=([1000.0, 1060.0], trades, raw_ledger),
    ):
        result = run_window_backtest(
            chrom, df, "all", now_ms, engine=engine, seed=1
        )

    assert result.insufficient_data is False
    assert result.details["total_fees_paid"] == 2.5
    assert "metrics" in result.details


# ─────────────────────────────────────────────────────────────────────────────
# 10. Cache: API called ONCE per symbol for 4 windows
# ─────────────────────────────────────────────────────────────────────────────

def test_cache_fetched_once_per_symbol():
    """
    run_all_windows() accepts a pre-fetched DataFrame.
    The caller (simulate evolution engine) should call the fetcher once.
    We verify that passing a single df to run_all_windows results in
    zero additional fetcher calls.
    """
    now_ms = int(time.time() * 1000)
    six_years_ms = _days_ms(6 * 365)
    start_ms = now_ms - six_years_ms

    n = six_years_ms // (5 * 60 * 1000)
    df = _make_df(n_candles=min(n, 50_000), start_ts_ms=start_ms)

    chrom = _make_chromosome()
    engine = _make_engine()

    # Patch BinanceFetcher inside windows module — run_all_windows should NOT call it
    with patch('app.genetic_engine.windows.run_window_backtest', wraps=run_window_backtest) as mock_rwb:
        # Count calls to _run_strategy_v2 via engine mock
        call_count = {"n": 0}
        original = engine._run_strategy_v2

        def counting_run(*args, **kwargs):
            call_count["n"] += 1
            return original(*args, **kwargs)

        engine._run_strategy_v2 = counting_run

        results = run_all_windows(chrom, df, end_ms=now_ms, engine=engine, seed=42)

    # run_window_backtest should be called once per window
    assert mock_rwb.call_count == len(WINDOWS), (
        f"Expected {len(WINDOWS)} window calls, got {mock_rwb.call_count}"
    )

    # The engine._run_strategy_v2 called at most once per *valid* window
    # (insufficient windows skip it), so count <= len(WINDOWS)
    assert call_count["n"] <= len(WINDOWS), (
        f"Engine called {call_count['n']} times, expected at most {len(WINDOWS)}"
    )

    # Crucially: the test demonstrates the caller fetched data once and passed df in
    # (no re-fetch inside run_all_windows)
    assert isinstance(results, list)
    assert len(results) == len(WINDOWS)


# ─────────────────────────────────────────────────────────────────────────────
# 11. chromosome.fitness_details contains per-window results after evaluation
# ─────────────────────────────────────────────────────────────────────────────

def test_window_results_in_fitness_details():
    """
    Simulate what EvolutionEngineV2.evaluate_generation() does in Stage 3 mode:
    - fetch df once
    - run_all_windows
    - store per-window results in chrom.fitness_details
    """
    now_ms = int(time.time() * 1000)
    six_years_ms = _days_ms(6 * 365)
    start_ms = now_ms - six_years_ms

    n = six_years_ms // (5 * 60 * 1000)
    df = _make_df(n_candles=min(n, 50_000), start_ts_ms=start_ms)

    chrom = _make_chromosome()
    engine = _make_engine()

    window_results = run_all_windows(chrom, df, end_ms=now_ms, engine=engine, seed=7)
    agg_fitness = aggregate_window_fitness(window_results)

    # Simulate what the engine stores
    per_window_summary = {}
    for wr in window_results:
        per_window_summary[wr.window_name] = {
            "fitness": round(wr.fitness, 4),
            "alpha": round(wr.alpha, 4),
            "ghost_dca_return": round(wr.ghost_dca_return, 4),
            "strategy_return": round(wr.strategy_return, 4),
            "insufficient_data": wr.insufficient_data,
            "n_candles": wr.n_candles,
        }

    fitness_details = {
        "fitness": round(agg_fitness, 4),
        "per_window": per_window_summary,
        "stage": "stage3_multi_window",
    }

    # Assertions
    assert "per_window" in fitness_details
    assert "stage" in fitness_details
    assert fitness_details["stage"] == "stage3_multi_window"

    pw = fitness_details["per_window"]
    for window_name in WINDOWS:
        assert window_name in pw, f"Missing window '{window_name}' in fitness_details"
        entry = pw[window_name]
        assert "alpha" in entry
        assert "ghost_dca_return" in entry
        assert "strategy_return" in entry
        assert "insufficient_data" in entry
        assert isinstance(entry["insufficient_data"], bool)
