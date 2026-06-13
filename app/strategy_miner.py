"""
Strategy Miner — 策略挖掘引擎
從歷史交易數據中挖掘盈利模式，測試 ensemble 組合、反向信號、參數方向。

Run: python app/strategy_miner.py
"""

import json
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

STATE_FILE = Path(__file__).resolve().parents[1] / "state" / "paper_trading_state.json"
REPORT_FILE = Path(__file__).resolve().parents[1] / "state" / "strategy_mining_report.json"


def load_all_trades():
    """從 paper_trading_state.json 提取所有歷史交易。"""
    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    trades = []
    for sid, acc in state.get("strategies", {}).items():
        for t in acc.get("trades", []):
            t["strategy_id"] = sid
            trades.append(t)
    return trades


def analyze_exit_patterns(trades):
    """分析出場原因與盈虧的關係（T-069 教訓復刻）。"""
    by_reason = defaultdict(list)
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        pnl = t.get("realized_pnl", 0)
        by_reason[reason].append(pnl)

    results = []
    for reason, pnls in sorted(by_reason.items(), key=lambda x: sum(x[1])):
        count = len(pnls)
        total = sum(pnls)
        avg = total / count if count else 0
        win_rate = len([p for p in pnls if p > 0]) / count * 100 if count else 0
        results.append({
            "exit_reason": reason,
            "count": count,
            "total_pnl": round(total, 4),
            "avg_pnl": round(avg, 6),
            "win_rate": round(win_rate, 1),
        })
    return results


def analyze_strategy_performance(trades):
    """各策略獨立表現。"""
    by_strat = defaultdict(list)
    for t in trades:
        by_strat[t["strategy_id"]].append(t.get("realized_pnl", 0))

    results = []
    for sid, pnls in sorted(by_strat.items(), key=lambda x: sum(x[1]), reverse=True):
        count = len(pnls)
        total = sum(pnls)
        avg = total / count if count else 0
        win_rate = len([p for p in pnls if p > 0]) / count * 100 if count else 0
        results.append({
            "strategy": sid,
            "trades": count,
            "total_pnl": round(total, 4),
            "avg_pnl": round(avg, 6),
            "win_rate": round(win_rate, 1),
        })
    return results


def analyze_time_patterns(trades):
    """分析進場時間與盈虧的關係。"""
    hour_stats = defaultdict(list)
    for t in trades:
        et = t.get("entry_time", "")
        if not et:
            continue
        try:
            dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
            hour = dt.hour
        except Exception:
            continue
        hour_stats[hour].append(t.get("realized_pnl", 0))

    results = []
    for h in sorted(hour_stats.keys()):
        pnls = hour_stats[h]
        count = len(pnls)
        total = sum(pnls)
        avg = total / count if count else 0
        win_rate = len([p for p in pnls if p > 0]) / count * 100 if count else 0
        results.append({
            "hour": h,
            "count": count,
            "total_pnl": round(total, 4),
            "avg_pnl": round(avg, 6),
            "win_rate": round(win_rate, 1),
        })
    return results


def analyze_consecutive_signals(trades):
    """
    Ensemble 分析：同一標的、同一方向，多個策略同時發出信號時的勝率。
    由於我們沒有原始信號時間戳，這裡用近似：同一策略短時間內的交易密度。
    更精確的做法需要 signal log，這裡先做啟發式分析。
    """
    # Group trades by (symbol, day, side) to see if multiple strategies traded same asset same day
    day_side_strats = defaultdict(set)
    day_side_pnls = defaultdict(list)
    for t in trades:
        et = t.get("entry_time", "")
        if not et:
            continue
        try:
            dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
            day_key = (t["symbol"], dt.strftime("%Y-%m-%d"), t["side"])
        except Exception:
            continue
        day_side_strats[day_key].add(t["strategy_id"])
        day_side_pnls[day_key].append(t.get("realized_pnl", 0))

    # Count how many strategies traded the same asset/day/side
    strat_count_stats = defaultdict(lambda: {"pnls": [], "count": 0})
    for key, strats in day_side_strats.items():
        n = len(strats)
        pnls = day_side_pnls[key]
        strat_count_stats[n]["pnls"].extend(pnls)
        strat_count_stats[n]["count"] += 1

    results = []
    for n in sorted(strat_count_stats.keys()):
        info = strat_count_stats[n]
        pnls = info["pnls"]
        count = len(pnls)
        total = sum(pnls)
        avg = total / count if count else 0
        win_rate = len([p for p in pnls if p > 0]) / count * 100 if count else 0
        results.append({
            "concurrent_strategies": n,
            "instances": info["count"],
            "total_trades": count,
            "total_pnl": round(total, 4),
            "avg_pnl": round(avg, 6),
            "win_rate": round(win_rate, 1),
        })
    return results


