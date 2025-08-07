"""
Try1 Bull Rider Strategy - Actually Makes Money in Bull Markets
Problem: Previous strategy missed 24% bull run, only made 0.47 trades/day
Solution: Aggressive trend following that PARTICIPATES in bull markets
Target: 10-20 trades/day, 60%+ win rate, capture market moves
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

class Try1BullRiderStrategy(IStrategy):
    """
    Bull market strategy that actually makes money
    Simple, aggressive, trend-following approach
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False  # DISABLE SHORTS IN BULL MARKETS
    
    # WIDER ROI for bull market swings
    minimal_roi = {
        "0": 0.04,    # 4% target (capture bigger moves)
        "120": 0.025, # 2.5% after 2 hours
        "300": 0.015, # 1.5% after 5 hours
        "600": 0.008  # 0.8% after 10 hours
    }
    
    # WIDER stop loss for bull market volatility
    stoploss = -0.04  # 4% stop loss (less stop outs)
    
    # WIDER trailing stop for bull market swings
    trailing_stop = True
    trailing_stop_positive = 0.015   # Start at 1.5% (let profits run)
    trailing_stop_positive_offset = 0.02   # Trail by 2% (wider swings)
    trailing_only_offset_is_reached = True
    
    # Position adjustment for bull markets
    position_adjustment_enable = True
    max_entry_position_adjustment = 1  # Scale in once
    
    # NO COMPLEX CONSENSUS - SIMPLE PARAMETERS
    rsi_oversold = IntParameter(35, 45, default=40, space="buy", load=True)
    rsi_overbought = IntParameter(60, 70, default=65, space="sell", load=True)
    volume_multiplier = DecimalParameter(0.8, 1.5, decimals=1, default=1.2, space="buy", load=True)
    trend_strength = DecimalParameter(0.003, 0.008, decimals=3, default=0.005, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Simple, effective indicators - NO OVERENGINEERING"""
        
        # Basic EMAs for trend
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Price momentum
        dataframe['momentum_5'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_20'] = dataframe['close'].pct_change(periods=20)
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Trend detection (SIMPLE)
        dataframe['uptrend'] = (
            (dataframe['ema_8'] > dataframe['ema_21']) &
            (dataframe['ema_21'] > dataframe['ema_50']) &
            (dataframe['close'] > dataframe['ema_8'])
        )
        
        dataframe['downtrend'] = (
            (dataframe['ema_8'] < dataframe['ema_21']) &
            (dataframe['ema_21'] < dataframe['ema_50']) &
            (dataframe['close'] < dataframe['ema_8'])
        )
        
        # Candle patterns (basic)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """SIMPLE ENTRY CONDITIONS - NO COMPLEX FILTERING"""
        
        # LONG: Multiple simple conditions (OR logic for more trades)
        long_dip_buy = (
            (dataframe['uptrend']) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['volume_ratio'] > self.volume_multiplier.value)
        )
        
        long_breakout = (
            (dataframe['momentum_5'] > self.trend_strength.value) &
            (dataframe['green_candle'] == 1) &
            (dataframe['volume_ratio'] > 1.5) &
            (dataframe['close'] > dataframe['ema_8'])
        )
        
        long_trend_follow = (
            (dataframe['uptrend']) &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['rsi'] > 45) & (dataframe['rsi'] < 70) &
            (dataframe['volume_ratio'] > 1.0)
        )
        
        # SHORT: Simple conditions
        short_dip_sell = (
            (dataframe['downtrend']) &
            (dataframe['rsi'] > self.rsi_overbought.value) &
            (dataframe['volume_ratio'] > self.volume_multiplier.value)
        )
        
        short_breakdown = (
            (dataframe['momentum_5'] < -self.trend_strength.value) &
            (dataframe['red_candle'] == 1) &
            (dataframe['volume_ratio'] > 1.5) &
            (dataframe['close'] < dataframe['ema_8'])
        )
        
        short_trend_follow = (
            (dataframe['downtrend']) &
            (dataframe['close'] < dataframe['close'].shift(1)) &
            (dataframe['rsi'] < 55) & (dataframe['rsi'] > 30) &
            (dataframe['volume_ratio'] > 1.0)
        )
        
        # COMBINE WITH OR LOGIC (more trades!)
        long_entry = long_dip_buy | long_breakout | long_trend_follow
        short_entry = short_dip_sell | short_breakdown | short_trend_follow
        
        # Basic filters only
        long_entry = long_entry & (dataframe['volume'] > 0)
        short_entry = short_entry & (dataframe['volume'] > 0)
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'bull_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'bull_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """MINIMAL exit conditions - let ROI and trailing stop work"""
        
        # Only exit on EXTREME trend reversal (much more restrictive)
        long_exit = (
            (dataframe['downtrend']) &
            (dataframe['momentum_5'] < -0.02) &  # Stronger momentum required
            (dataframe['momentum_20'] < -0.03) &  # Longer term momentum too
            (dataframe['rsi'] < 25) &             # More extreme RSI
            (dataframe['volume_ratio'] > 2.0)    # High volume confirmation
        )
        
        short_exit = (
            (dataframe['uptrend']) &
            (dataframe['momentum_5'] > 0.02) &   # Stronger momentum required
            (dataframe['momentum_20'] > 0.03) &  # Longer term momentum too
            (dataframe['rsi'] > 75) &            # More extreme RSI
            (dataframe['volume_ratio'] > 2.0)   # High volume confirmation
        )
        
        dataframe.loc[long_exit, 'exit_long'] = 1
        dataframe.loc[short_exit, 'exit_short'] = 1
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        AGGRESSIVE position sizing for bull markets
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        
        total_balance = self.wallets.get_total_stake_amount()
        
        # Base 8% position (more aggressive than 5%)
        base_stake = total_balance * 0.08
        
        # INCREASE size in strong trends
        if last_candle['uptrend'] and last_candle['momentum_20'] > 0.02:
            base_stake *= 1.3  # 30% larger in strong bull trends
        elif last_candle['downtrend'] and last_candle['momentum_20'] < -0.02:
            base_stake *= 1.3  # 30% larger in strong bear trends
        
        # INCREASE size on high volume
        if last_candle['volume_ratio'] > 2.0:
            base_stake *= 1.2  # 20% larger on volume spikes
        
        # Ensure within limits
        position_size = min(base_stake, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size
    
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """
        Scale into winning positions aggressively
        """
        # Scale in if profitable and trend continues
        if current_profit > 0.008 and trade.nr_of_successful_entries == 0:  # 0.8% profit
            dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            
            # Check if trend is still strong
            if ((trade.is_short and last_candle['downtrend']) or 
                (not trade.is_short and last_candle['uptrend'])):
                
                # Scale in with 60% of original position
                return trade.stake_amount * 0.6
        
        return None
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        MINIMAL custom exits - let ROI handle profits
        """
        
        # Only exit on EXTREME profit protection at 5%+ (let smaller profits run to ROI)
        if current_profit > 0.05:  # 5%+ profit
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            
            # Only exit if momentum completely reverses
            if abs(last_candle['momentum_5']) < -0.01:
                return 'profit_protection'
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                            side: str, **kwargs) -> bool:
        """
        Simple confirmation - don't block trades!
        """
        
        # Only basic sanity checks
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        
        # Don't trade in extreme volatility
        if last_candle['atr'] / last_candle['close'] > 0.05:  # 5% ATR
            return False
        
        return True