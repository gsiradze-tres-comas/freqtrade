#!/usr/bin/env python3
"""
ETH Weekend Effect Analysis - 3-Year Comparison
Runs both weekend filtered and unfiltered backtests and compares results
"""

import sys
import time
from pathlib import Path
from datetime import datetime, date

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

from eth_fast_backtest import FastETHBacktester

def run_weekend_comparison(start_date, end_date):
    """Run both weekend filtered and unfiltered backtests"""
    
    print("=" * 80)
    print("ETH WEEKEND EFFECT ANALYSIS - 3-Year Comparison")
    print("=" * 80)
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Mode: Ultra-fast 1-minute candles")
    
    total_days = (end_date - start_date).days + 1
    print(f"Total Days: {total_days}")
    print("=" * 80)
    print()
    
    results = {}
    
    # Test 1: WITH weekend filter (your current setup)
    print("🚫 TEST 1: WITH WEEKEND FILTER")
    print("-" * 50)
    print("⏳ Running backtest with weekend trading disabled...")
    
    start_time = time.time()
    backtester_with_filter = FastETHBacktester(enable_weekend_filter=True, use_minutes=True)
    results_with_filter = backtester_with_filter.run_backtest_fast("ETHUSDT", start_date, end_date)
    time_with_filter = time.time() - start_time
    
    results['with_filter'] = results_with_filter
    results['time_with_filter'] = time_with_filter
    
    print(f"✅ Completed in {time_with_filter/60:.1f} minutes\n")
    
    # Test 2: WITHOUT weekend filter (comparison)
    print("⚠️  TEST 2: WITHOUT WEEKEND FILTER") 
    print("-" * 50)
    print("⏳ Running backtest with weekend trading enabled...")
    
    start_time = time.time()
    backtester_no_filter = FastETHBacktester(enable_weekend_filter=False, use_minutes=True)
    results_no_filter = backtester_no_filter.run_backtest_fast("ETHUSDT", start_date, end_date)
    time_no_filter = time.time() - start_time
    
    results['without_filter'] = results_no_filter
    results['time_without_filter'] = time_no_filter
    
    print(f"✅ Completed in {time_no_filter/60:.1f} minutes\n")
    
    return results

def display_comparison(results):
    """Display side-by-side comparison of results"""
    
    with_filter = results['with_filter']['backtest_summary']
    without_filter = results['without_filter']['backtest_summary']
    
    with_trades = results['with_filter']['trade_analysis']
    without_trades = results['without_filter']['trade_analysis']
    
    print("🎯 WEEKEND EFFECT COMPARISON RESULTS")
    print("=" * 80)
    
    print(f"{'Metric':<25} {'With Weekend Filter':<20} {'Without Filter':<20} {'Difference':<15}")
    print("-" * 80)
    
    # Key performance metrics
    metrics = [
        ('Final Balance', 'final_balance', '${:,.2f}'),
        ('Total Return %', 'total_return_pct', '{:+.2f}%'),
        ('Total P&L', 'total_pnl', '${:+,.2f}'),
        ('Total Trades', 'total_trades', '{:,}'),
        ('Win Rate %', 'win_rate_pct', '{:.1f}%'),
    ]
    
    for label, key, fmt in metrics:
        val_with = with_filter[key]
        val_without = without_filter[key]
        
        if key in ['total_return_pct', 'win_rate_pct']:
            diff = val_with - val_without
            diff_str = f"{diff:+.1f}%"
        elif key == 'total_trades':
            diff = val_with - val_without
            diff_str = f"{diff:+,}"
        else:
            diff = val_with - val_without
            diff_str = f"${diff:+,.2f}"
        
        print(f"{label:<25} {fmt.format(val_with):<20} {fmt.format(val_without):<20} {diff_str:<15}")
    
    print("-" * 80)
    
    # Trade analysis
    profit_factor_with = with_trades['profit_factor']
    profit_factor_without = without_trades['profit_factor']
    pf_diff = profit_factor_with - profit_factor_without
    
    print(f"{'Profit Factor':<25} {profit_factor_with:.2f}{'':16} {profit_factor_without:.2f}{'':16} {pf_diff:+.2f}")
    print()
    
    # Weekend impact analysis
    print("📊 WEEKEND IMPACT ANALYSIS")
    print("-" * 40)
    
    extra_trades = without_filter['total_trades'] - with_filter['total_trades']
    weekend_ratio = extra_trades / without_filter['total_trades'] * 100 if without_filter['total_trades'] > 0 else 0
    
    performance_impact = with_filter['total_return_pct'] - without_filter['total_return_pct']
    
    print(f"Weekend trades (estimated): {extra_trades:,} ({weekend_ratio:.1f}% of total)")
    print(f"Performance impact: {performance_impact:+.2f}% return difference")
    
    if performance_impact > 0:
        print("✅ CONCLUSION: Weekend filter IMPROVES performance")
        print("   💡 Recommendation: Keep weekend trading disabled")
    else:
        print("❌ CONCLUSION: Weekend filter REDUCES performance")  
        print("   💡 Recommendation: Consider enabling weekend trading")
    
    print()
    print(f"⚡ Analysis completed in {(results['time_with_filter'] + results['time_without_filter'])/60:.1f} minutes total")

def main():
    """Run the weekend comparison analysis"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ETH Weekend Effect Analysis")
    parser.add_argument("--start", type=str, default="2022-01-01",
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2025-08-10",
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick test (6 months only)")
    
    args = parser.parse_args()
    
    if args.quick:
        start_date = date(2025, 2, 1)
        end_date = date(2025, 8, 10)
        print("🚀 Quick mode: 6 months analysis")
    else:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    try:
        # Run both backtests
        results = run_weekend_comparison(start_date, end_date)
        
        # Display comparison
        display_comparison(results)
        
    except KeyboardInterrupt:
        print("\n⚠️  Analysis interrupted by user")
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()