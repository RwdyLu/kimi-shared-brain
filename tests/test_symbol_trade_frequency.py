import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from lunar_genome_symbol_validate_v7 import symbol_metrics_from_rows


def _row(alpha: float, net_return: float, drawdown: float, trades: int) -> dict:
    return {
        "scenario": 1,
        "cost_bps": 30,
        "per_symbol": {
            "BTCUSDT": {
                "alpha_vs_full_ghost": alpha,
                "alpha_vs_routed_ghost": alpha + 0.01,
                "return": net_return,
                "max_drawdown": drawdown,
                "trades": trades,
                "router_checks": 10,
                "router_active_count": 7,
                "route_multiplier_sum": 5,
                "policy_multiplier_sum": 8,
                "regime_counts": {"trend_up": 6, "chop": 4},
                "regime_trades": {"trend_up": trades, "chop": 0},
            }
        },
    }


def test_symbol_trade_frequency_is_per_scenario_not_aggregate():
    metrics = symbol_metrics_from_rows(
        [
            _row(0.01, 0.02, 0.05, 10),
            _row(0.02, 0.03, 0.06, 20),
            _row(0.03, 0.04, 0.07, 30),
        ]
    )

    assert metrics["trade_total"] == 60
    assert metrics["trades"] == 20
    assert metrics["avg_trades_per_scenario"] == 20
    assert metrics["min_trades_per_scenario"] == 10
    assert metrics["max_trades_per_scenario"] == 30


def test_symbol_metrics_uses_full_ghost_alpha_and_regime_distribution():
    metrics = symbol_metrics_from_rows(
        [
            _row(-0.01, 0.02, 0.05, 10),
            _row(0.02, 0.03, 0.06, 30),
        ]
    )

    assert metrics["min_alpha"] == -0.01
    assert metrics["avg_alpha"] == 0.005
    assert metrics["router_active_frac"] == 0.7
    assert metrics["avg_route_multiplier"] == 0.5
    assert metrics["avg_policy_multiplier"] == 0.8
    assert metrics["regime_trade_distribution"]["trend_up"] == 1.0
    assert metrics["regime_check_distribution"]["trend_up"] == 0.6
