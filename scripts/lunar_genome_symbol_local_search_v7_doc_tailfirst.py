#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict

import argparse
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v7_robust as v7
import lunar_genome_symbol_validate_v7 as sv


def clone_genome(genome):
    return v7.dict_to_genome(v7.genome_to_dict(genome))


def genome_key(genome) -> str:
    return json.dumps(v7.genome_to_dict(genome), sort_keys=True, separators=(',', ':'))


def load_seed_rows(paths: list[str], symbols: set[str], max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            continue
        obj = json.loads(p.read_text())
        for key in ('qualified', 'top'):
            for row in obj.get(key, []) or []:
                if row.get('symbol') in symbols and row.get('genome'):
                    rows.append(row)
    rows.sort(key=lambda r: float(r.get('score') or 0.0), reverse=True)
    return rows[:max_rows]


def load_seed_genomes(args) -> list[Any]:
    symbols = set(args.symbols)
    seed_rows = load_seed_rows(args.seed_scan, symbols, args.seed_rows)
    genomes = []
    seen = set()
    for row in seed_rows:
        g = v7.dict_to_genome(row['genome'])
        if not g:
            continue
        k = genome_key(g)
        if k not in seen:
            seen.add(k)
            genomes.append(g)
    for archive_path in args.extra_seed:
        for g in v7.extract_genomes_from_json(archive_path, args.archive_seed_limit):
            k = genome_key(g)
            if k not in seen:
                seen.add(k)
                genomes.append(g)
            if len(genomes) >= args.max_seeds:
                break
    return genomes[: args.max_seeds]


REGIME_DEFAULTS = {
    'TrendGate': 0.0,
    'VolGateLow': 0.0,
    'VolGateHigh': 0.08,
    'ChopGate': 30.0,
    'RegimeFireScale': 1.0,
    'MinTradeThreshold': 0.003,
    'MicroReserveRate': 0.02,
}

REGIME_BOUNDS = {
    'TrendGate': (0.0, 0.02, 0.0030),
    'VolGateLow': (0.0, 0.005, 0.0009),
    'VolGateHigh': (0.002, 0.08, 0.0120),
    'ChopGate': (0.5, 30.0, 5.0000),
    'RegimeFireScale': (0.0, 1.0, 0.1800),
    'MinTradeThreshold': (0.002, 0.12, 0.0100),
    'MicroReserveRate': (0.005, 0.35, 0.0200),
}


def _genome_dict(genome):
    d = asdict(genome) if hasattr(genome, '__dataclass_fields__') else dict(genome)
    for key, value in REGIME_DEFAULTS.items():
        d.setdefault(key, value)
    return d


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def mutate_from(genome, rng: random.Random, prob: float, scale: float):
    g = clone_genome(genome)
    mutated = v7.lab.mutate_genome(g, rng, prob=prob, scale=scale)
    return mutated if mutated is not None else g


def mutate_regime_gate(genome, rng: random.Random, args):
    d = _genome_dict(clone_genome(genome))
    changed = False
    for key, (lo, hi, sigma) in REGIME_BOUNDS.items():
        if rng.random() < args.regime_gate_prob:
            d[key] = _clamp(float(d.get(key, REGIME_DEFAULTS[key])) + rng.gauss(0.0, sigma * args.regime_gate_scale), lo, hi)
            changed = True
    if not changed:
        key = rng.choice(list(REGIME_BOUNDS))
        lo, hi, sigma = REGIME_BOUNDS[key]
        d[key] = _clamp(float(d.get(key, REGIME_DEFAULTS[key])) + rng.gauss(0.0, sigma * args.regime_gate_scale), lo, hi)
    if d['VolGateHigh'] <= d['VolGateLow'] + 0.001:
        d['VolGateHigh'] = _clamp(float(d['VolGateLow']) + 0.001, REGIME_BOUNDS['VolGateHigh'][0], REGIME_BOUNDS['VolGateHigh'][1])
    g = v7.dict_to_genome(d) or clone_genome(genome)
    if args.regime_core_prob > 0 and rng.random() < args.regime_core_mix:
        return mutate_from(g, rng, args.regime_core_prob, args.regime_core_scale)
    return g


def make_population(seeds, elites, rng: random.Random, args):
    pop = [clone_genome(g) for g in elites[: max(1, min(len(elites), args.elites))]]
    base = elites or seeds
    while len(pop) < args.population:
        roll = rng.random()
        if base and roll < args.seed_mutant_frac:
            pop.append(mutate_regime_gate(rng.choice(base), rng, args))
        elif len(base) >= 2 and roll < args.seed_mutant_frac + args.crossover_frac:
            child = v7.lab.crossover(rng.choice(base), rng.choice(base), rng)
            pop.append(mutate_regime_gate(child, rng, args))
        else:
            explorer = v7.lab.random_genome(rng)
            pop.append(mutate_regime_gate(explorer, rng, args) if rng.random() < args.explorer_regime_gate_frac else explorer)
    return pop


def _evaluate_rows(genome, scenarios: list[dict[str, Any]], args):
    rows = []
    full_count = len(scenarios)
    for sc in scenarios:
        eval_args = v7.make_eval_args(args, sc['cost_bps'])
        rng = random.Random(sc['eval_seed'])
        metrics = v7.lab.evaluate_individual(genome, sc['env'], sc['season'], sc['markets'], rng, eval_args)
        row = dict(metrics)
        row['base_score'] = float(metrics.get('score', 0.0))
        row['scenario'] = sc['scenario']
        row['cost_bps'] = sc['cost_bps']
        rows.append(row)
        if args.prune_after > 0 and len(rows) >= min(args.prune_after, full_count):
            min_alpha = min(float(r.get('min_alpha', -9.0)) for r in rows)
            failures = sum(1 for r in rows if not r.get('qualified') or float(r.get('min_alpha', -9.0)) < args.min_alpha)
            if min_alpha < args.prune_min_alpha or failures > args.prune_max_failures:
                break
    return rows


def eval_symbol(genome, symbol: str, scenarios: list[dict[str, Any]], args):
    raw_rows = _evaluate_rows(genome, scenarios, args)
    rows = [r for r in raw_rows if r.get('per_symbol')]
    sm = sv.symbol_metrics_from_rows(rows)
    full_count = max(1, len(scenarios))
    pruned = len(raw_rows) < full_count
    if pruned:
        # Pruned genomes are proven unable to pass this epoch's all-scenario gate.
        # Keep their observed tail evidence, but never mark them as qualified.
        raw_min_alpha = min(float(r.get('min_alpha', -9.0)) for r in raw_rows) if raw_rows else -9.0
        raw_min_return = min(float(r.get('min_return', -9.0)) for r in raw_rows) if raw_rows else -9.0
        raw_avg_alpha = sum(float(r.get('avg_alpha', 0.0)) for r in raw_rows) / max(1, len(raw_rows))
        raw_avg_return = sum(float(r.get('avg_return', 0.0)) for r in raw_rows) / max(1, len(raw_rows))
        raw_max_dd = max(float(r.get('max_drawdown', 0.0)) for r in raw_rows) if raw_rows else 0.0
        raw_trades = sum(int(r.get('trades', 0)) for r in raw_rows)
        sm['scenario_count'] = full_count
        sm['qualified_rows'] = min(int(sm.get('qualified_rows', 0)), len(rows))
        sm['survival_rate'] = sm['qualified_rows'] / full_count
        sm['min_alpha'] = min(float(sm.get('min_alpha', 0.0)), raw_min_alpha)
        sm['avg_alpha'] = min(float(sm.get('avg_alpha', 0.0)), raw_avg_alpha)
        sm['min_return'] = min(float(sm.get('min_return', 0.0)), raw_min_return)
        sm['avg_return'] = min(float(sm.get('avg_return', 0.0)), raw_avg_return)
        sm['max_drawdown'] = max(float(sm.get('max_drawdown', 0.0)), raw_max_dd)
        sm['trades'] = max(int(sm.get('trades', 0)), raw_trades)
        sm['pruned'] = True
        sm['pruned_rows'] = len(raw_rows)
    qualified = bool(
        not pruned
        and sm['survival_rate'] >= args.min_survival_rate
        and sm['min_alpha'] >= args.min_alpha
        and sm['min_return'] >= args.min_return
        and sm['avg_alpha'] > 0
        and sm['max_drawdown'] <= args.max_drawdown
        and sm['trades'] >= args.min_trades
        and sm['trades'] <= args.max_trades
    )
    # Balanced robustness scoring: first keep pressure toward more surviving rows,
    # but reject genomes that buy coverage with a deep left tail. This matches the
    # document rule that anti-overfit physics matters more than high average return.
    qualified_row_count = int(sm.get('qualified_rows', 0))
    scenario_count = int(sm.get('scenario_count', 0))
    missing_rows = max(0, scenario_count - qualified_row_count)
    tail_gap = max(0.0, -float(sm['min_alpha']))
    severe_tail_gap = max(0.0, tail_gap - 0.0015)
    trade_over = max(0, sm['trades'] - args.max_trades)
    trade_under = max(0, args.min_trades - sm['trades'])
    return_gap = max(0.0, args.min_return - float(sm.get('min_return', -9.0)))
    dd_excess = max(0.0, sm['max_drawdown'] - args.max_drawdown)
    # Tail-first anti-overfit score: reject low-trade fake stability and prioritize worst-case alpha.
    score = (
        qualified_row_count * 5000.0
        - missing_rows * 120000.0
        - tail_gap * 650000.0
        - severe_tail_gap * 1400000.0
        + sm['min_alpha'] * 520000.0
        + float(sm.get('min_return', -9.0)) * 180000.0
        + sm['survival_rate'] * 120.0
        + sm['avg_alpha'] * 8.0
        + float(sm.get('avg_return', -9.0)) * 4.0
        - sm['max_drawdown'] * 600.0
        - dd_excess * 700000.0
        - return_gap * 900000.0
        - trade_over * 1800.0
        - (trade_over ** 2) * 0.15
        - trade_under * 500.0
    )
    if sm['trades'] < args.min_trades:
        score -= 60000.0 + trade_under * 500.0
    if pruned:
        score -= 5000.0 + (full_count - len(raw_rows)) * 10.0
    if qualified:
        score += 10000.0
    return score, qualified, sm

def save_json(path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=v7.to_jsonable))
    tmp.replace(p)


