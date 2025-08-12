#!/bin/bash

# The ONE and ONLY backtesting script you need
# Simulates PARALLEL multi-coin trading like live mode
# Tracks shared balance across all trades

echo "🚀 UNIFIED FREQTRADE BACKTESTING"
echo "======================================="
echo "✅ Parallel multi-coin trading simulation"  
echo "✅ Shared balance tracking across all trades"
echo "✅ Memory-efficient streaming processing"
echo "✅ Production-ready accuracy"
echo "======================================="

# Run the unified parallel backtester
python3 scripts/tick_data/unified_parallel_backtest.py "$@"

echo ""
echo "💡 Usage examples:"
echo "  ./scripts/backtest.sh                           # All coins, 1 year (default)"
echo "  ./scripts/backtest.sh --recent                  # All coins, 3 months"  
echo "  ./scripts/backtest.sh --full                    # All coins, full historical data"
echo "  ./scripts/backtest.sh --single ADAUSDT          # Single coin focus"
echo "  ./scripts/backtest.sh --exclude BTCUSDT ETHUSDT # Exclude specific coins"
echo "  ./scripts/backtest.sh --start 2025-01-01 --end 2025-08-01  # Custom period"