#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
ANALOG_FEATURES = ("ema_gap", "slow_ema_slope", "ret_6h", "ret_24h", "atr_pct", "rsi", "breakout_pos")
REALISTIC_EXECUTION_MODEL_VERSION = "realistic_v1"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols)


def parse_symbol_side_pairs(raw: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for part in raw.replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"journal allowed pair must be SYMBOL:SIDE, got {item!r}")
        symbol, side = item.split(":", 1)
        side = side.strip().lower()
        if side not in {"long", "short"}:
            raise ValueError(f"journal allowed side must be long or short, got {side!r}")
        pairs.add((symbol.strip().upper(), side))
    return pairs


def parse_timeframe_symbol_side_refs(raw: str, *, default_timeframe: str) -> set[tuple[str, str, str]]:
    refs: set[tuple[str, str, str]] = set()
    for part in raw.replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        fields = [field.strip() for field in item.split(":")]
        if len(fields) == 2:
            timeframe = default_timeframe
            symbol, side = fields
        elif len(fields) == 3:
            timeframe, symbol, side = fields
        else:
            raise ValueError(f"journal blocked pair must be SYMBOL:SIDE or TIMEFRAME:SYMBOL:SIDE, got {item!r}")
        side = side.lower()
        if side not in {"long", "short"}:
            raise ValueError(f"journal blocked side must be long or short, got {side!r}")
        refs.add((timeframe.lower(), symbol.upper(), side))
    return refs


def read_blocked_pair_refs(path: str, *, default_timeframe: str) -> set[tuple[str, str, str]]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        return set()
    rows = payload.get("blocked_pairs", payload) if isinstance(payload, dict) else payload
    refs: set[tuple[str, str, str]] = set()
    if not isinstance(rows, list):
        return refs
    for row in rows:
        if isinstance(row, str):
            refs.update(parse_timeframe_symbol_side_refs(row, default_timeframe=default_timeframe))
            continue
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "").lower()
        timeframe = str(row.get("timeframe") or default_timeframe).lower()
        if symbol and side in {"long", "short"}:
            refs.add((timeframe, symbol, side))
    return refs


def journal_blocked_pair_refs(args: argparse.Namespace) -> set[tuple[str, str, str]]:
    default_timeframe = str(getattr(args, "timeframe", "") or "").lower()
    refs = parse_timeframe_symbol_side_refs(
        getattr(args, "journal_blocked_pairs", ""),
        default_timeframe=default_timeframe,
    )
    refs.update(
        read_blocked_pair_refs(
            getattr(args, "journal_blocked_pairs_json", ""),
            default_timeframe=default_timeframe,
        )
    )
    return refs


