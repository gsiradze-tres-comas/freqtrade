"""
Try1 Profitable Strategy - Fixed Risk/Reward Ratio
Problem: 71.8% win rate but still losing money
Solution: Better risk/reward ratio + wider stops for crypto volatility
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

class Try1ProfitableStrategy(IStrategy):
    """
    Fixed version with proper risk/reward ratio
    Target: Actually make money with 70%+ win rate
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # FIXED ROI: Better risk/reward ratio
    minimal_roi = {
        "0": 0.025,   # 2.5% take profit (vs 1.2% before)
        "240": 0.015, # 1.5% after 4 hours
        "480": 0.008, # 0.8% after 8 hours
        "960": 0.004  # 0.4% after 16 hours
    }
    
    # WIDER STOP LOSS: Crypto needs room to breathe
    stoploss = -0.035  # 3.5% stop loss (vs 2% before)
    
    # IMPROVED TRAILING STOP
    trailing_stop = True
    trailing_stop_positive = 0.008   # Start trailing at 0.8%
    trailing_stop_positive_offset = 0.012  # Trail by 1.2%
    trailing_only_offset_is_reached = True
    
    # No position adjustment
    position_adjustment_enable = False
    
    # Same strategy weights (they work - 71.8% win rate!)
    strategy_weights = {
        'main_engulfing': 0.25,
        'rsi_bounce': 0.20,
        'ma_crossover': 0.20,
        'volume_spike': 0.15,
        'breakout': 0.10,
        'momentum_backup': 0.10
    }
    
    # Same parameters that gave us 71.8% win rate
    rsi_oversold = IntParameter(20, 30, default=25, space="buy", load=True)
    rsi_overbought = IntParameter(70, 80, default=75, space="sell", load=True)
    volume_threshold = DecimalParameter(1.2, 2.0, decimals=1, default=1.5, space="buy", load=True)
    min_confidence = DecimalParameter(0.25, 0.45, decimals=2, default=0.35, space="buy", load=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Same indicators that worked (71.8% win rate)"""
        
        # EMAs for ma_crossover strategy
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI for rsi_bounce strategy
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(2)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Price momentum
        dataframe['price_change'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_20'] = dataframe['close'].pct_change(periods=20)
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # Engulfing patterns
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.001)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        
        # Previous candle info
        dataframe['prev_body_size'] = dataframe['body_size'].shift(1)
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        
        # Support/Resistance
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Calculate strategy signals
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
    
    def _calculate_strategy_signals(self, df: DataFrame) -> DataFrame:
        """Same strategy signals that gave us 71.8% win rate"""
        
        # 1. Main Engulfing Strategy
        bullish_engulfing = (
            (df['green_candle'] == 1) &
            (df['prev_red'] == 1) &
            (df['body_size'] > df['prev_body_size']) &
            (df['body_ratio'] > 0.12) &
            (df['volume_ratio'] > 1.2) &
            (df['rsi'] > 15) & (df['rsi'] < 85)
        )
        
        bearish_engulfing = (
            (df['red_candle'] == 1) &
            (df['prev_green'] == 1) &
            (df['body_size'] > df['prev_body_size']) &
            (df['body_ratio'] > 0.12) &
            (df['volume_ratio'] > 1.2) &
            (df['rsi'] > 15) & (df['rsi'] < 85)
        )
        
        df['main_engulfing_signal'] = np.where(bullish_engulfing, 1.0,
                                              np.where(bearish_engulfing, -1.0, 0.0))
        
        # 2. RSI Bounce Strategy
        rsi_bounce_long = (
            (df['rsi'] < 25) &
            (df['rsi_slope'] > 5) &
            (df['volume_ratio'] > 0.8) &
            (df['price_change'] > 0.002)
        )
        
        rsi_bounce_short = (
            (df['rsi'] > 75) &
            (df['rsi_slope'] < -5) &
            (df['volume_ratio'] > 0.8) &
            (df['price_change'] < -0.002)
        )
        
        df['rsi_bounce_signal'] = np.where(rsi_bounce_long, 1.0,
                                          np.where(rsi_bounce_short, -1.0, 0.0))
        
        # 3. MA Crossover Strategy
        ma_cross_long = (
            (df['ema_fast'] > df['ema_slow']) &
            (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1)) &
            (abs(df['ema_fast'] - df['ema_slow']) / df['close'] > 0.001) &
            (df['volume_ratio'] > 0.8) &
            (df['close'] > df['ema_200'])
        )
        
        ma_cross_short = (
            (df['ema_fast'] < df['ema_slow']) &
            (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1)) &
            (abs(df['ema_fast'] - df['ema_slow']) / df['close'] > 0.001) &
            (df['volume_ratio'] > 0.8) &
            (df['close'] < df['ema_200'])
        )
        
        df['ma_crossover_signal'] = np.where(ma_cross_long, 1.0,
                                            np.where(ma_cross_short, -1.0, 0.0))
        
        # 4. Volume Spike Strategy
        volume_spike_long = (
            (df['volume_ratio'] > 2.0) &
            (df['price_change'] > 0.003) &
            (df['green_candle'] == 1) &
            (df['rsi'] < 70)
        )
        
        volume_spike_short = (
            (df['volume_ratio'] > 2.0) &
            (df['price_change'] < -0.003) &
            (df['red_candle'] == 1) &
            (df['rsi'] > 30)
        )
        
        df['volume_spike_signal'] = np.where(volume_spike_long, 1.0,
                                            np.where(volume_spike_short, -1.0, 0.0))
        
        # 5. Breakout Strategy
        breakout_long = (
            (df['close'] > df['resistance']) &
            (df['volume_ratio'] > 1.5) &
            (df['bb_width'] > 0.003) &
            (df['price_change'] > 0.003)
        )
        
        breakout_short = (
            (df['close'] < df['support']) &
            (df['volume_ratio'] > 1.5) &
            (df['bb_width'] > 0.003) &
            (df['price_change'] < -0.003)
        )
        
        df['breakout_signal'] = np.where(breakout_long, 1.0,
                                        np.where(breakout_short, -1.0, 0.0))
        
        # 6. Momentum Backup Strategy
        momentum_long = (
            (df['momentum_20'] > 0.005) &
            (df['rsi'] < 75) &
            (df['volume_ratio'] > 1.3)
        )
        
        momentum_short = (
            (df['momentum_20'] < -0.005) &
            (df['rsi'] > 25) &
            (df['volume_ratio'] > 1.3)
        )
        
        df['momentum_backup_signal'] = np.where(momentum_long, 1.0,
                                               np.where(momentum_short, -1.0, 0.0))
        
        return df
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Same entry logic that gave us 71.8% win rate"""
        
        # Count active strategies
        dataframe['active_strategies'] = (
            (dataframe['main_engulfing_signal'] != 0).astype(int) +
            (dataframe['rsi_bounce_signal'] != 0).astype(int) +
            (dataframe['ma_crossover_signal'] != 0).astype(int) +
            (dataframe['volume_spike_signal'] != 0).astype(int) +
            (dataframe['breakout_signal'] != 0).astype(int) +
            (dataframe['momentum_backup_signal'] != 0).astype(int)
        )
        
        # Same entry conditions that worked
        long_entry = (
            (dataframe['consensus_score'] >= self.min_confidence.value) &
            (dataframe['active_strategies'] >= 2) &
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)
        )
        
        short_entry = (
            (dataframe['consensus_score'] <= -self.min_confidence.value) &
            (dataframe['active_strategies'] >= 2) &
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)
        )
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'profitable_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'profitable_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Let the improved ROI and wider SL handle exits"""
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Reduced position size for better risk management
        4% instead of 6% (since we're using wider stops)
        """
        total_balance = self.wallets.get_total_stake_amount()
        
        # Smaller position size with wider stops = better risk management
        position_size = total_balance * 0.04  # 4% instead of 6%
        
        # Ensure within limits
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size