from __future__ import annotations

import sys
from pathlib import Path
import random

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.search import (  # noqa: E402
    FREEZE_BALANCED_WEIGHTS,
    FREEZE_BEAR_FADE_WEIGHTS,
    FREEZE_DENSE_WEIGHTS,
    FREEZE_DISTRIBUTED_WEIGHTS,
    FREEZE_PULLBACK_WEIGHTS,
    FREEZE_PROTECTIVE_WEIGHTS,
    SearchConfig,
    bear_fade_combo_rejection,
    balanced_combo_rejection,
    dense_combo_rejection,
    distributed_combo_rejection,
    distribution_hard_rejection,
    distribution_soft_score,
    exposure_matched_buy_hold_net_pnl,
    freeze_proxy_metrics,
    pullback_combo_rejection,
    pullback_soft_score,
    random_candidate,
    signal_prescreen,
    signal_thresholds,
    sort_rows,
    weighted_choice,
)
from v9.contract.schema import ContractCandidate  # noqa: E402


def trade(idx: int, pnl: float = 10.0) -> dict:
    return {
        "entry_time": f"2020-01-{idx % 28 + 1:02d}T01:00:00+00:00",
        "exit_time": f"2020-01-{idx % 28 + 1:02d}T05:00:00+00:00",
        "net_pnl": pnl,
        "r_multiple": pnl / 10.0,
    }


def summary(trades: list[dict], underwater: bool = False) -> dict:
    net = sum(float(t["net_pnl"]) for t in trades)
    curve = [
        {"dt": "2020-01-01T00:00:00+00:00", "equity": 10_000.0},
        {"dt": "2020-02-01T00:00:00+00:00", "equity": 10_000.0 + net},
    ]
    if underwater:
        curve = [
            {"dt": "2020-01-01T00:00:00+00:00", "equity": 10_000.0},
            {"dt": "2020-02-01T00:00:00+00:00", "equity": 9_000.0},
            {"dt": "2023-02-01T00:00:00+00:00", "equity": 9_500.0},
            {"dt": "2023-03-01T00:00:00+00:00", "equity": 10_000.0 + net},
        ]
    return {
        "initial_equity": 10_000.0,
        "net_pnl": net,
        "trade_count": len(trades),
        "trades": trades,
        "equity_curve": curve,
        "folds": [
            {"fold": 0, "net_pnl": net * 0.30},
            {"fold": 1, "net_pnl": net * 0.35},
            {"fold": 2, "net_pnl": net * 0.35},
        ],
    }


def test_freeze_proxy_is_zero_for_too_few_trades() -> None:
    cost2 = summary([trade(i) for i in range(10)])
    result = freeze_proxy_metrics(cost2, cost2, gate_score=1.0)
    assert result["score"] == 0.0


def test_freeze_proxy_penalizes_long_underwater_period() -> None:
    trades = [trade(i) for i in range(80)]
    normal = freeze_proxy_metrics(summary(trades), summary(trades), gate_score=1.0)
    underwater = freeze_proxy_metrics(summary(trades, underwater=True), summary(trades, underwater=True), gate_score=1.0)
    assert normal["score"] > 0.0
    assert underwater["score"] < normal["score"]
    assert underwater["max_underwater_days"] > 730


def test_freeze_proxy_zero_when_p5_proxy_negative() -> None:
    trades = [trade(i, 1.0) for i in range(60)] + [trade(99, -200.0)]
    result = freeze_proxy_metrics(summary(trades), summary(trades), gate_score=1.0)
    assert result["p5_proxy_net_pnl"] <= 0.0
    assert result["score"] == 0.0


def test_distribution_hard_rejection_blocks_low_trade_count() -> None:
    cost2 = summary([trade(i) for i in range(10)])
    cfg = SearchConfig(min_hard_trades=20)
    assert distribution_hard_rejection(cost2, cfg) == "hard_trades_below_min"


