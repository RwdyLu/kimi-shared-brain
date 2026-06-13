#!/usr/bin/env python3
"""
Fitness Scoring System / 適應度評分系統

計算策略在回測中的綜合表現分數。
參考 Freqtrade HyperOpt 的評分邏輯 + 基因算法的 multi-objective 概念。

Fitness = 複合分數 (0~1)，越高越好。

Author: second_bot
Date: 2026-05-22
"""

import math
from typing import Dict, List, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class BacktestMetrics:
    """回測指標集合"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_trade_duration: float = 0.0  # minutes
    
    # 額外
    consecutive_losses: int = 0
    best_trade: float = 0.0
    worst_trade: float = 0.0


def sigmoid(x: float, scale: float = 1.0) -> float:
    """Sigmoid 轉換，將任意值映射到 0~1"""
    try:
        return 1.0 / (1.0 + math.exp(-x * scale))
    except:
        return 0.5


def normalize(value: float, min_val: float, max_val: float, clamp: bool = True) -> float:
    """線性正規化到 0~1"""
    if max_val == min_val:
        return 0.5
    norm = (value - min_val) / (max_val - min_val)
    if clamp:
        norm = max(0.0, min(1.0, norm))
    return norm


def calculate_metrics(trades: List[Dict[str, Any]], equity_curve: List[float]) -> BacktestMetrics:
    """
    從交易記錄和權益曲線計算指標
    
    trades: [{symbol, entry_price, exit_price, entry_time, exit_time, pnl_pct, direction}]
    equity_curve: [balance_t0, balance_t1, ...]
    """
    if not trades:
        return BacktestMetrics()
    
    profits = [t["pnl_pct"] for t in trades]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    
    total_trades = len(trades)
    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    
    avg_profit = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    total_pnl = sum(profits)
    
    # Profit Factor = 總盈利 / |總虧損|
    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else 999.0
    
    # Expectancy = (勝率 * 平均盈利) + (敗率 * 平均虧損)
    expectancy = (win_rate * avg_profit) + ((1 - win_rate) * avg_loss)
    
    # Sharpe (簡化版，用交易收益)
    if len(profits) > 1:
        mean_return = np.mean(profits)
        std_return = np.std(profits)
        sharpe = (mean_return / std_return) * math.sqrt(252 * 12) if std_return > 0 else 0
        # 上面 * sqrt(252*12) 是假設 5m K 線，調整到年化
        # 但對基因評估來說，相對值就夠了
    else:
        sharpe = 0
    
    # Max Drawdown from equity curve
    max_dd = 0.0
    peak = equity_curve[0] if equity_curve else 1.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > max_dd:
            max_dd = dd
    
    # Average trade duration
    durations = []
    for t in trades:
        if t.get("entry_time") and t.get("exit_time"):
            # 簡化：假設 entry/exit_time 是 timestamp 或 datetime
            try:
                dur = (t["exit_time"] - t["entry_time"]) / 60000  # ms -> minutes
                durations.append(dur)
            except:
                pass
    avg_duration = np.mean(durations) if durations else 0
    
    # Consecutive losses
    max_consecutive = 0
    current = 0
    for p in profits:
        if p <= 0:
            current += 1
            max_consecutive = max(max_consecutive, current)
        else:
            current = 0
    
    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        avg_profit=avg_profit,
        avg_loss=avg_loss,
        total_pnl=total_pnl,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        profit_factor=profit_factor,
        expectancy=expectancy,
        avg_trade_duration=avg_duration,
        consecutive_losses=max_consecutive,
        best_trade=max(profits) if profits else 0,
        worst_trade=min(profits) if profits else 0,
    )


def compute_fitness(metrics: BacktestMetrics, min_trades: int = 20) -> float:
    """
    計算綜合 Fitness Score (0.0 ~ 1.0)
    
    多目標加權：
    - 夏普比率: 30%
    - 期望值: 25%
    - (1 - 最大回撤): 20%
    - 勝率: 10%
    - Profit Factor: 10%
    - 交易次數懲罰: 低於 min_trades 大幅扣分
    """
    
    # 交易次數不足 → 直接懲罰
    if metrics.total_trades < 5:
        return 0.01  # 幾乎無法評估
    
    trade_penalty = 1.0
    if metrics.total_trades < min_trades:
        # 線性懲罰：5筆=0.2, 20筆=1.0
        trade_penalty = max(0.1, metrics.total_trades / min_trades)
    
    # 各項標準化
    # Sharpe: 期望 ~0~2，但基因評估中 >0.5 就算不錯
    sharpe_score = sigmoid(metrics.sharpe_ratio, scale=2.0)
    
    # Expectancy: 每次交易期望收益，>0.001 算好
    expectancy_score = sigmoid(metrics.expectancy * 100, scale=5.0)  # 放大 100x
    
    # Max Drawdown: 越低越好，直接轉換
    dd_score = 1.0 - min(1.0, metrics.max_drawdown)
    
    # Win Rate: 40%~60% 是合理區間，極端值要懲罰
    if metrics.win_rate < 0.20:
        wr_score = metrics.win_rate / 0.20 * 0.3  # 低於 20% 大幅扣分
    elif metrics.win_rate > 0.80:
        wr_score = 0.7 + (1.0 - metrics.win_rate) / 0.20 * 0.3  # 高於 80% 可能過擬合
    else:
        wr_score = normalize(metrics.win_rate, 0.20, 0.80)
    
    # Profit Factor: >1.5 算好，<1.0 直接死
    if metrics.profit_factor < 1.0:
        pf_score = 0.0
    else:
        pf_score = normalize(metrics.profit_factor, 1.0, 3.0)
    
    # 連續虧損懲罰
    cl_penalty = 1.0
    if metrics.consecutive_losses >= 10:
        cl_penalty = 0.5
    elif metrics.consecutive_losses >= 6:
        cl_penalty = 0.8
    
    # 加權組合
    fitness = (
        sharpe_score * 0.30 +
        expectancy_score * 0.25 +
        dd_score * 0.20 +
        wr_score * 0.10 +
        pf_score * 0.10 +
        (1.0 if metrics.total_pnl > 0 else 0.0) * 0.05  # 總盈利為正加分
    )
    
    # 應用懲罰
    fitness *= trade_penalty * cl_penalty
    
    return max(0.0, min(1.0, fitness))


def compute_fitness_details(metrics: BacktestMetrics) -> Dict[str, float]:
    """返回詳細的 fitness 分項"""
    sharpe_score = sigmoid(metrics.sharpe_ratio, scale=2.0)
    expectancy_score = sigmoid(metrics.expectancy * 100, scale=5.0)
    dd_score = 1.0 - min(1.0, metrics.max_drawdown)
    
    if metrics.win_rate < 0.20:
        wr_score = metrics.win_rate / 0.20 * 0.3
    elif metrics.win_rate > 0.80:
        wr_score = 0.7 + (1.0 - metrics.win_rate) / 0.20 * 0.3
    else:
        wr_score = normalize(metrics.win_rate, 0.20, 0.80)
    
    pf_score = 0.0 if metrics.profit_factor < 1.0 else normalize(metrics.profit_factor, 1.0, 3.0)
    
    return {
        "sharpe_score": round(sharpe_score, 4),
        "expectancy_score": round(expectancy_score, 4),
        "drawdown_score": round(dd_score, 4),
        "winrate_score": round(wr_score, 4),
        "profit_factor_score": round(pf_score, 4),
        "raw_sharpe": round(metrics.sharpe_ratio, 4),
        "raw_expectancy": round(metrics.expectancy, 6),
        "raw_drawdown": round(metrics.max_drawdown, 4),
        "raw_winrate": round(metrics.win_rate, 4),
        "raw_pf": round(metrics.profit_factor, 4),
        "total_trades": metrics.total_trades,
        "total_pnl": round(metrics.total_pnl, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 多幣種聚合評分
# ═══════════════════════════════════════════════════════════════════════════════

def aggregate_fitness(
    per_symbol_metrics: Dict[str, BacktestMetrics],
    aggregation: str = "mean"
) -> float:
    """
    多幣種回測結果的聚合評分
    
    aggregation:
        "mean" — 平均分（適合分散策略）
        "worst" — 最差的幣種分數（適合穩健策略）
        "weighted" — 按交易次數加權
    """
    if not per_symbol_metrics:
        return 0.0
    
    scores = []
    for symbol, metrics in per_symbol_metrics.items():
        score = compute_fitness(metrics)
        scores.append((symbol, score, metrics.total_trades))
    
    if aggregation == "mean":
        return sum(s[1] for s in scores) / len(scores)
    
    elif aggregation == "worst":
        return min(s[1] for s in scores)
    
    elif aggregation == "weighted":
        total_weight = sum(s[2] for s in scores)
        if total_weight == 0:
            return sum(s[1] for s in scores) / len(scores)
        return sum(s[1] * s[2] for s in scores) / total_weight
    
    else:
        return sum(s[1] for s in scores) / len(scores)
