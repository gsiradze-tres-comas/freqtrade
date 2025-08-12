"""
Try1 Simple Strategy - Dead Simple Replication
Based on your exact profitable configuration:
- 2% stop loss, 1.2% take profit
- 6% position size
- Simple entry conditions that actually work
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

class Try1SimpleStrategy(IStrategy):
    """
    Dead simple replication of your profitable try1 bot
    No complex consensus, no multi-timeframe - just what works
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # Your exact profitable settings
    minimal_roi = {
        "0": 0.012,   # 1.2% take profit (your exact setting)
        "60": 0.008,  # 0.8% after 1 hour
        "120": 0.004, # 0.4% after 2 hours
        "240": 0.002  # 0.2% after 4 hours
    }
    
    # Your exact stop loss
    stoploss = -0.020  # 2.0% stop loss
    
    # No trailing stop - keep it simple
    trailing_stop = False
    
    # No position adjustment
    position_adjustment_enable = False
    
    # Simple parameters
    rsi_oversold = IntParameter(20, 30, default=25, space="buy", load=True)
    rsi_overbought = IntParameter(70, 80, default=75, space="sell", load=True)
    ema_period = IntParameter(8, 15, default=10, space="buy", load=True)
    volume_threshold = DecimalParameter(1.2, 2.0, decimals=1, default=1.5, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Simple indicators only"""
        
        # Basic EMAs
        dataframe['ema_10'] = ta.EMA(dataframe, timeperiod=self.ema_period.value)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Simple momentum
        dataframe['price_change'] = dataframe['close'].pct_change(periods=5)
        
        # Candle patterns (simple)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        dataframe['prev_body'] = dataframe['body_size'].shift(1)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Simple entry conditions that work"""
        
        # LONG: Simple bullish conditions
        long_entry = (
            # 1. RSI oversold bounce
            ((dataframe['rsi'] < self.rsi_oversold.value) & (dataframe['rsi'] > dataframe['rsi'].shift(1))) |
            
            # 2. EMA crossover with volume
            ((dataframe['ema_10'] > dataframe['ema_50']) & 
             (dataframe['ema_10'].shift(1) <= dataframe['ema_50'].shift(1)) &
             (dataframe['volume_ratio'] > self.volume_threshold.value)) |
            
            # 3. Bullish engulfing with volume
            ((dataframe['green_candle'] == 1) & 
             (dataframe['prev_red'] == 1) & 
             (dataframe['body_size'] > dataframe['prev_body']) &
             (dataframe['volume_ratio'] > 1.3)) |
            
            # 4. Simple momentum with volume
            ((dataframe['price_change'] > 0.003) & 
             (dataframe['volume_ratio'] > self.volume_threshold.value))
        )
        
        # SHORT: Simple bearish conditions
        short_entry = (
            # 1. RSI overbought rejection
            ((dataframe['rsi'] > self.rsi_overbought.value) & (dataframe['rsi'] < dataframe['rsi'].shift(1))) |
            
            # 2. EMA cross down with volume
            ((dataframe['ema_10'] < dataframe['ema_50']) & 
             (dataframe['ema_10'].shift(1) >= dataframe['ema_50'].shift(1)) &
             (dataframe['volume_ratio'] > self.volume_threshold.value)) |
            
            # 3. Bearish engulfing with volume
            ((dataframe['red_candle'] == 1) & 
             (dataframe['prev_green'] == 1) & 
             (dataframe['body_size'] > dataframe['prev_body']) &
             (dataframe['volume_ratio'] > 1.3)) |
            
            # 4. Simple down momentum with volume
            ((dataframe['price_change'] < -0.003) & 
             (dataframe['volume_ratio'] > self.volume_threshold.value))
        )
        
        # Add basic filters
        long_entry = long_entry & (dataframe['volume'] > 0)
        short_entry = short_entry & (dataframe['volume'] > 0)
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'simple_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'simple_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Let ROI and stop loss handle exits"""
        
        # No custom exits - let the proven 1.2% TP and 2% SL work
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