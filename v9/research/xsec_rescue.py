from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


LOOKBACK_H = (72, 168, 240, 336, 504, 672, 720, 1008, 1440)
SKIP_H = (0, 24)
REBALANCE_H = (24, 48, 72, 96, 120, 168, 240, 336)
K_VALUES = (2, 3, 4, 5)
SCORE_MODES = ("mom", "risk_adj_mom", "breakout", "vol_breakout")
MARKET_FILTER_H = (0, 336, 504, 720, 1008, 1344, 1440, 2160)
VOL_TARGET_ANN = (0.05, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18)
N_TRANCHES = (1, 3)
DRAWDOWN_STOPS = (0.0, 0.10, 0.15, 0.20)
COOLDOWNS_H = (0, 24, 72, 168, 336)
MARKET_CONFIRM_H = (0, 168, 336, 504, 720)
MARKET_DRAWDOWN_LIMITS = (0.0, 0.20, 0.25, 0.30, 0.35)

RESCUE_IGNORED_FAILURES = frozenset({"selection_passed_before_validation"})
RESCUE_HARD_REJECT_FAILURES = frozenset(
    {
        "max_dd20_le_25pct",
        "validation_max_dd20_le_30pct",
        "daily_turnover40_le_50pct",
        "validation_daily_turnover40_le_50pct",
        "return_2024h1_gt_minus_2pct",
        "validation_return20_gt_0",
        "validation_sharpe40_gt_0",
    }
)

GENE_LADDERS: dict[str, tuple[Any, ...]] = {
    "lookback_h": LOOKBACK_H,
    "skip_h": SKIP_H,
    "rebalance_h": REBALANCE_H,
    "k": K_VALUES,
    "score_mode": SCORE_MODES,
    "market_filter_h": MARKET_FILTER_H,
    "vol_target_ann": VOL_TARGET_ANN,
    "n_tranches": N_TRANCHES,
    "drawdown_stop": DRAWDOWN_STOPS,
    "cooldown_h": COOLDOWNS_H,
    "market_confirm_h": MARKET_CONFIRM_H,
    "market_drawdown_limit": MARKET_DRAWDOWN_LIMITS,
}

REQUIRED_CONFIG_KEYS = (
    "lookback_h",
    "skip_h",
    "rebalance_h",
    "k",
    "score_mode",
    "market_filter_h",
    "vol_target_ann",
)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validation_sharpe20(row: dict[str, Any]) -> float:
    return safe_float(((row.get("validation") or {}).get("cost20") or {}).get("sharpe"))


def selection_cost20(row: dict[str, Any]) -> dict[str, Any]:
    return dict((row.get("selection") or {}).get("cost20") or row.get("cost20") or {})


def selection_cost40(row: dict[str, Any]) -> dict[str, Any]:
    return dict((row.get("selection") or {}).get("cost40") or row.get("cost40") or {})


def selection_sharpe20(row: dict[str, Any]) -> float:
    return safe_float(selection_cost20(row).get("sharpe"))


def selection_sharpe40(row: dict[str, Any]) -> float:
    return safe_float(selection_cost40(row).get("sharpe"))


def selection_bootstrap_p5(row: dict[str, Any]) -> float:
    return safe_float(selection_cost20(row).get("bootstrap_30d_sharpe_p5"), -999.0)


def benchmark_sharpe_excess(row: dict[str, Any]) -> float:
    benchmark = selection_cost20(row).get("equal_weight_benchmark") or {}
    return safe_float(benchmark.get("sharpe_excess"), -999.0)


def active_rebalances40(row: dict[str, Any]) -> float:
    return safe_float(selection_cost40(row).get("active_rebalance_event_count"))


def time_in_market40(row: dict[str, Any]) -> float:
    return safe_float(selection_cost40(row).get("time_in_market_frac"))


def top_symbol_share(row: dict[str, Any]) -> float:
    return safe_float(selection_cost20(row).get("top_positive_symbol_share"), 1.0)


def failed_checks(row: dict[str, Any]) -> list[str]:
    return [name for name, passed in (row.get("advance_checks") or {}).items() if not passed]


def rescue_relevant_failures(row: dict[str, Any]) -> list[str]:
    return [name for name in failed_checks(row) if name not in RESCUE_IGNORED_FAILURES]


def diagnostic_metrics(row: dict[str, Any]) -> dict[str, float | bool]:
    diagnostic = row.get("diagnostic_walk_forward") or {}
    return {
        "triggered": bool(diagnostic.get("triggered")),
        "q25_sharpe": safe_float(diagnostic.get("q25_sharpe")),
        "sign_consistency": safe_float(diagnostic.get("sign_consistency")),
        "validation_sharpe20": safe_float(diagnostic.get("validation_sharpe20"), validation_sharpe20(row)),
        "validation_sharpe20_min": safe_float(diagnostic.get("validation_sharpe20_min")),
    }


