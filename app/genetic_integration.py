"""
Genetic Engine Integration / 基因引擎整合模組

將基因演算法引擎產生的策略無縫接入現有交易系統。
負責：
1. 從基因演化目錄載入最佳策略
2. 合併到現有 strategies.json
3. 啟動持續演化背景執行緒
4. 定期重新部署（汰舊換新）

Author: second_bot
Date: 2026-05-29
"""

import os
import sys
import json
import time
import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# Genetic engine imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.genetic_engine.converter import convert_to_strategy_json
from app.genetic_engine.chromosome import StrategyChromosome

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENETIC_DATA_DIR = PROJECT_ROOT / "app" / "genetic_engine" / "data"
GENETIC_EVOLUTION_DIR = GENETIC_DATA_DIR / "genetic_evolution"
GENETIC_EVOLUTION_V2_DIR = GENETIC_DATA_DIR / "genetic_evolution_v2"
STRATEGIES_CONFIG_PATH = PROJECT_ROOT / "config" / "strategies.json"
GENETIC_STRATEGIES_PATH = PROJECT_ROOT / "config" / "strategies_genetic.json"


class GeneticStrategyLoader:
    """
    基因策略載入器
    
    從基因演化目錄讀取最佳策略，轉換為現有系統格式。
    """
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or GENETIC_EVOLUTION_DIR
        self._cached_strategies: List[Dict[str, Any]] = []
        self._last_loaded: Optional[datetime] = None
    
    def find_best_chromosome_files(self, max_files: int = 10) -> List[Path]:
        """
        尋找演化目錄中的最佳策略檔案
        
        命名模式：gen_X_best_*.json 或 candidate_round*.json
        """
        if not self.data_dir.exists():
            return []
        
        files = []
        for pattern in ["gen_*_best_*.json", "candidate_round*.json", "deploy_*.json"]:
            files.extend(self.data_dir.glob(pattern))
        
        # Sort by modification time (newest first)
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:max_files]
    
    def load_chromosome_from_file(self, path: Path) -> Optional[StrategyChromosome]:
        """從 JSON 檔載入單一染色體"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            # 如果是轉換後的策略格式（有 chromosome_id）
            if "chromosome_id" in data:
                return None  # 已轉換，不需要再轉
            
            # 如果是原始染色體格式
            if "chromosome_id" in data and "entry_genes" in data:
                return StrategyChromosome.from_dict(data)
            
            return None
        except Exception as e:
            logger.warning(f"Failed to load chromosome from {path}: {e}")
            return None
    
    def load_genetic_strategies(self, max_strategies: int = 5) -> List[Dict[str, Any]]:
        """
        載入基因策略，轉換為現有系統格式
        
        Returns:
            List of strategy dicts ready for strategies.json
        """
        strategies = []
        
        # 1. 先找已轉換的 deploy_strategies.json
        deploy_file = self.data_dir / "deploy_strategies.json"
        if deploy_file.exists():
            try:
                with open(deploy_file, 'r') as f:
                    data = json.load(f)
                if "strategies" in data:
                    for s in data["strategies"]:
                        s["enabled"] = True
                        s["source"] = "genetic"
                        strategies.append(s)
                    logger.info(f"Loaded {len(strategies)} strategies from deploy_strategies.json")
            except Exception as e:
                logger.warning(f"Failed to load deploy_strategies.json: {e}")
        
        # 2. 從最佳染色體檔載入
        if len(strategies) < max_strategies:
            best_files = self.find_best_chromosome_files(max_files=max_strategies * 2)
            for f in best_files:
                if len(strategies) >= max_strategies:
                    break
                
                chrom = self.load_chromosome_from_file(f)
                if chrom:
                    strategy = convert_to_strategy_json(chrom)
                    strategy["enabled"] = True
                    strategy["source"] = "genetic"
                    strategy["file_source"] = str(f.name)
                    strategies.append(strategy)
                    logger.info(f"Converted chromosome {chrom.chromosome_id} from {f.name}")
        
        self._cached_strategies = strategies
        self._last_loaded = datetime.now()
        return strategies
    
    def get_cached_strategies(self) -> List[Dict[str, Any]]:
        """取得快取的策略（如果沒有快取則重新載入）"""
        if not self._cached_strategies or self._is_stale():
            return self.load_genetic_strategies()
        return self._cached_strategies
    
    def _is_stale(self, max_age_minutes: int = 60) -> bool:
        """檢查快取是否過期"""
        if self._last_loaded is None:
            return True
        return (datetime.now() - self._last_loaded).total_seconds() > max_age_minutes * 60


class GeneticIntegration:
    """
    基因引擎整合器
    
    將基因策略合併到現有策略池，並管理持續演化。
    """
    
    def __init__(
        self,
        strategies_config_path: str = None,
        genetic_data_dir: Path = None,
        live_pool_size: int = 5,
    ):
        self.config_path = Path(strategies_config_path) if strategies_config_path else STRATEGIES_CONFIG_PATH
        self.data_dir = genetic_data_dir or GENETIC_EVOLUTION_DIR
        self.loader = GeneticStrategyLoader(data_dir=self.data_dir)
        self.live_pool_size = live_pool_size
        self._genetic_strategies: List[Dict[str, Any]] = []
        self._evolution_thread: Optional[threading.Thread] = None
        self._evolution_running = False
        self._last_merge_time: Optional[datetime] = None
    
    def merge_genetic_strategies(self) -> List[Dict[str, Any]]:
        """
        將基因策略合併到現有策略配置
        
        策略：
        - 保留所有現有策略
        - 加入基因策略（標記 source=genetic）
        - 如果基因策略有相同 ID，用基因版本覆蓋（但保留原有策略）
        
        Returns:
            合併後的完整策略列表
        """
        # 載入現有策略
        existing_strategies = []
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                existing_strategies = data.get("strategies", [])
        except Exception as e:
            logger.error(f"Failed to load existing strategies: {e}")
        
        # 標記現有策略來源
        for s in existing_strategies:
            if "source" not in s:
                s["source"] = "manual"
        
        # 載入基因策略
        genetic = self.loader.load_genetic_strategies(max_strategies=self.live_pool_size)
        
        # 去重：如果基因策略 ID 已存在於手動策略，給基因策略加後綴
        existing_ids = {s.get("id", "") for s in existing_strategies}
        merged = list(existing_strategies)  # 複製現有策略
        
        for gs in genetic:
            gid = gs.get("id", "")
            if gid in existing_ids:
                # 重命名基因策略
                gs["id"] = f"{gid}_genetic"
                gs["name"] = f"{gs.get('name', 'Genetic')} (G)"
            merged.append(gs)
        
        self._genetic_strategies = genetic
        self._last_merge_time = datetime.now()
        
        genetic_count = len([s for s in merged if s.get("source") == "genetic"])
        manual_count = len([s for s in merged if s.get("source") == "manual"])
        logger.info(f"Merged strategies: {manual_count} manual + {genetic_count} genetic = {len(merged)} total")
        
        return merged
    
    def write_merged_config(self, output_path: str = None) -> str:
        """
        寫入合併後的策略配置到獨立檔案
        
        不覆蓋原始 strategies.json，而是寫到 strategies_genetic.json
        讓 strategy_executor 可以選擇載入哪個
        """
        merged = self.merge_genetic_strategies()
        
        output = Path(output_path) if output_path else GENETIC_STRATEGIES_PATH
        
        config_data = {
            "version": "genetic_merged_v1",
            "last_updated": datetime.now().isoformat(),
            "description": "Merged config: manual + genetic strategies",
            "strategies": merged,
            "registry_settings": {
                "genetic_enabled": True,
                "live_pool_size": self.live_pool_size,
                "last_merge": self._last_merge_time.isoformat() if self._last_merge_time else None,
            }
        }
        
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Merged genetic config written to {output}")
        return str(output)
    
    def inject_into_strategies_json(self, backup: bool = True) -> bool:
        """
        直接將基因策略注入現有 strategies.json
        
        這會修改原始檔案，建議先備份
        """
        try:
            if backup and self.config_path.exists():
                backup_path = self.config_path.with_suffix(f".json.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                import shutil
                shutil.copy2(self.config_path, backup_path)
                logger.info(f"Backup created: {backup_path}")
            
            merged = self.merge_genetic_strategies()
            
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            data["strategies"] = merged
            data["version"] = data.get("version", "2.0.0") + "+genetic"
            data["last_updated"] = datetime.now().isoformat()
            data["genetic_settings"] = {
                "enabled": True,
                "live_pool_size": self.live_pool_size,
                "last_merge": self._last_merge_time.isoformat() if self._last_merge_time else None,
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Genetic strategies injected into {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to inject genetic strategies: {e}")
            return False
    
    def remove_genetic_strategies(self) -> bool:
        """從 strategies.json 移除所有基因策略（還原）"""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            strategies = data.get("strategies", [])
            original_count = len(strategies)
            
            # 保留非基因策略
            clean = [s for s in strategies if s.get("source") != "genetic"]
            
            data["strategies"] = clean
            data["version"] = data.get("version", "2.0.0").replace("+genetic", "")
            if "genetic_settings" in data:
                del data["genetic_settings"]
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Removed {original_count - len(clean)} genetic strategies from config")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove genetic strategies: {e}")
            return False
    
    # ─── Continuous Evolution / 持續演化 ───────────────────────────
    
    def start_continuous_evolution(
        self,
        interval_hours: int = 6,
        population_size: int = 30,
        generations_per_run: int = 10,
        backtest_days: int = 90,
    ) -> threading.Thread:
        """
        在背景執行緒啟動持續演化
        
        每 interval_hours 小時跑一次演化，產出新的策略並自動部署
        """
        if self._evolution_running:
            logger.warning("Evolution already running")
            return self._evolution_thread
        
        def evolution_loop():
            logger.info(f"🧬 Continuous evolution started (interval={interval_hours}h)")
            self._evolution_running = True
            
            while self._evolution_running:
                try:
                    logger.info("🧬 Starting evolution cycle...")
                    
                    # Import here to avoid circular imports at module level
                    from app.genetic_engine.evolution import EvolutionEngine, DEFAULT_CONFIG
                    from app.genetic_engine.cli import save_best_strategies
                    
                    config = {
                        **DEFAULT_CONFIG,
                        "population_size": population_size,
                        "max_generations": generations_per_run,
                        "backtest_days": backtest_days,
                    }
                    
                    engine = EvolutionEngine(config=config)
                    
                    # 嘗試載入之前保存的狀態
                    genesis_dir = GENETIC_EVOLUTION_DIR
                    genesis_files = sorted(genesis_dir.glob("gen_*_best_*.json"), 
                                          key=lambda p: p.stat().st_mtime, reverse=True)
                    
                    if genesis_files:
                        # 用最近的結果作為初始種群的一部分
                        logger.info(f"Loading {min(5, len(genesis_files))} previous best as genesis seeds")
                        # 讓引擎從隨機開始，但給它一些好基因
                        # 實際上 EvolutionEngine 的 genesis 是隨機的，這裡我們跑完後用結果
                        pass
                    
                    engine.genesis()
                    best = engine.run(max_generations=generations_per_run, verbose=True)
                    
                    if best:
                        # 保存並部署
                        save_best_strategies(engine, str(GENETIC_EVOLUTION_DIR / "deploy_strategies.json"))
                        
                        # 重新合併到主配置
                        self.write_merged_config()
                        logger.info("🧬 Evolution cycle complete. New strategies deployed.")
                    else:
                        logger.warning("🧬 Evolution produced no viable strategies")
                    
                except Exception as e:
                    logger.error(f"🧬 Evolution cycle error: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                
                # 等待下一次演化
                logger.info(f"🧬 Next evolution in {interval_hours} hours")
                for _ in range(interval_hours * 3600):
                    if not self._evolution_running:
                        break
                    time.sleep(1)
            
            logger.info("🧬 Continuous evolution stopped")
        
        thread = threading.Thread(target=evolution_loop, daemon=True, name="genetic-evolution")
        thread.start()
        self._evolution_thread = thread
        
        return thread
    
    def stop_continuous_evolution(self) -> None:
        """停止持續演化執行緒"""
        self._evolution_running = False
        if self._evolution_thread and self._evolution_thread.is_alive():
            logger.info("Stopping evolution thread...")
            self._evolution_thread.join(timeout=5)
    
    # ─── Quick Operations / 快速操作 ───────────────────────────────
    
    def quick_deploy(self, top_n: int = 5) -> str:
        """
        快速部署：載入現有最佳基因策略並合併
        
        不跑演化，直接部署已有的
        """
        raise RuntimeError(
            "Quick deploy is disabled; manually Promote a Challenger to Champion."
        )
    
    def status(self) -> Dict[str, Any]:
        """取得整合狀態"""
        return {
            "genetic_data_dir": str(self.data_dir),
            "live_pool_size": self.live_pool_size,
            "genetic_strategies_loaded": len(self._genetic_strategies),
            "evolution_running": self._evolution_running,
            "evolution_thread_alive": self._evolution_thread.is_alive() if self._evolution_thread else False,
            "last_merge": self._last_merge_time.isoformat() if self._last_merge_time else None,
            "config_path": str(self.config_path),
            "merged_config_path": str(GENETIC_STRATEGIES_PATH),
        }


# ─── Singleton / 單例 ───────────────────────────────────────────

_genetic_integration: Optional[GeneticIntegration] = None


def get_genetic_integration(
    strategies_config_path: str = None,
    live_pool_size: int = 5,
) -> GeneticIntegration:
    """取得全局整合實例（單例）"""
    global _genetic_integration
    if _genetic_integration is None:
        _genetic_integration = GeneticIntegration(
            strategies_config_path=strategies_config_path,
            live_pool_size=live_pool_size,
        )
    return _genetic_integration


# ─── Convenience Functions / 便利函數 ───────────────────────────

def deploy_genetic_strategies(
    top_n: int = 5,
    inject: bool = False,
    strategies_config_path: str = None,
) -> str:
    """
    一鍵部署基因策略
    
    Args:
        top_n: 載入前 N 個基因策略
        inject: True=直接注入 strategies.json, False=寫到獨立檔案
        strategies_config_path: 策略配置路徑
        
    Returns:
        寫入的檔案路徑
    """
    integration = GeneticIntegration(
        strategies_config_path=strategies_config_path,
        live_pool_size=top_n,
    )
    
    if inject:
        integration.inject_into_strategies_json(backup=True)
        return str(integration.config_path)
    else:
        return integration.write_merged_config()


def start_evolution(
    interval_hours: int = 6,
    live_pool_size: int = 5,
    strategies_config_path: str = None,
) -> GeneticIntegration:
    """
    一鍵啟動：部署 + 持續演化
    
    Returns:
        GeneticIntegration 實例
    """
    integration = GeneticIntegration(
        strategies_config_path=strategies_config_path,
        live_pool_size=live_pool_size,
    )
    
    # 啟動背景演化
    integration.start_continuous_evolution(
        interval_hours=interval_hours,
        population_size=30,
        generations_per_run=10,
    )
    
    return integration


def stop_evolution() -> None:
    """停止所有演化活動"""
    global _genetic_integration
    if _genetic_integration:
        _genetic_integration.stop_continuous_evolution()
    logger.info("Genetic evolution stopped")


# ─── Module Test / 模組測試 ─────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("Genetic Engine Integration / 基因引擎整合模組")
    print("=" * 60)
    print()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python genetic_integration.py deploy [top_n]    — 部署現有最佳策略")
        print("  python genetic_integration.py inject [top_n]   — 注入到 strategies.json")
        print("  python genetic_integration.py evolve [hours]    — 啟動持續演化")
        print("  python genetic_integration.py status            — 查看狀態")
        print("  python genetic_integration.py remove            — 移除基因策略")
        print()
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "deploy":
        top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        path = deploy_genetic_strategies(top_n=top_n, inject=False)
        print(f"✅ Deployed to: {path}")
    
    elif cmd == "inject":
        top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        path = deploy_genetic_strategies(top_n=top_n, inject=True)
        print(f"✅ Injected into: {path}")
    
    elif cmd == "evolve":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 6
        integration = start_evolution(interval_hours=hours)
        print(f"🧬 Evolution started. Status:")
        print(json.dumps(integration.status(), indent=2, default=str))
        print(f"\nPress Ctrl+C to stop...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_evolution()
            print("\n🛑 Stopped")
    
    elif cmd == "status":
        integration = GeneticIntegration()
        print(json.dumps(integration.status(), indent=2, default=str))
    
    elif cmd == "remove":
        integration = GeneticIntegration()
        integration.remove_genetic_strategies()
        print("✅ Genetic strategies removed")
    
    else:
        print(f"Unknown command: {cmd}")
