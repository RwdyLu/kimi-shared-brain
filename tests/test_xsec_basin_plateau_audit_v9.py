from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_basin_plateau_audit import audit_payload  # noqa: E402


def row(
    *,
    lookback_h: int = 720,
    k: int = 2,
    market_filter_h: int = 1008,
    vol_target_ann: float = 0.06,
    drawdown_stop: float = 0.08,
    cooldown_h: int = 72,
    advance_passed: bool = False,
    validation_sharpe: float | None = None,
) -> dict:
    return {
        "advance_passed": advance_passed,
        "config": {
            "lookback_h": lookback_h,
            "k": k,
            "market_filter_h": market_filter_h,
            "vol_target_ann": vol_target_ann,
            "drawdown_stop": drawdown_stop,
            "cooldown_h": cooldown_h,
        },
        "cost20": {"sharpe": 2.0, "total_return": 1.0, "max_drawdown": 0.15},
        "validation": {
            "cost20": {
                "sharpe": validation_sharpe,
                "total_return": 0.20,
                "max_drawdown": 0.20,
                "symbol_pnl": {"BTCUSDT": 100.0, "ETHUSDT": 50.0},
            }
            if validation_sharpe is not None
            else {}
        },
        "walk_forward": {"q25_sharpe": 0.40, "bounded_loss_consistency_passed": True},
        "advance_checks": {},
    }


def write_artifact(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "artifact.json"
    path.write_text(
        json.dumps(
            {
                "selection_validation": {"validation_sharpe20_min": 1.06},
                "rows": rows,
            }
        )
    )
    return path


def test_plateau_audit_requires_adjacent_validation_neighbors(tmp_path: Path) -> None:
    artifact = write_artifact(
        tmp_path,
        [
            row(advance_passed=True, validation_sharpe=1.20),
            row(lookback_h=600, validation_sharpe=1.15),
            row(lookback_h=840, validation_sharpe=1.10),
            row(k=3, validation_sharpe=0.90),
        ],
    )

    payload = audit_payload(artifact, min_neighbors=2)

    assert payload["plateau_passed"] is True
    assert payload["centers"][0]["neighbor_validation_pass_count"] == 2
    assert payload["centers"][0]["validation_symbol_pnl"]["BTCUSDT"] == 100.0


def test_plateau_audit_rejects_isolated_passing_center(tmp_path: Path) -> None:
    artifact = write_artifact(
        tmp_path,
        [
            row(advance_passed=True, validation_sharpe=1.20),
            row(lookback_h=600, validation_sharpe=0.95),
            row(lookback_h=840, validation_sharpe=0.90),
            row(k=3, validation_sharpe=1.20),
        ],
    )

    payload = audit_payload(artifact, min_neighbors=2)

    assert payload["plateau_passed"] is False
    assert payload["centers"][0]["neighbor_validation_pass_count"] == 1
