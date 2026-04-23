"""
Strategy Conditions / 策略條件檢查

Maps strategy conditions from strategies.json to executable check functions.
將 strategies.json 中的策略條件對應到可執行的檢查函數。

Conditions supported / 支援的條件:
- close_vs_ma240: Price near MA240 (within threshold)
- ma5_cross_ma20: MA5 crosses above MA20
- ma5_cross_below_ma20: MA5 crosses below MA20
- volume_spike: Volume > average * threshold
- consecutive_green: N consecutive bullish candles
- consecutive_red: N consecutive bearish candles
- close_above_ma240: Price above MA240
- close_below_ma240: Price below MA240
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum


class ConditionResult(Enum):
    """Result of a condition check / 條件檢查結果"""
    PASSED = "passed"        # Condition met / 條件滿足
    FAILED = "failed"        # Condition not met / 條件不滿足
    MISSING_DATA = "missing_data"  # Required data unavailable / 缺少必要資料
    NOT_IMPLEMENTED = "not_implemented"  # Condition not yet supported / 條件尚未支援


@dataclass
class ConditionCheck:
    """Result of checking a single condition / 單一條件檢查結果"""
    condition: str
    result: ConditionResult
    details: Dict[str, Any]
    message: str = ""


class StrategyConditions:
    """
    Strategy condition checker / 策略條件檢查器
    
    Evaluates strategy conditions against market data.
    根據市場資料評估策略條件。
    """
    
    def __init__(self):
        """Initialize condition checker / 初始化條件檢查器"""
        self._checkers: Dict[str, Callable] = {
            "close_vs_ma240": self._check_close_vs_ma240,
            "ma5_cross_ma20": self._check_ma5_cross_ma20,
            "ma5_cross_below_ma20": self._check_ma5_cross_below_ma20,
            "volume_spike": self._check_volume_spike,
            "consecutive_green": self._check_consecutive_green,
            "consecutive_red": self._check_consecutive_red,
            "close_above_ma240": self._check_close_above_ma240,
            "close_below_ma240": self._check_close_below_ma240,
        }
    
    def check_condition(
        self,
        condition: str,
        data: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None
    ) -> ConditionCheck:
        """
        Check a single condition / 檢查單一條件
        
        Args:
            condition: Condition name from strategies.json
            data: Market data dictionary containing:
                - price: Current price
                - ma5, ma20, ma240: Moving averages
                - volume_ratio: Volume ratio
                - candles: List of candle data
                - closes: List of close prices
            parameters: Strategy parameters from config
            
        Returns:
            ConditionCheck result
        """
        if condition not in self._checkers:
            return ConditionCheck(
                condition=condition,
                result=ConditionResult.NOT_IMPLEMENTED,
                details={},
                message=f"Condition '{condition}' not yet implemented"
            )
        
        try:
            return self._checkers[condition](data, parameters or {})
        except Exception as e:
            return ConditionCheck(
                condition=condition,
                result=ConditionResult.MISSING_DATA,
                details={"error": str(e)},
                message=f"Error checking condition: {e}"
            )
    
    def check_all_conditions(
        self,
        conditions: List[str],
        data: Dict[str, Any],
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[ConditionCheck]:
        """
        Check all conditions for a strategy / 檢查策略的所有條件
        
        Args:
            conditions: List of condition names
            data: Market data
            parameters: Strategy parameters
            
        Returns:
            List of condition check results
        """
        results = []
        for condition in conditions:
            result = self.check_condition(condition, data, parameters)
            results.append(result)
        return results
    
    def strategy_passed(self, results: List[ConditionCheck]) -> bool:
        """
        Check if all required conditions passed / 檢查是否所有必要條件都通過
        
        A strategy passes if ALL conditions pass.
        策略通過的條件是所有條件都通過。
        
        Args:
            results: List of condition check results
            
        Returns:
            True if all conditions passed
        """
        if not results:
            return False
        
        for r in results:
            if r.result != ConditionResult.PASSED:
                return False
        return True
    
    # ===== Individual Condition Checkers / 個別條件檢查器 =====
    
    def _check_close_vs_ma240(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if price is near MA240 / 檢查價格是否在 MA240 附近"""
        price = data.get("price")
        ma240 = data.get("ma240")
        
        if price is None or ma240 is None or ma240 == 0:
            return ConditionCheck(
                condition="close_vs_ma240",
                result=ConditionResult.MISSING_DATA,
                details={"price": price, "ma240": ma240},
                message="Missing price or MA240 data"
            )
        
        # Price should be within 2% of MA240
        deviation = abs(price - ma240) / ma240 * 100
        threshold = params.get("ma240_threshold", 2.0)
        
        if deviation <= threshold:
            return ConditionCheck(
                condition="close_vs_ma240",
                result=ConditionResult.PASSED,
                details={"price": price, "ma240": ma240, "deviation": deviation},
                message=f"Price ${price:.2f} within {deviation:.2f}% of MA240 ${ma240:.2f}"
            )
        else:
            return ConditionCheck(
                condition="close_vs_ma240",
                result=ConditionResult.FAILED,
                details={"price": price, "ma240": ma240, "deviation": deviation},
                message=f"Price ${price:.2f} deviated {deviation:.2f}% from MA240 (threshold: {threshold}%)"
            )
    
    def _check_ma5_cross_ma20(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if MA5 crossed above MA20 / 檢查 MA5 是否上穿 MA20"""
        ma5 = data.get("ma5")
        ma20 = data.get("ma20")
        ma5_prev = data.get("ma5_prev")
        ma20_prev = data.get("ma20_prev")
        
        if ma5 is None or ma20 is None:
            return ConditionCheck(
                condition="ma5_cross_ma20",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing MA5 or MA20 data"
            )
        
        # Current: MA5 > MA20
        current_cross = ma5 > ma20
        
        # Previous: MA5 < MA20 (crossover happened)
        prev_cross = ma5_prev is not None and ma20_prev is not None and ma5_prev < ma20_prev
        
        if current_cross and prev_cross:
            return ConditionCheck(
                condition="ma5_cross_ma20",
                result=ConditionResult.PASSED,
                details={"ma5": ma5, "ma20": ma20, "ma5_prev": ma5_prev, "ma20_prev": ma20_prev},
                message=f"MA5 ${ma5:.2f} crossed above MA20 ${ma20:.2f}"
            )
        elif current_cross:
            return ConditionCheck(
                condition="ma5_cross_ma20",
                result=ConditionResult.PASSED,
                details={"ma5": ma5, "ma20": ma20},
                message=f"MA5 ${ma5:.2f} above MA20 ${ma20:.2f}"
            )
        else:
            return ConditionCheck(
                condition="ma5_cross_ma20",
                result=ConditionResult.FAILED,
                details={"ma5": ma5, "ma20": ma20},
                message=f"MA5 ${ma5:.2f} below MA20 ${ma20:.2f}"
            )
    
    def _check_ma5_cross_below_ma20(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if MA5 crossed below MA20 / 檢查 MA5 是否下穿 MA20"""
        ma5 = data.get("ma5")
        ma20 = data.get("ma20")
        ma5_prev = data.get("ma5_prev")
        ma20_prev = data.get("ma20_prev")
        
        if ma5 is None or ma20 is None:
            return ConditionCheck(
                condition="ma5_cross_below_ma20",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing MA5 or MA20 data"
            )
        
        current_cross = ma5 < ma20
        prev_cross = ma5_prev is not None and ma20_prev is not None and ma5_prev > ma20_prev
        
        if current_cross and prev_cross:
            return ConditionCheck(
                condition="ma5_cross_below_ma20",
                result=ConditionResult.PASSED,
                details={"ma5": ma5, "ma20": ma20},
                message=f"MA5 ${ma5:.2f} crossed below MA20 ${ma20:.2f}"
            )
        elif current_cross:
            return ConditionCheck(
                condition="ma5_cross_below_ma20",
                result=ConditionResult.PASSED,
                details={"ma5": ma5, "ma20": ma20},
                message=f"MA5 ${ma5:.2f} below MA20 ${ma20:.2f}"
            )
        else:
            return ConditionCheck(
                condition="ma5_cross_below_ma20",
                result=ConditionResult.FAILED,
                details={"ma5": ma5, "ma20": ma20},
                message=f"MA5 ${ma5:.2f} above MA20 ${ma20:.2f}"
            )
    
    def _check_volume_spike(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if volume is above threshold / 檢查成交量是否高於閾值"""
        volume_ratio = data.get("volume_ratio")
        threshold = params.get("volume_threshold", 1.5)
        
        if volume_ratio is None:
            return ConditionCheck(
                condition="volume_spike",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing volume ratio data"
            )
        
        if volume_ratio >= threshold:
            return ConditionCheck(
                condition="volume_spike",
                result=ConditionResult.PASSED,
                details={"volume_ratio": volume_ratio, "threshold": threshold},
                message=f"Volume ratio {volume_ratio:.2f}x exceeds threshold {threshold}x"
            )
        else:
            return ConditionCheck(
                condition="volume_spike",
                result=ConditionResult.FAILED,
                details={"volume_ratio": volume_ratio, "threshold": threshold},
                message=f"Volume ratio {volume_ratio:.2f}x below threshold {threshold}x"
            )
    
    def _check_consecutive_green(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check for consecutive green candles / 檢查連續綠K"""
        candles = data.get("candles", [])
        required = params.get("consecutive_count", 4)
        
        if not candles or len(candles) < required:
            return ConditionCheck(
                condition="consecutive_green",
                result=ConditionResult.MISSING_DATA,
                details={"candles_count": len(candles), "required": required},
                message=f"Not enough candles ({len(candles)} < {required})"
            )
        
        # Check last N candles
        recent = candles[-required:]
        green_count = sum(1 for c in recent if c.get("close", 0) > c.get("open", 0))
        
        if green_count >= required:
            return ConditionCheck(
                condition="consecutive_green",
                result=ConditionResult.PASSED,
                details={"green_count": green_count, "required": required},
                message=f"{green_count} consecutive green candles (required: {required})"
            )
        else:
            return ConditionCheck(
                condition="consecutive_green",
                result=ConditionResult.FAILED,
                details={"green_count": green_count, "required": required},
                message=f"Only {green_count} green candles (required: {required})"
            )
    
    def _check_consecutive_red(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check for consecutive red candles / 檢查連續紅K"""
        candles = data.get("candles", [])
        required = params.get("consecutive_count", 4)
        
        if not candles or len(candles) < required:
            return ConditionCheck(
                condition="consecutive_red",
                result=ConditionResult.MISSING_DATA,
                details={"candles_count": len(candles), "required": required},
                message=f"Not enough candles ({len(candles)} < {required})"
            )
        
        recent = candles[-required:]
        red_count = sum(1 for c in recent if c.get("close", 0) < c.get("open", 0))
        
        if red_count >= required:
            return ConditionCheck(
                condition="consecutive_red",
                result=ConditionResult.PASSED,
                details={"red_count": red_count, "required": required},
                message=f"{red_count} consecutive red candles (required: {required})"
            )
        else:
            return ConditionCheck(
                condition="consecutive_red",
                result=ConditionResult.FAILED,
                details={"red_count": red_count, "required": required},
                message=f"Only {red_count} red candles (required: {required})"
            )
    
    def _check_close_above_ma240(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if price is above MA240 / 檢查價格是否在 MA240 上方"""
        price = data.get("price")
        ma240 = data.get("ma240")
        
        if price is None or ma240 is None:
            return ConditionCheck(
                condition="close_above_ma240",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing price or MA240 data"
            )
        
        if price > ma240:
            return ConditionCheck(
                condition="close_above_ma240",
                result=ConditionResult.PASSED,
                details={"price": price, "ma240": ma240, "diff": price - ma240},
                message=f"Price ${price:.2f} above MA240 ${ma240:.2f} (+${price - ma240:.2f})"
            )
        else:
            return ConditionCheck(
                condition="close_above_ma240",
                result=ConditionResult.FAILED,
                details={"price": price, "ma240": ma240},
                message=f"Price ${price:.2f} below MA240 ${ma240:.2f}"
            )
    
    def _check_close_below_ma240(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if price is below MA240 / 檢查價格是否在 MA240 下方"""
        price = data.get("price")
        ma240 = data.get("ma240")
        
        if price is None or ma240 is None:
            return ConditionCheck(
                condition="close_below_ma240",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing price or MA240 data"
            )
        
        if price < ma240:
            return ConditionCheck(
                condition="close_below_ma240",
                result=ConditionResult.PASSED,
                details={"price": price, "ma240": ma240, "diff": ma240 - price},
                message=f"Price ${price:.2f} below MA240 ${ma240:.2f} (-${ma240 - price:.2f})"
            )
        else:
            return ConditionCheck(
                condition="close_below_ma240",
                result=ConditionResult.FAILED,
                details={"price": price, "ma240": ma240},
                message=f"Price ${price:.2f} above MA240 ${ma240:.2f}"
            )
