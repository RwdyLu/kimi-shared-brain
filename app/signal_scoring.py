"""
Strategy Signal Quality Scoring System
Evaluates and scores trading signal quality with multi-factor analysis.
"""
import json
import math
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class SignalStrength(Enum):
    """Signal strength classification."""
    STRONG = "strong"       # Score >= 80
    MODERATE = "moderate"   # Score >= 60
    WEAK = "weak"           # Score >= 40
    POOR = "poor"           # Score < 40
    REJECT = "reject"       # Score < 20


@dataclass
class SignalScore:
    """Individual scoring dimension."""
    name: str
    score: float           # 0-100
    weight: float          # 0-1
    description: str
    raw_value: float       # Original metric value


@dataclass
class SignalQuality:
    """Complete signal quality assessment."""
    signal_id: str
    symbol: str
    strategy: str
    side: str              # 'buy' or 'sell'
    
    # Composite scores
    total_score: float = 0.0
    confidence: float = 0.0  # 0-1
    strength: SignalStrength = SignalStrength.POOR
    
    # Individual scores
    scores: List[SignalScore] = field(default_factory=list)
    
    # Factor analysis
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volatility_score: float = 0.0
    volume_score: float = 0.0
    sentiment_score: float = 0.0
    
    # Risk assessment
    risk_score: float = 0.0
    risk_reward_ratio: float = 0.0
    max_loss_estimate: float = 0.0
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    market_conditions: str = ""
    recommendation: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'signal_id': self.signal_id,
            'symbol': self.symbol,
            'strategy': self.strategy,
            'side': self.side,
            'total_score': self.total_score,
            'confidence': self.confidence,
            'strength': self.strength.value,
            'scores': [
                {
                    'name': s.name,
                    'score': s.score,
                    'weight': s.weight,
                    'description': s.description,
                    'raw_value': s.raw_value
                }
                for s in self.scores
            ],
            'factor_scores': {
                'trend': self.trend_score,
                'momentum': self.momentum_score,
                'volatility': self.volatility_score,
                'volume': self.volume_score,
                'sentiment': self.sentiment_score,
            },
            'risk': {
                'risk_score': self.risk_score,
                'risk_reward_ratio': self.risk_reward_ratio,
                'max_loss_estimate': self.max_loss_estimate,
            },
            'recommendation': self.recommendation,
            'timestamp': self.timestamp.isoformat(),
        }


