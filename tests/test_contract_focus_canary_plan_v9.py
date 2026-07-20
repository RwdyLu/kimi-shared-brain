from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_focus_canary_plan.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_focus_canary_plan", SCRIPT)
assert SPEC and SPEC.loader
plan_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan_mod)


def args_for(actions_json: Path) -> Namespace:
    return Namespace(
        actions_json=str(actions_json),
        max_candidates=3,
        max_rejections=50,
        max_near_miss_candidates=5,
        include_near_miss_paper_probes=True,
        max_near_miss_paper_probes=1,
        min_near_miss_completed=4,
        min_near_miss_profit_factor=1.0,
        max_near_miss_gap_score=1.0,
        include_fresh_analog=False,
        signal_jsons="",
        max_fresh_analog_candidates=2,
        allow_fresh_veto=False,
        min_fresh_analog_samples=30,
        min_fresh_analog_hit_rate=0.42,
        min_fresh_analog_profitable_rate=0.42,
        min_fresh_analog_expectancy_r=0.25,
        min_probe_completed=8,
        min_probe_analog_supported=4,
        min_probe_analog_supported_rate=0.50,
        min_probe_sum_r=2.0,
        min_probe_profit_factor=1.2,
        max_probe_drawdown_r=10.0,
        max_probe_trailing_losses=5,
        active_risk_min_known=3,
        active_risk_max_sum_r=-2.0,
        active_risk_max_loss_rate=0.67,
        active_risk_max_avg_r=-0.25,
        allow_blocked=False,
        out_json=str(actions_json.with_suffix(".plan.json")),
        out_md=str(actions_json.with_suffix(".plan.md")),
        format="text",
    )


def candidate(
    symbol: str,
    side: str,
    *,
    timeframe: str = "1h",
    recent_completed: int = 12,
    recent_sum_r: float = 4.0,
    recent_profit_factor: float = 1.5,
    recent_max_drawdown_r: float = 3.0,
    recent_trailing_losses: int = 2,
    recent_analog_supported: int = 8,
    recent_analog_supported_rate: float = 0.67,
    active: int = 0,
    active_r_known: int = 0,
    active_profit: int = 0,
    active_loss: int = 0,
    active_sum_r: float = 0.0,
    active_avg_r: float = 0.0,
    active_min_r: float | None = None,
    active_max_r: float | None = None,
    edge_score: float = 1.0,
) -> dict:
    return {
        "timeframe": timeframe,
        "symbol": symbol,
        "side": side,
        "recent_completed": recent_completed,
        "recent_sum_r": recent_sum_r,
        "recent_profit_factor": recent_profit_factor,
        "recent_max_drawdown_r": recent_max_drawdown_r,
        "recent_trailing_losses": recent_trailing_losses,
        "recent_analog_supported": recent_analog_supported,
        "recent_analog_supported_rate": recent_analog_supported_rate,
        "active": active,
        "active_r_known": active_r_known,
        "active_profit": active_profit,
        "active_loss": active_loss,
        "active_sum_r": active_sum_r,
        "active_avg_r": active_avg_r,
        "active_min_r": active_min_r,
        "active_max_r": active_max_r,
        "edge_score": edge_score,
        "reason_codes": ["test"],
    }


