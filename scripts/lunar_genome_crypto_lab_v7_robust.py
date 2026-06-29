#!/usr/bin/env python3
"""Robust LunarGenome evolution for Binance crypto klines.

This runner keeps the v6 trading physics, but makes fitness depend on a
bundle of random public-Binance scenarios instead of one historical slice.
A candidate is useful only when it survives costs, months, symbols, and
frozen environment changes at the same time.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v6 as lab  # noqa: E402
import data_health_gate as dhg  # noqa: E402

GENOME_FIELDS = {f.name for f in fields(lab.LunarGenome)}


def parse_costs(raw: str) -> list[float]:
    costs = []
    for part in raw.split(','):
        part = part.strip()
        if part:
            costs.append(float(part))
    if not costs:
        raise ValueError('at least one cost is required')
    return costs


def genome_to_dict(genome: lab.LunarGenome) -> dict[str, Any]:
    if is_dataclass(genome):
        return asdict(genome)
    return dict(genome)


def dict_to_genome(obj: dict[str, Any]) -> lab.LunarGenome | None:
    if not isinstance(obj, dict):
        return None
    data = lab.with_gene_defaults(obj) if hasattr(lab, 'with_gene_defaults') else dict(obj)
    data = {k: data[k] for k in GENOME_FIELDS if k in data}
    if len(data) != len(GENOME_FIELDS):
        return None
    return lab.LunarGenome(**data)


def walk_dicts(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_dicts(value)


def extract_genomes_from_json(path: str | None, limit: int) -> list[lab.LunarGenome]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        print('seed_missing', path)
        return []
    try:
        obj = json.loads(p.read_text())
    except Exception as exc:
        print('seed_load_error', path, exc)
        return []
    genomes: list[lab.LunarGenome] = []
    seen: set[str] = set()
    for d in walk_dicts(obj):
        candidate = d.get('genome') if isinstance(d.get('genome'), dict) else d
        g = dict_to_genome(candidate)
        if g is None:
            continue
        key = json.dumps(genome_to_dict(g), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        genomes.append(g)
        if len(genomes) >= limit:
            break
    return genomes


def make_eval_args(args: argparse.Namespace, cost_bps: float) -> SimpleNamespace:
    return SimpleNamespace(
        initial_cash=args.initial_cash,
        cost_bps=cost_bps,
        lot_step=args.lot_step,
        lot_min=args.lot_min,
        min_notional=args.min_notional,
        drawdown_penalty=args.drawdown_penalty,
        max_drawdown=args.max_drawdown,
        max_trades=args.max_trades,
        min_trades=args.min_trades,
        min_positive_alpha_frac=args.min_positive_alpha_frac,
        min_alpha=args.min_alpha,
        min_return=getattr(args, 'min_return', 0.0),
        timeframe=args.timeframe,
        window_bars=args.window_bars,
        signal_delay_bars=getattr(args, 'signal_delay_bars', 0),
    )


def prepare_public_months_with_data_gate(args: argparse.Namespace, rng: random.Random, months: list[str]) -> tuple[dict[str, list[Path]], dict[str, Any]]:
    gate = dhg.build_gate_from_args(args)
    audit_hash = getattr(args, "data_audit_summary_hash", None)
    if not gate.enabled:
        selected = lab.prepare_public_months(args.symbols, args.timeframe, months, args.months_per_symbol, rng)
        result = gate.summarize(list(args.symbols), months, audit_hash)
        return selected, gate.to_jsonable(result)

    selected: dict[str, list[Path]] = {}
    result = gate.summarize(list(args.symbols), months, audit_hash)
    for symbol in result.allowed_symbols:
        valid_months = gate.valid_months(symbol, months)
        blocks = [block for block in dhg.contiguous_blocks(valid_months) if len(block) >= args.months_per_symbol]
        if not blocks:
            result.blocked_symbols[symbol] = f"no_contiguous_valid_block_{args.months_per_symbol}_months"
            continue
        choices = []
        for block in blocks:
            for start_idx in range(0, len(block) - args.months_per_symbol + 1):
                choices.append(block[start_idx:start_idx + args.months_per_symbol])
        picked = rng.choice(choices)
        cache_dir = Path(getattr(args, "data_cache_dir", ROOT / "data" / "binance_public_cache"))
        paths = [cache_dir / f"{symbol}_{args.timeframe}_{month}.parquet" for month in picked]
        missing_paths = [str(path) for path in paths if not path.exists()]
        if missing_paths:
            result.blocked_symbols[symbol] = "scenario_selected_missing_cache_files"
            continue
        selected[symbol] = paths

    result.allowed_symbols = sorted(selected)
    if not selected:
        raise SystemExit(
            "data_health_gate_rejected_all_symbols "
            + json.dumps(gate.to_jsonable(result), ensure_ascii=False, sort_keys=True)
        )
    return selected, gate.to_jsonable(result)


def build_scenarios(args: argparse.Namespace, rng: random.Random, epoch: int) -> list[dict[str, Any]]:
    costs = parse_costs(args.scenario_costs)
    months = lab.month_range(args.start, args.end)
    scenarios = []
    for idx in range(args.scenarios):
        selected, data_gate = prepare_public_months_with_data_gate(args, rng, months)
        markets = lab.load_markets(selected, args.timeframe)
        env = lab.sample_environment(rng)
        season = lab.sample_season(rng)
        for cost in costs:
            scenarios.append({
                'epoch': epoch,
                'scenario': idx + 1,
                'cost_bps': cost,
                'selected': {k: [Path(p).name.rsplit('_', 1)[-1].replace('.parquet', '') for p in v] for k, v in selected.items()},
                'data_gate': data_gate,
                'markets': markets,
                'env': env,
                'season': season,
                'eval_seed': rng.randrange(1, 2**31 - 1),
            })
    return scenarios


def robust_evaluate(genome: lab.LunarGenome, scenarios: list[dict[str, Any]], args: argparse.Namespace) -> tuple[float, dict[str, Any]]:
    rows = []
    for sc in scenarios:
        eval_args = make_eval_args(args, sc['cost_bps'])
        rng = random.Random(sc['eval_seed'])
        metrics = lab.evaluate_individual(genome, sc['env'], sc['season'], sc['markets'], rng, eval_args)
        score = float(metrics.get('score', 0.0))
        row = dict(metrics)
        row['base_score'] = score
        row['scenario'] = sc['scenario']
        row['cost_bps'] = sc['cost_bps']
        rows.append(row)

    n = max(1, len(rows))
    survival = sum(1 for r in rows if r.get('qualified'))
    positive_rates = [r.get('positive_alpha_symbols', 0) / max(1, r.get('symbols_tested', 1)) for r in rows]
    min_alphas = [float(r.get('min_alpha', -9.0)) for r in rows]
    avg_alphas = [float(r.get('avg_alpha', 0.0)) for r in rows]
    min_returns = [float(r.get('min_return', -9.0)) for r in rows]
    avg_returns = [float(r.get('avg_return', 0.0)) for r in rows]
    max_dds = [float(r.get('max_drawdown', 0.0)) for r in rows]
    trades = [int(r.get('trades', 0)) for r in rows]
    sorted_min_alphas = sorted(min_alphas)
    sorted_min_returns = sorted(min_returns)
    p05_idx = max(0, int(0.05 * (len(sorted_min_alphas) - 1))) if sorted_min_alphas else 0
    p05_alpha = sorted_min_alphas[p05_idx] if sorted_min_alphas else -9.0
    p05_return = sorted_min_returns[p05_idx] if sorted_min_returns else -9.0
    negative_alpha_tail = [x for x in min_alphas if x < args.min_alpha]
    expected_shortfall_alpha = (
        sum(args.min_alpha - x for x in negative_alpha_tail) / max(1, len(negative_alpha_tail))
    )
    trade_concentration = max(trades) / max(1, sum(trades)) if trades else 1.0

    survival_rate = survival / n
    worst_min_alpha = min(min_alphas) if min_alphas else -9.0
    avg_min_alpha = sum(min_alphas) / n
    avg_alpha = sum(avg_alphas) / n
    worst_min_return = min(min_returns) if min_returns else -9.0
    avg_return = sum(avg_returns) / n
    min_pos_frac = min(positive_rates) if positive_rates else 0.0
    max_dd = max(max_dds) if max_dds else 0.0
    avg_trades = sum(trades) / n

    shortfall = max(0.0, args.min_alpha - worst_min_alpha)
    return_shortfall = max(0.0, getattr(args, 'min_return', 0.0) - worst_min_return)
    pos_shortfall = max(0.0, args.min_positive_alpha_frac - min_pos_frac)
    dd_excess = max(0.0, max_dd - args.max_drawdown)
    trade_shortfall = max(0.0, args.min_trades - avg_trades) / max(1, args.min_trades)

    robust_score = (
        survival_rate * 1000.0
        + worst_min_alpha * 360.0
        + p05_alpha * 160.0
        + avg_min_alpha * 180.0
        + avg_alpha * 90.0
        + worst_min_return * 170.0
        + p05_return * 80.0
        + avg_return * 80.0
        + min_pos_frac * 90.0
        - shortfall * 600.0
        - return_shortfall * 700.0
        - expected_shortfall_alpha * 500.0
        - pos_shortfall * 160.0
        - dd_excess * 220.0
        - trade_shortfall * 80.0
        - trade_concentration * 25.0
    )

    qualified = bool(
        survival == n
        and worst_min_alpha >= args.min_alpha
        and worst_min_return >= getattr(args, 'min_return', 0.0)
        and min_pos_frac >= args.min_positive_alpha_frac
        and max_dd <= args.max_drawdown
        and avg_trades >= args.min_trades
    )

    metrics = {
        'qualified': qualified,
        'survival': survival,
        'scenario_count': n,
        'survival_rate': survival_rate,
        'worst_min_alpha': worst_min_alpha,
        'p05_alpha': p05_alpha,
        'expected_shortfall_alpha': expected_shortfall_alpha,
        'avg_min_alpha': avg_min_alpha,
        'avg_alpha': avg_alpha,
        'worst_min_return': worst_min_return,
        'p05_return': p05_return,
        'avg_return': avg_return,
        'min_positive_alpha_frac': min_pos_frac,
        'max_drawdown': max_dd,
        'avg_trades': avg_trades,
        'trade_concentration': trade_concentration,
        'rows': rows,
    }
    return robust_score, metrics



def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, 'item'):
        try:
            return obj.item()
        except Exception:
            pass
    if hasattr(obj, 'tolist'):
        try:
            return obj.tolist()
        except Exception:
            pass
    return str(obj)


def add_archive_genome(archive: list[lab.LunarGenome], genome: lab.LunarGenome, seen: set[str], limit: int) -> bool:
    key = json.dumps(genome_to_dict(genome), sort_keys=True)
    if key in seen:
        return False
    seen.add(key)
    archive.append(genome)
    if len(archive) > limit:
        del archive[:-limit]
    return True

def save_json(path: str, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=to_jsonable))
    tmp.replace(p)


def write_progress(args: argparse.Namespace, epoch: int, gen: int, best: lab.Individual, challengers: list[lab.Individual], started: float) -> None:
    payload = {
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'epoch': epoch,
        'generation': gen,
        'elapsed_sec': round(time.time() - started, 3),
        'best': {
            'score': best.score,
            'metrics': best.metrics,
            'genome': genome_to_dict(best.genome),
        },
        'challenger_count': len(challengers),
    }
    save_json(args.out + '.progress', payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='+', default=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','ADAUSDT','DOGEUSDT','LINKUSDT','AVAXUSDT','DOTUSDT'])
    parser.add_argument('--timeframe', default='1m')
    parser.add_argument('--start', default='2017-08')
    parser.add_argument('--end', default='2026-05')
    parser.add_argument('--epochs', type=int, default=1)
    parser.add_argument('--generations', type=int, default=8)
    parser.add_argument('--population', type=int, default=32)
    parser.add_argument('--archive', default='state/lunar_genome_archive_v7_robust.json')
    parser.add_argument('--archive-limit', type=int, default=64)
    parser.add_argument('--keep-top', type=int, default=6)
    parser.add_argument('--checkpoint-every', type=int, default=1)
    parser.add_argument('--extra-seed', action='append', default=[])
    parser.add_argument('--out', default='state/lunar_genome_crypto_lab_v7_robust.json')
    parser.add_argument('--seed', type=int, default=20260629)
    parser.add_argument('--months-per-symbol', type=int, default=4)
    parser.add_argument('--window-bars', type=int, default=25000)
    parser.add_argument('--scenarios', type=int, default=4)
    parser.add_argument('--scenario-costs', default='20,30,50')
    parser.add_argument('--data-manifest-dir', default='')
    parser.add_argument('--data-cache-dir', default=str(ROOT / 'data' / 'binance_public_cache'))
    parser.add_argument('--data-audit-summary-hash', default='')
    parser.add_argument('--elite-ratio', type=float, default=0.18)
    parser.add_argument('--mut-prob', type=float, default=0.35)
    parser.add_argument('--mut-scale', type=float, default=0.22)
    parser.add_argument('--initial-cash', type=float, default=10000.0)
    parser.add_argument('--cost-bps', type=float, default=20.0)
    parser.add_argument('--lot-step', type=float, default=0.0001)
    parser.add_argument('--lot-min', type=float, default=0.0001)
    parser.add_argument('--min-notional', type=float, default=10.0)
    parser.add_argument('--drawdown-penalty', type=float, default=18.0)
    parser.add_argument('--max-drawdown', type=float, default=0.35)
    parser.add_argument('--max-trades', type=int, default=20000)
    parser.add_argument('--min-trades', type=int, default=10)
    parser.add_argument('--min-positive-alpha-frac', type=float, default=1.0)
    parser.add_argument('--min-alpha', type=float, default=0.0)
    parser.add_argument('--min-return', type=float, default=0.0)
    args = parser.parse_args()

    started = time.time()
    rng = random.Random(args.seed)
    archive = lab.load_archive(args.archive, args.archive_limit)
    archive_seen: set[str] = set()
    deduped_archive: list[lab.LunarGenome] = []
    for g in archive:
        add_archive_genome(deduped_archive, g, archive_seen, args.archive_limit)
    archive = deduped_archive
    for seed_path in args.extra_seed:
        for g in extract_genomes_from_json(seed_path, args.archive_limit):
            add_archive_genome(archive, g, archive_seen, args.archive_limit)

    challengers: list[lab.Individual] = []
    global_best: lab.Individual | None = None
    scenario_manifest = []

    for epoch in range(1, args.epochs + 1):
        scenarios = build_scenarios(args, rng, epoch)
        scenario_manifest.append([
            {k: v for k, v in sc.items() if k not in ('markets',)}
            for sc in scenarios
        ])
        pop = lab.make_population(rng, args.population, archive)
        print('epoch', epoch, 'scenarios', len(scenarios), 'costs', args.scenario_costs, flush=True)

        for gen in range(1, args.generations + 1):
            for ind in pop:
                score, metrics = robust_evaluate(ind.genome, scenarios, args)
                ind.score = score
                ind.metrics = metrics
            pop.sort(key=lambda x: x.score, reverse=True)
            best = pop[0]
            if global_best is None or best.score > global_best.score:
                global_best = copy.deepcopy(best)
            for elite in pop[:max(1, args.keep_top)]:
                add_archive_genome(archive, copy.deepcopy(elite.genome), archive_seen, args.archive_limit)
            if best.metrics.get('qualified'):
                challengers.append(copy.deepcopy(best))
            if args.checkpoint_every > 0 and gen % args.checkpoint_every == 0:
                save_json(args.archive, {
                    'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'checkpoint': True,
                    'epoch': epoch,
                    'generation': gen,
                    'genomes': [genome_to_dict(g) for g in archive[-args.archive_limit:]],
                })
            print(
                'GEN', epoch, gen,
                'score', round(best.score, 6),
                'survive', f"{best.metrics['survival']}/{best.metrics['scenario_count']}",
                'worst_min', round(best.metrics['worst_min_alpha'], 6),
                'avg_alpha', round(best.metrics['avg_alpha'], 6),
                'min_pos', round(best.metrics['min_positive_alpha_frac'], 3),
                'dd', round(best.metrics['max_drawdown'], 4),
                'q', best.metrics.get('qualified'),
                flush=True,
            )
            write_progress(args, epoch, gen, best, challengers, started)
            pop = lab.next_generation(pop, rng, args.population, args.elite_ratio, args.mut_prob, args.mut_scale)

    archive_payload = []
    for genome in archive[-args.archive_limit:]:
        archive_payload.append(genome_to_dict(genome))
    save_json(args.archive, {'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'genomes': archive_payload})

    result = {
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'args': vars(args),
        'elapsed_sec': round(time.time() - started, 3),
        'best': None if global_best is None else {
            'score': global_best.score,
            'metrics': global_best.metrics,
            'genome': genome_to_dict(global_best.genome),
        },
        'challenger_count': len(challengers),
        'challengers': [
            {'score': c.score, 'metrics': c.metrics, 'genome': genome_to_dict(c.genome)}
            for c in challengers[-20:]
        ],
        'scenario_manifest': scenario_manifest,
    }
    save_json(args.out, result)

    best_metrics = {} if global_best is None else global_best.metrics
    print('DONE', json.dumps({
        'out': args.out,
        'archive': args.archive,
        'challenger_count': len(challengers),
        'best_survival': best_metrics.get('survival'),
        'best_scenario_count': best_metrics.get('scenario_count'),
        'best_worst_min_alpha': best_metrics.get('worst_min_alpha'),
        'best_avg_alpha': best_metrics.get('avg_alpha'),
        'best_qualified': best_metrics.get('qualified'),
    }, ensure_ascii=False, default=to_jsonable), flush=True)


if __name__ == '__main__':
    main()
