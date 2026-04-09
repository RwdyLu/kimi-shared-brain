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
from pathlib import Path

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Import monitor service and paths / 匯入監測服務與路徑
from ui.services.monitor_service import (
    get_scheduler_status,
    get_last_run_info,
    get_next_run_time,
    get_logs_preview
)
from config.paths import PROJECT_ROOT, CONFIG_DIR, LOGS_DIR, OUTPUTS_DIR, STATE_DIR

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
                    children=[]  # Will be populated by callback
                )
            ],
            className="mb-4"
        ),
        
        # Scheduler Status / 排程器狀態
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Scheduler Status / 排程器狀態", className="mb-0")),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6("Status / 狀態"),
                                        html.P(id="system-scheduler-status", children="Checking...")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("PID"),
                                        html.P(id="system-scheduler-pid", children="--")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Last Run / 最後執行"),
                                        html.P(id="system-last-run", children="--")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Next Run / 下次執行"),
                                        html.P(id="system-next-run", children="--")
                                    ],
                                    width=6,
                                    md=3
                                ),
                            ]
                        )
                    ]
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
                                    "Monitoring Params",
                                    href="/parameters",
                                    color="link",
                                    size="sm"
                                ),
                            ]
                        ),
                        html.P(
                            "⚠️ Scheduler controls are for display only in MVP. Use command line to control scheduler.",
                            className="text-muted small mt-3 mb-0"
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
                            children="Loading logs...",
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
                            "Refresh Logs / 刷新日誌",
                            id="system-refresh-logs",
                            color="outline-primary",
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
                                            html.Td(html.Code(str(PROJECT_ROOT)))
                                        ]),
                                        html.Tr([
                                            html.Td("Config Files / 配置文件"),
                                            html.Td(html.Code(str(CONFIG_DIR) + "/"))
                                        ]),
                                        html.Tr([
                                            html.Td("Logs / 日誌"),
                                            html.Td(html.Code(str(LOGS_DIR / "scheduler.log")))
                                        ]),
                                        html.Tr([
                                            html.Td("PID File / PID 檔案"),
                                            html.Td(html.Code(str(PROJECT_ROOT / ".monitor.pid")))
                                        ]),
                                        html.Tr([
                                            html.Td("Outputs / 輸出"),
                                            html.Td(html.Code(str(OUTPUTS_DIR) + "/"))
                                        ]),
                                        html.Tr([
                                            html.Td("State / 狀態"),
                                            html.Td(html.Code(str(STATE_DIR) + "/"))
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


# Callbacks / 回調

@callback(
    Output("system-health", "children"),
    Output("system-scheduler-status", "children"),
    Output("system-scheduler-pid", "children"),
    Output("system-last-run", "children"),
    Output("system-next-run", "children"),
    Output("system-logs", "children"),
    Input("system-interval", "n_intervals"),
    Input("system-refresh-logs", "n_clicks")
)
def update_system_info(n_intervals, n_clicks):
    """Update system information using monitor service"""
    try:
        # Get scheduler status
        status = get_scheduler_status()
        
        # Health indicators
        health_children = []
        
        # Scheduler health
        if status.get("running"):
            scheduler_badge = dbc.Badge("🟢 Running", color="success", className="mb-2 d-block")
            scheduler_status_text = dbc.Badge("✓ Operational", color="success")
        else:
            scheduler_badge = dbc.Badge("🔴 Stopped", color="danger", className="mb-2 d-block")
            scheduler_status_text = dbc.Badge("✗ Not Running", color="danger")
        
        health_children.append(
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H6("Scheduler / 排程器"),
                            scheduler_badge,
                            html.Small(
                                f"PID: {status.get('pid')}" if status.get('pid') else "No PID",
                                className="text-muted"
                            ) if status.get("running") else None
                        ],
                        width=6,
                        md=3,
                        className="mb-3"
                    ),
                    dbc.Col(
                        [
                            html.H6("Data API / 資料 API"),
                            dbc.Badge("🟢 Connected", color="success", className="mb-2 d-block"),
                            html.Small("Binance API", className="text-muted")
                        ],
                        width=6,
                        md=3,
                        className="mb-3"
                    ),
                    dbc.Col(
                        [
                            html.H6("Notifications / 通知"),
                            dbc.Badge("🟢 Active", color="success", className="mb-2 d-block"),
                            html.Small("Console + Discord", className="text-muted")
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
        )
        
        # Get last run info
        last_run = get_last_run_info()
        last_run_text = last_run.get("time_ago", "--") if last_run.get("timestamp") else "No runs"
        
        # Get next run time
        next_run = get_next_run_time()
        next_run_text = next_run if next_run else "--"
        
        # Get logs
        logs = get_logs_preview(30)
        logs_display = html.Pre(logs, style={"margin": 0, "whiteSpace": "pre-wrap"})
        
        return (
            health_children,
            scheduler_status_text,
            status.get("pid", "--"),
            last_run_text,
            next_run_text,
            logs_display
        )
        
    except Exception as e:
        error_msg = dbc.Alert(f"Error: {e}", color="danger")
        return error_msg, "Error", "--", "--", "--", f"Error loading logs: {e}"
