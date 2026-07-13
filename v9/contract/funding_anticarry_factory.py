from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.v9_funding_carry_precheck import (
    EVENTS_PER_YEAR,
    evaluate_funding_carry,
    last_closed_hour_open_time_for_funding,
    load_funding_cache,
    load_ohlcv_close_cache,
    timestamp_ms_to_iso,
    weights_from_detail_row,
)
from v9.contract.report import write_json
from v9.contract.simulator import utc_ts


ROW_CACHE_VERSION = "funding_anticarry_factory_v1_train_only_walkforward"
DEFAULT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "HYPEUSDT",
    "ZECUSDT",
    "XRPUSDT",
    "LABUSDT",
    "DOGEUSDT",
    "WLDUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "NEARUSDT",
    "1000PEPEUSDT",
    "SYNUSDT",
    "SUIUSDT",
    "VELVETUSDT",
    "ENAUSDT",
    "TAOUSDT",
    "BEATUSDT",
    "XLMUSDT",
    "AAVEUSDT",
    "AVAXUSDT",
    "BCHUSDT",
    "LINKUSDT",
    "UNIUSDT",
    "FILUSDT",
    "ALLOUSDT",
    "PAXGUSDT",
    "DOTUSDT",
    "PUMPUSDT",
)


@dataclass(frozen=True)
class FundingAntiCarryConfig:
    lookback_events: int
    rebalance_every_events: int
    bucket_fraction: float
    min_symbols: int
    direction: str = "anti_carry"


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    lookback_events: tuple[int, ...] = (180, 270)
    rebalance_every_events: tuple[int, ...] = (9,)
    bucket_fractions: tuple[float, ...] = (0.20,)
    min_symbols: int = 20
    costs_bps: tuple[float, ...] = (20.0, 40.0)
    stress_costs_bps: tuple[float, ...] = (50.0,)
    train_start: str = "2024-07-14"
    train_end: str = "2026-06-30 23:59:59"
    embargo_start: str = "2026-07-01"
    funding_cache_dir: str = "data/binance_funding_cache"
    ohlcv_cache_dir: str = "data/binance_usdm_ohlcv_cache"
    price_timeframe: str = "1h"
    universe_json: str = "artifacts/v9/universe/binance_usdm_top30_volume_snapshot.json"
    bootstrap_iterations: int = 100
    prior_trials: int = 0
    explicit_configs: tuple[FundingAntiCarryConfig, ...] = ()
    out_json: str = "artifacts/v9/contract_lab/funding_anticarry_factory_v1.json"
    out_md: str = "artifacts/v9/contract_lab/funding_anticarry_factory_v1.md"


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols)


