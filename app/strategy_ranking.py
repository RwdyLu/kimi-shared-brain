"""
Strategy Ranking & Selection
Ranks and selects best strategies based on multiple performance criteria.
"""

import json
import logging
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RankingMethod(Enum):
    """Methods for ranking strategies."""

    SHARPE = "sharpe"
    RETURN = "return"
    DRAWDOWN = "drawdown"
    CALMAR = "calmar"
    COMPOSITE = "composite"


@dataclass
class StrategyScore:
    """Strategy performance score."""

    strategy_id: str
    symbol: str
    timeframe: str

    # Raw metrics
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0

    # Composite score
    composite_score: float = 0.0
    rank: int = 0
    tier: str = "unranked"

    def to_dict(self) -> Dict:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "composite_score": self.composite_score,
            "rank": self.rank,
            "tier": self.tier,
        }


class StrategyRanking:
    """
    Strategy ranking and selection system.

    Evaluates strategies using multiple criteria and produces
    ranked lists with tier assignments (S/A/B/C/D).
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Scoring weights for composite ranking
        self.weights = {
            "sharpe_ratio": 0.30,
            "total_return": 0.25,
            "max_drawdown": 0.20,  # Lower is better
            "win_rate": 0.15,
            "profit_factor": 0.10,
        }

        # Tier thresholds (composite score)
        self.tiers = {
            "S": 90,
            "A": 75,
            "B": 60,
            "C": 45,
            "D": 30,
        }

        # History
        self.rankings: List[StrategyScore] = []

        self.logger.info("StrategyRanking initialized")

    def add_strategy(self, score: StrategyScore):
        """Add strategy for ranking."""
        self.rankings.append(score)

    def calculate_composite(self, score: StrategyScore) -> float:
        """
        Calculate composite score from metrics.

        Args:
            score: StrategyScore with raw metrics

        Returns:
            Composite score (0-100)
        """
        # Normalize each metric to 0-100 scale

        # Sharpe: typical range -2 to 3, map to 0-100
        sharpe_norm = max(0, min(100, (score.sharpe_ratio + 2) / 5 * 100))

        # Return: typical -50% to +100%, map to 0-100
        return_norm = max(0, min(100, (score.total_return + 50) / 150 * 100))

        # Drawdown: 0 to -50%, lower is better, invert
        dd_norm = max(0, min(100, (50 + score.max_drawdown) / 50 * 100))

        # Win rate: 0 to 100%
        wr_norm = max(0, min(100, score.win_rate))

        # Profit factor: 0 to 3, map to 0-100
        pf_norm = max(0, min(100, score.profit_factor / 3 * 100))

        # Weighted composite
        composite = (
            sharpe_norm * self.weights["sharpe_ratio"]
            + return_norm * self.weights["total_return"]
            + dd_norm * self.weights["max_drawdown"]
            + wr_norm * self.weights["win_rate"]
            + pf_norm * self.weights["profit_factor"]
        )

        return composite

    def rank_strategies(self, method: RankingMethod = RankingMethod.COMPOSITE) -> List[StrategyScore]:
        """
        Rank all strategies.

        Args:
            method: Ranking method

        Returns:
            Ranked list of StrategyScore
        """
        if not self.rankings:
            return []

        # Calculate composite scores
        for score in self.rankings:
            score.composite_score = self.calculate_composite(score)

        # Sort based on method
        if method == RankingMethod.SHARPE:
            self.rankings.sort(key=lambda s: s.sharpe_ratio, reverse=True)
        elif method == RankingMethod.RETURN:
            self.rankings.sort(key=lambda s: s.total_return, reverse=True)
        elif method == RankingMethod.DRAWDOWN:
            self.rankings.sort(key=lambda s: s.max_drawdown)  # Ascending
        elif method == RankingMethod.CALMAR:
            # Calmar = return / drawdown
            for s in self.rankings:
                s.calmar = s.total_return / abs(s.max_drawdown) if s.max_drawdown != 0 else 0
            self.rankings.sort(key=lambda s: getattr(s, "calmar", 0), reverse=True)
        else:
            # Composite
            self.rankings.sort(key=lambda s: s.composite_score, reverse=True)

        # Assign ranks and tiers
        for i, score in enumerate(self.rankings, 1):
            score.rank = i

            # Assign tier
            for tier, threshold in sorted(self.tiers.items(), key=lambda x: x[1], reverse=True):
                if score.composite_score >= threshold:
                    score.tier = tier
                    break
            else:
                score.tier = "F"

        self.logger.info(f"Ranked {len(self.rankings)} strategies")

        return self.rankings

    def get_top_strategies(self, n: int = 5) -> List[StrategyScore]:
        """Get top N strategies."""
        ranked = self.rank_strategies()
        return ranked[:n]

    def get_by_tier(self, tier: str) -> List[StrategyScore]:
        """Get strategies in specific tier."""
        ranked = self.rank_strategies()
        return [s for s in ranked if s.tier == tier]

    def eliminate_weak(self, min_tier: str = "C") -> List[StrategyScore]:
        """
        Eliminate strategies below minimum tier.

        Args:
            min_tier: Minimum acceptable tier

        Returns:
            Eliminated strategies
        """
        tier_order = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        min_level = tier_order.get(min_tier, 0)

        eliminated = [s for s in self.rankings if tier_order.get(s.tier, 0) < min_level]
        kept = [s for s in self.rankings if tier_order.get(s.tier, 0) >= min_level]

        self.rankings = kept

        self.logger.info(f"Eliminated {len(eliminated)} strategies below tier {min_tier}")

        return eliminated

    def compare_strategies(self, strategy_ids: List[str]) -> Dict:
        """
        Compare specific strategies side by side.

        Args:
            strategy_ids: List of strategy IDs to compare

        Returns:
            Comparison table
        """
        selected = [s for s in self.rankings if s.strategy_id in strategy_ids]

        return {
            "strategies": [s.to_dict() for s in selected],
            "winner": selected[0].strategy_id if selected else None,
            "metrics": {
                "best_return": max((s.total_return for s in selected), default=0),
                "best_sharpe": max((s.sharpe_ratio for s in selected), default=0),
                "lowest_drawdown": min((s.max_drawdown for s in selected), default=0),
            },
        }

    def export_rankings(self, filepath: str):
        """Export rankings to JSON."""
        ranked = self.rank_strategies()

        data = {
            "exported_at": datetime.now().isoformat(),
            "method": "composite",
            "weights": self.weights,
            "total": len(ranked),
            "by_tier": {},
            "rankings": [s.to_dict() for s in ranked],
        }

        # Count by tier
        for s in ranked:
            data["by_tier"][s.tier] = data["by_tier"].get(s.tier, 0) + 1

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Rankings exported to {filepath}")

    def reset(self):
        """Reset rankings."""
        self.rankings.clear()
        self.logger.info("Rankings reset")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    ranking = StrategyRanking()

    # Add sample strategies
    strategies = [
        StrategyScore(
            "MA_10_50",
            "BTCUSDT",
            "4h",
            total_return=25,
            sharpe_ratio=1.5,
            max_drawdown=-8,
            win_rate=65,
            profit_factor=2.1,
        ),
        StrategyScore(
            "RSI_14",
            "ETHUSDT",
            "1h",
            total_return=18,
            sharpe_ratio=1.2,
            max_drawdown=-12,
            win_rate=58,
            profit_factor=1.8,
        ),
        StrategyScore(
            "SNR_v1",
            "BTCUSDT",
            "4h",
            total_return=30,
            sharpe_ratio=1.8,
            max_drawdown=-6,
            win_rate=70,
            profit_factor=2.5,
        ),
        StrategyScore(
            "Bad_Strategy",
            "SOLUSDT",
            "1h",
            total_return=-5,
            sharpe_ratio=-0.3,
            max_drawdown=-25,
            win_rate=35,
            profit_factor=0.8,
        ),
    ]

    for s in strategies:
        ranking.add_strategy(s)

    # Rank
    ranked = ranking.rank_strategies()

    print("Strategy Ranking Demo")
    print("=" * 50)
    for s in ranked:
        print(f"#{s.rank} [{s.tier}] {s.strategy_id}: {s.composite_score:.1f} pts")
        print(f"   Return: {s.total_return:.1f}%, Sharpe: {s.sharpe_ratio:.2f}, DD: {s.max_drawdown:.1f}%")

    # Eliminate weak
    eliminated = ranking.eliminate_weak("C")
    print(f"\nEliminated: {[s.strategy_id for s in eliminated]}")
    print(f"Remaining: {len(ranking.rankings)} strategies")
