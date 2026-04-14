"""
Backtest Report Page / 回測報告頁面

Detailed backtest results, trade history, and performance analysis.
詳細的回測結果、交易歷史與績效分析。

⚠️  ANALYSIS ONLY / 僅分析用途
⚠️  Past performance does not guarantee future results

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-14
"""

import dash
from dash import dcc, html, callback, Output, Input, State
import dash_bootstrap_components as dbc
from datetime import datetime, timedelta
import json
import sys
from pathlib import Path

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from backtest import BacktestStorage

# Register page / 註冊頁面
dash.register_page(__name__, path="/backtest", title="Backtest Report")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Backtest Report / 回測報告", className="mb-4"),
        html.P("Historical backtest results and analysis / 歷史回測結果與分析", className="text-muted"),
        
        html.Hr(),
        
        # Backtest Selector / 回測選擇器
        dbc.Card(
            [
                dbc.CardHeader("Select Backtest / 選擇回測"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.Label("Backtest / 回測"),
                                        dbc.Select(
                                            id="backtest-selector",
                                            options=[],
                                            placeholder="Select a backtest..."
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.Label("Quick Select / 快速選擇"),
                                        dbc.ButtonGroup(
                                            [
                                                dbc.Button("Latest / 最新", id="btn-latest", color="primary", size="sm"),
                                                dbc.Button("Refresh / 刷新", id="btn-refresh", color="secondary", size="sm"),
                                            ]
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                )
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Summary Cards / 摘要卡片
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Period / 期間", className="text-muted"),
                                    html.H4(id="bt-period", children="--"),
                                    html.Small(id="bt-duration", children="--", className="text-muted")
                                ]
                            )
                        ]
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Total Return / 總報酬", className="text-muted"),
                                    html.H4(id="bt-return", children="--")
                                ]
                            )
                        ],
                        id="bt-return-card"
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Win Rate / 勝率", className="text-muted"),
                                    html.H4(id="bt-winrate", children="--")
                                ]
                            )
                        ]
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H5("Max Drawdown / 最大回撤", className="text-muted"),
                                    html.H4(id="bt-drawdown", children="--", className="text-danger")
                                ]
                            )
                        ]
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
            ]
        ),
        
        # Trade Statistics / 交易統計
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Trade Statistics / 交易統計"),
                            dbc.CardBody(
                                [
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    html.H6("Total Trades / 總交易數"),
                                                    html.H3(id="bt-total-trades", children="--")
                                                ],
                                                width=6,
                                                md=3,
                                                className="mb-3"
                                            ),
                                            dbc.Col(
                                                [
                                                    html.H6("Winning / 盈利"),
                                                    html.H3(id="bt-winning", children="--", className="text-success")
                                                ],
                                                width=6,
                                                md=3,
                                                className="mb-3"
                                            ),
                                            dbc.Col(
                                                [
                                                    html.H6("Losing / 虧損"),
                                                    html.H3(id="bt-losing", children="--", className="text-danger")
                                                ],
                                                width=6,
                                                md=3,
                                                className="mb-3"
                                            ),
                                            dbc.Col(
                                                [
                                                    html.H6("Symbols / 標的"),
                                                    html.H3(id="bt-symbols-count", children="--")
                                                ],
                                                width=6,
                                                md=3,
                                                className="mb-3"
                                            ),
                                        ]
                                    )
                                ]
                            )
                        ]
                    ),
                    width=12,
                    className="mb-4"
                )
            ]
        ),
        
        # Symbol Breakdown / 標的明細
        dbc.Card(
            [
                dbc.CardHeader("Symbol Breakdown / 標的明細"),
                dbc.CardBody(
                    id="bt-symbol-breakdown",
                    children=[html.P("Select a backtest to view details", className="text-muted")]
                )
            ],
            className="mb-4"
        ),
        
        # Trade History / 交易歷史
        dbc.Card(
            [
                dbc.CardHeader("Trade History / 交易歷史"),
                dbc.CardBody(
                    id="bt-trade-history",
                    children=[html.P("Select a backtest to view trades", className="text-muted")]
                )
            ],
            className="mb-4"
        ),
        
        # Export Button / 匯出按鈕
        dbc.Row(
            [
                dbc.Col(
                    dbc.Button(
                        "Export to JSON / 匯出為 JSON",
                        id="btn-export",
                        color="success",
                        className="me-2"
                    ),
                    width="auto"
                ),
                dbc.Col(
                    dcc.Download(id="download-backtest"),
                    width="auto"
                )
            ],
            className="mb-4"
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="backtest-interval",
            interval=30*1000,  # 30 seconds
            n_intervals=0
        ),
        
        # Store for selected backtest / 儲存選中的回測
        dcc.Store(id="selected-backtest-data")
    ],
    fluid=True
)


