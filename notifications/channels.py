"""
Notification Channels Module
通知渠道模組

BTC/ETH Monitoring System - Notification Layer
BTC/ETH 監測系統 - 通知層

This module provides notification channel integrations including Discord webhook.
本模組提供通知渠道整合，包含 Discord webhook。

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-06
"""

import json
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ChannelType(Enum):
    """Notification channel types / 通知渠道類型"""
    CONSOLE = "console"
    DISCORD_WEBHOOK = "discord_webhook"
    FILE = "file"


@dataclass
class ChannelConfig:
    """
    Channel configuration / 渠道配置
    
    Attributes:
        channel_type: Type of notification channel / 通知渠道類型
        webhook_url: Discord webhook URL (for DISCORD_WEBHOOK) / Discord webhook URL
        fallback_to_console: Whether to fallback to console on failure / 失敗時是否回退到 console
        timeout_seconds: Request timeout in seconds / 請求超時秒數
        retry_count: Number of retries on failure / 失敗時重試次數
        metadata: Additional channel-specific metadata / 額外渠道特定元資料
    """
    channel_type: ChannelType = ChannelType.CONSOLE
    webhook_url: Optional[str] = None
    fallback_to_console: bool = True
    timeout_seconds: int = 10
    retry_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """
    Send operation result / 發送操作結果
    
    Attributes:
        success: Whether the send was successful / 發送是否成功
        channel: Channel that was used / 使用的渠道
        message: Status message / 狀態訊息
        fallback_used: Whether fallback was activated / 是否使用了回退
        error: Error details if failed / 失敗時的錯誤詳情
    """
    success: bool
    channel: str
    message: str
    fallback_used: bool = False
    error: Optional[str] = None


class BaseChannel:
    """Base class for notification channels / 通知渠道基礎類別"""
    
    def __init__(self, config: ChannelConfig):
        self.config = config
    
    def send(self, message: str, embed: Optional[Dict[str, Any]] = None) -> SendResult:
        """
        Send notification / 發送通知
        
        Args:
            message: Plain text message / 純文字訊息
            embed: Discord embed data (for webhook) / Discord embed 資料
            
        Returns:
            SendResult with operation status / 包含操作狀態的 SendResult
        """
        raise NotImplementedError("Subclasses must implement send()")
    
    def send_alert(self, signal_data: Dict[str, Any]) -> SendResult:
        """
        Send formatted alert / 發送格式化提醒
        
        Args:
            signal_data: Signal payload data / 訊號 payload 資料
            
        Returns:
            SendResult with operation status / 包含操作狀態的 SendResult
        """
        raise NotImplementedError("Subclasses must implement send_alert()")


class ConsoleChannel(BaseChannel):
    """Console output channel / Console 輸出渠道"""
    
    def send(self, message: str, embed: Optional[Dict[str, Any]] = None) -> SendResult:
        """Print message to console / 印出訊息到 console"""
        print("\n" + "="*60)
        print("NOTIFICATION / 通知")
        print("="*60)
        print(message)
        if embed:
            print("\n[Embed data available / Embed 資料可用]")
        print("="*60 + "\n")
        
        return SendResult(
            success=True,
            channel="console",
            message="Message printed to console / 訊息已印出到 console"
        )
    
    def send_alert(self, signal_data: Dict[str, Any]) -> SendResult:
        """Send formatted alert to console / 發送格式化提醒到 console"""
        signal_type = signal_data.get("signal_type", "UNKNOWN")
        level = signal_data.get("level", "unknown")
        symbol = signal_data.get("symbol", "UNKNOWN")
        warning = signal_data.get("warning", "")
        reason = signal_data.get("reason", "")
        
        lines = [
            "",
            "="*60,
            f"🚨 ALERT / 提醒: {signal_type.upper()}",
            "="*60,
            f"Symbol / 標的: {symbol}",
            f"Level / 等級: {level.upper()}",
            "",
        ]
        
        if reason:
            lines.extend([f"Reason / 原因: {reason}", ""])
        
        if warning:
            lines.extend([f"⚠️  {warning}", ""])
        
        lines.append("="*60)
        lines.append("")
        
        message = "\n".join(lines)
        print(message)
        
        return SendResult(
            success=True,
            channel="console",
            message=f"Alert for {symbol} printed to console / {symbol} 提醒已印出到 console"
        )


