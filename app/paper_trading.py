"""
Paper Trading Simulator
Simulates trading with realistic slippage, latency, and fees.
"""

import json
import logging
import random
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TradeSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class SimulatedTrade:
    """Simulated trade record."""

    trade_id: str
    symbol: str
    side: TradeSide
    quantity: float
    entry_price: float
    exit_price: Optional[float] = None
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None

    # Simulated costs
    slippage: float = 0.0
    commission: float = 0.0
    realized_pnl: float = 0.0
    strategy_id: Optional[str] = None  # Which strategy generated this trade

    def to_dict(self) -> Dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "slippage": self.slippage,
            "commission": self.commission,
            "realized_pnl": self.realized_pnl,
            "strategy_id": self.strategy_id,
        }


class PaperTrading:
    """
    Paper trading simulator with realistic execution.

    Simulates:
    - Slippage (market impact)
    - Latency (order delay)
    - Commission fees
    - Partial fills
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        slippage_pct: float = 0.1,
        commission_pct: float = 0.1,
        latency_ms: int = 200,
    ):
        self.logger = logging.getLogger(__name__)

        # Account
        self.balance = initial_balance
        self.initial_balance = initial_balance

        # Simulation parameters
        self.slippage_pct = slippage_pct
        self.commission_pct = commission_pct
        self.latency_ms = latency_ms

        # State
        self.positions: Dict[str, Dict] = {}
        self.trades: List[SimulatedTrade] = []
        self.equity_curve: List[Dict] = []

        self.logger.info(f"PaperTrading initialized: ${initial_balance:,.2f}")

    def _simulate_slippage(self, price: float, side: TradeSide) -> float:
        """
        Simulate price slippage.

        Args:
            price: Target price
            side: Trade side

        Returns:
            Executed price with slippage
        """
        # Slippage: worse price for market orders
        slippage = price * (self.slippage_pct / 100) * random.gauss(1, 0.5)

        if side == TradeSide.BUY:
            executed = price + abs(slippage)
        else:
            executed = price - abs(slippage)

        return executed

    def _calculate_commission(self, value: float) -> float:
        """Calculate commission fee."""
        return value * (self.commission_pct / 100)

    def enter_position(self, symbol: str, side: TradeSide, quantity: float, price: float, strategy_id: Optional[str] = None) -> SimulatedTrade:
        """
        Enter paper position.

        Args:
            symbol: Trading pair
            side: Buy or sell
            quantity: Position size
            price: Entry price
            strategy_id: Strategy that generated this signal

        Returns:
            SimulatedTrade record
        """
        # Simulate latency
        if self.latency_ms > 0:
            import time

            time.sleep(self.latency_ms / 1000)

        # Simulate slippage
        executed_price = self._simulate_slippage(price, side)

        # Calculate costs
        trade_value = executed_price * quantity
        commission = self._calculate_commission(trade_value)

        # Deduct from balance
        if side == TradeSide.BUY:
            cost = trade_value + commission
            if cost > self.balance:
                self.logger.warning(f"Insufficient balance: ${self.balance:.2f} < ${cost:.2f}")
                quantity = self.balance / (executed_price * (1 + self.commission_pct / 100))
                trade_value = executed_price * quantity
                commission = self._calculate_commission(trade_value)
                cost = trade_value + commission

            self.balance -= cost

        # Record trade
        trade = SimulatedTrade(
            trade_id=f"PT_{len(self.trades)+1}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=executed_price,
            slippage=executed_price - price,
            commission=commission,
            strategy_id=strategy_id,
        )

        self.trades.append(trade)

        # Track position
        self.positions[symbol] = {
            "side": side,
            "quantity": quantity,
            "entry_price": executed_price,
            "entry_time": datetime.now(),
        }

        self.logger.info(
            f"Paper trade: {side.value.upper()} {quantity} {symbol} @ ${executed_price:.2f} "
            f"(slippage: ${executed_price-price:.2f}, comm: ${commission:.2f})"
        )

        # Update equity
        self._update_equity()

        return trade

    def exit_position(self, symbol: str, price: float) -> Optional[SimulatedTrade]:
        """
        Exit paper position.

        Args:
            symbol: Trading pair
            price: Exit price

        Returns:
            Updated SimulatedTrade or None
        """
        if symbol not in self.positions:
            self.logger.warning(f"No position to exit: {symbol}")
            return None

        position = self.positions[symbol]

        # Simulate latency
        if self.latency_ms > 0:
            import time

            time.sleep(self.latency_ms / 1000)

        # Determine exit side (opposite of entry)
        exit_side = TradeSide.SELL if position["side"] == TradeSide.BUY else TradeSide.BUY

        # Simulate slippage
        executed_price = self._simulate_slippage(price, exit_side)

        # Calculate costs
        trade_value = executed_price * position["quantity"]
        commission = self._calculate_commission(trade_value)

        # Calculate P&L
        if position["side"] == TradeSide.BUY:
            pnl = (executed_price - position["entry_price"]) * position["quantity"] - commission
            self.balance += trade_value - commission
        else:
            pnl = (position["entry_price"] - executed_price) * position["quantity"] - commission
            self.balance -= trade_value + commission

        # Find and update trade record
        trade = next((t for t in self.trades if t.symbol == symbol and t.exit_price is None), None)

        if trade:
            trade.exit_price = executed_price
            trade.exit_time = datetime.now()
            trade.commission += commission
            trade.realized_pnl = pnl
        else:
            # No matching trade record found (e.g., after state load)
            # Create a new record for the exit
            trade = SimulatedTrade(
                trade_id=f"sim_{datetime.now().strftime('%Y%m%d%H%M%S')}_{symbol}",
                symbol=symbol,
                side=position["side"],
                quantity=position["quantity"],
                entry_price=position["entry_price"],
                entry_time=position.get("entry_time", datetime.now()),
                exit_price=executed_price,
                exit_time=datetime.now(),
                commission=commission,
                realized_pnl=pnl,
            )
            self.trades.append(trade)

        del self.positions[symbol]

        self.logger.info(f"Paper exit: {symbol} @ ${executed_price:.2f} " f"PnL: ${pnl:.2f} (comm: ${commission:.2f})")

        # Update equity
        self._update_equity()

        return trade

    def _update_equity(self):
        """Update equity curve."""
        # Calculate unrealized P&L
        unrealized = 0
        for symbol, pos in self.positions.items():
            # Use last known price (simplified)
            unrealized += 0  # Would need current price

        self.equity_curve.append(
            {
                "timestamp": datetime.now().isoformat(),
                "balance": self.balance,
                "unrealized_pnl": unrealized,
                "total_equity": self.balance + unrealized,
            }
        )

    def get_performance(self) -> Dict:
        """Get paper trading performance."""
        completed_trades = [t for t in self.trades if t.exit_price is not None]

        total_pnl = sum(t.realized_pnl for t in completed_trades)
        wins = sum(1 for t in completed_trades if t.realized_pnl > 0)
        losses = len(completed_trades) - wins

        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.balance,
            "total_return_pct": (self.balance / self.initial_balance - 1) * 100,
            "total_trades": len(completed_trades),
            "winning_trades": wins,
            "losing_trades": losses,
            "win_rate": wins / len(completed_trades) * 100 if completed_trades else 0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / len(completed_trades) if completed_trades else 0,
            "max_pnl": max((t.realized_pnl for t in completed_trades), default=0),
            "min_pnl": min((t.realized_pnl for t in completed_trades), default=0),
            "open_positions": len(self.positions),
            "open_position_symbols": list(self.positions.keys()),
        }

    def save_state(self, filepath: str) -> None:
        """Save paper trading state to file / 儲存模擬交易狀態到檔案"""
        import json
        state = {
            "balance": self.balance,
            "initial_balance": self.initial_balance,
            "positions": {
                sym: {
                    "side": pos["side"].value,
                    "quantity": pos["quantity"],
                    "entry_price": pos["entry_price"],
                    "entry_time": pos["entry_time"].isoformat() if pos.get("entry_time") else None,
                }
                for sym, pos in self.positions.items()
            },
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": self.equity_curve,
        }
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        self.logger.info(f"Paper trading state saved to {filepath}")

    def load_state(self, filepath: str) -> bool:
        """Load paper trading state from file / 從檔案載入模擬交易狀態"""
        import json, os
        from pathlib import Path
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            self.balance = state.get("balance", self.initial_balance)
            self.initial_balance = state.get("initial_balance", self.initial_balance)

            # Restore positions
            positions_data = state.get("positions", {})
            for sym, pos_data in positions_data.items():
                side = TradeSide(pos_data["side"])
                entry_time = datetime.fromisoformat(pos_data["entry_time"]) if pos_data.get("entry_time") else datetime.now()
                self.positions[sym] = {
                    "side": side,
                    "quantity": pos_data["quantity"],
                    "entry_price": pos_data["entry_price"],
                    "entry_time": entry_time,
                }

            # Restore trades / 恢復交易記錄
            trades_data = state.get("trades", [])
            self.trades = []
            for t_data in trades_data:
                try:
                    trade = SimulatedTrade(
                        trade_id=t_data.get("trade_id", ""),
                        symbol=t_data.get("symbol", ""),
                        side=TradeSide(t_data.get("side", "buy")),
                        quantity=t_data.get("quantity", 0),
                        entry_price=t_data.get("entry_price", 0),
                        exit_price=t_data.get("exit_price"),
                        entry_time=datetime.fromisoformat(t_data["entry_time"]) if t_data.get("entry_time") else datetime.now(),
                        exit_time=datetime.fromisoformat(t_data["exit_time"]) if t_data.get("exit_time") else None,
                        slippage=t_data.get("slippage", 0),
                        commission=t_data.get("commission", 0),
                        realized_pnl=t_data.get("realized_pnl", 0),
                        strategy_id=t_data.get("strategy_id"),
                    )
                    self.trades.append(trade)
                except Exception as e:
                    self.logger.warning(f"Failed to restore trade: {e}")

            # Restore equity curve / 恢復資金曲線
            self.equity_curve = state.get("equity_curve", [])

            self.logger.info(
                f"Paper trading state loaded from {filepath}: balance=${self.balance:,.2f}, "
                f"positions={len(self.positions)}, trades={len(self.trades)}"
            )
            return True
        except Exception as e:
            self.logger.warning(f"Failed to load paper trading state: {e}")
            return False

    def reset(self):
        """Reset paper trading account."""
        self.balance = self.initial_balance
        self.positions.clear()
        self.trades.clear()
        self.equity_curve.clear()
        self.logger.info("Paper trading reset")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    paper = PaperTrading(initial_balance=10000)

    # Simulate trades
    paper.enter_position("BTCUSDT", TradeSide.BUY, 0.1, 45000)
    paper.exit_position("BTCUSDT", 46000)

    paper.enter_position("ETHUSDT", TradeSide.BUY, 1.0, 3200)
    paper.exit_position("ETHUSDT", 3100)

    print("Paper Trading Demo")
    print("=" * 50)
    print(f"Performance: {paper.get_performance()}")
    print(f"\nTrades:")
    for t in paper.trades:
        print(f"  {t.side.value.upper()} {t.quantity} {t.symbol}: PnL=${t.realized_pnl:.2f}")
