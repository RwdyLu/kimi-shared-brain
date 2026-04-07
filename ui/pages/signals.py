"""
Signals Page / 訊號頁面

Signal history and alert viewing.
訊號歷史與提醒查看。
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
import sys

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Import monitor service / 匯入監測服務
from ui.services.monitor_service import get_recent_runs, get_today_signals

# Register page / 註冊頁面
dash.register_page(__name__, path="/signals", title="Signals")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Signals", className="mb-4"),
        html.P("Signal history and alert feed / 訊號歷史與提醒串流", className="text-muted"),
        
        html.Hr(),
        
        # Summary Cards / 摘要卡片
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3(id="signals-total-count", children="--"),
                                    html.P("Total Today / 今日總計", className="text-muted mb-0")
                                ]
                            )
                        ],
                        color="primary",
                        outline=True
                    ),
                    width=6,
                    md=4,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3(id="signals-confirmed-count", children="--"),
                                    html.P("Confirmed / 已確認", className="text-muted mb-0")
                                ]
                            )
                        ],
                        color="success",
                        outline=True
                    ),
                    width=6,
                    md=4,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3(id="signals-watch-count", children="--"),
                                    html.P("Watch Only / 僅觀察", className="text-muted mb-0")
                                ]
                            )
                        ],
                        color="info",
                        outline=True
                    ),
                    width=6,
                    md=4,
                    className="mb-3"
                ),
            ]
        ),
        
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
                        "Refresh / 刷新",
                        id="signals-refresh",
                        color="primary",
                        className="mt-2"
                    )
                ]
            ),
            className="mb-4"
        ),
        
        # Run History / 執行歷史
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Run History / 執行歷史", className="mb-0"),
                        html.Small("Recent monitoring runs with signal counts", className="text-muted")
                    ]
                ),
                dbc.CardBody(
                    id="signals-run-history",
                    children=[
                        html.P("Loading run history...", className="text-muted")
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Signal Alert Info / 訊號提醒資訊
        dbc.Card(
            [
                dbc.CardHeader("Signal Types / 訊號類型"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6("✅ Trend Long / 順勢做多"),
                                        html.P(
                                            "Confirmed execution-grade signal for long positions. "
                                            "Requires: price > MA240, MA5 crosses above MA20, volume spike.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("✅ Trend Short / 順勢做空"),
                                        html.P(
                                            "Confirmed execution-grade signal for short positions. "
                                            "Requires: price < MA240, MA5 crosses below MA20, volume spike.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("👁️ Contrarian Watch / 逆勢觀察"),
                                        html.P(
                                            "Watch-only signal for potential reversals. "
                                            "Not for execution - use for observation and analysis only.",
                                            className="text-muted small"
                                        ),
                                        dbc.Alert(
                                            "⚠️ WATCH ONLY - NOT FOR EXECUTION / 僅觀察 - 非執行訊號",
                                            color="warning",
                                            className="py-1 mt-2"
                                        )
                                    ],
                                    width=12,
                                    className="mb-3"
                                ),
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Alert-Only Notice / 僅提醒通知
        dbc.Alert(
            [
                html.H5("⚠️ Alert-Only System / 僅提醒系統", className="alert-heading"),
                html.P(
                    "This monitoring system generates ALERTS ONLY. No automatic trading is performed. "
                    "All trading decisions require manual confirmation.",
                    className="mb-0"
                ),
                html.Hr(),
                html.P(
                    "本監測系統僅產生提醒，不執行自動交易。所有交易決策需人工確認。",
                    className="mb-0 small"
                )
            ],
            color="warning",
            className="mb-4"
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
    Output("signals-total-count", "children"),
    Output("signals-confirmed-count", "children"),
    Output("signals-watch-count", "children"),
    Output("signals-run-history", "children"),
    Input("signals-interval", "n_intervals"),
    Input("signals-refresh", "n_clicks")
)
def update_signals_page(n_intervals, n_clicks):
    """Update signals page with real data"""
    try:
        # Get today's signals
        today = get_today_signals()
        total = today.get("total", 0)
        confirmed = today.get("confirmed", 0)
        watch = today.get("watch_only", 0)
        
        # Get recent runs
        runs = get_recent_runs(10)
        
        # Build run history table
        if runs:
            rows = []
            for run in runs:
                run_id = run.get("run_id", "--")
                timestamp = run.get("timestamp", "--")
                signals = run.get("signals", 0)
                confirmed_count = run.get("confirmed", 0)
                watch_count = run.get("watch_only", 0)
                
                # Format signal display
                if signals > 0:
                    signal_text = f"{signals} total"
                    signal_detail = f"({confirmed_count}✓, {watch_count}👁️)"
                    badge_color = "success" if confirmed_count > 0 else "info"
                else:
                    signal_text = "No signals"
                    signal_detail = ""
                    badge_color = "secondary"
                
                rows.append(
                    html.Tr([
                        html.Td(f"#{run_id}"),
                        html.Td(timestamp),
                        html.Td(
                            [
                                dbc.Badge(signal_text, color=badge_color, className="me-1"),
                                html.Small(signal_detail, className="text-muted") if signal_detail else None
                            ]
                        ),
                    ])
                )
            
            run_history = dbc.Table(
                [
                    html.Thead(
                        html.Tr([
                            html.Th("Run / 執行"),
                            html.Th("Time / 時間"),
                            html.Th("Signals / 訊號"),
                        ])
                    ),
                    html.Tbody(rows)
                ],
                bordered=True,
                hover=True,
                size="sm"
            )
        else:
            run_history = html.P("No run history available", className="text-muted text-center py-3")
        
        return str(total), str(confirmed), str(watch), run_history
        
    except Exception as e:
        return "--", "--", "--", dbc.Alert(f"Error loading data: {e}", color="danger")
