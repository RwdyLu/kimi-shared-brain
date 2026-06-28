import importlib.util
from pathlib import Path
import uuid

import dash
import pytest


def load_module(monkeypatch):
    monkeypatch.setattr(dash, 'register_page', lambda *args, **kwargs: None)
    path = Path('ui/pages/strategy_detail.py')
    name = f'strategy_detail_test_{uuid.uuid4().hex}'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_records(today):
    return [
        {
            'symbol': 'BTCUSDT',
            'timestamp': f'{today}T10:00:00',
            'run_id': 1,
            'price': 100.0,
            'signal_types': ['MA_CROSS'],
            'signals_count': 1,
        },
        {
            'symbol': 'BTCUSDT',
            'timestamp': f'{today}T10:05:00',
            'run_id': 2,
            'price': 101.0,
            'signal_types': [],
            'signals_count': 0,
        },
    ]


def test_helpers_reuse_supplied_snapshot_records(monkeypatch):
    mod = load_module(monkeypatch)
    today = mod.datetime.now().strftime('%Y-%m-%d')
    records = sample_records(today)
    monkeypatch.setattr(mod, 'read_recent_jsonl', lambda *args, **kwargs: pytest.fail('unexpected disk read'))

    assert mod.get_latest_snapshot('BTCUSDT', records=records)['price'] == 101.0
    assert len(mod.get_signal_history('ma_cross', 'MA_CROSS', 'BTCUSDT', records=records)) == 1
    assert len(mod.get_recent_runs_for_strategy('MA_CROSS', 'BTCUSDT', records=records)) == 2
    assert len(mod.get_today_signals_for_strategy('ma_cross', 'MA_CROSS', 'BTCUSDT', records=records)) == 1
    assert len(mod.get_symbol_snapshots_today('BTCUSDT', records=records)) == 2


def test_detail_callback_reads_snapshot_tail_once(monkeypatch):
    mod = load_module(monkeypatch)
    today = mod.datetime.now().strftime('%Y-%m-%d')
    records = sample_records(today)
    reads = []

    def fake_read(path, *args, **kwargs):
        reads.append(path)
        return records

    strategy = {'id': 'ma_cross', 'name': 'MA Cross', 'signal_type': 'MA_CROSS', 'conditions': []}
    monkeypatch.setattr(mod, 'read_recent_jsonl', fake_read)
    monkeypatch.setattr(mod, 'find_strategy', lambda name: strategy)
    monkeypatch.setattr(mod, 'render_conditions', lambda strategy, snapshot: 'conditions')
    monkeypatch.setattr(mod, 'render_indicators', lambda snapshot, strategy: 'indicators')
    monkeypatch.setattr(mod, 'render_signal_history', lambda strategy, symbol, shared: ('history', shared))
    monkeypatch.setattr(mod, 'render_trading_log', lambda strategy, symbol, price, shared: ('trades', shared))
    monkeypatch.setattr(mod, 'render_signal_simulation', lambda strategy, symbol, shared: ('simulation', shared))
    monkeypatch.setattr(Path, 'exists', lambda self: True)

    result = mod.update_strategy_detail('BTCUSDT', 0, 'ma_cross')

    assert len(reads) == 1
    assert result[0] == '$101.00'
    assert result[4][1] is records
    assert result[5][1] is records
    assert result[6][1] is records


def test_layout_accepts_query_parameters(monkeypatch):
    mod = load_module(monkeypatch)
    monkeypatch.setattr(mod, 'find_strategy', lambda name: None)
    component = mod.layout('ma_cross_trend_v2', symbol='BTCUSDT')
    assert component is not None
