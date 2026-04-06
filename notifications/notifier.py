"""
Notifier Module
通知器模組

BTC/ETH Monitoring System - Notification Layer
BTC/ETH 監測系統 - 通知層

This module handles notification delivery for the monitoring system.
Supports console output and file-based logging. Alert-only, no auto trading.

本模組處理監測系統的通知傳送。支援主控台輸出與檔案記錄。僅提醒，無自動交易。

⚠️  IMPORTANT / 重要  ⚠️
This module generates ALERTS ONLY. No automatic trading is performed.
本模組僅產生提醒，不執行自動交易。

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-06
"""

import json
import os
import sys
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, '/tmp/kimi-shared-brain')

from signals.engine import Signal, SignalType, SignalLevel
from notifications.formatter import NotificationFormatter, OutputFormat


class OutputChannel(Enum):
    """Output channels / 輸出通道"""
    CONSOLE = "console"
    FILE = "file"
    BOTH = "both"


@dataclass
class NotifierConfig:
    """
    Notifier configuration / 通知器設定
    
    Defines output settings for the notifier.
    定義通知器的輸出設定。
    """
    output_channel: OutputChannel = OutputChannel.CONSOLE
    output_dir: str = "/tmp/kimi-shared-brain/alerts"
    log_file: str = "alerts.log"
    json_file: str = "alerts.json"
    language: str = "en"
    console_color: bool = True
    max_history: int = 1000  # Maximum alerts to keep in JSON history


