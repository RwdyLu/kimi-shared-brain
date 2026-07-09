from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.xsec_rescue import (  # noqa: E402
    build_rescue_plan,
    generate_rescue_neighbors,
    select_rescue_seeds,
    write_rescue_artifacts,
)


BASE_CONFIG = {
    "lookback_h": 504,
    "skip_h": 0,
    "rebalance_h": 168,
    "k": 3,
    "score_mode": "risk_adj_mom",
    "market_filter_h": 1008,
    "vol_target_ann": 0.06,
    "n_tranches": 1,
}


def row(
    *,
    config: dict | None = None,
    diagnostic_q25: float = 0.60,
    diagnostic_sign: float = 0.833,
    validation_sharpe: float = 1.40,
    validation_min: float = 1.20,
    failed_checks: tuple[str, ...] = ("positive_3_of_4_years",),
) -> dict:
    checks = {
        "positive_3_of_4_years": "positive_3_of_4_years" not in failed_checks,
        "max_dd20_le_25pct": "max_dd20_le_25pct" not in failed_checks,
        "validation_sharpe20_ge_adjusted_min": "validation_sharpe20_ge_adjusted_min" not in failed_checks,
    }
    return {
        "config": dict(config or BASE_CONFIG),
        "advance_passed": False,
        "advance_checks": checks,
        "selection": {
            "cost20": {
                "sharpe": 1.8,
                "yearly": {
                    "2021": {"net_return": 0.20},
                    "2022": {"net_return": -0.03},
                    "2023": {"net_return": 0.11},
                    "2024H1": {"net_return": 0.04},
                },
            }
        },
        "validation": {"cost20": {"sharpe": validation_sharpe}},
        "diagnostic_walk_forward": {
            "enabled": True,
            "diagnostic_only": True,
            "triggered": True,
            "q25_sharpe": diagnostic_q25,
            "sign_consistency": diagnostic_sign,
            "validation_sharpe20": validation_sharpe,
            "validation_sharpe20_min": validation_min,
        },
    }


def test_select_rescue_seeds_requires_strong_diagnostic_and_full_config() -> None:
    rows = [
        row(diagnostic_q25=0.72, validation_sharpe=1.6),
        row(diagnostic_q25=0.20, validation_sharpe=2.0),
        row(config={"lookback_h": 504}, diagnostic_q25=0.90, validation_sharpe=2.0),
    ]

    seeds = select_rescue_seeds(rows, top_k=5)

    assert len(seeds) == 1
    assert seeds[0]["diagnostic_q25_sharpe"] == 0.72
    assert seeds[0]["worst_year"] == {"bucket": "2022", "net_return": -0.03}


def test_generate_rescue_neighbors_prioritizes_failure_repair_and_deduplicates() -> None:
    seed = select_rescue_seeds([row(failed_checks=("positive_3_of_4_years", "max_dd20_le_25pct"))])[0]

    neighbors = generate_rescue_neighbors(seed, budget=8)

    assert len(neighbors) == 8
    assert neighbors[0]["changed_gene"] == "market_filter_h"
    assert all(neighbor["config"]["score_mode"] == "risk_adj_mom" for neighbor in neighbors)
    assert len({neighbor["config_fingerprint"] for neighbor in neighbors}) == len(neighbors)


def test_build_rescue_plan_counts_additional_trials_and_keeps_safety_false(tmp_path) -> None:
    alternate = dict(BASE_CONFIG)
    alternate["lookback_h"] = 672
    plan = build_rescue_plan(
        [row(diagnostic_q25=0.70), row(config=alternate, diagnostic_q25=0.65)],
        meta={"effective_trials": 20000},
        source_artifact="artifact.json",
        top_k=2,
        budget_per_seed=5,
    )

    assert plan["seed_count"] == 2
    assert plan["rescue_config_count"] == 10
    assert plan["effective_trials_after_rescue"] == 20010
    assert plan["holdout_authorized"] is False
    assert plan["paper_trading_authorized"] is False
    assert plan["live_trading_authorized"] is False

    metadata = write_rescue_artifacts(plan, tmp_path / "plan.json", tmp_path / "configs.json")
    assert metadata["rescue_config_count"] == 10
    assert json.loads((tmp_path / "configs.json").read_text()) == plan["configs"]
