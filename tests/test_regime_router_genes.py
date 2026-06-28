import os
import random
import sys
from dataclasses import asdict


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
