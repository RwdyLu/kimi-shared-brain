from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.xsec_rescue import (  # noqa: E402
    build_rescue_plan,
    config_fingerprint,
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
    advance_passed: bool = False,
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
    yearly: dict[str, float] | None = None,
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
        "walk_forward_robust",
    }
    checks = {name: name not in failed_checks for name in check_names}
    yearly = yearly or {"2021": 0.20, "2022": -0.03, "2023": 0.11, "2024H1": 0.04}
    return {
        "config": dict(config or BASE_CONFIG),
        "advance_passed": bool(advance_passed),
        "advance_checks": checks,
        "selection": {
            "cost20": {
                "sharpe": selection_sharpe,
                "bootstrap_30d_sharpe_p5": bootstrap_p5,
                "top_positive_symbol_share": top_symbol_share,
                "equal_weight_benchmark": {"sharpe_excess": benchmark_excess},
                "yearly": {bucket: {"net_return": value} for bucket, value in yearly.items()},
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


def test_select_rescue_seeds_prefers_accepted_train_only_rows_for_multiplicity_hardening() -> None:
    accepted_config = dict(BASE_CONFIG)
    accepted_config["lookback_h"] = 672
    accepted = row(
        config=accepted_config,
        advance_passed=True,
        diagnostic_q25=0.10,
        diagnostic_triggered=False,
        selection_sharpe=1.45,
        bootstrap_p5=0.42,
        failed_checks=(),
    )
    diagnostic = row(diagnostic_q25=0.90, validation_sharpe=1.8)

    seeds = select_rescue_seeds([diagnostic, accepted], top_k=2)

    assert [seed["rescue_seed_type"] for seed in seeds] == ["accepted_train_only", "diagnostic_walkforward"]
    assert seeds[0]["rescue_relevant_failure_count"] == 0
    assert seeds[0]["selection_bootstrap_p5"] == 0.42


def test_generate_rescue_neighbors_hardens_accepted_train_only_seed_for_multiplicity() -> None:
    accepted = row(
        advance_passed=True,
        diagnostic_triggered=False,
        failed_checks=(),
        bootstrap_p5=0.42,
        validation_sharpe=1.5,
    )
    seed = select_rescue_seeds([accepted], top_k=1)[0]

    neighbors = generate_rescue_neighbors(seed, budget=6)

    assert seed["rescue_seed_type"] == "accepted_train_only"
    assert len(neighbors) == 6
    assert neighbors[0]["mutation_bias"] == "multiplicity_hardening"
    assert neighbors[0]["changed_gene"] == "score_mode"
    assert neighbors[1]["changed_gene"] == "score_mode"


def test_generate_rescue_neighbors_spends_pair_budget_on_accepted_train_only_hardening() -> None:
    accepted = row(
        advance_passed=True,
        diagnostic_triggered=False,
        failed_checks=(),
        bootstrap_p5=0.42,
        validation_sharpe=1.5,
    )
    seed = select_rescue_seeds([accepted], top_k=1)[0]

    neighbors = generate_rescue_neighbors(seed, budget=18)

    single_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 1]
    two_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 2]
    assert len(neighbors) == 18
    assert len(two_gene) > len(single_gene)
    assert two_gene[0]["mutation_bias"] == "multiplicity_hardening"
    assert two_gene[0]["changed_gene"] == "score_mode+k"
    assert any(neighbor["changed_gene"] == "rebalance_h+lookback_h" for neighbor in two_gene)


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


def test_select_rescue_seeds_diversifies_near_miss_families_before_filling() -> None:
    same_family_a = dict(BASE_CONFIG)
    same_family_a["lookback_h"] = 168
    same_family_a["rebalance_h"] = 24
    same_family_a["score_mode"] = "breakout"
    same_family_a["market_filter_h"] = 336
    same_family_a["vol_target_ann"] = 0.08

    same_family_b = dict(same_family_a)
    same_family_b["vol_target_ann"] = 0.10

    other_family = dict(same_family_a)
    other_family["lookback_h"] = 336

    rows = [
        row(
            config=same_family_a,
            diagnostic_triggered=False,
            failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
            selection_sharpe=1.80,
            bootstrap_p5=0.60,
        ),
        row(
            config=same_family_b,
            diagnostic_triggered=False,
            failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
            selection_sharpe=1.79,
            bootstrap_p5=0.59,
        ),
        row(
            config=other_family,
            diagnostic_triggered=False,
            failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
            selection_sharpe=1.40,
            bootstrap_p5=0.30,
        ),
    ]

    seeds = select_rescue_seeds(rows, top_k=2)

    assert [seed["config"]["vol_target_ann"] for seed in seeds] == [0.08, 0.08]
    assert [seed["rescue_seed_family"]["lookback_h"] for seed in seeds] == [168, 336]


def test_select_rescue_seeds_prefers_more_rescueable_year_profile() -> None:
    fragile = row(
        diagnostic_triggered=False,
        failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
        selection_sharpe=2.20,
        bootstrap_p5=0.70,
        yearly={"2021": 0.30, "2022": -0.20, "2023": 0.10, "2024H1": 0.05},
    )
    rescueable = row(
        diagnostic_triggered=False,
        failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
        selection_sharpe=1.50,
        bootstrap_p5=0.40,
        yearly={"2021": 0.08, "2022": -0.01, "2023": 0.06, "2024H1": 0.04},
    )

    seeds = select_rescue_seeds([fragile, rescueable], top_k=1)

    assert seeds[0]["selection_sharpe20"] == 1.50
    assert seeds[0]["worst_year"] == {"bucket": "2022", "net_return": -0.01}
    assert seeds[0]["worst_year_return"] == -0.01
    assert seeds[0]["positive_year_count"] == 3


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


def test_generate_rescue_neighbors_uses_limited_two_gene_repairs() -> None:
    seed = select_rescue_seeds([row(failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"))])[0]

    neighbors = generate_rescue_neighbors(seed, budget=12)

    single_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 1]
    two_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 2]
    assert len(neighbors) == 12
    assert single_gene
    assert two_gene
    assert all(len(neighbor["changes"]) == len(neighbor["changed_genes"]) for neighbor in neighbors)
    assert all(neighbor["changed_gene"] == "+".join(neighbor["changed_genes"]) for neighbor in neighbors)


def test_generate_rescue_neighbors_spends_pair_budget_on_hostile_year() -> None:
    config = {
        **BASE_CONFIG,
        "lookback_h": 168,
        "rebalance_h": 72,
        "score_mode": "breakout",
        "market_filter_h": 720,
        "market_confirm_h": 168,
        "market_drawdown_limit": 0.25,
        "drawdown_stop": 0.15,
        "cooldown_h": 168,
        "vol_target_ann": 0.08,
    }
    seed = select_rescue_seeds(
        [
            row(
                config=config,
                diagnostic_triggered=False,
                failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
                selection_sharpe=1.70,
                bootstrap_p5=0.45,
            )
        ]
    )[0]

    neighbors = generate_rescue_neighbors(seed, budget=18)

    single_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 1]
    two_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 2]
    assert len(neighbors) == 18
    assert len(two_gene) > len(single_gene)
    assert single_gene[0]["mutation_bias"] == "hostile_year_defensive"
    assert any(neighbor["changed_gene"] == "market_filter_h+vol_target_ann" for neighbor in two_gene)
    first_pair = two_gene[0]
    assert first_pair["changed_gene"] == "market_filter_h+vol_target_ann"
    assert first_pair["changes"][0]["to"] == 1008
    assert first_pair["changes"][1]["to"] == 0.06


