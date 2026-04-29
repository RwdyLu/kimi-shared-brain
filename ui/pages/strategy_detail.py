"""
Strategy Detail Page / 策略詳情頁面

Interactive strategy detail page with coin selector and condition status.
互動式策略詳情頁面，包含幣種選擇器與條件狀態。

BTC/ETH Monitoring System - UI Layer
"""

import dash
from dash import dcc, html, callback, Output, Input
import dash_bootstrap_components as dbc
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from app.strategy_conditions import StrategyConditions, ConditionResult
from config.paths import PROJECT_ROOT, LOGS_DIR

# Register page with dynamic route / 註冊動態路由頁面
dash.register_page(__name__, path_template="/strategy/<strategy_name>", title="Strategy Detail")

# Constants / 常數
ALL_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"
]

# Load strategies from config / 從配置載入策略
def load_strategies():
    """Load strategies from config/strategies.json"""
    try:
        strategies_file = PROJECT_ROOT / "config" / "strategies.json"
        with open(strategies_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("strategies", [])
    except Exception as e:
        print(f"Error loading strategies: {e}")
        return []


def find_strategy(strategy_name: str):
    """Find strategy by id, name, or signal_type with flexible matching"""
    if not strategy_name:
        return None
    strategies = load_strategies()
    strategy_name_lower = strategy_name.lower().replace(" ", "_")
    for s in strategies:
        sid = s.get("id", "")
        sname = s.get("name", "")
        stype = s.get("signal_type", "")
        if sid == strategy_name:
            return s
        if sname == strategy_name:
            return s
        if stype == strategy_name:
            return s
        # Flexible: id normalized vs input normalized
        if sid.lower().replace("_", "") == strategy_name_lower.replace("_", ""):
            return s
        # Flexible: name normalized (spaces → underscores)
        if sname.lower().replace(" ", "_") == strategy_name_lower:
            return s
    print(f"[find_strategy] Not found: '{strategy_name}'. Available: {[s.get('id') for s in strategies]}")
    return None


def get_latest_snapshot(symbol: str) -> dict:
    """Get latest indicator snapshot for a symbol"""
    try:
        snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"
        if not snapshot_file.exists():
            return {}
        
        latest = {}
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get("symbol") == symbol:
                        # Keep the latest entry for this symbol
                        latest = data
                except json.JSONDecodeError:
                    continue
        return latest
    except Exception as e:
        print(f"Error reading snapshot for {symbol}: {e}")
        return {}


def get_signal_history(strategy_id: str, strategy_signal_type: str, symbol: str, limit: int = 5) -> list:
    """Get recent signal history for a strategy and symbol from snapshots"""
    try:
        snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"
        if not snapshot_file.exists():
            return []
        
        # Expected signal type in snapshots (uppercase)
        expected_signal = strategy_signal_type.upper().replace(" ", "_")
        
        runs = defaultdict(list)
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Scan from most recent
        for line in reversed(lines):
            try:
                data = json.loads(line.strip())
                if data.get("symbol") != symbol:
                    continue
                
                signal_types = data.get("signal_types", [])
                if not signal_types:
                    continue
                
                # Check if this snapshot contains our strategy's signal
                matched = any(expected_signal in st.upper() or strategy_id.upper().replace("_", "") in st.upper().replace("_", "") for st in signal_types)
                
                if matched:
                    run_id = data.get("run_id", data.get("timestamp", "unknown"))
                    runs[str(run_id)].append(data)
            except json.JSONDecodeError:
                continue
        
        # Get last N runs
        result = []
        for run_id in sorted(runs.keys(), reverse=True)[:limit]:
            entries = runs[run_id]
            if entries:
                # Use the first entry as representative
                entry = entries[0]
                result.append({
                    "run_id": run_id,
                    "timestamp": entry.get("timestamp", "--"),
                    "symbol": symbol,
                    "price": entry.get("price"),
                    "signal_types": entry.get("signal_types", []),
                    "signals_count": entry.get("signals_count", 0)
                })
        
        return result
    except Exception as e:
        print(f"Error reading signal history: {e}")
        return []


def get_recent_runs_for_strategy(strategy_signal_type: str, symbol: str, limit: int = 5) -> list:
    """Get recent runs with signal info for this strategy, even if no signal was generated"""
    try:
        snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"
        if not snapshot_file.exists():
            return []
        
        runs = {}
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in reversed(lines):
            try:
                data = json.loads(line.strip())
                if data.get("symbol") != symbol:
                    continue
                
                run_id = str(data.get("run_id", data.get("timestamp", "unknown")))
                if run_id not in runs:
                    runs[run_id] = data
                
                if len(runs) >= limit * 3:  # Get more to have enough distinct runs
                    break
            except json.JSONDecodeError:
                continue
        
        # Sort by run_id (timestamp-based) descending, take limit
        sorted_runs = sorted(runs.values(), key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
        
        result = []
        for entry in sorted_runs:
            signal_types = entry.get("signal_types", [])
            expected = strategy_signal_type.upper().replace(" ", "_")
            has_signal = any(expected in st.upper() or strategy_signal_type.upper().replace("_", "") in st.upper().replace("_", "") for st in signal_types)
            
            result.append({
                "run_id": entry.get("run_id", "--"),
                "timestamp": entry.get("timestamp", "--"),
                "symbol": symbol,
                "price": entry.get("price"),
                "has_signal": has_signal,
                "signal_types": signal_types,
                "signals_count": entry.get("signals_count", 0)
            })
        
        return result
    except Exception as e:
        print(f"Error reading runs: {e}")
        return []


# Status badge colors / 狀態標籤顏色
STATUS_COLORS = {
    "PASSED": "success",
    "FAILED": "danger",
    "MISSING_DATA": "warning",
    "NOT_IMPLEMENTED": "secondary"
}

STATUS_LABELS = {
    "PASSED": "✓ PASS",
    "FAILED": "✗ FAIL",
    "MISSING_DATA": "⚠ MISSING",
    "NOT_IMPLEMENTED": "? N/A"
}


def layout(strategy_name=None):
    """Page layout with strategy name from URL"""
    
    # Find strategy / 查找策略
    strategy = find_strategy(strategy_name) if strategy_name else None
    
    if not strategy:
        return dbc.Container(
            [
                dcc.Location(id="strategy-url", refresh=False),
                html.H2("Strategy Not Found / 策略未找到", className="mb-4"),
                dbc.Alert(
                    f"No strategy found with name: '{strategy_name}' / 找不到名稱為 '{strategy_name}' 的策略",
                    color="danger"
                ),
                dbc.Button("← Back to Dashboard / 返回儀表板", href="/", color="primary")
            ],
            fluid=True
        )
    
    # Strategy info / 策略資訊
    name = strategy.get("name", "Unknown")
    name_zh = strategy.get("name_zh", "")
    description = strategy.get("description", "No description")
    strategy_type = strategy.get("type", "unknown")
    enabled = strategy.get("enabled", False)
    symbols = strategy.get("symbols", ALL_SYMBOLS)
    default_symbol = symbols[0] if symbols else "BTCUSDT"
    
    type_colors = {
        "trend": "primary",
        "contrarian": "info",
        "mean_reversion": "warning",
        "cycle": "purple",
        "breakout": "danger",
        "momentum": "success"
    }
    
    return dbc.Container(
        [
            dcc.Location(id="strategy-url", refresh=False),
            dcc.Store(id="strategy-name-store", data=strategy_name),
            
            # Header / 頁首
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H2([
                                html.Span("📈 ", className="me-2"),
                                name
                            ], className="mb-1"),
                            html.H5(name_zh, className="text-muted mb-2") if name_zh else None,
                            html.P(description, className="text-muted mb-0")
                        ],
                        width=12,
                        md=8
                    ),
                    dbc.Col(
                        [
                            html.Div(
                                [
                                    dbc.Badge(
                                        strategy_type.upper(),
                                        color=type_colors.get(strategy_type, "secondary"),
                                        className="me-2"
                                    ),
                                    dbc.Badge(
                                        "Enabled / 啟用" if enabled else "Disabled / 停用",
                                        color="success" if enabled else "secondary"
                                    )
                                ],
                                className="text-end"
                            ),
                            html.Div(
                                dbc.Button(
                                    "← Dashboard / 儀表板",
                                    href="/",
                                    size="sm",
                                    color="outline-primary",
                                    className="mt-2"
                                ),
                                className="text-end"
                            )
                        ],
                        width=12,
                        md=4,
                        className="d-flex flex-column justify-content-center"
                    )
                ],
                className="mb-4"
            ),
            
            html.Hr(),
            
            # Coin Selector / 幣種選擇器
            dbc.Card(
                [
                    dbc.CardHeader([
                        html.H5("🪙 Coin Selector / 幣種選擇", className="mb-0")
                    ]),
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.Label("Select Symbol / 選擇標的", className="fw-bold"),
                                            dbc.Select(
                                                id="strategy-coin-selector",
                                                options=[
                                                    {"label": s.replace("USDT", "/USDT"), "value": s}
                                                    for s in symbols
                                                ],
                                                value=default_symbol
                                            )
                                        ],
                                        width=12,
                                        md=4
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Current Price / 當前價格", className="fw-bold"),
                                            html.H4(id="strategy-current-price", children="--", className="text-primary mb-0")
                                        ],
                                        width=12,
                                        md=4,
                                        className="d-flex flex-column justify-content-center"
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Strategy Score / 策略評分", className="fw-bold"),
                                            html.H4(id="strategy-score", children="--", className="text-info mb-0")
                                        ],
                                        width=12,
                                        md=4,
                                        className="d-flex flex-column justify-content-center"
                                    )
                                ]
                            )
                        ]
                    )
                ],
                className="mb-4"
            ),
            
            # Condition Status / 條件狀態
            dbc.Card(
                [
                    dbc.CardHeader([
                        html.H5("📋 Conditions / 條件檢查", className="mb-0"),
                        html.Small("Real-time condition evaluation / 即時條件評估", className="text-muted")
                    ]),
                    dbc.CardBody(
                        id="strategy-conditions-body",
                        children=[
                            html.P("Loading conditions... / 載入條件中...", className="text-muted")
                        ]
                    )
                ],
                className="mb-4"
            ),
            
            # Technical Indicators / 技術指標
            dbc.Card(
                [
                    dbc.CardHeader([
                        html.H5("📊 Technical Indicators / 技術指標", className="mb-0"),
                        html.Small("Latest indicator values / 最新指標數值", className="text-muted")
                    ]),
                    dbc.CardBody(
                        id="strategy-indicators-body",
                        children=[
                            html.P("Loading indicators... / 載入指標中...", className="text-muted")
                        ]
                    )
                ],
                className="mb-4"
            ),
            
            # Signal History / 訊號歷史
            dbc.Card(
                [
                    dbc.CardHeader([
                        html.H5("📜 Signal History / 訊號歷史", className="mb-0"),
                        html.Small("Recent 5 runs / 最近 5 次執行", className="text-muted")
                    ]),
                    dbc.CardBody(
                        id="strategy-signal-history",
                        children=[
                            html.P("Loading signal history... / 載入訊號歷史中...", className="text-muted")
                        ]
                    )
                ],
                className="mb-4"
            ),
            
            # Auto-refresh / 自動刷新
            dcc.Interval(
                id="strategy-interval",
                interval=30*1000,  # 30 seconds
                n_intervals=0
            ),
        ],
        fluid=True
    )


