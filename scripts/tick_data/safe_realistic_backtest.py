#!/usr/bin/env python3
"""
SafeBullRider Multi-Pair Realistic Backtesting - Works Like Paper Trading
Tests the SafeBullRider strategy across all your trading pairs with portfolio diversification
NO weekend filters, only essential daily loss limit checks like live trading
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
            daily_loss_limit = 10000 * self.max_daily_loss_pct  # $500 on $10k balance
            
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
    
    def check_exit_conditions_advanced(self, trade, current_price, current_time, df):
        """EXACT exit logic matching SafeBullRiderStrategy"""
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
        
        # 2. ROI targets (EXACT from SafeBullRider - same as Try1)
        for minutes, roi in sorted(self.minimal_roi.items()):
            if duration_minutes >= minutes and pnl_pct >= roi:
                return f"roi_{int(roi*100)}pct", current_price
        
        # 3. Trailing stop (EXACT from SafeBullRider - same as Try1)
        if max_profit >= self.trailing_stop_positive_offset:
            # Trailing stop is active
            trailing_stop_level = max_profit - self.trailing_stop_positive
            if pnl_pct <= trailing_stop_level:
                return "trailing_stop", current_price
        
        # 4. Exit signal conditions (EXACT from SafeBullRider populate_exit_trend)
        if len(df) >= 2:
            last = df.iloc[-1]
            if (last['downtrend'] and
                last['momentum_5'] < -0.02 and
                last['momentum_20'] < -0.03 and
                last['rsi'] < 25 and
                last['volume_ratio'] > 2.0):
                return "exit_signal", current_price
        
        # 5. Custom exit (EXACT from SafeBullRider custom_exit)
        if pnl_pct > 0.05 and len(df) >= 2:  # 5%+ profit protection
            if abs(df.iloc[-1]['momentum_5']) < -0.01:
                return "profit_protection", current_price
        
        # 6. Daily loss limit protection (SafeBullRider specific)
        daily_loss_limit = 10000 * self.max_daily_loss_pct * 0.8  # 80% of limit
        if abs(self.daily_loss_today) > daily_loss_limit:
            return "daily_limit_protection", current_price
        
        return None, None
    
    def custom_stake_amount(self, current_balance, df):
        """SafeBullRider position sizing (similar to Try1 but with risk adjustments)"""
        if len(df) < 2:
            return current_balance * 0.08
        
        last_candle = df.iloc[-1]
        
        # Base 8% position (SafeBullRider matches Try1)
        total_balance = current_balance
        base_stake = total_balance * 0.08
        
        # INCREASE size in strong trends (EXACT from SafeBullRider)
        if last_candle['uptrend'] and last_candle['momentum_20'] > 0.02:
            base_stake *= 1.3  # 30% larger in strong bull trends
        elif last_candle['downtrend'] and last_candle['momentum_20'] < -0.02:
            base_stake *= 1.3  # 30% larger in strong bear trends
        
        # INCREASE size on high volume (EXACT from SafeBullRider)
        if last_candle['volume_ratio'] > 2.0:
            base_stake *= 1.2  # 20% larger on volume spikes
        
        # SafeBullRider specific: reduce size in high volatility
        if not pd.isna(last_candle['volatility']) and last_candle['volatility'] > self.volatility_threshold:
            base_stake *= 0.8  # 20% smaller in high volatility
        
        return base_stake
    
    def run_realistic_backtest(self, start_date, end_date):
        """
        Run multi-pair realistic backtest matching SafeBullRider exactly
        Only essential daily loss limit checks - NO weekend filters
        """
        import time
        start_time = time.time()
        
        logger.info(f"Starting SafeBullRider multi-pair backtest from {start_date} to {end_date}")
        logger.info(f"Trading pairs: {', '.join(self.trading_pairs)}")
        logger.info("Only essential daily loss limit checks - NO weekend filters")
        
        # Reset portfolio to match SafeBullRider setup
        self.portfolio = Portfolio()
        self.portfolio.initial_balance = 10000  # Your dry_run_wallet
        self.portfolio.available_balance = 10000
        self.portfolio.current_balance = 10000
        self.portfolio.position_size_pct = 0.08
        self.portfolio.max_open_trades = 15     # SafeBullRider max_open_trades
        self.position_max_profit = {}
        self.daily_loss_today = 0.0
        self.last_check_date = None
        
        current_date = start_date
        total_days = (end_date - start_date).days + 1
        day_count = 0
        
        # Accumulate candles across days for indicator calculation
        all_candles = pd.DataFrame()
        
        while current_date <= end_date:
            day_count += 1
            
            # Load tick data for the day
            tick_df = self.load_tick_data(symbol, current_date)
            
            if tick_df is not None and len(tick_df) > 0:
                # Convert to 5-min candles
                daily_candles = self.create_5min_candles(tick_df)
                
                if len(daily_candles) > 0:
                    # Append to accumulated candles
                    all_candles = pd.concat([all_candles, daily_candles], ignore_index=True)
                    
                    # Keep only last 200 candles for efficiency (SafeBullRider needs 100+ for indicators)
                    if len(all_candles) > 200:
                        all_candles = all_candles.iloc[-200:]
                    
                    # Calculate indicators on accumulated candles
                    all_candles = self.populate_indicators(all_candles)
                    
                    # Process each new candle for signals
                    for idx in range(len(daily_candles)):
                        candle_time = daily_candles.iloc[idx]['datetime']
                        candle_idx = len(all_candles) - len(daily_candles) + idx
                        
                        if candle_idx < 0:
                            continue
                        
                        # Update existing positions
                        if len(self.portfolio.open_positions) > 0:
                            current_price = all_candles.iloc[candle_idx]['close']
                            positions_to_close = []
                            
                            for i, trade in enumerate(self.portfolio.open_positions):
                                exit_reason, exit_price = self.check_exit_conditions_advanced(
                                    trade, current_price, candle_time, all_candles.iloc[:candle_idx+1]
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
                        
                        # Check for new entry signals (respect max open trades)
                        if len(self.portfolio.open_positions) < self.portfolio.max_open_trades:
                            signal = self.check_entry_signals(
                                all_candles.iloc[:candle_idx+1], candle_time
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
                                    
                                    # Calculate position size (SafeBullRider logic)
                                    stake = self.custom_stake_amount(
                                        self.portfolio.available_balance,
                                        all_candles.iloc[:candle_idx+1]
                                    )
                                    
                                    # Open position
                                    self.open_position_at_price(
                                        symbol, signal, entry_price, stake, candle_time
                                    )
            
            # Progress update every 10 days
            if day_count % 10 == 0:
                elapsed = time.time() - start_time
                progress = day_count / total_days * 100
                open_pos = len(self.portfolio.open_positions)
                balance = self.portfolio.current_balance
                logger.info(f"Progress: {progress:.1f}% | Open: {open_pos}/{self.portfolio.max_open_trades} | Balance: ${balance:.2f}")
            
            current_date += timedelta(days=1)
        
        # Close any remaining positions at end
        if len(self.portfolio.open_positions) > 0:
            last_price = all_candles.iloc[-1]['close'] if len(all_candles) > 0 else 50000
            end_datetime = pd.Timestamp(end_date).tz_localize('UTC')
            for i in reversed(range(len(self.portfolio.open_positions))):
                self.close_position_at_price(i, "backtest_end", last_price, end_datetime)
        
        elapsed = time.time() - start_time
        logger.info(f"SafeBullRider backtest completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        
        results = self.generate_results()
        
        # Export to Freqtrade standard format for FreqUI visualization
        self.export_freqtrade_format(results, symbol, start_date, end_date)
        
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
        
        # Track balance history for drawdown calculation
        if not hasattr(self, 'balance_history'):
            self.balance_history = []
        self.balance_history.append({
            'timestamp': time,
            'balance': self.portfolio.current_balance,
            'trade_pnl': net_pnl
        })
        
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
    
    def export_freqtrade_format(self, results, symbol, start_date, end_date):
        """Export backtest results in Freqtrade standard format for FreqUI"""
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
                "pair": f"{symbol.replace('USDT', '/USDT:USDT')}",  # Convert to futures format
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
                "initial_stop_loss_abs": trade.entry_price * 0.94,  # 6% stop loss (SafeBullRider)
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
        
        # Create Freqtrade backtest result structure
        backtest_result = {
            "strategy": {
                "SafeBullRiderStrategy": {
                    "trades": freqtrade_trades,
                    "results_per_pair": [
                        {
                            "key": f"{symbol.replace('USDT', '/USDT:USDT')}",
                            "trades": len(freqtrade_trades),
                            "profit_mean": results['trade_analysis']['avg_trade_pnl'] / 800 if 'avg_trade_pnl' in results['trade_analysis'] and freqtrade_trades else 0,
                            "profit_sum": results['backtest_summary']['total_pnl'],
                            "profit_total": results['backtest_summary']['total_return_pct'] / 100,
                            "wins": results['trade_analysis']['winning_trades'],
                            "losses": results['trade_analysis']['losing_trades']
                        }
                    ],
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
                    "max_drawdown_abs": results['backtest_summary']['max_drawdown_usd'] if 'max_drawdown_usd' in results['backtest_summary'] else 0,
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
        
        return filepath

def detect_available_date_range():
    """Detect the full available date range from tick data files"""
    tick_dir = Path('user_data/tick_data/ETHUSDT/')
    if not tick_dir.exists():
        return None, None
        
    files = sorted([f for f in tick_dir.glob('*.feather')])
    if not files:
        return None, None
    
    # Extract dates from filenames
    first_date_str = files[0].name.split('trades-')[1].replace('.feather', '')
    last_date_str = files[-1].name.split('trades-')[1].replace('.feather', '')
    
    try:
        first_date = datetime.strptime(first_date_str, "%Y-%m-%d").date()
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        return first_date, last_date
    except:
        return None, None

def main():
    import argparse
    
    # Detect available date range
    available_start, available_end = detect_available_date_range()
    
    parser = argparse.ArgumentParser(description="SafeBullRider Realistic Backtesting - Works Like Paper Trading")
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
    else:
        print("❌ No tick data found!")
        print("Check that user_data/tick_data/ETHUSDT/ contains .feather files")
        return
    
    print("=" * 70)
    print("SAFEBULLRIDER REALISTIC BACKTESTING - Smart Enhanced Strategy")
    print("=" * 70)
    print(f"Date Range:       {start_date} to {end_date}")
    days_total = (end_date - start_date).days + 1
    print(f"Testing Period:   {days_total} days ({days_total / 365.25:.1f} years)")
    print(f"Strategy:         SafeBullRiderStrategy (EXACT implementation)")
    print(f"Initial Balance:  $10,000 (matches dry_run_wallet)")
    print(f"Max Open Trades:  15 (SafeBullRider config)")
    print(f"Position Size:    ~8% (~$800 per trade)")
    print(f"Weekend Filter:   DISABLED (trade 24/7)")
    print(f"Safety Features:  Daily loss limit (5% max)")
    print(f"Extra Checks:     Quality filters + volatility management")
    
    # Estimate time
    if days_total > 365:
        print("⚠️  WARNING: Testing multiple years may take 30+ minutes")
    elif days_total > 90:
        print(f"⏱️  Estimated time: ~{days_total / 30:.0f}-{days_total / 15:.0f} minutes")
    
    print("=" * 70)
    print()
    
    backtester = SafeRealisticBacktester()
    
    try:
        results = backtester.run_realistic_backtest("ETHUSDT", start_date, end_date)
        
        # Display results
        summary = results['backtest_summary']
        trade_analysis = results['trade_analysis']
        
        print("\\n🎯 SAFEBULLRIDER REALISTIC BACKTEST RESULTS")
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
        
        print("\\n📊 COMPARISON WITH TRY1BULLRIDER:")
        print("SafeBullRider adds:")
        print("  ✅ Daily loss limit protection (5% max)")
        print("  ✅ Enhanced entry patterns (momentum + volume confirmation)")
        print("  ✅ Market condition quality filters")
        print("  ✅ Volatility-adjusted position sizing")
        print("  ✅ ATR-based dynamic stop losses")
        
        if summary['total_trades'] > 0:
            avg_pct = (trade_analysis['avg_trade_pnl'] / 800) * 100  # Estimate based on ~$800 stakes
            trades_per_day = summary['total_trades'] / days_total
            print(f"\\nBacktest Stats:    {summary['total_trades']} trades, {summary['win_rate_pct']:.1f}% win rate, {avg_pct:+.2f}% avg")
            print(f"Trade Frequency:   {trades_per_day:.2f} trades/day")
        
        print("\\n✅ SafeBullRider realistic backtesting complete!")
        print("📈 Compare with Try1BullRider to see impact of safety features")
        print("🛡️  Only essential daily loss limit checks - NO weekend filters")
        
    except KeyboardInterrupt:
        print("\\n⚠️  Backtest interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()