#!/bin/bash
# Start GitHub Issues Webhook Listener

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="/tmp/github_webhook.pid"
LOGFILE="/tmp/github_webhook.log"

start() {
    if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
        echo "Webhook listener already running (PID: $(cat $PIDFILE))"
        return 1
    fi
    
    echo "🚀 Starting GitHub Webhook Listener..."
    cd "$APP_DIR"
    nohup python3 app/github_webhook.py > "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    
    sleep 2
    if kill -0 $(cat "$PIDFILE") 2>/dev/null; then
        echo "✅ Webhook listener started (PID: $(cat $PIDFILE))"
        echo "   Endpoint: http://localhost:5000/webhook"
        echo "   Logs:     $LOGFILE"
    else
        echo "❌ Failed to start webhook listener"
        rm -f "$PIDFILE"
        return 1
    fi
}

stop() {
    if [ ! -f "$PIDFILE" ]; then
        echo "Webhook listener not running"
        return 1
    fi
    
    PID=$(cat "$PIDFILE")
    echo "🛑 Stopping webhook listener (PID: $PID)..."
    kill "$PID" 2>/dev/null
    rm -f "$PIDFILE"
    echo "✅ Stopped"
}

status() {
    if [ -f "$PIDFILE" ] && kill -0 $(cat "$PIDFILE") 2>/dev/null; then
        echo "✅ Webhook listener is running (PID: $(cat $PIDFILE))"
        echo "   Endpoint: http://localhost:5000/webhook"
        echo "   Logs:     $LOGFILE"
    else
        echo "❌ Webhook listener is not running"
        rm -f "$PIDFILE" 2>/dev/null
    fi
}

case "${1:-start}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
