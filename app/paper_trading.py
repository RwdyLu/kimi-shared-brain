"""
Paper Trading Engine — Per-Strategy Isolated Capital / 策略獨立資金模擬交易

Each enabled strategy gets its own $1,000 virtual account.
Positions and trades are fully isolated by strategy_id.
Intraday positions are force-closed before 23:59.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# ─── Constants / 常數 ──────────────────────────────────────────
INITIAL_BALANCE_PER_STRATEGY = 1000.0
COMMISSION_RATE = 0.001
SLIPPAGE_RATE = 0.0001
MAX_POSITION_RATIO = 0.20  # 20% per position
DAILY_LOSS_LIMIT_PCT = 0.05  # 5% daily loss limit
STATE_FILE = Path(__file__).resolve().parents[1] / "state" / "paper_trading_state.json"
CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "strategies.json"


# ─── Data Classes / 資料類別 ────────────────────────────────────
@dataclass
class Position:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_time: str
    strategy_id: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        return cls(**data)


@dataclass
class Trade:
    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    entry_time: str
    exit_time: Optional[str]
    slippage: float
    commission: float
    realized_pnl: float
    strategy_id: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Trade":
        return cls(**data)


@dataclass
class StrategyAccount:
    """Per-strategy virtual trading account / 單一策略虛擬交易帳戶

    positions: Dict[str, List[dict]] — symbol -> [position1, position2, ...]
    Allows multiple simultaneous positions per symbol.
    """
    balance: float
    initial: float
    positions: Dict[str, List[dict]] = field(default_factory=dict)
    trades: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "balance": self.balance,
            "initial": self.initial,
            "positions": self.positions,
            "trades": self.trades,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyAccount":
        raw_positions = data.get("positions", {})
        # Migrate old format (Dict[str, dict]) -> new (Dict[str, List[dict]])
        positions: Dict[str, List[dict]] = {}
        for sym, pos in raw_positions.items():
            if isinstance(pos, list):
                positions[sym] = pos
            elif isinstance(pos, dict):
                # Old single-position format: wrap in list
                positions[sym] = [pos]
            else:
                positions[sym] = []
        return cls(
            balance=data.get("balance", INITIAL_BALANCE_PER_STRATEGY),
            initial=data.get("initial", INITIAL_BALANCE_PER_STRATEGY),
            positions=positions,
            trades=data.get("trades", []),
        )


# ─── Paper Trading Engine / 模擬交易引擎 ─────────────────────────
class PaperTrading:
    """
    Paper trading with per-strategy isolated capital.
    Each enabled strategy gets $1,000 and trades independently.
    """

    def __init__(self):
        self.state: Dict[str, Any] = {}
        self.strategies: Dict[str, StrategyAccount] = {}
        self.total_initial: float = 0.0
        self.last_updated: str = ""
        self.daily_settlements: Dict[str, Dict[str, dict]] = {}
        self._load_state()

    def _enabled_strategy_ids(self) -> List[str]:
        """Read enabled strategies from config / 從設定讀取啟用策略"""
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                s["id"]
                for s in data.get("strategies", [])
                if s.get("enabled", False)
            ]
        except Exception as e:
            logger.error(f"Failed to load strategies config: {e}")
            return []

    def _init_new_state(self):
        """Initialize fresh per-strategy state / 初始化全新策略獨立狀態"""
        enabled = self._enabled_strategy_ids()
        self.strategies = {
            sid: StrategyAccount(
                balance=INITIAL_BALANCE_PER_STRATEGY,
                initial=INITIAL_BALANCE_PER_STRATEGY,
            )
            for sid in enabled
        }
        self.total_initial = len(enabled) * INITIAL_BALANCE_PER_STRATEGY
        self.last_updated = datetime.now().isoformat()
        self.daily_settlements = {}
        logger.info(
            f"Initialized {len(enabled)} strategy accounts, "
            f"total initial: ${self.total_initial:,.2f}"
        )

    def _load_state(self):
        """Load state from disk / 從磁碟載入狀態"""
        if not STATE_FILE.exists():
            self._init_new_state()
            self._save_state()
            return

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state: {e}, reinitializing")
            self._init_new_state()
            self._save_state()
            return

        # Detect old single-balance format / 偵測舊格式
        if "strategies" not in raw:
            logger.warning("Old state format detected — reinitializing per-strategy accounts")
            self._init_new_state()
            self._save_state()
            return

        # Load new format / 載入新格式
        self.strategies = {
            sid: StrategyAccount.from_dict(acc)
            for sid, acc in raw.get("strategies", {}).items()
        }
        self.total_initial = raw.get("total_initial", 0)
        self.last_updated = raw.get("last_updated", "")
        self.daily_settlements = raw.get("daily_settlements", {})

    def _save_state(self):
        """Save state to disk / 保存狀態到磁碟"""
        self.last_updated = datetime.now().isoformat()
        state = {
            "strategies": {
                sid: acc.to_dict() for sid, acc in self.strategies.items()
            },
            "total_initial": self.total_initial,
            "last_updated": self.last_updated,
            "daily_settlements": self.daily_settlements,
        }
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    # ─── Public API / 公開介面 ─────────────────────────────────────

    def get_strategy_balance(self, strategy_id: str) -> float:
        """Get current balance for a strategy / 取得策略當前餘額"""
        acc = self.strategies.get(strategy_id)
        return acc.balance if acc else 0.0

    def get_strategy_positions(self, strategy_id: str) -> Dict[str, List[dict]]:
        """Get open positions for a strategy / 取得策略未平倉

        Returns Dict[str, List[dict]] — symbol -> [position1, ...]
        """
        acc = self.strategies.get(strategy_id)
        return acc.positions if acc else {}

    def get_all_positions(self) -> Dict[str, Dict[str, dict]]:
        """Get all positions grouped by strategy / 取得所有策略倉位"""
        return {
            sid: acc.positions for sid, acc in self.strategies.items()
        }

    def has_position(self, strategy_id: str, symbol: str) -> bool:
        """Check if strategy holds a symbol / 檢查策略是否持有某幣種"""
        acc = self.strategies.get(strategy_id)
        if not acc:
            return False
        positions = acc.positions.get(symbol, [])
        return len(positions) > 0

    def get_position_count(self, strategy_id: str, symbol: str) -> int:
        """Count open positions for a strategy-symbol pair / 計算策略-幣種的未平倉數"""
        acc = self.strategies.get(strategy_id)
        if not acc:
            return 0
        return len(acc.positions.get(symbol, []))

    def get_total_equity(self) -> float:
        """Total equity across all strategies / 所有策略總權益"""
        total = 0.0
        for acc in self.strategies.values():
            total += acc.balance + sum(
                p.get("quantity", 0) * p.get("entry_price", 0)
                for positions in acc.positions.values()
                for p in positions
            )
        return total

    def get_total_pnl(self) -> float:
        """Total realized + unrealized PnL / 總已實現+未實現損益"""
        return self.get_total_equity() - self.total_initial

    def get_today_realized_pnl(self) -> float:
        """Sum of today's realized PnL across all strategies / 今日所有策略已實現損益"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_pnl = 0.0
        for acc in self.strategies.values():
            for t in acc.trades:
                exit_time = t.get("exit_time", "")
                if exit_time and exit_time.startswith(today):
                    today_pnl += t.get("realized_pnl", 0)
        return today_pnl

    def get_strategy_today_pnl(self, strategy_id: str) -> float:
        """Today's realized PnL for a specific strategy / 指定策略今日已實現損益"""
        today = datetime.now().strftime("%Y-%m-%d")
        acc = self.strategies.get(strategy_id)
        if not acc:
            return 0.0
        return sum(
            t.get("realized_pnl", 0)
            for t in acc.trades
            if t.get("exit_time") and t.get("exit_time").startswith(today)
        )

    def get_strategy_return_pct(self, strategy_id: str) -> float:
        """Return % for a strategy / 策略報酬率"""
        acc = self.strategies.get(strategy_id)
        if not acc or acc.initial == 0:
            return 0.0
        return (acc.balance - acc.initial) / acc.initial * 100

    def enter_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        strategy_id: str,
    ) -> bool:
        """
        Enter a position using strategy's own balance.
        Multiple positions per symbol are allowed.
        Returns True if successful.
        """
        if strategy_id not in self.strategies:
            logger.warning(f"Unknown strategy: {strategy_id}")
            return False

        acc = self.strategies[strategy_id]
        cost = quantity * price
        commission = cost * COMMISSION_RATE
        slippage = cost * SLIPPAGE_RATE
        total_cost = cost + commission + slippage

        if acc.balance < total_cost:
            logger.warning(
                f"[{strategy_id}] Insufficient balance: ${acc.balance:.2f} < ${total_cost:.2f}"
            )
            return False

        # Position size check — total exposure across all positions for this symbol
        existing_exposure = sum(
            p.get("quantity", 0) * p.get("entry_price", 0)
            for p in acc.positions.get(symbol, [])
        )
        total_exposure = existing_exposure + cost
        if total_exposure > acc.balance * MAX_POSITION_RATIO * 2:  # Allow up to 2x single position for multiple entries
            logger.warning(
                f"[{strategy_id}] Total position too large for {symbol}: ${total_exposure:.2f}"
            )
            return False

        acc.balance -= total_cost
        entry_time = datetime.now().isoformat()
        position_id = f"POS_{datetime.now().strftime('%Y%m%d%H%M%S')}_{symbol}_{strategy_id}_{len(acc.positions.get(symbol, []))}"
        position = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": price,
            "entry_time": entry_time,
            "strategy_id": strategy_id,
            "position_id": position_id,
        }
        acc.positions.setdefault(symbol, []).append(position)

        # Record trade entry / 記錄交易進場
        trade_id = f"PT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{symbol}_{strategy_id}"
        trade = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": price,
            "exit_price": None,
            "entry_time": entry_time,
            "exit_time": None,
            "slippage": slippage,
            "commission": commission,
            "realized_pnl": 0.0,
            "strategy_id": strategy_id,
            "position_id": position_id,
        }
        acc.trades.append(trade)

        self._save_state()
        logger.info(
            f"[{strategy_id}] ENTER {side} {symbol} {quantity} @ ${price:,.2f} "
            f"cost=${total_cost:.2f} balance=${acc.balance:.2f} (position_id={position_id})"
        )
        return True

    def exit_position(
        self,
        symbol: str,
        price: float,
        strategy_id: str,
    ) -> Optional[dict]:
        """
        Exit the oldest (FIFO) position for a specific strategy-symbol pair.
        Returns trade dict if successful, None otherwise.
        """
        if strategy_id not in self.strategies:
            logger.warning(f"Unknown strategy: {strategy_id}")
            return None

        acc = self.strategies[strategy_id]
        positions = acc.positions.get(symbol, [])
        if not positions:
            logger.warning(f"[{strategy_id}] No position in {symbol} to exit")
            return None

        # FIFO — exit oldest position / 先進先出 — 平倉最老的一筆
        position = positions[0]
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        side = position["side"]
        position_id = position.get("position_id", "")

        # Calculate PnL / 計算損益
        if side.lower() == "buy":
            raw_pnl = (price - entry_price) * quantity
        else:
            raw_pnl = (entry_price - price) * quantity

        exit_cost = quantity * price
        commission = exit_cost * COMMISSION_RATE
        slippage = exit_cost * SLIPPAGE_RATE
        realized_pnl = raw_pnl - commission - slippage

        # Update balance / 更新餘額
        acc.balance += exit_cost - commission - slippage

        # Update trade record / 更新交易記錄
        # Find the matching open trade (FIFO — oldest unclosed trade for this position)
        open_trade = None
        for t in acc.trades:
            if t["symbol"] == symbol and t["exit_price"] is None and t.get("position_id") == position_id:
                open_trade = t
                break

        if open_trade:
            open_trade["exit_price"] = price
            open_trade["exit_time"] = datetime.now().isoformat()
            open_trade["realized_pnl"] = realized_pnl

        # Remove position / 移除倉位
        positions.pop(0)
        if not positions:
            del acc.positions[symbol]

        self._save_state()
        logger.info(
            f"[{strategy_id}] EXIT {symbol} @ ${price:,.2f} "
            f"PnL=${realized_pnl:+.2f} balance=${acc.balance:.2f} (position_id={position_id})"
        )

        return open_trade

    def force_close_all(self, current_prices: Dict[str, float]) -> Dict[str, list]:
        """
        Force close ALL positions across ALL strategies.
        Called at 23:30 for intraday settlement.
        Returns {strategy_id: [closed_trade, ...]}.
        """
        closed: Dict[str, list] = {}
        today = datetime.now().strftime("%Y-%m-%d")

        for sid, acc in self.strategies.items():
            if not acc.positions:
                continue

            closed[sid] = []
            # Copy symbols because we're modifying dict / 複製 symbols 因為會修改 dict
            for symbol in list(acc.positions.keys()):
                price = current_prices.get(symbol, 0)
                if price <= 0:
                    logger.warning(f"[{sid}] No price for {symbol}, skipping force close")
                    continue

                # Close all positions for this symbol (FIFO loop) / 平倉該幣種所有倉位
                while acc.positions.get(symbol):
                    trade = self.exit_position(symbol, price, sid)
                    if trade:
                        closed[sid].append(trade)
                    else:
                        break

            # Record daily settlement / 記錄當日結算
            if closed[sid]:
                day_pnl = sum(t.get("realized_pnl", 0) for t in closed[sid])
                if today not in self.daily_settlements:
                    self.daily_settlements[today] = {}
                self.daily_settlements[today][sid] = {
                    "realized_pnl": day_pnl,
                    "trades": len(closed[sid]),
                    "balance_after": acc.balance,
                }
                logger.info(f"[{sid}] Daily settlement: ${day_pnl:+.2f} ({len(closed[sid])} trades)")

        self._save_state()
        return closed

    def record_daily_settlement(self, strategy_id: str, realized_pnl: float, trade_count: int):
        """Manually record a daily settlement entry / 手動記錄日結算"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.daily_settlements:
            self.daily_settlements[today] = {}
        acc = self.strategies.get(strategy_id)
        self.daily_settlements[today][strategy_id] = {
            "realized_pnl": realized_pnl,
            "trades": trade_count,
            "balance_after": acc.balance if acc else 0,
        }
        self._save_state()

    def get_daily_settlement(self, date_str: str) -> Dict[str, dict]:
        """Get settlement for a specific date / 取得指定日期結算"""
        return self.daily_settlements.get(date_str, {})

    def get_all_settlements(self) -> Dict[str, Dict[str, dict]]:
        """Get all daily settlements / 取得所有日結算"""
        return self.daily_settlements

    def get_summary(self) -> dict:
        """Get overall summary / 取得總覽"""
        total_balance = sum(acc.balance for acc in self.strategies.values())
        total_pnl = total_balance - self.total_initial
        total_return_pct = (total_pnl / self.total_initial * 100) if self.total_initial else 0
        open_positions = sum(
            len(positions)
            for acc in self.strategies.values()
            for positions in acc.positions.values()
        )

        # Max hold time / 最大持倉時間
        max_hold_hours = 0
        now = datetime.now()
        for acc in self.strategies.values():
            for positions in acc.positions.values():
                for pos in positions:
                    et = pos.get("entry_time")
                    if et:
                        try:
                            entry = datetime.fromisoformat(et)
                            hold = (now - entry).total_seconds() / 3600
                            if hold > max_hold_hours:
                                max_hold_hours = hold
                        except Exception:
                            pass

        today_pnl = self.get_today_realized_pnl()

        return {
            "initial_balance": self.total_initial,
            "current_balance": total_balance,
            "total_pnl": total_pnl,
            "total_return_pct": total_return_pct,
            "open_positions": open_positions,
            "max_hold_hours": max_hold_hours,
            "today_pnl": today_pnl,
            "strategies": {
                sid: {
                    "balance": acc.balance,
                    "initial": acc.initial,
                    "return_pct": (acc.balance - acc.initial) / acc.initial * 100 if acc.initial else 0,
                    "positions": len(acc.positions),
                    "trades": len([t for t in acc.trades if t.get("exit_price")]),
                }
                for sid, acc in self.strategies.items()
            },
        }


# ─── Legacy compatibility / 舊版相容 ───────────────────────────
def create_paper_trading() -> PaperTrading:
    """Factory function for legacy compatibility."""
    return PaperTrading()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pt = PaperTrading()
    print("Paper Trading (Per-Strategy) initialized")
    print(f"Strategies: {list(pt.strategies.keys())}")
    print(f"Total initial: ${pt.total_initial:,.2f}")
    print(f"Summary: {pt.get_summary()}")
