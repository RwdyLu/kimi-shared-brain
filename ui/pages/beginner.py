import dash
from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc
from datetime import datetime
from pathlib import Path
import json

# Register page with Dash Pages
# 使用 Dash Pages 註冊頁面
dash.register_page(__name__, path="/beginner")

# =============================================================================
# Beginner-Friendly UI / 新手友善介面
# =============================================================================
# Design: "白痴都看得懂" - only 🟢🟡🔴 and one sentence

# All 10 symbols with display info / 全部 10 個幣種
def get_coin_config():
    return [
        {"symbol": "BTCUSDT", "name": "Bitcoin", "icon": "₿"},
        {"symbol": "ETHUSDT", "name": "Ethereum", "icon": "Ξ"},
        {"symbol": "BNBUSDT", "name": "BNB", "icon": "B"},
        {"symbol": "SOLUSDT", "name": "Solana", "icon": "S"},
        {"symbol": "XRPUSDT", "name": "XRP", "icon": "X"},
        {"symbol": "ADAUSDT", "name": "Cardano", "icon": "A"},
        {"symbol": "DOGEUSDT", "name": "Dogecoin", "icon": "D"},
        {"symbol": "AVAXUSDT", "name": "Avalanche", "icon": "AV"},
        {"symbol": "LINKUSDT", "name": "Chainlink", "icon": "L"},
        {"symbol": "DOTUSDT", "name": "Polkadot", "icon": "P"},
    ]


def load_live_ranking():
    """Load live strategy ranking data / 載入即時策略排名資料"""
    try:
        ranking_file = Path(__file__).parents[2] / "state" / "live_strategy_ranking.json"
        if not ranking_file.exists():
            return {}
        with open(ranking_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def load_prices():
    """Load current prices / 載入當前價格"""
    try:
        prices_file = Path(__file__).parents[2] / "state" / "prices.json"
        if not prices_file.exists():
            return {}
        with open(prices_file, 'r') as f:
            data = json.load(f)
        return data.get("prices", {})
    except Exception:
        return {}


def get_symbol_status(symbol_data, snapshot=None):
    """
    Determine simple status for a symbol / 判斷幣種簡單狀態

    🟢 可以買 = 最新快照有 confirmed 訊號
    🟡 觀望 = 有 watch 訊號但沒有 confirmed
    🔴 不要買 = 完全沒有訊號或有反向訊號
    """
    # First check snapshot for real-time confirmed signals
    if snapshot:
        signal_types = snapshot.get("signal_types", [])
        # Filter out contrarian watch signals (they are watch-only)
        confirmed_signals = [
            s for s in signal_types
            if isinstance(s, dict) and s.get("level") == "confirmed"
            or (isinstance(s, str) and not any(watch in s for watch in ["contrarian_watch", "overheated", "oversold"]))
        ]
        watch_signals = [
            s for s in signal_types
            if isinstance(s, dict) and s.get("level") == "watch_only"
            or (isinstance(s, str) and any(watch in s for watch in ["contrarian_watch", "overheated", "oversold"]))
        ]

        if confirmed_signals:
            return {
                "emoji": "🟢",
                "text": "可以買",
                "color": "success",
                "advice": "策略訊號確認，可以考慮進場",
                "score": 100,
                "signals": confirmed_signals
            }
        elif watch_signals:
            return {
                "emoji": "🟡",
                "text": "觀望",
                "color": "warning",
                "advice": "等待確認訊號",
                "score": 50,
                "signals": watch_signals
            }

    # Fallback to ranking data if no snapshot
    strategies = symbol_data.get("strategies", [])

    has_confirmed = any(s.get("status") == "Confirmed" for s in strategies)
    has_watch = any(s.get("status") == "Watch" for s in strategies)

    if has_confirmed:
        return {
            "emoji": "🟢",
            "text": "可以買",
            "color": "success",
            "advice": "策略訊號確認，可以考慮進場",
            "score": max(s.get("score", 0) for s in strategies) * 100,
            "signals": []
        }
    elif has_watch:
        return {
            "emoji": "🟡",
            "text": "觀望",
            "color": "warning",
            "advice": "等待確認訊號",
            "score": max(s.get("score", 0) for s in strategies) * 100,
            "signals": []
        }
    else:
        return {
            "emoji": "🔴",
            "text": "不要買",
            "color": "danger",
            "advice": "目前無訊號",
            "score": 0,
            "signals": []
        }


def format_price(price):
    """Format price for display / 格式化價格顯示"""
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:.2f}"
    else:
        return f"${price:.4f}"


# ─── New Feature F: Why explanation helpers / 為什麼說明輔助函數 ───

