"""
Calendar Page — Per-Strategy Daily Settlement / 策略明細每日結算日曆

Shows daily trading settlement calendar with:
- Monthly calendar view with per-strategy PnL detail and daily total
- Day detail panel with per-strategy summary + trade list
- Monthly summary cards

URL: /calendar
Title: 每日結算 / Daily Settlement

Author: kimiclaw_bot
Version: 2.0.0
Date: 2026-05-03
"""

import dash
from dash import dcc, html, callback, Output, Input, State
import dash_bootstrap_components as dbc
from datetime import datetime, timedelta
import calendar
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Register page / 註冊頁面
dash.register_page(__name__, path="/calendar", title="Calendar")

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


def get_trades_by_date(state: dict, year: int, month: int) -> Dict[str, List[dict]]:
    """
    Group completed trades by date from per-strategy accounts.
    從各策略帳戶按日期分組已平倉交易。
    """
    by_date = {}
    strategies = state.get("strategies", {})
    
    for sid, acc in strategies.items():
        for t in acc.get("trades", []):
            if t.get("exit_price") is None:
                continue
            exit_time = t.get("exit_time", "")
            if not exit_time:
                continue
            try:
                dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                if dt.year == year and dt.month == month:
                    date_key = dt.strftime("%Y-%m-%d")
                    t["_strategy_id"] = sid  # Inject strategy_id for display
                    by_date.setdefault(date_key, []).append(t)
            except Exception:
                pass
    
    return by_date


def get_daily_settlement(state: dict, date_key: str) -> Dict[str, dict]:
    """
    Get daily settlement from state.daily_settlements.
    Returns {strategy_id: {realized_pnl, trades, balance_after}}.
    """
    settlements = state.get("daily_settlements", {})
    return settlements.get(date_key, {})


def get_daily_summary(trades: List[dict], settlement: Dict[str, dict]) -> dict:
    """
    Calculate daily summary with per-strategy breakdown.
    計算當日小結（含各策略明細）。
    """
    # Base from trades
    total_pnl = sum(t.get("realized_pnl", 0) for t in trades)
    wins = sum(1 for t in trades if t.get("realized_pnl", 0) > 0)
    count = len(trades)
    win_rate = (wins / count * 100) if count > 0 else 0
    
    # Per-strategy breakdown from settlement
    strategy_pnls = {}
    for sid, data in settlement.items():
        strategy_pnls[sid] = data.get("realized_pnl", 0)
    
    # Also aggregate from trades for strategies not in settlement
    for t in trades:
        sid = t.get("_strategy_id", t.get("strategy_id", "Unknown"))
        if sid not in strategy_pnls:
            strategy_pnls[sid] = strategy_pnls.get(sid, 0) + t.get("realized_pnl", 0)
    
    return {
        "count": count,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "strategy_pnls": strategy_pnls,
    }