def reverse_signal_simulation(trades):
    """
    反向信號模擬：如果每次策略進場時我們反向操作（long->short, short->long），
    結果會怎樣？這能告訴我們「策略是否系統性地錯」。
    """
    reverse_pnls = []
    for t in trades:
        pnl = t.get("realized_pnl", 0)
        # Reverse: flip PnL sign approximately (doesn't account for commission diff)
        reverse_pnls.append(-pnl)

    total_original = sum(t.get("realized_pnl", 0) for t in trades)
    total_reverse = sum(reverse_pnls)
    return {
        "original_total_pnl": round(total_original, 4),
        "reverse_total_pnl": round(total_reverse, 4),
        "reverse_would_beat_original": total_reverse > total_original,
        "improvement_pct": round((total_reverse - total_original) / abs(total_original) * 100, 1) if total_original != 0 else 0,
    }


def find_profitable_subsets(trades):
    """
    策略子集測試：如果只使用部分策略（淘汰最差的），整體會不會變好？
    窮舉所有 2^N 不現實，這裡用 greedy backward elimination。
    """
    all_strats = list(set(t["strategy_id"] for t in trades))
    
    def total_pnl_of_subset(strat_set):
        return sum(t.get("realized_pnl", 0) for t in trades if t["strategy_id"] in strat_set)

    # Start with all, iteratively remove worst contributor
    current_set = set(all_strats)
    history = []
    while len(current_set) > 1:
        total = total_pnl_of_subset(current_set)
        history.append({
            "strategies": sorted(current_set),
            "count": len(current_set),
            "total_pnl": round(total, 4),
        })
        # Find strategy whose removal hurts least (or helps most)
        best_remove = None
        best_pnl_after_remove = -1e18
        for s in current_set:
            remaining = current_set - {s}
            pnl = total_pnl_of_subset(remaining)
            if pnl > best_pnl_after_remove:
                best_pnl_after_remove = pnl
                best_remove = s
        current_set.remove(best_remove)

    # Also check final single-strategy best
    best_single = max(all_strats, key=lambda s: total_pnl_of_subset({s}))
    history.append({
        "strategies": [best_single],
        "count": 1,
        "total_pnl": round(total_pnl_of_subset({best_single}), 4),
    })
    return history


