from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_revalidation_status.py"
SPEC = importlib.util.spec_from_file_location("v9_revalidation_status", SCRIPT)
assert SPEC and SPEC.loader
status_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(status_mod)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def group(tmp_path: Path) -> dict:
    config_path = tmp_path / "artifacts/v9/revalidation/group_configs.json"
    write_json(config_path, {"configs": [{"lookback_h": 336, "k": 2}]})
    return {
        "group_id": "group-a",
        "module": "v9.contract.xsec_ohlcv_factory",
        "preset": "breakout_slow",
        "train_start": "2017-08-01",
        "train_end": "2024-03-31 23:59:59",
        "embargo_start": "2024-07-01",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "config_count": 1,
        "config_json": str(config_path),
        "data_snapshot_path": str(tmp_path / "artifacts/v9/data_snapshots/xsec.parquet"),
        "data_snapshot_fingerprint": "snap-123",
        "output_json": str(tmp_path / "artifacts/v9/contract_lab/revalidate_group-a.json"),
        "output_md": str(tmp_path / "artifacts/v9/contract_lab/revalidate_group-a.md"),
        "command": ["python3", "-m", "v9.contract.xsec_ohlcv_factory"],
    }


def write_plan(path: Path, group_row: dict) -> None:
    write_json(
        path,
        {
            "kind": "v9_train_only_candidate_revalidation_plan_v1",
            "groups": [group_row],
            "skipped": [],
        },
    )


def test_revalidation_status_reports_completed_accepted(tmp_path) -> None:
    row = group(tmp_path)
    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, row)
    write_json(
        Path(row["output_json"]),
        {
            "summary": {"accepted_train_only": True, "rows": 1},
            "selection_validation": {"n_configs_tested": 1, "effective_trials": 2},
            "data": {
                "fingerprint": "data-fp",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "snapshot": {"path": row["data_snapshot_path"], "fingerprint": row["data_snapshot_fingerprint"]},
            },
        },
    )
    fingerprint = status_mod.group_plan_fingerprint(row)
    write_json(
        status_mod.completion_metadata_path(row["output_json"]),
        {
            "kind": "v9_revalidation_group_completion_v1",
            "group_plan_fingerprint": fingerprint,
            "returncode": 0,
            "status": "accepted_train_only_candidate_found",
        },
    )

    report = status_mod.build_report(plan_path, runner_state_path=tmp_path / "runner_state.json")

    assert report["status_counts"] == {"completed_accepted": 1}
    assert report["groups"][0]["output_status"] == "accepted_train_only_candidate_found"
    assert report["groups"][0]["data_snapshot_fingerprint"] == "snap-123"


def test_revalidation_status_detects_live_process_without_runner_state(tmp_path) -> None:
    row = group(tmp_path)
    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, row)

    report = status_mod.build_report(
        plan_path,
        runner_state_path=tmp_path / "runner_state.json",
        include_processes=True,
        process_scan=[
            "1234 00:10 80.0 2.0 python3 -m v9.contract.xsec_ohlcv_factory --out-json "
            + row["output_json"]
        ],
    )

    assert report["groups"][0]["status"] == "running_process_detected"
    assert report["groups"][0]["process_pid"] == "1234"


def test_revalidation_status_reports_progress_without_runner_state(tmp_path) -> None:
    row = group(tmp_path)
    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, row)
    progress = Path(row["output_json"]).with_suffix(".progress.jsonl")
    progress.parent.mkdir(parents=True, exist_ok=True)
    progress.write_text("{}\n{}\n")
    write_json(progress.with_suffix(".meta.json"), {"total_rows": 4, "cache_version": "unit"})

    report = status_mod.build_report(plan_path, runner_state_path=tmp_path / "runner_state.json")

    assert report["groups"][0]["status"] == "progress_without_runner_state"
    assert report["groups"][0]["progress_rows"] == 2
    assert report["groups"][0]["progress_total_rows"] == 4
    assert report["groups"][0]["progress_pct"] == 0.5
    assert report["groups"][0]["progress_updated_at"]
    assert report["groups"][0]["progress_age_sec"] >= 0
    assert report["generated_at"]