# Callback: Update all content based on coin selection and interval / 回調：根據幣種選擇與間隔更新內容
@callback(
    Output("strategy-current-price", "children"),
    Output("strategy-score", "children"),
    Output("strategy-conditions-body", "children"),
    Output("strategy-indicators-body", "children"),
    Output("strategy-signal-history", "children"),
    Input("strategy-coin-selector", "value"),
    Input("strategy-interval", "n_intervals"),
    Input("strategy-name-store", "data")
)
def update_strategy_detail(selected_symbol, n_intervals, strategy_name):
    """Update strategy detail content for selected coin"""
    if not strategy_name:
        return "--", "--", html.P("No strategy selected / 未選擇策略", className="text-muted"), html.P("No strategy selected", className="text-muted"), html.P("No strategy selected", className="text-muted")
    
    strategy = find_strategy(strategy_name)
    if not strategy:
        return "--", "--", dbc.Alert("Strategy not found / 策略未找到", color="danger"), html.Div(), html.Div()
    
    # Get latest snapshot for selected symbol
    snapshot = get_latest_snapshot(selected_symbol)
    
    # Current price
    price = snapshot.get("price")
    price_display = f"${price:,.2f}" if price else "--"
    
    # Score from live_strategy_ranking.json
    score = "--"
    try:
        ranking_file = PROJECT_ROOT / "state" / "live_strategy_ranking.json"
        if ranking_file.exists():
            with open(ranking_file, 'r') as f:
                ranking_data = json.load(f)
            symbol_scores = ranking_data.get("symbols", {})
            symbol_entry = symbol_scores.get(selected_symbol, {})
            scores = symbol_entry.get("strategies", [])
            for s in scores:
                if s.get("name") == strategy_name:
                    score = f"{s.get('score', 0) * 100:.1f}"
                    break
    except Exception:
        pass
    
    # Evaluate conditions
    conditions_component = render_conditions(strategy, snapshot)
    
    # Render indicators
    indicators_component = render_indicators(snapshot, strategy)
    
    # Render signal history
    signal_history_component = render_signal_history(strategy, selected_symbol)
    
    return price_display, score, conditions_component, indicators_component, signal_history_component


