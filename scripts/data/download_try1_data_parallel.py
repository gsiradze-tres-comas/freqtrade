#!/usr/bin/env python3
"""
Parallel Data Download Script for Try1 Strategy
Downloads data for all 15 crypto pairs with progress tracking and parallel processing
"""

import asyncio
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import json

# Configuration
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

DAYS = 30
TIMEFRAME = "1m"
EXCHANGE = "binance"
CONFIG_FILE = "user_data/configs/config_hft_optimized.json"
MAX_WORKERS = 5  # Parallel downloads

# Colors
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color

def print_header():
    """Print script header"""
    print(f"{Colors.BLUE}🚀 Try1 Parallel Data Download Script{Colors.NC}")
    print(f"{Colors.BLUE}===================================={Colors.NC}")
    print(f"📊 Downloading {DAYS} days of {TIMEFRAME} data for {len(PAIRS)} pairs")
    print(f"🏪 Exchange: {EXCHANGE}")
    print(f"🔄 Max parallel downloads: {MAX_WORKERS}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

def check_prerequisites():
    """Check if freqtrade and config file exist"""
    # Check freqtrade command
    try:
        subprocess.run(['freqtrade', '--version'], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.RED}❌ Error: freqtrade command not found{Colors.NC}")
        print("Please make sure freqtrade is installed and in your PATH")
        sys.exit(1)
    
    # Check config file
    if not Path(CONFIG_FILE).exists():
        print(f"{Colors.RED}❌ Error: Config file not found: {CONFIG_FILE}{Colors.NC}")
        sys.exit(1)
    
    # Create logs directory
    Path("user_data/logs").mkdir(parents=True, exist_ok=True)

def download_pair_data(pair: str) -> tuple[str, bool, str]:
    """Download data for a single pair"""
    pair_clean = pair.replace('/', '_').replace(':', '_')
    log_file = f"user_data/logs/download_{pair_clean}.log"
    
    try:
        # Run freqtrade download command
        result = subprocess.run([
            'freqtrade', 'download-data',
            '--exchange', EXCHANGE,
            '--pairs', pair,
            '--timeframe', TIMEFRAME,
            '--days', str(DAYS),
            '--config', CONFIG_FILE
        ], capture_output=True, text=True, timeout=300)  # 5 minute timeout
        
        # Write logs
        with open(log_file, 'w') as f:
            f.write(f"STDOUT:\n{result.stdout}\n\n")
            f.write(f"STDERR:\n{result.stderr}\n\n")
            f.write(f"Return code: {result.returncode}\n")
        
        if result.returncode == 0:
            return pair, True, "Success"
        else:
            return pair, False, f"Failed with code {result.returncode}"
            
    except subprocess.TimeoutExpired:
        return pair, False, "Timeout (5 minutes)"
    except Exception as e:
        return pair, False, f"Exception: {str(e)}"

def show_progress(completed: int, total: int, current_pair: str = None):
    """Show progress bar"""
    percentage = (completed * 100) // total
    bar_length = 30
    filled_length = (percentage * bar_length) // 100
    
    bar = '=' * filled_length + '-' * (bar_length - filled_length)
    
    status = f"Progress: [{bar}] {percentage}% ({completed}/{total})"
    if current_pair:
        status += f" | Current: {current_pair}"
    
    print(f"\r{Colors.CYAN}{status}{Colors.NC}", end='', flush=True)

def main():
    """Main function"""
    print_header()
    check_prerequisites()
    
    # Track results
    successful_downloads = []
    failed_downloads = []
    start_time = time.time()
    
    print(f"{Colors.BLUE}Starting parallel downloads...{Colors.NC}\n")
    
    # Use ThreadPoolExecutor for parallel downloads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all download tasks
        future_to_pair = {
            executor.submit(download_pair_data, pair): pair 
            for pair in PAIRS
        }
        
        # Process completed downloads
        completed = 0
        for future in as_completed(future_to_pair):
            pair = future_to_pair[future]
            
            try:
                pair_result, success, message = future.result()
                
                if success:
                    successful_downloads.append(pair_result)
                    print(f"\n{Colors.GREEN}✅ {pair_result}: {message}{Colors.NC}")
                else:
                    failed_downloads.append((pair_result, message))
                    print(f"\n{Colors.RED}❌ {pair_result}: {message}{Colors.NC}")
                
            except Exception as e:
                failed_downloads.append((pair, f"Exception: {str(e)}"))
                print(f"\n{Colors.RED}❌ {pair}: Exception: {str(e)}{Colors.NC}")
            
            completed += 1
            show_progress(completed, len(PAIRS))
    
    # Calculate total time
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    
    # Final summary
    print(f"\n\n{Colors.BLUE}📊 Download Summary{Colors.NC}")
    print(f"{Colors.BLUE}==================={Colors.NC}")
    print(f"✅ Successful: {Colors.GREEN}{len(successful_downloads)}{Colors.NC}/{len(PAIRS)} pairs")
    print(f"❌ Failed: {Colors.RED}{len(failed_downloads)}{Colors.NC}/{len(PAIRS)} pairs")
    print(f"⏰ Total time: {minutes}m {seconds}s")
    print(f"🏁 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show successful downloads
    if successful_downloads:
        print(f"\n{Colors.GREEN}✅ Successful downloads:{Colors.NC}")
        for pair in successful_downloads:
            print(f"   • {pair}")
    
    # Show failed downloads
    if failed_downloads:
        print(f"\n{Colors.RED}❌ Failed downloads:{Colors.NC}")
        for pair, error in failed_downloads:
            print(f"   • {pair}: {error}")
        print(f"\n{Colors.YELLOW}Check log files in user_data/logs/ for details{Colors.NC}")
    
    # Show data directory info
    data_dir = Path(f"user_data/data/{EXCHANGE}")
    if data_dir.exists():
        feather_files = list(data_dir.glob("*.feather"))
        print(f"\n{Colors.BLUE}📁 Data Directory Info:{Colors.NC}")
        print(f"Location: {data_dir}")
        print(f"Files created: {len(feather_files)}")
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in feather_files if f.exists())
        size_mb = total_size / (1024 * 1024)
        print(f"Total size: {size_mb:.1f} MB")
    
    # Save download report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_pairs": len(PAIRS),
        "successful": len(successful_downloads),
        "failed": len(failed_downloads),
        "duration_seconds": total_time,
        "successful_pairs": successful_downloads,
        "failed_pairs": [{"pair": p, "error": e} for p, e in failed_downloads]
    }
    
    with open("user_data/logs/download_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    # Exit with appropriate code
    if failed_downloads:
        print(f"\n{Colors.YELLOW}⚠️  Some downloads failed. Re-run to retry.{Colors.NC}")
        sys.exit(1)
    else:
        print(f"\n{Colors.GREEN}🎉 All downloads completed successfully!{Colors.NC}")
        print(f"{Colors.GREEN}Ready for backtesting with complete try1 dataset.{Colors.NC}")
        sys.exit(0)

if __name__ == "__main__":
    main()