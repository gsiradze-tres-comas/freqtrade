#!/usr/bin/env python3
"""
Run backtest for all symbols using tick data
Single command to test BTC, ETH, DOGE, ADA
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, timedelta
import gc

# Configuration
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'DOGEUSDT', 'ADAUSDT']
TICK_DATA_DIR = Path("user_data/tick_data")
START_DATE = date(2024, 8, 11)  # Full year as requested
END_DATE = date(2025, 8, 10)

def backtest_symbol(symbol):
    """Backtest one symbol with tick data"""
    print(f"Testing {symbol}...")
    
    symbol_dir = TICK_DATA_DIR / symbol
    if not symbol_dir.exists():
        print(f"  ❌ No data for {symbol}")
        return
    
    trades = 0
    profit = 0
    balance = 10000
    position = None
    
    current_date = START_DATE
    days = 0
    
    while current_date <= END_DATE:
        tick_file = symbol_dir / f"{symbol}-trades-{current_date.strftime('%Y-%m-%d')}.feather"
        
        if tick_file.exists():
            # Load tick data
            tick_df = pd.read_feather(tick_file)
            tick_df['datetime'] = pd.to_datetime(tick_df['datetime'])
            tick_df = tick_df.set_index('datetime')
            
            # Convert to hourly candles
            hourly = tick_df['price'].resample('1h').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last'
            }).dropna()
            
            if len(hourly) > 10:
                hourly['sma'] = hourly['close'].rolling(10).mean()
                
                for i in range(10, len(hourly)):
                    price = hourly['close'].iloc[i]
                    sma = hourly['sma'].iloc[i]
                    
                    # Simple strategy: buy above SMA, sell below
                    if position is None and price > sma * 1.01:
                        position = {'entry': price, 'size': balance * 0.08}
                    elif position and (price < sma * 0.99 or price < position['entry'] * 0.96 or price > position['entry'] * 1.04):
                        pnl = (price - position['entry']) / position['entry']
                        profit += position['size'] * pnl
                        balance += position['size'] * pnl
                        trades += 1
                        position = None
            
            days += 1
            del tick_df
            gc.collect()
        
        current_date += timedelta(days=1)
    
    print(f"  ✅ {symbol}: {trades} trades, ${profit:.2f} profit, Final: ${balance:.2f}")
    return {'symbol': symbol, 'trades': trades, 'profit': profit, 'balance': balance}

def main():
    print("=" * 60)
    print("BACKTESTING ALL SYMBOLS WITH TICK DATA")
    print("=" * 60)
    print(f"Period: {START_DATE} to {END_DATE}")
    print(f"Symbols: {', '.join([s[:3] for s in SYMBOLS])}")
    print("=" * 60)
    print()
    
    results = []
    for symbol in SYMBOLS:
        result = backtest_symbol(symbol)
        if result:
            results.append(result)
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_profit = sum(r['profit'] for r in results)
    total_trades = sum(r['trades'] for r in results)
    
    print(f"Total Trades: {total_trades}")
    print(f"Total Profit: ${total_profit:.2f}")
    print(f"Average per Symbol: ${total_profit/len(results):.2f}")
    
    print()
    print("✅ Done!")

if __name__ == "__main__":
    main()