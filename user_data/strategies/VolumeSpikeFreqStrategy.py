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


class VolumeSpikeFreqStrategy(IStrategy):
    """
    Volume Spike Strategy - Adapted from your original strategy
    Generates signals on significant volume increases with price momentum.
    Designed to catch breakouts and strong moves.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for momentum trades
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
        "entry": "market",  # Market orders for volume spikes
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
    volume_spike_factor = RealParameter(1.5, 5.0, default=2.0, space="buy", optimize=True)
    price_change_min = RealParameter(0.001, 0.01, default=0.003, space="buy", optimize=True)
    momentum_period = IntParameter(5, 20, default=10, space="buy", optimize=True)
    volume_ma_period = IntParameter(10, 50, default=20, space="buy", optimize=True)
    rsi_filter = BooleanParameter(default=True, space="buy", optimize=True)
    rsi_min = IntParameter(30, 50, default=40, space="buy", optimize=True)
    rsi_max = IntParameter(50, 70, default=60, space="buy", optimize=True)
    
    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        """
        return []
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # Volume analysis
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=self.volume_ma_period.value).mean()
        dataframe['volume_spike'] = dataframe['volume'] / dataframe['volume_ma']
        
        # Price momentum
        dataframe['momentum'] = ta.MOM(dataframe, timeperiod=self.momentum_period.value)
        dataframe['momentum_pct'] = dataframe['momentum'] / dataframe['close'].shift(self.momentum_period.value)
        
        # Price change
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['price_change_5'] = dataframe['close'].pct_change(periods=5)
        
        # RSI for filtering
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # ATR for stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Bollinger Bands for context
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # VWAP approximation
        dataframe['vwap'] = (dataframe['volume'] * (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3).cumsum() / dataframe['volume'].cumsum()
        
        # Candle patterns
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_pct'] = dataframe['body'] / dataframe['open']
        dataframe['green_candle'] = dataframe['close'] > dataframe['open']
        dataframe['red_candle'] = dataframe['close'] < dataframe['open']
        
        # Volume profile
        dataframe['volume_positive'] = dataframe['volume'].where(dataframe['green_candle'], 0)
        dataframe['volume_negative'] = dataframe['volume'].where(dataframe['red_candle'], 0)
        dataframe['volume_delta'] = dataframe['volume_positive'].rolling(window=10).sum() - dataframe['volume_negative'].rolling(window=10).sum()
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        conditions_long = []
        conditions_short = []
        
        # Long conditions - Bullish volume spike
        # 1. Volume spike detection
        conditions_long.append(
            dataframe['volume_spike'] > self.volume_spike_factor.value
        )
        
        # 2. Price must be moving up
        conditions_long.append(
            (dataframe['price_change'] > self.price_change_min.value) &
            (dataframe['green_candle'] == True)
        )
        
        # 3. Momentum confirmation
        conditions_long.append(
            dataframe['momentum_pct'] > 0
        )
        
        # 4. Optional RSI filter
        if self.rsi_filter.value:
            conditions_long.append(
                (dataframe['rsi'] > self.rsi_min.value) &
                (dataframe['rsi'] < 70)  # Not overbought
            )
        
        # 5. Volume delta positive (more buying volume)
        conditions_long.append(
            dataframe['volume_delta'] > 0
        )
        
        # 6. Basic sanity check
        conditions_long.append(dataframe['volume'] > 0)
        
        # Combine all long conditions
        if conditions_long:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions_long),
                'enter_long'] = 1
        
        # Short conditions - Bearish volume spike
        # 1. Volume spike detection
        conditions_short.append(
            dataframe['volume_spike'] > self.volume_spike_factor.value
        )
        
        # 2. Price must be moving down
        conditions_short.append(
            (dataframe['price_change'] < -self.price_change_min.value) &
            (dataframe['red_candle'] == True)
        )
        
        # 3. Momentum confirmation
        conditions_short.append(
            dataframe['momentum_pct'] < 0
        )
        
        # 4. Optional RSI filter
        if self.rsi_filter.value:
            conditions_short.append(
                (dataframe['rsi'] < self.rsi_max.value) &
                (dataframe['rsi'] > 30)  # Not oversold
            )
        
        # 5. Volume delta negative (more selling volume)
        conditions_short.append(
            dataframe['volume_delta'] < 0
        )
        
        # 6. Basic sanity check
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
        # Exit long when momentum reverses or volume dries up
        dataframe.loc[
            (
                (
                    (dataframe['momentum_pct'] < -0.002) |  # Momentum reversal
                    (dataframe['volume_spike'] < 0.5)      # Volume drying up
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        # Exit short when momentum reverses or volume dries up
        dataframe.loc[
            (
                (
                    (dataframe['momentum_pct'] > 0.002) |   # Momentum reversal
                    (dataframe['volume_spike'] < 0.5)       # Volume drying up
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Custom stoploss logic - tighter stops for volume spike trades
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            atr = last_candle['atr']
            
            # Volume spike trades should have tighter stops
            if current_profit > 0.02:
                # Lock in profits
                return -0.005  # 0.5% stop
            elif current_profit > 0.01:
                # Tighten stop
                return -0.01   # 1% stop
            else:
                # Use ATR-based stop (1.5x ATR)
                return -(atr / current_rate) * 1.5
        
        # Fallback to default stoploss
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for volume spike trades
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Exit if volume spike has completely reversed
            if last_candle['volume_spike'] < 0.3:
                if current_profit > 0:
                    return "volume_exhaustion"
            
            # Exit if momentum has strongly reversed
            if trade.is_short == False:
                if last_candle['momentum_pct'] < -0.005 and current_profit > 0:
                    return "momentum_reversal_long"
            else:
                if last_candle['momentum_pct'] > 0.005 and current_profit > 0:
                    return "momentum_reversal_short"
            
            # Exit on extreme RSI
            if last_candle['rsi'] > 80 and trade.is_short == False:
                return "rsi_extreme_overbought"
            elif last_candle['rsi'] < 20 and trade.is_short == True:
                return "rsi_extreme_oversold"
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """
        Additional confirmation for trade entry
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Don't enter if volume spike is already fading
            if last_candle['volume_spike'] < self.volume_spike_factor.value * 0.8:
                return False
            
            # Don't enter if price has moved too much already
            if abs(last_candle['price_change_5']) > 0.02:  # 2% in 5 candles
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
            "bb_lowerband": {"color": "grey"},
            "bb_middleband": {"color": "grey", "type": "line"},
            "bb_upperband": {"color": "grey"},
            "vwap": {"color": "purple"}
        },
        "subplots": {
            "Volume Spike": {
                "volume_spike": {"color": "yellow"}
            },
            "Momentum": {
                "momentum_pct": {"color": "blue"}
            },
            "RSI": {
                "rsi": {"color": "red"}
            }
        }
    }


from functools import reduce