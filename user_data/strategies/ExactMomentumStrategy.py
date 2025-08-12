"""
EXACT Momentum Strategy from try1 bot
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

class ExactMomentumStrategy(IStrategy):
    """
    Simple momentum strategy that generates signals based on price movement and RSI conditions.
    EXACT copy from try1 bot with parameters that achieved 2% average wins.
    
    Parameters copied exactly:
    - price_change_threshold = 0.002 (0.2% price change)
    - rsi_oversold = 30
    - rsi_overbought = 70
    - volume_threshold = 1.2 (1.2x average volume)
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
    price_change_threshold = DecimalParameter(0.002, 0.002, decimals=3, default=0.002, space="buy", load=True)
    rsi_oversold = IntParameter(30, 30, default=30, space="buy", load=True)
    rsi_overbought = IntParameter(70, 70, default=70, space="buy", load=True)
    volume_threshold = DecimalParameter(1.2, 1.2, decimals=1, default=1.2, space="buy", load=True)
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators exactly as in try1 bot"""
        
        # RSI for momentum confirmation
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # EMA for trend context
        dataframe['ema'] = ta.EMA(dataframe, timeperiod=20)
        
        # ATR for stop loss and take profit
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Price change calculation
        dataframe['price_change'] = (dataframe['close'] - dataframe['close'].shift(1)) / dataframe['close'].shift(1)
        
        # Calculate momentum patterns
        dataframe = self._calculate_momentum_signals(dataframe)
        
        return dataframe
    
    def _calculate_momentum_signals(self, dataframe: DataFrame) -> DataFrame:
        """Calculate momentum signals exactly as in try1 bot"""
        
        # Bullish momentum
        dataframe['bullish_momentum'] = (
            # Strong positive price movement
            (dataframe['price_change'] >= self.price_change_threshold.value) &
            # RSI not overbought (room to move up)
            (dataframe['rsi'] <= self.rsi_overbought.value) &
            # Above average volume
            (dataframe['volume_ratio'] >= self.volume_threshold.value)
        )
        
        # Bearish momentum
        dataframe['bearish_momentum'] = (
            # Strong negative price movement
            (dataframe['price_change'] <= -self.price_change_threshold.value) &
            # RSI not oversold (room to move down)
            (dataframe['rsi'] >= self.rsi_oversold.value) &
            # Above average volume
            (dataframe['volume_ratio'] >= self.volume_threshold.value)
        )
        
        # Calculate confidence scores exactly as try1
        dataframe['momentum_bull_confidence'] = self._calculate_momentum_confidence(dataframe, 'LONG')
        dataframe['momentum_bear_confidence'] = self._calculate_momentum_confidence(dataframe, 'SHORT')
        
        return dataframe
    
    def _calculate_momentum_confidence(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Calculate momentum confidence exactly as try1 bot"""
        confidence = pd.Series(0.0, index=dataframe.index)
        
        # Price movement strength (0.3 weight)
        movement_strength = np.minimum(np.abs(dataframe['price_change']) / self.price_change_threshold.value, 3.0) / 3.0
        confidence += movement_strength * 0.3
        
        # Volume confirmation (0.3 weight)
        volume_strength = np.minimum(dataframe['volume_ratio'] / self.volume_threshold.value, 2.0) / 2.0
        confidence += volume_strength * 0.3
        
        # RSI positioning (0.4 weight)
        if direction == 'LONG':
            # For long signals, prefer lower RSI (more room to go up)
            rsi_score = np.maximum(0, (self.rsi_overbought.value - dataframe['rsi']) / (self.rsi_overbought.value - self.rsi_oversold.value))
        else:  # SHORT
            # For short signals, prefer higher RSI (more room to go down)
            rsi_score = np.maximum(0, (dataframe['rsi'] - self.rsi_oversold.value) / (self.rsi_overbought.value - self.rsi_oversold.value))
        
        confidence += rsi_score * 0.4
        
        return np.minimum(confidence, 1.0)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions exactly as try1 bot"""
        
        # Long entry: bullish momentum with confidence
        long_entry = (
            dataframe['bullish_momentum'] &
            (dataframe['momentum_bull_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        # Short entry: bearish momentum with confidence
        short_entry = (
            dataframe['bearish_momentum'] &
            (dataframe['momentum_bear_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'exact_bull_momentum'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'exact_bear_momentum'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions exactly as try1 bot"""
        
        # Exit long on opposite momentum or extreme RSI
        exit_long = (
            dataframe['bearish_momentum'] |
            (dataframe['rsi'] >= 80)  # Extreme overbought
        )
        
        # Exit short on opposite momentum or extreme RSI
        exit_short = (
            dataframe['bullish_momentum'] |
            (dataframe['rsi'] <= 20)  # Extreme oversold
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'exact_momentum_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'exact_momentum_exit'
        
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