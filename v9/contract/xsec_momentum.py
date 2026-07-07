from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .metrics import max_drawdown
from .report import write_json
from .simulator import load_symbol_1h, utc_ts


SYMBOLS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT")


@dataclass(frozen=True)
class XSecConfig:
    lookback_h: int
    skip_h: int
    rebalance_h: int
    k: int


@dataclass(frozen=True)
class XSecRiskConfig:
    hysteresis_buffer: int = 0
    vol_target_ann: float = 0.0
    vol_lookback_h: int = 720
    vol_min_scale: float = 0.25
    vol_max_scale: float = 1.0


@dataclass(frozen=True)
class RunConfig:
    symbols: tuple[str, ...] = SYMBOLS
    lookbacks_h: tuple[int, ...] = (72, 168, 336, 720)
    skips_h: tuple[int, ...] = (0, 24)
    rebalances_h: tuple[int, ...] = (24, 72)
    ks: tuple[int, ...] = (1, 2)
    costs_bps: tuple[float, ...] = (10.0, 20.0)
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    out_json: str = "artifacts/v9/contract_lab/xsec_momentum_grid_v1.json"
    out_md: str = "artifacts/v9/contract_lab/xsec_momentum_grid_v1.md"


def load_close_matrix(cache_dir: Path, symbols: tuple[str, ...], start: pd.Timestamp, end: pd.Timestamp, embargo: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        df = load_symbol_1h(cache_dir, symbol, start, end, embargo)[["dt", "close"]].rename(columns={"close": symbol})
        frames.append(df)
    out = frames[0]
    for frame in frames[1:]:
        out = pd.merge(out, frame, on="dt", how="inner")
    out = out.sort_values("dt").dropna().reset_index(drop=True)
    if out.empty:
        raise SystemExit("empty common cross-sectional close matrix")
    return out


def momentum_scores(closes: pd.DataFrame, cfg: XSecConfig) -> pd.DataFrame:
    prices = closes.drop(columns=["dt"])
    return prices.shift(cfg.skip_h) / prices.shift(cfg.skip_h + cfg.lookback_h) - 1.0


def deterministic_ranks(row: pd.Series) -> list[str]:
    return sorted(row.index, key=lambda sym: (-float(row[sym]), sym))


def target_weights(
    score_row: pd.Series,
    cfg: XSecConfig,
    current_weights: dict[str, float] | None = None,
    risk_cfg: XSecRiskConfig | None = None,
) -> dict[str, float] | None:
    if score_row.isna().any():
        return None
    ranked = deterministic_ranks(score_row)
    rank_by_symbol = {sym: idx + 1 for idx, sym in enumerate(ranked)}
    risk_cfg = risk_cfg or XSecRiskConfig()
    current_weights = current_weights or {sym: 0.0 for sym in score_row.index}
    if risk_cfg.hysteresis_buffer > 0:
        long_exit_rank = min(len(ranked), cfg.k + risk_cfg.hysteresis_buffer)
        short_exit_rank = max(1, len(ranked) - cfg.k + 1 - risk_cfg.hysteresis_buffer)
        longs = [
            sym
            for sym in ranked
            if current_weights.get(sym, 0.0) > 0.0 and rank_by_symbol[sym] <= long_exit_rank
        ]
        shorts = [
            sym
            for sym in reversed(ranked)
            if current_weights.get(sym, 0.0) < 0.0 and rank_by_symbol[sym] >= short_exit_rank
        ]
        for sym in ranked:
            if len(longs) >= cfg.k:
                break
            if sym not in longs and sym not in shorts:
                longs.append(sym)
        for sym in reversed(ranked):
            if len(shorts) >= cfg.k:
                break
            if sym not in longs and sym not in shorts:
                shorts.append(sym)
    else:
        longs = ranked[: cfg.k]
        shorts = ranked[-cfg.k :]
    weights = {sym: 0.0 for sym in score_row.index}
    for sym in longs:
        weights[sym] = 1.0 / (2.0 * cfg.k)
    for sym in shorts:
        weights[sym] = -1.0 / (2.0 * cfg.k)
    return weights


def exposure_scale_from_history(past_returns: list[float], risk_cfg: XSecRiskConfig) -> float:
    if risk_cfg.vol_target_ann <= 0.0:
        return 1.0
    lookback = max(2, int(risk_cfg.vol_lookback_h))
    if len(past_returns) < lookback:
        return 1.0
    recent = pd.Series(past_returns[-lookback:])
    ewma_var = float(recent.pow(2.0).ewm(span=lookback, adjust=False).mean().iloc[-1])
    if ewma_var <= 0.0 or not math.isfinite(ewma_var):
        return 1.0
    ann_vol = math.sqrt(ewma_var) * math.sqrt(365.0 * 24.0)
    if ann_vol <= 0.0 or not math.isfinite(ann_vol):
        return 1.0
    scale = risk_cfg.vol_target_ann / ann_vol
    return max(risk_cfg.vol_min_scale, min(risk_cfg.vol_max_scale, scale))


def max_drawdown_from_returns(returns: pd.Series, initial: float = 10_000.0) -> tuple[float, list[dict[str, Any]]]:
    equity = initial
    curve = []
    for ts, ret in returns.items():
        equity *= 1.0 + float(ret)
        curve.append({"dt": ts.isoformat(), "equity": equity})
    return max_drawdown([p["equity"] for p in curve]), curve


def sharpe(period_returns: pd.Series, periods_per_year: float) -> float:
    clean = period_returns.dropna()
    if len(clean) < 2:
        return 0.0
    std = float(clean.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float(clean.mean() / std * math.sqrt(periods_per_year))


def spearman_corr(left: pd.Series, right: pd.Series) -> float:
    if left.nunique(dropna=True) < 2 or right.nunique(dropna=True) < 2:
        return 0.0
    value = left.rank().corr(right.rank())
    return 0.0 if value is None or not math.isfinite(float(value)) else float(value)


def annual_bucket(ts: pd.Timestamp) -> str:
    if ts.year <= 2021:
        return "2021"
    if ts.year >= 2024:
        return "2024H1"
    return str(ts.year)


def simulate_config(
    closes: pd.DataFrame,
    cfg: XSecConfig,
    cost_bps: float,
    risk_cfg: XSecRiskConfig | None = None,
    include_timeseries: bool = False,
) -> dict[str, Any]:
    risk_cfg = risk_cfg or XSecRiskConfig()
    symbols = [c for c in closes.columns if c != "dt"]
    scores = momentum_scores(closes, cfg)
    returns = closes[symbols].pct_change().shift(-1)
    base_weights = {sym: 0.0 for sym in symbols}
    weights = {sym: 0.0 for sym in symbols}
    strategy_rows = []
    rebalance_rows = []
    ic_values = []
    long_ret_sum = 0.0
    short_ret_sum = 0.0
    cost_sum = 0.0
    turnover_sum = 0.0
    rebalance_count = 0
    past_net_returns: list[float] = []
    symbol_ret_sum = {sym: 0.0 for sym in symbols}
    scale_sum = 0.0
    scale_count = 0

    for idx in range(len(closes) - 1):
        ts = pd.Timestamp(closes["dt"].iloc[idx])
        if idx % cfg.rebalance_h == 0:
            new_base_weights = target_weights(scores.iloc[idx], cfg, base_weights, risk_cfg)
            if new_base_weights is not None:
                scale = exposure_scale_from_history(past_net_returns, risk_cfg)
                new_weights = {sym: new_base_weights[sym] * scale for sym in symbols}
                turnover = sum(abs(new_weights[sym] - weights[sym]) for sym in symbols)
                cost = turnover * cost_bps / 10000.0
                base_weights = new_base_weights
                weights = new_weights
                rebalance_count += 1
                turnover_sum += turnover
                cost_sum += cost
                scale_sum += scale
                scale_count += 1
                fwd = (closes[symbols].iloc[min(idx + cfg.rebalance_h, len(closes) - 1)] / closes[symbols].iloc[idx] - 1.0)
                ic_values.append(spearman_corr(scores.iloc[idx], fwd))
            else:
                turnover = 0.0
                cost = 0.0
            rebalance_rows.append({"dt": ts, "cost": cost, "turnover": turnover, "gross_exposure": sum(abs(v) for v in weights.values())})
        else:
            cost = 0.0
        row_rets = returns.iloc[idx].fillna(0.0)
        symbol_parts = {sym: weights[sym] * float(row_rets[sym]) for sym in symbols}
        gross = sum(symbol_parts.values())
        long_part = sum(max(weights[sym], 0.0) * float(row_rets[sym]) for sym in symbols)
        short_part = sum(min(weights[sym], 0.0) * float(row_rets[sym]) for sym in symbols)
        net = gross - cost
        long_ret_sum += long_part
        short_ret_sum += short_part
        for sym, value in symbol_parts.items():
            symbol_ret_sum[sym] += value
        strategy_rows.append(
            {
                "dt": ts,
                "net_return": net,
                "gross_return": gross,
                "long_return": long_part,
                "short_return": short_part,
                "cost": cost,
                "gross_exposure": sum(abs(v) for v in weights.values()),
            }
        )
        past_net_returns.append(net)

    ret = pd.DataFrame(strategy_rows).set_index("dt")
    rebalances = pd.DataFrame(rebalance_rows).set_index("dt")
    period_returns = (1.0 + ret["net_return"]).resample(f"{cfg.rebalance_h}h").prod() - 1.0
    daily_returns = (1.0 + ret["net_return"]).resample("1D").prod() - 1.0
    long_period_returns = ret["long_return"].resample(f"{cfg.rebalance_h}h").sum()
    short_period_returns = ret["short_return"].resample(f"{cfg.rebalance_h}h").sum()
    total_return = float((1.0 + ret["net_return"]).prod() - 1.0)
    dd, curve = max_drawdown_from_returns(ret["net_return"])
    period_sharpe = sharpe(period_returns, 8760.0 / cfg.rebalance_h)
    long_leg_sharpe = sharpe(long_period_returns, 8760.0 / cfg.rebalance_h)
    short_leg_sharpe = sharpe(short_period_returns, 8760.0 / cfg.rebalance_h)
    hit_rate = float((period_returns > 0).mean()) if len(period_returns) else 0.0
    by_year = {}
    ret_by_period = period_returns.copy()
    for bucket in ["2021", "2022", "2023", "2024H1"]:
        subset = ret_by_period[[annual_bucket(ts) == bucket for ts in ret_by_period.index]]
        by_year[bucket] = {
            "periods": int(len(subset)),
            "net_return": float((1.0 + subset).prod() - 1.0) if len(subset) else 0.0,
            "sharpe": sharpe(subset, 8760.0 / cfg.rebalance_h) if len(subset) else 0.0,
        }
    ic_series = pd.Series(ic_values).dropna()
    ic_mean = float(ic_series.mean()) if len(ic_series) else 0.0
    ic_t = float(ic_mean / (ic_series.std(ddof=1) / math.sqrt(len(ic_series)))) if len(ic_series) > 1 and float(ic_series.std(ddof=1)) > 0 else 0.0
    btc = closes[["dt", "BTCUSDT"]].copy() if "BTCUSDT" in closes.columns else None
    beta_to_btc = 0.0
    if btc is not None:
        btc_ret = btc["BTCUSDT"].pct_change().shift(-1).iloc[: len(ret)].fillna(0.0)
        strat = ret["net_return"].reset_index(drop=True)
        var = float(btc_ret.var(ddof=1))
        beta_to_btc = float(strat.cov(btc_ret) / var) if var > 0 else 0.0
    daily_turnover = float(rebalances["turnover"].resample("1D").sum().mean()) if len(rebalances) else 0.0
    cost_bps_day = float(rebalances["cost"].resample("1D").sum().mean() * 10000.0) if len(rebalances) else 0.0
    long_pnl = float(long_ret_sum * 10_000.0)
    short_pnl = float(short_ret_sum * 10_000.0)
    symbol_pnl = {sym: float(value * 10_000.0) for sym, value in symbol_ret_sum.items()}
    positive_symbol_pnl = [max(v, 0.0) for v in symbol_pnl.values()]
    positive_symbol_total = sum(positive_symbol_pnl)
    top_positive_symbol_share = max(positive_symbol_pnl) / positive_symbol_total if positive_symbol_total > 0.0 else 0.0
    pnl = float(total_return * 10_000.0)
    rolling_mean = daily_returns.rolling(180, min_periods=60).mean()
    rolling_std = daily_returns.rolling(180, min_periods=60).std(ddof=1)
    rolling_180d = (rolling_mean / rolling_std.replace(0.0, pd.NA) * math.sqrt(365.0)).dropna()
    rolling_180d_sharpe = {
        "first": float(rolling_180d.iloc[0]) if len(rolling_180d) else 0.0,
        "last": float(rolling_180d.iloc[-1]) if len(rolling_180d) else 0.0,
        "min": float(rolling_180d.min()) if len(rolling_180d) else 0.0,
        "median": float(rolling_180d.median()) if len(rolling_180d) else 0.0,
    }
    yearly_positive = sum(1 for row in by_year.values() if row["net_return"] > 0)
    checks = {
        "sharpe_ge_1": period_sharpe >= 1.0,
        "positive_3_of_4_years": yearly_positive >= 3,
        "ic_t_ge_2": ic_t >= 2.0,
        "sharpe_20bps_ge_0_5": True,
        "legs_non_catastrophic": min(long_pnl, short_pnl) >= -0.5 * max(abs(long_pnl), abs(short_pnl), 1.0),
    }
    return {
        "config": asdict(cfg),
        "risk_config": asdict(risk_cfg),
        "cost_bps": float(cost_bps),
        "total_return": total_return,
        "net_pnl": pnl,
        "sharpe": period_sharpe,
        "max_drawdown": float(dd),
        "hit_rate": hit_rate,
        "daily_turnover": daily_turnover,
        "cost_bps_per_day": cost_bps_day,
        "yearly": by_year,
        "yearly_positive_count": yearly_positive,
        "ic_mean": ic_mean,
        "ic_t_stat": ic_t,
        "long_leg_pnl": long_pnl,
        "short_leg_pnl": short_pnl,
        "long_leg_sharpe": long_leg_sharpe,
        "short_leg_sharpe": short_leg_sharpe,
        "symbol_pnl": symbol_pnl,
        "top_positive_symbol_share": float(top_positive_symbol_share),
        "rolling_180d_sharpe": rolling_180d_sharpe,
        "avg_gross_exposure": float(ret["gross_exposure"].mean()) if len(ret) else 0.0,
        "avg_rebalance_scale": float(scale_sum / scale_count) if scale_count else 1.0,
        "btc_beta": beta_to_btc,
        "rebalance_count": int(rebalance_count),
        "checks": checks,
        "equity_curve": curve,
        **(
            {
                "daily_returns": [
                    {"dt": ts.isoformat(), "net_return": float(value)}
                    for ts, value in daily_returns.items()
                ],
                "period_returns": [
                    {"dt": ts.isoformat(), "net_return": float(value)}
                    for ts, value in period_returns.items()
                ],
            }
            if include_timeseries
            else {}
        ),
    }


def one_step_neighbors(cfg: XSecConfig, grid: list[XSecConfig]) -> list[XSecConfig]:
    values = {
        "lookback_h": sorted({g.lookback_h for g in grid}),
        "skip_h": sorted({g.skip_h for g in grid}),
        "rebalance_h": sorted({g.rebalance_h for g in grid}),
        "k": sorted({g.k for g in grid}),
    }
    neighbors = []
    for other in grid:
        diffs = []
        for field, vals in values.items():
            a = getattr(cfg, field)
            b = getattr(other, field)
            if a == b:
                continue
            if abs(vals.index(a) - vals.index(b)) == 1:
                diffs.append(field)
            else:
                diffs.append("__far__")
        if len(diffs) == 1 and diffs[0] != "__far__":
            neighbors.append(other)
    return neighbors


def run_grid(cfg: RunConfig) -> dict[str, Any]:
    start = utc_ts(cfg.train_start)
    end = utc_ts(cfg.train_end)
    embargo = utc_ts(cfg.embargo_start)
    closes = load_close_matrix(Path(cfg.cache_dir), cfg.symbols, start, end, embargo)
    grid = [
        XSecConfig(l, s, r, k)
        for l, s, r, k in itertools.product(cfg.lookbacks_h, cfg.skips_h, cfg.rebalances_h, cfg.ks)
    ]
    rows = []
    result_by_key: dict[tuple[int, int, int, int, float], dict[str, Any]] = {}
    for g in grid:
        for cost in cfg.costs_bps:
            result = simulate_config(closes, g, cost)
            result_by_key[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, cost)] = result
    for g in grid:
        cost10 = result_by_key[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, 10.0)]
        cost20 = result_by_key[(g.lookback_h, g.skip_h, g.rebalance_h, g.k, 20.0)]
        neighbor_sharpes = [
            result_by_key[(n.lookback_h, n.skip_h, n.rebalance_h, n.k, 10.0)]["sharpe"]
            for n in one_step_neighbors(g, grid)
        ]
        neighbor_median = float(pd.Series(neighbor_sharpes).median()) if neighbor_sharpes else 0.0
        checks = dict(cost10["checks"])
        checks["neighbor_median_sharpe_ge_0_5"] = neighbor_median >= 0.5
        checks["sharpe_20bps_ge_0_5"] = cost20["sharpe"] >= 0.5
        passed = all(checks.values())
        rows.append(
            {
                "config": asdict(g),
                "cost10": {k: v for k, v in cost10.items() if k != "equity_curve"},
                "cost20": {k: v for k, v in cost20.items() if k != "equity_curve"},
                "neighbor_median_sharpe": neighbor_median,
                "checks": checks,
                "passed": passed,
            }
        )
    rows.sort(key=lambda r: (bool(r["passed"]), float(r["neighbor_median_sharpe"]), float(r["cost10"]["sharpe"])), reverse=True)
    passers = [r for r in rows if r["passed"]]
    adjacent_passers = False
    passer_cfgs = [XSecConfig(**r["config"]) for r in passers]
    for p in passer_cfgs:
        if any(n in passer_cfgs for n in one_step_neighbors(p, grid)):
            adjacent_passers = True
            break
    accepted = len(passers) >= 2 and adjacent_passers
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "cross_sectional_momentum_v1_train_only_grid",
        "train_window": {"start": closes["dt"].iloc[0].isoformat(), "end": closes["dt"].iloc[-1].isoformat()},
        "symbols": list(cfg.symbols),
        "config": asdict(cfg),
        "summary": {
            "rows": len(rows),
            "pass_count": len(passers),
            "adjacent_passers": adjacent_passers,
            "accepted": accepted,
            "kill_rule_triggered": not accepted,
            "net_positive_10bps": sum(1 for r in rows if float(r["cost10"]["net_pnl"]) > 0),
            "sharpe_ge_1_10bps": sum(1 for r in rows if float(r["cost10"]["sharpe"]) >= 1.0),
            "ic_t_ge_2": sum(1 for r in rows if float(r["cost10"]["ic_t_stat"]) >= 2.0),
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
        "# Cross-Sectional Momentum v1 Train-Only Grid",
        "",
        f"created_at: `{payload['created_at']}`",
        f"train_window: `{payload['train_window']['start']}` to `{payload['train_window']['end']}`",
        f"symbols: `{', '.join(payload['symbols'])}`",
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
            "| cfg | pass | neigh sharpe | 10bps sharpe | 20bps sharpe | 10bps pnl | 20bps pnl | DD | IC t | beta BTC |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["top"]:
        cfg = row["config"]
        c10 = row["cost10"]
        c20 = row["cost20"]
        label = f"L{cfg['lookback_h']}_S{cfg['skip_h']}_R{cfg['rebalance_h']}_K{cfg['k']}"
        lines.append(
            "| `{label}` | `{passed}` | {neigh:.3f} | {s10:.3f} | {s20:.3f} | {p10:.2f} | {p20:.2f} | {dd:.3f} | {ic:.3f} | {beta:.3f} |".format(
                label=label,
                passed=row["passed"],
                neigh=row["neighbor_median_sharpe"],
                s10=c10["sharpe"],
                s20=c20["sharpe"],
                p10=c10["net_pnl"],
                p20=c20["net_pnl"],
                dd=c10["max_drawdown"],
                ic=c10["ic_t_stat"],
                beta=c10["btc_beta"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Train-only cross-sectional momentum diagnostic grid")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--out-json", default="artifacts/v9/contract_lab/xsec_momentum_grid_v1.json")
    ap.add_argument("--out-md", default="artifacts/v9/contract_lab/xsec_momentum_grid_v1.md")
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    cfg = RunConfig(
        cache_dir=args.cache_dir,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        out_json=args.out_json,
        out_md=args.out_md,
    )
    started = time.time()
    payload = run_grid(cfg)
    print(
        "xsec_momentum_v1 done "
        f"rows={payload['summary']['rows']} pass={payload['summary']['pass_count']} "
        f"accepted={payload['summary']['accepted']} elapsed_sec={time.time() - started:.2f}"
    )
    print(args.out_json)
    print(args.out_md)


if __name__ == "__main__":
    main()
