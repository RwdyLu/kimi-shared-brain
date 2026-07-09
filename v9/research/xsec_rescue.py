from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


LOOKBACK_H = (72, 168, 240, 336, 504, 672, 720, 1008, 1440)
SKIP_H = (0, 24)
REBALANCE_H = (24, 48, 72, 96, 120, 168, 240, 336)
K_VALUES = (2, 3, 4, 5)
MARKET_FILTER_H = (0, 336, 504, 720, 1008, 1344, 1440, 2160)
VOL_TARGET_ANN = (0.05, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18)
N_TRANCHES = (1, 3)

GENE_LADDERS: dict[str, tuple[Any, ...]] = {
    "lookback_h": LOOKBACK_H,
    "skip_h": SKIP_H,
    "rebalance_h": REBALANCE_H,
    "k": K_VALUES,
    "market_filter_h": MARKET_FILTER_H,
    "vol_target_ann": VOL_TARGET_ANN,
    "n_tranches": N_TRANCHES,
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


def selection_sharpe20(row: dict[str, Any]) -> float:
    return safe_float(((row.get("selection") or {}).get("cost20") or row.get("cost20") or {}).get("sharpe"))


def failed_checks(row: dict[str, Any]) -> list[str]:
    return [name for name, passed in (row.get("advance_checks") or {}).items() if not passed]


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


def seed_record(row: dict[str, Any], source_index: int) -> dict[str, Any]:
    metrics = diagnostic_metrics(row)
    return {
        "source_index": int(source_index),
        "config": dict(row.get("config") or {}),
        "config_fingerprint": config_fingerprint(row.get("config") or {}),
        "diagnostic_q25_sharpe": safe_float(metrics["q25_sharpe"]),
        "diagnostic_sign_consistency": safe_float(metrics["sign_consistency"]),
        "selection_sharpe20": selection_sharpe20(row),
        "validation_sharpe20": validation_sharpe20(row),
        "failed_checks": failed_checks(row),
        "yearly_returns": yearly_returns(row),
        "worst_year": worst_year(row),
    }


def select_rescue_seeds(
    rows: list[dict[str, Any]],
    top_k: int = 8,
    diagnostic_q25_min: float = 0.50,
    diagnostic_sign_min: float = 0.75,
) -> list[dict[str, Any]]:
    seeds = [
        seed_record(row, idx)
        for idx, row in enumerate(rows)
        if is_rescue_seed(row, diagnostic_q25_min=diagnostic_q25_min, diagnostic_sign_min=diagnostic_sign_min)
    ]
    seeds.sort(
        key=lambda seed: (
            safe_float(seed["diagnostic_q25_sharpe"]),
            safe_float(seed["validation_sharpe20"]),
            safe_float(seed["selection_sharpe20"]),
        ),
        reverse=True,
    )
    return seeds[: max(0, int(top_k))]


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
    ordered = []
    if "positive_3_of_4_years" in failures:
        ordered.extend(["market_filter_h", "rebalance_h", "lookback_h", "vol_target_ann"])
    if "max_dd20_le_25pct" in failures or "validation_max_dd20_le_30pct" in failures:
        ordered.extend(["vol_target_ann", "market_filter_h", "rebalance_h", "n_tranches"])
    if "validation_sharpe20_ge_adjusted_min" in failures:
        ordered.extend(["lookback_h", "rebalance_h", "k", "market_filter_h"])
    ordered.extend(["lookback_h", "rebalance_h", "market_filter_h", "vol_target_ann", "k", "skip_h", "n_tranches"])
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
) -> dict[str, Any]:
    seeds = select_rescue_seeds(rows, top_k=top_k)
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
    return {
        "kind": "xsec_diagnostic_rescue_plan_v1",
        "source_artifact": source_artifact,
        "source_meta": meta,
        "seed_count": len(planned_seeds),
        "rescue_config_count": len(configs),
        "budget_per_seed": int(budget_per_seed),
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
