from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPT = ROOT / "scripts" / "v9_contract_latest_market_signal.py"
SPEC = importlib.util.spec_from_file_location("v9_contract_latest_market_signal", SCRIPT)
assert SPEC and SPEC.loader
signal_mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signal_mod)


def write_symbol_cache(cache_dir: Path, symbol: str, closes: list[float]) -> None:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    rows = []
    previous = closes[0]
    for idx, close in enumerate(closes):
        open_price = previous if idx else close
        rows.append(
            {
                "open_time": int((start + pd.Timedelta(hours=idx)).timestamp() * 1000),
                "open": open_price,
                "high": max(open_price, close) * 1.001,
                "low": min(open_price, close) * 0.999,
                "close": close,
                "volume": 1000.0 + idx,
            }
        )
        previous = close
    frame = pd.DataFrame(rows)
    frame.to_parquet(cache_dir / f"{symbol}_1h_2026-01.parquet", index=False)


def base_args(tmp_path: Path, *, symbols: str) -> Namespace:
    return Namespace(
        cache_dir=str(tmp_path),
        timeframe="1h",
        universe_json="",
        top_n=20,
        symbols=symbols,
        lookback_bars=240,
        fast_ema=24,
        slow_ema=96,
        slope_n=12,
        breakout_n=24,
        breakout_buffer=0.002,
        atr_n=14,
        rsi_n=14,
        min_votes=5,
        min_slope=0.001,
        min_ret_24h=0.003,
        max_long_rsi=75.0,
        min_short_rsi=25.0,
        stop_atr_mult=2.0,
        min_stop_pct=0.01,
        reward_r=2.0,
        risk_per_trade=0.005,
        leverage_cap=2.0,
        out_json=str(tmp_path / "signal.json"),
        out_md=str(tmp_path / "signal.md"),
        marker=str(tmp_path / "FOUND.txt"),
        no_marker=str(tmp_path / "NO.txt"),
        format="text",
    )


def test_latest_market_signal_builds_long_paper_plan(tmp_path: Path) -> None:
    closes = [100.0 * (1.0015**idx) for idx in range(180)]
    write_symbol_cache(tmp_path, "AAAUSDT", closes)

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="AAAUSDT"))

    best = payload["top"][0]
    plan = best["paper_plan"]
    assert payload["summary"]["paper_plan_found"] is True
    assert payload["summary"]["paper_trading_authorized"] is False
    assert payload["summary"]["live_trading_authorized"] is False
    assert best["signal"] == "long"
    assert plan["stop_loss"] < plan["entry_price"] < plan["take_profit"]
    assert plan["order_intent"]["entry"] == "paper_only_no_order"


def test_latest_market_signal_builds_short_paper_plan(tmp_path: Path) -> None:
    closes = [180.0 * (0.9985**idx) for idx in range(180)]
    write_symbol_cache(tmp_path, "BBBUSDT", closes)

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="BBBUSDT"))

    best = payload["top"][0]
    plan = best["paper_plan"]
    assert payload["summary"]["paper_plan_found"] is True
    assert best["signal"] == "short"
    assert plan["take_profit"] < plan["entry_price"] < plan["stop_loss"]


def test_latest_market_signal_rejects_flat_market(tmp_path: Path) -> None:
    closes = [100.0 for _ in range(180)]
    write_symbol_cache(tmp_path, "CCCUSDT", closes)

    payload = signal_mod.run_screen(base_args(tmp_path, symbols="CCCUSDT"))

    assert payload["summary"]["paper_plan_found"] is False
    assert payload["top"][0]["signal"] == "none"


def test_latest_market_signal_writes_found_and_no_markers(tmp_path: Path) -> None:
    found_marker = tmp_path / "FOUND.txt"
    no_marker = tmp_path / "NO.txt"
    payload = {
        "updated_at": "2026-07-17T00:00:00+00:00",
        "summary": {"rows": 1, "paper_plan_found": True},
        "top": [
            {
                "symbol": "AAAUSDT",
                "signal": "long",
                "paper_plan": {
                    "entry_price": 100.0,
                    "stop_loss": 99.0,
                    "take_profit": 102.0,
                    "risk_per_trade": 0.005,
                    "leverage_cap": 2.0,
                },
            }
        ],
    }

    signal_mod.write_marker(payload, found_marker, no_marker)

    assert found_marker.exists()
    assert "FOUND_CONTRACT_MARKET_PAPER_PLAN" in found_marker.read_text()
    assert not no_marker.exists()

    payload["summary"]["paper_plan_found"] = False
    signal_mod.write_marker(payload, found_marker, no_marker)

    assert no_marker.exists()
    assert "NO_CONTRACT_MARKET_PAPER_PLAN" in no_marker.read_text()
    assert not found_marker.exists()