def suggest_new_rules(trades):
    """
    基於數據模式，生成可執行的策略改進建議。
    """
    suggestions = []

    # 1. Exit reason analysis
    exit_analysis = analyze_exit_patterns(trades)
    ma_reverse = next((x for x in exit_analysis if "ma_reverse" in x["exit_reason"].lower() or "reverse" in x["exit_reason"].lower()), None)
    if ma_reverse and ma_reverse["total_pnl"] < -10:
        suggestions.append({
            "rule_id": "R001",
            "title": "收緊 MA 反轉出場條件",
            "priority": "HIGH",
            "reason": f"MA 反轉出場佔 {ma_reverse['count']} 筆，總虧損 ${ma_reverse['total_pnl']:.2f}，平均每筆虧 {ma_reverse['avg_pnl']:.4f}",
            "action": "提高 ma_reverse_pnl_threshold（例如從 -1.5% 到 -2.5%），或完全禁用 MA 反轉出場，改用硬止損 + ATR 止損",
        })

    # 2. Time analysis
    time_analysis = analyze_time_patterns(trades)
    bad_hours = [x for x in time_analysis if x["avg_pnl"] < -0.05 and x["count"] >= 10]
    if bad_hours:
        bad_hour_list = ", ".join(str(x["hour"]) for x in bad_hours)
        suggestions.append({
            "rule_id": "R002",
            "title": "時段過濾",
            "priority": "MEDIUM",
            "reason": f"第 {bad_hour_list} 點進場的平均盈虧為負，可能對應低流動性時段",
            "action": f"在 {bad_hour_list} 點禁止開新倉",
        })

    good_hours = [x for x in time_analysis if x["avg_pnl"] > 0.02 and x["count"] >= 5]
    if good_hours:
        good_hour_list = ", ".join(str(x["hour"]) for x in good_hours)
        suggestions.append({
            "rule_id": "R003",
            "title": "優先時段加倉",
            "priority": "MEDIUM",
            "reason": f"第 {good_hour_list} 點進場的平均盈虧為正",
            "action": f"在 {good_hour_list} 點提高倉位至 1.5x",
        })

    # 3. Strategy subset
    subset_history = find_profitable_subsets(trades)
    best_subset = max(subset_history, key=lambda x: x["total_pnl"])
    if best_subset["total_pnl"] > sum(t.get("realized_pnl", 0) for t in trades) * 0.5:
        suggestions.append({
            "rule_id": "R004",
            "title": "策略淘汰機制",
            "priority": "HIGH",
            "reason": f"只保留 {best_subset['strategies']} 這 {best_subset['count']} 個策略時，總 PnL 最佳（${best_subset['total_pnl']:.2f}）",
            "action": "自動關閉連續 30 筆交易總 PnL 為負的策略，只保留 top 3",
        })

    # 4. Reverse signal
    reverse_sim = reverse_signal_simulation(trades)
    if reverse_sim["reverse_would_beat_original"]:
        suggestions.append({
            "rule_id": "R005",
            "title": "測試反向策略",
            "priority": "HIGH",
            "reason": f"如果完全反向操作，PnL 會從 ${reverse_sim['original_total_pnl']:.2f} 變成 ${reverse_sim['reverse_total_pnl']:.2f}，改善 {reverse_sim['improvement_pct']}%",
            "action": "選 1-2 個最爛的策略（opening_range_breakout, hilbert_cycle）開啟反向模式做 paper trading 驗證",
        })

    # 5. Concurrent strategies (ensemble)
    ensemble = analyze_consecutive_signals(trades)
    good_ensemble = [x for x in ensemble if x["avg_pnl"] > 0 and x["total_trades"] >= 5]
    if good_ensemble:
        best_ens = max(good_ensemble, key=lambda x: x["avg_pnl"])
        suggestions.append({
            "rule_id": "R006",
            "title": "Ensemble 信號過濾",
            "priority": "HIGH",
            "reason": f"當 {best_ens['concurrent_strategies']} 個策略同一天同向交易時，平均盈虧為 +{best_ens['avg_pnl']:.4f}，勝率 {best_ens['win_rate']:.1f}%",
            "action": "新增過濾條件：至少 2 個策略同時發出同向信號才進場",
        })

    return suggestions


