#!/usr/bin/env python3
"""
Multi-Symbol Fitness Aggregation / 多幣種適應度聚合

Stage 2 additions:
- Aggregate Alpha, realized PnL, max drawdown, win rate, total cost from ALL symbols
- Exclude data_invalid / empty / insufficient-sample symbols from aggregation
- Track excluded symbols separately
- Strategy missing required symbols → insufficient_data result (no normal fitness)
- Fee = trade_value * fee_rate * 2 (both legs)
- Partial sell: realized_pnl = sold_qty * (sell_price - avg_cost)
              remaining_cost = avg_cost * remaining_qty  (avg_cost unchanged)

Author: second_bot
Date: 2026-06-14
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any

import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregated result container
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AggregatedFitnessResult:
    """Result of multi-symbol fitness aggregation."""

    # Aggregated metrics (over successful symbols only)
    alpha: float = 0.0            # mean alpha vs baseline
    realized_pnl: float = 0.0    # sum of realized PnL across symbols
    max_drawdown: float = 0.0     # mean max drawdown
    win_rate: float = 0.0         # weighted win rate
    total_cost: float = 0.0       # total fees paid

    # Counts
    n_symbols_ok: int = 0
    n_symbols_failed: int = 0

    # Status flags
    data_invalid: bool = False
    insufficient_data: bool = False   # required symbol missing

    # Per-symbol breakdown
    per_symbol_status: Dict[str, str] = field(default_factory=dict)  # symbol → "ok"|"data_invalid"|"empty_trades"|"insufficient_samples"

    # Fitness score (0–1)
    fitness_score: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Fee calculation helper
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_FEE_RATE = 0.001  # 0.1%


def calculate_fee(trade_value: float, fee_rate: float = DEFAULT_FEE_RATE) -> float:
    """
    Calculate round-trip fee for a trade.

    fee = trade_value * fee_rate * 2   (buy leg + sell leg)

    Args:
        trade_value: executed amount in quote currency (qty * price)
        fee_rate:    per-leg fee rate (default 0.001 = 0.1%)

    Returns:
        Total fee for both legs.
    """
    return trade_value * fee_rate * 2


# ═══════════════════════════════════════════════════════════════════════════════
# Position / trade ledger helpers
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    """Tracks an open position and its average cost."""
    qty: float = 0.0
    avg_cost: float = 0.0   # cost per unit (not total)
    total_cost: float = 0.0 # avg_cost * qty

    def buy(self, qty: float, price: float, fee_rate: float = DEFAULT_FEE_RATE) -> float:
        """
        Add qty at price.  avg_cost is updated.

        Returns:
            Fee paid for this buy leg.
        """
        trade_value = qty * price
        fee = trade_value * fee_rate  # buy-side fee only
        new_qty = self.qty + qty
        new_cost = self.total_cost + trade_value + fee  # cost includes fee
        self.avg_cost = new_cost / new_qty if new_qty > 0 else 0.0
        self.total_cost = new_cost
        self.qty = new_qty
        return fee

    def sell(
        self, qty: float, price: float, fee_rate: float = DEFAULT_FEE_RATE
    ) -> tuple[float, float]:
        """
        Sell qty at price.  avg_cost of the remaining position is unchanged.

        Returns:
            (realized_pnl, fee)
            realized_pnl = qty * (price - avg_cost)  [before sell-side fee]
            fee = qty * price * fee_rate              [sell-side fee only]
        """
        if qty > self.qty:
            qty = self.qty  # clamp to available

        trade_value = qty * price
        fee = trade_value * fee_rate

        # Realized PnL on the sold portion (avg_cost unchanged)
        realized_pnl = qty * (price - self.avg_cost) - fee

        # Update position
        self.qty -= qty
        self.total_cost = self.avg_cost * self.qty  # cost = avg * remaining qty

        return realized_pnl, fee


# ═══════════════════════════════════════════════════════════════════════════════
# Per-symbol result format (simplified, mirrors BacktestMetrics)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SymbolResult:
    """Minimal per-symbol result used by aggregation."""
    symbol: str = ""
    realized_pnl: float = 0.0
    alpha: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_cost: float = 0.0
    n_trades: int = 0

    # Failure flags
    data_invalid: bool = False
    empty_trades: bool = False
    insufficient_samples: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregation logic
# ═══════════════════════════════════════════════════════════════════════════════

MIN_SAMPLE_TRADES = 5  # below this → insufficient_samples


def aggregate_multi_symbol_fitness(
    symbol_results: Dict[str, SymbolResult],
    required_symbols: Optional[Set[str]] = None,
) -> AggregatedFitnessResult:
    """
    Aggregate fitness from all symbol results.

    Rules:
    - Symbols flagged data_invalid, empty_trades, or insufficient_samples are
      EXCLUDED from the aggregate and counted separately.
    - If any required_symbol is missing or failed, the overall result is marked
      insufficient_data and fitness_score = 0.
    - Otherwise fitness_score is derived from mean alpha, mean drawdown, win rate.

    Args:
        symbol_results:   dict of symbol → SymbolResult
        required_symbols: if provided, all must have a successful result

    Returns:
        AggregatedFitnessResult
    """
    agg = AggregatedFitnessResult()

    ok_results: List[SymbolResult] = []
    failed_symbols: List[str] = []

    for sym, res in symbol_results.items():
        if res.data_invalid:
            agg.per_symbol_status[sym] = "data_invalid"
            failed_symbols.append(sym)
        elif res.empty_trades:
            agg.per_symbol_status[sym] = "empty_trades"
            failed_symbols.append(sym)
        elif res.insufficient_samples or res.n_trades < MIN_SAMPLE_TRADES:
            agg.per_symbol_status[sym] = "insufficient_samples"
            failed_symbols.append(sym)
        else:
            agg.per_symbol_status[sym] = "ok"
            ok_results.append(res)

    agg.n_symbols_ok = len(ok_results)
    agg.n_symbols_failed = len(failed_symbols)

    # Check required symbols
    if required_symbols:
        ok_syms = {r.symbol for r in ok_results}
        missing = required_symbols - set(symbol_results.keys())
        failed_required = required_symbols & set(failed_symbols)
        if missing or failed_required:
            agg.insufficient_data = True
            agg.fitness_score = 0.0
            return agg

    # If no successful symbols, data_invalid overall
    if not ok_results:
        agg.data_invalid = True
        agg.fitness_score = 0.0
        return agg

    # Aggregate over successful symbols
    agg.alpha = float(np.mean([r.alpha for r in ok_results]))
    agg.realized_pnl = float(sum(r.realized_pnl for r in ok_results))
    agg.max_drawdown = float(np.mean([r.max_drawdown for r in ok_results]))
    agg.total_cost = float(sum(r.total_cost for r in ok_results))

    # Weighted win rate (by trade count)
    total_trades = sum(r.n_trades for r in ok_results)
    if total_trades > 0:
        agg.win_rate = sum(r.win_rate * r.n_trades for r in ok_results) / total_trades
    else:
        agg.win_rate = 0.0

    # Simple fitness score
    agg.fitness_score = _compute_fitness_from_agg(agg)

    return agg


def _compute_fitness_from_agg(agg: AggregatedFitnessResult) -> float:
    """Derive a [0, 1] fitness score from aggregated metrics."""
    if agg.data_invalid or agg.insufficient_data:
        return 0.0

    # Alpha component: sigmoid around 0 (positive alpha is good)
    import math
    def _sig(x: float, k: float = 10.0) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-x * k))
        except OverflowError:
            return 1.0 if x > 0 else 0.0

    alpha_score = _sig(agg.alpha, k=10.0)
    dd_score = max(0.0, 1.0 - agg.max_drawdown)
    wr_score = max(0.0, min(1.0, agg.win_rate))

    fitness = alpha_score * 0.50 + dd_score * 0.30 + wr_score * 0.20
    return round(max(0.0, min(1.0, fitness)), 6)
