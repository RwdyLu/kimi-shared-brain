"""
Pre-Trade Risk Checks for Trading Factory System
6 checks before order execution:
1. Account Balance Check
2. API Rate Limit Check
3. Liquidity Check (order book depth)
4. Slippage Estimation Check
5. Volume Check
6. Volatility Check
"""

import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import ccxt


class RiskLevel(Enum):
    """Risk level classification."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class RiskCheckResult:
    """Result of a single risk check."""

    check_name: str
    level: RiskLevel
    message: str
    details: Dict
    timestamp: float


class RiskChecker:
    """
    Pre-trade risk checker with 6 validation checks.
    All checks must pass before order execution.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = True):
        """
        Initialize risk checker.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet (default: True)
        """
        self.logger = logging.getLogger(__name__)

        # Initialize exchange
        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot", "adjustForTimeDifference": True},
        }

        if testnet:
            config["options"]["testnet"] = True

        self.exchange = ccxt.binance(config)

        # Risk thresholds (configurable)
        self.thresholds = {
            "min_balance_usdt": 10.0,  # Minimum balance
            "min_order_book_depth": 10000,  # Minimum order book depth (USDT)
            "max_slippage_pct": 0.5,  # Maximum slippage %
            "min_volume_24h": 1000000,  # Minimum 24h volume (USDT)
            "max_volatility_pct": 5.0,  # Maximum volatility %
        }

        # API rate limit tracking
        self.last_api_call = 0
        self.api_call_count = 0
        self.api_window_start = time.time()

    def check_all(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> Tuple[bool, List[RiskCheckResult]]:
        """
        Run all 6 risk checks.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Order amount
            price: Order price (optional for market orders)

        Returns:
            (all_passed: bool, results: List[RiskCheckResult])
        """
        results = []

        # Run all checks
        checks = [
            ("Balance Check", self.check_balance, (symbol, side, amount)),
            ("API Limit Check", self.check_api_limits, ()),
            ("Liquidity Check", self.check_liquidity, (symbol,)),
            ("Slippage Check", self.check_slippage, (symbol, side, amount)),
            ("Volume Check", self.check_volume, (symbol,)),
            ("Volatility Check", self.check_volatility, (symbol,)),
        ]

        for check_name, check_func, args in checks:
            try:
                result = check_func(*args)
                results.append(result)

                if result.level == RiskLevel.FAIL:
                    self.logger.error(f"Risk check failed: {check_name} - {result.message}")

            except Exception as e:
                self.logger.error(f"Risk check error: {check_name} - {str(e)}")
                results.append(
                    RiskCheckResult(
                        check_name=check_name,
                        level=RiskLevel.FAIL,
                        message=f"Check error: {str(e)}",
                        details={},
                        timestamp=time.time(),
                    )
                )

        # All checks must pass
        all_passed = all(r.level == RiskLevel.PASS for r in results)

        return all_passed, results

    def check_balance(self, symbol: str, side: str, amount: float) -> RiskCheckResult:
        """
        Check 1: Account Balance
        Ensure sufficient balance for the order.
        """
        try:
            balance = self.exchange.fetch_balance()

            if side == "buy":
                # Need USDT
                usdt_balance = balance.get("USDT", {}).get("free", 0)
                required = amount * (price or 0)  # price should be provided

                if usdt_balance >= required:
                    return RiskCheckResult(
                        check_name="Balance Check",
                        level=RiskLevel.PASS,
                        message=f"Sufficient balance: {usdt_balance:.2f} USDT",
                        details={"available": usdt_balance, "required": required, "currency": "USDT"},
                        timestamp=time.time(),
                    )
                else:
                    return RiskCheckResult(
                        check_name="Balance Check",
                        level=RiskLevel.FAIL,
                        message=f"Insufficient balance: {usdt_balance:.2f} < {required:.2f} USDT",
                        details={"available": usdt_balance, "required": required, "currency": "USDT"},
                        timestamp=time.time(),
                    )
            else:
                # Need base currency (e.g., BTC)
                base = symbol.split("/")[0]
                base_balance = balance.get(base, {}).get("free", 0)

                if base_balance >= amount:
                    return RiskCheckResult(
                        check_name="Balance Check",
                        level=RiskLevel.PASS,
                        message=f"Sufficient balance: {base_balance:.6f} {base}",
                        details={"available": base_balance, "required": amount, "currency": base},
                        timestamp=time.time(),
                    )
                else:
                    return RiskCheckResult(
                        check_name="Balance Check",
                        level=RiskLevel.FAIL,
                        message=f"Insufficient balance: {base_balance:.6f} < {amount:.6f} {base}",
                        details={"available": base_balance, "required": amount, "currency": base},
                        timestamp=time.time(),
                    )

        except Exception as e:
            return RiskCheckResult(
                check_name="Balance Check",
                level=RiskLevel.FAIL,
                message=f"Balance check failed: {str(e)}",
                details={"error": str(e)},
                timestamp=time.time(),
            )

    def check_api_limits(self) -> RiskCheckResult:
        """
        Check 2: API Rate Limits
        Ensure we haven't exceeded rate limits.
        """
        current_time = time.time()

        # Reset counter if window passed (1 minute window)
        if current_time - self.api_window_start > 60:
            self.api_call_count = 0
            self.api_window_start = current_time

        # Binance spot: 1200 request weight per minute
        max_weight = 1200
        current_weight = self.api_call_count * 10  # Approximate weight per call

        if current_weight < max_weight * 0.8:  # 80% threshold
            return RiskCheckResult(
                check_name="API Limit Check",
                level=RiskLevel.PASS,
                message=f"API usage: {current_weight}/{max_weight} weight",
                details={
                    "current_weight": current_weight,
                    "max_weight": max_weight,
                    "usage_pct": (current_weight / max_weight) * 100,
                },
                timestamp=time.time(),
            )
        elif current_weight < max_weight:
            return RiskCheckResult(
                check_name="API Limit Check",
                level=RiskLevel.WARNING,
                message=f"API usage high: {current_weight}/{max_weight} weight",
                details={
                    "current_weight": current_weight,
                    "max_weight": max_weight,
                    "usage_pct": (current_weight / max_weight) * 100,
                },
                timestamp=time.time(),
            )
        else:
            return RiskCheckResult(
                check_name="API Limit Check",
                level=RiskLevel.FAIL,
                message=f"API limit exceeded: {current_weight}/{max_weight} weight",
                details={
                    "current_weight": current_weight,
                    "max_weight": max_weight,
                    "usage_pct": (current_weight / max_weight) * 100,
                },
                timestamp=time.time(),
            )

    def check_liquidity(self, symbol: str) -> RiskCheckResult:
        """
        Check 3: Liquidity (Order Book Depth)
        Ensure sufficient market depth.
        """
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit=20)

            bids = order_book.get("bids", [])
            asks = order_book.get("asks", [])

            # Calculate depth within 1% of mid price
            if bids and asks:
                mid_price = (bids[0][0] + asks[0][0]) / 2
                depth_1pct = mid_price * 0.01

                bid_depth = sum(b[1] * b[0] for b in bids if b[0] >= mid_price - depth_1pct)
                ask_depth = sum(a[1] * a[0] for a in asks if a[0] <= mid_price + depth_1pct)

                min_depth = min(bid_depth, ask_depth)

                if min_depth >= self.thresholds["min_order_book_depth"]:
                    return RiskCheckResult(
                        check_name="Liquidity Check",
                        level=RiskLevel.PASS,
                        message=f"Sufficient liquidity: {min_depth:.2f} USDT depth",
                        details={
                            "bid_depth": bid_depth,
                            "ask_depth": ask_depth,
                            "min_depth": min_depth,
                            "threshold": self.thresholds["min_order_book_depth"],
                        },
                        timestamp=time.time(),
                    )
                else:
                    return RiskCheckResult(
                        check_name="Liquidity Check",
                        level=RiskLevel.FAIL,
                        message=f"Insufficient liquidity: {min_depth:.2f} < {self.thresholds['min_order_book_depth']} USDT",
                        details={
                            "bid_depth": bid_depth,
                            "ask_depth": ask_depth,
                            "min_depth": min_depth,
                            "threshold": self.thresholds["min_order_book_depth"],
                        },
                        timestamp=time.time(),
                    )
            else:
                return RiskCheckResult(
                    check_name="Liquidity Check",
                    level=RiskLevel.FAIL,
                    message="Empty order book",
                    details={"bids_count": len(bids), "asks_count": len(asks)},
                    timestamp=time.time(),
                )

        except Exception as e:
            return RiskCheckResult(
                check_name="Liquidity Check",
                level=RiskLevel.FAIL,
                message=f"Liquidity check failed: {str(e)}",
                details={"error": str(e)},
                timestamp=time.time(),
            )

    def check_slippage(self, symbol: str, side: str, amount: float) -> RiskCheckResult:
        """
        Check 4: Slippage Estimation
        Estimate slippage for the order.
        """
        try:
            order_book = self.exchange.fetch_order_book(symbol, limit=20)

            if side == "buy":
                orders = order_book.get("asks", [])
            else:
                orders = order_book.get("bids", [])

            if not orders:
                return RiskCheckResult(
                    check_name="Slippage Check",
                    level=RiskLevel.FAIL,
                    message="No orders available",
                    details={},
                    timestamp=time.time(),
                )

            # Calculate average fill price
            remaining = amount
            total_cost = 0

            for price, qty in orders:
                if remaining <= 0:
                    break
                fill = min(remaining, qty)
                total_cost += fill * price
                remaining -= fill

            if remaining > 0:
                return RiskCheckResult(
                    check_name="Slippage Check",
                    level=RiskLevel.FAIL,
                    message=f"Insufficient depth for {amount} (remaining: {remaining})",
                    details={"requested": amount, "fillable": amount - remaining, "remaining": remaining},
                    timestamp=time.time(),
                )

            avg_price = total_cost / amount
            best_price = orders[0][0]
            slippage = abs(avg_price - best_price) / best_price * 100

            if slippage <= self.thresholds["max_slippage_pct"]:
                return RiskCheckResult(
                    check_name="Slippage Check",
                    level=RiskLevel.PASS,
                    message=f"Slippage acceptable: {slippage:.3f}%",
                    details={
                        "avg_price": avg_price,
                        "best_price": best_price,
                        "slippage_pct": slippage,
                        "threshold": self.thresholds["max_slippage_pct"],
                    },
                    timestamp=time.time(),
                )
            else:
                return RiskCheckResult(
                    check_name="Slippage Check",
                    level=RiskLevel.FAIL,
                    message=f"Slippage too high: {slippage:.3f}% > {self.thresholds['max_slippage_pct']}%",
                    details={
                        "avg_price": avg_price,
                        "best_price": best_price,
                        "slippage_pct": slippage,
                        "threshold": self.thresholds["max_slippage_pct"],
                    },
                    timestamp=time.time(),
                )

        except Exception as e:
            return RiskCheckResult(
                check_name="Slippage Check",
                level=RiskLevel.FAIL,
                message=f"Slippage check failed: {str(e)}",
                details={"error": str(e)},
                timestamp=time.time(),
            )

    def check_volume(self, symbol: str) -> RiskCheckResult:
        """
        Check 5: 24h Volume
        Ensure sufficient trading volume.
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            volume_24h = ticker.get("quoteVolume", 0)

            if volume_24h >= self.thresholds["min_volume_24h"]:
                return RiskCheckResult(
                    check_name="Volume Check",
                    level=RiskLevel.PASS,
                    message=f"Volume sufficient: {volume_24h:.2f} USDT/24h",
                    details={"volume_24h": volume_24h, "threshold": self.thresholds["min_volume_24h"]},
                    timestamp=time.time(),
                )
            else:
                return RiskCheckResult(
                    check_name="Volume Check",
                    level=RiskLevel.FAIL,
                    message=f"Volume too low: {volume_24h:.2f} < {self.thresholds['min_volume_24h']} USDT/24h",
                    details={"volume_24h": volume_24h, "threshold": self.thresholds["min_volume_24h"]},
                    timestamp=time.time(),
                )

        except Exception as e:
            return RiskCheckResult(
                check_name="Volume Check",
                level=RiskLevel.FAIL,
                message=f"Volume check failed: {str(e)}",
                details={"error": str(e)},
                timestamp=time.time(),
            )

    def check_volatility(self, symbol: str) -> RiskCheckResult:
        """
        Check 6: Volatility
        Check recent price volatility.
        """
        try:
            # Fetch recent OHLCV data
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe="1h", limit=24)

            if len(ohlcv) < 2:
                return RiskCheckResult(
                    check_name="Volatility Check",
                    level=RiskLevel.FAIL,
                    message="Insufficient OHLCV data",
                    details={"bars": len(ohlcv)},
                    timestamp=time.time(),
                )

            # Calculate price range
            highs = [bar[2] for bar in ohlcv]
            lows = [bar[3] for bar in ohlcv]

            max_high = max(highs)
            min_low = min(lows)

            volatility = ((max_high - min_low) / min_low) * 100

            if volatility <= self.thresholds["max_volatility_pct"]:
                return RiskCheckResult(
                    check_name="Volatility Check",
                    level=RiskLevel.PASS,
                    message=f"Volatility acceptable: {volatility:.2f}%",
                    details={
                        "volatility_pct": volatility,
                        "max_high": max_high,
                        "min_low": min_low,
                        "threshold": self.thresholds["max_volatility_pct"],
                    },
                    timestamp=time.time(),
                )
            else:
                return RiskCheckResult(
                    check_name="Volatility Check",
                    level=RiskLevel.FAIL,
                    message=f"Volatility too high: {volatility:.2f}% > {self.thresholds['max_volatility_pct']}%",
                    details={
                        "volatility_pct": volatility,
                        "max_high": max_high,
                        "min_low": min_low,
                        "threshold": self.thresholds["max_volatility_pct"],
                    },
                    timestamp=time.time(),
                )

        except Exception as e:
            return RiskCheckResult(
                check_name="Volatility Check",
                level=RiskLevel.FAIL,
                message=f"Volatility check failed: {str(e)}",
                details={"error": str(e)},
                timestamp=time.time(),
            )


# Convenience function for quick check
def pre_trade_check(
    symbol: str,
    side: str,
    amount: float,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    testnet: bool = True,
) -> Tuple[bool, List[RiskCheckResult]]:
    """
    Quick pre-trade risk check.

    Returns:
        (all_passed: bool, results: List[RiskCheckResult])
    """
    checker = RiskChecker(api_key, api_secret, testnet)
    return checker.check_all(symbol, side, amount)


# Example usage
if __name__ == "__main__":
    # Example: Check before buying 0.001 BTC
    passed, results = pre_trade_check(symbol="BTC/USDT", side="buy", amount=0.001, testnet=True)

    print(f"All checks passed: {passed}")
    for result in results:
        print(f"  {result.check_name}: {result.level.value} - {result.message}")
