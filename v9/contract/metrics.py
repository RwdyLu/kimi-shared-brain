from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateConfig:
    min_trades: int = 100
    max_drawdown: float = 0.20
    min_cvar5_r: float = -1.50
    max_deep_drawdown_loss_frac: float = 0.02
    min_profit_factor: float = 1.05
    require_positive_folds: bool = True


def cvar(values: list[float], frac: float = 0.05) -> float:
    xs = sorted(v for v in values if math.isfinite(v))
    if not xs:
        return 0.0
    n = max(1, int(math.ceil(len(xs) * frac)))
    return float(sum(xs[:n]) / n)


def max_drawdown(values: list[float]) -> float:
    peak = None
    worst = 0.0
    for value in values:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            worst = max(worst, (peak - value) / peak)
    return float(worst)


def profit_factor(pnls: list[float]) -> float | None:
    gains = sum(v for v in pnls if v > 0)
    losses = -sum(v for v in pnls if v < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return float(gains / losses)


def fold_pnls(trades: list[dict[str, Any]], folds: int = 3) -> list[dict[str, Any]]:
    if not trades:
        return []
    ordered = sorted(trades, key=lambda t: str(t["entry_time"]))
    n = len(ordered)
    out = []
    for fold in range(folds):
        lo = int(fold * n / folds)
        hi = int((fold + 1) * n / folds)
        part = ordered[lo:hi]
        out.append(
            {
                "fold": fold,
                "trades": len(part),
                "net_pnl": float(sum(float(t["net_pnl"]) for t in part)),
                "start": part[0]["entry_time"] if part else None,
                "end": part[-1]["exit_time"] if part else None,
            }
        )
    return out


def evaluate_gates(base: dict[str, Any], cost2: dict[str, Any], cfg: GateConfig | None = None) -> dict[str, Any]:
    cfg = cfg or GateConfig()
    initial = float(base.get("initial_equity", 0.0) or 0.0)
    deep = base.get("by_entry_regime", {}).get("deep_drawdown", {})
    deep_pnl = float(deep.get("net_pnl", 0.0) or 0.0)
    folds = base.get("folds", [])
    pf = base.get("profit_factor")
    pf_ok = bool(pf is not None and (math.isinf(float(pf)) or float(pf) >= cfg.min_profit_factor))

    checks = {
        "min_trades": int(base.get("trade_count", 0)) >= cfg.min_trades,
        "base_net_pnl_positive": float(base.get("net_pnl", 0.0)) > 0.0,
        "cost2_net_pnl_positive": float(cost2.get("net_pnl", 0.0)) > 0.0,
        "cvar5_r_ok": float(base.get("cvar5_r", 0.0)) >= cfg.min_cvar5_r,
        "max_drawdown_ok": float(base.get("max_drawdown", 1.0)) <= cfg.max_drawdown,
        "residual_flat": int(base.get("residual_positions", 1)) == 0,
        "deep_drawdown_loss_ok": deep_pnl >= -initial * cfg.max_deep_drawdown_loss_frac,
        "profit_factor_ok": pf_ok,
    }
    if cfg.require_positive_folds:
        checks["folds_all_positive"] = bool(folds) and all(float(f.get("net_pnl", 0.0)) > 0.0 for f in folds)

    failures = [name for name, passed in checks.items() if not passed]
    score = (
        float(base.get("net_pnl", 0.0)) / initial if initial else 0.0
    ) + (
        float(cost2.get("net_pnl", 0.0)) / initial if initial else 0.0
    ) + float(base.get("avg_r", 0.0)) * 0.10 + float(base.get("cvar5_r", 0.0)) * 0.05 - float(base.get("max_drawdown", 0.0))

    return {
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "score": float(score),
        "config": {
            "min_trades": cfg.min_trades,
            "max_drawdown": cfg.max_drawdown,
            "min_cvar5_r": cfg.min_cvar5_r,
            "max_deep_drawdown_loss_frac": cfg.max_deep_drawdown_loss_frac,
            "min_profit_factor": cfg.min_profit_factor,
            "require_positive_folds": cfg.require_positive_folds,
        },
    }
