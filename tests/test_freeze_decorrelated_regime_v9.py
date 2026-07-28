from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import freeze_decorrelated_candidates_v9 as freeze


def fake_args() -> argparse.Namespace:
    return argparse.Namespace(
        regime_max_share=0.80,
        regime_min_coverage=2,
        regime_min_days=1,
        regime_gates_report_only=True,
        enforce_regime_gates=False,
    )


def test_candidate_regime_report_uses_scenario_windows() -> None:
    candidate = {
        "candidate_id": "c1",
        "symbol": "BTCUSDT",
        "scenario_details": [
            {"scenario": 1, "cost_bps": 20.0, "alpha": 0.04, "return": 0.05},
            {"scenario": 2, "cost_bps": 20.0, "alpha": -0.01, "return": -0.02},
        ],
    }
    manifest = [
        {"scenario": 1, "cost_bps": 20.0, "selected": {"BTCUSDT": ["2020-01"]}},
        {"scenario": 2, "cost_bps": 20.0, "selected": {"BTCUSDT": ["2020-02"]}},
    ]
    regime_ctx = {
        "config_sha256": "abc",
        "embargo_start": "2020-03-01 00:00:00+00:00",
        "labels": {
            "BTCUSDT": {
                "month_counts": {
                    "2020-01": {"up_normal": 20, "range_normal": 10},
                    "2020-02": {"down_normal": 29},
                }
            }
        },
    }

    report = freeze.compute_candidate_regime_report(candidate, manifest, regime_ctx, fake_args())

    assert report["method"] == "train_only_scenario_window_regime_screen_v1"
    assert report["regime_coverage"] == 3
    assert report["max_regime_share"] < 0.80
    assert report["gates"]["regime_coverage_gte_min"] is True
    assert "per-trade" in report["note"]


def test_candidate_regime_report_refuses_embargo_month() -> None:
    candidate = {"candidate_id": "c1", "symbol": "BTCUSDT", "scenario_details": []}
    manifest = [{"scenario": 1, "cost_bps": 20.0, "selected": {"BTCUSDT": ["2020-03"]}}]
    regime_ctx = {
        "config_sha256": "abc",
        "embargo_start": "2020-03-01 00:00:00+00:00",
        "labels": {"BTCUSDT": {"month_counts": {"2020-03": {"up_normal": 1}}}},
    }

    with pytest.raises(SystemExit):
        freeze.compute_candidate_regime_report(candidate, manifest, regime_ctx, fake_args())
