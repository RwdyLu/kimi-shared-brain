from __future__ import annotations

import argparse
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .freeze import bootstrap_net_pnl_p5, max_underwater_days
from .metrics import GateConfig, evaluate_gates
from .report import write_json, write_markdown
from .schema import ContractCandidate
from .simulator import attach_regimes, load_regime_labels, load_symbol_1h, prepare_features, simulate_candidate, utc_ts


@dataclass(frozen=True)
class SearchConfig:
    symbol: str = "LINKUSDT"
    samples: int = 250
    seed: int = 20260706
    train_start: str = "2017-08-01"
    train_end: str = "2024-06-30 23:59:59"
    embargo_start: str = "2024-07-01"
    cache_dir: str = "data/binance_public_cache"
    regime_labels_dir: str = "artifacts/v9"
    out_json: str = "artifacts/v9/contract_lab/contract_search_LINKUSDT_train.json"
    out_md: str = "artifacts/v9/contract_lab/contract_search_LINKUSDT_train.md"
    ranking_mode: str = "train_gate"
    proxy_bootstrap_iterations: int = 200
    sampling_profile: str = "standard"
    min_signals_train: int | None = None
    min_signals_per_fold: int | None = None
    max_signals_train: int | None = None
    freeze_distribution_hard_gate: bool = False
    freeze_gate_margin: float = 0.90
    min_hard_trades: int | None = None
    max_attempts: int | None = None


FREEZE_TOP5_PROFIT_SHARE_LIMIT = 0.40
FREEZE_UNDERWATER_DAYS_LIMIT = 730
PULLBACK_NET2_TARGET = 1550.0


REGIME_CHOICES = [
    ("up_normal",),
    ("up_high_vol",),
    ("up_normal", "up_high_vol"),
    ("up_normal", "range_normal"),
    ("up_normal", "up_high_vol", "range_normal"),
]


FREEZE_DENSE_WEIGHTS = {
    "breakout_n": [(12, 0.30), (24, 0.35), (48, 0.25), (96, 0.10)],
    "atr_n": [(14, 0.40), (24, 0.40), (48, 0.20)],
    "stop_atr_k": [(1.0, 0.10), (1.5, 0.30), (2.0, 0.35), (2.5, 0.20), (3.0, 0.05)],
    "tp_r_multiple": [(1.5, 0.40), (2.0, 0.35), (2.5, 0.20), (3.0, 0.05)],
    "max_hold_bars": [(12, 0.15), (24, 0.35), (48, 0.35), (96, 0.15)],
    "risk_per_trade": [(0.0025, 0.25), (0.005, 0.35), (0.0075, 0.25), (0.01, 0.15)],
    "leverage_cap": [(1.0, 0.50), (2.0, 0.35), (3.0, 0.15)],
    "cooldown_bars": [(0, 0.40), (6, 0.35), (12, 0.20), (24, 0.05)],
    "allowed_regimes": [
        (("up_normal", "up_high_vol", "range_normal"), 0.50),
        (("up_normal", "up_high_vol"), 0.35),
        (("up_normal",), 0.15),
    ],
}


FREEZE_BALANCED_WEIGHTS = {
    "breakout_n": [(12, 0.10), (16, 0.20), (20, 0.30), (24, 0.25), (32, 0.15)],
    "atr_n": [(14, 0.25), (20, 0.30), (28, 0.30), (48, 0.15)],
    "stop_atr_k": [(1.0, 0.15), (1.5, 0.30), (2.0, 0.35), (2.5, 0.20)],
    "tp_r_multiple": [(1.5, 0.20), (2.0, 0.35), (2.5, 0.30), (3.0, 0.15)],
    "max_hold_bars": [(12, 0.20), (24, 0.40), (36, 0.25), (48, 0.15)],
    "risk_per_trade": [(0.003, 0.25), (0.005, 0.50), (0.0075, 0.25)],
    "leverage_cap": [(1.0, 0.55), (2.0, 0.35), (3.0, 0.10)],
    "cooldown_bars": [(2, 0.30), (4, 0.40), (8, 0.30)],
    "allowed_regimes": [
        (("up_normal", "up_high_vol", "range_normal"), 0.45),
        (("up_normal", "up_high_vol"), 0.40),
        (("up_normal",), 0.15),
    ],
}


FREEZE_PROTECTIVE_WEIGHTS = {
    **FREEZE_BALANCED_WEIGHTS,
    "be_trigger_r": [(None, 0.20), (0.5, 0.20), (0.75, 0.25), (1.0, 0.25), (1.5, 0.10)],
    "be_lock_r": [(0.0, 0.34), (0.1, 0.33), (0.25, 0.33)],
    "trail_atr_mult": [(None, 0.30), (1.5, 0.15), (2.0, 0.25), (2.5, 0.20), (3.0, 0.10)],
    "trail_trigger_r": [(0.5, 0.34), (1.0, 0.33), (1.5, 0.33)],
}


