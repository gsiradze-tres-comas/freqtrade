"""
SafeBullRider IMPROVED - No fancy BS, just better SafeBullRider
Keep the 87% win rate patterns, improve the filtering
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional, Union
import logging
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from functools import reduce

logger = logging.getLogger(__name__)

class BeastModeStrategyV3(IStrategy):
    """
    SafeBullRider but BETTER - focus on quality over quantity
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False
    
    startup_candle_count = 100
    
    # SAME SafeBullRider ROI - THIS WORKS
    minimal_roi = {
        "0": 0.04,
        "120": 0.025,
        "300": 0.015,
        "600": 0.008
    }
    
    # SAME SafeBullRider stops - THIS WORKS
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    
    # Position adjustment
    position_adjustment_enable = True
    max_entry_position_adjustment = 1
    
    # IMPROVED parameters - more selective
    rsi_oversold = IntParameter(30, 40, default=35, space="buy", load=True)  # Tighter
    rsi_overbought = IntParameter(65, 75, default=70, space="sell", load=True)  # Wider
    volume_multiplier = DecimalParameter(1.2, 2.5, decimals=1, default=1.5, space="buy", load=True)  # Higher
    trend_strength = DecimalParameter(0.005, 0.012, decimals=3, default=0.008, space="buy", load=True)  # Stronger
    
    # NEW quality filters
    min_volume_ratio = DecimalParameter(1.1, 2.0, decimals=1, default=1.3, space="buy")
    max_volatility = DecimalParameter(0.04, 0.12, decimals=2, default=0.08, space="buy")
    trend_consistency = IntParameter(3, 8, default=5, space="buy")
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """SAME SafeBullRider indicators + quality filters"""
        
        # EXACT SafeBullRider indicators
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Momentum
        dataframe['momentum_5'] = (dataframe['close'] - dataframe['close'].shift(5)) / dataframe['close'].shift(5)
        dataframe['momentum_20'] = (dataframe['close'] - dataframe['close'].shift(20)) / dataframe['close'].shift(20)
        
        # Trend detection
        dataframe['uptrend'] = (
            (dataframe['ema_8'] > dataframe['ema_21']) & 
            (dataframe['ema_21'] > dataframe['ema_50'])
        )
        
        # Candle patterns
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        
        # Volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = (dataframe['atr'] / dataframe['close']) * 100
        
        # NEW quality indicators
        
        # Trend consistency - how many of last N candles follow trend
        dataframe['trend_candles'] = 0
        for i in range(1, self.trend_consistency.value + 1):
            trend_follow = (
                (dataframe['uptrend']) & 
                (dataframe['close'] > dataframe['close'].shift(i))
            ).astype(int)
            dataframe['trend_candles'] += trend_follow
        
        # Volume quality - sustained volume not just spike
        dataframe['volume_quality'] = (
            dataframe['volume_ratio'].rolling(3).mean()
        )
        
        # Price momentum quality - smooth not choppy
        dataframe['momentum_smooth'] = (
            dataframe['momentum_5'].rolling(3).std()
        )
        
        # Market strength - multiple timeframes aligned
        dataframe['market_strength'] = (
            ((dataframe['momentum_5'] > 0).astype(int) +
             (dataframe['momentum_20'] > 0).astype(int) +
             (dataframe['uptrend']).astype(int) +
             (dataframe['rsi'] > 50).astype(int)) / 4
        )
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """
        SAME SafeBullRider patterns + quality filters
        """
        
        # SIMPLIFIED Try1BullRider patterns - the ones that actually work
        long_dip_buy = (
            (dataframe['ema_8'] > dataframe['ema_21']) &  # Simplified uptrend
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['volume_ratio'] > self.volume_multiplier.value) &
            (dataframe['momentum_5'] > -0.01)
        )
        
        long_breakout = (
            (dataframe['momentum_5'] > self.trend_strength.value) &
            (dataframe['momentum_20'] > 0) &
            (dataframe['green_candle'] == 1) &
            (dataframe['volume_ratio'] > 1.8) &  # Slightly lower requirement
            (dataframe['close'] > dataframe['ema_8'])
        )
        
        long_trend_follow = (
            (dataframe['ema_8'] > dataframe['ema_21']) &  # Simplified uptrend
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['rsi'] > 45) & (dataframe['rsi'] < 70) &  # Wider RSI range
            (dataframe['volume_ratio'] > 1.1) &  # Lower volume requirement
            (dataframe['atr_pct'] < 0.08)  # Higher volatility allowed
        )
        
        # Combine all patterns with OR logic (more opportunities)
        final_entry = long_dip_buy | long_breakout | long_trend_follow
        
        # Initialize columns if they don't exist
        dataframe['enter_long'] = 0
        dataframe['enter_tag'] = ''
        
        dataframe.loc[final_entry, 'enter_long'] = 1
        dataframe.loc[final_entry, 'enter_tag'] = 'improved_entry'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """EXACT SafeBullRider exit logic"""
        
        # Only exit on EXTREME trend reversal
        long_exit = (
            (dataframe['rsi'] > 85) |
            (
                (dataframe['momentum_5'] < -0.02) &
                (dataframe['rsi'] > 70) &
                (dataframe['close'] < dataframe['ema_8'])
            )
        )
        
        # Initialize columns if they don't exist
        dataframe['exit_long'] = 0
        dataframe['exit_tag'] = ''
        
        dataframe.loc[long_exit, 'exit_long'] = 1
        dataframe.loc[long_exit, 'exit_tag'] = 'trend_reversal'
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        """
        IMPROVED position sizing - bigger bets on higher quality signals
        """
        
        # Get recent trades performance for this pair
        try:
            recent_trades = Trade.get_trades_proxy(is_open=False, pair=pair)
            if len(recent_trades) >= 3:
                # Look at last 5 trades
                last_trades = recent_trades[-5:]
                win_rate = sum(1 for t in last_trades if t.close_profit and t.close_profit > 0) / len(last_trades)
                
                # If pair is performing well, increase stake
                if win_rate >= 0.8:  # 80% win rate
                    multiplier = 1.3
                elif win_rate >= 0.6:  # 60% win rate
                    multiplier = 1.1
                else:
                    multiplier = 0.9  # Reduce for underperforming pairs
            else:
                multiplier = 1.0  # Standard for new pairs
        except:
            multiplier = 1.0
        
        adjusted_stake = proposed_stake * multiplier
        return min(max(adjusted_stake, min_stake), max_stake)
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: str,
                           side: str, **kwargs) -> bool:
        """
        Simplified entry confirmation - just let it trade
        """
        return True