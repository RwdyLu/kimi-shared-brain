#!/usr/bin/env python3
"""
Genetic Engine V2 CLI / 基因引擎 V2 命令行接口

整合所有 V2 模組的統一入口：
- evolution: 單輪/多輪演化
- continuous: 持續演化模式
- evaluate: 評估單一策略
- archive: 檔案館操作
- deploy: 部署最佳策略到 Paper Trading

Usage:
    python cli_v2.py evolution --generations 20 --population 30
    python cli_v2.py continuous --interval 6 --live-pool 5
    python cli_v2.py evaluate --chromosome-id <id>
    python cli_v2.py archive --list
    python cli_v2.py deploy --top 5

Author: second_bot
Date: 2026-05-28
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# 確保能導入同目錄模組
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evolution_v2 import EvolutionEngineV2, ContinuousEvolutionV2, DEFAULT_CONFIG_V2
from chromosome_v2 import StrategyChromosomeV2, v1_to_v2
from backtest_engine_v2 import GeneBacktestEngineV2, evaluate_chromosome_multi_symbol_v2
from fitness_v2 import compute_fitness_v2, BacktestMetricsV2
from .environment import ThreeLayerConfig, SeasonSampler
from .archive import StrategyArchive


def cmd_evolution(args):
    """執行單輪或多輪演化"""
    print(f"🧬 Evolution V2 — {args.generations} generations, {args.population} population")
    
    config = {
        **DEFAULT_CONFIG_V2,
        "population_size": args.population,
        "max_generations": args.generations,
        "backtest_days": args.days,
    }
    
    if args.symbols:
        config["symbols"] = args.symbols.split(",")
    
    engine = EvolutionEngineV2(config=config, save_dir=args.save_dir)
    
    # 如果有存檔，嘗試載入
    if args.resume:
        checkpoint = Path(args.save_dir) / f"generation_{args.resume}.json"
        if checkpoint.exists():
            print(f"📂 Resuming from generation {args.resume}")
            with open(checkpoint) as f:
                data = json.load(f)
                engine.population = [StrategyChromosomeV2.from_dict(c) for c in data["population"]]
                engine.generation = data["generation"]
                engine.epoch_id = data["epoch_id"]
                if "three_layer" in data:
                    engine.three_layer = ThreeLayerConfig.from_dict(data["three_layer"])
    
    if not engine.population:
        engine.genesis_v2()
    
    best = engine.run(max_generations=args.generations, verbose=not args.quiet)
    
    if best:
        print(f"\n🏆 Best Strategy: {best.chromosome_id}")
        print(f"   Summary: {best.summary()}")
        print(f"   Fitness: {best.fitness_score:.4f}")
        
        # 保存最佳策略
        best_file = Path(args.save_dir) / f"best_strategy_{engine.epoch_id}.json"
        best_file.parent.mkdir(parents=True, exist_ok=True)
        with open(best_file, "w") as f:
            json.dump(best.to_dict(), f, indent=2)
        print(f"   Saved to: {best_file}")
    
    # 保存完整歷史
    history_file = Path(args.save_dir) / f"history_{engine.epoch_id}.json"
    with open(history_file, "w") as f:
        json.dump(engine.history, f, indent=2)
    
    # 輸出排行榜
    top = engine.get_top_strategies(5)
    print(f"\n📊 Top 5:")
    for i, c in enumerate(top, 1):
        print(f"   {i}. {c.chromosome_id[:8]} | Fit={c.fitness_score:.4f} | {c.summary()}")
    
    return best


def cmd_continuous(args):
    """持續演化模式"""
    print(f"🔄 Continuous Evolution V2")
    print(f"   Interval: {args.interval}h")
    print(f"   Live pool: {args.live_pool}")
    
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
        print("\n🛑 Interrupted by user")
        evo.stop()


def cmd_evaluate(args):
    """評估單一策略"""
    print(f"🔬 Evaluate Strategy: {args.chromosome_id or 'random'}")
    
    # 載入策略
    if args.chromosome_id:
        strategy_file = Path(args.save_dir) / f"{args.chromosome_id}.json"
        if not strategy_file.exists():
            # 嘗試從 generation 檔案查找
            for gen_file in Path(args.save_dir).glob("generation_*.json"):
                with open(gen_file) as f:
                    data = json.load(f)
                    for c in data.get("population", []):
                        if c["chromosome_id"].startswith(args.chromosome_id):
                            chrom = StrategyChromosomeV2.from_dict(c)
                            break
            else:
                print(f"❌ Strategy not found: {args.chromosome_id}")
                return
        else:
            with open(strategy_file) as f:
                chrom = StrategyChromosomeV2.from_dict(json.load(f))
    else:
        from chromosome_v2 import random_chromosome_v2
        chrom = random_chromosome_v2()
        print(f"   Generated random: {chrom.chromosome_id}")
    
    # 執行 V2 回測
    engine = GeneBacktestEngineV2()
    symbols = args.symbols.split(",") if args.symbols else DEFAULT_CONFIG_V2["symbols"][:3]
    
    fitness, per_symbol, trades = evaluate_chromosome_multi_symbol_v2(
        chrom, symbols, engine=engine,
        interval=args.interval or "5m",
        days=args.days or 30,
        verbose=True,
    )
    
    print(f"\n📊 Results:")
    print(f"   Fitness: {fitness:.4f}")
    print(f"   Total Trades: {len(trades)}")
    
    for symbol, result in per_symbol.items():
        m = result.strategy_metrics
        print(f"\n   {symbol}:")
        print(f"      Alpha vs DCA: {result.alpha_vs_dca:+.2%}")
        print(f"      Strategy Return: {m.total_pnl:+.2%}")
        print(f"      DCA Return: {m.dca_baseline_return:+.2%}")
        print(f"      Trades: {m.total_trades}")
        print(f"      Max DD: {m.max_drawdown:.2%}")


def cmd_archive(args):
    """檔案館操作"""
    archive = StrategyArchive()
    
    if args.list:
        stats = archive.get_stats()
        print(f"📋 Archive Status:")
        print(f"   Champions: {stats['champions']}")
        print(f"   Challengers: {stats['challengers']}")
        print(f"   Retired: {stats['retired']}")
        
        for c in stats.get("champion_list", []):
            print(f"   🏆 {c['symbol']}: {c['id']} (fit={c['fitness']:.4f})")
    
    if args.promote:
        success = archive.promote_challenger(args.promote)
        if success:
            print(f"✅ Promoted challenger {args.promote} to champion")
        else:
            print(f"❌ Failed to promote {args.promote}")
    
    if args.show:
        champ = archive.get_champion(args.show)
        if champ:
            print(f"🏆 Champion for {args.show}:")
            print(f"   ID: {champ.chromosome_id}")
            print(f"   Fitness: {champ.fitness_score:.4f}")
            print(f"   Epoch: {champ.epoch_id}")
            print(f"   Paper Trades: {champ.paper_trades} | PnL: ${champ.paper_pnl:.2f}")
        else:
            print(f"   No champion for {args.show}")


def cmd_deploy(args):
    """Deploy promoted Champions only; use built-in default when none exists."""
    print("📋 Deploying promoted Champion strategies")
    
    archive = StrategyArchive()
    
    from .converter import convert_to_strategy_json

    deployed = []
    champions = archive.get_all_champions()
    if champions:
        for symbol, rec in list(champions.items())[:args.top]:
            chrom = StrategyChromosomeV2.from_dict(rec.chromosome_data)
            deployed.append(convert_to_strategy_json(chrom))
            print(f"   🏆 Champion {symbol}: {rec.chromosome_id[:8]}")
    else:
        chrom = StrategyChromosomeV2.from_dict(
            archive.get_runtime_chromosome_data("default")
        )
        deployed.append(convert_to_strategy_json(chrom))
        print("   Default: built_in_default")
    
    if deployed:
        output = {
            "timestamp": datetime.now().isoformat(),
            "epoch_id": f"deploy_{datetime.now().strftime('%Y%m%d_%H%M')}",
            "strategies": deployed,
        }
        
        deploy_file = Path("config/strategies_genetic_v2.json")
        deploy_file.parent.mkdir(parents=True, exist_ok=True)
        with open(deploy_file, "w") as f:
            json.dump(output, f, indent=2)
        
        print(f"\n✅ Deployed {len(deployed)} strategies to {deploy_file}")
    else:
        print("❌ No strategies to deploy")


def main():
    parser = argparse.ArgumentParser(
        description="Genetic Trading Strategy V2 — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_v2.py evolution --generations 20 --population 30 --days 90
  python cli_v2.py continuous --interval 6 --live-pool 5
  python cli_v2.py evaluate --chromosome-id abc123
  python cli_v2.py archive --list
  python cli_v2.py deploy --top 5
        """
    )
    
    parser.add_argument("--save-dir", default="data/genetic_evolution_v2",
                       help="保存目錄")
    parser.add_argument("--symbols", default=None,
                       help="幣種列表，逗號分隔 (默認 10 個主流幣)")
    parser.add_argument("--quiet", action="store_true",
                       help="安靜模式")
    
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # evolution
    evo_parser = subparsers.add_parser("evolution", help="執行演化")
    evo_parser.add_argument("--generations", type=int, default=20,
                            help="世代數 (默認 20)")
    evo_parser.add_argument("--population", type=int, default=50,
                            help="種群大小 (默認 50)")
    evo_parser.add_argument("--days", type=int, default=90,
                            help="回測天數 (默認 90)")
    evo_parser.add_argument("--resume", type=int, default=None,
                            help="從第 N 代繼續")
    
    # continuous
    cont_parser = subparsers.add_parser("continuous", help="持續演化模式")
    cont_parser.add_argument("--interval", type=float, default=6.0,
                             help="演化間隔小時 (默認 6)")
    cont_parser.add_argument("--live-pool", type=int, default=5,
                             help="存活池大小 (默認 5)")
    cont_parser.add_argument("--days", type=int, default=180,
                             help="回測天數 (默認 180)")
    
    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="評估策略")
    eval_parser.add_argument("--chromosome-id", default=None,
                             help="策略 ID")
    eval_parser.add_argument("--interval", default="5m",
                             help="K 線間隔")
    eval_parser.add_argument("--days", type=int, default=30,
                             help="回測天數")
    
    # archive
    arch_parser = subparsers.add_parser("archive", help="檔案館操作")
    arch_parser.add_argument("--list", action="store_true",
                             help="列出所有記錄")
    arch_parser.add_argument("--promote", default=None,
                             help="提升挑戰者為冠軍")
    arch_parser.add_argument("--show", default=None,
                             help="顯示指定幣種的冠軍")
    
    # deploy
    deploy_parser = subparsers.add_parser("deploy", help="部署策略")
    deploy_parser.add_argument("--top", type=int, default=5,
                               help="部署前 N 個策略")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 執行對應命令
    if args.command == "evolution":
        cmd_evolution(args)
    elif args.command == "continuous":
        cmd_continuous(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "archive":
        cmd_archive(args)
    elif args.command == "deploy":
        cmd_deploy(args)


if __name__ == "__main__":
    main()
