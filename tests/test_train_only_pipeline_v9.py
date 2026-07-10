from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_pipeline.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_pipeline", SCRIPT)
assert SPEC and SPEC.loader
pipeline_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_mod)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def artifact(path: Path, lookback_h: int = 336) -> None:
    write_json(
        path,
        {
            "kind": "xsec_ohlcv_factory_v1_train_only_grid",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "top": [
                {
                    "advance_passed": True,
                    "config": {
                        "k": 3,
                        "lookback_h": lookback_h,
                        "market_filter_h": 1008,
                        "rebalance_h": 240,
                        "score_mode": "risk_adj_mom",
                        "n_tranches": 1,
                    },
                    "selection": {"cost40": {"sharpe": 2.0}},
                }
            ],
        },
    )


def args(tmp_path: Path) -> Namespace:
    return Namespace(
        state=str(tmp_path / "state.json"),
        base=str(tmp_path),
        registry=str(tmp_path / "registry.json"),
        queue=str(tmp_path / "queue.jsonl"),
        assignments_jsonl=str(tmp_path / "family_assignments.jsonl"),
        out_json=str(tmp_path / "pipeline.json"),
        out_md=str(tmp_path / "pipeline.md"),
        lock=str(tmp_path / "pipeline.lock"),
        queue_known_families=False,
        holdout_authorized=False,
        max_holdouts=0,
        holdout_timeout_sec=30,
        format="json",
    )


def test_pipeline_queues_novel_family_and_is_idempotent(tmp_path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact(artifact_path)
    write_json(
        tmp_path / "state.json",
        {
            "candidates_found": [
                {
                    "task": "xsec_task",
                    "status": "manual_review_required",
                    "output_json": str(artifact_path),
                }
            ]
        },
    )
    opts = args(tmp_path)

    first = pipeline_mod.build_report(opts)
    second = pipeline_mod.build_report(opts)

    assert first["summary"]["queued_count"] == 1
    assert first["summary"]["total_queue_family_count"] == 1
    assert first["holdout"]["ran"] is False
    assert first["live_trading_authorized"] is False
    assert second["summary"]["queued_count"] == 0
    assert second["summary"]["existing_queue_family_count"] == 1
    assert second["summary"]["total_queue_family_count"] == 1
    assert len((tmp_path / "queue.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / "family_assignments.jsonl").read_text().splitlines()) == 1


def test_pipeline_does_not_queue_rejected_family(tmp_path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact(artifact_path)
    write_json(
        tmp_path / "state.json",
        {
            "candidates_found": [
                {
                    "task": "xsec_task",
                    "status": "rejected_multiplicity",
                    "output_json": str(artifact_path),
                }
            ]
        },
    )

    report = pipeline_mod.build_report(args(tmp_path))

    assert report["summary"]["queued_count"] == 0
    assert report["summary"]["new_family_count"] == 1
    assert report["summary"]["registry_family_count"] == 1


def test_pipeline_uses_final_family_status_before_queueing(tmp_path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact(artifact_path)
    write_json(
        tmp_path / "state.json",
        {
            "candidates_found": [
                {
                    "task": "xsec_first_seen",
                    "status": "manual_review_required",
                    "output_json": str(artifact_path),
                },
                {
                    "task": "xsec_duplicate_later",
                    "status": "rejected_multiplicity",
                    "output_json": str(artifact_path),
                },
            ]
        },
    )

    report = pipeline_mod.build_report(args(tmp_path))
    registry = json.loads((tmp_path / "registry.json").read_text())
    families = registry["families"]

    assert report["summary"]["queued_count"] == 0
    assert len(families) == 1
    family = next(iter(families.values()))
    assert family["status"] == "rejected_multiplicity"
    assert family["seen_count"] == 2
    assert not (tmp_path / "queue.jsonl").exists()
