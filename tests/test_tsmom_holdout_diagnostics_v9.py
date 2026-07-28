from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_tsmom_holdout_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("v9_tsmom_holdout_diagnostics", SCRIPT)
assert SPEC and SPEC.loader
diag_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag_mod)


def test_period_summary_reports_long_short_and_cost() -> None:
    dt = pd.date_range("2024-07-01", periods=48, freq="1h", tz="UTC")
    frame = pd.DataFrame(
        {
            "dt": dt,
            "net_return": [-0.001] * 48,
            "long_gross_return": [0.0002] * 48,
            "short_gross_return": [-0.0008] * 48,
            "cost": [0.0004] * 48,
            "gross_exposure": [0.5] * 48,
            "long_exposure": [0.2] * 48,
            "short_exposure": [0.3] * 48,
            "turnover": [0.1] * 48,
        }
    ).set_index("dt")

    summary = diag_mod.period_summary(frame)

    assert summary["total_return"] < 0.0
    assert summary["long_gross_return"] > 0.0
    assert summary["short_gross_return"] < 0.0
    assert summary["cost_return"] > 0.0
    assert summary["avg_short_exposure"] == 0.3


def test_format_text_keeps_safety_and_diagnosis_visible() -> None:
    report = {
        "source_artifact": "candidate.json",
        "target_config": {"market_filter_h": 336},
        "target_lookbacks_h": [336, 720, 1440, 2160],
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "overall": {
            "total_return": -0.1,
            "sharpe": -0.2,
            "max_drawdown": 0.3,
            "long_gross_return": 0.1,
            "short_gross_return": -0.15,
            "cost_return": 0.05,
            "avg_gross_exposure": 0.4,
        },
        "diagnosis": ["short_leg_lost_money", "costs_material_vs_total_loss"],
        "worst_months": [
            {
                "month": "2024-08",
                "total_return": -0.05,
                "sharpe": -1.0,
                "max_drawdown": 0.1,
                "long_gross_return": 0.01,
                "short_gross_return": -0.04,
                "cost_return": 0.02,
            }
        ],
        "worst_symbols": [
            {
                "symbol": "BTCUSDT",
                "contribution_sum": -0.05,
                "avg_abs_weight": 0.1,
                "long_hours": 10,
                "short_hours": 20,
            }
        ],
        "by_mode": [
            {
                "mode": "short_weak",
                "total_return": -0.08,
                "long_gross_return": 0.0,
                "short_gross_return": -0.05,
                "cost_return": 0.03,
                "avg_gross_exposure": 0.3,
            }
        ],
        "note": "Read-only holdout diagnostics. It does not authorize paper trading or live trading.",
    }

    text = diag_mod.format_text(report)

    assert "holdout:False paper:False live:False" in text
    assert "diagnosis=short_leg_lost_money,costs_material_vs_total_loss" in text
    assert "BTCUSDT" in text
    assert "short_weak" in text
