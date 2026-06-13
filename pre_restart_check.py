import json
import os
import time
import subprocess
from pathlib import Path

# 1. First, patch scheduler.py to reload strategies on each run
def patch_scheduler():
    scheduler_path = Path('/root/.openclaw/workspace/kimi-shared-brain/app/scheduler.py')
    content = scheduler_path.read_text()
    
    # Find where to add reload - in _run_monitor, before the monitoring run
    # Add strategy reload at the beginning of the run
    if 'self.runner.strategy_executor.reload_strategies()' not in content:
        # Find the line: "self._run_count += 1" and add reload after it
        old_line = '        self._run_count += 1\n'
        new_lines = '''        self._run_count += 1
        
        # Reload strategies from config on each run / 每次執行前重新載入策略
        try:
            self.runner.strategy_executor.reload_strategies()
            self._log(f"  Strategies reloaded: {len(self.runner.strategy_executor.enabled_strategies)} enabled")
        except Exception as e:
            self._log(f"  Strategy reload error: {e}")
'''
        content = content.replace(old_line, new_lines)
        scheduler_path.write_text(content)
        print("✅ Patched scheduler.py to reload strategies on each run")
    else:
        print("  scheduler.py already patched")

patch_scheduler()

# 2. Check current scheduler process
result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
scheduler_lines = [l for l in result.stdout.split('\n') if 'scheduler' in l.lower() and 'python' in l.lower() and 'grep' not in l.lower()]
print(f"\n=== Current scheduler processes ===")
for line in scheduler_lines:
    print(f"  {line}")

# 3. Read current state to verify
cwd = '/root/.openclaw/workspace/kimi-shared-brain'
with open(f'{cwd}/config/strategies.json', 'r') as f:
    data = json.load(f)

enabled_count = sum(1 for s in data['strategies'] if s.get('enabled', False))
disabled_count = len(data['strategies']) - enabled_count
print(f"\n=== strategies.json ===")
print(f"  Total: {len(data['strategies'])}")
print(f"  Enabled: {enabled_count}")
print(f"  Disabled: {disabled_count}")
print(f"  WINNER present: {any(s['id'] == 'genetic_mut_dac146ea58c9' for s in data['strategies'])}")

# 4. Show the disabled ones with bleeding
print(f"\n=== Disabled strategies with bleeding ===")
for s in data['strategies']:
    if not s.get('enabled', False):
        print(f"  {s['id']}: {s.get('meta', {}).get('disabled_reason', 'N/A')}")
