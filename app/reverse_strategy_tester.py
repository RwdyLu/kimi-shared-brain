"""
Reverse Strategy Tester — 反向策略驗證器

既然數據顯示「完全反向操作能改善 200%」，這個腳本：
1. 選出最爛的 2 個策略（opening_range_breakout, hilbert_cycle）
2. 在 paper_trading 中開啟「反向模式」做 50 筆 paper trading 驗證
3. 同時保留 ma_cross_trend + rsi_mid_bounce 的正向策略作為對照組

注意：反向模式不修改原始策略邏輯，而是在 signal 接收層 flip side。

Run: python app/reverse_strategy_tester.py [--apply]
"""

import json
import argparse
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(__file__).resolve().parents[1] / "state" / "paper_trading_state.json"
CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "strategies.json"
REPORT_FILE = Path(__file__).resolve().parents[1] / "state" / "reverse_test_plan.json"

# 最爛策略（來自 mining report）
REVERSE_CANDIDATES = ["opening_range_breakout", "hilbert_cycle"]

# 對照組（來自 mining report，正向表現最佳）
CONTROL_GROUP = ["ma_cross_trend", "rsi_mid_bounce"]


def create_reverse_config(dry_run=True):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    changes = []
    strategies = config.get("strategies", [])

    # 1. 禁用所有舊策略
    for s in strategies:
        sid = s.get("id", "")
        if s.get("enabled", False) and sid not in REVERSE_CANDIDATES + CONTROL_GROUP:
            s["enabled"] = False
            changes.append(f"禁用 {sid}")

    # 2. 啟用反向候選策略 + 標記反向模式
    for s in strategies:
        sid = s.get("id", "")
        if sid in REVERSE_CANDIDATES:
            s["enabled"] = True
            params = s.get("parameters", {})
            params["reverse_mode"] = True
            params["reverse_mode_note"] = "When strategy signals LONG, paper trade SHORT and vice versa"
            s["parameters"] = params
            changes.append(f"🔁 {sid}: 啟用反向模式")

    # 3. 啟用對照組（正向）
    for s in strategies:
        sid = s.get("id", "")
        if sid in CONTROL_GROUP:
            s["enabled"] = True
            changes.append(f"✅ {sid}: 啟用正向對照")

    # 4. 全局標記
    settings = config.get("settings", {})
    settings["reverse_test_active"] = True
    settings["reverse_test_started"] = datetime.now().isoformat()
    settings["reverse_test_candidates"] = REVERSE_CANDIDATES
    settings["reverse_test_control"] = CONTROL_GROUP
    config["settings"] = settings

    print(f"{'='*60}")
    print(f"  Reverse Strategy Test Plan")
    print(f"{'='*60}")
    print()
    print("  理論基礎:")
    print("  從 2,510 筆歷史交易分析，完全反向操作 PnL 會從 -$215 變成 +$215")
    print("  改善幅度: 200%")
    print()
    print("  測試設計:")
    print(f"  🔁 反向組: {REVERSE_CANDIDATES}")
    print(f"     → 策略發出 LONG 時做空，SHORT 時做多")
    print()
    print(f"  ✅ 對照組: {CONTROL_GROUP}")
    print(f"     → 維持原始方向，驗證是否仍能微盈")
    print()
    print(f"  Changes ({len(changes)}):")
    for c in changes:
        print(f"    • {c}")

    if dry_run:
        print()
        print("  ⚠️ Dry run — no changes written.")
        print("     Run with --apply to activate reverse test.")
        return

    # Backup & write
    backup_path = CONFIG_FILE.parent / f"strategies.json.bak.reverse.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        original = json.load(f)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(original, f, indent=2, ensure_ascii=False)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Save plan report
    plan = {
        "timestamp": datetime.now().isoformat(),
        "type": "reverse_strategy_test",
        "reverse_candidates": REVERSE_CANDIDATES,
        "control_group": CONTROL_GROUP,
        "expected_improvement_pct": 200,
        "validation_target_trades": 50,
        "config_backup": str(backup_path),
    }
    with open(REPORT_FILE, "w") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    print()
    print(f"  ✅ Reverse test config applied!")
    print(f"  📁 Backup: {backup_path}")
    print(f"  📊 Plan report: {REPORT_FILE}")
    print()
    print("  Next steps:")
    print("    1. Restart scheduler: python start_scheduler.py")
    print("    2. Let it run until reverse candidates reach 50 trades")
    print("    3. Run: python app/strategy_miner.py 驗證反向組 vs 對照組")
    print()
    print("  ⚠️ 注意:")
    print("     反向模式需要 trade_executor.py 或 scheduler.py 識別 reverse_mode 標記")
    print("     如果底層還沒支援，先改手動方式：在 signal 路由層 flip side")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually apply config changes")
    args = parser.parse_args()
    create_reverse_config(dry_run=not args.apply)
