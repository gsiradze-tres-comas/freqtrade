"""
EXACT Volume Spike Strategy from try1 bot
Copied 1-1 with identical parameters and logic that achieved 2% average overnight wins
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ExactVolumeSpikeStrategy(IStrategy):
    """
    Volume Spike Strategy generates signals when volume significantly exceeds average.
    EXACT copy from try1 bot with parameters that achieved 2% average wins.
    
    Parameters copied exactly:
    - volume_spike_threshold = 1.5 (1.5x average volume)
    - min_price_movement = 0.002 (0.2% price movement)
    - rsi_filter_enabled = False (disable RSI filter for more signals)
    - rsi_neutral_min = 25, rsi_neutral_max = 75 (wide neutral range)
    - lookback_period = 10 (volume average lookback)
    - 1.5 ATR stop loss, 2.5 ATR take profit
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # EXACT parameters from successful try1 bot
    minimal_roi = {
        "0": 0.0375,  # 3.75% (2.5 ATR target)
        "30": 0.025,  # 2.5% after 30 minutes
        "60": 0.015,  # 1.5% after 1 hour
        "120": 0.0    # Break even after 2 hours
    }
    
    stoploss = -0.0225  # 2.25% (1.5 ATR stop loss)
    
    # EXACT try1 parameters - DO NOT CHANGE
    volume_spike_threshold = DecimalParameter(1.5, 1.5, decimals=1, default=1.5, space="buy", load=True)
    min_price_movement = DecimalParameter(0.002, 0.002, decimals=3, default=0.002, space="buy", load=True)
    rsi_filter_enabled = IntParameter(0, 0, default=0, space="buy", load=True)  # Disabled
    rsi_neutral_min = IntParameter(25, 25, default=25, space="buy", load=True)
    rsi_neutral_max = IntParameter(75, 75, default=75, space="buy", load=True)
    lookback_period = IntParameter(10, 10, default=10, space="buy", load=True)
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators exactly as in try1 bot"""
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=self.lookback_period.value)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Fix NaN values exactly as try1
        dataframe['volume_ratio'] = dataframe['volume_ratio'].fillna(1.0)
        dataframe['volume_ratio'] = dataframe['volume_ratio'].replace([np.inf, -np.inf], 1.0)
        
        # RSI (for optional filtering)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # ATR for stop loss and take profit
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Price movement analysis
        dataframe['price_change'] = (dataframe['close'] - dataframe['close'].shift(1)) / dataframe['close'].shift(1)
        dataframe['price_change'] = dataframe['price_change'].fillna(0.0)
        dataframe['price_change'] = dataframe['price_change'].replace([np.inf, -np.inf], 0.0)
        
        # Calculate accumulation/distribution scores
        dataframe = self._calculate_accumulation_scores(dataframe)
        
        # Calculate volume spike patterns
        dataframe = self._calculate_volume_spikes(dataframe)
        
        return dataframe
    
    def _calculate_accumulation_scores(self, dataframe: DataFrame) -> DataFrame:
        """Calculate accumulation/distribution scores exactly as try1 bot"""
        
        # Price position in candle (for current candle)
        candle_range = dataframe['high'] - dataframe['low']
        
        # Long accumulation score
        dataframe['accumulation_long'] = 0.0
        
        # Check recent 3 candles for volume-price relationship
        for i in range(1, 4):
            candle_volume_ratio = dataframe['volume_ratio'].shift(i)
            candle_change = (dataframe['close'].shift(i) - dataframe['open'].shift(i)) / dataframe['open'].shift(i)
            
            # For bullish signal, look for volume on up candles
            up_volume_score = np.where(
                (candle_change > 0) & (candle_volume_ratio > 1.0),
                0.3, 0.0
            )
            # Low volume on down moves is good
            down_low_volume_score = np.where(
                (candle_change < 0) & (candle_volume_ratio < 1.0),
                0.1, 0.0
            )
            
            dataframe['accumulation_long'] += up_volume_score + down_low_volume_score
        
        # Close near high is bullish
        close_position_long = np.where(
            candle_range > 0,
            (dataframe['close'] - dataframe['low']) / candle_range * 0.2,
            0.0
        )
        dataframe['accumulation_long'] += close_position_long
        dataframe['accumulation_long'] = np.minimum(dataframe['accumulation_long'], 1.0)
        
        # Short distribution score (inverse logic)
        dataframe['accumulation_short'] = 0.0
        
        for i in range(1, 4):
            candle_volume_ratio = dataframe['volume_ratio'].shift(i)
            candle_change = (dataframe['close'].shift(i) - dataframe['open'].shift(i)) / dataframe['open'].shift(i)
            
            # For bearish signal, look for volume on down candles
            down_volume_score = np.where(
                (candle_change < 0) & (candle_volume_ratio > 1.0),
                0.3, 0.0
            )
            # Low volume on up moves is good
            up_low_volume_score = np.where(
                (candle_change > 0) & (candle_volume_ratio < 1.0),
                0.1, 0.0
            )
            
            dataframe['accumulation_short'] += down_volume_score + up_low_volume_score
        
        # Close near low is bearish
        close_position_short = np.where(
            candle_range > 0,
            (dataframe['high'] - dataframe['close']) / candle_range * 0.2,
            0.0
        )
        dataframe['accumulation_short'] += close_position_short
        dataframe['accumulation_short'] = np.minimum(dataframe['accumulation_short'], 1.0)
        
        return dataframe
    
    def _calculate_volume_spikes(self, dataframe: DataFrame) -> DataFrame:
        """Calculate volume spike patterns exactly as try1 bot"""
        
        # Basic volume spike condition
        volume_spike = dataframe['volume_ratio'] >= self.volume_spike_threshold.value
        
        # Bullish volume spike
        dataframe['bullish_volume_spike'] = (
            volume_spike &
            # Positive price movement (or small negative acceptable)
            (dataframe['price_change'] >= -self.min_price_movement.value) &
            # Optional RSI filter (disabled by default)
            (
                (self.rsi_filter_enabled.value == 0) |
                (dataframe['rsi'] <= self.rsi_neutral_max.value)
            )
        )
        
        # Bearish volume spike
        dataframe['bearish_volume_spike'] = (
            volume_spike &
            # Negative price movement (or small positive acceptable)
            (dataframe['price_change'] <= self.min_price_movement.value) &
            # Optional RSI filter (disabled by default)
            (
                (self.rsi_filter_enabled.value == 0) |
                (dataframe['rsi'] >= self.rsi_neutral_min.value)
            )
        )
        
        # Calculate confidence scores exactly as try1
        dataframe['volume_bull_confidence'] = self._calculate_volume_confidence(dataframe, 'LONG')
        dataframe['volume_bear_confidence'] = self._calculate_volume_confidence(dataframe, 'SHORT')
        
        return dataframe
    
    def _calculate_volume_confidence(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Calculate volume confidence exactly as try1 bot"""
        confidence = pd.Series(0.0, index=dataframe.index)
        
        # Volume spike strength (0.4 weight)
        volume_score = np.minimum(dataframe['volume_ratio'] / self.volume_spike_threshold.value, 3.0) / 3.0
        # Fix NaN/inf values
        volume_score = np.where(np.isnan(volume_score) | np.isinf(volume_score), 0.0, volume_score)
        confidence += volume_score * 0.4
        
        # Price movement confirmation (0.3 weight)
        movement_score = np.minimum(np.abs(dataframe['price_change']) / self.min_price_movement.value, 2.0) / 2.0
        # Fix NaN/inf values
        movement_score = np.where(np.isnan(movement_score) | np.isinf(movement_score), 0.0, movement_score)
        confidence += movement_score * 0.3
        
        # Accumulation/Distribution pattern (0.3 weight)
        if direction == 'LONG':
            pattern_score = dataframe['accumulation_long']
        else:
            pattern_score = dataframe['accumulation_short']
        
        # Fix NaN/inf values
        pattern_score = np.where(np.isnan(pattern_score) | np.isinf(pattern_score), 0.0, pattern_score)
        confidence += pattern_score * 0.3
        
        # Final validation and cleanup
        confidence = np.where(np.isnan(confidence) | np.isinf(confidence), 0.0, confidence)
        return np.minimum(np.maximum(confidence, 0.0), 1.0)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions exactly as try1 bot"""
        
        # Long entry: bullish volume spike with confidence
        long_entry = (
            dataframe['bullish_volume_spike'] &
            (dataframe['volume_bull_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        # Short entry: bearish volume spike with confidence
        short_entry = (
            dataframe['bearish_volume_spike'] &
            (dataframe['volume_bear_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'exact_vol_bull_spike'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'exact_vol_bear_spike'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions exactly as try1 bot"""
        
        # Exit long on opposite volume spike
        exit_long = dataframe['bearish_volume_spike']
        
        # Exit short on opposite volume spike
        exit_short = dataframe['bullish_volume_spike']
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'exact_vol_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'exact_vol_exit'
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Dynamic stop loss exactly as try1 bot (1.5 ATR)"""
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        atr = current_candle['atr']
        
        # Calculate 1.5 ATR stop loss
        if trade.is_short:
            # For short trades, stop loss is above entry
            stop_distance = (1.5 * atr) / current_rate
            return stop_distance
        else:
            # For long trades, stop loss is below entry
            stop_distance = (1.5 * atr) / current_rate
            return -stop_distance
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit exactly as try1 bot (2.5 ATR target)"""
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        atr = current_candle['atr']
        
        # Calculate 2.5 ATR take profit
        entry_rate = trade.open_rate
        
        if trade.is_short:
            # For short trades, take profit below entry
            target_rate = entry_rate - (2.5 * atr)
            if current_rate <= target_rate:
                return "exact_25atr_target"
        else:
            # For long trades, take profit above entry
            target_rate = entry_rate + (2.5 * atr)
            if current_rate >= target_rate:
                return "exact_25atr_target"
        
        return None
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """Conservative leverage exactly as try1 bot"""
        return 1.0  # No leverage as in try1 bot