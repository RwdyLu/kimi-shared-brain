from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lunar_genome_crypto_lab_v6 as lab


def make_genome() -> lab.LunarGenome:
    data = {name: (lo if typ is int else float(lo)) for name, (lo, _hi, typ) in lab.BOUNDS.items()}
    data.update(
        {
            "MaxDCAMonths": 6,
            "BetaThreshold": 0.03,
            "MoonPhasePressure": 0.0,
            "DeadlineForcePct": 0.10,
            "TMacro": 24,
            "TMicro": 6,
            "TDeadline": 48,
            "EMAAnchor": 50,
            "kp": 1.5,
            "kv": 2.0,
            "ka": -1.0,
            "MinTradeThreshold": 0.002,
            "MicroReserveRate": 0.15,
            "SigmoidScale": 2.0,
            "Gamma": 1.0,
            "Beta": 1.0,
            "RegimeRouterBlend": 0.5,
        }
    )
    return lab.LunarGenome(**data)


def make_args(record_trades: bool) -> argparse.Namespace:
    return argparse.Namespace(
        initial_cash=10000.0,
        cost_bps=20.0,
        lot_step=0.0001,
        lot_min=0.0001,
        min_notional=10.0,
        drawdown_penalty=1.0,
        max_drawdown=0.50,
        max_trades=10000,
        min_trades=1,
        min_positive_alpha_frac=0.0,
        min_alpha=-9.0,
        min_return=-9.0,
        timeframe="1h",
        window_bars=5000,
        signal_delay_bars=0,
        record_trades=record_trades,
    )


def strip_trade_only_fields(metrics: dict) -> dict:
    clean = dict(metrics)
    per = {}
    for symbol, row in (clean.get("per_symbol") or {}).items():
        r = dict(row)
        r.pop("trade_log", None)
        r.pop("trade_log_final_price", None)
        r.pop("trade_log_initial_cash", None)
        per[symbol] = r
    clean["per_symbol"] = per
    return clean


def test_record_trades_preserves_metrics_and_reconstructs_equity() -> None:
    close = np.linspace(100.0, 160.0, 1600, dtype=np.float64)
    open_time = np.arange(1600, dtype=np.int64) * 3_600_000
    markets = {"BTCUSDT": {"close": close, "high": close * 1.001, "low": close * 0.999, "open_time": open_time}}
    genome = make_genome()
    env = lab.Environment(DeadReserveRatio=0.20, GlobalStopLoss=0.80)
    season = lab.Season(0.9, 1.0, 1.0, 1.1, tick_offset=0)

    off = lab.evaluate_individual(genome, env, season, markets, random.Random(7), make_args(False))
    on = lab.evaluate_individual(genome, env, season, markets, random.Random(7), make_args(True))

    assert strip_trade_only_fields(on) == strip_trade_only_fields(off)
    row = on["per_symbol"]["BTCUSDT"]
    trades = row["trade_log"]
    assert len(trades) == row["trades"]
    assert abs(sum(t["fee"] for t in trades) - row["cost"]) < 1e-9

    cash = row["trade_log_initial_cash"]
    qty = 0.0
    for trade in trades:
        cash += trade["cash_delta"]
        qty += trade["qty_delta"]
    reconstructed = cash + qty * row["trade_log_final_price"]
    assert abs(reconstructed - row["equity"]) < 1e-6
