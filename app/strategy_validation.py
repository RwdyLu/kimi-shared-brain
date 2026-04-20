"""
Strategy Validation Timer
Tracks validation periods (30-60 day trials) for trading strategies.
Handles automatic promotion/demotion based on performance criteria.
"""
import json
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta


class StrategyStatus(Enum):
    """Strategy lifecycle status."""
    TRIAL = "trial"           # In validation period
    VALIDATED = "validated"   # Passed validation
    FAILED = "failed"         # Failed validation
    DISABLED = "disabled"     # Manually disabled
    PROMOTED = "promoted"     # Promoted to production


class ValidationResult(Enum):
    """Validation decision."""
    PENDING = "pending"       # Still in trial
    PASS = "pass"             # Met all criteria
    FAIL = "fail"             # Failed criteria
    EXTEND = "extend"         # Extend trial period


@dataclass
class ValidationCriteria:
    """Criteria for strategy validation."""
    min_win_rate: float = 0.55        # Minimum 55% win rate
    min_profit_factor: float = 1.2    # Minimum profit factor
    max_drawdown: float = 0.15          # Maximum 15% drawdown
    min_trades: int = 20              # Minimum trades for evaluation
    min_sharpe: float = 0.5           # Minimum Sharpe ratio
    max_consecutive_losses: int = 5   # Maximum consecutive losses


@dataclass
class StrategyTrial:
    """Strategy trial tracking."""
    strategy_id: str
    strategy_name: str
    status: StrategyStatus
    
    # Trial timing
    trial_start: datetime
    trial_duration_days: int = 30     # Default 30 days
    extension_count: int = 0
    max_extensions: int = 2
    
    # Performance tracking
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    consecutive_losses: int = 0
    max_consecutive_losses: int = 0
    peak_balance: float = 0.0
    
    # Metrics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    
    # Validation
    criteria: ValidationCriteria = field(default_factory=ValidationCriteria)
    validation_result: ValidationResult = ValidationResult.PENDING
    validation_notes: List[str] = field(default_factory=list)
    
    def days_remaining(self) -> int:
        """Calculate days remaining in trial."""
        end_date = self.trial_start + timedelta(days=self.trial_duration_days)
        remaining = (end_date - datetime.now()).days
        return max(0, remaining)
    
    def is_expired(self) -> bool:
        """Check if trial period has expired."""
        return self.days_remaining() <= 0
    
    def update_metrics(self):
        """Recalculate all performance metrics."""
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
        
        if self.total_loss > 0:
            self.profit_factor = self.total_profit / self.total_loss
        else:
            self.profit_factor = float('inf') if self.total_profit > 0 else 0
    
    def evaluate(self) -> ValidationResult:
        """
        Evaluate strategy against criteria.
        
        Returns:
            ValidationResult: PASS, FAIL, EXTEND, or PENDING
        """
        self.update_metrics()
        
        # Not enough trades yet
        if self.total_trades < self.criteria.min_trades:
            if self.is_expired() and self.extension_count < self.max_extensions:
                return ValidationResult.EXTEND
            return ValidationResult.PENDING
        
        # Check all criteria
        checks = {
            'win_rate': self.win_rate >= self.criteria.min_win_rate,
            'profit_factor': self.profit_factor >= self.criteria.min_profit_factor,
            'drawdown': self.max_drawdown <= self.criteria.max_drawdown,
            'consecutive_losses': self.max_consecutive_losses <= self.criteria.max_consecutive_losses,
        }
        
        # Log evaluation
        notes = [
            f"Win Rate: {self.win_rate:.2%} (required: {self.criteria.min_win_rate:.2%}) {'✅' if checks['win_rate'] else '❌'}",
            f"Profit Factor: {self.profit_factor:.2f} (required: {self.criteria.min_profit_factor:.2f}) {'✅' if checks['profit_factor'] else '❌'}",
            f"Max Drawdown: {self.max_drawdown:.2%} (max: {self.criteria.max_drawdown:.2%}) {'✅' if checks['drawdown'] else '❌'}",
            f"Consecutive Losses: {self.max_consecutive_losses} (max: {self.criteria.max_consecutive_losses}) {'✅' if checks['consecutive_losses'] else '❌'}",
        ]
        self.validation_notes = notes
        
        # Determine result
        if all(checks.values()):
            self.validation_result = ValidationResult.PASS
            return ValidationResult.PASS
        elif self.is_expired():
            if self.extension_count < self.max_extensions and self.win_rate >= 0.45:
                # Extend if showing promise
                return ValidationResult.EXTEND
            self.validation_result = ValidationResult.FAIL
            return ValidationResult.FAIL
        
        return ValidationResult.PENDING
    
    def record_trade(self, profit_loss: float):
        """Record a trade result."""
        self.total_trades += 1
        
        if profit_loss > 0:
            self.winning_trades += 1
            self.total_profit += profit_loss
            self.consecutive_losses = 0
        else:
            self.losing_trades += 1
            self.total_loss += abs(profit_loss)
            self.consecutive_losses += 1
            self.max_consecutive_losses = max(
                self.max_consecutive_losses, 
                self.consecutive_losses
            )
        
        # Update drawdown
        if profit_loss > 0:
            self.peak_balance += profit_loss
        else:
            self.current_drawdown += abs(profit_loss)
            self.max_drawdown = max(self.max_drawdown, self.current_drawdown)
        
        self.update_metrics()
    
    def extend_trial(self, days: int = 15) -> bool:
        """Extend trial period."""
        if self.extension_count >= self.max_extensions:
            return False
        
        self.trial_duration_days += days
        self.extension_count += 1
        self.validation_result = ValidationResult.PENDING
        return True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'strategy_id': self.strategy_id,
            'strategy_name': self.strategy_name,
            'status': self.status.value,
            'trial_start': self.trial_start.isoformat(),
            'trial_duration_days': self.trial_duration_days,
            'days_remaining': self.days_remaining(),
            'extension_count': self.extension_count,
            'metrics': {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'win_rate': self.win_rate,
                'profit_factor': self.profit_factor,
                'max_drawdown': self.max_drawdown,
                'sharpe_ratio': self.sharpe_ratio,
                'consecutive_losses': self.max_consecutive_losses,
            },
            'validation': {
                'result': self.validation_result.value,
                'notes': self.validation_notes,
            }
        }


