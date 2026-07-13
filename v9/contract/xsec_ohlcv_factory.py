from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import numpy as np

from .metrics import max_drawdown
from .report import write_json
from .simulator import utc_ts
from .xsec_momentum import SYMBOLS, load_close_matrix, sharpe


ROW_CACHE_VERSION = "selection_validation_v13_validation_recent_period_gate"
ACTIVE_EXPOSURE_THRESHOLD = 0.01
SELECTION_MIN_ACTIVE_REBALANCES = 12
SELECTION_MIN_TIME_IN_MARKET_FRAC = 0.05
VALIDATION_MIN_ACTIVE_REBALANCES = 4
VALIDATION_MIN_TIME_IN_MARKET_FRAC = 0.03
ACCEPTANCE_MIN_VALIDATION_ACTIVE_REBALANCES = 50
DATA_SNAPSHOT_KIND = "xsec_ohlcv_data_snapshot_v1"


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
    drawdown_stop: float = 0.0
    cooldown_h: int = 0
    market_confirm_h: int = 0
    market_drawdown_limit: float = 0.0
    portfolio_mode: str = "long_only"
    hedge_ratio: float = 0.0
    downtrend_hedge_ratio: float = 0.0


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
    drawdown_stops: tuple[float, ...] = (0.0,)
    cooldowns_h: tuple[int, ...] = (0,)
    market_confirm_hs: tuple[int, ...] = (0,)
    market_drawdown_limits: tuple[float, ...] = (0.0,)
    portfolio_modes: tuple[str, ...] = ("long_only",)
    hedge_ratios: tuple[float, ...] = (0.0,)
    downtrend_hedge_ratios: tuple[float, ...] = (0.0,)
    costs_bps: tuple[float, ...] = (20.0, 40.0)
    stress_costs_bps: tuple[float, ...] = ()
    validate_all_rows: bool = False
    selection_min_active_rebalances: int = SELECTION_MIN_ACTIVE_REBALANCES
    selection_min_time_in_market_frac: float = SELECTION_MIN_TIME_IN_MARKET_FRAC
    selection_max_flat_streak_h: int = 0
    validation_min_active_rebalances: int = VALIDATION_MIN_ACTIVE_REBALANCES
    validation_min_time_in_market_frac: float = VALIDATION_MIN_TIME_IN_MARKET_FRAC
    validation_max_flat_streak_h: int = 0
    accepted_min_validation_active_rebalances: int = ACCEPTANCE_MIN_VALIDATION_ACTIVE_REBALANCES
    selection_min_2022_return: float | None = None
    validation_min_2024h1_periods: int = 0
    plateau_center_config: dict[str, Any] | None = None
    plateau_validation_sharpe_min: float = 1.0
    plateau_neighbor_pass_fraction_min: float = 0.70
    plateau_center_max_ratio: float = 1.30
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    data_snapshot: str = ""
    bootstrap_iterations: int = 500
    prior_trials: int = 0
    explicit_configs: tuple[OhlcvConfig, ...] = ()
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
    data_snapshot: str = "",
) -> RunConfig:
    base = {
        "cache_dir": cache_dir,
        "data_snapshot": data_snapshot,
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
    if preset == "evergreen_fast":
        return RunConfig(
            lookbacks_h=(72, 120, 168),
            skips_h=(0,),
            rebalances_h=(8, 12, 24),
            ks=(2, 3),
            score_modes=("mom", "risk_adj_mom", "vol_breakout"),
            market_filters_h=(0, 168, 336),
            vol_targets_ann=(0.12, 0.15, 0.18),
            selection_min_time_in_market_frac=0.60,
            selection_max_flat_streak_h=45 * 24,
            validation_min_time_in_market_frac=0.30,
            validation_max_flat_streak_h=45 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "evergreen_guarded":
        return RunConfig(
            lookbacks_h=(72, 120),
            skips_h=(0,),
            rebalances_h=(8, 12, 24),
            ks=(2, 3),
            score_modes=("risk_adj_mom", "vol_breakout"),
            market_filters_h=(0, 168),
            vol_targets_ann=(0.08, 0.10, 0.12),
            drawdown_stops=(0.05, 0.10),
            cooldowns_h=(72, 168),
            selection_min_time_in_market_frac=0.45,
            selection_max_flat_streak_h=60 * 24,
            validation_min_time_in_market_frac=0.25,
            validation_max_flat_streak_h=60 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "evergreen_regime_guarded":
        return RunConfig(
            lookbacks_h=(72, 120),
            skips_h=(0,),
            rebalances_h=(12, 24),
            ks=(2,),
            score_modes=("risk_adj_mom", "vol_breakout"),
            market_filters_h=(168, 336),
            vol_targets_ann=(0.08, 0.10),
            n_tranches=(2,),
            drawdown_stops=(0.10, 0.15),
            cooldowns_h=(72, 168),
            market_confirm_hs=(72,),
            market_drawdown_limits=(0.20, 0.30),
            selection_min_time_in_market_frac=0.25,
            selection_max_flat_streak_h=120 * 24,
            validation_min_time_in_market_frac=0.15,
            validation_max_flat_streak_h=120 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "evergreen_lowvol_guarded":
        return RunConfig(
            lookbacks_h=(72, 120),
            skips_h=(0,),
            rebalances_h=(8, 12),
            ks=(2, 3),
            score_modes=("risk_adj_mom",),
            market_filters_h=(336,),
            vol_targets_ann=(0.04, 0.06, 0.08),
            n_tranches=(2, 3),
            drawdown_stops=(0.10, 0.15),
            cooldowns_h=(72, 168),
            selection_min_time_in_market_frac=0.40,
            selection_max_flat_streak_h=45 * 24,
            validation_min_time_in_market_frac=0.20,
            validation_max_flat_streak_h=90 * 24,
            stress_costs_bps=(30.0, 40.0),
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
    if preset == "hq_market_neutral":
        return RunConfig(
            lookbacks_h=(600, 720, 840),
            skips_h=(0,),
            rebalances_h=(168,),
            ks=(3,),
            score_modes=("risk_adj_mom",),
            market_filters_h=(0, 504, 1176),
            vol_targets_ann=(0.04, 0.06, 0.07),
            portfolio_modes=("long_short",),
            n_tranches=(1,),
            drawdown_stops=(0.08,),
            cooldowns_h=(72, 120),
            selection_min_time_in_market_frac=0.05,
            validation_min_time_in_market_frac=0.03,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_hedged_long":
        return RunConfig(
            lookbacks_h=(600, 720, 840),
            skips_h=(0,),
            rebalances_h=(168,),
            ks=(3,),
            score_modes=("risk_adj_mom",),
            market_filters_h=(0, 1176),
            vol_targets_ann=(0.06, 0.07),
            portfolio_modes=("hedged_long",),
            hedge_ratios=(0.5, 1.0),
            n_tranches=(1,),
            drawdown_stops=(0.08,),
            cooldowns_h=(72, 120),
            selection_min_time_in_market_frac=0.05,
            validation_min_time_in_market_frac=0.03,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_active_recent":
        return RunConfig(
            lookbacks_h=(504, 720, 1008),
            skips_h=(0,),
            rebalances_h=(120, 168, 240),
            ks=(3, 4, 5),
            score_modes=("mom", "risk_adj_mom"),
            market_filters_h=(336, 504, 720, 1008),
            vol_targets_ann=(0.04, 0.06, 0.08),
            n_tranches=(1,),
            selection_min_time_in_market_frac=0.35,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=45 * 24,
            validation_min_time_in_market_frac=0.20,
            validation_max_flat_streak_h=45 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_recent_signal":
        return RunConfig(
            lookbacks_h=(168, 240, 336, 504),
            skips_h=(0,),
            rebalances_h=(48, 72, 120),
            ks=(2, 3),
            score_modes=("risk_adj_mom", "vol_breakout"),
            market_filters_h=(168, 240, 336, 504),
            vol_targets_ann=(0.04, 0.06),
            n_tranches=(1,),
            drawdown_stops=(0.10,),
            cooldowns_h=(72,),
            market_confirm_hs=(72,),
            market_drawdown_limits=(0.25,),
            selection_min_time_in_market_frac=0.30,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=30 * 24,
            validation_min_time_in_market_frac=0.18,
            validation_max_flat_streak_h=45 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_decay_bridge":
        return RunConfig(
            lookbacks_h=(336, 504, 720, 1008),
            skips_h=(0,),
            rebalances_h=(120, 168, 240),
            ks=(3,),
            score_modes=("risk_adj_mom",),
            market_filters_h=(240, 336, 504, 720),
            vol_targets_ann=(0.06, 0.08, 0.10),
            n_tranches=(1,),
            drawdown_stops=(0.0, 0.10),
            cooldowns_h=(72,),
            selection_min_time_in_market_frac=0.25,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=45 * 24,
            validation_min_time_in_market_frac=0.15,
            validation_max_flat_streak_h=45 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_wf_bridge":
        return RunConfig(
            lookbacks_h=(336, 504),
            skips_h=(0,),
            rebalances_h=(120, 168),
            ks=(3, 4),
            score_modes=("mom", "risk_adj_mom"),
            market_filters_h=(240, 336),
            vol_targets_ann=(0.04, 0.06),
            n_tranches=(2,),
            drawdown_stops=(0.08, 0.10),
            cooldowns_h=(72,),
            market_confirm_hs=(0, 72),
            market_drawdown_limits=(0.0, 0.25),
            selection_min_time_in_market_frac=0.25,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=45 * 24,
            validation_min_time_in_market_frac=0.15,
            validation_max_flat_streak_h=45 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_wf_hostile_bridge":
        return RunConfig(
            lookbacks_h=(336, 504),
            skips_h=(0,),
            rebalances_h=(120, 168),
            ks=(3, 4),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008),
            vol_targets_ann=(0.04, 0.05),
            n_tranches=(2,),
            drawdown_stops=(0.08, 0.10),
            cooldowns_h=(72,),
            market_confirm_hs=(168,),
            market_drawdown_limits=(0.0, 0.15, 0.20),
            selection_min_time_in_market_frac=0.15,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=180 * 24,
            validation_min_time_in_market_frac=0.10,
            validation_max_flat_streak_h=180 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_wf_hostile_hedged":
        return RunConfig(
            lookbacks_h=(336, 504),
            skips_h=(0,),
            rebalances_h=(120, 168),
            ks=(3, 4),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008),
            vol_targets_ann=(0.04, 0.05),
            n_tranches=(2,),
            drawdown_stops=(0.08,),
            cooldowns_h=(72,),
            market_confirm_hs=(168,),
            market_drawdown_limits=(0.0, 0.15, 0.20),
            portfolio_modes=("hedged_long",),
            hedge_ratios=(0.5, 1.0),
            selection_min_time_in_market_frac=0.15,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=180 * 24,
            validation_min_time_in_market_frac=0.10,
            validation_max_flat_streak_h=180 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_wf_hostile_regime_hedged":
        return RunConfig(
            lookbacks_h=(336, 504),
            skips_h=(0,),
            rebalances_h=(120, 168),
            ks=(3, 4),
            score_modes=("risk_adj_mom",),
            market_filters_h=(720, 1008),
            vol_targets_ann=(0.04, 0.05),
            n_tranches=(2,),
            drawdown_stops=(0.08,),
            cooldowns_h=(72,),
            market_confirm_hs=(168,),
            market_drawdown_limits=(0.0, 0.15, 0.20),
            portfolio_modes=("hedged_long",),
            hedge_ratios=(0.5, 1.0),
            downtrend_hedge_ratios=(0.25, 0.50),
            selection_min_2022_return=-0.02,
            selection_min_time_in_market_frac=0.15,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=180 * 24,
            validation_min_time_in_market_frac=0.10,
            validation_max_flat_streak_h=180 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_wf_tail_defense":
        return RunConfig(
            lookbacks_h=(240, 336, 504),
            skips_h=(0,),
            rebalances_h=(72, 120),
            ks=(3,),
            score_modes=("risk_adj_mom_ensemble",),
            market_filters_h=(720, 1008),
            vol_targets_ann=(0.03, 0.04),
            n_tranches=(2,),
            drawdown_stops=(0.06,),
            cooldowns_h=(72,),
            market_confirm_hs=(168,),
            market_drawdown_limits=(0.10, 0.15),
            portfolio_modes=("hedged_long",),
            hedge_ratios=(0.5,),
            downtrend_hedge_ratios=(0.50, 0.75),
            selection_min_2022_return=-0.02,
            selection_min_time_in_market_frac=0.12,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=180 * 24,
            validation_min_time_in_market_frac=0.08,
            validation_max_flat_streak_h=180 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "hq_wf_hostile_long_short":
        return RunConfig(
            lookbacks_h=(336, 504),
            skips_h=(0,),
            rebalances_h=(120, 168),
            ks=(3, 4),
            score_modes=("risk_adj_mom", "mom_reversal_blend"),
            market_filters_h=(0,),
            vol_targets_ann=(0.04, 0.05),
            n_tranches=(2,),
            drawdown_stops=(0.08, 0.10),
            cooldowns_h=(72,),
            market_confirm_hs=(0,),
            market_drawdown_limits=(0.0,),
            portfolio_modes=("long_short",),
            hedge_ratios=(0.5, 1.0),
            selection_min_time_in_market_frac=0.60,
            validation_min_2024h1_periods=1,
            selection_max_flat_streak_h=45 * 24,
            validation_min_time_in_market_frac=0.30,
            validation_max_flat_streak_h=45 * 24,
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "breakout_fast":
        return RunConfig(
            lookbacks_h=(168, 240, 336),
            skips_h=(0, 24),
            rebalances_h=(24, 48, 72),
            ks=(2, 3),
            score_modes=("breakout", "vol_breakout"),
            market_filters_h=(336, 720),
            vol_targets_ann=(0.08, 0.10, 0.12),
            drawdown_stops=(0.10, 0.15),
            cooldowns_h=(168,),
            market_confirm_hs=(168,),
            market_drawdown_limits=(0.25,),
            stress_costs_bps=(30.0, 40.0),
            **base,
        )
    if preset == "breakout_slow":
        return RunConfig(
            lookbacks_h=(504, 720, 1008),
            skips_h=(0, 24),
            rebalances_h=(120, 168, 240),
            ks=(2, 3),
            score_modes=("breakout", "vol_breakout"),
            market_filters_h=(720, 1008, 1440),
            vol_targets_ann=(0.05, 0.06, 0.08),
            drawdown_stops=(0.10, 0.15),
            cooldowns_h=(168,),
            market_confirm_hs=(336,),
            market_drawdown_limits=(0.25,),
            stress_costs_bps=(30.0, 40.0),
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


def ohlcv_config_from_dict(raw: dict[str, Any]) -> OhlcvConfig:
    return OhlcvConfig(
        lookback_h=int(raw["lookback_h"]),
        skip_h=int(raw.get("skip_h", 0)),
        rebalance_h=int(raw["rebalance_h"]),
        k=int(raw["k"]),
        score_mode=str(raw["score_mode"]),
        market_filter_h=int(raw["market_filter_h"]),
        vol_target_ann=float(raw["vol_target_ann"]),
        n_tranches=int(raw.get("n_tranches", 1)),
        drawdown_stop=float(raw.get("drawdown_stop", 0.0)),
        cooldown_h=int(raw.get("cooldown_h", 0)),
        market_confirm_h=int(raw.get("market_confirm_h", 0)),
        market_drawdown_limit=float(raw.get("market_drawdown_limit", 0.0)),
        portfolio_mode=str(raw.get("portfolio_mode", "long_only")),
        hedge_ratio=float(raw.get("hedge_ratio", 0.0)),
        downtrend_hedge_ratio=float(raw.get("downtrend_hedge_ratio", 0.0)),
    )


def load_explicit_configs(path: Path) -> tuple[OhlcvConfig, ...]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        raw_configs = payload.get("configs") or payload.get("rescue_configs") or []
    else:
        raw_configs = payload
    if not isinstance(raw_configs, list):
        raise ValueError("config list JSON must contain a list or a dict with configs")
    configs = tuple(ohlcv_config_from_dict(dict(row)) for row in raw_configs)
    if not configs:
        raise ValueError("config list JSON contains no configs")
    return configs


def rank_centered(frame: pd.DataFrame) -> pd.DataFrame:
    all_missing = frame.isna().all(axis=1)
    ranked = frame.rank(axis=1, pct=True, na_option="bottom") - 0.5
    ranked.loc[all_missing] = np.nan
    return ranked


def risk_adjusted_momentum_score(
    prices: pd.DataFrame,
    log_ret: pd.DataFrame,
    lookback_h: int,
    skip_h: int,
) -> pd.DataFrame:
    lookback = max(2, int(lookback_h))
    min_periods = min(lookback, max(2, lookback // 4))
    mom = prices.shift(skip_h) / prices.shift(skip_h + lookback) - 1.0
    vol = log_ret.rolling(lookback, min_periods=min_periods).std().shift(skip_h)
    return mom / vol.replace(0.0, np.nan)


def score_matrix(closes: pd.DataFrame, cfg: OhlcvConfig) -> pd.DataFrame:
    prices = closes.drop(columns=["dt"])
    mom = prices.shift(cfg.skip_h) / prices.shift(cfg.skip_h + cfg.lookback_h) - 1.0
    if cfg.score_mode == "mom":
        return mom
    ratios = prices / prices.shift(1)
    log_ret = ratios.apply(lambda col: np.log(col.where(col > 0.0)))
    min_periods = min(cfg.lookback_h, max(2, cfg.lookback_h // 4))
    if cfg.score_mode == "risk_adj_mom":
        min_periods = min(cfg.lookback_h, max(2, cfg.lookback_h // 4))
        vol = log_ret.rolling(cfg.lookback_h, min_periods=min_periods).std().shift(cfg.skip_h)
        return mom / vol.replace(0.0, pd.NA)
    if cfg.score_mode == "risk_adj_mom_ensemble":
        horizons = tuple(
            dict.fromkeys(
                (
                    max(2, cfg.lookback_h // 2),
                    max(2, cfg.lookback_h),
                    max(2, int(round(cfg.lookback_h * 1.5))),
                )
            )
        )
        ranked_scores = [
            rank_centered(risk_adjusted_momentum_score(prices, log_ret, horizon, cfg.skip_h))
            for horizon in horizons
        ]
        return sum(ranked_scores) / len(ranked_scores)
    if cfg.score_mode == "mom_reversal_blend":
        vol = log_ret.rolling(cfg.lookback_h, min_periods=min_periods).std().shift(cfg.skip_h)
        risk_adj = mom / vol.replace(0.0, pd.NA)
        reversal_h = max(24, min(72, cfg.lookback_h // 4))
        short_ret = prices.shift(cfg.skip_h) / prices.shift(cfg.skip_h + reversal_h) - 1.0
        risk_rank = risk_adj.rank(axis=1, pct=True) - 0.5
        reversal_rank = short_ret.rank(axis=1, pct=True) - 0.5
        return 0.50 * risk_rank - 0.50 * reversal_rank
    if cfg.score_mode in {"breakout", "vol_breakout"}:
        prior_high = prices.shift(cfg.skip_h + 1).rolling(cfg.lookback_h, min_periods=min_periods).max()
        breakout = prices.shift(cfg.skip_h) / prior_high - 1.0
        positive_breakout = breakout.where(breakout > 0.0, -0.5)
        if cfg.score_mode == "breakout":
            return positive_breakout
        short_h = max(24, min(168, cfg.lookback_h // 4))
        short_vol = log_ret.rolling(short_h, min_periods=max(2, short_h // 4)).std().shift(cfg.skip_h)
        long_vol = log_ret.rolling(cfg.lookback_h, min_periods=min_periods).std().shift(cfg.skip_h)
        vol_expansion = short_vol / long_vol.replace(0.0, pd.NA) - 1.0
        return positive_breakout + 0.25 * vol_expansion
    raise ValueError(f"unknown score mode: {cfg.score_mode}")


def market_drawdown_window_h(cfg: OhlcvConfig) -> int:
    if cfg.market_drawdown_limit <= 0.0:
        return 0
    return max(2, int(max(cfg.market_filter_h, cfg.market_confirm_h, cfg.lookback_h)))


def market_filter_components(closes: pd.DataFrame, cfg: OhlcvConfig) -> dict[str, pd.Series]:
    base = pd.Series([True] * len(closes), index=closes.index)
    prices = closes.drop(columns=["dt"])
    market = prices.mean(axis=1)
    shifted_market = market.shift(cfg.skip_h)
    if cfg.market_filter_h > 0:
        primary_mom = shifted_market / market.shift(cfg.skip_h + cfg.market_filter_h) - 1.0
        primary_allowed = (primary_mom > 0.0).fillna(False)
    else:
        primary_allowed = base
    if cfg.market_confirm_h > 0:
        confirm_mom = shifted_market / market.shift(cfg.skip_h + cfg.market_confirm_h) - 1.0
        confirm_allowed = (confirm_mom > 0.0).fillna(False)
    else:
        confirm_allowed = base
    dd_window = market_drawdown_window_h(cfg)
    if dd_window > 0:
        min_periods = max(2, min(dd_window, dd_window // 4))
        rolling_peak = shifted_market.rolling(dd_window, min_periods=min_periods).max()
        market_dd = 1.0 - shifted_market / rolling_peak
        drawdown_allowed = (market_dd <= cfg.market_drawdown_limit).fillna(False)
    else:
        drawdown_allowed = base
    allowed = (primary_allowed & confirm_allowed & drawdown_allowed).fillna(False)
    return {
        "allowed": allowed,
        "primary_allowed": primary_allowed,
        "confirm_allowed": confirm_allowed,
        "drawdown_allowed": drawdown_allowed,
    }


def market_filter(closes: pd.DataFrame, cfg: OhlcvConfig) -> pd.Series:
    return market_filter_components(closes, cfg)["allowed"]


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


def long_short_weights(score_row: pd.Series, cfg: OhlcvConfig, allow_exposure: bool) -> dict[str, float] | None:
    if score_row.isna().any():
        return None
    if not allow_exposure:
        return {sym: 0.0 for sym in score_row.index}
    ranked = sorted(score_row.index, key=lambda sym: (-float(score_row[sym]), sym))
    k = min(int(cfg.k), max(1, len(ranked) // 2))
    longs = ranked[:k]
    shorts = ranked[-k:]
    short_to_long = float(cfg.hedge_ratio) if float(cfg.hedge_ratio) > 0.0 else 1.0
    long_gross = 1.0 / (1.0 + short_to_long)
    short_gross = short_to_long / (1.0 + short_to_long)
    weights = {sym: 0.0 for sym in score_row.index}
    for sym in longs:
        weights[sym] = long_gross / k
    for sym in shorts:
        weights[sym] = -short_gross / k
    return weights


def hedged_long_weights(score_row: pd.Series, cfg: OhlcvConfig, allow_exposure: bool) -> dict[str, float] | None:
    weights = long_only_weights(score_row, cfg, allow_exposure)
    if weights is None:
        return None
    hedge_symbol = "BTCUSDT" if "BTCUSDT" in weights else sorted(weights)[0]
    if not allow_exposure:
        if float(cfg.downtrend_hedge_ratio) > 0.0:
            weights[hedge_symbol] = -float(cfg.downtrend_hedge_ratio)
        return weights
    long_gross = sum(max(v, 0.0) for v in weights.values())
    weights[hedge_symbol] = weights.get(hedge_symbol, 0.0) - float(cfg.hedge_ratio) * long_gross
    return weights


def target_weights(score_row: pd.Series, cfg: OhlcvConfig, allow_exposure: bool) -> dict[str, float] | None:
    if cfg.portfolio_mode == "long_only":
        return long_only_weights(score_row, cfg, allow_exposure)
    if cfg.portfolio_mode == "long_short":
        return long_short_weights(score_row, cfg, allow_exposure)
    if cfg.portfolio_mode == "hedged_long":
        return hedged_long_weights(score_row, cfg, allow_exposure)
    raise ValueError(f"unknown portfolio_mode: {cfg.portfolio_mode!r}")


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


def max_inactive_streak_h(active_exposure: pd.Series) -> float:
    max_streak = 0
    streak = 0
    for active in active_exposure.tolist():
        if bool(active):
            streak = 0
            continue
        streak += 1
        max_streak = max(max_streak, streak)
    return float(max_streak)


def compounded_return(returns: pd.Series) -> float:
    if len(returns) == 0:
        return 0.0
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def beta_and_correlation(strategy_returns: pd.Series, market_returns: pd.Series) -> tuple[float, float]:
    aligned = pd.concat(
        [
            strategy_returns.rename("strategy"),
            market_returns.rename("market"),
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(aligned) < 2:
        return 0.0, 0.0
    market = aligned["market"].to_numpy(dtype="float64")
    strategy = aligned["strategy"].to_numpy(dtype="float64")
    variance = float(np.var(market))
    beta = float(np.cov(strategy, market, ddof=0)[0, 1] / variance) if variance > 0.0 else 0.0
    corr = float(np.corrcoef(strategy, market)[0, 1]) if np.std(strategy) > 0.0 and np.std(market) > 0.0 else 0.0
    return beta, corr


def regime_attribution(
    ret: pd.DataFrame,
    market_returns: pd.Series,
    primary_allowed: pd.Series,
    cfg: OhlcvConfig,
) -> dict[str, float | int]:
    if len(ret) == 0:
        return {
            "trend_filter_h": int(cfg.market_filter_h),
            "market_total_return": 0.0,
            "market_sharpe": 0.0,
            "beta_to_equal_weight": 0.0,
            "corr_to_equal_weight": 0.0,
            "above_trend_hour_frac": 0.0,
            "below_trend_hour_frac": 0.0,
            "above_trend_avg_gross_exposure": 0.0,
            "below_trend_avg_gross_exposure": 0.0,
            "above_trend_strategy_return": 0.0,
            "below_trend_strategy_return": 0.0,
            "above_trend_market_return": 0.0,
            "below_trend_market_return": 0.0,
        }

    trend = pd.Series(primary_allowed.iloc[: len(ret)].to_numpy(dtype=bool), index=ret.index)
    market = market_returns.reindex(ret.index).fillna(0.0)
    beta, corr = beta_and_correlation(ret["net_return"], market)
    market_period_returns = (1.0 + market).resample(f"{cfg.rebalance_h}h").prod() - 1.0

    def mean_exposure(mask: pd.Series) -> float:
        subset = ret.loc[mask, "gross_exposure"]
        return float(subset.mean()) if len(subset) else 0.0

    def subset_return(series: pd.Series, mask: pd.Series) -> float:
        return compounded_return(series.loc[mask]) if bool(mask.any()) else 0.0

    below = ~trend
    return {
        "trend_filter_h": int(cfg.market_filter_h),
        "market_total_return": compounded_return(market),
        "market_sharpe": sharpe(market_period_returns, 8760.0 / cfg.rebalance_h),
        "beta_to_equal_weight": beta,
        "corr_to_equal_weight": corr,
        "above_trend_hour_frac": float(trend.mean()) if len(trend) else 0.0,
        "below_trend_hour_frac": float(below.mean()) if len(below) else 0.0,
        "above_trend_avg_gross_exposure": mean_exposure(trend),
        "below_trend_avg_gross_exposure": mean_exposure(below),
        "above_trend_strategy_return": subset_return(ret["net_return"], trend),
        "below_trend_strategy_return": subset_return(ret["net_return"], below),
        "above_trend_market_return": subset_return(market, trend),
        "below_trend_market_return": subset_return(market, below),
    }


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


def snapshot_metadata_path(snapshot_path: Path) -> Path:
    return snapshot_path.with_suffix(snapshot_path.suffix + ".json")


def snapshot_window_label(cfg: RunConfig) -> str:
    raw = f"{cfg.train_start}_{cfg.train_end}_{cfg.embargo_start}"
    return "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_")


def data_snapshot_path_for(cfg: RunConfig, fingerprint: str) -> Path:
    symbols_hash = hashlib.sha1(json.dumps(list(cfg.symbols), sort_keys=True).encode("utf-8")).hexdigest()[:10]
    return (
        Path("artifacts/v9/data_snapshots")
        / f"xsec_ohlcv_{snapshot_window_label(cfg)}_{symbols_hash}_{fingerprint[:16]}.parquet"
    )


def data_snapshot_metadata(closes: pd.DataFrame, cfg: RunConfig, fingerprint: str) -> dict[str, Any]:
    return {
        "kind": DATA_SNAPSHOT_KIND,
        "fingerprint": fingerprint,
        "train_start": cfg.train_start,
        "train_end": cfg.train_end,
        "embargo_start": cfg.embargo_start,
        "symbols": list(cfg.symbols),
        "rows": int(len(closes)),
        "first_dt": closes["dt"].iloc[0].isoformat() if len(closes) else None,
        "last_dt": closes["dt"].iloc[-1].isoformat() if len(closes) else None,
    }


def write_data_snapshot(closes: pd.DataFrame, cfg: RunConfig, fingerprint: str) -> tuple[Path, Path]:
    snapshot_path = data_snapshot_path_for(cfg, fingerprint)
    metadata_path = snapshot_metadata_path(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot_path.exists():
        closes.to_parquet(snapshot_path, index=False)
    metadata_path.write_text(json.dumps(data_snapshot_metadata(closes, cfg, fingerprint), sort_keys=True) + "\n")
    return snapshot_path, metadata_path


def read_data_snapshot(snapshot_path: Path, cfg: RunConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    metadata_path = snapshot_metadata_path(snapshot_path)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"data snapshot missing: {snapshot_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"data snapshot metadata missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("kind") != DATA_SNAPSHOT_KIND:
        raise ValueError(f"unsupported data snapshot kind: {metadata.get('kind')!r}")
    for key in ("train_start", "train_end", "embargo_start"):
        if str(metadata.get(key)) != str(getattr(cfg, key)):
            raise ValueError(f"data snapshot {key} mismatch: {metadata.get(key)!r} != {getattr(cfg, key)!r}")
    if list(metadata.get("symbols") or []) != list(cfg.symbols):
        raise ValueError("data snapshot symbols mismatch")
    closes = pd.read_parquet(snapshot_path)
    closes["dt"] = pd.to_datetime(closes["dt"], utc=True)
    closes = closes[["dt", *list(cfg.symbols)]].copy()
    fingerprint = data_fingerprint(closes)
    expected_fingerprint = str(metadata.get("fingerprint") or "")
    if fingerprint != expected_fingerprint:
        raise ValueError(
            f"data snapshot fingerprint mismatch: computed={fingerprint} metadata={expected_fingerprint}"
        )
    return closes, metadata


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
            "selection_min_active_rebalances": int(cfg.selection_min_active_rebalances),
            "selection_min_time_in_market_frac": float(cfg.selection_min_time_in_market_frac),
            "selection_max_flat_streak_h": int(cfg.selection_max_flat_streak_h),
            "validation_min_active_rebalances": int(cfg.validation_min_active_rebalances),
            "validation_min_time_in_market_frac": float(cfg.validation_min_time_in_market_frac),
            "validation_max_flat_streak_h": int(cfg.validation_max_flat_streak_h),
            "portfolio_modes": list(cfg.portfolio_modes),
            "hedge_ratios": list(cfg.hedge_ratios),
            "downtrend_hedge_ratios": list(cfg.downtrend_hedge_ratios),
            "selection_min_2022_return": cfg.selection_min_2022_return,
            "validation_min_2024h1_periods": int(cfg.validation_min_2024h1_periods),
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


def progress_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


GATE_ALIGNMENT_CONTROL_CHECKS = {
    "selection_passed_before_validation",
    "validation_usable",
}


def bounded_score(value: Any, floor: float, target: float) -> float:
    numeric = progress_float(value)
    if numeric is None or target <= floor:
        return 0.0
    return max(0.0, min(1.0, (numeric - floor) / (target - floor)))


def inverse_bounded_score(value: Any, target_or_better: float, fail_at_or_worse: float) -> float:
    numeric = progress_float(value)
    if numeric is None or fail_at_or_worse <= target_or_better:
        return 0.0
    if numeric <= target_or_better:
        return 1.0
    if numeric >= fail_at_or_worse:
        return 0.0
    return (fail_at_or_worse - numeric) / (fail_at_or_worse - target_or_better)


def gate_alignment_summary(row: dict[str, Any]) -> dict[str, Any]:
    checks = row.get("advance_checks") or {}
    scored_checks = {
        str(key): bool(value)
        for key, value in checks.items()
        if str(key) not in GATE_ALIGNMENT_CONTROL_CHECKS
    }
    passed_checks = sum(1 for value in scored_checks.values() if value)
    scored_check_count = len(scored_checks)
    pass_fraction = passed_checks / scored_check_count if scored_check_count else 0.0
    failed_checks = sorted(key for key, value in scored_checks.items() if not value)

    cost20 = row.get("cost20") or {}
    cost40 = row.get("cost40") or {}
    validation20 = ((row.get("validation") or {}).get("cost20") or {})
    validation40 = ((row.get("validation") or {}).get("cost40") or {})
    walk_forward = row.get("walk_forward") or {}
    benchmark = cost20.get("equal_weight_benchmark") or {}

    components = {
        "check_pass_fraction": pass_fraction,
        "selection_sharpe20": bounded_score(cost20.get("sharpe"), 0.0, 1.2),
        "selection_sharpe40": bounded_score(cost40.get("sharpe"), 0.0, 1.0),
        "validation_sharpe20": bounded_score(validation20.get("sharpe"), 0.0, 1.0),
        "walk_forward_q25": bounded_score(walk_forward.get("q25_sharpe"), -0.25, 0.75),
        "yearly_positive": bounded_score(cost20.get("yearly_positive_count"), 0.0, 3.0),
        "bootstrap_p5": bounded_score(cost20.get("bootstrap_30d_sharpe_p5"), 0.0, 0.45),
        "benchmark_excess": bounded_score(benchmark.get("sharpe_excess"), -0.10, 0.10),
        "drawdown": inverse_bounded_score(cost20.get("max_drawdown"), 0.25, 0.50),
        "drawdown_ratio": inverse_bounded_score(benchmark.get("drawdown_ratio"), 0.80, 1.20),
        "flat_streak": inverse_bounded_score(cost40.get("max_flat_streak_h"), 48.0, 240.0),
        "selection_activity": bounded_score(cost40.get("active_rebalance_event_count"), 0.0, 12.0),
        "selection_time_in_market": bounded_score(cost40.get("time_in_market_frac"), 0.0, 0.05),
        "validation_activity": bounded_score(validation40.get("active_rebalance_event_count"), 0.0, 4.0),
        "validation_time_in_market": bounded_score(validation40.get("time_in_market_frac"), 0.0, 0.03),
        "symbol_breadth": inverse_bounded_score(cost20.get("top_positive_symbol_share"), 0.60, 0.80),
    }
    weights = {
        "check_pass_fraction": 4.0,
        "selection_sharpe20": 1.5,
        "selection_sharpe40": 1.0,
        "validation_sharpe20": 2.0,
        "walk_forward_q25": 2.0,
        "yearly_positive": 2.0,
        "bootstrap_p5": 1.0,
        "benchmark_excess": 2.0,
        "drawdown": 1.5,
        "drawdown_ratio": 1.5,
        "flat_streak": 1.0,
        "selection_activity": 1.0,
        "selection_time_in_market": 1.0,
        "validation_activity": 1.0,
        "validation_time_in_market": 1.0,
        "symbol_breadth": 1.0,
    }
    total_weight = sum(weights.values())
    weighted = sum(components[name] * weights[name] for name in weights)
    return {
        "score": round(100.0 * weighted / total_weight, 6) if total_weight else 0.0,
        "passed_checks": int(passed_checks),
        "scored_checks": int(scored_check_count),
        "pass_fraction": round(pass_fraction, 6),
        "failed_checks": failed_checks,
        "components": {name: round(float(value), 6) for name, value in components.items()},
    }


def gate_alignment_score(row: dict[str, Any]) -> float:
    existing = row.get("gate_alignment")
    if isinstance(existing, dict):
        score = progress_float(existing.get("score"))
        if score is not None:
            return score
    return float(gate_alignment_summary(row)["score"])


def progress_row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    cost20 = row.get("cost20") or {}
    validation20 = ((row.get("validation") or {}).get("cost20") or {})
    walk_forward = row.get("walk_forward") or {}
    return (
        bool(row.get("advance_passed")),
        gate_alignment_score(row),
        progress_float(walk_forward.get("q25_sharpe")) or -999.0,
        progress_float(validation20.get("sharpe")) or -999.0,
        progress_float(cost20.get("sharpe")) or -999.0,
        -(progress_float(cost20.get("max_drawdown")) or 999.0),
    )


def progress_row_summary(row: dict[str, Any]) -> dict[str, Any]:
    cost20 = row.get("cost20") or {}
    validation20 = ((row.get("validation") or {}).get("cost20") or {})
    walk_forward = row.get("walk_forward") or {}
    checks = row.get("advance_checks") or {}
    gate_alignment = row.get("gate_alignment")
    if not isinstance(gate_alignment, dict):
        gate_alignment = gate_alignment_summary(row)
    return {
        "advance_passed": bool(row.get("advance_passed")),
        "config": row.get("config") or {},
        "gate_alignment_score": progress_float(gate_alignment.get("score")),
        "gate_alignment_pass_fraction": progress_float(gate_alignment.get("pass_fraction")),
        "cost20_sharpe": progress_float(cost20.get("sharpe")),
        "cost20_return": progress_float(cost20.get("total_return")),
        "cost20_max_drawdown": progress_float(cost20.get("max_drawdown")),
        "validation20_sharpe": progress_float(validation20.get("sharpe")),
        "validation20_return": progress_float(validation20.get("total_return")),
        "validation20_max_drawdown": progress_float(validation20.get("max_drawdown")),
        "walk_forward_q25_sharpe": progress_float(walk_forward.get("q25_sharpe")),
        "failed_checks": sorted(str(key) for key, value in checks.items() if value is False),
    }


def progress_diagnostics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    if not materialized:
        return {
            "pass_count_so_far": 0,
            "selection_pass_count_so_far": 0,
            "validated_row_count_so_far": 0,
            "failed_check_counts": {},
            "best_so_far": None,
            "best_passed_so_far": None,
        }
    failed_counts: Counter[str] = Counter()
    selection_pass_count = 0
    validated_row_count = 0
    for row in materialized:
        selection_checks = ((row.get("selection") or {}).get("checks") or {})
        if selection_checks and all(bool(value) for value in selection_checks.values()):
            selection_pass_count += 1
        if ((row.get("validation") or {}).get("cost20") or {}):
            validated_row_count += 1
        for key, value in (row.get("advance_checks") or {}).items():
            if value is False:
                failed_counts[str(key)] += 1
    passed = [row for row in materialized if row.get("advance_passed")]
    best = max(materialized, key=progress_row_sort_key)
    best_passed = max(passed, key=progress_row_sort_key) if passed else None
    return {
        "pass_count_so_far": len(passed),
        "selection_pass_count_so_far": int(selection_pass_count),
        "validated_row_count_so_far": int(validated_row_count),
        "failed_check_counts": dict(failed_counts.most_common(12)),
        "best_so_far": progress_row_summary(best),
        "best_passed_so_far": progress_row_summary(best_passed) if best_passed else None,
    }


def write_progress_meta(
    path: Path,
    total_rows: int,
    completed_rows: int,
    closes_fingerprint: str,
    cfg: RunConfig,
    bootstrap_p5_min: float,
    validation_sharpe20_min: float,
    confirm_iterations: int,
    progress_rows: Iterable[dict[str, Any]] | None = None,
) -> None:
    payload = {
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "cache_version": ROW_CACHE_VERSION,
        "total_rows": int(total_rows),
        "completed_rows": int(completed_rows),
        "prior_trials": int(cfg.prior_trials),
        "effective_trials": int(total_rows) + int(cfg.prior_trials),
        "data_fingerprint": closes_fingerprint,
        "train_start": cfg.train_start,
        "train_end": cfg.train_end,
        "embargo_start": cfg.embargo_start,
        "bootstrap_iterations": int(cfg.bootstrap_iterations),
        "confirm_iterations": int(confirm_iterations),
        "bootstrap_p5_min": float(bootstrap_p5_min),
        "validation_sharpe20_min": float(validation_sharpe20_min),
        "selection_min_active_rebalances": int(cfg.selection_min_active_rebalances),
        "selection_min_time_in_market_frac": float(cfg.selection_min_time_in_market_frac),
        "selection_max_flat_streak_h": int(cfg.selection_max_flat_streak_h),
        "validation_min_active_rebalances": int(cfg.validation_min_active_rebalances),
        "validation_min_time_in_market_frac": float(cfg.validation_min_time_in_market_frac),
        "validation_max_flat_streak_h": int(cfg.validation_max_flat_streak_h),
        "portfolio_modes": list(cfg.portfolio_modes),
        "hedge_ratios": list(cfg.hedge_ratios),
        "downtrend_hedge_ratios": list(cfg.downtrend_hedge_ratios),
        "selection_min_2022_return": cfg.selection_min_2022_return,
        "validation_min_2024h1_periods": int(cfg.validation_min_2024h1_periods),
    }
    if progress_rows is not None:
        payload["diagnostics"] = progress_diagnostics(progress_rows)
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
    phase_offset_h: int = 0,
) -> dict[str, Any]:
    symbols = [c for c in closes.columns if c != "dt"]
    if cfg.n_tranches < 1:
        raise ValueError("n_tranches must be >= 1")
    if phase_offset_h < 0:
        raise ValueError("phase_offset_h must be >= 0")
    scores = score_matrix(closes, cfg)
    regime_components = market_filter_components(closes, cfg)
    allowed = regime_components["allowed"]
    returns = closes[symbols].pct_change().shift(-1)
    weights = {sym: 0.0 for sym in symbols}
    tranche_weights = [{sym: 0.0 for sym in symbols} for _ in range(cfg.n_tranches)]
    base_phase = int(phase_offset_h) % int(cfg.rebalance_h)
    tranche_offsets = [
        int((base_phase + (idx * cfg.rebalance_h) // cfg.n_tranches) % cfg.rebalance_h)
        for idx in range(cfg.n_tranches)
    ]
    rows = []
    rebalances = []
    symbol_returns = {sym: 0.0 for sym in symbols}
    past_returns: list[float] = []
    scale_sum = 0.0
    scale_count = 0
    equity = 1.0
    peak_equity = 1.0
    risk_stop_peak_equity = 1.0
    risk_off_until = -1
    risk_off_event_count = 0
    risk_stop_exit_cost = 0.0
    risk_stop_exit_turnover = 0.0

    for idx in range(len(closes) - 1):
        ts = pd.Timestamp(closes["dt"].iloc[idx])
        risk_off = idx < risk_off_until
        current_drawdown = 1.0 - equity / risk_stop_peak_equity if risk_stop_peak_equity > 0.0 else 0.0
        stop_triggered = (
            cfg.drawdown_stop > 0.0
            and not risk_off
            and current_drawdown >= cfg.drawdown_stop
        )
        if stop_triggered:
            risk_off_until = idx + max(1, int(cfg.cooldown_h))
            risk_stop_peak_equity = max(equity, 1e-12)
            risk_off_event_count += 1
        risk_off = idx < risk_off_until
        old_weights = dict(weights)
        due_rebalance = False
        if stop_triggered:
            tranche_weights = [{sym: 0.0 for sym in symbols} for _ in range(cfg.n_tranches)]
            due_rebalance = True
        else:
            for tranche_idx, offset in enumerate(tranche_offsets):
                if idx < offset or (idx - offset) % cfg.rebalance_h != 0:
                    continue
                due_rebalance = True
                target = {sym: 0.0 for sym in symbols} if risk_off else target_weights(scores.iloc[idx], cfg, bool(allowed.iloc[idx]))
                if target is not None:
                    scale = exposure_scale(past_returns, cfg.vol_target_ann)
                    tranche_weights[tranche_idx] = {sym: target[sym] * scale / cfg.n_tranches for sym in symbols}
                    scale_sum += scale
                    scale_count += 1
        if due_rebalance:
            weights = {sym: sum(tranche[sym] for tranche in tranche_weights) for sym in symbols}
            turnover = sum(abs(weights[sym] - old_weights[sym]) for sym in symbols)
            cost = turnover * cost_bps / 10000.0
            if stop_triggered:
                risk_stop_exit_cost += cost
                risk_stop_exit_turnover += turnover
            rebalances.append(
                {
                    "dt": ts,
                    "turnover": turnover,
                    "cost": cost,
                    "gross_exposure": sum(abs(v) for v in weights.values()),
                    "reason": "risk_stop" if stop_triggered else ("risk_off" if risk_off else "rebalance"),
                }
            )
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
        equity *= 1.0 + net
        peak_equity = max(peak_equity, equity)
        if not risk_off:
            risk_stop_peak_equity = max(risk_stop_peak_equity, equity)
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
                "risk_off": bool(risk_off),
                "stop_triggered": bool(stop_triggered),
            }
        )
        past_returns.append(net)

    ret = pd.DataFrame(rows).set_index("dt")
    reb = pd.DataFrame(rebalances).set_index("dt")
    regime_len = len(ret)
    active_exposure = ret["gross_exposure"] > ACTIVE_EXPOSURE_THRESHOLD
    active_rebalances = reb["gross_exposure"] > ACTIVE_EXPOSURE_THRESHOLD if len(reb) else pd.Series(dtype=bool)

    def regime_fraction(name: str) -> float:
        series = regime_components[name].iloc[:regime_len]
        return float(series.mean()) if len(series) else 0.0

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
    regime_attr = regime_attribution(
        ret,
        equal_weight,
        regime_components["primary_allowed"],
        cfg,
    )
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
        "time_in_market_frac": float(active_exposure.mean()) if len(active_exposure) else 0.0,
        "max_flat_streak_h": max_inactive_streak_h(active_exposure),
        "avg_long_exposure": float(ret["long_exposure"].mean()) if len(ret) else 0.0,
        "avg_short_exposure": float(ret["short_exposure"].mean()) if len(ret) else 0.0,
        "avg_rebalance_scale": float(scale_sum / scale_count) if scale_count else 1.0,
        "rebalance_event_count": int(len(reb)),
        "active_rebalance_event_count": int(active_rebalances.sum()) if len(active_rebalances) else 0,
        "rebalance_offsets_h": [int(v) for v in tranche_offsets],
        "risk_off_event_count": int(risk_off_event_count),
        "risk_off_hours": int(ret["risk_off"].sum()) if len(ret) else 0,
        "time_in_risk_off_frac": float(ret["risk_off"].mean()) if len(ret) else 0.0,
        "risk_off_max_gross_exposure": float(ret.loc[ret["risk_off"], "gross_exposure"].max()) if len(ret) and bool(ret["risk_off"].any()) else 0.0,
        "risk_stop_exit_cost": float(risk_stop_exit_cost),
        "risk_stop_exit_turnover": float(risk_stop_exit_turnover),
        "market_regime": {
            "primary_filter_h": int(cfg.market_filter_h),
            "confirm_h": int(cfg.market_confirm_h),
            "drawdown_window_h": int(market_drawdown_window_h(cfg)),
            "drawdown_limit": float(cfg.market_drawdown_limit),
            "allowed_frac": regime_fraction("allowed"),
            "primary_allowed_frac": regime_fraction("primary_allowed"),
            "confirm_allowed_frac": regime_fraction("confirm_allowed"),
            "drawdown_allowed_frac": regime_fraction("drawdown_allowed"),
        },
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
        "phase_offset_h": int(base_phase),
        "equal_weight_benchmark": {
            "sharpe": ew_sharpe,
            "max_drawdown": ew_dd,
            "sharpe_excess": period_sharpe - ew_sharpe,
            "drawdown_ratio": dd / ew_dd if ew_dd > 0 else 1.0,
        },
        "regime_attribution": regime_attr,
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


def metric_float(block: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(block.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def advance_checks(
    cost20: dict[str, Any],
    cost40: dict[str, Any],
    bootstrap_p5_min: float = 0.25,
    min_active_rebalances: int = SELECTION_MIN_ACTIVE_REBALANCES,
    min_time_in_market_frac: float = SELECTION_MIN_TIME_IN_MARKET_FRAC,
    max_flat_streak_h: int = 0,
    require_bootstrap: bool = True,
    min_2022_return: float | None = None,
) -> dict[str, bool]:
    benchmark = cost20["equal_weight_benchmark"]
    checks = {
        "sharpe20_ge_1_2": float(cost20["sharpe"]) >= 1.2,
        "max_dd20_le_25pct": float(cost20["max_drawdown"]) <= 0.25,
        "daily_turnover40_le_50pct": float(cost40["daily_turnover"]) <= 0.50,
        "active_rebalances40_ge_min": metric_float(cost40, "active_rebalance_event_count") >= min_active_rebalances,
        "time_in_market40_ge_min": metric_float(cost40, "time_in_market_frac") >= min_time_in_market_frac,
        "positive_3_of_4_years": int(cost20["yearly_positive_count"]) >= 3,
        "return_2024h1_gt_minus_2pct": float(cost20["yearly"]["2024H1"]["net_return"]) > -0.02,
        "sharpe40_ge_1": float(cost40["sharpe"]) >= 1.0,
        "top_symbol_share_le_60pct": float(cost20["top_positive_symbol_share"]) <= 0.60,
        "benchmark_sharpe_excess_ge_0_10": float(benchmark["sharpe_excess"]) >= 0.10,
        "drawdown_ratio_le_0_80": float(benchmark["drawdown_ratio"]) <= 0.80,
    }
    if require_bootstrap:
        checks["bootstrap_p5_ge_adjusted_min"] = float(cost20["bootstrap_30d_sharpe_p5"]) >= bootstrap_p5_min
    if max_flat_streak_h > 0:
        checks["max_flat_streak40_le_limit"] = metric_float(cost40, "max_flat_streak_h") <= max_flat_streak_h
    if min_2022_return is not None:
        checks["return_2022_ge_min"] = float(cost20["yearly"]["2022"]["net_return"]) >= float(min_2022_return)
    return checks


def validation_checks(
    cost20: dict[str, Any],
    cost40: dict[str, Any],
    sharpe20_min: float = 0.70,
    min_active_rebalances: int = VALIDATION_MIN_ACTIVE_REBALANCES,
    min_time_in_market_frac: float = VALIDATION_MIN_TIME_IN_MARKET_FRAC,
    max_flat_streak_h: int = 0,
    min_2024h1_periods: int = 0,
) -> dict[str, bool]:
    checks = {
        "validation_sharpe20_ge_adjusted_min": float(cost20["sharpe"]) >= sharpe20_min,
        "validation_max_dd20_le_30pct": float(cost20["max_drawdown"]) <= 0.30,
        "validation_return20_gt_0": float(cost20["total_return"]) > 0.0,
        "validation_sharpe40_gt_0": float(cost40["sharpe"]) > 0.0,
        "validation_daily_turnover40_le_50pct": float(cost40["daily_turnover"]) <= 0.50,
        "validation_active_rebalances40_ge_min": metric_float(cost40, "active_rebalance_event_count") >= min_active_rebalances,
        "validation_time_in_market40_ge_min": metric_float(cost40, "time_in_market_frac") >= min_time_in_market_frac,
    }
    if max_flat_streak_h > 0:
        checks["validation_max_flat_streak40_le_limit"] = (
            metric_float(cost40, "max_flat_streak_h") <= max_flat_streak_h
        )
    if int(min_2024h1_periods) > 0:
        checks["validation_periods_2024h1_ge_min"] = (
            metric_float(cost20["yearly"]["2024H1"], "periods") >= int(min_2024h1_periods)
        )
    return checks


def min_rows_for_config(cfg: OhlcvConfig) -> int:
    return max(
        cfg.lookback_h + cfg.skip_h + cfg.rebalance_h + 24,
        cfg.market_filter_h + 24,
        cfg.market_confirm_h + 24,
        market_drawdown_window_h(cfg) + 24,
        240,
    )


def walk_forward_summary(
    closes: pd.DataFrame,
    cfg: OhlcvConfig,
    cost_bps: float = 40.0,
    folds: int = 6,
    min_q25_sharpe: float = 0.30,
    min_sign_consistency: float = 0.70,
    min_bounded_loss_consistency: float = 2.0 / 3.0,
    max_bounded_loss_return: float = 0.05,
    max_bounded_loss_drawdown: float = 0.20,
) -> dict[str, Any]:
    min_rows = min_rows_for_config(cfg)
    usable_folds = max(1, min(int(folds), len(closes) // min_rows))
    hedged_overlay = cfg.portfolio_mode == "hedged_long" and float(cfg.hedge_ratio) > 0.0
    unhedged_cfg = (
        replace(cfg, portfolio_mode="long_only", hedge_ratio=0.0, downtrend_hedge_ratio=0.0)
        if hedged_overlay
        else None
    )
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
        unhedged_result = simulate(frame, unhedged_cfg, cost_bps, bootstrap_iterations=0) if unhedged_cfg else None
        legs = result.get("legs", {}) or {}
        attribution = result.get("regime_attribution", {}) or {}
        row = {
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
            "regime_attribution": attribution,
        }
        if unhedged_result is not None:
            row.update(
                {
                    "unhedged_long_only_sharpe": float(unhedged_result["sharpe"]),
                    "unhedged_long_only_total_return": float(unhedged_result["total_return"]),
                    "unhedged_long_only_max_drawdown": float(unhedged_result["max_drawdown"]),
                }
            )
        rows.append(row)
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
    worst_fold_return = float(min(row["total_return"] for row in rows))
    worst_fold_drawdown = float(max(row["max_drawdown"] for row in rows))
    long_active = [row for row in rows if row["avg_long_exposure"] > 0.01]
    short_active = [row for row in rows if row["avg_short_exposure"] > 0.01]
    median_long_sharpe = float(np.median([row["long_gross_sharpe"] for row in long_active])) if long_active else 0.0
    median_short_sharpe = float(np.median([row["short_gross_sharpe"] for row in short_active])) if short_active else 0.0
    median_net_sharpe = float(np.median(sharpes))
    strict_consistency = sign_consistency >= min_sign_consistency and positive_return_fraction >= min_sign_consistency
    bounded_loss_consistency = (
        sign_consistency >= min_bounded_loss_consistency
        and positive_return_fraction >= min_bounded_loss_consistency
        and worst_fold_return >= -max_bounded_loss_return
        and worst_fold_drawdown <= max_bounded_loss_drawdown
    )
    unhedged_rows = [row for row in rows if "unhedged_long_only_max_drawdown" in row]
    if unhedged_rows:
        unhedged_median_sharpe = float(np.median([row["unhedged_long_only_sharpe"] for row in unhedged_rows]))
        hedged_dd_improvement_fraction = float(
            sum(
                1
                for row in unhedged_rows
                if row["max_drawdown"] <= row["unhedged_long_only_max_drawdown"] * 0.90
            )
            / len(unhedged_rows)
        )
    else:
        unhedged_median_sharpe = None
        hedged_dd_improvement_fraction = None
    checks = {
        "wf_q25_sharpe_ge_min": q25 >= min_q25_sharpe,
        "wf_consistency_ge_min_or_bounded_loss": strict_consistency or bounded_loss_consistency,
        "wf_median_long_leg_sharpe_ge_0": median_long_sharpe >= 0.0,
    }
    if hedged_overlay:
        retained_sharpe_floor = (unhedged_median_sharpe or 0.0) * 0.80
        checks.update(
            {
                "wf_hedge_ratio_between_0_20_and_1_00": 0.20 <= float(cfg.hedge_ratio) <= 1.00,
                "wf_net_worst_fold_return_ge_minus_5pct": worst_fold_return >= -max_bounded_loss_return,
                "wf_net_worst_fold_dd_le_20pct": worst_fold_drawdown <= max_bounded_loss_drawdown,
                "wf_net_median_sharpe_retains_80pct_long_only": bool(
                    unhedged_median_sharpe is not None and median_net_sharpe >= retained_sharpe_floor
                ),
                "wf_hedged_dd_improves_half_folds": bool(
                    hedged_dd_improvement_fraction is not None and hedged_dd_improvement_fraction >= 0.50
                ),
            }
        )
    else:
        checks["wf_median_short_leg_sharpe_ge_0"] = median_short_sharpe >= 0.0
    return {
        "enabled": True,
        "passed": all(checks.values()),
        "cost_bps": float(cost_bps),
        "fold_count": int(len(rows)),
        "min_q25_sharpe": float(min_q25_sharpe),
        "min_sign_consistency": float(min_sign_consistency),
        "min_bounded_loss_consistency": float(min_bounded_loss_consistency),
        "max_bounded_loss_return": float(max_bounded_loss_return),
        "max_bounded_loss_drawdown": float(max_bounded_loss_drawdown),
        "q25_sharpe": q25,
        "sign_consistency": sign_consistency,
        "positive_return_fraction": positive_return_fraction,
        "worst_fold_return": worst_fold_return,
        "worst_fold_max_drawdown": worst_fold_drawdown,
        "median_net_sharpe": median_net_sharpe,
        "median_long_gross_sharpe": median_long_sharpe,
        "median_short_gross_sharpe": median_short_sharpe,
        "unhedged_long_only_median_sharpe": unhedged_median_sharpe,
        "hedged_dd_improvement_fraction": hedged_dd_improvement_fraction,
        "strict_consistency_passed": strict_consistency,
        "bounded_loss_consistency_passed": bounded_loss_consistency,
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
            drawdown_stop=cfg.drawdown_stop,
            cooldown_h=cfg.cooldown_h,
            market_confirm_h=cfg.market_confirm_h,
            market_drawdown_limit=cfg.market_drawdown_limit,
            portfolio_mode=cfg.portfolio_mode,
            hedge_ratio=cfg.hedge_ratio,
            downtrend_hedge_ratio=cfg.downtrend_hedge_ratio,
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
    purge_h = max(
        int(cfg.lookback_h + cfg.skip_h),
        int(cfg.rebalance_h),
        int(cfg.market_filter_h),
        int(cfg.market_confirm_h),
        int(market_drawdown_window_h(cfg)),
    )
    validation_start = split_dt + pd.Timedelta(hours=purge_h)
    selection = closes.loc[closes["dt"] <= split_dt].copy().reset_index(drop=True)
    validation = closes.loc[closes["dt"] >= validation_start].copy().reset_index(drop=True)
    min_validation_rows = min_rows_for_config(cfg)
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
    snapshot_source = "live_cache"
    snapshot_path: Path | None = None
    snapshot_meta_path: Path | None = None
    snapshot_meta: dict[str, Any] = {}
    if cfg.data_snapshot:
        snapshot_path = Path(cfg.data_snapshot)
        closes, snapshot_meta = read_data_snapshot(snapshot_path, cfg)
        snapshot_meta_path = snapshot_metadata_path(snapshot_path)
        snapshot_source = "pinned_data_snapshot"
    else:
        closes = load_close_matrix(Path(cfg.cache_dir), cfg.symbols, start, end, embargo)
    closes_fingerprint = data_fingerprint(closes)
    if not cfg.data_snapshot:
        snapshot_path, snapshot_meta_path = write_data_snapshot(closes, cfg, closes_fingerprint)
        snapshot_meta = data_snapshot_metadata(closes, cfg, closes_fingerprint)
    if cfg.explicit_configs:
        grid = list(dict.fromkeys(cfg.explicit_configs))
    else:
        grid = [
            OhlcvConfig(l, s, r, k, mode, mf, vt, nt, dd, cd, mc, mdl, pm, hr, dhr)
            for l, s, r, k, mode, mf, vt, nt, dd, cd, mc, mdl, pm, hr, dhr in itertools.product(
                cfg.lookbacks_h,
                cfg.skips_h,
                cfg.rebalances_h,
                cfg.ks,
                cfg.score_modes,
                cfg.market_filters_h,
                cfg.vol_targets_ann,
                cfg.n_tranches,
                cfg.drawdown_stops,
                cfg.cooldowns_h,
                cfg.market_confirm_hs,
                cfg.market_drawdown_limits,
                cfg.portfolio_modes,
                cfg.hedge_ratios,
                cfg.downtrend_hedge_ratios,
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
        progress_rows=progress_rows.values(),
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
            bootstrap_iterations=0,
            bootstrap_seed_value=bootstrap_seed(g, 20.0, "selection", cfg.train_start, cfg.train_end),
        )
        cost40 = simulate(
            selection_closes,
            g,
            40.0,
            bootstrap_iterations=0,
            bootstrap_seed_value=bootstrap_seed(g, 40.0, "selection", cfg.train_start, cfg.train_end),
        )
        selection_checks = advance_checks(
            cost20,
            cost40,
            bootstrap_p5_min=bootstrap_p5_min,
            min_active_rebalances=cfg.selection_min_active_rebalances,
            min_time_in_market_frac=cfg.selection_min_time_in_market_frac,
            max_flat_streak_h=cfg.selection_max_flat_streak_h,
            require_bootstrap=False,
            min_2022_return=cfg.selection_min_2022_return,
        )
        selection_prefilter_passed = all(selection_checks.values())
        selection_prefilter = {
            "enabled": True,
            "passed": bool(selection_prefilter_passed),
            "skipped_bootstrap": not bool(selection_prefilter_passed),
            "bootstrap_check_skipped": not bool(selection_prefilter_passed),
            "failed_checks": sorted(name for name, passed in selection_checks.items() if not passed),
            "note": "Cheap train-only selection gates run before bootstrap, walk-forward, and validation.",
        }
        if selection_prefilter_passed:
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
            selection_checks = advance_checks(
                cost20,
                cost40,
                bootstrap_p5_min=bootstrap_p5_min,
                min_active_rebalances=cfg.selection_min_active_rebalances,
                min_time_in_market_frac=cfg.selection_min_time_in_market_frac,
                max_flat_streak_h=cfg.selection_max_flat_streak_h,
                min_2022_return=cfg.selection_min_2022_return,
            )
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
            selection_checks = advance_checks(
                cost20,
                cost40,
                bootstrap_p5_min=bootstrap_p5_min,
                min_active_rebalances=cfg.selection_min_active_rebalances,
                min_time_in_market_frac=cfg.selection_min_time_in_market_frac,
                max_flat_streak_h=cfg.selection_max_flat_streak_h,
                min_2022_return=cfg.selection_min_2022_return,
            )
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
            val_checks = validation_checks(
                val20,
                val40,
                sharpe20_min=validation_sharpe20_min,
                min_active_rebalances=cfg.validation_min_active_rebalances,
                min_time_in_market_frac=cfg.validation_min_time_in_market_frac,
                max_flat_streak_h=cfg.validation_max_flat_streak_h,
                min_2024h1_periods=cfg.validation_min_2024h1_periods,
            )
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
            "selection_prefilter": selection_prefilter,
            "validation": {"cost20": val20, "cost40": val40, "checks": val_checks, "split": split_meta},
            "walk_forward": walk_forward,
            "diagnostic_walk_forward": diagnostic_walk_forward,
            "leave_one_symbol": leave_one_symbol,
            "cost_stress": cost_stress,
            "advance_checks": checks,
            "advance_passed": all(checks.values()),
        }
        row["gate_alignment"] = gate_alignment_summary(row)
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
            progress_rows=progress_rows.values(),
        )
        rows.append(row)
    for row in rows:
        row["gate_alignment"] = gate_alignment_summary(row)
    rows.sort(
        key=progress_row_sort_key,
        reverse=True,
    )
    pass_rows = [row for row in rows if row["advance_passed"]]
    stability = plateau_stability_summary(rows, cfg)
    accepted_max_validation_active_rebalances = max(
        (
            metric_float(((row.get("validation") or {}).get("cost40") or {}), "active_rebalance_event_count")
            for row in pass_rows
        ),
        default=0.0,
    )
    accepted_activity_ok = (
        accepted_max_validation_active_rebalances >= int(cfg.accepted_min_validation_active_rebalances)
    )
    accepted = len(pass_rows) >= 3 and accepted_activity_ok
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
        "selection_min_active_rebalances": int(cfg.selection_min_active_rebalances),
        "selection_min_time_in_market_frac": float(cfg.selection_min_time_in_market_frac),
        "selection_max_flat_streak_h": int(cfg.selection_max_flat_streak_h),
        "validation_min_active_rebalances": int(cfg.validation_min_active_rebalances),
        "validation_min_time_in_market_frac": float(cfg.validation_min_time_in_market_frac),
        "validation_max_flat_streak_h": int(cfg.validation_max_flat_streak_h),
        "accepted_min_validation_active_rebalances": int(cfg.accepted_min_validation_active_rebalances),
        "selection_min_2022_return": cfg.selection_min_2022_return,
        "validation_min_2024h1_periods": int(cfg.validation_min_2024h1_periods),
        "validate_all_rows": bool(cfg.validate_all_rows),
        "stress_costs_bps": [float(v) for v in cfg.stress_costs_bps],
        "explicit_config_list": bool(cfg.explicit_configs),
        "walk_forward_required": True,
        "walk_forward_cost_bps": 40.0,
        "selection_prefilter_enabled": True,
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
        "accepted_activity_ok": accepted_activity_ok,
        "accepted_max_validation_active_rebalances": int(accepted_max_validation_active_rebalances),
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
            "snapshot": {
                "enabled": True,
                "source": snapshot_source,
                "path": str(snapshot_path) if snapshot_path else "",
                "metadata_path": str(snapshot_meta_path) if snapshot_meta_path else "",
                "fingerprint": str(snapshot_meta.get("fingerprint") or closes_fingerprint),
            },
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
            "| cfg | pass | gate | sel 20bps sh | wf q25 40bps | diag wf q25 | val 20bps sh | val ret | val DD | sel boot p5 | EW excess | DD ratio | top sym | loo min sh |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["top"]:
        cfg = row["config"]
        c20 = row["cost20"]
        v20 = row.get("validation", {}).get("cost20", {}) or {}
        walk_forward = row.get("walk_forward", {}) or {}
        diagnostic_walk_forward = row.get("diagnostic_walk_forward", {}) or {}
        leave_one_symbol = row.get("leave_one_symbol", {}) or {}
        gate_alignment = row.get("gate_alignment")
        if not isinstance(gate_alignment, dict):
            gate_alignment = gate_alignment_summary(row)
        bench = c20["equal_weight_benchmark"]
        label = (
            "L{lookback_h}_S{skip_h}_R{rebalance_h}_K{k}_{score_mode}_"
            "MF{market_filter_h}_MC{market_confirm_h}_MD{market_drawdown_limit}_"
            "VT{vol_target_ann}_NT{n_tranches}_DD{drawdown_stop}_CD{cooldown_h}_"
            "PM{portfolio_mode}_HR{hedge_ratio}_DHR{downtrend_hedge_ratio}"
        ).format(**cfg)
        lines.append(
            "| `{}` | `{}` | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
                label,
                row["advance_passed"],
                float(gate_alignment.get("score", 0.0) or 0.0),
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
            "evergreen_fast",
            "evergreen_guarded",
            "evergreen_regime_guarded",
            "evergreen_lowvol_guarded",
            "breakout_fast",
            "breakout_slow",
            "hq_dd_long",
            "hq_market_neutral",
            "hq_hedged_long",
            "hq_dd_plateau",
            "hq_active_recent",
            "hq_recent_signal",
            "hq_decay_bridge",
            "hq_wf_bridge",
            "hq_wf_hostile_bridge",
            "hq_wf_hostile_hedged",
            "hq_wf_hostile_regime_hedged",
            "hq_wf_tail_defense",
            "hq_wf_hostile_long_short",
            "hq_cadence_tranche",
            "hq_fast_rebal",
            "hq_breadth_wide",
        ),
        default="core",
    )
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--data-snapshot", default="", help="Optional pinned train-only close matrix snapshot")
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--bootstrap-iterations", type=int, default=500)
    ap.add_argument("--prior-trials", type=int, default=0)
    ap.add_argument("--config-list-json", default="", help="Optional train-only list of explicit OhlcvConfig rows to evaluate")
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
        data_snapshot=args.data_snapshot,
    )
    if args.config_list_json:
        cfg = RunConfig(
            symbols=cfg.symbols,
            lookbacks_h=cfg.lookbacks_h,
            skips_h=cfg.skips_h,
            rebalances_h=cfg.rebalances_h,
            ks=cfg.ks,
            score_modes=cfg.score_modes,
            market_filters_h=cfg.market_filters_h,
            vol_targets_ann=cfg.vol_targets_ann,
            n_tranches=cfg.n_tranches,
            drawdown_stops=cfg.drawdown_stops,
            cooldowns_h=cfg.cooldowns_h,
            market_confirm_hs=cfg.market_confirm_hs,
            market_drawdown_limits=cfg.market_drawdown_limits,
            portfolio_modes=cfg.portfolio_modes,
            hedge_ratios=cfg.hedge_ratios,
            downtrend_hedge_ratios=cfg.downtrend_hedge_ratios,
            costs_bps=cfg.costs_bps,
            stress_costs_bps=cfg.stress_costs_bps,
            validate_all_rows=cfg.validate_all_rows,
            selection_min_2022_return=cfg.selection_min_2022_return,
            validation_min_2024h1_periods=cfg.validation_min_2024h1_periods,
            plateau_center_config=None,
            plateau_validation_sharpe_min=cfg.plateau_validation_sharpe_min,
            plateau_neighbor_pass_fraction_min=cfg.plateau_neighbor_pass_fraction_min,
            plateau_center_max_ratio=cfg.plateau_center_max_ratio,
            train_start=cfg.train_start,
            train_end=cfg.train_end,
            embargo_start=cfg.embargo_start,
            cache_dir=cfg.cache_dir,
            data_snapshot=cfg.data_snapshot,
            bootstrap_iterations=cfg.bootstrap_iterations,
            prior_trials=cfg.prior_trials,
            explicit_configs=load_explicit_configs(Path(args.config_list_json)),
            out_json=cfg.out_json,
            out_md=cfg.out_md,
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
