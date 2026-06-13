#!/usr/bin/env python3
"""
Mass Scanner / 大規模策略掃描器

並行生成 + 回測 + 篩選隨機策略染色體，尋找能在多幣種上獲利的策略。

運行邏輯：
  1. 每批次生成 1,000 個隨機染色體
  2. 使用 ThreadPoolExecutor 並行回測（workers = CPU 核心數）
     — 採用 threading 避免 fork 複製記憶體造成 OOM
  3. 篩選：PnL>0、回撤<15%、交易>20筆、勝率>45%
  4. 結果寫入 SQLite（data/scan_results.db）
  5. 持續跑到找到 100 個合格策略，或評估滿 50,000 個
  6. 每 1,000 個輸出進度到 data/scan_progress.json（可由外部監控發 Discord）
  7. 結束時輸出 TOP_50.json（按 PnL 排序）

Author: second_bot
Date: 2026-06-01
"""

import os
import sys
import json
import time
import random
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.genetic_engine.chromosome import random_chromosome, StrategyChromosome
from app.genetic_engine.backtest_engine import (
    GeneBacktestEngine,
    evaluate_chromosome_multi_symbol,
)
from app.genetic_engine.fitness import BacktestMetrics

# ── 設定 ──────────────────────────────────────────────────────────────────────

DB_PATH = BASE_DIR / "data" / "scan_results.db"
PROGRESS_PATH = BASE_DIR / "data" / "scan_progress.json"
TOP50_PATH = BASE_DIR / "data" / "TOP_50.json"

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
    "ADAUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT",
    "AVAXUSDT", "LINKUSDT",
]
INTERVAL = "5m"
DAYS = 90
BATCH_SIZE = 1000
TARGET_PASS = 100
MAX_TOTAL = 50_000
WORKERS = min(os.cpu_count() or 2, 4)  # 上限 4，避免過度並行踩 API

# 篩選門檻
MIN_PNL = 0.0            # PnL > 0（實際獲利）
MAX_DRAWDOWN = 0.15      # 回撤 < 15%
MIN_TRADES = 20          # 交易次數 > 20
MIN_WIN_RATE = 0.45      # 勝率 > 45%


# ═══════════════════════════════════════════════════════════════════════════════
# SQLite 管理
# ═══════════════════════════════════════════════════════════════════════════════

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id     TEXT    NOT NULL,
    chromosome_id TEXT  NOT NULL UNIQUE,
    generation  INTEGER DEFAULT 0,
    genes_json  TEXT    NOT NULL,
    total_trades INTEGER,
    win_rate    REAL,
    total_pnl   REAL,
    max_drawdown REAL,
    sharpe_ratio REAL,
    profit_factor REAL,
    fitness_score REAL,
    passed_filter INTEGER DEFAULT 0,
    per_symbol_json TEXT,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_passed ON scan_results(passed_filter, total_pnl DESC);
CREATE INDEX IF NOT EXISTS idx_scan   ON scan_results(scan_id);
"""


def init_db() -> sqlite3.Connection:
    """初始化 SQLite 資料庫"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SQL_SCHEMA)
    conn.commit()
    return conn


def insert_result(
    conn: sqlite3.Connection,
    scan_id: str,
    chrom: StrategyChromosome,
    agg_metrics: BacktestMetrics,
    per_symbol: Dict[str, BacktestMetrics],
    passed: bool,
) -> None:
    """寫入單條回測結果"""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO scan_results
        (scan_id, chromosome_id, generation, genes_json,
         total_trades, win_rate, total_pnl, max_drawdown,
         sharpe_ratio, profit_factor, fitness_score,
         passed_filter, per_symbol_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_id,
            chrom.chromosome_id,
            chrom.generation,
            json.dumps(chrom.to_dict(), default=str),
            agg_metrics.total_trades,
            agg_metrics.win_rate,
            agg_metrics.total_pnl,
            agg_metrics.max_drawdown,
            agg_metrics.sharpe_ratio,
            agg_metrics.profit_factor,
            chrom.fitness_score,
            1 if passed else 0,
            json.dumps({s: asdict(m) for s, m in per_symbol.items()}, default=str),
        ),
    )
    conn.commit()


def get_passed_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM scan_results WHERE passed_filter = 1")
    return cur.fetchone()[0]