# Callbacks / 回調

@callback(
    Output("backtest-selector", "options"),
    Output("backtest-selector", "value"),
    Input("backtest-interval", "n_intervals"),
    Input("btn-refresh", "n_clicks"),
    State("backtest-selector", "value")
)
def update_backtest_list(n_intervals, n_clicks, current_value):
    """Update backtest dropdown list / 更新回測下拉選單"""
    try:
        storage = BacktestStorage()
        backtests = storage.get_latest_backtests(limit=20)
        
        if not backtests:
            return [], None
        
        # Build options
        options = []
        for bt in backtests:
            bt_id = bt.get("backtest_id", "Unknown")
            start = bt.get("start_date", "--")
            end = bt.get("end_date", "--")
            return_pct = bt.get("total_return_pct", 0)
            
            label = f"{bt_id} ({start}~{end}) [{return_pct:+.1f}%]"
            options.append({"label": label, "value": bt_id})
        
        # Keep current selection if still valid, else select latest
        if current_value and any(o["value"] == current_value for o in options):
            return options, current_value
        else:
            return options, options[0]["value"] if options else None
            
    except Exception as e:
        return [], None


@callback(
    Output("selected-backtest-data", "data"),
    Output("bt-period", "children"),
    Output("bt-duration", "children"),
    Output("bt-return", "children"),
    Output("bt-return", "className"),
    Output("bt-return-card", "color"),
    Output("bt-winrate", "children"),
    Output("bt-drawdown", "children"),
    Output("bt-total-trades", "children"),
    Output("bt-winning", "children"),
    Output("bt-losing", "children"),
    Output("bt-symbols-count", "children"),
    Output("bt-symbol-breakdown", "children"),
    Output("bt-trade-history", "children"),
    Input("backtest-selector", "value"),
    Input("btn-latest", "n_clicks"),
    Input("backtest-interval", "n_intervals")
)
def update_backtest_details(selected_id, latest_clicks, n_intervals):
    """Update all backtest detail displays / 更新所有回測詳情顯示"""
    ctx = dash.callback_context
    
    # If triggered by btn-latest, get the latest backtest
    if ctx.triggered and "btn-latest" in ctx.triggered[0]["prop_id"]:
        try:
            storage = BacktestStorage()
            backtests = storage.get_latest_backtests(limit=1)
            if backtests:
                selected_id = backtests[0].get("backtest_id")
        except:
            pass
    
    if not selected_id:
        empty_outputs = (
            {}, "--", "--", "--", "", None, "--", "--", "--", "--", "--", "--",
            html.P("No backtest selected", className="text-muted"),
            html.P("No backtest selected", className="text-muted")
        )
        return empty_outputs
    
    try:
        storage = BacktestStorage()
        
        # Find the selected backtest
        backtests = storage.get_latest_backtests(limit=50)
        bt = next((b for b in backtests if b.get("backtest_id") == selected_id), None)
        
        if not bt:
            empty_outputs = (
                {}, "--", "--", "--", "", None, "--", "--", "--", "--", "--", "--",
                html.P("Backtest not found", className="text-muted"),
                html.P("Backtest not found", className="text-muted")
            )
            return empty_outputs
        
        # Period
        start = bt.get("start_date", "--")
        end = bt.get("end_date", "--")
        period = f"{start} ~ {end}"
        
        # Calculate duration
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            days = (end_dt - start_dt).days
            duration = f"{days} days / {days} 天"
        except:
            duration = "--"
        
        # Return
        return_pct = bt.get("total_return_pct", 0)
        return_text = f"{return_pct:+.2f}%"
        return_class = "text-success" if return_pct >= 0 else "text-danger"
        card_color = "success" if return_pct >= 0 else "danger"
        
        # Win rate
        win_rate = bt.get("win_rate", 0)
        winrate_text = f"{win_rate:.1f}%"
        
        # Drawdown
        drawdown = bt.get("max_drawdown_pct", 0)
        drawdown_text = f"{drawdown:.2f}%"
        
        # Trade counts
        total = bt.get("total_trades", 0)
        winning = bt.get("winning_trades", 0)
        losing = bt.get("losing_trades", 0)
        
        # Symbols
        symbols = bt.get("symbols", [])
        symbols_count = len(symbols)
        
        # Symbol breakdown
        symbol_stats = bt.get("symbol_stats", {})
        if symbol_stats:
            breakdown_rows = []
            for sym, stats in symbol_stats.items():
                sym_trades = stats.get("total_trades", 0)
                sym_pnl = stats.get("total_pnl_pct", 0)
                pnl_color = "success" if sym_pnl >= 0 else "danger"
                
                breakdown_rows.append(
                    dbc.Row(
                        [
                            dbc.Col(html.Strong(sym), width=4),
                            dbc.Col(f"{sym_trades} trades / {sym_trades} 筆", width=4),
                            dbc.Col(html.Span(f"{sym_pnl:+.2f}%", className=f"text-{pnl_color}"), width=4)
                        ],
                        className="mb-2 border-bottom pb-2"
                    )
                )
            symbol_breakdown = html.Div(breakdown_rows)
        else:
            symbol_breakdown = html.P("No symbol data available", className="text-muted")
        
        # Trade history
        trades = storage.get_trades_for_backtest(selected_id)
        if trades:
            trade_rows = []
            for t in sorted(trades, key=lambda x: x.get("entry_time", "")):
                direction = t.get("direction", "--")
                entry = t.get("entry_price", 0)
                exit_p = t.get("exit_price", 0)
                pnl = t.get("pnl_pct", 0)
                result = t.get("result", "--")
                symbol = t.get("symbol", "--")
                
                pnl_color = "success" if pnl >= 0 else "danger"
                result_badge = dbc.Badge(
                    "WIN" if result == "closed_profit" else "LOSS",
                    color="success" if result == "closed_profit" else "danger"
                )
                
                trade_rows.append(
                    dbc.Row(
                        [
                            dbc.Col(symbol, width=2),
                            dbc.Col(direction.upper(), width=2),
                            dbc.Col(f"${entry:,.2f}", width=2),
                            dbc.Col(f"${exit_p:,.2f}", width=2),
                            dbc.Col(html.Span(f"{pnl:+.2f}%", className=f"text-{pnl_color}"), width=2),
                            dbc.Col(result_badge, width=2)
                        ],
                        className="mb-2 border-bottom pb-2 align-items-center"
                    )
                )
            
            # Header row
            trade_header = dbc.Row(
                [
                    dbc.Col(html.Strong("Symbol"), width=2),
                    dbc.Col(html.Strong("Direction"), width=2),
                    dbc.Col(html.Strong("Entry"), width=2),
                    dbc.Col(html.Strong("Exit"), width=2),
                    dbc.Col(html.Strong("P&L"), width=2),
                    dbc.Col(html.Strong("Result"), width=2)
                ],
                className="mb-3 border-bottom pb-2"
            )
            
            trade_history = html.Div([trade_header] + trade_rows)
        else:
            trade_history = html.P("No trades recorded", className="text-muted")
        
        return (
            bt, period, duration, return_text, return_class, card_color,
            winrate_text, drawdown_text, str(total), str(winning), str(losing),
            str(symbols_count), symbol_breakdown, trade_history
        )
        
    except Exception as e:
        error_msg = html.P(f"Error loading backtest: {e}", className="text-danger")
        error_outputs = (
            {}, "--", "--", "--", "", None, "--", "--", "--", "--", "--", "--",
            error_msg, error_msg
        )
        return error_outputs


@callback(
    Output("download-backtest", "data"),
    Input("btn-export", "n_clicks"),
    State("selected-backtest-data", "data"),
    prevent_initial_call=True
)
def export_backtest(n_clicks, backtest_data):
    """Export backtest data to JSON / 匯出回測資料為 JSON"""
    if not backtest_data or not n_clicks:
        return None
    
    bt_id = backtest_data.get("backtest_id", "backtest")
    
    return dict(
        content=json.dumps(backtest_data, indent=2, default=str),
        filename=f"{bt_id}_report.json"
    )
