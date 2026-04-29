#!/usr/bin/env python3
"""
Live Strategy Ranking
Generates real-time strategy performance ranking across all symbols.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from app.strategy_executor import StrategyExecutor
from data.fetcher import create_fetcher
from indicators.calculator import calculate_sma, calculate_volume_sma


def evaluate_strategy_live(strategy: dict, symbol: str) -> dict:
    """Evaluate a single strategy on a single symbol."""
    fetcher = create_fetcher()
    
    try:
        # Get data
        klines = fetcher.get_klines(symbol, "5m", 250)
        prices = [k.close for k in klines]
        volumes = [k.volume for k in klines]
        
        if len(prices) < 240:
            return None
        
        # Calculate indicators
        ma5 = calculate_sma(prices, 5)
        ma20 = calculate_sma(prices, 20)
        ma240 = calculate_sma(prices, 240)
        vol_ratio = calculate_volume_sma(volumes) if len(volumes) >= 20 else 0
        
        current_price = prices[-1]
        
        # Count how many conditions pass
        conditions = strategy.get("conditions", [])
        passed = 0
        checks = []
        
        for cond in conditions:
            if cond == "close_vs_ma240":
                threshold = ma240[-1] * 0.02
                ok = abs(current_price - ma240[-1]) <= threshold
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
            elif cond == "ma5_cross_ma20":
                ok = ma5[-1] > ma20[-1] and ma5[-2] <= ma20[-2] if len(ma5) > 1 else ma5[-1] > ma20[-1]
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
            elif cond == "ma5_cross_below_ma20":
                ok = ma5[-1] < ma20[-1]
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
            elif cond == "volume_spike":
                threshold = strategy.get("parameters", {}).get("volume_threshold", 1.5)
                ok = vol_ratio >= threshold
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
            elif cond == "consecutive_green":
                ok = all(prices[-i] > prices[-i-1] for i in range(1, 5)) if len(prices) >= 5 else False
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
            elif cond == "consecutive_red":
                ok = all(prices[-i] < prices[-i-1] for i in range(1, 5)) if len(prices) >= 5 else False
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
            elif cond in ["close_above_ma240", "close_below_ma240"]:
                if cond == "close_above_ma240":
                    ok = current_price > ma240[-1]
                else:
                    ok = current_price < ma240[-1]
                if ok: passed += 1
                checks.append({"condition": cond, "passed": ok})
        
        # Score = percentage of conditions passed
        total = len(conditions)
        score = (passed / total * 100) if total > 0 else 0
        
        return {
            "strategy_id": strategy["id"],
            "strategy_name": strategy["name"],
            "symbol": symbol,
            "score": round(score, 1),
            "conditions_passed": passed,
            "conditions_total": total,
            "current_price": round(current_price, 2),
            "ma240": round(ma240[-1], 2) if ma240 else None,
            "vol_ratio": round(vol_ratio, 2),
            "checks": checks
        }
    except Exception as e:
        return {
            "strategy_id": strategy["id"],
            "symbol": symbol,
            "error": str(e),
            "score": 0
        }


def generate_live_ranking() -> dict:
    """Generate live ranking across all strategies and symbols."""
    
    executor = StrategyExecutor()
    strategies = executor.enabled_strategies
    
    all_results = []
    symbol_scores = {}
    
    for strategy in strategies:
        symbols = strategy.get("symbols", [])
        for symbol in symbols:
            result = evaluate_strategy_live(strategy, symbol)
            if result:
                all_results.append(result)
                
                # Track symbol-level scores
                if symbol not in symbol_scores:
                    symbol_scores[symbol] = []
                symbol_scores[symbol].append({
                    "strategy": strategy["id"],
                    "score": result["score"]
                })
    
    # Calculate strategy average scores
    strategy_totals = {}
    for r in all_results:
        sid = r["strategy_id"]
        if sid not in strategy_totals:
            strategy_totals[sid] = {"scores": [], "name": r.get("strategy_name", sid)}
        strategy_totals[sid]["scores"].append(r["score"])
    
    strategy_ranking = []
    for sid, data in strategy_totals.items():
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        strategy_ranking.append({
            "strategy_id": sid,
            "name": data["name"],
            "avg_score": round(avg_score, 1),
            "symbols_evaluated": len(data["scores"]),
            "max_score": round(max(data["scores"]), 1) if data["scores"] else 0,
            "min_score": round(min(data["scores"]), 1) if data["scores"] else 0
        })
    
    strategy_ranking.sort(key=lambda x: x["avg_score"], reverse=True)
    
    # Add rank
    for i, r in enumerate(strategy_ranking, 1):
        r["rank"] = i
    
    # Best symbol per strategy
    best_per_strategy = {}
    for r in all_results:
        sid = r["strategy_id"]
        if sid not in best_per_strategy or r["score"] > best_per_strategy[sid]["score"]:
            best_per_strategy[sid] = r
    
    output = {
        "timestamp": datetime.now().isoformat(),
        "total_strategies": len(strategies),
        "total_symbols": len(symbol_scores),
        "strategy_ranking": strategy_ranking,
        "best_opportunities": [
            {
                "rank": i + 1,
                "strategy_id": r["strategy_id"],
                "strategy_name": r.get("strategy_name", r["strategy_id"]),
                "symbol": r["symbol"],
                "score": r["score"],
                "price": r.get("current_price")
            }
            for i, (sid, r) in enumerate(
                sorted(best_per_strategy.items(), key=lambda x: x[1]["score"], reverse=True)
            )
        ],
        "symbol_scores": {
            sym: sorted(scores, key=lambda x: x["score"], reverse=True)
            for sym, scores in symbol_scores.items()
        }
    }
    
def generate_live_ranking() -> dict:
    """Generate live ranking across all strategies and symbols."""
    
    executor = StrategyExecutor()
    strategies = executor.enabled_strategies
    
    all_results = []
    symbol_scores = {}
    
    for strategy in strategies:
        symbols = strategy.get("symbols", [])
        for symbol in symbols:
            result = evaluate_strategy_live(strategy, symbol)
            if result:
                all_results.append(result)
                
                # Track symbol-level scores
                if symbol not in symbol_scores:
                    symbol_scores[symbol] = []
                symbol_scores[symbol].append({
                    "strategy": strategy["id"],
                    "score": result["score"]
                })
    
    # Calculate strategy average scores
    strategy_totals = {}
    for r in all_results:
        sid = r["strategy_id"]
        if sid not in strategy_totals:
            strategy_totals[sid] = {"scores": [], "name": r.get("strategy_name", sid)}
        strategy_totals[sid]["scores"].append(r["score"])
    
    strategy_ranking = []
    for sid, data in strategy_totals.items():
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        strategy_ranking.append({
            "strategy_id": sid,
            "name": data["name"],
            "avg_score": round(avg_score, 1),
            "symbols_evaluated": len(data["scores"]),
            "max_score": round(max(data["scores"]), 1) if data["scores"] else 0,
            "min_score": round(min(data["scores"]), 1) if data["scores"] else 0
        })
    
    strategy_ranking.sort(key=lambda x: x["avg_score"], reverse=True)
    
    # Add rank
    for i, r in enumerate(strategy_ranking, 1):
        r["rank"] = i
    
    # Best symbol per strategy
    best_per_strategy = {}
    for r in all_results:
        sid = r["strategy_id"]
        if sid not in best_per_strategy or r["score"] > best_per_strategy[sid]["score"]:
            best_per_strategy[sid] = r
    
    output = {
        "timestamp": datetime.now().isoformat(),
        "total_strategies": len(strategies),
        "total_symbols": len(symbol_scores),
        "strategy_ranking": strategy_ranking,
        "best_opportunities": [
            {
                "rank": i + 1,
                "strategy_id": r["strategy_id"],
                "strategy_name": r.get("strategy_name", r["strategy_id"]),
                "symbol": r["symbol"],
                "score": r["score"],
                "price": r.get("current_price")
            }
            for i, (sid, r) in enumerate(
                sorted(best_per_strategy.items(), key=lambda x: x[1]["score"], reverse=True)
            )
        ],
        "symbol_scores": {
            sym: sorted(scores, key=lambda x: x["score"], reverse=True)
            for sym, scores in symbol_scores.items()
        }
    }
    
    # Save to alternate path to avoid overwriting scheduler's ranking
    output_path = Path("state/live_strategy_ranking_script.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    return output


if __name__ == "__main__":
    result = generate_live_ranking()
    
    print("=" * 60)
    print("LIVE STRATEGY RANKING")
    print("=" * 60)
    print(f"\nTimestamp: {result['timestamp']}")
    print(f"Strategies: {result['total_strategies']}")
    print(f"Symbols: {result['total_symbols']}")
    print("\n" + "=" * 60)
    print("STRATEGY RANKING (by avg score across all symbols)")
    print("=" * 60)
    
    for r in result["strategy_ranking"]:
        print(f"\n#{r['rank']} {r['name']}")
        print(f"   Avg Score: {r['avg_score']}%")
        print(f"   Symbols: {r['symbols_evaluated']}")
        print(f"   Range: {r['min_score']}% ~ {r['max_score']}%")
    
    print("\n" + "=" * 60)
    print("TOP OPPORTUNITIES")
    print("=" * 60)
    
    for opp in result["best_opportunities"][:5]:
        print(f"\n#{opp['rank']} {opp['strategy_name']}")
        print(f"   Symbol: {opp['symbol']}")
        print(f"   Score: {opp['score']}%")
        print(f"   Price: ${opp['price']}")
    
    print("\n" + "=" * 60)
    print(f"Saved to: state/live_strategy_ranking.json")
    print("=" * 60)
