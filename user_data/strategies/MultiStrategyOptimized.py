"""
Optimized Multi-Strategy Consensus Trading Strategy
Enhanced version with dynamic weights and improved risk management

Based on successful try1 bot analysis that achieved 2% average overnight wins
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, CategoricalParameter
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class SignalType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"

class StrategySignal:
    def __init__(self, signal_type: SignalType, confidence: float, strategy_name: str, weight: float):
        self.signal_type = signal_type
        self.confidence = confidence
        self.strategy_name = strategy_name
        self.weight = weight
        self.weighted_confidence = confidence * weight

class MultiStrategyOptimized(IStrategy):
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # Optimizable ROI parameters
    minimal_roi = {
        "0": 0.015,   # 1.5% target (optimizable)
        "30": 0.010,  # 1.0% after 30 minutes
        "60": 0.005,  # 0.5% after 1 hour
        "120": 0.0    # Break even after 2 hours
    }
    
    stoploss = -0.025  # 2.5% stop loss (slightly increased for safety)
    
    # Optimizable strategy weights
    engulfing_weight = DecimalParameter(0.15, 0.35, decimals=2, default=0.25, space="buy")
    rsi_weight = DecimalParameter(0.10, 0.30, decimals=2, default=0.20, space="buy")
    ma_weight = DecimalParameter(0.10, 0.30, decimals=2, default=0.20, space="buy")
    volume_weight = DecimalParameter(0.05, 0.25, decimals=2, default=0.15, space="buy")
    breakout_weight = DecimalParameter(0.05, 0.20, decimals=2, default=0.10, space="buy")
    momentum_weight = DecimalParameter(0.05, 0.20, decimals=2, default=0.10, space="buy")
    
    # Consensus parameters for optimization
    consensus_threshold = DecimalParameter(0.30, 0.60, decimals=2, default=0.45, space="buy")
    min_consensus_strength = DecimalParameter(0.20, 0.50, decimals=2, default=0.33, space="buy")
    
    # Risk management parameters
    volatility_threshold = DecimalParameter(2.0, 5.0, decimals=1, default=3.5, space="buy")
    volume_threshold = DecimalParameter(1.2, 2.5, decimals=1, default=1.5, space="buy")
    
    # ROI optimization parameters
    roi_target = DecimalParameter(0.008, 0.025, decimals=3, default=0.015, space="sell")
    roi_time_1 = IntParameter(15, 60, default=30, space="sell")
    roi_time_2 = IntParameter(45, 120, default=60, space="sell")
    
    def __post_init__(self):
        """Update dynamic parameters after optimization"""
        # Update ROI based on optimized parameters
        if hasattr(self, 'roi_target'):
            self.minimal_roi = {
                "0": self.roi_target.value,
                str(self.roi_time_1.value): self.roi_target.value * 0.67,
                str(self.roi_time_2.value): self.roi_target.value * 0.33,
                "240": 0.0
            }
    
    @property
    def strategy_weights(self) -> Dict[str, float]:
        """Dynamic strategy weights based on optimization"""
        weights = {
            'engulfing': self.engulfing_weight.value,
            'rsi_bounce': self.rsi_weight.value,
            'ma_crossover': self.ma_weight.value,
            'volume_spike': self.volume_weight.value,
            'breakout': self.breakout_weight.value,
            'momentum': self.momentum_weight.value
        }
        
        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v/total_weight for k, v in weights.items()}
        
        return weights
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate all indicators needed for the 6 strategies"""
        
        # Basic indicators
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_trend'] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Volatility indicators
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['bb_upper'], dataframe['bb_middle'], dataframe['bb_lower'] = ta.BBANDS(dataframe, timeperiod=20)
        
        # Price action indicators
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['upper_shadow'] = dataframe['high'] - dataframe[['close', 'open']].max(axis=1)
        dataframe['lower_shadow'] = dataframe[['close', 'open']].min(axis=1) - dataframe['low']
        
        # Support/Resistance levels
        dataframe['pivot_high'] = dataframe['high'].rolling(window=5).max()
        dataframe['pivot_low'] = dataframe['low'].rolling(window=5).min()
        
        # Momentum indicators
        dataframe['macd'], dataframe['macd_signal'], dataframe['macd_hist'] = ta.MACD(dataframe)
        dataframe['stoch_k'], dataframe['stoch_d'] = ta.STOCH(dataframe)
        
        # Volatility regime detection
        dataframe['volatility_regime'] = self._calculate_volatility_regime(dataframe)
        
        return dataframe
    
    def _calculate_volatility_regime(self, dataframe: DataFrame) -> pd.Series:
        """Calculate volatility regime to filter trades during extreme conditions"""
        atr_sma = ta.SMA(dataframe['atr'], timeperiod=20)
        volatility_ratio = dataframe['atr'] / atr_sma
        return volatility_ratio
    
    def _engulfing_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Enhanced Engulfing Pattern Strategy"""
        
        # Bullish engulfing pattern
        bullish_engulfing = (
            (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &
            (dataframe['close'] > dataframe['open']) &
            (dataframe['open'] < dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['open'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_sma'] * self.volume_threshold.value)
        )
        
        # Bearish engulfing pattern
        bearish_engulfing = (
            (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &
            (dataframe['close'] < dataframe['open']) &
            (dataframe['open'] > dataframe['close'].shift(1)) &
            (dataframe['close'] < dataframe['open'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_sma'] * self.volume_threshold.value)
        )
        
        if bullish_engulfing.iloc[-1]:
            confidence = min(0.95, 0.7 + (dataframe['volume_ratio'].iloc[-1] - self.volume_threshold.value) * 0.5)
            return StrategySignal(SignalType.LONG, confidence, 'engulfing', self.strategy_weights['engulfing'])
        elif bearish_engulfing.iloc[-1]:
            confidence = min(0.95, 0.7 + (dataframe['volume_ratio'].iloc[-1] - self.volume_threshold.value) * 0.5)
            return StrategySignal(SignalType.SHORT, confidence, 'engulfing', self.strategy_weights['engulfing'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'engulfing', self.strategy_weights['engulfing'])
    
    def _rsi_bounce_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """RSI Bounce Strategy with dynamic thresholds"""
        
        rsi = dataframe['rsi'].iloc[-1]
        rsi_prev = dataframe['rsi'].iloc[-2]
        
        # Dynamic RSI thresholds based on volatility
        volatility = dataframe['volatility_regime'].iloc[-1]
        oversold_threshold = 30 + (volatility - 1) * 5
        overbought_threshold = 70 - (volatility - 1) * 5
        
        # Oversold bounce
        if rsi < oversold_threshold and rsi > rsi_prev and dataframe['close'].iloc[-1] > dataframe['ema_fast'].iloc[-1]:
            confidence = min(0.90, 0.6 + (oversold_threshold - rsi) / oversold_threshold * 0.3)
            return StrategySignal(SignalType.LONG, confidence, 'rsi_bounce', self.strategy_weights['rsi_bounce'])
        
        # Overbought reversal
        elif rsi > overbought_threshold and rsi < rsi_prev and dataframe['close'].iloc[-1] < dataframe['ema_fast'].iloc[-1]:
            confidence = min(0.90, 0.6 + (rsi - overbought_threshold) / (100 - overbought_threshold) * 0.3)
            return StrategySignal(SignalType.SHORT, confidence, 'rsi_bounce', self.strategy_weights['rsi_bounce'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'rsi_bounce', self.strategy_weights['rsi_bounce'])
    
    def _ma_crossover_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """MA Crossover Strategy with trend confirmation"""
        
        ema_fast = dataframe['ema_fast'].iloc[-1]
        ema_slow = dataframe['ema_slow'].iloc[-1]
        ema_fast_prev = dataframe['ema_fast'].iloc[-2]
        ema_slow_prev = dataframe['ema_slow'].iloc[-2]
        ema_trend = dataframe['ema_trend'].iloc[-1]
        
        # Bullish crossover with trend confirmation
        if ema_fast > ema_slow and ema_fast_prev <= ema_slow_prev and ema_fast > ema_trend:
            trend_strength = abs(ema_fast - ema_slow) / ema_slow
            confidence = min(0.85, 0.65 + trend_strength * 100)
            return StrategySignal(SignalType.LONG, confidence, 'ma_crossover', self.strategy_weights['ma_crossover'])
        
        # Bearish crossover with trend confirmation
        elif ema_fast < ema_slow and ema_fast_prev >= ema_slow_prev and ema_fast < ema_trend:
            trend_strength = abs(ema_fast - ema_slow) / ema_slow
            confidence = min(0.85, 0.65 + trend_strength * 100)
            return StrategySignal(SignalType.SHORT, confidence, 'ma_crossover', self.strategy_weights['ma_crossover'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'ma_crossover', self.strategy_weights['ma_crossover'])
    
    def _volume_spike_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Volume Spike Strategy with price confirmation"""
        
        volume_ratio = dataframe['volume_ratio'].iloc[-1]
        price_change = (dataframe['close'].iloc[-1] - dataframe['open'].iloc[-1]) / dataframe['open'].iloc[-1]
        
        min_volume_ratio = self.volume_threshold.value
        
        # Volume spike with price movement
        if volume_ratio > min_volume_ratio:
            if price_change > 0.002:  # 0.2% positive move
                confidence = min(0.80, 0.55 + min(volume_ratio / 3.0, 0.25))
                return StrategySignal(SignalType.LONG, confidence, 'volume_spike', self.strategy_weights['volume_spike'])
            elif price_change < -0.002:  # 0.2% negative move
                confidence = min(0.80, 0.55 + min(volume_ratio / 3.0, 0.25))
                return StrategySignal(SignalType.SHORT, confidence, 'volume_spike', self.strategy_weights['volume_spike'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'volume_spike', self.strategy_weights['volume_spike'])
    
    def _breakout_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Breakout Strategy with volume confirmation"""
        
        current_price = dataframe['close'].iloc[-1]
        pivot_high = dataframe['pivot_high'].iloc[-2]
        pivot_low = dataframe['pivot_low'].iloc[-2]
        volume_confirmation = dataframe['volume_ratio'].iloc[-1] > 1.3
        
        # Upward breakout
        if current_price > pivot_high and volume_confirmation:
            confidence = min(0.75, 0.55 + (current_price - pivot_high) / pivot_high * 10)
            return StrategySignal(SignalType.LONG, confidence, 'breakout', self.strategy_weights['breakout'])
        
        # Downward breakout
        elif current_price < pivot_low and volume_confirmation:
            confidence = min(0.75, 0.55 + (pivot_low - current_price) / pivot_low * 10)
            return StrategySignal(SignalType.SHORT, confidence, 'breakout', self.strategy_weights['breakout'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'breakout', self.strategy_weights['breakout'])
    
    def _momentum_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Momentum Backup Strategy with improved error handling"""
        
        if len(dataframe) < 2:
            return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.strategy_weights['momentum'])
        
        try:
            macd_hist = float(dataframe['macd_hist'].iloc[-1])
            macd_hist_prev = float(dataframe['macd_hist'].iloc[-2])
            stoch_k = float(dataframe['stoch_k'].iloc[-1])
        except (ValueError, TypeError, IndexError):
            return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.strategy_weights['momentum'])
        
        # Check for NaN values
        if np.isnan(macd_hist) or np.isnan(macd_hist_prev) or np.isnan(stoch_k):
            return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.strategy_weights['momentum'])
        
        # Bullish momentum
        if macd_hist > 0 and macd_hist > macd_hist_prev and stoch_k > 20 and stoch_k < 80:
            confidence = min(0.70, 0.50 + abs(macd_hist) * 1000)
            return StrategySignal(SignalType.LONG, confidence, 'momentum', self.strategy_weights['momentum'])
        
        # Bearish momentum
        elif macd_hist < 0 and macd_hist < macd_hist_prev and stoch_k < 80 and stoch_k > 20:
            confidence = min(0.70, 0.50 + abs(macd_hist) * 1000)
            return StrategySignal(SignalType.SHORT, confidence, 'momentum', self.strategy_weights['momentum'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.strategy_weights['momentum'])
    
    def _generate_signals(self, dataframe: DataFrame, metadata: Dict) -> List[StrategySignal]:
        """Generate signals from all 6 strategies"""
        signals = []
        
        signals.append(self._engulfing_strategy(dataframe, metadata))
        signals.append(self._rsi_bounce_strategy(dataframe, metadata))
        signals.append(self._ma_crossover_strategy(dataframe, metadata))
        signals.append(self._volume_spike_strategy(dataframe, metadata))
        signals.append(self._breakout_strategy(dataframe, metadata))
        signals.append(self._momentum_strategy(dataframe, metadata))
        
        return signals
    
    def _weighted_consensus(self, signals: List[StrategySignal], pair: str) -> Tuple[SignalType, float, float]:
        """Calculate weighted consensus from multiple strategy signals"""
        
        long_signals = [s for s in signals if s.signal_type == SignalType.LONG]
        short_signals = [s for s in signals if s.signal_type == SignalType.SHORT]
        
        if not long_signals and not short_signals:
            return SignalType.NEUTRAL, 0.0, 0.0
        
        # Calculate weighted confidence for each direction
        long_confidence = sum(s.weighted_confidence for s in long_signals) if long_signals else 0
        short_confidence = sum(s.weighted_confidence for s in short_signals) if short_signals else 0
        
        # Determine winning direction
        if long_confidence > short_confidence:
            winning_signals = long_signals
            consensus_confidence = long_confidence
            signal_type = SignalType.LONG
        else:
            winning_signals = short_signals
            consensus_confidence = short_confidence
            signal_type = SignalType.SHORT
        
        # Calculate consensus strength
        total_strategies = len([s for s in signals if s.signal_type != SignalType.NEUTRAL])
        consensus_strength = len(winning_signals) / max(total_strategies, 1) if total_strategies > 0 else 0
        
        # Apply consensus strength adjustment
        final_confidence = consensus_confidence * consensus_strength
        
        return signal_type, final_confidence, consensus_strength
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate entry signals using optimized multi-strategy consensus"""
        
        # Initialize entry columns
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        dataframe['enter_tag'] = ''
        
        # Process each row
        for i in range(len(dataframe)):
            if i < 50:  # Need enough history for indicators
                continue
            
            # Create a slice up to current row
            current_data = dataframe.iloc[:i+1].copy()
            
            # Check volatility filter
            if current_data['volatility_regime'].iloc[-1] > self.volatility_threshold.value:
                continue
            
            # Generate signals from all strategies
            signals = self._generate_signals(current_data, metadata)
            
            # Calculate weighted consensus
            signal_type, confidence, consensus_strength = self._weighted_consensus(signals, metadata['pair'])
            
            # Check consensus requirements
            if (confidence >= self.consensus_threshold.value and 
                consensus_strength >= self.min_consensus_strength.value):
                
                active_strategies = [s.strategy_name for s in signals if s.signal_type == signal_type]
                enter_tag = f"opt_{signal_type.value.lower()}_{len(active_strategies)}strat_{confidence:.2f}conf"
                
                if signal_type == SignalType.LONG:
                    dataframe.loc[i, 'enter_long'] = 1
                    dataframe.loc[i, 'enter_tag'] = enter_tag
                elif signal_type == SignalType.SHORT:
                    dataframe.loc[i, 'enter_short'] = 1
                    dataframe.loc[i, 'enter_tag'] = enter_tag
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate exit signals with improved logic"""
        
        # Initialize exit columns
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        dataframe['exit_tag'] = ''
        
        # Exit on strong opposite consensus
        for i in range(len(dataframe)):
            if i < 50:
                continue
            
            current_data = dataframe.iloc[:i+1].copy()
            signals = self._generate_signals(current_data, metadata)
            signal_type, confidence, consensus_strength = self._weighted_consensus(signals, metadata['pair'])
            
            # Strong opposite signal for early exit
            if (confidence >= 0.75 and consensus_strength >= 0.60):
                if signal_type == SignalType.SHORT:
                    dataframe.loc[i, 'exit_long'] = 1
                    dataframe.loc[i, 'exit_tag'] = 'opt_consensus_short_exit'
                elif signal_type == SignalType.LONG:
                    dataframe.loc[i, 'exit_short'] = 1
                    dataframe.loc[i, 'exit_tag'] = 'opt_consensus_long_exit'
        
        return dataframe
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """Conservative leverage for optimized strategy"""
        return min(proposed_leverage, 2.0)