#!/usr/bin/env python3
"""
Memory-Efficient Streaming Tick Backtesting
Processes data day-by-day without loading everything in memory
DEFAULT: Tests ALL coins for FULL YEAR
"""

import sys
import os
sys.path.append('/Users/gsiradze/Documents/projects/tres-comas/freqtrade')
sys.path.append('/Users/gsiradze/Documents/projects/tres-comas/freqtrade/user_data/strategies')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from pathlib import Path
import argparse
import time
from collections import deque

# Import the actual strategy class
from SafeBullRiderStrategy import SafeBullRiderStrategy
from freqtrade.data.dataprovider import DataProvider
from freqtrade.exchange import Exchange
from freqtrade.configuration import Configuration
from freqtrade.resolvers import ExchangeResolver

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StreamingTickBacktester:
    """Memory-efficient streaming tick backtester - processes data day by day"""
    
    def __init__(self, config_path: str):
        """Initialize with Freqtrade config"""
        self.config = Configuration.from_files([config_path])
        
        # Initialize exchange and data provider (needed for strategy)
        self.exchange = ExchangeResolver.load_exchange(self.config)
        self.dataprovider = DataProvider(self.config, self.exchange)
        
        # Initialize the ACTUAL strategy class
        self.strategy = SafeBullRiderStrategy(self.config)
        self.strategy.dp = self.dataprovider
        
        logger.info("✅ Initialized streaming tick backtester - MEMORY EFFICIENT")
    
    def detect_available_symbols(self) -> list:
        """Auto-detect available trading symbols in tick data"""
        base_tick_path = Path('/Users/gsiradze/Documents/projects/tres-comas/tick_data')
        
        if not base_tick_path.exists():
            base_tick_path = Path('user_data/tick_data')
        
        if not base_tick_path.exists():
            return []
        
        symbols = []
        for symbol_dir in base_tick_path.iterdir():
            if symbol_dir.is_dir() and list(symbol_dir.glob('*-trades-*.feather')):
                symbols.append(symbol_dir.name)
        
        return sorted(symbols)
    
    def detect_available_date_range(self, symbol: str = 'ETHUSDT') -> tuple:
        """Auto-detect available tick data date range for a symbol"""
        tick_data_path = Path(f'/Users/gsiradze/Documents/projects/tres-comas/tick_data/{symbol}')
        
        if not tick_data_path.exists():
            tick_data_path = Path(f'user_data/tick_data/{symbol}')
        
        if not tick_data_path.exists():
            return None, None
        
        # Get all feather files and extract dates
        files = list(tick_data_path.glob(f'{symbol}-trades-*.feather'))
        if not files:
            return None, None
        
        dates = []
        for file in files:
            try:
                date_str = file.stem.split('-trades-')[1]
                dates.append(pd.to_datetime(date_str).date())
            except:
                continue
        
        if not dates:
            return None, None
        
        dates.sort()
        return dates[0], dates[-1]
    
    def stream_daily_candles(self, symbol: str, start_date: str, end_date: str):
        """Generator that yields 5-minute candles day by day (memory efficient)"""
        tick_data_path = Path(f'/Users/gsiradze/Documents/projects/tres-comas/tick_data/{symbol}')
        
        if not tick_data_path.exists():
            tick_data_path = Path(f'user_data/tick_data/{symbol}')
        
        if not tick_data_path.exists():
            raise FileNotFoundError(f"Tick data not found at {tick_data_path}")
        
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        current_date = start_dt
        days_processed = 0
        total_days = (end_dt - start_dt).days + 1
        total_ticks = 0
        
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            tick_file = tick_data_path / f"{symbol}-trades-{date_str}.feather"
            
            if tick_file.exists():
                try:
                    # Load only ONE day at a time
                    daily_ticks = pd.read_feather(tick_file)
                    daily_ticks['timestamp'] = pd.to_datetime(daily_ticks['datetime'])
                    
                    # Convert to 5-minute candles for this day only
                    daily_ticks = daily_ticks.set_index('timestamp')
                    ohlcv = daily_ticks['price'].resample('5min').ohlc()
                    ohlcv['volume'] = daily_ticks['qty'].resample('5min').sum()
                    ohlcv = ohlcv.dropna().reset_index()
                    ohlcv.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
                    
                    days_processed += 1
                    total_ticks += len(daily_ticks)
                    
                    # Progress every 30 days
                    if days_processed % 30 == 0:
                        progress = days_processed / total_days * 100
                        logger.info(f"📊 {symbol}: Day {days_processed}/{total_days} ({progress:.1f}%) - {total_ticks:,} ticks processed")
                    
                    # Yield the daily candles
                    yield ohlcv, len(daily_ticks)
                    
                    # Important: Delete variables to free memory immediately
                    del daily_ticks, ohlcv
                    
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {tick_file}: {e}")
            
            current_date += timedelta(days=1)
        
        logger.info(f"✅ {symbol}: Completed {days_processed} days, {total_ticks:,} total ticks")
    
    def run_streaming_backtest(self, symbol: str, start_date: str, end_date: str) -> dict:
        """Memory-efficient streaming backtest - processes day by day"""
        start_time = time.time()
        
        # Fresh state for each symbol
        balance = 10000.0
        trades = []
        ticks_processed = 0
        candles_processed = 0
        
        # Keep rolling history of candles for indicators (only keep what's needed)
        candle_history = deque(maxlen=200)  # Keep last 200 candles for indicators
        
        logger.info(f"🚀 Starting STREAMING backtest for {symbol}")
        
        try:
            # Process data day by day (streaming)
            for daily_candles, daily_tick_count in self.stream_daily_candles(symbol, start_date, end_date):
                ticks_processed += daily_tick_count
                
                # Add today's candles to rolling history
                for _, candle in daily_candles.iterrows():
                    candle_history.append(candle.to_dict())
                    candles_processed += 1
                
                # Only run strategy analysis if we have enough history
                if len(candle_history) >= 100:
                    # Convert rolling history to DataFrame
                    current_df = pd.DataFrame(list(candle_history))
                    
                    # Run strategy analysis on current state
                    analyzed_df = self.strategy.populate_indicators(current_df, {'pair': symbol})
                    analyzed_df = self.strategy.populate_entry_trend(analyzed_df, {'pair': symbol})
                    analyzed_df = self.strategy.populate_exit_trend(analyzed_df, {'pair': symbol})
                    
                    # Check only the last few candles for signals (today's data)
                    recent_candles = analyzed_df.tail(len(daily_candles))
                    entry_signals = recent_candles[recent_candles['enter_long'] == 1]
                    
                    # Process entry signals from today
                    for idx, signal in entry_signals.iterrows():
                        signal_time = signal['date']
                        
                        # Skip weekends and low liquidity hours
                        if signal_time.weekday() >= 5:
                            continue
                        if 2 <= signal_time.hour < 4:
                            continue
                        
                        entry_price = signal['close']
                        position_size = balance * 0.08
                        
                        # Find exit in future candles (look ahead in history)
                        future_candles = analyzed_df[analyzed_df.index > idx]
                        
                        for exit_idx, exit_candle in future_candles.iterrows():
                            exit_time = exit_candle['date']
                            exit_price = exit_candle['close']
                            
                            profit_pct = (exit_price - entry_price) / entry_price
                            trade_duration_minutes = (exit_time - signal_time).total_seconds() / 60
                            
                            should_exit = False
                            exit_reason = ''
                            
                            # Exit signal
                            if exit_candle.get('exit_long', 0) == 1:
                                should_exit = True
                                exit_reason = 'signal_exit'
                            
                            # Stop loss
                            elif profit_pct <= self.strategy.stoploss:
                                should_exit = True
                                exit_reason = 'stop_loss'
                            
                            # ROI check
                            else:
                                for duration_str, roi_target in self.strategy.minimal_roi.items():
                                    duration_minutes = int(duration_str) * 5
                                    if trade_duration_minutes >= duration_minutes and profit_pct >= roi_target:
                                        should_exit = True
                                        exit_reason = 'roi'
                                        break
                            
                            if should_exit:
                                profit_abs = position_size * profit_pct
                                
                                trade_record = {
                                    'pair': symbol,
                                    'entry_time': signal_time,
                                    'exit_time': exit_time,
                                    'entry_price': entry_price,
                                    'exit_price': exit_price,
                                    'size': position_size,
                                    'profit_pct': profit_pct,
                                    'profit_abs': profit_abs,
                                    'exit_reason': exit_reason,
                                    'duration': exit_time - signal_time
                                }
                                
                                trades.append(trade_record)
                                balance += profit_abs
                                break
        
        except Exception as e:
            logger.error(f"❌ Error during streaming backtest for {symbol}: {e}")
            return None
        
        runtime = time.time() - start_time
        
        # Calculate results
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        
        results = {
            'total_trades': len(trades),
            'winning_trades': len(trades_df[trades_df['profit_pct'] > 0]) if not trades_df.empty else 0,
            'losing_trades': len(trades_df[trades_df['profit_pct'] <= 0]) if not trades_df.empty else 0,
            'win_rate': (len(trades_df[trades_df['profit_pct'] > 0]) / len(trades_df) * 100) if not trades_df.empty else 0,
            'total_profit_pct': (balance - 10000) / 10000 * 100,
            'total_profit_abs': balance - 10000,
            'final_balance': balance,
            'trades': trades_df,
            'ticks_processed': ticks_processed,
            'candles_analyzed': candles_processed,
            'runtime_seconds': runtime
        }
        
        logger.info(f"🎯 {symbol} STREAMING COMPLETE! {results['total_trades']} trades, "
                   f"{results['win_rate']:.1f}% win rate, {results['total_profit_pct']:+.2f}% return "
                   f"({runtime:.1f}s, {ticks_processed/runtime:,.0f} ticks/sec)")
        
        return results

