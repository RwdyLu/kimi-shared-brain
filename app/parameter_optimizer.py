"""
Parameter Optimization Engine
Optimizes trading strategy parameters using various algorithms.
"""

import json
import logging
import random
import numpy as np
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OptimizationMethod(Enum):
    """Available optimization methods."""

    GRID_SEARCH = "grid_search"
    RANDOM_SEARCH = "random_search"
    BAYESIAN = "bayesian"
    GENETIC = "genetic"
    WALK_FORWARD = "walk_forward"


@dataclass
class OptimizationResult:
    """Result of parameter optimization."""

    best_params: Dict[str, Any]
    best_score: float
    method: OptimizationMethod
    iterations: int
    duration_seconds: float
    all_results: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "best_params": self.best_params,
            "best_score": self.best_score,
            "method": self.method.value,
            "iterations": self.iterations,
            "duration_seconds": self.duration_seconds,
            "top_results": sorted(self.all_results, key=lambda x: x.get("score", 0), reverse=True)[:10],
        }


class ParameterOptimizer:
    """
    Optimizes strategy parameters using multiple algorithms.

    Supports grid search, random search, genetic algorithms,
    and walk-forward optimization for robust parameter selection.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.results: List[OptimizationResult] = []

        self.logger.info("ParameterOptimizer initialized")

    def optimize(
        self,
        param_space: Dict[str, List],
        objective_func: Callable[[Dict], float],
        method: OptimizationMethod = OptimizationMethod.RANDOM_SEARCH,
        max_iterations: int = 100,
        target_score: Optional[float] = None,
    ) -> OptimizationResult:
        """
        Run parameter optimization.

        Args:
            param_space: Parameter ranges {name: [values]}
            objective_func: Function(params) -> score (higher is better)
            method: Optimization algorithm
            max_iterations: Max evaluations
            target_score: Stop if reached

        Returns:
            OptimizationResult
        """
        start_time = datetime.now()

        if method == OptimizationMethod.GRID_SEARCH:
            result = self._grid_search(param_space, objective_func, max_iterations)
        elif method == OptimizationMethod.RANDOM_SEARCH:
            result = self._random_search(param_space, objective_func, max_iterations)
        elif method == OptimizationMethod.GENETIC:
            result = self._genetic_optimize(param_space, objective_func, max_iterations)
        elif method == OptimizationMethod.WALK_FORWARD:
            result = self._walk_forward(param_space, objective_func, max_iterations)
        else:
            result = self._random_search(param_space, objective_func, max_iterations)

        duration = (datetime.now() - start_time).total_seconds()
        result.duration_seconds = duration

        self.results.append(result)

        self.logger.info(
            f"Optimization complete: {method.value} "
            f"best_score={result.best_score:.4f} "
            f"iterations={result.iterations} "
            f"time={duration:.1f}s"
        )

        return result

    def _grid_search(
        self, param_space: Dict[str, List], objective_func: Callable, max_iterations: int
    ) -> OptimizationResult:
        """Exhaustive grid search."""
        import itertools

        keys = list(param_space.keys())
        values = [param_space[k] for k in keys]

        all_combinations = list(itertools.product(*values))
        tested = all_combinations[:max_iterations]

        best_score = float("-inf")
        best_params = {}
        all_results = []

        for combo in tested:
            params = dict(zip(keys, combo))
            score = objective_func(params)

            all_results.append({"params": params, "score": score})

            if score > best_score:
                best_score = score
                best_params = params

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            method=OptimizationMethod.GRID_SEARCH,
            iterations=len(tested),
            all_results=all_results,
        )

    def _random_search(
        self, param_space: Dict[str, List], objective_func: Callable, max_iterations: int
    ) -> OptimizationResult:
        """Random search with optional early stopping."""
        best_score = float("-inf")
        best_params = {}
        all_results = []

        for i in range(max_iterations):
            params = {k: random.choice(v) for k, v in param_space.items()}
            score = objective_func(params)

            all_results.append({"params": params, "score": score})

            if score > best_score:
                best_score = score
                best_params = params
                self.logger.info(f"Iteration {i+1}: New best score={score:.4f}")

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            method=OptimizationMethod.RANDOM_SEARCH,
            iterations=max_iterations,
            all_results=all_results,
        )

    def _genetic_optimize(
        self,
        param_space: Dict[str, List],
        objective_func: Callable,
        max_iterations: int,
        population_size: int = 20,
        generations: int = 10,
    ) -> OptimizationResult:
        """Genetic algorithm optimization."""

        def create_individual():
            return {k: random.choice(v) for k, v in param_space.items()}

        def mutate(individual, mutation_rate=0.2):
            mutated = dict(individual)
            for key, values in param_space.items():
                if random.random() < mutation_rate:
                    current = mutated[key]
                    alternatives = [v for v in values if v != current]
                    if alternatives:
                        mutated[key] = random.choice(alternatives)
            return mutated

        def crossover(parent1, parent2):
            child = {}
            for key in param_space:
                child[key] = parent1[key] if random.random() < 0.5 else parent2[key]
            return child

        # Initialize population
        population = [create_individual() for _ in range(population_size)]

        best_score = float("-inf")
        best_params = {}
        all_results = []
        iteration = 0

        for gen in range(generations):
            if iteration >= max_iterations:
                break

            # Evaluate population
            scores = []
            for individual in population:
                score = objective_func(individual)
                scores.append((individual, score))
                all_results.append({"params": individual, "score": score})
                iteration += 1

                if score > best_score:
                    best_score = score
                    best_params = individual

            # Sort by score
            scores.sort(key=lambda x: x[1], reverse=True)

            # Select top 50%
            survivors = [ind for ind, _ in scores[: population_size // 2]]

            # Create next generation
            population = survivors[:]
            while len(population) < population_size:
                if len(survivors) >= 2 and random.random() < 0.7:
                    # Crossover
                    p1, p2 = random.sample(survivors, 2)
                    child = crossover(p1, p2)
                else:
                    # Mutation
                    child = mutate(random.choice(survivors))

                population.append(child)

            self.logger.info(f"Generation {gen+1}: best={scores[0][1]:.4f}")

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            method=OptimizationMethod.GENETIC,
            iterations=iteration,
            all_results=all_results,
        )

    def _walk_forward(
        self, param_space: Dict[str, List], objective_func: Callable, max_iterations: int
    ) -> OptimizationResult:
        """
        Walk-forward optimization.
        Tests parameters on multiple time periods to avoid overfitting.
        """
        best_score = float("-inf")
        best_params = {}
        all_results = []

        # Number of walk-forward periods
        n_periods = min(5, max_iterations // 20)

        for i in range(max_iterations):
            params = {k: random.choice(v) for k, v in param_space.items()}

            # Evaluate on multiple periods
            period_scores = []
            for period in range(n_periods):
                score = objective_func(params, period=period)
                period_scores.append(score)

            # Use average score across periods
            avg_score = sum(period_scores) / len(period_scores)
            # Penalize high variance
            variance = np.var(period_scores) if len(period_scores) > 1 else 0
            robust_score = avg_score - variance * 0.1

            all_results.append({"params": params, "score": robust_score, "period_scores": period_scores})

            if robust_score > best_score:
                best_score = robust_score
                best_params = params

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            method=OptimizationMethod.WALK_FORWARD,
            iterations=max_iterations,
            all_results=all_results,
        )

    def get_best_result(self) -> Optional[OptimizationResult]:
        """Get best overall result."""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.best_score)

    def compare_methods(self) -> Dict:
        """Compare optimization methods."""
        comparison = {}
        for result in self.results:
            method = result.method.value
            comparison[method] = {
                "best_score": result.best_score,
                "iterations": result.iterations,
                "duration": result.duration_seconds,
                "efficiency": result.best_score / max(result.duration_seconds, 0.001),
            }
        return comparison

    def export_results(self, filepath: str):
        """Export all results to JSON."""
        data = {
            "exported_at": datetime.now().isoformat(),
            "optimization_count": len(self.results),
            "results": [r.to_dict() for r in self.results],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Results exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    optimizer = ParameterOptimizer()

    # Sample parameter space
    param_space = {
        "fast_ma": [5, 10, 15, 20],
        "slow_ma": [30, 50, 100],
        "stop_loss": [1.0, 2.0, 3.0],
    }

    # Sample objective function (mock)
    def mock_objective(params):
        score = 0
        if params["fast_ma"] < params["slow_ma"]:
            score += 50
        score += params["stop_loss"] * 10
        score += random.gauss(0, 5)  # Noise
        return score

    # Run optimization
    result = optimizer.optimize(
        param_space=param_space, objective_func=mock_objective, method=OptimizationMethod.GENETIC, max_iterations=50
    )

    print("\nParameter Optimizer Demo")
    print("=" * 50)
    print(f"Method: {result.method.value}")
    print(f"Best Score: {result.best_score:.2f}")
    print(f"Best Params: {result.best_params}")
    print(f"Iterations: {result.iterations}")
    print(f"Duration: {result.duration_seconds:.2f}s")
    print(f"\nTop 5 Results:")
    for r in sorted(result.all_results, key=lambda x: x["score"], reverse=True)[:5]:
        print(f"  Score={r['score']:.2f}: {r['params']}")
