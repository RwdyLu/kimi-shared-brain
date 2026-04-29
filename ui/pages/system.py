"""
System Page / 系統頁面

System logs, health, and settings.
系統日誌、健康度與設定。
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import json
import urllib.request
import re

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Import monitor service and paths / 匯入監測服務與路徑
from ui.services.monitor_service import (
    get_scheduler_status,
    get_last_run_info,
    get_next_run_time,
    get_logs_preview
)
from config.paths import PROJECT_ROOT, CONFIG_DIR, LOGS_DIR, OUTPUTS_DIR, STATE_DIR

# ─── New Feature E: Health check helpers / 健康檢查輔助函數 ───

def check_scheduler_alive() -> tuple:
    """Check if scheduler is alive via .scheduler.lock / 檢查 scheduler 是否存活"""
    lock_file = STATE_DIR / ".scheduler.lock"
    if not lock_file.exists():
        return False, "No lock file"
    try:
        mtime = lock_file.stat().st_mtime
        age_min = (datetime.now().timestamp() - mtime) / 60
        if age_min < 10:
            return True, f"Active ({age_min:.0f}m ago)"
        return False, f"Stale ({age_min:.0f}m ago)"
    except Exception as e:
        return False, str(e)


def check_binance_ping() -> tuple:
    """Ping Binance API / 測試 Binance API 連線"""
    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/ping",
            headers={"User-Agent": "Mozilla/5.0"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True, f"OK ({resp.status})"
    except Exception as e:
        return False, str(e)[:30]


def check_state_dir_age() -> tuple:
    """Check state directory last update / 檢查 state 目錄最後更新時間"""
    try:
        newest = 0
        for f in STATE_DIR.iterdir():
            if f.is_file():
                mtime = f.stat().st_mtime
                if mtime > newest:
                    newest = mtime
        if newest == 0:
            return False, "Empty"
        age_min = (datetime.now().timestamp() - newest) / 60
        ok = age_min < 10
        return ok, f"{age_min:.0f}m ago"
    except Exception as e:
        return False, str(e)[:30]


def check_paper_balance() -> tuple:
    """Check paper trading balance / 檢查模擬交易餘額"""
    try:
        state_file = STATE_DIR / "paper_trading_state.json"
        if not state_file.exists():
            return False, "No state"
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        balance = state.get("balance", 0)
        ok = balance > 1000
        return ok, f"${balance:,.2f}"
    except Exception as e:
        return False, str(e)[:30]


def check_max_hold_time() -> tuple:
    """Check if any position held > 8h / 檢查是否有倉位超過 8 小時"""
    try:
        state_file = STATE_DIR / "paper_trading_state.json"
        if not state_file.exists():
            return True, "No positions"
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        positions = state.get("positions", {})
        if not positions:
            return True, "No positions"
        now = datetime.now()
        max_hours = 0
        for sym, pos in positions.items():
            entry_time_str = pos.get("entry_time")
            if entry_time_str:
                try:
                    entry_time = datetime.fromisoformat(entry_time_str)
                    hours = (now - entry_time).total_seconds() / 3600
                    if hours > max_hours:
                        max_hours = hours
                except Exception:
                    pass
        ok = max_hours < 8
        return ok, f"Max {max_hours:.1f}h"
    except Exception as e:
        return False, str(e)[:30]


def load_recent_runs(limit: int = 10) -> list:
    """Parse scheduler.log for recent runs / 解析 scheduler.log 取得最近 run 記錄"""
    runs = []
    log_file = LOGS_DIR / "scheduler.log"
    if not log_file.exists():
        return []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return []
    
    # Parse backwards / 反向解析
    i = len(lines) - 1
    while i >= 0 and len(runs) < limit:
        line = lines[i]
        # Look for "Run #N completed" lines
        m = re.search(r'Run #(\d+) completed', line)
        if m:
            run_num = m.group(1)
            # Scan backwards for signals count
            signals = 0
            failed = False
            j = i - 1
            while j >= 0 and (i - j) < 30:
                prev = lines[j]
                sig_m = re.search(r'Signals:\s*(\d+)', prev)
                if sig_m:
                    signals = int(sig_m.group(1))
                if 'ERROR' in prev or 'Exception' in prev:
                    failed = True
                if re.search(r'Run #\d+ started', prev):
                    break
                j -= 1
            
            status = "error" if failed else ("signals" if signals > 0 else "empty")
            runs.append({"run": run_num, "status": status, "signals": signals})
        i -= 1
    
    return list(reversed(runs))


# Register page / 註冊頁面
dash.register_page(__name__, path="/system", title="System")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("System", className="mb-4"),
        html.P("System logs, health, and settings / 系統日誌、健康度與設定", className="text-muted"),
        
        html.Hr(),
        
        # ─── New Feature E: Health Dashboard / 健康儀表板 ───
        dbc.Card(
            [
                dbc.CardHeader([
                    html.H5("System Health / 系統健康儀表板", className="mb-0 d-inline"),
                    dbc.Badge("Live", color="success", className="ms-2")
                ]),
                dbc.CardBody(
                    [
                        # 5 Health Indicators / 5 個健康指標
                        html.H6("Health Indicators / 健康指標", className="mb-3 text-muted"),
                        dbc.Row(id="health-indicators", children=[], className="mb-4"),
                        
                        html.Hr(),
                        
                        # Recent Runs Mini-Map / 最近 Run 迷你圖
                        html.H6("Recent Runs / 最近執行記錄", className="mb-3 text-muted"),
                        html.Div(id="recent-runs-minimap", children=[]),
                        html.Small("🟢 Signals  ⬜ No Signals  🔴 Error", className="text-muted d-block mt-2")
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Scheduler Status / 排程器狀態
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Scheduler Status / 排程器狀態", className="mb-0")),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6("Status / 狀態"),
                                        html.P(id="system-scheduler-status", children="Checking...")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("PID"),
                                        html.P(id="system-scheduler-pid", children="--")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Last Run / 最後執行"),
                                        html.P(id="system-last-run", children="--")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Next Run / 下次執行"),
                                        html.P(id="system-next-run", children="--")
                                    ],
                                    width=6,
                                    md=3
                                ),
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Scheduler Controls / 排程器控制
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Scheduler Controls / 排程器控制", className="mb-0")),
                dbc.CardBody(
                    [
                        html.P("Control the monitoring scheduler / 控制監測排程器"),
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "🔄 Restart / 重啟",
                                    color="warning",
                                    className="me-2",
                                    id="system-restart-btn"
                                ),
                                dbc.Button(
                                    "⏹ Stop / 停止",
                                    color="danger",
                                    className="me-2",
                                    id="system-stop-btn"
                                ),
                                dbc.Button(
                                    "▶ Start / 啟動",
                                    color="success",
                                    id="system-start-btn"
                                ),
                            ]
                        ),
                        html.Hr(),
                        html.P("View Configuration / 查看配置:", className="mb-2"),
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "Monitoring Params",
                                    href="/parameters",
                                    color="link",
                                    size="sm"
                                ),
                            ]
                        ),
                        html.P(
                            "⚠️ Scheduler controls are for display only in MVP. Use command line to control scheduler.",
                            className="text-muted small mt-3 mb-0"
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Recent Logs / 最近日誌
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Recent Logs / 最近日誌", className="mb-0"),
                        dbc.Badge("Live", color="success", className="ms-2")
                    ]
                ),
                dbc.CardBody(
                    [
                        html.Div(
                            id="system-logs",
                            children="Loading logs...",
                            style={
                                "maxHeight": "400px",
                                "overflowY": "auto",
                                "fontFamily": "monospace",
                                "fontSize": "0.85rem",
                                "backgroundColor": "#f8f9fa",
                                "padding": "1rem",
                                "borderRadius": "0.25rem"
                            }
                        ),
                        html.Hr(),
                        dbc.Button(
                            "Refresh Logs / 刷新日誌",
                            id="system-refresh-logs",
                            color="outline-primary",
                            size="sm"
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # File Locations / 檔案位置
        dbc.Card(
            [
                dbc.CardHeader(html.H5("File Locations / 檔案位置", className="mb-0")),
                dbc.CardBody(
                    [
                        dbc.Table(
                            [
                                html.Thead(
                                    html.Tr([
                                        html.Th("Type / 類型"),
                                        html.Th("Location / 位置")
                                    ])
                                ),
                                html.Tbody(
                                    [
                                        html.Tr([
                                            html.Td("Project Root / 專案根目錄"),
                                            html.Td(html.Code(str(PROJECT_ROOT)))
                                        ]),
                                        html.Tr([
                                            html.Td("Config Files / 配置文件"),
                                            html.Td(html.Code(str(CONFIG_DIR) + "/"))
                                        ]),
                                        html.Tr([
                                            html.Td("Logs / 日誌"),
                                            html.Td(html.Code(str(LOGS_DIR / "scheduler.log")))
                                        ]),
                                        html.Tr([
                                            html.Td("PID File / PID 檔案"),
                                            html.Td(html.Code(str(PROJECT_ROOT / ".monitor.pid")))
                                        ]),
                                        html.Tr([
                                            html.Td("Outputs / 輸出"),
                                            html.Td(html.Code(str(OUTPUTS_DIR) + "/"))
                                        ]),
                                        html.Tr([
                                            html.Td("State / 狀態"),
                                            html.Td(html.Code(str(STATE_DIR) + "/"))
                                        ]),
                                    ]
                                )
                            ],
                            bordered=True,
                            size="sm"
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Version Info / 版本資訊
        dbc.Card(
            [
                dbc.CardHeader(html.H5("Version Information / 版本資訊", className="mb-0")),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6("UI Version"),
                                        html.P("1.0.0", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Monitoring System"),
                                        html.P("1.1.0", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Config Schema"),
                                        html.P("1.0.0", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                                dbc.Col(
                                    [
                                        html.H6("Last Updated"),
                                        html.P("2026-04-07", className="text-muted")
                                    ],
                                    width=6,
                                    md=3
                                ),
                            ]
                        ),
                        html.Hr(),
                        html.P(
                            [
                                "Repository: ",
                                html.A(
                                    "github.com/RwdyLu/kimi-shared-brain",
                                    href="https://github.com/RwdyLu/kimi-shared-brain",
                                    target="_blank"
                                )
                            ],
                            className="text-muted mb-0"
                        )
                    ]
                )
            ]
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="system-interval",
            interval=30*1000,  # 30 seconds
            n_intervals=0
        ),
    ],
    fluid=True
)


# Callbacks / 回調

@callback(
    Output("health-indicators", "children"),
    Output("recent-runs-minimap", "children"),
    Output("system-scheduler-status", "children"),
    Output("system-scheduler-pid", "children"),
    Output("system-last-run", "children"),
    Output("system-next-run", "children"),
    Output("system-logs", "children"),
    Input("system-interval", "n_intervals"),
    Input("system-refresh-logs", "n_clicks")
)
def update_system_info(n_intervals, n_clicks):
    """Update system information with health dashboard / 更新系統資訊（含健康儀表板）"""
    try:
        # ─── Health Indicators / 健康指標 ───
        sched_ok, sched_msg = check_scheduler_alive()
        binance_ok, binance_msg = check_binance_ping()
        state_ok, state_msg = check_state_dir_age()
        balance_ok, balance_msg = check_paper_balance()
        hold_ok, hold_msg = check_max_hold_time()
        
        indicators = dbc.Row(
            [
                _health_indicator("Scheduler / 排程器", sched_ok, sched_msg),
                _health_indicator("Binance API", binance_ok, binance_msg),
                _health_indicator("State Write / 資料寫入", state_ok, state_msg),
                _health_indicator("Paper Balance / 餘額", balance_ok, balance_msg),
                _health_indicator("Hold Time / 持倉時間", hold_ok, hold_msg),
            ]
        )
        
        # ─── Recent Runs Mini-Map / 最近執行迷你圖 ───
        runs = load_recent_runs(10)
        minimap_blocks = []
        for run in runs:
            status = run.get("status", "empty")
            run_num = run.get("run", "?")
            signals = run.get("signals", 0)
            if status == "error":
                color = "#dc3545"  # red
                title = f"Run #{run_num}: Error"
            elif status == "signals":
                color = "#198754"  # green
                title = f"Run #{run_num}: {signals} signals"
            else:
                color = "#e9ecef"  # light gray
                title = f"Run #{run_num}: No signals"
            
            minimap_blocks.append(
                html.Div(
                    "",
                    style={
                        "width": "24px",
                        "height": "24px",
                        "backgroundColor": color,
                        "borderRadius": "4px",
                        "marginRight": "4px",
                        "display": "inline-block",
                        "cursor": "help",
                    },
                    title=title
                )
            )
        
        if not minimap_blocks:
            minimap = html.Small("No run history / 暫無執行記錄", className="text-muted")
        else:
            minimap = html.Div(minimap_blocks, style={"display": "flex", "flexWrap": "wrap", "gap": "4px"})
        
        # ─── Legacy scheduler info / 既有排程器資訊 ───
        status = get_scheduler_status()
        if status.get("running"):
            scheduler_status_text = dbc.Badge("✓ Operational", color="success")
        else:
            scheduler_status_text = dbc.Badge("✗ Not Running", color="danger")
        
        last_run = get_last_run_info()
        last_run_text = last_run.get("time_ago", "--") if last_run.get("timestamp") else "No runs"
        
        next_run = get_next_run_time()
        next_run_text = next_run if next_run else "--"
        
        logs = get_logs_preview(30)
        logs_display = html.Pre(logs, style={"margin": 0, "whiteSpace": "pre-wrap"})
        
        return (
            indicators,
            minimap,
            scheduler_status_text,
            status.get("pid", "--"),
            last_run_text,
            next_run_text,
            logs_display
        )
        
    except Exception as e:
        error_msg = dbc.Alert(f"Error: {e}", color="danger")
        empty = html.Small("--", className="text-muted")
        return error_msg, empty, "Error", "--", "--", "--", f"Error loading logs: {e}"


def _health_indicator(label: str, ok: bool, detail: str) -> dbc.Col:
    """Build a single health indicator column / 建立單個健康指標欄位"""
    color = "#198754" if ok else "#dc3545" if not ok and "No" not in detail else "#ffc107"
    status_text = "OK" if ok else "WARN" if "No" not in detail else "OFF"
    return dbc.Col(
        [
            html.Div(
                "",
                style={
                    "width": "16px",
                    "height": "16px",
                    "borderRadius": "50%",
                    "backgroundColor": color,
                    "display": "inline-block",
                    "marginRight": "8px",
                    "verticalAlign": "middle",
                }
            ),
            html.Span(label, className="small fw-bold"),
            html.Br(),
            html.Small(detail, className="text-muted"),
            html.Br(),
            html.Small(status_text, className=f"{'text-success' if ok else 'text-danger' if not ok and 'No' not in detail else 'text-warning'}"),
        ],
        width=6,
        md=2,
        className="mb-3"
    )
