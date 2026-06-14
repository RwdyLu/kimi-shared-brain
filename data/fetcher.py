"""
Binance Data Fetcher Module
Binance 資料抓取模組

BTC/ETH Monitoring System - Data Layer
BTC/ETH 監測系統 - 資料層

This module provides data fetching capabilities from Binance Spot API.
本模組提供從 Binance 現貨 API 抓取資料的功能。

Author: kimiclaw_bot
Version: 1.1.0
Date: 2026-04-06
"""

import requests
import time
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime


# Constants / 常數
BINANCE_BASE_URL = "https://api.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"

# Rate limiting / 速率限制
MAX_REQUESTS_PER_MINUTE = 1200
REQUEST_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE  # Minimum interval between requests

# Supported symbols / 支援的標的
SUPPORTED_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
]

# Supported intervals / 支援的時間框架
SUPPORTED_INTERVALS = ["1m", "5m", "15m"]

# Interval to milliseconds mapping / 時間框架對應毫秒數
INTERVAL_MS = {
    "1m": 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
}

# Retry configuration / 重試設定
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403}
MAX_RETRIES = 5
BACKOFF_BASE = 2.0   # seconds
BACKOFF_CAP = 60.0   # seconds

# max_pages safety margin factor / max_pages 安全邊際係數
MAX_PAGES_SAFETY_MARGIN = 1.1


def interval_to_ms(interval: str) -> int:
    """
    Convert interval string to milliseconds / 將時間框架字串轉換為毫秒數

    Args:
        interval: Kline interval (e.g., "5m") / K 線時間框架

    Returns:
        Milliseconds per candle / 每根 K 線的毫秒數

    Raises:
        ValueError: If interval is not supported / 若時間框架不受支援
    """
    if interval not in INTERVAL_MS:
        raise ValueError(
            f"Interval '{interval}' not supported for pagination. "
            f"Supported: {list(INTERVAL_MS.keys())}"
        )
    return INTERVAL_MS[interval]


def calculate_max_pages(
    start_ms: int,
    end_ms: int,
    interval: str,
    page_size: int = 1000,
    safety_margin: float = MAX_PAGES_SAFETY_MARGIN,
) -> int:
    """
    Auto-calculate max_pages from time range / 從時間範圍自動計算 max_pages

    Args:
        start_ms: Start timestamp in ms / 開始時間戳 (毫秒)
        end_ms: End timestamp in ms / 結束時間戳 (毫秒)
        interval: Kline interval / K 線時間框架
        page_size: Candles per page / 每頁 K 線數量
        safety_margin: Multiplier for safety buffer / 安全邊際係數

    Returns:
        Recommended max_pages value / 建議的 max_pages 值
    """
    interval_ms = interval_to_ms(interval)
    candles_needed = (end_ms - start_ms) / interval_ms
    pages_needed = candles_needed / page_size
    return max(1, int(pages_needed * safety_margin) + 1)


