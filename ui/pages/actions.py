"""
Actions Page / 行動頁面

Manual decision queue for signal-based actions.
訊號導向行動的人工決策佇列。
"""

import dash
from dash import dcc, html, callback, Output, Input, State, ALL, MATCH
import dash_bootstrap_components as dbc
import sys
import json
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Import ActionQueueService from dedicated service module
# 從專用服務模組匯入 ActionQueueService
from ui.services.action_service import ActionQueueService, load_pending_actions, load_history, process_decision, get_today_stats, clear_history

# Register page / 註冊頁面
dash.register_page(__name__, path="/actions", title="Actions")

# Global service instance / 全局服務實例
_action_service = ActionQueueService()


# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Actions", className="mb-4"),
        html.P("Manual decision queue for signals / 訊號的人工決策佇列", className="text-muted"),
        
        html.Hr(),
        
        # Status Alert / 狀態提示
        html.Div(id="actions-status-alert"),
        
        # Pending Actions / 待處理行動
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Pending Actions / 待處理行動", className="mb-0 d-inline"),
                        dbc.Badge("0", color="secondary", className="ms-2", id="actions-pending-count"),
                        dbc.Button(
                            "🔄 Refresh / 刷新",
                            size="sm",
                            color="outline-primary",
                            id="actions-refresh-btn",
                            className="float-end"
                        )
                    ]
                ),
                dbc.CardBody(
                    id="actions-pending-list",
                    children=[
                        html.Div(
                            [
                                html.P("📭 No pending actions / 無待處理行動", className="text-muted text-center py-4"),
                                html.P("New signals will appear here for your decision / 新訊號將在此顯示供您決策", className="text-muted text-center small")
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Action Queue Status / 行動佇列狀態
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3("--", id="actions-stats-pending", className="text-center"),
                                    html.P("Pending / 待處理", className="text-muted text-center mb-0")
                                ]
                            )
                        ],
                        color="warning",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3("--", id="actions-stats-approved", className="text-center"),
                                    html.P("Approved Today / 今日核准", className="text-muted text-center mb-0")
                                ]
                            )
                        ],
                        color="success",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3("--", id="actions-stats-rejected", className="text-center"),
                                    html.P("Rejected Today / 今日拒絕", className="text-muted text-center mb-0")
                                ]
                            )
                        ],
                        color="danger",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3("--", id="actions-stats-snoozed", className="text-center"),
                                    html.P("Snoozed / 暫緩", className="text-muted text-center mb-0")
                                ]
                            )
                        ],
                        color="info",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
            ]
        ),
        
        # Action History / 行動歷史
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Action History / 行動歷史", className="mb-0 d-inline"),
                        dbc.Button(
                            "Clear History / 清除歷史",
                            size="sm",
                            color="outline-danger",
                            id="actions-clear-history-btn",
                            className="float-end"
                        )
                    ]
                ),
                dbc.CardBody(
                    id="actions-history-list",
                    children=[
                        html.Div(
                            [
                                html.P("📜 No action history / 無行動歷史", className="text-muted text-center py-4"),
                                html.P("Approved, rejected, and snoozed actions will appear here", className="text-muted text-center small")
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # How It Works / 運作方式
        dbc.Card(
            [
                dbc.CardHeader("How It Works / 運作方式"),
                dbc.CardBody(
                    [
                        html.H6("Action Queue Workflow / 行動佇列流程", className="card-subtitle mb-3"),
                        html.Ol(
                            [
                                html.Li("Signal is generated by the monitoring system / 監測系統產生訊號"),
                                html.Li("Action item is created and added to pending queue / 建立行動項目並加入待處理佇列"),
                                html.Li("You review the signal and decide / 您審查訊號並決定:"),
                                html.Ul(
                                    [
                                        html.Li([
                                            html.Strong("Approve / 核准", className="text-success"),
                                            " - Log your approval (no auto-trading) / 記錄您的核准（無自動交易）"
                                        ]),
                                        html.Li([
                                            html.Strong("Reject / 拒絕", className="text-danger"),
                                            " - Decline the signal / 拒絕該訊號"
                                        ]),
                                        html.Li([
                                            html.Strong("Snooze / 暫緩", className="text-info"),
                                            " - Postpone decision for 30 minutes / 延後決策 30 分鐘"
                                        ]),
                                    ],
                                    className="mb-2"
                                ),
                                html.Li("Decision is logged for your records / 決策被記錄供您留存"),
                            ]
                        ),
                        
                        dbc.Alert(
                            [
                                html.Strong("⚠️ Important / 重要"),
                                html.Br(),
                                "This is an ALERT-ONLY system. Actions are logged but NEVER executed automatically."
                                " / 這是僅提醒系統。行動被記錄但絕不自動執行。"
                            ],
                            color="warning",
                            className="mt-3"
                        )
                    ]
                )
            ]
        ),
        
        # Confirmation Modal for Clear History / 清除歷史確認對話框
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Confirm Clear History / 確認清除歷史")),
                dbc.ModalBody(
                    "Are you sure you want to clear all action history? This cannot be undone.\n\n"
                    "確定要清除所有行動歷史嗎？此操作無法復原。"
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button(
                            "Cancel / 取消",
                            id="clear-cancel",
                            color="secondary",
                            className="me-2"
                        ),
                        dbc.Button(
                            "Clear All / 全部清除",
                            id="clear-confirm",
                            color="danger"
                        ),
                    ]
                ),
            ],
            id="clear-history-modal",
            is_open=False,
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="actions-interval",
            interval=30*1000,  # 30 seconds
            n_intervals=0
        ),
        
        # Store for action data / 行動資料儲存
        dcc.Store(id="actions-store", data={"pending": [], "history": [], "stats": {}})
    ],
    fluid=True
)


