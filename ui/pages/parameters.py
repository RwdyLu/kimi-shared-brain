"""
Parameters Page / 參數頁面

View and edit monitoring parameters.
查看與編輯監測參數。
"""

import dash
from dash import dcc, html, callback, Output, Input, State
import dash_bootstrap_components as dbc
import sys
import json

sys.path.insert(0, '/tmp/kimi-shared-brain')

# Register page / 註冊頁面
dash.register_page(__name__, path="/parameters", title="Parameters")

# Load initial config / 載入初始配置
def load_monitoring_params():
    """Load monitoring parameters from config"""
    try:
        from config.loader import get_monitoring_params
        return get_monitoring_params()
    except Exception as e:
        return {"error": str(e)}


# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Parameters", className="mb-4"),
        html.P("View and edit monitoring parameters / 查看與編輯監測參數", className="text-muted"),
        
        html.Hr(),
        
        # Category tabs / 類別標籤
        dbc.Tabs(
            [
                dbc.Tab(label="General / 一般", tab_id="tab-general"),
                dbc.Tab(label="Indicators / 指標", tab_id="tab-indicators"),
                dbc.Tab(label="Signals / 訊號", tab_id="tab-signals"),
                dbc.Tab(label="Notifications / 通知", tab_id="tab-notifications"),
                dbc.Tab(label="Data / 資料", tab_id="tab-data"),
            ],
            id="parameters-tabs",
            active_tab="tab-general",
            className="mb-4"
        ),
        
        # Tab content / 標籤內容
        html.Div(id="parameters-tab-content"),
        
        # Action buttons / 操作按鈕
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Hr(),
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    "Reset / 重設",
                                    id="params-reset",
                                    color="secondary",
                                    className="me-2"
                                ),
                                dbc.Button(
                                    "Save Changes / 儲存變更",
                                    id="params-save",
                                    color="primary",
                                    disabled=True  # Read-only for MVP
                                ),
                            ]
                        ),
                        html.Small(
                            " ⚠️ Edit mode disabled for MVP / 編輯模式在 MVP 中停用",
                            className="text-muted ms-2"
                        )
                    ],
                    width=12,
                    className="mt-4"
                )
            ]
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="parameters-interval",
            interval=60*1000,  # 60 seconds
            n_intervals=0
        ),
        
        # Store for config data / 配置資料儲存
        dcc.Store(id="parameters-store", data=load_monitoring_params())
    ],
    fluid=True
)


# Render tab content / 渲染標籤內容
@callback(
    Output("parameters-tab-content", "children"),
    Input("parameters-tabs", "active_tab"),
    Input("parameters-store", "data")
)
def render_tab_content(active_tab, data):
    """Render content for the selected tab"""
    if not data or "error" in data:
        return dbc.Alert(
            f"Error loading configuration / 載入配置錯誤: {data.get('error', 'Unknown')}",
            color="danger"
        )
    
    if active_tab == "tab-general":
        return render_general_tab(data.get("monitoring", {}))
    
    elif active_tab == "tab-indicators":
        return render_indicators_tab(data.get("indicators", {}))
    
    elif active_tab == "tab-signals":
        return render_signals_tab(data.get("signals", {}))
    
    elif active_tab == "tab-notifications":
        return render_notifications_tab(data.get("notifications", {}))
    
    elif active_tab == "tab-data":
        return render_data_tab(data.get("data", {}))
    
    return html.P("Select a tab / 選擇一個標籤")


