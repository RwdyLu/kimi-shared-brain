"""
Strategy Auto-Execution Loop
Automated strategy execution with monitoring and failover.
"""
import json
import logging
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading


class ExecutionStatus(Enum):
    """Execution loop status."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class ExecutionCycle:
    """Single execution cycle record."""
    cycle_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    strategies_run: int = 0
    signals_generated: int = 0
    trades_executed: int = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'cycle_id': self.cycle_id,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'strategies_run': self.strategies_run,
            'signals_generated': self.signals_generated,
            'trades_executed': self.trades_executed,
            'errors': self.errors,
        }


class AutoStrategyLoop:
    """
    Automated strategy execution loop.
    
    Runs strategies on schedule, handles errors, and provides
    monitoring and failover capabilities.
    """
    
    def __init__(self,
                 check_interval: int = 60,
                 max_concurrent: int = 5):
        self.logger = logging.getLogger(__name__)
        
        # Config
        self.check_interval = check_interval
        self.max_concurrent = max_concurrent
        
        # State
        self.status = ExecutionStatus.STOPPED
        self.cycle_count = 0
        self.cycles: List[ExecutionCycle] = []
        
        # Registered strategies
        self.strategies: Dict[str, Dict] = {}
        
        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self.logger.info("AutoStrategyLoop initialized")
    
    def register_strategy(self,
                         strategy_id: str,
                         run_func: Callable,
                         interval_minutes: int = 60):
        """
        Register a strategy for auto-execution.
        
        Args:
            strategy_id: Strategy identifier
            run_func: Function to call for execution
            interval_minutes: Run interval
        """
        self.strategies[strategy_id] = {
            'func': run_func,
            'interval': interval_minutes,
            'last_run': None,
            'run_count': 0,
        }
        
        self.logger.info(f"Registered {strategy_id} (interval: {interval_minutes}min)")
    
    def start(self):
        """Start the execution loop."""
        if self.status == ExecutionStatus.RUNNING:
            return
        
        self.status = ExecutionStatus.RUNNING
        self._stop_event.clear()
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self.logger.info("Auto execution loop started")
    
    def stop(self):
        """Stop the execution loop."""
        self._stop_event.set()
        self.status = ExecutionStatus.STOPPED
        self.logger.info("Auto execution loop stopped")
    
    def pause(self):
        """Pause execution."""
        self.status = ExecutionStatus.PAUSED
        self.logger.info("Auto execution loop paused")
    
    def resume(self):
        """Resume execution."""
        self.status = ExecutionStatus.RUNNING
        self.logger.info("Auto execution loop resumed")
    
    def _run_loop(self):
        """Main execution loop."""
        while not self._stop_event.is_set():
            if self.status != ExecutionStatus.RUNNING:
                time.sleep(1)
                continue
            
            self._execute_cycle()
            
            # Wait for next cycle
            self._stop_event.wait(self.check_interval)
    
    def _execute_cycle(self):
        """Execute one cycle."""
        self.cycle_count += 1
        cycle = ExecutionCycle(
            cycle_id=self.cycle_count,
            start_time=datetime.now()
        )
        
        now = datetime.now()
        
        for strategy_id, config in self.strategies.items():
            try:
                # Check if it's time to run
                if config['last_run']:
                    elapsed = (now - config['last_run']).total_seconds() / 60
                    if elapsed < config['interval']:
                        continue
                
                # Run strategy
                self.logger.info(f"Running {strategy_id}...")
                result = config['func']()
                
                config['last_run'] = now
                config['run_count'] += 1
                cycle.strategies_run += 1
                
                # Count signals/trades
                if isinstance(result, dict):
                    cycle.signals_generated += result.get('signals', 0)
                    cycle.trades_executed += result.get('trades', 0)
                
            except Exception as e:
                error_msg = f"{strategy_id}: {str(e)}"
                cycle.errors.append(error_msg)
                self.logger.error(f"Strategy error: {error_msg}")
        
        cycle.end_time = datetime.now()
        self.cycles.append(cycle)
        
        duration = (cycle.end_time - cycle.start_time).total_seconds()
        self.logger.info(
            f"Cycle {cycle.cycle_id} complete: "
            f"{cycle.strategies_run} strategies, "
            f"{cycle.signals_generated} signals, "
            f"{cycle.trades_executed} trades, "
            f"{len(cycle.errors)} errors, "
            f"duration: {duration:.1f}s"
        )
    
    def run_once(self) -> ExecutionCycle:
        """Run one cycle manually."""
        self._execute_cycle()
        return self.cycles[-1]
    
    def get_status(self) -> Dict:
        """Get loop status."""
        return {
            'status': self.status.value,
            'cycle_count': self.cycle_count,
            'registered_strategies': len(self.strategies),
            'last_cycle': self.cycles[-1].to_dict() if self.cycles else None,
        }
    
    def get_cycle_history(self, limit: int = 10) -> List[Dict]:
        """Get recent cycle history."""
        return [c.to_dict() for c in self.cycles[-limit:]]
    
    def export_stats(self, filepath: str):
        """Export execution stats."""
        data = {
            'exported_at': datetime.now().isoformat(),
            'status': self.get_status(),
            'cycles': [c.to_dict() for c in self.cycles],
            'strategies': {
                sid: {
                    'interval': c['interval'],
                    'run_count': c['run_count'],
                    'last_run': c['last_run'].isoformat() if c['last_run'] else None,
                }
                for sid, c in self.strategies.items()
            },
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Stats exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    loop = AutoStrategyLoop(check_interval=5)
    
    # Register mock strategies
    def strategy_1():
        return {'signals': 2, 'trades': 1}
    
    def strategy_2():
        return {'signals': 1, 'trades': 0}
    
    loop.register_strategy("MA_Cross", strategy_1, interval_minutes=1)
    loop.register_strategy("RSI_Strat", strategy_2, interval_minutes=2)
    
    # Run once
    print("Auto Strategy Loop Demo")
    print("=" * 50)
    
    cycle = loop.run_once()
    print(f"Cycle {cycle.cycle_id}: {cycle.strategies_run} strategies")
    print(f"Status: {loop.get_status()}")
