from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.triage import build_manual_review_queue, write_manual_review_queue  # noqa: E402


def write_candidate_artifact(path: Path, config: dict, symbols: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "symbols": symbols or ["BTCUSDT", "ETHUSDT"],
                "summary": {"accepted_train_only": True},
                "rows": [{"advance_passed": True, "config": config}],
            },
            sort_keys=True,
        )
    )


def result_for(path: Path, adjusted_p_value: float, z_score: float, sharpe: float, snapshot: str = "") -> dict:
    return {
        "task": path.stem,
        "output_json": str(path),
        "status": "accepted_train_only_candidate_found",
        "returncode": 0,
        "fingerprint": path.stem,
        "data_snapshot_fingerprint": snapshot,
        "planned_task": {
            "train_start": "2019-01-01",
            "train_end": "2024-03-31 23:59:59",
            "embargo_start": "2024-07-01",
            "module": "v9.contract.xsec_ohlcv_factory",
            "preset": "hq_dd_plateau",
            "cli_preset": "hq_dd_plateau",
        },
        "multiplicity_decision": "multiplicity_survivor",
        "multiplicity_evidence": {
            "evaluated": True,
            "decision": "multiplicity_survivor",
            "metrics": {
                "adjusted_p_value": adjusted_p_value,
                "z_score": z_score,
                "sharpe": sharpe,
                "max_drawdown": 0.16,
            },
        },
    }


def test_manual_review_queue_ranks_replicated_strong_family_and_drops_duplicates(tmp_path) -> None:
    strong_config = {"lookback_h": 504, "rebalance_h": 168, "k": 3, "score_mode": "risk_adj_mom"}
    weak_config = {"lookback_h": 168, "rebalance_h": 24, "k": 2, "score_mode": "mom"}
    candidates = []
    task_results = []

    for idx in range(3):
        path = tmp_path / f"strong_{idx}.json"
        write_candidate_artifact(path, strong_config)
        candidates.append(
            {
                "task": f"strong_{idx}",
                "output_json": str(path),
                "output_md": str(path.with_suffix(".md")),
                "status": "manual_review_required",
                "data_snapshot_fingerprint": "snap-strong",
            }
        )
        task_results.append(result_for(path, adjusted_p_value=0.001, z_score=4.0, sharpe=2.2, snapshot="snap-strong"))

    for idx in range(5):
        path = tmp_path / f"weak_{idx}.json"
        write_candidate_artifact(path, weak_config)
        candidates.append(
            {
                "task": f"weak_{idx}",
                "output_json": str(path),
                "output_md": str(path.with_suffix(".md")),
                "status": "manual_review_required",
            }
        )
        task_results.append(result_for(path, adjusted_p_value=0.20, z_score=0.8, sharpe=1.0))

    queue = build_manual_review_queue(candidates, task_results=task_results)
    assert len(queue) == 2
    assert queue == build_manual_review_queue(candidates, task_results=task_results)
    assert queue[0]["data_snapshot_fingerprint"] == "snap-strong"
    assert queue[0]["score"] > queue[1]["score"]
    assert queue[0]["score_components"]["replication_count"] == 3
    assert queue[1]["score_components"]["duplicate_count"] == 4
    assert all("duplicate_of" not in row for row in queue)
    assert all(row["holdout_authorized"] is False for row in queue)
    assert all(row["paper_trading_authorized"] is False for row in queue)
    assert all(row["live_trading_authorized"] is False for row in queue)

    payload = write_manual_review_queue(tmp_path / "manual_review_queue.json", candidates, task_results=task_results)
    assert payload["entry_count"] == 2
    written = json.loads((tmp_path / "manual_review_queue.json").read_text())
    assert written["entries"][0]["identity"] == queue[0]["identity"]
    assert written["paper_trading_authorized"] is False
