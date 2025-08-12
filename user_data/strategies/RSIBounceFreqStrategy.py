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


class RSIBounceFreqStrategy(IStrategy):
    """
    RSI Bounce Strategy - Adapted from your original strategy
    Generates signals when RSI bounces from oversold/overbought levels.
    Uses relaxed parameters to ensure signal generation for testing and trading.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for quick profits
    minimal_roi = {
        "0": 0.02,    # 2% profit target
        "15": 0.015,  # 1.5% after 15 minutes
        "30": 0.01,   # 1% after 30 minutes
        "45": 0.005,  # 0.5% after 45 minutes
        "60": 0      # Break even after 60 minutes
    }
    
    # Optimal stoploss
    stoploss = -0.015  # 1.5% stop loss
    
    # Trailing stop loss
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.008
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
    
    # Hyperoptable parameters - adapted from your original strategy
    rsi_period = IntParameter(7, 21, default=14, space="buy", optimize=True)
    rsi_oversold = IntParameter(25, 40, default=35, space="buy", optimize=True)
    rsi_overbought = IntParameter(60, 75, default=65, space="sell", optimize=True)
    rsi_bounce_threshold = IntParameter(2, 8, default=3, space="buy", optimize=True)
    min_volume_ratio = RealParameter(0.5, 1.5, default=0.8, space="buy", optimize=True)
    price_confirmation = RealParameter(0.0005, 0.003, default=0.001, space="buy", optimize=True)
    stop_loss_atr_multiplier = RealParameter(1.0, 2.5, default=1.5, space="sell", optimize=True)
    take_profit_atr_multiplier = RealParameter(2.0, 4.0, default=2.5, space="sell", optimize=True)
    
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
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # RSI change (for bounce detection)
        dataframe['rsi_change'] = dataframe['rsi'].diff()
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # ATR for dynamic stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Bollinger Bands for additional context
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # Price change for confirmation
        dataframe['price_change'] = dataframe['close'].pct_change()
        
        # MACD for trend context
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # RSI extremes detection
        dataframe['rsi_oversold'] = dataframe['rsi'] < self.rsi_oversold.value
        dataframe['rsi_overbought'] = dataframe['rsi'] > self.rsi_overbought.value
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        # Bullish RSI bounce conditions (from oversold)
        dataframe.loc[
            (
                # Previous RSI was oversold or close to it
                (dataframe['rsi'].shift(1) < self.rsi_oversold.value + 5) &
                # RSI is bouncing up
                (dataframe['rsi_change'] > self.rsi_bounce_threshold.value) &
                # Price confirmation (minimal requirement)
                (dataframe['price_change'] > -self.price_confirmation.value) &
                # Volume confirmation
                (dataframe['volume_ratio'] > self.min_volume_ratio.value) &
                # Optional: Price near lower Bollinger Band
                (dataframe['close'] < dataframe['bb_middleband']) &
                # Basic sanity check
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1
        
        # Bearish RSI bounce conditions (from overbought)
        dataframe.loc[
            (
                # Previous RSI was overbought or close to it
                (dataframe['rsi'].shift(1) > self.rsi_overbought.value - 5) &
                # RSI is bouncing down
                (dataframe['rsi_change'] < -self.rsi_bounce_threshold.value) &
                # Price confirmation (minimal requirement)
                (dataframe['price_change'] < self.price_confirmation.value) &
                # Volume confirmation
                (dataframe['volume_ratio'] > self.min_volume_ratio.value) &
                # Optional: Price near upper Bollinger Band
                (dataframe['close'] > dataframe['bb_middleband']) &
                # Basic sanity check
                (dataframe['volume'] > 0)
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Exit long when RSI becomes overbought
        dataframe.loc[
            (
                (dataframe['rsi'] > self.rsi_overbought.value) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        # Exit short when RSI becomes oversold
        dataframe.loc[
            (
                (dataframe['rsi'] < self.rsi_oversold.value) &
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
            if current_profit > 0.015:
                # If we're in good profit, tighten the stop
                return -0.005  # 0.5% stop
            elif current_profit > 0.005:
                # Moderate profit, use tighter ATR-based stop
                return -(atr / current_rate) * self.stop_loss_atr_multiplier.value * 0.75
            else:
                # Normal ATR-based stop
                return -(atr / current_rate) * self.stop_loss_atr_multiplier.value
        
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
            
            # For long trades
            if trade.is_short == False:
                # Exit if RSI is declining from overbought with profit
                if last_candle['rsi'] > 70 and last_candle['rsi_change'] < -2 and current_profit > 0:
                    return "rsi_reversal_from_overbought"
                
                # Exit if MACD shows bearish divergence
                if last_candle['macdhist'] < 0 and last_candle['macd'] < last_candle['macdsignal'] and current_profit > 0.005:
                    return "macd_bearish_divergence"
            
            # For short trades
            else:
                # Exit if RSI is rising from oversold with profit
                if last_candle['rsi'] < 30 and last_candle['rsi_change'] > 2 and current_profit > 0:
                    return "rsi_reversal_from_oversold"
                
                # Exit if MACD shows bullish divergence
                if last_candle['macdhist'] > 0 and last_candle['macd'] > last_candle['macdsignal'] and current_profit > 0.005:
                    return "macd_bullish_divergence"
            
            # Exit if volume drops significantly
            if last_candle['volume_ratio'] < 0.5 and current_profit > 0.002:
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
            "bb_lowerband": {"color": "grey"},
            "bb_middleband": {"color": "grey", "type": "line"},
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
                "volume_ratio": {"color": "yellow"}
            }
        }
    }