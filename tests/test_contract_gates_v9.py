from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.metrics import GateConfig, evaluate_gates


def base_payload(**overrides):
    payload = {
        "initial_equity": 10_000.0,
        "net_pnl": 1_000.0,
        "trade_count": 120,
        "cvar5_r": -0.5,
        "avg_r": 0.2,
        "max_drawdown": 0.10,
        "profit_factor": 1.4,
        "residual_positions": 0,
        "by_entry_regime": {"up_normal": {"net_pnl": 1_000.0, "trades": 120}},
        "folds": [
            {"fold": 0, "net_pnl": 200.0},
            {"fold": 1, "net_pnl": 300.0},
            {"fold": 2, "net_pnl": 500.0},
        ],
    }
    payload.update(overrides)
    return payload


def test_contract_gate_pass_matrix() -> None:
    result = evaluate_gates(base_payload(), base_payload(net_pnl=500.0), GateConfig())
    assert result["passed"] is True
    assert result["failures"] == []


def test_contract_gate_fails_closed_on_tail_and_residual() -> None:
    base = base_payload(cvar5_r=-2.0, residual_positions=1, by_entry_regime={"deep_drawdown": {"net_pnl": -500.0}})
    result = evaluate_gates(base, base_payload(net_pnl=-1.0), GateConfig())
    assert result["passed"] is False
    assert "cvar5_r_ok" in result["failures"]
    assert "residual_flat" in result["failures"]
    assert "cost2_net_pnl_positive" in result["failures"]
    assert "deep_drawdown_loss_ok" in result["failures"]
