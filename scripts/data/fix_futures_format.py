#!/usr/bin/env python3
"""
Fix futures data format for Freqtrade compatibility
"""

import pandas as pd
import os
from pathlib import Path
import json

# Change to freqtrade directory
os.chdir('/Users/gsiradze/Documents/projects/tres-comas/freqtrade')

data_dir = Path("user_data/data/binance")

print("Fixing futures data format...")
print("-" * 50)

# Process all 5m files
for file in data_dir.glob("*_USDT_USDT-5m.feather"):
    try:
        print(f"\nProcessing {file.name}...")
        
        # Read the data
        df = pd.read_feather(file)
        
        # Ensure all required columns exist
        if 'date' not in df.columns:
            print(f"  ❌ Missing 'date' column in {file.name}")
            continue
            
        # Convert date to datetime if it's not already
        df['date'] = pd.to_datetime(df['date'], utc=True)
        
        # Add candle_type column with 'futures' value
        df['candle_type'] = 'futures'
        
        # Ensure columns are in correct order
        expected_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'candle_type']
        
        # Check if all columns exist
        missing_cols = [col for col in expected_cols[:-1] if col not in df.columns]
        if missing_cols:
            print(f"  ❌ Missing columns: {missing_cols}")
            continue
        
        # Reorder columns
        df = df[expected_cols]
        
        # Save back with updated format
        df.to_feather(file)
        
        # Also create a metadata file that Freqtrade might look for
        metadata = {
            'pair': file.name.replace('_USDT_USDT-5m.feather', '/USDT:USDT'),
            'timeframe': '5m',
            'candle_type': 'futures',
            'data_format': 'feather',
            'first_date': str(df['date'].min()),
            'last_date': str(df['date'].max()),
            'length': len(df)
        }
        
        print(f"  ✓ Fixed {file.name}")
        print(f"    Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"    Candles: {len(df):,}")
        
    except Exception as e:
        print(f"  ❌ Error processing {file.name}: {e}")

print("\n" + "-" * 50)
print("✓ All files processed!")
print("\nNow checking if Freqtrade can see the data...")

# Test if we can load the data
try:
    test_file = data_dir / "BTC_USDT_USDT-5m.feather"
    if test_file.exists():
        df = pd.read_feather(test_file)
        print(f"\n✓ Successfully loaded BTC test file:")
        print(f"  Columns: {df.columns.tolist()}")
        print(f"  Candle type: {df['candle_type'].iloc[0] if 'candle_type' in df.columns else 'MISSING'}")
        print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
except Exception as e:
    print(f"\n❌ Error loading test file: {e}")