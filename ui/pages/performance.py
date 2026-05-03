"""
Performance Page — Per-Strategy Performance / 策略獨立績效頁面

Strategy performance overview with:
- Overall paper trading equity summary
- Per-strategy performance bar chart
- Recent trade history

URL: /performance
Title: 策略績效總覽 / Strategy Performance

Author: kimiclaw_bot
Version: 2.1.0
Date: 2026-05-03
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
from datetime import datetime
import json
import sys
from pathlib import Path
from typing import Dict, List

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Register page / 註冊頁面
dash.register_page(__name__, path="/performance", title="Performance")

# ─── Load strategy display names / 載入策略顯示名稱 ───
_DISPLAY_NAMES = None

def _load_display_names():
    global _DISPLAY_NAMES
    if _DISPLAY_NAMES is not None:
        return _DISPLAY_NAMES
    try:
        strategies_file = project_root / "config" / "strategies.json"
        with open(strategies_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _DISPLAY_NAMES = {
            s["id"]: s.get("name", s["id"])
            for s in data.get("strategies", [])
        }
    except Exception:
        _DISPLAY_NAMES = {}
    return _DISPLAY_NAMES

def get_strategy_display_name(strategy_id: str) -> str:
    names = _load_display_names()
    return names.get(strategy_id, strategy_id)

# ─── Data loading helpers / 資料載入輔助 ───
STATE_FILE = project_root / "state" / "paper_trading_state.json"

def load_paper_state() -> dict:
    """Load paper trading state from disk / 從磁碟載入模擬交易狀態"""
    try:
        if not STATE_FILE.exists():
            return {}
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def aggregate_all_trades(state: dict) -> List[dict]:
    """Aggregate completed trades from all strategy accounts / 聚合所有策略的已平倉交易"""
    all_trades = []
    strategies = state.get("strategies", {})
    for sid, acc in strategies.items():
        for t in acc.get("trades", []):
            if t.get("exit_price") is not None:
                t["_strategy_id"] = sid
                all_trades.append(t)
    return all_trades


def calculate_overall_metrics(state: dict) -> dict:
    """Calculate overall metrics from per-strategy state / 從策略獨立狀態計算整體指標"""
    strategies = state.get("strategies", {})
    total_initial = state.get("total_initial", 0)
    total_balance = sum(acc.get("balance", 0) for acc in strategies.values())
    total_return_pct = ((total_balance - total_initial) / total_initial * 100) if total_initial else 0
    
    all_trades = aggregate_all_trades(state)
    total_trades = len(all_trades)
    wins = sum(1 for t in all_trades if t.get("realized_pnl", 0) > 0)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "initial_balance": total_initial,
        "current_balance": total_balance,
        "total_return_pct": total_return_pct,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "all_trades": all_trades,
    }


def build_strategy_stats(state: dict) -> Dict[str, dict]:
    """Build per-strategy statistics / 建立各策略統計"""
    strategies = state.get("strategies", {})
    stats = {}
    for sid, acc in strategies.items():
        trades = [t for t in acc.get("trades", []) if t.get("exit_price") is not None]
        wins = [t for t in trades if t.get("realized_pnl", 0) > 0]
        losses = [t for t in trades if t.get("realized_pnl", 0) <= 0]
        
        win_pnls = [t.get("realized_pnl", 0) for t in wins]
        loss_pnls = [abs(t.get("realized_pnl", 0)) for t in losses]
        
        stats[sid] = {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": sum(t.get("realized_pnl", 0) for t in trades),
            "win_pnls": win_pnls,
            "loss_pnls": loss_pnls,
            "balance": acc.get("balance", 0),
            "initial": acc.get("initial", 1000),
        }
    return stats


# ─── Page layout / 頁面佈局 ───
layout = dbc.Container(
    [
        # Header / 標題
        dbc.Row([
            dbc.Col([
                html.H2("📈 Performance / 績效總覽", className="mb-3"),
                html.P("Strategy performance overview and trade history / 策略績效總覽與交易歷史", className="text-muted"),
            ], width=12)
        ]),
        
        # Top info line / 頂部說明文字
        dbc.Row([
            dbc.Col([
                html.P(id="perf-info-line", className="text-muted fst-italic")
            ], width=12)
        ]),
        
        html.Hr(),
        
        # ─── Section 1: Overall Performance / 整體績效 ───
        dbc.Card(
            [
                dbc.CardHeader("Overall Performance / 整體績效", className="fw-bold"),
                dbc.CardBody(
                    [
                        # KPI cards / 關鍵指標卡片
                        dbc.Row(
                            [
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([
                                            html.H6("Total Initial / 起始總額", className="text-muted"),
                                            html.H4(id="perf-initial-balance", children="$--")
                                        ]),
                                        color="light",
                                        className="mb-3"
                                    ),
                                    width=6, md=3
                                ),
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([
                                            html.H6("Current Balance / 當前總餘額", className="text-muted"),
                                            html.H4(id="perf-current-balance", children="$--")
                                        ]),
                                        color="light",
                                        className="mb-3"
                                    ),
                                    width=6, md=3
                                ),
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([
                                            html.H6("Total Return / 總報酬", className="text-muted"),
                                            html.H4(id="perf-total-return", children="--%")
                                        ]),
                                        color="light",
                                        className="mb-3"
                                    ),
                                    width=6, md=3
                                ),
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody([
                                            html.H6("Win Rate / 勝率", className="text-muted"),
                                            html.H4(id="perf-win-rate", children="--%")
                                        ]),
                                        color="light",
                                        className="mb-3"
                                    ),
                                    width=6, md=3
                                ),
                            ],
                            className="mb-3"
                        ),
                        
                        # Equity placeholder / 資金曲線（暫時顯示總結文字）
                        dbc.Alert(
                            [
                                html.H5("📊 Equity tracking per-strategy", className="alert-heading"),
                                html.P("Total equity is now tracked per individual strategy account. See per-strategy breakdown below."),
                            ],
                            color="info",
                            className="mb-3"
                        ),
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # ─── Section 2: Per-Strategy Performance / 各策略績效 ───
        dbc.Card(
            [
                dbc.CardHeader("Per-Strategy Performance / 各策略績效", className="fw-bold"),
                dbc.CardBody(
                    [
                        dcc.Graph(
                            id="perf-strategy-chart",
                            figure={
                                "data": [],
                                "layout": {
                                    "title": "Strategy PnL / 策略總損益",
                                    "height": 350,
                                    "template": "plotly_white"
                                }
                            },
                            config={"displayModeBar": False},
                            style={"height": "350px", "minHeight": "350px"}
                        ),
                        html.Hr(),
                        dbc.Table(
                            [
                                html.Thead(
                                    html.Tr([
                                        html.Th("Strategy / 策略"),
                                        html.Th("Trades / 交易", className="text-center"),
                                        html.Th("Win Rate / 勝率", className="text-center"),
                                        html.Th("Avg Win / 平均盈利", className="text-center"),
                                        html.Th("Avg Loss / 平均虧損", className="text-center"),
                                        html.Th("Profit Factor / 盈虧比", className="text-center"),
                                        html.Th("Balance / 餘額", className="text-center"),
                                        html.Th("Return% / 報酬率", className="text-center"),
                                    ])
                                ),
                                html.Tbody(id="perf-strategy-table-body", children=[])
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
        
        # ─── Section 3: Recent Trades / 最近交易記錄 ───
        dbc.Card(
            [
                dbc.CardHeader("Recent Trades / 最近交易 (Last 20)", className="fw-bold"),
                dbc.CardBody(
                    [
                        dbc.Table(
                            [
                                html.Thead(
                                    html.Tr([
                                        html.Th("Time / 時間"),
                                        html.Th("Symbol / 幣種"),
                                        html.Th("Strategy / 策略"),
                                        html.Th("Direction / 方向"),
                                        html.Th("Entry / 進場價", className="text-end"),
                                        html.Th("Exit / 出場價", className="text-end"),
                                        html.Th("PnL% / 損益%", className="text-end"),
                                        html.Th("Result / 結果", className="text-center"),
                                    ])
                                ),
                                html.Tbody(id="perf-trades-table-body", children=[])
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
        
        # Auto-refresh interval / 自動刷新間隔
        dcc.Interval(
            id="perf-interval",
            interval=30 * 1000,  # 30 seconds
            n_intervals=0
        ),
    ],
    fluid=True,
    className="dbc"
)

# ─── Callback: Load and render performance data / 回調：載入並渲染績效資料 ───
@callback(
    Output("perf-info-line", "children"),
    Output("perf-initial-balance", "children"),
    Output("perf-current-balance", "children"),
    Output("perf-total-return", "children"),
    Output("perf-win-rate", "children"),
    Output("perf-strategy-chart", "figure"),
    Output("perf-strategy-table-body", "children"),
    Output("perf-trades-table-body", "children"),
    Input("perf-interval", "n_intervals"),
)
def update_performance(n):
    """Load paper trading state and render all sections / 載入模擬交易狀態並渲染所有區塊"""
    state = load_paper_state()
    
    # Detect old format / 偵測舊格式
    if not state or "strategies" not in state:
        empty_fig = {
            "data": [],
            "layout": {
                "title": "No per-strategy data / 暫無策略資料（可能需要重設）",
                "height": 350,
                "template": "plotly_white"
            }
        }
        return (
            "Paper Trading 尚未開始或為舊格式 / Not started or old format",
            "$--", "$--", "--%", "--%",
            empty_fig,
            [html.Tr([html.Td("No data / 暫無資料", colSpan=8)])],
            [html.Tr([html.Td("No data / 暫無資料", colSpan=8)])]
        )
    
    # ─── Section 1: Overall KPIs / 整體關鍵指標 ───
    metrics = calculate_overall_metrics(state)
    
    initial_balance = metrics["initial_balance"]
    current_balance = metrics["current_balance"]
    total_return_pct = metrics["total_return_pct"]
    total_trades = metrics["total_trades"]
    win_rate = metrics["win_rate"]
    all_trades = metrics["all_trades"]
    
    # Info line / 頂部說明
    earliest_entry = None
    for t in all_trades:
        et = t.get("entry_time")
        if et:
            try:
                et_dt = datetime.fromisoformat(et.replace('Z', '+00:00'))
                if earliest_entry is None or et_dt < earliest_entry:
                    earliest_entry = et_dt
            except Exception:
                pass
    
    if earliest_entry:
        now = datetime.now()
        runtime = now - earliest_entry
        days = runtime.days
        hours = runtime.seconds // 3600
        info_line = (
            f"Paper Trading 開始於 {earliest_entry.strftime('%Y-%m-%d %H:%M')}，"
            f"已運行 {days} 天 {hours} 小時，共 {total_trades} 筆交易"
        )
    else:
        info_line = f"Paper Trading 進行中，共 {total_trades} 筆交易"
    
    # ─── Section 2: Per-Strategy Performance / 各策略績效 ───
    strategy_stats = build_strategy_stats(state)
    
    # Build bar chart data / 橫條圖資料
    sorted_strategies = sorted(
        strategy_stats.items(),
        key=lambda x: x[1]["total_pnl"],
        reverse=True
    )
    
    strategy_names = [get_strategy_display_name(sid) for sid, _ in sorted_strategies]
    strategy_pnls = [s["total_pnl"] for _, s in sorted_strategies]
    bar_colors = ["#28a745" if pnl >= 0 else "#dc3545" for pnl in strategy_pnls]
    
    strategy_chart = {
        "data": [
            {
                "y": strategy_names,
                "x": strategy_pnls,
                "type": "bar",
                "orientation": "h",
                "marker": {"color": bar_colors},
                "text": [f"${pnl:+.2f}" for pnl in strategy_pnls],
                "textposition": "outside",
                "name": "Total PnL"
            }
        ],
        "layout": {
            "title": "Strategy PnL / 策略總損益（正綠負紅）",
            "xaxis": {
                "title": "Total PnL ($)",
                "tickprefix": "$",
                "zeroline": True,
                "zerolinecolor": "#888",
                "zerolinewidth": 2
            },
            "yaxis": {"title": ""},
            "template": "plotly_white",
            "height": max(350, len(strategy_names) * 35 + 80),
            "margin": {"l": 180, "r": 80, "t": 50, "b": 50},
            "showlegend": False
        }
    }
    
    if not strategy_names:
        strategy_chart = {
            "data": [],
            "layout": {
                "title": "No strategy data / 暫無策略資料",
                "height": 350,
                "template": "plotly_white"
            }
        }
    
    # Strategy table rows / 策略表格行
    strategy_rows = []
    for sid, s in sorted_strategies:
        win_rate_s = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
        avg_win = sum(s["win_pnls"]) / len(s["win_pnls"]) if s["win_pnls"] else 0
        avg_loss = sum(s["loss_pnls"]) / len(s["loss_pnls"]) if s["loss_pnls"] else 0
        profit_factor = (sum(s["win_pnls"]) / sum(s["loss_pnls"])) if s["loss_pnls"] else float('inf') if s["win_pnls"] else 0
        
        return_pct = ((s["balance"] - s["initial"]) / s["initial"] * 100) if s["initial"] else 0
        
        pnl_color = "text-success" if s["total_pnl"] >= 0 else "text-danger"
        winrate_color = "text-success" if win_rate_s >= 50 else "text-warning" if win_rate_s >= 30 else "text-danger"
        return_color = "text-success" if return_pct >= 0 else "text-danger"
        
        strategy_rows.append(html.Tr([
            html.Td(get_strategy_display_name(sid), className="fw-bold"),
            html.Td(f"{s['trades']}", className="text-center"),
            html.Td(f"{win_rate_s:.1f}%", className=f"text-center {winrate_color}"),
            html.Td(f"+{avg_win:.2f}" if avg_win else "--", className="text-center text-success"),
            html.Td(f"-{avg_loss:.2f}" if avg_loss else "--", className="text-center text-danger"),
            html.Td(f"{profit_factor:.2f}" if profit_factor != float('inf') else "∞", className="text-center"),
            html.Td(f"${s['balance']:,.0f}", className="text-center"),
            html.Td(f"{return_pct:+.1f}%", className=f"text-center {return_color}"),
        ]))
    
    if not strategy_rows:
        strategy_rows = [html.Tr([html.Td("No completed trades / 暫無完成交易", colSpan=8)])]
    
    # ─── Section 3: Recent Trades / 最近交易 ───
    recent = sorted(
        all_trades,
        key=lambda t: t.get("exit_time", "") or "",
        reverse=True
    )[:20]
    
    trade_rows = []
    for t in recent:
        pnl = t.get("realized_pnl", 0)
        entry_price = t.get("entry_price", 0)
        exit_price = t.get("exit_price", 0)
        pnl_pct = ((pnl / (entry_price * t.get("quantity", 1))) * 100) if entry_price and t.get("quantity") else 0
        
        pnl_color = "text-success" if pnl >= 0 else "text-danger"
        result_badge = dbc.Badge("WIN", color="success", className="ms-1") if pnl > 0 else \
                       dbc.Badge("LOSS", color="danger", className="ms-1") if pnl < 0 else \
                       dbc.Badge("BREAKEVEN", color="secondary", className="ms-1")
        
        side = t.get("side", "--").upper()
        side_color = "text-success" if side == "BUY" else "text-danger" if side == "SELL" else "text-muted"
        sid = t.get("_strategy_id", t.get("strategy_id", "Unknown"))
        
        trade_rows.append(html.Tr([
            html.Td(t.get("exit_time", "--")[:19] if t.get("exit_time") else "--"),
            html.Td(t.get("symbol", "--")),
            html.Td(get_strategy_display_name(sid)),
            html.Td(side, className=f"fw-bold {side_color}"),
            html.Td(f"${entry_price:,.2f}" if entry_price else "--", className="text-end"),
            html.Td(f"${exit_price:,.2f}" if exit_price else "--", className="text-end"),
            html.Td(f"{pnl_pct:+.2f}%", className=f"text-end {pnl_color}"),
            html.Td(result_badge, className="text-center"),
        ]))
    
    if not trade_rows:
        trade_rows = [html.Tr([html.Td("No completed trades / 暫無完成交易", colSpan=8)])]
    
    # ─── Return all outputs / 回傳所有輸出 ───
    return (
        info_line,
        f"${initial_balance:,.2f}",
        f"${current_balance:,.2f}",
        html.Span(
            f"{total_return_pct:+.2f}%",
            className="text-success" if total_return_pct >= 0 else "text-danger"
        ),
        html.Span(
            f"{win_rate:.1f}%",
            className="text-success" if win_rate >= 50 else "text-warning" if win_rate >= 30 else "text-danger"
        ),
        strategy_chart,
        strategy_rows,
        trade_rows,
    )
