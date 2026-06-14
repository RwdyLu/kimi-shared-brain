"""Per-market lot, commission and tax rules used by GA backtests."""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class MarketRules:
    market: str
    lot_step: float
    lot_min: float
    buy_commission_rate: float
    sell_commission_rate: float
    sell_tax_rate: float = 0.0
    currency: str = "USD"

    def buy_fee(self, trade_value: float) -> float:
        return trade_value * self.buy_commission_rate

    def sell_fee(self, trade_value: float) -> float:
        return trade_value * (self.sell_commission_rate + self.sell_tax_rate)


MARKET_RULES: Dict[str, MarketRules] = {
    "crypto_spot": MarketRules(
        market="crypto_spot",
        lot_step=0.001,
        lot_min=0.001,
        buy_commission_rate=0.001,
        sell_commission_rate=0.001,
        currency="USDT",
    ),
    "cn_etf": MarketRules(
        market="cn_etf",
        lot_step=100.0,
        lot_min=100.0,
        buy_commission_rate=0.0003,
        sell_commission_rate=0.0003,
        sell_tax_rate=0.0,
        currency="CNY",
    ),
    "cn_gold_etf": MarketRules(
        market="cn_gold_etf",
        lot_step=100.0,
        lot_min=100.0,
        buy_commission_rate=0.0003,
        sell_commission_rate=0.0003,
        sell_tax_rate=0.0,
        currency="CNY",
    ),
}

SYMBOL_MARKETS = {
    "510300": "cn_etf",
    "510500": "cn_etf",
    "159915": "cn_etf",
    "588000": "cn_etf",
    "518880": "cn_gold_etf",
    "159934": "cn_gold_etf",
}


def rules_for_symbol(symbol: str) -> MarketRules:
    market = SYMBOL_MARKETS.get(symbol, "crypto_spot")
    return MARKET_RULES[market]
