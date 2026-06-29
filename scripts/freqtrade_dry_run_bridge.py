#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[1]
DEFAULT_OUT = BASE / "integrations" / "freqtrade"


STRATEGY_TEMPLATE = '''from __future__ import annotations

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

    timeframe = "{timeframe}"
    can_short = False
    minimal_roi = {{"0": 1000}}
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
'''


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def dry_run_config(pair: str, timeframe: str) -> dict[str, Any]:
    return {
        "$schema": "https://schema.freqtrade.io/schema.json",
        "dry_run": True,
        "trading_mode": "spot",
        "margin_mode": "",
        "max_open_trades": 1,
        "stake_currency": "USDT",
        "stake_amount": 50,
        "tradable_balance_ratio": 0.2,
        "fiat_display_currency": "USD",
        "timeframe": timeframe,
        "cancel_open_orders_on_exit": True,
        "exchange": {
            "name": "binance",
            "key": "",
            "secret": "",
            "ccxt_config": {"enableRateLimit": True},
            "ccxt_async_config": {"enableRateLimit": True},
            "pair_whitelist": [pair],
            "pair_blacklist": [],
        },
        "pairlists": [{"method": "StaticPairList"}],
        "entry_pricing": {"price_side": "same", "use_order_book": True, "order_book_top": 1},
        "exit_pricing": {"price_side": "same", "use_order_book": True, "order_book_top": 1},
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "api_server": {"enabled": False, "listen_ip_address": "127.0.0.1", "listen_port": 8080},
        "bot_name": "kimi-artifact-dry-run",
        "initial_state": "stopped",
        "force_entry_enable": False,
        "internals": {"process_throttle_secs": 5},
    }


def pair_from_symbol(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return f"{symbol[:-4]}/USDT"
    return symbol


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Freqtrade dry-run scaffold for approved strategy artifacts.")
    parser.add_argument("--artifact", required=True, help="Path to artifact directory or manifest.json")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    if not artifact_path.is_absolute():
        artifact_path = BASE / artifact_path
    manifest_path = artifact_path if artifact_path.name == "manifest.json" else artifact_path / "manifest.json"
    manifest = load_json(manifest_path)
    if not manifest:
        raise SystemExit(f"Missing artifact manifest: {manifest_path}")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = BASE / out_dir
    symbol = manifest.get("symbol") or "ETHUSDT"
    pair = pair_from_symbol(symbol)
    timeframe = manifest.get("timeframe") or "4h"
    status = manifest.get("approval_status") or "unknown"

    strategy_path = out_dir / "user_data" / "strategies" / "ExternalArtifactSignalStrategy.py"
    config_path = out_dir / "config_dry_run_template.json"
    signal_path = out_dir / "user_data" / "signals" / "external_signals.csv"
    readme_path = out_dir / "README.md"
    for path in [strategy_path, config_path, signal_path, readme_path]:
        if path.exists() and not args.force:
            raise SystemExit(f"Refusing to overwrite {path}; rerun with --force")

    write_text(strategy_path, STRATEGY_TEMPLATE.format(timeframe=timeframe))
    save_json(config_path, dry_run_config(pair, timeframe))
    write_text(
        signal_path,
        "date,pair,enter_long,exit_long\n"
        f"2026-01-01T00:00:00Z,{pair},0,0\n",
    )
    write_text(
        readme_path,
        f"""# Freqtrade Dry-Run Bridge

Artifact: `{manifest.get('strategy_id')}`

Approval status: `{status}`

This directory is a dry-run scaffold only. It does not contain Binance API keys,
does not enable live trading, and starts Freqtrade in `initial_state=stopped`.

Use this bridge only after the artifact is `paper_ready_requires_manual_launch`,
or after a manual operator override. The current bridge reads external signals
from `user_data/signals/external_signals.csv` or from `$KIMI_SIGNAL_CSV`.

Signal CSV schema:

```csv
date,pair,enter_long,exit_long
2026-01-01T00:00:00Z,{pair},0,0
```

Suggested dry-run command after installing Freqtrade separately:

```bash
freqtrade trade --config integrations/freqtrade/config_dry_run_template.json --strategy ExternalArtifactSignalStrategy --userdir integrations/freqtrade/user_data
```

Keep this in spot mode, no leverage, fixed stake, and dry-run until the full
approval chain has passed.
""",
    )

    print(
        json.dumps(
            {
                "artifact": str(manifest_path),
                "approval_status": status,
                "strategy": str(strategy_path),
                "config": str(config_path),
                "signals": str(signal_path),
                "live_trading_enabled": False,
                "dry_run": True,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
