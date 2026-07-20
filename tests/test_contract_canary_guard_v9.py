from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_canary_guard.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_canary_guard", SCRIPT)
assert SPEC and SPEC.loader
guard_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard_mod)


def args_for(report_json: Path) -> Namespace:
    return Namespace(
        report_json=str(report_json),
        out_json=str(report_json.with_suffix(".guard.json")),
        out_md=str(report_json.with_suffix(".guard.md")),
        min_completed=3,
        fail_sum_r=-2.0,
        fail_profit_factor=0.8,
        fail_consecutive_losses=3,
        promote_min_completed=4,
        promote_sum_r=4.0,
        promote_profit_factor=1.2,
        promote_max_drawdown_r=3.0,
        max_active_per_pair=1,
        format="text",
    )


def write_report(path: Path, records: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "updated_at": "2026-01-01T00:00:00+00:00",
                "records": records,
            }
        )
    )


def completed_record(r_multiple: float, idx: int) -> dict:
    return {
        "status": "completed",
        "symbol": "AAAUSDT",
        "side": "short",
        "created_at": f"2026-01-01T0{idx}:00:00+00:00",
        "outcome": {
            "r_multiple": r_multiple,
            "exit_dt": f"2026-01-01T0{idx}:30:00+00:00",
        },
    }


def test_canary_guard_collects_until_min_completed(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    write_report(report, [completed_record(1.0, 1)])

    payload = guard_mod.build_payload(args_for(report))

    assert payload["status"] == "collecting"
    assert payload["stats"]["completed"] == 1
    assert "completed<3" in payload["reason_codes"]


def test_canary_guard_fails_negative_canary(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    write_report(
        report,
        [
            completed_record(-1.0, 1),
            completed_record(-1.1, 2),
            completed_record(-1.2, 3),
            {"status": "open", "symbol": "AAAUSDT", "side": "short"},
            {"status": "pending_entry", "symbol": "AAAUSDT", "side": "short"},
        ],
    )

    payload = guard_mod.build_payload(args_for(report))

    assert payload["status"] == "failed"
    assert "profit_factor<0.8" in payload["reason_codes"]
    assert "AAAUSDT:short" in payload["active_overlap_violations"]


def test_canary_guard_promotes_positive_canary(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    write_report(
        report,
        [
            completed_record(1.5, 1),
            completed_record(1.2, 2),
            completed_record(-0.5, 3),
            completed_record(2.0, 4),
        ],
    )

    payload = guard_mod.build_payload(args_for(report))

    assert payload["status"] == "promote_candidate"
    assert payload["stats"]["sum_r"] == 4.2
