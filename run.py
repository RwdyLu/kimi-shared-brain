#!/usr/bin/env python3
"""
主入口

用法：
  python run.py loop        # 持續運行完整閉環（推薦）
  python run.py evolve      # 只跑一輪基因演化
  python run.py backtest    # 對現有 champion 跑驗證回測
  python run.py status      # 顯示當前 champion/challenger 狀態
"""

import sys


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "loop":
        from app.core_loop import CoreLoop
        CoreLoop().run_forever()

    elif cmd == "once":
        from app.core_loop import run_one_cycle
        run_one_cycle()

    elif cmd == "evolve":
        from app.genetic_engine.evolution import EvolutionEngine, DEFAULT_CONFIG
        evo = EvolutionEngine(config=DEFAULT_CONFIG)
        evo.run()

    elif cmd == "backtest":
        from run_validation_backtest import main as backtest_main
        backtest_main()

    elif cmd == "status":
        from app.genetic_engine.archive import StrategyArchive
        archive = StrategyArchive()
        stats = archive.get_stats()
        print(f"\n=== 策略狀態 ===")
        print(f"Champions : {stats['champions']}")
        print(f"Challengers: {stats['challengers']}")
        print(f"Retired   : {stats['retired']}")
        if stats.get("champion_list"):
            print("\nCurrent Champions:")
            for c in stats["champion_list"]:
                print(f"  [{c['symbol']}] {c['id']} fitness={c['fitness']:.3f}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
