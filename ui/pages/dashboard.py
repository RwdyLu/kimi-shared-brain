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
        dbc.Row([
            dbc.Col([
                html.H2("Dashboard", className="mb-4"),
                html.P("System overview and quick status / 系統概覽與快速狀態", className="text-muted"),
            ], width=8),
            # T-061: Health Timestamp Display
            dbc.Col([
                html.Div([
                    html.Small("最後更新 / Last Update:", className="text-muted d-block"),
                    html.Span(id="health-timestamp", children="--", className="badge bg-secondary")
                ], className="text-end mt-2")
            ], width=4)
        ]),
        
        html.Hr(),
        
        # T-074: Three Column Layout / 三欄布局
        dbc.Row(
            [
                # Left Column - Agent Status (T-075 placeholder) / 左欄 - Agent 狀態
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("🤖 Agent Status / 代理狀態", className="fw-bold"),
                            dbc.CardBody(
                                id="left-panel-agent-status",
                                children=[
                                    html.P("Loading agent status...", className="text-muted")
                                ]
                            )
                        ],
                        color="dark",
                        outline=True
                    ),
                    width=12,
                    md=3,
                    className="mb-4"
                ),
                
                # Center Column - Strategy Ranking (T-076) / 中欄 - 策略排名
                dbc.Col(
                    [
                        # T-XXX: Symbol Selector / 幣種選擇器
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H4("Strategy Ranking / 策略排名", className="mb-2"),
                                        dcc.Dropdown(
                                            id="symbol-selector",
                                            options=[
                                                {"label": "BTCUSDT", "value": "BTCUSDT"},
                                                {"label": "ETHUSDT", "value": "ETHUSDT"},
                                                {"label": "BNBUSDT", "value": "BNBUSDT"},
                                                {"label": "SOLUSDT", "value": "SOLUSDT"},
                                                {"label": "XRPUSDT", "value": "XRPUSDT"},
                                                {"label": "ADAUSDT", "value": "ADAUSDT"},
                                                {"label": "DOGEUSDT", "value": "DOGEUSDT"},
                                                {"label": "AVAXUSDT", "value": "AVAXUSDT"},
                                                {"label": "LINKUSDT", "value": "LINKUSDT"},
                                                {"label": "DOTUSDT", "value": "DOTUSDT"},
                                            ],
                                            value="BTCUSDT",
                                            clearable=False,
                                            className="mb-3"
                                        )
                                    ],
                                    width=12
                                )
                            ]
                        ),
                        
                        dbc.Card(
                            [
                                dbc.CardHeader("📊 Rankings / 排名", className="fw-bold"),
                                dbc.CardBody(
                                    id="center-panel-strategy-ranking",
                                    children=[
                                        html.P("Loading strategy data...", className="text-muted")
                                    ]
                                )
                            ],
                            color="dark",
                            outline=True,
                            className="mb-3"
                        ),
                        
                        # T-078: FT Block / 待確認任務區塊
                        dbc.Card(
                            [
                                dbc.CardHeader("⏳ Pending Acceptance / 待確認", className="fw-bold"),
                                dbc.CardBody(
                                    id="center-panel-ft-block",
                                    children=[
                                        html.P("No pending tasks", className="text-muted")
                                    ]
                                )
                            ],
                            color="warning",
                            outline=True,
                            className="mb-3"
                        ),
                        
                        # T-079: Discovery Count Badge / 探索計數徽章
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.Div(
                                            [
                                                html.Span("📡 Today Signals / 今日訊號: ", className="fw-bold"),
                                                html.Span(id="discovery-count-badge", children="0", className="badge bg-info ms-2")
                                            ],
                                            className="text-center"
                                        )
                                    ]
                                )
                            ],
                            color="info",
                            outline=True
                        )
                    ],
                    width=12,
                    md=6,
                    className="mb-4"
                ),
                
                # Right Column - Signals + History (T-077 placeholder) / 右欄 - 訊號與歷史
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("🔔 Signals & History / 訊號與歷史", className="fw-bold"),
                            dbc.CardBody(
                                id="right-panel-signals-history",
                                children=[
                                    html.P("Loading signals...", className="text-muted")
                                ]
                            )
                        ],
                        color="dark",
                        outline=True
                    ),
                    width=12,
                    md=3,
                    className="mb-4"
                )
            ],
            className="mb-4"
        ),
        
        # Live Prices Section / 即時價格區塊
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Live Prices / 即時價格", className="mb-3"),
                        dbc.Row(id="live-prices-row", children=[])
                    ],
                    width=12
                )
            ],
            className="mb-4"
        ),
        
        # T-052-C: Strategy Status Section / 策略狀態區塊
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Strategy Status / 策略狀態", className="mb-3"),
                        dbc.Row(
                            [
                                # BTC Strategy Card
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardHeader("Bitcoin (BTCUSDT)", className="fw-bold"),
                                            dbc.CardBody(
                                                [
                                                    html.H5(id="btc-strategy-price", children="--"),
                                                    html.P(id="btc-price-change", children="", className="text-muted small"),
                                                    html.Hr(),
                                                    # MA Cross Long
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="btc-long-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" MA Cross Long", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="btc-long-distance", children="--", className="small text-muted"),
                                                        html.Div(id="btc-long-detail", children="--", className="small")
                                                    ], className="mb-3"),
                                                    # MA Cross Short
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="btc-short-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" MA Cross Short", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="btc-short-distance", children="--", className="small text-muted"),
                                                        html.Div(id="btc-short-detail", children="--", className="small")
                                                    ], className="mb-3"),
                                                    # Contrarian Oversold
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="btc-oversold-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" Contrarian Oversold", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="btc-oversold-distance", children="--", className="small text-muted"),
                                                        html.Div(id="btc-oversold-detail", children="--", className="small")
                                                    ], className="mb-3"),
                                                    # Contrarian Overbought
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="btc-overbought-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" Contrarian Overbought", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="btc-overbought-distance", children="--", className="small text-muted"),
                                                        html.Div(id="btc-overbought-detail", children="--", className="small")
                                                    ]),
                                                ]
                                            )
                                        ],
                                        color="info",
                                        outline=True
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                
                                # ETH Strategy Card
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardHeader("Ethereum (ETHUSDT)", className="fw-bold"),
                                            dbc.CardBody(
                                                [
                                                    html.H5(id="eth-strategy-price", children="--"),
                                                    html.P(id="eth-price-change-eth", children="", className="text-muted small"),
                                                    html.Hr(),
                                                    # MA Cross Long
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="eth-long-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" MA Cross Long", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="eth-long-distance", children="--", className="small text-muted"),
                                                        html.Div(id="eth-long-detail", children="--", className="small")
                                                    ], className="mb-3"),
                                                    # MA Cross Short
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="eth-short-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" MA Cross Short", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="eth-short-distance", children="--", className="small text-muted"),
                                                        html.Div(id="eth-short-detail", children="--", className="small")
                                                    ], className="mb-3"),
                                                    # Contrarian Oversold
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="eth-oversold-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" Contrarian Oversold", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="eth-oversold-distance", children="--", className="small text-muted"),
                                                        html.Div(id="eth-oversold-detail", children="--", className="small")
                                                    ], className="mb-3"),
                                                    # Contrarian Overbought
                                                    html.Div([
                                                        html.Div([
                                                            html.Span(id="eth-overbought-status", children="🔴", style={"fontSize": "16px"}),
                                                            html.Span(" Contrarian Overbought", className="ms-1 fw-bold")
                                                        ]),
                                                        html.Div(id="eth-overbought-distance", children="--", className="small text-muted"),
                                                        html.Div(id="eth-overbought-detail", children="--", className="small")
                                                    ]),
                                                ]
                                            )
                                        ],
                                        color="secondary",
                                        outline=True
                                    ),
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                            ]
                        ),
                        html.P("🟢 = Triggered | 🟡 = <0.5% | 🔴 = ≥0.5%", className="text-muted small mt-2")
                    ],
                    width=12
                )
            ],
            className="mb-4"
        ),
        
        # System Status Section / 系統狀態區塊
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("System Status / 系統狀態", className="mb-3"),
                        dbc.Row(
                            [
                                # Scheduler Card / 排程器卡片
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardBody(
                                                [
                                                    html.H5("Scheduler / 排程器", className="card-title"),
                                                    html.P(
                                                        id="scheduler-status",
                                                        children="Loading...",
                                                        className="mb-0"
                                                    ),
                                                    html.Small(
                                                        id="scheduler-next-run",
                                                        children="",
                                                        className="text-muted"
                                                    )
                                                ]
                                            )
                                        ],
                                        color="primary",
                                        outline=True
                                    ),
                                    width=12,
                                    md=4,
                                    className="mb-3"
                                ),
                                
                                # Last Run Card / 最後執行卡片
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardBody(
                                                [
                                                    html.H5("Last Run (Live) / 最後執行 (即時)", className="card-title"),
                                                    html.P(
                                                        id="last-run-time",
                                                        children="Loading...",
                                                        className="mb-0 fw-bold"
                                                    ),
                                                    html.Small(
                                                        id="last-run-result",
                                                        children="",
                                                        className="text-muted"
                                                    )
                                                ]
                                            )
                                        ],
                                        color="secondary",
                                        outline=True
                                    ),
                                    width=12,
                                    md=4,
                                    className="mb-3"
                                ),
                                
                                # Active Symbols Card / 啟用貨幣卡片
                                dbc.Col(
                                    dbc.Card(
                                        [
                                            dbc.CardBody(
                                                [
                                                    html.H5("Active Symbols / 啟用貨幣", className="card-title"),
                                                    html.Div(id="dashboard-symbols", children="Loading...")
                                                ]
                                            )
                                        ],
                                        color="warning",
                                        outline=True
                                    ),
                                    width=12,
                                    md=4,
                                    className="mb-3"
                                ),
                            ]
                        ),
                    ],
                    width=12
                )
            ],
            className="mb-4"
        ),
        
        # Signal Summary Section / 訊號摘要區塊
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Today's Signals / 今日訊號", className="mb-3"),
                        dbc.Card(
                            [
                                dbc.CardBody(
                                    [
                                        html.H3(
                                            id="dashboard-signals-count",
                                            children="--",
                                            className="text-center"
                                        ),
                                        html.P(
                                            id="dashboard-signals-breakdown",
                                            children="Loading...",
                                            className="text-center text-muted"
                                        ),
                                    ]
                                )
                            ],
                            id="dashboard-signals-card",
                            color="success",
                            outline=True
                        ),
                    ],
                    width=12,
                    md=6
                ),
            ],
            className="mb-4"
        ),
        
        # T-053-A: Recent Check History Section / 近期檢查歷史區塊
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4("Check History / 檢查歷史", className="mb-3"),
                        html.P("Recent monitor checks from last 24 hours", className="text-muted"),
                        dbc.Table(
                            [
                                html.Thead(
                                    html.Tr([
                                        html.Th("Time"),
                                        html.Th("Run ID"),
                                        html.Th("BTC Price"),
                                        html.Th("ETH Price"),
                                        html.Th("Signals"),
                                    ])
                                ),
                                html.Tbody(id="check-history-table", children=[])
                            ],
                            bordered=True,
                            hover=True,
                            size="sm",
                            responsive=True
                        ),
                    ],
                    width=12
                )
            ],
            className="mb-4"
        ),
        
        # Auto-refresh interval / 自動更新間隔 (10 seconds for prices)
        dcc.Interval(id="dashboard-interval", interval=10000),
        
    ],
    fluid=True,
    className="py-4"
)


