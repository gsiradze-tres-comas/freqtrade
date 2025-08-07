#!/bin/bash

echo "📊 Starting comprehensive data download..."
echo "========================================"

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

# Download data for HFT pairs - force full redownload
echo "Downloading data for all 15 pairs..."
echo "Using --erase to force full historical download..."
if freqtrade download-data \
    --config user_data/configs/config_hft_optimized.json \
    --timeframe 1m 5m 15m 1h \
    --days 10 \
    --erase; then
    echo ""
    echo "✅ Data download completed successfully!"
    echo "📁 Data stored in: user_data/data/binance/"
    echo ""
    echo "📋 Next steps:"
    echo "   ./backtest_phase1.sh"
    echo "   ./run_phase1.sh"
else
    echo ""
    echo "❌ Data download failed!"
fi

echo ""
echo "🔚 Download script finished. Terminal ready."
exit 0