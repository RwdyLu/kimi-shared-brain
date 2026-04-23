"""
OCO Orders (One-Cancels-the-Other)
Automated stop-loss and take-profit order management.
"""

import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import ccxt


class OCOStatus(Enum):
    """OCO order lifecycle status."""

    PENDING = "pending"  # OCO not yet placed
    ACTIVE = "active"  # Both orders active
    STOP_TRIGGERED = "stop_triggered"  # Stop loss filled
    PROFIT_TRIGGERED = "profit_triggered"  # Take profit filled
    CANCELED = "canceled"  # Manually canceled
    EXPIRED = "expired"  # Time expired
    ERROR = "error"  # Error state


@dataclass
class OCOOrder:
    """OCO order pair configuration."""

    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    stop_loss_limit: Optional[float] = None  # Limit price for stop
    take_profit_limit: Optional[float] = None  # Limit price for TP
    time_in_force: str = "GTC"  # Good Till Cancel

    def validate(self) -> Tuple[bool, str]:
        """Validate OCO configuration."""
        if self.stop_loss_price <= 0 or self.take_profit_price <= 0:
            return False, "Prices must be positive"

        if self.quantity <= 0:
            return False, "Quantity must be positive"

        if self.side == "buy":
            # For buy OCO: stop < entry < take_profit (for short exit)
            if self.stop_loss_price >= self.entry_price:
                return False, "Stop loss must be below entry for buy"
            if self.take_profit_price <= self.entry_price:
                return False, "Take profit must be above entry for buy"
        else:  # sell
            # For sell OCO: stop > entry > take_profit (for long exit)
            if self.stop_loss_price <= self.entry_price:
                return False, "Stop loss must be above entry for sell"
            if self.take_profit_price >= self.entry_price:
                return False, "Take profit must be below entry for sell"

        return True, "Valid"


@dataclass
class OCOResult:
    """Result of OCO order execution."""

    success: bool
    oco_id: str
    status: OCOStatus
    stop_order_id: Optional[str]
    profit_order_id: Optional[str]
    filled_order: Optional[str]  # Which order filled ('stop' or 'profit')
    filled_price: float
    filled_quantity: float
    pnl: float
    message: str
    execution_time: float


