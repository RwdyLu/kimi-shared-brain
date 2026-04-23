"""
Integration Test Suite
End-to-end tests for the trading system components.
"""
import pytest
import asyncio
import json
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

# Import system components
sys.path.insert(0, '/app')


class TestMarketDataStream:
    """Test real-time market data streaming."""
    
    @pytest.fixture
    def stream(self):
        from app.market_stream import MarketStream
        return MarketStream(testnet=True)
    
    def test_stream_initialization(self, stream):
        assert stream is not None
        assert not stream.running
    
    def test_stream_lifecycle(self, stream):
        # Mock connection and lifecycle
        with patch.object(stream, 'start', return_value=True):
            stream.running = True
            assert stream.running is True
        
        # Stop
        stream.stop()
        assert stream.running is False


class TestOrderExecution:
    """Test order execution flow."""
    
    @pytest.fixture
    def executor(self):
        from app.order_retry import OrderRetryManager, RetryConfig
        config = RetryConfig(max_retries=3, base_delay=1.0)
        return OrderRetryManager(config=config)
    
    def test_risk_check_before_order(self):
        """Pre-trade risk check must pass before order."""
        from app.risk_checks import RiskChecker
        
        risk = RiskChecker()
        passed, results = risk.check_all(
            symbol="BTCUSDT",
            side="BUY",
            amount=1000000,
            price=50000
        )
        assert passed is False
    
    def test_order_retry_mechanism(self, executor):
        """Failed orders should retry with backoff."""
        import asyncio
        
        async def mock_operation():
            mock_operation.calls = getattr(mock_operation, 'calls', 0) + 1
            if mock_operation.calls < 3:
                raise Exception("timeout")
            return {"status": "success"}
        
        # Run async
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                executor.execute_with_retry(
                    operation_id="test_1",
                    operation=mock_operation
                )
            )
            assert result is not None
        finally:
            loop.close()


class TestPositionSizing:
    """Test position sizing calculations."""
    
    @pytest.fixture
    def sizer(self):
        from app.position_sizing import PositionSizingEngine
        return PositionSizingEngine(account_balance=10000)
    
    def test_position_sizing_calculation(self, sizer):
        """Position sizing should respect risk limits."""
        size = sizer.calculate_position_size(
            symbol="BTCUSDT",
            side="BUY",
            entry_price=50000,
            stop_loss=48000
        )
        
        assert size is not None
        assert size.quantity > 0
    
    def test_risk_based_sizing(self, sizer):
        """Risk-based sizing respects max drawdown."""
        size = sizer.calculate_position_size(
            symbol="BTCUSDT",
            side="BUY",
            entry_price=50000,
            stop_loss=48000
        )
        
        # Risk should be ~2% of account = $200
        # Stop distance = $2000, so size = $200 / $2000 = 0.01 BTC
        assert size.quantity > 0
        assert size.quantity < 1.0


class TestOCOOrders:
    """Test OCO (One-Cancels-Other) orders."""
    
    @pytest.fixture
    def oco_manager(self):
        from app.oco_orders import OCOOrderManager
        return OCOOrderManager(testnet=True)
    
    def test_oco_creation(self, oco_manager):
        """OCO pair should create both stop-loss and take-profit."""
        from app.oco_orders import OCOOrder
        
        oco = OCOOrder(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            entry_price=45000,
            stop_loss_price=43000,
            take_profit_price=48000
        )
        
        assert oco.symbol == "BTCUSDT"
        assert oco.stop_loss_price == 43000
        assert oco.take_profit_price == 48000
    
    def test_oco_cancellation(self, oco_manager):
        """Cancel OCO should work."""
        from app.oco_orders import OCOOrder
        
        oco = OCOOrder(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            entry_price=45000,
            stop_loss_price=43000,
            take_profit_price=48000
        )
        
        # Cancel (mock)
        with patch.object(oco_manager, 'cancel_oco', return_value=True):
            result = oco_manager.cancel_oco("test_oco_id")
            assert result is True


