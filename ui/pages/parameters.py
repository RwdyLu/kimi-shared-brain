"""
Parameters Page / 參數頁面

View and edit monitoring parameters.
查看與編輯監測參數。
"""

import dash
from dash import dcc, html, callback, Output, Input, State, ALL
import dash_bootstrap_components as dbc
import sys
import json
import os
from datetime import datetime

sys.path.insert(0, '/tmp/kimi-shared-brain')

from config.loader import get_monitoring_params

# Register page / 註冊頁面
dash.register_page(__name__, path="/parameters", title="Parameters")

# Config file path / 配置文件路徑
CONFIG_FILE = "/tmp/kimi-shared-brain/config/monitoring_params.json"


# Load initial config / 載入初始配置
def load_monitoring_params():
    """Load monitoring parameters from config"""
    try:
        return get_monitoring_params()
    except Exception as e:
        return {"error": str(e), "version": "1.0.0"}


# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Parameters", className="mb-4"),
        html.P("View and edit monitoring parameters / 查看與編輯監測參數", className="text-muted"),
        
        html.Hr(),
        
        # Status Alert / 狀態提示
        html.Div(id="parameters-status"),
        
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
                                    "🔄 Reload / 重新載入",
                                    id="params-reload",
                                    color="secondary",
                                    className="me-2"
                                ),
                                dbc.Button(
                                    "💾 Save Changes / 儲存變更",
                                    id="params-save",
                                    color="primary"
                                ),
                            ]
                        ),
                        dbc.Button(
                            "⏪ Reset to Defaults / 重設為預設值",
                            id="params-reset-defaults",
                            color="outline-danger",
                            className="ms-3"
                        ),
                    ],
                    width=12,
                    className="mt-4"
                )
            ]
        ),
        
        # Confirmation Modal / 確認對話框
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Confirm Reset / 確認重設")),
                dbc.ModalBody(
                    "Are you sure you want to reset all parameters to defaults? "
                    "This action cannot be undone.\n\n"
                    "確定要將所有參數重設為預設值嗎？此操作無法復原。"
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button(
                            "Cancel / 取消",
                            id="reset-cancel",
                            color="secondary",
                            className="me-2"
                        ),
                        dbc.Button(
                            "Confirm Reset / 確認重設",
                            id="reset-confirm",
                            color="danger"
                        ),
                    ]
                ),
            ],
            id="reset-modal",
            is_open=False,
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
    """Render content for the selected tab with editable inputs"""
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
    """Render General settings tab with editable inputs"""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Monitoring Settings / 監測設定", className="card-title mb-4"),
                
                render_editable_row(
                    "check_interval",
                    "Check Interval / 檢查間隔",
                    monitoring.get("check_interval_minutes", 5),
                    "minutes / 分鐘",
                    "How often to run monitoring checks / 多久執行一次監測檢查",
                    input_type="number",
                    min=1, max=60
                ),
                
                render_editable_row(
                    "max_run_history",
                    "Max Run History / 最大執行歷史",
                    monitoring.get("max_run_history", 100),
                    "runs / 次",
                    "Number of run records to keep / 保留的執行記錄數量",
                    input_type="number",
                    min=10, max=1000
                ),
                
                render_editable_row(
                    "prevent_overlap",
                    "Prevent Overlap / 防止重疊",
                    monitoring.get("prevent_overlap", True),
                    "",
                    "Prevent overlapping executions / 防止重疊執行",
                    input_type="switch"
                ),
                
                render_editable_row(
                    "enable_file_logging",
                    "Enable File Logging / 啟用檔案日誌",
                    monitoring.get("enable_file_logging", True),
                    "",
                    "Log to file in addition to console / 除了 console 也寫入檔案日誌",
                    input_type="switch"
                ),
                
                render_editable_row(
                    "log_file",
                    "Log File / 日誌檔案",
                    monitoring.get("log_file", "/tmp/kimi-shared-brain/logs/scheduler.log"),
                    "",
                    "Path to scheduler log file / 排程器日誌檔案路徑",
                    input_type="text"
                ),
            ]
        )
    )


