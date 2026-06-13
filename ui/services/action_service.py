"""
Action Service
行動服務

BTC/ETH Monitoring System - Action Queue Service Layer
BTC/ETH 監測系統 - 行動佇列服務層

This module provides the ActionQueueService for managing pending actions
and action history. Separated from UI layer for better code organization.

本模組提供 ActionQueueService 用於管理待處理行動與行動歷史。
與 UI 層分離以改善程式碼組織。

Version: 1.0.0
Date: 2026-04-09
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Import dynamic path resolver / 匯入動態路徑解析器
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.paths import STATE_DIR, ACTIONS_DIR


# Default paths / 預設路徑
DEFAULT_ACTIONS_DIR = str(ACTIONS_DIR)
DEFAULT_ACTIONS_FILE = os.path.join(DEFAULT_ACTIONS_DIR, "queue.json")
DEFAULT_HISTORY_FILE = os.path.join(DEFAULT_ACTIONS_DIR, "history.json")


class ActionQueueService:
    """
    Service for managing action queue
    管理行動佇列的服務
    
    This service manages pending actions and action history for the
    BTC/ETH monitoring system. Actions represent signals that require
    manual decision (approve, reject, or snooze).
    
    ⚠️ ALERT-ONLY SYSTEM / 僅提醒系統
    This service logs decisions but NEVER executes trades automatically.
    本服務記錄決策但絕不自動執行交易。
    """
    
    def __init__(self, actions_dir: str = None, actions_file: str = None, history_file: str = None):
        """
        Initialize the action queue service
        
        Args:
            actions_dir: Directory for action files (auto-detected from project root)
            actions_file: Path to queue.json (default: actions_dir/queue.json)
            history_file: Path to history.json (default: actions_dir/history.json)
        """
        self.actions_dir = actions_dir or DEFAULT_ACTIONS_DIR
        self.actions_file = actions_file or os.path.join(self.actions_dir, "queue.json")
        self.history_file = history_file or os.path.join(self.actions_dir, "history.json")
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """Ensure directories exist / 確保目錄存在"""
        os.makedirs(self.actions_dir, exist_ok=True)
    
    def load_pending_actions(self) -> List[Dict[str, Any]]:
        """
        Load pending actions from file
        從檔案載入待處理行動
        
        Returns:
            List of pending action dictionaries
        """
        try:
            if os.path.exists(self.actions_file):
                with open(self.actions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("pending", [])
            return []
        except Exception as e:
            print(f"Error loading pending actions: {e}")
            return []
    
    def load_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Load action history from file
        從檔案載入行動歷史
        
        Args:
            limit: Maximum number of history items to return
            
        Returns:
            List of action history dictionaries, sorted by decided_at descending
        """
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    history = data.get("history", [])
                    # Return most recent first
                    return sorted(history, key=lambda x: x.get("decided_at", ""), reverse=True)[:limit]
            return []
        except Exception as e:
            print(f"Error loading history: {e}")
            return []
    
    def save_pending_actions(self, actions: List[Dict[str, Any]]):
        """
        Save pending actions to file
        儲存待處理行動到檔案
        
        Args:
            actions: List of pending action dictionaries
        """
        try:
            data = {
                "pending": actions,
                "updated_at": datetime.now().isoformat(),
                "count": len(actions)
            }
            with open(self.actions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving pending actions: {e}")
    
    def save_history(self, history: List[Dict[str, Any]]):
        """
        Save action history to file
        儲存行動歷史到檔案
        
        Args:
            history: List of action history dictionaries
        """
        try:
            data = {
                "history": history,
                "updated_at": datetime.now().isoformat()
            }
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def process_decision(self, action_id: str, decision: str, note: str = "") -> bool:
        """
        Process a decision for an action
        處理行動的決策
        
        Args:
            action_id: Action ID
            decision: 'approve', 'reject', or 'snooze'
            note: Optional note for the decision
            
        Returns:
            True if successful, False otherwise
            
        Note:
            - approve/reject: Moves action to history
            - snooze: Keeps action in pending with snooze timestamp (30 min delay)
        """
        try:
            pending = self.load_pending_actions()
            history = self.load_history(limit=1000)  # Load all for append
            
            # Find the action
            action = None
            action_index = -1
            for i, a in enumerate(pending):
                if a.get("id") == action_id:
                    action = a
                    action_index = i
                    break
            
            if not action:
                return False
            
            # Update action with decision
            now = datetime.now()
            now_iso = now.isoformat()
            action["decision"] = decision
            action["decided_at"] = now_iso
            action["decision_note"] = note
            
            if decision == "snooze":
                # For snooze, keep in pending with snooze timestamp (30 min delay)
                snooze_until = now.replace(minute=(now.minute + 30) % 60)
                if now.minute + 30 >= 60:
                    snooze_until = snooze_until.replace(hour=(now.hour + 1) % 24)
                action["snooze_until"] = snooze_until.isoformat()
                action["snooze_count"] = action.get("snooze_count", 0) + 1
                # Move to end of queue
                pending.pop(action_index)
                pending.append(action)
            else:
                # For approve/reject, remove from pending and add to history
                pending.pop(action_index)
                history.append(action)
            
            # Save both files
            self.save_pending_actions(pending)
            self.save_history(history)
            
            return True
            
        except Exception as e:
            print(f"Error processing decision: {e}")
            return False
    
    def add_action(self, action: Dict[str, Any]) -> str:
        """
        Add a new action to the queue
        新增行動到佇列
        
        Args:
            action: Action dictionary with at least 'type', 'symbol', 'suggestion'
            
        Returns:
            Generated action ID
        """
        pending = self.load_pending_actions()
        
        # Generate ID with timestamp and index
        action_id = f"ACT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(pending)}"
        action["id"] = action_id
        action["created_at"] = datetime.now().isoformat()
        action["status"] = "pending"
        
        pending.append(action)
        self.save_pending_actions(pending)
        
        return action_id
    
    def get_today_stats(self) -> Dict[str, int]:
        """
        Get today's action statistics
        取得今日行動統計
        
        Returns:
            Dictionary with pending, approved, rejected, snoozed counts
        """
        history = self.load_history(limit=1000)
        today = datetime.now().strftime("%Y-%m-%d")
        
        stats = {
            "pending": len(self.load_pending_actions()),
            "approved": 0,
            "rejected": 0,
            "snoozed": 0
        }
        
        for action in history:
            decided_at = action.get("decided_at", "")
            if today in decided_at:
                decision = action.get("decision", "")
                if decision == "approve":
                    stats["approved"] += 1
                elif decision == "reject":
                    stats["rejected"] += 1
                elif decision == "snooze":
                    stats["snoozed"] += 1
        
        return stats
    
    def clear_history(self) -> bool:
        """
        Clear all action history
        清除所有行動歷史
        
        Returns:
            True if successful
        """
        try:
            self.save_history([])
            return True
        except Exception as e:
            print(f"Error clearing history: {e}")
            return False


# Global service instance for convenience / 便利用的全局服務實例
_default_service = ActionQueueService()


def load_pending_actions() -> List[Dict[str, Any]]:
    """Load pending actions using default service / 使用預設服務載入待處理行動"""
    return _default_service.load_pending_actions()


def load_history(limit: int = 20) -> List[Dict[str, Any]]:
    """Load history using default service / 使用預設服務載入歷史"""
    return _default_service.load_history(limit)


def process_decision(action_id: str, decision: str, note: str = "") -> bool:
    """Process decision using default service / 使用預設服務處理決策"""
    return _default_service.process_decision(action_id, decision, note)


def add_action(action: Dict[str, Any]) -> str:
    """Add action using default service / 使用預設服務新增行動"""
    return _default_service.add_action(action)


def get_today_stats() -> Dict[str, int]:
    """Get today stats using default service / 使用預設服務取得今日統計"""
    return _default_service.get_today_stats()


def clear_history() -> bool:
    """Clear history using default service / 使用預設服務清除歷史"""
    return _default_service.clear_history()
