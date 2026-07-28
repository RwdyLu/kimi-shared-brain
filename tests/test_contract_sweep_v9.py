from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.schema import ContractCandidate  # noqa: E402
from v9.contract.sweep import build_regime_hold_variants, hold_sweep_values  # noqa: E402


def best_balanced_candidate() -> ContractCandidate:
    return ContractCandidate(
        symbol="LINKUSDT",
        allowed_regimes=("up_normal",),
        atr_n=28,
        breakout_n=32,
        cooldown_bars=4,
        leverage_cap=1.0,
        max_hold_bars=36,
        risk_per_trade=0.005,
        stop_atr_k=2.5,
        tp_r_multiple=2.0,
    )


def test_hold_sweep_values_are_unique_and_rounded() -> None:
    assert hold_sweep_values(36, [1.0, 0.75, 0.5]) == [36, 27, 18]
    assert hold_sweep_values(1, [1.0, 0.75, 0.5]) == [1]


def test_regime_hold_sweep_builds_expected_six_variants() -> None:
    base = best_balanced_candidate()
    variants = build_regime_hold_variants(base, strict_drawdown_cap=0.25)
    candidates = [row["candidate"] for row in variants]

    assert len(variants) == 6
    assert [c.max_hold_bars for c in candidates[:3]] == [36, 27, 18]
    assert [c.max_regime_drawdown_1y for c in candidates[:3]] == [None, None, None]
    assert [c.max_hold_bars for c in candidates[3:]] == [36, 27, 18]
    assert [c.max_regime_drawdown_1y for c in candidates[3:]] == [0.25, 0.25, 0.25]
    assert candidates[0].candidate_id() == "bf7919c368e63524"
    assert len({c.candidate_id() for c in candidates}) == 6