def generate_report():
    trades = load_all_trades()
    total_trades = len(trades)
    total_pnl = sum(t.get("realized_pnl", 0) for t in trades)

    print(f"\n{'='*60}")
    print(f"  Strategy Mining Report  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"  Total trades analyzed: {total_trades}")
    print(f"  Combined PnL: ${total_pnl:.2f}")
    print(f"  Avg per trade: ${total_pnl/total_trades:.4f}" if total_trades else "  N/A")
    print()

    print("─" * 60)
    print("  1. EXIT REASON ANALYSIS")
    print("─" * 60)
    for r in analyze_exit_patterns(trades):
        print(f"  {r['exit_reason']:25s} | {r['count']:>4} trades | "
              f"total=${r['total_pnl']:>8.2f} | avg={r['avg_pnl']:>8.5f} | win={r['win_rate']:>5.1f}%")

    print()
    print("─" * 60)
    print("  2. STRATEGY PERFORMANCE (ranked by total PnL)")
    print("─" * 60)
    for r in analyze_strategy_performance(trades):
        status = "🔴" if r["total_pnl"] < -50 else ("🟡" if r["total_pnl"] < 0 else "🟢")
        print(f"  {status} {r['strategy']:30s} | {r['trades']:>4} trades | "
              f"total=${r['total_pnl']:>8.2f} | avg={r['avg_pnl']:>8.5f} | win={r['win_rate']:>5.1f}%")

    print()
    print("─" * 60)
    print("  3. TIME PATTERN ANALYSIS")
    print("─" * 60)
    for r in analyze_time_patterns(trades):
        marker = "✅" if r["avg_pnl"] > 0.01 else ("❌" if r["avg_pnl"] < -0.01 else "➖")
        print(f"  {marker} Hour {r['hour']:02d}: {r['count']:>3} trades | "
              f"avg={r['avg_pnl']:>8.5f} | total=${r['total_pnl']:>7.2f} | win={r['win_rate']:>5.1f}%")

    print()
    print("─" * 60)
    print("  4. ENSEMBLE / CONCURRENT SIGNAL ANALYSIS")
    print("─" * 60)
    for r in analyze_consecutive_signals(trades):
        marker = "✅" if r["avg_pnl"] > 0 else "❌"
        print(f"  {marker} {r['concurrent_strategies']} strategies same-day: "
              f"{r['instances']} instances, {r['total_trades']} trades | "
              f"avg={r['avg_pnl']:>8.5f} | win={r['win_rate']:>5.1f}%")

    print()
    print("─" * 60)
    print("  5. REVERSE SIGNAL SIMULATION")
    print("─" * 60)
    rev = reverse_signal_simulation(trades)
    print(f"  Original total PnL:  ${rev['original_total_pnl']:>10.2f}")
    print(f"  Reverse total PnL: ${rev['reverse_total_pnl']:>10.2f}")
    print(f"  Reverse beats original? {rev['reverse_would_beat_original']}")
    if rev['reverse_would_beat_original']:
        print(f"  🟢 改善幅度: {rev['improvement_pct']}%")

    print()
    print("─" * 60)
    print("  6. GREEDY SUBSET OPTIMIZATION")
    print("─" * 60)
    for h in find_profitable_subsets(trades):
        marker = "🟢" if h["total_pnl"] > 0 else "🔴"
        print(f"  {marker} Keep {h['count']:>2} strategies: PnL=${h['total_pnl']:>8.2f} | {', '.join(h['strategies'])}")

    print()
    print("─" * 60)
    print("  7. ACTIONABLE SUGGESTIONS")
    print("─" * 60)
    suggestions = suggest_new_rules(trades)
    for s in suggestions:
        icon = "🔴" if s["priority"] == "HIGH" else "🟡"
        print(f"\n  {icon} [{s['rule_id']}] {s['title']}")
        print(f"      Why: {s['reason']}")
        print(f"      Do:  {s['action']}")

    # Save JSON report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_trades": total_trades,
        "total_pnl": round(total_pnl, 4),
        "exit_patterns": analyze_exit_patterns(trades),
        "strategy_performance": analyze_strategy_performance(trades),
        "time_patterns": analyze_time_patterns(trades),
        "ensemble_analysis": analyze_consecutive_signals(trades),
        "reverse_simulation": reverse_signal_simulation(trades),
        "subset_optimization": find_profitable_subsets(trades),
        "suggestions": suggestions,
    }
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Report saved to {REPORT_FILE}")


if __name__ == "__main__":
    generate_report()
