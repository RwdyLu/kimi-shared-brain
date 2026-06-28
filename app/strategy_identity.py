"""Canonical strategy identity helpers shared by runtime and UI."""


def normalize_strategy_alias(value):
    return str(value or '').strip().lower().replace(' ', '_').replace('-', '_')


def build_strategy_alias_map(strategies):
    aliases = {}
    for strategy in strategies:
        strategy_id = strategy.get('id')
        if not strategy_id:
            continue
        for value in (strategy_id, strategy.get('name'), strategy.get('signal_type')):
            normalized = normalize_strategy_alias(value)
            if normalized:
                aliases[normalized] = strategy_id
    return aliases


def resolve_strategy_id(strategy_id, strategy_name, aliases):
    for candidate in (strategy_id, strategy_name):
        normalized = normalize_strategy_alias(candidate)
        if normalized in aliases:
            return aliases[normalized]
    return normalize_strategy_alias(strategy_id or strategy_name)
