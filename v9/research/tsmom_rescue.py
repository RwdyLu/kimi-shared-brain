from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ASSET_VOL_TARGET_ANN = (0.25, 0.35, 0.45)
PORTFOLIO_VOL_TARGET_ANN = (0.04, 0.06, 0.08, 0.10, 0.12)
NO_TRADE_BAND = (0.05, 0.10, 0.15, 0.20, 0.30, 0.50)
VOTE_THRESHOLD = (0.50, 0.625, 0.75)
MARKET_FILTER_H = (0, 168, 240, 336, 504, 720, 1440, 2160)
MARKET_OFF_SCALE = (0.0, 0.50)
DRAWDOWN_STOP = (0.0, 0.10, 0.12, 0.15, 0.20)
COOLDOWN_H = (0, 336, 480, 720)
BEAR_SHORT_SCALE = (0.0, 0.05, 0.10, 0.15, 0.33, 0.50, 0.67, 1.0)
SHORT_VOTE_THRESHOLD = (0.25, 0.375, 0.50)

GENE_LADDERS: dict[str, tuple[Any, ...]] = {
    "asset_vol_target_ann": ASSET_VOL_TARGET_ANN,
    "portfolio_vol_target_ann": PORTFOLIO_VOL_TARGET_ANN,
    "no_trade_band": NO_TRADE_BAND,
    "vote_threshold": VOTE_THRESHOLD,
    "market_filter_h": MARKET_FILTER_H,
    "market_off_scale": MARKET_OFF_SCALE,
    "drawdown_stop": DRAWDOWN_STOP,
    "cooldown_h": COOLDOWN_H,
    "bear_short_scale": BEAR_SHORT_SCALE,
    "short_vote_threshold": SHORT_VOTE_THRESHOLD,
}

REQUIRED_CONFIG_KEYS = (
    "asset_vol_target_ann",
    "portfolio_vol_target_ann",
    "no_trade_band",
)

