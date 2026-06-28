import os
import random
import sys
from dataclasses import asdict

import numpy as np


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import lunar_genome_crypto_lab_v6 as lab
import lunar_genome_crypto_lab_v7_robust as v7


NEW_ROUTER_FIELDS = {
    "RegimeRouterBlend",
    "UpTrendFireScale",
    "DownTrendFireScale",
    "ChopFireScale",
    "HighVolFireScale",
    "LowVolFireScale",
    "RegimeMinCoverage",
}


def _base_genome(**overrides):
    data = asdict(lab.random_genome(random.Random(7)))
    data.update(
        {
            "TrendGate": 0.001,
            "VolGateLow": 0.0,
            "VolGateHigh": 0.08,
            "ChopGate": 30.0,
            "RegimeFireScale": 1.0,
            "RegimeRouterBlend": 1.0,
            "UpTrendFireScale": 1.0,
            "DownTrendFireScale": 1.0,
            "ChopFireScale": 1.0,
            "HighVolFireScale": 1.0,
            "LowVolFireScale": 1.0,
            "RegimeMinCoverage": 0.02,
        }
    )
    data.update(overrides)
    return lab.LunarGenome(**data)


def test_old_genome_dicts_get_router_defaults():
    original = asdict(_base_genome())
    old_shape = {k: v for k, v in original.items() if k not in NEW_ROUTER_FIELDS}

    genome = v7.dict_to_genome(old_shape)

    assert genome is not None
    assert genome.RegimeRouterBlend == 0.0
    assert genome.UpTrendFireScale == 1.0
    assert genome.ChopFireScale == 1.0


def test_regime_router_scales_trend_up_when_enabled():
    genome = _base_genome(RegimeRouterBlend=1.0, UpTrendFireScale=1.4)

    route = lab.regime_route(genome, pos_term=0.02, vel_value=0.01, acc_value=0.0001)

    assert route["label"] == "trend_up"
    assert round(route["policy_multiplier"], 2) == 1.4
    assert round(route["combined_multiplier"], 2) == 1.4


def test_router_blend_zero_preserves_old_policy_multiplier():
    genome = _base_genome(RegimeRouterBlend=0.0, UpTrendFireScale=0.1)

    route = lab.regime_route(genome, pos_term=0.02, vel_value=0.01, acc_value=0.0001)

    assert route["label"] == "trend_up"
    assert route["policy_multiplier"] == 1.0


def test_chop_regime_can_be_suppressed_by_gene():
    genome = _base_genome(RegimeRouterBlend=1.0, ChopGate=2.0, ChopFireScale=0.0)

    route = lab.regime_route(genome, pos_term=0.0002, vel_value=0.001, acc_value=0.01)

    assert route["label"] == "chop"
    assert route["combined_multiplier"] == 0.0


def test_full_ghost_is_not_weakened_by_router():
    genome = _base_genome(
        EMAAnchor=20,
        TMacro=10,
        TMicro=10,
        TDeadline=10,
        MaxDCAMonths=12,
        BetaThreshold=0.0,
        TrendGate=0.000001,
        VolGateLow=0.0,
        VolGateHigh=1.0,
        ChopGate=1_000_000.0,
        RegimeFireScale=1.0,
        RegimeRouterBlend=1.0,
        UpTrendFireScale=0.0,
        MinTradeThreshold=0.12,
        MicroReserveRate=0.01,
    )
    close = np.linspace(100.0, 200.0, 1500)
    env = lab.Environment(DeadReserveRatio=0.10, GlobalStopLoss=0.99)
    season = lab.Season(winter=1.0, spring=1.0, summer=1.0, autumn=1.0, tick_offset=0)

    result = lab.simulate_symbol(
        genome,
        env,
        season,
        close,
        initial_cash=10_000.0,
        cost_rate=0.001,
        lot_step=0.0001,
        lot_min=0.0001,
        min_notional=10.0,
        bar_minutes=240,
    )

    assert result["routed_ghost_return"] < result["full_ghost_return"]
    assert result["full_ghost_return"] > 0
    assert result["alpha_vs_full_ghost"] < result["alpha_vs_routed_ghost"]
    assert result["alpha"] == result["alpha_vs_full_ghost"]