def get_top_n(conn: sqlite3.Connection, n: int = 50) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM scan_results
        WHERE passed_filter = 1
        ORDER BY total_pnl DESC
        LIMIT ?
        """,
        (n,),
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合多幣種指標
# ═══════════════════════════════════════════════════════════════════════════════

def aggregate_metrics(per_symbol: Dict[str, BacktestMetrics]) -> BacktestMetrics:
    """
    將多幣種指標聚合為單一 BacktestMetrics。
    總交易數加總，PnL/回撤/勝率取平均。
    """
    if not per_symbol:
        return BacktestMetrics()

    total_trades = sum(m.total_trades for m in per_symbol.values())
    total_wins = sum(m.winning_trades for m in per_symbol.values())

    avg_pnl = sum(m.total_pnl for m in per_symbol.values()) / len(per_symbol)
    avg_dd = sum(m.max_drawdown for m in per_symbol.values()) / len(per_symbol)
    avg_sharpe = sum(m.sharpe_ratio for m in per_symbol.values()) / len(per_symbol)
    avg_pf = sum(m.profit_factor for m in per_symbol.values()) / len(per_symbol)

    win_rate = total_wins / total_trades if total_trades > 0 else 0.0

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=total_wins,
        losing_trades=total_trades - total_wins,
        win_rate=win_rate,
        total_pnl=avg_pnl,
        max_drawdown=avg_dd,
        sharpe_ratio=avg_sharpe,
        profit_factor=avg_pf,
    )


def passes_filter(metrics: BacktestMetrics) -> bool:
    """檢查是否通過篩選條件"""
    return (
        metrics.total_pnl > MIN_PNL
        and metrics.max_drawdown < MAX_DRAWDOWN
        and metrics.total_trades > MIN_TRADES
        and metrics.win_rate > MIN_WIN_RATE
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 並行工作函數
# ═══════════════════════════════════════════════════════════════════════════════

def worker_init():
    """每個 worker 初始化時呼叫：建立獨立的 engine 實例"""
    global _WORKER_ENGINE
    _WORKER_ENGINE = GeneBacktestEngine()


def worker_evaluate(args: Tuple[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    單個 worker 的評估任務

    args = (chromosome_id, chrom_dict)
    returns = {
        "chromosome_id": str,
        "genes_dict": dict,
        "fitness": float,
        "passed": bool,
        "agg_metrics": dict,  # BacktestMetrics as dict
        "per_symbol": dict,   # {symbol: BacktestMetrics as dict}
        "error": str or None,
    }
    """
    chrom_id, chrom_dict = args
    try:
        chrom = StrategyChromosome.from_dict(chrom_dict)
        fitness, per_symbol, _ = evaluate_chromosome_multi_symbol(
            chrom,
            symbols=DEFAULT_SYMBOLS,
            engine=_WORKER_ENGINE,
            interval=INTERVAL,
            days=DAYS,
            verbose=False,
        )
        agg = aggregate_metrics(per_symbol)
        passed = passes_filter(agg)

        return {
            "chromosome_id": chrom_id,
            "genes_dict": chrom_dict,
            "fitness": fitness,
            "passed": passed,
            "agg_metrics": asdict(agg),
            "per_symbol": {s: asdict(m) for s, m in per_symbol.items()},
            "error": None,
        }
    except Exception as e:
        return {
            "chromosome_id": chrom_id,
            "genes_dict": chrom_dict,
            "fitness": 0.0,
            "passed": False,
            "agg_metrics": asdict(BacktestMetrics()),
            "per_symbol": {},
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 批次生成器
# ═══════════════════════════════════════════════════════════════════════════════

def generate_batch(n: int, generation: int = 0) -> List[Tuple[str, Dict[str, Any]]]:
    """生成 n 個隨機染色體，回傳 [(chrom_id, chrom_dict), ...]"""
    batch = []
    for _ in range(n):
        chrom = random_chromosome(generation=generation)
        batch.append((chrom.chromosome_id, chrom.to_dict()))
    return batch


# ═══════════════════════════════════════════════════════════════════════════════
# 進度報告
# ═══════════════════════════════════════════════════════════════════════════════

def write_progress(
    scan_id: str,
    total_evaluated: int,
    passed_count: int,
    batch_time: float,
    current_top_pnl: Optional[float] = None,
) -> None:
    """寫入進度 JSON，供外部監控腳本或 OpenClaw 讀取並發 Discord"""
    progress = {
        "scan_id": scan_id,
        "timestamp": datetime.now().isoformat(),
        "total_evaluated": total_evaluated,
        "passed_count": passed_count,
        "target_pass": TARGET_PASS,
        "max_total": MAX_TOTAL,
        "batch_time_sec": round(batch_time, 2),
        "current_top_pnl": current_top_pnl,
        "status": "running" if passed_count < TARGET_PASS and total_evaluated < MAX_TOTAL else "complete",
    }
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_PATH, "w") as f:
        json.dump(progress, f, indent=2)


