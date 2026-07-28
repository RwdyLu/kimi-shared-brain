from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_status.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_status", SCRIPT)
assert SPEC and SPEC.loader
status_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status_mod)


def test_build_status_reports_progress_and_safety(tmp_path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    task = "demo_task"
    (state_dir / "v9_auto_research_state.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-07-07T00:00:00+00:00",
                "mode": "continuous",
                "status": "running",
                "reason": "continuous_train_only:demo_task",
                "cycle_index": 3,
                "current_task": task,
                "active_task": {"status": "running", "elapsed_sec": 12.5},
                "tasks_done_total": 4,
                "candidates_found_total": 2,
                "distinct_candidates": 1,
                "holdout_authorized": False,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
        )
    )
    (state_dir / "latest_strategy_summary.txt").write_text("running demo\n")
    artifact_dir = tmp_path / "artifacts" / "v9" / "contract_lab"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / f"{task}.progress.jsonl").write_text("{}\n{}\n")
    (artifact_dir / f"{task}.progress.meta.json").write_text(
        json.dumps({"total_rows": 8, "cache_version": "v1"})
    )

    status = status_mod.build_status(tmp_path)

    assert status["status"] == "running"
    assert status["progress_rows"] == 2
    assert status["progress_total_rows"] == 8
    assert status["progress_pct"] == 0.25
    assert status["progress_cache_version"] == "v1"
    assert status["holdout_authorized"] is False
    assert status["paper_trading_authorized"] is False
    assert status["live_trading_authorized"] is False


def test_format_text_includes_progress() -> None:
    text = status_mod.format_text(
        {
            "status": "running",
            "reason": "reason",
            "progress_rows": 2,
            "progress_total_rows": 8,
            "progress_pct": 0.25,
            "current_task": "task",
            "candidates_found_total": 1,
            "distinct_candidates": 1,
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        }
    )
    assert "progress=2/8 (25.0%)" in text
    assert "holdout:False" in text