class Notifier:
    """
    Signal notifier / 訊號通知器
    
    Handles notification delivery for signals.
    Supports console output and file-based logging.
    
    ⚠️  ALERT ONLY - No automatic trading
    """
    
    # ANSI color codes / ANSI 顏色代碼
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m"
    }
    
    def __init__(self, config: Optional[NotifierConfig] = None):
        """
        Initialize notifier / 初始化通知器
        
        Args:
            config: Notifier configuration / 通知器設定
        """
        self.config = config or NotifierConfig()
        self.formatter = NotificationFormatter(language=self.config.language)
        
        # Setup output directory / 設定輸出目錄
        if self.config.output_channel in [OutputChannel.FILE, OutputChannel.BOTH]:
            os.makedirs(self.config.output_dir, exist_ok=True)
    
    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text / 為文字套用顏色"""
        if not self.config.console_color:
            return text
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"
    
    def _get_signal_color(self, signal: Signal) -> str:
        """Get color for signal type / 取得訊號類型的顏色"""
        if signal.level == SignalLevel.WATCH_ONLY:
            return "yellow"
        elif signal.signal_type == SignalType.TREND_LONG:
            return "green"
        elif signal.signal_type == SignalType.TREND_SHORT:
            return "red"
        return "cyan"
    
    def _output_console(self, message: str, signal: Optional[Signal] = None) -> None:
        """
        Output message to console / 將訊息輸出至主控台
        
        Args:
            message: Message to output / 要輸出的訊息
            signal: Optional signal for color coding / 可選訊號用於顏色編碼
        """
        if signal and self.config.console_color:
            color = self._get_signal_color(signal)
            print(self._colorize(message, color))
        else:
            print(message)
    
    def _output_file(self, message: str, signal: Optional[Signal] = None) -> None:
        """
        Output message to file / 將訊息輸出至檔案
        
        Args:
            message: Message to output / 要輸出的訊息
            signal: Optional signal / 可選訊號
        """
        log_path = os.path.join(self.config.output_dir, self.config.log_file)
        
        with open(log_path, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}]\n{message}\n\n")
    
    def _append_json_history(self, signal: Signal) -> None:
        """
        Append signal to JSON history / 將訊號附加至 JSON 歷史記錄
        
        Args:
            signal: Signal to append / 要附加的訊號
        """
        json_path = os.path.join(self.config.output_dir, self.config.json_file)
        
        # Load existing history / 載入現有歷史
        history = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []
        
        # Append new signal / 附加新訊號
        history.append(signal.to_dict())
        
        # Trim history if exceeds max / 若超過最大值則修剪歷史
        if len(history) > self.config.max_history:
            history = history[-self.config.max_history:]
        
        # Save history / 儲存歷史
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    
    def notify(self, signal: Signal, format_type: OutputFormat = OutputFormat.PLAIN_TEXT) -> bool:
        """
        Send notification for a signal / 為訊號發送通知
        
        Args:
            signal: Signal to notify / 要通知的訊號
            format_type: Output format type / 輸出格式類型
            
        Returns:
            True if notification sent successfully / 若通知發送成功則為 True
        """
        try:
            # Format message / 格式化訊息
            if format_type == OutputFormat.PLAIN_TEXT:
                message = self.formatter.format_alert(signal)
            elif format_type == OutputFormat.COMPACT:
                message = self.formatter.format_compact(signal)
            elif format_type == OutputFormat.MARKDOWN:
                message = self.formatter.format_markdown(signal)
            else:
                message = self.formatter.format_alert(signal)
            
            # Output to console / 輸出至主控台
            if self.config.output_channel in [OutputChannel.CONSOLE, OutputChannel.BOTH]:
                self._output_console(message, signal)
            
            # Output to file / 輸出至檔案
            if self.config.output_channel in [OutputChannel.FILE, OutputChannel.BOTH]:
                self._output_file(message, signal)
                self._append_json_history(signal)
            
            return True
            
        except Exception as e:
            print(f"Notification error / 通知錯誤: {e}")
            return False
    
    def notify_batch(self, signals: List[Signal], format_type: OutputFormat = OutputFormat.PLAIN_TEXT) -> int:
        """
        Send notifications for multiple signals / 為多個訊號發送通知
        
        Args:
            signals: List of signals to notify / 要通知的訊號列表
            format_type: Output format type / 輸出格式類型
            
        Returns:
            Number of successfully notified signals / 成功通知的訊號數量
        """
        if not signals:
            if self.config.language == "en":
                print("No signals to notify / 無訊號通知")
            else:
                print("無訊號通知")
            return 0
        
        success_count = 0
        
        for signal in signals:
            if self.notify(signal, format_type):
                success_count += 1
        
        # Summary / 摘要
        if self.config.output_channel in [OutputChannel.CONSOLE, OutputChannel.BOTH]:
            if self.config.language == "en":
                print(f"\n{'=' * 50}")
                print(f"Batch notification complete / 批次通知完成")
                print(f"Success / 成功: {success_count}/{len(signals)}")
                print(f"{'=' * 50}")
            else:
                print(f"\n{'=' * 50}")
                print(f"批次通知完成")
                print(f"成功: {success_count}/{len(signals)}")
                print(f"{'=' * 50}")
        
        return success_count
    
    def get_alert_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get alert history from JSON file / 從 JSON 檔案取得提醒歷史
        
        Args:
            limit: Maximum number of alerts to return / 要回傳的最大提醒數量
            
        Returns:
            List of alert dictionaries / 提醒字典列表
        """
        json_path = os.path.join(self.config.output_dir, self.config.json_file)
        
        if not os.path.exists(json_path):
            return []
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            if limit:
                history = history[-limit:]
            
            return history
            
        except (json.JSONDecodeError, IOError):
            return []
    
    def clear_history(self) -> bool:
        """
        Clear alert history / 清除提醒歷史
        
        Returns:
            True if cleared successfully / 若清除成功則為 True
        """
        json_path = os.path.join(self.config.output_dir, self.config.json_file)
        
        try:
            if os.path.exists(json_path):
                os.remove(json_path)
            return True
        except IOError:
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get notification statistics / 取得通知統計
        
        Returns:
            Dictionary with statistics / 包含統計資料的字典
        """
        history = self.get_alert_history()
        
        stats = {
            "total_alerts": len(history),
            "by_type": {},
            "by_level": {},
            "by_symbol": {}
        }
        
        for alert in history:
            signal_type = alert.get("signal_type", "unknown")
            level = alert.get("level", "unknown")
            symbol = alert.get("symbol", "unknown")
            
            stats["by_type"][signal_type] = stats["by_type"].get(signal_type, 0) + 1
            stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
            stats["by_symbol"][symbol] = stats["by_symbol"].get(symbol, 0) + 1
        
        return stats


class AlertOnlyNotifier(Notifier):
    """
    Alert-only notifier with extra safety checks / 帶額外安全檢查的僅提醒通知器
    
    This notifier enforces the alert-only policy with additional warnings.
    此通知器透過額外警告強制執行僅提醒政策。
    """
    
    ALERT_HEADER = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              ⚠️  ALERT ONLY - NO AUTO TRADING  ⚠️                 ║
║                                                                  ║
║         This is a MONITORING SYSTEM, not a trading system.       ║
║         這是監測系統，不是交易系統。                               ║
║                                                                  ║
║  • No orders will be placed automatically                        ║
║  • No positions will be managed                                  ║
║  • All decisions require human review                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    
    def __init__(self, config: Optional[NotifierConfig] = None):
        """Initialize alert-only notifier / 初始化僅提醒通知器"""
        super().__init__(config)
        self._alert_header_shown = False
    
    def _show_alert_header(self) -> None:
        """Show alert header once / 顯示提醒標頭（僅一次）"""
        if not self._alert_header_shown and self.config.output_channel in [OutputChannel.CONSOLE, OutputChannel.BOTH]:
            print(self.ALERT_HEADER)
            self._alert_header_shown = True
    
    def notify(self, signal: Signal, format_type: OutputFormat = OutputFormat.PLAIN_TEXT) -> bool:
        """
        Send notification with extra safety warnings / 發送帶額外安全警告的通知
        
        Args:
            signal: Signal to notify / 要通知的訊號
            format_type: Output format type / 輸出格式類型
            
        Returns:
            True if notification sent successfully / 若通知發送成功則為 True
        """
        # Show alert header / 顯示提醒標頭
        self._show_alert_header()
        
        # Add extra warning for contrarian signals / 為逆勢訊號添加額外警告
        if signal.level == SignalLevel.WATCH_ONLY:
            extra_warning = """
