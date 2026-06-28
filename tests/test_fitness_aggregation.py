#!/usr/bin/env python3
"""
Tests for Stage 2: multi-symbol fitness aggregation, fee calculation,
partial sell PnL/cost, and ledger conservation.

All tests are fully mocked — no real API or exchange calls.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.genetic_engine.fitness_aggregation import (
    AggregatedFitnessResult,
    SymbolResult,
    Position,
    aggregate_multi_symbol_fitness,
    calculate_fee,
    DEFAULT_FEE_RATE,
    MIN_SAMPLE_TRADES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ok_result(symbol: str, alpha: float = 0.05, pnl: float = 50.0,
               drawdown: float = 0.10, win_rate: float = 0.55,
               cost: float = 2.0, n_trades: int = 20) -> SymbolResult:
    return SymbolResult(
        symbol=symbol,
        realized_pnl=pnl,
        alpha=alpha,
        max_drawdown=drawdown,
        win_rate=win_rate,
        total_cost=cost,
        n_trades=n_trades,
    )


def _invalid_result(symbol: str) -> SymbolResult:
    return SymbolResult(symbol=symbol, data_invalid=True)


def _empty_result(symbol: str) -> SymbolResult:
    return SymbolResult(symbol=symbol, empty_trades=True)


def _insufficient_result(symbol: str) -> SymbolResult:
    """Fewer than MIN_SAMPLE_TRADES trades."""
    return SymbolResult(symbol=symbol, n_trades=MIN_SAMPLE_TRADES - 1)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: aggregation uses all symbols (not just the first)
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregationUsesAllSymbols:
    def test_aggregation_uses_all_symbols(self):
        """Result must aggregate 3 symbols, not just the first one."""
        results = {
            "BTCUSDT": _ok_result("BTCUSDT", alpha=0.10, pnl=100.0),
            "ETHUSDT": _ok_result("ETHUSDT", alpha=0.02, pnl=20.0),
            "BNBUSDT": _ok_result("BNBUSDT", alpha=0.06, pnl=60.0),
        }

        agg = aggregate_multi_symbol_fitness(results)

        assert agg.n_symbols_ok == 3, "All 3 symbols should be included"
        assert agg.n_symbols_failed == 0

        # alpha should be mean of all 3, not just first
        expected_alpha = (0.10 + 0.02 + 0.06) / 3
        assert abs(agg.alpha - expected_alpha) < 1e-9, (
            f"Expected mean alpha {expected_alpha:.4f}, got {agg.alpha:.4f}. "
            "Aggregation must use ALL symbols."
        )

        # realized_pnl should be sum of all 3
        expected_pnl = 100.0 + 20.0 + 60.0
        assert abs(agg.realized_pnl - expected_pnl) < 1e-9

        assert agg.fitness_score > 0.0, "Positive aggregate alpha should yield positive fitness"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: failed symbol excluded from fitness but tracked
# ─────────────────────────────────────────────────────────────────────────────

class TestFailedSymbolExcludedFromFitness:
    def test_failed_symbol_excluded_from_fitness(self):
        """1 of 3 symbols data_invalid → excluded from agg, tracked in per_symbol_status."""
        results = {
            "BTCUSDT": _ok_result("BTCUSDT", alpha=0.08, pnl=80.0),
            "ETHUSDT": _invalid_result("ETHUSDT"),
            "BNBUSDT": _ok_result("BNBUSDT", alpha=0.04, pnl=40.0),
        }

        agg = aggregate_multi_symbol_fitness(results)

        assert agg.n_symbols_ok == 2
        assert agg.n_symbols_failed == 1
        assert agg.per_symbol_status.get("ETHUSDT") == "data_invalid", (
            "Failed symbol must be tracked with 'data_invalid' status"
        )

        # Aggregated alpha must NOT include ETHUSDT
        expected_alpha = (0.08 + 0.04) / 2
        assert abs(agg.alpha - expected_alpha) < 1e-9, (
            f"Expected alpha {expected_alpha:.4f} (2 symbols), got {agg.alpha:.4f}"
        )

        # Realized PnL is from 2 successful symbols only
        expected_pnl = 80.0 + 40.0
        assert abs(agg.realized_pnl - expected_pnl) < 1e-9

        # Overall result is not data_invalid (we still have successful symbols)
        assert not agg.data_invalid
        assert agg.fitness_score > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: missing required symbol → no normal fitness
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingRequiredSymbolNoNormalFitness:
    def test_missing_required_symbol_no_normal_fitness(self):
        """Strategy requires BTC+ETH; only BTC data provided → insufficient_data, fitness=0."""
        results = {
            "BTCUSDT": _ok_result("BTCUSDT"),
            # ETHUSDT intentionally missing
        }

        agg = aggregate_multi_symbol_fitness(
            results,
            required_symbols={"BTCUSDT", "ETHUSDT"},
        )

        assert agg.insufficient_data is True, (
            "Missing required symbol must set insufficient_data=True"
        )
        assert agg.fitness_score == 0.0, (
            "Strategy missing required symbol must have fitness_score=0"
        )

    def test_failed_required_symbol_no_normal_fitness(self):
        """Required symbol exists but is data_invalid → insufficient_data."""
        results = {
            "BTCUSDT": _ok_result("BTCUSDT"),
            "ETHUSDT": _invalid_result("ETHUSDT"),
        }

        agg = aggregate_multi_symbol_fitness(
            results,
            required_symbols={"BTCUSDT", "ETHUSDT"},
        )

        assert agg.insufficient_data is True
        assert agg.fitness_score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: fee calculated on trade value, not trade count
# ─────────────────────────────────────────────────────────────────────────────

class TestFeeCalculatedOnTradeValue:
    def test_fee_calculated_on_trade_value(self):
        """fee = amount * price * 2 * fee_rate (round-trip), not count-based."""
        qty = 0.5         # BTC
        price = 50_000.0  # USDT per BTC
        fee_rate = 0.001

        trade_value = qty * price  # 25_000 USDT
        expected_fee = trade_value * fee_rate * 2  # 50 USDT

        actual_fee = calculate_fee(trade_value, fee_rate)
        assert abs(actual_fee - expected_fee) < 1e-9, (
            f"Expected fee {expected_fee}, got {actual_fee}. "
            "Fee must be trade_value * fee_rate * 2."
        )

    def test_fee_not_count_based(self):
        """Halving the qty halves the fee (not same fee regardless of amount)."""
        fee1 = calculate_fee(trade_value=1000.0)
        fee2 = calculate_fee(trade_value=500.0)
        assert abs(fee1 - fee2 * 2) < 1e-9, (
            "Fee must scale proportionally with trade value"
        )

    def test_fee_default_rate(self):
        """Default fee rate is 0.1%."""
        fee = calculate_fee(trade_value=10_000.0)
        assert abs(fee - 10_000.0 * DEFAULT_FEE_RATE * 2) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 & 6: partial sell — position cost and realized PnL
# ─────────────────────────────────────────────────────────────────────────────

class TestPartialSellPositionCost:
    def _make_position(self) -> Position:
        """Buy 1.0 BTC at 40_000 USDT."""
        pos = Position()
        pos.buy(qty=1.0, price=40_000.0, fee_rate=0.0)  # fee_rate=0 to isolate cost logic
        return pos

    def test_partial_sell_avg_cost_unchanged(self):
        """Sell 50% of position; avg_cost of remainder must be unchanged."""
        pos = self._make_position()
        initial_avg_cost = pos.avg_cost

        pos.sell(qty=0.5, price=50_000.0, fee_rate=0.0)

        assert abs(pos.avg_cost - initial_avg_cost) < 1e-9, (
            f"avg_cost should remain {initial_avg_cost} after partial sell, "
            f"got {pos.avg_cost}"
        )

    def test_partial_sell_remaining_qty(self):
        """Sell 50% → 50% remains."""
        pos = self._make_position()
        pos.sell(qty=0.5, price=50_000.0, fee_rate=0.0)
        assert abs(pos.qty - 0.5) < 1e-9

    def test_partial_sell_remaining_cost(self):
        """remaining_cost = avg_cost * remaining_qty."""
        pos = self._make_position()
        avg_cost = pos.avg_cost
        pos.sell(qty=0.5, price=50_000.0, fee_rate=0.0)

        expected_total_cost = avg_cost * 0.5
        assert abs(pos.total_cost - expected_total_cost) < 1e-9, (
            f"Expected remaining cost {expected_total_cost}, got {pos.total_cost}"
        )


class TestPartialSellRealizedPnL:
    def test_partial_sell_realized_pnl(self):
        """realized_pnl = sold_qty * (sell_price - avg_cost)."""
        pos = Position()
        pos.buy(qty=1.0, price=40_000.0, fee_rate=0.0)
        avg_cost = pos.avg_cost  # 40_000

        sell_qty = 0.5
        sell_price = 50_000.0

        realized_pnl, fee = pos.sell(qty=sell_qty, price=sell_price, fee_rate=0.0)

        expected_pnl = sell_qty * (sell_price - avg_cost)  # 0.5 * 10_000 = 5_000
        assert abs(realized_pnl - expected_pnl) < 1e-6, (
            f"Expected realized PnL {expected_pnl}, got {realized_pnl}"
        )

    def test_partial_sell_realized_pnl_with_fee(self):
        """With fee: realized_pnl = qty * (sell_price - avg_cost) - sell_fee."""
        pos = Position()
        pos.buy(qty=1.0, price=40_000.0, fee_rate=0.0)

        sell_qty = 0.5
        sell_price = 50_000.0
        fee_rate = 0.001

        realized_pnl, fee = pos.sell(qty=sell_qty, price=sell_price, fee_rate=fee_rate)

        expected_fee = sell_qty * sell_price * fee_rate
        expected_pnl = sell_qty * (sell_price - 40_000.0) - expected_fee
        assert abs(fee - expected_fee) < 1e-6
        assert abs(realized_pnl - expected_pnl) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: ledger conservation
# ─────────────────────────────────────────────────────────────────────────────

class TestLedgerConservation:
    """
    Conservation law (net-fee accounting):

        cash + position_value == initial_capital + realized_pnl_net

    Where:
        - cash is decreased by (qty*price + buy_fee) on each buy
        - cash is increased by (qty*price - sell_fee) on each sell
        - realized_pnl_net (returned by Position.sell) already deducts sell-side fees
          AND the buy-side fee is baked into avg_cost (so it's deducted from PnL)
        - position_value = remaining_qty * current_mark_price

    Note: fees do NOT appear as a separate term because they are already embedded
    in realized_pnl (via avg_cost on buy-side, and subtracted directly on sell-side).
    """

    def test_ledger_conservation_single_buy_sell(self):
        """Full buy then full sell conserves the ledger."""
        initial_capital = 10_000.0
        fee_rate = 0.001

        cash = initial_capital
        realized_pnl = 0.0

        pos = Position()

        # Buy 0.2 BTC at 40_000
        qty_buy = 0.2
        price_buy = 40_000.0
        fee_buy = pos.buy(qty=qty_buy, price=price_buy, fee_rate=fee_rate)
        cash -= (qty_buy * price_buy + fee_buy)

        # Sell all at 50_000
        price_sell = 50_000.0
        pnl, fee_sell = pos.sell(qty=qty_buy, price=price_sell, fee_rate=fee_rate)
        cash += (qty_buy * price_sell - fee_sell)
        realized_pnl += pnl

        position_value = pos.qty * price_sell

        lhs = cash + position_value
        rhs = initial_capital + realized_pnl

        assert abs(lhs - rhs) < 1e-6, (
            f"Ledger broke: cash+pos={lhs:.6f} ≠ capital+pnl={rhs:.6f}"
        )

    def test_ledger_conservation_partial_sell(self):
        """Partial sell: ledger holds after selling 50% then remaining 50%."""
        initial_capital = 5_000.0
        fee_rate = 0.001

        cash = initial_capital
        realized_pnl = 0.0

        pos = Position()

        # Buy 0.1 BTC at 30_000
        qty_buy = 0.1
        price_buy = 30_000.0
        fee_buy = pos.buy(qty=qty_buy, price=price_buy, fee_rate=fee_rate)
        cash -= (qty_buy * price_buy + fee_buy)

        # Partial sell: 0.05 BTC at 35_000
        qty_sell1 = 0.05
        price_sell1 = 35_000.0
        pnl1, fee1 = pos.sell(qty=qty_sell1, price=price_sell1, fee_rate=fee_rate)
        cash += (qty_sell1 * price_sell1 - fee1)
        realized_pnl += pnl1

        # Sell remaining 0.05 BTC at 40_000
        qty_sell2 = pos.qty
        price_sell2 = 40_000.0
        pnl2, fee2 = pos.sell(qty=qty_sell2, price=price_sell2, fee_rate=fee_rate)
        cash += (qty_sell2 * price_sell2 - fee2)
        realized_pnl += pnl2

        position_value = pos.qty * price_sell2  # should be 0

        lhs = cash + position_value
        rhs = initial_capital + realized_pnl

        assert abs(lhs - rhs) < 1e-6, (
            f"Partial-sell ledger broke: lhs={lhs:.6f} rhs={rhs:.6f}"
        )

    def test_ledger_conservation_multiple_buys(self):
        """Multiple buys and a single full sell also conserves the ledger."""
        initial_capital = 20_000.0
        fee_rate = 0.001

        cash = initial_capital
        realized_pnl = 0.0

        pos = Position()

        # Buy 1: 0.1 BTC at 40_000
        fee = pos.buy(0.1, 40_000.0, fee_rate)
        cash -= (0.1 * 40_000.0 + fee)

        # Buy 2: 0.2 BTC at 42_000
        fee = pos.buy(0.2, 42_000.0, fee_rate)
        cash -= (0.2 * 42_000.0 + fee)

        # Sell all at 45_000
        total_qty = pos.qty
        pnl, fee = pos.sell(total_qty, 45_000.0, fee_rate)
        cash += (total_qty * 45_000.0 - fee)
        realized_pnl += pnl

        position_value = pos.qty * 45_000.0

        lhs = cash + position_value
        rhs = initial_capital + realized_pnl

        assert abs(lhs - rhs) < 1e-6, (
            f"Multi-buy ledger broke: lhs={lhs:.6f} rhs={rhs:.6f}"
        )
