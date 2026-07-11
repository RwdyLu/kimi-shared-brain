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
DEFAULT_RESCUE_TOP_K = 8
DEFAULT_RESCUE_BUDGET_PER_SEED = 18
HOSTILE_YEAR_DEFENSIVE_PAIRS = (
    ("market_filter_h", "vol_target_ann"),
    ("market_confirm_h", "market_drawdown_limit"),
    ("market_filter_h", "market_drawdown_limit"),
    ("market_confirm_h", "vol_target_ann"),
)
ACCEPTED_TRAIN_ONLY_GENE_ORDER = (
    "score_mode",
    "k",
    "rebalance_h",
    "lookback_h",
    "vol_target_ann",
    "market_filter_h",
    "market_confirm_h",
    "market_drawdown_limit",
    "n_tranches",
    "drawdown_stop",
    "cooldown_h",
    "skip_h",
)
SEED_FAMILY_CONFIG_KEYS = (
    "score_mode",
    "lookback_h",
    "rebalance_h",
    "market_filter_h",
    "market_confirm_h",
)

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
ACTIVITY_FAILURES = frozenset({"active_rebalances40_ge_min", "time_in_market40_ge_min"})
REGIME_ROBUSTNESS_FAILURES = frozenset(
    {
        "positive_3_of_4_years",
        "bootstrap_p5_ge_adjusted_min",
        "sharpe40_ge_1",
        "sharpe20_ge_1_2",
        "benchmark_sharpe_excess_ge_0_10",
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


def rescue_seed_family_key(config: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(config.get(key) for key in SEED_FAMILY_CONFIG_KEYS)


def rescue_seed_family(config: dict[str, Any]) -> dict[str, Any]:
    return {key: config.get(key) for key in SEED_FAMILY_CONFIG_KEYS}


def yearly_returns(row: dict[str, Any]) -> dict[str, float]:
    cost20 = (row.get("selection") or {}).get("cost20") or row.get("cost20") or {}
    yearly = cost20.get("yearly") or {}
    return {str(name): safe_float(value.get("net_return")) for name, value in yearly.items() if isinstance(value, dict)}


def positive_year_count(row: dict[str, Any]) -> int:
    return sum(1 for value in yearly_returns(row).values() if value > 0.0)


def worst_year(row: dict[str, Any]) -> dict[str, Any]:
    returns = yearly_returns(row)
    if not returns:
        return {"bucket": None, "net_return": None}
    bucket, value = min(returns.items(), key=lambda item: item[1])
    return {"bucket": bucket, "net_return": value}


def worst_year_return(row: dict[str, Any]) -> float:
    return safe_float(worst_year(row).get("net_return"), -999.0)


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


def is_accepted_train_only_seed(row: dict[str, Any]) -> bool:
    return bool(row.get("advance_passed")) and valid_config(row.get("config") or {})


def accepted_train_only_sort_key(row: dict[str, Any]) -> tuple[float, ...]:
    return (
        selection_bootstrap_p5(row),
        validation_sharpe20(row),
        selection_sharpe20(row),
        benchmark_sharpe_excess(row),
        selection_sharpe40(row),
        float(positive_year_count(row)),
        worst_year_return(row),
        active_rebalances40(row),
        time_in_market40(row),
        -top_symbol_share(row),
    )


def near_miss_sort_key(row: dict[str, Any]) -> tuple[float, ...]:
    failures = rescue_relevant_failures(row)
    return (
        -float(len(failures)),
        float(positive_year_count(row)),
        worst_year_return(row),
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
    config = dict(row.get("config") or {})
    return {
        "source_index": int(source_index),
        "rescue_seed_type": seed_type,
        "rescue_seed_family": rescue_seed_family(config),
        "config": config,
        "config_fingerprint": config_fingerprint(config),
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
        "positive_year_count": positive_year_count(row),
        "yearly_returns": yearly_returns(row),
        "worst_year": worst_year(row),
        "worst_year_return": worst_year_return(row),
    }


def select_rescue_seeds(
    rows: list[dict[str, Any]],
    top_k: int = DEFAULT_RESCUE_TOP_K,
    diagnostic_q25_min: float = 0.50,
    diagnostic_sign_min: float = 0.75,
    allow_accepted_train_only: bool = True,
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

    accepted_rows = [
        (row, idx)
        for idx, row in enumerate(rows)
        if allow_accepted_train_only and is_accepted_train_only_seed(row)
    ]
    accepted_rows.sort(key=lambda item: accepted_train_only_sort_key(item[0]), reverse=True)

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

    def append_diverse_candidates(candidates: list[tuple[dict[str, Any], int]], seed_type: str) -> None:
        seen_families = {rescue_seed_family_key(seed.get("config") or {}) for seed in seeds}
        for prefer_new_family in (True, False):
            for row, idx in candidates:
                config = row.get("config") or {}
                fp = config_fingerprint(config)
                family_key = rescue_seed_family_key(config)
                if fp in seen_configs:
                    continue
                if prefer_new_family and family_key in seen_families:
                    continue
                seen_configs.add(fp)
                seen_families.add(family_key)
                seeds.append(seed_record(row, idx, seed_type=seed_type))
                if len(seeds) >= limit:
                    return

    append_diverse_candidates(accepted_rows, "accepted_train_only")
    if len(seeds) >= limit:
        return seeds

    append_diverse_candidates(diagnostic_rows, "diagnostic_walkforward")
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
    append_diverse_candidates(near_miss_rows, "near_miss_gate")
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


def numeric_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def order_numeric_neighbors(value: Any, candidates: list[Any], direction: str, zero_last: bool = False) -> list[Any]:
    current = numeric_value(value)
    if current is None:
        return candidates
    numeric_candidates = [(candidate, numeric_value(candidate)) for candidate in candidates]
    if any(number is None for _, number in numeric_candidates):
        return candidates
    rows = [(candidate, float(number)) for candidate, number in numeric_candidates if number is not None]
    zero_rows = [row for row in rows if row[1] == 0.0]
    nonzero_rows = [row for row in rows if not (zero_last and row[1] == 0.0)]
    if direction == "higher":
        primary = sorted((row for row in nonzero_rows if row[1] > current), key=lambda row: row[1] - current)
        secondary = sorted((row for row in nonzero_rows if row[1] < current), key=lambda row: current - row[1])
    elif direction == "lower":
        primary = sorted((row for row in nonzero_rows if row[1] < current), key=lambda row: current - row[1])
        secondary = sorted((row for row in nonzero_rows if row[1] > current), key=lambda row: row[1] - current)
    else:
        return candidates
    ordered = [candidate for candidate, _ in primary + secondary]
    if zero_last:
        ordered.extend(candidate for candidate, _ in zero_rows)
    return ordered


def rescue_mutation_bias(seed: dict[str, Any]) -> str:
    if seed.get("rescue_seed_type") == "accepted_train_only":
        return "multiplicity_hardening"
    failures = set(seed.get("rescue_relevant_failures") or seed.get("failed_checks") or [])
    worst = seed.get("worst_year") or {}
    if failures.intersection(ACTIVITY_FAILURES):
        return "activity_unblock"
    if failures.intersection(REGIME_ROBUSTNESS_FAILURES) and safe_float(worst.get("net_return")) < 0.0:
        return "hostile_year_defensive"
    return "balanced_neighbor"


def prioritized_neighbor_values(seed: dict[str, Any], gene: str, radius: int = 2) -> list[Any]:
    base = dict(seed["config"])
    values = nearby_values(base.get(gene), GENE_LADDERS[gene], radius=radius)
    bias = rescue_mutation_bias(seed)
    if bias == "activity_unblock":
        if gene in {"cooldown_h", "market_confirm_h", "market_filter_h", "lookback_h", "rebalance_h"}:
            return order_numeric_neighbors(base.get(gene), values, "lower")
        if gene in {"market_drawdown_limit", "drawdown_stop"}:
            return order_numeric_neighbors(base.get(gene), values, "higher")
    if bias == "hostile_year_defensive":
        if gene in {"market_filter_h", "market_confirm_h", "cooldown_h", "lookback_h", "rebalance_h"}:
            return order_numeric_neighbors(base.get(gene), values, "higher")
        if gene in {"vol_target_ann", "drawdown_stop", "market_drawdown_limit"}:
            return order_numeric_neighbors(base.get(gene), values, "lower", zero_last=True)
        if gene == "n_tranches":
            return order_numeric_neighbors(base.get(gene), values, "higher")
    if bias == "multiplicity_hardening":
        if gene in {"vol_target_ann", "drawdown_stop", "market_drawdown_limit"}:
            return order_numeric_neighbors(base.get(gene), values, "lower", zero_last=True)
        if gene in {"market_filter_h", "market_confirm_h", "rebalance_h", "lookback_h"}:
            return order_numeric_neighbors(base.get(gene), values, "higher")
        if gene == "n_tranches":
            return order_numeric_neighbors(base.get(gene), values, "higher")
    return values


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
    limit = max(0, int(budget))
    if limit <= 0:
        return neighbors

    mutation_bias = rescue_mutation_bias(seed)
    if mutation_bias == "multiplicity_hardening":
        ordered_genes = [gene for gene in ACCEPTED_TRAIN_ONLY_GENE_ORDER if gene in base and gene in GENE_LADDERS]
    else:
        ordered_genes = [gene for gene in rescue_gene_order(failures) if gene in base and gene in GENE_LADDERS]
    if mutation_bias == "hostile_year_defensive" and limit > 5:
        single_budget = max(1, int(limit / 3))
    else:
        single_budget = limit if limit <= 5 else max(1, int(limit * 2 / 3))

    def append_neighbor(changes: list[tuple[str, Any]]) -> bool:
        candidate = dict(base)
        for gene, value in changes:
            candidate[gene] = value
        fp = config_fingerprint(candidate)
        if fp in seen:
            return False
        seen.add(fp)
        change_rows = [{"gene": gene, "from": base[gene], "to": value} for gene, value in changes]
        neighbors.append(
            {
                "parent_source_index": seed["source_index"],
                "parent_config_fingerprint": seed["config_fingerprint"],
                "changed_gene": "+".join(gene for gene, _ in changes),
                "changed_genes": [gene for gene, _ in changes],
                "mutation_bias": mutation_bias,
                "from": change_rows[0]["from"],
                "to": change_rows[0]["to"],
                "changes": change_rows,
                "config_fingerprint": fp,
                "config": candidate,
            }
        )
        return True

    for gene in ordered_genes:
        for value in prioritized_neighbor_values(seed, gene, radius=radius):
            append_neighbor([(gene, value)])
            if len(neighbors) >= single_budget:
                break
        if len(neighbors) >= single_budget:
            break

    if len(neighbors) >= limit:
        return neighbors

    pair_genes = ordered_genes[:7] if mutation_bias == "hostile_year_defensive" else ordered_genes[:5]
    pair_radius = min(1, max(1, int(radius)))
    pair_gene_groups: list[tuple[str, str]] = []
    if mutation_bias == "hostile_year_defensive":
        pair_gene_groups.extend(
            (left, right)
            for left, right in HOSTILE_YEAR_DEFENSIVE_PAIRS
            if left in pair_genes and right in pair_genes
        )
    pair_gene_groups.extend(
        (left_gene, right_gene)
        for left_pos, left_gene in enumerate(pair_genes)
        for right_gene in pair_genes[left_pos + 1 :]
    )
    seen_pair_groups: set[tuple[str, str]] = set()
    for left_gene, right_gene in pair_gene_groups:
        pair_key = tuple(sorted((left_gene, right_gene)))
        if pair_key in seen_pair_groups:
            continue
        seen_pair_groups.add(pair_key)
        left_values = prioritized_neighbor_values(seed, left_gene, radius=pair_radius)
        right_values = prioritized_neighbor_values(seed, right_gene, radius=pair_radius)
        for left_value in left_values:
            for right_value in right_values:
                append_neighbor([(left_gene, left_value), (right_gene, right_value)])
                if len(neighbors) >= limit:
                    return neighbors
    return neighbors


def build_rescue_plan(
    rows: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    source_artifact: str | None = None,
    top_k: int = DEFAULT_RESCUE_TOP_K,
    budget_per_seed: int = DEFAULT_RESCUE_BUDGET_PER_SEED,
    generation: int = 1,
    excluded_fingerprints: set[str] | frozenset[str] | None = None,
    parent_failure_count_by_config_fingerprint: dict[str, int] | None = None,
    allow_accepted_train_only: bool = True,
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
        allow_accepted_train_only=allow_accepted_train_only,
        allow_near_miss=allow_near_miss,
        near_miss_max_failures=near_miss_max_failures,
        near_miss_min_selection_sharpe20=near_miss_min_selection_sharpe20,
        near_miss_min_bootstrap_p5=near_miss_min_bootstrap_p5,
        near_miss_min_active_rebalances40=near_miss_min_active_rebalances40,
        near_miss_min_time_in_market40=near_miss_min_time_in_market40,
    )
    parent_failure_count_by_config_fingerprint = parent_failure_count_by_config_fingerprint or {}
    generation_int = int(generation)
    if generation_int >= 2 and parent_failure_count_by_config_fingerprint:
        seeds = [
            seed
            for seed in seeds
            if seed["config_fingerprint"] in parent_failure_count_by_config_fingerprint
            and int(seed["rescue_relevant_failure_count"])
            < int(parent_failure_count_by_config_fingerprint[seed["config_fingerprint"]])
        ]
    configs: list[dict[str, Any]] = []
    excluded_fingerprints = excluded_fingerprints or frozenset()
    seen_configs: set[str] = {str(fp) for fp in excluded_fingerprints}
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
    accepted_train_only_seed_count = sum(
        1 for seed in planned_seeds if seed.get("rescue_seed_type") == "accepted_train_only"
    )
    diagnostic_seed_count = sum(1 for seed in planned_seeds if seed.get("rescue_seed_type") == "diagnostic_walkforward")
    near_miss_seed_count = sum(1 for seed in planned_seeds if seed.get("rescue_seed_type") == "near_miss_gate")
    seed_family_count = len({tuple((seed.get("rescue_seed_family") or {}).items()) for seed in planned_seeds})
    return {
        "kind": "xsec_diagnostic_or_nearmiss_rescue_plan_v2",
        "source_artifact": source_artifact,
        "source_meta": meta,
        "rescue_generation": generation_int,
        "seed_count": len(planned_seeds),
        "accepted_train_only_seed_count": accepted_train_only_seed_count,
        "diagnostic_seed_count": diagnostic_seed_count,
        "near_miss_seed_count": near_miss_seed_count,
        "seed_family_count": seed_family_count,
        "rescue_config_count": len(configs),
        "budget_per_seed": int(budget_per_seed),
        "excluded_config_fingerprint_count": len(excluded_fingerprints),
        "parent_failure_filter": {
            "enabled": generation_int >= 2 and bool(parent_failure_count_by_config_fingerprint),
            "parent_config_count": len(parent_failure_count_by_config_fingerprint),
            "require_relevant_failure_count_improvement": generation_int >= 2,
        },
        "rescue_seed_policy": {
            "diagnostic_q25_min": 0.50,
            "diagnostic_sign_min": 0.75,
            "allow_accepted_train_only": bool(allow_accepted_train_only),
            "allow_near_miss": bool(allow_near_miss),
            "near_miss_max_failures": int(near_miss_max_failures),
            "near_miss_min_selection_sharpe20": float(near_miss_min_selection_sharpe20),
            "near_miss_min_bootstrap_p5": float(near_miss_min_bootstrap_p5),
            "near_miss_min_active_rebalances40": float(near_miss_min_active_rebalances40),
            "near_miss_min_time_in_market40": float(near_miss_min_time_in_market40),
            "ignored_failures": sorted(RESCUE_IGNORED_FAILURES),
            "hard_reject_failures": sorted(RESCUE_HARD_REJECT_FAILURES),
            "seed_family_config_keys": list(SEED_FAMILY_CONFIG_KEYS),
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
        "accepted_train_only_seed_count": int(plan.get("accepted_train_only_seed_count") or 0),
        "diagnostic_seed_count": int(plan.get("diagnostic_seed_count") or 0),
        "near_miss_seed_count": int(plan.get("near_miss_seed_count") or 0),
        "prior_effective_trials": int(plan.get("prior_effective_trials") or 0),
        "effective_trials_after_rescue": int(plan.get("effective_trials_after_rescue") or 0),
    }
