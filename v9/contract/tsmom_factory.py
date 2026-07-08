from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .metrics import max_drawdown
from .report import write_json
from .simulator import utc_ts
from .xsec_momentum import load_close_matrix, sharpe


DEFAULT_SYMBOLS = (
    "ADAUSDT",
    "AVAXUSDT",
    "BNBUSDT",
    "BTCUSDT",
    "ETHUSDT",
    "LINKUSDT",
    "SOLUSDT",
    "XRPUSDT",
)


@dataclass(frozen=True)
class TsmomConfig:
    asset_vol_target_ann: float
    portfolio_vol_target_ann: float
    no_trade_band: float
    vote_threshold: float = 0.50
    market_filter_h: int = 0
    market_off_scale: float = 0.0
    drawdown_stop: float = 0.0
    cooldown_h: int = 0


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    lookbacks_h: tuple[int, ...] = (720, 1440, 2160, 4320)
    asset_vol_targets_ann: tuple[float, ...] = (0.30, 0.40)
    portfolio_vol_targets_ann: tuple[float, ...] = (0.10, 0.15)
    no_trade_bands: tuple[float, ...] = (0.05, 0.10)
    vote_thresholds: tuple[float, ...] = (0.50,)
    market_filters_h: tuple[int, ...] = (0,)
    drawdown_stops: tuple[float, ...] = (0.0,)
    cooldowns_h: tuple[int, ...] = (0,)
    preset_configs: tuple[TsmomConfig, ...] | None = None
    costs_bps: tuple[float, ...] = (20.0, 40.0)
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    bootstrap_iterations: int = 500
    prior_trials: int = 0
    out_json: str = "artifacts/v9/contract_lab/tsmom_factory_v1.json"
    out_md: str = "artifacts/v9/contract_lab/tsmom_factory_v1.md"


ROW_CACHE_VERSION = "tsmom_factory_v1_train_only"


def config_for_preset(
    preset: str,
    cache_dir: str,
    train_start: str,
    train_end: str,
    embargo_start: str,
    bootstrap_iterations: int,
    out_json: str,
    out_md: str,
    prior_trials: int = 0,
) -> RunConfig:
    base = {
        "cache_dir": cache_dir,
        "train_start": train_start,
        "train_end": train_end,
        "embargo_start": embargo_start,
        "bootstrap_iterations": bootstrap_iterations,
        "prior_trials": prior_trials,
        "out_json": out_json,
        "out_md": out_md,
    }
    if preset == "core":
        return RunConfig(**base)
    if preset == "defensive_regime":
        return RunConfig(
            preset_configs=defensive_regime_configs(),
            **base,
        )
    raise ValueError(f"unknown preset: {preset}")


def defensive_regime_configs() -> tuple[TsmomConfig, ...]:
    base = TsmomConfig(0.35, 0.12, 0.10)
    return (
        base,
        TsmomConfig(0.35, 0.08, 0.10),
        TsmomConfig(0.25, 0.12, 0.10),
        TsmomConfig(0.35, 0.12, 0.10, vote_threshold=0.625),
        TsmomConfig(0.35, 0.12, 0.10, vote_threshold=0.75),
        TsmomConfig(0.35, 0.12, 0.25),
        TsmomConfig(0.35, 0.12, 0.10, market_filter_h=720, market_off_scale=0.50),
        TsmomConfig(0.35, 0.12, 0.10, market_filter_h=1440, market_off_scale=0.50),
        TsmomConfig(0.35, 0.12, 0.10, market_filter_h=2160, market_off_scale=0.50),
        TsmomConfig(0.35, 0.12, 0.10, drawdown_stop=0.20, cooldown_h=480),
        TsmomConfig(0.35, 0.12, 0.10, drawdown_stop=0.15, cooldown_h=336),
        TsmomConfig(0.35, 0.08, 0.10, vote_threshold=0.625),
        TsmomConfig(0.35, 0.08, 0.10, market_filter_h=720, market_off_scale=0.50),
        TsmomConfig(0.35, 0.08, 0.10, drawdown_stop=0.20, cooldown_h=480),
        TsmomConfig(0.35, 0.12, 0.25, vote_threshold=0.625),
        TsmomConfig(0.25, 0.08, 0.10, vote_threshold=0.625),
    )


