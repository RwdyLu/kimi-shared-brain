from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from v9.contract.freeze import (  # noqa: E402
    FreezeConfig,
    bootstrap_net_pnl_p5,
    daily_realized_returns,
    freeze_gate,
    in_market_days,
    jaccard,
    pairwise_matrix,
    pearson_corr,
    select_candidates,
    trade_stats,
)


def trade(idx: int, pnl: float, r: float, regime: str = "up_normal", reason: str = "take_profit") -> dict:
    signal = pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=idx)
    entry = signal + pd.Timedelta(hours=1)
    exit_time = entry + pd.Timedelta(hours=4)
    return {
        "candidate_id": "x",
        "signal_time": signal.isoformat(),
        "entry_time": entry.isoformat(),
        "exit_time": exit_time.isoformat(),
        "signal_index": idx * 24,
        "entry_index": idx * 24 + 1,
        "exit_index": idx * 24 + 5,
        "entry_regime": regime,
        "exit_reason": reason,
        "net_pnl": pnl,
        "r_multiple": r,
    }


def summary(net: float, trades: list[dict], folds: list[float] | None = None) -> dict:
    return {
        "net_pnl": net,
        "trade_count": len(trades),
        "folds": [
            {"fold": idx, "net_pnl": value, "trades": len(trades) // 3, "start": "", "end": ""}
            for idx, value in enumerate(folds or [net / 3, net / 3, net / 3])
        ],
        "trades": trades,
        "equity_curve": [
            {"dt": "2020-01-01T00:00:00+00:00", "equity": 10_000.0},
            {"dt": "2020-03-01T00:00:00+00:00", "equity": 10_000.0 + net},
        ],
        "exposure_bar_ratio": 0.1,
    }


def test_trade_stats_regime_and_exit_reason_sum_to_total() -> None:
    trades = [trade(0, 10.0, 1.0), trade(1, -4.0, -0.4, "up_high_vol", "stop_loss"), trade(2, 6.0, 0.6)]
    stats = trade_stats(trades, [{"dt": "2020-01-01T00:00:00+00:00", "equity": 10_000.0}])
    assert stats["trades"] == 3
    assert stats["net_pnl"] == 12.0
    assert sum(row["net_pnl"] for row in stats["by_regime"].values()) == 12.0
    assert sum(row["net_pnl"] for row in stats["by_exit_reason"].values()) == 12.0
    assert stats["longest_loss_streak"] == 1


def test_bootstrap_is_seeded_and_reproducible() -> None:
    trades = [trade(i, float(i - 2), float(i - 2) / 10.0) for i in range(8)]
    left = bootstrap_net_pnl_p5(trades, iterations=50, block=2, seed=7)
    right = bootstrap_net_pnl_p5(trades, iterations=50, block=2, seed=7)
    assert left == right


def test_freeze_gate_blocks_fold_concentration_and_cost_retention() -> None:
    trades = [trade(i, 10.0, 0.5) for i in range(6)]
    base = summary(120.0, trades)
    cost2 = summary(40.0, trades, folds=[35.0, 4.0, 1.0])
    cost3 = summary(20.0, trades)
    stats = trade_stats(trades, cost2["equity_curve"])
    cfg = FreezeConfig(min_trades=3, max_top5_profit_share=2.0, bootstrap_iterations=10)
    gate = freeze_gate(base, cost2, cost3, stats, bootstrap_p5=1.0, train_end=pd.Timestamp("2020-12-31", tz="UTC"), cfg=cfg)
    assert gate["passed"] is False
    assert "cost_retention" in gate["failures"]
    assert "min_fold_share" in gate["failures"]


def test_correlation_and_jaccard_helpers() -> None:
    idx = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    a = pd.Series([0.0, 1.0, -1.0], index=idx)
    b = pd.Series([0.0, 1.0, -1.0], index=idx)
    c = pd.Series([0.0, -1.0, 1.0], index=idx)
    assert pearson_corr(a, b) == 1.0
    assert pearson_corr(a, c) < 0.0
    assert jaccard({"2020-01-01"}, {"2020-01-02"}) == 0.0
    assert jaccard({"2020-01-01", "2020-01-02"}, {"2020-01-02"}) == 0.5


def row(cid: str, p5: float, daily: pd.Series, days: set[str], passed: bool = True) -> dict:
    return {
        "candidate_id": cid,
        "base": {"exposure_bar_ratio": 0.1},
        "daily_returns": daily,
        "in_market_days": days,
        "freeze_gate": {
            "passed": passed,
            "derived": {"bootstrap_cost2_net_pnl_p5": p5, "min_fold_share": 0.2},
        },
    }


def test_selection_skips_pairwise_correlated_candidate() -> None:
    idx = pd.date_range("2020-01-01", periods=4, freq="1D", tz="UTC")
    a = row("a", 100.0, pd.Series([0.0, 1.0, 0.0, -0.5], index=idx), {"2020-01-02"})
    b = row("b", 90.0, pd.Series([0.0, 1.0, 0.0, -0.5], index=idx), {"2020-01-02"})
    c = row("c", 80.0, pd.Series([1.0, 0.0, -0.5, 0.0], index=idx), {"2020-01-04"})
    cfg = FreezeConfig(max_selected=3, corr_threshold=0.6, jaccard_threshold=0.5)
    pairs = pairwise_matrix([a, b, c], cfg)
    assert select_candidates([a, b, c], pairs, cfg) == ["a", "c"]


def test_daily_returns_and_market_days_are_cutoff_aligned() -> None:
    trades = [trade(0, 10.0, 1.0), trade(2, -5.0, -0.5)]
    series = daily_realized_returns(
        trades,
        pd.Timestamp("2020-01-01", tz="UTC"),
        pd.Timestamp("2020-01-05", tz="UTC"),
        10_000.0,
    )
    assert len(series) == 5
    assert abs(float(series.sum()) - 0.0005) < 1e-12
    days = in_market_days(trades)
    assert "2020-01-01" in days
    assert "2020-01-03" in days
