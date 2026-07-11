from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import json
import pandas as pd


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


def shadow_report(
    rebalances: int = 2,
    dd: float = 0.05,
    vol: float = 0.1,
    active_rebalances: int | None = None,
    time_in_market: float = 0.2,
) -> dict[str, Any]:
    active = rebalances if active_rebalances is None else active_rebalances
    return {
        "costs": {
            "40bps": {
                "sharpe": 0.2,
                "total_return": 0.01,
                "max_drawdown": dd,
                "realized_daily_vol_ann": vol,
                "rebalance_event_count": rebalances,
                "active_rebalance_event_count": active,
                "time_in_market_frac": time_in_market,
                "equal_weight_benchmark": {"sharpe": -0.1, "sharpe_excess": 0.3},
            }
        }
    }


def crash_matrix(periods: int = 96) -> pd.DataFrame:
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    aaa = []
    bbb = []
    for idx in range(periods):
        if idx < 36:
            aaa.append(100 + idx * 1.5)
            bbb.append(100 + idx)
        elif idx < 48:
            aaa.append(154 - (idx - 35) * 5.0)
            bbb.append(135 - (idx - 35) * 4.0)
        else:
            aaa.append(94 + (idx - 48) * 0.1)
            bbb.append(87 + (idx - 48) * 0.1)
    return pd.DataFrame(
        {
            "dt": dt,
            "AAA": aaa,
            "BBB": bbb,
            "CCC": [100 - idx * 0.1 for idx in range(periods)],
            "DDD": [100] * periods,
        }
    )


def stopped_config() -> dict[str, Any]:
    return {
        "lookback_h": 8,
        "skip_h": 0,
        "rebalance_h": 4,
        "k": 2,
        "score_mode": "mom",
        "market_filter_h": 0,
        "vol_target_ann": 0.0,
        "drawdown_stop": 0.05,
        "cooldown_h": 1000,
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


def test_build_gate_report_blocks_when_holdout_batch_has_no_paper_candidate(tmp_path) -> None:
    holdout_batch = tmp_path / "holdout_batch.json"
    holdout_batch.write_text(
        json.dumps(
            {
                "holdout_results": [
                    {"promotion_decision": "holdout_promising_recently_inactive_manual_review_required"}
                ],
                "summary": {
                    "status_counts": {
                        "holdout_promising_recently_inactive_manual_review_required": 1
                    }
                },
            }
        )
    )

    report = gate_mod.build_gate_report(
        holdout_batch_path=holdout_batch,
        cache_dir=tmp_path,
        warmup_start="2024-07-01",
        evaluation_start="2026-06-01",
        evaluation_end="2026-07-11 00:00:00",
        costs_bps=(40.0,),
        min_decay_ratio=0.5,
        min_benchmark_excess=0.5,
        max_holdout_dd=0.25,
        max_post_oos_dd=0.15,
        min_post_oos_rebalances=1,
        max_realized_vol_multiple=3.0,
    )

    assert report["decision"] == "paper_blocked_no_candidate"
    assert report["paper_trading_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["checks"] == {"holdout_batch_has_paper_candidate": False}
    assert report["data"]["source_holdout_status_counts"] == {
        "holdout_promising_recently_inactive_manual_review_required": 1
    }


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


def test_paper_decision_blocks_scheduled_only_rebalances() -> None:
    decision, checks = gate_mod.paper_decision(
        candidate=candidate(),
        holdout_report=holdout_report(),
        shadow_report=shadow_report(rebalances=3, active_rebalances=0, time_in_market=0.0),
        min_decay_ratio=0.5,
        min_benchmark_excess=0.5,
        max_holdout_dd=0.25,
        max_post_oos_dd=0.15,
        min_post_oos_rebalances=1,
        max_realized_vol_multiple=3.0,
    )

    assert decision == "paper_manual_review_required"
    assert checks["post_oos_has_min_rebalances"] is True
    assert checks["post_oos_has_min_active_rebalances"] is False
    assert checks["post_oos_time_in_market_positive"] is False


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


def test_shadow_oos_report_applies_drawdown_stop_and_cooldown() -> None:
    report = gate_mod.shadow_oos_report(
        closes=crash_matrix(),
        config=stopped_config(),
        evaluation_start=pd.Timestamp("2020-01-01", tz="UTC"),
        costs_bps=(20.0, 40.0),
    )

    cost40 = report["costs"]["40bps"]
    assert report["reference_cost_bps"] == 40.0
    assert report["latest_gross_exposure"] == 0.0
    assert all(weight == 0.0 for weight in report["latest_weights"].values())
    assert cost40["risk_off_event_count"] >= 1
    assert cost40["risk_off_hours"] >= 12
    assert cost40["risk_stop_exit_turnover"] > 0.0
    assert "active_rebalance_event_count" in cost40
    assert "time_in_market_frac" in cost40


def test_write_marker_never_authorizes_live(tmp_path) -> None:
    report = {
        "paper_trading_authorized": True,
        "decision": "paper_ready",
        "candidate": {"artifact": "candidate.json"},
    }

    gate_mod.write_marker(report, tmp_path)

    text = (tmp_path / "FOUND_PAPER_READY.txt").read_text()
    assert "live_trading_authorized=False" in text
