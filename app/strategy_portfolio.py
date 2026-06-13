"""
Strategy Portfolio Manager
Manages multiple strategies with capital allocation and correlation analysis.
"""

import json
import logging
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AllocationMethod(Enum):
    """Capital allocation methods."""

    EQUAL = "equal"
    RISK_PARITY = "risk_parity"
    SHARPE_WEIGHTED = "sharpe_weighted"
    INVERSE_VOL = "inverse_volatility"
    CUSTOM = "custom"


@dataclass
class PortfolioPosition:
    """Portfolio strategy allocation."""

    strategy_id: str
    symbol: str
    weight: float = 0.0
    allocation_pct: float = 0.0
    current_value: float = 0.0
    unrealized_pnl: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "weight": self.weight,
            "allocation_pct": self.allocation_pct,
            "current_value": self.current_value,
            "unrealized_pnl": self.unrealized_pnl,
        }


class StrategyPortfolio:
    """
    Manages a portfolio of trading strategies.

    Features:
    - Capital allocation across strategies
    - Correlation analysis
    - Risk-adjusted position sizing
    - Portfolio-level performance tracking
    """

    def __init__(self, total_capital: float = 100000.0):
        self.logger = logging.getLogger(__name__)

        self.total_capital = total_capital
        self.available_capital = total_capital

        # Positions
        self.positions: Dict[str, PortfolioPosition] = {}

        # Strategy returns history for correlation
        self.returns_history: Dict[str, List[float]] = {}

        # Performance
        self.equity_curve: List[Dict] = []

        self.logger.info(f"StrategyPortfolio initialized: ${total_capital:,.2f}")

    def add_strategy(self, strategy_id: str, symbol: str, weight: float = 1.0):
        """
        Add strategy to portfolio.

        Args:
            strategy_id: Strategy identifier
            symbol: Trading pair
            weight: Allocation weight
        """
        self.positions[strategy_id] = PortfolioPosition(strategy_id=strategy_id, symbol=symbol, weight=weight)

        self.returns_history[strategy_id] = []

        self.logger.info(f"Added {strategy_id} ({symbol}) with weight {weight}")

    def allocate_capital(self, method: AllocationMethod = AllocationMethod.EQUAL):
        """
        Allocate capital to strategies.

        Args:
            method: Allocation method
        """
        if not self.positions:
            return

        n = len(self.positions)

        if method == AllocationMethod.EQUAL:
            # Equal weight
            for pos in self.positions.values():
                pos.allocation_pct = 100.0 / n
                pos.current_value = self.total_capital / n

        elif method == AllocationMethod.RISK_PARITY:
            # Inverse variance weighting
            weights = self._calculate_risk_parity_weights()
            for sid, w in weights.items():
                if sid in self.positions:
                    self.positions[sid].allocation_pct = w * 100
                    self.positions[sid].current_value = self.total_capital * w

        elif method == AllocationMethod.SHARPE_WEIGHTED:
            # Weight by Sharpe ratio
            # Would need Sharpe data, simplified here
            for pos in self.positions.values():
                pos.allocation_pct = 100.0 / n
                pos.current_value = self.total_capital / n

        elif method == AllocationMethod.INVERSE_VOL:
            # Weight by inverse volatility
            vols = {}
            for sid, returns in self.returns_history.items():
                if returns:
                    vol = np.std(returns) if len(returns) > 1 else 1
                    vols[sid] = vol

            if vols:
                inv_vols = {sid: 1 / v for sid, v in vols.items()}
                total = sum(inv_vols.values())
                weights = {sid: w / total for sid, w in inv_vols.items()}

                for sid, w in weights.items():
                    if sid in self.positions:
                        self.positions[sid].allocation_pct = w * 100
                        self.positions[sid].current_value = self.total_capital * w

        self.logger.info(f"Capital allocated using {method.value}")

    def _calculate_risk_parity_weights(self) -> Dict[str, float]:
        """Calculate risk parity weights."""
        variances = {}
        for sid, returns in self.returns_history.items():
            if len(returns) > 1:
                variances[sid] = np.var(returns)
            else:
                variances[sid] = 1.0

        if not variances:
            n = len(self.positions)
            return {sid: 1 / n for sid in self.positions}

        # Inverse variance weights
        inv_vars = {sid: 1 / v for sid, v in variances.items()}
        total = sum(inv_vars.values())
        return {sid: w / total for sid, w in inv_vars.items()}

    def update_returns(self, strategy_id: str, daily_return: float):
        """
        Update strategy returns history.

        Args:
            strategy_id: Strategy identifier
            daily_return: Daily return value
        """
        if strategy_id in self.returns_history:
            self.returns_history[strategy_id].append(daily_return)

    def calculate_correlation_matrix(self) -> Dict:
        """
        Calculate correlation matrix between strategies.

        Returns:
            Correlation matrix dict
        """
        # Filter strategies with enough data
        valid = {sid: returns for sid, returns in self.returns_history.items() if len(returns) >= 10}

        if len(valid) < 2:
            return {"error": "Need at least 2 strategies with 10+ returns"}

        # Calculate pairwise correlations
        matrix = {}
        sids = list(valid.keys())

        for i, sid1 in enumerate(sids):
            matrix[sid1] = {}
            for j, sid2 in enumerate(sids):
                if i == j:
                    matrix[sid1][sid2] = 1.0
                else:
                    corr = np.corrcoef(valid[sid1], valid[sid2])[0, 1]
                    matrix[sid1][sid2] = float(corr)

        return {
            "strategies": sids,
            "matrix": matrix,
        }

    def get_portfolio_stats(self) -> Dict:
        """Get portfolio statistics."""
        total_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        total_value = sum(p.current_value for p in self.positions.values())

        return {
            "total_capital": self.total_capital,
            "total_value": total_value,
            "unrealized_pnl": total_pnl,
            "return_pct": (total_value / self.total_capital - 1) * 100,
            "num_strategies": len(self.positions),
            "allocations": {sid: pos.to_dict() for sid, pos in self.positions.items()},
        }

    def export_portfolio(self, filepath: str):
        """Export portfolio to JSON."""
        data = {
            "exported_at": datetime.now().isoformat(),
            "total_capital": self.total_capital,
            "stats": self.get_portfolio_stats(),
            "correlation_matrix": self.calculate_correlation_matrix(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Portfolio exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    portfolio = StrategyPortfolio(total_capital=100000)

    # Add strategies
    portfolio.add_strategy("MA_Cross", "BTCUSDT", weight=1.0)
    portfolio.add_strategy("RSI_Strat", "ETHUSDT", weight=0.8)
    portfolio.add_strategy("SNR_Strat", "BTCUSDT", weight=1.2)

    # Simulate returns
    for i in range(20):
        portfolio.update_returns("MA_Cross", np.random.normal(0.001, 0.02))
        portfolio.update_returns("RSI_Strat", np.random.normal(0.001, 0.015))
        portfolio.update_returns("SNR_Strat", np.random.normal(0.002, 0.025))

    # Allocate
    portfolio.allocate_capital(AllocationMethod.INVERSE_VOL)

    print("Strategy Portfolio Demo")
    print("=" * 50)
    print(f"Stats: {portfolio.get_portfolio_stats()}")
    print(f"\nCorrelation: {portfolio.calculate_correlation_matrix()}")
