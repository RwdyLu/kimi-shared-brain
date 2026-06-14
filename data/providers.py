"""Market data provider contracts and verified historical-file provider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

import pandas as pd

from data.fetcher import interval_to_ms, validate_klines


SUPPORTED_RESEARCH_INTERVALS = {"1m", "5m", "4h", "1d"}


@dataclass(frozen=True)
class DataProvenance:
    provider_id: str
    source_type: str
    is_mock: bool
    is_verified: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "source_type": self.source_type,
            "is_mock": self.is_mock,
            "is_verified": self.is_verified,
        }


@runtime_checkable
class DataProvider(Protocol):
    """Minimal provider contract consumed by the backtest cache."""

    provenance: DataProvenance

    def fetch_klines_paginated(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
        validate: bool = True,
        verbose: bool = False,
        max_pages: Optional[int] = None,
        strict_validation: bool = False,
    ) -> Tuple[List[List], Dict[str, Any]]:
        ...

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        ...


class HistoricalCSVProvider:
    """
    Read real OHLCV history from ``root/{symbol}_{interval}.csv``.

    Required columns: timestamp, open, high, low, close, volume. Timestamp may
    be milliseconds since epoch or an ISO datetime. Files are validated for
    ordering, duplicates, continuity, range and candle count before ranking.
    """

    provenance = DataProvenance(
        provider_id="historical_csv",
        source_type="historical_file",
        is_mock=False,
        is_verified=True,
    )
    DEFAULT_SESSION_SYMBOLS = {
        "510300", "510500", "159915", "588000", "518880", "159934",
    }

    def __init__(
        self,
        root: Path | str,
        session_symbols: Optional[List[str]] = None,
    ):
        self.root = Path(root)
        self.session_symbols = set(session_symbols or self.DEFAULT_SESSION_SYMBOLS)

    @staticmethod
    def _safe_symbol(symbol: str) -> str:
        return symbol.replace("/", "_").replace(":", "_")

    def _path(self, symbol: str, interval: str) -> Path:
        if interval not in SUPPORTED_RESEARCH_INTERVALS:
            raise ValueError(f"Unsupported research interval: {interval}")
        return self.root / f"{self._safe_symbol(symbol)}_{interval}.csv"

    def is_session_based(self, symbol: str) -> bool:
        return symbol in self.session_symbols

    def _load(self, symbol: str, interval: str) -> pd.DataFrame:
        path = self._path(symbol, interval)
        if not path.exists():
            raise FileNotFoundError(f"Historical data file not found: {path}")

        df = pd.read_csv(path)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")

        if pd.api.types.is_numeric_dtype(df["timestamp"]):
            df["timestamp"] = df["timestamp"].astype("int64")
        else:
            parsed = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
            df["timestamp"] = parsed.astype("int64") // 10**6

        for column in ("open", "high", "low", "close", "volume"):
            df[column] = pd.to_numeric(df[column], errors="raise")
        return df.sort_values("timestamp").reset_index(drop=True)

    @staticmethod
    def _to_raw_klines(df: pd.DataFrame, interval: str) -> List[List]:
        interval_ms = interval_to_ms(interval)
        rows: List[List] = []
        for row in df.itertuples(index=False):
            timestamp = int(row.timestamp)
            rows.append([
                timestamp,
                str(row.open),
                str(row.high),
                str(row.low),
                str(row.close),
                str(row.volume),
                timestamp + interval_ms - 1,
                "0",
                0,
                "0",
                "0",
                "0",
            ])
        return rows

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List]:
        df = self._load(symbol, interval)
        if start_time is not None:
            df = df[df["timestamp"] >= start_time]
        if end_time is not None:
            df = df[df["timestamp"] <= end_time]
        return self._to_raw_klines(df.head(limit), interval)

    def fetch_klines_paginated(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000,
        validate: bool = True,
        verbose: bool = False,
        max_pages: Optional[int] = None,
        strict_validation: bool = False,
    ) -> Tuple[List[List], Dict[str, Any]]:
        del limit, verbose, max_pages
        df = self._load(symbol, interval)
        df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= end_time)]
        klines = self._to_raw_klines(df, interval)
        if not validate:
            validation = {"valid": True, "data_invalid": False}
        elif symbol in self.session_symbols:
            validation = self._validate_session_data(
                klines, symbol, interval, start_time, end_time, strict_validation
            )
        else:
            expected_count = (end_time - start_time) // interval_to_ms(interval)
            validation = validate_klines(
                klines,
                expected_start_ms=start_time,
                expected_end_ms=end_time,
                expected_count=expected_count,
                interval=interval,
                symbol=symbol,
                strict=strict_validation,
            )
        validation["provenance"] = self.provenance.to_dict()
        return klines, validation

    @staticmethod
    def _validate_session_data(
        klines: List[List],
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        strict: bool,
    ) -> Dict[str, Any]:
        """Validate exchange-session data without treating overnight gaps as missing."""
        result: Dict[str, Any] = {
            "valid": False,
            "data_invalid": False,
            "actual_count": len(klines),
            "actual_start_ms": None,
            "actual_end_ms": None,
            "gaps": [],
            "warnings": [],
            "errors": [],
        }
        if not klines:
            result["errors"].append(f"[{symbol}] Empty kline data")
            result["data_invalid"] = strict
            return result

        timestamps = [int(row[0]) for row in klines]
        result["actual_start_ms"] = timestamps[0]
        result["actual_end_ms"] = timestamps[-1]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            result["errors"].append(f"[{symbol}] Timestamps are unsorted or duplicated")

        step = interval_to_ms(interval)
        if interval != "1d":
            for previous, current in zip(timestamps, timestamps[1:]):
                previous_day = pd.to_datetime(previous, unit="ms", utc=True).date()
                current_day = pd.to_datetime(current, unit="ms", utc=True).date()
                if previous_day == current_day and current - previous != step:
                    result["gaps"].append((previous, current))
                    result["errors"].append(
                        f"[{symbol}] Intraday gap: {previous} -> {current}"
                    )

        margin = step * 2
        if abs(timestamps[0] - start_time) > margin:
            result["warnings"].append(f"[{symbol}] Requested start is not covered")
        if abs(timestamps[-1] - end_time) > margin:
            result["warnings"].append(f"[{symbol}] Requested end is not covered")

        if result["errors"] and strict:
            result["data_invalid"] = True
        result["valid"] = not result["errors"]
        return result


def require_official_data(provider: DataProvider) -> None:
    """Reject mock, random, demo or unverified sources for formal ranking."""
    provenance = provider.provenance
    if provenance.is_mock or not provenance.is_verified:
        raise ValueError(
            "Official ranking requires verified non-mock market data; "
            f"got provider={provenance.provider_id}"
        )
