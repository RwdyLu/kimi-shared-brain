from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.task_planner import (  # noqa: E402
    load_explored_fingerprints,
    append_explored_record,
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
        assert "v9.contract.xsec_ohlcv_factory" in cmd
        assert "holdout" not in cmd
        assert "paper" not in cmd
        assert "live" not in cmd
        assert "--embargo-start 2024-07-01" in cmd
        assert task.train_end < "2024-07"
    presets = {task.preset for task in proposed_search_space()}
    assert {"hq_dd_long", "hq_fast_rebal", "hq_breadth_wide"}.issubset(presets)


def test_explored_jsonl_round_trip(tmp_path) -> None:
    fp = task_fingerprint("core", "2017-08-01", "2024-06-30 23:59:59")
    path = tmp_path / "explored.jsonl"
    append_explored_record(path, {"fingerprint": fp, "status": "completed_no_candidate"})
    assert load_explored_fingerprints(path) == {fp}


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
    first = propose_tasks(set(), 1, task_results=task_results, candidates=candidates)
    assert first[0].preset == "defensive_drawdown"
