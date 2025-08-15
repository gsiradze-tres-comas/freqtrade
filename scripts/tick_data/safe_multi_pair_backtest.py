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
    """
    
    def __init__(self):
        super().__init__()
        
        # Your EXACT trading pairs from config_billionaire.json
        self.trading_pairs = [
            "BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT",
            "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "BCHUSDT",
            "TIAUSDT", "DOTUSDT", "POLUSDT", "UNIUSDT", "1INCHUSDT"
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
            
            # Check if current daily loss exceeds limit
            daily_loss_limit = self.portfolio.initial_balance * self.max_daily_loss_pct  # $100 on $2k balance
            
            if abs(self.daily_loss_today) > daily_loss_limit:
                logger.warning(f"Daily loss limit reached: ${abs(self.daily_loss_today):.2f} > ${daily_loss_limit:.2f}")
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
            'current_balance': self.portfolio.available_balance,
            'total_trades': 0,
            'pairs_processed': 0,
            'status': 'running'
        }
        
        # Reset portfolio
        self.portfolio = Portfolio()
        self.portfolio.initial_balance = 2000
        self.portfolio.available_balance = 2000
        self.portfolio.current_balance = 2000
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
            self.progress_info['current_balance'] = self.portfolio.available_balance
            self.progress_info['total_trades'] = len(self.portfolio.closed_trades)
            
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
        
        results = self.generate_results()
        self.export_freqtrade_format(results, start_date, end_date)
        
        # Mark backtest as completed
        self.progress_info['status'] = 'completed'
        self.progress_info['progress_pct'] = 100.0
        self.progress_info['completion_time'] = datetime.now().isoformat()
        
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
        stop_loss_pct = 0.06  # 6% base stop (SafeBullRider default)
        
        # ATR-based adjustment if available
        if len(df) >= 1:
            last_row = df.iloc[-1]
            if not pd.isna(last_row['atr_pct']):
                atr_multiplier = 3.0  # 3x ATR for crypto
                atr_stop = last_row['atr_pct'] * atr_multiplier
                # Use ATR stop if wider (2% to 12% range)
                atr_stop = max(0.02, min(0.12, atr_stop))
                if atr_stop > stop_loss_pct:  # Only if ATR suggests wider stop
                    stop_loss_pct = atr_stop

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
        if len(df) < 2:
            return current_balance * 0.08
        
        last_candle = df.iloc[-1]
        
        # Base 8% position (SafeBullRider matches Try1)
        base_stake = current_balance * 0.08
        
        # INCREASE size in strong trends (same as Try1)
        if last_candle['uptrend'] and last_candle['momentum_20'] > 0.02:
            base_stake *= 1.3  # 30% larger in strong bull trends
        
        # INCREASE size on high volume (same as Try1)
        if last_candle['volume_ratio'] > 2.0:
            base_stake *= 1.2  # 20% larger on volume spikes
        
        # SafeBullRider specific: reduce size in high volatility
        if not pd.isna(last_candle['volatility']) and last_candle['volatility'] > self.volatility_threshold:
            base_stake *= 0.8  # 20% smaller in high volatility
        
        return base_stake
    
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
        
        logger.info(f"Closed {trade.symbol} @ {price:.4f}, P&L: {net_pnl:.2f} ({pnl_pct*100:.2f}%), Reason: {exit_reason}")
        
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
        
        logger.info(f"Opened {signal} position: {symbol} @ {price:.4f}, Stake: {stake:.2f}")
        
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
                    "profit_total": results['backtest_summary']['total_return_pct'] / 100,
                    "profit_total_abs": results['backtest_summary']['total_pnl'],
                    "backtest_start": start_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_end": end_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_days": (end_date - start_date).days,
                    "starting_balance": results['backtest_summary']['initial_balance'],
                    "final_balance": results['backtest_summary']['final_balance'],
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
                    "wins": results['trade_analysis']['winning_trades'],
                    "losses": results['trade_analysis']['losing_trades'],
                    "winrate": results['backtest_summary']['win_rate_pct'] / 100,
                    "expectancy": results['trade_analysis']['avg_trade_pnl'] if 'avg_trade_pnl' in results['trade_analysis'] else 0,
                    "max_drawdown": results['backtest_summary']['max_drawdown_pct'] / 100 if 'max_drawdown_pct' in results['backtest_summary'] else 0,
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
                
                # Calculate return percentage
                return_pct = (trade.pnl / trade.stake_amount) * 100 if trade.stake_amount > 0 else 0
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

def detect_available_date_range():
    """Detect available date range across all pairs"""
    all_dates = set()
    pairs_with_data = []
    
    trading_pairs = [
        "BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT",
        "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "BCHUSDT",
        "TIAUSDT", "DOTUSDT", "POLUSDT", "UNIUSDT", "1INCHUSDT"
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
    
    args = parser.parse_args()
    
    # Determine date range
    if args.start and args.end:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    elif args.recent:
        if available_end:
            end_date = available_end
            start_date = end_date - timedelta(days=90)
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
    print(f"Initial Balance:  $2,000 (realistic starting balance)")
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
    
    try:
        results = backtester.run_realistic_backtest(start_date, end_date)
        
        # Display results
        summary = results['backtest_summary']
        trade_analysis = results['trade_analysis']
        
        print("\\n🎯 SAFEBULLRIDER MULTI-PAIR BACKTEST RESULTS")
        print("=" * 60)
        print(f"Final Balance:    ${summary['final_balance']:,.2f}")
        print(f"Total Return:     {summary['total_return_pct']:+.2f}%")
        print(f"Total P&L:        ${summary['total_pnl']:+.2f}")
        print(f"Total Trades:     {summary['total_trades']}")
        print(f"Win Rate:         {summary['win_rate_pct']:.1f}%")
        
        if 'max_drawdown_pct' in summary:
            print(f"Max Drawdown:     {summary['max_drawdown_pct']:.2f}% (${summary['max_drawdown_usd']:.2f})")
        
        if summary['total_trades'] > 0:
            print(f"Avg Trade:        ${trade_analysis['avg_trade_pnl']:+.2f}")
            print(f"Best Trade:       ${trade_analysis['max_win']:+.2f}")
            print(f"Worst Trade:      ${trade_analysis['max_loss']:+.2f}")
        
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