def test_distribution_hard_rejection_blocks_nonpositive_net_pnl_before_concentration() -> None:
    cost2 = summary([trade(i, -10.0) for i in range(100)])
    cfg = SearchConfig(freeze_distribution_hard_gate=True, min_hard_trades=20)
    assert distribution_hard_rejection(cost2, cfg) == "hard_net_pnl_nonpositive"


def test_exposure_matched_buy_hold_net_pnl_scales_with_exposure() -> None:
    bars = pd.DataFrame({"close": [100.0, 150.0]})
    assert exposure_matched_buy_hold_net_pnl(bars, 10_000.0, 1.0) == 5_000.0
    assert exposure_matched_buy_hold_net_pnl(bars, 10_000.0, 0.25) == 1_250.0


def test_distribution_hard_rejection_blocks_top_trade_concentration() -> None:
    trades = [trade(i, 100.0) for i in range(5)] + [trade(i + 10, 1.0) for i in range(100)]
    cost2 = summary(trades)
    cfg = SearchConfig(freeze_distribution_hard_gate=True, freeze_gate_margin=0.90)
    assert distribution_hard_rejection(cost2, cfg) == "hard_top5_profit_share"


def test_distribution_hard_rejection_blocks_long_underwater_period() -> None:
    trades = [trade(i, 10.0) for i in range(100)]
    cost2 = summary(trades, underwater=True)
    cfg = SearchConfig(freeze_distribution_hard_gate=True, freeze_gate_margin=0.90)
    assert distribution_hard_rejection(cost2, cfg) == "hard_max_underwater_days"


def test_sort_rows_uses_freeze_proxy_ranking_score_when_requested() -> None:
    rows = [
        {"candidate_id": "a", "ranking_score": 0.1, "gates": {"passed": True, "score": 10.0}},
        {"candidate_id": "b", "ranking_score": 0.9, "gates": {"passed": False, "score": 0.1}},
    ]
    sort_rows(rows, "freeze_proxy")
    assert [r["candidate_id"] for r in rows] == ["b", "a"]


def test_sort_rows_train_gate_preserves_gate_first_order() -> None:
    rows = [
        {"candidate_id": "a", "ranking_score": 100.0, "gates": {"passed": False, "score": 100.0}},
        {"candidate_id": "b", "ranking_score": 0.1, "gates": {"passed": True, "score": 0.1}},
    ]
    sort_rows(rows, "train_gate")
    assert [r["candidate_id"] for r in rows] == ["b", "a"]


def test_freeze_dense_weights_exclude_breakout_168_and_are_positive() -> None:
    values = [value for value, weight in FREEZE_DENSE_WEIGHTS["breakout_n"] if weight > 0]
    assert 168 not in values
    for choices in FREEZE_DENSE_WEIGHTS.values():
        assert abs(sum(weight for _, weight in choices) - 1.0) < 1e-12
    for choices in FREEZE_BALANCED_WEIGHTS.values():
        assert abs(sum(weight for _, weight in choices) - 1.0) < 1e-12
    for choices in FREEZE_PROTECTIVE_WEIGHTS.values():
        assert abs(sum(weight for _, weight in choices) - 1.0) < 1e-12
    for choices in FREEZE_DISTRIBUTED_WEIGHTS.values():
        assert abs(sum(weight for _, weight in choices) - 1.0) < 1e-12
    for choices in FREEZE_PULLBACK_WEIGHTS.values():
        assert abs(sum(weight for _, weight in choices) - 1.0) < 1e-12
    for choices in FREEZE_BEAR_FADE_WEIGHTS.values():
        assert abs(sum(weight for _, weight in choices) - 1.0) < 1e-12


