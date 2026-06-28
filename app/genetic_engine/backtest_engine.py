#!/usr/bin/env python3
"""
Gene Backtest Engine / 基因回測引擎

專為策略基因體評估設計的快速回測引擎。
不生成圖表，只輸出數字。基於純 pandas/numpy，無需 talib。

參考:
- Freqtrade backtesting 邏輯
- Backtrader 的逐 K 線執行模型

Author: second_bot
Date: 2026-05-22
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from data.fetcher import BinanceFetcher, KlineData
from data.providers import DataProvider, require_official_data
from .gene_library import IndicatorGene, IndicatorType, ConditionType
from .chromosome import StrategyChromosome, RiskGenes
from .fitness import calculate_metrics, compute_fitness, compute_fitness_details, BacktestMetrics


# ═══════════════════════════════════════════════════════════════════════════════
# K線本地快取
# ═══════════════════════════════════════════════════════════════════════════════

class KlineCache:
    """
    本地 Parquet K線快取。
    優先從 data/kline_cache/ 讀取，不存在時回退到 API。
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            self.cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "kline_cache"
        else:
            self.cache_dir = Path(cache_dir)
        self._memory_cache: Dict[str, pd.DataFrame] = {}
    
    def _cache_key(self, symbol: str, interval: str) -> str:
        safe_symbol = symbol.replace("/", "_").replace(":", "_")
        return f"{safe_symbol}_{interval}"
    
    def _parquet_path(self, symbol: str, interval: str) -> Path:
        return self.cache_dir / f"{self._cache_key(symbol, interval)}.parquet"

    def _normalize_datetime_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize cache data to a UTC DatetimeIndex across pandas/pyarrow versions."""
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        elif df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        return df.sort_index()

    def _index_open_time_ms(self, df: pd.DataFrame) -> pd.Series:
        """Return candle open times as integer milliseconds."""
        if "_open_time_ms" in df.columns:
            values = df["_open_time_ms"].astype("int64")
            return pd.Series(values.to_numpy(), index=df.index)
        values = [int(pd.Timestamp(ts).timestamp() * 1000) for ts in df.index]
        return pd.Series(values, index=df.index, dtype="int64")
    
    def has_cache(self, symbol: str, interval: str) -> bool:
        return self._parquet_path(symbol, interval).exists()
    
    def load(self, symbol: str, interval: str,
             start_ms: Optional[int] = None,
             end_ms: Optional[int] = None,
             session_based: bool = False) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        """
        從快取載入 K 線 DataFrame，可選時間過濾。
        使用記憶體二級快取加速重複讀取。

        Returns:
            (df, validation) tuple.
            - (df, {"valid": True, ...}) on a good cache hit
            - (None, {"valid": False, "data_invalid": True, "errors": [...]}) on miss or bad data
              Never returns validation=None; the caller can always inspect the dict.
        """
        from data.fetcher import interval_to_ms as _interval_to_ms

        def _miss(reason: str) -> Tuple[None, Dict]:
            return None, {
                "valid": False,
                "data_invalid": True,
                "errors": [f"cache miss: {reason}"],
            }

        key = self._cache_key(symbol, interval)

        # 記憶體快取
        if key in self._memory_cache:
            df_full = self._memory_cache[key]
        else:
            path = self._parquet_path(symbol, interval)
            if not path.exists():
                return _miss("no parquet file")

            df_full = pd.read_parquet(path)
            # 確保 timestamp 是 datetime
            if '_open_time_ms' in df_full.columns:
                df_full['_open_time_ms'] = df_full['_open_time_ms'].astype('int64')
                df_full['timestamp'] = pd.to_datetime(df_full['_open_time_ms'], unit='ms', utc=True)
            elif 'timestamp' in df_full.columns:
                if pd.api.types.is_numeric_dtype(df_full['timestamp']):
                    df_full['timestamp'] = pd.to_datetime(df_full['timestamp'], unit='ms', utc=True)
                else:
                    df_full['timestamp'] = pd.to_datetime(df_full['timestamp'], utc=True)

            # 設為索引
            if 'timestamp' in df_full.columns:
                df_full = df_full.set_index('timestamp')
            df_full = self._normalize_datetime_index(df_full)
            if '_open_time_ms' not in df_full.columns:
                df_full['_open_time_ms'] = self._index_open_time_ms(df_full).to_numpy()

            self._memory_cache[key] = df_full

        # ── Coverage validation ────────────────────────────────────────────────
        if start_ms is not None and end_ms is not None:
            try:
                iv_ms = _interval_to_ms(interval)
            except ValueError:
                iv_ms = None

            # Check that cached data covers the requested range
            if len(df_full) == 0:
                return _miss("empty cache")

            open_time_ms = self._index_open_time_ms(df_full)
            cache_start_ms = int(open_time_ms.iloc[0])
            cache_end_ms = int(open_time_ms.iloc[-1])

            # Kline requests are half-open by open time: [start_ms, end_ms).
            # The final expected candle opens at end_ms - interval.
            margin = iv_ms if iv_ms else 60_000
            requested_last_open_ms = end_ms - margin
            if cache_end_ms < requested_last_open_ms:
                return _miss(
                    f"cache end {cache_end_ms} is before requested end {end_ms} "
                    f"(stale by {(end_ms - cache_end_ms) // 1000}s)"
                )

            # Does not cover start
            if cache_start_ms > start_ms + margin:
                return _miss(
                    f"cache start {cache_start_ms} is after requested start {start_ms}"
                )

            # Continuous markets require every interval. Exchange-session data
            # legitimately contains overnight, weekend and holiday gaps.
            if iv_ms is not None and not session_based:
                expected_count = max(0, (end_ms - start_ms + iv_ms - 1) // iv_ms)
                # Filter to requested window first
                window_mask = (open_time_ms >= start_ms) & (open_time_ms < end_ms)
                df_window = df_full.loc[window_mask.to_numpy()]
                actual_count = len(df_window)

                if actual_count < expected_count:
                    return _miss(
                        f"partial data: have {actual_count} candles, "
                        f"need {expected_count} for {interval} from {start_ms} to {end_ms}"
                    )

                # Check sorted and continuous (no gaps)
                if actual_count > 1:
                    ts_ms = self._index_open_time_ms(df_window).to_numpy()
                    diffs = ts_ms[1:] - ts_ms[:-1]
                    if not (diffs == iv_ms).all():
                        return _miss("gap or duplicate detected in cached data")

                return df_window.copy(), {"valid": True, "data_invalid": False, "errors": []}

        # 時間過濾 (when start_ms/end_ms not both provided, return raw slice)
        df = df_full
        if start_ms is not None:
            start_dt = pd.to_datetime(start_ms, unit='ms', utc=True)
            df = df[df.index >= start_dt]
        if end_ms is not None:
            end_dt = pd.to_datetime(end_ms, unit='ms', utc=True)
            if session_based:
                df = df[df.index <= end_dt]
            else:
                df = df[df.index < end_dt]

        if len(df) == 0:
            return _miss("filtered range is empty")

        return df.copy(), {"valid": True, "data_invalid": False, "errors": []}
    
    def save(self, df: pd.DataFrame, symbol: str, interval: str) -> None:
        """
        將 DataFrame 寫入 Parquet 快取。df 必須以 timestamp 為索引。
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._parquet_path(symbol, interval)
        # 寫入時重置索引以保留 timestamp 欄位
        df_to_write = self._normalize_datetime_index(df.copy())
        df_to_write.index.name = "timestamp"
        df_to_write = df_to_write.reset_index()
        df_to_write["timestamp"] = pd.to_datetime(df_to_write["timestamp"], utc=True)
        df_to_write["_open_time_ms"] = df_to_write["timestamp"].map(
            lambda ts: int(pd.Timestamp(ts).timestamp() * 1000)
        ).astype("int64")
        df_to_write.to_parquet(path, index=False)
        # 清除記憶體快取，確保下次重新讀取
        key = self._cache_key(symbol, interval)
        self._memory_cache.pop(key, None)

    def load_or_fetch(self, fetcher: DataProvider,
                      symbol: str, interval: str,
                      start_ms: Optional[int] = None,
                      end_ms: Optional[int] = None,
                      limit: int = 1000,
                      paginate: bool = True,
                      strict_validation: bool = False) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
        """
        優先讀取本地快取，不存在則呼叫 API（分頁抓取），成功後寫入快取。

        Returns:
            (df, validation) where validation is None when served from cache,
            or the validation dict from fetch_klines_paginated when fetched from API.
            If validation["data_invalid"] is True the caller must abort.

        Args:
            paginate: 若 True 且時間範圍大，使用分頁抓取以取得完整資料
        """
        session_detector = getattr(fetcher, "is_session_based", None)
        session_based = (
            callable(session_detector) and session_detector(symbol) is True
        )
        df, cache_validation = self.load(
            symbol, interval, start_ms, end_ms, session_based=session_based
        )
        if df is not None and cache_validation is not None and cache_validation.get("valid"):
            return df, cache_validation

        # 回退到 API
        validation: Optional[Dict] = None
        if paginate and start_ms is not None and end_ms is not None:
            klines, validation = fetcher.fetch_klines_paginated(
                symbol=symbol,
                interval=interval,
                start_time=start_ms,
                end_time=end_ms,
                limit=limit,
                validate=True,
                verbose=False,
                strict_validation=strict_validation,
            )
            if not klines:
                return None, validation
            # Log warnings if any
            if validation.get("warnings"):
                for w in validation["warnings"]:
                    print(f"   ⚠️ {w}")
            # If data is invalid, return immediately — do NOT cache bad data
            if validation.get("data_invalid"):
                return None, validation
        else:
            klines = fetcher.fetch_klines(symbol, interval, start_time=start_ms, end_time=end_ms, limit=limit)

        if not klines:
            return None, validation

        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype('int64'), unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # Write to cache after successful fetch
        self.save(df, symbol, interval)

        return df, validation