STRATEGY_DISPLAY_NAMES = {
    "ma_cross_trend": "均線交叉趨勢",
    "ma_cross_trend_short": "均線交叉趨勢（做空）",
    "hilbert_cycle": "希爾伯特週期",
    "stochastic_breakout": "隨機指標突破",
    "rsi_trend": "RSI 趨勢",
    "bb_mean_reversion": "布林帶均值回歸",
    "ema_cross_fast": "EMA 快速交叉",
    "rsi_mid_bounce": "RSI 中位反彈",
    "volume_spike": "成交量爆量",
    "price_channel_break": "價格通道突破",
    "momentum_divergence": "動能背離",
    "contrarian_watch_overheated": "反向觀察（過熱）",
    "contrarian_watch_oversold": "反向觀察（超賣）",
    "supertrend": "Supertrend 趨勢",
    "ichimoku_cloud": "一目均衡表",
    "williams_r": "Williams %R 反轉",
    "keltner_breakout": "Keltner 通道突破",
    "atr_breakout": "ATR 波動突破",
}


STRATEGY_EXPLANATIONS = {
    "ma_cross_trend": "短期均線突破長期均線，顯示上升趨勢開始",
    "ma_cross_trend_short": "短期均線跌破長期均線，顯示下降趨勢開始",
    "hilbert_cycle": "週期指標顯示趨勢轉折點接近，可能出現方向變化",
    "stochastic_breakout": "隨機指標從超賣區反彈，顯示買盤力量增強",
    "rsi_trend": "RSI 從低點反彈，顯示買盤增加",
    "bb_mean_reversion": "價格觸及布林帶下軌，統計上可能回歸均值",
    "ema_cross_fast": "快速 EMA 突破慢速 EMA，顯示短期動能轉強",
    "rsi_mid_bounce": "RSI 從中位區反彈，顯示動能轉為正面",
    "volume_spike": "成交量異常放大，顯示市場關注度提升",
    "price_channel_break": "價格突破近期高點，顯示趨勢延續",
    "momentum_divergence": "價格與動能指標出現背離，可能預示趨勢反轉",
    "contrarian_watch_overheated": "市場可能過熱，適合觀察等待回調",
    "contrarian_watch_oversold": "市場可能超賣，適合觀察等待反彈",
    "supertrend": "ATR 趨勢指標翻多，市場進入上升趨勢",
    "ichimoku_cloud": "價格突破雲層，一目均衡表確認趨勢",
    "williams_r": "Williams %R 從超賣區反彈，短線買點出現",
    "keltner_breakout": "價格突破 Keltner 上軌，波動率突破訊號",
    "atr_breakout": "價格突破 ATR 波動範圍，動能加速",
}


def get_strategy_display_name(strategy_id: str) -> str:
    """Get Chinese strategy name / 取得中文策略名稱"""
    return STRATEGY_DISPLAY_NAMES.get(strategy_id, strategy_id)


def get_strategy_explanation(strategy_id: str) -> str:
    """Get one-sentence explanation / 取得一句話說明"""
    return STRATEGY_EXPLANATIONS.get(strategy_id, "策略訊號觸發")


def load_latest_snapshot(symbol: str) -> dict:
    """Load latest indicator snapshot for symbol / 載入該幣種最新指標快照"""
    try:
        snapshots_file = Path(__file__).parents[2] / "logs" / "indicator_snapshots.jsonl"
        if not snapshots_file.exists():
            return {}

        latest = {}
        with open(snapshots_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    snap = json.loads(line)
                    if snap.get("symbol") == symbol:
                        # Keep the latest / 保留最新的一筆
                        ts = snap.get("timestamp", "")
                        if not latest or ts > latest.get("timestamp", ""):
                            latest = snap
                except Exception:
                    continue
        return latest
    except Exception:
        return {}


# =============================================================================
# Layout / 佈局
# =============================================================================

layout = dbc.Container(
    [
        # Header / 頂部
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.H1(
                            "今天可以買什麼幣？",
                            className="text-center mb-2 fw-bold"
                        ),
                        html.P(
                            "簡單到一看就懂",
                            className="text-center text-muted mb-4"
                        ),
                        dbc.Button(
                            "切換到專業模式",
                            href="/",
                            color="outline-secondary",
                            size="sm",
                            className="mb-4"
                        )
                    ],
                    width=12
                )
            ]
        ),

        # Coin Cards Grid / 幣種卡片網格
        dbc.Row(id="beginner-coins-grid", children=[]),

        # Detail Section (hidden initially) / 詳情區塊（初始隱藏）
        html.Div(id="beginner-detail-section", children=[]),

        # Interval for auto-update / 自動更新間隔
        dcc.Interval(id="beginner-interval", interval=30000, n_intervals=0)
    ],
    fluid=True,
    className="py-4"
)


# =============================================================================
# Callbacks / 回調
# =============================================================================

