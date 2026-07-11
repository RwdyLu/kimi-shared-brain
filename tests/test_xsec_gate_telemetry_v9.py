from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_gate_telemetry.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_gate_telemetry", SCRIPT)
assert SPEC and SPEC.loader
telemetry_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telemetry_mod)


def sample_row(*, failures: tuple[str, ...], sharpe: float = 1.0, active: int = 10) -> dict:
    checks = {
        "positive_3_of_4_years": "positive_3_of_4_years" not in failures,
        "bootstrap_p5_ge_adjusted_min": "bootstrap_p5_ge_adjusted_min" not in failures,
        "active_rebalances40_ge_min": "active_rebalances40_ge_min" not in failures,
        "time_in_market40_ge_min": "time_in_market40_ge_min" not in failures,
        "benchmark_sharpe_excess_ge_0_10": "benchmark_sharpe_excess_ge_0_10" not in failures,
        "top_symbol_share_le_60pct": "top_symbol_share_le_60pct" not in failures,
    }
    return {
        "advance_passed": not failures,
        "advance_checks": checks,
        "config": {
            "score_mode": "breakout",
            "lookback_h": 168,
            "rebalance_h": 24,
            "k": 2,
            "drawdown_stop": 0.1,
            "cooldown_h": 168,
        },
        "cost20": {
            "sharpe": sharpe,
            "total_return": 0.1,
            "max_drawdown": 0.12,
            "bootstrap_30d_sharpe_p5": -0.2,
            "equal_weight_benchmark": {"sharpe_excess": -0.1},
            "top_positive_symbol_share": 0.8,
        },
        "cost40": {
            "sharpe": sharpe - 0.1,
            "daily_turnover": 0.01,
            "active_rebalance_event_count": active,
            "time_in_market_frac": 0.02,
        },
    }


def write_progress(base: Path, rows: list[dict]) -> Path:
    progress = base.with_suffix(".progress.jsonl")
    meta = base.with_suffix(".progress.meta.json")
    progress.write_text("\n".join(json.dumps({"key": str(idx), "row": row}) for idx, row in enumerate(rows)))
    meta.write_text(json.dumps({"completed_rows": len(rows), "total_rows": 10}))
    return base.with_suffix(".json")


def test_gate_telemetry_summarizes_failures_and_recommendations(tmp_path) -> None:
    artifact = write_progress(
        tmp_path / "xsec_case",
        [
            sample_row(failures=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min", "active_rebalances40_ge_min")),
            sample_row(failures=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min", "time_in_market40_ge_min")),
            sample_row(failures=("positive_3_of_4_years", "benchmark_sharpe_excess_ge_0_10", "top_symbol_share_le_60pct")),
            sample_row(failures=(), sharpe=1.8, active=20),
        ],
    )

    report = telemetry_mod.build_report(artifact, top_limit=3)
    text = telemetry_mod.format_text(report)

    assert report["completed_rows"] == 4
    assert report["total_rows"] == 10
    assert report["pass_count"] == 1
    assert report["near_miss_count"] == 3
    assert report["failure_counts"]["positive_3_of_4_years"] == 3
    assert report["failure_categories"]["robustness"] >= 5
    actions = {row["action"] for row in report["recommendations"]}
    assert "run_family_registry_and_holdout_queue_after_task_finishes" in actions
    assert "rescue_near_miss_configs_with_neighbor_grid" in actions
    assert "de_prioritize_current_preset_until_year_robustness_improves" in actions
    assert "rows=4/10" in text
    assert "safety=paper:False live:False" in text


def test_resolve_artifact_uses_active_progress_path(tmp_path, monkeypatch) -> None:
    state = tmp_path / "state.json"
    progress = tmp_path / "active.progress.jsonl"
    state.write_text(json.dumps({"active_task": {"progress_path": str(progress)}}))

    args = type("Args", (), {"artifact": "", "state": str(state)})()

    assert telemetry_mod.resolve_artifact(args) == progress
