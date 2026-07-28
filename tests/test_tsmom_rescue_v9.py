from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.tsmom_rescue import (  # noqa: E402
    build_tsmom_rescue_plan,
    generate_tsmom_rescue_neighbors,
    select_tsmom_rescue_seeds,
    write_tsmom_rescue_artifacts,
)


BASE_CONFIG = {
    "asset_vol_target_ann": 0.35,
    "portfolio_vol_target_ann": 0.12,
    "no_trade_band": 0.10,
    "vote_threshold": 0.50,
    "market_filter_h": 720,
    "market_off_scale": 0.0,
    "drawdown_stop": 0.0,
    "cooldown_h": 0,
    "bear_mode": "short_weak",
    "bear_short_scale": 0.50,
    "short_vote_threshold": 0.375,
}


def row(
    *,
    config: dict | None = None,
    failed_checks: tuple[str, ...] = ("drop_one_lookback_stable",),
    bootstrap_passed: bool = True,
    walk_forward_passed: bool = True,
    validation_sharpe: float = 1.22,
) -> dict:
    checks = {
        "bootstrap_p5_ge_adjusted_min": bootstrap_passed,
        "drop_one_lookback_stable": "drop_one_lookback_stable" not in failed_checks,
        "leave_one_symbol_robust": "leave_one_symbol_robust" not in failed_checks,
        "validation_sharpe20_ge_adjusted_min": "validation_sharpe20_ge_adjusted_min" not in failed_checks,
        "selection_passed_before_validation": "selection_passed_before_validation" not in failed_checks,
    }
    return {
        "config": dict(config or BASE_CONFIG),
        "advance_passed": False,
        "advance_checks": checks,
        "selection": {
            "checks": {
                "bootstrap_p5_ge_adjusted_min": bootstrap_passed,
                "walk_forward_robust": walk_forward_passed,
            },
            "cost20": {
                "sharpe": 2.2,
                "total_return": 2.0,
                "max_drawdown": 0.13,
                "bootstrap_30d_sharpe_p5": 1.4 if bootstrap_passed else 0.1,
            },
        },
        "validation": {"cost20": {"sharpe": validation_sharpe, "max_drawdown": 0.14}},
        "walk_forward": {"passed": walk_forward_passed, "q25_sharpe": 0.80},
    }


def test_select_tsmom_rescue_seeds_requires_allowed_failures_and_selection_strength() -> None:
    rows = [
        row(),
        row(failed_checks=("selection_passed_before_validation",)),
        row(bootstrap_passed=False),
        row(walk_forward_passed=False),
    ]

    seeds = select_tsmom_rescue_seeds(rows, meta={"selection_bootstrap_p5_min": 0.47})

    assert len(seeds) == 1
    assert seeds[0]["failed_checks"] == ["drop_one_lookback_stable"]
    assert seeds[0]["validation_sharpe20"] == 1.22


def test_generate_tsmom_rescue_neighbors_prioritizes_failure_repair() -> None:
    seed = select_tsmom_rescue_seeds([row(failed_checks=("drop_one_lookback_stable", "validation_sharpe20_ge_adjusted_min"))])[0]

    neighbors = generate_tsmom_rescue_neighbors(seed, budget=6)

    assert len(neighbors) == 6
    assert neighbors[0]["changed_gene"] == "vote_threshold"
    assert len({neighbor["config_fingerprint"] for neighbor in neighbors}) == len(neighbors)
    assert all(neighbor["config"]["bear_mode"] == "short_weak" for neighbor in neighbors)


def test_build_tsmom_rescue_plan_counts_trials_and_keeps_safety_false(tmp_path) -> None:
    alternate = dict(BASE_CONFIG)
    alternate["market_filter_h"] = 1440
    plan = build_tsmom_rescue_plan(
        [row(), row(config=alternate, validation_sharpe=1.4)],
        meta={"effective_trials": 26358},
        source_artifact="artifact.json",
        top_k=2,
        budget_per_seed=5,
    )

    assert plan["kind"] == "tsmom_near_miss_rescue_plan_v1"
    assert plan["seed_count"] == 2
    assert plan["rescue_config_count"] == 10
    assert plan["effective_trials_after_rescue"] == 26368
    assert plan["accepted_via_rescue"] is True
    assert plan["holdout_authorized"] is False
    assert plan["paper_trading_authorized"] is False
    assert plan["live_trading_authorized"] is False
    assert all("parent_tsmom_rescue_source_index" in config for config in plan["configs"])

    metadata = write_tsmom_rescue_artifacts(plan, tmp_path / "plan.json", tmp_path / "configs.json")
    assert metadata["rescue_config_count"] == 10
    assert json.loads((tmp_path / "configs.json").read_text()) == plan["configs"]


def test_tsmom_rescue_plan_script_runs_from_repo_root(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        json.dumps(
            {
                "summary": {"accepted_train_only": False},
                "selection_validation": {"effective_trials": 100},
                "rows": [row()],
            }
        )
    )
    plan_path = tmp_path / "plan.json"
    config_path = tmp_path / "configs.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/v9_tsmom_rescue_plan.py"),
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