FREEZE_DISTRIBUTED_WEIGHTS = {
    "breakout_n": [(8, 0.30), (12, 0.30), (16, 0.20), (20, 0.15), (24, 0.05)],
    "atr_n": [(7, 0.35), (10, 0.40), (14, 0.25)],
    "stop_atr_k": [(1.0, 0.30), (1.25, 0.35), (1.5, 0.25), (1.75, 0.10)],
    "tp_r_multiple": [(1.2, 0.30), (1.5, 0.35), (1.8, 0.25), (2.2, 0.10)],
    "max_hold_bars": [(36, 0.20), (48, 0.35), (72, 0.30), (96, 0.15)],
    "risk_per_trade": [(0.004, 0.35), (0.005, 0.40), (0.0075, 0.25)],
    "leverage_cap": [(2.0, 0.35), (3.0, 0.45), (4.0, 0.20)],
    "cooldown_bars": [(0, 0.30), (2, 0.35), (4, 0.25), (6, 0.10)],
    "allowed_regimes": [
        (("deep_drawdown", "range_normal", "up_high_vol", "up_normal"), 0.45),
        (("range_normal", "up_high_vol", "up_normal"), 0.35),
        (("up_high_vol", "up_normal"), 0.20),
    ],
    "vol_scaling": [("none", 0.20), ("inverse_atr", 0.40), ("vol_target", 0.40)],
    "vol_lookback_n": [(20, 0.25), (50, 0.35), (100, 0.25), (200, 0.15)],
    "vol_target_ann": [(0.30, 0.20), (0.50, 0.35), (0.70, 0.30), (1.00, 0.15)],
    "scale_bounds": [((0.25, 2.0), 0.50), ((0.50, 1.5), 0.30), ((0.10, 3.0), 0.20)],
}


FREEZE_PULLBACK_WEIGHTS = {
    "trend_ema_len": [(50, 0.35), (100, 0.40), (200, 0.25)],
    "rsi_len": [(2, 0.45), (3, 0.35), (4, 0.20)],
    "rsi_entry_max": [(10.0, 0.20), (15.0, 0.30), (20.0, 0.30), (25.0, 0.20)],
    "rsi_exit_min": [(55.0, 0.30), (65.0, 0.45), (75.0, 0.25)],
    "atr_n": [(7, 0.30), (10, 0.35), (14, 0.35)],
    "stop_atr_k": [(1.0, 0.25), (1.25, 0.35), (1.5, 0.30), (1.75, 0.10)],
    "tp_r_multiple": [(1.0, 0.30), (1.2, 0.35), (1.5, 0.25), (1.8, 0.10)],
    "max_hold_bars": [(12, 0.35), (18, 0.40), (27, 0.25)],
    "risk_per_trade": [(0.003, 0.30), (0.004, 0.35), (0.005, 0.25), (0.0075, 0.10)],
    "leverage_cap": [(1.0, 0.35), (2.0, 0.45), (3.0, 0.20)],
    "cooldown_bars": [(0, 0.25), (2, 0.35), (4, 0.30), (6, 0.10)],
    "allowed_regimes": [
        (("up_normal", "up_high_vol", "range_normal"), 0.45),
        (("up_normal", "up_high_vol"), 0.40),
        (("up_normal",), 0.15),
    ],
}


FREEZE_BEAR_FADE_WEIGHTS = {
    "regime_len": [(100, 0.35), (150, 0.40), (200, 0.25)],
    "slope_len": [(10, 0.55), (20, 0.45)],
    "rsi_len": [(2, 0.40), (3, 0.35), (4, 0.25)],
    "rsi_hi": [(65.0, 0.25), (70.0, 0.35), (75.0, 0.25), (80.0, 0.15)],
    "stop_pct": [(0.02, 0.35), (0.03, 0.40), (0.05, 0.25)],
    "target_pct": [(0.01, 0.30), (0.015, 0.35), (0.02, 0.25), (0.03, 0.10)],
    "max_hold_bars": [(12, 0.30), (24, 0.45), (48, 0.25)],
    "risk_per_trade": [(0.003, 0.35), (0.004, 0.35), (0.005, 0.20), (0.0075, 0.10)],
    "leverage_cap": [(1.0, 0.45), (2.0, 0.40), (3.0, 0.15)],
    "cooldown_bars": [(0, 0.30), (2, 0.35), (4, 0.25), (6, 0.10)],
    "allowed_regimes": [
        (("deep_drawdown", "range_normal", "up_high_vol", "up_normal"), 0.45),
        (("deep_drawdown", "range_normal"), 0.30),
        (("deep_drawdown",), 0.25),
    ],
    "vol_scaling": [("none", 0.20), ("inverse_atr", 0.40), ("vol_target", 0.40)],
    "vol_lookback_n": [(20, 0.25), (50, 0.35), (100, 0.25), (200, 0.15)],
    "vol_target_ann": [(0.30, 0.20), (0.50, 0.35), (0.70, 0.30), (1.00, 0.15)],
    "scale_bounds": [((0.25, 2.0), 0.50), ((0.50, 1.5), 0.30), ((0.10, 3.0), 0.20)],
}


def weighted_choice(rng: random.Random, choices: list[tuple[Any, float]]) -> Any:
    clean = [(value, float(weight)) for value, weight in choices if float(weight) > 0.0]
    total = sum(weight for _, weight in clean)
    if total <= 0:
        raise ValueError("weighted choices must include positive weights")
    point = rng.random() * total
    cumulative = 0.0
    for value, weight in clean:
        cumulative += weight
        if point <= cumulative:
            return value
    return clean[-1][0]


def dense_combo_rejection(candidate: ContractCandidate) -> str | None:
    strict_regime = candidate.allowed_regimes == ("up_normal",)
    if candidate.breakout_n == 96 and candidate.cooldown_bars >= 12:
        return "breakout96_cooldown_ge12"
    if candidate.breakout_n >= 48 and candidate.max_hold_bars <= 12:
        return "slow_breakout_short_hold"
    if candidate.tp_r_multiple >= 2.5 and candidate.stop_atr_k >= 2.5:
        return "wide_stop_high_target"
    if candidate.stop_atr_k == 1.0 and candidate.breakout_n == 12:
        return "tight_stop_fast_breakout"
    if candidate.risk_per_trade == 0.01 and candidate.leverage_cap == 3.0:
        return "high_risk_high_leverage"
    if candidate.cooldown_bars > candidate.breakout_n / 2:
        return "cooldown_gt_half_breakout"
    if strict_regime and candidate.breakout_n >= 48:
        return "strict_regime_slow_breakout"
    return None


