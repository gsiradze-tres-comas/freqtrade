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

echo "🔬 Running Hyperparameter Optimization for MultiStrategyConsensus"
echo "Optimizing consensus thresholds, strategy weights, and risk parameters"
echo "Target: Achieve 2% average overnight wins like successful try1 bot"
echo ""

# Run hyperparameter optimization
freqtrade hyperopt \
    --config user_data/configs/config_hft_optimized.json \
    --strategy MultiStrategyConsensus \
    --hyperopt-loss SharpeHyperOptLoss \
    --spaces buy sell \
    --epochs 100 \
    --timerange 20250703-20250802 \
    --jobs 1 \
    "$@"

echo ""
echo "Hyperopt completed. Results saved to hyperopt_results.pickle"
echo ""
echo "To apply best parameters:"
echo "freqtrade hyperopt-show -n -1 --print-json"