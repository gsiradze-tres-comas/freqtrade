#!/usr/bin/env python3
"""
Compare performance and accuracy between original and optimized tick backtesting scripts
"""

import subprocess
import time
import json
import sys
from datetime import datetime

def run_original_backtest(symbol, start_date, end_date):
    """Run the original slow tick backtest"""
    print(f"\n{'='*80}")
    print(f"🐌 RUNNING ORIGINAL TICK BACKTEST (iterrows version)")
    print(f"{'='*80}")
    
    cmd = [
        'python3', 'scripts/tick_data/safe_strategy_tick_backtest.py',
        '--symbol', symbol,
        '--start', start_date,
        '--end', end_date
    ]
    
    start_time = time.time()
    try:
        # Run with timeout of 10 minutes (should be enough for 7 days)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        runtime = time.time() - start_time
        
        # Parse results from output
        output = result.stdout
        trades = 0
        win_rate = 0
        total_return = 0
        ticks_processed = 0
        
        for line in output.split('\n'):
            if 'Total Trades:' in line:
                trades = int(line.split(':')[1].strip())
            elif 'Win Rate:' in line:
                win_rate = float(line.split(':')[1].strip().replace('%', ''))
            elif 'Total Return:' in line:
                total_return = float(line.split(':')[1].strip().replace('%', '').replace('+', ''))
            elif 'Ticks Processed:' in line:
                ticks_str = line.split(':')[1].strip().replace(',', '')
                ticks_processed = int(ticks_str)
        
        return {
            'runtime': runtime,
            'trades': trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'ticks_processed': ticks_processed,
            'success': True
        }
    except subprocess.TimeoutExpired:
        print("⚠️ Original backtest timed out after 10 minutes")
        return {
            'runtime': 600,
            'success': False,
            'error': 'Timeout'
        }
    except Exception as e:
        print(f"❌ Error running original backtest: {e}")
        return {
            'runtime': time.time() - start_time,
            'success': False,
            'error': str(e)
        }

def run_optimized_backtest(symbol, start_date, end_date):
    """Run the optimized fast tick backtest"""
    print(f"\n{'='*80}")
    print(f"⚡ RUNNING OPTIMIZED TICK BACKTEST (vectorized version)")
    print(f"{'='*80}")
    
    cmd = [
        'python3', 'scripts/tick_data/safe_strategy_tick_backtest_fast.py',
        '--symbol', symbol,
        '--start', start_date,
        '--end', end_date
    ]
    
    start_time = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        runtime = time.time() - start_time
        
        # Parse results from output
        output = result.stdout
        trades = 0
        win_rate = 0
        total_return = 0
        ticks_processed = 0
        
        for line in output.split('\n'):
            if 'Total Trades:' in line:
                trades = int(line.split(':')[1].strip())
            elif 'Win Rate:' in line:
                win_rate = float(line.split(':')[1].strip().replace('%', ''))
            elif 'Total Return:' in line:
                total_return = float(line.split(':')[1].strip().replace('%', '').replace('+', ''))
            elif 'Ticks Processed:' in line:
                ticks_str = line.split(':')[1].strip().replace(',', '')
                ticks_processed = int(ticks_str)
        
        return {
            'runtime': runtime,
            'trades': trades,
            'win_rate': win_rate,
            'total_return': total_return,
            'ticks_processed': ticks_processed,
            'success': True
        }
    except Exception as e:
        print(f"❌ Error running optimized backtest: {e}")
        return {
            'runtime': time.time() - start_time,
            'success': False,
            'error': str(e)
        }

