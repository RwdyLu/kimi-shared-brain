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
DECISION_POLICY_VERSION = "portfolio_gate_v4_drawdown_recovery"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = [part.strip().upper() for part in raw.replace(",", " ").split() if part.strip()]
    return tuple(symbols)


def parse_timeframes(raw: str) -> tuple[str, ...]:
    timeframes = []
    seen = set()
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        timeframe = part.strip().lower()
        if not timeframe or timeframe in seen:
            continue
        # Reuse interval parsing for validation.
        interval_minutes(timeframe)
        seen.add(timeframe)
        timeframes.append(timeframe)
    return tuple(timeframes)


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


def normalized_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw = value.replace(";", ",")
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def blocked_confirmation_cohort_ref_from_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]] | None:
    timeframe = str(row.get("timeframe") or default_timeframe).lower()
    side = str(row.get("side") or "").lower()
    bucket = str(row.get("confirmation_bucket") or "").strip()
    if not timeframe or side not in {"long", "short"} or not bucket:
        return None
    return (
        timeframe,
        side,
        bucket,
        normalized_str_tuple(row.get("confirmation_timeframes")),
        normalized_str_tuple(row.get("confirmation_regime_ids")),
    )


def read_blocked_confirmation_cohort_refs(
    path: str,
    *,
    default_timeframe: str,
) -> set[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        return set()

    rows: list[Any] = []
    if isinstance(payload, list):
        rows.extend(payload)
    elif isinstance(payload, dict):
        rows.extend(payload.get("blocked_confirmation_cohorts") or [])
        actions = payload.get("actions") or {}
        if isinstance(actions, dict):
            rows.extend(actions.get("current_policy_blocked_confirmation_cohorts") or [])
            rows.extend(actions.get("blocked_confirmation_cohorts") or [])

    refs: set[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = blocked_confirmation_cohort_ref_from_row(row, default_timeframe=default_timeframe)
        if ref is not None:
            refs.add(ref)
    return refs


def blocked_regime_cohort_ref_from_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
) -> tuple[str, str, str] | None:
    timeframe = str(row.get("timeframe") or default_timeframe).lower()
    side = str(row.get("side") or "").lower()
    regime_id = str(row.get("market_regime_id") or row.get("regime_id") or "").strip()
    if not timeframe or side not in {"long", "short"} or not regime_id:
        return None
    return timeframe, side, regime_id


def read_blocked_regime_cohort_refs(
    path: str,
    *,
    default_timeframe: str,
) -> set[tuple[str, str, str]]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        return set()

    rows: list[Any] = []
    if isinstance(payload, list):
        rows.extend(payload)
    elif isinstance(payload, dict):
        rows.extend(payload.get("blocked_regime_cohorts") or [])
        actions = payload.get("actions") or {}
        if isinstance(actions, dict):
            rows.extend(actions.get("current_policy_blocked_regime_cohorts") or [])
            rows.extend(actions.get("current_policy_active_blocked_regime_cohorts") or [])
            rows.extend(actions.get("current_policy_fast_shadow_blocked_regime_cohorts") or [])
            rows.extend(actions.get("current_policy_fast_shadow_active_blocked_regime_cohorts") or [])
            rows.extend(actions.get("blocked_regime_cohorts") or [])

    refs: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = blocked_regime_cohort_ref_from_row(row, default_timeframe=default_timeframe)
        if ref is not None:
            refs.add(ref)
    return refs


TREND_ALIGNMENT_BLOCK_STATUSES = {
    "trend_following_weak",
    "active_trend_following_weak",
    "countertrend_block_supported",
    "active_countertrend_block_supported",
    "range_risk",
    "active_range_risk",
}


def blocked_trend_alignment_cohort_ref_from_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
) -> tuple[str, str, str, str, str] | None:
    timeframe = str(row.get("timeframe") or default_timeframe).lower()
    side = str(row.get("side") or "").lower()
    trend_state = str(row.get("market_trend_state") or "unknown").lower()
    alignment = str(row.get("trend_alignment_bucket") or "trend_unknown").lower()
    confirmation = str(row.get("confirmation_bucket") or "untracked")
    if not timeframe or side not in {"long", "short"} or not trend_state or not alignment or not confirmation:
        return None
    return timeframe, side, trend_state, alignment, confirmation


def read_blocked_trend_alignment_cohort_refs(
    path: str,
    *,
    default_timeframe: str,
) -> set[tuple[str, str, str, str, str]]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        return set()

    rows: list[Any] = []
    if isinstance(payload, list):
        rows.extend(payload)
    elif isinstance(payload, dict):
        rows.extend(payload.get("blocked_trend_alignment_cohorts") or [])
        actions = payload.get("actions") or {}
        if isinstance(actions, dict):
            for key in (
                "current_policy_trend_alignment_risk",
                "current_policy_trend_alignment_supported",
                "current_policy_shadow_trend_alignment_risk",
                "current_policy_fast_shadow_trend_alignment_risk",
            ):
                for row in actions.get(key) or []:
                    if isinstance(row, dict) and str(row.get("status") or "") in TREND_ALIGNMENT_BLOCK_STATUSES:
                        rows.append(row)

    refs: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = blocked_trend_alignment_cohort_ref_from_row(row, default_timeframe=default_timeframe)
        if ref is not None:
            refs.add(ref)
    return refs


def read_shadow_retest_pair_refs(path: str, *, default_timeframe: str) -> set[tuple[str, str, str]]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        return set()

    rows: list[Any] = []
    if isinstance(payload, list):
        rows.extend(payload)
    elif isinstance(payload, dict):
        rows.extend(payload.get("current_policy_fast_shadow_retest_candidates") or [])
        retest = payload.get("current_policy_fast_shadow_retest") or {}
        if isinstance(retest, dict):
            rows.extend(retest.get("retest_candidates") or [])
        rows.extend(payload.get("retest_candidates") or [])

    refs: set[tuple[str, str, str]] = set()
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


def journal_blocked_confirmation_cohort_refs(
    args: argparse.Namespace,
) -> set[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]]:
    return read_blocked_confirmation_cohort_refs(
        getattr(args, "journal_blocked_pairs_json", ""),
        default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
    )


def journal_blocked_regime_cohort_refs(args: argparse.Namespace) -> set[tuple[str, str, str]]:
    return read_blocked_regime_cohort_refs(
        getattr(args, "journal_blocked_pairs_json", ""),
        default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
    )


def journal_blocked_trend_alignment_cohort_refs(args: argparse.Namespace) -> set[tuple[str, str, str, str, str]]:
    return read_blocked_trend_alignment_cohort_refs(
        getattr(args, "journal_blocked_pairs_json", ""),
        default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
    )


def journal_shadow_retest_pair_refs(args: argparse.Namespace) -> set[tuple[str, str, str]]:
    return read_shadow_retest_pair_refs(
        getattr(args, "journal_shadow_retest_json", ""),
        default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
    )


def risk_portfolio_from_payload(payload: dict[str, Any], scope: str) -> tuple[dict[str, Any], str]:
    actions = payload.get("actions") or {}
    if scope == "current_policy":
        for key in ("current_policy_portfolio_risk", "portfolio_risk"):
            portfolio = payload.get(key) or actions.get(key)
            if isinstance(portfolio, dict):
                return portfolio, key
    portfolio = payload.get("portfolio_risk") or actions.get("portfolio_risk") or {}
    return portfolio if isinstance(portfolio, dict) else {}, "portfolio_risk"


def journal_risk_controls(args: argparse.Namespace) -> dict[str, Any]:
    path = str(getattr(args, "journal_risk_actions_json", "") or "")
    scope = str(getattr(args, "journal_risk_scope", "current_policy") or "current_policy")
    if not path:
        return {"enabled": False, "scope": scope}
    p = Path(path)
    if not p.exists():
        return {"enabled": False, "path": path, "missing": True, "scope": scope}
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {"enabled": False, "path": path, "invalid_json": True, "scope": scope}
    portfolio, source_key = risk_portfolio_from_payload(payload, scope)
    segment_risk = portfolio.get("segment_risk") or {}
    blocked_sides = set(str(side).lower() for side in (portfolio.get("blocked_sides") or []))
    blocked_sides.update(str(side).lower() for side in (segment_risk.get("blocked_sides") or []))
    segments = segment_risk.get("segments") if isinstance(segment_risk.get("segments"), dict) else {}
    thresholds = portfolio.get("thresholds") if isinstance(portfolio.get("thresholds"), dict) else {}
    return {
        "enabled": True,
        "path": path,
        "scope": scope,
        "source_key": source_key,
        "decision_policy_version": str(portfolio.get("decision_policy_version") or ""),
        "status": portfolio.get("status"),
        "block_new_focus": bool(portfolio.get("block_new_focus")),
        "active": int(portfolio.get("active") or 0),
        "active_excess": int(portfolio.get("active_excess") or 0),
        "max_active": int(thresholds.get("portfolio_max_active") or 0),
        "reason_codes": portfolio.get("reason_codes") or [],
        "blocked_sides": sorted(side for side in blocked_sides if side in {"long", "short"}),
        "side_reason_codes": portfolio.get("side_reason_codes") or segment_risk.get("reason_codes") or [],
        "segments": segments,
    }


def active_cap_record_allowed(record: dict[str, Any], *, scope: str, current_policy_version: str) -> bool:
    if scope != "current_policy":
        return True
    return str(record.get("decision_policy_version") or "") == current_policy_version


def journal_portfolio_drawdown_recovery_probe_allowed(
    row: dict[str, Any],
    risk_controls: dict[str, Any],
    args: argparse.Namespace,
) -> bool:
    if not bool(getattr(args, "journal_allow_portfolio_drawdown_recovery_probes", True)):
        return False
    if str(risk_controls.get("status") or "") != "portfolio_drawdown":
        return False
    if int(risk_controls.get("active") or 0) > int(getattr(args, "journal_portfolio_recovery_max_active", 12)):
        return False
    if int(risk_controls.get("active_excess") or 0) > int(
        getattr(args, "journal_portfolio_recovery_max_active_excess", 0)
    ):
        return False
    reason_codes = [str(reason) for reason in (risk_controls.get("reason_codes") or [])]
    hard_prefixes = ("portfolio_active>", "portfolio_active_R", "portfolio_active_loss_rate")
    if any(reason.startswith(hard_prefixes) for reason in reason_codes):
        return False

    analog = row.get("analog_evidence") or {}
    if not analog.get("supported"):
        return False
    if int(analog.get("used_count") or 0) < int(getattr(args, "journal_portfolio_recovery_min_analog_samples", 50)):
        return False
    if safe_float(analog.get("hit_rate")) < float(getattr(args, "journal_portfolio_recovery_min_hit_rate", 0.55)):
        return False
    if safe_float(analog.get("profitable_rate")) < float(
        getattr(args, "journal_portfolio_recovery_min_profitable_rate", 0.55)
    ):
        return False
    if safe_float(analog.get("expectancy_r")) < float(
        getattr(args, "journal_portfolio_recovery_min_expectancy_r", 0.35)
    ):
        return False
    return True


def journal_side_recovery_probe_allowed(
    row: dict[str, Any],
    side: str,
    risk_controls: dict[str, Any],
    args: argparse.Namespace,
) -> bool:
    if not bool(getattr(args, "journal_allow_side_recovery_probes", True)):
        return False
    if not risk_controls.get("enabled"):
        return False
    if risk_controls.get("block_new_focus"):
        return False
    segments = risk_controls.get("segments") or {}
    segment = segments.get(side)
    if not isinstance(segment, dict):
        return False
    max_segment_active = int(getattr(args, "journal_side_recovery_max_segment_active", 0))
    if int(segment.get("active") or 0) > max_segment_active:
        return False

    analog = row.get("analog_evidence") or {}
    if not analog.get("supported"):
        return False
    if int(analog.get("used_count") or 0) < int(getattr(args, "journal_side_recovery_min_analog_samples", 50)):
        return False
    if safe_float(analog.get("hit_rate")) < float(getattr(args, "journal_side_recovery_min_hit_rate", 0.55)):
        return False
    if safe_float(analog.get("profitable_rate")) < float(
        getattr(args, "journal_side_recovery_min_profitable_rate", 0.55)
    ):
        return False
    if safe_float(analog.get("expectancy_r")) < float(getattr(args, "journal_side_recovery_min_expectancy_r", 0.35)):
        return False
    return True


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


def data_freshness_reference(args: argparse.Namespace) -> str:
    return str(
        getattr(args, "_data_freshness_reference_utc", "")
        or getattr(args, "data_freshness_now", "")
        or now_utc()
    )


def market_data_freshness_decision(latest_dt: Any, args: argparse.Namespace) -> dict[str, Any]:
    mode = str(getattr(args, "data_freshness_mode", "block") or "block")
    timeframe = str(getattr(args, "timeframe", "") or "")
    max_age_bars = float(getattr(args, "data_freshness_max_age_bars", 2.5))
    grace_minutes = float(getattr(args, "data_freshness_grace_minutes", 5.0))
    thresholds = {
        "max_age_bars": max_age_bars,
        "grace_minutes": grace_minutes,
    }
    if mode == "off":
        return {
            "enabled": False,
            "allowed": True,
            "mode": mode,
            "reason": "data_freshness_off",
            "thresholds": thresholds,
        }
    try:
        latest = parse_utc_timestamp(latest_dt)
        reference = parse_utc_timestamp(data_freshness_reference(args))
        interval = interval_minutes(timeframe)
    except Exception as exc:
        allowed = mode == "annotate"
        return {
            "enabled": True,
            "allowed": allowed,
            "mode": mode,
            "reason": "data_freshness_invalid_timestamp" if not allowed else "data_freshness_invalid_annotated",
            "error": str(exc),
            "latest_dt": str(latest_dt),
            "reference_dt": data_freshness_reference(args),
            "thresholds": thresholds,
        }
    age_minutes = max(0.0, (reference - latest).total_seconds() / 60.0)
    age_bars = age_minutes / interval if interval > 0.0 else float("inf")
    max_age_minutes = interval * max_age_bars + grace_minutes
    fresh = age_minutes <= max_age_minutes
    allowed = fresh or mode == "annotate"
    if fresh:
        reason = "data_freshness_pass"
    elif mode == "annotate":
        reason = "data_freshness_stale_annotated"
    else:
        reason = "data_freshness_stale_blocked"
    return {
        "enabled": True,
        "allowed": allowed,
        "mode": mode,
        "reason": reason,
        "latest_dt": latest.isoformat(),
        "reference_dt": reference.isoformat(),
        "timeframe": timeframe,
        "age_minutes": float(age_minutes),
        "age_bars": float(age_bars),
        "max_age_minutes": float(max_age_minutes),
        "thresholds": thresholds,
    }


def percentile_rank(series: pd.Series, value: float) -> float:
    xs = pd.to_numeric(series, errors="coerce").dropna()
    if xs.empty or not math.isfinite(value):
        return 0.0
    return float((xs <= value).mean())