class StrategyValidationManager:
    """
    Manages validation periods for multiple strategies.
    """
    
    def __init__(self, criteria: Optional[ValidationCriteria] = None):
        self.logger = logging.getLogger(__name__)
        self.criteria = criteria or ValidationCriteria()
        self.strategies: Dict[str, StrategyTrial] = {}
        self.logger.info("StrategyValidationManager initialized")
    
    def add_strategy(self, strategy_id: str, strategy_name: str,
                    trial_days: int = 30) -> StrategyTrial:
        """
        Add a new strategy for validation.
        
        Args:
            strategy_id: Unique strategy identifier
            strategy_name: Human-readable name
            trial_days: Trial period in days
            
        Returns:
            StrategyTrial instance
        """
        trial = StrategyTrial(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            status=StrategyStatus.TRIAL,
            trial_start=datetime.now(),
            trial_duration_days=trial_days,
            criteria=self.criteria
        )
        
        self.strategies[strategy_id] = trial
        self.logger.info(
            f"Added strategy {strategy_id} ({strategy_name}) "
            f"with {trial_days} day trial"
        )
        
        return trial
    
    def record_trade(self, strategy_id: str, profit_loss: float):
        """Record a trade for a strategy."""
        if strategy_id not in self.strategies:
            self.logger.warning(f"Strategy {strategy_id} not found")
            return
        
        trial = self.strategies[strategy_id]
        trial.record_trade(profit_loss)
        
        self.logger.info(
            f"Strategy {strategy_id}: Trade PnL={profit_loss:.2f}, "
            f"Trades={trial.total_trades}, WinRate={trial.win_rate:.2%}"
        )
    
    def evaluate_all(self) -> Dict[str, ValidationResult]:
        """
        Evaluate all strategies.
        
        Returns:
            Dict mapping strategy_id to validation result
        """
        results = {}
        
        for strategy_id, trial in self.strategies.items():
            result = trial.evaluate()
            results[strategy_id] = result
            
            if result == ValidationResult.PASS:
                trial.status = StrategyStatus.VALIDATED
                self.logger.info(f"Strategy {strategy_id}: ✅ VALIDATED")
            elif result == ValidationResult.FAIL:
                trial.status = StrategyStatus.FAILED
                self.logger.info(f"Strategy {strategy_id}: ❌ FAILED")
            elif result == ValidationResult.EXTEND:
                if trial.extend_trial():
                    self.logger.info(f"Strategy {strategy_id}: Extended trial")
            
            # Auto-promote validated strategies
            if trial.status == StrategyStatus.VALIDATED:
                trial.status = StrategyStatus.PROMOTED
                self.logger.info(f"Strategy {strategy_id}: 🚀 PROMOTED to production")
        
        return results
    
    def get_strategy_status(self, strategy_id: str) -> Optional[Dict]:
        """Get detailed status for a strategy."""
        if strategy_id not in self.strategies:
            return None
        
        trial = self.strategies[strategy_id]
        trial.evaluate()  # Refresh evaluation
        
        return trial.to_dict()
    
    def get_all_status(self) -> List[Dict]:
        """Get status for all strategies."""
        return [trial.to_dict() for trial in self.strategies.values()]
    
    def get_summary(self) -> Dict:
        """Get summary statistics."""
        status_counts = {
            'trial': 0,
            'validated': 0,
            'failed': 0,
            'promoted': 0,
            'disabled': 0,
        }
        
        for trial in self.strategies.values():
            status_counts[trial.status.value] = status_counts.get(trial.status.value, 0) + 1
        
        return {
            'total_strategies': len(self.strategies),
            'status_counts': status_counts,
            'in_trial': status_counts['trial'],
            'promoted': status_counts['promoted'],
            'failed': status_counts['failed'],
        }
    
    def save_state(self, filepath: str = "state/strategy_validation.json"):
        """Save validation state to file."""
        state = {
            'strategies': {
                sid: trial.to_dict()
                for sid, trial in self.strategies.items()
            },
            'criteria': {
                'min_win_rate': self.criteria.min_win_rate,
                'min_profit_factor': self.criteria.min_profit_factor,
                'max_drawdown': self.criteria.max_drawdown,
                'min_trades': self.criteria.min_trades,
                'min_sharpe': self.criteria.min_sharpe,
                'max_consecutive_losses': self.criteria.max_consecutive_losses,
            },
            'saved_at': datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        self.logger.info(f"Validation state saved to {filepath}")
    
    def load_state(self, filepath: str = "state/strategy_validation.json"):
        """Load validation state from file."""
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            for sid, data in state['strategies'].items():
                trial = StrategyTrial(
                    strategy_id=sid,
                    strategy_name=data['strategy_name'],
                    status=StrategyStatus(data['status']),
                    trial_start=datetime.fromisoformat(data['trial_start']),
                    trial_duration_days=data['trial_duration_days'],
                    extension_count=data.get('extension_count', 0),
                    total_trades=data['metrics']['total_trades'],
                    winning_trades=data['metrics']['winning_trades'],
                    losing_trades=data['metrics']['losing_trades'],
                    criteria=self.criteria,
                )
                trial.win_rate = data['metrics']['win_rate']
                trial.profit_factor = data['metrics']['profit_factor']
                trial.max_drawdown = data['metrics']['max_drawdown']
                trial.sharpe_ratio = data['metrics'].get('sharpe_ratio', 0)
                
                self.strategies[sid] = trial
            
            self.logger.info(f"Validation state loaded from {filepath}")
        except FileNotFoundError:
            self.logger.warning(f"State file not found: {filepath}")


if __name__ == "__main__":
    # Example usage
    manager = StrategyValidationManager()
    
    # Add 10 strategies
    strategies = [
        ("BTC_4H_MA", "BTC 4H Moving Average Crossover"),
        ("BTC_1D_MR", "BTC 1D Mean Reversion"),
        ("ETH_4H_RSI", "ETH 4H RSI Strategy"),
        ("BTC_1H_BB", "BTC 1H Bollinger Bands"),
        ("ETH_1D_MACD", "ETH 1D MACD"),
        ("BTC_4H_ATR", "BTC 4H ATR Breakout"),
        ("ETH_1H_VWAP", "ETH 1H VWAP Strategy"),
        ("BTC_1D_TREND", "BTC 1D Trend Following"),
        ("ETH_4H_FIB", "ETH 4H Fibonacci"),
        ("BTC_1H_SCALP", "BTC 1H Scalping"),
    ]
    
    for sid, name in strategies:
        manager.add_strategy(sid, name, trial_days=30)
    
    # Simulate some trades
    import random
    random.seed(42)
    
    for _ in range(50):
        for sid in manager.strategies:
            pnl = random.gauss(100, 200)  # Mean 100, std 200
            manager.record_trade(sid, pnl)
    
    # Evaluate all
    results = manager.evaluate_all()
    
    # Print summary
    print("\nStrategy Validation Summary")
    print("=" * 50)
    for sid, result in results.items():
        trial = manager.strategies[sid]
        print(f"{sid}: {result.value} | WinRate: {trial.win_rate:.2%} | Trades: {trial.total_trades}")
    
    print(f"\nOverall: {manager.get_summary()}")
