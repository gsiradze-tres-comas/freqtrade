"""
EXACT RSI Bounce Strategy from try1 bot
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

class ExactRSIBounceStrategy(IStrategy):
    """
    RSI Bounce Strategy generates signals when RSI bounces from oversold/overbought levels.
    EXACT copy from try1 bot with parameters that achieved 2% average wins.
    
    Parameters copied exactly:
    - rsi_oversold = 35 (higher than typical 30)
    - rsi_overbought = 65 (lower than typical 70)
    - rsi_bounce_threshold = 3 (minimum RSI move for bounce)
    - min_volume_ratio = 0.8 (very low volume requirement)
    - price_confirmation = 0.001 (0.1% price move)
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
    rsi_oversold = IntParameter(35, 35, default=35, space="buy", load=True)
    rsi_overbought = IntParameter(65, 65, default=65, space="buy", load=True) 
    rsi_bounce_threshold = IntParameter(3, 3, default=3, space="buy", load=True)
    min_volume_ratio = DecimalParameter(0.8, 0.8, decimals=1, default=0.8, space="buy", load=True)
    price_confirmation = DecimalParameter(0.001, 0.001, decimals=3, default=0.001, space="buy", load=True)
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators exactly as in try1 bot"""
        
        # RSI for bounce detection
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # ATR for stop loss and take profit
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # RSI bounce calculations
        dataframe['rsi_prev'] = dataframe['rsi'].shift(1)
        dataframe['rsi_bounce'] = dataframe['rsi'] - dataframe['rsi_prev']
        
        # Price change confirmation
        dataframe['price_change'] = (dataframe['close'] - dataframe['close'].shift(1)) / dataframe['close'].shift(1)
        
        # Calculate RSI bounce patterns
        dataframe = self._calculate_rsi_bounces(dataframe)
        
        return dataframe
    
    def _calculate_rsi_bounces(self, dataframe: DataFrame) -> DataFrame:
        """Calculate RSI bounce patterns exactly as in try1 bot"""
        
        # Bullish RSI bounce (from oversold)
        dataframe['bullish_rsi_bounce'] = (
            # Previous RSI was oversold or close to it (with buffer)
            (dataframe['rsi_prev'] <= (self.rsi_oversold.value + 5)) &
            # RSI is bouncing up
            (dataframe['rsi_bounce'] >= self.rsi_bounce_threshold.value) &
            # Price confirmation (allow small negative moves)
            (dataframe['price_change'] >= -self.price_confirmation.value) &
            # Volume confirmation (very relaxed)
            (dataframe['volume_ratio'] >= self.min_volume_ratio.value)
        )
        
        # Bearish RSI bounce (from overbought)  
        dataframe['bearish_rsi_bounce'] = (
            # Previous RSI was overbought or close to it (with buffer)
            (dataframe['rsi_prev'] >= (self.rsi_overbought.value - 5)) &
            # RSI is bouncing down (positive when RSI falls)
            (dataframe['rsi_bounce'] <= -self.rsi_bounce_threshold.value) &
            # Price confirmation (allow small positive moves)
            (dataframe['price_change'] <= self.price_confirmation.value) &
            # Volume confirmation (very relaxed)
            (dataframe['volume_ratio'] >= self.min_volume_ratio.value)
        )
        
        # Calculate confidence scores exactly as try1
        dataframe['rsi_bull_confidence'] = self._calculate_bull_confidence(dataframe)
        dataframe['rsi_bear_confidence'] = self._calculate_bear_confidence(dataframe)
        
        return dataframe
    
    def _calculate_bull_confidence(self, dataframe: DataFrame) -> pd.Series:
        """Calculate bullish confidence exactly as try1 bot"""
        confidence = pd.Series(0.0, index=dataframe.index)
        
        # RSI extreme level strength (0.4 weight)
        extreme_score = np.maximum(0, (self.rsi_oversold.value + 10 - dataframe['rsi_prev']) / 20)
        confidence += np.minimum(extreme_score, 1.0) * 0.4
        
        # Bounce strength (0.3 weight)
        bounce_score = np.minimum(dataframe['rsi_bounce'] / (self.rsi_bounce_threshold.value * 3), 1.0)
        confidence += bounce_score * 0.3
        
        # Volume confirmation (0.2 weight)
        volume_score = np.minimum(dataframe['volume_ratio'] / self.min_volume_ratio.value, 2.0) / 2.0
        confidence += volume_score * 0.2
        
        # Price confirmation (0.1 weight)
        price_score = np.minimum(np.abs(dataframe['price_change']) / self.price_confirmation.value, 2.0) / 2.0
        confidence += price_score * 0.1
        
        return np.minimum(confidence, 1.0)
    
    def _calculate_bear_confidence(self, dataframe: DataFrame) -> pd.Series:
        """Calculate bearish confidence exactly as try1 bot"""
        confidence = pd.Series(0.0, index=dataframe.index)
        
        # RSI extreme level strength (0.4 weight) 
        extreme_score = np.maximum(0, (dataframe['rsi_prev'] - (self.rsi_overbought.value - 10)) / 20)
        confidence += np.minimum(extreme_score, 1.0) * 0.4
        
        # Bounce strength (0.3 weight)
        bounce_score = np.minimum(np.abs(dataframe['rsi_bounce']) / (self.rsi_bounce_threshold.value * 3), 1.0)
        confidence += bounce_score * 0.3
        
        # Volume confirmation (0.2 weight)
        volume_score = np.minimum(dataframe['volume_ratio'] / self.min_volume_ratio.value, 2.0) / 2.0
        confidence += volume_score * 0.2
        
        # Price confirmation (0.1 weight)
        price_score = np.minimum(np.abs(dataframe['price_change']) / self.price_confirmation.value, 2.0) / 2.0
        confidence += price_score * 0.1
        
        return np.minimum(confidence, 1.0)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions exactly as try1 bot"""
        
        # Long entry: bullish RSI bounce with confidence
        long_entry = (
            dataframe['bullish_rsi_bounce'] &
            (dataframe['rsi_bull_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        # Short entry: bearish RSI bounce with confidence
        short_entry = (
            dataframe['bearish_rsi_bounce'] &
            (dataframe['rsi_bear_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'exact_rsi_bull_bounce'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'exact_rsi_bear_bounce'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions exactly as try1 bot"""
        
        # Exit long on opposite RSI bounce or extreme levels
        exit_long = (
            dataframe['bearish_rsi_bounce'] |
            (dataframe['rsi'] >= 80)  # Extreme overbought
        )
        
        # Exit short on opposite RSI bounce or extreme levels
        exit_short = (
            dataframe['bullish_rsi_bounce'] |
            (dataframe['rsi'] <= 20)  # Extreme oversold
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'exact_rsi_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'exact_rsi_exit'
        
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