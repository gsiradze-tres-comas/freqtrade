"""
EXACT Breakout Strategy from try1 bot
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

class ExactBreakoutStrategy(IStrategy):
    """
    Breakout Strategy generates signals when price breaks above/below recent levels.
    EXACT copy from try1 bot with parameters that achieved 2% average wins.
    
    Parameters copied exactly:
    - lookback_period = 10 (period to find highs/lows)
    - breakout_threshold = 0.002 (0.2% minimum breakout)
    - volume_confirmation = 1.1 (1.1x volume requirement)
    - retest_tolerance = 0.001 (0.1% retest tolerance)
    - min_consolidation = 3 (minimum candles for consolidation)
    - 2.0 ATR stop loss, 3.0 ATR take profit
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # EXACT parameters from successful try1 bot
    minimal_roi = {
        "0": 0.045,   # 4.5% (3.0 ATR target)
        "30": 0.030,  # 3.0% after 30 minutes
        "60": 0.015,  # 1.5% after 1 hour
        "120": 0.0    # Break even after 2 hours
    }
    
    stoploss = -0.030  # 3.0% (2.0 ATR stop loss)
    
    # EXACT try1 parameters - DO NOT CHANGE
    lookback_period = IntParameter(10, 10, default=10, space="buy", load=True)
    breakout_threshold = DecimalParameter(0.002, 0.002, decimals=3, default=0.002, space="buy", load=True)
    volume_confirmation = DecimalParameter(1.1, 1.1, decimals=1, default=1.1, space="buy", load=True)
    retest_tolerance = DecimalParameter(0.001, 0.001, decimals=3, default=0.001, space="buy", load=True)
    min_consolidation = IntParameter(3, 3, default=3, space="buy", load=True)
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators exactly as in try1 bot"""
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # ATR for stop loss and take profit
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Recent highs and lows for breakout detection
        dataframe['recent_high'] = dataframe['high'].rolling(window=self.lookback_period.value).max().shift(1)
        dataframe['recent_low'] = dataframe['low'].rolling(window=self.lookback_period.value).min().shift(1)
        
        # Calculate breakout percentages
        dataframe['breakout_high_pct'] = (dataframe['high'] - dataframe['recent_high']) / dataframe['recent_high']
        dataframe['breakout_low_pct'] = (dataframe['recent_low'] - dataframe['low']) / dataframe['recent_low']
        
        # Close strength within candle
        candle_range = dataframe['high'] - dataframe['low']
        dataframe['close_strength_high'] = np.where(
            candle_range > 0,
            (dataframe['close'] - dataframe['low']) / candle_range,
            1.0
        )
        dataframe['close_strength_low'] = np.where(
            candle_range > 0,
            (dataframe['high'] - dataframe['close']) / candle_range,
            1.0
        )
        
        # Calculate consolidation scores
        dataframe = self._calculate_consolidation_scores(dataframe)
        
        # Calculate breakout patterns
        dataframe = self._calculate_breakouts(dataframe)
        
        return dataframe
    
    def _calculate_consolidation_scores(self, dataframe: DataFrame) -> DataFrame:
        """Calculate consolidation quality exactly as try1 bot"""
        
        dataframe['consolidation_score'] = 0.0
        
        # For each row, look back at consolidation data
        for i in range(len(dataframe)):
            if i < self.lookback_period.value + 3:
                continue
                
            # Get consolidation period data (excluding current candle)
            start_idx = max(0, i - self.lookback_period.value - 2)
            end_idx = i - 1
            
            if end_idx <= start_idx:
                continue
                
            consolidation_data = dataframe.iloc[start_idx:end_idx]
            recent_high = dataframe.iloc[i]['recent_high']
            recent_low = dataframe.iloc[i]['recent_low']
            
            if pd.isna(recent_high) or pd.isna(recent_low) or recent_low == 0:
                continue
                
            score = 0.0
            
            # 1. Range tightness (0.4 weight)
            range_size = (recent_high - recent_low) / recent_low
            if range_size < 0.02:  # Less than 2% range
                score += 0.4
            elif range_size < 0.04:  # Less than 4% range
                score += 0.2
            
            # 2. Number of tests of levels (0.3 weight)
            high_tests = 0
            low_tests = 0
            
            high_tolerance = recent_high * (1 - self.retest_tolerance.value)
            low_tolerance = recent_low * (1 + self.retest_tolerance.value)
            
            for _, candle in consolidation_data.iterrows():
                if candle['high'] >= high_tolerance:
                    high_tests += 1
                if candle['low'] <= low_tolerance:
                    low_tests += 1
            
            if high_tests >= 2 and low_tests >= 2:
                score += 0.3
            elif high_tests >= 1 and low_tests >= 1:
                score += 0.15
            
            # 3. Time spent in consolidation (0.3 weight)
            if len(consolidation_data) >= self.min_consolidation.value:
                score += min(len(consolidation_data) / (self.lookback_period.value * 2), 1.0) * 0.3
            
            dataframe.iloc[i, dataframe.columns.get_loc('consolidation_score')] = min(score, 1.0)
        
        return dataframe
    
    def _calculate_breakouts(self, dataframe: DataFrame) -> DataFrame:
        """Calculate breakout patterns exactly as try1 bot"""
        
        # Bullish breakout (break above recent high)
        dataframe['bullish_breakout'] = (
            # Current high breaks above recent high
            (dataframe['breakout_high_pct'] >= self.breakout_threshold.value) &
            # Close should be near the high (strong breakout) 
            (dataframe['close_strength_high'] >= 0.7) &
            # Volume confirmation
            (dataframe['volume_ratio'] >= self.volume_confirmation.value)
        )
        
        # Bearish breakout (break below recent low)
        dataframe['bearish_breakout'] = (
            # Current low breaks below recent low
            (dataframe['breakout_low_pct'] >= self.breakout_threshold.value) &
            # Close should be near the low (strong breakout)
            (dataframe['close_strength_low'] >= 0.7) &
            # Volume confirmation
            (dataframe['volume_ratio'] >= self.volume_confirmation.value)
        )
        
        # Calculate confidence scores exactly as try1
        dataframe['breakout_bull_confidence'] = self._calculate_breakout_confidence(dataframe, 'LONG')
        dataframe['breakout_bear_confidence'] = self._calculate_breakout_confidence(dataframe, 'SHORT')
        
        return dataframe
    
    def _calculate_breakout_confidence(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Calculate breakout confidence exactly as try1 bot"""
        confidence = pd.Series(0.0, index=dataframe.index)
        
        if direction == 'LONG':
            # Breakout strength (0.3 weight)
            breakout_score = np.minimum(dataframe['breakout_high_pct'] / (self.breakout_threshold.value * 3), 1.0)
            confidence += breakout_score * 0.3
            
            # Close position strength (0.2 weight)
            confidence += dataframe['close_strength_high'] * 0.2
        else:
            # Breakout strength (0.3 weight)
            breakout_score = np.minimum(dataframe['breakout_low_pct'] / (self.breakout_threshold.value * 3), 1.0)
            confidence += breakout_score * 0.3
            
            # Close position strength (0.2 weight)
            confidence += dataframe['close_strength_low'] * 0.2
        
        # Volume confirmation (0.3 weight)
        volume_score = np.minimum(dataframe['volume_ratio'] / self.volume_confirmation.value, 2.0) / 2.0
        confidence += volume_score * 0.3
        
        # Previous consolidation quality (0.2 weight)
        confidence += dataframe['consolidation_score'] * 0.2
        
        return np.minimum(confidence, 1.0)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions exactly as try1 bot"""
        
        # Long entry: bullish breakout with confidence
        long_entry = (
            dataframe['bullish_breakout'] &
            (dataframe['breakout_bull_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        # Short entry: bearish breakout with confidence
        short_entry = (
            dataframe['bearish_breakout'] &
            (dataframe['breakout_bear_confidence'] >= 0.4)  # Minimum confidence from try1
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = 'exact_bull_breakout'
        
        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = 'exact_bear_breakout'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions exactly as try1 bot"""
        
        # Exit long on opposite breakout or return to range
        exit_long = (
            dataframe['bearish_breakout'] |
            (dataframe['close'] < dataframe['recent_high'])  # Back in range
        )
        
        # Exit short on opposite breakout or return to range
        exit_short = (
            dataframe['bullish_breakout'] |
            (dataframe['close'] > dataframe['recent_low'])  # Back in range
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'exact_breakout_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'exact_breakout_exit'
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Dynamic stop loss exactly as try1 bot (2.0 ATR)"""
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        atr = current_candle['atr']
        
        # For breakout strategy, also consider using support/resistance levels
        if trade.is_short:
            # For short trades, use recent high as reference or 2 ATR
            recent_high = current_candle['recent_high']
            entry_rate = trade.open_rate
            resistance_stop = (recent_high + atr - entry_rate) / entry_rate
            atr_stop = (2.0 * atr) / entry_rate
            return min(resistance_stop, atr_stop)
        else:
            # For long trades, use recent low as reference or 2 ATR
            recent_low = current_candle['recent_low']
            entry_rate = trade.open_rate
            support_stop = (entry_rate - recent_low + atr) / entry_rate
            atr_stop = (2.0 * atr) / entry_rate
            return -min(support_stop, atr_stop)
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit exactly as try1 bot (3.0 ATR target)"""
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        current_candle = dataframe.iloc[-1]
        atr = current_candle['atr']
        
        # Calculate 3.0 ATR take profit
        entry_rate = trade.open_rate
        
        if trade.is_short:
            # For short trades, take profit below entry
            target_rate = entry_rate - (3.0 * atr)
            if current_rate <= target_rate:
                return "exact_3atr_target"
        else:
            # For long trades, take profit above entry
            target_rate = entry_rate + (3.0 * atr)
            if current_rate >= target_rate:
                return "exact_3atr_target"
        
        return None
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """Conservative leverage exactly as try1 bot"""
        return 1.0  # No leverage as in try1 bot