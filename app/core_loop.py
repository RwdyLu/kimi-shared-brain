#!/usr/bin/env python3
"""
核心閉環：基因演化 → 回測過濾 → Paper Trade 驗證 → 晉級/淘汰

循環邏輯：
1. 運行基因演化，取得通過手續費過濾的候選策略
2. 將候選策略加入 Paper Trade 運行 N 天
3. 每天評估 paper trade 結果：
   - 淨獲利 > 手續費門檻 → 晉升 Champion
   - 虧損超過閾值 → 淘汰（Retired）
   - 其他 → 繼續觀察
4. 有 Champion 後，繼續跑基因演化尋找更好的策略
"""

import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from app.genetic_engine.evolution import EvolutionEngine, DEFAULT_CONFIG
from app.genetic_engine.archive import StrategyArchive, ArchiveRecord
from app.genetic_engine.backtest_engine import BacktestEngine
from app.paper_trading import PaperTrading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/core_loop.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── 設定 ──────────────────────────────────────────────────────────────────────
PAPER_TRADE_DAYS = 7          # paper trade 觀察天數
PAPER_MIN_NET_PNL = 0.005     # paper trade 淨獲利門檻（超過此才晉升）
PAPER_MAX_LOSS = -0.03        # paper trade 最大虧損（超過此立即淘汰）
EVOLUTION_INTERVAL_HOURS = 6  # 每 N 小時重新跑一次基因演化
FEE_RATE = 0.001              # Binance 手續費 0.1%


