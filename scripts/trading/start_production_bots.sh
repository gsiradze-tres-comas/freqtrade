#!/bin/bash

# Start Production Bots Script
# Runs both SafeBullRider and BeastModeV3 in background

echo "🚀 STARTING PRODUCTION TRADING BOTS"
echo "===================================="

# Kill any existing bots first
echo "🛑 Cleaning up old processes..."
pkill -f "freqtrade trade" 2>/dev/null
sleep 2

# Start SafeBullRider on port 8081
echo ""
echo "📊 Starting SafeBullRider Strategy (Port 8081)..."
echo "   - Main production trading bot"
echo "   - Web UI: http://127.0.0.1:8081"

nohup freqtrade trade \
    --config user_data/configs/config_safe_bull.json \
    --strategy SafeBullRiderStrategy \
    --logfile user_data/logs/safebull_$(date +%Y%m%d).log \
    > user_data/logs/safebull_output.log 2>&1 &

SAFEBULL_PID=$!
echo "   ✅ SafeBullRider started (PID: $SAFEBULL_PID)"

sleep 3

# Start BeastModeV3 Analytics on port 8080
echo ""
echo "📈 Starting BeastModeV3 Analytics (Port 8080)..."
echo "   - Analytics and data collection bot"
echo "   - Web UI: http://127.0.0.1:8080"
echo "   - Database: PostgreSQL port 5433"

nohup freqtrade trade \
    --config user_data/configs/config_beastmode_8080.json \
    --strategy BeastModeStrategyV3 \
    --logfile user_data/logs/beastmode_$(date +%Y%m%d).log \
    > user_data/logs/beastmode_output.log 2>&1 &

BEAST_PID=$!
echo "   ✅ BeastModeV3 started (PID: $BEAST_PID)"

# Save PIDs to file for easy killing later
echo $SAFEBULL_PID > user_data/logs/safebull.pid
echo $BEAST_PID > user_data/logs/beastmode.pid

echo ""
echo "===================================="
echo "✅ BOTH BOTS RUNNING IN BACKGROUND"
echo ""
echo "📍 Web Interfaces:"
echo "   SafeBullRider: http://127.0.0.1:8081 (login: freqtrade/freqtrade)"
echo "   BeastModeV3:   http://127.0.0.1:8080 (login: freqtrade/freqtrade)"
echo ""
echo "📁 Log Files:"
echo "   SafeBull logs:  tail -f user_data/logs/safebull_$(date +%Y%m%d).log"
echo "   BeastMode logs: tail -f user_data/logs/beastmode_$(date +%Y%m%d).log"
echo ""
echo "🛑 To stop all bots:"
echo "   ./scripts/trading/kill_script.sh"
echo ""
echo "📊 To check status:"
echo "   ps aux | grep freqtrade | grep -v grep"
echo ""
echo "💡 Monitor performance:"
echo "   ./scripts/trading/monitor_performance.sh"
echo ""