#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import lunar_genome_crypto_lab_v7_robust as v7


def save_json(path: str, payload: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=v7.to_jsonable))
    tmp.replace(p)


def make_symbol_scenarios(args, rng, symbol: str):
    one = SimpleNamespace(**vars(args))
    one.symbols = [symbol]
    return v7.build_scenarios(one, rng, 1)


def symbol_metrics_from_rows(rows):
    n = max(1, len(rows))
    qualified_rows = 0
    min_alpha = 999.0
    avg_alpha = 0.0
    min_return = 999.0
    avg_return = 0.0
    max_dd = 0.0
    trade_values = []
    details = []
    regime_counts = {}
    regime_trades = {}
    router_active_fracs = []
    for r in rows:
        per = r.get('per_symbol') or {}
        # Single-symbol scenarios should have exactly one entry.
        sym, sm = next(iter(per.items()))
        alpha = float(sm.get('alpha_vs_ghost', sm.get('alpha', 0.0)))
        net_return = float(sm.get('return', sm.get('strategy_return', 0.0)))
        dd = float(sm.get('max_drawdown', sm.get('drawdown', r.get('max_drawdown', 0.0))))
        tr = int(sm.get('trades', r.get('trades', 0)))
        avg_alpha += alpha
        avg_return += net_return
        min_alpha = min(min_alpha, alpha)
        min_return = min(min_return, net_return)
        max_dd = max(max_dd, dd)
        trade_values.append(tr)
        for key, value in (sm.get('regime_counts') or {}).items():
            regime_counts[key] = regime_counts.get(key, 0) + int(value)
        for key, value in (sm.get('regime_trades') or {}).items():
            regime_trades[key] = regime_trades.get(key, 0) + int(value)
        router_active_fracs.append(float(sm.get('router_active_frac', 1.0)))
        row_ok = bool(alpha >= 0.0 and net_return >= 0.0 and dd <= 0.35 and tr >= 1)
        qualified_rows += 1 if row_ok else 0
        details.append({
            'scenario': r.get('scenario'),
            'cost_bps': r.get('cost_bps'),
            'symbol': sym,
            'alpha': alpha,
            'return': net_return,
            'max_drawdown': dd,
            'trades': tr,
            'qualified': row_ok,
        })
    avg_alpha /= n
    avg_return /= n
    survival_rate = qualified_rows / n
    trade_total = sum(trade_values)
    min_trades_per_scenario = min(trade_values) if trade_values else 0
    max_trades_per_scenario = max(trade_values) if trade_values else 0
    avg_trades_per_scenario = trade_total / n
    router_active_frac = sum(router_active_fracs) / max(1, len(router_active_fracs))
    dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else 'neutral'
    return {
        'qualified_rows': qualified_rows,
        'scenario_count': n,
        'survival_rate': survival_rate,
        'min_alpha': min_alpha if min_alpha != 999.0 else 0.0,
        'avg_alpha': avg_alpha,
        'min_return': min_return if min_return != 999.0 else 0.0,
        'avg_return': avg_return,
        'max_drawdown': max_dd,
        # ``trades`` is intentionally a per-scenario average for gate checks.
        # The old aggregate value is kept as ``trade_total`` for audit output.
        'trades': avg_trades_per_scenario,
        'trade_total': trade_total,
        'min_trades_per_scenario': min_trades_per_scenario,
        'max_trades_per_scenario': max_trades_per_scenario,
        'avg_trades_per_scenario': avg_trades_per_scenario,
        'regime_counts': regime_counts,
        'regime_trades': regime_trades,
        'router_active_frac': router_active_frac,
        'dominant_regime': dominant_regime,
        'details': details,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--limit', type=int, default=60)
    ap.add_argument('--latest', action='store_true')
    ap.add_argument('--seed', type=int, default=20260702)
    ap.add_argument('--symbols', nargs='+', default=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','ADAUSDT','DOGEUSDT','LINKUSDT','AVAXUSDT','DOTUSDT'])
    ap.add_argument('--timeframe', default='1m')
    ap.add_argument('--start', default='2017-08')
    ap.add_argument('--end', default='2026-05')
    ap.add_argument('--months-per-symbol', type=int, default=6)
    ap.add_argument('--window-bars', type=int, default=18000)
    ap.add_argument('--scenarios', type=int, default=5)
    ap.add_argument('--scenario-costs', default='20,30,50')
    ap.add_argument('--initial-cash', type=float, default=10000.0)
    ap.add_argument('--lot-step', type=float, default=0.0001)
    ap.add_argument('--lot-min', type=float, default=0.0001)
    ap.add_argument('--min-notional', type=float, default=10.0)
    ap.add_argument('--drawdown-penalty', type=float, default=18.0)
    ap.add_argument('--max-drawdown', type=float, default=0.35)
    ap.add_argument('--max-trades', type=int, default=20000)
    ap.add_argument('--min-trades', type=int, default=1)
    ap.add_argument('--min-positive-alpha-frac', type=float, default=1.0)
    ap.add_argument('--min-alpha', type=float, default=0.0)
    ap.add_argument('--min-return', type=float, default=0.0)
    ap.add_argument('--min-survival-rate', type=float, default=1.0)
    args = ap.parse_args()

    started = time.time()
    rng = random.Random(args.seed)
    genomes = v7.extract_genomes_from_json(args.archive, max(args.limit * 3, args.limit))
    genomes = genomes[-args.limit:] if args.latest else genomes[:args.limit]
    results = []
    scenario_cache = {}

    for symbol in args.symbols:
        scenario_cache[symbol] = make_symbol_scenarios(args, rng, symbol)

    for gi, genome in enumerate(genomes, 1):
        for symbol in args.symbols:
            score, metrics = v7.robust_evaluate(genome, scenario_cache[symbol], args)
            sm = symbol_metrics_from_rows(metrics.get('rows') or [])
            qualified = bool(
                sm['survival_rate'] >= args.min_survival_rate
                and sm['min_alpha'] >= args.min_alpha
                and sm['min_return'] >= args.min_return
                and sm['avg_alpha'] > 0
                and sm['max_drawdown'] <= args.max_drawdown
                and sm['avg_trades_per_scenario'] >= args.min_trades
                and sm['max_trades_per_scenario'] <= args.max_trades
            )
            # Favor stable positive alpha over sparse single-window spikes.
            symbol_score = (
                sm['survival_rate'] * 1000.0
                + sm['min_alpha'] * 700.0
                + sm['min_return'] * 350.0
                + sm['avg_alpha'] * 250.0
                + sm['avg_return'] * 120.0
                - max(0.0, sm['max_drawdown'] - args.max_drawdown) * 300.0
                - max(0.0, args.min_return - sm['min_return']) * 600.0
            )
            row = {
                'genome_index': gi,
                'symbol': symbol,
                'score': symbol_score,
                'qualified': qualified,
                'metrics': sm,
                'genome': v7.genome_to_dict(genome),
            }
            results.append(row)
        if gi % 5 == 0 or gi == len(genomes):
            best = max(results, key=lambda x: x['score'])
            print('CHECKED', gi, 'best', best['symbol'], 'score', round(best['score'], 6), 'survive', f"{best['metrics']['qualified_rows']}/{best['metrics']['scenario_count']}", 'min', round(best['metrics']['min_alpha'], 6), 'avg', round(best['metrics']['avg_alpha'], 6), 'q', best['qualified'], flush=True)

    results.sort(key=lambda x: x['score'], reverse=True)
    qualified = [r for r in results if r['qualified']]
    payload = {
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'args': vars(args),
        'elapsed_sec': round(time.time() - started, 3),
        'candidate_count': len(genomes),
        'symbol_candidate_count': len(results),
        'qualified_count': len(qualified),
        'qualified': qualified[:50],
        'top': results[:50],
    }
    save_json(args.out, payload)
    best = results[0] if results else {'metrics': {}}
    m = best['metrics']
    print('DONE', json.dumps({
        'out': args.out,
        'candidate_count': payload['candidate_count'],
        'symbol_candidate_count': payload['symbol_candidate_count'],
        'qualified_count': payload['qualified_count'],
        'best_symbol': best.get('symbol'),
        'best_survival': m.get('qualified_rows'),
        'best_scenario_count': m.get('scenario_count'),
        'best_min_alpha': m.get('min_alpha'),
        'best_avg_alpha': m.get('avg_alpha'),
        'best_min_return': m.get('min_return'),
        'best_avg_return': m.get('avg_return'),
        'best_qualified': best.get('qualified'),
    }, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
