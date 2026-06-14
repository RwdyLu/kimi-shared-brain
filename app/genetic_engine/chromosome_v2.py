#!/usr/bin/env python3
"""
Strategy Chromosome V2 / 策略基因體 V2

擴展原有染色體結構，加入：
- 宏觀基因組（Macro Genes）：定投節奏、大盤偏離閾值、月相壓力、EMA 錨點
- 微觀基因組（Micro Genes）：PDE 動力學權重 (kp/kv/ka)、最小開火閾值、微觀調撥率
- 保持向後兼容：原有 entry/exit/risk 結構不變

Reference: 《核心準則》第一篇章

Author: second_bot
Date: 2026-05-28
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


# ═══════════════════════════════════════════════════════════════════════════════
# V2 新增：宏觀基因組（Macro Genes）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MacroGenes:
    """
    宏觀基因組 — 老農定投模型
    
    決定系統在長周期（日線/4小時）級別的資產配置與建倉節奏
    """
    # 最大定投月數：限制宏觀子彈消耗速度
    max_dca_months: int = 12
    
    # 大盤偏離度閾值：觸發滴灌或深跌加倉的價格偏離門檻
    beta_threshold: float = 0.10  # 10% 偏離
    
    # 月相壓力：接近滿月時放大定投節奏的強度係數
    moon_phase_pressure: float = 1.0
    
    # 耐心耗盡時的強制動用比例
    deadline_force_pct: float = 0.30
    
    # 長期閒置回收門檻（月）
    gc_threshold_months: int = 6
    
    # 長期閒置回收上限比例
    gc_max_ratio: float = 0.50
    
    # Timing 結構基因
    t_macro: int = 20       # 宏觀統計窗口
    t_micro: int = 5        # 微觀統計窗口
    t_deadline: int = 3     # 耐心耗盡期限
    ema_anchor: int = 50    # EMA 錨定期

    # Stage 4: DCA 行為基因
    dca_interval: int = 24       # 定投間隔（K 線根數）
    hold_period: int = 48        # 最大持倉 K 線數，超過強制出場
    recycle_ratio: float = 0.20  # 實現盈利再投入比例 [0, 1]

    # Stage 4: 目標持倉權重（用於 kp/kv/ka PDE 公式）
    target_weight: float = 0.50  # 目標倉位佔比

    # Legacy fields remain serializable so archived chromosomes still load, but
    # only behaviorally connected fields participate in GA exploration.
    ACTIVE_EVOLUTION_FIELDS = (
        "t_macro",
        "t_micro",
        "t_deadline",
        "dca_interval",
        "hold_period",
        "recycle_ratio",
        "target_weight",
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_dca_months": self.max_dca_months,
            "beta_threshold": self.beta_threshold,
            "moon_phase_pressure": self.moon_phase_pressure,
            "deadline_force_pct": self.deadline_force_pct,
            "gc_threshold_months": self.gc_threshold_months,
            "gc_max_ratio": self.gc_max_ratio,
            "t_macro": self.t_macro,
            "t_micro": self.t_micro,
            "t_deadline": self.t_deadline,
            "ema_anchor": self.ema_anchor,
            "dca_interval": self.dca_interval,
            "hold_period": self.hold_period,
            "recycle_ratio": self.recycle_ratio,
            "target_weight": self.target_weight,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MacroGenes":
        return cls(
            max_dca_months=d.get("max_dca_months", 12),
            beta_threshold=d.get("beta_threshold", 0.10),
            moon_phase_pressure=d.get("moon_phase_pressure", 1.0),
            deadline_force_pct=d.get("deadline_force_pct", 0.30),
            gc_threshold_months=d.get("gc_threshold_months", 6),
            gc_max_ratio=d.get("gc_max_ratio", 0.50),
            t_macro=d.get("t_macro", 20),
            t_micro=d.get("t_micro", 5),
            t_deadline=d.get("t_deadline", 3),
            ema_anchor=d.get("ema_anchor", 50),
            dca_interval=d.get("dca_interval", 24),
            hold_period=d.get("hold_period", 48),
            recycle_ratio=d.get("recycle_ratio", 0.20),
            target_weight=d.get("target_weight", 0.50),
        )
    
    @classmethod
    def random(cls) -> "MacroGenes":
        """Randomize only macro genes that currently affect backtest behavior."""
        return cls(
            t_macro=random.randint(10, 50),
            t_micro=random.randint(1, 15),
            t_deadline=random.randint(1, 6),
            dca_interval=random.randint(1, 100),
            hold_period=random.randint(10, 200),
            recycle_ratio=round(random.uniform(0.0, 0.5), 3),
            target_weight=round(random.uniform(0.2, 0.8), 3),
        )
    
    def mutate(self, intensity: float = 0.3) -> "MacroGenes":
        """突變宏觀基因"""
        new = MacroGenes.from_dict(self.to_dict())
        
        # 各參數獨立以一定概率擾動
        fields_float = [
            ("recycle_ratio", 0.0, 0.80),
            ("target_weight", 0.10, 0.90),
        ]
        
        for field_name, min_v, max_v in fields_float:
            if random.random() < 0.3:
                current = getattr(new, field_name)
                delta = current * intensity * random.uniform(-1, 1)
                new_val = max(min_v, min(max_v, current + delta))
                setattr(new, field_name, round(new_val, 3))
        
        fields_int = [
            ("t_macro", 1, 100),
            ("t_micro", 1, 30),
            ("t_deadline", 1, 12),
            ("dca_interval", 1, 200),
            ("hold_period", 5, 500),
        ]
        
        for field_name, min_v, max_v in fields_int:
            if random.random() < 0.3:
                current = getattr(new, field_name)
                delta = int(current * intensity * random.uniform(-1, 1))
                new_val = max(min_v, min(max_v, current + delta))
                setattr(new, field_name, new_val)
        
        return new


# ═══════════════════════════════════════════════════════════════════════════════
# V2 新增：微觀基因組（Micro Genes）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MicroGenes:
    """
    微觀基因組 — 狙擊手動量模型
    
    決定系統在短周期（1分鐘/5分鐘）級別的 PDE 敏感度與開火權限
    """
    # PDE 動力學權重
    kp: float = 0.5   # 位置權重：當前價格距離均值的引力係數
    kv: float = 0.3   # 速度權重：對一階導數（價格變化率）的敏感度
    ka: float = 0.2   # 加速度權重：對二階導數（趨勢反轉與極值點）的敏感度
    
    # 最小交易偏差閾值：極其關鍵的基因
    # 決定目標權重與實際權重偏差達到多少時才允許扣動扳機
    min_trade_threshold: float = 0.02  # 2% 偏差
    
    # 微觀每次調撥率：每次開火時動用可用資金的百分比
    micro_reserve_rate: float = 0.15  # 15%
    
    # Sigmoid 縮放參數（用於條件判斷的平滑化）
    sigmoid_scale: float = 1.0
    
    # Gamma：衰減因子
    gamma: float = 0.95
    
    # Beta：趨勢跟隨係數
    beta: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "kp": self.kp,
            "kv": self.kv,
            "ka": self.ka,
            "min_trade_threshold": self.min_trade_threshold,
            "micro_reserve_rate": self.micro_reserve_rate,
            "sigmoid_scale": self.sigmoid_scale,
            "gamma": self.gamma,
            "beta": self.beta,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MicroGenes":
        return cls(
            kp=d.get("kp", 0.5),
            kv=d.get("kv", 0.3),
            ka=d.get("ka", 0.2),
            min_trade_threshold=d.get("min_trade_threshold", 0.02),
            micro_reserve_rate=d.get("micro_reserve_rate", 0.15),
            sigmoid_scale=d.get("sigmoid_scale", 1.0),
            gamma=d.get("gamma", 0.95),
            beta=d.get("beta", 0.5),
        )
    
    @classmethod
    def random(cls) -> "MicroGenes":
        """隨機生成微觀基因，確保 kp+kv+ka ≈ 1.0"""
        # 隨機生成三個權重後正規化
        raw = [random.uniform(0.1, 1.0) for _ in range(3)]
        total = sum(raw)
        kp, kv, ka = [r / total for r in raw]
        
        return cls(
            kp=round(kp, 3),
            kv=round(kv, 3),
            ka=round(ka, 3),
            min_trade_threshold=round(random.uniform(0.005, 0.10), 4),
            micro_reserve_rate=round(random.uniform(0.05, 0.30), 3),
            sigmoid_scale=round(random.uniform(0.5, 3.0), 2),
            gamma=round(random.uniform(0.80, 0.99), 3),
            beta=round(random.uniform(0.1, 0.9), 2),
        )
    
    def mutate(self, intensity: float = 0.3) -> "MicroGenes":
        """突變微觀基因，保持權重和為 1"""
        new = MicroGenes.from_dict(self.to_dict())
        
        # 擾動 kp, kv, ka
        if random.random() < 0.4:
            delta_kp = new.kp * intensity * random.uniform(-1, 1)
            delta_kv = new.kv * intensity * random.uniform(-1, 1)
            
            new.kp = max(0.05, min(0.90, new.kp + delta_kp))
            new.kv = max(0.05, min(0.90, new.kv + delta_kv))
            # ka 由補差得到，確保和為 1
            new.ka = max(0.05, min(0.90, 1.0 - new.kp - new.kv))
            
            # 最後正規化
            total = new.kp + new.kv + new.ka
            new.kp = round(new.kp / total, 3)
            new.kv = round(new.kv / total, 3)
            new.ka = round(new.ka / total, 3)
        
        # 其他參數
        if random.random() < 0.3:
            new.min_trade_threshold = max(0.001, min(0.20,
                new.min_trade_threshold + random.uniform(-0.01, 0.01)))
        
        if random.random() < 0.3:
            new.micro_reserve_rate = max(0.02, min(0.50,
                new.micro_reserve_rate + random.uniform(-0.05, 0.05)))

        if random.random() < 0.3:
            new.sigmoid_scale = round(max(0.1, min(
                10.0,
                new.sigmoid_scale * (1 + intensity * random.uniform(-1, 1)),
            )), 3)

        if random.random() < 0.3:
            new.gamma = round(max(0.1, min(
                5.0,
                new.gamma * (1 + intensity * random.uniform(-1, 1)),
            )), 3)

        if random.random() < 0.3:
            new.beta = round(max(0.0, min(
                1.0,
                new.beta + intensity * random.uniform(-0.25, 0.25),
            )), 3)
        
        return new


# ═══════════════════════════════════════════════════════════════════════════════
# V2 風控基因（擴展）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RiskGenesV2:
    """V2 風控基因 — 在原有基礎上加入庫存橋概念"""
    stop_loss_pct: float = -0.05
    take_profit_pct: float = 0.08
    position_pct: float = 0.15
    max_hold_bars: int = 72
    trailing_stop: bool = False
    trailing_stop_pct: Optional[float] = None
    profit_targets: Optional[List[Dict[str, float]]] = None
    
    # V2 新增：庫存橋參數
    # DeadHold 底倉比例（只進不出，宏觀定投累積）
    dead_hold_ratio: float = 0.30
    
    # FloatHold 浮動倉比例（可賣出，微觀狙擊）
    float_hold_ratio: float = 0.70
    
    # 加速度解封閾值：當 ka 超過此值時，DeadHold 可轉為 FloatHold
    unlock_ka_threshold: float = 0.60

    @classmethod
    def random_bridge(cls, base: "RiskGenesV2") -> "RiskGenesV2":
        dead_ratio = round(random.uniform(0.10, 0.60), 3)
        base.dead_hold_ratio = dead_ratio
        base.float_hold_ratio = round(1.0 - dead_ratio, 3)
        base.unlock_ka_threshold = round(random.uniform(0.01, 0.30), 4)
        return base

    def mutate_bridge(self, intensity: float = 0.3) -> "RiskGenesV2":
        new = RiskGenesV2.from_dict(self.to_dict())
        if random.random() < 0.4:
            dead_ratio = max(0.0, min(
                1.0,
                new.dead_hold_ratio + intensity * random.uniform(-0.25, 0.25),
            ))
            new.dead_hold_ratio = round(dead_ratio, 3)
            new.float_hold_ratio = round(1.0 - dead_ratio, 3)
        if random.random() < 0.4:
            new.unlock_ka_threshold = round(max(0.0, min(
                1.0,
                new.unlock_ka_threshold
                + intensity * random.uniform(-0.20, 0.20),
            )), 4)
        return new
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "position_pct": self.position_pct,
            "max_hold_bars": self.max_hold_bars,
            "trailing_stop": self.trailing_stop,
            "trailing_stop_pct": self.trailing_stop_pct,
            "dead_hold_ratio": self.dead_hold_ratio,
            "float_hold_ratio": self.float_hold_ratio,
            "unlock_ka_threshold": self.unlock_ka_threshold,
        }
        if self.profit_targets:
            d["profit_targets"] = self.profit_targets
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RiskGenesV2":
        return cls(
            stop_loss_pct=d.get("stop_loss_pct", -0.05),
            take_profit_pct=d.get("take_profit_pct", 0.08),
            position_pct=d.get("position_pct", 0.15),
            max_hold_bars=d.get("max_hold_bars", 72),
            trailing_stop=d.get("trailing_stop", False),
            trailing_stop_pct=d.get("trailing_stop_pct"),
            profit_targets=d.get("profit_targets"),
            dead_hold_ratio=d.get("dead_hold_ratio", 0.30),
            float_hold_ratio=d.get("float_hold_ratio", 0.70),
            unlock_ka_threshold=d.get("unlock_ka_threshold", 0.60),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# V2 完整策略基因體
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StrategyChromosomeV2:
    """
    V2 完整策略基因體
    
    結構：
    - 原有部分：entry_genes, exit_genes, entry/exit logic, trend/volume filter
    - V2 新增：macro_genes, micro_genes, risk_genes_v2
    """
    # === 必填 ===
    chromosome_id: str
    entry_genes: List[IndicatorGene]
    exit_genes: List[IndicatorGene]
    
    # === 可選（原有） ===
    entry_logic: str = "AND"
    entry_min_weight: float = 0.5
    exit_logic: str = "OR"
    exit_min_weight: float = 0.3
    trend_filter: Optional[IndicatorGene] = None
    volume_filter: Optional[IndicatorGene] = None
    
    # === V2 新增 ===
    macro_genes: MacroGenes = field(default_factory=MacroGenes)
    micro_genes: MicroGenes = field(default_factory=MicroGenes)
    risk_genes: RiskGenesV2 = field(default_factory=RiskGenesV2)
    
    # === 元數據 ===
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    fitness_score: Optional[float] = None
    fitness_details: Dict[str, Any] = field(default_factory=dict)
    paper_trades: int = 0
    paper_pnl: float = 0.0
    
    # === V2 元數據 ===
    epoch_id: str = "epoch_0"
    symbol: str = "default"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chromosome_id": self.chromosome_id,
            "entry_genes": [g.to_dict() for g in self.entry_genes],
            "entry_logic": self.entry_logic,
            "entry_min_weight": self.entry_min_weight,
            "exit_genes": [g.to_dict() for g in self.exit_genes],
            "exit_logic": self.exit_logic,
            "exit_min_weight": self.exit_min_weight,
            "trend_filter": self.trend_filter.to_dict() if self.trend_filter else None,
            "volume_filter": self.volume_filter.to_dict() if self.volume_filter else None,
            "macro_genes": self.macro_genes.to_dict(),
            "micro_genes": self.micro_genes.to_dict(),
            "risk_genes": self.risk_genes.to_dict(),
            "generation": self.generation,
            "parent_ids": self.parent_ids,
            "created_at": self.created_at,
            "fitness_score": self.fitness_score,
            "fitness_details": self.fitness_details,
            "paper_trades": self.paper_trades,
            "paper_pnl": self.paper_pnl,
            "epoch_id": self.epoch_id,
            "symbol": self.symbol,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategyChromosomeV2":
        return cls(
            chromosome_id=d["chromosome_id"],
            entry_genes=[IndicatorGene.from_dict(g) for g in d.get("entry_genes", [])],
            entry_logic=d.get("entry_logic", "AND"),
            entry_min_weight=d.get("entry_min_weight", 0.5),
            exit_genes=[IndicatorGene.from_dict(g) for g in d.get("exit_genes", [])],
            exit_logic=d.get("exit_logic", "OR"),
            exit_min_weight=d.get("exit_min_weight", 0.3),
            trend_filter=IndicatorGene.from_dict(d["trend_filter"]) if d.get("trend_filter") else None,
            volume_filter=IndicatorGene.from_dict(d["volume_filter"]) if d.get("volume_filter") else None,
            macro_genes=MacroGenes.from_dict(d.get("macro_genes", {})),
            micro_genes=MicroGenes.from_dict(d.get("micro_genes", {})),
            risk_genes=RiskGenesV2.from_dict(d.get("risk_genes", {})),
            generation=d.get("generation", 0),
            parent_ids=d.get("parent_ids", []),
            created_at=d.get("created_at", datetime.now().isoformat()),
            fitness_score=d.get("fitness_score"),
            fitness_details=d.get("fitness_details", {}),
            paper_trades=d.get("paper_trades", 0),
            paper_pnl=d.get("paper_pnl", 0.0),
            epoch_id=d.get("epoch_id", "epoch_0"),
            symbol=d.get("symbol", "default"),
        )
    
    def summary(self) -> str:
        """簡短文字描述"""
        entry_names = " + ".join([g.name for g in self.entry_genes])
        exit_names = " + ".join([g.name for g in self.exit_genes])
        
        fit = f"fit={self.fitness_score:.3f}" if self.fitness_score else "fit=??"
        
        return (
            f"[{self.chromosome_id[:8]}] G{self.generation} | "
            f"Entry({self.entry_logic}): {entry_names} | "
            f"Exit({self.exit_logic}): {exit_names} | "
            f"Macro: DCA={self.macro_genes.max_dca_months}mo β={self.macro_genes.beta_threshold:.1%} | "
            f"Micro: kp={self.micro_genes.kp:.2f} kv={self.micro_genes.kv:.2f} ka={self.micro_genes.ka:.2f} | "
            f"Risk: SL={self.risk_genes.stop_loss_pct:.1%} TP={self.risk_genes.take_profit_pct:.1%} | "
            f"{fit}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# V2 染色體生成器
# ═══════════════════════════════════════════════════════════════════════════════

def random_chromosome_v2(
    generation: int = 0,
    min_entry_genes: int = 1,
    max_entry_genes: int = 4,
    min_exit_genes: int = 1,
    max_exit_genes: int = 3,
    with_filters: bool = True,
) -> StrategyChromosomeV2:
    """隨機生成 V2 策略染色體"""
    from .chromosome import random_chromosome as old_random
    
    # 先生成舊版骨架
    old_chrom = old_random(
        generation=generation,
        min_entry_genes=min_entry_genes,
        max_entry_genes=max_entry_genes,
        min_exit_genes=min_exit_genes,
        max_exit_genes=max_exit_genes,
        with_filters=with_filters,
    )
    
    # 包裝為 V2
    return StrategyChromosomeV2(
        chromosome_id=old_chrom.chromosome_id,
        entry_genes=old_chrom.entry_genes,
        entry_logic=old_chrom.entry_logic,
        entry_min_weight=old_chrom.entry_min_weight,
        exit_genes=old_chrom.exit_genes,
        exit_logic=old_chrom.exit_logic,
        exit_min_weight=old_chrom.exit_min_weight,
        trend_filter=old_chrom.trend_filter,
        volume_filter=old_chrom.volume_filter,
        macro_genes=MacroGenes.random(),
        micro_genes=MicroGenes.random(),
        risk_genes=RiskGenesV2.random_bridge(RiskGenesV2(
            stop_loss_pct=old_chrom.risk_genes.stop_loss_pct,
            take_profit_pct=old_chrom.risk_genes.take_profit_pct,
            position_pct=old_chrom.risk_genes.position_pct,
            max_hold_bars=old_chrom.risk_genes.max_hold_bars,
            trailing_stop=old_chrom.risk_genes.trailing_stop,
            trailing_stop_pct=old_chrom.risk_genes.trailing_stop_pct,
            profit_targets=old_chrom.risk_genes.profit_targets,
        )),
        generation=generation,
    )


def mutate_chromosome_v2(
    chrom: StrategyChromosomeV2,
    generation: int,
    mutation_rate: float = 0.3,
    intensity: float = 0.3,
) -> StrategyChromosomeV2:
    """V2 突變：包含宏觀/微觀基因突變"""
    from .chromosome import mutate_chromosome as old_mutate
    
    # 先複製舊版部分
    old_chrom = old_mutate(chrom, generation, mutation_rate, intensity)
    
    # 突變宏觀/微觀基因
    new_macro = chrom.macro_genes.mutate(intensity) if random.random() < mutation_rate else chrom.macro_genes
    new_micro = chrom.micro_genes.mutate(intensity) if random.random() < mutation_rate else chrom.micro_genes
    new_risk = RiskGenesV2.from_dict(chrom.risk_genes.to_dict())
    old_risk = old_chrom.risk_genes
    new_risk.stop_loss_pct = old_risk.stop_loss_pct
    new_risk.take_profit_pct = old_risk.take_profit_pct
    new_risk.position_pct = old_risk.position_pct
    new_risk.max_hold_bars = old_risk.max_hold_bars
    new_risk.trailing_stop = old_risk.trailing_stop
    new_risk.trailing_stop_pct = old_risk.trailing_stop_pct
    new_risk.profit_targets = old_risk.profit_targets
    if random.random() < mutation_rate:
        new_risk = new_risk.mutate_bridge(intensity)
    
    return StrategyChromosomeV2(
        chromosome_id=old_chrom.chromosome_id,
        entry_genes=old_chrom.entry_genes,
        entry_logic=old_chrom.entry_logic,
        entry_min_weight=old_chrom.entry_min_weight,
        exit_genes=old_chrom.exit_genes,
        exit_logic=old_chrom.exit_logic,
        exit_min_weight=old_chrom.exit_min_weight,
        trend_filter=old_chrom.trend_filter,
        volume_filter=old_chrom.volume_filter,
        macro_genes=new_macro,
        micro_genes=new_micro,
        risk_genes=new_risk,
        generation=generation,
        parent_ids=old_chrom.parent_ids,
    )


def crossover_chromosomes_v2(
    parent1: StrategyChromosomeV2,
    parent2: StrategyChromosomeV2,
    generation: int,
) -> StrategyChromosomeV2:
    """
    V2 正交交叉（Orthogonal Crossover）
    
    語義塊級正交：
    - 感知段（kp, kv）：從父 A
    - 開火段（ka, MinTradeThreshold）：從父 B
    - 宏觀段（Macro）：從較好者
    """
    from .chromosome import crossover_chromosomes as old_crossover
    
    # 舊版部分交叉
    old_child = old_crossover(parent1, parent2, generation)
    
    # V2 部分正交交叉
    p1_better = (parent1.fitness_score or 0) > (parent2.fitness_score or 0)
    
    # 宏觀基因：從較好者繼承
    if p1_better:
        macro_child = MacroGenes.from_dict(parent1.macro_genes.to_dict())
    else:
        macro_child = MacroGenes.from_dict(parent2.macro_genes.to_dict())
    
    # 微觀基因正交：
    # 感知段 (kp, kv) 從一個父親
    # 開火段 (ka, threshold) 從另一個
    if random.random() < 0.5:
        # 父1 的感知 + 父2 的開火
        micro_child = MicroGenes(
            kp=parent1.micro_genes.kp,
            kv=parent1.micro_genes.kv,
            ka=parent2.micro_genes.ka,
            min_trade_threshold=parent2.micro_genes.min_trade_threshold,
            micro_reserve_rate=(parent1.micro_genes.micro_reserve_rate + parent2.micro_genes.micro_reserve_rate) / 2,
            sigmoid_scale=(parent1.micro_genes.sigmoid_scale + parent2.micro_genes.sigmoid_scale) / 2,
            gamma=(parent1.micro_genes.gamma + parent2.micro_genes.gamma) / 2,
            beta=(parent1.micro_genes.beta + parent2.micro_genes.beta) / 2,
        )
    else:
        # 父2 的感知 + 父1 的開火
        micro_child = MicroGenes(
            kp=parent2.micro_genes.kp,
            kv=parent2.micro_genes.kv,
            ka=parent1.micro_genes.ka,
            min_trade_threshold=parent1.micro_genes.min_trade_threshold,
            micro_reserve_rate=(parent1.micro_genes.micro_reserve_rate + parent2.micro_genes.micro_reserve_rate) / 2,
            sigmoid_scale=(parent1.micro_genes.sigmoid_scale + parent2.micro_genes.sigmoid_scale) / 2,
            gamma=(parent1.micro_genes.gamma + parent2.micro_genes.gamma) / 2,
            beta=(parent1.micro_genes.beta + parent2.micro_genes.beta) / 2,
        )
    
    # 正規化權重
    total = micro_child.kp + micro_child.kv + micro_child.ka
    micro_child.kp = round(micro_child.kp / total, 3)
    micro_child.kv = round(micro_child.kv / total, 3)
    micro_child.ka = round(micro_child.ka / total, 3)

    base_risk = RiskGenesV2.from_dict(old_child.risk_genes.to_dict())
    base_risk.dead_hold_ratio = round(
        (parent1.risk_genes.dead_hold_ratio + parent2.risk_genes.dead_hold_ratio) / 2,
        3,
    )
    base_risk.float_hold_ratio = round(1.0 - base_risk.dead_hold_ratio, 3)
    base_risk.unlock_ka_threshold = round(
        (
            parent1.risk_genes.unlock_ka_threshold
            + parent2.risk_genes.unlock_ka_threshold
        ) / 2,
        4,
    )
    
    return StrategyChromosomeV2(
        chromosome_id=old_child.chromosome_id,
        entry_genes=old_child.entry_genes,
        entry_logic=old_child.entry_logic,
        entry_min_weight=old_child.entry_min_weight,
        exit_genes=old_child.exit_genes,
        exit_logic=old_child.exit_logic,
        exit_min_weight=old_child.exit_min_weight,
        trend_filter=old_child.trend_filter,
        volume_filter=old_child.volume_filter,
        macro_genes=macro_child,
        micro_genes=micro_child,
        risk_genes=base_risk,
        generation=generation,
        parent_ids=old_child.parent_ids,
    )


def validate_chromosome_v2(chrom: StrategyChromosomeV2) -> bool:
    """驗證 V2 染色體合法性"""
    from .chromosome import validate_chromosome as old_validate
    
    # 先驗證舊版部分
    # 構建一個兼容的舊版染色體做驗證
    from .chromosome import StrategyChromosome, RiskGenes
    compat = StrategyChromosome(
        chromosome_id=chrom.chromosome_id,
        entry_genes=chrom.entry_genes,
        exit_genes=chrom.exit_genes,
        risk_genes=RiskGenes(
            stop_loss_pct=chrom.risk_genes.stop_loss_pct,
            take_profit_pct=chrom.risk_genes.take_profit_pct,
            position_pct=chrom.risk_genes.position_pct,
            max_hold_bars=chrom.risk_genes.max_hold_bars,
        ),
    )
    if not old_validate(compat):
        return False
    
    # V2 額外驗證
    # 微觀權重和應為 1
    weight_sum = chrom.micro_genes.kp + chrom.micro_genes.kv + chrom.micro_genes.ka
    if abs(weight_sum - 1.0) > 0.05:
        return False
    
    # 倉位比例合理
    bridge_sum = chrom.risk_genes.dead_hold_ratio + chrom.risk_genes.float_hold_ratio
    if abs(bridge_sum - 1.0) > 1e-6:
        return False
    
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容性轉換
# ═══════════════════════════════════════════════════════════════════════════════

def v1_to_v2(chrom_v1: Any) -> StrategyChromosomeV2:
    """將 V1 染色體轉換為 V2（加入默認宏觀/微觀基因）"""
    return StrategyChromosomeV2(
        chromosome_id=chrom_v1.chromosome_id,
        entry_genes=chrom_v1.entry_genes,
        entry_logic=getattr(chrom_v1, "entry_logic", "AND"),
        entry_min_weight=getattr(chrom_v1, "entry_min_weight", 0.5),
        exit_genes=chrom_v1.exit_genes,
        exit_logic=getattr(chrom_v1, "exit_logic", "OR"),
        exit_min_weight=getattr(chrom_v1, "exit_min_weight", 0.3),
        trend_filter=getattr(chrom_v1, "trend_filter", None),
        volume_filter=getattr(chrom_v1, "volume_filter", None),
        macro_genes=MacroGenes(),  # 默認值
        micro_genes=MicroGenes(),  # 默認值
        risk_genes=RiskGenesV2(
            stop_loss_pct=chrom_v1.risk_genes.stop_loss_pct,
            take_profit_pct=chrom_v1.risk_genes.take_profit_pct,
            position_pct=chrom_v1.risk_genes.position_pct,
            max_hold_bars=chrom_v1.risk_genes.max_hold_bars,
            trailing_stop=getattr(chrom_v1.risk_genes, "trailing_stop", False),
            trailing_stop_pct=getattr(chrom_v1.risk_genes, "trailing_stop_pct", None),
            profit_targets=getattr(chrom_v1.risk_genes, "profit_targets", None),
        ),
        generation=getattr(chrom_v1, "generation", 0),
        parent_ids=getattr(chrom_v1, "parent_ids", []),
        created_at=getattr(chrom_v1, "created_at", datetime.now().isoformat()),
        fitness_score=getattr(chrom_v1, "fitness_score", None),
        fitness_details=getattr(chrom_v1, "fitness_details", {}),
        paper_trades=getattr(chrom_v1, "paper_trades", 0),
        paper_pnl=getattr(chrom_v1, "paper_pnl", 0.0),
    )


if __name__ == "__main__":
    print("=== Chromosome V2 Test ===")
    
    chrom = random_chromosome_v2(generation=0)
    print(f"隨機生成: {chrom.summary()}")
    
    print(f"\n宏觀基因: {chrom.macro_genes.to_dict()}")
    print(f"微觀基因: {chrom.micro_genes.to_dict()}")
    print(f"風控基因: {chrom.risk_genes.to_dict()}")
    
    # 測試突變
    mutated = mutate_chromosome_v2(chrom, generation=1, mutation_rate=0.5, intensity=0.3)
    print(f"\n突變後微觀: {mutated.micro_genes.to_dict()}")
    
    # 測試交叉
    chrom2 = random_chromosome_v2(generation=0)
    chrom2.fitness_score = 0.9
    chrom.fitness_score = 0.6
    crossed = crossover_chromosomes_v2(chrom, chrom2, generation=1)
    print(f"\n交叉後: {crossed.summary()}")
    
    # 測試驗證
    print(f"\n驗證: {validate_chromosome_v2(chrom)}")
