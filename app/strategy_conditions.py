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
            # P2 Strategy Conditions / P2 策略條件
            "sine_cross_above_leadsine": self._check_sine_cross_above_leadsine,
            "tema_rising": self._check_tema_rising,
            "tema_below_bb_middle": self._check_tema_below_bb_middle,
            "fastk_cross_above_fastd": self._check_fastk_cross_above_fastd,
            "fastk_below_20": self._check_fastk_below_20,
            "sar_below_price": self._check_sar_below_price,
            "rsi_cross_above_30": self._check_rsi_cross_above_30,
            "rsi_below_30": self._check_rsi_below_30,
            "price_below_bb_lower": self._check_price_below_bb_lower,
            # High-frequency strategy conditions / 高頻策略條件
            "ema5_cross_above_ema10": self._check_ema5_cross_above_ema10,
            "rsi_cross_above_40": self._check_rsi_cross_above_40,
            "volume_above_avg_1_5x": self._check_volume_above_avg_1_5x,
            "price_above_20period_high": self._check_price_above_20period_high,
            "bullish_divergence_rsi": self._check_bullish_divergence_rsi,
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

    # ===== P2 Strategy Conditions / P2 策略條件 =====

    def _check_sine_cross_above_leadsine(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if HT Sine crossed above LeadSine / 檢查 Sine 是否上穿 LeadSine"""
        sine = data.get("ht_sine")
        leadsine = data.get("ht_leadsine")
        sine_prev = data.get("ht_sine_prev")
        leadsine_prev = data.get("ht_leadsine_prev")
        
        if sine is None or leadsine is None:
            return ConditionCheck(
                condition="sine_cross_above_leadsine",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing HT Sine/LeadSine data"
            )
        
        current_cross = sine > leadsine
        prev_cross = sine_prev is not None and leadsine_prev is not None and sine_prev < leadsine_prev
        
        if current_cross and prev_cross:
            return ConditionCheck(
                condition="sine_cross_above_leadsine",
                result=ConditionResult.PASSED,
                details={"sine": sine, "leadsine": leadsine},
                message=f"Sine ({sine:.4f}) crossed above LeadSine ({leadsine:.4f})"
            )
        elif current_cross:
            return ConditionCheck(
                condition="sine_cross_above_leadsine",
                result=ConditionResult.PASSED,
                details={"sine": sine, "leadsine": leadsine},
                message=f"Sine ({sine:.4f}) above LeadSine ({leadsine:.4f})"
            )
        else:
            return ConditionCheck(
                condition="sine_cross_above_leadsine",
                result=ConditionResult.FAILED,
                details={"sine": sine, "leadsine": leadsine},
                message=f"Sine ({sine:.4f}) below LeadSine ({leadsine:.4f})"
            )

    def _check_tema_rising(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if TEMA is rising / 檢查 TEMA 是否上升"""
        tema = data.get("tema")
        tema_prev = data.get("tema_prev")
        
        if tema is None:
            return ConditionCheck(
                condition="tema_rising",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing TEMA data"
            )
        
        if tema_prev is not None and tema > tema_prev:
            return ConditionCheck(
                condition="tema_rising",
                result=ConditionResult.PASSED,
                details={"tema": tema, "tema_prev": tema_prev},
                message=f"TEMA rising: ${tema:.2f} > ${tema_prev:.2f}"
            )
        elif tema_prev is not None:
            return ConditionCheck(
                condition="tema_rising",
                result=ConditionResult.FAILED,
                details={"tema": tema, "tema_prev": tema_prev},
                message=f"TEMA falling: ${tema:.2f} <= ${tema_prev:.2f}"
            )
        else:
            return ConditionCheck(
                condition="tema_rising",
                result=ConditionResult.PASSED,
                details={"tema": tema},
                message=f"TEMA present: ${tema:.2f}"
            )

    def _check_tema_below_bb_middle(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if TEMA is below BB middle band / 檢查 TEMA 是否在布林帶中軌下方"""
        tema = data.get("tema")
        bb_middle = data.get("bb_middle")
        
        if tema is None or bb_middle is None:
            return ConditionCheck(
                condition="tema_below_bb_middle",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing TEMA or BB middle data"
            )
        
        if tema < bb_middle:
            return ConditionCheck(
                condition="tema_below_bb_middle",
                result=ConditionResult.PASSED,
                details={"tema": tema, "bb_middle": bb_middle, "diff": bb_middle - tema},
                message=f"TEMA ${tema:.2f} below BB middle ${bb_middle:.2f}"
            )
        else:
            return ConditionCheck(
                condition="tema_below_bb_middle",
                result=ConditionResult.FAILED,
                details={"tema": tema, "bb_middle": bb_middle},
                message=f"TEMA ${tema:.2f} above BB middle ${bb_middle:.2f}"
            )

    def _check_fastk_cross_above_fastd(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if Stochastic FastK crossed above FastD / 檢查 FastK 是否上穿 FastD"""
        fastk = data.get("stoch_fastk")
        fastd = data.get("stoch_fastd")
        fastk_prev = data.get("stoch_fastk_prev")
        fastd_prev = data.get("stoch_fastd_prev")
        
        if fastk is None or fastd is None:
            return ConditionCheck(
                condition="fastk_cross_above_fastd",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing Stochastic data"
            )
        
        current_cross = fastk > fastd
        prev_cross = fastk_prev is not None and fastd_prev is not None and fastk_prev < fastd_prev
        
        if current_cross and prev_cross:
            return ConditionCheck(
                condition="fastk_cross_above_fastd",
                result=ConditionResult.PASSED,
                details={"fastk": fastk, "fastd": fastd},
                message=f"FastK ({fastk:.2f}) crossed above FastD ({fastd:.2f})"
            )
        elif current_cross:
            return ConditionCheck(
                condition="fastk_cross_above_fastd",
                result=ConditionResult.PASSED,
                details={"fastk": fastk, "fastd": fastd},
                message=f"FastK ({fastk:.2f}) above FastD ({fastd:.2f})"
            )
        else:
            return ConditionCheck(
                condition="fastk_cross_above_fastd",
                result=ConditionResult.FAILED,
                details={"fastk": fastk, "fastd": fastd},
                message=f"FastK ({fastk:.2f}) below FastD ({fastd:.2f})"
            )

    def _check_fastk_below_20(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if FastK is below 20 (oversold) / 檢查 FastK 是否低於 20"""
        fastk = data.get("stoch_fastk")
        
        if fastk is None:
            return ConditionCheck(
                condition="fastk_below_20",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing Stochastic FastK data"
            )
        
        if fastk < 20:
            return ConditionCheck(
                condition="fastk_below_20",
                result=ConditionResult.PASSED,
                details={"fastk": fastk},
                message=f"FastK {fastk:.2f} below 20 (oversold)"
            )
        else:
            return ConditionCheck(
                condition="fastk_below_20",
                result=ConditionResult.FAILED,
                details={"fastk": fastk},
                message=f"FastK {fastk:.2f} not below 20"
            )

    def _check_sar_below_price(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if SAR is below price (bullish) / 檢查 SAR 是否在價格下方"""
        price = data.get("price")
        sar = data.get("sar")
        
        if price is None or sar is None:
            return ConditionCheck(
                condition="sar_below_price",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing SAR or price data"
            )
        
        if sar < price:
            return ConditionCheck(
                condition="sar_below_price",
                result=ConditionResult.PASSED,
                details={"sar": sar, "price": price, "diff": price - sar},
                message=f"SAR ${sar:.2f} below price ${price:.2f} (bullish)"
            )
        else:
            return ConditionCheck(
                condition="sar_below_price",
                result=ConditionResult.FAILED,
                details={"sar": sar, "price": price},
                message=f"SAR ${sar:.2f} above price ${price:.2f} (bearish)"
            )

    def _check_rsi_cross_above_30(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if RSI crossed above 30 (exiting oversold) / 檢查 RSI 是否上穿 30"""
        rsi = data.get("rsi")
        rsi_prev = data.get("rsi_prev")
        
        if rsi is None:
            return ConditionCheck(
                condition="rsi_cross_above_30",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing RSI data"
            )
        
        current_above = rsi > 30
        prev_below = rsi_prev is not None and rsi_prev < 30
        
        if current_above and prev_below:
            return ConditionCheck(
                condition="rsi_cross_above_30",
                result=ConditionResult.PASSED,
                details={"rsi": rsi, "rsi_prev": rsi_prev},
                message=f"RSI crossed above 30: {rsi:.2f} (was {rsi_prev:.2f})"
            )
        elif current_above:
            return ConditionCheck(
                condition="rsi_cross_above_30",
                result=ConditionResult.PASSED,
                details={"rsi": rsi},
                message=f"RSI above 30: {rsi:.2f}"
            )
        else:
            return ConditionCheck(
                condition="rsi_cross_above_30",
                result=ConditionResult.FAILED,
                details={"rsi": rsi},
                message=f"RSI below 30: {rsi:.2f}"
            )

    def _check_rsi_below_30(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if RSI is below 30 (oversold) / 檢查 RSI 是否低於 30"""
        rsi = data.get("rsi")
        
        if rsi is None:
            return ConditionCheck(
                condition="rsi_below_30",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing RSI data"
            )
        
        if rsi < 30:
            return ConditionCheck(
                condition="rsi_below_30",
                result=ConditionResult.PASSED,
                details={"rsi": rsi},
                message=f"RSI {rsi:.2f} below 30 (oversold)"
            )
        else:
            return ConditionCheck(
                condition="rsi_below_30",
                result=ConditionResult.FAILED,
                details={"rsi": rsi},
                message=f"RSI {rsi:.2f} not below 30"
            )

    def _check_price_below_bb_lower(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check if price is below BB lower band / 檢查價格是否低於布林帶下軌"""
        price = data.get("price")
        bb_lower = data.get("bb_lower")
        
        if price is None or bb_lower is None:
            return ConditionCheck(
                condition="price_below_bb_lower",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing price or BB lower data"
            )
        
        if price < bb_lower:
            return ConditionCheck(
                condition="price_below_bb_lower",
                result=ConditionResult.PASSED,
                details={"price": price, "bb_lower": bb_lower, "diff": bb_lower - price},
                message=f"Price ${price:.2f} below BB lower ${bb_lower:.2f}"
            )
        else:
            return ConditionCheck(
                condition="price_below_bb_lower",
                result=ConditionResult.FAILED,
                details={"price": price, "bb_lower": bb_lower},
                message=f"Price ${price:.2f} above BB lower ${bb_lower:.2f}"
            )

    # ===================================================================
    # High-frequency strategy conditions / 高頻策略條件
    # ===================================================================

    def _check_ema5_cross_above_ema10(self, data: Dict[str, Any], parameters: Optional[Dict[str, Any]] = None) -> ConditionCheck:
        """Check if EMA5 crosses above EMA10 / 檢查EMA5是否上穿EMA10"""
        ema5 = data.get("ema5")
        ema10 = data.get("ema10")
        
        if ema5 is None or ema10 is None:
            return ConditionCheck(
                condition="ema5_cross_above_ema10",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="EMA5 or EMA10 data missing"
            )
        
        if ema5 > ema10:
            return ConditionCheck(
                condition="ema5_cross_above_ema10",
                result=ConditionResult.PASSED,
                details={"ema5": ema5, "ema10": ema10, "diff": ema5 - ema10},
                message=f"EMA5 ({ema5:.2f}) above EMA10 ({ema10:.2f})"
            )
        else:
            return ConditionCheck(
                condition="ema5_cross_above_ema10",
                result=ConditionResult.FAILED,
                details={"ema5": ema5, "ema10": ema10},
                message=f"EMA5 ({ema5:.2f}) not above EMA10 ({ema10:.2f})"
            )

    def _check_rsi_cross_above_40(self, data: Dict[str, Any], parameters: Optional[Dict[str, Any]] = None) -> ConditionCheck:
        """Check if RSI crosses above 40 / 檢查RSI是否上穿40"""
        rsi = data.get("rsi")
        
        if rsi is None:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="RSI data missing"
            )
        
        if rsi > 40:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.PASSED,
                details={"rsi": rsi},
                message=f"RSI {rsi:.1f} above 40"
            )
        else:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.FAILED,
                details={"rsi": rsi},
                message=f"RSI {rsi:.1f} not above 40"
            )

    def _check_volume_above_avg_1_5x(self, data: Dict[str, Any], parameters: Optional[Dict[str, Any]] = None) -> ConditionCheck:
        """Check if volume is above 1.5x average / 檢查成交量是否超過均量1.5倍"""
        volume_ratio = data.get("volume_ratio")
        
        if volume_ratio is None:
            return ConditionCheck(
                condition="volume_above_avg_1_5x",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Volume ratio data missing"
            )
        
        threshold = 1.5
        if volume_ratio > threshold:
            return ConditionCheck(
                condition="volume_above_avg_1_5x",
                result=ConditionResult.PASSED,
                details={"volume_ratio": volume_ratio, "threshold": threshold},
                message=f"Volume {volume_ratio:.2f}x above threshold {threshold}x"
            )
        else:
            return ConditionCheck(
                condition="volume_above_avg_1_5x",
                result=ConditionResult.FAILED,
                details={"volume_ratio": volume_ratio, "threshold": threshold},
                message=f"Volume {volume_ratio:.2f}x below threshold {threshold}x"
            )

    def _check_price_above_20period_high(self, data: Dict[str, Any], parameters: Optional[Dict[str, Any]] = None) -> ConditionCheck:
        """Check if price is above 20-period high / 檢查價格是否突破20期高點"""
        price = data.get("price")
        highs = data.get("highs")
        
        if price is None or highs is None or len(highs) < 20:
            return ConditionCheck(
                condition="price_above_20period_high",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Price or highs data missing (need 20 periods)"
            )
        
        period_high = max(highs[-20:])
        
        if price > period_high:
            return ConditionCheck(
                condition="price_above_20period_high",
                result=ConditionResult.PASSED,
                details={"price": price, "period_high": period_high},
                message=f"Price ${price:.2f} above 20-period high ${period_high:.2f}"
            )
        else:
            return ConditionCheck(
                condition="price_above_20period_high",
                result=ConditionResult.FAILED,
                details={"price": price, "period_high": period_high},
                message=f"Price ${price:.2f} below 20-period high ${period_high:.2f}"
            )

    def _check_bullish_divergence_rsi(self, data: Dict[str, Any], parameters: Optional[Dict[str, Any]] = None) -> ConditionCheck:
        """Check for bullish RSI divergence / 檢查RSI底背離"""
        closes = data.get("closes")
        rsi_values = data.get("rsi_values")
        
        if closes is None or rsi_values is None or len(closes) < 14 or len(rsi_values) < 14:
            return ConditionCheck(
                condition="bullish_divergence_rsi",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Price or RSI history missing (need 14 periods)"
            )
        
        # Simple divergence check: compare last 5 periods
        # Price makes lower low but RSI makes higher low
        price_low_1 = min(closes[-10:-5])
        price_low_2 = min(closes[-5:])
        rsi_low_1 = min(rsi_values[-10:-5])
        rsi_low_2 = min(rsi_values[-5:])
        
        price_lower_low = price_low_2 < price_low_1
        rsi_higher_low = rsi_low_2 > rsi_low_1
        
        if price_lower_low and rsi_higher_low:
            return ConditionCheck(
                condition="bullish_divergence_rsi",
                result=ConditionResult.PASSED,
                details={
                    "price_low_1": price_low_1,
                    "price_low_2": price_low_2,
                    "rsi_low_1": rsi_low_1,
                    "rsi_low_2": rsi_low_2
                },
                message=f"Bullish divergence: price lower low ({price_low_2:.2f} < {price_low_1:.2f}), RSI higher low ({rsi_low_2:.1f} > {rsi_low_1:.1f})"
            )
        else:
            return ConditionCheck(
                condition="bullish_divergence_rsi",
                result=ConditionResult.FAILED,
                details={
                    "price_lower_low": price_lower_low,
                    "rsi_higher_low": rsi_higher_low
                },
                message="No bullish divergence detected"
            )
