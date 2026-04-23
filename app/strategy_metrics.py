"""
Real-Time Strategy Metrics Calculator
Computes Win Rate, Sharpe Ratio, Max Drawdown, and other performance metrics.
Updates automatically with each new trade.
"""

import json
import math
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque


@dataclass
class TradeRecord:
    """Individual trade record."""

    timestamp: datetime
    symbol: str
    side: str  # 'buy' or 'sell'
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float  # Profit/Loss in base currency
    pnl_percent: float  # PnL as percentage
    fees: float = 0.0
    duration_minutes: float = 0.0


@dataclass
class MetricsSnapshot:
    """Snapshot of strategy metrics at a point in time."""

    timestamp: datetime

    # Basic counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0

    # Returns
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    avg_pnl_percent: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    # Ratios
    win_rate: float = 0.0
    loss_rate: float = 0.0
    profit_factor: float = 0.0
    payoff_ratio: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    current_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Streaks
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0

    # Time metrics
    avg_trade_duration: float = 0.0
    total_duration: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "break_even_trades": self.break_even_trades,
            "win_rate": self.win_rate,
            "loss_rate": self.loss_rate,
            "profit_factor": self.profit_factor,
            "payoff_ratio": self.payoff_ratio,
            "total_pnl": self.total_pnl,
            "avg_pnl": self.avg_pnl,
            "avg_pnl_percent": self.avg_pnl_percent,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_percent": self.max_drawdown_percent,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "current_streak": self.current_streak,
            "avg_trade_duration": self.avg_trade_duration,
        }


