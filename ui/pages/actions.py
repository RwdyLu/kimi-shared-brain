"""
Actions Page / 行動頁面

Manual decision queue for signal-based actions.
訊號導向行動的人工決策佇列。
"""

import dash
from dash import dcc, html, callback, Output, Input, State
import dash_bootstrap_components as dbc
import sys
from datetime import datetime

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Register page / 註冊頁面
dash.register_page(__name__, path="/actions", title="Actions")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Actions", className="mb-4"),
        html.P("Manual decision queue for signals / 訊號的人工決策佇列", className="text-muted"),
        
        html.Hr(),
        
        # Pending Actions / 待處理行動
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Pending Actions / 待處理行動", className="mb-0"),
                        dbc.Badge("0 pending", color="secondary", className="ms-2", id="actions-pending-count")
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
                        html.H5("Action History / 行動歷史", className="mb-0"),
                        dbc.Button(
                            "View All / 查看全部",
                            size="sm",
                            color="link",
                            id="actions-view-all"
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
                                            html.Strong("Approve / 核准"),
                                            " - Log your approval (no auto-trading) / 記錄您的核准（無自動交易）"
                                        ]),
                                        html.Li([
                                            html.Strong("Reject / 拒絕"),
                                            " - Decline the signal / 拒絕該訊號"
                                        ]),
                                        html.Li([
                                            html.Strong("Snooze / 暫緩"),
                                            " - Postpone decision for later / 延後決策"
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
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="actions-interval",
            interval=30*1000,  # 30 seconds
            n_intervals=0
        ),
        
        # Store for action data / 行動資料儲存
        dcc.Store(id="actions-store", data={"pending": [], "history": []})
    ],
    fluid=True
)


def render_pending_action_card(action):
    """Render a pending action card with approve/reject/snooze buttons"""
    action_type = action.get("type", "SIGNAL")
    symbol = action.get("symbol", "UNKNOWN")
    suggestion = action.get("suggestion", "Review signal")
    
    type_colors = {
        "SIGNAL_CONFIRMED": "primary",
        "WATCH_TRIGGERED": "info",
        "MANUAL_REVIEW": "warning"
    }
    
    return dbc.Card(
        [
            dbc.CardHeader(
                [
                    dbc.Badge(action_type, color=type_colors.get(action_type, "secondary")),
                    html.Small(
                        action.get("created_at", ""),
                        className="text-muted ms-2"
                    )
                ]
            ),
            dbc.CardBody(
                [
                    html.H5(f"{symbol}", className="card-title"),
                    html.P(suggestion, className="card-text"),
                    
                    html.Hr(),
                    
                    dbc.ButtonGroup(
                        [
                            dbc.Button(
                                "✓ Approve / 核准",
                                color="success",
                                size="sm",
                                className="me-2",
                                id={"type": "approve", "index": action.get("id")}
                            ),
                            dbc.Button(
                                "✗ Reject / 拒絕",
                                color="danger",
                                size="sm",
                                className="me-2",
                                id={"type": "reject", "index": action.get("id")}
                            ),
                            dbc.Button(
                                "⏸ Snooze / 暫緩",
                                color="info",
                                size="sm",
                                id={"type": "snooze", "index": action.get("id")}
                            ),
                        ]
                    ),
                    
                    html.Hr(),
                    
                    dbc.Textarea(
                        placeholder="Add note / 添加備註 (optional / 可選)",
                        size="sm",
                        className="mt-2"
                    )
                ]
            )
        ],
        className="mb-3"
    )


def render_history_item(action):
    """Render a history item"""
    decision = action.get("decision", "unknown")
    decision_colors = {
        "approve": "success",
        "reject": "danger",
        "snooze": "info"
    }
    
    return dbc.ListGroupItem(
        [
            html.Div(
                [
                    html.Strong(action.get("symbol", "UNKNOWN")),
                    dbc.Badge(
                        decision.upper(),
                        color=decision_colors.get(decision, "secondary"),
                        className="ms-2"
                    )
                ],
                className="d-flex justify-content-between"
            ),
            html.Small(
                f"{action.get('created_at', '')} → {action.get('decided_at', '')}",
                className="text-muted d-block"
            ),
            html.Small(
                action.get("decision_note", ""),
                className="text-muted d-block"
            ) if action.get("decision_note") else None
        ]
    )


# Callbacks would go here for interactivity
# 互動回調會放在這裡
