# T-039: UI Program Summary / UI 程式總結

**Task ID**: T-039  
**Title**: Plan and Build Extensible UI Prototype for Monitoring System  
**Date**: 2026-04-07  
**Phase**: 1 of 7 (UI Master Plan)  
**Status**: ✅ Phase 1 Complete / 第一階段完成  
**Commit**: [PENDING]

---

## 1. Program Overview / 程式總覽

### Goal / 目標
建立可長期擴充的 BTC/ETH 監測與研究系統 UI 雛形，支援未來新增股票、幣別、策略、可視化參數調整，以及人工按鈕決定是否下單。

### Core Requirements / 核心需求
1. ✅ Alert-only: No automatic trading
2. ✅ Human-in-the-loop: Manual decision workflow
3. ✅ Extensible: Config-driven, strategy registry
4. ✅ Multi-asset: Support stocks, crypto
5. ✅ MVP-first: Usable before perfect

### Tech Stack / 技術棧
- **UI Framework**: Dash (Plotly)
- **Backend**: Existing Python monitoring system (unchanged)
- **State**: File-based JSON
- **Language**: Python 3.9+

---

## 2. Phase 1: UI Master Plan / 第一階段：UI 主規格 ✅

### Deliverables / 交付物

| File | Size | Description |
|------|------|-------------|
| `ui/UI_MASTER_PLAN.md` | 29,653 bytes | Complete UI specification |

### Content Overview / 內容概述

| Section | Content |
|---------|---------|
| Architecture Overview | 3-layer architecture (UI → Service → Data) |
| Page Map | 6 pages: Dashboard, Signals, Parameters, Strategies, Actions, System |
| Data Flow | Read/write flows, real-time updates |
| Config Design | 5 config files defined |
| Strategy Extensibility | Base class, registry pattern, loading mechanism |
| Manual Action Queue | ActionItem model, workflow, service interface |
| Phased Roadmap | 7 phases defined |
| Technical Specs | Tech stack, file structure, dependencies |

---

## 3. Page Specifications / 頁面規格

### Page 1: Dashboard / 儀表板
- **URL**: `/`
- **Components**: Status card, last run, active symbols, recent signals, quick stats
- **Purpose**: System overview at a glance

### Page 2: Signals / 訊號
- **URL**: `/signals`
- **Components**: Filter, sortable table, detail modal, real-time feed
- **Purpose**: Signal history and alert viewing

### Page 3: Parameters / 參數
- **URL**: `/parameters`
- **Components**: Category tabs, parameter list, edit mode, descriptions
- **Purpose**: View and edit monitoring parameters

### Page 4: Strategies / 策略
- **URL**: `/strategies`
- **Components**: Strategy list, enable/disable toggles, detail view
- **Purpose**: Strategy registry and management

### Page 5: Actions / 行動
- **URL**: `/actions`
- **Components**: Pending queue, action history, Approve/Reject/Snooze buttons
- **Purpose**: Manual decision workflow

### Page 6: System / 系統
- **URL**: `/system`
- **Components**: Health indicators, log viewer, scheduler controls
- **Purpose**: System monitoring and management

---

## 4. Config Files Design / 配置文件設計

### 4.1 Config Structure

```
config/
├── monitoring_params.json    # Core monitoring parameters
├── strategies.json           # Strategy registry
├── assets.json               # Asset/symbol definitions
├── channel_config.json       # Notification channels (exists)
└── ui_config.json            # UI-specific settings
```

### 4.2 monitoring_params.json

Key sections:
- `monitoring`: check_interval_minutes, max_run_history
- `indicators`: ma_periods, volume settings
- `signals`: cooldown_minutes, consecutive_candles
- `notifications`: default_language, channels

### 4.3 strategies.json

Strategy registry with:
- id, name, type, enabled
- symbols list
- conditions list
- parameters

### 4.4 assets.json

Asset definitions with:
- symbol, name, type, exchange
- enabled status
- timeframes list

---

## 5. Strategy Extensibility / 策略擴充

### Design Pattern
- **Base Class**: `BaseStrategy` with abstract methods
- **Registry**: `StrategyRegistry` for centralized management
- **Loading**: Dynamic loading from config

### Interface Methods
```python
@property
def strategy_id(self) -> str

@property
def strategy_name(self) -> str

def evaluate(self, data: Dict) -> StrategyResult

def get_parameters(self) -> Dict
```

### Current Strategies
1. **MA Cross Trend**: Trend following with MA cross + volume
2. **Contrarian Watch**: Overbought/oversold detection

