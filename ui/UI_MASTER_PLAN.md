# UI Master Plan
# UI 主規格文件

**Version**: 1.0.0  
**Date**: 2026-04-07  
**Status**: Phase 1 - Planning  
**Framework**: Dash (Plotly)  
**Backend**: Existing Python monitoring system

---

## 1. Executive Summary / 執行摘要

### Purpose / 目的
建立可長期擴充的監測系統 UI，支援：
- 多資產監測（股票、加密貨幣）
- 多策略管理
- 可視化參數調整
- 訊號看板
- 人工決策流程（alert-only，不自動下單）

### Core Principles / 核心原則
1. **Alert-Only**: 系統僅產生提醒，不自動交易
2. **Human-in-the-Loop**: 所有交易決策需人工確認
3. **Modular Design**: 策略可註冊、可擴充
4. **Config-Driven**: 參數集中管理
5. **MVP First**: 先求可用，再求精緻

---

## 2. Architecture Overview / 架構總覽

### 2.1 High-Level Architecture / 高層架構

```
┌─────────────────────────────────────────────────────────────────┐
│                          User Interface                          │
│                    (Dash Multi-Page Application)                 │
├─────────────────────────────────────────────────────────────────┤
│  Dashboard │ Signals │ Parameters │ Strategies │ Actions │ System │
└────────────┴─────────┴────────────┴────────────┴─────────┴────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      UI Backend Layer                            │
│         (Flask/Dash callbacks, State Management)                 │
├─────────────────────────────────────────────────────────────────┤
│  Config Manager │ Monitoring Client │ Action Queue │ Auth/Sec   │
└─────────────────┴───────────────────┴──────────────┴────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Existing Monitoring System                    │
│                      (Unchanged Core Logic)                      │
├─────────────────────────────────────────────────────────────────┤
│  data/ │ indicators/ │ signals/ │ notifications/ │ scheduler/  │
└────────┴─────────────┴──────────┴───────────────┴───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Services                           │
│  Binance API │ Discord Webhook │ Future: Broker APIs │ DB       │
└──────────────┴─────────────────┴─────────────────────┴──────────┘
```

### 2.2 Component Responsibilities / 元件職責

| Component | Responsibility | Tech Stack |
|-----------|----------------|------------|
| **UI Frontend** | User interaction, visualization | Dash, Plotly, HTML/CSS |
| **UI Backend** | API endpoints, state management | Flask, Dash callbacks |
| **Config Manager** | Read/write config files | Python dataclasses, JSON |
| **Monitoring Client** | Interface with existing system | Import existing modules |
| **Action Queue** | Pending decisions, approvals | JSON file, in-memory queue |
| **Existing System** | Data fetch, signals, notifications | Unchanged Python modules |

### 2.3 Separation of Concerns / 關注點分離

```
UI Layer          →  Visualization, user interaction
├── Dashboard     →  Overview, status, quick stats
├── Signals       →  Signal history, current alerts
├── Parameters    →  Config editing, parameter tuning
├── Strategies    →  Strategy registry, enable/disable
├── Actions       →  Manual decisions, approval queue
└── System        →  Logs, health, settings

Service Layer     →  Business logic, data transformation
├── ConfigService →  Read/write configs
├── MonitorService→  Query monitoring status
├── SignalService →  Fetch signal history
└── ActionService →  Manage action queue

Data Layer        →  Existing monitoring system (unchanged)
├── data/         →  Data fetching
├── indicators/   →  Indicator calculations
├── signals/      →  Signal generation
├── notifications/→  Alert dispatch
└── scheduler/    →  Scheduling logic
```

---

## 3. Page Map / 頁面地圖

### 3.1 Navigation Structure / 導航結構

```
┌────────────────────────────────────────────────────┐
│  🏠 Dashboard │ Signals │ Parameters │ Strategies │ Actions │ System │
└────────────────────────────────────────────────────┘
```

### 3.2 Page Specifications / 頁面規格

