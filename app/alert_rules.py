"""
Alert Rules Engine
Configurable rule-based alert system with trigger conditions.
"""
import json
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class Operator(Enum):
    """Comparison operators."""
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    CONTAINS = "contains"
    REGEX = "regex"
    CHANGED = "changed"
    INCREASED_BY = "increased_by"
    DECREASED_BY = "decreased_by"


class LogicGate(Enum):
    """Logic gates for combining conditions."""
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class RuleCondition:
    """Single rule condition."""
    field: str                  # Data field path (dot notation)
    operator: Operator
    value: Any = None           # Target value
    value_end: Any = None       # For BETWEEN operator
    duration_seconds: int = 0  # Duration threshold
    
    def evaluate(self, data: Dict, history: List[Dict] = None) -> bool:
        """Evaluate condition against data."""
        current = self._get_field_value(data, self.field)
        
        if self.operator == Operator.CHANGED and history:
            if not history:
                return False
            previous = self._get_field_value(history[-1], self.field)
            return current != previous
        
        if self.operator == Operator.INCREASED_BY and history:
            if not history:
                return False
            previous = self._get_field_value(history[-1], self.field)
            if current is None or previous is None:
                return False
            increase_pct = ((current - previous) / abs(previous)) * 100 if previous != 0 else 0
            return increase_pct >= self.value
        
        if self.operator == Operator.DECREASED_BY and history:
            if not history:
                return False
            previous = self._get_field_value(history[-1], self.field)
            if current is None or previous is None:
                return False
            decrease_pct = ((previous - current) / abs(previous)) * 100 if previous != 0 else 0
            return decrease_pct >= self.value
        
        if current is None:
            return False
        
        if self.operator == Operator.EQ:
            return current == self.value
        elif self.operator == Operator.NE:
            return current != self.value
        elif self.operator == Operator.GT:
            return current > self.value
        elif self.operator == Operator.GTE:
            return current >= self.value
        elif self.operator == Operator.LT:
            return current < self.value
        elif self.operator == Operator.LTE:
            return current <= self.value
        elif self.operator == Operator.BETWEEN:
            return self.value <= current <= self.value_end
        elif self.operator == Operator.CONTAINS:
            return str(self.value) in str(current)
        elif self.operator == Operator.REGEX:
            import re
            return bool(re.search(str(self.value), str(current)))
        
        return False
    
    def _get_field_value(self, data: Dict, field_path: str) -> Any:
        """Get value from nested dict using dot notation."""
        parts = field_path.split('.')
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value


@dataclass
class AlertRule:
    """Alert rule definition."""
    rule_id: str
    name: str
    description: str
    enabled: bool = True
    priority: str = "medium"     # critical, high, medium, low
    
    # Conditions
    conditions: List[RuleCondition] = field(default_factory=list)
    logic: LogicGate = LogicGate.AND
    
    # Actions
    actions: List[str] = field(default_factory=list)  # Action IDs
    channels: List[str] = field(default_factory=list)    # Alert channels
    
    # Rate limiting
    cooldown_seconds: int = 300    # Minimum time between alerts
    max_alerts_per_hour: int = 10
    
    # Metadata
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    # State
    last_alert_at: Optional[datetime] = None
    alert_count_hour: int = 0
    alert_count_total: int = 0
    
    def evaluate(self, data: Dict, history: List[Dict] = None) -> bool:
        """Evaluate all conditions."""
        if not self.enabled:
            return False
        
        if not self.conditions:
            return False
        
        results = [c.evaluate(data, history) for c in self.conditions]
        
        if self.logic == LogicGate.AND:
            return all(results)
        elif self.logic == LogicGate.OR:
            return any(results)
        elif self.logic == LogicGate.NOT:
            return not any(results)
        
        return False
    
    def can_alert(self) -> bool:
        """Check if rule can trigger alert (rate limits)."""
        now = datetime.now()
        
        # Check cooldown
        if self.last_alert_at:
            elapsed = (now - self.last_alert_at).total_seconds()
            if elapsed < self.cooldown_seconds:
                return False
        
        # Check hourly limit
        if self.alert_count_hour >= self.max_alerts_per_hour:
            return False
        
        return True
    
    def record_alert(self):
        """Record that alert was triggered."""
        self.last_alert_at = datetime.now()
        self.alert_count_total += 1
        
        # Check if we need to reset hourly count
        if self.last_alert_at and (datetime.now() - self.last_alert_at).total_seconds() > 3600:
            self.alert_count_hour = 0
        
        self.alert_count_hour += 1
    
    def to_dict(self) -> Dict:
        return {
            'rule_id': self.rule_id,
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'priority': self.priority,
            'logic': self.logic.value,
            'conditions': [
                {
                    'field': c.field,
                    'operator': c.operator.value,
                    'value': c.value,
                    'value_end': c.value_end,
                    'duration_seconds': c.duration_seconds,
                }
                for c in self.conditions
            ],
            'actions': self.actions,
            'channels': self.channels,
            'cooldown_seconds': self.cooldown_seconds,
            'max_alerts_per_hour': self.max_alerts_per_hour,
            'category': self.category,
            'tags': self.tags,
            'created_at': self.created_at.isoformat(),
            'stats': {
                'total_alerts': self.alert_count_total,
                'hourly_alerts': self.alert_count_hour,
                'last_alert': self.last_alert_at.isoformat() if self.last_alert_at else None,
            }
        }