def build_market_regime_context(frames_by_symbol: dict[str, pd.DataFrame], args: argparse.Namespace) -> dict[str, Any]:
    timeframe = str(getattr(args, "timeframe", "") or "").lower()
    if str(getattr(args, "regime_filter_mode", "off")) == "off":
        return {
            "enabled": False,
            "timeframe": timeframe,
            "regime_id": "disabled",
            "trend_state": "unknown",
            "vol_state": "unknown",
        }

    requested = parse_symbols(getattr(args, "regime_symbols", ""))
    symbols = requested or tuple(frames_by_symbol)
    samples = []
    min_bars = max(
        int(getattr(args, "slow_ema", 96)),
        int(getattr(args, "atr_n", 14)),
        bars_for_hours(getattr(args, "timeframe", "1h"), 24.0),
        25,
    ) + 2
    for symbol in symbols:
        frame = frames_by_symbol.get(symbol.upper())
        if frame is None or len(frame) < min_bars:
            continue
        features = prepare_feature_frame(frame, args).dropna(
            subset=["close", "ema_slow", "ema_fast", "slow_ema_slope", "ret_24h", "atr_pct"]
        )
        if features.empty:
            continue
        latest = features.iloc[-1]
        close = safe_float(latest.get("close"))
        ema_slow = safe_float(latest.get("ema_slow"))
        ema_fast = safe_float(latest.get("ema_fast"))
        slow_slope = safe_float(latest.get("slow_ema_slope"))
        ret_24h = safe_float(latest.get("ret_24h"))
        atr_pct = safe_float(latest.get("atr_pct"))
        direction_votes = 0
        direction_votes += 1 if close > ema_slow else -1
        direction_votes += 1 if ema_fast > ema_slow else -1
        direction_votes += (
            1 if slow_slope > float(args.min_slope) else (-1 if slow_slope < -float(args.min_slope) else 0)
        )
        direction_votes += (
            1 if ret_24h > float(args.min_ret_24h) else (-1 if ret_24h < -float(args.min_ret_24h) else 0)
        )
        samples.append(
            {
                "symbol": symbol.upper(),
                "latest_dt": latest["dt"].isoformat(),
                "close": close,
                "ret_24h": ret_24h,
                "slow_ema_slope": slow_slope,
                "ema_gap": safe_float(latest.get("ema_gap")),
                "atr_pct": atr_pct,
                "atr_percentile": percentile_rank(
                    features["atr_pct"].tail(int(args.regime_vol_lookback_bars)),
                    atr_pct,
                ),
                "direction_votes": int(direction_votes),
            }
        )

    if not samples:
        return {
            "enabled": True,
            "timeframe": timeframe,
            "regime_id": "unknown",
            "trend_state": "unknown",
            "vol_state": "unknown",
            "reason": "no_market_regime_samples",
            "source_symbols": [symbol.upper() for symbol in symbols],
            "samples": [],
            "thresholds": {
                "min_direction_votes": int(args.regime_min_direction_votes),
                "high_vol_percentile": float(args.regime_high_vol_percentile),
            },
        }

    direction_score = int(sum(int(row["direction_votes"]) for row in samples))
    min_votes = int(args.regime_min_direction_votes)
    if direction_score >= min_votes:
        trend_state = "uptrend"
    elif direction_score <= -min_votes:
        trend_state = "downtrend"
    else:
        trend_state = "range"
    median_atr_pct = float(pd.Series([row["atr_pct"] for row in samples]).median())
    median_atr_percentile = float(pd.Series([row["atr_percentile"] for row in samples]).median())
    vol_state = "high_vol" if median_atr_percentile >= float(args.regime_high_vol_percentile) else "normal_vol"
    return {
        "enabled": True,
        "timeframe": timeframe,
        "regime_id": f"{trend_state}_{vol_state}",
        "trend_state": trend_state,
        "vol_state": vol_state,
        "direction_score": direction_score,
        "median_atr_pct": median_atr_pct,
        "median_atr_percentile": median_atr_percentile,
        "source_symbols": [row["symbol"] for row in samples],
        "samples": samples,
        "thresholds": {
            "min_direction_votes": min_votes,
            "high_vol_percentile": float(args.regime_high_vol_percentile),
        },
    }


def clone_args_for_timeframe(args: argparse.Namespace, timeframe: str) -> argparse.Namespace:
    values = dict(vars(args))
    values["timeframe"] = timeframe
    return argparse.Namespace(**values)


def build_confirmation_regime_contexts(
    *,
    cache_dir: Path,
    args: argparse.Namespace,
    regime_symbols: tuple[str, ...],
) -> list[dict[str, Any]]:
    contexts = []
    for timeframe in parse_timeframes(str(getattr(args, "regime_confirm_timeframes", "") or "")):
        if timeframe == str(getattr(args, "timeframe", "") or "").lower():
            continue
        confirm_args = clone_args_for_timeframe(args, timeframe)
        frames = {
            symbol: load_symbol_cache(
                cache_dir,
                symbol,
                timeframe,
                lookback_bars=int(getattr(args, "lookback_bars", 20000)),
            )
            for symbol in regime_symbols
        }
        context = build_market_regime_context(frames, confirm_args)
        context["confirmation_timeframe"] = timeframe
        contexts.append(context)
    return contexts


def single_regime_filter_decision(
    signal: str,
    market_regime: dict[str, Any] | None,
    args: argparse.Namespace,
    *,
    mode: str,
) -> dict[str, Any]:
    context = market_regime or {
        "enabled": False,
        "trend_state": "unknown",
        "vol_state": "unknown",
        "regime_id": "unknown",
    }
    if mode == "off":
        return {"enabled": False, "allowed": True, "mode": mode, "reason": "regime_filter_off"}
    if signal not in {"long", "short"}:
        return {"enabled": True, "allowed": True, "mode": mode, "reason": "no_directional_signal"}
    if bool(getattr(args, "regime_block_high_vol", False)) and context.get("vol_state") == "high_vol":
        return {
            "enabled": True,
            "allowed": False,
            "mode": mode,
            "reason": "blocked_high_vol_regime",
            "regime_id": context.get("regime_id"),
        }
    trend_state = str(context.get("trend_state") or "unknown")
    if trend_state == "unknown":
        allowed = mode != "trend_only"
        return {
            "enabled": True,
            "allowed": allowed,
            "mode": mode,
            "reason": "unknown_regime_allowed" if allowed else "unknown_regime_blocked",
            "regime_id": context.get("regime_id"),
        }
    if mode == "annotate":
        return {
            "enabled": True,
            "allowed": True,
            "mode": mode,
            "reason": "annotate_only",
            "regime_id": context.get("regime_id"),
        }
    if signal == "long" and trend_state == "downtrend":
        return {
            "enabled": True,
            "allowed": False,
            "mode": mode,
            "reason": "long_blocked_by_market_downtrend",
            "regime_id": context.get("regime_id"),
        }
    if signal == "short" and trend_state == "uptrend":
        return {
            "enabled": True,
            "allowed": False,
            "mode": mode,
            "reason": "short_blocked_by_market_uptrend",
            "regime_id": context.get("regime_id"),
        }
    if mode == "trend_only" and trend_state == "range":
        return {
            "enabled": True,
            "allowed": False,
            "mode": mode,
            "reason": "range_regime_blocked",
            "regime_id": context.get("regime_id"),
        }
    return {
        "enabled": True,
        "allowed": True,
        "mode": mode,
        "reason": "regime_aligned",
        "regime_id": context.get("regime_id"),
    }


