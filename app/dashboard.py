"""
Trading Dashboard UI
Web-based trading monitoring dashboard with real-time updates.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class DashboardUI:
    """
    Trading dashboard UI generator.
    Creates HTML dashboard with trading metrics and status.
    """

    def __init__(self, title: str = "Trading Dashboard"):
        self.logger = logging.getLogger(__name__)
        self.title = title
        self.components: List[Dict] = []
        self.refresh_interval = 30  # seconds

        self.logger.info("DashboardUI initialized")

    def add_component(self, component_type: str, config: Dict):
        """Add dashboard component."""
        self.components.append({"type": component_type, "config": config})

    def generate_html(self) -> str:
        """Generate complete HTML dashboard."""
        html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e1a;
            color: #e0e0e0;
            padding: 20px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid #1a2332;
        }}
        .header h1 {{
            font-size: 24px;
            color: #00d4aa;
            font-weight: 600;
        }}
        .status {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}
        .status-badge {{
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
        }}
        .status-healthy {{ background: #00d4aa20; color: #00d4aa; }}
        .status-warning {{ background: #f59e0b20; color: #f59e0b; }}
        .status-critical {{ background: #ef444420; color: #ef4444; }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: #111827;
            border: 1px solid #1a2332;
            border-radius: 12px;
            padding: 20px;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .card-title {{
            font-size: 14px;
            font-weight: 600;
            color: #9ca3af;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .card-value {{
            font-size: 32px;
            font-weight: 700;
            color: #f0f0f0;
        }}
        .card-change {{
            font-size: 14px;
            margin-top: 4px;
        }}
        .positive {{ color: #00d4aa; }}
        .negative {{ color: #ef4444; }}
        
        .trade-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .trade-table th {{
            text-align: left;
            padding: 12px;
            font-size: 12px;
            color: #9ca3af;
            text-transform: uppercase;
            border-bottom: 1px solid #1a2332;
        }}
        .trade-table td {{
            padding: 12px;
            font-size: 13px;
            border-bottom: 1px solid #1a2332;
        }}
        .trade-table tr:hover {{
            background: #1a2332;
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-buy {{ background: #00d4aa20; color: #00d4aa; }}
        .badge-sell {{ background: #ef444420; color: #ef4444; }}
        .badge-open {{ background: #3b82f620; color: #3b82f6; }}
        .badge-closed {{ background: #6b728020; color: #6b7280; }}
        
        .progress-bar {{
            width: 100%;
            height: 6px;
            background: #1a2332;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 8px;
        }}
        .progress-fill {{
            height: 100%;
            background: #00d4aa;
            border-radius: 3px;
            transition: width 0.3s ease;
        }}
        
        .timestamp {{
            font-size: 11px;
            color: #6b7280;
            margin-top: 20px;
            text-align: right;
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        .live-indicator {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #00d4aa;
            border-radius: 50%;
            animation: pulse 2s infinite;
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 {self.title}</h1>
        <div class="status">
            <span class="live-indicator"></span>
            <span class="status-badge status-healthy">● 系統正常</span>
            <span style="font-size: 11px; color: #6b7280;">
                更新: <span id="last-update">--:--:--</span>
            </span>
        </div>
    </div>
    
    <!-- Key Metrics -->
    <div class="grid">
        <div class="card">
            <div class="card-header">
                <span class="card-title">今日盈虧</span>
            </div>
            <div class="card-value positive">+$1,234.56</div>
            <div class="card-change positive">+2.45%</div>
        </div>
        <div class="card">
            <div class="card-header">
                <span class="card-title">未平倉 P&L</span>
            </div>
            <div class="card-value negative">-$456.78</div>
            <div class="card-change negative">-1.23%</div>
        </div>
        <div class="card">
            <div class="card-header">
                <span class="card-title">勝率</span>
            </div>
            <div class="card-value">65.2%</div>
            <div class="card-change">13 勝 / 7 敗</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 65.2%"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-header">
                <span class="card-title">帳戶餘額</span>
            </div>
            <div class="card-value">$52,431.89</div>
            <div class="card-change positive">+$2,431.89 (本月)</div>
        </div>
    </div>
    
    <!-- Active Trades -->
    <div class="card" style="margin-bottom: 16px;">
        <div class="card-header">
            <span class="card-title">📈 進行中交易</span>
            <span class="badge badge-open">2 活躍</span>
        </div>
        <table class="trade-table">
            <thead>
                <tr>
                    <th>交易對</th>
                    <th>方向</th>
                    <th>倉位大小</th>
                    <th>入場價</th>
                    <th>當前價</th>
                    <th>未實現 P&L</th>
                    <th>狀態</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>BTCUSDT</strong></td>
                    <td><span class="badge badge-buy">買入</span></td>
                    <td>0.5 BTC</td>
                    <td>$45,000.00</td>
                    <td>$47,500.00</td>
                    <td class="positive">+$1,250.00</td>
                    <td><span class="badge badge-open">持有中</span></td>
                </tr>
                <tr>
                    <td><strong>ETHUSDT</strong></td>
                    <td><span class="badge badge-sell">賣出</span></td>
                    <td>2.0 ETH</td>
                    <td>$3,200.00</td>
                    <td>$3,150.00</td>
                    <td class="positive">+$100.00</td>
                    <td><span class="badge badge-open">持有中</span></td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <!-- Recent Trades -->
    <div class="card" style="margin-bottom: 16px;">
        <div class="card-header">
            <span class="card-title">📝 最近成交</span>
            <span class="badge badge-closed">5 筆</span>
        </div>
        <table class="trade-table">
            <thead>
                <tr>
                    <th>時間</th>
                    <th>交易對</th>
                    <th>方向</th>
                    <th>入場價</th>
                    <th>出場價</th>
                    <th>已實現 P&L</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>10:30:15</td>
                    <td><strong>BTCUSDT</strong></td>
                    <td><span class="badge badge-buy">買入</span></td>
                    <td>$45,000</td>
                    <td>$47,500</td>
                    <td class="positive">+$2,500</td>
                </tr>
                <tr>
                    <td>09:15:22</td>
                    <td><strong>ETHUSDT</strong></td>
                    <td><span class="badge badge-sell">賣出</span></td>
                    <td>$3,300</td>
                    <td>$3,150</td>
                    <td class="positive">+$300</td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <!-- Strategy Performance -->
    <div class="card" style="margin-bottom: 16px;">
        <div class="card-header">
            <span class="card-title">🤖 策略表現</span>
        </div>
        <table class="trade-table">
            <thead>
                <tr>
                    <th>策略</th>
                    <th>交易次數</th>
                    <th>勝率</th>
                    <th>總 P&L</th>
                    <th>狀態</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>BTC_4H_MA</strong></td>
                    <td>15</td>
                    <td>73.3%</td>
                    <td class="positive">+$5,230</td>
                    <td><span class="badge badge-open">運行中</span></td>
                </tr>
                <tr>
                    <td><strong>ETH_1H_RSI</strong></td>
                    <td>8</td>
                    <td>50.0%</td>
                    <td class="negative">-$450</td>
                    <td><span class="badge badge-open">運行中</span></td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <!-- System Health -->
    <div class="card">
        <div class="card-header">
            <span class="card-title">💓 系統健康</span>
        </div>
        <table class="trade-table">
            <thead>
                <tr>
                    <th>指標</th>
                    <th>數值</th>
                    <th>狀態</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>CPU 使用率</td>
                    <td>45%</td>
                    <td><span class="badge status-healthy">正常</span></td>
                </tr>
                <tr>
                    <td>記憶體使用</td>
                    <td>62%</td>
                    <td><span class="badge status-healthy">正常</span></td>
                </tr>
                <tr>
                    <td>WebSocket 連線</td>
                    <td>已連線</td>
                    <td><span class="badge status-healthy">正常</span></td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <div class="timestamp">
        最後更新: <span id="footer-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
    </div>
    
    <script>
        function updateTime() {{
            const now = new Date();
            const timeStr = now.toTimeString().split(' ')[0];
            document.getElementById('last-update').textContent = timeStr;
            document.getElementById('footer-time').textContent = 
                now.toLocaleString('zh-TW');
        }}
        
        updateTime();
        setInterval(updateTime, {self.refresh_interval * 1000});
    </script>
</body>
</html>"""

        return html

    def save_dashboard(self, filepath: str):
        """Save dashboard to HTML file."""
        html = self.generate_html()

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        self.logger.info(f"Dashboard saved to {filepath}")

    def update_data(self, data: Dict):
        """Update dashboard with live data."""
        self.logger.info("Dashboard data updated")
        # In practice, this would update the dashboard components
        # For now, placeholder for future websocket integration

    def get_dashboard_info(self) -> Dict:
        """Get dashboard configuration info."""
        return {
            "title": self.title,
            "components": len(self.components),
            "refresh_interval": self.refresh_interval,
            "last_updated": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    dashboard = DashboardUI("Trading Dashboard")

    # Generate and save
    dashboard.save_dashboard("dashboard.html")

    print("Dashboard UI Demo")
    print("=" * 50)
    print(f"Title: {dashboard.title}")
    print(f"Components: {len(dashboard.components)}")
    print(f"Refresh: {dashboard.refresh_interval}s")
    print(f"\nInfo: {dashboard.get_dashboard_info()}")
    print("\nDashboard saved to: dashboard.html")