def main() -> None:
    parser = argparse.ArgumentParser(description='Per-symbol regime-gate genome search using v7 robust scenarios')
    parser.add_argument('--seed-scan', action='append', default=[])
    parser.add_argument('--extra-seed', action='append', default=[])
    parser.add_argument('--symbols', nargs='+', default=['DOGEUSDT', 'BNBUSDT'])
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--population', type=int, default=36)
    parser.add_argument('--elites', type=int, default=8)
    parser.add_argument('--seed-rows', type=int, default=24)
    parser.add_argument('--max-seeds', type=int, default=48)
    parser.add_argument('--archive-seed-limit', type=int, default=64)
    parser.add_argument('--seed', type=int, default=7331)
    parser.add_argument('--timeframe', default='1m')
    parser.add_argument('--start', default='2017-08')
    parser.add_argument('--end', default='2026-05')
    parser.add_argument('--months-per-symbol', type=int, default=4)
    parser.add_argument('--window-bars', type=int, default=12000)
    parser.add_argument('--scenarios', type=int, default=3)
    parser.add_argument('--scenario-costs', default='20,30,50')
    parser.add_argument('--initial-cash', type=float, default=10000.0)
    parser.add_argument('--cost-bps', type=float, default=20.0)
    parser.add_argument('--lot-step', type=float, default=0.0001)
    parser.add_argument('--lot-min', type=float, default=0.0001)
    parser.add_argument('--min-notional', type=float, default=5.0)
    parser.add_argument('--drawdown-penalty', type=float, default=1.0)
    parser.add_argument('--max-drawdown', type=float, default=0.35)
    parser.add_argument('--max-trades', type=int, default=20000)
    parser.add_argument('--min-trades', type=int, default=10)
    parser.add_argument('--min-positive-alpha-frac', type=float, default=1.0)
    parser.add_argument('--min-survival-rate', type=float, default=1.0)
    parser.add_argument('--min-alpha', type=float, default=0.0)
    parser.add_argument('--min-return', type=float, default=0.0)
    parser.add_argument('--mut-prob', type=float, default=0.45)
    parser.add_argument('--mut-scale', type=float, default=0.35)
    parser.add_argument('--regime-gate-prob', type=float, default=0.85)
    parser.add_argument('--regime-gate-scale', type=float, default=1.0)
    parser.add_argument('--regime-core-prob', type=float, default=0.04)
    parser.add_argument('--regime-core-scale', type=float, default=0.006)
    parser.add_argument('--regime-core-mix', type=float, default=0.35)
    parser.add_argument('--explorer-regime-gate-frac', type=float, default=0.50)
    parser.add_argument('--seed-mutant-frac', type=float, default=0.8)
    parser.add_argument('--crossover-frac', type=float, default=0.15)
    parser.add_argument('--out', default='state/lunar_genome_symbol_local_search_v7.json')
    parser.add_argument('--prune-after', type=int, default=12)
    parser.add_argument('--prune-min-alpha', type=float, default=-0.0015)
    parser.add_argument('--prune-max-failures', type=int, default=0)
    parser.add_argument('--audit-top', type=int, default=0)
    parser.add_argument('--checkpoint-every', type=int, default=1)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    started = time.time()
    seeds = load_seed_genomes(args)
    if not seeds:
        seeds = [v7.lab.random_genome(rng) for _ in range(max(4, args.elites))]
    elites = seeds[: args.elites]
    best_rows: list[dict[str, Any]] = []
    qualified_rows: list[dict[str, Any]] = []

    for epoch in range(1, args.epochs + 1):
        scenario_cache = {sym: sv.make_symbol_scenarios(args, rng, sym) for sym in args.symbols}
        pop = make_population(seeds, elites, rng, args)
        epoch_rows = []
        for gi, genome in enumerate(pop, 1):
            for symbol in args.symbols:
                score, qualified, sm = eval_symbol(genome, symbol, scenario_cache[symbol], args)
                row = {
                    'epoch': epoch,
                    'genome_index': gi,
                    'symbol': symbol,
                    'score': score,
                    'qualified': qualified,
                    'metrics': sm,
                    'genome': v7.genome_to_dict(genome),
                }
                epoch_rows.append(row)
                if qualified:
                    qualified_rows.append(row)
        epoch_rows.sort(key=lambda r: float(r['score']), reverse=True)
        if args.audit_top > 0:
            old_prune_after = args.prune_after
            args.prune_after = 0
            audited = []
            for row in epoch_rows[:args.audit_top]:
                g = v7.dict_to_genome(row['genome'])
                if not g:
                    continue
                score, qualified, sm = eval_symbol(g, row['symbol'], scenario_cache[row['symbol']], args)
                row = dict(row)
                row['score'] = score
                row['qualified'] = qualified
                row['metrics'] = sm
                row['audit_full'] = True
                row['genome'] = v7.genome_to_dict(g)
                audited.append(row)
                if qualified:
                    qualified_rows.append(row)
            args.prune_after = old_prune_after
            epoch_rows = audited + epoch_rows[args.audit_top:]
            epoch_rows.sort(key=lambda r: float(r['score']), reverse=True)
        selected_rows = []
        selected_rows.extend(epoch_rows[: args.elites * 2])
        selected_rows.extend(sorted(epoch_rows, key=lambda r: int((r.get('metrics') or {}).get('qualified_rows', 0)), reverse=True)[: args.elites])
        selected_rows.extend(sorted(epoch_rows, key=lambda r: float((r.get('metrics') or {}).get('min_alpha', -9.0)), reverse=True)[: args.elites])
        selected_rows.extend(sorted(epoch_rows, key=lambda r: float((r.get('metrics') or {}).get('avg_alpha', -9.0)), reverse=True)[: max(1, args.elites // 2)])
        unique_selected = []
        selected_seen = set()
        for row in selected_rows:
            g = v7.dict_to_genome(row['genome'])
            if not g:
                continue
            k = genome_key(g)
            if k in selected_seen:
                continue
            selected_seen.add(k)
            unique_selected.append(row)
        best_rows.extend(unique_selected)
        best_rows.sort(key=lambda r: float(r['score']), reverse=True)
        best_rows = best_rows[:160]
        elites = []
        seen = set()
        elite_sources = []
        elite_sources.extend(best_rows)
        elite_sources.extend(sorted(best_rows, key=lambda r: int((r.get('metrics') or {}).get('qualified_rows', 0)), reverse=True))
        elite_sources.extend(sorted(best_rows, key=lambda r: float((r.get('metrics') or {}).get('min_alpha', -9.0)), reverse=True))
        for row in elite_sources:
            g = v7.dict_to_genome(row['genome'])
            k = genome_key(g)
            if k not in seen:
                seen.add(k)
                elites.append(g)
            if len(elites) >= args.elites:
                break
        best = best_rows[0]
        m = best['metrics']
        print(
            'EPOCH', epoch,
            'best', best['symbol'],
            'score', round(best['score'], 6),
            'survive', f"{m['qualified_rows']}/{m['scenario_count']}",
            'min', round(m['min_alpha'], 6),
            'avg', round(m['avg_alpha'], 6),
            'q', best['qualified'],
            flush=True,
        )
        if epoch % args.checkpoint_every == 0 or qualified_rows:
            save_json(args.out, {
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'elapsed_sec': round(time.time() - started, 3),
                'epoch': epoch,
                'symbols': args.symbols,
                'qualified_count': len(qualified_rows),
                'qualified': sorted(qualified_rows, key=lambda r: float(r['score']), reverse=True)[:50],
                'top': best_rows[:50],
            })
        if qualified_rows and args.min_survival_rate >= 1.0:
            # Keep running after a hit; later epochs may improve margin.
            pass
    save_json(args.out, {
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'elapsed_sec': round(time.time() - started, 3),
        'epoch': args.epochs,
        'symbols': args.symbols,
        'qualified_count': len(qualified_rows),
        'qualified': sorted(qualified_rows, key=lambda r: float(r['score']), reverse=True)[:50],
        'top': best_rows[:50],
    })


if __name__ == '__main__':
    main()
