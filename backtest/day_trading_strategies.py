#!/usr/bin/env python3
"""
Day Trading Strategies Backtest
日內交易策略回測

3 strategies designed for daily close-out (no overnight positions):
- Strategy A: Opening Range Breakout
- Strategy B: VWAP Reversion
- Strategy C: RSI + MACD Dual Confirmation

Target: +0.1% ~ +0.3% daily after fees
Stop loss: -1%, Take profit: +1.5%
Fee: 0.1% per trade (Binance taker)
Position: $1,000 per trade
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

from data.fetcher import BinanceFetcher
from config.paths import PROJECT_ROOT


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    direction: str = "long"  # "long" or "short"
    pnl_pct: float = 0.0
    pnl_amount: float = 0.0
    exit_reason: str = ""
    fees: float = 0.0


class DayTradingBacktest:
    """Day trading backtest engine for intraday strategies"""
    
    def __init__(self, symbol: str, timeframe: str = "15m", days: int = 30):
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.fetcher = BinanceFetcher()
        
        # Trading parameters
        self.position_size = 1000.0  # $1,000 per trade
        self.fee_rate = 0.001  # 0.1% per side
        self.stop_loss_pct = 0.01  # -1%
        self.take_profit_pct = 0.015  # +1.5%
        
        self.trades: List[Trade] = []
        self.daily_pnl: Dict[str, float] = {}  # date -> pnl
        
    def fetch_data(self) -> pd.DataFrame:
        """Fetch historical OHLCV data"""
        end = datetime.now()
        start = end - timedelta(days=self.days)
        
        print(f"📊 Fetching {self.symbol} {self.timeframe} data ({self.days} days)...")
        
        # Calculate required candles
        if self.timeframe == "15m":
            candles_per_day = 96  # 24 * 4
        elif self.timeframe == "1h":
            candles_per_day = 24
        else:
            candles_per_day = 96
            
        limit = min(self.days * candles_per_day, 1000)
        
        try:
            klines = self.fetcher.get_klines(
                symbol=self.symbol,
                interval=self.timeframe,
                limit=limit
            )
            
            # Convert to DataFrame
            data = []
            for k in klines:
                data.append({
                    'timestamp': datetime.fromtimestamp(k.timestamp / 1000),
                    'open': k.open,
                    'high': k.high,
                    'low': k.low,
                    'close': k.close,
                    'volume': k.volume
                })
            
            df = pd.DataFrame(data)
            if len(df) > 0:
                df.set_index('timestamp', inplace=True)
            
            if df is None or len(df) == 0:
                print(f"⚠️ No data fetched for {self.symbol}")
                return pd.DataFrame()
                
            print(f"✅ Fetched {len(df)} candles")
            return df
            
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        if len(df) == 0:
            return df
            
        # VWAP
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = typical_price.cumsum() / df['volume'].cumsum()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # EMAs
        df['ema5'] = df['close'].ewm(span=5).mean()
        df['ema10'] = df['close'].ewm(span=10).mean()
        
        # 20-period high
        df['high_20'] = df['high'].rolling(window=20).max()
        df['low_20'] = df['low'].rolling(window=20).min()
        
        return df
    
    def run_strategy_a_opening_range_breakout(self, df: pd.DataFrame) -> List[Trade]:
        """
        Strategy A: Opening Range Breakout
        - First 15-min candle high/low as range
        - Break above high -> long, break below low -> short
        - Stop: 0.5% against breakout, Take profit: 1.5x range
        """
        trades = []
        
        # Group by trading day
        df['date'] = df.index.date if hasattr(df.index, 'date') else df['timestamp'].dt.date
        
        for date, day_df in df.groupby('date'):
            if len(day_df) < 2:
                continue
                
            # First candle defines the range
            first = day_df.iloc[0]
            or_high = first['high']
            or_low = first['low']
            or_range = or_high - or_low
            
            if or_range == 0:
                continue
                
            # Rest of the day
            rest = day_df.iloc[1:]
            
            for i in range(len(rest)):
                candle = rest.iloc[i]
                
                # Check for breakout
                if candle['close'] > or_high:
                    # Long entry
                    entry_price = candle['close']
                    stop_price = entry_price * (1 - 0.005)  # 0.5% stop
                    tp_price = entry_price + (or_range * 1.5)
                    
                    # Simulate holding until exit
                    holding = rest.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for j in range(len(holding)):
                        h = holding.iloc[j]
                        
                        # Check stop loss
                        if h['low'] <= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                            
                        # Check take profit
                        if h['high'] >= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        # Close at end of day
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trade = self._create_trade(
                        entry_time=candle.name if hasattr(candle, 'name') else candle['timestamp'],
                        entry_price=entry_price,
                        exit_price=exit_price,
                        direction="long",
                        exit_reason=exit_reason
                    )
                    trades.append(trade)
                    break  # One trade per day
                    
                elif candle['close'] < or_low:
                    # Short entry
                    entry_price = candle['close']
                    stop_price = entry_price * (1 + 0.005)
                    tp_price = entry_price - (or_range * 1.5)
                    
                    holding = rest.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for j in range(len(holding)):
                        h = holding.iloc[j]
                        
                        if h['high'] >= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                            
                        if h['low'] <= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trade = self._create_trade(
                        entry_time=candle.name if hasattr(candle, 'name') else candle['timestamp'],
                        entry_price=entry_price,
                        exit_price=exit_price,
                        direction="short",
                        exit_reason=exit_reason
                    )
                    trades.append(trade)
                    break
        
        return trades
    
    def run_strategy_b_vwap_reversion(self, df: pd.DataFrame) -> List[Trade]:
        """
        Strategy B: VWAP Reversion
        - Price deviates > 0.8% from VWAP -> counter-trend entry
        - Exit when price returns to VWAP
        - Stop: deviation > 1.5%
        """
        trades = []
        in_trade = False
        entry_price = 0
        direction = ""
        entry_time = None
        
        for i in range(1, len(df)):
            if in_trade:
                # Check exit conditions
                current = df.iloc[i]
                
                # Stop loss: deviation exceeded 1.5%
                deviation = abs(current['close'] - current['vwap']) / current['vwap']
                
                if direction == "long":
                    if deviation > 0.015:
                        # Stop loss hit
                        exit_price = current['close']
                        trade = self._create_trade(entry_time, entry_price, exit_price, "long", "stop_loss")
                        trades.append(trade)
                        in_trade = False
                    elif current['close'] >= current['vwap']:
                        # Returned to VWAP
                        exit_price = current['vwap']
                        trade = self._create_trade(entry_time, entry_price, exit_price, "long", "vwap_return")
                        trades.append(trade)
                        in_trade = False
                        
                else:  # short
                    if deviation > 0.015:
                        exit_price = current['close']
                        trade = self._create_trade(entry_time, entry_price, exit_price, "short", "stop_loss")
                        trades.append(trade)
                        in_trade = False
                    elif current['close'] <= current['vwap']:
                        exit_price = current['vwap']
                        trade = self._create_trade(entry_time, entry_price, exit_price, "short", "vwap_return")
                        trades.append(trade)
                        in_trade = False
                        
            else:
                # Check entry conditions
                current = df.iloc[i]
                prev = df.iloc[i-1]
                
                # Price must have deviated > 0.8% from VWAP
                deviation = abs(current['close'] - current['vwap']) / current['vwap']
                
                if deviation > 0.008:
                    if current['close'] < current['vwap']:
                        # Price below VWAP -> go long
                        entry_price = current['close']
                        entry_time = current.name if hasattr(current, 'name') else current['timestamp']
                        direction = "long"
                        in_trade = True
                        
                    elif current['close'] > current['vwap']:
                        # Price above VWAP -> go short
                        entry_price = current['close']
                        entry_time = current.name if hasattr(current, 'name') else current['timestamp']
                        direction = "short"
                        in_trade = True
        
        return trades
    
    def run_strategy_c_rsi_macd(self, df: pd.DataFrame) -> List[Trade]:
        """
        Strategy C: RSI + MACD Dual Confirmation
        - RSI < 35 and MACD golden cross -> buy
        - RSI > 65 and MACD death cross -> sell
        - Max 3 trades per day
        - Stop: -1%, Take profit: +1.5%
        """
        trades = []
        
        df['date'] = df.index.date if hasattr(df.index, 'date') else df['timestamp'].dt.date
        
        for date, day_df in df.groupby('date'):
            daily_trades = 0
            max_daily = 3
            
            for i in range(1, len(day_df)):
                if daily_trades >= max_daily:
                    break
                    
                current = day_df.iloc[i]
                prev = day_df.iloc[i-1]
                
                # MACD golden cross: MACD crosses above signal
                macd_golden = prev['macd'] <= prev['macd_signal'] and current['macd'] > current['macd_signal']
                # MACD death cross: MACD crosses below signal
                macd_death = prev['macd'] >= prev['macd_signal'] and current['macd'] < current['macd_signal']
                
                rsi = current['rsi'] if not pd.isna(current['rsi']) else 50
                
                # Long signal
                if rsi < 35 and macd_golden:
                    entry_price = current['close']
                    stop_price = entry_price * (1 - self.stop_loss_pct)
                    tp_price = entry_price * (1 + self.take_profit_pct)
                    
                    # Find exit in remaining candles
                    remaining = day_df.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for j in range(len(remaining)):
                        h = remaining.iloc[j]
                        
                        if h['low'] <= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                            
                        if h['high'] >= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trade = self._create_trade(
                        current.name if hasattr(current, 'name') else current['timestamp'],
                        entry_price, exit_price, "long", exit_reason
                    )
                    trades.append(trade)
                    daily_trades += 1
                    
                # Short signal
                elif rsi > 65 and macd_death:
                    entry_price = current['close']
                    stop_price = entry_price * (1 + self.stop_loss_pct)
                    tp_price = entry_price * (1 - self.take_profit_pct)
                    
                    remaining = day_df.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for j in range(len(remaining)):
                        h = remaining.iloc[j]
                        
                        if h['high'] >= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                            
                        if h['low'] <= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trade = self._create_trade(
                        current.name if hasattr(current, 'name') else current['timestamp'],
                        entry_price, exit_price, "short", exit_reason
                    )
                    trades.append(trade)
                    daily_trades += 1
        
        return trades
    
    def _create_trade(self, entry_time, entry_price, exit_price, direction, exit_reason) -> Trade:
        """Create a trade record with fee calculation"""
        # Calculate P&L
        if direction == "long":
            raw_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            raw_pnl_pct = (entry_price - exit_price) / entry_price
        
        # Deduct fees (0.1% entry + 0.1% exit)
        fees = self.fee_rate * 2
        pnl_pct = raw_pnl_pct - fees
        pnl_amount = pnl_pct * self.position_size
        
        return Trade(
            entry_time=entry_time,
            entry_price=entry_price,
            exit_price=exit_price,
            direction=direction,
            pnl_pct=pnl_pct,
            pnl_amount=pnl_amount,
            exit_reason=exit_reason,
            fees=fees
        )
    
    def analyze_trades(self, trades: List[Trade]) -> Dict[str, Any]:
        """Analyze trade results"""
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_daily_pnl": 0.0,
                "max_consecutive_loss_days": 0,
                "total_pnl": 0.0,
                "profit_factor": 0.0
            }
        
        total = len(trades)
        wins = sum(1 for t in trades if t.pnl_pct > 0)
        losses = total - wins
        win_rate = wins / total * 100 if total > 0 else 0
        
        total_pnl = sum(t.pnl_pct for t in trades)
        avg_pnl = total_pnl / total if total > 0 else 0
        
        # Daily P&L
        daily_pnl = {}
        for t in trades:
            date = t.entry_time.date() if hasattr(t.entry_time, 'date') else t.entry_time
            if isinstance(date, datetime):
                date = date.date()
            date_str = str(date)
            daily_pnl[date_str] = daily_pnl.get(date_str, 0) + t.pnl_pct
        
        avg_daily_pnl = sum(daily_pnl.values()) / len(daily_pnl) if daily_pnl else 0
        
        # Max consecutive loss days
        dates = sorted(daily_pnl.keys())
        max_consecutive = 0
        current_consecutive = 0
        
        for d in dates:
            if daily_pnl[d] < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        # Profit factor
        gross_profit = sum(t.pnl_pct for t in trades if t.pnl_pct > 0)
        gross_loss = abs(sum(t.pnl_pct for t in trades if t.pnl_pct < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 1.0 if gross_profit > 0 else 0.0
        
        return {
            "total_trades": total,
            "win_rate": round(win_rate, 1),
            "avg_daily_pnl": round(avg_daily_pnl * 100, 3),  # In percent
            "max_consecutive_loss_days": max_consecutive,
            "total_pnl": round(total_pnl * 100, 3),
            "profit_factor": round(profit_factor, 2),
            "wins": wins,
            "losses": losses
        }
    
    def run_all(self) -> Dict[str, Any]:
        """Run all 3 strategies and return results"""
        df = self.fetch_data()
        
        if len(df) == 0:
            return {"error": "No data available"}
        
        df = self.calculate_indicators(df)
        
        results = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "days": self.days,
            "strategies": {}
        }
        
        # Strategy A
        print("\n🔍 Running Strategy A: Opening Range Breakout")
        trades_a = self.run_strategy_a_opening_range_breakout(df)
        results["strategies"]["A"] = {
            "name": "Opening Range Breakout",
            "trades": trades_a,
            "stats": self.analyze_trades(trades_a)
        }
        
        # Strategy B
        print("\n🔍 Running Strategy B: VWAP Reversion")
        trades_b = self.run_strategy_b_vwap_reversion(df)
        results["strategies"]["B"] = {
            "name": "VWAP Reversion",
            "trades": trades_b,
            "stats": self.analyze_trades(trades_b)
        }
        
        # Strategy C
        print("\n🔍 Running Strategy C: RSI + MACD Dual Confirmation")
        trades_c = self.run_strategy_c_rsi_macd(df)
        results["strategies"]["C"] = {
            "name": "RSI + MACD Dual Confirmation",
            "trades": trades_c,
            "stats": self.analyze_trades(trades_c)
        }
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Print formatted results"""
        print("\n" + "="*80)
        print(f"📊 DAY TRADING BACKTEST RESULTS - {self.symbol}")
        print("="*80)
        
        for key, strategy in results["strategies"].items():
            name = strategy["name"]
            stats = strategy["stats"]
            
            print(f"\n{'='*60}")
            print(f"Strategy {key}: {name}")
            print(f"{'='*60}")
            
            if stats["total_trades"] == 0:
                print("⚠️ No trades generated")
                continue
            
            print(f"Total Trades:     {stats['total_trades']} (Wins: {stats['wins']}, Losses: {stats['losses']})")
            print(f"Win Rate:         {stats['win_rate']}%")
            print(f"Avg Daily P&L:    {stats['avg_daily_pnl']}%")
            print(f"Total P&L:        {stats['total_pnl']}%")
            print(f"Profit Factor:    {stats['profit_factor']}")
            print(f"Max Consecutive Loss Days: {stats['max_consecutive_loss_days']}")
        
        print("\n" + "="*80)


