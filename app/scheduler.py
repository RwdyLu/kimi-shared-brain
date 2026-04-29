"""
Monitoring Scheduler Module
監測排程器模組

Phase 2: Paper Trading Enabled / 模擬交易已啟用
- Confirmed signals trigger paper trades / 確認訊號觸發模擬交易
- No real exchange orders / 無真實交易所訂單

Author: kimiclaw_bot
Version: 1.2.0
Date: 2026-04-27
"""

import os
import time
import signal
import atexit
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import json

# Import dynamic path resolver / 匯入動態路徑解析器
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.paths import PROJECT_ROOT, LOGS_DIR, STATE_DIR

# Import monitoring system / 匯入監測系統
from app.monitor_runner import MonitorRunner
from app.trade_executor import TradeExecutor
from notifications.channels import (
    create_console_channel,
    create_discord_channel,
    create_multi_channel,
    ChannelConfig,
    ChannelType,
)


class SchedulerMode(Enum):
    """Scheduler operation modes / 排程器運作模式"""

    ONCE = "once"  # Run once and exit / 執行一次後退出
    INTERVAL = "interval"  # Run at fixed intervals / 固定間隔執行
    CRON = "cron"  # Cron-like schedule / 類 Cron 排程


@dataclass
class SchedulerConfig:
    """
    Scheduler configuration / 排程器配置

    Attributes:
        mode: Operation mode / 運作模式
        interval_minutes: Interval between runs (for INTERVAL mode) / 執行間隔（分鐘）
        max_runs: Maximum number of runs (None = infinite) / 最大執行次數
        prevent_overlap: Whether to prevent overlapping executions / 是否防止重疊執行
        log_file: Path to scheduler log file / 排程器日誌檔案路徑
        enable_file_logging: Whether to log to file / 是否啟用檔案日誌
    """

    mode: SchedulerMode = SchedulerMode.ONCE
    interval_minutes: int = None  # Will load from config if None
    max_runs: Optional[int] = None
    prevent_overlap: bool = True
    log_file: str = None  # Will load from config if None
    enable_file_logging: bool = None  # Will load from config if None

    def __post_init__(self):
        """Load defaults from config if not provided"""
        try:
            from config.loader import get_monitoring_params

            params = get_monitoring_params()
            monitoring = params.get("monitoring", {})

            if self.interval_minutes is None:
                self.interval_minutes = monitoring.get("check_interval_minutes", 5)
            if self.log_file is None:
                self.log_file = str(LOGS_DIR / "scheduler.log")
            if self.enable_file_logging is None:
                self.enable_file_logging = monitoring.get("enable_file_logging", True)
        except Exception:
            # Fallback defaults
            if self.interval_minutes is None:
                self.interval_minutes = 5
            if self.log_file is None:
                self.log_file = str(LOGS_DIR / "scheduler.log")
            if self.enable_file_logging is None:
                self.enable_file_logging = True


@dataclass
class RunRecord:
    """Record of a scheduled run / 排程執行記錄"""

    run_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    success: bool = False
    signals_generated: int = 0
    error: Optional[str] = None