def price_frame(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.drop(columns=["dt"])


def vote_fraction_matrix(closes: pd.DataFrame, lookbacks_h: tuple[int, ...]) -> pd.DataFrame:
    prices = price_frame(closes)
    votes = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    for lookback in lookbacks_h:
        momentum_positive = (prices / prices.shift(lookback) - 1.0) > 0.0
        above_sma = prices > prices.rolling(lookback, min_periods=lookback).mean()
        votes = votes + momentum_positive.astype(float) + above_sma.astype(float)
    return votes / float(2 * len(lookbacks_h))


def asset_vol_scale_matrix(closes: pd.DataFrame, asset_vol_target_ann: float, lookback_h: int = 720) -> pd.DataFrame:
    prices = price_frame(closes)
    ratios = prices / prices.shift(1)
    log_ret = ratios.apply(lambda col: np.log(col.where(col > 0.0)))
    ewma_var = log_ret.pow(2.0).ewm(span=lookback_h, adjust=False).mean()
    ann_vol = ewma_var.pow(0.5) * math.sqrt(365.0 * 24.0)
    scale = asset_vol_target_ann / ann_vol.replace(0.0, pd.NA)
    return scale.clip(lower=0.0, upper=1.0).fillna(1.0)


def target_weights_from_votes(vote_row: pd.Series, asset_scale_row: pd.Series, threshold: float = 0.50) -> dict[str, float]:
    raw = {}
    for sym in vote_row.index:
        vote = float(vote_row[sym])
        scale = float(asset_scale_row.get(sym, 1.0))
        raw[sym] = vote * max(0.0, min(1.0, scale)) if vote >= threshold else 0.0
    gross = sum(raw.values())
    if gross <= 0.0 or not math.isfinite(gross):
        return {sym: 0.0 for sym in vote_row.index}
    return {sym: raw[sym] / gross for sym in vote_row.index}


def market_regime_series(closes: pd.DataFrame, market_filter_h: int) -> pd.Series:
    if market_filter_h <= 0:
        return pd.Series([True] * len(closes), index=closes.index)
    prices = price_frame(closes)
    market = prices.mean(axis=1)
    trend = market > market.rolling(market_filter_h, min_periods=market_filter_h).mean()
    momentum = (market / market.shift(market_filter_h) - 1.0) > 0.0
    return (trend & momentum).fillna(False)


def portfolio_exposure_scale(past_returns: list[float], vol_target_ann: float, lookback_h: int = 720) -> float:
    if vol_target_ann <= 0.0 or len(past_returns) < lookback_h:
        return 1.0
    recent = pd.Series(past_returns[-lookback_h:])
    ewma_var = float(recent.pow(2.0).ewm(span=lookback_h, adjust=False).mean().iloc[-1])
    if ewma_var <= 0.0 or not math.isfinite(ewma_var):
        return 1.0
    ann_vol = math.sqrt(ewma_var) * math.sqrt(365.0 * 24.0)
    if ann_vol <= 0.0 or not math.isfinite(ann_vol):
        return 1.0
    return max(0.25, min(1.0, vol_target_ann / ann_vol))


def max_drawdown_from_returns(returns: pd.Series, initial: float = 10_000.0) -> float:
    equity = initial
    curve = []
    for ret in returns:
        equity *= 1.0 + float(ret)
        curve.append(equity)
    return float(max_drawdown(curve))


def annual_bucket(ts: pd.Timestamp) -> str:
    if ts.year <= 2021:
        return "2021"
    if ts.year >= 2024:
        return "2024H1"
    return str(ts.year)


def data_fingerprint(closes: pd.DataFrame) -> str:
    symbols = [c for c in closes.columns if c != "dt"]
    h = hashlib.sha1()
    h.update(json.dumps(symbols, sort_keys=True).encode("utf-8"))
    h.update(pd.to_datetime(closes["dt"]).astype("int64").to_numpy().tobytes())
    h.update(np.ascontiguousarray(closes[symbols].to_numpy(dtype="float64")).tobytes())
    return h.hexdigest()


def bootstrap_seed(
    cfg: TsmomConfig,
    lookbacks_h: tuple[int, ...],
    cost_bps: float,
    segment: str,
    train_start: str,
    train_end: str,
) -> int:
    raw = json.dumps(
        {
            "cfg": asdict(cfg),
            "lookbacks_h": [int(v) for v in lookbacks_h],
            "cost_bps": float(cost_bps),
            "segment": segment,
            "train_start": train_start,
            "train_end": train_end,
        },
        sort_keys=True,
    )
    return int(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8], 16)