def validate_klines(
    klines: List[List],
    expected_start_ms: Optional[int] = None,
    expected_end_ms: Optional[int] = None,
    expected_count: Optional[int] = None,
    interval: Optional[str] = None,
    symbol: Optional[str] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """
    Validate kline data integrity / 驗證 K 線資料完整性

    Gaps and duplicate timestamps with conflicting content are treated as
    ERRORS (not warnings), making validation fail-closed.

    Args:
        klines: Raw kline data from Binance API / 原始 K 線資料
        expected_start_ms: Expected start timestamp (ms) / 預期開始時間戳
        expected_end_ms: Expected end timestamp (ms) / 預期結束時間戳
        expected_count: Expected number of candles / 預期 K 線數量
        interval: Kline interval for continuity check / 時間框架（用於連續性檢查）
        symbol: Symbol for error messages / 標的（用於錯誤訊息）
        strict: When True (backtest mode), count/start/end mismatches set
                valid=False and data_invalid=True instead of just warnings.

    Returns:
        Validation result dict / 驗證結果字典
        {
            "valid": bool,
            "actual_count": int,
            "actual_start_ms": int,
            "actual_end_ms": int,
            "duration_ms": int,
            "gaps": List[Tuple[int, int]],  # 時間缺口列表
            "warnings": List[str],
            "errors": List[str],
        }
    """
    result = {
        "valid": False,
        "actual_count": len(klines),
        "actual_start_ms": None,
        "actual_end_ms": None,
        "duration_ms": None,
        "gaps": [],
        "warnings": [],
        "errors": [],
        "data_invalid": False,
    }

    prefix = f"[{symbol}] " if symbol else ""

    if not klines:
        result["errors"].append(f"{prefix}Empty kline data")
        return result

    # Extract timestamps
    timestamps = [int(c[0]) for c in klines if len(c) >= 1]
    if not timestamps:
        result["errors"].append(f"{prefix}No valid timestamps found")
        return result

    result["actual_start_ms"] = min(timestamps)
    result["actual_end_ms"] = max(timestamps)
    result["duration_ms"] = result["actual_end_ms"] - result["actual_start_ms"]

    # Check expected count
    if expected_count is not None and len(klines) < expected_count:
        msg = (
            f"{prefix}Expected {expected_count} candles, got {len(klines)} "
            f"(short by {expected_count - len(klines)})"
        )
        if strict:
            result["errors"].append(msg)
            result["data_invalid"] = True
        else:
            result["warnings"].append(msg)

    # Check expected start time
    if expected_start_ms is not None:
        margin_ms = interval_to_ms(interval) * 2 if interval else 60000
        if abs(result["actual_start_ms"] - expected_start_ms) > margin_ms:
            msg = (
                f"{prefix}Start time mismatch: expected {expected_start_ms}, "
                f"got {result['actual_start_ms']}"
            )
            if strict:
                result["errors"].append(msg)
                result["data_invalid"] = True
            else:
                result["warnings"].append(msg)

    # Check expected end time
    if expected_end_ms is not None:
        margin_ms = interval_to_ms(interval) * 2 if interval else 60000
        if abs(result["actual_end_ms"] - expected_end_ms) > margin_ms:
            msg = (
                f"{prefix}End time mismatch: expected {expected_end_ms}, "
                f"got {result['actual_end_ms']}"
            )
            if strict:
                result["errors"].append(msg)
                result["data_invalid"] = True
            else:
                result["warnings"].append(msg)

    # Check for gaps and duplicates — both are now ERRORS (fail-closed)
    if interval and len(timestamps) > 1:
        interval_ms = interval_to_ms(interval)
        sorted_ts = sorted(timestamps)
        for i in range(1, len(sorted_ts)):
            gap = sorted_ts[i] - sorted_ts[i - 1]
            if gap == 0:
                # Exact duplicate timestamp — error
                result["errors"].append(
                    f"{prefix}Duplicate timestamp at {sorted_ts[i]}"
                )
            elif gap != interval_ms:
                # Gap or unexpected spacing — error
                result["gaps"].append((sorted_ts[i - 1], sorted_ts[i]))
                result["errors"].append(
                    f"{prefix}Gap detected: {sorted_ts[i-1]} -> {sorted_ts[i]} "
                    f"({gap // interval_ms} candles missing)"
                )

    # Validate individual candle structure
    invalid_candles = 0
    for i, candle in enumerate(klines):
        if len(candle) < 6:
            invalid_candles += 1
            continue
        try:
            float(candle[1])  # open
            float(candle[4])  # close
        except (ValueError, IndexError):
            invalid_candles += 1

    if invalid_candles > 0:
        result["warnings"].append(
            f"{prefix}{invalid_candles}/{len(klines)} candles have invalid structure"
        )

    result["valid"] = len(result["errors"]) == 0 and invalid_candles == 0
    if not result["valid"] and result.get("data_invalid") is False:
        # Errors from gaps/duplicates/candle structure also mark data_invalid
        if result["errors"]:
            result["data_invalid"] = True
    return result


@dataclass
class KlineData:
    """
    Normalized Kline data structure / 標準化 K 線資料結構

    Attributes:
        timestamp: Kline open timestamp in milliseconds / K線開盤時間戳 (毫秒)
        open: Opening price / 開盤價
        high: Highest price / 最高價
        low: Lowest price / 最低價
        close: Closing price / 收盤價
        volume: Trading volume / 成交量
    """
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary / 轉換為字典"""
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KlineData":
        """Create from dictionary / 從字典建立"""
        return cls(
            timestamp=data["timestamp"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"]
        )


class BinanceFetcher:
    """
    Binance API data fetcher / Binance API 資料抓取器

    Provides methods to fetch and normalize kline data from Binance.
    提供從 Binance 抓取並標準化 K 線資料的方法。
    """

    def __init__(self, base_url: str = BINANCE_BASE_URL):
        """
        Initialize the fetcher / 初始化抓取器

        Args:
            base_url: Binance API base URL / Binance API 基礎 URL
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self._last_request_time: Optional[float] = None

    def _rate_limit(self) -> None:
        """
        Apply rate limiting / 套用速率限制

        Ensures we don't exceed Binance's rate limits.
        確保不超過 Binance 的速率限制。
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < REQUEST_INTERVAL:
                time.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _validate_symbol(self, symbol: str) -> None:
        """
        Validate symbol / 驗證標的

        Args:
            symbol: Trading pair symbol / 交易對標的

        Raises:
            ValueError: If symbol is not supported / 若標的不受支援
        """
        if symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(
                f"Symbol '{symbol}' is not supported. "
                f"Supported symbols: {SUPPORTED_SYMBOLS}"
            )

    def _validate_interval(self, interval: str) -> None:
        """
        Validate interval / 驗證時間框架

        Args:
            interval: Kline interval / K 線時間框架

        Raises:
            ValueError: If interval is not supported / 若時間框架不受支援
        """
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"Interval '{interval}' is not supported. "
                f"Supported intervals: {SUPPORTED_INTERVALS}"
            )

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[List]:
        """
        Fetch raw kline data from Binance with retry/backoff / 從 Binance 抓取原始 K 線資料（含重試/退避）

        Retries on: timeout, 429, 500, 502, 503, 504 with exponential backoff.
        Respects Retry-After header on 429.
        Does NOT retry on: 400, 401, 403 (permanent errors).

        Args:
            symbol: Trading pair (e.g., "BTCUSDT") / 交易對
            interval: Kline interval (e.g., "5m") / K 線時間框架
            limit: Number of candles to fetch (max 1000) / K 線數量
            start_time: Start timestamp in ms / 開始時間戳 (毫秒)
            end_time: End timestamp in ms / 結束時間戳 (毫秒)

        Returns:
            Raw kline data from Binance API / 來自 Binance API 的原始 K 線資料

        Raises:
            ValueError: If symbol or interval is invalid / 若標的或時間框架無效
            requests.RequestException: If API request fails / 若 API 請求失敗
        """
        # Validate inputs / 驗證輸入
        self._validate_symbol(symbol)
        self._validate_interval(interval)

        # Build request / 建立請求
        url = f"{self.base_url}{KLINES_ENDPOINT}"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000)  # Binance max is 1000
        }

        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            # Apply rate limiting / 套用速率限制
            self._rate_limit()

            try:
                response = self.session.get(url, params=params, timeout=30)

                # Permanent errors — do not retry
                if response.status_code in NON_RETRYABLE_STATUS_CODES:
                    response.raise_for_status()

                # Retryable HTTP errors
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = None
                    if response.status_code == 429:
                        retry_after_str = response.headers.get("Retry-After")
                        if retry_after_str is not None:
                            try:
                                retry_after = float(retry_after_str)
                            except ValueError:
                                pass
                    if retry_after is not None:
                        wait = min(retry_after, BACKOFF_CAP)
                    else:
                        wait = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(wait)
                        last_exc = requests.RequestException(
                            f"HTTP {response.status_code} on attempt {attempt + 1}"
                        )
                        continue
                    else:
                        response.raise_for_status()

                response.raise_for_status()
                data = response.json()

                if not data:
                    raise ValueError(f"Empty response for {symbol} {interval}")

                return data

            except requests.exceptions.Timeout as exc:
                last_exc = requests.RequestException(
                    f"Request timeout for {symbol} {interval}"
                )
                if attempt < MAX_RETRIES - 1:
                    wait = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
                    time.sleep(wait)
                    continue
                raise last_exc from exc
            except requests.exceptions.HTTPError as exc:
                # Already handled above for retryable; permanent errors bubble here
                raise requests.RequestException(
                    f"HTTP error {exc.response.status_code}: {exc.response.text}"
                ) from exc
            except requests.exceptions.RequestException as exc:
                last_exc = requests.RequestException(f"Request failed: {str(exc)}")
                if attempt < MAX_RETRIES - 1:
                    wait = min(BACKOFF_BASE ** attempt, BACKOFF_CAP)
                    time.sleep(wait)
                    continue
                raise last_exc from exc

        # Should not reach here, but raise last exception if we do
        raise last_exc or requests.RequestException(
            f"All {MAX_RETRIES} retries exhausted for {symbol} {interval}"
        )

    def fetch_klines_paginated(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
        validate: bool = True,
        verbose: bool = False,
        max_pages: Optional[int] = None,
        strict_validation: bool = False,
    ) -> Tuple[List[List], Dict[str, Any]]:
        """
        Paginated kline fetcher for large date ranges / 大範圍分頁 K 線抓取器

        Binance API limits each request to 1000 candles. This method
        automatically paginates across multiple requests to fetch the
        complete date range, ensuring backtest_days=90 (25,920 x 5m)
        can be fully retrieved.

        max_pages is auto-calculated from the time range if not provided.
        If the page cap is reached before the full range is covered, the
        result is marked invalid (data_invalid) so the caller can abort.

        After all pages are collected, data is deduplicated by timestamp.
        If the same timestamp has different content across pages, validation
        FAILS (not warns).  Data is sorted by timestamp ascending.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT") / 交易對
            interval: Kline interval (e.g., "5m") / K 線時間框架
            start_time: Start timestamp in ms / 開始時間戳 (毫秒)
            end_time: End timestamp in ms / 結束時間戳 (毫秒)
            limit: Candles per page (max 1000) / 每頁 K 線數量
            validate: Whether to validate data / 是否驗證資料
            verbose: Whether to print progress / 是否輸出進度
            max_pages: Maximum pages to fetch (None = auto-calculate) / 最多抓取的頁數

        Returns:
            Tuple of (klines, validation_result) / (K 線資料, 驗證結果)
            validation_result["valid"] is False when data_invalid.

        Raises:
            ValueError: If no data is returned / 若未返回任何資料
        """
        self._validate_symbol(symbol)
        self._validate_interval(interval)

        interval_ms = interval_to_ms(interval)
        page_size = min(limit, 1000)

        # Auto-calculate max_pages if not supplied
        if max_pages is None:
            max_pages = calculate_max_pages(start_time, end_time, interval, page_size)

        all_klines: List[List] = []
        page_count = 0
        max_pages_reached = False

        current_start = start_time

        while page_count < max_pages:
            page_count += 1

            klines = self.fetch_klines(
                symbol=symbol,
                interval=interval,
                limit=page_size,
                start_time=current_start,
                end_time=end_time,
            )

            if not klines:
                break

            all_klines.extend(klines)

            last_ts = int(klines[-1][0])
            if last_ts <= current_start:
                break

            next_start = last_ts + interval_ms

            if next_start >= end_time:
                break

            if len(klines) < page_size:
                break

            current_start = next_start

        else:
            # Loop exhausted max_pages without finishing
            if current_start < end_time:
                max_pages_reached = True

        if not all_klines:
            raise ValueError(f"Empty response for {symbol} {interval} (paginated)")

        # ── Deduplication ──────────────────────────────────────────────────────
        # Build a map: timestamp -> first candle seen
        # If same ts has different content → conflict error
        seen: Dict[int, List] = {}
        conflict_timestamps: List[int] = []
        for candle in all_klines:
            ts = int(candle[0])
            if ts in seen:
                if candle != seen[ts]:
                    conflict_timestamps.append(ts)
            else:
                seen[ts] = candle

        # Sort by timestamp ascending
        all_klines = [seen[ts] for ts in sorted(seen.keys())]

        if verbose:
            print(
                f"[fetch_paginated] {symbol} {interval}: "
                f"{page_count} pages, {len(all_klines)} candles fetched "
                f"({start_time} -> {end_time})"
            )

        # ── Validation ─────────────────────────────────────────────────────────
        validation: Dict[str, Any] = {
            "valid": True,
            "actual_count": len(all_klines),
            "actual_start_ms": None,
            "actual_end_ms": None,
            "duration_ms": None,
            "gaps": [],
            "warnings": [],
            "errors": [],
            "data_invalid": False,
        }

        if conflict_timestamps:
            for ts in conflict_timestamps:
                validation["errors"].append(
                    f"[{symbol}] Duplicate timestamp with conflicting content: {ts}"
                )
            validation["valid"] = False
            validation["data_invalid"] = True

        if max_pages_reached:
            validation["errors"].append(
                f"[{symbol}] max_pages={max_pages} reached before end_time — "
                f"data truncated, backtest aborted"
            )
            validation["valid"] = False
            validation["data_invalid"] = True

        if validate:
            expected_count = (end_time - start_time) // interval_ms
            v = validate_klines(
                klines=all_klines,
                expected_start_ms=start_time,
                expected_end_ms=end_time,
                expected_count=expected_count,
                interval=interval,
                symbol=symbol,
                strict=strict_validation,
            )
            # Merge validation results
            validation["actual_count"] = v["actual_count"]
            validation["actual_start_ms"] = v["actual_start_ms"]
            validation["actual_end_ms"] = v["actual_end_ms"]
            validation["duration_ms"] = v["duration_ms"]
            validation["gaps"].extend(v["gaps"])
            validation["warnings"].extend(v["warnings"])
            validation["errors"].extend(v["errors"])
            if not v["valid"]:
                validation["valid"] = False
                validation["data_invalid"] = True

        return all_klines, validation

    def normalize_kline_data(self, raw_data: List[List]) -> List[KlineData]:
        """
        Normalize raw kline data / 標準化原始 K 線資料

        Converts Binance raw kline format to standardized KlineData objects.
        將 Binance 原始 K 線格式轉換為標準化的 KlineData 物件。

        Args:
            raw_data: Raw kline data from Binance API / 來自 Binance API 的原始 K 線資料

        Returns:
            List of normalized KlineData objects / 標準化 KlineData 物件列表

        Raises:
            ValueError: If data format is invalid / 若資料格式無效
        """
        if not raw_data:
            return []

        normalized = []

        for i, candle in enumerate(raw_data):
            if len(candle) < 6:
                raise ValueError(
                    f"Invalid candle data at index {i}: "
                    f"expected at least 6 fields, got {len(candle)}"
                )

            try:
                kline = KlineData(
                    timestamp=int(candle[0]),      # Open time
                    open=float(candle[1]),          # Open price
                    high=float(candle[2]),          # High price
                    low=float(candle[3]),           # Low price
                    close=float(candle[4]),         # Close price
                    volume=float(candle[5])         # Volume
                )
                normalized.append(kline)
            except (ValueError, IndexError) as e:
                raise ValueError(f"Failed to parse candle at index {i}: {str(e)}")

        return normalized

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500
    ) -> List[KlineData]:
        """
        Fetch and normalize kline data / 抓取並標準化 K 線資料

        Convenience method that combines fetch_klines and normalize_kline_data.
        結合 fetch_klines 與 normalize_kline_data 的便利方法。

        Args:
            symbol: Trading pair (e.g., "BTCUSDT") / 交易對
            interval: Kline interval (e.g., "5m") / K 線時間框架
            limit: Number of candles to fetch / K 線數量

        Returns:
            List of normalized KlineData objects / 標準化 KlineData 物件列表
        """
        raw_data = self.fetch_klines(symbol, interval, limit)
        return self.normalize_kline_data(raw_data)

    def get_multi_timeframe_data(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None,
        limits: Optional[Dict[str, int]] = None
    ) -> Dict[str, List[KlineData]]:
        """
        Fetch data for multiple timeframes / 抓取多時間框架資料

        Args:
            symbol: Trading pair (e.g., "BTCUSDT") / 交易對
            timeframes: List of intervals to fetch / 要抓取的時間框架列表
                       Defaults to all supported intervals / 預設為所有支援的時間框架
            limits: Dict mapping interval to limit / 時間框架到數量的對應字典
                   e.g., {"1m": 25, "5m": 250, "15m": 10}

        Returns:
            Dict mapping interval to KlineData list / 時間框架到 KlineData 列表的字典

        Example:
            {
                "1m": [KlineData, ...],
                "5m": [KlineData, ...],
                "15m": [KlineData, ...]
            }
        """
        if timeframes is None:
            timeframes = SUPPORTED_INTERVALS

        # Default limits per T-022 spec / 根據 T-022 規格的預設數量
        default_limits = {
            "1m": 25,    # For volume avg(20) + buffer
            "5m": 250,   # For MA240 + buffer
            "15m": 10    # For consecutive candle detection
        }

        if limits is None:
            limits = default_limits

        result = {}

        for interval in timeframes:
            limit = limits.get(interval, 100)
            result[interval] = self.get_klines(symbol, interval, limit)

        return result

    def get_latest_price(self, symbol: str) -> Dict[str, float]:
        """
        Get latest price data / 取得最新價格資料

        Args:
            symbol: Trading pair / 交易對

        Returns:
            Latest price data / 最新價格資料
        """
        try:
            url = f"{self.base_url}/api/v3/ticker/24hr"
            params = {"symbol": symbol}

            self._rate_limit()
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            return {
                "symbol": symbol,
                "price": float(data["lastPrice"]),
                "volume": float(data["volume"]),
                "price_change_24h": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"])
            }
        except Exception as e:
            # Fallback to basic price endpoint
            try:
                url = f"{self.base_url}/api/v3/ticker/price"
                params = {"symbol": symbol}
                response = self.session.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                return {
                    "symbol": symbol,
                    "price": float(data["price"]),
                    "volume": 0,
                    "price_change_24h": 0,
                    "high_24h": 0,
                    "low_24h": 0
                }
            except Exception:
                raise


def create_fetcher() -> BinanceFetcher:
    """
    Factory function to create a fetcher instance / 建立抓取器實例的工廠函式

    Returns:
        BinanceFetcher instance / BinanceFetcher 實例
    """
    return BinanceFetcher()


# Example usage / 使用範例
if __name__ == "__main__":
    # This section is for testing/demonstration only
    # 此區塊僅供測試/展示使用

    print("Binance Data Fetcher Module")
    print("Binance 資料抓取模組")
    print("=" * 40)

    # Show supported symbols and intervals
    print(f"\nSupported symbols / 支援的標的: {SUPPORTED_SYMBOLS}")
    print(f"Supported intervals / 支援的時間框架: {SUPPORTED_INTERVALS}")

    # Example: Create fetcher
    print("\nExample usage / 使用範例:")
    print("  fetcher = create_fetcher()")
    print("  data = fetcher.get_klines('BTCUSDT', '5m', limit=100)")
    print("  multi_tf = fetcher.get_multi_timeframe_data('BTCUSDT')")
