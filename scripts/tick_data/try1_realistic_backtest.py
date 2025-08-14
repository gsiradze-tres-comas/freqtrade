#!/usr/bin/env python3
"""
Try1BullRider Multi-Pair Realistic Backtesting - Works Like Paper Trading
Tests the exact Try1BullRider strategy across all your trading pairs
Matches your live setup: 15 pairs, max 15 total positions, realistic diversification
NO weekend filters, NO extra checks - just pure strategy logic + realistic execution
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

class Try1RealisticBacktester(TickBacktester):
    """
    Multi-pair realistic backtester that matches your Try1BullRider strategy exactly
    Trades all your pairs with realistic portfolio diversification
    NO weekend filters - NO extra checks - just pure strategy + realistic execution
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
        self.portfolio.max_open_trades = 15      # Try1 config max_open_trades
        self.max_positions_per_pair = 2         # Prevent concentration (max 2 per pair)
        
        # Try1BullRiderStrategy parameters (EXACT values from your code)
        self.rsi_oversold = 40
        self.rsi_overbought = 65
        self.volume_multiplier = 1.2
        self.trend_strength = 0.005
        
        # ROI targets (EXACT from Try1BullRider)
        self.minimal_roi = {
            0: 0.04,    # 4% target
            120: 0.025, # 2.5% after 2 hours 
            300: 0.015, # 1.5% after 5 hours
            600: 0.008  # 0.8% after 10 hours
        }
        
        # Trailing stop parameters (EXACT from Try1)
        self.trailing_stop_positive = 0.015      # 1.5%
        self.trailing_stop_positive_offset = 0.02 # 2%
        
        # Track highest profit for trailing stop
        self.position_max_profit = {}
        
        # Track positions per pair for diversification
        self.positions_per_pair = {pair: 0 for pair in self.trading_pairs}
        
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
        """Update portfolio balance tracking with total portfolio value - FIXED"""
        total_portfolio_value = self.calculate_total_portfolio_value(current_prices)
        
        self.balance_history.append({
            'timestamp': timestamp,
            'balance': total_portfolio_value,
            'available_cash': self.portfolio.available_balance,
            'open_positions': len(self.portfolio.open_positions),
            'position_value': total_portfolio_value - self.portfolio.available_balance
        })
        
        # Track daily snapshots for proper drawdown analysis
        date_str = timestamp.strftime('%Y-%m-%d')
        if date_str not in self.daily_balance_snapshots:
            self.daily_balance_snapshots[date_str] = []
        self.daily_balance_snapshots[date_str].append(total_portfolio_value)
        
    def create_5min_candles(self, tick_df):
        """Convert tick data to 5-minute OHLCV candles (matches Try1's 5m timeframe)"""
        if len(tick_df) == 0:
            return pd.DataFrame()
        
        # Create a copy to avoid modifying original data
        tick_copy = tick_df.copy()
        tick_copy['datetime'] = pd.to_datetime(tick_copy['datetime'])
        tick_copy.set_index('datetime', inplace=True)
        
        # Create 5-minute candles (matching Try1 strategy timeframe)
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
        """EXACT implementation of Try1BullRiderStrategy indicators"""
        if len(df) < 100:  # Try1 needs startup_candle_count = 100
            return df
        
        # Basic EMAs for trend (EXACT from Try1)
        df['ema_8'] = ta.EMA(df, timeperiod=8)
        df['ema_21'] = ta.EMA(df, timeperiod=21)
        df['ema_50'] = ta.EMA(df, timeperiod=50)
        
        # RSI (EXACT from Try1)
        df['rsi'] = ta.RSI(df, timeperiod=14)
        
        # Volume (EXACT from Try1)
        df['volume_mean'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_mean']
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # Price momentum (EXACT from Try1)
        df['momentum_5'] = df['close'].pct_change(periods=5)
        df['momentum_20'] = df['close'].pct_change(periods=20)
        
        # ATR for volatility (EXACT from Try1)
        df['atr'] = ta.ATR(df, timeperiod=14)
        
        # Trend detection (EXACT from Try1BullRiderStrategy)
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
        
        # Candle patterns (EXACT from Try1)
        df['green_candle'] = (df['close'] > df['open']).astype(int)
        df['red_candle'] = (df['close'] < df['open']).astype(int)
        df['body_size'] = abs(df['close'] - df['open'])
        
        return df
    
    def check_entry_signals(self, df, timestamp):
        """EXACT entry logic from Try1BullRiderStrategy - NO weekend filter, NO extra checks"""
        if len(df) < 2:
            return None
        
        last = df.iloc[-1]
        
        # Skip if indicators not ready
        if pd.isna(last['rsi']) or pd.isna(last['uptrend']):
            return None
        
        # LONG conditions (EXACT from Try1BullRider) - three patterns with OR logic
        
        # Pattern 1: Dip buying in uptrend (EXACT from Try1)
        long_dip_buy = (
            last['uptrend'] and
            last['rsi'] < self.rsi_oversold and
            last['volume_ratio'] > self.volume_multiplier
        )
        
        # Pattern 2: Momentum breakout (EXACT from Try1)
        long_breakout = (
            last['momentum_5'] > self.trend_strength and
            last['green_candle'] == 1 and
            last['volume_ratio'] > 1.5 and
            last['close'] > last['ema_8']
        )
        
        # Pattern 3: Trend following (EXACT from Try1)
        long_trend_follow = (
            last['uptrend'] and
            last['close'] > df.iloc[-2]['close'] and
            last['rsi'] > 45 and last['rsi'] < 70 and
            last['volume_ratio'] > 1.0
        )
        
        # Combine with OR logic (like Try1 strategy)
        if long_dip_buy or long_breakout or long_trend_follow:
            # Try1's only filter: ATR volatility check
            if last['atr'] / last['close'] <= 0.05:  # 5% ATR limit (from confirm_trade_entry)
                return 'bull_long'
        
        return None
    
    def check_exit_conditions_advanced(self, trade, current_price, current_time, df):
        """EXACT exit logic matching Try1BullRiderStrategy"""
        pnl_pct = (current_price - trade.entry_price) / trade.entry_price
        duration_minutes = (current_time - trade.entry_time).total_seconds() / 60
        
        # Track maximum profit for trailing stop
        trade_id = id(trade)
        if trade_id not in self.position_max_profit:
            self.position_max_profit[trade_id] = pnl_pct
        else:
            self.position_max_profit[trade_id] = max(self.position_max_profit[trade_id], pnl_pct)
        
        max_profit = self.position_max_profit[trade_id]
        
        # 1. Stop loss at -4% (EXACT from Try1)
        if pnl_pct <= -0.04:
            return "stop_loss", current_price
        
        # 2. ROI targets (EXACT from Try1)
        for minutes, roi in sorted(self.minimal_roi.items()):
            if duration_minutes >= minutes and pnl_pct >= roi:
                return f"roi_{int(roi*100)}pct", current_price
        
        # 3. Trailing stop (EXACT from Try1)
        if max_profit >= self.trailing_stop_positive_offset:
            # Trailing stop is active
            trailing_stop_level = max_profit - self.trailing_stop_positive
            if pnl_pct <= trailing_stop_level:
                return "trailing_stop", current_price
        
        # 4. Exit signal conditions (EXACT from Try1's populate_exit_trend)
        if len(df) >= 2:
            last = df.iloc[-1]
            if (last['downtrend'] and
                last['momentum_5'] < -0.02 and
                last['momentum_20'] < -0.03 and
                last['rsi'] < 25 and
                last['volume_ratio'] > 2.0):
                return "exit_signal", current_price
        
        # 5. Custom exit (EXACT from Try1's custom_exit)
        if pnl_pct > 0.05 and len(df) >= 2:  # 5%+ profit protection
            if df.iloc[-1]['momentum_5'] < -0.01:
                return "profit_protection", current_price
        
        return None, None
    
    def custom_stake_amount(self, current_balance, df):
        """EXACT Try1BullRiderStrategy position sizing"""
        if len(df) < 2:
            return current_balance * 0.08
        
        last_candle = df.iloc[-1]
        
        # Base 8% position (Try1's exact custom_stake_amount logic)
        total_balance = current_balance  # Simulate self.wallets.get_total_stake_amount()
        base_stake = total_balance * 0.08
        
        # INCREASE size in strong trends (EXACT from Try1)
        if last_candle['uptrend'] and last_candle['momentum_20'] > 0.02:
            base_stake *= 1.3  # 30% larger in strong bull trends
        elif last_candle['downtrend'] and last_candle['momentum_20'] < -0.02:
            base_stake *= 1.3  # 30% larger in strong bear trends
        
        # INCREASE size on high volume (EXACT from Try1)
        if last_candle['volume_ratio'] > 2.0:
            base_stake *= 1.2  # 20% larger on volume spikes
        
        return base_stake
    
    def run_realistic_backtest(self, start_date, end_date):
        """
        Run multi-pair realistic backtest matching Try1BullRider exactly
        NO weekend filters, NO extra checks - pure strategy logic across all pairs
        """
        import time
        start_time = time.time()
        
        logger.info(f"Starting Try1BullRider multi-pair backtest from {start_date} to {end_date}")
        logger.info(f"Trading pairs: {', '.join(self.trading_pairs)}")
        logger.info("NO weekend filters - NO extra checks - pure Try1 strategy logic")
        
        # Reset portfolio to match Try1 setup
        self.portfolio = Portfolio()
        self.portfolio.initial_balance = 2000  # More realistic starting balance
        self.portfolio.available_balance = 2000
        self.portfolio.current_balance = 2000
        self.portfolio.position_size_pct = 0.08
        self.portfolio.max_open_trades = 15     # Try1 config max_open_trades
        self.position_max_profit = {}
        self.positions_per_pair = {pair: 0 for pair in self.trading_pairs}
        
        current_date = start_date
        total_days = (end_date - start_date).days + 1
        day_count = 0
        
        # Accumulate candles per pair for indicator calculation
        all_candles_per_pair = {pair: pd.DataFrame() for pair in self.trading_pairs}
        
        while current_date <= end_date:
            day_count += 1
            
            # Get available pairs for this date
            available_pairs = self.get_available_pairs_for_date(current_date)
            
            if len(available_pairs) > 0:
                # Load and process data for each available pair
                pair_data = {}
                
                for pair in available_pairs:
                    # Load tick data for the pair
                    tick_df = self.load_tick_data(pair, current_date)
                    
                    if tick_df is not None and len(tick_df) > 0:
                        # Convert to 5-min candles
                        daily_candles = self.create_5min_candles(tick_df)
                        
                        if len(daily_candles) > 0:
                            # Append to accumulated candles for this pair
                            all_candles_per_pair[pair] = pd.concat([all_candles_per_pair[pair], daily_candles], ignore_index=True)
                            
                            # Keep only last 200 candles for efficiency
                            if len(all_candles_per_pair[pair]) > 200:
                                all_candles_per_pair[pair] = all_candles_per_pair[pair].iloc[-200:]
                            
                            # Calculate indicators for this pair
                            all_candles_per_pair[pair] = self.populate_indicators(all_candles_per_pair[pair])
                            
                            # Store for processing
                            pair_data[pair] = {
                                'candles': all_candles_per_pair[pair],
                                'daily_candles': daily_candles,
                                'tick_df': tick_df
                            }
                
                # Process signals for all pairs simultaneously (like live trading)
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
                                exit_reason, exit_price = self.check_exit_conditions_advanced(
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
                        
                        # Check for new entry signals (respect pair and total limits)
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
                                    
                                    # Calculate position size (Try1's logic)
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
            
            current_date += timedelta(days=1)
        
        # Close any remaining positions at end
        if len(self.portfolio.open_positions) > 0:
            # Get last price for each pair with open positions
            for i in reversed(range(len(self.portfolio.open_positions))):
                trade = self.portfolio.open_positions[i]
                pair = trade.symbol
                
                # Try to get last known price for this pair
                if pair in all_candles_per_pair and len(all_candles_per_pair[pair]) > 0:
                    last_price = all_candles_per_pair[pair].iloc[-1]['close']
                else:
                    last_price = trade.entry_price  # Fallback to entry price
                
                end_datetime = pd.Timestamp(end_date).tz_localize('UTC')
                self.close_position_at_price(i, "backtest_end", last_price, end_datetime)
        
        elapsed = time.time() - start_time
        logger.info(f"Try1BullRider backtest completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        
        # Final portfolio validation
        final_validation = self.validate_portfolio_consistency()
        logger.info(f"Final Portfolio: Cash=${final_validation['available_cash']:.2f}, Positions=${final_validation['position_value']:.2f}, Total=${final_validation['total_portfolio']:.2f}")
        
        results = self.generate_results()
        
        # Export to Freqtrade standard format for FreqUI visualization
        self.export_freqtrade_format(results, start_date, end_date)
        
        return results
    
    def get_tick_execution_price(self, tick_df, signal_time, is_entry=True):
        """Get realistic execution price from tick data with slippage"""
        # Find ticks around signal time (within next minute)
        tick_datetime = pd.to_datetime(tick_df['datetime'])
        mask = (tick_datetime >= signal_time) & \
               (tick_datetime < signal_time + pd.Timedelta(minutes=1))
        
        execution_ticks = tick_df[mask]
        
        if len(execution_ticks) == 0:
            # No ticks in timeframe, use last known price
            return tick_df.iloc[-1]['price']
        
        # Simulate market order execution with realistic slippage
        if is_entry:
            # Entry: likely to get slightly worse price (buy at ask)
            return execution_ticks['price'].iloc[min(5, len(execution_ticks)-1)]  # 5th tick or last
        else:
            # Exit: sell at bid (first available)
            return execution_ticks['price'].iloc[0]  # First tick
    
    def close_position_at_price(self, trade_index, exit_reason, price, time):
        """Close position at specific price and time"""
        trade = self.portfolio.open_positions[trade_index]
        
        # Calculate P&L
        quantity = trade.quantity
        entry_value = trade.entry_price * quantity
        exit_value = price * quantity
        
        # Apply Binance futures fees (0.02% maker, 0.04% taker - use taker for market orders)
        fees = (entry_value + exit_value) * 0.0004  # 0.04% taker fee
        
        gross_pnl = exit_value - entry_value
        net_pnl = gross_pnl - fees
        pnl_pct = net_pnl / entry_value
        
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
        # Calculate quantity
        quantity = stake / price
        
        # Apply entry fee (Binance futures taker fee)
        fee = stake * 0.0004  # 0.04% taker fee
        
        # Create trade
        trade = Trade(
            symbol=symbol,
            entry_time=time,
            entry_price=price,
            entry_signal=signal,
            quantity=quantity,
            fees=fee
        )
        
        # Update portfolio
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
        
        # Group trades by pair
        for trade in self.portfolio.closed_trades:
            pair = f"{trade.symbol.replace('USDT', '/USDT:USDT')}"
            if pair not in pair_results:
                pair_results[pair] = {
                    'trades': 0,
                    'total_pnl': 0.0,
                    'wins': 0,
                    'losses': 0
                }
            
            pair_results[pair]['trades'] += 1
            pair_results[pair]['total_pnl'] += trade.pnl
            if trade.is_winner:
                pair_results[pair]['wins'] += 1
            else:
                pair_results[pair]['losses'] += 1
        
        # Convert to Freqtrade format
        results_per_pair = []
        for pair, stats in pair_results.items():
            profit_mean = stats['total_pnl'] / stats['trades'] if stats['trades'] > 0 else 0
            results_per_pair.append({
                "key": pair,
                "trades": stats['trades'],
                "profit_mean": profit_mean / 800,  # Normalize to percentage
                "profit_sum": stats['total_pnl'],
                "profit_total": stats['total_pnl'] / 10000,  # Percentage of initial balance
                "wins": stats['wins'],
                "losses": stats['losses']
            })
        
        return results_per_pair
    
    def export_freqtrade_format(self, results, start_date, end_date):
        """Export multi-pair backtest results in Freqtrade standard format for FreqUI"""
        import json
        from pathlib import Path
        import time as time_module
        
        # Create backtest results directory
        results_dir = Path("user_data/backtest_results")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert trades to Freqtrade format
        freqtrade_trades = []
        for trade in self.portfolio.closed_trades:
            freqtrade_trade = {
                "pair": f"{trade.symbol.replace('USDT', '/USDT:USDT')}",  # Convert to futures format
                "stake_amount": trade.entry_price * trade.quantity,
                "amount": trade.quantity,
                "open_date": trade.entry_time.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "close_date": trade.exit_time.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "open_rate": trade.entry_price,
                "close_rate": trade.exit_price,
                "fee_open": 0.0004,  # 0.04% taker fee
                "fee_close": 0.0004,
                "trade_duration": trade.duration_minutes,
                "profit_ratio": trade.pnl_pct,
                "profit_abs": trade.pnl,
                "exit_reason": trade.exit_reason,
                "initial_stop_loss_abs": trade.entry_price * 0.96,  # 4% stop loss
                "initial_stop_loss_ratio": -0.04,
                "stop_loss_abs": trade.entry_price * 0.96,
                "stop_loss_ratio": -0.04,
                "min_rate": min(trade.entry_price, trade.exit_price),
                "max_rate": max(trade.entry_price, trade.exit_price),
                "is_open": False,
                "buy_tag": trade.entry_signal,
                "enter_tag": trade.entry_signal,
            }
            freqtrade_trades.append(freqtrade_trade)
        
        # Create Freqtrade backtest result structure
        backtest_result = {
            "strategy": {
                "Try1BullRiderStrategy": {
                    "trades": freqtrade_trades,
                    "results_per_pair": self.generate_results_per_pair(results),
                    "total_trades": len(freqtrade_trades),
                    "profit_total": results['backtest_summary']['total_return_pct'] / 100,
                    "profit_total_abs": results['backtest_summary']['total_pnl'],
                    "backtest_start": start_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_end": end_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_days": (end_date - start_date).days,
                    "trades_per_day": len(freqtrade_trades) / max((end_date - start_date).days, 1),
                    "starting_balance": results['backtest_summary']['initial_balance'],
                    "final_balance": results['backtest_summary']['final_balance'],
                    "max_open_trades": 15,
                    "timeframe": "5m",
                    "timerange": f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}",
                    "strategy_name": "Try1BullRiderStrategy",
                    "stoploss": -0.04,
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
                    "max_drawdown_abs": results['backtest_summary']['max_drawdown_usd'] if 'max_drawdown_usd' in results['backtest_summary'] else 0,
                }
            }
        }
        
        # Save the result
        timestamp = int(time_module.time())
        filename = f"backtest-result-try1-{timestamp}.json"
        filepath = results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(backtest_result, f, indent=2, default=str)
        
        logger.info(f"✅ Try1BullRider backtest results exported to {filepath}")
        logger.info(f"📊 View in FreqUI: http://127.0.0.1:8080")
        
        return filepath

def detect_available_date_range():
    """Detect the full available date range from tick data files across all pairs"""
    all_dates = set()
    pairs_with_data = []
    
    # Check all pairs for available data
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
    
    # Detect available date range across all pairs
    available_start, available_end, pairs_with_data = detect_available_date_range()
    
    parser = argparse.ArgumentParser(description="Try1BullRider Multi-Pair Realistic Backtesting - Works Like Paper Trading")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date (YYYY-MM-DD). Default: use all available data")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (YYYY-MM-DD). Default: use all available data")
    parser.add_argument("--recent", action="store_true",
                        help="Test recent 3 months instead of full dataset")
    
    args = parser.parse_args()
    
    # Determine date range
    if args.start and args.end:
        # User specified dates
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    elif args.recent:
        # Recent 3 months
        if available_end:
            end_date = available_end
            start_date = end_date - timedelta(days=90)  # ~3 months
        else:
            print("❌ No tick data found!")
            return
    elif available_start and available_end:
        # Full available range
        start_date = available_start
        end_date = available_end
        print(f"🔍 Auto-detected date range: {start_date} to {end_date}")
        print(f"📊 Total available: {(end_date - start_date).days + 1} days (~{((end_date - start_date).days + 1) / 365.25:.1f} years)")
        print(f"📈 Pairs with data: {', '.join(pairs_with_data[:5])}{'...' if len(pairs_with_data) > 5 else ''} ({len(pairs_with_data)} total)")
    else:
        print("❌ No tick data found!")
        print("Check that user_data/tick_data/ contains pair directories with .feather files")
        return
    
    print("=" * 80)
    print("TRY1BULLRIDER MULTI-PAIR REALISTIC BACKTESTING - Pure Strategy Logic")
    print("=" * 80)
    print(f"Date Range:       {start_date} to {end_date}")
    days_total = (end_date - start_date).days + 1
    print(f"Testing Period:   {days_total} days ({days_total / 365.25:.1f} years)")
    print(f"Strategy:         Try1BullRiderStrategy (EXACT implementation)")
    print(f"Trading Pairs:    {len(pairs_with_data)} pairs available")
    print(f"Initial Balance:  $2,000 (realistic starting balance)")
    print(f"Max Open Trades:  15 total (max 2 per pair)")
    print(f"Position Size:    ~8% per trade (~$160 per position)")
    print(f"Weekend Filter:   DISABLED (trade 24/7)")
    print(f"Extra Checks:     NONE (pure strategy logic)")
    print(f"Portfolio:        Diversified across multiple crypto pairs")
    
    # Estimate time
    if days_total > 365:
        print("⚠️  WARNING: Testing multiple years may take 45+ minutes")
    elif days_total > 90:
        print(f"⏱️  Estimated time: ~{days_total / 20:.0f}-{days_total / 10:.0f} minutes")
    
    print("=" * 80)
    print()
    
    backtester = Try1RealisticBacktester()
    
    try:
        results = backtester.run_realistic_backtest(start_date, end_date)
        
        # Display results
        summary = results['backtest_summary']
        trade_analysis = results['trade_analysis']
        
        print("\\n🎯 TRY1BULLRIDER REALISTIC BACKTEST RESULTS")
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
            if 'profit_factor' in trade_analysis:
                print(f"Profit Factor:    {trade_analysis['profit_factor']:.2f}")
        
        print("\\n📊 PORTFOLIO BREAKDOWN:")
        # Show per-pair performance
        pair_results = {}
        for trade in backtester.portfolio.closed_trades:
            pair = trade.symbol
            if pair not in pair_results:
                pair_results[pair] = {'trades': 0, 'pnl': 0.0, 'wins': 0}
            pair_results[pair]['trades'] += 1
            pair_results[pair]['pnl'] += trade.pnl
            if trade.is_winner:
                pair_results[pair]['wins'] += 1
        
        # Show top 5 performing pairs
        top_pairs = sorted(pair_results.items(), key=lambda x: x[1]['pnl'], reverse=True)[:5]
        for pair, stats in top_pairs:
            win_rate = (stats['wins'] / stats['trades']) * 100 if stats['trades'] > 0 else 0
            print(f"  {pair:<10} | {stats['trades']} trades | ${stats['pnl']:+.2f} | {win_rate:.0f}% win rate")
        
        print("\\n📊 COMPARISON WITH YOUR LIVE PERFORMANCE:")
        print(f"Your Live Stats:   +12% in 8 days, 87.3% win rate, diversified portfolio")
        if summary['total_trades'] > 0:
            avg_pct = (trade_analysis['avg_trade_pnl'] / 800) * 100  # Estimate based on ~$800 stakes
            trades_per_day = summary['total_trades'] / days_total
            print(f"Backtest Stats:    {summary['total_trades']} trades across {len(pair_results)} pairs")
            print(f"Win Rate:          {summary['win_rate_pct']:.1f}%")
            print(f"Avg Trade:         {avg_pct:+.2f}%")
            print(f"Trade Frequency:   {trades_per_day:.2f} trades/day")
            print(f"Portfolio Pairs:   {len(pair_results)} of {len(pairs_with_data)} available pairs traded")
        
        print("\\n✅ Try1BullRider multi-pair realistic backtesting complete!")
        print("📈 This should closely match your profitable diversified live trading")
        print("🌍 Multi-pair diversification like your actual live setup")
        print("🔥 NO weekend filters, NO extra checks - pure strategy performance")
        
    except KeyboardInterrupt:
        print("\\n⚠️  Backtest interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()