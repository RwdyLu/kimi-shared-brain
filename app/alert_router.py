"""
Multi-channel Alert Router
Routes alerts to multiple channels with priority-based delivery.
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AlertPriority(Enum):
    """Alert priority levels."""

    CRITICAL = "critical"  # Immediate delivery to all channels
    HIGH = "high"  # Fast delivery, multiple channels
    MEDIUM = "medium"  # Standard delivery
    LOW = "low"  # Batched delivery
    INFO = "info"  # Log only unless configured


class AlertChannel(Enum):
    """Available alert channels."""

    DISCORD = "discord"
    EMAIL = "email"
    WEBHOOK = "webhook"
    TELEGRAM = "telegram"
    SLACK = "slack"
    SMS = "sms"
    LOG = "log"
    CONSOLE = "console"


@dataclass
class Alert:
    """Alert message."""

    alert_id: str
    title: str
    message: str
    priority: AlertPriority
    source: str  # System component
    category: str  # Alert category
    channels: List[AlertChannel] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "source": self.source,
            "category": self.category,
            "channels": [c.value for c in self.channels],
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class ChannelConfig:
    """Channel configuration."""

    channel: AlertChannel
    enabled: bool = True
    min_priority: AlertPriority = AlertPriority.LOW
    rate_limit: int = 60  # Seconds between alerts
    cooldown: int = 300  # Seconds after burst
    max_burst: int = 5  # Max alerts in burst window
    format_template: str = "[{priority}] {title}: {message}"

    def to_dict(self) -> Dict:
        return {
            "channel": self.channel.value,
            "enabled": self.enabled,
            "min_priority": self.min_priority.value,
            "rate_limit": self.rate_limit,
            "cooldown": self.cooldown,
            "max_burst": self.max_burst,
        }


@dataclass
class DeliveryResult:
    """Alert delivery result."""

    alert_id: str
    channel: AlertChannel
    success: bool
    timestamp: datetime
    error: Optional[str] = None
    delivery_time_ms: float = 0.0


class AlertRouter:
    """
    Multi-channel alert router with priority-based delivery.
    Supports rate limiting, deduplication, and channel-specific formatting.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Channel configurations
        self.channels: Dict[AlertChannel, ChannelConfig] = {}
        self.channel_handlers: Dict[AlertChannel, Callable] = {}

        # Rate limiting
        self.last_alert_time: Dict[AlertChannel, datetime] = {}
        self.burst_counts: Dict[AlertChannel, int] = {}
        self.cooldown_until: Dict[AlertChannel, datetime] = {}

        # Alert storage
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.max_history = 1000

        # Delivery tracking
        self.delivery_results: List[DeliveryResult] = []

        # Default channels
        self._setup_default_channels()

        self.logger.info("AlertRouter initialized")

    def _setup_default_channels(self):
        """Setup default channel configurations."""
        defaults = [
            ChannelConfig(AlertChannel.LOG, enabled=True, min_priority=AlertPriority.INFO),
            ChannelConfig(AlertChannel.CONSOLE, enabled=True, min_priority=AlertPriority.LOW),
            ChannelConfig(AlertChannel.DISCORD, enabled=False, min_priority=AlertPriority.MEDIUM),
            ChannelConfig(AlertChannel.WEBHOOK, enabled=False, min_priority=AlertPriority.HIGH),
            ChannelConfig(AlertChannel.EMAIL, enabled=False, min_priority=AlertPriority.HIGH),
            ChannelConfig(AlertChannel.TELEGRAM, enabled=False, min_priority=AlertPriority.MEDIUM),
            ChannelConfig(AlertChannel.SLACK, enabled=False, min_priority=AlertPriority.MEDIUM),
            ChannelConfig(AlertChannel.SMS, enabled=False, min_priority=AlertPriority.CRITICAL),
        ]

        for config in defaults:
            self.channels[config.channel] = config

    def configure_channel(
        self,
        channel: AlertChannel,
        enabled: Optional[bool] = None,
        min_priority: Optional[AlertPriority] = None,
        rate_limit: Optional[int] = None,
        handler: Optional[Callable] = None,
    ):
        """
        Configure alert channel.

        Args:
            channel: Channel to configure
            enabled: Enable/disable channel
            min_priority: Minimum priority for this channel
            rate_limit: Rate limit in seconds
            handler: Custom handler function
        """
        if channel in self.channels:
            config = self.channels[channel]

            if enabled is not None:
                config.enabled = enabled
            if min_priority is not None:
                config.min_priority = min_priority
            if rate_limit is not None:
                config.rate_limit = rate_limit

        if handler:
            self.channel_handlers[channel] = handler

        self.logger.info(f"Configured {channel.value}: enabled={self.channels[channel].enabled}")

    def _check_rate_limit(self, channel: AlertChannel) -> bool:
        """Check if channel can send alert (rate limit)."""
        config = self.channels[channel]
        now = datetime.now()

        # Check cooldown
        if channel in self.cooldown_until:
            if now < self.cooldown_until[channel]:
                return False

        # Check rate limit
        if channel in self.last_alert_time:
            elapsed = (now - self.last_alert_time[channel]).total_seconds()
            if elapsed < config.rate_limit:
                return False

        # Check burst
        if channel in self.burst_counts:
            if self.burst_counts[channel] >= config.max_burst:
                # Enter cooldown
                self.cooldown_until[channel] = now + self._seconds_to_delta(config.cooldown)
                self.burst_counts[channel] = 0
                self.logger.warning(f"Channel {channel.value} burst limit reached, cooldown for {config.cooldown}s")
                return False

        return True

    def _seconds_to_delta(self, seconds: int):
        """Convert seconds to timedelta."""
        from datetime import timedelta

        return timedelta(seconds=seconds)

    def _format_alert(self, alert: Alert, channel: AlertChannel) -> str:
        """Format alert for specific channel."""
        config = self.channels[channel]

        return config.format_template.format(
            priority=alert.priority.value.upper(),
            title=alert.title,
            message=alert.message,
            source=alert.source,
            category=alert.category,
            timestamp=alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def send_alert(self, alert: Alert) -> List[DeliveryResult]:
        """
        Send alert to configured channels.

        Args:
            alert: Alert to send

        Returns:
            List of delivery results
        """
        self.logger.info(f"Routing alert: {alert.alert_id} ({alert.priority.value})")

        # Store alert
        self.active_alerts[alert.alert_id] = alert
        self.alert_history.append(alert)

        if len(self.alert_history) > self.max_history:
            self.alert_history.pop(0)

        results = []

        # Determine target channels
        target_channels = (
            alert.channels
            if alert.channels
            else [
                c
                for c, config in self.channels.items()
                if config.enabled and alert.priority.value >= config.min_priority.value
            ]
        )

        # Deliver to each channel
        for channel in target_channels:
            config = self.channels[channel]

            # Skip disabled channels
            if not config.enabled:
                continue

            # Skip if priority too low
            if alert.priority.value < config.min_priority.value:
                continue

            # Check rate limit
            if not self._check_rate_limit(channel):
                self.logger.warning(f"Rate limited: {channel.value}")
                results.append(
                    DeliveryResult(
                        alert_id=alert.alert_id,
                        channel=channel,
                        success=False,
                        timestamp=datetime.now(),
                        error="Rate limited",
                    )
                )
                continue

            # Send
            start = datetime.now()
            try:
                if channel in self.channel_handlers:
                    # Use custom handler
                    formatted = self._format_alert(alert, channel)
                    await self.channel_handlers[channel](formatted, alert)
                else:
                    # Use default handler
                    await self._default_send(channel, alert)

                delivery_time = (datetime.now() - start).total_seconds() * 1000

                results.append(
                    DeliveryResult(
                        alert_id=alert.alert_id,
                        channel=channel,
                        success=True,
                        timestamp=datetime.now(),
                        delivery_time_ms=delivery_time,
                    )
                )

                # Update rate limit tracking
                self.last_alert_time[channel] = datetime.now()
                self.burst_counts[channel] = self.burst_counts.get(channel, 0) + 1

                self.logger.info(f"Delivered to {channel.value} in {delivery_time:.1f}ms")

            except Exception as e:
                self.logger.error(f"Delivery failed to {channel.value}: {e}")
                results.append(
                    DeliveryResult(
                        alert_id=alert.alert_id, channel=channel, success=False, timestamp=datetime.now(), error=str(e)
                    )
                )

        self.delivery_results.extend(results)
        return results

    async def _default_send(self, channel: AlertChannel, alert: Alert):
        """Default channel sender."""
        formatted = self._format_alert(alert, channel)

        if channel == AlertChannel.LOG:
            level = logging.WARNING if alert.priority in (AlertPriority.HIGH, AlertPriority.CRITICAL) else logging.INFO
            self.logger.log(level, f"ALERT: {formatted}")

        elif channel == AlertChannel.CONSOLE:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {formatted}")

        elif channel == AlertChannel.DISCORD:
            # Placeholder for Discord integration
            self.logger.info(f"[Discord] {formatted[:100]}...")

        elif channel == AlertChannel.WEBHOOK:
            # Placeholder for webhook
            self.logger.info(f"[Webhook] {formatted[:100]}...")

        elif channel == AlertChannel.EMAIL:
            # Placeholder for email
            self.logger.info(f"[Email] {formatted[:100]}...")

        else:
            self.logger.info(f"[{channel.value}] {formatted}")

    def resolve_alert(self, alert_id: str, resolution: str = "") -> bool:
        """
        Mark alert as resolved.

        Args:
            alert_id: Alert to resolve
            resolution: Resolution message

        Returns:
            True if resolved
        """
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            alert.resolved_at = datetime.now()
            alert.metadata["resolution"] = resolution

            self.logger.info(f"Resolved alert: {alert_id}")
            return True

        return False

    def get_active_alerts(
        self, priority: Optional[AlertPriority] = None, category: Optional[str] = None
    ) -> List[Alert]:
        """Get active (unresolved) alerts."""
        alerts = [a for a in self.active_alerts.values() if not a.resolved]

        if priority:
            alerts = [a for a in alerts if a.priority == priority]

        if category:
            alerts = [a for a in alerts if a.category == category]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_alert_stats(self) -> Dict:
        """Get alert statistics."""
        active = self.get_active_alerts()

        by_priority = {}
        for p in AlertPriority:
            by_priority[p.value] = len([a for a in active if a.priority == p])

        by_channel = {}
        for result in self.delivery_results[-100:]:  # Last 100 deliveries
            ch = result.channel.value
            if ch not in by_channel:
                by_channel[ch] = {"success": 0, "failed": 0}
            if result.success:
                by_channel[ch]["success"] += 1
            else:
                by_channel[ch]["failed"] += 1

        return {
            "active_alerts": len(active),
            "total_alerts": len(self.alert_history),
            "by_priority": by_priority,
            "delivery_stats": by_channel,
            "delivery_success_rate": self._calculate_success_rate(),
        }

    def _calculate_success_rate(self) -> float:
        """Calculate delivery success rate."""
        if not self.delivery_results:
            return 0.0

        recent = self.delivery_results[-100:]
        successful = sum(1 for r in recent if r.success)
        return (successful / len(recent)) * 100

    def export_alerts(self, filepath: str, active_only: bool = False):
        """Export alerts to JSON."""
        if active_only:
            alerts = [a.to_dict() for a in self.get_active_alerts()]
        else:
            alerts = [a.to_dict() for a in self.alert_history[-100:]]

        with open(filepath, "w") as f:
            json.dump({"exported_at": datetime.now().isoformat(), "alerts": alerts}, f, indent=2)

        self.logger.info(f"Alerts exported to {filepath}")


# Convenience functions for quick alerts
async def quick_alert(router: AlertRouter, title: str, message: str, priority: str = "medium", source: str = "system"):
    """Send a quick alert."""
    priority_map = {
        "critical": AlertPriority.CRITICAL,
        "high": AlertPriority.HIGH,
        "medium": AlertPriority.MEDIUM,
        "low": AlertPriority.LOW,
        "info": AlertPriority.INFO,
    }

    alert = Alert(
        alert_id=f"alert_{datetime.now().timestamp()}",
        title=title,
        message=message,
        priority=priority_map.get(priority, AlertPriority.MEDIUM),
        source=source,
        category="quick",
    )

    return await router.send_alert(alert)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    router = AlertRouter()

    # Configure channels
    router.configure_channel(AlertChannel.CONSOLE, enabled=True, min_priority=AlertPriority.LOW)
    router.configure_channel(AlertChannel.LOG, enabled=True, min_priority=AlertPriority.INFO)

    # Example alert
    async def demo():
        alert = Alert(
            alert_id="demo_001",
            title="High CPU Usage",
            message="CPU usage has been above 80% for 5 minutes",
            priority=AlertPriority.HIGH,
            source="health_monitor",
            category="system",
        )

        results = await router.send_alert(alert)

        print("\nAlert Router Demo")
        print("=" * 50)
        print(f"Alert: {alert.title}")
        print(f"Priority: {alert.priority.value}")
        print(f"Deliveries: {len(results)}")

        for result in results:
            icon = "✅" if result.success else "❌"
            print(f"{icon} {result.channel.value}: {result.delivery_time_ms:.1f}ms")

        print(f"\nStats: {router.get_alert_stats()}")

    asyncio.run(demo())