def render_conditions(strategy, snapshot):
    """Render conditions table with status"""
    conditions = strategy.get("conditions", [])
    parameters = strategy.get("parameters", {})
    
    if not conditions:
        return dbc.Alert("No conditions defined / 未定義條件", color="info")
    
    # Build data dict from snapshot
    data = {
        "price": snapshot.get("price"),
        "ma5": snapshot.get("ma5"),
        "ma20": snapshot.get("ma20"),
        "ma240": snapshot.get("ma240"),
        "ma5_prev": snapshot.get("ma5_prev"),
        "ma20_prev": snapshot.get("ma20_prev"),
        "volume_ratio": snapshot.get("volume_ratio"),
        "candles": snapshot.get("candles", []),
        "closes": snapshot.get("closes", []),
        "ht_sine": snapshot.get("ht_sine"),
        "ht_leadsine": snapshot.get("ht_leadsine"),
        "ht_sine_prev": snapshot.get("ht_sine_prev"),
        "ht_leadsine_prev": snapshot.get("ht_leadsine_prev"),
        "tema": snapshot.get("tema"),
        "tema_prev": snapshot.get("tema_prev"),
        "bb_middle": snapshot.get("bb_middle"),
        "bb_lower": snapshot.get("bb_lower"),
        "stoch_fastk": snapshot.get("stoch_fastk"),
        "stoch_fastd": snapshot.get("stoch_fastd"),
        "stoch_fastk_prev": snapshot.get("stoch_fastk_prev"),
        "stoch_fastd_prev": snapshot.get("stoch_fastd_prev"),
        "sar": snapshot.get("sar"),
        "rsi": snapshot.get("rsi"),
        "rsi_prev": snapshot.get("rsi_prev"),
    }
    
    # Evaluate conditions
    checker = StrategyConditions()
    results = checker.check_all_conditions(conditions, data, parameters)
    
    # Build table rows
    rows = []
    for check in results:
        status = check.result.name.upper()
        color = STATUS_COLORS.get(status, "secondary")
        label = STATUS_LABELS.get(status, status)
        
        # Get threshold info
        threshold_info = ""
        if check.condition == "volume_spike":
            threshold_info = f"≥ {parameters.get('volume_threshold', 1.5)}x"
        elif check.condition in ["consecutive_green", "consecutive_red"]:
            threshold_info = f"≥ {parameters.get('consecutive_count', 4)} candles"
        elif check.condition == "close_vs_ma240":
            threshold_info = f"≤ {parameters.get('ma240_threshold', 2.0)}% deviation"
        elif check.condition == "fastk_below_20":
            threshold_info = "< 20"
        elif check.condition == "rsi_below_30":
            threshold_info = "< 30"
        elif check.condition == "rsi_cross_above_30":
            threshold_info = "> 30"
        else:
            threshold_info = "N/A"
        
        # Current value
        current_value = ""
        if check.details:
            if "volume_ratio" in check.details:
                current_value = f"{check.details['volume_ratio']:.2f}x"
            elif "price" in check.details and "ma240" in check.details:
                current_value = f"Price: ${check.details['price']:,.2f}, MA240: ${check.details['ma240']:,.2f}"
            elif "ma5" in check.details and "ma20" in check.details:
                current_value = f"MA5: ${check.details['ma5']:,.2f}, MA20: ${check.details['ma20']:,.2f}"
            elif "rsi" in check.details:
                current_value = f"RSI: {check.details['rsi']:.2f}"
            elif "fastk" in check.details:
                current_value = f"FastK: {check.details['fastk']:.2f}"
            elif "sine" in check.details:
                current_value = f"Sine: {check.details['sine']:.4f}, LeadSine: {check.details.get('leadsine', 'N/A')}"
            elif "tema" in check.details:
                current_value = f"TEMA: ${check.details['tema']:,.2f}"
            elif "green_count" in check.details:
                current_value = f"{check.details['green_count']} green"
            elif "red_count" in check.details:
                current_value = f"{check.details['red_count']} red"
            elif "sar" in check.details:
                current_value = f"SAR: ${check.details['sar']:,.2f}"
            elif "bb_lower" in check.details:
                current_value = f"BB Lower: ${check.details['bb_lower']:,.2f}"
            elif "bb_middle" in check.details:
                current_value = f"BB Middle: ${check.details['bb_middle']:,.2f}"
        
        if not current_value:
            current_value = check.message[:50] if check.message else "--"
        
        rows.append(html.Tr([
            html.Td(check.condition, className="font-monospace"),
            html.Td(threshold_info, className="text-muted small"),
            html.Td(current_value, className="small"),
            html.Td(dbc.Badge(label, color=color, className="px-2 py-1")),
            html.Td(check.message, className="text-muted small")
        ]))
    
    # Overall status
    all_passed = all(r.result == ConditionResult.PASSED for r in results)
    overall_badge = dbc.Badge(
        "✅ ALL PASSED / 全部通過" if all_passed else "❌ NOT ALL PASSED / 未全部通過",
        color="success" if all_passed else "warning",
        className="mb-3 px-3 py-2"
    )
    
    return html.Div([
        overall_badge,
        dbc.Table(
            [
                html.Thead(html.Tr([
                    html.Th("Condition / 條件"),
                    html.Th("Threshold / 閾值"),
                    html.Th("Current Value / 當前值"),
                    html.Th("Status / 狀態"),
                    html.Th("Message / 訊息")
                ])),
                html.Tbody(rows)
            ],
            bordered=True,
            hover=True,
            size="sm",
            responsive=True,
            className="mb-0"
        )
    ])


