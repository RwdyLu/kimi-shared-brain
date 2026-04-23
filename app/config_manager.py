"""
Environment Configuration Manager
Manages application configuration across environments (dev, staging, prod).
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatabaseConfig:
    """Database configuration."""

    host: str = "localhost"
    port: int = 5432
    database: str = "trading"
    user: str = "trader"
    password: str = ""
    pool_size: int = 10

    def to_dict(self) -> Dict:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "pool_size": self.pool_size,
        }


@dataclass
class TradingConfig:
    """Trading system configuration."""

    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    timeframes: List[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    max_position_size: float = 0.1  # 10% of balance
    max_drawdown_pct: float = 15.0
    risk_per_trade: float = 1.0  # 1% risk

    def to_dict(self) -> Dict:
        return {
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "max_position_size": self.max_position_size,
            "max_drawdown_pct": self.max_drawdown_pct,
            "risk_per_trade": self.risk_per_trade,
        }


class ConfigManager:
    """
    Manages environment-specific configuration.
    Loads from env vars, files, and provides defaults.
    """

    def __init__(self, env: str = None):
        self.logger = logging.getLogger(__name__)
        self.env = env or os.getenv("APP_ENV", "development")

        # Config storage
        self.db: DatabaseConfig = DatabaseConfig()
        self.trading: TradingConfig = TradingConfig()
        self.features: Dict[str, bool] = {}

        # Load configuration
        self._load_from_env()
        self._load_from_file()

        self.logger.info(f"ConfigManager initialized (env={self.env})")

    def _load_from_env(self):
        """Load configuration from environment variables."""
        # Database
        self.db.host = os.getenv("DB_HOST", self.db.host)
        self.db.port = int(os.getenv("DB_PORT", self.db.port))
        self.db.database = os.getenv("DB_NAME", self.db.database)
        self.db.user = os.getenv("DB_USER", self.db.user)
        self.db.password = os.getenv("DB_PASSWORD", self.db.password)

        # Trading
        symbols = os.getenv("TRADING_SYMBOLS", "")
        if symbols:
            self.trading.symbols = symbols.split(",")

        self.trading.max_position_size = float(os.getenv("MAX_POSITION_SIZE", self.trading.max_position_size))
        self.trading.max_drawdown_pct = float(os.getenv("MAX_DRAWDOWN", self.trading.max_drawdown_pct))

        # Features
        self.features["enable_alerts"] = os.getenv("ENABLE_ALERTS", "true").lower() == "true"
        self.features["enable_auto_trade"] = os.getenv("ENABLE_AUTO_TRADE", "false").lower() == "true"
        self.features["enable_backtest"] = os.getenv("ENABLE_BACKTEST", "true").lower() == "true"

    def _load_from_file(self, filepath: str = "config.json"):
        """Load configuration from JSON file."""
        if not Path(filepath).exists():
            return

        try:
            with open(filepath, "r") as f:
                config = json.load(f)

            # Apply config
            if "database" in config:
                for key, value in config["database"].items():
                    if hasattr(self.db, key):
                        setattr(self.db, key, value)

            if "trading" in config:
                for key, value in config["trading"].items():
                    if hasattr(self.trading, key):
                        setattr(self.trading, key, value)

            if "features" in config:
                self.features.update(config["features"])

            self.logger.info(f"Loaded config from {filepath}")

        except Exception as e:
            self.logger.error(f"Config load error: {e}")

    def save_config(self, filepath: str = "config.json"):
        """Save current configuration to file."""
        config = {
            "environment": self.env,
            "database": self.db.to_dict(),
            "trading": self.trading.to_dict(),
            "features": self.features,
        }

        with open(filepath, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Config saved to {filepath}")

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if feature is enabled."""
        return self.features.get(feature, False)

    def get_db_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return f"postgresql://{self.db.user}:{self.db.password}" f"@{self.db.host}:{self.db.port}/{self.db.database}"

    def validate(self) -> List[str]:
        """Validate configuration."""
        errors = []

        if not self.db.host:
            errors.append("Database host is required")

        if not self.db.database:
            errors.append("Database name is required")

        if self.trading.max_position_size <= 0 or self.trading.max_position_size > 1:
            errors.append("max_position_size must be between 0 and 1")

        if self.trading.risk_per_trade <= 0:
            errors.append("risk_per_trade must be positive")

        return errors

    def get_summary(self) -> Dict:
        """Get configuration summary."""
        return {
            "environment": self.env,
            "database_host": self.db.host,
            "trading_symbols": self.trading.symbols,
            "max_position_size": self.trading.max_position_size,
            "risk_per_trade": self.trading.risk_per_trade,
            "features": self.features,
            "is_valid": len(self.validate()) == 0,
        }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Development config
    dev_config = ConfigManager(env="development")
    print("Development Config:")
    print(json.dumps(dev_config.get_summary(), indent=2))

    # Production config
    os.environ["APP_ENV"] = "production"
    os.environ["DB_HOST"] = "prod-db.example.com"
    os.environ["TRADING_SYMBOLS"] = "BTCUSDT,ETHUSDT,SOLUSDT"

    prod_config = ConfigManager()
    print("\nProduction Config:")
    print(json.dumps(prod_config.get_summary(), indent=2))

    # Validate
    errors = prod_config.validate()
    if errors:
        print(f"\nValidation errors: {errors}")
    else:
        print("\nConfig is valid!")