def main():
    """Run backtests for BTC and ETH"""
    symbols = ["BTCUSDT", "ETHUSDT"]
    all_results = []
    
    for symbol in symbols:
        print(f"\n{'='*80}")
        print(f"🚀 Testing {symbol}")
        print(f"{'='*80}")
        
        bt = DayTradingBacktest(symbol=symbol, timeframe="15m", days=30)
        results = bt.run_all()
        bt.print_results(results)
        
        all_results.append({
            "symbol": symbol,
            "results": results
        })
    
    # Summary table
    print("\n" + "="*80)
    print("📋 SUMMARY TABLE")
    print("="*80)
    print(f"{'Strategy':<35} {'Symbol':<10} {'Trades':<8} {'Win%':<8} {'Avg/Day':<10} {'Max Loss Days':<15}")
    print("-"*80)
    
    for r in all_results:
        symbol = r["symbol"]
        for key, strategy in r["results"]["strategies"].items():
            name = f"{key}: {strategy['name']}"
            stats = strategy["stats"]
            print(f"{name:<35} {symbol:<10} {stats['total_trades']:<8} {stats['win_rate']:<8} {stats['avg_daily_pnl']:<10} {stats['max_consecutive_loss_days']:<15}")
    
    print("="*80)
    
    return all_results


if __name__ == "__main__":
    main()