def render_pending_action_card(action: Dict[str, Any]) -> dbc.Card:
    """Render a pending action card with approve/reject/snooze buttons"""
    action_type = action.get("type", "SIGNAL")
    symbol = action.get("symbol", "UNKNOWN")
    suggestion = action.get("suggestion", "Review signal")
    signal_type = action.get("signal_type", "")
    
    type_colors = {
        "TREND_LONG": "success",
        "TREND_SHORT": "danger",
        "CONTRARIAN_WATCH": "info",
        "SIGNAL_CONFIRMED": "primary",
        "WATCH_TRIGGERED": "info",
        "MANUAL_REVIEW": "warning"
    }
    
    type_labels = {
        "TREND_LONG": "Trend Long",
        "TREND_SHORT": "Trend Short",
        "CONTRARIAN_WATCH": "Contrarian Watch",
        "SIGNAL_CONFIRMED": "Signal Confirmed",
        "WATCH_TRIGGERED": "Watch Triggered",
        "MANUAL_REVIEW": "Manual Review"
    }
    
    action_id = action.get("id", "")
    created_at = action.get("created_at", "")
    
    # Format time
    time_str = created_at
    if "T" in created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except:
            pass
    
    # Snooze info
    snooze_info = None
    if action.get("snooze_count", 0) > 0:
        snooze_info = dbc.Badge(
            f"⏸ Snoozed {action['snooze_count']}x",
            color="info",
            className="ms-2"
        )
    
    return dbc.Card(
        [
            dbc.CardHeader(
                [
                    dbc.Badge(
                        type_labels.get(action_type, action_type),
                        color=type_colors.get(action_type, "secondary")
                    ),
                    snooze_info,
                    html.Small(
                        time_str,
                        className="text-muted ms-auto"
                    )
                ],
                className="d-flex justify-content-between align-items-center"
            ),
            dbc.CardBody(
                [
                    html.H5(
                        [
                            f"📊 {symbol}",
                            dbc.Badge(signal_type, color="secondary", className="ms-2") if signal_type else None
                        ],
                        className="card-title"
                    ),
                    html.P(suggestion, className="card-text"),
                    
                    # Signal details if available
                    html.Div(
                        render_signal_details(action.get("details", {})),
                        className="mb-3"
                    ) if action.get("details") else None,
                    
                    html.Hr(),
                    
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "✓ Approve / 核准",
                                color="success",
                                size="sm",
                                className="me-2",
                                id={"type": "approve-btn", "index": action_id}
                            ),
                            dbc.Button(
                                "✗ Reject / 拒絕",
                                color="danger",
                                size="sm",
                                className="me-2",
                                id={"type": "reject-btn", "index": action_id}
                            ),
                            dbc.Button(
                                "⏸ Snooze / 暫緩",
                                color="info",
                                size="sm",
                                id={"type": "snooze-btn", "index": action_id}
                            ),
                        ]
                    ),
                    
                    html.Hr(),
                    
                    dbc.Textarea(
                        id={"type": "action-note", "index": action_id},
                        placeholder="Add note / 添加備註 (optional / 可選)...",
                        size="sm",
                        className="mt-2",
                        rows=2
                    )
                ]
            )
        ],
        className="mb-3",
        outline=True
    )


