from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_tsmom_holdout_audit.py"
SPEC = importlib.util.spec_from_file_location("v9_tsmom_holdout_audit", SCRIPT)
assert SPEC and SPEC.loader
holdout_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(holdout_mod)


def test_decision_from_costs_blocks_negative_holdout() -> None:
    decision, checks = holdout_mod.decision_from_costs(
        {
            "20bps": {"sharpe": -0.1, "total_return": -0.08, "max_drawdown": 0.28},
            "40bps": {"sharpe": -0.6, "total_return": -0.25, "max_drawdown": 0.37},
        }
    )

    assert decision == "holdout_failed_do_not_paper_trade"
    assert checks["holdout_20bps_sharpe_ge_0_7"] is False
    assert checks["holdout_20bps_return_gt_0"] is False
    assert checks["holdout_40bps_return_gt_0"] is False


def test_decision_from_costs_allows_only_manual_review_when_holdout_passes() -> None:
    decision, checks = holdout_mod.decision_from_costs(
        {
            "20bps": {"sharpe": 0.9, "total_return": 0.12, "max_drawdown": 0.18},
            "40bps": {"sharpe": 0.2, "total_return": 0.03, "max_drawdown": 0.20},
        }
    )

    assert decision == "holdout_promising_manual_review_required"
    assert all(checks.values())


def test_format_text_keeps_safety_flags_visible() -> None:
    report = {
        "decision": "holdout_failed_do_not_paper_trade",
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "source_artifact": "candidate.json",
        "target_config": {"market_filter_h": 336},
        "target_lookbacks_h": [336, 720, 1440, 2160],
        "holdout_data": {
            "rows": 100,
            "first_dt": "2024-07-01T00:00:00+00:00",
            "last_dt": "2024-08-01T00:00:00+00:00",
            "symbols": ["BTCUSDT", "ETHUSDT"],
        },
        "costs": {
            "20bps": {
                "sharpe": -0.1,
                "total_return": -0.08,
                "max_drawdown": 0.28,
                "daily_turnover": 0.1,
                "positive_symbol_count": 1,
                "symbol_count": 2,
                "bootstrap_30d_sharpe_p5": -1.0,
            }
        },
        "checks": {"holdout_20bps_return_gt_0": False},
        "note": "Read-only holdout audit. It does not authorize paper trading or live trading.",
    }

    text = holdout_mod.format_text(report)

    assert "decision=holdout_failed_do_not_paper_trade" in text
    assert "holdout:False paper:False live:False" in text
    assert "20bps=sharpe:-0.100" in text
