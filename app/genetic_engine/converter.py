#!/usr/bin/env python3
"""
Converter / 轉換器

將 StrategyChromosome 轉換為現有交易系統的 strategies.json 格式。
這是基因引擎 ↔ 現有系統的橋樑。

Author: second_bot
Date: 2026-05-22
"""

from typing import Dict, Any, List
from .chromosome import StrategyChromosome, IndicatorGene
from .gene_library import IndicatorType, ConditionType


def convert_to_strategy_json(chrom: StrategyChromosome) -> Dict[str, Any]:
    """
    將基因體轉換為現有 strategies.json 中的單一策略格式
    
    現有格式:
    {
        "id": "ma_cross_trend_v2",
        "name": "MA Cross Trend V2",
        "type": "trend",
        "enabled": true,
        "conditions": ["close_vs_ma240", "ma5_cross_ma20", ...],
        "parameters": {...},
        "signal_type": "trend_long",
        ...
    }
    """
    
    # 條件名稱轉換
    conditions = []
    
    # 進場條件 → conditions 列表
    for gene in chrom.entry_genes:
        cond_name = _gene_to_condition_name(gene, "entry")
        if cond_name:
            conditions.append(cond_name)
    
    # 出場條件也加入（現有系統可能用同樣的 conditions 解析）
    for gene in chrom.exit_genes:
        cond_name = _gene_to_condition_name(gene, "exit")
        if cond_name and cond_name not in conditions:
            conditions.append(cond_name)
    
    # 過濾條件
    if chrom.trend_filter:
        tf_name = _gene_to_condition_name(chrom.trend_filter, "filter")
        if tf_name:
            conditions.append(tf_name)
    
    if chrom.volume_filter:
        vf_name = _gene_to_condition_name(chrom.volume_filter, "filter")
        if vf_name:
            conditions.append(vf_name)
    
    # 參數構建 — 進場參數（conditions + indicator params）
    parameters = {
        "entry_logic": chrom.entry_logic,
        "entry_min_weight": chrom.entry_min_weight,
    }
    
    # 每個進場基因的參數
    for gene in chrom.entry_genes:
        for k, v in gene.params.items():
            parameters[f"entry_{gene.name}_{k}"] = v
        parameters[f"entry_{gene.name}_threshold"] = gene.threshold
        if gene.threshold2:
            parameters[f"entry_{gene.name}_threshold2"] = gene.threshold2
    
    # 出場基因參數也放入（供 conditions 解析使用）
    for gene in chrom.exit_genes:
        for k, v in gene.params.items():
            parameters[f"exit_{gene.name}_{k}"] = v
        parameters[f"exit_{gene.name}_threshold"] = gene.threshold
    
    # ═══════════════════════════════════════════════════════
    # default_exit_params — 匹配 strategies.json 的風控格式
    # ═══════════════════════════════════════════════════════
    risk = chrom.risk_genes
    
    # 階梯止盈轉換
    profit_targets = {}
    if risk.profit_targets:
        for pt in risk.profit_targets:
            minutes = str(pt.get("time_minutes", 0))
            profit_targets[minutes] = pt.get("target", 0.03)
    else:
        tp = risk.take_profit_pct
        profit_targets = {
            "0": tp,
            "20": round(tp * 0.85, 3),
            "40": round(tp * 0.7, 3),
            "60": round(tp * 0.55, 3),
            "120": round(tp * 0.35, 3),
        }
    
    # 追蹤止損映射
    trailing_trigger = 0.04
    trailing_drawback = 0.015
    if risk.trailing_stop and risk.trailing_stop_pct:
        trailing_trigger = round(risk.take_profit_pct * 0.5, 3)
        trailing_drawback = risk.trailing_stop_pct
    
    default_exit_params = {
        "hard_stop_loss": risk.stop_loss_pct,
        "atr_stop_multiplier": 2.0,
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
    
    # 策略類型判斷
    strategy_type = _infer_strategy_type(chrom)
    
    # 生成策略 ID — 保留原始大小寫，前綴 genetic_
    strategy_id = f"genetic_{chrom.chromosome_id.lower()}"
    
    return {
        "id": strategy_id,
        "name": f"GEN {chrom.chromosome_id[:8]}",
        "name_zh": f"基因策略 {chrom.chromosome_id[:8]}",
        "type": strategy_type,
        "enabled": True,
        "description": chrom.summary(),
        "description_zh": f"基因演算法生成，世代={chrom.generation}, 親代={chrom.parent_ids}",
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


def _gene_to_condition_name(gene: IndicatorGene, prefix: str) -> str:
    """
    將基因轉換為現有系統可識別的條件名稱
    映射到 strategy_conditions.py 中已實作的 38 個檢查器
    """
    name = gene.name
    cond = gene.condition.value
    
    # ── 趨勢指標 ──
    if name == "ema_cross":
        if cond == "cross_up":
            return "ema_cross_above"
        elif cond == "cross_down":
            return "ema_cross_below"
        else:
            return "ema_cross_above"
    
    elif name == "sma_cross":
        # 映射到現有 MA 交叉檢查器（固定 5/20 週期，基因參數被忽略）
        if cond == "cross_up":
            return "ma5_cross_ma20"
        elif cond == "cross_down":
            return "ma5_cross_below_ma20"
        else:
            return "ma5_cross_ma20"
    
    elif name == "adx":
        # 映射到現有固定閾值 ADX 檢查器
        if cond == "above":
            return "adx_above_25"
        else:
            return "adx_above_20"
    
    elif name == "supertrend":
        return "supertrend"
    
    elif name == "close_vs_ma":
        if cond == "above":
            return "close_above_ma240"
        elif cond == "below":
            return "close_below_ma240"
        else:
            return "close_above_ma240"
    
    # ── 動量指標 ──
    elif name == "rsi":
        if cond == "cross_above":
            return "rsi_cross_above_30"
        elif cond == "below":
            return "rsi_below_30"
        elif cond == "above":
            return "rsi_cross_above_40"
        else:
            return "rsi_cross_above_30"
    
    elif name == "stochastic":
        if cond in ("cross_up", "cross_above"):
            return "fastk_cross_above_fastd"
        elif cond == "below":
            return "fastk_below_20"
        else:
            return "fastk_cross_above_fastd"
    
    elif name == "cci":
        return "rsi_cross_above_40"  # fallback
    
    elif name == "momentum":
        return "rsi_cross_above_30"  # fallback
    
    # ── 波動指標 ──
    elif name == "bbands":
        if cond == "below":
            return "price_below_bb_lower"
        elif cond == "above":
            return "price_below_bb_lower_pct"
        else:
            return "price_below_bb_lower"
    
    elif name == "keltner":
        return "keltner_breakout"
    
    elif name == "atr":
        if cond == "above":
            return "atr_breakout"
        else:
            return "atr_below_threshold"
    
    # ── 量能指標 ──
    elif name == "volume_sma_ratio":
        if cond == "above":
            return "volume_spike"
        else:
            return "volume_above_avg_1_5x"
    
    elif name == "obv":
        return "volume_confirmed"
    
    elif name == "vwap":
        return "price_above_trend"
    
    # MACD fallback
    elif name == "macd":
        if cond == "cross_up":
            return "ema_cross_above"
        elif cond == "cross_down":
            return "ema_cross_below"
        else:
            return "ema_cross_above"
    
    else:
        return "ema_cross_above"


def _infer_strategy_type(chrom: StrategyChromosome) -> str:
    """從基因體推斷策略類型"""
    # 看進場基因中哪種類型最多
    type_counts = {}
    for g in chrom.entry_genes:
        t = g.indicator_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    
    if not type_counts:
        return "trend"
    
    dominant = max(type_counts, key=type_counts.get)
    return dominant


def convert_population_to_strategies_json(
    chromosomes: List[StrategyChromosome],
    existing: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    將一群染色體轉換為完整的 strategies.json 格式
    
    existing: 若有現有配置，保留 version/registry_settings 等元數據
    """
    strategies = [convert_to_strategy_json(c) for c in chromosomes]
    
    result = {
        "version": "genetic_v1",
        "last_updated": __import__("datetime").datetime.now().isoformat(),
        "description": "Strategies generated by Genetic Evolution Engine",
        "strategies": strategies,
        "registry_settings": {
            "auto_evolve": True,
            "evolution_cycle": 6,
            "live_pool_size": 5,
        },
    }
    
    if existing:
        result["version"] = existing.get("version", "genetic_v1")
        # 保留現有的 registry_settings 但覆蓋我們的
        old_registry = existing.get("registry_settings", {})
        old_registry.update(result["registry_settings"])
        result["registry_settings"] = old_registry
    
    return result
