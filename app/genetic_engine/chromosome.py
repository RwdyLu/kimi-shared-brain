#!/usr/bin/env python3
"""
Strategy Chromosome / 策略基因體

一個完整的交易策略 = 一條染色體
包含：進場邏輯、出場邏輯、風控參數、過濾條件

Author: second_bot
Date: 2026-05-22
"""

import random
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .gene_library import (
    IndicatorGene, IndicatorType, ConditionType,
    random_gene, mutate_gene, crossover_genes,
    get_genes_by_type, validate_gene
)


@dataclass
class RiskGenes:
    """風控基因 — 止損止盈倉位持倉時間"""
    stop_loss_pct: float = -0.05       # 硬止損 -5%
    take_profit_pct: float = 0.08      # 硬止盈 8%
    position_pct: float = 0.15         # 倉位 15%
    max_hold_bars: int = 72            # 最大持倉 72 根 5m K 線 = 6h
    trailing_stop: bool = False       # 是否追蹤止損
    trailing_stop_pct: Optional[float] = None  # 追蹤止損距離
    
    # 階梯止盈（gene-specific，可選）
    profit_targets: Optional[List[Dict[str, float]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "position_pct": self.position_pct,
            "max_hold_bars": self.max_hold_bars,
            "trailing_stop": self.trailing_stop,
            "trailing_stop_pct": self.trailing_stop_pct,
        }
        if self.profit_targets:
            d["profit_targets"] = self.profit_targets
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RiskGenes":
        return cls(
            stop_loss_pct=d.get("stop_loss_pct", -0.05),
            take_profit_pct=d.get("take_profit_pct", 0.08),
            position_pct=d.get("position_pct", 0.15),
            max_hold_bars=d.get("max_hold_bars", 72),
            trailing_stop=d.get("trailing_stop", False),
            trailing_stop_pct=d.get("trailing_stop_pct"),
            profit_targets=d.get("profit_targets"),
        )


@dataclass
class StrategyChromosome:
    """
    完整策略基因體
    
    類比生物基因體：
    - entry_genes = 進場觸發基因（多個基因的邏輯組合）
    - exit_genes = 出場觸發基因
    - risk_genes = 風控基因（止損止盈倉位）
    - trend_filter = 趨勢過濾基因（如 ADX > 20）
    - volume_filter = 量能過濾基因
    """
    # === 必填字段（無默認值） ===
    chromosome_id: str
    entry_genes: List[IndicatorGene]
    exit_genes: List[IndicatorGene]
    
    # === 可選字段（有默認值） ===
    entry_logic: str = "AND"  # "AND", "OR", "WEIGHTED"
    entry_min_weight: float = 0.5
    exit_logic: str = "OR"
    exit_min_weight: float = 0.3
    risk_genes: RiskGenes = field(default_factory=RiskGenes)
    trend_filter: Optional[IndicatorGene] = None
    volume_filter: Optional[IndicatorGene] = None
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    fitness_score: Optional[float] = None
    fitness_details: Dict[str, float] = field(default_factory=dict)
    paper_trades: int = 0
    paper_pnl: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chromosome_id": self.chromosome_id,
            "entry_genes": [g.to_dict() for g in self.entry_genes],
            "entry_logic": self.entry_logic,
            "entry_min_weight": self.entry_min_weight,
            "exit_genes": [g.to_dict() for g in self.exit_genes],
            "exit_logic": self.exit_logic,
            "exit_min_weight": self.exit_min_weight,
            "risk_genes": self.risk_genes.to_dict(),
            "trend_filter": self.trend_filter.to_dict() if self.trend_filter else None,
            "volume_filter": self.volume_filter.to_dict() if self.volume_filter else None,
            "generation": self.generation,
            "parent_ids": self.parent_ids,
            "created_at": self.created_at,
            "fitness_score": self.fitness_score,
            "fitness_details": self.fitness_details,
            "paper_trades": self.paper_trades,
            "paper_pnl": self.paper_pnl,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategyChromosome":
        return cls(
            chromosome_id=d["chromosome_id"],
            entry_genes=[IndicatorGene.from_dict(g) for g in d.get("entry_genes", [])],
            entry_logic=d.get("entry_logic", "AND"),
            entry_min_weight=d.get("entry_min_weight", 0.5),
            exit_genes=[IndicatorGene.from_dict(g) for g in d.get("exit_genes", [])],
            exit_logic=d.get("exit_logic", "OR"),
            exit_min_weight=d.get("exit_min_weight", 0.3),
            risk_genes=RiskGenes.from_dict(d.get("risk_genes", {})),
            trend_filter=IndicatorGene.from_dict(d["trend_filter"]) if d.get("trend_filter") else None,
            volume_filter=IndicatorGene.from_dict(d["volume_filter"]) if d.get("volume_filter") else None,
            generation=d.get("generation", 0),
            parent_ids=d.get("parent_ids", []),
            created_at=d.get("created_at", datetime.now().isoformat()),
            fitness_score=d.get("fitness_score"),
            fitness_details=d.get("fitness_details", {}),
            paper_trades=d.get("paper_trades", 0),
            paper_pnl=d.get("paper_pnl", 0.0),
        )
    
    def summary(self) -> str:
        """簡短文字描述"""
        entry_names = " + ".join([g.name for g in self.entry_genes])
        exit_names = " + ".join([g.name for g in self.exit_genes])
        filters = []
        if self.trend_filter:
            filters.append(f"trend={self.trend_filter.name}")
        if self.volume_filter:
            filters.append(f"vol={self.volume_filter.name}")
        
        fit = f"fit={self.fitness_score:.3f}" if self.fitness_score else "fit=??"
        
        return (
            f"[{self.chromosome_id[:8]}] G{self.generation} | "
            f"Entry({self.entry_logic}): {entry_names} | "
            f"Exit({self.exit_logic}): {exit_names} | "
            f"Risk: SL={self.risk_genes.stop_loss_pct:.1%} TP={self.risk_genes.take_profit_pct:.1%} | "
            f"{fit}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 染色體生成器
# ═══════════════════════════════════════════════════════════════════════════════

def random_chromosome(
    generation: int = 0,
    min_entry_genes: int = 1,
    max_entry_genes: int = 4,
    min_exit_genes: int = 1,
    max_exit_genes: int = 3,
    with_filters: bool = True,
) -> StrategyChromosome:
    """
    隨機生成一個策略染色體（Genesis / 創世）
    """
    cid = f"GEN_{uuid.uuid4().hex[:12].upper()}"
    
    # 進場基因：混合趨勢 + 動量 + 量能
    n_entry = random.randint(min_entry_genes, max_entry_genes)
    entry_genes = []
    
    # 至少一個趨勢基因
    trend_genes = get_genes_by_type(IndicatorType.TREND)
    if trend_genes:
        entry_genes.append(random_gene(allowed_names=[random.choice(trend_genes)]))
    
    # 填充剩餘
    while len(entry_genes) < n_entry:
        # 偏好動量和量能作為輔助
        g = random_gene(
            allowed_types=[IndicatorType.MOMENTUM, IndicatorType.VOLUME, IndicatorType.VOLATILITY]
        )
        entry_genes.append(g)
    
    # 出場基因：偏好波動和動量
    n_exit = random.randint(min_exit_genes, max_exit_genes)
    exit_genes = []
    
    # 至少一個動量或波動基因
    mom_vol_genes = get_genes_by_type(IndicatorType.MOMENTUM) + get_genes_by_type(IndicatorType.VOLATILITY)
    if mom_vol_genes:
        exit_genes.append(random_gene(allowed_names=[random.choice(mom_vol_genes)]))
    
    while len(exit_genes) < n_exit:
        g = random_gene(
            allowed_types=[IndicatorType.MOMENTUM, IndicatorType.VOLATILITY, IndicatorType.TREND]
        )
        exit_genes.append(g)
    
    # 風控基因 — 隨機但有合理邊界
    risk = RiskGenes(
        stop_loss_pct=round(random.uniform(-0.10, -0.03), 3),
        take_profit_pct=round(random.uniform(0.03, 0.15), 3),
        position_pct=round(random.uniform(0.05, 0.25), 3),
        max_hold_bars=random.randint(36, 288),  # 3h ~ 24h on 5m
        trailing_stop=random.random() < 0.3,
        trailing_stop_pct=round(random.uniform(0.01, 0.05), 3) if random.random() < 0.3 else None,
    )
    
    # 階梯止盈（30% 概率）
    if random.random() < 0.3:
        risk.profit_targets = [
            {"time_minutes": 30, "target": 0.03},
            {"time_minutes": 120, "target": 0.06},
        ]
    
    # 過濾條件
    trend_filter = None
    volume_filter = None
    
    if with_filters:
        # 50% 概率有趨勢過濾
        if random.random() < 0.5:
            adx_genes = get_genes_by_type(IndicatorType.TREND)
            if adx_genes:
                trend_filter = random_gene(allowed_names=["adx"])
                trend_filter.condition = ConditionType.ABOVE
                trend_filter.threshold = random.randint(18, 35)
        
        # 30% 概率有量能過濾
        if random.random() < 0.3:
            vol_genes = get_genes_by_type(IndicatorType.VOLUME)
            if vol_genes:
                volume_filter = random_gene(allowed_names=[random.choice(vol_genes)])
                volume_filter.condition = ConditionType.ABOVE
                volume_filter.threshold = round(random.uniform(1.0, 2.5), 2)
    
    return StrategyChromosome(
        chromosome_id=cid,
        entry_genes=entry_genes,
        entry_logic=random.choice(["AND", "OR", "WEIGHTED"]),
        entry_min_weight=round(random.uniform(0.3, 0.7), 2),
        exit_genes=exit_genes,
        exit_logic="OR",  # 出場永遠用 OR（安全）
        exit_min_weight=0.3,
        risk_genes=risk,
        trend_filter=trend_filter,
        volume_filter=volume_filter,
        generation=generation,
    )


def mutate_chromosome(
    chrom: StrategyChromosome,
    generation: int,
    mutation_rate: float = 0.3,
    intensity: float = 0.3,
) -> StrategyChromosome:
    """
    突變一個染色體，產生新個體
    """
    new_id = f"MUT_{uuid.uuid4().hex[:12].upper()}"
    
    # 複製基因
    new_entry = [IndicatorGene.from_dict(g.to_dict()) for g in chrom.entry_genes]
    new_exit = [IndicatorGene.from_dict(g.to_dict()) for g in chrom.exit_genes]
    new_risk = RiskGenes.from_dict(chrom.risk_genes.to_dict())
    new_trend = IndicatorGene.from_dict(chrom.trend_filter.to_dict()) if chrom.trend_filter else None
    new_volume = IndicatorGene.from_dict(chrom.volume_filter.to_dict()) if chrom.volume_filter else None
    
    # 突變進場基因
    for g in new_entry:
        if random.random() < mutation_rate:
            mutate_gene(g, intensity)
    
    # 可能增加或刪除進場基因
    if random.random() < mutation_rate * 0.3 and len(new_entry) < 5:
        new_entry.append(random_gene())
    if random.random() < mutation_rate * 0.2 and len(new_entry) > 1:
        new_entry.pop(random.randint(0, len(new_entry) - 1))
    
    # 突變出場基因
    for g in new_exit:
        if random.random() < mutation_rate:
            mutate_gene(g, intensity)
    
    # 突變風控基因
    if random.random() < mutation_rate:
        # 止損：在現值 ±20% 擾動
        delta = abs(new_risk.stop_loss_pct) * intensity * 0.5
        new_risk.stop_loss_pct = round(
            max(-0.15, min(-0.02, new_risk.stop_loss_pct + random.uniform(-delta, delta))), 3
        )
    
    if random.random() < mutation_rate:
        delta = new_risk.take_profit_pct * intensity * 0.5
        new_risk.take_profit_pct = round(
            max(0.02, min(0.20, new_risk.take_profit_pct + random.uniform(-delta, delta))), 3
        )
    
    if random.random() < mutation_rate:
        new_risk.position_pct = round(
            max(0.05, min(0.30, new_risk.position_pct + random.uniform(-0.05, 0.05))), 3
        )
    
    if random.random() < mutation_rate * 0.5:
        new_risk.max_hold_bars = max(12, min(576, 
            new_risk.max_hold_bars + random.randint(-24, 24)))
    
    # 突變邏輯模式
    new_entry_logic = chrom.entry_logic
    if random.random() < mutation_rate * 0.3:
        new_entry_logic = random.choice(["AND", "OR", "WEIGHTED"])
    
    return StrategyChromosome(
        chromosome_id=new_id,
        entry_genes=new_entry,
        entry_logic=new_entry_logic,
        entry_min_weight=chrom.entry_min_weight,
        exit_genes=new_exit,
        exit_logic=chrom.exit_logic,
        exit_min_weight=chrom.exit_min_weight,
        risk_genes=new_risk,
        trend_filter=new_trend,
        volume_filter=new_volume,
        generation=generation,
        parent_ids=[chrom.chromosome_id],
    )


def crossover_chromosomes(
    parent1: StrategyChromosome,
    parent2: StrategyChromosome,
    generation: int,
) -> StrategyChromosome:
    """
    兩個染色體交叉，產生後代
    """
    new_id = f"X_{uuid.uuid4().hex[:12].upper()}"
    
    # 進場基因：從父母中各取一部分
    entry_from_p1 = random.randint(0, len(parent1.entry_genes))
    entry_from_p2 = max(1, len(parent2.entry_genes) - entry_from_p1)
    
    new_entry = []
    for i in range(entry_from_p1):
        if i < len(parent1.entry_genes):
            new_entry.append(IndicatorGene.from_dict(parent1.entry_genes[i].to_dict()))
    for i in range(entry_from_p2):
        if i < len(parent2.entry_genes):
            new_entry.append(IndicatorGene.from_dict(parent2.entry_genes[i].to_dict()))
    
    if not new_entry:
        new_entry = [random_gene()]
    
    # 出場基因：取表現較好者的大部分
    new_exit = []
    p1_better = (parent1.fitness_score or 0) > (parent2.fitness_score or 0)
    primary_exit = parent1.exit_genes if p1_better else parent2.exit_genes
    secondary_exit = parent2.exit_genes if p1_better else parent1.exit_genes
    
    n_primary = random.randint(1, max(1, len(primary_exit)))
    for i in range(n_primary):
        if i < len(primary_exit):
            new_exit.append(IndicatorGene.from_dict(primary_exit[i].to_dict()))
    
    if len(new_exit) < 2 and secondary_exit:
        new_exit.append(IndicatorGene.from_dict(secondary_exit[0].to_dict()))
    
    # 風控：混合
    new_risk = RiskGenes(
        stop_loss_pct=round((parent1.risk_genes.stop_loss_pct + parent2.risk_genes.stop_loss_pct) / 2, 3),
        take_profit_pct=round((parent1.risk_genes.take_profit_pct + parent2.risk_genes.take_profit_pct) / 2, 3),
        position_pct=round((parent1.risk_genes.position_pct + parent2.risk_genes.position_pct) / 2, 3),
        max_hold_bars=(parent1.risk_genes.max_hold_bars + parent2.risk_genes.max_hold_bars) // 2,
        trailing_stop=random.choice([parent1.risk_genes.trailing_stop, parent2.risk_genes.trailing_stop]),
    )
    
    # 微擾動（防止完全一樣）
    new_risk.stop_loss_pct += random.uniform(-0.005, 0.005)
    new_risk.stop_loss_pct = round(max(-0.15, min(-0.02, new_risk.stop_loss_pct)), 3)
    
    # 過濾器：從較好者繼承
    new_trend = None
    new_volume = None
    if p1_better and parent1.trend_filter:
        new_trend = IndicatorGene.from_dict(parent1.trend_filter.to_dict())
    elif parent2.trend_filter:
        new_trend = IndicatorGene.from_dict(parent2.trend_filter.to_dict())
    
    if p1_better and parent1.volume_filter:
        new_volume = IndicatorGene.from_dict(parent1.volume_filter.to_dict())
    elif parent2.volume_filter:
        new_volume = IndicatorGene.from_dict(parent2.volume_filter.to_dict())
    
    return StrategyChromosome(
        chromosome_id=new_id,
        entry_genes=new_entry,
        entry_logic=random.choice([parent1.entry_logic, parent2.entry_logic]),
        entry_min_weight=round((parent1.entry_min_weight + parent2.entry_min_weight) / 2, 2),
        exit_genes=new_exit,
        exit_logic="OR",
        exit_min_weight=round((parent1.exit_min_weight + parent2.exit_min_weight) / 2, 2),
        risk_genes=new_risk,
        trend_filter=new_trend,
        volume_filter=new_volume,
        generation=generation,
        parent_ids=[parent1.chromosome_id, parent2.chromosome_id],
    )


def validate_chromosome(chrom: StrategyChromosome) -> bool:
    """驗證染色體合法性"""
    if not chrom.entry_genes:
        return False
    if not chrom.exit_genes:
        return False
    
    # 檢查止損止盈合理性
    if chrom.risk_genes.stop_loss_pct >= 0:
        return False
    if chrom.risk_genes.take_profit_pct <= 0:
        return False
    if chrom.risk_genes.position_pct <= 0 or chrom.risk_genes.position_pct > 1.0:
        return False
    
    # 檢查所有基因
    for g in chrom.entry_genes + chrom.exit_genes:
        if not validate_gene(g):
            return False
    
    if chrom.trend_filter and not validate_gene(chrom.trend_filter):
        return False
    if chrom.volume_filter and not validate_gene(chrom.volume_filter):
        return False
    
    return True