def main():
    parser = argparse.ArgumentParser(description='MEMORY-EFFICIENT Streaming Tick Backtesting')
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--recent', action='store_true', help='Use recent 3-month period')
    parser.add_argument('--full', action='store_true', help='Use full available data range')
    parser.add_argument('--single', help='Test only single symbol (e.g., ADAUSDT)')
    parser.add_argument('--symbols', nargs='+', help='Multiple trading pair symbols to test')
    parser.add_argument('--exclude', nargs='+', help='Symbols to exclude from testing')
    
    args = parser.parse_args()
    
    # Initialize backtester
    try:
        config_path = 'user_data/configs/config_safe_bull.json'
        backtester = StreamingTickBacktester(config_path)
        
        # Auto-detect available symbols
        available_symbols = backtester.detect_available_symbols()
        
        if not available_symbols:
            print("❌ No tick data found!")
            print("Make sure tick data is available in user_data/tick_data/")
            return 1
        
        print(f"📊 Available symbols: {', '.join(available_symbols)}")
        
        # Determine which symbols to test
        if args.single:
            symbols_to_test = [args.single]
            print(f"🎯 Testing single symbol: {args.single}")
        elif args.symbols:
            symbols_to_test = args.symbols
            print(f"🎯 Testing specified symbols: {', '.join(symbols_to_test)}")
        else:
            symbols_to_test = available_symbols
            # Exclude symbols if specified
            if args.exclude:
                symbols_to_test = [s for s in symbols_to_test if s not in args.exclude]
                print(f"🎯 Testing ALL symbols EXCEPT: {', '.join(args.exclude)}")
            else:
                print(f"🎯 Testing ALL available symbols: {', '.join(symbols_to_test)}")
        
        # Auto-detect date range
        primary_symbol = symbols_to_test[0] if symbols_to_test else available_symbols[0]
        data_start, data_end = backtester.detect_available_date_range(primary_symbol)
        
        if not data_start or not data_end:
            print(f"❌ No tick data found for {primary_symbol}!")
            return 1
        
        print(f"📊 Available tick data range: {data_start} to {data_end}")
        
        # Determine date range based on arguments
        if args.full:
            start_date = data_start.strftime('%Y-%m-%d')
            end_date = data_end.strftime('%Y-%m-%d')
            print(f"🎯 Using FULL data range: {start_date} to {end_date}")
        elif args.recent:
            end_date = data_end.strftime('%Y-%m-%d')
            start_date = (data_end - timedelta(days=90)).strftime('%Y-%m-%d')
            print(f"🎯 Using RECENT 3-month period: {start_date} to {end_date}")
        elif args.start and args.end:
            start_date = args.start
            end_date = args.end
            print(f"🎯 Using CUSTOM date range: {start_date} to {end_date}")
        else:
            # DEFAULT: 1 year period
            end_date = data_end.strftime('%Y-%m-%d')
            start_date = (data_end - timedelta(days=365)).strftime('%Y-%m-%d')
            print(f"🎯 Using DEFAULT 1-year period: {start_date} to {end_date}")
            print("💡 Use --recent for 3 months, --full for all data, --single SYMBOL for one coin")
        
    except Exception as e:
        print(f"❌ Failed to initialize backtester: {e}")
        return 1
    
    print("\n💧 MEMORY-EFFICIENT STREAMING TICK BACKTESTING")
    print("=" * 90)
    print("✅ DEFAULT: Tests ALL coins for FULL YEAR")
    print("✅ MEMORY EFFICIENT: Processes day-by-day (no memory overload)")
    print("✅ STREAMING: Never loads full datasets in memory")
    print("✅ FAST: Optimized algorithms with minimal memory footprint")
    print("=" * 90)
    print(f"📊 Symbols: {len(symbols_to_test)} coins")
    print(f"📅 Period: {start_date} to {end_date}")
    print("=" * 90)
    
    try:
        # Run streaming backtest for all symbols
        all_results = {}
        total_start_time = time.time()
        
        for i, symbol in enumerate(symbols_to_test, 1):
            print(f"\n{'='*90}")
            print(f"🌊 STREAMING SYMBOL {i}/{len(symbols_to_test)}: {symbol}")
            print(f"{'='*90}")
            
            # Check if symbol has data for the requested period
            symbol_start, symbol_end = backtester.detect_available_date_range(symbol)
            if not symbol_start or not symbol_end:
                print(f"⚠️ No data available for {symbol}, skipping...")
                continue
            
            print(f"📊 {symbol} data available: {symbol_start} to {symbol_end}")
            
            # Run streaming backtest
            results = backtester.run_streaming_backtest(symbol, start_date, end_date)
            
            if results:
                all_results[symbol] = results
            else:
                print(f"❌ Failed to complete backtest for {symbol}")
        
        total_runtime = time.time() - total_start_time
        
        # Display comprehensive summary
        print(f"\n{'='*90}")
        print("📊 STREAMING BACKTEST RESULTS")
        print(f"{'='*90}")
        
        if all_results:
            # Summary table
            print(f"{'Symbol':<12} {'Trades':<8} {'Win%':<8} {'Return%':<10} {'Final$':<10} {'Ticks':<12} {'Time(s)':<8}")
            print("-" * 88)
            
            total_trades = 0
            total_ticks = 0
            
            for symbol, results in all_results.items():
                total_trades += results['total_trades']
                total_ticks += results.get('ticks_processed', 0)
                
                ticks_str = f"{results.get('ticks_processed', 0)/1000000:.1f}M" if results.get('ticks_processed', 0) > 1000000 else f"{results.get('ticks_processed', 0):,}"
                balance_str = f"${results.get('final_balance', 10000):.0f}"
                
                print(f"{symbol:<12} {results['total_trades']:<8} "
                      f"{results['win_rate']:<7.1f}% "
                      f"{results['total_profit_pct']:<9.2f}% "
                      f"{balance_str:<10} "
                      f"{ticks_str:<12} "
                      f"{results.get('runtime_seconds', 0):<7.1f}")
            
            print("-" * 88)
            
            avg_return = sum(r['total_profit_pct'] for r in all_results.values()) / len(all_results)
            print(f"{'AVERAGE':<12} {total_trades:<8} {'':<8} {avg_return:<9.2f}% {'':<10} {total_ticks/1000000:.1f}M {total_runtime:<7.1f}")
            
            print(f"\n💧 STREAMING STATISTICS:")
            print(f"Memory Usage: LOW (day-by-day processing)")
            print(f"Total Symbols: {len(all_results)}")
            print(f"Total Ticks: {total_ticks:,}")
            print(f"Processing Speed: {total_ticks/total_runtime:,.0f} ticks/second")
            print(f"Total Time: {total_runtime/60:.1f} minutes")
            
            # Performance ranking
            if len(all_results) > 1:
                sorted_symbols = sorted(all_results.items(), key=lambda x: x[1]['total_profit_pct'], reverse=True)
                
                print(f"\n🏆 TOP PERFORMING SYMBOLS:")
                for i, (symbol, results) in enumerate(sorted_symbols[:3], 1):
                    print(f"  {i}. {symbol}: {results['total_profit_pct']:+.2f}% ({results['total_trades']} trades)")
        
        else:
            print("❌ No successful backtests completed!")
        
        print(f"\n✅ Memory-efficient streaming backtesting complete!")
        
    except Exception as e:
        logger.error(f"❌ Streaming backtesting failed: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())