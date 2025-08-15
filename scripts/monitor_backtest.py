#!/usr/bin/env python3
"""
Monitor backtest progress for long-running backtests
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime

def monitor_progress():
    """Monitor backtest progress from progress file"""
    
    progress_file = Path("user_data/backtest_progress.json")
    
    if not progress_file.exists():
        print("❌ No backtest progress file found")
        print("💡 Make sure a backtest is running with progress tracking enabled")
        return
    
    print("📊 BACKTEST PROGRESS MONITOR")
    print("=" * 60)
    print("Press Ctrl+C to stop monitoring\n")
    
    try:
        while True:
            with open(progress_file, 'r') as f:
                progress = json.load(f)
            
            # Clear screen (works on most terminals)
            print("\033[2J\033[H", end="")
            
            print("📊 BACKTEST PROGRESS MONITOR")
            print("=" * 60)
            
            status = progress.get('status', 'unknown')
            if status == 'completed':
                print("✅ BACKTEST COMPLETED!")
                print("-" * 40)
            elif status == 'running':
                print("🔄 BACKTEST RUNNING...")
                print("-" * 40)
            
            # Progress information
            progress_pct = progress.get('progress_pct', 0)
            current_date = progress.get('current_date', 'N/A')
            current_day = progress.get('current_day', 0)
            total_days = progress.get('total_days', 0)
            
            print(f"📅 Date:          {current_date}")
            print(f"📈 Progress:      {progress_pct:.1f}% ({current_day}/{total_days} days)")
            
            # Progress bar
            bar_width = 40
            filled_width = int(progress_pct / 100 * bar_width)
            bar = "█" * filled_width + "░" * (bar_width - filled_width)
            print(f"📊 Progress:      [{bar}] {progress_pct:.1f}%")
            
            # Performance metrics
            current_balance = progress.get('current_balance', 0)
            total_trades = progress.get('total_trades', 0)
            
            if current_balance > 0:
                profit_pct = ((current_balance - 2000) / 2000) * 100
                print(f"💰 Balance:       ${current_balance:,.2f} ({profit_pct:+.1f}%)")
            
            print(f"📊 Trades:        {total_trades:,}")
            
            # Time estimates
            start_time_str = progress.get('start_time', '')
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                elapsed = datetime.now() - start_time
                elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
                print(f"⏱️  Elapsed:       {elapsed_str}")
            
            estimated_completion = progress.get('estimated_completion', '')
            if estimated_completion and status == 'running':
                print(f"🎯 ETA:           {estimated_completion}")
            
            completion_time = progress.get('completion_time', '')
            if completion_time:
                completion_dt = datetime.fromisoformat(completion_time.replace('Z', '+00:00'))
                print(f"✅ Completed:     {completion_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            
            print("\n" + "=" * 60)
            print("💡 Tips:")
            print("  - View detailed results: python3 scripts/analyze_backtest_pairs.py")
            print("  - Kill backtest: pkill -f safe_multi_pair_backtest")
            print("  - Press Ctrl+C to stop monitoring")
            
            if status == 'completed':
                print("\n🎉 Backtest finished! Check the results above.")
                break
            
            # Wait before next update
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped by user")
    except Exception as e:
        print(f"\n❌ Error monitoring progress: {e}")

if __name__ == "__main__":
    monitor_progress()