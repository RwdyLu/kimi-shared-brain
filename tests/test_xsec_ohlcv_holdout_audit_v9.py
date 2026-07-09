from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_ohlcv_holdout_audit.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_ohlcv_holdout_audit", SCRIPT)
assert SPEC and SPEC.loader
audit_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_mod)


def write_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": "xsec_ohlcv_factory_v1_train_only_grid",
                "summary": {
                    "accepted_train_only": True,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                    "pass_count": 1,
                    "rows": 1,
                },
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "config": {
                    "train_start": "2017-08-01",
                    "train_end": "2024-06-30 23:59:59",
                    "embargo_start": "2024-07-01",
                },
                "rows": [
                    {
                        "advance_passed": True,
                        "config": {
                            "lookback_h": 24,
                            "skip_h": 0,
                            "rebalance_h": 24,
                            "k": 1,
                            "score_mode": "risk_adj_mom",
                            "market_filter_h": 24,
                            "vol_target_ann": 0.08,
                            "n_tranches": 1,
                        },
                    }
                ],
            }
        )
    )


def test_holdout_split_requires_explicit_authorization_before_reading_data(tmp_path, monkeypatch) -> None:
    artifact = tmp_path / "artifact.json"
    write_artifact(artifact)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("load_close_matrix should not be called without holdout authorization")

    monkeypatch.setattr(audit_mod, "load_close_matrix", fail_if_called)

    with pytest.raises(SystemExit, match="refusing to read holdout data"):
        audit_mod.build_report(
            artifact=artifact,
            cache_dir=tmp_path,
            split="holdout",
            holdout_start="2024-07-01",
            holdout_end="2026-05-31 23:59:59",
            costs_bps=(20.0, 40.0),
            bootstrap_iterations=0,
            holdout_authorized=False,
        )


def test_train_split_audit_runs_without_authorizing_holdout(tmp_path, monkeypatch) -> None:
    artifact = tmp_path / "artifact.json"
    write_artifact(artifact)
    frame = pd.DataFrame(
        {
            "dt": pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC"),
            "BTCUSDT": [100.0, 101.0, 102.0, 103.0],
            "ETHUSDT": [50.0, 50.5, 51.0, 51.5],
        }
    )

    monkeypatch.setattr(audit_mod, "load_close_matrix", lambda *args, **kwargs: frame)
    monkeypatch.setattr(
        audit_mod,
        "simulate",
        lambda closes, cfg, cost_bps, **kwargs: {
            "sharpe": 1.2 if cost_bps == 20.0 else 0.5,
            "total_return": 0.1,
            "max_drawdown": 0.1,
            "daily_turnover": 0.02,
            "top_positive_symbol_share": 0.5,
            "bootstrap_30d_sharpe_p5": 0.3,
            "symbol_pnl": {"BTCUSDT": 1.0, "ETHUSDT": 1.0},
            "yearly_positive_count": 2,
            "yearly": {},
            "equal_weight_benchmark": {"sharpe_excess": 0.2, "drawdown_ratio": 0.5},
            "legs": {"long_gross_return": 0.1, "short_gross_return": 0.0},
        },
    )

    report = audit_mod.build_report(
        artifact=artifact,
        cache_dir=tmp_path,
        split="train",
        holdout_start="2024-07-01",
        holdout_end="2026-05-31 23:59:59",
        costs_bps=(20.0, 40.0),
        bootstrap_iterations=0,
        holdout_authorized=False,
    )
    text = audit_mod.format_text(report)

    assert report["split"] == "train"
    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["decision"] == "train_split_audit_passed_holdout_still_unauthorized"
    assert "holdout:False paper:False live:False" in text