def test_focus_plan_prefers_promote_and_excludes_blocked(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [
                    candidate("AAAUSDT", "long", edge_score=2.0),
                    candidate("BBBUSDT", "short", edge_score=3.0),
                ],
                "positive_watchlist": [candidate("CCCUSDT", "long", edge_score=5.0)],
                "blocked_pairs": [candidate("BBBUSDT", "short")],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 2
    assert [row["symbol"] for row in payload["candidates"]] == ["AAAUSDT", "CCCUSDT"]
    assert payload["candidates"][0]["source"] == "promote_candidate"
    assert payload["candidates"][0]["allowed_pair"] == "AAAUSDT:long"
    assert "CONTRACT_EDGE_CANARY_ALLOWED_PAIRS=AAAUSDT:long" in payload["candidates"][0]["launch_command"]
    assert payload["candidates"][0]["env"]["CONTRACT_EDGE_CANARY_JOURNAL_RECORD_MODE"] == "analog_supported"


def test_focus_plan_filters_weak_positive_watchlist(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [
                    candidate("AAAUSDT", "long", recent_completed=7),
                    candidate("BBBUSDT", "long", recent_sum_r=1.0),
                    candidate("CCCUSDT", "long", recent_profit_factor=1.1),
                    candidate("DDDUSDT", "long", recent_max_drawdown_r=11.0),
                    candidate("EEEUSDT", "long", recent_trailing_losses=6),
                    candidate("GGGUSDT", "long", recent_analog_supported=3),
                    candidate("HHHUSDT", "long", recent_analog_supported_rate=0.49),
                    candidate("FFFUSDT", "long", recent_sum_r=6.0, edge_score=4.0),
                ],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 1
    assert payload["summary"]["rejected_candidates"] == 7
    assert payload["summary"]["rejection_reason_counts"]["recent_completed<8"] == 1
    assert payload["summary"]["rejection_reason_counts"]["recent_analog_supported<4"] == 1
    assert payload["summary"]["rejection_reason_counts"]["recent_analog_supported_rate<0.50"] == 1
    assert payload["summary"]["near_miss_candidates"] == 5
    assert payload["summary"]["paper_probe_candidates"] == 1
    assert payload["near_miss_candidates"][0]["source"] == "positive_watchlist"
    assert payload["near_miss_candidates"][0]["near_miss_gap_score"] >= 0.0
    assert payload["paper_probe_candidates"][0]["source"] == "near_miss_probe"
    row = payload["candidates"][0]
    assert row["source"] == "positive_watchlist"
    assert row["symbol"] == "FFFUSDT"
    assert row["metrics"]["recent_analog_supported"] == 8
    assert row["metrics"]["recent_analog_supported_rate"] == 0.67
    assert row["paths"]["journal_jsonl"] == "state/contract_focus_canary_1h_fffusdt_long_journal.jsonl"


def write_signal_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "timeframe": "15m",
                "rows": [
                    {
                        "symbol": "VELVETUSDT",
                        "signal": "long",
                        "reason": "long_consensus votes=6",
                        "latest_dt": "2026-01-01T00:00:00+00:00",
                        "paper_plan": {"entry_price": 1.0},
                        "regime_filter": {"allowed": True, "reason": "regime_aligned"},
                        "analog_evidence": {
                            "supported": True,
                            "reason": "analog_support_pass",
                            "used_count": 40,
                            "hit_rate": 0.55,
                            "profitable_rate": 0.55,
                            "expectancy_r": 0.65,
                        },
                    },
                    {
                        "symbol": "WEAKUSDT",
                        "signal": "long",
                        "paper_plan": {"entry_price": 1.0},
                        "regime_filter": {"allowed": True, "reason": "regime_aligned"},
                        "analog_evidence": {
                            "supported": True,
                            "used_count": 40,
                            "hit_rate": 0.42,
                            "profitable_rate": 0.42,
                            "expectancy_r": 0.1,
                        },
                    },
                    {
                        "symbol": "SHORTUSDT",
                        "signal": "short",
                        "paper_plan": {"entry_price": 1.0},
                        "regime_filter": {"allowed": False, "reason": "short_blocked_by_market_uptrend"},
                        "analog_evidence": {
                            "supported": True,
                            "used_count": 40,
                            "hit_rate": 0.7,
                            "profitable_rate": 0.7,
                            "expectancy_r": 1.0,
                        },
                    },
                ],
            }
        )
    )


