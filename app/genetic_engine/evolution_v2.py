#!/usr/bin/env python3
"""
Evolution Engine V2 / 基因算法主引擎 V2

核心改進：
1. 1-4-5 黃金配比初始化（10%舊神火種 / 40%伴生變異 / 50%外來移民）
2. 正交交叉（語義塊級互換）
3. 突變斜坡（stagnation-based mutation ramp）
4. 與 Archive 系統整合（Champion/Challenger/Retired）
5. 三層配置（Environment + Season + Combat Genes）

Reference: 《核心準則》第三篇章 5.1~5.6

Author: second_bot
Date: 2026-05-28
"""

import random
import math
import copy
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

from .chromosome_v2 import (
    StrategyChromosomeV2, random_chromosome_v2,
    mutate_chromosome_v2, crossover_chromosomes_v2,
    validate_chromosome_v2, MacroGenes, MicroGenes
)
from .backtest_engine_v2 import GeneBacktestEngineV2, evaluate_chromosome_multi_symbol_v2, GhostDCABaseline
from .windows import (
    WINDOWS, WINDOW_WEIGHTS, WindowResult,
    run_all_windows, aggregate_multi_symbol_windows, stable_window_seed,
)
from .fitness_v2 import (
    BacktestMetricsV2, compute_fitness_v2,
    compute_fitness_details_v2, aggregate_fitness_v2,
    calculate_monte_carlo_report, compute_fitness_v2_from_v1
)
from .environment import (
    Environment, SeasonConfig, SeasonSampler,
    ThreeLayerConfig, SeasonApplier
)
from .archive import StrategyArchive, ArchiveRecord


# ═══════════════════════════════════════════════════════════════════════════════
# V2 配置
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG_V2 = {
    "population_size": 50,
    "elite_count": 5,  # backup cap (actual elite size computed via elite_ratio)
    "elite_ratio": 0.05,  # 5.2 EliteRatio: max(1, ceil(PopSize * ratio))
    "max_generations": 100,
    "mutation_rate": 0.4,
    "mutation_rate_max": 0.55,
    "crossover_rate": 0.6,
    "mutation_intensity": 0.3,
    "mutation_intensity_max": 0.6,
    "min_fitness_to_survive": 0.15,
    "cull_ratio": 0.5,
    "backtest_days": 90,
    "backtest_interval": "5m",
    "symbols": [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
    ],
    "tournament_size": 3,
    "diversity_pressure": 0.1,
    "early_stop_generations": 15,
    "early_stop_threshold": 0.001,
    
    # V2 新增
    "init_elite_ratio": 0.10,      # 10% 舊神火種
    "init_mutant_ratio": 0.40,     # 40% 伴生變異
    "init_explorer_ratio": 0.50,   # 50% 外來移民
    "mutation_ramp_factor": 1.25,  # 停滯時突變放大因子
    "stagnation_ramp_threshold": 5,  # 連續 N 代無改善開始 ramp
    "use_orthogonal_crossover": True,
    "use_multi_window": True,
    "windows": ["all", "5y", "2y", "6m"],  # 坩堝多窗
    # Maximum lookback for the "all" window. Non-strict boundary validation is
    # intentional because symbols listed less than ten years ago start later.
    "multi_window_history_days": 10 * 365,
    "n_season_segments": 4,
    "ruin_probability_warn_threshold": 0.05,  # 3rd-chapter: Monte Carlo final-review warn level
    "monte_carlo_interval": "1m",
    "monte_carlo_history_days": 90,
    "monte_carlo_simulations": 1000,
    "monte_carlo_seed": 42,
}


# ═══════════════════════════════════════════════════════════════════════════════
# V2 演化引擎
# ═══════════════════════════════════════════════════════════════════════════════

