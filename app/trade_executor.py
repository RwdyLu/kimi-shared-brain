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
from pathlib import Path
import json

from app.paper_trading import PaperTrading
from signals.engine import SignalType, SignalLevel
from config.paths import STATE_DIR

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "strategies.json"


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

    # ─── New Risk Management Parameters / 新風險管理參數 ─────────────────
    HARD_STOP_LOSS = -0.05           # 硬止損 -5% (原 -3% 太緊)
    MAX_HOLD_HOURS = 8               # 最大持倉時間
    
    # 階梯ROI止盈 / 根據持倉時間動態調整
    MINIMAL_ROI = {
        0: 0.05,      # 0分鐘:  5%
        20: 0.04,     # 20分鐘: 4%
        40: 0.03,     # 40分鐘: 3%
        60: 0.02,     # 60分鐘: 2%
        120: 0.01,    # 120分鐘: 1%
        240: 0.005,   # 240分鐘: 0.5%
    }
    
    # 移動止损 / 鎖定利潤
    TRAILING_STOP_ENABLED = True
    TRAILING_STOP_OFFSET = 0.03    # 利潤超過 3% 後啟動
    TRAILING_STOP_DISTANCE = 0.02  # 回撤 2% 出場
    
    # ATR動態止损倍數
    ATR_STOP_MULTIPLIER = 1.5
    
    # MA 反轉與 Hilbert 反轉閾值（可策略覆蓋）
    MA_REVERSE_PNL_THRESHOLD = -0.015   # V2: 從 -0.5% 收緊至 -1.5%
    HILBERT_REVERSE_PNL_RANGE = 0.015  # V2: 從 ±2% 收緊至 ±1.5%
    
    # 策略專屬參數覆蓋 (可選)
    STRATEGY_PARAMS = {
        'ma_cross_trend': {
            'hard_stop': -0.05,
            'trailing_enabled': True,
            'trailing_offset': 0.03,
            'trailing_distance': 0.02,
            'min_roi': {0: 0.04, 30: 0.03, 60: 0.02, 120: 0.01, 240: 0.005},
        },
        'volume_spike': {
            'hard_stop': -0.04,
            'trailing_enabled': True,
            'trailing_offset': 0.025,
            'trailing_distance': 0.015,
            'min_roi': {0: 0.03, 20: 0.02, 40: 0.015, 60: 0.01},
        },
    }

    def __init__(
        self,
        exchange=None,
        paper_trading: Optional[PaperTrading] = None,
        position_pct: float = 0.15,
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

        # Load strategy configs for reverse_mode detection / 載入策略配置以偵測反向模式
        self._strategy_configs: Dict[str, dict] = {}
        self._default_params: Dict[str, Any] = {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for s in cfg.get("strategies", []):
                sid = s.get("id", "")
                params = s.get("parameters", {})
                self._strategy_configs[sid] = params
            # Load global default params / 載入全域預設參數
            self._default_params = cfg.get("default_params", {})
            self.logger.info(f"Loaded default_params: hard_stop={self._default_params.get('hard_stop_loss')}, "
                           f"atr_mult={self._default_params.get('atr_stop_multiplier')}, "
                           f"ma_reverse={self._default_params.get('ma_reverse_pnl_threshold')}")
        except Exception as e:
            self.logger.warning(f"Could not load strategy configs: {e}")

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

    def _get_latest_indicators(self, symbol: str) -> dict:
        """
        DEPRECATED: Real-time indicators are now passed directly from scheduler.
        Kept as fallback for compatibility.
        """
        return {}

    def _check_strategy_exit(self, strategy_id: str, position: dict, current_indicators: dict) -> tuple:
        """
        Unified risk management exit logic / 統一風險管理出場邏輯

        Exit hierarchy:
        1. Hard stop-loss (strategy-specific or global -5%)
        2. ATR-based dynamic stop-loss (if ATR available)
        3. Trailing stop-loss (lock profits)
        4. Minimal ROI take-profit (time-based阶梯止盈)
        5. Technical indicator reversal signals
        6. Time stop-loss (8h max hold)

        Returns (should_exit: bool, reason: str)
        """
        side = position.get('side', 'buy')
        entry_price = position.get('entry_price', 0)
        current_price = current_indicators.get('price', 0)
        entry_time_str = position.get('entry_time', '')

        if not current_price or entry_price <= 0:
            return False, None

        if side.lower() == 'buy':
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        # ─── Get strategy-specific params or defaults / 取得策略參數或預設 ──
        # Priority: STRATEGY_PARAMS > default_params > class constants
        defaults = self._default_params.copy()
        overrides = self.STRATEGY_PARAMS.get(strategy_id, {})
        
        hard_stop = overrides.get('hard_stop', defaults.get('hard_stop_loss', self.HARD_STOP_LOSS))
        trailing_enabled = overrides.get('trailing_enabled', self.TRAILING_STOP_ENABLED)
        trailing_offset = overrides.get('trailing_offset', defaults.get('trailing_stop_trigger', self.TRAILING_STOP_OFFSET))
        trailing_distance = overrides.get('trailing_distance', defaults.get('trailing_stop_drawback', self.TRAILING_STOP_DISTANCE))
        min_roi = overrides.get('min_roi', defaults.get('profit_targets', self.MINIMAL_ROI))
        atr_multiplier = overrides.get('atr_stop_multiplier', defaults.get('atr_stop_multiplier', self.ATR_STOP_MULTIPLIER))
        time_stop_hours = overrides.get('time_stop_hours', defaults.get('time_stop_hours', 8.2))

        # ─── 1. Hard Stop-Loss / 硬止損 ────────────────────────────────────
        if pnl_pct <= hard_stop:
            return True, f'hard_stop_{abs(hard_stop)*100:.0f}pct'

        # ─── 2. ATR Dynamic Stop-Loss / ATR動態止損 ───────────────────────
        atr = current_indicators.get('atr14', 0)
        if atr and atr > 0:
            atr_floor = defaults.get('atr_min_floor', -0.02)
            atr_stop_pct_raw = -(atr * atr_multiplier / entry_price)
            atr_stop_pct = max(atr_stop_pct_raw, atr_floor)  # Floor from config
            if pnl_pct <= atr_stop_pct:
                return True, f'atr_stop_{abs(atr_stop_pct)*100:.1f}pct'

        # ─── 3. Trailing Stop-Loss / 移動止损（鎖定利潤）────────────────
        if trailing_enabled and pnl_pct >= trailing_offset:
            # Calculate trailing stop price / 計算移動止损價格
            if side.lower() == 'buy':
                trail_price = entry_price * (1 + pnl_pct - trailing_distance)
                if current_price <= trail_price:
                    return True, f'trailing_stop_{trailing_distance*100:.1f}pct'
            else:
                trail_price = entry_price * (1 - pnl_pct + trailing_distance)
                if current_price >= trail_price:
                    return True, f'trailing_stop_{trailing_distance*100:.1f}pct'

        # ─── 4. Minimal ROI (Time-based阶梯止盈) ─────────────────────────
        if entry_time_str:
            try:
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                hold_minutes = (datetime.now() - entry_time).total_seconds() / 60

                # Find applicable ROI threshold / 找到適用的ROI門檻
                applicable_roi = 0.0
                for minutes_threshold, roi in sorted(min_roi.items(), key=lambda x: int(x[0]), reverse=True):
                    if hold_minutes >= int(minutes_threshold):
                        applicable_roi = roi
                        break

                if pnl_pct >= applicable_roi and applicable_roi > 0:
                    return True, f'min_roi_{applicable_roi*100:.1f}pct_{hold_minutes:.0f}min'
            except Exception:
                pass

        # ─── 5. Technical Indicator Reversal / 技術指標反轉 ───────────────
        ma5 = current_indicators.get('ma5', 0)
        ma20 = current_indicators.get('ma20', 0)
        rsi = current_indicators.get('rsi', 50)
        ht_sine = current_indicators.get('ht_sine', 0)
        ht_leadsine = current_indicators.get('ht_leadsine', 0)
        stoch_k = current_indicators.get('stoch_fastk', 50)
        stoch_d = current_indicators.get('stoch_fastd', 50)

        # MA cross reversal — only for losing positions / MA交叉反轉（僅虧損倉位）
        # V2 tightened: must be in loss > threshold AND MA crossed against position
        ma_reverse_threshold = overrides.get('ma_reverse_pnl', defaults.get('ma_reverse_pnl_threshold', self.MA_REVERSE_PNL_THRESHOLD))
        if ma5 and ma20 and pnl_pct < ma_reverse_threshold:
            if side.lower() == 'buy' and ma5 < ma20:
                return True, 'ma_reverse'
            if side.lower() == 'sell' and ma5 > ma20:
                return True, 'ma_reverse'

        # Hilbert cycle reversal / Hilbert週期反轉
        # V2 tightened: only within ±1.5% PnL range
        hilbert_range = overrides.get('hilbert_reverse_range', defaults.get('hilbert_reverse_pnl_range', self.HILBERT_REVERSE_PNL_RANGE))
        if ht_sine and ht_leadsine and abs(pnl_pct) < hilbert_range:
            if side.lower() == 'buy' and ht_sine < ht_leadsine:
                return True, 'hilbert_reverse'
            if side.lower() == 'sell' and ht_sine > ht_leadsine:
                return True, 'hilbert_reverse'

        # Stochastic overbought/oversold / 隨機指標極端
        if side.lower() == 'buy' and stoch_k > 85 and pnl_pct > 0:
            return True, 'stoch_overbought'
        if side.lower() == 'sell' and stoch_k < 15 and pnl_pct > 0:
            return True, 'stoch_oversold'

        # RSI extreme exit / RSI極端出場
        if side.lower() == 'buy' and rsi > 75 and pnl_pct > 0.01:
            return True, 'rsi_extreme'
        if side.lower() == 'sell' and rsi < 25 and pnl_pct > 0.01:
            return True, 'rsi_extreme'

        # ─── 6. Time Stop-Loss / 時間止損 ──────────────────────────────────
        if entry_time_str:
            try:
                entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                hold_hours = (datetime.now() - entry_time).total_seconds() / 3600
                if hold_hours >= time_stop_hours:
                    return True, f'time_stop_{hold_hours:.1f}h'
            except Exception:
                pass

        return False, None

    def execute_signals(
        self,
        confirmed_signals: List,
        current_prices: Dict[str, float],
        current_indicators: Optional[Dict[str, Dict]] = None,
    ) -> List[TradeResult]:
        """Execute trades for confirmed signals."""
        results = []
        if not self.enable_trading or not self.paper:
            self.logger.info("Trading disabled, skipping execution")
            return results

        current_indicators = current_indicators or {}

        # Step 0: Check strategy-specific exits before new entries
        # / 步驟 0：在開新倉前先檢查策略專屬出場條件
        exit_results = self._check_strategy_exits(current_prices, current_indicators)
        results.extend(exit_results)

        for signal in confirmed_signals:
            result = self._process_signal(signal, current_prices)
            if result:
                results.append(result)
        return results

    def _check_strategy_exits(self, current_prices: Dict[str, float], current_indicators: Dict[str, Dict]) -> List[TradeResult]:
        """
        Scan all open positions for strategy-specific exit conditions.
        / 掃描所有未平倉位，檢查策略專屬出場條件。
        """
        results = []
        if not self.paper:
            return results

        for strategy_id, acc in self.paper.strategies.items():
            for symbol, positions in list(acc.positions.items()):
                if not positions:
                    continue

                # Use real-time indicators from scheduler / 使用排程器傳入的即時指標
                indicators = current_indicators.get(symbol, {})
                current_price = current_prices.get(symbol, 0)
                if current_price > 0:
                    indicators["price"] = current_price

                # Check each position (FIFO order) / 逐倉位檢查（FIFO 順序）
                for position in list(positions):
                    should_exit, reason = self._check_strategy_exit(strategy_id, position, indicators)
                    if should_exit:
                        if current_price <= 0:
                            continue
                        position_side = position.get("side", "")
                        exit_side = TradeSide.SELL if position_side.lower() == "buy" else TradeSide.BUY

                        try:
                            trade = self.paper.exit_position(symbol=symbol, price=current_price, strategy_id=strategy_id, exit_reason=reason)
                            if trade:
                                balance_after = self.paper.get_strategy_balance(strategy_id)
                                self.logger.info(
                                    f"🎯 STRATEGY EXIT [{strategy_id}] {symbol} @ ${current_price:,.2f} "
                                    f"reason={reason} PnL=${trade.get('realized_pnl', 0):+.2f}"
                                )
                                results.append(TradeResult(
                                    symbol=symbol, side=exit_side, status="exited",
                                    trade_id=trade.get("trade_id"),
                                    quantity=trade.get("quantity"),
                                    entry_price=trade.get("entry_price"),
                                    balance_after=balance_after,
                                    reason=f"Strategy exit: {reason}",
                                    strategy_id=strategy_id,
                                ))
                        except Exception as e:
                            self.logger.error(f"[{strategy_id}] Strategy exit failed for {symbol}: {e}")
                    else:
                        # FIFO: if oldest position doesn't exit, newer ones won't either
                        break

        return results

    def _resolve_trade_side(self, signal) -> str:
        """Resolve trade side from signal metadata direction.
        Uses metadata['direction'] (LONG/SHORT) if available,
        falls back to static SIGNAL_TO_SIDE mapping.
        If strategy config has reverse_mode=True, flip the side.
        """
        meta = getattr(signal, 'metadata', None) or {}
        direction = meta.get('direction', '')
        if direction == 'LONG':
            side = TradeSide.BUY
        elif direction == 'SHORT':
            side = TradeSide.SELL
        else:
            side = self.SIGNAL_TO_SIDE.get(signal.signal_type)

        # Reverse mode detection / 反向模式偵測
        strategy_id = self._get_strategy_id(signal)
        params = self._strategy_configs.get(strategy_id, {})
        if params.get("reverse_mode", False):
            # Flip side: BUY -> SELL, SELL -> BUY
            flipped = TradeSide.SELL if side == TradeSide.BUY else TradeSide.BUY
            self.logger.info(
                f"🔄 REVERSE MODE [{strategy_id}]: signal={signal.signal_type.name} "
                f"original_side={side} -> flipped={flipped}"
            )
            return flipped
        return side

    def _process_signal(self, signal, current_prices: Dict[str, float]) -> Optional[TradeResult]:
        """Process a single confirmed signal."""
        symbol = signal.symbol
        signal_type = signal.signal_type
        strategy_id = self._get_strategy_id(signal)

        side = self._resolve_trade_side(signal)
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

        # Check exposure limit (per-strategy) / 檢查單策略曝險上限
        strategy_balance = self.paper.get_strategy_balance(strategy_id)
        open_positions = self.paper.get_strategy_positions(strategy_id)
        open_exposure = sum(
            p.get("entry_price", 0) * p.get("quantity", 0)
            for positions in open_positions.values()
            for p in positions
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

        # Verify direction matches — check oldest position (FIFO) / 驗證方向匹配（檢查最老的倉位）
        positions = self.paper.get_strategy_positions(strategy_id).get(symbol, [])
        if not positions:
            self.pending_exit_signals.get(symbol, {}).pop(strategy_id, None)
            return TradeResult(
                symbol=symbol, side=side, status="skipped",
                reason="No open position to exit", strategy_id=strategy_id,
            )
        position = positions[0]  # FIFO — oldest position
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

        # Check if position is in loss — skip 2-K confirmation for stop-loss / 虧損倉位立即出場，不等待 2-K 確認
        entry_price = position.get("entry_price", 0)
        position_quantity = position.get("quantity", 0)
        is_loss = False
        if entry_price > 0 and position_quantity > 0:
            if position_side == TradeSide.BUY:
                pnl_pct = (price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - price) / entry_price
            is_loss = pnl_pct < 0

        # 2-K-line confirmation / 連續 2 根 K 線確認
        # Skip confirmation for stop-loss exits / 止損出場跳過確認
        if not is_loss:
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
        else:
            self.logger.info(
                f"⚡ STOP-LOSS EXIT [{strategy_id}] {symbol} {signal_type_name} @ ${price:,.2f} "
                f"(PnL={pnl_pct*100:+.2f}%, skipping 2-K confirmation)"
            )

        # Execute exit / 執行出場
        self.logger.info(
            f"✅ EXIT CONFIRMED [{strategy_id}] {symbol} {signal_type_name} @ ${price:,.2f}"
        )

        try:
            trade = self.paper.exit_position(symbol=symbol, price=price, strategy_id=strategy_id, exit_reason=f"signal_exit:{signal.reason}")
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
        """Exit positions held longer than MAX_HOLD_HOURS / 時間止損：持倉超過 8 小時自動平倉

        Only applies to strategies WITHOUT their own exit logic.
        Strategies with dedicated exit conditions (ma_cross, rsi, etc.) skip time stop.
        """
        results = []
        if not self.paper:
            return results

        now = datetime.now()
        max_hold_delta = timedelta(hours=self.MAX_HOLD_HOURS)

        for strategy_id, acc in self.paper.strategies.items():
            # All strategies now use unified exit logic with time stop / 所有策略現在使用統一出場邏輯（含時間止損）
            for symbol, positions in list(acc.positions.items()):
                if not positions:
                    continue

                # Check each position individually / 逐倉位檢查
                for position in list(positions):
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
                            trade = self.paper.exit_position(symbol=symbol, price=price, strategy_id=strategy_id, exit_reason=f"time_stop:{hold_duration.total_seconds()/3600:.1f}h")
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
                    else:
                        # Since positions are FIFO, if this one hasn't reached the limit, newer ones won't either
                        break


    # ─── Strategy-specific exit logic / 策略專屬出場邏輯 ────────────────────

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

    def reload_paper(self):
        """Reload paper trading state from disk / 重新載入模擬交易狀態"""
        if self.paper:
            self.paper.reload()
            self.logger.info(f"Paper state reloaded: {len(self.paper.strategies)} strategies")

    def reset(self):
        """Reset paper trading / 重置模擬交易"""
        if self.paper:
            # Re-initialize fresh state / 重新初始化全新狀態
            self.paper._init_new_state()
            self.paper._save_state()
        self.pending_exit_signals.clear()
        self.logger.info("TradeExecutor reset")
