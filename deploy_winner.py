import json

# Load WINNER.json directly
winner = json.load(open('/root/.openclaw/workspace/kimi-shared-brain/app/genetic_engine/data/genetic_evolution/WINNER.json'))

# Gene to condition name helper
def gene_to_condition_name(gene, prefix):
    name = gene['name']
    params = gene.get('params', {})
    cond = gene['condition']
    
    if name == "ema_cross":
        sp = params.get("short_period", 12)
        lp = params.get("long_period", 26)
        return f"ema{sp}_cross_ema{lp}_{cond}"
    elif name == "sma_cross":
        sp = params.get("short_period", 10)
        lp = params.get("long_period", 30)
        return f"sma{sp}_cross_sma{lp}_{cond}"
    elif name == "macd":
        return f"macd_histogram_{cond}"
    elif name == "adx":
        th = int(gene['threshold'])
        return f"adx_{cond}_{th}"
    elif name == "rsi":
        period = params.get("period", 14)
        th = int(gene['threshold'])
        return f"rsi{period}_{cond}_{th}"
    elif name == "bbands":
        return f"bbands_zscore_{cond}"
    elif name == "volume_sma_ratio":
        return f"volume_ratio_{cond}_{gene['threshold']:.1f}"
    elif name == "close_vs_ma":
        period = params.get("ma_period", 50)
        ma_type = params.get("ma_type", "ema")
        return f"close_vs_{ma_type}{period}_{cond}"
    elif name == "atr":
        return f"atr_pct_{cond}_{gene['threshold']:.4f}"
    elif name == "stochastic":
        return f"stoch_{cond}_{int(gene['threshold'])}"
    elif name == "supertrend":
        return f"supertrend_{cond}"
    elif name == "cci":
        return f"cci_{cond}_{int(gene['threshold'])}"
    elif name == "momentum":
        return f"momentum{params.get('period', 10)}_{cond}"
    elif name == "obv":
        return f"obv_{cond}"
    elif name == "vwap":
        return f"vwap_{cond}"
    elif name == "keltner":
        return f"keltner_zscore_{cond}"
    else:
        return f"{name}_{cond}_{int(gene['threshold'])}"

# Build conditions
conditions = []
for gene in winner['entry_genes']:
    cond_name = gene_to_condition_name(gene, "entry")
    if cond_name and cond_name not in conditions:
        conditions.append(cond_name)
for gene in winner['exit_genes']:
    cond_name = gene_to_condition_name(gene, "exit")
    if cond_name and cond_name not in conditions:
        conditions.append(cond_name)

# Build entry parameters
parameters = {}
for gene in winner['entry_genes']:
    for k, v in gene['params'].items():
        parameters[f"entry_{gene['name']}_{k}"] = v
    parameters[f"entry_{gene['name']}_threshold"] = gene['threshold']
    if gene.get('threshold2'):
        parameters[f"entry_{gene['name']}_threshold2"] = gene['threshold2']
parameters["entry_logic"] = winner['entry_logic']
parameters["entry_min_weight"] = winner['entry_min_weight']

# Build default_exit_params from risk_genes
risk = winner['risk_genes']

profit_targets = {}
if risk.get('profit_targets'):
    for pt in risk['profit_targets']:
        minutes = str(pt.get("time_minutes", 0))
        profit_targets[minutes] = pt.get("target", 0.03)
else:
    tp = risk['take_profit_pct']
    profit_targets = {
        "0": tp,
        "20": round(tp * 0.85, 3),
        "40": round(tp * 0.7, 3),
        "60": round(tp * 0.55, 3),
        "120": round(tp * 0.35, 3),
    }

trailing_trigger = 0.04
trailing_drawback = 0.015
if risk.get('trailing_stop') and risk.get('trailing_stop_pct'):
    trailing_trigger = round(risk['take_profit_pct'] * 0.5, 3)
    trailing_drawback = risk['trailing_stop_pct']