def symbols_from_universe(path: str, *, top_n: int, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not path:
        return fallback[:top_n]
    p = Path(path)
    if not p.exists():
        return fallback[:top_n]
    payload = json.loads(p.read_text())
    symbols = tuple(str(symbol).upper() for symbol in payload.get("symbols", []) if symbol)
    return (symbols or fallback)[:top_n]


def open_time_to_dt(series: pd.Series) -> pd.Series:
    sample = float(series.dropna().iloc[0])
    if sample > 10**17:
        unit = "ns"
    elif sample > 10**14:
        unit = "us"
    elif sample > 10**11:
        unit = "ms"
    else:
        unit = "s"
    return pd.to_datetime(series, unit=unit, utc=True, errors="coerce")


def load_symbol_cache(cache_dir: Path, symbol: str, timeframe: str, *, lookback_bars: int) -> pd.DataFrame:
    frames = []
    for path in sorted(cache_dir.glob(f"{symbol.upper()}_{timeframe}_*.parquet")):
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        keep = [col for col in ["open_time", "open", "high", "low", "close", "volume"] if col in frame.columns]
        if "open_time" not in keep:
            continue
        frames.append(frame[keep].copy())
    if not frames:
        return pd.DataFrame(columns=["dt", "open", "high", "low", "close", "volume"])
    out = pd.concat(frames, ignore_index=True)
    out["dt"] = open_time_to_dt(out["open_time"])
    for col in ["open", "high", "low", "close", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["dt", "open", "high", "low", "close"])
    out = out.sort_values("dt").drop_duplicates("dt").tail(int(lookback_bars)).reset_index(drop=True)
    return out


def rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(length, min_periods=length).mean()
    loss = (-delta.clip(upper=0.0)).rolling(length, min_periods=length).mean()
    rs = gain / loss
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.mask((loss == 0) & (gain > 0), 100.0)
    out = out.mask((loss == 0) & (gain == 0), 50.0)
    return out


def atr(frame: pd.DataFrame, length: int) -> pd.Series:
    prev_close = frame["close"].shift(1)
    tr = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(length, min_periods=length).mean()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def interval_minutes(timeframe: str) -> float:
    raw = str(timeframe).strip().lower()
    if len(raw) < 2:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    unit = raw[-1]
    value = float(raw[:-1])
    if value <= 0:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if unit == "s":
        return value / 60.0
    if unit == "m":
        return value
    if unit == "h":
        return value * 60.0
    if unit == "d":
        return value * 1440.0
    raise ValueError(f"unsupported timeframe: {timeframe}")


def bars_for_hours(timeframe: str, hours: float) -> int:
    return max(1, int(round(float(hours) * 60.0 / interval_minutes(timeframe))))


def prepare_feature_frame(frame: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    df = frame.copy().sort_values("dt").reset_index(drop=True)
    ret_6h_bars = bars_for_hours(args.timeframe, 6.0)
    ret_24h_bars = bars_for_hours(args.timeframe, 24.0)
    df["ema_fast"] = df["close"].ewm(span=args.fast_ema, adjust=False, min_periods=args.fast_ema).mean()
    df["ema_slow"] = df["close"].ewm(span=args.slow_ema, adjust=False, min_periods=args.slow_ema).mean()
    df["atr"] = atr(df, args.atr_n)
    df["rsi"] = rsi(df["close"], args.rsi_n)
    df["high_breakout"] = df["high"].rolling(args.breakout_n, min_periods=args.breakout_n).max().shift(1)
    df["low_breakout"] = df["low"].rolling(args.breakout_n, min_periods=args.breakout_n).min().shift(1)
    df["ema_gap"] = df["ema_fast"] / df["ema_slow"] - 1.0
    df["slow_ema_slope"] = df["ema_slow"] / df["ema_slow"].shift(args.slope_n) - 1.0
    df["ret_6h"] = df["close"] / df["close"].shift(ret_6h_bars) - 1.0
    df["ret_24h"] = df["close"] / df["close"].shift(ret_24h_bars) - 1.0
    df["atr_pct"] = df["atr"] / df["close"]
    breakout_range = (df["high_breakout"] - df["low_breakout"]).replace(0.0, pd.NA)
    df["breakout_pos"] = (df["close"] - df["low_breakout"]) / breakout_range
    long_votes = [
        df["close"] > df["ema_slow"],
        df["ema_fast"] > df["ema_slow"],
        df["slow_ema_slope"] > args.min_slope,
        df["ret_24h"] > args.min_ret_24h,
        (df["high_breakout"] > 0) & (df["close"] >= df["high_breakout"] * (1.0 - args.breakout_buffer)),
        df["rsi"] <= args.max_long_rsi,
    ]
    short_votes = [
        df["close"] < df["ema_slow"],
        df["ema_fast"] < df["ema_slow"],
        df["slow_ema_slope"] < -args.min_slope,
        df["ret_24h"] < -args.min_ret_24h,
        (df["low_breakout"] > 0) & (df["close"] <= df["low_breakout"] * (1.0 + args.breakout_buffer)),
        df["rsi"] >= args.min_short_rsi,
    ]
    df["long_votes"] = sum(v.fillna(False).astype(int) for v in long_votes)
    df["short_votes"] = sum(v.fillna(False).astype(int) for v in short_votes)
    return df


def plan_prices(row: pd.Series, args: argparse.Namespace, side: str) -> dict[str, float] | None:
    close = safe_float(row.get("close"))
    latest_atr = safe_float(row.get("atr"))
    if close <= 0.0 or latest_atr <= 0.0:
        return None
    risk_per_unit = max(latest_atr * float(args.stop_atr_mult), close * float(args.min_stop_pct))
    if side == "long":
        stop = close - risk_per_unit
        take_profit = close + risk_per_unit * float(args.reward_r)
        if stop <= 0:
            return None
    else:
        stop = close + risk_per_unit
        take_profit = close - risk_per_unit * float(args.reward_r)
        if take_profit <= 0:
            return None
    return {
        "entry_price": close,
        "stop_loss": stop,
        "take_profit": take_profit,
        "risk_per_unit": risk_per_unit,
    }


def simulate_outcome(
    df: pd.DataFrame,
    *,
    start_idx: int,
    side: str,
    entry: float,
    stop: float,
    take_profit: float,
    horizon_bars: int,
) -> dict[str, Any]:
    future = df.iloc[start_idx + 1 : start_idx + 1 + int(horizon_bars)].copy()
    risk = (entry - stop) if side == "long" else (stop - entry)
    if future.empty or risk <= 0:
        return {"status": "pending", "exit_reason": "insufficient_future_bars", "r_multiple": None}
    for offset, row in enumerate(future.itertuples(index=False), start=1):
        high = safe_float(getattr(row, "high", 0.0))
        low = safe_float(getattr(row, "low", 0.0))
        dt = getattr(row, "dt")
        if side == "long":
            hit_stop = low <= stop
            hit_tp = high >= take_profit
            if hit_stop:
                return {
                    "status": "completed",
                    "exit_reason": "stop_loss",
                    "r_multiple": -1.0,
                    "exit_dt": dt.isoformat(),
                    "bars_held": offset,
                }
            if hit_tp:
                return {
                    "status": "completed",
                    "exit_reason": "take_profit",
                    "r_multiple": float((take_profit - entry) / risk),
                    "exit_dt": dt.isoformat(),
                    "bars_held": offset,
                }
        else:
            hit_stop = high >= stop
            hit_tp = low <= take_profit
            if hit_stop:
                return {
                    "status": "completed",
                    "exit_reason": "stop_loss",
                    "r_multiple": -1.0,
                    "exit_dt": dt.isoformat(),
                    "bars_held": offset,
                }
            if hit_tp:
                return {
                    "status": "completed",
                    "exit_reason": "take_profit",
                    "r_multiple": float((entry - take_profit) / risk),
                    "exit_dt": dt.isoformat(),
                    "bars_held": offset,
                }
    if len(future) < int(horizon_bars):
        return {"status": "pending", "exit_reason": "waiting_for_horizon", "r_multiple": None}
    last = future.iloc[-1]
    exit_price = safe_float(last["close"])
    r_mult = (exit_price - entry) / risk if side == "long" else (entry - exit_price) / risk
    return {
        "status": "completed",
        "exit_reason": "horizon_close",
        "r_multiple": float(r_mult),
        "exit_dt": last["dt"].isoformat(),
        "bars_held": int(horizon_bars),
    }


def execution_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": REALISTIC_EXECUTION_MODEL_VERSION,
        "timeframe": str(getattr(args, "timeframe", "1h")),
        "fee_bps_per_side": float(getattr(args, "paper_fee_bps", 5.0)),
        "slippage_bps": float(getattr(args, "paper_slippage_bps", 2.0)),
        "entry_latency_bars": int(getattr(args, "paper_entry_latency_bars", 1)),
        "max_entry_drift_bps": float(getattr(args, "paper_max_entry_drift_bps", 80.0)),
        "funding_bps_per_8h": float(getattr(args, "paper_funding_bps_per_8h", 1.0)),
        "partial_fill_frac": float(getattr(args, "paper_partial_fill_frac", 1.0)),
        "min_fill_frac": float(getattr(args, "paper_min_fill_frac", 1.0)),
    }


def execution_config_from_record(record: dict[str, Any]) -> dict[str, Any]:
    config = dict(record.get("paper_execution") or {})
    defaults = {
        "fee_bps_per_side": 5.0,
        "slippage_bps": 2.0,
        "entry_latency_bars": 1,
        "max_entry_drift_bps": 80.0,
        "funding_bps_per_8h": 1.0,
        "partial_fill_frac": 1.0,
        "min_fill_frac": 1.0,
    }
    for key, value in defaults.items():
        if isinstance(value, float):
            config[key] = safe_float(config.get(key), value)
        else:
            config[key] = int(safe_float(config.get(key), float(value)))
    return config


def rate_from_bps(value: Any) -> float:
    return safe_float(value) / 10000.0


def adverse_entry_fill(side: str, reference_price: float, slippage_bps: float) -> float:
    slip = rate_from_bps(slippage_bps)
    if side == "long":
        return reference_price * (1.0 + slip)
    return reference_price * (1.0 - slip)


def adverse_exit_fill(side: str, reference_price: float, slippage_bps: float) -> float:
    slip = rate_from_bps(slippage_bps)
    if side == "long":
        return reference_price * (1.0 - slip)
    return reference_price * (1.0 + slip)


def completed_realistic_outcome(
    *,
    side: str,
    entry_fill: float,
    exit_reference: float,
    exit_reason: str,
    exit_dt: pd.Timestamp,
    bars_held: int,
    risk_per_unit: float,
    config: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:
    slippage_bps = safe_float(config.get("slippage_bps"), 2.0)
    fee_bps = safe_float(config.get("fee_bps_per_side"), 5.0)
    funding_bps = safe_float(config.get("funding_bps_per_8h"), 1.0)
    exit_fill = adverse_exit_fill(side, exit_reference, slippage_bps)
    gross_pnl = exit_fill - entry_fill if side == "long" else entry_fill - exit_fill
    gross_r = gross_pnl / risk_per_unit if risk_per_unit > 0.0 else 0.0
    fee_cost = (abs(entry_fill) + abs(exit_fill)) * rate_from_bps(fee_bps)
    hold_hours = max(0.0, float(bars_held) * interval_minutes(timeframe) / 60.0)
    funding_cost = abs(entry_fill) * rate_from_bps(funding_bps) * (hold_hours / 8.0)
    net_pnl = gross_pnl - fee_cost - funding_cost
    net_r = net_pnl / risk_per_unit if risk_per_unit > 0.0 else 0.0
    return {
        "status": "completed",
        "exit_reason": exit_reason,
        "r_multiple": float(net_r),
        "gross_r_multiple": float(gross_r),
        "exit_dt": exit_dt.isoformat(),
        "bars_held": int(bars_held),
        "entry_fill_price": float(entry_fill),
        "exit_reference_price": float(exit_reference),
        "exit_fill_price": float(exit_fill),
        "fee_bps_per_side": float(fee_bps),
        "fee_cost_per_unit": float(fee_cost),
        "slippage_bps": float(slippage_bps),
        "funding_bps_per_8h": float(funding_bps),
        "funding_cost_per_unit": float(funding_cost),
        "net_pnl_per_unit": float(net_pnl),
        "gross_pnl_per_unit": float(gross_pnl),
    }


def simulate_realistic_exit(
    df: pd.DataFrame,
    *,
    entry_idx: int,
    side: str,
    entry_fill: float,
    stop: float,
    take_profit: float,
    horizon_bars: int,
    config: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:
    future = df.iloc[entry_idx + 1 : entry_idx + 1 + int(horizon_bars)].copy()
    risk = (entry_fill - stop) if side == "long" else (stop - entry_fill)
    if future.empty or risk <= 0:
        return {"status": "pending", "exit_reason": "insufficient_future_bars", "r_multiple": None}
    for offset, row in enumerate(future.itertuples(index=False), start=1):
        high = safe_float(getattr(row, "high", 0.0))
        low = safe_float(getattr(row, "low", 0.0))
        dt = getattr(row, "dt")
        if side == "long":
            if low <= stop:
                return completed_realistic_outcome(
                    side=side,
                    entry_fill=entry_fill,
                    exit_reference=stop,
                    exit_reason="stop_loss",
                    exit_dt=dt,
                    bars_held=offset,
                    risk_per_unit=risk,
                    config=config,
                    timeframe=timeframe,
                )
            if high >= take_profit:
                return completed_realistic_outcome(
                    side=side,
                    entry_fill=entry_fill,
                    exit_reference=take_profit,
                    exit_reason="take_profit",
                    exit_dt=dt,
                    bars_held=offset,
                    risk_per_unit=risk,
                    config=config,
                    timeframe=timeframe,
                )
        else:
            if high >= stop:
                return completed_realistic_outcome(
                    side=side,
                    entry_fill=entry_fill,
                    exit_reference=stop,
                    exit_reason="stop_loss",
                    exit_dt=dt,
                    bars_held=offset,
                    risk_per_unit=risk,
                    config=config,
                    timeframe=timeframe,
                )
            if low <= take_profit:
                return completed_realistic_outcome(
                    side=side,
                    entry_fill=entry_fill,
                    exit_reference=take_profit,
                    exit_reason="take_profit",
                    exit_dt=dt,
                    bars_held=offset,
                    risk_per_unit=risk,
                    config=config,
                    timeframe=timeframe,
                )
    if len(future) < int(horizon_bars):
        return {"status": "pending", "exit_reason": "waiting_for_horizon", "r_multiple": None}
    last = future.iloc[-1]
    return completed_realistic_outcome(
        side=side,
        entry_fill=entry_fill,
        exit_reference=safe_float(last["close"]),
        exit_reason="horizon_close",
        exit_dt=last["dt"],
        bars_held=int(horizon_bars),
        risk_per_unit=risk,
        config=config,
        timeframe=timeframe,
    )


def historical_analog_evidence(df: pd.DataFrame, args: argparse.Namespace, *, signal: str) -> dict[str, Any]:
    horizon = int(args.analog_horizon_bars)
    if signal not in {"long", "short"}:
        return {"enabled": True, "supported": False, "reason": "no_signal"}
    if len(df) < max(args.slow_ema, args.breakout_n, args.atr_n, args.rsi_n) + horizon + 10:
        return {"enabled": True, "supported": False, "reason": "insufficient_history"}
    latest = df.iloc[-1]
    target = pd.Series({feature: safe_float(latest.get(feature), float("nan")) for feature in ANALOG_FEATURES})
    if not target.apply(math.isfinite).all():
        return {"enabled": True, "supported": False, "reason": "invalid_current_features"}

    max_idx = len(df) - 1 - horizon
    history = df.iloc[:max_idx].copy()
    if signal == "long":
        history = history[(history["long_votes"] >= args.min_votes) & (history["long_votes"] > history["short_votes"])]
    else:
        history = history[
            (history["short_votes"] >= args.min_votes)
            & (history["short_votes"] > history["long_votes"])
        ]
    history = history.dropna(subset=list(ANALOG_FEATURES) + ["atr", "close"])
    if history.empty:
        return {"enabled": True, "supported": False, "reason": "no_same_side_analogs"}

    features = history.loc[:, ANALOG_FEATURES].astype(float)
    scales = features.std(ddof=0).replace(0.0, float("nan")).fillna(1.0)
    distances = (((features - target) / scales) ** 2).mean(axis=1).pow(0.5)
    nearest = history.assign(analog_distance=distances).nsmallest(int(args.analog_top_k), "analog_distance")
    outcomes = []
    for idx, row in nearest.iterrows():
        prices = plan_prices(row, args, signal)
        if not prices:
            continue
        outcome = simulate_outcome(
            df,
            start_idx=int(idx),
            side=signal,
            entry=prices["entry_price"],
            stop=prices["stop_loss"],
            take_profit=prices["take_profit"],
            horizon_bars=horizon,
        )
        if outcome.get("r_multiple") is None:
            continue
        outcomes.append(
            {
                "dt": row["dt"].isoformat(),
                "distance": float(row["analog_distance"]),
                "entry": float(prices["entry_price"]),
                "exit_reason": outcome["exit_reason"],
                "r_multiple": float(outcome["r_multiple"]),
                "bars_held": int(outcome.get("bars_held") or 0),
            }
        )
    used = len(outcomes)
    if not outcomes:
        return {
            "enabled": True,
            "supported": False,
            "reason": "no_completed_analog_outcomes",
            "candidate_count": int(len(history)),
            "used_count": 0,
        }
    r_values = [float(row["r_multiple"]) for row in outcomes]
    tp_count = sum(1 for row in outcomes if row["exit_reason"] == "take_profit")
    stop_count = sum(1 for row in outcomes if row["exit_reason"] == "stop_loss")
    profitable_count = sum(1 for value in r_values if value > 0.0)
    hit_rate = tp_count / used
    profitable_rate = profitable_count / used
    expectancy = sum(r_values) / used
    supported = (
        used >= int(args.min_analog_samples)
        and (hit_rate >= float(args.min_analog_hit_rate) or profitable_rate >= float(args.min_analog_profitable_rate))
        and expectancy >= float(args.min_analog_expectancy_r)
    )
    return {
        "enabled": True,
        "supported": bool(supported),
        "reason": "analog_support_pass" if supported else "analog_support_fail",
        "candidate_count": int(len(history)),
        "used_count": used,
        "top_k": int(args.analog_top_k),
        "horizon_bars": horizon,
        "take_profit_first_count": tp_count,
        "stop_loss_first_count": stop_count,
        "profitable_count": profitable_count,
        "hit_rate": float(hit_rate),
        "profitable_rate": float(profitable_rate),
        "expectancy_r": float(expectancy),
        "median_r": float(pd.Series(r_values).median()),
        "worst_r": float(min(r_values)),
        "best_r": float(max(r_values)),
        "sample": outcomes[:5],
        "thresholds": {
            "min_analog_samples": int(args.min_analog_samples),
            "min_analog_hit_rate": float(args.min_analog_hit_rate),
            "min_analog_profitable_rate": float(args.min_analog_profitable_rate),
            "min_analog_expectancy_r": float(args.min_analog_expectancy_r),
        },
    }


def classify_signal(frame: pd.DataFrame, args: argparse.Namespace, *, symbol: str) -> dict[str, Any]:
    min_bars = max(
        args.slow_ema,
        args.atr_n,
        args.rsi_n,
        args.breakout_n,
        args.slope_n,
        bars_for_hours(args.timeframe, 24.0),
        25,
    ) + 2
    if len(frame) < min_bars:
        return {
            "symbol": symbol,
            "status": "insufficient_data",
            "signal": "none",
            "reason": f"need_at_least_{min_bars}_bars",
            "paper_plan": None,
        }
    df = prepare_feature_frame(frame, args)
    latest = df.iloc[-1]
    previous = df.iloc[-2]
    close = safe_float(latest["close"])
    latest_atr = safe_float(latest["atr"])
    if close <= 0.0 or latest_atr <= 0.0:
        return {
            "symbol": symbol,
            "status": "insufficient_data",
            "signal": "none",
            "reason": "missing_close_or_atr",
            "paper_plan": None,
        }

    long_votes = {
        "close_above_slow_ema": close > safe_float(latest["ema_slow"]),
        "fast_above_slow_ema": safe_float(latest["ema_fast"]) > safe_float(latest["ema_slow"]),
        "slow_ema_slope_positive": safe_float(latest["slow_ema_slope"]) > args.min_slope,
        "ret_24h_positive": safe_float(latest["ret_24h"]) > args.min_ret_24h,
        "near_or_above_breakout": safe_float(latest["high_breakout"]) > 0
        and close >= safe_float(latest["high_breakout"]) * (1.0 - args.breakout_buffer),
        "rsi_not_overheated": safe_float(latest["rsi"], 50.0) <= args.max_long_rsi,
    }
    short_votes = {
        "close_below_slow_ema": close < safe_float(latest["ema_slow"]),
        "fast_below_slow_ema": safe_float(latest["ema_fast"]) < safe_float(latest["ema_slow"]),
        "slow_ema_slope_negative": safe_float(latest["slow_ema_slope"]) < -args.min_slope,
        "ret_24h_negative": safe_float(latest["ret_24h"]) < -args.min_ret_24h,
        "near_or_below_breakdown": safe_float(latest["low_breakout"]) > 0
        and close <= safe_float(latest["low_breakout"]) * (1.0 + args.breakout_buffer),
        "rsi_not_oversold": safe_float(latest["rsi"], 50.0) >= args.min_short_rsi,
    }
    long_score = int(sum(1 for value in long_votes.values() if value))
    short_score = int(sum(1 for value in short_votes.values() if value))
    signal = "none"
    votes: dict[str, bool] = {}
    if long_score >= args.min_votes and long_score > short_score:
        signal = "long"
        votes = long_votes
    elif short_score >= args.min_votes and short_score > long_score:
        signal = "short"
        votes = short_votes

    metrics = {
        "ema_fast": safe_float(latest["ema_fast"]),
        "ema_slow": safe_float(latest["ema_slow"]),
        "ema_gap": safe_float(latest["ema_gap"]),
        "slow_ema_slope": safe_float(latest["slow_ema_slope"]),
        "ret_6h": safe_float(latest["ret_6h"]),
        "ret_24h": safe_float(latest["ret_24h"]),
        "atr": latest_atr,
        "atr_pct": safe_float(latest["atr_pct"]),
        "rsi": safe_float(latest["rsi"], 50.0),
        "breakout_pos": safe_float(latest["breakout_pos"]),
        "long_votes": long_score,
        "short_votes": short_score,
    }
    if signal == "none":
        return {
            "symbol": symbol,
            "status": "ok",
            "signal": "none",
            "reason": f"no_consensus long_votes={long_score} short_votes={short_score}",
            "latest_dt": latest["dt"].isoformat(),
            "close": close,
            "metrics": metrics,
            "analog_evidence": {"enabled": True, "supported": False, "reason": "no_signal"},
            "paper_plan": None,
        }

    prices = plan_prices(latest, args, signal)
    if not prices:
        return {
            "symbol": symbol,
            "status": "invalid_plan",
            "signal": "none",
            "reason": "invalid_stop_or_take_profit",
            "paper_plan": None,
        }
    analog = historical_analog_evidence(df, args, signal=signal)
    plan = {
        "side": signal,
        "entry_reference": f"latest_closed_{args.timeframe}_close_next_bar_open_simulated",
        **prices,
        "reward_r": float(args.reward_r),
        "risk_per_trade": float(args.risk_per_trade),
        "leverage_cap": float(args.leverage_cap),
        "historical_analog_supported": bool(analog.get("supported")),
        "order_intent": {
            "entry": "paper_only_no_order",
            "stop": "paper_only_no_order",
            "take_profit": "paper_only_no_order",
            "reduce_only": True,
        },
    }
    return {
        "symbol": symbol,
        "status": "ok",
        "signal": signal,
        "reason": f"{signal}_consensus votes={long_score if signal == 'long' else short_score}",
        "latest_dt": latest["dt"].isoformat(),
        "previous_dt": previous["dt"].isoformat(),
        "close": close,
        "metrics": {**metrics, "votes": votes},
        "analog_evidence": analog,
        "paper_plan": plan,
    }


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    plan = row.get("paper_plan") or {}
    metrics = row.get("metrics") or {}
    analog = row.get("analog_evidence") or {}
    signal = row.get("signal")
    return (
        signal in {"long", "short"},
        bool(analog.get("supported")),
        float(analog.get("expectancy_r") or -999.0),
        float(analog.get("hit_rate") or 0.0),
        max(int(metrics.get("long_votes") or 0), int(metrics.get("short_votes") or 0)),
        abs(float(metrics.get("ema_gap") or 0.0)),
        abs(float(metrics.get("ret_24h") or 0.0)),
        -float(plan.get("risk_per_unit") or 0.0),
    )


def signal_id(row: dict[str, Any]) -> str:
    plan = row.get("paper_plan") or {}
    raw = "|".join(
        [
            str(row.get("symbol")),
            str(row.get("signal")),
            str(row.get("latest_dt")),
            f"{safe_float(plan.get('entry_price')):.10f}",
            f"{safe_float(plan.get('stop_loss')):.10f}",
            f"{safe_float(plan.get('take_profit')):.10f}",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def journal_record_from_row(
    row: dict[str, Any],
    *,
    updated_at: str,
    horizon_bars: int,
    execution_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = row["paper_plan"]
    analog = row.get("analog_evidence") or {}
    config = execution_config or {}
    return {
        "kind": "contract_latest_market_signal_paper_journal_v1",
        "signal_id": signal_id(row),
        "created_at": updated_at,
        "updated_at": updated_at,
        "status": "pending_entry",
        "execution_model_version": REALISTIC_EXECUTION_MODEL_VERSION,
        "paper_execution": config,
        "symbol": row["symbol"],
        "side": row["signal"],
        "timeframe": str(config.get("timeframe") or ""),
        "signal_dt": row["latest_dt"],
        "latest_dt": row["latest_dt"],
        "planned_entry_price": float(plan["entry_price"]),
        "entry_price": None,
        "entry_reference": plan.get("entry_reference"),
        "stop_loss": float(plan["stop_loss"]),
        "take_profit": float(plan["take_profit"]),
        "planned_risk_per_unit": float(plan["risk_per_unit"]),
        "risk_per_unit": None,
        "reward_r": float(plan["reward_r"]),
        "risk_per_trade": float(plan["risk_per_trade"]),
        "leverage_cap": float(plan["leverage_cap"]),
        "signal_reason": row.get("reason"),
        "analog_supported": bool(analog.get("supported")),
        "analog_reason": analog.get("reason"),
        "analog_used_count": int(analog.get("used_count") or 0),
        "analog_hit_rate": safe_float(analog.get("hit_rate")),
        "analog_profitable_rate": safe_float(analog.get("profitable_rate")),
        "analog_expectancy_r": safe_float(analog.get("expectancy_r")),
        "outcome_horizon_bars": int(horizon_bars),
        "outcome": None,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def read_journal(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def write_journal(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records)
    path.write_text(text + ("\n" if text else ""))


def migrate_legacy_record_to_realistic(
    record: dict[str, Any],
    *,
    execution_config: dict[str, Any],
    updated_at: str,
) -> bool:
    if record.get("execution_model_version"):
        return False
    status = str(record.get("status") or "")
    if status not in {"open", "completed"}:
        return False
    legacy_entry = safe_float(record.get("entry_price"), float("nan"))
    if pd.isna(legacy_entry) or legacy_entry <= 0.0:
        return False
    legacy_risk = safe_float(record.get("risk_per_unit"), float("nan"))
    record["legacy_status"] = status
    record["legacy_entry_price"] = float(legacy_entry)
    if not pd.isna(legacy_risk):
        record["legacy_risk_per_unit"] = float(legacy_risk)
    if record.get("outcome") is not None:
        record["legacy_outcome"] = record.get("outcome")
    record["updated_at"] = updated_at
    record["status"] = "pending_entry"
    record["execution_model_version"] = REALISTIC_EXECUTION_MODEL_VERSION
    record["paper_execution"] = execution_config
    record["timeframe"] = str(execution_config.get("timeframe") or record.get("timeframe") or "")
    record["signal_dt"] = record.get("signal_dt") or record.get("latest_dt")
    record["planned_entry_price"] = float(legacy_entry)
    record["entry_price"] = None
    if not pd.isna(legacy_risk):
        record["planned_risk_per_unit"] = float(legacy_risk)
    record["risk_per_unit"] = None
    record["outcome"] = None
    for key in [
        "entry_dt",
        "entry_reference_price",
        "entry_bar_index",
        "entry_drift_bps",
        "partial_fill_frac",
        "entry_fee_cost_per_unit",
    ]:
        record.pop(key, None)
    return True


def skip_realistic_record(record: dict[str, Any], *, updated_at: str, reason: str, **extra: Any) -> None:
    record["status"] = "skipped"
    record["updated_at"] = updated_at
    record["outcome"] = {
        "status": "skipped",
        "exit_reason": reason,
        "r_multiple": None,
        **extra,
    }


def update_realistic_record_outcome(record: dict[str, Any], frame: pd.DataFrame, *, updated_at: str) -> bool:
    if record.get("status") in {"completed", "skipped"}:
        return False
    if frame.empty:
        return False

    signal_dt = parse_utc_timestamp(record.get("signal_dt") or record.get("latest_dt"))
    candidates = frame.index[frame["dt"] == signal_dt]
    if len(candidates) == 0:
        return False

    config = execution_config_from_record(record)
    side = str(record.get("side"))
    signal_idx = int(candidates[-1])
    entry_latency = max(0, int(config.get("entry_latency_bars") or 0))
    entry_idx = signal_idx + entry_latency
    if entry_idx >= len(frame):
        return False

    modified = False
    if record.get("status") == "pending_entry":
        partial_fill_frac = safe_float(config.get("partial_fill_frac"), 1.0)
        min_fill_frac = safe_float(config.get("min_fill_frac"), 1.0)
        if partial_fill_frac < min_fill_frac:
            skip_realistic_record(
                record,
                updated_at=updated_at,
                reason="partial_fill_reject",
                partial_fill_frac=float(partial_fill_frac),
                min_fill_frac=float(min_fill_frac),
            )
            return True

        entry_row = frame.iloc[entry_idx]
        entry_reference = safe_float(entry_row.get("open"))
        planned_entry = safe_float(record.get("planned_entry_price") or record.get("entry_price"))
        if entry_reference <= 0.0 or planned_entry <= 0.0:
            skip_realistic_record(record, updated_at=updated_at, reason="invalid_entry_reference")
            return True

        entry_fill = adverse_entry_fill(side, entry_reference, safe_float(config.get("slippage_bps"), 2.0))
        drift_bps = abs(entry_fill / planned_entry - 1.0) * 10000.0
        max_drift_bps = safe_float(config.get("max_entry_drift_bps"), 80.0)
        if max_drift_bps > 0.0 and drift_bps > max_drift_bps:
            skip_realistic_record(
                record,
                updated_at=updated_at,
                reason="entry_drift_reject",
                planned_entry_price=float(planned_entry),
                entry_reference_price=float(entry_reference),
                entry_fill_price=float(entry_fill),
                entry_drift_bps=float(drift_bps),
                max_entry_drift_bps=float(max_drift_bps),
            )
            return True

        stop = safe_float(record.get("stop_loss"))
        risk = entry_fill - stop if side == "long" else stop - entry_fill
        if risk <= 0.0:
            skip_realistic_record(
                record,
                updated_at=updated_at,
                reason="invalid_post_fill_risk",
                entry_fill_price=float(entry_fill),
                stop_loss=float(stop),
            )
            return True

        entry_dt = entry_row["dt"]
        record["status"] = "open"
        record["updated_at"] = updated_at
        record["entry_price"] = float(entry_fill)
        record["entry_dt"] = entry_dt.isoformat()
        record["entry_reference_price"] = float(entry_reference)
        record["entry_bar_index"] = int(entry_idx)
        record["entry_drift_bps"] = float(drift_bps)
        record["risk_per_unit"] = float(risk)
        record["partial_fill_frac"] = float(partial_fill_frac)
        record["entry_fee_cost_per_unit"] = float(abs(entry_fill) * rate_from_bps(config.get("fee_bps_per_side")))
        modified = True

    if record.get("status") != "open":
        return modified

    entry_idx = int(record.get("entry_bar_index") or entry_idx)
    outcome = simulate_realistic_exit(
        frame,
        entry_idx=entry_idx,
        side=side,
        entry_fill=float(record["entry_price"]),
        stop=float(record["stop_loss"]),
        take_profit=float(record["take_profit"]),
        horizon_bars=int(record.get("outcome_horizon_bars") or 24),
        config=config,
        timeframe=str(record.get("timeframe") or config.get("timeframe") or "1h"),
    )
    if outcome.get("status") != "completed":
        return modified
    record["status"] = "completed"
    record["updated_at"] = updated_at
    record["outcome"] = outcome
    return True


def update_record_outcome(record: dict[str, Any], frame: pd.DataFrame, *, updated_at: str) -> bool:
    if record.get("execution_model_version") == REALISTIC_EXECUTION_MODEL_VERSION:
        return update_realistic_record_outcome(record, frame, updated_at=updated_at)
    if record.get("status") in {"completed", "skipped"}:
        return False
    if frame.empty:
        return False
    signal_dt = parse_utc_timestamp(record["latest_dt"])
    candidates = frame.index[frame["dt"] == signal_dt]
    if len(candidates) == 0:
        return False
    start_idx = int(candidates[-1])
    outcome = simulate_outcome(
        frame,
        start_idx=start_idx,
        side=str(record["side"]),
        entry=float(record["entry_price"]),
        stop=float(record["stop_loss"]),
        take_profit=float(record["take_profit"]),
        horizon_bars=int(record.get("outcome_horizon_bars") or 24),
    )
    if outcome.get("status") != "completed":
        return False
    record["status"] = "completed"
    record["updated_at"] = updated_at
    record["outcome"] = outcome
    return True


def update_journal(payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.journal_record_mode == "off":
        return {"enabled": False}
    path = Path(args.journal_jsonl)
    records = read_journal(path)
    seen = {record.get("signal_id") for record in records}
    execution_config = execution_config_from_args(args)
    allowed_pairs = parse_symbol_side_pairs(getattr(args, "journal_allowed_pairs", ""))
    blocked_pairs = journal_blocked_pair_refs(args)
    max_active_per_pair = int(getattr(args, "journal_max_active_per_pair", 0) or 0)
    updated = 0
    migrated = 0
    blocked_candidates = 0
    by_symbol: dict[str, pd.DataFrame] = {}

    for record in records:
        migrate_mode = getattr(args, "paper_migrate_legacy_records", "all")
        should_migrate = (
            migrate_mode == "all"
            or (migrate_mode == "active" and record.get("status") == "open")
        )
        if should_migrate and migrate_legacy_record_to_realistic(
            record,
            execution_config=execution_config,
            updated_at=payload["updated_at"],
        ):
            migrated += 1
        if record.get("status") in {"completed", "skipped"}:
            continue
        symbol = str(record.get("symbol", "")).upper()
        if not symbol:
            continue
        if symbol not in by_symbol:
            by_symbol[symbol] = load_symbol_cache(
                Path(args.cache_dir),
                symbol,
                args.timeframe,
                lookback_bars=args.lookback_bars,
            )
        if update_record_outcome(record, by_symbol[symbol], updated_at=payload["updated_at"]):
            updated += 1

    active_by_pair: dict[tuple[str, str], int] = {}
    for record in records:
        if record.get("status") not in {"pending_entry", "open"}:
            continue
        pair = (str(record.get("symbol", "")).upper(), str(record.get("side", "")).lower())
        active_by_pair[pair] = active_by_pair.get(pair, 0) + 1

    new_records = []
    for row in payload["rows"]:
        if row.get("signal") not in {"long", "short"} or not row.get("paper_plan"):
            continue
        pair = (str(row.get("symbol", "")).upper(), str(row.get("signal")).lower())
        pair_ref = (str(getattr(args, "timeframe", "") or "").lower(), pair[0], pair[1])
        if allowed_pairs and pair not in allowed_pairs:
            continue
        if pair_ref in blocked_pairs:
            blocked_candidates += 1
            continue
        if max_active_per_pair > 0 and active_by_pair.get(pair, 0) >= max_active_per_pair:
            continue
        analog = row.get("analog_evidence") or {}
        if args.journal_record_mode == "analog_supported" and not analog.get("supported"):
            continue
        sid = signal_id(row)
        if sid in seen:
            continue
        seen.add(sid)
        new_records.append(
            journal_record_from_row(
                row,
                updated_at=payload["updated_at"],
                horizon_bars=args.paper_outcome_horizon_bars,
                execution_config=execution_config,
            )
        )
        active_by_pair[pair] = active_by_pair.get(pair, 0) + 1

    records.extend(new_records)
    if args.max_journal_records > 0 and len(records) > args.max_journal_records:
        records = records[-int(args.max_journal_records) :]
    write_journal(path, records)
    completed = sum(1 for record in records if record.get("status") == "completed")
    skipped = sum(1 for record in records if record.get("status") == "skipped")
    active = sum(1 for record in records if record.get("status") in {"pending_entry", "open"})
    analog_supported_open = sum(
        1
        for record in records
        if record.get("status") in {"pending_entry", "open"} and record.get("analog_supported")
    )
    return {
        "enabled": True,
        "path": str(path),
        "new_records": len(new_records),
        "updated_records": updated,
        "migrated_legacy_records": migrated,
        "total_records": len(records),
        "open_records": active,
        "completed_records": completed,
        "skipped_records": skipped,
        "analog_supported_open_records": analog_supported_open,
        "record_mode": args.journal_record_mode,
        "journal_allowed_pairs": sorted(f"{symbol}:{side}" for symbol, side in allowed_pairs),
        "journal_blocked_pairs": sorted(f"{timeframe}:{symbol}:{side}" for timeframe, symbol, side in blocked_pairs),
        "journal_blocked_candidate_rows": blocked_candidates,
        "journal_max_active_per_pair": max_active_per_pair,
        "execution_model": REALISTIC_EXECUTION_MODEL_VERSION,
        "paper_execution": execution_config,
    }


def run_screen(args: argparse.Namespace) -> dict[str, Any]:
    fallback = parse_symbols(args.symbols) or DEFAULT_SYMBOLS
    symbols = parse_symbols(args.symbols) or symbols_from_universe(
        args.universe_json,
        top_n=args.top_n,
        fallback=fallback,
    )
    rows = []
    for symbol in symbols:
        frame = load_symbol_cache(Path(args.cache_dir), symbol, args.timeframe, lookback_bars=args.lookback_bars)
        rows.append(classify_signal(frame, args, symbol=symbol))
    rows.sort(key=row_sort_key, reverse=True)
    signal_rows = [row for row in rows if row.get("signal") in {"long", "short"} and row.get("paper_plan")]
    analog_supported_rows = [row for row in signal_rows if (row.get("analog_evidence") or {}).get("supported")]
    payload = {
        "kind": "contract_latest_market_signal_v2_analog_journal",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "timeframe": args.timeframe,
        "universe_json": args.universe_json,
        "symbols": symbols,
        "config": {
            "ret_6h_bars": bars_for_hours(args.timeframe, 6.0),
            "ret_24h_bars": bars_for_hours(args.timeframe, 24.0),
            "fast_ema": int(args.fast_ema),
            "slow_ema": int(args.slow_ema),
            "breakout_n": int(args.breakout_n),
            "atr_n": int(args.atr_n),
            "rsi_n": int(args.rsi_n),
            "min_votes": int(args.min_votes),
            "risk_per_trade": float(args.risk_per_trade),
            "leverage_cap": float(args.leverage_cap),
            "reward_r": float(args.reward_r),
            "analog_top_k": int(args.analog_top_k),
            "analog_horizon_bars": int(args.analog_horizon_bars),
            "min_analog_samples": int(args.min_analog_samples),
            "min_analog_hit_rate": float(args.min_analog_hit_rate),
            "min_analog_profitable_rate": float(args.min_analog_profitable_rate),
            "min_analog_expectancy_r": float(args.min_analog_expectancy_r),
            "paper_outcome_horizon_bars": int(args.paper_outcome_horizon_bars),
            "paper_execution": execution_config_from_args(args),
            "journal_allowed_pairs": sorted(
                f"{symbol}:{side}" for symbol, side in parse_symbol_side_pairs(args.journal_allowed_pairs)
            ),
            "journal_blocked_pairs_json": str(getattr(args, "journal_blocked_pairs_json", "")),
            "journal_max_active_per_pair": int(args.journal_max_active_per_pair),
        },
        "summary": {
            "rows": len(rows),
            "signal_count": len(signal_rows),
            "paper_plan_found": bool(signal_rows),
            "analog_supported_plan_count": len(analog_supported_rows),
            "analog_supported_plan_found": bool(analog_supported_rows),
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "top": rows[:10],
        "rows": rows,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    payload["journal"] = update_journal(payload, args)
    return payload


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_marker(payload: dict[str, Any], marker_path: Path, no_marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    no_marker_path.parent.mkdir(parents=True, exist_ok=True)
    if payload["summary"]["paper_plan_found"]:
        best = next((row for row in payload["top"] if row.get("paper_plan")), payload["top"][0])
        plan = best["paper_plan"]
        analog = best.get("analog_evidence") or {}
        marker_path.write_text(
            "FOUND_CONTRACT_MARKET_PAPER_PLAN "
            f"{payload['updated_at']} "
            f"symbol={best['symbol']} side={best['signal']} "
            f"entry={plan['entry_price']:.8f} stop={plan['stop_loss']:.8f} take_profit={plan['take_profit']:.8f} "
            f"analog_supported={bool(analog.get('supported'))} "
            f"analog_hit_rate={safe_float(analog.get('hit_rate')):.4f} "
            f"analog_expectancy_r={safe_float(analog.get('expectancy_r')):.4f} "
            f"risk_per_trade={plan['risk_per_trade']:.6f} leverage_cap={plan['leverage_cap']:.3f} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if no_marker_path.exists():
            no_marker_path.unlink()
    else:
        no_marker_path.write_text(
            "NO_CONTRACT_MARKET_PAPER_PLAN "
            f"{payload['updated_at']} rows={payload['summary']['rows']} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if marker_path.exists():
            marker_path.unlink()


def write_analog_marker(payload: dict[str, Any], marker_path: Path, no_marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    no_marker_path.parent.mkdir(parents=True, exist_ok=True)
    supported = [
        row
        for row in payload["rows"]
        if row.get("paper_plan") and (row.get("analog_evidence") or {}).get("supported")
    ]
    if supported:
        best = supported[0]
        plan = best["paper_plan"]
        analog = best["analog_evidence"]
        marker_path.write_text(
            "FOUND_CONTRACT_MARKET_ANALOG_PAPER_PLAN "
            f"{payload['updated_at']} "
            f"symbol={best['symbol']} side={best['signal']} "
            f"entry={plan['entry_price']:.8f} stop={plan['stop_loss']:.8f} take_profit={plan['take_profit']:.8f} "
            f"analog_used={analog.get('used_count')} hit_rate={safe_float(analog.get('hit_rate')):.4f} "
            f"expectancy_r={safe_float(analog.get('expectancy_r')):.4f} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if no_marker_path.exists():
            no_marker_path.unlink()
    else:
        no_marker_path.write_text(
            "NO_CONTRACT_MARKET_ANALOG_PAPER_PLAN "
            f"{payload['updated_at']} signals={payload['summary']['signal_count']} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if marker_path.exists():
            marker_path.unlink()


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Contract Latest Market Signal",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- timeframe: `{payload['timeframe']}`",
        f"- signal_count: `{payload['summary']['signal_count']}`",
        f"- analog_supported_plan_count: `{payload['summary']['analog_supported_plan_count']}`",
        f"- paper_plan_found: `{payload['summary']['paper_plan_found']}`",
        f"- journal_new_records: `{(payload.get('journal') or {}).get('new_records')}`",
        "",
        "| rank | symbol | signal | close | analog | hit | exp_r | entry | stop | take_profit | rsi | ret_24h |",
        "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(payload["top"], start=1):
        plan = row.get("paper_plan") or {}
        metrics = row.get("metrics") or {}
        analog = row.get("analog_evidence") or {}
        lines.append(
            f"| {idx} | {row.get('symbol')} | {row.get('signal')} | {row.get('close', 0.0):.8f} | "
            f"{analog.get('reason')} | {safe_float(analog.get('hit_rate')):.2f} | "
            f"{safe_float(analog.get('expectancy_r')):.2f} | "
            f"{plan.get('entry_price', 0.0):.8f} | {plan.get('stop_loss', 0.0):.8f} | "
            f"{plan.get('take_profit', 0.0):.8f} | {metrics.get('rsi', 0.0):.2f} | {metrics.get('ret_24h', 0.0):.4f} |"
        )
    lines.extend(["", "Paper plan only. No order, paper trading, or live trading is authorized."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    lines = [
        f"updated_at={payload['updated_at']}",
        f"timeframe={payload['timeframe']}",
        f"signal_count={payload['summary']['signal_count']}",
        f"analog_supported_plan_count={payload['summary']['analog_supported_plan_count']}",
        f"paper_plan_found={payload['summary']['paper_plan_found']}",
        f"journal_new_records={(payload.get('journal') or {}).get('new_records')}",
        f"journal_updated_records={(payload.get('journal') or {}).get('updated_records')}",
        f"journal_migrated_legacy_records={(payload.get('journal') or {}).get('migrated_legacy_records')}",
        "safety=paper_authorized:False live:False",
    ]
    if payload["top"]:
        best = payload["top"][0]
        plan = best.get("paper_plan") or {}
        analog = best.get("analog_evidence") or {}
        lines.append(
            "best "
            f"symbol={best.get('symbol')} signal={best.get('signal')} reason={best.get('reason')} "
            f"analog={analog.get('reason')} hit_rate={analog.get('hit_rate')} "
            f"expectancy_r={analog.get('expectancy_r')} "
            f"entry={plan.get('entry_price')} stop={plan.get('stop_loss')} take_profit={plan.get('take_profit')}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Latest public-market contract signal screen with paper-only analog evidence and TP/SL journal."
    )
    parser.add_argument("--cache-dir", default="data/binance_usdm_ohlcv_cache")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--universe-json", default="artifacts/v9/universe/binance_usdm_top20_volume_snapshot.json")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--lookback-bars", type=int, default=20000)
    parser.add_argument("--fast-ema", type=int, default=24)
    parser.add_argument("--slow-ema", type=int, default=96)
    parser.add_argument("--slope-n", type=int, default=12)
    parser.add_argument("--breakout-n", type=int, default=24)
    parser.add_argument("--breakout-buffer", type=float, default=0.002)
    parser.add_argument("--atr-n", type=int, default=14)
    parser.add_argument("--rsi-n", type=int, default=14)
    parser.add_argument("--min-votes", type=int, default=5)
    parser.add_argument("--min-slope", type=float, default=0.001)
    parser.add_argument("--min-ret-24h", type=float, default=0.003)
    parser.add_argument("--max-long-rsi", type=float, default=75.0)
    parser.add_argument("--min-short-rsi", type=float, default=25.0)
    parser.add_argument("--stop-atr-mult", type=float, default=2.0)
    parser.add_argument("--min-stop-pct", type=float, default=0.01)
    parser.add_argument("--reward-r", type=float, default=2.0)
    parser.add_argument("--risk-per-trade", type=float, default=0.005)
    parser.add_argument("--leverage-cap", type=float, default=2.0)
    parser.add_argument("--analog-top-k", type=int, default=40)
    parser.add_argument("--analog-horizon-bars", type=int, default=24)
    parser.add_argument("--min-analog-samples", type=int, default=12)
    parser.add_argument("--min-analog-hit-rate", type=float, default=0.42)
    parser.add_argument("--min-analog-profitable-rate", type=float, default=0.55)
    parser.add_argument("--min-analog-expectancy-r", type=float, default=0.15)
    parser.add_argument("--paper-outcome-horizon-bars", type=int, default=24)
    parser.add_argument("--paper-fee-bps", type=float, default=5.0)
    parser.add_argument("--paper-slippage-bps", type=float, default=2.0)
    parser.add_argument("--paper-entry-latency-bars", type=int, default=1)
    parser.add_argument("--paper-max-entry-drift-bps", type=float, default=80.0)
    parser.add_argument("--paper-funding-bps-per-8h", type=float, default=1.0)
    parser.add_argument("--paper-partial-fill-frac", type=float, default=1.0)
    parser.add_argument("--paper-min-fill-frac", type=float, default=1.0)
    parser.add_argument(
        "--paper-migrate-legacy-records",
        choices=("off", "active", "all"),
        default="all",
    )
    parser.add_argument("--journal-jsonl", default="state/contract_latest_market_signal_journal.jsonl")
    parser.add_argument(
        "--journal-allowed-pairs",
        default="",
        help="Optional comma list of SYMBOL:long or SYMBOL:short pairs to record in the paper journal.",
    )
    parser.add_argument(
        "--journal-blocked-pairs",
        default="",
        help="Optional comma list of SYMBOL:SIDE or TIMEFRAME:SYMBOL:SIDE pairs to skip in the paper journal.",
    )
    parser.add_argument(
        "--journal-blocked-pairs-json",
        default="",
        help="Optional JSON file with blocked_pairs rows containing timeframe, symbol, and side.",
    )
    parser.add_argument(
        "--journal-max-active-per-pair",
        type=int,
        default=0,
        help="If positive, do not add a new paper record when SYMBOL:SIDE already has this many active records.",
    )
    parser.add_argument(
        "--journal-record-mode",
        choices=("all_signals", "analog_supported", "off"),
        default="all_signals",
    )
    parser.add_argument("--max-journal-records", type=int, default=20000)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_latest_market_signal_v1.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_latest_market_signal_v1.md")
    parser.add_argument("--marker", default="state/FOUND_CONTRACT_MARKET_PAPER_PLAN.txt")
    parser.add_argument("--no-marker", default="state/NO_CONTRACT_MARKET_PAPER_PLAN.txt")
    parser.add_argument("--analog-marker", default="state/FOUND_CONTRACT_MARKET_ANALOG_PAPER_PLAN.txt")
    parser.add_argument("--analog-no-marker", default="state/NO_CONTRACT_MARKET_ANALOG_PAPER_PLAN.txt")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = run_screen(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    write_marker(payload, Path(args.marker), Path(args.no_marker))
    write_analog_marker(payload, Path(args.analog_marker), Path(args.analog_no_marker))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