def print_progress(scan_id: str, total: int, passed: int, batch_time: float) -> None:
    """終端輸出進度摘要"""
    progress_pct = (total / MAX_TOTAL) * 100
    print(
        f"\n📊 [{scan_id}] Batch done: {total:,} evaluated | "
        f"✅ {passed} passed ({passed / max(total, 1) * 100:.1f}%) | "
        f"⏱️ {batch_time:.1f}s | Progress: {progress_pct:.1f}%\n"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 主掃描迴圈
# ═══════════════════════════════════════════════════════════════════════════════

def run_scan(
    scan_id: Optional[str] = None,
    workers: int = WORKERS,
    batch_size: int = BATCH_SIZE,
    target_pass: int = TARGET_PASS,
    max_total: int = MAX_TOTAL,
    test_mode: bool = False,
) -> Dict[str, Any]:
    """
    主掃描迴圈

    test_mode=True: 只跑 100 個，方便快速驗證流程
    """
    if scan_id is None:
        scan_id = f"SCAN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if test_mode:
        max_total = 100
        batch_size = 100
        target_pass = 10

    print(f"🚀 Mass Scanner Starting — scan_id: {scan_id}")
    print(f"   Workers: {workers} | Batch: {batch_size} | Target: {target_pass} | Max: {max_total}")
    print(f"   Symbols: {len(DEFAULT_SYMBOLS)} ({', '.join(DEFAULT_SYMBOLS[:3])}...)")
    print(f"   Filter: PnL>{MIN_PNL}, DD<{MAX_DRAWDOWN}, Trades>{MIN_TRADES}, WR>{MIN_WIN_RATE}")
    print(f"   DB: {DB_PATH}")
    print(f"   Progress file: {PROGRESS_PATH}\n")

    # 初始化資料庫
    conn = init_db()
    total_evaluated = 0
    passed_count = get_passed_count(conn)

    # 預熱快取：在 fork 子行程前把資料載入父行程記憶體
    # Linux fork 會 copy-on-write 共享，避免每個 worker 重複載入
    print("🔥 Pre-warming cache for all symbols...")
    _warm_engine = GeneBacktestEngine()
    for sym in DEFAULT_SYMBOLS:
        _warm_engine.cache.load(sym, INTERVAL)
    print(f"   Cache warmed: {len(DEFAULT_SYMBOLS)} symbols\n")

    # 啟動 worker pool
    pool = mp.Pool(processes=workers, initializer=worker_init)

    try:
        while passed_count < target_pass and total_evaluated < max_total:
            current_batch_size = min(batch_size, max_total - total_evaluated)
            batch = generate_batch(current_batch_size, generation=0)

            t0 = time.time()
            results = pool.map(worker_evaluate, batch)
            batch_time = time.time() - t0

            # 寫入資料庫
            for res in results:
                total_evaluated += 1
                chrom = StrategyChromosome.from_dict(res["genes_dict"])
                chrom.fitness_score = res["fitness"]
                agg = BacktestMetrics(**res["agg_metrics"])
                per_symbol = {
                    s: BacktestMetrics(**m) for s, m in res["per_symbol"].items()
                }
                passed = res["passed"]

                insert_result(conn, scan_id, chrom, agg, per_symbol, passed)
                if passed:
                    passed_count += 1

            # 報告進度
            print_progress(scan_id, total_evaluated, passed_count, batch_time)
            write_progress(scan_id, total_evaluated, passed_count, batch_time)

            # 每批次後可選：短暫休息避免過熱
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    finally:
        pool.close()
        pool.join()
        conn.close()

    # 結束輸出 TOP_50
    conn = init_db()
    top50 = get_top_n(conn, 50)
    conn.close()

    TOP50_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOP50_PATH, "w") as f:
        json.dump(top50, f, indent=2, default=str)

    summary = {
        "scan_id": scan_id,
        "total_evaluated": total_evaluated,
        "passed_count": passed_count,
        "pass_rate": passed_count / max(total_evaluated, 1),
        "top_50_path": str(TOP50_PATH),
        "db_path": str(DB_PATH),
    }

    print(f"\n{'=' * 60}")
    print(f"🏁 Scan Complete!")
    print(f"   Evaluated: {total_evaluated:,}")
    print(f"   Passed:    {passed_count} ({summary['pass_rate'] * 100:.2f}%)")
    print(f"   TOP_50:    {TOP50_PATH}")
    print(f"{'=' * 60}\n")

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mass Strategy Scanner")
    parser.add_argument("--test", action="store_true", help="Test mode: 100 chromosomes")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--batch", type=int, default=BATCH_SIZE)
    parser.add_argument("--target", type=int, default=TARGET_PASS)
    parser.add_argument("--max", type=int, default=MAX_TOTAL)
    parser.add_argument("--scan-id", type=str, default=None)
    args = parser.parse_args()

    # macOS/Windows 需要這個才能 multiprocessing
    # Linux 使用 fork（預設），可共享父行程記憶體（copy-on-write），大幅節省記憶體
    run_scan(
        scan_id=args.scan_id,
        workers=args.workers,
        batch_size=args.batch,
        target_pass=args.target,
        max_total=args.max,
        test_mode=args.test,
    )
