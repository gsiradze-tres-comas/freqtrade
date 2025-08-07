#!/bin/bash

# Essential Data Download - Just get BTC and ETH first for testing
echo "📊 Downloading essential data for testing..."
echo "==============================================="

# Source environment
if [ -f .env.local ]; then
    source .env.local
elif [ -f .env ]; then
    source .env
else
    export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db"
fi

# Essential pairs for initial testing
ESSENTIAL_PAIRS="BTC/USDT:USDT ETH/USDT:USDT"

echo "Downloading 3 days of data for essential pairs..."
echo "Pairs: $ESSENTIAL_PAIRS"
echo ""

# Download with longer timeout and multiple timeframes
freqtrade download-data \
    --exchange binance \
    --pairs $ESSENTIAL_PAIRS \
    --timeframe 1m 5m 15m 1h \
    --days 3 \
    --config user_data/configs/config_phase1_optimized.json

echo ""
echo "✅ Essential data download complete!"
echo "You can now test backtesting with BTC and ETH pairs."
echo ""
echo "📋 Next steps:"
echo "   ./backtest_phase1.sh"
echo "   ./run_phase1.sh"
echo ""
echo "🔚 Download script finished. Terminal ready."
exit 0