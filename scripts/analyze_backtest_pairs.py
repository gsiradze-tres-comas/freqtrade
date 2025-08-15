#!/usr/bin/env python3
"""
Analyze backtest results to show performance for ALL pairs
"""

import json
import sys
from pathlib import Path

def analyze_all_pairs(json_file):
    """Analyze and display performance for all pairs from backtest results"""
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Extract per-pair results
    if 'results_per_pair' in data['strategy']['SafeBullRiderStrategy']:
        pairs = data['strategy']['SafeBullRiderStrategy']['results_per_pair']
        
        # Sort by profit (descending)
        sorted_pairs = sorted(pairs, key=lambda x: x['profit_sum'], reverse=True)
        
        print("\n" + "=" * 80)
        print("COMPLETE PAIRS PERFORMANCE BREAKDOWN")
        print("=" * 80)
        print(f"{'Pair':<18} {'Trades':<8} {'Total P&L':<12} {'Win Rate':<10} {'Avg Trade':<12} {'Status'}")
        print("-" * 80)
        
        winners = []
        losers = []
        
        for pair in sorted_pairs:
            win_rate = (pair['wins'] / pair['trades'] * 100) if pair['trades'] > 0 else 0
            avg_trade = pair['profit_sum'] / pair['trades'] if pair['trades'] > 0 else 0
            
            # Determine status
            if pair['profit_sum'] > 0:
                status = "✅ PROFITABLE"
                winners.append(pair)
            else:
                status = "❌ LOSS"
                losers.append(pair)
            
            print(f"{pair['key']:<18} {pair['trades']:<8} ${pair['profit_sum']:>+10.2f} {win_rate:>8.1f}% ${avg_trade:>+10.2f} {status}")
        
        print("-" * 80)
        
        # Summary statistics
        total_profit = sum(p['profit_sum'] for p in pairs)
        total_trades = sum(p['trades'] for p in pairs)
        total_wins = sum(p['wins'] for p in pairs)
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        print(f"{'TOTAL':<18} {total_trades:<8} ${total_profit:>+10.2f} {overall_win_rate:>8.1f}%")
        
        print("\n" + "=" * 80)
        print("PERFORMANCE SUMMARY")
        print("=" * 80)
        print(f"🏆 Profitable Pairs: {len(winners)} out of {len(pairs)}")
        print(f"❌ Losing Pairs:     {len(losers)} out of {len(pairs)}")
        
        if losers:
            print("\n📉 WORST PERFORMERS (Pairs that lost money):")
            print("-" * 40)
            for pair in losers:
                win_rate = (pair['wins'] / pair['trades'] * 100) if pair['trades'] > 0 else 0
                print(f"  {pair['key']:<15} Lost: ${abs(pair['profit_sum']):>.2f} ({pair['trades']} trades, {win_rate:.1f}% win rate)")
        
        if winners:
            print("\n📈 TOP 3 PERFORMERS:")
            print("-" * 40)
            for i, pair in enumerate(winners[:3], 1):
                win_rate = (pair['wins'] / pair['trades'] * 100) if pair['trades'] > 0 else 0
                print(f"  {i}. {pair['key']:<12} Profit: ${pair['profit_sum']:>8.2f} ({pair['trades']} trades, {win_rate:.1f}% win rate)")
        
        # Additional insights
        print("\n" + "=" * 80)
        print("KEY INSIGHTS")
        print("=" * 80)
        
        # Find pairs with unusual patterns
        low_win_rate_profitable = [p for p in winners if (p['wins']/p['trades']*100) < 50]
        high_win_rate_losers = [p for p in losers if p['trades'] > 0 and (p['wins']/p['trades']*100) > 70]
        
        if low_win_rate_profitable:
            print("⚠️  Profitable despite low win rate (<50%):")
            for p in low_win_rate_profitable:
                wr = (p['wins']/p['trades']*100)
                print(f"   {p['key']}: {wr:.1f}% win rate but +${p['profit_sum']:.2f}")
        
        if high_win_rate_losers:
            print("⚠️  Losing despite high win rate (>70%):")
            for p in high_win_rate_losers:
                wr = (p['wins']/p['trades']*100)
                print(f"   {p['key']}: {wr:.1f}% win rate but -${abs(p['profit_sum']):.2f}")
        
        # Trading frequency analysis
        avg_trades_per_pair = total_trades / len(pairs)
        high_activity = [p for p in pairs if p['trades'] > avg_trades_per_pair * 1.5]
        low_activity = [p for p in pairs if p['trades'] < avg_trades_per_pair * 0.5]
        
        if high_activity:
            print(f"\n🔥 High activity pairs (>{avg_trades_per_pair * 1.5:.0f} trades):")
            for p in high_activity[:3]:
                print(f"   {p['key']}: {p['trades']} trades")
        
        if low_activity:
            print(f"\n🐌 Low activity pairs (<{avg_trades_per_pair * 0.5:.0f} trades):")
            for p in low_activity[:3]:
                print(f"   {p['key']}: {p['trades']} trades")
    
    else:
        print("❌ No per-pair results found in the backtest file")

if __name__ == "__main__":
    # Find the most recent SafeBullRider backtest
    results_dir = Path("user_data/backtest_results")
    safe_files = sorted(results_dir.glob("backtest-result-safe-*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if safe_files:
        latest_file = safe_files[0]
        print(f"📁 Analyzing: {latest_file.name}")
        analyze_all_pairs(latest_file)
    else:
        print("❌ No SafeBullRider backtest results found")