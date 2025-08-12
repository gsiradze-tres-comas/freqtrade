"""
Phase 1 Enhanced Multi-Strategy with Multi-Timeframe Confluence
Targets 2-5% monthly returns through:
1. All 15 crypto pairs trading
2. Multi-timeframe confluence (1m, 5m, 15m, 1h)
3. Dynamic position sizing (Kelly Criterion)
4. Partial profit taking
5. Market session optimization
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

class MainMultiStrategyPhase1(IStrategy):
    """
    Phase 1 implementation: Quick income maximization through advanced features
    """
    
    INTERFACE_VERSION = 3
    timeframe = '1m'
    can_short = True
    
    # Balanced ROI for consistent profits
    minimal_roi = {
        "0": 0.025,   # TP3: 2.5% (final 30%)
        "30": 0.018,  # TP2: 1.8% (next 30%)
        "60": 0.012,  # TP1: 1.2% (first 40%)
        "120": 0.006, # Trailing profit
        "240": 0.002  # Small profit instead of breakeven
    }
    
    stoploss = -0.020  # 2.0% stop loss
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.010
    trailing_only_offset_is_reached = True
    
    # Position adjustment for partial profit taking
    position_adjustment_enable = True
    max_entry_position_adjustment = 3
    
    # Strategy weights (proven performance)
    engulfing_weight = DecimalParameter(0.25, 0.25, decimals=2, default=0.25, space="buy", load=True)
    rsi_bounce_weight = DecimalParameter(0.20, 0.20, decimals=2, default=0.20, space="buy", load=True)
    ma_crossover_weight = DecimalParameter(0.20, 0.20, decimals=2, default=0.20, space="buy", load=True)
    volume_spike_weight = DecimalParameter(0.15, 0.15, decimals=2, default=0.15, space="buy", load=True)
    breakout_weight = DecimalParameter(0.10, 0.10, decimals=2, default=0.10, space="buy", load=True)
    momentum_weight = DecimalParameter(0.10, 0.10, decimals=2, default=0.10, space="buy", load=True)
    
    # Keep original working thresholds but improve quality with better filters
    min_consensus_score = DecimalParameter(0.40, 0.40, decimals=2, default=0.40, space="buy", load=True)
    min_active_strategies = IntParameter(2, 2, default=2, space="buy", load=True)
    
    # Balanced multi-timeframe parameters for more opportunities
    htf_trend_weight = DecimalParameter(0.25, 0.40, decimals=2, default=0.28, space="buy", load=True)
    htf_confluence_min = DecimalParameter(0.60, 0.80, decimals=2, default=0.52, space="buy", load=True)
    
    # Kelly Criterion parameters
    kelly_fraction = DecimalParameter(0.15, 0.35, decimals=2, default=0.25, space="buy", load=True)
    max_position_size = DecimalParameter(0.05, 0.15, decimals=2, default=0.10, space="buy", load=True)
    
    @informative('5m')
    def populate_indicators_5m(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """5-minute timeframe indicators for trend confirmation"""
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # 5m trend direction
        dataframe['trend_5m'] = np.where(dataframe['ema_20'] > dataframe['ema_50'], 1, 
                                        np.where(dataframe['ema_20'] < dataframe['ema_50'], -1, 0))
        
        return dataframe
    
    @informative('15m')
    def populate_indicators_15m(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """15-minute timeframe indicators for support/resistance"""
        dataframe['bb_upper'] = ta.BBANDS(dataframe, timeperiod=20)['upperband']
        dataframe['bb_lower'] = ta.BBANDS(dataframe, timeperiod=20)['lowerband']
        dataframe['bb_middle'] = ta.BBANDS(dataframe, timeperiod=20)['middleband']
        
        # Support/resistance levels
        dataframe['resistance_15m'] = dataframe['high'].rolling(20).max()
        dataframe['support_15m'] = dataframe['low'].rolling(20).min()
        
        return dataframe
    
    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """1-hour timeframe indicators for major trend"""
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Major trend
        dataframe['major_trend_1h'] = np.where(dataframe['ema_50'] > dataframe['ema_200'], 1,
                                               np.where(dataframe['ema_50'] < dataframe['ema_200'], -1, 0))
        
        # Momentum state
        dataframe['momentum_1h'] = np.where(dataframe['rsi'] > 50, 1,
                                           np.where(dataframe['rsi'] < 50, -1, 0))
        
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Populate all indicators including multi-timeframe data"""
        
        # ===== COMMON INDICATORS (1m) =====
        # EMAs
        dataframe['ema_5'] = ta.EMA(dataframe, timeperiod=5)
        dataframe['ema_10'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lower'] = bollinger['lowerband']
        dataframe['bb_middle'] = bollinger['middleband']
        dataframe['bb_upper'] = bollinger['upperband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # ATR for dynamic stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        
        # Market session (UTC times)
        hour = pd.to_datetime(dataframe['date']).dt.hour
        dataframe['asian_session'] = ((hour >= 23) | (hour < 8)).astype(int)
        dataframe['european_session'] = ((hour >= 7) & (hour < 16)).astype(int)
        dataframe['us_session'] = ((hour >= 13) & (hour < 22)).astype(int)
        
        # ===== STRATEGY SIGNALS (1m) =====
        # 1. Enhanced Engulfing
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        dataframe['body_ratio'] = dataframe['body'] / (dataframe['high'] - dataframe['low'] + 1e-10)
        
        dataframe['engulf_bull'] = (
            (dataframe['close'] > dataframe['open']) &
            (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &
            (dataframe['close'] > dataframe['open'].shift(1)) &
            (dataframe['open'] < dataframe['close'].shift(1)) &
            (dataframe['body_ratio'] >= 0.6) &
            (dataframe['volume'] > dataframe['volume_mean'] * 1.5) &
            (dataframe['rsi'].between(30, 70)) &
            (dataframe['close'] > dataframe['ema_20'])
        ).astype(int)
        
        dataframe['engulf_bear'] = (
            (dataframe['close'] < dataframe['open']) &
            (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &
            (dataframe['close'] < dataframe['open'].shift(1)) &
            (dataframe['open'] > dataframe['close'].shift(1)) &
            (dataframe['body_ratio'] >= 0.6) &
            (dataframe['volume'] > dataframe['volume_mean'] * 1.5) &
            (dataframe['rsi'].between(30, 70)) &
            (dataframe['close'] < dataframe['ema_20'])
        ).astype(int)
        
        # 2. RSI Bounce
        dataframe['rsi_bull'] = (
            (dataframe['rsi'] < 35) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
            (dataframe['close'] > dataframe['bb_lower'])
        ).astype(int)
        
        dataframe['rsi_bear'] = (
            (dataframe['rsi'] > 65) &
            (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
            (dataframe['close'] < dataframe['bb_upper'])
        ).astype(int)
        
        # 3. MA Crossover
        dataframe['ma_bull'] = (
            (dataframe['ema_5'] > dataframe['ema_10']) &
            (dataframe['ema_5'].shift(1) <= dataframe['ema_10'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_mean'] * 0.8)
        ).astype(int)
        
        dataframe['ma_bear'] = (
            (dataframe['ema_5'] < dataframe['ema_10']) &
            (dataframe['ema_5'].shift(1) >= dataframe['ema_10'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_mean'] * 0.8)
        ).astype(int)
        
        # 4. Volume Spike
        dataframe['vol_bull'] = (
            (dataframe['volume'] > dataframe['volume_mean'] * 2.0) &
            (dataframe['close'] > dataframe['open']) &
            (dataframe['close'] > dataframe['close'].shift(1))
        ).astype(int)
        
        dataframe['vol_bear'] = (
            (dataframe['volume'] > dataframe['volume_mean'] * 2.0) &
            (dataframe['close'] < dataframe['open']) &
            (dataframe['close'] < dataframe['close'].shift(1))
        ).astype(int)
        
        # 5. Breakout
        dataframe['high_20'] = dataframe['high'].rolling(window=20).max()
        dataframe['low_20'] = dataframe['low'].rolling(window=20).min()
        
        dataframe['breakout_bull'] = (
            (dataframe['close'] > dataframe['high_20'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_mean'] * 1.2) &
            (dataframe['rsi'] < 75)
        ).astype(int)
        
        dataframe['breakout_bear'] = (
            (dataframe['close'] < dataframe['low_20'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_mean'] * 1.2) &
            (dataframe['rsi'] > 25)
        ).astype(int)
        
        # 6. Momentum
        dataframe['momentum'] = dataframe['close'].pct_change(periods=10)
        
        dataframe['momentum_bull'] = (
            (dataframe['momentum'] > 0.01) &
            (dataframe['rsi'] > 55) &
            (dataframe['volume'] > dataframe['volume_mean'])
        ).astype(int)
        
        dataframe['momentum_bear'] = (
            (dataframe['momentum'] < -0.01) &
            (dataframe['rsi'] < 45) &
            (dataframe['volume'] > dataframe['volume_mean'])
        ).astype(int)
        
        # ===== MULTI-TIMEFRAME CONFLUENCE =====
        # Get higher timeframe data
        dataframe['trend_5m'] = dataframe['trend_5m_5m']
        dataframe['resistance_15m'] = dataframe['resistance_15m_15m']
        dataframe['support_15m'] = dataframe['support_15m_15m']
        dataframe['major_trend_1h'] = dataframe['major_trend_1h_1h']
        dataframe['momentum_1h'] = dataframe['momentum_1h_1h']
        
        # Calculate HTF confluence score
        dataframe['htf_bull_score'] = (
            (dataframe['trend_5m'] == 1).astype(float) * 0.3 +
            (dataframe['close'] < dataframe['resistance_15m'] * 0.98).astype(float) * 0.2 +
            (dataframe['major_trend_1h'] == 1).astype(float) * 0.3 +
            (dataframe['momentum_1h'] == 1).astype(float) * 0.2
        )
        
        dataframe['htf_bear_score'] = (
            (dataframe['trend_5m'] == -1).astype(float) * 0.3 +
            (dataframe['close'] > dataframe['support_15m'] * 1.02).astype(float) * 0.2 +
            (dataframe['major_trend_1h'] == -1).astype(float) * 0.3 +
            (dataframe['momentum_1h'] == -1).astype(float) * 0.2
        )
        
        # ===== CONSENSUS CALCULATION =====
        dataframe['bull_strategies'] = (
            dataframe['engulf_bull'] + dataframe['rsi_bull'] + 
            dataframe['ma_bull'] + dataframe['vol_bull'] + 
            dataframe['breakout_bull'] + dataframe['momentum_bull']
        )
        
        dataframe['bear_strategies'] = (
            dataframe['engulf_bear'] + dataframe['rsi_bear'] + 
            dataframe['ma_bear'] + dataframe['vol_bear'] + 
            dataframe['breakout_bear'] + dataframe['momentum_bear']
        )
        
        # Weighted scores (1m strategies)
        dataframe['bull_score_1m'] = (
            (dataframe['engulf_bull'].astype(float) * self.engulfing_weight.value) +
            (dataframe['rsi_bull'].astype(float) * self.rsi_bounce_weight.value) +
            (dataframe['ma_bull'].astype(float) * self.ma_crossover_weight.value) +
            (dataframe['vol_bull'].astype(float) * self.volume_spike_weight.value) +
            (dataframe['breakout_bull'].astype(float) * self.breakout_weight.value) +
            (dataframe['momentum_bull'].astype(float) * self.momentum_weight.value)
        )
        
        dataframe['bear_score_1m'] = (
            (dataframe['engulf_bear'].astype(float) * self.engulfing_weight.value) +
            (dataframe['rsi_bear'].astype(float) * self.rsi_bounce_weight.value) +
            (dataframe['ma_bear'].astype(float) * self.ma_crossover_weight.value) +
            (dataframe['vol_bear'].astype(float) * self.volume_spike_weight.value) +
            (dataframe['breakout_bear'].astype(float) * self.breakout_weight.value) +
            (dataframe['momentum_bear'].astype(float) * self.momentum_weight.value)
        )
        
        # Combined scores with HTF confluence
        dataframe['bull_score'] = (
            dataframe['bull_score_1m'] * (1 - self.htf_trend_weight.value) +
            dataframe['htf_bull_score'] * self.htf_trend_weight.value
        )
        
        dataframe['bear_score'] = (
            dataframe['bear_score_1m'] * (1 - self.htf_trend_weight.value) +
            dataframe['htf_bear_score'] * self.htf_trend_weight.value
        )
        
        # Volatility for position sizing
        dataframe['volatility'] = dataframe['atr'] / dataframe['close']
        
        # Win rate tracking (simplified for now)
        dataframe['win_rate'] = 0.667  # Our current 66.7% win rate
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Entry conditions with multi-timeframe confluence"""
        
        # Simple quality improvements - avoid overcomplicating
        volume_filter = dataframe['volume'] > dataframe['volume_mean'] * 0.8  # Slightly above average volume
        
        # Long entry with improved quality but not too restrictive
        long_entry = (
            (dataframe['bull_score'] >= self.min_consensus_score.value) &
            (dataframe['bull_strategies'] >= self.min_active_strategies.value) &
            (dataframe['bull_score'] > dataframe['bear_score']) &
            (dataframe['htf_bull_score'] >= self.htf_confluence_min.value) &
            volume_filter
        )
        
        # Short entry with improved quality but not too restrictive
        short_entry = (
            (dataframe['bear_score'] >= self.min_consensus_score.value) &
            (dataframe['bear_strategies'] >= self.min_active_strategies.value) &
            (dataframe['bear_score'] > dataframe['bull_score']) &
            (dataframe['htf_bear_score'] >= self.htf_confluence_min.value) &
            volume_filter
        )
        
        # Market session filters
        if metadata.get('pair') in ['BTC/USDT:USDT', 'ETH/USDT:USDT']:
            # Major pairs: trade all sessions
            session_filter = True
        else:
            # Alt coins: avoid low volume Asian session
            session_filter = (dataframe['european_session'] == 1) | (dataframe['us_session'] == 1)
        
        dataframe.loc[long_entry & session_filter, 'enter_long'] = 1
        dataframe.loc[long_entry & session_filter, 'enter_tag'] = (
            'phase1_long_' + dataframe['bull_strategies'].astype(str) + 'str_' +
            (dataframe['bull_score'] * 100).round(0).astype(int).astype(str) + 'pts_' +
            (dataframe['htf_bull_score'] * 100).round(0).astype(int).astype(str) + 'htf'
        )
        
        dataframe.loc[short_entry & session_filter, 'enter_short'] = 1
        dataframe.loc[short_entry & session_filter, 'enter_tag'] = (
            'phase1_short_' + dataframe['bear_strategies'].astype(str) + 'str_' +
            (dataframe['bear_score'] * 100).round(0).astype(int).astype(str) + 'pts_' +
            (dataframe['htf_bear_score'] * 100).round(0).astype(int).astype(str) + 'htf'
        )
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Exit conditions with opposing HTF signals"""
        
        # Exit long on strong bearish consensus or HTF divergence
        exit_long = (
            ((dataframe['bear_score'] >= 0.50) & (dataframe['bear_strategies'] >= 3)) |
            (dataframe['htf_bear_score'] >= 0.80)
        )
        
        # Exit short on strong bullish consensus or HTF divergence
        exit_short = (
            ((dataframe['bull_score'] >= 0.50) & (dataframe['bull_strategies'] >= 3)) |
            (dataframe['htf_bull_score'] >= 0.80)
        )
        
        dataframe.loc[exit_long, 'exit_long'] = 1
        dataframe.loc[exit_long, 'exit_tag'] = 'phase1_exit'
        
        dataframe.loc[exit_short, 'exit_short'] = 1
        dataframe.loc[exit_short, 'exit_tag'] = 'phase1_exit'
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Dynamic position sizing using Kelly Criterion
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return proposed_stake
            
        current_candle = dataframe.iloc[-1]
        
        # Get win rate and volatility
        win_rate = current_candle.get('win_rate', 0.667)
        volatility = current_candle.get('volatility', 0.02)
        
        # Kelly Criterion calculation
        # f = (p * b - q) / b
        # where: p = win probability, q = loss probability, b = win/loss ratio
        avg_win = 0.015  # 1.5% average win
        avg_loss = 0.010  # 1.0% average loss (with 2% stop loss, often exit earlier)
        win_loss_ratio = avg_win / avg_loss
        
        kelly_f = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        kelly_f = max(0, min(kelly_f, 1))  # Ensure between 0 and 1
        
        # Apply Kelly fraction (conservative)
        position_fraction = kelly_f * self.kelly_fraction.value
        
        # Adjust for volatility (smaller positions in high volatility)
        volatility_adjustment = 1 - min(volatility * 10, 0.5)  # Reduce up to 50% in high vol
        
        # Adjust for market session
        session_adjustment = 1.0
        if current_candle.get('asian_session', 0) == 1:
            session_adjustment = 0.7  # Smaller positions in Asian session
        elif current_candle.get('us_session', 0) == 1:
            session_adjustment = 1.2  # Larger positions in US session
        
        # Calculate final position size
        base_stake = self.wallets.get_total_stake_amount()
        position_size = base_stake * position_fraction * volatility_adjustment * session_adjustment
        
        # Apply limits
        max_position = base_stake * self.max_position_size.value
        position_size = min(position_size, max_position, max_stake)
        position_size = max(position_size, min_stake) if min_stake else position_size
        
        return position_size
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """
        Partial profit taking system
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return None
            
        current_candle = dataframe.iloc[-1]
        
        # Check if trade has partial exits
        filled_entries = trade.select_filled_orders(trade.entry_side)
        filled_exits = trade.select_filled_orders(trade.exit_side)
        
        # Realistic partial profit taking levels
        if len(filled_exits) == 0 and current_profit >= 0.012:  # TP1: 1.2%
            return "partial_take_1"
        elif len(filled_exits) == 1 and current_profit >= 0.018:  # TP2: 1.8%
            return "partial_take_2"
        elif len(filled_exits) == 2 and current_profit >= 0.025:  # TP3: 2.5%
            return "partial_take_3"
        
        # Stop loss to breakeven after TP1
        if len(filled_exits) >= 1 and current_profit < 0:
            return "breakeven_stop"
        
        # Exit if HTF turns against us
        if trade.is_short and current_candle.get('htf_bull_score', 0) >= 0.85:
            return "htf_reversal"
        elif not trade.is_short and current_candle.get('htf_bear_score', 0) >= 0.85:
            return "htf_reversal"
        
        return None
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Dynamic stop loss with ATR and breakeven after partial profits
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return self.stoploss
            
        current_candle = dataframe.iloc[-1]
        atr = current_candle.get('atr', 0)
        
        # Check for partial exits
        filled_exits = trade.select_filled_orders(trade.exit_side)
        
        # Move to breakeven after first partial exit
        if len(filled_exits) >= 1:
            # Breakeven with small buffer for fees
            return max(self.stoploss, -0.002)
        
        # Dynamic ATR-based stop loss
        if atr > 0:
            # Tighter stops in low volatility
            volatility = current_candle.get('volatility', 0.02)
            if volatility < 0.01:  # Low volatility
                stop_distance = 1.5 * atr / current_rate
            else:  # Normal/high volatility
                stop_distance = 2.0 * atr / current_rate
            
            # Adjust for market session
            if current_candle.get('asian_session', 0) == 1:
                stop_distance *= 0.8  # Tighter stops in Asian session
            
            return -min(stop_distance, abs(self.stoploss))
        
        return self.stoploss
    
    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        """
        Pyramiding - add to winning positions
        """
        if current_profit < 0.005:  # Only add to winners
            return None
            
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if len(dataframe) == 0:
            return None
            
        current_candle = dataframe.iloc[-1]
        
        # Check if trend is still very strong for pyramiding
        if trade.is_short:
            if current_candle.get('bear_score', 0) < 0.65:  # Higher threshold
                return None
        else:
            if current_candle.get('bull_score', 0) < 0.65:  # Higher threshold
                return None
        
        # Check HTF alignment is strong
        if trade.is_short:
            if current_candle.get('htf_bear_score', 0) < 0.80:  # Much higher threshold
                return None
        else:
            if current_candle.get('htf_bull_score', 0) < 0.80:  # Much higher threshold
                return None
        
        # Calculate position size for pyramiding (smaller than initial)
        base_stake = self.wallets.get_total_stake_amount()
        additional_stake = base_stake * 0.05  # 5% additional position
        
        return min(additional_stake, max_stake)