def valid_config(config: dict[str, Any]) -> bool:
    return all(key in config for key in REQUIRED_CONFIG_KEYS)


def config_fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def yearly_returns(row: dict[str, Any]) -> dict[str, float]:
    cost20 = (row.get("selection") or {}).get("cost20") or row.get("cost20") or {}
    yearly = cost20.get("yearly") or {}
    return {str(name): safe_float(value.get("net_return")) for name, value in yearly.items() if isinstance(value, dict)}


def worst_year(row: dict[str, Any]) -> dict[str, Any]:
    returns = yearly_returns(row)
    if not returns:
        return {"bucket": None, "net_return": None}
    bucket, value = min(returns.items(), key=lambda item: item[1])
    return {"bucket": bucket, "net_return": value}


def is_rescue_seed(
    row: dict[str, Any],
    diagnostic_q25_min: float = 0.50,
    diagnostic_sign_min: float = 0.75,
) -> bool:
    metrics = diagnostic_metrics(row)
    validation_min = safe_float(metrics["validation_sharpe20_min"])
    if not metrics["triggered"] or not valid_config(row.get("config") or {}):
        return False
    if safe_float(metrics["q25_sharpe"]) < diagnostic_q25_min:
        return False
    if safe_float(metrics["sign_consistency"]) < diagnostic_sign_min:
        return False
    return validation_min <= 0.0 or safe_float(metrics["validation_sharpe20"]) >= validation_min


def is_near_miss_seed(
    row: dict[str, Any],
    max_failures: int = 3,
    min_selection_sharpe20: float = 1.20,
    min_bootstrap_p5: float = 0.0,
    min_active_rebalances40: float = 12.0,
    min_time_in_market40: float = 0.05,
) -> bool:
    if not valid_config(row.get("config") or {}):
        return False
    if bool(row.get("advance_passed")):
        return False
    failures = rescue_relevant_failures(row)
    if not failures or len(failures) > max(0, int(max_failures)):
        return False
    if RESCUE_HARD_REJECT_FAILURES.intersection(failures):
        return False
    if selection_sharpe20(row) < min_selection_sharpe20:
        return False
    if selection_bootstrap_p5(row) < min_bootstrap_p5:
        return False
    if active_rebalances40(row) < min_active_rebalances40:
        return False
    if time_in_market40(row) < min_time_in_market40:
        return False
    return True


def near_miss_sort_key(row: dict[str, Any]) -> tuple[float, ...]:
    failures = rescue_relevant_failures(row)
    return (
        -float(len(failures)),
        selection_bootstrap_p5(row),
        selection_sharpe20(row),
        benchmark_sharpe_excess(row),
        selection_sharpe40(row),
        active_rebalances40(row),
        time_in_market40(row),
        -top_symbol_share(row),
    )


def seed_record(row: dict[str, Any], source_index: int, seed_type: str = "diagnostic_walkforward") -> dict[str, Any]:
    metrics = diagnostic_metrics(row)
    relevant_failures = rescue_relevant_failures(row)
    return {
        "source_index": int(source_index),
        "rescue_seed_type": seed_type,
        "config": dict(row.get("config") or {}),
        "config_fingerprint": config_fingerprint(row.get("config") or {}),
        "diagnostic_q25_sharpe": safe_float(metrics["q25_sharpe"]),
        "diagnostic_sign_consistency": safe_float(metrics["sign_consistency"]),
        "selection_sharpe20": selection_sharpe20(row),
        "selection_sharpe40": selection_sharpe40(row),
        "selection_bootstrap_p5": selection_bootstrap_p5(row),
        "benchmark_sharpe_excess": benchmark_sharpe_excess(row),
        "active_rebalances40": active_rebalances40(row),
        "time_in_market40": time_in_market40(row),
        "top_symbol_share": top_symbol_share(row),
        "validation_sharpe20": validation_sharpe20(row),
        "failed_checks": failed_checks(row),
        "rescue_relevant_failures": relevant_failures,
        "rescue_relevant_failure_count": len(relevant_failures),
        "yearly_returns": yearly_returns(row),
        "worst_year": worst_year(row),
    }


