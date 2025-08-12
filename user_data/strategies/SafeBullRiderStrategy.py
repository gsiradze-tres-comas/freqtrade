"""
Safe Bull Rider Strategy - Enhanced with Risk Management
Based on Try1BullRiderStrategy but with critical safety features:
- Daily loss limits to prevent cascade losses
- Market correlation checks
- Time-based entry restrictions
- Volatility-based position sizing
- Maximum correlated positions limit
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
from freqtrade.exchange import timeframe_to_minutes
from functools import reduce

logger = logging.getLogger(__name__)

class SafeBullRiderStrategy(IStrategy):
    """
    Enhanced bull market strategy with risk management
    Prevents cascade losses like the Aug 11 crash that dropped 3% in minutes
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False  # DISABLE SHORTS IN BULL MARKETS
    
    # Need startup candles for EMA 50, rolling windows, ATR
    startup_candle_count = 100
    
    # Risk Management Parameters (OPTIMIZED FOR PROFIT)
    max_daily_loss_pct = 0.05  # 5% max daily loss (more room for recovery)
    max_monthly_loss_pct = 0.15  # 15% max monthly loss (allows volatility)
    max_correlated_positions = 15  # Match config max_open_trades
    low_liquidity_hours = []  # Trade 24/7 in bull markets!
    high_volatility_stop_reduction = 0.75  # Less aggressive stop tightening
    max_positions_in_drawdown = 10  # More positions allowed
    
    # Trade Frequency Controls (UNLEASH THE BEAST)
    max_trades_per_day = 999  # Unlimited daily trades
    min_minutes_between_trades = 5  # Only 5 minutes between trades
    cooldown_after_loss_minutes = 30  # Only 30 minutes after loss
    max_trades_per_symbol_daily = 999  # Unlimited per symbol
    
    # OPTIMIZED ROI for bull market profits
    minimal_roi = {
        "0": 0.08,    # 8% target (let winners run!)
        "60": 0.05,   # 5% after 1 hour
        "180": 0.03,  # 3% after 3 hours
        "360": 0.02,  # 2% after 6 hours
        "720": 0.015  # 1.5% after 12 hours (not 0.8%!)
    }
    
    # DYNAMIC stop loss (adjusted based on volatility)
    stoploss = -0.04  # 4% base stop loss
    
    # AGGRESSIVE trailing stop to capture big moves
    trailing_stop = True
    trailing_stop_positive = 0.005   # Start trailing at 0.5% profit
    trailing_stop_positive_offset = 0.015   # Trail by 1.5% (tighter)
    trailing_only_offset_is_reached = False  # Trail immediately!
    
    # Position adjustment for bull markets
    position_adjustment_enable = True
    max_entry_position_adjustment = 1  # Scale in once
    
    # Strategy parameters
    rsi_oversold = IntParameter(35, 45, default=40, space="buy", load=True)
    rsi_overbought = IntParameter(60, 70, default=65, space="sell", load=True)
    volume_multiplier = DecimalParameter(0.8, 1.5, decimals=1, default=1.2, space="buy", load=True)
    trend_strength = DecimalParameter(0.003, 0.008, decimals=3, default=0.005, space="buy", load=True)
    
    # Risk parameters (RELAXED for more opportunities)
    btc_correlation_threshold = DecimalParameter(-0.02, -0.01, decimals=3, default=-0.018, space="buy", load=True)
    volatility_threshold = DecimalParameter(0.02, 0.04, decimals=3, default=0.035, space="buy", load=True)
    
    # Plot configuration for FreqUI visualization
    plot_config = {
        'main_plot': {
            'ema_8': {'color': 'blue', 'type': 'line'},
            'ema_21': {'color': 'orange', 'type': 'line'},
            'ema_50': {'color': 'red', 'type': 'line'},
        },
        'subplots': {
            "RSI": {
                'rsi': {'color': 'purple'},
            },
            "Volume": {
                'volume': {'color': 'gray', 'type': 'bar'},
                'volume_mean': {'color': 'blue', 'type': 'line'},
            },
            "Risk": {
                'market_risk': {'color': 'red', 'type': 'line'},
                'volatility': {'color': 'orange', 'type': 'line'},
            }
        }
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Enhanced indicators with risk metrics"""
        
        # Basic EMAs for trend
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_mean'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']
        
        # Price momentum
        dataframe['momentum_5'] = dataframe['close'].pct_change(periods=5)
        dataframe['momentum_20'] = dataframe['close'].pct_change(periods=20)
        
        # VOLATILITY METRICS (NEW)
        dataframe['volatility'] = dataframe['close'].pct_change().rolling(window=20).std()
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
        
        # MARKET BREADTH (NEW)
        # Simulate market correlation (in production, would use BTC price)
        dataframe['price_change_1h'] = dataframe['close'].pct_change(periods=12)  # 1 hour change
        dataframe['price_change_4h'] = dataframe['close'].pct_change(periods=48)  # 4 hour change
        
        # Market risk indicator
        dataframe['market_risk'] = (
            (dataframe['volatility'] > dataframe['volatility'].rolling(window=100).mean() * 1.5).astype(int) +
            (dataframe['volume_ratio'] > 2).astype(int) +
            (dataframe['price_change_1h'] < -0.02).astype(int)
        ) / 3.0
        
        # Trend metrics
        dataframe['uptrend'] = (
            (dataframe['ema_8'] > dataframe['ema_21']) &
            (dataframe['ema_21'] > dataframe['ema_50']) &
            (dataframe['momentum_5'] > 0)
        ).astype(int)
        
        dataframe['downtrend'] = (
            (dataframe['ema_8'] < dataframe['ema_21']) &
            (dataframe['ema_21'] < dataframe['ema_50']) &
            (dataframe['momentum_5'] < 0)
        ).astype(int)
        
        return dataframe

    def check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit has been reached"""
        try:
            # Get today's closed trades
            today = datetime.now().date()
            closed_trades = Trade.get_trades_proxy(is_open=False)
            
            daily_loss = 0
            for trade in closed_trades:
                if trade.close_date and trade.close_date.date() == today:
                    if trade.close_profit:
                        daily_loss += min(0, trade.close_profit_abs)
            
            # Check if loss exceeds limit (assuming 10000 starting balance)
            if abs(daily_loss) > (10000 * self.max_daily_loss_pct):
                logger.warning(f"Daily loss limit reached: ${abs(daily_loss):.2f}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            
        return True
    
    def check_monthly_loss_limit(self) -> bool:
        """Check if monthly loss limit has been reached"""
        try:
            # Get current month trades
            now = datetime.now()
            month_start = datetime(now.year, now.month, 1)
            closed_trades = Trade.get_trades_proxy(is_open=False)
            
            monthly_loss = 0
            for trade in closed_trades:
                if trade.close_date and trade.close_date >= month_start:
                    if trade.close_profit:
                        monthly_loss += min(0, trade.close_profit_abs)
            
            # Check if loss exceeds monthly limit
            if abs(monthly_loss) > (10000 * self.max_monthly_loss_pct):
                logger.warning(f"Monthly loss limit reached: ${abs(monthly_loss):.2f}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking monthly loss limit: {e}")
            
        return True
    
    def check_trade_frequency(self, pair: str) -> bool:
        """Check if we're trading too frequently"""
        try:
            now = datetime.now()
            today = now.date()
            
            # Check all trades (open and closed) from today
            all_trades = Trade.get_trades_proxy()
            
            # Count today's trades
            today_trades = 0
            symbol_trades = 0
            last_trade_time = None
            last_loss_time = None
            
            for trade in all_trades:
                # Check if trade opened today
                if trade.open_date and trade.open_date.date() == today:
                    today_trades += 1
                    
                    # Count trades for this specific symbol
                    if trade.pair == pair:
                        symbol_trades += 1
                    
                    # Track last trade time
                    if last_trade_time is None or trade.open_date > last_trade_time:
                        last_trade_time = trade.open_date
                    
                    # Track last loss time
                    if trade.close_date and trade.close_profit and trade.close_profit < 0:
                        if last_loss_time is None or trade.close_date > last_loss_time:
                            last_loss_time = trade.close_date
            
            # Check daily trade limit
            if today_trades >= self.max_trades_per_day:
                logger.info(f"Daily trade limit reached: {today_trades}/{self.max_trades_per_day}")
                return False
            
            # Check symbol-specific daily limit
            if symbol_trades >= self.max_trades_per_symbol_daily:
                logger.info(f"Symbol daily limit reached for {pair}: {symbol_trades}/{self.max_trades_per_symbol_daily}")
                return False
            
            # Check minimum time between trades
            if last_trade_time:
                minutes_since_last = (now - last_trade_time).total_seconds() / 60
                if minutes_since_last < self.min_minutes_between_trades:
                    logger.info(f"Too soon since last trade: {minutes_since_last:.1f} minutes")
                    return False
            
            # Check cooldown after loss
            if last_loss_time:
                minutes_since_loss = (now - last_loss_time).total_seconds() / 60
                if minutes_since_loss < self.cooldown_after_loss_minutes:
                    logger.info(f"Cooldown after loss: {minutes_since_loss:.1f} minutes")
                    return False
            
        except Exception as e:
            logger.error(f"Error checking trade frequency: {e}")
        
        return True

    def check_market_conditions(self, dataframe: DataFrame) -> bool:
        """Check if market conditions are safe for trading"""
        last_row = dataframe.iloc[-1]
        
        # Check volatility
        if last_row['volatility'] > self.volatility_threshold.value:
            logger.info(f"High volatility detected: {last_row['volatility']:.4f}")
            return False
        
        # Check market risk score
        if last_row['market_risk'] > 0.6:
            logger.info(f"High market risk: {last_row['market_risk']:.2f}")
            return False
        
        # Check for market-wide selloff (simulated with price change)
        if last_row['price_change_1h'] < self.btc_correlation_threshold.value:
            logger.info(f"Market selloff detected: {last_row['price_change_1h']:.4f}")
            return False
        
        return True

    def check_time_restrictions(self) -> bool:
        """Check if current time is suitable for trading"""
        current_hour = datetime.now().hour
        
        # Check for low liquidity hours (OPTIMIZED - only 3-4 AM)
        for start_hour, end_hour in [(3, 4)]:  # Further reduced to 3-4 AM only
            if start_hour <= current_hour < end_hour:
                logger.info(f"Low liquidity hour: {current_hour}:00 UTC - blocking trades")
                return False
        
        # Block weekend trading (important for risk management)
        if datetime.now().weekday() >= 5:  # Saturday = 5, Sunday = 6
            logger.info("Weekend trading disabled")
            return False
            
        return True

    def count_correlated_positions(self) -> int:
        """Count currently open correlated positions"""
        try:
            open_trades = Trade.get_trades_proxy(is_open=True)
            # In crypto, most pairs are correlated, so count all open positions
            return len(open_trades)
        except Exception as e:
            logger.error(f"Error counting positions: {e}")
            return 0
    
    def check_drawdown_status(self) -> bool:
        """Check if account is in drawdown"""
        try:
            today = datetime.now().date()
            closed_trades = Trade.get_trades_proxy(is_open=False)
            daily_pnl = sum(t.close_profit_abs for t in closed_trades 
                          if t.close_date and t.close_date.date() == today and t.close_profit_abs)
            return daily_pnl < 0  # True if losing today
        except:
            return False

    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Copy original strategy entry logic + add safety checks"""
        
        # SAME ENTRY LOGIC AS ORIGINAL TRY1BULLRIDERSTRATEGY
        
        # ENHANCED ENTRY PATTERNS for better profit capture
        
        # Pattern 1: RSI Oversold Bounce (high win rate)
        long_dip_buy = (
            (dataframe['uptrend']) &
            (dataframe['rsi'] < self.rsi_oversold.value) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &  # RSI turning up
            (dataframe['volume_ratio'] > self.volume_multiplier.value) &
            (dataframe['close'] > dataframe['ema_21'])  # Above medium-term trend
        )
        
        # Pattern 2: Momentum Breakout (catch strong moves)
        long_breakout = (
            (dataframe['momentum_5'] > self.trend_strength.value) &
            (dataframe['momentum_20'] > 0) &  # Long-term momentum positive
            (dataframe['uptrend'] == 1) &
            (dataframe['volume_ratio'] > 1.8) &  # Higher volume threshold
            (dataframe['close'] > dataframe['ema_8']) &
            (dataframe['rsi'] < 70)  # Not overbought yet
        )
        
        # Pattern 3: Trend Continuation (ride the trend)
        long_trend_follow = (
            (dataframe['uptrend']) &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['close'].shift(2)) &  # 2 green candles
            (dataframe['rsi'] > 50) & (dataframe['rsi'] < 65) &  # Healthy RSI range
            (dataframe['volume_ratio'] > 1.2) &  # Moderate volume increase
            (dataframe['atr_pct'] < 0.03)  # Not too volatile
        )
        
        # Pattern 4: Support Bounce (NEW - catch reversals)
        support_bounce = (
            (dataframe['close'] > dataframe['ema_50']) &  # Above long-term trend
            (dataframe['low'] <= dataframe['ema_21']) &  # Touched support
            (dataframe['close'] > dataframe['ema_21']) &  # Bounced above support
            (dataframe['volume_ratio'] > 1.5) &
            (dataframe['rsi'] > 35) & (dataframe['rsi'] < 60)
        )
        
        # COMBINE WITH OR LOGIC - including new support bounce pattern
        long_entry = long_dip_buy | long_breakout | long_trend_follow | support_bounce
        
        # DYNAMIC SAFETY CONDITIONS based on market state
        is_volatile = dataframe['volatility'] > self.volatility_threshold.value
        
        # Stricter safety in volatile markets, relaxed in calm markets
        safety_conditions = (
            (dataframe['market_risk'] < np.where(is_volatile, 0.6, 0.85)) &  # Dynamic threshold
            (dataframe['volatility'] < self.volatility_threshold.value * np.where(is_volatile, 1.5, 2.0)) &
            (dataframe['price_change_1h'] > self.btc_correlation_threshold.value * np.where(is_volatile, 0.5, 0.8))
        )
        
        # Apply safety filter to original logic (this is the key feature!)
        final_entry = long_entry & safety_conditions & (dataframe['volume'] > 0)
        
        # DEBUG: Log entry signals for troubleshooting
        if len(dataframe) > 0:
            last_row = dataframe.iloc[-1]
            if long_entry.iloc[-1]:
                logger.info(f"Entry signal detected but safety filter may block: "
                          f"market_risk={last_row['market_risk']:.3f}, "
                          f"volatility={last_row['volatility']:.4f}, "
                          f"price_change_1h={last_row['price_change_1h']:.4f}")
            
            if final_entry.iloc[-1]:
                logger.info(f"FINAL ENTRY SIGNAL GENERATED for {dataframe.index[-1]}")
        
        dataframe.loc[final_entry, ['enter_long', 'enter_tag']] = (1, 'safe_bull_long')
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """Enhanced sell signals with profit protection and smart exits"""
        
        # PROFIT TAKING EXIT (lock in gains)
        profit_exit = (
            (dataframe['rsi'] > self.rsi_overbought.value + 5) &  # RSI > 70
            (dataframe['momentum_5'] < 0) &  # Momentum turning negative
            (dataframe['volume_ratio'] < 0.8)  # Volume drying up
        )
        
        # TREND REVERSAL EXIT (protect from losses)
        trend_reversal = (
            (dataframe['downtrend'] == 1) &
            (dataframe['momentum_20'] < -0.01) &  # Strong negative momentum
            (dataframe['close'] < dataframe['ema_21'])  # Below medium-term trend
        )
        
        # TRAILING STOP EXIT (protect profits)
        trailing_exit = (
            (dataframe['close'] < dataframe['close'].rolling(10).max() * 0.97) &  # 3% from 10-bar high
            (dataframe['rsi'] < 50)  # RSI weakening
        )
        
        # EMERGENCY EXIT CONDITIONS (risk management)
        emergency_exit = (
            (dataframe['market_risk'] > 0.75) |  # Very high risk
            (dataframe['price_change_1h'] < -0.025) |  # 2.5% rapid drop
            (dataframe['volatility'] > self.volatility_threshold.value * 1.8) |  # Extreme volatility
            (dataframe['atr_pct'] > 0.05)  # 5% ATR - huge swings
        )
        
        # Set exit signals with priority
        dataframe.loc[emergency_exit, ['exit_long', 'exit_tag']] = (1, 'emergency_exit')
        dataframe.loc[profit_exit, ['exit_long', 'exit_tag']] = (1, 'profit_take')
        dataframe.loc[trend_reversal, ['exit_long', 'exit_tag']] = (1, 'trend_reversal')
        dataframe.loc[trailing_exit, ['exit_long', 'exit_tag']] = (1, 'trailing_stop')
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, 
                           rate: float, time_in_force: str, current_time: datetime,
                           entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """Final safety checks before entering a trade"""
        
        # Check monthly loss limit FIRST (highest priority)
        if not self.check_monthly_loss_limit():
            logger.warning(f"Rejecting {pair} - Monthly loss limit reached")
            return False
        
        # Check daily loss limit
        if not self.check_daily_loss_limit():
            logger.warning(f"Rejecting {pair} - Daily loss limit reached")
            return False
        
        # Check trade frequency limits (prevent overtrading)
        if not self.check_trade_frequency(pair):
            logger.info(f"Rejecting {pair} - Trade frequency limit reached")
            return False
        
        # Check time restrictions
        if not self.check_time_restrictions():
            logger.info(f"Rejecting {pair} - Time restriction active")
            return False
        
        # Check correlated positions limit (dynamic based on drawdown)
        current_positions = self.count_correlated_positions()
        max_allowed = self.max_positions_in_drawdown if self.check_drawdown_status() else self.max_correlated_positions
        
        if current_positions >= max_allowed:
            logger.info(f"Rejecting {pair} - Position limit reached ({current_positions}/{max_allowed})")
            return False
        
        # Get current dataframe for market condition check
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if not self.check_market_conditions(dataframe):
            logger.info(f"Rejecting {pair} - Poor market conditions")
            return False
        
        logger.info(f"Accepting {pair} entry - All safety checks passed")
        return True

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float, **kwargs) -> float:
        """Dynamic stop loss based on market conditions"""
        
        # Get current market data
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return self.stoploss
        
        last_row = dataframe.iloc[-1]
        
        # Tighten stop loss in high volatility
        if last_row['volatility'] > self.volatility_threshold.value:
            return self.stoploss * self.high_volatility_stop_reduction
        
        # Tighten stop loss if market risk is high
        if last_row['market_risk'] > 0.6:
            return self.stoploss * 0.75
        
        # Tighten stop loss during low liquidity hours
        current_hour = current_time.hour
        for start_hour, end_hour in self.low_liquidity_hours:
            if start_hour <= current_hour < end_hour:
                return self.stoploss * 0.5  # 2% stop instead of 4%
        
        return self.stoploss

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        """Emergency exits based on market conditions"""
        
        # Get current market data
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        
        last_row = dataframe.iloc[-1]
        
        # Emergency exit if market crashes
        if last_row['price_change_1h'] < -0.025:  # 2.5% drop in 1 hour
            logger.warning(f"Emergency exit {pair} - Market crash detected")
            return 'market_crash'
        
        # Exit if daily loss limit approaching
        try:
            today = datetime.now().date()
            closed_trades = Trade.get_trades_proxy(is_open=False)
            daily_loss = sum(min(0, t.close_profit_abs) for t in closed_trades 
                           if t.close_date and t.close_date.date() == today)
            
            if abs(daily_loss) > (10000 * self.max_daily_loss_pct * 0.8):  # 80% of limit
                logger.warning(f"Emergency exit {pair} - Approaching daily loss limit")
                return 'daily_limit_protection'
        except:
            pass
        
        return None

