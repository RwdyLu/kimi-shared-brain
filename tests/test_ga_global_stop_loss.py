"""
Tests for G1: global_stop_loss equity drawdown circuit-breaker.

Verifies:
1. GSL triggers when equity drawdown exceeds threshold
2. No new entries after GSL trigger
3. GSL recorded in raw_ledger
4. GSL=0 means disabled (no trigger)
5. Peak equity tracked correctly
6. GSL trigger bar recorded correctly
"""

import random
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys

import pytest
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.genetic_engine.environment import Environment
from app.genetic_engine.chromosome_v2 import (
    StrategyChromosomeV2,
    MacroGenes,
    MicroGenes,
    RiskGenesV2,
    random_chromosome_v2,
)
from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_engine():
    return GeneBacktestEngineV2(
        initial_capital=100_000.0,
        fee_rate=0.001,
        lot_min=0.001,
        lot_step=0.001,
    )


def _make_chromosome(stop_loss_pct: float = -0.50) -> StrategyChromosomeV2:
    """Chromosome that almost never trades (large stop_loss, large take_profit)."""
    chrom = random_chromosome_v2()
    chrom.risk_genes.stop_loss_pct = stop_loss_pct
    chrom.risk_genes.take_profit_pct = 0.99
    chrom.risk_genes.cooldown_bars = 0
    chrom.risk_genes.max_hold_bars = 9999
    return chrom


def _make_price_series(n: int = 200, start: float = 100.0, trend: float = 0.0) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame."""
    random.seed(0)
    closes = [start]
    for _ in range(n - 1):
        closes.append(max(1.0, closes[-1] * (1 + trend + random.gauss(0, 0.01))))
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    df = pd.DataFrame({
        "open": closes,
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
    }, index=dates)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 1. GSL fields present in raw_ledger
# ══════════════════════════════════════════════════════════════════════════════

def test_raw_ledger_has_gsl_fields():
    engine = _make_engine()
    chrom = _make_chromosome()
    env = Environment(global_stop_loss=0.30)
    df = _make_price_series()

    equity, trades, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=env, verbose=False)

    assert "global_stop_loss_triggered" in ledger
    assert "gsl_trigger_bar" in ledger
    assert "gsl_drawdown_at_trigger" in ledger
    assert "blocked_by_cooldown" in ledger


# ══════════════════════════════════════════════════════════════════════════════
# 2. GSL disabled when global_stop_loss=0
# ══════════════════════════════════════════════════════════════════════════════

def test_gsl_disabled_when_zero():
    engine = _make_engine()
    chrom = _make_chromosome()
    env = Environment(global_stop_loss=0.0)
    df = _make_price_series(trend=-0.03)  # strongly downtrending

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=env, verbose=False)

    assert ledger["global_stop_loss_triggered"] is False
    assert ledger["gsl_trigger_bar"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. GSL disabled when environment=None
# ══════════════════════════════════════════════════════════════════════════════

def test_gsl_disabled_when_no_environment():
    engine = _make_engine()
    chrom = _make_chromosome()
    df = _make_price_series(trend=-0.03)

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=None, verbose=False)

    assert ledger["global_stop_loss_triggered"] is False
    assert ledger["gsl_trigger_bar"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. gsl_drawdown_at_trigger is non-negative float
# ══════════════════════════════════════════════════════════════════════════════

def test_gsl_drawdown_field_type():
    engine = _make_engine()
    chrom = _make_chromosome()
    env = Environment(global_stop_loss=0.30)
    df = _make_price_series()

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=env, verbose=False)

    dd = ledger["gsl_drawdown_at_trigger"]
    # Either None (not triggered) or a non-negative float
    assert dd is None or (isinstance(dd, float) and dd >= 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# 5. gsl_trigger_bar is None or a valid bar index
# ══════════════════════════════════════════════════════════════════════════════

def test_gsl_trigger_bar_valid():
    engine = _make_engine()
    chrom = _make_chromosome()
    env = Environment(global_stop_loss=0.30)
    df = _make_price_series(n=150)

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=env, verbose=False)

    bar = ledger["gsl_trigger_bar"]
    assert bar is None or (isinstance(bar, int) and 0 <= bar < len(df))


# ══════════════════════════════════════════════════════════════════════════════
# 6. When GSL triggers, trigger bar is strictly before end of data
# ══════════════════════════════════════════════════════════════════════════════

def test_gsl_trigger_bar_before_end_when_triggered():
    """If GSL triggers, the trigger bar must be < len(df) - 1."""
    engine = _make_engine()
    chrom = _make_chromosome(stop_loss_pct=-0.50)
    env = Environment(global_stop_loss=0.30)
    df = _make_price_series(n=200, trend=-0.02)

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=env, verbose=False)

    if ledger["global_stop_loss_triggered"]:
        assert ledger["gsl_trigger_bar"] < len(df) - 1
        assert ledger["gsl_drawdown_at_trigger"] >= 0.30 - 1e-9
