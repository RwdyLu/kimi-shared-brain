#!/usr/bin/env python3
"""
Strategy Archive / 策略檔案館

GA archive lifecycle:
- raw_candidate: Epoch best, not yet qualified
- seed_candidate: Stage 1/2 passed, can seed later research, cannot deploy
- rejected: failed staged eligibility
- qualified_challenger: Stage 3 passed, can enter validation
- validating: Shadow/Paper validation in progress
- pending_acceptance: Paper validation passed, waiting for manual Promote
- champion: manually promoted runtime strategy
- retired: old Champion or replaced strategy
"""

import json
from typing import Dict, List, Any, Optional, Iterable, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


RAW_CANDIDATE = "raw_candidate"
SEED_CANDIDATE = "seed_candidate"
REJECTED = "rejected"
QUALIFIED_CHALLENGER = "qualified_challenger"
VALIDATING = "validating"
PENDING_ACCEPTANCE = "pending_acceptance"
CHAMPION = "champion"
RETIRED = "retired"
LEGACY_CHALLENGER = "challenger"

ARCHIVE_STATUSES = {
    RAW_CANDIDATE,
    SEED_CANDIDATE,
    REJECTED,
    QUALIFIED_CHALLENGER,
    VALIDATING,
    PENDING_ACCEPTANCE,
    CHAMPION,
    RETIRED,
    LEGACY_CHALLENGER,
}


@dataclass
class ArchiveRecord:
    """檔案記錄"""

    chromosome_id: str
    status: str
    epoch_id: str
    generation: int
    fitness_score: float
    fitness_details: Dict[str, Any]
    chromosome_data: Dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    promoted_at: Optional[str] = None
    retired_at: Optional[str] = None
    validation_started_at: Optional[str] = None
    pending_at: Optional[str] = None
    paper_trades: int = 0
    paper_pnl: float = 0.0
    paper_metrics: Dict[str, Any] = field(default_factory=dict)
    retired_reason: Optional[str] = None

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
            "validation_started_at": self.validation_started_at,
            "pending_at": self.pending_at,
            "paper_trades": self.paper_trades,
            "paper_pnl": self.paper_pnl,
            "paper_metrics": self.paper_metrics,
            "retired_reason": self.retired_reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArchiveRecord":
        status = d.get("status", LEGACY_CHALLENGER)
        if status not in ARCHIVE_STATUSES:
            status = LEGACY_CHALLENGER
        return cls(
            chromosome_id=d["chromosome_id"],
            status=status,
            epoch_id=d["epoch_id"],
            generation=d["generation"],
            fitness_score=d["fitness_score"],
            fitness_details=d.get("fitness_details", {}),
            chromosome_data=d["chromosome_data"],
            created_at=d.get("created_at", datetime.now().isoformat()),
            promoted_at=d.get("promoted_at"),
            retired_at=d.get("retired_at"),
            validation_started_at=d.get("validation_started_at"),
            pending_at=d.get("pending_at"),
            paper_trades=d.get("paper_trades", 0),
            paper_pnl=d.get("paper_pnl", 0.0),
            paper_metrics=d.get("paper_metrics", {}),
            retired_reason=d.get("retired_reason"),
        )