def balanced_combo_rejection(candidate: ContractCandidate) -> str | None:
    if candidate.breakout_n <= 12 and candidate.atr_n >= 40 and candidate.max_hold_bars >= 36:
        return "fast_breakout_slow_atr_long_hold"
    if candidate.atr_n / candidate.breakout_n > 2.5:
        return "atr_breakout_ratio_gt_2_5"
    if candidate.max_hold_bars > 2 * candidate.atr_n:
        return "max_hold_gt_2x_atr"
    rr = candidate.tp_r_multiple / candidate.stop_atr_k
    if rr < 0.8 or rr > 2.0:
        return "rr_outside_0_8_2_0"
    return None


def distributed_combo_rejection(candidate: ContractCandidate) -> str | None:
    if candidate.cooldown_bars > candidate.breakout_n // 2:
        return "cooldown_gt_half_breakout"
    if candidate.breakout_n >= 20 and candidate.max_hold_bars <= 36:
        return "slow_breakout_short_hold"
    if candidate.allowed_regimes == ("up_high_vol", "up_normal") and candidate.breakout_n >= 20:
        return "strict_regime_slow_breakout"
    if candidate.stop_atr_k >= 1.75 and candidate.tp_r_multiple >= 2.2:
        return "wide_stop_high_target"
    if candidate.breakout_n <= 8 and candidate.risk_per_trade >= 0.0075 and candidate.leverage_cap >= 4:
        return "high_freq_high_risk"
    return None


def pullback_combo_rejection(candidate: ContractCandidate) -> str | None:
    if candidate.rsi_entry_max >= candidate.rsi_exit_min:
        return "rsi_entry_not_below_exit"
    if candidate.max_hold_bars > 3 * candidate.rsi_len * 3:
        return "pullback_hold_too_long_for_rsi"
    if candidate.stop_atr_k >= 1.75 and candidate.tp_r_multiple >= 1.8:
        return "pullback_wide_stop_high_target"
    if candidate.rsi_entry_max <= 10 and candidate.allowed_regimes == ("up_normal",):
        return "strict_regime_extreme_rsi"
    if candidate.cooldown_bars > 0 and candidate.cooldown_bars >= candidate.max_hold_bars / 2:
        return "pullback_cooldown_too_long"
    return None


def bear_fade_combo_rejection(candidate: ContractCandidate) -> str | None:
    if candidate.target_pct >= candidate.stop_pct:
        return "short_target_not_below_stop"
    if candidate.rsi_hi <= 65 and candidate.allowed_regimes == ("deep_drawdown", "range_normal", "up_high_vol", "up_normal"):
        return "broad_regime_low_rsi_hi"
    if candidate.max_hold_bars >= 48 and candidate.target_pct <= 0.01:
        return "long_hold_tiny_target"
    if candidate.stop_pct >= 0.05 and candidate.leverage_cap >= 3.0:
        return "wide_stop_high_leverage"
    if candidate.cooldown_bars > 0 and candidate.cooldown_bars >= candidate.max_hold_bars / 2:
        return "short_cooldown_too_long"
    return None


def is_balanced_derived_profile(sampling_profile: str) -> bool:
    return sampling_profile in {"freeze_balanced", "freeze_protective"}


