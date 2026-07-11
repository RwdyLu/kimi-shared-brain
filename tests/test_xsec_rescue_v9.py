from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.xsec_rescue import (  # noqa: E402
    build_rescue_plan,
    generate_rescue_neighbors,
    rescue_gene_order,
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
    diagnostic_triggered: bool = True,
    selection_sharpe: float = 1.8,
    selection_sharpe40: float = 1.1,
    bootstrap_p5: float = 0.55,
    benchmark_excess: float = 0.20,
    active_rebalances: int = 80,
    time_in_market: float = 0.20,
    top_symbol_share: float = 0.45,
    validation_sharpe: float = 1.40,
    validation_min: float = 1.20,
    failed_checks: tuple[str, ...] = ("positive_3_of_4_years",),
) -> dict:
    check_names = {
        "sharpe20_ge_1_2",
        "max_dd20_le_25pct",
        "daily_turnover40_le_50pct",
        "active_rebalances40_ge_min",
        "time_in_market40_ge_min",
        "positive_3_of_4_years",
        "bootstrap_p5_ge_adjusted_min",
        "sharpe40_ge_1",
        "top_symbol_share_le_60pct",
        "benchmark_sharpe_excess_ge_0_10",
        "drawdown_ratio_le_0_80",
        "validation_sharpe20_ge_adjusted_min",
        "validation_max_dd20_le_30pct",
        "validation_return20_gt_0",
        "validation_sharpe40_gt_0",
        "validation_daily_turnover40_le_50pct",
        "selection_passed_before_validation",
    }
    checks = {name: name not in failed_checks for name in check_names}
    return {
        "config": dict(config or BASE_CONFIG),
        "advance_passed": False,
        "advance_checks": checks,
        "selection": {
            "cost20": {
                "sharpe": selection_sharpe,
                "bootstrap_30d_sharpe_p5": bootstrap_p5,
                "top_positive_symbol_share": top_symbol_share,
                "equal_weight_benchmark": {"sharpe_excess": benchmark_excess},
                "yearly": {
                    "2021": {"net_return": 0.20},
                    "2022": {"net_return": -0.03},
                    "2023": {"net_return": 0.11},
                    "2024H1": {"net_return": 0.04},
                },
            },
            "cost40": {
                "sharpe": selection_sharpe40,
                "active_rebalance_event_count": active_rebalances,
                "time_in_market_frac": time_in_market,
            },
        },
        "validation": {"cost20": {"sharpe": validation_sharpe}},
        "diagnostic_walk_forward": {
            "enabled": True,
            "diagnostic_only": True,
            "triggered": diagnostic_triggered,
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
    assert seeds[0]["rescue_seed_type"] == "diagnostic_walkforward"
    assert seeds[0]["worst_year"] == {"bucket": "2022", "net_return": -0.03}


def test_select_rescue_seeds_falls_back_to_active_near_miss_without_diagnostic() -> None:
    near_miss = row(
        diagnostic_triggered=False,
        diagnostic_q25=0.0,
        failed_checks=(
            "selection_passed_before_validation",
            "positive_3_of_4_years",
            "bootstrap_p5_ge_adjusted_min",
        ),
        selection_sharpe=1.70,
        bootstrap_p5=0.49,
        active_rebalances=122,
        time_in_market=0.14,
    )

    seeds = select_rescue_seeds([near_miss], top_k=3)

    assert len(seeds) == 1
    assert seeds[0]["rescue_seed_type"] == "near_miss_gate"
    assert seeds[0]["selection_sharpe20"] == 1.70
    assert seeds[0]["active_rebalances40"] == 122
    assert "selection_passed_before_validation" in seeds[0]["failed_checks"]
    assert "selection_passed_before_validation" not in seeds[0]["rescue_relevant_failures"]


def test_select_rescue_seeds_rejects_inactive_near_miss_fallback() -> None:
    inactive = row(
        diagnostic_triggered=False,
        diagnostic_q25=0.0,
        failed_checks=("positive_3_of_4_years",),
        selection_sharpe=1.90,
        bootstrap_p5=0.52,
        active_rebalances=2,
        time_in_market=0.01,
    )

    seeds = select_rescue_seeds([inactive], top_k=3)

    assert seeds == []


def test_rescue_gene_order_targets_robustness_and_benchmark_failures() -> None:
    robustness_order = rescue_gene_order(["positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"])
    benchmark_order = rescue_gene_order(["benchmark_sharpe_excess_ge_0_10", "sharpe40_ge_1"])

    assert robustness_order[:4] == ["market_filter_h", "market_confirm_h", "rebalance_h", "lookback_h"]
    assert benchmark_order[:3] == ["score_mode", "k", "rebalance_h"]


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


def test_default_rescue_plan_stays_within_auto_rescue_cap() -> None:
    rows = []
    lookbacks = (72, 168, 240, 336, 504, 672, 720, 1008)
    for lookback in lookbacks:
        config = dict(BASE_CONFIG)
        config["lookback_h"] = lookback
        rows.append(
            row(
                config=config,
                diagnostic_triggered=False,
                diagnostic_q25=0.0,
                failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
                selection_sharpe=1.55,
                bootstrap_p5=0.45,
                active_rebalances=120,
                time_in_market=0.15,
            )
        )

    plan = build_rescue_plan(rows)

    assert plan["seed_count"] == 8
    assert plan["budget_per_seed"] == 18
    assert plan["rescue_config_count"] <= 150


def test_rescue_plan_script_runs_from_repo_root(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        json.dumps(
            {
                "summary": {"accepted_train_only": False},
                "selection_validation": {"effective_trials": 100},
                "rows": [row(diagnostic_q25=0.70)],
            }
        )
    )
    plan_path = tmp_path / "plan.json"
    config_path = tmp_path / "configs.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/v9_xsec_rescue_plan.py"),
            str(artifact),
            "--out-plan",
            str(plan_path),
            "--out-configs",
            str(config_path),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    metadata = json.loads(completed.stdout)
    assert metadata["rescue_seed_count"] == 1
    assert plan_path.exists()
    assert config_path.exists()
