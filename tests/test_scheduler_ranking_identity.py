import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import scheduler


def test_live_ranking_uses_canonical_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler, 'STATE_DIR', tmp_path)
    strategy = {
        'id': 'parabolic_sar_v2',
        'name': 'Parabolic SAR',
        'signal_type': 'PARABOLIC_SAR',
        'enabled': True,
    }
    signal = SimpleNamespace(metadata={
        'strategy_name': 'parabolic_sar',
        'strategy_id': 'parabolic_sar',
        'conditions_passed': 2,
        'conditions_total': 3,
    })
    result = SimpleNamespace(
        success=True,
        symbol='BTCUSDT',
        current_price=100.0,
        confirmed_signals=[signal],
        watch_only_signals=[],
    )
    instance = scheduler.MonitoringScheduler.__new__(scheduler.MonitoringScheduler)
    instance.runner = SimpleNamespace(
        strategy_executor=SimpleNamespace(enabled_strategies=[strategy])
    )
    instance._log = lambda message: None

    instance._update_live_ranking([result])

    data = json.loads((tmp_path / 'live_strategy_ranking.json').read_text())
    rows = data['symbols']['BTCUSDT']['strategies']
    assert data['score_type'] == 'signal_readiness'
    assert [row['strategy_id'] for row in rows] == ['parabolic_sar_v2']
    assert rows[0]['name'] == 'parabolic_sar_v2'