╔══════════════════════════════════════════════════════════════════╗
║  👁️  WATCH ONLY SIGNAL - NOT FOR EXECUTION                       ║
║  👁️  僅觀察訊號 - 非執行訊號                                      ║
╚══════════════════════════════════════════════════════════════════╝
"""
            if self.config.output_channel in [OutputChannel.CONSOLE, OutputChannel.BOTH]:
                print(extra_warning)
        
        # Call parent notify / 呼叫父類別通知
        return super().notify(signal, format_type)


# Convenience functions / 便利函式

def create_console_notifier(language: str = "en") -> Notifier:
    """
    Create console-only notifier / 建立僅主控台通知器
    
    Args:
        language: Output language / 輸出語言
        
    Returns:
        Configured Notifier instance / 配置好的通知器實例
    """
    config = NotifierConfig(
        output_channel=OutputChannel.CONSOLE,
        language=language
    )
    return Notifier(config)


def create_file_notifier(output_dir: str, language: str = "en") -> Notifier:
    """
    Create file-only notifier / 建立僅檔案通知器
    
    Args:
        output_dir: Directory for alert files / 提醒檔案目錄
        language: Output language / 輸出語言
        
    Returns:
        Configured Notifier instance / 配置好的通知器實例
    """
    config = NotifierConfig(
        output_channel=OutputChannel.FILE,
        output_dir=output_dir,
        language=language
    )
    return Notifier(config)


def create_default_notifier(output_dir: str = "/tmp/kimi-shared-brain/alerts", language: str = "en") -> Notifier:
    """
    Create default notifier (console + file) / 建立預設通知器（主控台 + 檔案）
    
    Args:
        output_dir: Directory for alert files / 提醒檔案目錄
        language: Output language / 輸出語言
        
    Returns:
        Configured Notifier instance / 配置好的通知器實例
    """
    config = NotifierConfig(
        output_channel=OutputChannel.BOTH,
        output_dir=output_dir,
        language=language
    )
    return AlertOnlyNotifier(config)


# Example usage / 使用範例
if __name__ == "__main__":
    print("Notifier Module")
    print("通知器模組")
    print("=" * 40)
    
    print("\n⚠️  ALERT ONLY SYSTEM / 僅提醒系統")
    print("This module generates ALERTS ONLY.")
    print("本模組僅產生提醒。")
    print("NO automatic trading is performed.")
    print("不執行自動交易。")
    
    print("\nExample / 範例:")
    print("  notifier = create_default_notifier()")
    print("  notifier.notify(signal)")
    print("  notifier.notify_batch(signals)")
    
    print("\nOutput Channels / 輸出通道:")
    print("  - CONSOLE: Print to stdout / 輸出至標準輸出")
    print("  - FILE: Save to alert files / 儲存至提醒檔案")
    print("  - BOTH: Console + File / 主控台 + 檔案")
    
    print("\nOutput Files / 輸出檔案:")
    print("  - alerts.log: Human-readable logs / 人類可讀記錄")
    print("  - alerts.json: Structured JSON history / 結構化 JSON 歷史")
