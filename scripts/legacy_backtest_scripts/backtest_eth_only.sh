#!/bin/bash

# ETH-Only Backtesting Script
# Tests Try1BullRiderStrategy on ETH/USDT using your complete tick dataset

echo "=================================="
echo "ETH-Only Backtest"
echo "=================================="
echo "Strategy: Try1BullRiderStrategy"
echo "Pair: ETH/USDT only"
echo "Data: Complete tick data from 2022"
echo "Config: ETH-only configuration"
echo ""

# Check if tick data is available
if [ ! -L "user_data/tick_data" ]; then
    echo "❌ Error: Tick data symlink not found!"
    echo "Run this first: ln -s ~/Documents/projects/tres-comas/tick_data user_data/tick_data"
    exit 1
fi

echo "📊 Available time ranges:"
echo "Recent (recommended): --timerange 20241001-20250810"
echo "6 months: --timerange 20250201-20250810"
echo "Full dataset: --timerange 20220101-20250810"
echo ""

# Default to recent 10 months for good performance
TIMERANGE=${1:-"20241001-20250810"}

echo "🚀 Running ETH backtest with timerange: $TIMERANGE"
echo ""

# Run the backtest
freqtrade backtesting \
    --config user_data/configs/config_eth_only.json \
    --strategy Try1BullRiderStrategy \
    --timerange "$TIMERANGE" \
    --enable-protections \
    --breakdown month \
    --cache none

echo ""
echo "=================================="
echo "✅ ETH Backtest Complete!"
echo "=================================="
echo ""
echo "📈 To view results:"
echo "freqtrade backtesting-analysis --config user_data/configs/config_eth_only.json"
echo ""
echo "🔄 To run different time periods:"
echo "./scripts/backtest/backtest_eth_only.sh 20250101-20250810  # 8 months"
echo "./scripts/backtest/backtest_eth_only.sh 20240601-20250810  # 14 months"
echo "./scripts/backtest/backtest_eth_only.sh 20220101-20250810  # Full dataset"