#!/usr/bin/env python3
"""
Download 1 year of tick data for all trading pairs
Downloads to external storage location to save space
"""

import os
import sys
import time
import asyncio
import aiohttp
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta
import logging
import zipfile
import io

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
EXTERNAL_STORAGE = Path.home() / "Documents" / "projects" / "tres-comas" / "tick_data"
TRADING_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "BNBUSDT",
    "BCHUSDT",
    "TIAUSDT",
    "DOTUSDT",
    "UNIUSDT",
    "1INCHUSDT"
]

# Binance data URL pattern
BASE_URL = "https://data.binance.vision/data/futures/um/daily/trades"

async def download_tick_file(session, symbol, date_str, max_retries=3):
    """Download a single tick data file with retry logic"""
    filename = f"{symbol}-trades-{date_str}.zip"
    url = f"{BASE_URL}/{symbol}/{filename}"
    
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120, connect=30)) as response:
                if response.status == 200:
                    data = await response.read()
                    return data, filename
                elif response.status == 404:
                    logger.debug(f"  ✗ {date_str}: No data available (404)")
                    return None, None
                elif response.status == 429:
                    # Rate limited - wait and retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"  ⚠️ {date_str}: Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"  ✗ {date_str}: HTTP {response.status} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    return None, None
        except asyncio.TimeoutError:
            logger.error(f"  ✗ {date_str}: Timeout (120s) - attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return None, None
        except aiohttp.ClientError as e:
            logger.error(f"  ✗ {date_str}: Connection error - {str(e)[:50]} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return None, None
        except Exception as e:
            logger.error(f"  ✗ {date_str}: {type(e).__name__}: {str(e)[:100]} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            return None, None
    
    return None, None

def process_zip_data(zip_data, symbol, date_str):
    """Process downloaded zip data and save as feather"""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            csv_name = f"{symbol}-trades-{date_str}.csv"
            
            with z.open(csv_name) as f:
                # Read CSV with proper dtype handling
                try:
                    # First try: assume no header (older format)
                    df = pd.read_csv(
                        f, 
                        names=['trade_id', 'price', 'qty', 'quoteQty', 'time', 'is_buyer_maker'],
                        dtype={'trade_id': 'int64', 'price': 'float64', 'qty': 'float64', 
                               'quoteQty': 'float64', 'time': 'int64', 'is_buyer_maker': 'bool'},
                        low_memory=False
                    )
                    
                    # Check if first row looks like headers
                    if df.iloc[0]['time'] == 'time' or not str(df.iloc[0]['time']).isdigit():
                        # It has headers, read again skipping first row
                        f.seek(0)
                        df = pd.read_csv(
                            f, 
                            header=0,
                            dtype={'trade_id': 'int64', 'price': 'float64', 'qty': 'float64', 
                                   'quoteQty': 'float64', 'time': 'int64', 'is_buyer_maker': 'bool'},
                            low_memory=False
                        )
                        df.columns = ['trade_id', 'price', 'qty', 'quoteQty', 'time', 'is_buyer_maker']
                except Exception as read_err:
                    # Try with headers and mixed types
                    f.seek(0)
                    df = pd.read_csv(f, header=0, low_memory=False)
                    # Rename columns to our standard names
                    df.columns = ['trade_id', 'price', 'qty', 'quoteQty', 'time', 'is_buyer_maker']
                
                # Convert types
                df['trade_id'] = pd.to_numeric(df['trade_id'], errors='coerce')
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
                df['qty'] = pd.to_numeric(df['qty'], errors='coerce')
                df['quoteQty'] = pd.to_numeric(df['quoteQty'], errors='coerce')
                df['time'] = pd.to_numeric(df['time'], errors='coerce')
                df['is_buyer_maker'] = df['is_buyer_maker'].astype(bool)
                
                # Remove any invalid rows
                df = df.dropna(subset=['time', 'price'])
                
                # Add datetime column
                df['datetime'] = pd.to_datetime(df['time'], unit='ms', utc=True)
                
                # Save as feather
                output_dir = EXTERNAL_STORAGE / symbol
                output_dir.mkdir(parents=True, exist_ok=True)
                
                output_file = output_dir / f"{symbol}-trades-{date_str}.feather"
                df.to_feather(output_file)
                
                return len(df)
    except Exception as e:
        logger.error(f"Error processing {symbol} {date_str}: {e}")
        return 0

async def download_symbol_data(symbol, start_date, end_date):
    """Download all data for a single symbol"""
    logger.info(f"Starting download for {symbol}")
    
    # Create list of dates to download
    dates_to_download = []
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        
        # Check if file already exists
        output_file = EXTERNAL_STORAGE / symbol / f"{symbol}-trades-{date_str}.feather"
        if not output_file.exists():
            dates_to_download.append(date_str)
        
        current_date += timedelta(days=1)
    
    if not dates_to_download:
        logger.info(f"✅ {symbol}: All data already downloaded")
        return
    
    logger.info(f"📥 {symbol}: Downloading {len(dates_to_download)} days")
    
    # Download in batches with improved configuration
    connector = aiohttp.TCPConnector(
        limit=10,  # Total connection limit
        limit_per_host=5,  # Limit per host
        keepalive_timeout=300,  # Keep connections alive for 5 minutes
        enable_cleanup_closed=True
    )
    timeout = aiohttp.ClientTimeout(total=120, connect=30, sock_read=60)
    
    async with aiohttp.ClientSession(
        connector=connector, 
        timeout=timeout,
        headers={'User-Agent': 'freqtrade-data-downloader/1.0'}
    ) as session:
        downloaded = 0
        failed = 0
        total_ticks = 0
        
        # Process in smaller batches to avoid overwhelming
        batch_size = 5  # Reduced batch size for more stability
        for i in range(0, len(dates_to_download), batch_size):
            batch = dates_to_download[i:i+batch_size]
            
            # Add semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(3)
            
            async def download_with_semaphore(date_str):
                async with semaphore:
                    return await download_tick_file(session, symbol, date_str)
            
            tasks = [download_with_semaphore(date_str) for date_str in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result, date_str in zip(results, batch):
                if isinstance(result, Exception):
                    logger.error(f"  ✗ {date_str}: Exception - {result}")
                    failed += 1
                    continue
                
                data, filename = result
                if data:
                    ticks = process_zip_data(data, symbol, date_str)
                    if ticks > 0:
                        downloaded += 1
                        total_ticks += ticks
                        logger.debug(f"  ✓ {date_str}: {ticks:,} ticks")
                    else:
                        failed += 1
                        logger.warning(f"  ✗ {date_str}: Processing failed")
                else:
                    failed += 1
                    logger.debug(f"  ✗ {date_str}: No data available")
            
            # Longer delay between batches for stability
            await asyncio.sleep(2)
            
            # Progress update
            progress = ((i + len(batch)) / len(dates_to_download)) * 100
            logger.info(f"  {symbol}: {progress:.1f}% complete ({downloaded} downloaded, {failed} failed)")
    
    logger.info(f"✅ {symbol}: Downloaded {downloaded} days, {total_ticks:,} total ticks")

async def download_all_pairs(start_date, end_date):
    """Download data for all trading pairs"""
    logger.info(f"Starting download for {len(TRADING_PAIRS)} pairs")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Storage location: {EXTERNAL_STORAGE}")
    
    # Ensure storage directory exists
    EXTERNAL_STORAGE.mkdir(parents=True, exist_ok=True)
    
    # Download each symbol sequentially to avoid rate limits
    for i, symbol in enumerate(TRADING_PAIRS, 1):
        logger.info(f"\n[{i}/{len(TRADING_PAIRS)}] Processing {symbol}")
        await download_symbol_data(symbol, start_date, end_date)
        
        # Delay between symbols to respect rate limits
        if i < len(TRADING_PAIRS):
            await asyncio.sleep(2)
    
    # Create/update symlinks for each pair
    logger.info("\n📎 Creating symlinks in user_data/tick_data/")
    tick_data_dir = Path("user_data/tick_data")
    tick_data_dir.mkdir(parents=True, exist_ok=True)
    
    for symbol in TRADING_PAIRS:
        source = EXTERNAL_STORAGE / symbol
        target = tick_data_dir / symbol
        
        if source.exists():
            try:
                if target.is_symlink():
                    # Remove existing symlink
                    target.unlink()
                elif target.exists() and target.is_dir():
                    # Check if it's already pointing to the right place
                    try:
                        if target.resolve() == source.resolve():
                            logger.info(f"  ✓ {symbol} already linked correctly")
                            continue
                        else:
                            # Remove directory if it's not a symlink
                            import shutil
                            shutil.rmtree(target)
                    except:
                        logger.warning(f"  ⚠️  {symbol}: Can't replace existing directory with symlink")
                        continue
                elif target.exists():
                    # Remove regular file
                    target.unlink()
                
                target.symlink_to(source)
                logger.info(f"  ✓ Linked {symbol}")
            except PermissionError:
                logger.warning(f"  ⚠️  {symbol}: Permission denied, skipping symlink")
            except Exception as e:
                logger.warning(f"  ⚠️  {symbol}: Symlink error - {e}")
    
    logger.info("\n✅ All downloads complete!")
    
    # Summary statistics
    total_size = 0
    total_files = 0
    for symbol in TRADING_PAIRS:
        symbol_dir = EXTERNAL_STORAGE / symbol
        if symbol_dir.exists():
            files = list(symbol_dir.glob("*.feather"))
            total_files += len(files)
            for f in files:
                total_size += f.stat().st_size
    
    logger.info(f"\n📊 Summary:")
    logger.info(f"  Total files: {total_files:,}")
    logger.info(f"  Total size: {total_size / (1024**3):.2f} GB")
    if total_files > 0:
        logger.info(f"  Average per file: {total_size / total_files / (1024**2):.1f} MB")

def main():
    """Main entry point"""
    global TRADING_PAIRS  # Declare at the beginning
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Download 1 year of tick data for all trading pairs")
    parser.add_argument("--days", type=int, default=365,
                        help="Number of days to download (default: 365)")
    parser.add_argument("--start-date", type=str, default=None,
                        help="Start date (YYYY-MM-DD). Default: 365 days ago")
    parser.add_argument("--end-date", type=str, default=None,
                        help="End date (YYYY-MM-DD). Default: yesterday")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Download only specific symbol (e.g., BTCUSDT)")
    
    args = parser.parse_args()
    
    # Determine date range
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    else:
        # Default: last 365 days (or specified days)
        end_date = date.today() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=args.days - 1)
    
    print("=" * 70)
    print("TICK DATA DOWNLOAD - All Trading Pairs")
    print("=" * 70)
    print(f"Date Range:     {start_date} to {end_date}")
    print(f"Total Days:     {(end_date - start_date).days + 1}")
    print(f"Storage Path:   {EXTERNAL_STORAGE}")
    
    if args.symbol:
        if args.symbol.upper() in TRADING_PAIRS:
            pairs_to_download = [args.symbol.upper()]
            print(f"Symbol:         {args.symbol.upper()} only")
        else:
            print(f"❌ Error: {args.symbol} not in trading pairs list")
            print(f"Available: {', '.join(TRADING_PAIRS)}")
            return
    else:
        pairs_to_download = TRADING_PAIRS
        print(f"Pairs:          {len(pairs_to_download)} symbols")
    
    print("=" * 70)
    
    # Estimate download size
    estimated_size_gb = len(pairs_to_download) * ((end_date - start_date).days + 1) * 0.05  # ~50MB per day per pair
    print(f"\n⚠️  Estimated download size: ~{estimated_size_gb:.1f} GB")
    print(f"⚠️  This will take considerable time. Continue? (Ctrl+C to cancel)")
    
    try:
        time.sleep(5)  # Give user time to cancel
    except KeyboardInterrupt:
        print("\n❌ Download cancelled by user")
        return
    
    print("\n🚀 Starting download...\n")
    
    # Override global TRADING_PAIRS if single symbol specified
    if args.symbol:
        TRADING_PAIRS = pairs_to_download
    
    # Run async download
    try:
        asyncio.run(download_all_pairs(start_date, end_date))
        
        print("\n✅ Download complete!")
        print(f"📁 Data saved to: {EXTERNAL_STORAGE}")
        print(f"🔗 Symlinks created in: user_data/tick_data/")
        
    except KeyboardInterrupt:
        print("\n⚠️  Download interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during download: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()