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
                                # BTC Strategy Distance Card
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardHeader([
                                                html.Strong("BTC Strategy Distance / BTC 策略距離"),
                                            ]),
                                            dbc.CardBody(
                                                [
                                                    # Price Section
                                                    html.H5("Current Price / 現價", className="text-muted mb-2"),
                                                    html.H3(id="btc-strategy-price", children="--", className="text-success mb-3"),
                                                    html.Hr(),
                                                    
                                                    # MA Distance Section
                                                    html.H6("MA Distance / MA 距離", className="text-muted mb-2"),
                                                    html.Div(id="btc-ma5-distance", children="--", className="mb-1"),
                                                    html.Div(id="btc-ma20-distance", children="--", className="mb-1"),
                                                    html.Div(id="btc-ma240-distance", children="--", className="mb-3"),
                                                    html.Hr(),
                                                    
                                                    # Strategy Conditions
                                                    html.H6("Trigger Conditions / 觸發條件", className="text-muted mb-2"),
                                                    html.Small([
                                                        html.Div("• Trend Long: MA5 cross above MA20 + volume", className="text-muted"),
                                                        html.Div("• Trend Short: MA5 cross below MA20", className="text-muted"),
                                                        html.Div("• Contrarian Oversold: 4 red candles + low volume", className="text-muted"),
                                                        html.Div("• Contrarian Overbought: 4 green candles + high volume", className="text-muted"),
                                                    ], className="d-block mb-3"),
                                                    html.Hr(),
                                                    
                                                    # Recent Signal
                                                    html.H6("Recent Signal / 最近訊號", className="text-muted mb-2"),
                                                    html.Div(id="btc-recent-signal", children="No recent signals / 無近期訊號"),
                                                ]
                                            )
                                        ],
                                        className="h-100"
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                
                                # ETH Strategy Distance Card
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardHeader([
                                                html.Strong("ETH Strategy Distance / ETH 策略距離"),
                                            ]),
                                            dbc.CardBody(
                                                [
                                                    # Price Section
                                                    html.H5("Current Price / 現價", className="text-muted mb-2"),
                                                    html.H3(id="eth-strategy-price", children="--", className="text-success mb-3"),
                                                    html.Hr(),
                                                    
                                                    # MA Distance Section
                                                    html.H6("MA Distance / MA 距離", className="text-muted mb-2"),
                                                    html.Div(id="eth-ma5-distance", children="--", className="mb-1"),
                                                    html.Div(id="eth-ma20-distance", children="--", className="mb-1"),
                                                    html.Div(id="eth-ma240-distance", children="--", className="mb-3"),
                                                    html.Hr(),
                                                    
                                                    # Strategy Conditions
                                                    html.H6("Trigger Conditions / 觸發條件", className="text-muted mb-2"),
                                                    html.Small([
                                                        html.Div("• Trend Long: MA5 cross above MA20 + volume", className="text-muted"),
                                                        html.Div("• Trend Short: MA5 cross below MA20", className="text-muted"),
                                                        html.Div("• Contrarian Oversold: 4 red candles + low volume", className="text-muted"),
                                                        html.Div("• Contrarian Overbought: 4 green candles + high volume", className="text-muted"),
                                                    ], className="d-block mb-3"),
                                                    html.Hr(),
                                                    
                                                    # Recent Signal
                                                    html.H6("Recent Signal / 最近訊號", className="text-muted mb-2"),
                                                    html.Div(id="eth-recent-signal", children="No recent signals / 無近期訊號"),
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
            interval=15*1000,  # 15 seconds / 15 秒 (T-052-A)
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
            
            # Format timestamp
            timestamp = prices_data.get("timestamp", "")
            time_text = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_text = f"Updated {dt.strftime('%H:%M:%S')}"
                except:
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
            
            # Format timestamp
            timestamp = prices_data.get("timestamp", "")
            time_text = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_text = f"Updated {dt.strftime('%H:%M:%S')}"
                except:
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
    Output("btc-ma5-distance", "children"),
    Output("btc-ma20-distance", "children"),
    Output("btc-ma240-distance", "children"),
    Output("btc-recent-signal", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_btc_strategy_distance(n):
    """Update BTC strategy distance display / 更新 BTC 策略距離顯示"""
    try:
        from ui.services.monitor_service import get_latest_indicator_snapshots
        
        snapshots = get_latest_indicator_snapshots()
        
        if not snapshots or "BTCUSDT" not in snapshots:
            return "--", "--", "--", "--", "Data unavailable / 資料不可用"
        
        data = snapshots["BTCUSDT"]
        
        # Price
        price = data.get("price")
        price_text = f"${price:,.2f}" if price else "--"
        
        # MA Distances
        ma5_pct = data.get("price_vs_ma5_pct")
        ma5_text, ma5_color = _format_ma_distance(ma5_pct)
        ma5_display = html.Span([
            "MA5: ",
            html.Span(ma5_text, className=f"text-{ma5_color}")
        ])
        
        ma20_pct = data.get("price_vs_ma20_pct")
        ma20_text, ma20_color = _format_ma_distance(ma20_pct)
        ma20_display = html.Span([
            "MA20: ",
            html.Span(ma20_text, className=f"text-{ma20_color}")
        ])
        
        ma240_pct = data.get("price_vs_ma240_pct")
        ma240_text, ma240_color = _format_ma_distance(ma240_pct)
        ma240_display = html.Span([
            "MA240: ",
            html.Span(ma240_text, className=f"text-{ma240_color}")
        ])
        
        # Recent signal
        signal_types = data.get("signal_types", [])
        signal_count = data.get("signals_count", 0)
        if signal_count > 0 and signal_types:
            recent_signal = html.Div([
                html.Span(f"{signal_count} signal(s) / {signal_count} 個訊號", className="text-warning"),
                html.Div([html.Small(f"• {s}") for s in signal_types], className="text-muted")
            ])
        else:
            recent_signal = "No signals / 無訊號"
        
        return price_text, ma5_display, ma20_display, ma240_display, recent_signal
        
    except Exception as e:
        return "--", "--", "--", "--", f"Error: {e}"


@callback(
    Output("eth-strategy-price", "children"),
    Output("eth-ma5-distance", "children"),
    Output("eth-ma20-distance", "children"),
    Output("eth-ma240-distance", "children"),
    Output("eth-recent-signal", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_eth_strategy_distance(n):
    """Update ETH strategy distance display / 更新 ETH 策略距離顯示"""
    try:
        from ui.services.monitor_service import get_latest_indicator_snapshots
        
        snapshots = get_latest_indicator_snapshots()
        
        if not snapshots or "ETHUSDT" not in snapshots:
            return "--", "--", "--", "--", "Data unavailable / 資料不可用"
        
        data = snapshots["ETHUSDT"]
        
        # Price
        price = data.get("price")
        price_text = f"${price:,.2f}" if price else "--"
        
        # MA Distances
        ma5_pct = data.get("price_vs_ma5_pct")
        ma5_text, ma5_color = _format_ma_distance(ma5_pct)
        ma5_display = html.Span([
            "MA5: ",
            html.Span(ma5_text, className=f"text-{ma5_color}")
        ])
        
        ma20_pct = data.get("price_vs_ma20_pct")
        ma20_text, ma20_color = _format_ma_distance(ma20_pct)
        ma20_display = html.Span([
            "MA20: ",
            html.Span(ma20_text, className=f"text-{ma20_color}")
        ])
        
        ma240_pct = data.get("price_vs_ma240_pct")
        ma240_text, ma240_color = _format_ma_distance(ma240_pct)
        ma240_display = html.Span([
            "MA240: ",
            html.Span(ma240_text, className=f"text-{ma240_color}")
        ])
        
        # Recent signal
        signal_types = data.get("signal_types", [])
        signal_count = data.get("signals_count", 0)
        if signal_count > 0 and signal_types:
            recent_signal = html.Div([
                html.Span(f"{signal_count} signal(s) / {signal_count} 個訊號", className="text-warning"),
                html.Div([html.Small(f"• {s}") for s in signal_types], className="text-muted")
            ])
        else:
            recent_signal = "No signals / 無訊號"
        
        return price_text, ma5_display, ma20_display, ma240_display, recent_signal
        
    except Exception as e:
        return "--", "--", "--", "--", f"Error: {e}"


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
