#!/usr/bin/env python3
"""
Scheduler Watchdog
監控 Scheduler 進程，如果死掉自動重啟
"""

import os
import sys
import time
import subprocess
import signal
from pathlib import Path
from datetime import datetime

# Config
WATCHDOG_INTERVAL = 60  # 每 60 秒檢查一次
SCHEDULER_SCRIPT = Path(__file__).parent.parent / "start_scheduler.py"
PID_FILE = Path(__file__).parent.parent / "state" / ".monitor.pid"
LOG_FILE = Path(__file__).parent.parent / "logs" / "watchdog.log"


def log(msg: str):
    """Write to log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    if LOG_FILE.parent.exists():
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")


def is_scheduler_alive(pid: int) -> bool:
    """Check if process is running"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_scheduler_pid() -> int:
    """Read PID from file"""
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, IOError):
            return None
    return None


def start_scheduler() -> int:
    """Start scheduler and return PID"""
    log("Starting scheduler...")
    
    # Use nohup to keep running after session ends
    proc = subprocess.Popen(
        [sys.executable, str(SCHEDULER_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True  # Detach from parent
    )
    
    # Write PID
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(proc.pid))
    
    log(f"Scheduler started with PID {proc.pid}")
    return proc.pid


def stop_scheduler(pid: int):
    """Gracefully stop scheduler"""
    log(f"Stopping scheduler PID {pid}...")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)
        if is_scheduler_alive(pid):
            os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def main():
    """Watchdog main loop"""
    log("=" * 60)
    log("SCHEDULER WATCHDOG STARTED")
    log(f"Check interval: {WATCHDOG_INTERVAL}s")
    log(f"PID file: {PID_FILE}")
    log("=" * 60)
    
    while True:
        try:
            pid = get_scheduler_pid()
            
            if pid is None:
                log("No PID file found, starting scheduler...")
                start_scheduler()
            elif not is_scheduler_alive(pid):
                log(f"Scheduler PID {pid} is dead, restarting...")
                start_scheduler()
            else:
                # Silent check - only log if debugging
                pass
                # log(f"Scheduler PID {pid} is alive ✓")
            
            time.sleep(WATCHDOG_INTERVAL)
            
        except KeyboardInterrupt:
            log("Watchdog stopped by user")
            break
        except Exception as e:
            log(f"Watchdog error: {e}")
            time.sleep(WATCHDOG_INTERVAL)


if __name__ == "__main__":
    main()
