"""
Order Retry Mechanism and Alert System
Handles order failures with automatic retry, backoff, and alerting.
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta


class RetryStatus(Enum):
    """Retry lifecycle status."""

    PENDING = "pending"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"
    MAX_RETRIES = "max_retries"
    CANCELLED = "cancelled"


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay
    backoff_multiplier: float = 2.0  # Exponential backoff multiplier
    retryable_errors: List[str] = field(
        default_factory=lambda: ["timeout", "connection", "rate_limit", "server_error", "network"]
    )
    non_retryable_errors: List[str] = field(
        default_factory=lambda: ["insufficient_balance", "invalid_symbol", "invalid_amount", "auth_failed"]
    )


@dataclass
class Alert:
    """Alert notification."""

    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    source: str
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
        }


class AlertManager:
    """
    Manages alert notifications with multiple channels.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_handlers: List[Callable[[Alert], None]] = []
        self.alert_history: List[Alert] = []
        self.rate_limits: Dict[str, datetime] = {}

        # Default handlers
        self.add_handler(self._log_alert)
        self.add_handler(self._store_alert)

    def add_handler(self, handler: Callable[[Alert], None]):
        """Add an alert handler."""
        self.alert_handlers.append(handler)

    def send_alert(
        self, level: AlertLevel, title: str, message: str, source: str = "order_retry", metadata: Optional[Dict] = None
    ):
        """
        Send an alert through all channels.

        Args:
            level: Alert severity
            title: Alert title
            message: Alert message
            source: Alert source
            metadata: Additional data
        """
        alert = Alert(
            level=level, title=title, message=message, timestamp=datetime.now(), source=source, metadata=metadata or {}
        )

        # Rate limiting for non-critical alerts
        if level != AlertLevel.CRITICAL:
            key = f"{source}:{title}"
            if key in self.rate_limits:
                if datetime.now() - self.rate_limits[key] < timedelta(minutes=5):
                    return  # Skip, too soon
            self.rate_limits[key] = datetime.now()

        # Send through all handlers
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                self.logger.error(f"Alert handler failed: {e}")

        self.alert_history.append(alert)

    def _log_alert(self, alert: Alert):
        """Log alert to logger."""
        log_method = {
            AlertLevel.INFO: self.logger.info,
            AlertLevel.WARNING: self.logger.warning,
            AlertLevel.ERROR: self.logger.error,
            AlertLevel.CRITICAL: self.logger.critical,
        }.get(alert.level, self.logger.info)

        log_method(f"[{alert.level.value.upper()}] {alert.title}: {alert.message}")

    def _store_alert(self, alert: Alert):
        """Store alert in history."""
        self.alert_history.append(alert)

    def get_recent_alerts(self, level: Optional[AlertLevel] = None, minutes: int = 60) -> List[Alert]:
        """Get recent alerts."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        alerts = [a for a in self.alert_history if a.timestamp > cutoff]

        if level:
            alerts = [a for a in alerts if a.level == level]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_alert_summary(self) -> Dict:
        """Get alert statistics."""
        now = datetime.now()
        last_hour = [a for a in self.alert_history if a.timestamp > now - timedelta(hours=1)]
        last_24h = [a for a in self.alert_history if a.timestamp > now - timedelta(hours=24)]

        def count_by_level(alerts):
            return {
                "info": len([a for a in alerts if a.level == AlertLevel.INFO]),
                "warning": len([a for a in alerts if a.level == AlertLevel.WARNING]),
                "error": len([a for a in alerts if a.level == AlertLevel.ERROR]),
                "critical": len([a for a in alerts if a.level == AlertLevel.CRITICAL]),
            }

        return {
            "last_hour": count_by_level(last_hour),
            "last_24h": count_by_level(last_24h),
            "total": len(self.alert_history),
        }


class OrderRetryManager:
    """
    Manages order retries with exponential backoff and alerting.
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or RetryConfig()
        self.alert_manager = AlertManager()

        # Active retries tracking
        self.active_retries: Dict[str, Dict] = {}
        self.retry_stats: Dict[str, Dict] = {"total_attempts": 0, "successes": 0, "failures": 0, "retries": 0}

    def is_retryable(self, error_message: str) -> bool:
        """
        Determine if an error is retryable.

        Args:
            error_message: Error message or exception string

        Returns:
            True if error is retryable
        """
        error_lower = error_message.lower()

        # Check non-retryable first
        for non_retry in self.config.non_retryable_errors:
            if non_retry in error_lower:
                return False

        # Check retryable
        for retryable in self.config.retryable_errors:
            if retryable in error_lower:
                return True

        # Default: retry if not explicitly non-retryable
        return True

    async def execute_with_retry(self, operation_id: str, operation: Callable, *args, **kwargs) -> Dict:
        """
        Execute an operation with retry logic.

        Args:
            operation_id: Unique operation identifier
            operation: Async callable to execute
            *args, **kwargs: Arguments for operation

        Returns:
            Dict with result and metadata
        """
        attempt = 0
        last_error = None
        start_time = time.time()

        self.active_retries[operation_id] = {
            "status": RetryStatus.RETRYING,
            "attempt": 0,
            "start_time": start_time,
            "errors": [],
        }

        while attempt <= self.config.max_retries:
            attempt += 1
            self.retry_stats["total_attempts"] += 1
            self.active_retries[operation_id]["attempt"] = attempt

            try:
                self.logger.info(f"[{operation_id}] Attempt {attempt}/{self.config.max_retries + 1}")

                # Execute operation
                result = await operation(*args, **kwargs)

                # Success
                self.retry_stats["successes"] += 1
                self.active_retries[operation_id]["status"] = RetryStatus.SUCCESS

                execution_time = time.time() - start_time

                if attempt > 1:
                    self.alert_manager.send_alert(
                        level=AlertLevel.INFO,
                        title="Order Retry Successful",
                        message=f"Operation {operation_id} succeeded after {attempt} attempts",
                        metadata={"operation_id": operation_id, "attempts": attempt, "execution_time": execution_time},
                    )

                return {
                    "success": True,
                    "result": result,
                    "attempts": attempt,
                    "execution_time": execution_time,
                    "operation_id": operation_id,
                }

            except Exception as e:
                error_msg = str(e)
                last_error = e
                self.active_retries[operation_id]["errors"].append(error_msg)

                # Check if retryable
                if not self.is_retryable(error_msg):
                    self.logger.error(f"[{operation_id}] Non-retryable error: {error_msg}")
                    self.retry_stats["failures"] += 1
                    self.active_retries[operation_id]["status"] = RetryStatus.FAILED

                    self.alert_manager.send_alert(
                        level=AlertLevel.ERROR,
                        title="Order Failed",
                        message=f"Operation {operation_id} failed with non-retryable error: {error_msg}",
                        metadata={"operation_id": operation_id, "error": error_msg, "attempts": attempt},
                    )

                    return {
                        "success": False,
                        "error": error_msg,
                        "attempts": attempt,
                        "retryable": False,
                        "operation_id": operation_id,
                    }

                # Check if max retries reached
                if attempt > self.config.max_retries:
                    self.logger.error(f"[{operation_id}] Max retries ({self.config.max_retries}) reached")
                    self.retry_stats["failures"] += 1
                    self.active_retries[operation_id]["status"] = RetryStatus.MAX_RETRIES

                    self.alert_manager.send_alert(
                        level=AlertLevel.CRITICAL,
                        title="Max Retries Exceeded",
                        message=f"Operation {operation_id} failed after {attempt} attempts",
                        metadata={
                            "operation_id": operation_id,
                            "error": error_msg,
                            "attempts": attempt,
                            "errors": self.active_retries[operation_id]["errors"],
                        },
                    )

                    return {
                        "success": False,
                        "error": error_msg,
                        "attempts": attempt,
                        "retryable": True,
                        "max_retries_reached": True,
                        "operation_id": operation_id,
                    }

                # Calculate delay with exponential backoff
                delay = min(
                    self.config.base_delay * (self.config.backoff_multiplier ** (attempt - 1)), self.config.max_delay
                )

                # Add jitter (±20%)
                jitter = delay * 0.2 * (2 * (hash(str(time.time())) % 1000) / 1000 - 1)
                delay = delay + jitter

                self.retry_stats["retries"] += 1
                self.logger.warning(
                    f"[{operation_id}] Attempt {attempt} failed: {error_msg}. " f"Retrying in {delay:.1f}s..."
                )

                # Send retry alert (rate limited)
                self.alert_manager.send_alert(
                    level=AlertLevel.WARNING,
                    title="Order Retry",
                    message=f"Attempt {attempt} failed for {operation_id}: {error_msg}. Retrying in {delay:.1f}s",
                    metadata={"operation_id": operation_id, "attempt": attempt, "delay": delay, "error": error_msg},
                )

                await asyncio.sleep(delay)

        # Should not reach here
        return {"success": False, "error": str(last_error), "attempts": attempt, "operation_id": operation_id}

    def get_retry_stats(self) -> Dict:
        """Get retry statistics."""
        return self.retry_stats.copy()

    def get_active_retries(self) -> Dict:
        """Get currently active retries."""
        return {k: v for k, v in self.active_retries.items() if v["status"] == RetryStatus.RETRYING}

    def cancel_retry(self, operation_id: str) -> bool:
        """Cancel an active retry."""
        if operation_id in self.active_retries:
            self.active_retries[operation_id]["status"] = RetryStatus.CANCELLED
            return True
        return False


# Convenience function
async def retry_operation(
    operation: Callable, *args, max_retries: int = 3, operation_id: Optional[str] = None, **kwargs
) -> Dict:
    """
    Quick retry wrapper.

    Usage:
        result = await retry_operation(place_order, symbol, amount, max_retries=5)
        if result["success"]:
            print(f"Success after {result['attempts']} attempts")
    """
    config = RetryConfig(max_retries=max_retries)
    manager = OrderRetryManager(config)

    op_id = operation_id or f"op_{int(time.time())}"
    return await manager.execute_with_retry(op_id, operation, *args, **kwargs)


if __name__ == "__main__":
    # Example usage
    async def example_operation():
        # Simulate occasional failures
        if hash(str(time.time())) % 3 == 0:
            raise Exception("Temporary network error")
        return {"order_id": "12345", "status": "filled"}

    async def main():
        config = RetryConfig(max_retries=3, base_delay=0.5)
        manager = OrderRetryManager(config)

        result = await manager.execute_with_retry("example", example_operation)

        print(f"Success: {result['success']}")
        print(f"Attempts: {result['attempts']}")
        print(f"Stats: {manager.get_retry_stats()}")

    asyncio.run(main())