class DiscordWebhookChannel(BaseChannel):
    """Discord webhook channel / Discord webhook 渠道"""
    
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        if config.channel_type == ChannelType.DISCORD_WEBHOOK and not config.webhook_url:
            raise ValueError("webhook_url is required for DISCORD_WEBHOOK channel type")
    
    def _build_embed(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Discord embed from signal data / 從訊號資料建立 Discord embed
        
        Args:
            signal_data: Signal payload / 訊號 payload
            
        Returns:
            Discord embed dictionary / Discord embed 字典
        """
        signal_type = signal_data.get("signal_type", "UNKNOWN")
        level = signal_data.get("level", "unknown")
        symbol = signal_data.get("symbol", "UNKNOWN")
        warning = signal_data.get("warning", "")
        reason = signal_data.get("reason", "")
        
        # Determine color based on signal type / 根據訊號類型決定顏色
        color_map = {
            "trend_long": 0x00FF00,      # Green / 綠色
            "trend_short": 0xFF0000,      # Red / 紅色
            "contrarian_watch_overheated": 0xFFA500,  # Orange / 橙色
            "contrarian_watch_oversold": 0x87CEEB,    # Light blue / 淺藍
        }
        color = color_map.get(signal_type, 0x808080)  # Default gray / 預設灰色
        
        # Determine emoji based on level / 根據等級決定表情符號
        emoji_map = {
            "confirmed": "✅",
            "watch_only": "👁️",
        }
        emoji = emoji_map.get(level, "ℹ️")
        
        # Build description / 建立描述
        description_parts = []
        if reason:
            description_parts.append(f"**Reason:** {reason}")
        description_parts.append(f"**Warning:** {warning}")
        description = "\n".join(description_parts)
        
        # Build fields / 建立欄位
        fields = []
        
        # Add price data if available / 添加價格資料（如果有）
        price_data = signal_data.get("price_data", {})
        if price_data:
            if "close_5m" in price_data:
                fields.append({
                    "name": "Close (5m)",
                    "value": f"${price_data['close_5m']:,.2f}",
                    "inline": True
                })
            if "ma5" in price_data:
                fields.append({
                    "name": "MA5",
                    "value": f"${price_data['ma5']:,.2f}",
                    "inline": True
                })
            if "ma20" in price_data:
                fields.append({
                    "name": "MA20",
                    "value": f"${price_data['ma20']:,.2f}",
                    "inline": True
                })
            if "ma240" in price_data:
                fields.append({
                    "name": "MA240",
                    "value": f"${price_data['ma240']:,.2f}",
                    "inline": True
                })
            if "volume_ratio" in price_data:
                fields.append({
                    "name": "Volume Ratio",
                    "value": f"{price_data['volume_ratio']:.2f}x",
                    "inline": True
                })
        
        # Add conditions if available / 添加條件（如果有）
        conditions = signal_data.get("conditions", {})
        if conditions:
            condition_lines = []
            for key, value in conditions.items():
                status = "✅" if value else "❌"
                condition_lines.append(f"{status} {key}")
            fields.append({
                "name": "Conditions",
                "value": "\n".join(condition_lines) if condition_lines else "N/A",
                "inline": False
            })
        
        # Build embed / 建立 embed
        embed = {
            "title": f"{emoji} {signal_type.upper().replace('_', ' ')}",
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {
                "text": f"{symbol} | Alert-Only System | {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            }
        }
        
        return embed
    
    def send(self, message: str, embed: Optional[Dict[str, Any]] = None) -> SendResult:
        """Send message via Discord webhook / 透過 Discord webhook 發送訊息"""
        if not self.config.webhook_url:
            if self.config.fallback_to_console:
                console = ConsoleChannel(ChannelConfig())
                result = console.send(message, embed)
                result.fallback_used = True
                return result
            return SendResult(
                success=False,
                channel="discord_webhook",
                message="No webhook URL configured / 未配置 webhook URL",
                error="Missing webhook_url"
            )
        
        payload = {"content": message}
        if embed:
            payload["embeds"] = [embed]
        
        for attempt in range(self.config.retry_count + 1):
            try:
                response = requests.post(
                    self.config.webhook_url,
                    json=payload,
                    timeout=self.config.timeout_seconds
                )
                response.raise_for_status()
                
                return SendResult(
                    success=True,
                    channel="discord_webhook",
                    message=f"Message sent to Discord / 訊息已發送到 Discord (attempt {attempt + 1})"
                )
                
            except requests.exceptions.Timeout:
                if attempt == self.config.retry_count:
                    error_msg = f"Discord webhook timeout after {self.config.retry_count + 1} attempts"
                    if self.config.fallback_to_console:
                        console = ConsoleChannel(ChannelConfig())
                        result = console.send(f"[Discord timeout] {message}", embed)
                        result.fallback_used = True
                        result.error = error_msg
                        return result
                    return SendResult(
                        success=False,
                        channel="discord_webhook",
                        message=error_msg,
                        error=error_msg
                    )
                    
            except requests.exceptions.RequestException as e:
                if attempt == self.config.retry_count:
                    error_msg = f"Discord webhook failed: {str(e)}"
                    if self.config.fallback_to_console:
                        console = ConsoleChannel(ChannelConfig())
                        result = console.send(f"[Discord failed] {message}", embed)
                        result.fallback_used = True
                        result.error = error_msg
                        return result
                    return SendResult(
                        success=False,
                        channel="discord_webhook",
                        message=error_msg,
                        error=error_msg
                    )
        
        return SendResult(
            success=False,
            channel="discord_webhook",
            message="Failed after all retries / 所有重試後仍失敗",
            error="Max retries exceeded"
        )
    
    def send_alert(self, signal_data: Dict[str, Any]) -> SendResult:
        """Send formatted alert via Discord webhook / 透過 Discord webhook 發送格式化提醒"""
        embed = self._build_embed(signal_data)
        
        # Build compact message for notification / 建立緊湊通知訊息
        signal_type = signal_data.get("signal_type", "UNKNOWN")
        level = signal_data.get("level", "unknown")
        symbol = signal_data.get("symbol", "UNKNOWN")
        warning = signal_data.get("warning", "")
        
        message = f"[{symbol}] {signal_type.upper()} | {level.upper()} | {warning}"
        
        return self.send(message, embed)


class MultiChannel:
    """Multi-channel sender / 多渠道發送器"""
    
    def __init__(self, channels: List[BaseChannel]):
        """
        Initialize multi-channel sender / 初始化多渠道發送器
        
        Args:
            channels: List of channel instances / 渠道實例列表
        """
        self.channels = channels
    
    def send_to_all(self, message: str, embed: Optional[Dict[str, Any]] = None) -> List[SendResult]:
        """
        Send to all channels / 發送到所有渠道
        
        Args:
            message: Message to send / 要發送的訊息
            embed: Optional embed data / 可選 embed 資料
            
        Returns:
            List of SendResult for each channel / 每個渠道的 SendResult 列表
        """
        results = []
        for channel in self.channels:
            result = channel.send(message, embed)
            results.append(result)
        return results
    
    def send_alert_to_all(self, signal_data: Dict[str, Any]) -> List[SendResult]:
        """
        Send alert to all channels / 發送提醒到所有渠道
        
        Args:
            signal_data: Signal payload / 訊號 payload
            
        Returns:
            List of SendResult for each channel / 每個渠道的 SendResult 列表
        """
        results = []
        for channel in self.channels:
            result = channel.send_alert(signal_data)
            results.append(result)
        return results


# Factory functions / 工廠函數

def create_console_channel() -> ConsoleChannel:
    """Create console channel / 建立 console 渠道"""
    return ConsoleChannel(ChannelConfig(channel_type=ChannelType.CONSOLE))


def create_discord_channel(webhook_url: str, fallback: bool = True) -> DiscordWebhookChannel:
    """
    Create Discord webhook channel / 建立 Discord webhook 渠道
    
    Args:
        webhook_url: Discord webhook URL / Discord webhook URL
        fallback: Whether to fallback to console on failure / 失敗時是否回退到 console
        
    Returns:
        DiscordWebhookChannel instance / DiscordWebhookChannel 實例
    """
    config = ChannelConfig(
        channel_type=ChannelType.DISCORD_WEBHOOK,
        webhook_url=webhook_url,
        fallback_to_console=fallback
    )
    return DiscordWebhookChannel(config)


def create_channel_from_config(config: ChannelConfig) -> BaseChannel:
    """
    Create channel from config / 從配置建立渠道
    
    Args:
        config: Channel configuration / 渠道配置
        
    Returns:
        BaseChannel instance / BaseChannel 實例
    """
    if config.channel_type == ChannelType.CONSOLE:
        return ConsoleChannel(config)
    elif config.channel_type == ChannelType.DISCORD_WEBHOOK:
        return DiscordWebhookChannel(config)
    else:
        raise ValueError(f"Unsupported channel type: {config.channel_type}")


def create_multi_channel(configs: List[ChannelConfig]) -> MultiChannel:
    """
    Create multi-channel sender from configs / 從配置建立多渠道發送器
    
    Args:
        configs: List of channel configurations / 渠道配置列表
        
    Returns:
        MultiChannel instance / MultiChannel 實例
    """
    channels = [create_channel_from_config(cfg) for cfg in configs]
    return MultiChannel(channels)


# Example usage / 使用範例
if __name__ == "__main__":
    # Test console channel / 測試 console 渠道
    print("Testing console channel / 測試 console 渠道...")
    console = create_console_channel()
    
    test_signal = {
        "signal_type": "trend_long",
        "level": "confirmed",
        "symbol": "BTCUSDT",
        "warning": "ALERT_ONLY_NO_AUTO_TRADE",
        "reason": "BTCUSDT: close > MA240, MA5 crossed above MA20",
        "price_data": {
            "close_5m": 70250.00,
            "ma5": 70180.00,
            "ma20": 70050.00,
            "ma240": 69500.00,
            "volume_ratio": 2.51
        },
        "conditions": {
            "c1_above_ma240": True,
            "c2_ma_cross_above": True,
            "c3_volume_spike": True
        }
    }
    
    result = console.send_alert(test_signal)
    print(f"Result: {result}")
    
    print("\n✅ Console channel test complete / Console 渠道測試完成")
