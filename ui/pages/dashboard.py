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
        
        # Live Prices Section (Moved to top) / 即時價格區塊 (移到頂部)
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Live Prices / 即時價格", className="mb-3"),
                        dbc.Row(
                            [
                                # BTC Price Card / BTC 價格卡片
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardBody(
                                                [
                                                    html.H5("Bitcoin", className="card-title text-muted"),
                                                    html.H2(
                                                        id="btc-price-display", 
                                                        children="--",
                                                        className="text-success fw-bold"
                                                    ),
                                                    html.Small(
                                                        id="btc-price-time",
                                                        children="Waiting for data...",
                                                        className="text-muted"
                                                    )
                                                ]
                                            )
                                        ],
                                        color="light",
                                        outline=True,
                                        className="h-100 border-success"
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                
                                # ETH Price Card / ETH 價格卡片
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardBody(
                                                [
                                                    html.H5("Ethereum", className="card-title text-muted"),
                                                    html.H2(
                                                        id="eth-price-display", 
                                                        children="--",
                                                        className="text-success fw-bold"
                                                    ),
                                                    html.Small(
                                                        id="eth-price-time",
                                                        children="Waiting for data...",
                                                        className="text-muted"
                                                    )
                                                ]
                                            )
                                        ],
                                        color="light",
                                        outline=True,
                                        className="h-100 border-success"
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                            ]
                        )
                    ],
                    width=12,
                    className="mb-4"
                )
            ]
        ),
        
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
        
        # Strategy Distance Panel / 策略距離面板 (T-052-C)
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Strategy Distance / 策略距離", className="mt-4 mb-3"),
                        html.P("Current price position relative to strategy triggers / 當前價格相對於策略觸發點的位置", 
                               className="text-muted small mb-2"),
                        dbc.Row(
                            [
                                # BTC Strategy Status Card (T-059-B)
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardHeader([
                                                html.Strong("BTC / 策略狀態"),
                                            ]),
                                            dbc.CardBody(
                                                [
                                                    # Price Header
                                                    html.Div([
                                                        html.Span(id="btc-strategy-price", children="--", className="h3 text-success"),
                                                        html.Span(id="btc-price-change", children="", className="ms-2 small"),
                                                    ], className="mb-3"),
                                                    html.Hr(),
                                                    
                                                    # Strategy Status List
                                                    html.H6("策略狀態", className="text-muted mb-2"),
                                                    
                                                    # MA Cross Long
                                                    html.Div([
                                                        html.Span(id="btc-long-status", children="🔴", className="me-2"),
                                                        html.Strong("MA Cross Long", className="me-2"),
                                                        html.Span(id="btc-long-distance", children="--", className="small"),
                                                        html.Div(id="btc-long-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                    
                                                    # MA Cross Short
                                                    html.Div([
                                                        html.Span(id="btc-short-status", children="🔴", className="me-2"),
                                                        html.Strong("MA Cross Short", className="me-2"),
                                                        html.Span(id="btc-short-distance", children="--", className="small"),
                                                        html.Div(id="btc-short-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                    
                                                    # Contrarian Oversold
                                                    html.Div([
                                                        html.Span(id="btc-oversold-status", children="🔴", className="me-2"),
                                                        html.Strong("Contrarian Oversold", className="me-2"),
                                                        html.Span(id="btc-oversold-distance", children="--", className="small"),
                                                        html.Div(id="btc-oversold-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                    
                                                    # Contrarian Overbought
                                                    html.Div([
                                                        html.Span(id="btc-overbought-status", children="🔴", className="me-2"),
                                                        html.Strong("Contrarian Overbought", className="me-2"),
                                                        html.Span(id="btc-overbought-distance", children="--", className="small"),
                                                        html.Div(id="btc-overbought-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                ]
                                            )
                                        ],
                                        className="h-100"
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                
                                # ETH Strategy Status Card (T-059-B)
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardHeader([
                                                html.Strong("ETH / 策略狀態"),
                                            ]),
                                            dbc.CardBody(
                                                [
                                                    # Price Header
                                                    html.Div([
                                                        html.Span(id="eth-strategy-price", children="--", className="h3 text-success"),
                                                        html.Span(id="eth-price-change", children="", className="ms-2 small"),
                                                    ], className="mb-3"),
                                                    html.Hr(),
                                                    
                                                    # Strategy Status List
                                                    html.H6("策略狀態", className="text-muted mb-2"),
                                                    
                                                    # MA Cross Long
                                                    html.Div([
                                                        html.Span(id="eth-long-status", children="🔴", className="me-2"),
                                                        html.Strong("MA Cross Long", className="me-2"),
                                                        html.Span(id="eth-long-distance", children="--", className="small"),
                                                        html.Div(id="eth-long-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                    
                                                    # MA Cross Short
                                                    html.Div([
                                                        html.Span(id="eth-short-status", children="🔴", className="me-2"),
                                                        html.Strong("MA Cross Short", className="me-2"),
                                                        html.Span(id="eth-short-distance", children="--", className="small"),
                                                        html.Div(id="eth-short-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                    
                                                    # Contrarian Oversold
                                                    html.Div([
                                                        html.Span(id="eth-oversold-status", children="🔴", className="me-2"),
                                                        html.Strong("Contrarian Oversold", className="me-2"),
                                                        html.Span(id="eth-oversold-distance", children="--", className="small"),
                                                        html.Div(id="eth-oversold-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                    
                                                    # Contrarian Overbought
                                                    html.Div([
                                                        html.Span(id="eth-overbought-status", children="🔴", className="me-2"),
                                                        html.Strong("Contrarian Overbought", className="me-2"),
                                                        html.Span(id="eth-overbought-distance", children="--", className="small"),
                                                        html.Div(id="eth-overbought-detail", children="--", className="small text-muted ms-4"),
                                                    ], className="mb-2"),
                                                ]
                                            )
                                        ],
                                        className="h-100"
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                            ]
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
            interval=10*1000,  # 10 seconds / 10 秒 (T-059-A)
            n_intervals=0
        ),
        
        # Store for data / 資料儲存
        dcc.Store(id="dashboard-store"),
        
        # T-053-C: Backtest Summary Section / 回測摘要區塊
        html.Hr(),
        html.H4("Backtest Results / 回測結果", className="mt-4 mb-3"),
        dbc.Row(
            [
                # Win Rate Card / 勝率卡片
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Win Rate / 勝率", className="card-title text-muted"),
                                    html.H2(
                                        id="backtest-win-rate",
                                        children="--",
                                        className="text-info fw-bold"
                                    ),
                                    html.Small(
                                        id="backtest-trade-count",
                                        children="No backtests yet",
                                        className="text-muted"
                                    )
                                ]
                            )
                        ],
                        color="light",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                
                # Total Return Card / 總報酬卡片
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Total Return / 總報酬", className="card-title text-muted"),
                                    html.H2(
                                        id="backtest-return",
                                        children="--",
                                        className="fw-bold"
                                    ),
                                    html.Small(
                                        id="backtest-period",
                                        children="--",
                                        className="text-muted"
                                    )
                                ]
                            )
                        ],
                        color="light",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                
                # Max Drawdown Card / 最大回撤卡片
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Max Drawdown / 最大回撤", className="card-title text-muted"),
                                    html.H2(
                                        id="backtest-drawdown",
                                        children="--",
                                        className="text-danger fw-bold"
                                    ),
                                    html.Small(
                                        "Risk metric / 風險指標",
                                        className="text-muted"
                                    )
                                ]
                            )
                        ],
                        color="light",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                
                # Latest Backtest ID / 最新回測 ID
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Latest Run / 最新執行", className="card-title text-muted"),
                                    html.H4(
                                        id="backtest-latest-id",
                                        children="--",
                                        className="text-primary"
                                    ),
                                    html.Small(
                                        id="backtest-symbols",
                                        children="--",
                                        className="text-muted"
                                    )
                                ]
                            )
                        ],
                        color="light",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
            ]
        ),
        
        # Backtest Action Button / 回測操作按鈕
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        "View Full Report / 查看完整報告",
                        href="/backtest",
                        color="primary",
                        className="mt-2"
                    ),
                    width=12
                )
            ]
        ),

        # T-055: Check History Table / 檢查歷史表格
        html.Hr(),
        html.H4([
            "📋 Check History / 檢查歷史 ",
            html.Small("Last 10 checks / 最近10次", className="text-muted")
        ], className="mt-4 mb-3"),
        dbc.Card(
            [
                dbc.CardHeader(
                    dbc.Row(
                        [
                            dbc.Col(html.Strong("Time / 時間"), width=3),
                            dbc.Col(html.Strong("BTC/USDT"), width=3),
                            dbc.Col(html.Strong("ETH/USDT"), width=3),
                            dbc.Col(html.Strong("Signals / 訊號"), width=3),
                        ],
                        className="text-center"
                    )
                ),
                dbc.CardBody(
                    id="check-history-table",
                    children=[
                        dbc.Row(
                            dbc.Col(
                                html.P("Loading check history... / 載入檢查歷史...", className="text-muted text-center py-3"),
                                width=12
                            )
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
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


# T-052-A: New BTC/ETH price callbacks / 新的 BTC/ETH 價格回調

def format_update_time(timestamp_str: str) -> str:
    """
    Format timestamp with relative time (T-058)
    格式化時間戳並顯示相對時間
    
    Args:
        timestamp_str: ISO format timestamp or HH:MM:SS
        
    Returns:
        Formatted string like "Updated 17:39:39 · 32s ago"
    """
    try:
        # Parse timestamp
        if 'T' in timestamp_str:
            t = datetime.fromisoformat(timestamp_str)
        else:
            today = datetime.now().strftime('%Y-%m-%d')
            t = datetime.fromisoformat(f"{today}T{timestamp_str}")
        
        # Calculate difference
        diff = int((datetime.now() - t).total_seconds())
        
        # Format relative time
        if diff < 60:
            ago = f"{diff}s ago"
        elif diff < 3600:
            ago = f"{diff//60}m ago"
        else:
            ago = f"{diff//3600}h ago"
        
        return f"Updated {t.strftime('%H:%M:%S')} · {ago}"
    except:
        return f"Updated {timestamp_str}"


@callback(
    Output("btc-price-display", "children"),
    Output("btc-price-time", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_btc_price(n):
    """Update BTC price display / 更新 BTC 價格顯示"""
    try:
        prices_data = get_current_prices()
        
        if not prices_data or not prices_data.get("prices"):
            return "--", "No data / 無資料"
        
        prices = prices_data.get("prices", {})
        
        if "BTCUSDT" in prices:
            price = prices["BTCUSDT"].get("price", 0)
            price_text = f"${price:,.2f}"
            
            # Format timestamp with relative time (T-058)
            timestamp = prices_data.get("timestamp", "")
            if timestamp:
                time_text = format_update_time(timestamp)
            else:
                time_text = "Updated recently"
            
            return price_text, time_text
        else:
            return "--", "No BTC data"
    except Exception as e:
        return "Error", str(e)


@callback(
    Output("eth-price-display", "children"),
    Output("eth-price-time", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_eth_price(n):
    """Update ETH price display / 更新 ETH 價格顯示"""
    try:
        prices_data = get_current_prices()
        
        if not prices_data or not prices_data.get("prices"):
            return "--", "No data / 無資料"
        
        prices = prices_data.get("prices", {})
        
        if "ETHUSDT" in prices:
            price = prices["ETHUSDT"].get("price", 0)
            price_text = f"${price:,.2f}"
            
            # Format timestamp with relative time (T-058)
            timestamp = prices_data.get("timestamp", "")
            if timestamp:
                time_text = format_update_time(timestamp)
            else:
                time_text = "Updated recently"
            
            return price_text, time_text
        else:
            return "--", "No ETH data"
    except Exception as e:
        return "Error", str(e)


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


# T-052-C: Strategy Distance callbacks / 策略距離回調
def _format_ma_distance(value: float) -> tuple:
    """Format MA distance with color indicator / 格式化 MA 距離並帶顏色指示"""
    if value is None:
        return "--", "secondary"
    
    sign = "+" if value >= 0 else ""
    color = "success" if value >= 0 else "danger"
    text = f"{sign}{value:.2f}%"
    
    return text, color


@callback(
    Output("btc-strategy-price", "children"),
    Output("btc-price-change", "children"),
    Output("btc-long-status", "children"),
    Output("btc-long-distance", "children"),
    Output("btc-long-detail", "children"),
    Output("btc-short-status", "children"),
    Output("btc-short-distance", "children"),
    Output("btc-short-detail", "children"),
    Output("btc-oversold-status", "children"),
    Output("btc-oversold-distance", "children"),
    Output("btc-oversold-detail", "children"),
    Output("btc-overbought-status", "children"),
    Output("btc-overbought-distance", "children"),
    Output("btc-overbought-detail", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_btc_strategy_status(n):
    """Update BTC strategy status display / 更新 BTC 策略狀態顯示 (T-059-B)"""
    try:
        from ui.services.monitor_service import get_latest_indicator_snapshots, get_last_run_info
        
        snapshots = get_latest_indicator_snapshots()
        last_run = get_last_run_info()
        
        if not snapshots or "BTCUSDT" not in snapshots:
            return (["--"] + ["--"] * 12)
        
        data = snapshots["BTCUSDT"]
        
        # Price
        price = data.get("price", 0)
        price_text = f"${price:,.2f}" if price else "--"
        
        # 24h change (placeholder - would need historical data)
        change_text = ""
        
        # MA values
        ma5 = data.get("ma5", 0)
        ma20 = data.get("ma20", 0)
        
        # Calculate MA distances
        long_distance = ((ma20 - price) / price * 100) if price and ma20 else None
        short_distance = ((price - ma20) / price * 100) if price and ma20 else None
        ma5_vs_ma20 = ((ma5 - ma20) / ma20 * 100) if ma5 and ma20 else None
        
        # Color coding: 🟢 triggered, 🟡 <0.5%, 🔴 >=0.5%
        def get_status_color(distance, triggered):
            if triggered:
                return "🟢"
            elif distance is None:
                return "⚪"
            elif abs(distance) < 0.5:
                return "🟡"
            else:
                return "🔴"
        
        # MA Cross Long
        long_triggered = data.get("ma_cross_long", False)
        long_color = get_status_color(long_distance, long_triggered)
        long_dist_text = f"{abs(long_distance):.2f}%" if long_distance else "--"
        long_detail = f"MA5 ${ma5:,.0f} 需上穿 MA20 ${ma20:,.0f}" if ma5 and ma20 else "--"
        
        # MA Cross Short
        short_triggered = data.get("ma_cross_short", False)
        short_color = get_status_color(short_distance, short_triggered)
        short_dist_text = f"{abs(short_distance):.2f}%" if short_distance else "--"
        short_detail = f"MA5 ${ma5:,.0f} 需下穿 MA20 ${ma20:,.0f}" if ma5 and ma20 else "--"
        
        # Contrarian strategies - get candle counts from last run
        run_data = last_run.get("data", {}) if last_run else {}
        symbol_data = run_data.get("BTCUSDT", {}) if isinstance(run_data, dict) else {}
        
        # Red candles (for oversold)
        red_candles = symbol_data.get("red_candles", 0) if isinstance(symbol_data, dict) else 0
        oversold_triggered = red_candles >= 4
        oversold_distance = max(0, 4 - red_candles)
        oversold_color = "🟢" if oversold_triggered else ("🟡" if oversold_distance <= 1 else "🔴")
        oversold_dist_text = f"差 {oversold_distance} 根" if not oversold_triggered else "已觸發"
        oversold_detail = f"連續 {red_candles}/4 根紅 K"
        
        # Green candles (for overbought)
        green_candles = symbol_data.get("green_candles", 0) if isinstance(symbol_data, dict) else 0
        overbought_triggered = green_candles >= 4
        overbought_distance = max(0, 4 - green_candles)
        overbought_color = "🟢" if overbought_triggered else ("🟡" if overbought_distance <= 1 else "🔴")
        overbought_dist_text = f"差 {overbought_distance} 根" if not overbought_triggered else "已觸發"
        overbought_detail = f"連續 {green_candles}/4 根綠 K"
        
        return (
            price_text, change_text,
            long_color, f"{long_dist_text}", long_detail,
            short_color, f"{short_dist_text}", short_detail,
            oversold_color, f"{oversold_dist_text}", oversold_detail,
            overbought_color, f"{overbought_dist_text}", overbought_detail
        )
        
    except Exception as e:
        return (["Error"] + ["--"] * 12)


@callback(
    Output("eth-strategy-price", "children"),
    Output("eth-price-change", "children"),
    Output("eth-long-status", "children"),
    Output("eth-long-distance", "children"),
    Output("eth-long-detail", "children"),
    Output("eth-short-status", "children"),
    Output("eth-short-distance", "children"),
    Output("eth-short-detail", "children"),
    Output("eth-oversold-status", "children"),
    Output("eth-oversold-distance", "children"),
    Output("eth-oversold-detail", "children"),
    Output("eth-overbought-status", "children"),
    Output("eth-overbought-distance", "children"),
    Output("eth-overbought-detail", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_eth_strategy_status(n):
    """Update ETH strategy status display / 更新 ETH 策略狀態顯示 (T-059-B)"""
    try:
        from ui.services.monitor_service import get_latest_indicator_snapshots, get_last_run_info
        
        snapshots = get_latest_indicator_snapshots()
        last_run = get_last_run_info()
        
        if not snapshots or "ETHUSDT" not in snapshots:
            return (["--"] + ["--"] * 12)
        
        data = snapshots["ETHUSDT"]
        
        # Price
        price = data.get("price", 0)
        price_text = f"${price:,.2f}" if price else "--"
        
        # 24h change (placeholder)
        change_text = ""
        
        # MA values
        ma5 = data.get("ma5", 0)
        ma20 = data.get("ma20", 0)
        
        # Calculate MA distances
        long_distance = ((ma20 - price) / price * 100) if price and ma20 else None
        short_distance = ((price - ma20) / price * 100) if price and ma20 else None
        ma5_vs_ma20 = ((ma5 - ma20) / ma20 * 100) if ma5 and ma20 else None
        
        # Color coding: 🟢 triggered, 🟡 <0.5%, 🔴 >=0.5%
        def get_status_color(distance, triggered):
            if triggered:
                return "🟢"
            elif distance is None:
                return "⚪"
            elif abs(distance) < 0.5:
                return "🟡"
            else:
                return "🔴"
        
        # MA Cross Long
        long_triggered = data.get("ma_cross_long", False)
        long_color = get_status_color(long_distance, long_triggered)
        long_dist_text = f"{abs(long_distance):.2f}%" if long_distance else "--"
        long_detail = f"MA5 ${ma5:,.0f} 需上穿 MA20 ${ma20:,.0f}" if ma5 and ma20 else "--"
        
        # MA Cross Short
        short_triggered = data.get("ma_cross_short", False)
        short_color = get_status_color(short_distance, short_triggered)
        short_dist_text = f"{abs(short_distance):.2f}%" if short_distance else "--"
        short_detail = f"MA5 ${ma5:,.0f} 需下穿 MA20 ${ma20:,.0f}" if ma5 and ma20 else "--"
        
        # Contrarian strategies - get candle counts from last run
        run_data = last_run.get("data", {}) if last_run else {}
        symbol_data = run_data.get("ETHUSDT", {}) if isinstance(run_data, dict) else {}
        
        # Red candles (for oversold)
        red_candles = symbol_data.get("red_candles", 0) if isinstance(symbol_data, dict) else 0
        oversold_triggered = red_candles >= 4
        oversold_distance = max(0, 4 - red_candles)
        oversold_color = "🟢" if oversold_triggered else ("🟡" if oversold_distance <= 1 else "🔴")
        oversold_dist_text = f"差 {oversold_distance} 根" if not oversold_triggered else "已觸發"
        oversold_detail = f"連續 {red_candles}/4 根紅 K"
        
        # Green candles (for overbought)
        green_candles = symbol_data.get("green_candles", 0) if isinstance(symbol_data, dict) else 0
        overbought_triggered = green_candles >= 4
        overbought_distance = max(0, 4 - green_candles)
        overbought_color = "🟢" if overbought_triggered else ("🟡" if overbought_distance <= 1 else "🔴")
        overbought_dist_text = f"差 {overbought_distance} 根" if not overbought_triggered else "已觸發"
        overbought_detail = f"連續 {green_candles}/4 根綠 K"
        
        return (
            price_text, change_text,
            long_color, f"{long_dist_text}", long_detail,
            short_color, f"{short_dist_text}", short_detail,
            oversold_color, f"{oversold_dist_text}", oversold_detail,
            overbought_color, f"{overbought_dist_text}", overbought_detail
        )
        
    except Exception as e:
        return (["Error"] + ["--"] * 12)


# T-053-C: Backtest results callback / 回測結果回調
@callback(
    Output("backtest-win-rate", "children"),
    Output("backtest-trade-count", "children"),
    Output("backtest-return", "children"),
    Output("backtest-return", "className"),
    Output("backtest-period", "children"),
    Output("backtest-drawdown", "children"),
    Output("backtest-latest-id", "children"),
    Output("backtest-symbols", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_backtest_summary(n):
    """Update backtest summary cards / 更新回測摘要卡片"""
    try:
        from backtest import BacktestStorage

        storage = BacktestStorage()
        backtests = storage.get_latest_backtests(limit=1)

        if not backtests:
            return (
                "--",
                "No backtests yet / 尚無回測",
                "--",
                "fw-bold",
                "--",
                "--",
                "--",
                "Run a backtest to see results"
            )

        bt = backtests[0]

        # Win rate
        win_rate = bt.get("win_rate", 0)
        win_rate_text = f"{win_rate:.1f}%"

        # Trade count
        total = bt.get("total_trades", 0)
        winning = bt.get("winning_trades", 0)
        trade_count = f"{total} trades ({winning} wins) / {total} 筆 ({winning} 勝)"

        # Return
        return_pct = bt.get("total_return_pct", 0)
        return_text = f"{return_pct:+.2f}%"
        return_class = "fw-bold text-success" if return_pct >= 0 else "fw-bold text-danger"

        # Period
        start = bt.get("start_date", "--")
        end = bt.get("end_date", "--")
        period = f"{start} ~ {end}"

        # Drawdown
        drawdown = bt.get("max_drawdown_pct", 0)
        drawdown_text = f"{drawdown:.2f}%"

        # Latest ID
        bt_id = bt.get("backtest_id", "--")

        # Symbols
        symbols = bt.get("symbols", [])
        symbols_text = ", ".join(symbols) if symbols else "--"

        return (
            win_rate_text,
            trade_count,
            return_text,
            return_class,
            period,
            drawdown_text,
            bt_id,
            symbols_text
        )

    except Exception as e:
        return (
            "--",
            f"Error: {str(e)[:30]}",
            "--",
            "fw-bold",
            "--",
            "--",
            "--",
            "Check backtest module"
        )


# T-054-B: Price History Chart Callbacks / 價格歷史圖表回調

def _load_price_history(symbol: str, hours: int = 24) -> tuple:
    """
    Load price history from indicator_snapshots.jsonl
    從 indicator_snapshots.jsonl 載入價格歷史
    
    Args:
        symbol: Symbol to load (e.g., "BTCUSDT")
        hours: Number of hours to look back
        
    Returns:
        Tuple of (timestamps, prices, ma5_values)
    """
    try:
        from config.paths import LOGS_DIR
        import json
        from datetime import datetime, timedelta
        
        snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"
        if not snapshot_file.exists():
            return [], [], []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        timestamps = []
        prices = []
        ma5_values = []
        
        with open(snapshot_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get("symbol") != symbol:
                        continue
                    
                    ts_str = record.get("timestamp", "")
                    if not ts_str:
                        continue
                    
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff_time:
                        continue
                    
                    price = record.get("price")
                    ma5 = record.get("ma5")
                    
                    if price is not None:
                        timestamps.append(ts.strftime("%H:%M"))
                        prices.append(price)
                        ma5_values.append(ma5 if ma5 is not None else price)
                        
                except Exception:
                    continue
        
        return timestamps, prices, ma5_values
        
    except Exception:
        return [], [], []


@callback(
    Output("check-history-table", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_check_history_table(n):
    """Update check history table / 更新檢查歷史表格 (T-055)"""
    try:
        check_history = _load_check_history(limit=10)
        
        if not check_history:
            return [
                dbc.Row(
                    dbc.Col(
                        html.P("No check history yet / 暫無檢查歷史", className="text-muted text-center py-3"),
                        width=12
                    )
                )
            ]
        
        rows = []
        for i, check in enumerate(check_history):
            # Format time
            time_str = check.get("time", "--")
            
            # Get prices
            btc_price = check.get("btc_price")
            eth_price = check.get("eth_price")
            
            btc_display = f"${btc_price:,.0f}" if btc_price else "--"
            eth_display = f"${eth_price:,.0f}" if eth_price else "--"
            
            # Get signals
            signals_count = check.get("signals_count", 0)
            confirmed = check.get("confirmed_signals", 0)
            
            if signals_count > 0:
                if confirmed > 0:
                    signal_display = html.Span(f"{signals_count} ({confirmed}✓)", className="text-success")
                else:
                    signal_display = html.Span(f"{signals_count} (👁️)", className="text-info")
            else:
                signal_display = html.Span("None", className="text-muted")
            
            # Highlight latest row
            is_latest = (i == 0)
            row_style = {"backgroundColor": "#d4edda"} if is_latest else {}
            
            row = dbc.Row(
                [
                    dbc.Col(html.Span(time_str, className="fw-bold" if is_latest else ""), width=3, className="text-center py-2"),
                    dbc.Col(btc_display, width=3, className="text-center py-2"),
                    dbc.Col(eth_display, width=3, className="text-center py-2"),
                    dbc.Col(signal_display, width=3, className="text-center py-2"),
                ],
                className="border-bottom align-items-center",
                style=row_style
            )
            rows.append(row)
        
        return rows
        
    except Exception as e:
        return [
            dbc.Row(
                dbc.Col(
                    html.P(f"Error loading history: {e}", className="text-danger text-center py-3"),
                    width=12
                )
            )
        ]


def _load_check_history(limit: int = 10) -> list:
    """
    Load check history from indicator_snapshots.jsonl
    從 indicator_snapshots.jsonl 載入檢查歷史
    
    Args:
        limit: Maximum number of checks to return
        
    Returns:
        List of check records with time, prices, and signals
    """
    try:
        from config.paths import LOGS_DIR
        import json
        from collections import defaultdict
        
        snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"
        if not snapshot_file.exists():
            return []
        
        # Group by run_id
        runs = defaultdict(lambda: {"btc_price": None, "eth_price": None, "signals_count": 0, "confirmed_signals": 0})
        
        with open(snapshot_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    run_id = str(record.get("run_id", ""))
                    symbol = record.get("symbol")
                    price = record.get("price")
                    ts_str = record.get("timestamp", "")
                    signals = record.get("signals_count", 0)
                    
                    if not run_id or not ts_str:
                        continue
                    
                    # Parse timestamp
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        time_str = ts.strftime("%H:%M:%S")
                    except:
                        time_str = ts_str
                    
                    runs[run_id]["time"] = time_str
                    runs[run_id]["timestamp"] = ts_str
                    
                    if symbol == "BTCUSDT" and price:
                        runs[run_id]["btc_price"] = price
                    elif symbol == "ETHUSDT" and price:
                        runs[run_id]["eth_price"] = price
                    
                    runs[run_id]["signals_count"] = max(runs[run_id]["signals_count"], signals)
                    
                except Exception:
                    continue
        
        # Convert to list and sort by timestamp (newest first)
        history = []
        for run_id, data in runs.items():
            if data.get("btc_price") or data.get("eth_price"):
                history.append({
                    "run_id": run_id,
                    "time": data.get("time", "--"),
                    "timestamp": data.get("timestamp", ""),
                    "btc_price": data.get("btc_price"),
                    "eth_price": data.get("eth_price"),
                    "signals_count": data.get("signals_count", 0),
                    "confirmed_signals": data.get("confirmed_signals", 0)
                })
        
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history[:limit]
        
    except Exception:
        return []
