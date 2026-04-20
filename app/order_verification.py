"""
Order Verification and Binance API Confirmation
Handles order polling, timeout control, and fee calculation.
"""
import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import ccxt


class OrderStatus(Enum):
    """Order lifecycle status."""
    PENDING = "pending"           # Order submitted, waiting for exchange
    OPEN = "open"                 # Order open on exchange
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"             # Fully filled
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    TIMEOUT = "timeout"           # Custom timeout status


@dataclass
class OrderResult:
    """Result of order verification."""
    success: bool
    order_id: str
    status: OrderStatus
    filled_amount: float
    remaining: float
    avg_price: float
    fee: float
    fee_currency: str
    total_cost: float
    message: str
    verification_time: float


class OrderVerifier:
    """
    Verifies order execution on Binance.
    Polls order status with timeout control.
    """
    
    def __init__(self, api_key: Optional[str] = None,
                 api_secret: Optional[str] = None,
                 testnet: bool = True):
        self.logger = logging.getLogger(__name__)
        
        config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True
            }
        }
        
        if testnet:
            config['options']['testnet'] = True
        
        self.exchange = ccxt.binance(config)
        
        # Timeout configuration (seconds)
        self.timeouts = {
            'order_submit': 10,       # Time to submit order
            'first_fill': 60,         # Time to get first fill
            'full_fill': 300,         # Time for complete fill
            'poll_interval': 2,       # Poll interval
        }
    
    def place_and_verify(self, symbol: str, side: str, order_type: str,
                        amount: float, price: Optional[float] = None,
                        timeout: Optional[int] = None) -> OrderResult:
        """
        Place order and verify execution.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            amount: Order amount
            price: Limit price (optional for market orders)
            timeout: Custom timeout in seconds
            
        Returns:
            OrderResult with verification details
        """
        start_time = time.time()
        timeout = timeout or self.timeouts['full_fill']
        
        try:
            # 1. Place order
            self.logger.info(f"Placing {side} {order_type} order: {amount} {symbol}")
            
            order_params = {
                'symbol': symbol,
                'type': order_type.upper(),
                'side': side.upper(),
                'amount': amount,
            }
            
            if price and order_type.lower() == 'limit':
                order_params['price'] = price
            
            order = self.exchange.create_order(**order_params)
            order_id = order['id']
            
            self.logger.info(f"Order placed: {order_id}")
            
            # 2. Poll for fills
            result = self._poll_order(order_id, symbol, start_time, timeout)
            result.order_id = order_id
            result.verification_time = time.time() - start_time
            
            return result
            
        except Exception as e:
            self.logger.error(f"Order placement failed: {str(e)}")
            return OrderResult(
                success=False,
                order_id="",
                status=OrderStatus.REJECTED,
                filled_amount=0,
                remaining=amount,
                avg_price=0,
                fee=0,
                fee_currency="",
                total_cost=0,
                message=f"Order failed: {str(e)}",
                verification_time=time.time() - start_time
            )
    
    def _poll_order(self, order_id: str, symbol: str,
                   start_time: float, timeout: int) -> OrderResult:
        """
        Poll order status until filled or timeout.
        """
        last_status = OrderStatus.PENDING
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                self.logger.warning(f"Order {order_id} timeout after {elapsed:.1f}s")
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    status=OrderStatus.TIMEOUT,
                    filled_amount=0,
                    remaining=0,
                    avg_price=0,
                    fee=0,
                    fee_currency="",
                    total_cost=0,
                    message=f"Timeout after {elapsed:.1f}s",
                    verification_time=elapsed
                )
            
            try:
                # Fetch order status
                order = self.exchange.fetch_order(order_id, symbol)
                
                status = order.get('status', '')
                filled = order.get('filled', 0)
                remaining = order.get('remaining', 0)
                avg_price = order.get('average', 0) or order.get('price', 0)
                
                # Map exchange status to our status
                if status == 'closed':
                    if remaining == 0:
                        current_status = OrderStatus.FILLED
                    else:
                        current_status = OrderStatus.CANCELED
                elif status == 'open':
                    if filled > 0:
                        current_status = OrderStatus.PARTIALLY_FILLED
                    else:
                        current_status = OrderStatus.OPEN
                elif status == 'canceled':
                    current_status = OrderStatus.CANCELED
                else:
                    current_status = OrderStatus.PENDING
                
                # Log status changes
                if current_status != last_status:
                    self.logger.info(
                        f"Order {order_id} status: {last_status.value} → "
                        f"{current_status.value} (filled: {filled})"
                    )
                    last_status = current_status
                
                # Check if complete
                if current_status == OrderStatus.FILLED:
                    # Calculate fees
                    fee_info = order.get('fee', {})
                    fee = fee_info.get('cost', 0)
                    fee_currency = fee_info.get('currency', '')
                    
                    total_cost = filled * avg_price
                    
                    self.logger.info(
                        f"Order {order_id} filled: {filled} @ {avg_price} "
                        f"(fee: {fee} {fee_currency})"
                    )
                    
                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        status=OrderStatus.FILLED,
                        filled_amount=filled,
                        remaining=remaining,
                        avg_price=avg_price,
                        fee=fee,
                        fee_currency=fee_currency,
                        total_cost=total_cost,
                        message="Order fully filled",
                        verification_time=elapsed
                    )
                
                elif current_status in [OrderStatus.CANCELED, OrderStatus.REJECTED]:
                    return OrderResult(
                        success=False,
                        order_id=order_id,
                        status=current_status,
                        filled_amount=filled,
                        remaining=remaining,
                        avg_price=avg_price,
                        fee=0,
                        fee_currency="",
                        total_cost=0,
                        message=f"Order {current_status.value}",
                        verification_time=elapsed
                    )
                
            except Exception as e:
                self.logger.error(f"Poll error: {str(e)}")
            
            # Wait before next poll
            time.sleep(self.timeouts['poll_interval'])
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        try:
            self.exchange.cancel_order(order_id, symbol)
            self.logger.info(f"Order {order_id} canceled")
            return True
        except Exception as e:
            self.logger.error(f"Cancel failed: {str(e)}")
            return False
    
    def get_order_fees(self, order_id: str, symbol: str) -> Dict:
        """Get detailed fee information for an order."""
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return {
                'fee': order.get('fee', {}),
                'fees': order.get('fees', []),
                'total_cost': order.get('cost', 0),
                'filled': order.get('filled', 0),
            }
        except Exception as e:
            self.logger.error(f"Fee fetch failed: {str(e)}")
            return {}


# Convenience function
def verify_order(symbol: str, side: str, order_type: str,
                amount: float, price: Optional[float] = None,
                api_key: Optional[str] = None,
                api_secret: Optional[str] = None,
                testnet: bool = True,
                timeout: Optional[int] = None) -> OrderResult:
    """
    Quick order verification.
    
    Usage:
        result = verify_order('BTC/USDT', 'buy', 'market', 0.001)
        if result.success:
            print(f"Filled: {result.filled_amount} @ {result.avg_price}")
    """
    verifier = OrderVerifier(api_key, api_secret, testnet)
    return verifier.place_and_verify(symbol, side, order_type, amount, price, timeout)


if __name__ == "__main__":
    # Example usage
    result = verify_order('BTC/USDT', 'buy', 'market', 0.001, testnet=True)
    print(f"Success: {result.success}")
    print(f"Status: {result.status.value}")
    print(f"Filled: {result.filled_amount}")
    print(f"Avg Price: {result.avg_price}")
    print(f"Fee: {result.fee} {result.fee_currency}")
