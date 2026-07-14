from __future__ import annotations

import math
from argparse import Namespace
from pathlib import Path

import pandas as pd

from scripts.v9_funding_delta_neutral_paper_screen import (
    DeltaNeutralFundingConfig,
    build_event_detail,
    current_signal,
    run_screen,
)


def write_funding_cache(root: Path, symbols: tuple[str, ...], *, events: int = 300) -> Path:
    funding_dir = root / "funding"
    funding_dir.mkdir()
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    funding_times = [int((start + pd.Timedelta(hours=8 * idx)).timestamp() * 1000) for idx in range(events)]
    for symbol in symbols:
        base_rate = {
            "AAAUSDT": 0.00030,
            "BBBUSDT": 0.00022,
            "CCCUSDT": 0.00004,
            "DDDUSDT": -0.00005,
        }[symbol]
        frame = pd.DataFrame(
            {
                "symbol": [symbol] * len(funding_times),
                "funding_time": funding_times,
                "funding_rate": [
                    base_rate + 0.00001 * math.sin(idx / 9.0)
                    for idx in range(len(funding_times))
                ],
            }
        )
        frame.to_parquet(funding_dir / f"{symbol}_funding_2025-01.parquet", index=False)
    return funding_dir


def base_args(tmp_path: Path, funding_dir: Path) -> Namespace:
    return Namespace(
        cache_dir=str(funding_dir),
        universe_json="",
        top_n=4,
        symbols="AAAUSDT,BBBUSDT,CCCUSDT,DDDUSDT",
        start="2025-01-01",
        end="",
        lookback_events_grid="5,9",
        max_positions_grid="1,2",
        min_trailing_funding_bps_grid="1.0,2.0",
        turnover_cost_bps=0.0,
        stress_turnover_cost_bps=2.0,
        capital_multiplier=2.0,
        selection_frac=0.7,
        min_validation_events=30,
        min_capital_annualized_return=0.03,
        min_current_capital_annualized_return=0.05,
        max_drawdown=0.05,
        out_json=str(tmp_path / "screen.json"),
        out_md=str(tmp_path / "screen.md"),
        marker=str(tmp_path / "FOUND.txt"),
        no_marker=str(tmp_path / "NO.txt"),
        format="text",
    )


def test_event_detail_selects_positive_funding_symbols(tmp_path: Path) -> None:
    symbols = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
    funding_dir = write_funding_cache(tmp_path, symbols)
    frame = pd.concat(pd.read_parquet(path) for path in funding_dir.glob("*.parquet"))
    cfg = DeltaNeutralFundingConfig(
        lookback_events=5,
        max_positions=2,
        min_trailing_funding_rate=0.00010,
        turnover_cost_bps=0.0,
        stress_turnover_cost_bps=2.0,
    )

    detail = build_event_detail(frame, cfg, turnover_cost_bps=0.0)

    active = detail[detail["position_count"] > 0]
    assert not active.empty
    assert set(active.iloc[-1]["short_perp_symbols"]) == {"AAAUSDT", "BBBUSDT"}
    assert active["net_capital_return"].mean() > 0


def test_current_signal_reports_short_perp_long_spot(tmp_path: Path) -> None:
    symbols = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
    funding_dir = write_funding_cache(tmp_path, symbols)
    frame = pd.concat(pd.read_parquet(path) for path in funding_dir.glob("*.parquet"))
    cfg = DeltaNeutralFundingConfig(
        lookback_events=5,
        max_positions=1,
        min_trailing_funding_rate=0.00010,
        turnover_cost_bps=0.0,
        stress_turnover_cost_bps=2.0,
    )

    signal = current_signal(frame, cfg)

    assert signal["position_count"] == 1
    assert signal["positions"][0]["symbol"] == "AAAUSDT"
    assert signal["positions"][0]["side"] == "short_perp_long_spot"
    assert signal["expected_capital_annualized_return"] > 0.05


def test_run_screen_writes_paper_watch_marker(tmp_path: Path) -> None:
    symbols = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")
    funding_dir = write_funding_cache(tmp_path, symbols)
    args = base_args(tmp_path, funding_dir)

    payload = run_screen(args)

    assert payload["summary"]["paper_watch_candidate_found"] is True
    assert payload["top"][0]["paper_watch_candidate"] is True
    assert payload["top"][0]["current_signal"]["position_count"] > 0
    assert payload["summary"]["paper_trading_authorized"] is False
