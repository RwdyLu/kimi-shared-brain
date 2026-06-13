"""
System Health Monitor
Monitors CPU, memory, disk, network, and trading system health.
"""

import os
import sys
import json
import time
import psutil
import asyncio
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"  # All good
    WARNING = "warning"  # Attention needed
    CRITICAL = "critical"  # Immediate action required
    UNKNOWN = "unknown"  # Data unavailable


@dataclass
class HealthMetric:
    """Single health metric reading."""

    name: str
    value: float
    unit: str
    status: HealthStatus
    threshold_warning: float
    threshold_critical: float
    timestamp: datetime
    message: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
        }


@dataclass
class HealthSnapshot:
    """Complete system health snapshot."""

    timestamp: datetime
    overall_status: HealthStatus
    metrics: List[HealthMetric] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "metrics": [m.to_dict() for m in self.metrics],
            "alerts": self.alerts,
            "uptime_seconds": self.uptime_seconds,
        }


class HealthMonitor:
    """
    System health monitoring with configurable thresholds.
    Tracks CPU, memory, disk, network, and custom trading metrics.
    """

    def __init__(
        self,
        cpu_warning: float = 70.0,
        cpu_critical: float = 90.0,
        memory_warning: float = 80.0,
        memory_critical: float = 95.0,
        disk_warning: float = 85.0,
        disk_critical: float = 95.0,
    ):
        self.logger = logging.getLogger(__name__)

        # Thresholds
        self.cpu_warning = cpu_warning
        self.cpu_critical = cpu_critical
        self.memory_warning = memory_warning
        self.memory_critical = memory_critical
        self.disk_warning = disk_warning
        self.disk_critical = disk_critical

        # History
        self.snapshots: List[HealthSnapshot] = []
        self.max_history = 1000

        # Alert handlers
        self.alert_handlers: List[Callable[[HealthMetric], None]] = []

        # Start time
        self.start_time = datetime.now()

        # Custom monitors
        self.custom_monitors: Dict[str, Callable] = {}

        self.logger.info("HealthMonitor initialized")

    def add_alert_handler(self, handler: Callable[[HealthMetric], None]):
        """Add alert callback."""
        self.alert_handlers.append(handler)

    def add_custom_monitor(self, name: str, monitor_fn: Callable[[], float]):
        """Add custom metric monitor."""
        self.custom_monitors[name] = monitor_fn

    def check_cpu(self) -> HealthMetric:
        """Check CPU usage."""
        cpu_percent = psutil.cpu_percent(interval=1)

        if cpu_percent >= self.cpu_critical:
            status = HealthStatus.CRITICAL
            message = f"CPU critical: {cpu_percent:.1f}%"
        elif cpu_percent >= self.cpu_warning:
            status = HealthStatus.WARNING
            message = f"CPU high: {cpu_percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"CPU normal: {cpu_percent:.1f}%"

        return HealthMetric(
            name="cpu_usage",
            value=cpu_percent,
            unit="%",
            status=status,
            threshold_warning=self.cpu_warning,
            threshold_critical=self.cpu_critical,
            timestamp=datetime.now(),
            message=message,
        )

    def check_memory(self) -> HealthMetric:
        """Check memory usage."""
        mem = psutil.virtual_memory()

        if mem.percent >= self.memory_critical:
            status = HealthStatus.CRITICAL
            message = f"Memory critical: {mem.percent:.1f}%"
        elif mem.percent >= self.memory_warning:
            status = HealthStatus.WARNING
            message = f"Memory high: {mem.percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Memory normal: {mem.percent:.1f}%"

        return HealthMetric(
            name="memory_usage",
            value=mem.percent,
            unit="%",
            status=status,
            threshold_warning=self.memory_warning,
            threshold_critical=self.memory_critical,
            timestamp=datetime.now(),
            message=message,
        )

    def check_disk(self) -> HealthMetric:
        """Check disk usage."""
        disk = psutil.disk_usage("/")
        percent = disk.percent

        if percent >= self.disk_critical:
            status = HealthStatus.CRITICAL
            message = f"Disk critical: {percent:.1f}%"
        elif percent >= self.disk_warning:
            status = HealthStatus.WARNING
            message = f"Disk high: {percent:.1f}%"
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk normal: {percent:.1f}%"

        return HealthMetric(
            name="disk_usage",
            value=percent,
            unit="%",
            status=status,
            threshold_warning=self.disk_warning,
            threshold_critical=self.disk_critical,
            timestamp=datetime.now(),
            message=message,
        )

    def check_network(self) -> HealthMetric:
        """Check network connectivity."""
        try:
            import socket

            # Try to connect to a reliable host
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            status = HealthStatus.HEALTHY
            message = "Network connected"
            value = 0.0  # Latency placeholder
        except:
            status = HealthStatus.CRITICAL
            message = "Network disconnected"
            value = 9999.0

        return HealthMetric(
            name="network",
            value=value,
            unit="ms",
            status=status,
            threshold_warning=100.0,
            threshold_critical=500.0,
            timestamp=datetime.now(),
            message=message,
        )

    def check_processes(self) -> List[HealthMetric]:
        """Check critical processes."""
        metrics = []

        # Check trading processes
        critical_processes = [
            ("python3", "trading bot"),
            ("node", "dashboard"),
        ]

        for proc_name, desc in critical_processes:
            found = any(
                proc_name in p.name() or proc_name in " ".join(p.cmdline())
                for p in psutil.process_iter(["name", "cmdline"])
                if p.info["name"] and p.info["cmdline"]
            )

            status = HealthStatus.HEALTHY if found else HealthStatus.WARNING
            metrics.append(
                HealthMetric(
                    name=f"process_{desc.replace(' ', '_')}",
                    value=1.0 if found else 0.0,
                    unit="boolean",
                    status=status,
                    threshold_warning=0.5,
                    threshold_critical=0.0,
                    timestamp=datetime.now(),
                    message=f"{desc} {'running' if found else 'not found'}",
                )
            )

        return metrics

    def check_load(self) -> HealthMetric:
        """Check system load average."""
        load1, load5, load15 = os.getloadavg()
        cpu_count = psutil.cpu_count()
        load_percent = (load1 / cpu_count) * 100

        if load_percent >= 200:
            status = HealthStatus.CRITICAL
            message = f"Load critical: {load1:.2f}"
        elif load_percent >= 100:
            status = HealthStatus.WARNING
            message = f"Load high: {load1:.2f}"
        else:
            status = HealthStatus.HEALTHY
            message = f"Load normal: {load1:.2f}"

        return HealthMetric(
            name="load_average",
            value=load1,
            unit="1m",
            status=status,
            threshold_warning=cpu_count,
            threshold_critical=cpu_count * 2,
            timestamp=datetime.now(),
            message=message,
        )

    def check_all(self) -> HealthSnapshot:
        """Run complete health check."""
        self.logger.info("Running health check...")

        metrics = [
            self.check_cpu(),
            self.check_memory(),
            self.check_disk(),
            self.check_network(),
            self.check_load(),
        ]

        # Add process checks
        metrics.extend(self.check_processes())

        # Add custom monitors
        for name, monitor_fn in self.custom_monitors.items():
            try:
                value = monitor_fn()
                metrics.append(
                    HealthMetric(
                        name=name,
                        value=value,
                        unit="custom",
                        status=HealthStatus.HEALTHY,
                        threshold_warning=0,
                        threshold_critical=0,
                        timestamp=datetime.now(),
                        message=f"{name}: {value}",
                    )
                )
            except Exception as e:
                self.logger.error(f"Custom monitor {name} failed: {e}")

        # Determine overall status
        statuses = [m.status for m in metrics]
        if HealthStatus.CRITICAL in statuses:
            overall = HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            overall = HealthStatus.WARNING
        else:
            overall = HealthStatus.HEALTHY

        # Collect alerts
        alerts = [m.message for m in metrics if m.status != HealthStatus.HEALTHY]

        # Calculate uptime
        uptime = (datetime.now() - self.start_time).total_seconds()

        snapshot = HealthSnapshot(
            timestamp=datetime.now(), overall_status=overall, metrics=metrics, alerts=alerts, uptime_seconds=uptime
        )

        # Store history
        self.snapshots.append(snapshot)
        if len(self.snapshots) > self.max_history:
            self.snapshots.pop(0)

        # Trigger alerts for non-healthy metrics
        for metric in metrics:
            if metric.status != HealthStatus.HEALTHY:
                for handler in self.alert_handlers:
                    try:
                        handler(metric)
                    except Exception as e:
                        self.logger.error(f"Alert handler error: {e}")

        self.logger.info(f"Health check complete: {overall.value}")
        return snapshot

    async def monitor_loop(self, interval: int = 60):
        """
        Continuous monitoring loop.

        Args:
            interval: Check interval in seconds
        """
        self.logger.info(f"Starting health monitor loop (interval={interval}s)")

        while True:
            try:
                snapshot = self.check_all()

                # Log critical/warning
                if snapshot.overall_status == HealthStatus.CRITICAL:
                    self.logger.error(f"CRITICAL HEALTH: {snapshot.alerts}")
                elif snapshot.overall_status == HealthStatus.WARNING:
                    self.logger.warning(f"WARNING: {snapshot.alerts}")

                await asyncio.sleep(interval)

            except Exception as e:
                self.logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(interval)

    def get_latest(self) -> Optional[HealthSnapshot]:
        """Get latest snapshot."""
        return self.snapshots[-1] if self.snapshots else None

    def get_history(self, minutes: int = 60) -> List[HealthSnapshot]:
        """Get snapshots from last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [s for s in self.snapshots if s.timestamp >= cutoff]

    def get_metric_history(self, metric_name: str, minutes: int = 60) -> List[Dict]:
        """Get history for a specific metric."""
        history = self.get_history(minutes)
        results = []

        for snapshot in history:
            for metric in snapshot.metrics:
                if metric.name == metric_name:
                    results.append(
                        {
                            "timestamp": snapshot.timestamp.isoformat(),
                            "value": metric.value,
                            "status": metric.status.value,
                        }
                    )

        return results

    def get_summary(self) -> Dict:
        """Get health summary."""
        latest = self.get_latest()

        if not latest:
            return {"status": "unknown", "message": "No data"}

        healthy_count = sum(1 for m in latest.metrics if m.status == HealthStatus.HEALTHY)
        warning_count = sum(1 for m in latest.metrics if m.status == HealthStatus.WARNING)
        critical_count = sum(1 for m in latest.metrics if m.status == HealthStatus.CRITICAL)

        return {
            "status": latest.overall_status.value,
            "timestamp": latest.timestamp.isoformat(),
            "uptime_hours": latest.uptime_seconds / 3600,
            "metrics": {
                "total": len(latest.metrics),
                "healthy": healthy_count,
                "warning": warning_count,
                "critical": critical_count,
            },
            "alerts": latest.alerts,
        }

    def export_snapshot(self, filepath: str):
        """Export latest snapshot to JSON."""
        latest = self.get_latest()
        if latest:
            with open(filepath, "w") as f:
                json.dump(latest.to_dict(), f, indent=2)
            self.logger.info(f"Snapshot exported to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    monitor = HealthMonitor()

    # Add alert handler
    def on_alert(metric: HealthMetric):
        print(f"🚨 ALERT: {metric.message}")

    monitor.add_alert_handler(on_alert)

    # Run single check
    snapshot = monitor.check_all()

    print("System Health Monitor")
    print("=" * 50)
    print(f"Status: {snapshot.overall_status.value.upper()}")
    print(f"Uptime: {snapshot.uptime_seconds:.1f}s")
    print(f"Metrics: {len(snapshot.metrics)}")
    print()

    for metric in snapshot.metrics:
        icon = (
            "✅" if metric.status == HealthStatus.HEALTHY else "⚠️" if metric.status == HealthStatus.WARNING else "🚨"
        )
        print(f"{icon} {metric.name}: {metric.value:.1f}{metric.unit} - {metric.message}")

    if snapshot.alerts:
        print(f"\nAlerts: {len(snapshot.alerts)}")
        for alert in snapshot.alerts:
            print(f"  ⚠️ {alert}")

    print(f"\nSummary: {monitor.get_summary()}")
