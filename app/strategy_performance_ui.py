"""
Strategy Performance UI
Displays strategy performance metrics and comparison dashboard.
"""
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


class StrategyPerformanceUI:
    """
    Strategy performance visualization UI.
    Generates HTML report for strategy comparison and analysis.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("StrategyPerformanceUI initialized")
    
    def generate_report(self,
                       strategies: List[Dict],
                       period: str = "30d") -> str:
        """
        Generate strategy performance HTML report.
        
        Args:
            strategies: List of strategy performance data
            period: Reporting period
            
        Returns:
            HTML string
        """
        html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy Performance</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e1a;
            color: #e0e0e0;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #1a2332;
        }}
        .header h1 {{
            font-size: 28px;
            color: #00d4aa;
            margin-bottom: 8px;
        }}
        .header p {{
            color: #6b7280;
            font-size: 14px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: #111827;
            border: 1px solid #1a2332;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }}
        .summary-card h3 {{
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}
        .summary-card .value {{
            font-size: 24px;
            font-weight: 700;
        }}
        .positive {{ color: #00d4aa; }}
        .negative {{ color: #ef4444; }}
        
        .strategy-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        .strategy-table th {{
            text-align: left;
            padding: 14px;
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            border-bottom: 2px solid #1a2332;
        }}
        .strategy-table td {{
            padding: 14px;
            font-size: 14px;
            border-bottom: 1px solid #1a2332;
        }}
        .strategy-table tr:hover {{
            background: #1a2332;
        }}
        .strategy-name {{
            font-weight: 600;
            color: #f0f0f0;
        }}
        .status-badge {{
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
        }}
        .status-active {{ background: #00d4aa20; color: #00d4aa; }}
        .status-paused {{ background: #f59e0b20; color: #f59e0b; }}
        .status-stopped {{ background: #ef444420; color: #ef4444; }}
        
        .chart-bar {{
            height: 6px;
            background: #1a2332;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 4px;
        }}
        .chart-fill {{
            height: 100%;
            border-radius: 3px;
        }}
        .fill-green {{ background: #00d4aa; }}
        .fill-red {{ background: #ef4444; }}
        .fill-yellow {{ background: #f59e0b; }}
        
        .footer {{
            margin-top: 40px;
            text-align: center;
            color: #6b7280;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Strategy Performance Report</h1>
        <p>Period: {period} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
    
    <div class="summary-grid">
        <div class="summary-card">
            <h3>Active Strategies</h3>
            <div class="value positive">{len([s for s in strategies if s.get('status') == 'active'])}</div>
        </div>
        <div class="summary-card">
            <h3>Total P&L</h3>
            <div class="value {'positive' if sum(s.get('total_pnl', 0) for s in strategies) > 0 else 'negative'}">
                ${sum(s.get('total_pnl', 0) for s in strategies):,.2f}
            </div>
        </div>
        <div class="summary-card">
            <h3>Avg Win Rate</h3>
            <div class="value">
                {sum(s.get('win_rate', 0) for s in strategies) / len(strategies) if strategies else 0:.1f}%
            </div>
        </div>
        <div class="summary-card">
            <h3>Total Trades</h3>
            <div class="value">{sum(s.get('total_trades', 0) for s in strategies)}</div>
        </div>
    </div>
    
    <table class="strategy-table">
        <thead>
            <tr>
                <th>Strategy</th>
                <th>Status</th>
                <th>Trades</th>
                <th>Win Rate</th>
                <th>Profit Factor</th>
                <th>Max Drawdown</th>
                <th>Total P&L</th>
                <th>Sharpe</th>
            </tr>
        </thead>
        <tbody>
            {self._generate_rows(strategies)}
        </tbody>
    </table>
    
    <div class="footer">
        <p>Trading System v2.0 | Strategy Analytics Module</p>
    </div>
</body>
</html>"""
        
        return html
    
    def _generate_rows(self, strategies: List[Dict]) -> str:
        """Generate table rows for strategies."""
        rows = []
        
        for s in sorted(strategies, key=lambda x: x.get('total_pnl', 0), reverse=True):
            status = s.get('status', 'unknown')
            status_class = f"status-{status}"
            status_text = status.upper()
            
            pnl = s.get('total_pnl', 0)
            pnl_class = 'positive' if pnl > 0 else 'negative'
            
            win_rate = s.get('win_rate', 0)
            win_color = 'fill-green' if win_rate > 50 else 'fill-red'
            
            drawdown = s.get('max_drawdown', 0)
            dd_color = 'fill-red' if drawdown > 20 else 'fill-yellow' if drawdown > 10 else 'fill-green'
            
            row = f"""
            <tr>
                <td>
                    <div class="strategy-name">{s.get('name', 'Unknown')}</div>
                    <div style="font-size: 11px; color: #6b7280;">{s.get('symbol', '')} | {s.get('timeframe', '')}</div>
                </td>
                <td><span class="status-badge {status_class}">{status_text}</span></td>
                <td>{s.get('total_trades', 0)}</td>
                <td>
                    {win_rate:.1f}%
                    <div class="chart-bar"><div class="chart-fill {win_color}" style="width: {win_rate}%"></div></div>
                </td>
                <td>{s.get('profit_factor', 0):.2f}</td>
                <td>
                    {drawdown:.1f}%
                    <div class="chart-bar"><div class="chart-fill {dd_color}" style="width: {min(drawdown, 100)}%"></div></div>
                </td>
                <td class="{pnl_class}">${pnl:,.2f}</td>
                <td>{s.get('sharpe_ratio', 0):.2f}</td>
            </tr>"""
            
            rows.append(row)
        
        return "\n".join(rows)
    
    def save_report(self, filepath: str, strategies: List[Dict], period: str = "30d"):
        """Save performance report to HTML file."""
        html = self.generate_report(strategies, period)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self.logger.info(f"Strategy report saved to {filepath}")


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    ui = StrategyPerformanceUI()
    
    # Sample data
    strategies = [
        {
            'name': 'BTC_4H_MA',
            'symbol': 'BTCUSDT',
            'timeframe': '4H',
            'status': 'active',
            'total_trades': 45,
            'win_rate': 73.3,
            'profit_factor': 2.1,
            'max_drawdown': 8.5,
            'total_pnl': 5230.50,
            'sharpe_ratio': 1.8,
        },
        {
            'name': 'ETH_1H_RSI',
            'symbol': 'ETHUSDT',
            'timeframe': '1H',
            'status': 'active',
            'total_trades': 28,
            'win_rate': 50.0,
            'profit_factor': 1.2,
            'max_drawdown': 15.2,
            'total_pnl': -450.25,
            'sharpe_ratio': 0.3,
        },
        {
            'name': 'SOL_1D_BB',
            'symbol': 'SOLUSDT',
            'timeframe': '1D',
            'status': 'paused',
            'total_trades': 12,
            'win_rate': 41.7,
            'profit_factor': 0.8,
            'max_drawdown': 22.1,
            'total_pnl': -1230.00,
            'sharpe_ratio': -0.5,
        },
    ]
    
    ui.save_report("strategy_performance.html", strategies)
    
    print("Strategy Performance UI Demo")
    print("=" * 50)
    print(f"Strategies: {len(strategies)}")
    print(f"Active: {len([s for s in strategies if s['status'] == 'active'])}")
    print(f"Report saved to: strategy_performance.html")
