#!/usr/bin/env python3
"""
Strategy Factory - 策略工廠
持續生成策略變體、評估、淘汰、進化。

核心哲學：像細菌培養一樣，大量生成變體，讓市場篩選贏家。
"""

import json
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

WORKSPACE = Path("/root/.openclaw/workspace/kimi-shared-brain")
CONFIG_FILE = WORKSPACE / "config/strategies.json"
STATE_FILE = WORKSPACE / "state/paper_trading_state.json"
FACTORY_LOG = WORKSPACE / "logs/strategy_factory.log"

# ─── 參數變異空間 ────────────────────────────────────────────────────────

PARAM_MUTATION_SPACE = {
    # 趨勢過濾
    "adx_threshold": [18, 20, 22, 25, 28, 32],
    "adx_strong_trend": [25, 28, 32, 35, 40],
    
    # 成交量
    "volume_threshold": [1.2, 1.5, 2.0, 2.5, 3.0, 4.0],
    "volume_multiplier": [2.0, 2.5, 3.0, 3.5, 4.0, 5.0],
    "volume_ema_multiplier": [2.0, 2.5, 3.0, 3.5],
    
    # RSI
    "rsi_overbought": [65, 70, 75, 80, 85],
    "rsi_oversold": [15, 20, 25, 30, 35],
    
    # 止盈階梯 (轉為 dict 格式)
    "profit_target_base": [0.04, 0.05, 0.06, 0.08, 0.10, 0.12],
    "profit_target_decay": [0.005, 0.01, 0.015, 0.02],
    
    # 止損
    "hard_stop": [-0.04, -0.05, -0.06, -0.08, -0.10],
    "atr_multiplier": [1.5, 2.0, 2.5, 3.0],
    "trailing_trigger": [0.03, 0.04, 0.05, 0.06, 0.08],
    "trailing_drawback": [0.01, 0.015, 0.02, 0.025, 0.03],
    
    # MA 反轉
    "ma_reverse_threshold": [-0.005, -0.008, -0.010, -0.015, -0.020, -0.030],
    
    # 時間
    "time_stop_hours": [6.0, 8.0, 10.0, 12.0, 16.0, 20.0],
    
    # 倉位
    "position_pct": [0.08, 0.10, 0.12, 0.15, 0.20],
    "max_concurrent": [2, 3, 4, 5],
}

# 策略模板（作為變異的母本）
STRATEGY_TEMPLATES = {
    "trend_follower": {
        "type": "trend",
        "conditions": ["close_vs_ma240", "ma5_cross_ma20", "volume_spike", "adx_above_threshold"],
        "base_params": ["adx_threshold", "volume_threshold", "hard_stop", "atr_multiplier", 
                       "trailing_trigger", "trailing_drawback", "time_stop_hours", "position_pct"],
    },
    "volume_breakout": {
        "type": "momentum", 
        "conditions": ["volume_ema_spike", "rsi_not_overbought", "adx_above_threshold"],
        "base_params": ["volume_multiplier", "rsi_overbought", "adx_threshold", 
                       "hard_stop", "time_stop_hours", "position_pct"],
    },
    "mean_reversion": {
        "type": "contrarian",
        "conditions": ["rsi_extreme", "price_vs_bollinger", "volume_confirm"],
        "base_params": ["rsi_oversold", "rsi_overbought", "hard_stop", 
                       "profit_target_base", "time_stop_hours", "position_pct"],
    },
}


# ─── 核心類別 ────────────────────────────────────────────────────────────

