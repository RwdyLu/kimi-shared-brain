#!/usr/bin/env python3
import argparse, json, math, random, time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from core_evolution_gate_v3 import ROOT, STATE_DIR, LOG_DIR, month_range, prepare_public_months, load_markets
import multiprocessing as mp


@dataclass
class Environment:
    DeadReserveRatio: float
    GlobalStopLoss: float
    MaxLeverage: float = 1.0


@dataclass
class Season:
    winter: float
    spring: float
    summer: float
    autumn: float
    tick_offset: int = 0


@dataclass
class LunarGenome:
    # Macro Genes
    MaxDCAMonths: int
    BetaThreshold: float
    MoonPhasePressure: float
    DeadlineForcePct: float
    GCThresholdMonths: int
    GCMaxRatio: float
    TMacro: int
    TMicro: int
    TDeadline: int
    EMAAnchor: int
    # Micro PDE Genes
    kp: float
    kv: float
    ka: float
    MinTradeThreshold: float
    MicroReserveRate: float
    SigmoidScale: float
    Gamma: float
    Beta: float
    TrendGate: float = 0.0
    VolGateLow: float = 0.0
    VolGateHigh: float = 0.08
    ChopGate: float = 30.0
    RegimeFireScale: float = 1.0
    RegimeRouterBlend: float = 0.0
    UpTrendFireScale: float = 1.0
    DownTrendFireScale: float = 1.0
    ChopFireScale: float = 1.0
    HighVolFireScale: float = 1.0
    LowVolFireScale: float = 1.0
    RegimeMinCoverage: float = 0.02


@dataclass
class Individual:
    genome: LunarGenome
    score: float = None
    metrics: dict = None


BOUNDS = {
    'MaxDCAMonths': (3, 36, int),
    'BetaThreshold': (0.03, 0.45, float),
    'MoonPhasePressure': (0.0, 1.0, float),
    'DeadlineForcePct': (0.0, 0.35, float),
    'GCThresholdMonths': (3, 48, int),
    'GCMaxRatio': (0.0, 0.45, float),
    'TMacro': (240, 1440 * 7, int),
    'TMicro': (1, 30, int),
    'TDeadline': (1440 * 7, 1440 * 90, int),
    'EMAAnchor': (120, 1440 * 45, int),
    'kp': (-4.0, 4.0, float),
    'kv': (-8.0, 8.0, float),
    'ka': (-12.0, 12.0, float),
    'MinTradeThreshold': (0.002, 0.12, float),
    'MicroReserveRate': (0.005, 0.35, float),
    'SigmoidScale': (0.5, 12.0, float),
    'Gamma': (0.1, 4.0, float),
    'Beta': (0.1, 4.0, float),
    'TrendGate': (0.0, 0.02, float),
    'VolGateLow': (0.0, 0.005, float),
    'VolGateHigh': (0.002, 0.08, float),
    'ChopGate': (0.5, 30.0, float),
    'RegimeFireScale': (0.0, 1.0, float),
    'RegimeRouterBlend': (0.0, 1.0, float),
    'UpTrendFireScale': (0.0, 1.5, float),
    'DownTrendFireScale': (0.0, 1.2, float),
    'ChopFireScale': (0.0, 1.0, float),
    'HighVolFireScale': (0.0, 1.0, float),
    'LowVolFireScale': (0.0, 1.2, float),
    'RegimeMinCoverage': (0.02, 0.35, float),
}


OPTIONAL_GENE_DEFAULTS = {
    'TrendGate': 0.0,
    'VolGateLow': 0.0,
    'VolGateHigh': 0.08,
    'ChopGate': 30.0,
    'RegimeFireScale': 1.0,
    'RegimeRouterBlend': 0.0,
    'UpTrendFireScale': 1.0,
    'DownTrendFireScale': 1.0,
    'ChopFireScale': 1.0,
    'HighVolFireScale': 1.0,
    'LowVolFireScale': 1.0,
    'RegimeMinCoverage': 0.02,
}


def with_gene_defaults(genome_or_dict):
    d = asdict(genome_or_dict) if hasattr(genome_or_dict, '__dataclass_fields__') else dict(genome_or_dict)
    for k, v in OPTIONAL_GENE_DEFAULTS.items():
        d.setdefault(k, v)
    return d


def clip_gene(name, value):
    lo, hi, typ = BOUNDS[name]
    value = max(lo, min(hi, value))
    if typ is int:
        return int(round(value))
    return float(value)


