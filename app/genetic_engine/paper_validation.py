#!/usr/bin/env python3
"""GA Shadow/Paper validation lifecycle helpers.

This module only records simulated validation metrics in the GA archive. It does
not call exchange APIs, place orders, or touch state/paper_trading_state.json.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .archive import StrategyArchive


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "ga_paper_validation.json"
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "data" / "genetic_archive"


PAPER_METRIC_DEFAULTS = {
    "paper_started_at": None,
    "paper_days": 0,
    "paper_trades": 0,
    "paper_closed_trades": 0,
    "paper_open_trades": 0,
    "paper_pnl": 0.0,
    "paper_gross_pnl": 0.0,
    "paper_fees": 0.0,
    "paper_slippage": 0.0,
    "paper_max_drawdown": 0.0,
    "paper_win_rate": 0.0,
    "paper_profit_factor": 0.0,
    "paper_symbols_traded": [],
    "paper_last_updated": None,
}


def load_paper_validation_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def default_paper_metrics(now: Optional[str] = None) -> Dict[str, Any]:
    timestamp = now or datetime.now().isoformat()
    metrics = dict(PAPER_METRIC_DEFAULTS)
    metrics["paper_started_at"] = timestamp
    metrics["paper_last_updated"] = timestamp
    return metrics


def _merge_metrics(existing: Mapping[str, Any], update: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = dict(PAPER_METRIC_DEFAULTS)
    metrics.update(dict(existing or {}))
    incoming = dict(update.get("paper_metrics", update) or {})
    metrics.update(incoming)
    metrics["paper_last_updated"] = incoming.get("paper_last_updated") or datetime.now().isoformat()
    if not metrics.get("paper_started_at"):
        metrics["paper_started_at"] = metrics["paper_last_updated"]
    return metrics


def _ruin_probability_from(record) -> Any:
    details = record.fitness_details or {}
    if "ruin_probability" in details:
        return details.get("ruin_probability")
    review = details.get("monte_carlo_final_review")
    if isinstance(review, Mapping):
        return review.get("ruin_probability")
    eligibility = details.get("eligibility")
    if isinstance(eligibility, Mapping):
        metrics = eligibility.get("metrics")
        if isinstance(metrics, Mapping):
            return metrics.get("ruin_probability")
    return None


class PaperValidationManager:
    """Coordinates GA archive transitions for Shadow/Paper validation."""

    def __init__(
        self,
        archive_dir: Optional[Path] = None,
        config_path: Optional[Path] = None,
        archive: Optional[StrategyArchive] = None,
    ):
        self.archive = archive or StrategyArchive(str(archive_dir or DEFAULT_ARCHIVE_DIR))
        self.config = load_paper_validation_config(config_path)

    def start_paper_validation(self, record_id: str) -> bool:
        if not self.archive.start_validation(record_id):
            return False
        record = self.archive._find_record(record_id, "validating")
        if not record:
            return False
        record.paper_metrics = default_paper_metrics()
        self.archive._save_all()
        return True

    def update_paper_metrics(self, record_id: str, trade_or_snapshot: Mapping[str, Any]) -> bool:
        record = self.archive._find_record(record_id, "validating")
        if not record:
            return False
        record.paper_metrics = _merge_metrics(record.paper_metrics, trade_or_snapshot)
        record.paper_trades = int(record.paper_metrics.get("paper_closed_trades", record.paper_trades))
        record.paper_pnl = float(record.paper_metrics.get("paper_pnl", record.paper_pnl))
        self.archive._save_all()
        return True

    def evaluate_paper_validation(self, record_id: str) -> Dict[str, Any]:
        record = self.archive._find_record(record_id, "validating")
        if not record:
            return {
                "passed": False,
                "failed_rules": [{
                    "metric": "status",
                    "actual": None,
                    "required": "validating",
                    "reason": "record is not validating",
                }],
                "paper_metrics": {},
            }

        metrics = dict(record.paper_metrics or {})
        ruin_probability = _ruin_probability_from(record)
        failed_rules = []

        checks = (
            ("paper_days", metrics.get("paper_days"), ">=", self.config["paper_days_min"], "paper_days below threshold"),
            ("paper_closed_trades", metrics.get("paper_closed_trades"), ">=", self.config["paper_closed_trades_min"], "paper_closed_trades below threshold"),
            ("paper_pnl", metrics.get("paper_pnl"), ">", self.config["paper_pnl_min"], "paper_pnl must be positive"),
            ("paper_max_drawdown", metrics.get("paper_max_drawdown"), "<=", self.config["paper_max_drawdown_max"], "paper_max_drawdown above threshold"),
            ("ruin_probability", ruin_probability, "<=", self.config["ruin_probability_max"], "ruin_probability above threshold"),
            ("paper_profit_factor", metrics.get("paper_profit_factor"), ">=", self.config["paper_profit_factor_min"], "paper_profit_factor below threshold"),
            ("paper_win_rate", metrics.get("paper_win_rate"), ">=", self.config["paper_win_rate_min"], "paper_win_rate below threshold"),
        )

        for metric, actual, op, threshold, reason in checks:
            if actual is None:
                failed_rules.append({
                    "metric": metric,
                    "actual": actual,
                    "required": f"{op} {threshold}",
                    "reason": f"metric missing: {metric}",
                })
                continue
            value = float(actual)
            passed = value > threshold if op == ">" else value >= threshold if op == ">=" else value <= threshold
            if not passed:
                failed_rules.append({
                    "metric": metric,
                    "actual": actual,
                    "required": f"{op} {threshold}",
                    "reason": reason,
                })

        return {
            "passed": not failed_rules,
            "failed_rules": failed_rules,
            "paper_metrics": metrics,
            "ruin_probability": ruin_probability,
        }

    def mark_pending_acceptance_if_passed(self, record_id: str) -> bool:
        result = self.evaluate_paper_validation(record_id)
        record = self.archive._find_record(record_id, "validating")
        if not record:
            return False
        record.paper_metrics = dict(record.paper_metrics or {})
        record.paper_metrics["paper_validation_passed"] = result["passed"]
        record.paper_metrics["paper_validation_failed_rules"] = result["failed_rules"]
        record.paper_metrics["paper_validation_checked_at"] = datetime.now().isoformat()
        if not result["passed"]:
            self.archive._save_all()
            return False
        return self.archive.mark_pending_acceptance(record_id, record.paper_metrics)


def start_paper_validation(record_id: str, archive_dir: Optional[Path] = None) -> bool:
    return PaperValidationManager(archive_dir=archive_dir).start_paper_validation(record_id)


def update_paper_metrics(
    record_id: str,
    trade_or_snapshot: Mapping[str, Any],
    archive_dir: Optional[Path] = None,
) -> bool:
    return PaperValidationManager(archive_dir=archive_dir).update_paper_metrics(
        record_id,
        trade_or_snapshot,
    )


def evaluate_paper_validation(record_id: str, archive_dir: Optional[Path] = None) -> Dict[str, Any]:
    return PaperValidationManager(archive_dir=archive_dir).evaluate_paper_validation(record_id)


def mark_pending_acceptance_if_passed(record_id: str, archive_dir: Optional[Path] = None) -> bool:
    return PaperValidationManager(archive_dir=archive_dir).mark_pending_acceptance_if_passed(record_id)
