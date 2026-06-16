"""Read and mutate Evolution V2 state for the Dash UI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.genetic_engine.archive import StrategyArchive
from app.genetic_engine.evolution_v2 import DEFAULT_CONFIG_V2


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "data" / "genetic_archive"
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "evolution_v2.json"
RUN_DIRS = (
    PROJECT_ROOT / "data" / "genetic_evolution_v2",
    PROJECT_ROOT / "genetic_runs",
)

EDITABLE_CONFIG = {
    "population_size": (1, 1000, int),
    "max_generations": (1, 10000, int),
    "mutation_rate": (0.0, 1.0, float),
    "crossover_rate": (0.0, 1.0, float),
    "backtest_days": (1, 3650, int),
    "multi_window_history_days": (180, 3650, int),
    "monte_carlo_history_days": (1, 3650, int),
    "monte_carlo_simulations": (10, 100000, int),
}


@dataclass
class EvolutionSnapshot:
    source_file: Optional[str]
    last_updated: Optional[str]
    epoch_id: Optional[str]
    generation: Optional[int]
    max_generations: int
    progress_pct: float
    environment: Dict[str, Any]
    seasons: List[Dict[str, Any]]
    ranking: List[Dict[str, Any]]
    archive: Dict[str, Any]
    config: Dict[str, Any]
    running: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_json(path: Path, default: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def load_evolution_config(config_file: Path = DEFAULT_CONFIG_FILE) -> Dict[str, Any]:
    saved = _load_json(config_file, {})
    return {**DEFAULT_CONFIG_V2, **saved}


def save_evolution_config(
    updates: Dict[str, Any],
    config_file: Path = DEFAULT_CONFIG_FILE,
) -> Dict[str, Any]:
    config = load_evolution_config(config_file)
    for key, value in updates.items():
        if key not in EDITABLE_CONFIG:
            raise ValueError(f"Unsupported evolution setting: {key}")
        low, high, caster = EDITABLE_CONFIG[key]
        try:
            parsed = caster(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric") from exc
        if not low <= parsed <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
        config[key] = parsed

    if config["mutation_rate"] + config["crossover_rate"] > 1.5:
        raise ValueError("mutation_rate + crossover_rate must not exceed 1.5")

    config_file.parent.mkdir(parents=True, exist_ok=True)
    with config_file.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    return config


def _generation_files(run_dirs: tuple[Path, ...] = RUN_DIRS) -> List[Path]:
    files: List[Path] = []
    for run_dir in run_dirs:
        if run_dir.exists():
            files.extend(run_dir.glob("generation_*.json"))
    return files


def load_latest_generation(
    run_dirs: tuple[Path, ...] = RUN_DIRS,
) -> tuple[Optional[Path], Dict[str, Any]]:
    candidates = _generation_files(run_dirs)
    if not candidates:
        return None, {}
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return latest, _load_json(latest, {})


def _rank_population(population: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(
        population,
        key=lambda row: row.get("fitness_score")
        if row.get("fitness_score") is not None else float("-inf"),
        reverse=True,
    )
    result = []
    for index, chromosome in enumerate(ranked, 1):
        details = chromosome.get("fitness_details") or {}
        result.append({
            "rank": index,
            "chromosome_id": chromosome.get("chromosome_id", "unknown"),
            "symbol": chromosome.get("symbol", "default"),
            "fitness": chromosome.get("fitness_score"),
            "generation": chromosome.get("generation"),
            "macro": chromosome.get("macro_genes") or {},
            "micro": chromosome.get("micro_genes") or {},
            "risk": chromosome.get("risk_genes") or {},
            "per_window": details.get("per_window") or {},
            "insufficient_data": bool(details.get("insufficient_data", False)),
            "data_provenance": details.get("data_provenance") or {},
        })
    return result


def _record_rows(records: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for symbol, record in records.items():
        rows.append({
            "symbol": symbol,
            "chromosome_id": record.chromosome_id,
            "fitness": record.fitness_score,
            "generation": record.generation,
            "created_at": record.created_at,
            "promoted_at": record.promoted_at,
            "retired_at": record.retired_at,
            "chromosome": record.chromosome_data,
            "fitness_details": record.fitness_details,
        })
    return rows


def load_archive_snapshot(
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
) -> Dict[str, List[Dict[str, Any]]]:
    archive = StrategyArchive(str(archive_dir))
    return {
        "raw_candidates": [
            {
                "symbol": record.chromosome_data.get("symbol", "default"),
                "chromosome_id": record.chromosome_id,
                "fitness": record.fitness_score,
                "generation": record.generation,
                "created_at": record.created_at,
                "chromosome": record.chromosome_data,
                "fitness_details": record.fitness_details,
            }
            for record in archive.raw_candidates
        ],
        "seed_candidates": [
            {
                "symbol": record.chromosome_data.get("symbol", "default"),
                "chromosome_id": record.chromosome_id,
                "fitness": record.fitness_score,
                "generation": record.generation,
                "created_at": record.created_at,
                "chromosome": record.chromosome_data,
                "fitness_details": record.fitness_details,
            }
            for record in archive.seed_candidates
        ],
        "rejected": [
            {
                "symbol": record.chromosome_data.get("symbol", "default"),
                "chromosome_id": record.chromosome_id,
                "fitness": record.fitness_score,
                "generation": record.generation,
                "created_at": record.created_at,
                "chromosome": record.chromosome_data,
                "fitness_details": record.fitness_details,
            }
            for record in archive.rejected
        ],
        "qualified_challengers": _record_rows(archive.qualified_challengers),
        "champions": _record_rows(archive.champions),
        "challengers": _record_rows(archive.challengers),
        "validating": _record_rows(archive.validating),
        "pending_acceptance": _record_rows(archive.pending_acceptance),
        "retired": [
            {
                "symbol": record.chromosome_data.get("symbol", "default"),
                "chromosome_id": record.chromosome_id,
                "fitness": record.fitness_score,
                "generation": record.generation,
                "created_at": record.created_at,
                "promoted_at": record.promoted_at,
                "retired_at": record.retired_at,
                "chromosome": record.chromosome_data,
                "fitness_details": record.fitness_details,
            }
            for record in archive.retired
        ],
    }


def load_evolution_snapshot(
    run_dirs: tuple[Path, ...] = RUN_DIRS,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    config_file: Path = DEFAULT_CONFIG_FILE,
) -> Dict[str, Any]:
    config = load_evolution_config(config_file)
    source, generation = load_latest_generation(run_dirs)
    three_layer = generation.get("three_layer") or {}
    current_generation = generation.get("generation")
    max_generations = int(config["max_generations"])
    progress = (
        min(100.0, ((int(current_generation) + 1) / max_generations) * 100)
        if current_generation is not None and max_generations > 0 else 0.0
    )
    running_file = PROJECT_ROOT / "state" / "evolution_v2_running.json"
    running_state = _load_json(running_file, {})
    if running_state.get("running"):
        current_generation = running_state.get("generation", current_generation)
        max_generations = int(running_state.get("max_generations", max_generations))
        progress = (
            min(100.0, ((int(current_generation) + 1) / max_generations) * 100)
            if current_generation is not None and max_generations > 0 else 0.0
        )

    snapshot = EvolutionSnapshot(
        source_file=str(source) if source else None,
        last_updated=generation.get("timestamp"),
        epoch_id=generation.get("epoch_id"),
        generation=current_generation,
        max_generations=max_generations,
        progress_pct=round(progress, 2),
        environment=three_layer.get("environment") or {},
        seasons=three_layer.get("seasons") or [],
        ranking=_rank_population(generation.get("population") or []),
        archive=load_archive_snapshot(archive_dir),
        config={key: config[key] for key in EDITABLE_CONFIG},
        running=bool(running_state.get("running", False)),
    )
    return snapshot.to_dict()


def promote_challenger(
    symbol: str,
    chromosome_id: str,
    confirmation: str,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
) -> Dict[str, Any]:
    if not chromosome_id or confirmation.strip() != chromosome_id:
        raise ValueError("Confirmation must exactly match the Challenger chromosome ID")

    archive = StrategyArchive(str(archive_dir))
    pending = archive.pending_acceptance.get(symbol)
    if pending is None or pending.chromosome_id != chromosome_id:
        raise ValueError("Selected strategy is not pending acceptance; refresh and try again")
    if not archive.promote_to_champion(chromosome_id, symbol):
        raise ValueError("Promote failed")
    return {
        "ok": True,
        "symbol": symbol,
        "chromosome_id": chromosome_id,
        "promoted_at": datetime.now().isoformat(),
    }