def block_bootstrap_p5(daily_returns: pd.Series, iterations: int = 500, block_days: int = 30, seed: int = 20260708) -> float:
    values = [float(v) for v in daily_returns.dropna()]
    if len(values) < block_days * 2 or iterations <= 0:
        return 0.0
    rng = random.Random(seed)
    max_start = max(1, len(values) - block_days + 1)
    samples = []
    for _ in range(iterations):
        sample: list[float] = []
        while len(sample) < len(values):
            start = rng.randrange(max_start)
            sample.extend(values[start : start + block_days])
        samples.append(sharpe(pd.Series(sample[: len(values)]), 365.0))
    samples.sort()
    return float(samples[int(0.05 * (len(samples) - 1))])


def simulate(
    closes: pd.DataFrame,
    cfg: TsmomConfig,
    lookbacks_h: tuple[int, ...],
    cost_bps: float,
    bootstrap_iterations: int = 500,
    bootstrap_seed_value: int = 20260708,
) -> dict[str, Any]:
    symbols = [c for c in closes.columns if c != "dt"]
    votes = vote_fraction_matrix(closes, lookbacks_h)
    asset_scales = asset_vol_scale_matrix(closes, cfg.asset_vol_target_ann)
    market_allowed = market_regime_series(closes, cfg.market_filter_h)
    returns = closes[symbols].pct_change().shift(-1)
    weights = {sym: 0.0 for sym in symbols}
    rows = []
    rebalances = []
    symbol_returns = {sym: 0.0 for sym in symbols}
    past_returns: list[float] = []
    exposure_scale_sum = 0.0
    exposure_scale_count = 0
    equity = 1.0
    peak_equity = 1.0
    risk_off_until = -1
    risk_off_event_count = 0
    market_filter_on_count = 0
    market_filter_off_count = 0

    for idx in range(len(closes) - 1):
        ts = pd.Timestamp(closes["dt"].iloc[idx])
        current_drawdown = 1.0 - equity / peak_equity if peak_equity > 0.0 else 0.0
        if cfg.drawdown_stop > 0.0 and idx >= risk_off_until and current_drawdown >= cfg.drawdown_stop:
            risk_off_until = idx + max(1, int(cfg.cooldown_h))
            risk_off_event_count += 1
        forced_exit = idx < risk_off_until and sum(abs(v) for v in weights.values()) > 0.0
        if idx % 24 == 0 or forced_exit:
            allow_market = bool(market_allowed.iloc[idx])
            if idx % 24 == 0:
                market_filter_on_count += int(allow_market)
                market_filter_off_count += int(not allow_market)
            risk_off = idx < risk_off_until
            if risk_off:
                base = {sym: 0.0 for sym in symbols}
            else:
                base = target_weights_from_votes(votes.iloc[idx], asset_scales.iloc[idx], threshold=cfg.vote_threshold)
                if not allow_market:
                    base = {sym: weight * max(0.0, min(1.0, cfg.market_off_scale)) for sym, weight in base.items()}
            scale = portfolio_exposure_scale(past_returns, cfg.portfolio_vol_target_ann)
            target = {sym: base[sym] * scale for sym in symbols}
            turnover = sum(abs(target[sym] - weights[sym]) for sym in symbols)
            must_exit = sum(abs(v) for v in target.values()) == 0.0 and sum(abs(v) for v in weights.values()) > 0.0
            if turnover > 0.0 and (turnover >= cfg.no_trade_band or must_exit or forced_exit):
                weights = target
                cost = turnover * cost_bps / 10000.0
                exposure_scale_sum += scale
                exposure_scale_count += 1
                rebalances.append(
                    {
                        "dt": ts,
                        "turnover": turnover,
                        "cost": cost,
                        "gross_exposure": sum(abs(v) for v in weights.values()),
                    }
                )
            else:
                turnover = 0.0
                cost = 0.0
        else:
            cost = 0.0
        row_rets = returns.iloc[idx].fillna(0.0)
        gross = 0.0
        for sym in symbols:
            value = weights[sym] * float(row_rets[sym])
            gross += value
            symbol_returns[sym] += value
        net = gross - cost
        equity *= 1.0 + net
        peak_equity = max(peak_equity, equity)
        rows.append(
            {
                "dt": ts,
                "net_return": net,
                "gross_return": gross,
                "cost": cost,
                "gross_exposure": sum(abs(v) for v in weights.values()),
                "market_allowed": bool(market_allowed.iloc[idx]),
                "risk_off": bool(idx < risk_off_until),
            }
        )
        past_returns.append(net)

    ret = pd.DataFrame(rows).set_index("dt")
    reb = pd.DataFrame(rebalances).set_index("dt") if rebalances else pd.DataFrame(columns=["turnover", "cost", "gross_exposure"])
    period_returns = (1.0 + ret["net_return"]).resample("1D").prod() - 1.0
    daily_returns = period_returns
    total_return = float((1.0 + ret["net_return"]).prod() - 1.0)
    dd = max_drawdown_from_returns(ret["net_return"])
    period_sharpe = sharpe(period_returns, 365.0)
    by_year = {}
    for bucket in ["2021", "2022", "2023", "2024H1"]:
        subset = period_returns[[annual_bucket(ts) == bucket for ts in period_returns.index]]
        by_year[bucket] = {
            "periods": int(len(subset)),
            "net_return": float((1.0 + subset).prod() - 1.0) if len(subset) else 0.0,
            "sharpe": sharpe(subset, 365.0) if len(subset) else 0.0,
        }
    symbol_pnl = {sym: float(value * 10_000.0) for sym, value in symbol_returns.items()}
    positive_symbol_count = sum(1 for value in symbol_pnl.values() if value > 0.0)
    positives = [max(v, 0.0) for v in symbol_pnl.values()]
    top_symbol_share = max(positives) / sum(positives) if sum(positives) > 0 else 0.0
    equal_weight = returns.mean(axis=1).iloc[: len(ret)].fillna(0.0)
    equal_weight.index = ret.index
    ew_daily_returns = (1.0 + equal_weight).resample("1D").prod() - 1.0
    ew_sharpe = sharpe(ew_daily_returns, 365.0)
    ew_dd = max_drawdown_from_returns(equal_weight)
    bootstrap_p5 = block_bootstrap_p5(daily_returns, iterations=bootstrap_iterations, seed=bootstrap_seed_value)
    active_yearly_bucket_count = sum(1 for row in by_year.values() if int(row["periods"]) > 0)
    positive_active_yearly_bucket_count = sum(
        1 for row in by_year.values() if int(row["periods"]) > 0 and float(row["net_return"]) > 0.0
    )
    yearly_positive = sum(1 for row in by_year.values() if row["net_return"] > 0)
    return {
        "config": asdict(cfg),
        "lookbacks_h": [int(v) for v in lookbacks_h],
        "cost_bps": float(cost_bps),
        "total_return": total_return,
        "net_pnl": float(total_return * 10_000.0),
        "sharpe": period_sharpe,
        "max_drawdown": dd,
        "daily_turnover": float(reb["turnover"].resample("1D").sum().mean()) if len(reb) else 0.0,
        "avg_gross_exposure": float(ret["gross_exposure"].mean()) if len(ret) else 0.0,
        "avg_portfolio_exposure_scale": float(exposure_scale_sum / exposure_scale_count) if exposure_scale_count else 1.0,
        "rebalance_event_count": int(len(reb)),
        "risk_off_event_count": int(risk_off_event_count),
        "risk_off_days": float(ret["risk_off"].resample("1D").max().sum()) if len(ret) else 0.0,
        "market_filter_on_count": int(market_filter_on_count),
        "market_filter_off_count": int(market_filter_off_count),
        "yearly": by_year,
        "yearly_positive_count": yearly_positive,
        "active_yearly_bucket_count": int(active_yearly_bucket_count),
        "positive_active_yearly_bucket_count": int(positive_active_yearly_bucket_count),
        "symbol_pnl": symbol_pnl,
        "symbol_count": int(len(symbols)),
        "positive_symbol_count": int(positive_symbol_count),
        "top_positive_symbol_share": float(top_symbol_share),
        "bootstrap_30d_sharpe_p5": bootstrap_p5,
        "bootstrap_seed": int(bootstrap_seed_value),
        "bootstrap_iterations": int(bootstrap_iterations),
        "equal_weight_benchmark": {
            "sharpe": ew_sharpe,
            "max_drawdown": ew_dd,
            "sharpe_excess": period_sharpe - ew_sharpe,
            "drawdown_ratio": dd / ew_dd if ew_dd > 0 else 1.0,
        },
    }


