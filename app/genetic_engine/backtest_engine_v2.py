#!/usr/bin/env python3
"""
Gene Backtest Engine V2 / 基因回測引擎 V2

在原有引擎基礎上增加：
1. Ghost DCA 基準線（與策略並行回測）
2. 季節摩擦應用（資金乘數）
3. 最小交易單位截斷模擬
4. 庫存橋（DeadHold/FloatHold）
5. V2 染色體支持（Macro/Micro 基因）

Reference: 《核心準則》第二篇章

Author: second_bot
Date: 2026-05-28
"""

import sys
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from data.fetcher import BinanceFetcher, KlineData
from .gene_library import IndicatorGene, IndicatorType, ConditionType
from .backtest_engine import (
    IndicatorCalculator, SimulatedTrade, GeneBacktestEngine,
    BacktestMetrics
)
from .chromosome_v2 import StrategyChromosomeV2, MacroGenes, MicroGenes, RiskGenesV2
from .environment import SeasonConfig, SeasonApplier, Environment
from .fitness_v2 import BacktestMetricsV2, calculate_metrics_v2


# ═══════════════════════════════════════════════════════════════════════════════
# V2 回測指標
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class V2BacktestResult:
    """V2 回測完整結果"""
    # 策略回測結果
    strategy_metrics: BacktestMetricsV2
    strategy_trades: List[SimulatedTrade]
    
    # Ghost DCA 基準結果
    dca_metrics: BacktestMetricsV2
    dca_trades: List[Dict[str, Any]]
    
    # 對比指標
    alpha_vs_dca: float  # 策略收益 - DCA 收益
    friction_penalty: float  # 摩擦成本懲罰
    
    # 原始數據
    equity_curve: List[float] = field(default_factory=list)
    dca_equity_curve: List[float] = field(default_factory=list)
    price_series: List[float] = field(default_factory=list)
    timestamp_series: List[int] = field(default_factory=list)

    # 資料無效標記
    data_invalid: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Ghost DCA 基準引擎
# ═══════════════════════════════════════════════════════════════════════════════

class GhostDCABaseline:
    """
    Ghost DCA 基準線
    
    在與策略完全相同的時間窗口內，模擬無腦定投行為：
    - 按固定時間間隔投入固定金額
    - 不考慮市場時機，純粹時間平均
    - 每次投入扣除手續費
    
    用於計算 Alpha = 策略收益 - DCA 收益
    """
    
    def __init__(
        self,
        initial_capital: float = 1000.0,
        dca_interval_hours: int = 168,  # 每週一次
        dca_amount_pct: float = 0.10,  # 每次投入 10% 資金
        fee_rate: float = 0.001,
    ):
        self.initial_capital = initial_capital
        self.dca_interval_hours = dca_interval_hours
        self.dca_amount_pct = dca_amount_pct
        self.fee_rate = fee_rate
    
    def run(
        self,
        df: pd.DataFrame,
        season: Optional[SeasonConfig] = None,
        environment: Optional[Environment] = None,
    ) -> Tuple[List[float], List[Dict[str, Any]]]:
        """
        執行 Ghost DCA 回測
        
        Returns:
            (equity_curve, trades)
        """
        equity = [self.initial_capital]
        cash = self.initial_capital
        position_value = 0.0
        position_qty = 0.0
        trades = []
        
        # DCA 計時器（毫秒）
        interval_ms = self.dca_interval_hours * 60 * 60 * 1000
        last_dca_time = None
        
        # 應用季節乘數
        aggressiveness = 1.0
        if season:
            aggressiveness = season.aggressiveness
        
        # 應用環境限制
        usable_cash_ratio = 1.0
        if environment:
            usable_cash_ratio = 1.0 - environment.dead_reserve_ratio
        
        for i in range(len(df)):
            timestamp = int(df.index[i].timestamp() * 1000)
            price = df['close'].iloc[i]
            
            # 檢查是否需要 DCA
            if last_dca_time is None or (timestamp - last_dca_time) >= interval_ms:
                # 計算本次投入金額
                base_amount = self.initial_capital * self.dca_amount_pct * aggressiveness
                
                # 受可用資金限制
                max_invest = cash * usable_cash_ratio
                invest_amount = min(base_amount, max_invest)
                
                if invest_amount > 0 and cash >= invest_amount:
                    # 扣除手續費
                    fee = invest_amount * self.fee_rate
                    net_invest = invest_amount - fee
                    
                    # 買入
                    qty = net_invest / price
                    position_qty += qty
                    position_value = position_qty * price
                    cash -= invest_amount
                    
                    trades.append({
                        "timestamp": timestamp,
                        "price": price,
                        "invest_amount": invest_amount,
                        "fee": fee,
                        "qty": qty,
                        "type": "dca_buy",
                    })
                    
                    last_dca_time = timestamp
            
            # 更新持倉價值
            position_value = position_qty * price
            total_value = cash + position_value
            equity.append(total_value)
        
        return equity, trades
    
    def calculate_dca_return(self, equity: List[float]) -> float:
        """計算 DCA 總收益"""
        if len(equity) < 2:
            return 0.0
        initial = equity[0]
        final = equity[-1]
        if initial <= 0:
            return 0.0
        return (final - initial) / initial