class SchedulerLock:
    """
    File-based lock to prevent overlapping executions
    基於檔案的鎖，防止重疊執行
    """

    def __init__(self, lock_file: str = None):
        self.lock_file = lock_file or str(STATE_DIR / ".scheduler.lock")
        self._locked = False
        self._pid = os.getpid()

    def acquire(self) -> bool:
        """
        Try to acquire lock / 嘗試取得鎖

        Returns:
            True if lock acquired, False otherwise / 成功取得鎖返回 True
        """
        try:
            # Check if lock file exists / 檢查鎖檔案是否存在
            if os.path.exists(self.lock_file):
                # Read PID from lock file / 從鎖檔案讀取 PID
                with open(self.lock_file, "r") as f:
                    try:
                        old_pid = int(f.read().strip())
                        # Check if process is still running / 檢查程序是否仍在執行
                        try:
                            os.kill(old_pid, 0)
                            # Process exists, lock is held / 程序存在，鎖被持有
                            return False
                        except OSError:
                            # Process doesn't exist, stale lock / 程序不存在，過期鎖
                            pass
                    except ValueError:
                        # Invalid lock file / 無效鎖檔案
                        pass

            # Create lock file with our PID / 建立鎖檔案
            os.makedirs(os.path.dirname(self.lock_file), exist_ok=True)
            with open(self.lock_file, "w") as f:
                f.write(str(self._pid))

            self._locked = True
            return True

        except Exception as e:
            print(f"Lock acquisition error / 鎖取得錯誤: {e}")
            return False

    def release(self) -> None:
        """Release lock / 釋放鎖"""
        if self._locked and os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    pid = f.read().strip()
                    if pid == str(self._pid):
                        os.remove(self.lock_file)
            except Exception:
                pass
        self._locked = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class MonitoringScheduler:
    """
    Monitoring system scheduler / 監測系統排程器

    Provides scheduled execution of the monitoring system.
    提供監測系統的定時執行功能。

    ⚠️  Single-run or interval execution (not a daemon)
    ⚠️  Alert-only (no auto-trading)
    """

    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        runner: Optional[MonitorRunner] = None,
        notification_channel: Optional[Any] = None,
        trade_executor: Optional[TradeExecutor] = None,
    ):
        """
        Initialize scheduler / 初始化排程器

        Args:
            config: Scheduler configuration / 排程器配置
            runner: Monitor runner instance / 監測執行器實例
            notification_channel: Channel for sending alerts / 發送提醒的渠道
        """
        self.config = config or SchedulerConfig()
        self.runner = runner or MonitorRunner()
        self.channel = notification_channel or create_console_channel()
        self.trade_executor = trade_executor

        self._run_count = 0
        self._running = False
        self._stop_requested = False
        self._run_records: List[RunRecord] = []
        self._lock = SchedulerLock()
        self._pid_file = str(STATE_DIR / ".monitor.pid")

        # Register cleanup on exit / 註冊退出時清理
        atexit.register(self._cleanup)

    def _cleanup(self) -> None:
        """Cleanup resources / 清理資源"""
        self._lock.release()
        self._remove_pid_file()

    def _write_pid_file(self) -> None:
        """Write PID file / 寫入 PID 檔案"""
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with open(self._pid_file, "w") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    def _remove_pid_file(self) -> None:
        """Remove PID file / 移除 PID 檔案"""
        try:
            if os.path.exists(self._pid_file):
                os.remove(self._pid_file)
        except Exception:
            pass

    def _log(self, message: str) -> None:
        """Log message to console and optionally file / 記錄訊息到 console 和檔案"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        print(log_line)

        if self.config.enable_file_logging:
            try:
                os.makedirs(os.path.dirname(self.config.log_file), exist_ok=True)
                with open(self.config.log_file, "a") as f:
                    f.write(log_line + "\n")
            except Exception:
                pass

    def _send_notification(self, title: str, message: str) -> None:
        """Send notification via configured channel / 透過配置渠道發送通知"""
        try:
            full_message = f"{title}\n{message}"
            self.channel.send(full_message)
        except Exception as e:
            self._log(f"Notification error / 通知錯誤: {e}")

    def _save_prices_to_state(self, results) -> None:
        """
        Save current prices to state file / 儲存當前價格到狀態檔案

        This allows the UI to display live prices / 這讓 UI 可以顯示即時價格
        """
        try:
            prices_data = {"timestamp": datetime.now().isoformat(), "prices": {}}

            for result in results:
                if result.success and result.current_price:
                    prices_data["prices"][result.symbol] = {
                        "price": result.current_price,
                        "timestamp": datetime.now().isoformat(),
                    }

            # Write to state file / 寫入狀態檔案
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            prices_file = STATE_DIR / "prices.json"
            with open(prices_file, "w") as f:
                json.dump(prices_data, f, indent=2)

            self._log(f"  Prices saved: {list(prices_data['prices'].keys())}")

        except Exception as e:
            self._log(f"  Price save error: {e}")

    def _update_live_ranking(self, results):
        """Update live strategy ranking after each run / 每次執行後更新即時策略排名"""
        try:
            import json
            from pathlib import Path

            ranking = {"last_updated": datetime.now().isoformat(), "symbols": {}}
            all_strategy_names = [
                "ma_cross_trend", "ma_cross_trend_short",
                "contrarian_watch_overheated", "contrarian_watch_oversold",
                "hilbert_cycle", "stochastic_breakout", "rsi_trend",
                "bb_mean_reversion", "ema_cross_fast", "rsi_mid_bounce",
                "volume_spike", "price_channel_break", "momentum_divergence"
            ]

            # Process symbols that were actually monitored
            monitored_symbols = set()
            for result in results:
                if not result.success:
                    continue
                symbol = result.symbol
                monitored_symbols.add(symbol)
                
                symbol_data = {"price": getattr(result, 'current_price', 0), "strategies": []}
                confirmed = getattr(result, 'confirmed_signals', []) or []
                watch_only = getattr(result, 'watch_only_signals', []) or []
                scores = {}

                for sig in confirmed:
                    meta = getattr(sig, 'metadata', {})
                    name = meta.get('strategy_name', 'Unknown') if meta else 'Unknown'
                    # Match by strategy_id if available, otherwise use strategy_name
                    strategy_id = meta.get('strategy_id', name) if meta else name
                    # Normalize: if strategy_name is a display name (e.g., "MA Cross Trend"), 
                    # try to find the matching ID from all_strategy_names
                    if name not in all_strategy_names:
                        # Try to match by replacing spaces with underscores and lowercasing
                        normalized = name.lower().replace(" ", "_").replace("-", "_")
                        if normalized in all_strategy_names:
                            name = normalized
                        else:
                            # Fallback: use strategy_id if available
                            name = strategy_id
                    
                    scores[name] = {
                        "name": name,
                        "status": "Confirmed",
                        "score": 1.0,
                        "conditions_passed": sig.metadata.get('conditions_passed', 0) if hasattr(sig, 'metadata') and sig.metadata else 0,
                        "total_conditions": sig.metadata.get('conditions_total', 0) if hasattr(sig, 'metadata') and sig.metadata else 0
                    }

                for sig in watch_only:
                    meta = getattr(sig, 'metadata', {})
                    name = meta.get('strategy_name', 'Unknown') if hasattr(sig, 'metadata') and sig.metadata else 'Unknown'
                    strategy_id = meta.get('strategy_id', name) if meta else name
                    if name not in all_strategy_names:
                        normalized = name.lower().replace(" ", "_").replace("-", "_")
                        if normalized in all_strategy_names:
                            name = normalized
                        else:
                            name = strategy_id
                    
                    if name not in scores:
                        scores[name] = {
                            "name": name,
                            "status": "Watch",
                            "score": 0.5,
                            "conditions_passed": sig.metadata.get('conditions_passed', 0) if hasattr(sig, 'metadata') and sig.metadata else 0,
                            "total_conditions": sig.metadata.get('conditions_total', 0) if hasattr(sig, 'metadata') and sig.metadata else 0
                        }

                for name in all_strategy_names:
                    if name not in scores:
                        scores[name] = {
                            "name": name,
                            "status": "Idle",
                            "score": 0.0,
                            "conditions_passed": 0,
                            "total_conditions": 0
                        }

                symbol_data["strategies"] = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
                ranking["symbols"][symbol] = symbol_data

            # Ensure all 10 symbols are present, even if not monitored this run
            all_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                          "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
            
            for symbol in all_symbols:
                if symbol not in ranking["symbols"]:
                    # Read previous data if available, otherwise create Idle entry
                    prev_data = self._load_previous_ranking_for_symbol(symbol)
                    if prev_data:
                        ranking["symbols"][symbol] = prev_data
                    else:
                        ranking["symbols"][symbol] = {
                            "price": 0,
                            "strategies": [
                                {
                                    "name": name,
                                    "status": "Idle",
                                    "score": 0.0,
                                    "conditions_passed": 0,
                                    "total_conditions": 0
                                }
                                for name in all_strategy_names
                            ]
                        }

            STATE_DIR.mkdir(parents=True, exist_ok=True)
            ranking_file = STATE_DIR / "live_strategy_ranking.json"
            with open(ranking_file, 'w') as f:
                json.dump(ranking, f, indent=2)

            self._log(f"  Live ranking updated: {len(monitored_symbols)} monitored, all 10 symbols present")

        except Exception as e:
            self._log(f"  Live ranking update error: {e}")

    def _load_previous_ranking_for_symbol(self, symbol: str) -> dict:
        """Load previous ranking data for a symbol if available / 載入該幣種之前的排名資料"""
        try:
            ranking_file = STATE_DIR / "live_strategy_ranking.json"
            if not ranking_file.exists():
                return None
            with open(ranking_file, 'r') as f:
                data = json.load(f)
            return data.get("symbols", {}).get(symbol)
        except Exception:
            return None

    def _run_monitor(self) -> RunRecord:
        """
        Execute one monitoring run / 執行一次監測

        Returns:
            RunRecord with execution details / 包含執行詳情的 RunRecord
        """
        self._run_count += 1
        run_id = self._run_count
        start_time = datetime.now()

        record = RunRecord(run_id=run_id, start_time=start_time)

        self._log(f"=" * 60)
        self._log(f"Run #{run_id} started at {start_time}")
        self._log(f"=" * 60)

        try:
            # Execute monitoring / 執行監測
            results, summary = self.runner.run_monitor_once()

            # Save current prices to state file / 儲存當前價格到狀態檔案
            self._save_prices_to_state(results)

            # Record results / 記錄結果
            record.end_time = datetime.now()
            record.success = True
            record.signals_generated = summary.total_signals

            # Execute paper trades for confirmed signals / 對確認訊號執行模擬交易
            trades_executed = 0
            if self.trade_executor and summary.confirmed_count > 0:
                self._log("  [Phase 2] Executing paper trades...")
                
                # Collect confirmed signals and current prices
                confirmed_signals = []
                current_prices = {}
                for result in results:
                    if result.success and result.current_price:
                        current_prices[result.symbol] = result.current_price
                        if result.confirmed_signals:
                            confirmed_signals.extend(result.confirmed_signals)
                
                # Execute trades
                trade_results = self.trade_executor.execute_signals(
                    confirmed_signals, current_prices
                )
                trades_executed = len([t for t in trade_results if t.status == "executed"])
                
                for tr in trade_results:
                    status_icon = "✅" if tr.status == "executed" else "⏭️"
                    self._log(f"    {status_icon} {tr.symbol}: {tr.side.upper()} {tr.status}")
                    if tr.trade_id:
                        self._log(f"       qty={tr.quantity:.6f} @ ${tr.entry_price:,.2f}")
                
                # Log paper performance
                perf = self.trade_executor.get_paper_performance()
                if perf:
                    self._log(f"  Paper Balance: ${perf.get('current_balance', 0):,.2f}")
                    self._log(f"  Open positions: {perf.get('open_positions', 0)}")
                # Save paper trading state after each run with trades
                self.trade_executor.save_state()

            # Update live strategy ranking / 更新即時策略排名
            self._update_live_ranking(results)

            duration = (record.end_time - start_time).total_seconds()

            self._log(f"Run #{run_id} completed")
            self._log(f"  Duration: {duration:.1f}s")
            self._log(f"  Symbols: {summary.successful_symbols}/{summary.total_symbols}")
            self._log(
                f"  Signals: {summary.total_signals} (Confirmed: {summary.confirmed_count}, Watch: {summary.watch_only_count})"
            )

            # Send notification if signals generated / 若有訊號則發送通知
            if summary.total_signals > 0:
                title = f"🚨 Monitoring Alert - {summary.total_signals} signals detected"
                message = f"Run #{run_id}: {summary.confirmed_count} confirmed, {summary.watch_only_count} watch-only"
                if trades_executed > 0:
                    message += f", {trades_executed} paper trades executed"
                self._send_notification(title, message)

        except Exception as e:
            record.end_time = datetime.now()
            record.success = False
            record.error = str(e)
            self._log(f"Run #{run_id} failed: {e}")
            self._send_notification("❌ Monitoring Error", f"Run #{run_id} failed: {e}")

        self._run_records.append(record)
        return record

    def run_once(self) -> RunRecord:
        """
        Run monitoring once / 執行一次監測

        Returns:
            RunRecord with execution details / 包含執行詳情的 RunRecord
        """
        # Check overlap prevention / 檢查重疊防止
        if self.config.prevent_overlap:
            if not self._lock.acquire():
                self._log("Another instance is running. Skipping this run.")
                return RunRecord(
                    run_id=0, start_time=datetime.now(), success=False, error="Lock held by another instance"
                )

        try:
            return self._run_monitor()
        finally:
            if self.config.prevent_overlap:
                self._lock.release()

    def run_interval(self, interval_minutes: Optional[int] = None) -> None:
        """
        Run monitoring at fixed intervals / 固定間隔執行監測

        Args:
            interval_minutes: Interval between runs (overrides config) / 執行間隔（覆寫配置）
        """
        interval = interval_minutes or self.config.interval_minutes
        self._running = True
        self._stop_requested = False

        # Write PID file / 寫入 PID 檔案
        self._write_pid_file()

        self._log(f"Starting interval scheduler / 啟動間隔排程器")
        self._log(f"Interval: {interval} minutes / 間隔：{interval} 分鐘")
        self._log(f"Press Ctrl+C to stop / 按 Ctrl+C 停止")
        self._log(f"{'='*60}")

        try:
            while self._running and not self._stop_requested:
                # Check max runs / 檢查最大執行次數
                if self.config.max_runs and self._run_count >= self.config.max_runs:
                    self._log(f"Max runs ({self.config.max_runs}) reached. Stopping.")
                    break

                # Run monitoring / 執行監測
                self.run_once()

                # Check if should continue / 檢查是否應繼續
                if self._stop_requested:
                    break

                # Wait for next run / 等待下次執行
                next_run = datetime.now() + timedelta(minutes=interval)
                self._log(f"Next run at {next_run.strftime('%H:%M:%S')} (in {interval} min)")

                # Sleep with interrupt check / 帶中斷檢查的睡眠
                for _ in range(interval * 60):
                    if self._stop_requested:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            self._log("\nScheduler stopped by user / 排程器被使用者停止")
        finally:
            self._running = False
            self._cleanup()

    def stop(self) -> None:
        """Request scheduler to stop / 請求排程器停止"""
        self._stop_requested = True
        self._log("Stop requested. Finishing current run...")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get scheduler statistics / 取得排程器統計

        Returns:
            Dictionary with statistics / 包含統計的字典
        """
        if not self._run_records:
            return {"total_runs": 0, "successful_runs": 0, "failed_runs": 0, "total_signals": 0}

        successful = sum(1 for r in self._run_records if r.success)
        failed = sum(1 for r in self._run_records if not r.success)
        total_signals = sum(r.signals_generated for r in self._run_records)

        return {
            "total_runs": len(self._run_records),
            "successful_runs": successful,
            "failed_runs": failed,
            "total_signals": total_signals,
            "first_run": self._run_records[0].start_time.isoformat(),
            "last_run": self._run_records[-1].start_time.isoformat(),
        }


