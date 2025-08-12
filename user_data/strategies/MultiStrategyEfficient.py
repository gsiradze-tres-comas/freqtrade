"""
Efficient Multi-Strategy Consensus Trading Strategy
Vectorized version for faster backtesting performance

Based on successful try1 bot that achieved 2% average overnight wins
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class MultiStrategyEfficient(IStrategy):
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # Optimizable ROI parameters
    minimal_roi = {
        "0": 0.015,   # 1.5% target
        "30": 0.010,  # 1.0% after 30 minutes
        "60": 0.005,  # 0.5% after 1 hour
        "120": 0.0    # Break even after 2 hours
    }
    
    stoploss = -0.025  # 2.5% stop loss
    
    # Consensus parameters for optimization
    consensus_threshold = DecimalParameter(0.30, 0.60, decimals=2, default=0.45, space="buy")
    min_signals_required = IntParameter(2, 4, default=3, space="buy")
    
    # Risk management parameters
    volatility_threshold = DecimalParameter(2.0, 5.0, decimals=1, default=3.5, space="buy")
    volume_threshold = DecimalParameter(1.2, 2.5, decimals=1, default=1.5, space="buy")
    
    # Strategy weight parameters (simplified)
    engulfing_enabled = IntParameter(0, 1, default=1, space="buy")
    rsi_enabled = IntParameter(0, 1, default=1, space="buy")
    ma_enabled = IntParameter(0, 1, default=1, space="buy")
    volume_enabled = IntParameter(0, 1, default=1, space="buy")
    breakout_enabled = IntParameter(0, 1, default=1, space="buy")
    momentum_enabled = IntParameter(0, 1, default=1, space="buy")
    
    # RSI parameters
    rsi_oversold = IntParameter(20, 35, default=30, space="buy")
    rsi_overbought = IntParameter(65, 80, default=70, space="sell")
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate all indicators needed for the strategies"""
        
        # Basic indicators
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_trend'] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume indicators
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Volatility indicators
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_sma'] = ta.SMA(dataframe['atr'], timeperiod=20)
        dataframe['volatility_ratio'] = dataframe['atr'] / dataframe['atr_sma']
        
        # Price action indicators
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['candle_range'] = dataframe['high'] - dataframe['low']
        
        # Support/Resistance levels
        dataframe['pivot_high'] = dataframe['high'].rolling(window=5).max()
        dataframe['pivot_low'] = dataframe['low'].rolling(window=5).min()
        
        # Momentum indicators
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        stoch = ta.STOCH(dataframe)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        
        # Strategy signals (vectorized)
        dataframe['engulfing_bull'] = self._engulfing_signal(dataframe, 'bull')
        dataframe['engulfing_bear'] = self._engulfing_signal(dataframe, 'bear')
        
        dataframe['rsi_bull'] = self._rsi_signal(dataframe, 'bull')
        dataframe['rsi_bear'] = self._rsi_signal(dataframe, 'bear')
        
        dataframe['ma_bull'] = self._ma_crossover_signal(dataframe, 'bull')
        dataframe['ma_bear'] = self._ma_crossover_signal(dataframe, 'bear')
        
        dataframe['volume_bull'] = self._volume_spike_signal(dataframe, 'bull')
        dataframe['volume_bear'] = self._volume_spike_signal(dataframe, 'bear')
        
        dataframe['breakout_bull'] = self._breakout_signal(dataframe, 'bull')
        dataframe['breakout_bear'] = self._breakout_signal(dataframe, 'bear')
        
        dataframe['momentum_bull'] = self._momentum_signal(dataframe, 'bull')
        dataframe['momentum_bear'] = self._momentum_signal(dataframe, 'bear')
        
        # Count signals
        dataframe['bull_signals'] = (
            (dataframe['engulfing_bull'] * self.engulfing_enabled.value) +
            (dataframe['rsi_bull'] * self.rsi_enabled.value) +
            (dataframe['ma_bull'] * self.ma_enabled.value) +
            (dataframe['volume_bull'] * self.volume_enabled.value) +
            (dataframe['breakout_bull'] * self.breakout_enabled.value) +
            (dataframe['momentum_bull'] * self.momentum_enabled.value)
        )
        
        dataframe['bear_signals'] = (
            (dataframe['engulfing_bear'] * self.engulfing_enabled.value) +
            (dataframe['rsi_bear'] * self.rsi_enabled.value) +
            (dataframe['ma_bear'] * self.ma_enabled.value) +
            (dataframe['volume_bear'] * self.volume_enabled.value) +
            (dataframe['breakout_bear'] * self.breakout_enabled.value) +
            (dataframe['momentum_bear'] * self.momentum_enabled.value)
        )
        
        return dataframe
    
    def _engulfing_signal(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Vectorized engulfing pattern detection"""
        if direction == 'bull':
            return (
                (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &  # Previous red
                (dataframe['close'] > dataframe['open']) &  # Current green
                (dataframe['open'] < dataframe['close'].shift(1)) &  # Gap down
                (dataframe['close'] > dataframe['open'].shift(1)) &  # Engulfs
                (dataframe['volume_ratio'] > self.volume_threshold.value)
            ).astype(int)
        else:
            return (
                (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &  # Previous green
                (dataframe['close'] < dataframe['open']) &  # Current red
                (dataframe['open'] > dataframe['close'].shift(1)) &  # Gap up
                (dataframe['close'] < dataframe['open'].shift(1)) &  # Engulfs
                (dataframe['volume_ratio'] > self.volume_threshold.value)
            ).astype(int)
    
    def _rsi_signal(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Vectorized RSI bounce detection"""
        if direction == 'bull':
            return (
                (dataframe['rsi'] < self.rsi_oversold.value) &
                (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
                (dataframe['close'] > dataframe['ema_fast'])
            ).astype(int)
        else:
            return (
                (dataframe['rsi'] > self.rsi_overbought.value) &
                (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
                (dataframe['close'] < dataframe['ema_fast'])
            ).astype(int)
    
    def _ma_crossover_signal(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Vectorized MA crossover detection"""
        if direction == 'bull':
            return (
                (dataframe['ema_fast'] > dataframe['ema_slow']) &
                (dataframe['ema_fast'].shift(1) <= dataframe['ema_slow'].shift(1)) &
                (dataframe['ema_fast'] > dataframe['ema_trend'])
            ).astype(int)
        else:
            return (
                (dataframe['ema_fast'] < dataframe['ema_slow']) &
                (dataframe['ema_fast'].shift(1) >= dataframe['ema_slow'].shift(1)) &
                (dataframe['ema_fast'] < dataframe['ema_trend'])
            ).astype(int)
    
    def _volume_spike_signal(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Vectorized volume spike detection"""
        price_change = (dataframe['close'] - dataframe['open']) / dataframe['open']
        
        if direction == 'bull':
            return (
                (dataframe['volume_ratio'] > self.volume_threshold.value) &
                (price_change > 0.002)
            ).astype(int)
        else:
            return (
                (dataframe['volume_ratio'] > self.volume_threshold.value) &
                (price_change < -0.002)
            ).astype(int)
    
    def _breakout_signal(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Vectorized breakout detection"""
        if direction == 'bull':
            return (
                (dataframe['close'] > dataframe['pivot_high'].shift(1)) &
                (dataframe['volume_ratio'] > 1.3)
            ).astype(int)
        else:
            return (
                (dataframe['close'] < dataframe['pivot_low'].shift(1)) &
                (dataframe['volume_ratio'] > 1.3)
            ).astype(int)
    
    def _momentum_signal(self, dataframe: DataFrame, direction: str) -> pd.Series:
        """Vectorized momentum detection"""
        if direction == 'bull':
            return (
                (dataframe['macd_hist'] > 0) &
                (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)) &
                (dataframe['stoch_k'] > 20) &
                (dataframe['stoch_k'] < 80)
            ).astype(int)
        else:
            return (
                (dataframe['macd_hist'] < 0) &
                (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1)) &
                (dataframe['stoch_k'] < 80) &
                (dataframe['stoch_k'] > 20)
            ).astype(int)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate entry signals using efficient multi-strategy consensus"""
        
        # Volatility filter
        volatility_ok = dataframe['volatility_ratio'] <= self.volatility_threshold.value
        
        # Consensus conditions
        long_consensus = (
            (dataframe['bull_signals'] >= self.min_signals_required.value) &
            (dataframe['bull_signals'] > dataframe['bear_signals']) &
            volatility_ok
        )
        
        short_consensus = (
            (dataframe['bear_signals'] >= self.min_signals_required.value) &
            (dataframe['bear_signals'] > dataframe['bull_signals']) &
            volatility_ok
        )
        
        dataframe.loc[long_consensus, 'enter_long'] = 1
        dataframe.loc[short_consensus, 'enter_short'] = 1
        
        # Add tags
        dataframe.loc[long_consensus, 'enter_tag'] = (
            'eff_long_' + dataframe['bull_signals'].astype(str) + 'sig'
        )
        dataframe.loc[short_consensus, 'enter_tag'] = (
            'eff_short_' + dataframe['bear_signals'].astype(str) + 'sig'
        )
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate exit signals efficiently"""
        
        # Exit on strong opposite consensus
        strong_short_signal = (
            (dataframe['bear_signals'] >= 4) &
            (dataframe['bear_signals'] > dataframe['bull_signals'] + 1)
        )
        
        strong_long_signal = (
            (dataframe['bull_signals'] >= 4) &
            (dataframe['bull_signals'] > dataframe['bear_signals'] + 1)
        )
        
        dataframe.loc[strong_short_signal, 'exit_long'] = 1
        dataframe.loc[strong_short_signal, 'exit_tag'] = 'eff_consensus_short_exit'
        
        dataframe.loc[strong_long_signal, 'exit_short'] = 1
        dataframe.loc[strong_long_signal, 'exit_tag'] = 'eff_consensus_long_exit'
        
        return dataframe
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """Conservative leverage for efficient strategy"""
        return min(proposed_leverage, 2.0)