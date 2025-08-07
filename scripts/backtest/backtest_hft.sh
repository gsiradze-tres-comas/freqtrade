#!/bin/bash

# Load environment variables if .env.local exists
if [ -f .env.local ]; then
    source .env.local
fi

# Fallback to manual setting if DATABASE_URL is not set
if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db"
fi

# Export Freqtrade environment variables
export FREQTRADE__EXCHANGE__KEY="${BINANCE_API_KEY}"
export FREQTRADE__EXCHANGE__SECRET="${BINANCE_API_SECRET}"
export FREQTRADE__DB_URL="${DATABASE_URL}"

# Run backtest with HFT strategy
echo "Running HFT Strategy Backtest..."
freqtrade backtesting \
    --config user_data/configs/config_hft_optimized.json \
    --strategy HighFrequencyStrategy \
    --timerange 20250701- \
    --breakdown day \
    --export trades \
    --export-filename user_data/backtest_results/hft_backtest_$(date +%Y%m%d_%H%M%S) \
    "$@"

echo ""
echo "Showing results..."
freqtrade backtesting-show --show-pair-list