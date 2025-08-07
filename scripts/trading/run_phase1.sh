#!/bin/bash

# Phase 1 Trading Bot Runner
# Target: 2-5% monthly returns with enhanced features

echo "🚀 Starting Freqtrade Phase 1 - Quick Income Maximization"
echo "=================================================="
echo "Features enabled:"
echo "✅ All 15 crypto pairs trading"
echo "✅ Multi-timeframe confluence (1m, 5m, 15m, 1h)"
echo "✅ Dynamic position sizing (Kelly Criterion)"
echo "✅ Partial profit taking (1%, 2%, 3%)"
echo "✅ Market session optimization"
echo "✅ Volatility expansion trading"
echo "✅ Support/resistance bounce trading"
echo "=================================================="

# Source environment variables
if [ -f .env.local ]; then
    echo "Loading environment from .env.local..."
    source .env.local
elif [ -f .env ]; then
    echo "Loading environment from .env..."
    source .env
else
    echo "No environment file found. Using defaults..."
    export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db"
fi

# Set API keys if available
if [ -n "$BINANCE_API_KEY" ]; then
    export FREQTRADE__EXCHANGE__KEY="${BINANCE_API_KEY}"
    export FREQTRADE__EXCHANGE__SECRET="${BINANCE_API_SECRET}"
    echo "✅ Binance API credentials loaded"
else
    echo "⚠️  No Binance API credentials found - running in dry-run mode"
fi

# Ensure PostgreSQL is running
if ! pg_isready -h 127.0.0.1 -p 5433 > /dev/null 2>&1; then
    echo "❌ PostgreSQL is not running on port 5433"
    echo "Please start PostgreSQL with: docker-compose up -d postgres"
    exit 1
fi

echo "✅ PostgreSQL is running"

# Download latest data if needed
echo ""
echo "Checking data freshness..."
LAST_DATA_FILE=$(ls -t user_data/data/binance/*1m.json 2>/dev/null | head -1)
if [ -z "$LAST_DATA_FILE" ]; then
    echo "No data found. Downloading..."
    python download_data_quick.py
elif [ $(find "$LAST_DATA_FILE" -mtime +1 -print) ]; then
    echo "Data is older than 1 day. Updating..."
    python download_data_quick.py
else
    echo "✅ Data is up to date"
fi

# Force dry-run mode for safety
echo ""
echo "🔒 SAFETY MODE: Trading in dry-run mode only"
echo "   To enable real trading, manually edit config and remove safety lock"
echo ""

# Start the bot with Phase 1 configuration
echo "Starting Freqtrade with Phase 1 strategy..."
echo "Target: 2-5% monthly returns"
echo ""

freqtrade trade \
    --dry-run \
    --config user_data/configs/config_phase1_optimized.json \
    --strategy MainMultiStrategyPhase1 \
    --db-url "${DATABASE_URL}"