class SignalQualityScorer:
    """
    Multi-factor signal quality scoring system.
    Evaluates signals across 5 dimensions with weighted scoring.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Default weights for scoring factors
        self.weights = {
            'trend': 0.25,
            'momentum': 0.20,
            'volatility': 0.15,
            'volume': 0.20,
            'sentiment': 0.20,
        }
        
        # Signal history for learning
        self.signal_history: List[Dict] = []
        
        self.logger.info("SignalQualityScorer initialized")
    
    def score_signal(self,
                    signal_id: str,
                    symbol: str,
                    strategy: str,
                    side: str,
                    trend_data: Dict,
                    momentum_data: Dict,
                    volatility_data: Dict,
                    volume_data: Dict,
                    sentiment_data: Dict,
                    risk_data: Dict) -> SignalQuality:
        """
        Score a trading signal across multiple dimensions.
        
        Args:
            signal_id: Unique signal identifier
            symbol: Trading pair
            strategy: Strategy name
            side: 'buy' or 'sell'
            trend_data: Trend analysis data
            momentum_data: Momentum indicators
            volatility_data: Volatility metrics
            volume_data: Volume analysis
            sentiment_data: Market sentiment
            risk_data: Risk parameters
            
        Returns:
            SignalQuality with complete assessment
        """
        quality = SignalQuality(
            signal_id=signal_id,
            symbol=symbol,
            strategy=strategy,
            side=side
        )
        
        # Score each dimension
        trend_score = self._score_trend(trend_data)
        momentum_score = self._score_momentum(momentum_data)
        volatility_score = self._score_volatility(volatility_data)
        volume_score = self._score_volume(volume_data)
        sentiment_score = self._score_sentiment(sentiment_data)
        
        # Store individual scores
        quality.scores = [
            SignalScore("Trend", trend_score, self.weights['trend'],
                       "Price trend alignment", trend_data.get('trend_strength', 0)),
            SignalScore("Momentum", momentum_score, self.weights['momentum'],
                       "Momentum confirmation", momentum_data.get('rsi', 50)),
            SignalScore("Volatility", volatility_score, self.weights['volatility'],
                       "Volatility regime fit", volatility_data.get('atr_percent', 0)),
            SignalScore("Volume", volume_score, self.weights['volume'],
                       "Volume confirmation", volume_data.get('volume_ratio', 1.0)),
            SignalScore("Sentiment", sentiment_score, self.weights['sentiment'],
                       "Market sentiment alignment", sentiment_data.get('sentiment_score', 0)),
        ]
        
        # Store factor scores
        quality.trend_score = trend_score
        quality.momentum_score = momentum_score
        quality.volatility_score = volatility_score
        quality.volume_score = volume_score
        quality.sentiment_score = sentiment_score
        
        # Calculate weighted total score
        quality.total_score = (
            trend_score * self.weights['trend'] +
            momentum_score * self.weights['momentum'] +
            volatility_score * self.weights['volatility'] +
            volume_score * self.weights['volume'] +
            sentiment_score * self.weights['sentiment']
        )
        
        # Assess risk
        quality.risk_score = self._assess_risk(risk_data, quality.total_score)
        quality.risk_reward_ratio = risk_data.get('risk_reward', 1.0)
        quality.max_loss_estimate = risk_data.get('max_loss', 0)
        
        # Calculate confidence based on score consistency
        scores = [trend_score, momentum_score, volatility_score, volume_score, sentiment_score]
        std_dev = self._calculate_std(scores)
        quality.confidence = max(0, 1 - (std_dev / 50))  # Lower std = higher confidence
        
        # Determine strength
        quality.strength = self._classify_strength(quality.total_score)
        
        # Generate recommendation
        quality.recommendation = self._generate_recommendation(quality)
        quality.market_conditions = self._describe_market(trend_data, volatility_data)
        
        # Log result
        self.logger.info(
            f"Signal {signal_id} ({symbol} {side}): "
            f"Score={quality.total_score:.1f}, "
            f"Strength={quality.strength.value}, "
            f"Confidence={quality.confidence:.2%}"
        )
        
        # Store for learning
        self.signal_history.append(quality.to_dict())
        
        return quality
    
    def _score_trend(self, data: Dict) -> float:
        """Score trend alignment (0-100)."""
        trend_strength = data.get('trend_strength', 0)  # 0-1
        trend_direction = data.get('trend_direction', 0)  # -1 to 1
        alignment = data.get('signal_alignment', 0)  # 0-1
        
        # Strong trend + alignment = high score
        score = trend_strength * 50 + alignment * 50
        return min(100, max(0, score))
    
    def _score_momentum(self, data: Dict) -> float:
        """Score momentum confirmation (0-100)."""
        rsi = data.get('rsi', 50)
        macd_signal = data.get('macd_signal', 0)  # -1 to 1
        
        # RSI: 40-60 = neutral, < 30 or > 70 = strong
        rsi_score = 100 - abs(rsi - 50) * 2  # 50 = 100, 0/100 = 0
        
        # MACD confirmation
        macd_score = abs(macd_signal) * 100
        
        score = rsi_score * 0.4 + macd_score * 0.6
        return min(100, max(0, score))
    
    def _score_volatility(self, data: Dict) -> float:
        """Score volatility regime fit (0-100)."""
        atr_percent = data.get('atr_percent', 0)
        volatility_regime = data.get('regime', 'normal')  # 'low', 'normal', 'high'
        
        # Optimal volatility: 1-3% for most strategies
        if atr_percent < 0.5:
            score = 30  # Too low, no movement
        elif atr_percent < 2.0:
            score = 90  # Optimal range
        elif atr_percent < 5.0:
            score = 70  # Manageable
        else:
            score = 40  # Too volatile
        
        # Adjust for regime
        regime_multiplier = {'low': 0.8, 'normal': 1.0, 'high': 0.7}
        score *= regime_multiplier.get(volatility_regime, 1.0)
        
        return min(100, max(0, score))
    
    def _score_volume(self, data: Dict) -> float:
        """Score volume confirmation (0-100)."""
        volume_ratio = data.get('volume_ratio', 1.0)  # Current vs average
        volume_trend = data.get('volume_trend', 0)  # -1 to 1
        
        # Higher than average volume = confirmation
        if volume_ratio > 2.0:
            score = 95
        elif volume_ratio > 1.5:
            score = 85
        elif volume_ratio > 1.0:
            score = 75
        elif volume_ratio > 0.7:
            score = 60
        else:
            score = 40  # Low volume, weak signal
        
        # Volume trend bonus
        if volume_trend > 0:
            score += 10
        
        return min(100, max(0, score))
    
    def _score_sentiment(self, data: Dict) -> float:
        """Score market sentiment alignment (0-100)."""
        sentiment_score = data.get('sentiment_score', 0)  # -1 to 1
        sentiment_trend = data.get('sentiment_trend', 0)  # -1 to 1
        
        # Align sentiment with signal
        # For buy signals: positive sentiment = good
        # For sell signals: negative sentiment = good
        score = abs(sentiment_score) * 80 + 20  # Base 20, max 100
        
        # Trending sentiment bonus
        if abs(sentiment_trend) > 0.3:
            score += 10
        
        return min(100, max(0, score))
    
    def _assess_risk(self, data: Dict, signal_score: float) -> float:
        """Assess risk level (0-100, lower = better)."""
        max_loss = data.get('max_loss', 0)
        account_risk = data.get('account_risk_percent', 0)
        
        # High risk = low score
        if account_risk > 0.05:  # > 5% account risk
            return 20
        elif account_risk > 0.03:
            return 40
        elif account_risk > 0.01:
            return 60
        else:
            return 80
    
    def _calculate_std(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)
    
    def _classify_strength(self, score: float) -> SignalStrength:
        """Classify signal strength."""
        if score >= 80:
            return SignalStrength.STRONG
        elif score >= 60:
            return SignalStrength.MODERATE
        elif score >= 40:
            return SignalStrength.WEAK
        elif score >= 20:
            return SignalStrength.POOR
        else:
            return SignalStrength.REJECT
    
    def _generate_recommendation(self, quality: SignalQuality) -> str:
        """Generate trading recommendation."""
        if quality.strength == SignalStrength.STRONG:
            if quality.risk_reward_ratio >= 2.0:
                return "✅ EXECUTE: Strong signal with favorable R/R"
            else:
                return "⚠️ CONSIDER: Strong signal but R/R is moderate"
        elif quality.strength == SignalStrength.MODERATE:
            if quality.confidence > 0.7:
                return "✅ EXECUTE: Moderate signal with high confidence"
            else:
                return "⏳ WAIT: Moderate signal, wait for confirmation"
        elif quality.strength == SignalStrength.WEAK:
            return "❌ SKIP: Weak signal, avoid this trade"
        else:
            return "❌ REJECT: Poor signal quality, do not trade"
    
    def _describe_market(self, trend_data: Dict, vol_data: Dict) -> str:
        """Describe current market conditions."""
        trend = trend_data.get('trend_direction', 0)
        vol = vol_data.get('atr_percent', 0)
        
        trend_desc = "uptrend" if trend > 0.2 else "downtrend" if trend < -0.2 else "sideways"
        vol_desc = "high volatility" if vol > 3 else "low volatility" if vol < 1 else "normal volatility"
        
        return f"{trend_desc}, {vol_desc}"
    
    def batch_score(self, signals: List[Dict]) -> List[SignalQuality]:
        """Score multiple signals in batch."""
        results = []
        for signal in signals:
            quality = self.score_signal(**signal)
            results.append(quality)
        return results
    
    def get_signal_stats(self, strategy: Optional[str] = None) -> Dict:
        """Get statistics for scored signals."""
        signals = self.signal_history
        
        if strategy:
            signals = [s for s in signals if s.get('strategy') == strategy]
        
        if not signals:
            return {'total': 0}
        
        scores = [s.get('total_score', 0) for s in signals]
        
        return {
            'total': len(signals),
            'avg_score': sum(scores) / len(scores),
            'max_score': max(scores),
            'min_score': min(scores),
            'strong_signals': sum(1 for s in scores if s >= 80),
            'moderate_signals': sum(1 for s in scores if 60 <= s < 80),
            'weak_signals': sum(1 for s in scores if 40 <= s < 60),
            'rejected_signals': sum(1 for s in scores if s < 40),
        }
    
    def save_state(self, filepath: str = "state/signal_scores.json"):
        """Save scoring history."""
        state = {
            'signals': self.signal_history,
            'weights': self.weights,
            'saved_at': datetime.now().isoformat(),
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        
        self.logger.info(f"Signal scores saved to {filepath}")


if __name__ == "__main__":
    # Example usage
    scorer = SignalQualityScorer()
    
    # Score a sample signal
    quality = scorer.score_signal(
        signal_id="SIG_001",
        symbol="BTC/USDT",
        strategy="BTC_4H_MA",
        side="buy",
        trend_data={
            'trend_strength': 0.8,
            'trend_direction': 1,
            'signal_alignment': 0.9
        },
        momentum_data={
            'rsi': 65,
            'macd_signal': 0.7
        },
        volatility_data={
            'atr_percent': 1.5,
            'regime': 'normal'
        },
        volume_data={
            'volume_ratio': 1.8,
            'volume_trend': 0.5
        },
        sentiment_data={
            'sentiment_score': 0.6,
            'sentiment_trend': 0.3
        },
        risk_data={
            'risk_reward': 2.5,
            'max_loss': 100,
            'account_risk_percent': 0.02
        }
    )
    
    print("Signal Quality Assessment")
    print("=" * 50)
    print(f"Signal: {quality.signal_id} ({quality.symbol} {quality.side})")
    print(f"Total Score: {quality.total_score:.1f}/100")
    print(f"Strength: {quality.strength.value.upper()}")
    print(f"Confidence: {quality.confidence:.2%}")
    print(f"R/R Ratio: {quality.risk_reward_ratio:.2f}")
    print(f"\nFactor Scores:")
    print(f"  Trend: {quality.trend_score:.1f}")
    print(f"  Momentum: {quality.momentum_score:.1f}")
    print(f"  Volatility: {quality.volatility_score:.1f}")
    print(f"  Volume: {quality.volume_score:.1f}")
    print(f"  Sentiment: {quality.sentiment_score:.1f}")
    print(f"\nRecommendation: {quality.recommendation}")
    print(f"Market: {quality.market_conditions}")