def render_indicators_tab(indicators):
    """Render Indicators settings tab with editable inputs"""
    ma_periods = indicators.get("ma_periods", {})
    volume = indicators.get("volume", {})
    patterns = indicators.get("patterns", {})
    
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Moving Average Periods / 移動平均週期", className="card-title mb-4"),
                
                render_editable_row(
                    "ma_short",
                    "Short MA / 短期 MA",
                    ma_periods.get("short", 5),
                    "candles / K線",
                    "Short-term moving average period / 短期移動平均週期",
                    input_type="number",
                    min=2, max=50
                ),
                
                render_editable_row(
                    "ma_medium",
                    "Medium MA / 中期 MA",
                    ma_periods.get("medium", 20),
                    "candles / K線",
                    "Medium-term moving average period / 中期移動平均週期",
                    input_type="number",
                    min=5, max=100
                ),
                
                render_editable_row(
                    "ma_long",
                    "Long MA / 長期 MA",
                    ma_periods.get("long", 240),
                    "candles / K線",
                    "Long-term moving average period (20 hours for 5m) / 長期移動平均週期（5m約20小時）",
                    input_type="number",
                    min=50, max=500
                ),
                
                html.Hr(),
                html.H5("Volume Settings / 成交量設定", className="card-title mb-4 mt-4"),
                
                render_editable_row(
                    "volume_window",
                    "Volume Window / 成交量視窗",
                    volume.get("window", 20),
                    "periods / 週期",
                    "Periods for volume average calculation / 成交量平均計算週期",
                    input_type="number",
                    min=5, max=100
                ),
                
                render_editable_row(
                    "volume_threshold",
                    "Volume Spike Threshold / 成交量爆增閾值",
                    volume.get("spike_threshold", 1.5),
                    "x",
                    "Current volume must be this many times average to trigger / 當前成交量必須為平均的多少倍才觸發",
                    input_type="number",
                    min=1.0, max=5.0, step=0.1
                ),
                
                html.Hr(),
                html.H5("Pattern Settings / 型態設定", className="card-title mb-4 mt-4"),
                
                render_editable_row(
                    "consecutive_candles",
                    "Consecutive Candles / 連續K線",
                    patterns.get("consecutive_candles", 4),
                    "candles / K線",
                    "Number of consecutive candles for pattern detection / 連續K線型態檢測數量",
                    input_type="number",
                    min=2, max=10
                ),
            ]
        )
    )


def render_signals_tab(signals):
    """Render Signals settings tab with editable inputs"""
    cooldowns = signals.get("cooldown_minutes", {})
    
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Signal Cooldowns / 訊號冷卻", className="card-title mb-4"),
                
                render_editable_row(
                    "cooldown_trend_long",
                    "Trend Long Cooldown / 順勢做多冷卻",
                    cooldowns.get("trend_long", 30),
                    "minutes / 分鐘",
                    "Minimum time between trend_long signals / trend_long 訊號之間的最小間隔",
                    input_type="number",
                    min=5, max=240
                ),
                
                render_editable_row(
                    "cooldown_trend_short",
                    "Trend Short Cooldown / 順勢做空冷卻",
                    cooldowns.get("trend_short", 30),
                    "minutes / 分鐘",
                    "Minimum time between trend_short signals / trend_short 訊號之間的最小間隔",
                    input_type="number",
                    min=5, max=240
                ),
                
                render_editable_row(
                    "cooldown_contrarian",
                    "Contrarian Watch Cooldown / 逆勢觀察冷卻",
                    cooldowns.get("contrarian_watch", 15),
                    "minutes / 分鐘",
                    "Minimum time between contrarian_watch signals / contrarian_watch 訊號之間的最小間隔",
                    input_type="number",
                    min=5, max=120
                ),
                
                html.Hr(),
                html.H5("Confirmation Levels / 確認層級", className="card-title mb-4 mt-4"),
                
                render_editable_row(
                    "min_confirmations",
                    "Minimum Confirmations / 最小確認數",
                    signals.get("min_confirmations", 3),
                    "conditions / 條件",
                    "Minimum conditions required for signal generation / 產生訊號所需的最小條件數",
                    input_type="number",
                    min=1, max=5
                ),
            ]
        )
    )