def breadth_min(symbol_count: int) -> int:
    return min(6, max(1, math.ceil(symbol_count * 2.0 / 3.0)))


def bootstrap_threshold(n_trials: int, base: float = 0.25) -> float:
    return base + 0.05 * math.log10(max(1, int(n_trials)))


def validation_sharpe_threshold(effective_trials: int, base: float = 0.70, slope: float = 0.10) -> float:
    return base + slope * max(0.0, math.log10(max(1, int(effective_trials))) - 1.0)


def advance_checks(cost20: dict[str, Any], cost40: dict[str, Any], bootstrap_p5_min: float = 0.25) -> dict[str, bool]:
    benchmark = cost20["equal_weight_benchmark"]
    active_buckets = int(cost20.get("active_yearly_bucket_count") or 0)
    positive_active_buckets = int(cost20.get("positive_active_yearly_bucket_count") or 0)
    required_positive_active = max(2, math.ceil(active_buckets * 0.75)) if active_buckets >= 2 else 2
    return {
        "sharpe20_ge_1_0": float(cost20["sharpe"]) >= 1.0,
        "max_dd20_le_30pct": float(cost20["max_drawdown"]) <= 0.30,
        "active_yearly_buckets_ge_2": active_buckets >= 2,
        "positive_active_yearly_buckets_ge_75pct": positive_active_buckets >= required_positive_active,
        "return_2024h1_gt_minus_2pct": float(cost20["yearly"]["2024H1"]["net_return"]) > -0.02,
        "bootstrap_p5_ge_adjusted_min": float(cost20["bootstrap_30d_sharpe_p5"]) >= bootstrap_p5_min,
        "sharpe40_ge_0_5": float(cost40["sharpe"]) >= 0.5,
        "breadth_positive_symbols_ge_min": int(cost20["positive_symbol_count"]) >= breadth_min(int(cost20["symbol_count"])),
        "top_symbol_share_le_70pct": float(cost20["top_positive_symbol_share"]) <= 0.70,
        "benchmark_sharpe_excess_ge_0": float(benchmark["sharpe_excess"]) >= 0.0,
        "drawdown_ratio_le_1_0": float(benchmark["drawdown_ratio"]) <= 1.0,
        "daily_turnover_le_50pct": float(cost20["daily_turnover"]) <= 0.50,
    }


