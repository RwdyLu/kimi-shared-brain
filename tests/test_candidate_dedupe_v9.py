from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.research.candidate_dedupe import dedupe_candidates, distinct_candidate_count, candidate_signature  # noqa: E402


def accepted_payload(config: dict) -> dict:
    return {
        "kind": "xsec_ohlcv_factory_v1_train_only_grid",
        "symbols": ["AAA", "BBB"],
        "summary": {"accepted_train_only": True},
        "rows": [{"advance_passed": True, "config": config}],
    }


def test_candidate_signature_defaults_missing_n_tranches_to_one() -> None:
    base = {
        "lookback_h": 504,
        "skip_h": 0,
        "rebalance_h": 168,
        "k": 3,
        "score_mode": "risk_adj_mom",
        "market_filter_h": 1008,
        "vol_target_ann": 0.06,
    }

    assert candidate_signature(accepted_payload(base)) == candidate_signature(accepted_payload({**base, "n_tranches": 1}))
    assert candidate_signature(accepted_payload(base)) != candidate_signature(accepted_payload({**base, "n_tranches": 3}))


def test_quarantined_candidates_do_not_count_as_distinct(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "candidate.json"
    artifact.write_text(json.dumps(accepted_payload({"lookback_h": 504})))
    candidates = [
        {
            "task": "drift",
            "output_json": str(artifact),
            "status": "quarantined_data_drift",
        }
    ]

    enriched = dedupe_candidates(candidates)

    assert enriched[0]["quarantined"] is True
    assert distinct_candidate_count(candidates) == 0


def test_rejected_multiplicity_candidates_do_not_count_as_distinct(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "candidate.json"
    artifact.write_text(json.dumps(accepted_payload({"lookback_h": 504})))
    candidates = [{"task": "weak", "output_json": str(artifact), "status": "rejected_multiplicity"}]

    enriched = dedupe_candidates(candidates)

    assert enriched[0]["quarantined"] is True
    assert distinct_candidate_count(candidates) == 0


def test_clean_candidate_after_quarantined_candidate_can_be_primary(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "candidate.json"
    artifact.write_text(json.dumps(accepted_payload({"lookback_h": 504})))
    candidates = [
        {"task": "drift", "output_json": str(artifact), "status": "quarantined_data_drift"},
        {"task": "clean", "output_json": str(artifact), "status": "manual_review_required"},
    ]

    enriched = dedupe_candidates(candidates)

    assert "duplicate_of" not in enriched[1]
    assert distinct_candidate_count(candidates) == 1
