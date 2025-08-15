#!/usr/bin/env python3
"""
Validate Compound Math for Trading Bot Returns
Checks if 500% annual return with 87% win rate is mathematically sound
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def simulate_compound_trading(
    starting_balance=2000,
    position_size_pct=0.08,
    win_rate=0.87,
    avg_win_pct=0.015,  # 1.5% average win
    avg_loss_pct=-0.04,  # 4% stop loss
    trades_per_day=2,
    trading_days=365
):
    """
    Simulate compound trading with realistic parameters
    """
    balance = starting_balance
    balance_history = []
    peak = starting_balance
    max_drawdown = 0
    
    total_trades = 0
    wins = 0
    losses = 0
    
    print(f"Starting simulation:")
    print(f"  Initial Balance: ${starting_balance:,.2f}")
    print(f"  Position Size: {position_size_pct*100:.1f}% per trade")
    print(f"  Win Rate: {win_rate*100:.1f}%")
    print(f"  Avg Win: {avg_win_pct*100:.2f}%")
    print(f"  Avg Loss: {avg_loss_pct*100:.2f}%")
    print(f"  Trades/Day: {trades_per_day}")
    print(f"  Trading Days: {trading_days}")
    print("-" * 50)
    
    for day in range(trading_days):
        daily_trades = 0
        daily_start_balance = balance
        
        # Handle fractional trades per day
        daily_trade_count = int(trades_per_day)
        if np.random.random() < (trades_per_day - daily_trade_count):
            daily_trade_count += 1
        
        for trade in range(daily_trade_count):
            total_trades += 1
            
            # Position size based on current balance
            position_size = balance * position_size_pct
            
            # Determine win/loss
            is_win = np.random.random() < win_rate
            
            if is_win:
                # Win trade
                profit = position_size * avg_win_pct
                balance += profit
                wins += 1
            else:
                # Loss trade
                loss = position_size * abs(avg_loss_pct)
                balance -= loss
                losses += 1
            
            # Track peak and drawdown
            if balance > peak:
                peak = balance
            
            current_drawdown = (peak - balance) / peak * 100
            max_drawdown = max(max_drawdown, current_drawdown)
            
            # Record balance
            balance_history.append({
                'day': day + 1,
                'trade': total_trades,
                'balance': balance,
                'position_size': position_size,
                'is_win': is_win,
                'drawdown': current_drawdown
            })
        
        # Daily progress report
        if (day + 1) % 30 == 0 or day == 0 or day == trading_days - 1:
            daily_return = (balance - daily_start_balance) / daily_start_balance * 100
            total_return = (balance - starting_balance) / starting_balance * 100
            current_win_rate = wins / total_trades * 100 if total_trades > 0 else 0
            
            print(f"Day {day+1:3d}: Balance: ${balance:>10,.2f} "
                  f"| Daily: {daily_return:>+6.2f}% "
                  f"| Total: {total_return:>+7.1f}% "
                  f"| Win Rate: {current_win_rate:>5.1f}% "
                  f"| Max DD: {max_drawdown:>5.1f}%")
    
    # Final results
    final_return = (balance - starting_balance) / starting_balance * 100
    actual_win_rate = wins / total_trades * 100
    
    print("\n" + "=" * 80)
    print("SIMULATION RESULTS:")
    print("=" * 80)
    print(f"Final Balance:     ${balance:>15,.2f}")
    print(f"Starting Balance:  ${starting_balance:>15,.2f}")
    print(f"Total Return:      {final_return:>15.1f}%")
    print(f"Total Trades:      {total_trades:>15,}")
    print(f"Wins:              {wins:>15,}")
    print(f"Losses:            {losses:>15,}")
    print(f"Actual Win Rate:   {actual_win_rate:>15.1f}%")
    print(f"Max Drawdown:      {max_drawdown:>15.1f}%")
    print()
    
    # Analysis
    print("ANALYSIS:")
    print("-" * 40)
    
    if final_return > 400:
        print("✅ 500%+ returns are MATHEMATICALLY POSSIBLE with these parameters")
    elif final_return > 200:
        print("⚠️  High returns achieved, but lower than reported 500%")
    else:
        print("❌ Returns much lower than reported - potential bug")
    
    if max_drawdown < 15:
        print("✅ Drawdown within reasonable range")
    elif max_drawdown < 30:
        print("⚠️  Moderate drawdown - risky but manageable")
    else:
        print("❌ High drawdown - very risky strategy")
    
    if abs(actual_win_rate - win_rate * 100) < 5:
        print("✅ Win rate close to target")
    else:
        print("⚠️  Win rate differs from target")
    
    return {
        'final_balance': balance,
        'total_return_pct': final_return,
        'max_drawdown_pct': max_drawdown,
        'total_trades': total_trades,
        'win_rate': actual_win_rate,
        'balance_history': balance_history
    }

def test_different_scenarios():
    """Test various scenarios to validate the math"""
    
    print("TESTING DIFFERENT SCENARIOS")
    print("=" * 80)
    
    scenarios = [
        {
            'name': 'Current SafeBullRider (Conservative)',
            'params': {
                'position_size_pct': 0.08,
                'win_rate': 0.87,
                'avg_win_pct': 0.010,  # 1.0% conservative
                'avg_loss_pct': -0.04,
                'trades_per_day': 1.5,  # Conservative
            }
        },
        {
            'name': 'Optimistic SafeBullRider',
            'params': {
                'position_size_pct': 0.08,
                'win_rate': 0.87,
                'avg_win_pct': 0.015,  # 1.5% per win
                'avg_loss_pct': -0.04,
                'trades_per_day': 2,
            }
        },
        {
            'name': 'Bull Market Boost',
            'params': {
                'position_size_pct': 0.08,
                'win_rate': 0.90,  # Even higher win rate
                'avg_win_pct': 0.018,  # 1.8% per win
                'avg_loss_pct': -0.04,
                'trades_per_day': 2.5,
            }
        }
    ]
    
    results = []
    
    for scenario in scenarios:
        print(f"\nScenario: {scenario['name']}")
        print("-" * 50)
        
        result = simulate_compound_trading(**scenario['params'])
        result['scenario'] = scenario['name']
        results.append(result)
    
    # Compare scenarios
    print("\n" + "=" * 80)
    print("SCENARIO COMPARISON:")
    print("=" * 80)
    print(f"{'Scenario':<25} {'Return':<12} {'Drawdown':<12} {'Trades':<8} {'Win Rate':<8}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['scenario']:<25} "
              f"{result['total_return_pct']:>+10.1f}% "
              f"{result['max_drawdown_pct']:>10.1f}% "
              f"{result['total_trades']:>7,} "
              f"{result['win_rate']:>7.1f}%")
    
    return results

if __name__ == "__main__":
    print("COMPOUND TRADING SIMULATION")
    print("Validating if 500% annual returns are mathematically possible")
    print("=" * 80)
    
    # Set random seed for reproducible results
    np.random.seed(42)
    
    # Run scenario tests
    test_results = test_different_scenarios()
    
    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("=" * 80)
    
    max_return = max(r['total_return_pct'] for r in test_results)
    min_drawdown = min(r['max_drawdown_pct'] for r in test_results)
    
    if max_return > 400:
        print("✅ 500%+ annual returns are MATHEMATICALLY POSSIBLE")
        print("   with 87% win rate and compound position sizing")
    else:
        print("❌ 500% returns seem unrealistic with these parameters")
    
    print(f"\nBest case scenario achieved: {max_return:.1f}% return")
    print(f"Best drawdown control: {min_drawdown:.1f}% max drawdown")
    
    print("\nNote: Real trading includes market conditions, slippage,")
    print("      and other factors not captured in this simulation.")