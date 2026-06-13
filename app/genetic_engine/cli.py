#!/usr/bin/env python3
"""
Genetic Engine CLI / 基因引擎命令行入口

Usage:
    # 執行一次完整演化（推薦先跑這個測試）
    python -m app.genetic_engine run --generations 20 --population 30

    # 持續演化模式（一直跑）
    python -m app.genetic_engine evolve --interval 6 --days 180

    # 只評估一個現有策略的基因形式
    python -m app.genetic_engine evaluate --strategy-id <id>

    # 將最佳策略轉換為可部署格式
    python -m app.genetic_engine deploy --top 5

    # 載入之前保存的世代繼續演化
    python -m app.genetic_engine resume --generation 5

Author: second_bot
Date: 2026-05-22
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from .evolution import EvolutionEngine, ContinuousEvolution, DEFAULT_CONFIG
from .chromosome import StrategyChromosome, random_chromosome
from .converter import convert_population_to_strategies_json
from .backtest_engine import GeneBacktestEngine, evaluate_chromosome_multi_symbol


def cmd_run(args):
    """執行單輪演化"""
    config = {
        **DEFAULT_CONFIG,
        "population_size": args.population,
        "max_generations": args.generations,
        "backtest_days": args.days,
        "cull_ratio": args.cull_ratio,
        "mutation_rate": args.mutation_rate,
        "symbols": args.symbols.split(",") if args.symbols else DEFAULT_CONFIG["symbols"],
    }
    
    engine = EvolutionEngine(config=config)
    
    # 若有 genesis 檔案，載入
    if args.from_genesis:
        genesis_chroms = load_genesis_file(args.from_genesis)
        engine.population = genesis_chroms
        print(f"📂 Loaded {len(genesis_chroms)} strategies from genesis file")
    else:
        engine.genesis()
    
    best = engine.run(max_generations=args.generations, verbose=True)
    
    # 保存結果
    if best:
        save_best_strategies(engine, args.output)
    
    return 0


def cmd_evolve(args):
    """持續演化模式"""
    config = {
        **DEFAULT_CONFIG,
        "backtest_days": args.days,
        "symbols": args.symbols.split(",") if args.symbols else DEFAULT_CONFIG["symbols"],
    }
    
    continuous = ContinuousEvolution(
        config=config,
        live_pool_size=args.live_pool,
        evolution_interval_hours=args.interval,
        backtest_days=args.days,
    )
    
    try:
        continuous.start()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        continuous.stop()
        # 保存當前狀態
        save_best_strategies(continuous.engine, args.output)
    
    return 0


def cmd_evaluate(args):
    """評估單一策略"""
    engine = GeneBacktestEngine()
    
    # 如果是現有策略 ID，嘗試從 strategies.json 載入
    if args.strategy_id:
        chrom = load_strategy_as_chromosome(args.strategy_id)
        if not chrom:
            print(f"❌ Strategy {args.strategy_id} not found")
            return 1
    else:
        # 隨機生成一個測試
        chrom = random_chromosome()
    
    symbols = args.symbols.split(",") if args.symbols else ["BTCUSDT", "ETHUSDT"]
    
    print(f"🔬 Evaluating {chrom.chromosome_id[:8]}...")
    fitness, per_symbol, trades = evaluate_chromosome_multi_symbol(
        chrom, symbols, engine, days=args.days, verbose=True
    )
    
    print(f"\n{'='*60}")
    print(f"Fitness: {fitness:.4f}")
    print(f"Total Trades: {len(trades)}")
    print(f"Per-Symbol:")
    for sym, metrics in per_symbol.items():
        print(f"  {sym}: {metrics.total_trades} trades | "
              f"WR={metrics.win_rate:.1%} | PnL={metrics.total_pnl:.2%} | "
              f"Sharpe={metrics.sharpe_ratio:.2f}")
    
    return 0


def cmd_deploy(args):
    """將最佳策略轉換為部署格式"""
    save_dir = Path("data/genetic_evolution")
    
    # 找最新世代
    gen_files = sorted(save_dir.glob("generation_*.json"), reverse=True)
    if not gen_files:
        print("❌ No evolution history found. Run 'run' first.")
        return 1
    
    latest = gen_files[0]
    with open(latest) as f:
        data = json.load(f)
    
    chroms = [StrategyChromosome.from_dict(c) for c in data["population"]]
    chroms.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
    top = chroms[:args.top]
    
    # 轉換
    strategies_json = convert_population_to_strategies_json(top)
    
    # 保存
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(strategies_json, f, indent=2)
    
    print(f"✅ Deployed {len(top)} strategies to {output}")
    for c in top:
        print(f"   {c.chromosome_id[:8]} | Fit={c.fitness_score:.3f} | {c.summary()}")
    
    return 0


def cmd_resume(args):
    """從保存的世代繼續"""
    engine = EvolutionEngine()
    engine.load_generation(args.generation)
    
    # 繼續演化
    best = engine.run(max_generations=args.generations, verbose=True)
    
    if best:
        save_best_strategies(engine, args.output)
    
    return 0


def cmd_status(args):
    """查看演化歷史狀態"""
    save_dir = Path("data/genetic_evolution")
    
    gen_files = sorted(save_dir.glob("generation_*.json"))
    if not gen_files:
        print("No evolution history found.")
        return 0
    
    print(f"📚 Evolution History: {len(gen_files)} generations")
    print(f"{'='*60}")
    
    for gf in gen_files[-10:]:  # 最近 10 代
        gen_num = int(gf.stem.split("_")[1])
        with open(gf) as f:
            data = json.load(f)
        
        pop = data.get("population", [])
        if pop:
            best_fit = max((c.get("fitness_score") or 0) for c in pop)
            avg_fit = sum((c.get("fitness_score") or 0) for c in pop) / len(pop)
        else:
            best_fit = avg_fit = 0
        
        print(f"Gen {gen_num:3d} | Pop: {len(pop):2d} | Best: {best_fit:.3f} | Avg: {avg_fit:.3f}")
    
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函數
# ═══════════════════════════════════════════════════════════════════════════════

def save_best_strategies(engine, output_path: str):
    """保存當前最佳策略"""
    top = engine.get_top_strategies(5)
    strategies_json = convert_population_to_strategies_json(top)
    
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(strategies_json, f, indent=2)
    
    print(f"\n💾 Saved top strategies to {path}")
    
    # 同時保存純基因格式
    gene_path = path.parent / f"{path.stem}_genes.json"
    with open(gene_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "strategies": [c.to_dict() for c in top],
        }, f, indent=2)
    print(f"💾 Saved gene format to {gene_path}")


def load_genesis_file(path: str) -> list:
    """從 genesis 檔案載入初始種群"""
    with open(path) as f:
        data = json.load(f)
    
    if "strategies" in data:
        return [StrategyChromosome.from_dict(c) for c in data["strategies"]]
    elif isinstance(data, list):
        return [StrategyChromosome.from_dict(c) for c in data]
    else:
        return [StrategyChromosome.from_dict(data)]


def load_strategy_as_chromosome(strategy_id: str) -> StrategyChromosome:
    """從現有 strategies.json 載入策略並轉為基因體"""
    strategies_path = Path("config/strategies.json")
    if not strategies_path.exists():
        return None
    
    with open(strategies_path) as f:
        data = json.load(f)
    
    strategies = data.get("strategies", [])
    for s in strategies:
        if s.get("id") == strategy_id or s.get("chromosome_id") == strategy_id:
            # 這是一個簡化轉換 — 現有策略 → 基因體
            # 實際上需要解析 conditions 和 parameters
            # 這裡只做基本轉換
            chrom = random_chromosome()  # 骨架
            chrom.chromosome_id = s.get("chromosome_id", f"LOAD_{strategy_id}")
            chrom.fitness_score = s.get("fitness_score")
            return chrom
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Genetic Strategy Evolution Engine")
    subparsers = parser.add_subparsers(dest="command")
    
    # run
    p_run = subparsers.add_parser("run", help="Run single evolution cycle")
    p_run.add_argument("--generations", type=int, default=20)
    p_run.add_argument("--population", type=int, default=30)
    p_run.add_argument("--days", type=int, default=90)
    p_run.add_argument("--cull-ratio", type=float, default=0.5)
    p_run.add_argument("--mutation-rate", type=float, default=0.4)
    p_run.add_argument("--symbols", type=str, default=None)
    p_run.add_argument("--from-genesis", type=str, default=None)
    p_run.add_argument("--output", type=str, default="data/genetic_evolution/deploy_strategies.json")
    
    # evolve (continuous)
    p_evolve = subparsers.add_parser("evolve", help="Continuous evolution mode")
    p_evolve.add_argument("--interval", type=float, default=6.0, help="Hours between cycles")
    p_evolve.add_argument("--days", type=int, default=180)
    p_evolve.add_argument("--live-pool", type=int, default=5)
    p_evolve.add_argument("--symbols", type=str, default=None)
    p_evolve.add_argument("--output", type=str, default="data/genetic_evolution/deploy_strategies.json")
    
    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate a single strategy")
    p_eval.add_argument("--strategy-id", type=str, default=None)
    p_eval.add_argument("--days", type=int, default=90)
    p_eval.add_argument("--symbols", type=str, default=None)
    
    # deploy
    p_deploy = subparsers.add_parser("deploy", help="Deploy top strategies")
    p_deploy.add_argument("--top", type=int, default=5)
    p_deploy.add_argument("--output", type=str, default="config/strategies_genetic.json")
    
    # v2
    p_v2 = subparsers.add_parser("v2", help="Genetic Engine V2 commands")
    p_v2_sub = p_v2.add_subparsers(dest="v2_command")
    
    # v2 evolution
    p_v2_evo = p_v2_sub.add_parser("evolution", help="V2 evolution")
    p_v2_evo.add_argument("--generations", type=int, default=20)
    p_v2_evo.add_argument("--population", type=int, default=50)
    p_v2_evo.add_argument("--days", type=int, default=90)
    p_v2_evo.add_argument("--symbols", type=str, default=None)
    p_v2_evo.add_argument("--resume", type=int, default=None)
    p_v2_evo.add_argument("--save-dir", type=str, default="data/genetic_evolution_v2")
    
    # v2 continuous
    p_v2_cont = p_v2_sub.add_parser("continuous", help="V2 continuous evolution")
    p_v2_cont.add_argument("--interval", type=float, default=6.0)
    p_v2_cont.add_argument("--live-pool", type=int, default=5)
    p_v2_cont.add_argument("--days", type=int, default=180)
    p_v2_cont.add_argument("--symbols", type=str, default=None)
    
    # v2 evaluate
    p_v2_eval = p_v2_sub.add_parser("evaluate", help="V2 evaluate strategy")
    p_v2_eval.add_argument("--chromosome-id", type=str, default=None)
    p_v2_eval.add_argument("--days", type=int, default=30)
    p_v2_eval.add_argument("--symbols", type=str, default=None)
    
    # v2 archive
    p_v2_arch = p_v2_sub.add_parser("archive", help="V2 archive operations")
    p_v2_arch.add_argument("--list", action="store_true")
    p_v2_arch.add_argument("--promote", type=str, default=None)
    p_v2_arch.add_argument("--show", type=str, default=None)
    
    # v2 deploy
    p_v2_deploy = p_v2_sub.add_parser("deploy", help="V2 deploy top strategies")
    p_v2_deploy.add_argument("--top", type=int, default=5)
    p_v2_deploy.add_argument("--save-dir", type=str, default="data/genetic_evolution_v2")
    
    args = parser.parse_args()
    
    if args.command == "run":
        return cmd_run(args)
    elif args.command == "evolve":
        return cmd_evolve(args)
    elif args.command == "evaluate":
        return cmd_evaluate(args)
    elif args.command == "deploy":
        return cmd_deploy(args)
    elif args.command == "resume":
        return cmd_resume(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "v2":
        return cmd_v2(args)
    else:
        parser.print_help()
        return 1


def cmd_v2(args):
    """V2 命令分發"""
    if args.v2_command == "evolution":
        return cmd_v2_evolution(args)
    elif args.v2_command == "continuous":
        return cmd_v2_continuous(args)
    elif args.v2_command == "evaluate":
        return cmd_v2_evaluate(args)
    elif args.v2_command == "archive":
        return cmd_v2_archive(args)
    elif args.v2_command == "deploy":
        return cmd_v2_deploy(args)
    else:
        print("V2 commands: evolution, continuous, evaluate, archive, deploy")
        return 1


def cmd_v2_evolution(args):
    """執行 V2 演化"""
    print(f"🧬 V2 Evolution — {args.generations} generations, {args.population} population")
    
    from evolution_v2 import EvolutionEngineV2, DEFAULT_CONFIG_V2
    from chromosome_v2 import StrategyChromosomeV2
    
    config = {
        **DEFAULT_CONFIG_V2,
        "population_size": args.population,
        "max_generations": args.generations,
        "backtest_days": args.days,
    }
    
    if args.symbols:
        config["symbols"] = args.symbols.split(",")
    
    engine = EvolutionEngineV2(config=config, save_dir=args.save_dir)
    
    # 若指定 resume
    if args.resume:
        checkpoint = Path(args.save_dir) / f"generation_{args.resume}.json"
        if checkpoint.exists():
            print(f"📂 Resuming from generation {args.resume}")
            with open(checkpoint) as f:
                data = json.load(f)
                from .environment import ThreeLayerConfig
                engine.population = [StrategyChromosomeV2.from_dict(c) for c in data["population"]]
                engine.generation = data["generation"]
                engine.epoch_id = data["epoch_id"]
                if "three_layer" in data:
                    engine.three_layer = ThreeLayerConfig.from_dict(data["three_layer"])
    
    if not engine.population:
        engine.genesis_v2()
    
    best = engine.run(max_generations=args.generations, verbose=True)
    
    if best:
        print(f"\n🏆 Best: {best.chromosome_id} | {best.summary()}")
        
        # 保存最佳策略
        best_file = Path(args.save_dir) / f"best_strategy_{engine.epoch_id}.json"
        best_file.parent.mkdir(parents=True, exist_ok=True)
        with open(best_file, "w") as f:
            json.dump(best.to_dict(), f, indent=2)
        print(f"💾 Saved to {best_file}")
    
    # 保存歷史
    history_file = Path(args.save_dir) / f"history_{engine.epoch_id}.json"
    with open(history_file, "w") as f:
        json.dump(engine.history, f, indent=2)
    
    # 排行榜
    top = engine.get_top_strategies(5)
    print(f"\n📊 Top 5:")
    for i, c in enumerate(top, 1):
        print(f"   {i}. {c.chromosome_id[:8]} | Fit={c.fitness_score:.4f} | {c.summary()}")
    
    return 0


def cmd_v2_continuous(args):
    """V2 持續演化"""
    print(f"🔄 V2 Continuous — interval {args.interval}h, pool {args.live_pool}")
    
    from evolution_v2 import ContinuousEvolutionV2, DEFAULT_CONFIG_V2
    
    config = {
        **DEFAULT_CONFIG_V2,
        "backtest_days": args.days,
    }
    
    if args.symbols:
        config["symbols"] = args.symbols.split(",")
    
    evo = ContinuousEvolutionV2(
        config=config,
        live_pool_size=args.live_pool,
        evolution_interval_hours=args.interval,
        backtest_days=args.days,
    )
    
    try:
        evo.start()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted")
        evo.stop()
    
    return 0


def cmd_v2_evaluate(args):
    """V2 評估"""
    print(f"🔬 V2 Evaluate: {args.chromosome_id or 'random'}")
    
    from backtest_engine_v2 import GeneBacktestEngineV2, evaluate_chromosome_multi_symbol_v2
    from chromosome_v2 import StrategyChromosomeV2
    from fitness_v2 import compute_fitness_v2, BacktestMetricsV2
    
    engine = GeneBacktestEngineV2()
    
    # 載入或生成策略
    if args.chromosome_id:
        # 嘗試從保存目錄查找
        save_dir = Path("data/genetic_evolution_v2")
        for gen_file in save_dir.glob("generation_*.json"):
            with open(gen_file) as f:
                data = json.load(f)
                for c in data.get("population", []):
                    if c["chromosome_id"].startswith(args.chromosome_id):
                        chrom = StrategyChromosomeV2.from_dict(c)
                        break
                else:
                    continue
                break
        else:
            print(f"❌ Strategy not found: {args.chromosome_id}")
            return 1
    else:
        from chromosome_v2 import random_chromosome_v2
        chrom = random_chromosome_v2()
        print(f"   Random: {chrom.chromosome_id}")
    
    symbols = args.symbols.split(",") if args.symbols else ["BTCUSDT", "ETHUSDT"]
    
    fitness, per_symbol, trades = evaluate_chromosome_multi_symbol_v2(
        chrom, symbols, engine=engine, days=args.days, verbose=True,
    )
    
    print(f"\n📊 Results: Fitness={fitness:.4f} | Trades={len(trades)}")
    for sym, result in per_symbol.items():
        m = result.strategy_metrics
        print(f"   {sym}: Alpha={result.alpha_vs_dca:+.2%} | Return={m.total_pnl:+.2%} | Trades={m.total_trades}")
    
    return 0


def cmd_v2_archive(args):
    """V2 檔案館"""
    from archive import StrategyArchive
    archive = StrategyArchive()
    
    if args.list:
        stats = archive.get_stats()
        print(f"📋 Champions: {stats['champions']} | Challengers: {stats['challengers']} | Retired: {stats['retired']}")
        for c in stats.get("champion_list", []):
            print(f"   🏆 {c['symbol']}: {c['id']}")
    
    if args.promote:
        success = archive.promote_challenger(args.promote)
        print(f"{'✅' if success else '❌'} Promote {args.promote}")
    
    if args.show:
        champ = archive.get_champion(args.show)
        if champ:
            print(f"🏆 {args.show}: {champ.chromosome_id} | Fit={champ.fitness_score:.4f}")
        else:
            print(f"   No champion for {args.show}")
    
    return 0


def cmd_v2_deploy(args):
    """V2 部署"""
    print(f"📋 V2 Deploy top {args.top}")
    
    from archive import StrategyArchive
    from .converter import convert_to_strategy_json
    from chromosome_v2 import StrategyChromosomeV2
    
    archive = StrategyArchive()
    deployed = []
    
    # 從最佳策略文件載入
    save_dir = Path(args.save_dir)
    best_files = sorted(save_dir.glob("best_strategy_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    for bf in best_files[:args.top]:
        with open(bf) as f:
            chrom = StrategyChromosomeV2.from_dict(json.load(f))
            # 轉換為部署格式
            from .converter import convert_to_strategy_json
            strategy_json = convert_to_strategy_json(chrom)
            deployed.append(strategy_json)
            print(f"   ✅ {chrom.chromosome_id[:8]}")
    
    if deployed:
        output = {
            "timestamp": datetime.now().isoformat(),
            "version": "v2",
            "strategies": deployed,
        }
        deploy_file = Path("config/strategies_genetic_v2.json")
        deploy_file.parent.mkdir(parents=True, exist_ok=True)
        with open(deploy_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n💾 Deployed {len(deployed)} strategies to {deploy_file}")
    else:
        print("❌ No strategies to deploy")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
