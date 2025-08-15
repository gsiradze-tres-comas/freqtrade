#!/usr/bin/env python3
"""
Download POL/USDT tick data from Binance
POL is actively trading but missing tick data
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import time
import ccxt
from pathlib import Path

def download_pol_tick_data():
    """Download missing POL/USDT tick data"""
    
    # Setup paths
    base_path = Path("/Users/gsiradze/Documents/projects/tres-comas/freqtrade")
    tick_data_path = base_path / "user_data" / "tick_data" / "POLUSDT"
    
    # Create directory if it doesn't exist
    tick_data_path.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 POL tick data directory: {tick_data_path}")
    
    # Initialize exchange
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    # Symbol for futures
    symbol = 'POL/USDT:USDT'
    
    # Date range - last 30 days to match other coins
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"📅 Downloading POL/USDT tick data from {start_date.date()} to {end_date.date()}")
    print("=" * 60)
    
    current_date = start_date
    downloaded_count = 0
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        filename = f"POLUSDT-trades-{date_str}.feather"
        filepath = tick_data_path / filename
        
        # Skip if file already exists
        if filepath.exists():
            print(f"✅ {date_str}: Already exists, skipping")
            current_date += timedelta(days=1)
            continue
        
        print(f"📥 {date_str}: Downloading...", end='')
        
        try:
            # Set time boundaries for the day
            since = int(current_date.timestamp() * 1000)
            until = int((current_date + timedelta(days=1)).timestamp() * 1000)
            
            all_trades = []
            last_trade_id = None
            
            # Download trades in batches
            while True:
                params = {
                    'startTime': since,
                    'endTime': until,
                    'limit': 1000
                }
                
                if last_trade_id:
                    params['fromId'] = int(last_trade_id) + 1
                
                trades = exchange.fetch_trades(symbol, since=since, params=params)
                
                if not trades:
                    break
                
                all_trades.extend(trades)
                
                # Check if we got all trades for the time period
                if len(trades) < 1000:
                    break
                
                last_trade_id = trades[-1]['info'].get('id', trades[-1].get('id'))
                time.sleep(0.1)  # Rate limiting
            
            if all_trades:
                # Convert to DataFrame
                df = pd.DataFrame([{
                    'timestamp': trade['timestamp'],
                    'price': trade['price'],
                    'amount': trade['amount'],
                    'cost': trade['cost'],
                    'side': trade['side'],
                    'id': trade.get('id', trade['info'].get('id', None))
                } for trade in all_trades])
                
                # Save as feather file
                df.to_feather(filepath)
                print(f" ✅ {len(all_trades):,} trades saved")
                downloaded_count += 1
            else:
                print(f" ⚠️  No trades found")
        
        except Exception as e:
            print(f" ❌ Error: {e}")
        
        current_date += timedelta(days=1)
        time.sleep(0.5)  # Be nice to the API
    
    print("=" * 60)
    print(f"✅ Download complete! {downloaded_count} days of POL tick data downloaded")
    print(f"📁 Data saved to: {tick_data_path}")
    
    # List downloaded files
    files = sorted(tick_data_path.glob("*.feather"))
    if files:
        print(f"\n📊 Total files: {len(files)}")
        print(f"📅 Date range: {files[0].stem.split('-')[-1]} to {files[-1].stem.split('-')[-1]}")

if __name__ == "__main__":
    print("POL/USDT TICK DATA DOWNLOADER")
    print("=" * 60)
    download_pol_tick_data()