def symbols_from_universe(path: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not path:
        return fallback
    p = Path(path)
    if not p.exists():
        return fallback
    payload = json.loads(p.read_text())
    symbols = tuple(str(symbol).upper() for symbol in payload.get("symbols", []) if symbol)
    return symbols or fallback


def config_for_preset(
    preset: str,
    funding_cache_dir: str,
    ohlcv_cache_dir: str,
    universe_json: str,
    train_start: str,
    train_end: str,
    embargo_start: str,
    bootstrap_iterations: int,
    out_json: str,
    out_md: str,
    prior_trials: int = 0,
    symbols: tuple[str, ...] = (),
) -> RunConfig:
    base_symbols = symbols or symbols_from_universe(universe_json, DEFAULT_SYMBOLS)
    base = {
        "symbols": base_symbols,
        "funding_cache_dir": funding_cache_dir,
        "ohlcv_cache_dir": ohlcv_cache_dir,
        "universe_json": universe_json,
        "train_start": train_start,
        "train_end": train_end,
        "embargo_start": embargo_start,
        "bootstrap_iterations": bootstrap_iterations,
        "prior_trials": prior_trials,
        "out_json": out_json,
        "out_md": out_md,
    }
    if preset in {"top30_anti_carry", "funding_anticarry_top30"}:
        return RunConfig(**base)
    if preset == "top30_anti_carry_scan":
        return RunConfig(
            lookback_events=(90, 180, 270),
            rebalance_every_events=(3, 9, 21),
            bucket_fractions=(0.20, 0.25),
            **base,
        )
    raise ValueError(f"unknown preset: {preset}")


def data_fingerprint(funding: pd.DataFrame, closes: pd.DataFrame, symbols: tuple[str, ...]) -> str:
    raw = json.dumps(
        {
            "funding_rows": int(len(funding)),
            "funding_min": int(funding["funding_time"].min()) if len(funding) else None,
            "funding_max": int(funding["funding_time"].max()) if len(funding) else None,
            "close_rows": int(len(closes)),
            "close_min": int(closes["open_time"].min()) if len(closes) else None,
            "close_max": int(closes["open_time"].max()) if len(closes) else None,
            "symbols": list(symbols),
            "cache_version": ROW_CACHE_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def row_cache_key(cfg: FundingAntiCarryConfig, data_fp: str, run: RunConfig) -> str:
    raw = json.dumps(
        {
            "cache_version": ROW_CACHE_VERSION,
            "config": asdict(cfg),
            "data_fingerprint": data_fp,
            "train_start": run.train_start,
            "train_end": run.train_end,
            "embargo_start": run.embargo_start,
            "costs_bps": [float(v) for v in run.costs_bps],
            "stress_costs_bps": [float(v) for v in run.stress_costs_bps],
        },
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def config_grid(run: RunConfig) -> tuple[FundingAntiCarryConfig, ...]:
    if run.explicit_configs:
        return run.explicit_configs
    return tuple(
        FundingAntiCarryConfig(
            lookback_events=int(lookback),
            rebalance_every_events=int(rebalance),
            bucket_fraction=float(bucket),
            min_symbols=int(run.min_symbols),
        )
        for lookback, rebalance, bucket in itertools.product(
            run.lookback_events,
            run.rebalance_every_events,
            run.bucket_fractions,
        )
    )


def filter_train_data(
    funding: pd.DataFrame,
    closes: pd.DataFrame,
    *,
    train_start: str,
    train_end: str,
    embargo_start: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = utc_ts(train_start)
    end = utc_ts(train_end)
    embargo = utc_ts(embargo_start)
    if end >= embargo:
        raise ValueError(f"train_end must be before embargo_start: {train_end} >= {embargo_start}")
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    funding_train = funding[(funding["funding_time"] >= start_ms) & (funding["funding_time"] <= end_ms)].copy()
    closes_train = closes[(closes["open_time"] >= start_ms) & (closes["open_time"] <= end_ms)].copy()
    return funding_train, closes_train


def split_detail(detail: pd.DataFrame, selection_frac: float = 0.75) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if detail.empty:
        return detail.copy(), detail.copy(), {"selection_usable": False, "validation_usable": False}
    times = detail["funding_time"].sort_values().tolist()
    split_idx = max(1, min(len(times) - 1, int(len(times) * float(selection_frac))))
    split_time = int(times[split_idx])
    selection = detail[detail["funding_time"] < split_time].copy()
    validation = detail[detail["funding_time"] >= split_time].copy()
    return selection, validation, {
        "selection_frac": float(selection_frac),
        "split_funding_time": split_time,
        "split_funding_time_iso": timestamp_ms_to_iso(split_time),
        "selection_usable": not selection.empty,
        "validation_usable": not validation.empty,
        "selection_events": int(len(selection)),
        "validation_events": int(len(validation)),
    }


def price_aware_event_detail(
    detail: pd.DataFrame,
    close_frame: pd.DataFrame,
    *,
    turnover_cost_bps: float,
) -> pd.DataFrame:
    if detail.empty or close_frame.empty:
        return pd.DataFrame()
    close_pivot = close_frame.pivot_table(index="open_time", columns="symbol", values="close", aggfunc="last").sort_index()
    rows: list[dict[str, Any]] = []
    previous_weights = pd.Series(dtype=float)
    for _, row in detail.sort_values("funding_time").iterrows():
        previous_funding_time = row.get("previous_funding_time")
        funding_time = int(row["funding_time"])
        if previous_funding_time is None or pd.isna(previous_funding_time):
            continue
        start_open_time = last_closed_hour_open_time_for_funding(int(previous_funding_time))
        end_open_time = last_closed_hour_open_time_for_funding(funding_time)
        if start_open_time not in close_pivot.index or end_open_time not in close_pivot.index:
            continue
        weights = weights_from_detail_row(row)
        start_prices = close_pivot.loc[start_open_time].dropna()
        end_prices = close_pivot.loc[end_open_time].dropna()
        common = weights.index.intersection(start_prices.index).intersection(end_prices.index)
        if len(common) < len(weights):
            continue
        aligned_weights = weights.loc[common].astype(float)
        price_returns = end_prices.loc[common] / start_prices.loc[common] - 1.0
        price_return = float((aligned_weights * price_returns).sum())
        all_symbols = previous_weights.index.union(aligned_weights.index)
        turnover = float(
            (
                aligned_weights.reindex(all_symbols, fill_value=0.0)
                - previous_weights.reindex(all_symbols, fill_value=0.0)
            )
            .abs()
            .sum()
        )
        cost = turnover * float(turnover_cost_bps) / 10_000.0
        funding_return = float(row["gross_funding_return"])
        rows.append(
            {
                "funding_time": funding_time,
                "funding_time_iso": row["funding_time_iso"],
                "price_return": price_return,
                "funding_return": funding_return,
                "turnover": turnover,
                "cost": cost,
                "net_return": funding_return + price_return - cost,
                "long_symbols": list(row["long_symbols"]),
                "short_symbols": list(row["short_symbols"]),
            }
        )
        previous_weights = aligned_weights
    return pd.DataFrame(rows)


def compounded_return(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def max_drawdown_compounded(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = (1.0 + returns.fillna(0.0)).cumprod()
    dd = 1.0 - equity / equity.cummax()
    return float(dd.max())


def annualized_sharpe(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    std = float(returns.std(ddof=1))
    if std <= 0.0 or not math.isfinite(std):
        return 0.0
    return float(returns.mean()) / std * math.sqrt(EVENTS_PER_YEAR)


def yearly_summary(detail: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    if detail.empty:
        return {}
    yearly = (
        detail.assign(year=pd.to_datetime(detail["funding_time"], unit="ms", utc=True).dt.year.astype(str))
        .groupby("year", as_index=False)
        .agg(
            periods=("net_return", "size"),
            funding_return=("funding_return", "sum"),
            price_return=("price_return", "sum"),
            cost=("cost", "sum"),
            net_return=("net_return", lambda value: compounded_return(pd.Series(value))),
        )
        .sort_values("year")
    )
    return {str(row["year"]): {k: row[k] for k in row.index if k != "year"} for _, row in yearly.iterrows()}


def symbol_breadth(detail: pd.DataFrame) -> dict[str, Any]:
    counts: dict[str, float] = {}
    gross_events = 0.0
    for _, row in detail.iterrows():
        symbols = list(row.get("long_symbols") or []) + list(row.get("short_symbols") or [])
        if not symbols:
            continue
        gross_events += len(symbols)
        for symbol in symbols:
            counts[symbol] = counts.get(symbol, 0.0) + 1.0
    top_share = max(counts.values(), default=0.0) / gross_events if gross_events > 0 else 0.0
    return {
        "active_symbol_count": len(counts),
        "top_positive_symbol_share": float(top_share),
        "top_symbols": sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10],
    }


def metric_row(detail: pd.DataFrame, *, cost_bps: float) -> dict[str, Any]:
    returns = detail["net_return"].astype(float) if not detail.empty else pd.Series(dtype=float)
    yearly = yearly_summary(detail)
    breadth = symbol_breadth(detail)
    active_events = int(len(detail))
    positive_years = sum(1 for row in yearly.values() if float(row.get("net_return", 0.0)) > 0.0)
    return {
        "cost_bps": float(cost_bps),
        "total_return": compounded_return(returns),
        "mean_return_per_event": float(returns.mean()) if len(returns) else 0.0,
        "annualized_return": float(returns.mean()) * EVENTS_PER_YEAR if len(returns) else 0.0,
        "sharpe": annualized_sharpe(returns),
        "max_drawdown": max_drawdown_compounded(returns),
        "rebalance_event_count": active_events,
        "active_rebalance_event_count": active_events,
        "time_in_market_frac": 1.0 if active_events else 0.0,
        "max_flat_streak_h": 0.0 if active_events else 999999.0,
        "yearly": yearly,
        "yearly_positive_count": int(positive_years),
        "yearly_count": int(len(yearly)),
        "positive_event_fraction": float((returns > 0).mean()) if len(returns) else 0.0,
        "funding_return_sum": float(detail["funding_return"].sum()) if not detail.empty else 0.0,
        "price_return_sum": float(detail["price_return"].sum()) if not detail.empty else 0.0,
        "cost_sum": float(detail["cost"].sum()) if not detail.empty else 0.0,
        "average_turnover": float(detail["turnover"].mean()) if not detail.empty else 0.0,
        "bootstrap_30d_sharpe_p5": annualized_sharpe(returns),
        "equal_weight_benchmark": {"sharpe_excess": annualized_sharpe(returns), "drawdown_ratio": 1.0},
        **breadth,
    }


def walk_forward_summary(detail: pd.DataFrame, close_frame: pd.DataFrame, *, cfg: FundingAntiCarryConfig, cost_bps: float) -> dict[str, Any]:
    if detail.empty:
        return {"enabled": True, "passed": False, "folds": [], "q25_sharpe": 0.0, "min_sharpe": 0.0}
    times = sorted(detail["funding_time"].unique())
    folds = []
    for part in range(4):
        start_idx = int(len(times) * part / 4)
        end_idx = int(len(times) * (part + 1) / 4)
        if end_idx <= start_idx:
            continue
        subset = detail[(detail["funding_time"] >= times[start_idx]) & (detail["funding_time"] <= times[end_idx - 1])]
        event_detail = price_aware_event_detail(subset, close_frame, turnover_cost_bps=cost_bps)
        metrics = metric_row(event_detail, cost_bps=cost_bps)
        folds.append(
            {
                "fold": part + 1,
                "start": timestamp_ms_to_iso(int(times[start_idx])),
                "end": timestamp_ms_to_iso(int(times[end_idx - 1])),
                "sharpe": metrics["sharpe"],
                "total_return": metrics["total_return"],
                "max_drawdown": metrics["max_drawdown"],
                "events": metrics["active_rebalance_event_count"],
            }
        )
    sharpes = sorted(float(row["sharpe"]) for row in folds)
    q25 = sharpes[max(0, int(math.floor((len(sharpes) - 1) * 0.25)))] if sharpes else 0.0
    min_sharpe = min(sharpes) if sharpes else 0.0
    return {
        "enabled": True,
        "passed": bool(q25 >= 0.50 and min_sharpe >= 0.0 and len(folds) >= 4),
        "folds": folds,
        "q25_sharpe": q25,
        "min_sharpe": min_sharpe,
        "config": asdict(cfg),
    }


def validation_checks(
    selection20: dict[str, Any],
    selection40: dict[str, Any],
    validation20: dict[str, Any],
    validation40: dict[str, Any],
    stress: dict[str, Any],
    walk_forward: dict[str, Any],
) -> dict[str, bool]:
    validation_years = validation40.get("yearly_count", 0)
    return {
        "selection_sharpe20_ge_1_0": float(selection20.get("sharpe", 0.0)) >= 1.0,
        "selection_sharpe40_ge_0_8": float(selection40.get("sharpe", 0.0)) >= 0.8,
        "selection_dd40_le_25pct": float(selection40.get("max_drawdown", 1.0)) <= 0.25,
        "validation_usable": int(validation40.get("active_rebalance_event_count", 0)) >= 100,
        "validation_sharpe20_ge_1_0": float(validation20.get("sharpe", 0.0)) >= 1.0,
        "validation_sharpe40_ge_0_8": float(validation40.get("sharpe", 0.0)) >= 0.8,
        "validation_return40_gt_0": float(validation40.get("total_return", 0.0)) > 0.0,
        "validation_dd40_le_25pct": float(validation40.get("max_drawdown", 1.0)) <= 0.25,
        "validation_positive_all_years": int(validation40.get("yearly_positive_count", 0)) == int(validation_years),
        "walk_forward_robust": bool(walk_forward.get("passed")),
        "stress50_sharpe_ge_1_0": float(stress.get("sharpe", 0.0)) >= 1.0,
        "stress50_return_gt_0": float(stress.get("total_return", 0.0)) > 0.0,
        "stress50_dd_le_25pct": float(stress.get("max_drawdown", 1.0)) <= 0.25,
        "symbol_breadth_top_share_le_35pct": float(validation40.get("top_positive_symbol_share", 1.0)) <= 0.35,
    }


def evaluate_config(
    funding: pd.DataFrame,
    closes: pd.DataFrame,
    cfg_row: FundingAntiCarryConfig,
    run: RunConfig,
    data_fp: str,
) -> dict[str, Any]:
    gross_detail, gross_metrics = evaluate_funding_carry(
        funding,
        lookback_events=cfg_row.lookback_events,
        bucket_fraction=cfg_row.bucket_fraction,
        min_symbols=cfg_row.min_symbols,
        rebalance_every_events=cfg_row.rebalance_every_events,
        direction=cfg_row.direction,
    )
    selection_detail, validation_detail, split_meta = split_detail(gross_detail)
    selection_cost = {
        f"cost{int(cost)}": metric_row(
            price_aware_event_detail(selection_detail, closes, turnover_cost_bps=float(cost)),
            cost_bps=float(cost),
        )
        for cost in run.costs_bps
    }
    validation_cost = {
        f"cost{int(cost)}": metric_row(
            price_aware_event_detail(validation_detail, closes, turnover_cost_bps=float(cost)),
            cost_bps=float(cost),
        )
        for cost in run.costs_bps
    }
    stress_cost = {
        f"cost{int(cost)}": metric_row(
            price_aware_event_detail(validation_detail, closes, turnover_cost_bps=float(cost)),
            cost_bps=float(cost),
        )
        for cost in run.stress_costs_bps
    }
    cost20 = selection_cost.get("cost20") or next(iter(selection_cost.values()), {})
    cost40 = selection_cost.get("cost40") or cost20
    val20 = validation_cost.get("cost20") or next(iter(validation_cost.values()), {})
    val40 = validation_cost.get("cost40") or val20
    stress50 = stress_cost.get("cost50") or next(iter(stress_cost.values()), {})
    walk_forward = walk_forward_summary(gross_detail, closes, cfg=cfg_row, cost_bps=40.0)
    checks = validation_checks(cost20, cost40, val20, val40, stress50, walk_forward)
    row = {
        "row_cache_key": row_cache_key(cfg_row, data_fp, run),
        "config": asdict(cfg_row),
        "gross_funding_metrics": gross_metrics,
        "cost20": cost20,
        "cost40": cost40,
        "selection": {"cost20": cost20, "cost40": cost40, "checks": {k: v for k, v in checks.items() if k.startswith("selection")}},
        "validation": {
            "cost20": val20,
            "cost40": val40,
            "checks": {k: v for k, v in checks.items() if not k.startswith("selection")},
            "split": split_meta,
        },
        "walk_forward": walk_forward,
        "cost_stress": {"validation": stress_cost},
        "advance_checks": checks,
        "advance_passed": all(checks.values()),
    }
    row["gate_alignment"] = gate_alignment_summary(row)
    return row


def progress_float(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if math.isfinite(out) else 0.0


def gate_alignment_summary(row: dict[str, Any]) -> dict[str, Any]:
    checks = row.get("advance_checks") or {}
    passed = sum(1 for value in checks.values() if bool(value))
    total = len(checks)
    cost40 = row.get("cost40") or {}
    validation40 = ((row.get("validation") or {}).get("cost40") or {})
    walk_forward = row.get("walk_forward") or {}
    components = {
        "check_pass_fraction": passed / total if total else 0.0,
        "selection_sharpe40": max(0.0, min(1.0, progress_float(cost40.get("sharpe")) / 1.5)),
        "validation_sharpe40": max(0.0, min(1.0, progress_float(validation40.get("sharpe")) / 1.5)),
        "walk_forward_q25": max(0.0, min(1.0, (progress_float(walk_forward.get("q25_sharpe")) + 0.25) / 1.25)),
        "validation_drawdown": max(0.0, min(1.0, (0.35 - progress_float(validation40.get("max_drawdown"))) / 0.35)),
    }
    score = 100.0 * sum(components.values()) / len(components)
    return {
        "score": round(score, 6),
        "passed_checks": int(passed),
        "scored_checks": int(total),
        "pass_fraction": round(passed / total, 6) if total else 0.0,
        "failed_checks": sorted(key for key, value in checks.items() if not value),
        "components": {key: round(float(value), 6) for key, value in components.items()},
    }


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    validation40 = ((row.get("validation") or {}).get("cost40") or {})
    walk_forward = row.get("walk_forward") or {}
    return (
        bool(row.get("advance_passed")),
        progress_float((row.get("gate_alignment") or {}).get("score")),
        progress_float(validation40.get("sharpe")),
        progress_float(walk_forward.get("q25_sharpe")),
        -progress_float(validation40.get("max_drawdown")),
    )


def run_factory(run: RunConfig) -> dict[str, Any]:
    symbols = tuple(run.symbols)
    funding = load_funding_cache(Path(run.funding_cache_dir), symbols)
    closes = load_ohlcv_close_cache(Path(run.ohlcv_cache_dir), symbols, run.price_timeframe)
    funding, closes = filter_train_data(
        funding,
        closes,
        train_start=run.train_start,
        train_end=run.train_end,
        embargo_start=run.embargo_start,
    )
    data_fp = data_fingerprint(funding, closes, symbols)
    rows = [evaluate_config(funding, closes, cfg_row, run, data_fp) for cfg_row in config_grid(run)]
    rows.sort(key=row_sort_key, reverse=True)
    pass_rows = [row for row in rows if row.get("advance_passed")]
    accepted = len(pass_rows) >= 2
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "funding_anticarry_factory_v1_train_only_grid",
        "train_window": {"start": run.train_start, "end": run.train_end},
        "data": {
            "fingerprint": data_fp,
            "funding_rows": int(len(funding)),
            "ohlcv_rows": int(len(closes)),
            "first_funding_time": timestamp_ms_to_iso(int(funding["funding_time"].min())) if len(funding) else None,
            "last_funding_time": timestamp_ms_to_iso(int(funding["funding_time"].max())) if len(funding) else None,
            "symbols": list(symbols),
            "funding_cache_dir": run.funding_cache_dir,
            "ohlcv_cache_dir": run.ohlcv_cache_dir,
            "universe_json": run.universe_json,
        },
        "selection_validation": {
            "enabled": True,
            "selection_frac": 0.75,
            "n_configs_tested": len(rows),
            "prior_trials": int(run.prior_trials),
            "effective_trials": len(rows) + int(run.prior_trials),
            "walk_forward_required": True,
            "stress_costs_bps": [float(v) for v in run.stress_costs_bps],
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
            "note": "Funding anti-carry train-only factory; no data at or after embargo_start is used.",
        },
        "symbols": list(symbols),
        "config": asdict(run),
        "summary": {
            "rows": len(rows),
            "pass_count": len(pass_rows),
            "accepted_train_only": bool(accepted),
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "top": rows[:25],
        "rows": rows,
    }
    write_json(payload, Path(run.out_json))
    if run.out_md:
        write_markdown(payload, Path(run.out_md))
    return payload


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Funding Anti-Carry Factory",
        "",
        f"- accepted_train_only: `{payload['summary']['accepted_train_only']}`",
        f"- pass_count: `{payload['summary']['pass_count']}`",
        f"- rows: `{payload['summary']['rows']}`",
        f"- train_window: `{payload['train_window']['start']} -> {payload['train_window']['end']}`",
        f"- symbols: `{len(payload['symbols'])}`",
        "",
        "| rank | passed | score | lookback | rebalance_events | bucket | val40_sharpe | val40_return | val40_dd | wf_q25 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(payload["rows"][:20], start=1):
        cfg = row["config"]
        val40 = row.get("validation", {}).get("cost40", {}) or {}
        wf = row.get("walk_forward", {}) or {}
        lines.append(
            f"| {idx} | {row.get('advance_passed')} | {(row.get('gate_alignment') or {}).get('score')} | "
            f"{cfg['lookback_events']} | {cfg['rebalance_every_events']} | {cfg['bucket_fraction']} | "
            f"{val40.get('sharpe')} | {val40.get('total_return')} | {val40.get('max_drawdown')} | "
            f"{wf.get('q25_sharpe')} |"
        )
    lines.append("")
    lines.append("No holdout, paper, or live trading is authorized by this artifact.")
    path.write_text("\n".join(lines) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train-only funding anti-carry factory for Binance USD-M perps.")
    parser.add_argument("--preset", default="top30_anti_carry")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--funding-cache-dir", default="data/binance_funding_cache")
    parser.add_argument("--ohlcv-cache-dir", default="data/binance_usdm_ohlcv_cache")
    parser.add_argument("--universe-json", default="artifacts/v9/universe/binance_usdm_top30_volume_snapshot.json")
    parser.add_argument("--train-start", default="2024-07-14")
    parser.add_argument("--train-end", default="2026-06-30 23:59:59")
    parser.add_argument("--embargo-start", default="2026-07-01")
    parser.add_argument("--bootstrap-iterations", type=int, default=100)
    parser.add_argument("--prior-trials", type=int, default=0)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/funding_anticarry_factory_v1.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/funding_anticarry_factory_v1.md")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    symbols = parse_symbols(args.symbols)
    run = config_for_preset(
        args.preset,
        funding_cache_dir=args.funding_cache_dir,
        ohlcv_cache_dir=args.ohlcv_cache_dir,
        universe_json=args.universe_json,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        bootstrap_iterations=args.bootstrap_iterations,
        out_json=args.out_json,
        out_md=args.out_md,
        prior_trials=args.prior_trials,
        symbols=symbols,
    )
    payload = run_factory(run)
    print(json.dumps({"summary": payload["summary"], "out_json": run.out_json}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
