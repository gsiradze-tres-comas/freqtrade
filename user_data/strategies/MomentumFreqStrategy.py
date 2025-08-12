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


class MomentumFreqStrategy(IStrategy):
    """
    Momentum Strategy - Adapted from your original strategy
    Generates signals based on price movement and RSI conditions.
    Designed for catching strong directional moves.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for momentum trades
    minimal_roi = {
        "0": 0.03,    # 3% profit target
        "15": 0.02,   # 2% after 15 minutes
        "30": 0.015,  # 1.5% after 30 minutes
        "45": 0.01,   # 1% after 45 minutes
        "60": 0.005,  # 0.5% after 60 minutes
        "90": 0      # Break even after 90 minutes
    }
    
    # Optimal stoploss
    stoploss = -0.025  # 2.5% stop loss
    
    # Trailing stop loss
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
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
    startup_candle_count: int = 50
    
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
    price_change_threshold = RealParameter(0.001, 0.005, default=0.002, space="buy", optimize=True)
    rsi_oversold = IntParameter(20, 40, default=30, space="buy", optimize=True)
    rsi_overbought = IntParameter(60, 80, default=70, space="sell", optimize=True)
    volume_threshold = RealParameter(1.0, 2.0, default=1.2, space="buy", optimize=True)
    momentum_period = IntParameter(10, 30, default=20, space="buy", optimize=True)
    ema_period = IntParameter(20, 50, default=30, space="buy", optimize=True)
    adx_threshold = IntParameter(20, 40, default=25, space="buy", optimize=True)
    
    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        """
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # Price change
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['price_change_abs'] = abs(dataframe['price_change'])
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # EMA
        dataframe[f'ema_{self.ema_period.value}'] = ta.EMA(dataframe, timeperiod=self.ema_period.value)
        dataframe['price_above_ema'] = dataframe['close'] > dataframe[f'ema_{self.ema_period.value}']
        dataframe['price_below_ema'] = dataframe['close'] < dataframe[f'ema_{self.ema_period.value}']
        
        # Momentum indicators
        dataframe['momentum'] = ta.MOM(dataframe, timeperiod=self.momentum_period.value)
        dataframe['momentum_pct'] = dataframe['momentum'] / dataframe['close'].shift(self.momentum_period.value)
        dataframe['roc'] = ta.ROC(dataframe, timeperiod=self.momentum_period.value)
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
        
        # MACD for momentum confirmation
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Stochastic for momentum
        stoch = ta.STOCH(dataframe)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # Candle patterns
        dataframe['green_candle'] = dataframe['close'] > dataframe['open']
        dataframe['red_candle'] = dataframe['close'] < dataframe['open']
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_pct'] = dataframe['body'] / dataframe['open']
        
        # Consecutive candles
        dataframe['consecutive_green'] = dataframe['green_candle'].rolling(window=3).sum()
        dataframe['consecutive_red'] = dataframe['red_candle'].rolling(window=3).sum()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        # Bullish momentum conditions
        dataframe.loc[
            (
                # Strong positive price movement
                (dataframe['price_change'] > self.price_change_threshold.value) &
                # RSI not overbought but rising
                (dataframe['rsi'] > self.rsi_oversold.value) &
                (dataframe['rsi'] < self.rsi_overbought.value) &
                (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
                # Volume confirmation
                (dataframe['volume_ratio'] > self.volume_threshold.value) &
                # Price above EMA (uptrend)
                (dataframe['price_above_ema'] == True) &
                # ADX shows trending market
                (dataframe['adx'] > self.adx_threshold.value) &
                # Positive momentum
                (dataframe['momentum_pct'] > 0.001) &
                # MACD confirmation
                (dataframe['macdhist'] > 0) &
                # DI+ > DI- (bullish trend)
                (dataframe['plus_di'] > dataframe['minus_di']) &
                # Basic sanity check
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1
        
        # Alternative bullish entry - Strong momentum burst
        dataframe.loc[
            (
                # Very strong momentum
                (dataframe['momentum_pct'] > 0.005) &
                # Multiple green candles
                (dataframe['consecutive_green'] >= 2) &
                # Not overbought
                (dataframe['rsi'] < 65) &
                # Volume spike
                (dataframe['volume_ratio'] > 1.5) &
                # Trending market
                (dataframe['adx'] > 20) &
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1
        
        # Bearish momentum conditions
        dataframe.loc[
            (
                # Strong negative price movement
                (dataframe['price_change'] < -self.price_change_threshold.value) &
                # RSI not oversold but falling
                (dataframe['rsi'] < self.rsi_overbought.value) &
                (dataframe['rsi'] > self.rsi_oversold.value) &
                (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
                # Volume confirmation
                (dataframe['volume_ratio'] > self.volume_threshold.value) &
                # Price below EMA (downtrend)
                (dataframe['price_below_ema'] == True) &
                # ADX shows trending market
                (dataframe['adx'] > self.adx_threshold.value) &
                # Negative momentum
                (dataframe['momentum_pct'] < -0.001) &
                # MACD confirmation
                (dataframe['macdhist'] < 0) &
                # DI- > DI+ (bearish trend)
                (dataframe['minus_di'] > dataframe['plus_di']) &
                # Basic sanity check
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1
        
        # Alternative bearish entry - Strong momentum burst
        dataframe.loc[
            (
                # Very strong negative momentum
                (dataframe['momentum_pct'] < -0.005) &
                # Multiple red candles
                (dataframe['consecutive_red'] >= 2) &
                # Not oversold
                (dataframe['rsi'] > 35) &
                # Volume spike
                (dataframe['volume_ratio'] > 1.5) &
                # Trending market
                (dataframe['adx'] > 20) &
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Exit long when momentum weakens
        dataframe.loc[
            (
                (
                    # Momentum reversal
                    (dataframe['momentum_pct'] < -0.001) |
                    # RSI overbought
                    (dataframe['rsi'] > self.rsi_overbought.value) |
                    # MACD bearish cross
                    (qtpylib.crossed_below(dataframe['macd'], dataframe['macdsignal'])) |
                    # Price crosses below EMA
                    (qtpylib.crossed_below(dataframe['close'], dataframe[f'ema_{self.ema_period.value}']))
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        # Exit short when momentum weakens
        dataframe.loc[
            (
                (
                    # Momentum reversal
                    (dataframe['momentum_pct'] > 0.001) |
                    # RSI oversold
                    (dataframe['rsi'] < self.rsi_oversold.value) |
                    # MACD bullish cross
                    (qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])) |
                    # Price crosses above EMA
                    (qtpylib.crossed_above(dataframe['close'], dataframe[f'ema_{self.ema_period.value}']))
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Custom stoploss logic - dynamic based on momentum strength
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            atr = last_candle['atr']
            momentum = abs(last_candle['momentum_pct'])
            
            # Tighter stops for strong momentum trades
            if momentum > 0.01:  # Very strong momentum
                if current_profit > 0.02:
                    return -0.005  # 0.5% stop
                elif current_profit > 0.01:
                    return -0.01   # 1% stop
                else:
                    return -(atr / current_rate) * 1.5
            else:
                # Normal momentum
                if current_profit > 0.015:
                    return -0.007  # 0.7% stop
                else:
                    return -(atr / current_rate) * 2
        
        # Fallback to default stoploss
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for momentum trades
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Exit if momentum has completely reversed
            if trade.is_short == False:
                if last_candle['momentum_pct'] < -0.003 and current_profit > 0:
                    return "momentum_exhaustion_long"
                # Exit if trend structure breaks
                if last_candle['minus_di'] > last_candle['plus_di'] and current_profit > 0.005:
                    return "trend_reversal_long"
            else:
                if last_candle['momentum_pct'] > 0.003 and current_profit > 0:
                    return "momentum_exhaustion_short"
                # Exit if trend structure breaks
                if last_candle['plus_di'] > last_candle['minus_di'] and current_profit > 0.005:
                    return "trend_reversal_short"
            
            # Exit if ADX drops (trend weakening)
            if last_candle['adx'] < 20 and current_profit > 0:
                return "trend_weakness"
            
            # Exit on extreme stochastic
            if last_candle['slowk'] > 90 and trade.is_short == False:
                return "stoch_overbought"
            elif last_candle['slowk'] < 10 and trade.is_short == True:
                return "stoch_oversold"
        
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
            f"ema_30": {"color": "blue"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "red"},
            },
            "MACD": {
                "macd": {"color": "blue"},
                "macdsignal": {"color": "orange"},
            },
            "ADX": {
                "adx": {"color": "purple"},
                "plus_di": {"color": "green"},
                "minus_di": {"color": "red"}
            },
            "Momentum": {
                "momentum_pct": {"color": "cyan"}
            }
        }
    }


from functools import reduce