# ═══════════════════════════════════════════════════════════════════════════════
# 純 Pandas 指標計算器（無需 talib）
# ═══════════════════════════════════════════════════════════════════════════════

class IndicatorCalculator:
    """
    基於 pandas/numpy 的技術指標計算器。
    涵蓋 gene_library 中定義的所有指標。
    """
    
    @staticmethod
    def calculate_all(df: pd.DataFrame, gene: IndicatorGene) -> pd.Series:
        """
        根據基因定義計算單一指標序列
        
        Returns:
            pd.Series: 指標值序列（與 df 同長度）
        """
        name = gene.name
        params = gene.params
        
        # 趨勢指標
        if name == "ema_cross":
            short = df['close'].ewm(span=params.get("short_period", 12), adjust=False).mean()
            long = df['close'].ewm(span=params.get("long_period", 26), adjust=False).mean()
            return short - long  # 正值 = short > long
        
        elif name == "sma_cross":
            short = df['close'].rolling(params.get("short_period", 10)).mean()
            long = df['close'].rolling(params.get("long_period", 30)).mean()
            return short - long
        
        elif name == "macd":
            fast = df['close'].ewm(span=params.get("fast", 12), adjust=False).mean()
            slow = df['close'].ewm(span=params.get("slow", 26), adjust=False).mean()
            macd_line = fast - slow
            signal_line = macd_line.ewm(span=params.get("signal", 9), adjust=False).mean()
            return macd_line - signal_line  # histogram
        
        elif name == "adx":
            return IndicatorCalculator._adx(df, params.get("period", 14))
        
        elif name == "supertrend":
            return IndicatorCalculator._supertrend(df, params.get("period", 10), params.get("multiplier", 3.0))
        
        elif name == "close_vs_ma":
            ma_type = params.get("ma_type", "ema")
            period = params.get("ma_period", 50)
            if ma_type == "sma":
                ma = df['close'].rolling(period).mean()
            elif ma_type == "wma":
                ma = IndicatorCalculator._wma(df['close'], period)
            else:
                ma = df['close'].ewm(span=period, adjust=False).mean()
            return (df['close'] - ma) / ma  # 百分比距離
        
        # 動量指標
        elif name == "rsi":
            return IndicatorCalculator._rsi(df['close'], params.get("period", 14))
        
        elif name == "stochastic":
            return IndicatorCalculator._stochastic(df, params.get("k_period", 14), params.get("d_period", 3))
        
        elif name == "cci":
            return IndicatorCalculator._cci(df, params.get("period", 20))
        
        elif name == "momentum":
            period = params.get("period", 10)
            return df['close'].pct_change(period) * 100  # 百分比動量
        
        # 波動指標
        elif name == "bbands":
            period = params.get("period", 20)
            std = params.get("std_dev", 2.0)
            ma = df['close'].rolling(period).mean()
            sigma = df['close'].rolling(period).std()
            # 返回 z-score: (close - ma) / sigma
            zscore = (df['close'] - ma) / sigma
            return zscore.fillna(0)
        
        elif name == "atr":
            atr = IndicatorCalculator._atr(df, params.get("period", 14))
            return atr / df['close']  # ATR as % of price
        
        elif name == "keltner":
            return IndicatorCalculator._keltner_zscore(df, params.get("ema_period", 20), 
                                                        params.get("atr_period", 10), 
                                                        params.get("multiplier", 2.0))
        
        # 量能指標
        elif name == "volume_sma_ratio":
            period = params.get("period", 20)
            vol_sma = df['volume'].rolling(period).mean()
            return df['volume'] / vol_sma
        
        elif name == "obv":
            return IndicatorCalculator._obv(df).rolling(params.get("smooth_period", 10)).mean()
        
        elif name == "vwap":
            # 簡化 VWAP（session 內）
            typical = (df['high'] + df['low'] + df['close']) / 3
            vwap = (typical * df['volume']).cumsum() / df['volume'].cumsum()
            return (df['close'] - vwap) / vwap
        
        else:
            # 未知指標，返回 0
            return pd.Series(0, index=df.index)
    
    # ── 內部計算方法 ──
    
    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()
    
    @staticmethod
    def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        atr = IndicatorCalculator._atr(df, period)
        plus_di = 100 * plus_dm.rolling(period).mean() / atr
        minus_di = 100 * minus_dm.rolling(period).mean() / atr
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        return adx.fillna(0)
    
    @staticmethod
    def _supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
        atr = IndicatorCalculator._atr(df, period)
        hl2 = (df['high'] + df['low']) / 2
        upper = hl2 + multiplier * atr
        lower = hl2 - multiplier * atr
        
        st = pd.Series(0.0, index=df.index)
        direction = pd.Series(1, index=df.index)  # 1 = up, -1 = down
        
        for i in range(1, len(df)):
            if df['close'].iloc[i] > st.iloc[i-1]:
                direction.iloc[i] = 1
            else:
                direction.iloc[i] = -1
            
            if direction.iloc[i] == 1:
                st.iloc[i] = max(lower.iloc[i], st.iloc[i-1] if direction.iloc[i-1] == 1 else lower.iloc[i])
            else:
                st.iloc[i] = min(upper.iloc[i], st.iloc[i-1] if direction.iloc[i-1] == -1 else upper.iloc[i])
        
        # 返回方向序列：1 = bullish, -1 = bearish
        return direction.astype(float)
    
    @staticmethod
    def _stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.Series:
        low_min = df['low'].rolling(k_period).min()
        high_max = df['high'].rolling(k_period).max()
        k = 100 * (df['close'] - low_min) / (high_max - low_min)
        d = k.rolling(d_period).mean()
        return k - d  # 返回 KD 差值
    
    @staticmethod
    def _cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma = tp.rolling(period).mean()
        mad = np.abs(tp - sma).rolling(period).mean()
        cci = (tp - sma) / (0.015 * mad)
        return cci
    
    @staticmethod
    def _wma(series: pd.Series, period: int) -> pd.Series:
        weights = np.arange(1, period + 1)
        return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    @staticmethod
    def _keltner_zscore(df: pd.DataFrame, ema_period: int, atr_period: int, multiplier: float) -> pd.Series:
        ema = df['close'].ewm(span=ema_period, adjust=False).mean()
        atr = IndicatorCalculator._atr(df, atr_period)
        upper = ema + multiplier * atr
        lower = ema - multiplier * atr
        zscore = (df['close'] - ema) / (upper - lower) * 2  # 縮放到 roughly -1~1
        return zscore
    
    @staticmethod
    def _obv(df: pd.DataFrame) -> pd.Series:
        obv = pd.Series(0.0, index=df.index)
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['close'].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + df['volume'].iloc[i]
            elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - df['volume'].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        return obv