# T-053: Dashboard Callbacks / 儀表板回調

@callback(
    Output("scheduler-status", "children"),
    Output("scheduler-status", "className"),
    Output("scheduler-next-run", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_scheduler(n):
    """Update scheduler status display"""
    try:
        status = get_scheduler_status()
        
        is_running = status.get("is_running", False)
        state = status.get("state", "unknown")
        interval_min = status.get("interval_minutes", 0)
        
        if is_running:
            text = f"🟢 Running ({state})"
            class_name = "text-success fw-bold mb-0"
        else:
            text = f"🔴 Stopped ({state})"
            class_name = "text-danger fw-bold mb-0"
        
        next_run = f"Interval: {interval_min} min"
        
        return text, class_name, next_run
    except Exception as e:
        return f"Error: {str(e)[:30]}", "text-danger mb-0", ""


@callback(
    Output("last-run-time", "children"),
    Output("last-run-result", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_last_run(n):
    """Update last run display using monitor service"""
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


# T-052-A: New Live Prices callback / 新的即時價格回調

# All 10 symbols with display names / 全部 10 個幣種及其顯示名稱
COIN_CONFIG = [
    {"symbol": "BTC", "name": "Bitcoin"},
    {"symbol": "ETH", "name": "Ethereum"},
    {"symbol": "BNB", "name": "BNB"},
    {"symbol": "SOL", "name": "Solana"},
    {"symbol": "XRP", "name": "XRP"},
    {"symbol": "ADA", "name": "Cardano"},
    {"symbol": "DOGE", "name": "Dogecoin"},
    {"symbol": "AVAX", "name": "Avalanche"},
    {"symbol": "LINK", "name": "Chainlink"},
    {"symbol": "DOT", "name": "Polkadot"},
]


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


def format_price_display(price: float) -> str:
    """Format price based on magnitude / 根據價格大小格式化"""
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.2f}"
    else:
        return f"${price:.4f}"


@callback(
    Output("live-prices-row", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_live_prices(n):
    """Update all 10 coin prices display / 更新全部 10 個幣種價格顯示"""
    try:
        prices_data = get_current_prices()
        
        if not prices_data or not prices_data.get("prices"):
            return dbc.Col(
                html.P("No price data available / 無價格資料", className="text-muted text-center"),
                width=12
            )
        
        prices = prices_data.get("prices", {})
        timestamp = prices_data.get("timestamp", "")
        time_text = format_update_time(timestamp) if timestamp else "Updated recently"
        
        cards = []
        for coin in COIN_CONFIG:
            symbol = coin["symbol"]
            name = coin["name"]
            key = f"{symbol}USDT"
            
            if key in prices:
                price = prices[key].get("price", 0)
                change_pct = prices[key].get("change_24h_pct", 0)
                price_text = format_price_display(price)
                
                # Format change with color
                if change_pct > 0:
                    change_text = f"+{change_pct:.2f}%"
                    change_color = "text-success"
                    arrow = "▲"
                elif change_pct < 0:
                    change_text = f"{change_pct:.2f}%"
                    change_color = "text-danger"
                    arrow = "▼"
                else:
                    change_text = "0.00%"
                    change_color = "text-muted"
                    arrow = "—"
            else:
                price_text = "--"
                change_text = "--"
                change_color = "text-muted"
                arrow = ""
            
            # Determine price color based on presence
            price_color = "text-primary" if key in prices else "text-muted"
            
            card = dbc.Col(
                dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                html.H5(name, className="card-title text-muted"),
                                html.H2(
                                    price_text,
                                    className=f"{price_color} fw-bold mb-1"
                                ),
                                html.P(
                                    [html.Span(arrow, className=f"{change_color} me-1"), html.Span(change_text, className=change_color)],
                                    className="small mb-2"
                                ),
                                html.P(
                                    time_text,
                                    className="text-muted small"
                                )
                            ]
                        )
                    ],
                    color="light",
                    outline=True
                ),
                width=6,
                md=3,
                lg=2,
                className="mb-3"
            )
            cards.append(card)
        
        return cards
        
    except Exception as e:
        return dbc.Col(
            html.P(f"Error loading prices: {str(e)[:50]}", className="text-danger"),
            width=12
        )


# T-061: Health Timestamp Callback / 健康時間戳回調
@callback(
    Output("health-timestamp", "children"),
    Output("health-timestamp", "className"),
    Input("dashboard-interval", "n_intervals")
)
def update_health_timestamp(n):
    """Update health timestamp display / 更新健康時間戳顯示 (T-061)"""
    try:
        from datetime import datetime
        
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        
        # Store last update time in a file for persistence
        last_update_file = Path("/tmp/kimi-shared-brain/.last_dashboard_update")
        last_update_file.write_text(now.isoformat())
        
        return time_str, "badge bg-success"
        
    except Exception as e:
        return "--", "badge bg-danger"


# T-061: Health Status Check / 健康狀態檢查
def get_health_status():
    """Check if dashboard has been updated within 10 minutes / 檢查儀表板是否在 10 分鐘內更新"""
    try:
        from datetime import datetime, timedelta
        
        last_update_file = Path("/tmp/kimi-shared-brain/.last_dashboard_update")
        if not last_update_file.exists():
            return "--", "badge bg-secondary"
        
        last_update_str = last_update_file.read_text().strip()
        last_update = datetime.fromisoformat(last_update_str)
        now = datetime.now()
        
        diff_minutes = (now - last_update).total_seconds() / 60
        time_str = last_update.strftime("%H:%M:%S")
        
        if diff_minutes > 10:
            return time_str, "badge bg-danger"  # Red if > 10 min
        else:
            return time_str, "badge bg-success"  # Green if <= 10 min
            
    except Exception:
        return "--", "badge bg-secondary"


# T-052-C: Strategy Status callbacks / 策略狀態回調 (FIXED: emoji rendering)

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
    """Update BTC strategy status display / 更新 BTC 策略狀態顯示 (T-059-B, FIXED)"""
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
                return html.Span("🟢", style={"fontSize": "16px"})
            elif distance is None:
                return html.Span("⚪", style={"fontSize": "16px"})
            elif abs(distance) < 0.5:
                return html.Span("🟡", style={"fontSize": "16px"})
            else:
                return html.Span("🔴", style={"fontSize": "16px"})
        
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
        oversold_color = html.Span("🟢", style={"fontSize": "16px"}) if oversold_triggered else (html.Span("🟡", style={"fontSize": "16px"}) if oversold_distance <= 1 else html.Span("🔴", style={"fontSize": "16px"}))
        oversold_dist_text = f"差 {oversold_distance} 根" if not oversold_triggered else "已觸發"
        oversold_detail = f"連續 {red_candles}/4 根紅 K"
        
        # Green candles (for overbought)
        green_candles = symbol_data.get("green_candles", 0) if isinstance(symbol_data, dict) else 0
        overbought_triggered = green_candles >= 4
        overbought_distance = max(0, 4 - green_candles)
        overbought_color = html.Span("🟢", style={"fontSize": "16px"}) if overbought_triggered else (html.Span("🟡", style={"fontSize": "16px"}) if overbought_distance <= 1 else html.Span("🔴", style={"fontSize": "16px"}))
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
        return ([f"Error: {str(e)[:20]}"] + ["--"] * 12)


@callback(
    Output("eth-strategy-price", "children"),
    Output("eth-price-change-eth", "children"),
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
    """Update ETH strategy status display / 更新 ETH 策略狀態顯示 (T-059-B, FIXED)"""
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
        
        # Color coding with html.Span for proper emoji rendering
        def get_status_color(distance, triggered):
            if triggered:
                return html.Span("🟢", style={"fontSize": "16px"})
            elif distance is None:
                return html.Span("⚪", style={"fontSize": "16px"})
            elif abs(distance) < 0.5:
                return html.Span("🟡", style={"fontSize": "16px"})
            else:
                return html.Span("🔴", style={"fontSize": "16px"})
        
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
        
        # Contrarian strategies
        run_data = last_run.get("data", {}) if last_run else {}
        symbol_data = run_data.get("ETHUSDT", {}) if isinstance(run_data, dict) else {}
        
        # Red candles
        red_candles = symbol_data.get("red_candles", 0) if isinstance(symbol_data, dict) else 0
        oversold_triggered = red_candles >= 4
        oversold_distance = max(0, 4 - red_candles)
        oversold_color = html.Span("🟢", style={"fontSize": "16px"}) if oversold_triggered else (html.Span("🟡", style={"fontSize": "16px"}) if oversold_distance <= 1 else html.Span("🔴", style={"fontSize": "16px"}))
        oversold_dist_text = f"差 {oversold_distance} 根" if not oversold_triggered else "已觸發"
        oversold_detail = f"連續 {red_candles}/4 根紅 K"
        
        # Green candles
        green_candles = symbol_data.get("green_candles", 0) if isinstance(symbol_data, dict) else 0
        overbought_triggered = green_candles >= 4
        overbought_distance = max(0, 4 - green_candles)
        overbought_color = html.Span("🟢", style={"fontSize": "16px"}) if overbought_triggered else (html.Span("🟡", style={"fontSize": "16px"}) if overbought_distance <= 1 else html.Span("🔴", style={"fontSize": "16px"}))
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
        return ([f"Error: {str(e)[:20]}"] + ["--"] * 12)


# T-053-B: Check History Callback / 檢查歷史回調
@callback(
    Output("check-history-table", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_check_history(n):
    """Update check history table from indicator_snapshots.jsonl"""
    try:
        history = _load_check_history(limit=10)
        
        if not history:
            return html.Tr([
                html.Td("No data", colSpan=5, className="text-center text-muted")
            ])
        
        rows = []
        for record in history:
            rows.append(html.Tr([
                html.Td(record.get("time", "--")),
                html.Td(record.get("run_id", "--")[:8]),
                html.Td(f"${record.get('btc_price', 0):,.2f}" if record.get('btc_price') else "--"),
                html.Td(f"${record.get('eth_price', 0):,.2f}" if record.get('eth_price') else "--"),
                html.Td(str(record.get("signals_count", 0))),
            ]))
        
        return rows
    except Exception as e:
        return html.Tr([
            html.Td(f"Error: {str(e)[:30]}", colSpan=5, className="text-danger")
        ])


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


# ============================================================================
# T-075, T-076, T-077, T-078, T-079: New Dashboard Panel Callbacks
# ============================================================================

# T-075: Left Panel Agent Status Callback / 左欄 Agent 狀態回調
@callback(
    Output("left-panel-agent-status", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_agent_status(n):
    """Update left panel agent status / 更新左欄 Agent 狀態 (T-075)"""
    try:
        import json
        from pathlib import Path
        
        tasks_file = Path("/tmp/kimi-shared-brain/state/tasks.json")
        if not tasks_file.exists():
            return html.P("Tasks file not found", className="text-muted")
        
        with open(tasks_file, 'r') as f:
            data = json.load(f)
        
        tasks = data.get("tasks", [])
        
        # Count by status
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
        assigned = sum(1 for t in tasks if t.get("status") == "assigned")
        
        # Find current tasks per agent
        kimiclaw_tasks = [t for t in tasks if t.get("assigned_to") == "kimiclaw_bot" and t.get("status") in ["in_progress", "assigned"]]
        second_bot_tasks = [t for t in tasks if t.get("assigned_to") == "second_bot" and t.get("status") in ["in_progress", "assigned"]]
        
        # Build status cards
        return html.Div([
            # Kimiclaw Bot Status
            html.Div([
                html.H6("🤖 kimiclaw_bot", className="fw-bold text-info mb-2"),
                html.Div([
                    dbc.Badge("WORKING" if kimiclaw_tasks else "IDLE", 
                             color="success" if kimiclaw_tasks else "secondary", 
                             className="me-2")
                ], className="mb-2"),
                html.Small(
                    f"Current: {', '.join(t.get('task_id', 'None') for t in kimiclaw_tasks[:3])}" if kimiclaw_tasks else "No active tasks",
                    className="text-muted d-block"
                )
            ], className="mb-4 pb-3 border-bottom border-secondary"),
            
            # Second Bot Status
            html.Div([
                html.H6("🤖 second_bot", className="fw-bold text-info mb-2"),
                html.Div([
                    dbc.Badge("WORKING" if second_bot_tasks else "IDLE", 
                             color="success" if second_bot_tasks else "secondary", 
                             className="me-2")
                ], className="mb-2"),
                html.Small(
                    f"Current: {', '.join(t.get('task_id', 'None') for t in second_bot_tasks[:3])}" if second_bot_tasks else "No active tasks",
                    className="text-muted d-block"
                )
            ], className="mb-4 pb-3 border-bottom border-secondary"),
            
            # Task Summary
            html.Div([
                html.H6("📊 Task Summary", className="fw-bold mb-2"),
                html.Div([
                    dbc.Badge(f"{completed}", color="success", className="me-1"),
                    html.Small("Completed", className="text-muted")
                ], className="mb-1"),
                html.Div([
                    dbc.Badge(f"{in_progress}", color="warning", className="me-1"),
                    html.Small("In Progress", className="text-muted")
                ], className="mb-1"),
                html.Div([
                    dbc.Badge(f"{assigned}", color="primary", className="me-1"),
                    html.Small("Assigned", className="text-muted")
                ], className="mb-1")
            ])
        ])
        
    except Exception as e:
        return html.P(f"Error loading agent status: {str(e)[:50]}", className="text-danger")


# T-076: Center Panel Strategy Ranking Callback / 中欄策略排名回調
@callback(
    Output("center-panel-strategy-ranking", "children"),
    Input("dashboard-interval", "n_intervals"),
    Input("symbol-selector", "value")
)
def update_strategy_ranking(n, selected_symbol):
    """Update center panel strategy ranking / 更新中欄策略排名 (T-076)
    
    Uses live strategy ranking data for all symbols / 使用所有幣種的即時策略排名資料
    """
    try:
        # Load live strategy ranking / 載入即時策略排名
        import json
        from pathlib import Path
        
        ranking_file = Path("/tmp/kimi-shared-brain/state/live_strategy_ranking.json")
        if not ranking_file.exists():
            # Fallback to backtest storage
            from backtest import BacktestStorage
            storage = BacktestStorage()
            backtests = storage.get_latest_backtests(limit=100)
            
            if not backtests:
                return html.Div([
                    html.P("No strategy data available", className="text-muted text-center"),
                    html.Small("Run monitoring to generate strategy rankings", className="text-muted d-block text-center")
                ])
            
            symbol_backtests = [bt for bt in backtests if selected_symbol in bt.get("symbols", [])]
            if not symbol_backtests:
                return html.Div([
                    html.P(f"No backtest data for {selected_symbol}", className="text-muted text-center"),
                    html.Small("Backtests for this symbol will appear here", className="text-muted d-block text-center")
                ])
            
            rows = []
            for i, bt in enumerate(symbol_backtests[:10], 1):
                strategy = bt.get("strategy", "Unknown")
                total_trades = bt.get("total_trades", 0)
                win_rate = bt.get("win_rate", 0)
                total_return = bt.get("total_return_pct", 0)
                max_dd = bt.get("max_drawdown_pct", 0)
                
                return_color = "text-success" if total_return >= 0 else "text-danger"
                winrate_color = "text-success" if win_rate >= 50 else "text-warning" if win_rate >= 30 else "text-danger"
                
                rows.append(html.Tr([
                    html.Td(f"#{i}", className="text-muted"),
                    html.Td(f"{strategy[:15]}", className="fw-bold"),
                    html.Td(f"{total_trades}"),
                    html.Td(f"{win_rate:.1f}%", className=winrate_color),
                    html.Td(f"{total_return:+.2f}%", className=return_color),
                    html.Td(f"{max_dd:.2f}%", className="text-danger")
                ]))
            
            return html.Div([
                html.Div([
                    html.Small(f"{selected_symbol} — Last updated: {datetime.now().strftime('%H:%M:%S')}", className="text-muted")
                ], className="text-end mb-2"),
                dbc.Table(
                    [
                        html.Thead(html.Tr([
                            html.Th("#"), html.Th("Strategy"), html.Th("Trades"),
                            html.Th("WR%"), html.Th("Return%"), html.Th("MaxDD%")
                        ]))
                    ] + [html.Tbody(rows)],
                    bordered=False,
                    hover=True,
                    size="sm"
                )
            ])
        
        with open(ranking_file, 'r') as f:
            ranking_data = json.load(f)
        
        symbol_scores = ranking_data.get("symbol_scores", {})
        symbol_data = symbol_scores.get(selected_symbol, [])
        
        if not symbol_data:
            return html.Div([
                html.P(f"No live strategy data for {selected_symbol}", className="text-muted text-center"),
                html.Small("Monitoring will populate data after next run", className="text-muted d-block text-center")
            ])
        
        # Build ranking table from live data / 從即時資料建立排名表
        rows = []
        for i, item in enumerate(symbol_data, 1):
            strategy = item.get("strategy", "Unknown")
            score = item.get("score", 0)
            
            # Color coding based on score / 根據分數顏色編碼
            if score >= 60:
                score_color = "text-success fw-bold"
                status_icon = "🟢"
            elif score >= 40:
                score_color = "text-warning"
                status_icon = "🟡"
            else:
                score_color = "text-muted"
                status_icon = "🔴"
            
            rows.append(html.Tr([
                html.Td(f"#{i}", className="text-muted"),
                html.Td(dcc.Link(f"{strategy[:20]}", href=f"/strategy/{strategy}", className="fw-bold text-decoration-none")),
                html.Td(f"{status_icon} {score:.1f}%", className=score_color),
            ]))
        
        # Also show best opportunities for this symbol / 也顯示該幣種的最佳機會
        best_opps = ranking_data.get("best_opportunities", [])
        symbol_opps = [o for o in best_opps if o.get("symbol") == selected_symbol]
        
        opp_section = html.Div()
        if symbol_opps:
            opp_rows = []
            for opp in symbol_opps[:3]:
                opp_rows.append(html.Tr([
                    html.Td(f"{opp.get('strategy_name', 'Unknown')[:20]}", className="fw-bold small"),
                    html.Td(f"Score: {opp.get('score', 0):.1f}%", className="text-info small"),
                    html.Td(f"${opp.get('price', 0):,.2f}", className="text-muted small")
                ]))
            
            opp_section = html.Div([
                html.Hr(className="my-2"),
                html.H6("🎯 Best Opportunities / 最佳機會", className="fw-bold mb-2"),
                dbc.Table(
                    [html.Thead(html.Tr([
                        html.Th("Strategy"), html.Th("Score"), html.Th("Price")
                    ]))] + [html.Tbody(opp_rows)],
                    bordered=False,
                    hover=True,
                    size="sm"
                )
            ])
        
        timestamp = ranking_data.get("timestamp", "")
        time_display = datetime.fromisoformat(timestamp).strftime('%H:%M:%S') if timestamp else "Recently"
        
        return html.Div([
            html.Div([
                html.Small(f"{selected_symbol} — Live @ {time_display}", className="text-muted")
            ], className="text-end mb-2"),
            dbc.Table(
                [
                    html.Thead(html.Tr([
                        html.Th("#"), html.Th("Strategy"), html.Th("Score")
                    ]))
                ] + [html.Tbody(rows)],
                bordered=False,
                hover=True,
                size="sm"
            ),
            opp_section
        ])
        
    except Exception as e:
        return html.P(f"Error loading rankings: {str(e)[:80]}", className="text-danger")


# T-077: Right Panel Signals + History Callback / 右欄訊號與歷史回調
@callback(
    Output("right-panel-signals-history", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_signals_history(n):
    """Update right panel signals and history / 更新右欄訊號與歷史 (T-077)"""
    try:
        from backtest import BacktestStorage
        from ui.services.monitor_service import get_today_signals
        
        # Get watch signals
        signals = get_today_signals()
        watch_signals = []  # Placeholder - would filter for watch-only
        
        # Get backtest history
        storage = BacktestStorage()
        backtests = storage.get_latest_backtests(limit=7)
        
        return html.Div([
            # Watch Signals Section
            html.Div([
                html.H6(f"🔔 Watch Signals ({signals.get('total', 0)})", className="fw-bold mb-2"),
                html.Hr(className="my-2"),
                
                # Signal count badge
                html.Div([
                    dbc.Badge(f"{signals.get('confirmed', 0)} Confirmed", color="success", className="me-2"),
                    dbc.Badge(f"{signals.get('watch_only', 0)} Watch", color="warning")
                ], className="mb-3"),
                
                # Signal list placeholder (would show actual signals)
                html.Small("Signals from last run displayed here", className="text-muted d-block")
            ], className="mb-4 pb-3 border-bottom border-secondary"),
            
            # Backtest History Section
            html.Div([
                html.H6("📈 Recent Backtests (7)", className="fw-bold mb-2"),
                html.Hr(className="my-2"),
                
                # Backtest list
                html.Div([
                    html.Div([
                        html.Div([
                            html.Small(f"{bt.get('backtest_id', '--')[:20]}", className="fw-bold d-block"),
                            html.Small(
                                f"Return: {bt.get('total_return_pct', 0):+.1f}% | WR: {bt.get('win_rate', 0):.0f}%",
                                className="text-muted"
                            )
                        ], className="mb-2 pb-2 border-bottom border-secondary")
                        for bt in backtests[:7]
                    ]) if backtests else html.Small("No backtest history", className="text-muted")
                ])
            ])
        ])
        
    except Exception as e:
        return html.P(f"Error loading signals/history: {str(e)[:50]}", className="text-danger")


# T-078: FT Block Callback / 待確認任務回調
@callback(
    Output("center-panel-ft-block", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_ft_block(n):
    """Update FT block with pending acceptance tasks / 更新待確認任務區塊 (T-078)"""
    try:
        import json
        from pathlib import Path
        
        tasks_file = Path("/tmp/kimi-shared-brain/state/tasks.json")
        if not tasks_file.exists():
            return html.P("No pending tasks", className="text-muted")
        
        with open(tasks_file, 'r') as f:
            data = json.load(f)
        
        # Find completed but not reviewed tasks
        pending = [t for t in data.get("tasks", []) 
                   if t.get("status") == "completed" and not t.get("reviewed_by")]
        
        if not pending:
            return html.P("No pending acceptance tasks", className="text-muted text-center")
        
        return html.Div([
            html.Div([
                html.Div([
                    html.Small(f"📋 {t.get('task_id', '--')}: {t.get('title', 'No title')[:30]}...", 
                              className="d-block fw-bold"),
                    html.Small(f"Completed: {t.get('completed_at', '--')}", className="text-muted")
                ], className="mb-2 pb-2 border-bottom border-secondary")
                for t in pending[:5]
            ])
        ])
        
    except Exception as e:
        return html.P(f"Error: {str(e)[:30]}", className="text-danger")


# T-079: Discovery Count Badge Callback / 探索計數徽章回調
@callback(
    Output("discovery-count-badge", "children"),
    Input("dashboard-interval", "n_intervals")
)
def update_discovery_count(n):
    """Update discovery count badge / 更新探索計數徽章 (T-079)"""
    try:
        from ui.services.monitor_service import get_today_signals
        signals = get_today_signals()
        return str(signals.get("total", 0))
    except Exception:
        return "0"