def random_candidate(symbol: str, rng: random.Random, sampling_profile: str = "standard") -> ContractCandidate:
    if sampling_profile == "freeze_bear_fade":
        scale_min, scale_max = weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["scale_bounds"])
        return ContractCandidate(
            symbol=symbol,
            family="bear_rally_fade_short_v1",
            side="short",
            allowed_regimes=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["allowed_regimes"]),
            regime_len=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["regime_len"]),
            slope_len=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["slope_len"]),
            rsi_len=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["rsi_len"]),
            rsi_hi=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["rsi_hi"]),
            stop_pct=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["stop_pct"]),
            target_pct=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["target_pct"]),
            max_hold_bars=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["max_hold_bars"]),
            risk_per_trade=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["risk_per_trade"]),
            leverage_cap=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["leverage_cap"]),
            cooldown_bars=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["cooldown_bars"]),
            vol_scaling=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["vol_scaling"]),
            vol_lookback_n=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["vol_lookback_n"]),
            vol_target_ann=weighted_choice(rng, FREEZE_BEAR_FADE_WEIGHTS["vol_target_ann"]),
            scale_min=scale_min,
            scale_max=scale_max,
            fee_bps=5.0,
            slippage_bps=2.0,
            funding_bps_per_8h=1.0,
            short_extra_cost_bps=5.0,
        )
    if sampling_profile == "freeze_pullback":
        return ContractCandidate(
            symbol=symbol,
            family="pullback_long_v1",
            allowed_regimes=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["allowed_regimes"]),
            trend_ema_len=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["trend_ema_len"]),
            rsi_len=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["rsi_len"]),
            rsi_entry_max=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["rsi_entry_max"]),
            rsi_exit_min=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["rsi_exit_min"]),
            atr_n=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["atr_n"]),
            stop_atr_k=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["stop_atr_k"]),
            tp_r_multiple=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["tp_r_multiple"]),
            max_hold_bars=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["max_hold_bars"]),
            risk_per_trade=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["risk_per_trade"]),
            leverage_cap=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["leverage_cap"]),
            cooldown_bars=weighted_choice(rng, FREEZE_PULLBACK_WEIGHTS["cooldown_bars"]),
            fee_bps=5.0,
            slippage_bps=2.0,
            funding_bps_per_8h=1.0,
        )
    if sampling_profile == "freeze_distributed":
        scale_min, scale_max = weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["scale_bounds"])
        return ContractCandidate(
            symbol=symbol,
            allowed_regimes=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["allowed_regimes"]),
            breakout_n=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["breakout_n"]),
            atr_n=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["atr_n"]),
            stop_atr_k=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["stop_atr_k"]),
            tp_r_multiple=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["tp_r_multiple"]),
            max_hold_bars=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["max_hold_bars"]),
            risk_per_trade=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["risk_per_trade"]),
            leverage_cap=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["leverage_cap"]),
            cooldown_bars=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["cooldown_bars"]),
            vol_scaling=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["vol_scaling"]),
            vol_lookback_n=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["vol_lookback_n"]),
            vol_target_ann=weighted_choice(rng, FREEZE_DISTRIBUTED_WEIGHTS["vol_target_ann"]),
            scale_min=scale_min,
            scale_max=scale_max,
            fee_bps=5.0,
            slippage_bps=2.0,
            funding_bps_per_8h=1.0,
        )
    if sampling_profile in {"freeze_balanced", "freeze_protective"}:
        weights = FREEZE_PROTECTIVE_WEIGHTS if sampling_profile == "freeze_protective" else FREEZE_BALANCED_WEIGHTS
        protective_kwargs = {}
        if sampling_profile == "freeze_protective":
            protective_kwargs = {
                "be_trigger_r": weighted_choice(rng, weights["be_trigger_r"]),
                "be_lock_r": weighted_choice(rng, weights["be_lock_r"]),
                "trail_atr_mult": weighted_choice(rng, weights["trail_atr_mult"]),
                "trail_trigger_r": weighted_choice(rng, weights["trail_trigger_r"]),
            }
        return ContractCandidate(
            symbol=symbol,
            allowed_regimes=weighted_choice(rng, weights["allowed_regimes"]),
            breakout_n=weighted_choice(rng, weights["breakout_n"]),
            atr_n=weighted_choice(rng, weights["atr_n"]),
            stop_atr_k=weighted_choice(rng, weights["stop_atr_k"]),
            tp_r_multiple=weighted_choice(rng, weights["tp_r_multiple"]),
            max_hold_bars=weighted_choice(rng, weights["max_hold_bars"]),
            risk_per_trade=weighted_choice(rng, weights["risk_per_trade"]),
            leverage_cap=weighted_choice(rng, weights["leverage_cap"]),
            cooldown_bars=weighted_choice(rng, weights["cooldown_bars"]),
            fee_bps=5.0,
            slippage_bps=2.0,
            funding_bps_per_8h=1.0,
            **protective_kwargs,
        )
    if sampling_profile == "freeze_dense":
        return ContractCandidate(
            symbol=symbol,
            allowed_regimes=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["allowed_regimes"]),
            breakout_n=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["breakout_n"]),
            atr_n=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["atr_n"]),
            stop_atr_k=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["stop_atr_k"]),
            tp_r_multiple=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["tp_r_multiple"]),
            max_hold_bars=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["max_hold_bars"]),
            risk_per_trade=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["risk_per_trade"]),
            leverage_cap=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["leverage_cap"]),
            cooldown_bars=weighted_choice(rng, FREEZE_DENSE_WEIGHTS["cooldown_bars"]),
            fee_bps=5.0,
            slippage_bps=2.0,
            funding_bps_per_8h=1.0,
        )
    if sampling_profile != "standard":
        raise ValueError(f"unknown sampling_profile: {sampling_profile}")
    return ContractCandidate(
        symbol=symbol,
        allowed_regimes=rng.choice(REGIME_CHOICES),
        breakout_n=rng.choice([12, 24, 48, 96, 168]),
        atr_n=rng.choice([14, 24, 48]),
        stop_atr_k=rng.choice([1.0, 1.5, 2.0, 2.5, 3.0]),
        tp_r_multiple=rng.choice([1.5, 2.0, 2.5, 3.0]),
        max_hold_bars=rng.choice([12, 24, 48, 96]),
        risk_per_trade=rng.choice([0.0025, 0.005, 0.0075, 0.01]),
        leverage_cap=rng.choice([1.0, 2.0, 3.0]),
        cooldown_bars=rng.choice([0, 6, 12, 24]),
        fee_bps=5.0,
        slippage_bps=2.0,
        funding_bps_per_8h=1.0,
    )


