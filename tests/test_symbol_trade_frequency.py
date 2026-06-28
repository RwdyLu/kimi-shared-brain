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
                "alpha_vs_ghost": alpha,
                "return": net_return,
                "max_drawdown": drawdown,
                "trades": trades,
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
