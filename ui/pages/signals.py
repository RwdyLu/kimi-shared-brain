"""
Signals Page / 訊號頁面

Signal history and alert viewing.
訊號歷史與提醒查看。
"""

import dash
from dash import dcc, html, callback, Output, Input, State
import dash_bootstrap_components as dbc
import sys
from pathlib import Path

# Dynamic path setup / 動態路徑設定
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

# Import monitor service / 匯入監測服務
from ui.services.monitor_service import get_recent_runs, get_today_signals, get_latest_indicator_snapshots

# Register page / 註冊頁面
dash.register_page(__name__, path="/signals", title="Signals")

# Page layout / 頁面佈局
layout = dbc.Container(
    [
        # Header / 標題
        html.H2("Signals", className="mb-4"),
        html.P("Signal history and alert feed / 訊號歷史與提醒串流", className="text-muted"),
        
        html.Hr(),
        
        # Summary Cards / 摘要卡片
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3(id="signals-total-count", children="--"),
                                    html.P("Total Today / 今日總計", className="text-muted mb-0")
                                ]
                            )
                        ],
                        color="primary",
                        outline=True
                    ),
                    width=6,
                    md=4,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3(id="signals-confirmed-count", children="--"),
                                    html.P("Confirmed / 已確認", className="text-muted mb-0")
                                ]
                            )
                        ],
                        color="success",
                        outline=True
                    ),
                    width=6,
                    md=4,
                    className="mb-3"
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardBody(
                                [
                                    html.H3(id="signals-watch-count", children="--"),
                                    html.P("Watch Only / 僅觀察", className="text-muted mb-0")
                                ]
                            )
                        ],
                        color="info",
                        outline=True
                    ),
                    width=6,
                    md=4,
                    className="mb-3"
                ),
            ]
        ),
        
        # Filters / 篩選器
        dbc.Card(
            dbc.CardBody(
                [
                    html.H5("Filters / 篩選", className="card-title"),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Signal Type / 訊號類型"),
                                    dbc.Select(
                                        id="signals-filter-type",
                                        options=[
                                            {"label": "All Types / 全部", "value": "all"},
                                            {"label": "Trend Long / 順勢做多", "value": "trend_long"},
                                            {"label": "Trend Short / 順勢做空", "value": "trend_short"},
                                            {"label": "Contrarian Watch / 逆勢觀察", "value": "contrarian_watch"},
                                            {"label": "Cycle / 週期 (Hilbert)", "value": "cycle"},
                                            {"label": "Breakout / 突破", "value": "breakout"},
                                            {"label": "Momentum / 動能", "value": "momentum"},
                                            {"label": "Reversal Long / 反轉做多", "value": "reversal_long"},
                                            {"label": "Mean Reversion / 均值回歸", "value": "mean_reversion"},
                                        ],
                                        value="all"
                                    )
                                ],
                                width=12,
                                md=4,
                                className="mb-3"
                            ),
                            dbc.Col(
                                [
                                    html.Label("Symbol / 標的"),
                                    dbc.Select(
                                        id="signals-filter-symbol",
                                        options=[
                                            {"label": "All Symbols / 全部", "value": "all"},
                                            {"label": "BTCUSDT", "value": "BTCUSDT"},
                                            {"label": "ETHUSDT", "value": "ETHUSDT"},
                                        ],
                                        value="all"
                                    )
                                ],
                                width=12,
                                md=4,
                                className="mb-3"
                            ),
                            dbc.Col(
                                [
                                    html.Label("Time Range / 時間範圍"),
                                    dbc.Select(
                                        id="signals-filter-time",
                                        options=[
                                            {"label": "Last 24 hours / 最近24小時", "value": "24h"},
                                            {"label": "Last 7 days / 最近7天", "value": "7d"},
                                            {"label": "Last 30 days / 最近30天", "value": "30d"},
                                            {"label": "All time / 全部", "value": "all"},
                                        ],
                                        value="24h"
                                    )
                                ],
                                width=12,
                                md=4,
                                className="mb-3"
                            ),
                        ]
                    ),
                    dbc.Button(
                        "Refresh / 刷新",
                        id="signals-refresh",
                        color="primary",
                        className="mt-2"
                    )
                ]
            ),
            className="mb-4"
        ),
        
        # Run History / 執行歷史
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Run History / 執行歷史", className="mb-0"),
                        html.Small("Click a run to view indicator details / 點擊執行查看指標詳情", className="text-muted")
                    ]
                ),
                dbc.CardBody(
                    id="signals-run-history",
                    children=[
                        html.P("Loading run history...", className="text-muted")
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Run Detail Modal / 執行詳情彈窗
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("Run Details / 執行詳情")),
                dbc.ModalBody(id="run-detail-modal-body"),
            ],
            id="run-detail-modal",
            size="lg",
            is_open=False,
        ),
        
        # Store for selected run / 儲存選中的執行
        dcc.Store(id="selected-run-id"),

        # Signal Feed / 訊號串流
        dbc.Card(
            [
                dbc.CardHeader(
                    [
                        html.H5("Signal Feed / 訊號串流", className="mb-0"),
                        html.Small("Latest signals filtered by type and symbol / 依類型與幣種篩選的最新訊號", className="text-muted")
                    ]
                ),
                dbc.CardBody(
                    id="signals-feed",
                    children=[
                        html.P("Loading signals...", className="text-muted")
                    ]
                )
            ],
            className="mb-4"
        ),

        # Signal Alert Info / 訊號提醒資訊
        dbc.Card(
            [
                dbc.CardHeader("Signal Types / 訊號類型"),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        html.H6("✅ Trend Long / 順勢做多"),
                                        html.P(
                                            "Confirmed execution-grade signal for long positions. "
                                            "Requires: price > MA240, MA5 crosses above MA20, volume spike.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("✅ Trend Short / 順勢做空"),
                                        html.P(
                                            "Confirmed execution-grade signal for short positions. "
                                            "Requires: price < MA240, MA5 crosses below MA20, volume spike.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("👁️ Contrarian Watch / 逆勢觀察"),
                                        html.P(
                                            "Watch-only signal for potential reversals. "
                                            "Not for execution - use for observation and analysis only.",
                                            className="text-muted small"
                                        ),
                                        dbc.Alert(
                                            "⚠️ WATCH ONLY - NOT FOR EXECUTION / 僅觀察 - 非執行訊號",
                                            color="warning",
                                            className="py-1 mt-2"
                                        )
                                    ],
                                    width=12,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("🌀 Cycle / 週期 (Hilbert)"),
                                        html.P(
                                            "Detects cyclic turning points via Hilbert Transform. "
                                            "Entry: HT_SINE cross above LEADSINE + TEMA rising.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("💥 Breakout / 突破"),
                                        html.P(
                                            "Detects price breaking out of channels. "
                                            "Entry: fastK cross above fastD + fastK < 20 + SAR below price.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("🚀 Momentum / 動能"),
                                        html.P(
                                            "Detects momentum shifts via RSI and TEMA. "
                                            "Entry: RSI cross above 30 + TEMA below BB middle + TEMA rising.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("🔄 Reversal Long / 反轉做多"),
                                        html.P(
                                            "Detects potential reversal to the upside. "
                                            "Entry: EMA5 cross above EMA10 or RSI cross above 40.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                                dbc.Col(
                                    [
                                        html.H6("📉 Mean Reversion / 均值回歸"),
                                        html.P(
                                            "Detects overextension from mean. "
                                            "Entry: price below BB lower + RSI < 30 + volume > avg × 1.5.",
                                            className="text-muted small"
                                        )
                                    ],
                                    width=12,
                                    md=6,
                                    className="mb-3"
                                ),
                            ]
                        )
                    ]
                )
            ],
            className="mb-4"
        ),
        
        # Alert-Only Notice / 僅提醒通知
        dbc.Alert(
            [
                html.H5("⚠️ Alert-Only System / 僅提醒系統", className="alert-heading"),
                html.P(
                    "This monitoring system generates ALERTS ONLY. No automatic trading is performed. "
                    "All trading decisions require manual confirmation.",
                    className="mb-0"
                ),
                html.Hr(),
                html.P(
                    "本監測系統僅產生提醒，不執行自動交易。所有交易決策需人工確認。",
                    className="mb-0 small"
                )
            ],
            color="warning",
            className="mb-4"
        ),
        
        # Auto-refresh / 自動刷新
        dcc.Interval(
            id="signals-interval",
            interval=30*1000,  # 30 seconds
            n_intervals=0
        ),
    ],
    fluid=True
)


