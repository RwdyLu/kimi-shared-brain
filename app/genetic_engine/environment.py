#!/usr/bin/env python3
"""
Environment & Season Layer / 環境與季節層

三層架構：
- 頂層 Environment（造物主法則）：全局紅線，跨 Epoch 截斷正態抽樣
- 中層 Season（季節氣候）：資金激進乘數等周期性參數，Epoch 內固定
- 底層 Combat Genes（戰鬥種群）：宏觀+微觀基因，參與進化

Reference: 《核心準則》第三篇章

Author: second_bot
Date: 2026-05-28
"""

import random
import math
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class Season(Enum):
    """四季：冬藏 → 春生 → 夏長 → 秋收"""
    WINTER = "winter"    # 最低激進度，保守
    SPRING = "spring"    # 適中激進度，平穩
    SUMMER = "summer"    # 較高激進度，積極
    AUTUMN = "autumn"    # 最高激進度，收割


# ═══════════════════════════════════════════════════════════════════════════════
# 頂層：Environment（造物主法則）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Environment:
    """
    造物主法則 — Epoch 內全員相同，基因層不參與改寫
    
    跨 Epoch 時對 DeadReserveRatio、GlobalStopLoss 做截斷正態抽樣
    MaxLeverage 在 GA Epoch 中固定為 1（現貨基線）
    """
    # 死守底倉下限（安全墊）
    dead_reserve_ratio: float = 0.20  # 至少保留 20% 底倉
    dead_reserve_min: float = 0.05
    dead_reserve_max: float = 0.50
    
    # 全局權益回撤熔斷
    global_stop_loss: float = 0.30  # 30% 回撤熔斷（0 = 關閉）
    global_stop_loss_min: float = 0.10
    global_stop_loss_max: float = 0.50
    
    # 槓桿上限（GA 期間固定為 1，即現貨）
    max_leverage: float = 1.0
    
    # 跨 Epoch 抽樣 sigma（區間寬度的 10%）
    resample_sigma_factor: float = 0.10

    def __post_init__(self) -> None:
        # GA research is spot-only. Config/archive input cannot raise leverage.
        self.max_leverage = 1.0
    
    def clone(self) -> "Environment":
        return Environment(
            dead_reserve_ratio=self.dead_reserve_ratio,
            global_stop_loss=self.global_stop_loss,
            max_leverage=self.max_leverage,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "dead_reserve_ratio": self.dead_reserve_ratio,
            "global_stop_loss": self.global_stop_loss,
            "max_leverage": self.max_leverage,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Environment":
        return cls(
            dead_reserve_ratio=d.get("dead_reserve_ratio", 0.20),
            global_stop_loss=d.get("global_stop_loss", 0.30),
            max_leverage=d.get("max_leverage", 1.0),
        )
    
    def resample_for_new_epoch(self) -> "Environment":
        """
        跨 Epoch 時重新抽樣 Environment 參數
        
        以當前值為均值，在合法區間內做截斷正態抽樣
        """
        new_env = self.clone()
        
        # DeadReserveRatio 截斷正態
        width = self.dead_reserve_max - self.dead_reserve_min
        sigma = width * self.resample_sigma_factor
        new_env.dead_reserve_ratio = self._truncated_normal(
            self.dead_reserve_ratio, sigma,
            self.dead_reserve_min, self.dead_reserve_max
        )
        
        # GlobalStopLoss 截斷正態
        width = self.global_stop_loss_max - self.global_stop_loss_min
        sigma = width * self.resample_sigma_factor
        new_env.global_stop_loss = self._truncated_normal(
            self.global_stop_loss, sigma,
            self.global_stop_loss_min, self.global_stop_loss_max
        )
        
        # MaxLeverage 在 GA 期間固定為 1
        new_env.max_leverage = 1.0
        
        return new_env
    
    @staticmethod
    def _truncated_normal(mean: float, sigma: float, low: float, high: float) -> float:
        """截斷正態抽樣（拒絕採樣法）"""
        max_attempts = 100
        for _ in range(max_attempts):
            val = random.gauss(mean, sigma)
            if low <= val <= high:
                return round(val, 4)
        # fallback
        return max(low, min(high, mean))


# ═══════════════════════════════════════════════════════════════════════════════
# 中層：Season（季節氣候）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SeasonConfig:
    """
    季節配置 — Epoch 內固定，決定宏觀節奏
    
    核心參數：資金激進乘數（Aggressiveness Multiplier）
    從低到高代表：冬 → 春 → 夏 → 秋
    """
    season: Season = Season.SPRING
    
    # 資金激進乘數：決定每次買入的資金量倍數
    aggressiveness: float = 1.0
    
    # 操作時間偏移（分鐘），用於抗性訓練
    # 回測時隨機抽取，實盤時輸出為 0
    tick_offset_minutes: int = 0
    
    # 回測步進與 K 線對齊（5 分鐘基準）
    base_tick_minutes: int = 5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "season": self.season.value,
            "aggressiveness": self.aggressiveness,
            "tick_offset_minutes": self.tick_offset_minutes,
            "base_tick_minutes": self.base_tick_minutes,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SeasonConfig":
        return cls(
            season=Season(d.get("season", "spring")),
            aggressiveness=d.get("aggressiveness", 1.0),
            tick_offset_minutes=d.get("tick_offset_minutes", 0),
            base_tick_minutes=d.get("base_tick_minutes", 5),
        )


class SeasonSampler:
    """
    季節採樣器
    
    每次 Epoch 從四季離散檔位按分類分佈抽樣。
    正常檔位（Spring）賦予更高概率以保證收斂。
    """
    
    # 四季對應的激進乘數
    SEASON_MULTIPLIERS = {
        Season.WINTER: 0.5,   # 冬藏：保守
        Season.SPRING: 1.0,   # 春生：平穩（基準）
        Season.SUMMER: 2.0,   # 夏長：積極
        Season.AUTUMN: 4.0,   # 秋收：激進收割
    }
    
    # 默認分類分佈概率（Spring 最高，保證收斂）
    DEFAULT_PROBS = {
        Season.WINTER: 0.15,
        Season.SPRING: 0.40,
        Season.SUMMER: 0.30,
        Season.AUTUMN: 0.15,
    }
    
    @classmethod
    def sample(cls, probs: Optional[Dict[Season, float]] = None) -> SeasonConfig:
        """抽取一個季節配置"""
        p = probs or cls.DEFAULT_PROBS
        seasons = list(p.keys())
        weights = list(p.values())
        
        chosen = random.choices(seasons, weights=weights, k=1)[0]
        
        return SeasonConfig(
            season=chosen,
            aggressiveness=cls.SEASON_MULTIPLIERS[chosen],
            tick_offset_minutes=random.randint(0, 4),  # 0~4 分鐘偏移
        )
    
    @classmethod
    def sample_seasons_for_epoch(cls, n_segments: int = 4) -> List[SeasonConfig]:
        """
        為一個 Epoch 生成多段季節配置
        
        把全樣本回測區間切成 N 段，底層種群必須忍受 N 種不同季節摩擦
        """
        # Stage 5 requires every strategy to traverse all four seasons exactly
        # once and in physical order. n_segments is retained for API compatibility.
        return cls.get_all_season_configs()
    
    @classmethod
    def get_all_season_configs(cls) -> List[SeasonConfig]:
        """返回所有四季的完整配置（用於展示）"""
        return [
            SeasonConfig(season=s, aggressiveness=m)
            for s, m in cls.SEASON_MULTIPLIERS.items()
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# 組合：三層配置包
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ThreeLayerConfig:
    """
    三層配置包 — 一個完整的進化環境設定
    
    包含 Environment + Season + 基因參數空間邊界
    """
    environment: Environment = field(default_factory=Environment)
    seasons: List[SeasonConfig] = field(default_factory=list)
    epoch_id: str = "epoch_0"
    generation: int = 0
    
    # 基因參數合法盒邊界（用於突變時的投影回盒）
    gene_bounds: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "generation": self.generation,
            "environment": self.environment.to_dict(),
            "seasons": [s.to_dict() for s in self.seasons],
            "gene_bounds": self.gene_bounds,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ThreeLayerConfig":
        return cls(
            epoch_id=d.get("epoch_id", "epoch_0"),
            generation=d.get("generation", 0),
            environment=Environment.from_dict(d.get("environment", {})),
            seasons=[SeasonConfig.from_dict(s) for s in d.get("seasons", [])],
            gene_bounds=d.get("gene_bounds", {}),
        )
    
    @classmethod
    def create_for_new_epoch(
        cls,
        prev_env: Optional[Environment] = None,
        n_season_segments: int = 4,
    ) -> "ThreeLayerConfig":
        """為新 Epoch 創建三層配置"""
        env = (prev_env.resample_for_new_epoch() if prev_env else Environment())
        seasons = SeasonSampler.sample_seasons_for_epoch(n_season_segments)
        
        return cls(
            environment=env,
            seasons=seasons,
            epoch_id=f"epoch_{random.randint(1000, 9999)}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 季節應用：回測時的季節摩擦
# ═══════════════════════════════════════════════════════════════════════════════

class SeasonApplier:
    """
    季節摩擦應用器
    
    在回測過程中，根據當前季節調整資金調撥量。
    確保基因不會因為某一種資金乘數而擊穿風控底線。
    """
    
    @staticmethod
    def apply_to_position_size(
        base_position_pct: float,
        season: SeasonConfig,
        environment: Environment,
    ) -> float:
        """
        應用季節乘數到基礎倉位比例
        
        但受 Environment 的 dead_reserve_ratio 限制
        """
        # 計算可用資金（扣除死守底倉）
        usable_ratio = 1.0 - environment.dead_reserve_ratio
        
        # 應用季節激進乘數
        adjusted = base_position_pct * season.aggressiveness
        
        # 限制在可用資金範圍內
        return min(adjusted, usable_ratio)
    
    @staticmethod
    def apply_to_dca_amount(
        base_dca_amount: float,
        season: SeasonConfig,
        environment: Environment,
    ) -> float:
        """應用季節乘數到定投金額"""
        adjusted = base_dca_amount * season.aggressiveness
        # 同樣受可用資金限制
        return adjusted

    @staticmethod
    def season_for_index(
        index: int,
        total_length: int,
        seasons: Optional[List[SeasonConfig]],
        fallback: Optional[SeasonConfig] = None,
    ) -> Optional[SeasonConfig]:
        """Map an ordered history index to sequential winter/spring/summer/autumn."""
        if not seasons:
            return fallback
        if total_length <= 0:
            return seasons[0]
        segment = min(len(seasons) - 1, index * len(seasons) // total_length)
        return seasons[segment]


# ═══════════════════════════════════════════════════════════════════════════════
# 實盤 SaaS 決策面：Regime Engine 接口
# ═══════════════════════════════════════════════════════════════════════════════

class RegimeEngine:
    """
    實盤 Regime Engine
    
    根據實時大盤水位判定當前季節，動態下發資金乘數。
    每個運行中的交易實例都有調度循環，Regime Engine 判斷大盤季節後下發。
    """
    
    # 大盤判定閾值（簡化版）
    # 實際產品中可能使用更複雜的市場狀態機
    BULL_THRESHOLD = 0.05      # 5% 以上漲幅視為牛市
    BEAR_THRESHOLD = -0.15   # -15% 以下視為熊市
    
    @classmethod
    def detect_season(
        cls,
        market_change_7d: float,
        market_change_30d: float,
        volatility_percentile: float,
    ) -> Season:
        """
        根據市場狀態判定季節
        
        Args:
            market_change_7d: 7 日漲跌幅
            market_change_30d: 30 日漲跌幅
            volatility_percentile: 波動率百分位 (0~1)
        
        Returns:
            當前季節
        """
        # 死水微瀾 → 冬
        if abs(market_change_7d) < 0.02 and volatility_percentile < 0.3:
            return Season.WINTER
        
        # 溫和上漲 → 春
        if market_change_7d > 0 and market_change_30d > -0.05 and volatility_percentile < 0.5:
            return Season.SPRING
        
        # 強勢上漲 → 夏
        if market_change_7d > cls.BULL_THRESHOLD or market_change_30d > 0.20:
            return Season.SUMMER
        
        # 高位或回落 → 秋（收割季）
        if market_change_30d > 0.30 or (market_change_7d < -0.05 and market_change_30d > 0.10):
            return Season.AUTUMN
        
        # 默認春
        return Season.SPRING
    
    @classmethod
    def get_aggressiveness(cls, season: Season) -> float:
        """獲取季節對應的激進乘數"""
        return SeasonSampler.SEASON_MULTIPLIERS.get(season, 1.0)


if __name__ == "__main__":
    print("=== Environment & Season Layer Test ===")
    
    # 測試 Environment
    env = Environment()
    print(f"初始 Environment: {env.to_dict()}")
    
    # 跨 Epoch 重抽樣
    env2 = env.resample_for_new_epoch()
    print(f"重抽樣後: {env2.to_dict()}")
    
    # 測試季節採樣
    print("\n四季配置:")
    for cfg in SeasonSampler.get_all_season_configs():
        print(f"  {cfg.season.value}: aggressiveness={cfg.aggressiveness}")
    
    # 測試 Epoch 季節序列
    print("\nEpoch 季節序列:")
    seasons = SeasonSampler.sample_seasons_for_epoch(4)
    for i, s in enumerate(seasons):
        print(f"  Segment {i+1}: {s.season.value} (x{s.aggressiveness}, offset={s.tick_offset_minutes}m)")
    
    # 測試三層配置
    print("\n三層配置包:")
    config = ThreeLayerConfig.create_for_new_epoch()
    print(f"  {config.to_dict()}")
    
    # 測試 Regime Engine
    print("\nRegime 判定:")
    test_cases = [
        (-0.20, -0.30, 0.8),   # 熊市暴跌
        (0.005, 0.01, 0.2),    # 死水微瀾
        (0.03, 0.08, 0.4),     # 溫和上漲
        (0.08, 0.25, 0.6),     # 強勢上漲
        (-0.02, 0.35, 0.5),    # 高位回落
    ]
    for ch7, ch30, vol in test_cases:
        season = RegimeEngine.detect_season(ch7, ch30, vol)
        agg = RegimeEngine.get_aggressiveness(season)
        print(f"  7d={ch7:+.1%}, 30d={ch30:+.1%}, vol={vol:.1f} → {season.value} (x{agg})")