class CoreLoop:
    def __init__(self, config: Optional[dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.archive = StrategyArchive()
        self.paper = PaperTrading()
        self.engine = BacktestEngine(fee_rate=FEE_RATE)
        Path("logs").mkdir(exist_ok=True)

    # ── Phase 1：基因演化 ──────────────────────────────────────────────────
    def run_evolution(self) -> List[ArchiveRecord]:
        """跑一輪基因演化，回傳通過過濾的候選策略列表"""
        log.info("=== 開始基因演化 ===")
        evo = EvolutionEngine(config=self.config)
        evo.run()

        candidates = []
        for chrom in evo.population:
            if not getattr(chrom, "passes_filter", False):
                continue
            metrics = getattr(chrom, "_agg_metrics", None)
            if metrics is None:
                continue

            record = ArchiveRecord(
                chromosome_id=chrom.id,
                status="challenger",
                epoch_id=f"loop_{datetime.now().strftime('%Y%m%d_%H%M')}",
                generation=getattr(evo, "current_generation", 0),
                fitness_score=getattr(chrom, "_fitness", 0.0),
                fitness_details={
                    "pnl": metrics.total_pnl,
                    "win_rate": metrics.win_rate,
                    "trades": metrics.total_trades,
                    "drawdown": metrics.max_drawdown,
                    "sharpe": metrics.sharpe_ratio,
                },
                chromosome_data=chrom.to_dict(),
            )
            self.archive.add_challenger(record)
            candidates.append(record)
            log.info(
                f"  候選策略 {chrom.id[:8]}: PnL={metrics.total_pnl:.2%} "
                f"WR={metrics.win_rate:.1%} DD={metrics.max_drawdown:.2%}"
            )

        log.info(f"=== 演化完成，共 {len(candidates)} 個候選策略 ===")
        return candidates

    # ── Phase 2：Paper Trade 驗證 ──────────────────────────────────────────
    def register_for_paper_trade(self, record: ArchiveRecord):
        """將候選策略加入 paper trade"""
        strategy_id = record.chromosome_id
        if strategy_id not in self.paper._state.get("strategies", {}):
            log.info(f"  新增 Paper Trade 策略: {strategy_id[:8]}")
            # PaperTrading 需要 strategy_id 存在才能操作，初始化帳戶
            self.paper._state.setdefault("strategies", {})[strategy_id] = {
                "balance": 1000.0,
                "positions": {},
                "trades": [],
                "daily_settlement": [],
                "start_date": datetime.now().isoformat(),
                "observe_until": (datetime.now() + timedelta(days=PAPER_TRADE_DAYS)).isoformat(),
            }
            self.paper._save_state()

    # ── Phase 3：評估 Paper Trade 結果 ────────────────────────────────────
    def evaluate_paper_trades(self):
        """檢查每個 challenger 的 paper trade 表現，決定晉升或淘汰"""
        log.info("=== 評估 Paper Trade 結果 ===")
        strategies = self.paper._state.get("strategies", {})

        for strategy_id, account in strategies.items():
            observe_until = account.get("observe_until")
            if not observe_until:
                continue

            deadline = datetime.fromisoformat(observe_until)
            if datetime.now() < deadline:
                remaining = (deadline - datetime.now()).days
                log.info(f"  {strategy_id[:8]}: 還有 {remaining} 天觀察期")
                continue

            # 計算淨獲利（已扣手續費）
            trades = account.get("trades", [])
            if not trades:
                log.info(f"  {strategy_id[:8]}: 無交易紀錄，淘汰")
                self.archive.retire_challenger(strategy_id, reason="no_trades")
                continue

            initial = 1000.0
            final = account.get("balance", initial)
            net_pnl = (final - initial) / initial

            total_fees = sum(
                abs(t.get("pnl_pct", 0)) * FEE_RATE * 2
                for t in trades
            )

            log.info(
                f"  {strategy_id[:8]}: 淨獲利={net_pnl:.2%} "
                f"手續費={total_fees:.2%} 交易={len(trades)}"
            )

            if net_pnl >= PAPER_MIN_NET_PNL:
                log.info(f"  ✅ 晉升 Champion: {strategy_id[:8]}")
                self.archive.promote_challenger(strategy_id)
            elif net_pnl <= PAPER_MAX_LOSS:
                log.info(f"  ❌ 淘汰（虧損過大）: {strategy_id[:8]}")
                self.archive.retire_challenger(strategy_id, reason="paper_loss")
            else:
                log.info(f"  ⚠️  延長觀察 7 天: {strategy_id[:8]}")
                account["observe_until"] = (
                    datetime.now() + timedelta(days=PAPER_TRADE_DAYS)
                ).isoformat()
                self.paper._save_state()

    # ── 主循環 ────────────────────────────────────────────────────────────
    def run_forever(self):
        """持續運行：演化 → paper trade → 評估 → 重複"""
        log.info("🚀 核心閉環啟動")
        log.info(
            f"  設定: 演化間隔={EVOLUTION_INTERVAL_HOURS}h | "
            f"Paper Trade={PAPER_TRADE_DAYS}天 | "
            f"晉升門檻={PAPER_MIN_NET_PNL:.1%}"
        )

        while True:
            try:
                # 1. 跑基因演化
                candidates = self.run_evolution()

                # 2. 將候選策略加入 paper trade
                for record in candidates:
                    self.register_for_paper_trade(record)

                # 3. 評估現有 paper trade 結果
                self.evaluate_paper_trades()

                # 4. 顯示當前狀態
                self._print_status()

                # 5. 等待下一輪
                wait_seconds = EVOLUTION_INTERVAL_HOURS * 3600
                log.info(f"⏳ 等待 {EVOLUTION_INTERVAL_HOURS} 小時後重新演化...")
                time.sleep(wait_seconds)

            except KeyboardInterrupt:
                log.info("使用者中斷，停止核心閉環")
                break
            except Exception as e:
                log.error(f"錯誤: {e}", exc_info=True)
                log.info("60 秒後重試...")
                time.sleep(60)

    def _print_status(self):
        stats = self.archive.get_stats()
        champions = stats.get("champions", 0)
        challengers = stats.get("challengers", 0)
        retired = stats.get("retired", 0)
        log.info(
            f"📊 狀態: Champions={champions} | Challengers={challengers} | Retired={retired}"
        )


def run_one_cycle(config: Optional[dict] = None):
    """跑一輪完整閉環（用於測試或手動觸發）"""
    loop = CoreLoop(config=config)
    candidates = loop.run_evolution()
    for record in candidates:
        loop.register_for_paper_trade(record)
    loop.evaluate_paper_trades()
    loop._print_status()
    return candidates


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        run_one_cycle()
    else:
        CoreLoop().run_forever()