def render_signal_details(details: Dict[str, Any]) -> html.Div:
    """Render signal details in a compact format"""
    items = []
    
    if "price" in details:
        items.append(html.Li(f"Price: {details['price']}"))
    if "volume_ratio" in details:
        items.append(html.Li(f"Volume Ratio: {details['volume_ratio']}x"))
    if "ma5" in details and "ma20" in details:
        items.append(html.Li(f"MA5/MA20: {details['ma5']:.2f} / {details['ma20']:.2f}"))
    if "ma240" in details:
        items.append(html.Li(f"MA240: {details['ma240']:.2f}"))
    
    if items:
        return html.Ul(items, className="small text-muted mb-0")
    return html.Div()


def render_history_item(action: Dict[str, Any]) -> dbc.ListGroupItem:
    """Render a history item"""
    decision = action.get("decision", "unknown")
    decision_colors = {
        "approve": "success",
        "reject": "danger",
        "snooze": "info"
    }
    decision_labels = {
        "approve": "APPROVED",
        "reject": "REJECTED",
        "snooze": "SNOOZED"
    }
    
    symbol = action.get("symbol", "UNKNOWN")
    action_type = action.get("type", "SIGNAL")
    created_at = action.get("created_at", "")
    decided_at = action.get("decided_at", "")
    note = action.get("decision_note", "")
    
    # Format times
    for time_field in [created_at, decided_at]:
        if "T" in time_field:
            try:
                dt = datetime.fromisoformat(time_field.replace('Z', '+00:00'))
                if time_field == created_at:
                    created_at = dt.strftime("%m-%d %H:%M")
                else:
                    decided_at = dt.strftime("%m-%d %H:%M")
            except:
                pass
    
    return dbc.ListGroupItem(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(symbol),
                            html.Small(f" ({action_type})", className="text-muted ms-1")
                        ]
                    ),
                    dbc.Badge(
                        decision_labels.get(decision, decision.upper()),
                        color=decision_colors.get(decision, "secondary")
                    )
                ],
                className="d-flex justify-content-between align-items-center mb-1"
            ),
            html.Small(
                f"Created: {created_at} → Decided: {decided_at}",
                className="text-muted d-block"
            ),
            html.Small(
                note,
                className="text-muted d-block fst-italic"
            ) if note else None
        ]
    )


# Callbacks / 回調

@callback(
    Output("actions-store", "data"),
    Output("actions-pending-list", "children"),
    Output("actions-history-list", "children"),
    Output("actions-pending-count", "children"),
    Output("actions-stats-pending", "children"),
    Output("actions-stats-approved", "children"),
    Output("actions-stats-rejected", "children"),
    Output("actions-stats-snoozed", "children"),
    Output("actions-status-alert", "children"),
    Input("actions-interval", "n_intervals"),
    Input("actions-refresh-btn", "n_clicks"),
    prevent_initial_call=False
)
def update_actions_data(n_intervals, n_clicks):
    """Update actions data from service"""
    try:
        # Load data using service functions
        pending = load_pending_actions()
        history = load_history(limit=10)
        stats = get_today_stats()
        
        # Render pending list
        if pending:
            pending_children = [render_pending_action_card(a) for a in pending]
        else:
            pending_children = [
                html.Div(
                    [
                        html.P("📭 No pending actions / 無待處理行動", className="text-muted text-center py-4"),
                        html.P("New signals will appear here for your decision / 新訊號將在此顯示供您決策", className="text-muted text-center small")
                    ]
                )
            ]
        
        # Render history list
        if history:
            history_children = dbc.ListGroup(
                [render_history_item(a) for a in history],
                flush=True
            )
        else:
            history_children = [
                html.Div(
                    [
                        html.P("📜 No action history / 無行動歷史", className="text-muted text-center py-4"),
                        html.P("Approved, rejected, and snoozed actions will appear here", className="text-muted text-center small")
                    ]
                )
            ]
        
        data = {
            "pending": pending,
            "history": history,
            "stats": stats
        }
        
        return (
            data,
            pending_children,
            history_children,
            str(stats["pending"]),
            str(stats["pending"]),
            str(stats["approved"]),
            str(stats["rejected"]),
            str(stats["snoozed"]),
            None
        )
        
    except Exception as e:
        error_alert = dbc.Alert(f"Error loading actions: {e}", color="danger", dismissable=True)
        return ({"pending": [], "history": [], "stats": {}}, [], [], "--", "--", "--", "--", "--", error_alert)


