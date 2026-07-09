from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_train_cv_evidence.py"
SPEC = importlib.util.spec_from_file_location("v9_train_cv_evidence", SCRIPT)
assert SPEC and SPEC.loader
evidence_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence_mod)


def write_artifact(path: Path, *, kind: str, symbols: list[str], config: dict, row_config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kind": kind,
                "summary": {
                    "accepted_train_only": True,
                    "holdout_authorized": False,
                    "paper_trading_authorized": False,
                    "live_trading_authorized": False,
                    "pass_count": 1,
                    "rows": 1,
                },
                "symbols": symbols,
                "config": {
                    "train_start": "2017-08-01",
                    "train_end": "2024-06-30 23:59:59",
                    "embargo_start": "2024-07-01",
                    "symbols": symbols,
                    **config,
                },
                "data": {
                    "fingerprint": "abc123",
                    "first_dt": "2020-01-01T00:00:00+00:00",
                    "last_dt": "2024-06-30T23:00:00+00:00",
                    "rows": 100,
                    "symbols": symbols,
                },
                "selection_validation": {
                    "effective_trials": 100,
                    "prior_trials": 90,
                    "n_configs_tested": 1,
                    "selection_bootstrap_p5_min": 0.25,
                    "validation_sharpe20_min": 0.7,
                    "note": "All selection and validation data remains before embargo_start.",
                },
                "rows": [
                    {
                        "advance_passed": True,
                        "config": row_config,
                        "advance_checks": {"ok": True},
                        "selection": {
                            "cost20": {
                                "sharpe": 1.4,
                                "total_return": 0.3,
                                "max_drawdown": 0.1,
                                "bootstrap_30d_sharpe_p5": 0.8,
                            },
                            "cost40": {"sharpe": 1.1, "total_return": 0.2, "max_drawdown": 0.12},
                            "checks": {"selection_ok": True},
                        },
                        "validation": {
                            "cost20": {"sharpe": 1.0, "total_return": 0.15, "max_drawdown": 0.11},
                            "cost40": {"sharpe": 0.8, "total_return": 0.1, "max_drawdown": 0.13},
                            "checks": {"validation_ok": True},
                        },
                    }
                ],
            }
        )
    )


def test_build_evidence_is_train_only_and_dedupes_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "artifacts/v9/contract_lab/tsmom.json"
    write_artifact(
        artifact,
        kind="tsmom_factory_v1_train_only_grid",
        symbols=["BTCUSDT", "ETHUSDT"],
        config={"lookbacks_h": [720, 1440]},
        row_config={"asset_vol_target_ann": 0.25, "portfolio_vol_target_ann": 0.06},
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "candidates_found": [
                    {
                        "task": "tsmom_cont_full_202406_tsmom_core_slow_cost_guard_abc123",
                        "status": "manual_review_required",
                        "output_json": str(artifact),
                    },
                    {
                        "task": "duplicate",
                        "status": "manual_review_required_data_drift",
                        "output_json": str(artifact),
                    },
                ]
            }
        )
    )

    report = evidence_mod.build_evidence(state, base=tmp_path)

    assert report["holdout_accessed"] is False
    assert report["holdout_authorized"] is False
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["summary"]["state_candidates"] == 2
    assert report["summary"]["distinct_candidates"] == 1
    assert report["summary"]["reported_candidates"] == 1
    candidate = report["candidates"][0]
    assert candidate["failed_checks"] == []
    assert candidate["pre_registered_holdout"]["status"] == "available_but_not_authorized"
    assert candidate["pre_registered_holdout"]["do_not_run_until"] == "holdout_authorized=true"


def test_xsec_evidence_requires_generic_holdout_entrypoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    artifact = tmp_path / "artifacts/v9/contract_lab/xsec.json"
    write_artifact(
        artifact,
        kind="xsec_ohlcv_factory_v1_train_only_grid",
        symbols=["BTCUSDT", "ETHUSDT"],
        config={"lookbacks_h": [336]},
        row_config={"lookback_h": 336, "rebalance_h": 168, "k": 2},
    )
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "candidates_found": [
                    {
                        "task": "xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123",
                        "status": "manual_review_required",
                        "output_json": str(artifact),
                    }
                ]
            }
        )
    )

    report = evidence_mod.build_evidence(state, base=tmp_path)
    markdown = evidence_mod.format_markdown(report)

    assert report["candidates"][0]["pre_registered_holdout"]["status"] == "missing_generic_xsec_holdout_entrypoint"
    assert "holdout_authorized=False" in markdown
    assert "holdout_accessed: `False`" in markdown
