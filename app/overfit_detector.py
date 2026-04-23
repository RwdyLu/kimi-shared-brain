"""
Overfitting Detection System
Detects strategy overfitting using multiple statistical tests.
"""
import json
import logging
import random
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OverfitLevel(Enum):
    """Overfitting severity levels."""
    NONE = "none"           # No overfitting detected
    MILD = "mild"           # Slight concerns
    MODERATE = "moderate"   # Significant overfitting
    SEVERE = "severe"       # Major overfitting


@dataclass
class OverfitReport:
    """Overfitting analysis report."""
    strategy_id: str
    overall_level: OverfitLevel = OverfitLevel.NONE
    
    # Test results
    insample_score: float = 0.0
    outsample_score: float = 0.0
    degradation: float = 0.0
    
    monte_carlo_pvalue: float = 1.0
    parameter_stability: float = 1.0
    trade_consistency: float = 1.0
    
    warnings: List[str] = field(default_factory=list)
    passed: bool = True
    
    def to_dict(self) -> Dict:
        return {
            'strategy_id': self.strategy_id,
            'overall_level': self.overall_level.value,
            'insample_score': self.insample_score,
            'outsample_score': self.outsample_score,
            'degradation': self.degradation,
            'monte_carlo_pvalue': self.monte_carlo_pvalue,
            'parameter_stability': self.parameter_stability,
            'trade_consistency': self.trade_consistency,
            'warnings': self.warnings,
            'passed': self.passed,
        }


