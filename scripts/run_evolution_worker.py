#!/usr/bin/env python3
"""Independent GA Evolution worker.

This worker is intentionally separate from scripts/run_scheduler.py and
app.scheduler.run_every_5_minutes(). It does not place orders, promote
strategies, or mutate the existing paper_trading_state.json ledger.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.genetic_engine.evolution_v2 import EvolutionEngineV2
from app.genetic_engine.paper_validation import PaperValidationManager


DEFAULT_LOCK_FILE = Path("/tmp/kimi_ga_evolution_worker.lock")
DEFAULT_CHECKPOINT_FILE = PROJECT_ROOT / "state" / "ga_evolution_checkpoint.json"
DEFAULT_RESOURCE_LOG_FILE = PROJECT_ROOT / "logs" / "ga_evolution_worker.log"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value is None else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return default if value is None else float(value)


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return default if value is None else Path(value)


@dataclass
class WorkerConfig:
    continuous: bool = False
    population_size: int = 30
    max_generations: int = 20
    interval_minutes: int = 10
    max_runtime_minutes: int = 360
    early_stop_generations: int = 10
    early_stop_threshold: float = 0.001
    lock_file: Path = DEFAULT_LOCK_FILE
    checkpoint_file: Path = DEFAULT_CHECKPOINT_FILE
    resource_log_file: Path = DEFAULT_RESOURCE_LOG_FILE
    auto_start_validation: bool = True

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls(
            continuous=_env_bool("GA_CONTINUOUS", False),
            population_size=_env_int("GA_POPULATION_SIZE", 30),
            max_generations=_env_int("GA_MAX_GENERATIONS", 20),
            interval_minutes=_env_int("GA_INTERVAL_MINUTES", 10),
            max_runtime_minutes=_env_int("GA_MAX_RUNTIME_MINUTES", 360),
            early_stop_generations=_env_int("GA_EARLY_STOP_GENERATIONS", 10),
            early_stop_threshold=_env_float("GA_EARLY_STOP_THRESHOLD", 0.001),
            lock_file=_env_path("GA_LOCK_FILE", DEFAULT_LOCK_FILE),
            checkpoint_file=_env_path("GA_CHECKPOINT_FILE", DEFAULT_CHECKPOINT_FILE),
            resource_log_file=_env_path("GA_RESOURCE_LOG_FILE", DEFAULT_RESOURCE_LOG_FILE),
            auto_start_validation=_env_bool("GA_AUTO_START_VALIDATION", True),
        )


def _now() -> str:
    return datetime.now().isoformat()


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class WorkerLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.acquired = False

    def _existing_lock(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"pid": None, "corrupt": True}

    def acquire(self) -> bool:
        existing = self._existing_lock()
        if existing:
            pid = existing.get("pid")
            if isinstance(pid, int) and _pid_exists(pid):
                return False
            if existing.get("corrupt") and not os.environ.get("GA_ALLOW_CORRUPT_LOCK_REPLACE"):
                return False
            # Stale lock: pid is absent or dead, so replacement is safe.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": os.getpid(),
            "started_at": _now(),
            "command": " ".join(sys.argv),
            "hostname": socket.gethostname(),
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            existing = self._existing_lock()
            if existing and existing.get("pid") == os.getpid():
                self.path.unlink(missing_ok=True)
        finally:
            self.acquired = False


def load_checkpoint(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "worker_started_at": None,
            "last_epoch_started_at": None,
            "last_epoch_completed_at": None,
            "last_epoch_id": None,
            "last_stage": None,
            "last_status": None,
            "last_error": None,
            "epochs_completed": 0,
            "consecutive_failures": 0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, checkpoint: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def _resource_usage() -> Dict[str, Optional[float]]:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # macOS reports ru_maxrss in bytes; Linux in KiB. Keep this approximate.
        memory_mb = usage.ru_maxrss / (1024 * 1024)
        if memory_mb < 1:
            memory_mb = usage.ru_maxrss / 1024
        return {"cpu_percent": None, "memory_mb": round(memory_mb, 3)}
    except Exception:
        return {"cpu_percent": None, "memory_mb": None}


def append_resource_log(path: Path, event: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


class EvolutionWorker:
    def __init__(
        self,
        config: WorkerConfig,
        engine_cls=EvolutionEngineV2,
        validation_manager_cls=PaperValidationManager,
        sleep_fn=time.sleep,
    ):
        self.config = config
        self.engine_cls = engine_cls
        self.validation_manager_cls = validation_manager_cls
        self.sleep_fn = sleep_fn
        self.worker_started_at = _now()

    def _engine_config(self) -> Dict[str, Any]:
        return {
            "population_size": self.config.population_size,
            "max_generations": self.config.max_generations,
            "early_stop_generations": self.config.early_stop_generations,
            "early_stop_threshold": self.config.early_stop_threshold,
        }

    def _archive_counts(self, engine: Any) -> Dict[str, int]:
        archive = getattr(engine, "archive", None)
        if archive is None:
            return {"qualified_count": 0, "rejected_count": 0, "seed_count": 0}
        return {
            "qualified_count": len(getattr(archive, "qualified_challengers", {})),
            "rejected_count": len(getattr(archive, "rejected", [])),
            "seed_count": len(getattr(archive, "seed_candidates", [])),
        }

    def _auto_start_validation(self, engine: Any) -> None:
        if not self.config.auto_start_validation:
            return
        archive = getattr(engine, "archive", None)
        if archive is None:
            return
        manager = self.validation_manager_cls(archive=archive)
        for record in list(getattr(archive, "qualified_challengers", {}).values()):
            manager.start_paper_validation(record.chromosome_id)

    def run_one_epoch(self, checkpoint: Dict[str, Any]) -> Dict[str, Any]:
        epoch_started_at = _now()
        started = time.monotonic()
        checkpoint.update({
            "worker_started_at": checkpoint.get("worker_started_at") or self.worker_started_at,
            "last_epoch_started_at": epoch_started_at,
            "last_status": "running",
            "last_error": None,
        })
        save_checkpoint(self.config.checkpoint_file, checkpoint)

        engine = self.engine_cls(config=self._engine_config())
        event = {
            "epoch_id": getattr(engine, "epoch_id", None),
            "population_size": self.config.population_size,
            "max_generations": self.config.max_generations,
            "started_at": epoch_started_at,
            "completed_at": None,
            "elapsed_seconds": None,
            "status": "running",
            "error": None,
            "archive_result_status": None,
            "qualified_count": 0,
            "rejected_count": 0,
            "seed_count": 0,
        }

        try:
            engine.run(max_generations=self.config.max_generations, verbose=True)
            elapsed = time.monotonic() - started
            if elapsed > self.config.max_runtime_minutes * 60:
                status = "timeout"
                error = f"epoch exceeded GA_MAX_RUNTIME_MINUTES={self.config.max_runtime_minutes}"
            else:
                status = "completed"
                error = None
            self._auto_start_validation(engine)
            counts = self._archive_counts(engine)
            event.update(counts)
            event["archive_result_status"] = self._archive_status(counts)
        except Exception as exc:
            elapsed = time.monotonic() - started
            status = "failed"
            error = str(exc)

        completed_at = _now()
        usage = _resource_usage()
        event.update({
            "epoch_id": getattr(engine, "epoch_id", event.get("epoch_id")),
            "completed_at": completed_at,
            "elapsed_seconds": round(elapsed, 3),
            "status": status,
            "error": error,
            "cpu_percent": usage["cpu_percent"],
            "memory_mb": usage["memory_mb"],
        })
        append_resource_log(self.config.resource_log_file, event)

        checkpoint.update({
            "last_epoch_completed_at": completed_at,
            "last_epoch_id": event.get("epoch_id"),
            "last_stage": event.get("archive_result_status"),
            "last_status": status,
            "last_error": error,
            "epochs_completed": int(checkpoint.get("epochs_completed", 0)) + (1 if status == "completed" else 0),
            "consecutive_failures": 0 if status == "completed" else int(checkpoint.get("consecutive_failures", 0)) + 1,
        })
        save_checkpoint(self.config.checkpoint_file, checkpoint)
        return event

    @staticmethod
    def _archive_status(counts: Dict[str, int]) -> str:
        if counts.get("qualified_count", 0) > 0:
            return "qualified_challenger"
        if counts.get("seed_count", 0) > 0:
            return "seed_candidate"
        if counts.get("rejected_count", 0) > 0:
            return "rejected"
        return "raw_candidate"

    def run(self) -> int:
        lock = WorkerLock(self.config.lock_file)
        if not lock.acquire():
            return 2
        try:
            checkpoint = load_checkpoint(self.config.checkpoint_file)
            checkpoint["worker_started_at"] = self.worker_started_at
            while True:
                self.run_one_epoch(checkpoint)
                checkpoint = load_checkpoint(self.config.checkpoint_file)
                if not self.config.continuous:
                    break
                if int(checkpoint.get("consecutive_failures", 0)) >= 5:
                    checkpoint["last_status"] = "paused"
                    checkpoint["last_error"] = "consecutive_failures >= 5"
                    save_checkpoint(self.config.checkpoint_file, checkpoint)
                    break
                self.sleep_fn(self.config.interval_minutes * 60)
            return 0
        finally:
            lock.release()


def main() -> int:
    return EvolutionWorker(WorkerConfig.from_env()).run()


if __name__ == "__main__":
    raise SystemExit(main())
