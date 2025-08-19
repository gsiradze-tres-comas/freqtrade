#!/usr/bin/env python3
"""
Check for missing tick data for all trading pairs
"""

from pathlib import Path
from datetime import datetime, date, timedelta

EXTERNAL_STORAGE = Path.home() / "Documents" / "projects" / "tres-comas" / "tick_data"
TRADING_PAIRS = [
    "BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "XRPUSDT",
    "SOLUSDT", "AVAXUSDT", "LINKUSDT", "BNBUSDT", "BCHUSDT",
    "TIAUSDT", "DOTUSDT", "POLUSDT", "UNIUSDT"
]

def check_missing_data():
    """Check for missing tick data"""
    print("=" * 70)
    print("TICK DATA STATUS CHECK")
    print("=" * 70)
    
    # Target date range (last 30 days)
    end_date = date.today() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=30)
    
    print(f"Checking period: {start_date} to {end_date}")
    print(f"Storage path: {EXTERNAL_STORAGE}")
    print("=" * 70)
    
    total_missing = 0
    
    for symbol in TRADING_PAIRS:
        symbol_dir = EXTERNAL_STORAGE / symbol
        missing_dates = []
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            file_path = symbol_dir / f"{symbol}-trades-{date_str}.feather"
            
            if not file_path.exists():
                missing_dates.append(date_str)
            
            current_date += timedelta(days=1)
        
        if missing_dates:
            print(f"\n❌ {symbol}: Missing {len(missing_dates)} days")
            print(f"   Missing dates: {missing_dates[:5]}{'...' if len(missing_dates) > 5 else ''}")
            total_missing += len(missing_dates)
        else:
            # Check latest available date
            files = sorted(symbol_dir.glob("*.feather"))
            if files:
                latest = files[-1].name.split('trades-')[1].replace('.feather', '')
                print(f"✅ {symbol}: Complete (latest: {latest})")
            else:
                print(f"❌ {symbol}: No data found")
    
    print("\n" + "=" * 70)
    if total_missing > 0:
        print(f"⚠️  Total missing: {total_missing} files")
        print(f"💡 Run: python3 scripts/tick_data/download_all_pairs_1year.py --days 2")
        print(f"   to download missing recent data")
    else:
        print("✅ All tick data is up to date!")
    
    # Check for extra pairs not in trading list
    print("\n📦 Extra tick data (not in current trading pairs):")
    for dir_path in EXTERNAL_STORAGE.iterdir():
        if dir_path.is_dir() and dir_path.name not in TRADING_PAIRS:
            files = list(dir_path.glob("*.feather"))
            if files:
                size_mb = sum(f.stat().st_size for f in files) / (1024**2)
                print(f"   {dir_path.name}: {len(files)} files ({size_mb:.0f} MB)")

if __name__ == "__main__":
    check_missing_data()