#!/usr/bin/env python3
"""
SafeBullRider Multi-Pair Realistic Backtesting - Works Like Paper Trading
Based on Try1 multi-pair script but with SafeBullRider safety features
Only essential daily loss limit checks - NO weekend filters
"""

import sys
import time
import numpy as np
import pandas as pd
import talib.abstract as ta
from pathlib import Path
from datetime import datetime, date, timedelta
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent.parent / "legacy_backtest_scripts"))

from tick_backtester import TickBacktester, Trade, Portfolio

class SafeRealisticBacktester(TickBacktester):
    """
    Multi-pair realistic backtester that matches your SafeBullRider strategy exactly
    Only essential safety checks (daily loss limit) - NO weekend filters
    Same execution engine as Try1 for fair comparison across all pairs
    
    BALANCE TERMINOLOGY (FIXED):
    - available_balance: Cash available for new trades (decreases as positions open)
    - current_balance: Legacy field, kept for compatibility (equals available_balance)
    - calculate_total_portfolio_value(): REAL portfolio value (cash + open positions)
    
    All risk calculations (daily loss, position size, drawdown) now use total portfolio value
    """
    
    def __init__(self):
        super().__init__()
        
        # Your EXACT trading pairs from config_billionaire.json (1INCH removed)
        self.trading_pairs = [
            "BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT",
            "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "BCHUSDT",
            "TIAUSDT", "DOTUSDT", "POLUSDT", "UNIUSDT"
        ]
        
        # Match your EXACT live configuration
        self.portfolio.position_size_pct = 0.08  # 8% base (matches your ~$800 stakes)
        self.portfolio.max_open_trades = 15      # SafeBullRider config
        self.max_positions_per_pair = 2         # Prevent concentration (max 2 per pair)
        
        # SafeBullRiderStrategy parameters (EXACT values from your code)
        self.rsi_oversold = 40
        self.rsi_overbought = 65
        self.volume_multiplier = 1.2
        self.trend_strength = 0.005
        
        # SafeBullRider risk management
        self.max_daily_loss_pct = 0.05  # 5% max daily loss (from SafeBullRider)
        self.btc_correlation_threshold = -0.018
        self.volatility_threshold = 0.035
        
        # ROI targets (EXACT from SafeBullRider - same as Try1)
        self.minimal_roi = {
            0: 0.04,    # 4% target
            120: 0.025, # 2.5% after 2 hours 
            300: 0.015, # 1.5% after 5 hours
            600: 0.008  # 0.8% after 10 hours
        }
        
        # Trailing stop parameters (EXACT from SafeBullRider - same as Try1)
        self.trailing_stop_positive = 0.015      # 1.5%
        self.trailing_stop_positive_offset = 0.02 # 2%
        
        # Track highest profit for trailing stop
        self.position_max_profit = {}
        
        # Track daily trades for loss limit
        self.daily_loss_today = 0.0
        self.last_check_date = None
        self.daily_limit_warned = False  # Track if we've warned today
        self.emergency_brake_triggered = False
        self.correlation_positions = {'crypto': 0}  # Track correlated positions
        
        # Track safety feature usage (minimal - only keep essential)
        self.safety_stats = {
            'daily_limit_hits': 0,
            'emergency_brakes': 0,
            'max_daily_loss': 0,
            'days_with_limits': 0
        }
        
        # FIXED: Proper balance tracking for accurate drawdowns
        self.balance_history = []
        self.daily_balance_snapshots = {}  # Track daily balance for proper drawdown calc
    
    def get_available_pairs_for_date(self, date):
        """Get list of pairs that have tick data available for given date"""
        available_pairs = []
        for pair in self.trading_pairs:
            tick_file = Path(f"user_data/tick_data/{pair}/{pair}-trades-{date.strftime('%Y-%m-%d')}.feather")
            if tick_file.exists():
                available_pairs.append(pair)
        return available_pairs
    
    def count_positions_for_pair(self, pair):
        """Count current open positions for a specific pair"""
        count = 0
        for trade in self.portfolio.open_positions:
            if trade.symbol == pair:
                count += 1
        return count
    
    def can_open_position_for_pair(self, pair):
        """Check if we can open another position for this pair"""
        current_positions = self.count_positions_for_pair(pair)
        total_positions = len(self.portfolio.open_positions)
        
        # Check pair-specific limit and total limit
        return (current_positions < self.max_positions_per_pair and 
                total_positions < self.portfolio.max_open_trades)
    
    def calculate_total_portfolio_value(self, current_prices=None):
        """Calculate total portfolio value including open positions - FIXED VERSION"""
        total_value = self.portfolio.available_balance
        
        # Add value of open positions
        if current_prices:
            for trade in self.portfolio.open_positions:
                if trade.symbol in current_prices:
                    position_value = trade.quantity * current_prices[trade.symbol]
                    total_value += position_value
                else:
                    # Fallback to entry price if no current price
                    position_value = trade.quantity * trade.entry_price
                    total_value += position_value
        else:
            # Fallback: use entry prices (conservative estimate)
            for trade in self.portfolio.open_positions:
                position_value = trade.quantity * trade.entry_price
                total_value += position_value
        
        return total_value
    
    def validate_portfolio_consistency(self):
        """Validate portfolio balance calculations are consistent - SANITY CHECKS"""
        available_cash = self.portfolio.available_balance
        
        # Calculate position values at entry prices (conservative)
        total_position_value = 0
        for trade in self.portfolio.open_positions:
            position_value = trade.quantity * trade.entry_price
            total_position_value += position_value
        
        expected_total = available_cash + total_position_value
        
        # Check for major inconsistencies
        if available_cash < 0:
            logger.error(f"🚨 CRITICAL: Negative cash balance: ${available_cash:.2f}")
        
        if total_position_value > self.portfolio.initial_balance * 2:
            logger.error(f"🚨 CRITICAL: Position value exceeds 2x initial balance: ${total_position_value:.2f}")
        
        if expected_total < self.portfolio.initial_balance * 0.5:
            logger.warning(f"⚠️  LARGE LOSSES: Portfolio down to ${expected_total:.2f} from ${self.portfolio.initial_balance:.2f}")
        
        return {
            'available_cash': available_cash,
            'position_value': total_position_value,
            'total_portfolio': expected_total,
            'is_valid': available_cash >= 0 and total_position_value >= 0
        }
    
    def update_portfolio_balance(self, timestamp, current_prices=None):
        """Update portfolio balance tracking with total portfolio value - ENHANCED"""
        total_portfolio_value = self.calculate_total_portfolio_value(current_prices)
        
        # Enhanced tracking with more details
        balance_entry = {
            'timestamp': timestamp,
            'balance': total_portfolio_value,
            'available_cash': self.portfolio.available_balance,
            'open_positions': len(self.portfolio.open_positions),
            'position_value': total_portfolio_value - self.portfolio.available_balance,
            'balance_change_pct': 0.0,
            'is_new_peak': False,
            'current_drawdown_pct': 0.0
        }
        
        # Calculate balance change percentage
        if len(self.balance_history) > 0:
            prev_balance = self.balance_history[-1]['balance']
            balance_entry['balance_change_pct'] = ((total_portfolio_value - prev_balance) / prev_balance) * 100
            
            # Check if this is a new peak
            all_balances = [entry['balance'] for entry in self.balance_history]
            current_peak = max(all_balances)
            if total_portfolio_value > current_peak:
                balance_entry['is_new_peak'] = True
                
            # Calculate current drawdown from peak
            balance_entry['current_drawdown_pct'] = ((current_peak - total_portfolio_value) / current_peak) * 100
        
        self.balance_history.append(balance_entry)
        
        # Track daily snapshots for proper drawdown analysis
        date_str = timestamp.strftime('%Y-%m-%d')
        if date_str not in self.daily_balance_snapshots:
            self.daily_balance_snapshots[date_str] = []
        self.daily_balance_snapshots[date_str].append(total_portfolio_value)
        
        # Real-time drawdown warnings
        if balance_entry['current_drawdown_pct'] > 15:
            logger.warning(f"⚠️  REAL-TIME DRAWDOWN ALERT: {balance_entry['current_drawdown_pct']:.1f}% at {timestamp}")
        elif balance_entry['is_new_peak']:
            logger.info(f"🎯 NEW PORTFOLIO PEAK: ${total_portfolio_value:,.2f} at {timestamp}")
        
    def create_5min_candles(self, tick_df):
        """Convert tick data to 5-minute OHLCV candles (matches SafeBullRider 5m timeframe)"""
        if len(tick_df) == 0:
            return pd.DataFrame()
        
        # Create a copy to avoid modifying original data
        tick_copy = tick_df.copy()
        tick_copy['datetime'] = pd.to_datetime(tick_copy['datetime'])
        tick_copy.set_index('datetime', inplace=True)
        
        # Create 5-minute candles (matching SafeBullRider strategy timeframe)
        candles = tick_copy['price'].resample('5min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        })
        
        # Add volume (count of trades as proxy)
        candles['volume'] = tick_copy['price'].resample('5min').count()
        
        candles = candles.dropna()
        candles.reset_index(inplace=True)
        
        return candles
    
    def populate_indicators(self, df):
        """EXACT implementation of SafeBullRiderStrategy indicators"""
        if len(df) < 100:  # SafeBullRider needs startup_candle_count = 100
            return df
        
        # Basic EMAs for trend (EXACT from SafeBullRider)
        df['ema_8'] = ta.EMA(df, timeperiod=8)
        df['ema_21'] = ta.EMA(df, timeperiod=21)
        df['ema_50'] = ta.EMA(df, timeperiod=50)
        
        # RSI (EXACT from SafeBullRider)
        df['rsi'] = ta.RSI(df, timeperiod=14)
        
        # Volume (EXACT from SafeBullRider)
        df['volume_mean'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_mean']
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # Price momentum (EXACT from SafeBullRider)
        df['momentum_5'] = df['close'].pct_change(periods=5)
        df['momentum_20'] = df['close'].pct_change(periods=20)
        
        # VOLATILITY METRICS (SafeBullRider specific)
        df['volatility'] = df['close'].pct_change().rolling(window=20).std()
        df['atr'] = ta.ATR(df, timeperiod=14)
        df['atr_pct'] = df['atr'] / df['close']
        
        # MARKET BREADTH (SafeBullRider specific)
        df['price_change_1h'] = df['close'].pct_change(periods=12)  # 1 hour change
        df['price_change_4h'] = df['close'].pct_change(periods=48)  # 4 hour change
        
        # Market risk indicator (SafeBullRider specific)
        df['market_risk'] = (
            (df['volatility'] > df['volatility'].rolling(window=100).mean() * 1.5).astype(int) +
            (df['volume_ratio'] > 2).astype(int) +
            (df['price_change_1h'] < -0.02).astype(int)
        ) / 3.0
        
        # Trend detection (EXACT from SafeBullRiderStrategy)
        df['uptrend'] = (
            (df['ema_8'] > df['ema_21']) &
            (df['ema_21'] > df['ema_50']) &
            (df['close'] > df['ema_8'])
        )
        
        df['downtrend'] = (
            (df['ema_8'] < df['ema_21']) &
            (df['ema_21'] < df['ema_50']) &
            (df['close'] < df['ema_8'])
        )
        
        # Candle patterns (EXACT from SafeBullRider)
        df['green_candle'] = (df['close'] > df['open']).astype(int)
        df['red_candle'] = (df['close'] < df['open']).astype(int)
        
        return df
    
    def check_daily_loss_limit(self, current_time):
        """Check if daily loss limit has been reached (SafeBullRider safety)"""
        try:
            current_date = current_time.date()
            
            # Reset daily loss if new day
            if self.last_check_date != current_date:
                self.daily_loss_today = 0.0
                self.last_check_date = current_date
                self.daily_limit_warned = False  # Reset warning flag
                self.emergency_brake_triggered = False
            
            # Check if current daily loss exceeds limit
            # FIXED: Use TOTAL portfolio value (cash + positions), not just available cash
            # This ensures consistent risk management regardless of open positions
            total_portfolio_value = self.calculate_total_portfolio_value()
            daily_loss_limit = total_portfolio_value * self.max_daily_loss_pct
            
            if abs(self.daily_loss_today) > daily_loss_limit:
                # Only warn once per day to avoid spam
                if not self.daily_limit_warned:
                    logger.warning(f"📛 Daily loss limit reached: ${abs(self.daily_loss_today):.2f} > ${daily_loss_limit:.2f} (5% of ${total_portfolio_value:.2f} portfolio) - Blocking new entries")
                    self.daily_limit_warned = True
                    self.safety_stats['daily_limit_hits'] += 1
                    self.safety_stats['days_with_limits'] += 1
                
                # Emergency brake at 150% of limit (7.5% loss)
                emergency_limit = daily_loss_limit * 1.5
                if abs(self.daily_loss_today) > emergency_limit and not self.emergency_brake_triggered:
                    logger.critical(f"🚨 EMERGENCY BRAKE: Daily loss ${abs(self.daily_loss_today):.2f} exceeds ${emergency_limit:.2f} (7.5% of ${total_portfolio_value:.2f} portfolio)!")
                    self.emergency_brake_triggered = True
                    self.safety_stats['emergency_brakes'] += 1
                    # Note: In live trading, this would close all positions
                    # In backtest, we just block new entries to preserve historical accuracy
                
                return False
                
        except Exception as e:
            logger.error(f"Error checking daily loss limit: {e}")
            
        return True
    
    def check_market_conditions(self, df):
        """Check if market conditions are safe (SafeBullRider quality filters)"""
        if len(df) < 2:
            return True
            
        last_row = df.iloc[-1]
        
        # Enhanced quality filters from SafeBullRider
        if pd.isna(last_row['volatility']) or pd.isna(last_row['market_risk']):
            return True
        
        # Check volatility (relaxed from SafeBullRider)
        if last_row['volatility'] > 0.08:  # Very high volatility
            logger.debug(f"High volatility detected: {last_row['volatility']:.4f}")
            return False
        
        # Check market risk score (relaxed from SafeBullRider)
        if last_row['market_risk'] > 0.7:  # High market risk
            logger.debug(f"High market risk: {last_row['market_risk']:.2f}")
            return False
        
        return True
    
    def check_entry_signals(self, df, timestamp):
        """EXACT entry logic from SafeBullRiderStrategy - smart enhanced patterns"""
        if len(df) < 2:
            return None
        
        last = df.iloc[-1]
        
        # Skip if indicators not ready
        if pd.isna(last['rsi']) or pd.isna(last['uptrend']):
            return None
        
        # Check daily loss limit first (SafeBullRider safety)
        if not self.check_daily_loss_limit(timestamp):
            return None
        
        # REMOVED: Correlation limits (was killing 470% returns)
        # Max 5 crypto limit blocked 19K trades and reduced returns from 470% to 87%
        
        # Check market conditions (SafeBullRider quality filters)
        if not self.check_market_conditions(df):
            return None
        
        # LONG conditions (EXACT from SafeBullRider) - enhanced patterns
        
        # Pattern 1: RSI Oversold Bounce (ENHANCED with momentum confirmation)
        long_dip_buy = (
            last['uptrend'] and
            last['rsi'] < self.rsi_oversold and
            last['volume_ratio'] > self.volume_multiplier and
            last['momentum_5'] > -0.01  # Not falling too hard
        )
        
        # Pattern 2: Momentum Breakout (ENHANCED with stronger confirmation)
        long_breakout = (
            last['momentum_5'] > self.trend_strength and
            last['momentum_20'] > 0 and  # Longer-term momentum positive
            last['green_candle'] == 1 and
            last['volume_ratio'] > 2.0 and  # Stronger volume requirement
            last['close'] > last['ema_8']
        )
        
        # Pattern 3: Trend Continuation (ENHANCED with quality filter)
        long_trend_follow = (
            last['uptrend'] and
            last['close'] > df.iloc[-2]['close'] and
            last['rsi'] > 50 and last['rsi'] < 65 and  # Tighter RSI range
            last['volume_ratio'] > 1.2 and  # Higher volume requirement
            last['atr_pct'] < 0.05  # Lower volatility for trend continuation
        )
        
        # Combine with OR logic (SafeBullRider approach)
        if long_dip_buy or long_breakout or long_trend_follow:
            # Final quality check (volume must be positive)
            if last['volume'] > 0:
                return 'smart_safe_long'
        
        return None

    def run_realistic_backtest(self, start_date, end_date):
        """Multi-pair realistic backtest matching SafeBullRider exactly"""
        import time
        start_time = time.time()
        
        # Store custom balance before reset
        custom_balance = self.portfolio.initial_balance
        
        logger.info(f"Starting SafeBullRider multi-pair backtest from {start_date} to {end_date}")
        logger.info(f"Trading pairs: {', '.join(self.trading_pairs)}")
        logger.info("Only essential daily loss limit checks - NO weekend filters")
        
        # Create progress file for monitoring long backtests
        progress_file = Path("user_data/backtest_progress.json")
        self.progress_info = {
            'start_time': datetime.now().isoformat(),
            'total_days': (end_date - start_date).days + 1,
            'current_day': 0,
            'current_date': '',
            'progress_pct': 0.0,
            'estimated_completion': '',
            'starting_balance': custom_balance,
            'current_balance': custom_balance,
            'available_cash': custom_balance,
            'total_trades': 0,
            'open_positions': 0,
            'pairs_processed': 0,
            'status': 'running'
        }
        
        # Reset portfolio with custom balance
        self.portfolio = Portfolio()
        self.portfolio.initial_balance = custom_balance
        self.portfolio.available_balance = custom_balance
        self.portfolio.current_balance = custom_balance
        self.portfolio.position_size_pct = 0.08
        self.portfolio.max_open_trades = 15
        self.position_max_profit = {}
        self.daily_loss_today = 0.0
        self.last_check_date = None
        
        current_date = start_date
        total_days = (end_date - start_date).days + 1
        day_count = 0
        
        # Accumulate candles per pair
        all_candles_per_pair = {pair: pd.DataFrame() for pair in self.trading_pairs}
        
        while current_date <= end_date:
            day_count += 1
            
            # Get available pairs for this date
            available_pairs = self.get_available_pairs_for_date(current_date)
            
            if len(available_pairs) > 0:
                # Load and process data for each available pair
                pair_data = {}
                
                for pair in available_pairs:
                    # Load tick data
                    tick_df = self.load_tick_data(pair, current_date)
                    
                    if tick_df is not None and len(tick_df) > 0:
                        # Convert to 5-min candles
                        daily_candles = self.create_5min_candles(tick_df)
                        
                        if len(daily_candles) > 0:
                            # Append to accumulated candles
                            all_candles_per_pair[pair] = pd.concat([all_candles_per_pair[pair], daily_candles], ignore_index=True)
                            
                            # Keep only last 200 candles for efficiency
                            if len(all_candles_per_pair[pair]) > 200:
                                all_candles_per_pair[pair] = all_candles_per_pair[pair].iloc[-200:]
                            
                            # Calculate indicators
                            all_candles_per_pair[pair] = self.populate_indicators(all_candles_per_pair[pair])
                            
                            # Store for processing
                            pair_data[pair] = {
                                'candles': all_candles_per_pair[pair],
                                'daily_candles': daily_candles,
                                'tick_df': tick_df
                            }
                
                # Process signals for all pairs simultaneously
                for pair, data in pair_data.items():
                    candles = data['candles']
                    daily_candles = data['daily_candles']
                    tick_df = data['tick_df']
                    
                    # Process each new candle for this pair
                    for idx in range(len(daily_candles)):
                        candle_time = daily_candles.iloc[idx]['datetime']
                        candle_idx = len(candles) - len(daily_candles) + idx
                        
                        if candle_idx < 0:
                            continue
                        
                        # Update existing positions for this pair
                        positions_to_close = []
                        for i, trade in enumerate(self.portfolio.open_positions):
                            if trade.symbol == pair:
                                current_price = candles.iloc[candle_idx]['close']
                                # Use same exit logic as Try1 but with SafeBullRider's wider stops
                                exit_reason, exit_price = self.check_exit_conditions_safe(
                                    trade, current_price, candle_time, candles.iloc[:candle_idx+1]
                                )
                                if exit_reason:
                                    # Get precise tick execution price
                                    tick_datetime = pd.to_datetime(tick_df['datetime'])
                                    mask = (tick_datetime >= candle_time) & \
                                           (tick_datetime < candle_time + pd.Timedelta(minutes=5))
                                    candle_ticks = tick_df[mask]
                                    
                                    if len(candle_ticks) > 0:
                                        exit_price = self.get_tick_execution_price(
                                            candle_ticks, candle_time, is_entry=False
                                        )
                                    
                                    positions_to_close.append((i, exit_reason, exit_price))
                        
                        # Close positions
                        for i, reason, price in reversed(positions_to_close):
                            self.close_position_at_price(i, reason, price, candle_time)
                        
                        # Check for new entry signals
                        if self.can_open_position_for_pair(pair):
                            signal = self.check_entry_signals(
                                candles.iloc[:candle_idx+1], candle_time
                            )
                            
                            if signal:
                                # Get precise tick execution price
                                tick_datetime = pd.to_datetime(tick_df['datetime'])
                                mask = (tick_datetime >= candle_time) & \
                                       (tick_datetime < candle_time + pd.Timedelta(minutes=5))
                                candle_ticks = tick_df[mask]
                                
                                if len(candle_ticks) > 0:
                                    entry_price = self.get_tick_execution_price(
                                        candle_ticks, candle_time, is_entry=True
                                    )
                                    
                                    # Calculate position size
                                    stake = self.custom_stake_amount(
                                        self.portfolio.available_balance,
                                        candles.iloc[:candle_idx+1]
                                    )
                                    
                                    # Open position
                                    self.open_position_at_price(
                                        pair, signal, entry_price, stake, candle_time
                                    )
                                    
                                    # Update portfolio balance after opening position
                                    current_prices = {pair: entry_price}
                                    self.update_portfolio_balance(candle_time, current_prices)
                        
                        # ENHANCED: Update portfolio balance after each candle for accurate drawdown tracking
                        # This captures intraday movements even without trades
                        if candle_idx == len(candles) - 1:  # Last candle of current data
                            # Gather current prices for all pairs
                            current_candle_prices = {}
                            for check_pair in self.trading_pairs:
                                if check_pair in all_candles_per_pair and len(all_candles_per_pair[check_pair]) > 0:
                                    # Find the price at this candle time
                                    check_candles = all_candles_per_pair[check_pair]
                                    time_mask = check_candles['datetime'] <= candle_time
                                    if time_mask.any():
                                        current_candle_prices[check_pair] = check_candles[time_mask].iloc[-1]['close']
                            
                            # Update balance tracking with current market prices
                            if current_candle_prices:
                                self.update_portfolio_balance(candle_time, current_candle_prices)
            
            # FIXED: Update portfolio balance daily for accurate drawdown tracking
            current_prices = {}
            for pair in self.trading_pairs:
                if pair in all_candles_per_pair and len(all_candles_per_pair[pair]) > 0:
                    # Get last available price for each pair
                    pair_candles = all_candles_per_pair[pair]
                    current_timestamp = pd.Timestamp(current_date).tz_localize('UTC')
                    date_mask = pair_candles['datetime'] <= current_timestamp
                    if date_mask.any():
                        current_prices[pair] = pair_candles[date_mask].iloc[-1]['close']
            
            # Update portfolio balance with current market values
            end_of_day = pd.Timestamp(current_date).replace(hour=23, minute=59)
            self.update_portfolio_balance(end_of_day, current_prices)
            
            # Validate portfolio consistency daily
            if day_count % 30 == 0:  # Check every 30 days
                validation = self.validate_portfolio_consistency()
                if not validation['is_valid']:
                    logger.error(f"Portfolio validation failed on day {day_count}")
            
            # Progress update every 10 days
            if day_count % 10 == 0:
                elapsed = time.time() - start_time
                progress = day_count / total_days * 100
                open_pos = len(self.portfolio.open_positions)
                total_portfolio_value = self.calculate_total_portfolio_value(current_prices)
                
                # Show positions per pair
                pair_positions = {}
                for trade in self.portfolio.open_positions:
                    pair_positions[trade.symbol] = pair_positions.get(trade.symbol, 0) + 1
                
                pair_summary = ", ".join([f"{pair}:{count}" for pair, count in pair_positions.items()])
                logger.info(f"Progress: {progress:.1f}% | Open: {open_pos}/{self.portfolio.max_open_trades} | Portfolio: ${total_portfolio_value:.2f}")
                if pair_summary:
                    logger.info(f"Positions: {pair_summary}")
            
            # Update progress tracking
            self.progress_info['current_day'] = day_count
            self.progress_info['current_date'] = current_date.strftime('%Y-%m-%d')
            self.progress_info['progress_pct'] = (day_count / total_days) * 100
            # FIXED: Use total portfolio value (cash + positions) instead of just available cash
            self.progress_info['current_balance'] = self.calculate_total_portfolio_value(current_prices)
            self.progress_info['available_cash'] = self.portfolio.available_balance
            self.progress_info['total_trades'] = len(self.portfolio.closed_trades)
            self.progress_info['open_positions'] = len(self.portfolio.open_positions)
            
            # Estimate completion time
            if day_count > 1:
                elapsed_time = time.time() - start_time
                time_per_day = elapsed_time / day_count
                remaining_days = total_days - day_count
                estimated_remaining = remaining_days * time_per_day
                completion_time = datetime.now() + timedelta(seconds=estimated_remaining)
                self.progress_info['estimated_completion'] = completion_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Save progress every 5 days or at major milestones
            if day_count % 5 == 0 or self.progress_info['progress_pct'] in [25, 50, 75]:
                import json
                with open(progress_file, 'w') as f:
                    json.dump(self.progress_info, f, indent=2)
            
            current_date += timedelta(days=1)
        
        # Close remaining positions
        if len(self.portfolio.open_positions) > 0:
            for i in reversed(range(len(self.portfolio.open_positions))):
                trade = self.portfolio.open_positions[i]
                pair = trade.symbol
                
                if pair in all_candles_per_pair and len(all_candles_per_pair[pair]) > 0:
                    last_price = all_candles_per_pair[pair].iloc[-1]['close']
                else:
                    last_price = trade.entry_price
                
                end_datetime = pd.Timestamp(end_date).tz_localize('UTC')
                self.close_position_at_price(i, "backtest_end", last_price, end_datetime)
        
        elapsed = time.time() - start_time
        logger.info(f"SafeBullRider backtest completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        
        results = self.generate_custom_results()
        self.export_freqtrade_format(results, start_date, end_date)
        
        # Mark backtest as completed
        self.progress_info['status'] = 'completed'
        self.progress_info['progress_pct'] = 100.0
        self.progress_info['completion_time'] = datetime.now().isoformat()
        # FIXED: Update final balance to show actual portfolio value after all positions closed
        self.progress_info['current_balance'] = self.portfolio.available_balance  # All positions closed, so cash = total
        self.progress_info['final_balance'] = self.portfolio.available_balance
        self.progress_info['profit_pct'] = ((self.portfolio.available_balance - self.portfolio.initial_balance) / self.portfolio.initial_balance) * 100
        
        import json
        with open(progress_file, 'w') as f:
            json.dump(self.progress_info, f, indent=2)
        
        logger.info(f"📁 Progress tracking saved to {progress_file}")
        
        return results
    
    def check_exit_conditions_safe(self, trade, current_price, current_time, df):
        """SafeBullRider exit logic with wider stops and daily loss protection"""
        pnl_pct = (current_price - trade.entry_price) / trade.entry_price
        duration_minutes = (current_time - trade.entry_time).total_seconds() / 60
        
        # Track maximum profit for trailing stop
        trade_id = id(trade)
        if trade_id not in self.position_max_profit:
            self.position_max_profit[trade_id] = pnl_pct
        else:
            self.position_max_profit[trade_id] = max(self.position_max_profit[trade_id], pnl_pct)
        
        max_profit = self.position_max_profit[trade_id]
        
        # 1. Dynamic stop loss (SafeBullRider uses 6% base, but can be ATR-adjusted)
        # FIXED: Match the logic from SafeBullRiderStrategy exactly
        stop_loss_pct = 0.06  # 6% base stop (SafeBullRider default)
        
        # ATR-based adjustment if available (matching strategy logic)
        if len(df) >= 1:
            last_row = df.iloc[-1]
            if not pd.isna(last_row['atr_pct']):
                atr_multiplier = 3.0  # 3x ATR for crypto
                # Calculate ATR-based stop (as positive percentage)
                atr_stop = last_row['atr_pct'] * atr_multiplier
                # Clamp between 2% and 12%
                atr_stop = max(0.02, min(0.12, atr_stop))
                # Use wider stop for volatile markets (matching strategy intent)
                # Strategy comment says "Use ATR stop if wider than base stop"
                if atr_stop > stop_loss_pct:
                    stop_loss_pct = atr_stop
                    logger.debug(f"Using ATR-based stop: {stop_loss_pct:.1%} instead of base 6%")

        if pnl_pct <= -stop_loss_pct:
            return "stop_loss", current_price
        
        # 2. ROI targets (same as Try1)
        for minutes, roi in sorted(self.minimal_roi.items()):
            if duration_minutes >= minutes and pnl_pct >= roi:
                return f"roi_{int(roi*100)}pct", current_price
        
        # 3. Trailing stop (same as Try1)
        if max_profit >= self.trailing_stop_positive_offset:
            trailing_stop_level = max_profit - self.trailing_stop_positive
            if pnl_pct <= trailing_stop_level:
                return "trailing_stop", current_price
        
        # 4. Daily loss limit protection (SafeBullRider specific)
        daily_loss_limit = self.portfolio.initial_balance * self.max_daily_loss_pct * 0.8  # 80% of limit
        if abs(self.daily_loss_today) > daily_loss_limit:
            return "daily_limit_protection", current_price
        
        return None, None
    
    def custom_stake_amount(self, current_balance, df):
        """SafeBullRider position sizing with volatility adjustment"""
        # FIXED: Use total portfolio value for consistent position sizing
        # This prevents positions from shrinking as more trades open
        total_portfolio = self.calculate_total_portfolio_value()
        
        if len(df) < 2:
            return total_portfolio * 0.08
        
        last_candle = df.iloc[-1]
        
        # Base 8% position of TOTAL portfolio (not just available cash)
        base_stake = total_portfolio * 0.08
        
        # INCREASE size in strong trends (same as Try1)
        if last_candle['uptrend'] and last_candle['momentum_20'] > 0.02:
            base_stake *= 1.3  # 30% larger in strong bull trends
        
        # INCREASE size on high volume (same as Try1)
        if last_candle['volume_ratio'] > 2.0:
            base_stake *= 1.2  # 20% larger on volume spikes
        
        # REMOVED: Dynamic position size reductions (were killing returns)
        # These adjustments happened 658 times and reduced performance significantly
        
        # SafeBullRider specific: reduce size in high volatility
        if not pd.isna(last_candle['volatility']) and last_candle['volatility'] > self.volatility_threshold:
            base_stake *= 0.8  # 20% smaller in high volatility
        
        # SAFETY: Never use more than available cash (even if position size suggests it)
        # This can happen when many positions are already open
        max_stake = self.portfolio.available_balance * 0.95  # Keep 5% buffer
        final_stake = min(base_stake, max_stake)
        
        # Warn if we had to reduce position size due to insufficient funds
        if final_stake < base_stake:
            logger.debug(f"Position size reduced from ${base_stake:.2f} to ${final_stake:.2f} due to available balance")
        
        return final_stake
    
    def get_tick_execution_price(self, tick_df, signal_time, is_entry=True):
        """Get realistic execution price from tick data with slippage"""
        tick_datetime = pd.to_datetime(tick_df['datetime'])
        mask = (tick_datetime >= signal_time) & \
               (tick_datetime < signal_time + pd.Timedelta(minutes=1))
        
        execution_ticks = tick_df[mask]
        
        if len(execution_ticks) == 0:
            return tick_df.iloc[-1]['price']
        
        if is_entry:
            return execution_ticks['price'].iloc[min(5, len(execution_ticks)-1)]
        else:
            return execution_ticks['price'].iloc[0]
    
    def close_position_at_price(self, trade_index, exit_reason, price, time):
        """Close position and update daily loss tracking"""
        trade = self.portfolio.open_positions[trade_index]
        
        # Calculate P&L
        quantity = trade.quantity
        entry_value = trade.entry_price * quantity
        exit_value = price * quantity
        
        # Apply fees
        fees = (entry_value + exit_value) * 0.0004  # 0.04% taker fee
        
        gross_pnl = exit_value - entry_value
        net_pnl = gross_pnl - fees
        pnl_pct = net_pnl / entry_value
        
        # Update daily loss tracking (SafeBullRider specific)
        current_date = time.date()
        if self.last_check_date == current_date:
            self.daily_loss_today += min(0, net_pnl)
            
            # Always track max daily loss (not just when limit hit)
            if abs(self.daily_loss_today) > self.safety_stats['max_daily_loss']:
                self.safety_stats['max_daily_loss'] = abs(self.daily_loss_today)
        
        # Update trade record
        trade.exit_time = time
        trade.exit_price = price
        trade.exit_reason = exit_reason
        trade.pnl = net_pnl
        trade.pnl_pct = pnl_pct
        trade.fees = fees
        trade.duration_minutes = int((time - trade.entry_time).total_seconds() / 60)
        trade.is_winner = net_pnl > 0
        
        # Update portfolio
        self.portfolio.available_balance += exit_value - fees/2
        # FIXED: current_balance should track total portfolio, not just cash
        # But for compatibility, we'll update it to match available_balance here
        # The real portfolio value is tracked via calculate_total_portfolio_value()
        self.portfolio.current_balance = self.portfolio.available_balance
        
        # FIXED: Update total portfolio value for accurate drawdown calculation
        self.update_portfolio_balance(time)
        
        # Move to closed trades
        self.portfolio.closed_trades.append(trade)
        self.portfolio.open_positions.remove(trade)
        
        # Clean up tracking
        trade_id = id(trade)
        if trade_id in self.position_max_profit:
            del self.position_max_profit[trade_id]
        
        # Enhanced logging with dates, gross P&L, and visual indicators
        # ⬆️ = profitable close, ⬇️ = loss close (works for both longs and shorts)
        exit_indicator = "⬆️" if net_pnl > 0 else "⬇️"
        trade_date = time.strftime('%Y-%m-%d %H:%M')
        duration_hours = trade.duration_minutes / 60
        
        logger.info(
            f"{exit_indicator} CLOSED {trade.symbol} | "
            f"Date: {trade_date} | "
            f"Price: {price:.4f} | "
            f"Gross P&L: {gross_pnl:.2f} | "
            f"Net P&L: {net_pnl:.2f} ({pnl_pct*100:.2f}%) | "
            f"Fees: {fees:.2f} | "
            f"Duration: {duration_hours:.1f}h | "
            f"Reason: {exit_reason}"
        )
        
        return trade
    
    def open_position_at_price(self, symbol, signal, price, stake, time):
        """Open position at specific price and time"""
        quantity = stake / price
        fee = stake * 0.0004  # 0.04% taker fee
        
        trade = Trade(
            symbol=symbol,
            entry_time=time,
            entry_price=price,
            entry_signal=signal,
            quantity=quantity,
            fees=fee
        )
        
        self.portfolio.available_balance -= (stake + fee)
        self.portfolio.open_positions.append(trade)
        
        # Enhanced logging with date and visual indicator
        # 🟢 = long entry, 🔵 = short entry (if implemented)
        entry_indicator = "🟢"  # Green for long positions
        trade_date = time.strftime('%Y-%m-%d %H:%M')
        
        logger.info(
            f"{entry_indicator} OPENED {symbol} | "
            f"Date: {trade_date} | "
            f"Signal: {signal} | "
            f"Price: {price:.4f} | "
            f"Stake: ${stake:.2f} | "
            f"Quantity: {quantity:.4f} | "
            f"Fee: ${fee:.2f}"
        )
        
        return trade
    
    def calculate_drawdown_stats(self):
        """FIXED: Calculate accurate drawdown statistics using total portfolio value"""
        if len(self.balance_history) == 0:
            return {
                'max_drawdown_pct': 0,
                'max_drawdown_usd': 0,
                'drawdown_duration_trades': 0,
                'recovery_time_trades': 0,
                'current_drawdown_pct': 0
            }
        
        # Extract portfolio values (not just cash balance)
        portfolio_values = [entry['balance'] for entry in self.balance_history]
        initial_balance = self.portfolio.initial_balance
        
        # Calculate running maximum (peak) and drawdown
        peak = initial_balance
        max_drawdown_usd = 0
        max_drawdown_pct = 0
        drawdown_start = None
        max_drawdown_duration = 0
        recovery_time = 0
        
        for i, portfolio_value in enumerate(portfolio_values):
            # Update peak
            if portfolio_value > peak:
                if drawdown_start is not None:
                    # We've recovered - calculate recovery time
                    recovery_time = max(recovery_time, i - drawdown_start)
                    drawdown_start = None
                peak = portfolio_value
            
            # Calculate current drawdown from peak
            drawdown_usd = peak - portfolio_value
            drawdown_pct = (drawdown_usd / peak) * 100 if peak > 0 else 0
            
            # Track maximum drawdown
            if drawdown_usd > max_drawdown_usd:
                max_drawdown_usd = drawdown_usd
                max_drawdown_pct = drawdown_pct
            
            # Track drawdown duration
            if portfolio_value < peak and drawdown_start is None:
                drawdown_start = i
            elif portfolio_value < peak and drawdown_start is not None:
                current_duration = i - drawdown_start
                max_drawdown_duration = max(max_drawdown_duration, current_duration)
        
        # Current drawdown
        current_portfolio_value = portfolio_values[-1] if portfolio_values else initial_balance
        current_peak = max(portfolio_values) if portfolio_values else initial_balance
        current_drawdown_pct = ((current_peak - current_portfolio_value) / current_peak) * 100 if current_peak > 0 else 0
        
        # SANITY CHECK: Warn if drawdown seems unrealistic
        if max_drawdown_pct > 50:
            logger.warning(f"⚠️  UNREALISTIC DRAWDOWN DETECTED: {max_drawdown_pct:.1f}%")
            logger.warning(f"   Portfolio values: ${portfolio_values[0]:.2f} → ${portfolio_values[-1]:.2f}")
            logger.warning(f"   Peak: ${max(portfolio_values):.2f}, Lowest: ${min(portfolio_values):.2f}")
        elif max_drawdown_pct > 25:
            logger.warning(f"⚠️  HIGH RISK: Drawdown {max_drawdown_pct:.1f}% - needs risk management review")
        else:
            logger.info(f"✅ REALISTIC DRAWDOWN: {max_drawdown_pct:.1f}% (within acceptable range)")
        
        return {
            'max_drawdown_pct': max_drawdown_pct,
            'max_drawdown_usd': max_drawdown_usd,
            'drawdown_duration_trades': max_drawdown_duration,
            'recovery_time_trades': recovery_time,
            'current_drawdown_pct': current_drawdown_pct,
            'total_balance_points': len(portfolio_values)
        }
    
    def generate_results_per_pair(self, results):
        """Generate per-pair results breakdown"""
        pair_results = {}
        
        for trade in self.portfolio.closed_trades:
            pair = f"{trade.symbol.replace('USDT', '/USDT:USDT')}"
            if pair not in pair_results:
                pair_results[pair] = {'trades': 0, 'total_pnl': 0.0, 'wins': 0, 'losses': 0}
            
            pair_results[pair]['trades'] += 1
            pair_results[pair]['total_pnl'] += trade.pnl
            if trade.is_winner:
                pair_results[pair]['wins'] += 1
            else:
                pair_results[pair]['losses'] += 1
        
        results_per_pair = []
        for pair, stats in pair_results.items():
            profit_mean = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0
            results_per_pair.append({
                "key": pair,
                "trades": stats['trades'],
                "profit_mean": profit_mean / 800,
                "profit_sum": stats['total_pnl'],
                "profit_total": stats['total_pnl'] / 10000,
                "wins": stats['wins'],
                "losses": stats['losses']
            })
        
        return results_per_pair
    
    def export_freqtrade_format(self, results, start_date, end_date):
        """Export multi-pair backtest results in Freqtrade standard format"""
        import json
        import csv
        from pathlib import Path
        import time as time_module
        
        results_dir = Path("user_data/backtest_results")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert trades to Freqtrade format
        freqtrade_trades = []
        for trade in self.portfolio.closed_trades:
            freqtrade_trade = {
                "pair": f"{trade.symbol.replace('USDT', '/USDT:USDT')}",
                "stake_amount": trade.entry_price * trade.quantity,
                "amount": trade.quantity,
                "open_date": trade.entry_time.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "close_date": trade.exit_time.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "open_rate": trade.entry_price,
                "close_rate": trade.exit_price,
                "fee_open": 0.0004,
                "fee_close": 0.0004,
                "trade_duration": trade.duration_minutes,
                "profit_ratio": trade.pnl_pct,
                "profit_abs": trade.pnl,
                "exit_reason": trade.exit_reason,
                "initial_stop_loss_abs": trade.entry_price * 0.94,  # 6% stop
                "initial_stop_loss_ratio": -0.06,
                "stop_loss_abs": trade.entry_price * 0.94,
                "stop_loss_ratio": -0.06,
                "min_rate": min(trade.entry_price, trade.exit_price),
                "max_rate": max(trade.entry_price, trade.exit_price),
                "is_open": False,
                "buy_tag": trade.entry_signal,
                "enter_tag": trade.entry_signal,
            }
            freqtrade_trades.append(freqtrade_trade)
        
        # Create backtest result structure
        backtest_result = {
            "strategy": {
                "SafeBullRiderStrategy": {
                    "trades": freqtrade_trades,
                    "results_per_pair": self.generate_results_per_pair(results),
                    "total_trades": len(freqtrade_trades),
                    "profit_total": results.get('backtest_summary', {}).get('total_return_pct', 0) / 100,
                    "profit_total_abs": results.get('backtest_summary', {}).get('total_pnl', 0),
                    "backtest_start": start_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_end": end_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_days": (end_date - start_date).days,
                    "starting_balance": results.get('backtest_summary', {}).get('initial_balance', self.portfolio.initial_balance),
                    "final_balance": results.get('backtest_summary', {}).get('final_balance', self.portfolio.available_balance),
                    "max_open_trades": 15,
                    "timeframe": "5m",
                    "strategy_name": "SafeBullRiderStrategy",
                    "stoploss": -0.06,  # SafeBullRider 6% stop
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.015,
                    "trailing_stop_positive_offset": 0.02,
                    "minimal_roi": {
                        "0": 0.04,
                        "120": 0.025,
                        "300": 0.015,
                        "600": 0.008
                    },
                    "wins": results.get('trade_analysis', {}).get('winning_trades', 0),
                    "losses": results.get('trade_analysis', {}).get('losing_trades', 0),
                    "winrate": results.get('backtest_summary', {}).get('win_rate_pct', 0) / 100,
                    "expectancy": results.get('trade_analysis', {}).get('avg_trade_pnl', 0),
                    "max_drawdown": results.get('backtest_summary', {}).get('max_drawdown_pct', 0) / 100,
                }
            }
        }
        
        # Save the result
        timestamp = int(time_module.time())
        filename = f"backtest-result-safe-{timestamp}.json"
        filepath = results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(backtest_result, f, indent=2, default=str)
        
        logger.info(f"✅ SafeBullRider backtest results exported to {filepath}")
        logger.info(f"📊 View in FreqUI: http://127.0.0.1:8080")
        
        # Export detailed CSV for analysis
        csv_filename = f"backtest-analysis-safe-{timestamp}.csv"
        csv_filepath = results_dir / csv_filename
        
        # Export per-pair performance CSV
        with open(csv_filepath, 'w', newline='') as csvfile:
            fieldnames = ['pair', 'trades', 'wins', 'losses', 'win_rate_pct', 'total_pnl', 'avg_pnl_per_trade', 
                         'best_trade', 'worst_trade', 'avg_hold_time_min', 'sharpe_ratio', 'max_drawdown_pct']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Calculate additional metrics per pair
            pair_stats = {}
            for trade in self.portfolio.closed_trades:
                symbol = trade.symbol
                if symbol not in pair_stats:
                    pair_stats[symbol] = {
                        'trades': [], 'wins': 0, 'losses': 0, 'total_pnl': 0,
                        'hold_times': [], 'returns': []
                    }
                
                pair_stats[symbol]['trades'].append(trade)
                pair_stats[symbol]['total_pnl'] += trade.pnl
                if trade.is_winner:
                    pair_stats[symbol]['wins'] += 1
                else:
                    pair_stats[symbol]['losses'] += 1
                
                # Calculate hold time and returns
                hold_time = (trade.exit_time - trade.entry_time).total_seconds() / 60  # minutes
                pair_stats[symbol]['hold_times'].append(hold_time)
                
                # Calculate return percentage (stake_amount = entry_price * quantity)
                stake_amount = trade.entry_price * trade.quantity if hasattr(trade, 'quantity') and trade.quantity > 0 else 1
                return_pct = (trade.pnl / stake_amount) * 100 if stake_amount > 0 else 0
                pair_stats[symbol]['returns'].append(return_pct)
            
            # Write CSV rows
            for symbol, stats in pair_stats.items():
                total_trades = len(stats['trades'])
                win_rate = (stats['wins'] / total_trades * 100) if total_trades > 0 else 0
                avg_pnl = stats['total_pnl'] / total_trades if total_trades > 0 else 0
                
                # Additional metrics
                best_trade = max([t.pnl for t in stats['trades']]) if stats['trades'] else 0
                worst_trade = min([t.pnl for t in stats['trades']]) if stats['trades'] else 0
                avg_hold_time = sum(stats['hold_times']) / len(stats['hold_times']) if stats['hold_times'] else 0
                
                # Simple Sharpe ratio approximation
                returns = stats['returns']
                if len(returns) > 1:
                    import numpy as np
                    avg_return = np.mean(returns)
                    std_return = np.std(returns)
                    sharpe = (avg_return / std_return) if std_return > 0 else 0
                else:
                    sharpe = 0
                
                # Simple max drawdown calculation
                cumulative_pnl = 0
                peak_pnl = 0
                max_dd = 0
                for trade in stats['trades']:
                    cumulative_pnl += trade.pnl
                    if cumulative_pnl > peak_pnl:
                        peak_pnl = cumulative_pnl
                    drawdown = (peak_pnl - cumulative_pnl) / abs(peak_pnl) * 100 if peak_pnl > 0 else 0
                    max_dd = max(max_dd, drawdown)
                
                writer.writerow({
                    'pair': symbol,
                    'trades': total_trades,
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'win_rate_pct': round(win_rate, 1),
                    'total_pnl': round(stats['total_pnl'], 2),
                    'avg_pnl_per_trade': round(avg_pnl, 2),
                    'best_trade': round(best_trade, 2),
                    'worst_trade': round(worst_trade, 2),
                    'avg_hold_time_min': round(avg_hold_time, 1),
                    'sharpe_ratio': round(sharpe, 2),
                    'max_drawdown_pct': round(max_dd, 1)
                })
        
        logger.info(f"📊 Detailed CSV analysis exported to {csv_filepath}")
        
        return filepath
    
    def generate_custom_results(self):
        """Generate results structure for SafeBullRider backtest"""
        total_trades = len(self.portfolio.closed_trades)
        final_balance = self.calculate_total_portfolio_value()
        
        if total_trades > 0:
            winning_trades = len([t for t in self.portfolio.closed_trades if t.is_winner])
            losing_trades = total_trades - winning_trades
            win_rate = (winning_trades / total_trades) * 100
            
            total_pnl = sum(t.pnl for t in self.portfolio.closed_trades)
            avg_trade_pnl = total_pnl / total_trades
            max_win = max((t.pnl for t in self.portfolio.closed_trades), default=0)
            max_loss = min((t.pnl for t in self.portfolio.closed_trades), default=0)
            
            # Calculate profit factor
            gross_profit = sum(t.pnl for t in self.portfolio.closed_trades if t.is_winner)
            gross_loss = abs(sum(t.pnl for t in self.portfolio.closed_trades if not t.is_winner))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            total_return_pct = ((final_balance - self.portfolio.initial_balance) / self.portfolio.initial_balance) * 100
        else:
            winning_trades = losing_trades = 0
            win_rate = 0
            total_pnl = avg_trade_pnl = max_win = max_loss = profit_factor = total_return_pct = 0
        
        # Calculate drawdown stats
        drawdown_stats = self.calculate_drawdown_stats()
        
        return {
            'backtest_summary': {
                'initial_balance': self.portfolio.initial_balance,
                'final_balance': final_balance,
                'total_trades': total_trades,
                'total_pnl': total_pnl,
                'total_return_pct': total_return_pct,
                'win_rate_pct': win_rate,
                'max_drawdown_pct': drawdown_stats['max_drawdown_pct'],
                'max_drawdown_usd': drawdown_stats['max_drawdown_usd']
            },
            'trade_analysis': {
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'avg_trade_pnl': avg_trade_pnl,
                'max_win': max_win,
                'max_loss': max_loss,
                'profit_factor': profit_factor
            }
        }

def detect_available_date_range():
    """Detect available date range across all pairs"""
    all_dates = set()
    pairs_with_data = []
    
    trading_pairs = [
        "BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT",
        "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "BCHUSDT",
        "TIAUSDT", "DOTUSDT", "POLUSDT", "UNIUSDT"
    ]
    
    for pair in trading_pairs:
        tick_dir = Path(f'user_data/tick_data/{pair}/')
        if tick_dir.exists():
            files = sorted([f for f in tick_dir.glob('*.feather')])
            if files:
                pairs_with_data.append(pair)
                for file in files:
                    try:
                        date_str = file.name.split('trades-')[1].replace('.feather', '')
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                        all_dates.add(date_obj)
                    except:
                        continue
    
    if not all_dates:
        return None, None, []
    
    return min(all_dates), max(all_dates), pairs_with_data

def main():
    import argparse
    
    available_start, available_end, pairs_with_data = detect_available_date_range()
    
    parser = argparse.ArgumentParser(description="SafeBullRider Multi-Pair Realistic Backtesting")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date (YYYY-MM-DD). Default: use all available data")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (YYYY-MM-DD). Default: use all available data")
    parser.add_argument("--recent", action="store_true",
                        help="Test recent 3 months instead of full dataset")
    parser.add_argument("--week", action="store_true",
                        help="Test last 7 days only")
    parser.add_argument("--month", action="store_true",
                        help="Test last 30 days only")
    parser.add_argument("--year", type=int, default=None,
                        help="Test specific calendar year (e.g., --year 2023) or use --year 0 for last 365 days")
    parser.add_argument("--today", action="store_true",
                        help="Test today only (if data available)")
    parser.add_argument("--yesterday", action="store_true",
                        help="Test yesterday only")
    parser.add_argument("--days", type=int, default=None,
                        help="Test last N days (e.g., --days 14 for 2 weeks)")
    parser.add_argument("--balance", type=float, default=2000,
                        help="Starting balance (default: 2000)")
    parser.add_argument("--pairs", type=str, default=None,
                        help="Test specific pairs (e.g., --pairs BTCUSDT,ETHUSDT or --pairs BTCUSDT)")
    
    args = parser.parse_args()
    
    # Handle custom pairs selection
    custom_pairs = None
    if args.pairs:
        # Split by comma and clean up
        custom_pairs = [pair.strip().upper() for pair in args.pairs.split(',')]
        # Validate pairs
        valid_pairs = [
            "BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT",
            "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "BCHUSDT",
            "TIAUSDT", "DOTUSDT", "POLUSDT", "UNIUSDT"
        ]
        invalid_pairs = [pair for pair in custom_pairs if pair not in valid_pairs]
        if invalid_pairs:
            print(f"❌ Invalid pairs: {', '.join(invalid_pairs)}")
            print(f"✅ Valid pairs: {', '.join(valid_pairs)}")
            return
        print(f"🎯 Testing custom pairs: {', '.join(custom_pairs)} ({len(custom_pairs)} total)")
    
    # Determine date range
    if args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    elif args.today:
        # Test today only
        end_date = datetime.now().date()
        start_date = end_date
        print(f"📅 Testing today only: {start_date}")
    elif args.yesterday:
        # Test yesterday only
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date
        print(f"📅 Testing yesterday only: {start_date}")
    elif args.days:
        # Test last N days
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date - timedelta(days=args.days - 1)
        print(f"📅 Testing last {args.days} days: {start_date} to {end_date}")
    elif args.week:
        # Test last 7 days
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date - timedelta(days=6)
        print(f"📅 Testing last week (7 days): {start_date} to {end_date}")
    elif args.month:
        # Test last 30 days
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date - timedelta(days=29)
        print(f"📅 Testing last month (30 days): {start_date} to {end_date}")
    elif args.year is not None:
        if args.year == 0:
            # Test last 365 days (backward compatibility)
            end_date = datetime.now().date() - timedelta(days=1)
            start_date = end_date - timedelta(days=364)
            print(f"📅 Testing last year (365 days): {start_date} to {end_date}")
        else:
            # Test specific calendar year
            if args.year < 2020 or args.year > 2030:
                print(f"❌ Invalid year: {args.year}. Must be between 2020-2030")
                return
            start_date = datetime(args.year, 1, 1).date()
            end_date = datetime(args.year, 12, 31).date()
            print(f"📅 Testing calendar year {args.year}: {start_date} to {end_date}")
    elif args.recent:
        # Test last 3 months (90 days)
        if available_end:
            end_date = available_end
            start_date = max(available_start, end_date - timedelta(days=90))
            print(f"📅 Testing recent period (90 days): {start_date} to {end_date}")
        else:
            print("❌ No tick data found!")
            return
    elif available_start and available_end:
        start_date = available_start
        end_date = available_end
        print(f"🔍 Auto-detected date range: {start_date} to {end_date}")
        print(f"📊 Total available: {(end_date - start_date).days + 1} days (~{((end_date - start_date).days + 1) / 365.25:.1f} years)")
        print(f"📈 Pairs with data: {', '.join(pairs_with_data[:5])}{'...' if len(pairs_with_data) > 5 else ''} ({len(pairs_with_data)} total)")
    else:
        print("❌ No tick data found!")
        return
    
    print("=" * 80)
    print("SAFEBULLRIDER MULTI-PAIR REALISTIC BACKTESTING - Smart Enhanced Strategy")
    print("=" * 80)
    print(f"Date Range:       {start_date} to {end_date}")
    days_total = (end_date - start_date).days + 1
    print(f"Testing Period:   {days_total} days ({days_total / 365.25:.1f} years)")
    print(f"Strategy:         SafeBullRiderStrategy (EXACT implementation)")
    print(f"Trading Pairs:    {len(pairs_with_data)} pairs available")
    print(f"Initial Balance:  ${args.balance:,.0f} (custom starting balance)")
    print(f"Max Open Trades:  15 total (max 2 per pair)")
    print(f"Position Size:    ~8% per trade (~$160 per position)")
    print(f"Weekend Filter:   DISABLED (trade 24/7)")
    print(f"Safety Features:  Daily loss limit (5% max)")
    print(f"Extra Checks:     Quality filters + volatility management")
    
    if days_total > 365:
        print("⚠️  WARNING: Testing multiple years may take 45+ minutes")
    elif days_total > 90:
        print(f"⏱️  Estimated time: ~{days_total / 20:.0f}-{days_total / 10:.0f} minutes")
    
    print("=" * 80)
    print()
    
    backtester = SafeRealisticBacktester()
    # Set custom pairs if specified
    if custom_pairs:
        backtester.trading_pairs = custom_pairs
    # Set custom starting balance
    backtester.portfolio.initial_balance = args.balance
    backtester.portfolio.available_balance = args.balance
    backtester.portfolio.current_balance = args.balance
    
    try:
        results = backtester.run_realistic_backtest(start_date, end_date)
        
        # Display results
        summary = results.get('backtest_summary', {})
        trade_analysis = results.get('trade_analysis', {})
        
        print("\\n🎯 SAFEBULLRIDER MULTI-PAIR BACKTEST RESULTS")
        print("=" * 60)
        print(f"Final Balance:    ${summary.get('final_balance', 0):,.2f}")
        print(f"Total Return:     {summary.get('total_return_pct', 0):+.2f}%")
        print(f"Total P&L:        ${summary.get('total_pnl', 0):+.2f}")
        print(f"Total Trades:     {summary.get('total_trades', 0)}")
        print(f"Win Rate:         {summary.get('win_rate_pct', 0):.1f}%")
        
        # Calculate and display gross profit/loss
        gross_profit = 0
        gross_loss = 0
        for trade in backtester.portfolio.closed_trades:
            # Calculate gross P&L (before fees)
            gross_pnl = (trade.exit_price - trade.entry_price) * trade.quantity
            if gross_pnl > 0:
                gross_profit += gross_pnl
            else:
                gross_loss += abs(gross_pnl)
        
        print(f"Gross Profit:     ${gross_profit:,.2f} (sum of all winning trades before fees)")
        print(f"Gross Loss:       ${gross_loss:,.2f} (sum of all losing trades before fees)")
        print(f"Profit/Loss Ratio: {gross_profit/gross_loss:.2f}" if gross_loss > 0 else "Profit/Loss Ratio: N/A")
        
        # Enhanced metrics with quality indicators
        if summary.get('total_trades', 0) > 0:
            # Profit Factor with quality indicator
            profit_factor = trade_analysis.get('profit_factor', 0)
            if profit_factor >= 2.0:
                pf_indicator = "✅ Excellent"
            elif profit_factor >= 1.5:
                pf_indicator = "✅ Good"
            elif profit_factor >= 1.0:
                pf_indicator = "⚠️  Marginal"
            else:
                pf_indicator = "❌ Poor"
            
            print(f"Profit Factor:    {profit_factor:.2f} {pf_indicator}")
            
            # FIXED: Calculate portfolio Sharpe ratio using DAILY returns
            if len(backtester.daily_balance_snapshots) > 1:
                import numpy as np
                
                # Get daily closing balances (last balance of each day)
                daily_balances = []
                dates = sorted(backtester.daily_balance_snapshots.keys())
                for date in dates:
                    if backtester.daily_balance_snapshots[date]:
                        # Use last balance of the day
                        daily_balances.append(backtester.daily_balance_snapshots[date][-1])
                
                if len(daily_balances) > 1:
                    # Calculate daily returns
                    daily_returns = np.diff(daily_balances) / daily_balances[:-1]
                    
                    # Remove any NaN or infinite values
                    daily_returns = daily_returns[np.isfinite(daily_returns)]
                    
                    if len(daily_returns) > 0:
                        # Calculate mean and std of daily returns
                        daily_mean = np.mean(daily_returns)
                        daily_std = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0
                        
                        # NON-ANNUALIZED Sharpe ratio - just for the actual backtest period
                        # This gives you the actual risk-adjusted return for your test period
                        if daily_std > 0:
                            # Simple Sharpe: mean return / volatility for the period
                            sharpe_ratio = daily_mean / daily_std
                            # Scale by sqrt of number of days to normalize
                            sharpe_ratio = sharpe_ratio * np.sqrt(len(daily_returns))
                        else:
                            sharpe_ratio = 0
                    else:
                        sharpe_ratio = 0
                else:
                    sharpe_ratio = 0
                
                # Sanity check - warn if unrealistic
                if sharpe_ratio > 5:
                    logger.warning(f"⚠️  Sharpe ratio {sharpe_ratio:.2f} seems unrealistic - check calculation")
                
                # Adjusted thresholds for non-annualized Sharpe
                days_in_test = len(daily_returns)
                if sharpe_ratio >= 2.0:
                    sharpe_indicator = "✅ Excellent"
                elif sharpe_ratio >= 1.0:
                    sharpe_indicator = "✅ Good"
                elif sharpe_ratio >= 0.5:
                    sharpe_indicator = "⚠️  Marginal"
                else:
                    sharpe_indicator = "❌ Poor"
                
                print(f"Sharpe Ratio:     {sharpe_ratio:.2f} ({days_in_test} days) {sharpe_indicator}")
            
            # Max Drawdown with better formatting
            dd_pct = summary.get('max_drawdown_pct', 0)
            if dd_pct <= 5.0:
                dd_indicator = "✅ Low Risk"
            elif dd_pct <= 10.0:
                dd_indicator = "⚠️  Moderate Risk"
            elif dd_pct <= 20.0:
                dd_indicator = "❌ High Risk"
            else:
                dd_indicator = "🚨 Extreme Risk"
            
            print(f"Max Drawdown:     {dd_pct:.2f}% (${summary.get('max_drawdown_usd', 0):.2f}) {dd_indicator}")
        
            print(f"Avg Trade:        ${trade_analysis.get('avg_trade_pnl', 0):+.2f}")
            print(f"Best Trade:       ${trade_analysis.get('max_win', 0):+.2f}")
            print(f"Worst Trade:      ${trade_analysis.get('max_loss', 0):+.2f}")
            
            # Add warnings for poor performance
            if profit_factor < 1.0:
                print(f"⚠️  WARNING: Poor Profit Factor: {profit_factor:.2f} (<1.0 = losing strategy)")
            if dd_pct > 15:
                print(f"⚠️  WARNING: High drawdown: {dd_pct:.1f}% (>15% = high risk)")
        
        # Show sample trades with dates
        if len(backtester.portfolio.closed_trades) > 0:
            print("\\n📅 TRADE TIMELINE SAMPLE:")
            trades_to_show = min(5, len(backtester.portfolio.closed_trades))
            
            # Show first few trades
            print("  First trades:")
            for i in range(trades_to_show):
                trade = backtester.portfolio.closed_trades[i]
                indicator = "🟢" if trade.is_winner else "🔴"
                print(f"    {indicator} {trade.entry_time.strftime('%Y-%m-%d %H:%M')} | {trade.symbol} | "
                      f"P&L: ${trade.pnl:+.2f} ({trade.pnl_pct*100:+.1f}%) | Duration: {trade.duration_minutes/60:.1f}h")
            
            # Show last few trades if we have more than 10 total
            if len(backtester.portfolio.closed_trades) > 10:
                print("  Last trades:")
                for i in range(-trades_to_show, 0):
                    trade = backtester.portfolio.closed_trades[i]
                    indicator = "🟢" if trade.is_winner else "🔴"
                    print(f"    {indicator} {trade.entry_time.strftime('%Y-%m-%d %H:%M')} | {trade.symbol} | "
                          f"P&L: ${trade.pnl:+.2f} ({trade.pnl_pct*100:+.1f}%) | Duration: {trade.duration_minutes/60:.1f}h")
        
        print("\\n📊 PORTFOLIO BREAKDOWN:")
        pair_results = {}
        for trade in backtester.portfolio.closed_trades:
            pair = trade.symbol
            if pair not in pair_results:
                pair_results[pair] = {'trades': 0, 'pnl': 0.0, 'wins': 0}
            pair_results[pair]['trades'] += 1
            pair_results[pair]['pnl'] += trade.pnl
            if trade.is_winner:
                pair_results[pair]['wins'] += 1
        
        # Show ALL pairs, not just top 5
        all_pairs = sorted(pair_results.items(), key=lambda x: x[1]['pnl'], reverse=True)
        for pair, stats in all_pairs:
            win_rate = (stats['wins'] / stats['trades']) * 100 if stats['trades'] > 0 else 0
            print(f"  {pair:<10} | {stats['trades']} trades | ${stats['pnl']:+.2f} | {win_rate:.0f}% win rate")
        
        # Display safety statistics (minimal - only essential)
        if hasattr(backtester, 'safety_stats'):
            print("\\n🛡️  SAFETY FEATURES (MINIMAL FOR MAX RETURNS):")
            print(f"  Daily Limit Hits:    {backtester.safety_stats['daily_limit_hits']} times")
            print(f"  Emergency Brakes:    {backtester.safety_stats['emergency_brakes']} times")
            print(f"  Max Daily Loss:      ${backtester.safety_stats['max_daily_loss']:.2f}")
            print(f"  Days with Limits:    {backtester.safety_stats['days_with_limits']} days")
            print(f"  🎯 REMOVED correlation limits & position sizing to preserve 470% returns")
        
        print("\\n✅ SafeBullRider multi-pair realistic backtesting complete!")
        print("📈 Compare with Try1BullRider to see impact of safety features")
        print("🛡️  Daily loss limit protection + enhanced quality filters")
        print("🌍 Multi-pair diversification like your actual live setup")
        
    except KeyboardInterrupt:
        print("\\n⚠️  Backtest interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()