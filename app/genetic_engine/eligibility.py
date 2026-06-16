#!/usr/bin/env python3
"""Stage-based GA eligibility checks for Challenger admission."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "ga_stages.json"

REQUIRED_METRICS = (
    "avg_alpha",
    "ruin_probability",
    "max_drawdown",
    "profit_factor",
    "sharpe_ratio",
    "win_rate",
    "total_trades",
    "profitable_symbols",
    "worst_symbol_alpha",
    "single_symbol_profit_contribution",
    "symbols_tested",
)


@dataclass
class EligibilityResult:
    eligible: bool
    challenger_eligible: bool
    stage: str
    candidate_status: str
    failed_rules: List[Dict[str, Any]]
    rejected_reason: str
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "challenger_eligible": self.challenger_eligible,
            "stage": self.stage,
            "candidate_status": self.candidate_status,
            "failed_rules": self.failed_rules,
            "rejected_reason": self.rejected_reason,
            "metrics": self.metrics,
        }


def load_ga_stages_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_stage_for_epoch(epoch_number: int, config: Optional[Mapping[str, Any]] = None) -> str:
    cfg = dict(config or load_ga_stages_config())
    for stage_range in cfg.get("epoch_stage_ranges", []):
        start = int(stage_range["start_epoch"])
        end = stage_range.get("end_epoch")
        if epoch_number >= start and (end is None or epoch_number <= int(end)):
            return str(stage_range["stage"])
    return "stage3_validate"


def _extract_metrics(chromosome_or_metrics: Any) -> Dict[str, Any]:
    if isinstance(chromosome_or_metrics, Mapping):
        source = dict(chromosome_or_metrics)
    else:
        source = dict(getattr(chromosome_or_metrics, "fitness_details", {}) or {})

    mc_report = source.get("monte_carlo_final_review")
    if isinstance(mc_report, Mapping) and "ruin_probability" not in source:
        source["ruin_probability"] = mc_report.get("ruin_probability")

    return source


def _add_failed(
    failed_rules: List[Dict[str, Any]],
    metric: str,
    actual: Any,
    required: str,
    reason: str,
) -> None:
    failed_rules.append({
        "metric": metric,
        "actual": actual,
        "required": required,
        "reason": reason,
    })


def _as_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_min(
    metrics: Mapping[str, Any],
    failed_rules: List[Dict[str, Any]],
    metric: str,
    threshold: float,
    reason: str,
) -> None:
    actual = metrics.get(metric)
    numeric = _as_number(actual)
    if numeric is None:
        _add_failed(failed_rules, metric, actual, f">= {threshold}", f"metric missing: {metric}")
    elif numeric < threshold:
        _add_failed(failed_rules, metric, actual, f">= {threshold}", reason)


def _check_max(
    metrics: Mapping[str, Any],
    failed_rules: List[Dict[str, Any]],
    metric: str,
    threshold: float,
    reason: str,
) -> None:
    actual = metrics.get(metric)
    numeric = _as_number(actual)
    if numeric is None:
        _add_failed(failed_rules, metric, actual, f"<= {threshold}", f"metric missing: {metric}")
    elif numeric > threshold:
        _add_failed(failed_rules, metric, actual, f"<= {threshold}", reason)


def check_stage_eligibility(
    chromosome_or_metrics: Any,
    stage_name: str,
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = dict(config or load_ga_stages_config())
    stages = cfg.get("stages", {})
    if stage_name not in stages:
        raise ValueError(f"Unknown GA eligibility stage: {stage_name}")

    stage_cfg = stages[stage_name]
    metrics = _extract_metrics(chromosome_or_metrics)
    failed_rules: List[Dict[str, Any]] = []

    if metrics.get("data_invalid") is True:
        _add_failed(
            failed_rules,
            "data_invalid",
            True,
            "False",
            "data_invalid is True",
        )

    for metric in REQUIRED_METRICS:
        if metric not in metrics or metrics.get(metric) is None:
            _add_failed(
                failed_rules,
                metric,
                metrics.get(metric),
                "present",
                f"metric missing: {metric}",
            )

    direct = cfg.get("direct_rejects", {})
    _check_min(
        metrics,
        failed_rules,
        "avg_alpha",
        float(direct.get("avg_alpha_min", {}).get("value", -0.10)),
        "avg_alpha below direct reject threshold",
    )
    _check_max(
        metrics,
        failed_rules,
        "ruin_probability",
        float(direct.get("ruin_probability_max", {}).get("value", 0.50)),
        "ruin_probability above direct reject threshold",
    )
    _check_min(
        metrics,
        failed_rules,
        "symbols_tested",
        float(direct.get("symbols_tested_min", {}).get("value", 10)),
        "symbols_tested below direct reject threshold",
    )

    _check_min(metrics, failed_rules, "avg_alpha", float(stage_cfg["avg_alpha_min"]), "avg_alpha below stage threshold")
    _check_max(metrics, failed_rules, "ruin_probability", float(stage_cfg["ruin_probability_max"]), "ruin_probability above stage threshold")
    _check_max(metrics, failed_rules, "max_drawdown", float(stage_cfg["max_drawdown_max"]), "max_drawdown above stage threshold")
    _check_min(metrics, failed_rules, "profit_factor", float(stage_cfg["profit_factor_min"]), "profit_factor below stage threshold")
    _check_min(metrics, failed_rules, "sharpe_ratio", float(stage_cfg["sharpe_ratio_min"]), "sharpe_ratio below stage threshold")
    _check_min(metrics, failed_rules, "win_rate", float(stage_cfg["win_rate_min"]), "win_rate below stage threshold")
    _check_min(metrics, failed_rules, "total_trades", float(stage_cfg["total_trades_min"]), "total_trades below stage threshold")
    _check_min(metrics, failed_rules, "profitable_symbols", float(stage_cfg["profitable_symbols_min"]), "profitable_symbols below stage threshold")
    _check_min(metrics, failed_rules, "worst_symbol_alpha", float(stage_cfg["worst_symbol_alpha_min"]), "worst_symbol_alpha below stage threshold")
    _check_max(
        metrics,
        failed_rules,
        "single_symbol_profit_contribution",
        float(stage_cfg["single_symbol_profit_contribution_max"]),
        "single_symbol_profit_contribution above stage threshold",
    )

    eligible = not failed_rules
    challenger_eligible = eligible and bool(stage_cfg.get("challenger_allowed", False))
    candidate_status = (
        stage_cfg.get("candidate_status", "qualified_challenger")
        if eligible
        else "rejected"
    )
    rejected_reason = "; ".join(rule["reason"] for rule in failed_rules)

    return EligibilityResult(
        eligible=eligible,
        challenger_eligible=challenger_eligible,
        stage=stage_name,
        candidate_status=candidate_status,
        failed_rules=failed_rules,
        rejected_reason=rejected_reason,
        metrics=metrics,
    ).to_dict()
