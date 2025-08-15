#!/usr/bin/env python3
"""
Compare Static vs Dynamic Position Sizing
Tests how different position sizing methods affect returns and drawdown
"""

import numpy as np
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from validate_compound_math import simulate_compound_trading

def test_position_sizing_methods():
    """Compare different position sizing approaches"""
    
    print("POSITION SIZING COMPARISON")
    print("=" * 80)
    print("Testing how position sizing affects returns and drawdown")
    print()
    
    base_params = {
        'starting_balance': 2000,
        'win_rate': 0.87,
        'avg_win_pct': 0.015,
        'avg_loss_pct': -0.04,
        'trades_per_day': 3,
        'trading_days': 365
    }
    
    scenarios = [
        {
            'name': 'Static $160 per trade',
            'method': 'static_amount',
            'position_size_pct': 160 / 2000  # Fixed $160 (8% of $2000)
        },
        {
            'name': 'Dynamic 8% of balance',
            'method': 'dynamic_percentage', 
            'position_size_pct': 0.08  # Always 8% of current balance
        },
        {
            'name': 'Conservative 5% dynamic',
            'method': 'conservative',
            'position_size_pct': 0.05  # Conservative 5%
        },
        {
            'name': 'Aggressive 12% dynamic',
            'method': 'aggressive',
            'position_size_pct': 0.12  # Aggressive 12%
        }
    ]
    
    results = []
    
    for scenario in scenarios:
        print(f"Testing: {scenario['name']}")
        print("-" * 50)
        
        # Set consistent seed
        np.random.seed(42)
        
        if scenario['method'] == 'static_amount':
            # Modified simulation for static amount
            result = simulate_static_amount_trading(**base_params, fixed_amount=160)
        else:
            result = simulate_compound_trading(**base_params, position_size_pct=scenario['position_size_pct'])
        
        result['scenario'] = scenario['name']
        result['method'] = scenario['method']
        results.append(result)
        
        print(f"Final Result: {result['total_return_pct']:+.1f}% return, {result['max_drawdown_pct']:.1f}% max drawdown")
        print()
    
    # Comparison analysis
    print("=" * 80)
    print("POSITION SIZING ANALYSIS:")
    print("=" * 80)
    print(f"{'Method':<25} {'Return':<12} {'Drawdown':<12} {'Final Balance':<15}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['scenario']:<25} "
              f"{result['total_return_pct']:>+10.1f}% "
              f"{result['max_drawdown_pct']:>10.1f}% "
              f"${result['final_balance']:>13,.0f}")
    
    # Insights
    print("\n" + "=" * 80)
    print("KEY INSIGHTS:")
    print("=" * 80)
    
    static_result = next(r for r in results if r['method'] == 'static_amount')
    dynamic_result = next(r for r in results if r['method'] == 'dynamic_percentage')
    
    return_diff = dynamic_result['total_return_pct'] - static_result['total_return_pct']
    
    print(f"1. Compound Effect: Dynamic sizing achieved {return_diff:+.1f}% more return")
    print(f"2. Risk Difference: Dynamic DD {dynamic_result['max_drawdown_pct']:.1f}% vs Static DD {static_result['max_drawdown_pct']:.1f}%")
    
    if return_diff > 100:
        print("3. ✅ COMPOUND EFFECT IS SIGNIFICANT - explains high backtest returns")
    elif return_diff > 50:
        print("3. ⚠️  Moderate compound effect - partial explanation")
    else:
        print("3. ❌ Compound effect minimal - not main factor in 500% returns")
    
    # Position size growth analysis
    print(f"\n4. Position Size Growth (Dynamic 8%):")
    print(f"   Start: 8% of $2,000 = $160 per trade")
    print(f"   End:   8% of ${dynamic_result['final_balance']:,.0f} = ${dynamic_result['final_balance'] * 0.08:,.0f} per trade")
    print(f"   Growth: {(dynamic_result['final_balance'] * 0.08 / 160):,.1f}x larger positions by year end")
    
    return results

def simulate_static_amount_trading(starting_balance, fixed_amount, win_rate, avg_win_pct, avg_loss_pct, trades_per_day, trading_days):
    """Simulate trading with fixed dollar amount per trade (not percentage)"""
    
    balance = starting_balance
    peak = starting_balance
    max_drawdown = 0
    
    total_trades = 0
    wins = 0
    losses = 0
    
    print(f"  Fixed Amount: ${fixed_amount} per trade")
    print(f"  Win Rate: {win_rate*100:.1f}%")
    print(f"  Avg Win: {avg_win_pct*100:.2f}%, Avg Loss: {avg_loss_pct*100:.2f}%")
    
    for day in range(trading_days):
        # Handle fractional trades per day
        daily_trade_count = int(trades_per_day)
        if np.random.random() < (trades_per_day - daily_trade_count):
            daily_trade_count += 1
        
        for trade in range(daily_trade_count):
            total_trades += 1
            
            # Fixed position size
            position_size = min(fixed_amount, balance * 0.9)  # Don't exceed 90% of balance
            
            # Determine win/loss
            is_win = np.random.random() < win_rate
            
            if is_win:
                profit = position_size * avg_win_pct
                balance += profit
                wins += 1
            else:
                loss = position_size * abs(avg_loss_pct)
                balance -= loss
                losses += 1
            
            # Track drawdown
            if balance > peak:
                peak = balance
            
            current_drawdown = (peak - balance) / peak * 100
            max_drawdown = max(max_drawdown, current_drawdown)
        
        # Progress report every 60 days
        if (day + 1) % 60 == 0:
            total_return = (balance - starting_balance) / starting_balance * 100
            current_win_rate = wins / total_trades * 100 if total_trades > 0 else 0
            print(f"  Day {day+1:3d}: ${balance:>8,.0f} | Return: {total_return:>+6.1f}% | Win Rate: {current_win_rate:>5.1f}%")
    
    final_return = (balance - starting_balance) / starting_balance * 100
    actual_win_rate = wins / total_trades * 100
    
    return {
        'final_balance': balance,
        'total_return_pct': final_return,
        'max_drawdown_pct': max_drawdown,
        'total_trades': total_trades,
        'win_rate': actual_win_rate
    }

if __name__ == "__main__":
    print("POSITION SIZING IMPACT ANALYSIS")
    print("Comparing static vs dynamic position sizing effects")
    print("=" * 80)
    
    results = test_position_sizing_methods()
    
    print("\nCONCLUSION:")
    print("=" * 80)
    
    dynamic_result = next(r for r in results if r['method'] == 'dynamic_percentage')
    
    if dynamic_result['total_return_pct'] > 400:
        print("✅ Dynamic position sizing CAN achieve 500%+ returns")
        print("   This explains the high backtest performance.")
    else:
        print("❌ Even dynamic sizing doesn't fully explain 500% returns")
        print("   Other factors must be contributing (multi-pair, timing, etc.)")
    
    print(f"\nDynamic sizing achieved: {dynamic_result['total_return_pct']:+.1f}% annual return")
    print("This validates the compound growth model in the backtesting.")