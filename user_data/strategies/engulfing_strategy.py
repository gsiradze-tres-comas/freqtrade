"""
Enhanced Engulfing Pattern Strategy implementation.
"""

from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from src.bot.strategy_base import TechnicalStrategy, StrategySignal, StrategyConfig
from src.bot.technical_analysis import TechnicalAnalysis

class EnhancedEngulfingStrategy(TechnicalStrategy):
    """
    Enhanced engulfing pattern strategy with volume and RSI confirmation.
    
    This strategy identifies bullish and bearish engulfing patterns
    and confirms them with volume spikes and RSI levels.
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ta = TechnicalAnalysis()
        
        # Strategy parameters
        params = config.parameters
        self.min_body_ratio = params.get('min_body_ratio', 0.6)
        self.volume_multiplier = params.get('volume_multiplier', 1.5)
        self.rsi_min = params.get('rsi_min', 30)
        self.rsi_max = params.get('rsi_max', 70)
        self.ema_period = params.get('ema_period', 20)
        self.volume_period = params.get('volume_period', 10)
        self.rsi_period = params.get('rsi_period', 14)
        
        # Required indicators
        self.required_indicators = [
            'ema', 'rsi', 'volume_sma', 'volume_ratio',
            'body_size', 'body_ratio', 'is_bullish', 'is_bearish'
        ]
        
        # Pattern tracking with timestamps for memory management
        self.logged_signals = {}  # Dict[signal_key, timestamp] for time-based cleanup
        
        self.logger.info(f"Enhanced Engulfing Strategy initialized with parameters: {params}")
    
    def analyze_market(self, data: pd.DataFrame, current_price: float) -> List[StrategySignal]:
        """Analyze market data for engulfing patterns."""
        signals = []
        
        self.logger.info(f"Analyzing market for engulfing patterns - data shape: {data.shape}, enabled: {self.is_enabled}")
        
        if not self.is_enabled or not self.check_data_requirements(data):
            self.logger.info(f"Strategy disabled or data requirements not met")
            return signals
        
        # Get the last few candles for pattern detection
        if len(data) < 2:
            self.logger.info(f"Not enough data: {len(data)} < 2")
            return signals
        
        current_candle = data.iloc[-1]
        previous_candle = data.iloc[-2]
        current_idx = len(data) - 1
        
        self.logger.info(f"Pattern detection - current: close={current_candle.get('close', 'N/A'):.5f}, previous: close={previous_candle.get('close', 'N/A'):.5f}")
        self.logger.info(f"Available columns: {list(data.columns)}")
        
        # Check for bullish engulfing
        bullish_signal = self._detect_bullish_engulfing(
            data, current_candle, previous_candle, current_idx
        )
        if bullish_signal:
            signals.append(bullish_signal)
        
        # Check for bearish engulfing
        bearish_signal = self._detect_bearish_engulfing(
            data, current_candle, previous_candle, current_idx
        )
        if bearish_signal:
            signals.append(bearish_signal)
        
        return signals
    
    def _detect_bullish_engulfing(self, data: pd.DataFrame, current: pd.Series, 
                                 previous: pd.Series, idx: int) -> Optional[StrategySignal]:
        """Detect bullish engulfing pattern."""
        
        # Debug logging for pattern detection
        self.logger.info(f"Checking bullish engulfing at {idx}")
        
        # Basic engulfing pattern conditions
        prev_bearish = previous.get('is_bearish', False)
        curr_bullish = current.get('is_bullish', False)
        
        # Debug candle OHLC values
        self.logger.info(f"Previous candle: O={previous.get('open', 0):.5f}, C={previous.get('close', 0):.5f}, bearish={prev_bearish}")
        self.logger.info(f"Current candle: O={current.get('open', 0):.5f}, C={current.get('close', 0):.5f}, bullish={curr_bullish}")
        
        if not (prev_bearish and curr_bullish):
            self.logger.info(f"No engulfing pattern: need prev_bearish=True AND curr_bullish=True, got prev_bearish={prev_bearish}, curr_bullish={curr_bullish}")
            return None
        
        if not (current['open'] < previous['close'] and current['close'] > previous['open']):
            self.logger.info(f"No price engulfing: curr_open={current['open']:.4f} vs prev_close={previous['close']:.4f}, curr_close={current['close']:.4f} vs prev_open={previous['open']:.4f}")
            return None
        
        # Body ratio check
        if current['body_ratio'] < self.min_body_ratio:
            self.logger.info(f"Body ratio too small: {current['body_ratio']:.3f} < {self.min_body_ratio}")
            return None
        
        # Volume confirmation
        if current['volume_ratio'] < self.volume_multiplier:
            self.logger.info(f"Volume too low: {current['volume_ratio']:.2f} < {self.volume_multiplier}")
            return None
        
        # RSI check - should be oversold but not extremely so
        if not (self.rsi_min <= current['rsi'] <= self.rsi_max):
            self.logger.info(f"RSI out of range: {current['rsi']:.1f} not in [{self.rsi_min}, {self.rsi_max}]")
            return None
        
        # Trend context - prefer patterns against downtrend
        if len(data) >= self.ema_period:
            if current['close'] < current['ema']:  # Price below EMA suggests downtrend
                trend_confirmation = True
            else:
                trend_confirmation = False
        else:
            trend_confirmation = True
        
        # Calculate confidence based on pattern strength
        confidence = self._calculate_bullish_confidence(current, previous, data)
        
        if confidence < self.config.min_confidence:
            return None
        
        # Prevent duplicate logging with memory management
        signal_key = f"LONG_{idx}_{current['high']}"
        current_time = datetime.now()
        
        # Clean up old signals (older than 1 hour) to prevent memory leaks
        self._cleanup_old_signals(current_time)
        
        if signal_key in self.logged_signals:
            return None
        
        self.logged_signals[signal_key] = current_time
        
        # Calculate stop loss and take profit
        entry_price = current['close']
        atr = data['atr'].iloc[-1] if 'atr' in data.columns else (current['high'] - current['low'])
        
        stop_loss = entry_price - (2 * atr)  # 2 ATR stop
        take_profit = entry_price + (3 * atr)  # 3 ATR target (1:1.5 risk/reward)
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=current.name if hasattr(current, 'name') else 'UNKNOWN',
            signal_type='LONG',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                'strategy_name': self.name,
                'pattern': 'bullish_engulfing',
                'volume_ratio': current['volume_ratio'],
                'rsi': current['rsi'],
                'body_ratio': current['body_ratio'],
                'trend_confirmation': trend_confirmation,
                'atr': atr
            }
        )
        
        self.logger.info(
            f"Bullish engulfing detected at {idx} | "
            f"Price: {entry_price:.4f} | Confidence: {confidence:.2f} | "
            f"Volume: {current['volume_ratio']:.1f}x | RSI: {current['rsi']:.1f}"
        )
        
        return signal
    
    def _detect_bearish_engulfing(self, data: pd.DataFrame, current: pd.Series, 
                                 previous: pd.Series, idx: int) -> Optional[StrategySignal]:
        """Detect bearish engulfing pattern."""
        
        self.logger.info(f"Checking bearish engulfing at {idx}")
        
        # Debug candle OHLC values
        prev_bullish = previous.get('is_bullish', False)
        curr_bearish = current.get('is_bearish', False)
        
        self.logger.info(f"Previous candle: O={previous.get('open', 0):.5f}, C={previous.get('close', 0):.5f}, bullish={prev_bullish}")
        self.logger.info(f"Current candle: O={current.get('open', 0):.5f}, C={current.get('close', 0):.5f}, bearish={curr_bearish}")
        
        # Basic engulfing pattern conditions
        if not (prev_bullish and curr_bearish):
            self.logger.info(f"No bearish engulfing pattern: need prev_bullish=True AND curr_bearish=True, got prev_bullish={prev_bullish}, curr_bearish={curr_bearish}")
            return None
        
        if not (current['open'] > previous['close'] and current['close'] < previous['open']):
            return None
        
        # Body ratio check
        if current['body_ratio'] < self.min_body_ratio:
            return None
        
        # Volume confirmation
        if current['volume_ratio'] < self.volume_multiplier:
            return None
        
        # RSI check - should be overbought but not extremely so
        if not (self.rsi_min <= current['rsi'] <= self.rsi_max):
            return None
        
        # Trend context - prefer patterns against uptrend
        if len(data) >= self.ema_period:
            if current['close'] > current['ema']:  # Price above EMA suggests uptrend
                trend_confirmation = True
            else:
                trend_confirmation = False
        else:
            trend_confirmation = True
        
        # Calculate confidence based on pattern strength
        confidence = self._calculate_bearish_confidence(current, previous, data)
        
        if confidence < self.config.min_confidence:
            return None
        
        # Prevent duplicate logging with memory management
        signal_key = f"SHORT_{idx}_{current['low']}"
        current_time = datetime.now()
        
        # Clean up old signals (older than 1 hour) to prevent memory leaks
        self._cleanup_old_signals(current_time)
        
        if signal_key in self.logged_signals:
            return None
        
        self.logged_signals[signal_key] = current_time
        
        # Calculate stop loss and take profit
        entry_price = current['close']
        atr = data['atr'].iloc[-1] if 'atr' in data.columns else (current['high'] - current['low'])
        
        stop_loss = entry_price + (2 * atr)  # 2 ATR stop
        take_profit = entry_price - (3 * atr)  # 3 ATR target (1:1.5 risk/reward)
        
        signal = StrategySignal(
            timestamp=datetime.now(),
            symbol=current.name if hasattr(current, 'name') else 'UNKNOWN',
            signal_type='SHORT',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={
                'strategy_name': self.name,
                'pattern': 'bearish_engulfing',
                'volume_ratio': current['volume_ratio'],
                'rsi': current['rsi'],
                'body_ratio': current['body_ratio'],
                'trend_confirmation': trend_confirmation,
                'atr': atr
            }
        )
        
        self.logger.info(
            f"Bearish engulfing detected at {idx} | "
            f"Price: {entry_price:.4f} | Confidence: {confidence:.2f} | "
            f"Volume: {current['volume_ratio']:.1f}x | RSI: {current['rsi']:.1f}"
        )
        
        return signal
    
    def _cleanup_old_signals(self, current_time: datetime):
        """Clean up old signal records to prevent memory leaks."""
        from datetime import timedelta
        
        # Remove signals older than 1 hour
        cutoff_time = current_time - timedelta(hours=1)
        signals_to_remove = [
            signal_key for signal_key, timestamp in self.logged_signals.items()
            if timestamp < cutoff_time
        ]
        
        for signal_key in signals_to_remove:
            del self.logged_signals[signal_key]
        
        # Log cleanup if significant number of signals were removed
        if len(signals_to_remove) > 10:
            self.logger.debug(f"Cleaned up {len(signals_to_remove)} old signal records")
    
    def _calculate_bullish_confidence(self, current: pd.Series, previous: pd.Series, 
                                    data: pd.DataFrame) -> float:
        """Calculate confidence for bullish signal."""
        confidence = 0.0
        
        # Base confidence from body ratio
        confidence += min(current['body_ratio'], 1.0) * 0.3
        
        # Volume confirmation strength
        volume_strength = min(current['volume_ratio'] / self.volume_multiplier, 2.0)
        confidence += volume_strength * 0.3
        
        # RSI positioning (prefer lower RSI for bullish)
        rsi_score = (self.rsi_max - current['rsi']) / (self.rsi_max - self.rsi_min)
        confidence += rsi_score * 0.2
        
        # Engulfing completeness (safe division to avoid NaN)
        previous_body = previous['open'] - previous['close']
        if abs(previous_body) > 0.0001:  # Avoid division by zero for doji candles
            engulfing_ratio = abs(current['close'] - previous['open']) / abs(previous_body)
            confidence += min(engulfing_ratio, 2.0) * 0.2
        else:
            # Previous candle is doji (no body), skip engulfing ratio
            confidence += 0.1  # Small bonus for engulfing a doji
        
        return min(confidence, 1.0)
    
    def _calculate_bearish_confidence(self, current: pd.Series, previous: pd.Series, 
                                     data: pd.DataFrame) -> float:
        """Calculate confidence for bearish signal."""
        confidence = 0.0
        
        # Base confidence from body ratio
        confidence += min(current['body_ratio'], 1.0) * 0.3
        
        # Volume confirmation strength
        volume_strength = min(current['volume_ratio'] / self.volume_multiplier, 2.0)
        confidence += volume_strength * 0.3
        
        # RSI positioning (prefer higher RSI for bearish)
        rsi_score = (current['rsi'] - self.rsi_min) / (self.rsi_max - self.rsi_min)
        confidence += rsi_score * 0.2
        
        # Engulfing completeness (safe division to avoid NaN)
        previous_body = previous['close'] - previous['open']
        if abs(previous_body) > 0.0001:  # Avoid division by zero for doji candles
            engulfing_ratio = abs(previous['close'] - current['close']) / abs(previous_body)
            confidence += min(engulfing_ratio, 2.0) * 0.2
        else:
            # Previous candle is doji (no body), skip engulfing ratio
            confidence += 0.1  # Small bonus for engulfing a doji
        
        return min(confidence, 1.0)
    
    def validate_signal(self, signal: StrategySignal, market_context: Dict) -> bool:
        """Validate signal against market context."""
        
        # Check if market conditions are suitable
        volatility = market_context.get('volatility_regime', 'NORMAL')
        if volatility == 'EXTREME':
            self.logger.warning(f"Signal rejected due to extreme volatility")
            return False
        
        # Check time since last signal to avoid overtrading
        if self.last_signal_time:
            time_diff = (signal.timestamp - self.last_signal_time).total_seconds()
            min_interval = 300  # 5 minutes minimum between signals
            if time_diff < min_interval:
                self.logger.warning(f"Signal rejected: too soon after last signal ({time_diff}s)")
                return False
        
        # Additional validation can be added here
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
            f"Position size calculation: {position_size:.6f} | "
            f"Confidence: {confidence_multiplier:.2f} | "
            f"Volatility adj: {volatility_adjustment:.2f}"
        )
        
        return position_size
    
    def get_signal_strength(self, data: pd.DataFrame, signal_type: str) -> float:
        """Calculate overall signal strength for the strategy."""
        if len(data) < 2:
            return 0.0
        
        current = data.iloc[-1]
        
        # Combine multiple factors for overall strength
        strength = 0.0
        
        # Volume strength
        if 'volume_ratio' in data.columns:
            volume_strength = min(current['volume_ratio'] / self.volume_multiplier, 2.0) / 2.0
            strength += volume_strength * 0.4
        
        # RSI positioning
        if 'rsi' in data.columns:
            if signal_type == 'LONG':
                rsi_strength = (self.rsi_max - current['rsi']) / (self.rsi_max - self.rsi_min)
            else:  # SHORT
                rsi_strength = (current['rsi'] - self.rsi_min) / (self.rsi_max - self.rsi_min)
            strength += rsi_strength * 0.3
        
        # Body ratio strength
        if 'body_ratio' in data.columns:
            body_strength = min(current['body_ratio'], 1.0)
            strength += body_strength * 0.3
        
        return min(strength, 1.0)