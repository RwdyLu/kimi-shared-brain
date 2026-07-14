#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
)
EVENTS_PER_YEAR = 3.0 * 365.25
MS_PER_DAY = 86_400_000


@dataclass(frozen=True)
class DeltaNeutralFundingConfig:
    lookback_events: int
    max_positions: int
    min_trailing_funding_rate: float
    turnover_cost_bps: float
    stress_turnover_cost_bps: float
    capital_multiplier: float = 2.0


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols)


def parse_int_grid(raw: str) -> tuple[int, ...]:
    values = [int(part.strip()) for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(values)


def parse_float_grid(raw: str) -> tuple[float, ...]:
    values = [float(part.strip()) for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(values)


def timestamp_ms_to_iso(value: int | float | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(int(value), unit="ms", tz="UTC").isoformat()


def normalize_funding_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "symbol": df["symbol"] if "symbol" in df.columns else pd.NA,
            "funding_time": df["funding_time"] if "funding_time" in df.columns else pd.NA,
            "funding_rate": df["funding_rate"] if "funding_rate" in df.columns else pd.NA,
        }
    )
    out["symbol"] = out["symbol"].astype("string").str.upper()
    out["funding_time"] = pd.to_numeric(out["funding_time"], errors="coerce").astype("Int64")
    out["funding_rate"] = pd.to_numeric(out["funding_rate"], errors="coerce")
    out = out.dropna(subset=["symbol", "funding_time", "funding_rate"])
    out["funding_time"] = out["funding_time"].astype("int64")
    return out.sort_values(["funding_time", "symbol"]).drop_duplicates(["funding_time", "symbol"], keep="last")


def load_funding_cache(cache_dir: Path, symbols: tuple[str, ...]) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        for path in sorted(cache_dir.glob(f"{symbol.upper()}_funding_*.parquet")):
            try:
                frames.append(pd.read_parquet(path, columns=["symbol", "funding_time", "funding_rate"]))
            except Exception:
                continue
    if not frames:
        return pd.DataFrame(columns=["symbol", "funding_time", "funding_rate"])
    return normalize_funding_frame(pd.concat(frames, ignore_index=True))


def filter_funding_window(frame: pd.DataFrame, *, start: str, end: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame
    if start:
        start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        out = out[out["funding_time"] >= start_ms]
    if end:
        end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
        out = out[out["funding_time"] <= end_ms]
    return out.copy()


def symbols_from_universe(path: str, *, top_n: int, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not path:
        return fallback[:top_n]
    p = Path(path)
    if not p.exists():
        return fallback[:top_n]
    payload = json.loads(p.read_text())
    symbols = tuple(str(symbol).upper() for symbol in payload.get("symbols", []) if symbol)
    return (symbols or fallback)[:top_n]


def max_drawdown_compounded(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = (1.0 + returns.fillna(0.0)).cumprod()
    drawdown = 1.0 - equity / equity.cummax()
    return float(drawdown.max())


def compounded_return(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def annualized_sharpe(returns: pd.Series) -> float:
    if len(returns) < 2:
        return 0.0
    std = float(returns.std(ddof=1))
    if std <= 0.0 or not math.isfinite(std):
        return 0.0
    return float(returns.mean()) / std * math.sqrt(EVENTS_PER_YEAR)


def summarize_detail(detail: pd.DataFrame, *, prefix: str = "") -> dict[str, Any]:
    if detail.empty:
        return {
            f"{prefix}events": 0,
            f"{prefix}active_events": 0,
            f"{prefix}capital_annualized_return": 0.0,
            f"{prefix}capital_sharpe": 0.0,
            f"{prefix}capital_total_return": 0.0,
            f"{prefix}capital_max_drawdown": 0.0,
            f"{prefix}active_event_fraction": 0.0,
        }
    returns = detail["net_capital_return"].astype(float)
    active = detail["position_count"].astype(int) > 0
    return {
        f"{prefix}events": int(len(detail)),
        f"{prefix}active_events": int(active.sum()),
        f"{prefix}active_event_fraction": float(active.mean()),
        f"{prefix}notional_annualized_return": float(detail["net_notional_return"].mean()) * EVENTS_PER_YEAR,
        f"{prefix}capital_annualized_return": float(returns.mean()) * EVENTS_PER_YEAR,
        f"{prefix}capital_sharpe": annualized_sharpe(returns),
        f"{prefix}capital_total_return": compounded_return(returns),
        f"{prefix}capital_max_drawdown": max_drawdown_compounded(returns),
        f"{prefix}positive_active_event_fraction": float((returns[active] > 0.0).mean()) if active.any() else 0.0,
        f"{prefix}funding_capture_sum": float(detail["funding_notional_return"].sum()),
        f"{prefix}cost_sum": float(detail["turnover_cost"].sum()),
    }


def trailing_mean_by_symbol(pivot: pd.DataFrame, lookback_events: int) -> pd.DataFrame:
    lookback = max(1, int(lookback_events))
    trailing = pd.DataFrame(index=pivot.index, columns=pivot.columns, dtype=float)
    for symbol in pivot.columns:
        series = pivot[symbol].dropna()
        if series.empty:
            continue
        trailing.loc[series.index, symbol] = series.rolling(lookback, min_periods=lookback).mean().shift(1)
    return trailing


def select_from_scores(
    scores: pd.Series,
    *,
    max_positions: int,
    min_trailing_funding_rate: float,
) -> list[str]:
    eligible = scores.dropna()
    eligible = eligible[eligible >= float(min_trailing_funding_rate)].sort_values(ascending=False)
    return [str(symbol) for symbol in eligible.index[: max(1, int(max_positions))]]


def build_event_detail(
    frame: pd.DataFrame,
    cfg: DeltaNeutralFundingConfig,
    *,
    turnover_cost_bps: float,
) -> pd.DataFrame:
    clean = normalize_funding_frame(frame)
    if clean.empty:
        return pd.DataFrame()
    pivot = clean.pivot_table(index="funding_time", columns="symbol", values="funding_rate", aggfunc="last").sort_index()
    trailing = trailing_mean_by_symbol(pivot, cfg.lookback_events)
    previous_weights = pd.Series(dtype=float)
    rows: list[dict[str, Any]] = []
    for funding_time in pivot.index:
        scores = trailing.loc[funding_time].dropna()
        realized = pivot.loc[funding_time].dropna()
        common_scores = scores.loc[scores.index.intersection(realized.index)]
        selected = select_from_scores(
            common_scores,
            max_positions=cfg.max_positions,
            min_trailing_funding_rate=cfg.min_trailing_funding_rate,
        )
        weights = pd.Series(dtype=float)
        if selected:
            weights = pd.Series(1.0 / len(selected), index=selected, dtype=float)
        all_symbols = previous_weights.index.union(weights.index)
        turnover = float(
            (
                weights.reindex(all_symbols, fill_value=0.0)
                - previous_weights.reindex(all_symbols, fill_value=0.0)
            )
            .abs()
            .sum()
        )
        funding_return = float((weights * realized.reindex(weights.index)).sum()) if selected else 0.0
        cost = turnover * float(turnover_cost_bps) / 10_000.0
        net_notional_return = funding_return - cost
        net_capital_return = net_notional_return / max(float(cfg.capital_multiplier), 1.0)
        rows.append(
            {
                "funding_time": int(funding_time),
                "short_perp_symbols": selected,
                "long_spot_symbols": selected,
                "position_count": int(len(selected)),
                "mean_trailing_funding_rate": float(common_scores.loc[selected].mean()) if selected else 0.0,
                "mean_realized_funding_rate": float(realized.loc[selected].mean()) if selected else 0.0,
                "funding_notional_return": funding_return,
                "turnover": turnover,
                "turnover_cost": cost,
                "net_notional_return": net_notional_return,
                "net_capital_return": net_capital_return,
            }
        )
        previous_weights = weights
    return pd.DataFrame(rows)


def split_detail(detail: pd.DataFrame, *, selection_frac: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if detail.empty:
        return detail.copy(), detail.copy()
    times = detail["funding_time"].sort_values().tolist()
    split_idx = max(1, min(len(times) - 1, int(len(times) * float(selection_frac))))
    split_time = int(times[split_idx])
    return detail[detail["funding_time"] < split_time].copy(), detail[detail["funding_time"] >= split_time].copy()


def recent_detail(detail: pd.DataFrame, *, days: int) -> pd.DataFrame:
    if detail.empty:
        return detail.copy()
    end = int(detail["funding_time"].max())
    start = end - int(days) * MS_PER_DAY
    return detail[detail["funding_time"] >= start].copy()


def current_signal(frame: pd.DataFrame, cfg: DeltaNeutralFundingConfig) -> dict[str, Any]:
    clean = normalize_funding_frame(frame)
    if clean.empty:
        return {"status": "insufficient_data", "positions": []}
    pivot = clean.pivot_table(index="funding_time", columns="symbol", values="funding_rate", aggfunc="last").sort_index()
    if pivot.empty:
        return {"status": "insufficient_data", "positions": []}
    latest_time = int(pivot.index.max())
    scores = {}
    for symbol in pivot.columns:
        series = pivot[symbol].dropna()
        if len(series) < int(cfg.lookback_events):
            continue
        scores[str(symbol)] = float(series.tail(int(cfg.lookback_events)).mean())
    score_series = pd.Series(scores, dtype=float)
    selected = select_from_scores(
        score_series,
        max_positions=cfg.max_positions,
        min_trailing_funding_rate=cfg.min_trailing_funding_rate,
    )
    selected_scores = score_series.reindex(selected).dropna()
    mean_score = float(selected_scores.mean()) if len(selected_scores) else 0.0
    return {
        "status": "ok",
        "latest_funding_time": latest_time,
        "latest_funding_time_iso": timestamp_ms_to_iso(latest_time),
        "positions": [
            {
                "symbol": symbol,
                "side": "short_perp_long_spot",
                "trailing_funding_rate": float(score_series.loc[symbol]),
                "trailing_funding_bps_per_8h": float(score_series.loc[symbol]) * 10_000.0,
            }
            for symbol in selected
        ],
        "position_count": int(len(selected)),
        "mean_trailing_funding_rate": mean_score,
        "expected_notional_annualized_return": mean_score * EVENTS_PER_YEAR,
        "expected_capital_annualized_return": mean_score * EVENTS_PER_YEAR / max(float(cfg.capital_multiplier), 1.0),
    }


def gate_checks(
    *,
    selection: dict[str, Any],
    validation: dict[str, Any],
    stress_validation: dict[str, Any],
    recent_30d: dict[str, Any],
    recent_90d: dict[str, Any],
    current: dict[str, Any],
    min_validation_events: int,
    min_capital_annualized_return: float,
    min_current_capital_annualized_return: float,
    max_drawdown: float,
) -> dict[str, bool]:
    return {
        "selection_active_events_ge_min": int(selection.get("selection_active_events", 0)) >= int(min_validation_events),
        "validation_active_events_ge_min": int(validation.get("validation_active_events", 0)) >= int(min_validation_events),
        "validation_capital_return_ge_min": float(validation.get("validation_capital_annualized_return", 0.0))
        >= float(min_capital_annualized_return),
        "validation_capital_sharpe_ge_1": float(validation.get("validation_capital_sharpe", 0.0)) >= 1.0,
        "validation_drawdown_le_max": float(validation.get("validation_capital_max_drawdown", 1.0)) <= float(max_drawdown),
        "stress_validation_return_gt_0": float(stress_validation.get("stress_validation_capital_annualized_return", 0.0))
        > 0.0,
        "stress_validation_sharpe_ge_0_5": float(stress_validation.get("stress_validation_capital_sharpe", 0.0)) >= 0.5,
        "recent_90d_return_gt_0": float(recent_90d.get("recent_90d_capital_annualized_return", 0.0)) > 0.0,
        "recent_30d_not_bad": float(recent_30d.get("recent_30d_capital_total_return", -1.0)) > -0.01,
        "current_signal_exists": int(current.get("position_count", 0)) > 0,
        "current_expected_return_ge_min": float(current.get("expected_capital_annualized_return", 0.0))
        >= float(min_current_capital_annualized_return),
    }


def evaluate_config(
    frame: pd.DataFrame,
    cfg: DeltaNeutralFundingConfig,
    *,
    selection_frac: float,
    min_validation_events: int,
    min_capital_annualized_return: float,
    min_current_capital_annualized_return: float,
    max_drawdown: float,
) -> dict[str, Any]:
    detail = build_event_detail(frame, cfg, turnover_cost_bps=cfg.turnover_cost_bps)
    stress_detail = build_event_detail(frame, cfg, turnover_cost_bps=cfg.stress_turnover_cost_bps)
    selection_detail, validation_detail = split_detail(detail, selection_frac=selection_frac)
    _, stress_validation_detail = split_detail(stress_detail, selection_frac=selection_frac)
    selection = summarize_detail(selection_detail, prefix="selection_")
    validation = summarize_detail(validation_detail, prefix="validation_")
    stress_validation = summarize_detail(stress_validation_detail, prefix="stress_validation_")
    recent_30 = summarize_detail(recent_detail(detail, days=30), prefix="recent_30d_")
    recent_90 = summarize_detail(recent_detail(detail, days=90), prefix="recent_90d_")
    current = current_signal(frame, cfg)
    checks = gate_checks(
        selection=selection,
        validation=validation,
        stress_validation=stress_validation,
        recent_30d=recent_30,
        recent_90d=recent_90,
        current=current,
        min_validation_events=min_validation_events,
        min_capital_annualized_return=min_capital_annualized_return,
        min_current_capital_annualized_return=min_current_capital_annualized_return,
        max_drawdown=max_drawdown,
    )
    return {
        "config": asdict(cfg),
        "selection": selection,
        "validation": validation,
        "stress_validation": stress_validation,
        "recent_30d": recent_30,
        "recent_90d": recent_90,
        "current_signal": current,
        "advance_checks": checks,
        "paper_watch_candidate": bool(all(checks.values())),
    }


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    validation = row.get("validation") or {}
    current = row.get("current_signal") or {}
    return (
        bool(row.get("paper_watch_candidate")),
        float(validation.get("validation_capital_sharpe", 0.0)),
        float(validation.get("validation_capital_annualized_return", 0.0)),
        -float(validation.get("validation_capital_max_drawdown", 1.0)),
        float(current.get("expected_capital_annualized_return", 0.0)),
    )


def config_grid(args: argparse.Namespace) -> tuple[DeltaNeutralFundingConfig, ...]:
    lookbacks = parse_int_grid(args.lookback_events_grid)
    positions = parse_int_grid(args.max_positions_grid)
    thresholds_bps = parse_float_grid(args.min_trailing_funding_bps_grid)
    return tuple(
        DeltaNeutralFundingConfig(
            lookback_events=lookback,
            max_positions=max_positions,
            min_trailing_funding_rate=threshold_bps / 10_000.0,
            turnover_cost_bps=float(args.turnover_cost_bps),
            stress_turnover_cost_bps=float(args.stress_turnover_cost_bps),
            capital_multiplier=float(args.capital_multiplier),
        )
        for lookback, max_positions, threshold_bps in itertools.product(lookbacks, positions, thresholds_bps)
    )


def run_screen(args: argparse.Namespace) -> dict[str, Any]:
    fallback = parse_symbols(args.symbols) or DEFAULT_SYMBOLS
    symbols = parse_symbols(args.symbols) or symbols_from_universe(args.universe_json, top_n=args.top_n, fallback=fallback)
    frame = load_funding_cache(Path(args.cache_dir), symbols)
    frame = filter_funding_window(frame, start=args.start, end=args.end)
    rows = [
        evaluate_config(
            frame,
            cfg,
            selection_frac=args.selection_frac,
            min_validation_events=args.min_validation_events,
            min_capital_annualized_return=args.min_capital_annualized_return,
            min_current_capital_annualized_return=args.min_current_capital_annualized_return,
            max_drawdown=args.max_drawdown,
        )
        for cfg in config_grid(args)
    ]
    rows.sort(key=row_sort_key, reverse=True)
    pass_rows = [row for row in rows if row.get("paper_watch_candidate")]
    payload = {
        "kind": "funding_delta_neutral_paper_screen_v1",
        "updated_at": now_utc(),
        "cache_dir": args.cache_dir,
        "universe_json": args.universe_json,
        "symbols": symbols,
        "loaded_rows": int(len(frame)),
        "data": {
            "first_funding_time": timestamp_ms_to_iso(int(frame["funding_time"].min())) if len(frame) else None,
            "last_funding_time": timestamp_ms_to_iso(int(frame["funding_time"].max())) if len(frame) else None,
            "start": args.start,
            "end": args.end,
        },
        "gate": {
            "selection_frac": float(args.selection_frac),
            "min_validation_events": int(args.min_validation_events),
            "min_capital_annualized_return": float(args.min_capital_annualized_return),
            "min_current_capital_annualized_return": float(args.min_current_capital_annualized_return),
            "max_drawdown": float(args.max_drawdown),
            "variant_count": len(rows),
            "note": "Paper watch only. Live trading is not authorized.",
        },
        "summary": {
            "rows": len(rows),
            "paper_watch_candidate_count": len(pass_rows),
            "paper_watch_candidate_found": bool(pass_rows),
            "paper_trading_authorized": False,
            "live_trading_authorized": False,
        },
        "top": rows[:10],
        "rows": rows,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    return payload


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_marker(payload: dict[str, Any], marker_path: Path, no_marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    no_marker_path.parent.mkdir(parents=True, exist_ok=True)
    if payload["summary"]["paper_watch_candidate_found"]:
        best = payload["top"][0]
        cfg = best["config"]
        current = best["current_signal"]
        marker_path.write_text(
            "FOUND_FUNDING_PAPER_WATCH "
            f"{payload['updated_at']} "
            f"lookback_events={cfg['lookback_events']} "
            f"max_positions={cfg['max_positions']} "
            f"min_trailing_funding_bps={cfg['min_trailing_funding_rate'] * 10000.0:.4f} "
            f"validation_capital_ann={best['validation']['validation_capital_annualized_return']:.6f} "
            f"validation_sharpe={best['validation']['validation_capital_sharpe']:.6f} "
            f"current_expected_capital_ann={current.get('expected_capital_annualized_return', 0.0):.6f} "
            f"positions={','.join(pos['symbol'] for pos in current.get('positions', []))} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if no_marker_path.exists():
            no_marker_path.unlink()
    else:
        no_marker_path.write_text(
            "NO_FUNDING_PAPER_WATCH "
            f"{payload['updated_at']} "
            f"rows={payload['summary']['rows']} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if marker_path.exists():
            marker_path.unlink()


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Funding Delta-Neutral Paper Screen",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- loaded_rows: `{payload['loaded_rows']}`",
        f"- symbols: `{len(payload['symbols'])}`",
        f"- paper_watch_candidate_found: `{payload['summary']['paper_watch_candidate_found']}`",
        f"- paper_watch_candidate_count: `{payload['summary']['paper_watch_candidate_count']}`",
        "",
        "| rank | paper_watch | lookback | max_pos | min_bps_8h | val_cap_ann | val_sharpe | val_dd | recent90_ann | current_ann | positions |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(payload["top"], start=1):
        cfg = row["config"]
        val = row["validation"]
        recent = row["recent_90d"]
        current = row["current_signal"]
        positions = ",".join(pos["symbol"] for pos in current.get("positions", []))
        lines.append(
            f"| {idx} | {row.get('paper_watch_candidate')} | {cfg['lookback_events']} | "
            f"{cfg['max_positions']} | {cfg['min_trailing_funding_rate'] * 10000.0:.2f} | "
            f"{val['validation_capital_annualized_return']:.4f} | {val['validation_capital_sharpe']:.4f} | "
            f"{val['validation_capital_max_drawdown']:.4f} | "
            f"{recent['recent_90d_capital_annualized_return']:.4f} | "
            f"{current.get('expected_capital_annualized_return', 0.0):.4f} | {positions} |"
        )
    lines.extend(
        [
            "",
            "This screen proposes paper-watch candidates only. It does not authorize live trading.",
        ]
    )
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"updated_at={payload['updated_at']}",
        f"loaded_rows={payload['loaded_rows']}",
        f"paper_watch_candidate_found={summary['paper_watch_candidate_found']}",
        f"paper_watch_candidate_count={summary['paper_watch_candidate_count']}",
        "safety=paper_authorized:False live:False",
    ]
    if payload["top"]:
        best = payload["top"][0]
        cfg = best["config"]
        current = best["current_signal"]
        lines.append(
            "best "
            f"paper_watch={best['paper_watch_candidate']} "
            f"lookback={cfg['lookback_events']} "
            f"max_positions={cfg['max_positions']} "
            f"min_bps_8h={cfg['min_trailing_funding_rate'] * 10000.0:.2f} "
            f"val_cap_ann={best['validation']['validation_capital_annualized_return']:.4f} "
            f"val_sharpe={best['validation']['validation_capital_sharpe']:.4f} "
            f"current_ann={current.get('expected_capital_annualized_return', 0.0):.4f} "
            f"positions={','.join(pos['symbol'] for pos in current.get('positions', []))}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper-watch screen for same-symbol spot/perp funding carry.")
    parser.add_argument("--cache-dir", default="data/binance_funding_cache")
    parser.add_argument("--universe-json", default="artifacts/v9/universe/binance_usdm_top30_volume_snapshot.json")
    parser.add_argument("--top-n", type=int, default=12)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="")
    parser.add_argument("--lookback-events-grid", default="21,63,90")
    parser.add_argument("--max-positions-grid", default="1,2,3")
    parser.add_argument("--min-trailing-funding-bps-grid", default="1.0,1.5,2.0")
    parser.add_argument("--turnover-cost-bps", type=float, default=10.0)
    parser.add_argument("--stress-turnover-cost-bps", type=float, default=15.0)
    parser.add_argument("--capital-multiplier", type=float, default=2.0)
    parser.add_argument("--selection-frac", type=float, default=0.70)
    parser.add_argument("--min-validation-events", type=int, default=60)
    parser.add_argument("--min-capital-annualized-return", type=float, default=0.05)
    parser.add_argument("--min-current-capital-annualized-return", type=float, default=0.08)
    parser.add_argument("--max-drawdown", type=float, default=0.05)
    parser.add_argument("--out-json", default="artifacts/v9/contract_lab/funding_delta_neutral_paper_screen_v1.json")
    parser.add_argument("--out-md", default="artifacts/v9/contract_lab/funding_delta_neutral_paper_screen_v1.md")
    parser.add_argument("--marker", default="state/FOUND_FUNDING_PAPER_WATCH.txt")
    parser.add_argument("--no-marker", default="state/NO_FUNDING_PAPER_WATCH.txt")
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
