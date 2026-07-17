#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols)


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


def classify_signal(frame: pd.DataFrame, args: argparse.Namespace, *, symbol: str) -> dict[str, Any]:
    min_bars = max(args.slow_ema, args.atr_n, args.rsi_n, args.breakout_n, args.slope_n, 25) + 2
    if len(frame) < min_bars:
        return {
            "symbol": symbol,
            "status": "insufficient_data",
            "signal": "none",
            "reason": f"need_at_least_{min_bars}_bars",
            "paper_plan": None,
        }
    df = frame.copy()
    df["ema_fast"] = df["close"].ewm(span=args.fast_ema, adjust=False, min_periods=args.fast_ema).mean()
    df["ema_slow"] = df["close"].ewm(span=args.slow_ema, adjust=False, min_periods=args.slow_ema).mean()
    df["atr"] = atr(df, args.atr_n)
    df["rsi"] = rsi(df["close"], args.rsi_n)
    df["high_breakout"] = df["high"].rolling(args.breakout_n, min_periods=args.breakout_n).max().shift(1)
    df["low_breakout"] = df["low"].rolling(args.breakout_n, min_periods=args.breakout_n).min().shift(1)
    latest = df.iloc[-1]
    previous = df.iloc[-2]
    close = safe_float(latest["close"])
    latest_atr = safe_float(latest["atr"])
    if close <= 0.0 or latest_atr <= 0.0:
        return {"symbol": symbol, "status": "insufficient_data", "signal": "none", "reason": "missing_close_or_atr", "paper_plan": None}
    ema_fast = safe_float(latest["ema_fast"])
    ema_slow = safe_float(latest["ema_slow"])
    rsi_value = safe_float(latest["rsi"], 50.0)
    ema_gap = (ema_fast / ema_slow - 1.0) if ema_slow > 0 else 0.0
    slope = (safe_float(latest["ema_slow"]) / safe_float(df["ema_slow"].iloc[-args.slope_n]) - 1.0) if safe_float(df["ema_slow"].iloc[-args.slope_n]) > 0 else 0.0
    ret_24h = close / safe_float(df["close"].iloc[-25]) - 1.0
    atr_pct = latest_atr / close
    high_breakout = safe_float(latest["high_breakout"])
    low_breakout = safe_float(latest["low_breakout"])
    long_votes = {
        "close_above_slow_ema": close > ema_slow,
        "fast_above_slow_ema": ema_fast > ema_slow,
        "slow_ema_slope_positive": slope > args.min_slope,
        "ret_24h_positive": ret_24h > args.min_ret_24h,
        "near_or_above_breakout": high_breakout > 0 and close >= high_breakout * (1.0 - args.breakout_buffer),
        "rsi_not_overheated": rsi_value <= args.max_long_rsi,
    }
    short_votes = {
        "close_below_slow_ema": close < ema_slow,
        "fast_below_slow_ema": ema_fast < ema_slow,
        "slow_ema_slope_negative": slope < -args.min_slope,
        "ret_24h_negative": ret_24h < -args.min_ret_24h,
        "near_or_below_breakdown": low_breakout > 0 and close <= low_breakout * (1.0 + args.breakout_buffer),
        "rsi_not_oversold": rsi_value >= args.min_short_rsi,
    }
    long_score = sum(1 for value in long_votes.values() if value)
    short_score = sum(1 for value in short_votes.values() if value)
    signal = "none"
    votes = {}
    if long_score >= args.min_votes and long_score > short_score:
        signal = "long"
        votes = long_votes
    elif short_score >= args.min_votes and short_score > long_score:
        signal = "short"
        votes = short_votes
    if signal == "none":
        return {
            "symbol": symbol,
            "status": "ok",
            "signal": "none",
            "reason": f"no_consensus long_votes={long_score} short_votes={short_score}",
            "latest_dt": latest["dt"].isoformat(),
            "close": close,
            "metrics": {
                "ema_gap": ema_gap,
                "slow_ema_slope": slope,
                "ret_24h": ret_24h,
                "atr_pct": atr_pct,
                "rsi": rsi_value,
                "long_votes": long_score,
                "short_votes": short_score,
            },
            "paper_plan": None,
        }
    risk_per_unit = max(latest_atr * float(args.stop_atr_mult), close * float(args.min_stop_pct))
    if signal == "long":
        stop = close - risk_per_unit
        take_profit = close + risk_per_unit * float(args.reward_r)
        invalid = stop <= 0
    else:
        stop = close + risk_per_unit
        take_profit = close - risk_per_unit * float(args.reward_r)
        invalid = take_profit <= 0
    if invalid:
        return {"symbol": symbol, "status": "invalid_plan", "signal": "none", "reason": "invalid_stop_or_take_profit", "paper_plan": None}
    plan = {
        "side": signal,
        "entry_reference": "latest_closed_1h_close_next_bar_open_simulated",
        "entry_price": close,
        "stop_loss": stop,
        "take_profit": take_profit,
        "risk_per_unit": risk_per_unit,
        "reward_r": float(args.reward_r),
        "risk_per_trade": float(args.risk_per_trade),
        "leverage_cap": float(args.leverage_cap),
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
        "metrics": {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "ema_gap": ema_gap,
            "slow_ema_slope": slope,
            "ret_24h": ret_24h,
            "atr": latest_atr,
            "atr_pct": atr_pct,
            "rsi": rsi_value,
            "long_votes": long_score,
            "short_votes": short_score,
            "votes": votes,
        },
        "paper_plan": plan,
    }


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    plan = row.get("paper_plan") or {}
    metrics = row.get("metrics") or {}
    signal = row.get("signal")
    return (
        signal in {"long", "short"},
        max(int(metrics.get("long_votes") or 0), int(metrics.get("short_votes") or 0)),
        abs(float(metrics.get("ema_gap") or 0.0)),
        abs(float(metrics.get("ret_24h") or 0.0)),
        -float(plan.get("risk_per_unit") or 0.0),
    )


