"""
UI Application - Main Entry Point
UI 應用程式 - 主入口點

BTC/ETH Monitoring System - UI Layer
BTC/ETH 監測系統 - UI 層

This module provides the main Dash application entry point.
本模組提供主要的 Dash 應用程式入口點。

Version: 1.0.0
Date: 2026-04-07
"""

import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output
import sys
import os
from pathlib import Path

# Dynamic path setup / 動態路徑設定
ui_dir = Path(__file__).resolve().parent
project_root = ui_dir.parent
sys.path.insert(0, str(project_root))

# Import configuration and services / 匯入配置與服務
from config.loader import get_monitoring_params
from config.paths import PROJECT_ROOT
from ui.services.monitor_service import get_scheduler_status

# Initialize the Dash app with multi-page support
# 使用多頁支援初始化 Dash 應用程式
app = dash.Dash(
    __name__,
    use_pages=True,  # Enable multi-page support / 啟用多頁支援
                     # Auto-discovers pages from ui/pages/ including strategy_detail.py
                     # 自動發現 ui/pages/ 下的頁面，包含 strategy_detail.py (/strategy/<strategy_name>)
    external_stylesheets=[dbc.themes.DARKLY],  # T-074: Dark theme
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ]
)

app.title = "BTC/ETH Monitoring System"

# Navigation bar / 導航列
navbar = dbc.Navbar(
    dbc.Container(
        [
            # Logo / Brand
            dbc.NavbarBrand(
                html.Span([
                    "📊 ",
                    html.Strong("BTC/ETH Monitor"),
                    html.Small(" UI", className="text-muted")
                ]),
                href="/",
                className="ms-2"
            ),
            
            # Navigation items / 導航項目
            dbc.Nav(
                [
                    dbc.NavItem(dbc.NavLink("Dashboard", href="/")),
                    dbc.NavItem(dbc.NavLink("Beginner", href="/beginner")),
                    dbc.NavItem(dbc.NavLink("Signals", href="/signals")),
                    dbc.NavItem(dbc.NavLink("Backtest", href="/backtest")),
                    dbc.NavItem(dbc.NavLink("Parameters", href="/parameters")),
                    dbc.NavItem(dbc.NavLink("Strategies", href="/strategies")),
                    dbc.NavItem(dbc.NavLink("Actions", href="/actions")),
                    dbc.NavItem(dbc.NavLink("System", href="/system")),
                ],
                className="ms-auto",
                navbar=True
            ),
            
            # Status indicator / 狀態指示器
            html.Div(
                id="navbar-status",
                children=[
                    dbc.Badge("🟢 Running", color="success", className="me-2")
                ]
            )
        ]
    ),
    color="dark",
    dark=True,
    className="mb-4"
)

# Main layout / 主佈局
app.layout = dbc.Container(
    [
        # Navigation / 導航
        navbar,
        
        # Page content / 頁面內容
        dash.page_container,
        
        # Footer / 頁尾
        html.Hr(),
        html.Footer(
            dbc.Container(
                html.P(
                    [
                        "⚠️ Alert-Only System • ",
                        html.A(
                            "Documentation",
                            href="https://github.com/RwdyLu/kimi-shared-brain",
                            target="_blank"
                        ),
                        " • v1.0.0"
                    ],
                    className="text-muted text-center"
                )
            )
        ),
        
        # Auto-refresh interval (for global updates) / 自動刷新間隔
        dcc.Interval(
            id="global-interval",
            interval=30*1000,  # 30 seconds / 30 秒
            n_intervals=0
        ),
        
        # Store for shared state / 共享狀態儲存
        dcc.Store(id="global-store", data={}),
        
        # Toast container for notifications / 通知容器
        html.Div(id="toast-container")
    ],
    fluid=True,
    className="dbc"
)


# Callback to update navbar status / 更新導航列狀態的回調
@app.callback(
    Output("navbar-status", "children"),
    Input("global-interval", "n_intervals")
)
def update_navbar_status(n):
    """Update system status badge in navbar using monitor service"""
    try:
        # Use the same source as Dashboard/System pages
        status = get_scheduler_status()
        
        if status.get("running"):
            return dbc.Badge("🟢 Running", color="success", className="me-2")
        else:
            return dbc.Badge("🔴 Stopped", color="danger", className="me-2")
    except Exception:
        return dbc.Badge("⚪ Unknown", color="secondary", className="me-2")


if __name__ == "__main__":
    print("=" * 70)
    print("BTC/ETH Monitoring System - UI")
    print("=" * 70)
    print("\nStarting Dash server...")
    print("Access the UI at: http://localhost:8050")
    print("\nPress Ctrl+C to stop\n")
    
    app.run(
        host="0.0.0.0",
        port=8050,
        debug=True,
        use_reloader=False
    )
