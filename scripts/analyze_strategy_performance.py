#!/usr/bin/env python3
"""
Quick Strategy Performance Analyzer
Diagnose why ETHUSDT dominates and other coins underperform
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

# Import the actual strategy class
from SafeBullRiderStrategy import SafeBullRiderStrategy
from freqtrade.data.dataprovider import DataProvider
from freqtrade.exchange import Exchange
from freqtrade.configuration import Configuration
from freqtrade.resolvers import ExchangeResolver

logging.basicConfig(level=logging.WARNING)  # Reduce logging noise
logger = logging.getLogger(__name__)

def quick_strategy_analysis():
    """Quick analysis of strategy performance across coins"""
    
    # Initialize strategy
    config_path = 'user_data/configs/config_safe_bull.json'
    config = Configuration.from_files([config_path])
    exchange = ExchangeResolver.load_exchange(config)
    dataprovider = DataProvider(config, exchange)
    strategy = SafeBullRiderStrategy(config)
    strategy.dp = dataprovider
    
    # Test symbols
    symbols = ['ADAUSDT', 'BTCUSDT', 'DOGEUSDT', 'ETHUSDT', 'XRPUSDT']
    
    # Analysis period - recent 30 days
    end_date = datetime(2025, 8, 10)
    start_date = end_date - timedelta(days=30)
    
    print("🔍 STRATEGY PERFORMANCE ANALYSIS")
    print("=" * 60)
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print("=" * 60)
    
    results = {}
    
    for symbol in symbols:
        print(f"\n📊 Analyzing {symbol}...")
        
        # Load sample data for analysis
        tick_data_path = Path(f'/Users/gsiradze/Documents/projects/tres-comas/tick_data/{symbol}')
        if not tick_data_path.exists():
            tick_data_path = Path(f'user_data/tick_data/{symbol}')
        
        if not tick_data_path.exists():
            print(f"❌ No data for {symbol}")
            continue
        
        # Load just a few recent days for quick analysis
        sample_days = []
        current_date = end_date - timedelta(days=7)  # Last 7 days
        
        while current_date <= end_date and len(sample_days) < 3:  # Max 3 days
            date_str = current_date.strftime('%Y-%m-%d')
            tick_file = tick_data_path / f"{symbol}-trades-{date_str}.feather"
            
            if tick_file.exists():
                try:
                    daily_ticks = pd.read_feather(tick_file)
                    daily_ticks['timestamp'] = pd.to_datetime(daily_ticks['datetime'])
                    
                    # Convert to 5-minute candles
                    daily_ticks = daily_ticks.set_index('timestamp')
                    ohlcv = daily_ticks['price'].resample('5min').ohlc()
                    ohlcv['volume'] = daily_ticks['qty'].resample('5min').sum()
                    ohlcv = ohlcv.dropna().reset_index()
                    ohlcv.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
                    
                    sample_days.append(ohlcv)
                except Exception as e:
                    print(f"⚠️ Error loading {symbol} {date_str}: {e}")
            
            current_date += timedelta(days=1)
        
        if not sample_days:
            print(f"❌ No sample data for {symbol}")
            continue
        
        # Combine sample data
        sample_data = pd.concat(sample_days, ignore_index=True)
        
        if len(sample_data) < 100:
            print(f"⚠️ Insufficient data for {symbol} ({len(sample_data)} candles)")
            continue
        
        # Run strategy analysis
        try:
            analyzed_df = strategy.populate_indicators(sample_data, {'pair': symbol})
            analyzed_df = strategy.populate_entry_trend(analyzed_df, {'pair': symbol})
            analyzed_df = strategy.populate_exit_trend(analyzed_df, {'pair': symbol})
            
            # Count signals
            total_candles = len(analyzed_df)
            entry_signals = len(analyzed_df[analyzed_df['enter_long'] == 1])
            exit_signals = len(analyzed_df[analyzed_df['exit_long'] == 1])
            
            # Calculate signal frequency
            entry_freq = (entry_signals / total_candles) * 100 if total_candles > 0 else 0
            exit_freq = (exit_signals / total_candles) * 100 if total_candles > 0 else 0
            
            # Analyze last few rows for current conditions
            recent = analyzed_df.tail(10)
            avg_volatility = recent['volatility'].mean()
            avg_market_risk = recent['market_risk'].mean()
            avg_uptrend = recent['uptrend'].mean()
            avg_rsi = recent['rsi'].mean()
            
            results[symbol] = {
                'candles': total_candles,
                'entry_signals': entry_signals,
                'exit_signals': exit_signals,
                'entry_freq': entry_freq,
                'exit_freq': exit_freq,
                'avg_volatility': avg_volatility,
                'avg_market_risk': avg_market_risk,
                'avg_uptrend': avg_uptrend,
                'avg_rsi': avg_rsi
            }
            
            print(f"✅ {symbol}: {entry_signals} entry signals ({entry_freq:.2f}%) from {total_candles} candles")
            
        except Exception as e:
            print(f"❌ Strategy analysis failed for {symbol}: {e}")
            continue
    
    # Summary comparison
    print(f"\n{'='*60}")
    print("📊 STRATEGY SIGNAL COMPARISON")
    print(f"{'='*60}")
    print(f"{'Symbol':<10} {'Candles':<8} {'Entries':<8} {'Entry%':<8} {'Volatil':<8} {'Risk':<6} {'RSI':<6}")
    print("-" * 60)
    
    for symbol, data in results.items():
        print(f"{symbol:<10} {data['candles']:<8} {data['entry_signals']:<8} "
              f"{data['entry_freq']:<7.2f}% {data['avg_volatility']:<7.4f} "
              f"{data['avg_market_risk']:<5.3f} {data['avg_rsi']:<5.1f}")
    
    # Analysis insights
    print(f"\n🔍 KEY INSIGHTS:")
    
    # Find symbol with most signals
    if results:
        max_signals = max(results.items(), key=lambda x: x[1]['entry_signals'])
        min_signals = min(results.items(), key=lambda x: x[1]['entry_signals'])
        
        print(f"📈 Most signals: {max_signals[0]} ({max_signals[1]['entry_signals']} signals)")
        print(f"📉 Fewest signals: {min_signals[0]} ({min_signals[1]['entry_signals']} signals)")
        
        # Calculate signal ratio
        if min_signals[1]['entry_signals'] > 0:
            ratio = max_signals[1]['entry_signals'] / min_signals[1]['entry_signals']
            print(f"⚡ Signal ratio: {ratio:.1f}x difference")
        
        # Check volatility correlation
        eth_vol = results.get('ETHUSDT', {}).get('avg_volatility', 0)
        btc_vol = results.get('BTCUSDT', {}).get('avg_volatility', 0)
        print(f"🌊 Volatility - ETHUSDT: {eth_vol:.4f}, BTCUSDT: {btc_vol:.4f}")
        
        # Check uptrend correlation  
        eth_trend = results.get('ETHUSDT', {}).get('avg_uptrend', 0)
        btc_trend = results.get('BTCUSDT', {}).get('avg_uptrend', 0)
        print(f"📈 Uptrend - ETHUSDT: {eth_trend:.3f}, BTCUSDT: {btc_trend:.3f}")

if __name__ == '__main__':
    try:
        quick_strategy_analysis()
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()