def test_freeze_dense_sampling_is_seeded_and_avoids_combo_rejections() -> None:
    left_rng = random.Random(123)
    right_rng = random.Random(123)
    left = [random_candidate("LINKUSDT", left_rng, "freeze_dense").candidate_id() for _ in range(20)]
    right = [random_candidate("LINKUSDT", right_rng, "freeze_dense").candidate_id() for _ in range(20)]
    assert left == right

    rng = random.Random(7)
    accepted = []
    for _ in range(1000):
        candidate = random_candidate("LINKUSDT", rng, "freeze_dense")
        if dense_combo_rejection(candidate) is None:
            accepted.append(candidate)
    assert len(accepted) > 200
    assert all(dense_combo_rejection(candidate) is None for candidate in accepted)


def test_dense_combo_rejection_rules() -> None:
    assert dense_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=96, cooldown_bars=12)
    ) == "breakout96_cooldown_ge12"
    assert dense_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=48, max_hold_bars=12)
    ) == "slow_breakout_short_hold"
    assert dense_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", tp_r_multiple=2.5, stop_atr_k=2.5)
    ) == "wide_stop_high_target"


def test_freeze_balanced_sampling_avoids_known_attractor() -> None:
    rng = random.Random(8)
    accepted = []
    for _ in range(1000):
        candidate = random_candidate("LINKUSDT", rng, "freeze_balanced")
        if balanced_combo_rejection(candidate) is None:
            accepted.append(candidate)
    assert len(accepted) > 200
    assert all(candidate.cooldown_bars > 0 for candidate in accepted)
    assert all(balanced_combo_rejection(candidate) is None for candidate in accepted)
    assert all(candidate.be_trigger_r is None and candidate.trail_atr_mult is None for candidate in accepted)


def test_freeze_protective_sampling_can_enable_new_exit_genes() -> None:
    rng = random.Random(9)
    accepted = []
    for _ in range(1000):
        candidate = random_candidate("LINKUSDT", rng, "freeze_protective")
        if balanced_combo_rejection(candidate) is None:
            accepted.append(candidate)
    assert len(accepted) > 200
    assert any(candidate.be_trigger_r is not None or candidate.trail_atr_mult is not None for candidate in accepted)


def test_freeze_distributed_sampling_is_seeded_and_avoids_combo_rejections() -> None:
    left_rng = random.Random(1234)
    right_rng = random.Random(1234)
    left = [random_candidate("LINKUSDT", left_rng, "freeze_distributed").candidate_id() for _ in range(20)]
    right = [random_candidate("LINKUSDT", right_rng, "freeze_distributed").candidate_id() for _ in range(20)]
    assert left == right

    rng = random.Random(10)
    accepted = []
    for _ in range(1000):
        candidate = random_candidate("LINKUSDT", rng, "freeze_distributed")
        if distributed_combo_rejection(candidate) is None:
            accepted.append(candidate)
    assert len(accepted) > 500
    assert all(distributed_combo_rejection(candidate) is None for candidate in accepted)
    assert any("deep_drawdown" in candidate.allowed_regimes for candidate in accepted)
    assert any(candidate.vol_scaling != "none" for candidate in accepted)


def test_freeze_distributed_combo_rejection_rules() -> None:
    assert distributed_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=8, cooldown_bars=6)
    ) == "cooldown_gt_half_breakout"
    assert distributed_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=20, max_hold_bars=36)
    ) == "slow_breakout_short_hold"
    assert distributed_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=20, allowed_regimes=("up_normal", "up_high_vol"))
    ) == "strict_regime_slow_breakout"
    assert distributed_combo_rejection(
        ContractCandidate(
            symbol="LINKUSDT",
            allowed_regimes=("deep_drawdown", "range_normal", "up_high_vol", "up_normal"),
            stop_atr_k=1.75,
            tp_r_multiple=2.2,
        )
    ) == "wide_stop_high_target"
    assert distributed_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=8, cooldown_bars=0, risk_per_trade=0.0075, leverage_cap=4)
    ) == "high_freq_high_risk"


