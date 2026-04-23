"""
Alert History & Analytics
Tracks, analyzes, and reports on alert patterns and effectiveness.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict


class AlertResolution(Enum):
    """How an alert was resolved."""

    ACKNOWLEDGED = "acknowledged"
    AUTO_RESOLVED = "auto_resolved"
    ESCALATED = "escalated"
    IGNORED = "ignored"
    FALSE_POSITIVE = "false_positive"


@dataclass
class AlertHistory:
    """Complete history entry for a single alert."""

    alert_id: str
    rule_id: str
    rule_name: str
    priority: str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    resolution: AlertResolution = AlertResolution.ACKNOWLEDGED
    acknowledged_by: str = ""
    response_time_seconds: float = 0.0
    was_actionable: bool = True
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "priority": self.priority,
            "triggered_at": self.triggered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution.value,
            "acknowledged_by": self.acknowledged_by,
            "response_time_seconds": self.response_time_seconds,
            "was_actionable": self.was_actionable,
        }


class AlertAnalytics:
    """
    Analytics engine for alert history.
    Provides insights into alert patterns, effectiveness, and system health.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alert_history: List[AlertHistory] = []
        self.max_history = 5000

        self.logger.info("AlertAnalytics initialized")

    def record_alert(self, history: AlertHistory):
        """Record an alert occurrence."""
        self.alert_history.append(history)

        # Maintain max history
        if len(self.alert_history) > self.max_history:
            self.alert_history.pop(0)

        self.logger.info(f"Alert recorded: {history.alert_id}")

    def resolve_alert(
        self, alert_id: str, resolution: AlertResolution, acknowledged_by: str = "", was_actionable: bool = True
    ):
        """Mark alert as resolved."""
        for alert in self.alert_history:
            if alert.alert_id == alert_id and not alert.resolved_at:
                alert.resolved_at = datetime.now()
                alert.resolution = resolution
                alert.acknowledged_by = acknowledged_by
                alert.was_actionable = was_actionable

                # Calculate response time
                alert.response_time_seconds = (alert.resolved_at - alert.triggered_at).total_seconds()

                self.logger.info(
                    f"Alert resolved: {alert_id} ({resolution.value}) " f"in {alert.response_time_seconds:.1f}s"
                )
                return True

        return False

    def get_alert_stats(self, rule_id: Optional[str] = None, days: int = 7) -> Dict:
        """
        Get alert statistics.

        Args:
            rule_id: Filter by rule
            days: Lookback period

        Returns:
            Alert statistics
        """
        cutoff = datetime.now() - timedelta(days=days)
        alerts = [a for a in self.alert_history if a.triggered_at >= cutoff]

        if rule_id:
            alerts = [a for a in alerts if a.rule_id == rule_id]

        if not alerts:
            return {"total": 0}

        total = len(alerts)
        resolved = [a for a in alerts if a.resolved_at]
        actionable = [a for a in alerts if a.was_actionable]

        # Response times
        response_times = [a.response_time_seconds for a in resolved if a.response_time_seconds > 0]
        avg_response = sum(response_times) / len(response_times) if response_times else 0

        # By priority
        by_priority = defaultdict(int)
        for a in alerts:
            by_priority[a.priority] += 1

        # By resolution
        by_resolution = defaultdict(int)
        for a in resolved:
            by_resolution[a.resolution.value] += 1

        # By rule
        by_rule = defaultdict(lambda: {"count": 0, "resolved": 0})
        for a in alerts:
            by_rule[a.rule_id]["count"] += 1
            if a.resolved_at:
                by_rule[a.rule_id]["resolved"] += 1

        # Noise rate (alerts per day)
        noise_rate = total / days

        return {
            "period_days": days,
            "total_alerts": total,
            "resolved": len(resolved),
            "resolution_rate": len(resolved) / total * 100,
            "actionable_rate": len(actionable) / total * 100 if total else 0,
            "avg_response_time_seconds": avg_response,
            "by_priority": dict(by_priority),
            "by_resolution": dict(by_resolution),
            "by_rule": dict(by_rule),
            "noise_rate_per_day": noise_rate,
            "most_active_rule": max(by_rule.items(), key=lambda x: x[1]["count"])[0] if by_rule else None,
        }

    def get_alert_trends(self, days: int = 7) -> List[Dict]:
        """
        Get daily alert trend.

        Returns:
            List of daily alert counts
        """
        cutoff = datetime.now() - timedelta(days=days)
        alerts = [a for a in self.alert_history if a.triggered_at >= cutoff]

        daily = defaultdict(lambda: {"count": 0, "resolved": 0, "avg_response": []})

        for alert in alerts:
            day = alert.triggered_at.strftime("%Y-%m-%d")
            daily[day]["count"] += 1
            if alert.resolved_at:
                daily[day]["resolved"] += 1
                if alert.response_time_seconds > 0:
                    daily[day]["avg_response"].append(alert.response_time_seconds)

        # Format results
        results = []
        for day, data in sorted(daily.items()):
            avg_resp = sum(data["avg_response"]) / len(data["avg_response"]) if data["avg_response"] else 0
            results.append(
                {
                    "date": day,
                    "total": data["count"],
                    "resolved": data["resolved"],
                    "resolution_rate": data["resolved"] / data["count"] * 100 if data["count"] else 0,
                    "avg_response_time": avg_resp,
                }
            )

        return results

    def get_rule_effectiveness(self, days: int = 30) -> Dict[str, Dict]:
        """
        Measure rule effectiveness (actionable vs noise).

        Returns:
            Effectiveness metrics per rule
        """
        cutoff = datetime.now() - timedelta(days=days)
        alerts = [a for a in self.alert_history if a.triggered_at >= cutoff]

        rule_stats = defaultdict(
            lambda: {
                "total": 0,
                "actionable": 0,
                "false_positives": 0,
                "avg_response_time": [],
                "resolution_rate": 0,
            }
        )

        for alert in alerts:
            stats = rule_stats[alert.rule_id]
            stats["total"] += 1

            if alert.was_actionable:
                stats["actionable"] += 1

            if alert.resolution == AlertResolution.FALSE_POSITIVE:
                stats["false_positives"] += 1

            if alert.resolved_at and alert.response_time_seconds > 0:
                stats["avg_response_time"].append(alert.response_time_seconds)

        # Calculate effectiveness
        results = {}
        for rule_id, stats in rule_stats.items():
            total = stats["total"]
            results[rule_id] = {
                "total_alerts": total,
                "actionable_count": stats["actionable"],
                "actionable_rate": stats["actionable"] / total * 100 if total else 0,
                "false_positives": stats["false_positives"],
                "false_positive_rate": stats["false_positives"] / total * 100 if total else 0,
                "avg_response_time": (
                    sum(stats["avg_response_time"]) / len(stats["avg_response_time"])
                    if stats["avg_response_time"]
                    else 0
                ),
                "effectiveness_score": (stats["actionable"] - stats["false_positives"]) / total * 100 if total else 0,
            }

        return results

    def get_noise_report(self, days: int = 7) -> Dict:
        """
        Identify noisy rules (high frequency, low value).

        Returns:
            Noise analysis
        """
        cutoff = datetime.now() - timedelta(days=days)
        alerts = [a for a in self.alert_history if a.triggered_at >= cutoff]

        rule_counts = defaultdict(list)
        for a in alerts:
            rule_counts[a.rule_id].append(a)

        noise_rules = []
        for rule_id, rule_alerts in rule_counts.items():
            total = len(rule_alerts)
            actionable = sum(1 for a in rule_alerts if a.was_actionable)
            fps = sum(1 for a in rule_alerts if a.resolution == AlertResolution.FALSE_POSITIVE)

            # Noise score: high frequency + low actionable rate
            noise_score = total * (1 - actionable / total) if total else 0

            if noise_score > 5:  # Threshold
                noise_rules.append(
                    {
                        "rule_id": rule_id,
                        "alert_count": total,
                        "actionable_rate": actionable / total * 100,
                        "false_positive_rate": fps / total * 100,
                        "noise_score": noise_score,
                        "recommendation": "Consider tuning thresholds or disabling" if noise_score > 20 else "Monitor",
                    }
                )

        noise_rules.sort(key=lambda x: x["noise_score"], reverse=True)

        return {
            "total_rules_analyzed": len(rule_counts),
            "noisy_rules": len(noise_rules),
            "top_offenders": noise_rules[:5],
            "recommendations": (
                [
                    "Adjust thresholds for noisy rules",
                    "Add suppression for known patterns",
                    "Review false positive causes",
                ]
                if noise_rules
                else ["No noisy rules detected"]
            ),
        }

    def export_history(self, filepath: str, days: int = 30):
        """Export alert history to JSON."""
        cutoff = datetime.now() - timedelta(days=days)
        alerts = [a.to_dict() for a in self.alert_history if a.triggered_at >= cutoff]

        data = {
            "exported_at": datetime.now().isoformat(),
            "period_days": days,
            "total_alerts": len(alerts),
            "alerts": alerts,
            "summary": self.get_alert_stats(days=days),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Alert history exported to {filepath}")

    def generate_report(self, days: int = 7) -> str:
        """Generate human-readable alert report."""
        stats = self.get_alert_stats(days=days)
        trends = self.get_alert_trends(days=days)
        effectiveness = self.get_rule_effectiveness(days=days)
        noise = self.get_noise_report(days=days)

        report = f"""
📊 Alert Analytics Report
{'=' * 50}
Period: Last {days} days
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

📈 Summary
• Total Alerts: {stats.get('total_alerts', 0)}
• Resolution Rate: {stats.get('resolution_rate', 0):.1f}%
• Avg Response Time: {stats.get('avg_response_time_seconds', 0):.1f}s
• Noise Rate: {stats.get('noise_rate_per_day', 0):.1f}/day

📊 By Priority
{self._format_dict(stats.get('by_priority', {}))}

📈 Daily Trends
{self._format_trends(trends)}

🎯 Rule Effectiveness (Top 5)
{self._format_effectiveness(effectiveness)}

⚠️ Noise Analysis
• Noisy Rules: {noise.get('noisy_rules', 0)}
{self._format_noise(noise.get('top_offenders', []))}

💡 Recommendations
{chr(10).join('• ' + r for r in noise.get('recommendations', []))}
"""

        return report

    def _format_dict(self, d: Dict) -> str:
        """Format dict for display."""
        if not d:
            return "  No data"
        return "\n".join(f"  • {k}: {v}" for k, v in d.items())

    def _format_trends(self, trends: List[Dict]) -> str:
        """Format trends for display."""
        if not trends:
            return "  No trend data"

        lines = []
        for t in trends[-7:]:  # Last 7 days
            lines.append(f"  {t['date']}: {t['total']} alerts ({t['resolution_rate']:.0f}% resolved)")
        return "\n".join(lines)

    def _format_effectiveness(self, eff: Dict) -> str:
        """Format effectiveness for display."""
        if not eff:
            return "  No data"

        lines = []
        for rule_id, stats in list(eff.items())[:5]:
            score = stats["effectiveness_score"]
            icon = "✅" if score > 50 else "⚠️" if score > 0 else "❌"
            lines.append(f"  {icon} {rule_id}: {score:.0f}% effective ({stats['total_alerts']} alerts)")
        return "\n".join(lines)

    def _format_noise(self, offenders: List[Dict]) -> str:
        """Format noise offenders."""
        if not offenders:
            return "  No noisy rules"

        lines = []
        for o in offenders[:3]:
            lines.append(f"  • {o['rule_id']}: score={o['noise_score']:.1f}, {o['actionable_rate']:.0f}% actionable")
        return "\n".join(lines)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    analytics = AlertAnalytics()

    # Add sample alerts
    for i in range(10):
        history = AlertHistory(
            alert_id=f"ALT_{i:03d}",
            rule_id="price_drop_btc",
            rule_name="BTC Price Drop",
            priority="high",
            triggered_at=datetime.now() - timedelta(hours=i),
            was_actionable=i % 3 != 0,  # Some false positives
        )

        analytics.record_alert(history)

        # Resolve most
        if i < 7:
            analytics.resolve_alert(
                history.alert_id,
                AlertResolution.ACKNOWLEDGED if i % 3 != 0 else AlertResolution.FALSE_POSITIVE,
                acknowledged_by="system",
                was_actionable=i % 3 != 0,
            )

    # Generate report
    print(analytics.generate_report(days=1))
