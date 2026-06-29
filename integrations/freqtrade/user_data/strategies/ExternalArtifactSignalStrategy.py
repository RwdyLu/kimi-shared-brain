from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from freqtrade.strategy import IStrategy


class ExternalArtifactSignalStrategy(IStrategy):
    """Dry-run bridge for approved Kimi strategy artifacts.

    This strategy does not contain GA search logic. It only consumes an external
    signal table produced by the research engine. Keep this in dry-run until the
    artifact approval status is paper-ready and the operator explicitly enables it.
    """

    timeframe = "4h"
    can_short = False
    minimal_roi = {"0": 1000}
    stoploss = -0.99
    process_only_new_candles = True
    startup_candle_count = 200

    @property
    def signal_path(self) -> Path:
        raw = os.environ.get("KIMI_SIGNAL_CSV", "user_data/signals/external_signals.csv")
        return Path(raw)

    @staticmethod
    def _normalize_pair(pair: str) -> str:
        return pair.replace("/", "").replace(":", "").upper()

    def _load_signals(self, pair: str) -> pd.DataFrame:
        path = self.signal_path
        if not path.exists():
            return pd.DataFrame(columns=["date", "enter_long", "exit_long"])
        df = pd.read_csv(path)
        if "date" not in df.columns:
            return pd.DataFrame(columns=["date", "enter_long", "exit_long"])
        df["date"] = pd.to_datetime(df["date"], utc=True)
        if "pair" in df.columns:
            normalized = df["pair"].astype(str).map(self._normalize_pair)
            df = df[normalized == self._normalize_pair(pair)]
        for col in ["enter_long", "exit_long"]:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df[["date", "enter_long", "exit_long"]].drop_duplicates("date", keep="last")

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        signals = self._load_signals(metadata["pair"])
        if signals.empty:
            dataframe["external_enter_long"] = 0
            dataframe["external_exit_long"] = 0
            return dataframe
        merged = dataframe.merge(signals, on="date", how="left")
        dataframe["external_enter_long"] = merged["enter_long"].fillna(0).astype(int)
        dataframe["external_exit_long"] = merged["exit_long"].fillna(0).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["external_enter_long"] == 1, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["external_exit_long"] == 1, "exit_long"] = 1
        return dataframe