def test_focus_plan_seeds_fresh_analog_signal_when_no_mature_candidate(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    signal_json = tmp_path / "signal.json"
    actions_json.write_text(json.dumps({"promote_candidates": [], "positive_watchlist": [], "blocked_pairs": []}))
    write_signal_json(signal_json)
    args = args_for(actions_json)
    args.include_fresh_analog = True
    args.signal_jsons = str(signal_json)

    payload = plan_mod.build_plan(args)

    assert payload["summary"]["selected"] == 1
    assert payload["summary"]["fresh_analog_seen"] == 1
    assert payload["summary"]["fresh_analog_added"] == 1
    row = payload["candidates"][0]
    assert row["source"] == "fresh_analog_signal"
    assert row["timeframe"] == "15m"
    assert row["symbol"] == "VELVETUSDT"
    assert row["metrics"]["analog_expectancy_r"] == 0.65
    assert row["env"]["CONTRACT_EDGE_CANARY_JOURNAL_RECORD_MODE"] == "analog_supported"


def test_focus_plan_excludes_blocked_fresh_analog_signal(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    signal_json = tmp_path / "signal.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [],
                "blocked_pairs": [candidate("VELVETUSDT", "long", timeframe="15m")],
            }
        )
    )
    write_signal_json(signal_json)
    args = args_for(actions_json)
    args.include_fresh_analog = True
    args.signal_jsons = str(signal_json)

    payload = plan_mod.build_plan(args)

    assert payload["summary"]["fresh_analog_seen"] == 1
    assert payload["summary"]["fresh_analog_added"] == 0
    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["rejection_reason_counts"]["blocked_pair"] == 1
    assert payload["rejected_candidates"][0]["source"] == "fresh_analog_signal"
    assert payload["rejected_candidates"][0]["rejection_reasons"] == ["blocked_pair"]


def test_focus_plan_excludes_fresh_veto_signal(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    signal_json = tmp_path / "signal.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [],
                "blocked_pairs": [],
                "fresh_analog_veto_pairs": [candidate("VELVETUSDT", "long", timeframe="15m")],
            }
        )
    )
    write_signal_json(signal_json)
    args = args_for(actions_json)
    args.include_fresh_analog = True
    args.signal_jsons = str(signal_json)

    payload = plan_mod.build_plan(args)

    assert payload["summary"]["fresh_analog_seen"] == 1
    assert payload["summary"]["fresh_analog_veto_pairs"] == 1
    assert payload["summary"]["fresh_analog_added"] == 0
    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["rejection_reason_counts"]["fresh_analog_veto_pair"] == 1
    assert payload["rejected_candidates"][0]["source"] == "fresh_analog_signal"
    assert payload["rejected_candidates"][0]["rejection_reasons"] == ["fresh_analog_veto_pair"]