class MetricsCalculator:
    """
    Real-time strategy metrics calculator.
    Efficiently updates metrics as new trades arrive.
    """

    def __init__(self, lookback_days: int = 30):
        self.logger = logging.getLogger(__name__)
        self.lookback_days = lookback_days
        self.trades: deque = deque(maxlen=10000)  # Ring buffer for recent trades

        # Running state
        self.current_equity: float = 0.0
        self.peak_equity: float = 0.0
        self.current_streak: int = 0
        self.streak_type: str = None  # 'win', 'loss', or None
        self.max_consecutive_wins: int = 0
        self.max_consecutive_losses: int = 0

        # Daily returns for Sharpe/Sortino
        self.daily_returns: deque = deque(maxlen=252)  # 1 year

        self.logger.info("MetricsCalculator initialized")

    def add_trade(self, trade: TradeRecord) -> MetricsSnapshot:
        """
        Add a new trade and recalculate metrics.

        Args:
            trade: New trade record

        Returns:
            Updated MetricsSnapshot
        """
        self.trades.append(trade)

        # Update equity curve
        self.current_equity += trade.pnl
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        # Update streaks
        if trade.pnl > 0:
            if self.streak_type == "win":
                self.current_streak += 1
            else:
                self.current_streak = 1
                self.streak_type = "win"
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.current_streak)
        elif trade.pnl < 0:
            if self.streak_type == "loss":
                self.current_streak += 1
            else:
                self.current_streak = 1
                self.streak_type = "loss"
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.current_streak)
        else:
            self.current_streak = 0
            self.streak_type = None

        # Calculate and return updated metrics
        return self.calculate_metrics()

    def calculate_metrics(self) -> MetricsSnapshot:
        """
        Calculate all metrics from current trades.

        Returns:
            MetricsSnapshot with all calculated metrics
        """
        if not self.trades:
            return MetricsSnapshot(timestamp=datetime.now())

        trades_list = list(self.trades)

        # Basic counts
        total_trades = len(trades_list)
        winning_trades = sum(1 for t in trades_list if t.pnl > 0)
        losing_trades = sum(1 for t in trades_list if t.pnl < 0)
        break_even_trades = total_trades - winning_trades - losing_trades

        # Returns
        pnls = [t.pnl for t in trades_list]
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        avg_pnl_percent = sum(t.pnl_percent for t in trades_list) / total_trades if total_trades > 0 else 0
        best_trade = max(pnls)
        worst_trade = min(pnls)

        # Win/Loss rates
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        loss_rate = losing_trades / total_trades if total_trades > 0 else 0

        # Profit factor (gross profit / gross loss)
        gross_profit = sum(t.pnl for t in trades_list if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades_list if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Payoff ratio (avg win / avg loss)
        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0

        # Drawdown calculation
        max_drawdown, max_dd_percent = self._calculate_drawdown(trades_list)
        current_drawdown = self.peak_equity - self.current_equity if self.peak_equity > 0 else 0

        # Sharpe ratio (annualized)
        sharpe = self._calculate_sharpe(pnls)

        # Sortino ratio (downside deviation)
        sortino = self._calculate_sortino(pnls)

        # Calmar ratio (return / max drawdown)
        calmar = (total_pnl / abs(max_drawdown)) if max_drawdown != 0 else 0

        # Duration metrics
        durations = [t.duration_minutes for t in trades_list]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return MetricsSnapshot(
            timestamp=datetime.now(),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            break_even_trades=break_even_trades,
            total_pnl=total_pnl,
            avg_pnl=avg_pnl,
            avg_pnl_percent=avg_pnl_percent,
            best_trade=best_trade,
            worst_trade=worst_trade,
            win_rate=win_rate,
            loss_rate=loss_rate,
            profit_factor=profit_factor,
            payoff_ratio=payoff_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_dd_percent,
            current_drawdown=current_drawdown,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_consecutive_wins=self.max_consecutive_wins,
            max_consecutive_losses=self.max_consecutive_losses,
            current_streak=self.current_streak,
            avg_trade_duration=avg_duration,
            total_duration=sum(durations),
        )

    def _calculate_drawdown(self, trades: List[TradeRecord]) -> Tuple[float, float]:
        """Calculate maximum drawdown."""
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        max_dd_percent = 0.0

        for trade in trades:
            equity += trade.pnl
            if equity > peak:
                peak = equity

            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown
                if peak > 0:
                    max_dd_percent = drawdown / peak

        return max_dd, max_dd_percent

    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) < 2:
            return 0.0

        excess_returns = [r - risk_free_rate for r in returns]
        avg_return = sum(excess_returns) / len(excess_returns)

        # Standard deviation
        variance = sum((r - avg_return) ** 2 for r in excess_returns) / (len(excess_returns) - 1)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return 0.0

        # Annualized (assuming daily returns)
        sharpe = (avg_return / std_dev) * math.sqrt(252)
        return sharpe

    def _calculate_sortino(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """Calculate Sortino ratio (downside deviation only)."""
        if len(returns) < 2:
            return 0.0

        excess_returns = [r - risk_free_rate for r in returns]
        avg_return = sum(excess_returns) / len(excess_returns)

        # Downside deviation (only negative returns)
        downside_returns = [r for r in excess_returns if r < 0]
        if not downside_returns:
            return float("inf") if avg_return > 0 else 0.0

        downside_variance = sum(r**2 for r in downside_returns) / len(downside_returns)
        downside_dev = math.sqrt(downside_variance)

        if downside_dev == 0:
            return 0.0

        sortino = (avg_return / downside_dev) * math.sqrt(252)
        return sortino

    def get_daily_summary(self, date: Optional[datetime] = None) -> Dict:
        """Get summary for a specific day."""
        if date is None:
            date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        next_day = date + timedelta(days=1)

        day_trades = [t for t in self.trades if date <= t.timestamp < next_day]

        if not day_trades:
            return {"date": date.isoformat(), "trades": 0}

        pnls = [t.pnl for t in day_trades]

        return {
            "date": date.isoformat(),
            "trades": len(day_trades),
            "winning_trades": sum(1 for p in pnls if p > 0),
            "losing_trades": sum(1 for p in pnls if p < 0),
            "total_pnl": sum(pnls),
            "avg_pnl": sum(pnls) / len(pnls),
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
        }

    def get_weekly_summary(self) -> Dict:
        """Get summary for current week."""
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        week_trades = [t for t in self.trades if t.timestamp >= week_start]

        if not week_trades:
            return {"week_start": week_start.isoformat(), "trades": 0}

        pnls = [t.pnl for t in week_trades]

        return {
            "week_start": week_start.isoformat(),
            "trades": len(week_trades),
            "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
            "total_pnl": sum(pnls),
            "avg_pnl": sum(pnls) / len(pnls),
        }

    def save_state(self, filepath: str = "state/metrics_state.json"):
        """Save metrics state to file."""
        state = {
            "current_equity": self.current_equity,
            "peak_equity": self.peak_equity,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "lookback_days": self.lookback_days,
            "saved_at": datetime.now().isoformat(),
        }

        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)

        self.logger.info(f"Metrics state saved to {filepath}")

    def load_state(self, filepath: str = "state/metrics_state.json"):
        """Load metrics state from file."""
        try:
            with open(filepath, "r") as f:
                state = json.load(f)

            self.current_equity = state.get("current_equity", 0.0)
            self.peak_equity = state.get("peak_equity", 0.0)
            self.max_consecutive_wins = state.get("max_consecutive_wins", 0)
            self.max_consecutive_losses = state.get("max_consecutive_losses", 0)

            self.logger.info(f"Metrics state loaded from {filepath}")
        except FileNotFoundError:
            self.logger.warning(f"State file not found: {filepath}")