# Callbacks / 回調

@callback(
    Output("signals-total-count", "children"),
    Output("signals-confirmed-count", "children"),
    Output("signals-watch-count", "children"),
    Output("signals-run-history", "children"),
    Input("signals-interval", "n_intervals"),
    Input("signals-refresh", "n_clicks")
)
def update_signals_page(n_intervals, n_clicks):
    """Update signals page with real data"""
    try:
        # Get today's signals
        today = get_today_signals()
        total = today.get("total", 0)
        confirmed = today.get("confirmed", 0)
        watch = today.get("watch_only", 0)
        
        # Get recent runs
        runs = get_recent_runs(10)
        
        # Build run history with clickable rows and prices
        if runs:
            run_items = []
            for run in runs:
                run_id = run.get("run_id", "--")
                timestamp = run.get("timestamp", "--")
                signals = run.get("signals", 0)
                confirmed_count = run.get("confirmed", 0)
                watch_count = run.get("watch_only", 0)
                symbols_checked = run.get("symbols_checked", ["BTCUSDT", "ETHUSDT"])
                
                # T-054-C: Get prices for this run / 取得此執行的價格
                prices = run.get("prices", {})
                price_display = []
                
                if prices:
                    for symbol in symbols_checked:
                        price = prices.get(symbol)
                        if price:
                            price_display.append(
                                html.Span(
                                    f"{symbol.replace('USDT', '')}: ${price:,.0f}",
                                    className="me-2 small"
                                )
                            )
                
                # Format signal display
                if signals > 0:
                    signal_text = f"{signals} signals"
                    badge_color = "success" if confirmed_count > 0 else "info"
                else:
                    signal_text = "No signals"
                    badge_color = "secondary"
                
                # Create clickable card for each run
                run_card = dbc.Card(
                    [
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            html.Strong(f"#{run_id}"),
                                            width=2,
                                            md=1
                                        ),
                                        dbc.Col(
                                            timestamp,
                                            width=4,
                                            md=3
                                        ),
                                        # T-054-C: Price display column / 價格顯示欄
                                        dbc.Col(
                                            html.Div(price_display) if price_display else html.Small("Prices N/A", className="text-muted"),
                                            width=6,
                                            md=4
                                        ),
                                        dbc.Col(
                                            dbc.Badge(signal_text, color=badge_color),
                                            width=3,
                                            md=2
                                        ),
                                        dbc.Col(
                                            html.Small("Click / 點擊", className="text-muted"),
                                            width=3,
                                            md=2,
                                            className="text-end"
                                        ),
                                    ],
                                    className="align-items-center"
                                )
                            ],
                            className="py-2"
                        )
                    ],
                    id={"type": "run-row", "index": run_id},
                    className="mb-2 hover-shadow",
                    style={"cursor": "pointer"}
                )
                
                run_items.append(run_card)
            
            run_history = html.Div(run_items)
        else:
            run_history = html.P("No run history available", className="text-muted text-center py-3")
        
        return str(total), str(confirmed), str(watch), run_history
        
    except Exception as e:
        return "--", "--", "--", dbc.Alert(f"Error loading data: {e}", color="danger")


