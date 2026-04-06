"""
Notification Formatter Module
通知格式化模組

BTC/ETH Monitoring System - Notification Layer
BTC/ETH 監測系統 - 通知層

This module formats signals into human-readable alert messages.
Converts Signal objects to formatted strings for various output channels.

本模組將訊號格式化為人類可讀的提醒訊息。
將 Signal 物件轉換為各種輸出通道的格式化字串。

⚠️  IMPORTANT / 重要  ⚠️
This module generates ALERTS ONLY. No automatic trading is performed.
本模組僅產生提醒，不執行自動交易。

Author: kimiclaw_bot
Version: 1.0.0
Date: 2026-04-06
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

import sys
sys.path.insert(0, '/tmp/kimi-shared-brain')

from signals.engine import Signal, SignalType, SignalLevel


class OutputFormat(Enum):
    """Output format types / 輸出格式類型"""
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    JSON = "json"


class NotificationFormatter:
    """
    Signal notification formatter / 訊號通知格式化器
    
    Formats Signal objects into human-readable alert messages.
    將 Signal 物件格式化為人類可讀的提醒訊息。
    """
    
    # Signal type display names / 訊號類型顯示名稱
    SIGNAL_NAMES = {
        SignalType.TREND_LONG: ("📈 TREND LONG", "📈 順勢做多"),
        SignalType.TREND_SHORT: ("📉 TREND SHORT", "📉 順勢做空"),
        SignalType.CONTRARIAN_WATCH_OVERHEATED: ("🔥 CONTRARIAN WATCH", "🔥 逆勢觀察 - 過熱"),
        SignalType.CONTRARIAN_WATCH_OVERSOLD: ("❄️ CONTRARIAN WATCH", "❄️ 逆勢觀察 - 超賣")
    }
    
    # Level indicators / 層級指示器
    LEVEL_INDICATORS = {
        SignalLevel.CONFIRMED: ("✅ CONFIRMED", "✅ 已確認"),
        SignalLevel.WATCH_ONLY: ("👁️ WATCH ONLY", "👁️ 僅觀察")
    }
    
    def __init__(self, language: str = "en"):
        """
        Initialize formatter / 初始化格式化器
        
        Args:
            language: Output language ("en" or "zh") / 輸出語言
        """
        self.language = language
        self.lang_idx = 0 if language == "en" else 1
    
    def _get_signal_name(self, signal_type: SignalType) -> str:
        """Get display name for signal type / 取得訊號類型顯示名稱"""
        names = self.SIGNAL_NAMES.get(signal_type, (str(signal_type), str(signal_type)))
        return names[self.lang_idx]
    
    def _get_level_indicator(self, level: SignalLevel) -> str:
        """Get display indicator for level / 取得層級顯示指示器"""
        indicators = self.LEVEL_INDICATORS.get(level, (str(level), str(level)))
        return indicators[self.lang_idx]
    
    def _format_timestamp(self, timestamp_ms: int) -> str:
        """Format timestamp to readable string / 將時間戳格式化為可讀字串"""
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        if self.language == "en":
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def _format_price(self, price: Optional[float]) -> str:
        """Format price with appropriate decimals / 格式化價格（適當小數位）"""
        if price is None:
            return "N/A"
        if price >= 10000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:,.4f}"
        else:
            return f"{price:.8f}"
    
    def format_alert(self, signal: Signal) -> str:
        """
        Format signal as plain text alert / 將訊號格式化為純文字提醒
        
        Args:
            signal: Signal object to format / 要格式化的訊號物件
            
        Returns:
            Formatted alert string / 格式化的提醒字串
        """
        lines = []
        
        # Header / 標頭
        signal_name = self._get_signal_name(signal.signal_type)
        level_indicator = self._get_level_indicator(signal.level)
        
        if self.language == "en":
            lines.append(f"{'=' * 50}")
            lines.append(f"ALERT: {signal_name} {level_indicator}")
            lines.append(f"{'=' * 50}")
        else:
            lines.append(f"{'=' * 50}")
            lines.append(f"提醒: {signal_name} {level_indicator}")
            lines.append(f"{'=' * 50}")
        
        # Basic info / 基本資訊
        if self.language == "en":
            lines.append(f"Symbol: {signal.symbol}")
            lines.append(f"Time: {self._format_timestamp(signal.timestamp)}")
        else:
            lines.append(f"標的: {signal.symbol}")
            lines.append(f"時間: {self._format_timestamp(signal.timestamp)}")
        
        # Price data / 價格資料
        lines.append("")
        if self.language == "en":
            lines.append("Price Data / 價格資料:")
        else:
            lines.append("價格資料:")
        
        price_data = signal.price_data
        
        # Common price fields / 通用價格欄位
        if "close_5m" in price_data:
            if self.language == "en":
                lines.append(f"  Close (5m): {self._format_price(price_data['close_5m'])}")
            else:
                lines.append(f"  收盤價 (5m): {self._format_price(price_data['close_5m'])}")
        
        if "ma5" in price_data and price_data["ma5"] is not None:
            if self.language == "en":
                lines.append(f"  MA5: {self._format_price(price_data['ma5'])}")
            else:
                lines.append(f"  MA5: {self._format_price(price_data['ma5'])}")
        
        if "ma20" in price_data and price_data["ma20"] is not None:
            if self.language == "en":
                lines.append(f"  MA20: {self._format_price(price_data['ma20'])}")
            else:
                lines.append(f"  MA20: {self._format_price(price_data['ma20'])}")
        
        if "ma240" in price_data and price_data["ma240"] is not None:
            if self.language == "en":
                lines.append(f"  MA240: {self._format_price(price_data['ma240'])}")
            else:
                lines.append(f"  MA240: {self._format_price(price_data['ma240'])}")
        
        # Volume data / 成交量資料
        if "volume_1m" in price_data:
            vol = price_data["volume_1m"]
            vol_avg = price_data.get("volume_avg_1m")
            vol_ratio = price_data.get("volume_ratio")
            
            if self.language == "en":
                lines.append(f"  Volume (1m): {vol:.2f}")
                if vol_avg:
                    lines.append(f"  Volume Avg: {vol_avg:.2f}")
                if vol_ratio:
                    lines.append(f"  Volume Ratio: {vol_ratio:.2f}x")
            else:
                lines.append(f"  成交量 (1m): {vol:.2f}")
                if vol_avg:
                    lines.append(f"  成交均量: {vol_avg:.2f}")
                if vol_ratio:
                    lines.append(f"  量比: {vol_ratio:.2f}x")
        
        # Pattern data (for contrarian) / 型態資料（逆勢用）
        if "pattern" in price_data:
            if self.language == "en":
                lines.append(f"  Pattern: {price_data['pattern']}")
                lines.append(f"  Consecutive Count: {price_data.get('consecutive_count', 'N/A')}")
            else:
                lines.append(f"  型態: {price_data['pattern']}")
                lines.append(f"  連續數量: {price_data.get('consecutive_count', 'N/A')}")
        
        # Conditions / 條件
        if signal.conditions:
            lines.append("")
            if self.language == "en":
                lines.append("Conditions Met / 條件滿足:")
                for cond, met in signal.conditions.items():
                    status = "✅" if met else "❌"
                    lines.append(f"  {status} {cond}")
            else:
                lines.append("條件滿足:")
                for cond, met in signal.conditions.items():
                    status = "✅" if met else "❌"
                    lines.append(f"  {status} {cond}")
        
        # Reason / 原因
        lines.append("")
        if self.language == "en":
            lines.append(f"Reason / 原因: {signal.reason}")
        else:
            lines.append(f"原因: {signal.reason}")
        
        # Warning / 警告
        lines.append("")
        lines.append(f"⚠️  {signal.warning}")
        
        # Footer / 頁尾
        lines.append("")
        lines.append(f"{'=' * 50}")
        
        return "\n".join(lines)
    
    def format_compact(self, signal: Signal) -> str:
        """
        Format signal as compact one-line alert / 將訊號格式化為緊湊單行提醒
        
        Args:
            signal: Signal object to format / 要格式化的訊號物件
            
        Returns:
            Compact alert string / 緊湊提醒字串
        """
        signal_name = self._get_signal_name(signal.signal_type)
        level = self._get_level_indicator(signal.level)
        
        close_price = signal.price_data.get("close_5m", "N/A")
        if isinstance(close_price, (int, float)):
            close_price = self._format_price(close_price)
        
        if self.language == "en":
            return f"[{signal.symbol}] {signal_name} @ {close_price} | {level} | {signal.warning}"
        else:
            return f"[{signal.symbol}] {signal_name} @ {close_price} | {level} | {signal.warning}"
    
    def format_markdown(self, signal: Signal) -> str:
        """
        Format signal as Markdown / 將訊號格式化為 Markdown
        
        Args:
            signal: Signal object to format / 要格式化的訊號物件
            
        Returns:
            Markdown formatted string / Markdown 格式化字串
        """
        lines = []
        
        signal_name = self._get_signal_name(signal.signal_type)
        level = self._get_level_indicator(signal.level)
        
        # Header
        if signal.level == SignalLevel.WATCH_ONLY:
            lines.append(f"## 👁️ {signal_name}")
        else:
            lines.append(f"## {signal_name}")
        
        lines.append("")
        lines.append(f"**{level}**  |  `{signal.symbol}`  |  {self._format_timestamp(signal.timestamp)}")
        lines.append("")
        
        # Price data table
        lines.append("### Price Data")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        
        price_data = signal.price_data
        
        if "close_5m" in price_data:
            lines.append(f"| Close (5m) | {self._format_price(price_data['close_5m'])} |")
        if "ma5" in price_data and price_data["ma5"] is not None:
            lines.append(f"| MA5 | {self._format_price(price_data['ma5'])} |")
        if "ma20" in price_data and price_data["ma20"] is not None:
            lines.append(f"| MA20 | {self._format_price(price_data['ma20'])} |")
        if "ma240" in price_data and price_data["ma240"] is not None:
            lines.append(f"| MA240 | {self._format_price(price_data['ma240'])} |")
        if "volume_1m" in price_data:
            lines.append(f"| Volume (1m) | {price_data['volume_1m']:.2f} |")
        if "volume_ratio" in price_data:
            lines.append(f"| Volume Ratio | {price_data['volume_ratio']:.2f}x |")
        if "pattern" in price_data:
            lines.append(f"| Pattern | {price_data['pattern']} |")
            lines.append(f"| Consecutive | {price_data.get('consecutive_count', 'N/A')} |")
        
        lines.append("")
        
        # Conditions
        if signal.conditions:
            lines.append("### Conditions")
            lines.append("")
            for cond, met in signal.conditions.items():
                status = "✅" if met else "❌"
                lines.append(f"- {status} {cond}")
            lines.append("")
        
        # Reason
        lines.append("### Reason")
        lines.append(f"\n{signal.reason}")
        lines.append("")
        
        # Warning
        lines.append("> ⚠️ **WARNING**: " + signal.warning)
        lines.append("")
        lines.append("---")
        
        return "\n".join(lines)
    
    def format_batch(self, signals: List[Signal], format_type: OutputFormat = OutputFormat.PLAIN_TEXT) -> str:
        """
        Format multiple signals as batch / 將多個訊號格式化為批次
        
        Args:
            signals: List of Signal objects / 訊號物件列表
            format_type: Output format type / 輸出格式類型
            
        Returns:
            Formatted batch string / 格式化的批次字串
        """
        if not signals:
            if self.language == "en":
                return "No signals to display / 無訊號顯示"
            else:
                return "無訊號顯示"
        
        lines = []
        
        # Header
        if self.language == "en":
            lines.append(f"{'=' * 60}")
            lines.append(f"SIGNAL BATCH / 訊號批次 - {len(signals)} signal(s)")
            lines.append(f"{'=' * 60}")
        else:
            lines.append(f"{'=' * 60}")
            lines.append(f"訊號批次 - {len(signals)} 個訊號")
            lines.append(f"{'=' * 60}")
        
        lines.append("")
        
        # Format each signal
        for i, signal in enumerate(signals, 1):
            if format_type == OutputFormat.PLAIN_TEXT:
                lines.append(f"--- Signal {i}/{len(signals)} ---")
                lines.append(self.format_alert(signal))
            elif format_type == OutputFormat.COMPACT:
                lines.append(f"{i}. {self.format_compact(signal)}")
            elif format_type == OutputFormat.MARKDOWN:
                lines.append(self.format_markdown(signal))
            
            lines.append("")
        
        return "\n".join(lines)


# Example usage / 使用範例
if __name__ == "__main__":
    print("Notification Formatter Module")
    print("通知格式化模組")
    print("=" * 40)
    
    # Create sample signal / 建立範例訊號
    from signals.engine import Signal, SignalType, SignalLevel
    import time
    
    sample_signal = Signal(
        signal_type=SignalType.TREND_LONG,
        level=SignalLevel.CONFIRMED,
        symbol="BTCUSDT",
        timestamp=int(time.time() * 1000),
        price_data={
            "close_5m": 69250.50,
            "ma5": 69180.25,
            "ma20": 69050.00,
            "ma240": 68500.75,
            "volume_1m": 12.5,
            "volume_avg_1m": 5.2,
            "volume_ratio": 2.4
        },
        conditions={
            "c1_above_ma240": True,
            "c2_ma_cross_above": True,
            "c3_volume_spike": True
        },
        reason="BTCUSDT: close > MA240, MA5 crossed above MA20, volume 2.4x average",
        warning="ALERT_ONLY_NO_AUTO_TRADE"
    )
    
    # Format in English / 英文格式
    print("\n--- English Format ---")
    formatter_en = NotificationFormatter(language="en")
    print(formatter_en.format_alert(sample_signal))
    
    # Format in Chinese / 中文格式
    print("\n--- 中文格式 ---")
    formatter_zh = NotificationFormatter(language="zh")
    print(formatter_zh.format_alert(sample_signal))
    
    # Compact format / 緊湊格式
    print("\n--- Compact Format ---")
    print(formatter_en.format_compact(sample_signal))
    
    # Markdown format / Markdown 格式
    print("\n--- Markdown Format ---")
    print(formatter_en.format_markdown(sample_signal))
