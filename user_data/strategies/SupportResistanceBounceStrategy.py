"""
Support/Resistance Bounce Strategy
Auto-detects key S/R levels and trades bounces with tight stops
Target: 80%+ win rate on quality setups
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class SupportResistanceBounceStrategy(IStrategy):
    """
    High win rate S/R bounce trading
    """
    
    INTERFACE_VERSION = 3
    timeframe = '15m'  # 15m for cleaner S/R levels
    can_short = True
    
    # Conservative targets for high win rate
    minimal_roi = {
        "0": 0.02,   # 2% target
        "30": 0.015, # 1.5% after 30 minutes
        "60": 0.01,  # 1% after 1 hour
        "120": 0.005, # 0.5% after 2 hours
        "240": 0.0   # Break even after 4 hours
    }
    
    stoploss = -0.01  # Very tight 1% stop loss
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.008
    trailing_only_offset_is_reached = True
    
    # Strategy parameters
    lookback_period = IntParameter(20, 100, default=50, space="buy", load=True)
    min_touches = IntParameter(2, 5, default=3, space="buy", load=True)
    level_tolerance = DecimalParameter(0.001, 0.005, decimals=3, default=0.002, space="buy", load=True)
    bounce_threshold = DecimalParameter(0.001, 0.005, decimals=3, default=0.003, space="buy", load=True)
    volume_confirm = DecimalParameter(1.2, 2.0, decimals=1, default=1.5, space="buy", load=True)
    
    def find_support_resistance_levels(self, dataframe: DataFrame) -> DataFrame:
        """Identify key support and resistance levels"""
        
        lookback = self.lookback_period.value
        tolerance = self.level_tolerance.value
        
        # Find local highs and lows
        dataframe['pivot_high'] = dataframe['high'].rolling(window=5, center=True).max() == dataframe['high']
        dataframe['pivot_low'] = dataframe['low'].rolling(window=5, center=True).min() == dataframe['low']
        
        # Initialize level columns
        dataframe['resistance_1'] = np.nan
        dataframe['resistance_2'] = np.nan
        dataframe['support_1'] = np.nan
        dataframe['support_2'] = np.nan
        dataframe['resistance_strength_1'] = 0
        dataframe['resistance_strength_2'] = 0
        dataframe['support_strength_1'] = 0
        dataframe['support_strength_2'] = 0
        
        # For each candle, find S/R levels
        for i in range(lookback, len(dataframe)):
            # Get recent pivots
            recent_highs = dataframe.loc[i-lookback:i][dataframe['pivot_high']]['high'].values
            recent_lows = dataframe.loc[i-lookback:i][dataframe['pivot_low']]['low'].values
            
            if len(recent_highs) > 0 and len(recent_lows) > 0:
                current_price = dataframe.loc[i, 'close']
                
                # Find resistance levels (above current price)
                resistances = []
                for high in recent_highs:
                    if high > current_price * (1 + tolerance):
                        # Count touches
                        touches = sum(abs(dataframe.loc[i-lookback:i, 'high'] - high) / high < tolerance)
                        if touches >= self.min_touches.value:
                            resistances.append((high, touches))
                
                # Find support levels (below current price)
                supports = []
                for low in recent_lows:
                    if low < current_price * (1 - tolerance):
                        # Count touches
                        touches = sum(abs(dataframe.loc[i-lookback:i, 'low'] - low) / low < tolerance)
                        if touches >= self.min_touches.value:
                            supports.append((low, touches))
                
                # Sort by strength (number of touches) and proximity
                if resistances:
                    resistances.sort(key=lambda x: (-x[1], x[0]))  # Sort by touches desc, then price asc
                    dataframe.loc[i, 'resistance_1'] = resistances[0][0]
                    dataframe.loc[i, 'resistance_strength_1'] = resistances[0][1]
                    if len(resistances) > 1:
                        dataframe.loc[i, 'resistance_2'] = resistances[1][0]
                        dataframe.loc[i, 'resistance_strength_2'] = resistances[1][1]
                
                if supports:
                    supports.sort(key=lambda x: (-x[1], -x[0]))  # Sort by touches desc, then price desc
                    dataframe.loc[i, 'support_1'] = supports[0][0]
                    dataframe.loc[i, 'support_strength_1'] = supports[0][1]
                    if len(supports) > 1:
                        dataframe.loc[i, 'support_2'] = supports[1][0]
                        dataframe.loc[i, 'support_strength_2'] = supports[1][1]
        
        # Forward fill the levels
        dataframe['resistance_1'].fillna(method='ffill', inplace=True)
        dataframe['resistance_2'].fillna(method='ffill', inplace=True)
        dataframe['support_1'].fillna(method='ffill', inplace=True)
        dataframe['support_2'].fillna(method='ffill', inplace=True)
        
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Calculate S/R levels and bounce indicators"""
        
        # Find S/R levels
        dataframe = self.find_support_resistance_levels(dataframe)
        
        # Distance to levels
        dataframe['dist_to_support_1'] = (dataframe['close'] - dataframe['support_1']) / dataframe['close']
        dataframe['dist_to_resistance_1'] = (dataframe['resistance_1'] - dataframe['close']) / dataframe['close']
        
        # RSI for oversold/overbought
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        
        # Price action patterns
        dataframe['hammer'] = (
            (dataframe['close'] > dataframe['open']) &
            ((dataframe['high'] - dataframe['close']) < (dataframe['close'] - dataframe['open']) * 0.3) &
            ((dataframe['open'] - dataframe['low']) > (dataframe['close'] - dataframe['open']) * 2)
        ).astype(int)
        
        dataframe['shooting_star'] = (
            (dataframe['close'] < dataframe['open']) &
            ((dataframe['close'] - dataframe['low']) < (dataframe['open'] - dataframe['close']) * 0.3) &
            ((dataframe['high'] - dataframe['open']) > (dataframe['open'] - dataframe['close']) * 2)
        ).astype(int)
        
        # Momentum
        dataframe['momentum'] = dataframe['close'].pct_change(periods=5)
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_percent'] = dataframe['atr'] / dataframe['close']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry on bounce from S/R levels"""
        
        bounce_threshold = self.bounce_threshold.value
        
        # Long entry - bounce from support
        long_entry = (
            # Near support level
            (dataframe['dist_to_support_1'] < bounce_threshold) &
            (dataframe['dist_to_support_1'] > -bounce_threshold/2) &
            # Oversold
            (dataframe['rsi'] < 40) &
            # Volume confirmation
            (dataframe['volume'] > dataframe['volume_mean'] * self.volume_confirm.value) &
            # Bullish candle pattern or positive momentum
            ((dataframe['hammer'] == 1) | (dataframe['momentum'] > 0)) &
            # Support strength
            (dataframe['support_strength_1'] >= self.min_touches.value + 1) &
            # Not too volatile
            (dataframe['atr_percent'] < 0.02)
        )
        
        # Short entry - bounce from resistance
        short_entry = (
            # Near resistance level
            (dataframe['dist_to_resistance_1'] < bounce_threshold) &
            (dataframe['dist_to_resistance_1'] > -bounce_threshold/2) &
            # Overbought
            (dataframe['rsi'] > 60) &
            # Volume confirmation
            (dataframe['volume'] > dataframe['volume_mean'] * self.volume_confirm.value) &
            # Bearish candle pattern or negative momentum
            ((dataframe['shooting_star'] == 1) | (dataframe['momentum'] < 0)) &
            # Resistance strength
            (dataframe['resistance_strength_1'] >= self.min_touches.value + 1) &
            # Not too volatile
            (dataframe['atr_percent'] < 0.02)
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'support_bounce_' + dataframe['support_strength_1'].astype(str) + 'touches'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'resistance_bounce_' + dataframe['resistance_strength_1'].astype(str) + 'touches'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit on level break or target"""
        
        # Exit long
        exit_long = (
            # Support broken
            (dataframe['close'] < dataframe['support_1'] * 0.995) |
            # Near resistance
            (dataframe['dist_to_resistance_1'] < 0.005) |
            # Momentum loss
            (dataframe['momentum'] < -0.005)
        )
        
        # Exit short
        exit_short = (
            # Resistance broken
            (dataframe['close'] > dataframe['resistance_1'] * 1.005) |
            # Near support
            (dataframe['dist_to_support_1'] < 0.005) |
            # Momentum loss
            (dataframe['momentum'] > 0.005)
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'sr_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'sr_exit'
        
        return dataframe