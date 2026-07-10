from __future__ import annotations

from v9.research.family_registry import (
    family_fingerprint,
    normalized_family_payload,
    queue_allowed,
    upsert_family,
)


def artifact_payload(lookback_h: int = 336, status: str = "manual_review_required") -> tuple[dict, dict]:
    payload = {
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
    }
    candidate = {
        "task": "xsec",
        "status": status,
        "output_json": "artifact.json",
    }
    return payload, candidate


def test_family_fingerprint_buckets_nearby_lookbacks() -> None:
    left, _ = artifact_payload(lookback_h=336)
    right, _ = artifact_payload(lookback_h=360)
    far, _ = artifact_payload(lookback_h=721)

    assert normalized_family_payload(left)["lookback_bucket"] == "medium"
    assert family_fingerprint(left, "a.json") == family_fingerprint(right, "b.json")
    assert family_fingerprint(left, "a.json") != family_fingerprint(far, "c.json")


def test_registry_queue_allows_only_first_non_rejected_family() -> None:
    payload, candidate = artifact_payload()
    registry = {"families": {}}
    fp = family_fingerprint(payload, "artifact.json")
    family = normalized_family_payload(payload, "artifact.json")

    entry, created = upsert_family(
        registry,
        fingerprint=fp,
        family=family,
        candidate=candidate,
        artifact="artifact.json",
        train_metric=2.0,
    )
    assert created is True
    assert queue_allowed(entry, candidate) is True

    entry, created = upsert_family(
        registry,
        fingerprint=fp,
        family=family,
        candidate=candidate,
        artifact="artifact_2.json",
        train_metric=2.1,
    )
    assert created is False
    assert queue_allowed(entry, candidate) is False


def test_registry_blocks_rejected_family() -> None:
    payload, candidate = artifact_payload(status="rejected_multiplicity")
    registry = {"families": {}}
    fp = family_fingerprint(payload, "artifact.json")
    entry, _ = upsert_family(
        registry,
        fingerprint=fp,
        family=normalized_family_payload(payload, "artifact.json"),
        candidate=candidate,
        artifact="artifact.json",
    )

    assert entry["status"] == "rejected_multiplicity"
    assert queue_allowed(entry, candidate) is False
