"""
Automated Backtest Pipeline
Runs strategy backtests automatically with reporting and comparison.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class BacktestStatus(Enum):
    """Backtest execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BacktestResult:
    """Result of a single backtest run."""

    strategy_id: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime

    # Performance metrics
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0

    # Status
    status: BacktestStatus = BacktestStatus.PENDING
    error_message: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
        }


class BacktestPipeline:
    """
    Automated backtest pipeline.

    Manages multiple backtest runs, tracks results, and generates
    comparison reports for strategy evaluation.
    """

    def __init__(self, results_dir: str = "backtest_results"):
        self.logger = logging.getLogger(__name__)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)

        # Active and completed backtests
        self.backtests: Dict[str, BacktestResult] = {}
        self.queue: List[str] = []

        self.logger.info("BacktestPipeline initialized")

    def schedule_backtest(
        self, strategy_id: str, symbol: str, timeframe: str, start_date: datetime, end_date: datetime
    ) -> str:
        """
        Schedule a backtest run.

        Args:
            strategy_id: Strategy to test
            symbol: Trading pair
            timeframe: Time interval
            start_date: Test start
            end_date: Test end

        Returns:
            Backtest ID
        """
        backtest_id = f"BT_{strategy_id}_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        result = BacktestResult(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            status=BacktestStatus.PENDING,
        )

        self.backtests[backtest_id] = result
        self.queue.append(backtest_id)

        self.logger.info(f"Scheduled backtest: {backtest_id}")

        return backtest_id

    def run_backtest(self, backtest_id: str, strategy_func: Callable, data: List[Dict]) -> BacktestResult:
        """
        Execute a scheduled backtest.

        Args:
            backtest_id: Backtest to run
            strategy_func: Function(data) -> signals
            data: Historical price data

        Returns:
            BacktestResult
        """
        if backtest_id not in self.backtests:
            raise ValueError(f"Backtest not found: {backtest_id}")

        result = self.backtests[backtest_id]
        result.status = BacktestStatus.RUNNING

        start_time = datetime.now()

        try:
            # Run strategy on data
            signals = strategy_func(data)

            # Calculate performance
            metrics = self._calculate_metrics(data, signals)

            result.total_return = metrics["total_return"]
            result.sharpe_ratio = metrics["sharpe_ratio"]
            result.max_drawdown = metrics["max_drawdown"]
            result.win_rate = metrics["win_rate"]
            result.profit_factor = metrics["profit_factor"]
            result.total_trades = metrics["total_trades"]
            result.status = BacktestStatus.COMPLETED

            self.logger.info(f"Backtest complete: {backtest_id} " f"return={result.total_return:.2f}%")

        except Exception as e:
            result.status = BacktestStatus.FAILED
            result.error_message = str(e)
            self.logger.error(f"Backtest failed: {backtest_id} - {e}")

        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        # Save result
        self._save_result(backtest_id)

        # Remove from queue
        if backtest_id in self.queue:
            self.queue.remove(backtest_id)

        return result

    def _calculate_metrics(self, data: List[Dict], signals: List[Dict]) -> Dict:
        """
        Calculate backtest performance metrics.

        Args:
            data: Price data
            signals: Strategy signals

        Returns:
            Performance metrics
        """
        # Mock calculation - would use actual trade simulation
        returns = []
        wins = 0
        losses = 0

        for signal in signals:
            # Simulate trade result
            if signal.get("direction") == "buy":
                # Random outcome for demo
                import random

                pnl = random.gauss(0, 2)
                returns.append(pnl)
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

        total_trades = len(signals)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        total_return = sum(returns) if returns else 0

        # Sharpe (simplified)
        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std = variance**0.5
            sharpe = mean_return / std if std > 0 else 0
        else:
            sharpe = 0

        # Profit factor
        gross_profit = sum(r for r in returns if r > 0)
        gross_loss = abs(sum(r for r in returns if r < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Max drawdown
        cumulative = 0
        max_dd = 0
        peak = 0
        for r in returns:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": total_trades,
        }

    def _save_result(self, backtest_id: str):
        """Save backtest result to disk."""
        result = self.backtests[backtest_id]
        filepath = self.results_dir / f"{backtest_id}.json"

        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    def run_batch(self, configs: List[Dict], strategy_func: Callable, data: List[Dict]) -> List[BacktestResult]:
        """
        Run multiple backtests in batch.

        Args:
            configs: List of backtest configurations
            strategy_func: Strategy function
            data: Historical data

        Returns:
            List of BacktestResult
        """
        results = []

        for config in configs:
            backtest_id = self.schedule_backtest(
                strategy_id=config["strategy_id"],
                symbol=config["symbol"],
                timeframe=config["timeframe"],
                start_date=config["start_date"],
                end_date=config["end_date"],
            )

            result = self.run_backtest(backtest_id, strategy_func, data)
            results.append(result)

        return results

    def compare_results(self, backtest_ids: Optional[List[str]] = None) -> Dict:
        """
        Compare multiple backtest results.

        Args:
            backtest_ids: IDs to compare (None = all completed)

        Returns:
            Comparison report
        """
        if backtest_ids is None:
            backtest_ids = [bid for bid, bt in self.backtests.items() if bt.status == BacktestStatus.COMPLETED]

        results = [self.backtests[bid] for bid in backtest_ids if bid in self.backtests]

        if not results:
            return {"error": "No completed backtests to compare"}

        # Rank by different metrics
        by_return = sorted(results, key=lambda r: r.total_return, reverse=True)
        by_sharpe = sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)
        by_drawdown = sorted(results, key=lambda r: r.max_drawdown)

        return {
            "count": len(results),
            "best_return": {
                "strategy": by_return[0].strategy_id,
                "return": by_return[0].total_return,
            },
            "best_sharpe": {
                "strategy": by_sharpe[0].strategy_id,
                "sharpe": by_sharpe[0].sharpe_ratio,
            },
            "lowest_drawdown": {
                "strategy": by_drawdown[0].strategy_id,
                "drawdown": by_drawdown[0].max_drawdown,
            },
            "comparison_table": [
                {
                    "strategy": r.strategy_id,
                    "symbol": r.symbol,
                    "return": r.total_return,
                    "sharpe": r.sharpe_ratio,
                    "drawdown": r.max_drawdown,
                    "win_rate": r.win_rate,
                    "trades": r.total_trades,
                }
                for r in results
            ],
        }

    def get_queue_status(self) -> Dict:
        """Get current queue status."""
        pending = [bid for bid in self.queue if self.backtests[bid].status == BacktestStatus.PENDING]
        running = [bid for bid in self.queue if self.backtests[bid].status == BacktestStatus.RUNNING]

        return {
            "pending": len(pending),
            "running": len(running),
            "completed": len(self.backtests) - len(self.queue),
            "total": len(self.backtests),
            "queue": self.queue[:5],  # First 5
        }

    def export_report(self, filepath: str):
        """Export full backtest report."""
        completed = [bt.to_dict() for bt in self.backtests.values() if bt.status == BacktestStatus.COMPLETED]

        report = {
            "generated_at": datetime.now().isoformat(),
            "total_backtests": len(self.backtests),
            "completed": len(completed),
            "results": completed,
            "comparison": self.compare_results(),
        }

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Report exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    pipeline = BacktestPipeline()

    # Schedule backtests
    configs = [
        {
            "strategy_id": "MA_Cross_10_50",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "start_date": datetime.now() - timedelta(days=30),
            "end_date": datetime.now(),
        },
        {
            "strategy_id": "RSI_14_30_70",
            "symbol": "ETHUSDT",
            "timeframe": "4h",
            "start_date": datetime.now() - timedelta(days=30),
            "end_date": datetime.now(),
        },
    ]

    # Mock strategy function
    def mock_strategy(data):
        import random

        return [{"direction": "buy", "price": d["close"]} for d in data if random.random() > 0.7]

    # Mock data
    mock_data = [{"close": 45000 + i * 10} for i in range(100)]

    # Run batch
    results = pipeline.run_batch(configs, mock_strategy, mock_data)

    print("\nBacktest Pipeline Demo")
    print("=" * 50)
    print(f"Completed: {len(results)} backtests")

    for r in results:
        print(f"\n{r.strategy_id}:")
        print(f"  Return: {r.total_return:.2f}%")
        print(f"  Sharpe: {r.sharpe_ratio:.2f}")
        print(f"  Win Rate: {r.win_rate:.1f}%")
        print(f"  Trades: {r.total_trades}")

    # Compare
    comparison = pipeline.compare_results()
    print(f"\nComparison:")
    print(f"  Best Return: {comparison['best_return']}")
    print(f"  Best Sharpe: {comparison['best_sharpe']}")
