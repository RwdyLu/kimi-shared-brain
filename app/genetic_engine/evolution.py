#!/usr/bin/env python3
"""
Evolution Engine / 基因算法主引擎

實現「生存競爭 + 繁殖 + 突變」的完整閉環。

參考:
- 基因算法 (Genetic Algorithm) 的選擇、交叉、突變
- Freqtrade HyperOpt 的參數搜尋空間
- 生物啟發式的 elitism + diversity preservation

Author: second_bot
Date: 2026-05-22
"""

import random
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

from .chromosome import (
    StrategyChromosome, random_chromosome, 
    mutate_chromosome, crossover_chromosomes, validate_chromosome
)
from .backtest_engine import GeneBacktestEngine, evaluate_chromosome_multi_symbol
from .fitness import compute_fitness, compute_fitness_details, BacktestMetrics


# ═══════════════════════════════════════════════════════════════════════════════
# 篩選工具
# ═══════════════════════════════════════════════════════════════════════════════

def passes_raw_filter(metrics: BacktestMetrics, config: Dict[str, Any]) -> bool:
    """
    基於原始回測指標的篩選（而非 fitness score）。
    
    用戶指定標準：
    - PnL > 0
    - 回撤 < 20%
    - 交易次數 > 20
    - 勝率 > 40%
    """
    return (
        metrics.total_pnl > config.get("filter_min_pnl", 0.0)
        and metrics.max_drawdown < config.get("filter_max_drawdown", 0.20)
        and metrics.total_trades > config.get("filter_min_trades", 20)
        and metrics.win_rate > config.get("filter_min_win_rate", 0.40)
    )


def aggregate_metrics(per_symbol: Dict[str, BacktestMetrics]) -> BacktestMetrics:
    """將多幣種指標聚合為單一 BacktestMetrics"""
    if not per_symbol:
        return BacktestMetrics()
    
    total_trades = sum(m.total_trades for m in per_symbol.values())
    total_wins = sum(m.winning_trades for m in per_symbol.values())
    
    avg_pnl = sum(m.total_pnl for m in per_symbol.values()) / len(per_symbol)
    avg_dd = sum(m.max_drawdown for m in per_symbol.values()) / len(per_symbol)
    avg_sharpe = sum(m.sharpe_ratio for m in per_symbol.values()) / len(per_symbol)
    avg_pf = sum(m.profit_factor for m in per_symbol.values()) / len(per_symbol)
    
    win_rate = total_wins / total_trades if total_trades > 0 else 0.0
    
    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=total_wins,
        losing_trades=total_trades - total_wins,
        win_rate=win_rate,
        total_pnl=avg_pnl,
        max_drawdown=avg_dd,
        sharpe_ratio=avg_sharpe,
        profit_factor=avg_pf,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
]

DEFAULT_CONFIG = {
    "population_size": 500,          # 每世代個體數
    "elite_count": 50,               # 精英保留數（10%）
    "max_generations": 50,           # 最大世代數
    "mutation_rate": 0.4,            # 突變率
    "crossover_rate": 0.6,           # 交叉率
    "mutation_intensity": 0.3,       # 突變強度
    "min_fitness_to_survive": 0.15,  # 最低存活分數
    "cull_ratio": 0.5,               # 每世代淘汰比例
    "backtest_days": 90,             # 回測天數
    "backtest_interval": "5m",       # 回測 K 線
    "symbols": DEFAULT_SYMBOLS,
    "tournament_size": 3,            # 錦標賽選擇參數
    "diversity_pressure": 0.1,         # 多樣性壓力（防止過早收斂）
    "early_stop_generations": 15,    # 連續 N 代無改善則停止
    "early_stop_threshold": 0.001,   # 改善門檻
    
    # ── 篩選標準（基於原始回測指標） ──
    "filter_min_pnl": 0.0,           # PnL > 0
    "filter_max_drawdown": 0.20,     # 回撤 < 20%
    "filter_min_trades": 20,         # 交易次數 > 20
    "filter_min_win_rate": 0.40,     # 勝率 > 40%
    "report_every_n_generations": 10,  # 每 N 代回報一次
}


