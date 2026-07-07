from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .freeze import max_underwater_days
from .report import write_json
from .simulator import load_symbol_1h, utc_ts


@dataclass(frozen=True)
class PairMRConfig:
    y_symbol: str
    x_symbol: str
    beta_lookback: int
    z_lookback: int
    z_entry: float
    z_exit: float
    z_stop: float
    max_hold_bars: int
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    initial_equity: float = 10_000.0
    beta_min: float = 0.25
    beta_max: float = 4.0

    def params_id(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class RunConfig:
    pairs: tuple[tuple[str, str], ...] = (("ETHUSDT", "BTCUSDT"), ("SOLUSDT", "ETHUSDT"), ("LINKUSDT", "ETHUSDT"))
    beta_lookbacks: tuple[int, ...] = (336, 720)
    z_lookbacks: tuple[int, ...] = (168, 336)
    z_entries: tuple[float, ...] = (1.5, 2.0, 2.5)
    z_exits: tuple[float, ...] = (0.25, 0.5)
    z_stops: tuple[float, ...] = (4.0,)
    max_holds: tuple[int, ...] = (72, 168)
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    out_json: str = "artifacts/v9/contract_lab/pair_mr_diag_grid.json"
    out_md: str = "artifacts/v9/contract_lab/pair_mr_diag_grid.md"


def load_pair_bars(cache_dir: Path, y_symbol: str, x_symbol: str, start: pd.Timestamp, end: pd.Timestamp, embargo: pd.Timestamp) -> pd.DataFrame:
    y = load_symbol_1h(cache_dir, y_symbol, start, end, embargo)[["dt", "open", "close"]].rename(
        columns={"open": "open_y", "close": "close_y"}
    )
    x = load_symbol_1h(cache_dir, x_symbol, start, end, embargo)[["dt", "open", "close"]].rename(
        columns={"open": "open_x", "close": "close_x"}
    )
    df = pd.merge(y, x, on="dt", how="inner").sort_values("dt").reset_index(drop=True)
    if df.empty:
        raise SystemExit(f"empty merged pair data for {y_symbol}/{x_symbol}")
    return df


def rolling_beta(y_log: pd.Series, x_log: pd.Series, lookback: int) -> pd.Series:
    x_mean = x_log.rolling(lookback, min_periods=lookback).mean()
    y_mean = y_log.rolling(lookback, min_periods=lookback).mean()
    cov = ((x_log - x_mean) * (y_log - y_mean)).rolling(lookback, min_periods=lookback).mean()
    var = ((x_log - x_mean) ** 2).rolling(lookback, min_periods=lookback).mean()
    return (cov / var).shift(1)


def prepare_pair_features(bars: pd.DataFrame, cfg: PairMRConfig) -> pd.DataFrame:
    df = bars.copy().sort_values("dt").reset_index(drop=True)
    y_log = pd.Series(df["close_y"]).apply(math.log)
    x_log = pd.Series(df["close_x"]).apply(math.log)
    beta = rolling_beta(y_log, x_log, cfg.beta_lookback)
    spread = y_log - beta * x_log
    spread_mean = spread.rolling(cfg.z_lookback, min_periods=cfg.z_lookback).mean().shift(1)
    spread_std = spread.rolling(cfg.z_lookback, min_periods=cfg.z_lookback).std().shift(1)
    df["beta"] = beta
    df["spread"] = spread
    df["z"] = (spread - spread_mean) / spread_std
    return df


def leg_weights(beta: float) -> tuple[float, float]:
    gross = 1.0 + abs(beta)
    return 1.0 / gross, abs(beta) / gross


def top_profit_share(trades: list[dict[str, Any]], net_pnl: float, n: int = 5) -> float:
    if net_pnl <= 0:
        return float("inf")
    winners = sorted((float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) > 0), reverse=True)
    return float(sum(winners[:n]) / net_pnl)


def net_excluding_top_winners(trades: list[dict[str, Any]], n: int = 5) -> float:
    pnls = [float(t["net_pnl"]) for t in trades]
    winners = sorted((p for p in pnls if p > 0), reverse=True)
    return float(sum(pnls) - sum(winners[:n]))


def fold_pnls(trades: list[dict[str, Any]], folds: int = 2) -> list[dict[str, Any]]:
    if not trades:
        return []
    ordered = sorted(trades, key=lambda t: str(t["entry_time"]))
    n = len(ordered)
    out = []
    for fold in range(folds):
        lo = int(fold * n / folds)
        hi = int((fold + 1) * n / folds)
        part = ordered[lo:hi]
        out.append({"fold": fold, "trades": len(part), "net_pnl": float(sum(float(t["net_pnl"]) for t in part))})
    return out


