#!/usr/bin/env python3
"""
Quick Data Download Script - Downloads 7 days of recent data for faster testing
"""

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import json

# Configuration - Much more practical amounts
PAIRS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT", 
    "BNB/USDT:USDT",
    "SOL/USDT:USDT",
    "ADA/USDT:USDT",
    "DOT/USDT:USDT",
    "MATIC/USDT:USDT",
    "LINK/USDT:USDT",
    "AVAX/USDT:USDT",
    "UNI/USDT:USDT",
    "LTC/USDT:USDT",
    "ATOM/USDT:USDT",
    "XRP/USDT:USDT",
    "ALGO/USDT:USDT",
    "FTM/USDT:USDT"
]

DAYS = 3  # Just 3 days for quick testing (reduce load)
TIMEFRAME = "1m"
EXCHANGE = "binance"
CONFIG_FILE = "user_data/configs/config_hft_optimized.json"

# Colors
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'

def download_batch_data(pairs: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Download data for multiple pairs in one command (like essential script)"""
    try:
        pairs_str = ' '.join(pairs)
        print(f"{Colors.BLUE}📊 Downloading {len(pairs)} pairs in batch...{Colors.NC}")
        print(f"Pairs: {pairs_str}")
        
        # Run freqtrade download command with explicit completion handling
        result = subprocess.run([
            'freqtrade', 'download-data',
            '--exchange', EXCHANGE,
            '--pairs'] + pairs + [
            '--timeframe', TIMEFRAME, '5m', '15m', '1h',
            '--days', str(DAYS),
            '--config', CONFIG_FILE
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ Batch download: Success{Colors.NC}")
            return pairs, []
        else:
            print(f"{Colors.RED}❌ Batch download: Failed with code {result.returncode}{Colors.NC}")
            return [], [(pair, f"Batch failed with code {result.returncode}") for pair in pairs]
            
    except Exception as e:
        print(f"{Colors.RED}❌ Batch download: Exception: {str(e)}{Colors.NC}")
        return [], [(pair, f"Exception: {str(e)}") for pair in pairs]

def download_single_pair(pair: str) -> tuple[str, bool, str]:
    """Fallback: Download single pair if batch fails"""
    try:
        print(f"{Colors.BLUE}📊 Downloading {pair} individually...{Colors.NC}")
        
        # Run freqtrade download command with explicit completion handling
        result = subprocess.run([
            'freqtrade', 'download-data',
            '--exchange', EXCHANGE,
            '--pairs', pair,
            '--timeframe', TIMEFRAME,
            '--days', str(DAYS),
            '--config', CONFIG_FILE
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            print(f"{Colors.GREEN}✅ {pair}: Success{Colors.NC}")
            return pair, True, "Success"
        else:
            print(f"{Colors.RED}❌ {pair}: Failed with code {result.returncode}{Colors.NC}")
            return pair, False, f"Failed with code {result.returncode}"
            
    except Exception as e:
        print(f"{Colors.RED}❌ {pair}: Exception: {str(e)}{Colors.NC}")
        return pair, False, f"Exception: {str(e)}"

def main():
    """Main function - batch download like essential script"""
    print(f"{Colors.BLUE}🚀 Quick Data Download Script{Colors.NC}")
    print(f"{Colors.BLUE}============================{Colors.NC}")
    print(f"📊 Downloading {DAYS} days of {TIMEFRAME} + higher timeframes for {len(PAIRS)} pairs")
    print(f"🏪 Exchange: {EXCHANGE}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Create logs directory
    Path("user_data/logs").mkdir(parents=True, exist_ok=True)
    
    # Track results
    successful_downloads = []
    failed_downloads = []
    start_time = time.time()
    
    # Filter out problematic pairs (MATIC and FTM)
    active_pairs = [pair for pair in PAIRS if pair not in ["MATIC/USDT:USDT", "FTM/USDT:USDT"]]
    
    # Try batch download first (like essential script)
    print(f"Attempting batch download for {len(active_pairs)} pairs...")
    batch_success, batch_failures = download_batch_data(active_pairs)
    
    if batch_success:
        print(f"{Colors.GREEN}✅ Batch download successful for all pairs!{Colors.NC}")
        successful_downloads.extend(batch_success)
    else:
        print(f"{Colors.YELLOW}⚠️ Batch download failed, trying individual downloads...{Colors.NC}")
        failed_downloads.extend(batch_failures)
        
        # Fallback to individual downloads
        for i, pair in enumerate(active_pairs, 1):
            print(f"\n[{i}/{len(active_pairs)}] Individual download: {pair}")
            
            pair_result, success, message = download_single_pair(pair)
            
            if success:
                successful_downloads.append(pair_result)
            else:
                failed_downloads.append((pair_result, message))
            
            # Short delay between individual downloads
            if i < len(active_pairs):
                time.sleep(2)
    
    # Calculate total time
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    
    # Final summary
    print(f"\n{Colors.BLUE}📊 Download Summary{Colors.NC}")
    print(f"{Colors.BLUE}==================={Colors.NC}")
    print(f"✅ Successful: {Colors.GREEN}{len(successful_downloads)}{Colors.NC}/{len(PAIRS)} pairs")
    print(f"❌ Failed: {Colors.RED}{len(failed_downloads)}{Colors.NC}/{len(PAIRS)} pairs")
    print(f"⏰ Total time: {minutes}m {seconds}s")
    
    if successful_downloads:
        print(f"\n{Colors.GREEN}✅ Successful downloads:{Colors.NC}")
        for pair in successful_downloads:
            print(f"   • {pair}")
    
    if failed_downloads:
        print(f"\n{Colors.RED}❌ Failed downloads:{Colors.NC}")
        for pair, error in failed_downloads:
            print(f"   • {pair}: {error}")
    
    # Show data directory info
    data_dir = Path(f"user_data/data/{EXCHANGE}")
    if data_dir.exists():
        feather_files = list(data_dir.glob("*.feather"))
        print(f"\n{Colors.BLUE}📁 Data Directory Info:{Colors.NC}")
        print(f"Location: {data_dir}")
        print(f"Files created: {len(feather_files)}")
        
        if feather_files:
            total_size = sum(f.stat().st_size for f in feather_files if f.exists())
            size_mb = total_size / (1024 * 1024)
            print(f"Total size: {size_mb:.1f} MB")
    
    if len(successful_downloads) >= 2:
        print(f"\n{Colors.GREEN}🎉 Downloaded enough data for testing!{Colors.NC}")
        print(f"{Colors.GREEN}You can now run backtests.{Colors.NC}")
        print(f"\n{Colors.BLUE}📋 Next steps:{Colors.NC}")
        print(f"   ./backtest_phase1.sh")
        print(f"   ./run_phase1.sh")
        exit_code = 0
    else:
        print(f"\n{Colors.YELLOW}⚠️  Not enough data downloaded for meaningful backtests.{Colors.NC}")
        exit_code = 1
    
    print(f"\n{Colors.BLUE}✅ Download script completed. Exiting...{Colors.NC}")
    return exit_code

if __name__ == "__main__":
    try:
        exit_code = main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Download interrupted by user{Colors.NC}")
        exit_code = 130
    finally:
        print(f"\n{Colors.BLUE}🔚 Script finished. Terminal ready.{Colors.NC}")
        sys.exit(exit_code)