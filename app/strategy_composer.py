"""
Strategy Composer / 策略合成器

Automatically composes new trading strategies by combining conditions
from the condition library. No trading knowledge required.

Core idea: Strategies are just combinations of conditions.
We provide "strategy archetypes" (templates), and the composer fills them
with actual conditions from the condition library.
"""

import json
import logging
import itertools
import random
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


logger = logging.getLogger(__name__)


class StrategyArchetype(Enum):
    """Strategy archetypes / 策略原型

    Each archetype defines WHAT the strategy tries to capture.
    The composer picks conditions that fit the archetype.
    """
    TREND_FOLLOWING = "trend_following"      # 順勢: 跟著趨勢走
    MEAN_REVERSION = "mean_reversion"        # 均值回歸: 跌太多買，漲太多賣
    MOMENTUM_BREAKOUT = "momentum_breakout" # 動量突破: 價格+成交量同時爆發
    REVERSAL = "reversal"                    # 反轉: 指標背離+超買超賣
    COMPOSITE = "composite"                  # 複合: 多條件投票


# Condition categories / 條件分類
# Each condition belongs to one or more categories
CONDITION_CATEGORIES: Dict[str, List[str]] = {
    "trend_confirm": [
        "close_above_ma240",
        "ema_cross_above",
        "price_above_trend",
        "supertrend",
        "adx_above_20",
        "adx_above_25",
    ],
    "trend_bearish": [
        "close_below_ma240",
        "ema_cross_below",
    ],
    "momentum": [
        "volume_spike",
        "volume_ema_spike",
        "volume_confirmed",
        "price_above_20period_high",
        "keltner_breakout",
        "atr_breakout",
        "consecutive_green",
    ],
    "oversold": [
        "rsi_below_30",
        "rsi_cross_above_30",
        "williams_r",
        "fastk_below_20",
        "price_below_bb_lower",
        "price_below_bb_lower_pct",
    ],
    "overbought_filter": [
        "rsi_not_overbought",
        "rsi_in_range",
    ],
    "volatility_filter": [
        "atr_below_threshold",
        "close_vs_ma240",
    ],
    "divergence": [
        "bullish_divergence_rsi",
    ],
}


# Archetype templates / 策略原型模板
# Each archetype specifies which categories to pick from
ARCHETYPE_TEMPLATES: Dict[StrategyArchetype, Dict[str, Any]] = {
    StrategyArchetype.TREND_FOLLOWING: {
        "description": "Follow the trend with confirmation filters",
        "description_zh": "順勢跟隨 + 確認過濾",
        "required_categories": ["trend_confirm", "momentum"],
        "optional_categories": ["overbought_filter", "volatility_filter"],
        "min_conditions": 2,
        "max_conditions": 4,
        "signal_type": "trend_long",
        "default_timeframes": ["5m", "15m"],
    },
    StrategyArchetype.MEAN_REVERSION: {
        "description": "Buy oversold, sell overbought",
        "description_zh": "超賣買入，超買賣出",
        "required_categories": ["oversold"],
        "optional_categories": ["trend_confirm", "volatility_filter", "divergence"],
        "min_conditions": 2,
        "max_conditions": 4,
        "signal_type": "mean_reversion_long",
        "default_timeframes": ["5m", "15m"],
    },
    StrategyArchetype.MOMENTUM_BREAKOUT: {
        "description": "Volume + price breakout",
        "description_zh": "成交量 + 價格突破",
        "required_categories": ["momentum"],
        "optional_categories": ["trend_confirm", "overbought_filter", "volatility_filter"],
        "min_conditions": 2,
        "max_conditions": 4,
        "signal_type": "momentum",
        "default_timeframes": ["5m"],
    },
    StrategyArchetype.REVERSAL: {
        "description": "RSI divergence + oversold bounce",
        "description_zh": "RSI背離 + 超賣反彈",
        "required_categories": ["oversold", "divergence"],
        "optional_categories": ["trend_confirm", "volatility_filter"],
        "min_conditions": 2,
        "max_conditions": 4,
        "signal_type": "reversal_long",
        "default_timeframes": ["15m", "1h"],
    },
    StrategyArchetype.COMPOSITE: {
        "description": "Multiple signals voting together",
        "description_zh": "多訊號投票",
        "required_categories": ["trend_confirm", "momentum", "oversold"],
        "optional_categories": ["overbought_filter", "volatility_filter", "divergence"],
        "min_conditions": 3,
        "max_conditions": 5,
        "signal_type": "composite_long",
        "default_timeframes": ["5m", "15m"],
    },
}


