#!/bin/bash

# Memory-efficient streaming tick backtesting for ALL coins, FULL YEAR
# MEMORY EFFICIENT: Processes day-by-day, never loads full datasets

echo "💧 Running MEMORY-EFFICIENT streaming tick backtest: ALL coins, FULL YEAR"
echo "========================================================================="

# Run the ACCURATE memory-efficient streaming backtester  
python3 scripts/tick_data/streaming_tick_backtest_accurate.py "$@"

echo ""
echo "💡 Usage examples:"
echo "  ./scripts/backtest/test_all_coins_year.sh                    # All coins, 1 year (default)"
echo "  ./scripts/backtest/test_all_coins_year.sh --recent           # All coins, 3 months"
echo "  ./scripts/backtest/test_all_coins_year.sh --full             # All coins, all available data"
echo "  ./scripts/backtest/test_all_coins_year.sh --single ADAUSDT   # Single coin, 1 year"
echo "  ./scripts/backtest/test_all_coins_year.sh --exclude BTCUSDT  # All except BTC"