def test_freeze_pullback_sampling_is_seeded_and_avoids_combo_rejections() -> None:
    left_rng = random.Random(4321)
    right_rng = random.Random(4321)
    left = [random_candidate("LINKUSDT", left_rng, "freeze_pullback").candidate_id() for _ in range(20)]
    right = [random_candidate("LINKUSDT", right_rng, "freeze_pullback").candidate_id() for _ in range(20)]
    assert left == right

    rng = random.Random(11)
    accepted = []
    for _ in range(1000):
        candidate = random_candidate("LINKUSDT", rng, "freeze_pullback")
        if pullback_combo_rejection(candidate) is None:
            accepted.append(candidate)
    assert len(accepted) > 500
    assert all(candidate.family == "pullback_long_v1" for candidate in accepted)
    assert all(candidate.max_hold_bars in {12, 18, 27} for candidate in accepted)
    assert all(pullback_combo_rejection(candidate) is None for candidate in accepted)


def test_freeze_pullback_combo_rejection_rules() -> None:
    assert pullback_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", family="pullback_long_v1", rsi_len=2, max_hold_bars=27)
    ) == "pullback_hold_too_long_for_rsi"
    assert pullback_combo_rejection(
        ContractCandidate(
            symbol="LINKUSDT",
            family="pullback_long_v1",
            rsi_len=4,
            max_hold_bars=12,
            stop_atr_k=1.75,
            tp_r_multiple=1.8,
        )
    ) == "pullback_wide_stop_high_target"
    assert pullback_combo_rejection(
        ContractCandidate(
            symbol="LINKUSDT",
            family="pullback_long_v1",
            rsi_len=4,
            rsi_entry_max=10,
            max_hold_bars=12,
            stop_atr_k=1.0,
            tp_r_multiple=1.0,
            allowed_regimes=("up_normal",),
        )
    ) == "strict_regime_extreme_rsi"


def test_freeze_bear_fade_sampling_is_seeded_and_avoids_combo_rejections() -> None:
    left_rng = random.Random(2222)
    right_rng = random.Random(2222)
    left = [random_candidate("LINKUSDT", left_rng, "freeze_bear_fade").candidate_id() for _ in range(20)]
    right = [random_candidate("LINKUSDT", right_rng, "freeze_bear_fade").candidate_id() for _ in range(20)]
    assert left == right

    rng = random.Random(12)
    accepted = []
    for _ in range(1000):
        candidate = random_candidate("LINKUSDT", rng, "freeze_bear_fade")
        if bear_fade_combo_rejection(candidate) is None:
            accepted.append(candidate)
    assert len(accepted) > 500
    assert all(candidate.family == "bear_rally_fade_short_v1" and candidate.side == "short" for candidate in accepted)
    assert all(bear_fade_combo_rejection(candidate) is None for candidate in accepted)
    assert any(candidate.vol_scaling != "none" for candidate in accepted)


def test_freeze_bear_fade_combo_rejection_rules() -> None:
    assert bear_fade_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", family="bear_rally_fade_short_v1", side="short", target_pct=0.03, stop_pct=0.02)
    ) == "short_target_not_below_stop"
    assert bear_fade_combo_rejection(
        ContractCandidate(
            symbol="LINKUSDT",
            family="bear_rally_fade_short_v1",
            side="short",
            rsi_hi=65,
            allowed_regimes=("deep_drawdown", "range_normal", "up_high_vol", "up_normal"),
        )
    ) == "broad_regime_low_rsi_hi"
    assert bear_fade_combo_rejection(
        ContractCandidate(
            symbol="LINKUSDT",
            family="bear_rally_fade_short_v1",
            side="short",
            max_hold_bars=48,
            target_pct=0.01,
        )
    ) == "long_hold_tiny_target"


def test_pullback_soft_score_rewards_distribution_metrics() -> None:
    cfg = SearchConfig(sampling_profile="freeze_pullback", min_hard_trades=100)
    weak = summary([trade(i, 1.0) for i in range(95)] + [trade(200 + i, 100.0) for i in range(5)])
    strong = summary([trade(i, 10.0) for i in range(200)])
    assert pullback_soft_score(strong, cfg) > pullback_soft_score(weak, cfg)


