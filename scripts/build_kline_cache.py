#!/usr/bin/env python3
"""
KLine Cache Builder / K線快取建立器

抓取 10 個幣種 × 3 個時間框架，從 2023-01-01 到今天，存成 Parquet。
已存在檔案會自動跳過（可中斷後恢復）。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone
from typing import List, Optional

from data.fetcher import BinanceFetcher, SUPPORTED_SYMBOLS, SUPPORTED_INTERVALS

# ── 參數 ──
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "kline_cache"
START_DATE = "2023-01-01"
END_DATE = None  # today


def fetch_all_klines(fetcher: BinanceFetcher, symbol: str, interval: str,
                     start_ms: int, end_ms: int, limit: int = 1000) -> List[list]:
    """分頁抓取所有 K 線，直到 start >= end"""
    all_klines = []
    current_start = start_ms
    max_loops = 5000
    loop = 0

    while current_start < end_ms and loop < max_loops:
        try:
            chunk = fetcher.fetch_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                start_time=current_start,
                end_time=end_ms,
            )
        except Exception as e:
            print(f"    ⚠️  Error fetching {symbol} {interval} @ {current_start}: {e}")
            time.sleep(1)
            loop += 1
            continue

        if not chunk or len(chunk) == 0:
            break

        all_klines.extend(chunk)

        last_close = int(chunk[-1][6])
        next_start = last_close + 1

        if next_start <= current_start:
            break
        current_start = next_start

        loop += 1
        if loop % 100 == 0:
            print(f"    ... fetched {len(all_klines):,} klines so far")

    return all_klines


def build_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = BinanceFetcher()

    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)

    if END_DATE:
        end_dt = datetime.strptime(END_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_ms = int(end_dt.timestamp() * 1000)
    else:
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    print(f"Cache dir: {CACHE_DIR}")
    print(f"Range: {START_DATE} → {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    print(f"Symbols: {len(SUPPORTED_SYMBOLS)} | Intervals: {len(SUPPORTED_INTERVALS)}")
    print("=" * 50)

    total_files = 0
    total_rows = 0
    skipped = 0

    for symbol in SUPPORTED_SYMBOLS:
        for interval in SUPPORTED_INTERVALS:
            parquet_path = CACHE_DIR / f"{symbol}_{interval}.parquet"

            # 已存在則跳過
            if parquet_path.exists():
                print(f"\n[{symbol} / {interval}] → SKIP (already exists)")
                skipped += 1
                continue

            print(f"\n[{symbol} / {interval}] → {parquet_path.name}")

            t0 = time.time()
            raw = fetch_all_klines(fetcher, symbol, interval, start_ms, end_ms)
            fetch_time = time.time() - t0

            if not raw:
                print(f"    ⚠️  No data fetched")
                continue

            df = pd.DataFrame(raw, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            for col in ['timestamp', 'close_time']:
                df[col] = pd.to_datetime(df[col], unit='ms', utc=True)
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
                        'taker_buy_base', 'taker_buy_quote']:
                df[col] = df[col].astype(float)
            for col in ['trades', 'ignore']:
                df[col] = df[col].astype(int)

            before_dedup = len(df)
            df = df.drop_duplicates(subset='timestamp', keep='last')
            after_dedup = len(df)
            if before_dedup != after_dedup:
                print(f"    🧹 Deduplicated: {before_dedup:,} → {after_dedup:,}")

            df = df.sort_values('timestamp').reset_index(drop=True)
            df.to_parquet(parquet_path, compression='zstd', index=False)

            size_mb = parquet_path.stat().st_size / (1024 * 1024)
            print(f"    ✅ {after_dedup:,} rows | {fetch_time:.1f}s fetch | {size_mb:.2f}MB")

            total_files += 1
            total_rows += after_dedup

    print(f"\n{'=' * 50}")
    print(f"Done. {total_files} new files, {skipped} skipped, {total_rows:,} total new rows.")
    print(f"Cache dir: {CACHE_DIR}")


if __name__ == "__main__":
    build_cache()
