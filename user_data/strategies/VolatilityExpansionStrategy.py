"""
Volatility Expansion Strategy - Quick Win Addition
Trades volatility breakouts after consolidation periods
Target: 2-3% moves on expansion
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class VolatilityExpansionStrategy(IStrategy):
    """
    Volatility expansion trading for quick 2-3% gains
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'  # 5m timeframe for volatility patterns
    can_short = True
    
    # Quick profit targets for volatility moves
    minimal_roi = {
        "0": 0.03,   # 3% target
        "10": 0.025, # 2.5% after 10 minutes
        "20": 0.02,  # 2% after 20 minutes
        "30": 0.015, # 1.5% after 30 minutes
        "60": 0.01,  # 1% after 1 hour
        "120": 0.0   # Break even after 2 hours
    }
    
    stoploss = -0.015  # Tight 1.5% stop loss
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True
    
    # Strategy parameters
    bb_period = IntParameter(15, 25, default=20, space="buy", load=True)
    bb_std = DecimalParameter(1.5, 2.5, decimals=1, default=2.0, space="buy", load=True)
    squeeze_threshold = DecimalParameter(0.001, 0.010, decimals=3, default=0.005, space="buy", load=True)
    volume_factor = DecimalParameter(1.5, 3.0, decimals=1, default=2.0, space="buy", load=True)
    keltner_mult = DecimalParameter(1.0, 2.0, decimals=1, default=1.5, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Calculate volatility indicators"""
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=self.bb_period.value, nbdevup=self.bb_std.value, nbdevdn=self.bb_std.value)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])
        
        # Keltner Channels (for squeeze detection)
        dataframe['kc_middle'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=10)
        dataframe['kc_upper'] = dataframe['kc_middle'] + (dataframe['atr'] * self.keltner_mult.value)
        dataframe['kc_lower'] = dataframe['kc_middle'] - (dataframe['atr'] * self.keltner_mult.value)
        
        # Squeeze indicator (BB inside KC)
        dataframe['squeeze'] = (
            (dataframe['bb_lower'] > dataframe['kc_lower']) & 
            (dataframe['bb_upper'] < dataframe['kc_upper'])
        ).astype(int)
        
        # Squeeze release (expansion)
        dataframe['squeeze_release'] = (
            (dataframe['squeeze'].shift(1) == 1) & 
            (dataframe['squeeze'] == 0)
        ).astype(int)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_spike'] = dataframe['volume'] > (dataframe['volume_mean'] * self.volume_factor.value)
        
        # Momentum oscillator for direction
        dataframe['mom'] = ta.MOM(dataframe, timeperiod=12)
        dataframe['mom_sma'] = ta.SMA(dataframe['mom'], timeperiod=5)
        
        # Price action
        dataframe['close_bb_dist'] = abs(dataframe['close'] - dataframe['bb_middle']) / dataframe['bb_middle']
        
        # Historical volatility
        dataframe['returns'] = dataframe['close'].pct_change()
        dataframe['hvol'] = dataframe['returns'].rolling(window=20).std() * np.sqrt(288)  # 5m bars per day
        dataframe['hvol_sma'] = dataframe['hvol'].rolling(window=10).mean()
        
        # Directional movement
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        plus_di = ta.PLUS_DI(dataframe, timeperiod=14)
        minus_di = ta.MINUS_DI(dataframe, timeperiod=14)
        dataframe['di_diff'] = plus_di - minus_di
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry on volatility expansion after squeeze"""
        
        # Bullish expansion
        long_entry = (
            # Squeeze release
            (dataframe['squeeze_release'] == 1) &
            # Bullish momentum
            (dataframe['mom'] > dataframe['mom_sma']) &
            (dataframe['di_diff'] > 0) &
            # Price breaking out
            (dataframe['close'] > dataframe['bb_upper'].shift(1)) &
            # Volume confirmation
            (dataframe['volume_spike'] == 1) &
            # Not overextended
            (dataframe['close_bb_dist'] < 0.03)
        )
        
        # Bearish expansion
        short_entry = (
            # Squeeze release
            (dataframe['squeeze_release'] == 1) &
            # Bearish momentum
            (dataframe['mom'] < dataframe['mom_sma']) &
            (dataframe['di_diff'] < 0) &
            # Price breaking down
            (dataframe['close'] < dataframe['bb_lower'].shift(1)) &
            # Volume confirmation
            (dataframe['volume_spike'] == 1) &
            # Not overextended
            (dataframe['close_bb_dist'] < 0.03)
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'vol_expansion_long'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'vol_expansion_short'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit on momentum exhaustion or band touch"""
        
        # Exit long
        exit_long = (
            # Momentum turning
            (dataframe['mom'] < dataframe['mom_sma']) |
            # Back inside bands
            (dataframe['close'] < dataframe['bb_middle']) |
            # New squeeze forming
            (dataframe['squeeze'] == 1)
        )
        
        # Exit short
        exit_short = (
            # Momentum turning
            (dataframe['mom'] > dataframe['mom_sma']) |
            # Back inside bands
            (dataframe['close'] > dataframe['bb_middle']) |
            # New squeeze forming
            (dataframe['squeeze'] == 1)
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'vol_exhaustion'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'vol_exhaustion'
        
        return dataframe