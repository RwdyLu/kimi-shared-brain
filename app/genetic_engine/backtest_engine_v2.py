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
import math
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
from .market_rules import MarketRules, MARKET_RULES, SYMBOL_MARKETS
from data.providers import DataProvider


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
        dca_interval_candles: Optional[int] = None,
        season_schedule: Optional[List[SeasonConfig]] = None,
    ) -> Tuple[List[float], List[Dict[str, Any]]]:
        """
        執行 Ghost DCA 回測

        Stage 4: dca_interval_candles — if provided, fires every N candles instead of
        using the time-based dca_interval_hours.  This wires macro_genes.dca_interval
        into GhostDCA behavior.

        Returns:
            (equity_curve, trades)
        """
        equity = [self.initial_capital]
        cash = self.initial_capital
        position_value = 0.0
        position_qty = 0.0
        trades = []

        # DCA 計時器 — candle-based (Stage 4) takes priority over time-based
        use_candle_interval = dca_interval_candles is not None
        interval_ms = self.dca_interval_hours * 60 * 60 * 1000
        last_dca_time = None
        last_dca_candle: Optional[int] = None

        # 應用季節乘數
        aggressiveness = 1.0
        if season:
            aggressiveness = season.aggressiveness

        # 應用環境限制
        usable_cash_ratio = 1.0
        if environment:
            usable_cash_ratio = 1.0 - environment.dead_reserve_ratio

        for i in range(len(df)):
            active_season = SeasonApplier.season_for_index(
                i, len(df), season_schedule, season
            )
            timestamp = int(df.index[i].timestamp() * 1000)
            price = df['close'].iloc[i]

            # 檢查是否需要 DCA
            if use_candle_interval:
                interval = max(1, int(dca_interval_candles))
                should_dca = (
                    last_dca_candle is None
                    or (i - last_dca_candle) >= interval
                )
            else:
                should_dca = (last_dca_time is None or (timestamp - last_dca_time) >= interval_ms)

            if should_dca:
                # 計算本次投入金額
                active_aggressiveness = (
                    active_season.aggressiveness if active_season else aggressiveness
                )
                base_amount = self.initial_capital * self.dca_amount_pct * active_aggressiveness

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
                        "season": active_season.season.value if active_season else None,
                    })

                    last_dca_time = timestamp
                    last_dca_candle = i

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
        data_provider: Optional[DataProvider] = None,
        market_rules: Optional[MarketRules] = None,
        official_ranking: bool = True,
    ):
        rules = market_rules or MARKET_RULES["crypto_spot"]
        super().__init__(
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            data_provider=data_provider,
            official_ranking=official_ranking,
        )
        self.market_rules = rules
        self._explicit_market_rules = market_rules is not None
        self._constructor_lot_step = lot_step
        self._constructor_lot_min = lot_min
        self._constructor_fee_rate = fee_rate
        self.lot_step = rules.lot_step if market_rules else lot_step
        self.lot_min = rules.lot_min if market_rules else lot_min
        self.buy_fee_rate = rules.buy_commission_rate if market_rules else fee_rate
        self.sell_fee_rate = (
            rules.sell_commission_rate + rules.sell_tax_rate
            if market_rules else fee_rate
        )
        self.dca_engine = GhostDCABaseline(
            initial_capital=initial_capital,
            fee_rate=self.buy_fee_rate,
        )

    def _apply_market_rules_for_symbol(self, symbol: str) -> None:
        if self._explicit_market_rules:
            rules = self.market_rules
        elif symbol in SYMBOL_MARKETS:
            rules = MARKET_RULES[SYMBOL_MARKETS[symbol]]
        else:
            self.lot_step = self._constructor_lot_step
            self.lot_min = self._constructor_lot_min
            self.buy_fee_rate = self._constructor_fee_rate
            self.sell_fee_rate = self._constructor_fee_rate
            self.dca_engine.fee_rate = self.buy_fee_rate
            return

        self.market_rules = rules
        self.lot_step = rules.lot_step
        self.lot_min = rules.lot_min
        self.buy_fee_rate = rules.buy_commission_rate
        self.sell_fee_rate = rules.sell_commission_rate + rules.sell_tax_rate
        self.dca_engine.fee_rate = self.buy_fee_rate
    
    def evaluate_v2(
        self,
        chrom: StrategyChromosomeV2,
        symbol: str,
        interval: str = "5m",
        days: int = 90,
        season: Optional[SeasonConfig] = None,
        environment: Optional[Environment] = None,
        verbose: bool = False,
        seasons: Optional[List[SeasonConfig]] = None,
    ) -> V2BacktestResult:
        """
        V2 評估：策略 + Ghost DCA 並行回測
        """
        self._apply_market_rules_for_symbol(symbol)
        # 獲取數據 — 優先讀快取，快取不足才呼叫 API（避免重複打 Binance）
        end_ms = int(datetime.now().timestamp() * 1000)
        start_ms = end_ms - (days * 24 * 60 * 60 * 1000)

        df_cached, validation = self.cache.load_or_fetch(
            self.fetcher, symbol, interval,
            start_ms=start_ms, end_ms=end_ms,
            limit=1000, paginate=True,
            strict_validation=True,
        )
        # Fail-closed: abort immediately on invalid data — do NOT proceed to backtest
        validation = validation or {"valid": False, "data_invalid": True, "errors": ["missing validation"]}
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

        if df_cached is None or len(df_cached) < 100:
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
        
        # KlineCache already returns a normalized OHLCV DataFrame. Converting its
        # rows again as raw Binance klines corrupts timestamps and column layout.
        df = df_cached.copy()
        
        # === 並行回測：策略 + Ghost DCA ===
        
        # 1. Ghost DCA — Stage 4: wire macro_genes.dca_interval
        dca_interval_candles = chrom.macro_genes.dca_interval
        dca_kwargs = {"dca_interval_candles": dca_interval_candles}
        if seasons is not None:
            dca_kwargs["season_schedule"] = seasons
        dca_equity, dca_trades = self.dca_engine.run(
            df, season, environment, **dca_kwargs
        )
        dca_return = self.dca_engine.calculate_dca_return(dca_equity)
        
        # 2. 策略回測
        strategy_kwargs = {}
        if seasons is not None:
            strategy_kwargs["season_schedule"] = seasons
        strategy_equity, strategy_trades, raw_metrics = self._run_strategy_v2(
            df, chrom, symbol, season, environment, verbose, **strategy_kwargs
        )
        
        # 計算策略收益
        strategy_return = (strategy_equity[-1] - strategy_equity[0]) / strategy_equity[0] if strategy_equity else 0.0
        
        # Alpha = 策略收益 - DCA 收益
        alpha = strategy_return - dca_return
        
        # Stage 2 Fix: friction_penalty = n_trades * fee_rate * 2 was REMOVED.
        # Fees are already deducted in the actual buy/sell ledger inside _run_strategy_v2.
        # The result carries actual total_fees from the ledger (via raw_metrics).
        n_trades = len(strategy_trades)
        # No synthetic friction_penalty — actual fees are tracked in the ledger
        friction_penalty = 0.0

        # 構建 V2 指標
        strategy_metrics = self._build_metrics_v2(
            strategy_trades, strategy_equity, dca_return, alpha, friction_penalty,
            raw_metrics=raw_metrics,
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
            actual_fees = raw_metrics.get("total_fees", 0.0)
            print(f"   {symbol}: Alpha={alpha:+.2%} | "
                  f"Str={strategy_return:+.2%} | DCA={dca_return:+.2%} | "
                  f"Trades={n_trades} | Fees={actual_fees:.4f}")
        
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
        season_schedule: Optional[List[SeasonConfig]] = None,
    ) -> Tuple[List[float], List[SimulatedTrade], Dict[str, Any]]:
        """
        V2 策略模擬核心

        Stage 4 wiring:
        - macro_genes.hold_period    → forced exit after N candles
        - macro_genes.recycle_ratio  → fraction of realized PnL reinvested into next buy
        - macro_genes.target_weight  → target position weight for kp/kv/ka PDE
        - micro_genes.kp/kv/ka       → PDE position-sizing formula
        - micro_genes.sigmoid_scale  → scale raw entry signal before thresholding
        - micro_genes.gamma          → risk-aversion exponent on position sizing
        - micro_genes.beta           → blend between entry/exit signal source
        - micro_genes.min_trade_threshold → skip trade if deviation < threshold
        - micro_genes.micro_reserve_rate  → fraction of float to sell on signal exit
        """
        trades = []

        # 資金模擬
        cash = self.initial_capital
        position_qty = 0.0
        position_avg_cost = 0.0  # per-unit avg cost (including buy-side fee)
        equity = [self.initial_capital]

        # Stage 2 Fix: track actual total fees from ledger
        total_fees_ledger = 0.0
        total_buy_fees = 0.0
        total_sell_fees = 0.0
        total_realized_pnl = 0.0
        total_buy_notional = 0.0
        total_sell_notional = 0.0

        # 庫存橋
        dead_hold_qty = 0.0   # 底倉（只進不出）
        float_hold_qty = 0.0  # 浮動倉（可賣出）

        # Track the oldest open float tranche. Additional buys must not reset the
        # holding deadline, otherwise continuous entry signals can bypass it.
        position_open_candle: Optional[int] = None
        hold_period = chrom.macro_genes.hold_period  # max candles before forced exit

        # Stage 4: recycle pool — accumulated realized PnL to reinvest
        recycle_pool: float = 0.0
        recycle_ratio: float = chrom.macro_genes.recycle_ratio
        recycled_profit_deployed: float = 0.0

        # Stage 4: kp/kv/ka PDE state
        target_weight: float = chrom.macro_genes.target_weight
        prev_actual_weight: float = 0.0
        prev_velocity: float = 0.0

        # Stage 4: gene scalars
        kp: float = chrom.micro_genes.kp
        kv: float = chrom.micro_genes.kv
        ka: float = chrom.micro_genes.ka
        sigmoid_scale: float = chrom.micro_genes.sigmoid_scale
        gamma: float = chrom.micro_genes.gamma
        beta: float = chrom.micro_genes.beta
        min_trade_threshold: float = chrom.micro_genes.min_trade_threshold
        seasons_applied: List[str] = []
        macro_interval = max(1, int(chrom.macro_genes.t_macro))
        micro_interval = max(1, int(chrom.macro_genes.t_micro))
        deadline_interval = max(1, int(chrom.macro_genes.t_deadline))
        macro_ticks = 0
        micro_ticks = 0
        deadline_ticks = 0
        unlock_events: List[Dict[str, Any]] = []

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
            active_season = SeasonApplier.season_for_index(
                i - warmup, len(df) - warmup, season_schedule, season
            )
            if active_season and (
                not seasons_applied or seasons_applied[-1] != active_season.season.value
            ):
                seasons_applied.append(active_season.season.value)
            timestamp = int(df.index[i].timestamp() * 1000)
            current_price = df['close'].iloc[i]

            # 更新權益
            position_value = position_qty * current_price
            total_value = cash + position_value
            equity.append(total_value)

            # === Stage 4: compute actual weight and PDE velocity ===
            actual_weight = position_value / total_value if total_value > 0 else 0.0
            velocity = actual_weight - prev_actual_weight
            acceleration = velocity - prev_velocity
            acceleration_signal = abs(ka * acceleration)

            # kp/kv/ka desired position weight
            raw_desired = (
                kp * (target_weight - actual_weight)
                + kv * (actual_weight - prev_actual_weight)
                + ka * acceleration
            )
            # clamp to [0, 1]
            desired_position_weight = max(0.0, min(1.0, raw_desired))

            # update PDE state
            prev_velocity = velocity
            prev_actual_weight = actual_weight

            elapsed = i - warmup
            macro_tick = elapsed % macro_interval == 0
            micro_tick = elapsed % micro_interval == 0
            deadline_tick = elapsed % deadline_interval == 0
            macro_ticks += int(macro_tick)
            micro_ticks += int(micro_tick)
            deadline_ticks += int(deadline_tick)

            # DeadHold can only cross the inventory bridge when the measured
            # acceleration contribution of ka exceeds the configured threshold.
            unlock_threshold = chrom.risk_genes.unlock_ka_threshold
            if (
                micro_tick
                and dead_hold_qty > 0
                and acceleration_signal > unlock_threshold
            ):
                unlocked_qty = dead_hold_qty
                dead_hold_qty = 0.0
                float_hold_qty += unlocked_qty
                if position_open_candle is None:
                    position_open_candle = i
                unlock_events.append({
                    "timestamp": timestamp,
                    "qty": unlocked_qty,
                    "acceleration_signal": acceleration_signal,
                })

            # === Stage 4: MinTradeThreshold — skip if deviation too small ===
            deviation_from_target = abs(target_weight - actual_weight)
            skip_trade = deviation_from_target < min_trade_threshold

            # === Stage 4: hold_period — forced exit if too long ===
            hold_period_exit = (
                position_open_candle is not None
                and (i - position_open_candle) >= hold_period
                and deadline_tick
            )

            # === 檢查出場 ===
            if position_qty > 0 and position_avg_cost > 0:
                max_sellable = float_hold_qty
                exit_qty = 0.0
                exit_reason = None

                if max_sellable > 0:
                    unrealized = (current_price - position_avg_cost) / position_avg_cost if position_avg_cost > 0 else 0

                    if unrealized <= chrom.risk_genes.stop_loss_pct:
                        exit_qty = max_sellable
                        exit_reason = "hard_stop"
                    elif unrealized >= chrom.risk_genes.take_profit_pct:
                        exit_qty = max_sellable
                        exit_reason = "take_profit"
                    elif hold_period_exit:
                        # Stage 4: force exit after hold_period candles
                        exit_qty = max_sellable
                        exit_reason = "hold_period_expired"
                    elif (
                        micro_tick
                        and not skip_trade
                        and self._check_exit_conditions(i, df, chrom, indicator_values)
                    ):
                        deviation = abs(unrealized)
                        if deviation >= min_trade_threshold:
                            # Stage 4: beta blends between exit fraction and full exit
                            # beta=0 → conservative (micro_reserve_rate fraction)
                            # beta=1 → aggressive (sell all float)
                            sell_frac = (1.0 - beta) * chrom.micro_genes.micro_reserve_rate + beta * 1.0
                            exit_qty = max_sellable * sell_frac
                            exit_reason = "signal_exit"

                    exit_qty = self._truncate_lot(exit_qty)

                    if exit_qty >= self.lot_min and exit_qty <= max_sellable:
                        sell_value = exit_qty * current_price
                        sell_fee = sell_value * self.sell_fee_rate
                        exit_avg_cost = position_avg_cost
                        realized = exit_qty * (current_price - exit_avg_cost) - sell_fee
                        cash += (sell_value - sell_fee)
                        total_sell_notional += sell_value
                        total_realized_pnl += realized
                        total_fees_ledger += sell_fee
                        total_sell_fees += sell_fee

                        # Stage 4: recycle — accumulate a fraction of realized PnL
                        if realized > 0:
                            recycle_pool += realized * recycle_ratio

                        float_hold_qty -= exit_qty
                        position_qty -= exit_qty
                        if position_qty <= self.lot_step / 2:
                            position_qty = 0.0
                            position_avg_cost = 0.0
                        if float_hold_qty <= self.lot_step / 2:
                            float_hold_qty = 0.0
                            position_open_candle = None

                        pnl_pct = realized / (exit_qty * exit_avg_cost) if exit_avg_cost > 0 else 0.0
                        trades.append(SimulatedTrade(
                            symbol=symbol,
                            direction="long",
                            entry_time=timestamp,
                            entry_price=exit_avg_cost,
                            exit_time=timestamp,
                            exit_price=current_price,
                            exit_reason=exit_reason or "sell",
                            pnl_pct=pnl_pct,
                        ))

            # === 檢查進場 ===
            if (
                micro_tick
                and not skip_trade
                and self._check_entry_conditions(i, df, chrom, indicator_values)
            ):
                # Stage 4: sigmoid_scale applied to raw signal weight
                # We model raw_signal as the weighted entry score in [0,1].
                # Apply sigmoid(sigmoid_scale * (score - 0.5)) to shift aggressiveness.
                # For simplicity we use desired_position_weight as the "signal strength".
                raw_signal = desired_position_weight - 0.5  # center around 0
                scaled_signal = 1.0 / (1.0 + math.exp(-sigmoid_scale * raw_signal))

                base_position_pct = chrom.risk_genes.position_pct * scaled_signal * 2.0
                active_season_mult = (
                    active_season.aggressiveness if active_season else season_mult
                )
                adjusted_pct = base_position_pct * active_season_mult
                adjusted_pct = min(adjusted_pct, usable_cash_ratio)

                # Stage 4: gamma — risk-aversion exponent reduces size when already heavy
                if actual_weight > 0:
                    gamma_factor = (1.0 - actual_weight) ** gamma
                else:
                    gamma_factor = 1.0
                adjusted_pct *= gamma_factor

                # Stage 4: add recycled PnL to invest budget
                recycle_bonus = recycle_pool

                invest_amount = cash * adjusted_pct + recycle_bonus
                invest_amount = min(invest_amount, cash * usable_cash_ratio)

                qty = invest_amount / current_price if current_price > 0 else 0.0
                qty = self._truncate_lot(qty)

                if qty >= self.lot_min and invest_amount <= cash * usable_cash_ratio:
                    buy_value = qty * current_price
                    buy_fee = buy_value * self.buy_fee_rate
                    total_cost = buy_value + buy_fee

                    if total_cost <= cash:
                        prev_total_cost = position_avg_cost * position_qty
                        new_total_cost = prev_total_cost + total_cost
                        new_qty = position_qty + qty
                        position_avg_cost = new_total_cost / new_qty if new_qty > 0 else 0.0

                        cash -= total_cost
                        total_buy_notional += buy_value
                        position_qty = new_qty
                        total_fees_ledger += buy_fee
                        total_buy_fees += buy_fee

                        # 庫存橋分配
                        allocation_total = (
                            chrom.risk_genes.dead_hold_ratio
                            + chrom.risk_genes.float_hold_ratio
                        )
                        if allocation_total > 0:
                            dead_fraction = (
                                chrom.risk_genes.dead_hold_ratio / allocation_total
                                if macro_tick else 0.0
                            )
                        else:
                            dead_fraction = 0.0
                        dead_alloc = qty * dead_fraction
                        float_alloc = qty - dead_alloc
                        dead_hold_qty += dead_alloc
                        if float_alloc > 0 and position_open_candle is None:
                            position_open_candle = i
                        float_hold_qty += float_alloc

                        recycled_profit_deployed += recycle_bonus
                        recycle_pool = 0.0

        # 結束時強制平倉（只平 FloatHold）
        if position_qty > 0 and float_hold_qty > 0:
            last_price = df['close'].iloc[-1]
            exit_qty = min(float_hold_qty, position_qty)
            exit_qty = self._truncate_lot(exit_qty)

            if exit_qty >= self.lot_min:
                sell_value = exit_qty * last_price
                sell_fee = sell_value * self.sell_fee_rate
                exit_avg_cost = position_avg_cost
                realized = exit_qty * (last_price - exit_avg_cost) - sell_fee
                cash += (sell_value - sell_fee)
                total_sell_notional += sell_value
                total_realized_pnl += realized
                total_fees_ledger += sell_fee
                total_sell_fees += sell_fee

                float_hold_qty -= exit_qty
                position_qty -= exit_qty
                if position_qty <= self.lot_step / 2:
                    position_qty = 0.0
                    position_avg_cost = 0.0

                pnl_pct = realized / (exit_qty * exit_avg_cost) if exit_avg_cost > 0 else 0.0
                trades.append(SimulatedTrade(
                    symbol=symbol,
                    direction="long",
                    entry_time=timestamp,
                    entry_price=exit_avg_cost,
                    exit_time=int(df.index[-1].timestamp() * 1000),
                    exit_price=last_price,
                    exit_reason="end_of_test",
                    pnl_pct=pnl_pct,
                ))

        # Include the final marked-to-market portfolio value after forced exits.
        if not df.empty:
            final_price = float(df["close"].iloc[-1])
            final_equity = cash + position_qty * final_price
            equity.append(final_equity)
        else:
            final_price = 0.0
            final_equity = cash

        raw_ledger = {
            "total_fees": total_fees_ledger,
            "total_buy_fees": total_buy_fees,
            "total_sell_fees": total_sell_fees,
            "realized_pnl": total_realized_pnl,
            "recycled_profit_deployed": recycled_profit_deployed,
            "recycle_pool_remaining": recycle_pool,
            "seasons_applied": seasons_applied,
            "cash": cash,
            "position_qty": position_qty,
            "position_avg_cost": position_avg_cost,
            "dead_hold_qty": dead_hold_qty,
            "float_hold_qty": float_hold_qty,
            "final_price": final_price,
            "final_equity": final_equity,
            "total_buy_notional": total_buy_notional,
            "total_sell_notional": total_sell_notional,
            "macro_ticks": macro_ticks,
            "micro_ticks": micro_ticks,
            "deadline_ticks": deadline_ticks,
            "unlock_events": unlock_events,
        }
        return equity, trades, raw_ledger
    
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
        raw_metrics: Optional[Dict] = None,
    ) -> BacktestMetricsV2:
        """構建 V2 回測指標"""
        # Stage 2: use actual fees from ledger (raw_metrics) if available
        actual_fees = 0.0
        if raw_metrics:
            actual_fees = raw_metrics.get("total_fees", 0.0)
        fee_drag = actual_fees / self.initial_capital if self.initial_capital > 0 else 0.0

        if not trades:
            return BacktestMetricsV2(
                total_trades=0,
                total_pnl=0.0,
                ghost_dca_pnl=dca_return,
                alpha_vs_dca=alpha,
                total_fees_paid=actual_fees,
                fee_drag_pct=fee_drag,
            )
        
        winning_trades = sum(1 for t in trades if t.pnl_pct > 0)
        losing_trades = len(trades) - winning_trades

        pnl_values = [t.pnl_pct for t in trades]

        total_pnl = sum(pnl_values)
        if raw_metrics and self.initial_capital > 0:
            total_pnl = raw_metrics.get("realized_pnl", 0.0) / self.initial_capital

        # consecutive_losses
        max_consec = 0
        cur_consec = 0
        for p in pnl_values:
            if p <= 0:
                cur_consec += 1
                max_consec = max(max_consec, cur_consec)
            else:
                cur_consec = 0

        wins = [p for p in pnl_values if p > 0]
        losses = [p for p in pnl_values if p <= 0]
        profit_factor = sum(wins) / abs(sum(losses)) if losses else 999.0
        expectancy = ((winning_trades / len(trades)) * (np.mean(wins) if wins else 0.0)
                      + ((losing_trades / len(trades)) * (np.mean(losses) if losses else 0.0)))

        return BacktestMetricsV2(
            total_trades=len(trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=winning_trades / len(trades) if trades else 0.0,
            avg_profit=float(np.mean(wins)) if wins else 0.0,
            avg_loss=float(np.mean(losses)) if losses else 0.0,
            total_pnl=total_pnl,
            total_pnl_after_fees=total_pnl,  # pnl_pct already net of fees
            max_drawdown=self._calculate_max_drawdown(equity),
            sharpe_ratio=self._calculate_sharpe(equity),
            profit_factor=profit_factor,
            expectancy=expectancy,
            consecutive_losses=max_consec,
            best_trade=max(pnl_values) if pnl_values else 0.0,
            worst_trade=min(pnl_values) if pnl_values else 0.0,
            ghost_dca_pnl=dca_return,
            alpha_vs_dca=alpha,
            total_fees_paid=actual_fees,
            fee_drag_pct=fee_drag,
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
    V2 多幣種評估 — Stage 2 aggregation wired in.

    Multi-symbol aggregation (Stage 2):
    - Collects BacktestMetricsV2 from ALL symbols (required = all configured symbols)
    - If ANY required symbol has data_invalid=True, empty trades, or < 5 trades →
      return fitness=0, insufficient_data=True logged
    - Aggregates required metrics across ALL successful symbols, then passes the
      combined BacktestMetricsV2 to compute_fitness_v2 (approach a: aggregate raw
      metrics into one object so the existing scoring formula is used unchanged).

    Aggregated fields per Fix 3:
      - alpha_vs_dca       : weighted average (by trade count)
      - total_pnl_after_fees: sum across symbols
      - max_drawdown       : worst across symbols
      - win_rate           : weighted by trade count
      - profit_factor      : total_gross_profit / total_gross_loss
      - consecutive_losses : max across symbols
      - total_fees_paid    : sum across symbols
      - total_trades       : sum across symbols
    """
    from .fitness_v2 import BacktestMetricsV2, compute_fitness_v2, compute_fitness_details_v2

    MIN_TRADES_PER_SYMBOL = 5

    if engine is None:
        engine = GeneBacktestEngineV2()

    per_symbol: Dict[str, V2BacktestResult] = {}
    all_trades: List[SimulatedTrade] = []

    if verbose:
        print(f"\n🔬 V2 Evaluating {chrom.chromosome_id[:8]} on {len(symbols)} symbols...")

    for symbol in symbols:
        result = engine.evaluate_v2(
            chrom, symbol, interval, days,
            seasons=seasons, environment=environment, verbose=verbose
        )

        per_symbol[symbol] = result
        all_trades.extend(result.strategy_trades)

    # ── Validate ALL required symbols ─────────────────────────────────────────
    insufficient_data = False
    for symbol in symbols:
        r = per_symbol.get(symbol)
        if r is None:
            if verbose:
                print(f"   ❌ {symbol}: missing result")
            insufficient_data = True
        elif r.data_invalid or r.strategy_metrics.data_invalid:
            if verbose:
                print(f"   ❌ {symbol}: data_invalid=True")
            insufficient_data = True
        elif r.strategy_metrics.total_trades == 0:
            if verbose:
                print(f"   ❌ {symbol}: empty trades")
            insufficient_data = True
        elif r.strategy_metrics.total_trades < MIN_TRADES_PER_SYMBOL:
            if verbose:
                print(f"   ❌ {symbol}: insufficient samples ({r.strategy_metrics.total_trades} trades)")
            insufficient_data = True

    if insufficient_data:
        if verbose:
            print(f"   ⚠️ Required symbol failed — fitness=0")
        return 0.0, per_symbol, all_trades

    # ── Aggregate metrics across ALL symbols ──────────────────────────────────
    # Approach (a): aggregate raw metrics into one BacktestMetricsV2 object,
    # then pass to compute_fitness_v2.  This keeps the existing scoring formula
    # intact and avoids creating a parallel ranking formula.

    valid_results = [per_symbol[s] for s in symbols]
    valid_metrics = [r.strategy_metrics for r in valid_results]

    trade_counts = [m.total_trades for m in valid_metrics]
    total_trades_all = sum(trade_counts)

    def _weighted(vals: List[float], weights: List[int]) -> float:
        total_w = sum(weights)
        if total_w == 0:
            return float(np.mean(vals)) if vals else 0.0
        return float(sum(v * w for v, w in zip(vals, weights)) / total_w)

    # alpha_vs_dca: weighted average
    alpha_vs_dca_agg = _weighted([r.alpha_vs_dca for r in valid_results], trade_counts)

    # realized PnL after fees: sum
    total_pnl_after_fees = sum(m.total_pnl_after_fees for m in valid_metrics)

    # total_pnl: sum
    total_pnl = sum(m.total_pnl for m in valid_metrics)

    # max_drawdown: worst
    max_drawdown_agg = max(m.max_drawdown for m in valid_metrics)

    # win_rate: weighted
    win_rate_agg = _weighted([m.win_rate for m in valid_metrics], trade_counts)

    # profit_factor: aggregate (total gross profit / total gross loss)
    total_gross_profit = sum(m.avg_profit * m.winning_trades for m in valid_metrics)
    total_gross_loss = sum(abs(m.avg_loss) * m.losing_trades for m in valid_metrics)
    profit_factor_agg = total_gross_profit / total_gross_loss if total_gross_loss > 0 else 999.0

    # consecutive_losses: max
    consec_losses_agg = max(m.consecutive_losses for m in valid_metrics)

    # total_fees: sum
    total_fees_agg = sum(m.total_fees_paid for m in valid_metrics)

    # ghost_dca_pnl: mean (for alpha baseline)
    ghost_dca_pnl_agg = float(np.mean([m.ghost_dca_pnl for m in valid_metrics]))

    # sharpe: mean
    sharpe_agg = float(np.mean([m.sharpe_ratio for m in valid_metrics]))

    # fee_drag_pct: based on total fees / initial capital
    fee_drag_agg = total_fees_agg / engine.initial_capital if engine.initial_capital > 0 else 0.0

    agg_m = BacktestMetricsV2(
        total_trades=total_trades_all,
        winning_trades=sum(m.winning_trades for m in valid_metrics),
        losing_trades=sum(m.losing_trades for m in valid_metrics),
        win_rate=win_rate_agg,
        avg_profit=_weighted([m.avg_profit for m in valid_metrics], [m.winning_trades for m in valid_metrics]),
        avg_loss=_weighted([m.avg_loss for m in valid_metrics], [m.losing_trades for m in valid_metrics]),
        total_pnl=total_pnl,
        total_pnl_after_fees=total_pnl_after_fees,
        max_drawdown=max_drawdown_agg,
        sharpe_ratio=sharpe_agg,
        profit_factor=profit_factor_agg,
        expectancy=_weighted([m.expectancy for m in valid_metrics], trade_counts),
        consecutive_losses=consec_losses_agg,
        best_trade=max(m.best_trade for m in valid_metrics),
        worst_trade=min(m.worst_trade for m in valid_metrics),
        ghost_dca_pnl=ghost_dca_pnl_agg,
        alpha_vs_dca=alpha_vs_dca_agg,
        alpha_per_trade=alpha_vs_dca_agg / total_trades_all if total_trades_all > 0 else 0.0,
        total_fees_paid=total_fees_agg,
        fee_drag_pct=fee_drag_agg,
    )

    fitness = compute_fitness_v2(agg_m)

    if verbose:
        print(f"   V2 Aggregate: Alpha={alpha_vs_dca_agg:+.4f} | DD={max_drawdown_agg:.4f} | "
              f"Trades={total_trades_all} | Fit={fitness:.4f}")

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
