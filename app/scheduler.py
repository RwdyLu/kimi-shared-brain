"""
Monitoring Scheduler Module
監測排程器模組

BTC/ETH Monitoring System - Scheduler Layer
BTC/ETH 監測系統 - 排程層

This module provides scheduling capabilities for the monitoring system.
本模組提供監測系統的排程功能。

⚠️  ALERT-ONLY SYSTEM / 僅提醒系統
⚠️  No auto-trading / 無自動交易

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-06
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

# Import monitoring system / 匯入監測系統
from app.monitor_runner import MonitorRunner
from notifications.channels import (
    create_console_channel, create_discord_channel, create_multi_channel,
    ChannelConfig, ChannelType
)


class SchedulerMode(Enum):
    """Scheduler operation modes / 排程器運作模式"""
    ONCE = "once"           # Run once and exit / 執行一次後退出
    INTERVAL = "interval"   # Run at fixed intervals / 固定間隔執行
    CRON = "cron"           # Cron-like schedule / 類 Cron 排程


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
                self.log_file = monitoring.get("log_file", "/tmp/kimi-shared-brain/logs/scheduler.log")
            if self.enable_file_logging is None:
                self.enable_file_logging = monitoring.get("enable_file_logging", True)
        except Exception:
            # Fallback defaults
            if self.interval_minutes is None:
                self.interval_minutes = 5
            if self.log_file is None:
                self.log_file = "/tmp/kimi-shared-brain/logs/scheduler.log"
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
    
    def __init__(self, lock_file: str = "/tmp/kimi-shared-brain/.scheduler.lock"):
        self.lock_file = lock_file
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
                with open(self.lock_file, 'r') as f:
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
            with open(self.lock_file, 'w') as f:
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
                with open(self.lock_file, 'r') as f:
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
        notification_channel: Optional[Any] = None
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
        
        self._run_count = 0
        self._running = False
        self._stop_requested = False
        self._run_records: List[RunRecord] = []
        self._lock = SchedulerLock()
        
        # Register cleanup on exit / 註冊退出時清理
        atexit.register(self._cleanup)
    
    def _cleanup(self) -> None:
        """Cleanup resources / 清理資源"""
        self._lock.release()
    
    def _log(self, message: str) -> None:
        """Log message to console and optionally file / 記錄訊息到 console 和檔案"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        
        if self.config.enable_file_logging:
            try:
                os.makedirs(os.path.dirname(self.config.log_file), exist_ok=True)
                with open(self.config.log_file, 'a') as f:
                    f.write(log_line + '\n')
            except Exception:
                pass
    
    def _send_notification(self, title: str, message: str) -> None:
        """Send notification via configured channel / 透過配置渠道發送通知"""
        try:
            full_message = f"{title}\n{message}"
            self.channel.send(full_message)
        except Exception as e:
            self._log(f"Notification error / 通知錯誤: {e}")
    
    def _run_monitor(self) -> RunRecord:
        """
        Execute one monitoring run / 執行一次監測
        
        Returns:
            RunRecord with execution details / 包含執行詳情的 RunRecord
        """
        self._run_count += 1
        run_id = self._run_count
        start_time = datetime.now()
        
        record = RunRecord(
            run_id=run_id,
            start_time=start_time
        )
        
        self._log(f"="*60)
        self._log(f"Run #{run_id} started at {start_time}")
        self._log(f"="*60)
        
        try:
            # Execute monitoring / 執行監測
            results, summary = self.runner.run_monitor_once()
            
            # Record results / 記錄結果
            record.end_time = datetime.now()
            record.success = True
            record.signals_generated = summary.total_signals
            
            duration = (record.end_time - start_time).total_seconds()
            
            self._log(f"Run #{run_id} completed")
            self._log(f"  Duration: {duration:.1f}s")
            self._log(f"  Symbols: {summary.successful_symbols}/{summary.total_symbols}")
            self._log(f"  Signals: {summary.total_signals} (Confirmed: {summary.confirmed_count}, Watch: {summary.watch_only_count})")
            
            # Send notification if signals generated / 若有訊號則發送通知
            if summary.total_signals > 0:
                title = f"🚨 Monitoring Alert - {summary.total_signals} signals detected"
                message = f"Run #{run_id}: {summary.confirmed_count} confirmed, {summary.watch_only_count} watch-only"
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
                    run_id=0,
                    start_time=datetime.now(),
                    success=False,
                    error="Lock held by another instance"
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
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "total_signals": 0
            }
        
        successful = sum(1 for r in self._run_records if r.success)
        failed = sum(1 for r in self._run_records if not r.success)
        total_signals = sum(r.signals_generated for r in self._run_records)
        
        return {
            "total_runs": len(self._run_records),
            "successful_runs": successful,
            "failed_runs": failed,
            "total_signals": total_signals,
            "first_run": self._run_records[0].start_time.isoformat(),
            "last_run": self._run_records[-1].start_time.isoformat()
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
    
    config = SchedulerConfig(
        mode=SchedulerMode.INTERVAL,
        interval_minutes=5,
        max_runs=max_runs
    )
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
    
    config = SchedulerConfig(
        mode=SchedulerMode.INTERVAL,
        interval_minutes=1,
        max_runs=max_runs
    )
    scheduler = MonitoringScheduler(config=config, notification_channel=channel)
    scheduler.run_interval()


# Example usage / 使用範例
if __name__ == "__main__":
    import sys
    
    print("="*60)
    print("Monitoring Scheduler / 監測排程器")
    print("="*60)
    print()
    print("Usage examples / 使用範例:")
    print()
    print("1. Run once / 執行一次:")
    print("   python3 -c \"from app.scheduler import run_once_with_notification; run_once_with_notification()\"")
    print()
    print("2. Run every 5 minutes / 每 5 分鐘執行:")
    print("   python3 -c \"from app.scheduler import run_every_5_minutes; run_every_5_minutes()\"")
    print()
    print("3. Run with Discord notification / 使用 Discord 通知執行:")
    print("   python3 -c \"from app.scheduler import run_once_with_notification; run_once_with_notification('YOUR_WEBHOOK_URL')\"")
    print()
    print("⚠️  This is an ALERT-ONLY system / 這是僅提醒系統")
    print("⚠️  No automatic trading / 無自動交易")
    print("="*60)
