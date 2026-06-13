import json
import sys
sys.path.insert(0, '/root/.openclaw/workspace/kimi-shared-brain/app/genetic_engine')

from chromosome import StrategyChromosome, RiskGenes

# Load WINNER
winner = json.load(open('/root/.openclaw/workspace/kimi-shared-brain/app/genetic_engine/data/genetic_evolution/WINNER.json'))
chrom = StrategyChromosome.from_dict(winner)

# ===== FIXED CONVERTER =====

def fixed_convert_to_strategy_json(chrom):
    """Fixed converter matching strategies.json format exactly"""
    
    # Entry conditions
    conditions = []
    for gene in chrom.entry_genes:
        cond_name = gene_to_condition_name(gene, "entry")
        if cond_name:
            conditions.append(cond_name)
    
    # Exit conditions (also add as conditions for the strategy system)
    for gene in chrom.exit_genes:
        cond_name = gene_to_condition_name(gene, "exit")
        if cond_name and cond_name not in conditions:
            conditions.append(cond_name)
    
    # Filter conditions
    if chrom.trend_filter:
        tf_name = gene_to_condition_name(chrom.trend_filter, "filter")
        if tf_name:
            conditions.append(tf_name)
    if chrom.volume_filter:
        vf_name = gene_to_condition_name(chrom.volume_filter, "filter")
        if vf_name:
            conditions.append(vf_name)
    
    # Entry parameters (indicator params only)
    parameters = {}
    for gene in chrom.entry_genes:
        for k, v in gene.params.items():
            parameters[f"entry_{gene.name}_{k}"] = v
        parameters[f"entry_{gene.name}_threshold"] = gene.threshold
        if gene.threshold2:
            parameters[f"entry_{gene.name}_threshold2"] = gene.threshold2
    parameters["entry_logic"] = chrom.entry_logic
    parameters["entry_min_weight"] = chrom.entry_min_weight
    
    # EXIT parameters (separate default_exit_params matching strategies.json format)
    risk = chrom.risk_genes
    
    # Convert profit_targets list to dict format {"minutes": target}
    profit_targets = {}
    if risk.profit_targets:
        for pt in risk.profit_targets:
            minutes = str(pt.get("time_minutes", 0))
            profit_targets[minutes] = pt.get("target", 0.03)
    else:
        # Default ladder
        profit_targets = {
            "0": risk.take_profit_pct,
            "20": round(risk.take_profit_pct * 0.85, 3),
            "40": round(risk.take_profit_pct * 0.7, 3),
            "60": round(risk.take_profit_pct * 0.55, 3),
            "120": round(risk.take_profit_pct * 0.35, 3),
        }
    
    # trailing stop mapping
    trailing_trigger = 0.04
    trailing_drawback = 0.015
    if risk.trailing_stop and risk.trailing_stop_pct:
        trailing_trigger = round(risk.take_profit_pct * 0.5, 3)
        trailing_drawback = risk.trailing_stop_pct
    
    default_exit_params = {
        "hard_stop_loss": risk.stop_loss_pct,
        "atr_stop_multiplier": 2.0,  # default, not directly in risk_genes
        "atr_min_floor": round(risk.stop_loss_pct * 0.5, 4),
        "ma_reverse_pnl_threshold": -0.015,
        "ma_reverse_min_duration_min": 15,
        "profit_targets": profit_targets,
        "trailing_stop_trigger": trailing_trigger,
        "trailing_stop_drawback": trailing_drawback,
        "time_stop_hours": round(risk.max_hold_bars * 5 / 60, 1),
        "position_pct": risk.position_pct,
        "max_concurrent_positions": 3,
    }
    
    # Strategy type inference
    type_counts = {}
    for g in chrom.entry_genes:
        t = g.indicator_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    strategy_type = max(type_counts, key=type_counts.get) if type_counts else "trend"
    
    # Readable strategy ID
    strategy_id = f"genetic_{chrom.chromosome_id.lower()}"
    
    return {
        "id": strategy_id,
        "name": f"GEN {chrom.chromosome_id[:8]}",
        "name_zh": f"基因策略 {chrom.chromosome_id[:8]}",
        "type": strategy_type,
        "enabled": True,
        "description": chrom.summary(),
        "description_zh": f"基因演算法生成，世代={chrom.generation}, 親代={chrom.parent_ids}, fitness={chrom.fitness_score:.3f if chrom.fitness_score else 'N/A'}",
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
            "generation": chrom.generation,
            "chromosome_id": chrom.chromosome_id,
            "fitness_score": chrom.fitness_score,
            "fitness_details": chrom.fitness_details,
            "parent_ids": chrom.parent_ids,
            "created_at": chrom.created_at,
            "source": "genetic_evolution",
        }
    }


def gene_to_condition_name(gene, prefix):
    """Convert gene to condition name"""
    name = gene.name
    params = gene.params
    cond = gene.condition.value
    
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
        th = int(gene.threshold)
        return f"adx_{cond}_{th}"
    elif name == "rsi":
        period = params.get("period", 14)
        th = int(gene.threshold)
        return f"rsi{period}_{cond}_{th}"
    elif name == "bbands":
        return f"bbands_zscore_{cond}"
    elif name == "volume_sma_ratio":
        return f"volume_ratio_{cond}_{gene.threshold:.1f}"
    elif name == "close_vs_ma":
        period = params.get("ma_period", 50)
        ma_type = params.get("ma_type", "ema")
        return f"close_vs_{ma_type}{period}_{cond}"
    elif name == "atr":
        return f"atr_pct_{cond}_{gene.threshold:.4f}"
    elif name == "stochastic":
        return f"stoch_{cond}_{int(gene.threshold)}"
    elif name == "supertrend":
        return f"supertrend_{cond}"
    elif name == "cci":
        return f"cci_{cond}_{int(gene.threshold)}"
    elif name == "momentum":
        return f"momentum{params.get('period', 10)}_{cond}"
    elif name == "obv":
        return f"obv_{cond}"
    elif name == "vwap":
        return f"vwap_{cond}"
    elif name == "keltner":
        return f"keltner_zscore_{cond}"
    else:
        return f"{name}_{cond}_{int(gene.threshold)}"


# Convert WINNER
new_strategy = fixed_convert_to_strategy_json(chrom)
print(json.dumps(new_strategy, indent=2, ensure_ascii=False))
