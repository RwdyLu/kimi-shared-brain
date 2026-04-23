"""
Position Sizing Engine
Dynamic position sizing with risk-based calculations.
"""

import math
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class RiskModel(Enum):
    """Risk management models."""

    FIXED_RISK = "fixed_risk"  # Fixed % risk per trade
    KELLY = "kelly"  # Kelly criterion
    HALF_KELLY = "half_kelly"  # Conservative Kelly
    FIXED_FRACTIONAL = "fixed_fractional"  # Fixed fractional


@dataclass
class PositionSize:
    """Calculated position size result."""

    symbol: str
    side: str
    quantity: float
    notional_value: float
    risk_amount: float
    risk_percent: float
    leverage: float
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    max_position_size: float
    recommended_size: float
    confidence: float  # 0-1, how confident the sizing is


class PositionSizingEngine:
    """
    Dynamic position sizing engine.
    Calculates optimal position size based on risk parameters.
    """

    def __init__(
        self,
        account_balance: float = 10000.0,
        max_risk_per_trade: float = 0.02,  # 2% max risk
        max_position_pct: float = 0.10,  # 10% max position
        max_leverage: float = 5.0,
        risk_model: RiskModel = RiskModel.FIXED_RISK,
    ):
        """
        Initialize position sizing engine.

        Args:
            account_balance: Total account balance in USDT
            max_risk_per_trade: Maximum risk per trade (0.02 = 2%)
            max_position_pct: Maximum position size as % of account
            max_leverage: Maximum allowed leverage
            risk_model: Risk calculation model
        """
        self.logger = logging.getLogger(__name__)

        self.account_balance = account_balance
        self.max_risk_per_trade = max_risk_per_trade
        self.max_position_pct = max_position_pct
        self.max_leverage = max_leverage
        self.risk_model = risk_model

        # Performance tracking for Kelly criterion
        self.win_rate = 0.5
        self.avg_win = 0.0
        self.avg_loss = 0.0

        self.logger.info(
            f"PositionSizingEngine initialized: "
            f"balance={account_balance}, max_risk={max_risk_per_trade}, "
            f"model={risk_model.value}"
        )

    def calculate_position_size(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        confidence: float = 0.5,
        volatility: Optional[float] = None,
    ) -> PositionSize:
        """
        Calculate optimal position size for a trade.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            entry_price: Planned entry price
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            confidence: Signal confidence (0-1)
            volatility: Current volatility (optional)

        Returns:
            PositionSize with calculated values
        """
        # Calculate risk per trade
        risk_amount = self.account_balance * self.max_risk_per_trade * confidence

        # Calculate position size based on risk model
        if self.risk_model == RiskModel.KELLY:
            size = self._kelly_sizing(entry_price, stop_loss, take_profit)
        elif self.risk_model == RiskModel.HALF_KELLY:
            size = self._kelly_sizing(entry_price, stop_loss, take_profit) * 0.5
        elif self.risk_model == RiskModel.FIXED_FRACTIONAL:
            size = self._fixed_fractional_sizing(entry_price)
        else:  # FIXED_RISK
            size = self._fixed_risk_sizing(entry_price, stop_loss, risk_amount)

        # Apply limits
        max_position_value = self.account_balance * self.max_position_pct
        max_by_leverage = (self.account_balance * self.max_leverage) / entry_price

        # Adjust for volatility if provided
        if volatility:
            size = self._adjust_for_volatility(size, volatility)

        # Final position size
        recommended_size = min(size, max_position_value / entry_price, max_by_leverage)
        recommended_size = max(0, recommended_size)  # Ensure non-negative

        # Calculate derived values
        notional_value = recommended_size * entry_price
        risk_percent = risk_amount / self.account_balance if self.account_balance > 0 else 0
        leverage = notional_value / self.account_balance if self.account_balance > 0 else 0

        self.logger.info(
            f"Position size for {symbol}: {recommended_size:.6f} "
            f"(notional: ${notional_value:.2f}, risk: {risk_percent:.2%})"
        )

        return PositionSize(
            symbol=symbol,
            side=side,
            quantity=recommended_size,
            notional_value=notional_value,
            risk_amount=risk_amount,
            risk_percent=risk_percent,
            leverage=leverage,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            max_position_size=max_position_value / entry_price,
            recommended_size=recommended_size,
            confidence=confidence,
        )

    def _fixed_risk_sizing(self, entry_price: float, stop_loss: Optional[float], risk_amount: float) -> float:
        """
        Fixed risk sizing: risk fixed amount per trade.
        Position size = risk_amount / (entry - stop_loss)
        """
        if stop_loss and entry_price != stop_loss:
            risk_per_unit = abs(entry_price - stop_loss)
            return risk_amount / risk_per_unit
        else:
            # No stop loss, use fixed fraction
            return (self.account_balance * self.max_risk_per_trade) / entry_price

    def _kelly_sizing(self, entry_price: float, stop_loss: Optional[float], take_profit: Optional[float]) -> float:
        """
        Kelly criterion sizing.
        f* = (p*b - q) / b
        where p = win rate, q = loss rate, b = avg_win/avg_loss
        """
        if self.avg_loss == 0 or self.win_rate <= 0:
            return self._fixed_risk_sizing(entry_price, stop_loss, self.account_balance * self.max_risk_per_trade)

        b = self.avg_win / self.avg_loss  # Average win/loss ratio
        q = 1 - self.win_rate

        kelly_fraction = (self.win_rate * b - q) / b
        kelly_fraction = max(0, min(kelly_fraction, 1))  # Clamp to [0, 1]

        # Use a fraction of Kelly for safety
        safe_fraction = kelly_fraction * 0.5  # Half Kelly

        return (self.account_balance * safe_fraction) / entry_price

    def _fixed_fractional_sizing(self, entry_price: float) -> float:
        """
        Fixed fractional sizing: fixed % of account per trade.
        """
        return (self.account_balance * self.max_risk_per_trade) / entry_price

    def _adjust_for_volatility(self, size: float, volatility: float) -> float:
        """
        Adjust position size based on volatility.
        Higher volatility = smaller position.
        """
        # Volatility adjustment factor (0.5 to 2.0)
        vol_factor = 1.0 / (1.0 + volatility)
        return size * vol_factor

    def update_performance(self, win: bool, profit_loss: float):
        """
        Update performance metrics for Kelly criterion.

        Args:
            win: True if trade was profitable
            profit_loss: Profit/loss amount
        """
        if win:
            self.avg_win = (self.avg_win * 9 + profit_loss) / 10  # EMA
            self.win_rate = (self.win_rate * 9 + 1) / 10
        else:
            self.avg_loss = (self.avg_loss * 9 + abs(profit_loss)) / 10  # EMA
            self.win_rate = (self.win_rate * 9 + 0) / 10

        self.logger.info(
            f"Performance updated: win_rate={self.win_rate:.2%}, "
            f"avg_win={self.avg_win:.2f}, avg_loss={self.avg_loss:.2f}"
        )

    def get_account_summary(self) -> Dict:
        """Get current account summary."""
        return {
            "account_balance": self.account_balance,
            "max_risk_per_trade": self.max_risk_per_trade,
            "max_position_pct": self.max_position_pct,
            "max_leverage": self.max_leverage,
            "risk_model": self.risk_model.value,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "kelly_fraction": self._calculate_kelly_fraction(),
        }

    def _calculate_kelly_fraction(self) -> float:
        """Calculate current Kelly fraction."""
        if self.avg_loss == 0 or self.win_rate <= 0:
            return 0
        b = self.avg_win / self.avg_loss
        q = 1 - self.win_rate
        kelly = (self.win_rate * b - q) / b
        return max(0, min(kelly, 1))


