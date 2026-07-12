from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.task_planner import (  # noqa: E402
    append_explored_record,
    cumulative_trials,
    candidate_quality,
    load_explored_fingerprints,
    ordered_presets_by_quality,
    propose_tasks,
    proposed_search_space,
    task_fingerprint,
)
from v9.contract.report import write_json  # noqa: E402


def test_task_planner_is_deterministic_and_does_not_repeat_explored() -> None:
    first = propose_tasks(set(), 5)
    second = propose_tasks(set(), 5)
    assert [task.fingerprint for task in first] == [task.fingerprint for task in second]
    explored = {task.fingerprint for task in first[:2]}
    later = propose_tasks(explored, 5)
    assert not explored.intersection({task.fingerprint for task in later})


def test_task_planner_outputs_train_only_commands_before_embargo() -> None:
    for task in proposed_search_space()[:20]:
        cmd = " ".join(task.command())
        assert "v9.contract.xsec_ohlcv_factory" in cmd or "v9.contract.tsmom_factory" in cmd
        assert "holdout" not in cmd
        assert "paper" not in cmd
        assert "live" not in cmd
        assert "--embargo-start 2024-07-01" in cmd
        assert task.train_end < "2024-07"
    presets = {task.preset for task in proposed_search_space()}
    assert {
        "tsmom_bear_short_medium",
        "tsmom_bear_short_medium_neighbor",
        "tsmom_bear_short_medium_risk",
        "tsmom_bear_short_cost_guard",
        "tsmom_slow_cost_guard",
        "tsmom_ultra_slow_cost_guard",
        "tsmom_core_cost_guard",
        "tsmom_core_slow_cost_guard",
        "tsmom_bear_short_fast",
        "tsmom_bear_short_regime",
        "tsmom_defensive_regime",
        "tsmom_trend_ensemble",
        "hq_cadence_tranche",
        "hq_dd_long",
        "hq_dd_plateau",
        "evergreen_fast",
        "evergreen_guarded",
        "evergreen_regime_guarded",
        "evergreen_lowvol_guarded",
        "breakout_fast",
        "breakout_slow",
        "hq_fast_rebal",
        "hq_breadth_wide",
    }.issubset(presets)


def test_explored_jsonl_round_trip(tmp_path) -> None:
    fp = task_fingerprint("core", "2017-08-01", "2024-06-30 23:59:59")
    path = tmp_path / "explored.jsonl"
    append_explored_record(path, {"fingerprint": fp, "status": "completed_no_candidate"})
    assert load_explored_fingerprints(path) == {fp}


def test_cumulative_trials_sums_explored_ledger(tmp_path) -> None:
    path = tmp_path / "explored.jsonl"
    append_explored_record(path, {"fingerprint": "a", "n_configs_tested": 8})
    append_explored_record(path, {"fingerprint": "b", "n_configs_tested": 12})
    append_explored_record(path, {"fingerprint": "c"})
    assert cumulative_trials(path) == 20


def test_prior_trials_in_command_but_not_fingerprint() -> None:
    with_prior = propose_tasks(set(), 1, prior_trials=250)[0]
    without_prior = propose_tasks(set(), 1, prior_trials=0)[0]
    assert "--prior-trials 250" in " ".join(with_prior.command())
    assert with_prior.fingerprint == without_prior.fingerprint


def test_task_fingerprint_changes_with_evaluation_version() -> None:
    old = task_fingerprint("core", "2017-08-01", "2024-06-30 23:59:59", evaluation_version="old")
    new = task_fingerprint("core", "2017-08-01", "2024-06-30 23:59:59", evaluation_version="new")
    assert old != new


def test_quality_aware_order_prefers_high_quality_distinct_candidate(tmp_path) -> None:
    out = tmp_path / "accepted.json"
    write_json(
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "symbols": ["AAA", "BBB"],
            "summary": {"accepted_train_only": True},
            "rows": [
                {
                    "advance_passed": True,
                    "config": {"lookback_h": 720, "rebalance_h": 168},
                    "cost20": {"bootstrap_30d_sharpe_p5": 1.8, "max_drawdown": 0.14},
                    "cost40": {"sharpe": 2.2},
                    "validation": {
                        "cost20": {"bootstrap_30d_sharpe_p5": 2.0, "max_drawdown": 0.10},
                        "cost40": {"sharpe": 2.4},
                    },
                }
            ],
        },
        out,
    )
    task_results = [
        {
            "task": "winner",
            "status": "accepted_train_only_candidate_found",
            "output_json": str(out),
            "planned_task": {"preset": "defensive_drawdown"},
        },
        {
            "task": "loser",
            "status": "completed_no_candidate",
            "output_json": str(tmp_path / "missing.json"),
            "planned_task": {"preset": "fast"},
        },
    ]
    candidates = [{"task": "winner", "output_json": str(out), "output_md": str(tmp_path / "accepted.md")}]
    ordered = ordered_presets_by_quality(task_results, candidates)
    assert ordered.index("defensive_drawdown") < ordered.index("fast")