#### Page 1: Dashboard / 儀表板
**URL**: `/`  
**Purpose**: System overview and quick status  
**Components**:
- System status card (running/stopped)
- Last run time and result
- Active symbols list
- Recent signals (last 5)
- Quick stats (signals today, alerts sent)
- Next scheduled run countdown

**Mock Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  System Status: 🟢 RUNNING          Last Run: 2 minutes ago │
├─────────────────────────────┬───────────────────────────────┤
│  MONITORING                 │  TODAY'S SIGNALS              │
│  ─────────────              │  ─────────────                │
│  BTCUSDT: Active            │  🔔 trend_long (BTC) 09:15    │
│  ETHUSDT: Active            │  👁️  contrarian (ETH) 08:30   │
│                             │  ─────────────────────        │
│  Scheduler: Every 5 min     │  Total: 2 signals             │
│  Next run: 3:42             │                               │
├─────────────────────────────┴───────────────────────────────┤
│  QUICK ACTIONS                                              │
│  [View Signals] [Check Parameters] [View Logs]              │
└─────────────────────────────────────────────────────────────┘
```

#### Page 2: Signals / 訊號
**URL**: `/signals`  
**Purpose**: Signal history and detail view  
**Components**:
- Signal filter (type, symbol, date range)
- Signal list table (sortable, paginated)
- Signal detail modal/card
- Real-time alert feed (auto-refresh)
- Export to CSV

**Mock Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  FILTER: [All Types ▼] [All Symbols ▼] [Last 24h ▼] [Search]│
├─────────────────────────────────────────────────────────────┤
│  TIME           │ SYMBOL   │ TYPE              │ STATUS    │
│  ─────────────────────────────────────────────────────────  │
│  09:15:32       │ BTCUSDT  │ 📈 trend_long     │ ✅ Confirmed│
│  08:30:15       │ ETHUSDT  │ 👁️  contrarian    │ Watch Only│
│  ...                                                      │
├─────────────────────────────────────────────────────────────┤
│  [◀ Prev] Page 1 of 5 [Next ▶]    [Export CSV]             │
└─────────────────────────────────────────────────────────────┘
```

#### Page 3: Parameters / 參數
**URL**: `/parameters`  
**Purpose**: View and edit monitoring parameters  
**Components**:
- Parameter categories (tabs)
- Parameter list with current values
- Parameter descriptions/tooltips
- Edit mode toggle
- Save/Reset buttons
- Change history log

**Categories**:
- General (intervals, thresholds)
- Indicators (MA periods, volume windows)
- Signals (cooldowns, confirmation levels)
- Notifications (channels, formats)

**Mock Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  [General] [Indicators] [Signals] [Notifications]          │
├─────────────────────────────────────────────────────────────┤
│  MONITORING INTERVALS                                       │
│  ─────────────────────                                      │
│  Check Interval (min)    [  5  ]  ⓘ How often to check    │
│  Max Run History         [ 100 ]  ⓘ Number of runs to keep│
│                                                             │
│  SIGNAL THRESHOLDS                                          │
│  ─────────────────────                                      │
│  Volume Spike Threshold  [ 1.5 ]  ⓘ x times average        │
│  Cooldown Period (min)   [ 15  ]  ⓘ Minimum between signals│
├─────────────────────────────────────────────────────────────┤
│                           [Cancel] [Save Changes]          │
└─────────────────────────────────────────────────────────────┘
```

#### Page 4: Strategies / 策略
**URL**: `/strategies`  
**Purpose**: Strategy registry and management  
**Components**:
- Strategy list (registered strategies)
- Enable/disable toggles
- Strategy detail view
- Add new strategy (placeholder for future)
- Strategy performance metrics (placeholder)

**Mock Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  REGISTERED STRATEGIES                          [+ New ▼]  │
├─────────────────────────────────────────────────────────────┤
│  NAME              │ TYPE      │ ASSETS    │ STATUS        │
│  ─────────────────────────────────────────────────────────  │
│  ☑️ MA Cross Trend │ Trend     │ BTC, ETH  │ 🟢 Active     │
│  ☑️ Contrarian Watch│ Contrarian│ BTC, ETH  │ 🟢 Active     │
│  ☐ RSI Oversold    │ Mean Rev  │ -         │ ⚪ Disabled   │
│  ...                                                      │
├─────────────────────────────────────────────────────────────┤
│  Strategy Extensibility                                     │
│  ─────────────────────                                      │
│  • Strategies are registered via config/strategies.json     │
│  • Custom strategies: TBD (Phase 3)                         │
└─────────────────────────────────────────────────────────────┘
```

