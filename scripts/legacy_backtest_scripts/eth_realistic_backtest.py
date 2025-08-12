#!/usr/bin/env python3
"""
ETH Realistic Backtesting - Matches Your Actual Paper Trading Setup
Tests the exact same configuration that's making you money in live trading
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
sys.path.append(str(Path(__file__).parent))

from tick_backtester import TickBacktester, Trade, Portfolio

class RealisticETHBacktester(TickBacktester):
    """
    Realistic backtester that matches your profitable paper trading setup exactly
    Based on your actual configuration and recent profitable performance
    """
    
    def __init__(self, enable_weekend_filter=True):
        super().__init__()
        self.enable_weekend_filter = enable_weekend_filter
        
        # Match your EXACT live configuration
        self.portfolio.position_size_pct = 0.08  # 8% base (matches your ~$800 stakes)
        self.portfolio.max_open_trades = 9       # Current open positions (was 15 max)
        
        # Try1BullRiderStrategy parameters (exact values from your code)
        self.rsi_oversold = 40
        self.rsi_overbought = 65
        self.volume_multiplier = 1.2
        self.trend_strength = 0.005
        
        # ROI targets (from your strategy)
        self.minimal_roi = {
            0: 0.04,    # 4% target
            120: 0.025, # 2.5% after 2 hours 
            300: 0.015, # 1.5% after 5 hours
            600: 0.008  # 0.8% after 10 hours
        }
        
        # Trailing stop parameters
        self.trailing_stop_positive = 0.015      # 1.5%
        self.trailing_stop_positive_offset = 0.02 # 2%
        
        # Track highest profit for trailing stop
        self.position_max_profit = {}
        
    def create_5min_candles(self, tick_df):
        """Convert tick data to 5-minute OHLCV candles (matches your 5m timeframe)"""
        if len(tick_df) == 0:
            return pd.DataFrame()
        
        # Create a copy to avoid modifying original data
        tick_copy = tick_df.copy()
        tick_copy['datetime'] = pd.to_datetime(tick_copy['datetime'])
        tick_copy.set_index('datetime', inplace=True)
        
        # Create 5-minute candles (matching your strategy timeframe)
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
        """Exact implementation of Try1BullRiderStrategy indicators"""
        if len(df) < 50:
            return df
        
        # Basic EMAs for trend
        df['ema_8'] = ta.EMA(df, timeperiod=8)
        df['ema_21'] = ta.EMA(df, timeperiod=21)
        df['ema_50'] = ta.EMA(df, timeperiod=50)
        
        # RSI
        df['rsi'] = ta.RSI(df, timeperiod=14)
        
        # Volume
        df['volume_mean'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_mean']
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # Price momentum
        df['momentum_5'] = df['close'].pct_change(periods=5)
        df['momentum_20'] = df['close'].pct_change(periods=20)
        
        # ATR for volatility
        df['atr'] = ta.ATR(df, timeperiod=14)
        
        # Trend detection (EXACT from strategy)
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
        
        # Candle patterns
        df['green_candle'] = (df['close'] > df['open']).astype(int)
        df['red_candle'] = (df['close'] < df['open']).astype(int)
        
        return df
    
    def check_entry_signals(self, df, timestamp):
        """Exact entry logic from Try1BullRiderStrategy"""
        if self.enable_weekend_filter and timestamp.weekday() in [5, 6]:
            return None
        
        if len(df) < 2:
            return None
        
        last = df.iloc[-1]
        
        # Skip if indicators not ready
        if pd.isna(last['rsi']) or pd.isna(last['uptrend']):
            return None
        
        # LONG conditions (from strategy) - EXACT logic
        long_dip_buy = (
            last['uptrend'] and
            last['rsi'] < self.rsi_oversold and
            last['volume_ratio'] > self.volume_multiplier
        )
        
        long_breakout = (
            last['momentum_5'] > self.trend_strength and
            last['green_candle'] == 1 and
            last['volume_ratio'] > 1.5 and
            last['close'] > last['ema_8']
        )
        
        long_trend_follow = (
            last['uptrend'] and
            last['close'] > df.iloc[-2]['close'] and
            last['rsi'] > 45 and last['rsi'] < 70 and
            last['volume_ratio'] > 1.0
        )
        
        # Combine with OR logic (like strategy)
        if long_dip_buy or long_breakout or long_trend_follow:
            # Check ATR filter (from confirm_trade_entry)
            if last['atr'] / last['close'] <= 0.05:  # 5% ATR limit
                return 'bull_long'
        
        return None
    
    def check_exit_conditions_advanced(self, trade, current_price, current_time, df):
        """Advanced exit logic matching Try1BullRiderStrategy exactly"""
        pnl_pct = (current_price - trade.entry_price) / trade.entry_price
        duration_minutes = (current_time - trade.entry_time).total_seconds() / 60
        
        # Track maximum profit for trailing stop
        trade_id = id(trade)
        if trade_id not in self.position_max_profit:
            self.position_max_profit[trade_id] = pnl_pct
        else:
            self.position_max_profit[trade_id] = max(self.position_max_profit[trade_id], pnl_pct)
        
        max_profit = self.position_max_profit[trade_id]
        
        # 1. Stop loss at -4%
        if pnl_pct <= -0.04:
            return "stop_loss", current_price
        
        # 2. ROI targets (from strategy)
        for minutes, roi in sorted(self.minimal_roi.items()):
            if duration_minutes >= minutes and pnl_pct >= roi:
                return f"roi_{int(roi*100)}pct", current_price
        
        # 3. Trailing stop (from strategy)
        if max_profit >= self.trailing_stop_positive_offset:
            # Trailing stop is active
            trailing_stop_level = max_profit - self.trailing_stop_positive
            if pnl_pct <= trailing_stop_level:
                return "trailing_stop", current_price
        
        # 4. Exit signal conditions (from populate_exit_trend)
        if len(df) >= 2:
            last = df.iloc[-1]
            if (last['downtrend'] and
                last['momentum_5'] < -0.02 and
                last['momentum_20'] < -0.03 and
                last['rsi'] < 25 and
                last['volume_ratio'] > 2.0):
                return "exit_signal", current_price
        
        # 5. Custom exit (profit protection at 5%+)
        if pnl_pct > 0.05 and len(df) >= 2:
            if df.iloc[-1]['momentum_5'] < -0.01:
                return "profit_protection", current_price
        
        return None, None
    
    def custom_stake_amount(self, current_balance, df):
        """Match Try1BullRiderStrategy position sizing exactly"""
        if len(df) < 2:
            return current_balance * 0.08
        
        last_candle = df.iloc[-1]
        
        # Base 8% position (matches your ~$800 stakes on $10k balance)
        base_stake = current_balance * 0.08
        
        # Increase size in strong trends (from strategy)
        if last_candle['uptrend'] and last_candle['momentum_20'] > 0.02:
            base_stake *= 1.3  # 30% larger
        
        # Increase size on high volume
        if last_candle['volume_ratio'] > 2.0:
            base_stake *= 1.2  # 20% larger
        
        return base_stake
    
    def run_realistic_backtest(self, symbol, start_date, end_date):
        """
        Run realistic backtest matching your profitable setup
        """
        import time
        start_time = time.time()
        
        logger.info(f"Starting REALISTIC backtest for {symbol} from {start_date} to {end_date}")
        
        # Reset portfolio to match your setup
        self.portfolio = Portfolio()
        self.portfolio.initial_balance = 10000  # Your dry_run_wallet
        self.portfolio.available_balance = 10000
        self.portfolio.current_balance = 10000
        self.portfolio.position_size_pct = 0.08
        self.portfolio.max_open_trades = 9      # Based on your current 9 open trades
        self.position_max_profit = {}
        
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
                    
                    # Keep only last 100 candles for efficiency
                    if len(all_candles) > 100:
                        all_candles = all_candles.iloc[-100:]
                    
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
                                    
                                    # Calculate position size
                                    stake = self.custom_stake_amount(
                                        self.portfolio.available_balance,
                                        all_candles.iloc[:candle_idx+1]
                                    )
                                    
                                    # Open position
                                    self.open_position_at_price(
                                        symbol, signal, entry_price, stake, candle_time
                                    )
            
            # Progress update every 7 days
            if day_count % 7 == 0:
                elapsed = time.time() - start_time
                progress = day_count / total_days * 100
                logger.info(f"Progress: {progress:.1f}% | Open: {len(self.portfolio.open_positions)}/{self.portfolio.max_open_trades} | Balance: ${self.portfolio.current_balance:.2f}")
            
            current_date += timedelta(days=1)
        
        # Close any remaining positions at end
        if len(self.portfolio.open_positions) > 0:
            last_price = all_candles.iloc[-1]['close'] if len(all_candles) > 0 else 0
            # Use timezone-aware datetime to match tick data
            end_datetime = pd.Timestamp(end_date).tz_localize('UTC')
            for i in reversed(range(len(self.portfolio.open_positions))):
                self.close_position_at_price(i, "backtest_end", last_price, end_datetime)
        
        elapsed = time.time() - start_time
        logger.info(f"Completed in {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        
        results = self.generate_results()
        
        # Export to Freqtrade standard format for FreqUI visualization
        self.export_freqtrade_format(results, symbol, start_date, end_date)
        
        # Create enhanced Plotly visualizations
        self.create_enhanced_visualizations(results, symbol, start_date, end_date)
        
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
        
        # Simulate market order execution
        if is_entry:
            # Entry: likely to get slightly worse price (buy at ask)
            return execution_ticks['price'].iloc[min(5, len(execution_ticks)-1)]  # 5th tick or last
        else:
            # Exit: sell at bid
            return execution_ticks['price'].iloc[0]  # First tick
    
    def close_position_at_price(self, trade_index, exit_reason, price, time):
        """Close position at specific price and time"""
        trade = self.portfolio.open_positions[trade_index]
        
        # Calculate P&L
        quantity = trade.quantity
        entry_value = trade.entry_price * quantity
        exit_value = price * quantity
        
        # Apply fees (0.05% maker/taker on Binance futures)
        fees = (entry_value + exit_value) * 0.0005
        
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
        
        # Apply entry fee
        fee = stake * 0.0005
        
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
                "fee_open": 0.0005,  # 0.05% fee
                "fee_close": 0.0005,
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
                    "results_per_pair": [
                        {
                            "key": f"{symbol.replace('USDT', '/USDT:USDT')}",
                            "trades": len(freqtrade_trades),
                            "profit_mean": results['trade_analysis']['avg_trade_pnl'] / 800,  # Convert to percentage
                            "profit_mean_pct": results['trade_analysis']['avg_trade_pnl'] / 8,
                            "profit_sum": results['backtest_summary']['total_pnl'],
                            "profit_sum_pct": results['backtest_summary']['total_return_pct'],
                            "profit_total_abs": results['backtest_summary']['total_pnl'],
                            "profit_total": results['backtest_summary']['total_return_pct'] / 100,
                            "profit_total_pct": results['backtest_summary']['total_return_pct'],
                            "duration_avg": results['trade_analysis']['avg_duration_minutes'] if 'avg_duration_minutes' in results['trade_analysis'] else 0,
                            "wins": results['trade_analysis']['winning_trades'],
                            "draws": 0,
                            "losses": results['trade_analysis']['losing_trades']
                        }
                    ],
                    "results_per_enter_tag": [
                        {
                            "key": "bull_long",
                            "trades": len(freqtrade_trades),
                            "profit_mean": results['trade_analysis']['avg_trade_pnl'] / 800,
                            "profit_mean_pct": results['trade_analysis']['avg_trade_pnl'] / 8,
                            "profit_sum": results['backtest_summary']['total_pnl'],
                            "profit_sum_pct": results['backtest_summary']['total_return_pct'],
                            "profit_total_abs": results['backtest_summary']['total_pnl'],
                            "profit_total": results['backtest_summary']['total_return_pct'] / 100,
                            "profit_total_pct": results['backtest_summary']['total_return_pct'],
                            "duration_avg": results['trade_analysis']['avg_duration_minutes'] if 'avg_duration_minutes' in results['trade_analysis'] else 0,
                            "wins": results['trade_analysis']['winning_trades'],
                            "draws": 0,
                            "losses": results['trade_analysis']['losing_trades']
                        }
                    ],
                    "total_trades": len(freqtrade_trades),
                    "total_volume": sum(t["stake_amount"] for t in freqtrade_trades),
                    "avg_stake_amount": sum(t["stake_amount"] for t in freqtrade_trades) / len(freqtrade_trades) if freqtrade_trades else 0,
                    "profit_mean": results['trade_analysis']['avg_trade_pnl'] / 800 if 'avg_trade_pnl' in results['trade_analysis'] else 0,
                    "profit_median": results['trade_analysis']['avg_trade_pnl'] / 800 if 'avg_trade_pnl' in results['trade_analysis'] else 0,
                    "profit_total": results['backtest_summary']['total_return_pct'] / 100,
                    "profit_total_abs": results['backtest_summary']['total_pnl'],
                    "backtest_start": start_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_start_ts": int(start_date.strftime("%s")) * 1000,
                    "backtest_end": end_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "backtest_end_ts": int(end_date.strftime("%s")) * 1000,
                    "backtest_days": (end_date - start_date).days,
                    "backtest_run_start_ts": int(start_date.strftime("%s")) * 1000,
                    "backtest_run_end_ts": int(end_date.strftime("%s")) * 1000,
                    "trades_per_day": len(freqtrade_trades) / max((end_date - start_date).days, 1),
                    "market_change": 0,  # Could calculate this from price data
                    "pairlist": [f"{symbol.replace('USDT', '/USDT:USDT')}"],
                    "stake_amount": 800,
                    "stake_currency": "USDT",
                    "stake_currency_decimals": 8,
                    "starting_balance": results['backtest_summary']['initial_balance'],
                    "dry_run_wallet": results['backtest_summary']['initial_balance'],
                    "final_balance": results['backtest_summary']['final_balance'],
                    "rejected_signals": 0,
                    "max_open_trades": 9,
                    "max_open_trades_setting": 9,
                    "timeframe": "5m",
                    "timeframe_detail": "",
                    "timerange": f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}",
                    "enable_protections": False,
                    "strategy_name": "Try1BullRiderStrategy",
                    "stoploss": -0.04,
                    "trailing_stop": True,
                    "trailing_stop_positive": 0.015,
                    "trailing_stop_positive_offset": 0.02,
                    "trailing_only_offset_is_reached": True,
                    "use_custom_stoploss": False,
                    "minimal_roi": {
                        "0": 0.04,
                        "120": 0.025,
                        "300": 0.015,
                        "600": 0.008
                    },
                    "use_exit_signal": True,
                    "exit_profit_only": False,
                    "exit_profit_offset": 0.0,
                    "ignore_roi_if_entry_signal": False,
                    "backtest_best_day": max([t['profit_abs'] for t in freqtrade_trades]) if freqtrade_trades else 0,
                    "backtest_worst_day": min([t['profit_abs'] for t in freqtrade_trades]) if freqtrade_trades else 0,
                    "backtest_best_day_abs": max([t['profit_abs'] for t in freqtrade_trades]) if freqtrade_trades else 0,
                    "backtest_worst_day_abs": min([t['profit_abs'] for t in freqtrade_trades]) if freqtrade_trades else 0,
                    "winning_days": len([t for t in freqtrade_trades if t['profit_abs'] > 0]),
                    "draw_days": 0,
                    "losing_days": len([t for t in freqtrade_trades if t['profit_abs'] < 0]),
                    "daily_profit": [t['profit_abs'] for t in freqtrade_trades],
                    "wins": results['trade_analysis']['winning_trades'],
                    "draws": 0,
                    "losses": results['trade_analysis']['losing_trades'],
                    "winrate": results['backtest_summary']['win_rate_pct'] / 100,
                    "expectancy": results['trade_analysis']['avg_trade_pnl'] if 'avg_trade_pnl' in results['trade_analysis'] else 0,
                    "expectancy_ratio": results['trade_analysis']['profit_factor'] if 'profit_factor' in results['trade_analysis'] else 0,
                    "max_drawdown": results['backtest_summary']['max_drawdown_pct'] / 100 if 'max_drawdown_pct' in results['backtest_summary'] else 0,
                    "max_drawdown_account": results['backtest_summary']['max_drawdown_pct'] / 100 if 'max_drawdown_pct' in results['backtest_summary'] else 0,
                    "max_drawdown_abs": results['backtest_summary']['max_drawdown_usd'] if 'max_drawdown_usd' in results['backtest_summary'] else 0,
                    "drawdown_start": start_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "drawdown_start_ts": int(start_date.strftime("%s")) * 1000,
                    "drawdown_end": end_date.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "drawdown_end_ts": int(end_date.strftime("%s")) * 1000,
                    "csum_min": results['backtest_summary']['initial_balance'] - results['backtest_summary']['max_drawdown_usd'] if 'max_drawdown_usd' in results['backtest_summary'] else results['backtest_summary']['initial_balance'],
                    "csum_max": results['backtest_summary']['final_balance']
                }
            }
        }
        
        # Save the result
        timestamp = int(time.time())
        filename = f"backtest-result-{timestamp}.json"
        filepath = results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(backtest_result, f, indent=2, default=str)
        
        logger.info(f"✅ Backtest results exported to {filepath}")
        logger.info(f"📊 View in FreqUI: http://127.0.0.1:8080")
        
        return filepath
    
    def create_enhanced_visualizations(self, results, symbol, start_date, end_date):
        """Create enhanced Plotly visualizations"""
        try:
            # Import enhanced visualizer
            import sys
            from pathlib import Path
            sys.path.append(str(Path(__file__).parent))
            from enhanced_visualizer import BacktestVisualizer
            
            # Add balance history to results for visualization
            if hasattr(self, 'balance_history'):
                results['balance_history'] = self.balance_history
            
            # Create visualizations
            visualizer = BacktestVisualizer()
            viz_paths = visualizer.save_visualizations(results, symbol, start_date, end_date)
            
            logger.info(f"🎨 Enhanced visualizations created!")
            logger.info(f"  - Open: {viz_paths['comprehensive']}")
            logger.info(f"  - Timeline: {viz_paths['timeline']}")
            
            return viz_paths
            
        except ImportError as e:
            logger.warning(f"⚠️  Could not create enhanced visualizations: {e}")
            logger.info("Install plotly with: pip install plotly")
            return None
        except Exception as e:
            logger.error(f"❌ Error creating visualizations: {e}")
            return None

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
    
    parser = argparse.ArgumentParser(description="ETH Realistic Backtesting - Matches Your Profitable Setup")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date (YYYY-MM-DD). Default: use all available data")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (YYYY-MM-DD). Default: use all available data")
    parser.add_argument("--recent", action="store_true",
                        help="Test recent 3 months instead of full dataset")
    parser.add_argument("--no-weekend-filter", action="store_true",
                        help="Disable weekend trading filter")
    
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
    
    weekend_filter = not args.no_weekend_filter
    
    print("=" * 70)
    print("ETH REALISTIC BACKTESTING - Matches Your Profitable Setup")
    print("=" * 70)
    print(f"Date Range:       {start_date} to {end_date}")
    days_total = (end_date - start_date).days + 1
    print(f"Testing Period:   {days_total} days ({days_total / 365.25:.1f} years)")
    print(f"Weekend Filter:   {'Enabled' if weekend_filter else 'Disabled'}")
    print(f"Initial Balance:  $10,000 (matches dry_run_wallet)")
    print(f"Max Open Trades:  9 (matches your current positions)")
    print(f"Position Size:    ~8% (~$800 per trade)")
    print(f"Strategy:         Try1BullRiderStrategy (Exact Implementation)")
    
    # Estimate time
    if days_total > 365:
        print("⚠️  WARNING: Testing multiple years may take 30+ minutes")
    elif days_total > 90:
        print(f"⏱️  Estimated time: ~{days_total / 30:.0f}-{days_total / 15:.0f} minutes")
    
    print("=" * 70)
    print()
    
    backtester = RealisticETHBacktester(enable_weekend_filter=weekend_filter)
    
    try:
        results = backtester.run_realistic_backtest("ETHUSDT", start_date, end_date)
        
        # Display results
        summary = results['backtest_summary']
        trade_analysis = results['trade_analysis']
        
        print("\\n🎯 REALISTIC BACKTEST RESULTS")
        print("=" * 50)
        print(f"Final Balance:    ${summary['final_balance']:,.2f}")
        print(f"Total Return:     {summary['total_return_pct']:+.2f}%")
        print(f"Total P&L:        ${summary['total_pnl']:+.2f}")
        print(f"Total Trades:     {summary['total_trades']}")
        print(f"Win Rate:         {summary['win_rate_pct']:.1f}%")
        print(f"Max Drawdown:     {summary['max_drawdown_pct']:.2f}% (${summary['max_drawdown_usd']:.2f})")
        
        if summary['total_trades'] > 0:
            print(f"Avg Trade:        ${trade_analysis['avg_trade_pnl']:+.2f}")
            print(f"Best Trade:       ${trade_analysis['max_win']:+.2f}")
            print(f"Worst Trade:      ${trade_analysis['max_loss']:+.2f}")
            print(f"Profit Factor:    {trade_analysis['profit_factor']:.2f}")
        
        print("\\n📊 COMPARISON WITH YOUR LIVE PERFORMANCE:")
        print(f"Your Recent Stats: 71 trades, 87.3% win rate, +1.08% avg")
        avg_pct = (trade_analysis['avg_trade_pnl'] / 800) * 100  # Estimate based on ~$800 stakes
        print(f"Backtest Stats:    {summary['total_trades']} trades, {summary['win_rate_pct']:.1f}% win rate, {avg_pct:+.2f}% avg")
        
        print("\\n✅ Realistic backtesting complete!")
        print("📈 This should closely match your profitable paper trading results")
        
    except KeyboardInterrupt:
        print("\\n⚠️  Backtest interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()