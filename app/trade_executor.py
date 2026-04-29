"""
Trade Executor / 交易執行器

Phase 2: Connects strategy signals to paper trading execution.
將策略訊號連接到模擬交易執行，從 ALERT-ONLY 升級到 PAPER-TRADING。

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-27
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

from app.paper_trading import PaperTrading, TradeSide
from signals.engine import SignalType, SignalLevel
from config.paths import STATE_DIR

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Result of a trade execution / 交易執行結果"""
    symbol: str
    side: str
    status: str  # "executed", "skipped", "blocked", "pending_human"
    trade_id: Optional[str] = None
    quantity: Optional[float] = None
    entry_price: Optional[float] = None
    reason: str = ""
    balance_after: Optional[float] = None


class TradeExecutor:
    """
    Trade executor that bridges strategy signals to paper trading.
    
    Integrates with:
    - MonitorRunner / StrategyExecutor (signal generation)
    - PaperTrading (simulated execution)
    
    Mode: PAPER-TRADING ONLY (no real exchange orders)
    """

    # Signal type → trade side mapping
    SIGNAL_TO_SIDE = {
        SignalType.TREND_LONG: TradeSide.BUY,
        SignalType.TREND_SHORT: TradeSide.SELL,
        SignalType.CYCLE: TradeSide.BUY,
        SignalType.BREAKOUT: TradeSide.BUY,
        SignalType.MOMENTUM: TradeSide.BUY,
        SignalType.MEAN_REVERSION: TradeSide.BUY,
        SignalType.REVERSAL_LONG: TradeSide.BUY,
        SignalType.BREAKOUT_LONG: TradeSide.BUY,
        # Exit signals
        SignalType.EXIT_LONG: TradeSide.SELL,   # Close long position
        SignalType.EXIT_SHORT: TradeSide.BUY,   # Close short position
    }

    # Entry vs exit signal classification
    ENTRY_SIGNALS = {
        SignalType.TREND_LONG, SignalType.TREND_SHORT, SignalType.CYCLE,
        SignalType.BREAKOUT, SignalType.MOMENTUM, SignalType.MEAN_REVERSION,
        SignalType.REVERSAL_LONG, SignalType.BREAKOUT_LONG,
    }
    EXIT_SIGNALS = {SignalType.EXIT_LONG, SignalType.EXIT_SHORT}

    def __init__(
        self,
        initial_balance: float = 10000.0,
        position_pct: float = 0.1,  # Use 10% of balance per trade
        max_total_exposure_pct: float = 0.5,  # Max 50% of balance in open positions
        enable_trading: bool = True,
        state_file: Optional[str] = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.enable_trading = enable_trading
        self.position_pct = position_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.state_file = state_file or str(STATE_DIR / "paper_trading_state.json")

        # Paper trading account
        self.paper = PaperTrading(
            initial_balance=initial_balance,
            slippage_pct=0.1,
            commission_pct=0.1,
        ) if enable_trading else None

        # Load previous state if available
        if self.paper and self.state_file:
            self.paper.load_state(self.state_file)

        # Track which symbols have open positions (simple single-position model)
        self.open_positions: Dict[str, Dict] = {}

        self.logger.info(
            f"TradeExecutor initialized: balance=${self.paper.balance if self.paper else 0:,.2f}, "
            f"position_pct={position_pct*100}%, max_exposure={max_total_exposure_pct*100}%, enabled={enable_trading}"
        )

    def execute_signals(
        self,
        confirmed_signals: List,
        current_prices: Dict[str, float],
    ) -> List[TradeResult]:
        """
        Execute trading for confirmed signals.
        
        Args:
            confirmed_signals: List of CONFIRMED Signal objects
            current_prices: Dict of symbol → current price
            
        Returns:
            List of TradeResult
        """
        results = []

        if not self.enable_trading or not self.paper:
            self.logger.info("Trading disabled, skipping execution")
            return results

        for signal in confirmed_signals:
            result = self._process_signal(signal, current_prices)
            if result:
                results.append(result)

        return results

    def _process_signal(self, signal, current_prices: Dict[str, float]) -> Optional[TradeResult]:
        """Process a single confirmed signal (entry or exit)."""
        symbol = signal.symbol
        signal_type = signal.signal_type

        # Map signal type to trade side
        side = self.SIGNAL_TO_SIDE.get(signal_type)
        if not side:
            self.logger.info(f"Signal type {signal_type.name} not mapped to trade side, skipping")
            return TradeResult(
                symbol=symbol,
                side="unknown",
                status="skipped",
                reason=f"Unmapped signal type: {signal_type.name}",
            )

        # Get current price
        price = current_prices.get(symbol)
        if not price or price <= 0:
            self.logger.warning(f"No valid price for {symbol}, skipping")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="No valid price",
            )

        # Handle EXIT signals
        if signal_type in self.EXIT_SIGNALS:
            return self._process_exit_signal(symbol, signal, price, side)

        # ENTRY signal handling below
        # Check if we already have an open position for this symbol
        if symbol in self.open_positions:
            self.logger.info(f"Already have open position for {symbol}, skipping new entry signal")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Position already open",
            )

        # Check total exposure limit
        open_exposure = sum(
            pos["entry_price"] * pos["quantity"] for pos in self.open_positions.values()
        )
        max_exposure = self.paper.balance * self.max_total_exposure_pct
        if open_exposure >= max_exposure:
            self.logger.info(
                f"Max total exposure reached ({open_exposure:.2f}/{max_exposure:.2f}), skipping {symbol}"
            )
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Max total exposure reached",
            )

        # Calculate position size
        position_value = self.paper.balance * self.position_pct
        if position_value < 1.0:
            self.logger.warning(f"Insufficient balance for trade: ${self.paper.balance:.2f}")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Insufficient balance",
            )

        quantity = position_value / price

        # Execute paper trade entry
        try:
            trade = self.paper.enter_position(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
            )

            # Track position
            self.open_positions[symbol] = {
                "side": side.value,
                "quantity": quantity,
                "entry_price": trade.entry_price,
                "trade_id": trade.trade_id,
                "entry_time": datetime.now().isoformat(),
            }

            self.logger.info(
                f"✅ PAPER TRADE ENTRY: {side.value.upper()} {quantity:.6f} {symbol} "
                f"@ ${trade.entry_price:,.2f} (balance: ${self.paper.balance:,.2f})"
            )

            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="executed",
                trade_id=trade.trade_id,
                quantity=quantity,
                entry_price=trade.entry_price,
                balance_after=self.paper.balance,
                reason=signal.reason,
            )

        except Exception as e:
            self.logger.error(f"Trade execution failed for {symbol}: {e}")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason=f"Execution error: {e}",
            )

    def _process_exit_signal(self, symbol: str, signal, price: float, side: TradeSide) -> Optional[TradeResult]:
        """Process an exit signal by closing the corresponding open position."""
        # Check if we have an open position
        if symbol not in self.open_positions:
            self.logger.info(f"No open position for {symbol}, skipping exit signal")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="No open position to exit",
            )

        position = self.open_positions[symbol]
        signal_type = signal.signal_type

        # Verify position direction matches exit signal
        # EXIT_LONG requires a long position, EXIT_SHORT requires a short position
        if signal_type == SignalType.EXIT_LONG and position["side"] != "buy":
            self.logger.info(f"Position for {symbol} is not long, skipping EXIT_LONG")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Position direction mismatch for EXIT_LONG",
            )

        if signal_type == SignalType.EXIT_SHORT and position["side"] != "sell":
            self.logger.info(f"Position for {symbol} is not short, skipping EXIT_SHORT")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Position direction mismatch for EXIT_SHORT",
            )

        # Execute paper trade exit
        try:
            trade = self.paper.exit_position(symbol=symbol, price=price)

            if trade:
                # Remove from tracking
                del self.open_positions[symbol]

                self.logger.info(
                    f"✅ PAPER TRADE EXIT: {symbol} @ ${price:,.2f} "
                    f"PnL: ${trade.realized_pnl:.2f} (balance: ${self.paper.balance:,.2f})"
                )

                return TradeResult(
                    symbol=symbol,
                    side=side.value,
                    status="exited",
                    trade_id=trade.trade_id,
                    quantity=trade.quantity,
                    entry_price=trade.entry_price,
                    balance_after=self.paper.balance,
                    reason=f"Exit signal: {signal.reason}",
                )
            else:
                return TradeResult(
                    symbol=symbol,
                    side=side.value,
                    status="skipped",
                    reason="Exit failed - no trade record",
                )

        except Exception as e:
            self.logger.error(f"Trade exit failed for {symbol}: {e}")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason=f"Exit execution error: {e}",
            )

    def check_exit_signals(self, symbol: str, current_price: float) -> Optional[TradeResult]:
        """
        Check if an open position should be exited.
        
        Simple exit logic: exit on opposite signal or if position has been held.
        This is a placeholder for more sophisticated exit rules (stop loss, take profit).
        """
        if symbol not in self.open_positions:
            return None

        position = self.open_positions[symbol]

        # For now, positions are held until explicitly exited
        # TODO: Implement stop-loss / take-profit exit rules
        return None

    def get_paper_performance(self) -> Optional[Dict]:
        """Get paper trading performance summary."""
        if not self.paper:
            return None

        perf = self.paper.get_performance()
        perf["open_positions"] = len(self.open_positions)
        perf["open_position_symbols"] = list(self.open_positions.keys())
        return perf

    def save_state(self) -> None:
        """Save paper trading state / 儲存模擬交易狀態"""
        if self.paper and self.state_file:
            self.paper.save_state(self.state_file)

    def reset(self):
        """Reset paper trading account and positions."""
        if self.paper:
            self.paper.reset()
        self.open_positions.clear()
        self.logger.info("TradeExecutor reset")