def validation_checks(cost20: dict[str, Any], cost40: dict[str, Any], sharpe20_min: float = 0.70) -> dict[str, bool]:
    active_buckets = int(cost20.get("active_yearly_bucket_count") or 0)
    positive_active_buckets = int(cost20.get("positive_active_yearly_bucket_count") or 0)
    required_positive_active = max(1, math.ceil(active_buckets * 0.50)) if active_buckets >= 1 else 1
    return {
        "validation_sharpe20_ge_adjusted_min": float(cost20["sharpe"]) >= sharpe20_min,
        "validation_max_dd20_le_35pct": float(cost20["max_drawdown"]) <= 0.35,
        "validation_return20_gt_0": float(cost20["total_return"]) > 0.0,
        "validation_sharpe40_gt_0": float(cost40["sharpe"]) > 0.0,
        "validation_positive_active_yearly_buckets_ge_50pct": positive_active_buckets >= required_positive_active,
        "validation_breadth_positive_symbols_ge_min": int(cost20["positive_symbol_count"]) >= breadth_min(int(cost20["symbol_count"])),
    }


def drop_one_lookback_summary(
    closes: pd.DataFrame,
    cfg: TsmomConfig,
    lookbacks_h: tuple[int, ...],
    ensemble_sharpe20: float,
) -> dict[str, Any]:
    rows = []
    threshold = max(1.0, 0.90 * float(ensemble_sharpe20))
    for dropped in lookbacks_h:
        remaining = tuple(v for v in lookbacks_h if v != dropped)
        if len(remaining) < 2:
            continue
        result = simulate(closes, cfg, remaining, 20.0, bootstrap_iterations=0)
        rows.append(
            {
                "dropped_lookback_h": int(dropped),
                "remaining_lookbacks_h": [int(v) for v in remaining],
                "sharpe20": float(result["sharpe"]),
                "total_return20": float(result["total_return"]),
                "max_drawdown20": float(result["max_drawdown"]),
                "passed": float(result["sharpe"]) >= threshold and float(result["total_return"]) > 0.0,
            }
        )
    return {
        "enabled": True,
        "threshold_sharpe20": float(threshold),
        "rows": rows,
        "passed": bool(rows and all(row["passed"] for row in rows)),
        "note": "Train-only drop-one-lookback stability check; it does not authorize holdout, paper trading, or live trading.",
    }


