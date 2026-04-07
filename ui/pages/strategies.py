"""
Strategies Page / 策略頁面

Strategy registry and management.
策略註冊表與管理。
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
import sys

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Register page / 註冊頁面
dash.register_page(__name__, path="/strategies", title="Strategies")

# Load strategies / 載入策略
def load_strategies():
    """Load strategies from config"""
    try:
        from config.loader import get_strategies
        return get_strategies()
    except Exception as e:
        return {"error": str(e)}


# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Strategies", className="mb-4"),
        html.P("Strategy registry and management / 策略註冊表與管理", className="text-muted"),
        
        html.Hr(),
        
        # Strategy list / 策略列表
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Registered Strategies / 已註冊策略", className="mb-0"),
                        html.Small("Enable/disable strategies and view details / 啟用/停用策略並查看詳情", className="text-muted")
                    ]
                ),
                dbc.CardBody(
                    id="strategies-list",
                    children=render_strategies_list()
                )
            ],
            className="mb-4"
        ),
        
        # Strategy extensibility info / 策略擴充資訊
        dbc.Card(
            [
                dbc.CardHeader("Strategy Extensibility / 策略擴充"),
                dbc.CardBody(
                    [
                        html.H6("Current Status / 目前狀態", className="card-subtitle mb-2"),
                        html.P("✅ Config-driven strategy registry enabled", className="text-success"),
                        html.P("Strategies are defined in config/strategies.json", className="text-muted"),
                        
                        html.Hr(),
                        
                        html.H6("Future Features / 未來功能", className="card-subtitle mb-2"),
                        html.Ul(
                            [
                                html.Li("Visual strategy builder / 視覺化策略建立器"),
                                html.Li("Custom strategy upload / 自訂策略上傳"),
                                html.Li("Strategy performance metrics / 策略績效指標"),
                                html.Li("Backtesting integration / 回測整合"),
                            ],
                            className="text-muted"
                        ),
                        
                        dbc.Alert(
                            [
                                html.Strong("Note / 注意"),
                                html.Br(),
                                "Strategy editing is disabled for MVP. Modify config/strategies.json manually."
                                " / 策略編輯在 MVP 中停用。請手動修改 config/strategies.json。"
                            ],
                            color="info",
                            className="mt-3"
                        )
                    ]
                )
            ]
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="strategies-interval",
            interval=60*1000,  # 60 seconds
            n_intervals=0
        ),
    ],
    fluid=True
)


def render_strategies_list():
    """Render the strategies list"""
    data = load_strategies()
    
    if "error" in data:
        return dbc.Alert(f"Error loading strategies / 載入策略錯誤: {data['error']}", color="danger")
    
    strategies = data.get("strategies", [])
    
    if not strategies:
        return html.P("No strategies registered / 無已註冊策略", className="text-muted")
    
    return dbc.Accordion(
        [
            dbc.AccordionItem(
                render_strategy_details(strategy),
                title=render_strategy_title(strategy),
                item_id=strategy.get("id", f"strategy-{i}")
            )
            for i, strategy in enumerate(strategies)
        ],
        start_collapsed=True
    )


def render_strategy_title(strategy):
    """Render strategy title with status badge"""
    name = strategy.get("name", "Unknown")
    enabled = strategy.get("enabled", False)
    
    badge_color = "success" if enabled else "secondary"
    badge_text = "Enabled / 啟用" if enabled else "Disabled / 停用"
    
    return html.Div(
        [
            html.Span(name),
            dbc.Badge(badge_text, color=badge_color, className="ms-2")
        ],
        className="d-flex align-items-center"
    )


def render_strategy_details(strategy):
    """Render detailed view of a strategy"""
    strategy_type = strategy.get("type", "unknown")
    type_colors = {
        "trend": "primary",
        "contrarian": "info",
        "mean_reversion": "warning"
    }
    
    return html.Div(
        [
            # Header info / 標題資訊
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H6("Type / 類型"),
                            dbc.Badge(
                                strategy_type.upper(),
                                color=type_colors.get(strategy_type, "secondary"),
                                className="mb-3"
                            ),
                        ],
                        width=6,
                        md=3
                    ),
                    dbc.Col(
                        [
                            html.H6("ID"),
                            html.Code(strategy.get("id", "N/A"), className="mb-3 d-block"),
                        ],
                        width=6,
                        md=3
                    ),
                    dbc.Col(
                        [
                            html.H6("Chinese Name / 中文名稱"),
                            html.P(strategy.get("name_zh", "N/A"), className="mb-3"),
                        ],
                        width=6,
                        md=3
                    ),
                    dbc.Col(
                        [
                            html.H6("Status / 狀態"),
                            dbc.Badge(
                                "✓ Enabled" if strategy.get("enabled") else "✗ Disabled",
                                color="success" if strategy.get("enabled") else "secondary",
                                className="mb-3"
                            ),
                        ],
                        width=6,
                        md=3
                    ),
                ]
            ),
            
            html.Hr(),
            
            # Description / 說明
            html.H6("Description / 說明"),
            html.P(strategy.get("description", "No description / 無說明")),
            html.P(strategy.get("description_zh", ""), className="text-muted"),
            
            html.Hr(),
            
            # Configuration / 配置
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H6("Symbols / 標的"),
                            html.Div(
                                [
                                    dbc.Badge(symbol, color="light", text_color="dark", className="me-1 mb-1")
                                    for symbol in strategy.get("symbols", [])
                                ]
                            ),
                        ],
                        width=12,
                        md=6,
                        className="mb-3"
                    ),
                    dbc.Col(
                        [
                            html.H6("Timeframes / 時間框架"),
                            html.Div(
                                [
                                    dbc.Badge(tf, color="light", text_color="dark", className="me-1 mb-1")
                                    for tf in strategy.get("timeframes", [])
                                ]
                            ),
                        ],
                        width=12,
                        md=6,
                        className="mb-3"
                    ),
                ]
            ),
            
            html.Hr(),
            
            # Conditions / 條件
            html.H6("Conditions / 條件"),
            html.Ul([html.Li(condition) for condition in strategy.get("conditions", [])]),
            
            # Parameters / 參數
            html.H6("Parameters / 參數"),
            dbc.Table(
                [
                    html.Thead(html.Tr([html.Th("Parameter"), html.Th("Value")])),
                    html.Tbody([
                        html.Tr([html.Td(k), html.Td(str(v))])
                        for k, v in strategy.get("parameters", {}).items()
                    ])
                ],
                bordered=True,
                size="sm",
                className="w-auto"
            ),
            
            # Signal info / 訊號資訊
            html.Hr(),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H6("Signal Type / 訊號類型"),
                            html.Code(strategy.get("signal_type", "N/A")),
                        ],
                        width=6,
                        md=4
                    ),
                    dbc.Col(
                        [
                            html.H6("Signal Level / 訊號層級"),
                            dbc.Badge(
                                strategy.get("signal_level", "N/A").upper(),
                                color="success" if strategy.get("signal_level") == "confirmed" else "info"
                            ),
                        ],
                        width=6,
                        md=4
                    ),
                ]
            ),
            
            # Warning (if applicable) / 警告（如適用）
            if strategy.get("warning"):
                dbc.Alert(
                    strategy.get("warning"),
                    color="warning",
                    className="mt-3"
                )
            else:
                None
        ]
    )


# Callback to refresh strategies list / 刷新策略列表回調
@callback(
    Output("strategies-list", "children"),
    Input("strategies-interval", "n_intervals")
)
def refresh_strategies(n):
    """Refresh strategies list"""
    return render_strategies_list()
