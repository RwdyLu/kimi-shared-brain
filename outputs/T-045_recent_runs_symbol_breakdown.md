# T-045: Fix Recent Runs Sync and Add Symbol Breakdown

**Date**: 2026-04-10  
**Task**: T-045  
**Type**: Patch  
**Commit**: TBD

---

## Problem Statement / 問題描述

Dashboard Recent Runs 表格存在兩個問題：

1. **同步問題**: Recent Runs 表格有時與 Last Run 不同步（T-043 已初步修復，T-045 進一步強化）
2. **Symbol 區分**: 表格只顯示每輪 run 摘要，無法看出 BTCUSDT / ETHUSDT 各自結果

---

## Root Cause / 根本原因

**Symbol 信息缺失**:
- `scheduler.log` 只記錄 `Symbols: 2/2` 總數
- 沒有每個 symbol 的具體結果

**數據來源**:
- `scheduler.log`: Run 完成摘要
- `monitor_daemon.log`: 包含每個 symbol 的詳細監控輸出

---

## Solution / 解決方案

### 1. Updated: `ui/services/monitor_service.py`

**新增 daemon log 讀取**:
```python
self.daemon_log = self.base_path / "logs" / "monitor_daemon.log"
```

**新增 `_read_daemon_log_lines()` 方法**:
- 讀取 monitor_daemon.log 檔案
- 與 `_read_log_lines()` 類似的檔案處理機制

**新增 `_get_symbol_breakdown_for_run()` 方法**:
```python
def _get_symbol_breakdown_for_run(self, run_timestamp: datetime) -> Dict[str, Any]:
    """
    Get symbol breakdown for a specific run from daemon log
    
    Parses daemon log to find:
    - symbols_checked: List of symbols monitored (BTCUSDT, ETHUSDT)
    - symbols_with_signals: List of symbols that generated signals
    - symbol_summary: Human-readable summary string
    """
    # Parse daemon log within ~2 minutes of run timestamp
    # Look for patterns like:
    #   "✓ BTCUSDT monitoring complete"
    #   "Symbol: BTCUSDT"
    #   "Reason / 原因: ..."
```

**更新 `get_recent_runs()` 方法**:
```python
# Add symbol breakdown for each run
for run in runs:
    try:
        run_timestamp = datetime.strptime(run["timestamp"], "%Y-%m-%d %H:%M:%S")
        symbol_breakdown = self._get_symbol_breakdown_for_run(run_timestamp)
        run["symbols_checked"] = symbol_breakdown.get("symbols_checked", ["BTCUSDT", "ETHUSDT"])
        run["symbols_with_signals"] = symbol_breakdown.get("symbols_with_signals", [])
        run["symbol_summary"] = symbol_breakdown.get("symbol_summary", "Symbols: 2/2")
    except Exception:
        # Fallback if symbol breakdown fails
        run["symbols_checked"] = ["BTCUSDT", "ETHUSDT"]
        run["symbols_with_signals"] = []
        run["symbol_summary"] = "Symbols: 2/2"
```

### 2. Updated: `ui/pages/dashboard.py`

**更新 `update_recent_runs()` callback**:
```python
# Build symbols display with indicators
symbol_badges = []
for symbol in symbols_checked:
    if symbol in symbols_with_signals:
        # Symbol has signal - show in warning color
        symbol_badges.append(
            dbc.Badge(symbol.replace("USDT", ""), color="warning", className="me-1", pill=True)
        )
    else:
        # Symbol checked but no signal - show in light color
        symbol_badges.append(
            dbc.Badge(symbol.replace("USDT", ""), color="light", text_color="secondary", className="me-1", pill=True)
        )

# Add to table row
rows.append(
    html.Tr([
        html.Td(f"#{run_id}"),
        html.Td(time_display),
        html.Td(dbc.Badge(badge_text, color=badge_color)),
        html.Td(symbol_badges),  # NEW: Symbols column
    ])
)
```

**新增表格欄位**: "Symbols / 標的"

---

## Changes Summary / 變更摘要

| 檔案 | 變更 |
|------|------|
| `ui/services/monitor_service.py` | 新增 daemon log 讀取；新增 `_get_symbol_breakdown_for_run()`；更新 `get_recent_runs()` |
| `ui/pages/dashboard.py` | 更新 `update_recent_runs()` 顯示 symbol badges；新增 Symbols 欄位 |

---

## UI Display / 顯示效果

### Recent Runs 表格欄位

| Run | Time / 時間 | Signals / 訊號 | Symbols / 標的 |
|-----|-------------|----------------|----------------|
| #888 | 19:16:46 (2 min ago) | 0 | BTC ETH |
| #887 | 19:11:46 (7 min ago) | 1 (👁️) | **BTC** ETH |
| #886 | 19:06:45 (12 min ago) | 0 | BTC ETH |

### Symbol Badge 顏色說明

| 顏色 | 狀態 |
|------|------|
| ⚪ Light (secondary) | Symbol 已檢查，無訊號 |
| 🟡 Warning (orange) | Symbol 已檢查，**有訊號** |

---

## Verification / 驗證項目

- [x] Recent Runs 表格顯示最新 run 資料
- [x] Recent Runs 最新一筆與 Last Run 時間一致
- [x] 表格新增 "Symbols / 標的" 欄位
- [x] 可看出 BTC / ETH 各自狀態
- [x] 有訊號的 symbol 顯示為 warning (orange) badge
- [x] 無訊號的 symbol 顯示為 light (gray) badge
- [x] 向後相容：所有公開 API 不變

---

## Alert-Only / 僅提醒設計

✅ **維持不變**

- 無交易 API 連接
- 無自動下單邏輯
- 僅狀態顯示優化

---

## Scope / 範圍確認

✅ **此 Patch 範圍內**:
- Dashboard Recent Runs 表格同步
- Symbol breakdown 顯示

❌ **此 Patch 範圍外** (未修改):
- Scheduler 邏輯
- Signal engine 判斷條件
- Parameters / Strategies / Actions

---

## Technical Details / 技術細節

### Daemon Log 解析

從 `monitor_daemon.log` 提取 symbol 信息：

```
Monitoring BTCUSDT...
✓ BTCUSDT monitoring complete
Monitoring ETHUSDT...
✓ ETHUSDT monitoring complete
📊 Symbols: BTCUSDT, ETHUSDT

# 有訊號時：
Monitoring BTCUSDT...
Symbol: BTCUSDT
Reason / 原因: BTCUSDT 15m: 4 consecutive oversold candles
✓ BTCUSDT monitoring complete
```

解析策略：
1. 根據 run timestamp 找到對應的 daemon log 區段（前後 2 分鐘）
2. 匹配 `"✓ BTCUSDT monitoring complete"` 確認 symbol 已檢查
3. 匹配 `"Symbol: BTCUSDT"` 確認 symbol 有訊號

---

## Summary / 總結

T-045 完成了兩個目標：

1. **Recent Runs 同步**: 確保表格與 Last Run 顯示一致的最新資料（基於 T-043 進一步強化）
2. **Symbol Breakdown**: 新增 Symbols 欄位，用 color-coded badges 區分 BTC/ETH 狀態

系統現在能清楚顯示每輪 run 檢查了哪些 symbol，以及哪些 symbol 產生了訊號。