def random_genome(rng):
    vals = {}
    for k, (lo, hi, typ) in BOUNDS.items():
        if typ is int:
            vals[k] = rng.randint(lo, hi)
        else:
            vals[k] = rng.uniform(lo, hi)
    return LunarGenome(**vals)


def mutate_genome(g, rng, prob=0.15, scale=1.0):
    d = with_gene_defaults(g)
    for k, (lo, hi, typ) in BOUNDS.items():
        if rng.random() < prob:
            sigma = (hi - lo) * 0.08 * scale
            d[k] = clip_gene(k, d[k] + rng.gauss(0, sigma))
    return LunarGenome(**d)


def crossover(a, b, rng):
    da = with_gene_defaults(a)
    db = with_gene_defaults(b)
    # Orthogonal block crossover: macro timing / macro risk / PDE sensing / fire control.
    blocks = [
        ['MaxDCAMonths','BetaThreshold','MoonPhasePressure','DeadlineForcePct','GCThresholdMonths','GCMaxRatio'],
        ['TMacro','TMicro','TDeadline','EMAAnchor'],
        ['kp','kv','ka'],
        ['MinTradeThreshold','MicroReserveRate','SigmoidScale','Gamma','Beta'],
        ['TrendGate','VolGateLow','VolGateHigh','ChopGate','RegimeFireScale'],
        ['RegimeRouterBlend','UpTrendFireScale','DownTrendFireScale','ChopFireScale','HighVolFireScale','LowVolFireScale','RegimeMinCoverage'],
    ]
    child = {}
    for block in blocks:
        src = da if rng.random() < 0.5 else db
        for k in block:
            child[k] = src[k]
    return LunarGenome(**child)


def sample_environment(rng):
    # Truncated-normal style around conservative anchors. MaxLeverage fixed at 1 for spot.
    def trunc(mu, sigma, lo, hi):
        for _ in range(50):
            x = rng.gauss(mu, sigma)
            if lo <= x <= hi:
                return x
        return max(lo, min(hi, mu))
    return Environment(
        DeadReserveRatio=trunc(0.18, 0.04, 0.02, 0.40),
        GlobalStopLoss=trunc(0.35, 0.08, 0.10, 0.80),
        MaxLeverage=1.0,
    )


def sample_season(rng):
    # Four categorical levels from low to high; normal/medium weighted higher.
    levels = [0.55, 0.85, 1.0, 1.25, 1.55]
    weights = [0.10, 0.25, 0.35, 0.20, 0.10]
    def pick():
        return rng.choices(levels, weights=weights, k=1)[0]
    vals = sorted([pick(), pick(), pick(), pick()])
    return Season(winter=vals[0], spring=vals[1], summer=vals[2], autumn=vals[3], tick_offset=0)


def rolling_ema(a, span):
    return pd.Series(a).ewm(span=max(2, int(span)), adjust=False).mean().to_numpy(dtype=np.float64)