@dataclass
class StrategyVariant:
    """策略變體"""
    id: str
    name: str
    template: str
    params: Dict[str, Any]
    generation: int = 1
    parent_id: Optional[str] = None
    created_at: str = ""
    
    def to_strategy_config(self, symbols: List[str]) -> Dict:
        """轉為 strategies.json 格式"""
        # Build profit targets dict
        base = self.params.get("profit_target_base", 0.06)
        decay = self.params.get("profit_target_decay", 0.01)
        profit_targets = {
            "0": base,
            "20": max(base - decay, 0.02),
            "40": max(base - decay * 2, 0.015),
            "60": max(base - decay * 3, 0.01),
            "120": max(base - decay * 4, 0.005),
        }
        
        conditions = list(STRATEGY_TEMPLATES[self.template]["conditions"])
        # Replace threshold placeholders
        for i, c in enumerate(conditions):
            if "adx_above" in c:
                conditions[i] = f"adx_above_{self.params.get('adx_threshold', 20)}"
        
        return {
            "id": self.id,
            "name": f"{self.name} G{self.generation}",
            "name_zh": f"{self.name} 第{self.generation}代",
            "type": STRATEGY_TEMPLATES[self.template]["type"],
            "enabled": True,  # 激進模式：直接啟用
            "description": f"Auto-generated variant of {self.template} | Gen:{self.generation} | Parent:{self.parent_id or 'root'}",
            "symbols": symbols,
            "timeframes": ["5m"],
            "conditions": conditions,
            "parameters": {
                k: v for k, v in self.params.items() 
                if k not in ["profit_target_base", "profit_target_decay"]
            },
            "default_exit_params": {
                "hard_stop_loss": self.params.get("hard_stop", -0.06),
                "atr_stop_multiplier": self.params.get("atr_multiplier", 2.0),
                "ma_reverse_pnl_threshold": self.params.get("ma_reverse_threshold", -0.015),
                "profit_targets": profit_targets,
                "trailing_stop_trigger": self.params.get("trailing_trigger", 0.04),
                "trailing_stop_drawback": self.params.get("trailing_drawback", 0.015),
                "time_stop_hours": self.params.get("time_stop_hours", 10.0),
                "position_pct": self.params.get("position_pct", 0.12),
            },
            "signal_type": "trend_long",
            "signal_level": "confirmed",
            "meta": {
                "factory_generated": True,
                "generation": self.generation,
                "parent_id": self.parent_id,
                "created_at": self.created_at or datetime.now().isoformat(),
            }
        }


