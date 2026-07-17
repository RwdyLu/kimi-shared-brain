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