@callback(
    Output("beginner-coins-grid", "children"),
    Input("beginner-interval", "n_intervals")
)
def update_beginner_grid(n):
    """Update beginner-friendly coin grid / 更新新手幣種網格"""
    ranking_data = load_live_ranking()
    prices_data = load_prices()
    symbol_scores = ranking_data.get("symbols", {})

    coins = get_coin_config()
    cards = []

    for coin in coins:
        symbol = coin["symbol"]
        name = coin["name"]
        icon = coin["icon"]

        # Get symbol data / 取得幣種資料
        symbol_data = symbol_scores.get(symbol, {"strategies": []})

        # ─── New Feature F: Why explanation / 為什麼說明 ───
        # Load latest snapshot for this symbol / 載入該幣種最新快照
        snapshot = load_latest_snapshot(symbol)
        signal_types = snapshot.get("signal_types", []) if snapshot else []
        snapshot_price = snapshot.get("price", 0) if snapshot else 0

        # Pass snapshot to status function / 傳快照給狀態函數
        status = get_symbol_status(symbol_data, snapshot)

        # Get price / 取得價格
        price_info = prices_data.get(symbol, {})
        price = price_info.get("price", 0)
        price_text = format_price(price) if price else "--"

        # Build why section / 建立為什麼區塊
        why_children = []

        if status["text"] == "可以買":
            # Confirmed signals — show strategy details
            confirmed_list = status.get("signals", signal_types)
            if confirmed_list:
                for st in confirmed_list:
                    st_id = st if isinstance(st, str) else st.get("strategy", "")
                    st_name = get_strategy_display_name(st_id)
                    st_explain = get_strategy_explanation(st_id)
                    why_children.append(
                        html.Div([
                            html.Strong(f"✅ {st_name}", className="d-block mb-1"),
                            html.Small(st_explain, className="text-muted d-block mb-2")
                        ])
                    )
            else:
                why_children.append(
                    html.Small("策略訊號確認，可以考慮進場", className="text-muted d-block")
                )

        elif status["text"] == "觀望":
            # Watch only — waiting for confirmation
            why_children.append(
                html.Small("有觀察訊號但尚未確認，建議等待", className="text-muted d-block")
            )

        else:
            # No signal / Don't buy
            why_children.append(
                html.Small("目前無訊號", className="text-muted d-block")
            )

        # Reference price, stop loss, take profit / 參考價、止損、止盈
        ref_price = snapshot_price or price or 0
        if ref_price > 0:
            stop_loss = ref_price * 0.98
            take_profit = ref_price * 1.025
            ref_display = format_price(ref_price)
            sl_display = format_price(stop_loss)
            tp_display = format_price(take_profit)
            sl_pct = "-2.0%"
            tp_pct = "+2.5%"
        else:
            ref_display = sl_display = tp_display = "--"
            sl_pct = tp_pct = ""

        # Card border color / 卡片邊框顏色
        border_color = f"border-{status['color']}"

        card = dbc.Col(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.H3(icon, className="text-center mb-2"),
                            html.H5(name, className="text-center fw-bold mb-3"),
                            html.Div(
                                f"{status['emoji']} {status['text']}",
                                className=f"text-center fs-4 fw-bold text-{status['color']} mb-3"
                            ),
                            html.H2(
                                price_text,
                                className="text-center fw-bold mb-2"
                            ),
                            html.P(
                                status['advice'],
                                className="text-center text-muted small"
                            ),

                            # ─── Why section / 為什麼區塊 ───
                            html.Hr(className="my-2"),
                            html.H6("為什麼？", className="text-center fw-bold mb-2"),
                            html.Div(why_children, className="small mb-2"),

                            # Price targets / 價格目標
                            html.Div([
                                html.Div([
                                    html.Small("進場參考: ", className="text-muted"),
                                    html.Span(ref_display, className="fw-bold")
                                ]),
                                html.Div([
                                    html.Small("建議止損: ", className="text-muted"),
                                    html.Span(sl_display, className="text-danger fw-bold"),
                                    html.Small(f" ({sl_pct})", className="text-danger") if sl_pct else None
                                ]),
                                html.Div([
                                    html.Small("建議止盈: ", className="text-muted"),
                                    html.Span(tp_display, className="text-success fw-bold"),
                                    html.Small(f" ({tp_pct})", className="text-success") if tp_pct else None
                                ]),
                            ], className="text-center small mb-2"),

                            # Disclaimer / 免責聲明
                            html.P(
                                "⚠️ 以上僅供參考，非投資建議",
                                className="text-center text-muted small mt-2 mb-0",
                                style={"fontSize": "0.75rem"}
                            ),
                        ],
                        className="text-center"
                    )
                ],
                className=f"h-100 {border_color} border-3",
                outline=True
            ),
            width=6,
            md=4,
            lg=2,
            className="mb-4"
        )
        cards.append(card)

    return cards


@callback(
    Output("beginner-detail-section", "children"),
    Input("beginner-interval", "n_intervals")
)
def update_detail_section(n):
    """Keep detail section empty for now / 詳情區塊暫時留白"""
    return html.Div()
