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
            # Additional indicator conditions / 額外指標條件
            "supertrend": self._check_supertrend,
            "williams_r": self._check_williams_r,
            "keltner_breakout": self._check_keltner_breakout,
            "atr_breakout": self._check_atr_breakout,
            # Composite strategy conditions (Phase 3)
            "ema_cross_above": self._check_ema_cross_above,
            "rsi_in_range": self._check_rsi_in_range,
            "volume_confirmed": self._check_volume_confirmed,
            "price_above_trend": self._check_price_above_trend,
            "ema_cross_below": self._check_ema_cross_below,
            "rsi_not_overbought": self._check_rsi_not_overbought,
            "rsi_not_oversold": self._check_rsi_not_oversold,
            # P3 Risk Management Conditions / P3 風險管理條件
            "adx_above_25": self._check_adx_above_25,
            "adx_above_20": self._check_adx_above_20,
            "atr_below_threshold": self._check_atr_below_threshold,
            "volume_ema_spike": self._check_volume_ema_spike,
            "price_below_bb_lower_pct": self._check_price_below_bb_lower_pct,
            # Aliases / 條件名別名 (策略使用不同名稱但邏輯相同)
            "parabolic_sar_v2": self._check_sar_below_price,
            "adx_above_18": self._check_adx_above_20,
            "adx_above_28": self._check_adx_above_25,
            "rsi_extreme": self._check_rsi_below_30,
            "price_vs_bollinger": self._check_price_below_bb_lower_pct,
            "volume_confirm": self._check_volume_confirmed,
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
    
    def strategy_passed(self, results: List[ConditionCheck], min_passed: Optional[int] = None) -> bool:
        """
        Check if overall strategy passed.
        Default: ALL conditions must pass (AND logic).
        Optional: min_passed=N for N-of-M voting (e.g. 2 of 3).

        Args:
            results: List of condition check results
            min_passed: Minimum number of conditions that must pass (None = all)
        """
        if not results:
            return False
        
        passed_count = sum(1 for r in results if r.result == ConditionResult.PASSED)
        
        if min_passed is not None:
            return passed_count >= min_passed
        
        return passed_count == len(results)

    @staticmethod
    def estimate_min_passed(condition_count: int) -> int:
        """Estimate minimum conditions to require based on total count.

        - 2 conditions: require both (2/2)
        - 3 conditions: require 2/3 (loosen)
        - 4+ conditions: require 3/4 or floor(count * 0.75)
        """
        if condition_count <= 2:
            return condition_count
        if condition_count == 3:
            return 2
        return max(2, condition_count - 1)
    
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
        """Check if RSI crosses above 40 / 檢查RSI是否上穿40

        條件：前一根 RSI < 40，當前 RSI > 40（穿越）
        不是只看當前 RSI > 40
        """
        rsi = data.get("rsi")
        prev_rsi = data.get("prev_rsi")
        
        if rsi is None:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="RSI data missing"
            )
        
        # 需要前一根 RSI 來判斷穿越
        if prev_rsi is None:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.FAILED,
                details={"rsi": rsi},
                message=f"RSI {rsi:.1f} — need prev RSI for cross detection"
            )
        
        # RSI 從 40 以下穿越到 40 以上
        if prev_rsi <= 40 and rsi > 40:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.PASSED,
                details={"rsi": rsi, "prev_rsi": prev_rsi},
                message=f"RSI cross above 40: {prev_rsi:.1f} → {rsi:.1f}"
            )
        else:
            return ConditionCheck(
                condition="rsi_cross_above_40",
                result=ConditionResult.FAILED,
                details={"rsi": rsi, "prev_rsi": prev_rsi},
                message=f"RSI {rsi:.1f} (prev {prev_rsi:.1f}) — no cross above 40"
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

    # ===================================================================
    # Additional indicator conditions / 額外指標條件
    # ===================================================================

    def _check_supertrend(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check Supertrend bullish signal / 檢查 Supertrend 翻多訊號
        
        ATR proxy: 用最近 14 根的 high-low 範圍
        Supertrend 翻多：價格在 MA20 上方且有 ATR 支撐
        """
        atr = data.get("atr", 0)
        price = data.get("price", 0)
        ma20 = data.get("ma20", 0)
        
        if not price or not ma20:
            return ConditionCheck(
                condition="supertrend",
                result=ConditionResult.MISSING_DATA,
                details={"price": price, "ma20": ma20, "atr": atr},
                message="Missing price or MA20 data for Supertrend"
            )
        
        if price > ma20 and atr > 0:
            return ConditionCheck(
                condition="supertrend",
                result=ConditionResult.PASSED,
                details={"price": price, "ma20": ma20, "atr": atr},
                message=f"Supertrend bullish: price ${price:,.2f} above MA20 ${ma20:,.2f}"
            )
        return ConditionCheck(
            condition="supertrend",
            result=ConditionResult.FAILED,
            details={"price": price, "ma20": ma20, "atr": atr},
            message=f"Supertrend bearish: price ${price:,.2f} vs MA20 ${ma20:,.2f}"
        )

    def _check_williams_r(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check Williams %R oversold / 檢查 Williams %R 超賣
        
        Williams %R 用 Stochastic 近似：K < 20 = 超賣
        """
        stoch_k = data.get("stoch_fastk", 50)
        # Williams %R 用 Stochastic 近似：K - 100
        wr_approx = stoch_k - 100
        threshold = params.get("threshold", -80)
        
        if stoch_k is None:
            return ConditionCheck(
                condition="williams_r",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing Stochastic FastK data for Williams %R"
            )
        
        if wr_approx < threshold:
            return ConditionCheck(
                condition="williams_r",
                result=ConditionResult.PASSED,
                details={"wr_approx": wr_approx, "threshold": threshold, "stoch_k": stoch_k},
                message=f"Williams %R {wr_approx:.1f} below {threshold} (oversold)"
            )
        return ConditionCheck(
            condition="williams_r",
            result=ConditionResult.FAILED,
            details={"wr_approx": wr_approx, "threshold": threshold, "stoch_k": stoch_k},
            message=f"Williams %R {wr_approx:.1f} not oversold (threshold {threshold})"
        )

    def _check_keltner_breakout(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check Keltner channel breakout / 檢查 Keltner Channel 突破
        
        用 MA20 + 2*ATR 作為上軌 proxy
        """
        price = data.get("price", 0)
        ma20 = data.get("ma20", 0)
        atr = data.get("atr", data.get("bb_upper", 0) - data.get("ma20", 0))
        upper = ma20 + 2 * atr if atr and ma20 else ma20 * 1.02 if ma20 else 0
        
        if not price or not ma20:
            return ConditionCheck(
                condition="keltner_breakout",
                result=ConditionResult.MISSING_DATA,
                details={"price": price, "ma20": ma20, "atr": atr},
                message="Missing price or MA20 data for Keltner breakout"
            )
        
        if price > upper:
            return ConditionCheck(
                condition="keltner_breakout",
                result=ConditionResult.PASSED,
                details={"price": price, "ma20": ma20, "atr": atr, "upper": upper},
                message=f"Price ${price:,.2f} broke above Keltner upper ${upper:,.2f}"
            )
        return ConditionCheck(
            condition="keltner_breakout",
            result=ConditionResult.FAILED,
            details={"price": price, "ma20": ma20, "atr": atr, "upper": upper},
            message=f"Price ${price:,.2f} below Keltner upper ${upper:,.2f}"
        )

    def _check_atr_breakout(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check ATR breakout / 檢查 ATR 突破
        
        ATR breakout proxy: 價格突破 MA5 且 MA5 > MA20
        """
        price = data.get("price", 0)
        ma5 = data.get("ma5", 0)
        ma20 = data.get("ma20", 0)
        
        if not price or not ma5 or not ma20:
            return ConditionCheck(
                condition="atr_breakout",
                result=ConditionResult.MISSING_DATA,
                details={"price": price, "ma5": ma5, "ma20": ma20},
                message="Missing price, MA5 or MA20 data for ATR breakout"
            )
        
        if price > ma5 and ma5 > ma20:
            return ConditionCheck(
                condition="atr_breakout",
                result=ConditionResult.PASSED,
                details={"price": price, "ma5": ma5, "ma20": ma20},
                message=f"ATR breakout: price ${price:,.2f} > MA5 ${ma5:,.2f} > MA20 ${ma20:,.2f}"
            )
        return ConditionCheck(
            condition="atr_breakout",
            result=ConditionResult.FAILED,
            details={"price": price, "ma5": ma5, "ma20": ma20},
            message=f"ATR breakout not confirmed: price ${price:,.2f}, MA5 ${ma5:,.2f}, MA20 ${ma20:,.2f}"
        )

    # ===================================================================
    # Composite Strategy Conditions (Phase 3 — Profitability Sprint)
    # EMA crossover + RSI filter + volume confirmation
    # ===================================================================

    def _check_ema_cross_above(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check EMA fast crosses above EMA slow / 檢查短期EMA上穿長期EMA

        Uses ema_fast and ema_slow from data, or falls back to ma5/ma20.
        Detects cross by comparing current and previous values.
        """
        ema_fast = data.get("ema_fast") or data.get("ema5") or data.get("ma5")
        ema_slow = data.get("ema_slow") or data.get("ema20") or data.get("ma20")
        ema_fast_prev = data.get("ema_fast_prev") or data.get("ema5_prev") or data.get("ma5_prev")
        ema_slow_prev = data.get("ema_slow_prev") or data.get("ema20_prev") or data.get("ma20_prev")
        closes = data.get("closes")

        if ema_fast is None or ema_slow is None:
            if closes and len(closes) >= 20:
                try:
                    alpha_fast = 2 / (params.get("ema_fast_period", 8) + 1)
                    alpha_slow = 2 / (params.get("ema_slow_period", 21) + 1)
                    ema_fast_arr = self._compute_ema(closes, alpha_fast)
                    ema_slow_arr = self._compute_ema(closes, alpha_slow)
                    ema_fast = ema_fast_arr[-1]
                    ema_slow = ema_slow_arr[-1]
                    ema_fast_prev = ema_fast_arr[-2] if len(ema_fast_arr) >= 2 else ema_fast
                    ema_slow_prev = ema_slow_arr[-2] if len(ema_slow_arr) >= 2 else ema_slow
                except Exception:
                    return ConditionCheck(
                        condition="ema_cross_above",
                        result=ConditionResult.MISSING_DATA,
                        details={},
                        message="Missing EMA data and could not compute from closes"
                    )
            else:
                return ConditionCheck(
                    condition="ema_cross_above",
                    result=ConditionResult.MISSING_DATA,
                    details={},
                    message="Missing EMA fast/slow data and insufficient close history"
                )

        cross = ema_fast > ema_slow and (ema_fast_prev is None or ema_fast_prev <= ema_slow_prev)
        if cross:
            return ConditionCheck(
                condition="ema_cross_above",
                result=ConditionResult.PASSED,
                details={"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_fast_prev": ema_fast_prev, "ema_slow_prev": ema_slow_prev},
                message=f"EMA cross above: fast {ema_fast:.2f} > slow {ema_slow:.2f}"
            )
        return ConditionCheck(
            condition="ema_cross_above",
            result=ConditionResult.FAILED,
            details={"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_fast_prev": ema_fast_prev, "ema_slow_prev": ema_slow_prev},
            message=f"EMA cross not detected: fast {ema_fast:.2f}, slow {ema_slow:.2f}"
        )

    def _check_ema_cross_below(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check EMA fast crosses below EMA slow / 檢查短期EMA下穿長期EMA"""
        ema_fast = data.get("ema_fast") or data.get("ema5") or data.get("ma5")
        ema_slow = data.get("ema_slow") or data.get("ema20") or data.get("ma20")
        ema_fast_prev = data.get("ema_fast_prev") or data.get("ema5_prev") or data.get("ma5_prev")
        ema_slow_prev = data.get("ema_slow_prev") or data.get("ema20_prev") or data.get("ma20_prev")
        closes = data.get("closes")

        if ema_fast is None or ema_slow is None:
            if closes and len(closes) >= 20:
                try:
                    alpha_fast = 2 / (params.get("ema_fast_period", 8) + 1)
                    alpha_slow = 2 / (params.get("ema_slow_period", 21) + 1)
                    ema_fast_arr = self._compute_ema(closes, alpha_fast)
                    ema_slow_arr = self._compute_ema(closes, alpha_slow)
                    ema_fast = ema_fast_arr[-1]
                    ema_slow = ema_slow_arr[-1]
                    ema_fast_prev = ema_fast_arr[-2] if len(ema_fast_arr) >= 2 else ema_fast
                    ema_slow_prev = ema_slow_arr[-2] if len(ema_slow_arr) >= 2 else ema_slow
                except Exception:
                    return ConditionCheck(
                        condition="ema_cross_below",
                        result=ConditionResult.MISSING_DATA,
                        details={},
                        message="Missing EMA data and could not compute from closes"
                    )
            else:
                return ConditionCheck(
                    condition="ema_cross_below",
                    result=ConditionResult.MISSING_DATA,
                    details={},
                    message="Missing EMA fast/slow data and insufficient close history"
                )

        cross = ema_fast < ema_slow and (ema_fast_prev is None or ema_fast_prev >= ema_slow_prev)
        if cross:
            return ConditionCheck(
                condition="ema_cross_below",
                result=ConditionResult.PASSED,
                details={"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_fast_prev": ema_fast_prev, "ema_slow_prev": ema_slow_prev},
                message=f"EMA cross below: fast {ema_fast:.2f} < slow {ema_slow:.2f}"
            )
        return ConditionCheck(
            condition="ema_cross_below",
            result=ConditionResult.FAILED,
            details={"ema_fast": ema_fast, "ema_slow": ema_slow, "ema_fast_prev": ema_fast_prev, "ema_slow_prev": ema_slow_prev},
            message=f"EMA cross below not detected: fast {ema_fast:.2f}, slow {ema_slow:.2f}"
        )

    def _check_rsi_in_range(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check RSI is within a healthy range / 檢查RSI在健康區間. Default: 45-65."""
        rsi = data.get("rsi")
        closes = data.get("closes")
        rsi_values = data.get("rsi_values")

        if rsi is None:
            if rsi_values and len(rsi_values) >= 1:
                rsi = rsi_values[-1]
            elif closes and len(closes) >= 14:
                try:
                    rsi = self._compute_rsi(closes, 14)
                except Exception:
                    return ConditionCheck(
                        condition="rsi_in_range",
                        result=ConditionResult.MISSING_DATA,
                        details={},
                        message="Missing RSI data and could not compute from closes"
                    )
            else:
                return ConditionCheck(
                    condition="rsi_in_range",
                    result=ConditionResult.MISSING_DATA,
                    details={},
                    message="Missing RSI data and insufficient close history"
                )

        rsi_min = params.get("rsi_min", 45)
        rsi_max = params.get("rsi_max", 65)

        if rsi_min <= rsi <= rsi_max:
            return ConditionCheck(
                condition="rsi_in_range",
                result=ConditionResult.PASSED,
                details={"rsi": rsi, "rsi_min": rsi_min, "rsi_max": rsi_max},
                message=f"RSI {rsi:.1f} in range [{rsi_min}, {rsi_max}]"
            )
        return ConditionCheck(
            condition="rsi_in_range",
            result=ConditionResult.FAILED,
            details={"rsi": rsi, "rsi_min": rsi_min, "rsi_max": rsi_max},
            message=f"RSI {rsi:.1f} outside range [{rsi_min}, {rsi_max}]"
        )

    def _check_rsi_not_overbought(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check RSI is not overbought (for long entries) / 檢查RSI未超買"""
        rsi = data.get("rsi")
        closes = data.get("closes")
        rsi_values = data.get("rsi_values")

        if rsi is None:
            if rsi_values and len(rsi_values) >= 1:
                rsi = rsi_values[-1]
            elif closes and len(closes) >= 14:
                try:
                    rsi = self._compute_rsi(closes, 14)
                except Exception:
                    return ConditionCheck(
                        condition="rsi_not_overbought",
                        result=ConditionResult.MISSING_DATA,
                        details={},
                        message="Missing RSI data"
                    )
            else:
                return ConditionCheck(
                    condition="rsi_not_overbought",
                    result=ConditionResult.MISSING_DATA,
                    details={},
                    message="Missing RSI data"
                )

        threshold = params.get("rsi_overbought", 70)
        if rsi < threshold:
            return ConditionCheck(
                condition="rsi_not_overbought",
                result=ConditionResult.PASSED,
                details={"rsi": rsi, "threshold": threshold},
                message=f"RSI {rsi:.1f} below overbought threshold {threshold}"
            )
        return ConditionCheck(
            condition="rsi_not_overbought",
            result=ConditionResult.FAILED,
            details={"rsi": rsi, "threshold": threshold},
            message=f"RSI {rsi:.1f} overbought (threshold {threshold})"
        )

    def _check_rsi_not_oversold(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check RSI is not oversold (for short entries) / 檢查RSI未超賣"""
        rsi = data.get("rsi")
        closes = data.get("closes")
        rsi_values = data.get("rsi_values")

        if rsi is None:
            if rsi_values and len(rsi_values) >= 1:
                rsi = rsi_values[-1]
            elif closes and len(closes) >= 14:
                try:
                    rsi = self._compute_rsi(closes, 14)
                except Exception:
                    return ConditionCheck(
                        condition="rsi_not_oversold",
                        result=ConditionResult.MISSING_DATA,
                        details={},
                        message="Missing RSI data"
                    )
            else:
                return ConditionCheck(
                    condition="rsi_not_oversold",
                    result=ConditionResult.MISSING_DATA,
                    details={},
                    message="Missing RSI data"
                )

        threshold = params.get("rsi_oversold", 30)
        if rsi > threshold:
            return ConditionCheck(
                condition="rsi_not_oversold",
                result=ConditionResult.PASSED,
                details={"rsi": rsi, "threshold": threshold},
                message=f"RSI {rsi:.1f} above oversold threshold {threshold}"
            )
        return ConditionCheck(
            condition="rsi_not_oversold",
            result=ConditionResult.FAILED,
            details={"rsi": rsi, "threshold": threshold},
            message=f"RSI {rsi:.1f} oversold (threshold {threshold})"
        )

    def _check_volume_confirmed(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check volume is above average with configurable multiplier / 檢查成交量高於均量"""
        volume_ratio = data.get("volume_ratio")
        current_volume = data.get("volume")
        volumes = data.get("volumes")

        if volume_ratio is None:
            if current_volume and volumes and len(volumes) >= 10:
                avg_volume = sum(volumes[-10:]) / len(volumes[-10:])
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            else:
                return ConditionCheck(
                    condition="volume_confirmed",
                    result=ConditionResult.MISSING_DATA,
                    details={},
                    message="Missing volume ratio and insufficient volume history"
                )

        multiplier = params.get("volume_multiplier", 1.2)
        if volume_ratio >= multiplier:
            return ConditionCheck(
                condition="volume_confirmed",
                result=ConditionResult.PASSED,
                details={"volume_ratio": volume_ratio, "multiplier": multiplier},
                message=f"Volume {volume_ratio:.2f}x above threshold {multiplier}x"
            )
        return ConditionCheck(
            condition="volume_confirmed",
            result=ConditionResult.FAILED,
            details={"volume_ratio": volume_ratio, "multiplier": multiplier},
            message=f"Volume {volume_ratio:.2f}x below threshold {multiplier}x"
        )

    def _check_price_above_trend(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Check price is above long-term trend MA / 檢查價格高於長期趨勢均線"""
        price = data.get("price")
        ma_trend = data.get("ma_trend") or data.get("ma240") or data.get("ma100")
        closes = data.get("closes")

        if price is None or ma_trend is None:
            if closes and len(closes) >= 100:
                try:
                    import numpy as np
                    ma_trend = np.mean(closes[-100:])
                except Exception:
                    return ConditionCheck(
                        condition="price_above_trend",
                        result=ConditionResult.MISSING_DATA,
                        details={},
                        message="Missing price/MA trend and could not compute"
                    )
            else:
                return ConditionCheck(
                    condition="price_above_trend",
                    result=ConditionResult.MISSING_DATA,
                    details={"price": price, "ma_trend": ma_trend},
                    message="Missing price or long-term MA data"
                )

        if price > ma_trend:
            return ConditionCheck(
                condition="price_above_trend",
                result=ConditionResult.PASSED,
                details={"price": price, "ma_trend": ma_trend},
                message=f"Price ${price:.2f} above trend MA ${ma_trend:.2f}"
            )
        return ConditionCheck(
            condition="price_above_trend",
            result=ConditionResult.FAILED,
            details={"price": price, "ma_trend": ma_trend},
            message=f"Price ${price:.2f} below trend MA ${ma_trend:.2f}"
        )

    # -------------------------------------------------------------------
    # Utility methods for composite conditions
    # -------------------------------------------------------------------

    @staticmethod
    def _compute_ema(values: List[float], alpha: float) -> List[float]:
        """Compute exponential moving average from a list of values."""
        if not values:
            return []
        ema = [values[0]]
        for v in values[1:]:
            ema.append(alpha * v + (1 - alpha) * ema[-1])
        return ema

    @staticmethod
    def _compute_rsi(closes: List[float], period: int = 14) -> float:
        """Compute RSI from a list of close prices. Returns last RSI value."""
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0) for d in deltas[-period:]]
        losses = [abs(min(d, 0)) for d in deltas[-period:]]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    # ===== P3 Risk Management Conditions / P3 風險管理條件 =====

    def _check_adx_above_25(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """ADX > 25: strong trend filter / ADX 趨勢強度過濾 (強趨勢)"""
        adx = data.get("adx14")
        if adx is None:
            return ConditionCheck(
                condition="adx_above_25",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing ADX14 data"
            )
        threshold = params.get("adx_threshold", 25)
        if adx >= threshold:
            return ConditionCheck(
                condition="adx_above_25",
                result=ConditionResult.PASSED,
                details={"adx": adx, "threshold": threshold},
                message=f"ADX {adx:.1f} ≥ {threshold} (strong trend)"
            )
        return ConditionCheck(
            condition="adx_above_25",
            result=ConditionResult.FAILED,
            details={"adx": adx, "threshold": threshold},
            message=f"ADX {adx:.1f} < {threshold} (weak/no trend)"
        )

    def _check_adx_above_20(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """ADX > 20: moderate trend filter / ADX 趨勢強度過濾 (中等趨勢)"""
        adx = data.get("adx14")
        if adx is None:
            return ConditionCheck(
                condition="adx_above_20",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing ADX14 data"
            )
        threshold = params.get("adx_threshold", 20)
        if adx >= threshold:
            return ConditionCheck(
                condition="adx_above_20",
                result=ConditionResult.PASSED,
                details={"adx": adx, "threshold": threshold},
                message=f"ADX {adx:.1f} ≥ {threshold} (moderate trend)"
            )
        return ConditionCheck(
            condition="adx_above_20",
            result=ConditionResult.FAILED,
            details={"adx": adx, "threshold": threshold},
            message=f"ADX {adx:.1f} < {threshold} (no trend)"
        )

    def _check_atr_below_threshold(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """ATR below threshold: low volatility filter / ATR 低波動過濾"""
        atr = data.get("atr14")
        price = data.get("price")
        if atr is None or price is None or price <= 0:
            return ConditionCheck(
                condition="atr_below_threshold",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing ATR or price data"
            )
        atr_pct = atr / price
        threshold = params.get("atr_threshold", 0.02)
        if atr_pct <= threshold:
            return ConditionCheck(
                condition="atr_below_threshold",
                result=ConditionResult.PASSED,
                details={"atr_pct": atr_pct, "threshold": threshold},
                message=f"ATR {atr_pct*100:.2f}% ≤ {threshold*100:.2f}% (low volatility)"
            )
        return ConditionCheck(
            condition="atr_below_threshold",
            result=ConditionResult.FAILED,
            details={"atr_pct": atr_pct, "threshold": threshold},
            message=f"ATR {atr_pct*100:.2f}% > {threshold*100:.2f}% (high volatility)"
        )

    def _check_volume_ema_spike(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Volume > EMA20 × multiplier / 成交量爆發 (Strategy005 風格)"""
        current_volume = data.get("volume")
        volume_ema20 = data.get("volume_ema20")
        
        # Fallback: compute from volumes list if EMA not available
        if volume_ema20 is None:
            volumes = data.get("volumes")
            if volumes and len(volumes) >= 20:
                try:
                    from indicators.calculator import calculate_ema
                    ema_list = calculate_ema(volumes, period=20)
                    volume_ema20 = ema_list[-1] if ema_list else None
                except Exception:
                    volume_ema20 = None
        
        if current_volume is None or volume_ema20 is None or volume_ema20 <= 0:
            return ConditionCheck(
                condition="volume_ema_spike",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing volume or volume EMA20 data"
            )
        
        multiplier = params.get("volume_multiplier", 4.0)
        ratio = current_volume / volume_ema20
        if ratio >= multiplier:
            return ConditionCheck(
                condition="volume_ema_spike",
                result=ConditionResult.PASSED,
                details={"ratio": ratio, "multiplier": multiplier},
                message=f"Volume {ratio:.1f}x EMA20 (threshold {multiplier}x)"
            )
        return ConditionCheck(
            condition="volume_ema_spike",
            result=ConditionResult.FAILED,
            details={"ratio": ratio, "multiplier": multiplier},
            message=f"Volume {ratio:.1f}x EMA20 below {multiplier}x"
        )

    def _check_price_below_bb_lower_pct(self, data: Dict[str, Any], params: Dict[str, Any]) -> ConditionCheck:
        """Price < BB lower × pct / 價格低於布林下軌 (ClucMay72018 風格)"""
        price = data.get("price")
        bb_lower = data.get("bb_lower")
        if price is None or bb_lower is None or bb_lower <= 0:
            return ConditionCheck(
                condition="price_below_bb_lower_pct",
                result=ConditionResult.MISSING_DATA,
                details={},
                message="Missing price or BB lower band data"
            )
        pct = params.get("bb_lower_pct", 0.985)
        threshold = bb_lower * pct
        if price <= threshold:
            return ConditionCheck(
                condition="price_below_bb_lower_pct",
                result=ConditionResult.PASSED,
                details={"price": price, "bb_lower": bb_lower, "threshold": threshold},
                message=f"Price ${price:,.2f} ≤ BB lower × {pct} (${threshold:,.2f})"
            )
        return ConditionCheck(
            condition="price_below_bb_lower_pct",
            result=ConditionResult.FAILED,
            details={"price": price, "bb_lower": bb_lower, "threshold": threshold},
            message=f"Price ${price:,.2f} > BB lower × {pct} (${threshold:,.2f})"
        )