class EvolutionEngineV2:
    """
    V2 策略基因池演化引擎
    
    每一世代：
    1. 評估所有個體（多窗回測 + 季節摩擦）
    2. 排序，標記精英
    3. 淘汰底部個體
    4. 1-4-5 配比繁殖填補
    5. 突變斜坡調整
    6. 保存挑戰者
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        engine: Optional[GeneBacktestEngineV2] = None,
        save_dir: Optional[str] = None,
        archive: Optional[StrategyArchive] = None,
    ):
        self.config = {**DEFAULT_CONFIG_V2, **(config or {})}
        self.backtest_engine = engine or GeneBacktestEngineV2()
        self.population: List[StrategyChromosomeV2] = []
        self.generation = 0
        self.epoch_id = f"epoch_{random.randint(10000, 99999)}"
        self.history: List[Dict[str, Any]] = []
        self.best_fitness_history: List[float] = []
        
        # V2 三層配置
        self.three_layer = ThreeLayerConfig.create_for_new_epoch(
            n_season_segments=self.config["n_season_segments"]
        )
        self.three_layer.epoch_id = self.epoch_id
        
        # 檔案館
        self.archive = archive or StrategyArchive()
        
        # 保存路徑
        self.save_dir = Path(save_dir) if save_dir else Path("data/genetic_evolution_v2")
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # 突變斜坡狀態
        self.current_mutation_rate = self.config["mutation_rate"]
        self.current_mutation_intensity = self.config["mutation_intensity"]
        self.stagnation_count = 0

    def start_new_epoch(self) -> None:
        """Resample the shared environment once, then keep it fixed for the epoch."""
        previous_environment = self.three_layer.environment
        self.epoch_id = f"epoch_{random.randint(10000, 99999)}"
        self.three_layer = ThreeLayerConfig.create_for_new_epoch(
            prev_env=previous_environment,
            n_season_segments=self.config["n_season_segments"],
        )
        self.three_layer.epoch_id = self.epoch_id
        self.generation = 0
        self.history = []
        self.best_fitness_history = []
        for chrom in self.population:
            chrom.epoch_id = self.epoch_id
            chrom.fitness_score = None
            chrom.fitness_details = {}
    
    # ═══════════════════════════════════════════════════════
    # 1-4-5 黃金配比初始化
    # ═══════════════════════════════════════════════════════
    
    def genesis_v2(self, n: Optional[int] = None) -> List[StrategyChromosomeV2]:
        """
        V2 創世 — 1-4-5 黃金配比
        
        10% 舊神火種：從檔案館注入精英
        40% 伴生變異：精英拷貝 + 加大尺度突變
        50% 外來移民：合法盒內均勻隨機
        """
        size = n or self.config["population_size"]
        
        n_elite = max(1, int(size * self.config["init_elite_ratio"]))
        n_mutant = int(size * self.config["init_mutant_ratio"])
        n_explorer = size - n_elite - n_mutant
        
        print(f"🌱 Genesis V2: {size} strategies")
        print(f"   10% Incumbent Elites: {n_elite}")
        print(f"   40% Targeted Mutants: {n_mutant}")
        print(f"   50% Explorers: {n_explorer}")
        
        population = []
        
        # 10% 舊神火種
        elite_seeds = self.archive.get_elite_seeds(top_n=n_elite * 2)
        for i, seed_data in enumerate(elite_seeds[:n_elite]):
            try:
                chrom = StrategyChromosomeV2.from_dict(seed_data)
                chrom.generation = 0
                chrom.epoch_id = self.epoch_id
                chrom.fitness_score = None
                if validate_chromosome_v2(chrom):
                    population.append(chrom)
                    print(f"   🔥 Elite seed {i+1}: {chrom.chromosome_id[:8]}")
            except Exception as e:
                print(f"   ⚠️ Elite seed failed: {e}")
        
        # 如果檔案館種子不足，回退到隨機
        while len(population) < n_elite:
            chrom = random_chromosome_v2(generation=0)
            chrom.epoch_id = self.epoch_id
            if validate_chromosome_v2(chrom):
                population.append(chrom)
        
        # 40% 伴生變異：在隨機選中的精英上施加加大尺度突變
        source_elites = random.sample(population[:n_elite], min(n_mutant, n_elite))
        for i in range(n_mutant):
            source = random.choice(source_elites)
            # 加大突變尺度（1.5 倍）
            mutant = mutate_chromosome_v2(
                source, generation=0,
                mutation_rate=self.config["mutation_rate"],
                intensity=self.config["mutation_intensity"] * 1.5,
            )
            mutant.chromosome_id = f"MUT_{random.randint(100000, 999999)}"
            mutant.epoch_id = self.epoch_id
            if validate_chromosome_v2(mutant):
                population.append(mutant)
        
        # 50% 外來移民：均勻隨機全新個體
        attempts = 0
        while len(population) < size and attempts < size * 3:
            chrom = random_chromosome_v2(generation=0)
            chrom.epoch_id = self.epoch_id
            if validate_chromosome_v2(chrom):
                population.append(chrom)
            attempts += 1
        
        self.population = population[:size]
        self.generation = 0
        print(f"   ✓ {len(self.population)} valid strategies created")
        return self.population
    
    # ═══════════════════════════════════════════════════════
    # 世代評估（多窗 + 季節摩擦）
    # ═══════════════════════════════════════════════════════
    
    def evaluate_generation(self, verbose: bool = True) -> None:
        """評估當前世代（使用 V2 回測引擎和適應度）"""
        print(f"\n📊 Gen {self.generation} | Evaluating {len(self.population)} strategies...")
        
        for i, chrom in enumerate(self.population):
            if chrom.fitness_score is not None:
                continue
            
            if verbose:
                print(f"   [{i+1}/{len(self.population)}] {chrom.chromosome_id[:8]}...", end=" ")
            
            try:
                use_multi_window = self.config.get("use_multi_window", True)

                if use_multi_window:
                    # ── Stage 3: multi-window cross-validation ────────────────
                    # Fetch data ONCE per symbol; slice in-memory per window.
                    import time as _time
                    symbols = self.config["symbols"]
                    end_ms = int(_time.time() * 1000)
                    history_days = int(self.config["multi_window_history_days"])
                    start_ms = end_ms - history_days * 24 * 60 * 60 * 1000

                    all_window_results: List[WindowResult] = []
                    symbol_window_map: Dict[str, List[WindowResult]] = {}

                    for symbol in symbols:
                        # Fetch full history ONCE via cache — avoids re-hitting Binance per window
                        df_full, validation = self.backtest_engine.cache.load_or_fetch(
                            self.backtest_engine.fetcher,
                            symbol=symbol,
                            interval=self.config["backtest_interval"],
                            start_ms=start_ms,
                            end_ms=end_ms,
                            limit=1000,
                            paginate=True,
                            strict_validation=False,
                        )
                        if (
                            df_full is None
                            or validation is None
                            or not validation.get("valid", False)
                            or validation.get("data_invalid", False)
                        ):
                            # Mark all windows as insufficient for this symbol
                            failed_results = [
                                WindowResult(w, insufficient_data=True, weight=WINDOW_WEIGHTS[w])
                                for w in WINDOWS
                            ]
                            symbol_window_map[symbol] = failed_results
                            all_window_results.extend(failed_results)
                            continue

                        r_seed = stable_window_seed(
                            chrom.chromosome_id, self.epoch_id, self.generation
                        )
                        win_results = run_all_windows(
                            chromosome=chrom,
                            symbol_df=df_full,
                            end_ms=end_ms,
                            engine=self.backtest_engine,
                            seed=r_seed,
                            seasons=self.three_layer.seasons,
                            environment=self.three_layer.environment,
                        )
                        symbol_window_map[symbol] = win_results
                        all_window_results.extend(win_results)

                    fitness_score, per_symbol_fitness, failed_symbols = (
                        aggregate_multi_symbol_windows(symbol_window_map, symbols)
                    )

                    total_trades = 0
                    total_alpha = 0.0
                    per_window_summary: Dict[str, Any] = {}
                    for sym, wrs in symbol_window_map.items():
                        for wr in wrs:
                            if not wr.insufficient_data:
                                total_alpha += wr.alpha
                                total_trades += wr.details.get("n_trades", 0)
                            key = f"{sym}:{wr.window_name}"
                            per_window_summary[key] = {
                                "fitness": round(wr.fitness, 4),
                                "alpha": round(wr.alpha, 4),
                                "ghost_dca_return": round(wr.ghost_dca_return, 4),
                                "strategy_return": round(wr.strategy_return, 4),
                                "insufficient_data": wr.insufficient_data,
                                "n_candles": wr.n_candles,
                            }

                    n_valid = len([r for r in all_window_results if not r.insufficient_data])
                    avg_alpha = total_alpha / n_valid if n_valid > 0 else 0.0

                    chrom.fitness_score = fitness_score
                    chrom.fitness_details = {
                        "fitness": round(fitness_score, 4),
                        "avg_alpha": round(avg_alpha, 4),
                        "total_trades": total_trades,
                        "symbols_tested": len(symbols),
                        "windows_valid": n_valid,
                        "windows_total": len(all_window_results),
                        "per_symbol_fitness": per_symbol_fitness,
                        "failed_symbols": failed_symbols,
                        "insufficient_data": bool(failed_symbols),
                        "per_window": per_window_summary,
                        "stage": "stage3_multi_window",
                    }

                    if verbose:
                        print(f"Fit={fitness_score:.3f} Alpha={avg_alpha:+.3f} "
                              f"Trades={total_trades} Windows={n_valid}/{len(all_window_results)}")

                else:
                    # ── Stage 2: single-window multi-symbol (original) ────────
                    fitness, per_symbol, all_trades = evaluate_chromosome_multi_symbol_v2(
                        chrom,
                        symbols=self.config["symbols"],
                        engine=self.backtest_engine,
                        interval=self.config["backtest_interval"],
                        days=self.config["backtest_days"],
                        seasons=self.three_layer.seasons,
                        environment=self.three_layer.environment,
                        verbose=False,
                    )

                    fitness_score = fitness

                    total_trades = 0
                    total_alpha = 0.0
                    total_friction = 0.0

                    for symbol, result in per_symbol.items():
                        total_trades += result.strategy_metrics.total_trades
                        total_alpha += result.alpha_vs_dca
                        total_friction += result.friction_penalty

                    avg_alpha = total_alpha / len(per_symbol) if per_symbol else 0.0

                    chrom.fitness_score = fitness_score
                    chrom.fitness_details = {
                        "fitness": round(fitness_score, 4),
                        "avg_alpha": round(avg_alpha, 4),
                        "total_trades": total_trades,
                        "total_friction": round(total_friction, 4),
                        "symbols_tested": len(per_symbol),
                        "seasons_applied": len(self.three_layer.seasons),
                    }

                    if verbose:
                        print(f"Fit={fitness_score:.3f} Alpha={avg_alpha:+.3f} Trades={total_trades}")
                
            except Exception as e:
                if verbose:
                    print(f"ERROR: {e}")
                chrom.fitness_score = 0.0
                chrom.fitness_details = {"error": str(e)}
        
        # 排序
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
            "best_summary": self.population[0].summary() if self.population else None,
            "mutation_rate": round(self.current_mutation_rate, 3),
            "mutation_intensity": round(self.current_mutation_intensity, 3),
            "epoch_id": self.epoch_id,
            "three_layer": self.three_layer.to_dict(),
        })
        
        if verbose:
            print(f"\n   🏆 Best: {best:.4f} | Avg: {avg:.4f} | Top: {self.population[0].chromosome_id[:8]}")
            if self.population:
                print(f"   {self.population[0].summary()}")
    
    # ═══════════════════════════════════════════════════════
    # 突變斜坡（Mutation Ramp）
    # ═══════════════════════════════════════════════════════
    
    def apply_mutation_ramp(self) -> None:
        """
        突變斜坡：連續多代無顯著改善時，上調突變概率與幅度
        """
        ramp_threshold = self.config["stagnation_ramp_threshold"]
        ramp_factor = self.config["mutation_ramp_factor"]
        
        if self.stagnation_count >= ramp_threshold:
            old_rate = self.current_mutation_rate
            old_intensity = self.current_mutation_intensity
            
            self.current_mutation_rate = min(
                self.config["mutation_rate_max"],
                self.current_mutation_rate * ramp_factor
            )
            self.current_mutation_intensity = min(
                self.config["mutation_intensity_max"],
                self.current_mutation_intensity * ramp_factor
            )
            
            print(f"   🔥 Mutation RAMP! Rate: {old_rate:.2f}→{self.current_mutation_rate:.2f} | "
                  f"Intensity: {old_intensity:.2f}→{self.current_mutation_intensity:.2f}")
    
    def reset_mutation_ramp(self) -> None:
        """改善出現時，重置突變參數"""
        self.current_mutation_rate = self.config["mutation_rate"]
        self.current_mutation_intensity = self.config["mutation_intensity"]
        self.stagnation_count = 0
    
    # ═══════════════════════════════════════════════════════
    # 正交選擇與繁殖
    # ═══════════════════════════════════════════════════════
    
    def select_parent(self) -> StrategyChromosomeV2:
        """錦標賽選擇"""
        tournament_size = min(self.config["tournament_size"], len(self.population))
        contestants = random.sample(self.population, tournament_size)
        return max(contestants, key=lambda c: c.fitness_score or 0.0)
    
    def evolve_v2(self, verbose: bool = True) -> None:
        """
        V2 演化一代：淘汰 + 1-4-5 配比繁殖
        """
        if not self.population:
            raise ValueError("Population empty. Call genesis_v2() first.")
        
        # 標記精英
        elite_ratio = self.config.get("elite_ratio", 0.05)
        elite_count = max(1, math.ceil(len(self.population) * elite_ratio))
        elite_count = min(elite_count, self.config["elite_count"], len(self.population))
        elites = self.population[:elite_count]
        
        # 淘汰
        cull_ratio = self.config["cull_ratio"]
        min_fitness = self.config["min_fitness_to_survive"]
        
        survivors = []
        for chrom in self.population:
            fit = chrom.fitness_score or 0.0
            if chrom in elites:
                survivors.append(chrom)
                continue
            if fit < min_fitness:
                continue
            rank = self.population.index(chrom) / len(self.population)
            if rank < (1 - cull_ratio):
                survivors.append(chrom)
        
        if len(survivors) < self.config["population_size"] // 4:
            survivors = self.population[:max(5, self.config["population_size"] // 4)]
        
        # 繁殖填補
        offspring = []
        target_size = self.config["population_size"]
        
        while len(survivors) + len(offspring) < target_size:
            roll = random.random()
            
            if roll < self.config["crossover_rate"] and len(survivors) >= 2:
                p1 = self.select_parent()
                p2 = self.select_parent()
                if p1.chromosome_id != p2.chromosome_id:
                    # crossover_chromosomes_v2 is itself the orthogonal-crossover implementation (5.3)
                    child = crossover_chromosomes_v2(p1, p2, self.generation + 1)
                    if validate_chromosome_v2(child):
                        offspring.append(child)
                        continue
            
            if roll < self.config["crossover_rate"] + self.current_mutation_rate:
                parent = self.select_parent()
                child = mutate_chromosome_v2(
                    parent,
                    self.generation + 1,
                    self.current_mutation_rate,
                    self.current_mutation_intensity,
                )
                if validate_chromosome_v2(child):
                    offspring.append(child)
            else:
                child = random_chromosome_v2(generation=self.generation + 1)
                child.epoch_id = self.epoch_id
                if validate_chromosome_v2(child):
                    offspring.append(child)
        
        self.population = survivors + offspring
        self.generation += 1
        
        for chrom in self.population:
            chrom.fitness_score = None
            chrom.fitness_details = {}
        
        if verbose:
            print(f"   🔄 Evolved to Gen {self.generation}: {len(survivors)} survivors + {len(offspring)} offspring")
    
    # ═══════════════════════════════════════════════════════
    # 完整演化循環
    # ═══════════════════════════════════════════════════════
    
    def run(
        self,
        max_generations: Optional[int] = None,
        verbose: bool = True,
    ) -> StrategyChromosomeV2:
        """運行完整 V2 演化循環"""
        max_gen = max_generations or self.config["max_generations"]
        
        if not self.population:
            self.genesis_v2()
        
        print(f"\n{'='*70}")
        print(f"🧬 EVOLUTION V2 START | Epoch: {self.epoch_id}")
        print(f"{'='*70}")
        print(f"Population: {self.config['population_size']}")
        print(f"Elites: {self.config['elite_count']}")
        print(f"Mutation: {self.config['mutation_rate']:.2f} (max {self.config['mutation_rate_max']:.2f})")
        print(f"Crossover: {self.config['crossover_rate']:.2f}")
        print(f"Init: 10% Elite / 40% Mutant / 50% Explorer")
        print(f"Symbols: {len(self.config['symbols'])}")
        print(f"{'='*70}\n")
        
        best_ever = None
        best_fitness_ever = 0.0
        
        for gen in range(max_gen):
            self.evaluate_generation(verbose=verbose)
            
            current_best = self.population[0]
            current_best_fit = current_best.fitness_score or 0.0
            
            if current_best_fit > best_fitness_ever + self.config["early_stop_threshold"]:
                best_fitness_ever = current_best_fit
                best_ever = copy.deepcopy(current_best)
                self.stagnation_count = 0
                self.reset_mutation_ramp()
                self._save_chromosome(current_best, f"gen_{gen}_best")
            else:
                self.stagnation_count += 1
                self.apply_mutation_ramp()
            
            self._save_generation()
            
            if self.stagnation_count >= self.config["early_stop_generations"]:
                print(f"\n⏹️ Early stop at Gen {gen} (no improvement for {self.stagnation_count} gen)")
                break
            
            if gen < max_gen - 1:
                self.evolve_v2(verbose=verbose)
        
        # Epoch 結束：最佳個體作為挑戰者寫入檔案館
        if best_ever:
            fitness_before_review = best_ever.fitness_score
            try:
                report = self._run_monte_carlo_final_review(best_ever)
                best_ever.fitness_details["monte_carlo_final_review"] = report
                ruin_prob = report.get("ruin_probability")
                warn_threshold = self.config.get("ruin_probability_warn_threshold", 0.05)
                if ruin_prob is None:
                    print("  Monte Carlo final review: insufficient 1m trade samples")
                elif ruin_prob > warn_threshold:
                    print(f"  \u26a0\ufe0f Warn: Ruin probability {ruin_prob:.4f} exceeds threshold {warn_threshold:.4f} (fitness unchanged)")
                else:
                    print(f"  Monte Carlo final review: ruin probability = {ruin_prob:.4f}")
            except Exception as e:
                best_ever.fitness_details["monte_carlo_final_review"] = {
                    "error": str(e),
                    "interval": "1m",
                }
                print(f"  Monte Carlo final review failed: {e}")
            finally:
                best_ever.fitness_score = fitness_before_review
            self._archive_challenger(best_ever)
        
        print(f"\n{'='*70}")
        print(f"🏆 EVOLUTION V2 COMPLETE")
        print(f"{'='*70}")
        if best_ever:
            print(f"Best: {best_ever.chromosome_id[:8]} | Fitness: {best_fitness_ever:.4f}")
            print(f"Summary: {best_ever.summary()}")
        
        return best_ever or (self.population[0] if self.population else None)

    def _run_monte_carlo_final_review(
        self,
        challenger: StrategyChromosomeV2,
    ) -> Dict[str, Any]:
        """Run once per Epoch on the final Challenger using the complete 1m sample."""
        interval = self.config.get("monte_carlo_interval", "1m")
        if interval != "1m":
            raise ValueError("Monte Carlo final review interval must be 1m")

        days = int(self.config.get("monte_carlo_history_days", 90))
        _, _, trades = evaluate_chromosome_multi_symbol_v2(
            challenger,
            symbols=self.config["symbols"],
            engine=self.backtest_engine,
            interval=interval,
            days=days,
            seasons=self.three_layer.seasons,
            environment=self.three_layer.environment,
            verbose=False,
        )
        report = calculate_monte_carlo_report(
            [{"pnl_pct": t.pnl_pct} for t in trades],
            initial_capital=self.backtest_engine.initial_capital,
            n_simulations=int(self.config.get("monte_carlo_simulations", 1000)),
            seed=int(self.config.get("monte_carlo_seed", 42)),
        )
        report.update({
            "interval": interval,
            "history_days": days,
            "symbols": list(self.config["symbols"]),
            "fitness_unchanged": True,
        })
        return report
    
    # ═══════════════════════════════════════════════════════
    # 保存與檔案
    # ═══════════════════════════════════════════════════════
    
    def _save_chromosome(self, chrom: StrategyChromosomeV2, label: str) -> None:
        path = self.save_dir / f"{label}_{chrom.chromosome_id}.json"
        with open(path, "w") as f:
            json.dump(chrom.to_dict(), f, indent=2)
    
    def _save_generation(self) -> None:
        path = self.save_dir / f"generation_{self.generation}.json"
        data = {
            "generation": self.generation,
            "epoch_id": self.epoch_id,
            "timestamp": datetime.now().isoformat(),
            "three_layer": self.three_layer.to_dict(),
            "population": [c.to_dict() for c in self.population],
            "history": self.history,
            "mutation_rate": self.current_mutation_rate,
            "mutation_intensity": self.current_mutation_intensity,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _archive_challenger(self, chrom: StrategyChromosomeV2) -> None:
        """將最佳個體存為挑戰者"""
        record = ArchiveRecord(
            chromosome_id=chrom.chromosome_id,
            status="challenger",
            epoch_id=self.epoch_id,
            generation=self.generation,
            fitness_score=chrom.fitness_score or 0.0,
            fitness_details=chrom.fitness_details,
            chromosome_data=chrom.to_dict(),
        )
        self.archive.add_challenger(record, chrom.symbol)
        print(f"\n📋 Challenger archived: {chrom.chromosome_id[:8]} (fit={chrom.fitness_score:.4f})")
    
    def get_top_strategies(self, n: int = 5) -> List[StrategyChromosomeV2]:
        self.population.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
        return self.population[:n]
    
    def promote_best_to_champion(self, symbol: str = "default") -> bool:
        """將當前最佳提升為冠軍"""
        if not self.population:
            return False
        best = self.population[0]
        return self.archive.promote_challenger(best.chromosome_id, symbol)


# ═══════════════════════════════════════════════════════════════════════════════
# 持續演化模式 V2
# ═══════════════════════════════════════════════════════════════════════════════

class ContinuousEvolutionV2:
    """
    V2 持續演化模式
    
    - 每 X 小時執行一輪（較短世代數）
    - 每次用全歷史數據回測
    - Epoch 最佳只進 Challenger，不會自動部署
    - 表現差的自動淘汰，從基因池補新血
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
        
        self.engine = EvolutionEngineV2(config=config)
        self.live_pool: List[StrategyChromosomeV2] = []
        self.running = False
    
    def start(self) -> None:
        self.running = True
        
        print(f"\n🔄 Continuous Evolution V2 Started")
        print(f"   Interval: {self.evolution_interval_hours}h")
        print(f"   Live pool: {self.live_pool_size}")
        print(f"   Backtest: {self.backtest_days} days")
        
        if not self.engine.population:
            self.engine.genesis_v2()
        
        cycle = 0
        while self.running:
            cycle += 1
            if cycle > 1:
                self.engine.start_new_epoch()
            print(f"\n{'='*60}")
            print(f"🔄 CYCLE {cycle} | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"{'='*60}")
            
            if self.live_pool:
                self.engine.population.extend(self.live_pool)
                seen = set()
                unique = []
                for c in self.engine.population:
                    if c.chromosome_id not in seen:
                        seen.add(c.chromosome_id)
                        unique.append(c)
                self.engine.population = unique[:self.engine.config["population_size"]]
            
            best = self.engine.run(max_generations=10, verbose=True)
            
            # Research continuity only. These strategies remain candidates and
            # must never become runtime strategies without manual Promote.
            self.live_pool = self.engine.get_top_strategies(self.live_pool_size)
            
            if self.running:
                sleep_seconds = int(self.evolution_interval_hours * 3600)
                print(f"\n⏳ Sleeping {self.evolution_interval_hours}h...")
                time.sleep(sleep_seconds)
    
    def stop(self) -> None:
        self.running = False
        print("🛑 Continuous Evolution V2 stopped")
    
    def _deploy_to_paper(self, strategies: Optional[List[StrategyChromosomeV2]] = None) -> None:
        """Write only the promoted Champion, or the deterministic fallback."""
        from .converter import convert_to_strategy_json

        chrom = StrategyChromosomeV2.from_dict(
            self.engine.archive.get_runtime_chromosome_data("default")
        )
        deployed = [convert_to_strategy_json(chrom)]
        
        save_path = Path("data/genetic_evolution_v2/live_pool_strategies.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "cycle": len(self.engine.history),
                "epoch_id": self.engine.epoch_id,
                "strategies": deployed,
            }, f, indent=2)
        
        print(f"\n📋 Runtime strategy refreshed from Champion/default")


if __name__ == "__main__":
    print("=== Evolution V2 Module Loaded ===")
    print(f"Config: population={DEFAULT_CONFIG_V2['population_size']}")
    print(f"Init: {DEFAULT_CONFIG_V2['init_elite_ratio']:.0%} elite / "
          f"{DEFAULT_CONFIG_V2['init_mutant_ratio']:.0%} mutant / "
          f"{DEFAULT_CONFIG_V2['init_explorer_ratio']:.0%} explorer")