def signal_thresholds(cfg: SearchConfig) -> tuple[int, int, int | None]:
    if cfg.sampling_profile == "freeze_bear_fade":
        min_train = 200 if cfg.min_signals_train is None else cfg.min_signals_train
        min_fold = 30 if cfg.min_signals_per_fold is None else cfg.min_signals_per_fold
        max_train = 8000 if cfg.max_signals_train is None else cfg.max_signals_train
        return min_train, min_fold, max_train
    if cfg.sampling_profile == "freeze_pullback":
        min_train = 700 if cfg.min_signals_train is None else cfg.min_signals_train
        min_fold = 120 if cfg.min_signals_per_fold is None else cfg.min_signals_per_fold
        max_train = 8000 if cfg.max_signals_train is None else cfg.max_signals_train
        return min_train, min_fold, max_train
    if cfg.sampling_profile == "freeze_distributed":
        min_train = 700 if cfg.min_signals_train is None else cfg.min_signals_train
        min_fold = 120 if cfg.min_signals_per_fold is None else cfg.min_signals_per_fold
        max_train = 6000 if cfg.max_signals_train is None else cfg.max_signals_train
        return min_train, min_fold, max_train
    if is_balanced_derived_profile(cfg.sampling_profile):
        min_train = 600 if cfg.min_signals_train is None else cfg.min_signals_train
        min_fold = 100 if cfg.min_signals_per_fold is None else cfg.min_signals_per_fold
        max_train = 4000 if cfg.max_signals_train is None else cfg.max_signals_train
        return min_train, min_fold, max_train
    if cfg.sampling_profile == "freeze_dense":
        min_train = 240 if cfg.min_signals_train is None else cfg.min_signals_train
        min_fold = 25 if cfg.min_signals_per_fold is None else cfg.min_signals_per_fold
        max_train = 4000 if cfg.max_signals_train is None else cfg.max_signals_train
        return min_train, min_fold, max_train
    min_train = 0 if cfg.min_signals_train is None else cfg.min_signals_train
    min_fold = 0 if cfg.min_signals_per_fold is None else cfg.min_signals_per_fold
    max_train = cfg.max_signals_train
    return min_train, min_fold, max_train


def signal_distribution_metrics(features: pd.DataFrame, signals: pd.Series) -> dict[str, Any]:
    signal_rows = features.loc[signals, ["dt"]].copy()
    if signal_rows.empty:
        return {"max_month_signal_share": 0.0, "median_signal_interval_bars": None}
    months = signal_rows["dt"].dt.strftime("%Y-%m")
    max_month_share = float(months.value_counts(normalize=True).max())
    indexes = list(signal_rows.index)
    intervals = [right - left for left, right in zip(indexes, indexes[1:])]
    median_interval = float(pd.Series(intervals).median()) if intervals else None
    return {
        "max_month_signal_share": max_month_share,
        "median_signal_interval_bars": median_interval,
    }


def signal_prescreen(bars: pd.DataFrame, candidate: ContractCandidate, cfg: SearchConfig) -> tuple[dict[str, Any], str | None]:
    features = prepare_features(bars, candidate)
    signals = features["entry_signal"].fillna(False).astype(bool)
    total = int(signals.sum())
    n = len(signals)
    fold_counts = []
    for fold in range(3):
        lo = int(fold * n / 3)
        hi = int((fold + 1) * n / 3)
        fold_counts.append(int(signals.iloc[lo:hi].sum()))
    min_train, min_fold, max_train = signal_thresholds(cfg)
    payload = {
        "signal_count": total,
        "signal_counts_by_fold": fold_counts,
        "min_signal_count_by_fold": min(fold_counts) if fold_counts else 0,
        **signal_distribution_metrics(features, signals),
        "thresholds": {
            "min_signals_train": min_train,
            "min_signals_per_fold": min_fold,
            "max_signals_train": max_train,
            "max_month_signal_share": 0.15 if is_balanced_derived_profile(cfg.sampling_profile) else None,
            "min_median_signal_interval_bars": 2 if is_balanced_derived_profile(cfg.sampling_profile) else None,
        },
    }
    if total < min_train:
        return payload, "signals_below_min_train"
    if max_train is not None and total > max_train:
        return payload, "signals_above_max_train"
    if fold_counts and min(fold_counts) < min_fold:
        return payload, "signals_below_min_fold"
    if is_balanced_derived_profile(cfg.sampling_profile):
        if payload["max_month_signal_share"] > 0.15:
            return payload, "signals_monthly_concentration"
        median_interval = payload["median_signal_interval_bars"]
        if median_interval is not None and median_interval < 2:
            return payload, "signals_interval_too_dense"
    return payload, None


def compact_result(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in {"trades", "equity_curve"}}


def clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def top_profit_share(trades: list[dict[str, Any]], net_pnl: float, top_n: int = 5) -> float:
    if net_pnl <= 0:
        return float("inf")
    winners = sorted((float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) > 0), reverse=True)
    return float(sum(winners[:top_n]) / net_pnl)


def p5_proxy_net_pnl(trades: list[dict[str, Any]]) -> float:
    pnls = [float(t["net_pnl"]) for t in trades]
    n = len(pnls)
    if n == 0:
        return 0.0
    series = pd.Series(pnls)
    mean = float(series.mean())
    std = float(series.std(ddof=1)) if n > 1 else 0.0
    return float(n * (mean - 1.645 * std / (n**0.5)))


def fold_profit_metrics(summary: dict[str, Any]) -> dict[str, float]:
    folds = summary.get("folds", [])
    total = float(summary.get("net_pnl", 0.0))
    k = max(1, len(folds))
    if total <= 0 or not folds:
        return {"min_fold_share": -1.0, "max_fold_profit_share": 1.0, "fold_pen": 0.0}
    shares = [float(f["net_pnl"]) / total for f in folds]
    max_share = max(shares)
    concentration_pen = clip(1.0 - (max_share - 1.0 / k) / (1.0 - 1.0 / k)) if k > 1 else 1.0
    min_share_pen = clip(min(shares) / 0.10)
    return {
        "min_fold_share": float(min(shares)),
        "max_fold_profit_share": float(max_share),
        "fold_pen": float(min(concentration_pen, min_share_pen)),
    }


