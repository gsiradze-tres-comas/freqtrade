#!/usr/bin/env python3
"""
Fix futures data files to include candle_type column required by Freqtrade
"""

import pandas as pd
import os
from pathlib import Path

data_dir = Path("user_data/data/binance")

# Process all futures files
for file in data_dir.glob("*-futures.feather"):
    print(f"Processing {file.name}...")
    
    # Read the data
    df = pd.read_feather(file)
    
    # Add candle_type column if it doesn't exist
    if 'candle_type' not in df.columns:
        df['candle_type'] = 'futures'
        
        # Save back
        df.to_feather(file)
        print(f"  ✓ Added candle_type column to {file.name}")
    else:
        print(f"  - {file.name} already has candle_type column")

print("\n✓ All futures files updated!")