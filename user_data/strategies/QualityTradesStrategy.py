"""
Quality Trades Strategy - Ultra-Selective Approach
Based on analysis of what actually works:
- ROI exits: +35.78% profit (738 trades, 100% win rate)
- Trailing stops: +16.52% profit (279 trades, 99.3% win rate)
- Target: 5-10 high-confidence trades per day maximum
- Remove ALL losing components
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, informative
from typing import Dict, Optional, Union
import logging
from datetime import datetime
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)

class QualityTradesStrategy(IStrategy):
    """
    Ultra-selective strategy focusing on quality over quantity
    Target: 2% daily returns with 5-10 trades per day maximum
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # Proven profitable ROI from successful trades
    minimal_roi = {
        "0": 0.025,    # 2.5% target (let winners run)
        "30": 0.018,   # 1.8% after 30 min
        "60": 0.012,   # 1.2% after 1 hour  
        "120": 0.008,  # 0.8% after 2 hours
        "240": 0.006,  # 0.6% after 4 hours (proven profitable level)
        "480": 0.004   # 0.4% after 8 hours
    }
    
    # Wider stop loss - crypto needs room to breathe
    stoploss = -0.035  # 3.5% stop loss (vs 2% that failed)
    
    # Proven profitable trailing stop settings
    trailing_stop = True
    trailing_stop_positive = 0.005   # Start trailing at 0.5%
    trailing_stop_positive_offset = 0.008  # Trail by 0.8%
    trailing_only_offset_is_reached = True
    
    # NO position adjustment - keep it simple
    position_adjustment_enable = False
    
    # Balanced parameters - selective but not impossibly restrictive
    volume_surge_min = DecimalParameter(1.5, 3.0, decimals=1, default=2.0, space="buy", load=True)
    momentum_threshold = DecimalParameter(0.003, 0.01, decimals=3, default=0.005, space="buy", load=True)
    rsi_extreme_oversold = IntParameter(25, 35, default=30, space="buy", load=True)
    rsi_extreme_overbought = IntParameter(65, 75, default=70, space="sell", load=True)
    
    # Confluence requirements - need some confirmations but not all
    min_confirmations = IntParameter(2, 4, default=3, space="buy", load=True)
    
    @informative('15m')
    def populate_indicators_15m(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """15m trend confirmation"""
        dataframe['ema_50_15m'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200_15m'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['rsi_15m'] = ta.RSI(dataframe, timeperiod=14)
        
        # Strong trend definition
        dataframe['strong_uptrend_15m'] = (
            (dataframe['close'] > dataframe['ema_50_15m']) &
            (dataframe['ema_50_15m'] > dataframe['ema_200_15m']) &
            (dataframe['close'] > dataframe['close'].shift(3))  # Higher highs
        ).astype(int)
        
        dataframe['strong_downtrend_15m'] = (
            (dataframe['close'] < dataframe['ema_50_15m']) &
            (dataframe['ema_50_15m'] < dataframe['ema_200_15m']) &
            (dataframe['close'] < dataframe['close'].shift(3))  # Lower lows
        ).astype(int)
        
        return dataframe
    
    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """1h macro trend"""
        # Simplified trend detection
        dataframe['ema_100_1h'] = ta.EMA(dataframe, timeperiod=100)
        dataframe['macro_uptrend_1h'] = (dataframe['close'] > dataframe['ema_100_1h']).astype(int)
        dataframe['macro_downtrend_1h'] = (dataframe['close'] < dataframe['ema_100_1h']).astype(int)
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Ultra-selective quality indicators only"""
        
        # Price action basics
        dataframe['hl2'] = (dataframe['high'] + dataframe['low']) / 2
        dataframe['hlc3'] = (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3
        
        # Volume analysis - key for quality trades
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_surge'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Momentum - only strong moves
        dataframe['momentum_5'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_10'] = dataframe['close'].pct_change(periods=10)
        
        # RSI for extremes only
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(1)
        
        # Bollinger Bands for squeeze/expansion
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # Support/Resistance levels
        dataframe['resistance'] = dataframe['high'].rolling(window=50).max()
        dataframe['support'] = dataframe['low'].rolling(window=50).min()
        
        # Price position relative to range
        dataframe['price_position'] = (dataframe['close'] - dataframe['support']) / (dataframe['resistance'] - dataframe['support'] + 0.0001)
        
        # Engulfing patterns (simplified but effective)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.0001)
        
        # Previous candle info
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_body_size'] = dataframe['body_size'].shift(1)
        
        # Get higher timeframe data
        dataframe['strong_uptrend_15m'] = dataframe['strong_uptrend_15m_15m']
        dataframe['strong_downtrend_15m'] = dataframe['strong_downtrend_15m_15m']
        dataframe['macro_uptrend_1h'] = dataframe['macro_uptrend_1h_1h']
        dataframe['macro_downtrend_1h'] = dataframe['macro_downtrend_1h_1h']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Ultra-selective entry conditions - quality over quantity"""
        
        # LONG CONDITIONS - Must have multiple confirmations
        long_confirmations = (
            # 1. Volume surge confirmation
            (dataframe['volume_surge'] >= self.volume_surge_min.value) +
            
            # 2. Strong momentum
            (dataframe['momentum_10'] > self.momentum_threshold.value) +
            
            # 3. RSI oversold bounce
            ((dataframe['rsi'] < self.rsi_extreme_oversold.value) & (dataframe['rsi_slope'] > 2)) +
            
            # 4. Bullish engulfing pattern
            ((dataframe['green_candle'] == 1) & (dataframe['prev_red'] == 1) & 
             (dataframe['body_size'] > dataframe['prev_body_size'] * 1.2) & 
             (dataframe['body_ratio'] > 0.6)) +
            
            # 5. Breaking above resistance with volume
            ((dataframe['close'] > dataframe['resistance']) & (dataframe['volume_surge'] > 2.5)) +
            
            # 6. BB expansion with breakout
            ((dataframe['close'] > dataframe['bb_upper']) & (dataframe['bb_width'] > 0.015)) +
            
            # 7. 15m trend alignment
            (dataframe['strong_uptrend_15m'] == 1) +
            
            # 8. 1h macro trend alignment
            (dataframe['macro_uptrend_1h'] == 1)
        )
        
        # SHORT CONDITIONS - Must have multiple confirmations
        short_confirmations = (
            # 1. Volume surge confirmation
            (dataframe['volume_surge'] >= self.volume_surge_min.value) +
            
            # 2. Strong down momentum
            (dataframe['momentum_10'] < -self.momentum_threshold.value) +
            
            # 3. RSI overbought rejection
            ((dataframe['rsi'] > self.rsi_extreme_overbought.value) & (dataframe['rsi_slope'] < -2)) +
            
            # 4. Bearish engulfing pattern
            ((dataframe['red_candle'] == 1) & (dataframe['prev_green'] == 1) & 
             (dataframe['body_size'] > dataframe['prev_body_size'] * 1.2) & 
             (dataframe['body_ratio'] > 0.6)) +
            
            # 5. Breaking below support with volume
            ((dataframe['close'] < dataframe['support']) & (dataframe['volume_surge'] > 2.5)) +
            
            # 6. BB expansion with breakdown
            ((dataframe['close'] < dataframe['bb_lower']) & (dataframe['bb_width'] > 0.015)) +
            
            # 7. 15m trend alignment
            (dataframe['strong_downtrend_15m'] == 1) +
            
            # 8. 1h macro trend alignment
            (dataframe['macro_downtrend_1h'] == 1)
        )
        
        # Ultra-selective entry - need MULTIPLE confirmations
        long_entry = (
            (long_confirmations >= self.min_confirmations.value) &
            (dataframe['atr_ratio'] > 0.002) &  # Minimum volatility
            (dataframe['volume'] > 0)
        )
        
        short_entry = (
            (short_confirmations >= self.min_confirmations.value) &
            (dataframe['atr_ratio'] > 0.002) &  # Minimum volatility
            (dataframe['volume'] > 0)
        )
        
        # Tag entries for analysis
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, f'quality_long_{int(long_confirmations.max())}conf')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, f'quality_short_{int(short_confirmations.max())}conf')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """NO custom exits - let ROI and trailing stops do their job"""
        
        # Only exit on extreme opposite signals (emergency exits)
        extreme_long_reversal = (
            (dataframe['rsi'] > 90) &
            (dataframe['momentum_5'] < -0.02) &
            (dataframe['volume_surge'] > 4.0)
        )
        
        extreme_short_reversal = (
            (dataframe['rsi'] < 10) &
            (dataframe['momentum_5'] > 0.02) &
            (dataframe['volume_surge'] > 4.0)
        )
        
        dataframe.loc[extreme_long_reversal, 'exit_long'] = 1
        dataframe.loc[extreme_short_reversal, 'exit_short'] = 1
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Conservative position sizing - 4% per trade max
        """
        total_balance = self.wallets.get_total_stake_amount()
        
        # Conservative sizing for high-quality trades
        position_size = total_balance * 0.04  # 4% per trade
        
        # Boost size slightly for higher confidence trades
        if entry_tag and ('5conf' in entry_tag or '6conf' in entry_tag):
            position_size *= 1.5  # 6% for highest confidence
        
        # Ensure within limits
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Only emergency exits - let the proven profitable systems (ROI/trailing) work
        """
        
        # Get current data
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return None
            
        current_candle = dataframe.iloc[-1]
        
        # Emergency exit on massive volume spike against position
        if current_profit < -0.01 and current_candle.get('volume_surge', 0) > 5.0:
            if trade.is_short and current_candle.get('momentum_5', 0) > 0.015:
                return "emergency_volume_spike"
            elif not trade.is_short and current_candle.get('momentum_5', 0) < -0.015:
                return "emergency_volume_spike"
        
        return None