def render_indicators(snapshot, strategy):
    """Render technical indicators grid"""
    indicators = strategy.get("indicators", [])
    
    # Default indicators to show / 預設顯示的指標
    indicator_cards = []
    
    # Price / 價格
    price = snapshot.get("price")
    if price is not None:
        indicator_cards.append(make_indicator_card("Price / 價格", f"${price:,.2f}", "primary"))
    
    # Moving Averages / 移動平均線
    ma5 = snapshot.get("ma5")
    if ma5 is not None:
        indicator_cards.append(make_indicator_card("MA5", f"${ma5:,.2f}", "info"))
    
    ma20 = snapshot.get("ma20")
    if ma20 is not None:
        indicator_cards.append(make_indicator_card("MA20", f"${ma20:,.2f}", "info"))
    
    ma240 = snapshot.get("ma240")
    if ma240 is not None:
        indicator_cards.append(make_indicator_card("MA240", f"${ma240:,.2f}", "info"))
    
    # Volume / 成交量
    volume_ratio = snapshot.get("volume_ratio")
    if volume_ratio is not None:
        vol_color = "success" if volume_ratio >= 1.5 else ("warning" if volume_ratio >= 1.0 else "secondary")
        indicator_cards.append(make_indicator_card("Volume Ratio / 成交量比", f"{volume_ratio:.2f}x", vol_color))
    
    # RSI
    rsi = snapshot.get("rsi")
    if rsi is not None:
        rsi_color = "success" if 30 <= rsi <= 70 else ("danger" if rsi > 70 else "warning")
        indicator_cards.append(make_indicator_card("RSI", f"{rsi:.2f}", rsi_color))
    
    # TEMA
    tema = snapshot.get("tema")
    if tema is not None:
        indicator_cards.append(make_indicator_card("TEMA", f"${tema:,.2f}", "info"))
    
    # Bollinger Bands / 布林帶
    bb_middle = snapshot.get("bb_middle")
    if bb_middle is not None:
        indicator_cards.append(make_indicator_card("BB Middle / 布林中軌", f"${bb_middle:,.2f}", "info"))
    
    bb_lower = snapshot.get("bb_lower")
    if bb_lower is not None:
        indicator_cards.append(make_indicator_card("BB Lower / 布林下軌", f"${bb_lower:,.2f}", "info"))
    
    # Stochastic / 隨機指標
    fastk = snapshot.get("stoch_fastk")
    if fastk is not None:
        indicator_cards.append(make_indicator_card("Stoch FastK", f"{fastk:.2f}", "info"))
    
    fastd = snapshot.get("stoch_fastd")
    if fastd is not None:
        indicator_cards.append(make_indicator_card("Stoch FastD", f"{fastd:.2f}", "info"))
    
    # SAR
    sar = snapshot.get("sar")
    if sar is not None:
        indicator_cards.append(make_indicator_card("SAR", f"${sar:,.2f}", "info"))
    
    # HT Sine
    ht_sine = snapshot.get("ht_sine")
    if ht_sine is not None:
        indicator_cards.append(make_indicator_card("HT Sine", f"{ht_sine:.4f}", "info"))
    
    ht_leadsine = snapshot.get("ht_leadsine")
    if ht_leadsine is not None:
        indicator_cards.append(make_indicator_card("HT LeadSine", f"{ht_leadsine:.4f}", "info"))
    
    # Distance percentages / 距離百分比
    price_vs_ma5 = snapshot.get("price_vs_ma5_pct")
    if price_vs_ma5 is not None:
        color = "success" if price_vs_ma5 >= 0 else "danger"
        indicator_cards.append(make_indicator_card("Price vs MA5 / 價格與MA5", f"{price_vs_ma5:+.2f}%", color))
    
    price_vs_ma20 = snapshot.get("price_vs_ma20_pct")
    if price_vs_ma20 is not None:
        color = "success" if price_vs_ma20 >= 0 else "danger"
        indicator_cards.append(make_indicator_card("Price vs MA20 / 價格與MA20", f"{price_vs_ma20:+.2f}%", color))
    
    price_vs_ma240 = snapshot.get("price_vs_ma240_pct")
    if price_vs_ma240 is not None:
        color = "success" if price_vs_ma240 >= 0 else "danger"
        indicator_cards.append(make_indicator_card("Price vs MA240 / 價格與MA240", f"{price_vs_ma240:+.2f}%", color))
    
    if not indicator_cards:
        return dbc.Alert("No indicator data available / 無指標資料", color="warning")
    
    # Arrange in rows of 4
    rows = []
    for i in range(0, len(indicator_cards), 4):
        row_cards = indicator_cards[i:i+4]
        cols = [dbc.Col(card, width=6, md=3, className="mb-3") for card in row_cards]
        rows.append(dbc.Row(cols))
    
    return html.Div(rows)