def test_candidate_quality_uses_selection_not_validation(tmp_path) -> None:
    sel20 = {"bootstrap_30d_sharpe_p5": 0.40, "max_drawdown": 0.10}
    sel40 = {"sharpe": 1.10}
    row = {
        "advance_passed": True,
        "cost20": sel20,
        "cost40": sel40,
        "selection": {"cost20": sel20, "cost40": sel40},
        "validation": {
            "cost20": {"bootstrap_30d_sharpe_p5": 9.9, "max_drawdown": 0.0},
            "cost40": {"sharpe": 9.9},
        },
    }
    out = tmp_path / "accepted.json"
    out.write_text(json.dumps({"rows": [row]}))

    quality = candidate_quality(str(out))
    assert quality == pytest.approx(0.40 + 0.25 * 1.10 - 0.5 * 0.10)

    row["validation"]["cost20"]["bootstrap_30d_sharpe_p5"] = 0.0
    row["validation"]["cost40"]["sharpe"] = 0.0
    out.write_text(json.dumps({"rows": [row]}))
    assert candidate_quality(str(out)) == pytest.approx(quality)


def test_candidate_quality_zero_drawdown_is_not_missing(tmp_path) -> None:
    row = {
        "advance_passed": True,
        "selection": {
            "cost20": {"bootstrap_30d_sharpe_p5": 0.30, "max_drawdown": 0.0},
            "cost40": {"sharpe": 1.0},
        },
    }
    out = tmp_path / "accepted.json"
    out.write_text(json.dumps({"rows": [row]}))

    assert candidate_quality(str(out)) == pytest.approx(0.30 + 0.25 * 1.0)


def test_focus_train_only_presets_take_priority() -> None:
    first = propose_tasks(set(), 16)
    assert [task.preset for task in first[:12]] == [
        "tsmom_defensive_regime",
        "tsmom_bear_short_regime",
        "tsmom_trend_ensemble",
        "tsmom_bear_short_medium",
        "tsmom_bear_short_medium_neighbor",
        "tsmom_bear_short_medium_risk",
        "tsmom_bear_short_cost_guard",
        "tsmom_slow_cost_guard",
        "tsmom_ultra_slow_cost_guard",
        "tsmom_core_cost_guard",
        "tsmom_core_slow_cost_guard",
        "tsmom_bear_short_fast",
    ]
    assert [task.preset for task in first[12:16]] == [
        "evergreen_regime_guarded",
        "evergreen_lowvol_guarded",
        "evergreen_guarded",
        "evergreen_fast",
    ]
    assert all(task.module == "v9.contract.tsmom_factory" for task in first[:12])
    assert first[0].cli_preset == "defensive_regime"
    assert first[1].cli_preset == "bear_short_regime"
    assert first[2].cli_preset == "core"
    assert first[3].cli_preset == "bear_short_medium"
    assert all(task.module == "v9.contract.xsec_ohlcv_factory" for task in first[12:16])


def test_xsec_first_preset_mode_prioritizes_xsec_without_disabling_tsmom() -> None:
    first = propose_tasks(set(), 20, preset_mode="xsec_first")
    assert [task.preset for task in first[:18]] == [
        "evergreen_regime_guarded",
        "evergreen_lowvol_guarded",
        "evergreen_guarded",
        "evergreen_fast",
        "breakout_fast",
        "breakout_slow",
        "hq_dd_plateau",
        "hq_dd_long",
        "defensive_drawdown",
        "hq_cadence_tranche",
        "hq_breadth_wide",
        "hq_fast_rebal",
        "defensive_neighbor",
        "defensive_breadth",
        "defensive",
        "slow",
        "core",
        "fast",
    ]
    assert all(task.module == "v9.contract.xsec_ohlcv_factory" for task in first[:18])
    assert [task.preset for task in first[18:20]] == [
        "tsmom_defensive_regime",
        "tsmom_bear_short_regime",
    ]
    assert all(task.module == "v9.contract.tsmom_factory" for task in first[18:20])


def test_propose_tasks_uses_quality_aware_preset_order(tmp_path) -> None:
    out = tmp_path / "accepted.json"
    write_json(
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "symbols": ["AAA", "BBB"],
            "summary": {"accepted_train_only": True},
            "rows": [
                {
                    "advance_passed": True,
                    "config": {"lookback_h": 720, "rebalance_h": 168},
                    "cost20": {"bootstrap_30d_sharpe_p5": 1.8, "max_drawdown": 0.14},
                    "cost40": {"sharpe": 2.2},
                    "validation": {
                        "cost20": {"bootstrap_30d_sharpe_p5": 2.0, "max_drawdown": 0.10},
                        "cost40": {"sharpe": 2.4},
                    },
                }
            ],
        },
        out,
    )
    task_results = [
        {
            "task": "winner",
            "status": "accepted_train_only_candidate_found",
            "output_json": str(out),
            "planned_task": {"preset": "defensive_drawdown"},
        }
    ]
    candidates = [{"task": "winner", "output_json": str(out), "output_md": str(tmp_path / "accepted.md")}]
    first = propose_tasks(set(), 16, task_results=task_results, candidates=candidates)
    assert [task.preset for task in first[:12]] == [
        "tsmom_defensive_regime",
        "tsmom_bear_short_regime",
        "tsmom_trend_ensemble",
        "tsmom_bear_short_medium",
        "tsmom_bear_short_medium_neighbor",
        "tsmom_bear_short_medium_risk",
        "tsmom_bear_short_cost_guard",
        "tsmom_slow_cost_guard",
        "tsmom_ultra_slow_cost_guard",
        "tsmom_core_cost_guard",
        "tsmom_core_slow_cost_guard",
        "tsmom_bear_short_fast",
    ]
    assert [task.preset for task in first[12:16]] == [
        "evergreen_regime_guarded",
        "evergreen_lowvol_guarded",
        "evergreen_guarded",
        "evergreen_fast",
    ]