def freeze_proxy_metrics(
    base: dict[str, Any],
    cost2: dict[str, Any],
    gate_score: float,
    bootstrap_iterations: int = 200,
) -> dict[str, Any]:
    trades = cost2.get("trades", [])
    n_trades = len(trades)
    initial = float(cost2.get("initial_equity", 10_000.0) or 10_000.0)
    if bootstrap_iterations > 0:
        p5_proxy = bootstrap_net_pnl_p5(trades, iterations=bootstrap_iterations, block=10, seed=20260706)
        p5_method = f"block_bootstrap_{bootstrap_iterations}"
    else:
        p5_proxy = p5_proxy_net_pnl(trades)
        p5_method = "normal_approx"
    p5_target = max(1.0, initial * 0.05)
    underwater_days = max_underwater_days(cost2.get("equity_curve", []))
    fold_metrics = fold_profit_metrics(cost2)
    top5_share = top_profit_share(trades, float(cost2.get("net_pnl", 0.0)))

    if n_trades < 30:
        score = 0.0
    else:
        trades_pen = clip(n_trades / 150.0)
        uw_pen = clip((1460.0 - underwater_days) / 730.0)
        top5_pen = clip((0.80 - top5_share) / 0.40)
        fold_pen = clip(fold_metrics["min_fold_share"] / 0.10)
        p5_pen = clip(p5_proxy / p5_target) if p5_proxy > 0 else 0.0
        score = max(0.0, float(gate_score)) * trades_pen * uw_pen * fold_pen * top5_pen * p5_pen
    return {
        "score": float(score),
        "p5_proxy_net_pnl": float(p5_proxy),
        "p5_proxy_method": p5_method,
        "p5_target": float(p5_target),
        "max_underwater_days": int(underwater_days),
        "top5_profit_share": float(top5_share),
        **fold_metrics,
    }


def distribution_hard_rejection(cost2: dict[str, Any], cfg: SearchConfig) -> str | None:
    if cfg.min_hard_trades is not None and int(cost2.get("trade_count", 0)) < cfg.min_hard_trades:
        return "hard_trades_below_min"
    if float(cost2.get("net_pnl", 0.0)) <= 0.0:
        return "hard_net_pnl_nonpositive"
    if not cfg.freeze_distribution_hard_gate:
        return None
    margin = float(cfg.freeze_gate_margin)
    top5_limit = FREEZE_TOP5_PROFIT_SHARE_LIMIT * margin
    underwater_limit = int(FREEZE_UNDERWATER_DAYS_LIMIT * margin)
    top5_share = top_profit_share(cost2.get("trades", []), float(cost2.get("net_pnl", 0.0)))
    if top5_share > top5_limit:
        return "hard_top5_profit_share"
    underwater_days = max_underwater_days(cost2.get("equity_curve", []))
    if underwater_days > underwater_limit:
        return "hard_max_underwater_days"
    return None


def exposure_matched_buy_hold_net_pnl(
    bars: pd.DataFrame,
    initial_equity: float,
    exposure_ratio: float,
    side: str = "long",
) -> float:
    if bars.empty:
        return 0.0
    first = float(bars["close"].iloc[0])
    last = float(bars["close"].iloc[-1])
    if first <= 0:
        return 0.0
    direction = -1.0 if side == "short" else 1.0
    return float(direction * initial_equity * (last / first - 1.0) * max(0.0, float(exposure_ratio)))


def distribution_diagnostics(
    candidate: ContractCandidate,
    cost2: dict[str, Any],
    rejection: str | None,
    full_exposure_buy_hold_net_pnl: float | None = None,
) -> dict[str, Any]:
    exposure = float(cost2.get("exposure_bar_ratio", 0.0))
    exposure_benchmark = float(full_exposure_buy_hold_net_pnl or 0.0) * exposure
    net_pnl = float(cost2.get("net_pnl", 0.0))
    scales = [float(t.get("risk_scale", 1.0)) for t in cost2.get("trades", [])]
    scale_series = pd.Series(scales)
    scale_min = float(candidate.scale_min)
    scale_max = float(candidate.scale_max)
    return {
        "candidate_id": candidate.candidate_id(),
        "family": candidate.family,
        "vol_scaling": candidate.vol_scaling,
        "trade_count": int(cost2.get("trade_count", 0)),
        "net_pnl": net_pnl,
        "exposure_bar_ratio": exposure,
        "exposure_matched_buy_hold_net_pnl": exposure_benchmark,
        "net_pnl_minus_exposure_benchmark": float(net_pnl - exposure_benchmark),
        "top5_profit_share": float(top_profit_share(cost2.get("trades", []), net_pnl)),
        "max_underwater_days": int(max_underwater_days(cost2.get("equity_curve", []))),
        "median_risk_scale": float(scale_series.median()) if scales else None,
        "scale_min_clamp_share": float(sum(s <= scale_min + 1e-12 for s in scales) / len(scales)) if scales else None,
        "scale_max_clamp_share": float(sum(s >= scale_max - 1e-12 for s in scales) / len(scales)) if scales else None,
        "distribution_rejection": rejection,
    }


