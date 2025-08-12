"""
Enhanced Engulfing Pattern Strategy
Uses proven parameters and logic that achieved 2% average overnight wins
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ExactEngulfingStrategy(IStrategy):
    """
    Enhanced engulfing pattern strategy with volume and RSI confirmation.
    Uses proven parameters that achieved 2% average wins.
    
    Optimized parameters:
    - min_body_ratio = 0.6
    - volume_multiplier = 1.5 
    - rsi_min = 30, rsi_max = 70
    - ema_period = 20
    - 2 ATR stop loss, 3 ATR take profit (1:1.5 risk/reward)
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
    min_body_ratio = DecimalParameter(0.6, 0.6, decimals=1, default=0.6, space="buy", load=True)
    volume_multiplier = DecimalParameter(1.5, 1.5, decimals=1, default=1.5, space="buy", load=True)
    rsi_min = IntParameter(30, 30, default=30, space="buy", load=True)
    rsi_max = IntParameter(70, 70, default=70, space="buy", load=True)
    ema_period = IntParameter(20, 20, default=20, space="buy", load=True)
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators exactly as in try1 bot"""
        
        # EMA for trend context
        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.ema_period.value)
        
        # RSI for confirmation
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=10)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # ATR for stop loss and take profit
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Body size and ratio calculations (EXACT from try1)
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['candle_range'] = dataframe['high'] - dataframe['low']
        dataframe['body_ratio'] = np.where(
            dataframe['candle_range'] > 0,
            dataframe['body_size'] / dataframe['candle_range'],
            0.0
        )
        
        # Candle type identification (EXACT from try1)
        dataframe['is_bullish'] = dataframe['close'] > dataframe['open']
        dataframe['is_bearish'] = dataframe['close'] < dataframe['open']
        
        # Calculate engulfing patterns
        dataframe = self._calculate_engulfing_patterns(dataframe)
        
        return dataframe
    
    def _calculate_engulfing_patterns(self, dataframe: DataFrame) -> DataFrame:
        """Calculate engulfing patterns exactly as in try1 bot"""
        
        # Previous candle info
        prev_bearish = dataframe['is_bearish'].shift(1)
        prev_bullish = dataframe['is_bullish'].shift(1)
        prev_open = dataframe['open'].shift(1)
        prev_close = dataframe['close'].shift(1)
        
        # Current candle info
        curr_bullish = dataframe['is_bullish']
        curr_bearish = dataframe['is_bearish']
        curr_open = dataframe['open']
        curr_close = dataframe['close']
        
        # Bullish engulfing (EXACT logic from try1)
        dataframe['bullish_engulfing'] = (
            prev_bearish &  # Previous candle was bearish
            curr_bullish &  # Current candle is bullish
            (curr_open < prev_close) &  # Opens below previous close
            (curr_close > prev_open) &  # Closes above previous open
            (dataframe['body_ratio'] >= self.min_body_ratio.value) &  # Strong body
            (dataframe['volume_ratio'] >= self.volume_multiplier.value) &  # Volume confirmation
            (dataframe['rsi'] >= self.rsi_min.value) &  # RSI not too low
            (dataframe['rsi'] <= self.rsi_max.value)  # RSI not too high
        )
        
        # Bearish engulfing (EXACT logic from try1)
        dataframe['bearish_engulfing'] = (
            prev_bullish &  # Previous candle was bullish
            curr_bearish &  # Current candle is bearish
            (curr_open > prev_close) &  # Opens above previous close
            (curr_close < prev_open) &  # Closes below previous open
            (dataframe['body_ratio'] >= self.min_body_ratio.value) &  # Strong body
            (dataframe['volume_ratio'] >= self.volume_multiplier.value) &  # Volume confirmation
            (dataframe['rsi'] >= self.rsi_min.value) &  # RSI not too low
            (dataframe['rsi'] <= self.rsi_max.value)  # RSI not too high
        )
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions exactly as try1 bot"""
        
        # Long entry: bullish engulfing with trend confirmation
        long_entry = (
            dataframe['bullish_engulfing'] &
            (dataframe['close'] >= dataframe['ema'])  # Above EMA for trend confirmation
        )
        
        # Short entry: bearish engulfing with trend confirmation  
        short_entry = (
            dataframe['bearish_engulfing'] &
            (dataframe['close'] <= dataframe['ema'])  # Below EMA for trend confirmation
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'exact_bull_engulf'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'exact_bear_engulf'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions exactly as try1 bot"""
        
        # Exit long on bearish engulfing or trend change
        exit_long = (
            dataframe['bearish_engulfing'] |
            (dataframe['close'] < dataframe['ema'])  # Below EMA
        )
        
        # Exit short on bullish engulfing or trend change
        exit_short = (
            dataframe['bullish_engulfing'] |
            (dataframe['close'] > dataframe['ema'])  # Above EMA
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'exact_engulf_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'exact_engulf_exit'
        
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