def test_generate_rescue_neighbors_prefers_defensive_regime_repairs_for_negative_worst_year() -> None:
    config = {
        **BASE_CONFIG,
        "lookback_h": 168,
        "rebalance_h": 72,
        "score_mode": "breakout",
        "market_filter_h": 720,
        "market_confirm_h": 168,
        "market_drawdown_limit": 0.25,
        "drawdown_stop": 0.15,
        "cooldown_h": 168,
        "vol_target_ann": 0.08,
    }
    seed = select_rescue_seeds(
        [
            row(
                config=config,
                diagnostic_triggered=False,
                failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
                selection_sharpe=1.70,
                bootstrap_p5=0.45,
            )
        ]
    )[0]

    neighbors = generate_rescue_neighbors(seed, budget=8)

    assert neighbors[0]["mutation_bias"] == "hostile_year_defensive"
    assert neighbors[0]["changed_gene"] == "market_filter_h"
    assert neighbors[0]["to"] == 1008
    assert neighbors[1]["to"] == 1344


def test_generate_rescue_neighbors_uses_tail_defensive_bias_for_bootstrap_only_failure() -> None:
    config = {
        **BASE_CONFIG,
        "market_filter_h": 504,
        "market_confirm_h": 168,
        "rebalance_h": 48,
        "k": 2,
        "vol_target_ann": 0.08,
        "n_tranches": 1,
    }
    seed = select_rescue_seeds(
        [
            row(
                config=config,
                diagnostic_triggered=False,
                failed_checks=("bootstrap_p5_ge_adjusted_min",),
                selection_sharpe=1.70,
                bootstrap_p5=0.20,
                yearly={"2021": 0.20, "2022": 0.01, "2023": 0.11, "2024H1": 0.04},
            )
        ]
    )[0]

    neighbors = generate_rescue_neighbors(seed, budget=18)

    two_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 2]
    assert neighbors[0]["mutation_bias"] == "tail_defensive"
    assert neighbors[0]["changed_gene"] == "market_filter_h"
    assert neighbors[0]["to"] == 720
    assert any(neighbor["changed_gene"] == "vol_target_ann+n_tranches" for neighbor in two_gene)
    vol_tranche = next(neighbor for neighbor in two_gene if neighbor["changed_gene"] == "vol_target_ann+n_tranches")
    assert vol_tranche["changes"][0]["to"] == 0.06
    assert vol_tranche["changes"][1]["to"] == 3


