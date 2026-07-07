#!/usr/bin/env python3
import argparse, csv, io, json, math, random, time, urllib.request, zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / 'data' / 'binance_public_cache'
LOCAL_DIR = ROOT / 'data' / 'kline_cache'
STATE_DIR = ROOT / 'state'
LOG_DIR = ROOT / 'logs'
BASE_URL = 'https://data.binance.vision/data/spot/monthly/klines'
COLS = ['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_base','taker_buy_quote','ignore']

EXPECTED_INTERVAL_MS = {
    '1m': 60_000,
    '3m': 180_000,
    '5m': 300_000,
    '15m': 900_000,
    '30m': 1_800_000,
    '1h': 3_600_000,
    '2h': 7_200_000,
    '4h': 14_400_000,
    '1d': 86_400_000,
}

MAX_MONTH_ROWS = {
    '1m': 45_500,
    '5m': 9_200,
    '15m': 3_100,
    '1h': 800,
    '4h': 210,
}


def month_range(start, end):
    sy, sm = map(int, start.split('-'))
    ey, em = map(int, end.split('-'))
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f'{y:04d}-{m:02d}')
        m += 1
        if m == 13:
            y += 1; m = 1
    return out


def download_month(symbol, timeframe, month, timeout=20):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f'{symbol}_{timeframe}_{month}.parquet'
    if out.exists():
        if cache_file_usable(out, timeframe):
            return out
        try:
            out.unlink()
        except Exception:
            return None
    url = f'{BASE_URL}/{symbol}/{timeframe}/{symbol}-{timeframe}-{month}.zip'
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as fh:
                df = pd.read_csv(fh, header=None, names=COLS)
        df = df[['open_time','open','high','low','close']]
        for col in ['open','high','low','close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna().sort_values('open_time')
        if len(df) < 1000:
            return None
        df.to_parquet(out, index=False)
        return out
    except Exception as exc:
        print('download_skip', symbol, month, type(exc).__name__, str(exc)[:120], flush=True)
        return None


def normalize_open_time_ms(values):
    s = pd.to_numeric(pd.Series(values), errors='coerce')
    if s.dropna().empty:
        return s.astype('Int64')
    median_value = float(s.dropna().median())
    if median_value > 10_000_000_000_000:
        s = s / 1000.0
    elif median_value < 10_000_000_000:
        s = s * 1000.0
    return s.round().astype('Int64')


def cache_file_usable(path, timeframe):
    if not path.exists() or path.stat().st_size <= 1000:
        return False
    expected = EXPECTED_INTERVAL_MS.get(timeframe)
    max_rows = MAX_MONTH_ROWS.get(timeframe)
    try:
        df = pd.read_parquet(path, columns=['open_time', 'close'])
    except Exception:
        return False
    if df.empty:
        return False
    if max_rows and len(df) > max_rows:
        return False
    if expected and len(df) > 2:
        ts = normalize_open_time_ms(df['open_time']).dropna().astype('int64')
        diffs = ts.sort_values().diff().dropna()
        diffs = diffs[diffs > 0]
        if diffs.empty:
            return False
        median_diff = float(diffs.median())
        if abs(median_diff - expected) > expected * 0.05:
            return False
    return True


def choose_contiguous_paths(symbol, timeframe, months, months_per_symbol, rng):
    available = {}
    month_set = set(months)
    for p in CACHE_DIR.glob(f'{symbol}_{timeframe}_*.parquet'):
        month = p.name.rsplit('_', 1)[-1].replace('.parquet', '')
        if month in month_set and cache_file_usable(p, timeframe):
            available[month] = p
        elif month in month_set:
            print('cache_skip_invalid', p.name, flush=True)

    block_len = max(1, min(months_per_symbol, len(months)))
    blocks = []
    for i in range(0, len(months) - block_len + 1):
        block = months[i:i + block_len]
        if all(m in available for m in block):
            blocks.append(block)
    if blocks:
        block = rng.choice(blocks)
        return [available[m] for m in block]

    cached = list(available.values())
    rng.shuffle(cached)
    return sorted(cached[:months_per_symbol])


def prepare_public_months(symbols, timeframe, months, months_per_symbol, rng):
    selected = {}
    month_set = set(months)
    for symbol in symbols:
        paths = choose_contiguous_paths(symbol, timeframe, months, months_per_symbol, rng)
        if len(paths) >= months_per_symbol:
            selected[symbol] = paths
            print('public_months', symbol, [p.name.rsplit('_', 1)[-1].replace('.parquet','') for p in paths], flush=True)
            continue

        picked_months = {p.name.rsplit('_', 1)[-1].replace('.parquet', '') for p in paths}
        picks = [m for m in months if m not in picked_months]
        rng.shuffle(picks)
        for month in picks:
            path = download_month(symbol, timeframe, month)
            if path and cache_file_usable(path, timeframe):
                paths.append(path)
            if len(paths) >= months_per_symbol:
                break
        paths = sorted(paths)
        selected[symbol] = paths
        print('public_months', symbol, [p.name.rsplit('_', 1)[-1].replace('.parquet','') for p in paths], flush=True)
    return selected


def load_markets(selected, timeframe):
    markets = {}
    for symbol, paths in selected.items():
        frames = []
        for p in sorted(paths):
            try:
                if not cache_file_usable(p, timeframe):
                    print('read_skip_invalid', p.name, flush=True)
                    continue
                dfp = pd.read_parquet(p, columns=['open_time','open','high','low','close'])
                dfp['open_time'] = normalize_open_time_ms(dfp['open_time'])
                frames.append(dfp.dropna(subset=['open_time']))
            except Exception as exc:
                print('read_skip', p, type(exc).__name__, str(exc)[:120], flush=True)
        if frames:
            df = pd.concat(frames, ignore_index=True).sort_values('open_time').drop_duplicates('open_time')
        else:
            fallback = LOCAL_DIR / f'{symbol}_{timeframe}.parquet'
            if not fallback.exists():
                continue
            print('fallback_local', symbol, fallback, flush=True)
            df = pd.read_parquet(fallback, columns=['open','high','low','close'])
        if len(df) < 2000:
            continue
        markets[symbol] = {k: df[k].to_numpy(dtype=np.float64) for k in ['close','high','low']}
        if 'open_time' in df.columns:
            markets[symbol]['open_time'] = df['open_time'].to_numpy(dtype=np.int64)
    if not markets:
        raise SystemExit('no usable markets loaded')
    return markets


def roll_mean(a, w):
    out = np.full(a.shape[0], np.nan, dtype=np.float64)
    if w <= 0 or a.shape[0] < w:
        return out
    cs = np.empty(a.shape[0] + 1, dtype=np.float64)
    cs[0] = 0.0
    np.cumsum(a, out=cs[1:])
    out[w-1:] = (cs[w:] - cs[:-w]) / float(w)
    return out


def roll_min(a, w):
    return pd.Series(a).rolling(w).min().to_numpy(dtype=np.float64)


def roll_max(a, w):
    return pd.Series(a).rolling(w).max().to_numpy(dtype=np.float64)


def rsi(close, period):
    diff = np.diff(close, prepend=close[0])
    gain = np.where(diff > 0, diff, 0.0)
    loss = np.where(diff < 0, -diff, 0.0)
    avg_gain = roll_mean(gain, period)
    avg_loss = roll_mean(loss, period)
    rs = avg_gain / np.where(avg_loss == 0, np.nan, avg_loss)
    val = 100.0 - (100.0 / (1.0 + rs))
    val[np.isnan(val) & (avg_gain > 0) & (avg_loss == 0)] = 100.0
    val[np.isnan(val)] = 50.0
    return val


def state_from_events(entry, exit_):
    n = entry.shape[0]
    state = np.zeros(n, dtype=np.bool_)
    events = np.flatnonzero(entry | exit_)
    on = False; last = 0
    for idx in events:
        if idx > last:
            state[last:idx] = on
        if exit_[idx]:
            on = False
        if entry[idx]:
            on = True
        last = idx
    if last < n:
        state[last:] = on
    return state


def signal_for(candidate, m):
    close = m['close']; high = m['high']; low = m['low']
    fam = candidate['family']
    if fam == 'ma_cross':
        fast = roll_mean(close, candidate['fast'])
        slow = roll_mean(close, candidate['slow'])
        sig = fast > slow
        sig[np.isnan(fast) | np.isnan(slow)] = False
        return sig
    if fam == 'momentum':
        lb = candidate['lookback']
        mom = np.full(close.shape[0], np.nan, dtype=np.float64)
        mom[lb:] = close[lb:] / close[:-lb] - 1.0
        return mom > (candidate['threshold_bps'] / 10000.0)
    if fam == 'rsi_revert':
        rv = rsi(close, candidate['period'])
        return state_from_events(rv < candidate['low'], rv > candidate['high'])
    if fam == 'breakout':
        lb = candidate['lookback']
        prev_high = np.roll(roll_max(high, lb), 1)
        prev_low = np.roll(roll_min(low, lb), 1)
        prev_high[0] = np.nan; prev_low[0] = np.nan
        if candidate['mode'] == 'trend':
            return state_from_events(close > prev_high, close < prev_low)
        return state_from_events(close < prev_low, close > prev_high)
    raise ValueError(f'unknown family {fam}')


def eval_slice(close, sig, start, end, cost, shift=0):
    end = min(end, close.shape[0] - 1)
    if end <= start + 100:
        return {'net': 0.0, 'trades': 0, 'wins': 0, 'losses': 0, 'exposure': 0.0}
    pos = sig.astype(np.float64)
    if shift:
        pos = np.roll(pos, shift)
    p = pos[start:end]
    c = close[start:end+1]
    valid = np.isfinite(c) & (c > 0)
    if not valid.all():
        p = p.copy(); p[~valid[:-1]] = 0.0
    ret = np.diff(c) / c[:-1]
    gross = float(np.nansum(p * ret))
    change = np.abs(np.diff(np.r_[0.0, p, 0.0]))
    costs = float(np.nansum(change) * cost)
    net = gross - costs
    pi = p.astype(np.int8)
    d = np.diff(np.r_[0, pi, 0])
    entries = np.flatnonzero(d == 1)
    exits = np.flatnonzero(d == -1)
    n = min(entries.shape[0], exits.shape[0])
    wins = losses = 0
    if n:
        entries = entries[:n]; exits = exits[:n]
        tr = c[np.minimum(exits, c.shape[0]-1)] / c[entries] - 1.0 - (2.0 * cost)
        wins = int(np.sum(tr > 0)); losses = int(np.sum(tr <= 0))
    return {'net': net, 'trades': int(n), 'wins': wins, 'losses': losses, 'exposure': float(np.mean(p))}


def make_candidate(i, rng):
    fam = rng.choice(['ma_cross','rsi_revert','breakout','momentum'])
    c = {'id': f'core_v3_g{i:04d}_{fam}', 'family': fam}
    if fam == 'ma_cross':
        fast = rng.randint(5, 80); slow = rng.randint(max(fast + 5, 20), 260)
        c.update(fast=fast, slow=slow)
    elif fam == 'rsi_revert':
        low = rng.randint(15, 42); high = rng.randint(max(low + 12, 55), 85)
        c.update(period=rng.randint(6, 42), low=low, high=high)
    elif fam == 'breakout':
        c.update(lookback=rng.randint(12, 240), mode=rng.choice(['trend','revert']))
    else:
        c.update(lookback=rng.randint(5, 180), threshold_bps=rng.choice([5,10,15,20,30,40,60,80,120]))
    return c


def neighbors(c):
    out = []
    if c['family'] == 'rsi_revert':
        for dp, dl, dh in [(-3,0,0),(3,0,0),(0,-3,0),(0,3,0),(0,0,-3),(0,0,3)]:
            n = dict(c)
            n['period'] = max(3, c['period'] + dp)
            n['low'] = max(5, min(50, c['low'] + dl))
            n['high'] = max(n['low'] + 8, min(95, c['high'] + dh))
            out.append(n)
    elif c['family'] == 'ma_cross':
        for df, ds in [(-3,0),(3,0),(0,-8),(0,8)]:
            n = dict(c); n['fast'] = max(3, c['fast'] + df); n['slow'] = max(n['fast'] + 2, c['slow'] + ds); out.append(n)
    elif c['family'] == 'breakout':
        for dl in [-12, 12, -24, 24]:
            n = dict(c); n['lookback'] = max(4, c['lookback'] + dl); out.append(n)
    else:
        for dl, dt in [(-8,0),(8,0),(0,-5),(0,5)]:
            n = dict(c); n['lookback'] = max(3, c['lookback'] + dl); n['threshold_bps'] = max(1, c['threshold_bps'] + dt); out.append(n)
    return out


def evaluate(candidate, markets, rng, base_cost, stress_costs, eras, window, train_frac, min_trades, min_pos_frac, do_stability):
    sigs = {s: signal_for(candidate, m) for s, m in markets.items()}
    train = test = stress25 = stress30 = baseline = 0.0
    trades = wins = losses = pos_symbols = 0
    per = {}
    slice_book = {}
    for symbol, m in markets.items():
        close = m['close']; sig = sigs[symbol]
        n = close.shape[0]
        sym_train = sym_test = sym_s25 = sym_s30 = sym_base = 0.0
        sym_trades = sym_wins = sym_losses = 0
        slices = []
        for _ in range(eras):
            w = min(window, n - 2)
            start = rng.randint(0, max(0, n - w - 2)) if n > w + 2 else 0
            split = start + max(100, int(w * train_frac))
            end = start + w
            slices.append((start, split, end))
            tr = eval_slice(close, sig, start, split, base_cost)
            te = eval_slice(close, sig, split, end, base_cost)
            sym_train += tr['net']; sym_test += te['net']; sym_trades += te['trades']; sym_wins += te['wins']; sym_losses += te['losses']
            sym_s25 += eval_slice(close, sig, split, end, stress_costs[0])['net']
            sym_s30 += eval_slice(close, sig, split, end, stress_costs[1])['net']
            shift = rng.randint(max(1, w // 10), max(2, w - 2))
            sym_base += eval_slice(close, sig, split, end, base_cost, shift=shift)['net']
        train += sym_train; test += sym_test; stress25 += sym_s25; stress30 += sym_s30; baseline += sym_base
        trades += sym_trades; wins += sym_wins; losses += sym_losses
        if sym_test > 0:
            pos_symbols += 1
        per[symbol] = {'train_net': sym_train, 'test_net': sym_test, 'stress25_net': sym_s25, 'stress30_net': sym_s30, 'random_shift_net': sym_base, 'trades': sym_trades}
        slice_book[symbol] = slices
    n_symbols = len(markets)
    need_pos = math.ceil(n_symbols * min_pos_frac)
    stability_pass = 0; stability_total = 0; stability_avg = None
    prelim = test > 0 and train > 0 and trades >= min_trades and pos_symbols >= need_pos and stress25 > 0 and stress30 > 0 and (test - baseline) > 0
    if do_stability and prelim:
        vals = []
        for nb in neighbors(candidate):
            nb_total = 0.0
            for symbol, m in markets.items():
                sig = signal_for(nb, m); close = m['close']
                for _, split, end in slice_book[symbol]:
                    nb_total += eval_slice(close, sig, split, end, base_cost)['net']
            vals.append(nb_total)
        stability_total = len(vals)
        stability_pass = sum(1 for v in vals if v > 0)
        stability_avg = float(np.mean(vals)) if vals else None
    stable = (not do_stability) or (stability_total > 0 and stability_pass / stability_total >= 0.60 and stability_avg is not None and stability_avg > 0)
    out = dict(candidate)
    out.update(train_net=train, test_net=test, stress25_net=stress25, stress30_net=stress30, random_shift_net=baseline,
               random_edge=test-baseline, positive_symbols=pos_symbols, symbols_tested=n_symbols, total_trades=trades,
               wins=wins, losses=losses, winrate=wins / max(wins + losses, 1), stability_pass=stability_pass,
               stability_total=stability_total, stability_avg_net=stability_avg, per_symbol=per,
               qualified=bool(prelim and stable), all_symbols_positive=bool(pos_symbols == n_symbols and test > 0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--generations', type=int, default=1000)
    ap.add_argument('--timeframe', default='1m')
    ap.add_argument('--symbols', default='ADAUSDT,AVAXUSDT,BNBUSDT,BTCUSDT,DOGEUSDT,DOTUSDT,ETHUSDT,LINKUSDT,SOLUSDT,XRPUSDT')
    ap.add_argument('--month-start', default='2024-01')
    ap.add_argument('--month-end', default='2026-05')
    ap.add_argument('--months-per-symbol', type=int, default=5)
    ap.add_argument('--eras-per-symbol', type=int, default=3)
    ap.add_argument('--window-bars', type=int, default=60000)
    ap.add_argument('--train-frac', type=float, default=0.70)
    ap.add_argument('--fee-bps', type=float, default=10.0)
    ap.add_argument('--slippage-bps', type=float, default=5.0)
    ap.add_argument('--stress-bps', default='25,30')
    ap.add_argument('--min-trades', type=int, default=40)
    ap.add_argument('--min-positive-symbol-frac', type=float, default=0.70)
    ap.add_argument('--seed', type=int, default=20260622)
    ap.add_argument('--out', default='state/core_evolution_results_v3.json')
    args = ap.parse_args()
    STATE_DIR.mkdir(exist_ok=True); LOG_DIR.mkdir(exist_ok=True)
    started = time.time(); rng = random.Random(args.seed)
    symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    months = month_range(args.month_start, args.month_end)
    print('preparing Binance public data...', flush=True)
    selected = prepare_public_months(symbols, args.timeframe, months, args.months_per_symbol, rng)
    markets = load_markets(selected, args.timeframe)
    print('loaded_markets', {k: len(v['close']) for k, v in markets.items()}, flush=True)
    base_cost = (args.fee_bps + args.slippage_bps) / 10000.0
    stress_costs = [float(x) / 10000.0 for x in args.stress_bps.split(',')[:2]]
    if len(stress_costs) < 2:
        stress_costs = [0.0025, 0.0030]
    results = []; best = None
    for i in range(1, args.generations + 1):
        cand_rng = random.Random(args.seed + i * 104729)
        cand = make_candidate(i, rng)
        res = evaluate(cand, markets, cand_rng, base_cost, stress_costs, args.eras_per_symbol, args.window_bars,
                       args.train_frac, args.min_trades, args.min_positive_symbol_frac, True)
        results.append(res)
        if best is None or res['test_net'] > best['test_net']:
            best = res
        if i == 1 or i % 25 == 0:
            q = sum(1 for r in results if r['qualified'])
            strict = sum(1 for r in results if r['qualified'] and r['all_symbols_positive'])
            print(f"gen={i} best={best['id']} test={best['test_net']:.6f} stress30={best['stress30_net']:.6f} edge={best['random_edge']:.6f} pos={best['positive_symbols']}/{best['symbols_tested']} q={q} strict={strict}", flush=True)
    results.sort(key=lambda x: (x['qualified'], x['test_net']), reverse=True)
    qualified = [r for r in results if r['qualified']]
    strict = [r for r in qualified if r['all_symbols_positive']]
    payload = {'config': vars(args), 'symbols': sorted(markets.keys()), 'selected_public_files': {k:[str(p) for p in v] for k,v in selected.items()},
               'generations_run': args.generations, 'qualified_count': len(qualified), 'strict_all_symbols_positive_count': len(strict),
               'elapsed_sec': round(time.time() - started, 3), 'top': results[:50], 'qualified': qualified, 'strict_all_symbols_positive': strict}
    out = ROOT / args.out; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print('DONE', json.dumps({k: payload[k] for k in ['generations_run','qualified_count','strict_all_symbols_positive_count','elapsed_sec']}), 'OUT', out, flush=True)

if __name__ == '__main__':
    main()