def test_distribution_soft_score_rewards_better_distribution() -> None:
    cfg = SearchConfig(sampling_profile="freeze_bear_fade", min_hard_trades=100)
    weak = summary([trade(i, 1.0) for i in range(95)] + [trade(200 + i, 100.0) for i in range(5)])
    strong = summary([trade(i, 10.0) for i in range(200)])
    assert distribution_soft_score(strong, cfg) > distribution_soft_score(weak, cfg)


def test_legacy_candidate_hash_is_stable_with_default_protective_stop_genes() -> None:
    candidate = ContractCandidate(
        symbol="LINKUSDT",
        allowed_regimes=("up_normal",),
        atr_n=28,
        breakout_n=32,
        cooldown_bars=4,
        leverage_cap=1.0,
        max_hold_bars=36,
        risk_per_trade=0.005,
        stop_atr_k=2.5,
        tp_r_multiple=2.0,
    )
    assert candidate.candidate_id() == "bf7919c368e63524"


def test_candidate_hash_ignores_inactive_protective_stop_params() -> None:
    base = ContractCandidate(symbol="LINKUSDT")
    inactive_be = ContractCandidate(symbol="LINKUSDT", be_trigger_r=None, be_lock_r=0.25)
    inactive_trail = ContractCandidate(symbol="LINKUSDT", trail_atr_mult=None, trail_trigger_r=1.5)
    assert inactive_be.candidate_id() == base.candidate_id()
    assert inactive_trail.candidate_id() == base.candidate_id()


def test_candidate_hash_ignores_inactive_regime_drawdown_filter() -> None:
    base = ContractCandidate(symbol="LINKUSDT")
    inactive = ContractCandidate(symbol="LINKUSDT", max_regime_drawdown_1y=None)
    active = ContractCandidate(symbol="LINKUSDT", max_regime_drawdown_1y=0.25)
    assert inactive.candidate_id() == base.candidate_id()
    assert active.candidate_id() != base.candidate_id()


def test_candidate_hash_ignores_inactive_pullback_params_for_donchian_family() -> None:
    base = ContractCandidate(symbol="LINKUSDT")
    inactive = ContractCandidate(
        symbol="LINKUSDT",
        trend_ema_len=200,
        rsi_len=4,
        rsi_entry_max=10.0,
        rsi_exit_min=75.0,
    )
    assert inactive.candidate_id() == base.candidate_id()


def test_pullback_candidate_hash_ignores_inactive_breakout_n() -> None:
    base = ContractCandidate(symbol="LINKUSDT", family="pullback_long_v1", breakout_n=12)
    changed = ContractCandidate(symbol="LINKUSDT", family="pullback_long_v1", breakout_n=96)
    assert changed.candidate_id() == base.candidate_id()


def test_donchian_candidate_hash_ignores_inactive_short_params() -> None:
    base = ContractCandidate(symbol="LINKUSDT")
    inactive = ContractCandidate(
        symbol="LINKUSDT",
        regime_len=200,
        slope_len=10,
        rsi_hi=80.0,
        stop_pct=0.05,
        target_pct=0.01,
        short_extra_cost_bps=20.0,
    )
    assert inactive.candidate_id() == base.candidate_id()


def test_candidate_hash_ignores_inactive_vol_scaling_params() -> None:
    base = ContractCandidate(symbol="LINKUSDT")
    inactive = ContractCandidate(
        symbol="LINKUSDT",
        vol_scaling="none",
        vol_lookback_n=200,
        vol_target_ann=1.0,
        scale_min=0.10,
        scale_max=3.0,
    )
    active = ContractCandidate(symbol="LINKUSDT", vol_scaling="inverse_atr", vol_lookback_n=50)
    assert inactive.candidate_id() == base.candidate_id()
    assert active.candidate_id() != base.candidate_id()


