"""
Breakout Strategy - Generate signals on price breakouts from consolidation.
Detects breaks above/below recent highs/lows with volume confirmation.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.bot.strategy_base import TechnicalStrategy, StrategySignal, StrategyConfig

class BreakoutStrategy(TechnicalStrategy):
    """
    Breakout Strategy generates signals when price breaks above/below recent levels.
    Uses relaxed parameters and multiple timeframes for maximum signal generation.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Relaxed parameters for maximum signal generation
        params = config.parameters
        self.lookback_period = params.get('lookback_period', 10)           # Period to find highs/lows
        self.breakout_threshold = params.get('breakout_threshold', 0.002)  # 0.2% minimum breakout
        self.volume_confirmation = params.get('volume_confirmation', 1.1)  # 1.1x volume requirement
        self.retest_tolerance = params.get('retest_tolerance', 0.001)      # 0.1% retest tolerance
        self.min_consolidation = params.get('min_consolidation', 3)        # Minimum candles for consolidation
        self.stop_loss_atr_multiplier = params.get('stop_loss_atr_multiplier', 2.0)
        self.take_profit_atr_multiplier = params.get('take_profit_atr_multiplier', 3.0)
        
        # Required indicators
        self.required_indicators = ['volume_ratio']
        
        self.logger.info(f"Breakout Strategy initialized with {self.lookback_period} period lookback")
    
    def analyze_market(self, data: pd.DataFrame, current_price: float) -> List[StrategySignal]:
        """Analyze market data for breakout signals."""
        signals = []
        
        if not self.is_enabled or not self.check_data_requirements(data):
            return signals
        
        # Need enough data for breakout analysis
        if len(data) < self.lookback_period + 5:
            return signals
        
        current_candle = data.iloc[-1]
        
        # Find recent highs and lows
        recent_data = data.tail(self.lookback_period + 1).iloc[:-1]  # Exclude current candle
        recent_high = recent_data['high'].max()
        recent_low = recent_data['low'].min()
        
        current_high = current_candle['high']
        current_low = current_candle['low']
        current_close = current_candle['close']
        
        self.logger.info(f"Breakout analysis - Recent high: {recent_high:.2f}, Recent low: {recent_low:.2f}, Current: {current_close:.2f}")
        
        # Check for bullish breakout (break above recent high)
        bullish_signal = self._detect_bullish_breakout(data, current_candle, recent_high, recent_low)
        if bullish_signal:
            signals.append(bullish_signal)
        
        # Check for bearish breakout (break below recent low)
        bearish_signal = self._detect_bearish_breakout(data, current_candle, recent_high, recent_low)
        if bearish_signal:
            signals.append(bearish_signal)
        
        return signals
    
    def _detect_bullish_breakout(self, data: pd.DataFrame, current: pd.Series, 
                                recent_high: float, recent_low: float) -> Optional[StrategySignal]:
        """Detect bullish breakout above recent high."""
        
        current_high = current['high']
        current_close = current['close']
        
        # Calculate breakout strength
        breakout_pct = (current_high - recent_high) / recent_high
        
        self.logger.info(f"Checking bullish breakout: current_high={current_high:.2f}, recent_high={recent_high:.2f}, breakout={breakout_pct:.4f}")
        
        # Conditions for bullish breakout:
        # 1. Current high breaks above recent high
        if breakout_pct < self.breakout_threshold:
            self.logger.info(f"Breakout too small: {breakout_pct:.4f} < {self.breakout_threshold:.4f}")
            return None
        
        # 2. Close should be near the high (strong breakout)
        close_strength = (current_close - current['low']) / (current_high - current['low']) if current_high > current['low'] else 1.0
        if close_strength < 0.7:  # Close in upper 30% of candle
            self.logger.info(f"Close not strong enough: {close_strength:.2f} < 0.7")
            return None
        
        # 3. Volume confirmation (relaxed)
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.volume_confirmation:
            self.logger.info(f"Volume confirmation failed: {volume_ratio:.2f} < {self.volume_confirmation}")
            return None
        
        # 4. Check for previous consolidation
        consolidation_score = self._calculate_consolidation_score(data, recent_high, recent_low)
        
        # Calculate confidence
        confidence = self._calculate_breakout_confidence(breakout_pct, close_strength, volume_ratio, consolidation_score, 'LONG')
        
        if confidence < self.config.min_confidence:
            self.logger.info(f"Confidence too low: {confidence:.2f} < {self.config.min_confidence}")
            return None
        
        # Create signal
        entry_price = current_close
        atr = self._estimate_atr(data)
        
        # Use recent low as stop loss reference
        stop_loss = max(recent_low - atr, entry_price - (self.stop_loss_atr_multiplier * atr))
        take_profit = entry_price + (self.take_profit_atr_multiplier * atr)
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=getattr(current, 'name', 'UNKNOWN'),
            signal_type='LONG',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                'strategy_name': self.name,
                'pattern': 'bullish_breakout',
                'breakout_level': recent_high,
                'breakout_percentage': breakout_pct,
                'close_strength': close_strength,
                'volume_ratio': volume_ratio,
                'consolidation_score': consolidation_score
            }
        )
        
        self.logger.info(f"Bullish breakout signal: price={entry_price:.2f}, confidence={confidence:.2f}, breakout={breakout_pct:.3f}")
        return signal
    
    def _detect_bearish_breakout(self, data: pd.DataFrame, current: pd.Series,
                                recent_high: float, recent_low: float) -> Optional[StrategySignal]:
        """Detect bearish breakout below recent low."""
        
        current_low = current['low']
        current_close = current['close']
        
        # Calculate breakout strength
        breakout_pct = (recent_low - current_low) / recent_low
        
        self.logger.info(f"Checking bearish breakout: current_low={current_low:.2f}, recent_low={recent_low:.2f}, breakout={breakout_pct:.4f}")
        
        # Conditions for bearish breakout:
        # 1. Current low breaks below recent low
        if breakout_pct < self.breakout_threshold:
            self.logger.info(f"Breakout too small: {breakout_pct:.4f} < {self.breakout_threshold:.4f}")
            return None
        
        # 2. Close should be near the low (strong breakout)
        close_strength = (current['high'] - current_close) / (current['high'] - current_low) if current['high'] > current_low else 1.0
        if close_strength < 0.7:  # Close in lower 30% of candle
            self.logger.info(f"Close not strong enough: {close_strength:.2f} < 0.7")
            return None
        
        # 3. Volume confirmation (relaxed)
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.volume_confirmation:
            self.logger.info(f"Volume confirmation failed: {volume_ratio:.2f} < {self.volume_confirmation}")
            return None
        
        # 4. Check for previous consolidation
        consolidation_score = self._calculate_consolidation_score(data, recent_high, recent_low)
        
        # Calculate confidence
        confidence = self._calculate_breakout_confidence(breakout_pct, close_strength, volume_ratio, consolidation_score, 'SHORT')
        
        if confidence < self.config.min_confidence:
            self.logger.info(f"Confidence too low: {confidence:.2f} < {self.config.min_confidence}")
            return None
        
        # Create signal
        entry_price = current_close
        atr = self._estimate_atr(data)
        
        # Use recent high as stop loss reference
        stop_loss = min(recent_high + atr, entry_price + (self.stop_loss_atr_multiplier * atr))
        take_profit = entry_price - (self.take_profit_atr_multiplier * atr)
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=getattr(current, 'name', 'UNKNOWN'),
            signal_type='SHORT',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                'strategy_name': self.name,
                'pattern': 'bearish_breakout',
                'breakout_level': recent_low,
                'breakout_percentage': breakout_pct,
                'close_strength': close_strength,
                'volume_ratio': volume_ratio,
                'consolidation_score': consolidation_score
            }
        )
        
        self.logger.info(f"Bearish breakout signal: price={entry_price:.2f}, confidence={confidence:.2f}, breakout={breakout_pct:.3f}")
        return signal
    
    def _calculate_consolidation_score(self, data: pd.DataFrame, recent_high: float, recent_low: float) -> float:
        """Calculate quality of previous consolidation."""
        score = 0.0
        
        # Check if there was actually consolidation before breakout
        consolidation_data = data.tail(self.lookback_period + 3).iloc[:-1]  # Exclude current candle
        
        if len(consolidation_data) < self.min_consolidation:
            return 0.1  # Minimal score for insufficient data
        
        # 1. Range tightness (0.4 weight)
        range_size = (recent_high - recent_low) / recent_low
        if range_size < 0.02:  # Less than 2% range
            score += 0.4
        elif range_size < 0.04:  # Less than 4% range
            score += 0.2
        
        # 2. Number of tests of levels (0.3 weight)
        high_tests = 0
        low_tests = 0
        
        for _, candle in consolidation_data.iterrows():
            # Count touches of recent high/low levels
            high_tolerance = recent_high * (1 - self.retest_tolerance)
            low_tolerance = recent_low * (1 + self.retest_tolerance)
            
            if candle['high'] >= high_tolerance:
                high_tests += 1
            if candle['low'] <= low_tolerance:
                low_tests += 1
        
        if high_tests >= 2 and low_tests >= 2:
            score += 0.3
        elif high_tests >= 1 and low_tests >= 1:
            score += 0.15
        
        # 3. Time spent in consolidation (0.3 weight)
        if len(consolidation_data) >= self.min_consolidation:
            score += min(len(consolidation_data) / (self.lookback_period * 2), 1.0) * 0.3
        
        return min(score, 1.0)
    
    def _calculate_breakout_confidence(self, breakout_pct: float, close_strength: float,
                                     volume_ratio: float, consolidation_score: float, direction: str) -> float:
        """Calculate confidence for breakout signal."""
        confidence = 0.0
        
        # Breakout strength (0.3 weight)
        breakout_score = min(breakout_pct / (self.breakout_threshold * 3), 1.0)
        confidence += breakout_score * 0.3
        
        # Close position strength (0.2 weight)
        confidence += close_strength * 0.2
        
        # Volume confirmation (0.3 weight)
        volume_score = min(volume_ratio / self.volume_confirmation, 2.0) / 2.0
        confidence += volume_score * 0.3
        
        # Previous consolidation quality (0.2 weight)
        confidence += consolidation_score * 0.2
        
        return min(confidence, 1.0)
    
    def _estimate_atr(self, data: pd.DataFrame) -> float:
        """Estimate ATR from available data."""
        if 'atr' in data.columns:
            return data['atr'].iloc[-1]
        
        # Calculate simple ATR approximation
        recent_data = data.tail(self.lookback_period)
        highs = recent_data['high']
        lows = recent_data['low']
        ranges = highs - lows
        return ranges.mean()
    
    def validate_signal(self, signal: StrategySignal, market_context: Dict) -> bool:
        """Validate breakout signal."""
        
        # Check breakout strength
        breakout_pct = signal.metadata.get('breakout_percentage', 0)
        if breakout_pct < self.breakout_threshold:
            self.logger.warning(f"Breakout signal rejected - insufficient breakout: {breakout_pct:.4f}")
            return False
        
        # Only reject in extreme volatility
        volatility = market_context.get('volatility_regime', 'NORMAL')
        if volatility == 'EXTREME':
            self.logger.warning(f"Breakout signal rejected due to extreme volatility")
            return False
        
        return True
    
    def calculate_position_size(self, signal: StrategySignal, account_balance: float) -> float:
        """Calculate position size for breakout signal."""
        
        # Larger position size for high-confidence breakouts
        base_position_pct = 0.03  # 3% of account
        
        # Adjust based on signal confidence and breakout strength
        confidence_multiplier = signal.confidence
        breakout_pct = signal.metadata.get('breakout_percentage', 0.002)
        breakout_multiplier = min(breakout_pct / self.breakout_threshold, 2.0) / 2.0 + 0.5  # 0.5 to 1.0
        
        # Adjust based on consolidation quality
        consolidation_score = signal.metadata.get('consolidation_score', 0.5)
        consolidation_multiplier = 0.7 + (consolidation_score * 0.3)  # 0.7 to 1.0
        
        # Calculate final position size
        position_value = (account_balance * base_position_pct * confidence_multiplier * 
                         breakout_multiplier * consolidation_multiplier)
        position_size = position_value / signal.entry_price
        
        self.logger.info(
            f"Breakout position size: {position_size:.6f} | "
            f"Confidence: {confidence_multiplier:.2f} | "
            f"Breakout: {breakout_pct:.3f} | "
            f"Consolidation: {consolidation_score:.2f}"
        )
        
        return position_size