#### Page 5: Actions / 行動
**URL**: `/actions`  
**Purpose**: Manual decision queue for signal-based actions  
**Components**:
- Pending actions queue
- Action history
- Approve/Reject/Snooze buttons
- Action detail view
- Notes field for each decision

**Action Types**:
- `SIGNAL_CONFIRMED` → Suggest manual position entry
- `WATCH_TRIGGERED` → Suggest adding to watchlist
- `MANUAL_REVIEW` → Flagged for human review

**Mock Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  PENDING ACTIONS                              [History ▼]  │
├─────────────────────────────────────────────────────────────┤
│  #  │ TIME    │ SIGNAL           │ SUGGESTION    │ ACTIONS │
│  ─────────────────────────────────────────────────────────  │
│  1  │ 09:15   │ BTC trend_long   │ Consider long │ [✓] [✗] [⏸]│
│     │         │ @ $69,250        │               │         │
├─────────────────────────────────────────────────────────────┤
│  Note: _________________________                           │
├─────────────────────────────────────────────────────────────┤
│  ACTION QUEUE STATUS                                        │
│  ─────────────────────                                      │
│  Pending: 1  │  Approved Today: 0  │  Rejected Today: 0     │
└─────────────────────────────────────────────────────────────┘
```

#### Page 6: System / 系統
**URL**: `/system`  
**Purpose**: System logs, health, and settings  
**Components**:
- System health indicators
- Log viewer (tail -f style)
- Scheduler controls (start/stop)
- Config file locations
- Version info

**Mock Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  SYSTEM HEALTH                                              │
├─────────────────────────────────────────────────────────────┤
│  Scheduler: 🟢 Running (PID: 69791)                        │
│  Last Check: 2 min ago                                      │
│  Data API: 🟢 Connected                                     │
│  Discord: 🟢 Connected                                      │
├─────────────────────────────────────────────────────────────┤
│  SCHEDULER CONTROLS                                         │
│  [Restart] [Stop] [View Config]                            │
├─────────────────────────────────────────────────────────────┤
│  RECENT LOGS                                                │
│  ─────────────────────                                      │
│  [2024-04-07 20:35:40] Run #17 completed, no signals        │
│  [2024-04-07 20:30:39] Run #16 completed, no signals        │
│  ...                                                      │
│  [View Full Logs]                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow / 資料流

### 4.1 Read Flows / 讀取流程

#### Flow 1: Monitoring Status
```
UI Dashboard → MonitorService → scheduler.log → Display
                    │
                    └──→ Check PID file → System status
```

#### Flow 2: Signal History
```
UI Signals → SignalService → alerts/alerts.json → Display
                  │
                  └──→ Fallback: scan scheduler.log
