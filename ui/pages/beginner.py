import dash
from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc
from datetime import datetime
from pathlib import Path
import json

# =============================================================================
# Beginner-Friendly UI / 新手友善介面
# =============================================================================
# Design: "白痴都看得懂" — only 🟢🟡🔴 and one sentence

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
        ranking_file = Path("/tmp/kimi-shared-brain/state/live_strategy_ranking.json")
        if not ranking_file.exists():
            return {}
        with open(ranking_file, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def load_prices():
    """Load current prices / 載入當前價格"""
    try:
        prices_file = Path("/tmp/kimi-shared-brain/state/prices.json")
        if not prices_file.exists():
            return {}
        with open(prices_file, 'r') as f:
            data = json.load(f)
        return data.get("prices", {})
    except Exception:
        return {}


def get_symbol_status(symbol_data):
    """
    Determine simple status for a symbol / 判斷幣種簡單狀態
    🟢 Buy = has Confirmed signals
    🟡 Wait = has Watch signals only
    🔴 Don't Buy = all Idle
    """
    strategies = symbol_data.get("strategies", [])
    
    has_confirmed = any(s.get("status") == "Confirmed" for s in strategies)
    has_watch = any(s.get("status") == "Watch" for s in strategies)
    
    if has_confirmed:
        return {
            "emoji": "🟢",
            "text": "可以買",
            "color": "success",
            "advice": "策略訊號確認，可以考慮進場",
            "score": max(s.get("score", 0) for s in strategies) * 100
        }
    elif has_watch:
        return {
            "emoji": "🟡",
            "text": "再等等",
            "color": "warning",
            "advice": "有觀察訊號，但還不夠強",
            "score": max(s.get("score", 0) for s in strategies) * 100
        }
    else:
        return {
            "emoji": "🔴",
            "text": "不要買",
            "color": "danger",
            "advice": "沒有訊號，先觀察",
            "score": 0
        }


def format_price(price):
    """Format price for display / 格式化價格顯示"""
    if price >= 1000:
        return f"${price:,.0f}"
    elif price >= 1:
        return f"${price:.2f}"
    else:
        return f"${price:.4f}"


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
        status = get_symbol_status(symbol_data)
        
        # Get price / 取得價格
        price_info = prices_data.get(symbol, {})
        price = price_info.get("price", 0)
        price_text = format_price(price) if price else "--"
        
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
                            html.Div(
                                dbc.Button(
                                    "看詳情",
                                    id=f"btn-{symbol}",
                                    color=status['color'],
                                    size="sm",
                                    className="w-100 mt-2"
                                ),
                                className="d-grid"
                            )
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
