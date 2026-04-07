"""
Dashboard Page / 儀表板頁面

Main overview page showing system status and quick stats.
顯示系統狀態和快速統計的主概覽頁面。
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
from datetime import datetime
import sys

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Register page / 註冊頁面
dash.register_page(__name__, path="/", title="Dashboard")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Dashboard", className="mb-4"),
        html.P("System overview and quick status / 系統概覽與快速狀態", className="text-muted"),
        
        html.Hr(),
        
        # Status cards / 狀態卡片
        dbc.Row(
            [
                # System Status Card / 系統狀態卡片
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("System Status / 系統狀態"),
                            dbc.CardBody(
                                [
                                    html.H3(id="dashboard-status", children="Loading..."),
                                    html.P(id="dashboard-status-detail", children="Checking scheduler...")
                                ]
                            )
                        ],
                        color="info",
                        outline=True
                    ),
                    width=12,
                    md=6,
                    lg=4,
                    className="mb-3"
                ),
                
                # Last Run Card / 最後執行卡片
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Last Run / 最後執行"),
                            dbc.CardBody(
                                [
                                    html.H3(id="dashboard-last-run", children="--"),
                                    html.P(id="dashboard-last-run-result", children="Waiting for data...")
                                ]
                            )
                        ],
                        color="secondary",
                        outline=True
                    ),
                    width=12,
                    md=6,
                    lg=4,
                    className="mb-3"
                ),
                
                # Signals Today Card / 今日訊號卡片
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Today's Signals / 今日訊號"),
                            dbc.CardBody(
                                [
                                    html.H3(id="dashboard-signals-count", children="--"),
                                    html.P(id="dashboard-signals-breakdown", children="Loading...")
                                ]
                            )
                        ],
                        color="warning",
                        outline=True
                    ),
                    width=12,
                    md=6,
                    lg=4,
                    className="mb-3"
                ),
            ]
        ),
        
        # Active Symbols / 活躍標的
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Active Symbols / 活躍標的", className="mt-4 mb-3"),
                        dbc.Card(
                            dbc.CardBody(
                                id="dashboard-symbols",
                                children=[
                                    html.P("Loading symbols...", className="text-muted")
                                ]
                            )
                        )
                    ],
                    width=12,
                    className="mb-4"
                )
            ]
        ),
        
        # Recent Signals / 最近訊號
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Recent Signals / 最近訊號", className="mt-4 mb-3"),
                        dbc.Card(
                            dbc.CardBody(
                                id="dashboard-recent-signals",
                                children=[
                                    html.P("Loading recent signals...", className="text-muted")
                                ]
                            )
                        )
                    ],
                    width=12,
                    className="mb-4"
                )
            ]
        ),
        
        # Quick Actions / 快速操作
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Quick Actions / 快速操作", className="mt-4 mb-3"),
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "View Signals",
                                    href="/signals",
                                    color="primary",
                                    className="me-2"
                                ),
                                dbc.Button(
                                    "Check Parameters",
                                    href="/parameters",
                                    color="secondary",
                                    className="me-2"
                                ),
                                dbc.Button(
                                    "View Logs",
                                    href="/system",
                                    color="info"
                                ),
                            ]
                        )
                    ],
                    width=12,
                    className="mb-4"
                )
            ]
        ),
        
        # Auto-refresh interval / 自動刷新間隔
        dcc.Interval(
            id="dashboard-interval",
            interval=10*1000,  # 10 seconds / 10 秒
            n_intervals=0
        ),
        
        # Store for data / 資料儲存
        dcc.Store(id="dashboard-store")
    ],
    fluid=True
)


# Callbacks for dynamic content / 動態內容回調

@callback(
    Output("dashboard-status", "children"),
    Output("dashboard-status-detail", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_status(n):
    """Update system status display"""
    try:
        import os
        pid_file = "/tmp/kimi-shared-brain/.monitor.pid"
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = f.read().strip()
                try:
                    os.kill(int(pid), 0)
                    return "🟢 Running", f"PID: {pid}"
                except (OSError, ValueError):
                    return "🔴 Stopped", "Scheduler not running"
        return "🔴 Stopped", "No PID file found"
    except Exception as e:
        return "⚪ Unknown", str(e)


@callback(
    Output("dashboard-symbols", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_symbols(n):
    """Update active symbols display"""
    try:
        from config.loader import get_enabled_symbols
        symbols = get_enabled_symbols()
        
        if not symbols:
            return html.P("No active symbols configured", className="text-muted")
        
        return dbc.ListGroup(
            [
                dbc.ListGroupItem(
                    [
                        html.Strong(symbol),
                        dbc.Badge("Active", color="success", className="ms-2")
                    ],
                    className="d-flex justify-content-between align-items-center"
                )
                for symbol in symbols
            ]
        )
    except Exception as e:
        return html.P(f"Error loading symbols: {e}", className="text-danger")


@callback(
    Output("dashboard-recent-signals", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_recent_signals(n):
    """Update recent signals display"""
    # Placeholder - will be implemented in Phase 4
    return html.Div(
        [
            html.P("📡 Signal history will be displayed here", className="text-muted"),
            html.P("(Implemented in Phase 4: Connect Monitoring Status)", className="text-muted small")
        ]
    )


@callback(
    Output("dashboard-signals-count", "children"),
    Output("dashboard-signals-breakdown", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_signals_count(n):
    """Update signal counts"""
    # Placeholder - will be implemented in Phase 4
    return "--", "(Data connection pending)"


@callback(
    Output("dashboard-last-run", "children"),
    Output("dashboard-last-run-result", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_last_run(n):
    """Update last run time"""
    # Placeholder - will be implemented in Phase 4
    return "--", "(Data connection pending)"