def select_rescue_seeds(
    rows: list[dict[str, Any]],
    top_k: int = 8,
    diagnostic_q25_min: float = 0.50,
    diagnostic_sign_min: float = 0.75,
    allow_near_miss: bool = True,
    near_miss_max_failures: int = 3,
    near_miss_min_selection_sharpe20: float = 1.20,
    near_miss_min_bootstrap_p5: float = 0.0,
    near_miss_min_active_rebalances40: float = 12.0,
    near_miss_min_time_in_market40: float = 0.05,
) -> list[dict[str, Any]]:
    limit = max(0, int(top_k))
    if limit <= 0:
        return []

    diagnostic_rows = [
        (row, idx)
        for idx, row in enumerate(rows)
        if is_rescue_seed(row, diagnostic_q25_min=diagnostic_q25_min, diagnostic_sign_min=diagnostic_sign_min)
    ]
    diagnostic_rows.sort(
        key=lambda item: (
            safe_float(diagnostic_metrics(item[0])["q25_sharpe"]),
            validation_sharpe20(item[0]),
            selection_sharpe20(item[0]),
        ),
        reverse=True,
    )

    seeds: list[dict[str, Any]] = []
    seen_configs: set[str] = set()
    for row, idx in diagnostic_rows:
        fp = config_fingerprint(row.get("config") or {})
        if fp in seen_configs:
            continue
        seen_configs.add(fp)
        seeds.append(seed_record(row, idx, seed_type="diagnostic_walkforward"))
        if len(seeds) >= limit:
            return seeds

    if not allow_near_miss:
        return seeds

    near_miss_rows = [
        (row, idx)
        for idx, row in enumerate(rows)
        if is_near_miss_seed(
            row,
            max_failures=near_miss_max_failures,
            min_selection_sharpe20=near_miss_min_selection_sharpe20,
            min_bootstrap_p5=near_miss_min_bootstrap_p5,
            min_active_rebalances40=near_miss_min_active_rebalances40,
            min_time_in_market40=near_miss_min_time_in_market40,
        )
    ]
    near_miss_rows.sort(key=lambda item: near_miss_sort_key(item[0]), reverse=True)
    for row, idx in near_miss_rows:
        fp = config_fingerprint(row.get("config") or {})
        if fp in seen_configs:
            continue
        seen_configs.add(fp)
        seeds.append(seed_record(row, idx, seed_type="near_miss_gate"))
        if len(seeds) >= limit:
            break
    return seeds


def nearby_values(value: Any, ladder: tuple[Any, ...], radius: int = 2) -> list[Any]:
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
    failures = [name for name in failures if name not in RESCUE_IGNORED_FAILURES]
    ordered = []
    if "positive_3_of_4_years" in failures or "bootstrap_p5_ge_adjusted_min" in failures:
        ordered.extend(["market_filter_h", "market_confirm_h", "rebalance_h", "lookback_h", "vol_target_ann", "n_tranches"])
    if "benchmark_sharpe_excess_ge_0_10" in failures or "sharpe40_ge_1" in failures or "sharpe20_ge_1_2" in failures:
        ordered.extend(["score_mode", "k", "rebalance_h", "lookback_h", "vol_target_ann"])
    if "max_dd20_le_25pct" in failures or "validation_max_dd20_le_30pct" in failures:
        ordered.extend(["vol_target_ann", "drawdown_stop", "cooldown_h", "market_filter_h", "market_drawdown_limit", "rebalance_h", "n_tranches"])
    if "active_rebalances40_ge_min" in failures or "time_in_market40_ge_min" in failures:
        ordered.extend(["cooldown_h", "market_confirm_h", "market_drawdown_limit", "market_filter_h", "rebalance_h"])
    if "top_symbol_share_le_60pct" in failures:
        ordered.extend(["k", "n_tranches", "score_mode", "rebalance_h"])
    if "daily_turnover40_le_50pct" in failures or "validation_daily_turnover40_le_50pct" in failures:
        ordered.extend(["rebalance_h", "n_tranches", "cooldown_h"])
    if "validation_sharpe20_ge_adjusted_min" in failures:
        ordered.extend(["lookback_h", "rebalance_h", "k", "score_mode", "market_filter_h"])
    ordered.extend(
        [
            "lookback_h",
            "rebalance_h",
            "market_filter_h",
            "market_confirm_h",
            "market_drawdown_limit",
            "vol_target_ann",
            "score_mode",
            "k",
            "skip_h",
            "n_tranches",
            "drawdown_stop",
            "cooldown_h",
        ]
    )
    seen = set()
    return [gene for gene in ordered if gene not in seen and not seen.add(gene)]


def generate_rescue_neighbors(seed: dict[str, Any], budget: int = 30, radius: int = 2) -> list[dict[str, Any]]:
    base = dict(seed["config"])
    failures = list(seed.get("failed_checks") or [])
    neighbors: list[dict[str, Any]] = []
    seen = {config_fingerprint(base)}
    for gene in rescue_gene_order(failures):
        if gene not in base or gene not in GENE_LADDERS:
            continue
        for value in nearby_values(base[gene], GENE_LADDERS[gene], radius=radius):
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
                    "from": base[gene],
                    "to": value,
                    "config_fingerprint": fp,
                    "config": candidate,
                }
            )
            if len(neighbors) >= budget:
                return neighbors
    return neighbors


