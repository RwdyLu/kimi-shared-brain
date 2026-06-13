#!/usr/bin/env python3
"""
Generation 0 評估腳本

先跑第一輪 500 個隨機策略，確認並行評估速度和方向。

用法:
    python run_gen0.py [--workers 2]

Author: second_bot
Date: 2026-06-01
"""

import random
import time
from pathlib import Path
import sys

# 修正 sys.path 使其指向 kimi-shared-brain 根目錄
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.genetic_engine.evolution import EvolutionEngine, DEFAULT_CONFIG


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2, help="Parallel workers")
    parser.add_argument("--pop", type=int, default=500, help="Population size")
    args = parser.parse_args()
    
    # 配置
    config = {
        **DEFAULT_CONFIG,
        "population_size": args.pop,
        "elite_count": max(10, args.pop // 10),
        "filter_min_pnl": 0.0,
        "filter_max_drawdown": 0.20,
        "filter_min_trades": 20,
        "filter_min_win_rate": 0.40,
    }
    
    print(f"{'='*60}")
    print("🧬 GEN 0 EVALUATION — Parallel Speed Test")
    print(f"{'='*60}")
    print(f"Population: {config['population_size']}")
    print(f"Workers: {args.workers}")
    print(f"Symbols: {len(config['symbols'])}")
    print(f"Filter: PnL>0, DD<20%, Trades>20, WR>40%")
    print(f"{'='*60}\n")
    
    engine = EvolutionEngine(config=config)
    
    # 創世
    t0 = time.time()
    engine.genesis(n=config["population_size"])
    t_gen = time.time() - t0
    print(f"\n🌱 Genesis done in {t_gen:.2f}s ({len(engine.population)} strategies)\n")
    
    # 並行評估
    t0 = time.time()
    engine.evaluate_generation_parallel(max_workers=args.workers, verbose=True)
    t_eval = time.time() - t0
    
    print(f"\n{'='*60}")
    print("📊 GEN 0 RESULTS")
    print(f"{'='*60}")
    print(f"Evaluation time: {t_eval:.1f}s ({t_eval/len(engine.population):.2f}s per strategy)")
    print(f"Best fitness: {engine.population[0].fitness_score:.4f}")
    print(f"Best ID: {engine.population[0].chromosome_id}")
    
    # 篩選統計
    passed = sum(1 for c in engine.population if hasattr(c, '_agg_metrics') and 
                  c._agg_metrics.total_pnl > 0 and 
                  c._agg_metrics.max_drawdown < 0.20 and
                  c._agg_metrics.total_trades > 20 and
                  c._agg_metrics.win_rate > 0.40)
    
    print(f"\n📈 Filter Results:")
    print(f"   Total evaluated: {len(engine.population)}")
    print(f"   Passed filter: {passed}")
    print(f"   Pass rate: {passed/len(engine.population)*100:.1f}%")
    
    # Top 5 details
    print(f"\n🏆 Top 5 (by fitness):")
    for i, c in enumerate(engine.population[:5]):
        fit = c.fitness_score or 0
        details = c.fitness_details or {}
        if hasattr(c, '_agg_metrics'):
            m = c._agg_metrics
            status = "✅" if (m.total_pnl > 0 and m.max_drawdown < 0.20 and m.total_trades > 20 and m.win_rate > 0.40) else "❌"
            print(f"   {i+1}. {c.chromosome_id[:16]} | Fit={fit:.4f} | PnL={m.total_pnl:.2%} | DD={m.max_drawdown:.2%} | Trades={m.total_trades} | WR={m.win_rate:.1%} {status}")
        else:
            print(f"   {i+1}. {c.chromosome_id[:16]} | Fit={fit:.4f} | (no metrics)")
    
    # 保存結果
    engine._save_generation()
    engine._export_top_n(20)
    
    print(f"\n{'='*60}")
    print(f"✅ GEN 0 complete. Check data/genetic_evolution/ for outputs.")
    print(f"{'='*60}")
    
    return passed


if __name__ == "__main__":
    passed = main()
    sys.exit(0 if passed > 0 else 1)
