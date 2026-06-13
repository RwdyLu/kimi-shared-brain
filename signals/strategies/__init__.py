"""
Strategy Plugins for Signal Engine
訊號引擎策略外掛

Each module in this package implements a strategy callable
that the SignalEngine can dispatch to dynamically.
"""
from typing import Dict, List, Any, Callable

# Registry of strategy functions
_STRATEGIES: Dict[str, Callable] = {}


def register(name: str):
    """Decorator to register a strategy function."""
    def decorator(func: Callable):
        _STRATEGIES[name] = func
        return func
    return decorator


def get_strategy(name: str) -> Callable:
    """Retrieve a registered strategy by name."""
    return _STRATEGIES.get(name)


def list_strategies() -> List[str]:
    """List all registered strategy names."""
    return list(_STRATEGIES.keys())


# Import all strategy modules so they self-register
from . import ema_rsi_volume