default_exit_params = {
    "hard_stop_loss": risk['stop_loss_pct'],
    "atr_stop_multiplier": 2.0,
    "atr_min_floor": round(risk['stop_loss_pct'] * 0.5, 4),
    "ma_reverse_pnl_threshold": -0.015,
    "ma_reverse_min_duration_min": 15,
    "profit_targets": profit_targets,
    "trailing_stop_trigger": trailing_trigger,
    "trailing_stop_drawback": trailing_drawback,
    "time_stop_hours": round(risk['max_hold_bars'] * 5 / 60, 1),
    "position_pct": risk['position_pct'],
    "max_concurrent_positions": 3,
}

# Strategy type inference
type_counts = {}
for g in winner['entry_genes']:
    t = g['indicator_type']
    type_counts[t] = type_counts.get(t, 0) + 1
strategy_type = max(type_counts, key=type_counts.get) if type_counts else "trend"

strategy_id = f"genetic_{winner['chromosome_id'].lower()}"
fitness_score = winner.get('fitness_score')
fitness_str = f"{fitness_score:.3f}" if fitness_score else "N/A"

new_strategy = {
    "id": strategy_id,
    "name": f"GEN {winner['chromosome_id'][:8]}",
    "name_zh": f"基因策略 {winner['chromosome_id'][:8]}",
    "type": strategy_type,
    "enabled": True,
    "description": f"Genetic winner G{winner['generation']} | fitness={fitness_str} | Entry({winner['entry_logic']}): {[g['name'] for g in winner['entry_genes']]} | Exit({winner['exit_logic']}): {[g['name'] for g in winner['exit_genes']]}",
    "description_zh": f"基因演算法優勝策略，世代={winner['generation']}, 親代={winner.get('parent_ids', [])}, fitness={fitness_str}",
    "symbols": [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
    ],
    "timeframes": ["5m"],
    "conditions": conditions,
    "parameters": parameters,
    "default_exit_params": default_exit_params,
    "signal_type": "trend_long" if strategy_type == "trend" else "momentum_long",
    "signal_level": "genetic",
    "meta": {
        "factory_generated": True,
        "generation": winner['generation'],
        "chromosome_id": winner['chromosome_id'],
        "fitness_score": winner.get('fitness_score'),
        "fitness_details": winner.get('fitness_details', {}),
        "parent_ids": winner.get('parent_ids', []),
        "created_at": winner['created_at'],
        "source": "genetic_evolution",
        "deployed_at": "2026-05-30T16:39:00",
    }
}

# 1. Add to strategies.json
with open('/root/.openclaw/workspace/kimi-shared-brain/config/strategies.json', 'r') as f:
    data = json.load(f)

# Remove if already exists
existing_ids = [s['id'] for s in data['strategies']]
if strategy_id in existing_ids:
    data['strategies'] = [s for s in data['strategies'] if s['id'] != strategy_id]
    print(f"Removed existing {strategy_id}")

data['strategies'].append(new_strategy)

with open('/root/.openclaw/workspace/kimi-shared-brain/config/strategies.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Added {strategy_id} to strategies.json")

# 2. Add to paper_trading_state.json
with open('/root/.openclaw/workspace/kimi-shared-brain/state/paper_trading_state.json', 'r') as f:
    state = json.load(f)

if strategy_id not in state.get('strategies', {}):
    state['strategies'][strategy_id] = {
        "balance": 1000.0,
        "initial": 1000.0,
        "positions": {},
        "trades": [],
        "enabled": True,
    }
    print(f"Added {strategy_id} to paper_trading_state.json with $1000 initial")
else:
    print(f"{strategy_id} already exists in paper_trading_state")

with open('/root/.openclaw/workspace/kimi-shared-brain/state/paper_trading_state.json', 'w') as f:
    json.dump(state, f, indent=2, ensure_ascii=False)

print("Step 2 (WINNER deploy) done.")
print(json.dumps(new_strategy, indent=2, ensure_ascii=False))
