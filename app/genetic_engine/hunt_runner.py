#!/usr/bin/env python3
"""
Hunt Mode Runner — 持續基因演化任務

配置：
- 模式：Hunt Mode（交叉突變，非純隨機）
- 種群大小：500
- 每輪世代：50代
- 間隔：每6小時自動跑一輪
- 篩選：PnL>0, 回撤<20%, 勝率>40%, 交易>20
- 輸出：每輪 TOP_20.json
- 通知：Discord Webhook
- 自動部署：fitness > 0.377 時自動部署替換

用法:
    cd kimi-shared-brain
    nohup python3 app/genetic_engine/hunt_runner.py > logs/hunt_runner.log 2>&1 &

Author: second_bot
Date: 2026-06-02
"""

import os
import sys
import fcntl
import time
import random
import requests
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.genetic_engine.chromosome import (
    StrategyChromosome, random_chromosome,
    mutate_chromosome, crossover_chromosomes, validate_chromosome
)
from app.genetic_engine.backtest_engine import (
    GeneBacktestEngine, evaluate_chromosome_multi_symbol
)
from app.genetic_engine.fitness import BacktestMetrics, compute_fitness
from app.genetic_engine.converter import convert_to_strategy_json

# ── 配置 ──────────────────────────────────────────────────────────────────────

CONFIG = {
    "population_size": 500,           # 種群大小 500
    "elite_count": 20,               # 10%
    "max_generations": 50,
    "mutation_rate": 0.4,
    "crossover_rate": 0.6,
    "mutation_intensity": 0.3,
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
    "report_every_n_generations": 10,

    # 篩選標準
    "filter_min_pnl": 0.0,
    "filter_max_drawdown": 0.20,
    "filter_min_trades": 20,
    "filter_min_win_rate": 0.40,

    # 部署門檻
    "deploy_threshold_fitness": 0.377,
    "deploy_threshold_id": "MUT_DAC146EA58C9",

    # 間隔
    "round_interval_hours": 6,
    "parallel_workers": 1,  # 降低為 1 避免 OOM（原 2）
}

SAVE_DIR = BASE_DIR / "data" / "genetic_evolution"
SAVE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Discord Webhook
WEBHOOK_URL = None


def load_discord_webhook():
    """載入 Discord Webhook URL"""
    global WEBHOOK_URL
    try:
        config_path = BASE_DIR / "config" / "channel_config.json"
        if config_path.exists():
            with open(config_path) as f:
                cfg = json.load(f)
                WEBHOOK_URL = cfg.get("webhook_url")
    except Exception as e:
        print(f"⚠️ Failed to load webhook: {e}")
    return WEBHOOK_URL


def send_discord(title: str, message: str, color: int = 0x00ff00) -> bool:
    """發送 Discord 通知"""
    if not WEBHOOK_URL:
        print(f"[Discord skipped] {title}: {message[:100]}")
        return False

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
            "footer": {"text": "Hunt Mode Runner"}
        }]
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"⚠️ Discord send failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合指標
# ═══════════════════════════════════════════════════════════════════════════════

def aggregate_metrics(per_symbol):
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
        total_trades=total_trades, winning_trades=total_wins,
        losing_trades=total_trades - total_wins, win_rate=win_rate,
        total_pnl=avg_pnl, max_drawdown=avg_dd,
        sharpe_ratio=avg_sharpe, profit_factor=avg_pf,
    )


