#!/usr/bin/env python3
"""
Simple Dashboard / 簡易看板

Lightweight real-time price dashboard for all 10 coins.
輕量級即時價格看板，顯示全部 10 個幣種。

Port: 8081
"""

import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dash import Dash, html, dcc, Input, Output
import dash_bootstrap_components as dbc

# ── Config ──────────────────────────────────────────────
COINS = [
    ("BTCUSDT", "Bitcoin", "BTC"),
    ("ETHUSDT", "Ethereum", "ETH"),
    ("BNBUSDT", "BNB", "BNB"),
    ("SOLUSDT", "Solana", "SOL"),
    ("XRPUSDT", "Ripple", "XRP"),
    ("ADAUSDT", "Cardano", "ADA"),
    ("DOGEUSDT", "Dogecoin", "DOGE"),
    ("AVAXUSDT", "Avalanche", "AVAX"),
    ("LINKUSDT", "Chainlink", "LINK"),
    ("DOTUSDT", "Polkadot", "DOT"),
]

REFRESH_SECONDS = 30

# ── Helpers ─────────────────────────────────────────────
def fetch_all_prices():
    """Fetch real-time prices for all 10 coins from Binance."""
    prices = {}
    for symbol, name, short in COINS:
        try:
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                prices[short] = {
                    "symbol": symbol,
                    "name": name,
                    "price": float(data.get("lastPrice", 0)),
                    "change_pct": float(data.get("priceChangePercent", 0)),
                    "high": float(data.get("highPrice", 0)),
                    "low": float(data.get("lowPrice", 0)),
                    "volume": float(data.get("volume", 0)),
                }
        except Exception:
            prices[short] = None
    return prices


def get_scheduler_status():
    """Check if scheduler is running via PID file."""
    try:
        pid_file = Path("state/.monitor.pid")
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            if pid:
                import os
                os.kill(int(pid), 0)  # Check process exists
                return True
    except Exception:
        pass
    return False


def get_paper_balance():
    """Parse latest paper balance from scheduler log."""
    try:
        log_path = Path("logs/scheduler.log")
        if not log_path.exists():
            return None
        lines = log_path.read_text().splitlines()
        for line in reversed(lines[-500:]):
            if "Paper Balance:" in line:
                # Extract number after $ sign
                import re
                m = re.search(r"\$([\d,.]+)", line)
                if m:
                    return m.group(1).replace(",", "")
    except Exception:
        pass
    return None


def get_recent_trades():
    """Parse last 5 paper trades from scheduler log."""
    trades = []
    try:
        log_path = Path("logs/scheduler.log")
        if not log_path.exists():
            return trades
        lines = log_path.read_text().splitlines()
        for line in reversed(lines[-1000:]):
            if "PAPER TRADE" in line or "✅ PAPER TRADE" in line:
                trades.append(line.strip())
                if len(trades) >= 5:
                    break
    except Exception:
        pass
    return list(reversed(trades))


# ── Dash App ────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
)
app.title = "Trading Monitor"


# Price card builder
def price_card(short, data):
    if data is None:
        return dbc.Card(
            dbc.CardBody([
                html.H5(short, className="card-title text-muted"),
                html.P("--", className="text-muted"),
            ]),
            className="h-100",
            style={"backgroundColor": "#2a2a2a"},
        )

    price = data["price"]
    change = data["change_pct"]
    color = "success" if change >= 0 else "danger"
    arrow = "▲" if change >= 0 else "▼"

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Strong(data["name"], className="text-light"),
                html.Small(f" ({short})", className="text-muted ms-1"),
            ]),
            html.H4(
                f"${price:,.2f}",
                className=f"text-{color} mt-2 mb-1",
                style={"fontFamily": "monospace"},
            ),
            html.Div([
                html.Span(f"{arrow} {change:+.2f}%", className=f"text-{color} small"),
                html.Br(),
                html.Small(
                    f"H: ${data['high']:,.2f}  L: ${data['low']:,.2f}",
                    className="text-muted",
                ),
            ]),
        ]),
        className="h-100",
        style={"backgroundColor": "#1e1e1e", "border": "1px solid #333"},
    )