def max_drawdown(equity):
    arr = np.asarray(equity, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    peak = np.maximum.accumulate(arr)
    dd = (peak - arr) / np.maximum(peak, 1e-9)
    return float(np.nanmax(dd))


def normalize_order_qty(notional, price, lot_step, lot_min, min_notional):
    if price <= 0 or notional < min_notional:
        return 0.0
    qty = notional / price
    qty = math.floor(qty / lot_step) * lot_step
    if qty < lot_min or qty * price < min_notional:
        return 0.0
    return qty


def season_mult(season, i, n):
    q = i / max(1, n)
    if q < 0.25:
        return season.winter
    if q < 0.50:
        return season.spring
    if q < 0.75:
        return season.summer
    return season.autumn


def timeframe_minutes(timeframe):
    raw = str(timeframe or '1m').strip().lower()
    if raw.endswith('m'):
        return max(1, int(raw[:-1]))
    if raw.endswith('h'):
        return max(1, int(raw[:-1]) * 60)
    if raw.endswith('d'):
        return max(1, int(raw[:-1]) * 1440)
    return 1


def scale_genome_for_timeframe(genome, timeframe):
    minutes = timeframe_minutes(timeframe)
    if minutes <= 1:
        return genome
    d = with_gene_defaults(genome)
    for key in ['TMacro', 'TMicro', 'TDeadline', 'EMAAnchor']:
        d[key] = max(1, int(round(d[key] / minutes)))
    d['EMAAnchor'] = max(2, d['EMAAnchor'])
    if minutes >= 240:
        d['TMacro'] = max(d['TMacro'], 6)
        d['TMicro'] = max(d['TMicro'], 3)
        d['TDeadline'] = max(d['TDeadline'], 42)
        d['MinTradeThreshold'] = max(float(d['MinTradeThreshold']), 0.035)
        d['MicroReserveRate'] = min(float(d['MicroReserveRate']), 0.08)
    elif minutes >= 60:
        d['TMacro'] = max(d['TMacro'], 12)
        d['TMicro'] = max(d['TMicro'], 4)
        d['TDeadline'] = max(d['TDeadline'], 96)
        d['MinTradeThreshold'] = max(float(d['MinTradeThreshold']), 0.025)
        d['MicroReserveRate'] = min(float(d['MicroReserveRate']), 0.12)
    elif minutes >= 15:
        d['TMacro'] = max(d['TMacro'], 16)
        d['TMicro'] = max(d['TMicro'], 8)
        d['TDeadline'] = max(d['TDeadline'], 192)
        d['MinTradeThreshold'] = max(float(d['MinTradeThreshold']), 0.015)
        d['MicroReserveRate'] = min(float(d['MicroReserveRate']), 0.18)
    elif minutes >= 5:
        d['TMacro'] = max(d['TMacro'], 24)
        d['TMicro'] = max(d['TMicro'], 12)
        d['TDeadline'] = max(d['TDeadline'], 288)
        d['MinTradeThreshold'] = max(float(d['MinTradeThreshold']), 0.010)
        d['MicroReserveRate'] = min(float(d['MicroReserveRate']), 0.24)
    return LunarGenome(**d)


def clamp01(value):
    return max(0.0, min(1.0, float(value)))


def clamp_route(value):
    return max(0.0, min(1.5, float(value)))


def regime_route(genome, pos_term, vel_value, acc_value):
    """Return a causal market-regime label and strategy fire multiplier.

    All inputs are derived from the previous completed bar. This keeps the
    regime genome from seeing future price action while still allowing the
    policy genome to specialize behavior by market state.
    """
    vol_proxy = abs(vel_value) + abs(acc_value)
    trend_proxy = abs(pos_term) + abs(vel_value)
    chop_proxy = abs(acc_value) / max(abs(vel_value), 1e-9)

    legacy_multiplier = 1.0
    if trend_proxy < genome.TrendGate:
        legacy_multiplier *= genome.RegimeFireScale
    if vol_proxy < genome.VolGateLow or vol_proxy > genome.VolGateHigh:
        legacy_multiplier *= genome.RegimeFireScale
    if chop_proxy > genome.ChopGate:
        legacy_multiplier *= genome.RegimeFireScale

    label = 'neutral'
    route_multiplier = 1.0
    if chop_proxy > genome.ChopGate:
        label = 'chop'
        route_multiplier = genome.ChopFireScale
    elif vol_proxy > genome.VolGateHigh:
        label = 'high_vol'
        route_multiplier = genome.HighVolFireScale
    elif vol_proxy < genome.VolGateLow:
        label = 'low_vol'
        route_multiplier = genome.LowVolFireScale
    elif pos_term > genome.TrendGate and vel_value >= 0:
        label = 'trend_up'
        route_multiplier = genome.UpTrendFireScale
    elif pos_term < -genome.TrendGate and vel_value <= 0:
        label = 'trend_down'
        route_multiplier = genome.DownTrendFireScale

    blend = clamp01(genome.RegimeRouterBlend)
    policy_multiplier = (1.0 - blend) + blend * clamp_route(route_multiplier)
    combined_multiplier = clamp_route(legacy_multiplier * policy_multiplier)
    return {
        'label': label,
        'vol_proxy': vol_proxy,
        'trend_proxy': trend_proxy,
        'chop_proxy': chop_proxy,
        'legacy_multiplier': clamp01(legacy_multiplier),
        'route_multiplier': clamp_route(route_multiplier),
        'policy_multiplier': clamp_route(policy_multiplier),
        'combined_multiplier': combined_multiplier,
    }


def simulate_symbol(genome, env, season, close, initial_cash, cost_rate, lot_step, lot_min, min_notional, bar_minutes=1):
    n = len(close)
    if n < max(1000, genome.EMAAnchor + 10):
        return None
    ema = rolling_ema(close, genome.EMAAnchor)
    ret = np.diff(close, prepend=close[0]) / np.maximum(close, 1e-12)
    vel = pd.Series(ret).rolling(max(2, genome.TMicro)).mean().fillna(0).to_numpy(dtype=np.float64)
    acc = np.diff(vel, prepend=vel[0])

    cash = initial_cash
    dead_qty = 0.0
    float_qty = 0.0
    realized = 0.0
    total_cost = 0.0
    truncated_orders = 0
    trade_count = 0
    dead_to_float = 0
    dca_spent = 0.0
    lots = []
    equity_curve = []
    regime_counts = {k: 0 for k in ['trend_up', 'trend_down', 'chop', 'high_vol', 'low_vol', 'neutral']}
    regime_trades = {k: 0 for k in regime_counts}
    router_checks = 0
    router_active = 0

    ghost_cash = initial_cash
    ghost_qty = 0.0
    ghost_spent = 0.0
    macro_budget = initial_cash * (1.0 - env.DeadReserveRatio) / max(1, genome.MaxDCAMonths)

    moon_period_bars = max(1, int(round(1440 * 29 / max(1, bar_minutes))))

    for i in range(1, n):
        price = close[i]
        if not np.isfinite(price) or price <= 0:
            continue
        sig_i = i - 1
        signal_price = close[sig_i]
        if not np.isfinite(signal_price) or signal_price <= 0:
            continue
        equity = cash + (dead_qty + float_qty) * price
        equity_curve.append(equity)
        if env.GlobalStopLoss > 0 and equity < initial_cash * (1.0 - env.GlobalStopLoss):
            break

        mult = season_mult(season, sig_i, n)
        moon = 1.0 + genome.MoonPhasePressure * (0.5 + 0.5 * math.sin(2.0 * math.pi * sig_i / moon_period_bars))

        # Signals use the previous completed bar; execution uses the current bar.
        if sig_i % max(1, genome.TMacro) == season.tick_offset:
            beta_dev = max(0.0, (ema[sig_i] - signal_price) / max(ema[sig_i], 1e-12))
            trigger = beta_dev >= genome.BetaThreshold or (sig_i % max(1, genome.TDeadline) == season.tick_offset)
            if trigger:
                macro_pos = (signal_price - ema[sig_i]) / max(ema[sig_i], 1e-12)
                macro_route = regime_route(genome, macro_pos, vel[sig_i], acc[sig_i])
                force = 1.0 + genome.DeadlineForcePct * (sig_i / max(1, n))
                notional = min(cash, macro_budget * mult * moon * force * macro_route['policy_multiplier'])
                qty = normalize_order_qty(notional, price, lot_step, lot_min, min_notional)
                if qty > 0:
                    gross = qty * price
                    fee = gross * cost_rate
                    cash -= gross + fee
                    dead_qty += qty
                    dca_spent += gross
                    total_cost += fee
                    trade_count += 1
                    regime_trades[macro_route['label']] += 1
                    lots.append({'qty': qty, 'price': price, 'dead': True})
                elif notional > 0:
                    truncated_orders += 1

                # Ghost DCA uses same macro cash rhythm, no micro engine.
                gqty = normalize_order_qty(min(ghost_cash, notional), price, lot_step, lot_min, min_notional)
                if gqty > 0:
                    gg = gqty * price; gf = gg * cost_rate
                    ghost_cash -= gg + gf
                    ghost_qty += gqty
                    ghost_spent += gg

        # Inventory bridge: high positive acceleration unlocks DeadHold to FloatHold.
        unlock_pressure = genome.ka * acc[sig_i] + genome.kv * vel[sig_i]
        if dead_qty > 0 and unlock_pressure > genome.MinTradeThreshold:
            move = dead_qty * min(0.50, genome.MicroReserveRate * mult)
            if move * price >= min_notional:
                dead_qty -= move
                float_qty += move
                dead_to_float += 1

        # Micro PDE target weight and fire permission.
        if sig_i % max(1, genome.TMicro) == season.tick_offset:
            pos_term = (signal_price - ema[sig_i]) / max(ema[sig_i], 1e-12)
            raw = -genome.kp * pos_term + genome.kv * vel[sig_i] + genome.ka * acc[sig_i]
            route = regime_route(genome, pos_term, vel[sig_i], acc[sig_i])
            regime_counts[route['label']] += 1
            router_checks += 1
            if route['combined_multiplier'] > 0.05:
                router_active += 1
            target_float_weight = 1.0 / (1.0 + math.exp(-max(-50, min(50, raw * genome.SigmoidScale))))
            target_float_weight = target_float_weight ** genome.Gamma
            float_value = float_qty * price
            equity = max(1e-9, cash + (dead_qty + float_qty) * price)
            target_value = equity * min(1.0 - env.DeadReserveRatio, target_float_weight * genome.Beta)
            diff = target_value - float_value
            if abs(diff) / equity >= genome.MinTradeThreshold:
                if diff > 0:
                    notional = min(cash, diff * genome.MicroReserveRate * mult * route['combined_multiplier'])
                    qty = normalize_order_qty(notional, price, lot_step, lot_min, min_notional)
                    if qty > 0:
                        gross = qty * price; fee = gross * cost_rate
                        cash -= gross + fee
                        float_qty += qty
                        lots.append({'qty': qty, 'price': price, 'dead': False})
                        total_cost += fee; trade_count += 1
                        regime_trades[route['label']] += 1
                    elif notional > 0:
                        truncated_orders += 1
                else:
                    sell_value = min(float_value, -diff * genome.MicroReserveRate * mult * route['combined_multiplier'])
                    qty = normalize_order_qty(sell_value, price, lot_step, lot_min, min_notional)
                    qty = min(qty, float_qty)
                    if qty > 0:
                        gross = qty * price; fee = gross * cost_rate
                        cash += gross - fee
                        float_qty -= qty
                        total_cost += fee; trade_count += 1
                        regime_trades[route['label']] += 1
                        # Approximate realized lot PnL FIFO over float/non-dead lots.
                        remain = qty
                        new_lots = []
                        for lot in lots:
                            if remain <= 0:
                                new_lots.append(lot); continue
                            if lot.get('dead'):
                                new_lots.append(lot); continue
                            take = min(remain, lot['qty'])
                            realized += take * (price - lot['price']) - (take * price * cost_rate)
                            lot['qty'] -= take; remain -= take
                            if lot['qty'] > 1e-12:
                                new_lots.append(lot)
                        lots = new_lots
                    elif sell_value > 0:
                        truncated_orders += 1

    final_price = close[min(n - 1, len(close) - 1)]
    equity = cash + (dead_qty + float_qty) * final_price
    ghost_equity = ghost_cash + ghost_qty * final_price
    mdd = max_drawdown(equity_curve)
    ghost_return = (ghost_equity - initial_cash) / initial_cash
    strategy_return = (equity - initial_cash) / initial_cash
    alpha = strategy_return - ghost_return
    router_active_frac = router_active / max(1, router_checks)
    dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else 'neutral'
    return {
        'equity': equity,
        'return': strategy_return,
        'ghost_equity': ghost_equity,
        'ghost_return': ghost_return,
        'alpha': alpha,
        'realized_pnl': realized,
        'cost': total_cost,
        'trades': trade_count,
        'truncated_orders': truncated_orders,
        'max_drawdown': mdd,
        'dead_to_float': dead_to_float,
        'dca_spent': dca_spent,
        'regime_counts': regime_counts,
        'regime_trades': regime_trades,
        'router_checks': router_checks,
        'router_active_frac': router_active_frac,
        'dominant_regime': dominant_regime,
    }


def evaluate_individual(genome, env, season, markets, rng, args):
    eval_genome = scale_genome_for_timeframe(genome, getattr(args, 'timeframe', '1m'))
    bar_minutes = timeframe_minutes(getattr(args, 'timeframe', '1m'))
    per = {}
    alphas = []
    returns = []
    realized = 0.0
    costs = 0.0
    trades = 0
    trunc = 0
    mdds = []
    positive_alpha = 0
    ruin = 0
    regime_counts = {k: 0 for k in ['trend_up', 'trend_down', 'chop', 'high_vol', 'low_vol', 'neutral']}
    regime_trades = {k: 0 for k in regime_counts}
    router_active_fracs = []
    for symbol, m in markets.items():
        close = m['close']
        if len(close) > args.window_bars:
            start = rng.randint(0, len(close) - args.window_bars)
            close = close[start:start + args.window_bars]
        res = simulate_symbol(eval_genome, env, season, close, args.initial_cash, args.cost_bps / 10000.0,
                              args.lot_step, args.lot_min, args.min_notional, bar_minutes)
        if not res:
            continue
        per[symbol] = res
        alphas.append(res['alpha'])
        returns.append(res['return'])
        realized += res['realized_pnl']
        costs += res['cost']
        trades += res['trades']
        trunc += res['truncated_orders']
        mdds.append(res['max_drawdown'])
        positive_alpha += 1 if res['alpha'] > 0 else 0
        ruin += 1 if res['equity'] <= args.initial_cash * (1.0 - env.GlobalStopLoss) else 0
        for key, value in (res.get('regime_counts') or {}).items():
            regime_counts[key] = regime_counts.get(key, 0) + int(value)
        for key, value in (res.get('regime_trades') or {}).items():
            regime_trades[key] = regime_trades.get(key, 0) + int(value)
        router_active_fracs.append(float(res.get('router_active_frac', 1.0)))
    n = max(1, len(alphas))
    avg_alpha = float(np.mean(alphas)) if alphas else -999.0
    min_alpha = float(np.min(alphas)) if alphas else -999.0
    avg_return = float(np.mean(returns)) if returns else -999.0
    min_return = float(np.min(returns)) if returns else -999.0
    avg_mdd = float(np.mean(mdds)) if mdds else 1.0
    max_mdd = float(np.max(mdds)) if mdds else 1.0
    trade_penalty = costs / max(1.0, args.initial_cash * n)
    trunc_penalty = trunc * 0.0005
    mdd_penalty = (max_mdd ** 2) * args.drawdown_penalty
    overtrade_penalty = max(0, trades - args.max_trades) * 0.0002
    min_return_floor = float(getattr(args, 'min_return', 0.0))
    return_shortfall = max(0.0, min_return_floor - min_return)
    positive_frac = positive_alpha / n
    min_shortfall = max(0.0, args.min_alpha - min_alpha)
    router_active_frac = float(np.mean(router_active_fracs)) if router_active_fracs else 0.0
    regime_min_coverage = float(getattr(eval_genome, 'RegimeMinCoverage', 0.02))
    coverage_shortfall = max(0.0, regime_min_coverage - router_active_frac)
    dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else 'neutral'
    score = (
        min_alpha * 160.0
        + avg_alpha * 45.0
        + min_return * 80.0
        + avg_return * 20.0
        + positive_frac * 35.0
        + realized / (args.initial_cash * n)
        - min_shortfall * 220.0
        - return_shortfall * 260.0
        - trade_penalty * 100.0
        - trunc_penalty
        - mdd_penalty
        - overtrade_penalty
        - coverage_shortfall * 120.0
    )
    qualified = bool(
        avg_alpha > 0
        and min_alpha >= args.min_alpha
        and min_return >= min_return_floor
        and positive_frac >= args.min_positive_alpha_frac
        and max_mdd <= args.max_drawdown
        and trades >= args.min_trades
        and trades <= args.max_trades
    )
    return {
        'score': score,
        'qualified': qualified,
        'avg_alpha': avg_alpha,
        'min_alpha': min_alpha,
        'avg_return': avg_return,
        'min_return': min_return,
        'positive_alpha_symbols': positive_alpha,
        'symbols_tested': len(alphas),
        'realized_pnl': realized,
        'cost': costs,
        'trades': trades,
        'truncated_orders': trunc,
        'avg_drawdown': avg_mdd,
        'max_drawdown': max_mdd,
        'ruin_symbols': ruin,
        'regime_counts': regime_counts,
        'regime_trades': regime_trades,
        'router_active_frac': router_active_frac,
        'dominant_regime': dominant_regime,
        'regime_min_coverage': regime_min_coverage,
        'regime_coverage_shortfall': coverage_shortfall,
        'per_symbol': per,
    }


def make_population(rng, pop_size, archive):
    pop = []
    incumbent_n = max(1, int(pop_size * 0.10))
    mutant_n = int(pop_size * 0.40)
    elites = archive[:incumbent_n]
    for g in elites:
        pop.append(Individual(g))
    while len(pop) < incumbent_n:
        pop.append(Individual(random_genome(rng)))
    elite_source = elites or [random_genome(rng)]
    for _ in range(mutant_n):
        pop.append(Individual(mutate_genome(rng.choice(elite_source), rng, prob=0.35, scale=1.5)))
    while len(pop) < pop_size:
        pop.append(Individual(random_genome(rng)))
    return pop[:pop_size]


def next_generation(pop, rng, pop_size, elite_ratio, mut_prob, mut_scale):
    pop = sorted(pop, key=lambda x: x.score, reverse=True)
    elite_n = max(1, math.ceil(pop_size * elite_ratio))
    new = [Individual(p.genome, p.score, p.metrics) for p in pop[:elite_n]]
    parents = pop[:max(elite_n, min(len(pop), pop_size // 3))]
    while len(new) < pop_size:
        a = rng.choice(parents).genome
        b = rng.choice(parents).genome
        child = crossover(a, b, rng)
        child = mutate_genome(child, rng, prob=mut_prob, scale=mut_scale)
        new.append(Individual(child))
    return new


def load_archive(path, limit):
    if not path or not Path(path).exists():
        return []
    try:
        data = json.load(open(path))
        items = data.get('challengers', []) + data.get('champions', []) + data.get('top', [])
        out = []
        for item in items[:limit]:
            g = item.get('genome') or item
            try:
                d = with_gene_defaults(g)
                if set(BOUNDS).issubset(d.keys()):
                    out.append(LunarGenome(**{k: d[k] for k in BOUNDS}))
            except Exception:
                continue
        return out
    except Exception:
        return []



_EVAL_CONTEXT = None


def init_evaluate_context(env, season, markets, args):
    global _EVAL_CONTEXT
    _EVAL_CONTEXT = (env, season, markets, args)


def evaluate_population_job(job):
    idx, genome, seed = job
    env, season, markets, args = _EVAL_CONTEXT
    rng = random.Random(seed)
    metrics = evaluate_individual(genome, env, season, markets, rng, args)
    return idx, metrics


def evaluate_population_jobs(jobs):
    out = []
    for idx, genome, env, season, markets, seed, args in jobs:
        rng = random.Random(seed)
        metrics = evaluate_individual(genome, env, season, markets, rng, args)
        out.append((idx, metrics))
    return out



def write_progress(args, epoch, gen, best, pop, challengers, started):
    progress_path = ROOT / (args.out + '.progress')
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'epoch': epoch,
        'generation': gen,
        'elapsed_sec': round(time.time() - started, 3),
        'best': {
            'score': best.score,
            'genome': asdict(best.genome),
            'metrics': best.metrics,
        },
        'qualified_in_population': sum(1 for p in pop if p.metrics and p.metrics['qualified']),
        'challenger_count': len(challengers),
        'top': [
            {'score': p.score, 'genome': asdict(p.genome), 'metrics': p.metrics}
            for p in pop[:10]
            if p.metrics is not None
        ],
    }
    progress_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', type=int, default=3)
    ap.add_argument('--generations', type=int, default=12)
    ap.add_argument('--population', type=int, default=60)
    ap.add_argument('--elite-ratio', type=float, default=0.05)
    ap.add_argument('--symbols', default='ADAUSDT,AVAXUSDT,BNBUSDT,BTCUSDT,DOGEUSDT,DOTUSDT,ETHUSDT,LINKUSDT,SOLUSDT,XRPUSDT')
    ap.add_argument('--timeframe', default='1m')
    ap.add_argument('--month-start', default='2024-01')
    ap.add_argument('--month-end', default='2026-05')
    ap.add_argument('--months-per-symbol', type=int, default=7)
    ap.add_argument('--window-bars', type=int, default=90000)
    ap.add_argument('--initial-cash', type=float, default=10000.0)
    ap.add_argument('--cost-bps', type=float, default=20.0)
    ap.add_argument('--lot-step', type=float, default=0.0001)
    ap.add_argument('--lot-min', type=float, default=0.0001)
    ap.add_argument('--min-notional', type=float, default=10.0)
    ap.add_argument('--drawdown-penalty', type=float, default=18.0)
    ap.add_argument('--max-drawdown', type=float, default=0.35)
    ap.add_argument('--max-trades', type=int, default=20000)
    ap.add_argument('--min-trades', type=int, default=10)
    ap.add_argument('--min-positive-alpha-frac', type=float, default=0.70)
    ap.add_argument('--min-alpha', type=float, default=-0.02)
    ap.add_argument('--min-return', type=float, default=0.0)
    ap.add_argument('--seed', type=int, default=20260625)
    ap.add_argument('--archive', default='state/lunar_genome_archive.json')
    ap.add_argument('--out', default='state/lunar_genome_crypto_lab_v6.json')
    ap.add_argument('--workers', type=int, default=1)
    args = ap.parse_args()

    STATE_DIR.mkdir(exist_ok=True); LOG_DIR.mkdir(exist_ok=True)
    started = time.time()
    rng = random.Random(args.seed)
    symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    months = month_range(args.month_start, args.month_end)
    archive = load_archive(ROOT / args.archive, 12)
    all_results = []
    challengers = []

    for epoch in range(1, args.epochs + 1):
        env = sample_environment(rng)
        season = sample_season(rng)
        selected = prepare_public_months(symbols, args.timeframe, months, args.months_per_symbol, rng)
        markets = load_markets(selected, args.timeframe)
        print('epoch_start', epoch, 'env', asdict(env), 'season', asdict(season), 'markets', {k: len(v['close']) for k, v in markets.items()}, flush=True)
        pop = make_population(rng, args.population, archive)
        best_score = None
        stall = 0
        mut_prob = 0.15
        mut_scale = 1.0
        for gen in range(1, args.generations + 1):
            pending = [
                (idx, ind.genome, args.seed + epoch * 1000003 + gen * 1009 + idx * 104729)
                for idx, ind in enumerate(pop)
                if ind.metrics is None
            ]
            if pending:
                workers = max(1, int(getattr(args, 'workers', 1)))
                if workers == 1 or len(pending) == 1:
                    init_evaluate_context(env, season, markets, args)
                    evaluated = [evaluate_population_job(job) for job in pending]
                else:
                    chunksize = max(1, len(pending) // (workers * 4))
                    with mp.Pool(processes=workers, initializer=init_evaluate_context, initargs=(env, season, markets, args)) as pool:
                        evaluated = pool.map(evaluate_population_job, pending, chunksize=chunksize)
                for idx, metrics in evaluated:
                    pop[idx].score = metrics['score']
                    pop[idx].metrics = metrics
            pop.sort(key=lambda x: x.score, reverse=True)
            best = pop[0]
            q = sum(1 for p in pop if p.metrics and p.metrics['qualified'])
            print('epoch', epoch, 'gen', gen, 'best', round(best.score, 6), 'alpha', round(best.metrics['avg_alpha'], 6),
                  'min_alpha', round(best.metrics['min_alpha'], 6), 'pos', f"{best.metrics['positive_alpha_symbols']}/{best.metrics['symbols_tested']}",
                  'mdd', round(best.metrics['max_drawdown'], 4), 'trades', best.metrics['trades'], 'q', q,
                  'mut', round(mut_prob, 3), round(mut_scale, 3), flush=True)
            if best_score is None or best.score > best_score * 1.001:
                best_score = best.score
                stall = 0
            else:
                stall += 1
                if stall >= 3:
                    mut_prob = min(0.55, mut_prob * 1.25)
                    mut_scale = min(3.0, mut_scale * 1.25)
                    stall = 0
            if gen < args.generations:
                pop = next_generation(pop, rng, args.population, args.elite_ratio, mut_prob, mut_scale)
        epoch_best = pop[0]
        record = {
            'epoch': epoch,
            'role': 'challenger',
            'environment': asdict(env),
            'season': asdict(season),
            'genome': asdict(epoch_best.genome),
            'score': epoch_best.score,
            'metrics': epoch_best.metrics,
        }
        challengers.append(record)
        archive = [epoch_best.genome] + archive[:11]
        all_results.extend([{
            'epoch': epoch,
            'genome': asdict(p.genome),
            'score': p.score,
            'metrics': p.metrics,
        } for p in pop[:20]])

    all_results.sort(key=lambda x: x['score'], reverse=True)
    challengers.sort(key=lambda x: x['score'], reverse=True)
    payload = {
        'config': vars(args),
        'elapsed_sec': round(time.time() - started, 3),
        'challenger_count': len(challengers),
        'qualified_count': sum(1 for r in all_results if r['metrics']['qualified']),
        'challengers': challengers,
        'top': all_results[:50],
        'note': 'Crypto spot adaptation of LunarGenome spec: Environment/Season/LunarGenome frozen per epoch, Alpha vs Ghost DCA fitness, pessimistic friction, lot truncation, drawdown penalty, 1-4-5 population, challenger output.',
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    arch = ROOT / args.archive
    arch.write_text(json.dumps({'champions': [], 'challengers': challengers, 'retired': []}, indent=2, ensure_ascii=False))
    print('DONE', json.dumps({'challenger_count': payload['challenger_count'], 'qualified_count': payload['qualified_count'], 'elapsed_sec': payload['elapsed_sec']}), 'OUT', out, flush=True)
    for c in challengers[:5]:
        m = c['metrics']
        print('CHALLENGER', c['epoch'], 'score', round(c['score'], 6), 'alpha', round(m['avg_alpha'], 6),
              'min_alpha', round(m['min_alpha'], 6), 'pos', f"{m['positive_alpha_symbols']}/{m['symbols_tested']}",
              'mdd', round(m['max_drawdown'], 4), 'trades', m['trades'], 'qualified', m['qualified'], flush=True)

if __name__ == '__main__':
    main()
