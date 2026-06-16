#!/usr/bin/env python3
"""
Fitness Scoring System V2 / 適應度評分系統 V2

核心理念：GA 的目的不是尋找歷史最高收益率（過擬合），
而是在極端市場環境中尋找「高勝率決策」與「極低摩擦成本」的數學極值點。

設計準則來自文件《核心準則：進化的物理意義》：
- Alpha vs Ghost DCA 基準（不是絕對收益，是超額收益）
- 交易摩擦懲罰（雙邊手續費，過度頻繁交易會被摩擦成本抽乾）
- 指數級最大回撤懲罰（淘汰死扛運氣基因）
- 最小交易單位截斷模擬（真實撮合規則）
- 連續虧損懲罰

Author: second_bot
Date: 2026-05-28
"""

import math
import random
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field
import numpy as np


@dataclass
class BacktestMetricsV2:
    """V2 回測指標集合 — 加入 DCA 基準與摩擦成本"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    total_pnl: float = 0.0  # 策略總收益
    total_pnl_after_fees: float = 0.0  # 扣除手續費後的淨收益
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_trade_duration: float = 0.0  # minutes
    consecutive_losses: int = 0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    
    # ═══════════════════════════════════════════
    # V2 新增：DCA 基準相關
    # ═══════════════════════════════════════════
    ghost_dca_pnl: float = 0.0  # 同期 Ghost DCA 收益
    alpha_vs_dca: float = 0.0   # 超額收益 = 策略 - DCA
    alpha_per_trade: float = 0.0  # 每筆交易平均超額
    
    # ═══════════════════════════════════════════
    # V2 新增：摩擦成本
    # ═══════════════════════════════════════════
    total_fees_paid: float = 0.0     # 總手續費
    fee_drag_pct: float = 0.0        # 手續費拖累比例（相對本金）
    friction_penalty_score: float = 0.0  # 摩擦懲罰分數（越低越好）
    friction_penalty: float = 0.0  # friction penalty amount (n_trades * fee_rate * 2)
    
    # ═══════════════════════════════════════════
    # V2 新增：風險指標
    # ═══════════════════════════════════════════
    ruin_probability: float = 0.0    # 蒙特卡洛資金耗盡概率
    calmar_ratio: float = 0.0        # 年化收益 / 最大回撤
    
    # ═══════════════════════════════════════════
    # V2 新增：倉位狀態（宏觀/微觀混合模型用）
    # ═══════════════════════════════════════════
    dead_hold_value: float = 0.0     # 底倉價值
    float_hold_value: float = 0.0    # 浮動倉價值
    total_portfolio_value: float = 0.0  # 總組合價值

    # 資料無效標記（資料驗證失敗時設為 True，無法計算正常 fitness）
    data_invalid: bool = False

    def is_valid(self) -> bool:
        """檢查 metrics 是否有效（有交易數據）"""
        return self.total_trades > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函數
# ═══════════════════════════════════════════════════════════════════════════════

def sigmoid(x: float, scale: float = 1.0) -> float:
    """Sigmoid 轉換"""
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


def exp_decay_penalty(drawdown: float, steepness: float = 8.0) -> float:
    """
    指數級回撤懲罰
    
    dd=0% → 1.0
    dd=5% → ~0.67
    dd=10% → ~0.37
    dd=20% → ~0.05
    dd=30% → ~0.002
    
    線性懲罰會讓 30% 回撤還有 0.7 分，指數懲罰直接壓到接近 0。
    """
    return math.exp(-steepness * drawdown)


# ═══════════════════════════════════════════════════════════════════════════════
# Ghost DCA 計算
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_ghost_dca(
    prices: List[float],
    timestamps: List[int],
    initial_capital: float = 1000.0,
    dca_interval_hours: float = 168.0,  # 每週定投一次
    fee_rate: float = 0.001,
) -> Tuple[float, float, float, List[float]]:
    """
    計算 Ghost DCA（定期定額）基準線
    
    Returns:
        (total_invested, final_value, total_pnl_pct, equity_curve)
    """
    if not prices or len(prices) < 2:
        return initial_capital, initial_capital, 0.0, [initial_capital]
    
    # 計定投次數（根據時間間隔）
    # 簡化：每 N 根 K 線投一次
    total_hours = (timestamps[-1] - timestamps[0]) / 3600000  # ms → hours
    n_dca = max(1, int(total_hours / dca_interval_hours))
    
    per_dca_amount = initial_capital / n_dca
    
    total_shares = 0.0
    total_invested = 0.0
    equity_curve = []
    
    # 計算定投間隔的 K 線數
    klines_per_dca = max(1, len(prices) // n_dca) if n_dca > 0 else len(prices)
    
    for i, price in enumerate(prices):
        # 每次到達定投間隔就買入
        if i % klines_per_dca == 0 and total_invested < initial_capital:
            buy_amount = min(per_dca_amount, initial_capital - total_invested)
            shares_bought = (buy_amount * (1 - fee_rate)) / price
            total_shares += shares_bought
            total_invested += buy_amount
        
        # 計算當前權益
        current_value = total_shares * price
        equity_curve.append(current_value)
    
    final_value = total_shares * prices[-1]
    pnl_pct = (final_value - initial_capital) / initial_capital if initial_capital > 0 else 0.0
    
    return total_invested, final_value, pnl_pct, equity_curve


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics 計算（V2 版）
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_metrics_v2(
    trades: List[Dict[str, Any]],
    equity_curve: List[float],
    ghost_dca_pnl: float = 0.0,
    fee_rate: float = 0.001,
    prices: List[float] = None,
    timestamps: List[int] = None,
    initial_capital: float = 1000.0,
) -> BacktestMetricsV2:
    """
    從交易記錄和權益曲線計算 V2 指標
    
    核心改動：
    1. 加入摩擦成本計算
    2. 加入 Alpha vs DCA
    3. 指標更全面
    """
    if not trades:
        return BacktestMetricsV2(
            ghost_dca_pnl=ghost_dca_pnl,
            alpha_vs_dca=-ghost_dca_pnl,  # 沒交易 = 跑輸 DCA
        )
    
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
    
    # 摩擦成本計算
    # 每筆交易：進場手續費 + 出場手續費 = 2 * fee_rate
    # 但 pnl 已經包含了 fee deduction，所以我們需要計算「理論手續費」
    total_fees = total_trades * fee_rate * 2  # 雙邊
    total_pnl_after_fees = total_pnl  # pnl 已扣費
    fee_drag_pct = total_fees / initial_capital if initial_capital > 0 else 0
    
    # Profit Factor
    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    profit_factor = total_wins / total_losses if total_losses > 0 else 999.0
    
    # Expectancy
    expectancy = (win_rate * avg_profit) + ((1 - win_rate) * avg_loss)
    
    # Sharpe
    if len(profits) > 1:
        mean_return = np.mean(profits)
        std_return = np.std(profits)
        sharpe = (mean_return / std_return) * math.sqrt(252 * 12) if std_return > 0 else 0
    else:
        sharpe = 0
    
    # Max Drawdown（從權益曲線）
    max_dd = 0.0
    peak = equity_curve[0] if equity_curve else 1.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak
        if dd > max_dd:
            max_dd = dd
    
    # 平均持倉時間
    durations = []
    for t in trades:
        if t.get("entry_time") and t.get("exit_time"):
            try:
                dur = (t["exit_time"] - t["entry_time"]) / 60000
                durations.append(dur)
            except:
                pass
    avg_duration = np.mean(durations) if durations else 0
    
    # 連續虧損
    max_consecutive = 0
    current = 0
    for p in profits:
        if p <= 0:
            current += 1
            max_consecutive = max(max_consecutive, current)
        else:
            current = 0
    
    # Calmar Ratio（年化收益 / 最大回撤）
    calmar = (total_pnl / max_dd) if max_dd > 0 else (total_pnl * 100)
    
    # Alpha vs DCA
    alpha_vs_dca = total_pnl - ghost_dca_pnl
    alpha_per_trade = alpha_vs_dca / total_trades if total_trades > 0 else 0
    
    return BacktestMetricsV2(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        avg_profit=avg_profit,
        avg_loss=avg_loss,
        total_pnl=total_pnl,
        total_pnl_after_fees=total_pnl_after_fees,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        profit_factor=profit_factor,
        expectancy=expectancy,
        avg_trade_duration=avg_duration,
        consecutive_losses=max_consecutive,
        best_trade=max(profits) if profits else 0,
        worst_trade=min(profits) if profits else 0,
        ghost_dca_pnl=ghost_dca_pnl,
        alpha_vs_dca=alpha_vs_dca,
        alpha_per_trade=alpha_per_trade,
        total_fees_paid=total_fees,
        fee_drag_pct=fee_drag_pct,
        calmar_ratio=calmar,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 核心適應度計算（V2）
# ═══════════════════════════════════════════════════════════════════════════════

def compute_fitness_v2(
    metrics: BacktestMetricsV2,
    min_trades: int = 20,
    max_trades_for_scoring: int = 200,
) -> float:
    """
    V2 綜合 Fitness Score (0.0 ~ 1.0)
    
    核心變動：
    - Alpha vs DCA 成為核心指標（取代單純夏普）
    - 指數級回撤懲罰（不是線性）
    - 摩擦成本直接扣分（過度交易會被抽乾）
    - 連續虧損懲罰
    
    加權：
    - Alpha vs DCA: 35%（核心！超額收益才是真金）
    - (1 - 指數回撤懲罰): 25%（風控優先）
    - 摩擦效率: 20%（交易次數越接近 sweet spot 越高分）
    - 勝率: 10%
    - Profit Factor: 10%
    """
    
    # ═══════════════════════════════════════════
    # 1. 基本篩選
    # ═══════════════════════════════════════════
    if metrics.total_trades < 5:
        return 0.01
    
    # ═══════════════════════════════════════════
    # 2. Alpha vs DCA 評分（核心）
    # ═══════════════════════════════════════════
    # Alpha > 0 才算真正打敗定投
    # Alpha 範圍：-0.5 ~ +0.5 合理，使用 sigmoid
    alpha_raw = metrics.alpha_vs_dca
    alpha_score = sigmoid(alpha_raw * 4, scale=2.0)  # 放大 4x，讓 Alpha=0.125 時 score≈0.5
    
    # 如果策略連 DCA 都打不過，大幅扣分
    if alpha_raw < 0:
        alpha_score *= 0.5  # 負 Alpha 直接砍半
    
    # ═══════════════════════════════════════════
    # 3. 指數級回撤懲罰
    # ═══════════════════════════════════════════
    dd_penalty = exp_decay_penalty(metrics.max_drawdown, steepness=10.0)
    # 轉換為「分數」：越高越好
    dd_score = dd_penalty
    
    # ═══════════════════════════════════════════
    # 4. 摩擦效率評分
    # ═══════════════════════════════════════════
    # Sweet spot：20~100 筆交易（90 天回測期間）
    # 太少 = 樣本不足，太多 = 被摩擦抽乾
    n = metrics.total_trades
    if n < min_trades:
        friction_score = n / min_trades * 0.5  # 線性遞增
    elif n <= max_trades_for_scoring:
        # 20~200 筆之間，越接近 50 筆越好
        optimal = 50
        dist = abs(n - optimal)
        friction_score = max(0.3, 1.0 - (dist / max_trades_for_scoring))
    else:
        # >200 筆：過度交易，分數驟降
        excess = n - max_trades_for_scoring
        friction_score = max(0.0, 0.5 - (excess / 500))
    
    # 手續費拖累額外懲罰
    if metrics.fee_drag_pct > 0.05:  # 手續費吃掉 5% 以上本金
        friction_score *= 0.5
    elif metrics.fee_drag_pct > 0.02:
        friction_score *= 0.8
    
    # ═══════════════════════════════════════════
    # 5. 勝率評分
    # ═══════════════════════════════════════════
    if metrics.win_rate < 0.20:
        wr_score = metrics.win_rate / 0.20 * 0.3
    elif metrics.win_rate > 0.80:
        # 過高勝率可能是過擬合信號
        wr_score = 0.7 + (1.0 - metrics.win_rate) / 0.20 * 0.3
    else:
        wr_score = normalize(metrics.win_rate, 0.20, 0.80)
    
    # ═══════════════════════════════════════════
    # 6. Profit Factor 評分
    # ═══════════════════════════════════════════
    if metrics.profit_factor < 1.0:
        pf_score = 0.0
    else:
        pf_score = normalize(metrics.profit_factor, 1.0, 3.0)
    
    # ═══════════════════════════════════════════
    # 7. 連續虧損懲罰
    # ═══════════════════════════════════════════
    cl_penalty = 1.0
    if metrics.consecutive_losses >= 10:
        cl_penalty = 0.4  # 10 連虧 = 60% 扣分
    elif metrics.consecutive_losses >= 6:
        cl_penalty = 0.7
    elif metrics.consecutive_losses >= 4:
        cl_penalty = 0.9
    
    # ═══════════════════════════════════════════
    # 8. 總組合
    # ═══════════════════════════════════════════
    fitness = (
        alpha_score * 0.35 +       # Alpha vs DCA：核心
        dd_score * 0.25 +           # 回撤控制
        friction_score * 0.20 +     # 摩擦效率
        wr_score * 0.10 +           # 勝率
        pf_score * 0.10             # Profit Factor
    )
    
    # 應用懲罰
    fitness *= cl_penalty
    
    # 總虧損策略額外懲罰
    if metrics.total_pnl < 0 and metrics.alpha_vs_dca < 0:
        fitness *= 0.5
    
    return max(0.0, min(1.0, fitness))


def compute_fitness_details_v2(metrics: BacktestMetricsV2) -> Dict[str, Any]:
    """返回詳細的 V2 fitness 分項"""
    alpha_score = sigmoid(metrics.alpha_vs_dca * 4, scale=2.0)
    if metrics.alpha_vs_dca < 0:
        alpha_score *= 0.5
    
    dd_score = exp_decay_penalty(metrics.max_drawdown, steepness=10.0)
    
    # 摩擦效率
    n = metrics.total_trades
    optimal = 50
    if n < 20:
        friction_score = n / 20 * 0.5
    elif n <= 200:
        dist = abs(n - optimal)
        friction_score = max(0.3, 1.0 - (dist / 200))
    else:
        friction_score = max(0.0, 0.5 - ((n - 200) / 500))
    
    if metrics.fee_drag_pct > 0.05:
        friction_score *= 0.5
    elif metrics.fee_drag_pct > 0.02:
        friction_score *= 0.8
    
    if metrics.win_rate < 0.20:
        wr_score = metrics.win_rate / 0.20 * 0.3
    elif metrics.win_rate > 0.80:
        wr_score = 0.7 + (1.0 - metrics.win_rate) / 0.20 * 0.3
    else:
        wr_score = normalize(metrics.win_rate, 0.20, 0.80)
    
    pf_score = 0.0 if metrics.profit_factor < 1.0 else normalize(metrics.profit_factor, 1.0, 3.0)
    
    return {
        "alpha_score": round(alpha_score, 4),
        "alpha_raw": round(metrics.alpha_vs_dca, 4),
        "drawdown_score": round(dd_score, 4),
        "drawdown_raw": round(metrics.max_drawdown, 4),
        "friction_score": round(friction_score, 4),
        "fee_drag_pct": round(metrics.fee_drag_pct, 4),
        "winrate_score": round(wr_score, 4),
        "profit_factor_score": round(pf_score, 4),
        "total_trades": metrics.total_trades,
        "total_pnl": round(metrics.total_pnl, 4),
        "pnl_after_fees": round(metrics.total_pnl_after_fees, 4),
        "ghost_dca_pnl": round(metrics.ghost_dca_pnl, 4),
        "consecutive_losses": metrics.consecutive_losses,
        "calmar_ratio": round(metrics.calmar_ratio, 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 多幣種聚合評分（V2）
# ═══════════════════════════════════════════════════════════════════════════════

def aggregate_fitness_v2(
    per_symbol_metrics: Dict[str, BacktestMetricsV2],
    aggregation: str = "worst_alpha",
) -> float:
    """
    多幣種回測結果的聚合評分（V2）
    
    aggregation:
        "mean" — 平均分
        "worst" — 最差 fitness（穩健策略）
        "worst_alpha" — 最差 Alpha vs DCA（推薦！防止過擬合單一幣種）
        "weighted" — 按交易次數加權
    """
    if not per_symbol_metrics:
        return 0.0
    
    scores = []
    for symbol, metrics in per_symbol_metrics.items():
        score = compute_fitness_v2(metrics)
        alpha = metrics.alpha_vs_dca
        scores.append((symbol, score, metrics.total_trades, alpha))
    
    if aggregation == "mean":
        return sum(s[1] for s in scores) / len(scores)
    
    elif aggregation == "worst":
        return min(s[1] for s in scores)
    
    elif aggregation == "worst_alpha":
        # 按最差 Alpha 聚合 — 即使某幣種 fitness 高，只要有一個幣種 Alpha 很差就整體扣分
        worst_alpha = min(s[3] for s in scores)
        avg_fitness = sum(s[1] for s in scores) / len(scores)
        # 混合：平均 fitness 受最差 Alpha 拖累
        if worst_alpha < 0:
            penalty = 1.0 + worst_alpha  # worst_alpha 越負，penalty 越小
            return avg_fitness * max(0.3, penalty)
        return avg_fitness
    
    elif aggregation == "weighted":
        total_weight = sum(s[2] for s in scores)
        if total_weight == 0:
            return sum(s[1] for s in scores) / len(scores)
        return sum(s[1] * s[2] for s in scores) / total_weight
    
    else:
        return sum(s[1] for s in scores) / len(scores)


# ═══════════════════════════════════════════════════════════════════════════════
# 蒙特卡洛終審：計算資金耗盡概率
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_ruin_probability(
    trades: List[Dict[str, Any]],
    initial_capital: float = 1000.0,
    n_simulations: int = 1000,
    ruin_threshold: float = 0.5,  # 虧損 50% 視為資金耗盡
) -> float:
    """
    蒙特卡洛模擬計算資金耗盡概率
    
    不進入每代適應度打分，只在 Epoch 結束時對挑戰者追加一次。
    """
    if not trades or len(trades) < 10:
        return 0.0
    
    profits = [t["pnl_pct"] for t in trades]
    n_trades = len(profits)
    
    ruin_count = 0
    
    for _ in range(n_simulations):
        capital = initial_capital
        # 隨機抽樣交易序列（有放回）
        for _ in range(n_trades):
            pnl = np.random.choice(profits)
            capital *= (1 + pnl)
            if capital <= initial_capital * ruin_threshold:
                ruin_count += 1
                break
    
    return ruin_count / n_simulations


def calculate_monte_carlo_report(
    trades: List[Dict[str, Any]],
    initial_capital: float = 1000.0,
    n_simulations: int = 1000,
    ruin_threshold: float = 0.5,
    seed: int = 42,
) -> Dict[str, Any]:
    """Return reproducible ruin risk and final-return quantiles."""
    profits = [float(t["pnl_pct"]) for t in trades if "pnl_pct" in t]
    if len(profits) < 10:
        return {
            "insufficient_data": True,
            "sample_trades": len(profits),
            "simulations": 0,
            "ruin_probability": None,
            "return_quantiles": {},
        }

    rng = np.random.default_rng(seed)
    final_returns = []
    ruin_count = 0

    for _ in range(n_simulations):
        capital = initial_capital
        ruined = False
        for pnl in rng.choice(profits, size=len(profits), replace=True):
            capital *= 1.0 + pnl
            if capital <= initial_capital * ruin_threshold:
                ruined = True
                break
        ruin_count += int(ruined)
        final_returns.append((capital - initial_capital) / initial_capital)

    quantiles = np.quantile(final_returns, [0.05, 0.50, 0.95])
    return {
        "insufficient_data": False,
        "sample_trades": len(profits),
        "simulations": n_simulations,
        "ruin_probability": round(ruin_count / n_simulations, 6),
        "return_quantiles": {
            "p05": round(float(quantiles[0]), 6),
            "p50": round(float(quantiles[1]), 6),
            "p95": round(float(quantiles[2]), 6),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容性包裝（讓舊代碼也能用 V2）
# ═══════════════════════════════════════════════════════════════════════════════

def compute_fitness_v2_from_v1(
    total_trades: int,
    total_pnl: float,
    win_rate: float,
    max_drawdown: float,
    sharpe_ratio: float,
    profit_factor: float,
    expectancy: float,
    ghost_dca_pnl: float = 0.0,
    fee_rate: float = 0.001,
    initial_capital: float = 1000.0,
) -> float:
    """
    從舊版參數快速計算 V2 fitness（用於過渡期兼容）
    """
    total_fees = total_trades * fee_rate * 2
    fee_drag = total_fees / initial_capital
    
    alpha = total_pnl - ghost_dca_pnl
    
    metrics = BacktestMetricsV2(
        total_trades=total_trades,
        win_rate=win_rate,
        total_pnl=total_pnl,
        total_pnl_after_fees=total_pnl,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        profit_factor=profit_factor,
        expectancy=expectancy,
        ghost_dca_pnl=ghost_dca_pnl,
        alpha_vs_dca=alpha,
        total_fees_paid=total_fees,
        fee_drag_pct=fee_drag,
    )
    
    return compute_fitness_v2(metrics)


def calculate_monte_carlo_report(
    trades: List[Dict[str, Any]],
    initial_capital: float = 1000.0,
    n_simulations: int = 1000,
    ruin_threshold: float = 0.5,
    seed: int = 42,
) -> Dict[str, Any]:
    """Return reproducible ruin risk and final-return quantiles."""
    profits = [float(t["pnl_pct"]) for t in trades if "pnl_pct" in t]
    if len(profits) < 10:
        return {
            "insufficient_data": True,
            "sample_trades": len(profits),
            "simulations": 0,
            "ruin_probability": None,
            "return_quantiles": {},
            "seed": seed,
        }

    rng = np.random.default_rng(seed)
    final_returns = []
    ruin_count = 0

    for _ in range(n_simulations):
        capital = initial_capital
        ruined = False
        for pnl in rng.choice(profits, size=len(profits), replace=True):
            capital *= 1.0 + pnl
            if capital <= initial_capital * ruin_threshold:
                ruined = True
                break
        ruin_count += int(ruined)
        final_returns.append((capital - initial_capital) / initial_capital)

    quantiles = np.quantile(final_returns, [0.05, 0.50, 0.95])
    return {
        "insufficient_data": False,
        "sample_trades": len(profits),
        "simulations": n_simulations,
        "ruin_probability": round(ruin_count / n_simulations, 6),
        "return_quantiles": {
            "p05": round(float(quantiles[0]), 6),
            "p50": round(float(quantiles[1]), 6),
            "p95": round(float(quantiles[2]), 6),
        },
        "seed": seed,
    }


if __name__ == "__main__":
    # 簡單測試
    print("=== Fitness V2 Test ===")
    
    # 測試 1：優秀策略（打敗 DCA，低回撤，適度交易）
    m1 = BacktestMetricsV2(
        total_trades=45,
        win_rate=0.55,
        total_pnl=0.25,
        max_drawdown=0.08,
        ghost_dca_pnl=0.15,
        alpha_vs_dca=0.10,
        fee_drag_pct=0.009,
        profit_factor=1.8,
        expectancy=0.003,
    )
    print(f"優秀策略: fitness={compute_fitness_v2(m1):.4f}")
    print(f"  details: {compute_fitness_details_v2(m1)}")
    
    # 測試 2：過度交易（被摩擦抽乾）
    m2 = BacktestMetricsV2(
        total_trades=300,
        win_rate=0.52,
        total_pnl=0.05,
        max_drawdown=0.05,
        ghost_dca_pnl=0.15,
        alpha_vs_dca=-0.10,
        fee_drag_pct=0.06,
        profit_factor=1.2,
        expectancy=0.0002,
    )
    print(f"過度交易: fitness={compute_fitness_v2(m2):.4f}")
    
    # 測試 3：死扛大回撤
    m3 = BacktestMetricsV2(
        total_trades=30,
        win_rate=0.60,
        total_pnl=0.30,
        max_drawdown=0.35,
        ghost_dca_pnl=0.15,
        alpha_vs_dca=0.15,
        fee_drag_pct=0.006,
        profit_factor=2.0,
        consecutive_losses=8,
    )
    print(f"大回撤: fitness={compute_fitness_v2(m3):.4f}")
    
    # 測試指數回撤懲罰
    print("\n=== 指數回撤懲罰測試 ===")
    for dd in [0.02, 0.05, 0.10, 0.15, 0.20, 0.30]:
        penalty = exp_decay_penalty(dd, steepness=10.0)
        print(f"  DD={dd:.0%}: penalty_score={penalty:.4f}")
    
    # 測試 Ghost DCA
    print("\n=== Ghost DCA 測試 ===")
    prices = [100, 102, 98, 95, 110, 115, 108, 112, 120, 125]
    timestamps = list(range(0, len(prices) * 3600000, 3600000))
    invested, final, pnl, curve = calculate_ghost_dca(prices, timestamps, initial_capital=1000)
    print(f"  Invested={invested:.2f}, Final={final:.2f}, PnL={pnl:.2%}")