def simulate_pair(bars: pd.DataFrame, cfg: PairMRConfig, cost_multiplier: float = 1.0) -> dict[str, Any]:
    df = prepare_pair_features(bars, cfg)
    cost_rate = (cfg.fee_bps + cfg.slippage_bps) * cost_multiplier / 10000.0
    equity = float(cfg.initial_equity)
    equity_curve = [{"dt": df["dt"].iloc[0].isoformat(), "equity": equity, "event": "start"}] if len(df) else []
    position: dict[str, Any] | None = None
    pending_entry: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    beta_skip_count = 0
    signal_count = 0

    for idx, row in df.iterrows():
        if pending_entry is not None and position is None:
            beta = float(pending_entry["beta"])
            if not math.isfinite(beta) or not cfg.beta_min <= beta <= cfg.beta_max:
                beta_skip_count += 1
            else:
                weight_y, weight_x = leg_weights(beta)
                position = {
                    **pending_entry,
                    "entry_index": idx,
                    "entry_time": row["dt"],
                    "entry_open_y": float(row["open_y"]),
                    "entry_open_x": float(row["open_x"]),
                    "weight_y": weight_y,
                    "weight_x": weight_x,
                    "entry_equity": equity,
                }
            pending_entry = None

        if position is not None:
            held = idx - int(position["entry_index"])
            z = float(row["z"]) if row.get("z") is not None else float("nan")
            reason = None
            if math.isfinite(z) and abs(z) <= cfg.z_exit:
                reason = "z_exit"
            elif math.isfinite(z) and abs(z) >= cfg.z_stop:
                reason = "z_stop"
            elif held >= cfg.max_hold_bars:
                reason = "max_hold"
            if reason is not None:
                side = str(position["side"])
                y_ret = math.log(float(row["open_y"]) / float(position["entry_open_y"]))
                x_ret = math.log(float(row["open_x"]) / float(position["entry_open_x"]))
                if side == "long_spread":
                    gross_ret = float(position["weight_y"]) * y_ret - float(position["weight_x"]) * x_ret
                else:
                    gross_ret = -float(position["weight_y"]) * y_ret + float(position["weight_x"]) * x_ret
                cost_ret = 4.0 * cost_rate
                net_ret = gross_ret - cost_ret
                net_pnl = float(position["entry_equity"]) * net_ret
                equity += net_pnl
                trade = {
                    "pair": f"{cfg.y_symbol}/{cfg.x_symbol}",
                    "params_id": cfg.params_id(),
                    "side": side,
                    "entry_time": position["signal_time"].isoformat(),
                    "fill_time": position["entry_time"].isoformat(),
                    "exit_time": row["dt"].isoformat(),
                    "bars_held": int(held),
                    "z_at_entry": float(position["z"]),
                    "z_at_exit": z,
                    "beta_at_entry": float(position["beta"]),
                    "exit_reason": reason,
                    "gross_ret": gross_ret,
                    "cost_ret": cost_ret,
                    "net_ret": net_ret,
                    "net_pnl": net_pnl,
                    "leg_y_ret": y_ret,
                    "leg_x_ret": x_ret,
                    "weight_y": float(position["weight_y"]),
                    "weight_x": float(position["weight_x"]),
                }
                trades.append(trade)
                equity_curve.append({"dt": row["dt"].isoformat(), "equity": equity, "event": f"exit_{reason}"})
                position = None

        if position is None and pending_entry is None and idx < len(df) - 1:
            z = float(row["z"]) if row.get("z") is not None else float("nan")
            beta = float(row["beta"]) if row.get("beta") is not None else float("nan")
            if math.isfinite(z) and z <= -cfg.z_entry:
                signal_count += 1
                pending_entry = {"signal_time": row["dt"], "signal_index": idx, "side": "long_spread", "z": z, "beta": beta}
            elif math.isfinite(z) and z >= cfg.z_entry:
                signal_count += 1
                pending_entry = {"signal_time": row["dt"], "signal_index": idx, "side": "short_spread", "z": z, "beta": beta}

    if position is not None and len(df):
        last = df.iloc[-1]
        side = str(position["side"])
        y_ret = math.log(float(last["close_y"]) / float(position["entry_open_y"]))
        x_ret = math.log(float(last["close_x"]) / float(position["entry_open_x"]))
        gross_ret = float(position["weight_y"]) * y_ret - float(position["weight_x"]) * x_ret if side == "long_spread" else -float(position["weight_y"]) * y_ret + float(position["weight_x"]) * x_ret
        cost_ret = 4.0 * cost_rate
        net_ret = gross_ret - cost_ret
        net_pnl = float(position["entry_equity"]) * net_ret
        equity += net_pnl
        trades.append(
            {
                "pair": f"{cfg.y_symbol}/{cfg.x_symbol}",
                "params_id": cfg.params_id(),
                "side": side,
                "entry_time": position["signal_time"].isoformat(),
                "fill_time": position["entry_time"].isoformat(),
                "exit_time": last["dt"].isoformat(),
                "bars_held": int(len(df) - 1 - int(position["entry_index"])),
                "z_at_entry": float(position["z"]),
                "z_at_exit": float(last["z"]),
                "beta_at_entry": float(position["beta"]),
                "exit_reason": "train_end",
                "gross_ret": gross_ret,
                "cost_ret": cost_ret,
                "net_ret": net_ret,
                "net_pnl": net_pnl,
                "leg_y_ret": y_ret,
                "leg_x_ret": x_ret,
                "weight_y": float(position["weight_y"]),
                "weight_x": float(position["weight_x"]),
            }
        )
        equity_curve.append({"dt": last["dt"].isoformat(), "equity": equity, "event": "exit_train_end"})

    net_pnl = float(equity - cfg.initial_equity)
    folds = fold_pnls(trades, 2)
    top5 = top_profit_share(trades, net_pnl)
    excised = net_excluding_top_winners(trades)
    underwater = max_underwater_days(equity_curve)
    mean_abs_exposure = float(pd.Series([abs(float(t["weight_y"]) - float(t["weight_x"])) for t in trades]).mean()) if trades else 0.0
    exit_mix = {reason: sum(1 for t in trades if t["exit_reason"] == reason) for reason in sorted({t["exit_reason"] for t in trades})}
    gate_checks = {
        "min_trades": len(trades) >= 30,
        "net_pnl_positive": net_pnl > 0,
        "top5_excised_positive": excised > 0,
        "halves_positive": bool(folds) and all(float(f["net_pnl"]) > 0 for f in folds),
        "max_underwater_days": underwater <= 730,
    }
    return {
        "candidate": asdict(cfg),
        "params_id": cfg.params_id(),
        "pair": f"{cfg.y_symbol}/{cfg.x_symbol}",
        "cost_multiplier": float(cost_multiplier),
        "bar_count": int(len(df)),
        "signal_count": int(signal_count),
        "beta_skip_count": int(beta_skip_count),
        "trade_count": len(trades),
        "net_pnl": net_pnl,
        "final_equity": float(equity),
        "top5_profit_share": top5,
        "top5_excised_net_pnl": excised,
        "max_underwater_days": int(underwater),
        "folds": folds,
        "gate_checks": gate_checks,
        "gate_passed": all(gate_checks.values()),
        "mean_abs_residual_exposure": mean_abs_exposure,
        "mean_hold_bars": float(pd.Series([t["bars_held"] for t in trades]).mean()) if trades else 0.0,
        "median_hold_bars": float(pd.Series([t["bars_held"] for t in trades]).median()) if trades else 0.0,
        "exit_reason_mix": exit_mix,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def compact_result(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in {"trades", "equity_curve"}}


def run_grid(cfg: RunConfig) -> dict[str, Any]:
    start = utc_ts(cfg.train_start)
    end = utc_ts(cfg.train_end)
    embargo = utc_ts(cfg.embargo_start)
    rows = []
    pair_cache: dict[tuple[str, str], pd.DataFrame] = {}
    for y_symbol, x_symbol in cfg.pairs:
        pair_cache[(y_symbol, x_symbol)] = load_pair_bars(Path(cfg.cache_dir), y_symbol, x_symbol, start, end, embargo)
        for beta_l, z_l, z_entry, z_exit, z_stop, hold in itertools.product(
            cfg.beta_lookbacks,
            cfg.z_lookbacks,
            cfg.z_entries,
            cfg.z_exits,
            cfg.z_stops,
            cfg.max_holds,
        ):
            pcfg = PairMRConfig(
                y_symbol=y_symbol,
                x_symbol=x_symbol,
                beta_lookback=beta_l,
                z_lookback=z_l,
                z_entry=z_entry,
                z_exit=z_exit,
                z_stop=z_stop,
                max_hold_bars=hold,
            )
            bars = pair_cache[(y_symbol, x_symbol)]
            cost1 = simulate_pair(bars, pcfg, cost_multiplier=1.0)
            cost2 = simulate_pair(bars, pcfg, cost_multiplier=2.0)
            rows.append(
                {
                    "params_id": pcfg.params_id(),
                    "pair": f"{y_symbol}/{x_symbol}",
                    "candidate": asdict(pcfg),
                    "cost1": compact_result(cost1),
                    "cost2": compact_result(cost2),
                    "passed": bool(cost1["gate_passed"] and cost2["gate_passed"] and cost2["net_pnl"] > 0),
                }
            )
    rows.sort(
        key=lambda r: (
            bool(r["passed"]),
            float(r["cost2"]["net_pnl"]),
            -float(r["cost2"]["top5_profit_share"]) if math.isfinite(float(r["cost2"]["top5_profit_share"])) else -999.0,
        ),
        reverse=True,
    )
    primary = [r for r in rows if r["pair"] == "ETHUSDT/BTCUSDT"]
    primary_net_positive = [r for r in primary if float(r["cost1"]["net_pnl"]) > 0]
    primary_top5_survivors = [r for r in primary if float(r["cost1"]["top5_excised_net_pnl"]) > 0]
    secondary_positive_by_pair = {
        pair: sum(1 for r in rows if r["pair"] == pair and float(r["cost1"]["net_pnl"]) > 0)
        for pair in sorted({r["pair"] for r in rows if r["pair"] != "ETHUSDT/BTCUSDT"})
    }
    accepted = []
    for row in primary:
        if not row["passed"]:
            continue
        params = row["candidate"]
        secondary_ok = any(
            r["pair"] != "ETHUSDT/BTCUSDT"
            and float(r["cost1"]["net_pnl"]) > 0
            and all(r["candidate"][k] == params[k] for k in ["beta_lookback", "z_lookback", "z_entry", "z_exit", "z_stop", "max_hold_bars"])
            for r in rows
        )
        if secondary_ok:
            accepted.append(row["params_id"])
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "pair_mean_reversion_v1_train_only_grid",
        "train_window": {"start": start.isoformat(), "end": end.isoformat()},
        "embargo_start": embargo.isoformat(),
        "config": asdict(cfg),
        "summary": {
            "rows": len(rows),
            "primary_rows": len(primary),
            "primary_net_positive_1x": len(primary_net_positive),
            "primary_net_positive_1x_rate": len(primary_net_positive) / len(primary) if primary else 0.0,
            "primary_top5_excision_survivors": len(primary_top5_survivors),
            "secondary_positive_by_pair": secondary_positive_by_pair,
            "accepted_params": accepted,
            "accepted_count": len(accepted),
            "kill_rule_triggered": (len(primary_net_positive) / len(primary) if primary else 0.0) < 0.05 or len(primary_top5_survivors) == 0,
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
        "# Pair Mean Reversion v1 Train-Only Grid",
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
            "| pair | params | pass | 1x pnl | 2x pnl | trades | top5 excised | underwater | top5 | beta skips |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["top"]:
        c1 = row["cost1"]
        c2 = row["cost2"]
        lines.append(
            "| {pair} | `{pid}` | `{passed}` | {p1:.2f} | {p2:.2f} | {trades} | {excised:.2f} | {uw} | {top5:.3f} | {skip} |".format(
                pair=row["pair"],
                pid=row["params_id"],
                passed=row["passed"],
                p1=c1["net_pnl"],
                p2=c2["net_pnl"],
                trades=c1["trade_count"],
                excised=c1["top5_excised_net_pnl"],
                uw=c1["max_underwater_days"],
                top5=c1["top5_profit_share"],
                skip=c1["beta_skip_count"],
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Train-only beta-hedged pair mean-reversion diagnostic grid")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--out-json", default="artifacts/v9/contract_lab/pair_mr_diag_grid.json")
    ap.add_argument("--out-md", default="artifacts/v9/contract_lab/pair_mr_diag_grid.md")
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
        "pair_mr_v1 done "
        f"rows={payload['summary']['rows']} accepted={payload['summary']['accepted_count']} "
        f"kill={payload['summary']['kill_rule_triggered']} elapsed_sec={time.time() - started:.2f}"
    )
    print(args.out_json)
    print(args.out_md)


if __name__ == "__main__":
    main()