def render_general_tab(monitoring):
    """Render General settings tab"""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Monitoring Settings / 監測設定", className="card-title mb-4"),
                
                render_parameter_row(
                    "Check Interval / 檢查間隔",
                    monitoring.get("check_interval_minutes", 5),
                    "minutes / 分鐘",
                    "How often to run monitoring checks / 多久執行一次監測檢查"
                ),
                
                render_parameter_row(
                    "Max Run History / 最大執行歷史",
                    monitoring.get("max_run_history", 100),
                    "runs / 次",
                    "Number of run records to keep / 保留的執行記錄數量"
                ),
                
                render_parameter_row(
                    "Prevent Overlap / 防止重疊",
                    "Enabled / 啟用" if monitoring.get("prevent_overlap", True) else "Disabled / 停用",
                    "",
                    "Prevent overlapping executions / 防止重疊執行"
                ),
                
                render_parameter_row(
                    "Enable File Logging / 啟用檔案日誌",
                    "Enabled / 啟用" if monitoring.get("enable_file_logging", True) else "Disabled / 停用",
                    "",
                    "Log to file in addition to console / 除了 console 也寫入檔案日誌"
                ),
                
                render_parameter_row(
                    "Log File / 日誌檔案",
                    monitoring.get("log_file", "/tmp/kimi-shared-brain/logs/scheduler.log"),
                    "",
                    "Path to scheduler log file / 排程器日誌檔案路徑"
                ),
            ]
        )
    )


def render_indicators_tab(indicators):
    """Render Indicators settings tab"""
    ma_periods = indicators.get("ma_periods", {})
    volume = indicators.get("volume", {})
    patterns = indicators.get("patterns", {})
    
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Moving Average Periods / 移動平均週期", className="card-title mb-4"),
                
                render_parameter_row(
                    "Short MA / 短期 MA",
                    ma_periods.get("short", 5),
                    "candles / K線",
                    "Short-term moving average period / 短期移動平均週期"
                ),
                
                render_parameter_row(
                    "Medium MA / 中期 MA",
                    ma_periods.get("medium", 20),
                    "candles / K線",
                    "Medium-term moving average period / 中期移動平均週期"
                ),
                
                render_parameter_row(
                    "Long MA / 長期 MA",
                    ma_periods.get("long", 240),
                    "candles / K線",
                    "Long-term moving average period (20 hours for 5m) / 長期移動平均週期（5m約20小時）"
                ),
                
                html.Hr(),
                html.H5("Volume Settings / 成交量設定", className="card-title mb-4 mt-4"),
                
                render_parameter_row(
                    "Volume Window / 成交量視窗",
                    volume.get("window", 20),
                    "periods / 週期",
                    "Periods for volume average calculation / 成交量平均計算週期"
                ),
                
                render_parameter_row(
                    "Volume Spike Threshold / 成交量爆增閾值",
                    volume.get("spike_threshold", 1.5),
                    "x",
                    "Current volume must be this many times average to trigger / 當前成交量必須為平均的多少倍才觸發"
                ),
                
                html.Hr(),
                html.H5("Pattern Settings / 型態設定", className="card-title mb-4 mt-4"),
                
                render_parameter_row(
                    "Consecutive Candles / 連續K線",
                    patterns.get("consecutive_candles", 4),
                    "candles / K線",
                    "Number of consecutive candles for pattern detection / 連續K線型態檢測數量"
                ),
            ]
        )
    )


def render_signals_tab(signals):
    """Render Signals settings tab"""
    cooldowns = signals.get("cooldown_minutes", {})
    
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Signal Cooldowns / 訊號冷卻", className="card-title mb-4"),
                
                render_parameter_row(
                    "Trend Long Cooldown / 順勢做多冷卻",
                    cooldowns.get("trend_long", 30),
                    "minutes / 分鐘",
                    "Minimum time between trend_long signals / trend_long 訊號之間的最小間隔"
                ),
                
                render_parameter_row(
                    "Trend Short Cooldown / 順勢做空冷卻",
                    cooldowns.get("trend_short", 30),
                    "minutes / 分鐘",
                    "Minimum time between trend_short signals / trend_short 訊號之間的最小間隔"
                ),
                
                render_parameter_row(
                    "Contrarian Watch Cooldown / 逆勢觀察冷卻",
                    cooldowns.get("contrarian_watch", 15),
                    "minutes / 分鐘",
                    "Minimum time between contrarian_watch signals / contrarian_watch 訊號之間的最小間隔"
                ),
                
                html.Hr(),
                html.H5("Confirmation Levels / 確認層級", className="card-title mb-4 mt-4"),
                
                render_parameter_row(
                    "Trend Signals / 順勢訊號",
                    "Confirmed / 已確認",
                    "",
                    "Trend signals are execution-grade / 順勢訊號為可執行等級"
                ),
                
                render_parameter_row(
                    "Contrarian Signals / 逆勢訊號",
                    "Watch Only / 僅觀察",
                    "",
                    "Contrarian signals are for observation only / 逆勢訊號僅供觀察"
                ),
            ]
        )
    )