def regime_filter_decision(
    signal: str,
    market_regime: dict[str, Any] | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    mode = str(getattr(args, "regime_filter_mode", "off"))
    context = market_regime or {
        "enabled": False,
        "trend_state": "unknown",
        "vol_state": "unknown",
        "regime_id": "unknown",
    }
    decision = single_regime_filter_decision(signal, context, args, mode=mode)
    confirmation_contexts = context.get("confirmation_contexts") or []
    confirm_mode = str(getattr(args, "regime_confirm_mode", "block_conflict") or "block_conflict")
    if (
        decision.get("allowed", True)
        and mode != "off"
        and confirm_mode != "off"
        and signal in {"long", "short"}
        and confirmation_contexts
    ):
        confirmation_filters = []
        for confirmation in confirmation_contexts:
            confirmation_filter = single_regime_filter_decision(
                signal,
                confirmation,
                args,
                mode=confirm_mode,
            )
            confirmation_filters.append(
                {
                    **confirmation_filter,
                    "timeframe": confirmation.get("confirmation_timeframe")
                    or confirmation.get("timeframe"),
                    "regime_id": confirmation.get("regime_id"),
                    "trend_state": confirmation.get("trend_state"),
                    "vol_state": confirmation.get("vol_state"),
                    "direction_score": confirmation.get("direction_score"),
                }
            )
            if not confirmation_filter.get("allowed", True):
                timeframe = confirmation.get("confirmation_timeframe") or confirmation.get(
                    "timeframe"
                )
                return {
                    **decision,
                    "allowed": False,
                    "reason": f"confirmation_{timeframe}_{confirmation_filter.get('reason')}",
                    "confirmation_mode": confirm_mode,
                    "confirmation_filters": confirmation_filters,
                }
        return {
            **decision,
            "confirmation_mode": confirm_mode,
            "confirmation_filters": confirmation_filters,
        }
    return decision


def market_quality_decision(row: pd.Series, args: argparse.Namespace, *, signal: str) -> dict[str, Any]:
    mode = str(getattr(args, "market_quality_mode", "block") or "block")
    thresholds = {
        "min_atr_pct": float(getattr(args, "market_quality_min_atr_pct", 0.0015)),
        "max_atr_pct": float(getattr(args, "market_quality_max_atr_pct", 0.08)),
        "max_ema_gap": float(getattr(args, "market_quality_max_ema_gap", 0.15)),
        "max_abs_ret_24h": float(getattr(args, "market_quality_max_abs_ret_24h", 0.20)),
        "max_breakout_extension": float(getattr(args, "market_quality_max_breakout_extension", 0.35)),
        "min_volume_ratio": float(getattr(args, "market_quality_min_volume_ratio", 0.25)),
    }
    if mode == "off":
        return {
            "enabled": False,
            "allowed": True,
            "mode": mode,
            "reason": "market_quality_off",
            "reason_codes": [],
            "thresholds": thresholds,
        }
    if signal not in {"long", "short"}:
        return {
            "enabled": True,
            "allowed": True,
            "mode": mode,
            "reason": "no_directional_signal",
            "reason_codes": [],
            "thresholds": thresholds,
        }

    atr_pct = safe_float(row.get("atr_pct"), float("nan"))
    ema_gap = safe_float(row.get("ema_gap"), float("nan"))
    ret_24h = safe_float(row.get("ret_24h"), float("nan"))
    breakout_pos = safe_float(row.get("breakout_pos"), float("nan"))
    volume_ratio = safe_float(row.get("volume_ratio"), float("nan"))
    reason_codes: list[str] = []

    if not math.isfinite(atr_pct):
        reason_codes.append("atr_pct_missing")
    elif atr_pct < thresholds["min_atr_pct"]:
        reason_codes.append(f"atr_pct<{thresholds['min_atr_pct']:.4f}")
    elif atr_pct > thresholds["max_atr_pct"]:
        reason_codes.append(f"atr_pct>{thresholds['max_atr_pct']:.4f}")

    if math.isfinite(ema_gap):
        if signal == "long" and ema_gap > thresholds["max_ema_gap"]:
            reason_codes.append(f"long_ema_gap>{thresholds['max_ema_gap']:.3f}")
        if signal == "short" and ema_gap < -thresholds["max_ema_gap"]:
            reason_codes.append(f"short_ema_gap<-{thresholds['max_ema_gap']:.3f}")

    if math.isfinite(ret_24h):
        if signal == "long" and ret_24h > thresholds["max_abs_ret_24h"]:
            reason_codes.append(f"long_ret_24h>{thresholds['max_abs_ret_24h']:.3f}")
        if signal == "short" and ret_24h < -thresholds["max_abs_ret_24h"]:
            reason_codes.append(f"short_ret_24h<-{thresholds['max_abs_ret_24h']:.3f}")

    if math.isfinite(breakout_pos):
        extension = thresholds["max_breakout_extension"]
        if signal == "long" and breakout_pos > 1.0 + extension:
            reason_codes.append(f"long_breakout_pos>{1.0 + extension:.2f}")
        if signal == "short" and breakout_pos < -extension:
            reason_codes.append(f"short_breakout_pos<-{extension:.2f}")

    if math.isfinite(volume_ratio) and volume_ratio < thresholds["min_volume_ratio"]:
        reason_codes.append(f"volume_ratio<{thresholds['min_volume_ratio']:.2f}")

    allowed = not reason_codes or mode == "annotate"
    if reason_codes and mode == "annotate":
        reason = "market_quality_annotated"
    elif reason_codes:
        reason = "market_quality_blocked"
    else:
        reason = "market_quality_pass"
    return {
        "enabled": True,
        "allowed": allowed,
        "mode": mode,
        "reason": reason,
        "reason_codes": reason_codes,
        "thresholds": thresholds,
        "atr_pct": None if not math.isfinite(atr_pct) else float(atr_pct),
        "ema_gap": None if not math.isfinite(ema_gap) else float(ema_gap),
        "ret_24h": None if not math.isfinite(ret_24h) else float(ret_24h),
        "breakout_pos": None if not math.isfinite(breakout_pos) else float(breakout_pos),
        "volume_ratio": None if not math.isfinite(volume_ratio) else float(volume_ratio),
    }


def prepare_feature_frame(frame: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    df = frame.copy().sort_values("dt").reset_index(drop=True)
    ret_6h_bars = bars_for_hours(args.timeframe, 6.0)
    ret_24h_bars = bars_for_hours(args.timeframe, 24.0)
    volume_window = max(2, int(getattr(args, "market_quality_volume_window", 48) or 48))
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
    df["volume_sma"] = (
        pd.to_numeric(df.get("volume", pd.Series(0.0, index=df.index)), errors="coerce")
        .rolling(volume_window, min_periods=max(2, min(volume_window, 12)))
        .mean()
    )
    df["volume_ratio"] = pd.to_numeric(df.get("volume", pd.Series(0.0, index=df.index)), errors="coerce") / df[
        "volume_sma"
    ].replace(0.0, pd.NA)
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
        "decision_policy_version": str(getattr(args, "decision_policy_version", DECISION_POLICY_VERSION)),
        "timeframe": str(getattr(args, "timeframe", "1h")),
        "fee_bps_per_side": float(getattr(args, "paper_fee_bps", 5.0)),
        "slippage_bps": float(getattr(args, "paper_slippage_bps", 2.0)),
        "entry_latency_bars": int(getattr(args, "paper_entry_latency_bars", 1)),
        "max_entry_drift_bps": float(getattr(args, "paper_max_entry_drift_bps", 80.0)),
        "funding_bps_per_8h": float(getattr(args, "paper_funding_bps_per_8h", 1.0)),
        "partial_fill_frac": float(getattr(args, "paper_partial_fill_frac", 1.0)),
        "min_fill_frac": float(getattr(args, "paper_min_fill_frac", 1.0)),
        "stale_grace_bars": int(getattr(args, "paper_stale_grace_bars", 4)),
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
        "stale_grace_bars": 4,
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


def simulate_realistic_analog_outcome(
    df: pd.DataFrame,
    *,
    start_idx: int,
    side: str,
    prices: dict[str, float],
    horizon_bars: int,
    config: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:
    entry_latency = max(0, int(config.get("entry_latency_bars") or 0))
    entry_idx = int(start_idx) + entry_latency
    if entry_idx >= len(df):
        return {
            "status": "pending",
            "exit_reason": "insufficient_entry_latency_bars",
            "r_multiple": None,
        }

    partial_fill_frac = safe_float(config.get("partial_fill_frac"), 1.0)
    min_fill_frac = safe_float(config.get("min_fill_frac"), 1.0)
    if partial_fill_frac < min_fill_frac:
        return {
            "status": "skipped",
            "exit_reason": "partial_fill_reject",
            "r_multiple": None,
            "partial_fill_frac": float(partial_fill_frac),
            "min_fill_frac": float(min_fill_frac),
        }

    entry_row = df.iloc[entry_idx]
    entry_reference = safe_float(entry_row.get("open"))
    planned_entry = safe_float(prices.get("entry_price"))
    if entry_reference <= 0.0 or planned_entry <= 0.0:
        return {
            "status": "skipped",
            "exit_reason": "invalid_entry_reference",
            "r_multiple": None,
        }

    entry_fill = adverse_entry_fill(side, entry_reference, safe_float(config.get("slippage_bps"), 2.0))
    drift_bps = abs(entry_fill / planned_entry - 1.0) * 10000.0
    max_drift_bps = safe_float(config.get("max_entry_drift_bps"), 80.0)
    if max_drift_bps > 0.0 and drift_bps > max_drift_bps:
        return {
            "status": "skipped",
            "exit_reason": "entry_drift_reject",
            "r_multiple": None,
            "planned_entry_price": float(planned_entry),
            "entry_reference_price": float(entry_reference),
            "entry_fill_price": float(entry_fill),
            "entry_drift_bps": float(drift_bps),
            "max_entry_drift_bps": float(max_drift_bps),
        }

    stop = safe_float(prices.get("stop_loss"))
    risk = entry_fill - stop if side == "long" else stop - entry_fill
    if risk <= 0.0:
        return {
            "status": "skipped",
            "exit_reason": "invalid_post_fill_risk",
            "r_multiple": None,
            "entry_fill_price": float(entry_fill),
            "stop_loss": float(stop),
        }

    outcome = simulate_realistic_exit(
        df,
        entry_idx=entry_idx,
        side=side,
        entry_fill=float(entry_fill),
        stop=stop,
        take_profit=safe_float(prices.get("take_profit")),
        horizon_bars=int(horizon_bars),
        config=config,
        timeframe=timeframe,
    )
    return {
        **outcome,
        "entry_dt": entry_row["dt"].isoformat(),
        "entry_reference_price": float(entry_reference),
        "entry_drift_bps": float(drift_bps),
        "planned_entry_price": float(planned_entry),
        "risk_per_unit": float(risk),
        "partial_fill_frac": float(partial_fill_frac),
    }


def analog_time_segment_robustness(outcomes: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    min_segments = max(1, int(getattr(args, "analog_min_robust_segments", 2)))
    min_samples = max(1, int(getattr(args, "analog_robust_segment_min_samples", 3)))
    min_expectancy = float(getattr(args, "min_analog_segment_expectancy_r", 0.0))
    min_profitable_rate = float(getattr(args, "min_analog_segment_profitable_rate", 0.45))
    thresholds = {
        "min_robust_segments": min_segments,
        "segment_min_samples": min_samples,
        "min_segment_expectancy_r": min_expectancy,
        "min_segment_profitable_rate": min_profitable_rate,
    }
    if min_segments <= 1:
        return {
            "enabled": False,
            "supported": True,
            "reason": "analog_time_segments_off",
            "thresholds": thresholds,
            "segments": [],
        }

    ordered = sorted(outcomes, key=lambda row: str(row.get("dt") or ""))
    if len(ordered) < min_segments * min_samples:
        return {
            "enabled": True,
            "supported": False,
            "reason": "insufficient_time_segment_samples",
            "used_count": len(ordered),
            "thresholds": thresholds,
            "segments": [],
        }

    segments = []
    for idx in range(min_segments):
        start = round(idx * len(ordered) / min_segments)
        end = round((idx + 1) * len(ordered) / min_segments)
        rows = ordered[start:end]
        r_values = [safe_float(row.get("r_multiple")) for row in rows]
        profitable = sum(1 for value in r_values if value > 0.0)
        segment_used = len(r_values)
        expectancy = sum(r_values) / segment_used if segment_used else 0.0
        profitable_rate = profitable / segment_used if segment_used else 0.0
        reasons = []
        if segment_used < min_samples:
            reasons.append(f"segment_used<{min_samples}")
        if expectancy < min_expectancy:
            reasons.append(f"segment_expectancy_r<{min_expectancy:g}")
        if profitable_rate < min_profitable_rate:
            reasons.append(f"segment_profitable_rate<{min_profitable_rate:g}")
        segments.append(
            {
                "segment": idx + 1,
                "start_dt": rows[0].get("dt") if rows else None,
                "end_dt": rows[-1].get("dt") if rows else None,
                "used_count": segment_used,
                "expectancy_r": float(expectancy),
                "profitable_rate": float(profitable_rate),
                "best_r": float(max(r_values)) if r_values else 0.0,
                "worst_r": float(min(r_values)) if r_values else 0.0,
                "reason_codes": reasons,
            }
        )

    failing = [segment for segment in segments if segment["reason_codes"]]
    worst_expectancy = min(float(segment["expectancy_r"]) for segment in segments)
    worst_profitable_rate = min(float(segment["profitable_rate"]) for segment in segments)
    return {
        "enabled": True,
        "supported": not failing,
        "reason": "analog_time_segments_pass" if not failing else "analog_time_segments_fail",
        "segment_count": len(segments),
        "failing_segment_count": len(failing),
        "worst_segment_expectancy_r": float(worst_expectancy),
        "worst_segment_profitable_rate": float(worst_profitable_rate),
        "thresholds": thresholds,
        "segments": segments,
    }


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

    config = execution_config_from_args(args)
    entry_latency = max(0, int(config.get("entry_latency_bars") or 0))
    max_idx = len(df) - 1 - horizon - entry_latency
    if max_idx < 0:
        return {"enabled": True, "supported": False, "reason": "insufficient_realistic_analog_horizon"}
    history = df.iloc[: max_idx + 1].copy()
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
    rejected_outcomes = []
    pending_outcomes = 0
    for idx, row in nearest.iterrows():
        prices = plan_prices(row, args, signal)
        if not prices:
            continue
        outcome = simulate_realistic_analog_outcome(
            df,
            start_idx=int(idx),
            side=signal,
            prices=prices,
            horizon_bars=horizon,
            config=config,
            timeframe=str(getattr(args, "timeframe", "1h")),
        )
        if outcome.get("status") == "skipped":
            rejected_outcomes.append(
                {
                    "dt": row["dt"].isoformat(),
                    "distance": float(row["analog_distance"]),
                    "exit_reason": outcome.get("exit_reason"),
                    "entry_drift_bps": outcome.get("entry_drift_bps"),
                }
            )
            continue
        if outcome.get("status") != "completed" or outcome.get("r_multiple") is None:
            pending_outcomes += 1
            continue
        outcomes.append(
            {
                "dt": row["dt"].isoformat(),
                "distance": float(row["analog_distance"]),
                "planned_entry": float(prices["entry_price"]),
                "entry_fill": float(outcome.get("entry_fill_price") or 0.0),
                "exit_reason": outcome["exit_reason"],
                "r_multiple": float(outcome["r_multiple"]),
                "gross_r_multiple": safe_float(outcome.get("gross_r_multiple")),
                "fee_cost_per_unit": safe_float(outcome.get("fee_cost_per_unit")),
                "funding_cost_per_unit": safe_float(outcome.get("funding_cost_per_unit")),
                "bars_held": int(outcome.get("bars_held") or 0),
            }
        )
    used = len(outcomes)
    if not outcomes:
        return {
            "enabled": True,
            "supported": False,
            "reason": "no_completed_realistic_analog_outcomes",
            "execution_model": REALISTIC_EXECUTION_MODEL_VERSION,
            "candidate_count": int(len(history)),
            "used_count": 0,
            "entry_reject_count": len(rejected_outcomes),
            "pending_count": int(pending_outcomes),
            "rejected_sample": rejected_outcomes[:5],
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
    robustness = analog_time_segment_robustness(outcomes, args)
    final_supported = bool(supported and robustness.get("supported"))
    if final_supported:
        reason = "analog_support_pass"
    elif supported and not robustness.get("supported"):
        reason = "analog_robustness_fail"
    else:
        reason = "analog_support_fail"
    return {
        "enabled": True,
        "supported": final_supported,
        "base_supported": bool(supported),
        "reason": reason,
        "execution_model": REALISTIC_EXECUTION_MODEL_VERSION,
        "candidate_count": int(len(history)),
        "used_count": used,
        "top_k": int(args.analog_top_k),
        "horizon_bars": horizon,
        "time_segment_robustness": robustness,
        "entry_latency_bars": entry_latency,
        "fee_bps_per_side": float(config.get("fee_bps_per_side") or 0.0),
        "slippage_bps": float(config.get("slippage_bps") or 0.0),
        "funding_bps_per_8h": float(config.get("funding_bps_per_8h") or 0.0),
        "entry_reject_count": len(rejected_outcomes),
        "pending_count": int(pending_outcomes),
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
        "rejected_sample": rejected_outcomes[:5],
        "thresholds": {
            "min_analog_samples": int(args.min_analog_samples),
            "min_analog_hit_rate": float(args.min_analog_hit_rate),
            "min_analog_profitable_rate": float(args.min_analog_profitable_rate),
            "min_analog_expectancy_r": float(args.min_analog_expectancy_r),
            "analog_min_robust_segments": int(getattr(args, "analog_min_robust_segments", 2)),
            "analog_robust_segment_min_samples": int(
                getattr(args, "analog_robust_segment_min_samples", 3)
            ),
            "min_analog_segment_expectancy_r": float(
                getattr(args, "min_analog_segment_expectancy_r", 0.0)
            ),
            "min_analog_segment_profitable_rate": float(
                getattr(args, "min_analog_segment_profitable_rate", 0.45)
            ),
        },
    }


def classify_signal(
    frame: pd.DataFrame,
    args: argparse.Namespace,
    *,
    symbol: str,
    market_regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "volume_ratio": safe_float(latest["volume_ratio"], float("nan")),
        "long_votes": long_score,
        "short_votes": short_score,
    }
    data_freshness = market_data_freshness_decision(latest["dt"], args)
    if signal == "none":
        return {
            "symbol": symbol,
            "status": "ok",
            "signal": "none",
            "reason": f"no_consensus long_votes={long_score} short_votes={short_score}",
            "latest_dt": latest["dt"].isoformat(),
            "close": close,
            "metrics": metrics,
            "market_regime": market_regime or {"enabled": False},
            "data_freshness": data_freshness,
            "regime_filter": regime_filter_decision(signal, market_regime, args),
            "market_quality": market_quality_decision(latest, args, signal=signal),
            "analog_evidence": {"enabled": True, "supported": False, "reason": "no_signal"},
            "paper_plan": None,
        }

    if not data_freshness.get("allowed", True):
        return {
            "symbol": symbol,
            "status": "data_stale",
            "signal": "none",
            "raw_signal": signal,
            "reason": str(data_freshness.get("reason") or "data_freshness_stale_blocked"),
            "latest_dt": latest["dt"].isoformat(),
            "previous_dt": previous["dt"].isoformat(),
            "close": close,
            "metrics": {**metrics, "votes": long_votes if signal == "long" else short_votes},
            "market_regime": market_regime or {"enabled": False},
            "data_freshness": data_freshness,
            "regime_filter": regime_filter_decision(signal, market_regime, args),
            "market_quality": market_quality_decision(latest, args, signal=signal),
            "analog_evidence": {"enabled": True, "supported": False, "reason": "data_freshness_stale"},
            "paper_plan": None,
        }

    regime_filter = regime_filter_decision(signal, market_regime, args)
    if not regime_filter.get("allowed", True):
        return {
            "symbol": symbol,
            "status": "regime_blocked",
            "signal": "none",
            "raw_signal": signal,
            "reason": str(regime_filter.get("reason") or "regime_blocked"),
            "latest_dt": latest["dt"].isoformat(),
            "previous_dt": previous["dt"].isoformat(),
            "close": close,
            "metrics": {**metrics, "votes": long_votes if signal == "long" else short_votes},
            "market_regime": market_regime or {"enabled": False},
            "data_freshness": data_freshness,
            "regime_filter": regime_filter,
            "market_quality": market_quality_decision(latest, args, signal=signal),
            "analog_evidence": {"enabled": True, "supported": False, "reason": "regime_blocked"},
            "paper_plan": None,
        }

    market_quality = market_quality_decision(latest, args, signal=signal)
    prices = plan_prices(latest, args, signal)
    if not prices:
        return {
            "symbol": symbol,
            "status": "invalid_plan",
            "signal": "none",
            "reason": "invalid_stop_or_take_profit",
            "market_regime": market_regime or {"enabled": False},
            "data_freshness": data_freshness,
            "regime_filter": regime_filter,
            "market_quality": market_quality,
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
    if not market_quality.get("allowed", True):
        return {
            "symbol": symbol,
            "status": "market_quality_blocked",
            "signal": "none",
            "raw_signal": signal,
            "reason": str(market_quality.get("reason") or "market_quality_blocked"),
            "latest_dt": latest["dt"].isoformat(),
            "previous_dt": previous["dt"].isoformat(),
            "close": close,
            "metrics": {**metrics, "votes": long_votes if signal == "long" else short_votes},
            "market_regime": market_regime or {"enabled": False},
            "data_freshness": data_freshness,
            "regime_filter": regime_filter,
            "market_quality": market_quality,
            "analog_evidence": analog,
            "paper_plan": plan,
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
        "market_regime": market_regime or {"enabled": False},
        "data_freshness": data_freshness,
        "regime_filter": regime_filter,
        "market_quality": market_quality,
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


def compact_confirmation_filters(regime_filter: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in regime_filter.get("confirmation_filters") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "timeframe": item.get("timeframe"),
                "allowed": bool(item.get("allowed", True)),
                "mode": item.get("mode"),
                "reason": item.get("reason"),
                "regime_id": item.get("regime_id"),
                "trend_state": item.get("trend_state"),
                "vol_state": item.get("vol_state"),
                "direction_score": item.get("direction_score"),
            }
        )
    return rows


def regime_confirmation_payload(regime_filter: dict[str, Any]) -> dict[str, Any]:
    confirmation_filters = compact_confirmation_filters(regime_filter)
    confirmation_allowed = (
        all(bool(item.get("allowed", True)) for item in confirmation_filters)
        if confirmation_filters
        else None
    )
    return {
        "regime_confirmation_mode": regime_filter.get("confirmation_mode"),
        "regime_confirmation_allowed": confirmation_allowed,
        "regime_confirmation_timeframes": [
            item.get("timeframe")
            for item in confirmation_filters
            if item.get("timeframe")
        ],
        "regime_confirmation_regime_ids": [
            item.get("regime_id")
            for item in confirmation_filters
            if item.get("regime_id")
        ],
        "regime_confirmation_reasons": [
            item.get("reason")
            for item in confirmation_filters
            if item.get("reason")
        ],
        "regime_confirmation_filters": confirmation_filters,
    }


def confirmation_bucket_from_regime_filter(regime_filter: dict[str, Any]) -> str:
    payload = regime_confirmation_payload(regime_filter)
    if not payload["regime_confirmation_filters"]:
        if payload["regime_confirmation_mode"] is not None:
            return "confirmation_context_missing"
        return "untracked"
    if payload["regime_confirmation_allowed"] is True:
        return "confirmed_aligned"
    if payload["regime_confirmation_allowed"] is False:
        return "confirmation_conflict"
    return "confirmation_unknown"


def confirmation_cohort_ref_for_signal_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
    regime_filter = row.get("regime_filter") or {}
    payload = regime_confirmation_payload(regime_filter)
    return (
        str(default_timeframe or "").lower(),
        str(row.get("signal") or "").lower(),
        confirmation_bucket_from_regime_filter(regime_filter),
        tuple(str(item) for item in payload["regime_confirmation_timeframes"]),
        tuple(str(item) for item in payload["regime_confirmation_regime_ids"]),
    )


def trend_alignment_bucket_for_values(side: str, trend_state: str) -> str:
    side = str(side or "").lower()
    trend_state = str(trend_state or "unknown").lower()
    if side not in {"long", "short"}:
        return "no_direction"
    if trend_state == "uptrend":
        return "trend_aligned" if side == "long" else "countertrend"
    if trend_state == "downtrend":
        return "trend_aligned" if side == "short" else "countertrend"
    if trend_state == "range":
        return "range"
    return "trend_unknown"


def trend_alignment_cohort_ref_for_signal_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
) -> tuple[str, str, str, str, str] | None:
    side = str(row.get("signal") or row.get("side") or "").lower()
    if side not in {"long", "short"}:
        return None
    market_regime = row.get("market_regime") or {}
    trend_state = str(row.get("market_trend_state") or market_regime.get("trend_state") or "unknown").lower()
    regime_filter = row.get("regime_filter") or {}
    return (
        str(row.get("timeframe") or default_timeframe).lower(),
        side,
        trend_state,
        trend_alignment_bucket_for_values(side, trend_state),
        confirmation_bucket_from_regime_filter(regime_filter),
    )


def regime_cohort_ref_for_signal_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
) -> tuple[str, str, str] | None:
    market_regime = row.get("market_regime") or {}
    regime_id = str(row.get("market_regime_id") or market_regime.get("regime_id") or "").strip()
    side = str(row.get("signal") or row.get("side") or "").lower()
    timeframe = str(row.get("timeframe") or default_timeframe).lower()
    if not timeframe or side not in {"long", "short"} or not regime_id:
        return None
    return timeframe, side, regime_id


def apply_regime_confirmation_to_record(
    record: dict[str, Any],
    row: dict[str, Any],
    *,
    updated_at: str,
) -> bool:
    payload = regime_confirmation_payload(row.get("regime_filter") or {})
    if (
        not payload["regime_confirmation_filters"]
        and payload["regime_confirmation_mode"] is None
    ):
        return False
    changed = False
    for key, value in payload.items():
        if record.get(key) != value:
            record[key] = value
            changed = True
    if changed:
        record["updated_at"] = updated_at
    return changed


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
    market_regime = row.get("market_regime") or {}
    regime_filter = row.get("regime_filter") or {}
    market_quality = row.get("market_quality") or {}
    data_freshness = row.get("data_freshness") or {}
    confirmation = regime_confirmation_payload(regime_filter)
    analog_robustness = analog.get("time_segment_robustness") or {}
    return {
        "kind": "contract_latest_market_signal_paper_journal_v1",
        "signal_id": signal_id(row),
        "created_at": updated_at,
        "updated_at": updated_at,
        "status": "pending_entry",
        "execution_model_version": REALISTIC_EXECUTION_MODEL_VERSION,
        "decision_policy_version": str(config.get("decision_policy_version") or DECISION_POLICY_VERSION),
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
        "market_regime_id": market_regime.get("regime_id"),
        "market_trend_state": market_regime.get("trend_state"),
        "market_vol_state": market_regime.get("vol_state"),
        "market_direction_score": market_regime.get("direction_score"),
        "market_regime_source_symbols": market_regime.get("source_symbols") or [],
        "data_freshness_mode": data_freshness.get("mode"),
        "data_freshness_allowed": data_freshness.get("allowed"),
        "data_freshness_reason": data_freshness.get("reason"),
        "data_freshness_reference_dt": data_freshness.get("reference_dt"),
        "data_freshness_age_minutes": data_freshness.get("age_minutes"),
        "data_freshness_age_bars": data_freshness.get("age_bars"),
        "data_freshness_max_age_minutes": data_freshness.get("max_age_minutes"),
        "regime_filter_mode": regime_filter.get("mode"),
        "regime_filter_reason": regime_filter.get("reason"),
        **confirmation,
        "market_quality_mode": market_quality.get("mode"),
        "market_quality_allowed": market_quality.get("allowed"),
        "market_quality_reason": market_quality.get("reason"),
        "market_quality_reason_codes": market_quality.get("reason_codes") or [],
        "market_quality_atr_pct": market_quality.get("atr_pct"),
        "market_quality_ema_gap": market_quality.get("ema_gap"),
        "market_quality_ret_24h": market_quality.get("ret_24h"),
        "market_quality_breakout_pos": market_quality.get("breakout_pos"),
        "market_quality_volume_ratio": market_quality.get("volume_ratio"),
        "analog_supported": bool(analog.get("supported")),
        "analog_base_supported": bool(analog.get("base_supported", analog.get("supported"))),
        "analog_reason": analog.get("reason"),
        "analog_used_count": int(analog.get("used_count") or 0),
        "analog_hit_rate": safe_float(analog.get("hit_rate")),
        "analog_profitable_rate": safe_float(analog.get("profitable_rate")),
        "analog_expectancy_r": safe_float(analog.get("expectancy_r")),
        "analog_time_segment_supported": analog_robustness.get("supported"),
        "analog_time_segment_reason": analog_robustness.get("reason"),
        "analog_time_segment_count": int(analog_robustness.get("segment_count") or 0),
        "analog_time_segment_failing_count": int(analog_robustness.get("failing_segment_count") or 0),
        "analog_worst_segment_expectancy_r": safe_float(
            analog_robustness.get("worst_segment_expectancy_r")
        ),
        "analog_worst_segment_profitable_rate": safe_float(
            analog_robustness.get("worst_segment_profitable_rate")
        ),
        "analog_time_segment_robustness": analog_robustness,
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


def shadow_record_from_row(
    row: dict[str, Any],
    *,
    updated_at: str,
    horizon_bars: int,
    execution_config: dict[str, Any],
    reason: str,
    reason_codes: list[str] | None = None,
    risk_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk_controls = risk_controls or {}
    record = journal_record_from_row(
        row,
        updated_at=updated_at,
        horizon_bars=horizon_bars,
        execution_config=execution_config,
    )
    record["kind"] = "contract_latest_market_signal_shadow_journal_v1"
    record["shadow_journal"] = True
    record["shadow_reason"] = reason
    record["shadow_reason_codes"] = reason_codes or []
    record["shadow_portfolio_risk_status"] = risk_controls.get("status")
    record["shadow_portfolio_blocked_sides"] = risk_controls.get("blocked_sides") or []
    record["shadow_global_active"] = risk_controls.get("active")
    record["shadow_global_max_active"] = risk_controls.get("max_active")
    return record


def shadow_record_allowed(row: dict[str, Any], args: argparse.Namespace, *, force: bool = False) -> bool:
    mode = str(getattr(args, "journal_shadow_record_mode", "inherit") or "inherit")
    if mode == "inherit":
        mode = str(getattr(args, "journal_record_mode", "all_signals") or "all_signals")
    if mode == "strong_analog":
        mode = "positive_expectancy"
    if mode == "off":
        return False
    if force:
        return True
    if mode == "all_signals":
        return True
    analog = row.get("analog_evidence") or {}
    if mode == "analog_supported":
        return bool(analog.get("supported"))
    if mode == "positive_expectancy":
        if bool(analog.get("supported")):
            return True
        if int(analog.get("used_count") or 0) < int(getattr(args, "journal_shadow_min_analog_samples", 20)):
            return False
        if safe_float(analog.get("expectancy_r")) < float(getattr(args, "journal_shadow_min_expectancy_r", 0.15)):
            return False
        if safe_float(analog.get("hit_rate")) < float(getattr(args, "journal_shadow_min_hit_rate", 0.30)):
            return False
        if safe_float(analog.get("profitable_rate")) < float(
            getattr(args, "journal_shadow_min_profitable_rate", 0.40)
        ):
            return False
        return True
    return False


def formal_entry_gate_reason_codes(row: dict[str, Any], args: argparse.Namespace) -> list[str]:
    mode = str(getattr(args, "journal_record_mode", "all_signals") or "all_signals")
    if mode == "all_signals":
        return []
    analog = row.get("analog_evidence") or {}
    reasons: list[str] = []
    if mode in {"analog_supported", "strong_analog"} and not bool(analog.get("supported")):
        reasons.append("analog_supported=false")
    if mode != "strong_analog":
        return reasons

    min_samples = int(getattr(args, "journal_strong_min_analog_samples", 30))
    min_expectancy = float(getattr(args, "journal_strong_min_expectancy_r", 0.25))
    min_hit_rate = float(getattr(args, "journal_strong_min_hit_rate", 0.50))
    min_profitable_rate = float(getattr(args, "journal_strong_min_profitable_rate", 0.55))
    require_robustness = bool(getattr(args, "journal_strong_require_robustness", True))
    used_count = int(analog.get("used_count") or 0)
    if used_count < min_samples:
        reasons.append(f"analog_used_count<{min_samples}")
    if safe_float(analog.get("expectancy_r")) < min_expectancy:
        reasons.append(f"analog_expectancy_r<{min_expectancy:g}")
    if safe_float(analog.get("hit_rate")) < min_hit_rate:
        reasons.append(f"analog_hit_rate<{min_hit_rate:g}")
    if safe_float(analog.get("profitable_rate")) < min_profitable_rate:
        reasons.append(f"analog_profitable_rate<{min_profitable_rate:g}")
    robustness = analog.get("time_segment_robustness") or {}
    if require_robustness and robustness.get("supported") is not True:
        reasons.append("analog_time_segment_robustness!=true")
    return reasons


def market_quality_blocked_candidate_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("status") != "market_quality_blocked":
        return None
    raw_signal = str(row.get("raw_signal") or "").lower()
    if raw_signal not in {"long", "short"} or not row.get("paper_plan"):
        return None
    return {
        **row,
        "signal": raw_signal,
        "blocked_signal": True,
        "blocked_signal_reason": row.get("reason"),
    }


def analog_robustness_failed_candidate(row: dict[str, Any]) -> bool:
    analog = row.get("analog_evidence") or {}
    robustness = analog.get("time_segment_robustness") or {}
    return (
        bool(analog.get("base_supported"))
        and not bool(analog.get("supported"))
        and str(analog.get("reason") or "") == "analog_robustness_fail"
        and robustness.get("supported") is False
    )


def analog_robustness_shadow_reason_codes(row: dict[str, Any]) -> list[str]:
    analog = row.get("analog_evidence") or {}
    robustness = analog.get("time_segment_robustness") or {}
    reason_codes = [
        "analog_robustness_fail",
        f"time_segment_reason={robustness.get('reason')}",
        f"failing_segments={int(robustness.get('failing_segment_count') or 0)}",
        f"worst_segment_expectancy_r={safe_float(robustness.get('worst_segment_expectancy_r')):.6g}",
        f"worst_segment_profitable_rate={safe_float(robustness.get('worst_segment_profitable_rate')):.6g}",
    ]
    for segment in robustness.get("segments") or []:
        if not isinstance(segment, dict) or not segment.get("reason_codes"):
            continue
        reason_codes.extend(
            f"segment_{int(segment.get('segment') or 0)}:{reason}"
            for reason in segment.get("reason_codes") or []
        )
    return reason_codes


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


def latest_frame_dt(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame.empty or "dt" not in frame.columns:
        return None
    try:
        return parse_utc_timestamp(frame.iloc[-1]["dt"])
    except Exception:
        return None


def elapsed_bars_since(frame: pd.DataFrame, value: Any, timeframe: str) -> int | None:
    try:
        reference = parse_utc_timestamp(value)
    except Exception:
        return None
    latest = latest_frame_dt(frame)
    if latest is None:
        return None
    elapsed_minutes = (latest - reference).total_seconds() / 60.0
    if elapsed_minutes < 0.0:
        return 0
    return int(math.floor(elapsed_minutes / interval_minutes(timeframe)))


def maybe_skip_stale_unresolved_record(
    record: dict[str, Any],
    frame: pd.DataFrame,
    *,
    updated_at: str,
    reason: str,
    reference_dt: Any,
    required_bars: int,
    stale_grace_bars: int,
    timeframe: str,
) -> bool:
    elapsed = elapsed_bars_since(frame, reference_dt, timeframe)
    if elapsed is None:
        return False
    stale_after = int(required_bars) + int(stale_grace_bars)
    if elapsed < stale_after:
        return False
    skip_realistic_record(
        record,
        updated_at=updated_at,
        reason=reason,
        elapsed_bars=int(elapsed),
        required_bars=int(required_bars),
        stale_grace_bars=int(stale_grace_bars),
        latest_data_dt=latest_frame_dt(frame).isoformat() if latest_frame_dt(frame) is not None else None,
    )
    return True


def frame_dt_index(frame: pd.DataFrame, value: Any) -> int | None:
    if value is None:
        return None
    try:
        target = parse_utc_timestamp(value)
    except Exception:
        return None
    candidates = frame.index[frame["dt"] == target]
    if len(candidates) == 0:
        return None
    return int(candidates[-1])


def update_realistic_record_outcome(record: dict[str, Any], frame: pd.DataFrame, *, updated_at: str) -> bool:
    if record.get("status") in {"completed", "skipped"}:
        return False
    if frame.empty:
        return False

    config = execution_config_from_record(record)
    side = str(record.get("side"))
    timeframe = str(record.get("timeframe") or config.get("timeframe") or "1h")
    entry_latency = max(0, int(config.get("entry_latency_bars") or 0))
    stale_grace_bars = max(0, int(config.get("stale_grace_bars") or 0))
    signal_idx = frame_dt_index(frame, record.get("signal_dt") or record.get("latest_dt"))
    entry_idx = (signal_idx + entry_latency) if signal_idx is not None else None

    modified = False
    if record.get("status") == "pending_entry":
        if entry_idx is None or entry_idx >= len(frame):
            if maybe_skip_stale_unresolved_record(
                record,
                frame,
                updated_at=updated_at,
                reason="stale_pending_entry_unresolved",
                reference_dt=record.get("signal_dt") or record.get("latest_dt"),
                required_bars=entry_latency,
                stale_grace_bars=stale_grace_bars,
                timeframe=timeframe,
            ):
                return True
            return False
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

    entry_idx = frame_dt_index(frame, record.get("entry_dt"))
    if entry_idx is None and signal_idx is not None:
        entry_idx = signal_idx + entry_latency
    if entry_idx is None:
        entry_idx = int(record.get("entry_bar_index") or -1)
    if entry_idx < 0 or entry_idx >= len(frame):
        if maybe_skip_stale_unresolved_record(
            record,
            frame,
            updated_at=updated_at,
            reason="stale_open_entry_unresolved",
            reference_dt=record.get("entry_dt"),
            required_bars=int(record.get("outcome_horizon_bars") or 24),
            stale_grace_bars=stale_grace_bars,
            timeframe=timeframe,
        ):
            return True
        return modified
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
        if maybe_skip_stale_unresolved_record(
            record,
            frame,
            updated_at=updated_at,
            reason="stale_open_unresolved",
            reference_dt=record.get("entry_dt"),
            required_bars=int(record.get("outcome_horizon_bars") or 24),
            stale_grace_bars=stale_grace_bars,
            timeframe=timeframe,
        ):
            return True
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
    shadow_path_raw = str(getattr(args, "journal_shadow_jsonl", "") or "")
    shadow_path = Path(shadow_path_raw) if shadow_path_raw else None
    shadow_records = read_journal(shadow_path) if shadow_path is not None else []
    shadow_seen = {record.get("signal_id") for record in shadow_records}
    fast_shadow_path_raw = str(getattr(args, "journal_fast_shadow_jsonl", "") or "")
    fast_shadow_path = Path(fast_shadow_path_raw) if fast_shadow_path_raw else None
    fast_shadow_records = read_journal(fast_shadow_path) if fast_shadow_path is not None else []
    fast_shadow_seen = {record.get("signal_id") for record in fast_shadow_records}
    fast_shadow_horizon = int(getattr(args, "journal_fast_shadow_outcome_horizon_bars", 0) or 0)
    execution_config = execution_config_from_args(args)
    allowed_pairs = parse_symbol_side_pairs(getattr(args, "journal_allowed_pairs", ""))
    blocked_pairs = journal_blocked_pair_refs(args)
    blocked_regime_cohorts = journal_blocked_regime_cohort_refs(args)
    blocked_confirmation_cohorts = journal_blocked_confirmation_cohort_refs(args)
    blocked_trend_alignment_cohorts = journal_blocked_trend_alignment_cohort_refs(args)
    shadow_retest_pairs = journal_shadow_retest_pair_refs(args)
    shadow_retest_max_new = int(getattr(args, "journal_shadow_retest_max_new", 0) or 0)
    risk_controls = journal_risk_controls(args)
    blocked_sides = set(risk_controls.get("blocked_sides") or [])
    respect_portfolio_risk = bool(getattr(args, "journal_respect_portfolio_risk", True))
    respect_global_active_cap = bool(getattr(args, "journal_respect_global_portfolio_active_cap", True))
    respect_portfolio_side_risk = bool(getattr(args, "journal_respect_portfolio_side_risk", True))
    max_active_per_pair = int(getattr(args, "journal_max_active_per_pair", 0) or 0)
    max_active_total = int(getattr(args, "journal_max_active_total", 0) or 0)
    active_cap_scope = str(getattr(args, "journal_active_cap_scope", "current_policy") or "current_policy")
    current_policy_version = str(execution_config.get("decision_policy_version") or DECISION_POLICY_VERSION)
    updated = 0
    migrated = 0
    blocked_candidates = 0
    blocked_regime_cohort_candidates = 0
    blocked_confirmation_cohort_candidates = 0
    blocked_trend_alignment_cohort_candidates = 0
    portfolio_risk_blocked_candidates = 0
    portfolio_drawdown_recovery_candidates = 0
    portfolio_side_blocked_candidates = 0
    portfolio_side_recovery_candidates = 0
    global_active_cap_blocked_candidates = 0
    global_active_added = 0
    active_total_cap_blocked_candidates = 0
    market_quality_blocked_candidates = 0
    market_quality_shadow_new_records = 0
    market_quality_fast_shadow_new_records = 0
    analog_robustness_fail_candidates = 0
    analog_robustness_fail_shadow_new_records = 0
    analog_robustness_fail_fast_shadow_new_records = 0
    formal_entry_gate_blocked_candidates = 0
    formal_entry_gate_shadow_new_records = 0
    formal_entry_gate_fast_shadow_new_records = 0
    shadow_retest_candidate_rows = 0
    shadow_retest_new_records = 0
    regime_confirmation_backfilled = 0
    shadow_updated = 0
    shadow_regime_confirmation_backfilled = 0
    fast_shadow_updated = 0
    fast_shadow_regime_confirmation_backfilled = 0
    new_shadow_records: list[dict[str, Any]] = []
    new_fast_shadow_records: list[dict[str, Any]] = []
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

    for record in shadow_records:
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
            shadow_updated += 1

    for record in fast_shadow_records:
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
            fast_shadow_updated += 1

    active_by_pair: dict[tuple[str, str], int] = {}
    active_total = 0
    for record in records:
        if record.get("status") not in {"pending_entry", "open"}:
            continue
        if not active_cap_record_allowed(
            record,
            scope=active_cap_scope,
            current_policy_version=current_policy_version,
        ):
            continue
        active_total += 1
        pair = (str(record.get("symbol", "")).upper(), str(record.get("side", "")).lower())
        active_by_pair[pair] = active_by_pair.get(pair, 0) + 1

    records_by_signal_id = {
        record.get("signal_id"): record
        for record in records
        if record.get("signal_id")
    }
    shadow_records_by_signal_id = {
        record.get("signal_id"): record
        for record in shadow_records
        if record.get("signal_id")
    }
    fast_shadow_records_by_signal_id = {
        record.get("signal_id"): record
        for record in fast_shadow_records
        if record.get("signal_id")
    }
    new_records = []

    def add_shadow_record(
        row: dict[str, Any],
        reason: str,
        reason_codes: list[str] | None = None,
        *,
        extra_fields: dict[str, Any] | None = None,
        force: bool = False,
    ) -> bool:
        if shadow_path is None:
            return False
        if not shadow_record_allowed(row, args, force=force):
            return False
        sid = signal_id(row)
        if sid in seen or sid in shadow_seen:
            return False
        shadow_seen.add(sid)
        record = shadow_record_from_row(
            row,
            updated_at=payload["updated_at"],
            horizon_bars=args.paper_outcome_horizon_bars,
            execution_config=execution_config,
            reason=reason,
            reason_codes=reason_codes,
            risk_controls=risk_controls,
        )
        if extra_fields:
            record.update(extra_fields)
        new_shadow_records.append(record)
        return True

    def add_fast_shadow_record(
        row: dict[str, Any],
        reason: str,
        reason_codes: list[str] | None = None,
        *,
        extra_fields: dict[str, Any] | None = None,
        force: bool = False,
    ) -> bool:
        if fast_shadow_path is None or fast_shadow_horizon <= 0:
            return False
        if not shadow_record_allowed(row, args, force=force):
            return False
        sid = signal_id(row)
        if sid in seen or sid in fast_shadow_seen:
            return False
        fast_shadow_seen.add(sid)
        record = shadow_record_from_row(
            row,
            updated_at=payload["updated_at"],
            horizon_bars=fast_shadow_horizon,
            execution_config=execution_config,
            reason=reason,
            reason_codes=reason_codes,
            risk_controls=risk_controls,
        )
        record["kind"] = "contract_latest_market_signal_fast_shadow_journal_v1"
        record["fast_shadow_journal"] = True
        record["shadow_fast_probe"] = True
        record["shadow_fast_probe_horizon_bars"] = fast_shadow_horizon
        record["promotion_eligible"] = False
        if extra_fields:
            record.update(extra_fields)
        new_fast_shadow_records.append(record)
        return True

    for row in payload["rows"]:
        market_quality_candidate = market_quality_blocked_candidate_row(row)
        if market_quality_candidate is not None:
            pair = (
                str(market_quality_candidate.get("symbol", "")).upper(),
                str(market_quality_candidate.get("signal")).lower(),
            )
            if allowed_pairs and pair not in allowed_pairs:
                continue
            market_quality_blocked_candidates += 1
            market_quality = market_quality_candidate.get("market_quality") or {}
            reason_codes = [
                "market_quality_blocked",
                *[str(reason) for reason in (market_quality.get("reason_codes") or [])],
            ]
            extra_fields = {
                "market_quality_block_shadow": True,
                "blocked_signal": True,
                "blocked_signal_reason": market_quality_candidate.get("blocked_signal_reason"),
                "promotion_eligible": False,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
            if add_shadow_record(
                market_quality_candidate,
                "market_quality_block",
                reason_codes,
                extra_fields=extra_fields,
                force=True,
            ):
                market_quality_shadow_new_records += 1
            if add_fast_shadow_record(
                market_quality_candidate,
                "market_quality_block",
                reason_codes,
                extra_fields=extra_fields,
                force=True,
            ):
                market_quality_fast_shadow_new_records += 1
            continue
        if row.get("signal") not in {"long", "short"} or not row.get("paper_plan"):
            continue
        sid = signal_id(row)
        record = records_by_signal_id.get(sid)
        if record is not None and apply_regime_confirmation_to_record(
            record,
            row,
            updated_at=payload["updated_at"],
        ):
            regime_confirmation_backfilled += 1
        shadow_record = shadow_records_by_signal_id.get(sid)
        if shadow_record is not None and apply_regime_confirmation_to_record(
            shadow_record,
            row,
            updated_at=payload["updated_at"],
        ):
            shadow_regime_confirmation_backfilled += 1
        fast_shadow_record = fast_shadow_records_by_signal_id.get(sid)
        if fast_shadow_record is not None and apply_regime_confirmation_to_record(
            fast_shadow_record,
            row,
            updated_at=payload["updated_at"],
        ):
            fast_shadow_regime_confirmation_backfilled += 1
        pair = (str(row.get("symbol", "")).upper(), str(row.get("signal")).lower())
        pair_ref = (str(getattr(args, "timeframe", "") or "").lower(), pair[0], pair[1])
        if allowed_pairs and pair not in allowed_pairs:
            continue
        if pair_ref in blocked_pairs:
            blocked_candidates += 1
            continue
        regime_ref = regime_cohort_ref_for_signal_row(
            row,
            default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
        )
        if regime_ref in blocked_regime_cohorts:
            blocked_regime_cohort_candidates += 1
            add_shadow_record(
                row,
                "regime_cohort_block",
                [
                    "regime_cohort_stop_candidate",
                    f"market_regime_id={regime_ref[2]}",
                ],
            )
            add_fast_shadow_record(
                row,
                "regime_cohort_block",
                [
                    "regime_cohort_stop_candidate",
                    f"market_regime_id={regime_ref[2]}",
                ],
            )
            continue
        confirmation_ref = confirmation_cohort_ref_for_signal_row(
            row,
            default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
        )
        if confirmation_ref in blocked_confirmation_cohorts:
            blocked_confirmation_cohort_candidates += 1
            add_shadow_record(
                row,
                "confirmation_cohort_block",
                [
                    "confirmation_cohort_stop_candidate",
                    f"confirmation_bucket={confirmation_ref[2]}",
                ],
            )
            add_fast_shadow_record(
                row,
                "confirmation_cohort_block",
                [
                    "confirmation_cohort_stop_candidate",
                    f"confirmation_bucket={confirmation_ref[2]}",
                ],
            )
            continue
        trend_alignment_ref = trend_alignment_cohort_ref_for_signal_row(
            row,
            default_timeframe=str(getattr(args, "timeframe", "") or "").lower(),
        )
        if trend_alignment_ref in blocked_trend_alignment_cohorts:
            blocked_trend_alignment_cohort_candidates += 1
            reason_codes = [
                "trend_alignment_risk_block",
                f"market_trend_state={trend_alignment_ref[2]}",
                f"trend_alignment_bucket={trend_alignment_ref[3]}",
                f"confirmation_bucket={trend_alignment_ref[4]}",
            ]
            add_shadow_record(row, "trend_alignment_cohort_block", reason_codes)
            add_fast_shadow_record(row, "trend_alignment_cohort_block", reason_codes)
            continue
        if pair_ref in shadow_retest_pairs:
            shadow_retest_candidate_rows += 1
            if shadow_retest_max_new <= 0 or shadow_retest_new_records < shadow_retest_max_new:
                if add_shadow_record(
                    row,
                    "fast_shadow_full_horizon_retest",
                    ["fast_shadow_retest_ready"],
                    extra_fields={
                        "shadow_retest": True,
                        "shadow_retest_source": str(getattr(args, "journal_shadow_retest_json", "") or ""),
                        "promotion_eligible": False,
                    },
                ):
                    shadow_retest_new_records += 1
            continue
        drawdown_recovery_probe = False
        if respect_portfolio_risk and risk_controls.get("block_new_focus"):
            if journal_portfolio_drawdown_recovery_probe_allowed(row, risk_controls, args):
                drawdown_recovery_probe = True
                portfolio_drawdown_recovery_candidates += 1
            else:
                portfolio_risk_blocked_candidates += 1
                add_shadow_record(
                    row,
                    "portfolio_risk_block",
                    list(risk_controls.get("reason_codes") or []),
                )
                add_fast_shadow_record(
                    row,
                    "portfolio_risk_block",
                    list(risk_controls.get("reason_codes") or []),
                )
                continue
        recovery_probe = False
        if respect_portfolio_side_risk and pair[1] in blocked_sides:
            if journal_side_recovery_probe_allowed(row, pair[1], risk_controls, args):
                recovery_probe = True
                portfolio_side_recovery_candidates += 1
            else:
                portfolio_side_blocked_candidates += 1
                add_shadow_record(
                    row,
                    "portfolio_side_block",
                    list(risk_controls.get("side_reason_codes") or []),
                )
                add_fast_shadow_record(
                    row,
                    "portfolio_side_block",
                    list(risk_controls.get("side_reason_codes") or []),
                )
                continue
        global_max_active = int(risk_controls.get("max_active") or 0)
        global_active = int(risk_controls.get("active") or 0)
        if respect_global_active_cap and global_max_active > 0 and global_active + global_active_added >= global_max_active:
            global_active_cap_blocked_candidates += 1
            add_shadow_record(row, "global_active_cap_block", [f"global_active>={global_max_active}"])
            add_fast_shadow_record(row, "global_active_cap_block", [f"global_active>={global_max_active}"])
            continue
        if max_active_total > 0 and active_total >= max_active_total:
            active_total_cap_blocked_candidates += 1
            add_shadow_record(row, "journal_active_total_cap_block", [f"journal_active_total>={max_active_total}"])
            add_fast_shadow_record(row, "journal_active_total_cap_block", [f"journal_active_total>={max_active_total}"])
            continue
        if max_active_per_pair > 0 and active_by_pair.get(pair, 0) >= max_active_per_pair:
            add_shadow_record(
                row,
                "journal_active_pair_cap_block",
                [f"journal_active_pair>={max_active_per_pair}"],
            )
            add_fast_shadow_record(
                row,
                "journal_active_pair_cap_block",
                [f"journal_active_pair>={max_active_per_pair}"],
            )
            continue
        analog = row.get("analog_evidence") or {}
        if analog_robustness_failed_candidate(row):
            analog_robustness_fail_candidates += 1
            reason_codes = analog_robustness_shadow_reason_codes(row)
            extra_fields = {
                "analog_robustness_shadow": True,
                "promotion_eligible": False,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
            if add_shadow_record(
                row,
                "analog_robustness_fail",
                reason_codes,
                extra_fields=extra_fields,
                force=True,
            ):
                analog_robustness_fail_shadow_new_records += 1
            if add_fast_shadow_record(
                row,
                "analog_robustness_fail",
                reason_codes,
                extra_fields=extra_fields,
                force=True,
            ):
                analog_robustness_fail_fast_shadow_new_records += 1
            continue
        formal_entry_reasons = formal_entry_gate_reason_codes(row, args)
        if formal_entry_reasons:
            formal_entry_gate_blocked_candidates += 1
            extra_fields = {
                "formal_entry_gate_block": True,
                "formal_entry_gate_mode": str(getattr(args, "journal_record_mode", "") or ""),
                "formal_entry_gate_reason_codes": formal_entry_reasons,
                "promotion_eligible": False,
                "paper_trading_authorized": False,
                "live_trading_authorized": False,
            }
            if add_shadow_record(
                row,
                "formal_entry_gate_block",
                formal_entry_reasons,
                extra_fields=extra_fields,
                force=bool(analog.get("supported")),
            ):
                formal_entry_gate_shadow_new_records += 1
            if add_fast_shadow_record(
                row,
                "formal_entry_gate_block",
                formal_entry_reasons,
                extra_fields=extra_fields,
                force=bool(analog.get("supported")),
            ):
                formal_entry_gate_fast_shadow_new_records += 1
            continue
        if sid in seen:
            continue
        seen.add(sid)
        record = journal_record_from_row(
            row,
            updated_at=payload["updated_at"],
            horizon_bars=args.paper_outcome_horizon_bars,
            execution_config=execution_config,
        )
        if recovery_probe:
            record["portfolio_side_recovery_probe"] = True
            record["portfolio_side_recovery_reason"] = "blocked_side_strong_analog_recovery"
            record["portfolio_side_recovery_from_status"] = risk_controls.get("status")
            record["portfolio_side_recovery_blocked_sides"] = sorted(blocked_sides)
        if drawdown_recovery_probe:
            record["portfolio_drawdown_recovery_probe"] = True
            record["portfolio_drawdown_recovery_reason"] = "portfolio_drawdown_strong_analog_recovery"
            record["portfolio_drawdown_recovery_from_status"] = risk_controls.get("status")
        new_records.append(record)
        active_by_pair[pair] = active_by_pair.get(pair, 0) + 1
        active_total += 1
        global_active_added += 1

    records.extend(new_records)
    shadow_records.extend(new_shadow_records)
    fast_shadow_records.extend(new_fast_shadow_records)
    if args.max_journal_records > 0 and len(records) > args.max_journal_records:
        records = records[-int(args.max_journal_records) :]
    max_shadow_records = int(getattr(args, "max_shadow_journal_records", 0) or 0)
    if max_shadow_records > 0 and len(shadow_records) > max_shadow_records:
        shadow_records = shadow_records[-max_shadow_records:]
    max_fast_shadow_records = int(getattr(args, "max_fast_shadow_journal_records", 0) or 0)
    if max_fast_shadow_records > 0 and len(fast_shadow_records) > max_fast_shadow_records:
        fast_shadow_records = fast_shadow_records[-max_fast_shadow_records:]
    write_journal(path, records)
    if shadow_path is not None:
        write_journal(shadow_path, shadow_records)
    if fast_shadow_path is not None:
        write_journal(fast_shadow_path, fast_shadow_records)
    completed = sum(1 for record in records if record.get("status") == "completed")
    skipped = sum(1 for record in records if record.get("status") == "skipped")
    active = sum(1 for record in records if record.get("status") in {"pending_entry", "open"})
    shadow_completed = sum(1 for record in shadow_records if record.get("status") == "completed")
    shadow_skipped = sum(1 for record in shadow_records if record.get("status") == "skipped")
    shadow_active = sum(1 for record in shadow_records if record.get("status") in {"pending_entry", "open"})
    fast_shadow_completed = sum(1 for record in fast_shadow_records if record.get("status") == "completed")
    fast_shadow_skipped = sum(1 for record in fast_shadow_records if record.get("status") == "skipped")
    fast_shadow_active = sum(
        1 for record in fast_shadow_records if record.get("status") in {"pending_entry", "open"}
    )
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
        "regime_confirmation_backfilled_records": regime_confirmation_backfilled,
        "migrated_legacy_records": migrated,
        "total_records": len(records),
        "open_records": active,
        "completed_records": completed,
        "skipped_records": skipped,
        "analog_supported_open_records": analog_supported_open,
        "shadow_enabled": shadow_path is not None,
        "shadow_path": str(shadow_path) if shadow_path is not None else "",
        "shadow_new_records": len(new_shadow_records),
        "shadow_updated_records": shadow_updated,
        "shadow_regime_confirmation_backfilled_records": shadow_regime_confirmation_backfilled,
        "shadow_total_records": len(shadow_records),
        "shadow_open_records": shadow_active,
        "shadow_completed_records": shadow_completed,
        "shadow_skipped_records": shadow_skipped,
        "shadow_record_mode": str(getattr(args, "journal_shadow_record_mode", "inherit") or "inherit"),
        "shadow_min_analog_samples": int(getattr(args, "journal_shadow_min_analog_samples", 20)),
        "shadow_min_expectancy_r": float(getattr(args, "journal_shadow_min_expectancy_r", 0.15)),
        "shadow_min_hit_rate": float(getattr(args, "journal_shadow_min_hit_rate", 0.30)),
        "shadow_min_profitable_rate": float(getattr(args, "journal_shadow_min_profitable_rate", 0.40)),
        "shadow_retest_json": str(getattr(args, "journal_shadow_retest_json", "")),
        "shadow_retest_pairs": sorted(
            f"{timeframe}:{symbol}:{side}" for timeframe, symbol, side in shadow_retest_pairs
        ),
        "shadow_retest_max_new": shadow_retest_max_new,
        "shadow_retest_candidate_rows": shadow_retest_candidate_rows,
        "shadow_retest_new_records": shadow_retest_new_records,
        "market_quality_blocked_candidate_rows": market_quality_blocked_candidates,
        "market_quality_shadow_new_records": market_quality_shadow_new_records,
        "fast_shadow_enabled": fast_shadow_path is not None and fast_shadow_horizon > 0,
        "fast_shadow_path": str(fast_shadow_path) if fast_shadow_path is not None else "",
        "fast_shadow_outcome_horizon_bars": fast_shadow_horizon,
        "fast_shadow_new_records": len(new_fast_shadow_records),
        "market_quality_fast_shadow_new_records": market_quality_fast_shadow_new_records,
        "analog_robustness_fail_candidate_rows": analog_robustness_fail_candidates,
        "analog_robustness_fail_shadow_new_records": analog_robustness_fail_shadow_new_records,
        "analog_robustness_fail_fast_shadow_new_records": (
            analog_robustness_fail_fast_shadow_new_records
        ),
        "formal_entry_gate_mode": str(getattr(args, "journal_record_mode", "all_signals") or "all_signals"),
        "formal_entry_gate_min_analog_samples": int(
            getattr(args, "journal_strong_min_analog_samples", 30)
        ),
        "formal_entry_gate_min_expectancy_r": float(
            getattr(args, "journal_strong_min_expectancy_r", 0.25)
        ),
        "formal_entry_gate_min_hit_rate": float(
            getattr(args, "journal_strong_min_hit_rate", 0.50)
        ),
        "formal_entry_gate_min_profitable_rate": float(
            getattr(args, "journal_strong_min_profitable_rate", 0.55)
        ),
        "formal_entry_gate_require_robustness": bool(
            getattr(args, "journal_strong_require_robustness", True)
        ),
        "formal_entry_gate_blocked_candidate_rows": formal_entry_gate_blocked_candidates,
        "formal_entry_gate_shadow_new_records": formal_entry_gate_shadow_new_records,
        "formal_entry_gate_fast_shadow_new_records": formal_entry_gate_fast_shadow_new_records,
        "fast_shadow_updated_records": fast_shadow_updated,
        "fast_shadow_regime_confirmation_backfilled_records": fast_shadow_regime_confirmation_backfilled,
        "fast_shadow_total_records": len(fast_shadow_records),
        "fast_shadow_open_records": fast_shadow_active,
        "fast_shadow_completed_records": fast_shadow_completed,
        "fast_shadow_skipped_records": fast_shadow_skipped,
        "record_mode": args.journal_record_mode,
        "journal_allowed_pairs": sorted(f"{symbol}:{side}" for symbol, side in allowed_pairs),
        "journal_blocked_pairs": sorted(f"{timeframe}:{symbol}:{side}" for timeframe, symbol, side in blocked_pairs),
        "journal_blocked_candidate_rows": blocked_candidates,
        "journal_blocked_regime_cohorts": sorted(
            f"{timeframe}:{side}:{regime_id}"
            for timeframe, side, regime_id in blocked_regime_cohorts
        ),
        "journal_blocked_regime_cohort_candidate_rows": blocked_regime_cohort_candidates,
        "journal_blocked_confirmation_cohorts": sorted(
            f"{timeframe}:{side}:{bucket}:{','.join(confirm_timeframes) or 'none'}:"
            f"{','.join(confirm_regime_ids) or 'none'}"
            for timeframe, side, bucket, confirm_timeframes, confirm_regime_ids in blocked_confirmation_cohorts
        ),
        "journal_blocked_confirmation_cohort_candidate_rows": blocked_confirmation_cohort_candidates,
        "journal_blocked_trend_alignment_cohorts": sorted(
            f"{timeframe}:{side}:{trend}:{alignment}:{confirmation}"
            for timeframe, side, trend, alignment, confirmation in blocked_trend_alignment_cohorts
        ),
        "journal_blocked_trend_alignment_cohort_candidate_rows": (
            blocked_trend_alignment_cohort_candidates
        ),
        "journal_risk_actions_json": str(getattr(args, "journal_risk_actions_json", "")),
        "journal_risk_scope": risk_controls.get("scope"),
        "journal_risk_source_key": risk_controls.get("source_key"),
        "journal_risk_decision_policy_version": risk_controls.get("decision_policy_version"),
        "journal_portfolio_risk_status": risk_controls.get("status"),
        "journal_portfolio_block_new_records": bool(
            respect_portfolio_risk and risk_controls.get("block_new_focus")
        ),
        "journal_portfolio_blocked_sides": sorted(blocked_sides),
        "journal_portfolio_risk_blocked_candidate_rows": portfolio_risk_blocked_candidates,
        "journal_portfolio_drawdown_recovery_candidate_rows": portfolio_drawdown_recovery_candidates,
        "journal_portfolio_side_blocked_candidate_rows": portfolio_side_blocked_candidates,
        "journal_portfolio_side_recovery_candidate_rows": portfolio_side_recovery_candidates,
        "journal_portfolio_reason_codes": risk_controls.get("reason_codes") or [],
        "journal_portfolio_side_reason_codes": risk_controls.get("side_reason_codes") or [],
        "journal_global_portfolio_max_active": int(risk_controls.get("max_active") or 0),
        "journal_global_portfolio_active": int(risk_controls.get("active") or 0),
        "journal_global_active_cap_blocked_candidate_rows": global_active_cap_blocked_candidates,
        "journal_max_active_per_pair": max_active_per_pair,
        "journal_max_active_total": max_active_total,
        "journal_active_cap_scope": active_cap_scope,
        "journal_active_cap_policy_version": current_policy_version,
        "journal_active_total_for_cap": active_total,
        "journal_active_total_cap_blocked_candidate_rows": active_total_cap_blocked_candidates,
        "execution_model": REALISTIC_EXECUTION_MODEL_VERSION,
        "paper_execution": execution_config,
    }


def annotate_paper_actionability(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.setdefault("summary", {})
    journal = payload.get("journal") or {}
    new_records = int(journal.get("new_records") or 0)
    paper_plan_found = bool(summary.get("paper_plan_found"))
    reason_codes: list[str] = []

    if new_records > 0:
        status = "recorded_new_paper"
        actionable_new = True
    elif not paper_plan_found:
        status = "no_paper_plan"
        actionable_new = False
    elif journal.get("journal_portfolio_block_new_records"):
        status = "blocked_by_portfolio_risk"
        actionable_new = False
        reason_codes.extend(str(reason) for reason in (journal.get("journal_portfolio_reason_codes") or []))
    elif int(journal.get("journal_portfolio_side_blocked_candidate_rows") or 0) > 0:
        status = "blocked_by_portfolio_side_risk"
        actionable_new = False
        reason_codes.extend(str(reason) for reason in (journal.get("journal_portfolio_side_reason_codes") or []))
    elif int(journal.get("journal_global_active_cap_blocked_candidate_rows") or 0) > 0:
        status = "blocked_by_global_active_cap"
        actionable_new = False
        max_active = int(journal.get("journal_global_portfolio_max_active") or 0)
        if max_active > 0:
            reason_codes.append(f"global_active>={max_active}")
    elif int(journal.get("journal_active_total_cap_blocked_candidate_rows") or 0) > 0:
        status = "blocked_by_journal_active_total_cap"
        actionable_new = False
        max_active = int(journal.get("journal_max_active_total") or 0)
        if max_active > 0:
            reason_codes.append(f"journal_active_total>={max_active}")
    elif int(journal.get("journal_blocked_candidate_rows") or 0) > 0:
        status = "blocked_pair"
        actionable_new = False
    elif int(journal.get("journal_blocked_trend_alignment_cohort_candidate_rows") or 0) > 0:
        status = "blocked_by_trend_alignment_cohort"
        actionable_new = False
    elif int(journal.get("journal_blocked_confirmation_cohort_candidate_rows") or 0) > 0:
        status = "blocked_by_confirmation_cohort"
        actionable_new = False
    elif int(journal.get("journal_blocked_regime_cohort_candidate_rows") or 0) > 0:
        status = "blocked_by_regime_cohort"
        actionable_new = False
    elif int(journal.get("analog_robustness_fail_candidate_rows") or 0) > 0:
        status = "shadow_only_analog_robustness_fail"
        actionable_new = False
    elif int(journal.get("market_quality_blocked_candidate_rows") or 0) > 0:
        status = "shadow_only_market_quality_block"
        actionable_new = False
    else:
        status = "not_new_already_recorded_or_filtered"
        actionable_new = False

    summary["paper_actionable_new"] = actionable_new
    summary["paper_actionability_status"] = status
    summary["paper_actionability_reason_codes"] = sorted(set(reason_codes))
    return payload


def run_screen(args: argparse.Namespace) -> dict[str, Any]:
    screen_updated_at = now_utc()
    if not str(getattr(args, "data_freshness_now", "") or ""):
        setattr(args, "_data_freshness_reference_utc", screen_updated_at)
    fallback = parse_symbols(args.symbols) or DEFAULT_SYMBOLS
    symbols = parse_symbols(args.symbols) or symbols_from_universe(
        args.universe_json,
        top_n=args.top_n,
        fallback=fallback,
    )
    regime_symbols = parse_symbols(getattr(args, "regime_symbols", ""))
    frame_symbols = tuple(dict.fromkeys([*symbols, *regime_symbols]))
    frames_by_symbol: dict[str, pd.DataFrame] = {}
    for symbol in frame_symbols:
        frames_by_symbol[symbol] = load_symbol_cache(
            Path(args.cache_dir),
            symbol,
            args.timeframe,
            lookback_bars=args.lookback_bars,
        )
    market_regime = build_market_regime_context(frames_by_symbol, args)
    confirmation_contexts = build_confirmation_regime_contexts(
        cache_dir=Path(args.cache_dir),
        args=args,
        regime_symbols=regime_symbols or symbols,
    )
    if confirmation_contexts:
        market_regime["confirmation_contexts"] = confirmation_contexts
        market_regime["confirmation_timeframes"] = [
            context.get("confirmation_timeframe") for context in confirmation_contexts
        ]
        market_regime["confirmation_mode"] = str(getattr(args, "regime_confirm_mode", "block_conflict"))
    rows = []
    for symbol in symbols:
        rows.append(classify_signal(frames_by_symbol[symbol], args, symbol=symbol, market_regime=market_regime))
    rows.sort(key=row_sort_key, reverse=True)
    signal_rows = [row for row in rows if row.get("signal") in {"long", "short"} and row.get("paper_plan")]
    analog_supported_rows = [row for row in signal_rows if (row.get("analog_evidence") or {}).get("supported")]
    regime_filtered_rows = [row for row in rows if (row.get("regime_filter") or {}).get("allowed") is False]
    data_stale_filtered_rows = [row for row in rows if row.get("status") == "data_stale"]
    market_quality_filtered_rows = [
        row
        for row in rows
        if (row.get("market_quality") or {}).get("allowed") is False
    ]
    payload = {
        "kind": "contract_latest_market_signal_v2_analog_journal",
        "updated_at": screen_updated_at,
        "cache_dir": args.cache_dir,
        "timeframe": args.timeframe,
        "universe_json": args.universe_json,
        "symbols": symbols,
        "market_regime": market_regime,
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
            "analog_min_robust_segments": int(getattr(args, "analog_min_robust_segments", 2)),
            "analog_robust_segment_min_samples": int(
                getattr(args, "analog_robust_segment_min_samples", 3)
            ),
            "min_analog_segment_expectancy_r": float(
                getattr(args, "min_analog_segment_expectancy_r", 0.0)
            ),
            "min_analog_segment_profitable_rate": float(
                getattr(args, "min_analog_segment_profitable_rate", 0.45)
            ),
            "paper_outcome_horizon_bars": int(args.paper_outcome_horizon_bars),
            "decision_policy_version": str(getattr(args, "decision_policy_version", DECISION_POLICY_VERSION)),
            "paper_execution": execution_config_from_args(args),
            "data_freshness_mode": str(getattr(args, "data_freshness_mode", "block")),
            "data_freshness_max_age_bars": float(getattr(args, "data_freshness_max_age_bars", 2.5)),
            "data_freshness_grace_minutes": float(getattr(args, "data_freshness_grace_minutes", 5.0)),
            "data_freshness_reference_dt": data_freshness_reference(args),
            "regime_filter_mode": str(getattr(args, "regime_filter_mode", "off")),
            "regime_symbols": [symbol.upper() for symbol in regime_symbols],
            "regime_confirm_timeframes": parse_timeframes(
                str(getattr(args, "regime_confirm_timeframes", "") or "")
            ),
            "regime_confirm_mode": str(getattr(args, "regime_confirm_mode", "block_conflict")),
            "regime_min_direction_votes": int(args.regime_min_direction_votes),
            "regime_vol_lookback_bars": int(args.regime_vol_lookback_bars),
            "regime_high_vol_percentile": float(args.regime_high_vol_percentile),
            "regime_block_high_vol": bool(args.regime_block_high_vol),
            "market_quality_mode": str(getattr(args, "market_quality_mode", "block")),
            "market_quality_min_atr_pct": float(getattr(args, "market_quality_min_atr_pct", 0.0015)),
            "market_quality_max_atr_pct": float(getattr(args, "market_quality_max_atr_pct", 0.08)),
            "market_quality_max_ema_gap": float(getattr(args, "market_quality_max_ema_gap", 0.15)),
            "market_quality_max_abs_ret_24h": float(getattr(args, "market_quality_max_abs_ret_24h", 0.20)),
            "market_quality_max_breakout_extension": float(
                getattr(args, "market_quality_max_breakout_extension", 0.35)
            ),
            "market_quality_min_volume_ratio": float(getattr(args, "market_quality_min_volume_ratio", 0.25)),
            "market_quality_volume_window": int(getattr(args, "market_quality_volume_window", 48)),
            "journal_allowed_pairs": sorted(
                f"{symbol}:{side}" for symbol, side in parse_symbol_side_pairs(args.journal_allowed_pairs)
            ),
            "journal_blocked_pairs_json": str(getattr(args, "journal_blocked_pairs_json", "")),
            "journal_risk_actions_json": str(getattr(args, "journal_risk_actions_json", "")),
            "journal_risk_scope": str(getattr(args, "journal_risk_scope", "current_policy")),
            "journal_active_cap_scope": str(getattr(args, "journal_active_cap_scope", "current_policy")),
            "journal_record_mode": str(getattr(args, "journal_record_mode", "all_signals")),
            "journal_strong_min_analog_samples": int(
                getattr(args, "journal_strong_min_analog_samples", 30)
            ),
            "journal_strong_min_expectancy_r": float(
                getattr(args, "journal_strong_min_expectancy_r", 0.25)
            ),
            "journal_strong_min_hit_rate": float(getattr(args, "journal_strong_min_hit_rate", 0.50)),
            "journal_strong_min_profitable_rate": float(
                getattr(args, "journal_strong_min_profitable_rate", 0.55)
            ),
            "journal_strong_require_robustness": bool(
                getattr(args, "journal_strong_require_robustness", True)
            ),
            "journal_shadow_jsonl": str(getattr(args, "journal_shadow_jsonl", "")),
            "journal_shadow_record_mode": str(getattr(args, "journal_shadow_record_mode", "inherit")),
            "journal_shadow_min_analog_samples": int(getattr(args, "journal_shadow_min_analog_samples", 20)),
            "journal_shadow_min_expectancy_r": float(getattr(args, "journal_shadow_min_expectancy_r", 0.15)),
            "journal_shadow_min_hit_rate": float(getattr(args, "journal_shadow_min_hit_rate", 0.30)),
            "journal_shadow_min_profitable_rate": float(getattr(args, "journal_shadow_min_profitable_rate", 0.40)),
            "journal_shadow_retest_json": str(getattr(args, "journal_shadow_retest_json", "")),
            "journal_shadow_retest_max_new": int(getattr(args, "journal_shadow_retest_max_new", 0) or 0),
            "journal_fast_shadow_jsonl": str(getattr(args, "journal_fast_shadow_jsonl", "")),
            "journal_fast_shadow_outcome_horizon_bars": int(
                getattr(args, "journal_fast_shadow_outcome_horizon_bars", 0) or 0
            ),
            "journal_respect_portfolio_risk": bool(getattr(args, "journal_respect_portfolio_risk", True)),
            "journal_respect_global_portfolio_active_cap": bool(
                getattr(args, "journal_respect_global_portfolio_active_cap", True)
            ),
            "journal_allow_portfolio_drawdown_recovery_probes": bool(
                getattr(args, "journal_allow_portfolio_drawdown_recovery_probes", True)
            ),
            "journal_portfolio_recovery_max_active": int(getattr(args, "journal_portfolio_recovery_max_active", 12)),
            "journal_portfolio_recovery_max_active_excess": int(
                getattr(args, "journal_portfolio_recovery_max_active_excess", 0)
            ),
            "journal_portfolio_recovery_min_analog_samples": int(
                getattr(args, "journal_portfolio_recovery_min_analog_samples", 50)
            ),
            "journal_portfolio_recovery_min_hit_rate": float(
                getattr(args, "journal_portfolio_recovery_min_hit_rate", 0.55)
            ),
            "journal_portfolio_recovery_min_profitable_rate": float(
                getattr(args, "journal_portfolio_recovery_min_profitable_rate", 0.55)
            ),
            "journal_portfolio_recovery_min_expectancy_r": float(
                getattr(args, "journal_portfolio_recovery_min_expectancy_r", 0.35)
            ),
            "journal_respect_portfolio_side_risk": bool(
                getattr(args, "journal_respect_portfolio_side_risk", True)
            ),
            "journal_allow_side_recovery_probes": bool(getattr(args, "journal_allow_side_recovery_probes", True)),
            "journal_side_recovery_max_segment_active": int(
                getattr(args, "journal_side_recovery_max_segment_active", 0)
            ),
            "journal_side_recovery_min_analog_samples": int(
                getattr(args, "journal_side_recovery_min_analog_samples", 50)
            ),
            "journal_side_recovery_min_hit_rate": float(getattr(args, "journal_side_recovery_min_hit_rate", 0.55)),
            "journal_side_recovery_min_profitable_rate": float(
                getattr(args, "journal_side_recovery_min_profitable_rate", 0.55)
            ),
            "journal_side_recovery_min_expectancy_r": float(
                getattr(args, "journal_side_recovery_min_expectancy_r", 0.35)
            ),
            "journal_max_active_per_pair": int(args.journal_max_active_per_pair),
            "journal_max_active_total": int(getattr(args, "journal_max_active_total", 0) or 0),
        },
        "summary": {
            "rows": len(rows),
            "signal_count": len(signal_rows),
            "regime_filtered_count": len(regime_filtered_rows),
            "data_stale_filtered_count": len(data_stale_filtered_rows),
            "market_quality_filtered_count": len(market_quality_filtered_rows),
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
    annotate_paper_actionability(payload)
    return payload


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_marker(payload: dict[str, Any], marker_path: Path, no_marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    no_marker_path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    actionability = str(summary.get("paper_actionability_status") or "unknown")
    actionability_reasons = ",".join(str(reason) for reason in (summary.get("paper_actionability_reason_codes") or []))
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
            f"paper_actionable_new={bool(summary.get('paper_actionable_new'))} "
            f"paper_actionability_status={actionability} "
            f"paper_actionability_reasons={actionability_reasons or 'none'} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if no_marker_path.exists():
            no_marker_path.unlink()
    else:
        no_marker_path.write_text(
            "NO_CONTRACT_MARKET_PAPER_PLAN "
            f"{payload['updated_at']} rows={payload['summary']['rows']} "
            f"paper_actionable_new={bool(summary.get('paper_actionable_new'))} "
            f"paper_actionability_status={actionability} "
            f"paper_actionability_reasons={actionability_reasons or 'none'} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if marker_path.exists():
            marker_path.unlink()


def write_analog_marker(payload: dict[str, Any], marker_path: Path, no_marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    no_marker_path.parent.mkdir(parents=True, exist_ok=True)
    summary = payload.get("summary") or {}
    actionability = str(summary.get("paper_actionability_status") or "unknown")
    actionability_reasons = ",".join(str(reason) for reason in (summary.get("paper_actionability_reason_codes") or []))
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
            f"paper_actionable_new={bool(summary.get('paper_actionable_new'))} "
            f"paper_actionability_status={actionability} "
            f"paper_actionability_reasons={actionability_reasons or 'none'} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if no_marker_path.exists():
            no_marker_path.unlink()
    else:
        no_marker_path.write_text(
            "NO_CONTRACT_MARKET_ANALOG_PAPER_PLAN "
            f"{payload['updated_at']} signals={payload['summary']['signal_count']} "
            f"paper_actionable_new={bool(summary.get('paper_actionable_new'))} "
            f"paper_actionability_status={actionability} "
            f"paper_actionability_reasons={actionability_reasons or 'none'} "
            "paper_trading_authorized=False live_trading_authorized=False\n"
        )
        if marker_path.exists():
            marker_path.unlink()


def format_markdown(payload: dict[str, Any]) -> str:
    market_regime = payload.get("market_regime") or {}
    confirmation = market_regime.get("confirmation_contexts") or []
    lines = [
        "# Contract Latest Market Signal",
        "",
        f"- updated_at: `{payload['updated_at']}`",
        f"- timeframe: `{payload['timeframe']}`",
        f"- market_regime: `{market_regime.get('regime_id')}`",
        f"- market_regime_confirmations: `{len(confirmation)}`",
        f"- market_direction_score: `{market_regime.get('direction_score')}`",
        f"- data_stale_filtered_count: `{payload['summary'].get('data_stale_filtered_count')}`",
        f"- regime_filtered_count: `{payload['summary'].get('regime_filtered_count')}`",
        f"- market_quality_filtered_count: `{payload['summary'].get('market_quality_filtered_count')}`",
        f"- signal_count: `{payload['summary']['signal_count']}`",
        f"- analog_supported_plan_count: `{payload['summary']['analog_supported_plan_count']}`",
        f"- paper_plan_found: `{payload['summary']['paper_plan_found']}`",
        f"- paper_actionable_new: `{payload['summary'].get('paper_actionable_new')}`",
        f"- paper_actionability_status: `{payload['summary'].get('paper_actionability_status')}`",
        f"- paper_actionability_reasons: "
        f"`{','.join(payload['summary'].get('paper_actionability_reason_codes') or [])}`",
        f"- journal_new_records: `{(payload.get('journal') or {}).get('new_records')}`",
        f"- journal_regime_cohort_blocked: "
        f"`{(payload.get('journal') or {}).get('journal_blocked_regime_cohort_candidate_rows')}`",
        f"- journal_trend_alignment_blocked: "
        f"`{(payload.get('journal') or {}).get('journal_blocked_trend_alignment_cohort_candidate_rows')}`",
        f"- journal_market_quality_blocked: "
        f"`{(payload.get('journal') or {}).get('market_quality_blocked_candidate_rows')}`",
        f"- journal_analog_robustness_fail_shadow: "
        f"`{(payload.get('journal') or {}).get('analog_robustness_fail_candidate_rows')}/"
        f"{(payload.get('journal') or {}).get('analog_robustness_fail_shadow_new_records')}/"
        f"{(payload.get('journal') or {}).get('analog_robustness_fail_fast_shadow_new_records')}`",
        f"- journal_formal_entry_gate: "
        f"`{(payload.get('journal') or {}).get('formal_entry_gate_mode')}/"
        f"{(payload.get('journal') or {}).get('formal_entry_gate_blocked_candidate_rows')}/"
        f"{(payload.get('journal') or {}).get('formal_entry_gate_shadow_new_records')}/"
        f"{(payload.get('journal') or {}).get('formal_entry_gate_fast_shadow_new_records')}`",
        f"- journal_shadow_mode: `{(payload.get('journal') or {}).get('shadow_record_mode')}`",
        f"- journal_shadow_new/active/completed: "
        f"`{(payload.get('journal') or {}).get('shadow_new_records')}/"
        f"{(payload.get('journal') or {}).get('shadow_open_records')}/"
        f"{(payload.get('journal') or {}).get('shadow_completed_records')}`",
        f"- journal_portfolio_risk: `{(payload.get('journal') or {}).get('journal_portfolio_risk_status')}`",
        f"- journal_portfolio_blocked_sides: "
        f"`{','.join((payload.get('journal') or {}).get('journal_portfolio_blocked_sides') or [])}`",
        "",
        "| rank | symbol | signal | close | regime | quality | analog | hit | exp_r | entry | stop | take_profit | rsi | ret_24h |",
        "| ---: | --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(payload["top"], start=1):
        plan = row.get("paper_plan") or {}
        metrics = row.get("metrics") or {}
        analog = row.get("analog_evidence") or {}
        regime_filter = row.get("regime_filter") or {}
        market_quality = row.get("market_quality") or {}
        signal = row.get("signal")
        if signal == "none" and row.get("raw_signal"):
            signal = f"blocked:{row.get('raw_signal')}"
        lines.append(
            f"| {idx} | {row.get('symbol')} | {signal} | {row.get('close', 0.0):.8f} | "
            f"{regime_filter.get('reason')} | "
            f"{market_quality.get('reason')} | "
            f"{analog.get('reason')} | {safe_float(analog.get('hit_rate')):.2f} | "
            f"{safe_float(analog.get('expectancy_r')):.2f} | "
            f"{plan.get('entry_price', 0.0):.8f} | {plan.get('stop_loss', 0.0):.8f} | "
            f"{plan.get('take_profit', 0.0):.8f} | {metrics.get('rsi', 0.0):.2f} | {metrics.get('ret_24h', 0.0):.4f} |"
        )
    lines.extend(["", "Paper plan only. No order, paper trading, or live trading is authorized."])
    return "\n".join(lines) + "\n"


def format_text(payload: dict[str, Any]) -> str:
    market_regime = payload.get("market_regime") or {}
    confirmation = market_regime.get("confirmation_contexts") or []
    lines = [
        f"updated_at={payload['updated_at']}",
        f"timeframe={payload['timeframe']}",
        f"market_regime={market_regime.get('regime_id')} direction_score={market_regime.get('direction_score')} "
        f"vol={market_regime.get('vol_state')} sources={','.join(market_regime.get('source_symbols') or [])}",
        "market_regime_confirmation "
        f"mode={market_regime.get('confirmation_mode')} "
        f"timeframes={','.join(str(item.get('confirmation_timeframe') or item.get('timeframe')) for item in confirmation)} "
        f"regimes={','.join(str(item.get('regime_id')) for item in confirmation)}",
        f"signal_count={payload['summary']['signal_count']}",
        f"regime_filtered_count={payload['summary'].get('regime_filtered_count')}",
        f"data_stale_filtered_count={payload['summary'].get('data_stale_filtered_count')}",
        f"market_quality_filtered_count={payload['summary'].get('market_quality_filtered_count')}",
        f"analog_supported_plan_count={payload['summary']['analog_supported_plan_count']}",
        f"paper_plan_found={payload['summary']['paper_plan_found']}",
        f"paper_actionable_new={payload['summary'].get('paper_actionable_new')}",
        f"paper_actionability_status={payload['summary'].get('paper_actionability_status')}",
        "paper_actionability_reason_codes="
        f"{','.join(payload['summary'].get('paper_actionability_reason_codes') or [])}",
        f"journal_new_records={(payload.get('journal') or {}).get('new_records')}",
        f"journal_updated_records={(payload.get('journal') or {}).get('updated_records')}",
        f"journal_migrated_legacy_records={(payload.get('journal') or {}).get('migrated_legacy_records')}",
        f"journal_open_records={(payload.get('journal') or {}).get('open_records')}",
        "journal_risk "
        f"scope={(payload.get('journal') or {}).get('journal_risk_scope')} "
        f"source={(payload.get('journal') or {}).get('journal_risk_source_key')} "
        f"policy={(payload.get('journal') or {}).get('journal_risk_decision_policy_version')}",
        f"journal_max_active_total={(payload.get('journal') or {}).get('journal_max_active_total')}",
        "journal_active_cap "
        f"scope={(payload.get('journal') or {}).get('journal_active_cap_scope')} "
        f"policy={(payload.get('journal') or {}).get('journal_active_cap_policy_version')} "
        f"active_for_cap={(payload.get('journal') or {}).get('journal_active_total_for_cap')}",
        "journal_active_total_cap_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_active_total_cap_blocked_candidate_rows')}",
        "journal_global_active_cap_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_global_active_cap_blocked_candidate_rows')}",
        "journal_confirmation_cohort_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_blocked_confirmation_cohort_candidate_rows')}",
        "journal_regime_cohort_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_blocked_regime_cohort_candidate_rows')}",
        "journal_trend_alignment_cohort_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_blocked_trend_alignment_cohort_candidate_rows')}",
        "journal_market_quality_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('market_quality_blocked_candidate_rows')}",
        "journal_market_quality_shadow_new_records="
        f"{(payload.get('journal') or {}).get('market_quality_shadow_new_records')}",
        "journal_market_quality_fast_shadow_new_records="
        f"{(payload.get('journal') or {}).get('market_quality_fast_shadow_new_records')}",
        "journal_analog_robustness_fail "
        f"candidates={(payload.get('journal') or {}).get('analog_robustness_fail_candidate_rows')} "
        f"shadow_new={(payload.get('journal') or {}).get('analog_robustness_fail_shadow_new_records')} "
        "fast_shadow_new="
        f"{(payload.get('journal') or {}).get('analog_robustness_fail_fast_shadow_new_records')}",
        "journal_formal_entry_gate "
        f"mode={(payload.get('journal') or {}).get('formal_entry_gate_mode')} "
        f"min_samples={(payload.get('journal') or {}).get('formal_entry_gate_min_analog_samples')} "
        f"min_expectancy={(payload.get('journal') or {}).get('formal_entry_gate_min_expectancy_r')} "
        f"min_hit={(payload.get('journal') or {}).get('formal_entry_gate_min_hit_rate')} "
        f"min_profitable={(payload.get('journal') or {}).get('formal_entry_gate_min_profitable_rate')} "
        f"require_robustness={(payload.get('journal') or {}).get('formal_entry_gate_require_robustness')} "
        f"blocked={(payload.get('journal') or {}).get('formal_entry_gate_blocked_candidate_rows')} "
        f"shadow_new={(payload.get('journal') or {}).get('formal_entry_gate_shadow_new_records')} "
        f"fast_shadow_new={(payload.get('journal') or {}).get('formal_entry_gate_fast_shadow_new_records')}",
        "journal_portfolio_risk_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_portfolio_risk_blocked_candidate_rows')}",
        "journal_portfolio_drawdown_recovery_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_portfolio_drawdown_recovery_candidate_rows')}",
        "journal_portfolio_side_blocked_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_portfolio_side_blocked_candidate_rows')}",
        "journal_portfolio_side_recovery_candidate_rows="
        f"{(payload.get('journal') or {}).get('journal_portfolio_side_recovery_candidate_rows')}",
        "journal_portfolio_blocked_sides="
        f"{','.join((payload.get('journal') or {}).get('journal_portfolio_blocked_sides') or [])}",
        "journal_shadow "
        f"enabled={(payload.get('journal') or {}).get('shadow_enabled')} "
        f"mode={(payload.get('journal') or {}).get('shadow_record_mode')} "
        f"new={(payload.get('journal') or {}).get('shadow_new_records')} "
        f"updated={(payload.get('journal') or {}).get('shadow_updated_records')} "
        f"active={(payload.get('journal') or {}).get('shadow_open_records')} "
        f"completed={(payload.get('journal') or {}).get('shadow_completed_records')} "
        f"path={(payload.get('journal') or {}).get('shadow_path')}",
        "journal_shadow_retest "
        f"pairs={len((payload.get('journal') or {}).get('shadow_retest_pairs') or [])} "
        f"candidates={(payload.get('journal') or {}).get('shadow_retest_candidate_rows')} "
        f"new={(payload.get('journal') or {}).get('shadow_retest_new_records')} "
        f"max_new={(payload.get('journal') or {}).get('shadow_retest_max_new')} "
        f"json={(payload.get('journal') or {}).get('shadow_retest_json')}",
        "journal_fast_shadow "
        f"enabled={(payload.get('journal') or {}).get('fast_shadow_enabled')} "
        f"horizon={(payload.get('journal') or {}).get('fast_shadow_outcome_horizon_bars')} "
        f"new={(payload.get('journal') or {}).get('fast_shadow_new_records')} "
        f"updated={(payload.get('journal') or {}).get('fast_shadow_updated_records')} "
        f"active={(payload.get('journal') or {}).get('fast_shadow_open_records')} "
        f"completed={(payload.get('journal') or {}).get('fast_shadow_completed_records')} "
        f"path={(payload.get('journal') or {}).get('fast_shadow_path')}",
        "safety=paper_authorized:False live:False",
    ]
    if payload["top"]:
        best = payload["top"][0]
        plan = best.get("paper_plan") or {}
        analog = best.get("analog_evidence") or {}
        regime_filter = best.get("regime_filter") or {}
        market_quality = best.get("market_quality") or {}
        signal = best.get("signal")
        if signal == "none" and best.get("raw_signal"):
            signal = f"blocked:{best.get('raw_signal')}"
        lines.append(
            "best "
            f"symbol={best.get('symbol')} signal={signal} reason={best.get('reason')} "
            f"regime={regime_filter.get('reason')} "
            f"quality={market_quality.get('reason')} "
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
    parser.add_argument("--analog-min-robust-segments", type=int, default=2)
    parser.add_argument("--analog-robust-segment-min-samples", type=int, default=3)
    parser.add_argument("--min-analog-segment-expectancy-r", type=float, default=0.0)
    parser.add_argument("--min-analog-segment-profitable-rate", type=float, default=0.45)
    parser.add_argument("--paper-outcome-horizon-bars", type=int, default=24)
    parser.add_argument("--decision-policy-version", default=DECISION_POLICY_VERSION)
    parser.add_argument("--paper-fee-bps", type=float, default=5.0)
    parser.add_argument("--paper-slippage-bps", type=float, default=2.0)
    parser.add_argument("--paper-entry-latency-bars", type=int, default=1)
    parser.add_argument("--paper-max-entry-drift-bps", type=float, default=80.0)
    parser.add_argument("--paper-funding-bps-per-8h", type=float, default=1.0)
    parser.add_argument("--paper-partial-fill-frac", type=float, default=1.0)
    parser.add_argument("--paper-min-fill-frac", type=float, default=1.0)
    parser.add_argument(
        "--paper-stale-grace-bars",
        type=int,
        default=4,
        help="Skip unresolved paper records after entry/horizon plus this many bars if data can no longer settle them.",
    )
    parser.add_argument(
        "--data-freshness-mode",
        choices=("off", "annotate", "block"),
        default="block",
        help="Block current directional paper plans when latest cached candle is too old.",
    )
    parser.add_argument("--data-freshness-max-age-bars", type=float, default=2.5)
    parser.add_argument("--data-freshness-grace-minutes", type=float, default=5.0)
    parser.add_argument(
        "--data-freshness-now",
        default="",
        help="Optional UTC reference timestamp for deterministic freshness checks.",
    )
    parser.add_argument(
        "--regime-filter-mode",
        choices=("off", "annotate", "block_conflict", "trend_only"),
        default="block_conflict",
        help="Use broad BTC/ETH market regime before recording a paper signal.",
    )
    parser.add_argument(
        "--regime-symbols",
        default="BTCUSDT,ETHUSDT",
        help="Comma list of market symbols used to infer the broad regime. Falls back to screened symbols if missing.",
    )
    parser.add_argument(
        "--regime-confirm-timeframes",
        default="",
        help="Comma list of higher timeframes used to confirm broad regime before recording a signal.",
    )
    parser.add_argument(
        "--regime-confirm-mode",
        choices=("off", "annotate", "block_conflict", "trend_only"),
        default="block_conflict",
        help="How confirmation timeframes gate a signal after the primary regime filter allows it.",
    )
    parser.add_argument("--regime-min-direction-votes", type=int, default=2)
    parser.add_argument("--regime-vol-lookback-bars", type=int, default=1000)
    parser.add_argument("--regime-high-vol-percentile", type=float, default=0.85)
    parser.add_argument("--regime-block-high-vol", action="store_true")
    parser.add_argument(
        "--market-quality-mode",
        choices=("off", "annotate", "block"),
        default="block",
        help="Gate signals with immediate market-quality checks before writing paper journal records.",
    )
    parser.add_argument("--market-quality-min-atr-pct", type=float, default=0.0015)
    parser.add_argument("--market-quality-max-atr-pct", type=float, default=0.08)
    parser.add_argument("--market-quality-max-ema-gap", type=float, default=0.15)
    parser.add_argument("--market-quality-max-abs-ret-24h", type=float, default=0.20)
    parser.add_argument("--market-quality-max-breakout-extension", type=float, default=0.35)
    parser.add_argument("--market-quality-min-volume-ratio", type=float, default=0.25)
    parser.add_argument("--market-quality-volume-window", type=int, default=48)
    parser.add_argument(
        "--paper-migrate-legacy-records",
        choices=("off", "active", "all"),
        default="all",
    )
    parser.add_argument("--journal-jsonl", default="state/contract_latest_market_signal_journal.jsonl")
    parser.add_argument(
        "--journal-shadow-jsonl",
        default="",
        help="Optional separate shadow journal for candidates blocked by risk caps; never counted as active risk.",
    )
    parser.add_argument(
        "--journal-shadow-record-mode",
        choices=("inherit", "all_signals", "analog_supported", "positive_expectancy", "off"),
        default="inherit",
    )
    parser.add_argument("--journal-shadow-min-analog-samples", type=int, default=20)
    parser.add_argument("--journal-shadow-min-expectancy-r", type=float, default=0.15)
    parser.add_argument("--journal-shadow-min-hit-rate", type=float, default=0.30)
    parser.add_argument("--journal-shadow-min-profitable-rate", type=float, default=0.40)
    parser.add_argument(
        "--journal-shadow-retest-json",
        default="",
        help="Optional actions/retest JSON whose fast-shadow retest candidates are shadow-only full horizon retests.",
    )
    parser.add_argument(
        "--journal-shadow-retest-max-new",
        type=int,
        default=2,
        help="Maximum full-horizon shadow retest records to add per run; 0 means unlimited.",
    )
    parser.add_argument(
        "--journal-fast-shadow-jsonl",
        default="",
        help="Optional fast horizon shadow journal for research feedback; never promotion eligible.",
    )
    parser.add_argument(
        "--journal-fast-shadow-outcome-horizon-bars",
        type=int,
        default=0,
        help="If positive, write blocked shadow candidates to a shorter outcome horizon journal.",
    )
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
        "--journal-risk-actions-json",
        default="artifacts/v9/contract_lab/contract_paper_strategy_actions_latest.json",
        help="Optional actions JSON with portfolio_risk and blocked_sides used to stop new paper journal records.",
    )
    parser.add_argument(
        "--journal-risk-scope",
        choices=("current_policy", "global"),
        default="current_policy",
        help="Which portfolio risk object to use from the actions JSON for new journal records.",
    )
    parser.add_argument("--journal-respect-portfolio-risk", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--journal-respect-global-portfolio-active-cap", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--journal-allow-portfolio-drawdown-recovery-probes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--journal-portfolio-recovery-max-active", type=int, default=12)
    parser.add_argument("--journal-portfolio-recovery-max-active-excess", type=int, default=0)
    parser.add_argument("--journal-portfolio-recovery-min-analog-samples", type=int, default=50)
    parser.add_argument("--journal-portfolio-recovery-min-hit-rate", type=float, default=0.55)
    parser.add_argument("--journal-portfolio-recovery-min-profitable-rate", type=float, default=0.55)
    parser.add_argument("--journal-portfolio-recovery-min-expectancy-r", type=float, default=0.35)
    parser.add_argument("--journal-respect-portfolio-side-risk", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--journal-allow-side-recovery-probes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--journal-side-recovery-max-segment-active", type=int, default=0)
    parser.add_argument("--journal-side-recovery-min-analog-samples", type=int, default=50)
    parser.add_argument("--journal-side-recovery-min-hit-rate", type=float, default=0.55)
    parser.add_argument("--journal-side-recovery-min-profitable-rate", type=float, default=0.55)
    parser.add_argument("--journal-side-recovery-min-expectancy-r", type=float, default=0.35)
    parser.add_argument(
        "--journal-max-active-per-pair",
        type=int,
        default=0,
        help="If positive, do not add a new paper record when SYMBOL:SIDE already has this many active records.",
    )
    parser.add_argument(
        "--journal-max-active-total",
        type=int,
        default=12,
        help="If positive, do not add a new paper record when this journal already has this many active records.",
    )
    parser.add_argument(
        "--journal-active-cap-scope",
        choices=("current_policy", "all"),
        default="current_policy",
        help="Which existing active journal records count toward journal active caps.",
    )
    parser.add_argument(
        "--journal-record-mode",
        choices=("all_signals", "analog_supported", "strong_analog", "off"),
        default="all_signals",
    )
    parser.add_argument("--journal-strong-min-analog-samples", type=int, default=30)
    parser.add_argument("--journal-strong-min-expectancy-r", type=float, default=0.25)
    parser.add_argument("--journal-strong-min-hit-rate", type=float, default=0.50)
    parser.add_argument("--journal-strong-min-profitable-rate", type=float, default=0.55)
    parser.add_argument("--journal-strong-require-robustness", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-journal-records", type=int, default=20000)
    parser.add_argument("--max-shadow-journal-records", type=int, default=20000)
    parser.add_argument("--max-fast-shadow-journal-records", type=int, default=20000)
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