def test_generate_rescue_neighbors_uses_walk_forward_plateau_bias_for_wf_failure() -> None:
    config = {
        **BASE_CONFIG,
        "lookback_h": 336,
        "rebalance_h": 48,
        "market_filter_h": 720,
        "market_confirm_h": 0,
        "vol_target_ann": 0.04,
        "n_tranches": 1,
        "drawdown_stop": 0.08,
        "cooldown_h": 72,
        "portfolio_mode": "hedged_long",
        "hedge_ratio": 0.40,
    }
    sample = row(
        config=config,
        diagnostic_triggered=False,
        failed_checks=("walk_forward_robust",),
        selection_sharpe=2.40,
        bootstrap_p5=1.20,
        yearly={"2021": 0.20, "2022": 0.05, "2023": 0.11, "2024H1": 0.01},
    )
    sample["walk_forward"] = {
        "q25_sharpe": -0.01,
        "worst_fold_return": -0.056,
        "worst_fold_max_drawdown": 0.095,
        "hedged_dd_improvement_fraction": 0.667,
        "checks": {
            "wf_q25_sharpe_ge_min": False,
            "wf_consistency_ge_min_or_bounded_loss": False,
            "wf_net_median_sharpe_retains_80pct_long_only": False,
            "wf_hedged_dd_improves_half_folds": True,
        },
    }
    seed = select_rescue_seeds([sample])[0]

    neighbors = generate_rescue_neighbors(seed, budget=18)

    two_gene = [neighbor for neighbor in neighbors if len(neighbor["changed_genes"]) == 2]
    hedge_neighbors = [neighbor for neighbor in neighbors if "hedge_ratio" in neighbor["changed_genes"]]
    assert neighbors[0]["mutation_bias"] == "walk_forward_plateau"
    assert neighbors[0]["changed_gene"] == "rebalance_h"
    assert neighbors[0]["to"] == 72
    assert any(neighbor["changed_gene"] == "rebalance_h+lookback_h" for neighbor in two_gene)
    assert hedge_neighbors
    assert hedge_neighbors[0]["config"]["hedge_ratio"] == 0.3


