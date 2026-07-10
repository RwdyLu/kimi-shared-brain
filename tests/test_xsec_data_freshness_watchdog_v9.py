from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_data_freshness_watchdog.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_data_freshness_watchdog", SCRIPT)
assert SPEC and SPEC.loader
watchdog_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog_mod)


def test_evaluate_freshness_passes_fresh_complete_cache() -> None:
    status = watchdog_mod.evaluate_freshness(
        latest={"BTCUSDT": 1783641600000, "ETHUSDT": 1783641600000},
        previous_status={},
        ledger_records=[],
        now="2026-07-10T01:30:00+00:00",
        max_cache_age_hours=3.0,
        min_symbol_coverage=0.9,
        max_unchanged_runs=4,
    )

    assert status["data_fresh"] is True
    assert status["coverage_fraction"] == 1.0
    assert status["checks"]["cache_age_le_max"] is True


def test_evaluate_freshness_blocks_stale_or_partial_cache() -> None:
    status = watchdog_mod.evaluate_freshness(
        latest={"BTCUSDT": 1783641600000, "ETHUSDT": 1783630800000},
        previous_status={},
        ledger_records=[],
        now="2026-07-10T09:30:00+00:00",
        max_cache_age_hours=3.0,
        min_symbol_coverage=0.9,
        max_unchanged_runs=4,
    )

    assert status["data_fresh"] is False
    assert status["checks"]["cache_age_le_max"] is False
    assert status["checks"]["symbol_coverage_ge_min"] is False


def test_evaluate_freshness_blocks_after_repeated_unchanged_runs() -> None:
    status = watchdog_mod.evaluate_freshness(
        latest={"BTCUSDT": 1783641600000, "ETHUSDT": 1783641600000},
        previous_status={"max_latest_ms": 1783641600000, "unchanged_run_count": 3},
        ledger_records=[],
        now="2026-07-10T01:30:00+00:00",
        max_cache_age_hours=3.0,
        min_symbol_coverage=0.9,
        max_unchanged_runs=4,
    )

    assert status["unchanged_run_count"] == 4
    assert status["checks"]["cache_advancing_or_below_limit"] is False
    assert status["data_fresh"] is False


def test_duplicate_latest_dt_count_ignores_skip_records() -> None:
    records = [
        {"kind": "xsec_paper_ledger_record_v1", "latest_dt": "2026-07-10T00:00:00Z"},
        {"kind": "xsec_paper_ledger_skip_v1", "latest_dt": "2026-07-10T00:00:00Z"},
        {"kind": "xsec_paper_ledger_record_v1", "latest_dt": "2026-07-10T00:00:00Z"},
    ]

    assert watchdog_mod.count_duplicate_latest_dt_records(records) == 1