class OCOOrderManager:
    """
    Manages OCO (One-Cancels-the-Other) orders.
    Places stop-loss and take-profit as a pair.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True):
        self.logger = logging.getLogger(__name__)

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot", "adjustForTimeDifference": True},
        }

        if testnet:
            config["options"]["testnet"] = True

        self.exchange = ccxt.binance(config)

        # Active OCO orders tracking
        self.active_ocos: Dict[str, Dict] = {}

    def place_oco(self, oco: OCOOrder, timeout: float = 300.0) -> OCOResult:
        """
        Place OCO order pair.

        For Binance:
        - Uses createOrder for stop loss
        - Uses createOrder for take profit
        - Manages cancellation when one fills

        Args:
            oco: OCO order configuration
            timeout: Maximum time to wait for fill

        Returns:
            OCOResult with execution details
        """
        start_time = time.time()

        # Validate OCO
        valid, msg = oco.validate()
        if not valid:
            return OCOResult(
                success=False,
                oco_id="",
                status=OCOStatus.ERROR,
                stop_order_id=None,
                profit_order_id=None,
                filled_order=None,
                filled_price=0,
                filled_quantity=0,
                pnl=0,
                message=msg,
                execution_time=0,
            )

        try:
            self.logger.info(f"Placing OCO for {oco.symbol}: " f"SL={oco.stop_loss_price}, TP={oco.take_profit_price}")

            # Place stop loss order (STOP_LOSS_LIMIT)
            stop_order = self.exchange.create_order(
                symbol=oco.symbol,
                type="STOP_LOSS_LIMIT",
                side=oco.side.upper(),
                amount=oco.quantity,
                price=oco.stop_loss_limit or oco.stop_loss_price,
                params={"stopPrice": oco.stop_loss_price, "timeInForce": oco.time_in_force},
            )

            stop_id = stop_order["id"]
            self.logger.info(f"Stop loss order placed: {stop_id}")

            # Place take profit order (TAKE_PROFIT_LIMIT)
            profit_order = self.exchange.create_order(
                symbol=oco.symbol,
                type="TAKE_PROFIT_LIMIT",
                side=oco.side.upper(),
                amount=oco.quantity,
                price=oco.take_profit_limit or oco.take_profit_price,
                params={"stopPrice": oco.take_profit_price, "timeInForce": oco.time_in_force},
            )

            profit_id = profit_order["id"]
            self.logger.info(f"Take profit order placed: {profit_id}")

            # Track active OCO
            oco_id = f"OCO_{stop_id}_{profit_id}"
            self.active_ocos[oco_id] = {
                "symbol": oco.symbol,
                "stop_id": stop_id,
                "profit_id": profit_id,
                "entry_price": oco.entry_price,
                "quantity": oco.quantity,
                "side": oco.side,
                "start_time": start_time,
            }

            # Monitor for fills
            return self._monitor_oco(oco_id, timeout)

        except Exception as e:
            self.logger.error(f"OCO placement failed: {str(e)}")
            return OCOResult(
                success=False,
                oco_id="",
                status=OCOStatus.ERROR,
                stop_order_id=None,
                profit_order_id=None,
                filled_order=None,
                filled_price=0,
                filled_quantity=0,
                pnl=0,
                message=f"OCO failed: {str(e)}",
                execution_time=time.time() - start_time,
            )

    def _monitor_oco(self, oco_id: str, timeout: float) -> OCOResult:
        """
        Monitor OCO orders until one fills or timeout.
        """
        oco_info = self.active_ocos.get(oco_id)
        if not oco_info:
            return OCOResult(
                success=False,
                oco_id=oco_id,
                status=OCOStatus.ERROR,
                stop_order_id=None,
                profit_order_id=None,
                filled_order=None,
                filled_price=0,
                filled_quantity=0,
                pnl=0,
                message="OCO not found",
                execution_time=0,
            )

        symbol = oco_info["symbol"]
        stop_id = oco_info["stop_id"]
        profit_id = oco_info["profit_id"]
        entry_price = oco_info["entry_price"]
        quantity = oco_info["quantity"]
        side = oco_info["side"]
        start_time = oco_info["start_time"]

        while True:
            elapsed = time.time() - start_time

            if elapsed > timeout:
                self.logger.warning(f"OCO {oco_id} timeout")
                self._cancel_oco(oco_id)
                return OCOResult(
                    success=False,
                    oco_id=oco_id,
                    status=OCOStatus.EXPIRED,
                    stop_order_id=stop_id,
                    profit_order_id=profit_id,
                    filled_order=None,
                    filled_price=0,
                    filled_quantity=0,
                    pnl=0,
                    message=f"Timeout after {elapsed:.1f}s",
                    execution_time=elapsed,
                )

            try:
                # Check stop loss order
                stop_order = self.exchange.fetch_order(stop_id, symbol)
                if stop_order["status"] == "closed":
                    filled = stop_order.get("filled", 0)
                    avg_price = stop_order.get("average", 0) or stop_order.get("price", 0)

                    # Cancel take profit
                    self.exchange.cancel_order(profit_id, symbol)

                    # Calculate PnL
                    pnl = self._calculate_pnl(side, entry_price, avg_price, filled)

                    self.logger.info(f"Stop loss triggered: {filled} @ {avg_price}, PnL: {pnl:.2f}")

                    del self.active_ocos[oco_id]

                    return OCOResult(
                        success=True,
                        oco_id=oco_id,
                        status=OCOStatus.STOP_TRIGGERED,
                        stop_order_id=stop_id,
                        profit_order_id=profit_id,
                        filled_order="stop",
                        filled_price=avg_price,
                        filled_quantity=filled,
                        pnl=pnl,
                        message="Stop loss triggered",
                        execution_time=elapsed,
                    )

                # Check take profit order
                profit_order = self.exchange.fetch_order(profit_id, symbol)
                if profit_order["status"] == "closed":
                    filled = profit_order.get("filled", 0)
                    avg_price = profit_order.get("average", 0) or profit_order.get("price", 0)

                    # Cancel stop loss
                    self.exchange.cancel_order(stop_id, symbol)

                    # Calculate PnL
                    pnl = self._calculate_pnl(side, entry_price, avg_price, filled)

                    self.logger.info(f"Take profit triggered: {filled} @ {avg_price}, PnL: {pnl:.2f}")

                    del self.active_ocos[oco_id]

                    return OCOResult(
                        success=True,
                        oco_id=oco_id,
                        status=OCOStatus.PROFIT_TRIGGERED,
                        stop_order_id=stop_id,
                        profit_order_id=profit_id,
                        filled_order="profit",
                        filled_price=avg_price,
                        filled_quantity=filled,
                        pnl=pnl,
                        message="Take profit triggered",
                        execution_time=elapsed,
                    )

            except Exception as e:
                self.logger.error(f"Monitor error: {str(e)}")

            time.sleep(2)  # Poll interval

    def _calculate_pnl(self, side: str, entry: float, exit: float, quantity: float) -> float:
        """Calculate PnL for the trade."""
        if side == "buy":
            return (exit - entry) * quantity
        else:  # sell
            return (entry - exit) * quantity

    def _cancel_oco(self, oco_id: str) -> bool:
        """Cancel both orders in OCO pair."""
        oco_info = self.active_ocos.get(oco_id)
        if not oco_info:
            return False

        try:
            self.exchange.cancel_order(oco_info["stop_id"], oco_info["symbol"])
            self.exchange.cancel_order(oco_info["profit_id"], oco_info["symbol"])
            del self.active_ocos[oco_id]
            return True
        except Exception as e:
            self.logger.error(f"Cancel failed: {str(e)}")
            return False

    def cancel_oco(self, oco_id: str) -> bool:
        """Public method to cancel OCO."""
        return self._cancel_oco(oco_id)

    def get_active_ocos(self) -> Dict[str, Dict]:
        """Get all active OCO orders."""
        return self.active_ocos.copy()

    def modify_oco(self, oco_id: str, new_stop: Optional[float] = None, new_profit: Optional[float] = None) -> bool:
        """
        Modify OCO order prices.
        Cancels and replaces with new prices.
        """
        oco_info = self.active_ocos.get(oco_id)
        if not oco_info:
            return False

        try:
            # Cancel existing
            self._cancel_oco(oco_id)

            # Place new OCO with updated prices
            new_oco = OCOOrder(
                symbol=oco_info["symbol"],
                side=oco_info["side"],
                quantity=oco_info["quantity"],
                entry_price=oco_info["entry_price"],
                stop_loss_price=new_stop or oco_info.get("stop_price"),
                take_profit_price=new_profit or oco_info.get("profit_price"),
            )

            result = self.place_oco(new_oco)
            return result.success

        except Exception as e:
            self.logger.error(f"Modify failed: {str(e)}")
            return False


# Convenience function
def place_oco_order(
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    testnet: bool = True,
    timeout: float = 300.0,
) -> OCOResult:
    """
    Quick OCO order placement.

    Usage:
        result = place_oco_order('BTC/USDT', 'sell', 0.001, 50000, 49000, 52000)
        if result.status == OCOStatus.PROFIT_TRIGGERED:
            print(f"Profit! PnL: {result.pnl:.2f}")
    """
    manager = OCOOrderManager(api_key, api_secret, testnet)
    oco = OCOOrder(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
    )
    return manager.place_oco(oco, timeout)


if __name__ == "__main__":
    # Example usage
    print("OCO Order Manager Example")
    print("=" * 50)

    oco = OCOOrder(
        symbol="BTC/USDT",
        side="sell",  # Long position exit
        quantity=0.001,
        entry_price=50000,
        stop_loss_price=49000,
        take_profit_price=52000,
    )

    valid, msg = oco.validate()
    print(f"Validation: {msg}")

    if valid:
        print(f"OCO Config:")
        print(f"  Entry: {oco.entry_price}")
        print(f"  Stop Loss: {oco.stop_loss_price}")
        print(f"  Take Profit: {oco.take_profit_price}")
        print(
            f"  Risk/Reward: 1:{abs(oco.take_profit_price - oco.entry_price) / abs(oco.entry_price - oco.stop_loss_price):.1f}"
        )