@dataclass
class RuleAction:
    """Alert rule action."""
    action_id: str
    name: str
    action_type: str           # log, alert, webhook, command
    config: Dict = field(default_factory=dict)
    enabled: bool = True
    
    async def execute(self, context: Dict) -> bool:
        """Execute action."""
        if not self.enabled:
            return False
        
        if self.action_type == "log":
            logging.getLogger(__name__).warning(
                f"Rule {context.get('rule_id')}: {context.get('message')}"
            )
            return True
        
        elif self.action_type == "alert":
            # Placeholder for alert routing
            return True
        
        elif self.action_type == "webhook":
            # Placeholder for webhook
            return True
        
        elif self.action_type == "command":
            # Placeholder for command execution
            return True
        
        return False


class AlertRulesEngine:
    """
    Configurable alert rules engine.
    Evaluates rules against incoming data and triggers actions.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.rules: Dict[str, AlertRule] = {}
        self.actions: Dict[str, RuleAction] = {}
        self.data_history: List[Dict] = []
        self.max_history = 1000
        self.triggered_alerts: List[Dict] = []
        
        self.logger.info("AlertRulesEngine initialized")
    
    def add_rule(self, rule: AlertRule) -> bool:
        """Add alert rule."""
        self.rules[rule.rule_id] = rule
        self.logger.info(f"Added rule: {rule.rule_id} ({rule.name})")
        return True
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        """Enable rule."""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True
            return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Disable rule."""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
            return True
        return False
    
    def add_action(self, action: RuleAction) -> bool:
        """Add action."""
        self.actions[action.action_id] = action
        return True
    
    def evaluate_data(self, data: Dict) -> List[Dict]:
        """
        Evaluate all rules against data.
        
        Args:
            data: Data to evaluate
            
        Returns:
            List of triggered alerts
        """
        triggered = []
        
        # Store history
        self.data_history.append(data)
        if len(self.data_history) > self.max_history:
            self.data_history.pop(0)
        
        # Evaluate each rule
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Check conditions
            if rule.evaluate(data, self.data_history):
                # Check rate limits
                if rule.can_alert():
                    # Trigger alert
                    alert = {
                        'rule_id': rule.rule_id,
                        'rule_name': rule.name,
                        'priority': rule.priority,
                        'timestamp': datetime.now().isoformat(),
                        'data_snapshot': data,
                        'actions': rule.actions,
                        'channels': rule.channels,
                    }
                    
                    triggered.append(alert)
                    self.triggered_alerts.append(alert)
                    rule.record_alert()
                    
                    self.logger.warning(
                        f"Rule triggered: {rule.rule_id} ({rule.name})"
                    )
                else:
                    self.logger.info(f"Rule {rule.rule_id} rate limited")
        
        return triggered
    
    async def execute_actions(self, alert: Dict):
        """Execute actions for triggered alert."""
        for action_id in alert.get('actions', []):
            if action_id in self.actions:
                action = self.actions[action_id]
                try:
                    await action.execute(alert)
                except Exception as e:
                    self.logger.error(f"Action {action_id} failed: {e}")
    
    def get_rule_stats(self) -> Dict:
        """Get rule statistics."""
        total = len(self.rules)
        enabled = sum(1 for r in self.rules.values() if r.enabled)
        
        by_priority = {}
        for rule in self.rules.values():
            p = rule.priority
            by_priority[p] = by_priority.get(p, 0) + 1
        
        total_alerts = sum(r.alert_count_total for r in self.rules.values())
        
        return {
            'total_rules': total,
            'enabled': enabled,
            'disabled': total - enabled,
            'by_priority': by_priority,
            'total_alerts_triggered': total_alerts,
            'recent_alerts': len([a for a in self.triggered_alerts
                                 if datetime.fromisoformat(a['timestamp']) > datetime.now() - timedelta(hours=24)]),
        }
    
    def export_rules(self, filepath: str):
        """Export rules to JSON."""
        rules_data = {rid: rule.to_dict() for rid, rule in self.rules.items()}
        
        with open(filepath, 'w') as f:
            json.dump(rules_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Rules exported to {filepath}")
    
    def import_rules(self, filepath: str):
        """Import rules from JSON."""
        with open(filepath, 'r') as f:
            rules_data = json.load(f)
        
        for rid, data in rules_data.items():
            conditions = []
            for c in data.get('conditions', []):
                conditions.append(RuleCondition(
                    field=c['field'],
                    operator=Operator(c['operator']),
                    value=c.get('value'),
                    value_end=c.get('value_end'),
                    duration_seconds=c.get('duration_seconds', 0)
                ))
            
            rule = AlertRule(
                rule_id=rid,
                name=data['name'],
                description=data.get('description', ''),
                enabled=data.get('enabled', True),
                priority=data.get('priority', 'medium'),
                conditions=conditions,
                logic=LogicGate(data.get('logic', 'and')),
                actions=data.get('actions', []),
                channels=data.get('channels', []),
                cooldown_seconds=data.get('cooldown_seconds', 300),
                max_alerts_per_hour=data.get('max_alerts_per_hour', 10),
                category=data.get('category', 'general'),
                tags=data.get('tags', [])
            )
            
            self.add_rule(rule)
        
        self.logger.info(f"Rules imported from {filepath}")


class RuleTemplates:
    """Pre-built alert rule templates."""
    
    @staticmethod
    def price_drop_alert(symbol: str, drop_percent: float = 5.0) -> AlertRule:
        """Alert when price drops by specified percentage."""
        return AlertRule(
            rule_id=f"price_drop_{symbol.lower()}",
            name=f"{symbol} Price Drop Alert",
            description=f"Alert when {symbol} drops by {drop_percent}%",
            priority="high",
            conditions=[
                RuleCondition(
                    field="price.change_percent",
                    operator=Operator.DECREASED_BY,
                    value=drop_percent
                )
            ],
            channels=["console", "log"],
            cooldown_seconds=60,
            category="price",
            tags=["price", "drop", symbol]
        )
    
    @staticmethod
    def high_volume_alert(symbol: str, volume_multiplier: float = 3.0) -> AlertRule:
        """Alert on unusually high volume."""
        return AlertRule(
            rule_id=f"high_volume_{symbol.lower()}",
            name=f"{symbol} High Volume Alert",
            description=f"Alert when {symbol} volume is {volume_multiplier}x average",
            priority="medium",
            conditions=[
                RuleCondition(
                    field="volume.ratio",
                    operator=Operator.GT,
                    value=volume_multiplier
                )
            ],
            channels=["console"],
            cooldown_seconds=300,
            category="volume",
            tags=["volume", symbol]
        )
    
    @staticmethod
    def balance_low_alert(threshold: float = 100.0) -> AlertRule:
        """Alert when account balance is low."""
        return AlertRule(
            rule_id="balance_low",
            name="Low Balance Alert",
            description=f"Alert when balance drops below ${threshold}",
            priority="critical",
            conditions=[
                RuleCondition(
                    field="account.balance",
                    operator=Operator.LT,
                    value=threshold
                )
            ],
            channels=["console", "log"],
            cooldown_seconds=600,
            category="account",
            tags=["balance", "risk"]
        )
    
    @staticmethod
    def order_failed_alert() -> AlertRule:
        """Alert on order execution failure."""
        return AlertRule(
            rule_id="order_failed",
            name="Order Failed Alert",
            description="Alert when order execution fails",
            priority="high",
            conditions=[
                RuleCondition(
                    field="order.status",
                    operator=Operator.EQ,
                    value="failed"
                )
            ],
            channels=["console", "log"],
            cooldown_seconds=30,
            category="execution",
            tags=["order", "failure"]
        )


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    engine = AlertRulesEngine()
    
    # Add rules from templates
    engine.add_rule(RuleTemplates.price_drop_alert("BTCUSDT", 5.0))
    engine.add_rule(RuleTemplates.high_volume_alert("BTCUSDT", 3.0))
    engine.add_rule(RuleTemplates.balance_low_alert(500.0))
    engine.add_rule(RuleTemplates.order_failed_alert())
    
    # Test data
    test_data = {
        'price': {'current': 45000, 'change_percent': -6.5},
        'volume': {'ratio': 4.2, 'current': 1000000},
        'account': {'balance': 450},
        'order': {'status': 'filled'}
    }
    
    # Evaluate
    triggered = engine.evaluate_data(test_data)
    
    print("Alert Rules Engine Demo")
    print("=" * 50)
    print(f"Rules: {len(engine.rules)}")
    print(f"Triggered: {len(triggered)}")
    
    for alert in triggered:
        print(f"\n🚨 {alert['rule_name']}")
        print(f"   Priority: {alert['priority']}")
        print(f"   Channels: {alert['channels']}")
    
    print(f"\nStats: {engine.get_rule_stats()}")