def main():
    # Test parameters - use 7 days to keep original script runtime reasonable
    symbol = 'ADAUSDT'
    start_date = '2025-07-24'
    end_date = '2025-07-31'
    
    print("📊 TICK BACKTEST PERFORMANCE COMPARISON")
    print("=" * 80)
    print(f"Symbol: {symbol}")
    print(f"Period: {start_date} to {end_date} (7 days)")
    print("=" * 80)
    
    # Run optimized version first (it's faster)
    opt_results = run_optimized_backtest(symbol, start_date, end_date)
    
    # Run original version
    orig_results = run_original_backtest(symbol, start_date, end_date)
    
    # Display comparison
    print(f"\n{'='*80}")
    print("📊 PERFORMANCE COMPARISON RESULTS")
    print("=" * 80)
    
    print(f"\n{'Metric':<25} {'Original':<20} {'Optimized':<20} {'Improvement':<20}")
    print("-" * 85)
    
    if orig_results['success'] and opt_results['success']:
        # Runtime comparison
        speedup = orig_results['runtime'] / opt_results['runtime'] if opt_results['runtime'] > 0 else 0
        print(f"{'Runtime (seconds)':<25} {orig_results['runtime']:<20.1f} {opt_results['runtime']:<20.1f} {speedup:.1f}x faster")
        
        # Ticks processed
        if orig_results['ticks_processed'] > 0:
            orig_tps = orig_results['ticks_processed'] / orig_results['runtime']
            opt_tps = opt_results['ticks_processed'] / opt_results['runtime']
            tps_improvement = opt_tps / orig_tps if orig_tps > 0 else 0
            print(f"{'Ticks/second':<25} {orig_tps:<20,.0f} {opt_tps:<20,.0f} {tps_improvement:.1f}x faster")
        
        # Results comparison
        print(f"{'Total Trades':<25} {orig_results['trades']:<20} {opt_results['trades']:<20}")
        print(f"{'Win Rate (%)':<25} {orig_results['win_rate']:<20.1f} {opt_results['win_rate']:<20.1f}")
        print(f"{'Total Return (%)':<25} {orig_results['total_return']:<20.2f} {opt_results['total_return']:<20.2f}")
        print(f"{'Ticks Processed':<25} {orig_results['ticks_processed']:<20,} {opt_results['ticks_processed']:<20,}")
        
        # Accuracy comparison
        print("\n" + "=" * 85)
        print("📊 ACCURACY COMPARISON")
        print("-" * 85)
        
        trade_diff = abs(orig_results['trades'] - opt_results['trades'])
        return_diff = abs(orig_results['total_return'] - opt_results['total_return'])
        
        if trade_diff <= 5 and return_diff <= 0.5:
            print("✅ Results are nearly identical - optimization maintains accuracy!")
        elif trade_diff <= 10 and return_diff <= 1.0:
            print("⚠️ Minor differences in results - acceptable variance")
        else:
            print("❌ Significant differences in results - review optimization logic")
        
        print(f"Trade count difference: {trade_diff}")
        print(f"Return difference: {return_diff:.2f}%")
        
    elif not orig_results['success']:
        print("\n❌ Original backtest failed or timed out")
        print(f"⚡ Optimized version completed in {opt_results['runtime']:.1f} seconds")
        if opt_results['success']:
            print(f"   - Trades: {opt_results['trades']}")
            print(f"   - Win Rate: {opt_results['win_rate']:.1f}%")
            print(f"   - Return: {opt_results['total_return']:.2f}%")
    else:
        print("\n❌ Optimized backtest failed")
    
    # Summary
    print("\n" + "=" * 85)
    print("📊 SUMMARY")
    print("-" * 85)
    
    if orig_results['success'] and opt_results['success']:
        print(f"⚡ Optimized version is {speedup:.1f}x faster!")
        print(f"⚡ Processing speed: {opt_tps:,.0f} ticks/second (vs {orig_tps:,.0f})")
        
        if orig_results['runtime'] > 60:
            time_saved = orig_results['runtime'] - opt_results['runtime']
            print(f"⏱️ Time saved: {time_saved/60:.1f} minutes")
        
        print("\n💡 RECOMMENDATION:")
        if speedup > 50:
            print("   The optimized version provides massive performance improvements!")
            print("   Use scripts/tick_data/safe_strategy_tick_backtest_fast.py for all future backtests.")
        elif speedup > 10:
            print("   The optimized version is significantly faster.")
            print("   Recommended for large-scale backtesting.")
        else:
            print("   Moderate performance improvement achieved.")
    elif opt_results['success']:
        print("⚡ Optimized version succeeded where original timed out!")
        print("   This demonstrates the critical importance of the optimization.")
        print("\n💡 RECOMMENDATION:")
        print("   Always use the optimized version for tick-level backtesting.")

if __name__ == '__main__':
    main()