@callback(
    Output("actions-status-alert", "children", allow_duplicate=True),
    Output("actions-store", "data", allow_duplicate=True),
    Input({"type": "approve-btn", "index": ALL}, "n_clicks"),
    Input({"type": "reject-btn", "index": ALL}, "n_clicks"),
    Input({"type": "snooze-btn", "index": ALL}, "n_clicks"),
    State({"type": "action-note", "index": ALL}, "value"),
    State({"type": "action-note", "index": ALL}, "id"),
    prevent_initial_call=True
)
def handle_decision(approve_clicks, reject_clicks, snooze_clicks, notes, note_ids):
    """Handle approve/reject/snooze button clicks"""
    from dash import callback_context
    
    ctx = callback_context
    if not ctx.triggered:
        return None, dash.no_update
    
    # Get triggered button info
    triggered = ctx.triggered[0]
    button_id = triggered["prop_id"].split(".")[0]
    
    try:
        button_data = json.loads(button_id)
        action_id = button_data["index"]
        decision = button_data["type"].replace("-btn", "")
        
        # Find note for this action
        note = ""
        for i, nid in enumerate(note_ids):
            if nid["index"] == action_id and notes[i]:
                note = notes[i]
                break
        
        # Process decision using service function
        success = process_decision(action_id, decision, note)
        
        if success:
            decision_labels = {
                "approve": "approved",
                "reject": "rejected",
                "snooze": "snoozed"
            }
            message = f"✅ Action {action_id} has been {decision_labels.get(decision, decision)}"
            
            # Refresh data
            pending = load_pending_actions()
            history = load_history(limit=10)
            stats = get_today_stats()
            data = {"pending": pending, "history": history, "stats": stats}
            
            return dbc.Alert(message, color="success", dismissable=True, className="mt-3"), data
        else:
            return dbc.Alert(f"❌ Failed to process action {action_id}", color="danger", dismissable=True), dash.no_update
            
    except Exception as e:
        return dbc.Alert(f"❌ Error: {e}", color="danger", dismissable=True), dash.no_update


@callback(
    Output("clear-history-modal", "is_open"),
    Output("actions-status-alert", "children", allow_duplicate=True),
    Output("actions-store", "data", allow_duplicate=True),
    Input("actions-clear-history-btn", "n_clicks"),
    Input("clear-cancel", "n_clicks"),
    Input("clear-confirm", "n_clicks"),
    State("clear-history-modal", "is_open"),
    prevent_initial_call=True
)
def handle_clear_history(clear_btn, cancel_btn, confirm_btn, is_open):
    """Handle clear history modal and action"""
    from dash import callback_context
    
    ctx = callback_context
    if not ctx.triggered:
        return is_open, None, dash.no_update
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "actions-clear-history-btn":
        return True, None, dash.no_update
    
    elif button_id == "clear-cancel":
        return False, None, dash.no_update
    
    elif button_id == "clear-confirm":
        try:
            # Clear history using service function
            success = clear_history()
            
            if success:
                # Refresh data
                pending = load_pending_actions()
                history = load_history(limit=10)
                stats = get_today_stats()
                data = {"pending": pending, "history": history, "stats": stats}
                
                return False, dbc.Alert("✅ History cleared successfully", color="info", dismissable=True), data
            else:
                return False, dbc.Alert("❌ Failed to clear history", color="danger", dismissable=True), dash.no_update
            
        except Exception as e:
            return False, dbc.Alert(f"❌ Error clearing history: {e}", color="danger", dismissable=True), dash.no_update
    
    return is_open, None, dash.no_update
