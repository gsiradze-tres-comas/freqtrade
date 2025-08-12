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


class EngulfingFreqStrategy(IStrategy):
    """
    Engulfing Pattern Strategy - Adapted from your original strategy
    Identifies bullish and bearish engulfing patterns with volume and RSI confirmation.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for pattern trades
    minimal_roi = {
        "0": 0.025,   # 2.5% profit target
        "10": 0.02,   # 2% after 10 minutes
        "20": 0.015,  # 1.5% after 20 minutes
        "30": 0.01,   # 1% after 30 minutes
        "45": 0.005,  # 0.5% after 45 minutes
        "60": 0      # Break even after 60 minutes
    }
    
    # Optimal stoploss
    stoploss = -0.02  # 2% stop loss
    
    # Trailing stop loss
    trailing_stop = True
    trailing_stop_positive = 0.008
    trailing_stop_positive_offset = 0.012
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
        "entry": "GTC",
        "exit": "GTC"
    }
    
    # Hyperoptable parameters
    min_body_ratio = RealParameter(0.4, 0.8, default=0.6, space="buy", optimize=True)
    volume_multiplier = RealParameter(1.2, 2.5, default=1.5, space="buy", optimize=True)
    rsi_min = IntParameter(25, 40, default=30, space="buy", optimize=True)
    rsi_max = IntParameter(60, 75, default=70, space="sell", optimize=True)
    ema_period = IntParameter(15, 30, default=20, space="buy", optimize=True)
    body_size_min = RealParameter(0.001, 0.01, default=0.003, space="buy", optimize=True)
    
    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        """
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # EMA
        dataframe[f'ema_{self.ema_period.value}'] = ta.EMA(dataframe, timeperiod=self.ema_period.value)
        
        # Volume analysis
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=10).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Candle body analysis
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_pct'] = dataframe['body'] / dataframe['open']
        dataframe['upper_shadow'] = dataframe['high'] - np.maximum(dataframe['close'], dataframe['open'])
        dataframe['lower_shadow'] = np.minimum(dataframe['close'], dataframe['open']) - dataframe['low']
        dataframe['candle_range'] = dataframe['high'] - dataframe['low']
        dataframe['body_ratio'] = dataframe['body'] / dataframe['candle_range']
        
        # Candle types
        dataframe['is_green'] = dataframe['close'] > dataframe['open']
        dataframe['is_red'] = dataframe['close'] < dataframe['open']
        
        # Previous candle data for engulfing detection
        dataframe['prev_open'] = dataframe['open'].shift(1)
        dataframe['prev_close'] = dataframe['close'].shift(1)
        dataframe['prev_high'] = dataframe['high'].shift(1)
        dataframe['prev_low'] = dataframe['low'].shift(1)
        dataframe['prev_body'] = dataframe['body'].shift(1)
        dataframe['prev_is_green'] = dataframe['is_green'].shift(1)
        dataframe['prev_is_red'] = dataframe['is_red'].shift(1)
        
        # Engulfing pattern detection
        dataframe['bullish_engulfing'] = (
            # Current candle is green
            (dataframe['is_green'] == True) &
            # Previous candle is red
            (dataframe['prev_is_red'] == True) &
            # Current open is below previous close
            (dataframe['open'] < dataframe['prev_close']) &
            # Current close is above previous open
            (dataframe['close'] > dataframe['prev_open']) &
            # Current body is larger than previous body
            (dataframe['body'] > dataframe['prev_body']) &
            # Minimum body size
            (dataframe['body_pct'] > self.body_size_min.value) &
            # Body ratio requirement
            (dataframe['body_ratio'] > self.min_body_ratio.value)
        )
        
        dataframe['bearish_engulfing'] = (
            # Current candle is red
            (dataframe['is_red'] == True) &
            # Previous candle is green
            (dataframe['prev_is_green'] == True) &
            # Current open is above previous close
            (dataframe['open'] > dataframe['prev_close']) &
            # Current close is below previous open
            (dataframe['close'] < dataframe['prev_open']) &
            # Current body is larger than previous body
            (dataframe['body'] > dataframe['prev_body']) &
            # Minimum body size
            (dataframe['body_pct'] > self.body_size_min.value) &
            # Body ratio requirement
            (dataframe['body_ratio'] > self.min_body_ratio.value)
        )
        
        # ATR for stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Support and resistance levels
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        
        # MACD for trend context
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        # Bullish engulfing conditions
        dataframe.loc[
            (
                # Bullish engulfing pattern detected
                (dataframe['bullish_engulfing'] == True) &
                # RSI not overbought
                (dataframe['rsi'] > self.rsi_min.value) &
                (dataframe['rsi'] < self.rsi_max.value) &
                # Volume confirmation
                (dataframe['volume_ratio'] > self.volume_multiplier.value) &
                # Price context - near support or above EMA
                (
                    (dataframe['close'] > dataframe[f'ema_{self.ema_period.value}']) |
                    (dataframe['close'] < dataframe['support'] * 1.02)  # Within 2% of support
                ) &
                # MACD context (optional trend confirmation)
                (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) &  # MACD histogram improving
                # Basic sanity check
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1
        
        # Bearish engulfing conditions
        dataframe.loc[
            (
                # Bearish engulfing pattern detected
                (dataframe['bearish_engulfing'] == True) &
                # RSI not oversold
                (dataframe['rsi'] < self.rsi_max.value) &
                (dataframe['rsi'] > self.rsi_min.value) &
                # Volume confirmation
                (dataframe['volume_ratio'] > self.volume_multiplier.value) &
                # Price context - near resistance or below EMA
                (
                    (dataframe['close'] < dataframe[f'ema_{self.ema_period.value}']) |
                    (dataframe['close'] > dataframe['resistance'] * 0.98)  # Within 2% of resistance
                ) &
                # MACD context (optional trend confirmation)
                (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &  # MACD histogram deteriorating
                # Basic sanity check
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Exit long on bearish engulfing
        dataframe.loc[
            (
                (dataframe['bearish_engulfing'] == True) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        # Exit short on bullish engulfing
        dataframe.loc[
            (
                (dataframe['bullish_engulfing'] == True) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1
        
        # Exit on RSI extremes
        dataframe.loc[
            (
                (dataframe['rsi'] > 75) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        dataframe.loc[
            (
                (dataframe['rsi'] < 25) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Custom stoploss logic - based on pattern strength
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            atr = last_candle['atr']
            
            # Pattern-based stop loss
            if current_profit > 0.02:
                # Lock in profits
                return -0.005  # 0.5% stop
            elif current_profit > 0.01:
                # Tighten stop
                return -0.01   # 1% stop
            else:
                # Use ATR-based stop
                return -(atr / current_rate) * 2
        
        # Fallback to default stoploss
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for engulfing patterns
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # For long trades
            if trade.is_short == False:
                # Exit on opposite pattern with profit
                if last_candle['bearish_engulfing'] and current_profit > 0:
                    return "opposite_engulfing_pattern"
                
                # Exit if price reaches resistance
                if last_candle['close'] >= last_candle['resistance'] * 0.995 and current_profit > 0.005:
                    return "resistance_reached"
            
            # For short trades
            else:
                # Exit on opposite pattern with profit
                if last_candle['bullish_engulfing'] and current_profit > 0:
                    return "opposite_engulfing_pattern"
                
                # Exit if price reaches support
                if last_candle['close'] <= last_candle['support'] * 1.005 and current_profit > 0.005:
                    return "support_reached"
            
            # Exit if volume drops significantly after entry
            if last_candle['volume_ratio'] < 0.5 and current_profit > 0:
                return "volume_exhaustion"
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """
        Additional confirmation for engulfing pattern entries
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Don't enter if the pattern is too old (not from current candle)
            if side == "long":
                if not last_candle['bullish_engulfing']:
                    return False
            else:
                if not last_candle['bearish_engulfing']:
                    return False
            
            # Don't enter if volume is declining
            if last_candle['volume_ratio'] < self.volume_multiplier.value * 0.8:
                return False
        
        return True
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Customize leverage for each new trade. This method is only called in futures mode.
        """
        return 1.0  # No leverage for now
    
    plot_config = {
        "main_plot": {
            f"ema_20": {"color": "blue"},
            "support": {"color": "green"},
            "resistance": {"color": "red"},
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
                "volume_ratio": {"color": "yellow"}
            },
            "Patterns": {
                "bullish_engulfing": {"color": "green", "type": "scatter"},
                "bearish_engulfing": {"color": "red", "type": "scatter"}
            }
        }
    }


from functools import reduce