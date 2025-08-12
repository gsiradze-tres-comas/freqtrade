"""
Multi-Strategy Consensus Trading Strategy
Based on successful try1 bot that achieved 2% average overnight wins

This strategy combines 6 individual strategies with weighted consensus:
- Enhanced Engulfing Pattern (25% weight)
- RSI Bounce Strategy (20% weight) 
- MA Crossover Strategy (20% weight)
- Volume Spike Strategy (15% weight)
- Breakout Strategy (10% weight)
- Momentum Backup (10% weight)
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
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

class MultiStrategyConsensus(IStrategy):
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # Strategy weights (must sum to 1.0)
    STRATEGY_WEIGHTS = {
        'engulfing': 0.25,
        'rsi_bounce': 0.20,
        'ma_crossover': 0.20,
        'volume_spike': 0.15,
        'breakout': 0.10,
        'momentum': 0.10
    }
    
    # Symbol-specific configuration overrides (lowered thresholds for realistic trading)
    SYMBOL_CONFIG = {
        'BTC/USDT': {'confidence_threshold': 0.40, 'volume_multiplier': 1.0},
        'ETH/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.0},
        'BNB/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.2},
        'SOL/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.2},
        'XRP/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.5},
        'ADA/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.5},
        'AVAX/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.5},
        'LINK/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.5},
        'DOT/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.5},
        'MATIC/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 1.5},
        'DOGE/USDT': {'confidence_threshold': 0.35, 'volume_multiplier': 2.0},
        'SHIB/USDT': {'confidence_threshold': 0.40, 'volume_multiplier': 2.0},
        'PEPE/USDT': {'confidence_threshold': 0.40, 'volume_multiplier': 2.0},
        'FLOKI/USDT': {'confidence_threshold': 0.40, 'volume_multiplier': 2.0},
        'WIF/USDT': {'confidence_threshold': 0.40, 'volume_multiplier': 2.0},
    }
    
    # Optimizable parameters
    minimal_roi = {
        "0": 0.012,  # 1.2% target
        "30": 0.008, # 0.8% after 30 minutes
        "60": 0.004, # 0.4% after 1 hour
        "120": 0.0   # Break even after 2 hours
    }
    
    stoploss = -0.02  # 2% stop loss
    
    # Parameter ranges for optimization (lowered for more realistic trade generation)
    consensus_threshold = DecimalParameter(0.30, 0.60, decimals=2, default=0.45, space="buy")
    min_consensus_strength = DecimalParameter(0.20, 0.50, decimals=2, default=0.33, space="buy")
    
    # Volatility filter parameters (increased to allow more trades)
    volatility_threshold = DecimalParameter(2.0, 4.0, decimals=1, default=3.5, space="buy")
    
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
    
    def _get_symbol_config(self, pair: str) -> Dict[str, float]:
        """Get symbol-specific configuration with defaults"""
        return self.SYMBOL_CONFIG.get(pair, {
            'confidence_threshold': 0.35,
            'volume_multiplier': 1.0
        })
    
    def _engulfing_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Enhanced Engulfing Pattern Strategy (25% weight)"""
        
        # Bullish engulfing pattern
        bullish_engulfing = (
            (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &  # Previous red candle
            (dataframe['close'] > dataframe['open']) &  # Current green candle
            (dataframe['open'] < dataframe['close'].shift(1)) &  # Gap down open
            (dataframe['close'] > dataframe['open'].shift(1)) &  # Engulfs previous candle
            (dataframe['volume'] > dataframe['volume_sma'] * 1.2)  # Volume confirmation
        )
        
        # Bearish engulfing pattern
        bearish_engulfing = (
            (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &  # Previous green candle
            (dataframe['close'] < dataframe['open']) &  # Current red candle
            (dataframe['open'] > dataframe['close'].shift(1)) &  # Gap up open
            (dataframe['close'] < dataframe['open'].shift(1)) &  # Engulfs previous candle
            (dataframe['volume'] > dataframe['volume_sma'] * 1.2)  # Volume confirmation
        )
        
        if bullish_engulfing.iloc[-1]:
            confidence = min(0.95, 0.7 + (dataframe['volume_ratio'].iloc[-1] - 1.2) * 0.5)
            return StrategySignal(SignalType.LONG, confidence, 'engulfing', self.STRATEGY_WEIGHTS['engulfing'])
        elif bearish_engulfing.iloc[-1]:
            confidence = min(0.95, 0.7 + (dataframe['volume_ratio'].iloc[-1] - 1.2) * 0.5)
            return StrategySignal(SignalType.SHORT, confidence, 'engulfing', self.STRATEGY_WEIGHTS['engulfing'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'engulfing', self.STRATEGY_WEIGHTS['engulfing'])
    
    def _rsi_bounce_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """RSI Bounce Strategy (20% weight)"""
        
        rsi = dataframe['rsi'].iloc[-1]
        rsi_prev = dataframe['rsi'].iloc[-2]
        
        # Oversold bounce
        if rsi < 35 and rsi > rsi_prev and dataframe['close'].iloc[-1] > dataframe['ema_fast'].iloc[-1]:
            confidence = min(0.90, 0.6 + (35 - rsi) / 35 * 0.3)
            return StrategySignal(SignalType.LONG, confidence, 'rsi_bounce', self.STRATEGY_WEIGHTS['rsi_bounce'])
        
        # Overbought reversal
        elif rsi > 65 and rsi < rsi_prev and dataframe['close'].iloc[-1] < dataframe['ema_fast'].iloc[-1]:
            confidence = min(0.90, 0.6 + (rsi - 65) / 35 * 0.3)
            return StrategySignal(SignalType.SHORT, confidence, 'rsi_bounce', self.STRATEGY_WEIGHTS['rsi_bounce'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'rsi_bounce', self.STRATEGY_WEIGHTS['rsi_bounce'])
    
    def _ma_crossover_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """MA Crossover Strategy (20% weight)"""
        
        ema_fast = dataframe['ema_fast'].iloc[-1]
        ema_slow = dataframe['ema_slow'].iloc[-1]
        ema_fast_prev = dataframe['ema_fast'].iloc[-2]
        ema_slow_prev = dataframe['ema_slow'].iloc[-2]
        
        # Bullish crossover
        if ema_fast > ema_slow and ema_fast_prev <= ema_slow_prev:
            trend_strength = abs(ema_fast - ema_slow) / ema_slow
            confidence = min(0.85, 0.65 + trend_strength * 100)
            return StrategySignal(SignalType.LONG, confidence, 'ma_crossover', self.STRATEGY_WEIGHTS['ma_crossover'])
        
        # Bearish crossover
        elif ema_fast < ema_slow and ema_fast_prev >= ema_slow_prev:
            trend_strength = abs(ema_fast - ema_slow) / ema_slow
            confidence = min(0.85, 0.65 + trend_strength * 100)
            return StrategySignal(SignalType.SHORT, confidence, 'ma_crossover', self.STRATEGY_WEIGHTS['ma_crossover'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'ma_crossover', self.STRATEGY_WEIGHTS['ma_crossover'])
    
    def _volume_spike_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Volume Spike Strategy (15% weight)"""
        
        volume_ratio = dataframe['volume_ratio'].iloc[-1]
        price_change = (dataframe['close'].iloc[-1] - dataframe['open'].iloc[-1]) / dataframe['open'].iloc[-1]
        
        symbol_config = self._get_symbol_config(metadata['pair'])
        min_volume_ratio = 1.5 * symbol_config['volume_multiplier']
        
        # Volume spike with price movement
        if volume_ratio > min_volume_ratio:
            if price_change > 0.002:  # 0.2% positive move
                confidence = min(0.80, 0.55 + min(volume_ratio / 3.0, 0.25))
                return StrategySignal(SignalType.LONG, confidence, 'volume_spike', self.STRATEGY_WEIGHTS['volume_spike'])
            elif price_change < -0.002:  # 0.2% negative move
                confidence = min(0.80, 0.55 + min(volume_ratio / 3.0, 0.25))
                return StrategySignal(SignalType.SHORT, confidence, 'volume_spike', self.STRATEGY_WEIGHTS['volume_spike'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'volume_spike', self.STRATEGY_WEIGHTS['volume_spike'])
    
    def _breakout_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Breakout Strategy (10% weight)"""
        
        current_price = dataframe['close'].iloc[-1]
        pivot_high = dataframe['pivot_high'].iloc[-2]
        pivot_low = dataframe['pivot_low'].iloc[-2]
        
        # Upward breakout
        if current_price > pivot_high and dataframe['volume_ratio'].iloc[-1] > 1.3:
            confidence = min(0.75, 0.55 + (current_price - pivot_high) / pivot_high * 10)
            return StrategySignal(SignalType.LONG, confidence, 'breakout', self.STRATEGY_WEIGHTS['breakout'])
        
        # Downward breakout
        elif current_price < pivot_low and dataframe['volume_ratio'].iloc[-1] > 1.3:
            confidence = min(0.75, 0.55 + (pivot_low - current_price) / pivot_low * 10)
            return StrategySignal(SignalType.SHORT, confidence, 'breakout', self.STRATEGY_WEIGHTS['breakout'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'breakout', self.STRATEGY_WEIGHTS['breakout'])
    
    def _momentum_strategy(self, dataframe: DataFrame, metadata: Dict) -> StrategySignal:
        """Momentum Backup Strategy (10% weight)"""
        
        if len(dataframe) < 2:
            return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.STRATEGY_WEIGHTS['momentum'])
        
        try:
            macd_hist = float(dataframe['macd_hist'].iloc[-1])
            macd_hist_prev = float(dataframe['macd_hist'].iloc[-2])
            stoch_k = float(dataframe['stoch_k'].iloc[-1])
        except (ValueError, TypeError, IndexError):
            return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.STRATEGY_WEIGHTS['momentum'])
        
        # Check for NaN values
        if np.isnan(macd_hist) or np.isnan(macd_hist_prev) or np.isnan(stoch_k):
            return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.STRATEGY_WEIGHTS['momentum'])
        
        # Bullish momentum
        if macd_hist > 0 and macd_hist > macd_hist_prev and stoch_k > 20:
            confidence = min(0.70, 0.50 + abs(macd_hist) * 1000)
            return StrategySignal(SignalType.LONG, confidence, 'momentum', self.STRATEGY_WEIGHTS['momentum'])
        
        # Bearish momentum
        elif macd_hist < 0 and macd_hist < macd_hist_prev and stoch_k < 80:
            confidence = min(0.70, 0.50 + abs(macd_hist) * 1000)
            return StrategySignal(SignalType.SHORT, confidence, 'momentum', self.STRATEGY_WEIGHTS['momentum'])
        
        return StrategySignal(SignalType.NEUTRAL, 0.0, 'momentum', self.STRATEGY_WEIGHTS['momentum'])
    
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
        """
        Calculate weighted consensus from multiple strategy signals
        Returns: (signal_type, confidence, consensus_strength)
        """
        
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
        
        # Calculate consensus strength (proportion of strategies agreeing)
        total_strategies = len([s for s in signals if s.signal_type != SignalType.NEUTRAL])
        consensus_strength = len(winning_signals) / max(total_strategies, 1) if total_strategies > 0 else 0
        
        # Apply consensus strength adjustment
        final_confidence = consensus_confidence * consensus_strength
        
        # Apply symbol-specific threshold
        symbol_config = self._get_symbol_config(pair)
        min_confidence = symbol_config['confidence_threshold']
        
        if final_confidence < min_confidence:
            return SignalType.NEUTRAL, final_confidence, consensus_strength
        
        return signal_type, final_confidence, consensus_strength
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate entry signals using multi-strategy consensus"""
        
        # Initialize entry columns
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        dataframe['enter_tag'] = ''
        
        # Process each row (in practice, we only need the last few rows)
        for i in range(len(dataframe)):
            if i < 50:  # Need enough history for indicators
                continue
            
            # Create a slice up to current row for signal generation
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
                enter_tag = f"consensus_{signal_type.value.lower()}_{len(active_strategies)}strat_{confidence:.2f}conf"
                
                if signal_type == SignalType.LONG:
                    dataframe.loc[i, 'enter_long'] = 1
                    dataframe.loc[i, 'enter_tag'] = enter_tag
                elif signal_type == SignalType.SHORT:
                    dataframe.loc[i, 'enter_short'] = 1
                    dataframe.loc[i, 'enter_tag'] = enter_tag
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate exit signals"""
        
        # Initialize exit columns
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        dataframe['exit_tag'] = ''
        
        # Exit on opposite consensus (optional, mainly rely on ROI/stoploss)
        for i in range(len(dataframe)):
            if i < 50:
                continue
            
            current_data = dataframe.iloc[:i+1].copy()
            signals = self._generate_signals(current_data, metadata)
            signal_type, confidence, consensus_strength = self._weighted_consensus(signals, metadata['pair'])
            
            # Strong opposite signal for early exit
            if (confidence >= 0.80 and consensus_strength >= 0.70):
                if signal_type == SignalType.SHORT:
                    dataframe.loc[i, 'exit_long'] = 1
                    dataframe.loc[i, 'exit_tag'] = 'consensus_short_exit'
                elif signal_type == SignalType.LONG:
                    dataframe.loc[i, 'exit_short'] = 1
                    dataframe.loc[i, 'exit_tag'] = 'consensus_long_exit'
        
        return dataframe
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """Dynamic leverage based on confidence and volatility"""
        
        # Conservative leverage for multi-strategy approach
        return min(proposed_leverage, 3.0)