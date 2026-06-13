#!/usr/bin/env python3
"""
Auto-Tune Integration Script
掛載到現有交易系統的調參任務

用法：
    # 1. 每 6 小時建議模式檢查（安全）
    python auto_tune_task.py --mode advisory --every-hours 6

    # 2. 單次執行，分析所有策略
    python auto_tune_task.py

    # 3. 確認 staging（半自動模式）
    python auto_tune_task.py --approve TUNE_20260520_143022

    # 4. 回滾上次調參
    python auto_tune_task.py --revert

掛載到 scheduler：
    在 scheduler.py 的循環中加入：
        if self._should_run_tuning():
            self._run_auto_tuning()
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# 添加路徑
sys.path.insert(0, str(Path(__file__).resolve().parent))
from adaptive_tuner import AdaptiveTuner, TuningMode, AutoTunerScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("auto_tune")

# ═══════════════════════════════════════════════════════════════════
# 配置 — 根據你的實際路徑修改
# ═════════════════════════════════════════════════════════════════==

CONFIG = {
    "strategies_json": "app/strategies.json",
    "paper_state": "data/paper_trading_state.json",  # 修改為你的實際路徑
    "tuning_history_dir": "data/tuning_history",
    "min_trades": 10,           # 至少幾筆交易才調參
    "check_interval_hours": 6,  # 檢查間隔（掛載到 scheduler 時用）
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-Tune Task")
    parser.add_argument("--mode", choices=["advisory", "semi_auto", "auto"], default="advisory")
    parser.add_argument("--strategy-id", help="指定策略（不指定 = 全部）")
    parser.add_argument("--approve", help="確認 staging session_id")
    parser.add_argument("--revert", action="store_true", help="回滾最後一次")
    parser.add_argument("--report", action="store_true", help="輸出調參歷史")
    parser.add_argument("--dry-run", action="store_true", help="預演模式（不寫檔）")
    parser.add_argument("--every-hours", type=int, help="定時模式：每 N 小時執行（配合 cron）")
    args = parser.parse_args()

    # 路徑解析（相對於專案根目錄）
    base_dir = Path(__file__).resolve().parent.parent
    strategies_path = base_dir / "config" / "strategies.json"
    paper_state_path = base_dir / "state" / "paper_trading_state.json"
    history_dir = base_dir / "state" / "tuning_history"

    # 檢查檔案存在
    if not paper_state_path.exists():
        logger.error(f"Paper state not found: {paper_state_path}")
        logger.info("請修改 CONFIG['paper_state'] 為正確路徑")
        sys.exit(1)

    tuner = AdaptiveTuner(
        strategies_json_path=str(strategies_path),
        paper_state_path=str(paper_state_path),
        mode=TuningMode(args.mode),
        history_dir=str(history_dir),
    )

    # 執行命令
    if args.approve:
        success = tuner.approve_staging(args.approve)
        sys.exit(0 if success else 1)

    elif args.revert:
        success = tuner.revert_last_tuning(args.strategy_id)
        sys.exit(0 if success else 1)

    elif args.report:
        report = tuner.get_tuning_report(args.strategy_id)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0)

    else:
        # 執行調參
        session = tuner.run_tuning(args.strategy_id)

        # 輸出摘要
        if session.actions:
            print(f"\n{'='*60}")
            print(f"🔧 調參會話: {session.session_id}")
            print(f"📊 策略: {session.strategy_id}")
            print(f"⚙️  模式: {session.mode.value}")
            print(f"{'='*60}")
            for a in session.actions:
                delta = "↑" if a.new_value > a.old_value else "↓"
                print(f"\n  {a.action_type.value:20} | {a.param_key}")
                print(f"    {a.old_value} {delta} {a.new_value}")
                print(f"    原因: {a.reason}")
                print(f"    信心: {'▮' * int(a.confidence * 10)}{'▯' * (10 - int(a.confidence * 10))} {a.confidence:.0%}")

            if session.mode == TuningMode.ADVISORY:
                print(f"\n💡 建議模式 — 未寫入檔案。要應用請用:")
                print(f"   python auto_tune_task.py --mode semi_auto")
            elif session.mode == TuningMode.SEMI_AUTO:
                print(f"\n⏳ 半自動模式 — 已寫入 staging，等待確認:")
                print(f"   python auto_tune_task.py --approve {session.session_id}")
            elif session.mode == TuningMode.AUTO:
                print(f"\n✅ 自動模式 — 已直接應用")
        else:
            print(f"\n✅ {session.strategy_id}: 無需調整（表現正常或交易數不足）")

        sys.exit(0)


if __name__ == "__main__":
    main()
