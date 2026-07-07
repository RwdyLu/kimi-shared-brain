from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_candidate_review.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_candidate_review", SCRIPT)
assert SPEC and SPEC.loader
review_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_mod)


def test_build_review_summarizes_train_only_candidate(tmp_path) -> None:
    artifact = tmp_path / "candidate.json"
    artifact.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "data": {"fingerprint": "data-fp"},
                "selection_validation": {"prior_trials": 10, "effective_trials": 12},
                "summary": {
                    "accepted_train_only": True,
                    "pass_count": 1,
                    "rows": 2,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                },
                "rows": [
                    {
                        "advance_passed": True,
                        "config": {"lookback_h": 504, "rebalance_h": 168},
                        "selection": {
                            "cost20": {
                                "sharpe": 2.1,
                                "total_return": 1.2,
                                "max_drawdown": 0.1,
                                "bootstrap_30d_sharpe_p5": 1.0,
                                "bootstrap_30d_sharpe_p5_confirm": 0.9,
                                "top_positive_symbol_share": 0.2,
                                "equal_weight_benchmark": {"sharpe_excess": 0.3, "drawdown_ratio": 0.5},
                            },
                            "cost40": {"sharpe": 2.0},
                        },
                        "validation": {
                            "cost20": {"sharpe": 1.1, "total_return": 0.2, "max_drawdown": 0.15},
                            "cost40": {"sharpe": 0.9},
                        },
                        "advance_checks": {"ok": True},
                    },
                    {"advance_passed": False},
                ],
            }
        )
    )

    review = review_mod.build_review(artifact)

    assert review["decision"] == "train_only_manual_review_required"
    assert review["pass_count"] == 1
    assert review["rows"] == 2
    assert review["holdout_authorized"] is False
    assert review["paper_trading_authorized"] is False
    assert review["live_trading_authorized"] is False
    assert review["top_pass"]["selection"]["sharpe20"] == 2.1
    assert review["top_pass"]["validation"]["sharpe20"] == 1.1


def test_format_text_keeps_train_only_safety_visible(tmp_path) -> None:
    text = review_mod.format_text(
        {
            "decision": "train_only_manual_review_required",
            "pass_count": 1,
            "rows": 2,
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "data": {"fingerprint": "fp"},
            "selection_validation": {"prior_trials": 10, "effective_trials": 12},
            "top_pass": {
                "config": {"lookback_h": 504},
                "selection": {
                    "sharpe20": 2.1,
                    "max_drawdown20": 0.1,
                    "bootstrap_30d_sharpe_p5": 1.0,
                    "bootstrap_30d_sharpe_p5_confirm": 0.9,
                },
                "validation": {"sharpe20": 1.1, "max_drawdown20": 0.15, "total_return20": 0.2},
            },
        }
    )
    assert "decision=train_only_manual_review_required" in text
    assert "holdout:False paper:False live:False" in text
    assert "validation=sharpe20:1.100" in text
