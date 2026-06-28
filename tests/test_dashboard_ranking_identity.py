import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.strategy_identity import build_strategy_alias_map, resolve_strategy_id


def make_aliases():
    """
    Build alias map matching real strategies.json format.
    name='GEN X_14ddf6' normalises to 'gen_x_14ddf6', which maps to canonical id.
    """
    strategies = [
        {
            "id": "genetic_x_14ddf6519470",
            "name": "GEN X_14ddf6",
            "name_zh": "\u57fa\u56e0\u7b56\u7565 X_14ddf6",
            "type": "momentum",
            "enabled": True,
        }
    ]
    return build_strategy_alias_map(strategies)


def deduplicate_ranking(raw, aliases):
    """Mirrors the dedup logic added to dashboard.py."""
    import copy
    data = copy.deepcopy(raw)
    for sym_data in data.get("symbols", {}).values():
        merged = {}
        for entry in sym_data.get("strategies", []):
            canon = resolve_strategy_id(entry.get("name", ""), entry.get("name", ""), aliases)
            if canon not in merged:
                merged[canon] = dict(entry)
                merged[canon]["name"] = canon
            else:
                if entry.get("rolling_avg", 0) > merged[canon].get("rolling_avg", 0):
                    merged[canon] = dict(entry)
                    merged[canon]["name"] = canon
        sym_data["strategies"] = list(merged.values())
    return data


def test_dashboard_deduplicates_gen_x():
    aliases = make_aliases()
    raw = {
        "symbols": {
            "BTCUSDT": {
                "strategies": [
                    {"name": "genetic_x_14ddf6519470", "rolling_avg": 0.5},
                    {"name": "gen_x_14ddf6",           "rolling_avg": 0.0},
                ]
            }
        }
    }
    result = deduplicate_ranking(raw, aliases)
    strat_names = [s["name"] for s in result["symbols"]["BTCUSDT"]["strategies"]]
    assert strat_names.count("genetic_x_14ddf6519470") == 1, f"Expected 1, got: {strat_names}"
    assert "gen_x_14ddf6" not in strat_names, f"gen_x_14ddf6 still present: {strat_names}"


def test_dedup_keeps_higher_rolling_avg():
    aliases = make_aliases()
    raw = {
        "symbols": {
            "BTCUSDT": {
                "strategies": [
                    {"name": "gen_x_14ddf6",           "rolling_avg": 0.8},
                    {"name": "genetic_x_14ddf6519470", "rolling_avg": 0.3},
                ]
            }
        }
    }
    result = deduplicate_ranking(raw, aliases)
    strategies = result["symbols"]["BTCUSDT"]["strategies"]
    assert len(strategies) == 1, f"Expected 1 strategy, got {len(strategies)}: {[s['name'] for s in strategies]}"
    assert strategies[0]["rolling_avg"] == 0.8, f"Expected 0.8, got {strategies[0]['rolling_avg']}"
