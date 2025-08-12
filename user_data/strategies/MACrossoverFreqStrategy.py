# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these imports ---
import numpy as np
import pandas as pd
from datetime import datetime
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


class MACrossoverFreqStrategy(IStrategy):
    """
    Moving Average Crossover Strategy - Adapted from your original strategy
    Generates signals on EMA crossovers with relaxed parameters for high signal generation.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for quick exits
    minimal_roi = {
        "0": 0.015,   # 1.5% profit target
        "10": 0.01,   # 1% after 10 minutes
        "20": 0.005,  # 0.5% after 20 minutes
        "30": 0      # Break even after 30 minutes
    }
    
    # Optimal stoploss
    stoploss = -0.02  # 2% stop loss
    
    # Trailing stop loss
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    trailing_only_offset_is_reached = True
    
    # Optimal timeframe for the strategy
    timeframe = '5m'
    
    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True
    
    # These values can be overridden in the config
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30
    
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
    
    # Hyperoptable parameters - adapted from your original strategy
    fast_ema_period = IntParameter(3, 15, default=5, space="buy", optimize=True)
    slow_ema_period = IntParameter(10, 30, default=10, space="buy", optimize=True)
    min_separation = RealParameter(0.0001, 0.002, default=0.0005, space="buy", optimize=True)
    volume_threshold = RealParameter(0.5, 2.0, default=0.7, space="buy", optimize=True)
    trend_confirmation = BooleanParameter(default=True, space="buy", optimize=True)
    
    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        """
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # Calculate EMAs
        dataframe[f'ema_{self.fast_ema_period.value}'] = ta.EMA(dataframe, timeperiod=self.fast_ema_period.value)
        dataframe[f'ema_{self.slow_ema_period.value}'] = ta.EMA(dataframe, timeperiod=self.slow_ema_period.value)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # ATR for dynamic stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Additional indicators for trend confirmation
        if self.trend_confirmation.value:
            dataframe['adx'] = ta.ADX(dataframe)
            
        # Calculate EMA separation
        dataframe['ema_separation'] = abs(dataframe[f'ema_{self.fast_ema_period.value}'] - 
                                         dataframe[f'ema_{self.slow_ema_period.value}']) / \
                                         dataframe[f'ema_{self.slow_ema_period.value}']
        
        # Trend strength indicators
        dataframe['ema_fast_trend'] = dataframe[f'ema_{self.fast_ema_period.value}'].pct_change(periods=3)
        dataframe['ema_slow_trend'] = dataframe[f'ema_{self.slow_ema_period.value}'].pct_change(periods=3)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        conditions_long = []
        conditions_short = []
        
        # Bullish crossover conditions (fast EMA crosses above slow EMA)
        conditions_long.append(
            qtpylib.crossed_above(
                dataframe[f'ema_{self.fast_ema_period.value}'], 
                dataframe[f'ema_{self.slow_ema_period.value}']
            )
        )
        
        # Minimum separation check
        conditions_long.append(
            dataframe['ema_separation'] > self.min_separation.value
        )
        
        # Volume confirmation
        conditions_long.append(
            dataframe['volume_ratio'] > self.volume_threshold.value
        )
        
        # Optional trend confirmation
        if self.trend_confirmation.value:
            conditions_long.append(
                (dataframe['ema_fast_trend'] > -0.001) &  # Fast EMA not declining strongly
                (dataframe['ema_slow_trend'] > -0.001)    # Slow EMA not declining strongly
            )
        
        # Basic sanity check
        conditions_long.append(dataframe['volume'] > 0)
        
        # Combine all long conditions
        if conditions_long:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_long),
                'enter_long'] = 1
        
        # Bearish crossover conditions (fast EMA crosses below slow EMA)
        conditions_short.append(
            qtpylib.crossed_below(
                dataframe[f'ema_{self.fast_ema_period.value}'],
                dataframe[f'ema_{self.slow_ema_period.value}']
            )
        )
        
        # Minimum separation check
        conditions_short.append(
            dataframe['ema_separation'] > self.min_separation.value
        )
        
        # Volume confirmation
        conditions_short.append(
            dataframe['volume_ratio'] > self.volume_threshold.value
        )
        
        # Optional trend confirmation for shorts
        if self.trend_confirmation.value:
            conditions_short.append(
                (dataframe['ema_fast_trend'] < 0.001) &  # Fast EMA not rising strongly
                (dataframe['ema_slow_trend'] < 0.001)    # Slow EMA not rising strongly
            )
        
        # Basic sanity check
        conditions_short.append(dataframe['volume'] > 0)
        
        # Combine all short conditions
        if conditions_short:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_short),
                'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Exit long when opposite crossover happens
        dataframe.loc[
            (
                qtpylib.crossed_below(
                    dataframe[f'ema_{self.fast_ema_period.value}'],
                    dataframe[f'ema_{self.slow_ema_period.value}']
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        # Exit short when opposite crossover happens
        dataframe.loc[
            (
                qtpylib.crossed_above(
                    dataframe[f'ema_{self.fast_ema_period.value}'],
                    dataframe[f'ema_{self.slow_ema_period.value}']
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Custom stoploss logic - uses ATR for dynamic stops
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            atr = last_candle['atr']
            
            # Dynamic stop loss based on ATR
            if current_profit > 0.01:
                # If we're in profit, tighten the stop
                return -0.005  # 0.5% stop
            else:
                # Use ATR-based stop (2x ATR)
                return -(atr / current_rate) * 2
        
        # Fallback to default stoploss
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for more control
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Exit if EMAs are converging (signal weakening)
            if last_candle['ema_separation'] < self.min_separation.value / 2:
                if current_profit > 0:
                    return "ema_convergence"
            
            # Exit if volume drops significantly
            if last_candle['volume_ratio'] < 0.5 and current_profit > 0:
                return "low_volume"
        
        return None
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Customize leverage for each new trade. This method is only called in futures mode.
        """
        return 1.0  # No leverage for now
    
    plot_config = {
        "main_plot": {
            "ema_5": {"color": "blue"},
            "ema_10": {"color": "red"},
        },
        "subplots": {
            "Volume Ratio": {
                "volume_ratio": {"color": "yellow"}
            },
            "EMA Separation": {
                "ema_separation": {"color": "green"}
            }
        }
    }


from functools import reduce