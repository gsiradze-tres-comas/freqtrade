"""
Try1 Replicated Strategy - Based on your 2% daily profitable bot
Using your exact configuration:
- Stop Loss: 2.0%
- Take Profit: 1.2% 
- Position Size: 6.0%
- Multi-strategy consensus with 6 strategies
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

class Try1ReplicatedStrategy(IStrategy):
    """
    Replication of your successful try1 bot configuration
    Target: 2% daily returns with consistent wins
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'  # Your bot used 5m timeframe
    can_short = True
    
    # Minimal ROI - let positions run to take profit
    minimal_roi = {
        "0": 0.012,  # 1.2% take profit
        "60": 0.008,  # 0.8% after 1 hour
        "120": 0.004,  # 0.4% after 2 hours
        "240": 0.002,  # 0.2% after 4 hours
        "480": 0.001   # 0.1% after 8 hours
    }
    
    # Your exact stop loss
    stoploss = -0.020  # 2.0% stop loss
    
    # Trailing stop configuration
    trailing_stop = True
    trailing_stop_positive = 0.003  # Start trailing at 0.3% profit
    trailing_stop_positive_offset = 0.006  # Trail by 0.6%
    trailing_only_offset_is_reached = True
    
    # Position adjustment disabled (your bot didn't pyramid)
    position_adjustment_enable = False
    
    # Strategy weights (from your config)
    strategy_weights = {
        'engulfing': 0.25,
        'ma_crossover': 0.20,
        'momentum': 0.20,
        'rsi_bounce': 0.15,
        'volume_spike': 0.10,
        'breakout': 0.10
    }
    
    # Strategy parameters
    rsi_period = IntParameter(10, 20, default=14, space="buy", load=True)
    rsi_oversold = IntParameter(20, 35, default=25, space="buy", load=True)
    rsi_overbought = IntParameter(65, 80, default=75, space="sell", load=True)
    
    ema_fast = IntParameter(5, 15, default=10, space="buy", load=True)
    ema_slow = IntParameter(20, 50, default=30, space="buy", load=True)
    
    volume_multiplier = DecimalParameter(1.2, 3.0, decimals=1, default=1.5, space="buy", load=True)
    momentum_period = IntParameter(10, 30, default=20, space="buy", load=True)
    
    @informative('15m')
    def populate_indicators_15m(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """15m indicators for higher timeframe confirmation"""
        dataframe['ema_50_15m'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['rsi_15m'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['trend_15m'] = np.where(dataframe['close'] > dataframe['ema_50_15m'], 1, -1)
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Indicators for 6 strategies"""
        
        # Price action
        dataframe['open'] = dataframe['open']
        dataframe['high'] = dataframe['high']
        dataframe['low'] = dataframe['low']
        dataframe['close'] = dataframe['close']
        
        # EMAs for MA crossover strategy
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI for bounce strategy
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_spike'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Momentum
        dataframe['momentum'] = dataframe['close'].pct_change(periods=self.momentum_period.value)
        dataframe['momentum_sma'] = dataframe['momentum'].rolling(window=5).mean()
        
        # Bollinger Bands for breakout
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # Engulfing pattern detection
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body'] / (dataframe['high'] - dataframe['low'] + 0.001)
        
        # Previous candle info
        dataframe['prev_close'] = dataframe['close'].shift(1)
        dataframe['prev_open'] = dataframe['open'].shift(1)
        dataframe['prev_high'] = dataframe['high'].shift(1)
        dataframe['prev_low'] = dataframe['low'].shift(1)
        dataframe['prev_body'] = abs(dataframe['prev_close'] - dataframe['prev_open'])
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        
        # Support/Resistance
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Get 15m data
        dataframe['trend_15m'] = dataframe['trend_15m_15m']
        dataframe['rsi_15m'] = dataframe['rsi_15m_15m']
        
        # Strategy signals (0-1 confidence for each)
        dataframe = self._calculate_strategy_signals(dataframe)
        
        # Consensus score
        dataframe['consensus_score'] = (
            dataframe['engulfing_signal'] * self.strategy_weights['engulfing'] +
            dataframe['ma_crossover_signal'] * self.strategy_weights['ma_crossover'] +
            dataframe['momentum_signal'] * self.strategy_weights['momentum'] +
            dataframe['rsi_bounce_signal'] * self.strategy_weights['rsi_bounce'] +
            dataframe['volume_spike_signal'] * self.strategy_weights['volume_spike'] +
            dataframe['breakout_signal'] * self.strategy_weights['breakout']
        )
        
        return dataframe
    
    def _calculate_strategy_signals(self, df: DataFrame) -> DataFrame:
        """Calculate individual strategy signals"""
        
        # 1. Engulfing Pattern
        bullish_engulfing = (
            (df['close'] > df['open']) &  # Current green
            (df['prev_close'] < df['prev_open']) &  # Previous red
            (df['close'] > df['prev_open']) &  # Engulfs previous
            (df['open'] < df['prev_close']) &
            (df['body_ratio'] > 0.5) &  # Significant body
            (df['volume_spike'] > 1.2)  # Volume confirmation
        )
        
        bearish_engulfing = (
            (df['close'] < df['open']) &  # Current red
            (df['prev_close'] > df['prev_open']) &  # Previous green
            (df['close'] < df['prev_open']) &  # Engulfs previous
            (df['open'] > df['prev_close']) &
            (df['body_ratio'] > 0.5) &
            (df['volume_spike'] > 1.2)
        )
        
        df['engulfing_signal'] = np.where(bullish_engulfing, 1.0,
                                         np.where(bearish_engulfing, -1.0, 0.0))
        
        # 2. MA Crossover
        ma_bullish = (
            (df['ema_fast'] > df['ema_slow']) &
            (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1)) &
            (df['close'] > df['ema_200'])  # Above long-term trend
        )
        
        ma_bearish = (
            (df['ema_fast'] < df['ema_slow']) &
            (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1)) &
            (df['close'] < df['ema_200'])
        )
        
        df['ma_crossover_signal'] = np.where(ma_bullish, 1.0,
                                            np.where(ma_bearish, -1.0, 0.0))
        
        # 3. Momentum
        momentum_bullish = (
            (df['momentum'] > 0.003) &  # 0.3% momentum
            (df['momentum'] > df['momentum_sma']) &
            (df['volume_spike'] > 1.3)
        )
        
        momentum_bearish = (
            (df['momentum'] < -0.003) &
            (df['momentum'] < df['momentum_sma']) &
            (df['volume_spike'] > 1.3)
        )
        
        df['momentum_signal'] = np.where(momentum_bullish, 1.0,
                                       np.where(momentum_bearish, -1.0, 0.0))
        
        # 4. RSI Bounce
        rsi_bullish = (
            (df['rsi'] < self.rsi_oversold.value) &
            (df['rsi'] > df['rsi'].shift(1)) &  # RSI turning up
            (df['close'] > df['support'])  # Above support
        )
        
        rsi_bearish = (
            (df['rsi'] > self.rsi_overbought.value) &
            (df['rsi'] < df['rsi'].shift(1)) &  # RSI turning down
            (df['close'] < df['resistance'])  # Below resistance
        )
        
        df['rsi_bounce_signal'] = np.where(rsi_bullish, 1.0,
                                          np.where(rsi_bearish, -1.0, 0.0))
        
        # 5. Volume Spike
        volume_bullish = (
            (df['volume_spike'] > self.volume_multiplier.value) &
            (df['close'] > df['open']) &  # Green candle
            (df['close'] > df['prev_close'])  # Higher close
        )
        
        volume_bearish = (
            (df['volume_spike'] > self.volume_multiplier.value) &
            (df['close'] < df['open']) &  # Red candle
            (df['close'] < df['prev_close'])  # Lower close
        )
        
        df['volume_spike_signal'] = np.where(volume_bullish, 1.0,
                                            np.where(volume_bearish, -1.0, 0.0))
        
        # 6. Breakout
        breakout_bullish = (
            (df['close'] > df['bb_upper']) &
            (df['volume_spike'] > 1.5) &
            (df['bb_width'] > 0.02)  # Bollinger expansion
        )
        
        breakout_bearish = (
            (df['close'] < df['bb_lower']) &
            (df['volume_spike'] > 1.5) &
            (df['bb_width'] > 0.02)
        )
        
        df['breakout_signal'] = np.where(breakout_bullish, 1.0,
                                        np.where(breakout_bearish, -1.0, 0.0))
        
        return df
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry signals based on consensus"""
        
        # Count active strategies
        dataframe['active_strategies'] = (
            (dataframe['engulfing_signal'] != 0).astype(int) +
            (dataframe['ma_crossover_signal'] != 0).astype(int) +
            (dataframe['momentum_signal'] != 0).astype(int) +
            (dataframe['rsi_bounce_signal'] != 0).astype(int) +
            (dataframe['volume_spike_signal'] != 0).astype(int) +
            (dataframe['breakout_signal'] != 0).astype(int)
        )
        
        # Long entry conditions
        long_conditions = (
            (dataframe['consensus_score'] > 0.35) &  # 35% consensus threshold
            (dataframe['active_strategies'] >= 2) &  # At least 2 strategies agree
            (dataframe['trend_15m'] == 1) &  # 15m uptrend
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)  # Minimum volatility
        )
        
        # Short entry conditions
        short_conditions = (
            (dataframe['consensus_score'] < -0.35) &  # -35% consensus threshold
            (dataframe['active_strategies'] >= 2) &  # At least 2 strategies agree
            (dataframe['trend_15m'] == -1) &  # 15m downtrend
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.0015)  # Minimum volatility
        )
        
        dataframe.loc[long_conditions, ['enter_long', 'enter_tag']] = (1, 'try1_long_consensus')
        dataframe.loc[short_conditions, ['enter_short', 'enter_tag']] = (1, 'try1_short_consensus')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit signals - mainly rely on SL/TP and trailing stop"""
        
        # Exit long if strong bearish consensus
        exit_long = (
            (dataframe['consensus_score'] < -0.40) &  # Strong opposite signal
            (dataframe['active_strategies'] >= 3)  # Multiple strategies agree
        )
        
        # Exit short if strong bullish consensus
        exit_short = (
            (dataframe['consensus_score'] > 0.40) &  # Strong opposite signal
            (dataframe['active_strategies'] >= 3)  # Multiple strategies agree
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_short, 'exit_short'] = 1
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Position sizing - 6% of balance per trade (from your config)
        """
        total_balance = self.wallets.get_total_stake_amount()
        
        # Your bot uses 6% position size
        position_size = total_balance * 0.06
        
        # Ensure within limits
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size