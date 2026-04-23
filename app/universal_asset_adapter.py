"""
Universal Asset Adapter
Adapts different asset types for unified trading.
"""
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class AssetType(Enum):
    """Supported asset types."""
    CRYPTO = "crypto"
    STOCK = "stock"
    ETF = "etf"
    FOREX = "forex"
    FUTURES = "futures"


@dataclass
class Asset:
    """Unified asset representation."""
    symbol: str
    asset_type: AssetType
    exchange: str
    currency: str
    lot_size: float
    min_quantity: float
    price_decimal: int
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'asset_type': self.asset_type.value,
            'exchange': self.exchange,
            'currency': self.currency,
            'lot_size': self.lot_size,
            'min_quantity': self.min_quantity,
            'price_decimal': self.price_decimal,
        }


class UniversalAssetAdapter:
    """
    Universal adapter for different asset types.
    
    Provides unified interface for trading across:
    - Crypto (Binance)
    - Taiwan Stocks (TWSE)
    - US Stocks
    - ETFs
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.assets: Dict[str, Asset] = {}
        
        # Register default assets
        self._register_defaults()
        
        self.logger.info("UniversalAssetAdapter initialized")
    
    def _register_defaults(self):
        """Register default supported assets."""
        defaults = [
            Asset("BTCUSDT", AssetType.CRYPTO, "Binance", "USDT", 0.001, 0.001, 2),
            Asset("ETHUSDT", AssetType.CRYPTO, "Binance", "USDT", 0.01, 0.01, 2),
            Asset("2330.TW", AssetType.STOCK, "TWSE", "TWD", 1000, 1000, 2),
            Asset("2317.TW", AssetType.STOCK, "TWSE", "TWD", 1000, 1000, 2),
            Asset("AAPL", AssetType.STOCK, "US", "USD", 1, 1, 2),
            Asset("MSFT", AssetType.STOCK, "US", "USD", 1, 1, 2),
            Asset("QQQ", AssetType.ETF, "US", "USD", 1, 1, 2),
        ]
        
        for asset in defaults:
            self.assets[asset.symbol] = asset
    
    def get_asset(self, symbol: str) -> Optional[Asset]:
        """Get asset info."""
        return self.assets.get(symbol)
    
    def normalize_quantity(self, symbol: str, quantity: float) -> float:
        """Normalize quantity to lot size."""
        asset = self.assets.get(symbol)
        if not asset:
            return quantity
        
        # Round to lot size
        lots = int(quantity / asset.lot_size)
        return lots * asset.lot_size
    
    def format_price(self, symbol: str, price: float) -> str:
        """Format price with correct decimals."""
        asset = self.assets.get(symbol)
        if not asset:
            return f"{price:.2f}"
        
        return f"{price:.{asset.price_decimal}f}"
    
    def get_all_assets(self) -> List[Asset]:
        """Get all registered assets."""
        return list(self.assets.values())
    
    def get_by_type(self, asset_type: AssetType) -> List[Asset]:
        """Get assets by type."""
        return [a for a in self.assets.values() if a.asset_type == asset_type]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adapter = UniversalAssetAdapter()
    
    print("Universal Asset Adapter Demo")
    print("=" * 50)
    
    for asset in adapter.get_all_assets():
        print(f"{asset.symbol} ({asset.asset_type.value}): {asset.exchange}, lot={asset.lot_size}")
