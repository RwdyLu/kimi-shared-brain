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
        return f"{symbol}_{interval}"
    
    def _parquet_path(self, symbol: str, interval: str) -> Path:
        return self.cache_dir / f"{symbol}_{interval}.parquet"
    
    def has_cache(self, symbol: str, interval: str) -> bool:
        return self._parquet_path(symbol, interval).exists()
    
    def load(self, symbol: str, interval: str,
             start_ms: Optional[int] = None,
             end_ms: Optional[int] = None) -> Optional[pd.DataFrame]:
        """
        從快取載入 K 線 DataFrame，可選時間過濾。
        使用記憶體二級快取加速重複讀取。
        """
        key = self._cache_key(symbol, interval)
        
        # 記憶體快取
        if key in self._memory_cache:
            df = self._memory_cache[key]
        else:
            path = self._parquet_path(symbol, interval)
            if not path.exists():
                return None
            
            df = pd.read_parquet(path)
            # 確保 timestamp 是 datetime
            if 'timestamp' in df.columns:
                if df['timestamp'].dtype == 'int64':
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                elif not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            
            # 設為索引
            if 'timestamp' in df.columns:
                df = df.set_index('timestamp').sort_index()
            
            self._memory_cache[key] = df
        
        # 時間過濾
        if start_ms is not None:
            start_dt = pd.to_datetime(start_ms, unit='ms', utc=True)
            df = df[df.index >= start_dt]
        if end_ms is not None:
            end_dt = pd.to_datetime(end_ms, unit='ms', utc=True)
            df = df[df.index <= end_dt]
        
        return df.copy()  # 避免修改記憶體快取
    
    def load_or_fetch(self, fetcher: BinanceFetcher,
                      symbol: str, interval: str,
                      start_ms: Optional[int] = None,
                      end_ms: Optional[int] = None,
                      limit: int = 1000) -> Optional[pd.DataFrame]:
        """
        優先讀取本地快取，不存在則呼叫 API（並回傳 raw klines 格式）。
        """
        df = self.load(symbol, interval, start_ms, end_ms)
        if df is not None:
            return df
        
        # 回退到 API
        klines = fetcher.fetch_klines(symbol, interval, start_time=start_ms, end_time=end_ms, limit=limit)
        if not klines:
            return None
        
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df



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
    
    def __init__(self, initial_capital: float = 1000.0, fee_rate: float = 0.001):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate  # 0.1% per trade
        self.fetcher = BinanceFetcher()
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
        end_ms = int(datetime.now().timestamp() * 1000)
        start_ms = end_ms - (days * 24 * 60 * 60 * 1000)
        
        df = self.cache.load_or_fetch(
            self.fetcher, symbol, interval,
            start_ms=start_ms, end_ms=end_ms, limit=1000
        )
        
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
    
    Returns:
        (aggregated_fitness, per_symbol_metrics, all_trades)
    """
    if engine is None:
        engine = GeneBacktestEngine()
    
    per_symbol = {}
    all_trades = []
    
    if verbose:
        print(f"\n🔬 Evaluating {chrom.chromosome_id[:8]} on {len(symbols)} symbols...")
    
    for symbol in symbols:
        metrics, trades = engine.evaluate(chrom, symbol, interval, days, verbose)
        per_symbol[symbol] = metrics
        all_trades.extend(trades)
    
    # 聚合 fitness — 用最差表現作為保守估計
    from .fitness import aggregate_fitness
    agg_fitness = aggregate_fitness(per_symbol, aggregation="worst")
    
    # 存入染色體
    chrom.fitness_score = agg_fitness
    chrom.fitness_details = compute_fitness_details(
        BacktestMetrics(
            total_trades=sum(m.total_trades for m in per_symbol.values()),
            total_pnl=np.mean([m.total_pnl for m in per_symbol.values()]),
        )
    )
    
    if verbose:
        print(f"   Aggregate Fitness: {agg_fitness:.4f}")
    
    return agg_fitness, per_symbol, all_trades
