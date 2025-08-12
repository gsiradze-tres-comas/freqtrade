"""
Try1 Balanced Strategy - Sweet Spot Between Simple & Selective
Target: 5-15 trades per day (150-450 total for month)
Based on your exact profitable configuration with balanced selectivity
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional, Union
import logging
from datetime import datetime
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)

class Try1BalancedStrategy(IStrategy):
    """
    Balanced selectivity targeting 5-15 trades per day
    Using your exact profitable settings with smart filtering
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # Your exact profitable settings
    minimal_roi = {
        "0": 0.012,   # 1.2% take profit (your exact setting)
        "120": 0.008, # 0.8% after 2 hours
        "240": 0.004, # 0.4% after 4 hours
        "480": 0.002  # 0.2% after 8 hours
    }
    
    # Your exact stop loss
    stoploss = -0.020  # 2.0% stop loss
    
    # Simple trailing stop like your bot
    trailing_stop = True
    trailing_stop_positive = 0.005  # Start trailing at 0.5%
    trailing_stop_positive_offset = 0.008  # Trail by 0.8%
    trailing_only_offset_is_reached = True
    
    # No position adjustment
    position_adjustment_enable = False
    
    # Balanced parameters - not too tight, not too loose
    rsi_oversold = IntParameter(25, 30, default=28, space="buy", load=True)
    rsi_overbought = IntParameter(70, 75, default=72, space="sell", load=True)
    volume_threshold = DecimalParameter(1.8, 2.5, decimals=1, default=2.2, space="buy", load=True)
    momentum_threshold = DecimalParameter(0.005, 0.010, decimals=3, default=0.007, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Balanced indicators for quality signals"""
        
        # EMAs
        dataframe['ema_10'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI with slope
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(1)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Momentum
        dataframe['momentum_5'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_10'] = dataframe['close'].pct_change(periods=10)
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # ATR for volatility filtering
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # Candle analysis
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.001)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        
        # Previous candle
        dataframe['prev_body_size'] = dataframe['body_size'].shift(1)
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        
        # Support/Resistance
        dataframe['resistance'] = dataframe['high'].rolling(window=50).max()
        dataframe['support'] = dataframe['low'].rolling(window=50).min()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Balanced entry conditions - quality but not impossible"""
        
        # LONG: Multiple good conditions (not perfect storm)
        long_conditions = []
        
        # Condition 1: RSI oversold bounce with volume
        long_conditions.append(
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['rsi_slope'] > 1) &  # RSI turning up
            (dataframe['volume_ratio'] > self.volume_threshold.value)
        )
        
        # Condition 2: EMA crossover with momentum
        long_conditions.append(
            (dataframe['ema_10'] > dataframe['ema_50']) &
            (dataframe['ema_10'].shift(1) <= dataframe['ema_50'].shift(1)) &
            (dataframe['momentum_10'] > self.momentum_threshold.value) &
            (dataframe['volume_ratio'] > 1.5)
        )
        
        # Condition 3: Strong bullish engulfing
        long_conditions.append(
            (dataframe['green_candle'] == 1) &
            (dataframe['prev_red'] == 1) &
            (dataframe['body_size'] > dataframe['prev_body_size'] * 1.3) &
            (dataframe['body_ratio'] > 0.5) &
            (dataframe['volume_ratio'] > 2.0)
        )
        
        # Condition 4: BB breakout with momentum
        long_conditions.append(
            (dataframe['close'] > dataframe['bb_upper']) &
            (dataframe['bb_width'] > 0.015) &
            (dataframe['momentum_5'] > 0.005) &
            (dataframe['volume_ratio'] > 2.5)
        )
        
        # Condition 5: Support bounce with volume
        long_conditions.append(
            (dataframe['close'] <= dataframe['support'] * 1.002) &  # Near support
            (dataframe['close'] > dataframe['support'] * 0.998) &   # But above it
            (dataframe['momentum_5'] > 0.003) &
            (dataframe['volume_ratio'] > 2.0) &
            (dataframe['rsi'] < 40)
        )
        
        # SHORT: Multiple good conditions
        short_conditions = []
        
        # Condition 1: RSI overbought rejection with volume
        short_conditions.append(
            (dataframe['rsi'] > self.rsi_overbought.value) &
            (dataframe['rsi_slope'] < -1) &  # RSI turning down
            (dataframe['volume_ratio'] > self.volume_threshold.value)
        )
        
        # Condition 2: EMA cross down with momentum
        short_conditions.append(
            (dataframe['ema_10'] < dataframe['ema_50']) &
            (dataframe['ema_10'].shift(1) >= dataframe['ema_50'].shift(1)) &
            (dataframe['momentum_10'] < -self.momentum_threshold.value) &
            (dataframe['volume_ratio'] > 1.5)
        )
        
        # Condition 3: Strong bearish engulfing
        short_conditions.append(
            (dataframe['red_candle'] == 1) &
            (dataframe['prev_green'] == 1) &
            (dataframe['body_size'] > dataframe['prev_body_size'] * 1.3) &
            (dataframe['body_ratio'] > 0.5) &
            (dataframe['volume_ratio'] > 2.0)
        )
        
        # Condition 4: BB breakdown with momentum
        short_conditions.append(
            (dataframe['close'] < dataframe['bb_lower']) &
            (dataframe['bb_width'] > 0.015) &
            (dataframe['momentum_5'] < -0.005) &
            (dataframe['volume_ratio'] > 2.5)
        )
        
        # Condition 5: Resistance rejection with volume
        short_conditions.append(
            (dataframe['close'] >= dataframe['resistance'] * 0.998) &  # Near resistance
            (dataframe['close'] < dataframe['resistance'] * 1.002) &   # But below it
            (dataframe['momentum_5'] < -0.003) &
            (dataframe['volume_ratio'] > 2.0) &
            (dataframe['rsi'] > 60)
        )
        
        # Combine conditions with OR logic (any condition can trigger)
        long_entry = (
            (long_conditions[0] | long_conditions[1] | long_conditions[2] | 
             long_conditions[3] | long_conditions[4]) &
            (dataframe['atr_ratio'] > 0.002) &  # Minimum volatility
            (dataframe['volume'] > 0)
        )
        
        short_entry = (
            (short_conditions[0] | short_conditions[1] | short_conditions[2] | 
             short_conditions[3] | short_conditions[4]) &
            (dataframe['atr_ratio'] > 0.002) &  # Minimum volatility
            (dataframe['volume'] > 0)
        )
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'balanced_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'balanced_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Let ROI, SL, and trailing stop handle exits"""
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        6% position size (your exact profitable setting)
        """
        total_balance = self.wallets.get_total_stake_amount()
        
        # Your exact 6% position size
        position_size = total_balance * 0.06
        
        # Ensure within limits
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size