from __future__ import annotations

import math
from typing import Any


NORMAL_P5_Z = 1.6448536269514722
MIN_SIGMA = 1e-9
TRAIN_ONLY_FACTORY_KINDS = {
    "tsmom_factory_v1_train_only_grid",
    "xsec_ohlcv_factory_v1_train_only_grid",
}


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def sidak_adjust(raw_p_value: float, trials: int) -> float:
    p = min(1.0, max(0.0, float(raw_p_value)))
    n = max(1, int(trials))
    return 1.0 - math.pow(1.0 - p, n)


def accepted_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    for row in payload.get("rows", []):
        if row.get("advance_passed"):
            return row
    for row in payload.get("top", []):
        if row.get("advance_passed"):
            return row
    return None


def cost_block(row: dict[str, Any], cost_name: str) -> dict[str, Any]:
    validation = row.get("validation") or {}
    selection = row.get("selection") or {}
    return validation.get(cost_name) or selection.get(cost_name) or row.get(cost_name) or {}


def preferred_cost_block(row: dict[str, Any], preferred_cost: str) -> tuple[str, dict[str, Any]]:
    fallback = "cost20" if preferred_cost == "cost40" else "cost40"
    for name in (preferred_cost, fallback):
        block = cost_block(row, name)
        if block:
            return name, block
    return preferred_cost, {}


def positive_bucket_fraction(block: dict[str, Any]) -> float | None:
    active = safe_float(block.get("active_yearly_bucket_count"))
    positive = safe_float(block.get("positive_active_yearly_bucket_count"))
    if active is None or active <= 0 or positive is None:
        yearly = block.get("yearly") or {}
        if not isinstance(yearly, dict):
            return None
        active_returns = [
            safe_float(row.get("net_return"))
            for row in yearly.values()
            if isinstance(row, dict) and safe_float(row.get("periods"), 0.0) > 0
        ]
        active_returns = [value for value in active_returns if value is not None]
        if not active_returns:
            return None
        return sum(1 for value in active_returns if value > 0.0) / len(active_returns)
    return positive / active


def activity_count(block: dict[str, Any]) -> float | None:
    direct = safe_float(block.get("trade_count"), safe_float(block.get("rebalance_event_count")))
    if direct is not None:
        return direct
    yearly = block.get("yearly") or {}
    if not isinstance(yearly, dict):
        return None
    periods = [
        safe_float(row.get("periods"))
        for row in yearly.values()
        if isinstance(row, dict) and safe_float(row.get("periods")) is not None
    ]
    if not periods:
        return None
    return float(sum(periods))


def bootstrap_sigma(sharpe: float | None, bootstrap_p5: float | None) -> float | None:
    if sharpe is None or bootstrap_p5 is None:
        return None
    if sharpe <= bootstrap_p5:
        return None
    return max(MIN_SIGMA, (sharpe - bootstrap_p5) / NORMAL_P5_Z)


def multiplicity_evidence(
    payload: dict[str, Any] | None,
    *,
    total_trials: int,
    preferred_cost: str = "cost40",
    max_adjusted_p_value: float = 0.05,
    min_sharpe: float = 1.0,
    max_drawdown: float = 0.35,
    min_positive_bucket_fraction: float = 2.0 / 3.0,
    min_activity_count: int = 50,
) -> dict[str, Any]:
    if not payload or payload.get("kind") not in TRAIN_ONLY_FACTORY_KINDS:
        return {"evaluated": False, "decision": "not_train_only_factory_artifact"}
    row = accepted_row(payload)
    if row is None:
        return {"evaluated": False, "decision": "missing_accepted_row"}
    cost_name, block = preferred_cost_block(row, preferred_cost)
    sharpe = safe_float(block.get("sharpe"))
    bootstrap_p5 = safe_float(block.get("bootstrap_30d_sharpe_p5"))
    sigma = bootstrap_sigma(sharpe, bootstrap_p5)
    drawdown = safe_float(block.get("max_drawdown"))
    bucket_fraction = positive_bucket_fraction(block)
    activity = activity_count(block)
    checks = {
        "has_sharpe_and_bootstrap_p5": sharpe is not None and bootstrap_p5 is not None and sigma is not None,
        "sharpe_ge_min": sharpe is not None and sharpe >= min_sharpe,
        "max_drawdown_le_max": drawdown is not None and drawdown <= max_drawdown,
        "positive_bucket_fraction_ge_min": bucket_fraction is not None and bucket_fraction >= min_positive_bucket_fraction,
        "activity_count_ge_min": activity is not None and activity >= min_activity_count,
    }
    raw_p_value = None
    adjusted_p_value = None
    z_score = None
    if sigma is not None and sharpe is not None:
        z_score = sharpe / sigma
        raw_p_value = normal_sf(z_score)
        adjusted_p_value = sidak_adjust(raw_p_value, total_trials)
        checks["adjusted_p_value_le_max"] = adjusted_p_value <= max_adjusted_p_value
    else:
        checks["adjusted_p_value_le_max"] = False
    passed = all(checks.values())
    if passed:
        decision = "multiplicity_survivor"
    elif checks.get("adjusted_p_value_le_max") is False:
        decision = "rejected_multiplicity"
    else:
        decision = "rejected_train_hard_gate"
    return {
        "evaluated": True,
        "decision": decision,
        "cost_name": cost_name,
        "total_trials": max(1, int(total_trials)),
        "thresholds": {
            "max_adjusted_p_value": max_adjusted_p_value,
            "min_sharpe": min_sharpe,
            "max_drawdown": max_drawdown,
            "min_positive_bucket_fraction": min_positive_bucket_fraction,
            "min_activity_count": int(min_activity_count),
        },
        "metrics": {
            "sharpe": sharpe,
            "bootstrap_30d_sharpe_p5": bootstrap_p5,
            "bootstrap_sigma": sigma,
            "z_score": z_score,
            "raw_p_value": raw_p_value,
            "adjusted_p_value": adjusted_p_value,
            "max_drawdown": drawdown,
            "positive_bucket_fraction": bucket_fraction,
            "activity_count": activity,
        },
        "checks": checks,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