class OverfitDetector:
    """
    Detects strategy overfitting using statistical tests.
    
    Tests include:
    - In-sample vs out-of-sample degradation
    - Monte Carlo permutation test
    - Parameter stability analysis
    - Trade distribution consistency
    """
    
    def __init__(self,
                 degradation_threshold: float = 0.30,
                 mc_pvalue_threshold: float = 0.05,
                 stability_threshold: float = 0.50):
        self.logger = logging.getLogger(__name__)
        
        # Thresholds
        self.degradation_threshold = degradation_threshold
        self.mc_pvalue_threshold = mc_pvalue_threshold
        self.stability_threshold = stability_threshold
        
        self.logger.info("OverfitDetector initialized")
    
    def test_insample_degradation(self,
                                   insample_return: float,
                                   outsample_return: float) -> Tuple[float, bool, str]:
        """
        Test in-sample vs out-of-sample performance degradation.
        
        Args:
            insample_return: In-sample total return
            outsample_return: Out-of-sample total return
            
        Returns:
            (degradation_ratio, passed, message)
        """
        if insample_return == 0:
            return 0.0, True, "No in-sample return to compare"
        
        degradation = (insample_return - outsample_return) / abs(insample_return)
        
        passed = degradation < self.degradation_threshold
        
        if not passed:
            msg = f"Severe degradation: {degradation*100:.1f}% (threshold: {self.degradation_threshold*100:.1f}%)"
        else:
            msg = f"Acceptable degradation: {degradation*100:.1f}%"
        
        return degradation, passed, msg
    
    def monte_carlo_test(self,
                        returns: List[float],
                        n_permutations: int = 1000) -> Tuple[float, bool, str]:
        """
        Monte Carlo permutation test.
        
        Tests if strategy returns are significantly better than random.
        
        Args:
            returns: Strategy returns
            n_permutations: Number of random permutations
            
        Returns:
            (p_value, passed, message)
        """
        if len(returns) < 10:
            return 1.0, True, "Too few trades for MC test"
        
        actual_sharpe = self._calculate_sharpe(returns)
        
        # Generate random permutations
        random_sharpes = []
        for _ in range(n_permutations):
            shuffled = returns.copy()
            random.shuffle(shuffled)
            random_sharpes.append(self._calculate_sharpe(shuffled))
        
        # P-value: proportion of random that beat actual
        p_value = sum(1 for r in random_sharpes if r >= actual_sharpe) / n_permutations
        
        passed = p_value < self.mc_pvalue_threshold
        
        if not passed:
            msg = f"MC p-value: {p_value:.3f} - not significantly better than random"
        else:
            msg = f"MC p-value: {p_value:.3f} - significantly better than random"
        
        return p_value, passed, msg
    
    def _calculate_sharpe(self, returns: List[float]) -> float:
        """Calculate Sharpe ratio."""
        if not returns:
            return 0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = variance ** 0.5
        return mean / std if std > 0 else 0
    
    def test_parameter_stability(self,
                                  param_results: Dict[str, List[float]]) -> Tuple[float, bool, str]:
        """
        Test parameter stability across different periods.
        
        Args:
            param_results: {param_name: [results per period]}
            
        Returns:
            (stability_score, passed, message)
        """
        if not param_results:
            return 1.0, True, "No parameter results"
        
        stability_scores = []
        
        for param, results in param_results.items():
            if len(results) < 2:
                continue
            
            # Coefficient of variation (CV)
            mean = sum(results) / len(results)
            variance = sum((r - mean) ** 2 for r in results) / len(results)
            std = variance ** 0.5
            
            cv = std / abs(mean) if mean != 0 else float('inf')
            # Invert: lower CV = higher stability
            stability = max(0, 1 - cv)
            stability_scores.append(stability)
        
        avg_stability = sum(stability_scores) / len(stability_scores) if stability_scores else 1.0
        passed = avg_stability >= self.stability_threshold
        
        if not passed:
            msg = f"Parameter instability: {avg_stability:.2f} (threshold: {self.stability_threshold})"
        else:
            msg = f"Parameter stability: {avg_stability:.2f}"
        
        return avg_stability, passed, msg
    
    def test_trade_consistency(self,
                               monthly_returns: List[float]) -> Tuple[float, bool, str]:
        """
        Test trade consistency across months.
        
        Args:
            monthly_returns: Returns per month
            
        Returns:
            (consistency_score, passed, message)
        """
        if len(monthly_returns) < 3:
            return 1.0, True, "Too few months"
        
        # Calculate percentage of positive months
        positive_months = sum(1 for r in monthly_returns if r > 0)
        consistency = positive_months / len(monthly_returns)
        
        passed = consistency >= 0.5  # At least 50% positive months
        
        if not passed:
            msg = f"Only {consistency*100:.0f}% positive months"
        else:
            msg = f"{consistency*100:.0f}% positive months"
        
        return consistency, passed, msg
    
    def analyze(self,
               strategy_id: str,
               insample_return: float,
               outsample_return: float,
               returns: List[float],
               monthly_returns: List[float],
               param_results: Optional[Dict] = None) -> OverfitReport:
        """
        Full overfitting analysis.
        
        Args:
            strategy_id: Strategy identifier
            insample_return: In-sample return
            outsample_return: Out-of-sample return
            returns: Trade returns
            monthly_returns: Monthly aggregated returns
            param_results: Parameter stability results
            
        Returns:
            OverfitReport
        """
        report = OverfitReport(strategy_id=strategy_id)
        
        # Test 1: In-sample degradation
        report.degradation, passed, msg = self.test_insample_degradation(
            insample_return, outsample_return
        )
        report.insample_score = insample_return
        report.outsample_score = outsample_return
        
        if not passed:
            report.warnings.append(msg)
        
        # Test 2: Monte Carlo
        report.monte_carlo_pvalue, passed, msg = self.monte_carlo_test(returns)
        if not passed:
            report.warnings.append(msg)
        
        # Test 3: Parameter stability
        if param_results:
            report.parameter_stability, passed, msg = self.test_parameter_stability(param_results)
            if not passed:
                report.warnings.append(msg)
        
        # Test 4: Trade consistency
        report.trade_consistency, passed, msg = self.test_trade_consistency(monthly_returns)
        if not passed:
            report.warnings.append(msg)
        
        # Determine overall level
        warning_count = len(report.warnings)
        
        if warning_count == 0:
            report.overall_level = OverfitLevel.NONE
        elif warning_count == 1:
            report.overall_level = OverfitLevel.MILD
        elif warning_count == 2:
            report.overall_level = OverfitLevel.MODERATE
        else:
            report.overall_level = OverfitLevel.SEVERE
        
        report.passed = report.overall_level in [OverfitLevel.NONE, OverfitLevel.MILD]
        
        self.logger.info(
            f"Overfit analysis for {strategy_id}: {report.overall_level.value} "
            f"({warning_count} warnings)"
        )
        
        return report
    
    def export_report(self, report: OverfitReport, filepath: str):
        """Export report to JSON."""
        with open(filepath, 'w') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Report exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    detector = OverfitDetector()
    
    # Good strategy
    good_report = detector.analyze(
        strategy_id="MA_Crossover",
        insample_return=25.0,
        outsample_return=22.0,
        returns=[2, -1, 3, 1, -2, 4, 2, 1, 3, 2],
        monthly_returns=[3, 2, 4, -1, 5, 2],
        param_results={
            'fast_ma': [20, 21, 19],
            'slow_ma': [50, 52, 49],
        }
    )
    
    # Overfit strategy
    bad_report = detector.analyze(
        strategy_id="Overfit_Strategy",
        insample_return=50.0,
        outsample_return=5.0,
        returns=[10, -8, 15, -12, 8, -10],
        monthly_returns=[20, -15, 10, -20, 5],
        param_results={
            'param1': [50, 20, 5],
            'param2': [80, 30, 10],
        }
    )
    
    print("Overfit Detection Demo")
    print("=" * 50)
    print(f"Good Strategy: {good_report.overall_level.value} (passed: {good_report.passed})")
    print(f"  Degradation: {good_report.degradation*100:.1f}%")
    print(f"  MC p-value: {good_report.monte_carlo_pvalue:.3f}")
    
    print(f"\nBad Strategy: {bad_report.overall_level.value} (passed: {bad_report.passed})")
    print(f"  Warnings: {bad_report.warnings}")
    print(f"  Degradation: {bad_report.degradation*100:.1f}%")