# ─── Page layout / 頁面佈局 ───
layout = dbc.Container(
    [
        # Header / 標題
        dbc.Row([
            dbc.Col([
                html.H2("📅 Calendar / 每日結算", className="mb-3"),
                html.P("Daily trading settlement with per-strategy breakdown / 每日交易結算（含策略明細）", className="text-muted"),
            ], width=12)
        ]),
        
        html.Hr(),
        
        # ─── Section 1: Monthly Summary Cards / 月結算卡片 ───
        dbc.Card([
            dbc.CardHeader("Monthly Summary / 本月總結", className="fw-bold"),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H6("Total PnL / 總損益", className="text-muted"),
                                html.H4(id="cal-month-pnl", children="$--")
                            ]),
                            color="light",
                            className="mb-3"
                        ),
                        width=6, md=2
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H6("Trades / 交易次數", className="text-muted"),
                                html.H4(id="cal-month-trades", children="--")
                            ]),
                            color="light",
                            className="mb-3"
                        ),
                        width=6, md=2
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H6("Win Rate / 勝率", className="text-muted"),
                                html.H4(id="cal-month-winrate", children="--%")
                            ]),
                            color="light",
                            className="mb-3"
                        ),
                        width=6, md=2
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H6("Best Day / 最佳單日", className="text-muted"),
                                html.H4(id="cal-best-day", children="--")
                            ]),
                            color="light",
                            className="mb-3"
                        ),
                        width=6, md=3
                    ),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H6("Worst Day / 最差單日", className="text-muted"),
                                html.H4(id="cal-worst-day", children="--")
                            ]),
                            color="light",
                            className="mb-3"
                        ),
                        width=6, md=3
                    ),
                ]),
            ])
        ], className="mb-4"),
        
        # ─── Section 2: Calendar Navigation / 月曆導航 ───
        dbc.Row([
            dbc.Col(
                dbc.Button("← Prev Month", id="cal-prev-month", color="secondary", outline=True),
                width="auto"
            ),
            dbc.Col(
                html.H4(id="cal-month-label", className="text-center mb-0"),
                width=True
            ),
            dbc.Col(
                dbc.Button("Next Month →", id="cal-next-month", color="secondary", outline=True),
                width="auto"
            ),
        ], className="mb-3 align-items-center", justify="between"),
        
        # ─── Section 3: Calendar Grid / 月曆視圖 ───
        dbc.Card([
            dbc.CardBody([
                dbc.Table([
                    html.Thead(html.Tr([
                        html.Th("Sun", className="text-center"),
                        html.Th("Mon", className="text-center"),
                        html.Th("Tue", className="text-center"),
                        html.Th("Wed", className="text-center"),
                        html.Th("Thu", className="text-center"),
                        html.Th("Fri", className="text-center"),
                        html.Th("Sat", className="text-center"),
                    ])),
                    html.Tbody(id="cal-grid-body", children=[])
                ], bordered=True, hover=True, className="text-center")
            ])
        ], className="mb-4"),
        
        # ─── Section 4: Day Detail / 點擊日期明細 ───
        dbc.Card([
            dbc.CardHeader(id="cal-detail-header", children="Day Detail / 日期明細", className="fw-bold"),
            dbc.CardBody([
                # Per-strategy summary / 各策略小結
                html.Div(id="cal-detail-strategy-summary", children=[]),
                
                html.Hr(),
                
                # Trade list / 交易列表
                dbc.Table([
                    html.Thead(html.Tr([
                        html.Th("Time / 時間"),
                        html.Th("Symbol / 幣種"),
                        html.Th("Strategy / 策略"),
                        html.Th("Direction / 方向"),
                        html.Th("Entry / 進場價", className="text-end"),
                        html.Th("Exit / 出場價", className="text-end"),
                        html.Th("PnL% / 損益%", className="text-end"),
                        html.Th("PnL / 盈虧", className="text-end"),
                    ])),
                    html.Tbody(id="cal-detail-body", children=[])
                ], bordered=True, hover=True, size="sm", responsive=True),
                
                html.Hr(),
                
                dbc.Row([
                    dbc.Col([
                        html.P(id="cal-detail-summary", className="mb-0 fw-bold")
                    ], width=12)
                ])
            ])
        ], className="mb-4"),
        
        # Store selected date and current month / 儲存選中日期和當前月份
        dcc.Store(id="cal-selected-date", data=None),
        dcc.Store(id="cal-current-ym", data={"year": datetime.now().year, "month": datetime.now().month}),
        
        # Auto-refresh interval / 自動刷新間隔
        dcc.Interval(id="cal-interval", interval=30*1000, n_intervals=0),
    ],
    fluid=True,
    className="dbc"
)

# ─── Callback: Month navigation / 回調：月份導航 ───
@callback(
    Output("cal-current-ym", "data"),
    Input("cal-prev-month", "n_clicks"),
    Input("cal-next-month", "n_clicks"),
    Input("cal-interval", "n_intervals"),
    State("cal-current-ym", "data"),
)
def update_month(prev_clicks, next_clicks, n_intervals, current_ym):
    """Update current month based on button clicks / 根據按鈕點擊更新當前月份"""
    ctx = dash.callback_context
    if not ctx.triggered:
        return current_ym
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    year = current_ym.get("year", datetime.now().year)
    month = current_ym.get("month", datetime.now().month)
    
    if button_id == "cal-prev-month":
        month -= 1
        if month < 1:
            month = 12
            year -= 1
    elif button_id == "cal-next-month":
        month += 1
        if month > 12:
            month = 1
            year += 1
    
    return {"year": year, "month": month}

