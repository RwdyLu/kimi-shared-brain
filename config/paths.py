"""
Root Path Resolver
根路徑解析器

BTC/ETH Monitoring System - Path Resolution
BTC/ETH 監測系統 - 路徑解析

Provides dynamic project root detection to avoid hardcoded paths.
提供動態專案根目錄檢測，避免硬編碼路徑。

Version: 1.0.0
Date: 2026-04-09
"""

import os
import sys
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """
    Dynamically detect project root directory
    動態檢測專案根目錄
    
    Detection order:
    1. Check KIMI_SHARED_BRAIN_ROOT environment variable
    2. Check if /tmp/kimi-shared-brain exists AND has config files
    3. Check current working directory
    4. Check script location
    5. Fallback to /tmp/kimi-shared-brain
    
    Returns:
        Path to project root directory
    """
    # 1. Environment variable (highest priority)
    env_root = os.environ.get('KIMI_SHARED_BRAIN_ROOT')
    if env_root and os.path.isdir(env_root):
        return Path(env_root).resolve()
    
    # 2. Check current working directory first
    cwd = Path.cwd()
    if (cwd / "config" / "assets.json").exists():
        return cwd
    
    # 3. Check script location (traverse up to find config/ with assets.json)
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, script_dir.parent, script_dir.parent.parent]:
        if (parent / "config" / "assets.json").exists():
            return parent
    
    # 4. Check if /tmp/kimi-shared-brain exists AND has config files
    default_path = Path("/tmp/kimi-shared-brain")
    if default_path.exists() and (default_path / "config" / "assets.json").exists():
        return default_path
    
    # 5. Fallback to script location parent
    return script_dir.parent


def get_config_dir() -> Path:
    """Get config directory / 取得配置目錄"""
    return get_project_root() / "config"


def get_logs_dir() -> Path:
    """Get logs directory / 取得日誌目錄"""
    return get_project_root() / "logs"


def get_outputs_dir() -> Path:
    """Get outputs directory / 取得輸出目錄"""
    return get_project_root() / "outputs"


def get_state_dir() -> Path:
    """Get state directory / 取得狀態目錄"""
    return get_project_root() / "state"


def get_actions_dir() -> Path:
    """Get actions state directory / 取得行動狀態目錄"""
    return get_state_dir() / "actions"


def get_ui_dir() -> Path:
    """Get UI directory / 取得 UI 目錄"""
    return get_project_root() / "ui"


def resolve_path(relative_path: str) -> Path:
    """
    Resolve a path relative to project root
    解析相對於專案根目錄的路徑
    
    Args:
        relative_path: Path relative to project root (e.g., "config/monitoring_params.json")
    
    Returns:
        Absolute Path
    """
    return get_project_root() / relative_path


# Global paths for convenience / 便利的全局路徑
PROJECT_ROOT = get_project_root()
CONFIG_DIR = get_config_dir()
LOGS_DIR = get_logs_dir()
OUTPUTS_DIR = get_outputs_dir()
STATE_DIR = get_state_dir()
ACTIONS_DIR = get_actions_dir()
UI_DIR = get_ui_dir()


def ensure_dirs():
    """
    Ensure all necessary directories exist
    確保所有必要目錄存在
    """
    dirs_to_create = [
        CONFIG_DIR,
        LOGS_DIR,
        OUTPUTS_DIR,
        STATE_DIR,
        ACTIONS_DIR,
    ]
    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)


# Auto-ensure directories on import / 匯入時自動確保目錄存在
ensure_dirs()
