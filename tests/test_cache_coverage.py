"""
Regression tests for KlineCache coverage validation and strict_validation wiring.

Tests:
1. test_cache_partial_triggers_api_refetch
2. test_cache_missing_middle_candle_triggers_refetch
3. test_cache_stale_end_triggers_api_fetch
4. test_strict_count_mismatch_data_invalid
5. test_strict_start_mismatch_data_invalid
6. test_strict_end_mismatch_data_invalid
7. test_v1_strict_count_mismatch_aborts
8. test_v2_strict_count_mismatch_aborts
9. test_load_or_fetch_returns_tuple_always
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetcher import (
    BinanceFetcher,
    validate_klines,
    interval_to_ms,
    INTERVAL_MS,
)
from app.genetic_engine.backtest_engine import KlineCache


# ─── Helpers ─────────────────────────────────────────────────────────────────

INTERVAL_5M_MS = 5 * 60 * 1000
START_MS = 1_700_000_000_000


def make_klines(start_ms: int, count: int, interval_ms: int = INTERVAL_5M_MS) -> list:
    """Generate full-format klines for count candles."""
    return [
        [
            start_ms + i * interval_ms,
            "100.0", "101.0", "99.0", "100.5", "1000.0",
            start_ms + (i + 1) * interval_ms - 1,
            "100000.0", 100, "500.0", "50000.0", "0",
        ]
        for i in range(count)
    ]


def make_df_from_klines(klines: list) -> pd.DataFrame:
    """Convert raw klines list to a DataFrame with datetime index (UTC)."""
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore',
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype('int64'), unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df


def make_ok_validation(klines: list) -> dict:
    return {
        "valid": True,
        "data_invalid": False,
        "actual_count": len(klines),
        "actual_start_ms": int(klines[0][0]) if klines else None,
        "actual_end_ms": int(klines[-1][0]) if klines else None,
        "duration_ms": None,
        "gaps": [],
        "warnings": [],
        "errors": [],
    }


def make_mock_fetcher(klines: list) -> Mock:
    """Mock fetcher whose fetch_klines_paginated returns klines + ok validation."""
    fetcher = Mock()
    fetcher.fetch_klines_paginated.return_value = (klines, make_ok_validation(klines))
    return fetcher


# ─── Fix 4.1: Partial cache → API refetch ────────────────────────────────────

class TestCachePartialTriggersApiRefetch(unittest.TestCase):
    """Cache has 1000 candles, request needs 25920 → must call API."""

    def test_cache_partial_triggers_api_refetch(self):
        # 90 days of 5m = 25920 expected candles
        expected_count = 90 * 24 * 12  # 25920
        end_ms = START_MS + expected_count * INTERVAL_5M_MS

        # Build a cache with only 1000 candles
        partial_klines = make_klines(START_MS, 1000)
        full_klines = make_klines(START_MS, expected_count)
        fetcher = make_mock_fetcher(full_klines)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            # Manually write partial data to cache
            partial_df = make_df_from_klines(partial_klines)
            cache.save(partial_df, "BTCUSDT", "5m")

            df, validation = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            # API must have been called because partial cache was rejected
            fetcher.fetch_klines_paginated.assert_called_once()
            self.assertIsNotNone(df)
            self.assertFalse(validation.get("data_invalid"),
                             f"Expected valid data but got: {validation}")


# ─── Fix 4.2: Gap in cached data → refetch ───────────────────────────────────

class TestCacheMissingMiddleCandleTriggersRefetch(unittest.TestCase):
    """Cache has a gap in the middle → must reject and refetch."""

    def test_cache_missing_middle_candle_triggers_refetch(self):
        count = 500
        end_ms = START_MS + count * INTERVAL_5M_MS

        # Create klines with a gap at candle 250
        raw = make_klines(START_MS, count)
        del raw[250]  # Remove one candle — creates a gap

        full_klines = make_klines(START_MS, count)
        fetcher = make_mock_fetcher(full_klines)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            gapped_df = make_df_from_klines(raw)
            cache.save(gapped_df, "BTCUSDT", "5m")

            df, validation = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            # API must be called because gap was detected
            fetcher.fetch_klines_paginated.assert_called_once()
            self.assertIsNotNone(df)


# ─── Fix 4.3: Stale cache (end_ms too old) → refetch ────────────────────────

class TestCacheStaleEndTriggersApiFetch(unittest.TestCase):
    """Cache ends 7 days ago but we request data up to now → must fetch."""

    def test_cache_stale_end_triggers_api_fetch(self):
        # Cache covers the first 83 days only (7 days stale)
        days_cached = 83
        days_needed = 90

        cache_count = days_cached * 24 * 12
        needed_count = days_needed * 24 * 12
        end_ms = START_MS + needed_count * INTERVAL_5M_MS
        cache_end_ms = START_MS + cache_count * INTERVAL_5M_MS

        stale_klines = make_klines(START_MS, cache_count)
        full_klines = make_klines(START_MS, needed_count)
        fetcher = make_mock_fetcher(full_klines)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            stale_df = make_df_from_klines(stale_klines)
            cache.save(stale_df, "BTCUSDT", "5m")

            df, validation = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            # API must be called because cache is stale
            fetcher.fetch_klines_paginated.assert_called_once()
            self.assertIsNotNone(df)


# ─── Fix 4.4–4.6: strict=True → data_invalid ─────────────────────────────────

class TestStrictValidation(unittest.TestCase):
    """validate_klines with strict=True: count/start/end mismatch → data_invalid=True."""

    def _klines(self, start_ms: int, count: int) -> list:
        return make_klines(start_ms, count)

    def test_strict_count_mismatch_data_invalid(self):
        """strict=True, fewer candles than expected → data_invalid=True."""
        klines = self._klines(START_MS, 50)  # only 50
        result = validate_klines(
            klines,
            expected_count=100,
            interval="5m",
            strict=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(result["data_invalid"])
        self.assertTrue(any("Expected 100" in e for e in result["errors"]))

    def test_strict_count_mismatch_not_data_invalid_without_strict(self):
        """Without strict: count mismatch is a warning, not error."""
        klines = self._klines(START_MS, 50)
        result = validate_klines(
            klines,
            expected_count=100,
            interval="5m",
            strict=False,
        )
        self.assertTrue(result["valid"])
        self.assertFalse(result["data_invalid"])
        self.assertTrue(any("Expected 100" in w for w in result["warnings"]))

    def test_strict_start_mismatch_data_invalid(self):
        """strict=True, start_ms off by more than 2 candles → data_invalid=True."""
        klines = self._klines(START_MS, 50)
        # expected_start_ms is 1 hour later (12 candles away for 5m)
        result = validate_klines(
            klines,
            expected_start_ms=START_MS + 12 * INTERVAL_5M_MS,
            interval="5m",
            strict=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(result["data_invalid"])
        self.assertTrue(any("Start time mismatch" in e for e in result["errors"]))

    def test_strict_end_mismatch_data_invalid(self):
        """strict=True, end_ms off by more than 2 candles → data_invalid=True."""
        klines = self._klines(START_MS, 50)
        actual_end = START_MS + 49 * INTERVAL_5M_MS
        # expected_end_ms is 1 hour later (12 candles away)
        result = validate_klines(
            klines,
            expected_end_ms=actual_end + 12 * INTERVAL_5M_MS,
            interval="5m",
            strict=True,
        )
        self.assertFalse(result["valid"])
        self.assertTrue(result["data_invalid"])
        self.assertTrue(any("End time mismatch" in e for e in result["errors"]))


# ─── Fix 4.7–4.8: Engine abort on strict count mismatch ─────────────────────

class TestEngineAbortOnStrictMismatch(unittest.TestCase):
    """V1 and V2 engines abort when fetch_klines_paginated returns data_invalid=True."""

    def _make_invalid_validation(self) -> dict:
        return {
            "valid": False,
            "data_invalid": True,
            "actual_count": 50,
            "actual_start_ms": START_MS,
            "actual_end_ms": None,
            "duration_ms": None,
            "gaps": [],
            "warnings": [],
            "errors": ["[BTCUSDT] Expected 25920 candles, got 50 (short by 25870)"],
        }

    def test_v1_strict_count_mismatch_aborts(self):
        """V1 engine: data_invalid=True → metrics.data_invalid=True, no trades."""
        from app.genetic_engine.backtest_engine import GeneBacktestEngine

        engine = GeneBacktestEngine()
        # Inject mock cache that returns invalid data
        mock_cache = Mock()
        mock_cache.load_or_fetch.return_value = (None, self._make_invalid_validation())
        engine.cache = mock_cache

        chrom = Mock()
        chrom.entry_genes = []
        chrom.exit_genes = []
        chrom.trend_filter = None
        chrom.volume_filter = None

        metrics, trades = engine.evaluate(chrom, "BTCUSDT", interval="5m", days=90)

        self.assertTrue(metrics.data_invalid,
                        "V1 metrics.data_invalid must be True on count mismatch")
        self.assertEqual(trades, [])
        self.assertEqual(metrics.total_trades, 0)

    def test_v2_strict_count_mismatch_aborts(self):
        """V2 engine: data_invalid=True → result.data_invalid=True, no trades."""
        from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2, V2BacktestResult

        engine = GeneBacktestEngineV2()
        engine.fetcher = Mock()
        engine.fetcher.fetch_klines_paginated.return_value = (
            make_klines(START_MS, 50),
            self._make_invalid_validation(),
        )

        chrom = Mock()
        chrom.entry_genes = []
        chrom.exit_genes = []
        chrom.trend_filter = None
        chrom.volume_filter = None

        result = engine.evaluate_v2(chrom, "BTCUSDT", interval="5m", days=90)

        self.assertIsInstance(result, V2BacktestResult)
        self.assertTrue(result.data_invalid)
        self.assertEqual(result.strategy_trades, [])
        self.assertTrue(result.strategy_metrics.data_invalid)


# ─── Fix 4.9: load_or_fetch always returns tuple ─────────────────────────────

class TestLoadOrFetchReturnsTupleAlways(unittest.TestCase):
    """load_or_fetch must always return (df, validation) — never a bare DataFrame."""

    def test_returns_tuple_on_api_fetch(self):
        """API path returns (df, validation) tuple."""
        count = 200
        end_ms = START_MS + count * INTERVAL_5M_MS
        klines = make_klines(START_MS, count)
        fetcher = make_mock_fetcher(klines)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            result = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )
            self.assertIsInstance(result, tuple, "Must return tuple")
            self.assertEqual(len(result), 2, "Tuple must have 2 elements")
            df, validation = result
            self.assertIsNotNone(df)
            self.assertIsInstance(validation, dict)
            self.assertIn("valid", validation)
            self.assertIn("data_invalid", validation)

    def test_returns_tuple_on_cache_hit(self):
        """Cache-hit path returns (df, validation) tuple with valid=True."""
        count = 200
        end_ms = START_MS + count * INTERVAL_5M_MS
        klines = make_klines(START_MS, count)
        fetcher = make_mock_fetcher(klines)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            # Prime the cache
            cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )
            fetcher.reset_mock()

            # Second call — from cache
            cache2 = KlineCache(cache_dir=Path(tmpdir))
            result = cache2.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )
            self.assertIsInstance(result, tuple)
            df, validation = result
            self.assertIsNotNone(df)
            self.assertIsNotNone(validation, "validation must never be None")
            self.assertIsInstance(validation, dict)
            self.assertTrue(validation.get("valid"))
            self.assertFalse(validation.get("data_invalid"))
            # API must NOT have been called again
            fetcher.fetch_klines_paginated.assert_not_called()

    def test_returns_tuple_on_cache_miss_no_file(self):
        """No cache file → API called, returns (df, validation) tuple."""
        count = 200
        end_ms = START_MS + count * INTERVAL_5M_MS
        klines = make_klines(START_MS, count)
        fetcher = make_mock_fetcher(klines)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            result = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )
            self.assertIsInstance(result, tuple)
            df, validation = result
            self.assertIsNotNone(df)
            self.assertIsNotNone(validation)

    def test_returns_tuple_on_invalid_data(self):
        """data_invalid=True from API → returns (None, validation) tuple, not bare None."""
        count = 50
        end_ms = START_MS + 1000 * INTERVAL_5M_MS
        klines = make_klines(START_MS, count)
        fetcher = Mock()
        bad_validation = {
            "valid": False,
            "data_invalid": True,
            "actual_count": count,
            "actual_start_ms": START_MS,
            "actual_end_ms": None,
            "duration_ms": None,
            "gaps": [],
            "warnings": [],
            "errors": ["[BTCUSDT] max_pages reached"],
        }
        fetcher.fetch_klines_paginated.return_value = (klines, bad_validation)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            result = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=START_MS, end_ms=end_ms,
                limit=1000, paginate=True,
            )
            self.assertIsInstance(result, tuple)
            df, validation = result
            self.assertIsNone(df)
            self.assertIsNotNone(validation)
            self.assertTrue(validation.get("data_invalid"))


class TestV2NormalizedCacheContract(unittest.TestCase):
    def test_v2_uses_cached_dataframe_without_raw_kline_reconversion(self):
        from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2

        index = pd.date_range("2025-01-01", periods=200, freq="5min")
        df = pd.DataFrame(
            {
                "open": np.full(200, 100.0),
                "high": np.full(200, 101.0),
                "low": np.full(200, 99.0),
                "close": np.full(200, 100.0),
                "volume": np.full(200, 10.0),
            },
            index=index,
        )
        engine = GeneBacktestEngineV2()
        engine.cache = Mock()
        engine.cache.load_or_fetch.return_value = (
            df,
            {"valid": True, "data_invalid": False, "warnings": [], "errors": []},
        )
        engine.dca_engine = Mock()
        engine.dca_engine.run.return_value = ([1000.0, 1000.0], [])
        engine.dca_engine.calculate_dca_return.return_value = 0.0
        engine._run_strategy_v2 = Mock(
            return_value=([1000.0, 1000.0], [], {"total_fees": 0.0, "realized_pnl": 0.0})
        )
        engine._klines_to_df = Mock(side_effect=AssertionError("must not reconvert cached DataFrame"))

        chrom = Mock()
        result = engine.evaluate_v2(chrom, "BTCUSDT", interval="5m", days=1)

        self.assertFalse(result.data_invalid)
        engine._klines_to_df.assert_not_called()
        passed_df = engine._run_strategy_v2.call_args.args[0]
        pd.testing.assert_frame_equal(passed_df, df)


if __name__ == '__main__':
    unittest.main(verbosity=2)
