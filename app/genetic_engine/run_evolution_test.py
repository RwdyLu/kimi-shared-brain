#!/usr/bin/env python3
"""
Wrapper to run genetic engine v2 evolution with proper import paths
"""

import sys
import os

# Add the genetic_engine directory and parent to path
ge_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(ge_dir)
sys.path.insert(0, ge_dir)
sys.path.insert(0, parent_dir)

# Now run the cli_v2 evolution command
import argparse
from .evolution_v2 import EvolutionEngineV2, DEFAULT_CONFIG_V2
from .chromosome_v2 import StrategyChromosomeV2
from pathlib import Path
import json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--population", type=int, default=50)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--save-dir", type=str, default="genetic_runs")
    args = parser.parse_args()
    
    print(f"🧬 Evolution V2 — {args.generations} generations, {args.population} population")
    
    config = {
        **DEFAULT_CONFIG_V2,
        "population_size": args.population,
        "max_generations": args.generations,
        "backtest_days": args.days,
    }
    
    engine = EvolutionEngineV2(config=config, save_dir=args.save_dir)
    engine.genesis_v2()
    
    best = engine.run(max_generations=args.generations, verbose=True)
    
    if best:
        print(f"\n🏆 Best Strategy: {best.chromosome_id}")
        print(f"   Summary: {best.summary()}")
        print(f"   Fitness: {best.fitness_score:.4f}")
    
    # Save history
    history_file = Path(args.save_dir) / f"history_{engine.epoch_id}.json"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(history_file, "w") as f:
        json.dump(engine.history, f, indent=2)
    print(f"\n📁 History saved to: {history_file}")

if __name__ == "__main__":
    main()
