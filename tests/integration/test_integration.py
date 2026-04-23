"""
Integration Test Suite
End-to-end tests for the trading system components.
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

# Import system components
import sys
sys.path.insert(0, '/app')


class TestMarketDataStream:
    """Test real-time market data streaming."""
    
    @pytest.fixture
    def stream(self):
        from app.market_stream import MarketStream, StreamType
        return MarketStream(symbols=["BTCUSDT"], stream_type=StreamType.TICKER)
    
    def test_stream_initialization(self, stream):
        assert stream.symbols == ["BTCUSDT"]
        assert stream.stream_type == StreamType.TICKER
        assert not stream.running
    
    def test_stream_lifecycle(self, stream):
        # Cannot start without handlers
        result = stream.start()
        assert result is False
        
        # Add handler
        handler = Mock()
        stream.add_handler("tick", handler)
        
        # Mock connection
        with patch.object(stream, '_connect', return_value=True):
            with patch.object(stream, '_run_loop', new_callable=AsyncMock):
                result = stream.start()
                assert result is True
                assert stream.running
        
        # Stop
        stream.stop()
        assert not stream.running


class TestOrderExecution:
    """Test order execution flow."""
    
    @pytest.fixture
    def executor(self):
        from app.order_executor import OrderExecutor
        return OrderExecutor(api_key="test", api_secret="test")
    
    def test_risk_check_before_order(self, executor):
        """Pre-trade risk check must pass before order."""
        with patch.object(executor.risk_manager, 'check_order', return_value=False):
            result = executor.place_order(
                symbol="BTCUSDT",
                side="BUY",
                quantity=1000000  # Too large
            )
            assert result['status'] == 'rejected'
            assert 'risk_check_failed' in result['reason']
    
    def test_order_retry_mechanism(self, executor):
        """Failed orders should retry with backoff."""
        with patch.object(executor, '_place_order_api', side_effect=[Exception("timeout"), Exception("timeout"), {"order_id": "123"}]):
            result = executor.place_order_with_retry(
                symbol="BTCUSDT",
                side="BUY",
                quantity=0.1,
                max_retries=3
            )
            assert result['status'] == 'success'
            assert result['retries'] == 2


class TestPositionSizing:
    """Test position sizing calculations."""
    
    @pytest.fixture
    def sizer(self):
        from app.position_sizer import PositionSizer
        return PositionSizer(account_balance=10000)
    
    def test_kelly_criterion(self, sizer):
        """Kelly criterion should limit position size."""
        size = sizer.calculate_kelly(
            win_rate=0.6,
            avg_win=100,
            avg_loss=50
        )
        assert size > 0
        assert size <= sizer.account_balance * 0.25  # Max 25%
    
    def test_risk_based_sizing(self, sizer):
        """Risk-based sizing respects max drawdown."""
        size = sizer.calculate_risk_based(
            entry_price=50000,
            stop_loss=48000,
            risk_percent=1.0
        )
        
        risk_amount = size * (50000 - 48000)
        expected_risk = sizer.account_balance * 0.01
        assert abs(risk_amount - expected_risk) < 1


class TestOCOOrders:
    """Test OCO (One-Cancels-Other) orders."""
    
    @pytest.fixture
    def oco_manager(self):
        from app.oco_manager import OCOManager
        return OCOManager()
    
    def test_oco_creation(self, oco_manager):
        """OCO pair should create both stop-loss and take-profit."""
        oco = oco_manager.create_oco(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            entry_price=45000,
            stop_loss=43000,
            take_profit=48000
        )
        
        assert oco.stop_loss_order is not None
        assert oco.take_profit_order is not None
        assert oco.status == "active"
    
    def test_oco_cancellation(self, oco_manager):
        """Filling one order should cancel the other."""
        oco = oco_manager.create_oco(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            entry_price=45000,
            stop_loss=43000,
            take_profit=48000
        )
        
        # Simulate stop-loss fill
        oco_manager.handle_fill(oco.id, oco.stop_loss_order.id)
        
        assert oco.status == "closed"
        assert oco.take_profit_order.status == "cancelled"


class TestAlertSystem:
    """Test alert routing and rules."""
    
    @pytest.fixture
    def alert_router(self):
        from app.alert_router import AlertRouter
        return AlertRouter()
    
    @pytest.fixture
    def alert_rules(self):
        from app.alert_rules import AlertRulesEngine, RuleCondition, RuleOperator
        engine = AlertRulesEngine()
        
        # Add test rule
        rule = engine.create_rule(
            name="Price Drop Alert",
            conditions=[
                RuleCondition(
                    field="price_change_24h",
                    operator=RuleOperator.LT,
                    value=-5
                )
            ],
            priority="high",
            channels=["discord"]
        )
        
        return engine
    
    def test_alert_routing(self, alert_router):
        """Alert should route to correct channels."""
        alert = {
            "priority": "critical",
            "message": "System down!",
            "channels": ["discord", "email"]
        }
        
        routes = alert_router.route_alert(alert)
        
        assert len(routes) == 2
        assert any(r['channel'] == 'discord' for r in routes)
        assert any(r['channel'] == 'email' for r in routes)
    
    def test_rule_evaluation(self, alert_rules):
        """Rule should trigger on matching condition."""
        context = {"price_change_24h": -7.5}
        
        triggered = alert_rules.evaluate_rules(context)
        
        assert len(triggered) == 1
        assert triggered[0]['rule_name'] == "Price Drop Alert"


class TestStrategyValidation:
    """Test strategy validation lifecycle."""
    
    @pytest.fixture
    def validator(self):
        from app.strategy_validation import StrategyValidation
        return StrategyValidation()
    
    def test_validation_period(self, validator):
        """Strategy should complete validation after period."""
        strategy = validator.create_strategy(
            name="Test Strategy",
            validation_days=30
        )
        
        assert strategy.status == "validation"
        assert strategy.days_remaining == 30
        
        # Simulate time passing
        strategy.start_date = datetime.now() - timedelta(days=31)
        
        # Evaluate
        result = validator.evaluate_strategy(strategy.id)
        assert result['status'] in ['passed', 'failed', 'extended']


class TestTradeStorage:
    """Test trade data persistence."""
    
    @pytest.fixture
    def storage(self):
        from app.trade_storage import TradeStorage, TradeRecord, TradeStatus, TradeType
        storage = TradeStorage()
        
        # Add test trade
        trade = TradeRecord(
            trade_id="T001",
            symbol="BTCUSDT",
            side=TradeType.BUY,
            status=TradeStatus.OPEN,
            entry_price=45000,
            quantity=0.5,
            strategy="BTC_4H"
        )
        storage.add_trade(trade)
        
        return storage
    
    def test_trade_query(self, storage):
        """Should query trades by symbol."""
        trades = storage.get_trades(symbol="BTCUSDT")
        assert len(trades) == 1
        assert trades[0].symbol == "BTCUSDT"
    
    def test_pnl_calculation(self, storage):
        """Should calculate P&L correctly."""
        closed = storage.close_trade("T001", exit_price=47000)
        
        assert closed is not None
        assert closed.status == TradeStatus.CLOSED
        assert closed.realized_pnl == 1000.0  # (47000-45000)*0.5


class TestConcurrency:
    """Test concurrent access handling."""
    
    @pytest.fixture
    def lock_manager(self):
        from app.concurrency import LockManager
        return LockManager()
    
    def test_optimistic_lock(self, lock_manager):
        """Optimistic lock should detect conflicts."""
        resource = {"id": "task_1", "version": 1, "data": "original"}
        
        # Acquire lock
        lock = lock_manager.acquire_optimistic("task_1", resource['version'])
        assert lock is not None
        
        # Simulate conflict
        resource['version'] = 2
        
        # Try to update with old version
        result = lock_manager.update_with_lock("task_1", resource, expected_version=1)
        assert result is False  # Conflict detected


@pytest.mark.asyncio
class TestWebSocketIntegration:
    """Test WebSocket integration."""
    
    async def test_websocket_connection(self):
        """Should connect to Binance WebSocket."""
        from app.market_stream import MarketStream, StreamType
        
        stream = MarketStream(
            symbols=["BTCUSDT"],
            stream_type=StreamType.TICKER,
            testnet=True
        )
        
        handler = Mock()
        stream.add_handler("tick", handler)
        
        # Connect (mock)
        with patch('websockets.connect', new_callable=AsyncMock) as mock_ws:
            mock_ws.return_value = AsyncMock()
            
            result = await stream.connect()
            assert result is True
            mock_ws.assert_called_once()


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
