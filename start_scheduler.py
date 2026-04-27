#!/usr/bin/env python3
"""
Start Scheduler Script / 啟動排程器腳本

T-054-A: Restart Scheduler to enable price logging
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.scheduler import MonitoringScheduler, SchedulerConfig, SchedulerMode
from app.trade_executor import TradeExecutor

def main():
    print("="*70)
    print("🔄 T-054-A: Starting Scheduler with Paper Trading")
    print("="*70)
    
    config = SchedulerConfig(
        mode=SchedulerMode.INTERVAL,
        interval_minutes=5,
        max_runs=None,
        prevent_overlap=True
    )
    
    # Initialize trade executor for PAPER-TRADING
    executor = TradeExecutor(initial_balance=10000, position_pct=0.1)
    
    scheduler = MonitoringScheduler(config, trade_executor=executor)
    
    print(f"✓ Scheduler initialized")
    print(f"  Mode: {config.mode.value}")
    print(f"  Interval: {config.interval_minutes} minutes")
    print(f"  Trading: PAPER-TRADING ENABLED")
    print(f"  Price logging: ENABLED (T-052-B)")
    print("="*70)
    
    # Start interval execution
    scheduler.run_interval()

if __name__ == "__main__":
    main()
