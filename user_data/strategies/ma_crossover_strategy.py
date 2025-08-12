"""
Moving Average Crossover Strategy - Generate signals on EMA crossovers.
Uses fast and slow EMAs with relaxed parameters for high signal generation.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.bot.strategy_base import TechnicalStrategy, StrategySignal, StrategyConfig

class MACrossoverStrategy(TechnicalStrategy):
    """
    Moving Average Crossover Strategy generates signals when fast EMA crosses slow EMA.
    Uses very relaxed parameters and multiple timeframes for maximum signal generation.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Relaxed parameters for maximum signal generation
        params = config.parameters
        self.fast_ema_period = params.get('fast_ema_period', 5)    # Very fast EMA
        self.slow_ema_period = params.get('slow_ema_period', 10)   # Moderate slow EMA  
        self.min_separation = params.get('min_separation', 0.0005) # 0.05% minimum separation
        self.volume_threshold = params.get('volume_threshold', 0.7) # Very low volume requirement
        self.trend_confirmation = params.get('trend_confirmation', True) # Optional trend filter
        
        # Required indicators
        self.required_indicators = ['ema', 'volume_ratio']
        
        self.logger.info(f"MA Crossover Strategy initialized with periods: fast={self.fast_ema_period}, slow={self.slow_ema_period}")
    
    def analyze_market(self, data: pd.DataFrame, current_price: float) -> List[StrategySignal]:
        """Analyze market data for MA crossover signals."""
        signals = []
        
        if not self.is_enabled or not self.check_data_requirements(data):
            return signals
        
        # Need enough data for both EMAs
        required_length = max(self.fast_ema_period, self.slow_ema_period) + 2
        if len(data) < required_length:
            return signals
        
        # Calculate EMAs if not present
        data_with_emas = self._ensure_emas(data)
        
        current_candle = data_with_emas.iloc[-1]
        previous_candle = data_with_emas.iloc[-2]
        
        fast_ema_current = current_candle[f'ema_{self.fast_ema_period}']
        slow_ema_current = current_candle[f'ema_{self.slow_ema_period}']
        fast_ema_previous = previous_candle[f'ema_{self.fast_ema_period}']
        slow_ema_previous = previous_candle[f'ema_{self.slow_ema_period}']
        
        self.logger.info(f"MA Crossover analysis - Fast EMA: {fast_ema_current:.2f}, Slow EMA: {slow_ema_current:.2f}")
        
        # Check for bullish crossover (fast crosses above slow)
        bullish_signal = self._detect_bullish_crossover(
            data_with_emas, current_candle, previous_candle,
            fast_ema_current, slow_ema_current, fast_ema_previous, slow_ema_previous
        )
        if bullish_signal:
            signals.append(bullish_signal)
        
        # Check for bearish crossover (fast crosses below slow)
        bearish_signal = self._detect_bearish_crossover(
            data_with_emas, current_candle, previous_candle,
            fast_ema_current, slow_ema_current, fast_ema_previous, slow_ema_previous
        )
        if bearish_signal:
            signals.append(bearish_signal)
        
        return signals
    
    def _ensure_emas(self, data: pd.DataFrame) -> pd.DataFrame:
        """Ensure fast and slow EMAs are calculated."""
        data_copy = data.copy()
        
        # Calculate fast EMA if not present
        fast_col = f'ema_{self.fast_ema_period}'
        if fast_col not in data_copy.columns:
            data_copy[fast_col] = data_copy['close'].ewm(span=self.fast_ema_period).mean()
        
        # Calculate slow EMA if not present  
        slow_col = f'ema_{self.slow_ema_period}'
        if slow_col not in data_copy.columns:
            data_copy[slow_col] = data_copy['close'].ewm(span=self.slow_ema_period).mean()
        
        return data_copy
    
    def _detect_bullish_crossover(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series,
                                 fast_current: float, slow_current: float, 
                                 fast_previous: float, slow_previous: float) -> Optional[StrategySignal]:
        """Detect bullish crossover signal (fast EMA crosses above slow EMA)."""
        
        self.logger.info(f"Checking bullish crossover: fast_prev={fast_previous:.2f}, fast_curr={fast_current:.2f}, slow_prev={slow_previous:.2f}, slow_curr={slow_current:.2f}")
        
        # Check for crossover
        was_below = fast_previous <= slow_previous
        is_above = fast_current > slow_current
        
        if not (was_below and is_above):
            self.logger.info(f"No bullish crossover detected")
            return None
        
        # Check minimum separation to avoid false signals
        separation = (fast_current - slow_current) / slow_current
        if separation < self.min_separation:
            self.logger.info(f"Crossover separation too small: {separation:.6f} < {self.min_separation:.6f}")
            return None
        
        # Volume check (very relaxed)
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.volume_threshold:
            self.logger.info(f"Volume too low: {volume_ratio:.2f} < {self.volume_threshold}")
            return None
        
        # Optional trend confirmation
        if self.trend_confirmation:
            # Both EMAs should be trending up for stronger signal
            fast_trend = (fast_current - data[f'ema_{self.fast_ema_period}'].iloc[-3]) / data[f'ema_{self.fast_ema_period}'].iloc[-3]
            slow_trend = (slow_current - data[f'ema_{self.slow_ema_period}'].iloc[-3]) / data[f'ema_{self.slow_ema_period}'].iloc[-3]
            
            if fast_trend < -0.001 or slow_trend < -0.001:  # Very relaxed trend requirement
                self.logger.info(f"Trend confirmation failed: fast_trend={fast_trend:.4f}, slow_trend={slow_trend:.4f}")
                # Don't return None - just lower confidence instead
        
        # Calculate confidence
        confidence = self._calculate_crossover_confidence(separation, volume_ratio, fast_current, slow_current, data, 'LONG')
        
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
            stop_loss=entry_price - (2 * atr),
            take_profit=entry_price + (3 * atr),
            metadata={
                'strategy_name': self.name, 'pattern': 'bullish_ma_crossover',
                'fast_ema': fast_current,
                'slow_ema': slow_current,
                'separation': separation,
                'volume_ratio': volume_ratio,
                'fast_period': self.fast_ema_period,
                'slow_period': self.slow_ema_period
            }
        )
        
        self.logger.info(f"Bullish MA crossover signal: price={entry_price:.2f}, confidence={confidence:.2f}, separation={separation:.4f}")
        return signal
    
    def _detect_bearish_crossover(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series,
                                 fast_current: float, slow_current: float,
                                 fast_previous: float, slow_previous: float) -> Optional[StrategySignal]:
        """Detect bearish crossover signal (fast EMA crosses below slow EMA)."""
        
        self.logger.info(f"Checking bearish crossover: fast_prev={fast_previous:.2f}, fast_curr={fast_current:.2f}, slow_prev={slow_previous:.2f}, slow_curr={slow_current:.2f}")
        
        # Check for crossover
        was_above = fast_previous >= slow_previous
        is_below = fast_current < slow_current
        
        if not (was_above and is_below):
            self.logger.info(f"No bearish crossover detected")
            return None
        
        # Check minimum separation to avoid false signals
        separation = (slow_current - fast_current) / slow_current
        if separation < self.min_separation:
            self.logger.info(f"Crossover separation too small: {separation:.6f} < {self.min_separation:.6f}")
            return None
        
        # Volume check (very relaxed)
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.volume_threshold:
            self.logger.info(f"Volume too low: {volume_ratio:.2f} < {self.volume_threshold}")
            return None
        
        # Optional trend confirmation
        if self.trend_confirmation:
            # Both EMAs should be trending down for stronger signal
            fast_trend = (fast_current - data[f'ema_{self.fast_ema_period}'].iloc[-3]) / data[f'ema_{self.fast_ema_period}'].iloc[-3]
            slow_trend = (slow_current - data[f'ema_{self.slow_ema_period}'].iloc[-3]) / data[f'ema_{self.slow_ema_period}'].iloc[-3]
            
            if fast_trend > 0.001 or slow_trend > 0.001:  # Very relaxed trend requirement
                self.logger.info(f"Trend confirmation failed: fast_trend={fast_trend:.4f}, slow_trend={slow_trend:.4f}")
                # Don't return None - just lower confidence instead
        
        # Calculate confidence
        confidence = self._calculate_crossover_confidence(separation, volume_ratio, fast_current, slow_current, data, 'SHORT')
        
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
            stop_loss=entry_price + (2 * atr),
            take_profit=entry_price - (3 * atr),
            metadata={
                'strategy_name': self.name, 'pattern': 'bearish_ma_crossover',
                'fast_ema': fast_current,
                'slow_ema': slow_current,
                'separation': separation,
                'volume_ratio': volume_ratio,
                'fast_period': self.fast_ema_period,
                'slow_period': self.slow_ema_period
            }
        )
        
        self.logger.info(f"Bearish MA crossover signal: price={entry_price:.2f}, confidence={confidence:.2f}, separation={separation:.4f}")
        return signal
    
    def _calculate_crossover_confidence(self, separation: float, volume_ratio: float,
                                      fast_ema: float, slow_ema: float, data: pd.DataFrame, direction: str) -> float:
        """Calculate confidence for crossover signal."""
        confidence = 0.0
        
        # Separation strength (0.3 weight)
        separation_score = min(separation / (self.min_separation * 5), 1.0)
        confidence += separation_score * 0.3
        
        # Volume confirmation (0.2 weight)
        volume_score = min(volume_ratio / self.volume_threshold, 2.0) / 2.0
        confidence += volume_score * 0.2
        
        # EMA trend alignment (0.3 weight)
        if len(data) >= 5:
            if direction == 'LONG':
                # Check if EMAs are generally trending up
                fast_trend = (fast_ema - data[f'ema_{self.fast_ema_period}'].iloc[-5]) / data[f'ema_{self.fast_ema_period}'].iloc[-5]
                slow_trend = (slow_ema - data[f'ema_{self.slow_ema_period}'].iloc[-5]) / data[f'ema_{self.slow_ema_period}'].iloc[-5]
            else:
                # Check if EMAs are generally trending down
                fast_trend = -(fast_ema - data[f'ema_{self.fast_ema_period}'].iloc[-5]) / data[f'ema_{self.fast_ema_period}'].iloc[-5]
                slow_trend = -(slow_ema - data[f'ema_{self.slow_ema_period}'].iloc[-5]) / data[f'ema_{self.slow_ema_period}'].iloc[-5]
            
            trend_score = max(0, min((fast_trend + slow_trend) / 0.01, 1.0))  # Normalize to 1% trend
            confidence += trend_score * 0.3
        
        # Price position relative to EMAs (0.2 weight)
        current_price = data['close'].iloc[-1]
        if direction == 'LONG':
            price_score = 1.0 if current_price >= fast_ema else 0.5
        else:
            price_score = 1.0 if current_price <= fast_ema else 0.5
        confidence += price_score * 0.2
        
        return min(confidence, 1.0)
    
    def _estimate_atr(self, data: pd.DataFrame) -> float:
        """Estimate ATR from available data."""
        if 'atr' in data.columns:
            return data['atr'].iloc[-1]
        
        # Calculate simple ATR approximation from last 10 candles
        recent_data = data.tail(10)
        highs = recent_data['high']
        lows = recent_data['low']
        ranges = highs - lows
        return ranges.mean()
    
    def validate_signal(self, signal: StrategySignal, market_context: Dict) -> bool:
        """Validate MA crossover signal - very permissive."""
        
        # Only reject in extreme conditions
        volatility = market_context.get('volatility_regime', 'NORMAL')
        if volatility == 'EXTREME':
            self.logger.warning(f"MA crossover signal rejected due to extreme volatility")
            return False
        
        return True
    
    def calculate_position_size(self, signal: StrategySignal, account_balance: float) -> float:
        """Calculate position size for MA crossover signal."""
        
        # Standard position size for crossover strategy
        base_position_pct = 0.02  # 2% of account
        
        # Adjust based on signal confidence and separation
        confidence_multiplier = signal.confidence
        separation = signal.metadata.get('separation', 0.001)
        separation_multiplier = min(separation / 0.002, 1.5)  # Bonus for strong separation
        
        # Calculate final position size
        position_value = account_balance * base_position_pct * confidence_multiplier * separation_multiplier
        position_size = position_value / signal.entry_price
        
        self.logger.info(f"MA crossover position size: {position_size:.6f} | Confidence: {confidence_multiplier:.2f} | Separation bonus: {separation_multiplier:.2f}")
        
        return position_size