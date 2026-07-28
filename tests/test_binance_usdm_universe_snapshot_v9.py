from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_binance_usdm_universe_snapshot.py"
SPEC = importlib.util.spec_from_file_location("v9_binance_usdm_universe_snapshot", SCRIPT)
assert SPEC and SPEC.loader
universe_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(universe_mod)


def args(**overrides):
    values = {
        "top_n": 2,
        "prefilter_limit": 4,
        "volume_lookback_days": 3,
        "min_listing_age_days": 90,
        "min_median_quote_volume": 50_000_000.0,
        "sleep_sec": 0.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_median_quote_volume_from_klines() -> None:
    rows = [
        [0, "1", "1", "1", "1", "1", 0, "100.0"],
        [0, "1", "1", "1", "1", "1", 0, "300.0"],
        [0, "1", "1", "1", "1", "1", 0, "200.0"],
    ]

    assert universe_mod.median_quote_volume_from_klines(rows) == 200.0


def test_is_candidate_symbol_filters_non_tradable_stables_and_young_symbols() -> None:
    now_ms = 2_000_000_000_000
    base = {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "quoteAsset": "USDT",
        "baseAsset": "BTC",
        "onboardDate": now_ms - 100 * universe_mod.MS_PER_DAY,
    }

    assert universe_mod.is_candidate_symbol(base, now_ms=now_ms, min_listing_age_days=90)
    assert not universe_mod.is_candidate_symbol({**base, "status": "BREAK"}, now_ms=now_ms, min_listing_age_days=90)
    assert not universe_mod.is_candidate_symbol({**base, "baseAsset": "USDC"}, now_ms=now_ms, min_listing_age_days=90)
    assert not universe_mod.is_candidate_symbol(
        {**base, "onboardDate": now_ms - 10 * universe_mod.MS_PER_DAY},
        now_ms=now_ms,
        min_listing_age_days=90,
    )


def test_build_universe_ranks_by_median_quote_volume(monkeypatch) -> None:
    now_ms = 2_000_000_000_000
    symbols = [
        ("AAAUSDT", "AAA", 200_000_000),
        ("BBBUSDT", "BBB", 300_000_000),
        ("CCCUSDT", "CCC", 100_000_000),
        ("USDCUSDT", "USDC", 900_000_000),
        ("YOUNGUSDT", "YOUNG", 800_000_000),
    ]

    monkeypatch.setattr(universe_mod.time, "time", lambda: now_ms / 1000)
    monkeypatch.setattr(
        universe_mod,
        "fetch_exchange_info",
        lambda: {
            "symbols": [
                {
                    "symbol": symbol,
                    "status": "TRADING",
                    "contractType": "PERPETUAL",
                    "quoteAsset": "USDT",
                    "baseAsset": base,
                    "onboardDate": now_ms - (10 if symbol == "YOUNGUSDT" else 120) * universe_mod.MS_PER_DAY,
                }
                for symbol, base, _volume in symbols
            ]
        },
    )
    monkeypatch.setattr(
        universe_mod,
        "fetch_ticker_24h",
        lambda: [{"symbol": symbol, "quoteVolume": str(volume)} for symbol, _base, volume in symbols],
    )

    def fake_klines(symbol, *, limit):
        medians = {
            "AAAUSDT": [210_000_000, 220_000_000, 230_000_000],
            "BBBUSDT": [310_000_000, 320_000_000, 330_000_000],
            "CCCUSDT": [40_000_000, 45_000_000, 46_000_000],
        }
        return [[0, "1", "1", "1", "1", "1", 0, str(value)] for value in medians[symbol]]

    monkeypatch.setattr(universe_mod, "fetch_daily_klines", fake_klines)

    report = universe_mod.build_universe(args())

    assert report["symbols"] == ["BBBUSDT", "AAAUSDT"]
    assert report["candidate_count"] == 3
    assert report["selected_count"] == 2
