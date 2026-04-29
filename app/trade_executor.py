"""
Trade Executor / 交易執行器

Phase 2: Connects strategy signals to paper trading execution.
將策略訊號連接到模擬交易執行，從 ALERT-ONLY 升級到 PAPER-TRADING。

Fix A: 出場機制完善
- 時間止損：持倉超過 8 小時自動平倉
- EXIT 訊號需連續 2 根 K 線確認才出場
- 以 paper.positions 為唯一 source of truth

Author: kimiclaw_bot
Version: 1.1.0
Date: 2026-04-29
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
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
    status: str  # "executed", "skipped", "blocked", "pending_exit", "exited", "time_stopped"
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
        # 13 unique strategy signal types
        SignalType.MA_CROSS_TREND: TradeSide.BUY,
        SignalType.MA_CROSS_TREND_SHORT: TradeSide.SELL,
        SignalType.CONTRARIAN_OVERHEATED: TradeSide.BUY,
        SignalType.CONTRARIAN_OVERSOLD: TradeSide.BUY,
        SignalType.HILBERT_CYCLE: TradeSide.BUY,
        SignalType.STOCHASTIC_BREAKOUT: TradeSide.BUY,
        SignalType.RSI_TREND: TradeSide.BUY,
        SignalType.BB_MEAN_REVERSION: TradeSide.BUY,
        SignalType.EMA_CROSS_FAST: TradeSide.BUY,
        SignalType.RSI_MID_BOUNCE: TradeSide.BUY,
        SignalType.VOLUME_SPIKE: TradeSide.BUY,
        SignalType.PRICE_CHANNEL_BREAK: TradeSide.BUY,
        SignalType.MOMENTUM_DIVERGENCE: TradeSide.BUY,
        # Exit signals
        SignalType.EXIT_LONG: TradeSide.SELL,   # Close long position
        SignalType.EXIT_SHORT: TradeSide.BUY,   # Close short position
    }

    # Entry vs exit signal classification
    ENTRY_SIGNALS = {
        SignalType.MA_CROSS_TREND, SignalType.MA_CROSS_TREND_SHORT,
        SignalType.CONTRARIAN_OVERHEATED, SignalType.CONTRARIAN_OVERSOLD,
        SignalType.HILBERT_CYCLE, SignalType.STOCHASTIC_BREAKOUT,
        SignalType.RSI_TREND, SignalType.BB_MEAN_REVERSION,
        SignalType.EMA_CROSS_FAST, SignalType.RSI_MID_BOUNCE,
        SignalType.VOLUME_SPIKE, SignalType.PRICE_CHANNEL_BREAK,
        SignalType.MOMENTUM_DIVERGENCE,
    }
    EXIT_SIGNALS = {SignalType.EXIT_LONG, SignalType.EXIT_SHORT}

    # Time stop-loss: max holding hours before auto-exit
    MAX_HOLD_HOURS = 8

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

        # Track pending exit signals for 2-consecutive-K-line confirmation
        # Structure: {symbol: {"signal_type": str, "first_seen": datetime, "price": float}}
        self.pending_exit_signals: Dict[str, Dict] = {}

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
        # Use paper.positions as source of truth for open positions
        if symbol in self.paper.positions:
            self.logger.info(f"Already have open position for {symbol}, skipping new entry signal")
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Position already open",
            )

        # Check total exposure limit
        open_exposure = sum(
            pos["entry_price"] * pos["quantity"] for pos in self.paper.positions.values()
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
        """Process an exit signal with 2-consecutive-K-line confirmation."""
        # Use paper.positions as source of truth
        if symbol not in self.paper.positions:
            self.logger.info(f"No open position for {symbol}, skipping exit signal")
            # Also clear any stale pending exit
            self.pending_exit_signals.pop(symbol, None)
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="No open position to exit",
            )

        position = self.paper.positions[symbol]
        signal_type = signal.signal_type
        position_side_str = position["side"].value if isinstance(position["side"], TradeSide) else position["side"]

        # Verify position direction matches exit signal
        # EXIT_LONG requires a long position (buy), EXIT_SHORT requires a short position (sell)
        if signal_type == SignalType.EXIT_LONG and position_side_str != "buy":
            self.logger.info(f"Position for {symbol} is {position_side_str}, skipping EXIT_LONG")
            self.pending_exit_signals.pop(symbol, None)
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Position direction mismatch for EXIT_LONG",
            )

        if signal_type == SignalType.EXIT_SHORT and position_side_str != "sell":
            self.logger.info(f"Position for {symbol} is {position_side_str}, skipping EXIT_SHORT")
            self.pending_exit_signals.pop(symbol, None)
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason="Position direction mismatch for EXIT_SHORT",
            )

        # Check for pending exit signal (2-consecutive confirmation)
        pending = self.pending_exit_signals.get(symbol)
        signal_type_name = signal_type.name

        if pending is None:
            # First EXIT signal: record it and wait for next confirmation
            self.pending_exit_signals[symbol] = {
                "signal_type": signal_type_name,
                "first_seen": datetime.now(),
                "price": price,
            }
            self.logger.info(
                f"⏳ EXIT SIGNAL PENDING (1st): {symbol} {signal_type_name} @ ${price:,.2f} "
                f"— waiting for 2nd consecutive confirmation"
            )
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="pending_exit",
                reason=f"First EXIT {signal_type_name}, awaiting 2nd confirmation",
            )

        # Second signal: check if it's the same type
        if pending["signal_type"] != signal_type_name:
            # Signal type changed, reset pending
            self.logger.info(
                f"EXIT signal type changed for {symbol}: {pending['signal_type']} → {signal_type_name}, "
                f"resetting pending tracker"
            )
            self.pending_exit_signals[symbol] = {
                "signal_type": signal_type_name,
                "first_seen": datetime.now(),
                "price": price,
            }
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="pending_exit",
                reason=f"EXIT type changed to {signal_type_name}, awaiting confirmation",
            )

        # Same signal type on 2nd consecutive K-line: execute exit
        self.logger.info(
            f"✅ EXIT CONFIRMED (2nd): {symbol} {signal_type_name} @ ${price:,.2f} "
            f"(pending since {pending['first_seen'].strftime('%H:%M:%S')})"
        )

        # Execute paper trade exit
        try:
            trade = self.paper.exit_position(symbol=symbol, price=price)

            if trade:
                # Clear pending exit
                del self.pending_exit_signals[symbol]

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
                    reason=f"Exit confirmed (2nd K-line): {signal.reason}",
                )
            else:
                # Exit failed but clear pending to avoid getting stuck
                del self.pending_exit_signals[symbol]
                return TradeResult(
                    symbol=symbol,
                    side=side.value,
                    status="skipped",
                    reason="Exit failed - no trade record",
                )

        except Exception as e:
            self.logger.error(f"Trade exit failed for {symbol}: {e}")
            # Clear pending on error
            self.pending_exit_signals.pop(symbol, None)
            return TradeResult(
                symbol=symbol,
                side=side.value,
                status="skipped",
                reason=f"Exit execution error: {e}",
            )

    def check_time_stop_loss(self, current_prices: Dict[str, float]) -> List[TradeResult]:
        """
        Check all open positions and exit any held longer than MAX_HOLD_HOURS.
        Returns list of TradeResult for any time-stopped positions.
        """
        results = []
        if not self.paper:
            return results

        now = datetime.now()
        max_hold_delta = timedelta(hours=self.MAX_HOLD_HOURS)

        # Iterate over a copy since we may modify during iteration
        symbols = list(self.paper.positions.keys())
        for symbol in symbols:
            position = self.paper.positions.get(symbol)
            if not position:
                continue

            entry_time = position.get("entry_time")
            if not entry_time:
                continue

            # Ensure entry_time is datetime
            if isinstance(entry_time, str):
                entry_time = datetime.fromisoformat(entry_time)

            hold_duration = now - entry_time
            if hold_duration > max_hold_delta:
                price = current_prices.get(symbol)
                if not price or price <= 0:
                    self.logger.warning(
                        f"Time stop-loss for {symbol}: held {hold_duration.total_seconds()/3600:.1f}h "
                        f"but no valid price, skipping auto-exit"
                    )
                    continue

                position_side_str = position["side"].value if isinstance(position["side"], TradeSide) else position["side"]
                exit_side = TradeSide.SELL if position_side_str == "buy" else TradeSide.BUY

                self.logger.info(
                    f"⏰ TIME STOP-LOSS TRIGGERED: {symbol} held {hold_duration.total_seconds()/3600:.1f}h "
                    f"(max {self.MAX_HOLD_HOURS}h), auto-exiting @ ${price:,.2f}"
                )

                try:
                    trade = self.paper.exit_position(symbol=symbol, price=price)
                    if trade:
                        # Clear any pending exit for this symbol
                        self.pending_exit_signals.pop(symbol, None)

                        self.logger.info(
                            f"✅ PAPER TRADE TIME-STOP: {symbol} @ ${price:,.2f} "
                            f"PnL: ${trade.realized_pnl:.2f} (balance: ${self.paper.balance:,.2f})"
                        )
                        results.append(TradeResult(
                            symbol=symbol,
                            side=exit_side.value,
                            status="time_stopped",
                            trade_id=trade.trade_id,
                            quantity=trade.quantity,
                            entry_price=trade.entry_price,
                            balance_after=self.paper.balance,
                            reason=f"Time stop-loss: held {hold_duration.total_seconds()/3600:.1f}h",
                        ))
                except Exception as e:
                    self.logger.error(f"Time stop-loss exit failed for {symbol}: {e}")

        return results

    def get_paper_performance(self) -> Optional[Dict]:
        """Get paper trading performance summary."""
        if not self.paper:
            return None

        perf = self.paper.get_performance()
        # Add pending exits info for visibility
        perf["pending_exits"] = len(self.pending_exit_signals)
        perf["pending_exit_symbols"] = list(self.pending_exit_signals.keys())
        return perf

    def save_state(self) -> None:
        """Save paper trading state / 儲存模擬交易狀態"""
        if self.paper and self.state_file:
            self.paper.save_state(self.state_file)

    def reset(self):
        """Reset paper trading account and positions."""
        if self.paper:
            self.paper.reset()
        self.pending_exit_signals.clear()
        self.logger.info("TradeExecutor reset")