# ═══════════════════════════════════════════════════════════════════════════════
# V2 回測引擎
# ═══════════════════════════════════════════════════════════════════════════════

class GeneBacktestEngineV2(GeneBacktestEngine):
    """
    V2 基因策略回測引擎
    
    擴展原有引擎，加入：
    - Ghost DCA 並行回測
    - 季節摩擦
    - 最小交易單位截斷
    - 庫存橋模擬
    """
    
    def __init__(
        self,
        initial_capital: float = 1000.0,
        fee_rate: float = 0.001,
        lot_step: float = 0.001,  # 最小交易單位
        lot_min: float = 0.001,   # 最小下單量
    ):
        super().__init__(initial_capital=initial_capital, fee_rate=fee_rate)
        self.lot_step = lot_step
        self.lot_min = lot_min
        self.dca_engine = GhostDCABaseline(
            initial_capital=initial_capital,
            fee_rate=fee_rate,
        )
    
    def evaluate_v2(
        self,
        chrom: StrategyChromosomeV2,
        symbol: str,
        interval: str = "5m",
        days: int = 90,
        season: Optional[SeasonConfig] = None,
        environment: Optional[Environment] = None,
        verbose: bool = False,
    ) -> V2BacktestResult:
        """
        V2 評估：策略 + Ghost DCA 並行回測
        """
        # 獲取數據 — 使用分頁抓取確保 90 天 5m 資料完整（~25,920 根）
        end_ms = int(datetime.now().timestamp() * 1000)
        start_ms = end_ms - (days * 24 * 60 * 60 * 1000)
        
        klines, validation = self.fetcher.fetch_klines_paginated(
            symbol=symbol,
            interval=interval,
            start_time=start_ms,
            end_time=end_ms,
            limit=1000,
            validate=True,
            verbose=False,
            strict_validation=True,
        )

        # Fail-closed: abort immediately on invalid data — do NOT proceed to backtest
        if not validation.get("valid", True) or validation.get("data_invalid", False):
            if verbose:
                for e in validation.get("errors", []):
                    print(f"   ❌ {e}")
            empty_metrics = BacktestMetricsV2()
            empty_metrics.data_invalid = True
            return V2BacktestResult(
                strategy_metrics=empty_metrics,
                strategy_trades=[],
                dca_metrics=BacktestMetricsV2(),
                dca_trades=[],
                alpha_vs_dca=0.0,
                friction_penalty=0.0,
                data_invalid=True,
            )

        if validation.get("warnings"):
            for w in validation["warnings"]:
                if verbose:
                    print(f"   ⚠️ {w}")

        if not klines or len(klines) < 100:
            if verbose:
                print(f"   ⚠️ {symbol}: insufficient data")
            # 返回空結果
            empty_metrics = BacktestMetricsV2()
            return V2BacktestResult(
                strategy_metrics=empty_metrics,
                strategy_trades=[],
                dca_metrics=empty_metrics,
                dca_trades=[],
                alpha_vs_dca=0.0,
                friction_penalty=0.0,
            )
        
        # 轉換為 DataFrame
        df = self._klines_to_df(klines)
        
        # === 並行回測：策略 + Ghost DCA ===
        
        # 1. Ghost DCA
        dca_equity, dca_trades = self.dca_engine.run(df, season, environment)
        dca_return = self.dca_engine.calculate_dca_return(dca_equity)
        
        # 2. 策略回測
        strategy_equity, strategy_trades, raw_metrics = self._run_strategy_v2(
            df, chrom, symbol, season, environment, verbose
        )
        
        # 計算策略收益
        strategy_return = (strategy_equity[-1] - strategy_equity[0]) / strategy_equity[0] if strategy_equity else 0.0
        
        # Alpha = 策略收益 - DCA 收益
        alpha = strategy_return - dca_return
        
        # 摩擦成本懲罰
        n_trades = len(strategy_trades)
        friction_penalty = n_trades * self.fee_rate * 2  # 每筆來回手續費
        
        # 構建 V2 指標
        strategy_metrics = self._build_metrics_v2(
            strategy_trades, strategy_equity, dca_return, alpha, friction_penalty
        )
        
        dca_metrics = self._build_metrics_v2(
            [], dca_equity, dca_return, 0.0, 0.0
        )
        
        result = V2BacktestResult(
            strategy_metrics=strategy_metrics,
            strategy_trades=strategy_trades,
            dca_metrics=dca_metrics,
            dca_trades=dca_trades,
            alpha_vs_dca=alpha,
            friction_penalty=friction_penalty,
            equity_curve=strategy_equity,
            dca_equity_curve=dca_equity,
            price_series=df['close'].tolist(),
            timestamp_series=[int(t.timestamp() * 1000) for t in df.index],
        )
        
        if verbose:
            print(f"   {symbol}: Alpha={alpha:+.2%} | "
                  f"Str={strategy_return:+.2%} | DCA={dca_return:+.2%} | "
                  f"Trades={n_trades} | Friction={friction_penalty:.2%}")
        
        return result
    
    def _klines_to_df(self, klines: List) -> pd.DataFrame:
        """K 線轉 DataFrame"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    
    def _run_strategy_v2(
        self,
        df: pd.DataFrame,
        chrom: StrategyChromosomeV2,
        symbol: str,
        season: Optional[SeasonConfig],
        environment: Optional[Environment],
        verbose: bool,
    ) -> Tuple[List[float], List[SimulatedTrade], Dict[str, Any]]:
        """
        V2 策略模擬核心
        
        新增：
        - 季節摩擦（position size 調整）
        - 最小交易單位截斷
        - 庫存橋（DeadHold / FloatHold）
        """
        trades = []
        
        # 資金模擬
        cash = self.initial_capital
        position_qty = 0.0
        position_cost = 0.0
        equity = [self.initial_capital]
        
        # 庫存橋
        dead_hold_qty = 0.0   # 底倉（只進不出）
        float_hold_qty = 0.0  # 浮動倉（可賣出）
        
        # 計算可用資金比例（受 Environment 限制）
        usable_cash_ratio = 1.0
        if environment:
            usable_cash_ratio = 1.0 - environment.dead_reserve_ratio
        
        # 應用季節乘數
        season_mult = 1.0
        if season:
            season_mult = season.aggressiveness
        
        # 預計算指標
        indicator_values = self._precalculate_indicators(df, chrom)
        
        warmup = 100
        
        for i in range(warmup, len(df)):
            timestamp = int(df.index[i].timestamp() * 1000)
            current_price = df['close'].iloc[i]
            
            # 更新權益
            position_value = position_qty * current_price
            total_value = cash + position_value
            equity.append(total_value)
            
            # === 檢查出場 ===
            if position_qty > 0:
                # 檢查出場條件（只檢查浮動倉）
                exit_qty = 0.0
                exit_reason = None
                
                # 只能賣出 float_hold 部分
                max_sellable = float_hold_qty
                
                if max_sellable > 0:
                    unrealized = (current_price - position_cost / position_qty) / (position_cost / position_qty) if position_cost > 0 else 0
                    
                    # 硬止損
                    if unrealized <= chrom.risk_genes.stop_loss_pct:
                        exit_qty = max_sellable
                        exit_reason = "hard_stop"
                    
                    # 硬止盈
                    elif unrealized >= chrom.risk_genes.take_profit_pct:
                        exit_qty = max_sellable
                        exit_reason = "take_profit"
                    
                    # 出場信號
                    elif self._check_exit_conditions(i, df, chrom, indicator_values):
                        # 應用 Micro 基因的最小交易閾值
                        deviation = abs(unrealized)
                        if deviation >= chrom.micro_genes.min_trade_threshold:
                            exit_qty = max_sellable * chrom.micro_genes.micro_reserve_rate
                            exit_reason = "signal_exit"
                    
                    # 截斷到最小交易單位
                    exit_qty = self._truncate_lot(exit_qty)
                    
                    if exit_qty >= self.lot_min and exit_qty <= max_sellable:
                        # 執行賣出
                        sell_value = exit_qty * current_price
                        fee = sell_value * self.fee_rate
                        cash += (sell_value - fee)
                        
                        # 更新庫存橋
                        float_hold_qty -= exit_qty
                        position_qty -= exit_qty
                        
                        # 記錄交易
                        pnl = (current_price - position_cost / (position_qty + exit_qty)) / (position_cost / (position_qty + exit_qty)) if position_cost > 0 else 0
                        trades.append(SimulatedTrade(
                            symbol=symbol,
                            direction="long",
                            entry_time=timestamp,
                            entry_price=position_cost / (position_qty + exit_qty) if position_cost > 0 else current_price,
                            exit_time=timestamp,
                            exit_price=current_price,
                            exit_reason=exit_reason or "sell",
                            pnl_pct=pnl - (self.fee_rate * 2),
                        ))
            
            # === 檢查進場 ===
            if self._check_entry_conditions(i, df, chrom, indicator_values):
                # 計算進場倉位（受季節和環境限制）
                base_position_pct = chrom.risk_genes.position_pct
                
                # 應用季節摩擦
                adjusted_pct = base_position_pct * season_mult
                
                # 應用環境限制
                adjusted_pct = min(adjusted_pct, usable_cash_ratio)
                
                # 計算投入金額
                invest_amount = cash * adjusted_pct
                
                # 計算可買數量
                qty = invest_amount / current_price
                
                # 截斷到最小交易單位
                qty = self._truncate_lot(qty)
                
                if qty >= self.lot_min and invest_amount <= cash * usable_cash_ratio:
                    # 扣除手續費
                    buy_value = qty * current_price
                    fee = buy_value * self.fee_rate
                    total_cost = buy_value + fee
                    
                    if total_cost <= cash:
                        cash -= total_cost
                        position_qty += qty
                        position_cost += total_cost
                        
                        # 庫存橋分配
                        # DeadHold 比例由風控基因決定
                        dead_alloc = qty * chrom.risk_genes.dead_hold_ratio
                        float_alloc = qty * chrom.risk_genes.float_hold_ratio
                        
                        dead_hold_qty += dead_alloc
                        float_hold_qty += float_alloc
                        
                        # 如果有加速度解封條件，檢查是否轉移
                        # 簡化：不實時檢查，只在出場時區分
        
        # 結束時強制平倉（只平 FloatHold）
        if position_qty > 0 and float_hold_qty > 0:
            last_price = df['close'].iloc[-1]
            exit_qty = min(float_hold_qty, position_qty)
            exit_qty = self._truncate_lot(exit_qty)
            
            if exit_qty >= self.lot_min:
                sell_value = exit_qty * last_price
                fee = sell_value * self.fee_rate
                cash += (sell_value - fee)
                
                float_hold_qty -= exit_qty
                position_qty -= exit_qty
                
                unrealized = (last_price - position_cost / (position_qty + exit_qty)) / (position_cost / (position_qty + exit_qty)) if position_cost > 0 else 0
                trades.append(SimulatedTrade(
                    symbol=symbol,
                    direction="long",
                    entry_time=timestamp,
                    entry_price=position_cost / (position_qty + exit_qty) if position_cost > 0 else last_price,
                    exit_time=int(df.index[-1].timestamp() * 1000),
                    exit_price=last_price,
                    exit_reason="end_of_test",
                    pnl_pct=unrealized - (self.fee_rate * 2),
                ))
        
        return equity, trades, {}
    
    def _truncate_lot(self, qty: float) -> float:
        """截斷到最小交易單位的整數倍"""
        if qty <= 0:
            return 0.0
        steps = int(qty / self.lot_step)
        return steps * self.lot_step
    
    def _precalculate_indicators(self, df: pd.DataFrame, chrom: StrategyChromosomeV2) -> Dict[str, pd.Series]:
        """預計算所有指標"""
        values = {}
        
        for gene in chrom.entry_genes:
            key = f"entry_{gene.name}_{id(gene)}"
            values[key] = self.calculator.calculate_all(df, gene)
        
        for gene in chrom.exit_genes:
            key = f"exit_{gene.name}_{id(gene)}"
            values[key] = self.calculator.calculate_all(df, gene)
        
        if chrom.trend_filter:
            values["trend_filter"] = self.calculator.calculate_all(df, chrom.trend_filter)
        if chrom.volume_filter:
            values["volume_filter"] = self.calculator.calculate_all(df, chrom.volume_filter)
        
        return values
    
    def _check_entry_conditions(
        self, idx: int, df: pd.DataFrame, chrom: StrategyChromosomeV2, indicator_values: Dict
    ) -> bool:
        """V2 進場條件檢查（與父類兼容）"""
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
        self, idx: int, df: pd.DataFrame, chrom: StrategyChromosomeV2, indicator_values: Dict
    ) -> bool:
        """V2 出場條件檢查"""
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
        """評估單一基因條件（與父類相同）"""
        if idx >= len(series) or pd.isna(series.iloc[idx]):
            return False
        
        val = series.iloc[idx]
        
        from .gene_library import ConditionType
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
    
    def _build_metrics_v2(
        self,
        trades: List[SimulatedTrade],
        equity: List[float],
        dca_return: float,
        alpha: float,
        friction_penalty: float,
    ) -> BacktestMetricsV2:
        """構建 V2 回測指標"""
        if not trades:
            return BacktestMetricsV2(
                total_trades=0,
                total_pnl=0.0,
                ghost_dca_pnl=dca_return,
                alpha_vs_dca=alpha,
            )
        
        winning_trades = sum(1 for t in trades if t.pnl_pct > 0)
        losing_trades = len(trades) - winning_trades
        
        pnl_values = [t.pnl_pct for t in trades]
        
        return BacktestMetricsV2(
            total_trades=len(trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=winning_trades / len(trades) if trades else 0.0,
            avg_profit=np.mean([t.pnl_pct for t in trades if t.pnl_pct > 0]) if winning_trades > 0 else 0.0,
            avg_loss=np.mean([t.pnl_pct for t in trades if t.pnl_pct <= 0]) if losing_trades > 0 else 0.0,
            total_pnl=sum(pnl_values),
            max_drawdown=self._calculate_max_drawdown(equity),
            sharpe_ratio=self._calculate_sharpe(equity),
            ghost_dca_pnl=dca_return,
            alpha_vs_dca=alpha,
            friction_penalty=friction_penalty,
        )
    
    def _calculate_max_drawdown(self, equity: List[float]) -> float:
        """計算最大回撤"""
        if len(equity) < 2:
            return 0.0
        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd
    
    def _calculate_sharpe(self, equity: List[float], risk_free_rate: float = 0.0) -> float:
        """計算夏普比率（簡化）"""
        if len(equity) < 2:
            return 0.0
        returns = []
        for i in range(1, len(equity)):
            if equity[i-1] > 0:
                returns.append((equity[i] - equity[i-1]) / equity[i-1])
        
        if not returns or np.std(returns) == 0:
            return 0.0
        
        return (np.mean(returns) - risk_free_rate) / np.std(returns) * np.sqrt(len(returns))


# ═══════════════════════════════════════════════════════════════════════════════
# 多幣種 V2 評估
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_chromosome_multi_symbol_v2(
    chrom: StrategyChromosomeV2,
    symbols: List[str],
    engine: Optional[GeneBacktestEngineV2] = None,
    interval: str = "5m",
    days: int = 90,
    seasons: Optional[List[SeasonConfig]] = None,
    environment: Optional[Environment] = None,
    verbose: bool = False,
) -> Tuple[float, Dict[str, V2BacktestResult], List[SimulatedTrade]]:
    """
    V2 多幣種評估
    
    在多個幣種上執行 V2 回測，可選多季節摩擦測試。
    """
    if engine is None:
        engine = GeneBacktestEngineV2()
    
    per_symbol: Dict[str, V2BacktestResult] = {}
    all_trades = []
    
    if verbose:
        print(f"\n🔬 V2 Evaluating {chrom.chromosome_id[:8]} on {len(symbols)} symbols...")
    
    for symbol in symbols:
        # 如果有季節配置，輪流應用
        season = None
        if seasons:
            season = random.choice(seasons)
        
        result = engine.evaluate_v2(
            chrom, symbol, interval, days,
            season=season, environment=environment, verbose=verbose
        )
        
        per_symbol[symbol] = result
        all_trades.extend(result.strategy_trades)
    
    # 計算平均 Alpha
    alphas = [r.alpha_vs_dca for r in per_symbol.values()]
    avg_alpha = np.mean(alphas) if alphas else 0.0
    
    # 總摩擦成本
    total_friction = sum(r.friction_penalty for r in per_symbol.values())
    
    # 綜合 fitness（簡化版，完整版在 fitness_v2.py）
    fitness = max(0.0, avg_alpha - total_friction * 0.1)
    
    if verbose:
        print(f"   V2 Aggregate: Alpha={avg_alpha:+.2%} | Friction={total_friction:.2%} | Fit={fitness:.4f}")
    
    return fitness, per_symbol, all_trades


if __name__ == "__main__":
    print("=== Backtest Engine V2 Test ===")
    
    # 測試 Ghost DCA
    print("\n1. Ghost DCA Baseline Test")
    dca = GhostDCABaseline(initial_capital=1000, dca_interval_hours=168)
    
    # 簡單價格序列
    test_prices = pd.Series([100, 102, 98, 105, 103, 110, 108, 115, 112, 120])
    test_df = pd.DataFrame({"close": test_prices})
    test_df.index = pd.date_range("2024-01-01", periods=10, freq="D")
    
    equity, trades = dca.run(test_df)
    ret = dca.calculate_dca_return(equity)
    print(f"   DCA Return: {ret:+.2%} | Trades: {len(trades)} | Final Equity: ${equity[-1]:.2f}")
    
    # 測試截斷
    print("\n2. Lot Truncation Test")
    engine = GeneBacktestEngineV2(lot_step=0.001, lot_min=0.001)
    print(f"   0.0005 → {engine._truncate_lot(0.0005)}")
    print(f"   0.0023 → {engine._truncate_lot(0.0023)}")
    print(f"   1.2345 → {engine._truncate_lot(1.2345)}")
    
    print("\n3. Season Application Test")
    from .environment import Season, SeasonConfig
    season = SeasonConfig(season=Season.SUMMER, aggressiveness=2.0)
    env = Environment(dead_reserve_ratio=0.20)
    
    base_pos = 0.15
    adjusted = SeasonApplier.apply_to_position_size(base_pos, season, env)
    print(f"   Base={base_pos:.0%} | Season=Summer(x2) | Env Reserve=20% | Result={adjusted:.2%}")
    
    print("\n✅ V2 Backtest Engine ready")
