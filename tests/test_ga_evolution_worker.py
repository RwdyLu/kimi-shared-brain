"""Phase E tests for the independent GA Evolution worker."""

import json

from scripts import run_evolution_worker as worker_mod


class DummyArchive:
    def __init__(self, qualified=None, rejected=None, seeds=None):
        self.qualified_challengers = qualified or {}
        self.rejected = rejected or []
        self.seed_candidates = seeds or []
        self.promote_called = False

    def promote_to_champion(self, *_args, **_kwargs):
        self.promote_called = True
        raise AssertionError("worker must not promote")


class DummyEngine:
    instances = []
    run_calls = 0

    def __init__(self, config=None):
        self.config = config or {}
        self.epoch_id = f"epoch_{len(DummyEngine.instances) + 1}"
        self.archive = DummyArchive()
        DummyEngine.instances.append(self)

    def run(self, max_generations=None, verbose=True):
        DummyEngine.run_calls += 1
        self.max_generations = max_generations
        self.verbose = verbose
        return object()


class FailingEngine(DummyEngine):
    def run(self, max_generations=None, verbose=True):
        DummyEngine.run_calls += 1
        raise RuntimeError("boom")


class DummyValidationManager:
    started = []

    def __init__(self, archive=None):
        self.archive = archive

    def start_paper_validation(self, record_id):
        DummyValidationManager.started.append(record_id)
        return True


class Record:
    def __init__(self, chromosome_id):
        self.chromosome_id = chromosome_id


def _config(tmp_path, **overrides):
    cfg = worker_mod.WorkerConfig(
        lock_file=tmp_path / "worker.lock",
        checkpoint_file=tmp_path / "state" / "checkpoint.json",
        resource_log_file=tmp_path / "logs" / "worker.log",
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_defaults_are_single_run_not_continuous(monkeypatch):
    for name in (
        "GA_CONTINUOUS",
        "GA_POPULATION_SIZE",
        "GA_MAX_GENERATIONS",
        "GA_INTERVAL_MINUTES",
    ):
        monkeypatch.delenv(name, raising=False)

    cfg = worker_mod.WorkerConfig.from_env()

    assert cfg.continuous is False
    assert cfg.population_size == 30
    assert cfg.max_generations == 20
    assert cfg.interval_minutes == 10


def test_env_overrides_worker_config(monkeypatch, tmp_path):
    monkeypatch.setenv("GA_CONTINUOUS", "true")
    monkeypatch.setenv("GA_POPULATION_SIZE", "12")
    monkeypatch.setenv("GA_MAX_GENERATIONS", "7")
    monkeypatch.setenv("GA_INTERVAL_MINUTES", "3")
    monkeypatch.setenv("GA_LOCK_FILE", str(tmp_path / "custom.lock"))

    cfg = worker_mod.WorkerConfig.from_env()

    assert cfg.continuous is True
    assert cfg.population_size == 12
    assert cfg.max_generations == 7
    assert cfg.interval_minutes == 3
    assert cfg.lock_file == tmp_path / "custom.lock"


def test_lock_file_prevents_second_worker(tmp_path):
    lock = worker_mod.WorkerLock(tmp_path / "worker.lock")

    assert lock.acquire()
    assert worker_mod.WorkerLock(tmp_path / "worker.lock").acquire() is False
    lock.release()


def test_stale_lock_can_be_replaced(tmp_path):
    path = tmp_path / "worker.lock"
    path.write_text(json.dumps({"pid": 99999999, "started_at": "old"}), encoding="utf-8")

    lock = worker_mod.WorkerLock(path)

    assert lock.acquire()
    assert _read_json(path)["pid"] != 99999999
    lock.release()


def test_checkpoint_and_resource_log_are_written_to_tmp_path(tmp_path):
    cfg = _config(tmp_path)
    evo = worker_mod.EvolutionWorker(
        cfg,
        engine_cls=DummyEngine,
        validation_manager_cls=DummyValidationManager,
    )

    assert evo.run() == 0
    checkpoint = _read_json(cfg.checkpoint_file)
    assert checkpoint["last_status"] == "completed"
    assert checkpoint["epochs_completed"] == 1
    assert cfg.resource_log_file.exists()
    log = json.loads(cfg.resource_log_file.read_text(encoding="utf-8").splitlines()[0])
    assert log["population_size"] == 30
    assert log["max_generations"] == 20
    assert log["status"] == "completed"


def test_single_run_exits_without_looping(tmp_path):
    DummyEngine.instances = []
    DummyEngine.run_calls = 0
    cfg = _config(tmp_path, continuous=False)
    evo = worker_mod.EvolutionWorker(cfg, engine_cls=DummyEngine)

    assert evo.run() == 0
    assert DummyEngine.run_calls == 1


def test_continuous_false_does_not_sleep(tmp_path):
    sleep_calls = []
    cfg = _config(tmp_path, continuous=False)
    evo = worker_mod.EvolutionWorker(
        cfg,
        engine_cls=DummyEngine,
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    evo.run()

    assert sleep_calls == []


def test_consecutive_failures_stop_continuous_loop(tmp_path):
    cfg = _config(tmp_path, continuous=True)
    evo = worker_mod.EvolutionWorker(
        cfg,
        engine_cls=FailingEngine,
        sleep_fn=lambda _seconds: None,
    )

    assert evo.run() == 0
    checkpoint = _read_json(cfg.checkpoint_file)
    assert checkpoint["last_status"] == "paused"
    assert checkpoint["consecutive_failures"] == 5


def test_worker_does_not_call_promote_to_champion(tmp_path):
    class QualifiedEngine(DummyEngine):
        def __init__(self, config=None):
            super().__init__(config)
            self.archive = DummyArchive(qualified={"BTCUSDT": Record("QUAL_1")})

    cfg = _config(tmp_path)
    evo = worker_mod.EvolutionWorker(
        cfg,
        engine_cls=QualifiedEngine,
        validation_manager_cls=DummyValidationManager,
    )

    assert evo.run() == 0
    assert QualifiedEngine.instances[-1].archive.promote_called is False


def test_worker_can_auto_start_paper_validation_for_qualified(tmp_path):
    DummyValidationManager.started = []

    class QualifiedEngine(DummyEngine):
        def __init__(self, config=None):
            super().__init__(config)
            self.archive = DummyArchive(qualified={"BTCUSDT": Record("QUAL_1")})

    cfg = _config(tmp_path, auto_start_validation=True)
    evo = worker_mod.EvolutionWorker(
        cfg,
        engine_cls=QualifiedEngine,
        validation_manager_cls=DummyValidationManager,
    )

    evo.run()

    assert DummyValidationManager.started == ["QUAL_1"]


def test_worker_does_not_modify_paper_trading_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    paper_state = state_dir / "paper_trading_state.json"
    paper_state.write_text('{"do_not_touch": true}', encoding="utf-8")
    before = paper_state.read_text(encoding="utf-8")

    cfg = _config(tmp_path, checkpoint_file=state_dir / "ga_evolution_checkpoint.json")
    evo = worker_mod.EvolutionWorker(cfg, engine_cls=DummyEngine)
    evo.run()

    assert paper_state.read_text(encoding="utf-8") == before


def test_worker_does_not_change_scheduler_entrypoint():
    scheduler = (worker_mod.PROJECT_ROOT / "scripts" / "run_scheduler.py").read_text(encoding="utf-8")

    assert "run_every_5_minutes" in scheduler
    assert "run_evolution_worker" not in scheduler
    assert "EvolutionEngineV2" not in scheduler