# Default parameters for each condition / 每個條件的預設參數
CONDITION_DEFAULT_PARAMS: Dict[str, Dict[str, Any]] = {
    "close_vs_ma240": {"ma240_threshold": 2.0},
    "volume_spike": {"volume_threshold": 1.5},
    "volume_ema_spike": {"volume_multiplier": 3.0},
    "volume_confirmed": {"volume_multiplier": 1.2},
    "adx_above_20": {"adx_threshold": 20},
    "adx_above_25": {"adx_threshold": 25},
    "rsi_below_30": {},
    "rsi_cross_above_30": {},
    "rsi_not_overbought": {"rsi_overbought": 70},
    "rsi_in_range": {"rsi_min": 45, "rsi_max": 65},
    "price_below_bb_lower_pct": {"bb_lower_pct": 0.985},
    "atr_below_threshold": {"atr_threshold": 0.02},
    "ema_cross_above": {"ema_fast_period": 8, "ema_slow_period": 21},
    "ema_cross_below": {"ema_fast_period": 8, "ema_slow_period": 21},
    "price_above_trend": {},
    "supertrend": {},
    "williams_r": {"threshold": -80},
    "fastk_below_20": {},
    "keltner_breakout": {},
    "atr_breakout": {},
    "consecutive_green": {"consecutive_count": 4},
    "price_above_20period_high": {},
    "bullish_divergence_rsi": {"lookback_period": 14},
    "close_above_ma240": {},
    "close_below_ma240": {},
}


@dataclass
class ComposedStrategy:
    """A strategy composed by the composer / 合成器產生的策略"""
    id: str
    name: str
    archetype: StrategyArchetype
    conditions: List[str]
    parameters: Dict[str, Any]
    signal_type: str
    timeframes: List[str]
    description: str
    description_zh: str

    def to_strategy_config(self, symbols: List[str]) -> Dict[str, Any]:
        """Convert to strategies.json format / 轉換為 strategies.json 格式"""
        return {
            "id": self.id,
            "name": self.name,
            "name_zh": self.description_zh,
            "type": self.archetype.value,
            "enabled": False,  # Disabled until backtest passes
            "description": self.description,
            "description_zh": self.description_zh,
            "symbols": symbols,
            "timeframes": self.timeframes,
            "conditions": self.conditions,
            "parameters": self.parameters,
            "signal_type": self.signal_type,
            "signal_level": "confirmed",
        }


