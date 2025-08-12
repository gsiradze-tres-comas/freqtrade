"""
Try1 Ultra Selective Strategy - Match your profitable bot's frequency
Target: 5-10 trades per day maximum (not 142!)
Based on your exact settings but with extreme selectivity
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

class Try1UltraSelectiveStrategy(IStrategy):
    """
    Ultra-selective version matching your try1 bot's trading frequency
    Target: 5-10 trades per day, not 142!
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'  # Back to 5m like your bot
    can_short = True
    
    # Your exact profitable settings
    minimal_roi = {
        "0": 0.012,   # 1.2% take profit (your exact setting)
        "120": 0.008, # 0.8% after 2 hours (longer hold)
        "240": 0.004, # 0.4% after 4 hours
        "480": 0.002  # 0.2% after 8 hours
    }
    
    # Your exact stop loss
    stoploss = -0.020  # 2.0% stop loss
    
    # No trailing stop - let TP/SL work
    trailing_stop = False
    
    # No position adjustment
    position_adjustment_enable = False
    
    # MUCH MORE RESTRICTIVE PARAMETERS
    rsi_oversold = IntParameter(15, 25, default=20, space="buy", load=True)
    rsi_overbought = IntParameter(75, 85, default=80, space="sell", load=True)
    volume_threshold = DecimalParameter(2.0, 4.0, decimals=1, default=3.0, space="buy", load=True)
    momentum_threshold = DecimalParameter(0.008, 0.015, decimals=3, default=0.012, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Indicators for ultra-selective trading"""
        
        # EMAs
        dataframe['ema_10'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(2)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=50).mean()  # Longer period
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Strong momentum only
        dataframe['momentum_5'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_20'] = dataframe['close'].pct_change(periods=20)
        
        # Bollinger Bands for extremes
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.5, nbdevdn=2.5)  # Wider bands
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # Strong candle patterns only
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.001)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        
        # Previous candle analysis
        dataframe['prev_body_size'] = dataframe['body_size'].shift(1)
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        
        # Support/Resistance (longer periods)
        dataframe['resistance'] = dataframe['high'].rolling(window=100).max()
        dataframe['support'] = dataframe['low'].rolling(window=100).min()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """ULTRA-SELECTIVE entry conditions - only the best setups"""
        
        # LONG: Only perfect storm conditions
        perfect_long = (
            # 1. RSI extreme oversold with strong bounce
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['rsi_slope'] > 8) &  # Strong RSI bounce
            
            # 2. Massive volume spike
            (dataframe['volume_ratio'] > self.volume_threshold.value) &
            
            # 3. Strong momentum continuation
            (dataframe['momentum_20'] > self.momentum_threshold.value) &
            
            # 4. Price above key EMAs
            (dataframe['close'] > dataframe['ema_10']) &
            (dataframe['ema_10'] > dataframe['ema_50']) &
            
            # 5. Strong bullish engulfing with massive volume
            (dataframe['green_candle'] == 1) &
            (dataframe['prev_red'] == 1) &
            (dataframe['body_size'] > dataframe['prev_body_size'] * 2.0) &  # 2x previous body
            (dataframe['body_ratio'] > 0.7) &  # Large body ratio
            
            # 6. Breaking resistance with conviction
            (dataframe['close'] > dataframe['resistance']) &
            
            # 7. High volatility environment
            (dataframe['atr_ratio'] > 0.003)  # Minimum 0.3% ATR
        )
        
        # SHORT: Only perfect storm conditions
        perfect_short = (
            # 1. RSI extreme overbought with strong rejection
            (dataframe['rsi'] > self.rsi_overbought.value) &
            (dataframe['rsi_slope'] < -8) &  # Strong RSI rejection
            
            # 2. Massive volume spike
            (dataframe['volume_ratio'] > self.volume_threshold.value) &
            
            # 3. Strong down momentum
            (dataframe['momentum_20'] < -self.momentum_threshold.value) &
            
            # 4. Price below key EMAs
            (dataframe['close'] < dataframe['ema_10']) &
            (dataframe['ema_10'] < dataframe['ema_50']) &
            
            # 5. Strong bearish engulfing with massive volume
            (dataframe['red_candle'] == 1) &
            (dataframe['prev_green'] == 1) &
            (dataframe['body_size'] > dataframe['prev_body_size'] * 2.0) &  # 2x previous body
            (dataframe['body_ratio'] > 0.7) &  # Large body ratio
            
            # 6. Breaking support with conviction
            (dataframe['close'] < dataframe['support']) &
            
            # 7. High volatility environment
            (dataframe['atr_ratio'] > 0.003)  # Minimum 0.3% ATR
        )
        
        dataframe.loc[perfect_long, ['enter_long', 'enter_tag']] = (1, 'perfect_long')
        dataframe.loc[perfect_short, ['enter_short', 'enter_tag']] = (1, 'perfect_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Let 1.2% TP and 2% SL handle exits"""
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