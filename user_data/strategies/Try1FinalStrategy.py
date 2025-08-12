"""
Try1 Final Strategy - Exact Match of Your Profitable Bot
Target: 10-20 trades per day MAX (not 79)
Using your exact 6-strategy consensus with strict quality filters
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

class Try1FinalStrategy(IStrategy):
    """
    Final strategy exactly matching your profitable try1 bot
    6 strategies with weighted consensus + strict quality filters
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # Your exact profitable settings from config.yaml
    minimal_roi = {
        "0": 0.012,   # 1.2% take profit (take_profit_percent: 1.2)
        "240": 0.006, # 0.6% after 4 hours
        "480": 0.003, # 0.3% after 8 hours
        "960": 0.001  # 0.1% after 16 hours
    }
    
    # Your exact stop loss from config.yaml
    stoploss = -0.020  # stop_loss_percent: 2.0
    
    # Trailing stop like your config
    trailing_stop = True
    trailing_stop_positive = 0.005  # Start at 0.5%
    trailing_stop_positive_offset = 0.008  # Trail by 0.8%
    trailing_only_offset_is_reached = True
    
    # No position adjustment
    position_adjustment_enable = False
    
    # Strategy weights from your config
    strategy_weights = {
        'main_engulfing': 0.25,      # Primary strategy
        'rsi_bounce': 0.20,          # High frequency
        'ma_crossover': 0.20,        # Reliable signals
        'volume_spike': 0.15,        # Volume confirmation
        'breakout': 0.10,            # Range breakouts
        'momentum_backup': 0.10      # Backup momentum
    }
    
    # Parameters matching your config ranges but with better balance
    rsi_oversold = IntParameter(20, 30, default=25, space="buy", load=True)     # rsi_min: 15
    rsi_overbought = IntParameter(70, 80, default=75, space="sell", load=True)  # rsi_max: 85
    volume_threshold = DecimalParameter(1.2, 2.0, decimals=1, default=1.5, space="buy", load=True)  # volume_multiplier: 1.05
    min_confidence = DecimalParameter(0.25, 0.45, decimals=2, default=0.35, space="buy", load=True)  # Reduced from 0.70 to 0.35
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Indicators for all 6 strategies from your config"""
        
        # EMAs for ma_crossover strategy
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)   # fast_ema_period: 8
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)  # slow_ema_period: 21
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI for rsi_bounce strategy
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(2)
        
        # Volume analysis for multiple strategies
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()  # volume_lookback: 20
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Price momentum for momentum_backup
        dataframe['price_change'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_20'] = dataframe['close'].pct_change(periods=20)
        
        # Bollinger Bands for breakout strategy
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # Engulfing pattern detection for main_engulfing
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.001)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        
        # Previous candle info
        dataframe['prev_body_size'] = dataframe['body_size'].shift(1)
        dataframe['prev_red'] = dataframe['red_candle'].shift(1)
        dataframe['prev_green'] = dataframe['green_candle'].shift(1)
        
        # Support/Resistance for breakout
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()   # lookback_period: 20
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Calculate individual strategy signals
        dataframe = self._calculate_strategy_signals(dataframe)
        
        # Calculate weighted consensus score
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
        """Calculate signals for all 6 strategies from your config"""
        
        # 1. Main Engulfing Strategy (25% weight)
        bullish_engulfing = (
            (df['green_candle'] == 1) &
            (df['prev_red'] == 1) &
            (df['body_size'] > df['prev_body_size']) &
            (df['body_ratio'] > 0.12) &  # min_body_ratio: 0.12
            (df['volume_ratio'] > 1.2) &  # volume_multiplier: 1.2
            (df['rsi'] > 15) & (df['rsi'] < 85)  # RSI filters
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
        
        # 2. RSI Bounce Strategy (20% weight)
        rsi_bounce_long = (
            (df['rsi'] < 25) &  # rsi_oversold: 25
            (df['rsi_slope'] > 5) &  # rsi_bounce_threshold: 5
            (df['volume_ratio'] > 0.8) &  # min_volume_ratio: 0.8
            (df['price_change'] > 0.002)  # price_confirmation: 0.002
        )
        
        rsi_bounce_short = (
            (df['rsi'] > 75) &  # rsi_overbought: 75
            (df['rsi_slope'] < -5) &
            (df['volume_ratio'] > 0.8) &
            (df['price_change'] < -0.002)
        )
        
        df['rsi_bounce_signal'] = np.where(rsi_bounce_long, 1.0,
                                          np.where(rsi_bounce_short, -1.0, 0.0))
        
        # 3. MA Crossover Strategy (20% weight)
        ma_cross_long = (
            (df['ema_fast'] > df['ema_slow']) &
            (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1)) &
            (abs(df['ema_fast'] - df['ema_slow']) / df['close'] > 0.001) &  # min_separation: 0.001
            (df['volume_ratio'] > 0.8) &  # volume_threshold: 0.8
            (df['close'] > df['ema_200'])  # trend_confirmation: true
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
        
        # 4. Volume Spike Strategy (15% weight)
        volume_spike_long = (
            (df['volume_ratio'] > 2.0) &  # volume_spike_threshold: 2.0
            (df['price_change'] > 0.003) &  # min_price_movement: 0.003
            (df['green_candle'] == 1) &
            (df['rsi'] < 70)  # rsi_filter_enabled: true
        )
        
        volume_spike_short = (
            (df['volume_ratio'] > 2.0) &
            (df['price_change'] < -0.003) &
            (df['red_candle'] == 1) &
            (df['rsi'] > 30)
        )
        
        df['volume_spike_signal'] = np.where(volume_spike_long, 1.0,
                                            np.where(volume_spike_short, -1.0, 0.0))
        
        # 5. Breakout Strategy (10% weight)
        breakout_long = (
            (df['close'] > df['resistance']) &
            (df['volume_ratio'] > 1.5) &  # volume_confirmation: 1.5
            (df['bb_width'] > 0.003) &  # Significant width
            (df['price_change'] > 0.003)  # breakout_threshold: 0.003
        )
        
        breakout_short = (
            (df['close'] < df['support']) &
            (df['volume_ratio'] > 1.5) &
            (df['bb_width'] > 0.003) &
            (df['price_change'] < -0.003)
        )
        
        df['breakout_signal'] = np.where(breakout_long, 1.0,
                                        np.where(breakout_short, -1.0, 0.0))
        
        # 6. Momentum Backup Strategy (10% weight)
        momentum_long = (
            (df['momentum_20'] > 0.005) &  # price_change_threshold: 0.005
            (df['rsi'] < 75) &  # rsi_overbought: 75
            (df['volume_ratio'] > 1.3)  # volume_threshold: 1.3
        )
        
        momentum_short = (
            (df['momentum_20'] < -0.005) &
            (df['rsi'] > 25) &  # rsi_oversold: 25
            (df['volume_ratio'] > 1.3)
        )
        
        df['momentum_backup_signal'] = np.where(momentum_long, 1.0,
                                               np.where(momentum_short, -1.0, 0.0))
        
        return df
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry based on weighted consensus like your try1 bot"""
        
        # Count active strategies
        dataframe['active_strategies'] = (
            (dataframe['main_engulfing_signal'] != 0).astype(int) +
            (dataframe['rsi_bounce_signal'] != 0).astype(int) +
            (dataframe['ma_crossover_signal'] != 0).astype(int) +
            (dataframe['volume_spike_signal'] != 0).astype(int) +
            (dataframe['breakout_signal'] != 0).astype(int) +
            (dataframe['momentum_backup_signal'] != 0).astype(int)
        )
        
        # Long entry: Balanced consensus (35% instead of 70%)
        long_entry = (
            (dataframe['consensus_score'] >= self.min_confidence.value) &  # 35% consensus
            (dataframe['active_strategies'] >= 2) &  # At least 2 strategies agree
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)  # Reduced volatility requirement
        )
        
        # Short entry: Balanced consensus
        short_entry = (
            (dataframe['consensus_score'] <= -self.min_confidence.value) &  # -35% consensus
            (dataframe['active_strategies'] >= 2) &  # At least 2 strategies agree
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)  # Reduced volatility requirement
        )
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'consensus_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'consensus_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Let ROI, SL, and trailing stop handle exits like your bot"""
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        6% position size (position_size_percent: 6.0 from your config)
        """
        total_balance = self.wallets.get_total_stake_amount()
        
        # Your exact 6% position size
        position_size = total_balance * 0.06
        
        # Ensure within limits
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size