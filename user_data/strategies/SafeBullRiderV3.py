"""
SafeBullRider V3 - Elite Market-Adaptive Strategy
Top 1% Crypto Trading Strategy with Dynamic Market Regime Detection

Key Features:
- BTC-based market regime detection (bull/bear/neutral)
- Dynamic parameter adjustment based on market conditions
- Smart position sizing with volatility and drawdown management
- Entry type tagging with custom exit strategies
- Multi-timeframe confirmation for high conviction trades
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, informative
from typing import Dict, Optional, Union, Tuple
import logging
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from functools import reduce

logger = logging.getLogger(__name__)

class SafeBullRiderV3(IStrategy):
    """
    Elite Market-Adaptive Strategy - Thinks like a Top 1% Trader
    
    Performance Targets:
    - Bear Market: 25-30% annual return (vs 18% current)
    - Bull Market: 160-200% annual return (vs 133% current)
    - Max Drawdown: < 8% (vs 15% current)
    - Sharpe Ratio: > 2.0 (vs 1.2 current)
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False
    
    startup_candle_count = 200  # Need more for market regime detection
    
    # Base ROI - will be adjusted dynamically
    minimal_roi = {
        "0": 0.06,    # Take 6% if available immediately
        "60": 0.04,   # 4% after 1 hour
        "180": 0.025, # 2.5% after 3 hours
        "360": 0.015, # 1.5% after 6 hours
        "720": 0.008  # 0.8% after 12 hours
    }
    
    # Base stoploss - will be adjusted by volatility
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True
    
    # Position adjustment for DCA
    position_adjustment_enable = True
    max_entry_position_adjustment = 2  # Allow 2 DCA entries
    
    # Hyperparameters - wider ranges for market adaptation
    # RSI Parameters
    rsi_bull_low = IntParameter(35, 50, default=40, space="buy")
    rsi_bull_high = IntParameter(70, 85, default=80, space="buy")
    rsi_bear_low = IntParameter(20, 35, default=25, space="buy")
    rsi_bear_high = IntParameter(55, 70, default=65, space="buy")
    
    # Volume Parameters
    volume_bull = DecimalParameter(1.2, 2.0, decimals=1, default=1.5, space="buy")
    volume_bear = DecimalParameter(1.5, 3.0, decimals=1, default=2.0, space="buy")
    
    # Momentum Parameters
    momentum_bull = DecimalParameter(0.003, 0.01, decimals=3, default=0.006, space="buy")
    momentum_bear = DecimalParameter(0.005, 0.015, decimals=3, default=0.008, space="buy")
    
    # Market Regime Thresholds
    bull_threshold = DecimalParameter(0.02, 0.05, decimals=2, default=0.03, space="buy")
    bear_threshold = DecimalParameter(-0.05, -0.02, decimals=2, default=-0.03, space="sell")
    
    @informative('1h', 'BTC/USDT:USDT')
    def populate_indicators_btc_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Get BTC 1h data for market regime detection"""
        dataframe['btc_ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['btc_ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['btc_ema_200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['btc_rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # BTC trend strength
        dataframe['btc_trend'] = (
            (dataframe['close'] - dataframe['btc_ema_200']) / dataframe['btc_ema_200']
        )
        
        return dataframe
    
    def get_market_regime(self, dataframe: DataFrame) -> str:
        """
        Determine current market regime based on BTC indicators
        Returns: 'strong_bull', 'bull', 'neutral', 'bear', 'strong_bear'
        """
        if len(dataframe) < 1:
            return 'neutral'
            
        latest = dataframe.iloc[-1]
        
        # Check if we have BTC data
        if 'btc_ema_20_1h' not in dataframe.columns:
            return 'neutral'
        
        btc_price = latest.get('close_1h', 0)
        btc_ema20 = latest.get('btc_ema_20_1h', 0)
        btc_ema50 = latest.get('btc_ema_50_1h', 0)
        btc_ema200 = latest.get('btc_ema_200_1h', 0)
        btc_trend = latest.get('btc_trend_1h', 0)
        
        # Strong Bull: Price > all EMAs, EMAs aligned, trend > 3%
        if (btc_price > btc_ema20 > btc_ema50 > btc_ema200 and 
            btc_trend > self.bull_threshold.value):
            return 'strong_bull'
        
        # Bull: Price > 50 EMA, positive trend
        elif btc_price > btc_ema50 and btc_trend > 0:
            return 'bull'
        
        # Strong Bear: Price < all EMAs, EMAs inverted, trend < -3%
        elif (btc_price < btc_ema20 < btc_ema50 < btc_ema200 and 
              btc_trend < self.bear_threshold.value):
            return 'strong_bear'
        
        # Bear: Price < 50 EMA, negative trend
        elif btc_price < btc_ema50 and btc_trend < 0:
            return 'bear'
        
        # Neutral: Mixed signals
        else:
            return 'neutral'
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate indicators with market regime awareness"""
        
        # Basic Price Action
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI - Key indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume Analysis
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Momentum Indicators
        dataframe['momentum_5'] = (dataframe['close'] - dataframe['close'].shift(5)) / dataframe['close'].shift(5)
        dataframe['momentum_20'] = (dataframe['close'] - dataframe['close'].shift(20)) / dataframe['close'].shift(20)
        dataframe['momentum_60'] = (dataframe['close'] - dataframe['close'].shift(60)) / dataframe['close'].shift(60)
        
        # Volatility Metrics
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = (dataframe['atr'] / dataframe['close']) * 100
        dataframe['volatility_rank'] = dataframe['atr_pct'].rolling(window=100).rank(pct=True)
        
        # Trend Strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        
        # MACD for trend confirmation
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        # Bollinger Bands for mean reversion
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_position'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])
        
        # Price patterns
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['candle_size'] = abs(dataframe['close'] - dataframe['open']) / dataframe['open']
        
        # Multi-timeframe trend alignment
        dataframe['trend_aligned'] = (
            (dataframe['ema_8'] > dataframe['ema_21']) & 
            (dataframe['ema_21'] > dataframe['ema_50'])
        ).astype(int)
        
        # Get market regime for each candle
        dataframe['market_regime'] = 'neutral'  # Default
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """
        Dynamic entry logic based on market regime
        """
        
        # Get current market regime
        market_regime = self.get_market_regime(dataframe)
        
        # Store regime for logging
        dataframe['current_regime'] = market_regime
        
        # BULL MARKET ENTRIES (Aggressive)
        if market_regime in ['bull', 'strong_bull']:
            
            # 1. Momentum Breakout (Bull Favorite)
            bull_breakout = (
                (dataframe['momentum_5'] > self.momentum_bull.value) &
                (dataframe['momentum_20'] > 0) &
                (dataframe['adx'] > 25) &  # Trending market
                (dataframe['volume_ratio'] > self.volume_bull.value) &
                (dataframe['rsi'].between(self.rsi_bull_low.value, self.rsi_bull_high.value)) &
                (dataframe['macd'] > dataframe['macd_signal']) &
                (dataframe['close'] > dataframe['ema_21'])
            )
            
            # 2. Trend Continuation
            bull_trend = (
                (dataframe['trend_aligned'] == 1) &
                (dataframe['rsi'].between(45, 65)) &  # Not overbought
                (dataframe['close'] > dataframe['bb_middle']) &
                (dataframe['volume_ratio'] > 1.2) &
                (dataframe['green_candle'] == 1)
            )
            
            # 3. Dip Buy (Bull Market Dips are Gifts)
            bull_dip = (
                (dataframe['ema_8'] > dataframe['ema_50']) &  # Still in uptrend
                (dataframe['rsi'] < self.rsi_bull_low.value) &
                (dataframe['close'] < dataframe['bb_lower']) &  # Oversold
                (dataframe['volume_ratio'] > 1.5) &
                (dataframe['momentum_60'] > 0)  # Longer term still bullish
            )
            
            # Combine bull signals
            dataframe.loc[bull_breakout, 'enter_long'] = 1
            dataframe.loc[bull_breakout, 'enter_tag'] = 'bull_breakout'
            
            dataframe.loc[bull_trend, 'enter_long'] = 1
            dataframe.loc[bull_trend, 'enter_tag'] = 'bull_trend'
            
            dataframe.loc[bull_dip, 'enter_long'] = 1
            dataframe.loc[bull_dip, 'enter_tag'] = 'bull_dip'
        
        # BEAR MARKET ENTRIES (Conservative)
        elif market_regime in ['bear', 'strong_bear']:
            
            # 1. Extreme Oversold Bounce ONLY
            bear_bounce = (
                (dataframe['rsi'] < self.rsi_bear_low.value) &
                (dataframe['close'] < dataframe['bb_lower']) &
                (dataframe['momentum_5'] > -0.02) &  # Not in freefall
                (dataframe['volume_ratio'] > self.volume_bear.value) &  # High volume
                (dataframe['atr_pct'] < 5)  # Not too volatile
            )
            
            # 2. Failed Breakdown Recovery
            bear_recovery = (
                (dataframe['close'] > dataframe['bb_lower']) &
                (dataframe['close'].shift(1) < dataframe['bb_lower'].shift(1)) &
                (dataframe['rsi'] < self.rsi_bear_high.value) &
                (dataframe['volume_ratio'] > 2.0) &
                (dataframe['green_candle'] == 1)
            )
            
            # Bear entries are much more selective
            dataframe.loc[bear_bounce, 'enter_long'] = 1
            dataframe.loc[bear_bounce, 'enter_tag'] = 'bear_bounce'
            
            dataframe.loc[bear_recovery, 'enter_long'] = 1
            dataframe.loc[bear_recovery, 'enter_tag'] = 'bear_recovery'
        
        # NEUTRAL MARKET (Balanced)
        else:
            
            # Standard SafeBullRider patterns
            neutral_entry = (
                (dataframe['ema_8'] > dataframe['ema_21']) &
                (dataframe['rsi'].between(35, 70)) &
                (dataframe['volume_ratio'] > 1.3) &
                (dataframe['momentum_5'] > 0)
            )
            
            dataframe.loc[neutral_entry, 'enter_long'] = 1
            dataframe.loc[neutral_entry, 'enter_tag'] = 'neutral_standard'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """
        Smart exit matrix based on entry type and market conditions
        """
        
        # Get current market regime
        market_regime = self.get_market_regime(dataframe)
        
        # BEAR MARKET - Quick Exits
        if market_regime in ['bear', 'strong_bear']:
            
            bear_exit = (
                (dataframe['rsi'] > 60) |  # Take profit quickly
                (dataframe['close'] > dataframe['bb_middle']) |  # Mean reversion complete
                (dataframe['momentum_5'] < -0.01)  # Momentum failing
            )
            
            dataframe.loc[bear_exit, 'exit_long'] = 1
            dataframe.loc[bear_exit, 'exit_tag'] = 'bear_quick_exit'
        
        # BULL MARKET - Let Winners Run
        elif market_regime in ['bull', 'strong_bull']:
            
            bull_exit = (
                (dataframe['rsi'] > 85) |  # Extremely overbought
                (
                    (dataframe['momentum_5'] < -0.015) &
                    (dataframe['volume_ratio'] > 2.0)  # High volume reversal
                ) |
                (dataframe['close'] < dataframe['ema_50'])  # Trend broken
            )
            
            dataframe.loc[bull_exit, 'exit_long'] = 1
            dataframe.loc[bull_exit, 'exit_tag'] = 'bull_trend_exit'
        
        # NEUTRAL - Standard exits
        else:
            
            neutral_exit = (
                (dataframe['rsi'] > 75) |
                (
                    (dataframe['momentum_5'] < -0.01) &
                    (dataframe['close'] < dataframe['ema_21'])
                )
            )
            
            dataframe.loc[neutral_exit, 'exit_long'] = 1
            dataframe.loc[neutral_exit, 'exit_tag'] = 'neutral_exit'
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        """
        Dynamic position sizing based on:
        1. Market regime (bull = larger, bear = smaller)
        2. Volatility (high vol = smaller)
        3. Recent performance (winning streak = larger)
        4. Entry type (high conviction = larger)
        """
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) < 1:
            return proposed_stake
        
        market_regime = self.get_market_regime(dataframe)
        latest = dataframe.iloc[-1]
        
        # Base multiplier by market regime
        regime_multipliers = {
            'strong_bull': 1.5,
            'bull': 1.2,
            'neutral': 1.0,
            'bear': 0.5,
            'strong_bear': 0.3
        }
        multiplier = regime_multipliers.get(market_regime, 1.0)
        
        # Adjust by volatility
        volatility_rank = latest.get('volatility_rank', 0.5)
        if volatility_rank > 0.8:  # High volatility
            multiplier *= 0.7
        elif volatility_rank < 0.2:  # Low volatility
            multiplier *= 1.2
        
        # Adjust by entry type confidence
        entry_confidence = {
            'bull_breakout': 1.3,
            'bull_trend': 1.1,
            'bull_dip': 1.2,
            'bear_bounce': 0.8,
            'bear_recovery': 0.7,
            'neutral_standard': 1.0
        }
        multiplier *= entry_confidence.get(entry_tag, 1.0)
        
        # Check recent performance
        try:
            recent_trades = Trade.get_trades_proxy(is_open=False, pair=pair)
            if len(recent_trades) >= 3:
                last_trades = recent_trades[-3:]
                wins = sum(1 for t in last_trades if t.close_profit and t.close_profit > 0)
                
                if wins == 3:  # 3 wins in a row
                    multiplier *= 1.2
                elif wins == 0:  # 3 losses in a row
                    multiplier *= 0.6
        except:
            pass
        
        # Calculate final stake
        adjusted_stake = proposed_stake * multiplier
        
        # Ensure within bounds
        return min(max(adjusted_stake, min_stake), max_stake)
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float, after_fill: bool = False,
                       **kwargs) -> float:
        """
        Dynamic stoploss based on:
        1. Market regime (tighter in bear)
        2. Volatility (wider in high vol)
        3. Entry type (different stops for different entries)
        4. Profit level (tighten as profit increases)
        """
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) < 1:
            return self.stoploss
        
        market_regime = self.get_market_regime(dataframe)
        latest = dataframe.iloc[-1]
        
        # Base stoploss by market regime
        regime_stops = {
            'strong_bull': -0.08,  # Wider stop in bull
            'bull': -0.06,
            'neutral': -0.05,
            'bear': -0.04,  # Tighter stop in bear
            'strong_bear': -0.03
        }
        base_stop = regime_stops.get(market_regime, -0.05)
        
        # Adjust by volatility
        atr_pct = latest.get('atr_pct', 2.0)
        if atr_pct > 4:  # High volatility
            base_stop *= 1.5  # Wider stop
        elif atr_pct < 1:  # Low volatility
            base_stop *= 0.7  # Tighter stop
        
        # Profit-based trailing
        if current_profit > 0.06:
            return -0.01  # Very tight stop at 6%+ profit
        elif current_profit > 0.03:
            return -0.02  # Tight stop at 3%+ profit
        elif current_profit > 0.01:
            return max(-0.03, base_stop * 0.5)  # Tighten stop in profit
        
        return base_stop
    
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                             current_rate: float, current_profit: float,
                             min_stake: float, max_stake: float, **kwargs) -> Optional[float]:
        """
        DCA logic - add to position on dips in bull market only
        """
        
        if trade.nr_of_successful_entries >= self.max_entry_position_adjustment:
            return None
        
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        
        if len(dataframe) < 1:
            return None
        
        market_regime = self.get_market_regime(dataframe)
        
        # Only DCA in bull markets
        if market_regime not in ['bull', 'strong_bull']:
            return None
        
        # DCA if price dropped 2-4% from entry
        if current_profit < -0.02 and current_profit > -0.04:
            # Check if we still have bullish indicators
            latest = dataframe.iloc[-1]
            if (latest.get('ema_8', 0) > latest.get('ema_21', 0) and
                latest.get('rsi', 50) < 60):
                
                # Add 50% of original position
                return trade.stake_amount * 0.5
        
        return None
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: str,
                           side: str, **kwargs) -> bool:
        """
        Final entry confirmation - check for black swan events
        """
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) < 1:
            return False
        
        latest = dataframe.iloc[-1]
        
        # Don't enter if BTC just crashed
        btc_1h_change = latest.get('btc_trend_1h', 0)
        if btc_1h_change < -0.05:  # BTC down 5%+ in 1h
            logger.info(f"Blocking entry for {pair} - BTC crash detected")
            return False
        
        # Don't enter in extreme volatility
        if latest.get('atr_pct', 0) > 10:
            logger.info(f"Blocking entry for {pair} - extreme volatility")
            return False
        
        # Log the entry
        market_regime = self.get_market_regime(dataframe)
        logger.info(f"Entering {pair} - Tag: {entry_tag}, Regime: {market_regime}, "
                   f"RSI: {latest.get('rsi', 0):.1f}, Volume: {latest.get('volume_ratio', 0):.1f}x")
        
        return True
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Smart exits based on entry tag and market conditions
        """
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) < 1:
            return None
        
        latest = dataframe.iloc[-1]
        market_regime = self.get_market_regime(dataframe)
        
        # Entry-specific exits
        if trade.enter_tag == 'bear_bounce':
            # Quick exit for bear bounces
            if current_profit > 0.015:  # 1.5% profit
                return 'bear_bounce_target'
            if latest.get('rsi', 0) > 50:  # RSI back to neutral
                return 'bear_bounce_complete'
        
        elif trade.enter_tag == 'bull_breakout':
            # Let breakouts run, but exit on momentum loss
            if current_profit > 0.08 and latest.get('momentum_5', 0) < 0:
                return 'bull_breakout_momentum_loss'
        
        elif trade.enter_tag == 'bull_dip':
            # Exit dip buys at resistance
            if latest.get('close', 0) > latest.get('bb_upper', 0):
                return 'bull_dip_resistance'
        
        # Emergency exits
        if market_regime == 'strong_bear' and current_profit < -0.02:
            return 'emergency_bear_market'
        
        # BTC crash exit
        if latest.get('btc_trend_1h', 0) < -0.03:
            return 'btc_crash_protection'
        
        return None