#!/usr/bin/env python3
"""
Simple Web UI Server for Trading Monitor
轻量级 Web UI 服务器，提供手机和桌面访问
"""

import json
import os
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / "state"
LOGS_DIR = BASE_DIR / "logs"
WEB_DIR = BASE_DIR / "web"


@app.route("/")
def index():
    """Serve the main UI page"""
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/api/prices")
def api_prices():
    """Return latest prices from prices.json"""
    try:
        prices_file = STATE_DIR / "prices.json"
        if not prices_file.exists():
            return jsonify([])

        with open(prices_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = []
        for symbol, info in data.get("prices", {}).items():
            result.append(
                {
                    "symbol": symbol,
                    "price": info.get("price", 0),
                    "change_24h": info.get("change_24h", 0),
                    "volume": info.get("volume", 0),
                    "timestamp": info.get("timestamp", ""),
                }
            )
        return jsonify(sorted(result, key=lambda x: x["symbol"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies")
def api_strategies():
    """Return strategy status from strategies.json"""
    try:
        config_file = BASE_DIR / "config" / "strategies.json"
        if not config_file.exists():
            return jsonify([])

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        strategies = []
        for s in data.get("strategies", []):
            strategies.append(
                {
                    "id": s.get("id", ""),
                    "enabled": s.get("enabled", False),
                    "type": s.get("type", ""),
                    "source": s.get("source", ""),
                }
            )
        return jsonify(strategies)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/paper")
def api_paper():
    """Return paper trading summary"""
    try:
        state_file = STATE_DIR / "paper_trading_state.json"
        if not state_file.exists():
            return jsonify({})

        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        strategies = data.get("strategies", {})
        total_balance = sum(acc.get("balance", 0) for acc in strategies.values())
        total_initial = sum(acc.get("initial", 1000) for acc in strategies.values())
        total_pnl = total_balance - total_initial
        pnl_pct = (total_pnl / total_initial * 100) if total_initial > 0 else 0

        # Collect positions
        positions = []
        for sid, acc in strategies.items():
            for sym, pos_list in acc.get("positions", {}).items():
                if pos_list:
                    for pos in pos_list:
                        if isinstance(pos, dict):
                            positions.append(
                                {
                                    "symbol": pos.get("symbol", sym),
                                    "strategy": sid,
                                    "side": pos.get("side", ""),
                                    "quantity": pos.get("quantity", 0),
                                    "entry_price": pos.get("entry_price", 0),
                                    "entry_time": pos.get("entry_time", ""),
                                    "unrealized_pnl": 0,  # Would need current price to calculate
                                }
                            )

        return jsonify(
            {
                "current_balance": total_balance,
                "total_initial": total_initial,
                "total_pnl": total_pnl,
                "pnl_pct": pnl_pct,
                "open_positions": len(positions),
                "positions": positions,
                "strategy_count": len(strategies),
                "enabled_count": sum(
                    1 for acc in strategies.values() if acc.get("balance", 0) > 0
                ),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/screening")
def api_screening():
    """Return latest screening results"""
    try:
        screening_file = STATE_DIR / "screening_results.json"
        if not screening_file.exists():
            return jsonify([])

        with open(screening_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        coins = data.get("coins", [])
        return jsonify(
            {
                "timestamp": data.get("timestamp", ""),
                "count": len(coins),
                "coins": coins[:20],  # Limit to top 20
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/status")
def api_status():
    """Return system status"""
    try:
        # Check scheduler log for latest run
        log_file = LOGS_DIR / "scheduler.log"
        latest_run = "Unknown"
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    if "Run #" in line and "completed" in line:
                        latest_run = line.strip()
                        break

        # Check if prices are fresh
        prices_file = STATE_DIR / "prices.json"
        prices_fresh = False
        if prices_file.exists():
            import time

            mtime = prices_file.stat().st_mtime
            age_minutes = (time.time() - mtime) / 60
            prices_fresh = age_minutes < 10

        return jsonify(
            {
                "status": "running" if prices_fresh else "stale",
                "prices_fresh": prices_fresh,
                "latest_run": latest_run,
                "server_time": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Use port 8080 by default
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Trading Monitor UI on http://0.0.0.0:{port}")
    print(f"📱 Mobile access: http://YOUR_SERVER_IP:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