class StrategyArchive:
    """Manage GA candidate, validation, Champion, and Retired lifecycles."""

    def __init__(self, archive_dir: str = "data/genetic_archive"):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        self.raw_candidates: List[ArchiveRecord] = []
        self.seed_candidates: List[ArchiveRecord] = []
        self.rejected: List[ArchiveRecord] = []
        self.qualified_challengers: Dict[str, ArchiveRecord] = {}
        self.validating: Dict[str, ArchiveRecord] = {}
        self.pending_acceptance: Dict[str, ArchiveRecord] = {}
        self.champions: Dict[str, ArchiveRecord] = {}
        self.retired: List[ArchiveRecord] = []

        # Backward-compatible alias used by existing UI/services/tests.
        self.challengers = self.qualified_challengers

        self._load_all()

    def _load_json(self, filename: str, default: Any) -> Any:
        path = self.archive_dir / filename
        if not path.exists():
            return default
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _load_record_list(self, filename: str, status: Optional[str] = None) -> List[ArchiveRecord]:
        records = []
        for item in self._load_json(filename, []):
            record = ArchiveRecord.from_dict(item)
            if status:
                record.status = status
            records.append(record)
        return records

    def _load_record_dict(self, filename: str, status: Optional[str] = None) -> Dict[str, ArchiveRecord]:
        data = self._load_json(filename, {})
        records = {}
        for symbol, item in data.items():
            record = ArchiveRecord.from_dict(item)
            if status:
                record.status = status
            records[symbol] = record
        return records

    def _load_all(self) -> None:
        """載入所有檔案；old challengers.json is mapped to qualified_challenger."""
        self.raw_candidates = self._load_record_list("raw_candidates.json", RAW_CANDIDATE)
        self.seed_candidates = self._load_record_list("seed_candidates.json", SEED_CANDIDATE)
        self.rejected = self._load_record_list("rejected.json", REJECTED)

        self.qualified_challengers = self._load_record_dict(
            "qualified_challengers.json",
            QUALIFIED_CHALLENGER,
        )
        if not self.qualified_challengers:
            self.qualified_challengers = self._load_record_dict(
                "challengers.json",
                QUALIFIED_CHALLENGER,
            )
        self.challengers = self.qualified_challengers

        self.validating = self._load_record_dict("validating.json", VALIDATING)
        self.pending_acceptance = self._load_record_dict(
            "pending_acceptance.json",
            PENDING_ACCEPTANCE,
        )
        self.champions = self._load_record_dict("champions.json", CHAMPION)
        self.retired = self._load_record_list("retired.json", RETIRED)

    def _dump_json(self, filename: str, data: Any) -> None:
        with (self.archive_dir / filename).open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def _save_record_file(self, prefix: str, record: ArchiveRecord) -> None:
        path = self.archive_dir / f"{prefix}_{record.epoch_id}_{record.chromosome_id[:8]}.json"
        self._dump_json(path.name, record.to_dict())

    def _save_all(self) -> None:
        """保存所有檔案."""
        self._dump_json("raw_candidates.json", [r.to_dict() for r in self.raw_candidates])
        self._dump_json("seed_candidates.json", [r.to_dict() for r in self.seed_candidates])
        self._dump_json("rejected.json", [r.to_dict() for r in self.rejected])
        qualified = {k: v.to_dict() for k, v in self.qualified_challengers.items()}
        self._dump_json("qualified_challengers.json", qualified)
        # Legacy read compatibility for existing UI/services that still expect challengers.json.
        self._dump_json("challengers.json", qualified)
        self._dump_json("validating.json", {k: v.to_dict() for k, v in self.validating.items()})
        self._dump_json(
            "pending_acceptance.json",
            {k: v.to_dict() for k, v in self.pending_acceptance.items()},
        )
        self._dump_json("champions.json", {k: v.to_dict() for k, v in self.champions.items()})
        self._dump_json("retired.json", [r.to_dict() for r in self.retired])

    def _record_symbol(self, record: ArchiveRecord, symbol: str = "default") -> str:
        return (
            (record.fitness_details or {}).get("archive_symbol")
            or record.chromosome_data.get("symbol")
            or symbol
        )

    def _clone_for_status(self, record: ArchiveRecord, status: str) -> ArchiveRecord:
        data = record.to_dict()
        data["status"] = status
        return ArchiveRecord.from_dict(data)

    def _iter_mutable_records(self) -> Iterable[Tuple[str, Any, ArchiveRecord]]:
        for key, record in self.qualified_challengers.items():
            yield "qualified_challengers", key, record
        for key, record in self.validating.items():
            yield "validating", key, record
        for key, record in self.pending_acceptance.items():
            yield "pending_acceptance", key, record
        for key, record in self.champions.items():
            yield "champions", key, record
        for index, record in enumerate(self.raw_candidates):
            yield "raw_candidates", index, record
        for index, record in enumerate(self.seed_candidates):
            yield "seed_candidates", index, record
        for index, record in enumerate(self.rejected):
            yield "rejected", index, record
        for index, record in enumerate(self.retired):
            yield "retired", index, record

    def _pop_record(self, chromosome_id: str, status: Optional[str] = None) -> Optional[ArchiveRecord]:
        for container, key, record in list(self._iter_mutable_records()):
            if record.chromosome_id != chromosome_id:
                continue
            if status and record.status != status:
                continue
            if container in {
                "qualified_challengers",
                "validating",
                "pending_acceptance",
                "champions",
            }:
                return getattr(self, container).pop(key)
            return getattr(self, container).pop(key)
        return None

    def _find_record(self, chromosome_id: str, status: Optional[str] = None) -> Optional[ArchiveRecord]:
        for _, _, record in self._iter_mutable_records():
            if record.chromosome_id == chromosome_id and (status is None or record.status == status):
                return record
        return None

    def add_raw_candidate(self, record: ArchiveRecord, symbol: str = "default") -> ArchiveRecord:
        record.status = RAW_CANDIDATE
        record.fitness_details = dict(record.fitness_details or {})
        record.fitness_details.setdefault("archive_symbol", symbol)
        self.raw_candidates.append(record)
        self._save_record_file(RAW_CANDIDATE, record)
        self._save_all()
        return record

    def add_seed_candidate(self, record: ArchiveRecord, symbol: str = "default") -> ArchiveRecord:
        record.status = SEED_CANDIDATE
        record.fitness_details = dict(record.fitness_details or {})
        record.fitness_details.setdefault("archive_symbol", symbol)
        self.seed_candidates.append(record)
        self._save_record_file(SEED_CANDIDATE, record)
        self._save_all()
        return record

    def add_rejected(
        self,
        record: ArchiveRecord,
        symbol: str = "default",
        failed_rules: Optional[List[Dict[str, Any]]] = None,
        rejected_reason: Optional[str] = None,
    ) -> ArchiveRecord:
        record.status = REJECTED
        details = dict(record.fitness_details or {})
        details.setdefault("rejected_symbol", symbol)
        if failed_rules is not None:
            details["failed_rules"] = failed_rules
        if rejected_reason is not None:
            details["rejected_reason"] = rejected_reason
        record.fitness_details = details
        self.rejected.append(record)
        self._save_record_file(REJECTED, record)
        self._save_all()
        return record

    def add_qualified_challenger(
        self,
        record: ArchiveRecord,
        symbol: str = "default",
    ) -> ArchiveRecord:
        eligibility = (record.fitness_details or {}).get("eligibility", {})
        if not eligibility.get("challenger_eligible"):
            raise ValueError("qualified_challenger requires eligibility.challenger_eligible=True")
        record.status = QUALIFIED_CHALLENGER
        record.fitness_details = dict(record.fitness_details or {})
        record.fitness_details.setdefault("archive_symbol", symbol)
        self.qualified_challengers[symbol] = record
        self._save_record_file(QUALIFIED_CHALLENGER, record)
        self._save_all()
        return record

    def add_challenger(self, record: ArchiveRecord, symbol: str = "default"):
        """Backward-compatible safe wrapper for Stage 3 qualified challengers."""
        return self.add_qualified_challenger(record, symbol)

    def get_qualified_challenger(self, symbol: str = "default") -> Optional[ArchiveRecord]:
        return self.qualified_challengers.get(symbol)

    def get_challenger(self, symbol: str = "default") -> Optional[ArchiveRecord]:
        """Backward-compatible alias for qualified challenger."""
        return self.get_qualified_challenger(symbol)

    def start_validation(self, record_id: str) -> bool:
        record = self._pop_record(record_id, QUALIFIED_CHALLENGER)
        if not record:
            return False
        record.status = VALIDATING
        record.validation_started_at = datetime.now().isoformat()
        record.paper_metrics = dict(record.paper_metrics or {})
        record.paper_metrics.setdefault("paper_started_at", record.validation_started_at)
        record.paper_metrics.setdefault("paper_days", 0)
        record.paper_metrics.setdefault("paper_trades", 0)
        record.paper_metrics.setdefault("paper_closed_trades", 0)
        record.paper_metrics.setdefault("paper_open_trades", 0)
        record.paper_metrics.setdefault("paper_pnl", 0.0)
        record.paper_metrics.setdefault("paper_gross_pnl", 0.0)
        record.paper_metrics.setdefault("paper_fees", 0.0)
        record.paper_metrics.setdefault("paper_slippage", 0.0)
        record.paper_metrics.setdefault("paper_max_drawdown", 0.0)
        record.paper_metrics.setdefault("paper_win_rate", 0.0)
        record.paper_metrics.setdefault("paper_profit_factor", 0.0)
        record.paper_metrics.setdefault("paper_symbols_traded", [])
        record.paper_metrics.setdefault("paper_last_updated", record.validation_started_at)
        symbol = self._record_symbol(record)
        self.validating[symbol] = record
        self._save_all()
        return True

    def mark_pending_acceptance(self, record_id: str, paper_metrics: Dict[str, Any]) -> bool:
        record = self._pop_record(record_id, VALIDATING)
        if not record:
            return False
        if not paper_metrics or not paper_metrics.get("paper_validation_passed"):
            self.validating[self._record_symbol(record)] = record
            self._save_all()
            return False
        record.status = PENDING_ACCEPTANCE
        record.pending_at = datetime.now().isoformat()
        record.paper_metrics = dict(paper_metrics or {})
        record.paper_trades = int(record.paper_metrics.get("paper_closed_trades", record.paper_trades))
        record.paper_pnl = float(record.paper_metrics.get("paper_pnl", record.paper_pnl))
        symbol = self._record_symbol(record)
        self.pending_acceptance[symbol] = record
        self._save_all()
        return True

    def promote_to_champion(self, record_id: str, symbol: str = "default") -> bool:
        record = self._pop_record(record_id, PENDING_ACCEPTANCE)
        if not record:
            return False

        symbol = self._record_symbol(record, symbol)
        if symbol in self.champions:
            self.retire_champion(self.champions[symbol].chromosome_id, "replaced_by_new_champion")

        record.status = CHAMPION
        record.promoted_at = datetime.now().isoformat()
        self.champions[symbol] = record
        self._save_all()
        return True

    def promote_challenger(self, chromosome_id: str, symbol: str = "default") -> bool:
        """Legacy name retained; only pending_acceptance records can be promoted."""
        return self.promote_to_champion(chromosome_id, symbol)

    def retire_champion(self, record_id: str, reason: Optional[str] = None) -> bool:
        record = self._pop_record(record_id, CHAMPION)
        if not record:
            return False
        record.status = RETIRED
        record.retired_at = datetime.now().isoformat()
        record.retired_reason = reason
        self.retired.append(record)
        self._save_all()
        return True

    def get_champion(self, symbol: str = "default") -> Optional[ArchiveRecord]:
        return self.champions.get(symbol)

    def get_runtime_chromosome_data(self, symbol: str = "default") -> Dict[str, Any]:
        """Return only a promoted Champion, or the deterministic built-in default."""
        champion = self.get_champion(symbol)
        if champion:
            return champion.chromosome_data

        from .chromosome_v2 import built_in_default_chromosome
        return built_in_default_chromosome(symbol).to_dict()

    def get_all_champions(self) -> Dict[str, ArchiveRecord]:
        return dict(self.champions)

    def get_elite_seeds(self, symbol: str = "default", top_n: int = 3) -> List[Dict[str, Any]]:
        """Return promoted Champion, qualified candidates, seed candidates, then retired elites."""
        seeds = []

        champ = self.get_champion(symbol)
        if champ:
            seeds.append(champ.chromosome_data)

        qualified = self.get_qualified_challenger(symbol)
        if qualified and len(seeds) < top_n:
            seeds.append(qualified.chromosome_data)

        for record in sorted(self.seed_candidates, key=lambda r: r.fitness_score, reverse=True):
            if len(seeds) >= top_n:
                break
            seeds.append(record.chromosome_data)

        retired_sorted = sorted(
            [r for r in self.retired if r.fitness_score is not None],
            key=lambda r: r.fitness_score,
            reverse=True,
        )
        for record in retired_sorted:
            if len(seeds) >= top_n:
                break
            seeds.append(record.chromosome_data)

        return seeds

    def update_paper_results(self, chromosome_id: str, trades: int, pnl: float):
        """更新紙上交易結果到檔案記錄."""
        for _, _, record in self._iter_mutable_records():
            if record.chromosome_id == chromosome_id:
                record.paper_trades = trades
                record.paper_pnl = pnl
                self._save_all()
                return

    def get_stats(self) -> Dict[str, Any]:
        return {
            "raw_candidates": len(self.raw_candidates),
            "seed_candidates": len(self.seed_candidates),
            "rejected": len(self.rejected),
            "qualified_challengers": len(self.qualified_challengers),
            "challengers": len(self.qualified_challengers),
            "validating": len(self.validating),
            "pending_acceptance": len(self.pending_acceptance),
            "champions": len(self.champions),
            "retired": len(self.retired),
            "champion_list": [
                {"symbol": s, "id": r.chromosome_id[:8], "fitness": r.fitness_score}
                for s, r in self.champions.items()
            ],
            "retired_count": len(self.retired),
            "rejected_count": len(self.rejected),
        }


if __name__ == "__main__":
    print("=== Strategy Archive Loaded ===")