def split_selection_validation(closes: pd.DataFrame, cfg: RunConfig, selection_frac: float = 0.60) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not 0.50 <= selection_frac <= 0.90:
        raise ValueError("selection_frac must be between 0.50 and 0.90")
    split_idx = max(1, min(len(closes) - 2, int(len(closes) * selection_frac)))
    split_dt = pd.Timestamp(closes["dt"].iloc[split_idx])
    purge_h = max(int(max(cfg.lookbacks_h)), 24)
    validation_start = split_dt + pd.Timedelta(hours=purge_h)
    selection = closes.loc[closes["dt"] <= split_dt].copy().reset_index(drop=True)
    validation = closes.loc[closes["dt"] >= validation_start].copy().reset_index(drop=True)
    min_validation_rows = max(max(cfg.lookbacks_h) + 48, 240)
    meta = {
        "selection_start": selection["dt"].iloc[0].isoformat() if len(selection) else None,
        "selection_end": selection["dt"].iloc[-1].isoformat() if len(selection) else None,
        "validation_start": validation["dt"].iloc[0].isoformat() if len(validation) else None,
        "validation_end": validation["dt"].iloc[-1].isoformat() if len(validation) else None,
        "purge_hours": int(purge_h),
        "selection_rows": int(len(selection)),
        "validation_rows": int(len(validation)),
        "min_validation_rows": int(min_validation_rows),
        "validation_usable": bool(len(validation) >= min_validation_rows),
    }
    return selection, validation, meta


