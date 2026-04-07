"""
System Page / 系統頁面

System logs, health, and settings.
系統日誌、健康度與設定。
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
import sys
import os

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Register page / 註冊頁面
dash.register_page(__name__, path="/system", title="System")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("System", className="mb-4"),
        html.P("System logs, health, and settings / 系統日誌、健康度與設定", className="text-muted"),
        
        html.Hr(),
        
        # System Health / 系統健康度
        dbc.Card(
            [
                dbc.CardHeader(html.H5("System Health / 系統健康度", className="mb-0")),
                dbc.CardBody(
                    id="system-health",
                    children=render_system_health()
                )
            ],
            className="mb-4"
        ),
        
        # Scheduler Controls / 排程器控制
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Scheduler Controls / 排程器控制", className="mb-0")),
                dbc.CardBody(
                    [
                        html.P("Control the monitoring scheduler / 控制監測排程器"),
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "🔄 Restart / 重啟",
                                    color="warning",
                                    className="me-2",
                                    id="system-restart-btn"
                                ),
                                dbc.Button(
                                    "⏹ Stop / 停止",
                                    color="danger",
                                    className="me-2",
                                    id="system-stop-btn"
                                ),
                                dbc.Button(
                                    "▶ Start / 啟動",
                                    color="success",
                                    id="system-start-btn"
                                ),
                            ]
                        ),
                        html.Hr(),
                        html.P("View Configuration / 查看配置:", className="mb-2"),
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "Scheduler Config",
                                    href="#",
                                    color="link",
                                    size="sm"
                                ),
                                dbc.Button(
                                    "Monitoring Params",
                                    href="#",
                                    color="link",
                                    size="sm"
                                ),
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Recent Logs / 最近日誌
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Recent Logs / 最近日誌", className="mb-0"),
                        dbc.Badge("Live", color="success", className="ms-2")
                    ]
                ),
                dbc.CardBody(
                    [
                        html.Div(
                            id="system-logs",
                            children=render_logs_preview(),
                            style={
                                "maxHeight": "400px",
                                "overflowY": "auto",
                                "fontFamily": "monospace",
                                "fontSize": "0.85rem",
                                "backgroundColor": "#f8f9fa",
                                "padding": "1rem",
                                "borderRadius": "0.25rem"
                            }
                        ),
                        html.Hr(),
                        dbc.Button(
                            "View Full Logs / 查看完整日誌",
                            href="#",
                            color="link",
                            size="sm"
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # File Locations / 檔案位置
        dbc.Card(
            [
                dbc.CardHeader(html.H5("File Locations / 檔案位置", className="mb-0")),
                dbc.CardBody(
                    [
                        dbc.Table(
                            [
                                html.Thead(
                                    html.Tr([
                                        html.Th("Type / 類型"),
                                        html.Th("Location / 位置")
                                    ])
                                ),
                                html.Tbody(
                                    [
                                        html.Tr([
                                            html.Td("Project Root / 專案根目錄"),
                                            html.Td(html.Code("/tmp/kimi-shared-brain"))
                                        ]),
                                        html.Tr([
                                            html.Td("Config Files / 配置文件"),
                                            html.Td(html.Code("/tmp/kimi-shared-brain/config/"))
                                        ]),
                                        html.Tr([
                                            html.Td("Logs / 日誌"),
                                            html.Td(html.Code("/tmp/kimi-shared-brain/logs/"))
                                        ]),
                                        html.Tr([
                                            html.Td("Alerts / 提醒"),
                                            html.Td(html.Code("/tmp/kimi-shared-brain/alerts/"))
                                        ]),
                                        html.Tr([
                                            html.Td("Outputs / 輸出"),
                                            html.Td(html.Code("/tmp/kimi-shared-brain/outputs/"))
                                        ]),
                                        html.Tr([
                                            html.Td("State / 狀態"),
                                            html.Td(html.Code("/tmp/kimi-shared-brain/state/"))
                                        ]),
                                    ]
                                )
                            ],
                            bordered=True,
                            size="sm"
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Version Info / 版本資訊
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Version Information / 版本資訊", className="mb-0")),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6("UI Version"),
                                        html.P("1.0.0", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Monitoring System"),
                                        html.P("1.1.0", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Config Schema"),
                                        html.P("1.0.0", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Last Updated"),
                                        html.P("2026-04-07", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                            ]
                        ),
                        html.Hr(),
                        html.P(
                            [
                                "Repository: ",
                                html.A(
                                    "github.com/RwdyLu/kimi-shared-brain",
                                    href="https://github.com/RwdyLu/kimi-shared-brain",
                                    target="_blank"
                                )
                            ],
                            className="text-muted mb-0"
                        )
                    ]
                )
            ]
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="system-interval",
            interval=10*1000,  # 10 seconds
            n_intervals=0
        ),
    ],
    fluid=True
)


def render_system_health():
    """Render system health indicators"""
    try:
        # Check scheduler status
        pid_file = "/tmp/kimi-shared-brain/.monitor.pid"
        scheduler_status = "stopped"
        scheduler_pid = None
        
        if os.path.exists(pid_file):
            with open(pid_file, 'r') as f:
                pid = f.read().strip()
                try:
                    os.kill(int(pid), 0)
                    scheduler_status = "running"
                    scheduler_pid = pid
                except (OSError, ValueError):
                    scheduler_status = "stale"
        
        # Check data connection (placeholder)
        data_status = "connected"  # Would check actual API
        
        # Check Discord connection (placeholder)
        discord_status = "connected"  # Would check actual connection
        
        return dbc.Row(
            [
                dbc.Col(
                    [
                        html.H6("Scheduler / 排程器"),
                        dbc.Badge(
                            "🟢 Running" if scheduler_status == "running" else "🔴 Stopped",
                            color="success" if scheduler_status == "running" else "danger",
                            className="mb-2 d-block"
                        ),
                        html.Small(
                            f"PID: {scheduler_pid}" if scheduler_pid else "Not running",
                            className="text-muted"
                        ) if scheduler_status == "running" else None
                    ],
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    [
                        html.H6("Data API / 資料 API"),
                        dbc.Badge(
                            "🟢 Connected" if data_status == "connected" else "🔴 Disconnected",
                            color="success" if data_status == "connected" else "danger",
                            className="mb-2 d-block"
                        ),
                        html.Small("Binance API", className="text-muted")
                    ],
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    [
                        html.H6("Notifications / 通知"),
                        dbc.Badge(
                            "🟢 Connected" if discord_status == "connected" else "🔴 Disconnected",
                            color="success" if discord_status == "connected" else "danger",
                            className="mb-2 d-block"
                        ),
                        html.Small("Discord + Console", className="text-muted")
                    ],
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    [
                        html.H6("UI Status / UI 狀態"),
                        dbc.Badge("🟢 Active", color="success", className="mb-2 d-block"),
                        html.Small("Dash server running", className="text-muted")
                    ],
                    width=6,
                    md=3,
                    className="mb-3"
                ),
            ]
        )
    except Exception as e:
        return dbc.Alert(f"Error checking health / 檢查健康度錯誤: {e}", color="danger")


def render_logs_preview():
    """Render a preview of recent logs"""
    log_lines = []
    
    try:
        log_file = "/tmp/kimi-shared-brain/logs/scheduler.log"
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                # Get last 20 lines
                lines = f.readlines()
                log_lines = lines[-20:] if len(lines) > 20 else lines
        else:
            log_lines = ["No log file found / 未找到日誌檔案"]
    except Exception as e:
        log_lines = [f"Error reading logs / 讀取日誌錯誤: {e}"]
    
    if not log_lines:
        log_lines = ["No logs available / 無可用日誌"]
    
    return html.Pre(
        "".join(log_lines),
        style={"margin": 0}
    )


# Callbacks / 回調

@callback(
    Output("system-health", "children"),
    Output("system-logs", "children"),
    Input("system-interval", "n_intervals")
)
def update_system_info(n):
    """Update system health and logs"""
    return render_system_health(), render_logs_preview()
