"""
Signals Page / 訊號頁面

Signal history and alert viewing.
訊號歷史與提醒查看。
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
from dash import dash_table
import sys

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Register page / 註冊頁面
dash.register_page(__name__, path="/signals", title="Signals")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Signals", className="mb-4"),
        html.P("Signal history and alert feed / 訊號歷史與提醒串流", className="text-muted"),
        
        html.Hr(),
        
        # Filters / 篩選器
        dbc.Card(
            dbc.CardBody(
                [
                    html.H5("Filters / 篩選", className="card-title"),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Signal Type / 訊號類型"),
                                    dbc.Select(
                                        id="signals-filter-type",
                                        options=[
                                            {"label": "All Types / 全部", "value": "all"},
                                            {"label": "Trend Long / 順勢做多", "value": "trend_long"},
                                            {"label": "Trend Short / 順勢做空", "value": "trend_short"},
                                            {"label": "Contrarian Watch / 逆勢觀察", "value": "contrarian"},
                                        ],
                                        value="all"
                                    )
                                ],
                                width=12,
                                md=4,
                                className="mb-3"
                            ),
                            dbc.Col(
                                [
                                    html.Label("Symbol / 標的"),
                                    dbc.Select(
                                        id="signals-filter-symbol",
                                        options=[
                                            {"label": "All Symbols / 全部", "value": "all"},
                                            {"label": "BTCUSDT", "value": "BTCUSDT"},
                                            {"label": "ETHUSDT", "value": "ETHUSDT"},
                                        ],
                                        value="all"
                                    )
                                ],
                                width=12,
                                md=4,
                                className="mb-3"
                            ),
                            dbc.Col(
                                [
                                    html.Label("Time Range / 時間範圍"),
                                    dbc.Select(
                                        id="signals-filter-time",
                                        options=[
                                            {"label": "Last 24 hours / 最近24小時", "value": "24h"},
                                            {"label": "Last 7 days / 最近7天", "value": "7d"},
                                            {"label": "Last 30 days / 最近30天", "value": "30d"},
                                            {"label": "All time / 全部", "value": "all"},
                                        ],
                                        value="24h"
                                    )
                                ],
                                width=12,
                                md=4,
                                className="mb-3"
                            ),
                        ]
                    ),
                    dbc.Button(
                        "Apply Filters / 套用篩選",
                        id="signals-apply-filters",
                        color="primary",
                        className="mt-2"
                    )
                ]
            ),
            className="mb-4"
        ),
        
        # Signal list / 訊號列表
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        "Signal History / 訊號歷史",
                        dbc.Badge("Live", color="success", className="ms-2")
                    ]
                ),
                dbc.CardBody(
                    id="signals-list",
                    children=[
                        html.Div(
                            [
                                html.P("📡 Signal data connection pending", className="text-muted"),
                                html.P("(Implemented in Phase 4: Connect Monitoring Status)", className="text-muted small")
                            ],
                            className="text-center py-5"
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Real-time alert feed / 即時提醒串流
        dbc.Card(
            [
                dbc.CardHeader("Real-time Alert Feed / 即時提醒串流"),
                dbc.CardBody(
                    id="signals-alert-feed",
                    children=[
                        html.Div(
                            html.P("Waiting for alerts... / 等待提醒...", className="text-muted"),
                            className="text-center py-3"
                        )
                    ],
                    style={"maxHeight": "300px", "overflowY": "auto"}
                )
            ]
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="signals-interval",
            interval=30*1000,  # 30 seconds
            n_intervals=0
        ),
    ],
    fluid=True
)


# Callbacks / 回調

@callback(
    Output("signals-list", "children"),
    Input("signals-interval", "n_intervals"),
    Input("signals-apply-filters", "n_clicks")
)
def update_signals_list(n_intervals, n_clicks):
    """Update signal list display"""
    # Placeholder - will be implemented in Phase 4
    return html.Div(
        [
            html.P("Signal history table will be displayed here", className="text-muted"),
            html.P("Features: Sortable columns, pagination, detail view", className="text-muted small"),
            html.Hr(),
            html.Table(
                [
                    html.Thead(
                        html.Tr([
                            html.Th("Time / 時間"),
                            html.Th("Symbol / 標的"),
                            html.Th("Type / 類型"),
                            html.Th("Status / 狀態"),
                            html.Th("Actions / 操作")
                        ])
                    ),
                    html.Tbody(
                        html.Tr(
                            html.Td("No data / 無資料", colSpan=5, className="text-center text-muted"),
                            className="py-4"
                        )
                    )
                ],
                className="table table-striped"
            )
        ]
    )


@callback(
    Output("signals-alert-feed", "children"),
    Input("signals-interval", "n_intervals")
)
def update_alert_feed(n):
    """Update real-time alert feed"""
    # Placeholder - will be implemented in Phase 4
    return html.Div(
        [
            dbc.Alert(
                [
                    html.Strong("System Ready / 系統就緒"),
                    html.Br(),
                    "Waiting for new signals... / 等待新訊號..."
                ],
                color="info"
            )
        ]
    )
