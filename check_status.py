import json
from pathlib import Path

# 1. Check if paper_trading auto-adds new strategies
from app.paper_trading import PaperTrading

pt = PaperTrading()
print('=== PaperTrading Strategies Loaded ===')
for sid, acc in pt.strategies.items():
    trades = len(acc.trades)
    balance = acc.balance
    pos_count = sum(len(v) for v in acc.positions.values())
    print(f'  {sid:30} | balance=${balance:9.2f} | trades={trades:>4} | open_pos={pos_count}')

# 2. Check config
with open('config/strategies.json', 'r') as f:
    config = json.load(f)

enabled = [s['id'] for s in config.get('strategies', []) if s.get('enabled')]
print(f'\n=== Config Enabled Strategies ({len(enabled)}) ===')
for sid in enabled:
    marker = '✅' if sid in pt.strategies else '❌ NOT IN PAPER STATE'
    print(f'  {marker} {sid}')

# 3. Check state file directly
with open('state/paper_trading_state.json', 'r') as f:
    state = json.load(f)

state_strats = list(state.get('strategies', {}).keys())
print(f'\n=== State File Strategies ({len(state_strats)}) ===')
for sid in state_strats:
    acc = state['strategies'][sid]
    trades_len = len(acc.get('trades', []))
    bal = acc.get('balance', 0)
    print(f'  {sid:30} | balance=${bal:9.2f} | trades={trades_len:>4}')

# 4. Summary
v2_in_state = [s for s in state_strats if '_v2' in s or s in ['cluc_bounce', 'supertrend_trend']]
print(f'\n=== V2 Strategies in State: {len(v2_in_state)} ===')
for s in v2_in_state:
    print(f'  ✅ {s}')
if not v2_in_state:
    print('  ❌ None — V2 strategies NOT yet added to paper_trading_state.json')
