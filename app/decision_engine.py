"""
Hybrid Automated Decision Rule Engine
IF-THEN logic with auto/ask/skip decision modes.
"""
import json
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class DecisionMode(Enum):
    """Decision execution modes."""
    AUTO = "auto"           # Execute automatically
    ASK = "ask"             # Ask for human confirmation
    SKIP = "skip"           # Skip this rule
    BLOCK = "block"         # Block execution


class RuleCondition(Enum):
    """Types of rule conditions."""
    EQ = "eq"               # Equal
    NE = "ne"               # Not equal
    GT = "gt"               # Greater than
    GTE = "gte"             # Greater than or equal
    LT = "lt"               # Less than
    LTE = "lte"             # Less than or equal
    IN = "in"               # In list
    CONTAINS = "contains"   # Contains substring
    EXISTS = "exists"       # Key exists
    CUSTOM = "custom"       # Custom function


@dataclass
class RuleConditionConfig:
    """Single condition configuration."""
    field: str              # Field to check
    operator: RuleCondition
    value: Any              # Value to compare
    weight: float = 1.0     # Condition weight
    
    def evaluate(self, data: Dict) -> bool:
        """Evaluate condition against data."""
        # Get field value
        if '.' in self.field:
            # Nested field access
            parts = self.field.split('.')
            value = data
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return False
        else:
            value = data.get(self.field)
        
        # Check exists
        if self.operator == RuleCondition.EXISTS:
            return value is not None
        
        # Handle None
        if value is None:
            return False
        
        # Evaluate based on operator
        if self.operator == RuleCondition.EQ:
            return value == self.value
        elif self.operator == RuleCondition.NE:
            return value != self.value
        elif self.operator == RuleCondition.GT:
            return value > self.value
        elif self.operator == RuleCondition.GTE:
            return value >= self.value
        elif self.operator == RuleCondition.LT:
            return value < self.value
        elif self.operator == RuleCondition.LTE:
            return value <= self.value
        elif self.operator == RuleCondition.IN:
            return value in self.value if isinstance(self.value, (list, tuple)) else False
        elif self.operator == RuleCondition.CONTAINS:
            return self.value in str(value)
        
        return False


@dataclass
class DecisionRule:
    """Single decision rule."""
    rule_id: str
    name: str
    description: str
    priority: int = 100   # Lower = higher priority
    
    # Conditions (ALL must match)
    conditions: List[RuleConditionConfig] = field(default_factory=list)
    
    # Decision
    mode: DecisionMode = DecisionMode.AUTO
    action: str = ""        # Action to execute
    action_params: Dict = field(default_factory=dict)
    
    # Metadata
    enabled: bool = True
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    
    def evaluate(self, data: Dict) -> bool:
        """Evaluate if all conditions match."""
        if not self.enabled:
            return False
        
        if not self.conditions:
            return True  # No conditions = always match
        
        return all(condition.evaluate(data) for condition in self.conditions)
    
    def to_dict(self) -> Dict:
        return {
            'rule_id': self.rule_id,
            'name': self.name,
            'description': self.description,
            'priority': self.priority,
            'mode': self.mode.value,
            'action': self.action,
            'action_params': self.action_params,
            'enabled': self.enabled,
            'category': self.category,
            'tags': self.tags,
        }


@dataclass
class DecisionResult:
    """Result of decision evaluation."""
    decision_id: str
    rule_id: str
    rule_name: str
    mode: DecisionMode
    matched: bool
    executed: bool
    action: str
    params: Dict
    timestamp: datetime
    context: Dict
    requires_human: bool = False
    human_question: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'decision_id': self.decision_id,
            'rule_id': self.rule_id,
            'rule_name': self.rule_name,
            'mode': self.mode.value,
            'matched': self.matched,
            'executed': self.executed,
            'action': self.action,
            'params': self.params,
            'timestamp': self.timestamp.isoformat(),
            'requires_human': self.requires_human,
            'human_question': self.human_question,
        }