def test_bear_fade_candidate_hash_ignores_inactive_long_fields() -> None:
    base = ContractCandidate(symbol="LINKUSDT", family="bear_rally_fade_short_v1", side="short", breakout_n=12, atr_n=7)
    changed = ContractCandidate(symbol="LINKUSDT", family="bear_rally_fade_short_v1", side="short", breakout_n=96, atr_n=48)
    assert changed.candidate_id() == base.candidate_id()


def test_balanced_combo_rejection_rules() -> None:
    assert balanced_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=12, atr_n=48, max_hold_bars=48)
    ) == "fast_breakout_slow_atr_long_hold"
    assert balanced_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", breakout_n=12, atr_n=48, max_hold_bars=24)
    ) == "atr_breakout_ratio_gt_2_5"
    assert balanced_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", atr_n=14, max_hold_bars=36)
    ) == "max_hold_gt_2x_atr"
    assert balanced_combo_rejection(
        ContractCandidate(symbol="LINKUSDT", max_hold_bars=12, tp_r_multiple=3.0, stop_atr_k=1.0)
    ) == "rr_outside_0_8_2_0"


def signal_bars(signal_count: int) -> pd.DataFrame:
    periods = 300
    dt = pd.date_range("2020-01-01", periods=periods, freq="1h", tz="UTC")
    close = [100.0] * periods
    for idx in range(1, min(signal_count + 1, periods)):
        close[idx] = close[idx - 1] + 1.0
    for idx in range(signal_count + 1, periods):
        close[idx] = close[idx - 1]
    return pd.DataFrame(
        {
            "dt": dt,
            "open": close,
            "high": [v + 0.5 for v in close],
            "low": [v - 0.5 for v in close],
            "close": close,
            "regime_id": "up_normal",
            "insufficient_history": False,
        }
    )


def test_signal_prescreen_train_boundary() -> None:
    candidate = ContractCandidate(symbol="LINKUSDT", breakout_n=1, atr_n=1, allowed_regimes=("up_normal",))
    reject_cfg = SearchConfig(sampling_profile="freeze_dense", min_signals_train=240, min_signals_per_fold=0, max_signals_train=None)
    payload, reason = signal_prescreen(signal_bars(239), candidate, reject_cfg)
    assert payload["signal_count"] == 239
    assert reason == "signals_below_min_train"
    payload, reason = signal_prescreen(signal_bars(240), candidate, reject_cfg)
    assert payload["signal_count"] == 240
    assert reason is None


def test_signal_prescreen_balanced_rejects_month_concentration() -> None:
    candidate = ContractCandidate(symbol="LINKUSDT", breakout_n=1, atr_n=1, allowed_regimes=("up_normal",))
    cfg = SearchConfig(
        sampling_profile="freeze_balanced",
        min_signals_train=10,
        min_signals_per_fold=0,
        max_signals_train=None,
    )
    payload, reason = signal_prescreen(signal_bars(20), candidate, cfg)
    assert payload["max_month_signal_share"] > 0.15
    assert reason == "signals_monthly_concentration"


def test_freeze_protective_uses_balanced_signal_thresholds() -> None:
    balanced = signal_thresholds(SearchConfig(sampling_profile="freeze_balanced"))
    protective = signal_thresholds(SearchConfig(sampling_profile="freeze_protective"))
    assert protective == balanced == (600, 100, 4000)


def test_freeze_distributed_uses_higher_signal_thresholds() -> None:
    assert signal_thresholds(SearchConfig(sampling_profile="freeze_distributed")) == (700, 120, 6000)


def test_freeze_pullback_uses_higher_signal_thresholds() -> None:
    assert signal_thresholds(SearchConfig(sampling_profile="freeze_pullback")) == (700, 120, 8000)


def test_freeze_bear_fade_uses_short_signal_thresholds() -> None:
    assert signal_thresholds(SearchConfig(sampling_profile="freeze_bear_fade")) == (200, 30, 8000)
