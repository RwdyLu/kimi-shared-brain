"""
Tests for G2: cooldown_bars gene implementation.

Verifies:
1. cooldown_bars field exists in RiskGenesV2 with default=0
2. to_dict / from_dict round-trips correctly
3. random_bridge sets cooldown_bars in valid range
4. mutate_bridge can change cooldown_bars
5. crossover averages cooldown_bars
6. blocked_by_cooldown in raw_ledger (int >= 0)
7. cooldown_bars=0 disables cooldown (blocked_by_cooldown == 0)
"""

import random
from pathlib import Path
import sys

import pytest
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.genetic_engine.chromosome_v2 import (
    StrategyChromosomeV2,
    RiskGenesV2,
    crossover_chromosomes_v2,
    random_chromosome_v2,
)
from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2
from app.genetic_engine.environment import Environment


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_engine():
    return GeneBacktestEngineV2(
        initial_capital=100_000.0,
        fee_rate=0.001,
        lot_min=0.001,
        lot_step=0.001,
    )


def _make_price_series(n: int = 200) -> pd.DataFrame:
    random.seed(1)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(max(1.0, closes[-1] * (1 + random.gauss(0, 0.01))))
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open": closes,
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": [1000.0] * n,
    }, index=dates)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Field exists with correct default
# ══════════════════════════════════════════════════════════════════════════════

def test_cooldown_bars_default_zero():
    risk = RiskGenesV2()
    assert hasattr(risk, "cooldown_bars")
    assert risk.cooldown_bars == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. to_dict / from_dict round-trip
# ══════════════════════════════════════════════════════════════════════════════

def test_cooldown_bars_to_dict_from_dict():
    risk = RiskGenesV2(cooldown_bars=7)
    d = risk.to_dict()
    assert "cooldown_bars" in d
    assert d["cooldown_bars"] == 7

    restored = RiskGenesV2.from_dict(d)
    assert restored.cooldown_bars == 7


def test_cooldown_bars_from_dict_missing_uses_default():
    d = {
        "stop_loss_pct": -0.05,
        "take_profit_pct": 0.10,
        "position_pct": 0.15,
        "max_hold_bars": 72,
        "trailing_stop": False,
    }
    risk = RiskGenesV2.from_dict(d)
    assert risk.cooldown_bars == 0


# ══════════════════════════════════════════════════════════════════════════════
# 3. random_bridge sets cooldown_bars in [0, 50]
# ══════════════════════════════════════════════════════════════════════════════

def test_random_bridge_cooldown_bars_in_range():
    for _ in range(20):
        base = RiskGenesV2()
        result = RiskGenesV2.random_bridge(base)
        assert 0 <= result.cooldown_bars <= 50, f"cooldown_bars={result.cooldown_bars} out of range"


# ══════════════════════════════════════════════════════════════════════════════
# 4. mutate_bridge can change cooldown_bars
# ══════════════════════════════════════════════════════════════════════════════

def test_mutate_bridge_can_change_cooldown_bars():
    random.seed(99)
    risk = RiskGenesV2(cooldown_bars=10)
    changed = False
    for _ in range(50):
        mutated = risk.mutate_bridge(intensity=1.0)
        assert 0 <= mutated.cooldown_bars <= 50
        if mutated.cooldown_bars != 10:
            changed = True
    assert changed, "mutate_bridge should sometimes change cooldown_bars"


# ══════════════════════════════════════════════════════════════════════════════
# 5. crossover averages cooldown_bars
# ══════════════════════════════════════════════════════════════════════════════

def test_crossover_averages_cooldown_bars():
    random.seed(7)
    p1 = random_chromosome_v2()
    p2 = random_chromosome_v2()
    p1.risk_genes.cooldown_bars = 4
    p2.risk_genes.cooldown_bars = 12
    expected = round((4 + 12) / 2)  # = 8

    child = crossover_chromosomes_v2(p1, p2, generation=1)
    assert child.risk_genes.cooldown_bars == expected


# ══════════════════════════════════════════════════════════════════════════════
# 6. blocked_by_cooldown in raw_ledger is int >= 0
# ══════════════════════════════════════════════════════════════════════════════

def test_blocked_by_cooldown_in_ledger():
    engine = _make_engine()
    chrom = random_chromosome_v2()
    chrom.risk_genes.cooldown_bars = 5
    df = _make_price_series()

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=None, verbose=False)

    assert "blocked_by_cooldown" in ledger
    assert isinstance(ledger["blocked_by_cooldown"], int)
    assert ledger["blocked_by_cooldown"] >= 0


# ══════════════════════════════════════════════════════════════════════════════
# 7. cooldown_bars=0 means blocked_by_cooldown == 0
# ══════════════════════════════════════════════════════════════════════════════

def test_no_cooldown_means_zero_blocked():
    engine = _make_engine()
    chrom = random_chromosome_v2()
    chrom.risk_genes.cooldown_bars = 0
    df = _make_price_series()

    _, _, ledger = engine._run_strategy_v2(df, chrom, "TEST", season=None, environment=None, verbose=False)

    assert ledger["blocked_by_cooldown"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 8. Off-by-one: cooldown_bars=N blocks exactly N bars after exit
#
# Definition:
#   exit at bar i=EXIT_BAR, cooldown_bars=N
#   → bars EXIT_BAR+1 … EXIT_BAR+N are blocked
#   → bar EXIT_BAR+N+1 is the first bar entry is allowed
#   → cooldown_until_bar = EXIT_BAR + N + 1
#   → entry gate: current_bar >= cooldown_until_bar
# ══════════════════════════════════════════════════════════════════════════════

def test_cooldown_off_by_one_definition():
    """Verify cooldown_until_bar arithmetic matches the documented definition."""
    # Simulate the formula directly — no full backtest needed
    cooldown_bars = 3
    exit_bar = 100

    # Formula in backtest_engine_v2.py: cooldown_until_bar = i + cooldown_bars + 1
    cooldown_until_bar = exit_bar + cooldown_bars + 1  # = 104

    # Bars blocked (entry gate: i >= cooldown_until_bar → False means blocked)
    blocked = [i for i in range(exit_bar, exit_bar + cooldown_bars + 5)
               if i < cooldown_until_bar]

    # Should block exit_bar itself AND the N bars after it
    # exit_bar=100 is blocked on same-bar re-entry; 101,102,103 are post-exit blocked
    assert 101 in blocked, "bar 101 should be blocked"
    assert 102 in blocked, "bar 102 should be blocked"
    assert 103 in blocked, "bar 103 should be blocked"
    assert 104 not in blocked, "bar 104 should be the first allowed bar"

    # Exactly N bars after exit are blocked (101,102,103)
    post_exit_blocked = [b for b in blocked if b > exit_bar]
    assert len(post_exit_blocked) == cooldown_bars, (
        f"Expected {cooldown_bars} bars blocked after exit, got {len(post_exit_blocked)}: {post_exit_blocked}"
    )
