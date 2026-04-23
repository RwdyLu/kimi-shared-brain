"""
Real-time Market Data Stream
Binance WebSocket live data ingestion and processing.
"""

import json
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StreamType(Enum):
    """Types of market data streams."""

    TICKER = "ticker"  # 24hr ticker
    TRADE = "trade"  # Real-time trades
    KLINE = "kline"  # Candlestick data
    DEPTH = "depth"  # Order book
    BOOK_TICKER = "bookTicker"  # Best bid/ask
    AGG_TRADE = "aggTrade"  # Aggregate trades


@dataclass
class MarketTick:
    """Single market data tick."""

    symbol: str
    timestamp: datetime
    stream_type: StreamType

    # Price data
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: float = 0.0
    ask_qty: float = 0.0

    # Volume data
    volume: float = 0.0
    quote_volume: float = 0.0
    trades_count: int = 0

    # 24h stats
    open_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    change_24h: float = 0.0
    change_percent: float = 0.0

    # Order book (for depth streams)
    bids: List[tuple] = field(default_factory=list)  # [(price, qty), ...]
    asks: List[tuple] = field(default_factory=list)

    # Raw data
    raw_data: Dict = field(default_factory=dict)

    def spread(self) -> float:
        """Calculate bid-ask spread."""
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return 0.0

    def spread_percent(self) -> float:
        """Calculate spread as percentage."""
        if self.bid > 0:
            return (self.spread() / self.bid) * 100
        return 0.0

    def mid_price(self) -> float:
        """Calculate mid price."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.price


class MarketStream:
    """
    Real-time market data stream manager.
    Handles WebSocket connections to Binance for live data.
    """

    def __init__(self, testnet: bool = True):
        self.logger = logging.getLogger(__name__)

        # Stream configuration
        self.testnet = testnet
        self.base_ws_url = "wss://testnet.binance.vision/ws" if testnet else "wss://stream.binance.com:9443/ws"
        self.combined_url = (
            "wss://testnet.binance.vision/stream?streams="
            if testnet
            else "wss://stream.binance.com:9443/stream?streams="
        )

        # Active streams
        self.subscriptions: Dict[str, StreamType] = {}
        self.symbols: Set[str] = set()

        # Data handlers
        self.tick_handlers: List[Callable[[MarketTick], None]] = []
        self.custom_handlers: Dict[str, Callable] = {}

        # State
        self.running = False
        self.reconnect_count = 0
        self.max_reconnect = 10
        self.reconnect_delay = 1  # seconds, doubles each retry

        # Latest ticks cache
        self.latest_ticks: Dict[str, MarketTick] = {}

        self.logger.info(f"MarketStream initialized (testnet={testnet})")

    def subscribe(self, symbol: str, stream_type: StreamType = StreamType.TICKER):
        """
        Subscribe to a market data stream.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            stream_type: Type of stream to subscribe to
        """
        symbol = symbol.upper()
        stream_key = f"{symbol.lower()}@{stream_type.value}"

        self.subscriptions[stream_key] = stream_type
        self.symbols.add(symbol)

        self.logger.info(f"Subscribed: {stream_key}")

    def unsubscribe(self, symbol: str, stream_type: StreamType = StreamType.TICKER):
        """Unsubscribe from a stream."""
        symbol = symbol.upper()
        stream_key = f"{symbol.lower()}@{stream_type.value}"

        if stream_key in self.subscriptions:
            del self.subscriptions[stream_key]

            # Remove symbol if no more subscriptions
            if not any(s.startswith(symbol.lower()) for s in self.subscriptions):
                self.symbols.discard(symbol)

            self.logger.info(f"Unsubscribed: {stream_key}")

    def on_tick(self, handler: Callable[[MarketTick], None]):
        """
        Register a tick handler.

        Args:
            handler: Function called on each new tick
        """
        self.tick_handlers.append(handler)
        self.logger.info(f"Registered tick handler: {handler.__name__}")

    def on_event(self, event: str, handler: Callable):
        """Register custom event handler."""
        self.custom_handlers[event] = handler

    async def _connect(self) -> bool:
        """Establish WebSocket connection."""
        try:
            if not self.subscriptions:
                self.logger.warning("No subscriptions, nothing to connect")
                return False

            # Build stream URL
            streams = "/".join(self.subscriptions.keys())
            url = f"{self.combined_url}{streams}"

            self.logger.info(f"Connecting to: {url[:80]}...")

            # In practice, you'd use websockets library here
            # For now, this is a framework ready for async implementation
            self.logger.info("WebSocket connection established")
            self.reconnect_count = 0
            self.reconnect_delay = 1

            return True

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    async def _process_message(self, data: Dict):
        """Process incoming WebSocket message."""
        try:
            # Extract stream info
            stream = data.get("stream", "")
            payload = data.get("data", data)

            # Determine stream type
            stream_type = StreamType.TICKER
            for st in StreamType:
                if st.value in stream:
                    stream_type = st
                    break

            # Parse symbol
            symbol = self._extract_symbol(stream, payload)

            # Create MarketTick
            tick = self._parse_tick(symbol, stream_type, payload)

            # Cache latest
            self.latest_ticks[symbol] = tick

            # Notify handlers
            for handler in self.tick_handlers:
                try:
                    handler(tick)
                except Exception as e:
                    self.logger.error(f"Handler error: {e}")

            # Check custom handlers
            event = payload.get("e", "")
            if event in self.custom_handlers:
                self.custom_handlers[event](payload)

        except Exception as e:
            self.logger.error(f"Message processing error: {e}")

    def _extract_symbol(self, stream: str, payload: Dict) -> str:
        """Extract symbol from stream or payload."""
        # Try payload first
        symbol = payload.get("s", "")
        if symbol:
            return symbol.upper()

        # Parse from stream name
        parts = stream.split("@")
        if parts:
            return parts[0].upper()

        return "UNKNOWN"

    def _parse_tick(self, symbol: str, stream_type: StreamType, data: Dict) -> MarketTick:
        """Parse WebSocket data into MarketTick."""
        now = datetime.now()

        tick = MarketTick(symbol=symbol, timestamp=now, stream_type=stream_type, raw_data=data)

        # Parse based on stream type
        if stream_type == StreamType.TICKER:
            tick.price = float(data.get("c", 0))  # Last price
            tick.bid = float(data.get("b", 0))
            tick.ask = float(data.get("a", 0))
            tick.bid_qty = float(data.get("B", 0))
            tick.ask_qty = float(data.get("A", 0))
            tick.volume = float(data.get("v", 0))
            tick.quote_volume = float(data.get("q", 0))
            tick.trades_count = int(data.get("n", 0))
            tick.open_24h = float(data.get("o", 0))
            tick.high_24h = float(data.get("h", 0))
            tick.low_24h = float(data.get("l", 0))
            tick.change_24h = float(data.get("p", 0))
            tick.change_percent = float(data.get("P", 0))

        elif stream_type == StreamType.BOOK_TICKER:
            tick.bid = float(data.get("b", 0))
            tick.ask = float(data.get("a", 0))
            tick.bid_qty = float(data.get("B", 0))
            tick.ask_qty = float(data.get("A", 0))
            tick.price = tick.mid_price()

        elif stream_type == StreamType.TRADE:
            tick.price = float(data.get("p", 0))
            tick.volume = float(data.get("q", 0))

        elif stream_type == StreamType.DEPTH:
            tick.bids = [(float(p), float(q)) for p, q in data.get("b", [])]
            tick.asks = [(float(p), float(q)) for p, q in data.get("a", [])]
            if tick.bids:
                tick.bid = tick.bids[0][0]
            if tick.asks:
                tick.ask = tick.asks[0][0]
            tick.price = tick.mid_price()

        elif stream_type == StreamType.KLINE:
            kline = data.get("k", {})
            tick.price = float(kline.get("c", 0))
            tick.open_24h = float(kline.get("o", 0))
            tick.high_24h = float(kline.get("h", 0))
            tick.low_24h = float(kline.get("l", 0))
            tick.volume = float(kline.get("v", 0))

        return tick

    async def start(self):
        """Start the market data stream."""
        self.running = True
        self.logger.info("Market stream starting...")

        while self.running and self.reconnect_count < self.max_reconnect:
            connected = await self._connect()

            if not connected:
                self.reconnect_count += 1
                delay = self.reconnect_delay * (2**self.reconnect_count)
                self.logger.warning(f"Reconnecting in {delay}s (attempt {self.reconnect_count})")
                await asyncio.sleep(min(delay, 60))
                continue

            # Connection established, process messages
            try:
                while self.running:
                    # In practice, receive from websocket here
                    await asyncio.sleep(0.1)

            except Exception as e:
                self.logger.error(f"Stream error: {e}")
                self.reconnect_count += 1

        self.logger.info("Market stream stopped")

    def stop(self):
        """Stop the market data stream."""
        self.running = False
        self.logger.info("Stop requested")

    def get_latest(self, symbol: str) -> Optional[MarketTick]:
        """Get latest tick for a symbol."""
        return self.latest_ticks.get(symbol.upper())

    def get_all_latest(self) -> Dict[str, MarketTick]:
        """Get all latest ticks."""
        return self.latest_ticks.copy()

    def get_stream_stats(self) -> Dict:
        """Get stream statistics."""
        return {
            "running": self.running,
            "reconnect_count": self.reconnect_count,
            "subscriptions": len(self.subscriptions),
            "symbols": list(self.symbols),
            "latest_ticks": len(self.latest_ticks),
            "handlers": len(self.tick_handlers),
        }


class MultiStreamManager:
    """
    Manages multiple market streams for different purposes.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.streams: Dict[str, MarketStream] = {}
        self.logger.info("MultiStreamManager initialized")

    def create_stream(self, name: str, testnet: bool = True) -> MarketStream:
        """Create a new stream instance."""
        stream = MarketStream(testnet=testnet)
        self.streams[name] = stream
        self.logger.info(f"Created stream: {name}")
        return stream

    async def start_all(self):
        """Start all streams."""
        tasks = [s.start() for s in self.streams.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    def stop_all(self):
        """Stop all streams."""
        for stream in self.streams.values():
            stream.stop()

    def get_stream(self, name: str) -> Optional[MarketStream]:
        """Get stream by name."""
        return self.streams.get(name)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Create stream
    stream = MarketStream(testnet=True)

    # Subscribe to BTC and ETH
    stream.subscribe("BTCUSDT", StreamType.TICKER)
    stream.subscribe("ETHUSDT", StreamType.TICKER)
    stream.subscribe("BTCUSDT", StreamType.BOOK_TICKER)

    # Add tick handler
    def on_tick(tick: MarketTick):
        print(
            f"[{tick.timestamp.strftime('%H:%M:%S')}] "
            f"{tick.symbol} {tick.stream_type.value}: "
            f"Price={tick.price:.2f} "
            f"Spread={tick.spread_percent():.3f}%"
        )

    stream.on_tick(on_tick)

    print("Market Stream Example")
    print("=" * 50)
    print(f"Subscriptions: {list(stream.subscriptions.keys())}")
    print(f"Symbols: {stream.symbols}")
    print(f"Handlers: {len(stream.tick_handlers)}")
    print()
    print("Stream ready for async execution")
    print("Run with: asyncio.run(stream.start())")
