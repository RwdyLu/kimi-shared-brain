"""
Backtest Runner / 回測執行器

Historical backtesting engine for BTC/ETH strategies.
BTC/ETH 策略的歷史回測引擎。

⚠️  ANALYSIS ONLY / 僅分析用途
⚠️  Past performance does not guarantee future results

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-14
"""

from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np

from backtest import (
    BacktestConfig, BacktestSummary, BacktestStorage, 
    TradeRecord, TradeDirection, TradeResult
)
from data.fetcher import BinanceFetcher
from indicators import calculator as indicator_calc
from signals.engine import SignalEngine
from config.paths import PROJECT_ROOT


class BacktestRunner:
    """
    Backtest execution engine
    回測執行引擎
    """
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.storage = BacktestStorage()
        
        # Initialize components
        self.fetcher = BinanceFetcher()
        self.signal_engine = SignalEngine()
        
        # State tracking
        self.active_trades: Dict[str, TradeRecord] = {}  # symbol -> TradeRecord
        self.closed_trades: List[TradeRecord] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.current_equity: float = config.initial_capital
        self.peak_equity: float = config.initial_capital
        self.max_drawdown: float = 0.0
        self.drawdown_start: Optional[str] = None
        
        # Generate backtest ID
        self.backtest_id = f"BT{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    def run(self) -> BacktestSummary:
        """
        Execute the backtest
        執行回測
        """
        print(f"\n{'='*70}")
        print(f"🔄 BACKTEST START / 回測開始")
        print(f"{'='*70}")
        print(f"Backtest ID: {self.backtest_id}")
        print(f"Period: {self.config.start_date} ~ {self.config.end_date}")
        print(f"Symbols: {', '.join(self.config.symbols)}")
        print(f"Initial Capital: ${self.config.initial_capital:,.2f}")
        print(f"{'='*70}\n")
        
        # Process each symbol
        for symbol in self.config.symbols:
            self._backtest_symbol(symbol)
        
        # Close any remaining open trades at end of test
        self._close_all_trades("end_of_test")
        
        # Build and save summary
        summary = self._build_summary()
        self.storage.save_backtest_result(summary)
        
        # Print results
        self._print_results(summary)
        
        return summary
    
    def _backtest_symbol(self, symbol: str) -> None:
        """
        Run backtest for a single symbol
        對單一標的執行回測
        """
        print(f"\n📊 Processing {symbol}...")
        
        # Fetch historical data
        try:
            df = self._fetch_historical_data(symbol)
            if df is None or len(df) == 0:
                print(f"   ⚠️ No data available for {symbol}")
                return
            print(f"   ✓ Loaded {len(df)} candles")
        except Exception as e:
            print(f"   ✗ Error fetching data: {e}")
            return
        
        # Process each candle
        for idx, row in df.iterrows():
            timestamp = idx.strftime('%Y-%m-%d %H:%M')
            current_price = row['close']
            
            # Check for exit conditions on active trade
            if symbol in self.active_trades:
                self._check_exit_conditions(symbol, timestamp, current_price, row)
            
            # Check for entry signals (only if no active trade)
            if symbol not in self.active_trades:
                self._check_entry_signals(symbol, timestamp, current_price, row)
            
            # Update equity curve
            self._update_equity_curve(timestamp)
    
    def _fetch_historical_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch historical kline data
        取得歷史 K 線資料
        """
        # Convert dates to timestamps
        start_dt = datetime.strptime(self.config.start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(self.config.end_date, '%Y-%m-%d') + timedelta(days=1)
        
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)
        
        # Fetch from Binance
        klines = self.fetcher.get_historical_klines(
            symbol=symbol,
            interval="4h",  # Default to 4h for consistency with live monitoring
            start_time=start_ms,
            end_time=end_ms
        )
        
        if not klines:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # Convert types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # Calculate indicators using module functions
        df['MA5'] = indicator_calc.calculate_ma5(df['close'].tolist())
        df['MA20'] = indicator_calc.calculate_ma20(df['close'].tolist())
        df['MA240'] = indicator_calc.calculate_ma240(df['close'].tolist())
        
        return df
    
    def _check_entry_signals(self, symbol: str, timestamp: str, price: float, row: pd.Series) -> None:
        """
        Check for entry signals and open trades
        檢查進場訊號並開倉
        """
        # Prepare indicator data
        indicators = {
            'MA5': row.get('MA5'),
            'MA20': row.get('MA20'),
            'MA240': row.get('MA240'),
            'volume': row.get('volume'),
            'volume_MA20': row.get('volume_MA20')
        }
        
        # Get signals from engine
        signals = self.signal_engine.generate_signals(indicators)
        
        for signal in signals:
            if signal.status.value == "confirmed":
                # Open trade
                direction = TradeDirection.LONG if "LONG" in signal.signal_type.name else TradeDirection.SHORT
                
                trade = TradeRecord(
                    trade_id=f"{self.backtest_id}_{symbol}_{len(self.closed_trades)}",
                    symbol=symbol,
                    direction=direction.value,
                    entry_time=timestamp,
                    entry_price=price,
                    quantity=1.0
                )
                
                self.active_trades[symbol] = trade
                self.storage.save_trade(trade)
                
                print(f"   ➡️  ENTRY: {direction.value.upper()} @ ${price:,.2f} ({timestamp})")
                break
    
    def _check_exit_conditions(self, symbol: str, timestamp: str, price: float, row: pd.Series) -> None:
        """
        Check for exit conditions and close trades
        檢查出場條件並平倉
        """
        trade = self.active_trades[symbol]
        
        exit_triggered = False
        exit_price = price
        exit_reason = "signal"
        
        # Check stop loss
        if self.config.stop_loss_pct:
            if trade.direction == "long":
                stop_price = trade.entry_price * (1 - self.config.stop_loss_pct / 100)
                if price <= stop_price:
                    exit_triggered = True
                    exit_price = stop_price
                    exit_reason = "stop_loss"
            else:  # short
                stop_price = trade.entry_price * (1 + self.config.stop_loss_pct / 100)
                if price >= stop_price:
                    exit_triggered = True
                    exit_price = stop_price
                    exit_reason = "stop_loss"
        
        # Check take profit
        if not exit_triggered and self.config.take_profit_pct:
            if trade.direction == "long":
                tp_price = trade.entry_price * (1 + self.config.take_profit_pct / 100)
                if price >= tp_price:
                    exit_triggered = True
                    exit_price = tp_price
                    exit_reason = "take_profit"
            else:  # short
                tp_price = trade.entry_price * (1 - self.config.take_profit_pct / 100)
                if price <= tp_price:
                    exit_triggered = True
                    exit_price = tp_price
                    exit_reason = "take_profit"
        
        # Check reverse signal (optional exit)
        if not exit_triggered:
            indicators = {
                'MA5': row.get('MA5'),
                'MA20': row.get('MA20'),
                'MA240': row.get('MA240'),
            }
            signals = self.signal_engine.generate_signals(indicators)
            
            for signal in signals:
                # Close on opposite direction signal
                is_long_signal = "LONG" in signal.signal_type.name
                if (trade.direction == "long" and not is_long_signal) or \
                   (trade.direction == "short" and is_long_signal):
                    exit_triggered = True
                    exit_reason = "reverse_signal"
                    break
        
        if exit_triggered:
            self._close_trade(symbol, timestamp, exit_price, exit_reason)
    
    def _close_trade(self, symbol: str, exit_time: str, exit_price: float, reason: str) -> None:
        """
        Close an active trade
        平倉
        """
        trade = self.active_trades.pop(symbol)
        
        trade.exit_time = exit_time
        trade.exit_price = exit_price
        trade.exit_reason = reason
        
        # Calculate P&L
        if trade.direction == "long":
            trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
        else:  # short
            trade.pnl_pct = ((trade.entry_price - exit_price) / trade.entry_price) * 100
        
        trade.pnl_amount = (trade.pnl_pct / 100) * self.config.initial_capital * (self.config.position_size_pct / 100)
        
        if trade.pnl_pct >= 0:
            trade.result = TradeResult.CLOSED_PROFIT.value
            emoji = "✅"
        else:
            trade.result = TradeResult.CLOSED_LOSS.value
            emoji = "❌"
        
        self.closed_trades.append(trade)
        self.storage.save_trade(trade)
        
        # Update equity
        self.current_equity += trade.pnl_amount
        
        print(f"   {emoji} EXIT: ${exit_price:,.2f} | P&L: {trade.pnl_pct:+.2f}% ({reason})")
    
    def _close_all_trades(self, reason: str) -> None:
        """
        Close all active trades at end of backtest
        回測結束時平倉所有持倉
        """
        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            self._close_trade(symbol, "end_of_test", trade.entry_price, reason)
    
    def _update_equity_curve(self, timestamp: str) -> None:
        """
        Update equity curve tracking
        更新權益曲線
        """
        self.equity_curve.append({
            "timestamp": timestamp,
            "equity": self.current_equity
        })
        
        # Track drawdown
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
            self.drawdown_start = None
        else:
            drawdown = (self.peak_equity - self.current_equity) / self.peak_equity * 100
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
                if self.drawdown_start is None:
                    self.drawdown_start = timestamp
    
    def _build_summary(self) -> BacktestSummary:
        """
        Build backtest summary statistics
        建立回測摘要統計
        """
        total_trades = len(self.closed_trades)
        winning_trades = sum(1 for t in self.closed_trades if t.pnl_pct and t.pnl_pct > 0)
        losing_trades = total_trades - winning_trades
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        total_return = ((self.current_equity - self.config.initial_capital) / self.config.initial_capital) * 100
        
        # Symbol breakdown
        symbol_stats = {}
        for symbol in self.config.symbols:
            symbol_trades = [t for t in self.closed_trades if t.symbol == symbol]
            if symbol_trades:
                symbol_stats[symbol] = {
                    "total_trades": len(symbol_trades),
                    "winning_trades": sum(1 for t in symbol_trades if t.pnl_pct and t.pnl_pct > 0),
                    "total_pnl_pct": sum(t.pnl_pct for t in symbol_trades if t.pnl_pct)
                }
        
        return BacktestSummary(
            backtest_id=self.backtest_id,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            symbols=self.config.symbols,
            strategy=self.config.strategy,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return_pct=total_return,
            cumulative_return_pct=total_return,
            max_drawdown_pct=self.max_drawdown,
            max_drawdown_start=self.drawdown_start,
            symbol_stats=symbol_stats,
            equity_curve=self.equity_curve
        )
    
    def _print_results(self, summary: BacktestSummary) -> None:
        """
        Print backtest results to console
        印出回測結果
        """
        print(f"\n{'='*70}")
        print(f"📊 BACKTEST RESULTS / 回測結果")
        print(f"{'='*70}")
        print(f"Backtest ID: {summary.backtest_id}")
        print(f"Period: {summary.start_date} ~ {summary.end_date}")
        print(f"{'='*70}")
        
        print(f"\n💰 PERFORMANCE / 績效")
        print(f"   Initial Capital: ${self.config.initial_capital:,.2f}")
        print(f"   Final Equity:    ${self.current_equity:,.2f}")
        print(f"   Total Return:    {summary.total_return_pct:+.2f}%")
        
        print(f"\n📈 TRADE STATISTICS / 交易統計")
        print(f"   Total Trades:    {summary.total_trades}")
        print(f"   Winning Trades:  {summary.winning_trades}")
        print(f"   Losing Trades:   {summary.losing_trades}")
        print(f"   Win Rate:        {summary.win_rate:.1f}%")
        
        print(f"\n⚠️  RISK METRICS / 風險指標")
        print(f"   Max Drawdown:    {summary.max_drawdown_pct:.2f}%")
        
        print(f"\n📊 SYMBOL BREAKDOWN / 標的明細")
        for symbol, stats in summary.symbol_stats.items():
            print(f"   {symbol}: {stats['total_trades']} trades, {stats['total_pnl_pct']:+.2f}%")
        
        print(f"\n{'='*70}")
        print(f"✅ BACKTEST COMPLETE / 回測完成")
        print(f"{'='*70}\n")


def run_backtest(
    symbols: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 10000.0,
    stop_loss_pct: Optional[float] = None,
    take_profit_pct: Optional[float] = None
) -> BacktestSummary:
    """
    Convenience function to run a backtest
    執行回測的便捷函數
    
    Args:
        symbols: List of symbols to test (default: ["BTCUSDT", "ETHUSDT"])
        start_date: Start date (YYYY-MM-DD, default: 30 days ago)
        end_date: End date (YYYY-MM-DD, default: today)
        initial_capital: Starting capital
        stop_loss_pct: Stop loss percentage (e.g., 5.0 for 5%)
        take_profit_pct: Take profit percentage (e.g., 10.0 for 10%)
    
    Returns:
        BacktestSummary with results
    """
    # Set defaults
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Create config
    config = BacktestConfig(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct
    )
    
    # Run backtest
    runner = BacktestRunner(config)
    return runner.run()


if __name__ == "__main__":
    # Example usage
    summary = run_backtest(
        symbols=["BTCUSDT", "ETHUSDT"],
        start_date="2024-01-01",
        end_date="2024-01-31",
        initial_capital=10000.0,
        stop_loss_pct=5.0,
        take_profit_pct=10.0
    )
    
    print(f"\nBacktest saved with ID: {summary.backtest_id}")