class StrategyFactory:
    """策略工廠：生成、評估、淘汰、進化"""
    
    def __init__(self):
        self.logger = logger
        self.config = self._load_config()
        self.state = self._load_state()
        self.variants: List[StrategyVariant] = []
        
    def _load_config(self) -> Dict:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    
    def _load_state(self) -> Dict:
        with open(STATE_FILE) as f:
            return json.load(f)
    
    def _save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
    
    def _save_state(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    def _generate_variant_id(self, template: str, generation: int) -> str:
        """生成唯一 ID"""
        timestamp = datetime.now().strftime("%m%d%H%M")
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=3))
        return f"{template}_g{generation}_{timestamp}_{random_suffix}"
    
    def mutate_params(self, parent_params: Optional[Dict] = None, 
                     template: str = "trend_follower") -> Dict[str, Any]:
        """
        生成變異參數。
        如果有 parent，基於 parent 做小幅變異。
        如果沒有，從空間隨機採樣。
        """
        params = {}
        base_params = STRATEGY_TEMPLATES[template]["base_params"]
        
        for param_name in base_params:
            if param_name not in PARAM_MUTATION_SPACE:
                continue
                
            candidates = PARAM_MUTATION_SPACE[param_name]
            
            if parent_params and param_name in parent_params:
                # 基於父代做變異：70% 概率小幅變動，30% 完全隨機
                parent_val = parent_params[param_name]
                if random.random() < 0.7:
                    # 找附近的值
                    try:
                        idx = candidates.index(parent_val)
                        shift = random.choice([-2, -1, 1, 2])
                        new_idx = max(0, min(len(candidates)-1, idx + shift))
                        params[param_name] = candidates[new_idx]
                    except ValueError:
                        params[param_name] = random.choice(candidates)
                else:
                    params[param_name] = random.choice(candidates)
            else:
                params[param_name] = random.choice(candidates)
        
        return params
    
    def spawn_variant(self, template: str = "trend_follower", 
                     parent: Optional[StrategyVariant] = None,
                     symbols: Optional[List[str]] = None) -> StrategyVariant:
        """生成一個新變體"""
        generation = 1 if not parent else parent.generation + 1
        parent_id = parent.id if parent else None
        parent_params = parent.params if parent else None
        
        params = self.mutate_params(parent_params, template)
        
        variant_id = self._generate_variant_id(template, generation)
        name = template.replace("_", " ").title()
        
        variant = StrategyVariant(
            id=variant_id,
            name=name,
            template=template,
            params=params,
            generation=generation,
            parent_id=parent_id,
            created_at=datetime.now().isoformat(),
        )
        
        return variant
    
    def deploy_variant(self, variant: StrategyVariant, symbols: List[str]):
        """部署變體到 config 和 state"""
        # 1. 加入 config
        strategy_config = variant.to_strategy_config(symbols)
        
        # 檢查 ID 是否已存在
        existing_ids = [s["id"] for s in self.config["strategies"]]
        if variant.id in existing_ids:
            self.logger.warning(f"Variant {variant.id} already exists, skipping")
            return False
        
        self.config["strategies"].append(strategy_config)
        
        # 2. 加入 state（開戶）
        if variant.id not in self.state.get("strategies", {}):
            self.state["strategies"][variant.id] = {
                "balance": 1000.0,
                "initial": 1000.0,
                "positions": {},
                "trades": [],
                "meta": {
                    "factory_generated": True,
                    "generation": variant.generation,
                    "parent_id": variant.parent_id,
                    "created_at": variant.created_at,
                }
            }
        
        self._save_config()
        self._save_state()
        
        self.logger.info(f"✅ Deployed {variant.id} (Gen {variant.generation}, parent={variant.parent_id})")
        self.logger.info(f"   Params: {variant.params}")
        return True
    
    def evaluate_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """評估策略表現，返回評分"""
        if strategy_id not in self.state.get("strategies", {}):
            return {"score": -999, "trades": 0, "win_rate": 0, "balance": 1000, "status": "not_found"}
        
        info = self.state["strategies"][strategy_id]
        trades = info.get("trades", [])
        n = len(trades)
        
        if n == 0:
            return {"score": 0, "trades": 0, "win_rate": 0, "status": "no_trades", "balance": info.get("balance", 1000)}
        
        wins = [t for t in trades if t.get("realized_pnl", 0) > 0]
        losses = [t for t in trades if t.get("realized_pnl", 0) <= 0]
        
        total_pnl = sum(t.get("realized_pnl", 0) for t in trades)
        win_rate = len(wins) / n * 100 if n > 0 else 0
        avg_win = sum(t["realized_pnl"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["realized_pnl"] for t in losses) / len(losses) if losses else 0
        balance = info.get("balance", 1000)
        pnl_pct = (balance - 1000) / 1000 * 100
        
        # 評分公式（越高越好）
        # 核心：盈利為王，但懲罰高頻低盈虧比
        score = 0
        score += pnl_pct * 10  # 總盈虧佔比最大
        score += win_rate * 0.5  # 勝率加成
        score += min(n, 50) * 0.1  # 交易筆數小加成（但上限）
        
        # 懲罰項
        if avg_loss != 0 and avg_win / abs(avg_loss) < 0.8:
            score -= 20  # 盈虧比太差
        if n > 20 and win_rate < 30:
            score -= 30  # 大量交易但勝率極低
        if balance < 900:
            score -= 50  # 虧損超過 10%
        
        return {
            "score": round(score, 2),
            "trades": n,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 4),
            "balance": round(balance, 2),
            "pnl_pct": round(pnl_pct, 2),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "status": "active" if n < 20 else ("winning" if balance > 1000 else "losing"),
        }
    
    def cull_losers(self, min_trades: int = 15, min_balance: float = 950.0):
        """
        淘汰輸家。
        規則：交易筆數 >= min_trades 且 balance < min_balance 的策略自動 disable。
        """
        culled = []
        for s in self.config["strategies"]:
            sid = s["id"]
            if not s.get("enabled"):
                continue
            
            eval_result = self.evaluate_strategy(sid)
            
            # 淘汰條件
            should_cull = False
            reason = ""
            
            if eval_result["trades"] >= min_trades:
                if eval_result["balance"] < min_balance:
                    should_cull = True
                    reason = f"balance ${eval_result['balance']:.2f} < ${min_balance}"
                elif eval_result["win_rate"] < 25 and eval_result["trades"] >= 30:
                    should_cull = True
                    reason = f"win rate {eval_result['win_rate']:.1f}% < 25%"
                elif eval_result["pnl_pct"] < -8:
                    should_cull = True
                    reason = f"total loss {eval_result['pnl_pct']:.1f}%"
            
            if should_cull:
                s["enabled"] = False
                s["meta"] = s.get("meta", {})
                s["meta"]["culled_at"] = datetime.now().isoformat()
                s["meta"]["cull_reason"] = reason
                culled.append((sid, reason, eval_result))
                self.logger.info(f"🗑️ CULLED {sid}: {reason}")
        
        if culled:
            self._save_config()
        
        return culled
    
    def evolve_generation(self, n_variants: int = 3, symbols: Optional[List[str]] = None):
        """
        進化一代：
        1. 評估現有活躍策略
        2. 選出贏家作為母本
        3. 生成變體
        4. 部署
        """
        if symbols is None:
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
                      "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"🧬 EVOLUTION CYCLE | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.logger.info(f"{'='*60}")
        
        # 1. 評估所有活躍策略
        active_strategies = [s for s in self.config["strategies"] if s.get("enabled")]
        scores = []
        
        for s in active_strategies:
            sid = s["id"]
            eval_result = self.evaluate_strategy(sid)
            scores.append((sid, eval_result["score"], eval_result, s))
            self.logger.info(f"📊 {sid}: score={eval_result['score']:.1f} | "
                           f"trades={eval_result['trades']} | "
                           f"balance=${eval_result['balance']:.2f} | "
                           f"win={eval_result['win_rate']:.0f}%")
        
        # 2. 選出前 3 名作為母本
        scores.sort(key=lambda x: x[1], reverse=True)
        parents = scores[:3]
        
        self.logger.info(f"\n🏆 Top parents: {[p[0] for p in parents]}")
        
        # 3. 先淘汰輸家
        culled = self.cull_losers()
        self.logger.info(f"🗑️ Culled {len(culled)} losers")
        
        # 4. 生成變體
        deployed = 0
        templates = list(STRATEGY_TEMPLATES.keys())
        
        for i in range(n_variants):
            # 50% 概率基於贏家變異，50% 完全新策略
            if parents and random.random() < 0.5:
                parent_sid, _, _, parent_cfg = random.choice(parents)
                parent_params = parent_cfg.get("parameters", {})
                # 補充 exit params
                exit_params = parent_cfg.get("default_exit_params", {})
                parent_params.update({
                    "hard_stop": exit_params.get("hard_stop_loss", -0.06),
                    "atr_multiplier": exit_params.get("atr_stop_multiplier", 2.0),
                    "ma_reverse_threshold": exit_params.get("ma_reverse_pnl_threshold", -0.015),
                    "trailing_trigger": exit_params.get("trailing_stop_trigger", 0.04),
                    "trailing_drawback": exit_params.get("trailing_stop_drawback", 0.015),
                    "time_stop_hours": exit_params.get("time_stop_hours", 10.0),
                    "position_pct": exit_params.get("position_pct", 0.12),
                })
                template = parent_cfg.get("type", "trend_follower")
                if template not in STRATEGY_TEMPLATES:
                    template = "trend_follower"
                
                parent_variant = StrategyVariant(
                    id=parent_sid, name="", template=template, params=parent_params
                )
                variant = self.spawn_variant(template, parent_variant)
            else:
                template = random.choice(templates)
                variant = self.spawn_variant(template)
            
            success = self.deploy_variant(variant, symbols)
            if success:
                deployed += 1
        
        self.logger.info(f"\n✅ Deployed {deployed} new variants")
        self.logger.info(f"📈 Active strategies: {len([s for s in self.config['strategies'] if s.get('enabled')])}")
        
        return {
            "parents": [p[0] for p in parents],
            "culled": [c[0] for c in culled],
            "deployed": deployed,
        }
    
    def get_factory_strategies(self) -> List[Dict]:
        """獲取所有工廠生成的策略"""
        return [s for s in self.config["strategies"] 
                if s.get("meta", {}).get("factory_generated")]


