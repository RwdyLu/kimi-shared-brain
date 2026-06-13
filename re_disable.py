import json

# Re-disable hilbert_cycle and opening_range_breakout in paper_trading_state
with open('/root/.openclaw/workspace/kimi-shared-brain/state/paper_trading_state.json', 'r') as f:
    state = json.load(f)

for sid in ('hilbert_cycle', 'opening_range_breakout'):
    if sid in state.get('strategies', {}):
        state['strategies'][sid]['enabled'] = False
        state['strategies'][sid]['disabled_at'] = '2026-05-30T16:39:00'
        state['strategies'][sid]['disabled_reason'] = 'Manual disable: heavy bleeding - re-applied'
        state['strategies'][sid]['positions'] = {}
        print(f'Disabled {sid} in paper_trading_state.json')

with open('/root/.openclaw/workspace/kimi-shared-brain/state/paper_trading_state.json', 'w') as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print('Re-disable done.')
