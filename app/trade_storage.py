"""
Trade Data Persistence
PostgreSQL-based trade record storage, query, and backup system.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class TradeStatus(Enum):
    """Trade execution status."""

    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradeType(Enum):
    """Trade direction."""

    BUY = "buy"
    SELL = "sell"


@dataclass
class TradeRecord:
    """Single trade record."""

    trade_id: str
    symbol: str
    side: TradeType
    status: TradeStatus

    # Order details
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    leverage: float = 1.0

    # P&L
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    pnl_percent: float = 0.0
    fee: float = 0.0

    # Strategy
    strategy: str = ""
    signal_id: str = ""

    # Risk
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0

    # Timestamps
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Metadata
    metadata: Dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "status": self.status.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "leverage": self.leverage,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "pnl_percent": self.pnl_percent,
            "fee": self.fee,
            "strategy": self.strategy,
            "signal_id": self.signal_id,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward": self.risk_reward,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TradeRecord":
        """Create TradeRecord from dict."""
        record = cls(
            trade_id=data["trade_id"],
            symbol=data["symbol"],
            side=TradeType(data["side"]),
            status=TradeStatus(data["status"]),
            entry_price=data.get("entry_price", 0),
            exit_price=data.get("exit_price", 0),
            quantity=data.get("quantity", 0),
            leverage=data.get("leverage", 1),
            realized_pnl=data.get("realized_pnl", 0),
            unrealized_pnl=data.get("unrealized_pnl", 0),
            pnl_percent=data.get("pnl_percent", 0),
            fee=data.get("fee", 0),
            strategy=data.get("strategy", ""),
            signal_id=data.get("signal_id", ""),
            stop_loss=data.get("stop_loss", 0),
            take_profit=data.get("take_profit", 0),
            risk_reward=data.get("risk_reward", 0),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )

        if data.get("entry_time"):
            record.entry_time = datetime.fromisoformat(data["entry_time"])
        if data.get("exit_time"):
            record.exit_time = datetime.fromisoformat(data["exit_time"])
        if data.get("created_at"):
            record.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            record.updated_at = datetime.fromisoformat(data["updated_at"])

        return record


class TradeStorage:
    """
    Trade data persistence layer.
    Manages trade records with PostgreSQL backend.
    """

    def __init__(self, db_config: Optional[Dict] = None):
        self.logger = logging.getLogger(__name__)

        # Database config
        self.db_config = db_config or {
            "host": "localhost",
            "port": 5432,
            "database": "trading",
            "user": "trader",
            "password": "",
        }

        # In-memory cache (before DB migration)
        self.trades: Dict[str, TradeRecord] = {}
        self.trade_history: List[str] = []
        self.max_cache = 10000

        # Stats
        self.total_trades = 0
        self.total_pnl = 0.0

        self.logger.info("TradeStorage initialized (PostgreSQL-ready)")

    def add_trade(self, trade: TradeRecord) -> bool:
        """
        Add new trade record.

        Args:
            trade: TradeRecord to store

        Returns:
            True if added successfully
        """
        trade.created_at = datetime.now()
        trade.updated_at = datetime.now()

        self.trades[trade.trade_id] = trade
        self.trade_history.append(trade.trade_id)

        # Maintain cache size
        if len(self.trade_history) > self.max_cache:
            old_id = self.trade_history.pop(0)
            if old_id in self.trades:
                del self.trades[old_id]

        self.total_trades += 1

        self.logger.info(f"Trade added: {trade.trade_id} ({trade.symbol} {trade.side.value} " f"@{trade.entry_price})")

        return True

    def update_trade(self, trade_id: str, updates: Dict) -> bool:
        """
        Update existing trade.

        Args:
            trade_id: Trade to update
            updates: Dict of fields to update

        Returns:
            True if updated
        """
        if trade_id not in self.trades:
            self.logger.warning(f"Trade not found: {trade_id}")
            return False

        trade = self.trades[trade_id]

        # Update fields
        for key, value in updates.items():
            if hasattr(trade, key):
                setattr(trade, key, value)

        trade.updated_at = datetime.now()

        self.logger.info(f"Trade updated: {trade_id}")
        return True

    def close_trade(
        self, trade_id: str, exit_price: float, exit_time: Optional[datetime] = None
    ) -> Optional[TradeRecord]:
        """
        Close a trade and calculate P&L.

        Args:
            trade_id: Trade to close
            exit_price: Exit price
            exit_time: Exit timestamp

        Returns:
            Updated TradeRecord or None
        """
        if trade_id not in self.trades:
            return None

        trade = self.trades[trade_id]
        trade.exit_price = exit_price
        trade.exit_time = exit_time or datetime.now()
        trade.status = TradeStatus.CLOSED

        # Calculate P&L
        if trade.side == TradeType.BUY:
            trade.realized_pnl = (exit_price - trade.entry_price) * trade.quantity
        else:
            trade.realized_pnl = (trade.entry_price - exit_price) * trade.quantity

        trade.pnl_percent = (
            (trade.realized_pnl / (trade.entry_price * trade.quantity)) * 100 if trade.entry_price else 0
        )

        # Net P&L after fees
        trade.realized_pnl -= trade.fee
        self.total_pnl += trade.realized_pnl

        trade.updated_at = datetime.now()

        self.logger.info(f"Trade closed: {trade_id} P&L=${trade.realized_pnl:.2f} " f"({trade.pnl_percent:+.2f}%)")

        return trade

    def get_trade(self, trade_id: str) -> Optional[TradeRecord]:
        """Get single trade."""
        return self.trades.get(trade_id)

    def get_trades(
        self,
        symbol: Optional[str] = None,
        status: Optional[TradeStatus] = None,
        strategy: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[TradeRecord]:
        """
        Query trades with filters.

        Args:
            symbol: Filter by symbol
            status: Filter by status
            strategy: Filter by strategy
            start_time: Filter by entry time
            end_time: Filter by entry time
            limit: Max results

        Returns:
            List of matching TradeRecords
        """
        results = list(self.trades.values())

        if symbol:
            results = [t for t in results if t.symbol == symbol.upper()]

        if status:
            results = [t for t in results if t.status == status]

        if strategy:
            results = [t for t in results if t.strategy == strategy]

        if start_time:
            results = [t for t in results if t.entry_time and t.entry_time >= start_time]

        if end_time:
            results = [t for t in results if t.entry_time and t.entry_time <= end_time]

        # Sort by entry time descending
        results.sort(key=lambda t: t.entry_time or datetime.min, reverse=True)

        return results[:limit]

    def get_open_trades(self) -> List[TradeRecord]:
        """Get all open trades."""
        return [t for t in self.trades.values() if t.status == TradeStatus.OPEN]

    def get_pnl_summary(self, symbol: Optional[str] = None, days: int = 30) -> Dict:
        """
        Get P&L summary.

        Args:
            symbol: Filter by symbol
            days: Lookback period

        Returns:
            P&L statistics
        """
        cutoff = datetime.now() - timedelta(days=days)

        trades = self.get_trades(symbol=symbol, start_time=cutoff)
        closed_trades = [t for t in trades if t.status == TradeStatus.CLOSED]

        if not closed_trades:
            return {"total_trades": 0, "total_pnl": 0}

        pnls = [t.realized_pnl for t in closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        return {
            "total_trades": len(closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(closed_trades) * 100,
            "total_pnl": sum(pnls),
            "gross_profit": sum(wins) if wins else 0,
            "gross_loss": sum(losses) if losses else 0,
            "avg_pnl": sum(pnls) / len(pnls),
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(losses) / len(losses) if losses else 0,
            "max_win": max(pnls) if pnls else 0,
            "max_loss": min(pnls) if pnls else 0,
            "profit_factor": abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float("inf"),
        }

    def get_strategy_performance(self, days: int = 30) -> Dict[str, Dict]:
        """Get performance by strategy."""
        cutoff = datetime.now() - timedelta(days=days)
        trades = self.get_trades(start_time=cutoff)

        strategies = {}
        for trade in trades:
            if trade.strategy not in strategies:
                strategies[trade.strategy] = []
            strategies[trade.strategy].append(trade)

        results = {}
        for strategy, trades_list in strategies.items():
            closed = [t for t in trades_list if t.status == TradeStatus.CLOSED]
            pnls = [t.realized_pnl for t in closed]

            results[strategy] = {
                "total_trades": len(trades_list),
                "closed_trades": len(closed),
                "total_pnl": sum(pnls),
                "win_rate": len([p for p in pnls if p > 0]) / len(pnls) * 100 if pnls else 0,
            }

        return results

    def export_trades(self, filepath: str, symbol: Optional[str] = None, days: int = 30):
        """Export trades to JSON."""
        cutoff = datetime.now() - timedelta(days=days)
        trades = self.get_trades(symbol=symbol, start_time=cutoff)

        data = {
            "exported_at": datetime.now().isoformat(),
            "symbol": symbol,
            "days": days,
            "count": len(trades),
            "trades": [t.to_dict() for t in trades],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Trades exported to {filepath}")

    def import_trades(self, filepath: str) -> int:
        """Import trades from JSON."""
        with open(filepath, "r") as f:
            data = json.load(f)

        count = 0
        for trade_data in data.get("trades", []):
            try:
                trade = TradeRecord.from_dict(trade_data)
                self.add_trade(trade)
                count += 1
            except Exception as e:
                self.logger.error(f"Import error: {e}")

        self.logger.info(f"Imported {count} trades from {filepath}")
        return count

    def backup(self, filepath: str):
        """Create full backup."""
        data = {
            "backup_at": datetime.now().isoformat(),
            "total_trades": len(self.trades),
            "total_pnl": self.total_pnl,
            "trades": [t.to_dict() for t in self.trades.values()],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Backup created: {filepath}")

    def get_stats(self) -> Dict:
        """Get storage statistics."""
        open_trades = len(self.get_open_trades())
        closed_trades = len([t for t in self.trades.values() if t.status == TradeStatus.CLOSED])

        return {
            "total_trades": len(self.trades),
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "cached_history": len(self.trade_history),
            "total_pnl": self.total_pnl,
            "storage_type": "memory_cache",
            "postgresql_ready": True,
        }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    storage = TradeStorage()

    # Add sample trades
    trades = [
        TradeRecord(
            trade_id="T001",
            symbol="BTCUSDT",
            side=TradeType.BUY,
            status=TradeStatus.CLOSED,
            entry_price=45000,
            quantity=0.1,
            strategy="BTC_4H_MA",
            stop_loss=43000,
            take_profit=48000,
            fee=2.25,
        ),
        TradeRecord(
            trade_id="T002",
            symbol="ETHUSDT",
            side=TradeType.BUY,
            status=TradeStatus.OPEN,
            entry_price=3200,
            quantity=1.5,
            strategy="ETH_1H_RSI",
            stop_loss=3000,
            take_profit=3500,
            fee=4.8,
        ),
    ]

    for trade in trades:
        trade.entry_time = datetime.now() - timedelta(hours=2)
        storage.add_trade(trade)

    # Close first trade
    storage.close_trade("T001", 47500)

    # Query
    print("Trade Storage Demo")
    print("=" * 50)
    print(f"Total trades: {len(storage.trades)}")
    print(f"Open trades: {len(storage.get_open_trades())}")

    # P&L
    pnl = storage.get_pnl_summary()
    print(f"\nP&L Summary:")
    print(f"  Total P&L: ${pnl['total_pnl']:.2f}")
    print(f"  Win Rate: {pnl['win_rate']:.1f}%")
    print(f"  Trades: {pnl['total_trades']}")

    # Stats
    print(f"\nStats: {storage.get_stats()}")
