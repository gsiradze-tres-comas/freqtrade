"""
Billionaire Strategy - Targeting 2% Daily Profits
Aggressive high-frequency trading with:
1. No time-based ROI limits - let winners run
2. Quick stop losses to preserve capital
3. Momentum-based entries for explosive moves
4. Compound position sizing for exponential growth
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

class BillionaireStrategy(IStrategy):
    """
    Aggressive strategy targeting 2% daily returns through:
    - High-frequency scalping on momentum
    - No artificial ROI limits
    - Quick stops, let winners run
    - Compound position sizing
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # No ROI table - let the market decide!
    minimal_roi = {
        "0": 100.0  # 10000% - effectively disabled
    }
    
    # Tight stop loss - cut losses FAST
    stoploss = -0.008  # 0.8% stop loss (vs previous 2%)
    
    # Aggressive trailing for profit protection
    trailing_stop = True
    trailing_stop_positive = 0.002  # Start trailing at 0.2% profit
    trailing_stop_positive_offset = 0.005  # Trail by 0.5%
    trailing_only_offset_is_reached = True
    
    # Position adjustment for pyramiding winners
    position_adjustment_enable = True
    max_entry_position_adjustment = 5  # More aggressive pyramiding
    
    # Momentum parameters
    momentum_period = IntParameter(5, 20, default=10, space="buy", load=True)
    momentum_threshold = DecimalParameter(0.002, 0.01, decimals=3, default=0.005, space="buy", load=True)
    
    # Volume surge parameters
    volume_surge = DecimalParameter(1.5, 5.0, decimals=1, default=3.0, space="buy", load=True)
    
    # Volatility parameters
    atr_multiplier = DecimalParameter(1.0, 3.0, decimals=1, default=2.0, space="buy", load=True)
    volatility_threshold = DecimalParameter(0.001, 0.005, decimals=3, default=0.002, space="buy", load=True)
    
    # Exit parameters
    take_profit = DecimalParameter(0.02, 0.05, decimals=3, default=0.03, space="sell", load=True)
    panic_sell = DecimalParameter(-0.015, -0.005, decimals=3, default=-0.01, space="sell", load=True)
    
    @informative('5m')
    def populate_indicators_5m(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """5-minute momentum confirmation"""
        dataframe['momentum_5m'] = dataframe['close'].pct_change(periods=12)  # 1 hour momentum
        dataframe['volume_mean_5m'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['breakout_5m'] = (
            (dataframe['close'] > dataframe['high'].shift(1).rolling(20).max()) & 
            (dataframe['volume'] > dataframe['volume_mean_5m'] * 2)
        ).astype(int)
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Fast indicators for momentum detection"""
        
        # Price action
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['momentum'] = dataframe['close'].pct_change(periods=self.momentum_period.value)
        
        # Cumulative momentum (for trend strength)
        dataframe['cum_momentum'] = dataframe['price_change'].rolling(window=10).sum()
        
        # Volume analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_surge'] = dataframe['volume'] / dataframe['volume_mean']
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['volatility'] = dataframe['atr'] / dataframe['close']
        
        # Bollinger Bands for mean reversion
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # RSI for extremes
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        
        # VWAP for institutional levels
        dataframe['vwap'] = (dataframe['volume'] * (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3).cumsum() / dataframe['volume'].cumsum()
        
        # Support/Resistance (simplified)
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Market session power hours (UTC)
        hour = pd.to_datetime(dataframe['date']).dt.hour
        # Power hours: US open (13-15 UTC), London/US overlap (13-16 UTC)
        dataframe['power_hour'] = ((hour >= 13) & (hour <= 16)).astype(int)
        
        # Get 5m data
        dataframe['momentum_5m'] = dataframe['momentum_5m_5m']
        dataframe['breakout_5m'] = dataframe['breakout_5m_5m']
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Aggressive momentum-based entries"""
        
        # LONG SIGNALS - Explosive upward momentum
        long_momentum = (
            (dataframe['momentum'] > self.momentum_threshold.value) &  # Strong momentum
            (dataframe['momentum_5m'] > 0.001) &  # 5m confirmation
            (dataframe['volume_surge'] > self.volume_surge.value) &  # Volume surge
            (dataframe['volatility'] > self.volatility_threshold.value) &  # Sufficient volatility
            (dataframe['rsi_fast'] < 80) &  # Not overbought yet
            (dataframe['close'] > dataframe['vwap']) &  # Above VWAP
            (dataframe['cum_momentum'] > 0)  # Sustained momentum
        )
        
        # Breakout longs
        long_breakout = (
            (dataframe['close'] > dataframe['resistance']) &  # Breaking resistance
            (dataframe['volume_surge'] > self.volume_surge.value * 1.5) &  # Extra volume
            (dataframe['breakout_5m'] == 1) &  # 5m breakout confirmation
            (dataframe['power_hour'] == 1)  # During power hours
        )
        
        # Bounce longs (oversold)
        long_bounce = (
            (dataframe['close'] < dataframe['bb_lower']) &  # Oversold
            (dataframe['rsi'] < 25) &  # RSI oversold
            (dataframe['momentum'] > 0) &  # Turning positive
            (dataframe['volume_surge'] > 2.0)  # Volume coming in
        )
        
        # SHORT SIGNALS - Explosive downward momentum
        short_momentum = (
            (dataframe['momentum'] < -self.momentum_threshold.value) &  # Strong down momentum
            (dataframe['momentum_5m'] < -0.001) &  # 5m confirmation
            (dataframe['volume_surge'] > self.volume_surge.value) &  # Volume surge
            (dataframe['volatility'] > self.volatility_threshold.value) &  # Sufficient volatility
            (dataframe['rsi_fast'] > 20) &  # Not oversold yet
            (dataframe['close'] < dataframe['vwap']) &  # Below VWAP
            (dataframe['cum_momentum'] < 0)  # Sustained down momentum
        )
        
        # Breakdown shorts
        short_breakdown = (
            (dataframe['close'] < dataframe['support']) &  # Breaking support
            (dataframe['volume_surge'] > self.volume_surge.value * 1.5) &  # Extra volume
            (dataframe['momentum_5m'] < -0.002) &  # 5m breakdown
            (dataframe['power_hour'] == 1)  # During power hours
        )
        
        # Rejection shorts (overbought)
        short_rejection = (
            (dataframe['close'] > dataframe['bb_upper']) &  # Overbought
            (dataframe['rsi'] > 75) &  # RSI overbought
            (dataframe['momentum'] < 0) &  # Turning negative
            (dataframe['volume_surge'] > 2.0)  # Volume coming in
        )
        
        # Combine signals
        dataframe.loc[
            long_momentum | long_breakout | long_bounce,
            ['enter_long', 'enter_tag']
        ] = (1, 'billionaire_long')
        
        dataframe.loc[
            short_momentum | short_breakdown | short_rejection,
            ['enter_short', 'enter_tag']
        ] = (1, 'billionaire_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Let winners run, cut losers fast"""
        
        # Exit longs
        exit_long = (
            # Momentum reversal
            ((dataframe['momentum'] < -0.003) & (dataframe['volume_surge'] > 2.0)) |
            # Strong rejection from highs
            ((dataframe['rsi'] > 85) & (dataframe['price_change'] < -0.002)) |
            # Break below VWAP with volume
            ((dataframe['close'] < dataframe['vwap']) & (dataframe['volume_surge'] > 3.0))
        )
        
        # Exit shorts
        exit_short = (
            # Momentum reversal
            ((dataframe['momentum'] > 0.003) & (dataframe['volume_surge'] > 2.0)) |
            # Strong bounce from lows
            ((dataframe['rsi'] < 15) & (dataframe['price_change'] > 0.002)) |
            # Break above VWAP with volume
            ((dataframe['close'] > dataframe['vwap']) & (dataframe['volume_surge'] > 3.0))
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_short, 'exit_short'] = 1
        
        return dataframe
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """Aggressive profit taking and loss cutting"""
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return None
            
        current_candle = dataframe.iloc[-1]
        
        # Take profit if we hit target
        if current_profit >= self.take_profit.value:
            return f"take_profit_{current_profit:.1%}"
        
        # Panic sell if momentum turns hard against us
        if current_profit < self.panic_sell.value:
            if trade.is_short and current_candle.get('momentum', 0) > 0.005:
                return "panic_momentum_reversal"
            elif not trade.is_short and current_candle.get('momentum', 0) < -0.005:
                return "panic_momentum_reversal"
        
        # Exit if volatility dies (no opportunity)
        if current_candle.get('volatility', 0) < 0.001 and current_profit > 0.002:
            return "low_volatility_exit"
        
        return None
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Compound position sizing for exponential growth
        Kelly Criterion with aggressive sizing
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return proposed_stake
            
        current_candle = dataframe.iloc[-1]
        
        # Base position size (start conservative, grow aggressive)
        total_balance = self.wallets.get_total_stake_amount()
        
        # Kelly fraction based on win rate (assuming 60% win rate from momentum)
        win_rate = 0.60
        win_loss_ratio = 3.75  # Target 3% wins vs 0.8% losses
        kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        kelly_fraction = max(0.1, min(kelly_fraction, 0.5))  # Between 10-50%
        
        # Adjust for momentum strength
        momentum_mult = 1.0
        if abs(current_candle.get('momentum', 0)) > 0.01:  # Very strong momentum
            momentum_mult = 1.5
        elif abs(current_candle.get('momentum', 0)) > 0.005:  # Strong momentum
            momentum_mult = 1.25
        
        # Adjust for session
        session_mult = 1.5 if current_candle.get('power_hour', 0) == 1 else 1.0
        
        # Calculate position size
        position_size = total_balance * kelly_fraction * momentum_mult * session_mult * 0.2  # Start with 20% of Kelly
        
        # Compound gains - increase size as balance grows
        if total_balance > 11000:  # 10% profit
            position_size *= 1.2
        if total_balance > 12000:  # 20% profit
            position_size *= 1.5
        if total_balance > 15000:  # 50% profit
            position_size *= 2.0
        
        # Max 30% of balance per trade for risk management
        max_position = total_balance * 0.30
        position_size = min(position_size, max_position, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size
    
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """
        Aggressive pyramiding on winners
        """
        if current_profit < 0.005:  # Only add to winners
            return None
            
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if len(dataframe) == 0:
            return None
            
        current_candle = dataframe.iloc[-1]
        
        # Check momentum is still strong in our direction
        if trade.is_short:
            if current_candle.get('momentum', 0) > -0.003:  # Momentum weakening
                return None
        else:
            if current_candle.get('momentum', 0) < 0.003:  # Momentum weakening
                return None
        
        # Volume must be surging
        if current_candle.get('volume_surge', 0) < 2.0:
            return None
        
        # Add 50% more to position
        additional_stake = trade.stake_amount * 0.5
        
        return min(additional_stake, max_stake)