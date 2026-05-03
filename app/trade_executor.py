"""
Trade Executor — Per-Strategy Isolated Execution / 策略獨立交易執行器

Connects strategy signals to per-strategy paper trading accounts.
Each strategy trades with its own isolated capital and positions.

Author: kimiclaw_bot
Version: 2.0.0
Date: 2026-05-03
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.paper_trading import PaperTrading
from signals.engine import SignalType, SignalLevel
from config.paths import STATE_DIR

logger = logging.getLogger(__name__)


# ─── Local TradeSide enum / 本地交易方向列舉 ─────────────────────
class TradeSide:
    BUY = "buy"
    SELL = "sell"


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
    strategy_id: str = ""


class TradeExecutor:
    """
    Trade executor bridging strategy signals to per-strategy paper trading.
    """

    # Signal type → trade side mapping
    SIGNAL_TO_SIDE = {
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
        SignalType.EXIT_LONG: TradeSide.SELL,
        SignalType.EXIT_SHORT: TradeSide.BUY,
    }

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

    MAX_HOLD_HOURS = 8

    def __init__(
        self,
        exchange=None,
        paper_trading: Optional[PaperTrading] = None,
        position_pct: float = 0.1,
        max_total_exposure_pct: float = 0.5,
        enable_trading: bool = True,
    ):
        self.logger = logging.getLogger(__name__)
        self.enable_trading = enable_trading
        self.position_pct = position_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.exchange = exchange

        # Paper trading instance (auto-loads state)
        self.paper = paper_trading or (PaperTrading() if enable_trading else None)

        # Pending exit signals: {symbol: {strategy_id: {...}}}
        self.pending_exit_signals: Dict[str, Dict[str, Dict]] = {}

        self.logger.info(
            f"TradeExecutor initialized: strategies={list(self.paper.strategies.keys()) if self.paper else []}, "
            f"position_pct={position_pct*100}%, enabled={enable_trading}"
        )

    def _get_strategy_id(self, signal) -> str:
        """Extract strategy_id from signal metadata / 從訊號元資料提取策略 ID"""
        meta = getattr(signal, 'metadata', None) or {}
        sid = meta.get('strategy_id') or meta.get('strategy_name') or ''
        if sid:
            return sid.lower().replace(' ', '_').replace('-', '_')
        # Fallback: map from signal type name / 後備：從訊號類型名稱映射
        return signal.signal_type.name.lower().replace(' ', '_').replace('-', '_')

    def execute_signals(
        self,
        confirmed_signals: List,
        current_prices: Dict[str, float],
    ) -> List[TradeResult]:
        """Execute trades for confirmed signals."""
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
        """Process a single confirmed signal."""
        symbol = signal.symbol
        signal_type = signal.signal_type
        strategy_id = self._get_strategy_id(signal)

        side = self.SIGNAL_TO_SIDE.get(signal_type)
        if not side:
            return TradeResult(
                symbol=symbol, side="unknown", status="skipped",
                reason=f"Unmapped signal type: {signal_type.name}", strategy_id=strategy_id,
            )

        price = current_prices.get(symbol)
        if not price or price <= 0:
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="No valid price", strategy_id=strategy_id,
            )

        # EXIT signal / 出場訊號
        if signal_type in self.EXIT_SIGNALS:
            return self._process_exit_signal(symbol, signal, price, side, strategy_id)

        # ENTRY signal / 進場訊號 ──────────────────────────────────
        # Check strategy exists / 檢查策略存在
        if strategy_id not in self.paper.strategies:
            self.logger.warning(f"[{strategy_id}] Strategy not in paper trading, skipping entry")
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason=f"Unknown strategy: {strategy_id}", strategy_id=strategy_id,
            )

        # Check if already holding / 檢查是否已持有
        if self.paper.has_position(strategy_id, symbol):
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="Position already open", strategy_id=strategy_id,
            )

        # Check exposure limit (per-strategy) / 檢查單策略曝險上限
        strategy_balance = self.paper.get_strategy_balance(strategy_id)
        open_positions = self.paper.get_strategy_positions(strategy_id)
        open_exposure = sum(
            p.get("entry_price", 0) * p.get("quantity", 0)
            for p in open_positions.values()
        )
        max_exposure = strategy_balance * self.max_total_exposure_pct
        if open_exposure >= max_exposure:
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="Max strategy exposure reached", strategy_id=strategy_id,
            )

        # Calculate position size from strategy balance / 依策略餘額計算倉位大小
        position_value = strategy_balance * self.position_pct
        if position_value < 1.0:
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="Insufficient strategy balance", strategy_id=strategy_id,
            )

        quantity = position_value / price

        # Execute entry / 執行進場
        try:
            success = self.paper.enter_position(
                symbol=symbol, side=side, quantity=quantity,
                price=price, strategy_id=strategy_id,
            )
            if not success:
                return TradeResult(
                    symbol=symbol, side=side, status="skipped",
                    reason="Enter position returned False", strategy_id=strategy_id,
                )

            balance_after = self.paper.get_strategy_balance(strategy_id)
            self.logger.info(
                f"✅ PAPER ENTRY [{strategy_id}] {side.upper()} {quantity:.6f} {symbol} "
                f"@ ${price:,.2f} balance=${balance_after:.2f}"
            )

            return TradeResult(
                symbol=symbol, side=side, status="executed",
                quantity=quantity, entry_price=price,
                balance_after=balance_after,
                reason=signal.reason, strategy_id=strategy_id,
            )

        except Exception as e:
            self.logger.error(f"[{strategy_id}] Entry failed for {symbol}: {e}")
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason=f"Entry error: {e}", strategy_id=strategy_id,
            )

    def _process_exit_signal(
        self, symbol: str, signal, price: float, side: str, strategy_id: str
    ) -> Optional[TradeResult]:
        """Process exit signal with 2-K-line confirmation / 處理出場訊號（需連續 2 根 K 線確認）"""
        # Check if this strategy holds the symbol / 檢查該策略是否持有此幣種
        if not self.paper.has_position(strategy_id, symbol):
            self.pending_exit_signals.get(symbol, {}).pop(strategy_id, None)
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="No open position to exit", strategy_id=strategy_id,
            )

        position = self.paper.get_strategy_positions(strategy_id).get(symbol, {})
        position_side = position.get("side", "")
        signal_type = signal.signal_type
        signal_type_name = signal_type.name

        # Verify direction matches / 驗證方向匹配
        if signal_type == SignalType.EXIT_LONG and position_side != TradeSide.BUY:
            self.pending_exit_signals.get(symbol, {}).pop(strategy_id, None)
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="EXIT_LONG mismatch", strategy_id=strategy_id,
            )
        if signal_type == SignalType.EXIT_SHORT and position_side != TradeSide.SELL:
            self.pending_exit_signals.get(symbol, {}).pop(strategy_id, None)
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="EXIT_SHORT mismatch", strategy_id=strategy_id,
            )

        # 2-K-line confirmation / 連續 2 根 K 線確認
        if symbol not in self.pending_exit_signals:
            self.pending_exit_signals[symbol] = {}

        pending = self.pending_exit_signals[symbol].get(strategy_id)

        if pending is None:
            self.pending_exit_signals[symbol][strategy_id] = {
                "signal_type": signal_type_name,
                "first_seen": datetime.now(),
                "price": price,
            }
            self.logger.info(
                f"⏳ EXIT PENDING [{strategy_id}] {symbol} {signal_type_name} @ ${price:,.2f}"
            )
            return TradeResult(
                symbol=symbol, side=side, status="pending_exit",
                reason=f"1st EXIT, awaiting 2nd confirmation", strategy_id=strategy_id,
            )

        if pending["signal_type"] != signal_type_name:
            self.pending_exit_signals[symbol][strategy_id] = {
                "signal_type": signal_type_name,
                "first_seen": datetime.now(),
                "price": price,
            }
            return TradeResult(
                symbol=symbol, side=side, status="pending_exit",
                reason=f"EXIT type changed to {signal_type_name}", strategy_id=strategy_id,
            )

        # 2nd confirmation — execute exit / 第二次確認 — 執行出場
        self.logger.info(
            f"✅ EXIT CONFIRMED [{strategy_id}] {symbol} {signal_type_name} @ ${price:,.2f}"
        )

        try:
            trade = self.paper.exit_position(symbol=symbol, price=price, strategy_id=strategy_id)
            self.pending_exit_signals[symbol].pop(strategy_id, None)

            if trade:
                balance_after = self.paper.get_strategy_balance(strategy_id)
                self.logger.info(
                    f"✅ PAPER EXIT [{strategy_id}] {symbol} @ ${price:,.2f} "
                    f"PnL=${trade.get('realized_pnl', 0):+.2f} balance=${balance_after:.2f}"
                )
                return TradeResult(
                    symbol=symbol, side=side, status="exited",
                    trade_id=trade.get("trade_id"),
                    quantity=trade.get("quantity"),
                    entry_price=trade.get("entry_price"),
                    balance_after=balance_after,
                    reason=f"Exit confirmed (2nd K-line): {signal.reason}",
                    strategy_id=strategy_id,
                )
            else:
                return TradeResult(
                    symbol=symbol, side=side, status="skipped",
                    reason="Exit failed", strategy_id=strategy_id,
                )

        except Exception as e:
            self.logger.error(f"[{strategy_id}] Exit failed for {symbol}: {e}")
            self.pending_exit_signals[symbol].pop(strategy_id, None)
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason=f"Exit error: {e}", strategy_id=strategy_id,
            )

    def check_time_stop_loss(self, current_prices: Dict[str, float]) -> List[TradeResult]:
        """Exit positions held longer than MAX_HOLD_HOURS / 時間止損：持倉超過 8 小時自動平倉"""
        results = []
        if not self.paper:
            return results

        now = datetime.now()
        max_hold_delta = timedelta(hours=self.MAX_HOLD_HOURS)

        for strategy_id, acc in self.paper.strategies.items():
            for symbol in list(acc.positions.keys()):
                position = acc.positions.get(symbol)
                if not position:
                    continue

                entry_time_str = position.get("entry_time")
                if not entry_time_str:
                    continue

                entry_time = datetime.fromisoformat(entry_time_str) if isinstance(entry_time_str, str) else entry_time_str
                hold_duration = now - entry_time

                if hold_duration > max_hold_delta:
                    price = current_prices.get(symbol, 0)
                    if price <= 0:
                        self.logger.warning(f"[{strategy_id}] Time stop for {symbol}: no price")
                        continue

                    position_side = position.get("side", "")
                    exit_side = TradeSide.SELL if position_side == TradeSide.BUY else TradeSide.BUY

                    self.logger.info(
                        f"⏰ TIME STOP [{strategy_id}] {symbol} held {hold_duration.total_seconds()/3600:.1f}h"
                    )

                    try:
                        trade = self.paper.exit_position(symbol=symbol, price=price, strategy_id=strategy_id)
                        self.pending_exit_signals.get(symbol, {}).pop(strategy_id, None)

                        if trade:
                            balance_after = self.paper.get_strategy_balance(strategy_id)
                            results.append(TradeResult(
                                symbol=symbol, side=exit_side, status="time_stopped",
                                trade_id=trade.get("trade_id"),
                                quantity=trade.get("quantity"),
                                entry_price=trade.get("entry_price"),
                                balance_after=balance_after,
                                reason=f"Time stop: {hold_duration.total_seconds()/3600:.1f}h",
                                strategy_id=strategy_id,
                            ))
                    except Exception as e:
                        self.logger.error(f"[{strategy_id}] Time stop exit failed: {e}")

        return results

    def get_paper_performance(self) -> Optional[Dict]:
        """Get paper trading summary / 取得模擬交易總覽"""
        if not self.paper:
            return None
        perf = self.paper.get_summary()
        perf["pending_exits"] = sum(len(v) for v in self.pending_exit_signals.values())
        perf["pending_exit_symbols"] = list(self.pending_exit_signals.keys())
        return perf

    def save_state(self) -> None:
        """PaperTrading auto-saves; this is a no-op for compatibility."""
        pass

    def reset(self):
        """Reset paper trading / 重置模擬交易"""
        if self.paper:
            # Re-initialize fresh state / 重新初始化全新狀態
            self.paper._init_new_state()
            self.paper._save_state()
        self.pending_exit_signals.clear()
        self.logger.info("TradeExecutor reset")