# ═══════════════════════════════════════════════════════════════════════════════
# 演化引擎
# ═══════════════════════════════════════════════════════════════════════════════

class EvolutionEngine:
    """
    策略基因池的演化引擎。
    
    每一世代:
    1. 評估所有個體（全歷史回測）
    2. 排序，標記精英
    3. 淘汰底部個體
    4. 繁殖填補空缺（交叉 + 突變）
    5. 偶爾注入全新隨機個體（維持多樣性）
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        engine: Optional[GeneBacktestEngine] = None,
        save_dir: Optional[str] = None,
    ):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.backtest_engine = engine or GeneBacktestEngine()
        self.population: List[StrategyChromosome] = []
        self.generation = 0
        self.history: List[Dict[str, Any]] = []
        self.best_fitness_history: List[float] = []
        self.save_dir = Path(save_dir) if save_dir else Path("data/genetic_evolution")
        self.save_dir.mkdir(parents=True, exist_ok=True)
    
    def genesis(self, n: Optional[int] = None) -> List[StrategyChromosome]:
        """
        創世 — 生成初始種群
        """
        size = n or self.config["population_size"]
        print(f"🌱 Genesis: Creating {size} random strategies...")
        
        population = []
        attempts = 0
        while len(population) < size and attempts < size * 3:
            chrom = random_chromosome(generation=0)
            if validate_chromosome(chrom):
                population.append(chrom)
            attempts += 1
        
        self.population = population
        self.generation = 0
        print(f"   ✓ {len(population)} valid strategies created")
        return population
    
    def evaluate_generation_parallel(self, max_workers: int = 2, verbose: bool = True) -> None:
        """
        並行評估當前世代的所有個體（使用 ThreadPoolExecutor）。
        
        每個 worker 獨立運行回測，共享 KlineCache 記憶體快取。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        print(f"\n📊 Generation {self.generation}: Parallel evaluating {len(self.population)} strategies (workers={max_workers})...")
        
        # 收集需要評估的染色體
        to_eval = [(i, chrom) for i, chrom in enumerate(self.population) if chrom.fitness_score is None]
        
        if not to_eval:
            if verbose:
                print("   All already evaluated.")
            return
        
        completed = 0
        total = len(to_eval)
        
        def _eval_one(args):
            idx, chrom = args
            try:
                engine = GeneBacktestEngine()
                fitness, per_symbol, trades = evaluate_chromosome_multi_symbol(
                    chrom,
                    symbols=self.config["symbols"],
                    engine=engine,
                    interval=self.config["backtest_interval"],
                    days=self.config["backtest_days"],
                    verbose=False,
                )
                agg = aggregate_metrics(per_symbol)
                return idx, fitness, agg, per_symbol, None
            except Exception as e:
                return idx, 0.0, BacktestMetrics(), {}, str(e)
        
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_eval_one, args): args for args in to_eval}
            
            for future in as_completed(futures):
                idx, fitness, agg_metrics, per_symbol, error = future.result()
                chrom = self.population[idx]
                
                if error:
                    chrom.fitness_score = 0.0
                    chrom.fitness_details = {"error": error}
                else:
                    chrom.fitness_score = fitness
                    chrom.fitness_details = {
                        "fitness": round(fitness, 4),
                        "total_trades": agg_metrics.total_trades,
                        "avg_pnl_per_symbol": round(agg_metrics.total_pnl, 4),
                        "max_drawdown": round(agg_metrics.max_drawdown, 4),
                        "win_rate": round(agg_metrics.win_rate, 4),
                        "sharpe_ratio": round(agg_metrics.sharpe_ratio, 4),
                        "symbols_tested": len(per_symbol),
                    }
                    # 將聚合指標附加到染色體上供篩選使用
                    chrom._agg_metrics = agg_metrics
                
                completed += 1
                if verbose and completed % 50 == 0:
                    print(f"   [{completed}/{total}] evaluated...")
        
        # 排序
        self.population.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
        
        # 統計
        best = self.population[0].fitness_score if self.population else 0
        avg = sum((c.fitness_score or 0) for c in self.population) / len(self.population) if self.population else 0
        self.best_fitness_history.append(best)
        
        # 篩選統計
        passed = sum(1 for c in self.population if hasattr(c, '_agg_metrics') and passes_raw_filter(c._agg_metrics, self.config))
        
        self.history.append({
            "generation": self.generation,
            "best_fitness": best,
            "avg_fitness": round(avg, 4),
            "population_size": len(self.population),
            "best_strategy_id": self.population[0].chromosome_id if self.population else None,
            "passed_filter": passed,
        })
        
        if verbose:
            print(f"\n   🏆 Best: {best:.4f} | Avg: {avg:.4f} | Passed: {passed}/{len(self.population)} | Top: {self.population[0].chromosome_id[:8]}")
    
    def evaluate_generation(self, verbose: bool = True) -> None:
        """
        串行評估（保留給小規模測試用）。
        大規模評估請使用 evaluate_generation_parallel。
        """
        print(f"\n📊 Generation {self.generation}: Evaluating {len(self.population)} strategies (serial)...")
        
        for i, chrom in enumerate(self.population):
            if chrom.fitness_score is not None:
                continue
            
            if verbose:
                print(f"   [{i+1}/{len(self.population)}] {chrom.chromosome_id[:8]}...", end=" ")
            
            try:
                fitness, per_symbol, trades = evaluate_chromosome_multi_symbol(
                    chrom,
                    symbols=self.config["symbols"],
                    engine=self.backtest_engine,
                    interval=self.config["backtest_interval"],
                    days=self.config["backtest_days"],
                    verbose=False,
                )
                chrom.fitness_score = fitness
                
                total_trades = sum(m.total_trades for m in per_symbol.values())
                avg_pnl = sum(m.total_pnl for m in per_symbol.values()) / len(per_symbol) if per_symbol else 0
                
                chrom.fitness_details = {
                    "fitness": round(fitness, 4),
                    "total_trades": total_trades,
                    "avg_pnl_per_symbol": round(avg_pnl, 4),
                    "symbols_tested": len(per_symbol),
                }
                
                if verbose:
                    print(f"Fit={fitness:.3f} Trades={total_trades}")
                
            except Exception as e:
                if verbose:
                    print(f"ERROR: {e}")
                chrom.fitness_score = 0.0
                chrom.fitness_details = {"error": str(e)}
        
        self.population.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
        
        best = self.population[0].fitness_score if self.population else 0
        avg = sum((c.fitness_score or 0) for c in self.population) / len(self.population) if self.population else 0
        self.best_fitness_history.append(best)
        
        self.history.append({
            "generation": self.generation,
            "best_fitness": best,
            "avg_fitness": round(avg, 4),
            "population_size": len(self.population),
            "best_strategy_id": self.population[0].chromosome_id if self.population else None,
        })
        
        if verbose:
            print(f"\n   🏆 Best: {best:.4f} | Avg: {avg:.4f} | Top: {self.population[0].chromosome_id[:8]}")
    
    def select_parent(self) -> StrategyChromosome:
        """
        錦標賽選擇 — 從 population 中隨機抽 N 個，取最好的
        """
        tournament_size = min(self.config["tournament_size"], len(self.population))
        contestants = random.sample(self.population, tournament_size)
        return max(contestants, key=lambda c: c.fitness_score or 0.0)
    
    def evolve(self, verbose: bool = True) -> None:
        """
        演化一代：淘汰 + 繁殖
        """
        if not self.population:
            raise ValueError("Population is empty. Call genesis() first.")
        
        # 標記精英（直接保留）
        elite_count = min(self.config["elite_count"], len(self.population))
        elites = self.population[:elite_count]
        
        # 淘汰
        cull_ratio = self.config["cull_ratio"]
        min_fitness = self.config["min_fitness_to_survive"]
        
        survivors = []
        for chrom in self.population:
            fit = chrom.fitness_score or 0.0
            # 精英自動存活
            if chrom in elites:
                survivors.append(chrom)
                continue
            # 分數太低直接淘汰
            if fit < min_fitness:
                continue
            # 按排名淘汰
            rank = self.population.index(chrom) / len(self.population)
            if rank < (1 - cull_ratio):
                survivors.append(chrom)
        
        # 確保至少保留一些
        if len(survivors) < self.config["population_size"] // 4:
            survivors = self.population[:max(5, self.config["population_size"] // 4)]
        
        # 繁殖填補
        offspring = []
        target_size = self.config["population_size"]
        
        while len(survivors) + len(offspring) < target_size:
            roll = random.random()
            
            if roll < self.config["crossover_rate"] and len(survivors) >= 2:
                # 交叉
                p1 = self.select_parent()
                p2 = self.select_parent()
                if p1.chromosome_id != p2.chromosome_id:
                    child = crossover_chromosomes(p1, p2, self.generation + 1)
                    if validate_chromosome(child):
                        offspring.append(child)
                        continue
            
            # 突變或全新
            if roll < self.config["crossover_rate"] + self.config["mutation_rate"]:
                # 突變
                parent = self.select_parent()
                child = mutate_chromosome(
                    parent,
                    self.generation + 1,
                    self.config["mutation_rate"],
                    self.config["mutation_intensity"],
                )
                if validate_chromosome(child):
                    offspring.append(child)
            else:
                # 全新隨機（維持多樣性）
                child = random_chromosome(generation=self.generation + 1)
                if validate_chromosome(child):
                    offspring.append(child)
        
        # 更新世代
        self.population = survivors + offspring
        self.generation += 1
        
        # 清除 fitness（新世代需要重新評估）
        for chrom in self.population:
            chrom.fitness_score = None
            chrom.fitness_details = {}
        
        if verbose:
            print(f"   🔄 Evolved to Gen {self.generation}: {len(survivors)} survivors + {len(offspring)} offspring")
    
    def run(
        self,
        max_generations: Optional[int] = None,
        verbose: bool = True,
        parallel_workers: int = 2,
    ) -> StrategyChromosome:
        """
        運行完整演化循環，返回最佳策略。
        
        Args:
            max_generations: 最大世代數
            verbose: 是否輸出詳細日誌
            parallel_workers: 並行評估的 worker 數量
        """
        max_gen = max_generations or self.config["max_generations"]
        report_every = self.config.get("report_every_n_generations", 10)
        
        if not self.population:
            self.genesis()
        
        print(f"\n{'='*60}")
        print(f"🧬 EVOLUTION START")
        print(f"{'='*60}")
        print(f"Population: {self.config['population_size']}")
        print(f"Elites: {self.config['elite_count']}")
        print(f"Cull Ratio: {self.config['cull_ratio']}")
        print(f"Mutation Rate: {self.config['mutation_rate']}")
        print(f"Symbols: {len(self.config['symbols'])}")
        print(f"Filter: PnL>{self.config['filter_min_pnl']}, DD<{self.config['filter_max_drawdown']}, Trades>{self.config['filter_min_trades']}, WR>{self.config['filter_min_win_rate']}")
        print(f"{'='*60}\n")
        
        best_ever = None
        best_fitness_ever = 0.0
        stagnation_count = 0
        
        for gen in range(max_gen):
            # 評估 — 大規模用並行
            if len(self.population) >= 100:
                self.evaluate_generation_parallel(max_workers=parallel_workers, verbose=verbose)
            else:
                self.evaluate_generation(verbose=verbose)
            
            # 更新歷史最佳
            current_best = self.population[0]
            current_best_fit = current_best.fitness_score or 0.0
            
            if current_best_fit > best_fitness_ever + self.config["early_stop_threshold"]:
                best_fitness_ever = current_best_fit
                best_ever = current_best
                stagnation_count = 0
                
                # 保存最佳
                self._save_chromosome(current_best, f"gen_{gen}_best")
            else:
                stagnation_count += 1
            
            # 每 N 代報告最佳染色體詳細數據
            if (gen + 1) % report_every == 0 or gen == 0:
                self._report_best(gen, current_best)
            
            # 保存世代快照
            self._save_generation()
            
            # 早停檢查
            if stagnation_count >= self.config["early_stop_generations"]:
                print(f"\n⏹️ Early stop at Gen {gen} (no improvement for {stagnation_count} generations)")
                break
            
            # 演化到下一代
            if gen < max_gen - 1:
                self.evolve(verbose=verbose)
        
        # 最終輸出 TOP_20
        self._export_top_n(20)
        
        # 最終輸出
        print(f"\n{'='*60}")
        print(f"🏆 EVOLUTION COMPLETE")
        print(f"{'='*60}")
        if best_ever:
            print(f"Best Strategy: {best_ever.chromosome_id}")
            print(f"Fitness: {best_ever.fitness_score:.4f}")
            print(f"Details: {best_ever.fitness_details}")
            print(f"Summary: {best_ever.summary()}")
        
        return best_ever or (self.population[0] if self.population else None)
    
    def _report_best(self, gen: int, chrom: StrategyChromosome) -> None:
        """每 N 代回報最佳染色體的詳細數據"""
        print(f"\n📈 Generation {gen} — Best Strategy Report")
        print(f"   ID: {chrom.chromosome_id}")
        print(f"   Fitness: {chrom.fitness_score:.4f}")
        if chrom.fitness_details:
            for k, v in chrom.fitness_details.items():
                print(f"   {k}: {v}")
        
        # 檢查是否通過原始指標篩選
        if hasattr(chrom, '_agg_metrics'):
            passed = passes_raw_filter(chrom._agg_metrics, self.config)
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"   Raw Filter: {status}")
            m = chrom._agg_metrics
            print(f"      PnL: {m.total_pnl:.2%} | DD: {m.max_drawdown:.2%} | Trades: {m.total_trades} | WR: {m.win_rate:.1%}")
        print()
    
    def _export_top_n(self, n: int = 20) -> None:
        """輸出 TOP_N.json（按 fitness 排序，含詳細指標）"""
        self.population.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
        top_n = self.population[:n]
        
        export = []
        for chrom in top_n:
            data = chrom.to_dict()
            data["fitness_score"] = chrom.fitness_score
            data["fitness_details"] = chrom.fitness_details
            if hasattr(chrom, '_agg_metrics'):
                data["raw_metrics"] = {
                    "total_pnl": chrom._agg_metrics.total_pnl,
                    "max_drawdown": chrom._agg_metrics.max_drawdown,
                    "total_trades": chrom._agg_metrics.total_trades,
                    "win_rate": chrom._agg_metrics.win_rate,
                    "sharpe_ratio": chrom._agg_metrics.sharpe_ratio,
                    "profit_factor": chrom._agg_metrics.profit_factor,
                }
                data["passes_filter"] = passes_raw_filter(chrom._agg_metrics, self.config)
                chrom.passes_filter = data["passes_filter"]
            export.append(data)
        
        path = self.save_dir / "TOP_20.json"
        with open(path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "generation": self.generation,
                "total_evaluated": len(self.population),
                "top_strategies": export,
            }, f, indent=2, default=str)
        
        print(f"\n📁 TOP_{n}.json exported to {path}")
        passed_count = sum(1 for c in top_n if getattr(c, "passes_filter", False))
        print(f"   {passed_count}/{n} strategies pass raw filter")
    
    def get_top_strategies(self, n: int = 5) -> List[StrategyChromosome]:
        """獲取當前世代 Top N"""
        self.population.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
        return self.population[:n]
    
    def _save_chromosome(self, chrom: StrategyChromosome, label: str) -> None:
        """保存單個染色體"""
        path = self.save_dir / f"{label}_{chrom.chromosome_id}.json"
        with open(path, "w") as f:
            json.dump(chrom.to_dict(), f, indent=2)
    
    def _save_generation(self) -> None:
        """保存整個世代"""
        path = self.save_dir / f"generation_{self.generation}.json"
        data = {
            "generation": self.generation,
            "timestamp": datetime.now().isoformat(),
            "population": [c.to_dict() for c in self.population],
            "history": self.history,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def load_generation(self, gen: int) -> None:
        """載入指定世代"""
        path = self.save_dir / f"generation_{gen}.json"
        if not path.exists():
            raise FileNotFoundError(f"Generation {gen} not found")
        
        with open(path) as f:
            data = json.load(f)
        
        self.generation = data["generation"]
        self.population = [StrategyChromosome.from_dict(c) for c in data["population"]]
        self.history = data.get("history", [])
        print(f"📂 Loaded Generation {gen} with {len(self.population)} strategies")


# ═══════════════════════════════════════════════════════════════════════════════
# 持續演化模式（Continuous Evolution）
# ═══════════════════════════════════════════════════════════════════════════════

class ContinuousEvolution:
    """
    持續演化模式 — 不斷運行，定期汰換。
    
    這是用户要的「一直生成一直汰換」模式：
    - 每 X 小時執行一輪演化
    - 每次用「到目前為止」的全歷史數據回測
    - 自動將表現最好的部署到 Paper Trading
    - Paper Trading 表現差的自動被淘汰
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        live_pool_size: int = 5,
        evolution_interval_hours: float = 6.0,
        backtest_days: int = 180,
    ):
        self.config = config or {}
        self.live_pool_size = live_pool_size
        self.evolution_interval_hours = evolution_interval_hours
        self.backtest_days = backtest_days
        
        self.engine = EvolutionEngine(config=config)
        self.live_pool: List[StrategyChromosome] = []  # 當前部署的策略
        self.paper_results: Dict[str, Dict[str, Any]] = {}  # 紙上交易結果
        self.running = False
    
    def start(self) -> None:
        """啟動持續演化循環"""
        self.running = True
        
        print(f"\n🔄 Continuous Evolution Started")
        print(f"   Evolution every: {self.evolution_interval_hours}h")
        print(f"   Live pool size: {self.live_pool_size}")
        print(f"   Backtest window: {self.backtest_days} days")
        
        # 初始種群
        if not self.engine.population:
            self.engine.genesis()
        
        cycle = 0
        while self.running:
            cycle += 1
            print(f"\n{'='*60}")
            print(f"🔄 CYCLE {cycle} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"{'='*60}")
            
            # 1. 執行演化（若已經有 live pool，將其納入初始種群）
            if self.live_pool:
                # 將 live pool 策略注入種群（作為精英種子）
                self.engine.population.extend(self.live_pool)
                # 去重
                seen = set()
                unique = []
                for c in self.engine.population:
                    if c.chromosome_id not in seen:
                        seen.add(c.chromosome_id)
                        unique.append(c)
                self.engine.population = unique[:self.engine.config["population_size"]]
            
            # 2. 運行演化（較少世代，因為要頻繁運行）
            best = self.engine.run(max_generations=10, verbose=True)
            
            # 3. 更新 live pool
            top_strategies = self.engine.get_top_strategies(self.live_pool_size)
            self.live_pool = top_strategies
            
            # Stage 7: research results stay in the research pool.
            
            # 5. 等待下一輪
            if self.running:
                sleep_seconds = int(self.evolution_interval_hours * 3600)
                print(f"\n⏳ Sleeping for {self.evolution_interval_hours}h...")
                time.sleep(sleep_seconds)
    
    def stop(self) -> None:
        """停止持續演化"""
        self.running = False
        print("🛑 Continuous Evolution stopped")
    
    def _deploy_to_paper(self, strategies: List[StrategyChromosome]) -> None:
        """
        Disabled: only manually promoted V2 Champions may enter runtime.
        """
        raise RuntimeError("Direct GA deployment is disabled; manually Promote a Challenger.")

        # Legacy implementation retained below for migration reference only.
        from .converter import convert_to_strategy_json
        
        deployed = []
        for chrom in strategies:
            strategy_json = convert_to_strategy_json(chrom)
            deployed.append(strategy_json)
        
        # 保存為待部署配置
        save_path = Path("data/genetic_evolution/live_pool_strategies.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "cycle": len(self.history),
                "strategies": deployed,
            }, f, indent=2)
        
        print(f"\n📋 Deployed {len(deployed)} strategies to live pool config")
    
    @property
    def history(self) -> List[Dict[str, Any]]:
        return self.engine.history
