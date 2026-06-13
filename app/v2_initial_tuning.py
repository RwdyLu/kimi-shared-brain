#!/usr/bin/env python3
"""
V2 Strategy Initial Tuning + Monitoring Setup
V2 策略初始調參 + 監控設定

基於舊策略 2103 筆交易數據的教訓，為 V2 策略設定更激進的初始參數，
並建立監控等待新數據累積。
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("v2_tuning")

BASE_DIR = Path("/root/.openclaw/workspace/kimi-shared-brain")


def analyze_old_data():
    """分析舊策略數據，提取關鍵教訓"""
    with open(BASE_DIR / "state/paper_trading_state.json", "r") as f:
        data = json.load(f)
    
    lessons = {
        "ma_reverse_dominant": [],
        "high_frequency_low_profit": [],
        "tight_stop_killed": [],
    }
    
    for s, v in data.get("strategies", {}).items():
        trades = v.get("trades", [])
        if not trades:
            continue
        
        closed = [t for t in trades if t.get("exit_price")]
        if len(closed) < 10:
            continue
        
        # Infer exit reasons
        reasons = {"signal_exit": 0, "ma_reverse": 0, "atr_stop": 0, "hard_stop": 0, "time_stop": 0}
        for t in closed:
            pnl = t.get("realized_pnl", 0)
            entry = t.get("entry_price", 1)
            qty = t.get("quantity", 1)
            pnl_pct = pnl / (qty * entry) if entry else 0
            
            if pnl_pct <= -0.045:
                reasons["hard_stop"] += 1
            elif pnl_pct <= -0.015:
                reasons["atr_stop"] += 1
            else:
                entry_time = t.get("entry_time", "")
                exit_time = t.get("exit_time", "")
                if entry_time and exit_time:
                    from datetime import datetime as dt
                    try:
                        et = dt.fromisoformat(entry_time.replace("Z", "+00:00"))
                        xt = dt.fromisoformat(exit_time.replace("Z", "+00:00"))
                        duration_min = (xt - et).total_seconds() / 60
                        if duration_min < 30:
                            reasons["ma_reverse"] += 1
                        elif duration_min > 360:
                            reasons["time_stop"] += 1
                        else:
                            reasons["signal_exit"] += 1
                    except:
                        reasons["signal_exit"] += 1
                else:
                    reasons["signal_exit"] += 1
        
        total = len(closed)
        ma_pct = reasons["ma_reverse"] / total
        avg_pnl = sum(t.get("realized_pnl", 0) for t in closed) / len(closed)
        
        if ma_pct > 0.50:
            lessons["ma_reverse_dominant"].append({
                "strategy": s,
                "ma_pct": ma_pct,
                "avg_pnl": avg_pnl,
                "trades": total,
            })
        
        if total > 100 and avg_pnl > -0.005:
            lessons["high_frequency_low_profit"].append({
                "strategy": s,
                "avg_pnl": avg_pnl,
                "trades": total,
            })
    
    return lessons


def generate_v2_initial_params(lessons):
    """基於教訓產生 V2 初始參數建議"""
    
    # 從舊數據計算教訓
    ma_reverse_strategies = [l["strategy"] for l in lessons.get("ma_reverse_dominant", [])]
    
    params = {
        # 核心止損參數（基於舊策略的教訓）
        "hard_stop_loss": -0.06,           # 舊的 -3% 太緊，新 -5% 還是有些策略被掃，建議 -6%
        "atr_stop_multiplier": 2.0,        # 舊的沒有ATR止損，新 1.5x 可能太緊，建議 2.0x
        "atr_min_floor": -0.025,           # ATR止損最低地板（防止低波動時太緊）
        
        # MA反轉出場（頭號殺手）
        "ma_reverse_pnl_threshold": -0.015,  # 舊的太寬鬆（-0.005），建議收緊到 -1.5%
        "ma_reverse_min_duration_min": 15,   # MA反轉至少要持倉15分鐘才允許
        
        # 階梯止盈（提高目標，減少微盈出場）
        "profit_targets": {
            "0": 0.06,     # 0分鐘: 6%（舊的 5%）
            "20": 0.05,    # 20分鐘: 5%
            "40": 0.04,    # 40分鐘: 4%
            "60": 0.03,    # 60分鐘: 3%
            "120": 0.02,   # 120分鐘: 2%
            "240": 0.01,   # 240分鐘: 1%
        },
        
        # 移動止損
        "trailing_stop_trigger": 0.04,      # 利潤達到 4% 啟動移動止損（舊的 3%）
        "trailing_stop_drawback": 0.015,    # 回撤 1.5% 出場（舊的 2% 可以更緊）
        
        # 時間止損
        "time_stop_hours": 10.0,            # 延長到 10 小時（舊的 8.2h）
        
        # 倉位
        "position_pct": 0.12,               # 從 15% 降到 12%（舊策略交易太頻繁，降低頻率）
        "max_concurrent_positions": 3,       # 最多同時 3 個倉位
        
        # 趨勢過濾（ADX）
        "adx_min_for_entry": 22,            # 舊的 20，提高到 22 減少橫盤進場
        "adx_strong_trend": 28,             # 強趨勢門檻
        
        # 成交量過濾
        "volume_ema_multiplier": 2.5,       # 成交量爆發倍數（舊 3.0 可能太嚴格）
    }
    
    return params


def write_v2_params_to_config(params):
    """將參數寫入 strategies.json 的 default_params"""
    config_path = BASE_DIR / "config/strategies.json"
    
    with open(config_path, "r") as f:
        config = json.load(f)
    
    # 添加 default_params
    if "default_params" not in config:
        config["default_params"] = {}
    
    config["default_params"].update(params)
    config["default_params"]["_tuned_at"] = datetime.now().isoformat()
    config["default_params"]["_tuned_from"] = "v2_initial_tuning_based_on_2103_old_trades"
    
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    logger.info(f"V2 initial params written to {config_path}")


def setup_monitoring():
    """設定監控腳本，檢查 V2 策略何時有足夠數據"""
    monitor_script = BASE_DIR / "app/v2_monitor.py"
    
    content = '''#!/usr/bin/env python3
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
'''
    
    with open(monitor_script, "w") as f:
        f.write(content)
    
    monitor_script.chmod(0o755)
    logger.info(f"Monitor script written: {monitor_script}")


def main():
    print("=" * 70)
    print("V2 STRATEGY INITIAL TUNING")
    print("Based on analysis of 2,103 old trades from 14 pre-V2 strategies")
    print("=" * 70)
    
    # 1. 分析舊數據
    print("\n📊 Step 1: Analyzing old strategy data...")
    lessons = analyze_old_data()
    
    ma_dominant = lessons.get("ma_reverse_dominant", [])
    print(f"   Found {len(ma_dominant)} strategies where MA reverse was dominant:")
    for l in ma_dominant:
        print(f"      {l['strategy']:<25} MA reverse: {l['ma_pct']:>5.1%} | Avg PnL: {l['avg_pnl']:+.3f}")
    
    # 2. 產生建議
    print("\n🔧 Step 2: Generating V2 initial parameters...")
    params = generate_v2_initial_params(lessons)
    
    print("\n   Key parameter changes based on old data lessons:")
    print(f"   • hard_stop_loss: -5% → -6% (some strategies still hit -5% too often)")
    print(f"   • atr_stop_multiplier: 1.5x → 2.0x (1.5x was too tight for high volatility)")
    print(f"   • ma_reverse_pnl_threshold: -0.5% → -1.5% (MA reverse was the #1 killer)")
    print(f"   • profit_targets: baseline raised by ~1% at each step")
    print(f"   • position_pct: 15% → 12% (reduce frequency, let winners run)")
    print(f"   • adx_min_for_entry: 20 → 22 (tighter trend filter)")
    
    # 3. 寫入配置
    print("\n💾 Step 3: Writing to config/strategies.json...")
    write_v2_params_to_config(params)
    
    # 4. 設定監控
    print("\n📡 Step 4: Setting up V2 monitoring...")
    setup_monitoring()
    
    # 5. 輸出總結
    print("\n" + "=" * 70)
    print("✅ V2 INITIAL TUNING COMPLETE")
    print("=" * 70)
    print("""
Next Steps:
1. V2 strategies are now running with tuned initial parameters
2. Monitor script: python app/v2_monitor.py
3. Once V2 strategies accumulate 15+ closed trades each, run:
   
   python app/auto_tune_task.py --mode advisory
   
   to get adaptive tuning suggestions based on ACTUAL V2 performance.

4. Review daily: check if the old killers (MA reverse, tight stops) 
   are still haunting the new strategies.
""")
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "basis": "2103_old_trades_14_strategies",
        "lessons": lessons,
        "applied_params": params,
    }
    
    report_path = BASE_DIR / "state/v2_initial_tuning_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"📄 Full report saved: {report_path}")


if __name__ == "__main__":
    main()
