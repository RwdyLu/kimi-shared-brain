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
from pathlib import Path

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Import monitor service / 匯入監測服務
from ui.services.monitor_service import (
    get_scheduler_status,
    get_last_run_info,
    get_today_signals,
    get_recent_runs,
    get_current_prices  # T-051: Add current prices / 新增當前價格
)
from config.loader import get_enabled_symbols

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
                        id="dashboard-status-card",
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
                            dbc.CardHeader([
                                "Last Run (Live) / 最後執行 (即時)",
                                html.Small(" 📍Current Session", className="text-muted ms-2")
                            ]),
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
                        id="dashboard-signals-card",
                        color="warning",
                        outline=True
                    ),
                    width=12,
                    md=6,
                    lg=4,
                    className="mb-3"
                ),
                
                # Current Prices Card / 當前價格卡片 (T-051)
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader([
                                "Live Prices / 即時價格",
                                html.Small(" 💰From Last Run", className="text-muted ms-2")
                            ]),
                            dbc.CardBody(
                                [
                                    html.Div(id="dashboard-prices", children=[
                                        html.P("Loading prices...", className="text-muted")
                                    ])
                                ]
                            )
                        ],
                        id="dashboard-prices-card",
                        color="success",
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
        
        # Recent Runs / 近期執行記錄
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4([
                            "Recent Run History / 近期執行記錄",
                            html.Small(" 📜From Log", className="text-muted ms-2")
                        ], className="mt-4 mb-3"),
                        html.P("Historical runs from scheduler log / 來自排程器日誌的歷史記錄", 
                               className="text-muted small mb-2"),
                        dbc.Card(
                            dbc.CardBody(
                                id="dashboard-recent-runs",
                                children=[
                                    html.P("Loading recent runs...", className="text-muted")
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
    Output("dashboard-status-card", "color"),
    Input("dashboard-interval", "n_intervals")
)
def update_status(n):
    """Update system status display using monitor service"""
    try:
        status = get_scheduler_status()
        
        if status.get("running"):
            return (
                "🟢 Running",
                f"PID: {status.get('pid')}",
                "success"
            )
        else:
            return (
                "🔴 Stopped",
                status.get("status_text", "Scheduler not running"),
                "danger"
            )
    except Exception as e:
        return "⚪ Unknown", str(e), "secondary"


@callback(
    Output("dashboard-last-run", "children"),
    Output("dashboard-last-run-result", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_last_run(n):
    """Update last run time using monitor service"""
    try:
        last_run = get_last_run_info()
        
        if last_run.get("timestamp"):
            time_display = last_run.get("time_ago", last_run["timestamp"])
            result_text = last_run.get("result_text", "No details")
            
            # Add run number if available
            if last_run.get("run_id"):
                time_display = f"#{last_run['run_id']} • {time_display}"
            
            return time_display, result_text
        else:
            return "No runs yet", "Waiting for first run"
    except Exception as e:
        return "Error", str(e)


@callback(
    Output("dashboard-symbols", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_symbols(n):
    """Update active symbols display"""
    try:
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
    Output("dashboard-signals-count", "children"),
    Output("dashboard-signals-breakdown", "children"),
    Output("dashboard-signals-card", "color"),
    Input("dashboard-interval", "n_intervals")
)
def update_signals_count(n):
    """Update signal counts using monitor service"""
    try:
        signals = get_today_signals()
        
        total = signals.get("total", 0)
        confirmed = signals.get("confirmed", 0)
        watch_only = signals.get("watch_only", 0)
        
        if total > 0:
            breakdown = f"✅ {confirmed} confirmed • 👁️ {watch_only} watch"
            color = "warning" if confirmed > 0 else "info"
        else:
            breakdown = "No signals today / 今日無訊號"
            color = "success"
        
        return str(total), breakdown, color
    except Exception as e:
        return "--", str(e), "secondary"


@callback(
    Output("dashboard-prices", "children"),
    Output("dashboard-prices-card", "color"),
    Input("dashboard-interval", "n_intervals")
)
def update_prices(n):
    """Update current prices display / 更新當前價格顯示"""
    try:
        prices_data = get_current_prices()
        
        if not prices_data or not prices_data.get("prices"):
            return html.P("No price data available / 無價格資料", className="text-muted"), "secondary"
        
        prices = prices_data.get("prices", {})
        
        # Build price display / 建立價格顯示
        price_items = []
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            if symbol in prices:
                price = prices[symbol].get("price", 0)
                # Format based on symbol
                if symbol == "BTCUSDT":
                    price_text = f"${price:,.2f}"
                else:  # ETHUSDT
                    price_text = f"${price:,.2f}"
                
                price_items.append(
                    html.Div([
                        html.Strong(symbol.replace("USDT", "") + ": ", className="me-2"),
                        html.Span(price_text, className="text-success fs-5")
                    ], className="mb-2")
                )
        
        # Add timestamp / 添加時間戳
        timestamp = prices_data.get("timestamp", "")
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
                price_items.append(
                    html.Small(f"Updated: {time_str}", className="text-muted d-block mt-2")
                )
            except:
                pass
        
        return html.Div(price_items), "success"
    except Exception as e:
        return html.P(f"Error loading prices: {e}", className="text-danger"), "danger"


@callback(
    Output("dashboard-recent-runs", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_recent_runs(n):
    """Update recent runs display"""
    try:
        runs = get_recent_runs(5)
        
        if not runs:
            return html.P("No recent runs found", className="text-muted text-center py-3")
        
        rows = []
        for run in runs:
            run_id = run.get("run_id", "--")
            timestamp = run.get("timestamp", "--")
            time_ago = run.get("time_ago", "")
            signals = run.get("signals", 0)
            confirmed = run.get("confirmed", 0)
            watch = run.get("watch_only", 0)
            symbols_checked = run.get("symbols_checked", ["BTCUSDT", "ETHUSDT"])
            symbols_with_signals = run.get("symbols_with_signals", [])
            
            # Format time display: show time_ago if available, otherwise timestamp
            time_display = f"{timestamp} ({time_ago})" if time_ago else timestamp
            
            # Signal badge color
            if signals > 0:
                if confirmed > 0:
                    badge_color = "success"
                    badge_text = f"{signals} ({confirmed}✓)"
                else:
                    badge_color = "info"
                    badge_text = f"{signals} (👁️)"
            else:
                badge_color = "secondary"
                badge_text = "0"
            
            # Build symbols display with indicators
            symbol_badges = []
            for symbol in symbols_checked:
                if symbol in symbols_with_signals:
                    # Symbol has signal
                    symbol_badges.append(
                        dbc.Badge(symbol.replace("USDT", ""), color="warning", className="me-1", pill=True)
                    )
                else:
                    # Symbol checked but no signal
                    symbol_badges.append(
                        dbc.Badge(symbol.replace("USDT", ""), color="light", text_color="secondary", className="me-1", pill=True)
                    )
            
            rows.append(
                html.Tr([
                    html.Td(f"#{run_id}"),
                    html.Td(time_display),
                    html.Td(dbc.Badge(badge_text, color=badge_color)),
                    html.Td(symbol_badges),
                ])
            )
        
        return dbc.Table(
            [
                html.Thead(
                    html.Tr([
                        html.Th("Run"),
                        html.Th("Time / 時間"),
                        html.Th("Signals / 訊號"),
                        html.Th("Symbols / 標的"),
                    ])
                ),
                html.Tbody(rows)
            ],
            bordered=True,
            hover=True,
            size="sm"
        )
    except Exception as e:
        return html.P(f"Error loading runs: {e}", className="text-danger")


@callback(
    Output("dashboard-recent-signals", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_recent_signals(n):
    """Update recent signals display"""
    try:
        # Get today's signals info
        signals = get_today_signals()
        
        if signals.get("total", 0) == 0:
            return html.Div(
                [
                    html.P("📡 No signals today", className="text-muted text-center"),
                    html.P(
                        "Signals will appear here when detected",
                        className="text-muted text-center small"
                    )
                ],
                className="py-3"
            )
        
        # Show summary of today's signals
        return html.Div(
            [
                html.P(f"Today's signal count: {signals['total']}", className="mb-2"),
                html.Ul(
                    [
                        html.Li(f"Confirmed signals: {signals['confirmed']}"),
                        html.Li(f"Watch-only signals: {signals['watch_only']}"),
                    ]
                ),
                html.P(
                    "Go to Signals page for details / 前往訊號頁面查看詳情",
                    className="text-muted small"
                ),
                dbc.Button(
                    "View All Signals",
                    href="/signals",
                    color="primary",
                    size="sm"
                )
            ]
        )
    except Exception as e:
        return html.P(f"Error loading signals: {e}", className="text-danger")