# T-052-D: Handle run row clicks and show modal with indicator details
@callback(
    Output("run-detail-modal", "is_open"),
    Output("run-detail-modal-body", "children"),
    Output("selected-run-id", "data"),
    Input({"type": "run-row", "index": dash.ALL}, "n_clicks"),
    Input("signals-interval", "n_intervals"),
    State("run-detail-modal", "is_open"),
    prevent_initial_call=True
)
def toggle_run_modal(n_clicks_list, n_intervals, is_open):
    """Show modal with indicator details when a run is clicked"""
    ctx = dash.callback_context
    if not ctx.triggered:
        return False, html.Div(), None
    
    # Check if triggered by interval (refresh)
    triggered_id = ctx.triggered[0]["prop_id"]
    if "signals-interval" in triggered_id:
        # Keep modal state as is during refresh
        return dash.no_update, dash.no_update, dash.no_update
    
    # Find which run was clicked
    clicked_run_id = None
    for i, n_clicks in enumerate(n_clicks_list):
        if n_clicks:
            # Extract run_id from the pattern-matching ID
            clicked_run_id = ctx.inputs_list[0][i]["id"]["index"]
            break
    
    if not clicked_run_id:
        return False, html.Div(), None
    
    # Get indicator snapshots for this run
    try:
        snapshots = get_latest_indicator_snapshots()
        
        # Build modal content
        modal_content = []
        
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            if symbol in snapshots:
                data = snapshots[symbol]
                price = data.get("price")
                ma5 = data.get("ma5")
                ma20 = data.get("ma20")
                ma5_pct = data.get("price_vs_ma5_pct")
                ma20_pct = data.get("price_vs_ma20_pct")
                
                # Format values
                price_str = f"${price:,.2f}" if price else "--"
                ma5_str = f"${ma5:,.2f}" if ma5 else "--"
                ma20_str = f"${ma20:,.2f}" if ma20 else "--"
                
                # Format percentages with colors
                if ma5_pct is not None:
                    ma5_pct_color = "success" if ma5_pct >= 0 else "danger"
                    ma5_pct_str = html.Span(f"{ma5_pct:+.2f}%", className=f"text-{ma5_pct_color}")
                else:
                    ma5_pct_str = "--"
                
                if ma20_pct is not None:
                    ma20_pct_color = "success" if ma20_pct >= 0 else "danger"
                    ma20_pct_str = html.Span(f"{ma20_pct:+.2f}%", className=f"text-{ma20_pct_color}")
                else:
                    ma20_pct_str = "--"
                
                symbol_card = dbc.Card(
                    [
                        dbc.CardHeader(html.H5(symbol.replace("USDT", ""), className="mb-0")),
                        dbc.CardBody(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.H6("Price / 現價", className="text-muted"),
                                                html.H4(price_str, className="text-success")
                                            ],
                                            width=12,
                                            md=4
                                        ),
                                        dbc.Col(
                                            [
                                                html.H6("MA5", className="text-muted"),
                                                html.P(ma5_str),
                                                html.Small(["Distance: ", ma5_pct_str], className="text-muted")
                                            ],
                                            width=12,
                                            md=4
                                        ),
                                        dbc.Col(
                                            [
                                                html.H6("MA20", className="text-muted"),
                                                html.P(ma20_str),
                                                html.Small(["Distance: ", ma20_pct_str], className="text-muted")
                                            ],
                                            width=12,
                                            md=4
                                        ),
                                    ]
                                )
                            ]
                        )
                    ],
                    className="mb-3"
                )
                modal_content.append(symbol_card)
            else:
                # No data for this symbol
                modal_content.append(
                    dbc.Alert(
                        f"{symbol}: Data unavailable / 資料不可用",
                        color="secondary",
                        className="mb-3"
                    )
                )
        
        return True, html.Div(modal_content), clicked_run_id
        
    except Exception as e:
        return True, dbc.Alert(f"Error loading indicator data: {e}", color="danger"), clicked_run_id


