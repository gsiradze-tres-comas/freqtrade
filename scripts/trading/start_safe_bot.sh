#!/bin/bash

# Start SafeBullRiderStrategy in background
# This script handles proper backgrounding and logging

echo "🛡️ Starting SafeBullRiderStrategy Paper Trading Bot..."

# Check if safe bot is already running
if pgrep -f "SafeBullRiderStrategy" > /dev/null; then
    echo "⚠️ SafeBullRiderStrategy is already running!"
    echo "Use './scripts/trading/kill_safe_bot.sh' to stop it first"
    exit 1
fi

# Check if database is accessible
if ! psql postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_safe_db -c "SELECT 1" > /dev/null 2>&1; then
    echo "Creating safe bot database..."
    psql postgresql://postgres:postgres@127.0.0.1:5433/postgres -c "CREATE DATABASE freqtrade_safe_db;"
fi

# Start the bot in background with proper logging
nohup freqtrade trade \
    --config user_data/configs/config_safe_bull.json \
    --strategy SafeBullRiderStrategy \
    --logfile user_data/logs/freqtrade_safe.log \
    > user_data/logs/safe_bot_output.log 2>&1 &

# Save the PID
echo $! > user_data/.safe_bot.pid

echo "✅ SafeBullRiderStrategy started with PID: $!"
echo ""
echo "📊 Monitor with:"
echo "   tail -f user_data/logs/freqtrade_safe.log"
echo ""
echo "🛑 Stop with:"
echo "   ./scripts/trading/kill_safe_bot.sh"
echo ""
echo "🌐 Web UI available at:"
echo "   http://127.0.0.1:8081 (if configured on different port)"
echo ""
echo "📈 The bot is now running in background with safety features:"
echo "   - Daily loss limit: 2%"
echo "   - No trading 1-5 AM UTC"
echo "   - Max 3 correlated positions"
echo "   - Market crash detection active"