def build_rescue_plan(
    rows: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    source_artifact: str | None = None,
    top_k: int = 8,
    budget_per_seed: int = 30,
    allow_near_miss: bool = True,
    near_miss_max_failures: int = 3,
    near_miss_min_selection_sharpe20: float = 1.20,
    near_miss_min_bootstrap_p5: float = 0.0,
    near_miss_min_active_rebalances40: float = 12.0,
    near_miss_min_time_in_market40: float = 0.05,
) -> dict[str, Any]:
    seeds = select_rescue_seeds(
        rows,
        top_k=top_k,
        allow_near_miss=allow_near_miss,
        near_miss_max_failures=near_miss_max_failures,
        near_miss_min_selection_sharpe20=near_miss_min_selection_sharpe20,
        near_miss_min_bootstrap_p5=near_miss_min_bootstrap_p5,
        near_miss_min_active_rebalances40=near_miss_min_active_rebalances40,
        near_miss_min_time_in_market40=near_miss_min_time_in_market40,
    )
    configs: list[dict[str, Any]] = []
    seen_configs: set[str] = set()
    planned_seeds = []
    for seed in seeds:
        neighbors = generate_rescue_neighbors(seed, budget=budget_per_seed)
        unique_neighbors = []
        for neighbor in neighbors:
            fp = str(neighbor["config_fingerprint"])
            if fp in seen_configs:
                continue
            seen_configs.add(fp)
            configs.append(dict(neighbor["config"]))
            unique_neighbors.append(neighbor)
        seed_out = dict(seed)
        seed_out["neighbors"] = unique_neighbors
        seed_out["neighbor_count"] = len(unique_neighbors)
        planned_seeds.append(seed_out)
    meta = meta or {}
    prior_effective_trials = int(meta.get("effective_trials") or meta.get("prior_trials") or 0)
    diagnostic_seed_count = sum(1 for seed in planned_seeds if seed.get("rescue_seed_type") == "diagnostic_walkforward")
    near_miss_seed_count = sum(1 for seed in planned_seeds if seed.get("rescue_seed_type") == "near_miss_gate")
    return {
        "kind": "xsec_diagnostic_or_nearmiss_rescue_plan_v2",
        "source_artifact": source_artifact,
        "source_meta": meta,
        "seed_count": len(planned_seeds),
        "diagnostic_seed_count": diagnostic_seed_count,
        "near_miss_seed_count": near_miss_seed_count,
        "rescue_config_count": len(configs),
        "budget_per_seed": int(budget_per_seed),
        "rescue_seed_policy": {
            "diagnostic_q25_min": 0.50,
            "diagnostic_sign_min": 0.75,
            "allow_near_miss": bool(allow_near_miss),
            "near_miss_max_failures": int(near_miss_max_failures),
            "near_miss_min_selection_sharpe20": float(near_miss_min_selection_sharpe20),
            "near_miss_min_bootstrap_p5": float(near_miss_min_bootstrap_p5),
            "near_miss_min_active_rebalances40": float(near_miss_min_active_rebalances40),
            "near_miss_min_time_in_market40": float(near_miss_min_time_in_market40),
            "ignored_failures": sorted(RESCUE_IGNORED_FAILURES),
            "hard_reject_failures": sorted(RESCUE_HARD_REJECT_FAILURES),
        },
        "prior_effective_trials": prior_effective_trials,
        "effective_trials_after_rescue": prior_effective_trials + len(configs),
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "multiple_testing_note": "Every rescue config must be counted as an additional train-only trial before any validation threshold is interpreted.",
        "seeds": planned_seeds,
        "configs": configs,
    }


def rescue_artifact_paths(output_json: str) -> tuple[Path, Path]:
    stem = Path(output_json).stem
    base = Path("artifacts/v9/rescue")
    return base / f"{stem}_rescue_plan.json", base / f"{stem}_rescue_configs.json"


def write_rescue_artifacts(plan: dict[str, Any], plan_path: Path, config_path: Path) -> dict[str, Any]:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True))
    config_path.write_text(json.dumps(plan.get("configs", []), indent=2, sort_keys=True))
    return {
        "rescue_plan_json": str(plan_path),
        "rescue_config_json": str(config_path),
        "rescue_config_count": int(plan.get("rescue_config_count") or 0),
        "rescue_seed_count": int(plan.get("seed_count") or 0),
    }