def render_notifications_tab(notifications):
    """Render Notifications settings tab with editable inputs"""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Notification Settings / 通知設定", className="card-title mb-4"),
                
                render_editable_row(
                    "default_language",
                    "Default Language / 預設語言",
                    notifications.get("default_language", "zh"),
                    "",
                    "Default language for alert messages / 提醒訊息的預設語言",
                    input_type="select",
                    options=[
                        {"label": "中文 (Chinese)", "value": "zh"},
                        {"label": "English", "value": "en"}
                    ]
                ),
                
                render_editable_row(
                    "default_format",
                    "Default Format / 預設格式",
                    notifications.get("default_format", "markdown"),
                    "",
                    "Default format for notifications / 通知的預設格式",
                    input_type="select",
                    options=[
                        {"label": "Markdown", "value": "markdown"},
                        {"label": "Plain Text", "value": "plain_text"},
                        {"label": "JSON", "value": "json"}
                    ]
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
    """Render Data settings tab with editable inputs"""
    return dbc.Card(
        dbc.CardBody(
            [
                html.H5("Data Source / 資料來源", className="card-title mb-4"),
                
                render_editable_row(
                    "exchange",
                    "Exchange / 交易所",
                    data.get("exchange", "binance"),
                    "",
                    "Data exchange provider / 資料交易所提供者",
                    input_type="select",
                    options=[
                        {"label": "Binance", "value": "binance"},
                        {"label": "Binance Testnet", "value": "binance_testnet"}
                    ]
                ),
                
                render_editable_row(
                    "base_url",
                    "Base URL / 基礎網址",
                    data.get("base_url", "https://api.binance.com"),
                    "",
                    "API base URL / API 基礎網址",
                    input_type="text"
                ),
                
                render_editable_row(
                    "timeout_seconds",
                    "Timeout / 超時",
                    data.get("timeout_seconds", 30),
                    "seconds / 秒",
                    "API request timeout / API 請求超時",
                    input_type="number",
                    min=5, max=120
                ),
                
                html.Hr(),
                html.H5("Timeframes / 時間框架", className="card-title mb-4 mt-4"),
                
                render_editable_row(
                    "default_limit",
                    "Default Limit / 預設數量",
                    data.get("default_limit", 300),
                    "candles / K線",
                    "Default number of candles to fetch / 預設抓取的K線數量",
                    input_type="number",
                    min=100, max=1000
                ),
            ]
        )
    )


def render_editable_row(param_id, label, value, unit, description, input_type="text", **kwargs):
    """Render an editable parameter row with input field"""
    
    if input_type == "number":
        input_field = dbc.Input(
            id={"type": "param-input", "id": param_id},
            type="number",
            value=value,
            min=kwargs.get("min"),
            max=kwargs.get("max"),
            step=kwargs.get("step", 1),
            className="param-input"
        )
    elif input_type == "switch":
        input_field = dbc.Switch(
            id={"type": "param-switch", "id": param_id},
            value=value,
            label="Enabled / 啟用" if value else "Disabled / 停用",
            className="param-switch"
        )
    elif input_type == "select":
        input_field = dbc.Select(
            id={"type": "param-select", "id": param_id},
            options=kwargs.get("options", []),
            value=value,
            className="param-select"
        )
    else:
        input_field = dbc.Input(
            id={"type": "param-input", "id": param_id},
            type="text",
            value=value,
            className="param-input"
        )
    
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
                    dbc.InputGroup(
                        [
                            input_field,
                            dbc.InputGroupText(unit) if unit else None
                        ],
                        className="mb-0"
                    ) if unit else input_field
                ],
                width=12,
                md=7,
                className="d-flex align-items-center"
            ),
        ],
        className="mb-4 align-items-start"
    )


# Callbacks / 回調

@callback(
    Output("parameters-store", "data"),
    Output("parameters-status", "children"),
    Input("params-save", "n_clicks"),
    Input("params-reload", "n_clicks"),
    Input("reset-confirm", "n_clicks"),
    State("parameters-store", "data"),
    State({"type": "param-input", "id": ALL}, "value"),
    State({"type": "param-input", "id": ALL}, "id"),
    State({"type": "param-switch", "id": ALL}, "value"),
    State({"type": "param-switch", "id": ALL}, "id"),
    State({"type": "param-select", "id": ALL}, "value"),
    State({"type": "param-select", "id": ALL}, "id"),
    prevent_initial_call=True
)
def handle_actions(save_clicks, reload_clicks, reset_clicks, current_data,
                   input_values, input_ids, switch_values, switch_ids,
                   select_values, select_ids):
    """Handle save, reload, and reset actions"""
    from dash import callback_context
    
    ctx = callback_context
    if not ctx.triggered:
        return current_data, None
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "params-reload":
        # Reload from file
        new_data = load_monitoring_params()
        return new_data, dbc.Alert(
            "✅ Configuration reloaded from file / 配置已從檔案重新載入",
            color="info",
            dismissable=True,
            className="mt-3"
        )
    
    elif button_id == "params-save":
        # Collect all parameter values
        param_updates = {}
        
        # Process number inputs
        for val, pid in zip(input_values, input_ids):
            param_updates[pid["id"]] = val
        
        # Process switches
        for val, pid in zip(switch_values, switch_ids):
            param_updates[pid["id"]] = val
        
        # Process selects
        for val, pid in zip(select_values, select_ids):
            param_updates[pid["id"]] = val
        
        # Build updated config
        updated_config = build_config_from_params(param_updates, current_data)
        
        # Save to file
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(updated_config, f, indent=2, ensure_ascii=False)
            
            return updated_config, dbc.Alert(
                f"✅ Configuration saved successfully at {datetime.now().strftime('%H:%M:%S')} / 配置儲存成功",
                color="success",
                dismissable=True,
                className="mt-3"
            )
        except Exception as e:
            return current_data, dbc.Alert(
                f"❌ Error saving configuration / 儲存配置錯誤: {e}",
                color="danger",
                dismissable=True,
                className="mt-3"
            )
    
    elif button_id == "reset-confirm":
        # Reset to defaults
        default_config = get_default_config()
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            return default_config, dbc.Alert(
                "✅ Configuration reset to defaults / 配置已重設為預設值",
                color="warning",
                dismissable=True,
                className="mt-3"
            )
        except Exception as e:
            return current_data, dbc.Alert(
                f"❌ Error resetting configuration / 重設配置錯誤: {e}",
                color="danger",
                dismissable=True,
                className="mt-3"
            )
    
    return current_data, None


