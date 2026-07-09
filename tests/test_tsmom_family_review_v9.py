from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_tsmom_family_review.py"
SPEC = importlib.util.spec_from_file_location("v9_tsmom_family_review", SCRIPT)
assert SPEC and SPEC.loader
review_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_mod)


def artifact_payload(*, accepted: bool = True, pass_count: int = 1, fingerprint: str = "fp1") -> dict:
    checks = {
        "sharpe20_ge_1_0": True,
        "max_dd20_le_30pct": True,
        "validation_sharpe20_ge_adjusted_min": True,
        "walk_forward_robust": True,
    }
    return {
        "kind": "tsmom_factory_v1_train_only_grid",
        "summary": {
            "accepted_train_only": accepted,
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "pass_count": pass_count,
            "rows": 2,
        },
        "data": {
            "fingerprint": fingerprint,
            "first_dt": "2020-01-01T00:00:00+00:00",
            "last_dt": "2024-05-31T23:00:00+00:00",
            "rows": 100,
            "symbols": ["BTCUSDT", "ETHUSDT"],
        },
        "selection_validation": {
            "effective_trials": 1000,
            "n_configs_tested": 2,
            "selection_bootstrap_p5_min": 0.4,
            "validation_sharpe20_min": 1.0,
            "lookbacks_h": [240, 336],
            "walk_forward_required": True,
            "drop_one_lookback_required": True,
            "leave_one_symbol_required": True,
        },
        "rows": [
            {
                "advance_passed": accepted,
                "config": {
                    "asset_vol_target_ann": 0.35,
                    "portfolio_vol_target_ann": 0.12,
                    "no_trade_band": 0.1,
                    "market_filter_h": 720,
                },
                "lookbacks_h": [240, 336],
                "cost20": {"sharpe": 1.8, "total_return": 1.2, "max_drawdown": 0.12, "bootstrap_30d_sharpe_p5": 1.1},
                "cost40": {"sharpe": 1.5},
                "validation": {"cost20": {"sharpe": 1.2, "total_return": 0.2, "max_drawdown": 0.1}, "cost40": {"sharpe": 0.9}},
                "walk_forward": {"passed": True, "q25_sharpe": 0.5, "sign_consistency": 1.0},
                "drop_one_lookback": {"passed": True},
                "leave_one_symbol": {"passed": True},
                "advance_checks": checks,
            }
        ],
    }


def write_artifact(root: Path, rel: str, payload: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_tsmom_family_review_groups_duplicates_and_keeps_safety_false(tmp_path) -> None:
    primary = "tsmom_primary"
    state = {
        "candidates_found": [
            {
                "task": primary,
                "status": "manual_review_required",
                "output_json": "artifacts/a.json",
                "output_md": "artifacts/a.md",
            },
            {
                "task": "tsmom_dup",
                "duplicate_of": primary,
                "status": "manual_review_required_data_drift",
                "output_json": "artifacts/b.json",
                "output_md": "artifacts/b.md",
            },
            {
                "task": "other",
                "status": "manual_review_required",
                "output_json": "artifacts/c.json",
                "output_md": "artifacts/c.md",
            },
        ]
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    write_artifact(tmp_path, "artifacts/a.json", artifact_payload(fingerprint="fp1"))
    write_artifact(tmp_path, "artifacts/b.json", artifact_payload(fingerprint="fp2"))
    write_artifact(tmp_path, "artifacts/c.json", artifact_payload(fingerprint="fp3"))

    review = review_mod.build_review(state_path, primary, tmp_path)
    text = review_mod.format_markdown(review)

    assert review["decision"] == "train_only_family_promising_manual_review_required"
    assert review["candidate_record_count"] == 2
    assert review["accepted_artifact_count"] == 2
    assert len(review["distinct_data_fingerprints"]) == 2
    assert "family_contains_data_drift_duplicates" in review["warnings"]
    assert review["holdout_authorized"] is False
    assert review["paper_trading_authorized"] is False
    assert review["live_trading_authorized"] is False
    assert "does not authorize holdout" in text


def test_tsmom_family_review_marks_single_fingerprint_warning(tmp_path) -> None:
    primary = "tsmom_primary"
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "candidates_found": [
                    {"task": primary, "status": "manual_review_required", "output_json": "artifacts/a.json"},
                ]
            }
        )
    )
    write_artifact(tmp_path, "artifacts/a.json", artifact_payload(fingerprint="same"))

    review = review_mod.build_review(state_path, primary, tmp_path)

    assert review["decision"] == "train_only_family_candidate_but_needs_drift_review"
    assert "accepted_family_seen_on_single_data_fingerprint" in review["warnings"]
