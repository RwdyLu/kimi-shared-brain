from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_only_plateau_axis_report.py"
SPEC = importlib.util.spec_from_file_location("v9_train_only_plateau_axis_report", SCRIPT)
assert SPEC and SPEC.loader
axis_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(axis_mod)


def test_build_axis_report_reconciles_neighbor_counts(tmp_path) -> None:
    center = {
        "lookback_h": 504,
        "rebalance_h": 168,
        "market_filter_h": 1008,
        "vol_target_ann": 0.06,
        "k": 3,
        "skip_h": 0,
        "score_mode": "risk_adj_mom",
    }

    def row(config, sharpe):
        return {"config": config, "validation": {"cost20": {"sharpe": sharpe}}}

    rows = [row(center, 1.2)]
    rows.extend(
        [
            row({**center, "lookback_h": 336}, 1.1),
            row({**center, "lookback_h": 672}, 0.8),
            row({**center, "rebalance_h": 120}, 1.3),
            row({**center, "rebalance_h": 240}, 0.7),
        ]
    )
    artifact = tmp_path / "plateau.json"
    artifact.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "data": {"fingerprint": "fp"},
                "selection_validation": {
                    "plateau_stability": {
                        "passed": False,
                        "center_config": center,
                        "neighbor_pass_count": 2,
                        "neighbor_total": 4,
                        "neighbor_pass_fraction": 0.5,
                        "validation_sharpe20_min": 1.0,
                        "center_validation_sharpe20": 1.2,
                        "best_neighbor_validation_sharpe20": 1.3,
                        "center_not_spike": True,
                    }
                },
                "summary": {
                    "accepted_train_only": False,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                },
                "rows": rows,
            }
        )
    )

    report = axis_mod.build_axis_report(artifact)

    assert report["overall_neighbors"]["pass_count"] == 2
    assert report["overall_neighbors"]["total"] == 4
    assert report["reconciled_with_plateau"] is True
    assert report["summary"]["holdout_authorized"] is False
    lookback = next(axis for axis in report["axes"] if axis["axis"] == "lookback_h")
    assert lookback["changed"]["pass_count"] == 1
    assert lookback["changed"]["total"] == 2


def test_format_text_keeps_safety_and_axis_rates_visible(tmp_path) -> None:
    text = axis_mod.format_text(
        {
            "decision": "train_only_plateau_axis_report",
            "summary": {"holdout_authorized": False, "paper_trading_authorized": False, "live_trading_authorized": False},
            "overall_neighbors": {"pass_count": 46, "total": 80, "pass_fraction": 0.575},
            "threshold": 1.0,
            "reconciled_with_plateau": True,
            "plateau": {
                "passed": False,
                "center_validation_sharpe20": 1.324,
                "best_neighbor_validation_sharpe20": 2.333,
                "center_not_spike": True,
            },
            "axes": [
                {
                    "axis": "rebalance_h",
                    "center_value": 168,
                    "changed": {
                        "pass_count": 20,
                        "total": 54,
                        "pass_fraction": 0.37037,
                        "mean_sharpe20": 0.8,
                        "min_sharpe20": -0.1,
                        "max_sharpe20": 1.5,
                    },
                }
            ],
        }
    )

    assert "holdout:False paper:False live:False" in text
    assert "overall=neighbors:46/80" in text
    assert "reconciled:True" in text
    assert "axis=rebalance_h" in text