@callback(
    Output("reset-modal", "is_open"),
    Input("params-reset-defaults", "n_clicks"),
    Input("reset-cancel", "n_clicks"),
    Input("reset-confirm", "n_clicks"),
    State("reset-modal", "is_open"),
    prevent_initial_call=True
)
def toggle_reset_modal(reset_clicks, cancel_clicks, confirm_clicks, is_open):
    """Toggle the reset confirmation modal"""
    from dash import callback_context
    
    ctx = callback_context
    if not ctx.triggered:
        return is_open
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    if button_id == "params-reset-defaults":
        return True
    elif button_id in ["reset-cancel", "reset-confirm"]:
        return False
    
    return is_open


def build_config_from_params(params, current_data):
    """Build config dict from parameter inputs"""
    config = {
        "version": current_data.get("version", "1.0.0"),
        "monitoring": {
            "check_interval_minutes": params.get("check_interval", 5),
            "max_run_history": params.get("max_run_history", 100),
            "prevent_overlap": params.get("prevent_overlap", True),
            "enable_file_logging": params.get("enable_file_logging", True),
            "log_file": params.get("log_file", "/tmp/kimi-shared-brain/logs/scheduler.log")
        },
        "indicators": {
            "ma_periods": {
                "short": params.get("ma_short", 5),
                "medium": params.get("ma_medium", 20),
                "long": params.get("ma_long", 240)
            },
            "volume": {
                "window": params.get("volume_window", 20),
                "spike_threshold": params.get("volume_threshold", 1.5)
            },
            "patterns": {
                "consecutive_candles": params.get("consecutive_candles", 4)
            }
        },
        "signals": {
            "cooldown_minutes": {
                "trend_long": params.get("cooldown_trend_long", 30),
                "trend_short": params.get("cooldown_trend_short", 30),
                "contrarian_watch": params.get("cooldown_contrarian", 15)
            },
            "min_confirmations": params.get("min_confirmations", 3)
        },
        "notifications": {
            "default_language": params.get("default_language", "zh"),
            "default_format": params.get("default_format", "markdown"),
            "channels": current_data.get("notifications", {}).get("channels", ["console", "discord"]),
            "warning_banners": current_data.get("notifications", {}).get("warning_banners", {
                "alert_only": "ALERT ONLY - NO AUTO TRADING",
                "watch_only": "WATCH ONLY - NOT FOR EXECUTION"
            }),
            "alert_prefix": "🔔",
            "watch_prefix": "👁️"
        },
        "data": {
            "exchange": params.get("exchange", "binance"),
            "base_url": params.get("base_url", "https://api.binance.com"),
            "klines_endpoint": current_data.get("data", {}).get("klines_endpoint", "/api/v3/klines"),
            "timeout_seconds": params.get("timeout_seconds", 30),
            "timeframes": current_data.get("data", {}).get("timeframes", ["1m", "5m", "15m"]),
            "default_limit": params.get("default_limit", 300)
        }
    }
    return config


def get_default_config():
    """Get default configuration"""
    return {
        "version": "1.0.0",
        "monitoring": {
            "check_interval_minutes": 5,
            "max_run_history": 100,
            "prevent_overlap": True,
            "enable_file_logging": True,
            "log_file": "/tmp/kimi-shared-brain/logs/scheduler.log"
        },
        "indicators": {
            "ma_periods": {
                "short": 5,
                "medium": 20,
                "long": 240
            },
            "volume": {
                "window": 20,
                "spike_threshold": 1.5
            },
            "patterns": {
                "consecutive_candles": 4
            }
        },
        "signals": {
            "cooldown_minutes": {
                "trend_long": 30,
                "trend_short": 30,
                "contrarian_watch": 15
            },
            "min_confirmations": 3
        },
        "notifications": {
            "default_language": "zh",
            "default_format": "markdown",
            "channels": ["console", "discord"],
            "warning_banners": {
                "alert_only": "ALERT ONLY - NO AUTO TRADING",
                "watch_only": "WATCH ONLY - NOT FOR EXECUTION"
            },
            "alert_prefix": "🔔",
            "watch_prefix": "👁️"
        },
        "data": {
            "exchange": "binance",
            "base_url": "https://api.binance.com",
            "klines_endpoint": "/api/v3/klines",
            "timeout_seconds": 30,
            "timeframes": ["1m", "5m", "15m"],
            "default_limit": 300
        }
    }
