#!/bin/bash
"""
Start Crypto Monitor Service
啟動幣種監控服務
"""

echo "🔍 Starting Crypto Opportunity Monitor..."
echo "=================================="

# Create logs directory
mkdir -p logs

# Run initial screening
echo "Running initial screening..."
cd /root/.openclaw/workspace/kimi-shared-brain
python3 scripts/crypto_monitor.py

echo ""
echo "✅ Crypto monitor cron job installed!"
echo "   Schedule: Every hour at :00"
echo "   Log file: logs/crypto_monitor.log"
echo "   Results: state/screening_results.json"
echo "   History: state/screening_history.json"
echo ""
echo "To check status:"
echo "   crontab -l"
echo "To view logs:"
echo "   tail -f logs/crypto_monitor.log"
echo "To stop:"
echo "   crontab -r"
