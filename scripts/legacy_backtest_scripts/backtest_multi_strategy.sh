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

# Run backtest with Multi-Strategy
echo "Running Multi-Strategy Consensus Backtest..."
echo "Testing 15 cryptocurrency pairs with 6 combined strategies"
echo "Based on successful try1 bot patterns that achieved 2% overnight wins"
echo ""

freqtrade backtesting \
    --config user_data/configs/config_multi_simple.json \
    --strategy MultiStrategyConsensus \
    --timerange 20250701- \
    --breakdown day \
    --export trades \
    --export-filename user_data/backtest_results/multi_strategy_backtest_$(date +%Y%m%d_%H%M%S) \
    "$@"

echo ""
echo "Showing detailed results..."
freqtrade backtesting-show --show-pair-list

echo ""
echo "Strategy Analysis:"
echo "- Enhanced Engulfing Pattern: 25% weight"
echo "- RSI Bounce Strategy: 20% weight" 
echo "- MA Crossover Strategy: 20% weight"
echo "- Volume Spike Strategy: 15% weight"
echo "- Breakout Strategy: 10% weight"
echo "- Momentum Backup: 10% weight"
echo ""
echo "Risk Management:"
echo "- 1.2% take profit target"
echo "- 2% stop loss"
echo "- Symbol-specific confidence thresholds"
echo "- Volatility regime filtering"
echo "- Weighted consensus decision making"