# Layout
app.layout = dbc.Container(
    [
        # Header
        dbc.Row(
            dbc.Col(
                html.H2([
                    html.Span("📊 ", className="me-2"),
                    "Trading Monitor",
                    html.Small(" Simple", className="text-muted ms-2"),
                ], className="mt-4 mb-3 text-light")
            )
        ),

        # Status bar
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        dbc.Row([
                            dbc.Col([
                                html.Strong("System Status", className="text-muted small"),
                                html.Div(id="status-display", children="Checking..."),
                            ], width=4),
                            dbc.Col([
                                html.Strong("Paper Balance", className="text-muted small"),
                                html.Div(id="balance-display", children="--"),
                            ], width=4),
                            dbc.Col([
                                html.Strong("Last Update", className="text-muted small"),
                                html.Div(id="update-time", children="--"),
                            ], width=4),
                        ])
                    ),
                    style={"backgroundColor": "#1e1e1e", "border": "1px solid #333"},
                    className="mb-4",
                )
            )
        ),

        # Price grid (10 cards)
        dbc.Row(
            [
                dbc.Col(price_card(short, None), width=6, md=4, lg=2, className="mb-3", id=f"card-{short}")
                for _, _, short in COINS
            ],
            id="price-grid"
        ),

        # Recent trades
        dbc.Row(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader("Recent Paper Trades", className="text-light"),
                        dbc.CardBody(
                            html.Div(id="trades-list", children=[
                                html.P("No trades yet", className="text-muted")
                            ]),
                        ),
                    ],
                    style={"backgroundColor": "#1e1e1e", "border": "1px solid #333"},
                    className="mt-4",
                )
            )
        ),

        # Auto refresh
        dcc.Interval(id="refresh-interval", interval=REFRESH_SECONDS * 1000),

    ],
    fluid=True,
    style={"backgroundColor": "#121212", "minHeight": "100vh"},
)


# ── Callback ──────────────────────────────────────────────
@app.callback(
    [
        Output("status-display", "children"),
        Output("balance-display", "children"),
        Output("update-time", "children"),
        Output("price-grid", "children"),
        Output("trades-list", "children"),
    ],
    Input("refresh-interval", "n_intervals"),
)
def update_all(n):
    # Status
    running = get_scheduler_status()
    status = dbc.Badge("🟢 Running", color="success") if running else dbc.Badge("🔴 Stopped", color="danger")

    # Balance
    bal = get_paper_balance()
    balance = html.H5(f"${float(bal):,.2f}", className="text-info") if bal else html.P("--", className="text-muted")

    # Time
    now = datetime.now().strftime("%H:%M:%S")

    # Prices
    prices = fetch_all_prices()
    cards = [
        dbc.Col(price_card(short, prices.get(short)), width=6, md=4, lg=2, className="mb-3")
        for _, _, short in COINS
    ]

    # Trades
    trades = get_recent_trades()
    if trades:
        trades_ui = html.Ul([
            html.Li(
                html.Small(t, className="text-light font-monospace"),
                className="mb-1",
                style={"borderBottom": "1px solid #333", "paddingBottom": "4px"},
            )
            for t in trades
        ], className="list-unstyled")
    else:
        trades_ui = html.P("No paper trades recorded yet", className="text-muted")

    return status, balance, now, cards, trades_ui


# ── Main ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("Simple Trading Monitor")
    print("=" * 60)
    print(f"\nAccess: http://localhost:8081")
    print(f"Coins: {[s for _, _, s in COINS]}")
    print(f"Refresh: every {REFRESH_SECONDS}s")
    print("\nCtrl+C to stop\n")
    app.run(host="0.0.0.0", port=8081, debug=False, use_reloader=False)
