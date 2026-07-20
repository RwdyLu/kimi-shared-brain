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
        min_probe_completed=8,
        min_probe_analog_supported=4,
        min_probe_analog_supported_rate=0.50,
        min_probe_sum_r=2.0,
        min_probe_profit_factor=1.2,
        max_probe_drawdown_r=10.0,
        max_probe_trailing_losses=5,
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
        "active": 0,
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
    row = payload["candidates"][0]
    assert row["source"] == "positive_watchlist"
    assert row["symbol"] == "FFFUSDT"
    assert row["metrics"]["recent_analog_supported"] == 8
    assert row["metrics"]["recent_analog_supported_rate"] == 0.67
    assert row["paths"]["journal_jsonl"] == "state/contract_focus_canary_1h_fffusdt_long_journal.jsonl"
