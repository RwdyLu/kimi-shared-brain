from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_funding_carry_precheck.py"
SPEC = importlib.util.spec_from_file_location("v9_funding_carry_precheck", SCRIPT)
assert SPEC and SPEC.loader
precheck_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(precheck_mod)


def synthetic_funding_frame() -> pd.DataFrame:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    symbols = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
    base = {
        "AAAUSDT": -0.0010,
        "BBBUSDT": -0.0006,
        "CCCUSDT": 0.0006,
        "DDDUSDT": 0.0010,
    }
    rows = []
    for idx in range(12):
        funding_time = int((start + pd.Timedelta(hours=8 * idx)).timestamp() * 1000)
        for symbol in symbols:
            wobble = (idx % 3) * 0.00001
            signed_wobble = -wobble if symbol in {"AAAUSDT", "BBBUSDT"} else 2.0 * wobble
            rows.append({"symbol": symbol, "funding_time": funding_time, "funding_rate": base[symbol] + signed_wobble})
    return pd.DataFrame(rows)


def test_evaluate_funding_carry_uses_point_in_time_trailing_signal() -> None:
    frame = synthetic_funding_frame()

    detail, metrics = precheck_mod.evaluate_funding_carry(
        frame,
        lookback_events=3,
        bucket_fraction=0.25,
        min_symbols=4,
    )

    expected_first = int((pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(hours=24)).timestamp() * 1000)
    assert metrics["status"] == "ok"
    assert metrics["first_evaluated_funding_time"] == expected_first
    assert detail.iloc[0]["long_symbols"] == ["AAAUSDT"]
    assert detail.iloc[0]["short_symbols"] == ["DDDUSDT"]
    assert metrics["annualized_gross_return"] > 0
    assert metrics["passes_gross_precheck"] is True


def test_last_closed_hour_open_time_for_funding_uses_previous_closed_candle() -> None:
    funding_time = int(pd.Timestamp("2026-07-13T08:00:00.001Z").timestamp() * 1000)

    open_time = precheck_mod.last_closed_hour_open_time_for_funding(funding_time)

    assert pd.Timestamp(open_time, unit="ms", tz="UTC").isoformat() == "2026-07-13T07:00:00+00:00"


def test_price_aware_carry_uses_close_to_close_returns() -> None:
    frame = synthetic_funding_frame()
    detail, _metrics = precheck_mod.evaluate_funding_carry(
        frame,
        lookback_events=3,
        bucket_fraction=0.25,
        min_symbols=4,
    )
    close_rows = []
    for funding_time in sorted(frame["funding_time"].unique()):
        open_time = precheck_mod.last_closed_hour_open_time_for_funding(int(funding_time))
        for symbol in sorted(frame["symbol"].unique()):
            close_rows.append({"symbol": symbol, "open_time": open_time, "close": 100.0})
    close_frame = pd.DataFrame(close_rows)

    metrics = precheck_mod.evaluate_price_aware_carry(detail, close_frame, turnover_cost_bps=0.0)

    assert metrics["status"] == "ok"
    assert metrics["net_annualized_return"] == metrics["funding_annualized_return"]
    assert metrics["price_annualized_return"] == 0.0
    assert metrics["passes_price_aware_precheck"] is True


def test_load_funding_cache_reads_symbol_monthly_files(tmp_path) -> None:
    frame = synthetic_funding_frame()
    for symbol, part in frame.groupby("symbol"):
        part.to_parquet(tmp_path / f"{symbol}_funding_2026-01.parquet", index=False)

    loaded = precheck_mod.load_funding_cache(tmp_path, ("AAAUSDT", "DDDUSDT"))

    assert set(loaded["symbol"]) == {"AAAUSDT", "DDDUSDT"}
    assert len(loaded) == 24


def test_evaluate_funding_carry_reports_insufficient_data() -> None:
    detail, metrics = precheck_mod.evaluate_funding_carry(
        pd.DataFrame(columns=["symbol", "funding_time", "funding_rate"]),
        lookback_events=3,
        bucket_fraction=0.25,
        min_symbols=4,
    )

    assert detail.empty
    assert metrics["status"] == "insufficient_data"
