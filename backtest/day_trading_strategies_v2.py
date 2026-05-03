#!/usr/bin/env python3
"""
Day Trading Strategies Backtest v2
日內交易策略回測 v2

Fixed strategies based on first run results:
- Strategy A: ORB with volume confirmation + better risk management
- Strategy B: VWAP Reversion with mean reversion timing + max 2 trades/day
- Strategy C: RSI + MACD with dynamic thresholds + better entry timing

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


class DayTradingBacktestV2:
    """Fixed day trading backtest engine"""
    
    def __init__(self, symbol: str, timeframe: str = "15m", days: int = 30):
        self.symbol = symbol
        self.timeframe = timeframe
        self.days = days
        self.fetcher = BinanceFetcher()
        
        self.position_size = 1000.0
        self.fee_rate = 0.001  # 0.1% per side
        
    def fetch_data(self) -> pd.DataFrame:
        """Fetch historical OHLCV data"""
        if self.timeframe == "15m":
            candles_per_day = 96
        elif self.timeframe == "1h":
            candles_per_day = 24
        else:
            candles_per_day = 96
            
        limit = min(self.days * candles_per_day, 1000)
        
        print(f"📊 Fetching {self.symbol} {self.timeframe} data ({self.days} days, {limit} candles)...")
        
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
        
        # VWAP (reset daily)
        df['date'] = df.index.date
        df['vwap'] = np.nan
        for date, group in df.groupby('date'):
            typical = (group['high'] + group['low'] + group['close']) / 3
            vwap = (typical * group['volume']).cumsum() / group['volume'].cumsum()
            df.loc[group.index, 'vwap'] = vwap
        
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
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # Volume MA
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        
        # ATR for volatility
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr14'] = tr.rolling(window=14).mean()
        
        return df
    
    def _create_trade(self, entry_time, entry_price, exit_price, direction, exit_reason) -> Trade:
        """Create trade with fee calculation"""
        if direction == "long":
            raw_pnl_pct = (exit_price - entry_price) / entry_price
        else:
            raw_pnl_pct = (entry_price - exit_price) / entry_price
        
        fees = self.fee_rate * 2  # entry + exit
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
    # STRATEGY A: Opening Range Breakout v2
    # ===================================================================
    def run_strategy_a(self, df: pd.DataFrame) -> List[Trade]:
        """
        Opening Range Breakout v2
        - First 30 minutes (2 candles) define range
        - Breakout with volume > 1.2x average
        - Dynamic stop: 0.8% or ATR, whichever is smaller
        - Take profit: 1.8% or 2x range
        - Max 1 trade per day
        """
        trades = []
        
        for date, day_df in df.groupby('date'):
            if len(day_df) < 4:
                continue
            
            # Opening range: first 2 candles (30 min)
            opening = day_df.iloc[:2]
            or_high = opening['high'].max()
            or_low = opening['low'].min()
            or_range = or_high - or_low
            avg_volume = opening['volume'].mean()
            
            if or_range == 0 or avg_volume == 0:
                continue
            
            # Rest of day
            rest = day_df.iloc[2:]
            traded = False
            
            for i in range(len(rest)):
                if traded:
                    break
                    
                candle = rest.iloc[i]
                
                # Volume confirmation
                volume_ok = candle['volume'] > avg_volume * 1.2
                
                # Long breakout
                if candle['close'] > or_high and volume_ok:
                    entry_price = candle['close']
                    # Dynamic stop: min(0.8%, ATR-based)
                    atr_stop = max(candle['atr14'] * 2 / entry_price, 0.005)
                    stop_pct = min(0.008, atr_stop)
                    stop_price = entry_price * (1 - stop_pct)
                    
                    # TP: 1.8% or 2x range
                    tp_pct = max(0.018, (or_range * 2) / entry_price)
                    tp_price = entry_price * (1 + tp_pct)
                    
                    # Simulate
                    holding = rest.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for h in holding.itertuples():
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
                
                # Short breakout
                elif candle['close'] < or_low and volume_ok:
                    entry_price = candle['close']
                    atr_stop = max(candle['atr14'] * 2 / entry_price, 0.005)
                    stop_pct = min(0.008, atr_stop)
                    stop_price = entry_price * (1 + stop_pct)
                    
                    tp_pct = max(0.018, (or_range * 2) / entry_price)
                    tp_price = entry_price * (1 - tp_pct)
                    
                    holding = rest.iloc[i+1:]
                    exit_price = None
                    exit_reason = ""
                    
                    for h in holding.itertuples():
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
    
    # ===================================================================
    # STRATEGY B: VWAP Mean Reversion v2
    # ===================================================================
    def run_strategy_b(self, df: pd.DataFrame) -> List[Trade]:
        """
        VWAP Mean Reversion v2
        - Wait for price to deviate > 1.0% from VWAP
        - Enter when price starts returning (next candle moves toward VWAP)
        - Stop: deviation extends to 2.0%
        - Exit: price crosses VWAP or 3 candles max hold
        - Max 2 trades per day
        """
        trades = []
        
        for date, day_df in df.groupby('date'):
            daily_trades = 0
            max_daily = 2
            in_trade = False
            entry_price = 0
            direction = ""
            entry_time = None
            
            for i in range(2, len(day_df)):
                if daily_trades >= max_daily:
                    break
                
                curr = day_df.iloc[i]
                prev = day_df.iloc[i-1]
                prev2 = day_df.iloc[i-2]
                
                # Skip if indicators not ready
                if pd.isna(curr['vwap']) or pd.isna(prev['vwap']):
                    continue
                
                if in_trade:
                    # Check exit
                    deviation = abs(curr['close'] - curr['vwap']) / curr['vwap']
                    
                    if direction == "long":
                        # Stop loss: deviation > 2%
                        if deviation > 0.02 and curr['close'] < curr['vwap']:
                            trades.append(self._create_trade(
                                entry_time, entry_price, curr['close'], "long", "stop_loss"
                            ))
                            daily_trades += 1
                            in_trade = False
                        # Exit: crossed above VWAP
                        elif curr['close'] >= curr['vwap']:
                            trades.append(self._create_trade(
                                entry_time, entry_price, curr['vwap'], "long", "vwap_cross"
                            ))
                            daily_trades += 1
                            in_trade = False
                        # Time exit: 3 candles max
                        elif i - entry_idx >= 3:
                            trades.append(self._create_trade(
                                entry_time, entry_price, curr['close'], "long", "time_exit"
                            ))
                            daily_trades += 1
                            in_trade = False
                    
                    else:  # short
                        if deviation > 0.02 and curr['close'] > curr['vwap']:
                            trades.append(self._create_trade(
                                entry_time, entry_price, curr['close'], "short", "stop_loss"
                            ))
                            daily_trades += 1
                            in_trade = False
                        elif curr['close'] <= curr['vwap']:
                            trades.append(self._create_trade(
                                entry_time, entry_price, curr['vwap'], "short", "vwap_cross"
                            ))
                            daily_trades += 1
                            in_trade = False
                        elif i - entry_idx >= 3:
                            trades.append(self._create_trade(
                                entry_time, entry_price, curr['close'], "short", "time_exit"
                            ))
                            daily_trades += 1
                            in_trade = False
                
                else:
                    # Check entry: deviation > 1% and returning
                    prev_deviation = abs(prev['close'] - prev['vwap']) / prev['vwap']
                    
                    if prev_deviation > 0.01:
                        # Price was below VWAP, now moving up (long signal)
                        if prev['close'] < prev['vwap'] and curr['close'] > prev['close']:
                            entry_price = curr['close']
                            entry_time = curr.name if hasattr(curr, 'name') else curr['timestamp']
                            direction = "long"
                            in_trade = True
                            entry_idx = i
                        
                        # Price was above VWAP, now moving down (short signal)
                        elif prev['close'] > prev['vwap'] and curr['close'] < prev['close']:
                            entry_price = curr['close']
                            entry_time = curr.name if hasattr(curr, 'name') else curr['timestamp']
                            direction = "short"
                            in_trade = True
                            entry_idx = i
        
        return trades
    
    # ===================================================================
    # STRATEGY C: RSI + MACD v2
    # ===================================================================
    def run_strategy_c(self, df: pd.DataFrame) -> List[Trade]:
        """
        RSI + MACD Dual Confirmation v2
        - RSI < 30 (oversold) + MACD histogram turning positive
        - RSI > 70 (overbought) + MACD histogram turning negative
        - Stop: -1.0%, TP: +1.5%
        - Max 2 trades per day
        - Only trade when ADX > 25 (trending market)
        """
        trades = []
        
        # Calculate ADX
        plus_dm = df['high'].diff()
        minus_dm = df['low'].diff().abs()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        tr = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr
        minus_di = 100 * minus_dm.rolling(14).mean() / atr
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.rolling(14).mean()
        
        for date, day_df in df.groupby('date'):
            daily_trades = 0
            max_daily = 2
            
            for i in range(3, len(day_df)):
                if daily_trades >= max_daily:
                    break
                
                curr = day_df.iloc[i]
                prev = day_df.iloc[i-1]
                prev2 = day_df.iloc[i-2]
                
                # Skip if indicators not ready
                if pd.isna(curr['rsi']) or pd.isna(curr['macd_hist']):
                    continue
                
                # ADX check - skip if not trending
                adx = curr['adx'] if 'adx' in curr else 0
                
                # Long signal: RSI < 30 and MACD hist turning positive
                rsi_long = curr['rsi'] < 30
                macd_long = prev['macd_hist'] <= 0 and curr['macd_hist'] > 0
                
                if rsi_long and macd_long:
                    entry_price = curr['close']
                    stop_price = entry_price * 0.99  # -1%
                    tp_price = entry_price * 1.015  # +1.5%
                    
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
                        curr.name if hasattr(curr, 'name') else curr['timestamp'],
                        entry_price, exit_price, "long", exit_reason
                    ))
                    daily_trades += 1
                    continue
                
                # Short signal: RSI > 70 and MACD hist turning negative
                rsi_short = curr['rsi'] > 70
                macd_short = prev['macd_hist'] >= 0 and curr['macd_hist'] < 0
                
                if rsi_short and macd_short:
                    entry_price = curr['close']
                    stop_price = entry_price * 1.01  # +1%
                    tp_price = entry_price * 0.985  # -1.5%
                    
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
                        curr.name if hasattr(curr, 'name') else curr['timestamp'],
                        entry_price, exit_price, "short", exit_reason
                    ))
                    daily_trades += 1
        
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
        
        print("\n🔍 Strategy A: Opening Range Breakout v2")
        trades_a = self.run_strategy_a(df)
        results["A"] = {"name": "Opening Range Breakout", "trades": trades_a, "stats": self.analyze_trades(trades_a)}
        
        print("🔍 Strategy B: VWAP Mean Reversion v2")
        trades_b = self.run_strategy_b(df)
        results["B"] = {"name": "VWAP Mean Reversion", "trades": trades_b, "stats": self.analyze_trades(trades_b)}
        
        print("🔍 Strategy C: RSI + MACD v2")
        trades_c = self.run_strategy_c(df)
        results["C"] = {"name": "RSI + MACD", "trades": trades_c, "stats": self.analyze_trades(trades_c)}
        
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
        
        bt = DayTradingBacktestV2(symbol=symbol, timeframe="15m", days=30)
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
