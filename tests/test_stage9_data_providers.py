"""Stage 9 tests: verified providers, ETF rules and official ranking isolation."""

from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from app.genetic_engine.backtest_engine import GeneBacktestEngine, KlineCache
from app.genetic_engine.backtest_engine_v2 import GeneBacktestEngineV2
from app.genetic_engine.market_rules import rules_for_symbol
from app.strategy_ranking import StrategyRanking, StrategyScore
from data.fetcher import BinanceFetcher, interval_to_ms
from data.providers import DataProvenance, HistoricalCSVProvider, require_official_data


def _write_history(
    root: Path,
    symbol: str = "510300",
    interval: str = "1d",
    count: int = 5,
    gap_at: Optional[int] = None,
) -> tuple[int, int]:
    step = interval_to_ms(interval)
    start = 1_700_000_000_000
    timestamps = []
    for index in range(count):
        offset = index + (1 if gap_at is not None and index >= gap_at else 0)
        timestamps.append(start + offset * step)
    pd.DataFrame({
        "timestamp": timestamps,
        "open": [4.0] * count,
        "high": [4.1] * count,
        "low": [3.9] * count,
        "close": [4.0] * count,
        "volume": [1_000_000] * count,
    }).to_csv(root / f"{symbol}_{interval}.csv", index=False)
    return timestamps[0], timestamps[-1]


def test_research_intervals_cover_intraday_and_daily():
    assert interval_to_ms("1m") == 60_000
    assert interval_to_ms("5m") == 300_000
    assert interval_to_ms("4h") == 14_400_000
    assert interval_to_ms("1d") == 86_400_000
    assert (10 * 365 * 24 * 60 * 60 * 1000) // interval_to_ms("1d") == 3650


def test_verified_csv_provider_loads_cn_etf_history(tmp_path):
    start, end = _write_history(tmp_path)
    provider = HistoricalCSVProvider(tmp_path)
    klines, validation = provider.fetch_klines_paginated(
        "510300", "1d", start, end, strict_validation=True
    )

    assert len(klines) == 5
    assert validation["valid"] is True
    assert validation["data_invalid"] is False
    assert validation["provenance"]["provider_id"] == "historical_csv"


def test_csv_gap_fails_closed(tmp_path):
    start, end = _write_history(tmp_path, interval="5m", gap_at=3)
    provider = HistoricalCSVProvider(tmp_path)
    _, validation = provider.fetch_klines_paginated(
        "510300", "5m", start, end, strict_validation=True
    )
    assert validation["valid"] is False
    assert validation["data_invalid"] is True
    assert validation["gaps"]


def test_cache_accepts_replaceable_provider(tmp_path):
    start, end = _write_history(tmp_path)
    provider = HistoricalCSVProvider(tmp_path)
    cache = KlineCache(tmp_path / "cache")
    df, validation = cache.load_or_fetch(
        provider, "510300", "1d", start, end, strict_validation=True
    )
    assert df is not None
    assert len(df) == 5
    assert validation["valid"] is True
    assert cache.has_cache("510300", "1d")


def test_session_history_hits_cache_without_refetch(tmp_path):
    start, end = _write_history(tmp_path)
    provider = HistoricalCSVProvider(tmp_path)
    cache = KlineCache(tmp_path / "cache")
    cache.load_or_fetch(provider, "510300", "1d", start, end, strict_validation=True)

    original_fetch = provider.fetch_klines_paginated

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider should not be called on a valid cache hit")

    provider.fetch_klines_paginated = fail_if_called
    try:
        df, validation = cache.load_or_fetch(
            provider, "510300", "1d", start, end, strict_validation=True
        )
    finally:
        provider.fetch_klines_paginated = original_fetch

    assert df is not None
    assert len(df) == 5
    assert validation["valid"] is True


def test_cn_etf_and_gold_rules_apply_lots_commission_and_tax():
    etf = rules_for_symbol("510300")
    gold = rules_for_symbol("518880")

    assert etf.lot_step == etf.lot_min == 100.0
    assert etf.buy_fee(10_000) == pytest.approx(3.0)
    assert etf.sell_fee(10_000) == pytest.approx(3.0)
    assert gold.market == "cn_gold_etf"
    assert gold.sell_tax_rate == 0.0


def test_v2_engine_uses_market_rules_and_verified_provider(tmp_path):
    provider = HistoricalCSVProvider(tmp_path)
    rules = rules_for_symbol("510300")
    engine = GeneBacktestEngineV2(
        data_provider=provider,
        market_rules=rules,
    )
    assert engine.fetcher is provider
    assert engine.lot_step == 100.0
    assert engine.lot_min == 100.0
    assert engine.buy_fee_rate == pytest.approx(0.0003)
    assert engine.sell_fee_rate == pytest.approx(0.0003)


def test_v2_engine_auto_selects_registered_etf_rules(tmp_path):
    provider = HistoricalCSVProvider(tmp_path)
    engine = GeneBacktestEngineV2(data_provider=provider)
    engine._apply_market_rules_for_symbol("518880")
    assert engine.market_rules.market == "cn_gold_etf"
    assert engine.lot_step == 100.0
    assert engine.sell_fee_rate == pytest.approx(0.0003)


def test_official_ranking_rejects_mock_and_unverified_data():
    ranking = StrategyRanking(official=True)
    with pytest.raises(ValueError, match="Official ranking rejects"):
        ranking.add_strategy(StrategyScore(
            strategy_id="mock",
            symbol="510300",
            timeframe="1d",
            data_source="random_demo",
            data_is_mock=True,
            data_validated=False,
        ))

    ranking.add_strategy(StrategyScore(
        strategy_id="verified",
        symbol="510300",
        timeframe="1d",
        data_source="historical_csv",
        data_is_mock=False,
        data_validated=True,
    ))
    assert len(ranking.rankings) == 1


def test_provider_gate_rejects_mock_source():
    class MockProvider:
        provenance = DataProvenance(
            provider_id="random_demo",
            source_type="generated",
            is_mock=True,
            is_verified=False,
        )

    with pytest.raises(ValueError, match="verified non-mock"):
        require_official_data(MockProvider())


def test_binance_provider_is_marked_verified_real_data():
    engine = GeneBacktestEngine()
    assert isinstance(engine.fetcher, BinanceFetcher)
    assert engine.data_provenance.is_mock is False
    assert engine.data_provenance.is_verified is True