# ─── Callback: Render calendar grid / 回調：渲染月曆格子 ───
@callback(
    Output("cal-month-label", "children"),
    Output("cal-grid-body", "children"),
    Output("cal-month-pnl", "children"),
    Output("cal-month-trades", "children"),
    Output("cal-month-winrate", "children"),
    Output("cal-best-day", "children"),
    Output("cal-worst-day", "children"),
    Output("cal-detail-header", "children"),
    Output("cal-detail-strategy-summary", "children"),
    Output("cal-detail-body", "children"),
    Output("cal-detail-summary", "children"),
    Input("cal-current-ym", "data"),
    Input("cal-selected-date", "data"),
    Input("cal-interval", "n_intervals"),
)
def render_calendar(current_ym, selected_date, n_intervals):
    """Render calendar grid and summary / 渲染月曆格子和總結"""
    year = current_ym.get("year", datetime.now().year)
    month = current_ym.get("month", datetime.now().month)
    
    state = load_paper_state()
    trades_by_date = get_trades_by_date(state, year, month)
    
    # Monthly summary / 月結算
    month_total_pnl = 0
    month_total_trades = 0
    month_wins = 0
    best_day_pnl = float('-inf')
    worst_day_pnl = float('inf')
    best_day_str = "--"
    worst_day_str = "--"
    
    for date_key, day_trades in trades_by_date.items():
        settlement = get_daily_settlement(state, date_key)
        summary = get_daily_summary(day_trades, settlement)
        day_pnl = summary["total_pnl"]
        month_total_pnl += day_pnl
        month_total_trades += summary["count"]
        month_wins += sum(1 for t in day_trades if t.get("realized_pnl", 0) > 0)
        
        if day_pnl > best_day_pnl:
            best_day_pnl = day_pnl
            best_day_str = f"{date_key[5:]} (+${day_pnl:+.2f})"
        if day_pnl < worst_day_pnl:
            worst_day_pnl = day_pnl
            worst_day_str = f"{date_key[5:]} ({day_pnl:+.2f})"
    
    month_winrate = (month_wins / month_total_trades * 100) if month_total_trades > 0 else 0
    month_pnl_color = "text-success" if month_total_pnl >= 0 else "text-danger"
    
    # Build calendar grid / 構建月曆格子
    cal = calendar.Calendar()
    month_days = cal.monthdayscalendar(year, month)
    
    rows = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for week in month_days:
        cells = []
        for day in week:
            if day == 0:
                cells.append(html.Td("", className="bg-light"))
                continue
            
            date_key = f"{year}-{month:02d}-{day:02d}"
            day_trades = trades_by_date.get(date_key, [])
            settlement = get_daily_settlement(state, date_key)
            summary = get_daily_summary(day_trades, settlement)
            
            is_today = (date_key == today_str)
            border_class = "border border-primary border-2" if is_today else ""
            
            if day_trades or settlement:
                pnl = summary["total_pnl"]
                pnl_color = "text-success" if pnl >= 0 else "text-danger"
                pnl_str = f"${pnl:+.2f}"
                
                # Build per-strategy mini list / 各策略小字明細
                strategy_items = []
                for sid, spnl in sorted(summary["strategy_pnls"].items(), key=lambda x: abs(x[1]), reverse=True):
                    if abs(spnl) < 0.01:
                        continue
                    spnl_color = "text-success" if spnl >= 0 else "text-danger"
                    strategy_items.append(
                        html.Div(
                            f"{get_strategy_display_name(sid)[:8]}: {spnl:+.0f}",
                            className=f"{spnl_color} small lh-1"
                        )
                    )
                
                content = html.Div([
                    html.Div(day, className="fw-bold"),
                    html.Div(pnl_str, className=f"{pnl_color} fw-bold small"),
                    html.Div(f"{summary['count']} trades", className="text-muted small mb-1"),
                    html.Div(strategy_items, className="mt-1")
                ])
            else:
                content = html.Div([
                    html.Div(day, className="fw-bold text-muted"),
                    html.Div("-", className="text-muted small")
                ])
            
            cells.append(html.Td(
                content,
                id={"type": "cal-day", "date": date_key},
                className=f"p-2 {border_class}",
                style={"cursor": "pointer", "minHeight": "80px"},
                n_clicks=0
            ))
        
        rows.append(html.Tr(cells))
    
    # Detail panel / 明細面板
    if selected_date:
        detail_header = f"Day Detail / {selected_date} 交易明細"
        day_trades = trades_by_date.get(selected_date, [])
        settlement = get_daily_settlement(state, selected_date)
        summary = get_daily_summary(day_trades, settlement)
        
        # ─── Per-strategy summary cards / 各策略小結卡片 ───
        strategy_summary_cards = []
        if summary["strategy_pnls"]:
            strategy_summary_cards.append(html.H6("Strategy PnL / 策略損益明細", className="fw-bold mb-2"))
            card_row = []
            for sid, spnl in sorted(summary["strategy_pnls"].items(), key=lambda x: x[1], reverse=True):
                spnl_color = "success" if spnl >= 0 else "danger"
                card_row.append(
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                html.H6(get_strategy_display_name(sid), className="mb-1 small fw-bold"),
                                html.P(f"${spnl:+.2f}", className=f"text-{spnl_color} fw-bold mb-0")
                            ]),
                            color=spnl_color,
                            outline=True,
                            className="mb-2"
                        ),
                        width=6, md=3
                    )
                )
            strategy_summary_cards.append(dbc.Row(card_row))
        else:
            strategy_summary_cards = [html.P("No strategy data / 無策略資料", className="text-muted")]
        
        # ─── Trade list / 交易列表 ───
        detail_rows = []
        for t in day_trades:
            pnl = t.get("realized_pnl", 0)
            entry_price = t.get("entry_price", 0)
            exit_price = t.get("exit_price", 0)
            qty = t.get("quantity", 1)
            pnl_pct = ((pnl / (entry_price * qty)) * 100) if entry_price and qty else 0
            
            pnl_color = "text-success" if pnl >= 0 else "text-danger"
            side = t.get("side", "--").upper()
            side_color = "text-success" if side == "BUY" else "text-danger"
            sid = t.get("_strategy_id", t.get("strategy_id", "Unknown"))
            
            detail_rows.append(html.Tr([
                html.Td(t.get("exit_time", "--")[:19] if t.get("exit_time") else "--"),
                html.Td(t.get("symbol", "--")),
                html.Td(get_strategy_display_name(sid)),
                html.Td(side, className=f"fw-bold {side_color}"),
                html.Td(f"${entry_price:,.2f}" if entry_price else "--", className="text-end"),
                html.Td(f"${exit_price:,.2f}" if exit_price else "--", className="text-end"),
                html.Td(f"{pnl_pct:+.2f}%", className=f"text-end {pnl_color}"),
                html.Td(f"${pnl:+.2f}", className=f"text-end {pnl_color}"),
            ]))
        
        if not detail_rows:
            detail_rows = [html.Tr([html.Td("No trades / 無交易", colSpan=8)])]
        
        detail_summary = (
            f"當日小結：{summary['count']} 筆交易，勝率 {summary['win_rate']:.1f}%，"
            f"總盈虧 ${summary['total_pnl']:+.2f}"
        )
    else:
        detail_header = "Day Detail / 日期明細（點擊月曆日期查看）"
        strategy_summary_cards = [html.P("Select a date / 請選擇日期", className="text-muted")]
        detail_rows = [html.Tr([html.Td("Select a date / 請選擇日期", colSpan=8)])]
        detail_summary = ""
    
    return (
        f"{year}年 {month}月",
        rows,
        html.Span(f"${month_total_pnl:+.2f}", className=month_pnl_color),
        str(month_total_trades),
        f"{month_winrate:.1f}%",
        best_day_str,
        worst_day_str,
        detail_header,
        strategy_summary_cards,
        detail_rows,
        detail_summary,
    )

# ─── Callback: Handle date click / 回調：處理日期點擊 ───
@callback(
    Output("cal-selected-date", "data"),
    Input({"type": "cal-day", "date": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_date_click(n_clicks_list):
    """Handle calendar day cell clicks / 處理月曆日期點擊"""
    ctx = dash.callback_context
    if not ctx.triggered:
        return None
    
    triggered = ctx.triggered[0]
    prop_id = triggered["prop_id"]
    
    # Extract date from prop_id like {"type":"cal-day","date":"2026-05-01"}.n_clicks
    if "cal-day" in prop_id:
        try:
            import json
            # Parse the JSON part before .n_clicks
            json_part = prop_id.split(".n_clicks")[0]
            cell_id = json.loads(json_part)
            return cell_id.get("date")
        except Exception:
            return None
    
    return None
