"""
Backtest Module / 回測模組

BTC/ETH Strategy Backtesting System
BTC/ETH 策略回測系統

⚠️  ANALYSIS ONLY / 僅分析用途
⚠️  Past performance does not guarantee future results / 過去績效不保證未來結果

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-14
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path

# Import project paths
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.paths import PROJECT_ROOT, STATE_DIR

# Lazy imports to avoid circular dependency
# from app.monitor_runner import MonitorRunner
# from data.fetcher import BinanceFetcher
# from indicators import calculator as indicator_calc
from signals.engine import SignalEngine


class TradeDirection(Enum):
    """Trade direction / 交易方向"""
    LONG = "long"
    SHORT = "short"


class TradeResult(Enum):
    """Trade result status / 交易結果狀態"""
    OPEN = "open"
    CLOSED_PROFIT = "closed_profit"
    CLOSED_LOSS = "closed_loss"


@dataclass
class TradeRecord:
    """Single trade record / 單筆交易記錄"""
    trade_id: str
    symbol: str
    direction: str  # "long" or "short"
    entry_time: str  # ISO format
    entry_price: float
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    quantity: float = 1.0  # Standardized to 1 unit for P&L % calculation
    pnl_pct: Optional[float] = None  # Profit/Loss percentage
    pnl_amount: Optional[float] = None  # Absolute P&L
    result: str = "open"  # "open", "closed_profit", "closed_loss"
    exit_reason: Optional[str] = None  # "signal", "stop_loss", "take_profit", "end_of_test"


@dataclass
class BacktestSummary:
    """Backtest run summary / 回測執行摘要"""
    backtest_id: str
    start_date: str
    end_date: str
    symbols: List[str]
    strategy: str
    
    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # Returns
    total_return_pct: float = 0.0
    cumulative_return_pct: float = 0.0
    
    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_start: Optional[str] = None
    max_drawdown_end: Optional[str] = None
    
    # Per-symbol breakdown
    symbol_stats: Dict[str, Any] = None
    
    # Equity curve data points
    equity_curve: List[Dict[str, Any]] = None


@dataclass
class BacktestConfig:
    """Backtest configuration / 回測配置"""
    symbols: List[str]
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    strategy: str = "ma_cross"  # Strategy to test
    strategy_id: Optional[str] = None  # Strategy ID from strategies.json / 策略ID
    strategy_type: Optional[str] = None  # Strategy type / 策略類型
    initial_capital: float = 10000.0
    position_size_pct: float = 100.0  # Use full capital per trade
    
    # Exit conditions
    stop_loss_pct: Optional[float] = None  # e.g., 5.0 for 5% stop loss
    take_profit_pct: Optional[float] = None  # e.g., 10.0 for 10% take profit
    
    # Commission
    commission_pct: float = 0.0  # e.g., 0.1 for 0.1% per trade (entry + exit)
    
    # Time-based exit
    max_holding_periods: Optional[int] = None  # Max candles to hold


class BacktestStorage:
    """
    Backtest result storage manager
    回測結果儲存管理器
    """
    
    def __init__(self, backtest_dir: Optional[Path] = None):
        self.backtest_dir = backtest_dir or (PROJECT_ROOT / "backtest")
        self.results_file = self.backtest_dir / "backtest_results.jsonl"
        self.trades_file = self.backtest_dir / "trade_history.jsonl"
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories / 建立必要目錄"""
        self.backtest_dir.mkdir(parents=True, exist_ok=True)
    
    def save_backtest_result(self, summary: BacktestSummary) -> None:
        """
        Save backtest summary to JSONL
        儲存回測摘要到 JSONL
        """
        try:
            record = {
                "type": "summary",
                "timestamp": datetime.now().isoformat(),
                "data": asdict(summary)
            }
            
            with open(self.results_file, 'a') as f:
                f.write(json.dumps(record) + '\n')
                
        except Exception as e:
            print(f"Error saving backtest result: {e}")
    
    def save_trade(self, trade: TradeRecord) -> None:
        """
        Save individual trade to JSONL
        儲存單筆交易到 JSONL
        """
        try:
            record = {
                "type": "trade",
                "timestamp": datetime.now().isoformat(),
                "data": asdict(trade)
            }
            
            with open(self.trades_file, 'a') as f:
                f.write(json.dumps(record) + '\n')
                
        except Exception as e:
            print(f"Error saving trade: {e}")
    
    def get_latest_backtests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get latest backtest results
        取得最新回測結果
        
        Returns:
            List of backtest summaries
        """
        results = []
        
        try:
            if not self.results_file.exists():
                return results
            
            with open(self.results_file, 'r') as f:
                lines = f.readlines()
            
            # Read from end to get latest
            for line in reversed(lines[-limit:]):
                try:
                    record = json.loads(line.strip())
                    if record.get("type") == "summary":
                        results.append(record["data"])
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"Error reading backtest results: {e}")
        
        return results
    
    def get_trades_for_backtest(self, backtest_id: str) -> List[Dict[str, Any]]:
        """
        Get all trades for a specific backtest
        取得特定回測的所有交易
        """
        trades = []
        
        try:
            if not self.trades_file.exists():
                return trades
            
            with open(self.trades_file, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        if record.get("type") == "trade":
                            trade_data = record["data"]
                            if trade_data.get("trade_id", "").startswith(backtest_id):
                                trades.append(trade_data)
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            print(f"Error reading trades: {e}")
        
        return trades


# Export classes
__all__ = [
    'BacktestConfig',
    'BacktestSummary', 
    'BacktestStorage',
    'TradeRecord',
    'TradeDirection',
    'TradeResult'
]