def run_grid(cfg: RunConfig) -> dict[str, Any]:
    start = utc_ts(cfg.train_start)
    end = utc_ts(cfg.train_end)
    embargo = utc_ts(cfg.embargo_start)
    closes = load_close_matrix(Path(cfg.cache_dir), cfg.symbols, start, end, embargo)
    closes_fingerprint = data_fingerprint(closes)
    if cfg.preset_configs:
        grid = list(cfg.preset_configs)
    else:
        grid = [
            TsmomConfig(asset_vt, portfolio_vt, band, threshold, market_filter_h, 0.0, dd_stop, cooldown_h)
            for asset_vt, portfolio_vt, band, threshold, market_filter_h, dd_stop, cooldown_h in itertools.product(
                cfg.asset_vol_targets_ann,
                cfg.portfolio_vol_targets_ann,
                cfg.no_trade_bands,
                cfg.vote_thresholds,
                cfg.market_filters_h,
                cfg.drawdown_stops,
                cfg.cooldowns_h,
            )
        ]
    n_trials = len(grid)
    prior_trials = max(0, int(cfg.prior_trials))
    effective_trials = n_trials + prior_trials
    bootstrap_p5_min = bootstrap_threshold(effective_trials)
    validation_sharpe20_min = validation_sharpe_threshold(effective_trials)
    selection_closes, validation_closes, split_meta = split_selection_validation(closes, cfg)
    rows = []

    for g in grid:
        cost20 = simulate(
            selection_closes,
            g,
            cfg.lookbacks_h,
            20.0,
            bootstrap_iterations=cfg.bootstrap_iterations,
            bootstrap_seed_value=bootstrap_seed(g, cfg.lookbacks_h, 20.0, "selection", cfg.train_start, cfg.train_end),
        )
        cost40 = simulate(
            selection_closes,
            g,
            cfg.lookbacks_h,
            40.0,
            bootstrap_iterations=cfg.bootstrap_iterations,
            bootstrap_seed_value=bootstrap_seed(g, cfg.lookbacks_h, 40.0, "selection", cfg.train_start, cfg.train_end),
        )
        selection_checks = advance_checks(cost20, cost40, bootstrap_p5_min=bootstrap_p5_min)
        selection_passed = all(selection_checks.values())
        should_validate = bool(split_meta["validation_usable"] and selection_passed)
        if should_validate:
            val20 = simulate(
                validation_closes,
                g,
                cfg.lookbacks_h,
                20.0,
                bootstrap_iterations=cfg.bootstrap_iterations,
                bootstrap_seed_value=bootstrap_seed(g, cfg.lookbacks_h, 20.0, "validation", cfg.train_start, cfg.train_end),
            )
            val40 = simulate(
                validation_closes,
                g,
                cfg.lookbacks_h,
                40.0,
                bootstrap_iterations=cfg.bootstrap_iterations,
                bootstrap_seed_value=bootstrap_seed(g, cfg.lookbacks_h, 40.0, "validation", cfg.train_start, cfg.train_end),
            )
            drop_one = drop_one_lookback_summary(validation_closes, g, cfg.lookbacks_h, float(val20["sharpe"]))
            val_checks = validation_checks(val20, val40, sharpe20_min=validation_sharpe20_min)
            val_checks["drop_one_lookback_stable"] = bool(drop_one["passed"])
        else:
            val20 = {}
            val40 = {}
            drop_one = {"enabled": True, "passed": False, "rows": [], "note": "Skipped because selection did not pass or validation data was insufficient."}
            val_checks = {
                "validation_usable": bool(split_meta["validation_usable"]),
                "selection_passed_before_validation": bool(selection_passed),
            }
        checks = {**selection_checks, **val_checks}
        row = {
            "row_cache_key": row_cache_key(g, cfg, closes_fingerprint, bootstrap_p5_min, validation_sharpe20_min),
            "config": asdict(g),
            "lookbacks_h": [int(v) for v in cfg.lookbacks_h],
            "cost20": cost20,
            "cost40": cost40,
            "selection": {"cost20": cost20, "cost40": cost40, "checks": selection_checks},
            "validation": {"cost20": val20, "cost40": val40, "checks": val_checks, "split": split_meta},
            "drop_one_lookback": drop_one,
            "advance_checks": checks,
            "advance_passed": all(checks.values()),
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            bool(row["advance_passed"]),
            float(((row.get("validation") or {}).get("cost20") or {}).get("sharpe", -999.0) or -999.0),
            float(row["cost20"]["sharpe"]),
            -float(row["cost20"]["max_drawdown"]),
        ),
        reverse=True,
    )
    pass_rows = [row for row in rows if row["advance_passed"]]
    selection_validation = {
        "enabled": True,
        "selection_frac": 0.60,
        "n_configs_tested": n_trials,
        "prior_trials": prior_trials,
        "effective_trials": effective_trials,
        "selection_bootstrap_p5_min": bootstrap_p5_min,
        "validation_sharpe20_min": validation_sharpe20_min,
        "lookbacks_h": [int(v) for v in cfg.lookbacks_h],
        "drop_one_lookback_required": True,
        "breadth_min_symbols": breadth_min(len(cfg.symbols)),
        "note": "All selection and validation data remains before embargo_start.",
    }
    summary = {
        "rows": len(rows),
        "pass_count": len(pass_rows),
        "accepted_train_only": len(pass_rows) >= 1,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "tsmom_factory_v1_train_only_grid",
        "train_window": {"start": closes["dt"].iloc[0].isoformat(), "end": closes["dt"].iloc[-1].isoformat()},
        "data": {
            "fingerprint": closes_fingerprint,
            "rows": int(len(closes)),
            "first_dt": closes["dt"].iloc[0].isoformat(),
            "last_dt": closes["dt"].iloc[-1].isoformat(),
            "symbols": list(cfg.symbols),
        },
        "selection_validation": selection_validation,
        "symbols": list(cfg.symbols),
        "config": asdict(cfg),
        "summary": summary,
        "top": rows[:25],
        "rows": rows,
    }
    write_json(payload, Path(cfg.out_json))
    if cfg.out_md:
        write_markdown(payload, Path(cfg.out_md))
    return payload


