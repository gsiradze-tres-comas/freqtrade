"""
RSI Bounce Strategy - Generate signals when RSI bounces from extreme levels.
Designed for high signal generation in various market conditions.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.bot.strategy_base import TechnicalStrategy, StrategySignal, StrategyConfig

class RSIBounceStrategy(TechnicalStrategy):
    """
    RSI Bounce Strategy generates signals when RSI bounces from oversold/overbought levels.
    Uses relaxed parameters to ensure signal generation for testing and trading.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Very relaxed parameters for maximum signal generation
        params = config.parameters
        self.rsi_oversold = params.get('rsi_oversold', 35)      # Higher than typical 30
        self.rsi_overbought = params.get('rsi_overbought', 65)  # Lower than typical 70
        self.rsi_bounce_threshold = params.get('rsi_bounce_threshold', 3)  # Minimum RSI move for bounce
        self.min_volume_ratio = params.get('min_volume_ratio', 0.8)  # Very low volume requirement
        self.price_confirmation = params.get('price_confirmation', 0.001)  # 0.1% price move
        self.stop_loss_atr_multiplier = params.get('stop_loss_atr_multiplier', 1.5)
        self.take_profit_atr_multiplier = params.get('take_profit_atr_multiplier', 2.5)
        
        # Required indicators
        self.required_indicators = ['rsi', 'volume_ratio']
        
        self.logger.info(f"RSI Bounce Strategy initialized with relaxed parameters: {params}")
    
    def analyze_market(self, data: pd.DataFrame, current_price: float) -> List[StrategySignal]:
        """Analyze market data for RSI bounce signals."""
        signals = []
        
        if not self.is_enabled or not self.check_data_requirements(data):
            return signals
        
        # Need at least 3 candles for bounce analysis
        if len(data) < 3:
            return signals
        
        current_candle = data.iloc[-1]
        previous_candle = data.iloc[-2]
        
        current_rsi = current_candle.get('rsi', 50)
        previous_rsi = previous_candle.get('rsi', 50)
        
        self.logger.info(f"RSI Bounce analysis - Current RSI: {current_rsi:.1f}, Previous RSI: {previous_rsi:.1f}")
        
        # Check for bullish RSI bounce (from oversold)
        bullish_signal = self._detect_bullish_rsi_bounce(data, current_candle, previous_candle, current_rsi, previous_rsi)
        if bullish_signal:
            signals.append(bullish_signal)
        
        # Check for bearish RSI bounce (from overbought)
        bearish_signal = self._detect_bearish_rsi_bounce(data, current_candle, previous_candle, current_rsi, previous_rsi)
        if bearish_signal:
            signals.append(bearish_signal)
        
        return signals
    
    def _detect_bullish_rsi_bounce(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series, 
                                  current_rsi: float, previous_rsi: float) -> Optional[StrategySignal]:
        """Detect bullish RSI bounce from oversold levels."""
        
        # Look for RSI bouncing up from oversold area
        rsi_bounce = current_rsi - previous_rsi
        
        self.logger.info(f"Checking bullish RSI bounce: prev_rsi={previous_rsi:.1f}, curr_rsi={current_rsi:.1f}, bounce={rsi_bounce:.1f}")
        
        # Conditions for bullish signal:
        # 1. Previous RSI was oversold or close to it
        if previous_rsi > self.rsi_oversold + 5:  # Allow some buffer above oversold
            self.logger.info(f"Previous RSI not oversold enough: {previous_rsi:.1f} > {self.rsi_oversold + 5}")
            return None
        
        # 2. RSI is bouncing up
        if rsi_bounce < self.rsi_bounce_threshold:
            self.logger.info(f"RSI bounce too small: {rsi_bounce:.1f} < {self.rsi_bounce_threshold}")
            return None
        
        # 3. Price confirmation (minimal requirement)
        price_change = (current['close'] - previous['close']) / previous['close']
        if price_change < -self.price_confirmation:  # Allow small negative moves
            self.logger.info(f"Price moving against signal: {price_change:.4f} < {-self.price_confirmation:.4f}")
            return None
        
        # 4. Minimal volume check (very relaxed)
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.min_volume_ratio:
            self.logger.info(f"Volume too low: {volume_ratio:.2f} < {self.min_volume_ratio}")
            return None
        
        # Calculate confidence
        confidence = self._calculate_rsi_confidence(previous_rsi, rsi_bounce, volume_ratio, price_change, 'LONG')
        
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
                'strategy_name': self.name, 'pattern': 'rsi_bullish_bounce',
                'previous_rsi': previous_rsi,
                'current_rsi': current_rsi,
                'rsi_bounce': rsi_bounce,
                'price_change': price_change,
                'volume_ratio': volume_ratio
            }
        )
        
        self.logger.info(f"Bullish RSI bounce signal: price={entry_price:.2f}, confidence={confidence:.2f}, rsi_bounce={rsi_bounce:.1f}")
        return signal
    
    def _detect_bearish_rsi_bounce(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series,
                                  current_rsi: float, previous_rsi: float) -> Optional[StrategySignal]:
        """Detect bearish RSI bounce from overbought levels."""
        
        # Look for RSI bouncing down from overbought area
        rsi_bounce = previous_rsi - current_rsi  # Positive when RSI falls
        
        self.logger.info(f"Checking bearish RSI bounce: prev_rsi={previous_rsi:.1f}, curr_rsi={current_rsi:.1f}, bounce={rsi_bounce:.1f}")
        
        # Conditions for bearish signal:
        # 1. Previous RSI was overbought or close to it
        if previous_rsi < self.rsi_overbought - 5:  # Allow some buffer below overbought
            self.logger.info(f"Previous RSI not overbought enough: {previous_rsi:.1f} < {self.rsi_overbought - 5}")
            return None
        
        # 2. RSI is bouncing down
        if rsi_bounce < self.rsi_bounce_threshold:
            self.logger.info(f"RSI bounce too small: {rsi_bounce:.1f} < {self.rsi_bounce_threshold}")
            return None
        
        # 3. Price confirmation (minimal requirement)
        price_change = (current['close'] - previous['close']) / previous['close']
        if price_change > self.price_confirmation:  # Allow small positive moves
            self.logger.info(f"Price moving against signal: {price_change:.4f} > {self.price_confirmation:.4f}")
            return None
        
        # 4. Minimal volume check (very relaxed)
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.min_volume_ratio:
            self.logger.info(f"Volume too low: {volume_ratio:.2f} < {self.min_volume_ratio}")
            return None
        
        # Calculate confidence
        confidence = self._calculate_rsi_confidence(100 - previous_rsi, rsi_bounce, volume_ratio, abs(price_change), 'SHORT')
        
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
                'strategy_name': self.name, 'pattern': 'rsi_bearish_bounce',
                'previous_rsi': previous_rsi,
                'current_rsi': current_rsi,
                'rsi_bounce': rsi_bounce,
                'price_change': price_change,
                'volume_ratio': volume_ratio
            }
        )
        
        self.logger.info(f"Bearish RSI bounce signal: price={entry_price:.2f}, confidence={confidence:.2f}, rsi_bounce={rsi_bounce:.1f}")
        return signal
    
    def _calculate_rsi_confidence(self, extreme_level: float, bounce_strength: float, 
                                 volume_ratio: float, price_conf: float, direction: str) -> float:
        """Calculate confidence for RSI bounce signal."""
        confidence = 0.0
        
        # RSI extreme level strength (0.4 weight)
        if direction == 'LONG':
            # Lower RSI = stronger oversold = higher confidence
            extreme_score = max(0, (self.rsi_oversold + 10 - extreme_level) / 20)
        else:
            # Higher RSI = stronger overbought = higher confidence  
            extreme_score = max(0, (extreme_level - (self.rsi_overbought - 10)) / 20)
        
        confidence += min(extreme_score, 1.0) * 0.4
        
        # Bounce strength (0.3 weight)
        bounce_score = min(bounce_strength / (self.rsi_bounce_threshold * 3), 1.0)
        confidence += bounce_score * 0.3
        
        # Volume confirmation (0.2 weight)
        volume_score = min(volume_ratio / self.min_volume_ratio, 2.0) / 2.0
        confidence += volume_score * 0.2
        
        # Price confirmation (0.1 weight) 
        price_score = min(abs(price_conf) / self.price_confirmation, 2.0) / 2.0
        confidence += price_score * 0.1
        
        return min(confidence, 1.0)
    
    def _estimate_atr(self, data: pd.DataFrame) -> float:
        """Estimate ATR from available data."""
        if 'atr' in data.columns:
            return data['atr'].iloc[-1]
        
        # Calculate simple ATR approximation from last 5 candles
        recent_data = data.tail(5)
        highs = recent_data['high']
        lows = recent_data['low']
        ranges = highs - lows
        return ranges.mean()
    
    def validate_signal(self, signal: StrategySignal, market_context: Dict) -> bool:
        """Validate RSI bounce signal - very permissive for signal generation."""
        
        # Only reject in extreme market conditions
        volatility = market_context.get('volatility_regime', 'NORMAL')
        if volatility == 'EXTREME':
            self.logger.warning(f"RSI bounce signal rejected due to extreme volatility")
            return False
        
        return True
    
    def calculate_position_size(self, signal: StrategySignal, account_balance: float) -> float:
        """Calculate position size for RSI bounce signal."""
        
        # Conservative base position size for bounce strategy
        base_position_pct = 0.015  # 1.5% of account
        
        # Adjust based on signal confidence
        confidence_multiplier = signal.confidence
        
        # Calculate final position size
        position_value = account_balance * base_position_pct * confidence_multiplier
        position_size = position_value / signal.entry_price
        
        self.logger.info(f"RSI bounce position size: {position_size:.6f} | Confidence: {confidence_multiplier:.2f}")
        
        return position_size