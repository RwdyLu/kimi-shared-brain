#!/bin/bash
# V2 基因引擎啟動腳本

cd "$(dirname "$0")/../.." || exit 1

APP_DIR="app/genetic_engine"
SAVE_DIR="data/genetic_evolution_v2"

# 確保保存目錄存在
mkdir -p "$SAVE_DIR"

echo "═══════════════════════════════════════════════════════"
echo "  Genetic Engine V2 Launcher"
echo "═══════════════════════════════════════════════════════"
echo ""

# 顯示幫助
show_help() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  evolution    單輪演化 (默認 20 代, 50 個體)"
    echo "  continuous   持續演化模式 (每 6 小時一輪)"
    echo "  quick-test   快速測試 (3 代, 5 個體, 7 天數據)"
    echo "  evaluate     評估指定策略"
    echo "  deploy       部署最佳策略到 Paper Trading"
    echo "  archive      檔案館操作"
    echo ""
    echo "Examples:"
    echo "  $0 evolution --generations 30 --population 40"
    echo "  $0 continuous --interval 4 --live-pool 5"
    echo "  $0 quick-test"
    echo ""
}

# 解析命令
CMD="${1:-evolution}"
shift || true

case "$CMD" in
    help|--help|-h)
        show_help
        exit 0
        ;;
    
    evolution)
        echo "🧬 啟動 V2 單輪演化..."
        python3 -m "$APP_DIR" v2 evolution "$@"
        ;;
    
    continuous)
        echo "🔄 啟動 V2 持續演化..."
        nohup python3 -m "$APP_DIR" v2 continuous "$@" > "$SAVE_DIR/continuous.log" 2>&1 &
        PID=$!
        echo $PID > "$SAVE_DIR/continuous.pid"
        echo "✅ 已啟動 (PID: $PID)"
        echo "   日誌: $SAVE_DIR/continuous.log"
        ;;
    
    quick-test)
        echo "⚡ 快速測試模式 (3 代, 5 個體, 7 天)..."
        python3 -m "$APP_DIR" v2 evolution \
            --generations 3 \
            --population 5 \
            --days 7 \
            --symbols "BTCUSDT,ETHUSDT" \
            "$@"
        ;;
    
    evaluate)
        echo "🔬 評估策略..."
        python3 -m "$APP_DIR" v2 evaluate "$@"
        ;;
    
    deploy)
        echo "📋 部署策略..."
        python3 -m "$APP_DIR" v2 deploy "$@"
        ;;
    
    archive)
        echo "📋 檔案館..."
        python3 -m "$APP_DIR" v2 archive "$@"
        ;;
    
    stop)
        if [ -f "$SAVE_DIR/continuous.pid" ]; then
            PID=$(cat "$SAVE_DIR/continuous.pid")
            if kill -0 "$PID" 2>/dev/null; then
                echo "🛑 停止持續演化 (PID: $PID)..."
                kill "$PID"
                rm "$SAVE_DIR/continuous.pid"
                echo "✅ 已停止"
            else
                echo "⚠️ 進程已不存在"
                rm -f "$SAVE_DIR/continuous.pid"
            fi
        else
            echo "⚠️ 未找到運行中的持續演化進程"
        fi
        ;;
    
    status)
        echo "📊 V2 狀態..."
        echo "   保存目錄: $SAVE_DIR"
        if [ -f "$SAVE_DIR/continuous.pid" ]; then
            PID=$(cat "$SAVE_DIR/continuous.pid")
            if kill -0 "$PID" 2>/dev/null; then
                echo "   持續演化: 運行中 (PID: $PID)"
            else
                echo "   持續演化: 已停止"
            fi
        else
            echo "   持續演化: 未啟動"
        fi
        
        # 顯示最新結果
        if [ -d "$SAVE_DIR" ]; then
            BEST=$(ls -t "$SAVE_DIR"/best_strategy_*.json 2>/dev/null | head -1)
            if [ -n "$BEST" ]; then
                echo "   最新策略: $(basename "$BEST")"
            fi
            
            HISTORY=$(ls -t "$SAVE_DIR"/history_*.json 2>/dev/null | head -1)
            if [ -n "$HISTORY" ]; then
                echo "   最新歷史: $(basename "$HISTORY")"
            fi
        fi
        ;;
    
    *)
        echo "❌ 未知命令: $CMD"
        show_help
        exit 1
        ;;
esac