# Fix E: Signal type filter callback / 訊號類型篩選回調
@callback(
    Output("signals-feed", "children"),
    Input("signals-interval", "n_intervals"),
    Input("signals-refresh", "n_clicks"),
    Input("signals-filter-type", "value"),
    Input("signals-filter-symbol", "value"),
    Input("signals-filter-time", "value"),
)
def update_signals_feed(n_intervals, n_clicks, filter_type, filter_symbol, filter_time):
    """Update signal feed based on filters / 根據篩選條件更新訊號串流"""
    try:
        import json
        from datetime import datetime, timedelta
        from pathlib import Path
        from config.paths import LOGS_DIR
        
        snapshot_file = LOGS_DIR / "indicator_snapshots.jsonl"
        if not snapshot_file.exists():
            return html.P("No signal data available / 無訊號資料", className="text-muted text-center py-3")
        
        # Time filter / 時間篩選
        now = datetime.now()
        if filter_time == "24h":
            cutoff = now - timedelta(hours=24)
        elif filter_time == "7d":
            cutoff = now - timedelta(days=7)
        elif filter_time == "30d":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None
        
        # Type mapping / 類型映射
        type_mapping = {
            "trend_long": ["MA_CROSS_TREND", "EMA_CROSS_FAST", "VOLUME_SPIKE", "PRICE_CHANNEL_BREAK"],
            "trend_short": ["MA_CROSS_TREND_SHORT"],
            "contrarian_watch": ["CONTRARIAN_WATCH_OVERHEATED", "CONTRARIAN_WATCH_OVERSOLD"],
            "cycle": ["HILBERT_CYCLE"],
            "breakout": ["STOCHASTIC_BREAKOUT"],
            "momentum": ["RSI_TREND", "RSI_MID_BOUNCE", "MOMENTUM_DIVERGENCE"],
            "reversal_long": ["BB_MEAN_REVERSION"],
            "mean_reversion": ["BB_MEAN_REVERSION"],
        }
        
        # Read and filter snapshots / 讀取並篩選快照
        signals = []
        seen = set()
        
        with open(snapshot_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    symbol = record.get("symbol")
                    signal_types = record.get("signal_types", [])
                    ts_str = record.get("timestamp", "")
                    
                    # Skip if no signals / 若無訊號則跳過
                    if not signal_types:
                        continue
                    
                    # Time filter / 時間篩選
                    if cutoff and ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00').replace('+00:00', ''))
                            if ts < cutoff:
                                continue
                        except:
                            continue
                    
                    # Symbol filter / 幣種篩選
                    if filter_symbol != "all" and symbol != filter_symbol:
                        continue
                    
                    # Type filter / 類型篩選
                    if filter_type != "all":
                        allowed_types = type_mapping.get(filter_type, [])
                        if not any(st in allowed_types for st in signal_types):
                            continue
                    
                    # Deduplicate by symbol+types+timestamp (minute precision)
                    ts_minute = ts_str[:16] if ts_str else ""
                    key = f"{symbol}:{','.join(sorted(signal_types))}:{ts_minute}"
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    signals.append(record)
                    
                except Exception:
                    continue
        
        # Sort by timestamp descending / 按時間降序排序
        signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Limit to last 50 / 限制最近 50 條
        signals = signals[:50]
        
        if not signals:
            return html.P("No signals match the selected filters / 無符合篩選條件的訊號", className="text-muted text-center py-3")
        
        # Build cards / 建立卡片
        signal_cards = []
        for sig in signals:
            symbol = sig.get("symbol", "Unknown")
            price = sig.get("price")
            signal_types = sig.get("signal_types", [])
            ts_str = sig.get("timestamp", "")
            run_id = sig.get("run_id", "")
            
            # Format timestamp / 格式化時間
            try:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00').replace('+00:00', ''))
                time_display = ts.strftime("%m-%d %H:%M")
            except:
                time_display = ts_str[:16] if ts_str else "--"
            
            # Badge colors / 徽章顏色
            type_colors = {
                "MA_CROSS_TREND": "success",
                "MA_CROSS_TREND_SHORT": "danger",
                "CONTRARIAN_WATCH_OVERHEATED": "warning",
                "CONTRARIAN_WATCH_OVERSOLD": "warning",
                "HILBERT_CYCLE": "info",
                "STOCHASTIC_BREAKOUT": "primary",
                "RSI_TREND": "secondary",
                "RSI_MID_BOUNCE": "secondary",
                "BB_MEAN_REVERSION": "dark",
                "EMA_CROSS_FAST": "success",
                "VOLUME_SPIKE": "secondary",
                "PRICE_CHANNEL_BREAK": "primary",
                "MOMENTUM_DIVERGENCE": "info",
            }
            
            badges = []
            for st in signal_types:
                color = type_colors.get(st, "light")
                label = st.replace("_", " ").title()
                badges.append(dbc.Badge(label, color=color, className="me-1 mb-1"))
            
            price_str = f"${price:,.2f}" if price else "--"
            
            card = dbc.Card(
                [
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.Strong(symbol.replace("USDT", "")),
                                            html.Br(),
                                            html.Small(time_display, className="text-muted")
                                        ],
                                        width=3,
                                        md=2
                                    ),
                                    dbc.Col(
                                        [
                                            html.H5(price_str, className="mb-0"),
                                            html.Small(f"Run {run_id}", className="text-muted")
                                        ],
                                        width=3,
                                        md=2
                                    ),
                                    dbc.Col(
                                        html.Div(badges),
                                        width=6,
                                        md=8
                                    ),
                                ],
                                className="align-items-center"
                            )
                        ],
                        className="py-2"
                    )
                ],
                className="mb-2"
            )
            signal_cards.append(card)
        
        return html.Div(signal_cards)
        
    except Exception as e:
        return dbc.Alert(f"Error loading signals: {e}", color="danger")