# Convenience function
def calculate_position(
    symbol: str,
    side: str,
    entry_price: float,
    account_balance: float = 10000.0,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    confidence: float = 0.5,
    risk_model: RiskModel = RiskModel.FIXED_RISK,
) -> PositionSize:
    """
    Quick position size calculation.

    Usage:
        pos = calculate_position('BTC/USDT', 'buy', 50000, stop_loss=49000)
        print(f"Size: {pos.quantity}, Risk: {pos.risk_percent:.2%}")
    """
    engine = PositionSizingEngine(account_balance=account_balance, risk_model=risk_model)
    return engine.calculate_position_size(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence=confidence,
    )


if __name__ == "__main__":
    # Example usage
    pos = calculate_position(
        symbol="BTC/USDT",
        side="buy",
        entry_price=50000,
        account_balance=10000,
        stop_loss=49000,
        take_profit=52000,
        confidence=0.7,
    )

    print(f"Symbol: {pos.symbol}")
    print(f"Side: {pos.side}")
    print(f"Quantity: {pos.quantity:.6f}")
    print(f"Notional Value: ${pos.notional_value:.2f}")
    print(f"Risk Amount: ${pos.risk_amount:.2f}")
    print(f"Risk %: {pos.risk_percent:.2%}")
    print(f"Leverage: {pos.leverage:.2f}x")
    print(f"Confidence: {pos.confidence:.0%}")
