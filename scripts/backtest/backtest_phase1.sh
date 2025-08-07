#!/bin/bash

# Phase 1 Backtesting Script
# Tests all enhanced features for income maximization

echo "📊 Freqtrade Phase 1 Backtesting"
echo "================================="
echo "Testing enhanced features:"
echo "- Multi-timeframe confluence"
echo "- Dynamic position sizing"
echo "- Partial profit taking"
echo "- All 15 crypto pairs"
echo "================================="

# Source environment
if [ -f .env.local ]; then
    source .env.local
elif [ -f .env ]; then
    source .env
else
    export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db"
fi

# Set timerange (use 30-day data range: July 1-31, 2025)
if [ -z "$1" ]; then
    TIMERANGE="20250701-20250801"
    echo "Using default timerange: $TIMERANGE (30-day historical data)"
else
    TIMERANGE=$1
    echo "Using custom timerange: $TIMERANGE"
fi

# Run backtest for Phase 1 strategy
echo ""
echo "Running Phase 1 MainMultiStrategyPhase1..."
if freqtrade backtesting \
    --config user_data/configs/config_hft_optimized.json \
    --strategy MainMultiStrategyPhase1 \
    --timerange $TIMERANGE \
    --enable-position-stacking \
    --max-open-trades 15; then
    echo "✅ Phase 1 backtest completed successfully"
else
    echo "❌ Phase 1 backtest failed"
fi

# Run backtest for volatility expansion
echo ""
echo "Running Volatility Expansion Strategy..."
if freqtrade backtesting \
    --config user_data/configs/config_hft_optimized.json \
    --strategy VolatilityExpansionStrategy \
    --timerange $TIMERANGE \
    --timeframe 5m; then
    echo "✅ Volatility expansion backtest completed successfully"
else
    echo "❌ Volatility expansion backtest failed"
fi

# Run backtest for S/R bounce
echo ""
echo "Running Support/Resistance Bounce Strategy..."
if freqtrade backtesting \
    --config user_data/configs/config_hft_optimized.json \
    --strategy SupportResistanceBounceStrategy \
    --timerange $TIMERANGE \
    --timeframe 15m; then
    echo "✅ S/R bounce backtest completed successfully"
else
    echo "❌ S/R bounce backtest failed"
fi

# Show results and exit
echo ""
echo "================================="
echo "📈 Backtesting Complete!"
echo "================================="
echo ""
echo "To view detailed results:"
echo "freqtrade backtesting-show"
echo ""
echo "Expected performance targets:"
echo "- Month 1: 2-3% return"
echo "- Month 2: 3-4% return"
echo "- Month 3+: 4-5% return"
echo ""
echo "🔚 Backtest script finished. Terminal ready."
exit 0