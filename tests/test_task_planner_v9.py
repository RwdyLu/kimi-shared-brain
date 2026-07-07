from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.task_planner import (  # noqa: E402
    load_explored_fingerprints,
    append_explored_record,
    propose_tasks,
    proposed_search_space,
    task_fingerprint,
)


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


def test_explored_jsonl_round_trip(tmp_path) -> None:
    fp = task_fingerprint("core", "2017-08-01", "2024-06-30 23:59:59")
    path = tmp_path / "explored.jsonl"
    append_explored_record(path, {"fingerprint": fp, "status": "completed_no_candidate"})
    assert load_explored_fingerprints(path) == {fp}

