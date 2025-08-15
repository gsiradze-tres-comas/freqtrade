#!/usr/bin/env python3
"""
Compare multiple backtest results to identify patterns and trends
"""

import json
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

def load_backtest_results(pattern="backtest-result-safe-*.json"):
    """Load all matching backtest result files"""
    
    results_dir = Path("user_data/backtest_results")
    files = sorted(results_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not files:
        print(f"❌ No backtest files found matching pattern: {pattern}")
        return []
    
    backtest_data = []
    
    for file in files:
        try:
            with open(file, 'r') as f:
                data = json.load(f)
            
            # Extract key information
            strategy_data = data['strategy']['SafeBullRiderStrategy']
            
            backtest_info = {
                'filename': file.name,
                'timestamp': file.stem.split('-')[-1],
                'date': datetime.fromtimestamp(int(file.stem.split('-')[-1])),
                'total_return': strategy_data.get('total_return', 0),
                'total_trades': strategy_data.get('total_trades', 0),
                'win_rate': strategy_data.get('win_rate', 0),
                'max_drawdown': strategy_data.get('max_drawdown', 0),
                'profit_sum': strategy_data.get('profit_sum', 0),
                'results_per_pair': strategy_data.get('results_per_pair', []),
                'backtest_days': data.get('backtest_days', 0),
                'backtest_start': data.get('backtest_start', ''),
                'backtest_end': data.get('backtest_end', '')
            }
            
            backtest_data.append(backtest_info)
            
        except Exception as e:
            print(f"⚠️  Error loading {file.name}: {e}")
            continue
    
    return backtest_data

def compare_overall_performance(backtests):
    """Compare overall performance across backtests"""
    
    if len(backtests) < 2:
        print("❌ Need at least 2 backtests to compare")
        return
    
    print("\n" + "=" * 80)
    print("BACKTEST PERFORMANCE COMPARISON")
    print("=" * 80)
    
    print(f"{'Date':<12} {'Period':<15} {'Return %':<10} {'Trades':<8} {'Win %':<8} {'Max DD %':<8} {'Profit':<10}")
    print("-" * 80)
    
    for bt in backtests:
        date_str = bt['date'].strftime('%Y-%m-%d')
        period = f"{bt['backtest_days']}d" if bt['backtest_days'] else "N/A"
        
        print(f"{date_str:<12} {period:<15} {bt['total_return']:>8.1f}% "
              f"{bt['total_trades']:>6,} {bt['win_rate']:>6.1f}% "
              f"{bt['max_drawdown']:>7.1f}% ${bt['profit_sum']:>8,.0f}")

def compare_pair_performance(backtests):
    """Compare per-pair performance across backtests"""
    
    print("\n" + "=" * 80)
    print("PAIR PERFORMANCE COMPARISON")
    print("=" * 80)
    
    # Collect all pairs across all backtests
    all_pairs = set()
    pair_data = {}
    
    for i, bt in enumerate(backtests):
        date_str = bt['date'].strftime('%Y-%m-%d')
        pair_data[date_str] = {}
        
        for pair_result in bt['results_per_pair']:
            pair = pair_result['key']
            all_pairs.add(pair)
            pair_data[date_str][pair] = {
                'profit': pair_result.get('profit_sum', 0),
                'trades': pair_result.get('trades', 0),
                'wins': pair_result.get('wins', 0)
            }
    
    # Sort pairs by average performance
    pair_avg_profits = {}
    for pair in all_pairs:
        profits = []
        for date in pair_data:
            if pair in pair_data[date]:
                profits.append(pair_data[date][pair]['profit'])
        pair_avg_profits[pair] = sum(profits) / len(profits) if profits else 0
    
    sorted_pairs = sorted(pair_avg_profits.items(), key=lambda x: x[1], reverse=True)
    
    # Display comparison table
    dates = sorted(pair_data.keys())
    
    print(f"{'Pair':<18}", end='')
    for date in dates[-3:]:  # Show last 3 backtests
        print(f"{date:<15}", end='')
    print("Avg Profit")
    print("-" * 80)
    
    for pair, avg_profit in sorted_pairs:
        print(f"{pair:<18}", end='')
        
        profits_for_display = []
        for date in dates[-3:]:
            if pair in pair_data[date]:
                profit = pair_data[date][pair]['profit']
                profits_for_display.append(profit)
                print(f"${profit:>8,.0f}    ", end='')
            else:
                print(f"{'N/A':>8}    ", end='')
        
        print(f"${avg_profit:>8,.0f}")

def identify_consistent_patterns(backtests):
    """Identify consistently good/bad performing pairs"""
    
    print("\n" + "=" * 80)
    print("CONSISTENCY ANALYSIS")
    print("=" * 80)
    
    # Track performance across backtests
    pair_performances = {}
    
    for bt in backtests:
        for pair_result in bt['results_per_pair']:
            pair = pair_result['key']
            profit = pair_result.get('profit_sum', 0)
            
            if pair not in pair_performances:
                pair_performances[pair] = []
            
            pair_performances[pair].append(profit)
    
    consistent_winners = []
    consistent_losers = []
    volatile_pairs = []
    
    for pair, profits in pair_performances.items():
        if len(profits) >= 2:  # Need at least 2 data points
            avg_profit = sum(profits) / len(profits)
            all_positive = all(p > 0 for p in profits)
            all_negative = all(p < 0 for p in profits)
            
            # Calculate volatility (coefficient of variation)
            if avg_profit != 0:
                std_dev = (sum((p - avg_profit) ** 2 for p in profits) / len(profits)) ** 0.5
                cv = abs(std_dev / avg_profit)
                
                if all_positive and cv < 0.3:  # Low volatility, consistent profits
                    consistent_winners.append((pair, avg_profit, cv))
                elif all_negative and cv < 0.3:  # Low volatility, consistent losses
                    consistent_losers.append((pair, avg_profit, cv))
                elif cv > 0.5:  # High volatility
                    volatile_pairs.append((pair, avg_profit, cv))
    
    # Display results
    if consistent_winners:
        print("🏆 CONSISTENTLY PROFITABLE PAIRS:")
        print("-" * 40)
        for pair, avg_profit, cv in sorted(consistent_winners, key=lambda x: x[1], reverse=True):
            print(f"  {pair:<15} Avg: ${avg_profit:>7.0f} (CV: {cv:.2f})")
    
    if consistent_losers:
        print("\n❌ CONSISTENTLY UNPROFITABLE PAIRS:")
        print("-" * 40)
        for pair, avg_profit, cv in sorted(consistent_losers, key=lambda x: x[1]):
            print(f"  {pair:<15} Avg: ${avg_profit:>7.0f} (CV: {cv:.2f})")
    
    if volatile_pairs:
        print("\n📈📉 HIGHLY VOLATILE PAIRS:")
        print("-" * 40)
        for pair, avg_profit, cv in sorted(volatile_pairs, key=lambda x: x[2], reverse=True):
            status = "+" if avg_profit > 0 else "-"
            print(f"  {pair:<15} Avg: ${avg_profit:>7.0f} (CV: {cv:.2f}) {status}")

def generate_recommendations(backtests):
    """Generate trading recommendations based on backtest comparisons"""
    
    print("\n" + "=" * 80)
    print("TRADING RECOMMENDATIONS")
    print("=" * 80)
    
    if len(backtests) < 2:
        print("❌ Need multiple backtests for meaningful recommendations")
        return
    
    # Analyze trends
    latest = backtests[0]
    previous = backtests[1] if len(backtests) > 1 else None
    
    print("📊 BASED ON BACKTEST COMPARISON:")
    print("-" * 40)
    
    # Performance trend
    if previous:
        return_change = latest['total_return'] - previous['total_return']
        if return_change > 5:
            print("✅ Strategy performance is IMPROVING (+{:.1f}% return)".format(return_change))
        elif return_change < -5:
            print("⚠️  Strategy performance is DECLINING ({:.1f}% return)".format(return_change))
        else:
            print("📊 Strategy performance is STABLE ({:+.1f}% change)".format(return_change))
    
    # Risk analysis
    avg_max_dd = sum(bt['max_drawdown'] for bt in backtests) / len(backtests)
    if avg_max_dd > 15:
        print("🚨 HIGH RISK: Average max drawdown {:.1f}% - Consider position size reduction".format(avg_max_dd))
    elif avg_max_dd > 10:
        print("⚠️  MEDIUM RISK: Average max drawdown {:.1f}% - Monitor closely".format(avg_max_dd))
    else:
        print("✅ LOW RISK: Average max drawdown {:.1f}% - Risk management effective".format(avg_max_dd))
    
    # Trade frequency analysis
    avg_trades = sum(bt['total_trades'] for bt in backtests) / len(backtests)
    latest_trades = latest['total_trades']
    
    if latest_trades > avg_trades * 1.2:
        print("⚡ HIGH ACTIVITY: {} trades vs {:.0f} average - Monitor for overtrading".format(latest_trades, avg_trades))
    elif latest_trades < avg_trades * 0.8:
        print("🐌 LOW ACTIVITY: {} trades vs {:.0f} average - Check for missed opportunities".format(latest_trades, avg_trades))

def main():
    """Main comparison function"""
    
    print("📊 FREQTRADE BACKTEST COMPARISON TOOL")
    print("=" * 60)
    
    # Load all SafeBullRider backtest results
    backtests = load_backtest_results()
    
    if not backtests:
        return
    
    print(f"📁 Found {len(backtests)} backtest results")
    
    # Run comparisons
    compare_overall_performance(backtests)
    compare_pair_performance(backtests)
    identify_consistent_patterns(backtests)
    generate_recommendations(backtests)
    
    print("\n" + "=" * 80)
    print("💡 USAGE TIPS:")
    print("=" * 80)
    print("• Run backtests regularly to track strategy evolution")
    print("• Focus on consistently profitable pairs for live trading")
    print("• Investigate volatile pairs - they might need different parameters")
    print("• Monitor drawdown trends to maintain risk management")
    print("• Compare different time periods to validate strategy robustness")

if __name__ == "__main__":
    main()