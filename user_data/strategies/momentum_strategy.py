"""
Simple Momentum Strategy for testing signal generation.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.bot.strategy_base import TechnicalStrategy, StrategySignal, StrategyConfig

class MomentumStrategy(TechnicalStrategy):
    """
    Simple momentum strategy that generates signals based on price movement
    and RSI conditions. Designed to complement engulfing patterns and ensure
    signal generation for testing purposes.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Strategy parameters
        params = config.parameters
        self.price_change_threshold = params.get('price_change_threshold', 0.002)  # 0.2% price change
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.volume_threshold = params.get('volume_threshold', 1.2)  # 1.2x average volume
        
        # Required indicators
        self.required_indicators = ['rsi', 'volume_ratio', 'ema']
        
        self.logger.info(f"Momentum Strategy initialized with parameters: {params}")
    
    def analyze_market(self, data: pd.DataFrame, current_price: float) -> List[StrategySignal]:
        """Analyze market data for momentum signals."""
        signals = []
        
        if not self.is_enabled or not self.check_data_requirements(data):
            return signals
        
        # Need at least 3 candles for momentum analysis
        if len(data) < 3:
            return signals
        
        current_candle = data.iloc[-1]
        previous_candle = data.iloc[-2]
        
        self.logger.info(f"Momentum analysis - current RSI: {current_candle.get('rsi', 'N/A'):.1f}, price change: {((current_candle['close'] - previous_candle['close']) / previous_candle['close'] * 100):.2f}%")
        
        # Check for bullish momentum
        bullish_signal = self._detect_bullish_momentum(data, current_candle, previous_candle)
        if bullish_signal:
            signals.append(bullish_signal)
        
        # Check for bearish momentum
        bearish_signal = self._detect_bearish_momentum(data, current_candle, previous_candle)
        if bearish_signal:
            signals.append(bearish_signal)
        
        return signals
    
    def _detect_bullish_momentum(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series) -> Optional[StrategySignal]:
        """Detect bullish momentum signals."""
        
        # Calculate price change
        price_change = (current['close'] - previous['close']) / previous['close']
        
        self.logger.info(f"Checking bullish momentum: price_change={price_change:.4f}, threshold={self.price_change_threshold}")
        
        # Bullish conditions:
        # 1. Strong positive price movement
        if price_change < self.price_change_threshold:
            self.logger.info(f"Price change too small: {price_change:.4f} < {self.price_change_threshold}")
            return None
        
        # 2. RSI in oversold/neutral range (room to move up)
        rsi = current.get('rsi', 50)
        if rsi > self.rsi_overbought:
            self.logger.info(f"RSI too high (overbought): {rsi:.1f} > {self.rsi_overbought}")
            return None
        
        # 3. Above average volume
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.volume_threshold:
            self.logger.info(f"Volume too low: {volume_ratio:.2f} < {self.volume_threshold}")
            return None
        
        # Calculate confidence based on signal strength
        confidence = self._calculate_momentum_confidence(price_change, rsi, volume_ratio, 'LONG')
        
        if confidence < self.config.min_confidence:
            self.logger.info(f"Confidence too low: {confidence:.2f} < {self.config.min_confidence}")
            return None
        
        # Create signal
        entry_price = current['close']
        atr = data['atr'].iloc[-1] if 'atr' in data.columns else abs(current['high'] - current['low'])
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=getattr(current, 'name', 'UNKNOWN'),
            signal_type='LONG',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=entry_price - (2 * atr),
            take_profit=entry_price + (3 * atr),
            metadata={
                'strategy_name': self.name,
                'pattern': 'bullish_momentum',
                'price_change': price_change,
                'rsi': rsi,
                'volume_ratio': volume_ratio,
                'atr': atr
            }
        )
        
        self.logger.info(f"Bullish momentum signal generated: price={entry_price:.2f}, confidence={confidence:.2f}, price_change={price_change:.3f}")
        return signal
    
    def _detect_bearish_momentum(self, data: pd.DataFrame, current: pd.Series, previous: pd.Series) -> Optional[StrategySignal]:
        """Detect bearish momentum signals."""
        
        # Calculate price change
        price_change = (current['close'] - previous['close']) / previous['close']
        
        self.logger.info(f"Checking bearish momentum: price_change={price_change:.4f}, threshold={-self.price_change_threshold}")
        
        # Bearish conditions:
        # 1. Strong negative price movement
        if price_change > -self.price_change_threshold:
            self.logger.info(f"Price change not negative enough: {price_change:.4f} > {-self.price_change_threshold}")
            return None
        
        # 2. RSI in overbought/neutral range (room to move down)
        rsi = current.get('rsi', 50)
        if rsi < self.rsi_oversold:
            self.logger.info(f"RSI too low (oversold): {rsi:.1f} < {self.rsi_oversold}")
            return None
        
        # 3. Above average volume
        volume_ratio = current.get('volume_ratio', 1.0)
        if volume_ratio < self.volume_threshold:
            self.logger.info(f"Volume too low: {volume_ratio:.2f} < {self.volume_threshold}")
            return None
        
        # Calculate confidence based on signal strength
        confidence = self._calculate_momentum_confidence(abs(price_change), rsi, volume_ratio, 'SHORT')
        
        if confidence < self.config.min_confidence:
            self.logger.info(f"Confidence too low: {confidence:.2f} < {self.config.min_confidence}")
            return None
        
        # Create signal
        entry_price = current['close']
        atr = data['atr'].iloc[-1] if 'atr' in data.columns else abs(current['high'] - current['low'])
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=getattr(current, 'name', 'UNKNOWN'),
            signal_type='SHORT',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=entry_price + (2 * atr),
            take_profit=entry_price - (3 * atr),
            metadata={
                'strategy_name': self.name,
                'pattern': 'bearish_momentum',
                'price_change': price_change,
                'rsi': rsi,
                'volume_ratio': volume_ratio,
                'atr': atr
            }
        )
        
        self.logger.info(f"Bearish momentum signal generated: price={entry_price:.2f}, confidence={confidence:.2f}, price_change={price_change:.3f}")
        return signal
    
    def _calculate_momentum_confidence(self, price_change: float, rsi: float, volume_ratio: float, direction: str) -> float:
        """Calculate confidence for momentum signal."""
        confidence = 0.0
        
        # Price movement strength (0.3 weight)
        movement_strength = min(abs(price_change) / self.price_change_threshold, 3.0) / 3.0
        confidence += movement_strength * 0.3
        
        # Volume confirmation (0.3 weight)
        volume_strength = min(volume_ratio / self.volume_threshold, 2.0) / 2.0
        confidence += volume_strength * 0.3
        
        # RSI positioning (0.4 weight)
        if direction == 'LONG':
            # For long signals, prefer lower RSI (more room to go up)
            rsi_score = max(0, (self.rsi_overbought - rsi) / (self.rsi_overbought - self.rsi_oversold))
        else:  # SHORT
            # For short signals, prefer higher RSI (more room to go down)
            rsi_score = max(0, (rsi - self.rsi_oversold) / (self.rsi_overbought - self.rsi_oversold))
        
        confidence += rsi_score * 0.4
        
        return min(confidence, 1.0)
    
    def validate_signal(self, signal: StrategySignal, market_context: Dict) -> bool:
        """Validate signal against market context."""
        
        # Check if market conditions are suitable
        volatility = market_context.get('volatility_regime', 'NORMAL')
        if volatility == 'EXTREME':
            self.logger.warning(f"Momentum signal rejected due to extreme volatility")
            return False
        
        return True
    
    def calculate_position_size(self, signal: StrategySignal, account_balance: float) -> float:
        """Calculate position size based on signal strength and risk."""
        
        # Base position size (2% of account by default)
        base_position_pct = 0.02
        
        # Adjust based on signal confidence
        confidence_multiplier = signal.confidence
        
        # Adjust based on volatility (if available in metadata)
        volatility_adjustment = 1.0
        if 'atr' in signal.metadata:
            atr = signal.metadata['atr']
            atr_pct = atr / signal.entry_price
            if atr_pct > 0.02:  # If ATR > 2% of price, reduce size
                volatility_adjustment = max(0.5, 1 - (atr_pct - 0.02) * 10)
        
        # Calculate final position size
        position_value = account_balance * base_position_pct * confidence_multiplier * volatility_adjustment
        position_size = position_value / signal.entry_price
        
        self.logger.info(
            f"Momentum position size calculation: {position_size:.6f} | "
            f"Confidence: {confidence_multiplier:.2f} | "
            f"Volatility adj: {volatility_adjustment:.2f}"
        )
        
        return position_size