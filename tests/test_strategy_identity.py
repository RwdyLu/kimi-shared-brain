import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.strategy_identity import build_strategy_alias_map, resolve_strategy_id


def test_aliases_resolve_to_canonical_id():
    strategies = [{
        'id': 'parabolic_sar_v2',
        'name': 'Parabolic SAR',
        'signal_type': 'PARABOLIC_SAR',
    }]
    aliases = build_strategy_alias_map(strategies)
    assert resolve_strategy_id('parabolic_sar_v2', None, aliases) == 'parabolic_sar_v2'
    assert resolve_strategy_id(None, 'Parabolic SAR', aliases) == 'parabolic_sar_v2'
    assert resolve_strategy_id(None, 'parabolic_sar', aliases) == 'parabolic_sar_v2'


def test_genetic_id_is_not_shortened():
    strategy_id = 'genetic_x_14ddf6519470'
    aliases = build_strategy_alias_map([{'id': strategy_id, 'name': 'GEN X_14DDF6'}])
    assert resolve_strategy_id(strategy_id, 'gen_x_14ddf6', aliases) == strategy_id
