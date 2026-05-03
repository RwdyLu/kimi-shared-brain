#!/usr/bin/env python3
"""
Day Trading Strategies Backtest v3
日內交易策略回測 v3

Redesigned strategies based on crypto market characteristics:
- Crypto is 24/7, trend-following works better than mean reversion
- Use momentum from first 30-60 minutes to establish daily bias
- Tight risk management with fixed SL/TP

Target: +0.1% ~ +0.3% daily after 0.1% fees
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from data.fetcher import BinanceFetcher


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    direction: str = "long"
    pnl_pct: float = 0.0
    pnl_amount: float = 0.0
    exit_reason: str = ""
    fees: float = 0.0


class DayTradingBacktestV3:
    """Day trading backtest - v3"""
    
    def __init__(self, symbol: str, timeframe: str = "15m", days: int = 30):
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.fetcher = BinanceFetcher()
        
        self.position_size = 1000.0
        self.fee_rate = 0.001
        
    def fetch_data(self) -> pd.DataFrame:
        """Fetch historical OHLCV data"""
        if self.timeframe == "15m":
            candles_per_day = 96
        elif self.timeframe == "1h":
            candles_per_day = 24
        else:
            candles_per_day = 96
            
        limit = min(self.days * candles_per_day, 1000)
        
        print(f"📊 Fetching {self.symbol} {self.timeframe} ({limit} candles)...")
        
        try:
            klines = self.fetcher.get_klines(symbol=self.symbol, interval=self.timeframe, limit=limit)
            
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
            if len(df) == 0:
                return pd.DataFrame()
                
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            print(f"✅ Fetched {len(df)} candles ({df.index[0]} ~ {df.index[-1]})")
            return df
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        if len(df) == 0:
            return df
        
        df['date'] = df.index.date
        
        # EMAs
        df['ema5'] = df['close'].ewm(span=5).mean()
        df['ema10'] = df['close'].ewm(span=10).mean()
        df['ema20'] = df['close'].ewm(span=20).mean()
        
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
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr14'] = tr.rolling(window=14).mean()
        
        # Volume MA
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        
        return df
    
    def _create_trade(self, entry_time, entry_price, exit_price, direction, exit_reason) -> Trade:
        """Create trade with fee calculation"""
        if direction == "long":
            raw_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            raw_pnl_pct = (entry_price - exit_price) / entry_price
        
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
    
    # ===================================================================
    # STRATEGY A: First Hour Momentum
    # ===================================================================
    def run_strategy_a(self, df: pd.DataFrame) -> List[Trade]:
        """
        First Hour Momentum
        - Use first 4 candles (60 min) to determine daily bias
        - If close > open with strong volume (>1.5x avg) -> go long
        - If close < open with strong volume -> go short
        - Entry: next candle after first hour
        - Stop: -1.0%, TP: +1.5% (user's requirement)
        - Close at end of day if not hit SL/TP
        - Max 1 trade per day
        """
        trades = []
        
        for date, day_df in df.groupby('date'):
            if len(day_df) < 6:
                continue
            
            # First hour (4 candles of 15m)
            first_hour = day_df.iloc[:4]
            first_open = first_hour.iloc[0]['open']
            first_hour_close = first_hour.iloc[-1]['close']
            first_hour_high = first_hour['high'].max()
            first_hour_low = first_hour['low'].min()
            avg_volume = first_hour['volume'].mean()
            
            # Calculate momentum
            momentum = (first_hour_close - first_open) / first_open
            momentum_pct = abs(momentum) * 100
            
            # Need at least 0.5% momentum with volume confirmation
            volume_ok = first_hour.iloc[-1]['volume'] > avg_volume * 1.3
            
            if momentum_pct < 0.5 or not volume_ok:
                continue
            
            # Determine direction
            if first_hour_close > first_open:
                direction = "long"
                entry_price = day_df.iloc[4]['close']  # Enter on 5th candle
                stop_price = entry_price * 0.99  # -1%
                tp_price = entry_price * 1.015  # +1.5%
            else:
                direction = "short"
                entry_price = day_df.iloc[4]['close']
                stop_price = entry_price * 1.01  # +1%
                tp_price = entry_price * 0.985  # -1.5%
            
            # Simulate rest of day
            rest = day_df.iloc[5:]
            exit_price = None
            exit_reason = ""
            
            for h in rest.itertuples():
                if direction == "long":
                    if h.low <= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop_loss"
                        break
                    if h.high >= tp_price:
                        exit_price = tp_price
                        exit_reason = "take_profit"
                        break
                else:
                    if h.high >= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop_loss"
                        break
                    if h.low <= tp_price:
                        exit_price = tp_price
                        exit_reason = "take_profit"
                        break
            
            if exit_price is None:
                exit_price = day_df.iloc[-1]['close']
                exit_reason = "end_of_day"
            
            trades.append(self._create_trade(
                day_df.iloc[4].name, entry_price, exit_price, direction, exit_reason
            ))
        
        return trades
    
    # ===================================================================
    # STRATEGY B: EMA Crossover with Trend Filter
    # ===================================================================
    def run_strategy_b(self, df: pd.DataFrame) -> List[Trade]:
        """
        EMA Crossover with Trend Filter
        - EMA5 crosses above EMA10 -> long (if RSI < 70)
        - EMA5 crosses below EMA10 -> short (if RSI > 30)
        - Stop: -1.0%, TP: +1.5%
        - Close at end of day
        - Max 1 trade per day (first signal only)
        """
        trades = []
        
        for date, day_df in df.groupby('date'):
            if len(day_df) < 5:
                continue
            
            traded = False
            
            for i in range(3, len(day_df)):
                if traded:
                    break
                
                curr = day_df.iloc[i]
                prev = day_df.iloc[i-1]
                
                # Skip if indicators not ready
                if pd.isna(curr['ema5']) or pd.isna(curr['ema10']) or pd.isna(curr['rsi']):
                    continue
                
                # Long signal: EMA5 crosses above EMA10, RSI not overbought
                ema_cross_up = prev['ema5'] <= prev['ema10'] and curr['ema5'] > curr['ema10']
                
                if ema_cross_up and curr['rsi'] < 70:
                    entry_price = curr['close']
                    stop_price = entry_price * 0.99
                    tp_price = entry_price * 1.015
                    
                    remaining = day_df.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for h in remaining.itertuples():
                        if h.low <= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                        if h.high >= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trades.append(self._create_trade(
                        curr.name, entry_price, exit_price, "long", exit_reason
                    ))
                    traded = True
                
                # Short signal: EMA5 crosses below EMA10, RSI not oversold
                ema_cross_down = prev['ema5'] >= prev['ema10'] and curr['ema5'] < curr['ema10']
                
                if ema_cross_down and curr['rsi'] > 30:
                    entry_price = curr['close']
                    stop_price = entry_price * 1.01
                    tp_price = entry_price * 0.985
                    
                    remaining = day_df.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for h in remaining.itertuples():
                        if h.high >= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                        if h.low <= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trades.append(self._create_trade(
                        curr.name, entry_price, exit_price, "short", exit_reason
                    ))
                    traded = True
        
        return trades
    
    # ===================================================================
    # STRATEGY C: Bollinger Band Squeeze Breakout
    # ===================================================================
    def run_strategy_c(self, df: pd.DataFrame) -> List[Trade]:
        """
        Bollinger Band Squeeze Breakout
        - Wait for BB squeeze (band width < 2% of price) in first 2 hours
        - When price breaks out of squeeze with volume > 1.5x avg -> follow breakout
        - Stop: -1.0%, TP: +1.5%
        - Close at end of day
        - Max 1 trade per day
        """
        trades = []
        
        for date, day_df in df.groupby('date'):
            if len(day_df) < 10:
                continue
            
            # First 2 hours (8 candles) for squeeze detection
            setup_period = day_df.iloc[:8]
            
            # Check for squeeze
            squeezed = False
            squeeze_idx = None
            
            for i in range(3, len(setup_period)):
                candle = setup_period.iloc[i]
                if pd.isna(candle['bb_upper']) or pd.isna(candle['bb_lower']):
                    continue
                
                band_width = (candle['bb_upper'] - candle['bb_lower']) / candle['close']
                
                # Squeeze: band width < 1.5% of price
                if band_width < 0.015:
                    squeezed = True
                    squeeze_idx = i
                    break
            
            if not squeezed or squeeze_idx is None:
                continue
            
            # Look for breakout after squeeze
            post_squeeze = day_df.iloc[squeeze_idx+1:]
            avg_volume = setup_period['volume'].mean()
            
            traded = False
            for i in range(min(3, len(post_squeeze))):
                if traded:
                    break
                    
                candle = post_squeeze.iloc[i]
                
                # Volume confirmation
                volume_ok = candle['volume'] > avg_volume * 1.3
                if not volume_ok:
                    continue
                
                # Breakout direction
                if candle['close'] > candle['bb_upper']:
                    # Long breakout
                    entry_price = candle['close']
                    stop_price = entry_price * 0.99
                    tp_price = entry_price * 1.015
                    
                    remaining = post_squeeze.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for h in remaining.itertuples():
                        if h.low <= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                        if h.high >= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trades.append(self._create_trade(
                        candle.name, entry_price, exit_price, "long", exit_reason
                    ))
                    traded = True
                    
                elif candle['close'] < candle['bb_lower']:
                    # Short breakout
                    entry_price = candle['close']
                    stop_price = entry_price * 1.01
                    tp_price = entry_price * 0.985
                    
                    remaining = post_squeeze.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for h in remaining.itertuples():
                        if h.high >= stop_price:
                            exit_price = stop_price
                            exit_reason = "stop_loss"
                            break
                        if h.low <= tp_price:
                            exit_price = tp_price
                            exit_reason = "take_profit"
                            break
                    
                    if exit_price is None:
                        exit_price = day_df.iloc[-1]['close']
                        exit_reason = "end_of_day"
                    
                    trades.append(self._create_trade(
                        candle.name, entry_price, exit_price, "short", exit_reason
                    ))
                    traded = True
        
        return trades
    
    def analyze_trades(self, trades: List[Trade]) -> Dict[str, Any]:
        """Analyze trade results"""
        if not trades:
            return {
                "total_trades": 0, "win_rate": 0.0, "avg_daily_pnl": 0.0,
                "max_consecutive_loss_days": 0, "total_pnl": 0.0,
                "profit_factor": 0.0, "wins": 0, "losses": 0
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
            "avg_daily_pnl": round(avg_daily_pnl * 100, 3),
            "max_consecutive_loss_days": max_consecutive,
            "total_pnl": round(total_pnl * 100, 3),
            "profit_factor": round(profit_factor, 2),
            "wins": wins,
            "losses": losses
        }
    
    def run_all(self) -> Dict[str, Any]:
        """Run all strategies"""
        df = self.fetch_data()
        if len(df) == 0:
            return {"error": "No data"}
        
        df = self.calculate_indicators(df)
        
        results = {"symbol": self.symbol, "timeframe": self.timeframe, "days": self.days}
        
        print("\n🔍 Strategy A: First Hour Momentum")
        trades_a = self.run_strategy_a(df)
        results["A"] = {"name": "First Hour Momentum", "trades": trades_a, "stats": self.analyze_trades(trades_a)}
        
        print("🔍 Strategy B: EMA Crossover")
        trades_b = self.run_strategy_b(df)
        results["B"] = {"name": "EMA Crossover", "trades": trades_b, "stats": self.analyze_trades(trades_b)}
        
        print("🔍 Strategy C: BB Squeeze Breakout")
        trades_c = self.run_strategy_c(df)
        results["C"] = {"name": "BB Squeeze Breakout", "trades": trades_c, "stats": self.analyze_trades(trades_c)}
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Print results"""
        print("\n" + "="*70)
        print(f"📊 RESULTS: {self.symbol}")
        print("="*70)
        
        for key in ["A", "B", "C"]:
            s = results[key]
            stats = s["stats"]
            
            print(f"\n{'='*60}")
            print(f"Strategy {key}: {s['name']}")
            print(f"{'='*60}")
            
            if stats["total_trades"] == 0:
                print("⚠️ No trades")
                continue
            
            print(f"Trades: {stats['total_trades']} (W:{stats['wins']} L:{stats['losses']})")
            print(f"Win Rate: {stats['win_rate']}%")
            print(f"Avg Daily P&L: {stats['avg_daily_pnl']}%")
            print(f"Total P&L: {stats['total_pnl']}%")
            print(f"Profit Factor: {stats['profit_factor']}")
            print(f"Max Consecutive Loss Days: {stats['max_consecutive_loss_days']}")
        
        print("\n" + "="*70)


def main():
    symbols = ["BTCUSDT", "ETHUSDT"]
    all_results = []
    
    for symbol in symbols:
        print(f"\n{'='*70}")
        print(f"🚀 {symbol}")
        print(f"{'='*70}")
        
        bt = DayTradingBacktestV3(symbol=symbol, timeframe="15m", days=30)
        results = bt.run_all()
        bt.print_results(results)
        all_results.append({"symbol": symbol, "results": results})
    
    # Summary
    print("\n" + "="*80)
    print("📋 SUMMARY")
    print("="*80)
    print(f"{'Strategy':<35} {'Symbol':<10} {'Trades':<8} {'Win%':<8} {'Avg/Day':<10} {'Max Loss Days':<15}")
    print("-"*80)
    
    for r in all_results:
        sym = r["symbol"]
        for key in ["A", "B", "C"]:
            name = f"{key}: {r['results'][key]['name']}"
            stats = r['results'][key]['stats']
            print(f"{name:<35} {sym:<10} {stats['total_trades']:<8} {stats['win_rate']:<8} {stats['avg_daily_pnl']:<10} {stats['max_consecutive_loss_days']:<15}")
    
    print("="*80)
    
    return all_results


if __name__ == "__main__":
    main()
