from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_binance_funding_cache_update.py"
SPEC = importlib.util.spec_from_file_location("v9_binance_funding_cache_update", SCRIPT)
assert SPEC and SPEC.loader
update_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_mod)


def test_frame_from_funding_rows_normalizes_and_deduplicates() -> None:
    rows = [
        {"symbol": "BTCUSDT", "fundingTime": "1783728000000", "fundingRate": "0.00010000", "markPrice": "100.0"},
        {"symbol": "BTCUSDT", "fundingTime": "1783728000000", "fundingRate": "0.00020000", "markPrice": "101.0"},
        {"symbol": "BTCUSDT", "fundingTime": "1783756800000", "fundingRate": "-0.00005000", "markPrice": "99.0"},
        {"symbol": "ETHUSDT", "fundingTime": "1783756800000", "fundingRate": "0.50000000", "markPrice": "1.0"},
    ]

    frame = update_mod.frame_from_funding_rows(rows, symbol="BTCUSDT")

    assert frame["symbol"].tolist() == ["BTCUSDT", "BTCUSDT"]
    assert frame["funding_time"].tolist() == [1783728000000, 1783756800000]
    assert frame["funding_rate"].tolist() == [0.0002, -0.00005]
    assert frame["mark_price"].tolist() == [101.0, 99.0]


def test_write_monthly_cache_merges_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "BTCUSDT_funding_2026-07.parquet"
    pd.DataFrame(
        {
            "symbol": ["BTCUSDT"],
            "funding_time": [1783728000000],
            "funding_rate": [0.0001],
            "mark_price": [100.0],
        }
    ).to_parquet(path, index=False)
    frame = pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "funding_time": [1783728000000, 1783756800000],
            "funding_rate": [0.0003, -0.0001],
            "mark_price": [102.0, 99.0],
        }
    )

    result = update_mod.write_monthly_cache(tmp_path, "BTCUSDT", frame)
    merged = pd.read_parquet(path)

    assert result["written_file_count"] == 1
    assert merged["funding_time"].tolist() == [1783728000000, 1783756800000]
    assert merged.loc[merged["funding_time"] == 1783728000000, "funding_rate"].iloc[0] == 0.0003


def test_latest_cached_funding_time_reads_monthly_files(tmp_path) -> None:
    pd.DataFrame(
        {
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "funding_time": [1783728000000, 1783756800000],
            "funding_rate": [0.0001, 0.0002],
        }
    ).to_parquet(tmp_path / "BTCUSDT_funding_2026-07.parquet", index=False)
    pd.DataFrame(
        {
            "symbol": ["BTCUSDT"],
            "funding_time": [1786406400000],
            "funding_rate": [0.0003],
        }
    ).to_parquet(tmp_path / "BTCUSDT_funding_2026-08.parquet", index=False)

    latest = update_mod.latest_cached_funding_time(tmp_path, "BTCUSDT")

    assert latest == 1786406400000


def test_update_symbol_skips_when_cache_is_already_beyond_now(tmp_path, monkeypatch) -> None:
    latest = int(pd.Timestamp("2026-07-11T08:00:00Z").timestamp() * 1000)
    pd.DataFrame(
        {
            "symbol": ["BTCUSDT"],
            "funding_time": [latest],
            "funding_rate": [0.0001],
        }
    ).to_parquet(tmp_path / "BTCUSDT_funding_2026-07.parquet", index=False)

    def fail_fetch(*_args, **_kwargs):
        raise AssertionError("fetch_funding_rates should not run when cache is current")

    monkeypatch.setattr(update_mod, "fetch_funding_rates", fail_fetch)

    result = update_mod.update_symbol(
        cache_dir=tmp_path,
        symbol="BTCUSDT",
        now_ms=int(pd.Timestamp("2026-07-11T07:00:00Z").timestamp() * 1000),
        lookback_events_if_empty=90,
    )

    assert result["status"] == "up_to_date"
    assert result["downloaded_rows"] == 0


def test_update_symbol_fetches_incremental_rows(tmp_path, monkeypatch) -> None:
    latest = int(pd.Timestamp("2026-07-11T00:00:00Z").timestamp() * 1000)
    next_time = int(pd.Timestamp("2026-07-11T08:00:00Z").timestamp() * 1000)
    pd.DataFrame(
        {
            "symbol": ["BTCUSDT"],
            "funding_time": [latest],
            "funding_rate": [0.0001],
        }
    ).to_parquet(tmp_path / "BTCUSDT_funding_2026-07.parquet", index=False)
    calls = []

    def fake_fetch(symbol, start_ms, end_ms):
        calls.append((symbol, start_ms, end_ms))
        return [{"symbol": "BTCUSDT", "fundingTime": next_time, "fundingRate": "0.0002", "markPrice": "101.0"}]

    monkeypatch.setattr(update_mod, "fetch_funding_rates", fake_fetch)

    result = update_mod.update_symbol(
        cache_dir=tmp_path,
        symbol="BTCUSDT",
        now_ms=int(pd.Timestamp("2026-07-11T09:00:00Z").timestamp() * 1000),
        lookback_events_if_empty=90,
    )

    assert calls[0][0] == "BTCUSDT"
    assert calls[0][1] == latest + 1
    assert result["status"] == "updated"
    assert result["latest_after"] == next_time
