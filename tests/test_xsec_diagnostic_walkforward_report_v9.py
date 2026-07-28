from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_xsec_diagnostic_walkforward_report import format_text, load_rows, summarize  # noqa: E402


def row(
    *,
    selection_sharpe: float,
    validation_sharpe: float,
    diagnostic_q25: float | None = None,
    diagnostic_sign: float = 0.0,
    failed_checks: tuple[str, ...] = (),
) -> dict:
    checks = {
        "positive_3_of_4_years": "positive_3_of_4_years" not in failed_checks,
        "validation_sharpe20_ge_adjusted_min": "validation_sharpe20_ge_adjusted_min" not in failed_checks,
    }
    diagnostic = {
        "enabled": True,
        "diagnostic_only": True,
        "triggered": diagnostic_q25 is not None,
    }
    if diagnostic_q25 is not None:
        diagnostic.update({"q25_sharpe": diagnostic_q25, "sign_consistency": diagnostic_sign})
    return {
        "config": {"lookback_h": 336},
        "advance_passed": False,
        "advance_checks": checks,
        "cost20": {"sharpe": selection_sharpe},
        "validation": {"cost20": {"sharpe": validation_sharpe}},
        "walk_forward": {"enabled": True, "passed": False, "folds": []},
        "diagnostic_walk_forward": diagnostic,
    }


def test_report_reads_progress_and_summarizes_diagnostics(tmp_path) -> None:
    base = tmp_path / "xsec_ohlcv_cont_full_202406_hq_dd_plateau_abc123"
    progress = base.with_suffix(".progress.jsonl")
    meta = base.with_suffix(".progress.meta.json")
    rows = [
        row(selection_sharpe=2.1, validation_sharpe=2.3, diagnostic_q25=0.025, diagnostic_sign=0.667, failed_checks=("positive_3_of_4_years",)),
        row(selection_sharpe=2.2, validation_sharpe=2.2, diagnostic_q25=0.207, diagnostic_sign=0.833, failed_checks=("positive_3_of_4_years",)),
        row(selection_sharpe=1.6, validation_sharpe=0.7, failed_checks=("positive_3_of_4_years", "validation_sharpe20_ge_adjusted_min")),
    ]
    progress.write_text("\n".join(json.dumps({"key": str(idx), "row": value}) for idx, value in enumerate(rows)))
    meta.write_text(json.dumps({"completed_rows": 3, "total_rows": 81}))

    loaded, loaded_meta, source_kind = load_rows(base.with_suffix(".json"))
    summary = summarize(loaded, loaded_meta, source_kind)

    assert summary["source_kind"] == "progress"
    assert summary["completed_rows"] == 3
    assert summary["total_rows"] == 81
    assert summary["diagnostic_triggered_count"] == 2
    assert summary["diagnostic_q25_max"] == 0.207
    assert summary["diagnostic_sign_max"] == 0.833
    assert summary["fail_counts"]["positive_3_of_4_years"] == 3
    assert summary["fail_counts"]["validation_sharpe20_ge_adjusted_min"] == 1

    text = format_text(summary)
    assert "rows=3/81" in text
    assert "diagnostic_triggered=2" in text
    assert "diag_q25=0.207" in text
