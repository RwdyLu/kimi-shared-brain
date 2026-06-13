import subprocess
import json
from datetime import datetime
import sys

# 激進路線自動監控腳本
# 每天運行：v2_monitor + auto_tune_task advisory

WORKSPACE = "/root/.openclaw/workspace/kimi-shared-brain"

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=WORKSPACE)
    return result.stdout + result.stderr

# 1. 運行 v2_monitor
print(f"=== V2 Monitor | {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
output = run_cmd("python3 app/v2_monitor.py")
print(output)

# 2. 對 ready 的策略運行 advisory
for sid in ['ma_cross_trend_v2', 'supertrend_trend']:
    print(f"\n=== Auto-Tune: {sid} ===")
    output = run_cmd(f"python3 app/auto_tune_task.py --mode advisory --strategy-id {sid}")
    print(output)

# 3. 檢查新策略交易筆數
print(f"\n=== V2 策略狀態 ===")
state_output = run_cmd("""python3 -c "
import json
with open('state/paper_trading_state.json') as f:
    data = json.load(f)
for sid in ['ma_cross_trend_v2', 'volume_breakout_v2', 'parabolic_sar_v2', 'supertrend_trend']:
    if sid in data['strategies']:
        info = data['strategies'][sid]
        trades = len(info.get('trades', []))
        bal = info.get('balance', 0)
        print(f'{sid}: ${bal:.2f} | {trades} trades')
" """)
print(state_output)
