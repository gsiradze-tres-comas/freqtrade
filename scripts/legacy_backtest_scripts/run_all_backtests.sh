#!/bin/bash

# Run backtests for all symbols with both strategies
# This script runs each test separately to avoid timeouts

echo "🚀 RUNNING COMPLETE STRATEGY COMPARISON"
echo "========================================"
echo "Testing: BTC, ETH, DOGE, ADA"
echo "Strategies: Try1BullRiderStrategy vs SafeBullRiderStrategy"
echo "Period: Last year (2024-08-11 to 2025-08-10)"
echo "========================================"
echo ""

# Results file
RESULTS_FILE="user_data/backtest_results/all_results_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p user_data/backtest_results

# Function to run backtest and capture results
run_backtest() {
    local SYMBOL=$1
    local STRATEGY=$2
    local CONFIG=$3
    
    echo "Testing $STRATEGY on $SYMBOL..."
    
    # Run backtest and capture output
    OUTPUT=$(freqtrade backtesting \
        --config $CONFIG \
        --strategy $STRATEGY \
        --pairs ${SYMBOL}/USDT:USDT \
        --timerange 20240811-20250810 \
        --timeframe 5m 2>&1)
    
    # Extract key metrics from output
    TRADES=$(echo "$OUTPUT" | grep -E "^\| TOTAL" | awk '{print $4}')
    WIN_RATE=$(echo "$OUTPUT" | grep "Win Rate" | awk '{print $3}')
    PROFIT=$(echo "$OUTPUT" | grep -E "^\| TOTAL.*%" | sed -n 's/.*| *\([0-9.-]*\)%.*/\1/p')
    
    if [ -z "$TRADES" ]; then
        TRADES="0"
        WIN_RATE="0"
        PROFIT="0"
    fi
    
    echo "  Results: $TRADES trades, Win rate: $WIN_RATE, Profit: $PROFIT%"
    echo "$SYMBOL,$STRATEGY,$TRADES,$WIN_RATE,$PROFIT" >> $RESULTS_FILE
}

# Write header
echo "Symbol,Strategy,Trades,WinRate,Profit%" > $RESULTS_FILE

# Test each symbol with both strategies
echo "📊 Testing BTC..."
run_backtest "BTC" "Try1BullRiderStrategy" "user_data/configs/config_billionaire.json"
run_backtest "BTC" "SafeBullRiderStrategy" "user_data/configs/config_safe_bull.json"

echo ""
echo "📊 Testing ETH..."
run_backtest "ETH" "Try1BullRiderStrategy" "user_data/configs/config_billionaire.json"
run_backtest "ETH" "SafeBullRiderStrategy" "user_data/configs/config_safe_bull.json"

echo ""
echo "📊 Testing DOGE..."
run_backtest "DOGE" "Try1BullRiderStrategy" "user_data/configs/config_billionaire.json"
run_backtest "DOGE" "SafeBullRiderStrategy" "user_data/configs/config_safe_bull.json"

echo ""
echo "📊 Testing ADA..."
run_backtest "ADA" "Try1BullRiderStrategy" "user_data/configs/config_billionaire.json"
run_backtest "ADA" "SafeBullRiderStrategy" "user_data/configs/config_safe_bull.json"

echo ""
echo "========================================"
echo "SUMMARY OF RESULTS"
echo "========================================"
cat $RESULTS_FILE | column -t -s ','

echo ""
echo "Results saved to: $RESULTS_FILE"
echo ""

# Calculate totals
TRY1_TOTAL=$(grep "Try1BullRiderStrategy" $RESULTS_FILE | awk -F',' '{sum+=$5} END {print sum}')
SAFE_TOTAL=$(grep "SafeBullRiderStrategy" $RESULTS_FILE | awk -F',' '{sum+=$5} END {print sum}')

echo "🏆 FINAL COMPARISON:"
echo "Try1BullRiderStrategy Total: ${TRY1_TOTAL}%"
echo "SafeBullRiderStrategy Total: ${SAFE_TOTAL}%"

# Determine winner
if (( $(echo "$SAFE_TOTAL > $TRY1_TOTAL" | bc -l) )); then
    echo ""
    echo "🥇 SafeBullRiderStrategy WINS!"
elif (( $(echo "$TRY1_TOTAL > $SAFE_TOTAL" | bc -l) )); then
    echo ""
    echo "🥇 Try1BullRiderStrategy WINS!"
else
    echo ""
    echo "🤝 It's a TIE!"
fi

echo ""
echo "✅ All backtests completed!"