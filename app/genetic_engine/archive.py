#!/usr/bin/env python3
"""
Strategy Archive / 策略檔案館

Challenger / Champion / Retired 三態系統：
- Challenger：Epoch 結束時的最優個體，不會自動覆蓋冠軍
- Champion：當前冠軍，實盤加載的唯一參數包
- Retired：被 Promote 淘汰的原冠軍

Reference: 《核心準則》5.5 節

Author: second_bot
Date: 2026-05-28
"""

import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


@dataclass
class ArchiveRecord:
    """檔案記錄"""
    chromosome_id: str
    status: str  # "champion" | "challenger" | "retired"
    epoch_id: str
    generation: int
    fitness_score: float
    fitness_details: Dict[str, Any]
    chromosome_data: Dict[str, Any]  # 完整基因體序列化
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    promoted_at: Optional[str] = None  # 何時被 promote
    retired_at: Optional[str] = None
    paper_trades: int = 0
    paper_pnl: float = 0.0
    retire_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chromosome_id": self.chromosome_id,
            "status": self.status,
            "epoch_id": self.epoch_id,
            "generation": self.generation,
            "fitness_score": self.fitness_score,
            "fitness_details": self.fitness_details,
            "chromosome_data": self.chromosome_data,
            "created_at": self.created_at,
            "promoted_at": self.promoted_at,
            "retired_at": self.retired_at,
            "paper_trades": self.paper_trades,
            "paper_pnl": self.paper_pnl,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArchiveRecord":
        return cls(
            chromosome_id=d["chromosome_id"],
            status=d["status"],
            epoch_id=d["epoch_id"],
            generation=d["generation"],
            fitness_score=d["fitness_score"],
            fitness_details=d.get("fitness_details", {}),
            chromosome_data=d["chromosome_data"],
            created_at=d.get("created_at", datetime.now().isoformat()),
            promoted_at=d.get("promoted_at"),
            retired_at=d.get("retired_at"),
            paper_trades=d.get("paper_trades", 0),
            paper_pnl=d.get("paper_pnl", 0.0),
        )