def row_cache_key(
    cfg_row: TsmomConfig,
    cfg: RunConfig,
    closes_fingerprint: str,
    bootstrap_p5_min: float,
    validation_sharpe20_min: float,
) -> str:
    raw = json.dumps(
        {
            "cache_version": ROW_CACHE_VERSION,
            "config": asdict(cfg_row),
            "lookbacks_h": [int(v) for v in cfg.lookbacks_h],
            "data_fingerprint": closes_fingerprint,
            "train_start": cfg.train_start,
            "train_end": cfg.train_end,
            "embargo_start": cfg.embargo_start,
            "bootstrap_iterations": int(cfg.bootstrap_iterations),
            "bootstrap_p5_min": float(bootstrap_p5_min),
            "validation_sharpe20_min": float(validation_sharpe20_min),
        },
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# TSMOM Factory v1 Train-Only Grid",
        "",
        f"created_at: `{payload['created_at']}`",
        f"train_window: `{payload['train_window']['start']}` to `{payload['train_window']['end']}`",
        "",
        "This is train-only research. It does not authorize holdout, paper trading, or live trading.",
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Top Rows",
            "",
            "| cfg | pass | sel 20bps sh | val 20bps sh | val ret | val DD | sel boot p5 | symbols+ | turnover | drop-one |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["top"]:
        cfg = row["config"]
        c20 = row["cost20"]
        v20 = row.get("validation", {}).get("cost20", {}) or {}
        drop_one = row.get("drop_one_lookback", {}) or {}
        label = (
            "AVT{asset_vol_target_ann}_PVT{portfolio_vol_target_ann}_B{no_trade_band}"
            "_VT{vote_threshold}_MF{market_filter_h}_MO{market_off_scale}_DD{drawdown_stop}_CD{cooldown_h}"
        ).format(**cfg)
        lines.append(
            "| `{}` | `{}` | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | `{}/{}` | {:.3f} | `{}` |".format(
                label,
                row["advance_passed"],
                c20["sharpe"],
                float(v20.get("sharpe", 0.0) or 0.0),
                float(v20.get("total_return", 0.0) or 0.0),
                float(v20.get("max_drawdown", 0.0) or 0.0),
                c20["bootstrap_30d_sharpe_p5"],
                c20["positive_symbol_count"],
                c20["symbol_count"],
                c20["daily_turnover"],
                bool(drop_one.get("passed", False)),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Train-only OHLCV time-series momentum ensemble factory")
    ap.add_argument("--preset", choices=("core", "defensive_regime"), default="core")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--bootstrap-iterations", type=int, default=500)
    ap.add_argument("--prior-trials", type=int, default=0)
    ap.add_argument("--out-json", default="artifacts/v9/contract_lab/tsmom_factory_v1.json")
    ap.add_argument("--out-md", default="artifacts/v9/contract_lab/tsmom_factory_v1.md")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    cfg = config_for_preset(
        preset=args.preset,
        cache_dir=args.cache_dir,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        bootstrap_iterations=args.bootstrap_iterations,
        out_json=args.out_json,
        out_md=args.out_md,
        prior_trials=args.prior_trials,
    )
    started = time.time()
    payload = run_grid(cfg)
    print(
        "tsmom_factory_v1 done "
        f"rows={payload['summary']['rows']} pass={payload['summary']['pass_count']} "
        f"accepted={payload['summary']['accepted_train_only']} elapsed_sec={time.time() - started:.2f}"
    )
    print(args.out_json)
    print(args.out_md)


if __name__ == "__main__":
    main()
