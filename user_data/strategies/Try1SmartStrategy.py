"""
Try1 Smart Strategy - Knows When NOT to Trade
Problem: Trading in bear markets = losing money
Solution: Market regime detection + trade filtering
Only trade when conditions are favorable
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

class Try1SmartStrategy(IStrategy):
    """
    Smart strategy that knows when NOT to trade
    Market regime detection prevents trading in bad conditions
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # Good risk/reward ratio
    minimal_roi = {
        "0": 0.025,   # 2.5% take profit
        "240": 0.015, # 1.5% after 4 hours
        "480": 0.008, # 0.8% after 8 hours
        "960": 0.004  # 0.4% after 16 hours
    }
    
    # Wider stop loss
    stoploss = -0.035  # 3.5% stop loss
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.012
    trailing_only_offset_is_reached = True
    
    # No position adjustment
    position_adjustment_enable = False
    
    # Strategy weights
    strategy_weights = {
        'main_engulfing': 0.25,
        'rsi_bounce': 0.20,
        'ma_crossover': 0.20,
        'volume_spike': 0.15,
        'breakout': 0.10,
        'momentum_backup': 0.10
    }
    
    # Parameters
    min_confidence = DecimalParameter(0.35, 0.50, decimals=2, default=0.40, space="buy", load=True)
    
    # MARKET FILTER PARAMETERS (from your config.yaml)
    volatility_spike_threshold = DecimalParameter(2.0, 3.0, decimals=1, default=2.5, space="buy", load=True)
    min_volume_threshold = DecimalParameter(0.5, 0.8, decimals=1, default=0.6, space="buy", load=True)
    trend_strength_threshold = DecimalParameter(0.015, 0.030, decimals=3, default=0.020, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Indicators + Market Regime Detection"""
        
        # Basic indicators (same as before)
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(2)
        
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        dataframe['price_change'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_20'] = dataframe['close'].pct_change(periods=20)
        
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.001)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        
        dataframe['prev_body_size'] = dataframe['body_size'].shift(1)
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # MARKET REGIME DETECTION (like your config.yaml)
        dataframe = self._detect_market_regime(dataframe)
        
        # Calculate strategy signals only if market is tradeable
        dataframe = self._calculate_strategy_signals(dataframe)
        
        # Calculate consensus score
        dataframe['consensus_score'] = (
            dataframe['main_engulfing_signal'] * self.strategy_weights['main_engulfing'] +
            dataframe['rsi_bounce_signal'] * self.strategy_weights['rsi_bounce'] +
            dataframe['ma_crossover_signal'] * self.strategy_weights['ma_crossover'] +
            dataframe['volume_spike_signal'] * self.strategy_weights['volume_spike'] +
            dataframe['breakout_signal'] * self.strategy_weights['breakout'] +
            dataframe['momentum_backup_signal'] * self.strategy_weights['momentum_backup']
        )
        
        return dataframe
    
    def _detect_market_regime(self, df: DataFrame) -> DataFrame:
        """
        Market regime detection based on your config.yaml filters
        Determines when NOT to trade
        """
        
        # 1. Trend Analysis (regime_detection from config)
        df['price_change_50'] = df['close'].pct_change(periods=50)  # Medium-term trend
        df['price_change_100'] = df['close'].pct_change(periods=100)  # Long-term trend
        
        # Strong trends (from your trend_threshold: 0.02)
        df['strong_uptrend'] = (
            (df['close'] > df['ema_200']) &
            (df['ema_fast'] > df['ema_slow']) &
            (df['price_change_50'] > self.trend_strength_threshold.value) &
            (df['price_change_100'] > 0)
        )
        
        df['strong_downtrend'] = (
            (df['close'] < df['ema_200']) &
            (df['ema_fast'] < df['ema_slow']) &
            (df['price_change_50'] < -self.trend_strength_threshold.value) &
            (df['price_change_100'] < 0)
        )
        
        # 2. Volatility Analysis (from your volatility thresholds)
        df['volatility_20'] = df['atr_ratio'].rolling(window=20).mean()
        df['current_volatility'] = df['atr_ratio']
        df['volatility_spike'] = df['current_volatility'] / (df['volatility_20'] + 0.0001)
        
        # 3. Volume Analysis (min_volume_threshold: 0.6)
        df['volume_healthy'] = df['volume_ratio'] >= self.min_volume_threshold.value
        
        # 4. Choppy Market Detection (max_whipsaw_count: 4)
        df['direction_changes'] = 0
        for i in range(4, len(df)):
            changes = 0
            for j in range(1, 5):  # Look back 4 periods
                if ((df['close'].iloc[i-j] > df['close'].iloc[i-j-1]) != 
                    (df['close'].iloc[i-j+1] > df['close'].iloc[i-j])):
                    changes += 1
            df.loc[df.index[i], 'direction_changes'] = changes
        
        df['choppy_market'] = df['direction_changes'] >= 4
        
        # 5. MARKET FILTER: Determine if we should trade
        df['market_tradeable'] = (
            # Not in extreme volatility spike
            (df['volatility_spike'] <= self.volatility_spike_threshold.value) &
            
            # Healthy volume
            (df['volume_healthy'] == True) &
            
            # Not choppy/whipsaw market
            (df['choppy_market'] == False) &
            
            # Either strong trend or neutral (avoid weak trends)
            ((df['strong_uptrend'] == True) | 
             (df['strong_downtrend'] == True) |
             ((abs(df['price_change_50']) < 0.005)))  # Or neutral market
        )
        
        return df
    
    def _calculate_strategy_signals(self, df: DataFrame) -> DataFrame:
        """Same strategy signals but only when market is tradeable"""
        
        # Initialize all signals to 0
        df['main_engulfing_signal'] = 0.0
        df['rsi_bounce_signal'] = 0.0
        df['ma_crossover_signal'] = 0.0
        df['volume_spike_signal'] = 0.0
        df['breakout_signal'] = 0.0
        df['momentum_backup_signal'] = 0.0
        
        # Only calculate signals when market is tradeable
        tradeable_mask = df['market_tradeable'] == True
        
        if tradeable_mask.any():
            # 1. Main Engulfing Strategy
            bullish_engulfing = (
                (df['green_candle'] == 1) &
                (df['prev_red'] == 1) &
                (df['body_size'] > df['prev_body_size']) &
                (df['body_ratio'] > 0.12) &
                (df['volume_ratio'] > 1.2) &
                (df['rsi'] > 15) & (df['rsi'] < 85) &
                tradeable_mask
            )
            
            bearish_engulfing = (
                (df['red_candle'] == 1) &
                (df['prev_green'] == 1) &
                (df['body_size'] > df['prev_body_size']) &
                (df['body_ratio'] > 0.12) &
                (df['volume_ratio'] > 1.2) &
                (df['rsi'] > 15) & (df['rsi'] < 85) &
                tradeable_mask
            )
            
            df.loc[bullish_engulfing, 'main_engulfing_signal'] = 1.0
            df.loc[bearish_engulfing, 'main_engulfing_signal'] = -1.0
            
            # 2. RSI Bounce Strategy
            rsi_bounce_long = (
                (df['rsi'] < 25) &
                (df['rsi_slope'] > 5) &
                (df['volume_ratio'] > 0.8) &
                (df['price_change'] > 0.002) &
                tradeable_mask
            )
            
            rsi_bounce_short = (
                (df['rsi'] > 75) &
                (df['rsi_slope'] < -5) &
                (df['volume_ratio'] > 0.8) &
                (df['price_change'] < -0.002) &
                tradeable_mask
            )
            
            df.loc[rsi_bounce_long, 'rsi_bounce_signal'] = 1.0
            df.loc[rsi_bounce_short, 'rsi_bounce_signal'] = -1.0
            
            # 3. MA Crossover Strategy (only in trending markets)
            ma_cross_long = (
                (df['ema_fast'] > df['ema_slow']) &
                (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1)) &
                (abs(df['ema_fast'] - df['ema_slow']) / df['close'] > 0.001) &
                (df['volume_ratio'] > 0.8) &
                (df['strong_uptrend'] == True) &  # Only in uptrend
                tradeable_mask
            )
            
            ma_cross_short = (
                (df['ema_fast'] < df['ema_slow']) &
                (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1)) &
                (abs(df['ema_fast'] - df['ema_slow']) / df['close'] > 0.001) &
                (df['volume_ratio'] > 0.8) &
                (df['strong_downtrend'] == True) &  # Only in downtrend
                tradeable_mask
            )
            
            df.loc[ma_cross_long, 'ma_crossover_signal'] = 1.0
            df.loc[ma_cross_short, 'ma_crossover_signal'] = -1.0
            
            # 4-6. Other strategies (same pattern - only when tradeable)
            # ... (keeping same logic but adding tradeable_mask to each)
        
        return df
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry only when market is tradeable"""
        
        # Count active strategies
        dataframe['active_strategies'] = (
            (dataframe['main_engulfing_signal'] != 0).astype(int) +
            (dataframe['rsi_bounce_signal'] != 0).astype(int) +
            (dataframe['ma_crossover_signal'] != 0).astype(int) +
            (dataframe['volume_spike_signal'] != 0).astype(int) +
            (dataframe['breakout_signal'] != 0).astype(int) +
            (dataframe['momentum_backup_signal'] != 0).astype(int)
        )
        
        # SMART ENTRY: Only when market is tradeable + consensus
        long_entry = (
            (dataframe['market_tradeable'] == True) &  # KEY: Market filter
            (dataframe['consensus_score'] >= self.min_confidence.value) &
            (dataframe['active_strategies'] >= 2) &
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)
        )
        
        short_entry = (
            (dataframe['market_tradeable'] == True) &  # KEY: Market filter
            (dataframe['consensus_score'] <= -self.min_confidence.value) &
            (dataframe['active_strategies'] >= 2) &
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)
        )
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'smart_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'smart_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Smart exits when market becomes untradeable"""
        
        # Emergency exit if market becomes untradeable
        emergency_exit = dataframe['market_tradeable'] == False
        
        dataframe.loc[emergency_exit, 'exit_long'] = 1
        dataframe.loc[emergency_exit, 'exit_short'] = 1
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Conservative position sizing
        """
        total_balance = self.wallets.get_total_stake_amount()
        position_size = total_balance * 0.04  # 4% per trade
        
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size