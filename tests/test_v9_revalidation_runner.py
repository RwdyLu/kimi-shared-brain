from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_revalidation_runner.py"
SPEC = importlib.util.spec_from_file_location("v9_revalidation_runner", SCRIPT)
assert SPEC and SPEC.loader
runner_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner_mod)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def write_snapshot(path: Path, *, fingerprint: str = "snap-123") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("snapshot")
    write_json(
        path.with_suffix(path.suffix + ".json"),
        {
            "kind": "xsec_ohlcv_data_snapshot_v1",
            "fingerprint": fingerprint,
            "train_start": "2017-08-01",
            "train_end": "2024-01-31 23:59:59",
            "embargo_start": "2024-07-01",
            "symbols": ["BTCUSDT", "ETHUSDT"],
        },
    )


def plan_group(tmp_path: Path, *, snapshot_fingerprint: str = "snap-123") -> dict:
    config_json = tmp_path / "artifacts/v9/revalidation/group_configs.json"
    write_json(config_json, {"configs": [{"lookback_h": 336, "k": 2}]})
    snapshot = tmp_path / "artifacts/v9/data_snapshots/xsec.parquet"
    return {
        "group_id": "group-a",
        "module": "v9.contract.xsec_ohlcv_factory",
        "preset": "hq_dd_plateau",
        "cli_preset": "hq_dd_plateau",
        "train_start": "2017-08-01",
        "train_end": "2024-01-31 23:59:59",
        "embargo_start": "2024-07-01",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "config_count": 1,
        "config_json": str(config_json),
        "data_snapshot_path": str(snapshot),
        "data_snapshot_fingerprint": snapshot_fingerprint,
        "output_json": str(tmp_path / "artifacts/v9/contract_lab/revalidate_group-a.json"),
        "output_md": str(tmp_path / "artifacts/v9/contract_lab/revalidate_group-a.md"),
        "command": [
            "python3",
            "-m",
            "v9.contract.xsec_ohlcv_factory",
            "--data-snapshot",
            str(snapshot),
            "--preset",
            "hq_dd_plateau",
            "--config-list-json",
            str(config_json),
        ],
    }


def write_plan(path: Path, group: dict) -> None:
    write_json(
        path,
        {
            "kind": "v9_train_only_candidate_revalidation_plan_v1",
            "group_count": 1,
            "pinned_group_count": 1,
            "groups": [group],
            "skipped": [],
        },
    )


def test_revalidation_runner_aborts_on_snapshot_fingerprint_mismatch(tmp_path) -> None:
    group = plan_group(tmp_path, snapshot_fingerprint="expected-snap")
    write_snapshot(Path(group["data_snapshot_path"]), fingerprint="other-snap")

    row = runner_mod.run_group(
        group,
        runner_state_path=tmp_path / "runner_state.json",
        log_dir=tmp_path / "logs",
        dry_run=True,
    )

    assert row["status"] == "snapshot_verification_failed"
    assert row["returncode"] is None
    assert row["snapshot_check"]["reason"] == "snapshot_fingerprint_mismatch"


def test_revalidation_runner_skips_completed_matching_plan_fingerprint(tmp_path) -> None:
    group = plan_group(tmp_path)
    output = Path(group["output_json"])
    write_json(output, {"summary": {"accepted_train_only": True}})
    fingerprint = runner_mod.group_plan_fingerprint(group)
    write_json(
        runner_mod.completion_metadata_path(group["output_json"]),
        {
            "kind": "v9_revalidation_group_completion_v1",
            "group_id": group["group_id"],
            "group_plan_fingerprint": fingerprint,
            "returncode": 0,
        },
    )

    row = runner_mod.run_group(
        group,
        runner_state_path=tmp_path / "runner_state.json",
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    assert row["status"] == "skipped_existing"
    assert row["returncode"] == 0


def test_revalidation_runner_dry_run_preserves_plan_command(tmp_path, monkeypatch) -> None:
    group = plan_group(tmp_path)
    write_snapshot(Path(group["data_snapshot_path"]))
    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, group)

    def fake_read_data_snapshot(snapshot_path, cfg):
        return None, {"fingerprint": group["data_snapshot_fingerprint"]}

    monkeypatch.setattr(runner_mod, "read_data_snapshot", fake_read_data_snapshot)

    report = runner_mod.run_plan(
        plan_path,
        runner_state_path=tmp_path / "runner_state.json",
        log_dir=tmp_path / "logs",
        max_groups=1,
        dry_run=True,
    )

    assert report["selected_group_count"] == 1
    assert report["rows"][0]["status"] == "dry_run"
    assert report["rows"][0]["command"] == group["command"]
    state = json.loads((tmp_path / "runner_state.json").read_text())
    assert state["summary"]["dry_run_count"] == 1