def render_notifications_tab(notifications):
    """Render Notifications settings tab"""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Notification Settings / 通知設定", className="card-title mb-4"),
                
                render_parameter_row(
                    "Default Language / 預設語言",
                    notifications.get("default_language", "zh"),
                    "",
                    "Default language for alert messages / 提醒訊息的預設語言"
                ),
                
                render_parameter_row(
                    "Default Format / 預設格式",
                    notifications.get("default_format", "markdown"),
                    "",
                    "Default format for notifications / 通知的預設格式"
                ),
                
                render_parameter_row(
                    "Channels / 渠道",
                    ", ".join(notifications.get("channels", ["console", "discord"])),
                    "",
                    "Active notification channels / 啟用的通知渠道"
                ),
                
                html.Hr(),
                html.H5("Warning Banners / 警告橫幅", className="card-title mb-4 mt-4"),
                
                dbc.Alert(
                    notifications.get("alert_prefix", "🔔") + " " +
                    notifications.get("warning_banners", {}).get("alert_only", "ALERT ONLY"),
                    color="warning",
                    className="mb-2"
                ),
                
                dbc.Alert(
                    notifications.get("watch_prefix", "👁️") + " " +
                    notifications.get("warning_banners", {}).get("watch_only", "WATCH ONLY"),
                    color="info"
                ),
            ]
        )
    )


def render_data_tab(data):
    """Render Data settings tab"""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Data Source / 資料來源", className="card-title mb-4"),
                
                render_parameter_row(
                    "Exchange / 交易所",
                    data.get("exchange", "binance"),
                    "",
                    "Data exchange provider / 資料交易所提供者"
                ),
                
                render_parameter_row(
                    "Base URL / 基礎網址",
                    data.get("base_url", "https://api.binance.com"),
                    "",
                    "API base URL / API 基礎網址"
                ),
                
                render_parameter_row(
                    "Klines Endpoint / K線端點",
                    data.get("klines_endpoint", "/api/v3/klines"),
                    "",
                    "Endpoint for candlestick data / K線資料端點"
                ),
                
                render_parameter_row(
                    "Timeout / 超時",
                    data.get("timeout_seconds", 30),
                    "seconds / 秒",
                    "API request timeout / API 請求超時"
                ),
                
                html.Hr(),
                html.H5("Timeframes / 時間框架", className="card-title mb-4 mt-4"),
                
                render_parameter_row(
                    "Available Timeframes / 可用時間框架",
                    ", ".join(data.get("timeframes", ["1m", "5m", "15m"])),
                    "",
                    "Supported candlestick timeframes / 支援的K線時間框架"
                ),
                
                render_parameter_row(
                    "Default Limit / 預設數量",
                    data.get("default_limit", 300),
                    "candles / K線",
                    "Default number of candles to fetch / 預設抓取的K線數量"
                ),
            ]
        )
    )


def render_parameter_row(label, value, unit, description):
    """Render a parameter row with label, value, and description"""
    return dbc.Row(
        [
            dbc.Col(
                [
                    html.Label(label, className="fw-bold"),
                    html.P(description, className="text-muted small mb-0")
                ],
                width=12,
                md=5
            ),
            dbc.Col(
                [
                    html.Div(
                        [
                            html.Span(str(value), className="fs-5 font-monospace"),
                            html.Small(f" {unit}", className="text-muted") if unit else None
                        ]
                    )
                ],
                width=12,
                md=7,
                className="d-flex align-items-center"
            ),
        ],
        className="mb-3 align-items-start"
    )