def test_focus_plan_treats_lossless_profit_factor_as_passing(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [
                    candidate(
                        "WINUSDT",
                        "long",
                        recent_completed=8,
                        recent_sum_r=3.0,
                        recent_profit_factor=None,
                        recent_max_drawdown_r=0.0,
                        recent_trailing_losses=0,
                        recent_analog_supported=5,
                        recent_analog_supported_rate=0.625,
                    )
                ],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 1
    assert payload["summary"]["rejected_candidates"] == 0
    row = payload["candidates"][0]
    assert row["symbol"] == "WINUSDT"
    assert row["metrics"]["recent_profit_factor"] is None


def test_focus_plan_waits_for_active_near_miss_settlement(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [
                    candidate(
                        "SOLUSDT",
                        "long",
                        recent_completed=5,
                        recent_sum_r=1.3,
                        recent_profit_factor=1.57,
                        recent_analog_supported=4,
                        recent_analog_supported_rate=0.8,
                        recent_max_drawdown_r=2.2,
                        recent_trailing_losses=0,
                        active=8,
                        active_r_known=8,
                        active_profit=5,
                        active_loss=3,
                        active_sum_r=1.2,
                        active_avg_r=0.15,
                        active_min_r=-0.4,
                        active_max_r=0.8,
                    )
                ],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["near_miss_candidates"] == 1
    assert payload["summary"]["paper_probe_candidates"] == 0
    near = payload["near_miss_candidates"][0]
    assert near["symbol"] == "SOLUSDT"
    assert near["next_action"] == "await_active_settlement"
    assert near["missing_metrics"]["missing_completed"] == 3
    assert near["missing_metrics"]["active"] == 8
    assert near["missing_metrics"]["active_r_known"] == 8
    assert near["missing_metrics"]["active_profit"] == 5
    assert near["missing_metrics"]["active_loss"] == 3
    assert near["missing_metrics"]["active_sum_r"] == 1.2
    assert near["metrics"]["active_sum_r"] == 1.2
    assert near["pro_forma_probe"]["would_pass_if_active_settled_now"] is True
    assert near["pro_forma_probe"]["projected_completed"] == 13
    assert near["pro_forma_probe"]["projected_sum_r"] == 2.5
    assert payload["paper_trading_authorized"] is False
    assert payload["live_trading_authorized"] is False


def test_focus_plan_marks_losing_active_near_miss_as_risk_wait(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [
                    candidate(
                        "RISKUSDT",
                        "long",
                        recent_completed=5,
                        recent_sum_r=1.3,
                        recent_profit_factor=1.57,
                        recent_analog_supported=4,
                        recent_analog_supported_rate=0.8,
                        recent_max_drawdown_r=2.2,
                        recent_trailing_losses=0,
                        active=4,
                        active_r_known=4,
                        active_profit=1,
                        active_loss=3,
                        active_sum_r=-1.4,
                        active_avg_r=-0.35,
                    )
                ],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["near_miss_candidates"] == 1
    assert payload["summary"]["paper_probe_candidates"] == 0
    near = payload["near_miss_candidates"][0]
    assert near["symbol"] == "RISKUSDT"
    assert near["next_action"] == "await_active_settlement_risk"
    assert near["missing_metrics"]["active_loss_rate"] == 0.75
    assert near["pro_forma_probe"]["would_pass_if_active_settled_now"] is False
    assert "projected_sum_r<2.00" in near["pro_forma_probe"]["blocking_reasons"]
    assert "active_unrealized_loss_rate>=0.67_avg_r<=-0.25" in near["pro_forma_probe"]["blocking_reasons"]


def test_focus_plan_pro_forma_does_not_project_analog_support(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [],
                "positive_watchlist": [
                    candidate(
                        "ANALOGUSDT",
                        "long",
                        recent_completed=5,
                        recent_sum_r=1.3,
                        recent_profit_factor=1.57,
                        recent_analog_supported=3,
                        recent_analog_supported_rate=0.6,
                        recent_max_drawdown_r=2.2,
                        recent_trailing_losses=0,
                        active=8,
                        active_r_known=8,
                        active_profit=8,
                        active_loss=0,
                        active_sum_r=2.0,
                        active_avg_r=0.25,
                    )
                ],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["near_miss_candidates"] == 1
    assert payload["summary"]["paper_probe_candidates"] == 0
    near = payload["near_miss_candidates"][0]
    assert near["next_action"] == "await_active_settlement"
    assert near["pro_forma_probe"]["would_pass_if_active_settled_now"] is False
    assert "recent_analog_supported<4" in near["pro_forma_probe"]["blocking_reasons"]


def test_focus_plan_rejects_promote_candidate_with_bad_active_risk(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [
                    candidate(
                        "BADACTIVEUSDT",
                        "long",
                        recent_completed=20,
                        recent_sum_r=6.0,
                        recent_profit_factor=1.4,
                        recent_max_drawdown_r=3.0,
                        recent_trailing_losses=1,
                        active=4,
                        active_r_known=4,
                        active_profit=1,
                        active_loss=3,
                        active_sum_r=-2.4,
                        active_avg_r=-0.6,
                    )
                ],
                "positive_watchlist": [],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 0
    assert payload["summary"]["rejected_candidates"] == 1
    row = payload["rejected_candidates"][0]
    assert row["source"] == "promote_candidate"
    assert "active_unrealized_sum_r<=-2.00" in row["rejection_reasons"]
    assert "active_unrealized_loss_rate>=0.67_avg_r<=-0.25" in row["rejection_reasons"]


def test_focus_plan_allows_candidate_with_healthy_active_risk(tmp_path: Path) -> None:
    actions_json = tmp_path / "actions.json"
    actions_json.write_text(
        json.dumps(
            {
                "promote_candidates": [
                    candidate(
                        "GOODACTIVEUSDT",
                        "long",
                        recent_completed=20,
                        recent_sum_r=6.0,
                        recent_profit_factor=1.4,
                        recent_max_drawdown_r=3.0,
                        recent_trailing_losses=1,
                        active=4,
                        active_r_known=4,
                        active_profit=4,
                        active_loss=0,
                        active_sum_r=2.4,
                        active_avg_r=0.6,
                    )
                ],
                "positive_watchlist": [],
                "blocked_pairs": [],
            }
        )
    )

    payload = plan_mod.build_plan(args_for(actions_json))

    assert payload["summary"]["selected"] == 1
    row = payload["candidates"][0]
    assert row["symbol"] == "GOODACTIVEUSDT"
    assert row["metrics"]["active_sum_r"] == 2.4