# ═══════════════════════════════════════════════════════════════════════════════
# 基因回測引擎
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SimulatedTrade:
    """模擬交易記錄"""
    symbol: str
    direction: str  # "long"
    entry_time: int  # timestamp ms
    entry_price: float
    exit_time: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl_pct: float = 0.0
    max_profit_pct: float = 0.0
    max_loss_pct: float = 0.0
    bars_held: int = 0


class GeneBacktestEngine:
    """
    基因策略回測引擎
    
    針對單一幣種、單一時間框架執行回測。
    每個策略基因體會被評估其在歷史數據上的表現。
    """
    
    def __init__(
        self,
        initial_capital: float = 1000.0,
        fee_rate: float = 0.001,
        data_provider: Optional[DataProvider] = None,
        official_ranking: bool = True,
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate  # 0.1% per trade
        self.data_provider = data_provider or BinanceFetcher()
        if official_ranking:
            require_official_data(self.data_provider)
        # Backward-compatible alias used by existing cache and tests.
        self.fetcher = self.data_provider
        self.data_provenance = self.data_provider.provenance
        self.calculator = IndicatorCalculator()
        self.cache = KlineCache()
    
    def evaluate(
        self,
        chrom: StrategyChromosome,
        symbol: str,
        interval: str = "5m",
        days: int = 90,
        verbose: bool = False,
    ) -> Tuple[BacktestMetrics, List[SimulatedTrade]]:
        """
        評估單一策略在單一幣種上的表現
        
        Args:
            chrom: 策略基因體
            symbol: 交易對，如 "BTCUSDT"
            interval: K 線間隔
            days: 回測天數（從現在往回）
            verbose: 是否輸出詳細日誌
        
        Returns:
            (metrics, trades)
        """
        # 獲取數據 — 優先本地快取，不存在才走 API
        # 使用分頁抓取確保 90 天 5m 資料完整（~25,920 根）
        end_ms = int(datetime.now().timestamp() * 1000)
        start_ms = end_ms - (days * 24 * 60 * 60 * 1000)

        df, validation = self.cache.load_or_fetch(
            self.fetcher, symbol, interval,
            start_ms=start_ms, end_ms=end_ms, limit=1000, paginate=True,
            strict_validation=True,
        )

        # Fail-closed: abort immediately on invalid data
        if validation is not None and (
            not validation.get("valid", True) or validation.get("data_invalid", False)
        ):
            if verbose:
                for e in validation.get("errors", []):
                    print(f"   ❌ {e}")
            metrics = BacktestMetrics()
            metrics.data_invalid = True
            return metrics, []

        if df is None or len(df) < 100:
            if verbose:
                print(f"   ⚠️ {symbol}: insufficient data ({len(df) if df is not None else 0} bars)")
            return BacktestMetrics(), []
        
        # 確保所需欄位存在且為 float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        # 預計算所有指標
        indicator_values = {}
        
        # 進場指標
        for gene in chrom.entry_genes:
            key = f"entry_{gene.name}_{id(gene)}"
            indicator_values[key] = self.calculator.calculate_all(df, gene)
        
        # 出場指標
        for gene in chrom.exit_genes:
            key = f"exit_{gene.name}_{id(gene)}"
            indicator_values[key] = self.calculator.calculate_all(df, gene)
        
        # 過濾指標
        if chrom.trend_filter:
            indicator_values["trend_filter"] = self.calculator.calculate_all(df, chrom.trend_filter)
        if chrom.volume_filter:
            indicator_values["volume_filter"] = self.calculator.calculate_all(df, chrom.volume_filter)
        
        # 執行回測
        trades = self._run_simulation(df, chrom, indicator_values, symbol, verbose)
        
        # 計算權益曲線
        equity = [self.initial_capital]
        current = self.initial_capital
        for t in trades:
            current *= (1 + t.pnl_pct)
            equity.append(current)
        
        # 計算指標
        trade_dicts = [{
            "symbol": t.symbol,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "pnl_pct": t.pnl_pct,
            "direction": t.direction,
        } for t in trades]
        
        metrics = calculate_metrics(trade_dicts, equity)
        
        if verbose:
            print(f"   {symbol}: {metrics.total_trades} trades | "
                  f"WinRate={metrics.win_rate:.1%} | "
                  f"PnL={metrics.total_pnl:.2%} | "
                  f"Sharpe={metrics.sharpe_ratio:.2f} | "
                  f"MaxDD={metrics.max_drawdown:.2%}")
        
        return metrics, trades
    
    def _run_simulation(
        self,
        df: pd.DataFrame,
        chrom: StrategyChromosome,
        indicator_values: Dict[str, pd.Series],
        symbol: str,
        verbose: bool,
    ) -> List[SimulatedTrade]:
        """核心模擬邏輯 — 優化版：使用 numpy 陣列避免 pandas iloc 開銷"""
        trades = []
        active_trade = None
        
        # ── 預提取 numpy 陣列，消除 pandas iloc 開銷 ──
        warmup = 100
        n = len(df)
        if n <= warmup:
            return []
        
        # 索引、價格轉為 numpy
        idx_arr = np.arange(n)
        ts_arr = (df.index.astype('int64').values // 10**6).astype(np.int64)  # ms timestamps
        close_arr = df['close'].values.astype(np.float64)
        
        # 進場訊號預計算為 numpy bool 陣列
        entry_signals = np.zeros(n, dtype=bool)
        exit_signals = np.zeros(n, dtype=bool)
        
        # 進場條件預計算
        entry_results = []
        entry_weights = []
        for gene in chrom.entry_genes:
            key = f"entry_{gene.name}_{id(gene)}"
            val = indicator_values.get(key)
            if val is None:
                continue
            s = self._evaluate_gene_series(gene, val)
            entry_results.append(s.values)
            entry_weights.append(gene.weight)
        
        if entry_results:
            entry_stack = np.stack(entry_results, axis=0)
            if chrom.entry_logic == "AND":
                entry_signals = entry_stack.all(axis=0)
            elif chrom.entry_logic == "OR":
                entry_signals = entry_stack.any(axis=0)
            elif chrom.entry_logic == "WEIGHTED":
                w_arr = np.array(entry_weights)
                weighted = (entry_stack * w_arr[:, None]).sum(axis=0) / w_arr.sum()
                entry_signals = weighted >= chrom.entry_min_weight
        
        # 出場條件預計算（僅訊號出場，不含硬止損/止盈/時間）
        exit_results = []
        exit_weights = []
        for gene in chrom.exit_genes:
            key = f"exit_{gene.name}_{id(gene)}"
            val = indicator_values.get(key)
            if val is None:
                continue
            s = self._evaluate_gene_series(gene, val)
            exit_results.append(s.values)
            exit_weights.append(gene.weight)
        
        if exit_results:
            exit_stack = np.stack(exit_results, axis=0)
            if chrom.exit_logic == "AND":
                exit_signals = exit_stack.all(axis=0)
            elif chrom.exit_logic == "OR":
                exit_signals = exit_stack.any(axis=0)
            elif chrom.exit_logic == "WEIGHTED":
                w_arr = np.array(exit_weights)
                weighted = (exit_stack * w_arr[:, None]).sum(axis=0) / w_arr.sum()
                exit_signals = weighted >= chrom.exit_min_weight
        
        # 過濾條件預計算
        trend_pass = np.ones(n, dtype=bool)
        volume_pass = np.ones(n, dtype=bool)
        
        if chrom.trend_filter:
            tf = indicator_values.get("trend_filter")
            if tf is not None:
                trend_pass = self._evaluate_gene_series(chrom.trend_filter, tf).values
        
        if chrom.volume_filter:
            vf = indicator_values.get("volume_filter")
            if vf is not None:
                volume_pass = self._evaluate_gene_series(chrom.volume_filter, vf).values
        
        # ── 快速模擬迴圈 ──
        for i in range(warmup, n):
            timestamp = int(ts_arr[i])
            current_price = close_arr[i]
            
            if active_trade:
                active_trade.bars_held += 1
                unrealized = (current_price - active_trade.entry_price) / active_trade.entry_price
                active_trade.max_profit_pct = max(active_trade.max_profit_pct, unrealized)
                active_trade.max_loss_pct = min(active_trade.max_loss_pct, unrealized)
                
                exit_reason = None
                
                # 硬止損
                if unrealized <= chrom.risk_genes.stop_loss_pct:
                    exit_reason = "hard_stop"
                # 硬止盈
                elif unrealized >= chrom.risk_genes.take_profit_pct:
                    exit_reason = "take_profit"
                # 時間止損
                elif active_trade.bars_held >= chrom.risk_genes.max_hold_bars:
                    exit_reason = "time_stop"
                # 出場訊號
                elif exit_signals[i]:
                    exit_reason = "signal_exit"
                # 追蹤止損
                elif chrom.risk_genes.trailing_stop and chrom.risk_genes.trailing_stop_pct:
                    peak = active_trade.max_profit_pct
                    if peak > chrom.risk_genes.trailing_stop_pct and unrealized <= (peak - chrom.risk_genes.trailing_stop_pct):
                        exit_reason = "trailing_stop"
                
                if exit_reason:
                    pnl = unrealized - (self.fee_rate * 2)
                    active_trade.exit_time = timestamp
                    active_trade.exit_price = current_price
                    active_trade.exit_reason = exit_reason
                    active_trade.pnl_pct = pnl
                    trades.append(active_trade)
                    active_trade = None
            else:
                # 過濾條件
                if not trend_pass[i] or not volume_pass[i]:
                    continue
                
                # 進場訊號
                if entry_signals[i]:
                    active_trade = SimulatedTrade(
                        symbol=symbol,
                        direction="long",
                        entry_time=timestamp,
                        entry_price=current_price,
                    )
        
        # 結束時強制平倉
        if active_trade:
            last_price = close_arr[-1]
            unrealized = (last_price - active_trade.entry_price) / active_trade.entry_price
            pnl = unrealized - (self.fee_rate * 2)
            active_trade.exit_time = int(ts_arr[-1])
            active_trade.exit_price = last_price
            active_trade.exit_reason = "end_of_test"
            active_trade.pnl_pct = pnl
            trades.append(active_trade)
        
        return trades
    
    def _evaluate_gene_series(self, gene: IndicatorGene, series: pd.Series) -> pd.Series:
        """向量版基因評估：回傳與 series 同長度的 bool Series"""
        val = series.values
        cond = gene.condition
        th = gene.threshold
        th2 = gene.threshold2
        
        if cond == ConditionType.ABOVE:
            return pd.Series(val > th, index=series.index)
        elif cond == ConditionType.BELOW:
            return pd.Series(val < th, index=series.index)
        elif cond == ConditionType.CROSS_UP:
            prev = np.roll(val, 1)
            prev[0] = np.nan
            return pd.Series((prev <= th) & (val > th), index=series.index)
        elif cond == ConditionType.CROSS_DOWN:
            prev = np.roll(val, 1)
            prev[0] = np.nan
            return pd.Series((prev >= th) & (val < th), index=series.index)
        elif cond == ConditionType.BETWEEN:
            if th2 is None:
                return pd.Series(False, index=series.index)
            low, high = sorted([th, th2])
            return pd.Series((val >= low) & (val <= high), index=series.index)
        elif cond == ConditionType.OUTSIDE:
            if th2 is None:
                return pd.Series(False, index=series.index)
            low, high = sorted([th, th2])
            return pd.Series((val < low) | (val > high), index=series.index)
        
        return pd.Series(False, index=series.index)
    
    def _check_entry_conditions(
        self, idx: int, df: pd.DataFrame, chrom: StrategyChromosome, indicator_values: Dict
    ) -> bool:
        """檢查進場條件"""
        results = []
        weights = []
        
        for gene in chrom.entry_genes:
            key = f"entry_{gene.name}_{id(gene)}"
            val = indicator_values.get(key)
            if val is None:
                continue
            result = self._evaluate_gene(idx, gene, val)
            results.append(result)
            weights.append(gene.weight)
        
        if not results:
            return False
        
        if chrom.entry_logic == "AND":
            return all(results)
        elif chrom.entry_logic == "OR":
            return any(results)
        elif chrom.entry_logic == "WEIGHTED":
            total_weight = sum(weights)
            if total_weight == 0:
                return False
            weighted_score = sum(r * w for r, w in zip(results, weights)) / total_weight
            return weighted_score >= chrom.entry_min_weight
        
        return False
    
    def _check_exit_conditions(
        self, idx: int, df: pd.DataFrame, chrom: StrategyChromosome, indicator_values: Dict
    ) -> bool:
        """檢查出場條件（除了硬止損止盈之外的條件出場）"""
        results = []
        weights = []
        
        for gene in chrom.exit_genes:
            key = f"exit_{gene.name}_{id(gene)}"
            val = indicator_values.get(key)
            if val is None:
                continue
            result = self._evaluate_gene(idx, gene, val)
            results.append(result)
            weights.append(gene.weight)
        
        if not results:
            return False
        
        if chrom.exit_logic == "AND":
            return all(results)
        elif chrom.exit_logic == "OR":
            return any(results)
        elif chrom.exit_logic == "WEIGHTED":
            total_weight = sum(weights)
            if total_weight == 0:
                return False
            weighted_score = sum(r * w for r, w in zip(results, weights)) / total_weight
            return weighted_score >= chrom.exit_min_weight
        
        return False
    
    def _evaluate_gene(self, idx: int, gene: IndicatorGene, series: pd.Series) -> bool:
        """
        在索引 idx 處評估單一基因條件
        """
        if idx >= len(series) or pd.isna(series.iloc[idx]):
            return False
        
        val = series.iloc[idx]
        cond = gene.condition
        th = gene.threshold
        th2 = gene.threshold2
        
        if cond == ConditionType.ABOVE:
            return val > th
        elif cond == ConditionType.BELOW:
            return val < th
        elif cond == ConditionType.CROSS_UP:
            if idx == 0:
                return False
            prev = series.iloc[idx - 1]
            return (prev <= th) and (val > th)
        elif cond == ConditionType.CROSS_DOWN:
            if idx == 0:
                return False
            prev = series.iloc[idx - 1]
            return (prev >= th) and (val < th)
        elif cond == ConditionType.BETWEEN:
            if th2 is None:
                return False
            low, high = sorted([th, th2])
            return low <= val <= high
        elif cond == ConditionType.OUTSIDE:
            if th2 is None:
                return False
            low, high = sorted([th, th2])
            return val < low or val > high
        
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 多幣種評估
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_chromosome_multi_symbol(
    chrom: StrategyChromosome,
    symbols: List[str],
    engine: Optional[GeneBacktestEngine] = None,
    interval: str = "5m",
    days: int = 90,
    verbose: bool = False,
) -> Tuple[float, Dict[str, BacktestMetrics], List[SimulatedTrade]]:
    """
    在多個幣種上評估策略，返回聚合 fitness

    Multi-symbol aggregation (Stage 2):
    - Collects BacktestMetrics from ALL symbols (required_symbols = all configured symbols)
    - If ANY symbol has data_invalid=True, empty trades, or < MIN_TRADES samples → fitness=0,
      insufficient_data=True is logged
    - Aggregates metrics across ALL successful symbols (approach: build a combined
      BacktestMetrics object and pass to compute_fitness, consistent with existing scoring)

    Aggregated fields:
      - total_pnl         : weighted average (by trade count) across symbols
      - max_drawdown      : worst (max) across symbols
      - win_rate          : weighted by trade count
      - profit_factor     : aggregate (total_gross_profit / total_gross_loss)
      - consecutive_losses: max across symbols
      - total_trades      : sum across symbols
      - sharpe_ratio      : mean across symbols

    Returns:
        (aggregated_fitness, per_symbol_metrics, all_trades)
    """
    from .fitness import compute_fitness

    MIN_TRADES_PER_SYMBOL = 5  # must match fitness.py threshold

    if engine is None:
        engine = GeneBacktestEngine()

    per_symbol: Dict[str, BacktestMetrics] = {}
    all_trades: List[SimulatedTrade] = []

    if verbose:
        print(f"\n🔬 Evaluating {chrom.chromosome_id[:8]} on {len(symbols)} symbols...")

    for symbol in symbols:
        metrics, trades = engine.evaluate(chrom, symbol, interval, days, verbose)
        per_symbol[symbol] = metrics
        all_trades.extend(trades)

    # ── Validate ALL required symbols (required = all configured symbols) ──────
    insufficient_data = False
    for symbol in symbols:
        m = per_symbol.get(symbol)
        if m is None:
            if verbose:
                print(f"   ❌ {symbol}: missing result")
            insufficient_data = True
        elif m.data_invalid:
            if verbose:
                print(f"   ❌ {symbol}: data_invalid=True")
            insufficient_data = True
        elif m.total_trades == 0:
            if verbose:
                print(f"   ❌ {symbol}: empty trades")
            insufficient_data = True
        elif m.total_trades < MIN_TRADES_PER_SYMBOL:
            if verbose:
                print(f"   ❌ {symbol}: insufficient samples ({m.total_trades} trades)")
            insufficient_data = True

    if insufficient_data:
        chrom.fitness_score = 0.0
        chrom.fitness_details = {"insufficient_data": True, "symbols_tested": len(symbols)}
        if verbose:
            print(f"   ⚠️ Required symbol failed — fitness=0")
        return 0.0, per_symbol, all_trades

    # ── Aggregate metrics across ALL successful symbols ────────────────────────
    # Approach (b): compute per-symbol fitness with compute_fitness, then weighted average
    # by trade count.  This is consistent with existing compute_fitness logic and avoids
    # inventing a new formula.

    valid_metrics = [per_symbol[s] for s in symbols]

    total_trades_all = sum(m.total_trades for m in valid_metrics)

    def _weighted(vals: List[float], weights: List[int]) -> float:
        total_w = sum(weights)
        if total_w == 0:
            return 0.0
        return sum(v * w for v, w in zip(vals, weights)) / total_w

    trade_counts = [m.total_trades for m in valid_metrics]

    # Build aggregated BacktestMetrics
    agg = BacktestMetrics(
        total_trades=total_trades_all,
        winning_trades=sum(m.winning_trades for m in valid_metrics),
        losing_trades=sum(m.losing_trades for m in valid_metrics),
        win_rate=_weighted([m.win_rate for m in valid_metrics], trade_counts),
        avg_profit=_weighted([m.avg_profit for m in valid_metrics], trade_counts),
        avg_loss=_weighted([m.avg_loss for m in valid_metrics], trade_counts),
        total_pnl=_weighted([m.total_pnl for m in valid_metrics], trade_counts),
        max_drawdown=max(m.max_drawdown for m in valid_metrics),
        sharpe_ratio=float(np.mean([m.sharpe_ratio for m in valid_metrics])),
        profit_factor=(
            sum(m.avg_profit * m.winning_trades for m in valid_metrics)
            / max(1e-9, sum(abs(m.avg_loss) * m.losing_trades for m in valid_metrics))
        ),
        expectancy=_weighted([m.expectancy for m in valid_metrics], trade_counts),
        avg_trade_duration=_weighted([m.avg_trade_duration for m in valid_metrics], trade_counts),
        consecutive_losses=max(m.consecutive_losses for m in valid_metrics),
        best_trade=max(m.best_trade for m in valid_metrics),
        worst_trade=min(m.worst_trade for m in valid_metrics),
    )

    agg_fitness = compute_fitness(agg)

    # 存入染色體
    chrom.fitness_score = agg_fitness
    chrom.fitness_details = compute_fitness_details(agg)
    chrom.fitness_details["symbols_tested"] = len(symbols)

    if verbose:
        print(f"   Aggregate Fitness: {agg_fitness:.4f} | Trades={total_trades_all}")

    return agg_fitness, per_symbol, all_trades
