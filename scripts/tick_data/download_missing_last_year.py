#!/usr/bin/env python3
"""
Download missing tick data for the last year (BTC, DOGE)
Based on current data gaps identified
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import sys

# Configuration
SYMBOLS = ['BTCUSDT', 'DOGEUSDT']  # ETH is complete
BASE_URL = "https://data.binance.vision/data/futures/um/daily/aggTrades"
TICK_DATA_DIR = Path("user_data/tick_data")
BATCH_SIZE = 5  # Download 5 days at a time
DELAY_SECONDS = 1  # Delay between requests

def download_day(symbol, date_str):
    """Download single day of tick data"""
    url = f"{BASE_URL}/{symbol}/{symbol}-aggTrades-{date_str}.zip"
    
    print(f"Downloading {symbol} {date_str}...")
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            # Save zip file temporarily
            zip_path = f"/tmp/{symbol}-{date_str}.zip"
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            
            # Extract and convert to feather
            import zipfile
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                csv_file = zip_ref.namelist()[0]
                zip_ref.extract(csv_file, '/tmp')
                csv_path = f"/tmp/{csv_file}"
            
            # Load CSV and convert to feather
            df = pd.read_csv(csv_path, names=[
                'agg_trade_id', 'price', 'quantity', 'first_trade_id',
                'last_trade_id', 'timestamp', 'is_buyer_maker', 'ignore'
            ])
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Save as feather
            symbol_dir = TICK_DATA_DIR / symbol
            symbol_dir.mkdir(parents=True, exist_ok=True)
            
            feather_path = symbol_dir / f"{symbol}-trades-{date_str}.feather"
            df.to_feather(feather_path)
            
            # Cleanup temp files
            os.remove(zip_path)
            os.remove(csv_path)
            
            print(f"✅ {symbol} {date_str}: {len(df):,} trades")
            return True
            
        elif response.status_code == 404:
            print(f"⚠️  {symbol} {date_str}: No data available")
            return False
        else:
            print(f"❌ {symbol} {date_str}: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ {symbol} {date_str}: Error - {e}")
        return False

def get_missing_dates(symbol):
    """Get missing dates for last year"""
    symbol_dir = TICK_DATA_DIR / symbol
    existing_files = set()
    
    if symbol_dir.exists():
        for file in symbol_dir.glob("*.feather"):
            date_part = file.stem.split('-trades-')[1]
            existing_files.add(date_part)
    
    # Generate all dates for last year
    start_date = datetime(2024, 8, 11)  # From analysis
    end_date = datetime(2025, 8, 11)    # Today
    
    missing_dates = []
    current_date = start_date
    
    while current_date < end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        if date_str not in existing_files:
            missing_dates.append(date_str)
        current_date += timedelta(days=1)
    
    return missing_dates

def main():
    print("📊 Downloading missing tick data for last year...")
    print(f"Target symbols: {SYMBOLS}")
    print(f"Data directory: {TICK_DATA_DIR}")
    
    total_downloaded = 0
    total_failed = 0
    
    for symbol in SYMBOLS:
        print(f"\n🔍 Checking {symbol}...")
        missing_dates = get_missing_dates(symbol)
        
        if not missing_dates:
            print(f"✅ {symbol}: No missing data")
            continue
            
        print(f"📅 {symbol}: {len(missing_dates)} missing days")
        print(f"Range: {missing_dates[0]} to {missing_dates[-1]}")
        
        # Download in batches
        for i in range(0, len(missing_dates), BATCH_SIZE):
            batch = missing_dates[i:i+BATCH_SIZE]
            print(f"\n📦 Batch {i//BATCH_SIZE + 1}: {len(batch)} days")
            
            for date_str in batch:
                success = download_day(symbol, date_str)
                if success:
                    total_downloaded += 1
                else:
                    total_failed += 1
                
                # Delay to avoid rate limiting
                time.sleep(DELAY_SECONDS)
            
            # Longer delay between batches
            if i + BATCH_SIZE < len(missing_dates):
                print(f"⏳ Waiting 5 seconds before next batch...")
                time.sleep(5)
    
    print(f"\n📈 Download Summary:")
    print(f"✅ Successfully downloaded: {total_downloaded} files")
    print(f"❌ Failed downloads: {total_failed} files")
    print(f"🎯 Total processing time: ~{(total_downloaded + total_failed) * 2} seconds")
    
    if total_downloaded > 0:
        print(f"\n🚀 Ready for backtesting with updated data!")
        print(f"Run: python3 scripts/tick_data/eth_realistic_backtest.py --recent")

if __name__ == "__main__":
    main()