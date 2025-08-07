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

# SAFETY CHECK: Force dry-run mode to prevent accidental real trading
echo "🚨 SAFETY: Multi-Strategy Bot running in DRY-RUN mode only"
echo "Real trading is DISABLED for safety"
echo "To enable real trading, manually edit this script and remove safety checks"
echo ""

# Run freqtrade with Multi-Strategy config (FORCED DRY-RUN FOR SAFETY)
freqtrade trade --config user_data/configs/config_hft_optimized.json --strategy MultiStrategyConsensus --dry-run "$@"