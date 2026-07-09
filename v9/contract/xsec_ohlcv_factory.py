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

import pandas as pd
import numpy as np

from .metrics import max_drawdown
from .report import write_json
from .simulator import utc_ts
from .xsec_momentum import SYMBOLS, load_close_matrix, sharpe


ROW_CACHE_VERSION = "selection_validation_v4_diagnostic_walkforward"


@dataclass(frozen=True)
class OhlcvConfig:
    lookback_h: int
    skip_h: int
    rebalance_h: int
    k: int
    score_mode: str
    market_filter_h: int
    vol_target_ann: float
    n_tranches: int = 1


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...] = SYMBOLS
    lookbacks_h: tuple[int, ...] = (168, 336)
    skips_h: tuple[int, ...] = (0,)
    rebalances_h: tuple[int, ...] = (24, 72)
    ks: tuple[int, ...] = (2,)
    score_modes: tuple[str, ...] = ("mom", "risk_adj_mom")
    market_filters_h: tuple[int, ...] = (0, 720)
    vol_targets_ann: tuple[float, ...] = (0.16,)
    n_tranches: tuple[int, ...] = (1,)
    costs_bps: tuple[float, ...] = (20.0, 40.0)
    stress_costs_bps: tuple[float, ...] = ()
    validate_all_rows: bool = False
    plateau_center_config: dict[str, Any] | None = None
    plateau_validation_sharpe_min: float = 1.0
    plateau_neighbor_pass_fraction_min: float = 0.70
    plateau_center_max_ratio: float = 1.30
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    bootstrap_iterations: int = 500
    prior_trials: int = 0
    out_json: str = "artifacts/v9/contract_lab/xsec_ohlcv_factory_v1.json"
    out_md: str = "artifacts/v9/contract_lab/xsec_ohlcv_factory_v1.md"


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
    if preset == "defensive":
        return RunConfig(
            lookbacks_h=(168, 336, 720),
            skips_h=(0,),
            rebalances_h=(72, 168),
            ks=(2,),
            score_modes=("mom", "risk_adj_mom"),
            market_filters_h=(720,),
            vol_targets_ann=(0.12, 0.16),
            **base,
        )
    if preset == "slow":
        return RunConfig(
            lookbacks_h=(720, 1440),
            skips_h=(0, 24),
            rebalances_h=(168,),
            ks=(2, 3),
            score_modes=("mom", "risk_adj_mom"),
            market_filters_h=(720, 1440),
            vol_targets_ann=(0.12,),
            **base,
        )
    if preset == "fast":
        return RunConfig(
            lookbacks_h=(72, 168),
            skips_h=(0,),
            rebalances_h=(12, 24),
            ks=(2,),
            score_modes=("mom", "risk_adj_mom"),
            market_filters_h=(0, 336),
            vol_targets_ann=(0.18,),
            **base,
        )
    if preset == "defensive_neighbor":
        return RunConfig(
            lookbacks_h=(240, 336, 504),
            skips_h=(0, 24),
            rebalances_h=(48, 72, 96),
            ks=(2,),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008),
            vol_targets_ann=(0.10, 0.12, 0.14),
            **base,
        )
    if preset == "defensive_breadth":
        return RunConfig(
            lookbacks_h=(336, 504, 720),
            skips_h=(0,),
            rebalances_h=(72, 168),
            ks=(2, 3),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1440),
            vol_targets_ann=(0.10, 0.12),
            **base,
        )
    if preset == "defensive_drawdown":
        return RunConfig(
            lookbacks_h=(336, 720, 1440),
            skips_h=(0, 24),
            rebalances_h=(72, 168),
            ks=(2,),
            score_modes=("risk_adj_mom",),
            market_filters_h=(1008, 1440, 2160),
            vol_targets_ann=(0.08, 0.10, 0.12),
            **base,
        )
    if preset == "hq_dd_long":
        return RunConfig(
            lookbacks_h=(504, 720, 1008),
            skips_h=(0,),
            rebalances_h=(120, 168, 336),
            ks=(2, 3),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008, 1440),
            vol_targets_ann=(0.06, 0.08, 0.10, 0.12),
            **base,
        )
    if preset == "hq_dd_plateau":
        return RunConfig(
            lookbacks_h=(336, 504, 672),
            skips_h=(0,),
            rebalances_h=(120, 168, 240),
            ks=(3,),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008, 1344),
            vol_targets_ann=(0.05, 0.06, 0.08),
            stress_costs_bps=(30.0, 40.0),
            validate_all_rows=True,
            plateau_center_config={
                "lookback_h": 504,
                "skip_h": 0,
                "rebalance_h": 168,
                "k": 3,
                "score_mode": "risk_adj_mom",
                "market_filter_h": 1008,
                "vol_target_ann": 0.06,
            },
            **base,
        )
    if preset == "hq_cadence_tranche":
        return RunConfig(
            lookbacks_h=(336, 504, 720),
            skips_h=(0,),
            rebalances_h=(48, 96, 168),
            ks=(2, 3),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008),
            vol_targets_ann=(0.10, 0.12),
            n_tranches=(3,),
            **base,
        )
    if preset == "hq_fast_rebal":
        return RunConfig(
            lookbacks_h=(168, 240, 336),
            skips_h=(0,),
            rebalances_h=(24, 48, 96),
            ks=(2, 3),
            score_modes=("risk_adj_mom",),
            market_filters_h=(504, 720, 1008),
            vol_targets_ann=(0.10, 0.12, 0.14),
            **base,
        )
    if preset == "hq_breadth_wide":
        return RunConfig(
            lookbacks_h=(336, 504, 672),
            skips_h=(0,),
            rebalances_h=(48, 72, 120),
            ks=(3, 4, 5),
            score_modes=("risk_adj_mom",),
            market_filters_h=(504, 720, 1008),
            vol_targets_ann=(0.08, 0.10, 0.12),
            **base,
        )
    raise ValueError(f"unknown preset: {preset}")


