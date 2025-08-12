# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Optional, Union

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
)

import talib.abstract as ta
from technical import qtpylib


class HighFrequencyStrategy(IStrategy):
    """
    High-frequency trading strategy optimized for speed and profitability.
    Combines multiple proven strategies with ultra-fast execution.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = False
    
    # Minimal ROI designed for quick profits
    minimal_roi = {
        "0": 0.02,    # 2% profit target
        "10": 0.015,  # 1.5% after 10 minutes
        "20": 0.01,   # 1% after 20 minutes
        "30": 0.005,  # 0.5% after 30 minutes
        "60": 0      # Break even after 60 minutes
    }
    
    # Optimal stoploss
    stoploss = -0.02  # 2% stop loss
    
    # Trailing stop loss
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    trailing_only_offset_is_reached = True
    
    # Optimal timeframe for high-frequency trading
    timeframe = '1m'
    
    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True
    
    # These values can be overridden in the config
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 100
    
    # Optional order type mapping
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True
    }
    
    # Optional order time in force
    order_time_in_force = {
        "entry": "IOC",  # Immediate or Cancel for fast execution
        "exit": "IOC"
    }
    
    # Hyperoptable parameters
    # MA Crossover parameters
    fast_ma_period = IntParameter(5, 20, default=8, space="buy", optimize=True)
    slow_ma_period = IntParameter(20, 50, default=21, space="buy", optimize=True)
    
    # RSI parameters
    rsi_period = IntParameter(7, 21, default=14, space="buy", optimize=True)
    rsi_buy = IntParameter(20, 40, default=30, space="buy", optimize=True)
    rsi_sell = IntParameter(60, 80, default=70, space="sell", optimize=True)
    
    # Volume spike parameters
    volume_spike_factor = RealParameter(1.5, 5.0, default=2.0, space="buy", optimize=True)
    
    # Momentum parameters
    momentum_period = IntParameter(10, 30, default=20, space="buy", optimize=True)
    
    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        """
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, '5m') for pair in pairs]
        informative_pairs += [(pair, '15m') for pair in pairs]
        return informative_pairs
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # Moving Averages (for MA crossover strategy)
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.fast_ma_period.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.slow_ma_period.value)
        dataframe['sma_20'] = ta.SMA(dataframe, timeperiod=20)
        
        # RSI (for RSI bounce strategy)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_percent'] = (dataframe['close'] - dataframe['bb_lowerband']) / (dataframe['bb_upperband'] - dataframe['bb_lowerband'])
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # Volume indicators
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=30).mean()
        dataframe['volume_spike'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Momentum
        dataframe['momentum'] = ta.MOM(dataframe, timeperiod=self.momentum_period.value)
        
        # Support and Resistance levels
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Price patterns (for engulfing strategy)
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_prev'] = dataframe['body'].shift(1)
        dataframe['bullish_engulfing'] = (
            (dataframe['close'] > dataframe['open']) &  # Current candle is green
            (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &  # Previous candle is red
            (dataframe['open'] < dataframe['close'].shift(1)) &  # Current open is below previous close
            (dataframe['close'] > dataframe['open'].shift(1)) &  # Current close is above previous open
            (dataframe['body'] > dataframe['body_prev'])  # Current body is larger
        )
        dataframe['bearish_engulfing'] = (
            (dataframe['close'] < dataframe['open']) &  # Current candle is red
            (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &  # Previous candle is green
            (dataframe['open'] > dataframe['close'].shift(1)) &  # Current open is above previous close
            (dataframe['close'] < dataframe['open'].shift(1)) &  # Current close is below previous open
            (dataframe['body'] > dataframe['body_prev'])  # Current body is larger
        )
        
        # ATR for volatility-based stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe)
        
        # Stochastic Fast
        stoch_fast = ta.STOCHF(dataframe)
        dataframe['fastd'] = stoch_fast['fastd']
        dataframe['fastk'] = stoch_fast['fastk']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        conditions = []
        
        # MA Crossover Strategy
        conditions.append(
            qtpylib.crossed_above(dataframe['ema_fast'], dataframe['ema_slow']) &
            (dataframe['volume'] > 0)
        )
        
        # RSI Bounce Strategy
        conditions.append(
            (dataframe['rsi'] < self.rsi_buy.value) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &  # RSI starting to rise
            (dataframe['close'] > dataframe['bb_lowerband']) &
            (dataframe['volume'] > 0)
        )
        
        # Volume Spike Strategy
        conditions.append(
            (dataframe['volume_spike'] > self.volume_spike_factor.value) &
            (dataframe['close'] > dataframe['open']) &  # Green candle
            (dataframe['momentum'] > 0) &
            (dataframe['volume'] > 0)
        )
        
        # Bollinger Band Bounce
        conditions.append(
            (dataframe['close'] < dataframe['bb_lowerband']) &
            (dataframe['rsi'] < 30) &
            (dataframe['volume'] > 0)
        )
        
        # Bullish Engulfing Pattern
        conditions.append(
            (dataframe['bullish_engulfing']) &
            (dataframe['rsi'] < 50) &
            (dataframe['volume'] > dataframe['volume_mean'])
        )
        
        # MACD Cross
        conditions.append(
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
            (dataframe['adx'] > 25) &  # Ensure we're in a trend
            (dataframe['volume'] > 0)
        )
        
        # Combine all conditions with OR logic
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, conditions),
                'enter_long'] = 1
        
        # Short conditions
        short_conditions = []
        
        # MA Crossover (bearish)
        short_conditions.append(
            qtpylib.crossed_below(dataframe['ema_fast'], dataframe['ema_slow']) &
            (dataframe['volume'] > 0)
        )
        
        # RSI Overbought
        short_conditions.append(
            (dataframe['rsi'] > self.rsi_sell.value) &
            (dataframe['rsi'] < dataframe['rsi'].shift(1)) &  # RSI starting to fall
            (dataframe['close'] < dataframe['bb_upperband']) &
            (dataframe['volume'] > 0)
        )
        
        # Bearish Engulfing Pattern
        short_conditions.append(
            (dataframe['bearish_engulfing']) &
            (dataframe['rsi'] > 50) &
            (dataframe['volume'] > dataframe['volume_mean'])
        )
        
        if short_conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, short_conditions),
                'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Exit long conditions
        exit_long_conditions = []
        
        # Take profit at resistance
        exit_long_conditions.append(
            (dataframe['close'] >= dataframe['resistance'] * 0.99)
        )
        
        # RSI overbought
        exit_long_conditions.append(
            (dataframe['rsi'] > self.rsi_sell.value)
        )
        
        # MA crossover bearish
        exit_long_conditions.append(
            qtpylib.crossed_below(dataframe['ema_fast'], dataframe['ema_slow'])
        )
        
        # MACD bearish cross
        exit_long_conditions.append(
            qtpylib.crossed_below(dataframe['macd'], dataframe['macdsignal'])
        )
        
        if exit_long_conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, exit_long_conditions),
                'exit_long'] = 1
        
        # Exit short conditions
        exit_short_conditions = []
        
        # Take profit at support
        exit_short_conditions.append(
            (dataframe['close'] <= dataframe['support'] * 1.01)
        )
        
        # RSI oversold
        exit_short_conditions.append(
            (dataframe['rsi'] < self.rsi_buy.value)
        )
        
        # MA crossover bullish
        exit_short_conditions.append(
            qtpylib.crossed_above(dataframe['ema_fast'], dataframe['ema_slow'])
        )
        
        # MACD bullish cross
        exit_short_conditions.append(
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])
        )
        
        if exit_short_conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, exit_short_conditions),
                'exit_short'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Custom stoploss logic - implements dynamic stop loss based on ATR
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            atr = last_candle['atr']
            
            # Dynamic stop loss based on ATR
            if current_profit > 0.02:
                # If we're in good profit, tighten the stop
                return -0.01
            elif current_profit > 0.01:
                # Moderate profit, use ATR-based stop
                return -(atr / current_rate) * 1.5
            else:
                # Normal ATR-based stop
                return -(atr / current_rate) * 2
        
        # Fallback to default stoploss
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for more control
        """
        # Exit if trade has been open too long and in small profit
        if current_time - trade.open_date_utc.replace(tzinfo=timezone.utc) > timedelta(hours=2):
            if current_profit > 0.001:
                return "exit_trade_duration"
        
        # Exit if momentum is reversing
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # For long trades
            if trade.is_short == False:
                if last_candle['momentum'] < 0 and current_profit > 0:
                    return "exit_momentum_reversal"
            # For short trades
            else:
                if last_candle['momentum'] > 0 and current_profit > 0:
                    return "exit_momentum_reversal"
        
        return None
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Customize leverage for each new trade. This method is only called in futures mode.
        """
        # Use lower leverage for more volatile pairs
        return 2.0  # Conservative leverage for now
    
    plot_config = {
        "main_plot": {
            "ema_fast": {"color": "blue"},
            "ema_slow": {"color": "red"},
            "bb_lowerband": {"color": "grey"},
            "bb_upperband": {"color": "grey"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "red"},
            },
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
            "Volume": {
                "volume_spike": {"color": "yellow"}
            }
        }
    }


from functools import reduce