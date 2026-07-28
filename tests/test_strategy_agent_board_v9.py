from __future__ import annotations

import json
from pathlib import Path

from scripts.v9_strategy_agent_board import build_board, format_markdown


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def write_minimal_state(root: Path, *, paper_watch: bool) -> None:
    (root / "state").mkdir()
    (root / "artifacts/v9/contract_lab").mkdir(parents=True)
    write_json(
        root / "state/v9_auto_research_state.json",
        {
            "status": "running",
            "updated_at": "2026-07-17T00:00:00+00:00",
            "cycle_index": 7,
            "tasks_done_total": 11,
            "candidates_found_total": 2,
            "distinct_candidates": 1,
            "current_task": {"name": "xsec_task"},
        },
    )
    write_json(
        root / "artifacts/v9/contract_lab/funding_delta_neutral_top20_paper_screen_latest.json",
        {
            "updated_at": "2026-07-17T00:00:00+00:00",
            "require_spot": True,
            "loaded_rows": 100,
            "spot_excluded_symbols": ["LABUSDT"],
            "data": {"first_funding_time": "2024-01-01T00:00:00+00:00"},
            "summary": {
                "paper_watch_candidate_found": paper_watch,
                "paper_watch_candidate_count": 1 if paper_watch else 0,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            },
            "top": [
                {
                    "paper_watch_candidate": paper_watch,
                    "config": {"lookback_events": 63},
                    "current_signal": {
                        "expected_capital_annualized_return": 0.1 if paper_watch else 0.0,
                        "positions": [{"symbol": "BTCUSDT"}] if paper_watch else [],
                    },
                    "advance_checks": {"current_signal_exists": paper_watch},
                }
            ],
        },
    )


def test_board_reports_research_running_without_trade_candidate(tmp_path: Path) -> None:
    write_minimal_state(tmp_path, paper_watch=False)
    (tmp_path / "state/NO_FUNDING_PAPER_WATCH.txt").write_text("NO_FUNDING")

    board = build_board(tmp_path)

    assert board["summary"]["decision"] == "research_running_no_trade_candidate"
    assert board["summary"]["paper_trading_authorized"] is False
    assert board["agents"]["data_auditor"]["status"] == "ok"
    assert board["agents"]["feasibility"]["status"] == "block"
    assert board["agents"]["validator"]["status"] == "research_running"


def test_board_reports_paper_watch_only_when_candidate_exists(tmp_path: Path) -> None:
    write_minimal_state(tmp_path, paper_watch=True)
    (tmp_path / "state/FOUND_FUNDING_PAPER_WATCH.txt").write_text("FOUND_FUNDING")

    board = build_board(tmp_path)
    markdown = format_markdown(board)

    assert board["summary"]["decision"] == "paper_watch_only_not_authorized"
    assert board["agents"]["feasibility"]["paper_watch_candidate_found"] is True
    assert board["agents"]["execution_risk"]["checks"]["trading_authorized"] is False
    assert "Strategy Agent Board" in markdown
    assert "never authorizes live trading" in markdown
