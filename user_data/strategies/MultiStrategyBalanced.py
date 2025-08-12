"""
Balanced Multi-Strategy Trading System
Fixes the 7% loss with realistic risk management

Key improvements:
1. Moderate stop loss (1.5%)
2. Quick profit taking (0.5-1%)
3. Trade with trend only
4. Exit quickly on reversal
5. Better signal quality filters
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class MultiStrategyBalanced(IStrategy):
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # Realistic ROI - take profits quickly
    minimal_roi = {
        "0": 0.01,    # 1% immediate target
        "5": 0.008,   # 0.8% after 5 minutes
        "15": 0.006,  # 0.6% after 15 minutes
        "30": 0.004,  # 0.4% after 30 minutes
        "60": 0.002,  # 0.2% after 1 hour
        "120": 0.0    # Break even after 2 hours
    }
    
    # Moderate stop loss
    stoploss = -0.015  # 1.5% stop loss
    
    # Balanced parameters
    consensus_threshold = DecimalParameter(0.40, 0.60, decimals=2, default=0.50, space="buy")
    min_signals_required = IntParameter(2, 4, default=3, space="buy")
    
    # Risk filters
    volatility_threshold = DecimalParameter(2.0, 4.0, decimals=1, default=3.0, space="buy")
    volume_threshold = DecimalParameter(1.3, 2.5, decimals=1, default=1.8, space="buy")
    
    # Trend EMAs
    trend_ema_short = IntParameter(20, 50, default=34, space="buy")
    trend_ema_long = IntParameter(80, 150, default=89, space="buy")
    
    # RSI levels
    rsi_oversold = IntParameter(25, 35, default=30, space="buy")
    rsi_overbought = IntParameter(65, 75, default=70, space="sell")
    
    def informative_pairs(self):
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate indicators for signal generation"""
        
        # Trend EMAs
        dataframe['ema_trend_short'] = ta.EMA(dataframe, timeperiod=self.trend_ema_short.value)
        dataframe['ema_trend_long'] = ta.EMA(dataframe, timeperiod=self.trend_ema_long.value)
        
        # Trend direction
        dataframe['trend_up'] = dataframe['ema_trend_short'] > dataframe['ema_trend_long']
        dataframe['trend_down'] = dataframe['ema_trend_short'] < dataframe['ema_trend_long']
        
        # Fast EMAs for crossovers
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = (dataframe['atr'] / dataframe['close']) * 100
        
        # Bollinger Bands
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_upper'] = bb['upperband']
        dataframe['bb_lower'] = bb['lowerband']
        dataframe['bb_middle'] = bb['middleband']
        dataframe['bb_position'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])
        
        # Support/Resistance
        dataframe['high_5'] = dataframe['high'].rolling(window=5).max()
        dataframe['low_5'] = dataframe['low'].rolling(window=5).min()
        
        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        # Calculate trading signals
        dataframe = self._calculate_signals(dataframe)
        
        return dataframe
    
    def _calculate_signals(self, dataframe: DataFrame) -> DataFrame:
        """Calculate balanced trading signals"""
        
        # Price action helpers
        green_candle = dataframe['close'] > dataframe['open']
        red_candle = dataframe['close'] < dataframe['open']
        body_size = abs(dataframe['close'] - dataframe['open'])
        avg_body = body_size.rolling(window=20).mean()
        
        # 1. Engulfing patterns (relaxed requirements)
        dataframe['engulfing_bull'] = (
            red_candle.shift(1) &  # Previous red
            green_candle &  # Current green
            (dataframe['close'] > dataframe['high'].shift(1)) &  # Close above previous high
            (body_size > avg_body * 1.5) &  # Larger than average
            (dataframe['volume_ratio'] > 1.3) &
            dataframe['trend_up']
        ).astype(int)
        
        dataframe['engulfing_bear'] = (
            green_candle.shift(1) &  # Previous green
            red_candle &  # Current red
            (dataframe['close'] < dataframe['low'].shift(1)) &  # Close below previous low
            (body_size > avg_body * 1.5) &
            (dataframe['volume_ratio'] > 1.3) &
            dataframe['trend_down']
        ).astype(int)
        
        # 2. RSI bounce
        dataframe['rsi_bull'] = (
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
            green_candle &
            (dataframe['bb_position'] < 0.3)  # Near lower band
        ).astype(int)
        
        dataframe['rsi_bear'] = (
            (dataframe['rsi'] > self.rsi_overbought.value) &
            (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
            red_candle &
            (dataframe['bb_position'] > 0.7)  # Near upper band
        ).astype(int)
        
        # 3. MA crossover
        ema_cross_up = (dataframe['ema_fast'] > dataframe['ema_slow']) & (dataframe['ema_fast'].shift(1) <= dataframe['ema_slow'].shift(1))
        ema_cross_down = (dataframe['ema_fast'] < dataframe['ema_slow']) & (dataframe['ema_fast'].shift(1) >= dataframe['ema_slow'].shift(1))
        
        dataframe['ma_bull'] = (
            ema_cross_up &
            dataframe['trend_up'] &
            (dataframe['volume_ratio'] > 1.2)
        ).astype(int)
        
        dataframe['ma_bear'] = (
            ema_cross_down &
            dataframe['trend_down'] &
            (dataframe['volume_ratio'] > 1.2)
        ).astype(int)
        
        # 4. Volume spike
        price_change_pct = ((dataframe['close'] - dataframe['open']) / dataframe['open']) * 100
        
        dataframe['volume_bull'] = (
            (dataframe['volume_ratio'] > self.volume_threshold.value) &
            (price_change_pct > 0.2) &  # 0.2% move
            dataframe['trend_up'] &
            (dataframe['rsi'] < 65)  # Not overbought
        ).astype(int)
        
        dataframe['volume_bear'] = (
            (dataframe['volume_ratio'] > self.volume_threshold.value) &
            (price_change_pct < -0.2) &
            dataframe['trend_down'] &
            (dataframe['rsi'] > 35)  # Not oversold
        ).astype(int)
        
        # 5. Breakout
        dataframe['breakout_bull'] = (
            (dataframe['close'] > dataframe['high_5'].shift(1)) &
            (dataframe['volume_ratio'] > 1.5) &
            dataframe['trend_up'] &
            (dataframe['macd_hist'] > 0)
        ).astype(int)
        
        dataframe['breakout_bear'] = (
            (dataframe['close'] < dataframe['low_5'].shift(1)) &
            (dataframe['volume_ratio'] > 1.5) &
            dataframe['trend_down'] &
            (dataframe['macd_hist'] < 0)
        ).astype(int)
        
        # 6. MACD momentum
        dataframe['momentum_bull'] = (
            (dataframe['macd'] > dataframe['macd_signal']) &
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)) &
            (dataframe['macd_hist'].shift(1) > dataframe['macd_hist'].shift(2)) &  # Accelerating
            dataframe['trend_up']
        ).astype(int)
        
        dataframe['momentum_bear'] = (
            (dataframe['macd'] < dataframe['macd_signal']) &
            (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1)) &
            (dataframe['macd_hist'].shift(1) < dataframe['macd_hist'].shift(2)) &  # Accelerating
            dataframe['trend_down']
        ).astype(int)
        
        # Count signals
        dataframe['bull_signals'] = (
            dataframe['engulfing_bull'] +
            dataframe['rsi_bull'] +
            dataframe['ma_bull'] +
            dataframe['volume_bull'] +
            dataframe['breakout_bull'] +
            dataframe['momentum_bull']
        )
        
        dataframe['bear_signals'] = (
            dataframe['engulfing_bear'] +
            dataframe['rsi_bear'] +
            dataframe['ma_bear'] +
            dataframe['volume_bear'] +
            dataframe['breakout_bear'] +
            dataframe['momentum_bear']
        )
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Generate entry signals with balanced risk"""
        
        # Volatility filter (allow moderate volatility)
        volatility_ok = dataframe['atr_pct'] <= self.volatility_threshold.value
        
        # Long entry conditions
        long_entry = (
            (dataframe['bull_signals'] >= self.min_signals_required.value) &
            (dataframe['bear_signals'] <= 1) &  # Allow 1 conflicting signal
            volatility_ok &
            dataframe['trend_up'] &
            (dataframe['volume_ratio'] > 1.0) &
            (dataframe['bb_position'] < 0.8)  # Not at top of range
        )
        
        # Short entry conditions
        short_entry = (
            (dataframe['bear_signals'] >= self.min_signals_required.value) &
            (dataframe['bull_signals'] <= 1) &  # Allow 1 conflicting signal
            volatility_ok &
            dataframe['trend_down'] &
            (dataframe['volume_ratio'] > 1.0) &
            (dataframe['bb_position'] > 0.2)  # Not at bottom of range
        )
        
        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[short_entry, 'enter_short'] = 1
        
        # Tags for analysis
        dataframe.loc[long_entry, 'enter_tag'] = (
            'bal_long_' + dataframe['bull_signals'].astype(str) + 'sig'
        )
        dataframe.loc[short_entry, 'enter_tag'] = (
            'bal_short_' + dataframe['bear_signals'].astype(str) + 'sig'
        )
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Quick exits on reversal"""
        
        # Exit long conditions
        exit_long = (
            (dataframe['bear_signals'] >= 2) |  # Multiple bear signals
            (dataframe['rsi'] > 75) |  # Overbought
            (dataframe['bb_position'] > 0.95) |  # At upper band
            (~dataframe['trend_up'])  # Trend changed
        )
        
        # Exit short conditions
        exit_short = (
            (dataframe['bull_signals'] >= 2) |  # Multiple bull signals
            (dataframe['rsi'] < 25) |  # Oversold
            (dataframe['bb_position'] < 0.05) |  # At lower band
            (~dataframe['trend_down'])  # Trend changed
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'bal_exit_reversal'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'bal_exit_reversal'
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """Dynamic stop loss"""
        
        # Move to breakeven after 0.5% profit
        if current_profit > 0.005:
            return -0.001  # 0.1% trailing stop
        
        # Tighter stop if losing
        if current_profit < -0.008:
            return -0.005  # 0.5% stop
        
        return self.stoploss
    
    def leverage(self, pair: str, current_time, current_rate: float, 
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                 side: str, **kwargs) -> float:
        """No leverage until proven profitable"""
        return 1.0