#!/usr/bin/env python3
"""
Stage 3: Multi-Window Cross-Validation / 多視窗與交叉驗證

Window definitions, per-window backtest execution, Ghost DCA/Alpha per window,
cache-reuse logic, and aggregate fitness with weight redistribution.

Window weights (must sum to 1.0):
┌─────────────┬────────┬──────────────────────────────────────────────────────┐
│ Window      │ Weight │ Rationale                                            │
├─────────────┼────────┼──────────────────────────────────────────────────────┤
│ all         │  0.20  │ Full-history sanity check; low weight to avoid       │
│             │        │ recency-bias suppression on short histories          │
│ 5y          │  0.30  │ Long-term robustness; highest single weight          │
│ 2y          │  0.30  │ Medium-term cycle coverage (≥ 1 full bull/bear)      │
│ 6m          │  0.15  │ Recent regime test; lower weight (overfitting risk)  │
│ random_is   │  0.05  │ In-sample randomization; diversity regularization    │
└─────────────┴────────┴──────────────────────────────────────────────────────┘
Total: 1.00

Reference: 《核心準則》第三篇章 Stage 3

Author: second_bot
Date: 2026-06-14
"""

import random as _random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Window definitions (milliseconds relative to end_ms)
# ─────────────────────────────────────────────────────────────────────────────

_MS_PER_SECOND = 1000
_SECONDS_PER_HOUR = 3600
_HOURS_PER_DAY = 24
_DAYS_PER_MONTH = 30
_DAYS_PER_YEAR = 365

def _days_ms(days: float) -> int:
    return int(days * _HOURS_PER_DAY * _SECONDS_PER_HOUR * _MS_PER_SECOND)

WINDOWS: Dict[str, Optional[int]] = {
    "all":       None,              # full available history
    "5y":        _days_ms(5 * _DAYS_PER_YEAR),
    "2y":        _days_ms(2 * _DAYS_PER_YEAR),
    "6m":        _days_ms(6 * _DAYS_PER_MONTH),
    "random_is": None,              # computed at runtime via _random_is_slice()
}

# ─────────────────────────────────────────────────────────────────────────────
# Window weights — must sum to 1.0 (enforced by assertion at import time)
# ─────────────────────────────────────────────────────────────────────────────

WINDOW_WEIGHTS: Dict[str, float] = {
    "all":       0.20,
    "5y":        0.30,
    "2y":        0.30,
    "6m":        0.15,
    "random_is": 0.05,
}

