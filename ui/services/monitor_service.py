"""
Monitor Service
監測服務

BTC/ETH Monitoring System - UI Service Layer
BTC/ETH 監測系統 - UI 服務層

This module provides services for querying monitoring system status.
本模組提供查詢監測系統狀態的服務。

Version: 1.1.0
Date: 2026-04-10
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

# Import dynamic path resolver / 匯入動態路徑解析器
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.paths import PROJECT_ROOT, LOGS_DIR, STATE_DIR


class MonitorService:
    """
    Service for querying monitoring system status
    查詢監測系統狀態的服務
    """
    
    def __init__(self, base_path: str = None):
        """
        Initialize monitor service
        
        Args:
            base_path: Base path to monitoring system (default: auto-detected)
        """
        self.base_path = Path(base_path) if base_path else PROJECT_ROOT
        self.log_file = self.base_path / "logs" / "scheduler.log"
        self.pid_file = self.base_path / ".monitor.pid"
        self.alerts_dir = self.base_path / "alerts"
    
    def _read_log_lines(self) -> List[str]:
        """
        Read log file lines with proper file handling
        讀取日誌檔案行數，確保檔案正確處理
        """
        try:
            if not self.log_file.exists():
                return []
            
            # Force read from disk, not cache
            # 強制從磁碟讀取，而非快取
            with open(self.log_file, 'r', encoding='utf-8') as f:
                # Seek to end first to ensure fresh read
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()
                f.seek(0)  # Seek back to beginning
                
                if file_size == 0:
                    return []
                
                return f.readlines()
        except Exception as e:
            print(f"Error reading log file: {e}")
            return []
    
    def _is_recent_run_active(self, max_minutes: int = 10) -> bool:
        """
        Check if there's a recent run in the log (within max_minutes)
        檢查日誌中是否有最近的 run（在 max_minutes 分鐘內）
        
        This is a fallback method when PID check fails but scheduler is still running
        這是當 PID 檢查失敗但 scheduler 仍在運行時的備用方法
        
        Args:
            max_minutes: Maximum minutes since last run to consider "active"
            
        Returns:
            True if recent run found
        """
        try:
            lines = self._read_log_lines()
            if not lines:
                return False
            
            # Find the last completed run
            for line in reversed(lines):
                if "Run #" in line and "completed" in line:
                    # Parse timestamp
                    timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                    if timestamp_match:
                        timestamp_str = timestamp_match.group(1)
                        last_run_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        time_diff = datetime.now() - last_run_time
                        
                        # Check if within threshold
                        if time_diff.total_seconds() <= max_minutes * 60:
                            return True
                    break
            
            return False
        except Exception:
            return False
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get scheduler status
        
        Returns:
            Dict with status, pid, uptime info
        """
        status = {
            "running": False,
            "pid": None,
            "uptime": None,
            "status_text": "Stopped / 已停止",
            "status_color": "danger"
        }
        
        try:
            # Primary check: PID file
            if self.pid_file.exists():
                with open(self.pid_file, 'r') as f:
                    pid = f.read().strip()
                    try:
                        pid_int = int(pid)
                        os.kill(pid_int, 0)
                        # PID is valid and process is running
                        status["running"] = True
                        status["pid"] = pid
                        status["status_text"] = "Running / 執行中"
                        status["status_color"] = "success"
                        return status
                    except (OSError, ValueError):
                        # PID file exists but process not running
                        # Fall through to secondary check
                        pass
            
            # Secondary check: Recent log activity
            # This handles the case where PID file has stale PID but scheduler is actually running
            if self._is_recent_run_active(max_minutes=10):
                status["running"] = True
                status["pid"] = "Unknown (from log)"
                status["status_text"] = "Running (active) / 執行中 (活躍)"
                status["status_color"] = "success"
            elif self.pid_file.exists():
                # PID file exists but no recent activity
                status["status_text"] = "Stale PID / 過期 PID"
                status["status_color"] = "warning"
                
        except Exception as e:
            status["error"] = str(e)
        
        return status
    
    def get_last_run_info(self) -> Dict[str, Any]:
        """
        Get information about the last monitoring run
        
        Returns:
            Dict with last run time, result, signals count
        """
        result = {
            "timestamp": None,
            "time_ago": None,
            "run_id": None,
            "signals": 0,
            "confirmed": 0,
            "watch_only": 0,
            "duration": None,
            "result_text": "No data / 無資料"
        }
        
        try:
            lines = self._read_log_lines()
            if not lines:
                return result
            
            # Find the last completed run
            last_run_line = None
            for line in reversed(lines):
                if "Run #" in line and "completed" in line:
                    last_run_line = line
                    break
            
            if not last_run_line:
                return result
            
            # Parse the line
            # Format: [2026-04-07 22:39:15] Run #66 completed
            timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', last_run_line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                result["timestamp"] = timestamp_str
                result["time_ago"] = self._format_time_ago(timestamp)
            
            # Extract run ID
            run_match = re.search(r'Run #(\d+)', last_run_line)
            if run_match:
                result["run_id"] = int(run_match.group(1))
            
            # Find the corresponding run details
            for line in reversed(lines):
                if result["run_id"] and f"Run #{result['run_id']}" in line:
                    # Duration
                    duration_match = re.search(r'Duration: ([\d.]+)s', line)
                    if duration_match:
                        result["duration"] = float(duration_match.group(1))
                    
                    # Signals
                    signals_match = re.search(r'Signals: (\d+) \(Confirmed: (\d+), Watch: (\d+)\)', line)
                    if signals_match:
                        result["signals"] = int(signals_match.group(1))
                        result["confirmed"] = int(signals_match.group(2))
                        result["watch_only"] = int(signals_match.group(3))
            
            # Build result text
            if result["signals"] > 0:
                result["result_text"] = f"{result['signals']} signals ({result['confirmed']} confirmed, {result['watch_only']} watch)"
            else:
                result["result_text"] = "No signals / 無訊號"
                
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def get_recent_runs(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent monitoring runs
        
        Args:
            count: Number of runs to return
            
        Returns:
            List of run info dicts
        """
        runs = []
        
        try:
            lines = self._read_log_lines()
            if not lines:
                return runs
            
            # Find completed runs
            run_info = {}
            for line in reversed(lines):
                timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                if not timestamp_match:
                    continue
                
                timestamp_str = timestamp_match.group(1)
                
                # Check for run completion
                run_match = re.search(r'Run #(\d+) completed', line)
                if run_match:
                    run_id = int(run_match.group(1))
                    if run_id not in run_info:
                        run_info[run_id] = {
                            "run_id": run_id,
                            "timestamp": timestamp_str,
                            "time_ago": self._format_time_ago(
                                datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            ),
                            "signals": 0,
                            "confirmed": 0,
                            "watch_only": 0
                        }
                
                # Extract signal counts - match the run that needs signal info
                signals_match = re.search(r'Signals: (\d+) \(Confirmed: (\d+), Watch: (\d+)\)', line)
                if signals_match and run_info:
                    # Find the most recent run without signal counts
                    for run_id in sorted(run_info.keys(), reverse=True):
                        if run_info[run_id]["signals"] == 0:
                            run_info[run_id]["signals"] = int(signals_match.group(1))
                            run_info[run_id]["confirmed"] = int(signals_match.group(2))
                            run_info[run_id]["watch_only"] = int(signals_match.group(3))
                            break
            
            # Convert to list and sort by run_id descending (most recent first)
            runs = list(run_info.values())
            runs.sort(key=lambda x: x["run_id"], reverse=True)
            return runs[:count]
            
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_today_signals(self) -> Dict[str, Any]:
        """
        Get signal counts for today
        
        Returns:
            Dict with total, confirmed, watch_only counts
        """
        result = {
            "total": 0,
            "confirmed": 0,
            "watch_only": 0,
            "history": []
        }
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            lines = self._read_log_lines()
            
            for line in lines:
                if today in line and "Signals:" in line:
                    signals_match = re.search(r'Signals: (\d+) \(Confirmed: (\d+), Watch: (\d+)\)', line)
                    if signals_match:
                        result["total"] += int(signals_match.group(1))
                        result["confirmed"] += int(signals_match.group(2))
                        result["watch_only"] += int(signals_match.group(3))
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def get_recent_signals(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent signals from log
        
        Args:
            count: Number of signals to return
            
        Returns:
            List of signal info dicts
        """
        signals = []
        
        try:
            # Check for alert files in alerts directory
            if self.alerts_dir.exists():
                alert_files = sorted(self.alerts_dir.glob("*.json"), reverse=True)
                for alert_file in alert_files[:count]:
                    try:
                        with open(alert_file, 'r') as f:
                            alert_data = json.load(f)
                            signals.append(alert_data)
                    except:
                        pass
            
            # If no alert files, parse from log (this is a simplified version)
            if not signals:
                lines = self._read_log_lines()
                # Look for signal-related log entries
                # This would need more sophisticated parsing based on actual log format
                
        except Exception as e:
            return [{"error": str(e)}]
        
        return signals
    
    def get_logs_preview(self, lines_count: int = 20) -> str:
        """
        Get a preview of recent log lines
        
        Args:
            lines_count: Number of lines to return
            
        Returns:
            Log content as string
        """
        try:
            lines = self._read_log_lines()
            
            if not lines:
                return "No log file found or log is empty / 未找到日誌或日誌為空"
            
            return "".join(lines[-lines_count:])
            
        except Exception as e:
            return f"Error reading logs / 讀取日誌錯誤: {e}"
    
    def get_next_run_time(self) -> Optional[str]:
        """
        Get next scheduled run time from log
        
        Returns:
            Formatted time string or None if scheduler is stopped
        """
        try:
            # Check if scheduler is running first
            status = self.get_scheduler_status()
            if not status.get("running", False):
                return None  # Scheduler is stopped, no next run
            
            lines = self._read_log_lines()
            
            for line in reversed(lines):
                match = re.search(r'Next run at ([\d:]+)', line)
                if match:
                    return match.group(1)
            
            return None
            
        except Exception:
            return None
    
    def _format_time_ago(self, timestamp: datetime) -> str:
        """Format time difference as human readable string"""
        now = datetime.now()
        diff = now - timestamp
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return f"{diff.seconds} second{'s' if diff.seconds > 1 else ''} ago"
    
    def get_full_status(self) -> Dict[str, Any]:
        """
        Get complete monitoring status
        
        Returns:
            Dict with all status information including historical vs live distinction
        """
        scheduler_status = self.get_scheduler_status()
        
        return {
            "scheduler": scheduler_status,
            "last_run": self.get_last_run_info(),
            "today_signals": self.get_today_signals(),
            "recent_runs": self.get_recent_runs(5),
            "next_run": self.get_next_run_time() if scheduler_status.get("running") else None,
            "is_live": scheduler_status.get("running", False),
            "timestamp": datetime.now().isoformat(),
            "mode": "LIVE" if scheduler_status.get("running") else "HISTORICAL_ONLY"
        }


# Create a new service instance for each call to avoid caching issues
# 為每次呼叫建立新實例以避免快取問題
def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status"""
    return MonitorService().get_scheduler_status()


def get_last_run_info() -> Dict[str, Any]:
    """Get last run information"""
    return MonitorService().get_last_run_info()


def get_today_signals() -> Dict[str, Any]:
    """Get today's signal counts"""
    return MonitorService().get_today_signals()


def get_recent_runs(count: int = 5) -> List[Dict[str, Any]]:
    """Get recent runs"""
    return MonitorService().get_recent_runs(count)


def get_logs_preview(lines: int = 20) -> str:
    """Get logs preview"""
    return MonitorService().get_logs_preview(lines)


def get_next_run_time() -> Optional[str]:
    """Get next scheduled run time"""
    return MonitorService().get_next_run_time()


def get_full_status() -> Dict[str, Any]:
    """Get full monitoring status"""
    return MonitorService().get_full_status()
