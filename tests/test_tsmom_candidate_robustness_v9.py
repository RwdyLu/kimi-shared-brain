from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_tsmom_candidate_robustness.py"
SPEC = importlib.util.spec_from_file_location("v9_tsmom_candidate_robustness", SCRIPT)
assert SPEC and SPEC.loader
robustness_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(robustness_mod)


def row(config: dict, passed: bool, val20: float, val40: float, dd20: float = 0.12, ret40: float = 0.10) -> dict:
    return {
        "advance_passed": passed,
        "config": config,
        "selection": {
            "cost20": {
                "sharpe": 1.8,
                "total_return": 1.0,
                "max_drawdown": 0.16,
                "bootstrap_30d_sharpe_p5": 0.7,
                "positive_symbol_count": 8,
                "symbol_count": 8,
            },
            "cost40": {"sharpe": 1.3},
        },
        "validation": {
            "cost20": {
                "sharpe": val20,
                "total_return": 0.30,
                "max_drawdown": dd20,
                "positive_symbol_count": 7,
                "symbol_count": 8,
            },
            "cost40": {"sharpe": val40, "total_return": ret40, "max_drawdown": dd20 + 0.02},
        },
        "drop_one_lookback": {"passed": True},
    }


def write_artifact(path: Path, config: dict, rows: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "kind": "tsmom_factory_v1_train_only_grid",
                "train_window": {"start": "2020-01-01T00:00:00+00:00", "end": "2024-06-30T23:00:00+00:00"},
                "data": {"fingerprint": path.stem, "first_dt": "2020-01-01T00:00:00+00:00", "last_dt": "2024-06-30T23:00:00+00:00"},
                "selection_validation": {"prior_trials": 10, "effective_trials": 12},
                "summary": {
                    "accepted_train_only": any(r["advance_passed"] for r in rows),
                    "pass_count": sum(1 for r in rows if r["advance_passed"]),
                    "rows": len(rows),
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                },
                "rows": rows,
            }
        )
    )


def test_build_report_marks_cross_window_candidate_promising(tmp_path) -> None:
    config = {"market_filter_h": 336, "portfolio_vol_target_ann": 0.12, "bear_mode": "short_weak"}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_artifact(a, config, [row(config, True, 1.3, 0.9)])
    write_artifact(b, config, [row(config, True, 1.1, 0.7)])

    report = robustness_mod.build_report([a, b], target_artifact=a)

    assert report["kind"] == "tsmom_train_only_candidate_robustness_v1"
    assert report["decision"] == "promising_train_only_robustness_manual_review_required"
    assert report["robustness_passed"] is True
    assert report["target_config_found_windows"] == 2
    assert report["target_config_pass_windows"] == 2
    assert report["validation_sharpe20_min_pass_windows"] == 1.1
    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False


def test_build_report_blocks_single_window_promotion(tmp_path) -> None:
    config = {"market_filter_h": 336, "portfolio_vol_target_ann": 0.12, "bear_mode": "short_weak"}
    other = {"market_filter_h": 720, "portfolio_vol_target_ann": 0.08, "bear_mode": "short_weak"}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_artifact(a, config, [row(config, True, 1.3, 0.9)])
    write_artifact(b, config, [row(config, False, 0.2, -0.1), row(other, True, 1.4, 1.0)])

    report = robustness_mod.build_report([a, b], target_artifact=a)
    text = robustness_mod.format_text(report)

    assert report["decision"] == "weak_train_only_robustness_do_not_promote"
    assert report["robustness_passed"] is False
    assert report["target_config_found_windows"] == 2
    assert report["target_config_pass_windows"] == 1
    assert report["checks"]["target_config_passed_at_least_2_windows"] is False
    assert "paper:False live:False" in text
    assert "passed:1" in text