def pullback_soft_score(cost2: dict[str, Any], cfg: SearchConfig) -> float:
    top5 = top_profit_share(cost2.get("trades", []), float(cost2.get("net_pnl", 0.0)))
    underwater = max_underwater_days(cost2.get("equity_curve", []))
    min_trades = float(cfg.min_hard_trades or 504)
    net_score = clip(float(cost2.get("net_pnl", 0.0)) / PULLBACK_NET2_TARGET)
    top5_margin = clip((FREEZE_TOP5_PROFIT_SHARE_LIMIT - top5) / FREEZE_TOP5_PROFIT_SHARE_LIMIT)
    underwater_margin = clip((FREEZE_UNDERWATER_DAYS_LIMIT - underwater) / FREEZE_UNDERWATER_DAYS_LIMIT)
    trade_count_margin = clip(float(cost2.get("trade_count", 0)) / max(min_trades * 2.0, 1.0))
    return float(0.35 * net_score + 0.25 * top5_margin + 0.25 * underwater_margin + 0.15 * trade_count_margin)


def distribution_soft_score(cost2: dict[str, Any], cfg: SearchConfig) -> float:
    top5 = top_profit_share(cost2.get("trades", []), float(cost2.get("net_pnl", 0.0)))
    underwater = max_underwater_days(cost2.get("equity_curve", []))
    min_trades = float(cfg.min_hard_trades or 150)
    net_score = clip(float(cost2.get("net_pnl", 0.0)) / PULLBACK_NET2_TARGET)
    top5_score = clip((FREEZE_TOP5_PROFIT_SHARE_LIMIT - top5) / FREEZE_TOP5_PROFIT_SHARE_LIMIT)
    underwater_score = clip((FREEZE_UNDERWATER_DAYS_LIMIT - underwater) / FREEZE_UNDERWATER_DAYS_LIMIT)
    trade_score = clip(float(cost2.get("trade_count", 0)) / max(min_trades * 2.0, 1.0))
    return float(0.40 * net_score + 0.30 * top5_score + 0.20 * underwater_score + 0.10 * trade_score)


def sort_rows(rows: list[dict[str, Any]], ranking_mode: str) -> None:
    if ranking_mode == "freeze_proxy":
        rows.sort(key=lambda r: (float(r.get("ranking_score", 0.0)), bool(r["gates"]["passed"]), float(r["gates"]["score"])), reverse=True)
    else:
        rows.sort(key=lambda r: (bool(r["gates"]["passed"]), float(r["gates"]["score"])), reverse=True)


