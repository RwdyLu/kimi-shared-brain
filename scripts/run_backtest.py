"""
Backtest Engine / 回測引擎

Reference: Freqtrade backtesting architecture (freqtrade/optimize/backtesting.py)
Simplified for integration with existing system.

Features:
- Download historical klines from Binance
- Bar-by-bar backtesting with existing strategy conditions
- Reuse trade_executor logic for paper simulation
- Generate backtest reports (PnL, win rate, profit factor, max drawdown, Sharpe)

Usage:
    python scripts/run_backtest.py --symbol BTCUSDT --days 30 --strategy ma_cross_trend_v2
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.fetcher import BinanceFetcher, KlineData
from indicators.calculator import (
    calculate_ma5, calculate_ma20, calculate_ma240,
    calculate_rsi, calculate_tema, calculate_stochastic,
    calculate_bollinger_bands, calculate_sar, calculate_ht_sine,
    calculate_ema, calculate_atr, calculate_adx,
    calculate_volume_sma,
)
from app.strategy_conditions import StrategyConditions, ConditionResult


@dataclass
class BacktestTrade:
    """A single backtest trade record / 單筆回測交易記錄"""
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    side: str = "buy"  # buy (long) or sell (short)
    quantity: float = 0.0
    pnl_pct: float = 0.0
    pnl_absolute: float = 0.0
    exit_reason: str = ""
    strategy_id: str = ""
    symbol: str = ""


@dataclass
class BacktestResult:
    """Backtest result summary / 回測結果摘要"""
    strategy_id: str = ""
    symbol: str = ""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_profit_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    start_balance: float = 1000.0
    end_balance: float = 1000.0
    trades: List[BacktestTrade] = field(default_factory=list)


class HistoryDownloader:
    """Download historical klines from Binance / 從 Binance 下載歷史 K 線"""

    def __init__(self):
        self.fetcher = BinanceFetcher()

    def download(self, symbol: str, interval: str = "5m", days: int = 30) -> List[KlineData]:
        """
        Download historical klines.
        Binance API limit is 1000 candles per request.
        For 5m interval, 1000 candles = ~3.5 days.
        """
        end_time = datetime.utcnow()
        all_klines: List[KlineData] = []

        # Calculate how many requests we need
        candles_needed = (days * 24 * 60) // 5  # for 5m interval
        requests_needed = (candles_needed // 1000) + 1

        print(f"[History] Downloading {days} days of {interval} data for {symbol}")
        print(f"[History] Estimated {candles_needed} candles, {requests_needed} API requests")

        current_end = int(end_time.timestamp() * 1000)
        ms_per_candle = self._interval_to_ms(interval)

        for i in range(requests_needed):
            # Calculate start time for this chunk
            chunk_candles = min(1000, candles_needed - len(all_klines))
            if chunk_candles <= 0:
                break

            chunk_start = current_end - (chunk_candles * ms_per_candle)

            try:
                raw = self.fetcher.fetch_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=chunk_candles,
                    start_time=chunk_start,
                    end_time=current_end,
                )
                klines = self.fetcher.normalize_kline_data(raw)

                if not klines:
                    break

                all_klines = klines + all_klines  # prepend older data
                current_end = klines[0].timestamp - ms_per_candle

                print(f"  Chunk {i+1}: Got {len(klines)} candles (total: {len(all_klines)})")

                # Rate limiting
                import time
                time.sleep(0.1)

            except Exception as e:
                print(f"  Chunk {i+1} failed: {e}")
                break

        print(f"[History] Total downloaded: {len(all_klines)} candles")
        return all_klines

    @staticmethod
    def _interval_to_ms(interval: str) -> int:
        """Convert interval string to milliseconds"""
        mapping = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }
        return mapping.get(interval, 5 * 60 * 1000)


class BacktestEngine:
    """
    Bar-by-bar backtesting engine.

    Architecture (inspired by Freqtrade backtesting.py):
    1. Load historical data
    2. For each bar, calculate indicators
    3. Check strategy entry conditions
    4. If signal: open paper position
    5. Check exit conditions (stop-loss, take-profit, trailing, technical reversal)
    6. Record all trades and compute statistics
    """

    def __init__(self, strategy_config: Dict[str, Any]):
        self.strategy_config = strategy_config
        self.condition_checker = StrategyConditions()
        self.trades: List[BacktestTrade] = []
        self.balance = 1000.0
        self.initial_balance = 1000.0
        self.position_pct = 0.15
        self.max_total_exposure_pct = 0.5

        # Risk management params (same as TradeExecutor)
        self.hard_stop_loss = -0.05
        self.minimal_roi = {
            0: 0.05, 20: 0.04, 40: 0.03, 60: 0.02, 120: 0.01, 240: 0.005,
        }
        self.trailing_enabled = True
        self.trailing_offset = 0.03
        self.trailing_distance = 0.02
        self.atr_stop_multiplier = 1.5
        self.max_hold_hours = 8

        # Open positions during backtest
        self.open_positions: List[Dict[str, Any]] = []

    def run(self, klines: List[KlineData]) -> BacktestResult:
        """Run backtest on historical klines"""
        if not klines:
            raise ValueError("No klines data provided")

        strategy_id = self.strategy_config["id"]
        symbol = self.strategy_config.get("symbols", ["UNKNOWN"])[0]
        conditions = self.strategy_config.get("conditions", [])
        parameters = self.strategy_config.get("parameters", {})

        print(f"[Backtest] Running {strategy_id} on {len(klines)} candles")

        # Need minimum 240 candles for MA240
        min_required = 240
        if len(klines) < min_required:
            print(f"[Backtest] Warning: Only {len(klines)} candles, need {min_required} for full indicators")

        for i in range(min_required, len(klines)):
            window = klines[:i+1]
            current = klines[i]

            # Calculate indicators for this bar
            indicators = self._calculate_indicators_for_bar(window)

            # Check exits first
            self._check_exits(current, indicators)

            # Check entry conditions
            market_data = self._build_market_data(indicators, current, window)
            results = self.condition_checker.check_all_conditions(conditions, market_data, parameters)

            if self.condition_checker.strategy_passed(results):
                self._open_position(current, indicators, strategy_id, symbol)

        # Close any remaining open positions at the end
        for pos in self.open_positions:
            self._close_position(pos, klines[-1], "end_of_data")

        # Build result
        return self._build_result(strategy_id, symbol)

    def _calculate_indicators_for_bar(self, window: List[KlineData]) -> Dict[str, Any]:
        """Calculate all indicators for current window"""
        closes = [k.close for k in window]
        highs = [k.high for k in window]
        lows = [k.low for k in window]
        volumes = [k.volume for k in window]

        result = {}

        if len(closes) >= 5:
            ma5_list = calculate_ma5(closes)
            if ma5_list:
                result["ma5"] = ma5_list[-1]

        if len(closes) >= 20:
            ma20_list = calculate_ma20(closes)
            if ma20_list:
                result["ma20"] = ma20_list[-1]

        if len(closes) >= 240:
            ma240_list = calculate_ma240(closes)
            if ma240_list:
                result["ma240"] = ma240_list[-1]

        # Volume
        if volumes:
            result["volume"] = volumes[-1]
            result["volumes"] = volumes
            if len(volumes) >= 20:
                avg_vol = calculate_volume_sma(volumes, 20)
                result["volume_ratio"] = volumes[-1] / avg_vol if avg_vol > 0 else 1.0
                vol_ema = calculate_ema(volumes, 20)
                if vol_ema:
                    result["volume_ema20"] = vol_ema[-1]

        # EMA
        if len(closes) >= 10:
            ema5_list = calculate_ema(closes, 5)
            ema10_list = calculate_ema(closes, 10)
            if ema5_list and ema10_list:
                result["ema5"] = ema5_list[-1]
                result["ema10"] = ema10_list[-1]

        # RSI
        if len(closes) >= 15:
            rsi_list = calculate_rsi(closes, 14)
            if rsi_list:
                result["rsi"] = rsi_list[-1]
                if len(rsi_list) >= 2:
                    result["rsi_prev"] = rsi_list[-2]

        # TEMA
        if len(closes) >= 27:
            tema_list = calculate_tema(closes, 9)
            if tema_list:
                result["tema"] = tema_list[-1]
                if len(tema_list) >= 2:
                    result["tema_prev"] = tema_list[-2]

        # Stochastic
        if len(closes) >= 8:
            fastk_list, fastd_list = calculate_stochastic(closes, highs, lows, 5, 3)
            if fastk_list and fastd_list:
                result["stoch_fastk"] = fastk_list[-1]
                result["stoch_fastd"] = fastd_list[-1]

        # Bollinger Bands
        if len(closes) >= 20:
            bb = calculate_bollinger_bands(closes, 20, 2.0)
            if bb["middle"]:
                result["bb_upper"] = bb["upper"][-1]
                result["bb_middle"] = bb["middle"][-1]
                result["bb_lower"] = bb["lower"][-1]

        # SAR
        if len(highs) >= 2 and len(lows) >= 2:
            sar_list = calculate_sar(highs, lows, 0.02, 0.2)
            if sar_list:
                result["sar"] = sar_list[-1]

        # Hilbert Sine
        if len(closes) >= 20:
            ht = calculate_ht_sine(closes)
            if ht["sine"]:
                result["ht_sine"] = ht["sine"][-1]
                result["ht_leadsine"] = ht["leadsine"][-1]

        # P3 Risk Management
        if len(closes) >= 15:
            atr_list = calculate_atr(highs, lows, closes, 14)
            if atr_list:
                result["atr14"] = atr_list[-1]

        if len(closes) >= 20:
            adx_list = calculate_adx(highs, lows, closes, 14)
            if adx_list:
                result["adx14"] = adx_list[-1]

        # Previous MA values for crossover detection
        if len(closes) >= 2:
            prev_closes = closes[:-1]
            if len(prev_closes) >= 5:
                ma5_prev = calculate_ma5(prev_closes)
                if ma5_prev:
                    result["ma5_prev"] = ma5_prev[-1]
            if len(prev_closes) >= 20:
                ma20_prev = calculate_ma20(prev_closes)
                if ma20_prev:
                    result["ma20_prev"] = ma20_prev[-1]

        return result

    def _build_market_data(self, indicators: Dict, current: KlineData, window: List[KlineData]) -> Dict:
        """Build market data dict for condition checking"""
        candles = [{"open": k.open, "high": k.high, "low": k.low, "close": k.close, "volume": k.volume} for k in window]

        data = {
            "price": current.close,
            "ma5": indicators.get("ma5"),
            "ma20": indicators.get("ma20"),
            "ma240": indicators.get("ma240"),
            "volume_ratio": indicators.get("volume_ratio"),
            "volume": current.volume,
            "volumes": [k.volume for k in window],
            "volume_ema20": indicators.get("volume_ema20"),
            "candles": candles,
            "closes": [k.close for k in window],
            "rsi": indicators.get("rsi"),
            "rsi_prev": indicators.get("rsi_prev"),
            "tema": indicators.get("tema"),
            "tema_prev": indicators.get("tema_prev"),
            "stoch_fastk": indicators.get("stoch_fastk"),
            "stoch_fastd": indicators.get("stoch_fastd"),
            "bb_upper": indicators.get("bb_upper"),
            "bb_middle": indicators.get("bb_middle"),
            "bb_lower": indicators.get("bb_lower"),
            "sar": indicators.get("sar"),
            "ht_sine": indicators.get("ht_sine"),
            "ht_leadsine": indicators.get("ht_leadsine"),
            "ema5": indicators.get("ema5"),
            "ema10": indicators.get("ema10"),
            "atr14": indicators.get("atr14"),
            "adx14": indicators.get("adx14"),
            "ma5_prev": indicators.get("ma5_prev"),
            "ma20_prev": indicators.get("ma20_prev"),
        }
        return data

    def _open_position(self, current: KlineData, indicators: Dict, strategy_id: str, symbol: str):
        """Open a new position"""
        # Check max exposure
        total_exposure = sum(p["value"] for p in self.open_positions)
        if total_exposure >= self.initial_balance * self.max_total_exposure_pct:
            return

        # Check if already in position for this strategy+symbol
        for p in self.open_positions:
            if p["strategy_id"] == strategy_id and p["symbol"] == symbol:
                return

        position_value = self.balance * self.position_pct
        if position_value <= 0:
            return

        quantity = position_value / current.close

        # ATR-based stop distance
        atr = indicators.get("atr14", 0)
        if atr and atr > 0 and current.close > 0:
            atr_stop_pct = (atr * self.atr_stop_multiplier / current.close)
        else:
            atr_stop_pct = abs(self.hard_stop_loss)  # fallback to hard stop
        stop_loss_pct = -max(abs(self.hard_stop_loss), atr_stop_pct)

        position = {
            "symbol": symbol,
            "strategy_id": strategy_id,
            "entry_price": current.close,
            "entry_time": datetime.fromtimestamp(current.timestamp / 1000),
            "quantity": quantity,
            "value": position_value,
            "side": "buy",
            "stop_loss_pct": stop_loss_pct,
            "trailing_stop_price": None,
            "highest_price": current.close,
        }

        self.open_positions.append(position)
        self.balance -= position_value  # Reserve capital

    def _check_exits(self, current: KlineData, indicators: Dict):
        """Check all exit conditions for open positions"""
        price = current.close
        now = datetime.fromtimestamp(current.timestamp / 1000)

        for pos in list(self.open_positions):
            entry_price = pos["entry_price"]
            entry_time = pos["entry_time"]
            side = pos["side"]

            # Calculate PnL
            if side == "buy":
                pnl_pct = (price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - price) / entry_price

            exited = False
            reason = ""

            # 1. Hard stop-loss
            if pnl_pct <= pos["stop_loss_pct"]:
                exited = True
                reason = f"hard_stop_{abs(pos['stop_loss_pct'])*100:.0f}pct"

            # 2. Minimal ROI (time-based)
            if not exited:
                hold_minutes = (now - entry_time).total_seconds() / 60
                applicable_roi = 0.0
                for minutes_threshold, roi in sorted(self.minimal_roi.items(), key=lambda x: int(x[0]), reverse=True):
                    if hold_minutes >= int(minutes_threshold):
                        applicable_roi = roi
                        break
                if pnl_pct >= applicable_roi and applicable_roi > 0:
                    exited = True
                    reason = f"min_roi_{applicable_roi*100:.1f}pct"

            # 3. Trailing stop
            if not exited and self.trailing_enabled:
                if pnl_pct >= self.trailing_offset:
                    # Update highest price
                    if price > pos["highest_price"]:
                        pos["highest_price"] = price

                    trail_price = pos["highest_price"] * (1 - self.trailing_distance)
                    if price <= trail_price:
                        exited = True
                        reason = f"trailing_stop_{self.trailing_distance*100:.1f}pct"

            # 4. Time stop
            if not exited:
                hold_hours = (now - entry_time).total_seconds() / 3600
                if hold_hours >= self.max_hold_hours:
                    exited = True
                    reason = f"time_stop_{hold_hours:.1f}h"

            # 5. Technical reversal (MA cross) - only if profitable or small loss AND strong confirmation
            if not exited and abs(pnl_pct) < 0.02:
                ma5 = indicators.get("ma5")
                ma20 = indicators.get("ma20")
                ma5_prev = indicators.get("ma5_prev")
                ma20_prev = indicators.get("ma20_prev")
                # Require confirmed MA cross: previous bar MA5 > MA20, now MA5 < MA20
                if ma5 and ma20 and ma5_prev and ma20_prev:
                    if side == "buy" and ma5_prev > ma20_prev and ma5 < ma20:
                        exited = True
                        reason = "ma_reverse"

            if exited:
                self._close_position(pos, current, reason)

    def _close_position(self, position: Dict, current: KlineData, reason: str):
        """Close a position and record the trade"""
        price = current.close
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        side = position["side"]

        if side == "buy":
            pnl_pct = (price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - price) / entry_price

        pnl_absolute = quantity * entry_price * pnl_pct

        # Return capital + PnL
        self.balance += position["value"] + pnl_absolute

        trade = BacktestTrade(
            entry_time=position["entry_time"],
            exit_time=datetime.fromtimestamp(current.timestamp / 1000),
            entry_price=entry_price,
            exit_price=price,
            side=side,
            quantity=quantity,
            pnl_pct=pnl_pct,
            pnl_absolute=pnl_absolute,
            exit_reason=reason,
            strategy_id=position["strategy_id"],
            symbol=position["symbol"],
        )

        self.trades.append(trade)

        if position in self.open_positions:
            self.open_positions.remove(position)

    def _build_result(self, strategy_id: str, symbol: str) -> BacktestResult:
        """Build backtest result from trades"""
        if not self.trades:
            return BacktestResult(strategy_id=strategy_id, symbol=symbol,
                                  start_balance=self.initial_balance, end_balance=self.balance)

        winning = [t for t in self.trades if t.pnl_pct > 0]
        losing = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0
        avg_profit = statistics.mean([t.pnl_pct for t in winning]) * 100 if winning else 0
        avg_loss = statistics.mean([t.pnl_pct for t in losing]) * 100 if losing else 0

        total_profit = sum(t.pnl_absolute for t in winning)
        total_loss = abs(sum(t.pnl_absolute for t in losing))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        # Calculate max drawdown
        equity_curve = [self.initial_balance]
        for t in self.trades:
            equity_curve.append(equity_curve[-1] + t.pnl_absolute)

        max_dd = 0.0
        peak = equity_curve[0]
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (simplified: assume risk-free rate = 0)
        returns = [t.pnl_pct for t in self.trades]
        if len(returns) > 1:
            avg_return = statistics.mean(returns)
            std_return = statistics.stdev(returns)
            sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0  # Annualized
        else:
            sharpe = 0.0

        return BacktestResult(
            strategy_id=strategy_id,
            symbol=symbol,
            total_trades=len(self.trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            avg_profit_pct=avg_profit,
            avg_loss_pct=avg_loss,
            profit_factor=profit_factor,
            total_pnl_pct=((self.balance - self.initial_balance) / self.initial_balance) * 100,
            max_drawdown_pct=max_dd * 100,
            sharpe_ratio=sharpe,
            start_balance=self.initial_balance,
            end_balance=self.balance,
            trades=self.trades,
        )


def print_backtest_result(result: BacktestResult):
    """Print formatted backtest result / 印出格式化的回測結果"""
    print(f"\n{'='*60}")
    print(f"BACKTEST RESULT: {result.strategy_id} on {result.symbol}")
    print(f"{'='*60}")
    print(f"Total Trades:     {result.total_trades}")
    print(f"Winning Trades:   {result.winning_trades} ({result.win_rate:.1f}%)")
    print(f"Losing Trades:    {result.losing_trades}")
    print(f"Profit Factor:    {result.profit_factor:.2f}")
    print(f"Avg Profit:       +{result.avg_profit_pct:.2f}%")
    print(f"Avg Loss:         {result.avg_loss_pct:.2f}%")
    print(f"Total PnL:        {result.total_pnl_pct:+.2f}%")
    print(f"Max Drawdown:     {result.max_drawdown_pct:.2f}%")
    print(f"Sharpe Ratio:     {result.sharpe_ratio:.2f}")
    print(f"Start Balance:    ${result.start_balance:,.2f}")
    print(f"End Balance:      ${result.end_balance:,.2f}")
    print(f"{'='*60}")

    if result.trades:
        print(f"\nLast 5 Trades:")
        for t in result.trades[-5:]:
            icon = "✅" if t.pnl_pct > 0 else "❌"
            print(f"  {icon} {t.entry_time.strftime('%m-%d %H:%M')} -> {t.exit_time.strftime('%m-%d %H:%M')} | "
                  f"${t.entry_price:,.2f} -> ${t.exit_price:,.2f} | "
                  f"PnL: {t.pnl_pct*100:+.2f}% | {t.exit_reason}")


def main():
    parser = argparse.ArgumentParser(description="Backtest crypto strategies")
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair (default: BTCUSDT)")
    parser.add_argument("--days", type=int, default=30, help="Days of history (default: 30)")
    parser.add_argument("--strategy", default="ma_cross_trend_v2", help="Strategy ID from strategies.json")
    parser.add_argument("--interval", default="5m", help="Kline interval (default: 5m)")
    args = parser.parse_args()

    # Load strategy config
    config_path = Path(__file__).parent.parent / "config" / "strategies.json"
    with open(config_path) as f:
        all_configs = json.load(f)

    strategy_config = None
    for s in all_configs["strategies"]:
        if s["id"] == args.strategy:
            strategy_config = s
            break

    if not strategy_config:
        print(f"Strategy '{args.strategy}' not found in strategies.json")
        return

    if not strategy_config.get("enabled"):
        print(f"Warning: Strategy '{args.strategy}' is disabled in config")

    # Download history
    downloader = HistoryDownloader()
    klines = downloader.download(args.symbol, args.interval, args.days)

    if len(klines) < 300:
        print(f"Insufficient data: {len(klines)} candles. Need at least 300.")
        return

    # Run backtest
    engine = BacktestEngine(strategy_config)
    result = engine.run(klines)

    # Print results
    print_backtest_result(result)

    # Save results
    output_dir = Path(__file__).parent.parent / "backtest_results"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{args.strategy}_{args.symbol}_{args.days}d_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    result_dict = {
        "strategy_id": result.strategy_id,
        "symbol": result.symbol,
        "total_trades": result.total_trades,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "total_pnl_pct": result.total_pnl_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "start_balance": result.start_balance,
        "end_balance": result.end_balance,
        "trades": [
            {
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason,
            }
            for t in result.trades
        ],
    }

    with open(output_file, "w") as f:
        json.dump(result_dict, f, indent=2)

    print(f"\n📁 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
