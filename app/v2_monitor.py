#!/usr/bin/env python3
"""
V2 Strategy Monitor
監控 V2 策略交易數據累積，達到門檻後自動觸發調參。
"""

import json
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/root/.openclaw/workspace/kimi-shared-brain")
MIN_TRADES = 15  # 至少 15 筆交易才分析

V2_STRATEGIES = [
    "ma_cross_trend_v2",
    "volume_breakout_v2",
    "cluc_bounce",
    "supertrend_trend",
]

def check_v2_data():
    with open(BASE_DIR / "state/paper_trading_state.json", "r") as f:
        data = json.load(f)
    
    ready = []
    pending = []
    
    for sid in V2_STRATEGIES:
        sdata = data.get("strategies", {}).get(sid, {})
        trades = sdata.get("trades", [])
        closed = [t for t in trades if t.get("exit_price")]
        
        if len(closed) >= MIN_TRADES:
            ready.append({
                "strategy": sid,
                "trades": len(closed),
                "balance": sdata.get("balance", 1000),
            })
        else:
            pending.append({
                "strategy": sid,
                "trades": len(closed),
                "needed": MIN_TRADES - len(closed),
            })
    
    print(f"V2 Strategy Monitoring | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    if ready:
        print(f"\n✅ READY FOR TUNING ({len(ready)} strategies):")
        for r in ready:
            print(f"   {r['strategy']:<25} {r['trades']:>3} trades | Balance: ${r['balance']:.2f}")
        print(f"\n   Run: python app/auto_tune_task.py --strategy-id <sid>")
    
    if pending:
        print(f"\n⏳ WAITING FOR DATA ({len(pending)} strategies):")
        for p in pending:
            print(f"   {p['strategy']:<25} {p['trades']:>3} trades | Need {p['needed']:>2} more")
    
    return len(ready) > 0

if __name__ == "__main__":
    has_ready = check_v2_data()
    sys.exit(0 if has_ready else 1)
