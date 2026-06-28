"""Regression tests for legacy deployment paths found during final audit."""

from datetime import datetime

import pytest

from app.genetic_integration import GeneticIntegration, deploy_genetic_strategies
from app.strategy_validation import (
    StrategyStatus,
    StrategyTrial,
    StrategyValidationManager,
    ValidationCriteria,
)
from app import strategy_executor


def test_legacy_genetic_deployment_entry_points_are_disabled(tmp_path):
    integration = GeneticIntegration(
        strategies_config_path=str(tmp_path / "strategies.json")
    )
    with pytest.raises(RuntimeError, match="Challenger/Champion"):
        integration.start_continuous_evolution()
    with pytest.raises(RuntimeError, match="manually Promote"):
        deploy_genetic_strategies()


def test_validation_does_not_auto_promote():
    criteria = ValidationCriteria(
        min_win_rate=0.0,
        min_profit_factor=0.0,
        max_drawdown=1.0,
        min_trades=0,
        min_sharpe=-1.0,
        max_consecutive_losses=99,
    )
    manager = StrategyValidationManager(criteria=criteria)
    trial = StrategyTrial(
        strategy_id="candidate",
        strategy_name="Candidate",
        status=StrategyStatus.TRIAL,
        trial_start=datetime.now(),
        criteria=criteria,
    )
    manager.strategies["candidate"] = trial

    manager.evaluate_all()
    assert manager.strategies["candidate"].status == StrategyStatus.VALIDATED
    assert manager.promote_validated("candidate") is True
    assert manager.strategies["candidate"].status == StrategyStatus.PROMOTED


def test_runtime_loader_ignores_legacy_genetic_file(monkeypatch, tmp_path):
    legacy = tmp_path / "strategies_genetic.json"
    legacy.write_text('{"strategies":[{"id":"unsafe","source":"genetic"}]}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_executor, "load_strategies", lambda _path: [
        {"id": "manual", "source": "manual", "enabled": True},
    ])

    loaded = strategy_executor.load_merged_genetic_strategies()
    assert all(strategy.get("id") != "unsafe" for strategy in loaded)
    assert any(strategy.get("id") == "manual" for strategy in loaded)
    runtime_genetic = [
        strategy for strategy in loaded
        if (strategy.get("meta") or {}).get("source") == "genetic_evolution"
    ]
    assert len(runtime_genetic) == 1
    assert runtime_genetic[0]["id"] == "genetic_builtin_default_default"
