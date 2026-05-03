#!/usr/bin/env python3
import sys, json, time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest.runner import run_backtest

STRATEGIES = [
    ('ma_cross_trend', 'trend'),
    ('ma_cross_trend_short', 'trend'),
    ('rsi_mid_bounce', 'reversal'),
    ('rsi_trend', 'momentum'),
    ('hilbert_cycle', 'cycle'),
    ('stochastic_breakout', 'breakout'),
    ('ema_cross_fast', 'trend'),
    ('volume_spike', 'momentum'),
    ('momentum_divergence', 'reversal'),
    ('price_channel_break', 'breakout'),
    ('opening_range_breakout', 'momentum'),
    ('rsi_scalping', 'reversal'),
    ('ema_scalping', 'trend'),
    ('cci_reversal', 'reversal'),
    ('roc_momentum', 'momentum'),
]

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
END_DATE = datetime.now().strftime('%Y-%m-%d')
START_DATE = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

def run_daily_backtest():
    print(f"[{datetime.now()}] 開始每日回測 {START_DATE} ~ {END_DATE}")
    results = []
    for sid, stype in STRATEGIES:
        try:
            r = run_backtest(
                symbols=SYMBOLS,
                start_date=START_DATE,
                end_date=END_DATE,
                stop_loss_pct=1.5,
                take_profit_pct=3.0,
                commission_pct=0.1,
                strategy_id=sid,
                strategy_type=stype
            )
            trades = r.total_trades if hasattr(r, 'total_trades') else r.get('total_trades', 0)
            ret = r.total_return_pct if hasattr(r, 'total_return_pct') else r.get('total_return_pct', 0)
            wr = r.win_rate if hasattr(r, 'win_rate') else r.get('win_rate', 0)
            dd = r.max_drawdown_pct if hasattr(r, 'max_drawdown_pct') else r.get('max_drawdown_pct', 0)
            recommended = ret > 0 and wr > 40 and trades >= 10 and dd < 10
            score = round((wr/100) * ret - (dd/100), 3) if ret > 0 else round(ret, 3)
            results.append({
                'strategy_id': sid,
                'total_trades': trades,
                'total_return_pct': round(ret, 2),
                'win_rate': round(wr, 1),
                'max_drawdown_pct': round(dd, 2),
                'score': score,
                'recommended': recommended,
                'updated_at': datetime.now().isoformat()
            })
            status = '✅' if recommended else ('🟢' if ret > 0 else '🔴')
            print(f"  {status} {sid}: {ret:.2f}% WR={wr:.1f}% trades={trades}")
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ {sid}: ERROR {e}")

    results.sort(key=lambda x: x['score'], reverse=True)
    output = {
        'updated_at': datetime.now().isoformat(),
        'period': f'{START_DATE} ~ {END_DATE}',
        'rankings': results,
        'recommended': [r for r in results if r['recommended']]
    }
    out = Path(__file__).parent.parent / 'state' / 'daily_backtest_ranking.json'
    with open(out, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ 寫入 {out}")
    rec = [r for r in results if r['recommended']]
    print(f"🏆 推薦 {len(rec)} 個策略：")
    for r in rec:
        print(f"  ✅ {r['strategy_id']}: {r['total_return_pct']}% WR={r['win_rate']}%")

if __name__ == '__main__':
    run_daily_backtest()
