from __future__ import annotations

import math

import pandas as pd

from v9.contract.funding_anticarry_factory import (
    FundingAntiCarryConfig,
    RunConfig,
    config_grid,
    filter_train_data,
    run_factory,
    validation_checks,
)


def write_synthetic_cache(root, symbols: tuple[str, ...], *, events: int = 600) -> tuple[object, object]:
    funding_dir = root / "funding"
    ohlcv_dir = root / "ohlcv"
    funding_dir.mkdir()
    ohlcv_dir.mkdir()
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    funding_times = [int((start + pd.Timedelta(hours=8 * idx)).timestamp() * 1000) for idx in range(events)]
    hourly_times = [int((start + pd.Timedelta(hours=idx)).timestamp() * 1000) for idx in range(events * 8 + 1)]
    for symbol in symbols:
        is_high = symbol in {"AAAUSDT", "BBBUSDT"}
        funding_rate = 0.00010 if is_high else -0.00005
        drift = 0.00018 if is_high else -0.00010
        funding = pd.DataFrame(
            {
                "symbol": [symbol] * len(funding_times),
                "funding_time": funding_times,
                "funding_rate": [
                    funding_rate + (0.000005 * math.sin(idx / 7.0))
                    for idx in range(len(funding_times))
                ],
                "mark_price": [100.0] * len(funding_times),
            }
        )
        funding.to_parquet(funding_dir / f"{symbol}_funding_2024-01.parquet", index=False)
        price = 100.0
        closes = []
        for idx, open_time in enumerate(hourly_times):
            wobble = 0.00003 * math.sin(idx / 11.0)
            price *= 1.0 + drift + wobble
            closes.append(
                {
                    "open_time": open_time,
                    "open": price,
                    "high": price * 1.001,
                    "low": price * 0.999,
                    "close": price,
                    "volume": 1000.0,
                }
            )
        pd.DataFrame(closes).to_parquet(ohlcv_dir / f"{symbol}_1h_2024-01.parquet", index=False)
    return funding_dir, ohlcv_dir


def test_config_grid_uses_explicit_configs() -> None:
    explicit = (FundingAntiCarryConfig(lookback_events=5, rebalance_every_events=3, bucket_fraction=0.5, min_symbols=4),)
    run = RunConfig(symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT"), explicit_configs=explicit)

    assert config_grid(run) == explicit


def test_filter_train_data_rejects_leaky_window(tmp_path) -> None:
    funding = pd.DataFrame({"funding_time": [1], "symbol": ["AAAUSDT"], "funding_rate": [0.0]})
    closes = pd.DataFrame({"open_time": [1], "symbol": ["AAAUSDT"], "close": [1.0]})

    try:
        filter_train_data(
            funding,
            closes,
            train_start="2024-01-01",
            train_end="2024-02-01",
            embargo_start="2024-02-01",
        )
    except ValueError as exc:
        assert "train_end must be before embargo_start" in str(exc)
    else:
        raise AssertionError("leaky train window should fail")


def test_validation_checks_require_stress_and_walkforward() -> None:
    good = {
        "sharpe": 1.5,
        "total_return": 0.2,
        "max_drawdown": 0.1,
        "active_rebalance_event_count": 200,
        "yearly_count": 1,
        "yearly_positive_count": 1,
        "top_positive_symbol_share": 0.25,
    }
    checks = validation_checks(good, good, good, good, good, {"passed": True})

    assert all(checks.values())
    checks = validation_checks(good, good, {**good, "sharpe": 0.2}, good, good, {"passed": True})
    assert checks["validation_sharpe20_ge_1_0"] is False


def test_run_factory_accepts_synthetic_anti_carry(tmp_path) -> None:
    symbols = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
    funding_dir, ohlcv_dir = write_synthetic_cache(tmp_path, symbols)
    configs = (
        FundingAntiCarryConfig(lookback_events=5, rebalance_every_events=3, bucket_fraction=0.5, min_symbols=4),
        FundingAntiCarryConfig(lookback_events=8, rebalance_every_events=3, bucket_fraction=0.5, min_symbols=4),
    )
    run = RunConfig(
        symbols=symbols,
        explicit_configs=configs,
        min_symbols=4,
        costs_bps=(20.0, 40.0),
        stress_costs_bps=(50.0,),
        train_start="2024-01-01",
        train_end="2024-07-15 23:59:59",
        embargo_start="2024-07-16",
        funding_cache_dir=str(funding_dir),
        ohlcv_cache_dir=str(ohlcv_dir),
        universe_json="",
        out_json=str(tmp_path / "factory.json"),
        out_md=str(tmp_path / "factory.md"),
    )

    payload = run_factory(run)

    assert payload["summary"]["accepted_train_only"] is True
    assert payload["summary"]["pass_count"] == 2
    assert payload["rows"][0]["advance_passed"] is True
    assert payload["rows"][0]["validation"]["cost40"]["sharpe"] > 1.0
    assert payload["rows"][0]["walk_forward"]["passed"] is True
    assert payload["summary"]["paper_trading_authorized"] is False
    assert (tmp_path / "factory.json").exists()
    assert "No holdout" in (tmp_path / "factory.md").read_text()
