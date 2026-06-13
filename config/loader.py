"""
Config Loader Module
配置載入模組

BTC/ETH Monitoring System - Configuration Layer
BTC/ETH 監測系統 - 配置層

This module provides centralized configuration loading and management.
本模組提供集中化的配置載入與管理。

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-07
"""

import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Import dynamic path resolver / 匯入動態路徑解析器
from config.paths import CONFIG_DIR, resolve_path


# Default config paths / 預設配置路徑
DEFAULT_CONFIG_DIR = CONFIG_DIR


class ConfigLoader:
    """
    Centralized configuration loader
    集中化配置載入器
    """
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize config loader
        
        Args:
            config_dir: Path to config directory (default: /tmp/kimi-shared-brain/config)
        """
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self._cache: Dict[str, Any] = {}
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON config file"""
        filepath = self.config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_monitoring_params(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load monitoring parameters
        
        Returns:
            Dict with monitoring, indicators, signals, notifications, data sections
        """
        cache_key = "monitoring_params"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        config = self._load_json("monitoring_params.json")
        if use_cache:
            self._cache[cache_key] = config
        return config
    
    def load_strategies(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load strategy registry
        
        Returns:
            Dict with strategies list and registry settings
        """
        cache_key = "strategies"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        config = self._load_json("strategies.json")
        if use_cache:
            self._cache[cache_key] = config
        return config
    
    def load_assets(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load asset definitions
        
        Returns:
            Dict with assets list and asset groups
        """
        cache_key = "assets"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        config = self._load_json("assets.json")
        if use_cache:
            self._cache[cache_key] = config
        return config
    
    def load_channel_config(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Load notification channel config
        
        Returns:
            Dict with channel configuration
        """
        cache_key = "channel_config"
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        config = self._load_json("channel_config.json")
        if use_cache:
            self._cache[cache_key] = config
        return config
    
    def clear_cache(self) -> None:
        """Clear config cache"""
        self._cache.clear()
    
    def reload_all(self) -> Dict[str, Any]:
        """Reload all configs (bypass cache)"""
        self.clear_cache()
        return {
            "monitoring_params": self.load_monitoring_params(use_cache=False),
            "strategies": self.load_strategies(use_cache=False),
            "assets": self.load_assets(use_cache=False),
            "channel_config": self.load_channel_config(use_cache=False)
        }


# Convenience functions for direct access / 直接存取的便利函數

_loader = ConfigLoader()


def get_monitoring_params() -> Dict[str, Any]:
    """Get monitoring parameters"""
    return _loader.load_monitoring_params()


def get_strategies() -> Dict[str, Any]:
    """Get strategy registry"""
    return _loader.load_strategies()


def get_assets() -> Dict[str, Any]:
    """Get asset definitions"""
    return _loader.load_assets()


def get_channel_config() -> Dict[str, Any]:
    """Get channel config"""
    return _loader.load_channel_config()


def get_enabled_symbols() -> List[str]:
    """Get list of enabled symbols from assets config"""
    assets_config = get_assets()
    return [
        asset["symbol"] 
        for asset in assets_config.get("assets", [])
        if asset.get("enabled", False)
    ]


def get_enabled_strategies() -> List[Dict[str, Any]]:
    """Get list of enabled strategies from strategies config"""
    strategies_config = get_strategies()
    return [
        strategy 
        for strategy in strategies_config.get("strategies", [])
        if strategy.get("enabled", False)
    ]


def get_indicator_params() -> Dict[str, Any]:
    """Get indicator parameters from monitoring config"""
    params = get_monitoring_params()
    return params.get("indicators", {})


def get_signal_params() -> Dict[str, Any]:
    """Get signal parameters from monitoring config"""
    params = get_monitoring_params()
    return params.get("signals", {})


def get_monitoring_interval() -> int:
    """Get monitoring check interval in minutes"""
    params = get_monitoring_params()
    return params.get("monitoring", {}).get("check_interval_minutes", 5)


def get_volume_threshold() -> float:
    """Get volume spike threshold"""
    indicators = get_indicator_params()
    return indicators.get("volume", {}).get("spike_threshold", 1.5)


def get_cooldown_minutes(signal_type: str = "trend_long") -> int:
    """Get cooldown minutes for a signal type"""
    signals = get_signal_params()
    cooldowns = signals.get("cooldown_minutes", {})
    return cooldowns.get(signal_type, 30)


def reload_configs() -> None:
    """Reload all configurations (clear cache)"""
    _loader.reload_all()


# =============================================================================
# Example usage / 使用範例
# =============================================================================

if __name__ == "__main__":
    print("Config Loader Test / 配置載入器測試")
    print("=" * 50)
    
    # Test loading all configs
    try:
        monitoring = get_monitoring_params()
        print(f"✅ Monitoring params loaded: {monitoring['version']}")
        print(f"   Check interval: {get_monitoring_interval()} minutes")
        print(f"   Volume threshold: {get_volume_threshold()}x")
        
        strategies = get_strategies()
        enabled = get_enabled_strategies()
        print(f"✅ Strategies loaded: {len(enabled)} enabled out of {len(strategies['strategies'])}")
        
        assets = get_assets()
        symbols = get_enabled_symbols()
        print(f"✅ Assets loaded: {symbols}")
        
        print("\n✅ All configs loaded successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
