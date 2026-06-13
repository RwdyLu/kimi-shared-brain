"""
Strategy Improvement Applier — 策略改進執行器
基於 strategy_miner.py 的分析結果，自動修改 config 啟用最佳子集 + 時段過濾。

Safety: 只改 config/strategies.json，不動交易邏輯。可隨時回滾。
Run: python app/apply_strategy_improvements.py [--dry-run]
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from copy import deepcopy

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "strategies.json"
BACKUP_DIR = Path(__file__).resolve().parents[1] / "state" / "config_backups"

# ─── 改進規則（來自 strategy_miner 分析） ─────────────────────────

# 1. 最佳子集：只保留這些策略
KEEP_STRATEGIES = {
    "ma_cross_trend",
    "rsi_mid_bounce",
    # 可選加入 ma_cross_trend_v2（如果 V2 數據更多後驗證有效）
}

# 2. 時段過濾：禁止這些小時開新倉
FORBIDDEN_HOURS = {0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 14, 15, 17, 18, 23}

# 3. 可選：加倉時段（20, 22 點）
BOOST_HOURS = {20, 22}
BOOST_MULTIPLIER = 1.5


def backup_config():
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"strategies.json.bak.{ts}"
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return backup_path


def apply_improvements(dry_run: bool = True):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    original = deepcopy(config)
    changes = []

    strategies = config.get("strategies", [])

    # 1. 策略淘汰：只保留最佳子集
    for s in strategies:
        sid = s.get("id", "")
        was_enabled = s.get("enabled", False)

        if sid in KEEP_STRATEGIES:
            if not was_enabled:
                s["enabled"] = True
                changes.append(f"啟用 {sid}")
        else:
            if was_enabled:
                s["enabled"] = False
                changes.append(f"禁用 {sid}（表現不佳，拖累整體 PnL）")

    # 2. 時段過濾：在每個保留策略的 parameters 中加入 hour_restrictions
    for s in strategies:
        sid = s.get("id", "")
        if sid not in KEEP_STRATEGIES:
            continue

        params = s.get("parameters", {})
        if "hour_restrictions" not in params:
            params["hour_restrictions"] = {
                "forbidden_hours": sorted(FORBIDDEN_HOURS),
                "boost_hours": sorted(BOOST_HOURS),
                "boost_multiplier": BOOST_MULTIPLIER,
            }
            changes.append(f"{sid}: 加入時段過濾（禁止 {sorted(FORBIDDEN_HOURS)} 點，20/22 點 1.5x 倉位）")
        s["parameters"] = params

    # 3. 全局設定：如果有的話
    global_settings = config.get("settings", {})
    if "max_active_strategies" not in global_settings:
        global_settings["max_active_strategies"] = len(KEEP_STRATEGIES)
        changes.append(f"設定 max_active_strategies = {len(KEEP_STRATEGIES)}")

    config["settings"] = global_settings

    print(f"{'='*60}")
    print(f"  Strategy Improvement Applier")
    print(f"{'='*60}")
    print(f"  Config file: {CONFIG_FILE}")
    print(f"  Dry run: {dry_run}")
    print()
    print(f"  Changes to apply ({len(changes)}):")
    for c in changes:
        print(f"    • {c}")

    if dry_run:
        print()
        print("  ⚠️  Dry run mode — no changes written.")
        print(f"     Run with --apply to actually modify config.")
        return

    # Write backup & apply
    backup_path = backup_config()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print()
    print(f"  ✅ Config updated. Backup saved to:")
    print(f"     {backup_path}")
    print()
    print("  Next steps:")
    print("    1. Restart scheduler to pick up new config")
    print("    2. Monitor paper trading for 48h")
    print("    3. Run: python app/strategy_miner.py 再次驗證")


def rollback():
    """回滾到最近一次備份。"""
    backups = sorted(BACKUP_DIR.glob("strategies.json.bak.*"), reverse=True)
    if not backups:
        print("❌ No backup found.")
        return

    latest = backups[0]
    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Rolled back to {latest.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply strategy improvements")
    parser.add_argument("--apply", action="store_true", help="Actually modify config (default is dry-run)")
    parser.add_argument("--rollback", action="store_true", help="Rollback to latest backup")
    args = parser.parse_args()

    if args.rollback:
        rollback()
    else:
        apply_improvements(dry_run=not args.apply)
