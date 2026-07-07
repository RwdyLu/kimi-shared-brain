from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .metrics import cvar, fold_pnls, max_drawdown, profit_factor
from .schema import ContractCandidate


def month_range(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    cur = pd.Timestamp(start.year, start.month, 1, tz="UTC")
    final = pd.Timestamp(end.year, end.month, 1, tz="UTC")
    months = []
    while cur <= final:
        months.append(cur.strftime("%Y-%m"))
        cur += pd.DateOffset(months=1)
    return months


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


def utc_ts(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_convert("UTC") if ts.tzinfo else pd.Timestamp(value, tz="UTC")


def load_symbol_1h(
    cache_dir: Path,
    symbol: str,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    embargo_start: pd.Timestamp,
) -> pd.DataFrame:
    if train_end >= embargo_start:
        raise SystemExit(f"train_end {train_end} must be before embargo_start {embargo_start}")
    frames: list[pd.DataFrame] = []
    for month in month_range(train_start, train_end):
        path = cache_dir / f"{symbol}_1h_{month}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        keep = [c for c in ["open_time", "open", "high", "low", "close", "volume"] if c in df.columns]
        if "open_time" not in keep:
            continue
        df = df[keep].copy()
        df["dt"] = open_time_to_dt(df["open_time"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        frames.append(df)
    if not frames:
        raise SystemExit(f"no cached 1h data for {symbol}")
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["dt", "open", "high", "low", "close"])
    out = out.sort_values("dt").drop_duplicates("dt")
    out = out[(out["dt"] >= train_start) & (out["dt"] <= train_end)].copy()
    if out.empty:
        raise SystemExit(f"empty train data for {symbol}")
    if (out["dt"] >= embargo_start).any():
        bad = out.loc[out["dt"] >= embargo_start, "dt"].min()
        raise SystemExit(f"embargo guard failed: bar {bad} >= {embargo_start}")
    return out.reset_index(drop=True)


def load_regime_labels(path: Path, embargo_start: pd.Timestamp) -> pd.DataFrame:
    labels = pd.read_parquet(path).copy()
    labels["dt"] = pd.to_datetime(labels["dt"], utc=True, errors="coerce")
    labels = labels.dropna(subset=["dt", "regime_id"]).sort_values("dt")
    if (labels["dt"] >= embargo_start).any():
        bad = labels.loc[labels["dt"] >= embargo_start, "dt"].min()
        raise SystemExit(f"regime label embargo guard failed: {bad} >= {embargo_start}")
    return labels


def attach_regimes(bars: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Attach previous daily regime labels to hourly bars.

    Daily labels are computed from a daily close, so the label for day D only
    becomes tradable at D+1 00:00 UTC. This prevents intraday label leakage.
    """

    bars = bars.copy().sort_values("dt")
    bars["dt"] = pd.to_datetime(bars["dt"], utc=True, errors="coerce").astype("datetime64[ns, UTC]")
    label_cols = ["dt", "regime_id", "insufficient_history"]
    for col in ["trend_return", "realized_vol_90d", "vol_percentile_2y", "drawdown_1y"]:
        if col in labels.columns:
            label_cols.append(col)
    labs = labels[label_cols].copy().sort_values("dt")
    labs["dt"] = pd.to_datetime(labs["dt"], utc=True, errors="coerce").astype("datetime64[ns, UTC]")
    labs["effective_dt"] = labs["dt"] + pd.Timedelta(days=1)
    merge_cols = [c for c in labs.columns if c != "dt"]
    merged = pd.merge_asof(
        bars,
        labs[merge_cols],
        left_on="dt",
        right_on="effective_dt",
        direction="backward",
    )
    merged["regime_id"] = merged["regime_id"].fillna("unknown")
    merged["insufficient_history"] = merged["insufficient_history"].fillna(True).astype(bool)
    return merged.drop(columns=["effective_dt"]).reset_index(drop=True)


def rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0).rolling(length, min_periods=length).mean()
    losses = (-delta.clip(upper=0.0)).rolling(length, min_periods=length).mean()
    rs = gains / losses
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.mask((losses == 0) & (gains > 0), 100.0)
    out = out.mask((losses == 0) & (gains == 0), 50.0)
    return out


def prepare_features(bars: pd.DataFrame, candidate: ContractCandidate) -> pd.DataFrame:
    df = bars.copy().sort_values("dt").reset_index(drop=True)
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.rolling(candidate.atr_n, min_periods=candidate.atr_n).mean()
    df["atr_pct"] = df["atr"] / df["close"]
    df["atr_pct_ref"] = df["atr_pct"].rolling(candidate.vol_lookback_n, min_periods=candidate.vol_lookback_n).median()
    log_returns = np.log(df["close"] / df["close"].shift(1))
    df["sigma_ann"] = log_returns.rolling(candidate.vol_lookback_n, min_periods=candidate.vol_lookback_n).std() * math.sqrt(365 * 24)
    df["risk_scale"] = 1.0
    if candidate.vol_scaling == "inverse_atr":
        raw_scale = df["atr_pct_ref"] / df["atr_pct"]
        valid = df["atr_pct_ref"].notna() & df["atr_pct"].notna() & (df["atr_pct_ref"] > 0) & (df["atr_pct"] > 0)
        df["risk_scale"] = raw_scale.where(valid).clip(lower=candidate.scale_min, upper=candidate.scale_max)
    elif candidate.vol_scaling == "vol_target":
        raw_scale = float(candidate.vol_target_ann) / df["sigma_ann"]
        valid = df["sigma_ann"].notna() & (df["sigma_ann"] > 0)
        df["risk_scale"] = raw_scale.where(valid).clip(lower=candidate.scale_min, upper=candidate.scale_max)
    df["prev_breakout_high"] = df["high"].rolling(candidate.breakout_n, min_periods=candidate.breakout_n).max().shift(1)
    regime_drawdown_ok = pd.Series(True, index=df.index)
    if candidate.max_regime_drawdown_1y is not None:
        raw_drawdown = df["drawdown_1y"] if "drawdown_1y" in df.columns else pd.Series(float("nan"), index=df.index)
        drawdown = pd.to_numeric(raw_drawdown, errors="coerce")
        regime_drawdown_ok = drawdown.notna() & (drawdown <= float(candidate.max_regime_drawdown_1y))
    allowed = set(candidate.allowed_regimes)
    df["entry_signal"] = (
        df["regime_id"].isin(allowed)
        & ~df.get("insufficient_history", pd.Series(False, index=df.index)).astype(bool)
        & regime_drawdown_ok
        & df["atr"].notna()
        & df["prev_breakout_high"].notna()
        & (df["close"] > df["prev_breakout_high"])
    )
    df["exit_signal"] = False
    if candidate.family == "pullback_long_v1":
        ema = df["close"].ewm(span=candidate.trend_ema_len, adjust=False, min_periods=candidate.trend_ema_len).mean()
        pullback_rsi = rsi(df["close"], candidate.rsi_len)
        df["trend_ema"] = ema
        df["rsi"] = pullback_rsi
        df["entry_signal"] = (
            df["regime_id"].isin(allowed)
            & ~df.get("insufficient_history", pd.Series(False, index=df.index)).astype(bool)
            & regime_drawdown_ok
            & df["atr"].notna()
            & ema.notna()
            & pullback_rsi.notna()
            & (df["close"] > ema)
            & (pullback_rsi < float(candidate.rsi_entry_max))
        )
        df["exit_signal"] = (
            pullback_rsi.notna()
            & (pullback_rsi.shift(1) <= float(candidate.rsi_exit_min))
            & (pullback_rsi > float(candidate.rsi_exit_min))
        )
    elif candidate.family == "bear_rally_fade_short_v1":
        sma = df["close"].rolling(candidate.regime_len, min_periods=candidate.regime_len).mean()
        sma_slope = sma - sma.shift(candidate.slope_len)
        fade_rsi = rsi(df["close"], candidate.rsi_len)
        bearish_regime = (df["close"] < sma) & (sma_slope < 0)
        df["regime_sma"] = sma
        df["regime_sma_slope"] = sma_slope
        df["rsi"] = fade_rsi
        df["entry_signal"] = (
            df["regime_id"].isin(allowed)
            & ~df.get("insufficient_history", pd.Series(False, index=df.index)).astype(bool)
            & regime_drawdown_ok
            & sma.notna()
            & sma_slope.notna()
            & fade_rsi.notna()
            & bearish_regime
            & (fade_rsi >= float(candidate.rsi_hi))
        )
        df["exit_signal"] = sma.notna() & (df["close"] > sma)
    return df


def _close_position(
    position: dict[str, Any],
    exit_time: pd.Timestamp,
    exit_index: int,
    exit_price: float,
    reason: str,
    fee_rate: float,
    funding_rate_8h: float,
    equity: float,
) -> tuple[dict[str, Any], float]:
    qty = float(position["qty"])
    entry_price = float(position["entry_price"])
    exit_fee = qty * exit_price * fee_rate
    hold_hours = max(0.0, (exit_time - position["entry_time"]).total_seconds() / 3600.0)
    funding_cost = float(position["entry_notional"]) * funding_rate_8h * hold_hours / 8.0
    gross_pnl = qty * (exit_price - entry_price)
    if position.get("side") == "short":
        gross_pnl = qty * (entry_price - exit_price)
    net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee - funding_cost
    short_extra_cost = 0.0
    if position.get("side") == "short":
        short_extra_cost = float(position.get("entry_notional", 0.0)) * float(position.get("short_extra_cost_bps", 0.0)) / 10000.0
        net_pnl -= short_extra_cost
    equity_after = equity + gross_pnl - exit_fee - funding_cost - short_extra_cost
    risk_amount = max(float(position["risk_amount"]), 1e-12)
    trade = {
        "symbol": position["symbol"],
        "candidate_id": position["candidate_id"],
        "side": str(position.get("side", "long")),
        "signal_time": position["signal_time"].isoformat(),
        "entry_time": position["entry_time"].isoformat(),
        "exit_time": exit_time.isoformat(),
        "signal_index": int(position["signal_index"]),
        "entry_index": int(position["entry_index"]),
        "exit_index": int(exit_index),
        "entry_price": entry_price,
        "exit_price": float(exit_price),
        "qty": qty,
        "entry_regime": position["entry_regime"],
        "exit_reason": reason,
        "bars_held": int(exit_index - position["entry_index"]),
        "gross_pnl": float(gross_pnl),
        "entry_fee": float(position["entry_fee"]),
        "exit_fee": float(exit_fee),
        "funding_cost": float(funding_cost),
        "short_extra_cost": float(short_extra_cost),
        "net_pnl": float(net_pnl),
        "r_multiple": float(net_pnl / risk_amount),
        "risk_amount": float(risk_amount),
        "risk_scale": float(position.get("risk_scale", 1.0)),
        "equity_before_entry": float(position["equity_before_entry"]),
        "equity_after_exit": float(equity_after),
        "actual_leverage": float(position["actual_leverage"]),
        "stop_price": float(position["stop_price"]),
        "target_price": float(position["target_price"]),
        "liquidation_price": float(position["liquidation_price"]),
    }
    return trade, equity_after


def _intrabar_exit(row: pd.Series, position: dict[str, Any]) -> tuple[str, float] | None:
    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    liquidation = float(position["liquidation_price"])
    side = str(position.get("side", "long"))
    if side == "short":
        if liquidation > 0 and high >= liquidation:
            return "liquidation", max(open_price, liquidation)

        stop = float(position["stop_price"])
        target = float(position["target_price"])
        stop_hit = high >= stop
        target_hit = low <= target
        if stop_hit:
            return "stop_loss", max(open_price, stop)
        if target_hit:
            return "take_profit", min(open_price, target) if open_price <= target else target
        return None

    if liquidation > 0 and low <= liquidation:
        return "liquidation", min(open_price, liquidation)

    stop = float(position["stop_price"])
    target = float(position["target_price"])
    stop_hit = low <= stop
    target_hit = high >= target
    if stop_hit:
        return "stop_loss", min(open_price, stop)
    if target_hit:
        return "take_profit", max(open_price, target) if open_price >= target else target
    return None


def _update_protective_stop(position: dict[str, Any], candidate: ContractCandidate) -> None:
    if position.get("side") == "short":
        return
    initial_risk = max(float(position["initial_risk_per_unit"]), 1e-12)
    entry_price = float(position["entry_price"])
    highest_high = float(position.get("highest_high", entry_price))
    unrealized_r = (highest_high - entry_price) / initial_risk
    candidates = [float(position["stop_price"])]
    if candidate.be_trigger_r is not None and unrealized_r >= float(candidate.be_trigger_r):
        candidates.append(entry_price + float(candidate.be_lock_r) * initial_risk)
    if candidate.trail_atr_mult is not None and unrealized_r >= float(candidate.trail_trigger_r):
        prev_atr = float(position.get("prev_atr", 0.0))
        if math.isfinite(prev_atr) and prev_atr > 0:
            candidates.append(highest_high - float(candidate.trail_atr_mult) * prev_atr)
    position["stop_price"] = max(candidates)


def _enter_position(
    row: pd.Series,
    idx: int,
    candidate: ContractCandidate,
    cost_multiplier: float,
    equity: float,
    pending_entry: dict[str, Any],
) -> dict[str, Any] | None:
    fee_rate = candidate.fee_bps * cost_multiplier / 10000.0
    slip_rate = candidate.slippage_bps * cost_multiplier / 10000.0
    side = candidate.side
    atr = float(pending_entry.get("atr", 0.0) or 0.0)
    risk_scale = float(pending_entry.get("risk_scale", 1.0))
    if not math.isfinite(risk_scale) or risk_scale <= 0:
        return None
    if side == "short":
        entry_price = float(row["open"]) * (1.0 - slip_rate)
        if entry_price <= 0:
            return None
        stop_price = entry_price * (1.0 + float(candidate.stop_pct))
        target_price = entry_price * (1.0 - float(candidate.target_pct))
        risk_per_unit = stop_price - entry_price
    else:
        entry_price = float(row["open"]) * (1.0 + slip_rate)
        if not math.isfinite(atr) or atr <= 0 or entry_price <= 0:
            return None
        stop_price = entry_price - candidate.stop_atr_k * atr
        if stop_price <= 0 or stop_price >= entry_price:
            return None
        risk_per_unit = entry_price - stop_price
        target_price = entry_price + candidate.tp_r_multiple * risk_per_unit
    risk_budget = equity * candidate.risk_per_trade * risk_scale
    qty_by_risk = risk_budget / risk_per_unit
    qty_by_leverage = equity * candidate.leverage_cap / entry_price
    qty = max(0.0, min(qty_by_risk, qty_by_leverage))
    if qty <= 0:
        return None
    entry_notional = qty * entry_price
    entry_fee = entry_notional * fee_rate
    if entry_fee >= equity:
        return None
    actual_leverage = entry_notional / equity
    liquidation_price = 0.0
    if actual_leverage > 1.0:
        if side == "short":
            liquidation_price = entry_price * (1.0 + 0.95 / actual_leverage)
        else:
            liquidation_price = entry_price * (1.0 - 0.95 / actual_leverage)
    return {
        "symbol": candidate.symbol,
        "candidate_id": candidate.candidate_id(),
        "side": side,
        "entry_time": row["dt"],
        "signal_time": pending_entry["signal_time"],
        "signal_index": int(pending_entry["signal_index"]),
        "entry_index": idx,
        "entry_price": entry_price,
        "qty": qty,
        "entry_fee": entry_fee,
        "entry_notional": entry_notional,
        "risk_amount": qty * risk_per_unit,
        "risk_scale": risk_scale,
        "initial_risk_per_unit": risk_per_unit,
        "equity_before_entry": equity,
        "actual_leverage": actual_leverage,
        "stop_price": stop_price,
        "initial_stop_price": stop_price,
        "target_price": target_price,
        "liquidation_price": liquidation_price,
        "entry_regime": str(pending_entry.get("regime_id", "unknown")),
        "highest_high": entry_price,
        "prev_atr": atr,
        "short_extra_cost_bps": candidate.short_extra_cost_bps,
    }


def _summarize(
    candidate: ContractCandidate,
    cost_multiplier: float,
    bars: pd.DataFrame,
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    final_equity: float,
    include_trades: bool,
) -> dict[str, Any]:
    pnls = [float(t["net_pnl"]) for t in trades]
    rs = [float(t["r_multiple"]) for t in trades]
    wins = [p for p in pnls if p > 0]
    by_regime: dict[str, dict[str, Any]] = {}
    for trade in trades:
        regime = str(trade["entry_regime"])
        row = by_regime.setdefault(regime, {"trades": 0, "net_pnl": 0.0, "r_sum": 0.0})
        row["trades"] += 1
        row["net_pnl"] += float(trade["net_pnl"])
        row["r_sum"] += float(trade["r_multiple"])
    for row in by_regime.values():
        row["avg_r"] = row["r_sum"] / row["trades"] if row["trades"] else 0.0
        del row["r_sum"]

    held_bars = sum(max(1, int(t["bars_held"])) for t in trades)
    equities = [float(p["equity"]) for p in equity_curve]
    payload = {
        "candidate": candidate.to_dict(),
        "candidate_id": candidate.candidate_id(),
        "symbol": candidate.symbol,
        "cost_multiplier": float(cost_multiplier),
        "initial_equity": float(candidate.initial_equity),
        "final_equity": float(final_equity),
        "net_pnl": float(final_equity - candidate.initial_equity),
        "total_return": float(final_equity / candidate.initial_equity - 1.0),
        "trade_count": len(trades),
        "win_rate": float(len(wins) / len(trades)) if trades else 0.0,
        "avg_r": float(sum(rs) / len(rs)) if rs else 0.0,
        "cvar5_r": cvar(rs, 0.05),
        "profit_factor": profit_factor(pnls),
        "max_drawdown": max_drawdown(equities),
        "exposure_bar_ratio": float(held_bars / len(bars)) if len(bars) else 0.0,
        "residual_positions": 0,
        "by_entry_regime": by_regime,
        "folds": fold_pnls(trades, 3),
        "bar_count": int(len(bars)),
        "first_bar": bars["dt"].min().isoformat() if len(bars) else None,
        "last_bar": bars["dt"].max().isoformat() if len(bars) else None,
    }
    if include_trades:
        payload["trades"] = trades
        payload["equity_curve"] = equity_curve
    return payload


def simulate_candidate(
    bars: pd.DataFrame,
    candidate: ContractCandidate,
    cost_multiplier: float = 1.0,
    include_trades: bool = True,
) -> dict[str, Any]:
    df = prepare_features(bars, candidate)
    fee_rate = candidate.fee_bps * cost_multiplier / 10000.0
    funding_rate_8h = candidate.funding_bps_per_8h * cost_multiplier / 10000.0
    equity = float(candidate.initial_equity)
    position: dict[str, Any] | None = None
    pending_entry: dict[str, Any] | None = None
    pending_signal_exit = False
    cooldown_until = -1
    trades: list[dict[str, Any]] = []
    equity_curve = [{"dt": df["dt"].iloc[0].isoformat(), "equity": equity, "event": "start"}] if len(df) else []

    for idx, row in df.iterrows():
        just_exited = False
        if position is not None and idx - int(position["entry_index"]) >= candidate.max_hold_bars:
            _update_protective_stop(position, candidate)
            trade, equity = _close_position(position, row["dt"], idx, float(row["open"]), "max_hold", fee_rate, funding_rate_8h, equity)
            trades.append(trade)
            equity_curve.append({"dt": row["dt"].isoformat(), "equity": equity, "event": "exit_max_hold"})
            position = None
            cooldown_until = idx + candidate.cooldown_bars
            just_exited = True

        if pending_signal_exit and position is not None:
            trade, equity = _close_position(position, row["dt"], idx, float(row["open"]), "signal_exit", fee_rate, funding_rate_8h, equity)
            trades.append(trade)
            equity_curve.append({"dt": row["dt"].isoformat(), "equity": equity, "event": "exit_signal"})
            position = None
            cooldown_until = idx + candidate.cooldown_bars
            just_exited = True
        pending_signal_exit = False

        if pending_entry is not None and position is None and idx >= cooldown_until:
            position = _enter_position(row, idx, candidate, cost_multiplier, equity, pending_entry)
            pending_entry = None
            if position is not None:
                equity -= float(position["entry_fee"])
                equity_curve.append({"dt": row["dt"].isoformat(), "equity": equity, "event": "entry_fee"})

        if position is not None:
            _update_protective_stop(position, candidate)
            intrabar = _intrabar_exit(row, position)
            if intrabar is not None:
                reason, exit_price = intrabar
                trade, equity = _close_position(position, row["dt"], idx, exit_price, reason, fee_rate, funding_rate_8h, equity)
                trades.append(trade)
                equity_curve.append({"dt": row["dt"].isoformat(), "equity": equity, "event": f"exit_{reason}"})
                position = None
                cooldown_until = idx + candidate.cooldown_bars
                just_exited = True
            else:
                position["highest_high"] = max(float(position.get("highest_high", position["entry_price"])), float(row["high"]))
                if row.get("atr") is not None and math.isfinite(float(row["atr"])):
                    position["prev_atr"] = float(row["atr"])

        if position is not None and not just_exited and idx < len(df) - 1 and bool(row.get("exit_signal", False)):
            pending_signal_exit = True

        if (
            position is None
            and not just_exited
            and idx < len(df) - 1
            and idx >= cooldown_until
            and bool(row.get("entry_signal", False))
        ):
            pending_entry = {
                "signal_time": row["dt"],
                "signal_index": int(idx),
                "atr": float(row["atr"]),
                "risk_scale": float(row.get("risk_scale", float("nan"))),
                "regime_id": str(row.get("regime_id", "unknown")),
            }

    if position is not None and len(df):
        last = df.iloc[-1]
        trade, equity = _close_position(position, last["dt"], len(df) - 1, float(last["close"]), "train_end", fee_rate, funding_rate_8h, equity)
        trades.append(trade)
        equity_curve.append({"dt": last["dt"].isoformat(), "equity": equity, "event": "exit_train_end"})
        position = None

    return _summarize(candidate, cost_multiplier, df, trades, equity_curve, equity, include_trades)