class StrategyArchive:
    """
    策略檔案館
    
    管理 Champion / Challenger / Retired 的生命週期。
    實盤只加載 Champion 的參數包。
    """
    
    def __init__(self, archive_dir: str = "data/genetic_archive"):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        self.champions: Dict[str, ArchiveRecord] = {}  # symbol -> champion
        self.challengers: Dict[str, ArchiveRecord] = {}  # symbol -> challenger
        self.retired: List[ArchiveRecord] = []
        
        self._load_all()
    
    def _load_all(self):
        """載入所有檔案"""
        # 載入 Champions
        champion_file = self.archive_dir / "champions.json"
        if champion_file.exists():
            with open(champion_file) as f:
                data = json.load(f)
                for symbol, rec in data.items():
                    self.champions[symbol] = ArchiveRecord.from_dict(rec)
        
        # 載入 Challengers
        challenger_file = self.archive_dir / "challengers.json"
        if challenger_file.exists():
            with open(challenger_file) as f:
                data = json.load(f)
                for symbol, rec in data.items():
                    self.challengers[symbol] = ArchiveRecord.from_dict(rec)
        
        # 載入 Retired
        retired_file = self.archive_dir / "retired.json"
        if retired_file.exists():
            with open(retired_file) as f:
                data = json.load(f)
                self.retired = [ArchiveRecord.from_dict(r) for r in data]
    
    def _save_all(self):
        """保存所有檔案"""
        with open(self.archive_dir / "champions.json", "w") as f:
            json.dump({k: v.to_dict() for k, v in self.champions.items()}, f, indent=2)
        
        with open(self.archive_dir / "challengers.json", "w") as f:
            json.dump({k: v.to_dict() for k, v in self.challengers.items()}, f, indent=2)
        
        with open(self.archive_dir / "retired.json", "w") as f:
            json.dump([r.to_dict() for r in self.retired], f, indent=2)
    
    def add_challenger(self, record: ArchiveRecord, symbol: str = "default"):
        """
        添加挑戰者
        
        Epoch 結束時，最優個體作為挑戰者寫入，不會自動覆蓋冠軍。
        """
        record.status = "challenger"
        self.challengers[symbol] = record
        
        # 同時保存為獨立檔案
        file_path = self.archive_dir / f"challenger_{record.epoch_id}_{record.chromosome_id[:8]}.json"
        with open(file_path, "w") as f:
            json.dump(record.to_dict(), f, indent=2)
        
        self._save_all()
    
    def promote_challenger(self, chromosome_id: str, symbol: str = "default") -> bool:
        """
        Promote 挑戰者為冠軍
        
        用戶在前端對 challenger 執行 Promote 後：
        - 原冠軍標記為退役
        - 挑戰者成為新冠軍
        - 刷新實盤冠軍緩存
        """
        challenger = self.challengers.get(symbol)
        if not challenger or challenger.chromosome_id != chromosome_id:
            # 嘗試從檔案中查找
            found = None
            for f in self.archive_dir.glob("challenger_*.json"):
                with open(f) as fh:
                    data = json.load(fh)
                    if data["chromosome_id"] == chromosome_id:
                        found = ArchiveRecord.from_dict(data)
                        break
            if not found:
                return False
            challenger = found
        
        # 原冠軍退役
        if symbol in self.champions:
            old_champion = self.champions[symbol]
            old_champion.status = "retired"
            old_champion.retired_at = datetime.now().isoformat()
            self.retired.append(old_champion)
        
        # 挑戰者升為冠軍
        challenger.status = "champion"
        challenger.promoted_at = datetime.now().isoformat()
        self.champions[symbol] = challenger
        
        # 從 challengers 中移除（或保留記錄）
        if symbol in self.challengers:
            del self.challengers[symbol]
        
        self._save_all()
        
        print(f"🏆 Champion promoted: {chromosome_id[:8]} for {symbol}")
        print(f"   Old champion retired. Live pool will reload on next cycle.")
        return True
    
    def get_champion(self, symbol: str = "default") -> Optional[ArchiveRecord]:
        """獲取當前冠軍"""
        return self.champions.get(symbol)
    
    def get_challenger(self, symbol: str = "default") -> Optional[ArchiveRecord]:
        """獲取當前挑戰者"""
        return self.challengers.get(symbol)
    
    def get_all_champions(self) -> Dict[str, ArchiveRecord]:
        """獲取所有冠軍"""
        return dict(self.champions)
    
    def get_elite_seeds(self, symbol: str = "default", top_n: int = 3) -> List[Dict[str, Any]]:
        """
        獲取精英種子（用於 1-4-5 初始化中的 10% 舊神火種）
        
        查詢優先級：
        1. 當前冠軍
        2. 最近挑戰者
        3. 已退役但表現優秀的記錄
        """
        seeds = []
        
        # 冠軍
        champ = self.get_champion(symbol)
        if champ:
            seeds.append(champ.chromosome_data)
        
        # 挑戰者
        chall = self.get_challenger(symbol)
        if chall and len(seeds) < top_n:
            seeds.append(chall.chromosome_data)
        
        # 從退役中按 fitness 排序取前幾個
        retired_sorted = sorted(
            [r for r in self.retired if r.fitness_score is not None],
            key=lambda r: r.fitness_score,
            reverse=True,
        )
        for r in retired_sorted:
            if len(seeds) >= top_n:
                break
            seeds.append(r.chromosome_data)
        
        return seeds
    
    def update_paper_results(self, chromosome_id: str, trades: int, pnl: float):
        """更新紙上交易結果到檔案記錄"""
        # 更新冠軍
        for symbol, rec in self.champions.items():
            if rec.chromosome_id == chromosome_id:
                rec.paper_trades = trades
                rec.paper_pnl = pnl
                self._save_all()
                return
        
        # 更新挑戰者
        for symbol, rec in self.challengers.items():
            if rec.chromosome_id == chromosome_id:
                rec.paper_trades = trades
                rec.paper_pnl = pnl
                self._save_all()
                return
    
    def retire_challenger(self, chromosome_id: str, reason: str = "manual") -> bool:
        """將挑戰者直接淘汰（paper trade 不過關）"""
        # 先找到這個 challenger
        target = None
        target_symbol = None
        for symbol, record in list(self.challengers.items()):
            if record.chromosome_id == chromosome_id:
                target = record
                target_symbol = symbol
                break

        if target is None:
            # 嘗試從檔案中查找
            for f in self.archive_dir.glob("challenger_*.json"):
                with open(f) as fh:
                    data = json.load(fh)
                    if data["chromosome_id"] == chromosome_id:
                        target = ArchiveRecord.from_dict(data)
                        break

        if target is None:
            return False

        target.status = "retired"
        target.retired_at = datetime.now().isoformat()
        target.retire_reason = reason
        self.retired.append(target)

        if target_symbol and target_symbol in self.challengers:
            del self.challengers[target_symbol]

        self._save_all()
        print(f"🗑️  Retired challenger: {chromosome_id[:8]} (reason: {reason})")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """獲取檔案館統計"""
        return {
            "champions": len(self.champions),
            "challengers": len(self.challengers),
            "retired": len(self.retired),
            "champion_list": [
                {"symbol": s, "id": r.chromosome_id[:8], "fitness": r.fitness_score}
                for s, r in self.champions.items()
            ],
            "retired_count": len(self.retired),
        }


if __name__ == "__main__":
    print("=== Strategy Archive Test ===")
    
    archive = StrategyArchive("data/test_archive")
    
    # 模擬添加挑戰者
    dummy_chrom = {"chromosome_id": "test_123", "entry_genes": [], "exit_genes": []}
    record = ArchiveRecord(
        chromosome_id="test_123",
        status="challenger",
        epoch_id="epoch_001",
        generation=50,
        fitness_score=0.85,
        fitness_details={"alpha": 0.12},
        chromosome_data=dummy_chrom,
    )
    archive.add_challenger(record, "BTCUSDT")
    
    # 查看
    print(f"Challenger added: {archive.get_challenger('BTCUSDT').chromosome_id}")
    print(f"Stats: {archive.get_stats()}")
    
    # Promote
    archive.promote_challenger("test_123", "BTCUSDT")
    print(f"After promote: {archive.get_champion('BTCUSDT').status}")
    print(f"Stats: {archive.get_stats()}")
    
    # 獲取精英種子
    seeds = archive.get_elite_seeds("BTCUSDT", top_n=2)
    print(f"Elite seeds: {len(seeds)}")
