from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_xsec_binance_cache_update.py"
SPEC = importlib.util.spec_from_file_location("v9_xsec_binance_cache_update", SCRIPT)
assert SPEC and SPEC.loader
update_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_mod)


def test_current_closed_open_time_uses_previous_complete_candle() -> None:
    now_ms = int(pd.Timestamp("2026-07-11T02:21:00Z").timestamp() * 1000)

    closed = update_mod.current_closed_open_time_ms(now_ms, "1h")

    assert pd.Timestamp(closed, unit="ms", tz="UTC").isoformat() == "2026-07-11T01:00:00+00:00"


def test_write_monthly_cache_merges_and_deduplicates(tmp_path) -> None:
    path = tmp_path / "BTCUSDT_1h_2026-07.parquet"
    existing = pd.DataFrame(
        {
            "open_time": [1783728000000],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
        }
    )
    existing.to_parquet(path, index=False)
    frame = pd.DataFrame(
        {
            "open_time": [1783728000000, 1783731600000],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.8, 101.5],
            "volume": [10.0, 11.0],
        }
    )

    result = update_mod.write_monthly_cache(tmp_path, "BTCUSDT", "1h", frame)
    merged = pd.read_parquet(path)

    assert result["written_file_count"] == 1
    assert merged["open_time"].tolist() == [1783728000000, 1783731600000]
    assert merged.loc[merged["open_time"] == 1783728000000, "close"].iloc[0] == 100.8


def test_update_symbol_skips_when_cache_already_has_last_closed(tmp_path, monkeypatch) -> None:
    latest = int(pd.Timestamp("2026-07-11T01:00:00Z").timestamp() * 1000)
    pd.DataFrame(
        {
            "open_time": [latest],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
        }
    ).to_parquet(tmp_path / "BTCUSDT_1h_2026-07.parquet", index=False)

    def fail_fetch(*_args, **_kwargs):
        raise AssertionError("fetch_klines should not run when cache is current")

    monkeypatch.setattr(update_mod, "fetch_klines", fail_fetch)

    result = update_mod.update_symbol(
        cache_dir=tmp_path,
        symbol="BTCUSDT",
        interval="1h",
        now_ms=int(pd.Timestamp("2026-07-11T02:21:00Z").timestamp() * 1000),
        lookback_bars_if_empty=72,
    )

    assert result["status"] == "up_to_date"
    assert result["downloaded_rows"] == 0
