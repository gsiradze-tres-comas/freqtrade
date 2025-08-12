"""
EXACT MA Crossover Strategy from try1 bot
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

class ExactMACrossoverStrategy(IStrategy):
    """
    Moving Average Crossover Strategy generates signals when fast EMA crosses slow EMA.
    EXACT copy from try1 bot with parameters that achieved 2% average wins.
    
    Parameters copied exactly:
    - fast_ema_period = 5 (very fast EMA)
    - slow_ema_period = 10 (moderate slow EMA)
    - min_separation = 0.0005 (0.05% minimum separation)
    - volume_threshold = 0.7 (very low volume requirement)
    - trend_confirmation = True (optional trend filter)
    - 2 ATR stop loss, 3 ATR take profit
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # EXACT parameters from successful try1 bot
    minimal_roi = {
        "0": 0.045,   # 4.5% (3 ATR target)
        "30": 0.030,  # 3.0% after 30 minutes
        "60": 0.015,  # 1.5% after 1 hour
        "120": 0.0    # Break even after 2 hours
    }
    
    stoploss = -0.030  # 3.0% (2 ATR stop loss)
    
    # EXACT try1 parameters - DO NOT CHANGE
    fast_ema_period = IntParameter(5, 5, default=5, space="buy", load=True)
    slow_ema_period = IntParameter(10, 10, default=10, space="buy", load=True)
    min_separation = DecimalParameter(0.0005, 0.0005, decimals=4, default=0.0005, space="buy", load=True)
    volume_threshold = DecimalParameter(0.7, 0.7, decimals=1, default=0.7, space="buy", load=True)
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators exactly as in try1 bot"""
        
        # Fast and slow EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.fast_ema_period.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.slow_ema_period.value)
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # ATR for stop loss and take profit
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Previous EMA values for crossover detection
        dataframe['ema_fast_prev'] = dataframe['ema_fast'].shift(1)
        dataframe['ema_slow_prev'] = dataframe['ema_slow'].shift(1)
        
        # EMA separation
        dataframe['ema_separation'] = abs(dataframe['ema_fast'] - dataframe['ema_slow']) / dataframe['ema_slow']
        
        # Trend calculation for confirmation (3 periods lookback)
        dataframe['fast_trend'] = (dataframe['ema_fast'] - dataframe['ema_fast'].shift(3)) / dataframe['ema_fast'].shift(3)
        dataframe['slow_trend'] = (dataframe['ema_slow'] - dataframe['ema_slow'].shift(3)) / dataframe['ema_slow'].shift(3)
        
        # Calculate crossover patterns
        dataframe = self._calculate_ma_crossovers(dataframe)
        
        return dataframe
    
    def _calculate_ma_crossovers(self, dataframe: DataFrame) -> DataFrame:
        """Calculate MA crossover patterns exactly as in try1 bot"""
        
        # Bullish crossover (fast crosses above slow)
        was_below = dataframe['ema_fast_prev'] <= dataframe['ema_slow_prev']
        is_above = dataframe['ema_fast'] > dataframe['ema_slow']
        
        dataframe['bullish_crossover'] = (
            was_below & is_above &  # Crossover occurred
            (dataframe['ema_separation'] >= self.min_separation.value) &  # Minimum separation
            (dataframe['volume_ratio'] >= self.volume_threshold.value) &  # Volume confirmation
            # Trend confirmation (very relaxed)
            ((dataframe['fast_trend'] >= -0.001) | (dataframe['slow_trend'] >= -0.001))
        )
        
        # Bearish crossover (fast crosses below slow)
        was_above = dataframe['ema_fast_prev'] >= dataframe['ema_slow_prev']
        is_below = dataframe['ema_fast'] < dataframe['ema_slow']
        
        dataframe['bearish_crossover'] = (
            was_above & is_below &  # Crossover occurred
            (dataframe['ema_separation'] >= self.min_separation.value) &  # Minimum separation
            (dataframe['volume_ratio'] >= self.volume_threshold.value) &  # Volume confirmation
            # Trend confirmation (very relaxed)
            ((dataframe['fast_trend'] <= 0.001) | (dataframe['slow_trend'] <= 0.001))
        )
        
        # Calculate confidence scores exactly as try1
        dataframe['ma_bull_confidence'] = self._calculate_crossover_confidence(dataframe, 'LONG')
        dataframe['ma_bear_confidence'] = self._calculate_crossover_confidence(dataframe, 'SHORT')
        
        return dataframe
    
    def _calculate_crossover_confidence(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Calculate crossover confidence exactly as try1 bot"""
        confidence = pd.Series(0.0, index=dataframe.index)
        
        # Separation strength (0.3 weight)
        separation_score = np.minimum(dataframe['ema_separation'] / (self.min_separation.value * 5), 1.0)
        confidence += separation_score * 0.3
        
        # Volume confirmation (0.2 weight)
        volume_score = np.minimum(dataframe['volume_ratio'] / self.volume_threshold.value, 2.0) / 2.0
        confidence += volume_score * 0.2
        
        # EMA trend alignment (0.3 weight)
        if direction == 'LONG':
            # Check if EMAs are generally trending up over 5 periods
            fast_trend_5 = (dataframe['ema_fast'] - dataframe['ema_fast'].shift(5)) / dataframe['ema_fast'].shift(5)
            slow_trend_5 = (dataframe['ema_slow'] - dataframe['ema_slow'].shift(5)) / dataframe['ema_slow'].shift(5)
        else:
            # Check if EMAs are generally trending down over 5 periods  
            fast_trend_5 = -(dataframe['ema_fast'] - dataframe['ema_fast'].shift(5)) / dataframe['ema_fast'].shift(5)
            slow_trend_5 = -(dataframe['ema_slow'] - dataframe['ema_slow'].shift(5)) / dataframe['ema_slow'].shift(5)
        
        trend_score = np.maximum(0, np.minimum((fast_trend_5 + slow_trend_5) / 0.01, 1.0))  # Normalize to 1% trend
        confidence += trend_score * 0.3
        
        # Price position relative to EMAs (0.2 weight)
        if direction == 'LONG':
            price_score = np.where(dataframe['close'] >= dataframe['ema_fast'], 1.0, 0.5)
        else:
            price_score = np.where(dataframe['close'] <= dataframe['ema_fast'], 1.0, 0.5)
        confidence += price_score * 0.2
        
        return np.minimum(confidence, 1.0)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions exactly as try1 bot"""
        
        # Long entry: bullish crossover with confidence
        long_entry = (
            dataframe['bullish_crossover'] &
            (dataframe['ma_bull_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        # Short entry: bearish crossover with confidence
        short_entry = (
            dataframe['bearish_crossover'] &
            (dataframe['ma_bear_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'exact_ma_bull_cross'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'exact_ma_bear_cross'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions exactly as try1 bot"""
        
        # Exit long on opposite crossover
        exit_long = dataframe['bearish_crossover']
        
        # Exit short on opposite crossover
        exit_short = dataframe['bullish_crossover']
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'exact_ma_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'exact_ma_exit'
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Dynamic stop loss exactly as try1 bot (2 ATR)"""
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        atr = current_candle['atr']
        
        # Calculate 2 ATR stop loss
        if trade.is_short:
            # For short trades, stop loss is above entry
            stop_distance = (2 * atr) / current_rate
            return stop_distance
        else:
            # For long trades, stop loss is below entry
            stop_distance = (2 * atr) / current_rate
            return -stop_distance
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit exactly as try1 bot (3 ATR target)"""
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        atr = current_candle['atr']
        
        # Calculate 3 ATR take profit
        entry_rate = trade.open_rate
        
        if trade.is_short:
            # For short trades, take profit below entry
            target_rate = entry_rate - (3 * atr)
            if current_rate <= target_rate:
                return "exact_3atr_target"
        else:
            # For long trades, take profit above entry
            target_rate = entry_rate + (3 * atr)
            if current_rate >= target_rate:
                return "exact_3atr_target"
        
        return None
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """Conservative leverage exactly as try1 bot"""
        return 1.0  # No leverage as in try1 bot