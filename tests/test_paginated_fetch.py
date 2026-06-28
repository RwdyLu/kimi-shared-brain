"""
Tests for paginated kline fetching and data validation.
Tests / 分頁 K 線抓取與資料驗證測試

Phase 1 of GA Core Principles: Fix 1000-candle limit for 90-day backtest.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, call, MagicMock
import json
import time
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetcher import (
    BinanceFetcher,
    KlineData,
    validate_klines,
    interval_to_ms,
    calculate_max_pages,
    INTERVAL_MS,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_klines(start_ms: int, interval_ms: int, count: int) -> list:
    """Generate synthetic kline pages with full Binance format."""
    return [
        [
            start_ms + i * interval_ms,   # 0: open_time
            "100.0",                        # 1: open
            "101.0",                        # 2: high
            "99.0",                         # 3: low
            "100.5",                        # 4: close
            "1000.0",                       # 5: volume
            start_ms + (i + 1) * interval_ms - 1,  # 6: close_time
            "100000.0",                     # 7: quote_volume
            100,                            # 8: trades
            "500.0",                        # 9: taker_buy_base
            "50000.0",                      # 10: taker_buy_quote
            "0"                             # 11: ignore
        ]
        for i in range(count)
    ]


# ─── interval_to_ms ──────────────────────────────────────────────────────────

class TestIntervalToMs(unittest.TestCase):
    """Test interval_to_ms helper"""

    def test_known_intervals(self):
        self.assertEqual(interval_to_ms("1m"), 60 * 1000)
        self.assertEqual(interval_to_ms("5m"), 5 * 60 * 1000)
        self.assertEqual(interval_to_ms("15m"), 15 * 60 * 1000)

    def test_unknown_interval_raises(self):
        with self.assertRaises(ValueError) as ctx:
            interval_to_ms("1h")
        self.assertIn("1h", str(ctx.exception))


# ─── validate_klines ─────────────────────────────────────────────────────────

class TestValidateKlines(unittest.TestCase):
    """Test validate_klines function"""

    def _make_klines(self, start_ms, interval_ms, count, valid=True):
        """Generate synthetic kline data"""
        klines = []
        for i in range(count):
            ts = start_ms + i * interval_ms
            if valid:
                klines.append([
                    ts,          # 0: open_time
                    100.0,       # 1: open
                    101.0,       # 2: high
                    99.0,        # 3: low
                    100.5,       # 4: close
                    1000.0,      # 5: volume
                    ts + interval_ms - 1,  # 6: close_time
                    100000.0,    # 7: quote_volume
                    100,         # 8: trades
                    500.0,       # 9: taker_buy_base
                    50000.0,     # 10: taker_buy_quote
                    "0"          # 11: ignore
                ])
            else:
                klines.append([ts])  # Invalid: too short
        return klines

    def test_empty_klines(self):
        result = validate_klines([])
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["Empty kline data"])

    def test_no_valid_timestamps(self):
        result = validate_klines([[]])
        self.assertFalse(result["valid"])
        self.assertIn("No valid timestamps", result["errors"][0])

    def test_valid_data(self):
        start = 1700000000000
        klines = self._make_klines(start, 300000, 100)
        result = validate_klines(
            klines,
            expected_start_ms=start,
            expected_end_ms=start + 99 * 300000,
            expected_count=100,
            interval="5m",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["actual_count"], 100)
        self.assertEqual(result["gaps"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["errors"], [])

    def test_short_count_warning(self):
        start = 1700000000000
        klines = self._make_klines(start, 300000, 50)
        result = validate_klines(
            klines,
            expected_count=100,
            interval="5m",
        )
        self.assertTrue(result["valid"])  # Still valid structurally
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("Expected 100 candles", result["warnings"][0])

    def test_gap_detection_is_error_not_warning(self):
        """Gap is now a hard ERROR (fail-closed), not just a warning."""
        start = 1700000000000
        interval_ms = 300000
        klines = self._make_klines(start, interval_ms, 10)
        # Introduce a gap: candle at index 5 jumps forward by 10 intervals.
        # This creates a gap between index 4 and the moved index 5, and another
        # unexpected spacing between the moved index 5 and the original index 6.
        klines[5][0] = start + 15 * interval_ms
        result = validate_klines(klines, interval="5m")
        self.assertFalse(result["valid"])
        self.assertTrue(any("Gap detected" in e for e in result["errors"]))
        self.assertGreaterEqual(len(result["gaps"]), 1)

    def test_invalid_candle_structure(self):
        start = 1700000000000
        klines = self._make_klines(start, 300000, 10)
        klines[3] = [start + 3 * 300000]  # Too short
        result = validate_klines(klines, interval="5m")
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("invalid structure", result["warnings"][0])

    def test_time_mismatch_warning(self):
        start = 1700000000000
        klines = self._make_klines(start, 300000, 10)
        result = validate_klines(
            klines,
            expected_start_ms=start + 1000000,
            interval="5m",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("Start time mismatch", result["warnings"][0])

    def test_missing_one_candle_fails(self):
        """A single missing candle creates a gap — validation must FAIL."""
        start = 1700000000000
        interval_ms = 300000
        klines = self._make_klines(start, interval_ms, 10)
        # Remove candle at index 5 (skip one interval)
        del klines[5]
        result = validate_klines(klines, interval="5m")
        self.assertFalse(result["valid"])
        self.assertTrue(any("Gap detected" in e for e in result["errors"]))


# ─── normalize_kline_data / get_klines ───────────────────────────────────────

class TestNormalizeKlineData(unittest.TestCase):
    """Test normalize_kline_data method is properly accessible on BinanceFetcher."""

    def setUp(self):
        self.fetcher = BinanceFetcher()

    def test_normalize_returns_kline_data_objects(self):
        """normalize_kline_data must be a method on BinanceFetcher."""
        raw = make_klines(1700000000000, 300000, 5)
        result = self.fetcher.normalize_kline_data(raw)
        self.assertEqual(len(result), 5)
        self.assertIsInstance(result[0], KlineData)
        self.assertEqual(result[0].timestamp, 1700000000000)
        self.assertAlmostEqual(result[0].open, 100.0)
        self.assertAlmostEqual(result[0].close, 100.5)

    def test_normalize_empty(self):
        result = self.fetcher.normalize_kline_data([])
        self.assertEqual(result, [])

    def test_normalize_raises_on_short_candle(self):
        raw = [[1700000000000, "100.0"]]  # Only 2 fields
        with self.assertRaises(ValueError):
            self.fetcher.normalize_kline_data(raw)

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_get_klines_calls_normalize(self, mock_fetch):
        """get_klines must call fetch_klines then normalize_kline_data."""
        raw = make_klines(1700000000000, 300000, 3)
        mock_fetch.return_value = raw

        result = self.fetcher.get_klines("BTCUSDT", "5m", limit=3)

        mock_fetch.assert_called_once_with("BTCUSDT", "5m", 3)
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[0], KlineData)


# ─── fetch_klines_paginated ───────────────────────────────────────────────────

class TestFetchKlinesPaginated(unittest.TestCase):
    """Test BinanceFetcher.fetch_klines_paginated"""

    def setUp(self):
        self.fetcher = BinanceFetcher()

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_single_page(self, mock_fetch):
        """When all data fits in one page"""
        start = 1700000000000
        interval_ms = 300000
        end = start + 500 * interval_ms

        klines = make_klines(start, interval_ms, 500)
        mock_fetch.return_value = klines

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000, max_pages=100
        )

        self.assertEqual(len(result), 500)
        self.assertEqual(mock_fetch.call_count, 1)
        self.assertTrue(validation["valid"])

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_multi_page(self, mock_fetch):
        """When data spans multiple pages"""
        start = 1700000000000
        interval_ms = 300000
        page_size = 1000
        end = start + 2500 * interval_ms  # 2.5 pages worth

        page1 = make_klines(start, interval_ms, 1000)
        page2_start = start + 1000 * interval_ms
        page2 = make_klines(page2_start, interval_ms, 1000)
        page3_start = start + 2000 * interval_ms
        page3 = make_klines(page3_start, interval_ms, 500)

        mock_fetch.side_effect = [page1, page2, page3]

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=page_size, max_pages=100
        )

        self.assertEqual(len(result), 2500)
        self.assertEqual(mock_fetch.call_count, 3)
        self.assertTrue(validation["valid"])

        calls = mock_fetch.call_args_list
        self.assertEqual(calls[0][1]["start_time"], start)
        self.assertEqual(calls[1][1]["start_time"], page2_start)
        self.assertEqual(calls[2][1]["start_time"], page3_start)

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_early_termination_small_page(self, mock_fetch):
        """When API returns fewer candles than limit (end of data)"""
        start = 1700000000000
        interval_ms = 300000
        end = start + 5000 * interval_ms

        page1 = make_klines(start, interval_ms, 1000)
        page2_start = start + 1000 * interval_ms
        page2 = make_klines(page2_start, interval_ms, 500)

        mock_fetch.side_effect = [page1, page2]

        result, _ = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000, max_pages=100
        )

        self.assertEqual(len(result), 1500)
        self.assertEqual(mock_fetch.call_count, 2)

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_empty_response(self, mock_fetch):
        """When API returns empty data"""
        mock_fetch.return_value = []

        with self.assertRaises(ValueError) as ctx:
            self.fetcher.fetch_klines_paginated(
                "BTCUSDT", "5m", 1700000000000, 1700000001000, max_pages=5
            )
        self.assertIn("Empty response", str(ctx.exception))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_cross_page_duplicate_dedup(self, mock_fetch):
        """Last candle of page N == first candle of page N+1: deduplicated correctly."""
        start = 1700000000000
        interval_ms = 300000
        page_size = 1000
        end = start + 1500 * interval_ms

        page1 = make_klines(start, interval_ms, 1000)
        # page2 starts with the SAME candle as the last of page1
        page2 = make_klines(start + 999 * interval_ms, interval_ms, 500)

        mock_fetch.side_effect = [page1, page2]

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=page_size, max_pages=10
        )

        # After dedup: 1000 + 500 - 1 overlap = 1499 unique candles
        self.assertEqual(len(result), 1499)
        # Timestamps should be strictly ascending
        timestamps = [int(c[0]) for c in result]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertEqual(len(set(timestamps)), len(timestamps))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_cross_page_duplicate_conflict_fails_validation(self, mock_fetch):
        """Same timestamp with DIFFERENT content across pages → validation must FAIL."""
        start = 1700000000000
        interval_ms = 300000
        end = start + 1500 * interval_ms

        page1 = make_klines(start, interval_ms, 1000)
        page2 = make_klines(start + 999 * interval_ms, interval_ms, 500)
        # Mutate the overlapping candle in page2 to have a different close
        page2[0][4] = "999.9"  # Different close price — conflict

        mock_fetch.side_effect = [page1, page2]

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000, max_pages=10
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(validation["data_invalid"])
        self.assertTrue(any("conflicting content" in e for e in validation["errors"]))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_missing_one_candle_fails(self, mock_fetch):
        """A single missing candle → validation FAILS (not warns)."""
        start = 1700000000000
        interval_ms = 300000
        end = start + 100 * interval_ms

        klines = make_klines(start, interval_ms, 100)
        # Remove candle 50 — creates a gap
        del klines[50]

        mock_fetch.return_value = klines

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000, max_pages=5
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(validation["data_invalid"])
        self.assertTrue(any("Gap detected" in e for e in validation["errors"]))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_max_pages_truncation_marks_data_invalid(self, mock_fetch):
        """When max_pages is reached before end_time → data_invalid=True."""
        start = 1700000000000
        interval_ms = 300000
        end = start + 100000 * interval_ms  # Far future

        def side_effect(symbol, interval, limit, start_time, end_time):
            return make_klines(start_time, interval_ms, 1000)

        mock_fetch.side_effect = side_effect

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000, max_pages=3
        )

        # Should have exactly 3000 candles (3 pages × 1000)
        self.assertEqual(mock_fetch.call_count, 3)
        self.assertFalse(validation["valid"])
        self.assertTrue(validation["data_invalid"])
        self.assertTrue(any("max_pages" in e for e in validation["errors"]))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_validation_fail_closed_data_invalid_fitness(self, mock_fetch):
        """validation.valid=False → data_invalid must be True (caller must abort backtest).

        We use max_pages=1 with a large time range so the page cap is hit,
        forcing the paginator to mark data_invalid=True.
        """
        start = 1700000000000
        interval_ms = 300000
        # Range large enough to need many pages
        end = start + 5000 * interval_ms

        # Return a full page every call so pagination keeps wanting more
        def side_effect(symbol, interval, limit, start_time, end_time):
            return make_klines(start_time, interval_ms, 1000)

        mock_fetch.side_effect = side_effect

        _, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000, max_pages=1
        )

        # max_pages=1 → truncated → must be data_invalid
        self.assertFalse(validation["valid"])
        self.assertTrue(validation["data_invalid"])

    def test_90_day_5m_calculation(self):
        """Verify the 90-day 5m calculation from design doc"""
        candles_per_day = 24 * 12  # 5m = 12 candles per hour
        expected = 90 * candles_per_day
        self.assertEqual(expected, 25920)

        pages_needed = (expected + 999) // 1000
        self.assertEqual(pages_needed, 26)

    def test_auto_max_pages_calculation(self):
        """calculate_max_pages auto-calculates with safety margin."""
        start = 1700000000000
        interval_ms = 300000
        end = start + 25920 * interval_ms  # 90-day 5m range

        max_pages = calculate_max_pages(start, end, "5m", page_size=1000)
        # Should be >= 26 (exact) and cover with margin
        self.assertGreaterEqual(max_pages, 26)
        # With 10% margin: ceil(25920/1000 * 1.1) + 1 = 30
        self.assertLessEqual(max_pages, 35)


# ─── Retry / Backoff ─────────────────────────────────────────────────────────

class TestRetryBackoff(unittest.TestCase):
    """Test retry and backoff behaviour in fetch_klines."""

    def setUp(self):
        self.fetcher = BinanceFetcher()

    @patch.object(BinanceFetcher, '_rate_limit')  # suppress rate-limit sleeps
    @patch('data.fetcher.time.sleep')
    def test_429_with_retry_after_waits_correct_time(self, mock_sleep, mock_rate_limit):
        """429 with Retry-After header → wait exactly that many seconds."""
        raw_response = make_klines(1700000000000, 300000, 5)

        with patch.object(self.fetcher.session, 'get') as mock_get:
            resp_429 = Mock()
            resp_429.status_code = 429
            resp_429.headers = {"Retry-After": "10"}
            resp_429.raise_for_status.side_effect = None

            resp_ok = Mock()
            resp_ok.status_code = 200
            resp_ok.raise_for_status.return_value = None
            resp_ok.json.return_value = raw_response

            mock_get.side_effect = [resp_429, resp_ok]

            result = self.fetcher.fetch_klines("BTCUSDT", "5m", limit=5)

        # Should have slept for the Retry-After value (10s)
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        self.assertTrue(any(s == 10.0 for s in sleep_calls))
        self.assertEqual(len(result), 5)

    @patch.object(BinanceFetcher, '_rate_limit')  # suppress rate-limit sleeps
    @patch('data.fetcher.time.sleep')
    def test_5xx_exponential_backoff(self, mock_sleep, mock_rate_limit):
        """5xx errors → exponential backoff, eventually succeeds."""
        raw_response = make_klines(1700000000000, 300000, 3)

        with patch.object(self.fetcher.session, 'get') as mock_get:
            def make_5xx():
                r = Mock()
                r.status_code = 503
                r.headers = {}
                r.raise_for_status.side_effect = None
                return r

            resp_ok = Mock()
            resp_ok.status_code = 200
            resp_ok.raise_for_status.return_value = None
            resp_ok.json.return_value = raw_response

            mock_get.side_effect = [make_5xx(), make_5xx(), resp_ok]

            result = self.fetcher.fetch_klines("BTCUSDT", "5m", limit=3)

        # Should have slept twice with exponential delays: 2^0=1, 2^1=2
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        self.assertGreaterEqual(len(sleep_calls), 2)
        # Exponential: second sleep >= first
        self.assertGreaterEqual(sleep_calls[1], sleep_calls[0])
        self.assertEqual(len(result), 3)

    @patch.object(BinanceFetcher, '_rate_limit')  # suppress rate-limit sleeps
    @patch('data.fetcher.time.sleep')
    def test_permanent_errors_not_retried(self, mock_sleep, mock_rate_limit):
        """400, 401, 403 → should NOT be retried."""
        import requests as req_lib

        for status_code in (400, 401, 403):
            mock_sleep.reset_mock()
            with patch.object(self.fetcher.session, 'get') as mock_get:
                resp = Mock()
                resp.status_code = status_code
                resp.headers = {}
                http_err = req_lib.exceptions.HTTPError(response=resp)
                resp.raise_for_status.side_effect = http_err
                mock_get.return_value = resp

                with self.assertRaises(req_lib.RequestException):
                    self.fetcher.fetch_klines("BTCUSDT", "5m", limit=5)

            # No retries means no backoff sleep
            mock_sleep.assert_not_called()


# ─── KlineCache integration tests ────────────────────────────────────────────

class TestKlineCacheIntegration(unittest.TestCase):
    """Integration tests for KlineCache.load_or_fetch() cache write/read behaviour."""

    def _make_fetcher_mock(self, klines):
        """Return a Mock BinanceFetcher whose fetch_klines_paginated returns klines."""
        fetcher = Mock()
        validation_ok = {
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
        fetcher.fetch_klines_paginated.return_value = (klines, validation_ok)
        return fetcher

    def test_load_or_fetch_calls_api_on_cache_miss(self):
        """First call with no cache → API is called exactly once."""
        import tempfile
        import pandas as pd
        from pathlib import Path
        # Import KlineCache from backtest_engine
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app.genetic_engine.backtest_engine import KlineCache

        raw = make_klines(1700000000000, 300000, 100)
        fetcher = self._make_fetcher_mock(raw)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))

            start_ms = 1700000000000
            end_ms = start_ms + 100 * 300000

            df, validation = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=start_ms, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            # API called exactly once
            fetcher.fetch_klines_paginated.assert_called_once()
            self.assertIsNotNone(df)
            self.assertEqual(len(df), 100)
            self.assertFalse(validation["data_invalid"])

    def test_load_or_fetch_writes_to_cache_after_api_fetch(self):
        """After first API fetch, parquet file must exist on disk."""
        import tempfile
        import pandas as pd
        from pathlib import Path
        from app.genetic_engine.backtest_engine import KlineCache

        raw = make_klines(1700000000000, 300000, 100)
        fetcher = self._make_fetcher_mock(raw)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            start_ms = 1700000000000
            end_ms = start_ms + 100 * 300000

            cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=start_ms, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            parquet_path = Path(tmpdir) / "BTCUSDT_5m.parquet"
            self.assertTrue(parquet_path.exists(), "Cache file must be written after API fetch")

    def test_load_or_fetch_second_call_skips_api(self):
        """Second call with cache present → API is NOT called again."""
        import tempfile
        import pandas as pd
        from pathlib import Path
        from app.genetic_engine.backtest_engine import KlineCache

        raw = make_klines(1700000000000, 300000, 100)
        fetcher = self._make_fetcher_mock(raw)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            start_ms = 1700000000000
            end_ms = start_ms + 100 * 300000

            # First call — fetches from API and writes cache
            df1, _ = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=start_ms, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            # Second call — must serve from cache
            # Create a fresh KlineCache (clears memory cache too)
            cache2 = KlineCache(cache_dir=Path(tmpdir))
            df2, validation2 = cache2.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=start_ms, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            # API should only have been called once total
            fetcher.fetch_klines_paginated.assert_called_once()
            self.assertIsNotNone(df2)
            # validation is a valid dict when served from cache (never None)
            self.assertIsNotNone(validation2)
            self.assertTrue(validation2.get("valid"), "cache hit must return valid=True")
            self.assertFalse(validation2.get("data_invalid"), "cache hit must not be data_invalid")

    def test_load_or_fetch_does_not_cache_invalid_data(self):
        """When API returns data_invalid=True, no cache file must be written."""
        import tempfile
        import pandas as pd
        from pathlib import Path
        from app.genetic_engine.backtest_engine import KlineCache

        raw = make_klines(1700000000000, 300000, 50)
        fetcher = Mock()
        bad_validation = {
            "valid": False,
            "data_invalid": True,
            "actual_count": 50,
            "actual_start_ms": 1700000000000,
            "actual_end_ms": None,
            "duration_ms": None,
            "gaps": [],
            "warnings": [],
            "errors": ["[BTCUSDT] max_pages=1 reached before end_time"],
        }
        fetcher.fetch_klines_paginated.return_value = (raw, bad_validation)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = KlineCache(cache_dir=Path(tmpdir))
            start_ms = 1700000000000
            end_ms = start_ms + 100 * 300000

            df, validation = cache.load_or_fetch(
                fetcher, "BTCUSDT", "5m",
                start_ms=start_ms, end_ms=end_ms,
                limit=1000, paginate=True,
            )

            parquet_path = Path(tmpdir) / "BTCUSDT_5m.parquet"
            self.assertFalse(parquet_path.exists(), "Invalid data must NOT be cached")
            self.assertIsNone(df)
            self.assertTrue(validation["data_invalid"])


# ─── Fail-closed regression tests (V1 and V2 engines) ────────────────────────

class TestBacktestEngineFailClosed(unittest.TestCase):
    """Regression tests: invalid validation → data_invalid result, no normal fitness."""

    def _make_invalid_validation(self):
        return {
            "valid": False,
            "data_invalid": True,
            "actual_count": 50,
            "actual_start_ms": 1700000000000,
            "actual_end_ms": None,
            "duration_ms": None,
            "gaps": [],
            "warnings": [],
            "errors": ["[BTCUSDT] Gap detected: 1700000000000 -> 1700001800000 (6 candles missing)"],
        }

    def _make_mock_cache_returning_invalid(self):
        """Return a mock KlineCache.load_or_fetch that returns (None, invalid_validation)."""
        mock_cache = Mock()
        mock_cache.load_or_fetch.return_value = (None, self._make_invalid_validation())
        return mock_cache

    def test_v1_engine_aborts_on_invalid_data(self):
        """V1 GeneBacktestEngine.evaluate() must return data_invalid=True and no trades."""
        import tempfile
        from pathlib import Path
        from app.genetic_engine.backtest_engine import GeneBacktestEngine, KlineCache
        from app.genetic_engine.fitness import BacktestMetrics

        engine = GeneBacktestEngine()
        engine.cache = self._make_mock_cache_returning_invalid()

        # Build a minimal chromosome mock
        chrom = Mock()
        chrom.entry_genes = []
        chrom.exit_genes = []
        chrom.trend_filter = None
        chrom.volume_filter = None

        metrics, trades = engine.evaluate(chrom, "BTCUSDT", interval="5m", days=90, verbose=False)

        self.assertTrue(metrics.data_invalid,
                        "metrics.data_invalid must be True when validation fails")
        self.assertEqual(trades, [], "No trades must be produced when data is invalid")
        self.assertEqual(metrics.total_trades, 0,
                         "total_trades must be 0 when data is invalid")

    def test_v2_engine_aborts_on_invalid_data(self):
        """V2 GeneBacktestEngineV2.evaluate_v2() must return data_invalid=True and no trades."""
        from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2, V2BacktestResult

        engine = GeneBacktestEngineV2()

        # Patch fetcher to return invalid validation
        engine.fetcher = Mock()
        engine.fetcher.fetch_klines_paginated.return_value = (
            make_klines(1700000000000, 300000, 50),
            self._make_invalid_validation(),
        )

        chrom = Mock()
        chrom.entry_genes = []
        chrom.exit_genes = []
        chrom.trend_filter = None
        chrom.volume_filter = None

        result = engine.evaluate_v2(chrom, "BTCUSDT", interval="5m", days=90, verbose=False)

        self.assertIsInstance(result, V2BacktestResult)
        self.assertTrue(result.data_invalid,
                        "V2BacktestResult.data_invalid must be True when validation fails")
        self.assertEqual(result.strategy_trades, [],
                         "No strategy trades must be produced when data is invalid")
        self.assertTrue(result.strategy_metrics.data_invalid,
                        "strategy_metrics.data_invalid must also be True")

    def test_v1_normal_data_produces_fitness(self):
        """Sanity: with valid data, V1 must NOT set data_invalid."""
        from app.genetic_engine.backtest_engine import GeneBacktestEngine, KlineCache
        import pandas as pd

        engine = GeneBacktestEngine()

        # Build a small valid DataFrame (200 rows)
        n = 200
        start_ms = 1700000000000
        interval_ms = 300000
        idx = pd.date_range(
            pd.Timestamp(start_ms, unit='ms', tz='UTC'),
            periods=n, freq='5min'
        )
        df = pd.DataFrame({
            'open': [100.0] * n,
            'high': [101.0] * n,
            'low': [99.0] * n,
            'close': [100.5] * n,
            'volume': [1000.0] * n,
        }, index=idx)

        valid_validation = {
            "valid": True,
            "data_invalid": False,
            "actual_count": n,
            "actual_start_ms": start_ms,
            "actual_end_ms": start_ms + (n - 1) * interval_ms,
            "duration_ms": (n - 1) * interval_ms,
            "gaps": [],
            "warnings": [],
            "errors": [],
        }

        engine.cache = Mock()
        engine.cache.load_or_fetch.return_value = (df, valid_validation)

        chrom = Mock()
        chrom.entry_genes = []
        chrom.exit_genes = []
        chrom.trend_filter = None
        chrom.volume_filter = None

        metrics, trades = engine.evaluate(chrom, "BTCUSDT", interval="5m", days=90, verbose=False)

        self.assertFalse(metrics.data_invalid,
                         "data_invalid must be False when data is valid")


# ─── Signature / Compatibility ────────────────────────────────────────────────

class TestBinanceCompatibility(unittest.TestCase):
    """Ensure existing fetch_klines signature is preserved"""

    def test_fetch_klines_signature_unchanged(self):
        import inspect
        sig = inspect.signature(BinanceFetcher.fetch_klines)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ['self', 'symbol', 'interval', 'limit', 'start_time', 'end_time'])

        defaults = {
            p.name: p.default
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        }
        self.assertEqual(defaults['limit'], 500)
        self.assertEqual(defaults['start_time'], None)
        self.assertEqual(defaults['end_time'], None)

    def test_get_klines_signature_unchanged(self):
        import inspect
        sig = inspect.signature(BinanceFetcher.get_klines)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ['self', 'symbol', 'interval', 'limit'])

    def test_normalize_kline_data_is_method_on_class(self):
        """normalize_kline_data must be a proper method, not a standalone function."""
        self.assertTrue(hasattr(BinanceFetcher, 'normalize_kline_data'))
        self.assertTrue(callable(BinanceFetcher.normalize_kline_data))


if __name__ == '__main__':
    unittest.main(verbosity=2)