class StrategyMetricsManager:
    """
    Manages metrics for multiple strategies.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.calculators: Dict[str, MetricsCalculator] = {}
        self.logger.info("StrategyMetricsManager initialized")

    def add_strategy(self, strategy_id: str) -> MetricsCalculator:
        """Add a new strategy tracker."""
        calc = MetricsCalculator()
        self.calculators[strategy_id] = calc
        self.logger.info(f"Added metrics tracking for strategy: {strategy_id}")
        return calc

    def record_trade(self, strategy_id: str, trade: TradeRecord) -> Optional[MetricsSnapshot]:
        """Record a trade for a strategy."""
        if strategy_id not in self.calculators:
            self.add_strategy(strategy_id)

        calc = self.calculators[strategy_id]
        metrics = calc.add_trade(trade)

        self.logger.info(
            f"Strategy {strategy_id}: Trade recorded | "
            f"Trades: {metrics.total_trades} | "
            f"WinRate: {metrics.win_rate:.2%} | "
            f"PnL: {metrics.total_pnl:.2f}"
        )

        return metrics

    def get_metrics(self, strategy_id: str) -> Optional[MetricsSnapshot]:
        """Get current metrics for a strategy."""
        if strategy_id not in self.calculators:
            return None
        return self.calculators[strategy_id].calculate_metrics()

    def get_all_metrics(self) -> Dict[str, MetricsSnapshot]:
        """Get metrics for all strategies."""
        return {sid: calc.calculate_metrics() for sid, calc in self.calculators.items()}

    def get_summary(self) -> Dict:
        """Get summary across all strategies."""
        all_metrics = self.get_all_metrics()

        if not all_metrics:
            return {"strategies": 0}

        total_trades = sum(m.total_trades for m in all_metrics.values())
        total_pnl = sum(m.total_pnl for m in all_metrics.values())
        avg_win_rate = sum(m.win_rate for m in all_metrics.values()) / len(all_metrics)

        return {
            "strategies": len(all_metrics),
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "avg_win_rate": avg_win_rate,
            "best_strategy": max(all_metrics.items(), key=lambda x: x[1].total_pnl)[0],
            "worst_strategy": min(all_metrics.items(), key=lambda x: x[1].total_pnl)[0],
        }


if __name__ == "__main__":
    # Example usage
    manager = StrategyMetricsManager()

    # Simulate trades
    import random

    random.seed(42)

    for i in range(50):
        trade = TradeRecord(
            timestamp=datetime.now() - timedelta(minutes=i * 30),
            symbol="BTC/USDT",
            side="buy" if i % 2 == 0 else "sell",
            entry_price=50000,
            exit_price=50000 + random.gauss(0, 500),
            quantity=0.001,
            pnl=random.gauss(50, 100),
            pnl_percent=random.gauss(0.1, 0.2),
            fees=0.5,
            duration_minutes=random.randint(10, 120),
        )

        manager.record_trade("BTC_4H_MA", trade)

    # Get metrics
    metrics = manager.get_metrics("BTC_4H_MA")

    print("Strategy Metrics Example")
    print("=" * 50)
    print(f"Total Trades: {metrics.total_trades}")
    print(f"Win Rate: {metrics.win_rate:.2%}")
    print(f"Profit Factor: {metrics.profit_factor:.2f}")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {metrics.max_drawdown:.2f}")
    print(f"Total PnL: {metrics.total_pnl:.2f}")
    print(f"Best Trade: {metrics.best_trade:.2f}")
    print(f"Worst Trade: {metrics.worst_trade:.2f}")
    print(f"Max Consecutive Wins: {metrics.max_consecutive_wins}")
    print(f"Max Consecutive Losses: {metrics.max_consecutive_losses}")
    print(f"Avg Trade Duration: {metrics.avg_trade_duration:.1f} minutes")