# Convenience functions / 便利函數


def run_once_with_notification(webhook_url: Optional[str] = None) -> RunRecord:
    """
    Run monitoring once with optional Discord notification
    執行一次監測，可選 Discord 通知

    Args:
        webhook_url: Discord webhook URL (optional) / Discord webhook URL（可選）

    Returns:
        RunRecord with execution details / 包含執行詳情的 RunRecord
    """
    # Create notification channel / 建立通知渠道
    if webhook_url:
        channel = create_discord_channel(webhook_url, fallback=True)
    else:
        channel = create_console_channel()

    # Create scheduler / 建立排程器
    config = SchedulerConfig(mode=SchedulerMode.ONCE)
    scheduler = MonitoringScheduler(config=config, notification_channel=channel)

    return scheduler.run_once()


def run_every_5_minutes(webhook_url: Optional[str] = None, max_runs: Optional[int] = None) -> None:
    """
    Run monitoring every 5 minutes / 每 5 分鐘執行監測

    Args:
        webhook_url: Discord webhook URL (optional) / Discord webhook URL（可選）
        max_runs: Maximum number of runs (None = infinite) / 最大執行次數
    """
    if webhook_url:
        channel = create_discord_channel(webhook_url, fallback=True)
    else:
        channel = create_console_channel()

    config = SchedulerConfig(mode=SchedulerMode.INTERVAL, interval_minutes=5, max_runs=max_runs)
    scheduler = MonitoringScheduler(config=config, notification_channel=channel)
    scheduler.run_interval()


