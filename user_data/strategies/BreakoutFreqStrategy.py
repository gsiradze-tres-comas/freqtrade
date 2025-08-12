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


class BreakoutFreqStrategy(IStrategy):
    """
    Breakout Strategy - Adapted from your original strategy
    Generates signals when price breaks above/below recent levels with volume confirmation.
    """
    
    # Strategy interface version
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for breakout trades
    minimal_roi = {
        "0": 0.04,    # 4% profit target for breakouts
        "15": 0.03,   # 3% after 15 minutes
        "30": 0.02,   # 2% after 30 minutes
        "45": 0.015,  # 1.5% after 45 minutes
        "60": 0.01,   # 1% after 60 minutes
        "90": 0.005,  # 0.5% after 90 minutes
        "120": 0     # Break even after 120 minutes
    }
    
    # Optimal stoploss
    stoploss = -0.03  # 3% stop loss
    
    # Trailing stop loss
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.02
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
        "entry": "market",  # Market orders for breakouts
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
    lookback_period = IntParameter(5, 25, default=10, space="buy", optimize=True)
    breakout_threshold = RealParameter(0.001, 0.005, default=0.002, space="buy", optimize=True)
    volume_confirmation = RealParameter(1.0, 2.5, default=1.1, space="buy", optimize=True)
    min_consolidation = IntParameter(3, 10, default=3, space="buy", optimize=True)
    stop_loss_atr_multiplier = RealParameter(1.5, 3.0, default=2.0, space="sell", optimize=True)
    take_profit_atr_multiplier = RealParameter(2.5, 5.0, default=3.0, space="sell", optimize=True)
    bb_breakout = BooleanParameter(default=True, space="buy", optimize=True)
    
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
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Rolling highs and lows for breakout detection
        dataframe[f'rolling_high_{self.lookback_period.value}'] = dataframe['high'].rolling(window=self.lookback_period.value).max()
        dataframe[f'rolling_low_{self.lookback_period.value}'] = dataframe['low'].rolling(window=self.lookback_period.value).min()
        
        # Consolidation detection
        dataframe['high_low_range'] = dataframe['high'] - dataframe['low']
        dataframe['range_mean'] = dataframe['high_low_range'].rolling(window=self.lookback_period.value).mean()
        dataframe['consolidation'] = dataframe['high_low_range'] < dataframe['range_mean'] * 0.7
        dataframe['consolidation_count'] = dataframe['consolidation'].rolling(window=self.lookback_period.value).sum()
        
        # Bollinger Bands for additional breakout confirmation
        if self.bb_breakout.value:
            bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
            dataframe['bb_lowerband'] = bollinger['lower']
            dataframe['bb_middleband'] = bollinger['mid']
            dataframe['bb_upperband'] = bollinger['upper']
            dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # Breakout detection
        dataframe['high_breakout'] = (
            (dataframe['close'] > dataframe[f'rolling_high_{self.lookback_period.value}'].shift(1)) &
            ((dataframe['close'] - dataframe[f'rolling_high_{self.lookback_period.value}'].shift(1)) / dataframe[f'rolling_high_{self.lookback_period.value}'].shift(1) > self.breakout_threshold.value)
        )
        
        dataframe['low_breakout'] = (
            (dataframe['close'] < dataframe[f'rolling_low_{self.lookback_period.value}'].shift(1)) &
            ((dataframe[f'rolling_low_{self.lookback_period.value}'].shift(1) - dataframe['close']) / dataframe[f'rolling_low_{self.lookback_period.value}'].shift(1) > self.breakout_threshold.value)
        )
        
        # RSI for momentum confirmation
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD for trend confirmation
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # EMA for trend context
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        # Price position relative to EMAs
        dataframe['above_ema20'] = dataframe['close'] > dataframe['ema_20']
        dataframe['above_ema50'] = dataframe['close'] > dataframe['ema_50']
        dataframe['ema_bullish'] = dataframe['ema_20'] > dataframe['ema_50']
        
        # Additional Bollinger Band breakouts
        if self.bb_breakout.value:
            dataframe['bb_upper_breakout'] = (
                (dataframe['close'] > dataframe['bb_upperband']) &
                (dataframe['bb_width'] > 0.02)  # Bands not too tight
            )
            dataframe['bb_lower_breakout'] = (
                (dataframe['close'] < dataframe['bb_lowerband']) &
                (dataframe['bb_width'] > 0.02)  # Bands not too tight
            )
        
        # Momentum indicators
        dataframe['momentum'] = ta.MOM(dataframe, timeperiod=10)
        dataframe['roc'] = ta.ROC(dataframe, timeperiod=10)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        conditions_long = []
        conditions_short = []
        
        # Long conditions - Bullish breakout
        # 1. High breakout detected
        conditions_long.append(dataframe['high_breakout'] == True)
        
        # 2. Volume confirmation
        conditions_long.append(dataframe['volume_ratio'] > self.volume_confirmation.value)
        
        # 3. Some consolidation before breakout
        conditions_long.append(dataframe['consolidation_count'] >= self.min_consolidation.value)
        
        # 4. Momentum confirmation
        conditions_long.append(
            (dataframe['rsi'] > 50) &
            (dataframe['momentum'] > 0)
        )
        
        # 5. Optional: Above key EMAs
        conditions_long.append(dataframe['above_ema20'] == True)
        
        # 6. MACD confirmation
        conditions_long.append(dataframe['macdhist'] > 0)
        
        # Basic sanity check
        conditions_long.append(dataframe['volume'] > 0)
        
        # Alternative long entry: Bollinger Band breakout
        if self.bb_breakout.value:
            bb_long_conditions = [
                dataframe['bb_upper_breakout'] == True,
                dataframe['volume_ratio'] > self.volume_confirmation.value,
                dataframe['rsi'] < 75,  # Not extremely overbought
                dataframe['volume'] > 0
            ]
            
            # Combine regular and BB conditions with OR
            combined_long = (
                reduce(lambda x, y: x & y, conditions_long) |
                reduce(lambda x, y: x & y, bb_long_conditions)
            )
            
            dataframe.loc[combined_long, 'enter_long'] = 1
        else:
            # Only regular conditions
            if conditions_long:
                dataframe.loc[
                    reduce(lambda x, y: x & y, conditions_long),
                    'enter_long'] = 1
        
        # Short conditions - Bearish breakout
        # 1. Low breakout detected
        conditions_short.append(dataframe['low_breakout'] == True)
        
        # 2. Volume confirmation
        conditions_short.append(dataframe['volume_ratio'] > self.volume_confirmation.value)
        
        # 3. Some consolidation before breakout
        conditions_short.append(dataframe['consolidation_count'] >= self.min_consolidation.value)
        
        # 4. Momentum confirmation
        conditions_short.append(
            (dataframe['rsi'] < 50) &
            (dataframe['momentum'] < 0)
        )
        
        # 5. Optional: Below key EMAs
        conditions_short.append(dataframe['above_ema20'] == False)
        
        # 6. MACD confirmation
        conditions_short.append(dataframe['macdhist'] < 0)
        
        # Basic sanity check
        conditions_short.append(dataframe['volume'] > 0)
        
        # Alternative short entry: Bollinger Band breakout
        if self.bb_breakout.value:
            bb_short_conditions = [
                dataframe['bb_lower_breakout'] == True,
                dataframe['volume_ratio'] > self.volume_confirmation.value,
                dataframe['rsi'] > 25,  # Not extremely oversold
                dataframe['volume'] > 0
            ]
            
            # Combine regular and BB conditions with OR
            combined_short = (
                reduce(lambda x, y: x & y, conditions_short) |
                reduce(lambda x, y: x & y, bb_short_conditions)
            )
            
            dataframe.loc[combined_short, 'enter_short'] = 1
        else:
            # Only regular conditions
            if conditions_short:
                dataframe.loc[
                    reduce(lambda x, y: x & y, conditions_short),
                    'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        # Exit long on breakdown or momentum exhaustion
        dataframe.loc[
            (
                (
                    (dataframe['low_breakout'] == True) |  # Opposite breakout
                    (dataframe['rsi'] > 80) |              # Extremely overbought
                    (dataframe['macdhist'] < dataframe['macdhist'].shift(1))  # MACD weakening
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_long'] = 1
        
        # Exit short on breakup or momentum exhaustion
        dataframe.loc[
            (
                (
                    (dataframe['high_breakout'] == True) |  # Opposite breakout
                    (dataframe['rsi'] < 20) |               # Extremely oversold
                    (dataframe['macdhist'] > dataframe['macdhist'].shift(1))  # MACD strengthening
                ) &
                (dataframe['volume'] > 0)
            ),
            'exit_short'] = 1
        
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Custom stoploss logic - dynamic based on ATR and breakout strength
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            atr = last_candle['atr']
            
            # Breakout trades need wider stops initially
            if current_profit > 0.03:
                # Lock in profits for strong moves
                return -0.01  # 1% stop
            elif current_profit > 0.02:
                # Tighten stop
                return -0.015  # 1.5% stop
            else:
                # Use ATR-based stop (wider for breakouts)
                return -(atr / current_rate) * self.stop_loss_atr_multiplier.value
        
        # Fallback to default stoploss
        return self.stoploss
    
    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Custom exit logic for breakout trades
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Exit if breakout fails (retracement back into range)
            if trade.is_short == False:
                # For long trades, exit if price falls back below recent high
                recent_high = last_candle[f'rolling_high_{self.lookback_period.value}']
                if current_rate < recent_high * 0.995 and current_profit < 0:
                    return "failed_breakout_long"
                
                # Exit if opposite breakout occurs
                if last_candle['low_breakout'] and current_profit > 0:
                    return "opposite_breakout_long"
            
            else:
                # For short trades, exit if price rises back above recent low
                recent_low = last_candle[f'rolling_low_{self.lookback_period.value}']
                if current_rate > recent_low * 1.005 and current_profit < 0:
                    return "failed_breakout_short"
                
                # Exit if opposite breakout occurs
                if last_candle['high_breakout'] and current_profit > 0:
                    return "opposite_breakout_short"
            
            # Exit if volume drops significantly (breakout losing steam)
            if last_candle['volume_ratio'] < 0.6 and current_profit > 0.005:
                return "volume_exhaustion"
            
            # Exit on momentum reversal
            if trade.is_short == False and last_candle['momentum'] < -50:
                return "momentum_reversal_long"
            elif trade.is_short == True and last_candle['momentum'] > 50:
                return "momentum_reversal_short"
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """
        Additional confirmation for breakout entries
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Don't enter if breakout is already old
            if side == "long":
                if not (last_candle['high_breakout'] or (self.bb_breakout.value and last_candle['bb_upper_breakout'])):
                    return False
            else:
                if not (last_candle['low_breakout'] or (self.bb_breakout.value and last_candle['bb_lower_breakout'])):
                    return False
            
            # Don't enter if volume is fading
            if last_candle['volume_ratio'] < self.volume_confirmation.value * 0.8:
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
            f"rolling_high_10": {"color": "red"},
            f"rolling_low_10": {"color": "green"},
            "ema_20": {"color": "blue"},
            "ema_50": {"color": "orange"},
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
            "Breakouts": {
                "high_breakout": {"color": "green", "type": "scatter"},
                "low_breakout": {"color": "red", "type": "scatter"}
            }
        }
    }


from functools import reduce