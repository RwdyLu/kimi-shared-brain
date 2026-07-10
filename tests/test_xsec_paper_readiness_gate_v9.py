from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_paper_readiness_gate.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_paper_readiness_gate", SCRIPT)
assert SPEC and SPEC.loader
gate_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate_mod)


def candidate(decay: float = 0.67) -> dict[str, Any]:
    return {
        "artifact": "candidate.json",
        "candidate_config": {"vol_target_ann": 0.08},
        "promotion_decision": "paper_candidate_manual_review_required",
        "promotion_evidence": {
            "holdout_sharpe_decay_ratio": decay,
            "holdout_sharpe": 1.4,
            "holdout_return": 0.5,
            "holdout_drawdown": 0.12,
        },
    }


def holdout_report(excess: float = 1.2, dd: float = 0.12) -> dict[str, Any]:
    return {
        "costs": {
            "40bps": {
                "sharpe": 1.4,
                "total_return": 0.5,
                "max_drawdown": dd,
                "benchmark_sharpe_excess": excess,
            }
        }
    }


def shadow_report(rebalances: int = 2, dd: float = 0.05, vol: float = 0.1) -> dict[str, Any]:
    return {
        "costs": {
            "40bps": {
                "sharpe": 0.2,
                "total_return": 0.01,
                "max_drawdown": dd,
                "realized_daily_vol_ann": vol,
                "rebalance_event_count": rebalances,
                "equal_weight_benchmark": {"sharpe": -0.1, "sharpe_excess": 0.3},
            }
        }
    }


def test_paper_candidate_from_batch_selects_best_decay() -> None:
    batch = {
        "holdout_results": [
            candidate(decay=0.51),
            {**candidate(decay=0.72), "artifact": "better.json"},
            {"promotion_decision": "holdout_failed_do_not_paper_trade"},
        ]
    }

    selected = gate_mod.paper_candidate_from_batch(batch)

    assert selected["artifact"] == "better.json"


def test_paper_decision_authorizes_only_paper_not_live() -> None:
    decision, checks = gate_mod.paper_decision(
        candidate=candidate(),
        holdout_report=holdout_report(),
        shadow_report=shadow_report(),
        min_decay_ratio=0.5,
        min_benchmark_excess=0.5,
        max_holdout_dd=0.25,
        max_post_oos_dd=0.15,
        min_post_oos_rebalances=1,
        max_realized_vol_multiple=3.0,
    )

    assert decision == "paper_ready"
    assert all(checks.values())


def test_paper_decision_treats_zero_drawdown_as_passing() -> None:
    report = shadow_report(dd=0.0)

    decision, checks = gate_mod.paper_decision(
        candidate=candidate(),
        holdout_report=holdout_report(),
        shadow_report=report,
        min_decay_ratio=0.5,
        min_benchmark_excess=0.5,
        max_holdout_dd=0.25,
        max_post_oos_dd=0.15,
        min_post_oos_rebalances=1,
        max_realized_vol_multiple=3.0,
    )

    assert decision == "paper_ready"
    assert checks["post_oos_drawdown_le_max"] is True


def test_paper_decision_blocks_weak_benchmark_excess() -> None:
    decision, checks = gate_mod.paper_decision(
        candidate=candidate(),
        holdout_report=holdout_report(excess=0.1),
        shadow_report=shadow_report(),
        min_decay_ratio=0.5,
        min_benchmark_excess=0.5,
        max_holdout_dd=0.25,
        max_post_oos_dd=0.15,
        min_post_oos_rebalances=1,
        max_realized_vol_multiple=3.0,
    )

    assert decision == "paper_manual_review_required"
    assert checks["holdout_40bps_benchmark_excess_ge_min"] is False


def test_paper_decision_blocks_post_oos_crash() -> None:
    decision, checks = gate_mod.paper_decision(
        candidate=candidate(),
        holdout_report=holdout_report(),
        shadow_report=shadow_report(dd=0.22),
        min_decay_ratio=0.5,
        min_benchmark_excess=0.5,
        max_holdout_dd=0.25,
        max_post_oos_dd=0.15,
        min_post_oos_rebalances=1,
        max_realized_vol_multiple=3.0,
    )

    assert decision == "paper_manual_review_required"
    assert checks["post_oos_drawdown_le_max"] is False


def test_write_marker_never_authorizes_live(tmp_path) -> None:
    report = {
        "paper_trading_authorized": True,
        "decision": "paper_ready",
        "candidate": {"artifact": "candidate.json"},
    }

    gate_mod.write_marker(report, tmp_path)

    text = (tmp_path / "FOUND_PAPER_READY.txt").read_text()
    assert "live_trading_authorized=False" in text