def test_generate_rescue_neighbors_prefers_less_restrictive_repairs_when_activity_fails() -> None:
    config = {
        **BASE_CONFIG,
        "lookback_h": 168,
        "rebalance_h": 72,
        "score_mode": "breakout",
        "market_filter_h": 720,
        "market_confirm_h": 168,
        "market_drawdown_limit": 0.25,
        "drawdown_stop": 0.15,
        "cooldown_h": 168,
        "vol_target_ann": 0.08,
    }
    seed = select_rescue_seeds(
        [
            row(
                config=config,
                diagnostic_triggered=False,
                failed_checks=("active_rebalances40_ge_min", "time_in_market40_ge_min"),
                selection_sharpe=1.70,
                bootstrap_p5=0.60,
                active_rebalances=12,
                time_in_market=0.05,
            )
        ]
    )[0]

    neighbors = generate_rescue_neighbors(seed, budget=8)

    assert neighbors[0]["mutation_bias"] == "activity_unblock"
    assert neighbors[0]["changed_gene"] == "cooldown_h"
    assert neighbors[0]["to"] == 72


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
    assert plan["seed_family_count"] == 2
    assert plan["rescue_config_count"] == 10
    assert plan["effective_trials_after_rescue"] == 20010
    assert plan["holdout_authorized"] is False
    assert plan["paper_trading_authorized"] is False
    assert plan["live_trading_authorized"] is False

    metadata = write_rescue_artifacts(plan, tmp_path / "plan.json", tmp_path / "configs.json")
    assert metadata["rescue_config_count"] == 10
    assert metadata["accepted_train_only_seed_count"] == 0
    assert metadata["diagnostic_seed_count"] == 2
    assert metadata["near_miss_seed_count"] == 0
    assert metadata["prior_effective_trials"] == 20000
    assert metadata["effective_trials_after_rescue"] == 20010
    assert json.loads((tmp_path / "configs.json").read_text()) == plan["configs"]


def test_build_rescue_plan_counts_accepted_train_only_seeds() -> None:
    accepted_config = dict(BASE_CONFIG)
    accepted_config["lookback_h"] = 672
    accepted = row(config=accepted_config, advance_passed=True, diagnostic_triggered=False, failed_checks=())
    near_miss = row(
        diagnostic_triggered=False,
        failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
        selection_sharpe=1.55,
        bootstrap_p5=0.45,
    )

    plan = build_rescue_plan([near_miss, accepted], top_k=2, budget_per_seed=3)

    assert plan["seed_count"] == 2
    assert plan["accepted_train_only_seed_count"] == 1
    assert plan["near_miss_seed_count"] == 1
    assert plan["rescue_seed_policy"]["allow_accepted_train_only"] is True
    assert plan["seeds"][0]["rescue_seed_type"] == "accepted_train_only"


def test_build_rescue_plan_excludes_cross_generation_fingerprints() -> None:
    seed_row = row(diagnostic_q25=0.70)
    initial = build_rescue_plan([seed_row], top_k=1, budget_per_seed=5)
    excluded = {config_fingerprint(initial["configs"][0])}

    plan = build_rescue_plan([seed_row], top_k=1, budget_per_seed=5, generation=2, excluded_fingerprints=excluded)

    assert plan["rescue_generation"] == 2
    assert plan["excluded_config_fingerprint_count"] == 1
    assert excluded.isdisjoint({config_fingerprint(config) for config in plan["configs"]})


