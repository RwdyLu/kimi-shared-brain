from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import regime_context_v9 as rc


def write_month(cache: Path, symbol: str, month: str, start: str, periods: int, base: float = 100.0) -> None:
    dt = pd.date_range(start=start, periods=periods, freq="1h", tz="UTC")
    trend = pd.Series(range(periods), dtype=float) * 0.05
    df = pd.DataFrame(
        {
            "open_time": (dt.view("int64") // 1_000_000).astype("int64"),
            "open": base + trend,
            "high": base + trend + 1.0,
            "low": base + trend - 1.0,
            "close": base + trend + 0.25,
            "volume": 1000.0,
        }
    )
    df.to_parquet(cache / f"{symbol}_1h_{month}.parquet", index=False)


def write_config(path: Path, min_daily_bars: int = 20) -> None:
    path.write_text(
        "\n".join(
            [
                "version: test_regime_v9",
                "trend_return_days: 10",
                "trend_up_threshold: 0.01",
                "trend_down_threshold: -0.01",
                "vol_window_days: 5",
                "vol_percentile_lookback_days: 20",
                "high_vol_percentile: 0.80",
                "low_vol_percentile: 0.35",
                "drawdown_lookback_days: 30",
                "deep_drawdown_threshold: 0.20",
                f"min_daily_bars: {min_daily_bars}",
                "folds: 2",
                "cvar_frac: 0.05",
                "train_pnl_concentration_limit: 0.60",
                "risk_budget_per_trade: 0.01",
            ]
        )
        + "\n"
    )


def test_regime_context_writes_train_only_labels(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    out = tmp_path / "out"
    cfg = tmp_path / "regime.yaml"
    cache.mkdir()
    write_config(cfg)
    write_month(cache, "BTCUSDT", "2020-01", "2020-01-01", 24 * 31)
    write_month(cache, "BTCUSDT", "2020-02", "2020-02-01", 24 * 29, base=140.0)

    payload = rc.run(
        argparse.Namespace(
            cache_dir=str(cache),
            symbols=["BTCUSDT"],
            train_start="2020-01-01",
            train_end="2020-02-29 23:00:00",
            embargo_start="2020-03-01",
            config=str(cfg),
            candidate_trades="",
            out=str(out),
        )
    )

    labels_path = out / "regime_labels_BTCUSDT.parquet"
    assert labels_path.exists()
    labels = pd.read_parquet(labels_path)
    assert not labels.empty
    assert labels["dt"].max() < pd.Timestamp("2020-03-01", tz="UTC")
    assert payload["symbols"]["BTCUSDT"]["scored_days"] > 0


def test_regime_context_refuses_embargo_overlap(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    out = tmp_path / "out"
    cfg = tmp_path / "regime.yaml"
    cache.mkdir()
    write_config(cfg)
    write_month(cache, "BTCUSDT", "2020-03", "2020-03-01", 24)

    with pytest.raises(SystemExit):
        rc.run(
            argparse.Namespace(
                cache_dir=str(cache),
                symbols=["BTCUSDT"],
                train_start="2020-03-01",
                train_end="2020-03-01 23:00:00",
                embargo_start="2020-03-01",
                config=str(cfg),
                candidate_trades="",
                out=str(out),
            )
        )