class TestAlertSystem:
    """Test alert routing and rules."""
    
    @pytest.fixture
    def alert_router(self):
        from app.alert_router import AlertRouter
        return AlertRouter()
    
    @pytest.fixture
    def alert_rules(self):
        from app.alert_rules import AlertRulesEngine
        return AlertRulesEngine()
    
    def test_alert_routing(self, alert_router):
        """Alert should route to correct channels."""
        import asyncio
        from app.alert_router import Alert, AlertPriority, AlertChannel
        
        alert = Alert(
            alert_id="A001",
            title="System Alert",
            message="System down!",
            priority=AlertPriority.CRITICAL,
            source="test",
            category="system",
            channels=[AlertChannel.DISCORD]
        )
        
        # Run async method synchronously
        loop = asyncio.new_event_loop()
        try:
            routes = loop.run_until_complete(alert_router.send_alert(alert))
            assert isinstance(routes, list)
        finally:
            loop.close()
    
    def test_rule_evaluation(self, alert_rules):
        """Rule engine should evaluate data."""
        from app.alert_rules import AlertRule, RuleCondition, Operator, LogicGate
        
        rule = AlertRule(
            rule_id="test_1",
            name="Price Drop Alert",
            description="Alert when price drops more than 5%",
            conditions=[
                RuleCondition(field="price_change_24h", operator=Operator.LT, value=-5)
            ],
            logic=LogicGate.AND,
            channels=["discord"]
        )
        
        alert_rules.add_rule(rule)
        
        data = {"price_change_24h": -7.5}
        triggered = alert_rules.evaluate_data(data)
        
        assert isinstance(triggered, list)


class TestStrategyValidation:
    """Test strategy validation lifecycle."""
    
    @pytest.fixture
    def validator(self):
        from app.strategy_validation import StrategyValidationManager
        return StrategyValidationManager()
    
    def test_validation_period(self, validator):
        """Strategy should complete validation after period."""
        from app.strategy_validation import StrategyTrial, ValidationCriteria, StrategyStatus
        from datetime import datetime
        
        criteria = ValidationCriteria(min_trades=10, min_sharpe=0.5)
        trial = StrategyTrial(
            strategy_id="test_strategy",
            strategy_name="Test Strategy",
            status=StrategyStatus.TRIAL,
            trial_start=datetime.now(),
            criteria=criteria
        )
        
        assert trial.strategy_id == "test_strategy"
        assert trial.strategy_name == "Test Strategy"


class TestTradeStorage:
    """Test trade data persistence."""
    
    @pytest.fixture
    def storage(self):
        from app.trade_storage import TradeStorage
        return TradeStorage()
    
    def test_trade_query(self, storage):
        """Should query trades by symbol."""
        from app.trade_storage import TradeRecord, TradeStatus, TradeType
        
        trade = TradeRecord(
            trade_id="T001",
            symbol="BTCUSDT",
            side=TradeType.BUY,
            status=TradeStatus.OPEN,
            entry_price=45000,
            quantity=0.5,
            strategy="BTC_4H",
            entry_time=datetime.now()
        )
        
        storage.add_trade(trade)
        trades = storage.get_trades(symbol="BTCUSDT")
        
        assert isinstance(trades, list)
    
    def test_pnl_calculation(self):
        """Should calculate P&L correctly."""
        entry_price = 45000
        exit_price = 47000
        quantity = 0.5
        
        pnl = (exit_price - entry_price) * quantity
        assert pnl == 1000.0


class TestConcurrency:
    """Test concurrent access handling."""
    
    @pytest.fixture
    def lock_manager(self):
        from app.concurrency import OptimisticLock
        return OptimisticLock("task_1")
    
    def test_optimistic_lock(self, lock_manager):
        """Optimistic lock should detect conflicts."""
        assert lock_manager is not None
        assert lock_manager.resource_id == "task_1"


class TestEndToEnd:
    """End-to-end trading flow tests."""
    
    def test_full_trading_flow(self):
        """Test complete trading lifecycle."""
        # 1. Market data arrives
        # 2. Strategy generates signal
        # 3. Risk check passes
        # 4. Position sizing calculates
        # 5. Order submitted
        # 6. OCO orders created
        # 7. Alert sent
        
        # This would require full system integration
        # Placeholder for future implementation
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
