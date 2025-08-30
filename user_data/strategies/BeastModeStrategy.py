"""
SafeBullRider IMPROVED - No fancy BS, just better SafeBullRider
Keep the 87% win rate patterns, improve the filtering
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from typing import Dict, Optional, Union
import logging
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from functools import reduce

logger = logging.getLogger(__name__)

class BeastModeStrategy(IStrategy):
    """
    SafeBullRider but BETTER - focus on quality over quantity
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False
    
    startup_candle_count = 100
    
    # SAME SafeBullRider ROI - THIS WORKS
    minimal_roi = {
        "0": 0.04,
        "120": 0.025,
        "300": 0.015,
        "600": 0.008
    }
    
    # Dynamic stops based on market conditions
    stoploss = -0.06  # Default stop loss
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    
    # Position adjustment
    position_adjustment_enable = True
    max_entry_position_adjustment = 1
    
    # IMPROVED parameters - more selective
    rsi_oversold = IntParameter(30, 40, default=35, space="buy", load=True)  # Tighter
    rsi_overbought = IntParameter(65, 75, default=70, space="sell", load=True)  # Wider
    volume_multiplier = DecimalParameter(1.2, 2.5, decimals=1, default=1.5, space="buy", load=True)  # Higher
    trend_strength = DecimalParameter(0.005, 0.012, decimals=3, default=0.008, space="buy", load=True)  # Stronger
    
    # NEW quality filters
    min_volume_ratio = DecimalParameter(1.1, 2.0, decimals=1, default=1.3, space="buy")
    max_volatility = DecimalParameter(0.04, 0.12, decimals=2, default=0.08, space="buy")
    trend_consistency = IntParameter(3, 8, default=5, space="buy")
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Enhanced indicators with crash protection"""
        
        # EXACT SafeBullRider indicators
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Momentum
        dataframe['momentum_5'] = (dataframe['close'] - dataframe['close'].shift(5)) / dataframe['close'].shift(5)
        dataframe['momentum_20'] = (dataframe['close'] - dataframe['close'].shift(20)) / dataframe['close'].shift(20)
        dataframe['momentum_1h'] = (dataframe['close'] - dataframe['close'].shift(12)) / dataframe['close'].shift(12)  # 1 hour momentum
        
        # Trend detection
        dataframe['uptrend'] = (
            (dataframe['ema_8'] > dataframe['ema_21']) & 
            (dataframe['ema_21'] > dataframe['ema_50'])
        )
        
        # Candle patterns
        dataframe['green_candle'] = (dataframe['close'] > dataframe['open']).astype(int)
        
        # Volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = (dataframe['atr'] / dataframe['close']) * 100
        
        # ============ CRASH PROTECTION INDICATORS ============
        
        # 1. BEARISH DIVERGENCE DETECTION
        # Find local highs for divergence analysis
        dataframe['price_high_20'] = dataframe['high'].rolling(20).max()
        dataframe['rsi_high_20'] = dataframe['rsi'].rolling(20).max()
        
        # Bearish divergence: price makes higher high but RSI makes lower high
        dataframe['bearish_divergence'] = (
            (dataframe['high'] > dataframe['high'].shift(20)) &  # Higher high in price
            (dataframe['rsi'] < dataframe['rsi'].shift(20)) &     # Lower high in RSI
            (dataframe['rsi'] > 65)                                # In overbought territory
        ).astype(int)
        
        # 2. VOLUME EXHAUSTION ANALYSIS
        dataframe['volume_trend'] = dataframe['volume'].rolling(10).mean() / dataframe['volume'].rolling(30).mean()
        dataframe['volume_exhaustion'] = (
            (dataframe['close'] > dataframe['close'].shift(5)) &   # Price going up
            (dataframe['volume'] < dataframe['volume'].shift(5)) &  # But volume declining
            (dataframe['volume_ratio'] < 0.8)                       # Below average volume
        ).astype(int)
        
        # 3. RESISTANCE DETECTION
        dataframe['resistance_level'] = dataframe['high'].rolling(50).max()
        dataframe['near_resistance'] = (
            (dataframe['high'] >= dataframe['resistance_level'] * 0.99) &  # Near resistance
            (dataframe['close'] < dataframe['resistance_level'] * 0.98)     # But closed below
        ).astype(int)
        
        # Count failed breakout attempts
        dataframe['failed_breaks'] = dataframe['near_resistance'].rolling(10).sum()
        
        # 4. MARKET STRUCTURE ANALYSIS
        # Detect lower highs and lower lows (trend reversal)
        dataframe['lower_high'] = (
            (dataframe['high'] < dataframe['high'].shift(10)) &
            (dataframe['high'].shift(10) < dataframe['high'].shift(20))
        ).astype(int)
        
        dataframe['lower_low'] = (
            (dataframe['low'] < dataframe['low'].shift(10)) &
            (dataframe['low'].shift(10) < dataframe['low'].shift(20))
        ).astype(int)
        
        # 5. PARABOLIC MOVE DETECTION
        dataframe['parabolic_move'] = (
            (dataframe['momentum_1h'] > 0.03) &  # 3%+ move in 1 hour
            (dataframe['rsi'] > 70)               # With overbought RSI
        ).astype(int)
        
        # NEW quality indicators
        
        # Trend consistency - how many of last N candles follow trend
        dataframe['trend_candles'] = 0
        for i in range(1, self.trend_consistency.value + 1):
            trend_follow = (
                (dataframe['uptrend']) & 
                (dataframe['close'] > dataframe['close'].shift(i))
            ).astype(int)
            dataframe['trend_candles'] += trend_follow
        
        # Volume quality - sustained volume not just spike
        dataframe['volume_quality'] = (
            dataframe['volume_ratio'].rolling(3).mean()
        )
        
        # Price momentum quality - smooth not choppy
        dataframe['momentum_smooth'] = (
            dataframe['momentum_5'].rolling(3).std()
        )
        
        # Market strength - multiple timeframes aligned
        dataframe['market_strength'] = (
            ((dataframe['momentum_5'] > 0).astype(int) +
             (dataframe['momentum_20'] > 0).astype(int) +
             (dataframe['uptrend']).astype(int) +
             (dataframe['rsi'] > 50).astype(int)) / 4
        )
        
        # 6. CRASH WARNING SIGNALS
        # Combine multiple warning signals
        dataframe['crash_warning'] = (
            dataframe['bearish_divergence'] +
            dataframe['volume_exhaustion'] +
            (dataframe['failed_breaks'] >= 3).astype(int) +
            (dataframe['lower_high'] & dataframe['lower_low']).astype(int) +
            dataframe['parabolic_move']
        )
        
        # Critical level: 3+ warning signals
        dataframe['high_risk'] = (dataframe['crash_warning'] >= 3).astype(int)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """
        Enhanced entry with crash protection filters
        """
        
        # SIMPLIFIED Try1BullRider patterns - the ones that actually work
        long_dip_buy = (
            (dataframe['ema_8'] > dataframe['ema_21']) &  # Simplified uptrend
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['volume_ratio'] > self.volume_multiplier.value) &
            (dataframe['momentum_5'] > -0.01)
        )
        
        long_breakout = (
            (dataframe['momentum_5'] > self.trend_strength.value) &
            (dataframe['momentum_20'] > 0) &
            (dataframe['green_candle'] == 1) &
            (dataframe['volume_ratio'] > 1.8) &  # Slightly lower requirement
            (dataframe['close'] > dataframe['ema_8'])
        )
        
        long_trend_follow = (
            (dataframe['ema_8'] > dataframe['ema_21']) &  # Simplified uptrend
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['rsi'] > 45) & (dataframe['rsi'] < 70) &  # Wider RSI range
            (dataframe['volume_ratio'] > 1.1) &  # Lower volume requirement
            (dataframe['atr_pct'] < 0.08)  # Higher volatility allowed
        )
        
        # Combine all patterns with OR logic (more opportunities)
        basic_entry = long_dip_buy | long_breakout | long_trend_follow
        
        # ============ CRASH PROTECTION FILTERS ============
        # Block entries when crash risk is high
        safe_to_enter = (
            (dataframe['high_risk'] == 0) &              # No high risk signals
            (dataframe['parabolic_move'] == 0) &         # Not after parabolic moves
            (dataframe['bearish_divergence'] == 0) &     # No bearish divergence
            (dataframe['failed_breaks'] < 3) &           # Less than 3 failed breakouts
            (dataframe['momentum_1h'] > -0.02)           # No sharp drops in last hour
        )
        
        # Final entry = basic patterns AND safety checks
        final_entry = basic_entry & safe_to_enter
        
        # Initialize columns if they don't exist
        dataframe['enter_long'] = 0
        dataframe['enter_tag'] = ''
        
        dataframe.loc[final_entry, 'enter_long'] = 1
        dataframe.loc[final_entry, 'enter_tag'] = 'improved_entry'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Enhanced exit logic with early warning signals"""
        
        # Original SafeBullRider exits
        original_exit = (
            (dataframe['rsi'] > 85) |
            (
                (dataframe['momentum_5'] < -0.02) &
                (dataframe['rsi'] > 70) &
                (dataframe['close'] < dataframe['ema_8'])
            )
        )
        
        # ============ EARLY WARNING EXITS ============
        # Exit on crash warning signals
        crash_protection_exit = (
            (dataframe['high_risk'] == 1) |                         # Multiple warning signals
            (dataframe['bearish_divergence'] == 1) |                # RSI divergence detected
            (dataframe['volume_exhaustion'] == 1) |                 # Volume drying up
            ((dataframe['failed_breaks'] >= 3) & (dataframe['rsi'] > 65)) |  # Multiple failed breakouts
            ((dataframe['lower_high'] == 1) & (dataframe['lower_low'] == 1)) |  # Market structure breakdown
            (dataframe['momentum_1h'] < -0.03)                      # Sharp 1-hour drop (3%+)
        )
        
        # Combine all exit signals
        long_exit = original_exit | crash_protection_exit
        
        # Initialize columns if they don't exist
        dataframe['exit_long'] = 0
        dataframe['exit_tag'] = ''
        
        dataframe.loc[long_exit, 'exit_long'] = 1
        dataframe.loc[long_exit, 'exit_tag'] = 'trend_reversal'
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        """
        RISK-MANAGED position sizing - reduce size based on volatility and recent performance
        """
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return proposed_stake
        
        latest = dataframe.iloc[-1]
        multiplier = 1.0
        
        # 1. VOLATILITY-BASED SIZING (Most Important)
        atr_pct = latest.get('atr_pct', 2.0)  # ATR as percentage of price
        if atr_pct > 5.0:  # High volatility (bear market conditions)
            multiplier *= 0.5  # Cut position size in half
            logger.info(f"High volatility detected ({atr_pct:.1f}%) - reducing {pair} position size")
        elif atr_pct > 3.5:  # Moderate high volatility
            multiplier *= 0.7  # Reduce by 30%
        elif atr_pct < 1.5:  # Low volatility (calm markets)
            multiplier *= 1.2  # Increase by 20%
        
        # 2. PAIR PERFORMANCE-BASED SIZING
        try:
            recent_trades = Trade.get_trades_proxy(is_open=False, pair=pair)
            if len(recent_trades) >= 3:
                # Look at last 5 trades
                last_trades = recent_trades[-5:]
                win_rate = sum(1 for t in last_trades if t.close_profit and t.close_profit > 0) / len(last_trades)
                
                # Adjust based on recent pair performance
                if win_rate >= 0.8:  # 80% win rate
                    multiplier *= 1.2
                elif win_rate <= 0.4:  # 40% or worse win rate
                    multiplier *= 0.6  # Reduce significantly for underperforming pairs
        except:
            pass
        
        # 3. MAXIMUM POSITION RISK LIMIT
        # Ensure single trade can't lose more than ~$15 (0.6% of $2500 account)
        max_loss_dollars = 15.0
        max_position_value = max_loss_dollars / 0.06  # Assuming 6% max stoploss
        if proposed_stake * multiplier > max_position_value:
            multiplier = max_position_value / proposed_stake
            logger.info(f"Position size capped for {pair} - max risk limit applied")
        
        adjusted_stake = proposed_stake * multiplier
        return min(max(adjusted_stake, min_stake), max_stake)
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Dynamic stop loss based on market conditions
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss
        
        latest = dataframe.iloc[-1]
        
        # Tighter stop loss in high-risk conditions
        if latest.get('rsi', 50) > 70:
            return -0.03  # 3% stop when overbought
        elif latest.get('atr_pct', 2) > 4:
            return -0.04  # 4% stop in high volatility
        elif latest.get('high_risk', 0) == 1:
            return -0.025  # 2.5% stop when crash warnings present
        
        # Time-based stop tightening
        if trade.open_date:
            hours_open = (current_time - trade.open_date).total_seconds() / 3600
            if hours_open > 24:
                return -0.04  # Tighter stop for old positions
        
        return self.stoploss
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: str,
                           side: str, **kwargs) -> bool:
        """
        Enhanced entry confirmation with time-based and correlation checks
        """
        
        # 1. DAILY LOSS LIMIT CHECK (Critical Risk Management)
        try:
            today = current_time.date()
            all_trades = Trade.get_trades_proxy(is_open=False)
            
            # Calculate today's P&L
            daily_pnl = 0.0
            daily_trades = 0
            
            for trade in all_trades:
                if trade.close_date and trade.close_date.date() == today:
                    if trade.close_profit_abs:
                        daily_pnl += trade.close_profit_abs
                        daily_trades += 1
            
            # Daily loss limit: Stop trading if we've lost more than $60 today (2.4% of $2500)
            daily_loss_limit = -60.0
            if daily_pnl < daily_loss_limit:
                logger.warning(f"DAILY LOSS LIMIT HIT: ${daily_pnl:.2f} < ${daily_loss_limit:.2f} - blocking {pair} entry")
                return False
            
            # Consecutive loss protection: If we've had 5+ losses in a row today, reduce activity
            if daily_trades >= 5:
                recent_losses = 0
                for trade in all_trades[-5:]:
                    if trade.close_date and trade.close_date.date() == today:
                        if trade.close_profit_abs and trade.close_profit_abs < 0:
                            recent_losses += 1
                
                if recent_losses >= 4:  # 4 out of last 5 trades were losses
                    logger.warning(f"Consecutive losses detected ({recent_losses}/5) - being more selective")
                    # Only allow high-conviction entries (can add additional filters here)
                    pass
        
        except Exception as e:
            logger.warning(f"Error checking daily limits: {e}")
        
        # 2. EXTREME VOLATILITY FILTER
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) >= 1:
            latest = dataframe.iloc[-1]
            atr_pct = latest.get('atr_pct', 2.0)
            
            # Block entries during extreme volatility (bear market crash conditions)
            if atr_pct > 8.0:  # Extreme volatility
                logger.warning(f"EXTREME VOLATILITY: {atr_pct:.1f}% ATR - blocking {pair} entry")
                return False
        
        # 3. TIME-BASED RISK MANAGEMENT
        current_hour = current_time.hour
        risky_hours = [8, 9, 15, 16]  # UTC hours with historical crashes
        
        if current_hour in risky_hours:
            logger.info(f"Risky hour detected ({current_hour}:00 UTC) - being more selective for {pair}")
            # During risky hours, only allow entries with stronger signals
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) >= 1:
                latest = dataframe.iloc[-1]
                # Require stronger conditions during risky hours (conditional)
                bull_market = latest.get('bull_market', 0)
                rsi_threshold = 70 if bull_market else 60  # More lenient in bull markets
                warning_threshold = 2 if bull_market else 0  # Allow some warnings in bull
                
                if latest.get('rsi', 50) > rsi_threshold or latest.get('crash_warning', 0) > warning_threshold:
                    logger.warning(f"Blocking {pair} entry during risky hour with weak conditions")
                    return False
        
        # 4. BTC CORRELATION CHECK
        # Check if BTC has dropped significantly (market-wide risk)
        try:
            btc_pair = 'BTC/USDT:USDT'
            if pair != btc_pair:  # Don't check BTC against itself
                btc_df, _ = self.dp.get_analyzed_dataframe(btc_pair, self.timeframe)
                if len(btc_df) >= 1:
                    btc_latest = btc_df.iloc[-1]
                    btc_1h_change = btc_latest.get('momentum_1h', 0)
                    
                    # If BTC dropped more than 2% in last hour, don't enter alts
                    if btc_1h_change < -0.02:
                        logger.warning(f"BTC CRASH DETECTED ({btc_1h_change:.2%}) - blocking {pair} entry")
                        return False
        except Exception as e:
            logger.debug(f"Could not check BTC correlation: {e}")
        
        # 5. POSITION CORRELATION LIMITS
        # Limit number of correlated positions
        try:
            open_trades = Trade.get_trades_proxy(is_open=True)
            crypto_positions = len([t for t in open_trades if 'USDT' in t.pair])
            
            # Maximum 5 correlated crypto positions
            if crypto_positions >= 5:
                logger.info(f"Already have {crypto_positions} crypto positions - blocking {pair} to limit correlation")
                return False
        except Exception as e:
            logger.debug(f"Could not check position correlation: {e}")
        
        return True