class StrategyComposer:
    """
    Strategy Composer / 策略合成器

    Automatically composes strategies by combining conditions.
    Uses archetype templates to ensure sensible combinations.

    Usage:
        composer = StrategyComposer()
        strategies = composer.compose_all(max_per_archetype=10)
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
        ]
        self.logger = logging.getLogger(__name__)

    def compose_all(
        self,
        max_per_archetype: int = 20,
        shuffle: bool = True
    ) -> List[ComposedStrategy]:
        """
        Compose strategies for all archetypes.

        Args:
            max_per_archetype: Max strategies per archetype
            shuffle: Randomize order to diversify exploration

        Returns:
            List of composed strategies
        """
        all_strategies: List[ComposedStrategy] = []

        for archetype in StrategyArchetype:
            composed = self.compose_for_archetype(archetype, max_per_archetype)
            all_strategies.extend(composed)
            self.logger.info(f"Composed {len(composed)} strategies for {archetype.value}")

        if shuffle:
            random.shuffle(all_strategies)

        self.logger.info(f"Total composed: {len(all_strategies)} strategies")
        return all_strategies

    def compose_for_archetype(
        self,
        archetype: StrategyArchetype,
        max_count: int = 20
    ) -> List[ComposedStrategy]:
        """
        Compose strategies for a specific archetype.

        Uses combinatorial generation with constraints:
        - Pick all required categories
        - Pick 0-N from optional categories
        - Respect min/max conditions limit
        """
        template = ARCHETYPE_TEMPLATES[archetype]
        required_cats = template["required_categories"]
        optional_cats = template["optional_categories"]
        min_cond = template["min_conditions"]
        max_cond = template["max_conditions"]

        # Get all conditions for each category
        required_conditions: List[List[str]] = []
        for cat in required_cats:
            conditions = CONDITION_CATEGORIES.get(cat, [])
            if not conditions:
                self.logger.warning(f"No conditions for category {cat}")
            required_conditions.append(conditions)

        optional_conditions: List[str] = []
        for cat in optional_cats:
            optional_conditions.extend(CONDITION_CATEGORIES.get(cat, []))

        # Generate combinations
        combinations: List[Set[str]] = []

        # Cartesian product of required categories (pick one from each)
        for required_combo in itertools.product(*required_conditions):
            base = set(required_combo)

            # Add optional conditions (0 to max_cond - len(base))
            max_optional = min(max_cond - len(base), len(optional_conditions))
            min_optional = max(0, min_cond - len(base))

            for num_optional in range(min_optional, max_optional + 1):
                for optional_combo in itertools.combinations(optional_conditions, num_optional):
                    full = base | set(optional_combo)
                    if min_cond <= len(full) <= max_cond:
                        combinations.append(full)

        # Limit combinations
        if len(combinations) > max_count:
            combinations = random.sample(combinations, max_count)

        # Create strategy objects
        strategies: List[ComposedStrategy] = []
        for i, combo in enumerate(combinations):
            strategy = self._build_strategy(archetype, list(combo), i)
            strategies.append(strategy)

        return strategies

    def _build_strategy(
        self,
        archetype: StrategyArchetype,
        conditions: List[str],
        index: int
    ) -> ComposedStrategy:
        """Build a ComposedStrategy from conditions."""
        template = ARCHETYPE_TEMPLATES[archetype]

        # Generate ID and name
        cond_hash = "_".join(sorted(conditions))[:40]
        strategy_id = f"{archetype.value}_{index:03d}_{hash(cond_hash) % 10000:04d}"
        name = f"Auto-{archetype.value.title()} #{index+1}"

        # Merge parameters from all conditions
        params: Dict[str, Any] = {}
        for cond in conditions:
            defaults = CONDITION_DEFAULT_PARAMS.get(cond, {})
            params.update(defaults)

        return ComposedStrategy(
            id=strategy_id,
            name=name,
            archetype=archetype,
            conditions=conditions,
            parameters=params,
            signal_type=template["signal_type"],
            timeframes=template["default_timeframes"],
            description=f"Auto-composed {archetype.value}: {', '.join(conditions)}",
            description_zh=f"自動合成-{archetype.value}: {', '.join(conditions)}",
        )

    def export_to_strategies_json(
        self,
        strategies: List[ComposedStrategy],
        filepath: str,
        merge_with_existing: Optional[str] = None
    ):
        """
        Export composed strategies to strategies.json format.

        Args:
            strategies: Composed strategies
            filepath: Output path
            merge_with_existing: Path to existing strategies.json to merge with
        """
        output = {
            "version": "2.1.0",
            "last_updated": datetime.now().isoformat(),
            "description": "Auto-composed strategies - requires backtest validation",
            "strategies": [s.to_strategy_config(self.symbols) for s in strategies],
            "registry_settings": {
                "auto_load": True,
                "validate_on_load": True,
                "allow_duplicate_ids": False,
                "backtest_all_on_load": False,
                "ranking_metric": "profit_factor",
            }
        }

        # Merge with existing if provided
        if merge_with_existing and Path(merge_with_existing).exists():
            with open(merge_with_existing) as f:
                existing = json.load(f)

            existing_ids = {s["id"] for s in existing.get("strategies", [])}

            for s in output["strategies"]:
                if s["id"] not in existing_ids:
                    existing["strategies"].append(s)

            existing["last_updated"] = datetime.now().isoformat()
            existing["description"] = f"{existing.get('description', '')} + auto-composed"
            output = existing

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Exported {len(strategies)} strategies to {filepath}")

    def get_composition_stats(self) -> Dict[str, Any]:
        """Get statistics about available conditions and combinations."""
        stats = {
            "total_conditions": sum(len(v) for v in CONDITION_CATEGORIES.values()),
            "categories": {k: len(v) for k, v in CONDITION_CATEGORIES.items()},
            "archetypes": {},
        }

        for archetype in StrategyArchetype:
            template = ARCHETYPE_TEMPLATES[archetype]
            required = template["required_categories"]
            optional = template["optional_categories"]

            # Estimate max combinations
            req_counts = [len(CONDITION_CATEGORIES.get(c, [])) for c in required]
            req_combos = 1
            for c in req_counts:
                req_combos *= max(c, 1)

            opt_total = sum(len(CONDITION_CATEGORIES.get(c, [])) for c in optional)
            max_optional = template["max_conditions"] - template["min_conditions"]

            opt_combos = sum(
                itertools.combinations(range(opt_total), k).__length__() if hasattr(
                    itertools.combinations(range(opt_total), k), '__length__'
                ) else 0
                for k in range(max_optional + 1)
            ) if opt_total > 0 else 1

            stats["archetypes"][archetype.value] = {
                "required_categories": required,
                "optional_categories": optional,
                "estimated_combinations": req_combos * max(opt_combos, 1),
            }

        return stats


# =============================================================================
# Auto-Discovery Engine / 自動發現引擎
# =============================================================================

@dataclass
class DiscoveryResult:
    """Result of strategy discovery / 策略發現結果"""
    strategy_id: str
    backtest_id: str
    passed: bool
    score: float
    metrics: Dict[str, Any]
    reason: str = ""


class StrategyDiscoveryEngine:
    """
    Strategy Discovery Engine / 策略自動發現引擎

    Full pipeline:
    1. Compose strategies (StrategyComposer)
    2. Generate parameter variations (StrategyGenerator)
    3. Run backtests (BacktestPipeline)
    4. Score and filter
    5. Enable passing strategies

    Usage:
        engine = StrategyDiscoveryEngine()
        results = engine.discover(
            symbols=["BTCUSDT"],
            timeframes=["5m"],
            backtest_days=30,
            min_trades=20,
            min_profit_factor=1.3,
            min_sharpe=0.5,
            max_drawdown=0.15,
        )
    """

    def __init__(
        self,
        strategies_dir: str = "config",
        results_dir: str = "backtest_results",
    ):
        self.composer = StrategyComposer()
        self.strategies_dir = Path(strategies_dir)
        self.results_dir = Path(results_dir)
        self.logger = logging.getLogger(__name__)

        # Scoring thresholds / 評分門檻
        self.min_trades = 20
        self.min_profit_factor = 1.3
        self.min_sharpe = 0.5
        self.max_drawdown = 0.15
        self.min_win_rate = 0.45

    def discover(
        self,
        symbols: List[str],
        timeframes: List[str],
        backtest_days: int = 90,
        max_strategies: int = 50,
        max_variations_per_strategy: int = 5,
    ) -> List[DiscoveryResult]:
        """
        Run full discovery pipeline.

        Args:
            symbols: Symbols to test
            timeframes: Timeframes to test
            backtest_days: Historical days for backtest (default: 90)
            max_strategies: Max strategies to compose
            max_variations_per_strategy: Max parameter variations per strategy

        Returns:
            List of discovery results
        """
        # Auto-scale min_trades based on backtest period and symbols
        self.min_trades = max(5, len(symbols) * backtest_days // 30)

        self.logger.info("=" * 60)
        self.logger.info("STRATEGY DISCOVERY STARTED")
        self.logger.info(f"Symbols: {symbols}, Timeframes: {timeframes}, Days: {backtest_days}")
        self.logger.info(f"Auto-scaled min_trades: {self.min_trades}")
        self.logger.info("=" * 60)

        # Phase 1: Compose strategies
        self.logger.info("Phase 1: Composing strategies...")
        composed = self.composer.compose_all(max_per_archetype=max_strategies // 5)
        composed = composed[:max_strategies]
        self.logger.info(f"Composed {len(composed)} strategies")

        # Phase 2: Generate parameter variations (if StrategyGenerator available)
        variations = self._generate_variations(composed, max_variations_per_strategy)
        self.logger.info(f"Generated {len(variations)} total variations")

        # Phase 3: Run backtests
        self.logger.info("Phase 3: Running backtests...")
        results = self._run_backtests(variations, symbols, timeframes, backtest_days)
        self.logger.info(f"Backtests completed: {len(results)}")

        # Phase 4: Score and filter
        self.logger.info("Phase 4: Scoring and filtering...")
        passed = self._score_and_filter(results)
        self.logger.info(f"Strategies passed: {len(passed)}/{len(results)}")

        # Phase 5: Enable passing strategies
        if passed:
            self.logger.info("Phase 5: Enabling passing strategies...")
            self._enable_strategies(passed)

        return passed

    def _generate_variations(
        self,
        strategies: List[ComposedStrategy],
        max_per_strategy: int
    ) -> List[ComposedStrategy]:
        """Generate parameter variations for each strategy."""
        all_variations: List[ComposedStrategy] = []

        for strategy in strategies:
            all_variations.append(strategy)

            # Add parameter variations (simplified)
            for i in range(1, max_per_strategy):
                varied = self._vary_parameters(strategy, i)
                if varied:
                    all_variations.append(varied)

        return all_variations

    def _vary_parameters(self, strategy: ComposedStrategy, seed: int) -> Optional[ComposedStrategy]:
        """Create a parameter variation of a strategy."""
        random.seed(hash(strategy.id) + seed)

        new_params = dict(strategy.parameters)
        varied = False

        # Vary common parameters
        if "volume_threshold" in new_params:
            new_params["volume_threshold"] = round(
                new_params["volume_threshold"] * random.uniform(0.7, 1.5), 2
            )
            varied = True

        if "volume_multiplier" in new_params:
            new_params["volume_multiplier"] = round(
                new_params["volume_multiplier"] * random.uniform(0.7, 1.5), 2
            )
            varied = True

        if "adx_threshold" in new_params:
            new_params["adx_threshold"] = int(
                new_params["adx_threshold"] * random.uniform(0.8, 1.2)
            )
            varied = True

        if "bb_lower_pct" in new_params:
            new_params["bb_lower_pct"] = round(
                new_params["bb_lower_pct"] * random.uniform(0.98, 1.02), 4
            )
            varied = True

        if not varied:
            return None

        new_id = f"{strategy.id}_v{seed}"
        return ComposedStrategy(
            id=new_id,
            name=f"{strategy.name} (v{seed})",
            archetype=strategy.archetype,
            conditions=strategy.conditions,
            parameters=new_params,
            signal_type=strategy.signal_type,
            timeframes=strategy.timeframes,
            description=f"{strategy.description} [param_variation={seed}]",
            description_zh=f"{strategy.description_zh} [參數變體={seed}]",
        )

    def _run_backtests(
        self,
        strategies: List[ComposedStrategy],
        symbols: List[str],
        timeframes: List[str],
        days: int,
    ) -> List[DiscoveryResult]:
        """Run unified backtests for all strategies using StrategyConditions."""
        results: List[DiscoveryResult] = []

        for strategy in strategies:
            for symbol in symbols:
                for tf in timeframes:
                    try:
                        result = self._run_unified_backtest(strategy, symbol, tf, days)
                        results.append(result)
                    except Exception as e:
                        self.logger.error(f"Backtest failed for {strategy.id} {symbol} {tf}: {e}")
                        results.append(DiscoveryResult(
                            strategy_id=strategy.id,
                            backtest_id=f"BT_{strategy.id}_{symbol}_{tf}",
                            passed=False,
                            score=0.0,
                            metrics={},
                            reason=f"ERROR: {str(e)[:100]}",
                        ))

        return results

    def _run_unified_backtest(
        self,
        strategy: ComposedStrategy,
        symbol: str,
        timeframe: str,
        days: int,
    ) -> DiscoveryResult:
        """Run a single unified backtest via UnifiedBacktestRunner."""
        from backtest.unified_runner import run_unified_backtest
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Build strategy config dict
        strategy_config = strategy.to_strategy_config(symbols=[symbol])
        strategy_config["timeframes"] = [timeframe]

        # Run backtest with tighter SL/TP for more trade samples
        summary = run_unified_backtest(
            strategy_config=strategy_config,
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
            initial_capital=10000.0,
            stop_loss_pct=3.0,      # Tighter SL for more trades
            take_profit_pct=6.0,    # Tighter TP for more trades
            commission_pct=0.04,  # Approx Binance taker fee
        )

        # Extract metrics from BacktestSummary
        total_trades = summary.total_trades
        winning_trades = summary.winning_trades
        losing_trades = summary.losing_trades

        # Calculate profit factor
        if losing_trades > 0:
            avg_win = summary.total_return_pct / winning_trades if winning_trades > 0 else 0
            avg_loss = -summary.total_return_pct / losing_trades if losing_trades > 0 else 1
            profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
        else:
            profit_factor = float("inf") if winning_trades > 0 else 1.0

        win_rate = summary.win_rate
        max_dd = summary.max_drawdown_pct
        total_return = summary.total_return_pct

        # Approximate Sharpe (simplified)
        sharpe = 0.0
        if summary.equity_curve and len(summary.equity_curve) > 1:
            equities = [p["equity"] for p in summary.equity_curve]
            returns = []
            for i in range(1, len(equities)):
                if equities[i - 1] > 0:
                    returns.append((equities[i] - equities[i - 1]) / equities[i - 1])
            if returns:
                mean_ret = sum(returns) / len(returns)
                std_ret = (sum((r - mean_ret) ** 2 for r in returns) / len(returns)) ** 0.5
                if std_ret > 0:
                    sharpe = (mean_ret / std_ret) * (252 ** 0.5)  # Annualized

        metrics = {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": total_trades,
        }

        # Determine if passes
        passed = (
            total_trades >= self.min_trades
            and profit_factor >= self.min_profit_factor
            and sharpe >= self.min_sharpe
            and max_dd <= self.max_drawdown * 100
            and win_rate >= self.min_win_rate
        )

        score = (
            profit_factor * 0.3
            + sharpe * 0.3
            + (win_rate / 100) * 0.2
            - (max_dd / 100) * 0.2
        )

        reason = "PASS" if passed else "FAIL"
        if not passed:
            fails = []
            if total_trades < self.min_trades:
                fails.append(f"trades({total_trades})<{self.min_trades}")
            if profit_factor < self.min_profit_factor:
                fails.append(f"pf({profit_factor:.2f})<{self.min_profit_factor}")
            if sharpe < self.min_sharpe:
                fails.append(f"sharpe({sharpe:.2f})<{self.min_sharpe}")
            if max_dd > self.max_drawdown * 100:
                fails.append(f"dd({max_dd:.1f})>{self.max_drawdown*100}")
            if win_rate < self.min_win_rate:
                fails.append(f"wr({win_rate:.1f})<{self.min_win_rate}")
            reason = f"FAIL: {'; '.join(fails)}"

        return DiscoveryResult(
            strategy_id=strategy.id,
            backtest_id=f"BT_{strategy.id}_{symbol}_{timeframe}",
            passed=passed,
            score=score,
            metrics=metrics,
            reason=reason,
        )

    def _score_and_filter(self, results: List[DiscoveryResult]) -> List[DiscoveryResult]:
        """Score and filter results."""
        passed = [r for r in results if r.passed]
        passed.sort(key=lambda r: r.score, reverse=True)
        return passed

    def _enable_strategies(self, results: List[DiscoveryResult]):
        """Enable passing strategies in strategies.json."""
        # This would modify strategies.json to set enabled=True for passing strategies
        self.logger.info(f"Would enable {len(results)} strategies")
        for r in results[:10]:  # Top 10
            self.logger.info(f"  {r.strategy_id}: score={r.score:.2f}, {r.reason}")


# =============================================================================
# CLI / 命令列介面
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo: Show composition stats
    composer = StrategyComposer()
    stats = composer.get_composition_stats()

    print("\n" + "=" * 60)
    print("STRATEGY COMPOSER DEMO")
    print("=" * 60)
    print(f"\nTotal available conditions: {stats['total_conditions']}")
    print("\nConditions by category:")
    for cat, count in stats["categories"].items():
        print(f"  {cat}: {count}")

    print("\nArchetype templates:")
    for arch, info in stats["archetypes"].items():
        print(f"\n  {arch}:")
        print(f"    Required: {info['required_categories']}")
        print(f"    Optional: {info['optional_categories']}")
        print(f"    Est. combinations: {info['estimated_combinations']}")

    # Demo: Compose strategies
    print("\n" + "-" * 60)
    print("Composing strategies...")
    strategies = composer.compose_all(max_per_archetype=5)

    print(f"\nComposed {len(strategies)} strategies:")
    for s in strategies[:5]:
        print(f"\n  {s.id}")
        print(f"    Type: {s.archetype.value}")
        print(f"    Conditions: {s.conditions}")
        print(f"    Params: {s.parameters}")
        print(f"    Timeframes: {s.timeframes}")

    # Demo: Export
    print("\n" + "-" * 60)
    composer.export_to_strategies_json(
        strategies,
        "/tmp/composed_strategies.json"
    )
    print("Exported to /tmp/composed_strategies.json")

    # Demo: Discovery engine
    print("\n" + "-" * 60)
    print("Running discovery engine (mock)...")
    engine = StrategyDiscoveryEngine()
    results = engine.discover(
        symbols=["BTCUSDT"],
        timeframes=["5m"],
        backtest_days=30,
        max_strategies=10,
        max_variations_per_strategy=2,
    )

    print(f"\nPassed strategies: {len(results)}")
    for r in results[:5]:
        print(f"  {r.strategy_id}: score={r.score:.2f} ({r.reason})")
