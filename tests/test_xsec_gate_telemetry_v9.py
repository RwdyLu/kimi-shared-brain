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


def sample_row(
    *,
    failures: tuple[str, ...],
    config_overrides: dict | None = None,
    sharpe: float = 1.5,
    active: int = 20,
    time_in_market: float = 0.10,
    bootstrap_p5: float = 0.20,
    yearly: dict[str, float] | None = None,
) -> dict:
    checks = {
        "positive_3_of_4_years": "positive_3_of_4_years" not in failures,
        "bootstrap_p5_ge_adjusted_min": "bootstrap_p5_ge_adjusted_min" not in failures,
        "active_rebalances40_ge_min": "active_rebalances40_ge_min" not in failures,
        "time_in_market40_ge_min": "time_in_market40_ge_min" not in failures,
        "benchmark_sharpe_excess_ge_0_10": "benchmark_sharpe_excess_ge_0_10" not in failures,
        "top_symbol_share_le_60pct": "top_symbol_share_le_60pct" not in failures,
        "selection_passed_before_validation": "selection_passed_before_validation" not in failures,
    }
    yearly = yearly or {"2021": 0.10, "2022": -0.05, "2023": 0.04, "2024H1": 0.03}
    config = {
        "score_mode": "breakout",
        "lookback_h": 168,
        "skip_h": 0,
        "rebalance_h": 24,
        "k": 2,
        "market_filter_h": 720,
        "market_confirm_h": 168,
        "market_drawdown_limit": 0.25,
        "vol_target_ann": 0.08,
        "drawdown_stop": 0.1,
        "cooldown_h": 168,
        "n_tranches": 1,
    }
    config.update(config_overrides or {})
    return {
        "advance_passed": not failures,
        "advance_checks": checks,
        "config": config,
        "cost20": {
            "sharpe": sharpe,
            "total_return": 0.1,
            "max_drawdown": 0.12,
            "bootstrap_30d_sharpe_p5": bootstrap_p5,
            "equal_weight_benchmark": {"sharpe_excess": -0.1},
            "top_positive_symbol_share": 0.8,
            "yearly": {bucket: {"net_return": value} for bucket, value in yearly.items()},
        },
        "cost40": {
            "sharpe": sharpe - 0.1,
            "daily_turnover": 0.01,
            "active_rebalance_event_count": active,
            "time_in_market_frac": time_in_market,
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
            sample_row(
                failures=("positive_3_of_4_years", "bootstrap_p5_ge_adjusted_min", "time_in_market40_ge_min"),
                config_overrides={"lookback_h": 240},
            ),
            sample_row(
                failures=("positive_3_of_4_years", "benchmark_sharpe_excess_ge_0_10", "top_symbol_share_le_60pct"),
                config_overrides={"lookback_h": 336},
            ),
            sample_row(failures=(), config_overrides={"lookback_h": 504}, sharpe=1.8, active=20),
        ],
    )

    report = telemetry_mod.build_report(artifact, top_limit=3)
    text = telemetry_mod.format_text(report)

    assert report["completed_rows"] == 4
    assert report["total_rows"] == 10
    assert report["pass_count"] == 1
    assert report["near_miss_count"] == 3
    assert report["near_miss_definition"]["ignored_failures"] == ["selection_passed_before_validation", "validation_usable"]
    assert report["failure_counts"]["positive_3_of_4_years"] == 3
    assert report["failure_categories"]["robustness"] >= 5
    assert report["year_robustness"]["near_miss_rows"]["worst_year_counts"]["2022"] == 3
    assert report["rescue_preview"]["enabled"] is True
    assert report["rescue_preview"]["seed_count"] > 0
    assert report["rescue_preview"]["near_miss_seed_count"] > 0
    assert report["rescue_preview"]["rescue_config_count"] <= report["rescue_preview"]["auto_config_cap"]
    assert report["rescue_preview"]["within_auto_cap"] is True
    assert report["top_rows"][0]["year_robustness"]["worst_year"]["bucket"] == "2022"
    actions = {row["action"] for row in report["recommendations"]}
    assert "run_family_registry_and_holdout_queue_after_task_finishes" in actions
    assert "rescue_near_miss_configs_with_neighbor_grid" in actions
    assert "de_prioritize_current_preset_until_year_robustness_improves" in actions
    assert "diagnose_hostile_year_regime_filter_before_broadening_search" in actions
    assert "rows=4/10" in text
    assert "safety=paper:False live:False" in text
    assert "near_miss_definition=market_failures<=3" in text
    assert "near_miss_worst_years: 2022:3" in text
    assert "rescue_preview:" in text
    assert "within_cap:True" in text


def test_gate_telemetry_near_miss_ignores_validation_flow_failures(tmp_path) -> None:
    artifact = write_progress(
        tmp_path / "xsec_case",
        [
            sample_row(
                failures=(
                    "selection_passed_before_validation",
                    "positive_3_of_4_years",
                    "bootstrap_p5_ge_adjusted_min",
                    "active_rebalances40_ge_min",
                )
            ),
            sample_row(
                failures=(
                    "selection_passed_before_validation",
                    "positive_3_of_4_years",
                    "bootstrap_p5_ge_adjusted_min",
                    "active_rebalances40_ge_min",
                    "benchmark_sharpe_excess_ge_0_10",
                )
            ),
        ],
    )

    report = telemetry_mod.build_report(artifact, top_limit=2)

    assert report["failure_counts"]["selection_passed_before_validation"] == 2
    assert report["near_miss_count"] == 1
    assert report["near_miss_rows"][0]["market_failed_checks"] == [
        "positive_3_of_4_years",
        "bootstrap_p5_ge_adjusted_min",
        "active_rebalances40_ge_min",
    ]
    assert len(report["near_miss_rows"][0]["failed_checks"]) == 4


def test_resolve_artifact_uses_active_progress_path(tmp_path, monkeypatch) -> None:
    state = tmp_path / "state.json"
    progress = tmp_path / "active.progress.jsonl"
    state.write_text(json.dumps({"active_task": {"progress_path": str(progress)}}))

    args = type("Args", (), {"artifact": "", "state": str(state)})()

    assert telemetry_mod.resolve_artifact(args) == progress