ALLOWED_RESCUE_FAILURES = {
    "drop_one_lookback_stable",
    "leave_one_symbol_robust",
    "validation_sharpe20_ge_adjusted_min",
    "validation_max_dd20_le_35pct",
    "validation_return20_gt_0",
    "validation_sharpe40_gt_0",
    "validation_positive_active_yearly_buckets_ge_50pct",
    "validation_breadth_positive_symbols_ge_min",
    "validation_long_leg_gross_return_gt_minus_5pct",
    "validation_short_leg_gross_return_gt_minus_5pct",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def failed_checks(row: dict[str, Any]) -> list[str]:
    return [name for name, passed in (row.get("advance_checks") or {}).items() if not passed]


def valid_config(config: dict[str, Any]) -> bool:
    return all(key in config for key in REQUIRED_CONFIG_KEYS)


def config_fingerprint(config: dict[str, Any]) -> str:
    payload = {key: value for key, value in config.items() if not str(key).startswith("parent_")}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def selection_cost20(row: dict[str, Any]) -> dict[str, Any]:
    return (row.get("selection") or {}).get("cost20") or row.get("cost20") or {}


def selection_checks(row: dict[str, Any]) -> dict[str, bool]:
    return dict((row.get("selection") or {}).get("checks") or {})


def validation_cost20(row: dict[str, Any]) -> dict[str, Any]:
    return (row.get("validation") or {}).get("cost20") or {}


def selection_bootstrap_passed(row: dict[str, Any], meta: dict[str, Any] | None = None) -> bool:
    checks = selection_checks(row)
    if "bootstrap_p5_ge_adjusted_min" in checks:
        return bool(checks["bootstrap_p5_ge_adjusted_min"])
    threshold = safe_float((meta or {}).get("selection_bootstrap_p5_min"), 0.25)
    return safe_float(selection_cost20(row).get("bootstrap_30d_sharpe_p5")) >= threshold


def walk_forward_passed(row: dict[str, Any]) -> bool:
    return bool((row.get("walk_forward") or {}).get("passed"))


def is_tsmom_rescue_seed(
    row: dict[str, Any],
    meta: dict[str, Any] | None = None,
    *,
    max_failures: int = 2,
) -> bool:
    failures = failed_checks(row)
    if not failures or row.get("advance_passed"):
        return False
    if len(failures) > max_failures:
        return False
    if any(name not in ALLOWED_RESCUE_FAILURES for name in failures):
        return False
    if not valid_config(row.get("config") or {}):
        return False
    return selection_bootstrap_passed(row, meta) and walk_forward_passed(row)


def seed_record(row: dict[str, Any], source_index: int) -> dict[str, Any]:
    c20 = selection_cost20(row)
    v20 = validation_cost20(row)
    config = dict(row.get("config") or {})
    return {
        "source_index": int(source_index),
        "config": config,
        "config_fingerprint": config_fingerprint(config),
        "selection_sharpe20": safe_float(c20.get("sharpe")),
        "selection_total_return20": safe_float(c20.get("total_return")),
        "selection_max_drawdown20": safe_float(c20.get("max_drawdown"), 1.0),
        "selection_bootstrap_p5": safe_float(c20.get("bootstrap_30d_sharpe_p5")),
        "walk_forward_q25_sharpe": safe_float((row.get("walk_forward") or {}).get("q25_sharpe")),
        "validation_sharpe20": safe_float(v20.get("sharpe")),
        "validation_max_drawdown20": safe_float(v20.get("max_drawdown"), 1.0),
        "failed_checks": failed_checks(row),
    }


def select_tsmom_rescue_seeds(
    rows: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    *,
    top_k: int = 3,
    max_failures: int = 2,
) -> list[dict[str, Any]]:
    seeds = [
        seed_record(row, idx)
        for idx, row in enumerate(rows)
        if is_tsmom_rescue_seed(row, meta, max_failures=max_failures)
    ]
    seeds.sort(
        key=lambda seed: (
            safe_float(seed["validation_sharpe20"]),
            safe_float(seed["walk_forward_q25_sharpe"]),
            safe_float(seed["selection_bootstrap_p5"]),
            safe_float(seed["selection_sharpe20"]),
            -safe_float(seed["selection_max_drawdown20"]),
        ),
        reverse=True,
    )
    return seeds[: max(0, int(top_k))]


def nearby_values(value: Any, ladder: tuple[Any, ...], radius: int = 1) -> list[Any]:
    if value not in ladder:
        try:
            numeric_value = float(value)
            idx = min(range(len(ladder)), key=lambda pos: abs(float(ladder[pos]) - numeric_value))
        except (TypeError, ValueError):
            return []
    else:
        idx = ladder.index(value)
    lo = max(0, idx - radius)
    hi = min(len(ladder), idx + radius + 1)
    return [candidate for candidate in ladder[lo:hi] if candidate != value]


def rescue_gene_order(failures: list[str]) -> list[str]:
    ordered: list[str] = []
    if "drop_one_lookback_stable" in failures:
        ordered.extend(["vote_threshold", "no_trade_band", "market_filter_h", "portfolio_vol_target_ann"])
    if "leave_one_symbol_robust" in failures:
        ordered.extend(["market_filter_h", "asset_vol_target_ann", "portfolio_vol_target_ann", "bear_short_scale"])
    if "validation_short_leg_gross_return_gt_minus_5pct" in failures:
        ordered.extend(["bear_short_scale", "short_vote_threshold", "market_filter_h"])
    if any(name.startswith("validation_") for name in failures):
        ordered.extend(["portfolio_vol_target_ann", "no_trade_band", "market_filter_h", "vote_threshold"])
    ordered.extend(
        [
            "market_filter_h",
            "portfolio_vol_target_ann",
            "asset_vol_target_ann",
            "no_trade_band",
            "vote_threshold",
            "bear_short_scale",
            "short_vote_threshold",
            "drawdown_stop",
            "cooldown_h",
        ]
    )
    seen = set()
    return [gene for gene in ordered if gene not in seen and not seen.add(gene)]


def generate_tsmom_rescue_neighbors(seed: dict[str, Any], budget: int = 25, radius: int = 1) -> list[dict[str, Any]]:
    base = dict(seed["config"])
    failures = list(seed.get("failed_checks") or [])
    neighbors: list[dict[str, Any]] = []
    seen = {config_fingerprint(base)}
    for gene in rescue_gene_order(failures):
        if gene not in GENE_LADDERS:
            continue
        base_value = base.get(gene, 0.0 if gene in {"market_off_scale", "drawdown_stop", "bear_short_scale"} else None)
        for value in nearby_values(base_value, GENE_LADDERS[gene], radius=radius):
            candidate = dict(base)
            candidate[gene] = value
            fp = config_fingerprint(candidate)
            if fp in seen:
                continue
            seen.add(fp)
            neighbors.append(
                {
                    "parent_source_index": seed["source_index"],
                    "parent_config_fingerprint": seed["config_fingerprint"],
                    "changed_gene": gene,
                    "from": base_value,
                    "to": value,
                    "config_fingerprint": fp,
                    "config": candidate,
                }
            )
            if len(neighbors) >= budget:
                return neighbors
    return neighbors


def build_tsmom_rescue_plan(
    rows: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    source_artifact: str | None = None,
    *,
    top_k: int = 3,
    budget_per_seed: int = 25,
    max_failures: int = 2,
) -> dict[str, Any]:
    meta = meta or {}
    seeds = select_tsmom_rescue_seeds(rows, meta, top_k=top_k, max_failures=max_failures)
    configs: list[dict[str, Any]] = []
    seen_configs: set[str] = set()
    planned_seeds = []
    for seed in seeds:
        neighbors = generate_tsmom_rescue_neighbors(seed, budget=budget_per_seed)
        unique_neighbors = []
        for neighbor in neighbors:
            fp = str(neighbor["config_fingerprint"])
            if fp in seen_configs:
                continue
            seen_configs.add(fp)
            config = dict(neighbor["config"])
            config["parent_tsmom_rescue_source_index"] = int(seed["source_index"])
            config["parent_tsmom_rescue_fingerprint"] = str(seed["config_fingerprint"])
            configs.append(config)
            unique_neighbors.append(neighbor)
        seed_out = dict(seed)
        seed_out["neighbors"] = unique_neighbors
        seed_out["neighbor_count"] = len(unique_neighbors)
        planned_seeds.append(seed_out)
    prior_effective_trials = int(meta.get("effective_trials") or meta.get("prior_trials") or 0)
    return {
        "kind": "tsmom_near_miss_rescue_plan_v1",
        "source_artifact": source_artifact,
        "source_meta": meta,
        "seed_count": len(planned_seeds),
        "rescue_config_count": len(configs),
        "budget_per_seed": int(budget_per_seed),
        "max_failures": int(max_failures),
        "prior_effective_trials": prior_effective_trials,
        "effective_trials_after_rescue": prior_effective_trials + len(configs),
        "accepted_via_rescue": True,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "multiple_testing_note": "Every rescue config is an extra train-only trial. Validation gates remain unchanged; no holdout, paper, or live authorization.",
        "seeds": planned_seeds,
        "configs": configs,
    }


def tsmom_rescue_artifact_paths(output_json: str) -> tuple[Path, Path]:
    stem = Path(output_json).stem
    base = Path("artifacts/v9/rescue")
    return base / f"{stem}_tsmom_rescue_plan.json", base / f"{stem}_tsmom_rescue_configs.json"


def write_tsmom_rescue_artifacts(plan: dict[str, Any], plan_path: Path, config_path: Path) -> dict[str, Any]:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True))
    config_path.write_text(json.dumps(plan.get("configs", []), indent=2, sort_keys=True))
    return {
        "rescue_plan_json": str(plan_path),
        "rescue_config_json": str(config_path),
        "rescue_seed_count": int(plan.get("seed_count") or 0),
        "rescue_config_count": int(plan.get("rescue_config_count") or 0),
        "effective_trials_after_rescue": int(plan.get("effective_trials_after_rescue") or 0),
        "accepted_via_rescue": True,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