def score_matrix(closes: pd.DataFrame, cfg: OhlcvConfig) -> pd.DataFrame:
    prices = closes.drop(columns=["dt"])
    mom = prices.shift(cfg.skip_h) / prices.shift(cfg.skip_h + cfg.lookback_h) - 1.0
    if cfg.score_mode == "mom":
        return mom
    if cfg.score_mode == "risk_adj_mom":
        ratios = prices / prices.shift(1)
        log_ret = ratios.apply(lambda col: np.log(col.where(col > 0.0)))
        min_periods = min(cfg.lookback_h, max(2, cfg.lookback_h // 4))
        vol = log_ret.rolling(cfg.lookback_h, min_periods=min_periods).std().shift(cfg.skip_h)
        return mom / vol.replace(0.0, pd.NA)
    raise ValueError(f"unknown score mode: {cfg.score_mode}")


def market_filter(closes: pd.DataFrame, cfg: OhlcvConfig) -> pd.Series:
    if cfg.market_filter_h <= 0:
        return pd.Series([True] * len(closes), index=closes.index)
    prices = closes.drop(columns=["dt"])
    market = prices.mean(axis=1)
    market_mom = market.shift(cfg.skip_h) / market.shift(cfg.skip_h + cfg.market_filter_h) - 1.0
    return (market_mom > 0.0).fillna(False)


def long_only_weights(score_row: pd.Series, cfg: OhlcvConfig, allow_exposure: bool) -> dict[str, float] | None:
    if score_row.isna().any():
        return None
    if not allow_exposure:
        return {sym: 0.0 for sym in score_row.index}
    ranked = sorted(score_row.index, key=lambda sym: (-float(score_row[sym]), sym))
    longs = ranked[: cfg.k]
    weights = {sym: 0.0 for sym in score_row.index}
    for sym in longs:
        weights[sym] = 1.0 / cfg.k
    return weights


def exposure_scale(past_returns: list[float], vol_target_ann: float, lookback_h: int = 720) -> float:
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


def bootstrap_seed(cfg: OhlcvConfig, cost_bps: float, segment: str, train_start: str, train_end: str) -> int:
    raw = json.dumps(
        {
            "cfg": asdict(cfg),
            "cost_bps": float(cost_bps),
            "segment": segment,
            "train_start": train_start,
            "train_end": train_end,
        },
        sort_keys=True,
    )
    return int(hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8], 16)


def data_fingerprint(closes: pd.DataFrame) -> str:
    symbols = [c for c in closes.columns if c != "dt"]
    h = hashlib.sha1()
    h.update(json.dumps(symbols, sort_keys=True).encode("utf-8"))
    h.update(pd.to_datetime(closes["dt"]).astype("int64").to_numpy().tobytes())
    h.update(np.ascontiguousarray(closes[symbols].to_numpy(dtype="float64")).tobytes())
    return h.hexdigest()


def row_cache_key(
    cfg_row: OhlcvConfig,
    closes_fingerprint: str,
    cfg: RunConfig,
    bootstrap_p5_min: float,
    validation_sharpe20_min: float,
    confirm_iterations: int,
) -> str:
    raw = json.dumps(
        {
            "cache_version": ROW_CACHE_VERSION,
            "config": asdict(cfg_row),
            "data_fingerprint": closes_fingerprint,
            "train_start": cfg.train_start,
            "train_end": cfg.train_end,
            "embargo_start": cfg.embargo_start,
            "bootstrap_iterations": int(cfg.bootstrap_iterations),
            "confirm_iterations": int(confirm_iterations),
            "bootstrap_p5_min": float(bootstrap_p5_min),
            "stress_costs_bps": [float(v) for v in cfg.stress_costs_bps],
            "validate_all_rows": bool(cfg.validate_all_rows),
            "validation_sharpe20_min": float(validation_sharpe20_min),
        },
        sort_keys=True,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def progress_path_for(out_json: str) -> Path:
    return Path(out_json).with_suffix(".progress.jsonl")


def progress_meta_path_for(out_json: str) -> Path:
    return Path(out_json).with_suffix(".progress.meta.json")


def load_progress_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = record.get("key")
        row = record.get("row")
        if isinstance(key, str) and isinstance(row, dict):
            rows[key] = row
    return rows


def append_progress_row(path: Path, key: str, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({"key": key, "row": row}, sort_keys=True) + "\n")
        handle.flush()


def write_progress_meta(
    path: Path,
    total_rows: int,
    completed_rows: int,
    closes_fingerprint: str,
    cfg: RunConfig,
    bootstrap_p5_min: float,
    validation_sharpe20_min: float,
    confirm_iterations: int,
) -> None:
    payload = {
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "cache_version": ROW_CACHE_VERSION,
        "total_rows": int(total_rows),
        "completed_rows": int(completed_rows),
        "data_fingerprint": closes_fingerprint,
        "train_start": cfg.train_start,
        "train_end": cfg.train_end,
        "embargo_start": cfg.embargo_start,
        "bootstrap_iterations": int(cfg.bootstrap_iterations),
        "confirm_iterations": int(confirm_iterations),
        "bootstrap_p5_min": float(bootstrap_p5_min),
        "validation_sharpe20_min": float(validation_sharpe20_min),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")


def block_bootstrap_p5(daily_returns: pd.Series, iterations: int = 500, block_days: int = 30, seed: int = 20260707) -> float:
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
    cfg: OhlcvConfig,
    cost_bps: float,
    bootstrap_iterations: int = 500,
    bootstrap_seed_value: int = 20260707,
    bootstrap_confirm_iterations: int = 0,
    bootstrap_confirm_seed_value: int | None = None,
) -> dict[str, Any]:
    symbols = [c for c in closes.columns if c != "dt"]
    if cfg.n_tranches < 1:
        raise ValueError("n_tranches must be >= 1")
    scores = score_matrix(closes, cfg)
    allowed = market_filter(closes, cfg)
    returns = closes[symbols].pct_change().shift(-1)
    weights = {sym: 0.0 for sym in symbols}
    tranche_weights = [{sym: 0.0 for sym in symbols} for _ in range(cfg.n_tranches)]
    tranche_offsets = [(idx * cfg.rebalance_h) // cfg.n_tranches for idx in range(cfg.n_tranches)]
    rows = []
    rebalances = []
    symbol_returns = {sym: 0.0 for sym in symbols}
    past_returns: list[float] = []
    scale_sum = 0.0
    scale_count = 0

    for idx in range(len(closes) - 1):
        ts = pd.Timestamp(closes["dt"].iloc[idx])
        old_weights = dict(weights)
        due_rebalance = False
        for tranche_idx, offset in enumerate(tranche_offsets):
            if idx < offset or (idx - offset) % cfg.rebalance_h != 0:
                continue
            due_rebalance = True
            target = long_only_weights(scores.iloc[idx], cfg, bool(allowed.iloc[idx]))
            if target is not None:
                scale = exposure_scale(past_returns, cfg.vol_target_ann)
                tranche_weights[tranche_idx] = {sym: target[sym] * scale / cfg.n_tranches for sym in symbols}
                scale_sum += scale
                scale_count += 1
        if due_rebalance:
            weights = {sym: sum(tranche[sym] for tranche in tranche_weights) for sym in symbols}
            turnover = sum(abs(weights[sym] - old_weights[sym]) for sym in symbols)
            cost = turnover * cost_bps / 10000.0
            rebalances.append({"dt": ts, "turnover": turnover, "cost": cost, "gross_exposure": sum(abs(v) for v in weights.values())})
        else:
            cost = 0.0
        row_rets = returns.iloc[idx].fillna(0.0)
        gross = 0.0
        long_gross = 0.0
        short_gross = 0.0
        for sym in symbols:
            value = weights[sym] * float(row_rets[sym])
            gross += value
            symbol_returns[sym] += value
            if weights[sym] >= 0.0:
                long_gross += value
            else:
                short_gross += value
        net = gross - cost
        long_exposure = sum(max(v, 0.0) for v in weights.values())
        short_exposure = sum(abs(min(v, 0.0)) for v in weights.values())
        rows.append(
            {
                "dt": ts,
                "net_return": net,
                "gross_return": gross,
                "long_gross_return": long_gross,
                "short_gross_return": short_gross,
                "cost": cost,
                "gross_exposure": sum(abs(v) for v in weights.values()),
                "long_exposure": long_exposure,
                "short_exposure": short_exposure,
            }
        )
        past_returns.append(net)

    ret = pd.DataFrame(rows).set_index("dt")
    reb = pd.DataFrame(rebalances).set_index("dt")
    period_returns = (1.0 + ret["net_return"]).resample(f"{cfg.rebalance_h}h").prod() - 1.0
    daily_returns = (1.0 + ret["net_return"]).resample("1D").prod() - 1.0
    long_period_returns = (1.0 + ret["long_gross_return"]).resample(f"{cfg.rebalance_h}h").prod() - 1.0
    short_period_returns = (1.0 + ret["short_gross_return"]).resample(f"{cfg.rebalance_h}h").prod() - 1.0
    total_return = float((1.0 + ret["net_return"]).prod() - 1.0)
    long_gross_return = float((1.0 + ret["long_gross_return"]).prod() - 1.0)
    short_gross_return = float((1.0 + ret["short_gross_return"]).prod() - 1.0)
    dd = max_drawdown_from_returns(ret["net_return"])
    period_sharpe = sharpe(period_returns, 8760.0 / cfg.rebalance_h)
    by_year = {}
    for bucket in ["2021", "2022", "2023", "2024H1"]:
        subset = period_returns[[annual_bucket(ts) == bucket for ts in period_returns.index]]
        by_year[bucket] = {
            "periods": int(len(subset)),
            "net_return": float((1.0 + subset).prod() - 1.0) if len(subset) else 0.0,
            "sharpe": sharpe(subset, 8760.0 / cfg.rebalance_h) if len(subset) else 0.0,
        }
    symbol_pnl = {sym: float(value * 10_000.0) for sym, value in symbol_returns.items()}
    positives = [max(v, 0.0) for v in symbol_pnl.values()]
    top_symbol_share = max(positives) / sum(positives) if sum(positives) > 0 else 0.0
    equal_weight = returns.mean(axis=1).iloc[: len(ret)].fillna(0.0)
    equal_weight.index = ret.index
    ew_period_returns = (1.0 + equal_weight).resample(f"{cfg.rebalance_h}h").prod() - 1.0
    ew_sharpe = sharpe(ew_period_returns, 8760.0 / cfg.rebalance_h)
    ew_dd = max_drawdown_from_returns(equal_weight)
    bootstrap_p5 = block_bootstrap_p5(daily_returns, iterations=bootstrap_iterations, seed=bootstrap_seed_value)
    yearly_positive = sum(1 for row in by_year.values() if row["net_return"] > 0)
    result = {
        "config": asdict(cfg),
        "cost_bps": float(cost_bps),
        "total_return": total_return,
        "net_pnl": float(total_return * 10_000.0),
        "sharpe": period_sharpe,
        "max_drawdown": dd,
        "daily_turnover": float(reb["turnover"].resample("1D").sum().mean()) if len(reb) else 0.0,
        "avg_gross_exposure": float(ret["gross_exposure"].mean()) if len(ret) else 0.0,
        "avg_long_exposure": float(ret["long_exposure"].mean()) if len(ret) else 0.0,
        "avg_short_exposure": float(ret["short_exposure"].mean()) if len(ret) else 0.0,
        "avg_rebalance_scale": float(scale_sum / scale_count) if scale_count else 1.0,
        "rebalance_event_count": int(len(reb)),
        "rebalance_offsets_h": [int(v) for v in tranche_offsets],
        "yearly": by_year,
        "yearly_positive_count": yearly_positive,
        "symbol_pnl": symbol_pnl,
        "top_positive_symbol_share": float(top_symbol_share),
        "legs": {
            "long_gross_return": long_gross_return,
            "long_gross_sharpe": sharpe(long_period_returns, 8760.0 / cfg.rebalance_h),
            "short_gross_return": short_gross_return,
            "short_gross_sharpe": sharpe(short_period_returns, 8760.0 / cfg.rebalance_h),
            "avg_long_exposure": float(ret["long_exposure"].mean()) if len(ret) else 0.0,
            "avg_short_exposure": float(ret["short_exposure"].mean()) if len(ret) else 0.0,
        },
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
    if bootstrap_confirm_iterations > 0:
        confirm_seed = int(bootstrap_confirm_seed_value if bootstrap_confirm_seed_value is not None else bootstrap_seed_value)
        result["bootstrap_30d_sharpe_p5_confirm"] = block_bootstrap_p5(
            daily_returns,
            iterations=bootstrap_confirm_iterations,
            seed=confirm_seed,
        )
        result["bootstrap_confirm_seed"] = confirm_seed
        result["bootstrap_confirm_iterations"] = int(bootstrap_confirm_iterations)
    return result


def bootstrap_threshold(n_trials: int, base: float = 0.25) -> float:
    return base + 0.05 * math.log10(max(1, int(n_trials)))


def validation_sharpe_threshold(effective_trials: int, base: float = 0.70, slope: float = 0.10) -> float:
    return base + slope * max(0.0, math.log10(max(1, int(effective_trials))) - 1.0)


def advance_checks(cost20: dict[str, Any], cost40: dict[str, Any], bootstrap_p5_min: float = 0.25) -> dict[str, bool]:
    benchmark = cost20["equal_weight_benchmark"]
    return {
        "sharpe20_ge_1_2": float(cost20["sharpe"]) >= 1.2,
        "max_dd20_le_25pct": float(cost20["max_drawdown"]) <= 0.25,
        "positive_3_of_4_years": int(cost20["yearly_positive_count"]) >= 3,
        "return_2024h1_gt_minus_2pct": float(cost20["yearly"]["2024H1"]["net_return"]) > -0.02,
        "bootstrap_p5_ge_adjusted_min": float(cost20["bootstrap_30d_sharpe_p5"]) >= bootstrap_p5_min,
        "sharpe40_ge_1": float(cost40["sharpe"]) >= 1.0,
        "top_symbol_share_le_60pct": float(cost20["top_positive_symbol_share"]) <= 0.60,
        "benchmark_sharpe_excess_ge_0_10": float(benchmark["sharpe_excess"]) >= 0.10,
        "drawdown_ratio_le_0_80": float(benchmark["drawdown_ratio"]) <= 0.80,
    }


def validation_checks(cost20: dict[str, Any], cost40: dict[str, Any], sharpe20_min: float = 0.70) -> dict[str, bool]:
    return {
        "validation_sharpe20_ge_adjusted_min": float(cost20["sharpe"]) >= sharpe20_min,
        "validation_max_dd20_le_30pct": float(cost20["max_drawdown"]) <= 0.30,
        "validation_return20_gt_0": float(cost20["total_return"]) > 0.0,
        "validation_sharpe40_gt_0": float(cost40["sharpe"]) > 0.0,
    }


def min_rows_for_config(cfg: OhlcvConfig) -> int:
    return max(cfg.lookback_h + cfg.skip_h + cfg.rebalance_h + 24, cfg.market_filter_h + 24, 240)


def walk_forward_summary(
    closes: pd.DataFrame,
    cfg: OhlcvConfig,
    cost_bps: float = 40.0,
    folds: int = 6,
    min_q25_sharpe: float = 0.30,
    min_sign_consistency: float = 0.70,
) -> dict[str, Any]:
    min_rows = min_rows_for_config(cfg)
    usable_folds = max(1, min(int(folds), len(closes) // min_rows))
    rows = []
    if usable_folds < 2:
        return {
            "enabled": True,
            "passed": False,
            "cost_bps": float(cost_bps),
            "folds": [],
            "reason": "insufficient_rows_for_walk_forward",
        }
    for fold in range(usable_folds):
        lo = int(fold * len(closes) / usable_folds)
        hi = int((fold + 1) * len(closes) / usable_folds)
        frame = closes.iloc[lo:hi].copy().reset_index(drop=True)
        if len(frame) < min_rows:
            continue
        result = simulate(frame, cfg, cost_bps, bootstrap_iterations=0)
        legs = result.get("legs", {}) or {}
        rows.append(
            {
                "fold": int(fold),
                "start": frame["dt"].iloc[0].isoformat(),
                "end": frame["dt"].iloc[-1].isoformat(),
                "rows": int(len(frame)),
                "sharpe": float(result["sharpe"]),
                "total_return": float(result["total_return"]),
                "max_drawdown": float(result["max_drawdown"]),
                "daily_turnover": float(result["daily_turnover"]),
                "long_gross_sharpe": float(legs.get("long_gross_sharpe", 0.0) or 0.0),
                "short_gross_sharpe": float(legs.get("short_gross_sharpe", 0.0) or 0.0),
                "long_gross_return": float(legs.get("long_gross_return", 0.0) or 0.0),
                "short_gross_return": float(legs.get("short_gross_return", 0.0) or 0.0),
                "avg_long_exposure": float(legs.get("avg_long_exposure", 0.0) or 0.0),
                "avg_short_exposure": float(legs.get("avg_short_exposure", 0.0) or 0.0),
            }
        )
    if not rows:
        return {
            "enabled": True,
            "passed": False,
            "cost_bps": float(cost_bps),
            "folds": [],
            "reason": "no_usable_folds",
        }
    sharpes = [row["sharpe"] for row in rows]
    q25 = float(np.percentile(sharpes, 25))
    sign_consistency = float(sum(1 for value in sharpes if value > 0.0) / len(sharpes))
    positive_return_fraction = float(sum(1 for row in rows if row["total_return"] > 0.0) / len(rows))
    long_active = [row for row in rows if row["avg_long_exposure"] > 0.01]
    short_active = [row for row in rows if row["avg_short_exposure"] > 0.01]
    median_long_sharpe = float(np.median([row["long_gross_sharpe"] for row in long_active])) if long_active else 0.0
    median_short_sharpe = float(np.median([row["short_gross_sharpe"] for row in short_active])) if short_active else 0.0
    checks = {
        "wf_q25_sharpe_ge_min": q25 >= min_q25_sharpe,
        "wf_sign_consistency_ge_min": sign_consistency >= min_sign_consistency,
        "wf_positive_return_fraction_ge_min": positive_return_fraction >= min_sign_consistency,
        "wf_median_long_leg_sharpe_ge_0": median_long_sharpe >= 0.0,
        "wf_median_short_leg_sharpe_ge_0": median_short_sharpe >= 0.0,
    }
    return {
        "enabled": True,
        "passed": all(checks.values()),
        "cost_bps": float(cost_bps),
        "fold_count": int(len(rows)),
        "min_q25_sharpe": float(min_q25_sharpe),
        "min_sign_consistency": float(min_sign_consistency),
        "q25_sharpe": q25,
        "sign_consistency": sign_consistency,
        "positive_return_fraction": positive_return_fraction,
        "median_long_gross_sharpe": median_long_sharpe,
        "median_short_gross_sharpe": median_short_sharpe,
        "checks": checks,
        "folds": rows,
        "note": "Train-only cross-sectional walk-forward robustness; it does not authorize holdout, paper trading, or live trading.",
    }


def leave_one_symbol_summary(
    closes: pd.DataFrame,
    cfg: OhlcvConfig,
    cost_bps: float = 40.0,
    min_sharpe: float = 0.20,
) -> dict[str, Any]:
    symbols = [c for c in closes.columns if c != "dt"]
    if len(symbols) < 3:
        return {
            "enabled": True,
            "passed": False,
            "cost_bps": float(cost_bps),
            "rows": [],
            "reason": "requires_at_least_three_symbols",
        }
    rows = []
    for dropped in symbols:
        frame = closes.drop(columns=[dropped]).copy().reset_index(drop=True)
        effective_k = min(int(cfg.k), len(symbols) - 1)
        test_cfg = OhlcvConfig(
            lookback_h=cfg.lookback_h,
            skip_h=cfg.skip_h,
            rebalance_h=cfg.rebalance_h,
            k=effective_k,
            score_mode=cfg.score_mode,
            market_filter_h=cfg.market_filter_h,
            vol_target_ann=cfg.vol_target_ann,
            n_tranches=cfg.n_tranches,
        )
        result = simulate(frame, test_cfg, cost_bps, bootstrap_iterations=0)
        rows.append(
            {
                "dropped_symbol": dropped,
                "remaining_symbols": [sym for sym in symbols if sym != dropped],
                "sharpe": float(result["sharpe"]),
                "total_return": float(result["total_return"]),
                "max_drawdown": float(result["max_drawdown"]),
                "daily_turnover": float(result["daily_turnover"]),
            }
        )
    min_row = min(rows, key=lambda row: (row["sharpe"], row["total_return"])) if rows else None
    checks = {
        "loo_min_sharpe_ge_min": bool(rows) and min(row["sharpe"] for row in rows) >= min_sharpe,
        "loo_all_returns_gt_0": bool(rows) and all(row["total_return"] > 0.0 for row in rows),
    }
    return {
        "enabled": True,
        "passed": all(checks.values()),
        "cost_bps": float(cost_bps),
        "min_sharpe": float(min(row["sharpe"] for row in rows)) if rows else 0.0,
        "min_return": float(min(row["total_return"] for row in rows)) if rows else 0.0,
        "worst_drop": min_row,
        "checks": checks,
        "rows": rows,
        "note": "Train-only cross-sectional leave-one-symbol robustness; it does not authorize holdout, paper trading, or live trading.",
    }


def cost_label(cost_bps: float) -> str:
    raw = f"{float(cost_bps):g}".replace(".", "p")
    return f"cost{raw}"


def stress_cost_results(
    closes: pd.DataFrame,
    cfg: OhlcvConfig,
    base_results: dict[str, dict[str, Any]],
    costs_bps: tuple[float, ...],
    segment: str,
    train_start: str,
    train_end: str,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for cost in costs_bps:
        label = cost_label(cost)
        if math.isclose(float(cost), 20.0):
            result = base_results.get("cost20", {})
        elif math.isclose(float(cost), 40.0):
            result = base_results.get("cost40", {})
        else:
            result = simulate(
                closes,
                cfg,
                float(cost),
                bootstrap_iterations=0,
                bootstrap_seed_value=bootstrap_seed(cfg, float(cost), f"{segment}_stress", train_start, train_end),
            )
        if result:
            results[label] = result
    return results


def _config_value_matches(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return left == right


def config_matches(config: dict[str, Any], target: dict[str, Any]) -> bool:
    return all(_config_value_matches(config.get(key), value) for key, value in target.items())


def validation_sharpe20(row: dict[str, Any]) -> float | None:
    value = ((row.get("validation") or {}).get("cost20") or {}).get("sharpe")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def plateau_stability_summary(rows: list[dict[str, Any]], cfg: RunConfig) -> dict[str, Any] | None:
    if not cfg.plateau_center_config:
        return None
    center_config = dict(cfg.plateau_center_config)
    center_row = next((row for row in rows if config_matches(row.get("config", {}), center_config)), None)
    neighbor_rows = [row for row in rows if not config_matches(row.get("config", {}), center_config)]
    neighbor_values = [validation_sharpe20(row) for row in neighbor_rows]
    valid_neighbor_values = [value for value in neighbor_values if value is not None]
    neighbor_pass_count = sum(
        1 for value in neighbor_values if value is not None and value >= cfg.plateau_validation_sharpe_min
    )
    neighbor_total = len(neighbor_rows)
    neighbor_pass_fraction = neighbor_pass_count / neighbor_total if neighbor_total else 0.0
    center_sharpe = validation_sharpe20(center_row) if center_row else None
    best_neighbor_sharpe = max(valid_neighbor_values) if valid_neighbor_values else None
    center_not_spike = False
    if center_sharpe is not None and best_neighbor_sharpe is not None:
        if center_sharpe <= best_neighbor_sharpe:
            center_not_spike = True
        elif best_neighbor_sharpe > 0.0:
            center_not_spike = center_sharpe <= best_neighbor_sharpe * cfg.plateau_center_max_ratio
    passed = bool(
        center_sharpe is not None
        and center_sharpe >= cfg.plateau_validation_sharpe_min
        and neighbor_pass_fraction >= cfg.plateau_neighbor_pass_fraction_min
        and center_not_spike
    )
    return {
        "enabled": True,
        "passed": passed,
        "center_config": center_config,
        "center_found": center_row is not None,
        "center_validation_sharpe20": center_sharpe,
        "best_neighbor_validation_sharpe20": best_neighbor_sharpe,
        "neighbor_pass_count": int(neighbor_pass_count),
        "neighbor_total": int(neighbor_total),
        "neighbor_pass_fraction": float(neighbor_pass_fraction),
        "validation_sharpe20_min": float(cfg.plateau_validation_sharpe_min),
        "neighbor_pass_fraction_min": float(cfg.plateau_neighbor_pass_fraction_min),
        "center_max_ratio": float(cfg.plateau_center_max_ratio),
        "center_not_spike": bool(center_not_spike),
        "note": "Train-only plateau diagnostic; it does not authorize holdout, paper trading, or live trading.",
    }


def split_selection_validation(closes: pd.DataFrame, cfg: OhlcvConfig, selection_frac: float = 0.75) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not 0.50 <= selection_frac <= 0.90:
        raise ValueError("selection_frac must be between 0.50 and 0.90")
    split_idx = max(1, min(len(closes) - 2, int(len(closes) * selection_frac)))
    split_dt = pd.Timestamp(closes["dt"].iloc[split_idx])
    purge_h = max(int(cfg.lookback_h + cfg.skip_h), int(cfg.rebalance_h), int(cfg.market_filter_h))
    validation_start = split_dt + pd.Timedelta(hours=purge_h)
    selection = closes.loc[closes["dt"] <= split_dt].copy().reset_index(drop=True)
    validation = closes.loc[closes["dt"] >= validation_start].copy().reset_index(drop=True)
    min_validation_rows = max(cfg.lookback_h + cfg.skip_h + cfg.rebalance_h + 24, cfg.market_filter_h + 24, 240)
    meta = {
        "selection_start": selection["dt"].iloc[0].isoformat() if len(selection) else None,
        "selection_end": selection["dt"].iloc[-1].isoformat() if len(selection) else None,
        "validation_start": validation["dt"].iloc[0].isoformat() if len(validation) else None,
        "validation_end": validation["dt"].iloc[-1].isoformat() if len(validation) else None,
        "purge_hours": purge_h,
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
    grid = [
        OhlcvConfig(l, s, r, k, mode, mf, vt, nt)
        for l, s, r, k, mode, mf, vt, nt in itertools.product(
            cfg.lookbacks_h,
            cfg.skips_h,
            cfg.rebalances_h,
            cfg.ks,
            cfg.score_modes,
            cfg.market_filters_h,
            cfg.vol_targets_ann,
            cfg.n_tranches,
        )
    ]
    n_trials = len(grid)
    prior_trials = max(0, int(cfg.prior_trials))
    effective_trials = n_trials + prior_trials
    bootstrap_p5_min = bootstrap_threshold(effective_trials)
    validation_sharpe20_min = validation_sharpe_threshold(effective_trials)
    confirm_iterations = max(500, 5 * int(cfg.bootstrap_iterations))
    progress_path = progress_path_for(cfg.out_json)
    progress_meta_path = progress_meta_path_for(cfg.out_json)
    progress_rows = load_progress_rows(progress_path)
    write_progress_meta(
        progress_meta_path,
        n_trials,
        len(progress_rows),
        closes_fingerprint,
        cfg,
        bootstrap_p5_min,
        validation_sharpe20_min,
        confirm_iterations,
    )
    rows = []
    for g in grid:
        cache_key = row_cache_key(g, closes_fingerprint, cfg, bootstrap_p5_min, validation_sharpe20_min, confirm_iterations)
        if cache_key in progress_rows:
            rows.append(progress_rows[cache_key])
            continue
        selection_closes, validation_closes, split_meta = split_selection_validation(closes, g)
        cost20 = simulate(
            selection_closes,
            g,
            20.0,
            bootstrap_iterations=cfg.bootstrap_iterations,
            bootstrap_seed_value=bootstrap_seed(g, 20.0, "selection", cfg.train_start, cfg.train_end),
        )
        cost40 = simulate(
            selection_closes,
            g,
            40.0,
            bootstrap_iterations=cfg.bootstrap_iterations,
            bootstrap_seed_value=bootstrap_seed(g, 40.0, "selection", cfg.train_start, cfg.train_end),
        )
        selection_checks = advance_checks(cost20, cost40, bootstrap_p5_min=bootstrap_p5_min)
        if all(selection_checks.values()):
            cost20 = simulate(
                selection_closes,
                g,
                20.0,
                bootstrap_iterations=cfg.bootstrap_iterations,
                bootstrap_seed_value=bootstrap_seed(g, 20.0, "selection", cfg.train_start, cfg.train_end),
                bootstrap_confirm_iterations=confirm_iterations,
                bootstrap_confirm_seed_value=bootstrap_seed(g, 20.0, "selection_confirm", cfg.train_start, cfg.train_end),
            )
            selection_checks = advance_checks(cost20, cost40, bootstrap_p5_min=bootstrap_p5_min)
            selection_checks["bootstrap_p5_confirm_ge_adjusted_min"] = (
                float(cost20["bootstrap_30d_sharpe_p5_confirm"]) >= bootstrap_p5_min
            )
        selection_passed = all(selection_checks.values())
        if selection_passed:
            walk_forward = walk_forward_summary(selection_closes, g, cost_bps=40.0)
            selection_checks["walk_forward_robust"] = bool(walk_forward["passed"])
            selection_passed = all(selection_checks.values())
        else:
            walk_forward = {
                "enabled": True,
                "passed": False,
                "folds": [],
                "note": "Skipped because base selection checks did not pass.",
            }
        diagnostic_walk_forward = {
            "enabled": bool(cfg.validate_all_rows),
            "diagnostic_only": True,
            "triggered": False,
            "rows": [],
            "note": "Diagnostic walk-forward only runs for validate_all_rows rows that fail selection but pass validation Sharpe.",
        }
        should_validate = bool(split_meta["validation_usable"] and (selection_passed or cfg.validate_all_rows))
        if should_validate:
            val20 = simulate(
                validation_closes,
                g,
                20.0,
                bootstrap_iterations=cfg.bootstrap_iterations,
                bootstrap_seed_value=bootstrap_seed(g, 20.0, "validation", cfg.train_start, cfg.train_end),
            )
            val40 = simulate(
                validation_closes,
                g,
                40.0,
                bootstrap_iterations=cfg.bootstrap_iterations,
                bootstrap_seed_value=bootstrap_seed(g, 40.0, "validation", cfg.train_start, cfg.train_end),
            )
            val_checks = validation_checks(val20, val40, sharpe20_min=validation_sharpe20_min)
            if selection_passed:
                leave_one_symbol = leave_one_symbol_summary(validation_closes, g, cost_bps=40.0)
                val_checks["leave_one_symbol_robust"] = bool(leave_one_symbol["passed"])
                val20_legs = val20.get("legs", {}) or {}
                val_checks["validation_long_leg_gross_return_gt_minus_5pct"] = (
                    float(val20_legs.get("avg_long_exposure", 0.0) or 0.0) <= 0.01
                    or float(val20_legs.get("long_gross_return", 0.0) or 0.0) > -0.05
                )
            else:
                leave_one_symbol = {
                    "enabled": True,
                    "passed": False,
                    "rows": [],
                    "note": "Skipped because selection did not pass.",
                }
                if cfg.validate_all_rows and float(val20.get("sharpe", 0.0) or 0.0) >= validation_sharpe20_min:
                    diagnostic_walk_forward = walk_forward_summary(selection_closes, g, cost_bps=40.0)
                    diagnostic_walk_forward["diagnostic_only"] = True
                    diagnostic_walk_forward["triggered"] = True
                    diagnostic_walk_forward["trigger_reason"] = "selection_failed_but_validation_sharpe20_ge_adjusted_min"
                    diagnostic_walk_forward["validation_sharpe20"] = float(val20.get("sharpe", 0.0) or 0.0)
                    diagnostic_walk_forward["validation_sharpe20_min"] = float(validation_sharpe20_min)
        else:
            val20 = {}
            val40 = {}
            leave_one_symbol = {
                "enabled": True,
                "passed": False,
                "rows": [],
                "note": "Skipped because selection did not pass or validation data was insufficient.",
            }
            val_checks = {
                "validation_usable": bool(split_meta["validation_usable"]),
                "selection_passed_before_validation": bool(selection_passed),
            }
        cost_stress = {}
        if cfg.stress_costs_bps:
            cost_stress = {
                "selection": stress_cost_results(
                    selection_closes,
                    g,
                    {"cost20": cost20, "cost40": cost40},
                    cfg.stress_costs_bps,
                    "selection",
                    cfg.train_start,
                    cfg.train_end,
                ),
                "validation": stress_cost_results(
                    validation_closes,
                    g,
                    {"cost20": val20, "cost40": val40},
                    cfg.stress_costs_bps,
                    "validation",
                    cfg.train_start,
                    cfg.train_end,
                )
                if val20
                else {},
            }
        checks = {**selection_checks, **val_checks}
        row = {
            "row_cache_key": cache_key,
            "config": asdict(g),
            "cost20": cost20,
            "cost40": cost40,
            "selection": {"cost20": cost20, "cost40": cost40, "checks": selection_checks},
            "validation": {"cost20": val20, "cost40": val40, "checks": val_checks, "split": split_meta},
            "walk_forward": walk_forward,
            "diagnostic_walk_forward": diagnostic_walk_forward,
            "leave_one_symbol": leave_one_symbol,
            "cost_stress": cost_stress,
            "advance_checks": checks,
            "advance_passed": all(checks.values()),
        }
        append_progress_row(progress_path, cache_key, row)
        progress_rows[cache_key] = row
        write_progress_meta(
            progress_meta_path,
            n_trials,
            len(progress_rows),
            closes_fingerprint,
            cfg,
            bootstrap_p5_min,
            validation_sharpe20_min,
            confirm_iterations,
        )
        rows.append(row)
    rows.sort(
        key=lambda row: (
            bool(row["advance_passed"]),
            float((row.get("walk_forward") or {}).get("q25_sharpe", -999.0) or -999.0),
            float(row["cost20"]["sharpe"]),
            -float(row["cost20"]["max_drawdown"]),
        ),
        reverse=True,
    )
    pass_rows = [row for row in rows if row["advance_passed"]]
    stability = plateau_stability_summary(rows, cfg)
    accepted = len(pass_rows) >= 3
    if stability:
        accepted = accepted and bool(stability["passed"])
    selection_validation = {
        "enabled": True,
        "selection_frac": 0.75,
        "n_configs_tested": n_trials,
        "prior_trials": prior_trials,
        "effective_trials": effective_trials,
        "selection_bootstrap_p5_min": bootstrap_p5_min,
        "selection_bootstrap_confirm_iterations": confirm_iterations,
        "validation_sharpe20_min": validation_sharpe20_min,
        "validate_all_rows": bool(cfg.validate_all_rows),
        "stress_costs_bps": [float(v) for v in cfg.stress_costs_bps],
        "walk_forward_required": True,
        "walk_forward_cost_bps": 40.0,
        "diagnostic_walk_forward_for_validate_all_rows": True,
        "leave_one_symbol_required": True,
        "note": "All selection and validation data remains before embargo_start.",
    }
    if stability:
        selection_validation["plateau_stability"] = stability
    summary = {
        "rows": len(rows),
        "pass_count": len(pass_rows),
        "accepted_train_only": accepted,
        "holdout_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    if stability:
        summary["plateau_stability_passed"] = bool(stability["passed"])
        summary["plateau_neighbor_pass_fraction"] = stability["neighbor_pass_fraction"]
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "xsec_ohlcv_factory_v1_train_only_grid",
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
    progress_path.unlink(missing_ok=True)
    progress_meta_path.unlink(missing_ok=True)
    return payload


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# XSec OHLCV Factory v1 Train-Only Grid",
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
    plateau = payload.get("selection_validation", {}).get("plateau_stability")
    if plateau:
        lines.extend(
            [
                "",
                "## Plateau Stability",
                "",
                f"- passed: `{plateau['passed']}`",
                f"- neighbor_pass_fraction: `{plateau['neighbor_pass_fraction']:.3f}`",
                f"- neighbor_pass_count: `{plateau['neighbor_pass_count']}/{plateau['neighbor_total']}`",
                f"- center_validation_sharpe20: `{float(plateau['center_validation_sharpe20'] or 0.0):.3f}`",
                f"- best_neighbor_validation_sharpe20: `{float(plateau['best_neighbor_validation_sharpe20'] or 0.0):.3f}`",
                f"- center_not_spike: `{plateau['center_not_spike']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Top Rows",
            "",
            "| cfg | pass | sel 20bps sh | wf q25 40bps | diag wf q25 | val 20bps sh | val ret | val DD | sel boot p5 | EW excess | DD ratio | top sym | loo min sh |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["top"]:
        cfg = row["config"]
        c20 = row["cost20"]
        v20 = row.get("validation", {}).get("cost20", {}) or {}
        walk_forward = row.get("walk_forward", {}) or {}
        diagnostic_walk_forward = row.get("diagnostic_walk_forward", {}) or {}
        leave_one_symbol = row.get("leave_one_symbol", {}) or {}
        bench = c20["equal_weight_benchmark"]
        label = "L{lookback_h}_S{skip_h}_R{rebalance_h}_K{k}_{score_mode}_MF{market_filter_h}_VT{vol_target_ann}_NT{n_tranches}".format(**cfg)
        lines.append(
            "| `{}` | `{}` | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
                label,
                row["advance_passed"],
                c20["sharpe"],
                float(walk_forward.get("q25_sharpe", 0.0) or 0.0),
                float(diagnostic_walk_forward.get("q25_sharpe", 0.0) or 0.0),
                float(v20.get("sharpe", 0.0) or 0.0),
                float(v20.get("total_return", 0.0) or 0.0),
                float(v20.get("max_drawdown", 0.0) or 0.0),
                c20["bootstrap_30d_sharpe_p5"],
                bench["sharpe_excess"],
                bench["drawdown_ratio"],
                c20["top_positive_symbol_share"],
                float(leave_one_symbol.get("min_sharpe", 0.0) or 0.0),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Train-only OHLCV cross-sectional strategy factory")
    ap.add_argument(
        "--preset",
        choices=(
            "core",
            "defensive",
            "slow",
            "fast",
            "defensive_neighbor",
            "defensive_breadth",
            "defensive_drawdown",
            "hq_dd_long",
            "hq_dd_plateau",
            "hq_cadence_tranche",
            "hq_fast_rebal",
            "hq_breadth_wide",
        ),
        default="core",
    )
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--bootstrap-iterations", type=int, default=500)
    ap.add_argument("--prior-trials", type=int, default=0)
    ap.add_argument("--out-json", default="artifacts/v9/contract_lab/xsec_ohlcv_factory_v1.json")
    ap.add_argument("--out-md", default="artifacts/v9/contract_lab/xsec_ohlcv_factory_v1.md")
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
        "xsec_ohlcv_factory_v1 done "
        f"rows={payload['summary']['rows']} pass={payload['summary']['pass_count']} "
        f"accepted={payload['summary']['accepted_train_only']} elapsed_sec={time.time() - started:.2f}"
    )
    print(args.out_json)
    print(args.out_md)


if __name__ == "__main__":
    main()