def run_screen(args: argparse.Namespace) -> dict[str, Any]:
    fallback = parse_symbols(args.symbols) or DEFAULT_SYMBOLS
    symbols = parse_symbols(args.symbols) or symbols_from_universe(args.universe_json, top_n=args.top_n, fallback=fallback)
    rows = []
    for symbol in symbols:
        frame = load_symbol_cache(Path(args.cache_dir), symbol, args.timeframe, lookback_bars=args.lookback_bars)
        rows.append(classify_signal(frame, args, symbol=symbol))
    rows.sort(key=row_sort_key, reverse=True)
    signal_rows = [row for row in rows if row.get("signal") in {"long", "short"} and row.get("paper_plan")]
    return {
        "kind": "contract_latest_market_signal_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "timeframe": args.timeframe,
        "universe_json": args.universe_json,
        "symbols": symbols,
        "config": {
            "fast_ema": int(args.fast_ema),
            "slow_ema": int(args.slow_ema),
            "breakout_n": int(args.breakout_n),
            "atr_n": int(args.atr_n),
            "rsi_n": int(args.rsi_n),
            "min_votes": int(args.min_votes),
            "risk_per_trade": float(args.risk_per_trade),
            "leverage_cap": float(args.leverage_cap),
            "reward_r": float(args.reward_r),
        },
        "summary": {
            "rows": len(rows),
            "signal_count": len(signal_rows),
            "paper_plan_found": bool(signal_rows),
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "top": rows[:10],
        "rows": rows,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_marker(payload: dict[str, Any], marker_path: Path, no_marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    no_marker_path.parent.mkdir(parents=True, exist_ok=True)
    if payload["summary"]["paper_plan_found"]:
        best = payload["top"][0]
        plan = best["paper_plan"]
        marker_path.write_text(
            "FOUND_CONTRACT_MARKET_PAPER_PLAN "
            f"{payload['updated_at']} "
            f"symbol={best['symbol']} side={best['signal']} "
            f"entry={plan['entry_price']:.8f} stop={plan['stop_loss']:.8f} take_profit={plan['take_profit']:.8f} "
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


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Contract Latest Market Signal",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- timeframe: `{payload['timeframe']}`",
        f"- signal_count: `{payload['summary']['signal_count']}`",
        f"- paper_plan_found: `{payload['summary']['paper_plan_found']}`",
        "",
        "| rank | symbol | signal | close | reason | entry | stop | take_profit | rsi | ret_24h |",
        "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(payload["top"], start=1):
        plan = row.get("paper_plan") or {}
        metrics = row.get("metrics") or {}
        lines.append(
            f"| {idx} | {row.get('symbol')} | {row.get('signal')} | {row.get('close', 0.0):.8f} | "
            f"{row.get('reason')} | {plan.get('entry_price', 0.0):.8f} | {plan.get('stop_loss', 0.0):.8f} | "
            f"{plan.get('take_profit', 0.0):.8f} | {metrics.get('rsi', 0.0):.2f} | {metrics.get('ret_24h', 0.0):.4f} |"
        )
    lines.extend(["", "Paper plan only. No order, paper trading, or live trading is authorized."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    lines = [
        f"updated_at={payload['updated_at']}",
        f"timeframe={payload['timeframe']}",
        f"signal_count={payload['summary']['signal_count']}",
        f"paper_plan_found={payload['summary']['paper_plan_found']}",
        "safety=paper_authorized:False live:False",
    ]
    if payload["top"]:
        best = payload["top"][0]
        plan = best.get("paper_plan") or {}
        lines.append(
            "best "
            f"symbol={best.get('symbol')} signal={best.get('signal')} reason={best.get('reason')} "
            f"entry={plan.get('entry_price')} stop={plan.get('stop_loss')} take_profit={plan.get('take_profit')}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Latest public-market contract signal screen with paper-only TP/SL plan.")
    parser.add_argument("--cache-dir", default="data/binance_usdm_ohlcv_cache")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--universe-json", default="artifacts/v9/universe/binance_usdm_top20_volume_snapshot.json")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--lookback-bars", type=int, default=240)
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
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/contract_latest_market_signal_v1.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/contract_latest_market_signal_v1.md")
    parser.add_argument("--marker", default="state/FOUND_CONTRACT_MARKET_PAPER_PLAN.txt")
    parser.add_argument("--no-marker", default="state/NO_CONTRACT_MARKET_PAPER_PLAN.txt")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    payload = run_screen(args)
    write_json(payload, Path(args.out_json))
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text(format_markdown(payload))
    write_marker(payload, Path(args.marker), Path(args.no_marker))
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    else:
        print(format_text(payload), flush=True)


if __name__ == "__main__":
    main()
