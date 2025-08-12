"""
Try1 Perfect Strategy - Complete Replication of Your Profitable Bot
Target: 2% daily profit like your successful July 2025 paper trading
Combines all winning elements with proper implementation
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional, Union, Tuple
import logging
from datetime import datetime, time
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)

class Try1PerfectStrategy(IStrategy):
    """
    Perfect replication of your profitable try1 bot
    2% daily target with smart filtering and risk management
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    
    # Dynamic ROI based on market conditions
    minimal_roi = {
        "0": 0.03,    # 3% for strong moves
        "180": 0.02,  # 2% after 3 hours
        "360": 0.015, # 1.5% after 6 hours
        "720": 0.008, # 0.8% after 12 hours
        "1440": 0.004 # 0.4% after 24 hours
    }
    
    # Wider stop loss with room for volatility
    stoploss = -0.04  # 4% stop loss
    
    # Smart trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01    # Start trailing at 1%
    trailing_stop_positive_offset = 0.015  # Trail by 1.5%
    trailing_only_offset_is_reached = True
    
    # Position adjustment for scaling
    position_adjustment_enable = True
    max_entry_position_adjustment = 2  # Scale in up to 2 times
    
    # Strategy weights (exact from config.yaml)
    strategy_weights = {
        'main_engulfing': 0.25,
        'rsi_bounce': 0.20,
        'ma_crossover': 0.20,
        'volume_spike': 0.15,
        'breakout': 0.10,
        'momentum_backup': 0.10
    }
    
    # Parameters optimized for July 2025 market - MUCH MORE LENIENT
    min_confidence = DecimalParameter(0.25, 0.40, decimals=2, default=0.35, space="buy", load=True)
    min_active_strategies = IntParameter(1, 2, default=1, space="buy", load=True)  # Allow single strategy
    
    # Market filter parameters
    volatility_spike_threshold = DecimalParameter(2.0, 3.0, decimals=1, default=2.5, space="buy", load=True)
    min_volume_threshold = DecimalParameter(0.5, 0.8, decimals=1, default=0.6, space="buy", load=True)
    trend_strength_threshold = DecimalParameter(0.01, 0.03, decimals=3, default=0.02, space="buy", load=True)
    max_daily_trades = IntParameter(10, 25, default=15, space="buy", load=True)
    
    # Trading session parameters
    trade_during_low_volume = False
    avoid_news_hours = True
    
    # Risk management
    max_open_trades = 5  # Limit concurrent positions
    daily_profit_target = 0.02  # 2% daily target
    daily_loss_limit = -0.03    # 3% daily loss limit
    
    def __init__(self, config: Dict) -> None:
        super().__init__(config)
        self.trade_count_today = 0
        self.daily_profit = 0.0
        self.last_trade_date = None
        
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Complete indicator set for all 6 strategies"""
        
        # Price EMAs
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI with multiple periods
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        dataframe['rsi_slow'] = ta.RSI(dataframe, timeperiod=21)
        dataframe['rsi_slope'] = dataframe['rsi'] - dataframe['rsi'].shift(3)
        
        # Volume analysis
        dataframe['volume_mean_20'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_mean_50'] = dataframe['volume'].rolling(window=50).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean_20']
        dataframe['volume_trend'] = dataframe['volume_mean_20'] / dataframe['volume_mean_50']
        
        # Price action
        dataframe['price_change_5'] = dataframe['close'].pct_change(periods=5)
        dataframe['price_change_20'] = dataframe['close'].pct_change(periods=20)
        dataframe['price_change_50'] = dataframe['close'].pct_change(periods=50)
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        dataframe['bb_position'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])
        
        # ATR and volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_ratio'] = dataframe['atr'] / dataframe['close']
        dataframe['volatility_20'] = dataframe['close'].pct_change().rolling(window=20).std()
        dataframe['volatility_50'] = dataframe['close'].pct_change().rolling(window=50).std()
        dataframe['volatility_ratio'] = dataframe['volatility_20'] / (dataframe['volatility_50'] + 0.0001)
        
        # Candle patterns
        dataframe['body_size'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['wick_size'] = dataframe['high'] - dataframe['low'] - dataframe['body_size']
        dataframe['body_ratio'] = dataframe['body_size'] / (dataframe['high'] - dataframe['low'] + 0.0001)
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        dataframe['red_candle'] = (dataframe['close'] < dataframe['open']).astype(int)
        
        # Previous candle info
        for i in range(1, 4):
            dataframe[f'prev_body_size_{i}'] = dataframe['body_size'].shift(i)
            dataframe[f'prev_red_{i}'] = dataframe['red_candle'].shift(i)
            dataframe[f'prev_green_{i}'] = dataframe['green_candle'].shift(i)
            dataframe[f'prev_high_{i}'] = dataframe['high'].shift(i)
            dataframe[f'prev_low_{i}'] = dataframe['low'].shift(i)
        
        # Support/Resistance levels
        dataframe['resistance_20'] = dataframe['high'].rolling(window=20).max()
        dataframe['support_20'] = dataframe['low'].rolling(window=20).min()
        dataframe['resistance_50'] = dataframe['high'].rolling(window=50).max()
        dataframe['support_50'] = dataframe['low'].rolling(window=50).min()
        
        # Market structure
        dataframe['higher_high'] = (dataframe['high'] > dataframe['high'].shift(1)) & (dataframe['high'].shift(1) > dataframe['high'].shift(2))
        dataframe['lower_low'] = (dataframe['low'] < dataframe['low'].shift(1)) & (dataframe['low'].shift(1) < dataframe['low'].shift(2))
        dataframe['trend_strength'] = abs(dataframe['price_change_20'])
        
        # Market regime detection
        dataframe = self._detect_market_regime(dataframe)
        
        # Calculate all strategy signals
        dataframe = self._calculate_all_signals(dataframe)
        
        # Calculate weighted consensus
        dataframe['consensus_score'] = (
            dataframe['main_engulfing_signal'] * self.strategy_weights['main_engulfing'] +
            dataframe['rsi_bounce_signal'] * self.strategy_weights['rsi_bounce'] +
            dataframe['ma_crossover_signal'] * self.strategy_weights['ma_crossover'] +
            dataframe['volume_spike_signal'] * self.strategy_weights['volume_spike'] +
            dataframe['breakout_signal'] * self.strategy_weights['breakout'] +
            dataframe['momentum_backup_signal'] * self.strategy_weights['momentum_backup']
        )
        
        # Count active strategies
        dataframe['active_strategies'] = (
            (dataframe['main_engulfing_signal'] != 0).astype(int) +
            (dataframe['rsi_bounce_signal'] != 0).astype(int) +
            (dataframe['ma_crossover_signal'] != 0).astype(int) +
            (dataframe['volume_spike_signal'] != 0).astype(int) +
            (dataframe['breakout_signal'] != 0).astype(int) +
            (dataframe['momentum_backup_signal'] != 0).astype(int)
        )
        
        return dataframe
    
    def _detect_market_regime(self, df: DataFrame) -> DataFrame:
        """Advanced market regime detection"""
        
        # Trend detection
        df['bull_market'] = (
            (df['close'] > df['ema_200']) &
            (df['ema_8'] > df['ema_21']) &
            (df['ema_21'] > df['ema_50']) &
            (df['price_change_50'] > self.trend_strength_threshold.value)
        )
        
        df['bear_market'] = (
            (df['close'] < df['ema_200']) &
            (df['ema_8'] < df['ema_21']) &
            (df['ema_21'] < df['ema_50']) &
            (df['price_change_50'] < -self.trend_strength_threshold.value)
        )
        
        df['sideways_market'] = (~df['bull_market']) & (~df['bear_market'])
        
        # Volatility analysis
        df['high_volatility'] = df['volatility_ratio'] > self.volatility_spike_threshold.value
        df['normal_volatility'] = (df['volatility_ratio'] >= 0.8) & (df['volatility_ratio'] <= 1.5)
        
        # Volume health
        df['healthy_volume'] = df['volume_ratio'] >= self.min_volume_threshold.value
        df['volume_expanding'] = df['volume_trend'] > 1.0
        
        # Market quality score (more lenient)
        df['market_quality'] = (
            df['healthy_volume'].astype(int) +
            df['normal_volatility'].astype(int) +
            (~df['sideways_market']).astype(int) +
            (df['trend_strength'] > 0.005).astype(int)  # Lower trend requirement
        ) / 4.0
        
        # Trading allowed (less restrictive)
        df['trading_allowed'] = (
            df['market_quality'] >= 0.25  # Lower quality threshold
        ) & (
            ~df['high_volatility']
        )
        
        return df
    
    def _calculate_all_signals(self, df: DataFrame) -> DataFrame:
        """Calculate signals for all 6 strategies"""
        
        # 1. Main Engulfing Strategy (25% weight) - RELAXED CONDITIONS
        bullish_engulfing = (
            (df['green_candle'] == 1) &
            (df['prev_red_1'] == 1) &
            (df['body_size'] > df['prev_body_size_1'] * 1.2) &  # Reduced from 1.5 to 1.2
            (df['close'] > df['prev_high_1']) &
            (df['body_ratio'] > 0.3) &  # Reduced from 0.6 to 0.3
            (df['volume_ratio'] > 1.2) &  # Reduced from 1.5 to 1.2
            (df['rsi'] < 75) & (df['rsi'] > 25)  # Widened range
        )
        
        bearish_engulfing = (
            (df['red_candle'] == 1) &
            (df['prev_green_1'] == 1) &
            (df['body_size'] > df['prev_body_size_1'] * 1.2) &  # Reduced from 1.5 to 1.2
            (df['close'] < df['prev_low_1']) &
            (df['body_ratio'] > 0.3) &  # Reduced from 0.6 to 0.3
            (df['volume_ratio'] > 1.2) &  # Reduced from 1.5 to 1.2
            (df['rsi'] < 75) & (df['rsi'] > 25)  # Widened range
        )
        
        df['main_engulfing_signal'] = np.where(bullish_engulfing, 1.0,
                                              np.where(bearish_engulfing, -1.0, 0.0))
        
        # 2. RSI Bounce Strategy (20% weight) - RELAXED CONDITIONS
        rsi_bounce_long = (
            (df['rsi'] < 35) &  # Relaxed from 30 to 35
            (df['rsi'] > df['rsi'].shift(1)) &
            (df['rsi_slope'] > 2) &  # Reduced from 5 to 2
            (df['volume_ratio'] > 1.0) &  # Reduced from 1.2 to 1.0
            (df['price_change_5'] > -0.02) &  # More lenient price change
            True  # Removed market regime requirement
        )
        
        rsi_bounce_short = (
            (df['rsi'] > 65) &  # Relaxed from 70 to 65
            (df['rsi'] < df['rsi'].shift(1)) &
            (df['rsi_slope'] < -2) &  # Reduced from -5 to -2
            (df['volume_ratio'] > 1.0) &  # Reduced from 1.2 to 1.0
            (df['price_change_5'] < 0.02) &  # More lenient price change
            True  # Removed market regime requirement
        )
        
        df['rsi_bounce_signal'] = np.where(rsi_bounce_long, 1.0,
                                          np.where(rsi_bounce_short, -1.0, 0.0))
        
        # 3. MA Crossover Strategy (20% weight) - RELAXED CONDITIONS
        ma_cross_long = (
            (df['ema_8'] > df['ema_21']) &
            (df['ema_8'].shift(1) <= df['ema_21'].shift(1)) &
            (df['volume_ratio'] > 0.8) &  # Reduced from 1.0 to 0.8
            (abs(df['ema_8'] - df['ema_21']) / df['close'] > 0.001)  # Reduced from 0.002 to 0.001
            # Removed bull_market and ema_21 > ema_50 requirements
        )
        
        ma_cross_short = (
            (df['ema_8'] < df['ema_21']) &
            (df['ema_8'].shift(1) >= df['ema_21'].shift(1)) &
            (df['volume_ratio'] > 0.8) &  # Reduced from 1.0 to 0.8
            (abs(df['ema_8'] - df['ema_21']) / df['close'] > 0.001)  # Reduced from 0.002 to 0.001
            # Removed bear_market and ema_21 < ema_50 requirements
        )
        
        df['ma_crossover_signal'] = np.where(ma_cross_long, 1.0,
                                            np.where(ma_cross_short, -1.0, 0.0))
        
        # 4. Volume Spike Strategy (15% weight)
        volume_spike_long = (
            (df['volume_ratio'] > 2.5) &
            (df['price_change_5'] > 0.005) &
            (df['green_candle'] == 1) &
            (df['volume_expanding']) &
            (df['rsi'] < 65)
        )
        
        volume_spike_short = (
            (df['volume_ratio'] > 2.5) &
            (df['price_change_5'] < -0.005) &
            (df['red_candle'] == 1) &
            (df['volume_expanding']) &
            (df['rsi'] > 35)
        )
        
        df['volume_spike_signal'] = np.where(volume_spike_long, 1.0,
                                            np.where(volume_spike_short, -1.0, 0.0))
        
        # 5. Breakout Strategy (10% weight)
        breakout_long = (
            (df['close'] > df['resistance_20']) &
            (df['close'].shift(1) <= df['resistance_20'].shift(1)) &
            (df['volume_ratio'] > 1.8) &
            (df['bb_width'] > 0.02) &
            (df['bull_market'])
        )
        
        breakout_short = (
            (df['close'] < df['support_20']) &
            (df['close'].shift(1) >= df['support_20'].shift(1)) &
            (df['volume_ratio'] > 1.8) &
            (df['bb_width'] > 0.02) &
            (df['bear_market'])
        )
        
        df['breakout_signal'] = np.where(breakout_long, 1.0,
                                        np.where(breakout_short, -1.0, 0.0))
        
        # 6. Momentum Backup Strategy (10% weight) - RELAXED + FALLBACK SIGNALS
        momentum_long = (
            (df['price_change_20'] > 0.005) &  # Reduced from 0.01 to 0.005
            (df['price_change_5'] > 0.002) &   # Reduced from 0.003 to 0.002
            (df['rsi'] > 45) & (df['rsi'] < 75) &  # Widened range
            (df['volume_ratio'] > 1.0) &  # Reduced from 1.3 to 1.0
            (df['close'] > df['ema_8'])   # Simple trend filter instead of higher_high
        )
        
        momentum_short = (
            (df['price_change_20'] < -0.005) &  # Reduced from -0.01 to -0.005
            (df['price_change_5'] < -0.002) &   # Reduced from -0.003 to -0.002
            (df['rsi'] < 55) & (df['rsi'] > 25) &  # Widened range
            (df['volume_ratio'] > 1.0) &  # Reduced from 1.3 to 1.0
            (df['close'] < df['ema_8'])   # Simple trend filter instead of lower_low
        )
        
        # ADD SIMPLE FALLBACK SIGNALS when main strategies fail
        simple_long_fallback = (
            (df['rsi'] < 30) &  # Simple oversold
            (df['close'] > df['ema_21']) &  # Above trend
            (df['volume_ratio'] > 0.8)  # Some volume
        )
        
        simple_short_fallback = (
            (df['rsi'] > 70) &  # Simple overbought  
            (df['close'] < df['ema_21']) &  # Below trend
            (df['volume_ratio'] > 0.8)  # Some volume
        )
        
        df['momentum_backup_signal'] = np.where(
            momentum_long | simple_long_fallback, 1.0,
            np.where(momentum_short | simple_short_fallback, -1.0, 0.0)
        )
        
        return df
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Smart entry with all filters and limits"""
        
        # Check if we've hit daily limits
        if self._check_daily_limits():
            return dataframe
        
        # Primary entry conditions - MUCH MORE LENIENT
        long_entry = (
            (dataframe['trading_allowed']) &
            (dataframe['consensus_score'] >= self.min_confidence.value) &
            (dataframe['active_strategies'] >= self.min_active_strategies.value) &
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.001) &  # Reduced from 0.002 to 0.001
            (dataframe['market_quality'] >= 0.3)  # Reduced from 0.6 to 0.3
        )
        
        short_entry = (
            (dataframe['trading_allowed']) &
            (dataframe['consensus_score'] <= -self.min_confidence.value) &
            (dataframe['active_strategies'] >= self.min_active_strategies.value) &
            (dataframe['volume'] > 0) &
            (dataframe['atr_ratio'] > 0.001) &  # Reduced from 0.002 to 0.001
            (dataframe['market_quality'] >= 0.3)  # Reduced from 0.6 to 0.3
        )
        
        # Time-based filters (skip during backtesting)
        if hasattr(dataframe.index, 'hour'):
            dataframe['hour'] = dataframe.index.hour
            time_filter = ~dataframe['hour'].isin([0, 1, 23]) if self.avoid_news_hours else True
        else:
            time_filter = True  # Skip time filtering in backtesting
        
        long_entry = long_entry & time_filter
        short_entry = short_entry & time_filter
        
        dataframe.loc[long_entry, ['enter_long', 'enter_tag']] = (1, 'perfect_long')
        dataframe.loc[short_entry, ['enter_short', 'enter_tag']] = (1, 'perfect_short')
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Smart exits based on market conditions"""
        
        # Exit if market becomes unfavorable
        market_exit = (
            (dataframe['high_volatility']) |
            (~dataframe['trading_allowed']) |
            (dataframe['market_quality'] < 0.3)
        )
        
        dataframe.loc[market_exit, 'exit_long'] = 1
        dataframe.loc[market_exit, 'exit_short'] = 1
        
        return dataframe
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """Dynamic exit based on trade performance"""
        
        # Quick profit taking for scalping
        if current_profit > 0.015 and trade.calc_profit_ratio(current_rate) > 0.015:
            return 'quick_profit_1.5%'
        
        # Exit losing trades faster in bad market conditions
        if current_profit < -0.02 and self.dp.runmode.value in ('live', 'dry_run'):
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            
            if last_candle['high_volatility'] or not last_candle['trading_allowed']:
                return 'unfavorable_market'
        
        return None
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """Dynamic position sizing based on market conditions"""
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        
        total_balance = self.wallets.get_total_stake_amount()
        base_stake = total_balance * 0.05  # 5% base position
        
        # Adjust based on market quality
        if last_candle['market_quality'] >= 0.8:
            stake_multiplier = 1.2  # 20% larger in excellent conditions
        elif last_candle['market_quality'] >= 0.6:
            stake_multiplier = 1.0  # Normal size
        else:
            stake_multiplier = 0.8  # 20% smaller in poor conditions
        
        # Adjust based on consensus strength
        if abs(last_candle['consensus_score']) >= 0.8:
            stake_multiplier *= 1.1  # 10% larger for strong consensus
        
        position_size = base_stake * stake_multiplier
        
        # Ensure within limits
        position_size = min(position_size, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size
    
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """Scale into winning positions"""
        
        # Only scale into profitable trades
        if current_profit > 0.005 and trade.nr_of_successful_entries < 2:
            # Check if market conditions still favorable
            dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            
            if last_candle['trading_allowed'] and last_candle['market_quality'] >= 0.6:
                # Scale in with 50% of original position
                return trade.stake_amount * 0.5
        
        return None
    
    def _check_daily_limits(self) -> bool:
        """Check if daily trading limits are reached"""
        
        current_date = datetime.now().date()
        
        # Reset counters for new day
        if self.last_trade_date != current_date:
            self.trade_count_today = 0
            self.daily_profit = 0.0
            self.last_trade_date = current_date
        
        # Check trade count limit
        if self.trade_count_today >= self.max_daily_trades.value:
            return True
        
        # Check profit target
        if self.daily_profit >= self.daily_profit_target:
            return True
        
        # Check loss limit
        if self.daily_profit <= self.daily_loss_limit:
            return True
        
        return False
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                            side: str, **kwargs) -> bool:
        """Final confirmation before entering trade"""
        
        # Update trade counter
        self.trade_count_today += 1
        
        # Double-check daily limits
        if self._check_daily_limits():
            return False
        
        # Confirm market conditions one more time
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        
        if not last_candle['trading_allowed'] or last_candle['market_quality'] < 0.5:
            return False
        
        return True
    
    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        """Track daily profit on exit"""
        
        # Calculate and update daily profit
        profit = trade.calc_profit_ratio(rate)
        self.daily_profit += profit
        
        return True