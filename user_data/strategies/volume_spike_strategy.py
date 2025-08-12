"""
Volume Spike Strategy - Generate signals on unusual volume activity.
Detects volume spikes combined with price movement for signal generation.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.bot.strategy_base import TechnicalStrategy, StrategySignal, StrategyConfig

class VolumeSpikeStrategy(TechnicalStrategy):
    """
    Volume Spike Strategy generates signals when volume significantly exceeds average.
    Uses relaxed parameters and multiple confirmation methods for high signal generation.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Relaxed parameters for maximum signal generation
        params = config.parameters
        self.volume_spike_threshold = params.get('volume_spike_threshold', 1.5)  # 1.5x average volume
        self.min_price_movement = params.get('min_price_movement', 0.002)       # 0.2% price movement
        self.rsi_filter_enabled = params.get('rsi_filter_enabled', False)       # Disable RSI filter for more signals
        self.rsi_neutral_min = params.get('rsi_neutral_min', 25)                # Wide neutral range
        self.rsi_neutral_max = params.get('rsi_neutral_max', 75)                # Wide neutral range
        self.lookback_period = params.get('volume_lookback', 10)                # Volume average lookback
        self.stop_loss_atr_multiplier = params.get('stop_loss_atr_multiplier', 1.5)
        self.take_profit_atr_multiplier = params.get('take_profit_atr_multiplier', 2.5)
        
        # Required indicators
        self.required_indicators = ['volume_ratio']
        
        self.logger.info(f"Volume Spike Strategy initialized with spike threshold: {self.volume_spike_threshold}x")
    
    def analyze_market(self, data: pd.DataFrame, current_price: float) -> List[StrategySignal]:
        """Analyze market data for volume spike signals."""
        signals = []
        
        if not self.is_enabled or not self.check_data_requirements(data):
            return signals
        
        # Need enough data for volume analysis
        if len(data) < self.lookback_period + 2:
            return signals
        
        current_candle = data.iloc[-1]
        previous_candle = data.iloc[-2]
        
        # Calculate volume metrics with NaN protection
        volume_ratio = current_candle.get('volume_ratio', 1.0)
        current_volume = current_candle.get('volume', 0)
        
        # Fix NaN values
        import numpy as np
        if np.isnan(volume_ratio) or np.isinf(volume_ratio):
            volume_ratio = 1.0
        if np.isnan(current_volume) or np.isinf(current_volume):
            current_volume = 0
        
        self.logger.info(f"Volume Spike analysis - Current volume ratio: {volume_ratio:.2f}, threshold: {self.volume_spike_threshold}")
        
        # Check for volume spike
        if volume_ratio < self.volume_spike_threshold:
            self.logger.info(f"No volume spike detected: {volume_ratio:.2f} < {self.volume_spike_threshold}")
            return signals
        
        # Check for bullish volume spike
        bullish_signal = self._detect_bullish_volume_spike(data, current_candle, previous_candle, volume_ratio)
        if bullish_signal:
            signals.append(bullish_signal)
        
        # Check for bearish volume spike
        bearish_signal = self._detect_bearish_volume_spike(data, current_candle, previous_candle, volume_ratio)
        if bearish_signal:
            signals.append(bearish_signal)
        
        return signals
    
    def _detect_bullish_volume_spike(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series, 
                                    volume_ratio: float) -> Optional[StrategySignal]:
        """Detect bullish signal with volume spike."""
        
        # Price movement analysis
        price_change = (current['close'] - previous['close']) / previous['close']
        
        self.logger.info(f"Checking bullish volume spike: price_change={price_change:.4f}, volume_ratio={volume_ratio:.2f}")
        
        # Conditions for bullish signal:
        # 1. Positive price movement (or small negative acceptable)
        if price_change < -self.min_price_movement:
            self.logger.info(f"Price movement too negative: {price_change:.4f} < {-self.min_price_movement:.4f}")
            return None
        
        # 2. Optional RSI filter (disabled by default for more signals)
        if self.rsi_filter_enabled:
            rsi = current.get('rsi', 50)
            if rsi > self.rsi_neutral_max:
                self.logger.info(f"RSI too high: {rsi:.1f} > {self.rsi_neutral_max}")
                return None
        
        # 3. Check for accumulation pattern (multiple criteria)
        accumulation_score = self._calculate_accumulation_score(data, current, 'LONG')
        
        # Calculate confidence
        confidence = self._calculate_volume_confidence(volume_ratio, price_change, accumulation_score, 'LONG')
        
        if confidence < self.config.min_confidence:
            self.logger.info(f"Confidence too low: {confidence:.2f} < {self.config.min_confidence}")
            return None
        
        # Create signal
        entry_price = current['close']
        atr = self._estimate_atr(data)
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=getattr(current, 'name', 'UNKNOWN'),
            signal_type='LONG',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=entry_price - (self.stop_loss_atr_multiplier * atr),
            take_profit=entry_price + (self.take_profit_atr_multiplier * atr),
            metadata={
                'strategy_name': self.name, 'pattern': 'bullish_volume_spike',
                'volume_ratio': volume_ratio,
                'price_change': price_change,
                'accumulation_score': accumulation_score,
                'volume_threshold': self.volume_spike_threshold
            }
        )
        
        self.logger.info(f"Bullish volume spike signal: price={entry_price:.2f}, confidence={confidence:.2f}, volume={volume_ratio:.2f}x")
        return signal
    
    def _detect_bearish_volume_spike(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series,
                                    volume_ratio: float) -> Optional[StrategySignal]:
        """Detect bearish signal with volume spike."""
        
        # Price movement analysis
        price_change = (current['close'] - previous['close']) / previous['close']
        
        self.logger.info(f"Checking bearish volume spike: price_change={price_change:.4f}, volume_ratio={volume_ratio:.2f}")
        
        # Conditions for bearish signal:
        # 1. Negative price movement (or small positive acceptable)
        if price_change > self.min_price_movement:
            self.logger.info(f"Price movement too positive: {price_change:.4f} > {self.min_price_movement:.4f}")
            return None
        
        # 2. Optional RSI filter (disabled by default for more signals)
        if self.rsi_filter_enabled:
            rsi = current.get('rsi', 50)
            if rsi < self.rsi_neutral_min:
                self.logger.info(f"RSI too low: {rsi:.1f} < {self.rsi_neutral_min}")
                return None
        
        # 3. Check for distribution pattern
        distribution_score = self._calculate_accumulation_score(data, current, 'SHORT')
        
        # Calculate confidence
        confidence = self._calculate_volume_confidence(volume_ratio, abs(price_change), distribution_score, 'SHORT')
        
        if confidence < self.config.min_confidence:
            self.logger.info(f"Confidence too low: {confidence:.2f} < {self.config.min_confidence}")
            return None
        
        # Create signal
        entry_price = current['close']
        atr = self._estimate_atr(data)
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=getattr(current, 'name', 'UNKNOWN'),
            signal_type='SHORT',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=entry_price + (self.stop_loss_atr_multiplier * atr),
            take_profit=entry_price - (self.take_profit_atr_multiplier * atr),
            metadata={
                'strategy_name': self.name, 'pattern': 'bearish_volume_spike',
                'volume_ratio': volume_ratio,
                'price_change': price_change,
                'distribution_score': distribution_score,
                'volume_threshold': self.volume_spike_threshold
            }
        )
        
        self.logger.info(f"Bearish volume spike signal: price={entry_price:.2f}, confidence={confidence:.2f}, volume={volume_ratio:.2f}x")
        return signal
    
    def _calculate_accumulation_score(self, data: pd.DataFrame, current: pd.Series, direction: str) -> float:
        """Calculate accumulation/distribution score based on price-volume relationship."""
        score = 0.0
        
        # Check recent candles for volume-price relationship
        recent_data = data.tail(3)
        
        for _, candle in recent_data.iterrows():
            candle_volume_ratio = candle.get('volume_ratio', 1.0)
            candle_close = candle['close']
            candle_open = candle['open']
            candle_change = (candle_close - candle_open) / candle_open
            
            if direction == 'LONG':
                # For bullish signal, look for volume on up candles
                if candle_change > 0 and candle_volume_ratio > 1.0:
                    score += 0.3
                elif candle_change < 0 and candle_volume_ratio < 1.0:
                    score += 0.1  # Low volume on down moves is good
            else:  # SHORT
                # For bearish signal, look for volume on down candles
                if candle_change < 0 and candle_volume_ratio > 1.0:
                    score += 0.3
                elif candle_change > 0 and candle_volume_ratio < 1.0:
                    score += 0.1  # Low volume on up moves is good
        
        # Price position in candle (for current candle)
        candle_range = current['high'] - current['low']
        if candle_range > 0:
            if direction == 'LONG':
                # Close near high is bullish
                close_position = (current['close'] - current['low']) / candle_range
                score += close_position * 0.2
            else:  # SHORT
                # Close near low is bearish
                close_position = (current['high'] - current['close']) / candle_range
                score += close_position * 0.2
        
        return min(score, 1.0)
    
    def _calculate_volume_confidence(self, volume_ratio: float, price_movement: float, 
                                   pattern_score: float, direction: str) -> float:
        """Calculate confidence for volume spike signal."""
        import numpy as np
        
        # Validate inputs and fix NaN/inf values
        volume_ratio = volume_ratio if not (np.isnan(volume_ratio) or np.isinf(volume_ratio)) else 1.0
        price_movement = price_movement if not (np.isnan(price_movement) or np.isinf(price_movement)) else 0.0
        pattern_score = pattern_score if not (np.isnan(pattern_score) or np.isinf(pattern_score)) else 0.0
        
        confidence = 0.0
        
        # Volume spike strength (0.4 weight)
        volume_score = min(volume_ratio / self.volume_spike_threshold, 3.0) / 3.0
        if not (np.isnan(volume_score) or np.isinf(volume_score)):
            confidence += volume_score * 0.4
        
        # Price movement confirmation (0.3 weight)
        movement_score = min(abs(price_movement) / self.min_price_movement, 2.0) / 2.0
        if not (np.isnan(movement_score) or np.isinf(movement_score)):
            confidence += movement_score * 0.3
        
        # Accumulation/Distribution pattern (0.3 weight)
        if not (np.isnan(pattern_score) or np.isinf(pattern_score)):
            confidence += pattern_score * 0.3
        
        # Final validation
        confidence = confidence if not (np.isnan(confidence) or np.isinf(confidence)) else 0.0
        return min(max(confidence, 0.0), 1.0)
    
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
        """Validate volume spike signal - very permissive."""
        
        # Only check for basic volume validity
        volume_ratio = signal.metadata.get('volume_ratio', 0)
        if volume_ratio < 1.0:
            self.logger.warning(f"Volume spike signal rejected - invalid volume ratio: {volume_ratio}")
            return False
        
        return True
    
    def calculate_position_size(self, signal: StrategySignal, account_balance: float) -> float:
        """Calculate position size for volume spike signal."""
        
        # Slightly larger position size for volume-confirmed signals
        base_position_pct = 0.025  # 2.5% of account
        
        # Adjust based on signal confidence and volume strength
        confidence_multiplier = signal.confidence
        volume_ratio = signal.metadata.get('volume_ratio', 1.0)
        volume_multiplier = min(volume_ratio / self.volume_spike_threshold, 2.0) / 2.0 + 0.5  # 0.5 to 1.0
        
        # Calculate final position size
        position_value = account_balance * base_position_pct * confidence_multiplier * volume_multiplier
        position_size = position_value / signal.entry_price
        
        self.logger.info(
            f"Volume spike position size: {position_size:.6f} | "
            f"Confidence: {confidence_multiplier:.2f} | Volume: {volume_ratio:.2f}x"
        )
        
        return position_size