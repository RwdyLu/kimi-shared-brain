"""
Tests for paginated kline fetching and data validation.
Tests / 分頁 K 線抓取與資料驗證測試

Phase 1 of GA Core Principles: Fix 1000-candle limit for 90-day backtest.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, call
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetcher import (
    BinanceFetcher,
    validate_klines,
    interval_to_ms,
    INTERVAL_MS,
)


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

    def test_gap_detection(self):
        start = 1700000000000
        klines = self._make_klines(start, 300000, 10)
        # Insert a big gap at index 5: jump from index 4 to index 15
        klines[5][0] = start + 15 * 300000  # 1700004500000
        result = validate_klines(klines, interval="5m")
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["gaps"]), 1)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("Gap detected", result["warnings"][0])
        self.assertIn("candles missing", result["warnings"][0])

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


class TestFetchKlinesPaginated(unittest.TestCase):
    """Test BinanceFetcher.fetch_klines_paginated"""

    def setUp(self):
        self.fetcher = BinanceFetcher()

    def _make_page(self, start_ms, interval_ms, count):
        """Generate a page of klines"""
        return [
            [
                start_ms + i * interval_ms,
                100.0, 101.0, 99.0, 100.5, 1000.0,
                start_ms + (i + 1) * interval_ms - 1,
                100000.0, 100, 500.0, 50000.0, "0"
            ]
            for i in range(count)
        ]

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_single_page(self, mock_fetch):
        """When all data fits in one page"""
        start = 1700000000000
        interval_ms = 300000
        end = start + 500 * interval_ms
        
        klines = self._make_page(start, interval_ms, 500)
        mock_fetch.return_value = klines
        
        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000
        )
        
        self.assertEqual(len(result), 500)
        self.assertEqual(mock_fetch.call_count, 1)
        self.assertTrue(validation["valid"])
        mock_fetch.assert_called_with(
            symbol="BTCUSDT",
            interval="5m",
            limit=1000,
            start_time=start,
            end_time=end,
        )

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_multi_page(self, mock_fetch):
        """When data spans multiple pages"""
        start = 1700000000000
        interval_ms = 300000
        page_size = 1000
        end = start + 2500 * interval_ms  # 2.5 pages worth
        
        # Page 1: 1000 candles
        page1 = self._make_page(start, interval_ms, 1000)
        # Page 2: 1000 candles starting from page1 end
        page2_start = start + 1000 * interval_ms
        page2 = self._make_page(page2_start, interval_ms, 1000)
        # Page 3: 500 candles (partial, triggers end condition)
        page3_start = start + 2000 * interval_ms
        page3 = self._make_page(page3_start, interval_ms, 500)
        
        mock_fetch.side_effect = [page1, page2, page3]
        
        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=page_size
        )
        
        self.assertEqual(len(result), 2500)
        self.assertEqual(mock_fetch.call_count, 3)
        self.assertTrue(validation["valid"])
        
        # Check calls use correct pagination
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
        
        # Only 1500 candles exist
        page1 = self._make_page(start, interval_ms, 1000)
        page2_start = start + 1000 * interval_ms
        page2 = self._make_page(page2_start, interval_ms, 500)  # Only 500 left
        
        mock_fetch.side_effect = [page1, page2]
        
        result, _ = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000
        )
        
        self.assertEqual(len(result), 1500)
        self.assertEqual(mock_fetch.call_count, 2)

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_empty_response(self, mock_fetch):
        """When API returns empty data"""
        mock_fetch.return_value = []
        
        with self.assertRaises(ValueError) as ctx:
            self.fetcher.fetch_klines_paginated(
                "BTCUSDT", "5m", 1700000000000, 1700000001000
            )
        self.assertIn("Empty response", str(ctx.exception))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_validation_warnings(self, mock_fetch):
        """Test that validation warnings are returned"""
        start = 1700000000000
        interval_ms = 300000
        end = start + 1000 * interval_ms

        # Only return 500 candles when 1000 expected
        klines = self._make_page(start, interval_ms, 500)
        mock_fetch.return_value = klines

        result, validation = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000
        )

        self.assertEqual(len(result), 500)
        self.assertTrue(validation["valid"])  # Structurally valid
        self.assertGreaterEqual(len(validation["warnings"]), 1)
        self.assertTrue(any("Expected 1000 candles" in w for w in validation["warnings"]))

    @patch.object(BinanceFetcher, 'fetch_klines')
    def test_max_pages_safety_cap(self, mock_fetch):
        """Test safety cap of 50 pages"""
        start = 1700000000000
        interval_ms = 300000
        # Request way more than 50 pages worth
        end = start + 100000 * interval_ms

        def side_effect(symbol, interval, limit, start_time, end_time):
            # Return a page starting at the requested start_time
            return self._make_page(start_time, interval_ms, 1000)

        mock_fetch.side_effect = side_effect

        result, _ = self.fetcher.fetch_klines_paginated(
            "BTCUSDT", "5m", start, end, limit=1000
        )

        # Should stop at 50 pages (50,000 candles)
        self.assertEqual(len(result), 50000)
        self.assertEqual(mock_fetch.call_count, 50)

    def test_90_day_5m_calculation(self):
        """Verify the 90-day 5m calculation from design doc"""
        # 90 days * 24 hours * 12 candles/hour = 25,920 candles
        candles_per_day = 24 * 12  # 5m = 12 candles per hour
        expected = 90 * candles_per_day
        self.assertEqual(expected, 25920)
        
        # With 1000 candles per page, need 26 pages
        pages_needed = (expected + 999) // 1000
        self.assertEqual(pages_needed, 26)


class TestBinanceCompatibility(unittest.TestCase):
    """Ensure existing fetch_klines signature is preserved"""

    def test_fetch_klines_signature_unchanged(self):
        """fetch_klines must still accept all original parameters"""
        import inspect
        sig = inspect.signature(BinanceFetcher.fetch_klines)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ['self', 'symbol', 'interval', 'limit', 'start_time', 'end_time'])
        
        # Check defaults
        defaults = {
            p.name: p.default
            for p in sig.parameters.values()
            if p.default is not inspect.Parameter.empty
        }
        self.assertEqual(defaults['limit'], 500)
        self.assertEqual(defaults['start_time'], None)
        self.assertEqual(defaults['end_time'], None)

    def test_get_klines_signature_unchanged(self):
        """get_klines must still work as before"""
        import inspect
        sig = inspect.signature(BinanceFetcher.get_klines)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ['self', 'symbol', 'interval', 'limit'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
