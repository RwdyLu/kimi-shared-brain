#!/usr/bin/env python3
"""
Task Watcher - Auto-detects assigned tasks from GitHub
Runs periodically to check for new task assignments.
"""
import os
import sys
import json
import time
import subprocess
from datetime import datetime

TASKS_FILE = "state/tasks.json"
CHECK_INTERVAL = 300  # 5 minutes


def run_command(cmd):
    """Run shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return str(e), 1


def get_assigned_tasks():
    """Get tasks assigned to kimiclaw_bot."""
    try:
        with open(TASKS_FILE, 'r') as f:
            data = json.load(f)
        
        assigned = [
            t for t in data.get('tasks', [])
            if t.get('status') == 'assigned'
            and t.get('assigned_to') == 'kimiclaw_bot'
        ]
        return assigned
    except Exception as e:
        print(f"Error reading tasks: {e}")
        return []


def check_for_updates():
    """Check git for updates."""
    # Fetch latest
    stdout, rc = run_command("git fetch origin main")
    if rc != 0:
        print(f"Fetch failed: {stdout}")
        return False
    
    # Check if behind
    stdout, rc = run_command("git rev-list HEAD...origin/main --count")
    if rc == 0 and stdout.strip() != "0":
        return True
    
    return False


def sync_and_check():
    """Sync with git and check for new assignments."""
    print(f"[{datetime.now().isoformat()}] Checking for updates...")
    
    # Pull latest
    stdout, rc = run_command("git pull origin main")
    if rc != 0:
        print(f"Pull failed: {stdout}")
        return []
    
    # Check for assigned tasks
    assigned = get_assigned_tasks()
    
    if assigned:
        print(f"Found {len(assigned)} assigned tasks:")
        for task in assigned:
            print(f"  - {task['task_id']}: {task['title']}")
    else:
        print("No new assignments")
    
    return assigned


def main_loop():
    """Main watcher loop."""
    print("Task Watcher started")
    print(f"Checking every {CHECK_INTERVAL}s")
    print("-" * 50)
    
    while True:
        try:
            assigned = sync_and_check()
            
            if assigned:
                # Signal that work is available
                # In practice, this could trigger a webhook or notification
                print("\n⚠️ NEW TASKS ASSIGNED!")
                print("Ready to execute...\n")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("\nWatcher stopped")
            break
        except Exception as e:
            print(f"Error in watcher: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main_loop()
