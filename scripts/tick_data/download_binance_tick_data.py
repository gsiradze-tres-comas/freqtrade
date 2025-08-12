#!/usr/bin/env python3
"""
Binance Tick Data Downloader
Downloads raw trade data from Binance Historical Data Vision
https://data.binance.vision/
"""

import argparse
import requests
import zipfile
import pandas as pd
from datetime import datetime, timedelta, date
from pathlib import Path
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceTickDownloader:
    def __init__(self, data_dir: str = "user_data/tick_data", market: str = "um"):
        # market: "um" (USD-M) or "cm" (COIN-M)
        if market not in {"um", "cm"}:
            raise ValueError("market must be 'um' (USD-M) or 'cm' (COIN-M)")
        self.base_url = f"https://data.binance.vision/data/futures/{market}/daily/trades"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def get_url(self, symbol: str, for_date: date) -> str:
        """Generate download URL for specific symbol and date"""
        date_str = for_date.strftime("%Y-%m-%d")
        filename = f"{symbol}-trades-{date_str}.zip"
        return f"{self.base_url}/{symbol}/{filename}"
    
    def download_file(self, url, local_path):
        """Download a single file with retry logic"""
        try:
            logger.info(f"Downloading {url}")
            response = requests.get(url, stream=True, timeout=300)
            
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"✓ Downloaded {local_path.name}")
                return True
            else:
                logger.warning(f"✗ Failed to download {url} - Status: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"✗ Error downloading {url}: {e}")
            return False
    
    def extract_and_process(self, zip_path: Path, symbol: str, for_date: date) -> bool:
        """Extract ZIP and convert to feather format"""
        try:
            # Extract ZIP file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(zip_path.parent)
            
            # Find the CSV file
            csv_file = zip_path.with_suffix('.csv')
            if not csv_file.exists():
                logger.error(f"CSV file not found after extraction: {csv_file}")
                return False
            
            # Read and process CSV (Binance Vision trades can be headerless)
            logger.info(f"Processing {csv_file.name}")
            df = pd.read_csv(csv_file, header=0)
            if 'time' not in df.columns:
                # Retry assuming headerless: id,price,qty,quoteQty,time,isBuyerMaker,(isBestMatch)
                df = pd.read_csv(csv_file, header=None)
                # Assign canonical names for first 6 columns
                base_cols = ['id', 'price', 'qty', 'quoteQty', 'time', 'isBuyerMaker']
                rename_map_fallback = {i: name for i, name in enumerate(base_cols) if i in df.columns}
                df = df.rename(columns=rename_map_fallback)
            
            # Normalize columns from Binance Vision to our internal schema
            # Binance Vision trades usually have: id, price, qty, quoteQty, time, isBuyerMaker, (isBestMatch)
            rename_map = {}
            if 'id' in df.columns:
                rename_map['id'] = 'trade_id'
            if 'quote_qty' in df.columns:
                # Older dumps might use snake_case
                rename_map['quote_qty'] = 'quoteQty'
            # Normalize isBuyerMaker to is_buyer_maker expected by our downstream scripts
            if 'isBuyerMaker' in df.columns:
                rename_map['isBuyerMaker'] = 'is_buyer_maker'
            elif 'is_buyer_maker' not in df.columns and 'is_buyer' in df.columns:
                # Edge-case fallback
                rename_map['is_buyer'] = 'is_buyer_maker'

            df = df.rename(columns=rename_map)
            
            # Convert timestamp to datetime
            if 'time' not in df.columns:
                logger.error("Column 'time' not found in CSV. Unexpected schema.")
                return False
            df['datetime'] = pd.to_datetime(df['time'], unit='ms', utc=True)
            # Ensure numeric dtypes
            for col in ('price', 'qty'):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'quoteQty' in df.columns:
                df['quoteQty'] = pd.to_numeric(df['quoteQty'], errors='coerce')
            # Ensure boolean for maker flag if present as string
            if 'is_buyer_maker' in df.columns:
                if df['is_buyer_maker'].dtype == object:
                    df['is_buyer_maker'] = df['is_buyer_maker'].astype(str).str.lower().map({'true': True, 'false': False}).fillna(False)
            
            # Keep only the columns we need in correct order
            required_cols = ['trade_id', 'price', 'qty', 'quoteQty', 'time', 'is_buyer_maker', 'datetime']
            # Create trade_id if missing by using row index as fallback (rare)
            if 'trade_id' not in df.columns:
                df['trade_id'] = df.index.astype('int64')
            # Some symbols may lack quoteQty in certain dumps; fill with price*qty as approximation
            if 'quoteQty' not in df.columns and {'price', 'qty'} <= set(df.columns):
                df['quoteQty'] = df['price'] * df['qty']
            # If is_buyer_maker still missing, default False
            if 'is_buyer_maker' not in df.columns:
                df['is_buyer_maker'] = False
            df = df[required_cols]
            
            # Save as feather for fast loading
            feather_path = self.data_dir / symbol / f"{symbol}-trades-{for_date.strftime('%Y-%m-%d')}.feather"
            feather_path.parent.mkdir(parents=True, exist_ok=True)
            
            df.to_feather(feather_path)
            logger.info(f"✓ Processed {len(df):,} trades -> {feather_path.name}")
            
            # Clean up temporary files
            csv_file.unlink()
            zip_path.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Error processing {zip_path}: {e}")
            return False
    
    def download_symbol_date_range(self, symbol: str, start_date: date, end_date: date) -> int:
        """Download tick data for a symbol across a date range"""
        logger.info(f"Downloading {symbol} tick data from {start_date} to {end_date}")
        
        current_date = start_date
        success_count = 0
        total_days = (end_date - start_date).days + 1
        
        while current_date <= end_date:
            try:
                # Generate URL and local path
                url = self.get_url(symbol, current_date)
                zip_path = self.data_dir / "temp" / f"{symbol}-trades-{current_date.strftime('%Y-%m-%d')}.zip"
                zip_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Check if already processed
                feather_path = self.data_dir / symbol / f"{symbol}-trades-{current_date.strftime('%Y-%m-%d')}.feather"
                if feather_path.exists():
                    logger.info(f"⚠ {feather_path.name} already exists, skipping")
                    success_count += 1
                    current_date += timedelta(days=1)
                    continue
                
                # Download and process
                if self.download_file(url, zip_path):
                    if self.extract_and_process(zip_path, symbol, current_date):
                        success_count += 1
                    time.sleep(1)  # Rate limiting
                
                current_date += timedelta(days=1)
                
            except KeyboardInterrupt:
                logger.info("Download interrupted by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                current_date += timedelta(days=1)
        
        logger.info(f"Download complete: {success_count}/{total_days} days successfully processed")
        return success_count
    
    def get_available_data_summary(self):
        """Get summary of downloaded tick data"""
        summary = {}
        
        for symbol_dir in self.data_dir.iterdir():
            if symbol_dir.is_dir() and symbol_dir.name != "temp":
                symbol = symbol_dir.name
                files = list(symbol_dir.glob("*.feather"))
                
                if files:
                    # Get date range
                    dates = [f.stem.split('-trades-')[1] for f in files]
                    dates.sort()
                    
                    # Count total trades
                    total_trades = 0
                    for file in files:
                        try:
                            df = pd.read_feather(file)
                            total_trades += len(df)
                        except:
                            continue
                    
                    summary[symbol] = {
                        'files': len(files),
                        'date_range': f"{dates[0]} to {dates[-1]}" if dates else "None",
                        'total_trades': total_trades
                    }
        
        return summary

def _parse_pairs_or_symbols(arg: str) -> list[str]:
    """Accept comma-separated list of Binance symbols or freqtrade pairs and normalize to Binance symbols.
    Examples: "BTCUSDT,ETHUSDT" or "BTC/USDT:USDT,ETH/USDT:USDT" -> ["BTCUSDT", "ETHUSDT"]
    """
    raw_items = [x.strip() for x in arg.split(',') if x.strip()]
    normalized: list[str] = []
    for item in raw_items:
        if '/' in item:
            # Convert "BTC/USDT:USDT" -> "BTCUSDT"
            base_quote = item.split(':')[0]  # BTC/USDT
            base, quote = base_quote.split('/')
            normalized.append(f"{base}{quote}")
        else:
            normalized.append(item)
    return normalized


def main():
    parser = argparse.ArgumentParser(description="Download Binance futures tick data (trades) from Binance Vision")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated list of Binance symbols or freqtrade pairs (e.g. BTCUSDT,ETHUSDT or BTC/USDT:USDT,ETH/USDT:USDT). If omitted, loads from user_data/configs/config_billionaire.json pair_whitelist.")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date (YYYY-MM-DD). Defaults to 2022-01-01 if --symbols omitted, else 7 days before --end")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (YYYY-MM-DD). Defaults to yesterday (UTC)")
    parser.add_argument("--data-dir", type=str, default="user_data/tick_data",
                        help="Directory to store downloaded tick data")
    parser.add_argument("--market", type=str, default="um", choices=["um", "cm"],
                        help="Futures market type: um = USD-M, cm = COIN-M")

    args = parser.parse_args()

    # Zero-params friendly defaults
    config_path = Path("user_data/configs/config_billionaire.json")
    if args.symbols is None and config_path.exists():
        try:
            import json
            with open(config_path, 'r') as f:
                cfg = json.load(f)
            pairs = cfg.get('exchange', {}).get('pair_whitelist', [])
            symbols = _parse_pairs_or_symbols(','.join(pairs)) if pairs else ["BTCUSDT"]
            # Default to long historical range for convenience
            end_dt = (datetime.utcnow().date() - timedelta(days=1)) if args.end is None else datetime.strptime(args.end, "%Y-%m-%d").date()
            start_dt = datetime(2022, 1, 1).date() if args.start is None else datetime.strptime(args.start, "%Y-%m-%d").date()
        except Exception:
            symbols = ["BTCUSDT"]
            end_dt = (datetime.utcnow().date() - timedelta(days=1))
            start_dt = end_dt - timedelta(days=6)
    else:
        # Use provided args or hard defaults
        symbols = _parse_pairs_or_symbols(args.symbols) if args.symbols else ["BTCUSDT"]
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else (datetime.utcnow().date() - timedelta(days=1))
        if args.start:
            start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
        else:
            # Short default window when symbols were passed explicitly without dates
            start_dt = end_dt - timedelta(days=6)

    downloader = BinanceTickDownloader(data_dir=args.data_dir, market=args.market)

    print("Starting tick data download...")
    print("=" * 50)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Date range: {start_dt} to {end_dt}")
    print(f"Data dir: {args.data_dir}")

    for symbol in symbols:
        print(f"\nDownloading {symbol}...")
        downloader.download_symbol_date_range(symbol, start_dt, end_dt)
    
    print("\n" + "=" * 50)
    print("Download Summary:")
    summary = downloader.get_available_data_summary()
    for symbol, info in summary.items():
        print(f"{symbol:12} {info['files']:3d} files  {info['date_range']:20} {info['total_trades']:,} trades")

if __name__ == "__main__":
    main()