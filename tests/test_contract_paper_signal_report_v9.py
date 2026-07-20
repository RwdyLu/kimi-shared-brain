from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_paper_signal_report.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_paper_signal_report", SCRIPT)
assert SPEC and SPEC.loader
report_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report_mod)


def test_paper_report_calculates_open_short_r_multiple(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "open_time": [
                int(pd.Timestamp("2026-01-01T00:00:00Z").timestamp() * 1000),
                int(pd.Timestamp("2026-01-01T01:00:00Z").timestamp() * 1000),
            ],
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 98.0],
            "close": [100.0, 98.0],
            "volume": [10.0, 11.0],
        }
    ).to_parquet(tmp_path / "AAAUSDT_1h_2026-01.parquet", index=False)
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": "open",
                "symbol": "AAAUSDT",
                "side": "short",
                "entry_price": 100.0,
                "stop_loss": 102.0,
                "take_profit": 96.0,
                "analog_supported": True,
            }
        )
        + "\n"
    )
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
    )

    payload = report_mod.build_report(args)

    row = payload["open"][0]
    assert row["symbol"] == "AAAUSDT"
    assert row["current_r_multiple"] == 1.0
    assert row["current_directional_pct"] == 0.020000000000000018
    assert report_mod.outcome_label(row) == "open_profit"


def test_paper_report_builds_strategy_scoreboard(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    rows = []
    for idx in range(20):
        rows.append(
            {
                "created_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-01T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "AAAUSDT",
                "side": "long",
                "outcome": {"r_multiple": 0.3, "exit_dt": f"2026-01-01T{idx:02d}:30:00+00:00"},
            }
        )
        rows.append(
            {
                "created_at": f"2026-01-02T{idx:02d}:00:00+00:00",
                "updated_at": f"2026-01-02T{idx:02d}:00:00+00:00",
                "status": "completed",
                "symbol": "BBBUSDT",
                "side": "short",
                "outcome": {"r_multiple": -0.3, "exit_dt": f"2026-01-02T{idx:02d}:30:00+00:00"},
            }
        )
    journal.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    args = Namespace(
        cache_dir=str(tmp_path),
        sources=f"1h:{journal}",
        lookback_bars=20,
        max_rows=20,
        scoreboard_max_rows=20,
        scoreboard_min_trades=20,
        scoreboard_recent_trades=20,
        scoreboard_fail_sum_r=-5.0,
        scoreboard_fail_profit_factor=0.8,
        scoreboard_fail_consecutive_losses=6,
        scoreboard_promote_sum_r=5.0,
        scoreboard_promote_profit_factor=1.2,
        scoreboard_promote_max_drawdown_r=5.0,
    )

    payload = report_mod.build_report(args)

    assert payload["summary"]["scoreboard_groups"] == 2
    assert payload["summary"]["promote_candidates"] == 1
    assert payload["summary"]["stop_candidates"] == 1
    assert payload["scoreboard"][0]["symbol"] == "AAAUSDT"
    assert payload["scoreboard"][0]["status"] == "promote_candidate"
    assert payload["scoreboard"][0]["recent_sum_r"] == 5.999999999999998
    stop = next(row for row in payload["scoreboard"] if row["symbol"] == "BBBUSDT")
    assert stop["status"] == "stop_candidate"
    assert "recent_sum_r<=-5" in stop["reason_codes"]
