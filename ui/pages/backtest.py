"""
Backtest Page / 回測頁面

Run backtests and view detailed results with performance metrics and charts.
執行回測並查看包含績效指標和圖表的詳細結果。

⚠️  ANALYSIS ONLY / 僅分析用途
⚠️  Past performance does not guarantee future results

Author: kimiclaw_bot
Version: 2.0.0
Date: 2026-04-18
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

from backtest import BacktestStorage, BacktestConfig
from backtest.runner import BacktestRunner, run_backtest

# Register page / 註冊頁面
dash.register_page(__name__, path="/backtest", title="Backtest")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Backtest / 回測", className="mb-4"),
        html.P("Run backtests and view results / 執行回測並查看結果", className="text-muted"),
        
        html.Hr(),
        
        # T-072: Run Backtest Section / 執行回測區塊
        dbc.Card(
            [
                dbc.CardHeader("Run Backtest / 執行回測", className="fw-bold"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                # Symbol Dropdown / 標的下拉選單
                                dbc.Col(
                                    [
                                        html.Label("Symbol / 標的", className="fw-bold"),
                                        dbc.Select(
                                            id="backtest-symbol",
                                            options=[
                                                {"label": "BTCUSDT", "value": "BTCUSDT"},
                                                {"label": "ETHUSDT", "value": "ETHUSDT"},
                                                {"label": "BTCUSDT + ETHUSDT", "value": "BOTH"},
                                            ],
                                            value="BTCUSDT",
                                            placeholder="Select symbol..."
                                        )
                                    ],
                                    width=12,
                                    md=3,
                                    className="mb-3"
                                ),
                                
                                # Stop Loss Input / 止損輸入
                                dbc.Col(
                                    [
                                        html.Label("Stop Loss % / 止損 %", className="fw-bold"),
                                        dbc.Input(
                                            id="backtest-stoploss",
                                            type="number",
                                            value=2.0,
                                            min=0.1,
                                            max=50.0,
                                            step=0.1,
                                            placeholder="2.0"
                                        )
                                    ],
                                    width=12,
                                    md=3,
                                    className="mb-3"
                                ),
                                
                                # Take Profit Input / 止盈輸入
                                dbc.Col(
                                    [
                                        html.Label("Take Profit % / 止盈 %", className="fw-bold"),
                                        dbc.Input(
                                            id="backtest-takeprofit",
                                            type="number",
                                            value=4.0,
                                            min=0.1,
                                            max=100.0,
                                            step=0.1,
                                            placeholder="4.0"
                                        )
                                    ],
                                    width=12,
                                    md=3,
                                    className="mb-3"
                                ),
                                
                                # Initial Capital Input / 本金輸入
                                dbc.Col(
                                    [
                                        html.Label("Initial Capital / 本金", className="fw-bold"),
                                        dbc.Input(
                                            id="backtest-capital",
                                            type="number",
                                            value=10000,
                                            min=1000,
                                            max=1000000,
                                            step=1000,
                                            placeholder="10000"
                                        )
                                    ],
                                    width=12,
                                    md=3,
                                    className="mb-3"
                                ),
                            ]
                        ),
                        
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        # Run Backtest Button / 執行回測按鈕
                                        dbc.Button(
                                            "🚀 Run Backtest / 執行回測",
                                            id="btn-run-backtest",
                                            color="primary",
                                            size="lg",
                                            className="me-2"
                                        ),
                                        
                                        # Status Message / 狀態訊息
                                        html.Span(
                                            id="backtest-status",
                                            children="",
                                            className="ms-3"
                                        )
                                    ],
                                    width=12,
                                    className="d-flex align-items-center"
                                )
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # T-072: Performance Metrics Cards / 績效指標卡片
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H6("Win Rate / 勝率", className="text-muted mb-2"),
                                    html.H3(id="perf-winrate", children="--", className="mb-0"),
                                    html.Small(id="perf-winrate-detail", children="--", className="text-muted")
                                ]
                            )
                        ],
                        color="info",
                        outline=True
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
                                    html.H6("Total Return / 總報酬", className="text-muted mb-2"),
                                    html.H3(id="perf-return", children="--", className="mb-0"),
                                    html.Small(id="perf-return-detail", children="--", className="text-muted")
                                ]
                            )
                        ],
                        color="success",
                        outline=True
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
                                    html.H6("Max Drawdown / 最大回撤", className="text-muted mb-2"),
                                    html.H3(id="perf-drawdown", children="--", className="text-danger mb-0"),
                                    html.Small(id="perf-drawdown-detail", children="--", className="text-muted")
                                ]
                            )
                        ],
                        color="danger",
                        outline=True
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
                                    html.H6("Total Trades / 總交易次數", className="text-muted mb-2"),
                                    html.H3(id="perf-trades", children="--", className="mb-0"),
                                    html.Small(id="perf-trades-detail", children="--", className="text-muted")
                                ]
                            )
                        ],
                        color="primary",
                        outline=True
                    ),
                    width=6,
                    md=3,
                    className="mb-3"
                ),
            ],
            className="mb-4"
        ),
        
        # T-072: Equity Curve Chart / 權益曲線圖表
        dbc.Card(
            [
                dbc.CardHeader("Equity Curve / 權益曲線", className="fw-bold"),
                dbc.CardBody(
                    [
                        dcc.Graph(
                            id="equity-chart",
                            figure={
                                "data": [],
                                "layout": {
                                    "title": "Run a backtest to see equity curve",
                                    "height": 500,
                                    "template": "plotly_white"
                                }
                            },
                            config={"displayModeBar": True}
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # T-072: Recent Trades Table / 最近交易表
        dbc.Card(
            [
                dbc.CardHeader("Recent Trades / 最近交易 (Last 20)", className="fw-bold"),
                dbc.CardBody(
                    [
                        dbc.Table(
                            [
                                html.Thead(
                                    html.Tr([
                                        html.Th("Symbol"),
                                        html.Th("Direction"),
                                        html.Th("Entry Price"),
                                        html.Th("Exit Price"),
                                        html.Th("P&L %"),
                                        html.Th("Result")
                                    ])
                                ),
                                html.Tbody(id="trades-table-body", children=[])
                            ],
                            bordered=True,
                            hover=True,
                            size="sm",
                            responsive=True
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Backtest History / 回測歷史
        dbc.Card(
            [
                dbc.CardHeader("Backtest History / 回測歷史", className="fw-bold"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.Label("Select Previous Backtest / 選擇歷史回測"),
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
                                        html.Label("Actions / 操作"),
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
        
        # Interval for auto-refresh / 自動更新間隔
        dcc.Interval(id="backtest-interval", interval=30000),
        
        # Store for backtest results / 儲存回測結果
        dcc.Store(id="last-backtest-result", data=None)
    ],
    fluid=True,
    className="py-4"
)


# T-072: Run Backtest Callback / 執行回測回調
@callback(
    Output("perf-winrate", "children"),
    Output("perf-winrate-detail", "children"),
    Output("perf-return", "children"),
    Output("perf-return-detail", "children"),
    Output("perf-drawdown", "children"),
    Output("perf-drawdown-detail", "children"),
    Output("perf-trades", "children"),
    Output("perf-trades-detail", "children"),
    Output("equity-chart", "figure"),
    Output("trades-table-body", "children"),
    Output("backtest-status", "children"),
    Output("backtest-status", "className"),
    Output("last-backtest-result", "data"),
    Input("btn-run-backtest", "n_clicks"),
    State("backtest-symbol", "value"),
    State("backtest-stoploss", "value"),
    State("backtest-takeprofit", "value"),
    State("backtest-capital", "value"),
    prevent_initial_call=True
)
def run_backtest_callback(n_clicks, symbol, stop_loss, take_profit, capital):
    """
    Run backtest when button is clicked / 當按下按鈕時執行回測
    """
    if not n_clicks:
        return ["--"] * 6 + [{}, [], "", "", None]
    
    try:
        # Show running status
        status_msg = "⏳ Running backtest... / 執行回測中..."
        
        # Determine symbols
        if symbol == "BOTH":
            symbols = ["BTCUSDT", "ETHUSDT"]
        else:
            symbols = [symbol]
        
        # Set date range (last 7 days for quick backtest)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Run backtest
        summary = run_backtest(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=float(capital) if capital else 10000.0,
            stop_loss_pct=float(stop_loss) if stop_loss else 2.0,
            take_profit_pct=float(take_profit) if take_profit else 4.0
        )
        
        # Build performance metrics
        win_rate = f"{summary.win_rate:.1f}%"
        win_rate_detail = f"{summary.winning_trades}W / {summary.losing_trades}L"
        
        return_pct_str = f"{summary.total_return_pct:+.2f}%"
        return_detail = f"${summary.total_return_pct/100 * capital:.2f}"
        
        drawdown_str = f"{summary.max_drawdown_pct:.2f}%"
        drawdown_detail = "Max DD"
        
        trades_str = str(summary.total_trades)
        trades_detail = "Total"
        
        # Build equity chart
        if summary.equity_curve and len(summary.equity_curve) > 0:
            timestamps = [point["timestamp"] for point in summary.equity_curve]
            equities = [point["equity"] for point in summary.equity_curve]
            
            # Calculate drawdown series
            peak = capital
            drawdowns = []
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = ((peak - eq) / peak) * 100
                drawdowns.append(dd)
            
            figure = {
                "data": [
                    {
                        "x": timestamps,
                        "y": equities,
                        "type": "scatter",
                        "mode": "lines",
                        "name": "Equity",
                        "line": {"color": "#2ecc71", "width": 2},
                        "fill": "tozeroy",
                        "fillcolor": "rgba(46, 204, 113, 0.1)"
                    },
                    {
                        "x": timestamps,
                        "y": drawdowns,
                        "type": "scatter",
                        "mode": "lines",
                        "name": "Drawdown %",
                        "yaxis": "y2",
                        "line": {"color": "#e74c3c", "width": 1.5}
                    }
                ],
                "layout": {
                    "title": f"Backtest: {', '.join(symbols)} | Return: {summary.total_return_pct:+.2f}%",
                    "height": 500,
                    "template": "plotly_white",
                    "yaxis": {"title": "Equity ($)", "side": "left"},
                    "yaxis2": {"title": "Drawdown (%)", "side": "right", "overlaying": "y"},
                    "hovermode": "x unified"
                }
            }
        else:
            figure = {
                "data": [],
                "layout": {
                    "title": "No equity data available",
                    "height": 500,
                    "template": "plotly_white"
                }
            }
        
        # Build trades table (last 20)
        storage = BacktestStorage()
        trades = storage.get_trades_for_backtest(summary.backtest_id)
        
        # Sort by exit time (most recent first) and take last 20
        trades_sorted = sorted(
            trades,
            key=lambda x: x.get("exit_time") or "",
            reverse=True
        )[:20]
        
        table_rows = []
        for trade in trades_sorted:
            pnl_pct = trade.get("pnl_pct", 0)
            pnl_color = "text-success" if pnl_pct >= 0 else "text-danger"
            result_badge = dbc.Badge(
                "WIN" if pnl_pct >= 0 else "LOSS",
                color="success" if pnl_pct >= 0 else "danger",
                className="me-1"
            )
            
            table_rows.append(html.Tr([
                html.Td(trade.get("symbol", "--")),
                html.Td(trade.get("direction", "--").upper()),
                html.Td(f"${trade.get('entry_price', 0):,.2f}"),
                html.Td(f"${trade.get('exit_price', 0):,.2f}"),
                html.Td(f"{pnl_pct:+.2f}%", className=pnl_color),
                html.Td(result_badge)
            ]))
        
        if not table_rows:
            table_rows = [html.Tr([html.Td("No trades executed", colSpan=6, className="text-center text-muted")])]
        
        # Success status
        status_msg = f"✅ Backtest complete! ID: {summary.backtest_id}"
        status_class = "ms-3 text-success"
        
        # Store result
        result_data = {
            "backtest_id": summary.backtest_id,
            "symbols": symbols,
            "win_rate": summary.win_rate,
            "total_return": summary.total_return_pct,
            "max_drawdown": summary.max_drawdown_pct,
            "total_trades": summary.total_trades
        }
        
        return (
            win_rate, win_rate_detail,
            return_pct_str, return_detail,
            drawdown_str, drawdown_detail,
            trades_str, trades_detail,
            figure, table_rows,
            status_msg, status_class,
            result_data
        )
        
    except Exception as e:
        error_msg = f"❌ Error: {str(e)[:50]}"
        return (
            "--", "Error", "--", "Error", "--", "Error", "--", "Error",
            {"data": [], "layout": {"title": f"Error: {str(e)[:50]}", "height": 500}},
            [html.Tr([html.Td(f"Error: {str(e)}", colSpan=6, className="text-danger")])],
            error_msg, "ms-3 text-danger",
            None
        )


# Callback to load backtest history / 載入回測歷史回調
@callback(
    Output("backtest-selector", "options"),
    Output("backtest-selector", "value"),
    Input("backtest-interval", "n_intervals"),
    Input("btn-refresh", "n_clicks"),
    Input("btn-latest", "n_clicks")
)
def load_backtest_history(n_intervals, refresh_clicks, latest_clicks):
    """Load backtest history into dropdown / 載入回測歷史到下拉選單"""
    try:
        storage = BacktestStorage()
        backtests = storage.get_latest_backtests(limit=20)
        
        options = []
        for bt in backtests:
            bt_id = bt.get("backtest_id", "unknown")
            symbols = ", ".join(bt.get("symbols", []))
            return_pct = bt.get("total_return_pct", 0)
            label = f"{bt_id} | {symbols} | {return_pct:+.2f}%"
            options.append({"label": label, "value": bt_id})
        
        # Default to latest if available
        default_value = options[0]["value"] if options else None
        
        return options, default_value
    except Exception:
        return [], None


# Callback to display selected backtest / 顯示選擇的回測回調
@callback(
    Output("perf-winrate", "children", allow_duplicate=True),
    Output("perf-winrate-detail", "children", allow_duplicate=True),
    Output("perf-return", "children", allow_duplicate=True),
    Output("perf-return-detail", "children", allow_duplicate=True),
    Output("perf-drawdown", "children", allow_duplicate=True),
    Output("perf-drawdown-detail", "children", allow_duplicate=True),
    Output("perf-trades", "children", allow_duplicate=True),
    Output("perf-trades-detail", "children", allow_duplicate=True),
    Output("equity-chart", "figure", allow_duplicate=True),
    Output("trades-table-body", "children", allow_duplicate=True),
    Output("backtest-status", "children", allow_duplicate=True),
    Output("backtest-status", "className", allow_duplicate=True),
    Input("backtest-selector", "value"),
    prevent_initial_call=True
)
def display_selected_backtest(backtest_id):
    """Display selected backtest from history / 顯示選擇的歷史回測"""
    if not backtest_id:
        return ["--"] * 6 + [{}, [], "", "", None]
    
    try:
        storage = BacktestStorage()
        
        # Find the backtest
        backtests = storage.get_latest_backtests(limit=50)
        selected = None
        for bt in backtests:
            if bt.get("backtest_id") == backtest_id:
                selected = bt
                break
        
        if not selected:
            return ["--"] * 6 + [{}, [], "Backtest not found", "text-warning"]
        
        # Extract metrics
        win_rate = f"{selected.get('win_rate', 0):.1f}%"
        win_rate_detail = f"{selected.get('winning_trades', 0)}W / {selected.get('losing_trades', 0)}L"
        
        return_pct = selected.get('total_return_pct', 0)
        return_str = f"{return_pct:+.2f}%"
        return_detail = "Historical"
        
        drawdown = selected.get('max_drawdown_pct', 0)
        drawdown_str = f"{drawdown:.2f}%"
        drawdown_detail = "Max DD"
        
        total_trades = selected.get('total_trades', 0)
        trades_str = str(total_trades)
        trades_detail = "Total"
        
        # Build equity chart from stored curve
        equity_curve = selected.get('equity_curve', [])
        if equity_curve and len(equity_curve) > 0:
            timestamps = [point.get("timestamp", "") for point in equity_curve]
            equities = [point.get("equity", 0) for point in equity_curve]
            
            figure = {
                "data": [
                    {
                        "x": timestamps,
                        "y": equities,
                        "type": "scatter",
                        "mode": "lines",
                        "name": "Equity",
                        "line": {"color": "#2ecc71", "width": 2},
                        "fill": "tozeroy",
                        "fillcolor": "rgba(46, 204, 113, 0.1)"
                    }
                ],
                "layout": {
                    "title": f"Historical: {backtest_id} | Return: {return_pct:+.2f}%",
                    "height": 500,
                    "template": "plotly_white"
                }
            }
        else:
            figure = {
                "data": [],
                "layout": {
                    "title": "No equity curve data available",
                    "height": 500,
                    "template": "plotly_white"
                }
            }
        
        # Build trades table
        trades = storage.get_trades_for_backtest(backtest_id)
        trades_sorted = sorted(trades, key=lambda x: x.get("exit_time") or "", reverse=True)[:20]
        
        table_rows = []
        for trade in trades_sorted:
            pnl_pct = trade.get("pnl_pct", 0)
            pnl_color = "text-success" if pnl_pct >= 0 else "text-danger"
            result_badge = dbc.Badge(
                "WIN" if pnl_pct >= 0 else "LOSS",
                color="success" if pnl_pct >= 0 else "danger"
            )
            
            table_rows.append(html.Tr([
                html.Td(trade.get("symbol", "--")),
                html.Td(trade.get("direction", "--").upper()),
                html.Td(f"${trade.get('entry_price', 0):,.2f}"),
                html.Td(f"${trade.get('exit_price', 0):,.2f}"),
                html.Td(f"{pnl_pct:+.2f}%", className=pnl_color),
                html.Td(result_badge)
            ]))
        
        if not table_rows:
            table_rows = [html.Tr([html.Td("No trades found", colSpan=6, className="text-center text-muted")])]
        
        status_msg = f"📊 Loaded: {backtest_id}"
        status_class = "ms-3 text-info"
        
        return (
            win_rate, win_rate_detail,
            return_str, return_detail,
            drawdown_str, drawdown_detail,
            trades_str, trades_detail,
            figure, table_rows,
            status_msg, status_class
        )
        
    except Exception as e:
        return (
            "--", "Error", "--", "Error", "--", "Error", "--", "Error",
            {"data": [], "layout": {"title": f"Error: {str(e)[:50]}", "height": 500}},
            [html.Tr([html.Td(f"Error: {str(e)}", colSpan=6, className="text-danger")])],
            f"Error: {str(e)[:30]}", "ms-3 text-danger"
        )