def run_every_minute(webhook_url: Optional[str] = None, max_runs: Optional[int] = None) -> None:
    """
    Run monitoring every minute / 每分鐘執行監測

    ⚠️  Warning: Higher API usage / 警告：較高的 API 使用量

    Args:
        webhook_url: Discord webhook URL (optional) / Discord webhook URL（可選）
        max_runs: Maximum number of runs (None = infinite) / 最大執行次數
    """
    if webhook_url:
        channel = create_discord_channel(webhook_url, fallback=True)
    else:
        channel = create_console_channel()

    config = SchedulerConfig(mode=SchedulerMode.INTERVAL, interval_minutes=1, max_runs=max_runs)
    scheduler = MonitoringScheduler(config=config, notification_channel=channel)
    scheduler.run_interval()


# Example usage / 使用範例
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Monitoring Scheduler / 監測排程器")
    print("=" * 60)
    print()
    print("Usage examples / 使用範例:")
    print()
    print("1. Run once / 執行一次:")
    print('   python3 -c "from app.scheduler import run_once_with_notification; run_once_with_notification()"')
    print()
    print("2. Run every 5 minutes / 每 5 分鐘執行:")
    print('   python3 -c "from app.scheduler import run_every_5_minutes; run_every_5_minutes()"')
    print()
    print("3. Run with Discord notification / 使用 Discord 通知執行:")
    print(
        "   python3 -c \"from app.scheduler import run_once_with_notification; run_once_with_notification('YOUR_WEBHOOK_URL')\""
    )
    print()
    print("⚠️  This is a PAPER TRADING system / 這是模擬交易系統")
    print("⚠️  No real exchange orders / 無真實交易所訂單")
    print("=" * 60)