```

#### Flow 3: Parameters
```
UI Parameters → ConfigService → config/*.json → Display
```

### 4.2 Write Flows / 寫入流程

#### Flow 1: Parameter Update
```
UI Parameters → ConfigService → Validate → Backup → Write config/*.json
                                                    │
                                                    └──→ Notify scheduler (if hot-reload)
```

#### Flow 2: Action Decision
```
UI Actions → ActionService → Update action_queue.json
                                   │
                                   └──→ Log decision → Archive
```

### 4.3 Real-Time Updates / 即時更新

```
Monitoring System → alerts/alerts.json (append)
                          │
                          ▼
                   UI Signals (polling or websocket)
                          │
                          ▼
                   Auto-refresh every 30s
```

---

## 5. Config Design / 配置設計

### 5.1 Config Files / 配置文件

```
config/
├── monitoring_params.json    # Core monitoring parameters
├── strategies.json           # Strategy registry
├── assets.json               # Asset/symbol definitions
├── channel_config.json       # Notification channels
└── ui_config.json            # UI-specific settings
```

### 5.2 monitoring_params.json

```json
{
  "version": "1.0.0",
  "monitoring": {
    "check_interval_minutes": 5,
    "max_run_history": 100,
    "prevent_overlap": true
  },
  "indicators": {
    "ma_periods": {
      "short": 5,
      "medium": 20,
      "long": 240
    },
    "volume": {
      "window": 20,
      "spike_threshold": 1.5
    }
  },
  "signals": {
    "cooldown_minutes": {
      "trend_long": 30,
      "trend_short": 30,
      "contrarian_watch": 15
    },
    "consecutive_candles": 4
  },
  "notifications": {
    "default_language": "zh",
    "channels": ["console", "discord"]
  }
}
```

### 5.3 strategies.json

```json
{
  "version": "1.0.0",
  "strategies": [
    {
      "id": "ma_cross_trend",
      "name": "MA Cross Trend",
      "type": "trend",
      "enabled": true,
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "conditions": [
        "close_vs_ma240",
        "ma5_cross_ma20",
        "volume_spike"
      ],
      "parameters": {
        "volume_threshold": 1.5
      }
    },
    {
      "id": "contrarian_watch",
      "name": "Contrarian Watch",
      "type": "contrarian",
      "enabled": true,
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "conditions": [
        "close_vs_ma240",
        "consecutive_candles"
      ],
      "parameters": {
        "consecutive_count": 4
      }
    }
  ]
}
```

### 5.4 assets.json

```json
{
  "version": "1.0.0",
  "assets": [
    {
      "symbol": "BTCUSDT",
      "name": "Bitcoin",
      "type": "crypto",
      "exchange": "binance",
      "enabled": true,
      "timeframes": ["1m", "5m", "15m"]
    },
    {
      "symbol": "ETHUSDT",
      "name": "Ethereum",
      "type": "crypto",
      "exchange": "binance",
      "enabled": true,
      "timeframes": ["1m", "5m", "15m"]
    }
  ],
  "asset_groups": [
    {
      "id": "crypto_major",
      "name": "Major Cryptocurrencies",
      "assets": ["BTCUSDT", "ETHUSDT"]
    }
  ]
}
```

### 5.5 ui_config.json

```json
{
  "version": "1.0.0",
  "ui": {
    "theme": "light",
    "refresh_interval_seconds": 30,
    "max_signals_display": 50,
    "default_page": "dashboard"
  },
  "features": {
    "enable_realtime": false,
    "enable_actions": true,
    "enable_strategy_editing": false
  }
}
```

---

## 6. Strategy Extensibility Design / 策略擴充設計

### 6.1 Strategy Interface / 策略介面

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class StrategyResult:
    """Strategy evaluation result"""
    signal_generated: bool
    signal_type: Optional[str]
    confidence: float
    metadata: Dict[str, Any]

class BaseStrategy(ABC):
    """Base class for all strategies"""
    
    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique strategy identifier"""
        pass
    
    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable strategy name"""
        pass
    
    @abstractmethod
    def evaluate(self, data: Dict[str, Any]) -> StrategyResult:
        """
        Evaluate strategy against market data
        
        Args:
            data: Market data including prices, indicators
            
        Returns:
            StrategyResult with signal decision
        """
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Return configurable parameters"""
        pass
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate parameter values (optional override)"""
        return True
```

### 6.2 Strategy Registry / 策略註冊表

```python
class StrategyRegistry:
    """Central registry for all strategies"""
    
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
    
    def register(self, strategy: BaseStrategy) -> None:
        """Register a strategy"""
        self._strategies[strategy.strategy_id] = strategy
    
    def get(self, strategy_id: str) -> Optional[BaseStrategy]:
        """Get strategy by ID"""
        return self._strategies.get(strategy_id)
    
    def list_enabled(self) -> List[BaseStrategy]:
        """List all enabled strategies"""
        # Filter by config
        config = load_strategies_config()
        enabled_ids = [s["id"] for s in config["strategies"] if s["enabled"]]
        return [self._strategies[sid] for sid in enabled_ids if sid in self._strategies]
```

### 6.3 Strategy Loading / 策略載入

```python
def load_strategies_from_config() -> StrategyRegistry:
    """Load all enabled strategies from config"""
    registry = StrategyRegistry()
    config = load_strategies_config()
    
    for strategy_config in config["strategies"]:
        if not strategy_config["enabled"]:
            continue
            
        # Load strategy class dynamically
        strategy_class = load_strategy_class(strategy_config["id"])
        strategy = strategy_class(parameters=strategy_config.get("parameters", {}))
        registry.register(strategy)
    
    return registry
```

---

## 7. Manual Action Queue Design / 人工行動佇列設計

### 7.1 Action Queue Data Model / 行動佇列資料模型

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

class ActionStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SNOOZED = "snoozed"
    EXPIRED = "expired"

class ActionType(Enum):
    SIGNAL_CONFIRMED = "signal_confirmed"
    WATCH_TRIGGERED = "watch_triggered"
    MANUAL_REVIEW = "manual_review"

@dataclass
class ActionItem:
    """An item in the action queue"""
    action_id: str
    action_type: ActionType
    status: ActionStatus
    created_at: datetime
    signal_id: Optional[str]  # Reference to originating signal
    symbol: str
    suggestion: str
    metadata: Dict[str, Any]
    
    # Decision fields (filled when acted upon)
    decided_at: Optional[datetime] = None
    decision: Optional[str] = None  # approve/reject/snooze
    decision_note: Optional[str] = None
    decided_by: Optional[str] = None
    
    # Snooze fields
    snooze_until: Optional[datetime] = None
```

### 7.2 Action Queue File Format / 行動佇列檔案格式

```json
{
  "version": "1.0.0",
  "queue": [
    {
      "action_id": "act_20240407_091532_001",
      "action_type": "signal_confirmed",
      "status": "pending",
      "created_at": "2024-04-07T09:15:32Z",
      "signal_id": "sig_20240407_091532_btc",
      "symbol": "BTCUSDT",
      "suggestion": "Consider long position",
      "metadata": {
        "signal_type": "trend_long",
        "price": 69250.50,
        "confidence": 0.85
      },
      "decided_at": null,
      "decision": null,
      "decision_note": null,
      "decided_by": null,
      "snooze_until": null
    }
  ],
  "history": [
    {
      "action_id": "act_20240406_143022_001",
      "action_type": "signal_confirmed",
      "status": "approved",
      "created_at": "2024-04-06T14:30:22Z",
      "decided_at": "2024-04-06T14:35:10Z",
      "decision": "approved",
      "decision_note": "Good setup, entering",
      "decided_by": "user_001"
    }
  ]
}
```

### 7.3 Action Flow / 行動流程

```
1. Signal Generated
        │
        ▼
2. Create Action Item (status: PENDING)
        │
        ▼
3. Display in UI Actions Page
        │
        ▼
4. User Decision:
   ├─ Approve → status: APPROVED → Log → Archive
   ├─ Reject  → status: REJECTED → Log → Archive
   └─ Snooze  → status: SNOOZED  → Set snooze_until → Back to queue
        │
        ▼
5. If snooze expired → status: PENDING (reactivate)
```

### 7.4 Action Service Interface / 行動服務介面

```python
class ActionService:
    """Service for managing action queue"""
    
    def __init__(self, queue_file: str = "state/action_queue.json"):
        self.queue_file = queue_file
        self._load_queue()
    
    def get_pending(self) -> List[ActionItem]:
        """Get all pending actions"""
        return [a for a in self.queue if a.status == ActionStatus.PENDING]
    
    def get_history(self, limit: int = 50) -> List[ActionItem]:
        """Get action history"""
        return sorted(self.history, key=lambda x: x.created_at, reverse=True)[:limit]
    
    def create_from_signal(self, signal: Signal) -> ActionItem:
        """Create action item from signal"""
        action = ActionItem(
            action_id=generate_action_id(),
            action_type=self._map_signal_to_action(signal),
            status=ActionStatus.PENDING,
            created_at=datetime.now(),
            signal_id=signal.id,
            symbol=signal.symbol,
            suggestion=self._generate_suggestion(signal),
            metadata=signal.to_dict()
        )
        self.queue.append(action)
        self._save_queue()
        return action
    
    def approve(self, action_id: str, note: Optional[str] = None) -> ActionItem:
        """Approve an action"""
        action = self._find_action(action_id)
        action.status = ActionStatus.APPROVED
        action.decided_at = datetime.now()
        action.decision = "approve"
        action.decision_note = note
        self._move_to_history(action)
        self._save_queue()
        return action
    
    def reject(self, action_id: str, note: Optional[str] = None) -> ActionItem:
        """Reject an action"""
        action = self._find_action(action_id)
        action.status = ActionStatus.REJECTED
        action.decided_at = datetime.now()
        action.decision = "reject"
        action.decision_note = note
        self._move_to_history(action)
        self._save_queue()
        return action
    
    def snooze(self, action_id: str, minutes: int, note: Optional[str] = None) -> ActionItem:
        """Snooze an action"""
        action = self._find_action(action_id)
        action.status = ActionStatus.SNOOZED
        action.snooze_until = datetime.now() + timedelta(minutes=minutes)
        action.decision_note = note
        self._save_queue()
        return action
```

---

## 8. Phased Roadmap / 分階段路線圖

### Phase 1: UI Master Plan ✅ (This Document)
**Duration**: 1 task  
**Deliverables**:
- ✅ `ui/UI_MASTER_PLAN.md`
- ✅ Architecture overview
- ✅ Page map
- ✅ Data flow design
- ✅ Config design
- ✅ Strategy extensibility design
- ✅ Manual action queue design

### Phase 2: Config Centralization
**Duration**: 1 task  
**Deliverables**:
- `config/monitoring_params.json`
- `config/strategies.json`
- `config/assets.json`
- Update existing code to read from configs
- Config validation utilities

**Files Modified**:
- `indicators/calculator.py` (read thresholds from config)
- `signals/engine.py` (read cooldowns from config)
- `app/scheduler.py` (read intervals from config)

### Phase 3: Dash App Skeleton
**Duration**: 1 task  
**Deliverables**:
- `ui/app.py` (main entry)
- `ui/pages/dashboard.py`
- `ui/pages/signals.py`
- `ui/pages/parameters.py`
- `ui/pages/strategies.py`
- `ui/pages/actions.py`
- `ui/pages/system.py`
- `ui/components/` (reusable components)
- `requirements-ui.txt`

**UI Features**:
- Multi-page navigation
- Basic layout for each page
- Placeholder content

### Phase 4: Connect Monitoring Status
**Duration**: 1 task  
**Deliverables**:
- `ui/services/monitor_service.py`
- Real-time status display
- Scheduler status integration
- Last run time display
- Signal count display

**UI Features**:
- Dashboard shows live status
- System page shows health
- Auto-refresh (30s interval)

### Phase 5: Parameter Panel MVP
**Duration**: 1 task  
**Deliverables**:
- Config reading service
- Parameter display with descriptions
- Edit mode (read-only for MVP)
- Parameter categorization

**UI Features**:
- View all parameters
- Tooltips with descriptions
- Organized by category

### Phase 6: Action Queue MVP
**Duration**: 1 task  
**Deliverables**:
- `ui/services/action_service.py`
- `state/action_queue.json` initialization
- Pending actions display
- Approve/Reject/Snooze buttons (UI only)
- Action history view

**UI Features**:
- See pending actions
- See action history
- Button interactions (log to console for MVP)

### Phase 7: UI MVP Review
**Duration**: 1 task  
**Deliverables**:
- `outputs/T-039_ui_mvp_review.md`
- Usability assessment
- Remaining work documentation
- Next phase recommendations

**Review Contents**:
- What is usable now
- What remains placeholder
- What is ready for next phase
- UI foundation status

---

## 9. Technical Specifications / 技術規格

### 9.1 Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| UI Framework | Dash (Plotly) | ^2.14 |
| Web Server | Flask | (bundled with Dash) |
| Styling | Dash Bootstrap Components | ^1.4 |
| Charts | Plotly | ^5.18 |
| State | File-based JSON | - |
| Python | Python | 3.9+ |

### 9.2 File Structure

```
ui/
├── app.py                    # Main Dash application entry
├── config.py                 # UI configuration
├── requirements.txt          # UI dependencies
│
├── pages/                    # Page modules (Dash multi-page)
│   ├── __init__.py
│   ├── dashboard.py          # Dashboard page
│   ├── signals.py            # Signals page
│   ├── parameters.py         # Parameters page
│   ├── strategies.py         # Strategies page
│   ├── actions.py            # Actions page
│   └── system.py             # System page
│
├── components/               # Reusable UI components
│   ├── __init__.py
│   ├── status_card.py        # System status display
│   ├── signal_table.py       # Signal list table
│   ├── parameter_form.py     # Parameter editing form
│   └── action_buttons.py     # Approve/Reject/Snooze buttons
│
└── services/                 # Business logic layer
    ├── __init__.py
    ├── config_service.py     # Config read/write
    ├── monitor_service.py    # Monitor status queries
    ├── signal_service.py     # Signal history queries
    └── action_service.py     # Action queue management
```

### 9.3 Dependencies

```txt
# requirements-ui.txt
dash>=2.14.0
dash-bootstrap-components>=1.4.0
plotly>=5.18.0
pandas>=2.0.0
```

### 9.4 Running the UI

```bash
# Install dependencies
pip install -r ui/requirements.txt

# Run the UI
python ui/app.py

# Access at http://localhost:8050
```

---

## 10. Security Considerations / 安全考量

### 10.1 Alert-Only Enforcement / 僅提醒強制

- UI will NEVER connect to trading APIs
- Action buttons only log decisions, never execute trades
- All "approvals" are for logging purposes only
- Clear labeling: "APPROVED (Logged) - No Trade Executed"

### 10.2 Config Protection / 配置保護

- Config backups before edits
- Validation before saving
- Read-only mode by default
- Audit log for config changes

### 10.3 Access Control (Future) / 存取控制（未來）

```json
{
  "access_control": {
    "enabled": false,
    "users": [
      {
        "username": "admin",
        "role": "admin",
        "permissions": ["read", "write", "config", "actions"]
      }
    ]
  }
}
```

---

## 11. Future Extensions / 未來擴充

### Phase 8+ Ideas

1. **Real-time WebSocket**: Live price feeds, instant signal alerts
2. **Advanced Charts**: TradingView-style candlestick charts with indicators
3. **Strategy Builder**: Visual strategy creation interface
4. **Backtesting UI**: Run and visualize backtests
5. **Multi-asset Support**: Stocks, forex, commodities
6. **Performance Analytics**: Strategy performance metrics, P&L tracking
7. **Mobile Responsive**: Better mobile experience
8. **Authentication**: Login system, multi-user support
9. **Database Backend**: Move from JSON files to proper database
10. **Plugin System**: Third-party strategy plugins

---

## 12. Summary / 總結

This UI Master Plan establishes the foundation for an extensible monitoring system UI that:

✅ **Preserves existing backend**: All monitoring logic stays unchanged  
✅ **Enables human control**: Alert-only with manual decision workflow  
✅ **Supports expansion**: Config-driven, strategy registry pattern  
✅ **MVP-first approach**: 7 phases to usable UI, not perfect UI  
✅ **Dash-based**: Single Python codebase, easy deployment  

### Next Steps

1. **Phase 2**: Config Centralization
2. **Phase 3**: Dash App Skeleton
3. **Phase 4-6**: Feature implementation
4. **Phase 7**: MVP Review

---

**Created by**: kimiclaw_bot  
**Date**: 2026-04-07  
**Version**: 1.0.0  
**Status**: Phase 1 Complete
