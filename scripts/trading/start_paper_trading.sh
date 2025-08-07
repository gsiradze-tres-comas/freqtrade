#!/bin/bash

# 🚀 Start Try1BullRiderStrategy in Paper Trading Mode
# This will run the profitable strategy live with real-time data
# All trades are simulated (dry-run) but tracked in database

echo "🚀 Starting Try1BullRiderStrategy Paper Trading..."
echo "📊 Strategy: Profitable bull market trend-following"
echo "🎯 Target: 25 trades/day, 76% win rate, +6.69% monthly"
echo "💾 Database: PostgreSQL for comprehensive tracking"
echo "🔒 Safety: Dry-run mode (no real money)"
echo ""

# Check if bot is already running
EXISTING_PID=$(ps aux | grep "freqtrade trade" | grep -v grep | awk '{print $2}')
if [ ! -z "$EXISTING_PID" ]; then
    echo "❌ ERROR: Freqtrade bot is already running!"
    echo "📍 Process ID: $EXISTING_PID"
    echo "⏹️  To stop existing bot: ./kill_script.sh"
    echo "📊 To monitor existing bot: ./monitor_performance.sh"
    echo "🌐 Web UI: http://127.0.0.1:8080"
    echo ""
    echo "❗ Only one bot instance should run at a time to prevent conflicts."
    exit 1
fi

echo "✅ No existing bot detected, proceeding..."
echo ""

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "📁 Loading environment variables from .env file..."
    set -a  # automatically export all variables
    source .env
    set +a  # turn off automatic export
    echo "✅ Environment variables loaded"
else
    echo "⚠️  No .env file found, checking system environment variables..."
fi

# Ensure API keys are set
if [ -z "$BINANCE_API_KEY" ] || [ -z "$BINANCE_API_SECRET" ]; then
    echo "❌ ERROR: Binance API keys not set!"
    echo "Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables"
    echo "Or add them to .env.local file"
    exit 1
fi

# Set API keys for this session
export FREQTRADE__EXCHANGE__KEY="${BINANCE_API_KEY}"
export FREQTRADE__EXCHANGE__SECRET="${BINANCE_API_SECRET}"

echo "✅ API keys configured"
echo "🏃 Starting paper trading bot..."
echo "📱 Web UI will be available at: http://127.0.0.1:8080"
echo "👤 Login: freqtrade / freqtrade"
echo ""
echo "📝 To monitor logs in real-time:"
echo "   tail -f user_data/logs/freqtrade_hft.log"
echo ""
echo "⏹️  To stop the bot:"
echo "   ./kill_script.sh"
echo ""

# Start the bot
freqtrade trade \
    --config user_data/configs/config_billionaire.json \
    --strategy Try1BullRiderStrategy \
    -v

echo ""
echo "🔴 Paper trading stopped."