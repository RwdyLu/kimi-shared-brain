"""
Strategy Parameter Generator
Generates trading strategy variations by exploring parameter space.
"""
import json
import logging
import random
import itertools
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StrategyType(Enum):
    """Types of strategies that can be generated."""
    MA_CROSSOVER = "ma_crossover"
    RSI = "rsi"
    SNR = "snr"
    BOLLINGER = "bollinger"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"


@dataclass
class StrategyParams:
    """Strategy parameter set."""
    strategy_type: StrategyType
    symbol: str
    timeframe: str
    params: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    tested: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'strategy_type': self.strategy_type.value,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'params': self.params,
            'score': self.score,
            'tested': self.tested,
        }


class StrategyGenerator:
    """
    Generates strategy parameter combinations for testing.
    
    Uses grid search, random search, and genetic algorithm approaches
    to explore the parameter space efficiently.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Parameter ranges for each strategy type
        self.param_ranges: Dict[StrategyType, Dict[str, List]] = {
            StrategyType.MA_CROSSOVER: {
                'fast_period': [5, 10, 15, 20],
                'slow_period': [30, 50, 100, 200],
                'entry_threshold': [0.0, 0.5, 1.0],
            },
            StrategyType.RSI: {
                'period': [7, 14, 21],
                'oversold': [20, 25, 30],
                'overbought': [70, 75, 80],
            },
            StrategyType.SNR: {
                'lookback': [50, 100, 200],
                'touch_threshold': [0.5, 1.0, 2.0],
                'min_touches': [2, 3, 5],
            },
            StrategyType.BOLLINGER: {
                'period': [10, 20, 30],
                'std_dev': [1.5, 2.0, 2.5],
            },
            StrategyType.MOMENTUM: {
                'lookback': [10, 20, 30],
                'threshold': [0.02, 0.05, 0.1],
            },
            StrategyType.MEAN_REVERSION: {
                'period': [10, 20, 50],
                'zscore_threshold': [1.5, 2.0, 2.5],
            },
        }
        
        # Generated strategies
        self.generated: List[StrategyParams] = []
        self.tested_count = 0
        
        self.logger.info("StrategyGenerator initialized")
    
    def generate_grid(self,
                     strategy_type: StrategyType,
                     symbol: str = "BTCUSDT",
                     timeframe: str = "1h") -> List[StrategyParams]:
        """
        Generate all combinations via grid search.
        
        Args:
            strategy_type: Type of strategy
            symbol: Trading pair
            timeframe: Time interval
            
        Returns:
            List of StrategyParams
        """
        ranges = self.param_ranges.get(strategy_type, {})
        
        # Generate all combinations
        keys = list(ranges.keys())
        values = [ranges[k] for k in keys]
        
        strategies = []
        for combo in itertools.product(*values):
            params = dict(zip(keys, combo))
            
            # Validate params (e.g., fast MA < slow MA)
            if strategy_type == StrategyType.MA_CROSSOVER:
                if params.get('fast_period', 0) >= params.get('slow_period', 0):
                    continue
            
            strategy = StrategyParams(
                strategy_type=strategy_type,
                symbol=symbol,
                time frame=timeframe,
                params=params
            )
            strategies.append(strategy)
        
        self.generated.extend(strategies)
        
        self.logger.info(
            f"Generated {len(strategies)} grid combinations "
            f"for {strategy_type.value}"
        )
        
        return strategies
    
    def generate_random(self,
                       strategy_type: StrategyType,
                       count: int = 10,
                       symbol: str = "BTCUSDT",
                       timeframe: str = "1h") -> List[StrategyParams]:
        """
        Generate random parameter combinations.
        
        Args:
            strategy_type: Type of strategy
            count: Number to generate
            symbol: Trading pair
            timeframe: Time interval
            
        Returns:
            List of StrategyParams
        """
        ranges = self.param_ranges.get(strategy_type, {})
        strategies = []
        
        for _ in range(count):
            params = {}
            for key, values in ranges.items():
                params[key] = random.choice(values)
            
            # Validate
            if strategy_type == StrategyType.MA_CROSSOVER:
                if params.get('fast_period', 0) >= params.get('slow_period', 0):
                    # Swap to make valid
                    params['fast_period'], params['slow_period'] = \
                        params['slow_period'], params['fast_period']
            
            strategy = StrategyParams(
                strategy_type=strategy_type,
                symbol=symbol,
                timeframe=timeframe,
                params=params
            )
            strategies.append(strategy)
        
        self.generated.extend(strategies)
        
        self.logger.info(
            f"Generated {len(strategies)} random combinations "
            f"for {strategy_type.value}"
        )
        
        return strategies
    
    def mutate_strategy(self,
                       strategy: StrategyParams,
                       mutation_rate: float = 0.3) -> StrategyParams:
        """
        Mutate a strategy's parameters (genetic algorithm).
        
        Args:
            strategy: Strategy to mutate
            mutation_rate: Probability of mutating each param
            
        Returns:
            Mutated StrategyParams
        """
        ranges = self.param_ranges.get(strategy.strategy_type, {})
        new_params = dict(strategy.params)
        
        for key, values in ranges.items():
            if random.random() < mutation_rate and key in new_params:
                # Pick a different value
                current = new_params[key]
                alternatives = [v for v in values if v != current]
                if alternatives:
                    new_params[key] = random.choice(alternatives)
        
        mutated = StrategyParams(
            strategy_type=strategy.strategy_type,
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
            params=new_params
        )
        
        return mutated
    
    def crossover(self,
                  parent1: StrategyParams,
                  parent2: StrategyParams) -> StrategyParams:
        """
        Crossover two strategies (genetic algorithm).
        
        Args:
            parent1: First parent
            parent2: Second parent
            
        Returns:
            Child StrategyParams
        """
        child_params = {}
        
        for key in parent1.params:
            child_params[key] = parent1.params[key] if random.random() < 0.5 else parent2.params.get(key, parent1.params[key])
        
        child = StrategyParams(
            strategy_type=parent1.strategy_type,
            symbol=parent1.symbol,
            timeframe=parent1.timeframe,
            params=child_params
        )
        
        return child
    
    def get_untested(self, limit: int = 10) -> List[StrategyParams]:
        """Get untested strategies."""
        untested = [s for s in self.generated if not s.tested]
        return untested[:limit]
    
    def mark_tested(self, strategy_id: int, score: float):
        """Mark strategy as tested with score."""
        if 0 <= strategy_id < len(self.generated):
            self.generated[strategy_id].tested = True
            self.generated[strategy_id].score = score
            self.tested_count += 1
    
    def get_top_strategies(self, n: int = 10) -> List[StrategyParams]:
        """Get top N strategies by score."""
        tested = [s for s in self.generated if s.tested]
        return sorted(tested, key=lambda s: s.score, reverse=True)[:n]
    
    def get_stats(self) -> Dict:
        """Get generation statistics."""
        by_type = {}
        for s in self.generated:
            key = s.strategy_type.value
            by_type[key] = by_type.get(key, {'total': 0, 'tested': 0})
            by_type[key]['total'] += 1
            if s.tested:
                by_type[key]['tested'] += 1
        
        return {
            'total_generated': len(self.generated),
            'tested': self.tested_count,
            'untested': len(self.generated) - self.tested_count,
            'by_type': by_type,
            'top_score': max((s.score for s in self.generated if s.tested), default=0),
        }
    
    def export_params(self, filepath: str, strategies: Optional[List[StrategyParams]] = None):
        """Export strategies to JSON."""
        strategies = strategies or self.generated
        
        data = {
            'exported_at': datetime.now().isoformat(),
            'count': len(strategies),
            'strategies': [s.to_dict() for s in strategies]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Exported {len(strategies)} strategies to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    generator = StrategyGenerator()
    
    # Generate grid for MA crossover
    ma_strategies = generator.generate_grid(
        StrategyType.MA_CROSSOVER,
        symbol="BTCUSDT",
        timeframe="4h"
    )
    
    # Generate random RSI strategies
    rsi_strategies = generator.generate_random(
        StrategyType.RSI,
        count=5,
        symbol="ETHUSDT",
        timeframe="1h"
    )
    
    print("Strategy Generator Demo")
    print("=" * 50)
    print(f"MA Crossover: {len(ma_strategies)} combinations")
    print(f"RSI: {len(rsi_strategies)} random")
    print(f"\nStats: {generator.get_stats()}")
    
    # Show first strategy
    if ma_strategies:
        s = ma_strategies[0]
        print(f"\nExample: {s.strategy_type.value}")
        print(f"  Symbol: {s.symbol}")
        print(f"  Params: {s.params}")
