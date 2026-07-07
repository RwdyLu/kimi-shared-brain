from __future__ import annotations

import argparse
import itertools
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


@dataclass(frozen=True)
class OhlcvConfig:
    lookback_h: int
    skip_h: int
    rebalance_h: int
    k: int
    score_mode: str
    market_filter_h: int
    vol_target_ann: float


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
    costs_bps: tuple[float, ...] = (20.0, 40.0)
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    bootstrap_iterations: int = 500
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
) -> RunConfig:
    base = {
        "cache_dir": cache_dir,
        "train_start": train_start,
        "train_end": train_end,
        "embargo_start": embargo_start,
        "bootstrap_iterations": bootstrap_iterations,
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


def simulate(closes: pd.DataFrame, cfg: OhlcvConfig, cost_bps: float, bootstrap_iterations: int = 500) -> dict[str, Any]:
    symbols = [c for c in closes.columns if c != "dt"]
    scores = score_matrix(closes, cfg)
    allowed = market_filter(closes, cfg)
    returns = closes[symbols].pct_change().shift(-1)
    weights = {sym: 0.0 for sym in symbols}
    rows = []
    rebalances = []
    symbol_returns = {sym: 0.0 for sym in symbols}
    past_returns: list[float] = []
    scale_sum = 0.0
    scale_count = 0

    for idx in range(len(closes) - 1):
        ts = pd.Timestamp(closes["dt"].iloc[idx])
        if idx % cfg.rebalance_h == 0:
            target = long_only_weights(scores.iloc[idx], cfg, bool(allowed.iloc[idx]))
            if target is not None:
                scale = exposure_scale(past_returns, cfg.vol_target_ann)
                target = {sym: target[sym] * scale for sym in symbols}
                turnover = sum(abs(target[sym] - weights[sym]) for sym in symbols)
                cost = turnover * cost_bps / 10000.0
                weights = target
                scale_sum += scale
                scale_count += 1
            else:
                turnover = 0.0
                cost = 0.0
            rebalances.append({"dt": ts, "turnover": turnover, "cost": cost, "gross_exposure": sum(abs(v) for v in weights.values())})
        else:
            cost = 0.0
        row_rets = returns.iloc[idx].fillna(0.0)
        gross = 0.0
        for sym in symbols:
            value = weights[sym] * float(row_rets[sym])
            gross += value
            symbol_returns[sym] += value
        net = gross - cost
        rows.append({"dt": ts, "net_return": net, "gross_return": gross, "cost": cost, "gross_exposure": sum(abs(v) for v in weights.values())})
        past_returns.append(net)

    ret = pd.DataFrame(rows).set_index("dt")
    reb = pd.DataFrame(rebalances).set_index("dt")
    period_returns = (1.0 + ret["net_return"]).resample(f"{cfg.rebalance_h}h").prod() - 1.0
    daily_returns = (1.0 + ret["net_return"]).resample("1D").prod() - 1.0
    total_return = float((1.0 + ret["net_return"]).prod() - 1.0)
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
    bootstrap_p5 = block_bootstrap_p5(daily_returns, iterations=bootstrap_iterations)
    yearly_positive = sum(1 for row in by_year.values() if row["net_return"] > 0)
    return {
        "config": asdict(cfg),
        "cost_bps": float(cost_bps),
        "total_return": total_return,
        "net_pnl": float(total_return * 10_000.0),
        "sharpe": period_sharpe,
        "max_drawdown": dd,
        "daily_turnover": float(reb["turnover"].resample("1D").sum().mean()) if len(reb) else 0.0,
        "avg_gross_exposure": float(ret["gross_exposure"].mean()) if len(ret) else 0.0,
        "avg_rebalance_scale": float(scale_sum / scale_count) if scale_count else 1.0,
        "yearly": by_year,
        "yearly_positive_count": yearly_positive,
        "symbol_pnl": symbol_pnl,
        "top_positive_symbol_share": float(top_symbol_share),
        "bootstrap_30d_sharpe_p5": bootstrap_p5,
        "equal_weight_benchmark": {
            "sharpe": ew_sharpe,
            "max_drawdown": ew_dd,
            "sharpe_excess": period_sharpe - ew_sharpe,
            "drawdown_ratio": dd / ew_dd if ew_dd > 0 else 1.0,
        },
    }


def advance_checks(cost20: dict[str, Any], cost40: dict[str, Any]) -> dict[str, bool]:
    benchmark = cost20["equal_weight_benchmark"]
    return {
        "sharpe20_ge_1_2": float(cost20["sharpe"]) >= 1.2,
        "max_dd20_le_25pct": float(cost20["max_drawdown"]) <= 0.25,
        "positive_3_of_4_years": int(cost20["yearly_positive_count"]) >= 3,
        "return_2024h1_gt_minus_2pct": float(cost20["yearly"]["2024H1"]["net_return"]) > -0.02,
        "bootstrap_p5_ge_0_25": float(cost20["bootstrap_30d_sharpe_p5"]) >= 0.25,
        "sharpe40_ge_1": float(cost40["sharpe"]) >= 1.0,
        "top_symbol_share_le_60pct": float(cost20["top_positive_symbol_share"]) <= 0.60,
        "benchmark_sharpe_excess_ge_0_10": float(benchmark["sharpe_excess"]) >= 0.10,
        "drawdown_ratio_le_0_80": float(benchmark["drawdown_ratio"]) <= 0.80,
    }


def run_grid(cfg: RunConfig) -> dict[str, Any]:
    start = utc_ts(cfg.train_start)
    end = utc_ts(cfg.train_end)
    embargo = utc_ts(cfg.embargo_start)
    closes = load_close_matrix(Path(cfg.cache_dir), cfg.symbols, start, end, embargo)
    grid = [
        OhlcvConfig(l, s, r, k, mode, mf, vt)
        for l, s, r, k, mode, mf, vt in itertools.product(
            cfg.lookbacks_h,
            cfg.skips_h,
            cfg.rebalances_h,
            cfg.ks,
            cfg.score_modes,
            cfg.market_filters_h,
            cfg.vol_targets_ann,
        )
    ]
    rows = []
    for g in grid:
        cost20 = simulate(closes, g, 20.0, bootstrap_iterations=cfg.bootstrap_iterations)
        cost40 = simulate(closes, g, 40.0, bootstrap_iterations=cfg.bootstrap_iterations)
        checks = advance_checks(cost20, cost40)
        rows.append(
            {
                "config": asdict(g),
                "cost20": cost20,
                "cost40": cost40,
                "advance_checks": checks,
                "advance_passed": all(checks.values()),
            }
        )
    rows.sort(
        key=lambda row: (
            bool(row["advance_passed"]),
            float(row["cost20"]["sharpe"]),
            -float(row["cost20"]["max_drawdown"]),
        ),
        reverse=True,
    )
    pass_rows = [row for row in rows if row["advance_passed"]]
    accepted = len(pass_rows) >= 3
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "xsec_ohlcv_factory_v1_train_only_grid",
        "train_window": {"start": closes["dt"].iloc[0].isoformat(), "end": closes["dt"].iloc[-1].isoformat()},
        "symbols": list(cfg.symbols),
        "config": asdict(cfg),
        "summary": {
            "rows": len(rows),
            "pass_count": len(pass_rows),
            "accepted_train_only": accepted,
            "holdout_authorized": False,
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "top": rows[:25],
        "rows": rows,
    }
    write_json(payload, Path(cfg.out_json))
    if cfg.out_md:
        write_markdown(payload, Path(cfg.out_md))
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
    lines.extend(
        [
            "",
            "## Top Rows",
            "",
            "| cfg | pass | 20bps sh | 40bps sh | DD | 2024H1 | boot p5 | EW excess | DD ratio | top sym |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["top"]:
        cfg = row["config"]
        c20 = row["cost20"]
        c40 = row["cost40"]
        bench = c20["equal_weight_benchmark"]
        label = "L{lookback_h}_S{skip_h}_R{rebalance_h}_K{k}_{score_mode}_MF{market_filter_h}_VT{vol_target_ann}".format(**cfg)
        lines.append(
            "| `{}` | `{}` | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
                label,
                row["advance_passed"],
                c20["sharpe"],
                c40["sharpe"],
                c20["max_drawdown"],
                c20["yearly"]["2024H1"]["net_return"],
                c20["bootstrap_30d_sharpe_p5"],
                bench["sharpe_excess"],
                bench["drawdown_ratio"],
                c20["top_positive_symbol_share"],
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