def make_indicator_card(title, value, color):
    """Create a small indicator card"""
    return dbc.Card(
        [
            dbc.CardBody(
                [
                    html.H6(title, className="text-muted small mb-1"),
                    html.H5(value, className=f"text-{color} mb-0 fw-bold")
                ],
                className="py-2 px-3"
            )
        ],
        color=color,
        outline=True,
        className="h-100"
    )


def render_signal_history(strategy, symbol):
    """Render signal history for last 5 runs"""
    signal_type = strategy.get("signal_type", "")
    
    # Get recent runs (with or without signals)
    runs = get_recent_runs_for_strategy(signal_type, symbol, limit=5)
    
    if not runs:
        return dbc.Alert(
            "No run history available for this symbol / 此標的無執行歷史",
            color="info"
        )
    
    rows = []
    for run in runs:
        run_id = run.get("run_id", "--")
        timestamp = run.get("timestamp", "--")
        price = run.get("price")
        has_signal = run.get("has_signal", False)
        signal_types = run.get("signal_types", [])
        signals_count = run.get("signals_count", 0)
        
        # Format timestamp
        try:
            ts = datetime.fromisoformat(timestamp)
            time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = str(timestamp)
        
        # Signal badge
        if has_signal:
            signal_badge = dbc.Badge("✓ Confirmed / 已確認", color="success", className="px-2")
        elif signals_count > 0:
            signal_badge = dbc.Badge("⚠ Other Signal / 其他訊號", color="warning", className="px-2")
        else:
            signal_badge = dbc.Badge("✗ No Signal / 無訊號", color="secondary", className="px-2")
        
        price_str = f"${price:,.2f}" if price else "--"
        
        # Signal types display
        st_display = ", ".join(signal_types) if signal_types else "None"
        
        rows.append(html.Tr([
            html.Td(f"#{run_id}"),
            html.Td(time_str, className="font-monospace small"),
            html.Td(price_str),
            html.Td(signal_badge),
            html.Td(html.Small(st_display, className="text-muted font-monospace"))
        ]))
    
    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Run ID / 執行編號"),
                html.Th("Time / 時間"),
                html.Th("Price / 價格"),
                html.Th("Status / 狀態"),
                html.Th("Signal Types / 訊號類型")
            ])),
            html.Tbody(rows)
        ],
        bordered=True,
        hover=True,
        size="sm",
        responsive=True,
        className="mb-0"
    )