def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description="Strategy Factory - 策略工廠")
    parser.add_argument("--evolve", action="store_true", help="進化一代新策略")
    parser.add_argument("--cull", action="store_true", help="淘汰輸家")
    parser.add_argument("--evaluate", type=str, help="評估指定策略")
    parser.add_argument("--list", action="store_true", help="列出所有工廠策略")
    parser.add_argument("--n-variants", type=int, default=3, help="每次進化生成數量")
    parser.add_argument("--aggressive", action="store_true", help="激進模式：更多變體")
    
    args = parser.parse_args()
    
    factory = StrategyFactory()
    
    if args.aggressive:
        args.n_variants = 6
    
    if args.evaluate:
        result = factory.evaluate_strategy(args.evaluate)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.cull:
        culled = factory.cull_losers()
        print(f"\n🗑️ Culled {len(culled)} strategies:")
        for sid, reason, eval_result in culled:
            print(f"  {sid}: {reason}")
    
    elif args.list:
        strategies = factory.get_factory_strategies()
        print(f"\n🏭 Factory Strategies ({len(strategies)} total):")
        for s in strategies:
            enabled = "✅" if s.get("enabled") else "❌"
            gen = s.get("meta", {}).get("generation", "?")
            print(f"  {enabled} {s['id']} | Gen {gen} | {s.get('name', '')}")
    
    elif args.evolve or args.aggressive:
        result = factory.evolve_generation(n_variants=args.n_variants)
        print(f"\n🧬 Evolution complete:")
        print(f"  Parents: {result['parents']}")
        print(f"  Culled: {result['culled']}")
        print(f"  Deployed: {result['deployed']} new variants")
    
    else:
        # 默認：評估所有
        print("\n📊 Strategy Evaluation:")
        for s in factory.config["strategies"]:
            if s.get("enabled"):
                result = factory.evaluate_strategy(s["id"])
                status = "💀" if result["balance"] < 950 else "🟡" if result["balance"] < 1000 else "🟢"
                print(f"{status} {s['id']}: ${result['balance']:.2f} | "
                      f"{result['trades']}T | {result['win_rate']:.0f}%W | "
                      f"Score:{result['score']:.1f}")


if __name__ == "__main__":
    main()