assert abs(sum(WINDOW_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"WINDOW_WEIGHTS must sum to 1.0, got {sum(WINDOW_WEIGHTS.values())}"
)

# Minimum data coverage required (< threshold → mark insufficient_data=True)
MIN_DATA_COVERAGE = 0.80

# Random in-sample window length range [6m, 2y] in milliseconds
_RANDOM_IS_MIN_MS = _days_ms(6 * _DAYS_PER_MONTH)
_RANDOM_IS_MAX_MS = _days_ms(2 * _DAYS_PER_YEAR)


# ─────────────────────────────────────────────────────────────────────────────
# WindowResult dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WindowResult:
    """Per-window backtest result."""
    window_name: str
    fitness: float = 0.0
    alpha: float = 0.0                    # strategy_return - ghost_dca_return
    ghost_dca_return: float = 0.0
    strategy_return: float = 0.0
    insufficient_data: bool = False
    n_candles: int = 0
    # Additional detail
    weight: float = 0.0                   # window weight (from WINDOW_WEIGHTS)
    details: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _random_is_slice(
    df_start_ms: int,
    df_end_ms: int,
    seed: Optional[int] = None,
) -> Tuple[int, int]:
    """
    Pick a random In-Sample slice within [df_start_ms, df_end_ms].
    Length is sampled uniformly from [6m, 2y].

    Returns (slice_start_ms, slice_end_ms).
    """
    rng = _random.Random(seed)
    length_ms = int(rng.uniform(_RANDOM_IS_MIN_MS, _RANDOM_IS_MAX_MS))
    # Ensure we have room
    available_ms = df_end_ms - df_start_ms
    if available_ms <= length_ms:
        return df_start_ms, df_end_ms

    max_start = df_end_ms - length_ms
    start_ms = int(rng.uniform(df_start_ms, max_start))
    end_ms = start_ms + length_ms
    return start_ms, end_ms


def _slice_df(df: pd.DataFrame, start_ms: Optional[int], end_ms: Optional[int]) -> pd.DataFrame:
    """
    Slice a DataFrame (with millisecond-timestamp index) to [start_ms, end_ms].
    If start_ms is None, no lower bound; if end_ms is None, no upper bound.
    The index is expected to be DatetimeIndex (UTC).
    """
    import pandas as pd

    mask = pd.Series(True, index=df.index)
    if start_ms is not None:
        start_ts = pd.Timestamp(start_ms, unit='ms', tz='UTC')
        # Handle tz-naive index
        if df.index.tz is None:
            start_ts = start_ts.tz_localize(None)
        mask = mask & (df.index >= start_ts)
    if end_ms is not None:
        end_ts = pd.Timestamp(end_ms, unit='ms', tz='UTC')
        if df.index.tz is None:
            end_ts = end_ts.tz_localize(None)
        mask = mask & (df.index <= end_ts)
    return df[mask]


# ─────────────────────────────────────────────────────────────────────────────
# Per-window backtest runner
# ─────────────────────────────────────────────────────────────────────────────

def run_window_backtest(
    chromosome,
    full_df: pd.DataFrame,
    window_name: str,
    end_ms: int,
    engine=None,
    seed: Optional[int] = None,
) -> WindowResult:
    """
    Execute a single-window backtest.

    Parameters
    ----------
    chromosome  : StrategyChromosomeV2
    full_df     : Full symbol DataFrame (all available history).  Slicing
                  happens here — callers must NOT pre-slice.
    window_name : One of WINDOWS keys.
    end_ms      : Upper bound of the window (default = now).
    engine      : GeneBacktestEngineV2 instance (created if None).
    seed        : RNG seed for "random_is" window.

    Returns
    -------
    WindowResult
    """
    from .backtest_engine_v2 import GeneBacktestEngineV2, GhostDCABaseline

    weight = WINDOW_WEIGHTS.get(window_name, 0.0)

    if full_df is None or full_df.empty:
        return WindowResult(
            window_name=window_name,
            insufficient_data=True,
            weight=weight,
            details={"reason": "empty_df"},
        )

    # Determine time slice
    df_start_ms = int(full_df.index[0].timestamp() * 1000)
    df_end_ms   = int(full_df.index[-1].timestamp() * 1000)
    total_span_ms = df_end_ms - df_start_ms

    window_span_ms: Optional[int] = WINDOWS.get(window_name)  # expected span

    if window_name == "random_is":
        slice_start_ms, slice_end_ms = _random_is_slice(df_start_ms, df_end_ms, seed=seed)
        window_span_ms = slice_end_ms - slice_start_ms
    elif window_span_ms is None:
        # "all" window — use entire df
        slice_start_ms = df_start_ms
        slice_end_ms   = df_end_ms
    else:
        slice_start_ms = end_ms - window_span_ms
        slice_end_ms   = end_ms

    # Slice the dataframe
    df_slice = _slice_df(full_df, slice_start_ms, slice_end_ms)
    n_candles = len(df_slice)

    # Check coverage: require 80% of expected window span
    if window_span_ms and window_span_ms > 0:
        actual_span_ms = (
            (int(df_slice.index[-1].timestamp() * 1000) - int(df_slice.index[0].timestamp() * 1000))
            if n_candles >= 2 else 0
        )
        coverage = actual_span_ms / window_span_ms
        if coverage < MIN_DATA_COVERAGE:
            return WindowResult(
                window_name=window_name,
                insufficient_data=True,
                n_candles=n_candles,
                weight=weight,
                details={
                    "reason": "insufficient_coverage",
                    "coverage": round(coverage, 4),
                    "required": MIN_DATA_COVERAGE,
                },
            )

    if n_candles < 200:
        # warmup=100 + meaningful strategy signal needs ≥200 candles
        return WindowResult(
            window_name=window_name,
            insufficient_data=True,
            n_candles=n_candles,
            weight=weight,
            details={"reason": "too_few_candles", "n_candles": n_candles},
        )

    if engine is None:
        engine = GeneBacktestEngineV2()

    # ── Ghost DCA baseline (independent per window) ───────────────────────────
    dca_engine = GhostDCABaseline(initial_capital=engine.initial_capital)
    dca_equity, _ = dca_engine.run(df_slice)
    ghost_dca_return = dca_engine.calculate_dca_return(dca_equity)

    # ── Strategy backtest ─────────────────────────────────────────────────────
    strategy_equity, strategy_trades, raw_ledger = engine._run_strategy_v2(
        df_slice, chromosome, symbol="window", season=None, environment=None, verbose=False
    )

    if strategy_equity and len(strategy_equity) >= 2:
        strategy_return = (strategy_equity[-1] - strategy_equity[0]) / strategy_equity[0]
    else:
        strategy_return = 0.0

    alpha = strategy_return - ghost_dca_return

    # Simple fitness within this window (alpha + trade quality)
    n_trades = len(strategy_trades)
    if n_trades >= 5:
        win_rate = sum(1 for t in strategy_trades if t.pnl_pct > 0) / n_trades
        fitness = max(0.0, (alpha * 0.6) + (win_rate * 0.4))
    else:
        fitness = 0.0

    return WindowResult(
        window_name=window_name,
        fitness=fitness,
        alpha=alpha,
        ghost_dca_return=ghost_dca_return,
        strategy_return=strategy_return,
        insufficient_data=False,
        n_candles=n_candles,
        weight=weight,
        details={
            "n_trades": n_trades,
            "slice_start_ms": slice_start_ms,
            "slice_end_ms": slice_end_ms,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cache-aware multi-window runner
# ─────────────────────────────────────────────────────────────────────────────

def run_all_windows(
    chromosome,
    symbol_df: pd.DataFrame,
    end_ms: int,
    engine=None,
    seed: Optional[int] = None,
) -> List[WindowResult]:
    """
    Run all WINDOWS for one symbol.

    symbol_df must be the FULL available history for the symbol.
    Data is sliced in-memory — no re-fetch occurs here.

    Parameters
    ----------
    chromosome : StrategyChromosomeV2
    symbol_df  : Full history DataFrame (caller fetches ONCE for the symbol).
    end_ms     : Epoch-ms upper bound (usually now).
    engine     : GeneBacktestEngineV2 (shared; created if None).
    seed       : RNG base seed for "random_is"; each window uses seed+offset.

    Returns
    -------
    List[WindowResult] — one entry per window (in WINDOWS order).
    """
    results: List[WindowResult] = []
    for i, window_name in enumerate(WINDOWS):
        w_seed = (seed + i) if seed is not None else None
        result = run_window_backtest(
            chromosome=chromosome,
            full_df=symbol_df,
            window_name=window_name,
            end_ms=end_ms,
            engine=engine,
            seed=w_seed,
        )
        results.append(result)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate window fitness
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_window_fitness(window_results: List[WindowResult]) -> float:
    """
    Weighted average of per-window fitness scores.

    Rules:
    - Windows marked insufficient_data=True are excluded.
    - Their weight is redistributed proportionally to remaining windows.
    - If ALL windows are insufficient → return 0.0.

    Parameters
    ----------
    window_results : List[WindowResult]

    Returns
    -------
    float — aggregated fitness in [0, 1] range (or 0.0 if all insufficient).
    """
    valid = [r for r in window_results if not r.insufficient_data]
    if not valid:
        return 0.0

    total_valid_weight = sum(r.weight for r in valid)
    if total_valid_weight <= 0:
        return 0.0

    # Redistribute weights proportionally
    return sum((r.weight / total_valid_weight) * r.fitness for r in valid)
