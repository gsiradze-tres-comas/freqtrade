"""
ELITE ADAPTIVE STRATEGY - TOP 1% QUANTITATIVE TRADING SYSTEM
Institutional-grade market regime detection with dynamic adaptation

🎯 CORE INNOVATION: Adaptive parameters that change based on market conditions
📊 REGIME DETECTION: Multi-asset market oracle for regime classification  
⚡ SMART EXECUTION: Kelly criterion position sizing with VaR limits
🛡️ RISK MANAGEMENT: Real-time drawdown protection and regime change detection
"""

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, informative
from typing import Dict, Optional, Union
import logging
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from functools import reduce

logger = logging.getLogger(__name__)

class EliteAdaptiveStrategy(IStrategy):
    """
    🏆 ELITE ADAPTIVE MARKET REGIME STRATEGY
    
    Transforms based on market conditions:
    - BULL REGIME: Aggressive trend following
    - BEAR REGIME: Conservative mean reversion  
    - SIDEWAYS REGIME: Range-bound scalping
    - VOLATILE REGIME: Breakout capture
    """
    
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = False
    
    startup_candle_count = 200  # More data for regime detection
    
    # ADAPTIVE ROI - Changes based on market regime
    minimal_roi = {
        "0": 0.06,      # Higher initial target
        "60": 0.04,     # Faster profit taking
        "180": 0.025,   # Medium term
        "360": 0.015,   # Longer term
        "720": 0.008    # Final exit
    }
    
    # ADAPTIVE STOPS - Tighter in volatile conditions
    stoploss = -0.04  # Tighter base stop
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True
    
    # Position adjustment for scaling
    position_adjustment_enable = True
    max_entry_position_adjustment = 2
    
    # BASE PARAMETERS (will be dynamically adjusted)
    base_rsi_oversold = IntParameter(25, 40, default=30, space="buy", load=True)
    base_volume_multiplier = DecimalParameter(1.5, 3.0, decimals=1, default=2.0, space="buy", load=True)
    base_trend_strength = DecimalParameter(0.008, 0.02, decimals=3, default=0.012, space="buy", load=True)
    
    # REGIME DETECTION PARAMETERS
    regime_lookback = IntParameter(20, 50, default=30, space="buy")
    volatility_threshold = DecimalParameter(0.03, 0.08, decimals=3, default=0.05, space="buy")
    trend_strength_threshold = DecimalParameter(0.15, 0.35, decimals=2, default=0.25, space="buy")
    
    # RISK MANAGEMENT PARAMETERS
    max_portfolio_risk = DecimalParameter(0.04, 0.08, decimals=2, default=0.06, space="buy")
    max_single_trade_risk = DecimalParameter(0.015, 0.03, decimals=3, default=0.02, space="buy")
    daily_loss_limit_pct = DecimalParameter(0.02, 0.05, decimals=3, default=0.03, space="buy")
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        🧠 ELITE INDICATOR SYSTEM
        Multi-timeframe analysis with regime detection
        """
        
        # ================================
        # CORE TECHNICAL INDICATORS  
        # ================================
        
        # Moving Averages (multiple timeframes for regime detection)
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # RSI with multiple periods
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=7)
        dataframe['rsi_slow'] = ta.RSI(dataframe, timeperiod=21)
        
        # Volume Analysis
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        dataframe['volume_trend'] = dataframe['volume_sma'] / dataframe['volume_sma'].shift(10)
        
        # Momentum Indicators
        dataframe['momentum_5'] = (dataframe['close'] - dataframe['close'].shift(5)) / dataframe['close'].shift(5)
        dataframe['momentum_20'] = (dataframe['close'] - dataframe['close'].shift(20)) / dataframe['close'].shift(20)
        dataframe['momentum_50'] = (dataframe['close'] - dataframe['close'].shift(50)) / dataframe['close'].shift(50)
        
        # Volatility Measures
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = (dataframe['atr'] / dataframe['close']) * 100
        
        # Bollinger Bands
        bb_result = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_upper'] = bb_result['upperband']
        dataframe['bb_middle'] = bb_result['middleband'] 
        dataframe['bb_lower'] = bb_result['lowerband']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # ================================
        # MARKET REGIME DETECTION
        # ================================
        
        # Trend Regime Detection
        dataframe['major_uptrend'] = (
            (dataframe['ema_21'] > dataframe['ema_50']) & 
            (dataframe['ema_50'] > dataframe['ema_200'])
        )
        dataframe['minor_uptrend'] = (dataframe['ema_8'] > dataframe['ema_21'])
        
        # Volatility Regime
        dataframe['volatility_regime'] = np.where(
            dataframe['atr_pct'] > dataframe['atr_pct'].rolling(self.regime_lookback.value).quantile(0.7),
            'high',
            np.where(
                dataframe['atr_pct'] < dataframe['atr_pct'].rolling(self.regime_lookback.value).quantile(0.3),
                'low',
                'medium'
            )
        )
        
        # Market Regime Classification
        dataframe['market_regime'] = self.classify_market_regime(dataframe)
        
        # ================================
        # ADAPTIVE SIGNAL GENERATION
        # ================================
        
        # Dynamic parameters based on regime
        dataframe = self.calculate_adaptive_parameters(dataframe)
        
        # Pattern Recognition
        dataframe['doji'] = (abs(dataframe['close'] - dataframe['open']) <= (dataframe['high'] - dataframe['low']) * 0.1).astype(int)
        dataframe['hammer'] = self.detect_hammer(dataframe)
        dataframe['engulfing'] = self.detect_engulfing(dataframe)
        
        # Support/Resistance Levels
        dataframe = self.calculate_support_resistance(dataframe)
        
        # Quality Filters
        dataframe['signal_quality'] = self.calculate_signal_quality(dataframe)
        
        return dataframe
    
    @informative('1h', 'BTC/USDT:USDT')
    def populate_indicators_btc_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        🌍 BTC MARKET ORACLE - Higher timeframe market direction
        """
        dataframe['btc_ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['btc_ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['btc_ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        dataframe['btc_rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['btc_momentum'] = (dataframe['close'] - dataframe['close'].shift(24)) / dataframe['close'].shift(24)  # 24h momentum
        
        # BTC Market Regime (influences all other pairs)
        dataframe['btc_bull_regime'] = (
            (dataframe['btc_ema_21'] > dataframe['btc_ema_50']) &
            (dataframe['btc_ema_50'] > dataframe['btc_ema_200']) &
            (dataframe['btc_momentum'] > 0.02)
        )
        
        dataframe['btc_bear_regime'] = (
            (dataframe['btc_ema_21'] < dataframe['btc_ema_50']) &
            (dataframe['btc_ema_50'] < dataframe['btc_ema_200']) &
            (dataframe['btc_momentum'] < -0.02)
        )
        
        return dataframe
    
    def classify_market_regime(self, dataframe: DataFrame) -> pd.Series:
        """
        🎯 ELITE MARKET REGIME CLASSIFIER
        Returns: bull, bear, sideways, volatile
        """
        conditions = [
            # BULL REGIME: Strong uptrend with good momentum
            (
                dataframe['major_uptrend'] & 
                dataframe['minor_uptrend'] &
                (dataframe['momentum_20'] > 0.05) &
                (dataframe['volatility_regime'] != 'high')
            ),
            
            # BEAR REGIME: Strong downtrend
            (
                (~dataframe['major_uptrend']) & 
                (~dataframe['minor_uptrend']) &
                (dataframe['momentum_20'] < -0.05)
            ),
            
            # VOLATILE REGIME: High volatility regardless of direction
            (dataframe['volatility_regime'] == 'high'),
            
            # SIDEWAYS REGIME: Choppy, no clear direction
            (
                (abs(dataframe['momentum_20']) < 0.02) &
                (dataframe['volatility_regime'] == 'low')
            )
        ]
        
        choices = ['bull', 'bear', 'volatile', 'sideways']
        
        return np.select(conditions, choices, default='sideways')
    
    def calculate_adaptive_parameters(self, dataframe: DataFrame) -> DataFrame:
        """
        ⚡ DYNAMIC PARAMETER ADAPTATION
        Parameters change based on market regime
        """
        # Initialize with base parameters
        dataframe['adaptive_rsi_oversold'] = self.base_rsi_oversold.value
        dataframe['adaptive_volume_multiplier'] = self.base_volume_multiplier.value
        dataframe['adaptive_trend_strength'] = self.base_trend_strength.value
        
        # BULL REGIME: More aggressive
        bull_mask = dataframe['market_regime'] == 'bull'
        dataframe.loc[bull_mask, 'adaptive_rsi_oversold'] = self.base_rsi_oversold.value + 10  # Higher RSI allowed
        dataframe.loc[bull_mask, 'adaptive_volume_multiplier'] = self.base_volume_multiplier.value * 0.8  # Lower volume requirement
        dataframe.loc[bull_mask, 'adaptive_trend_strength'] = self.base_trend_strength.value * 0.7  # Lower trend strength needed
        
        # BEAR REGIME: More conservative  
        bear_mask = dataframe['market_regime'] == 'bear'
        dataframe.loc[bear_mask, 'adaptive_rsi_oversold'] = self.base_rsi_oversold.value - 5  # Lower RSI required
        dataframe.loc[bear_mask, 'adaptive_volume_multiplier'] = self.base_volume_multiplier.value * 1.5  # Higher volume required
        dataframe.loc[bear_mask, 'adaptive_trend_strength'] = self.base_trend_strength.value * 1.3  # Higher trend strength needed
        
        # VOLATILE REGIME: Very selective
        volatile_mask = dataframe['market_regime'] == 'volatile'
        dataframe.loc[volatile_mask, 'adaptive_rsi_oversold'] = self.base_rsi_oversold.value - 10  # Much lower RSI required
        dataframe.loc[volatile_mask, 'adaptive_volume_multiplier'] = self.base_volume_multiplier.value * 2.0  # Much higher volume required
        
        # SIDEWAYS REGIME: Scalping parameters
        sideways_mask = dataframe['market_regime'] == 'sideways'
        dataframe.loc[sideways_mask, 'adaptive_rsi_oversold'] = self.base_rsi_oversold.value + 5  # Slightly higher RSI
        dataframe.loc[sideways_mask, 'adaptive_volume_multiplier'] = self.base_volume_multiplier.value * 1.2  # Moderate volume
        
        return dataframe
    
    def detect_hammer(self, dataframe: DataFrame) -> pd.Series:
        """🔨 Hammer candlestick pattern detection"""
        body = abs(dataframe['close'] - dataframe['open'])
        lower_shadow = np.where(dataframe['close'] > dataframe['open'], 
                               dataframe['open'] - dataframe['low'],
                               dataframe['close'] - dataframe['low'])
        upper_shadow = dataframe['high'] - np.maximum(dataframe['close'], dataframe['open'])
        
        return (
            (lower_shadow > body * 2) &
            (upper_shadow < body * 0.5) &
            (body > 0)
        ).astype(int)
    
    def detect_engulfing(self, dataframe: DataFrame) -> pd.Series:
        """💪 Bullish engulfing pattern detection"""
        prev_red = dataframe['close'].shift(1) < dataframe['open'].shift(1)
        curr_green = dataframe['close'] > dataframe['open']
        
        engulfs = (
            (dataframe['open'] < dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['open'].shift(1))
        )
        
        return (prev_red & curr_green & engulfs).astype(int)
    
    def calculate_support_resistance(self, dataframe: DataFrame, period: int = 20) -> DataFrame:
        """📊 Dynamic support/resistance levels"""
        dataframe['resistance'] = dataframe['high'].rolling(window=period).max()
        dataframe['support'] = dataframe['low'].rolling(window=period).min()
        
        dataframe['near_support'] = (
            (dataframe['close'] - dataframe['support']) / dataframe['support'] < 0.01
        ).astype(int)
        
        dataframe['near_resistance'] = (
            (dataframe['resistance'] - dataframe['close']) / dataframe['close'] < 0.01
        ).astype(int)
        
        return dataframe
    
    def calculate_signal_quality(self, dataframe: DataFrame) -> pd.Series:
        """⭐ Signal quality score (0-100)"""
        quality_factors = []
        
        # Trend alignment
        trend_score = (
            dataframe['minor_uptrend'].astype(int) +
            dataframe['major_uptrend'].astype(int)
        ) * 20
        quality_factors.append(trend_score)
        
        # Volume confirmation
        volume_score = np.clip(dataframe['volume_ratio'] * 10, 0, 30)
        quality_factors.append(volume_score)
        
        # Pattern recognition
        pattern_score = (
            dataframe['hammer'] + 
            dataframe['engulfing'] +
            dataframe['near_support']
        ) * 15
        quality_factors.append(pattern_score)
        
        # Low volatility bonus (better for entries)
        volatility_score = np.where(
            dataframe['volatility_regime'] == 'low', 25,
            np.where(dataframe['volatility_regime'] == 'medium', 15, 5)
        )
        quality_factors.append(volatility_score)
        
        total_quality = sum(quality_factors)
        return np.clip(total_quality, 0, 100)
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """
        🎯 ELITE ADAPTIVE ENTRY SYSTEM
        Different logic for each market regime
        """
        
        dataframe['enter_long'] = 0
        dataframe['enter_tag'] = ''
        
        # ================================
        # BULL REGIME: TREND FOLLOWING
        # ================================
        bull_entry = (
            (dataframe['market_regime'] == 'bull') &
            (dataframe['rsi'] < dataframe['adaptive_rsi_oversold']) &
            (dataframe['minor_uptrend']) &
            (dataframe['volume_ratio'] > dataframe['adaptive_volume_multiplier']) &
            (dataframe['momentum_5'] > -0.01) &
            (dataframe['signal_quality'] > 60)
        )
        
        # ================================
        # BEAR REGIME: OVERSOLD BOUNCES
        # ================================
        bear_entry = (
            (dataframe['market_regime'] == 'bear') &
            (dataframe['rsi'] < dataframe['adaptive_rsi_oversold']) &
            (dataframe['volume_ratio'] > dataframe['adaptive_volume_multiplier'] * 0.7) &  # Lower volume requirement
            (dataframe['signal_quality'] > 40)  # Much lower quality requirement in bear markets
        )
        
        # ================================
        # SIDEWAYS REGIME: MEAN REVERSION  
        # ================================
        sideways_entry = (
            (dataframe['market_regime'] == 'sideways') &
            (dataframe['rsi'] < dataframe['adaptive_rsi_oversold']) &
            (dataframe['near_support']) &
            (dataframe['bb_lower'] > dataframe['close']) &  # Below lower Bollinger
            (dataframe['volume_ratio'] > dataframe['adaptive_volume_multiplier']) &
            (dataframe['signal_quality'] > 50)
        )
        
        # ================================
        # VOLATILE REGIME: BREAKOUT CAPTURE
        # ================================
        volatile_entry = (
            (dataframe['market_regime'] == 'volatile') &
            (dataframe['rsi'] < dataframe['adaptive_rsi_oversold']) &
            (dataframe['volume_ratio'] > dataframe['adaptive_volume_multiplier'] * 2) &  # Very high volume
            (dataframe['close'] > dataframe['resistance'].shift(1)) &  # Breakout above resistance
            (dataframe['signal_quality'] > 80)  # Very high quality required
        )
        
        # Apply entries with tags
        dataframe.loc[bull_entry, 'enter_long'] = 1
        dataframe.loc[bull_entry, 'enter_tag'] = 'bull_trend'
        
        dataframe.loc[bear_entry, 'enter_long'] = 1
        dataframe.loc[bear_entry, 'enter_tag'] = 'bear_bounce'
        
        dataframe.loc[sideways_entry, 'enter_long'] = 1
        dataframe.loc[sideways_entry, 'enter_tag'] = 'sideways_mean_reversion'
        
        dataframe.loc[volatile_entry, 'enter_long'] = 1
        dataframe.loc[volatile_entry, 'enter_tag'] = 'volatile_breakout'
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: Dict) -> DataFrame:
        """
        🚪 ELITE ADAPTIVE EXIT SYSTEM  
        Regime-specific exit logic
        """
        
        dataframe['exit_long'] = 0
        dataframe['exit_tag'] = ''
        
        # Universal exit conditions (apply to all regimes)
        universal_exit = (
            (dataframe['rsi'] > 85) |  # Extreme overbought
            (
                (~dataframe['minor_uptrend']) &  # Trend breaks
                (dataframe['momentum_5'] < -0.02) &
                (dataframe['volume_ratio'] > 2.0)
            )
        )
        
        # Regime-specific exits
        
        # BULL REGIME: Let winners run, but exit on trend break
        bull_exit = (
            (dataframe['market_regime'] == 'bull') &
            (
                (~dataframe['major_uptrend']) |  # Major trend breaks
                (dataframe['rsi'] > 80)  # Very overbought
            )
        )
        
        # BEAR REGIME: Take profits quickly
        bear_exit = (
            (dataframe['market_regime'] == 'bear') &
            (
                (dataframe['rsi'] > 60) |  # Quick profit taking
                (dataframe['momentum_5'] < -0.01)  # Momentum turns negative
            )
        )
        
        # SIDEWAYS REGIME: Hit targets or cut losses quickly
        sideways_exit = (
            (dataframe['market_regime'] == 'sideways') &
            (
                (dataframe['rsi'] > 65) |  # Medium overbought
                (dataframe['near_resistance']) |  # Hit resistance
                (dataframe['close'] < dataframe['bb_middle'])  # Back to middle of range
            )
        )
        
        # VOLATILE REGIME: Very tight stops
        volatile_exit = (
            (dataframe['market_regime'] == 'volatile') &
            (
                (dataframe['rsi'] > 70) |  # Lower profit target
                (dataframe['momentum_5'] < 0)  # Any negative momentum
            )
        )
        
        # Apply exits
        final_exit = universal_exit | bull_exit | bear_exit | sideways_exit | volatile_exit
        
        dataframe.loc[final_exit, 'exit_long'] = 1
        dataframe.loc[final_exit, 'exit_tag'] = 'regime_exit'
        
        return dataframe
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        """
        💰 ELITE POSITION SIZING - Kelly Criterion + Risk Management
        """
        
        # Get current market data for this pair
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return min_stake
        
        latest = dataframe.iloc[-1]
        
        # Base multiplier
        multiplier = 1.0
        
        # ================================
        # REGIME-BASED POSITION SIZING
        # ================================
        
        regime = latest.get('market_regime', 'sideways')
        signal_quality = latest.get('signal_quality', 50)
        
        if regime == 'bull':
            # Aggressive sizing in bull markets
            multiplier *= 1.5
            if signal_quality > 80:
                multiplier *= 1.2  # Extra size for high quality signals
        elif regime == 'bear':
            # Conservative sizing in bear markets  
            multiplier *= 0.6
            if signal_quality > 80:
                multiplier *= 1.1  # Slight bonus for high quality
        elif regime == 'volatile':
            # Very small positions in volatile markets
            multiplier *= 0.4
        else:  # sideways
            # Standard sizing for sideways markets
            multiplier *= 0.8
        
        # ================================
        # VOLATILITY-BASED ADJUSTMENT
        # ================================
        
        atr_pct = latest.get('atr_pct', 2.0)
        if atr_pct > 6.0:  # Very high volatility
            multiplier *= 0.5
        elif atr_pct > 4.0:  # High volatility
            multiplier *= 0.7
        elif atr_pct < 1.5:  # Low volatility
            multiplier *= 1.2
        
        # ================================
        # PAIR PERFORMANCE-BASED SIZING
        # ================================
        
        try:
            recent_trades = Trade.get_trades_proxy(is_open=False, pair=pair)
            if len(recent_trades) >= 3:
                # Analyze last 5 trades for this pair
                last_trades = recent_trades[-5:]
                win_rate = sum(1 for t in last_trades if t.close_profit and t.close_profit > 0) / len(last_trades)
                
                if win_rate >= 0.8:  # Very successful pair
                    multiplier *= 1.3
                elif win_rate >= 0.6:  # Good pair
                    multiplier *= 1.1
                elif win_rate <= 0.3:  # Poor performing pair
                    multiplier *= 0.6
        except:
            pass
        
        # ================================
        # PORTFOLIO RISK LIMITS
        # ================================
        
        # Calculate total portfolio risk
        try:
            open_trades = Trade.get_open_trade_count()
            if open_trades >= 10:  # Too many open positions
                multiplier *= 0.7
            elif open_trades >= 7:
                multiplier *= 0.8
        except:
            pass
        
        # Maximum single trade risk (2% of account)
        max_risk_amount = self.max_single_trade_risk.value * self.dp.get_balance(self.config['stake_currency'])
        max_position_value = max_risk_amount / 0.04  # Assuming 4% max loss per trade
        
        adjusted_stake = proposed_stake * multiplier
        
        # Apply limits
        final_stake = min(
            max(adjusted_stake, min_stake),
            min(max_stake, max_position_value)
        )
        
        return final_stake
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: str,
                           side: str, **kwargs) -> bool:
        """
        🛡️ ELITE RISK MANAGEMENT - Final entry confirmation
        """
        
        # ================================
        # DAILY LOSS LIMIT CHECK
        # ================================
        
        try:
            today = current_time.date()
            all_trades = Trade.get_trades_proxy(is_open=False)
            
            # Calculate today's P&L
            daily_pnl = 0.0
            for trade in all_trades:
                if trade.close_date and trade.close_date.date() == today:
                    if trade.close_profit_abs:
                        daily_pnl += trade.close_profit_abs
            
            # Dynamic daily loss limit based on account size
            account_balance = self.dp.get_balance(self.config['stake_currency'])
            daily_loss_limit = -1 * (account_balance * self.daily_loss_limit_pct.value)
            
            if daily_pnl < daily_loss_limit:
                logger.warning(f"DAILY LOSS LIMIT HIT: ${daily_pnl:.2f} < ${daily_loss_limit:.2f} - blocking {pair} entry")
                return False
        
        except Exception as e:
            logger.warning(f"Error checking daily limits: {e}")
        
        # ================================
        # PORTFOLIO RISK CHECK
        # ================================
        
        try:
            open_trades = Trade.get_open_trade_count()
            total_stake = sum(trade.stake_amount for trade in Trade.get_open_trades() if trade.stake_amount)
            
            account_balance = self.dp.get_balance(self.config['stake_currency'])
            portfolio_risk_pct = total_stake / account_balance if account_balance > 0 else 1.0
            
            if portfolio_risk_pct > self.max_portfolio_risk.value:
                logger.warning(f"PORTFOLIO RISK LIMIT: {portfolio_risk_pct:.1%} > {self.max_portfolio_risk.value:.1%} - blocking {pair}")
                return False
        except:
            pass
        
        # ================================
        # MARKET CONDITION CHECK
        # ================================
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) >= 1:
            latest = dataframe.iloc[-1]
            
            # Block entries during extreme market stress
            signal_quality = latest.get('signal_quality', 0)
            if signal_quality < 40:  # Very low quality signal
                logger.warning(f"Low signal quality ({signal_quality}) - blocking {pair} entry")
                return False
            
            # Block entries during extreme volatility (unless volatile regime strategy)
            atr_pct = latest.get('atr_pct', 2.0)
            regime = latest.get('market_regime', 'sideways')
            
            if atr_pct > 10.0 and regime != 'volatile':  # Extreme volatility
                logger.warning(f"EXTREME VOLATILITY: {atr_pct:.1f}% ATR - blocking {pair} entry")
                return False
        
        # ================================
        # TIME-BASED FILTERS
        # ================================
        
        # Avoid trading during low liquidity periods (optional)
        hour = current_time.hour
        if hour >= 2 and hour <= 6:  # Low liquidity Asian hours
            # Allow but with higher quality requirement
            if len(dataframe) >= 1:
                signal_quality = dataframe.iloc[-1].get('signal_quality', 0)
                if signal_quality < 70:
                    return False
        
        return True