def run_search(cfg: SearchConfig) -> dict[str, Any]:
    symbol = cfg.symbol.upper()
    if cfg.ranking_mode not in {"train_gate", "freeze_proxy"}:
        raise SystemExit(f"unknown ranking_mode: {cfg.ranking_mode}")
    if cfg.sampling_profile not in {
        "standard",
        "freeze_dense",
        "freeze_balanced",
        "freeze_protective",
        "freeze_distributed",
        "freeze_pullback",
        "freeze_bear_fade",
    }:
        raise SystemExit(f"unknown sampling_profile: {cfg.sampling_profile}")
    train_start = utc_ts(cfg.train_start)
    train_end = utc_ts(cfg.train_end)
    embargo_start = utc_ts(cfg.embargo_start)
    bars = load_symbol_1h(Path(cfg.cache_dir), symbol, train_start, train_end, embargo_start)
    labels = load_regime_labels(Path(cfg.regime_labels_dir) / f"regime_labels_{symbol}.parquet", embargo_start)
    bars = attach_regimes(bars, labels)
    buy_hold_by_side = {
        "long": exposure_matched_buy_hold_net_pnl(bars, 10_000.0, 1.0, "long"),
        "short": exposure_matched_buy_hold_net_pnl(bars, 10_000.0, 1.0, "short"),
    }

    rng = random.Random(cfg.seed)
    seen: set[str] = set()
    rows = []
    evaluated_distribution: list[dict[str, Any]] = []
    attempts = 0
    rejections: Counter[str] = Counter()
    attempt_limit = cfg.max_attempts if cfg.max_attempts is not None else cfg.samples * 50
    while len(rows) < cfg.samples and attempts < attempt_limit:
        attempts += 1
        candidate = random_candidate(symbol, rng, cfg.sampling_profile)
        if cfg.sampling_profile == "freeze_dense":
            combo_reject = dense_combo_rejection(candidate)
            if combo_reject:
                rejections[combo_reject] += 1
                continue
        if cfg.sampling_profile == "freeze_distributed":
            combo_reject = distributed_combo_rejection(candidate)
            if combo_reject:
                rejections[combo_reject] += 1
                continue
        if cfg.sampling_profile == "freeze_pullback":
            combo_reject = pullback_combo_rejection(candidate)
            if combo_reject:
                rejections[combo_reject] += 1
                continue
        if cfg.sampling_profile == "freeze_bear_fade":
            combo_reject = bear_fade_combo_rejection(candidate)
            if combo_reject:
                rejections[combo_reject] += 1
                continue
        if cfg.sampling_profile in {"freeze_balanced", "freeze_protective"}:
            combo_reject = balanced_combo_rejection(candidate)
            if combo_reject:
                rejections[combo_reject] += 1
                continue
        cid = candidate.candidate_id()
        if cid in seen:
            rejections["duplicate_candidate"] += 1
            continue
        seen.add(cid)
        prescreen, prescreen_reject = signal_prescreen(bars, candidate, cfg)
        if prescreen_reject:
            rejections[prescreen_reject] += 1
            continue
        keep_trades = cfg.ranking_mode == "freeze_proxy" or cfg.freeze_distribution_hard_gate or cfg.min_hard_trades is not None
        base = simulate_candidate(bars, candidate, cost_multiplier=1.0, include_trades=keep_trades)
        cost2 = simulate_candidate(bars, candidate, cost_multiplier=2.0, include_trades=keep_trades)
        distribution_reject = distribution_hard_rejection(cost2, cfg)
        if keep_trades:
            evaluated_distribution.append(distribution_diagnostics(candidate, cost2, distribution_reject, buy_hold_by_side[candidate.side]))
        if distribution_reject:
            rejections[distribution_reject] += 1
            continue
        gates = evaluate_gates(base, cost2, GateConfig())
        ranking_score = float(gates["score"])
        freeze_proxy = None
        if cfg.ranking_mode == "freeze_proxy":
            freeze_proxy = freeze_proxy_metrics(base, cost2, ranking_score, bootstrap_iterations=cfg.proxy_bootstrap_iterations)
            ranking_score = float(freeze_proxy["score"])
            if cfg.sampling_profile == "freeze_pullback":
                ranking_score = pullback_soft_score(cost2, cfg)
            if cfg.sampling_profile == "freeze_bear_fade":
                ranking_score = distribution_soft_score(cost2, cfg)
        rows.append(
            {
                "candidate_id": cid,
                "candidate": candidate.to_dict(),
                "base": compact_result(base),
                "cost2": compact_result(cost2),
                "gates": gates,
                "ranking_score": ranking_score,
                "freeze_proxy": freeze_proxy,
                "signal_prescreen": prescreen,
            }
        )

    sort_rows(rows, cfg.ranking_mode)
    failure_counts = Counter()
    for row in rows:
        failure_counts.update(row["gates"]["failures"])
    best = rows[0] if rows else None
    payload = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "kind": "contract_lab_v9_train_only_search",
        "symbol": symbol,
        "train_window": {"start": train_start.isoformat(), "end": train_end.isoformat()},
        "embargo_start": embargo_start.isoformat(),
        "config": cfg.__dict__,
        "summary": {
            "sampled": len(rows),
            "attempts": attempts,
            "attempt_limit": attempt_limit,
            "accepted_rate": (len(rows) / attempts) if attempts else 0.0,
            "gate_passed": sum(1 for r in rows if r["gates"]["passed"]),
            "best_score": best["gates"]["score"] if best else None,
            "best_ranking_score": best["ranking_score"] if best else None,
            "best_candidate_id": best["candidate_id"] if best else None,
            "failure_counts": dict(failure_counts),
            "rejection_counts": dict(rejections),
        },
        "distribution_diagnostics": evaluated_distribution,
        "top": rows[:25],
        "candidates": rows,
    }
    write_json(payload, Path(cfg.out_json))
    write_markdown(payload, Path(cfg.out_md))
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run v9 train-only contract-style strategy search")
    ap.add_argument("--symbol", default="LINKUSDT")
    ap.add_argument("--samples", type=int, default=250)
    ap.add_argument("--seed", type=int, default=20260706)
    ap.add_argument("--train-start", default="2017-08-01")
    ap.add_argument("--train-end", default="2024-06-30 23:59:59")
    ap.add_argument("--embargo-start", default="2024-07-01")
    ap.add_argument("--cache-dir", default="data/binance_public_cache")
    ap.add_argument("--regime-labels-dir", default="artifacts/v9")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-md", default="")
    ap.add_argument("--ranking-mode", choices=["train_gate", "freeze_proxy"], default="train_gate")
    ap.add_argument("--proxy-bootstrap-iterations", type=int, default=200)
    ap.add_argument(
        "--sampling-profile",
        choices=[
            "standard",
            "freeze_dense",
            "freeze_balanced",
            "freeze_protective",
            "freeze_distributed",
            "freeze_pullback",
            "freeze_bear_fade",
        ],
        default="standard",
    )
    ap.add_argument("--min-signals-train", type=int, default=None)
    ap.add_argument("--min-signals-per-fold", type=int, default=None)
    ap.add_argument("--max-signals-train", type=int, default=None)
    ap.add_argument("--freeze-distribution-hard-gate", action="store_true")
    ap.add_argument("--freeze-gate-margin", type=float, default=0.90)
    ap.add_argument("--min-hard-trades", type=int, default=None)
    ap.add_argument("--max-attempts", type=int, default=None)
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    symbol = args.symbol.upper()
    out_json = args.out_json or f"artifacts/v9/contract_lab/contract_search_{symbol}_train.json"
    out_md = args.out_md or f"artifacts/v9/contract_lab/contract_search_{symbol}_train.md"
    cfg = SearchConfig(
        symbol=symbol,
        samples=args.samples,
        seed=args.seed,
        train_start=args.train_start,
        train_end=args.train_end,
        embargo_start=args.embargo_start,
        cache_dir=args.cache_dir,
        regime_labels_dir=args.regime_labels_dir,
        out_json=out_json,
        out_md=out_md,
        ranking_mode=args.ranking_mode,
        proxy_bootstrap_iterations=args.proxy_bootstrap_iterations,
        sampling_profile=args.sampling_profile,
        min_signals_train=args.min_signals_train,
        min_signals_per_fold=args.min_signals_per_fold,
        max_signals_train=args.max_signals_train,
        freeze_distribution_hard_gate=args.freeze_distribution_hard_gate,
        freeze_gate_margin=args.freeze_gate_margin,
        min_hard_trades=args.min_hard_trades,
        max_attempts=args.max_attempts,
    )
    started = time.time()
    payload = run_search(cfg)
    print(
        "contract_lab_v9 done "
        f"symbol={payload['symbol']} sampled={payload['summary']['sampled']} "
        f"passed={payload['summary']['gate_passed']} elapsed_sec={time.time() - started:.2f}"
    )
    print(out_json)
    print(out_md)


if __name__ == "__main__":
    main()
