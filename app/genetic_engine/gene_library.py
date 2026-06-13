#!/usr/bin/env python3
"""
Indicator Gene Library / 指標基因庫

定義所有可用於策略基因體的「指標基因」。
每個基因是一個可計算的技術指標 + 條件判斷的組合。

參考開源項目:
- Freqtrade 的 sample_strategy / FreqAI feature engineering
- TA-Lib 的指標分類
- Backtrader 的 Indicator 架構

Author: second_bot
Date: 2026-05-22
"""

import random
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class IndicatorType(Enum):
    """指標類型分類"""
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    PATTERN = "pattern"


class ConditionType(Enum):
    """條件判斷類型"""
    ABOVE = "above"           # 值 > 閾值
    BELOW = "below"           # 值 < 閾值
    CROSS_UP = "cross_up"     # 上穿
    CROSS_DOWN = "cross_down" # 下穿
    BETWEEN = "between"       # 在區間內 (需要兩個閾值)
    OUTSIDE = "outside"       # 在區間外


@dataclass
class IndicatorGene:
    """
    單一指標基因
    
    例如：RSI(14) on 5m < 30 是一個基因
         EMA(5) cross above EMA(20) on 15m 是另一個基因
    """
    name: str                           # 指標名稱
    indicator_type: IndicatorType       # 指標分類
    timeframe: str                      # "5m", "15m", "1h", "4h"
    params: Dict[str, Any] = field(default_factory=dict)   # 指標參數
    condition: ConditionType = ConditionType.ABOVE           # 條件類型
    threshold: float = 0.0                # 主閾值
    threshold2: Optional[float] = None   # 次閾值（BETWEEN/OUTSIDE 用）
    weight: float = 1.0                 # 加權邏輯時的權重
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "indicator_type": self.indicator_type.value,
            "timeframe": self.timeframe,
            "params": self.params,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "threshold2": self.threshold2,
            "weight": self.weight,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IndicatorGene":
        return cls(
            name=d["name"],
            indicator_type=IndicatorType(d["indicator_type"]),
            timeframe=d["timeframe"],
            params=d.get("params", {}),
            condition=ConditionType(d["condition"]),
            threshold=d["threshold"],
            threshold2=d.get("threshold2"),
            weight=d.get("weight", 1.0),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 基因庫定義 — 每個指標的參數空間和合理取值範圍
# ═══════════════════════════════════════════════════════════════════════════════

GENE_LIBRARY: Dict[str, Dict[str, Any]] = {
    # ── 趨勢指標 ──
    "ema_cross": {
        "type": IndicatorType.TREND,
        "params": {
            "short_period": (3, 50),      # (min, max)
            "long_period": (10, 200),
        },
        "conditions": [ConditionType.CROSS_UP, ConditionType.CROSS_DOWN],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "EMA short crosses EMA long",
    },
    "sma_cross": {
        "type": IndicatorType.TREND,
        "params": {
            "short_period": (5, 50),
            "long_period": (20, 200),
        },
        "conditions": [ConditionType.CROSS_UP, ConditionType.CROSS_DOWN],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "SMA short crosses SMA long",
    },
    "macd": {
        "type": IndicatorType.TREND,
        "params": {
            "fast": (8, 20),
            "slow": (18, 35),
            "signal": (5, 15),
        },
        "conditions": [ConditionType.CROSS_UP, ConditionType.CROSS_DOWN, ConditionType.ABOVE, ConditionType.BELOW],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "threshold_range": (-0.5, 0.5),  # MACD histogram value
        "description": "MACD histogram",
    },
    "adx": {
        "type": IndicatorType.TREND,
        "params": {
            "period": (10, 30),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW],
        "threshold_range": (15, 50),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "ADX trend strength",
    },
    "supertrend": {
        "type": IndicatorType.TREND,
        "params": {
            "period": (7, 14),
            "multiplier": (2.0, 4.0),
        },
        "conditions": [ConditionType.CROSS_UP, ConditionType.CROSS_DOWN],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Supertrend direction change",
    },
    "close_vs_ma": {
        "type": IndicatorType.TREND,
        "params": {
            "ma_period": (20, 240),
            "ma_type": ["ema", "sma", "wma"],
        },
        "conditions": [ConditionType.CROSS_UP, ConditionType.CROSS_DOWN, ConditionType.ABOVE, ConditionType.BELOW],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Price vs Moving Average",
    },
    
    # ── 動量指標 ──
    "rsi": {
        "type": IndicatorType.MOMENTUM,
        "params": {
            "period": (7, 21),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW, ConditionType.BETWEEN, ConditionType.OUTSIDE],
        "threshold_range": (20, 80),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "RSI momentum",
    },
    "stochastic": {
        "type": IndicatorType.MOMENTUM,
        "params": {
            "k_period": (5, 21),
            "d_period": (3, 7),
            "smooth": (1, 3),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW, ConditionType.CROSS_UP, ConditionType.CROSS_DOWN],
        "threshold_range": (10, 90),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Stochastic oscillator",
    },
    "cci": {
        "type": IndicatorType.MOMENTUM,
        "params": {
            "period": (10, 30),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW],
        "threshold_range": (-150, 150),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "CCI commodity channel index",
    },
    "momentum": {
        "type": IndicatorType.MOMENTUM,
        "params": {
            "period": (5, 20),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW],
        "threshold_range": (-5, 5),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Price momentum",
    },
    
    # ── 波動指標 ──
    "bbands": {
        "type": IndicatorType.VOLATILITY,
        "params": {
            "period": (10, 30),
            "std_dev": (1.5, 3.0),
        },
        "conditions": [ConditionType.BELOW, ConditionType.ABOVE, ConditionType.BETWEEN],
        "threshold_range": (-3, 3),  # z-score like
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Bollinger Bands position",
    },
    "atr": {
        "type": IndicatorType.VOLATILITY,
        "params": {
            "period": (7, 21),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW],
        "threshold_range": (0.001, 0.05),  # ATR as % of price
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "ATR volatility",
    },
    "keltner": {
        "type": IndicatorType.VOLATILITY,
        "params": {
            "ema_period": (15, 25),
            "atr_period": (7, 14),
            "multiplier": (1.5, 3.0),
        },
        "conditions": [ConditionType.BELOW, ConditionType.ABOVE, ConditionType.BETWEEN],
        "threshold_range": (-3, 3),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Keltner Channel position",
    },
    
    # ── 量能指標 ──
    "volume_sma_ratio": {
        "type": IndicatorType.VOLUME,
        "params": {
            "period": (10, 30),
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW],
        "threshold_range": (0.8, 3.0),
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "Volume vs SMA ratio",
    },
    "obv": {
        "type": IndicatorType.VOLUME,
        "params": {
            "smooth_period": (5, 20),
        },
        "conditions": [ConditionType.CROSS_UP, ConditionType.CROSS_DOWN],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "OBV direction",
    },
    "vwap": {
        "type": IndicatorType.VOLUME,
        "params": {
            "anchor": ["session", "daily", "weekly"],
        },
        "conditions": [ConditionType.ABOVE, ConditionType.BELOW, ConditionType.CROSS_UP, ConditionType.CROSS_DOWN],
        "timeframes": ["5m", "15m", "1h", "4h"],
        "description": "VWAP position",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# 基因生成器
# ═══════════════════════════════════════════════════════════════════════════════

def random_gene(
    allowed_types: Optional[List[IndicatorType]] = None,
    allowed_names: Optional[List[str]] = None,
    timeframe_bias: Optional[str] = None,
) -> IndicatorGene:
    """
    隨機生成一個指標基因
    
    Args:
        allowed_types: 只從這些類型中選
        allowed_names: 只從這些指標名中選
        timeframe_bias: 偏好時間框架（如 "5m"）
    """
    # 過濾基因庫
    pool = GENE_LIBRARY.copy()
    if allowed_names:
        pool = {k: v for k, v in pool.items() if k in allowed_names}
    if allowed_types:
        pool = {k: v for k, v in pool.items() if v["type"] in allowed_types}
    
    if not pool:
        raise ValueError("No genes match the filter criteria")
    
    # 隨機選指標
    name = random.choice(list(pool.keys()))
    meta = pool[name]
    
    # 隨機選時間框架
    if timeframe_bias and timeframe_bias in meta["timeframes"]:
        tf = timeframe_bias
    else:
        tf = random.choice(meta["timeframes"])
    
    # 隨機生成參數
    params = {}
    for param_name, param_range in meta.get("params", {}).items():
        if isinstance(param_range, tuple) and len(param_range) == 2:
            if isinstance(param_range[0], int):
                params[param_name] = random.randint(param_range[0], param_range[1])
            else:
                params[param_name] = round(random.uniform(param_range[0], param_range[1]), 2)
        elif isinstance(param_range, list):
            params[param_name] = random.choice(param_range)
    
    # 隨機選條件
    condition = random.choice(meta["conditions"])
    
    # 隨機生成閾值
    threshold_range = meta.get("threshold_range", (0, 100))
    threshold = round(random.uniform(threshold_range[0], threshold_range[1]), 3)
    
    threshold2 = None
    if condition in (ConditionType.BETWEEN, ConditionType.OUTSIDE):
        # 第二個閾值要與第一個不同
        t_min, t_max = threshold_range
        threshold2 = round(random.uniform(t_min, t_max), 3)
        # 確保有意義的區間
        if abs(threshold2 - threshold) < (t_max - t_min) * 0.1:
            threshold2 = threshold + (t_max - t_min) * 0.2
            threshold2 = max(t_min, min(t_max, threshold2))
    
    return IndicatorGene(
        name=name,
        indicator_type=meta["type"],
        timeframe=tf,
        params=params,
        condition=condition,
        threshold=threshold,
        threshold2=threshold2,
        weight=round(random.uniform(0.5, 1.5), 2),
    )


def mutate_gene(gene: IndicatorGene, intensity: float = 0.3) -> IndicatorGene:
    """
    突變一個基因
    
    intensity: 0.0~1.0，越高變化越大
    """
    if gene.name not in GENE_LIBRARY:
        return gene  # unknown gene, can't mutate safely
    
    meta = GENE_LIBRARY[gene.name]
    new_params = dict(gene.params)
    
    # 隨機選擇突變點
    mutation_roll = random.random()
    
    if mutation_roll < 0.4:
        # 突變參數
        for param_name, param_range in meta.get("params", {}).items():
            if random.random() < intensity:
                if isinstance(param_range, tuple) and len(param_range) == 2:
                    if isinstance(param_range[0], int):
                        # 整數參數：在現值附近擾動
                        current = new_params.get(param_name, param_range[0])
                        delta = max(1, int((param_range[1] - param_range[0]) * intensity * 0.5))
                        new_val = current + random.randint(-delta, delta)
                        new_params[param_name] = max(param_range[0], min(param_range[1], new_val))
                    else:
                        # 浮點參數
                        current = new_params.get(param_name, param_range[0])
                        delta = (param_range[1] - param_range[0]) * intensity * 0.5
                        new_val = current + random.uniform(-delta, delta)
                        new_params[param_name] = round(max(param_range[0], min(param_range[1], new_val)), 2)
                elif isinstance(param_range, list):
                    new_params[param_name] = random.choice(param_range)
    
    elif mutation_roll < 0.7:
        # 突變閾值
        tr = meta.get("threshold_range", (0, 100))
        delta = (tr[1] - tr[0]) * intensity
        new_threshold = gene.threshold + random.uniform(-delta, delta)
        gene.threshold = round(max(tr[0], min(tr[1], new_threshold)), 3)
        
        if gene.threshold2 is not None:
            new_t2 = gene.threshold2 + random.uniform(-delta, delta)
            gene.threshold2 = round(max(tr[0], min(tr[1], new_t2)), 3)
    
    else:
        # 突變時間框架
        gene.timeframe = random.choice(meta["timeframes"])
    
    gene.params = new_params
    return gene


def crossover_genes(gene1: IndicatorGene, gene2: IndicatorGene) -> IndicatorGene:
    """
    兩個基因的交叉。只有同類型基因才能交叉。
    """
    if gene1.name != gene2.name:
        # 不同指標，隨機選一個
        return random.choice([gene1, gene2]).__class__.from_dict(
            random.choice([gene1, gene2]).to_dict()
        )
    
    # 同指標：參數混合
    child_params = {}
    for key in gene1.params:
        child_params[key] = random.choice([gene1.params[key], gene2.params[key]])
    
    # 閾值取平均 + 微擾
    threshold = (gene1.threshold + gene2.threshold) / 2
    threshold += random.uniform(-abs(gene1.threshold - gene2.threshold) * 0.2,
                                 abs(gene1.threshold - gene2.threshold) * 0.2)
    
    threshold2 = None
    if gene1.threshold2 is not None and gene2.threshold2 is not None:
        threshold2 = (gene1.threshold2 + gene2.threshold2) / 2
    
    return IndicatorGene(
        name=gene1.name,
        indicator_type=gene1.indicator_type,
        timeframe=random.choice([gene1.timeframe, gene2.timeframe]),
        params=child_params,
        condition=random.choice([gene1.condition, gene2.condition]),
        threshold=round(threshold, 3),
        threshold2=round(threshold2, 3) if threshold2 else None,
        weight=round((gene1.weight + gene2.weight) / 2, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函數
# ═══════════════════════════════════════════════════════════════════════════════

def get_genes_by_type(indicator_type: IndicatorType) -> List[str]:
    """獲取某類型的所有基因名稱"""
    return [k for k, v in GENE_LIBRARY.items() if v["type"] == indicator_type]


def get_gene_description(name: str) -> str:
    """獲取基因描述"""
    return GENE_LIBRARY.get(name, {}).get("description", "Unknown")


def validate_gene(gene: IndicatorGene) -> bool:
    """驗證基因是否在合理範圍內"""
    if gene.name not in GENE_LIBRARY:
        return False
    meta = GENE_LIBRARY[gene.name]
    
    # 檢查參數範圍
    for param_name, param_range in meta.get("params", {}).items():
        val = gene.params.get(param_name)
        if val is None:
            continue
        if isinstance(param_range, tuple):
            if not (param_range[0] <= val <= param_range[1]):
                return False
        elif isinstance(param_range, list):
            if val not in param_range:
                return False
    
    # 檢查條件是否合法
    if gene.condition not in meta.get("conditions", []):
        return False
    
    # 檢查時間框架
    if gene.timeframe not in meta.get("timeframes", []):
        return False
    
    return True