---

## 6. Manual Action Queue / 人工行動佇列

### Data Model
```python
@dataclass
class ActionItem:
    action_id: str
    action_type: ActionType  # SIGNAL_CONFIRMED, WATCH_TRIGGERED, MANUAL_REVIEW
    status: ActionStatus      # PENDING, APPROVED, REJECTED, SNOOZED, EXPIRED
    symbol: str
    suggestion: str
    metadata: Dict
    # ... decision fields
```

### Workflow
1. Signal generated → Create ActionItem (PENDING)
2. Display in Actions page
3. User decision: Approve / Reject / Snooze
4. Log decision → Archive

### File Location
`state/action_queue.json`

---

## 7. Phased Roadmap / 分階段路線圖

### Phase 1: UI Master Plan ✅ COMPLETE
- Architecture, page map, data flow
- Config design, strategy extensibility
- Action queue design

### Phase 2: Config Centralization ⏳ PENDING
- Create config files
- Update existing code to read configs
- Config validation utilities

### Phase 3: Dash App Skeleton ⏳ PENDING
- Multi-page Dash app structure
- Page layouts with placeholders
- Navigation and routing

### Phase 4: Connect Monitoring Status ⏳ PENDING
- Monitor service
- Real-time status display
- Auto-refresh

### Phase 5: Parameter Panel MVP ⏳ PENDING
- Config reading
- Parameter display
- Read-only for MVP

### Phase 6: Action Queue MVP ⏳ PENDING
- Action service
- Pending actions display
- Buttons (UI only for MVP)

### Phase 7: UI MVP Review ⏳ PENDING
- Usability assessment
- Remaining work doc
- Next phase recommendations

---

## 8. Technical Specifications / 技術規格

### File Structure
```
ui/
├── app.py                    # Main entry
├── config.py                 # UI config
├── requirements.txt          # Dependencies
├── pages/                    # 6 page modules
│   ├── dashboard.py
│   ├── signals.py
│   ├── parameters.py
│   ├── strategies.py
│   ├── actions.py
│   └── system.py
├── components/               # Reusable components
└── services/                 # Business logic
    ├── config_service.py
    ├── monitor_service.py
    ├── signal_service.py
    └── action_service.py
```

### Dependencies
```
dash>=2.14.0
dash-bootstrap-components>=1.4.0
plotly>=5.18.0
pandas>=2.0.0
```

### Running the UI
```bash
pip install -r ui/requirements.txt
python ui/app.py
# Access at http://localhost:8050
```

---

## 9. Security & Safety / 安全與保護

### Alert-Only Enforcement
- ✅ UI never connects to trading APIs
- ✅ Action buttons only log decisions
- ✅ Clear labeling: "APPROVED (Logged) - No Trade"
- ✅ All approvals for logging only

### Config Protection
- Config backups before edits
- Validation before saving
- Read-only by default
- Audit log for changes

---

## 10. Next Steps / 下一步

### Immediate / 立即
1. **Phase 2**: Create config files and update existing code
2. **Phase 3**: Build Dash app skeleton
3. Continue through phases 4-7

### Child Tasks to Create / 待建立子任務

| Task ID | Title | Phase |
|---------|-------|-------|
| T-039-02 | Config Centralization | Phase 2 |
| T-039-03 | Dash App Skeleton | Phase 3 |
| T-039-04 | Connect Monitoring Status | Phase 4 |
| T-039-05 | Parameter Panel MVP | Phase 5 |
| T-039-06 | Action Queue MVP | Phase 6 |
| T-039-07 | UI MVP Review | Phase 7 |

---

## 11. Summary / 總結

### What Was Accomplished / 已完成
✅ Complete UI architecture specification  
✅ 6-page application design  
✅ Config-driven design  
✅ Strategy extensibility pattern  
✅ Manual action queue design  
✅ 7-phase roadmap defined  

### What's Ready / 已就緒
- UI specification document
- Page layouts (mockups)
- Data models (ActionItem, Strategy, etc.)
- Config schemas
- Service interfaces

### What's Next / 接下來
- Implement config files (Phase 2)
- Build Dash skeleton (Phase 3)
- Connect to monitoring system (Phase 4)
- Build parameter panel (Phase 5)
- Build action queue (Phase 6)
- Review and iterate (Phase 7)

---

**Created by**: kimiclaw_bot  
**Date**: 2026-04-07  
**Phase 1 Status**: ✅ Complete  
**Ready for**: Phase 2 - Config Centralization