class DecisionEngine:
    """
    Hybrid automated decision rule engine.
    Evaluates IF-THEN rules with multiple decision modes.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.rules: Dict[str, DecisionRule] = {}
        self.action_handlers: Dict[str, Callable] = {}
        self.decision_history: List[DecisionResult] = []
        
        # Register default actions
        self.register_action("log", self._action_log)
        self.register_action("alert", self._action_alert)
        self.register_action("block", self._action_block)
        self.register_action("notify", self._action_notify)
        
        self.logger.info("DecisionEngine initialized")
    
    def add_rule(self, rule: DecisionRule) -> bool:
        """
        Add a decision rule.
        
        Args:
            rule: DecisionRule to add
            
        Returns:
            True if added successfully
        """
        self.rules[rule.rule_id] = rule
        self.logger.info(f"Added rule: {rule.rule_id} ({rule.name})")
        return True
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule."""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True
            return True
        return False
    
    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule."""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
            return True
        return False
    
    def register_action(self, action_name: str, handler: Callable):
        """
        Register an action handler.
        
        Args:
            action_name: Name of the action
            handler: Function to execute
        """
        self.action_handlers[action_name] = handler
        self.logger.info(f"Registered action handler: {action_name}")
    
    def evaluate(self, context: Dict, decision_id: Optional[str] = None) -> List[DecisionResult]:
        """
        Evaluate all rules against context.
        
        Args:
            context: Data to evaluate rules against
            decision_id: Optional decision identifier
            
        Returns:
            List of DecisionResult
        """
        decision_id = decision_id or f"dec_{datetime.now().timestamp()}"
        results = []
        
        # Sort rules by priority
        sorted_rules = sorted(self.rules.values(), key=lambda r: r.priority)
        
        for rule in sorted_rules:
            # Evaluate conditions
            matched = rule.evaluate(context)
            
            if not matched:
                continue
            
            self.logger.info(f"Rule matched: {rule.rule_id} ({rule.name})")
            
            # Create result
            result = DecisionResult(
                decision_id=decision_id,
                rule_id=rule.rule_id,
                rule_name=rule.name,
                mode=rule.mode,
                matched=True,
                executed=False,
                action=rule.action,
                params=rule.action_params.copy(),
                timestamp=datetime.now(),
                context=context.copy()
            )
            
            # Handle decision mode
            if rule.mode == DecisionMode.AUTO:
                # Execute automatically
                self._execute_action(result)
                result.executed = True
                
            elif rule.mode == DecisionMode.ASK:
                # Requires human confirmation
                result.requires_human = True
                result.human_question = self._generate_question(rule, context)
                self.logger.info(f"ASK decision: {result.human_question}")
                
            elif rule.mode == DecisionMode.SKIP:
                # Skip execution
                result.executed = False
                self.logger.info(f"SKIPPED: {rule.name}")
                
            elif rule.mode == DecisionMode.BLOCK:
                # Block further execution
                result.executed = False
                self.logger.warning(f"BLOCKED by rule: {rule.name}")
                results.append(result)
                break  # Stop processing further rules
            
            results.append(result)
            self.decision_history.append(result)
        
        return results
    
    def _execute_action(self, result: DecisionResult):
        """Execute the action for a decision."""
        action_name = result.action
        
        if action_name in self.action_handlers:
            try:
                self.action_handlers[action_name](result)
                self.logger.info(f"Executed action: {action_name}")
            except Exception as e:
                self.logger.error(f"Action execution failed: {e}")
        else:
            self.logger.warning(f"No handler for action: {action_name}")
    
    def confirm_decision(self, decision_id: str, approved: bool) -> Optional[DecisionResult]:
        """
        Confirm an ASK decision.
        
        Args:
            decision_id: Decision to confirm
            approved: True to approve, False to reject
            
        Returns:
            Updated DecisionResult or None
        """
        # Find the decision
        for result in self.decision_history:
            if result.decision_id == decision_id and result.requires_human:
                if approved:
                    result.mode = DecisionMode.AUTO
                    self._execute_action(result)
                    result.executed = True
                    result.requires_human = False
                    self.logger.info(f"Decision {decision_id} APPROVED")
                else:
                    result.mode = DecisionMode.SKIP
                    result.executed = False
                    result.requires_human = False
                    self.logger.info(f"Decision {decision_id} REJECTED")
                
                return result
        
        return None
    
    def _generate_question(self, rule: DecisionRule, context: Dict) -> str:
        """Generate human-readable question for ASK mode."""
        return (
            f"Rule '{rule.name}' matched. "
            f"Action: {rule.action} with params {rule.action_params}. "
            f"Approve execution?"
        )
    
    # Default action handlers
    def _action_log(self, result: DecisionResult):
        """Log action."""
        self.logger.info(f"[LOG] Rule {result.rule_id}: {result.rule_name}")
    
    def _action_alert(self, result: DecisionResult):
        """Alert action."""
        self.logger.warning(f"[ALERT] Rule triggered: {result.rule_name}")
    
    def _action_block(self, result: DecisionResult):
        """Block action."""
        self.logger.error(f"[BLOCK] Execution blocked by: {result.rule_name}")
    
    def _action_notify(self, result: DecisionResult):
        """Notify action."""
        self.logger.info(f"[NOTIFY] Notification from rule: {result.rule_name}")
    
    def get_rule_stats(self) -> Dict:
        """Get rule statistics."""
        total = len(self.rules)
        enabled = sum(1 for r in self.rules.values() if r.enabled)
        
        by_mode = {}
        for rule in self.rules.values():
            mode = rule.mode.value
            by_mode[mode] = by_mode.get(mode, 0) + 1
        
        return {
            'total_rules': total,
            'enabled': enabled,
            'disabled': total - enabled,
            'by_mode': by_mode,
        }
    
    def get_decision_history(self, 
                            rule_id: Optional[str] = None,
                            limit: int = 100) -> List[DecisionResult]:
        """Get decision history."""
        history = self.decision_history[-limit:]
        
        if rule_id:
            history = [d for d in history if d.rule_id == rule_id]
        
        return history
    
    def export_rules(self, filepath: str):
        """Export rules to JSON file."""
        rules_data = {rid: rule.to_dict() for rid, rule in self.rules.items()}
        
        with open(filepath, 'w') as f:
            json.dump(rules_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Rules exported to {filepath}")
    
    def import_rules(self, filepath: str):
        """Import rules from JSON file."""
        with open(filepath, 'r') as f:
            rules_data = json.load(f)
        
        for rid, data in rules_data.items():
            # Parse conditions
            conditions = []
            for cond_data in data.get('conditions', []):
                conditions.append(RuleConditionConfig(
                    field=cond_data['field'],
                    operator=RuleCondition(cond_data['operator']),
                    value=cond_data['value'],
                    weight=cond_data.get('weight', 1.0)
                ))
            
            rule = DecisionRule(
                rule_id=rid,
                name=data['name'],
                description=data.get('description', ''),
                priority=data.get('priority', 100),
                conditions=conditions,
                mode=DecisionMode(data.get('mode', 'auto')),
                action=data.get('action', ''),
                action_params=data.get('action_params', {}),
                enabled=data.get('enabled', True),
                category=data.get('category', 'general'),
                tags=data.get('tags', [])
            )
            
            self.add_rule(rule)
        
        self.logger.info(f"Rules imported from {filepath}")


# Pre-built rule templates
class RuleTemplates:
    """Common rule templates."""
    
    @staticmethod
    def high_confidence_auto_trade(strategy: str = "", threshold: float = 80.0) -> DecisionRule:
        """Auto-execute high confidence signals."""
        return DecisionRule(
            rule_id="auto_high_confidence",
            name="Auto Trade High Confidence",
            description=f"Auto-execute {strategy} signals with confidence >= {threshold}%",
            priority=10,
            conditions=[
                RuleConditionConfig("signal.confidence", RuleCondition.GTE, threshold),
                RuleConditionConfig("signal.strength", RuleCondition.IN, ["strong", "moderate"]),
            ],
            mode=DecisionMode.AUTO,
            action="execute_trade",
            tags=["auto", "high_confidence"]
        )
    
    @staticmethod
    def large_position_ask(position_value: float = 1000.0) -> DecisionRule:
        """Ask for large positions."""
        return DecisionRule(
            rule_id="ask_large_position",
            name="Ask for Large Positions",
            description=f"Ask for confirmation when position value >= ${position_value}",
            priority=20,
            conditions=[
                RuleConditionConfig("position.value", RuleCondition.GTE, position_value),
            ],
            mode=DecisionMode.ASK,
            action="confirm_trade",
            tags=["ask", "risk_management"]
        )
    
    @staticmethod
    def high_volatility_skip(volatility_threshold: float = 5.0) -> DecisionRule:
        """Skip trades in high volatility."""
        return DecisionRule(
            rule_id="skip_high_volatility",
            name="Skip High Volatility",
            description=f"Skip trades when volatility >= {volatility_threshold}%",
            priority=5,
            conditions=[
                RuleConditionConfig("market.volatility", RuleCondition.GTE, volatility_threshold),
            ],
            mode=DecisionMode.SKIP,
            action="skip_trade",
            tags=["skip", "risk_management"]
        )
    
    @staticmethod
    def low_balance_block(min_balance: float = 100.0) -> DecisionRule:
        """Block trades when balance is low."""
        return DecisionRule(
            rule_id="block_low_balance",
            name="Block Low Balance",
            description=f"Block trades when balance < ${min_balance}",
            priority=1,
            conditions=[
                RuleConditionConfig("account.balance", RuleCondition.LT, min_balance),
            ],
            mode=DecisionMode.BLOCK,
            action="block_trade",
            tags=["block", "safety"]
        )


if __name__ == "__main__":
    # Example usage
    engine = DecisionEngine()
    
    # Add rules from templates
    engine.add_rule(RuleTemplates.high_confidence_auto_trade("BTC", 75))
    engine.add_rule(RuleTemplates.large_position_ask(500))
    engine.add_rule(RuleTemplates.high_volatility_skip(3.0))
    engine.add_rule(RuleTemplates.low_balance_block(50))
    
    # Test context
    context = {
        "signal": {
            "confidence": 85,
            "strength": "strong",
            "symbol": "BTC/USDT"
        },
        "position": {
            "value": 750
        },
        "market": {
            "volatility": 2.5
        },
        "account": {
            "balance": 1000
        }
    }
    
    # Evaluate
    results = engine.evaluate(context, "test_decision_001")
    
    print("Decision Engine Example")
    print("=" * 50)
    for result in results:
        print(f"\nRule: {result.rule_name} ({result.rule_id})")
        print(f"Mode: {result.mode.value.upper()}")
        print(f"Action: {result.action}")
        print(f"Executed: {result.executed}")
        if result.requires_human:
            print(f"❓ Human Required: {result.human_question}")
    
    print(f"\nRule Stats: {engine.get_rule_stats()}")