def test_build_rescue_plan_excludes_source_configs_by_default() -> None:
    seed_config = dict(BASE_CONFIG)
    seed_config["lookback_h"] = 504
    already_tested = dict(BASE_CONFIG)
    already_tested["lookback_h"] = 240
    already_fp = config_fingerprint(already_tested)

    plan = build_rescue_plan(
        [
            row(config=seed_config, diagnostic_q25=0.70),
            row(
                config=already_tested,
                diagnostic_q25=0.10,
                selection_sharpe=0.10,
                bootstrap_p5=-0.20,
            ),
        ],
        top_k=1,
        budget_per_seed=8,
    )

    assert plan["source_config_fingerprint_count"] == 2
    assert plan["excluded_source_config_fingerprint_count"] == 2
    assert plan["rescue_seed_policy"]["exclude_source_configs"] is True
    assert plan["candidate_budget_per_seed"] == 24
    assert plan["rescue_config_count"] == 8
    assert already_fp not in {config_fingerprint(config) for config in plan["configs"]}


def test_build_rescue_plan_gen2_requires_parent_failure_improvement() -> None:
    improved = row(
        diagnostic_triggered=False,
        failed_checks=("positive_3_of_4_years",),
        selection_sharpe=1.60,
        bootstrap_p5=0.50,
    )
    unimproved = row(
        config={**BASE_CONFIG, "lookback_h": 672},
        diagnostic_triggered=False,
        failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
        selection_sharpe=1.70,
        bootstrap_p5=0.40,
    )
    parent_counts = {
        config_fingerprint(improved["config"]): 2,
        config_fingerprint(unimproved["config"]): 2,
    }

    plan = build_rescue_plan(
        [improved, unimproved],
        top_k=2,
        budget_per_seed=3,
        generation=2,
        parent_failure_count_by_config_fingerprint=parent_counts,
    )

    assert plan["rescue_generation"] == 2
    assert plan["parent_failure_filter"]["enabled"] is True
    assert plan["seed_count"] == 1
    assert plan["seeds"][0]["config"] == improved["config"]


def test_build_rescue_plan_gen2_allows_accepted_parent_zero_hardening_continuation() -> None:
    accepted_config = dict(BASE_CONFIG)
    accepted_config["lookback_h"] = 672
    accepted = row(
        config=accepted_config,
        advance_passed=True,
        diagnostic_triggered=False,
        failed_checks=(),
        selection_sharpe=1.70,
        bootstrap_p5=0.45,
    )
    unimproved = row(
        config={**BASE_CONFIG, "lookback_h": 720},
        diagnostic_triggered=False,
        failed_checks=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min"),
        selection_sharpe=1.70,
        bootstrap_p5=0.40,
    )
    parent_counts = {
        config_fingerprint(accepted["config"]): 0,
        config_fingerprint(unimproved["config"]): 2,
    }

    plan = build_rescue_plan(
        [unimproved, accepted],
        top_k=2,
        budget_per_seed=3,
        generation=2,
        parent_failure_count_by_config_fingerprint=parent_counts,
    )

    assert plan["rescue_generation"] == 2
    assert plan["parent_failure_filter"]["allow_accepted_train_only_parent_zero_continuation"] is True
    assert plan["seed_count"] == 1
    assert plan["accepted_train_only_seed_count"] == 1
    assert plan["seeds"][0]["rescue_seed_type"] == "accepted_train_only"
    assert plan["seeds"][0]["config"] == accepted["config"]


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


def test_rescue_plan_script_accepts_progress_jsonl(tmp_path) -> None:
    progress = tmp_path / "artifact.progress.jsonl"
    progress.write_text(json.dumps({"key": "a", "row": row(failed_checks=("positive_3_of_4_years",))}) + "\n")
    progress.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "completed_rows": 1,
                "total_rows": 10,
                "effective_trials": 50,
            }
        )
    )
    plan_path = tmp_path / "progress_plan.json"
    config_path = tmp_path / "progress_configs.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/v9_xsec_rescue_plan.py"),
            str(progress),
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
    plan = json.loads(plan_path.read_text())
    assert metadata["source_kind"] == "progress"
    assert metadata["rescue_config_count"] > 0
    assert plan["source_meta"]["source_kind"] == "progress"
    assert plan["prior_effective_trials"] == 50
    assert config_path.exists()
