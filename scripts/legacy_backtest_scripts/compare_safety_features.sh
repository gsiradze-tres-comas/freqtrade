#!/bin/bash

echo "🔍 Comparing Original vs Safe Strategy Performance"
echo "Testing period: August 10-11 (Weekend + Monday Crash)"
echo "================================================"

# Set test period to capture the crash
TIMERANGE="20250810-20250811"

# Create results directory
mkdir -p user_data/backtest_results/safety_comparison

echo ""
echo "📊 Testing ORIGINAL Try1BullRiderStrategy..."
echo "----------------------------------------"
freqtrade backtesting \
    --config user_data/configs/config_billionaire.json \
    --strategy Try1BullRiderStrategy \
    --timerange $TIMERANGE \
    --export trades \
    --export-filename user_data/backtest_results/safety_comparison/original_results.json \
    2>&1 | grep -E "RESULTS|trades|Profit|Drawdown|Win Rate"

echo ""
echo "🛡️ Testing SAFE BullRiderStrategy..."
echo "----------------------------------------"
freqtrade backtesting \
    --config user_data/configs/config_safe_bull.json \
    --strategy SafeBullRiderStrategy \
    --timerange $TIMERANGE \
    --export trades \
    --export-filename user_data/backtest_results/safety_comparison/safe_results.json \
    2>&1 | grep -E "RESULTS|trades|Profit|Drawdown|Win Rate"

echo ""
echo "📈 ANALYSIS:"
echo "============"

# Extract key metrics from the results
echo "The SAFE strategy should show:"
echo "✅ Fewer trades during low liquidity hours (1-5 AM)"
echo "✅ No cascade of stop losses at 11:30 AM"
echo "✅ Lower maximum drawdown"
echo "✅ Better risk-adjusted returns"
echo ""

# Quick Python analysis
python3 << 'EOF'
import json
import os

def analyze_results(filename):
    if not os.path.exists(filename):
        return None
    
    with open(filename, 'r') as f:
        data = json.load(f)
    
    if 'strategy' in data:
        strategy_data = list(data['strategy'].values())[0]
        trades = strategy_data.get('trades', [])
        
        # Count trades by hour
        stop_losses = 0
        morning_trades = 0
        
        for trade in trades:
            if trade.get('exit_reason') == 'stop_loss':
                stop_losses += 1
            
            # Check if trade opened during risky hours
            open_time = trade.get('open_date', '')
            if '01:' in open_time or '02:' in open_time or '03:' in open_time or '04:' in open_time:
                morning_trades += 1
        
        return {
            'total_trades': len(trades),
            'stop_losses': stop_losses,
            'morning_trades': morning_trades,
            'profit': strategy_data.get('profit_total', 0) * 100,
            'drawdown': strategy_data.get('max_drawdown', 0) * 100
        }
    return None

# Analyze both results
original = analyze_results('user_data/backtest_results/safety_comparison/original_results.json')
safe = analyze_results('user_data/backtest_results/safety_comparison/safe_results.json')

if original:
    print(f"ORIGINAL Strategy:")
    print(f"  Total Trades: {original['total_trades']}")
    print(f"  Stop Losses: {original['stop_losses']}")
    print(f"  Low Liquidity Trades: {original['morning_trades']}")
    print(f"  Profit: {original['profit']:.2f}%")
    print(f"  Max Drawdown: {original['drawdown']:.2f}%")
    print()

if safe:
    print(f"SAFE Strategy:")
    print(f"  Total Trades: {safe['total_trades']}")
    print(f"  Stop Losses: {safe['stop_losses']}")
    print(f"  Low Liquidity Trades: {safe['morning_trades']}")
    print(f"  Profit: {safe['profit']:.2f}%")
    print(f"  Max Drawdown: {safe['drawdown']:.2f}%")
    print()
    
    if original:
        print(f"IMPROVEMENTS:")
        print(f"  Stop Loss Reduction: {original['stop_losses'] - safe['stop_losses']} fewer")
        print(f"  Risky Trade Reduction: {original['morning_trades'] - safe['morning_trades']} fewer")
        print(f"  Drawdown Improvement: {original['drawdown'] - safe['drawdown']:.2f}% less")
EOF

echo ""
echo "✅ Safety comparison complete!"
echo "Check user_data/backtest_results/safety_comparison/ for detailed results"