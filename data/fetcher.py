"""
Binance Data Fetcher Module
Binance 資料抓取模組

BTC/ETH Monitoring System - Data Layer
BTC/ETH 監測系統 - 資料層

This module provides data fetching capabilities from Binance Spot API.
本模組提供從 Binance 現貨 API 抓取資料的功能。

Author: kimiclaw_bot
Version: 1.0.0
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
        Fetch raw kline data from Binance / 從 Binance 抓取原始 K 線資料
        
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
        
        # Apply rate limiting / 套用速率限制
        self._rate_limit()
        
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
        
        # Make request / 發送請求
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                raise ValueError(f"Empty response for {symbol} {interval}")
            
            return data
            
        except requests.exceptions.Timeout:
            raise requests.RequestException(f"Request timeout for {symbol} {interval}")
        except requests.exceptions.HTTPError as e:
            raise requests.RequestException(f"HTTP error {e.response.status_code}: {e.response.text}")
        except requests.exceptions.RequestException as e:
            raise requests.RequestException(f"Request failed: {str(e)}")
    
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
                raise ValueError(f"Invalid candle data at index {i}: expected at least 6 fields, got {len(candle)}")
            
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
        import requests
        
        try:
            url = f"{self.base_url}/api/v3/ticker/24hr"
            params = {"symbol": symbol}
            
            self._rate_limit()
            response = requests.get(url, params=params, timeout=10)
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
            self.logger.error(f"Error fetching price for {symbol}: {e}")
            # Fallback to basic price endpoint
            try:
                url = f"{self.base_url}/api/v3/ticker/price"
                params = {"symbol": symbol}
                response = requests.get(url, params=params, timeout=10)
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