def passes_filter(metrics, config):
    return (
        metrics.total_pnl > config.get("filter_min_pnl", 0.0)
        and metrics.max_drawdown < config.get("filter_max_drawdown", 0.20)
        and metrics.total_trades > config.get("filter_min_trades", 20)
        and metrics.win_rate > config.get("filter_min_win_rate", 0.40)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 演化引擎
# ═══════════════════════════════════════════════════════════════════════════════

class HuntEngine:
    def __init__(self, config):
        self.config = config
        self.population = []
        self.generation = 0
        self.history = []
        self.best_fitness_history = []
        self.save_dir = SAVE_DIR
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def genesis(self, n=None):
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

    def seed_with_previous(self, previous_best):
        """將上一輪最佳策略注入種群"""
        if not previous_best:
            return
        print(f"📌 Seeding with previous best: {previous_best.chromosome_id[:16]} fit={previous_best.fitness_score:.4f}")
        # 將前輪最佳作為精英種子加入
        self.population.insert(0, previous_best)
        # 去重
        seen = set()
        unique = []
        for c in self.population:
            if c.chromosome_id not in seen:
                seen.add(c.chromosome_id)
                unique.append(c)
        self.population = unique[:self.config["population_size"]]
        print(f"   Seeded population: {len(self.population)}")

    def evaluate_parallel(self, max_workers=2, verbose=True):
        print(f"\n📊 Generation {self.generation}: Parallel evaluating {len(self.population)} strategies (workers={max_workers})...")
        to_eval = [(i, chrom) for i, chrom in enumerate(self.population) if chrom.fitness_score is None]
        if not to_eval:
            print("   All already evaluated.")
            return

        completed = 0
        total = len(to_eval)

        def _eval_one(args):
            idx, chrom = args
            try:
                engine = GeneBacktestEngine()
                fitness, per_symbol, trades = evaluate_chromosome_multi_symbol(
                    chrom, symbols=self.config["symbols"], engine=engine,
                    interval=self.config["backtest_interval"], days=self.config["backtest_days"], verbose=False,
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
                        "profit_factor": round(agg_metrics.profit_factor, 4),
                        "symbols_tested": len(per_symbol),
                    }
                    chrom._agg_metrics = agg_metrics
                completed += 1
                if verbose and completed % 50 == 0:
                    print(f"   [{completed}/{total}] evaluated...")

        self.population.sort(key=lambda c: c.fitness_score or 0.0, reverse=True)
        best = self.population[0].fitness_score if self.population else 0
        avg = sum((c.fitness_score or 0) for c in self.population) / len(self.population) if self.population else 0
        self.best_fitness_history.append(best)
        passed = sum(1 for c in self.population if hasattr(c, '_agg_metrics') and passes_filter(c._agg_metrics, self.config))
        self.history.append({
            "generation": self.generation, "best_fitness": best,
            "avg_fitness": round(avg, 4), "population_size": len(self.population),
            "best_strategy_id": self.population[0].chromosome_id if self.population else None,
            "passed_filter": passed,
        })
        print(f"\n   🏆 Best: {best:.4f} | Avg: {avg:.4f} | Passed: {passed}/{len(self.population)} | Top: {self.population[0].chromosome_id[:8]}")

    def select_parent(self):
        tournament_size = min(self.config["tournament_size"], len(self.population))
        contestants = random.sample(self.population, tournament_size)
        return max(contestants, key=lambda c: c.fitness_score or 0.0)

    def evolve(self, verbose=True):
        if not self.population:
            raise ValueError("Population empty")
        elite_count = min(self.config["elite_count"], len(self.population))
        elites = self.population[:elite_count]
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

        offspring = []
        target_size = self.config["population_size"]
        while len(survivors) + len(offspring) < target_size:
            roll = random.random()
            if roll < self.config["crossover_rate"] and len(survivors) >= 2:
                p1 = self.select_parent()
                p2 = self.select_parent()
                if p1.chromosome_id != p2.chromosome_id:
                    child = crossover_chromosomes(p1, p2, self.generation + 1)
                    if validate_chromosome(child):
                        offspring.append(child)
                        continue
            if roll < self.config["crossover_rate"] + self.config["mutation_rate"]:
                parent = self.select_parent()
                child = mutate_chromosome(parent, self.generation + 1, self.config["mutation_rate"], self.config["mutation_intensity"])
                if validate_chromosome(child):
                    offspring.append(child)
            else:
                child = random_chromosome(generation=self.generation + 1)
                if validate_chromosome(child):
                    offspring.append(child)

        self.population = survivors + offspring
        self.generation += 1
        for chrom in self.population:
            chrom.fitness_score = None
            chrom.fitness_details = {}
        if verbose:
            print(f"   🔄 Evolved to Gen {self.generation}: {len(survivors)} survivors + {len(offspring)} offspring")

    def run(self, max_generations=None, verbose=True, parallel_workers=2):
        max_gen = max_generations or self.config["max_generations"]
        report_every = self.config.get("report_every_n_generations", 10)
        if not self.population:
            self.genesis()

        print(f"\n{'='*60}")
        print(f"🧬 HUNT MODE — Round Start")
        print(f"{'='*60}")
        print(f"Population: {self.config['population_size']}")
        print(f"Elites: {self.config['elite_count']}")
        print(f"Cull Ratio: {self.config['cull_ratio']}")
        print(f"Mutation Rate: {self.config['mutation_rate']}")
        print(f"Crossover Rate: {self.config['crossover_rate']}")
        print(f"Symbols: {len(self.config['symbols'])}")
        print(f"Filter: PnL>{self.config['filter_min_pnl']}, DD<{self.config['filter_max_drawdown']}, Trades>{self.config['filter_min_trades']}, WR>{self.config['filter_min_win_rate']}")
        print(f"Deploy Threshold: fitness > {self.config['deploy_threshold_fitness']}")
        print(f"{'='*60}\n")

        best_ever = None
        best_fitness_ever = 0.0
        stagnation_count = 0

        for gen in range(max_gen):
            self.evaluate_parallel(max_workers=parallel_workers, verbose=verbose)
            current_best = self.population[0]
            current_best_fit = current_best.fitness_score or 0.0

            if current_best_fit > best_fitness_ever + self.config["early_stop_threshold"]:
                best_fitness_ever = current_best_fit
                best_ever = current_best
                stagnation_count = 0
                self._save_chromosome(current_best, f"gen_{gen}_best")
            else:
                stagnation_count += 1

            if (gen + 1) % report_every == 0 or gen == 0:
                self._report_best(gen, current_best)

            self._save_generation()

            if stagnation_count >= self.config["early_stop_generations"]:
                print(f"\n⏹️ Early stop at Gen {gen} (no improvement for {stagnation_count} generations)")
                break

            if gen < max_gen - 1:
                self.evolve(verbose=verbose)

        self._export_top_n(20)
        print(f"\n{'='*60}")
        print(f"🏆 ROUND COMPLETE")
        print(f"{'='*60}")
        if best_ever:
            print(f"Best Strategy: {best_ever.chromosome_id}")
            print(f"Fitness: {best_ever.fitness_score:.4f}")
            print(f"Details: {best_ever.fitness_details}")
            print(f"Summary: {best_ever.summary()}")
        return best_ever or (self.population[0] if self.population else None)

    def _report_best(self, gen, chrom):
        print(f"\n📈 Generation {gen} — Best Strategy Report")
        print(f"   ID: {chrom.chromosome_id}")
        print(f"   Fitness: {chrom.fitness_score:.4f}")
        if chrom.fitness_details:
            for k, v in chrom.fitness_details.items():
                print(f"   {k}: {v}")
        if hasattr(chrom, '_agg_metrics'):
            passed = passes_filter(chrom._agg_metrics, self.config)
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"   Raw Filter: {status}")
            m = chrom._agg_metrics
            print(f"      PnL: {m.total_pnl:.2%} | DD: {m.max_drawdown:.2%} | Trades: {m.total_trades} | WR: {m.win_rate:.1%}")
        print()

    def _export_top_n(self, n=20):
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
                data["passes_filter"] = passes_filter(chrom._agg_metrics, self.config)
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
        passed_count = sum(1 for c in export if c.get("passes_filter"))
        print(f"   {passed_count}/{n} strategies pass raw filter")

    def _save_chromosome(self, chrom, label):
        path = self.save_dir / f"{label}_{chrom.chromosome_id}.json"
        with open(path, "w") as f:
            json.dump(chrom.to_dict(), f, indent=2)

    def _save_generation(self):
        path = self.save_dir / f"generation_{self.generation}.json"
        with open(path, "w") as f:
            json.dump({
                "generation": self.generation,
                "timestamp": datetime.now().isoformat(),
                "population": [c.to_dict() for c in self.population],
                "history": self.history,
            }, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# 自動部署
# ═══════════════════════════════════════════════════════════════════════════════

def deploy_strategy(chrom, config):
    """將染色體部署到 strategies.json 和 paper_trading_state.json（帶文件鎖）"""
    strategy_json = convert_to_strategy_json(chrom)
    strategy_id = strategy_json.get("id", chrom.chromosome_id.lower())

    # 1. 更新 strategies.json
    strategies_path = BASE_DIR / "config" / "strategies.json"
    if strategies_path.exists():
        with open(strategies_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                data = json.load(f)
                # 移除舊的基因策略（標記為 genetic 的）
                data["strategies"] = [s for s in data["strategies"] if not s.get("id", "").startswith("genetic_")]
                data["strategies"].append(strategy_json)
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2, default=str)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    else:
        data = {"version": "2.0.0", "strategies": [strategy_json]}
        with open(strategies_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # 2. 更新 paper_trading_state.json（帶文件鎖，防止 scheduler 並發覆蓋）
    state_path = BASE_DIR / "state" / "paper_trading_state.json"
    if state_path.exists():
        with open(state_path, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                state = json.load(f)
                # 移除舊的基因策略帳戶
                old_ids = [k for k in state.get("strategies", {}).keys() if k.startswith("genetic_")]
                for oid in old_ids:
                    del state["strategies"][oid]

                state["strategies"][strategy_id] = {
                    "balance": 1000.0,
                    "initial": 1000.0,
                    "positions": {},
                    "trades": [],
                }

                # 重新計算 total_initial
                total_initial = sum(s.get("initial", 1000) for s in state["strategies"].values())
                state["total_initial"] = total_initial
                state["last_updated"] = datetime.now().isoformat()

                f.seek(0)
                f.truncate()
                json.dump(state, f, indent=2, default=str)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    else:
        state = {
            "strategies": {
                strategy_id: {
                    "balance": 1000.0,
                    "initial": 1000.0,
                    "positions": {},
                    "trades": [],
                }
            },
            "total_initial": 1000,
            "last_updated": datetime.now().isoformat(),
            "daily_settlements": {}
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2, default=str)

    # Verify both files actually contain the strategy
    verify_ok = True
    with open(strategies_path, "r") as vf:
        vdata = json.load(vf)
        if strategy_id not in [s.get("id") for s in vdata.get("strategies", [])]:
            print(f"   ⚠️ strategies.json verification FAILED")
            verify_ok = False
    
    with open(state_path, "r") as vf:
        vstate = json.load(vf)
        if strategy_id not in vstate.get("strategies", {}):
            print(f"   ⚠️ paper_trading_state.json verification FAILED")
            verify_ok = False
    
    if verify_ok:
        print(f"\n🚀 DEPLOYED: {strategy_id}")
        print(f"   Fitness: {chrom.fitness_score:.4f}")
        print(f"   ✅ Verified in both strategies.json and paper_trading_state.json")
    else:
        print(f"\n⚠️ PARTIAL DEPLOY: {strategy_id} — verification failed, check logs")
    
    return strategy_id


# ═══════════════════════════════════════════════════════════════════════════════
# 主循環
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    load_discord_webhook()

    print(f"{'='*60}")
    print(f"🎯 HUNT MODE RUNNER")
    print(f"{'='*60}")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Config: pop={CONFIG['population_size']}, gen={CONFIG['max_generations']}, interval={CONFIG['round_interval_hours']}h")
    print(f"Deploy threshold: fitness > {CONFIG['deploy_threshold_fitness']}")
    print(f"Discord webhook: {'✅' if WEBHOOK_URL else '❌'}")
    print(f"{'='*60}\n")

    send_discord("🎯 Hunt Mode Started", f"Continuous evolution started.\nConfig: pop={CONFIG['population_size']}, gen={CONFIG['max_generations']}, interval={CONFIG['round_interval_hours']}h\nDeploy threshold: fitness > {CONFIG['deploy_threshold_fitness']}", color=0x00ff00)

    best_ever = None
    best_fitness_ever = 0.0
    round_num = 0

    while True:
        round_num += 1
        t_start = time.time()

        print(f"\n{'='*60}")
        print(f"🔁 ROUND {round_num} START — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        engine = HuntEngine(config=CONFIG)

        # 如果有上一輪最佳，注入種群
        if best_ever:
            engine.genesis()
            engine.seed_with_previous(best_ever)
        else:
            engine.genesis()

        # 執行演化
        round_best = engine.run(
            max_generations=CONFIG["max_generations"],
            verbose=True,
            parallel_workers=CONFIG["parallel_workers"],
        )

        t_elapsed = time.time() - t_start

        # 更新歷史最佳
        if round_best and (round_best.fitness_score or 0) > best_fitness_ever:
            best_fitness_ever = round_best.fitness_score or 0
            best_ever = round_best

        # 報告到 Discord
        if round_best:
            fit = round_best.fitness_score or 0
            msg = f"**Round {round_num} Complete**\n"
            msg += f"⏱ Time: {t_elapsed/60:.1f}min\n"
            msg += f"🏆 Best: `{round_best.chromosome_id[:16]}`\n"
            msg += f"📊 Fitness: `{fit:.4f}`\n"
            if hasattr(round_best, '_agg_metrics'):
                m = round_best._agg_metrics
                msg += f"💰 PnL: `{m.total_pnl:.2%}` | DD: `{m.max_drawdown:.2%}` | Trades: `{m.total_trades}` | WR: `{m.win_rate:.1%}`\n"
                msg += f"🎯 Sharpe: `{m.sharpe_ratio:.2f}` | PF: `{m.profit_factor:.2f}`\n"
                passed = passes_filter(m, CONFIG)
                msg += f"✅ Filter: {'PASSED' if passed else 'FAILED'}\n"
            msg += f"📈 Best Ever: `{best_fitness_ever:.4f}` (ID: `{best_ever.chromosome_id[:16] if best_ever else 'None'}`)\n"

            # 檢查是否應該部署
            if fit > CONFIG["deploy_threshold_fitness"]:
                msg += f"\n🚀 **DEPLOYING** — fitness {fit:.4f} > threshold {CONFIG['deploy_threshold_fitness']}\n"
                deployed_id = deploy_strategy(round_best, CONFIG)
                msg += f"Deployed as: `{deployed_id}`\n"
                send_discord(f"🚀 ROUND {round_num} — NEW WINNER DEPLOYED", msg, color=0xffd700)
            else:
                msg += f"\n⏸️ Not deploying — fitness {fit:.4f} ≤ threshold {CONFIG['deploy_threshold_fitness']}\n"
                send_discord(f"📊 ROUND {round_num} Complete", msg, color=0x3498db)

        # 輸出 TOP_20
        top20_path = SAVE_DIR / "TOP_20.json"

        # 等待下一輪
        sleep_seconds = CONFIG["round_interval_hours"] * 3600
        next_run = datetime.now() + timedelta(hours=CONFIG["round_interval_hours"])
        print(f"\n⏳ Sleeping until {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({CONFIG['round_interval_hours']}h)...")
        send_discord("⏳ Resting", f"Round {round_num} done. Next round at {next_run.strftime('%H:%M')}.", color=0x95a5a6)

        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user")
            send_discord("🛑 Stopped", "Hunt Mode interrupted by user.", color=0xe74c3c)
            break

    print(f"\n{'='*60}")
    print(f"🏁 HUNT MODE ENDED")
    print(f"Best Ever: {best_fitness_ever:.4f} — {best_ever.chromosome_id if best_ever else 'None'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        send_discord("💥 Hunt Mode Crashed", f"Error: {e}\n```\n{traceback.format_exc()[:1000]}\n```", color=0xe74c3c)
        sys.exit(1)
